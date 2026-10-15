// SPDX-License-Identifier: GPL-2.0
/*
 * test-text - host test of osd_text (text.c): widths, where the pixels land, clipping, the straight-alpha mix, bad
 * UTF-8. The font is OSD_TEST_FONT, else OSD_FONT; without one the test says so and exits 77 (skipped).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "osd.h"

static int fails;

#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* the bounding box of the pixels with alpha in the canvas */
static int bbox(const struct osd_canvas *c, int b[4])
{
	int n = 0;

	b[0] = c->w, b[1] = c->h, b[2] = b[3] = -1;
	for (int y = 0; y < c->h; y++)
		for (int x = 0; x < c->w; x++)
			if (c->px[(size_t)y * c->stride + x] >> 24) {
				b[0] = x < b[0] ? x : b[0], b[1] = y < b[1] ? y : b[1];
				b[2] = x > b[2] ? x : b[2], b[3] = y > b[3] ? y : b[3];
				n++;
			}
	return n;
}

int main(void)
{
	const char *font = getenv("OSD_TEST_FONT") ? getenv("OSD_TEST_FONT") : OSD_FONT;
	struct osd_canvas c = { .w = 640, .h = 120, .stride = 640 };
	int b[4], n;
	double w38, w19, w;

	c.px = calloc((size_t)c.w * c.h, 4);
	CHECK(osd_text_width("HDMI", 38) == 0, "a width without a font must be 0");
	if (osd_font_open("/nonexistent/font.ttf") == 0) {
		printf("FAIL: a missing font opened\n");
		return 1;
	}
	if (osd_font_open(font)) {
		printf("skipped: no font at %s (set OSD_TEST_FONT)\n", font);
		return 77;
	}
	CHECK(osd_font_open("/nonexistent/font.ttf") == 0, "a second open is a no-op");

	w38 = osd_text_width("HDMI input", 38);
	w19 = osd_text_width("HDMI input", 19);
	CHECK(w38 > 100 && w38 < 400, "HDMI input at 38 px is %.1f wide", w38);
	CHECK(w38 / w19 > 1.95 && w38 / w19 < 2.05, "width scales with the size: %.1f / %.1f", w38, w19);
	CHECK(osd_text_width("", 38) == 0, "an empty string has no width");
	CHECK(osd_text_width("\xc2\xb7", 38) > 0, "the middle dot has a width");

	/* where the pixels land: left end near x, baseline at 80, ascenders above it, descenders below */
	w = osd_text(&c, "Kodi", 100, 80, 38, 0xfafafa, 1.0f, 0);
	n = bbox(&c, b);
	CHECK(n > 300, "Kodi drew %d pixels", n);
	CHECK(b[0] >= 98 && b[0] <= 106, "left edge %d", b[0]);
	CHECK(b[2] <= 100 + (int)w + 2 && b[2] >= 100 + (int)w - 8, "right edge %d for an advance of %.1f", b[2], w);
	CHECK(b[3] <= 81 && b[3] >= 78, "K, o, d, i sit on the baseline: bottom %d", b[3]);
	CHECK(b[1] >= 80 - 40 && b[1] <= 80 - 24, "top of the d %d", b[1]);
	CHECK(c.px[(size_t)b[1] * c.w + b[0]] >> 24 <= 255, "alpha in range");

	/* straight-alpha mix: white at 50 % over an opaque dark red keeps alpha 255 and lightens the glyph's core */
	for (size_t i = 0; i < (size_t)c.w * c.h; i++)
		c.px[i] = 0xff600000;
	osd_text(&c, "H", 50, 80, 60, 0xffffff, 0.5f, 0);
	{
		unsigned r = 0, cnt = 0;

		for (size_t i = 0; i < (size_t)c.w * c.h; i++) {
			CHECK((c.px[i] >> 24) == 255, "the opaque canvas stays opaque");
			if ((c.px[i] >> 16 & 255) > 0x60) {
				r = (c.px[i] >> 16 & 255) > r ? (c.px[i] >> 16 & 255) : r;
				cnt++;
			}
		}
		CHECK(cnt > 100 && r > 0xb0 - 8 && r < 0xb0 + 8, "50 %% white over 0x60 is about 0xb0: %u (%u pixels)", r, cnt);
	}

	/* max_w stops at a glyph boundary and the advance is what fits */
	memset(c.px, 0, (size_t)c.w * c.h * 4);
	w = osd_text(&c, "HDMI input", 10, 80, 38, 0xffffff, 1.0f, 100);
	n = bbox(&c, b);
	CHECK(w <= 100 && w > 60, "max_w 100 gave an advance of %.1f", w);
	CHECK(b[2] <= 10 + 100, "drawn up to %d", b[2]);

	/* clipping and bad input must not crash: off every edge, malformed UTF-8, NULL */
	osd_text(&c, "Clip", -30, 20, 80, 0xffffff, 1.0f, 0);
	osd_text(&c, "Clip", 600, 200, 80, 0xffffff, 1.0f, 0);
	osd_text(&c, "\xff\xc3(\xe2\x82 x", 10, 80, 30, 0xffffff, 1.0f, 0);
	osd_text(&c, NULL, 10, 80, 30, 0xffffff, 1.0f, 0);
	osd_text(&c, "x", 10, 80, 0, 0xffffff, 1.0f, 0);

	printf(fails ? "%d failed\n" : "all passed\n", fails);
	free(c.px);
	return fails != 0;
}
