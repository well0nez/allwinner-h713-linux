// SPDX-License-Identifier: GPL-2.0
/*
 * libh713osd text - see osd.h ("Text"). One font face, loaded once; a string is laid out left to right with the
 * glyphs' own advances (unhinted, so at 38 px a word is the width the designer drew, not rounded per letter) and
 * each glyph's coverage is mixed over the canvas in straight alpha, as osd_draw mixes its lines. FreeType renders
 * the glyphs; nothing is cached, because the strings are short and drawn when something changes, not per frame.
 */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#include <ft2build.h>
#include FT_FREETYPE_H

#include "osd.h"

static FT_Library ft_lib;
static FT_Face ft_face;

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
	return 0;
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
	uint32_t v = *p;
	double A = (v >> 24) / 255.0, out = a + A * (1 - a), r, g, b;

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
	uint32_t cp;

	if (!ft_face || !utf8 || px < 1 || FT_Set_Char_Size(ft_face, 0, (FT_F26Dot6)(px * 64 + 0.5), 72, 72))
		return 0;
	while ((cp = next_cp(&s))) {
		FT_UInt gi = FT_Get_Char_Index(ft_face, cp);
		double adv;
		int gx;

		if (FT_Load_Glyph(ft_face, gi, FT_LOAD_NO_HINTING | (c ? FT_LOAD_RENDER : 0)))
			continue;
		adv = ft_face->glyph->linearHoriAdvance / 65536.0;
		if (prev && gi && FT_HAS_KERNING(ft_face)) {
			FT_Vector k;

			if (!FT_Get_Kerning(ft_face, prev, gi, FT_KERNING_UNFITTED, &k))
				pen += k.x / 64.0;
		}
		if (max_w > 0 && pen + adv > max_w)
			break;
		if (c) {
			const FT_Bitmap *bm = &ft_face->glyph->bitmap;

			gx = (int)floor(x + pen) + ft_face->glyph->bitmap_left;
			for (unsigned row = 0; row < bm->rows; row++) {
				int py = (int)floor(baseline) - ft_face->glyph->bitmap_top + (int)row;

				if (py < 0 || py >= c->h)
					continue;
				for (unsigned col = 0; col < bm->width; col++) {
					int pxx = gx + (int)col;
					unsigned cov = bm->buffer[row * bm->pitch + col];

					if (cov && pxx >= 0 && pxx < c->w)
						mix(c->px + (size_t)py * c->stride + pxx, rgb, cov / 255.0 * alpha);
				}
			}
		}
		pen += adv;
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
