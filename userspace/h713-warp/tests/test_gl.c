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
 * T1c projection modes, BYTE-EXACT (FB-MIRROR). T1a's pattern through the
 *     identity keystone mirrored by warp_mirror() for rear, ceiling and
 *     rear-ceiling: every output pixel must equal the source pixel mirrored
 *     left-right, both ways, or top-bottom. Pixel centres sit at half
 *     integers, so a sign change in NDC is an exact column or row reversal
 *     and nothing is resampled.
 *
 * T1c the soft border's arithmetic, no GL. The vendor's mask (draw_edge @
 *     0x3C64 in libkeystone: a ring of 255 - 20 around zeros, GL_LINEAR,
 *     CLAMP_TO_EDGE) sampled bilinearly on the CPU must equal the closed form
 *     the luma and chroma shaders compute, 1 - (1 - r.x)(1 - r.y), at every
 *     fragment centre of a 1920x1080 panel, and gl_edge_mask must round the
 *     way the vendor does. A wrong closed form (max instead of the OR) is the
 *     negative control: it has to differ.
 * T1d the soft border drawn, +-1 LSB. A flat luma source through the identity
 *     with the daemon's luma shader and a 4 px edge: every pixel against the
 *     CPU reference of T1c; then the edge off, byte-exact.
 *
 * The daemon is an ES2 program; this driver asks for an ES3 context where it
 * can get one, because R8/RG8 textures are core there and the ES2 way round
 * it (GL_EXT_texture_rg) is not on every driver. The shaders are version 100
 * either way -- the very strings gl.c compiles.
 */
#define EGL_NO_X11
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>

#include "../warp.h"

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

/* the identity matrix of the warp itself -- not a hand-written one -- and,
 * for T1c, the same mirrored by the daemon's own warp_mirror() */
static void identity(float mf[16], int mode)
{
	static const int zero[WARP_KEYS] = { 0, 0, 0, 0, 0, 0, 0, 0 };
	double m[16];
	int i;

	if (!warp_matrix(zero, m)) {
		printf("FAIL warp_matrix refused the identity\n");
		exit(1);
	}
	warp_mirror(mode, m);
	for (i = 0; i < 16; i++)
		mf[i] = (float)m[i];
}

static void draw(GLuint prog, int w, int h, int mode)
{
	static const GLfloat quad[] = {
		-1, -1, 0, 0,   1, -1, 1, 0,   -1, 1, 0, 1,   1, 1, 1, 1,
	};
	float mf[16];

	identity(mf, mode);
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
	int x, y, i, mode;

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
	draw(prog, w, h, MODE_FRONT);
	glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, out);
	for (i = 0; i < w * h * 4; i++)
		bad += in[i] != out[i];
	printf("%s T1a identity geometry byte-exact: %ld of %d bytes differ\n",
	       bad ? "FAIL" : "ok", bad, w * h * 4);
	/* T1c: the three mirrored modes, same source, same program */
	for (mode = MODE_REAR; mode <= MODE_REAR_CEILING; mode++) {
		int fx = mode != MODE_REAR_CEILING, fy = mode != MODE_REAR;
		long wrong = 0;

		draw(prog, w, h, mode);
		glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, out);
		for (y = 0; y < h; y++)
			for (x = 0; x < w; x++) {
				const unsigned char *o = out + ((size_t)y * w + x) * 4;
				const unsigned char *s = in + ((size_t)(fy ? h - 1 - y : y) * w +
							       (fx ? w - 1 - x : x)) * 4;

				wrong += memcmp(o, s, 4) != 0;
			}
		printf("%s T1c %s mirrored byte-exact: %ld of %d pixels differ from the source %s\n",
		       wrong ? "FAIL" : "ok", warp_mode_name[mode], wrong, w * h,
		       fx && fy ? "turned over" : fx ? "mirrored left-right" : "mirrored top-bottom");
		bad += wrong;
	}
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
	draw(prog, w, h, MODE_FRONT);
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

/* the vendor's mask texel: 255 - 20 on the outermost ring, 0 inside, as 0..1 */
static double mask_texel(int i, int j, int w, int h)
{
	return i == 0 || i == w - 1 || j == 0 || j == h - 1 ? 235.0 / 255.0 : 0.0;
}

/* that mask sampled GL_LINEAR with CLAMP_TO_EDGE at (u, v) in 0..1 */
static double mask_bilinear(int w, int h, double u, double v)
{
	double x = u * w - 0.5, y = v * h - 0.5, fx, fy;
	int x0 = (int)floor(x), y0 = (int)floor(y), x1, y1;

	fx = x - x0;
	fy = y - y0;
	x1 = x0 + 1 > w - 1 ? w - 1 : x0 + 1;
	y1 = y0 + 1 > h - 1 ? h - 1 : y0 + 1;
	x0 = x0 < 0 ? 0 : x0;
	y0 = y0 < 0 ? 0 : y0;

	return (1 - fx) * (1 - fy) * mask_texel(x0, y0, w, h) + fx * (1 - fy) * mask_texel(x1, y0, w, h) +
	       (1 - fx) * fy * mask_texel(x0, y1, w, h) + fx * fy * mask_texel(x1, y1, w, h);
}

static double ramp(double e, int n)
{
	double r = 1.5 - e * n;

	return r < 0 ? 0 : r > 1 ? 1 : r;
}

/* the alpha the shaders' closed form gives (gl.c EDGE_GLSL); wrong = the negative control */
static double edge_alpha(int w, int h, double u, double v, int wrong)
{
	double ru = ramp(u < 1 - u ? u : 1 - u, w), rv = ramp(v < 1 - v ? v : 1 - v, h);

	return 235.0 / 255.0 * (wrong ? (ru > rv ? ru : rv) : 1 - (1 - ru) * (1 - rv));
}

static int t1c(void)
{
	static const struct { unsigned int w, h; int px, mw, mh; } sizes[] = {
		{ 1920, 1080, 4, 480, 272 }, { 1366, 768, 4, 352, 192 },
		{ 1920, 1080, 3, 640, 368 }, { 1920, 1080, 0, 0, 0 },
	};
	double worst = 0, worst_wrong = 0;
	int e[2], bad = 0, x, y;
	size_t i;

	for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
		gl_edge_mask(sizes[i].w, sizes[i].h, sizes[i].px, e);
		if (e[0] != sizes[i].mw || e[1] != sizes[i].mh) {
			printf("FAIL T1c mask of %ux%u at %d px: %dx%d, want %dx%d\n", sizes[i].w,
			       sizes[i].h, sizes[i].px, e[0], e[1], sizes[i].mw, sizes[i].mh);
			bad++;
		}
	}
	gl_edge_mask(1920, 1080, 4, e);
	for (y = 0; y < 1080; y++)
		for (x = 0; x < 1920; x++) {
			double u = (x + 0.5) / 1920.0, v = (y + 0.5) / 1080.0;
			double ref = mask_bilinear(e[0], e[1], u, v);
			double d = fabs(edge_alpha(e[0], e[1], u, v, 0) - ref);
			double dw = fabs(edge_alpha(e[0], e[1], u, v, 1) - ref);

			if (d > worst)
				worst = d;
			if (dw > worst_wrong)
				worst_wrong = dw;
		}
	bad += worst > 1e-9 || worst_wrong < 0.1;
	printf("%s T1c edge closed form = the vendor's mask sampled bilinearly: worst %.2e (negative control differs by %.3f)\n",
	       bad ? "FAIL" : "ok", worst, worst_wrong);

	return bad != 0;
}

static int t1d(void)
{
	const int w = 256, h = 256, px = 4, luma = 200;
	unsigned char *in = malloc((size_t)w * h);
	unsigned char *out = malloc((size_t)w * h * 4);
	GLuint prog = program(gl_luma_shader);
	int e[2], worst = 0, x, y, first, fifth;
	long bad = 0, bad_off = 0;

	memset(in, luma, (size_t)w * h);
	if (!prog || !fbo_new(w, h)) {
		printf("FAIL T1d: no program or no FBO\n");
		return 1;
	}
	tex_new(GL_LUMINANCE, GL_LUMINANCE, w, h, in, 0);
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, "u_y"), 0);
	gl_edge_mask((unsigned int)w, (unsigned int)h, px, e);
	glUniform2f(glGetUniformLocation(prog, "u_edge"), (float)e[0], (float)e[1]);
	draw(prog, w, h, MODE_FRONT);
	glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, out);
	for (y = 0; y < h; y++)
		for (x = 0; x < w; x++) {
			double a = edge_alpha(e[0], e[1], (x + 0.5) / w, (y + 0.5) / h, 0);
			int want = (int)(16 + (luma - 16) * (1 - a) + 0.5);
			int d = abs((int)out[((size_t)y * w + x) * 4] - want);

			if (d > worst)
				worst = d;
			bad += d > TOL_LSB;
		}
	/* the shape in numbers: the outermost pixel keeps 20/255 of the
	 * picture (16 + 184 * 20 / 255 = 30), the second still (half a texel),
	 * then the ramp over one texel of 4 px; the seventh is the picture */
	first = out[((size_t)(h / 2) * w) * 4];
	fifth = out[((size_t)(h / 2) * w + 6) * 4];
	printf("%s T1d edge ramp within %d LSB: %ld of %d pixels outside, worst %d (edge pixel %d, seventh %d)\n",
	       bad ? "FAIL" : "ok", TOL_LSB, bad, w * h, worst, first, fifth);
	glUniform2f(glGetUniformLocation(prog, "u_edge"), 0.0f, 0.0f);
	draw(prog, w, h, MODE_FRONT);
	glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, out);
	for (y = 0; y < h; y++)
		for (x = 0; x < w; x++)
			bad_off += out[((size_t)y * w + x) * 4] != luma;
	printf("%s T1d edge off byte-exact: %ld of %d pixels differ\n",
	       bad_off ? "FAIL" : "ok", bad_off, w * h);
	free(in);
	free(out);

	return bad != 0 || bad_off != 0;
}

int main(void)
{
	int rc = t1c();

	if (egl_up())
		return rc ? 1 : 77;	/* the automake convention for "skipped" */
	rc |= t1a();
	rc |= t1b();
	rc |= t1d();

	return rc;
}
