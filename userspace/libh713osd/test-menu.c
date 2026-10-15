// SPDX-License-Identifier: GPL-2.0
/*
 * test-menu - host test of the launcher's drawing (osd.c, "The menu"): the bands tile the column, a band repainted
 * alone gives the same pixels as a full draw (the invariant h713-osd's incremental redraw lives on), a move of the
 * selection touches two bands only, the pill is where the mock-up puts it, nothing is drawn right of the column.
 * The font is OSD_TEST_FONT, else OSD_FONT; without one: skipped (exit 77).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "osd.h"

static int fails;

#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

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
	int box[OSD_LAUNCHER_ROWS + 3][4], n = osd_launcher_bands(c, l, box);

	memset(c->px, 0, (size_t)c->h * c->stride * 4);
	for (int b = 0; b < n; b++)
		osd_launcher_draw(c, l, b);
}

/* the bounding box of the pixels whose alpha exceeds a in the rectangle */
static int dark_rows(const struct osd_canvas *c, int x, int y0, int y1, int a)
{
	int n = 0;

	for (int y = y0; y < y1; y++)
		n += (int)(c->px[(size_t)y * c->stride + x] >> 24) > a;
	return n;
}

/* the bands, sorted by their top, lie edge to edge from the top of the canvas to its bottom, none empty but the gap */
static void tiles(int box[][4], int n, int h, const char *what)
{
	int order[OSD_LAUNCHER_ROWS + 3], at = 0;

	for (int k = 0; k < n; k++)
		order[k] = k;
	for (int i = 1; i < n; i++)
		for (int j = i; j > 0 && box[order[j]][1] < box[order[j - 1]][1]; j--) {
			int x = order[j];

			order[j] = order[j - 1], order[j - 1] = x;
		}
	for (int i = 0; i < n; i++) {
		if (!box[order[i]][3])
			continue;
		CHECK(box[order[i]][1] == at, "%s: band %d starts at %d, not where the one before ended (%d)", what, order[i], box[order[i]][1], at);
		at = box[order[i]][1] + box[order[i]][3];
	}
	CHECK(at == h, "%s: the bands end at %d of %d", what, at, h);
}

static void run(int w, int h)
{
	struct osd_canvas a = { .w = w, .h = h, .stride = w }, b = a;
	struct osd_launcher l = mk(1, 6), l2 = mk(2, 6);
	int box[OSD_LAUNCHER_ROWS + 3][4], n, same = 0;
	double u = h / 1080.0;

	a.px = calloc((size_t)w * h, 4);
	b.px = calloc((size_t)w * h, 4);

	n = osd_launcher_bands(&a, &l, box);
	CHECK(n == 9, "six rows are nine bands (header, six rows, foot, gap), got %d", n);
	tiles(box, n, h, "six rows");
	CHECK(box[8][3] > 0, "Standby is apart from the five rows above: a gap of %d rows", box[8][3]);
	for (int k = 1; k <= 6; k++)
		CHECK(box[k][3] >= (int)(123 * u) && box[k][3] <= (int)(125 * u) + 1, "row band %d is 124 units high: %d", k, box[k][3]);
	CHECK(box[0][2] >= (int)(699 * u) && box[0][2] <= (int)(701 * u) + 1, "the column is 700 units wide: %d", box[0][2]);

	/* all bands = the launcher; a second pass over every band changes nothing (scrim replaces, the row is mixed once) */
	full(&a, &l);
	for (int k = n - 1; k >= 0; k--)
		osd_launcher_draw(&a, &l, k);
	full(&b, &l);
	CHECK(!memcmp(a.px, b.px, (size_t)w * h * 4), "a second pass over the bands in reverse order changed pixels");

	/* a move of the selection from row 1 to row 2: repaint bands 2 and 3 only, as a full draw of the new state; the gap band, once */
	full(&a, &l);
	osd_launcher_draw(&a, &l2, 2);
	osd_launcher_draw(&a, &l2, 3);
	full(&b, &l2);
	CHECK(!memcmp(a.px, b.px, (size_t)w * h * 4), "two bands repainted differ from a full draw");
	for (int y = 0; y < h; y++)
		for (int x = 0; x < w; x++)
			same += a.px[(size_t)y * w + x] != b.px[(size_t)y * w + x];
	CHECK(!same, "%d pixels differ", same);

	/* the move changed those two bands and no other */
	full(&a, &l);
	full(&b, &l2);
	for (int k = 0; k < n; k++) {
		int diff = 0;

		for (int y = box[k][1]; y < box[k][1] + box[k][3]; y++)
			diff += memcmp(a.px + (size_t)y * w, b.px + (size_t)y * w, (size_t)w * 4) != 0;
		CHECK((k == 2 || k == 3) == (diff > 0), "band %d: %d rows differ", k, diff);
		if (k == 2 || k == 3)
			CHECK(box[k][3] <= (int)(125 * u) + 1, "a move repaints bands of 124 units, not %d rows", box[k][3]);
	}

	/* the pill of the chosen row: a white outline at x = 118 units and 638, round ends; rows not chosen have none */
	full(&a, &l);
	{
		int y = (int)((194 + 124 + 52) * u);		/* the middle of row 1's pill (top 318 = 194 + 124) */
		int xl = (int)(118 * u), xr = (int)(638 * u);
		uint32_t pl = a.px[(size_t)y * w + xl], pm = a.px[(size_t)y * w + (int)(380 * u)];

		CHECK((pl >> 24) > 200 && (pl >> 16 & 255) > 200, "the outline at the left end is bright: %08x", pl);
		CHECK((a.px[(size_t)y * w + xr] >> 24) > 200, "the outline at the right end: %08x", a.px[(size_t)y * w + xr]);
		CHECK((pm >> 24) > 180 && (pm >> 16 & 255) < 40, "inside the pill it is dark, 0.72 over the scrim (about 0.78): %08x", pm);
		CHECK((a.px[(size_t)((194 + 52) * u) * w + (int)(500 * u)] >> 24) < 150, "no pill on row 0");
	}

	/* nothing right of the column, and the scrim falls off: alpha at the left edge > in the middle > at the end */
	for (int y = 0; y < h; y += 7)
		for (int x = (int)(702 * u); x < w; x += 11)
			if (a.px[(size_t)y * w + x]) {
				CHECK(0, "a pixel right of the column at %d, %d: %08x", x, y, a.px[(size_t)y * w + x]);
				y = h, x = w;
			}
	CHECK((a.px[(size_t)(100 * u) * w + 1] >> 24) > 170 && (a.px[(size_t)(100 * u) * w + (int)(315 * u)] >> 24) < 90 &&
	      (a.px[(size_t)(100 * u) * w + (int)(690 * u)] >> 24) < 6, "the scrim: 0.70 at the edge, 0.25 at 315, ~0 at the end");
	CHECK(dark_rows(&a, 1, 0, h, 100) == h, "the scrim covers the left edge from top to bottom");

	/* three rows (the rows of package H): HDMI and Kodi at the top, Standby alone at the foot */
	l = mk(0, 3);
	n = osd_launcher_bands(&a, &l, box);
	CHECK(n == 6, "three rows are six bands, got %d", n);
	tiles(box, n, h, "three rows");
	full(&a, &l);
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
	printf(fails ? "%d failed\n" : "all passed\n", fails);
	return fails != 0;
}
