// SPDX-License-Identifier: GPL-2.0
/*
 * The page, drawn into an ARGB canvas the way the mockup v2 shows it (S1: the areas on the left, the rows on the
 * right, all white lines on a dark translucent ground). Text is libh713osd's osd_text; the shapes are signed
 * distance fields like the library's own. A row is drawn alone when only it changed, so a key press costs one row.
 */
#define _GNU_SOURCE
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "ui.h"

static struct osd_canvas *cv;
static double U, XOFF;			/* panel pixels per design pixel; the left margin of a panel wider than 16:9 */
static int bx0, by0, bx1, by1;		/* what this call touched, in panel pixels */

#define BRIGHT	0xffffffu
#define PILL	0x0e1110u
#define BACKDROP 0x80000000u		/* the dimmed picture: black at one half */

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
	uint32_t *p = cv->px + (size_t)y * cv->stride + x, v = *p;
	float da = (v >> 24) / 255.0f, oa = a + da * (1 - a), r, g, b;

	if (a <= 0 || oa <= 0)
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

	for (int py = (int)fmax(0, y - h - 2); py < (int)fmin(cv->h, y + h + 2); py++)
		for (int px = (int)fmax(0, x - w - 2); px < (int)fmin(cv->w, x + w + 2); px++) {
			double dx = fabs(px + 0.5 - x) - w + rr, dy = fabs(py + 0.5 - y) - h + rr;
			double d = sqrt(fmax(dx, 0) * fmax(dx, 0) + fmax(dy, 0) * fmax(dy, 0)) + fmin(fmax(dx, dy), 0) - rr;

			if (af > 0)
				mix(px, py, fill, af * (float)clampd(0.5 - d, 0, 1));
			if (lw > 0)
				mix(px, py, line, al * (float)clampd(0.5 - (fabs(d + l / 2) - l / 2), 0, 1));
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

static double text_w(const char *s, double px)
{
	return osd_text_width(s, px * U);
}

/* align 0 left of x, 1 right-aligned at x; the baseline y; size in design pixels */
static void text(double x, double y, double size, float a, const char *s, int align)
{
	double w = text_w(s, size);

	osd_text(cv, s, (align ? x - w : x) * U + XOFF, y * U, size * U, BRIGHT, a, 0);
	touch(align ? x - w - 2 : x - 2, y - size, align ? x + 2 : x + w + 2, y + size * 0.4);
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

	for (int y = 0; y < msz; y++)
		for (int x = 0; x < msz; x++) {
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

static void draw_icon(const char *name, double cx, double cy, double size, float a)
{
	int x0, y0;

	mk = size * U / 48;
	msz = (int)ceil(48 * mk);
	if (msz > 160)
		return;
	memset(mask, 0, sizeof(float) * msz * msz);
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
	x0 = (int)(cx * U + XOFF - msz / 2.0 + 0.5);
	y0 = (int)(cy * U - msz / 2.0 + 0.5);
	for (int y = 0; y < msz; y++)
		for (int x = 0; x < msz; x++)
			if (mask[y * msz + x] > 0 && x0 + x >= 0 && x0 + x < cv->w && y0 + y >= 0 && y0 + y < cv->h)
				mix(x0 + x, y0 + y, BRIGHT, a * mask[y * msz + x]);
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

	clear_box(80, y - 56, 584, y + 56, BACKDROP);
	if (sel)
		rrect(331, y, 235, 48, 48, PILL, 0.72f, BRIGHT, active ? 1.0f : 0.5f, active ? 3 : 2);
	draw_icon(areas[i].icon, 156, y, 64, sel ? 1.0f : 0.42f);
	text(214, y + 13, 34, sel ? 1.0f : 0.42f, areas[i].name, 0);
}

/* --- the rows ------------------------------------------------------------------------------------------------ */

static double row_y(int k)
{
	return 202 + 94 * k;
}

static void draw_value(const struct row *r, double y, float a)
{
	char t[24];

	switch (r->kind) {
	case R_SLIDER: {
		double f = r->max > r->min ? (double)(r->val - r->min) / (r->max - r->min) : 0;

		stroke(1110, y, 1650, y, 6, BRIGHT, a * 0.5f);
		stroke(1110, y, 1110 + 540 * clampd(f, 0, 1), y, 6, BRIGHT, a);
		snprintf(t, sizeof(t), r->tag && !strcmp(r->tag, "zoom") ? "%d %%" : "%d", r->val);
		text(1760, y + 12, 32, a, t, 1);
		break;
	}
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

	clear_box(690, y - 54, 1830, y + 54, BACKDROP);	/* the pill reaches past the pitch of 94: the lit one is drawn last */
	if (k == v->choice)
		rrect(1260, y, 560, 52, 52, PILL, 0.72f, BRIGHT, 1.0f, 3);
	if (k == r->val)
		stroke(734, y, 734, y, 16, BRIGHT, k == v->choice ? 1.0f : 0.5f);
	text(776, y + 12, 32, k == v->choice ? 1.0f : 0.42f, r->opt[k], 0);
}

static void draw_row(const struct view *v, struct row *r, int k)
{
	bool sel = v->f != F_AREAS && k == v->row;
	float a = sel ? 1.0f : 0.42f;
	double y = row_y(k);

	clear_box(690, y - 54, 1830, y + 54, BACKDROP);
	if (sel)
		rrect(1260, y, 560, 52, 52, PILL, 0.72f, BRIGHT, 1.0f, 3);
	text(752, y + 12, 32, a, r->label, 0);
	draw_value(r, y, a);
}

static void draw_note(const struct view *v, const struct row *sel)
{
	const char *n = sel && v->f != F_AREAS ? sel->note : NULL;

	if (sel && v->f != F_AREAS && sel->kind == R_CHOICE && sel->opt_note[sel->val])
		n = sel->opt_note[sel->val];			/* the sentence for the value it stands on */
	static const char *const foot[] = {
		"Up/Down select    OK open    Back close",
		"Up/Down select    Left/Right change    Back to the areas",
		"Up/Down select    OK choose    Back cancel",
	};

	clear_box(80, 930, 1840, 1050, BACKDROP);
	if (n)
		text(752, 970, 26, 0.7f, n, 0);
	text(96, 1020, 26, 0.42f, foot[v->f < F_CORNERS ? v->f : 0], 0);
}

static void draw_corner_hint(const struct view *v)
{
	static const char *const name[] = { "Top left", "Top right", "Bottom left", "Bottom right" };
	char t[64];

	clear_box(240, 860, 1680, 1060, 0);
	rrect(960, 960, 700, 76, 76, PILL, 0.72f, BRIGHT, 1.0f, 3);
	snprintf(t, sizeof(t), "%s corner   %s", name[v->corner & 3], v->corner_at);
	text(960 - text_w(t, 36) / 2, 955, 36, 1.0f, t, 0);
	text(960 - text_w("Arrows move it    OK next corner    Back done", 26) / 2, 995, 26, 0.6f,
	     "Arrows move it    OK next corner    Back done", 0);
}

void ui_draw(struct osd_canvas *c, const struct view *v, unsigned dirty, int box[4])
{
	struct area *a = &areas[v->area];
	int n = visible_rows(a);

	cv = c;
	U = c->h / 1080.0;
	XOFF = (c->w - 1920 * U) / 2;
	bx0 = c->w, by0 = c->h, bx1 = by1 = 0;
	if (v->f == F_CORNERS) {
		/* nothing of the page over the calibration picture: only the hint */
		if (dirty & D_ALL)
			clear_box(0, 0, 1920, 1080, 0);
		draw_corner_hint(v);
	} else {
		if (dirty & D_ALL)
			clear_box(0, 0, 1920, 1080, BACKDROP);
		if (dirty & (D_ALL | D_AREAS))
			for (int i = 0; i < nareas; i++)
				draw_area(v, i);
		if (v->f == F_CHOICE) {
			struct row *r = visible_row(a, v->row);

			if (dirty & D_ALL) {
				clear_box(690, 70, 1830, 140, BACKDROP);
				text(752, 120, 26, 0.7f, r->label, 0);	/* which row these options are for */
			}
			/* the highlighted one last: its pill reaches 5 px into the room of its neighbours */
			for (int pass = 0; pass < 2; pass++)
				for (int k = 0; k < r->n; k++)
					if ((k == v->choice) == pass && (dirty & (D_ALL | D_AREAS | D_ROW(k))))
						draw_option(v, r, k);
		} else {
			for (int pass = 0; pass < 2; pass++)
				for (int k = 0; k < n; k++)
					if ((v->f != F_AREAS && k == v->row) == pass && (dirty & (D_ALL | D_AREAS | D_ROW(k))))
						draw_row(v, visible_row(a, k), k);
		}
		if (dirty & (D_ALL | D_NOTE | D_AREAS))
			draw_note(v, visible_row(a, v->row));
	}
	if (bx1 <= bx0 || by1 <= by0) {
		box[0] = box[1] = box[2] = box[3] = 0;
		return;
	}
	box[0] = bx0, box[1] = by0, box[2] = bx1 - bx0, box[3] = by1 - by0;
}
