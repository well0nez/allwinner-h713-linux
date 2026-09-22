/* SPDX-License-Identifier: GPL-2.0 */
/*
 * EGL and GLES2 on the render node (design AP2d M6 and M8). Everything here
 * is the working code of umbau/src/userspace/h713-gpu-probe/scanout.c, which
 * ran on the device: the dma-buf import of the XRGB8888 targets and of the
 * capture's R8 + GR88 planes, the BT.709 limited-range shader, the native
 * fence. Two things are different on purpose: no GBM and no libdrm (scanout.c
 * took the render node through gbm_create_device() because it also held a KMS
 * node; here the node comes from EGL_EXT_platform_device, or from
 * EGL_PLATFORM_SURFACELESS_MESA where that extension is absent), and the
 * vertex stage carries the keystone matrix with the quad at z = -1 (AP2f 6b).
 * The pitch does NOT reach the shader: EGL takes it in
 * EGL_DMA_BUF_PLANE0_PITCH_EXT, so a 1366-wide source in 1376-byte lines is
 * still a 1366-wide image and nothing is divided by anything (KS3 measured
 * that; design M5 feared otherwise).
 */
#define EGL_NO_X11
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <drm_fourcc.h>

#include "warp.h"

const char *const gl_vertex_shader =
	"attribute vec2 a_pos; attribute vec2 a_uv; varying vec2 v_uv;\n"
	"uniform mat4 u_k;\n"
	/* z = -1: the vendor's translate(1,1,1) puts z_clip at 0, where no
	 * division by w can push it out of the clip volume (AP2f 6b)
	 */
	"void main() { gl_Position = u_k * vec4(a_pos, -1.0, 1.0); v_uv = a_uv; }\n";

/* M8: two planes, BT.709 limited range. GR88 is "[15:0] G:R 8:8 little
 * endian", so the first chroma byte, Cb, lands in .r (scanout.c). The two
 * offsets are 16/255 and 128/255 and NOT scanout.c's 0.0625 and 0.5, which
 * are 16/256 and 128/256: that shortcut is worth up to 1.1 LSB in blue and
 * made T1b fail at its stated +-1 (measured, host test 22.09.2026).
 * h713-gpu-probe checked its own samples "within 2" and never saw it.
 */
const char *const gl_fragment_shader =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y, u_c;\n"
	"void main() { float y = 1.1643835 * (texture2D(u_y, v_uv).r - 0.0627451);\n"
	"  vec2 c = texture2D(u_c, v_uv).rg - 0.5019608;\n"
	"  gl_FragColor = vec4(y + 1.7927411 * c.y, y - 0.2132486 * c.x - 0.5329093 * c.y,\n"
	"                      y + 2.1124018 * c.x, 1.0); }\n";

/* grid and border as before; the MASK is the calibration picture of the
 * manual keystone, drawn in our own style after the vendor's: a grey field, a
 * white rounded frame, a large circle with a crosshair and a dark centre dot,
 * and the corner being edited marked with a ring. Coordinates are in units of
 * the panel height (u_aspect = width / height), so circles are round. */
const char *const gl_pattern_shader =
	"precision highp float; varying vec2 v_uv;\n"
	"uniform float u_grid, u_mask, u_aspect; uniform int u_corner;\n"
	"float ring(vec2 p, vec2 c, float r, float w) { return 1.0 - step(w, abs(length(p - c) - r)); }\n"
	"void main() {\n"
	"  vec2 e = min(v_uv, 1.0 - v_uv);\n"
	"  if (u_mask < 0.5) {\n"
	"    float border = 1.0 - step(0.004, min(e.x, e.y));\n"
	"    vec2 g = abs(fract(v_uv * vec2(16.0, 9.0)) - 0.5);\n"
	"    float grid = u_grid * step(0.47, max(g.x, g.y));\n"
	"    float mark = 1.0 - step(0.06, max(e.x, e.y));\n"
	"    gl_FragColor = vec4(vec3(max(border, max(grid, mark * 0.5))), 1.0); return; }\n"
	"  vec2 p = vec2(v_uv.x * u_aspect, v_uv.y);\n"
	"  vec2 c = vec2(0.5 * u_aspect, 0.5);\n"
	"  vec2 ep = vec2(min(p.x, u_aspect - p.x), min(p.y, 1.0 - p.y));\n"
	"  float col = 0.5;\n"
	"  float frame = 1.0 - step(0.004, abs(min(ep.x, ep.y) - 0.06));\n"
	"  float cross = max(1.0 - step(0.0015, abs(p.x - c.x)), 1.0 - step(0.0015, abs(p.y - c.y)));\n"
	"  cross *= step(0.06, min(ep.x, ep.y));\n"
	"  float circle = ring(p, c, 0.42, 0.003);\n"
	"  float dot = 1.0 - step(0.13, length(p - c));\n"
	"  col = mix(col, 0.85, max(frame, max(cross, circle)));\n"
	"  col = mix(col, 0.25, dot);\n"
	"  if (u_corner >= 0) {\n"
	"    vec2 k = vec2(u_corner == 1 || u_corner == 3 ? u_aspect - 0.14 : 0.14,\n"
	"                  u_corner >= 2 ? 1.0 - 0.14 : 0.14);\n"
	"    float mk = max(ring(p, k, 0.045, 0.006), 1.0 - step(0.014, length(p - k)));\n"
	"    col = mix(col, 1.0, mk); }\n"
	"  gl_FragColor = vec4(vec3(col), 1.0); }\n";

static const char *const NEED[] = {
	"EGL_EXT_image_dma_buf_import", "EGL_KHR_surfaceless_context",
	"EGL_ANDROID_native_fence_sync", "GL_OES_EGL_image",
};

static PFNEGLCREATEIMAGEKHRPROC p_img_new;
static PFNEGLDESTROYIMAGEKHRPROC p_img_del;
static PFNEGLCREATESYNCKHRPROC p_sync_new;
static PFNEGLDESTROYSYNCKHRPROC p_sync_del;
static PFNEGLDUPNATIVEFENCEFDANDROIDPROC p_sync_fd;
static PFNGLEGLIMAGETARGETRENDERBUFFERSTORAGEOESPROC p_img_rb;
static PFNGLEGLIMAGETARGETTEXTURE2DOESPROC p_img_tex;

static EGLDisplay dpy = EGL_NO_DISPLAY;
static EGLContext ctx = EGL_NO_CONTEXT;
static char renderer[128] = "not opened";
static GLuint prog_warp, prog_pattern;
static unsigned int panel_w, panel_h;

/* Text over the mask: a 5x7 font for the digits, the lowercase letters and
 * ". / : - %", built into a luminance texture once, drawn as one quad per
 * glyph with the identity matrix, so the numbers stay upright and readable
 * whatever the warp does to the picture. Each glyph is seven rows of five
 * bits, MSB left. */
static const unsigned char FONT_ROWS[][7] = {
	/* 0..9 */
	{0x0e,0x11,0x13,0x15,0x19,0x11,0x0e}, {0x04,0x0c,0x04,0x04,0x04,0x04,0x0e},
	{0x0e,0x11,0x01,0x02,0x04,0x08,0x1f}, {0x1f,0x02,0x04,0x02,0x01,0x11,0x0e},
	{0x02,0x06,0x0a,0x12,0x1f,0x02,0x02}, {0x1f,0x10,0x1e,0x01,0x01,0x11,0x0e},
	{0x06,0x08,0x10,0x1e,0x11,0x11,0x0e}, {0x1f,0x01,0x02,0x04,0x08,0x08,0x08},
	{0x0e,0x11,0x11,0x0e,0x11,0x11,0x0e}, {0x0e,0x11,0x11,0x0f,0x01,0x02,0x0c},
	/* a..z */
	{0x00,0x00,0x0e,0x01,0x0f,0x11,0x0f}, {0x10,0x10,0x16,0x19,0x11,0x11,0x1e},
	{0x00,0x00,0x0e,0x10,0x10,0x11,0x0e}, {0x01,0x01,0x0d,0x13,0x11,0x11,0x0f},
	{0x00,0x00,0x0e,0x11,0x1f,0x10,0x0e}, {0x06,0x09,0x08,0x1c,0x08,0x08,0x08},
	{0x00,0x0f,0x11,0x11,0x0f,0x01,0x0e}, {0x10,0x10,0x16,0x19,0x11,0x11,0x11},
	{0x04,0x00,0x0c,0x04,0x04,0x04,0x0e}, {0x02,0x00,0x06,0x02,0x02,0x12,0x0c},
	{0x10,0x10,0x12,0x14,0x18,0x14,0x12}, {0x0c,0x04,0x04,0x04,0x04,0x04,0x0e},
	{0x00,0x00,0x1a,0x15,0x15,0x11,0x11}, {0x00,0x00,0x16,0x19,0x11,0x11,0x11},
	{0x00,0x00,0x0e,0x11,0x11,0x11,0x0e}, {0x00,0x00,0x1e,0x11,0x1e,0x10,0x10},
	{0x00,0x00,0x0f,0x11,0x0f,0x01,0x01}, {0x00,0x00,0x16,0x19,0x10,0x10,0x10},
	{0x00,0x00,0x0e,0x10,0x0e,0x01,0x1e}, {0x08,0x08,0x1c,0x08,0x08,0x09,0x06},
	{0x00,0x00,0x11,0x11,0x11,0x13,0x0d}, {0x00,0x00,0x11,0x11,0x11,0x0a,0x04},
	{0x00,0x00,0x11,0x11,0x15,0x15,0x0a}, {0x00,0x00,0x11,0x0a,0x04,0x0a,0x11},
	{0x00,0x00,0x11,0x11,0x0f,0x01,0x0e}, {0x00,0x00,0x1f,0x02,0x04,0x08,0x1f},
	/* space . / : - % */
	{0,0,0,0,0,0,0}, {0x00,0x00,0x00,0x00,0x00,0x0c,0x0c},
	{0x01,0x01,0x02,0x04,0x08,0x10,0x10}, {0x00,0x0c,0x0c,0x00,0x0c,0x0c,0x00},
	{0x00,0x00,0x00,0x1f,0x00,0x00,0x00}, {0x18,0x19,0x02,0x04,0x08,0x13,0x03},
};
#define FONT_GLYPHS	((int)(sizeof(FONT_ROWS) / sizeof(FONT_ROWS[0])))
#define FONT_CELL	8	/* texels per glyph in the atlas, 5 used + 3 gap */

static int glyph_index(char ch)
{
	if (ch >= '0' && ch <= '9')
		return ch - '0';
	if (ch >= 'a' && ch <= 'z')
		return 10 + ch - 'a';
	switch (ch) {
	case '.': return 37;
	case '/': return 38;
	case ':': return 39;
	case '-': return 40;
	case '%': return 41;
	default: return 36;	/* space, and anything the font lacks */
	}
}

const char *const gl_text_shader =
	"precision mediump float; varying vec2 v_uv; uniform sampler2D u_font;\n"
	"void main() { float a = texture2D(u_font, v_uv).r;\n"
	"  gl_FragColor = vec4(vec3(1.0), 1.0) * a; }\n";

static GLuint prog_text, font_tex;

static void font_build(void)
{
	unsigned char *px = calloc((size_t)FONT_GLYPHS * FONT_CELL * FONT_CELL, 1);
	int g, row, bit;

	if (!px)
		return;
	for (g = 0; g < FONT_GLYPHS; g++)
		for (row = 0; row < 7; row++)
			for (bit = 0; bit < 5; bit++)
				if (FONT_ROWS[g][row] & (0x10 >> bit))
					px[row * FONT_GLYPHS * FONT_CELL + g * FONT_CELL + bit] = 255;
	glGenTextures(1, &font_tex);
	glBindTexture(GL_TEXTURE_2D, font_tex);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_LUMINANCE, FONT_GLYPHS * FONT_CELL, FONT_CELL, 0,
		     GL_LUMINANCE, GL_UNSIGNED_BYTE, px);
	free(px);
}

/* One string at (x, y) in NDC, glyphs `h` panel pixels high, upright, blended */
static void text_draw(const char *s, float x, float y, float h)
{
	static const float ident[16] = { 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1 };
	float gw = h * 6.0f / 7.0f * 2.0f / (float)panel_w;	/* advance in NDC */
	float gh = h * 2.0f / (float)panel_h;
	float cw = h * 8.0f / 7.0f * 2.0f / (float)panel_w;	/* the 8-texel cell */

	glUseProgram(prog_text);
	glUniformMatrix4fv(glGetUniformLocation(prog_text, "u_k"), 1, GL_FALSE, ident);
	glUniform1i(glGetUniformLocation(prog_text, "u_font"), 0);
	glActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D, font_tex);
	glEnable(GL_BLEND);
	glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
	for (; *s; s++, x += gw) {
		float u0 = (float)glyph_index(*s) / (float)FONT_GLYPHS, u1 = u0 + 1.0f / (float)FONT_GLYPHS;
		/* NDC y = -1 is the TOP of the panel here (the warp's convention),
		 * so the glyph's top row (atlas v = 0) sits at y and its bottom
		 * (v = 1) at y + gh */
		float q[16] = { x, y + gh, u0, 1,   x + cw, y + gh, u1, 1,
				x, y, u0, 0,   x + cw, y, u1, 0 };

		glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, q);
		glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, q + 2);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	}
	glDisable(GL_BLEND);
}


static struct {
	EGLImageKHR img;
	GLuint rb, fbo;
} target[WARP_TARGETS];

static struct {
	EGLImageKHR img[2];
	GLuint tex[2];
} slot[WARP_SLOTS];
static int slots_up;

static bool oops(char *why, size_t n, const char *what)
{
	snprintf(why, n, "%s: egl 0x%x gl 0x%x", what, eglGetError(),
		 ctx == EGL_NO_CONTEXT ? 0 : glGetError());

	return false;
}

static bool has_ext(const char *list, const char *name)
{
	size_t k = strlen(name);

	for (; list && (list = strstr(list, name)); list += k)
		if (list[k] == ' ' || !list[k])
			return true;

	return false;
}

static EGLDisplay display_for(const char *node)
{
	PFNEGLQUERYDEVICESEXTPROC query;
	PFNEGLQUERYDEVICESTRINGEXTPROC string;
	EGLDeviceEXT dev[8];
	EGLint i, n = 0;
	const char *client = eglQueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS);

	query = (PFNEGLQUERYDEVICESEXTPROC)eglGetProcAddress("eglQueryDevicesEXT");
	string = (PFNEGLQUERYDEVICESTRINGEXTPROC)eglGetProcAddress("eglQueryDeviceStringEXT");
	if (!has_ext(client, "EGL_EXT_platform_device") || !query || !string ||
	    !query(8, dev, &n))
		n = 0;
	for (i = 0; i < n; i++) {
		const char *path = string(dev[i], EGL_DRM_RENDER_NODE_FILE_EXT);

		if (path && !strcmp(path, node))
			return eglGetPlatformDisplay(EGL_PLATFORM_DEVICE_EXT,
						     dev[i], NULL);
	}
	info("gl              %s was not offered as an EGL device -- surfaceless, Mesa picks the node",
	     node);

	return eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA,
				     EGL_DEFAULT_DISPLAY, NULL);
}

static GLuint program(const char *fs, char *why, size_t n)
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
			snprintf(why, n, "%s shader: %s", i ? "fragment" : "vertex", log);
			return 0;
		}
		glAttachShader(prog, s);
		glDeleteShader(s);
	}
	glBindAttribLocation(prog, 0, "a_pos");
	glBindAttribLocation(prog, 1, "a_uv");
	glLinkProgram(prog);
	glGetProgramiv(prog, GL_LINK_STATUS, &ok);
	if (!ok) {
		glGetProgramInfoLog(prog, sizeof(log), NULL, log);
		snprintf(why, n, "program link: %s", log);
		return 0;
	}

	return prog;
}

int gl_open(const char *node, char *why, size_t n)
{
	static const EGLint cattr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
	static const EGLint attr[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE,
	};
	const char *el, *gl;
	EGLConfig cfg;
	EGLint v[2], num = 0;
	int i;

	dpy = display_for(node);
	if (dpy == EGL_NO_DISPLAY || !eglInitialize(dpy, v, v + 1)) {
		oops(why, n, "eglInitialize");
		return 1;
	}
	el = eglQueryString(dpy, EGL_EXTENSIONS);
	if (!eglBindAPI(EGL_OPENGL_ES_API) ||
	    !eglChooseConfig(dpy, attr, &cfg, 1, &num) || !num ||
	    (ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, cattr)) == EGL_NO_CONTEXT ||
	    !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
		oops(why, n, "surfaceless ES2 context");
		return 1;
	}
	gl = (const char *)glGetString(GL_EXTENSIONS);
	snprintf(renderer, sizeof(renderer), "%s",
		 (const char *)glGetString(GL_RENDERER));
	for (i = 0; i < 4; i++)
		if (!has_ext(i < 3 ? el : gl, NEED[i])) {
			snprintf(why, n, "the render node has no %s (design M6)", NEED[i]);
			return 1;
		}
	p_img_new = (PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
	p_img_del = (PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
	p_sync_new = (PFNEGLCREATESYNCKHRPROC)eglGetProcAddress("eglCreateSyncKHR");
	p_sync_del = (PFNEGLDESTROYSYNCKHRPROC)eglGetProcAddress("eglDestroySyncKHR");
	p_sync_fd = (PFNEGLDUPNATIVEFENCEFDANDROIDPROC)eglGetProcAddress("eglDupNativeFenceFDANDROID");
	p_img_rb = (PFNGLEGLIMAGETARGETRENDERBUFFERSTORAGEOESPROC)
		eglGetProcAddress("glEGLImageTargetRenderbufferStorageOES");
	p_img_tex = (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)
		eglGetProcAddress("glEGLImageTargetTexture2DOES");
	if (!p_img_new || !p_img_del || !p_sync_new || !p_sync_fd || !p_img_rb ||
	    !p_img_tex) {
		snprintf(why, n, "the EGL/GLES entry points of design M6 are not all there");
		return 1;
	}
	prog_warp = program(gl_fragment_shader, why, n);
	prog_pattern = prog_warp ? program(gl_pattern_shader, why, n) : 0;
	prog_text = prog_pattern ? program(gl_text_shader, why, n) : 0;
	if (prog_text)
		font_build();
	if (!prog_warp || !prog_pattern || !prog_text)
		return 1;
	why[0] = '\0';

	return 0;
}

const char *gl_renderer(void)
{
	return renderer;
}

/* an EGLImage over one dma-buf plane */
static EGLImageKHR image(int fourcc, int w, int h, int fd, int offset, int pitch)
{
	EGLint a[13], i = 0;

	a[i++] = EGL_WIDTH;			a[i++] = w;
	a[i++] = EGL_HEIGHT;			a[i++] = h;
	a[i++] = EGL_LINUX_DRM_FOURCC_EXT;	a[i++] = fourcc;
	a[i++] = EGL_DMA_BUF_PLANE0_FD_EXT;	a[i++] = fd;
	a[i++] = EGL_DMA_BUF_PLANE0_OFFSET_EXT;	a[i++] = offset;
	a[i++] = EGL_DMA_BUF_PLANE0_PITCH_EXT;	a[i++] = pitch;
	a[i] = EGL_NONE;

	return p_img_new(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, a);
}

static GLuint texture(EGLImageKHR img, int unit)
{
	GLuint t;

	glGenTextures(1, &t);
	glActiveTexture((GLenum)(GL_TEXTURE0 + unit));
	glBindTexture(GL_TEXTURE_2D, t);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	p_img_tex(GL_TEXTURE_2D, img);

	return t;
}

/* the three panel buffers h713-tv handed over: image, renderbuffer, FBO */
bool gl_targets(const struct peer *p, char *why, size_t n)
{
	int i;

	panel_w = p->width;
	panel_h = p->height;
	for (i = 0; i < WARP_TARGETS; i++) {
		target[i].img = image(DRM_FORMAT_XRGB8888, (int)p->width,
				      (int)p->height, p->target[i], 0, (int)p->pitch);
		if (target[i].img == EGL_NO_IMAGE_KHR)
			return oops(why, n, "XRGB8888 import of a panel buffer");
		glGenRenderbuffers(1, &target[i].rb);
		glGenFramebuffers(1, &target[i].fbo);
		glBindRenderbuffer(GL_RENDERBUFFER, target[i].rb);
		p_img_rb(GL_RENDERBUFFER, target[i].img);
		glBindFramebuffer(GL_FRAMEBUFFER, target[i].fbo);
		glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
					  GL_RENDERBUFFER, target[i].rb);
		if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
			return oops(why, n, "FBO on an imported panel buffer");
	}
	why[0] = '\0';

	return true;
}

/* the capture slots, imported once: Y as R8, C as GR88 at half width and
 * full height, because the source is 4:2:2 NV16 and not NV12
 */
bool gl_source(const struct source *s, char *why, size_t n)
{
	int i;

	for (i = 0; i < WARP_SLOTS; i++) {
		int cfd = s->planes > 1 ? s->dmabuf[i][1] : s->dmabuf[i][0];
		int coff = s->planes > 1 ? 0 : (int)s->off_c;

		slot[i].img[0] = image(DRM_FORMAT_R8, (int)s->width, (int)s->height,
				       s->dmabuf[i][0], 0, (int)s->pitch);
		slot[i].img[1] = image(DRM_FORMAT_GR88, (int)s->width / 2,
				       (int)s->height, cfd, coff, (int)s->cpitch);
		if (slot[i].img[0] == EGL_NO_IMAGE_KHR ||
		    slot[i].img[1] == EGL_NO_IMAGE_KHR)
			return oops(why, n, "R8 + GR88 import of a capture slot");
		slot[i].tex[0] = texture(slot[i].img[0], 0);
		slot[i].tex[1] = texture(slot[i].img[1], 1);
		slots_up = i + 1;
	}
	why[0] = '\0';

	return true;
}

/* a source geometry change throws the six images away; the targets stay */
void gl_source_drop(void)
{
	int i, j;

	for (i = 0; i < slots_up; i++)
		for (j = 0; j < 2; j++) {
			if (slot[i].tex[j])
				glDeleteTextures(1, &slot[i].tex[j]);
			if (slot[i].img[j] && p_img_del)
				p_img_del(dpy, slot[i].img[j]);
			slot[i].tex[j] = 0;
			slot[i].img[j] = NULL;
		}
	slots_up = 0;
}

bool gl_draw(int target_index, int source_slot, const float m[16], int pattern,
	     int mark_corner, const char *const labels[5], char *why, size_t n)
{
	static const GLfloat quad[] = {
		-1, -1, 0, 0,   1, -1, 1, 0,   -1, 1, 0, 1,   1, 1, 1, 1,
	};
	GLuint prog = pattern == PATTERN_NONE ? prog_warp : prog_pattern;
	GLenum err;

	glBindFramebuffer(GL_FRAMEBUFFER, target[target_index].fbo);
	glViewport(0, 0, (GLsizei)panel_w, (GLsizei)panel_h);
	/* the warp shrinks the picture, so what is outside the quad is defined */
	glClearColor(0, 0, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glUseProgram(prog);
	glUniformMatrix4fv(glGetUniformLocation(prog, "u_k"), 1, GL_FALSE, m);
	if (pattern == PATTERN_NONE) {
		glUniform1i(glGetUniformLocation(prog, "u_y"), 0);
		glUniform1i(glGetUniformLocation(prog, "u_c"), 1);
		glActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D, slot[source_slot].tex[0]);
		glActiveTexture(GL_TEXTURE1);
		glBindTexture(GL_TEXTURE_2D, slot[source_slot].tex[1]);
	} else {
		glUniform1f(glGetUniformLocation(prog, "u_grid"),
			    pattern == PATTERN_GRID ? 1.0f : 0.0f);
		glUniform1f(glGetUniformLocation(prog, "u_mask"),
			    pattern == PATTERN_MASK ? 1.0f : 0.0f);
		glUniform1f(glGetUniformLocation(prog, "u_aspect"),
			    panel_h ? (float)panel_w / (float)panel_h : 1.0f);
		glUniform1i(glGetUniformLocation(prog, "u_corner"),
			    pattern == PATTERN_MASK ? mark_corner : -1);
	}
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, quad);
	glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, quad + 2);
	glEnableVertexAttribArray(0);
	glEnableVertexAttribArray(1);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	if (pattern == PATTERN_MASK && labels) {
		/* 22 panel pixels high; the corners just inside the frame, the
		 * centre line below the dot; x steps are the glyph advance */
		/* the frame line sits at 6 percent of the height from each edge (the
		 * mask shader), 40 px glyphs are 7.4 percent of it: the top row
		 * starts just under the top edge, the bottom row ends just above
		 * the frame line at the bottom */
		float h = 40.0f, left = -0.94f, top = -0.96f, bottom = 0.90f;
		float right = 0.94f - (labels[1] ? (float)strlen(labels[1]) : 0) * h * 6.0f / 7.0f * 2.0f / (float)panel_w;
		float right3 = 0.94f - (labels[3] ? (float)strlen(labels[3]) : 0) * h * 6.0f / 7.0f * 2.0f / (float)panel_w;

		if (labels[0]) text_draw(labels[0], left, top, h);
		if (labels[1]) text_draw(labels[1], right, top, h);
		/* both rows in the band outside the frame line (6 percent), which the
		 * warp never covers with picture */
		if (labels[2]) text_draw(labels[2], left, bottom, h);
		if (labels[3]) text_draw(labels[3], right3, bottom, h);
		if (labels[4]) text_draw(labels[4], -0.42f, 0.34f, h);
	}
	err = glGetError();
	if (err) {
		snprintf(why, n, "draw: gl 0x%x", err);
		return false;
	}

	return true;
}

/* The out-fence: h713-tv passes it to the commit as IN_FENCE_FD, and
 * drm_atomic_helper_commit waits it out before the commit tail writes
 * AFBD_SRC, so GPU and scanout never overlap on a buffer. No fence: glFinish.
 */
int gl_fence(void)
{
	EGLSyncKHR sy = p_sync_new(dpy, EGL_SYNC_NATIVE_FENCE_ANDROID, NULL);
	int fd = -1;

	glFlush();
	if (sy != EGL_NO_SYNC_KHR) {
		fd = p_sync_fd(dpy, sy);
		p_sync_del(dpy, sy);
	}
	if (fd < 0)
		glFinish();

	return fd;
}

void gl_close(void)
{
	int i;

	gl_source_drop();
	for (i = 0; i < WARP_TARGETS; i++) {
		if (target[i].fbo)
			glDeleteFramebuffers(1, &target[i].fbo);
		if (target[i].rb)
			glDeleteRenderbuffers(1, &target[i].rb);
		if (target[i].img && p_img_del)
			p_img_del(dpy, target[i].img);
		memset(&target[i], 0, sizeof(target[i]));
	}
	if (dpy != EGL_NO_DISPLAY) {
		eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
		eglTerminate(dpy);
	}
	dpy = EGL_NO_DISPLAY;
	ctx = EGL_NO_CONTEXT;
	prog_warp = prog_pattern = prog_text = 0;
	font_tex = 0;
	snprintf(renderer, sizeof(renderer), "not opened");
}
