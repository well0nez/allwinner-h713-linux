// SPDX-License-Identifier: GPL-2.0
/*
 * libh713osd - see osd.h. One item is laid out as a short list of primitives (strokes, arcs, rounded
 * rectangles, filled polygons), each in one tone - bright white, dim white or red (a warning: the end of the
 * focus travel); then every pixel of its rectangle gets the coverage of the nearest edge of each tone and is
 * mixed over what the canvas already holds.
 *
 * The distance functions follow the usual 2-D signed distance formulas; the round-capped segment, the
 * triangle as three half planes and the rounded rectangle came over from the warp-konsole draft
 * (versuch/warp-konsole, osd.c), the digits are drawn anew with arcs, because straight strokes looked crude.
 */
#include <math.h>
#include <string.h>

#include "osd.h"

#define AA	1.2		/* px from fully out to fully in at an edge */
#define DIM	0.30		/* the weight of a dim line: the bar's track, the waves above the level */
#define MAXP	64

enum { T_BRIGHT, T_DIM, T_RED };	/* the tones of a line */

enum { P_SEG, P_ARC, P_RRECT, P_RRECT_LINE, P_POLY };

struct prim {
	int type, tone;
	double a[8];		/* the shape's numbers, see prim_dist */
	int n;			/* P_POLY: corners in a[] as x0,y0,x1,y1,... (at most 4) */
};

struct scene {
	struct prim p[MAXP];
	int n;
	double lw;		/* half the line width of icons and digits, px */
	int panel;		/* 0 none, 1 rounded rectangle, 2 circle */
	double px, py, pw, ph, pr;	/* the panel: left, top, width, height, corner radius */
};

static double clampd(double v, double lo, double hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

static double seg_dist(double x, double y, double ax, double ay, double bx, double by)
{
	double abx = bx - ax, aby = by - ay, apx = x - ax, apy = y - ay;
	double t = clampd((apx * abx + apy * aby) / (abx * abx + aby * aby + 1e-12), 0, 1);

	return hypot(apx - abx * t, apy - aby * t);
}

/* the distance to an arc of radius r around (cx, cy) from angle a0 to a1 (degrees, y down: 0 right,
 * 90 below), a1 > a0 */
static double arc_dist(double x, double y, double cx, double cy, double r, double a0, double a1)
{
	double ang = atan2(y - cy, x - cx) * 180 / M_PI;
	double r0 = a0 * M_PI / 180, r1 = a1 * M_PI / 180;

	while (ang < a0)
		ang += 360;
	if (ang <= a1)
		return fabs(hypot(x - cx, y - cy) - r);
	return fmin(hypot(x - cx - r * cos(r0), y - cy - r * sin(r0)),
		    hypot(x - cx - r * cos(r1), y - cy - r * sin(r1)));
}

static double rrect_sd(double x, double y, double cx, double cy, double hw, double hh, double r)
{
	double qx = fabs(x - cx) - hw + r, qy = fabs(y - cy) - hh + r;

	return hypot(fmax(qx, 0), fmax(qy, 0)) + fmin(fmax(qx, qy), 0) - r;
}

/* a convex polygon, corners clockwise on screen: the largest distance to its edges' half planes */
static double poly_sd(double x, double y, const double *c, int n)
{
	double d = -1e9;
	int i;

	for (i = 0; i < n; i++) {
		double ax = c[2 * i], ay = c[2 * i + 1];
		double bx = c[2 * ((i + 1) % n)], by = c[2 * ((i + 1) % n) + 1];
		double e = ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / hypot(bx - ax, by - ay);

		d = fmax(d, -e);
	}
	return d;
}

/* signed distance of one primitive, negative inside */
static double prim_dist(const struct prim *p, double x, double y, double lw)
{
	const double *a = p->a;

	switch (p->type) {
	case P_SEG:
		return seg_dist(x, y, a[0], a[1], a[2], a[3]) - lw;
	case P_ARC:
		return arc_dist(x, y, a[0], a[1], a[2], a[3], a[4]) - lw;
	case P_RRECT:
		return rrect_sd(x, y, a[0], a[1], a[2], a[3], a[4]);
	case P_RRECT_LINE:
		return fabs(rrect_sd(x, y, a[0], a[1], a[2], a[3], a[4])) - lw;
	case P_POLY:
		return poly_sd(x, y, a, p->n);
	}
	return 1e9;
}

static struct prim *add(struct scene *s, int type, int tone)
{
	struct prim *p = &s->p[s->n < MAXP - 1 ? s->n++ : s->n];

	memset(p, 0, sizeof(*p));
	p->type = type;
	p->tone = tone;
	return p;
}

static void seg(struct scene *s, double ax, double ay, double bx, double by, int tone)
{
	struct prim *p = add(s, P_SEG, tone);

	p->a[0] = ax, p->a[1] = ay, p->a[2] = bx, p->a[3] = by;
}

static void arc(struct scene *s, double cx, double cy, double r, double a0, double a1, int tone)
{
	struct prim *p = add(s, P_ARC, tone);

	p->a[0] = cx, p->a[1] = cy, p->a[2] = r, p->a[3] = a0, p->a[4] = a1;
}

static void rrect(struct scene *s, int type, double cx, double cy, double hw, double hh, double r, int tone)
{
	struct prim *p = add(s, type, tone);

	p->a[0] = cx, p->a[1] = cy, p->a[2] = hw, p->a[3] = hh, p->a[4] = r;
}

/* --- the digits: a box 6 wide and 10 high, y down; strokes with round caps ---------------------------- */

static void digit(struct scene *s, int d, double ox, double oy, double k)
{
#define X(v) (ox + (v) * k)
#define Y(v) (oy + (v) * k)
	switch (d) {
	case 0: rrect(s, P_RRECT_LINE, X(3), Y(5), 2.5 * k, 4.5 * k, 2.5 * k, 0); break;
	case 1: seg(s, X(3.4), Y(0.5), X(3.4), Y(9.5), 0); seg(s, X(1.4), Y(2.3), X(3.4), Y(0.5), 0); break;
	case 2: arc(s, X(3), Y(3), 2.5 * k, 195, 395, 0);
		seg(s, X(3 + 2.5 * cos(35 * M_PI / 180)), Y(3 + 2.5 * sin(35 * M_PI / 180)), X(0.6), Y(9.5), 0);
		seg(s, X(0.6), Y(9.5), X(5.5), Y(9.5), 0); break;
	case 3: arc(s, X(3), Y(2.75), 2.25 * k, 200, 450, 0); arc(s, X(3), Y(7.25), 2.25 * k, 270, 520, 0); break;
	case 4: seg(s, X(4.2), Y(9.5), X(4.2), Y(0.5), 0); seg(s, X(4.2), Y(0.5), X(0.5), Y(6.9), 0);
		seg(s, X(0.5), Y(6.9), X(5.6), Y(6.9), 0); break;
	case 5: seg(s, X(5.2), Y(0.5), X(1.1), Y(0.5), 0); seg(s, X(1.1), Y(0.5), X(0.9), Y(4.7), 0);
		arc(s, X(3), Y(6.75), 2.75 * k, 222, 520, 0); break;
	case 6: arc(s, X(3), Y(6.75), 2.75 * k, 0, 360, 0); seg(s, X(4.5), Y(0.5), X(0.75), Y(5.9), 0); break;
	case 7: seg(s, X(0.5), Y(0.5), X(5.5), Y(0.5), 0); seg(s, X(5.5), Y(0.5), X(2.2), Y(9.5), 0); break;
	case 8: arc(s, X(3), Y(2.65), 2.15 * k, 0, 360, 0); arc(s, X(3), Y(7.15), 2.35 * k, 0, 360, 0); break;
	case 9: arc(s, X(3), Y(3.25), 2.75 * k, 0, 360, 0); seg(s, X(5.25), Y(4.1), X(1.5), Y(9.5), 0); break;
	}
#undef X
#undef Y
}

/* a number 0..999, right edge at rx, top at y, digit height h; returns the left edge */
static double number(struct scene *s, int v, double rx, double y, double h)
{
	double k = h / 10, step = 7.6 * k, x = rx - 6 * k;

	if (v < 0)
		v = 0;
	do {
		digit(s, v % 10, x, y, k);
		x -= step;
		v /= 10;
	} while (v);
	return x + step;
}

/* the same, centred on cx */
static void number_centred(struct scene *s, int v, double cx, double y, double h)
{
	int n = v >= 100 ? 3 : v >= 10 ? 2 : 1;
	double k = h / 10, w = (n - 1) * 7.6 * k + 6 * k;

	number(s, v, cx + w / 2, y, h);
}

/* --- the icons, centred at (cx, cy), k = one unit (the icon box is about 36 units) -------------------- */

static void speaker(struct scene *s, double cx, double cy, double k, int level, int crossed)
{
	struct prim *p;
	int i;

	rrect(s, P_RRECT_LINE, cx - 11 * k, cy, 3.5 * k, 6 * k, 1.5 * k, 0);
	p = add(s, P_SEG, 0); p->a[0] = cx - 7.5 * k, p->a[1] = cy - 6 * k, p->a[2] = cx + 1 * k, p->a[3] = cy - 13 * k;
	p = add(s, P_SEG, 0); p->a[0] = cx + 1 * k, p->a[1] = cy - 13 * k, p->a[2] = cx + 1 * k, p->a[3] = cy + 13 * k;
	p = add(s, P_SEG, 0); p->a[0] = cx + 1 * k, p->a[1] = cy + 13 * k, p->a[2] = cx - 7.5 * k, p->a[3] = cy + 6 * k;
	if (crossed) {
		seg(s, cx + 7 * k, cy - 5.5 * k, cx + 18 * k, cy + 5.5 * k, 0);
		seg(s, cx + 7 * k, cy + 5.5 * k, cx + 18 * k, cy - 5.5 * k, 0);
		return;
	}
	for (i = 0; i < 3; i++)		/* the waves: as many bright as the level has thirds, the rest dim */
		arc(s, cx + 1 * k, cy, (7 + 5.5 * i) * k, -48, 48, level <= i * 33);
}

/* the focus: a viewfinder (four corners around a small ring) and, right of it, both directions stacked - the
 * one pressed bright, the other dim; at the end of the travel the pressed one turns red, with a red bar across
 * its tip (Marco, 11.10.2026: a symbol alone would not tell a user that the end is reached) */
static void focus_icon(struct scene *s, double cx, double cy, double k, int dir, int edge)
{
	double fx = cx - 12 * k, h = 11 * k, c = 4.5 * k, ax = cx + 16 * k, cw = 7 * k, ch = 4.2 * k;
	int i, d;

	for (i = 0; i < 4; i++) {
		double sx = i & 1 ? 1 : -1, sy = i & 2 ? 1 : -1;
		double x = fx + sx * h, y = cy + sy * h;

		seg(s, x, y, x - sx * c, y, T_BRIGHT);
		seg(s, x, y, x, y - sy * c, T_BRIGHT);
	}
	arc(s, fx, cy, 3.5 * k, 0, 360, T_BRIGHT);
	for (d = 1; d >= -1; d -= 2) {		/* +1 up (above), -1 down (below) */
		double yc = cy - d * 7.5 * k, tip = yc - d * ch / 2, foot = yc + d * ch / 2;
		int tone = d != dir ? T_DIM : edge ? T_RED : T_BRIGHT;

		seg(s, ax - cw, foot, ax, tip, tone);
		seg(s, ax, tip, ax + cw, foot, tone);
		if (d == dir && edge)
			seg(s, ax - cw, tip - d * 3 * k, ax + cw, tip - d * 3 * k, T_RED);
	}
}

static void hdmi_icon(struct scene *s, double cx, double cy, double k, int dim)
{
	double c[] = { -13, -6, 13, -6, 13, 1, 8.5, 6, -8.5, 6, -13, 1 };
	int i;

	for (i = 0; i < 6; i++)
		seg(s, cx + c[2 * i] * k, cy + c[2 * i + 1] * k,
		    cx + c[2 * ((i + 1) % 6)] * k, cy + c[2 * ((i + 1) % 6) + 1] * k, dim);
	seg(s, cx - 7 * k, cy - 1 * k, cx + 7 * k, cy - 1 * k, dim);
}

static void console_icon(struct scene *s, double cx, double cy, double k, int dim)
{
	rrect(s, P_RRECT_LINE, cx, cy, 14 * k, 10 * k, 2.5 * k, dim);
	seg(s, cx - 8 * k, cy - 4 * k, cx - 3.5 * k, cy, dim);
	seg(s, cx - 3.5 * k, cy, cx - 8 * k, cy + 4 * k, dim);
	seg(s, cx - 0.5 * k, cy + 4 * k, cx + 6 * k, cy + 4 * k, dim);
}

static void bar(struct scene *s, double x0, double x1, double cy, int v)
{
	seg(s, x0, cy, x1, cy, 1);
	if (v > 0)
		seg(s, x0, cy, x0 + (x1 - x0) * clampd(v, 0, 100) / 100, cy, 0);
}

/* --- layout -------------------------------------------------------------------------------------------- */

static void place_panel(struct scene *s, const struct osd_canvas *c, const struct osd_style *st,
			double u, double w, double h)
{
	s->pw = w, s->ph = h;
	switch (st->place) {
	case OSD_BOTTOM:
		s->px = (c->w - w) / 2, s->py = c->h - 90 * u - h;
		break;
	case OSD_TOP_RIGHT:
		s->px = c->w - 64 * u - w, s->py = 64 * u;
		break;
	case OSD_CENTER:
		s->px = (c->w - w) / 2, s->py = (c->h - h) / 2;
		break;
	}
}

static void layout(struct scene *s, const struct osd_canvas *c, const struct osd_style *st,
		   const struct osd_item *it)
{
	double u = c->h / 1080.0 * (st->scale > 0 ? st->scale : 1), k = u, cy;
	int card = st->place == OSD_CENTER, v = (int)clampd(it->value, 0, 100);

	memset(s, 0, sizeof(*s));
	s->lw = 1.6 * u;
	s->panel = st->look == OSD_PILL;

	if (it->kind == OSD_MUTE_BADGE) {
		double d = 64 * u;

		s->panel = 2;	/* the badge has its own disc in both looks, faint, so it never vanishes in a bright picture */
		s->pw = s->ph = d, s->pr = d / 2;
		s->px = st->place == OSD_TOP_RIGHT ? 48 * u : c->w - 48 * u - d;
		s->py = 48 * u;
		speaker(s, s->px + d / 2 - 4 * u, s->py + d / 2, 1.25 * u, 0, 1);
		return;
	}
	if (card) {			/* the centre: a square card, the icon large, the value below */
		double d = it->kind == OSD_FOCUS ? 190 * u : 260 * u;

		place_panel(s, c, st, u, d, d);
		s->pr = 36 * u;
		k = it->kind == OSD_FOCUS ? 2.9 * u : 2.1 * u;
		cy = s->py + (it->kind == OSD_FOCUS ? 65 * u : 100 * u);
	} else {
		double w = it->kind == OSD_VOLUME || it->kind == OSD_MUTE ? 540 * u : it->kind == OSD_FOCUS ? 150 * u : 220 * u;

		place_panel(s, c, st, u, w, 76 * u);
		s->pr = 38 * u;
		cy = s->py + 38 * u;
		k = 1.38 * u;		/* the icons in a strip: about 50 px high at 1080 lines */
	}

	switch (it->kind) {
	case OSD_VOLUME:
	case OSD_MUTE: {
		int mute = it->kind == OSD_MUTE, first;

		if (card) {
			speaker(s, s->px + s->pw / 2 - 2 * k, cy - 8 * u, k, v, mute);
			first = s->n;
			number_centred(s, v, s->px + s->pw / 2, s->py + 150 * u, 34 * u);
			bar(s, s->px + 50 * u, s->px + 210 * u, s->py + 222 * u, v);
		} else {
			speaker(s, s->px + 60 * u, cy, k, v, mute);
			first = s->n;
			number(s, v, s->px + s->pw - 32 * u, cy - 15 * u, 30 * u);
			bar(s, s->px + 118 * u, s->px + s->pw - 116 * u, cy, v);
		}
		if (mute)	/* the volume is kept, not heard: its digits and bar stay, dim */
			for (int i = first; i < s->n; i++)
				s->p[i].tone = T_DIM;
		break;
	}
	case OSD_FOCUS:
		focus_icon(s, s->px + s->pw / 2, cy + (card ? 30 * u : 0), k, it->value >= 0 ? 1 : -1, it->flags & OSD_EDGE);
		break;
	case OSD_INPUT:
		if (card) {
			hdmi_icon(s, s->px + s->pw / 2, cy - 10 * u, 1.6 * u, it->value != 0);
			console_icon(s, s->px + s->pw / 2, cy + 80 * u, 1.6 * u, it->value == 0);
		} else {
			hdmi_icon(s, s->px + 60 * u, cy, k, it->value != 0);
			console_icon(s, s->px + s->pw - 60 * u, cy, k, it->value == 0);
		}
		break;
	default:
		break;
	}
}

/* --- mixing --------------------------------------------------------------------------------------------- */

static double cover(double d, double aa)
{
	return clampd(0.5 - d / aa, 0, 1);
}

/* straight-alpha "over": colour (r, g, b) with alpha a onto the pixel */
static void over(uint32_t *px, double r, double g, double b, double a)
{
	double da = (*px >> 24) / 255.0, dr = (*px >> 16 & 255), dg = (*px >> 8 & 255), db = (*px & 255);
	double oa = a + da * (1 - a);

	if (a <= 0 || oa <= 0)
		return;
	r = (r * a + dr * da * (1 - a)) / oa;
	g = (g * a + dg * da * (1 - a)) / oa;
	b = (b * a + db * da * (1 - a)) / oa;
	*px = (uint32_t)(oa * 255 + 0.5) << 24 | (uint32_t)(r + 0.5) << 16 | (uint32_t)(g + 0.5) << 8 |
	      (uint32_t)(b + 0.5);
}

void osd_clear(struct osd_canvas *c)
{
	for (int y = 0; y < c->h; y++)
		memset(c->px + (size_t)y * c->stride, 0, (size_t)c->w * 4);
}

void osd_draw(struct osd_canvas *c, const struct osd_style *st, const struct osd_item *it, int box[4])
{
	static struct scene s;
	double u = c->h / 1080.0 * (st->scale > 0 ? st->scale : 1), shadow = 14 * u;
	double fade = clampd(it->alpha, 0, 1);
	int bare = st->look == OSD_BARE && it->kind != OSD_MUTE_BADGE;
	int x0, y0, x1, y1;

	layout(&s, c, st, it);
	x0 = (int)floor(s.px - shadow), y0 = (int)floor(s.py - shadow);
	x1 = (int)ceil(s.px + s.pw + shadow), y1 = (int)ceil(s.py + s.ph + shadow);
	x0 = x0 < 0 ? 0 : x0, y0 = y0 < 0 ? 0 : y0;
	x1 = x1 > c->w ? c->w : x1, y1 = y1 > c->h ? c->h : y1;
	if (box)
		box[0] = x0, box[1] = y0, box[2] = x1 - x0, box[3] = y1 - y0;

	for (int y = y0; y < y1; y++)
		for (int x = x0; x < x1; x++) {
			double fx = x + 0.5, fy = y + 0.5, t[3] = { 1e9, 1e9, 1e9 }, all;
			uint32_t *px = c->px + (size_t)y * c->stride + x;

			for (int i = 0; i < s.n; i++) {
				double d = prim_dist(&s.p[i], fx, fy, s.lw);

				t[s.p[i].tone] = fmin(t[s.p[i].tone], d);
			}
			all = fmin(t[T_BRIGHT], fmin(t[T_DIM], t[T_RED]));
			if (s.panel == 1)
				over(px, 10, 12, 16, 0.46 * fade *
				     cover(rrect_sd(fx, fy, s.px + s.pw / 2, s.py + s.ph / 2, s.pw / 2, s.ph / 2, s.pr), AA));
			else if (s.panel == 2)
				over(px, 10, 12, 16, 0.38 * fade *
				     cover(hypot(fx - s.px - s.pw / 2, fy - s.py - s.ph / 2) - s.pw / 2, AA));
			if (bare)	/* a soft shadow around every line keeps it legible on a bright picture */
				over(px, 0, 0, 0, 0.62 * fade * cover(all - 3 * u, shadow) *
				     (t[T_DIM] < fmin(t[T_BRIGHT], t[T_RED]) ? 0.7 : 1));
			over(px, 250, 250, 250, 0.94 * fade * fmax(cover(t[T_BRIGHT], AA), DIM * cover(t[T_DIM], AA)));
			over(px, 255, 72, 64, 0.96 * fade * cover(t[T_RED], AA));
		}
}
