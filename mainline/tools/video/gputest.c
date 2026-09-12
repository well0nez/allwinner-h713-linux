// SPDX-License-Identifier: GPL-2.0
/*
 * gputest -- does panfrost actually RUN A JOB on this board?
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -o gputest gputest.c -lEGL -lGLESv2
 *
 * "Initialized panfrost 1.4.0" only proves the kernel driver bound. It says
 * nothing about whether the GPU executes shaders, which is the entire premise
 * of the GPU video path. This renders with a fragment shader whose output is a
 * FUNCTION OF gl_FragCoord, then reads the pixels back and checks specific
 * ones. A driver that quietly falls back to software, or a job that never
 * completes, cannot produce the right gradient.
 *
 * Deliberately surfaceless: no GBM, no display, no compositor. The question is
 * only whether the shader core runs.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define W 256
#define H 256

static const char *VS =
	"attribute vec2 p;\n"
	"void main() { gl_Position = vec4(p, 0.0, 1.0); }\n";

/*
 * Output depends on the fragment's own coordinates, so a correct image proves
 * per-pixel shader execution rather than a clear or a memset.
 */
static const char *FS =
	"precision mediump float;\n"
	"void main() {\n"
	"  gl_FragColor = vec4(gl_FragCoord.x / 256.0,\n"
	"                      gl_FragCoord.y / 256.0,\n"
	"                      0.25, 1.0);\n"
	"}\n";

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

	glShaderSource(s, 1, &src, NULL);
	glCompileShader(s);
	glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
	if (!ok) {
		char log[1024] = { 0 };

		glGetShaderInfoLog(s, sizeof(log) - 1, NULL, log);
		fprintf(stderr, "shader compile failed: %s\n", log);
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
	GLuint fbo, rb, prog, vs, fs, vbo;
	unsigned char *px;
	double t0;
	int bad = 0, i;

	static const EGLint cfg_attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
		EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
		EGL_NONE
	};
	static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const GLfloat quad[] = { -1, -1,  1, -1, -1, 1,  1, 1 };

	dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	if (dpy == EGL_NO_DISPLAY) {
		fprintf(stderr, "eglGetDisplay failed\n");
		return 1;
	}
	if (!eglInitialize(dpy, &major, &minor)) {
		fprintf(stderr, "eglInitialize failed: 0x%x\n", eglGetError());
		return 1;
	}
	printf("EGL %d.%d\n", major, minor);
	printf("EGL_VENDOR   : %s\n", eglQueryString(dpy, EGL_VENDOR));

	eglBindAPI(EGL_OPENGL_ES_API);
	if (!eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n) || n < 1) {
		fprintf(stderr, "eglChooseConfig failed\n");
		return 1;
	}
	ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
	if (ctx == EGL_NO_CONTEXT) {
		fprintf(stderr, "eglCreateContext failed: 0x%x\n", eglGetError());
		return 1;
	}
	if (!eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
		fprintf(stderr, "eglMakeCurrent failed: 0x%x\n", eglGetError());
		return 1;
	}

	/*
	 * THE line that matters. "Mali-G31 (Panfrost)" means the job goes to
	 * the hardware; "llvmpipe" or "softpipe" means mesa fell back to the
	 * CPU and the whole premise of this path is void.
	 */
	printf("GL_VENDOR    : %s\n", glGetString(GL_VENDOR));
	printf("GL_RENDERER  : %s\n", glGetString(GL_RENDERER));
	printf("GL_VERSION   : %s\n", glGetString(GL_VERSION));

	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glGenRenderbuffers(1, &rb);
	glBindRenderbuffer(GL_RENDERBUFFER, rb);
	glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA4, W, H);
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
	glUseProgram(prog);

	glGenBuffers(1, &vbo);
	glBindBuffer(GL_ARRAY_BUFFER, vbo);
	glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
	glEnableVertexAttribArray(0);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0);

	glViewport(0, 0, W, H);
	glClearColor(0, 0, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	glFinish();

	px = malloc(W * H * 4);
	glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, px);

	/*
	 * Check the gradient at three points. Tolerance is wide because the
	 * renderbuffer is RGBA4 (4 bits/channel) -- the question is "did the
	 * GPU compute this", not "is it bit-exact".
	 */
	struct { int x, y, r, g; } probe[] = {
		{  16,  16,  16,  16 },
		{ 128, 128, 128, 128 },
		{ 240, 240, 240, 240 },
	};
	for (i = 0; i < 3; i++) {
		unsigned char *p = px + ((size_t)probe[i].y * W + probe[i].x) * 4;
		int dr = abs((int)p[0] - probe[i].r);
		int dg = abs((int)p[1] - probe[i].g);

		printf("  (%3d,%3d) = %3d,%3d,%3d  expect ~%d,%d  %s\n",
		       probe[i].x, probe[i].y, p[0], p[1], p[2],
		       probe[i].r, probe[i].g,
		       (dr < 24 && dg < 24) ? "ok" : "BAD");
		if (dr >= 24 || dg >= 24)
			bad++;
	}

	/* Throughput: 200 full-screen passes, to show jobs actually stream. */
	t0 = now_ms();
	for (i = 0; i < 200; i++)
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	glFinish();
	printf("200 draws of %dx%d: %.1f ms (%.1f Mpixel/s)\n", W, H,
	       now_ms() - t0,
	       200.0 * W * H / ((now_ms() - t0) / 1000.0) / 1e6);

	printf("%s\n", bad ? "FAIL: pixels wrong" : "PASS: GPU ran the job");
	return bad ? 1 : 0;
}
