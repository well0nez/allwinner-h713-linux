// SPDX-License-Identifier: GPL-2.0
/*
 * gles-tear -- score tearing on the GPU presentation path.
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -o gles-tear gles-tear.c -lEGL -lGLESv2
 *   run with EGL_PLATFORM=surfaceless, after modprobe sunxi-scanout-dmabuf
 *
 * Draws the SAME content h713-present's `bar` does -- one red bar on blue,
 * stepping 16 px/frame -- but rendered by the GPU into a scanout dma-buf and
 * published through the same AFBD_SRC + commit the video path uses. Synthetic
 * and decoder-independent on purpose: a decoder fault must not be able to
 * present as a display fault, which is the discipline the CPU-path measurement
 * used and the reason its result survived.
 *
 * Score the capture with tools/display/tear-measure.py, which counts ROWS WITH
 * NO BAR. That metric is not arbitrary: rolling shutter and keystone can shift
 * a bar but can never delete it, so a barless row is specific to a raster
 * catching a surface that was blued but not yet barred. Measuring the bar's
 * position instead measures the camera -- already tried, already discarded.
 *
 * TWO PHASES, FORCED. On a CPU fill the blue pass and the bar pass are
 * naturally separated in time. Mali is a tile-based renderer: a clear plus a
 * draw resolve together per tile at flush, so the window would not exist and
 * the metric would have nothing to detect. `glFinish()` between the passes
 * recreates it deliberately, which is what makes the single-buffered control a
 * valid positive.
 *
 * Modes, and the comparison only means something with all three:
 *   db      double-buffered, the real path. Expect the ~23% floor.
 *   sb      SINGLE-buffered, rendering into the live surface. Positive
 *           control; the CPU path read 59.38% here.
 *   noflip  full workload, scanout pinned to a buffer written once. The
 *           floor itself -- the displayed surface CANNOT be corrupted, so
 *           whatever this reads is the instrument's cost for this workload,
 *           not tearing. The CPU path's 23.03%.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <fcntl.h>
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
#define FB_FRONT 0x6c100000UL
#define FB_BACK  0x6c500000UL
#define DRM_FORMAT_ARGB8888 0x34325241

#define AFBD_BASE    0x05600000UL
#define AFBD_CTRL    0x140
#define AFBD_READY   0x144
#define AFBD_STATUS  0x168
#define AFBD_SRC     0x178
#define CCU_AFBD_CLK 0x02001dc0UL

#define SCANOUT_IOC_GET_FD _IOWR('S', 1, struct scanout_req)
struct scanout_req {
	uint64_t phys;
	uint64_t size;
	int32_t  fd;
	uint32_t pad;
};

static PFNEGLCREATEIMAGEKHRPROC eglCreateImageKHR_;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC glEGLImageTargetTexture2DOES_;
static EGLDisplay dpy;
static volatile uint32_t *regs;

static const char *VS =
	"attribute vec2 p;\nvoid main(){ gl_Position = vec4(p,0.0,1.0); }\n";
static const char *FS =
	"precision mediump float;\nuniform vec4 col;\n"
	"void main(){ gl_FragColor = col; }\n";

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static uint32_t rd(unsigned o) { return regs[o / 4]; }
static void wr(unsigned o, uint32_t v) { regs[o / 4] = v; }

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

struct target {
	unsigned long phys;
	GLuint tex, fbo;
};

static int target_init(struct target *t, int sfd, unsigned long phys)
{
	struct scanout_req req = { .phys = phys, .size = (uint64_t)W * H * 4 };
	EGLImageKHR img;
	EGLint attr[] = {
		EGL_WIDTH, W, EGL_HEIGHT, H,
		EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_ARGB8888,
		EGL_DMA_BUF_PLANE0_FD_EXT, 0,
		EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
		EGL_DMA_BUF_PLANE0_PITCH_EXT, W * 4,
		EGL_NONE
	};

	if (ioctl(sfd, SCANOUT_IOC_GET_FD, &req) < 0) {
		perror("SCANOUT_IOC_GET_FD");
		return -1;
	}
	attr[7] = req.fd;
	img = eglCreateImageKHR_(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT,
				 NULL, attr);
	if (img == EGL_NO_IMAGE_KHR) {
		fprintf(stderr, "EGLImage over %#lx failed 0x%x\n", phys,
			eglGetError());
		return -1;
	}
	t->phys = phys;
	glGenTextures(1, &t->tex);
	glBindTexture(GL_TEXTURE_2D, t->tex);
	glEGLImageTargetTexture2DOES_(GL_TEXTURE_2D, img);
	glGenFramebuffers(1, &t->fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, t->fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
			       GL_TEXTURE_2D, t->tex, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
		fprintf(stderr, "FBO over %#lx incomplete\n", phys);
		return -1;
	}
	close(req.fd);
	return 0;
}

int main(int argc, char **argv)
{
	struct target tgt[2];
	GLuint prog, vs, fs, vbo;
	GLint ucol, uploc;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n, major, minor;
	int sfd, mfd, i, frames, timeouts = 0, mode;
	double t0, fill_tot = 0;
	const char *m;

	static const EGLint cfg_attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE
	};
	static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const GLfloat full[] = { -1, -1,  1, -1, -1, 1,  1, 1 };

	setvbuf(stdout, NULL, _IONBF, 0);
	m = argc >= 2 ? argv[1] : "db";
	frames = argc >= 3 ? atoi(argv[2]) : 600;
	mode = !strcmp(m, "sb") ? 1 : (!strcmp(m, "noflip") ? 2 : 0);
	if (strcmp(m, "db") && strcmp(m, "sb") && strcmp(m, "noflip")) {
		fprintf(stderr, "usage: gles-tear <db|sb|noflip> [frames]\n");
		return 2;
	}

	mfd = open("/dev/mem", O_RDWR | O_SYNC);
	if (mfd < 0) { perror("/dev/mem"); return 1; }
	{
		volatile uint32_t *ccu = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED,
					      mfd, CCU_AFBD_CLK & ~0xfffUL);
		if (ccu == MAP_FAILED) { perror("mmap ccu"); return 1; }
		if (!(ccu[(CCU_AFBD_CLK & 0xfff) / 4] & (1u << 31))) {
			fprintf(stderr, "AFBD clock gated: bring the display up "
				"in U-Boot first\n");
			return 1;
		}
	}
	regs = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, AFBD_BASE);
	if (regs == MAP_FAILED) { perror("mmap afbd"); return 1; }

	sfd = open("/dev/scanout-dmabuf", O_RDWR);
	if (sfd < 0) { perror("/dev/scanout-dmabuf"); return 1; }

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
	glEGLImageTargetTexture2DOES_ =
		(void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");
	printf("renderer: %s  mode: %s  frames: %d\n",
	       glGetString(GL_RENDERER), m, frames);

	if (target_init(&tgt[0], sfd, FB_FRONT) ||
	    target_init(&tgt[1], sfd, FB_BACK))
		return 1;

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
	ucol = glGetUniformLocation(prog, "col");
	uploc = 0;
	glGenBuffers(1, &vbo);
	glBindBuffer(GL_ARRAY_BUFFER, vbo);
	glBufferData(GL_ARRAY_BUFFER, sizeof(full), full, GL_DYNAMIC_DRAW);
	glEnableVertexAttribArray(uploc);
	glVertexAttribPointer(uploc, 2, GL_FLOAT, GL_FALSE, 0, 0);
	glViewport(0, 0, W, H);

	/*
	 * noflip: the displayed surface is written ONCE -- with a real bar --
	 * and then never touched again, while the per-frame workload renders
	 * into the other slot.
	 *
	 * It must be a BAR, not a blue clear. The metric counts rows that have
	 * lost the bar, so a solid-blue reference scores every row as missing
	 * and the scorer reports "no frame yielded a usable bar" instead. The
	 * first version of this cleared to blue and produced exactly that,
	 * wasting a capture: the floor run has to be visually identical to the
	 * runs it is the floor FOR, differing only in that its pixels cannot
	 * change.
	 */
	if (mode == 2) {
		GLfloat bar0[] = { -1, -1, -1 + 128.0f / W, -1,
				   -1, 1, -1 + 128.0f / W, 1 };

		glBindFramebuffer(GL_FRAMEBUFFER, tgt[0].fbo);
		glBufferData(GL_ARRAY_BUFFER, sizeof(full), full, GL_DYNAMIC_DRAW);
		glUniform4f(ucol, 0, 0, 1, 1);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
		glBufferData(GL_ARRAY_BUFFER, sizeof(bar0), bar0, GL_DYNAMIC_DRAW);
		glUniform4f(ucol, 1, 0, 0, 1);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
		glFinish();
		wr(AFBD_SRC, (uint32_t)FB_FRONT);
		commit_frame();
	}

	t0 = now_ms();
	for (i = 0; i < frames; i++) {
		int slot = (mode == 0) ? (i & 1) : (mode == 1 ? 0 : 1);
		int x0 = (i * 16) % W;
		float xl = (float)x0 / W * 2.0f - 1.0f;
		float xr = (float)(x0 + 64) / W * 2.0f - 1.0f;
		GLfloat bar[] = { xl, -1, xr, -1, xl, 1, xr, 1 };
		double a = now_ms(), b;

		glBindFramebuffer(GL_FRAMEBUFFER, tgt[slot].fbo);

		/* Phase 1: blue the whole surface, and make it land. */
		glBufferData(GL_ARRAY_BUFFER, sizeof(full), full, GL_DYNAMIC_DRAW);
		glUniform4f(ucol, 0, 0, 1, 1);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
		glFinish();

		/* Phase 2: the bar. A raster between the two sees no bar. */
		glBufferData(GL_ARRAY_BUFFER, sizeof(bar), bar, GL_DYNAMIC_DRAW);
		glUniform4f(ucol, 1, 0, 0, 1);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
		glFinish();
		b = now_ms();

		if (mode != 2)
			wr(AFBD_SRC, (uint32_t)tgt[slot].phys);
		if (commit_frame() < 0)
			timeouts++;
		fill_tot += b - a;
	}

	{
		double el = now_ms() - t0;

		printf("%s: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
		       "     render mean %.2f ms of a 16.75 ms frame (%.1f%%)\n",
		       m, frames, el, frames / (el / 1000.0), timeouts,
		       fill_tot / frames, 100.0 * (fill_tot / frames) / 16.75);
	}

	/* Always finish on the front buffer, as every tool here does. */
	glBindFramebuffer(GL_FRAMEBUFFER, tgt[0].fbo);
	glClearColor(0, 0, 1, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glFinish();
	wr(AFBD_SRC, (uint32_t)FB_FRONT);
	commit_frame();
	return timeouts ? 1 : 0;
}
