// SPDX-License-Identifier: GPL-2.0
/*
 * libh713osd - see osd.h. One item is laid out as a short list of primitives (round-capped strokes, arcs,
 * outlines of rounded rectangles), each in one tone - bright white, dim white or red (a warning: the end of the
 * focus travel); then every pixel of its rectangle gets the coverage of the nearest edge of each tone and is
 * mixed over what the canvas already holds.
 *
 * The distance functions follow the usual 2-D signed distance formulas; the round-capped segment and the
 * rounded rectangle came over from the warp-konsole draft (versuch/warp-konsole, osd.c); the digits are drawn
 * anew with arcs, because straight strokes looked crude.
 */
#include <math.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "osd.h"

#define AA	1.2		/* px from fully out to fully in at an edge */
#define DIM	0.30		/* the weight of a dim line: the bar's track, the waves above the level */
#define MAXP	64

enum { T_BRIGHT, T_DIM, T_RED };	/* the tones of a line */

enum { P_SEG, P_ARC, P_RRECT_LINE };

struct prim {
	int type, tone;
	double lw;		/* half the line width of this shape; 0: the scene's */
	double a[10];		/* the shape's numbers, see prim_dist */
};

struct scene {
	struct prim p[MAXP];
	int n;
	double lw;		/* half the line width of icons and digits, px */
	double dim;		/* the weight of a dim line */
	double pill_a;		/* the alpha of the pill's fill */
	unsigned pill_rgb;	/* its colour (0xRRGGBB) */
	double px, py, pw, ph;	/* the item's box: left, top, width, height */
	int panel;		/* behind the lines: 0 a soft shadow (the bare look), 1 the pill, 2 the badge's disc, 3 nothing */
};

static double clampd(double v, double lo, double hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

static double seg_dist(double x, double y, double ax, double ay, double bx, double by)
{
	double abx = bx - ax, aby = by - ay, apx = x - ax, apy = y - ay;
	double t = clampd((apx * abx + apy * aby) / (abx * abx + aby * aby + 1e-12), 0, 1);

	apx -= abx * t, apy -= aby * t;
	return sqrt(apx * apx + apy * apy);	/* not hypot(): it guards against overflow nobody needs here, slowly */
}

/* the distance to an arc (arc() below: a[0..2] centre and radius, a[5..8] the unit vectors of its start and end,
 * a[9] its span in degrees). Whether a point lies within the arc's angle is decided with two cross products
 * against the start and the end - no atan2 per pixel: within a span of up to 180 degrees means "after the start
 * and before the end"; for a larger span, "not strictly inside the complement", which is smaller than 180. */
static double arc_dist(double x, double y, const double *a)
{
	double px = x - a[0], py = y - a[1], ex0, ey0, ex1, ey1;
	bool in;

	if (a[9] >= 360)
		in = true;
	else if (a[9] <= 180)
		in = a[5] * py - a[6] * px >= 0 && px * a[8] - py * a[7] >= 0;
	else
		in = !(a[7] * py - a[8] * px > 0 && px * a[6] - py * a[5] > 0);
	if (in)
		return fabs(sqrt(px * px + py * py) - a[2]);
	ex0 = px - a[2] * a[5], ey0 = py - a[2] * a[6];
	ex1 = px - a[2] * a[7], ey1 = py - a[2] * a[8];
	return sqrt(fmin(ex0 * ex0 + ey0 * ey0, ex1 * ex1 + ey1 * ey1));
}

static double rrect_sd(double x, double y, double cx, double cy, double hw, double hh, double r)
{
	double qx = fabs(x - cx) - hw + r, qy = fabs(y - cy) - hh + r;

	double ox = fmax(qx, 0), oy = fmax(qy, 0);

	return sqrt(ox * ox + oy * oy) + fmin(fmax(qx, qy), 0) - r;
}

/* signed distance of one primitive, negative inside */
static double prim_dist(const struct prim *p, double x, double y, double lw)
{
	const double *a = p->a;

	switch (p->type) {
	case P_SEG:
		return seg_dist(x, y, a[0], a[1], a[2], a[3]) - lw;
	case P_ARC:
		return arc_dist(x, y, a) - lw;
	case P_RRECT_LINE:
		return fabs(rrect_sd(x, y, a[0], a[1], a[2], a[3], a[4])) - lw;
	}
	return 1e9;
}

/* the rectangle outside which the primitive is more than m px away (m includes its half line width) */
static void prim_bbox(const struct prim *p, double m, double b[4])
{
	const double *a = p->a;

	switch (p->type) {
	case P_SEG:
		b[0] = fmin(a[0], a[2]) - m, b[1] = fmin(a[1], a[3]) - m;
		b[2] = fmax(a[0], a[2]) + m, b[3] = fmax(a[1], a[3]) + m;
		break;
	case P_ARC:	/* the whole circle: simple, and never too small */
		b[0] = a[0] - a[2] - m, b[1] = a[1] - a[2] - m;
		b[2] = a[0] + a[2] + m, b[3] = a[1] + a[2] + m;
		break;
	default:	/* P_RRECT_LINE */
		b[0] = a[0] - a[2] - m, b[1] = a[1] - a[3] - m;
		b[2] = a[0] + a[2] + m, b[3] = a[1] + a[3] + m;
		break;
	}
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
	p->a[5] = cos(a0 * M_PI / 180), p->a[6] = sin(a0 * M_PI / 180);
	p->a[7] = cos(a1 * M_PI / 180), p->a[8] = sin(a1 * M_PI / 180);
	p->a[9] = a1 - a0;
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

/* power: a ring open at the top and the stroke through the gap (IEC 60417-5009) */
static void power_icon(struct scene *s, double cx, double cy, double k, int tone)
{
	arc(s, cx, cy, 11 * k, -55, 235, tone);
	seg(s, cx, cy - 15 * k, cx, cy - 2 * k, tone);
}

/* standby: a crescent moon - the disc of radius r minus a second disc shifted up and right; the outline is the
 * part of each circle that lies outside (resp. inside) the other one */
static void moon_icon(struct scene *s, double cx, double cy, double k, int tone)
{
	double R = 12 * k, rb = 10 * k, bx = 7 * k, by = -5 * k;
	double d = sqrt(bx * bx + by * by), a = (R * R - rb * rb + d * d) / (2 * d);
	double phi = atan2(by, bx) * 180 / M_PI, al = acos(a / R) * 180 / M_PI;
	double be = acos((d - a) / rb) * 180 / M_PI, psi = phi + 180;

	arc(s, cx, cy, R, phi + al, phi + 360 - al, tone);
	arc(s, cx + bx, cy + by, rb, psi - be, psi + be, tone);
}

/* a countdown ring: the whole circle dim, the time left bright, clockwise from the top */
static void ring(struct scene *s, double cx, double cy, double r, double left)
{
	left = clampd(left, 0, 1);
	if (left < 1)
		arc(s, cx, cy, r, 0, 360, T_DIM);
	if (left > 0.004)
		arc(s, cx, cy, r, -90, -90 + 360 * left, T_BRIGHT);
}

/* a number centred at cx */
static void number_c(struct scene *s, int v, double cx, double y, double h)
{
	double k = h / 10;
	int n = v >= 100 ? 3 : v >= 10 ? 2 : 1;

	number(s, v, cx + ((n - 1) * 7.6 * k + 6 * k) / 2, y, h);
}

/* the Bluetooth rune */
static void bt_icon(struct scene *s, double cx, double cy, double k, int tone)
{
	double t = 13 * k, w = 6.5 * k;

	seg(s, cx, cy - t, cx, cy + t, tone);
	seg(s, cx - w, cy - w, cx + w, cy + w, tone);
	seg(s, cx + w, cy + w, cx, cy + t, tone);
	seg(s, cx - w, cy + w, cx + w, cy - w, tone);
	seg(s, cx + w, cy - w, cx, cy - t, tone);
}

/* a key of the remote: a small circle with a chevron pointing dir (-1 left, +1 right) */
static void key_icon(struct scene *s, double cx, double cy, double k, int dir, int tone)
{
	arc(s, cx, cy, 10 * k, 0, 360, tone);
	seg(s, cx - dir * 2 * k, cy - 4.5 * k, cx + dir * 2.5 * k, cy, tone);
	seg(s, cx + dir * 2.5 * k, cy, cx - dir * 2 * k, cy + 4.5 * k, tone);
}

static void bar(struct scene *s, double x0, double x1, double cy, int v)
{
	seg(s, x0, cy, x1, cy, 1);
	if (v > 0)
		seg(s, x0, cy, x0 + (x1 - x0) * clampd(v, 0, 100) / 100, cy, 0);
}

/* --- layout -------------------------------------------------------------------------------------------- */

static void place_box(struct scene *s, const struct osd_canvas *c, const struct osd_style *st,
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

/* the power key's countdown (TODO 2.38): large, in the middle, whatever osd.conf places the other overlays - a
 * ring with the seconds left, standby on its left, off on its right, as the keys Left and Right choose; the
 * choice bright and underlined, the other dim (Marco 11.10.2026: of three mockups this one) */
static void power_layout(struct scene *s, const struct osd_canvas *c, const struct osd_style *st,
			 const struct osd_item *it, double u)
{
	struct osd_style mid = *st;
	int sb = it->flags & OSD_PWR_STANDBY, only = it->flags & OSD_PWR_OFF_ONLY;
	double left = clampd(it->value, 0, 150) / 150.0, k = 2.1 * u, ox = 172 * u, bw = 42 * u, cx, cy;

	if (only)
		sb = 0;
	mid.place = OSD_CENTER;
	s->lw = 2.0 * u;
	place_box(s, c, &mid, u, only ? 220 * u : 520 * u, 210 * u);
	cx = s->px + s->pw / 2, cy = s->py + s->ph / 2;
	ring(s, cx, cy, 70 * u, left);
	number_c(s, (it->value + 9) / 10, cx, cy - 22 * u, 44 * u);
	if (only)
		return;
	moon_icon(s, cx - ox, cy, k, sb ? T_BRIGHT : T_DIM);
	power_icon(s, cx + ox, cy, k, sb ? T_DIM : T_BRIGHT);
	seg(s, (sb ? cx - ox : cx + ox) - bw / 2, cy + 44 * u, (sb ? cx - ox : cx + ox) + bw / 2, cy + 44 * u, T_BRIGHT);
}

/* every item is one strip of lines; in the pill look a dark translucent panel with fully rounded ends lies
 * behind it, in the bare look a soft shadow around each line. No square card: the owner rejected it on
 * 11.10.2026 ("rounded backgrounds that are completely rectangular do not work"), the pill he kept. */
static void layout(struct scene *s, const struct osd_canvas *c, const struct osd_style *st,
		   const struct osd_item *it)
{
	double u = c->h / 1080.0 * (st->scale > 0 ? st->scale : 1), k = 1.38 * u, cy, w;
	int v = (int)clampd(it->value, 0, 100);

	memset(s, 0, sizeof(*s));
	s->lw = 1.6 * u;
	s->dim = DIM;
	s->pill_a = 0.46;
	s->pill_rgb = 0x0a0c10;
	s->panel = st->look == OSD_PILL;

	if (it->kind == OSD_MUTE_BADGE) {
		double d = 64 * u;

		s->panel = st->look == OSD_PILL ? 2 : 0;
		s->pw = s->ph = d;
		s->px = st->place == OSD_TOP_RIGHT ? 48 * u : c->w - 48 * u - d;
		s->py = 48 * u;
		speaker(s, s->px + d / 2 - 4 * u, s->py + d / 2, 1.25 * u, 0, 1);
		return;
	}
	if (it->kind == OSD_POWER) {
		power_layout(s, c, st, it, u);
		return;
	}
	w = it->kind == OSD_VOLUME || it->kind == OSD_MUTE ? 540 * u : it->kind == OSD_FOCUS ? 196 * u :
	    it->kind == OSD_PAIR ? 324 * u : 220 * u;
	place_box(s, c, st, u, w, 76 * u);
	cy = s->py + 38 * u;		/* the icons: about 50 px high at 1080 lines */

	switch (it->kind) {
	case OSD_VOLUME:
	case OSD_MUTE: {
		int mute = it->kind == OSD_MUTE, first;

		speaker(s, s->px + 60 * u, cy, k, v, mute);
		first = s->n;
		number(s, v, s->px + s->pw - 32 * u, cy - 15 * u, 30 * u);
		bar(s, s->px + 118 * u, s->px + s->pw - 116 * u, cy, v);
		if (mute)	/* the volume is kept, not heard: its digits and bar stay, dim */
			for (int i = first; i < s->n; i++)
				s->p[i].tone = T_DIM;
		break;
	}
	case OSD_FOCUS:		/* larger than the other icons: it is the only content of its strip (Marco 11.10.) */
		focus_icon(s, s->px + s->pw / 2 + 2 * u, cy, 1.95 * u, it->value >= 0 ? 1 : -1, it->flags & OSD_EDGE);
		break;
	case OSD_INPUT:
		hdmi_icon(s, s->px + 60 * u, cy, k, it->value != 0);
		console_icon(s, s->px + s->pw - 60 * u, cy, k, it->value == 0);
		break;
	case OSD_PAIR: {	/* the rune, then "hold Left + Right"; around the rune the time left */
		double bx = s->px + 58 * u, kk = 1.9 * u;

		bt_icon(s, bx, cy, k, T_BRIGHT);
		if (it->value > 0)
			ring(s, bx, cy, 28 * u, it->value / 100.0);
		key_icon(s, s->px + 158 * u, cy, kk, -1, T_BRIGHT);
		seg(s, s->px + 210 * u, cy - 9 * u, s->px + 210 * u, cy + 9 * u, T_BRIGHT);
		seg(s, s->px + 201 * u, cy, s->px + 219 * u, cy, T_BRIGHT);
		key_icon(s, s->px + 262 * u, cy, kk, 1, T_BRIGHT);
		break;
	}
	default:
		break;
	}
}

/* --- mixing --------------------------------------------------------------------------------------------- */

static double cover(double d, double aa)
{
	return clampd(0.5 - d / aa, 0, 1);
}

void osd_clear(struct osd_canvas *c)
{
	for (int y = 0; y < c->h; y++)
		memset(c->px + (size_t)y * c->stride, 0, (size_t)c->w * 4);
}

void osd_clear_box(struct osd_canvas *c, const int box[4])
{
	for (int y = box[1]; y < box[1] + box[3] && y < c->h; y++)
		if (y >= 0 && box[0] >= 0 && box[0] + box[2] <= c->w)
			memset(c->px + (size_t)y * c->stride + box[0], 0, (size_t)box[2] * 4);
}

#ifdef OSD_PROFILE
#include <time.h>
double osd_prof[3];	/* seconds in: the work buffer's fill, the primitives, the mixing */
static double prof_now(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}
#define PROF(i, t) (osd_prof[i] += prof_now() - (t), (t) = prof_now())
#else
#define PROF(i, t) ((void)0)
#endif

/* the scene's rectangle, with a margin for the shadow, mixed over the canvas: every primitive's distance per pixel,
 * then the panel (or the shadow) and the lines; box = the rectangle touched. u: one unit of the layout in pixels */
static void render(struct osd_canvas *c, const struct scene *sc, double u, double fade, int box[4])
{
#ifdef OSD_PROFILE
	double pt = prof_now();
#endif
	static double *dist;	/* the nearest edge per tone and pixel of the item's rectangle */
	static size_t dcap;
	const struct scene s = *sc;
	double shadow = 14 * u, reach;
	int x0, y0, x1, y1, bw, bh;
	size_t n;

	x0 = (int)floor(s.px - shadow), y0 = (int)floor(s.py - shadow);
	x1 = (int)ceil(s.px + s.pw + shadow), y1 = (int)ceil(s.py + s.ph + shadow);
	x0 = x0 < 0 ? 0 : x0, y0 = y0 < 0 ? 0 : y0;
	x1 = x1 > c->w ? c->w : x1, y1 = y1 > c->h ? c->h : y1;
	if (box)
		box[0] = x0, box[1] = y0, box[2] = x1 - x0, box[3] = y1 - y0;
	bw = x1 - x0, bh = y1 - y0;
	if (bw <= 0 || bh <= 0)
		return;
	n = (size_t)bw * bh;
	if (3 * n > dcap) {
		double *nd = realloc(dist, 3 * n * sizeof(*dist));

		if (!nd)
			return;
		dist = nd, dcap = 3 * n;
	}
	for (size_t i = 0; i < 3 * n; i++)
		dist[i] = 1e9;
	PROF(0, pt);
	/*
	 * Each primitive only within its own rectangle: beyond `reach` it adds nothing - no coverage, no shadow -
	 * so the picture is the same as with every primitive at every pixel (osd-mockup compared, bit for bit),
	 * at a fraction of the work (11.10.2026 on the board: the volume strip from 209 ms).
	 */
	reach = AA + (s.panel ? 0 : 3 * u + shadow) + 1;
	for (int i = 0; i < s.n; i++) {
		double *t = dist + (size_t)s.p[i].tone * n, b[4];
		int bx0, by0, bx1, by1;

		double lw = s.p[i].lw ? s.p[i].lw : s.lw;

		prim_bbox(&s.p[i], reach + lw, b);
		bx0 = (int)floor(b[0]), by0 = (int)floor(b[1]), bx1 = (int)ceil(b[2]), by1 = (int)ceil(b[3]);
		bx0 = bx0 < x0 ? x0 : bx0, by0 = by0 < y0 ? y0 : by0;
		bx1 = bx1 > x1 ? x1 : bx1, by1 = by1 > y1 ? y1 : by1;
		for (int y = by0; y < by1; y++)
			for (int x = bx0; x < bx1; x++) {
				double *q = t + (size_t)(y - y0) * bw + (x - x0);

				*q = fmin(*q, prim_dist(&s.p[i], x + 0.5, y + 0.5, lw));
			}
	}

	PROF(1, pt);
	/*
	 * The layers - the panel or the shadow, the white lines, the red ones - are mixed premultiplied onto what
	 * the canvas holds, in one pass, and turned back into straight alpha once at the end: one division per
	 * pixel instead of three per layer. Most pixels of a pill are its plain inside: per row the stretch where
	 * the pill covers fully and the one where it does not reach are known from its shape (a stadium: half
	 * circles of radius h/2 on a straight middle), a line counts only nearer than half the anti-aliasing, and a
	 * pixel with nothing but the panel over a clear canvas gets its value without mixing (11.10.2026 on the
	 * board: the volume strip's mixing from 12 ms).
	 */
	const double half = AA / 2, pill_a = s.pill_a * fade;
	const uint32_t pill_px = (uint32_t)(pill_a * 255 + 0.5) << 24 | s.pill_rgb;
	const double pr = s.pill_rgb >> 16 & 255, pg = s.pill_rgb >> 8 & 255, pb = s.pill_rgb & 255;

	for (int y = y0; y < y1; y++) {
		double fy = y + 0.5, cx = s.px + s.pw / 2, inner = -1, outer = 1e9;

		if (s.panel == 1) {	/* |x - cx| <= inner: covered fully; >= outer: not at all */
			double r = s.ph / 2, dy = fabs(fy - (s.py + r)), L = s.pw / 2 - r;

			inner = dy <= r - half ? L + sqrt((r - half) * (r - half) - dy * dy) : -1;
			outer = dy < r + half ? L + sqrt((r + half) * (r + half) - dy * dy) : -1;
		}
		for (int x = x0; x < x1; x++) {
			size_t k = (size_t)(y - y0) * bw + (x - x0);
			double fx = x + 0.5, t[3] = { dist[k], dist[n + k], dist[2 * n + k] }, la[3], lc0, A, R, G, B, inv;
			uint32_t *px = c->px + (size_t)y * c->stride + x, v;
			bool lines = t[T_BRIGHT] < half || t[T_DIM] < half || t[T_RED] < half;

			if (s.panel == 1) {
				double ax = fabs(fx - cx);

				la[0] = ax <= inner ? pill_a : ax >= outer ? 0 :
					pill_a * cover(rrect_sd(fx, fy, cx, s.py + s.ph / 2, s.pw / 2, s.ph / 2, s.ph / 2), AA);
				lc0 = 1;
			} else if (s.panel == 2) {
				double dx = fx - s.px - s.pw / 2, dy = fy - s.py - s.ph / 2;

				la[0] = 0.38 * fade * cover(sqrt(dx * dx + dy * dy) - s.pw / 2, AA);
				lc0 = 1;
			} else if (s.panel == 3) {	/* nothing behind the lines (a menu row that is not the chosen one) */
				la[0] = 0;
				lc0 = 0;
			} else {	/* the bare look: a soft shadow around every line keeps it legible on a bright picture */
				double all = fmin(t[T_BRIGHT], fmin(t[T_DIM], t[T_RED]));

				la[0] = all - 3 * u >= shadow / 2 ? 0 : 0.62 * fade * cover(all - 3 * u, shadow) *
					(t[T_DIM] < fmin(t[T_BRIGHT], t[T_RED]) ? 0.7 : 1);
				lc0 = 0;
			}
			if (!lines) {
				if (la[0] <= 0)
					continue;
				if (!*px && s.panel == 1 && la[0] == pill_a) {
					*px = pill_px;		/* the plain inside of the pill */
					continue;
				}
				la[1] = la[2] = 0;
			} else {
				la[1] = 0.94 * fade * fmax(cover(t[T_BRIGHT], AA), s.dim * cover(t[T_DIM], AA));
				la[2] = 0.96 * fade * cover(t[T_RED], AA);
				if (la[0] <= 0 && la[1] <= 0 && la[2] <= 0)
					continue;
			}
			v = *px;
			A = (v >> 24) / 255.0;
			R = (v >> 16 & 255) * A, G = (v >> 8 & 255) * A, B = (v & 255) * A;
			if (la[0] > 0) {	/* the panel's colour (10, 12, 16), or the shadow's black */
				R = pr * lc0 * la[0] + R * (1 - la[0]);
				G = pg * lc0 * la[0] + G * (1 - la[0]);
				B = pb * lc0 * la[0] + B * (1 - la[0]);
				A = la[0] + A * (1 - la[0]);
			}
			if (la[1] > 0) {
				R = 250 * la[1] + R * (1 - la[1]), G = 250 * la[1] + G * (1 - la[1]);
				B = 250 * la[1] + B * (1 - la[1]), A = la[1] + A * (1 - la[1]);
			}
			if (la[2] > 0) {
				R = 255 * la[2] + R * (1 - la[2]), G = 72 * la[2] + G * (1 - la[2]);
				B = 64 * la[2] + B * (1 - la[2]), A = la[2] + A * (1 - la[2]);
			}
			if (A <= 0) {
				*px = 0;
				continue;
			}
			inv = 1 / A;
			*px = (uint32_t)(A * 255 + 0.5) << 24 | (uint32_t)fmin(R * inv + 0.5, 255) << 16 |
			      (uint32_t)fmin(G * inv + 0.5, 255) << 8 | (uint32_t)fmin(B * inv + 0.5, 255);
		}
	}
	PROF(2, pt);
}

/* --- the menu: the symbols, a row and a hint (the launcher and its opaque page) ---------------------------- */

static const char *const ICON_NAME[OSD_ICONS] = { "hdmi", "film", "globe", "desk", "sliders", "power" };

int osd_icon_by_name(const char *name)
{
	for (int i = 0; name && i < OSD_ICONS; i++)
		if (!strcmp(name, ICON_NAME[i]))
			return i;
	return -1;
}

/* a cubic Bezier through the symbol's coordinates (p: four points x, y) as a chain of segments */
static void bezier(struct scene *s, double ox, double oy, double k, const double p[8], int tone)
{
	double px = ox + p[0] * k, py = oy + p[1] * k;

	for (int i = 1; i <= 8; i++) {
		double t = i / 8.0, m = 1 - t, a = m * m * m, b = 3 * m * m * t, c = 3 * m * t * t, d = t * t * t;
		double x = ox + (a * p[0] + b * p[2] + c * p[4] + d * p[6]) * k;
		double y = oy + (a * p[1] + b * p[3] + c * p[5] + d * p[7]) * k;

		seg(s, px, py, x, y, tone);
		px = x, py = y;
	}
}

/* one symbol of the mock-up's set (Strichsymbole in a box of 48 units, origin ox, oy, k pixels a unit) */
static void micon(struct scene *s, int icon, double ox, double oy, double k, int tone)
{
#define X(v) (ox + (v) * k)
#define Y(v) (oy + (v) * k)
	switch (icon) {
	case OSD_ICON_HDMI: {		/* a plug: the shell, two legs, the bar */
		static const double c[] = { 9, 17, 39, 17, 39, 25, 35, 30, 13, 30, 9, 25 };

		for (int i = 0; i < 6; i++)
			seg(s, X(c[2 * i]), Y(c[2 * i + 1]), X(c[2 * ((i + 1) % 6)]), Y(c[2 * ((i + 1) % 6) + 1]), tone);
		seg(s, X(17), Y(30), X(17), Y(35), tone);
		seg(s, X(31), Y(30), X(31), Y(35), tone);
		seg(s, X(15), Y(22), X(33), Y(22), tone);
		break;
	}
	case OSD_ICON_FILM:		/* a screen with a play triangle */
		rrect(s, P_RRECT_LINE, X(24), Y(24), 16 * k, 13 * k, 5 * k, tone);
		seg(s, X(21), Y(19.5), X(21), Y(28.5), tone);
		seg(s, X(21), Y(28.5), X(29), Y(24), tone);
		seg(s, X(29), Y(24), X(21), Y(19.5), tone);
		break;
	case OSD_ICON_GLOBE: {
		static const double l[] = { 24, 10, 19, 15, 19, 33, 24, 38 }, r[] = { 24, 10, 29, 15, 29, 33, 24, 38 };

		arc(s, X(24), Y(24), 14 * k, 0, 360, tone);
		seg(s, X(10), Y(24), X(38), Y(24), tone);
		bezier(s, ox, oy, k, l, tone);
		bezier(s, ox, oy, k, r, tone);
		break;
	}
	case OSD_ICON_DESK:		/* a monitor on its stand */
		rrect(s, P_RRECT_LINE, X(24), Y(21), 16 * k, 11 * k, 4 * k, tone);
		seg(s, X(18), Y(38), X(30), Y(38), tone);
		seg(s, X(24), Y(32), X(24), Y(38), tone);
		break;
	case OSD_ICON_SLIDERS: {	/* three tracks with a knob each; the track stops at the knob */
		static const double ky[] = { 15, 24, 33 }, kx[] = { 18, 31, 22 };

		for (int i = 0; i < 3; i++) {
			seg(s, X(10), Y(ky[i]), X(kx[i] - 3.6), Y(ky[i]), tone);
			seg(s, X(kx[i] + 3.6), Y(ky[i]), X(38), Y(ky[i]), tone);
			arc(s, X(kx[i]), Y(ky[i]), 3.6 * k, 0, 360, tone);
		}
		break;
	}
	case OSD_ICON_POWER:		/* IEC 60417-5009: a ring open at the top, the stroke through the gap */
		seg(s, X(24), Y(10), X(24), Y(23), tone);
		arc(s, X(24), Y(24.665), 12.5 * k, 312.8, 587.2, tone);
		break;
	}
#undef X
#undef Y
}

void osd_draw_row(struct osd_canvas *c, const struct osd_row *r, int box[4])
{
	static struct scene s;
	double u = c->h / 1080.0, f = r->h * u / 104;	/* f: this row in units of the launcher's 104-line pill */

	memset(&s, 0, sizeof(s));
	s.lw = 2.4 * f;
	s.dim = 0.447;		/* 0.94 * 0.447 = the mock-up's 42 % white */
	s.pill_a = 1.0;		/* the lit pill of the opaque page: a little lighter than the ground (h713-settings' PAGEPILL) */
	s.pill_rgb = OSD_PAGE_PILL;
	s.panel = r->selected ? 1 : 3;
	s.px = r->x * u, s.py = r->y * u, s.pw = r->w * u, s.ph = r->h * u;
	if (r->selected) {
		rrect(&s, P_RRECT_LINE, s.px + s.pw / 2, s.py + s.ph / 2, s.pw / 2, s.ph / 2, s.ph / 2, T_BRIGHT);
		s.p[s.n - 1].lw = 1.5 * f;
	}
	micon(&s, r->icon, s.px + 32 * f, s.py + 16 * f, 1.5 * f, r->selected ? T_BRIGHT : T_DIM);
	render(c, &s, u, 1.0, box);
	osd_text(c, r->label, s.px + 132 * f, s.py + 65 * f, 38 * f, 0xfafafa, r->selected ? 0.94f : 0.42f, s.pw - 160 * f);
}

void osd_draw_hint(struct osd_canvas *c, double x, double baseline, const char *text, int arrows)
{
	static struct scene s;
	double u = c->h / 1080.0, x0 = x * u, y0 = baseline * u;

	if (arrows) {		/* the marks for up and down as shapes: the face has neither */
		memset(&s, 0, sizeof(s));
		s.lw = 1.5 * u;
		s.dim = 0.447;
		s.panel = 3;
		s.px = x0, s.py = y0 - 26 * u, s.pw = 60 * u, s.ph = 30 * u;
		for (int d = 0; d < 2; d++)	/* d 0: up, 1: down; three outlines inside each other make it solid */
			for (int k = 0; k < 3; k++) {
				double cx = x0 + (11 + 28 * d) * u, cy = y0 - 9 * u, dir = d ? 1 : -1, f = u * (1 - 0.36 * k);

				seg(&s, cx, cy + dir * 8 * f, cx - 9 * f, cy - dir * 6 * f, T_DIM);
				seg(&s, cx - 9 * f, cy - dir * 6 * f, cx + 9 * f, cy - dir * 6 * f, T_DIM);
				seg(&s, cx + 9 * f, cy - dir * 6 * f, cx, cy + dir * 8 * f, T_DIM);
			}
		render(c, &s, u, 1.0, NULL);
	}
	osd_text(c, text, x0 + (arrows ? 68 * u : 0), y0, 26 * u, 0xffffff, 0.42f, 0);
}

/* a rectangle (x, y, w, h, clipped to the canvas) set to one colour, REPLACING what was there */
static void fill_box(struct osd_canvas *c, const int box[4], uint32_t argb)
{
	int x0 = box[0] < 0 ? 0 : box[0], x1 = box[0] + box[2] > c->w ? c->w : box[0] + box[2];
	int y0 = box[1] < 0 ? 0 : box[1], y1 = box[1] + box[3] > c->h ? c->h : box[1] + box[3];

	for (int y = y0; y < y1; y++)
		for (int x = x0; x < x1; x++)
			c->px[(size_t)y * c->stride + x] = argb;
}

/* --- the launcher: a column on the left edge, cut into bands that repaint on their own ------------------------------- */

#define LAU_COLUMN	700	/* the column the list stands in (the tiles' left part), 1080-line units */
#define LAU_FIRST	194	/* the first pill's top */
#define LAU_PITCH	124	/* from one pill to the next */
#define LAU_FOOT_PILL	844	/* the last row of the group at the foot sits with its top here, as in the mock-up */
#define LAU_FOOT	958	/* the hint's band starts here */

/* the pills' tops and every band's top and bottom, in 1080-line units: band 0 the header (down to the first pill's top less
 * 10), band 1 + i row i (10 above its pill to 10 below: 124, so the rows tile), band n + 1 the foot, band n + 2 the gap that
 * is left between the rows at the top and those at the foot (empty when there is none). Returns the count of bands. */
static int lau_geometry(const struct osd_launcher *l, double top[OSD_LAUNCHER_ROWS], double y0[OSD_LAUNCHER_ROWS + 3],
			double y1[OSD_LAUNCHER_ROWS + 3])
{
	int n = l->n < OSD_LAUNCHER_ROWS ? l->n : OSD_LAUNCHER_ROWS, ne = 0, ti = 0, ej = 0;
	double gap0 = LAU_FIRST - 10, gap1 = LAU_FOOT;

	for (int i = 0; i < n; i++)
		ne += l->row[i].end != 0;
	for (int i = 0; i < n; i++) {
		top[i] = l->row[i].end ? LAU_FOOT_PILL - LAU_PITCH * (ne - 1 - ej++) : LAU_FIRST + LAU_PITCH * ti++;
		y0[i + 1] = top[i] - 10, y1[i + 1] = top[i] + 114;
		if (!l->row[i].end)
			gap0 = y1[i + 1];
		else if (gap1 == LAU_FOOT && ej == 1)
			gap1 = y0[i + 1];
	}
	y0[0] = 0, y1[0] = LAU_FIRST - 10;
	y0[n + 1] = LAU_FOOT, y1[n + 1] = 1080;
	y0[n + 2] = gap0, y1[n + 2] = gap1 > gap0 ? gap1 : gap0;
	return n + 3;
}

int osd_launcher_bands(const struct osd_canvas *c, const struct osd_launcher *l, int box[][4])
{
	double top[OSD_LAUNCHER_ROWS], y0[OSD_LAUNCHER_ROWS + 3], y1[OSD_LAUNCHER_ROWS + 3], u = c->h / 1080.0;
	int bands = lau_geometry(l, top, y0, y1), colw = (int)ceil(LAU_COLUMN * u);

	if (l->n < 1)
		return 0;
	/* the header starts at the top of the canvas and the foot runs to its bottom; the rest is rounded once, so bands that meet in
	 * units meet in pixels. Tile k < bands is the band's left part (the column, where its content is), tile bands + k the right
	 * part (the calm rest of the page, to the canvas' right edge) */
	for (int k = 0; k < bands; k++) {
		int a = k == 0 ? 0 : (int)floor(y0[k] * u + 0.5), b = k == bands - 2 ? c->h : (int)floor(y1[k] * u + 0.5);

		box[k][0] = 0, box[k][1] = a, box[k][2] = colw < c->w ? colw : c->w, box[k][3] = b > a ? b - a : 0;
		box[bands + k][0] = box[k][2], box[bands + k][1] = a, box[bands + k][2] = c->w - box[k][2], box[bands + k][3] = box[k][3];
	}
	return 2 * bands;
}

void osd_launcher_draw(struct osd_canvas *c, const struct osd_launcher *l, int tile)
{
	int box[2 * (OSD_LAUNCHER_ROWS + 3)][4], tiles = osd_launcher_bands(c, l, box), bands = tiles / 2;
	double top[OSD_LAUNCHER_ROWS], y0[OSD_LAUNCHER_ROWS + 3], y1[OSD_LAUNCHER_ROWS + 3], u = c->h / 1080.0;
	int n = bands - 3, band = tile % (bands ? bands : 1);

	if (tile < 0 || tile >= tiles || !box[tile][2] || !box[tile][3])
		return;
	lau_geometry(l, top, y0, y1);
	fill_box(c, box[tile], OSD_PAGE_GROUND);
	if (tile >= bands)			/* the right part: the ground alone, nothing shows through */
		return;
	if (band == 0) {
		osd_text(c, l->head, 150 * u, 140 * u, 30 * u, 0xffffff, 0.42f, 0);
	} else if (band <= n) {
		struct osd_row r = { l->row[band - 1].icon, l->row[band - 1].label, band - 1 == l->sel, 118, top[band - 1], 520, 104 };

		osd_draw_row(c, &r, NULL);
	} else if (band == n + 1) {
		osd_draw_hint(c, 150, 1010, "select \xc2\xb7 OK open \xc2\xb7 BACK close", 1);
	}					/* band n + 2: the ground alone */
}

/* --- the page without a signal: a ground, the plug, two lines in the middle ------------------------------------------- */

/* the bands' edges in 1080-line units: the ground above, the middle band with the symbol and the words, the ground below */
static const double NOSIG_EDGE[OSD_NOSIGNAL_TILES + 1] = { 0, 330, 720, 1080 };

int osd_nosignal_bands(const struct osd_canvas *c, int box[][4])
{
	double u = c->h / 1080.0;

	for (int k = 0; k < OSD_NOSIGNAL_TILES; k++) {
		int a = k == 0 ? 0 : (int)floor(NOSIG_EDGE[k] * u + 0.5);
		int b = k == OSD_NOSIGNAL_TILES - 1 ? c->h : (int)floor(NOSIG_EDGE[k + 1] * u + 0.5);

		box[k][0] = 0, box[k][1] = a, box[k][2] = c->w, box[k][3] = b > a ? b - a : 0;
	}
	return OSD_NOSIGNAL_TILES;
}

void osd_nosignal_draw(struct osd_canvas *c, int tile, int quiet)
{
	static const char TITLE[] = "No signal on HDMI", HINT[] = "HOME: menu";
	static struct scene s;
	int box[OSD_NOSIGNAL_TILES][4];
	double u = c->h / 1080.0, cx = c->w / 2.0, k = 3.0 * u;
	int tiles = osd_nosignal_bands(c, box);

	if (tile < 0 || tile >= tiles || !box[tile][2] || !box[tile][3])
		return;
	fill_box(c, box[tile], OSD_PAGE_GROUND);
	if (tile != OSD_NOSIGNAL_MIDDLE || quiet)	/* the ground alone */
		return;
	/* the plug of the HDMI symbol, 144 units wide, its middle at 450; the strokes are the launcher's, drawn larger */
	memset(&s, 0, sizeof(s));
	s.lw = 4.8 * u;
	s.dim = 0.447;
	s.panel = 3;
	s.px = cx - 24 * k, s.py = 450 * u - 26 * k, s.pw = 48 * k, s.ph = 48 * k;
	micon(&s, OSD_ICON_HDMI, s.px, s.py, k, T_BRIGHT);
	render(c, &s, u, 1.0, NULL);
	osd_text(c, TITLE, cx - osd_text_width(TITLE, 70 * u) / 2, 600 * u, 70 * u, 0xfafafa, 0.94f, 0);
	osd_text(c, HINT, cx - osd_text_width(HINT, 38 * u) / 2, 668 * u, 38 * u, 0xffffff, 0.6f, 0);
}

void osd_draw(struct osd_canvas *c, const struct osd_style *st, const struct osd_item *it, int box[4])
{
	static struct scene s;

	layout(&s, c, st, it);
	render(c, &s, c->h / 1080.0 * (st->scale > 0 ? st->scale : 1), clampd(it->alpha, 0, 1), box);
}
