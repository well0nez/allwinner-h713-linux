// SPDX-License-Identifier: GPL-2.0
/*
 * libh713osd text - see osd.h ("Text"). One font face, loaded once; a string is laid out left to right with the
 * glyphs' own advances (unhinted, so at 38 px a word is the width the designer drew, not rounded per letter) and
 * each glyph's coverage is mixed over the canvas in straight alpha, as osd_draw mixes its lines. FreeType renders
 * the glyphs; each rendered glyph (its coverage and advance, per size) is kept in a small table: a page of the settings
 * draws the same labels at every move, and rendering them again cost about as much as drawing the page (16.10.2026).
 */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <ft2build.h>
#include FT_FREETYPE_H

#include "osd.h"

static FT_Library ft_lib;
static FT_Face ft_face;

/* the rendered glyphs, direct-mapped by (glyph, size); a collision replaces the older one */
#define GCACHE 512
static struct glyph {
	FT_UInt gi;
	FT_F26Dot6 size;
	int left, top;
	unsigned width, rows;
	double adv;
	unsigned char *cov;		/* width x rows, tight; NULL: the slot is free */
} gcache[GCACHE];
static FT_F26Dot6 cur_size;		/* the size set in the face; 0: none */

int osd_font_open(const char *path)
{
	if (ft_face)
		return 0;
	if (FT_Init_FreeType(&ft_lib))
		return -1;
	if (FT_New_Face(ft_lib, path, 0, &ft_face) || FT_Select_Charmap(ft_face, FT_ENCODING_UNICODE)) {
		if (ft_face)
			FT_Done_Face(ft_face);
		FT_Done_FreeType(ft_lib);
		ft_face = NULL, ft_lib = NULL;
		return -1;
	}
	cur_size = 0;
	return 0;
}

/* the glyph at this size: from the table, else rendered once; NULL when FreeType refuses it */
static const struct glyph *glyph_at(FT_UInt gi, FT_F26Dot6 size)
{
	struct glyph *g = &gcache[((size_t)gi * 31 + (size_t)size) % GCACHE];
	const FT_Bitmap *bm;

	if (g->cov && g->gi == gi && g->size == size)
		return g;
	if (FT_Load_Glyph(ft_face, gi, FT_LOAD_NO_HINTING | FT_LOAD_RENDER))
		return NULL;
	bm = &ft_face->glyph->bitmap;
	free(g->cov);
	g->cov = malloc((size_t)bm->width * bm->rows + 1);
	if (!g->cov)
		return NULL;
	for (unsigned row = 0; row < bm->rows; row++)
		memcpy(g->cov + (size_t)row * bm->width, bm->buffer + (size_t)row * bm->pitch, bm->width);
	g->gi = gi, g->size = size;
	g->left = ft_face->glyph->bitmap_left, g->top = ft_face->glyph->bitmap_top;
	g->width = bm->width, g->rows = bm->rows;
	g->adv = ft_face->glyph->linearHoriAdvance / 65536.0;
	return g;
}

/* the next code point of a UTF-8 string, advancing *s; a malformed byte counts as U+FFFD, the end as 0 */
static uint32_t next_cp(const unsigned char **s)
{
	const unsigned char *p = *s;
	uint32_t c = *p;
	int more = c < 0x80 ? 0 : c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc0 ? 1 : -1;

	if (!c)
		return 0;
	if (more < 0) {
		*s = p + 1;
		return 0xfffd;
	}
	c = more == 0 ? c : c & (0x3f >> more);
	for (int i = 1; i <= more; i++) {
		if ((p[i] & 0xc0) != 0x80) {
			*s = p + i;
			return 0xfffd;
		}
		c = c << 6 | (p[i] & 0x3f);
	}
	*s = p + more + 1;
	return c;
}

/* one glyph's coverage over the canvas: straight alpha, "src over dst" */
static void mix(uint32_t *p, unsigned rgb, double a)
{
	uint32_t v;
	double A, out, r, g, b;

	if (a >= 1.0) {			/* whole coverage: the colour itself (out = 1, the old colour weighs 0) */
		*p = 0xff000000u | rgb;
		return;
	}
	v = *p;
	A = (v >> 24) / 255.0, out = a + A * (1 - a);
	if (out <= 0)
		return;
	r = ((rgb >> 16 & 255) * a + (v >> 16 & 255) * A * (1 - a)) / out;
	g = ((rgb >> 8 & 255) * a + (v >> 8 & 255) * A * (1 - a)) / out;
	b = ((rgb & 255) * a + (v & 255) * A * (1 - a)) / out;
	*p = (uint32_t)(out * 255 + 0.5) << 24 | (uint32_t)(r + 0.5) << 16 | (uint32_t)(g + 0.5) << 8 | (uint32_t)(b + 0.5);
}

/* the layout loop of both public functions: draws when c is not NULL; returns the advance of what fits */
static double run(struct osd_canvas *c, const char *utf8, double x, double baseline, double px, unsigned rgb,
		  float alpha, double max_w)
{
	const unsigned char *s = (const unsigned char *)utf8;
	double pen = 0;
	FT_UInt prev = 0;
	FT_F26Dot6 size = (FT_F26Dot6)(px * 64 + 0.5);
	uint32_t cp;

	if (!ft_face || !utf8 || px < 1)
		return 0;
	if (size != cur_size) {
		cur_size = 0;
		if (FT_Set_Char_Size(ft_face, 0, size, 72, 72))
			return 0;
		cur_size = size;
	}
	while ((cp = next_cp(&s))) {
		FT_UInt gi = FT_Get_Char_Index(ft_face, cp);
		const struct glyph *g = glyph_at(gi, size);
		int gx;

		if (!g)
			continue;
		if (prev && gi && FT_HAS_KERNING(ft_face)) {
			FT_Vector k;

			if (!FT_Get_Kerning(ft_face, prev, gi, FT_KERNING_UNFITTED, &k))
				pen += k.x / 64.0;
		}
		if (max_w > 0 && pen + g->adv > max_w)
			break;
		if (c) {
			gx = (int)floor(x + pen) + g->left;
			for (unsigned row = 0; row < g->rows; row++) {
				int py = (int)floor(baseline) - g->top + (int)row;

				if (py < 0 || py >= c->h)
					continue;
				for (unsigned col = 0; col < g->width; col++) {
					int pxx = gx + (int)col;
					unsigned cov = g->cov[row * g->width + col];

					if (cov && pxx >= 0 && pxx < c->w)
						mix(c->px + (size_t)py * c->stride + pxx, rgb, cov / 255.0 * alpha);
				}
			}
		}
		pen += g->adv;
		prev = gi;
	}
	return pen;
}

double osd_text_width(const char *utf8, double px)
{
	return run(NULL, utf8, 0, 0, px, 0, 0, 0);
}

double osd_text(struct osd_canvas *c, const char *utf8, double x, double baseline, double px, unsigned rgb,
		float alpha, double max_w)
{
	return run(c, utf8, x, baseline, px, rgb, alpha, max_w);
}
