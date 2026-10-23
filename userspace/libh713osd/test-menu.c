// SPDX-License-Identifier: GPL-2.0
/*
 * test-menu - host test of the launcher's drawing (osd.c, "The menu"): the tiles cover the canvas exactly once, the page is opaque,
 * nothing but the ground lies in the outer 5 % (the safe margin), the pill is the lit pill's colour, a tile repainted alone gives the
 * same pixels as a full draw (the invariant h713-osd's incremental redraw lives on), a move of the selection touches two tiles.
 * The font is OSD_TEST_FONT, else OSD_FONT; without one: skipped (exit 77).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "osd.h"

static int fails;

#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

#define MAXT (2 * (OSD_LAUNCHER_ROWS + 3))

static struct osd_launcher mk(int sel, int n)
{
	struct osd_launcher l = { "20:47 \xc2\xb7 HDMI 1080p60", n, sel, { { OSD_ICON_HDMI, "HDMI input", 0 },
		{ OSD_ICON_FILM, "Kodi", 0 }, { OSD_ICON_GLOBE, "Browser", 0 }, { OSD_ICON_DESK, "Desktop", 0 },
		{ OSD_ICON_SLIDERS, "Settings", 0 }, { OSD_ICON_POWER, "Standby", 1 } } };

	if (n == 3)
		l.row[2] = l.row[5];
	return l;
}

static void full(struct osd_canvas *c, const struct osd_launcher *l)
{
	int box[MAXT][4], n = osd_launcher_bands(c, l, box);

	memset(c->px, 0, (size_t)c->h * c->stride * 4);
	for (int b = 0; b < n; b++)
		osd_launcher_draw(c, l, b);
}

/* every pixel is in exactly one tile (an empty tile is skipped) */
static void tiles(const struct osd_canvas *c, int box[][4], int n, const char *what)
{
	unsigned char *seen = calloc((size_t)c->w * c->h, 1);
	size_t bad = 0, area = 0;

	for (int k = 0; k < n; k++)
		for (int y = box[k][1]; y < box[k][1] + box[k][3]; y++)
			for (int x = box[k][0]; x < box[k][0] + box[k][2]; x++) {
				if (x < 0 || y < 0 || x >= c->w || y >= c->h || seen[(size_t)y * c->w + x]++)
					bad++;
				area++;
			}
	CHECK(!bad, "%s: %zu pixels outside the canvas or in two tiles", what, bad);
	CHECK(area == (size_t)c->w * c->h, "%s: the tiles cover %zu of %d pixels", what, area, c->w * c->h);
	free(seen);
}

/* the page is opaque, and nothing but the ground lies in the safe margin */
static void page(const struct osd_canvas *c, const char *what)
{
	int sx0 = c->w * OSD_SAFE_PERCENT / 100, sx1 = c->w - sx0, sy0 = c->h * OSD_SAFE_PERCENT / 100, sy1 = c->h - sy0;
	size_t clear = 0, outside = 0, ink = 0;

	for (int y = 0; y < c->h; y++)
		for (int x = 0; x < c->w; x++) {
			uint32_t v = c->px[(size_t)y * c->stride + x];

			clear += (v >> 24) != 255;
			if (v != OSD_PAGE_GROUND) {
				ink++;
				outside += x < sx0 || x >= sx1 || y < sy0 || y >= sy1;
			}
		}
	CHECK(!clear, "%s: %zu pixels are not opaque", what, clear);
	CHECK(!outside, "%s: %zu pixels of ink lie in the outer %d %%", what, outside, OSD_SAFE_PERCENT);
	CHECK(ink > (size_t)c->w * c->h / 200, "%s: only %zu pixels of ink - nothing drawn?", what, ink);
}

static void run(int w, int h)
{
	struct osd_canvas a = { .w = w, .h = h, .stride = w }, b = a;
	struct osd_launcher l = mk(1, 6), l2 = mk(2, 6);
	int box[MAXT][4], n, same = 0;
	double u = h / 1080.0;
	char what[64];

	a.px = calloc((size_t)w * h, 4);
	b.px = calloc((size_t)w * h, 4);

	n = osd_launcher_bands(&a, &l, box);
	CHECK(n == 18, "six rows are 9 bands, 18 tiles (left and right), got %d", n);
	tiles(&a, box, n, "six rows");
	CHECK(box[8][3] > 0, "Standby is apart from the five rows above: a gap of %d rows", box[8][3]);
	for (int k = 1; k <= 6; k++)
		CHECK(box[k][3] >= (int)(123 * u) && box[k][3] <= (int)(125 * u) + 1, "row band %d is 124 units high: %d", k, box[k][3]);
	CHECK(box[0][2] >= (int)(699 * u) && box[0][2] <= (int)(701 * u) + 1, "the column is 700 units wide: %d", box[0][2]);
	CHECK(box[9][0] == box[0][2] && box[9][0] + box[9][2] == w, "the right part starts where the column ends and runs to the edge");

	/* the page: opaque, the ground colour, content inside the safe margin - for every selection, and for the Kodi image's three rows */
	for (int sel = 0; sel < 6; sel++) {
		struct osd_launcher ls = mk(sel, 6);

		full(&a, &ls);
		snprintf(what, sizeof(what), "%dx%d six rows, row %d chosen", w, h, sel);
		page(&a, what);
	}
	for (int sel = 0; sel < 3; sel++) {
		struct osd_launcher ls = mk(sel, 3);

		full(&a, &ls);
		snprintf(what, sizeof(what), "%dx%d three rows, row %d chosen", w, h, sel);
		page(&a, what);
	}
	full(&a, &l);
	CHECK(a.px[(size_t)(h / 2) * w + w - 5] == OSD_PAGE_GROUND && a.px[5] == OSD_PAGE_GROUND && a.px[(size_t)(h - 3) * w + 3] == OSD_PAGE_GROUND,
	      "the ground is 0x%08x everywhere there is no ink", OSD_PAGE_GROUND);

	/* all tiles = the page; a second pass over the tiles in reverse order changes nothing (the ground replaces, the row is mixed once) */
	for (int k = n - 1; k >= 0; k--)
		osd_launcher_draw(&a, &l, k);
	full(&b, &l);
	CHECK(!memcmp(a.px, b.px, (size_t)w * h * 4), "a second pass over the tiles in reverse order changed pixels");

	/* a move of the selection from row 1 to row 2: repaint the two row tiles only, as a full draw of the new state */
	full(&a, &l);
	osd_launcher_draw(&a, &l2, 2);
	osd_launcher_draw(&a, &l2, 3);
	full(&b, &l2);
	for (int y = 0; y < h; y++)
		for (int x = 0; x < w; x++)
			same += a.px[(size_t)y * w + x] != b.px[(size_t)y * w + x];
	CHECK(!same, "two tiles repainted differ from a full draw in %d pixels", same);

	/* the move changed those two tiles and no other */
	full(&a, &l);
	full(&b, &l2);
	for (int k = 0; k < n; k++) {
		int diff = 0;

		for (int y = box[k][1]; y < box[k][1] + box[k][3]; y++)
			diff += memcmp(a.px + (size_t)y * w + box[k][0], b.px + (size_t)y * w + box[k][0], (size_t)box[k][2] * 4) != 0;
		CHECK((k == 2 || k == 3) == (diff > 0), "tile %d: %d rows differ", k, diff);
		if (k == 2 || k == 3)
			CHECK(box[k][3] <= (int)(125 * u) + 1 && box[k][2] <= (int)(701 * u) + 1, "a move repaints tiles of 700 x 124 units, not %d x %d", box[k][2], box[k][3]);
	}

	/* the pill of the chosen row: the lit pill's colour inside (opaque), a white outline at x = 118 units and 638, the other rows have none */
	full(&a, &l);
	{
		int y = (int)((194 + 124 + 52) * u);		/* the middle of row 1's pill (top 318 = 194 + 124) */
		int xl = (int)(118 * u), xr = (int)(638 * u);
		uint32_t pl = a.px[(size_t)y * w + xl], pm = a.px[(size_t)y * w + (int)(560 * u)], po = a.px[(size_t)((194 + 52) * u) * w + (int)(560 * u)];

		unsigned lmax = 0, rmax = 0;

		for (int d = -2; d <= 2; d++) {		/* the outline is thinner at 720p and 540p (3 px at 1080p): the brightest of a few pixels across it */
			lmax = (a.px[(size_t)y * w + xl + d] >> 16 & 255) > lmax ? (a.px[(size_t)y * w + xl + d] >> 16 & 255) : lmax;
			rmax = (a.px[(size_t)y * w + xr + d] >> 16 & 255) > rmax ? (a.px[(size_t)y * w + xr + d] >> 16 & 255) : rmax;
		}
		(void)pl;
		CHECK(lmax > 120, "the outline at the left end is bright: %u", lmax);
		CHECK(rmax > 120, "the outline at the right end is bright: %u", rmax);
		CHECK(pm == (0xff000000u | OSD_PAGE_PILL), "inside the pill it is the lit pill's colour %08x, not %08x", 0xff000000u | OSD_PAGE_PILL, pm);
		CHECK(po == OSD_PAGE_GROUND, "no pill on row 0: %08x", po);
	}

	/* three rows (the Kodi image's rows): HDMI and Kodi at the top, Standby alone at the foot */
	l = mk(0, 3);
	n = osd_launcher_bands(&a, &l, box);
	CHECK(n == 12, "three rows are six bands, twelve tiles, got %d", n);
	tiles(&a, box, n, "three rows");
	CHECK(box[3][1] <= (int)(844 * u) && box[3][1] + box[3][3] >= (int)(948 * u), "Standby's band holds its pill: %d+%d", box[3][1], box[3][3]);
	CHECK(box[5][3] > (int)(300 * u), "the gap between Kodi and Standby is its own band: %d rows", box[5][3]);
	free(a.px);
	free(b.px);
}

int main(void)
{
	const char *font = getenv("OSD_TEST_FONT") ? getenv("OSD_TEST_FONT") : OSD_FONT;

	CHECK(osd_icon_by_name("film") == OSD_ICON_FILM && osd_icon_by_name("power") == OSD_ICON_POWER &&
	      osd_icon_by_name("sliders") == OSD_ICON_SLIDERS && osd_icon_by_name("globe") == OSD_ICON_GLOBE &&
	      osd_icon_by_name("desk") == OSD_ICON_DESK && osd_icon_by_name("hdmi") == OSD_ICON_HDMI, "icon names");
	CHECK(osd_icon_by_name("nope") < 0 && osd_icon_by_name("") < 0 && osd_icon_by_name(NULL) < 0, "unknown icon names");
	if (osd_font_open(font)) {
		printf("skipped: no font at %s (set OSD_TEST_FONT)\n", font);
		return fails ? 1 : 77;
	}
	run(1920, 1080);
	run(1280, 720);
	run(960, 540);
	printf(fails ? "%d failed\n" : "all passed\n", fails);
	return fails != 0;
}
