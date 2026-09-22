/* SPDX-License-Identifier: GPL-2.0 */
/*
 * T1a and T1b (AP2d test plan), on any host with a GLES driver -- llvmpipe,
 * an Intel or AMD card, or panfrost on the device itself. Neither test needs
 * a dma-buf, a KMS node or h713-tv: both upload their source with
 * glTexImage2D and read the result back with glReadPixels, so what is under
 * test is the geometry and the colour arithmetic, not the import path (that
 * one is h713-gpu-probe's job and it ran on the device).
 *
 * T1a identity geometry, BYTE-EXACT. A known RGBA8 pattern as the source, all
 *     eight insets 0, the daemon's own vertex shader with the matrix that
 *     h713-warp/matrix.c computes for that case, nearest sampling: every
 *     output byte must equal the input byte. This tests the matrix, the
 *     viewport, the vertex order and the sampler addressing, and it has an
 *     exact contract -- AP2d T1 refuses to promise that for the YUV path.
 * T1b colour conversion, +-1 LSB. A fixed NV16 frame as two planes, the
 *     daemon's own fragment shader (BT.709 limited range, Cb in .r of the
 *     GR88 plane), against a CPU reference with the same coefficients. The
 *     tolerance is in the name so nobody widens it quietly.
 *
 * The daemon is an ES2 program; this driver asks for an ES3 context where it
 * can get one, because R8/RG8 textures are core there and the ES2 way round
 * it (GL_EXT_texture_rg) is not on every driver. The shaders are version 100
 * either way -- the very strings gl.c compiles.
 */
#define EGL_NO_X11
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>

#include "../h713-warp/warp.h"

#define TOL_LSB	1

static EGLDisplay dpy;
static int es3;

/* gl.c is linked for its shader strings and wants the journal of main.c */
void info(const char *fmt, ...) { (void)fmt; }
void warn(const char *fmt, ...) { (void)fmt; }
void fail(const char *fmt, ...) { (void)fmt; exit(1); }
void text_add(struct textbuf *t, const char *fmt, ...) { (void)t; (void)fmt; }
double now_s(void) { return 0.0; }

static const char *const FS_RGBA =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_s;\n"
	"void main() { gl_FragColor = texture2D(u_s, v_uv); }\n";

static int egl_up(void)
{
	static const EGLint attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE,
	};
	EGLint cattr[] = { EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE };
	EGLContext ctx = EGL_NO_CONTEXT;
	EGLConfig cfg;
	EGLint v[2], n = 0;

	dpy = eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA,
				    EGL_DEFAULT_DISPLAY, NULL);
	if (dpy == EGL_NO_DISPLAY || !eglInitialize(dpy, v, v + 1)) {
		printf("SKIP no EGL on this host (0x%x) -- T1a/T1b need a GLES driver\n",
		       eglGetError());
		return 1;
	}
	if (!eglBindAPI(EGL_OPENGL_ES_API) ||
	    !eglChooseConfig(dpy, attr, &cfg, 1, &n) || !n) {
		printf("SKIP no ES2 config (0x%x)\n", eglGetError());
		return 1;
	}
	es3 = 1;
	ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, cattr);
	if (ctx == EGL_NO_CONTEXT) {
		es3 = 0;
		cattr[1] = 2;
		ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, cattr);
	}
	if (ctx == EGL_NO_CONTEXT ||
	    !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
		printf("SKIP no context (0x%x)\n", eglGetError());
		return 1;
	}
	printf("     %s, %s\n", (const char *)glGetString(GL_RENDERER),
	       (const char *)glGetString(GL_VERSION));

	return 0;
}

static GLuint program(const char *fs)
{
	const char *src[2] = { gl_vertex_shader, fs };
	GLuint prog = glCreateProgram(), s;
	char log[512];
	GLint ok = 0;
	int i;

	for (i = 0; i < 2; i++) {
		s = glCreateShader(i ? GL_FRAGMENT_SHADER : GL_VERTEX_SHADER);
		glShaderSource(s, 1, &src[i], NULL);
		glCompileShader(s);
		glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
		if (!ok) {
			glGetShaderInfoLog(s, sizeof(log), NULL, log);
			printf("FAIL shader: %s\n", log);
			return 0;
		}
		glAttachShader(prog, s);
	}
	glBindAttribLocation(prog, 0, "a_pos");
	glBindAttribLocation(prog, 1, "a_uv");
	glLinkProgram(prog);
	glGetProgramiv(prog, GL_LINK_STATUS, &ok);

	return ok ? prog : 0;
}

static GLuint tex_new(GLint internal, GLenum format, int w, int h,
		      const void *data, int unit)
{
	GLuint t;

	glGenTextures(1, &t);
	glActiveTexture((GLenum)(GL_TEXTURE0 + unit));
	glBindTexture(GL_TEXTURE_2D, t);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glTexImage2D(GL_TEXTURE_2D, 0, internal, w, h, 0, format,
		     GL_UNSIGNED_BYTE, data);

	return t;
}

/* an RGBA render target of w x h, bound; the identity warp draws into it */
static GLuint fbo_new(int w, int h)
{
	GLuint fbo, t = tex_new(GL_RGBA, GL_RGBA, w, h, NULL, 3);

	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
			       GL_TEXTURE_2D, t, 0);

	return glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
		? fbo : 0;
}

/* the identity matrix of the warp itself -- not a hand-written one */
static void identity(float mf[16])
{
	static const int zero[WARP_KEYS] = { 0, 0, 0, 0, 0, 0, 0, 0 };
	double m[16];
	int i;

	if (!warp_matrix(zero, m)) {
		printf("FAIL warp_matrix refused the identity\n");
		exit(1);
	}
	for (i = 0; i < 16; i++)
		mf[i] = (float)m[i];
}

static void draw(GLuint prog, int w, int h)
{
	static const GLfloat quad[] = {
		-1, -1, 0, 0,   1, -1, 1, 0,   -1, 1, 0, 1,   1, 1, 1, 1,
	};
	float mf[16];

	identity(mf);
	glViewport(0, 0, w, h);
	glClearColor(0, 0, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glUseProgram(prog);
	glUniformMatrix4fv(glGetUniformLocation(prog, "u_k"), 1, GL_FALSE, mf);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, quad);
	glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, quad + 2);
	glEnableVertexAttribArray(0);
	glEnableVertexAttribArray(1);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
}

static int t1a(void)
{
	const int w = 256, h = 256;
	unsigned char *in = malloc((size_t)w * h * 4);
	unsigned char *out = malloc((size_t)w * h * 4);
	GLuint prog = program(FS_RGBA);
	long bad = 0;
	int x, y, i;

	for (y = 0; y < h; y++)
		for (x = 0; x < w; x++) {
			unsigned char *p = in + ((size_t)y * w + x) * 4;

			p[0] = (unsigned char)x;
			p[1] = (unsigned char)y;
			p[2] = (unsigned char)(x ^ y);
			p[3] = 255;
		}
	if (!prog || !fbo_new(w, h)) {
		printf("FAIL T1a: no program or no FBO\n");
		return 1;
	}
	tex_new(GL_RGBA, GL_RGBA, w, h, in, 0);
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, "u_s"), 0);
	draw(prog, w, h);
	glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, out);
	for (i = 0; i < w * h * 4; i++)
		bad += in[i] != out[i];
	printf("%s T1a identity geometry byte-exact: %ld of %d bytes differ\n",
	       bad ? "FAIL" : "ok", bad, w * h * 4);
	free(in);
	free(out);

	return bad != 0;
}

/* what the fragment shader must produce for one Y/Cb/Cr triple, 0..255 */
static void bt709(const int *yuv, int *out)
{
	double l = 1.1643835 * (yuv[0] - 16), a = yuv[1] - 128, b = yuv[2] - 128;
	double v[3];
	int i;

	v[0] = l + 1.7927411 * b;
	v[1] = l - 0.2132486 * a - 0.5329093 * b;
	v[2] = l + 2.1124018 * a;
	for (i = 0; i < 3; i++)
		out[i] = v[i] < 0 ? 0 : v[i] > 255 ? 255 : (int)(v[i] + 0.5);
}

static int t1b(void)
{
	const int w = 64, h = 64;
	unsigned char *luma = malloc((size_t)w * h);
	unsigned char *chroma = malloc((size_t)w * h);	/* w/2 * 2 bytes * h */
	unsigned char *out = malloc((size_t)w * h * 4);
	GLuint prog = program(gl_fragment_shader);
	int worst = 0, x, y, i;
	long bad = 0;

	if (!es3) {
		printf("SKIP T1b: this driver gave only an ES2 context, and R8/RG8 "
		       "textures without a dma-buf need ES3 or GL_EXT_texture_rg\n");
		return 0;
	}
	for (y = 0; y < h; y++)
		for (x = 0; x < w; x++)
			luma[(size_t)y * w + x] = (unsigned char)(16 + (x * 3 + y * 2) % 220);
	for (y = 0; y < h; y++)
		for (x = 0; x < w / 2; x++) {
			chroma[((size_t)y * (w / 2) + x) * 2] =
				(unsigned char)(16 + (x * 7) % 220);	/* Cb */
			chroma[((size_t)y * (w / 2) + x) * 2 + 1] =
				(unsigned char)(16 + (y * 5) % 220);	/* Cr */
		}
	if (!prog || !fbo_new(w, h)) {
		printf("FAIL T1b: no program or no FBO\n");
		return 1;
	}
	tex_new(GL_R8_EXT, GL_RED_EXT, w, h, luma, 0);
	tex_new(GL_RG8_EXT, GL_RG_EXT, w / 2, h, chroma, 1);
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, "u_y"), 0);
	glUniform1i(glGetUniformLocation(prog, "u_c"), 1);
	draw(prog, w, h);
	glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, out);
	for (y = 0; y < h; y++)
		for (x = 0; x < w; x++) {
			const unsigned char *p = out + ((size_t)y * w + x) * 4;
			int yuv[3], want[3];

			yuv[0] = luma[(size_t)y * w + x];
			yuv[1] = chroma[((size_t)y * (w / 2) + x / 2) * 2];
			yuv[2] = chroma[((size_t)y * (w / 2) + x / 2) * 2 + 1];
			bt709(yuv, want);
			for (i = 0; i < 3; i++) {
				int d = abs((int)p[i] - want[i]);

				if (d > worst)
					worst = d;
				bad += d > TOL_LSB;
			}
		}
	printf("%s T1b NV16 to RGB within %d LSB: %ld of %d samples outside, worst %d\n",
	       bad ? "FAIL" : "ok", TOL_LSB, bad, w * h * 3, worst);
	free(luma);
	free(chroma);
	free(out);

	return bad != 0;
}

int main(void)
{
	int rc;

	if (egl_up())
		return 77;		/* the automake convention for "skipped" */
	rc = t1a();
	rc |= t1b();

	return rc;
}
