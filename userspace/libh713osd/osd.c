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
	double a[10];		/* the shape's numbers, see prim_dist */
};

struct scene {
	struct prim p[MAXP];
	int n;
	double lw;		/* half the line width of icons and digits, px */
	double px, py, pw, ph;	/* the item's box: left, top, width, height */
	int panel;		/* behind the lines: 0 nothing (the bare look), 1 the pill, 2 the badge's disc */
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
	w = it->kind == OSD_VOLUME || it->kind == OSD_MUTE ? 540 * u : it->kind == OSD_FOCUS ? 196 * u : 220 * u;
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

void osd_draw(struct osd_canvas *c, const struct osd_style *st, const struct osd_item *it, int box[4])
{
#ifdef OSD_PROFILE
	double pt = prof_now();
#endif
	static struct scene s;
	static double *dist;	/* the nearest edge per tone and pixel of the item's rectangle */
	static size_t dcap;
	double u = c->h / 1080.0 * (st->scale > 0 ? st->scale : 1), shadow = 14 * u;
	double fade = clampd(it->alpha, 0, 1), reach;
	int x0, y0, x1, y1, bw, bh;
	size_t n;

	layout(&s, c, st, it);
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

		prim_bbox(&s.p[i], reach + s.lw, b);
		bx0 = (int)floor(b[0]), by0 = (int)floor(b[1]), bx1 = (int)ceil(b[2]), by1 = (int)ceil(b[3]);
		bx0 = bx0 < x0 ? x0 : bx0, by0 = by0 < y0 ? y0 : by0;
		bx1 = bx1 > x1 ? x1 : bx1, by1 = by1 > y1 ? y1 : by1;
		for (int y = by0; y < by1; y++)
			for (int x = bx0; x < bx1; x++) {
				double *q = t + (size_t)(y - y0) * bw + (x - x0);

				*q = fmin(*q, prim_dist(&s.p[i], x + 0.5, y + 0.5, s.lw));
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
	const double half = AA / 2, pill_a = 0.46 * fade;
	const uint32_t pill_px = (uint32_t)(pill_a * 255 + 0.5) << 24 | 10u << 16 | 12u << 8 | 16u;

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
				la[1] = 0.94 * fade * fmax(cover(t[T_BRIGHT], AA), DIM * cover(t[T_DIM], AA));
				la[2] = 0.96 * fade * cover(t[T_RED], AA);
				if (la[0] <= 0 && la[1] <= 0 && la[2] <= 0)
					continue;
			}
			v = *px;
			A = (v >> 24) / 255.0;
			R = (v >> 16 & 255) * A, G = (v >> 8 & 255) * A, B = (v & 255) * A;
			if (la[0] > 0) {	/* the panel's colour (10, 12, 16), or the shadow's black */
				R = 10 * lc0 * la[0] + R * (1 - la[0]);
				G = 12 * lc0 * la[0] + G * (1 - la[0]);
				B = 16 * lc0 * la[0] + B * (1 - la[0]);
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
