// SPDX-License-Identifier: GPL-2.0
/*
 * gles-scanout -- render with the GPU straight into the scanout carveout.
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -o gles-scanout gles-scanout.c -lEGL -lGLESv2
 *   run with EGL_PLATFORM=surfaceless, after insmod sunxi-scanout-dmabuf.ko
 *
 * gles-nv12 proved the GPU can SAMPLE a cedrus buffer with no CPU read. This
 * proves the other end: that it can WRITE into the physically contiguous region
 * AFBD scans out of, so the whole path is GPU DMA in and GPU DMA out and the
 * CPU never touches a pixel.
 *
 * The check is deliberately not "does it look right". The GPU renders a known
 * pattern into the imported dma-buf, and the test then reads the SAME physical
 * memory back through /dev/mem -- a completely independent path -- to confirm
 * the bytes are where AFBD will fetch them. Reading back through GL would only
 * prove GL is self-consistent.
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
#define DRM_FORMAT_ARGB8888 0x34325241  /* fourcc('A','R','2','4') */

#define SCANOUT_IOC_GET_FD _IOWR('S', 1, struct scanout_req)
struct scanout_req {
	uint64_t phys;
	uint64_t size;
	int32_t  fd;
	uint32_t pad;
};

static PFNEGLCREATEIMAGEKHRPROC eglCreateImageKHR_;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC glEGLImageTargetTexture2DOES_;

static const char *VS =
	"attribute vec2 p;\nvoid main(){ gl_Position=vec4(p,0.0,1.0); }\n";
/* Output is a function of position, so a correct readback cannot be a clear. */
static const char *FS =
	"precision mediump float;\n"
	"void main(){ gl_FragColor = vec4(gl_FragCoord.x/1280.0,\n"
	"                                 gl_FragCoord.y/720.0, 0.5, 1.0); }\n";

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
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

int main(void)
{
	EGLDisplay dpy;
	EGLContext ctx;
	EGLConfig cfg;
	EGLint n, major, minor;
	EGLImageKHR img;
	GLuint tex, fbo, prog, vs, fs, vbo;
	struct scanout_req req = { .phys = FB_FRONT, .size = (uint64_t)W * H * 4 };
	int sfd, mfd, i, bad = 0;
	volatile uint32_t *fb;
	double t0;

	static const EGLint cfg_attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE
	};
	static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const GLfloat quad[] = { -1, -1,  1, -1, -1, 1,  1, 1 };

	setvbuf(stdout, NULL, _IONBF, 0);

	sfd = open("/dev/scanout-dmabuf", O_RDWR);
	if (sfd < 0) {
		perror("open /dev/scanout-dmabuf (insmod sunxi-scanout-dmabuf.ko?)");
		return 1;
	}
	if (ioctl(sfd, SCANOUT_IOC_GET_FD, &req) < 0) {
		perror("SCANOUT_IOC_GET_FD");
		return 1;
	}
	printf("scanout dma-buf: fd=%d phys=%#llx size=%llu\n",
	       req.fd, (unsigned long long)req.phys,
	       (unsigned long long)req.size);

	dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	if (!eglInitialize(dpy, &major, &minor)) {
		fprintf(stderr, "eglInitialize 0x%x\n", eglGetError());
		return 1;
	}
	eglBindAPI(EGL_OPENGL_ES_API);
	eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n);
	ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
	eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx);
	printf("renderer: %s\n", glGetString(GL_RENDERER));

	eglCreateImageKHR_ = (void *)eglGetProcAddress("eglCreateImageKHR");
	glEGLImageTargetTexture2DOES_ =
		(void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");

	{
		EGLint attr[] = {
			EGL_WIDTH, W,
			EGL_HEIGHT, H,
			EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_ARGB8888,
			EGL_DMA_BUF_PLANE0_FD_EXT, req.fd,
			EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
			EGL_DMA_BUF_PLANE0_PITCH_EXT, W * 4,
			EGL_NONE
		};

		img = eglCreateImageKHR_(dpy, EGL_NO_CONTEXT,
					 EGL_LINUX_DMA_BUF_EXT, NULL, attr);
		if (img == EGL_NO_IMAGE_KHR) {
			fprintf(stderr, "eglCreateImageKHR(ARGB8888) failed: 0x%x\n",
				eglGetError());
			return 1;
		}
		printf("EGLImage over the carveout: ok\n");
	}

	/* Bind as a normal 2D texture -- it is the FBO colour attachment. */
	glGenTextures(1, &tex);
	glBindTexture(GL_TEXTURE_2D, tex);
	glEGLImageTargetTexture2DOES_(GL_TEXTURE_2D, img);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	if (glGetError() != GL_NO_ERROR) {
		fprintf(stderr, "EGLImageTargetTexture2D failed\n");
		return 1;
	}

	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
			       GL_TEXTURE_2D, tex, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
		fprintf(stderr, "FBO over the carveout incomplete -- panfrost "
			"will not render into this buffer\n");
		return 1;
	}
	printf("carveout is a complete FBO: ok\n");

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

	glViewport(0, 0, W, H);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	glFinish();

	/*
	 * Independent verification: read the same physical memory through
	 * /dev/mem, not through GL. This is the whole point -- the bytes have
	 * to be where AFBD will fetch them.
	 */
	mfd = open("/dev/mem", O_RDWR | O_SYNC);
	if (mfd < 0) { perror("open /dev/mem"); return 1; }
	fb = mmap(NULL, (size_t)W * H * 4, PROT_READ | PROT_WRITE, MAP_SHARED,
		  mfd, FB_FRONT);
	if (fb == MAP_FAILED) { perror("mmap scanout"); return 1; }

	{
		/*
		 * Expected values are x/W*255 and y/H*255 -- computed, not
		 * eyeballed, and the tolerance is tight enough that a wrong
		 * expectation fails instead of passing on slack. The first
		 * revision of this test wanted g=56 at y=64 (arithmetic slip,
		 * the right answer is 23) and passed anyway on a +-40 window,
		 * which is exactly the kind of test this project distrusts.
		 * A rising gradient in BOTH axes also pins the orientation:
		 * if the image were flipped, y=64 would read ~232.
		 */
		struct { int x, y, r, g; } probe[] = {
			{   64,  64,  13,  23 },
			{  640, 360, 128, 128 },
			{ 1216, 656, 242, 232 },
		};

		for (i = 0; i < 3; i++) {
			uint32_t v = fb[(size_t)probe[i].y * W + probe[i].x];
			int r = (v >> 16) & 0xff, g = (v >> 8) & 0xff;
			int ok = abs(r - probe[i].r) <= 4 && abs(g - probe[i].g) <= 4;

			printf("  phys (%4d,%3d) = %08x  r=%3d g=%3d  want ~%d,%d  %s\n",
			       probe[i].x, probe[i].y, v, r, g,
			       probe[i].r, probe[i].g, ok ? "ok" : "BAD");
			if (!ok)
				bad++;
		}
	}

	t0 = now_ms();
	for (i = 0; i < 100; i++)
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	glFinish();
	printf("100 full-frame renders into the carveout: %.1f ms (%.2f ms/frame)\n",
	       now_ms() - t0, (now_ms() - t0) / 100.0);

	printf("%s\n", bad ? "FAIL: GPU output is not in the scanout region" :
	       "PASS: GPU rendered directly into the scanout carveout");
	return bad ? 1 : 0;
}
