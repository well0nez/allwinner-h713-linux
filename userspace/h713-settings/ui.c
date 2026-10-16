// SPDX-License-Identifier: GPL-2.0
/*
 * The page, drawn into an ARGB canvas the way the mockup v2 shows it (the areas on the left, the rows on the
 * right, white lines), on an OPAQUE calm ground: over a picture a translucent page is unreadable (the owner, 15.10.).
 * Everything stays inside a safe margin of 5 % on each side (96 / 54 px at 1080p). While a value that is judged on the
 * picture is adjusted (the picture's sliders, the zoom, the corners) the page is only ONE pill at the foot over the real
 * picture (the mockup v1). Text is libh713osd's osd_text; the shapes are signed distance fields like the library's own.
 * A row is drawn alone when only it changed, so a key press costs one row.
 */
#define _GNU_SOURCE
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ui.h"

static struct osd_canvas *cv;
static double U, XOFF;			/* panel pixels per design pixel; the left margin of a panel wider than 16:9 */
static int bx0, by0, bx1, by1;		/* what this piece touched, in panel pixels */
static int nbox, rbox[MAXBOX][4];	/* the pieces so far, x y w h */

#define BRIGHT	0xffffffu
#define PILL	0x0e1110u		/* the overlays' pill, over the picture (72 %) */
#define PAGEPILL 0x1c2321u		/* the lit pill on the opaque page: a little lighter than the ground */
#define GROUND	0xff0b0e0du		/* the page's ground: opaque, dark in the tone of the pills */
#define SAFE_X0	96			/* 5 % of 1920 and of 1080, the design's units */
#define SAFE_X1	1824
#define SAFE_Y0	54
#define SAFE_Y1	1026

static double clampd(double v, double lo, double hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

static void touch(double x0, double y0, double x1, double y1)
{
	bx0 = (int)fmin(bx0, floor(clampd(x0 * U + XOFF, 0, cv->w)));
	by0 = (int)fmin(by0, floor(clampd(y0 * U, 0, cv->h)));
	bx1 = (int)fmax(bx1, ceil(clampd(x1 * U + XOFF, 0, cv->w)));
	by1 = (int)fmax(by1, ceil(clampd(y1 * U, 0, cv->h)));
}

/* straight alpha, mixed over what the canvas holds */
static void mix(int x, int y, unsigned rgb, float a)
{
	uint32_t *p = cv->px + (size_t)y * cv->stride + x, v;
	float da, oa, r, g, b;

	if (a <= 0)
		return;
	if (a == 1.0f) {		/* whole coverage: the colour itself, what the lines below come to (oa = 1, the old colour weighs 0) */
		*p = 0xff000000u | rgb;
		return;
	}
	v = *p;
	if (!(v >> 24)) {		/* over nothing: the colour with the coverage as its alpha (the division below gives the colour back, to the digit) */
		*p = (uint32_t)(a * 255 + 0.5f) << 24 | rgb;
		return;
	}
	da = (v >> 24) / 255.0f, oa = a + da * (1 - a);
	if (oa <= 0)
		return;
	r = (((rgb >> 16) & 255) * a + ((v >> 16) & 255) * da * (1 - a)) / oa;
	g = (((rgb >> 8) & 255) * a + ((v >> 8) & 255) * da * (1 - a)) / oa;
	b = ((rgb & 255) * a + (v & 255) * da * (1 - a)) / oa;
	*p = (uint32_t)(oa * 255 + 0.5f) << 24 | (uint32_t)(r + 0.5f) << 16 | (uint32_t)(g + 0.5f) << 8 | (uint32_t)(b + 0.5f);
}

static void clear_box(double x0, double y0, double x1, double y1, uint32_t argb)
{
	int xa = (int)clampd(x0 * U + XOFF, 0, cv->w), xb = (int)clampd(x1 * U + XOFF, 0, cv->w);
	int ya = (int)clampd(y0 * U, 0, cv->h), yb = (int)clampd(y1 * U, 0, cv->h);

	for (int y = ya; y < yb; y++)
		for (int x = xa; x < xb; x++)
			cv->px[(size_t)y * cv->stride + x] = argb;
	touch(x0, y0, x1, y1);
}

/* a rounded rectangle (a pill when r = hh): filled, and/or an outline of width lw drawn inside its edge */
static void rrect(double cx, double cy, double hw, double hh, double r, unsigned fill, float af, unsigned line, float al, double lw)
{
	double x = cx * U + XOFF, y = cy * U, w = hw * U, h = hh * U, rr = r * U, l = lw * U;

	/* deep inside (in the straight part, further from the edge than the outline reaches and the fade) the coverage is 1 and the outline's
	 * 0: a row's span of such pixels is the fill colour at once, without the distance. One pixel of safety on each side. */
	double deep = fmin(0, rr - l - 0.5), ex = w - rr + deep;

	for (int py = (int)fmax(0, y - h - 2); py < (int)fmin(cv->h, y + h + 2); py++) {
		int xa = (int)fmax(0, x - w - 2), xb = (int)fmin(cv->w, x + w + 2), sa = xb, sb = xb;

		if (af > 0 && ex > 0 && fabs(py + 0.5 - y) - h + rr <= deep) {
			sa = (int)ceil(x - ex - 0.5) + 1, sb = (int)floor(x + ex - 0.5) - 1;
			sa = sa < xa ? xa : sa, sb = sb > xb ? xb : sb;
			if (sb <= sa)
				sa = sb = xb;
		}
		for (int px = xa; px < xb; px++) {
			double dx, dy, d;

			if (px == sa) {
				for (int q = sa; q < sb; q++)
					mix(q, py, fill, af);
				px = sb - 1;
				continue;
			}
			dx = fabs(px + 0.5 - x) - w + rr, dy = fabs(py + 0.5 - y) - h + rr;
			/* in the straight part (both <= 0) the square root is of 0: the same distance without it */
			d = dx > 0 || dy > 0 ? sqrt(fmax(dx, 0) * fmax(dx, 0) + fmax(dy, 0) * fmax(dy, 0)) + fmin(fmax(dx, dy), 0) - rr
					     : fmax(dx, dy) - rr;

			if (af > 0 && d < 0.5)
				mix(px, py, fill, af * (float)clampd(0.5 - d, 0, 1));
			if (lw > 0 && d > -l - 0.5 && d < 0.5)	/* outside this band the outline's coverage is 0 */
				mix(px, py, line, al * (float)clampd(0.5 - (fabs(d + l / 2) - l / 2), 0, 1));
		}
	}
	touch(cx - hw - 2, cy - hh - 2, cx + hw + 2, cy + hh + 2);
}

/* a line with round ends (also a dot: both ends equal) */
static void stroke(double ax, double ay, double bx, double by, double w, unsigned rgb, float a)
{
	double x0 = ax * U + XOFF, y0 = ay * U, x1 = bx * U + XOFF, y1 = by * U, r = w * U / 2;
	double vx = x1 - x0, vy = y1 - y0, len2 = vx * vx + vy * vy;

	for (int py = (int)fmax(0, fmin(y0, y1) - r - 2); py < (int)fmin(cv->h, fmax(y0, y1) + r + 2); py++)
		for (int px = (int)fmax(0, fmin(x0, x1) - r - 2); px < (int)fmin(cv->w, fmax(x0, x1) + r + 2); px++) {
			double t = len2 > 0 ? clampd(((px + 0.5 - x0) * vx + (py + 0.5 - y0) * vy) / len2, 0, 1) : 0;
			double d = hypot(px + 0.5 - (x0 + t * vx), py + 0.5 - (y0 + t * vy)) - r;

			mix(px, py, rgb, a * (float)clampd(0.5 - d, 0, 1));
		}
	touch(fmin(ax, bx) - w, fmin(ay, by) - w, fmax(ax, bx) + w, fmax(ay, by) + w);
}

/* the mockup's "›": two strokes; dir +1 right, -1 left */
static void chevron(double cx, double cy, int dir, float a)
{
	stroke(cx - 6 * dir, cy - 12, cx + 6 * dir, cy, 4, BRIGHT, a);
	stroke(cx + 6 * dir, cy, cx - 6 * dir, cy + 12, 4, BRIGHT, a);
}

/* the width in the design's units (the library measures in panel pixels: at 720p they are two thirds of a design pixel) */
static double text_w(const char *s, double px)
{
	return osd_text_width(s, px * U) / U;
}

static double text_max;			/* a string may not run further than this from its left end (design px); 0: no limit */

/* align 0 left of x, 1 right-aligned at x; the baseline y; size in design pixels */
static void text(double x, double y, double size, float a, const char *s, int align)
{
	double w = text_w(s, size);

	osd_text(cv, s, (align ? x - w : x) * U + XOFF, y * U, size * U, BRIGHT, a, text_max * U);
	touch(align ? x - w - 2 : x - 2, y - size, align ? x + 2 : x + w + 2, y + size * 0.4);
}

/* the piece drawn so far is one rectangle to show; it joins one that lies within 24 rows of it (the pill of a row reaches
 * past the pitch), else it stands alone */
static void seal(void)
{
	int x0 = bx0, y0 = by0, x1 = bx1, y1 = by1;

	if (x1 <= x0 || y1 <= y0)
		return;
	bx0 = cv->w, by0 = cv->h, bx1 = by1 = 0;
	for (int i = 0; i < nbox; i++) {
		int *r = rbox[i];

		if (y0 <= r[1] + r[3] + 24 && y1 >= r[1] - 24) {
			int nx0 = x0 < r[0] ? x0 : r[0], ny0 = y0 < r[1] ? y0 : r[1];
			int nx1 = x1 > r[0] + r[2] ? x1 : r[0] + r[2], ny1 = y1 > r[1] + r[3] ? y1 : r[1] + r[3];

			r[0] = nx0, r[1] = ny0, r[2] = nx1 - nx0, r[3] = ny1 - ny0;
			return;
		}
	}
	if (nbox == MAXBOX) {		/* more pieces than places: into the last one */
		int *r = rbox[MAXBOX - 1], nx1 = x1 > r[0] + r[2] ? x1 : r[0] + r[2], ny1 = y1 > r[1] + r[3] ? y1 : r[1] + r[3];

		r[0] = x0 < r[0] ? x0 : r[0], r[1] = y0 < r[1] ? y0 : r[1];
		r[2] = nx1 - r[0], r[3] = ny1 - r[1];
		return;
	}
	rbox[nbox][0] = x0, rbox[nbox][1] = y0, rbox[nbox][2] = x1 - x0, rbox[nbox][3] = y1 - y0;
	nbox++;
}

int visible_rows(const struct area *a)
{
	int n = 0;

	for (int i = 0; i < a->n; i++)
		n += !a->row[i].hidden;
	return n;
}

struct row *visible_row(struct area *a, int k)
{
	for (int i = 0; i < a->n; i++)
		if (!a->row[i].hidden && !k--)
			return &a->row[i];
	return NULL;
}


/* --- the symbols of the areas: the mockup's 48-unit paths (round-capped lines, 3.2 wide), drawn into a coverage mask
 * with max() so that a joint is not drawn twice, then mixed once --------------------------------------------------- */

static float mask[160 * 160];
static int msz;				/* the mask's side in panel pixels */
static double mk;			/* panel pixels per symbol unit */

static void m_line(double x0, double y0, double x1, double y1)
{
	double r = 1.6 * mk, ax = x0 * mk, ay = y0 * mk, vx = x1 * mk - ax, vy = y1 * mk - ay, l2 = vx * vx + vy * vy;

	/* only the pixels within the line's reach (its box and the radius, one pixel of AA): the others are 0 and stay as they are */
	int xlo = (int)floor(fmin(ax, ax + vx) - r - 1), xhi = (int)ceil(fmax(ax, ax + vx) + r + 1);
	int ylo = (int)floor(fmin(ay, ay + vy) - r - 1), yhi = (int)ceil(fmax(ay, ay + vy) + r + 1);

	xlo = xlo < 0 ? 0 : xlo, ylo = ylo < 0 ? 0 : ylo;
	xhi = xhi > msz ? msz : xhi, yhi = yhi > msz ? msz : yhi;
	for (int y = ylo; y < yhi; y++)
		for (int x = xlo; x < xhi; x++) {
			double t = l2 > 0 ? clampd(((x + 0.5 - ax) * vx + (y + 0.5 - ay) * vy) / l2, 0, 1) : 0;
			float c = (float)clampd(0.5 - (hypot(x + 0.5 - ax - t * vx, y + 0.5 - ay - t * vy) - r), 0, 1);

			if (c > mask[y * msz + x])
				mask[y * msz + x] = c;
		}
}

/* a circular arc from angle a0 to a1 (degrees, y down), as short lines */
static void m_arc(double cx, double cy, double r, double a0, double a1)
{
	int n = 1 + (int)(fabs(a1 - a0) / 8);

	for (int i = 0; i < n; i++) {
		double u = (a0 + (a1 - a0) * i / n) * M_PI / 180, w = (a0 + (a1 - a0) * (i + 1) / n) * M_PI / 180;

		m_line(cx + r * cos(u), cy + r * sin(u), cx + r * cos(w), cy + r * sin(w));
	}
}

static void m_poly(const double *p, int n)
{
	for (int i = 0; i + 1 < n; i++)
		m_line(p[2 * i], p[2 * i + 1], p[2 * i + 2], p[2 * i + 3]);
}

/* a rounded rectangle outline, corner radius r */
static void m_rect(double x, double y, double w, double h, double r)
{
	m_line(x + r, y, x + w - r, y);
	m_line(x + r, y + h, x + w - r, y + h);
	m_line(x, y + r, x, y + h - r);
	m_line(x + w, y + r, x + w, y + h - r);
	m_arc(x + r, y + r, r, 180, 270);
	m_arc(x + w - r, y + r, r, 270, 360);
	m_arc(x + w - r, y + h - r, r, 0, 90);
	m_arc(x + r, y + h - r, r, 90, 180);
}

/* the masks made so far: a symbol at a size is the same shape every time (the areas' pills are drawn at every move) */
#define ICONS 16
static struct {
	char name[12];
	int msz;
	float *mask;
} icon_cache[ICONS];

static void build_icon(const char *name)
{
	if (!strcmp(name, "pic")) {
		static const double hill[] = { 12, 32, 21, 23, 27, 29, 31, 25, 37, 31 };

		m_rect(8, 12, 32, 24, 4);
		m_poly(hill, 5);
		m_arc(31, 19, 2.4, 0, 360);
	} else if (!strcmp(name, "trap")) {
		static const double t[] = { 13, 13, 35, 13, 40, 35, 8, 35, 13, 13 };

		m_poly(t, 5);
		for (int i = 0; i < 3; i++)
			m_line(24, 17 + 6 * i, 24, 17 + 6 * i);
	} else if (!strcmp(name, "speaker")) {
		static const double sp[] = { 10, 20, 17, 20, 26, 13, 26, 35, 17, 28, 10, 28, 10, 20 };

		m_poly(sp, 7);
		m_arc(26.5, 24, 6.9, -50, 50);		/* the two waves: chords (32,18)-(32,30) and (36,14)-(36,34) */
		m_arc(24.2, 24, 12.3, -53, 53);
	} else if (!strcmp(name, "focus")) {
		m_poly((const double[]){ 10, 17, 10, 12 }, 2);
		m_poly((const double[]){ 12, 10, 17, 10 }, 2);
		m_poly((const double[]){ 31, 10, 36, 10 }, 2);
		m_poly((const double[]){ 38, 12, 38, 17 }, 2);
		m_poly((const double[]){ 38, 31, 38, 36 }, 2);
		m_poly((const double[]){ 36, 38, 31, 38 }, 2);
		m_poly((const double[]){ 17, 38, 12, 38 }, 2);
		m_poly((const double[]){ 10, 36, 10, 31 }, 2);
		m_arc(12, 12, 2, 180, 270);
		m_arc(36, 12, 2, 270, 360);
		m_arc(36, 36, 2, 0, 90);
		m_arc(12, 36, 2, 90, 180);
		m_arc(24, 24, 5, 0, 360);
	} else if (!strcmp(name, "hdmi")) {
		static const double p[] = { 9, 17, 39, 17, 39, 25, 35, 30, 13, 30, 9, 25, 9, 17 };

		m_poly(p, 7);
		m_line(17, 30, 17, 35);
		m_line(31, 30, 31, 35);
		m_line(15, 22, 33, 22);
	} else if (!strcmp(name, "power")) {
		m_line(24, 10, 24, 23);
		m_arc(24, 24.67, 12.5, 227.2, -47.2);
	} else if (!strcmp(name, "wifi")) {
		m_arc(24, 34.3, 20, -134.4, -45.6);
		m_arc(24, 35.4, 13, -134, -46);
		m_arc(24, 36.5, 6, -131.8, -48.2);
		m_arc(24, 37, 1.4, 0, 1);
	}
}

static void draw_icon(const char *name, double cx, double cy, double size, float a)
{
	const float *m = NULL;
	int x0, y0;

	mk = size * U / 48;
	msz = (int)ceil(48 * mk);
	if (msz > 160)
		return;
	for (int i = 0; i < ICONS && icon_cache[i].mask; i++)
		if (icon_cache[i].msz == msz && !strcmp(icon_cache[i].name, name))
			m = icon_cache[i].mask;
	if (!m) {
		memset(mask, 0, sizeof(float) * msz * msz);
		build_icon(name);
		for (int i = 0; i < ICONS; i++)
			if (!icon_cache[i].mask) {
				float *c = malloc(sizeof(float) * msz * msz);

				if (c) {
					memcpy(c, mask, sizeof(float) * msz * msz);
					snprintf(icon_cache[i].name, sizeof(icon_cache[i].name), "%s", name);
					icon_cache[i].msz = msz, icon_cache[i].mask = c;
				}
				break;
			}
		m = mask;
	}
	x0 = (int)(cx * U + XOFF - msz / 2.0 + 0.5);
	y0 = (int)(cy * U - msz / 2.0 + 0.5);
	for (int y = 0; y < msz; y++)
		for (int x = 0; x < msz; x++)
			if (m[y * msz + x] > 0 && x0 + x >= 0 && x0 + x < cv->w && y0 + y >= 0 && y0 + y < cv->h)
				mix(x0 + x, y0 + y, BRIGHT, a * m[y * msz + x]);
	touch(cx - size / 2 - 2, cy - size / 2 - 2, cx + size / 2 + 2, cy + size / 2 + 2);
}

/* --- the areas ----------------------------------------------------------------------------------------------- */

static double area_y(int i)
{
	return 198 + 110 * i;
}

static void draw_area(const struct view *v, int i)
{
	bool sel = i == v->area, active = v->f == F_AREAS;
	double y = area_y(i);

	clear_box(80, y - 56, 584, y + 56, GROUND);
	if (sel)
		rrect(331, y, 235, 48, 48, PAGEPILL, 1.0f, BRIGHT, active ? 1.0f : 0.5f, active ? 3 : 2);
	draw_icon(areas[i].icon, 156, y, 64, sel ? 1.0f : 0.42f);
	text(214, y + 13, 34, sel ? 1.0f : 0.42f, areas[i].name, 0);
}

/* --- the rows ------------------------------------------------------------------------------------------------ */

static double row_y(int k)
{
	return 202 + 94 * k;
}

/* the slider's own track and number: in a row of the page (x 1110..1650, the number at 1760) or in the pill (at x0..x0+520) */
static void slider_value(const struct row *r, double x0, double xnum, double y, float a)
{
	double f = r->max > r->min ? (double)(r->val - r->min) / (r->max - r->min) : 0;
	char t[24];

	stroke(x0, y, x0 + 540, y, 6, BRIGHT, a * 0.5f);
	stroke(x0, y, x0 + 540 * clampd(f, 0, 1), y, 6, BRIGHT, a);
	snprintf(t, sizeof(t), r->tag && !strcmp(r->tag, "zoom") ? "%d %%" : "%d", r->val);
	text(xnum, y + 12, 32, a, t, 1);
}

static void draw_value(const struct row *r, double y, float a)
{
	switch (r->kind) {
	case R_SLIDER:
		slider_value(r, 1110, 1760, y, a);
		break;
	case R_SWITCH:
		if (r->val) {
			rrect(1710, y, 50, 22, 22, BRIGHT, a, BRIGHT, 0, 0);
			stroke(1738, y, 1738, y, 34, 0x0b0e0d, 1);		/* the knob, dark on the lit switch */
		} else {
			rrect(1710, y, 50, 22, 22, BRIGHT, 0, BRIGHT, a * 0.6f, 3);
			stroke(1682, y, 1682, y, 26, BRIGHT, a * 0.6f);
		}
		break;
	case R_CHOICE:
		text(1730, y + 12, 32, a, r->n ? r->opt[r->val] : "-", 1);
		chevron(1750, y, 1, a);
		break;
	case R_STEPPER:
		chevron(1680, y, -1, a);
		chevron(1750, y, 1, a);
		break;
	case R_INFO:
		text(1760, y + 12, 32, a, r->text, 1);
		break;
	case R_ACTION:
	case R_CORNERS:
		if (r->text[0])
			text(r->more ? 1730 : 1760, y + 12, 32, a, r->text, 1);
		if (r->more)
			chevron(1750, y, 1, a);
		break;
	}
}

/* an option list in place of the rows, for a choice */
static void draw_option(const struct view *v, const struct row *r, int k)
{
	double y = row_y(k);

	clear_box(690, y - 54, 1830, y + 54, GROUND);	/* the pill reaches past the pitch of 94: the lit one is drawn last */
	if (k == v->choice)
		rrect(1260, y, 560, 52, 52, PAGEPILL, 1.0f, BRIGHT, 1.0f, 3);
	if (k == r->val)
		stroke(734, y, 734, y, 16, BRIGHT, k == v->choice ? 1.0f : 0.5f);
	text(776, y + 12, 32, k == v->choice ? 1.0f : 0.42f, r->opt[k], 0);
}

static void draw_row(const struct view *v, struct row *r, int k)
{
	bool sel = v->f != F_AREAS && k == v->row;
	float a = sel ? 1.0f : 0.42f;
	double y = row_y(k);

	clear_box(690, y - 54, 1830, y + 54, GROUND);
	if (sel)
		rrect(1260, y, 560, 52, 52, PAGEPILL, 1.0f, BRIGHT, 1.0f, 3);
	text(752, y + 12, 32, a, r->label, 0);
	draw_value(r, y, a);
}

/* the sentence under the rows: the row's own, or for a choice the one of the value it stands on */
static const char *note_of(const struct view *v, const struct row *sel)
{
	const char *n = sel && v->f != F_AREAS ? sel->note : NULL;

	if (sel && v->f != F_AREAS && sel->kind == R_CHOICE && sel->opt_note[sel->val])
		n = sel->opt_note[sel->val];
	return n;
}

static const char *note_shown;		/* what the note area shows now: the sentence and the line of keys under it */
static int foot_shown = -1;

static void draw_note(const struct view *v, const struct row *sel)
{
	const char *n = note_of(v, sel);
	static const char *const foot[] = {
		"Up/Down select    OK open    Back close",
		"Up/Down select    Left/Right change    Back to the areas",
		"Up/Down select    OK choose    Back cancel",
	};

	note_shown = n;
	foot_shown = v->f < F_CORNERS ? v->f : 0;
	clear_box(690, 890, 1840, 1020, GROUND);	/* the note's room ... */
	clear_box(80, 914, 690, 1020, GROUND);		/* ... and the hint's: below the last area's pill (Wi-Fi, to y 909), not into it */
	if (n) {
		char first[160];
		size_t cut = strlen(n);

		/* one line from x 752 to the safe margin; a longer sentence goes on a second line, broken at a space */
		snprintf(first, sizeof(first), "%s", n);
		while (cut && text_w(first, 26) > SAFE_X1 - 752) {
			while (cut && first[cut - 1] != ' ')
				cut--;
			if (cut)
				first[--cut] = '\0';
		}
		if (cut && cut < strlen(n)) {
			text_max = SAFE_X1 - 752;
			text(752, 922, 26, 0.7f, first, 0);
			text(752, 952, 26, 0.7f, n + cut + 1, 0);	/* what does not fit on the second line is cut, not drawn out of the margin */
			text_max = 0;
		} else {
			text(752, 952, 26, 0.7f, n, 0);
		}
	}
	text(SAFE_X0, 1000, 26, 0.42f, foot[v->f < F_CORNERS ? v->f : 0], 0);
}

/* --- over the picture: one pill at the foot --------------------------------------------------------------------- */

/* a pill of the overlays' look, centred at x 960, its centre at y, half width hw, half height hh */
static void foot_pill(double y, double hw, double hh)
{
	clear_box(960 - hw - 20, y - hh - 10, 960 + hw + 20, SAFE_Y1, 0);	/* the pill, and the line of keys under it */
	rrect(960, y, hw, hh, hh, PILL, 0.72f, BRIGHT, 0, 0);
}

static void foot_line(double y, const char *s)
{
	text(960 - text_w(s, 24) / 2, y, 24, 0.5f, s, 0);
}

/* the slider of the selected row, as the mockup v1 has it: the label, the track, the number; the keys under it */
static void draw_slider_pill(const struct view *v)
{
	struct row *r = visible_row(&areas[v->area], v->row);

	foot_pill(920, 508, 60);
	text(520, 934, 34, 1.0f, r->label, 0);
	slider_value(r, 780, 1400, 922, 1.0f);
	foot_line(1004, "Up/Down next slider    Left/Right change    OK or Back done");
}

static void draw_corner_hint(const struct view *v)
{
	static const char *const name[] = { "Top left", "Top right", "Bottom left", "Bottom right" };
	char t[64];

	foot_pill(930, 700, 76);
	snprintf(t, sizeof(t), "%s corner   %s", name[v->corner & 3], v->corner_at);
	text(960 - text_w(t, 36) / 2, 925, 36, 1.0f, t, 0);
	foot_line(965, "Arrows move it    OK next corner    Back done");
}

int ui_draw(struct osd_canvas *c, const struct view *v, unsigned dirty, int box[][4])
{
	struct area *a = &areas[v->area];
	bool all = dirty & D_ALL;
	int n = visible_rows(a);

	cv = c;
	U = c->h / 1080.0;
	XOFF = (c->w - 1920 * U) / 2;
	bx0 = c->w, by0 = c->h, bx1 = by1 = 0;
	nbox = 0;
	if (v->f == F_CORNERS || v->f == F_SLIDER) {
		/* nothing of the page over the picture that is judged: only the pill (the whole canvas is clear first) */
		if (all)
			clear_box(0, 0, 1920, 1080, 0);
		if (all || (dirty & (D_SLIDER | D_NOTE))) {
			if (v->f == F_CORNERS)
				draw_corner_hint(v);
			else
				draw_slider_pill(v);
			seal();
		}
	} else {
		if (all)
			clear_box(0, 0, 1920, 1080, GROUND);
		seal();
		for (int i = 0; i < nareas; i++)
			if (all || (dirty & D_AREA(i))) {
				draw_area(v, i);
				seal();
			}
		if (v->f == F_CHOICE) {
			struct row *r = visible_row(a, v->row);

			if (all || (dirty & D_RIGHT)) {
				clear_box(690, 70, 1830, 140, GROUND);
				text(752, 120, 26, 0.7f, r->label, 0);	/* which row these options are for */
				seal();
			}
			/* the highlighted one last: its pill reaches 5 px into the room of its neighbours */
			for (int pass = 0; pass < 2; pass++)
				for (int k = 0; k < r->n; k++)
					if ((k == v->choice) == pass && (all || (dirty & (D_RIGHT | D_ROW(k))))) {
						draw_option(v, r, k);
						seal();
					}
		} else {
			for (int pass = 0; pass < 2; pass++)
				for (int k = 0; k < n; k++)
					if ((v->f != F_AREAS && k == v->row) == pass && (all || (dirty & (D_RIGHT | D_ROW(k))))) {
						draw_row(v, visible_row(a, k), k);
						seal();
					}
		}
		if (all || (dirty & D_NOTE)) {
			const struct row *sel = visible_row(a, v->row);
			bool low = false;

			/* a move that leaves the sentence and the keys as they are does not draw them again: a piece of 1760 x 130 pixels is
			 * about half of what a row move costs through the keystone - unless a piece of this drawing reached into their room */
			for (int i = 0; i < nbox; i++)
				low |= rbox[i][1] + rbox[i][3] > (int)(890 * U);
			if (all || low || note_of(v, sel) != note_shown || (int)(v->f < F_CORNERS ? v->f : 0) != foot_shown) {
				draw_note(v, sel);
				seal();
			}
		}
	}
	memcpy(box, rbox, sizeof(int) * 4 * (size_t)nbox);
	return nbox;
}
