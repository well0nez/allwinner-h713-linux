// SPDX-License-Identifier: GPL-2.0
/*
 * gles-play -- decoded H.264 on the panel with the CPU never touching a pixel.
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -o gles-play gles-play.c $(pkg-config --cflags --libs \
 *       gstreamer-1.0 gstreamer-app-1.0 gstreamer-allocators-1.0 \
 *       gstreamer-video-1.0) -lEGL -lGLESv2
 *   run with EGL_PLATFORM=surfaceless, after:
 *     modprobe sunxi_scanout_dmabuf   (images built since 2026-08-15 autoload
 *                                      it from /etc/modules-load.d)
 *     (display already up from U-Boot)
 *
 * gstreamer-video-1.0 in that list is required, not decoration:
 * gst_video_info_from_caps, gst_buffer_get_video_meta and
 * gst_video_meta_api_get_type all live in libgstvideo and nothing else here
 * pulls it. It was missing until 2026-08-15, when compiling this file inside a
 * freshly built rootfs showed the documented command had never linked.
 *
 * The whole point, and what M3 says it is worth: the CPU read of the decoder's
 * output was the 28.3 fps ceiling, at ~44 MB/s uncached. Here the VE decodes
 * into a CMA buffer, GStreamer hands us that buffer's dma-buf FD, the GPU
 * samples it directly and renders into the scanout carveout, and AFBD scans
 * that out. No pixel crosses the CPU at any point.
 *
 * Pieces proved separately before this existed:
 *   gles-nv12.c    GPU samples a cedrus dma-buf, 0.64 ms/frame convert
 *   gles-scanout.c GPU renders into 0x6c100000, verified via /dev/mem
 * This is the wiring, plus the flip.
 *
 * v4l2slh264dec advertises video/x-raw(memory:DMABuf), so the caps filter is
 * what makes the decoder hand out FDs rather than copied buffers. If that
 * negotiation fails the pipeline still runs and silently gives system memory,
 * which would quietly reintroduce the copy -- so the code REFUSES a buffer
 * that is not dma-buf backed rather than falling back.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <fcntl.h>
#include <gst/allocators/gstdmabuf.h>
#include <gst/app/gstappsink.h>
#include <gst/gst.h>
#include <gst/video/video.h>
#include <gst/video/video-info-dma.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define FB_FRONT 0x6c100000UL
#define FB_BACK  0x6c500000UL
#define DRM_FORMAT_NV12     0x3231564e
#define DRM_FORMAT_ARGB8888 0x34325241

#define AFBD_BASE   0x05600000UL
#define AFBD_CTRL   0x140
#define AFBD_READY  0x144
#define AFBD_STATUS 0x168
#define AFBD_SRC    0x178
#define CCU_AFBD_CLK 0x02001dc0UL

#define SCANOUT_IOC_GET_FD _IOWR('S', 1, struct scanout_req)
struct scanout_req {
	uint64_t phys;
	uint64_t size;
	int32_t  fd;
	uint32_t pad;
};

static PFNEGLCREATEIMAGEKHRPROC eglCreateImageKHR_;
static PFNEGLDESTROYIMAGEKHRPROC eglDestroyImageKHR_;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC glEGLImageTargetTexture2DOES_;

static EGLDisplay dpy;
static volatile uint32_t *regs;
static int width, height;

static const char *VS =
	"attribute vec2 p;\nvarying vec2 uv;\n"
	"void main(){ uv = vec2(p.x*0.5+0.5, 0.5-p.y*0.5);\n"
	"             gl_Position = vec4(p,0.0,1.0); }\n";
static const char *FS =
	"#extension GL_OES_EGL_image_external : require\n"
	"precision mediump float;\n"
	"uniform samplerExternalOES tex;\nvarying vec2 uv;\n"
	"void main(){ gl_FragColor = texture2D(tex, uv); }\n";

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static uint32_t rd(unsigned off) { return regs[off / 4]; }
static void wr(unsigned off, uint32_t v) { regs[off / 4] = v; }

/* The vendor's publish order, same as h713-present's commit(). */
static double commit_frame(void)
{
	uint32_t pending = rd(AFBD_STATUS);
	double t0;

	if (pending)
		wr(AFBD_STATUS, pending);
	wr(AFBD_CTRL, rd(AFBD_CTRL) | 1u);
	wr(AFBD_READY, 1);
	t0 = now_ms();
	while (now_ms() - t0 < 50.0) {
		if (rd(AFBD_STATUS) & 2u)
			return now_ms() - t0;
		usleep(100);
	}
	return -1.0;
}

static GLuint mkshader(GLenum t, const char *src)
{
	GLuint s = glCreateShader(t);
	GLint ok = 0;
	char log[512] = { 0 };

	glShaderSource(s, 1, &src, NULL);
	glCompileShader(s);
	glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
	if (!ok) {
		glGetShaderInfoLog(s, sizeof(log) - 1, NULL, log);
		fprintf(stderr, "compile: %s\n", log);
		return 0;
	}
	return s;
}


/*
 * The decoder REFUSES DMABuf caps unless downstream advertises GstVideoMeta:
 *
 *   ERROR v4l2codecs-h264dec: DMABuf caps negotiated without the mandatory
 *                             support of VideoMeta
 *   ERROR v4l2codecs-h264dec: Failed to negotiate with downstream
 *
 * which surfaces as the far less helpful "No valid frames decoded before end
 * of stream". It is mandatory because with dma-buf the plane strides and
 * offsets come from the meta rather than from the caps -- exactly the numbers
 * this program feeds to EGL. fakesink cannot advertise it, which is why the
 * gst-launch version of this pipeline could never have worked.
 */
static gboolean on_propose_allocation(GstElement *sink, GstQuery *query,
				      gpointer user_data)
{
	gst_query_add_allocation_meta(query, GST_VIDEO_META_API_TYPE, NULL);
	return TRUE;
}

/* An FBO over one scanout slot, so the GPU renders where AFBD fetches. */
struct target {
	unsigned long phys;
	GLuint tex, fbo;
	EGLImageKHR img;
};

static int target_init(struct target *t, int sfd, unsigned long phys)
{
	struct scanout_req req = { .phys = phys,
				   .size = (uint64_t)width * height * 4 };
	EGLint attr[] = {
		EGL_WIDTH, width,
		EGL_HEIGHT, height,
		EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_ARGB8888,
		EGL_DMA_BUF_PLANE0_FD_EXT, 0,
		EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
		EGL_DMA_BUF_PLANE0_PITCH_EXT, width * 4,
		EGL_NONE
	};

	if (ioctl(sfd, SCANOUT_IOC_GET_FD, &req) < 0) {
		perror("SCANOUT_IOC_GET_FD");
		return -1;
	}
	attr[7] = req.fd;
	t->phys = phys;
	t->img = eglCreateImageKHR_(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT,
				    NULL, attr);
	if (t->img == EGL_NO_IMAGE_KHR) {
		fprintf(stderr, "EGLImage over %#lx failed: 0x%x\n",
			phys, eglGetError());
		return -1;
	}
	glGenTextures(1, &t->tex);
	glBindTexture(GL_TEXTURE_2D, t->tex);
	glEGLImageTargetTexture2DOES_(GL_TEXTURE_2D, t->img);
	glGenFramebuffers(1, &t->fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, t->fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
			       GL_TEXTURE_2D, t->tex, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
		fprintf(stderr, "FBO over %#lx incomplete\n", phys);
		return -1;
	}
	close(req.fd);          /* EGL holds its own reference */
	return 0;
}

int main(int argc, char **argv)
{
	GstElement *pipeline, *sink;
	GstStateChangeReturn sret;
	struct target tgt[2];
	GLuint prog, vs, fs, vbo;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n, major, minor;
	int sfd, mfd, frames = 0, slot = 0, timeouts = 0, nondma = 0;
	double t_start, conv_tot = 0, commit_tot = 0;
	char desc[512];
	uint32_t gate;

	static const EGLint cfg_attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE
	};
	static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const GLfloat quad[] = { -1, -1,  1, -1, -1, 1,  1, 1 };

	setvbuf(stdout, NULL, _IONBF, 0);
	if (argc < 2) {
		fprintf(stderr, "usage: gles-play <file.h264> [max-frames]\n");
		return 2;
	}
	gst_init(&argc, &argv);

	/* Refuse to run blind against a dark panel, as h713-present does. */
	mfd = open("/dev/mem", O_RDWR | O_SYNC);
	if (mfd < 0) { perror("/dev/mem"); return 1; }
	{
		volatile uint32_t *ccu = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED,
					      mfd, CCU_AFBD_CLK & ~0xfffUL);

		if (ccu == MAP_FAILED) { perror("mmap ccu"); return 1; }
		gate = ccu[(CCU_AFBD_CLK & 0xfff) / 4];
		if (!(gate & (1u << 31))) {
			fprintf(stderr, "AFBD clock gated (%08x): run "
				"'h713_disp auto 0x34 logo' in U-Boot first\n", gate);
			return 1;
		}
	}
	regs = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, AFBD_BASE);
	if (regs == MAP_FAILED) { perror("mmap afbd"); return 1; }

	sfd = open("/dev/scanout-dmabuf", O_RDWR);
	if (sfd < 0) {
		perror("/dev/scanout-dmabuf (insmod sunxi-scanout-dmabuf.ko?)");
		return 1;
	}

	/*
	 * memory:DMABuf is the load-bearing part: it is what makes
	 * v4l2slh264dec hand out the decoder's own buffers instead of copies.
	 *
	 * format=DMA_DRM, not format=NV12. Since GStreamer 1.24 the DMABuf
	 * caps carry a DRM fourcc plus modifier in a drm-format field and the
	 * `format` field is the literal token DMA_DRM; asking for
	 * format=NV12 here fails to link with "can't handle caps".
	 */
	snprintf(desc, sizeof(desc),
		 "filesrc location=\"%s\" ! h264parse ! v4l2slh264dec ! "
		 "%s ! "
		 "appsink name=out max-buffers=2 drop=false sync=false",
		 argv[1],
		 getenv("GLES_CAPS") ? getenv("GLES_CAPS") :
		 "video/x-raw,format=NV12");
	pipeline = gst_parse_launch(desc, NULL);
	if (!pipeline) {
		fprintf(stderr, "pipeline build failed\n");
		return 1;
	}
	sink = gst_bin_get_by_name(GST_BIN(pipeline), "out");
	g_signal_connect(sink, "propose-allocation",
			 G_CALLBACK(on_propose_allocation), NULL);
	sret = gst_element_set_state(pipeline, GST_STATE_PLAYING);
	if (sret == GST_STATE_CHANGE_FAILURE) {
		fprintf(stderr, "pipeline will not play\n");
		return 1;
	}

	dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	if (!eglInitialize(dpy, &major, &minor)) {
		fprintf(stderr, "eglInitialize 0x%x\n", eglGetError());
		return 1;
	}
	eglBindAPI(EGL_OPENGL_ES_API);
	eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n);
	ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
	eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx);
	eglCreateImageKHR_ = (void *)eglGetProcAddress("eglCreateImageKHR");
	eglDestroyImageKHR_ = (void *)eglGetProcAddress("eglDestroyImageKHR");
	glEGLImageTargetTexture2DOES_ =
		(void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");
	printf("renderer: %s\n", glGetString(GL_RENDERER));

	vs = mkshader(GL_VERTEX_SHADER, VS);
	fs = mkshader(GL_FRAGMENT_SHADER, FS);
	if (!vs || !fs)
		return 1;
	prog = glCreateProgram();
	glAttachShader(prog, vs);
	glAttachShader(prog, fs);
	glBindAttribLocation(prog, 0, "p");
	glLinkProgram(prog);
	glUseProgram(prog);
	glGenBuffers(1, &vbo);
	glBindBuffer(GL_ARRAY_BUFFER, vbo);
	glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
	glEnableVertexAttribArray(0);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0);

	t_start = now_ms();
	for (;;) {
		GstSample *sample;
		GstBuffer *buf;
		GstMemory *mem;
		static GstVideoInfo vinfo;
		GstVideoMeta *vmeta;
		GstCaps *caps;
		EGLImageKHR img;
		GLuint tex;
		int dfd, cfd, stride, coff;
		double a, b, c;

		if (argc >= 3 && frames >= atoi(argv[2]))
			break;
		sample = gst_app_sink_pull_sample(GST_APP_SINK(sink));
		if (!sample) {
			/*
			 * NULL is EOS *or* error. Ask the bus which, so a
			 * negotiation failure reports itself rather than
			 * looking like a short clip.
			 */
			GstMessage *m = gst_bus_pop_filtered(
				GST_ELEMENT_BUS(pipeline), GST_MESSAGE_ERROR);

			if (m) {
				GError *err = NULL;
				gchar *dbg = NULL;

				gst_message_parse_error(m, &err, &dbg);
				fprintf(stderr, "pipeline error: %s\n%s\n",
					err ? err->message : "?", dbg ? dbg : "");
				g_clear_error(&err);
				g_free(dbg);
				gst_message_unref(m);
			}
			break;
		}

		buf = gst_sample_get_buffer(sample);
		mem = gst_buffer_peek_memory(buf, 0);
		if (!gst_is_dmabuf_memory(mem)) {
			/*
			 * Not dma-buf: the decoder handed us system memory and
			 * the copy is back. Refuse rather than quietly measure
			 * the thing this whole path exists to remove.
			 */
			nondma++;
			gst_sample_unref(sample);
			if (nondma == 1)
				fprintf(stderr, "buffer is NOT dma-buf backed -- "
					"caps negotiation gave system memory\n");
			break;
		}
		dfd = gst_dmabuf_memory_get_fd(mem);

		if (!frames) {
			caps = gst_sample_get_caps(sample);
			if (!gst_video_info_from_caps(&vinfo, caps)) {
				fprintf(stderr, "unusable caps: %s\n",
					gst_caps_to_string(caps));
				return 1;
			}
			width = GST_VIDEO_INFO_WIDTH(&vinfo);
			height = GST_VIDEO_INFO_HEIGHT(&vinfo);
			printf("decoded %dx%d %s, planes=%u memories=%u fd=%d\n",
			       width, height,
			       GST_VIDEO_INFO_NAME(&vinfo),
			       GST_VIDEO_INFO_N_PLANES(&vinfo),
			       gst_buffer_n_memory(buf), dfd);
			if (GST_VIDEO_INFO_FORMAT(&vinfo) != GST_VIDEO_FORMAT_NV12) {
				fprintf(stderr, "expected NV12\n");
				return 1;
			}
			if (target_init(&tgt[0], sfd, FB_FRONT) ||
			    target_init(&tgt[1], sfd, FB_BACK))
				return 1;
			glViewport(0, 0, width, height);
		}
		/*
		 * Prefer the buffer's own GstVideoMeta: with dma-buf the real
		 * strides and offsets belong to the allocation, and the caps
		 * only carry what the format implies. This is the same meta
		 * the decoder insists downstream support.
		 */
		vmeta = gst_buffer_get_video_meta(buf);
		if (vmeta) {
			stride = vmeta->stride[0];
			coff = vmeta->offset[1];
		} else {
			stride = GST_VIDEO_INFO_PLANE_STRIDE(&vinfo, 0);
			coff = GST_VIDEO_INFO_PLANE_OFFSET(&vinfo, 1);
		}
		/*
		 * Chroma may live in a second dma-buf rather than at an offset
		 * in the first. Use whichever the decoder actually produced.
		 */
		cfd = dfd;
		if (gst_buffer_n_memory(buf) > 1) {
			GstMemory *m1 = gst_buffer_peek_memory(buf, 1);

			if (gst_is_dmabuf_memory(m1)) {
				cfd = gst_dmabuf_memory_get_fd(m1);
				coff = 0;
			}
		}

		a = now_ms();
		{
			EGLint attr[] = {
				EGL_WIDTH, width,
				EGL_HEIGHT, height,
				EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_NV12,
				EGL_DMA_BUF_PLANE0_FD_EXT, dfd,
				EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
				EGL_DMA_BUF_PLANE0_PITCH_EXT, stride,
				EGL_DMA_BUF_PLANE1_FD_EXT, cfd,
				EGL_DMA_BUF_PLANE1_OFFSET_EXT, coff,
				EGL_DMA_BUF_PLANE1_PITCH_EXT, stride,
				EGL_YUV_COLOR_SPACE_HINT_EXT, EGL_ITU_REC709_EXT,
				EGL_SAMPLE_RANGE_HINT_EXT, EGL_YUV_NARROW_RANGE_EXT,
				EGL_NONE
			};

			img = eglCreateImageKHR_(dpy, EGL_NO_CONTEXT,
						 EGL_LINUX_DMA_BUF_EXT, NULL, attr);
		}
		if (img == EGL_NO_IMAGE_KHR) {
			fprintf(stderr, "frame %d: EGLImage failed 0x%x\n",
				frames, eglGetError());
			gst_sample_unref(sample);
			break;
		}

		glGenTextures(1, &tex);
		glBindTexture(GL_TEXTURE_EXTERNAL_OES, tex);
		glEGLImageTargetTexture2DOES_(GL_TEXTURE_EXTERNAL_OES, img);
		glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
		glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
		glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
		glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

		glBindFramebuffer(GL_FRAMEBUFFER, tgt[slot].fbo);
		glUniform1i(glGetUniformLocation(prog, "tex"), 0);
		glActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_EXTERNAL_OES, tex);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
		glFinish();
		b = now_ms();

		/* Publish: point AFBD at the slot the GPU just filled. */
		wr(AFBD_SRC, (uint32_t)tgt[slot].phys);
		if (commit_frame() < 0)
			timeouts++;
		c = now_ms();

		glDeleteTextures(1, &tex);
		eglDestroyImageKHR_(dpy, img);
		gst_sample_unref(sample);

		conv_tot += b - a;
		commit_tot += c - b;
		slot ^= 1;
		frames++;
	}

	{
		double el = now_ms() - t_start;

		if (frames)
			printf("%d frames in %.0f ms (%.2f fps), %d commit timeouts\n"
			       "  mean gpu %.2f ms, commit-wait %.2f ms\n",
			       frames, el, frames / (el / 1000.0), timeouts,
			       conv_tot / frames, commit_tot / frames);
		if (nondma)
			printf("REFUSED: %d buffer(s) were not dma-buf backed\n", nondma);
	}

	/* Leave the panel on the front slot, as every other tool here does. */
	wr(AFBD_SRC, (uint32_t)FB_FRONT);
	commit_frame();
	gst_element_set_state(pipeline, GST_STATE_NULL);
	return frames && !nondma ? 0 : 1;
}
