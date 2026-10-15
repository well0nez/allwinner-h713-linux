/* SPDX-License-Identifier: GPL-2.0 */
/*
 * EGL and GLES2 on the render node (design AP2d M6 and M8). Everything here
 * is the working code of h713-gpu-probe's own scanout.c, which
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
#define _GNU_SOURCE		/* clock_gettime, CLOCK_THREAD_CPUTIME_ID */
#define EGL_NO_X11
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <drm_fourcc.h>
#ifndef GL_RED_EXT
#define GL_RED_EXT 0x1903	/* GL_EXT_texture_rg */
#endif

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
/* The warp writes NV12 (23.09.2026): Y is resampled into the luma plane and
 * CbCr into the chroma plane, each through the same matrix, no colour maths
 * at all - the values leave the ring as they came, only moved, and the
 * firmware's picture controls, gamma and the rest act on them afterwards
 * exactly as on the ring, because it is the same channel. The chroma pass
 * draws at half size and the linear sampler averages the 4:2:2 source's two
 * chroma lines into the 4:2:0 output's one. */
/* The picture passes are a bare fetch: Y into the luma plane, CbCr into the
 * chroma plane, nothing else in the fragment. Anything after the fetch costs
 * this GPU dearly -- the Mali-G31 (one core) hides no texture latency behind
 * arithmetic: with the soft border's dozen operations folded into these
 * shaders a frame took the GPU 6.1 ms at 696 MHz, a bare fetch 1.65 ms, one
 * constant mix after the fetch 2.2 ms (measured 11.10.2026 through the
 * out-fence, arbeit/warp-zeichnen-20261011 m16-m18). So the border is its own
 * small draw again, below. */
const char *const gl_luma_shader =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y, u_c;\n"
	"void main() { gl_FragColor = vec4(texture2D(u_y, v_uv).r, 0.0, 0.0, 1.0); }\n";
const char *const gl_chroma_shader =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y, u_c;\n"
	"void main() { gl_FragColor = vec4(texture2D(u_c, v_uv).rg, 0.0, 1.0); }\n";

/* The vendor's soft border (FB-EDGEBLEND; draw_edge @ 0x3C64 in the stock
 * libkeystone.so): a GL_ALPHA mask of w/4 by h/4 texels, each count rounded
 * up to 16, its outermost texel ring at 255 - 20 and 0 inside, sampled
 * GL_LINEAR over the warped quad and blended as black with SRC_ALPHA /
 * ONE_MINUS_SRC_ALPHA. Seen from the quad's edge inward: half a texel at
 * 20/255 of the picture, then a one-texel linear ramp up to the full picture.
 * Drawn here as the vendor draws it, blended over the picture, but only where
 * it changes anything: a ring of ten vertices along the quad's edge, 1.5 mask
 * texels wide (gl_edge_ring), one triangle strip per plane, no overlap. u_edge
 * is the mask's texel count across the quad, r the ring as the linear filter
 * sees it in each axis, and the bilinear sample of an OR of two rings is
 * 1 - (1 - r.x)(1 - r.y); keep is what stays of the picture. The blend runs
 * towards u_fill, the plane's video black (Y 16, CbCr 128), so the band meets
 * the border without a step; the vendor's residual 20/255 stays. Inside the
 * ring keep is exactly 1, which is why the ring may stop there. */
const char *const gl_edge_shader =
	"precision highp float; varying vec2 v_uv; uniform vec2 u_edge, u_fill;\n"
	"void main() { vec2 r = clamp(1.5 - min(v_uv, 1.0 - v_uv) * u_edge, 0.0, 1.0);\n"
	"  float keep = 1.0 - 0.9215686 * (1.0 - (1.0 - r.x) * (1.0 - r.y));\n"
	"  gl_FragColor = vec4(u_fill, 0.0, 1.0 - keep); }\n";

static int edge_px;	/* the soft border's width in panel pixels, 0 = off ("edge" in warp.conf) */

void gl_edge(int px)
{
	edge_px = px;
}

/* The mask's texel count across the quad, the vendor's way: (w / px + 15) & ~15
 * per axis (draw_edge @ 0x3C64, its two guarded statics), so 1920x1080 at 4 is
 * 480x272 as on the stock; both 0 when off. */
void gl_edge_mask(unsigned int w, unsigned int h, int px, int out[2])
{
	out[0] = px > 0 ? (int)((w / (unsigned int)px + 15u) & ~15u) : 0;
	out[1] = px > 0 ? (int)((h / (unsigned int)px + 15u) & ~15u) : 0;
}

/* The ring's ten vertices (x, y, u, v each) as a triangle strip: outer and
 * inner corner alternating, around the quad and back to the start, 1.5 mask
 * texels wide -- the width over which the vendor's mask is not yet 0. In the
 * quad's own coordinates, so the vertex shader maps it like the picture. */
void gl_edge_ring(const int e[2], float v[40])
{
	static const float outer[4][2] = { { 0, 0 }, { 1, 0 }, { 1, 1 }, { 0, 1 } };
	float bx = e[0] > 0 ? 1.5f / (float)e[0] : 0.0f;
	float by = e[1] > 0 ? 1.5f / (float)e[1] : 0.0f;
	int i;

	for (i = 0; i < 5; i++) {
		const float *o = outer[i % 4];
		float iu = o[0] > 0.5f ? 1.0f - bx : bx, iv = o[1] > 0.5f ? 1.0f - by : by;

		v[i * 8 + 0] = 2.0f * o[0] - 1.0f;
		v[i * 8 + 1] = 2.0f * o[1] - 1.0f;
		v[i * 8 + 2] = o[0];
		v[i * 8 + 3] = o[1];
		v[i * 8 + 4] = 2.0f * iu - 1.0f;
		v[i * 8 + 5] = 2.0f * iv - 1.0f;
		v[i * 8 + 6] = iu;
		v[i * 8 + 7] = iv;
	}
}

const char *const gl_fragment_shader =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y, u_c;\n"
	"void main() { float y = 1.1643835 * (texture2D(u_y, v_uv).r - 0.0627451);\n"
	"  vec2 c = texture2D(u_c, v_uv).rg - 0.5019608;\n"
	"  gl_FragColor = vec4(y + 1.7927411 * c.y, y - 0.2132486 * c.x - 0.5329093 * c.y,\n"
	"                      y + 2.1124018 * c.x, 1.0); }\n";

/* MASK: quiet grid, frame and circle. Height-relative coordinates keep circles
 * round; pixel-relative line widths keep the 720p and 1080p views comparable.
 * The diagnostic GRID/BORDER branch and the video shaders stay unchanged. */
const char *const gl_pattern_shader =
	"precision highp float; varying vec2 v_uv;\n"
	"uniform float u_grid, u_mask, u_aspect, u_panel_h; uniform int u_corner;\n"
	"float ink(float d, float w, float px) { return 1.0 - smoothstep(w, w + px, d); }\n"
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
	"  float px = 1.0 / max(u_panel_h, 1.0), margin = 0.0666667;\n"
	"  float inside = step(margin, min(ep.x, ep.y));\n"
	"  float col = mix(0.035, 0.065, inside);\n"
	"  vec2 g = abs(fract((p - c) * 9.0 + 0.5) - 0.5) / 9.0;\n"
	"  float grid = ink(min(g.x, g.y), 0.45 * px, px) * inside;\n"
	"  col = mix(col, 0.20, grid);\n"
	"  float cross = ink(min(abs(p.x-c.x), abs(p.y-c.y)), 0.6*px, px) * inside;\n"
	"  col = mix(col, 0.42, cross);\n"
	"  float circle = ink(abs(length(p-c)-0.25), 0.75*px, px);\n"
	"  col = mix(col, 0.68, circle);\n"
	"  float dot = ink(abs(length(p-c)-0.0125), 0.65*px, px);\n"
	"  col = mix(col, 0.9, dot);\n"
	"  float frame = ink(abs(min(ep.x,ep.y)-margin), 0.8*px, px);\n"
	"  col = mix(col, 0.86, frame);\n"
	"  float corner = max(ink(abs(ep.x-margin),1.5*px,px) * step(ep.y,margin+0.045),\n"
	"                     ink(abs(ep.y-margin),1.5*px,px) * step(ep.x,margin+0.045));\n"
	"  corner *= step(margin-2.5*px,min(ep.x,ep.y));\n"
	"  col = mix(col, 1.0, corner);\n"
	"  gl_FragColor = vec4(vec3((16.0 + 219.0*col)/255.0), 1.0); }\n";

/* The Wayland client (package G): RGB in, the panel's NV12 out, and the colour maths INSIDE the keystone passes - T3's
 * variant B, 4.16 ms a frame for an AFBC source against 7.0 for a pass of its own (AU-47). BT.709 limited range: Y =
 * 16/255 + (219/255) (0.2126 R + 0.7152 G + 0.0722 B), Cb/Cr = 128/255 + (224/255) (B - Y') / 1.8556 and (R - Y') /
 * 1.5748. The chroma pass draws at half size, and the linear sampler averages the 2 x 2 RGB pixels under each output
 * pixel. AR30 is read normalised like any other format; alpha is ignored (premultiplied over black). */
const char *const gl_rgb_luma_shader =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y;\n"
	"void main() { gl_FragColor = vec4(dot(texture2D(u_y, v_uv).rgb, vec3(0.1825859, 0.6142306, 0.0620071))\n"
	"  + 0.0627451, 0.0, 0.0, 1.0); }\n";
const char *const gl_rgb_chroma_shader =
	"precision highp float; varying vec2 v_uv; uniform sampler2D u_y;\n"
	"void main() { vec3 c = texture2D(u_y, v_uv).rgb; float y = dot(c, vec3(0.2126, 0.7152, 0.0722));\n"
	"  gl_FragColor = vec4((c.b - y) * 0.4733948 + 0.5019608, (c.r - y) * 0.5578050 + 0.5019608, 0.0, 1.0); }\n";

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
/* the frame-cost trace (gl_timing, gl_last_cost), see the end of this file */
static bool timing_on;
static struct gl_cost cost;

static EGLDisplay dpy = EGL_NO_DISPLAY;
static EGLContext ctx = EGL_NO_CONTEXT;
static char renderer[128] = "not opened";
static GLuint prog_warp, prog_pattern, prog_luma, prog_chroma, prog_edge_y, prog_edge_c;
static GLuint prog_rgb_y, prog_rgb_c;	/* the Wayland client's two passes */
static bool gl_up;			/* gl_open() succeeded and gl_close() has not run since */
static unsigned int gl_gen = 1;		/* counts gl_close(): an image of an older one is gone */

/*
 * What a pass sets on its program, and what it set last time. Mesa's
 * glGetUniformLocation is a string lookup and every glUniform* dirties the
 * program's constant buffer for the next draw, so the matrix and the edge
 * width go to the GPU only when they changed -- which is never, frame to
 * frame, until somebody turns the keystone. The sampler units are fixed at
 * link time. Measured 11.10.2026 (arbeit/warp-zeichnen-20261011): the two
 * video passes cost this thread 750-900 us a frame at 1296 MHz before.
 */
struct pass_state {
	GLuint prog;
	GLint u_k, u_edge;
	float k[16];
	float edge[2];
	bool k_set, edge_set;
};
static struct pass_state pass_luma, pass_chroma, pass_edge_y, pass_edge_c, pass_rgb_y, pass_rgb_c;
static GLuint quad_vbo;		/* the unit quad, uploaded once */
static bool quad_bound;		/* the vertex pointers point at it (text_draw moves them) */
static GLuint ring_vbo;		/* the border's ring, uploaded when the mask count changes */
static int ring_e[2];
static unsigned int panel_w, panel_h;

/* Text over the mask: a 5x7 font for the digits, the lowercase letters and
 * ". / : - %", built into a luminance texture once, drawn as one quad per
 * glyph through the mode's flip alone (not the keystone), so the numbers
 * stay upright and readable on the wall whatever the warp does to the
 * picture. Each glyph is seven rows of five bits, MSB left. */
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
	"precision mediump float; varying vec2 v_uv; uniform sampler2D u_font; uniform float u_luma;\n"
	"void main() { float a = texture2D(u_font, v_uv).r;\n"
	"  gl_FragColor = vec4(vec3(u_luma), 1.0) * a; }\n";

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

/* One string at (x, y) in NDC, glyphs `h` panel pixels high, upright on the
 * wall (through `k`, the mode's flip, FB-MIRROR), blended */
static void text_draw(const char *s, float x, float y, float h, float luma, const float k[16])
{
	float gw = h * 6.0f / 7.0f * 2.0f / (float)panel_w;	/* advance in NDC */
	float gh = h * 2.0f / (float)panel_h;
	float cw = h * 8.0f / 7.0f * 2.0f / (float)panel_w;	/* the 8-texel cell */

	glUseProgram(prog_text);
	glUniformMatrix4fv(glGetUniformLocation(prog_text, "u_k"), 1, GL_FALSE, k);
	glUniform1i(glGetUniformLocation(prog_text, "u_font"), 0);
	glUniform1f(glGetUniformLocation(prog_text, "u_luma"), luma);
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

		glBindBuffer(GL_ARRAY_BUFFER, 0);
		glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, q);
		glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, q + 2);
		glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	}
	glDisable(GL_BLEND);
	quad_bound = false;
}

/* Labels stay upright in panel space, as before. Cards separate them from the
 * moving geometry without changing the warp, corner identity or numeric units. */
/* A card's rectangle in panel pixels, mirrored as the mode flips the panel
 * (lm[0] < 0: left-right, lm[5] < 0: top-bottom), so the card stands where the
 * wall expects it; the text inside goes through the same flip. */
static void label_box(float x, float y, float w, float h, float luma, const float lm[16])
{
	if (lm[0] < 0)
		x = (float)panel_w - x - w;
	if (lm[5] < 0)
		y = (float)panel_h - y - h;
	glEnable(GL_SCISSOR_TEST);
	glScissor((GLint)x, (GLint)y, (GLsizei)w, (GLsizei)h);
	glClearColor(luma, 0, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glDisable(GL_SCISSOR_TEST);
}

static float label_width(const char *s, float h)
{
	return (float)strlen(s) * h * 6.0f / 7.0f;
}

static void label_text(const char *s, float x, float y, float h, float luma, const float lm[16])
{
	text_draw(s, 2.0f*x/(float)panel_w-1.0f,
		  2.0f*y/(float)panel_h-1.0f, h, luma, lm);
}

static void mask_labels(const char *const labels[5], int active, const float lm[16])
{
	float scale = (float)panel_h / 720.0f, pad = 12.0f*scale;
	float margin = (48.0f+22.0f)*scale, w = 300.0f*scale, h = 60.0f*scale;
	float number_h = 14.0f*scale, title_h = 18.0f*scale;
	int c;

	for (c = 0; c < 4; c++) {
		char title[40], *numbers;
		float x, y, nh = number_h;

		if (!labels[c])
			continue;
		snprintf(title, sizeof(title), "%s", labels[c]);
		numbers = strchr(title, '\n');
		if (numbers)
			*numbers++ = '\0';
		x = c == 1 || c == 3 ? (float)panel_w-margin-w : margin;
		y = c >= 2 ? (float)panel_h-margin-h : margin;
		label_box(x, y, w, h, c == active ? 218.0f/255.0f : 80.0f/255.0f, lm);
		label_box(x+scale, y+scale, w-2*scale, h-2*scale, 20.0f/255.0f, lm);
		label_text(title, x+pad, y+9*scale, title_h, 225.0f/255.0f, lm);
		if (numbers) {
			float needed = label_width(numbers, nh);
			if (needed > w-2*pad)
				nh *= (w-2*pad)/needed;
			label_text(numbers, x+pad, y+34*scale, nh, 190.0f/255.0f, lm);
		}
	}
	if (labels[4])
		label_text(labels[4], ((float)panel_w-label_width(labels[4],title_h))/2,
			   (float)panel_h-116*scale, title_h, 225.0f/255.0f, lm);
	const char *hint = "per-mille inward, value/max";
	label_text(hint, ((float)panel_w-label_width(hint,number_h))/2,
		   (float)panel_h-32*scale, number_h, 150.0f/255.0f, lm);
}


static struct {
	EGLImageKHR img[2];		/* the luma plane as R8, the chroma plane as GR88 */
	GLuint rb[2], fbo[2];
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

static void pass_init(struct pass_state *p, GLuint prog);

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

	/* once: the ring and the Wayland client share the one context (package G) */
	if (gl_up)
		return 0;
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
	prog_luma = prog_warp ? program(gl_luma_shader, why, n) : 0;
	prog_chroma = prog_luma ? program(gl_chroma_shader, why, n) : 0;
	prog_pattern = prog_chroma ? program(gl_pattern_shader, why, n) : 0;
	prog_text = prog_pattern ? program(gl_text_shader, why, n) : 0;
	if (prog_text)
		font_build();
	if (!prog_warp || !prog_luma || !prog_chroma || !prog_pattern || !prog_text)
		return 1;
	prog_edge_y = program(gl_edge_shader, why, n);
	prog_edge_c = prog_edge_y ? program(gl_edge_shader, why, n) : 0;
	prog_rgb_y = prog_edge_c ? program(gl_rgb_luma_shader, why, n) : 0;
	prog_rgb_c = prog_rgb_y ? program(gl_rgb_chroma_shader, why, n) : 0;
	if (!prog_rgb_c)
		return 1;
	pass_init(&pass_rgb_y, prog_rgb_y);
	pass_init(&pass_rgb_c, prog_rgb_c);
	pass_init(&pass_luma, prog_luma);
	pass_init(&pass_chroma, prog_chroma);
	pass_init(&pass_edge_y, prog_edge_y);
	glUniform2f(glGetUniformLocation(prog_edge_y, "u_fill"), 16.0f / 255.0f, 0.0f);
	pass_init(&pass_edge_c, prog_edge_c);
	glUniform2f(glGetUniformLocation(prog_edge_c, "u_fill"), 128.0f / 255.0f, 128.0f / 255.0f);
	glGenBuffers(1, &ring_vbo);
	ring_e[0] = ring_e[1] = -1;
	{
		static const GLfloat quad[] = {
			-1, -1, 0, 0,   1, -1, 1, 0,   -1, 1, 0, 1,   1, 1, 1, 1,
		};

		glGenBuffers(1, &quad_vbo);
		glBindBuffer(GL_ARRAY_BUFFER, quad_vbo);
		glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
		glEnableVertexAttribArray(0);
		glEnableVertexAttribArray(1);
		quad_bound = false;
	}
	why[0] = '\0';
	gl_up = true;

	return 0;
}

bool gl_is_open(void)
{
	return gl_up;
}

/* the locations once, the sampler units for good, the rest "not set yet" */
static void pass_init(struct pass_state *p, GLuint prog)
{
	memset(p, 0, sizeof(*p));
	p->prog = prog;
	p->u_k = glGetUniformLocation(prog, "u_k");
	p->u_edge = glGetUniformLocation(prog, "u_edge");
	glUseProgram(prog);
	glUniform1i(glGetUniformLocation(prog, "u_y"), 0);
	glUniform1i(glGetUniformLocation(prog, "u_c"), 1);
}

/* the program with its matrix and edge, sent only when they moved */
static void pass_use(struct pass_state *p, const float m[16], const float e[2])
{
	glUseProgram(p->prog);
	if (!p->k_set || memcmp(p->k, m, sizeof(p->k))) {
		glUniformMatrix4fv(p->u_k, 1, GL_FALSE, m);
		memcpy(p->k, m, sizeof(p->k));
		p->k_set = true;
	}
	if (!p->edge_set || p->edge[0] != e[0] || p->edge[1] != e[1]) {
		glUniform2f(p->u_edge, e[0], e[1]);
		p->edge[0] = e[0];
		p->edge[1] = e[1];
		p->edge_set = true;
	}
}

/* the unit quad as the vertex source, unless it is there already */
static void quad_use(void)
{
	if (quad_bound)
		return;
	glBindBuffer(GL_ARRAY_BUFFER, quad_vbo);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, (const void *)0);
	glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, (const void *)8);
	glEnableVertexAttribArray(0);
	glEnableVertexAttribArray(1);
	quad_bound = true;
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
		int k;

		/* one dma-buf, two planes: Y as R8 at 0, CbCr as GR88 at coff */
		target[i].img[0] = image(DRM_FORMAT_R8, (int)p->width, (int)p->height,
					 p->target[i], 0, (int)p->pitch);
		target[i].img[1] = image(DRM_FORMAT_GR88, (int)p->width / 2, (int)p->height / 2,
					 p->target[i], (int)p->coff, (int)p->pitch);
		if (target[i].img[0] == EGL_NO_IMAGE_KHR || target[i].img[1] == EGL_NO_IMAGE_KHR)
			return oops(why, n, "R8 + GR88 import of an NV12 panel buffer");
		for (k = 0; k < 2; k++) {
			glGenRenderbuffers(1, &target[i].rb[k]);
			glGenFramebuffers(1, &target[i].fbo[k]);
			glBindRenderbuffer(GL_RENDERBUFFER, target[i].rb[k]);
			p_img_rb(GL_RENDERBUFFER, target[i].img[k]);
			glBindFramebuffer(GL_FRAMEBUFFER, target[i].fbo[k]);
			glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
						  GL_RENDERBUFFER, target[i].rb[k]);
			if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
				return oops(why, n, k ? "FBO on the chroma plane (GR88) of a panel buffer"
						      : "FBO on the luma plane (R8) of a panel buffer");
		}
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

/* One pass into one plane: the quad through the matrix with the given program
 * at the plane's size; what the quad does not cover is the clear colour (video
 * black: Y 16, CbCr 128). Labels are drawn on the luma pass only. */
/* the ring as the vertex source, rebuilt when the mask count moved */
static void ring_use(const int e[2])
{
	glBindBuffer(GL_ARRAY_BUFFER, ring_vbo);
	if (ring_e[0] != e[0] || ring_e[1] != e[1]) {
		float v[40];

		gl_edge_ring(e, v);
		glBufferData(GL_ARRAY_BUFFER, sizeof(v), v, GL_STATIC_DRAW);
		ring_e[0] = e[0];
		ring_e[1] = e[1];
	}
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 16, (const void *)0);
	glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 16, (const void *)8);
	quad_bound = false;
}

/* the soft border over one plane: the ring, blended towards the plane's black */
static void edge_draw(struct pass_state *p, const int e[2], const float m[16])
{
	float ef[2] = { (float)e[0], (float)e[1] };

	pass_use(p, m, ef);
	ring_use(e);
	glEnable(GL_BLEND);
	glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 10);
	glDisable(GL_BLEND);
}

static bool draw_into(GLuint fbo, int fw, int fh, float clear0, float clear1, GLuint prog,
		      int source_slot, const float m[16], int pattern, int mark_corner,
		      const char *const labels[5], const float lm[16], char *why, size_t n)
{
	GLenum err;
	int e[2] = { 0, 0 };

	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glViewport(0, 0, (GLsizei)fw, (GLsizei)fh);
	/* the warp shrinks the picture, so what is outside the quad is defined */
	glClearColor(clear0, clear1, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	if (pattern == PATTERN_NONE) {
		float ef[2];

		gl_edge_mask(panel_w, panel_h, edge_px, e);
		ef[0] = (float)e[0];
		ef[1] = (float)e[1];
		pass_use(prog == prog_luma ? &pass_luma : &pass_chroma, m, ef);
		/* the slot's two planes on units 0 and 1: bound once a frame,
		 * by the luma pass; the chroma pass finds them there */
		if (prog == prog_luma) {
			glActiveTexture(GL_TEXTURE0);
			glBindTexture(GL_TEXTURE_2D, slot[source_slot].tex[0]);
			glActiveTexture(GL_TEXTURE1);
			glBindTexture(GL_TEXTURE_2D, slot[source_slot].tex[1]);
		}
	} else {
		glUseProgram(prog);
		glUniformMatrix4fv(glGetUniformLocation(prog, "u_k"), 1, GL_FALSE, m);
		glUniform1f(glGetUniformLocation(prog, "u_grid"),
			    pattern == PATTERN_GRID ? 1.0f : 0.0f);
		glUniform1f(glGetUniformLocation(prog, "u_mask"),
			    pattern == PATTERN_MASK ? 1.0f : 0.0f);
		glUniform1f(glGetUniformLocation(prog, "u_aspect"),
			    panel_h ? (float)panel_w / (float)panel_h : 1.0f);
		glUniform1f(glGetUniformLocation(prog, "u_panel_h"), (float)panel_h);
		glUniform1i(glGetUniformLocation(prog, "u_corner"),
			    pattern == PATTERN_MASK ? mark_corner : -1);
	}
	quad_use();
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	if (pattern == PATTERN_NONE && e[0] > 0)
		edge_draw(prog == prog_luma ? &pass_edge_y : &pass_edge_c, e, m);
	if (pattern == PATTERN_MASK && labels) {
		mask_labels(labels, mark_corner, lm);
	}
	/* one error check a frame is enough: the chroma pass's, or the
	 * pattern's single pass -- an error in the luma pass is still pending
	 * then, glGetError() keeps it until it is read */
	if (prog == prog_luma)
		return true;
	err = glGetError();
	if (err) {
		snprintf(why, n, "draw: gl 0x%x", err);
		return false;
	}

	return true;
}

/* The cost of a frame (warp.h): this thread's CPU time around each pass.
 * GL_EXT_disjoint_timer_query is NOT used for the GPU's time: Panfrost (Mesa
 * 25.0) answers it from the CPU clock at the batch boundaries ("luma 0.01 ms,
 * chroma 1.5 ms" for two passes of the same shape, measured 11.10.2026), so
 * the GPU's time is taken from the out-fence instead, in loop.c. */
static bool timing_on;
static struct gl_cost cost;

void gl_timing(bool on)
{
	timing_on = on;
}

const struct gl_cost *gl_last_cost(void)
{
	return &cost;
}

static unsigned int thread_us(void)
{
	struct timespec t;

	clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
	return (unsigned int)(t.tv_sec * 1000000 + t.tv_nsec / 1000);
}

/* A frame: the luma pass at full size, the chroma pass at half size. A pattern
 * is grey: its shader draws into the luma plane as it always did (0..1 becomes
 * Y 0..255, the mask's white is the panel's white) and the chroma plane stays
 * at 128. */
bool gl_draw(int target_index, int source_slot, const float m[16], int pattern,
	     int mark_corner, const char *const labels[5], const float lm[16], char *why, size_t n)
{
	unsigned int c0 = timing_on ? thread_us() : 0, c1;
	bool ok;

	ok = draw_into(target[target_index].fbo[0], (int)panel_w, (int)panel_h,
		       16.0f / 255.0f, 0.0f,
		       pattern == PATTERN_NONE ? prog_luma : prog_pattern,
		       source_slot, m, pattern, mark_corner, labels, lm, why, n);
	if (!ok)
		return false;
	c1 = timing_on ? thread_us() : 0;
	if (pattern != PATTERN_NONE) {
		glBindFramebuffer(GL_FRAMEBUFFER, target[target_index].fbo[1]);
		glViewport(0, 0, (GLsizei)panel_w / 2, (GLsizei)panel_h / 2);
		glClearColor(128.0f / 255.0f, 128.0f / 255.0f, 0, 1);
		glClear(GL_COLOR_BUFFER_BIT);
		return true;
	}
	ok = draw_into(target[target_index].fbo[1], (int)panel_w / 2, (int)panel_h / 2,
		       128.0f / 255.0f, 128.0f / 255.0f, prog_chroma,
		       source_slot, m, PATTERN_NONE, -1, NULL, NULL, why, n);
	if (timing_on) {
		cost.cpu_luma_us = c1 - c0;
		cost.cpu_chroma_us = thread_us() - c1;
	}
	return ok;
}

/*
 * The self-check (no eyes needed): the same slot drawn a second time, into a
 * scratch buffer, 12 ms after the first draw, and the two compared row by
 * row. The capture ring carries no fence, so the only way to know whether the
 * first draw read a slot the firmware was still writing is to draw it again
 * once it is certainly written and look for rows that changed. Zero differing
 * rows over a few hundred frames of motion is the pass; a band of differing
 * rows at the bottom is the source race (loop.c). Two 8 MB readbacks per
 * checked frame, so only on request ("ctl check").
 */
static GLuint check_fbo, check_tex;
static unsigned char *check_a, *check_b;
#define CHECK_STEP	34		/* every 34th row: 32 rows of 1080, half a MB per check */

/* bytes per pixel of the bound FBO's native readback: 4 for RGBA, 1 for RED */
static int read_bpp(void)
{
	GLint fmt = GL_RGBA, type = GL_UNSIGNED_BYTE;

	glGetIntegerv(GL_IMPLEMENTATION_COLOR_READ_FORMAT, &fmt);
	glGetIntegerv(GL_IMPLEMENTATION_COLOR_READ_TYPE, &type);
	return fmt == GL_RED_EXT && type == GL_UNSIGNED_BYTE ? 1 : 4;
}

bool gl_check_compare(int target_index, int source_slot, const float m[16],
		      unsigned long *rows, int *lo, int *hi, char *why, size_t n)
{
	size_t line = (size_t)panel_w * 4;
	int y, x, bpp_a, bpp_b;

	if (!check_fbo) {
		glGenTextures(1, &check_tex);
		glBindTexture(GL_TEXTURE_2D, check_tex);
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, (GLsizei)panel_w, (GLsizei)panel_h,
			     0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
		glGenFramebuffers(1, &check_fbo);
		glBindFramebuffer(GL_FRAMEBUFFER, check_fbo);
		glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D,
				       check_tex, 0);
		if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
			return oops(why, n, "the self-check's scratch FBO");
		check_a = malloc(line * (panel_h / CHECK_STEP + 1));
		check_b = malloc(line * (panel_h / CHECK_STEP + 1));
		if (!check_a || !check_b)
			return oops(why, n, "16 MB for the self-check");
	}
	/* the luma plane is what is compared: Y into the RGBA scratch's red */
	if (!draw_into(check_fbo, (int)panel_w, (int)panel_h, 16.0f / 255.0f, 0.0f, prog_luma,
		       source_slot, m, PATTERN_NONE, -1, NULL, NULL, why, n))
		return false;
	glFinish();
	/* sampled rows, so the check costs a millisecond and not a frame; each
	 * FBO is read in the format its implementation offers (the R8 luma
	 * plane as RED, the RGBA scratch as RGBA), which is the path without a
	 * conversion - only the first byte of a pixel, Y, is compared */
	glBindFramebuffer(GL_FRAMEBUFFER, check_fbo);
	bpp_a = read_bpp();
	for (y = 0; y < (int)panel_h; y += CHECK_STEP)
		glReadPixels(0, y, (GLsizei)panel_w, 1, bpp_a == 4 ? GL_RGBA : GL_RED_EXT,
			     GL_UNSIGNED_BYTE, check_a + (size_t)(y / CHECK_STEP) * line);
	glBindFramebuffer(GL_FRAMEBUFFER, target[target_index].fbo[0]);
	bpp_b = read_bpp();
	for (y = 0; y < (int)panel_h; y += CHECK_STEP)
		glReadPixels(0, y, (GLsizei)panel_w, 1, bpp_b == 4 ? GL_RGBA : GL_RED_EXT,
			     GL_UNSIGNED_BYTE, check_b + (size_t)(y / CHECK_STEP) * line);
	if (glGetError())
		return oops(why, n, "the self-check's readback");
	*rows = 0;
	*lo = -1;
	*hi = -1;
	for (y = 0; y < (int)panel_h; y += CHECK_STEP) {
		const unsigned char *a = check_a + (size_t)(y / CHECK_STEP) * line;
		const unsigned char *b = check_b + (size_t)(y / CHECK_STEP) * line;

		for (x = 0; x < (int)panel_w; x++)
			if (a[x * bpp_a] != b[x * bpp_b])
				break;
		if (x < (int)panel_w) {
			(*rows)++;
			if (*lo < 0)
				*lo = y;
			*hi = y;
		}
	}

	return true;
}

/* The luma plane of one panel buffer, read back and written as a binary PGM:
 * what the warp drew, seen without a wall (23.09.2026, for the zoom and the
 * keystone to be judged from a file). One full readback, only on request. */
bool gl_dump_luma(int target_index, const char *path, char *why, size_t n)
{
	size_t line = (size_t)panel_w * 4;
	unsigned char *buf = malloc(line * panel_h);
	FILE *f;
	int y, x, bpp;

	if (!buf)
		return oops(why, n, "8 MB for the dump");
	glFinish();
	glBindFramebuffer(GL_FRAMEBUFFER, target[target_index].fbo[0]);
	bpp = read_bpp();
	memset(buf, 0x5a, line * panel_h);
	glReadPixels(0, 0, (GLsizei)panel_w, (GLsizei)panel_h, bpp == 4 ? GL_RGBA : GL_RED_EXT,
		     GL_UNSIGNED_BYTE, buf);
	if (glGetError()) {
		free(buf);
		return oops(why, n, "the dump's readback");
	}
	/* what the driver really wrote: four bytes a pixel carry 0,0,255 behind
	 * the red of an R8 plane, one byte a pixel does not (23.09.: the
	 * implementation format said RGBA and the data came packed) */
	if (bpp == 4) {
		int packed = 1;

		for (x = 0; x < 64; x++)
			if (buf[x * 4 + 3] == 255 && buf[x * 4 + 1] == 0 && buf[x * 4 + 2] == 0)
				packed = 0;
		if (packed) {
			bpp = 1;
			snprintf(why, n, "packed");
		}
	}
	f = fopen(path, "w");
	if (!f) {
		snprintf(why, n, "%s: %s", path, strerror(errno));
		free(buf);
		return false;
	}
	fprintf(f, "P5\n%u %u\n255\n", panel_w, panel_h);
	for (y = 0; y < (int)panel_h; y++)
		for (x = 0; x < (int)panel_w; x++)
			fputc(buf[((size_t)y * panel_w + (size_t)x) * (size_t)bpp], f);
	fclose(f);
	free(buf);
	if (strcmp(why, "packed"))
		why[0] = '\0';

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

/* ---------------- the Wayland client (package G) ------------------------ */

struct gl_image {
	EGLImageKHR img;		/* a client dma-buf; EGL_NO_IMAGE_KHR for the wl_shm texture */
	GLuint tex;
	int w, h;
	unsigned int gen;		/* gl_gen at its making */
};

/*
 * The formats a client may send (M3 1): what EGL imports on the render node, not a list by hand - cage passes Kodi's
 * buffer through only when Kodi's format and modifier (AR30, AFBC 0x0800000000000062, G0b) are among the host's. RGB
 * only: the passes compute YCbCr from RGB (ENTWURF G v3 D2), and a modifier EGL may only sample as an external
 * texture is left out (the shader takes a sampler2D).
 */
static const uint32_t RGB[] = {
	DRM_FORMAT_ARGB2101010, DRM_FORMAT_XRGB2101010, DRM_FORMAT_ABGR2101010, DRM_FORMAT_XBGR2101010,
	DRM_FORMAT_ARGB8888, DRM_FORMAT_XRGB8888, DRM_FORMAT_ABGR8888, DRM_FORMAT_XBGR8888,
	DRM_FORMAT_RGBA8888, DRM_FORMAT_RGBX8888, DRM_FORMAT_BGRA8888, DRM_FORMAT_BGRX8888, DRM_FORMAT_RGB565,
};

int gl_formats(struct gl_format *out, int max, char *why, size_t n)
{
	PFNEGLQUERYDMABUFFORMATSEXTPROC qf =
		(PFNEGLQUERYDMABUFFORMATSEXTPROC)eglGetProcAddress("eglQueryDmaBufFormatsEXT");
	PFNEGLQUERYDMABUFMODIFIERSEXTPROC qm =
		(PFNEGLQUERYDMABUFMODIFIERSEXTPROC)eglGetProcAddress("eglQueryDmaBufModifiersEXT");
	EGLint fmt[128], nf = 0, nm, i, j, k = 0;
	EGLuint64KHR mod[64];
	EGLBoolean ext[64];
	unsigned int r;

	if (!gl_up || !has_ext(eglQueryString(dpy, EGL_EXTENSIONS), "EGL_EXT_image_dma_buf_import_modifiers") ||
	    !qf || !qm || !qf(dpy, 128, fmt, &nf)) {
		snprintf(why, n, "the render node has no EGL_EXT_image_dma_buf_import_modifiers");
		return -1;
	}
	for (r = 0; r < sizeof(RGB) / sizeof(RGB[0]); r++)
		for (i = 0; i < nf; i++) {
			if ((uint32_t)fmt[i] != RGB[r])
				continue;
			if (!qm(dpy, fmt[i], 64, mod, ext, &nm))
				nm = 0;
			for (j = 0; j < nm && k < max; j++)
				if (!ext[j])
					out[k++] = (struct gl_format){ RGB[r], mod[j] };
			if (!nm && k < max)	/* the format with the driver's own layout only */
				out[k++] = (struct gl_format){ RGB[r], DRM_FORMAT_MOD_INVALID };
		}
	why[0] = '\0';

	return k;
}

static struct gl_image *image_new(void)
{
	struct gl_image *im = calloc(1, sizeof(*im));

	if (im)
		im->gen = gl_gen;
	return im;
}

struct gl_image *gl_image_dmabuf(int fd, uint32_t fourcc, uint64_t modifier, int w, int h,
				 uint32_t offset, uint32_t pitch, char *why, size_t n)
{
	EGLint a[17], i = 0;
	struct gl_image *im = gl_up ? image_new() : NULL;

	if (!im) {
		snprintf(why, n, gl_up ? "out of memory" : "the render node is not open");
		return NULL;
	}
	a[i++] = EGL_WIDTH;			a[i++] = w;
	a[i++] = EGL_HEIGHT;			a[i++] = h;
	a[i++] = EGL_LINUX_DRM_FOURCC_EXT;	a[i++] = (EGLint)fourcc;
	a[i++] = EGL_DMA_BUF_PLANE0_FD_EXT;	a[i++] = fd;
	a[i++] = EGL_DMA_BUF_PLANE0_OFFSET_EXT;	a[i++] = (EGLint)offset;
	a[i++] = EGL_DMA_BUF_PLANE0_PITCH_EXT;	a[i++] = (EGLint)pitch;
	if (modifier != DRM_FORMAT_MOD_INVALID) {
		a[i++] = EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT;	a[i++] = (EGLint)(modifier & 0xffffffffu);
		a[i++] = EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT;	a[i++] = (EGLint)(modifier >> 32);
	}
	a[i] = EGL_NONE;
	im->img = p_img_new(dpy, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, a);
	if (im->img == EGL_NO_IMAGE_KHR) {
		snprintf(why, n, "EGL import of a %dx%d %.4s buffer, modifier 0x%llx: egl 0x%x", w, h,
			 (const char *)&fourcc, (unsigned long long)modifier, eglGetError());
		free(im);
		return NULL;
	}
	im->tex = texture(im->img, 0);
	im->w = w;
	im->h = h;

	return im;
}

/* wl_shm: a texture the pixels are copied into, for test clients (G6) - the slow way, never Kodi's */
struct gl_image *gl_image_shm(void)
{
	struct gl_image *im = gl_up && has_ext((const char *)glGetString(GL_EXTENSIONS),
					      "GL_EXT_texture_format_BGRA8888") ? image_new() : NULL;

	if (!im)
		return NULL;
	im->img = EGL_NO_IMAGE_KHR;
	glGenTextures(1, &im->tex);
	glActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D, im->tex);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

	return im;
}

/* XRGB/ARGB8888 is B, G, R, X in memory: BGRA as GLES uploads it; GLES2 has no row length, so a padded
 * line goes up line by line */
bool gl_image_upload(struct gl_image *im, const void *px, int w, int h, int stride, char *why, size_t n)
{
	int y;

	glActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D, im->tex);
	if (w != im->w || h != im->h) {
		glTexImage2D(GL_TEXTURE_2D, 0, GL_BGRA_EXT, w, h, 0, GL_BGRA_EXT, GL_UNSIGNED_BYTE, NULL);
		im->w = w;
		im->h = h;
	}
	if (stride == w * 4)
		glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_BGRA_EXT, GL_UNSIGNED_BYTE, px);
	else
		for (y = 0; y < h; y++)
			glTexSubImage2D(GL_TEXTURE_2D, 0, 0, y, w, 1, GL_BGRA_EXT, GL_UNSIGNED_BYTE,
					(const unsigned char *)px + (size_t)y * (size_t)stride);
	if (glGetError())
		return oops(why, n, "wl_shm upload");
	return true;
}

int gl_image_width(const struct gl_image *im)
{
	return im->w;
}

int gl_image_height(const struct gl_image *im)
{
	return im->h;
}

bool gl_image_stale(const struct gl_image *im)
{
	return im->gen != gl_gen || !gl_up;
}

void gl_image_free(struct gl_image *im)
{
	if (!im)
		return;
	if (!gl_image_stale(im)) {
		glDeleteTextures(1, &im->tex);
		if (im->img != EGL_NO_IMAGE_KHR)
			p_img_del(dpy, im->img);
	}
	free(im);
}

/* one pass of the client's picture into one plane, the soft border over it as for the ring */
static void client_pass(GLuint fbo, int fw, int fh, float c0, float c1, struct pass_state *p,
			struct pass_state *edge, GLuint tex, const float m[16])
{
	int e[2];
	float ef[2];

	gl_edge_mask(panel_w, panel_h, edge_px, e);
	ef[0] = (float)e[0];
	ef[1] = (float)e[1];
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glViewport(0, 0, (GLsizei)fw, (GLsizei)fh);
	glClearColor(c0, c1, 0, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	pass_use(p, m, ef);
	glActiveTexture(GL_TEXTURE0);
	glBindTexture(GL_TEXTURE_2D, tex);
	quad_use();
	glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
	if (e[0] > 0)
		edge_draw(edge, e, m);
}

/* the client's frame: Y at full size, CbCr at half, video black around the quad (letterbox and keystone alike) */
bool gl_draw_client(int target_index, const struct gl_image *im, const float m[16], char *why, size_t n)
{
	GLenum err;

	client_pass(target[target_index].fbo[0], (int)panel_w, (int)panel_h, 16.0f / 255.0f, 0.0f,
		    &pass_rgb_y, &pass_edge_y, im->tex, m);
	client_pass(target[target_index].fbo[1], (int)panel_w / 2, (int)panel_h / 2, 128.0f / 255.0f,
		    128.0f / 255.0f, &pass_rgb_c, &pass_edge_c, im->tex, m);
	err = glGetError();
	if (err) {
		snprintf(why, n, "client draw: gl 0x%x", err);
		return false;
	}
	return true;
}

/* the three panel buffers' images, FBOs and renderbuffers: the claim they belong to is about to go */
void gl_targets_drop(void)
{
	int i, k;

	for (i = 0; i < WARP_TARGETS; i++) {
		for (k = 0; k < 2; k++) {
			if (target[i].fbo[k])
				glDeleteFramebuffers(1, &target[i].fbo[k]);
			if (target[i].rb[k])
				glDeleteRenderbuffers(1, &target[i].rb[k]);
			if (target[i].img[k] && p_img_del)
				p_img_del(dpy, target[i].img[k]);
		}
		memset(&target[i], 0, sizeof(target[i]));
	}
}

void gl_close(void)
{
	if (check_fbo) {
		glDeleteFramebuffers(1, &check_fbo);
		glDeleteTextures(1, &check_tex);
		check_fbo = check_tex = 0;
		free(check_a);
		free(check_b);
		check_a = check_b = NULL;
	}
	gl_source_drop();
	gl_targets_drop();
	if (ring_vbo)
		glDeleteBuffers(1, &ring_vbo);
	if (quad_vbo)
		glDeleteBuffers(1, &quad_vbo);
	if (dpy != EGL_NO_DISPLAY) {
		eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
		eglTerminate(dpy);
	}
	dpy = EGL_NO_DISPLAY;
	ctx = EGL_NO_CONTEXT;
	prog_warp = prog_pattern = prog_text = prog_luma = prog_chroma = 0;
	font_tex = 0;
	quad_vbo = 0;
	quad_bound = false;
	memset(&pass_luma, 0, sizeof(pass_luma));
	memset(&pass_chroma, 0, sizeof(pass_chroma));
	memset(&pass_edge_y, 0, sizeof(pass_edge_y));
	memset(&pass_edge_c, 0, sizeof(pass_edge_c));
	memset(&pass_rgb_y, 0, sizeof(pass_rgb_y));
	memset(&pass_rgb_c, 0, sizeof(pass_rgb_c));
	prog_edge_y = prog_edge_c = prog_rgb_y = prog_rgb_c = 0;
	gl_up = false;
	gl_gen++;
	ring_vbo = 0;
	snprintf(renderer, sizeof(renderer), "not opened");
}
