// SPDX-License-Identifier: GPL-2.0
/*
 * gles-nv12 -- can the Mali sample a CEDRUS buffer as NV12 and convert it?
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -o gles-nv12 gles-nv12.c -lEGL -lGLESv2
 *   run with EGL_PLATFORM=surfaceless
 *
 * This is the load-bearing question for the GPU video path. M3 measured the
 * ceiling as the ~44 MB/s CPU read of the decoder's CMA output buffer; the GPU
 * only escapes it if it can import that exact buffer as a dma-buf and sample it
 * directly.
 *
 * The buffer here is a REAL cedrus CAPTURE buffer -- VIDIOC_REQBUFS then
 * VIDIOC_EXPBUF -- because a buffer from anywhere else would not answer the
 * question. Neither ioctl needs streaming, so this tests the import path
 * without also having to drive a stateless decoder.
 *
 * The CPU fills it once with a known pattern (that is the test harness, not the
 * pipeline: in the real thing the VE writes it and the CPU never touches it).
 * Then: import as an NV12 EGLImage, sample through
 * GL_TEXTURE_EXTERNAL_OES, convert in the fragment shader, render to an RGBA8
 * FBO, and read back a handful of pixels to check the colour maths.
 *
 * A pass here means the remaining work is plumbing -- feeding it real decoded
 * frames, and a dma-buf for the scanout region -- rather than an unknown.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define W 1280
#define H 720
#define DRM_FORMAT_NV12 0x3231564e      /* fourcc('N','V','1','2') */

static PFNEGLCREATEIMAGEKHRPROC eglCreateImageKHR_;
static PFNEGLDESTROYIMAGEKHRPROC eglDestroyImageKHR_;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC glEGLImageTargetTexture2DOES_;

static const char *VS =
	"attribute vec2 p;\n"
	"varying vec2 uv;\n"
	"void main() {\n"
	"  uv = vec2(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5);\n"
	"  gl_Position = vec4(p, 0.0, 1.0);\n"
	"}\n";

/*
 * The sampler does the YUV->RGB itself. samplerExternalOES on mesa/panfrost
 * already applies the conversion for an NV12 image, so this is a plain fetch --
 * which is the point: the conversion that costs 10.8 ms of CPU per frame is a
 * texture unit's normal job.
 */
static const char *FS =
	"#extension GL_OES_EGL_image_external : require\n"
	"precision mediump float;\n"
	"uniform samplerExternalOES tex;\n"
	"varying vec2 uv;\n"
	"void main() { gl_FragColor = texture2D(tex, uv); }\n";

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static GLuint mkshader(GLenum type, const char *src)
{
	GLuint s = glCreateShader(type);
	GLint ok = 0;
	char log[512] = { 0 };

	glShaderSource(s, 1, &src, NULL);
	glCompileShader(s);
	glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
	if (!ok) {
		glGetShaderInfoLog(s, sizeof(log) - 1, NULL, log);
		fprintf(stderr, "shader compile failed: %s\n", log);
		return 0;
	}
	return s;
}

/*
 * A cedrus CAPTURE buffer and its dma-buf fd. REQBUFS allocates it in the
 * driver's CMA pool -- the same memory a decode would land in -- and EXPBUF
 * hands out an fd for it without streaming ever starting.
 */
static int cedrus_buffer(int *dmabuf_fd, size_t *size, uint32_t *stride,
			 uint32_t *cw, uint32_t *ch)
{
	struct v4l2_format ofmt = { 0 };
	struct v4l2_format fmt = { 0 };
	struct v4l2_requestbuffers req = { 0 };
	struct v4l2_exportbuffer exp = { 0 };
	int fd = open("/dev/video0", O_RDWR);

	if (fd < 0) { perror("open /dev/video0"); return -1; }

	/*
	 * OUTPUT (coded) format FIRST. A stateless decoder derives CAPTURE
	 * geometry from it -- setting CAPTURE alone yields the 16x16 minimum,
	 * which is a 384-byte buffer and a segfault waiting to happen.
	 */
	ofmt.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
	ofmt.fmt.pix.width = W;
	ofmt.fmt.pix.height = H;
	ofmt.fmt.pix.pixelformat = V4L2_PIX_FMT_H264_SLICE;
	ofmt.fmt.pix.sizeimage = 1 << 20;
	ofmt.fmt.pix.field = V4L2_FIELD_NONE;
	if (ioctl(fd, VIDIOC_S_FMT, &ofmt) < 0) {
		perror("S_FMT OUTPUT (H264_SLICE)");
		close(fd);
		return -1;
	}
	printf("cedrus OUTPUT : %ux%u fourcc=%.4s\n",
	       ofmt.fmt.pix.width, ofmt.fmt.pix.height,
	       (char *)&ofmt.fmt.pix.pixelformat);

	fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	fmt.fmt.pix.width = W;
	fmt.fmt.pix.height = H;
	fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12;
	fmt.fmt.pix.field = V4L2_FIELD_NONE;
	if (ioctl(fd, VIDIOC_S_FMT, &fmt) < 0) {
		perror("S_FMT CAPTURE");
		close(fd);
		return -1;
	}
	printf("cedrus CAPTURE: %ux%u fourcc=%.4s bytesperline=%u sizeimage=%u\n",
	       fmt.fmt.pix.width, fmt.fmt.pix.height,
	       (char *)&fmt.fmt.pix.pixelformat,
	       fmt.fmt.pix.bytesperline, fmt.fmt.pix.sizeimage);
	*stride = fmt.fmt.pix.bytesperline;
	*size = fmt.fmt.pix.sizeimage;
	*cw = fmt.fmt.pix.width;
	*ch = fmt.fmt.pix.height;
	if (!*stride || *size < (size_t)*stride * *ch) {
		fprintf(stderr, "implausible geometry, refusing\n");
		close(fd);
		return -1;
	}

	req.count = 1;
	req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	req.memory = V4L2_MEMORY_MMAP;
	if (ioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
		perror("REQBUFS");
		close(fd);
		return -1;
	}

	exp.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	exp.index = 0;
	exp.flags = O_RDWR;
	if (ioctl(fd, VIDIOC_EXPBUF, &exp) < 0) {
		perror("EXPBUF -- cedrus cannot export this buffer");
		close(fd);
		return -1;
	}
	*dmabuf_fd = exp.fd;
	printf("EXPBUF ok: dmabuf fd=%d, %zu bytes, stride %u\n",
	       exp.fd, *size, *stride);
	return fd;
}

/*
 * Known pattern so the readback can be checked rather than eyeballed.
 * Geometry comes from the driver, not from W/H: cedrus aligns the CAPTURE
 * height, and writing this against assumed dimensions is what turned a wrong
 * format into a segfault the first time.
 */
static void fill_pattern(uint8_t *p, uint32_t stride, uint32_t w, uint32_t h,
			 size_t size)
{
	size_t csoff = (size_t)stride * h;
	uint8_t *y = p, *c = p + csoff;
	uint32_t i, j;

	memset(p, 0, size);
	for (i = 0; i < h; i++)
		for (j = 0; j < w; j++)
			y[(size_t)i * stride + j] =
				(j < w / 3) ? 81 : (j < 2 * w / 3 ? 145 : 41);
	for (i = 0; i < h / 2; i++) {
		if (csoff + (size_t)i * stride + w > size)
			break;
		for (j = 0; j + 1 < w; j += 2) {
			uint8_t u, v;

			if (j < w / 3)       { u = 90;  v = 240; }   /* red   */
			else if (j < 2*w/3)  { u = 54;  v = 34;  }   /* green */
			else                 { u = 240; v = 110; }   /* blue  */
			c[(size_t)i * stride + j] = u;
			c[(size_t)i * stride + j + 1] = v;
		}
	}
}

int main(void)
{
	EGLDisplay dpy;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n, major, minor;
	EGLImageKHR img;
	GLuint tex, fbo, rb, prog, vs, fs, vbo;
	int vfd, dfd = -1, i, bad = 0;
	size_t size = 0;
	uint32_t stride = 0, cw = 0, ch = 0;
	uint8_t *map;
	uint8_t *px;
	double t0;

	/* Unbuffered: a segfault must not swallow the progress printed so far. */
	setvbuf(stdout, NULL, _IONBF, 0);

	static const EGLint cfg_attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE
	};
	static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const GLfloat quad[] = { -1, -1,  1, -1, -1, 1,  1, 1 };

	vfd = cedrus_buffer(&dfd, &size, &stride, &cw, &ch);
	if (vfd < 0)
		return 1;

	/* Fill once from the CPU -- harness only; the VE does this for real. */
	map = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, dfd, 0);
	if (map == MAP_FAILED) {
		perror("mmap dmabuf");
		return 1;
	}
	fill_pattern(map, stride, cw, ch, size);
	munmap(map, size);

	dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	if (!eglInitialize(dpy, &major, &minor)) {
		fprintf(stderr, "eglInitialize failed 0x%x\n", eglGetError());
		return 1;
	}
	eglBindAPI(EGL_OPENGL_ES_API);
	eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n);
	ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
	eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx);
	printf("renderer: %s\n", glGetString(GL_RENDERER));

	eglCreateImageKHR_ = (void *)eglGetProcAddress("eglCreateImageKHR");
	eglDestroyImageKHR_ = (void *)eglGetProcAddress("eglDestroyImageKHR");
	glEGLImageTargetTexture2DOES_ =
		(void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");
	if (!eglCreateImageKHR_ || !glEGLImageTargetTexture2DOES_) {
		fprintf(stderr, "dma-buf import entry points missing\n");
		return 1;
	}

	{
		EGLint attr[] = {
			EGL_WIDTH, (EGLint)cw,
			EGL_HEIGHT, (EGLint)ch,
			EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_NV12,
			EGL_DMA_BUF_PLANE0_FD_EXT, dfd,
			EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
			EGL_DMA_BUF_PLANE0_PITCH_EXT, (EGLint)stride,
			EGL_DMA_BUF_PLANE1_FD_EXT, dfd,
			EGL_DMA_BUF_PLANE1_OFFSET_EXT, (EGLint)(stride * ch),
			EGL_DMA_BUF_PLANE1_PITCH_EXT, (EGLint)stride,
			EGL_YUV_COLOR_SPACE_HINT_EXT, EGL_ITU_REC709_EXT,
			EGL_SAMPLE_RANGE_HINT_EXT, EGL_YUV_NARROW_RANGE_EXT,
			EGL_NONE
		};

		img = eglCreateImageKHR_(dpy, EGL_NO_CONTEXT,
					 EGL_LINUX_DMA_BUF_EXT, NULL, attr);
		if (img == EGL_NO_IMAGE_KHR) {
			fprintf(stderr, "eglCreateImageKHR(NV12) failed: 0x%x\n",
				eglGetError());
			return 1;
		}
		printf("EGLImage from cedrus dma-buf: ok\n");
	}

	glGenTextures(1, &tex);
	glBindTexture(GL_TEXTURE_EXTERNAL_OES, tex);
	glEGLImageTargetTexture2DOES_(GL_TEXTURE_EXTERNAL_OES, img);
	glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_EXTERNAL_OES, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	if (glGetError() != GL_NO_ERROR) {
		fprintf(stderr, "binding EGLImage to texture failed\n");
		return 1;
	}
	printf("bound as GL_TEXTURE_EXTERNAL_OES: ok\n");

	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glGenRenderbuffers(1, &rb);
	glBindRenderbuffer(GL_RENDERBUFFER, rb);
	glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8_OES, cw, ch);
	glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
				  GL_RENDERBUFFER, rb);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
		fprintf(stderr, "FBO incomplete\n");
		return 1;
	}

	vs = mkshader(GL_VERTEX_SHADER, VS);
	fs = mkshader(GL_FRAGMENT_SHADER, FS);
	if (!vs || !fs)
		return 1;
	prog = glCreateProgram();
	glAttachShader(prog, vs);
	glAttachShader(prog, fs);
	glBindAttribLocation(prog, 0, "p");
	glLinkProgram(prog);
	{
		GLint ok = 0;
		char log[512] = { 0 };

		glGetProgramiv(prog, GL_LINK_STATUS, &ok);
		if (!ok) {
			glGetProgramInfoLog(prog, sizeof(log) - 1, NULL, log);
			fprintf(stderr, "link failed: %s\n", log);
			return 1;
		}
	}
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, "tex"), 0);
	glActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_EXTERNAL_OES, tex);

	glGenBuffers(1, &vbo);
	glBindBuffer(GL_ARRAY_BUFFER, vbo);
	glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
	glEnableVertexAttribArray(0);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0);

	glViewport(0, 0, cw, ch);
	glClearColor(0, 0, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	glFinish();

	px = malloc((size_t)cw * ch * 4);
	glReadPixels(0, 0, cw, ch, GL_RGBA, GL_UNSIGNED_BYTE, px);

	{
		struct { const char *name; unsigned x; int r, g, b; } probe[] = {
			{ "red  ", cw / 6,     255, 0,   0   },
			{ "green", cw / 2,     0,   255, 0   },
			{ "blue ", 5 * cw / 6, 0,   0,   255 },
		};

		for (i = 0; i < 3; i++) {
			uint8_t *q = px + ((size_t)(ch / 2) * cw + probe[i].x) * 4;
			int dr = abs(q[0] - probe[i].r);
			int dg = abs(q[1] - probe[i].g);
			int db = abs(q[2] - probe[i].b);
			int ok = dr < 60 && dg < 60 && db < 60;

			printf("  %s got %3d,%3d,%3d  want %3d,%3d,%3d  %s\n",
			       probe[i].name, q[0], q[1], q[2],
			       probe[i].r, probe[i].g, probe[i].b,
			       ok ? "ok" : "BAD");
			if (!ok)
				bad++;
		}
	}

	/* Throughput of the conversion the CPU currently spends 10.8 ms on. */
	t0 = now_ms();
	for (i = 0; i < 100; i++)
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	glFinish();
	{
		double ms = now_ms() - t0;

		printf("100 NV12->RGB passes at %ux%u: %.1f ms (%.2f ms/frame, "
		       "%.0f fps equivalent)\n", cw, ch, ms, ms / 100.0,
		       100000.0 / ms);
	}

	printf("%s\n", bad ? "FAIL: colour wrong" :
	       "PASS: GPU sampled a cedrus dma-buf and converted it");
	glDeleteFramebuffers(1, &fbo);
	eglDestroyImageKHR_(dpy, img);
	close(dfd);
	close(vfd);
	return bad ? 1 : 0;
}
