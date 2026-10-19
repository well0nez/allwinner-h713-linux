// SPDX-License-Identifier: GPL-2.0
#ifndef _GNU_SOURCE
#define _GNU_SOURCE		/* as in main.c and color.c */
#endif
/*
 * h713-tv -- the gamma curve and the colour temperature, computed the way the display firmware's picture library does.
 *
 * The vendor's library keeps nine raw curves of the panel (one per colour temperature, three channels of 1024 samples,
 * 12 bit, measured and stored in the board's TSE file). A gamma level 0..4 is the exponent (180, 200, 210, 220, 240)/100/2.2
 * laid on a raw curve, and after the first start the curve is not computed sample by sample any more: the power law is
 * taken at twelve knots, the knots may be moved by the factory menu's 33 points, and a cubic Bezier through the twelve
 * knots makes the 1024 samples. The library sends the 33 points (all 0 on this board) after every start and every
 * resume, so that form is the one the panel is always shown with. This file does that arithmetic in the same order of
 * operations, so that the same raw curve gives the same 12-bit samples (checked sample for sample against an independent
 * description of the library in Python, see tests/test_gamma.c).
 *
 * What is NOT here: where the raw curves come from (h713-pq reads the TSE, main.c reads its file) and how a finished
 * curve reaches the CRTC (main.c). The second half of the file is the control: level, colour temperature, the picture
 * mode's wish, the file "werte" and the text of ctl.
 */
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>

#include "gamma.h"

/* the gamma factor of a level: the library's table, level 0..4 -> 1.8 2.0 2.1 2.2 2.4 */
static const unsigned int level_factor[GAMMA_LEVELS] = { 180, 200, 210, 220, 240 };

/* where the twelve knots of the Bezier form are, and the eleven the factory menu moves (5 % 10 % 20 % ... 100 %) */
#define GAMMA_KNOTS	12
static const int knot_x[GAMMA_KNOTS] = { 0, 51, 102, 204, 306, 409, 511, 613, 716, 818, 920, 1023 };

/* ------------------------------------------------------------------ *
 * The conversions the library's code does, written out
 * ------------------------------------------------------------------ */

/* (unsigned)double then the low 16 bits: toward zero, saturating, NaN and negative 0 */
static uint16_t to_u16(double v)
{
	if (!(v > 0.0))
		return 0;
	if (v >= 4294967295.0)
		return 0xffff;

	return (uint16_t)(uint32_t)v;
}

/* the low 16 bits as a signed number */
static int sxth(int v)
{
	v &= 0xffff;

	return v & 0x8000 ? v - 0x10000 : v;
}

/* a knot value plus its offset: 4095 and above is 4095, then 0 and below is 0 (a sum that overflows 16 bits ends in 0) */
static unsigned int clamp_knot(int value, int offset)
{
	int s = value + offset;

	if (sxth(s) >= GAMMA_MAX)
		s = GAMMA_MAX;
	if (sxth(s) <= 0)
		s = 0;

	return (unsigned int)s & 0xffffu;
}

/* ------------------------------------------------------------------ *
 * a t^3 + b t^2 + c t + d = 0
 *
 * Newton's method from the ends and, when the curve has extremes, from the middles of the three intervals they make;
 * -1 marks "no root here". The order of the operations is the library's (every operation rounds on its own).
 * ------------------------------------------------------------------ */

#define EPS	0.00001
#define BIG	10000.0

static double cub(double x, double a, double b, double c, double d)
{
	return ((x * c) + ((x * (x * b)) + (x * (x * (x * a))))) + d;
}

static double cub_slope(double x, double a3, double b2, double c)
{
	return ((b2 * x) + (x * (a3 * x))) + c;
}

/* Newton from x; the caller has seen that |f(x)| is above EPS. -1: no luck within 500 steps, or a flat spot */
static double newton(double x, double a, double b, double c, double d, double a3, double b2)
{
	unsigned int n = 0;

	for (;;) {
		double fp;

		if ((n >> 2) > 0x7c)
			return -1.0;
		fp = cub_slope(x, a3, b2, c);
		if (fp == 0.0)
			return -1.0;
		n++;
		x = x - cub(x, a, b, c, d) / fp;
		if (!(fabs(cub(x, a, b, c, d)) > EPS))
			return x;
	}
}

static double root_from(double x0, double fx0, double a, double b, double c, double d, double a3, double b2)
{
	if (!(fabs(fx0) > EPS))
		return x0;

	return newton(x0, a, b, c, d, a3, b2);
}

static void solve3(double a, double b, double c, double d, double r[3])
{
	double disc, sq, lo, hi, v;
	double bb, aaa, cc, f_lo, f_hi, f_lo_ext, f_hi_ext, a3, b2, x0;

	r[0] = r[1] = r[2] = -1.0;
	if (d == 0.0) {
		/* the knot itself: t = 0 is a root, and the rest comes from the quadratic */
		r[0] = 0.0;
		if (a != 0.0) {
			disc = (b * b) + ((a * -4.0) * c);
			if (disc < 0.0)
				return;
			if (disc == 0.0) {
				r[1] = r[2] = (b * -0.5) / a;
				return;
			}
			sq = sqrt(disc);
			lo = ((-b - sq) * 0.5) / a;
			hi = ((sq - b) * 0.5) / a;
			if (hi >= lo) {
				r[1] = lo;
				r[2] = hi;
			} else {
				r[1] = hi;
				r[2] = lo;
			}
			return;
		}
		if (b == 0.0)
			return;
		if (c == 0.0)
			r[1] = r[2] = 0.0;
		else
			r[1] = r[2] = (-c) / b;
		return;
	}

	if (a == 0.0) {
		if (b == 0.0) {
			if (c == 0.0)
				return;
			v = (-d) / c;
			r[0] = r[1] = v;
			return;
		}
		disc = (c * c) + ((b * -4.0) * d);
		if (disc < 0.0)
			return;
		if (disc == 0.0) {
			r[0] = r[1] = (c * -0.5) / b;
			return;
		}
		sq = sqrt(disc);
		lo = ((-c - sq) * 0.5) / b;
		hi = ((sq - c) * 0.5) / b;
		if (hi >= lo) {
			r[0] = lo;
			r[1] = hi;
		} else {
			r[0] = hi;
			r[1] = lo;
		}
		return;
	}

	/* a and d are not 0: the cubic proper. f(-BIG) and f(+BIG) first, then the extremes */
	bb = (b * BIG) * BIG;
	aaa = ((a * BIG) * BIG) * BIG;
	cc = c * BIG;
	f_lo = ((bb - aaa) - cc) + d;
	a3 = a * 3.0;
	b2 = b + b;
	r[0] = root_from(-BIG, f_lo, a, b, c, d, a3, b2);

	if (a3 == 0.0) {
		/* a is so small that 3a is 0: only for completeness */
		if (b2 == 0.0) {
			double z = 0.0;

			x0 = 0.0;
			r[0] = root_from(x0, ((c * z) + ((((a * z) * z) * z) + ((b * z) * z))) + d, a, b, c, d, a3, b2);
			return;
		}
		if (c == 0.0)
			lo = hi = 0.0;
		else
			lo = hi = (-c) / b2;
	} else {
		disc = (b2 * b2) + ((a3 * -4.0) * c);
		if (disc < 0.0) {
			/* no extremes: the curve is monotone, and Newton from 0 replaces the first root */
			double z = 0.0;

			r[0] = root_from(0.0, ((c * z) + ((((a * z) * z) * z) + ((b * z) * z))) + d, a, b, c, d, a3, b2);
			return;
		}
		if (disc == 0.0) {
			lo = hi = (b2 * -0.5) / a3;
		} else {
			double x1, x2;

			sq = sqrt(disc);
			x1 = ((-b2 - sq) * 0.5) / a3;
			x2 = ((sq - b2) * 0.5) / a3;
			if (x2 >= x1) {
				lo = x1;
				hi = x2;
			} else {
				lo = x2;
				hi = x1;
			}
		}
	}

	f_lo_ext = cub(lo, a, b, c, d);
	if (f_lo * f_lo_ext < 0.0) {
		x0 = (lo + -BIG) * 0.5;
		r[0] = root_from(x0, cub(x0, a, b, c, d), a, b, c, d, a3, b2);
	}
	f_hi_ext = cub(hi, a, b, c, d);
	if (f_lo_ext * f_hi_ext < 0.0) {
		x0 = (lo + hi) * 0.5;
		r[1] = root_from(x0, cub(x0, a, b, c, d), a, b, c, d, a3, b2);
	}
	f_hi = (cc + (aaa + bb)) + d;
	if (f_hi * f_hi_ext < 0.0) {
		x0 = (hi + BIG) * 0.5;
		r[2] = root_from(x0, cub(x0, a, b, c, d), a, b, c, d, a3, b2);
	}
}

/* ------------------------------------------------------------------ *
 * The Bezier form: n knots (x ascending, y 12 bit) -> 1024 samples
 *
 * y is quartered inside (so that x, 0..1023, and y, 0..1023.75, have about the same scale and the distances below are
 * real distances) and multiplied by 4 at the end. Every segment is one cubic Bezier with the Catmull-Rom control points
 * (a sixth of the chord to the neighbours, a third at the two ends), the tangents cut to half the segment's chord;
 * for every whole x in the segment t comes from the cubic above and y from the curve at t.
 * ------------------------------------------------------------------ */

static void bezier_fit(const int *xs, const unsigned int *ys, unsigned int n, double out[GAMMA_N])
{
	int v7 = xs[0] - 1;
	unsigned int i;

	for (i = 0; i < GAMMA_N; i++)
		out[i] = 0.0;
	if (n < 2)
		return;
	for (i = 0; i + 1 < n; i++) {
		double x1, y1, x2, y2, x3, y3, x4, y4;
		double d13, d24, half, p1x, p1y, p2x, p2y, p3x, p3y, p4x, p4y;
		double t3p2, t3p1, ca, cb, cc;
		bool ok13, ok24;
		int end;

		if (i) {
			x1 = (double)xs[i - 1];
			y1 = (double)ys[i - 1] * 0.25;
		} else {
			x1 = (double)xs[0];
			y1 = (double)ys[0] * 0.25;
		}
		x2 = (double)xs[i];
		y2 = (double)ys[i] * 0.25;
		x3 = (double)xs[i + 1];
		y3 = (double)ys[i + 1] * 0.25;
		if (i + 2 >= n) {
			x4 = x3;
			y4 = y3;
		} else {
			x4 = (double)xs[i + 2];
			y4 = (double)ys[i + 2] * 0.25;
		}

		d13 = sqrt(((x1 - x3) * (x1 - x3)) + ((y1 - y3) * (y1 - y3)));
		d24 = sqrt(((x2 - x4) * (x2 - x4)) + ((y2 - y4) * (y2 - y4)));
		half = sqrt(((x2 - x3) * (x2 - x3)) + ((y2 - y3) * (y2 - y3))) * 0.5;
		ok13 = (d13 / 6.0) < half;
		ok24 = (d24 / 6.0) < half;
		if (ok13 && ok24) {
			double k = (x1 == x2 && y1 == y2) ? 3.0 : 6.0, qx, qy;

			p2x = (x3 - x1) / k + x2;
			p2y = (y3 - y1) / k + y2;
			if (y4 == y3 && x4 == x3) {
				qx = (x4 - x2) / 3.0;
				qy = (y4 - y2) / 3.0;
			} else {
				qx = (x4 - x2) / 6.0;
				qy = (y4 - y2) / 6.0;
			}
			p3x = x3 - qx;
			p3y = y3 - qy;
		} else if (!ok13 && !ok24) {
			double s2 = half / d13, s3 = half / d24;

			p2x = (x3 - x1) * s2 + x2;
			p3x = (x2 - x4) * s3 + x3;
			p2y = (y3 - y1) * s2 + y2;
			p3y = (y2 - y4) * s3 + y3;
		} else {
			double s = ok13 ? half / d24 : half / d13;

			p2x = (x3 - x1) * s + x2;
			p3x = (x2 - x4) * s + x3;
			p2y = (y3 - y1) * s + y2;
			p3y = (y2 - y4) * s + y3;
		}
		p1x = x2;
		p1y = y2;
		p4x = x3;
		p4y = y3;

		t3p2 = p2x * 3.0;
		t3p1 = p1x * 3.0;
		ca = p4x + ((t3p2 - p1x) - p3x * 3.0);
		cb = (t3p1 + p2x * -6.0) + p3x * 3.0;
		cc = t3p2 - t3p1;

		end = xs[i + 1];
		while (v7 < end) {
			double xv, r[3], y, t, u, t3, b1, b2, b3, b4;

			v7++;
			xv = (double)v7;
			solve3(ca, cb, cc, p1x - xv, r);
			if (r[2] > 1.0)
				r[2] = -1.0;
			if (r[1] > 1.0)
				r[1] = -1.0;
			if (r[0] > 1.0)
				r[0] = -1.0;
			if (r[0] < 0.0 && r[1] < 0.0 && r[2] < 0.0) {
				/* no root in 0..1: the straight line between the two knots */
				y = (p1y * ((p4x - xv) / (p4x - p1x)) + ((xv - p1x) / (p4x - p1x)) * p4y) * 4.0;
			} else {
				t = r[0];
				if (r[0] < 0.0)
					t = r[1] > 0.0 ? r[1] : r[0];
				if (r[2] > 0.0 && t < 0.0)
					t = r[2];
				u = 1.0 - t;
				t3 = t * 3.0;
				b1 = u * (u * u);
				b2 = u * (t3 * u);
				b3 = u * (t * t3);
				b4 = t * (t * t);
				y = ((((b1 * p1y) + (b2 * p2y)) + (b3 * p3y)) + (b4 * p4y)) * 4.0;
				if (y > 4095.0)
					y = 4095.0;
				if (y < 0.0)
					y = 0.0;
			}
			if (v7 >= 0 && v7 < GAMMA_N)
				out[v7] = y;
		}
	}
}

/* ------------------------------------------------------------------ *
 * The curve
 * ------------------------------------------------------------------ */

/* the exponent of a level; the library's order: (factor / 100) / 2.2 */
static double level_exponent(unsigned int level)
{
	return ((double)level_factor[level] / 100.0) / 2.2;
}

/* a channel's end point must not be 0: the samples are divided by it */
static bool ends_ok(const gamma_curve base)
{
	return base[0][GAMMA_N - 1] && base[1][GAMMA_N - 1] && base[2][GAMMA_N - 1];
}

bool gamma_compute_pow(const gamma_curve base, unsigned int level, gamma_curve out)
{
	double g, ends[3];
	unsigned int c, x;

	if (level >= GAMMA_LEVELS || !ends_ok(base))
		return false;
	g = level_exponent(level);
	for (c = 0; c < 3; c++)
		ends[c] = (double)base[c][GAMMA_N - 1];
	for (c = 0; c < 3; c++)
		for (x = 0; x < GAMMA_N; x++)
			out[c][x] = to_u16(pow((double)base[c][x] / ends[c], g) * ends[c]);

	return true;
}

bool gamma_compute(const gamma_curve base, unsigned int level, const int *points, gamma_curve out)
{
	unsigned int ys[3][GAMMA_KNOTS];
	int offs[3][GAMMA_KNOTS] = { { 0 } };
	double g, ends[3], curve[GAMMA_N];
	unsigned int c, k, i;

	if (level >= GAMMA_LEVELS || !ends_ok(base))
		return false;
	/* the factory menu's points, knot after knot, red green blue each; the knot at 0 never moves */
	for (i = 0; points && i < GAMMA_POINTS; i++)
		offs[i % 3][i / 3 + 1] = sxth(points[i]);
	g = level_exponent(level);
	for (c = 0; c < 3; c++)
		ends[c] = (double)base[c][GAMMA_N - 1];
	for (c = 0; c < 3; c++)
		for (k = 0; k < GAMMA_KNOTS; k++) {
			uint16_t v = to_u16(pow((double)base[c][knot_x[k]] / ends[c], g) * ends[c]);

			ys[c][k] = clamp_knot(sxth(v), offs[c][k]);
		}
	for (c = 0; c < 3; c++) {
		bezier_fit(knot_x, ys[c], GAMMA_KNOTS, curve);
		for (i = 0; i < GAMMA_N; i++)
			out[c][i] = to_u16(curve[i]);
	}

	return true;
}

void gamma_pack(const gamma_curve lut, uint8_t out[GAMMA_BYTES])
{
	unsigned int c, i, o = 0;

	for (c = 0; c < 3; c++)
		for (i = 0; i < GAMMA_N / 2; i++) {
			uint32_t w = ((uint32_t)(lut[c][2 * i + 1] & 0xfff) << 12) | (lut[c][2 * i] & 0xfff);

			out[o++] = (uint8_t)w;
			out[o++] = (uint8_t)(w >> 8);
			out[o++] = (uint8_t)(w >> 16);
			out[o++] = (uint8_t)(w >> 24);
		}
}

uint32_t gamma_crc32(const uint8_t *p, size_t n)
{
	uint32_t crc = 0xffffffffu;
	size_t i;
	int b;

	for (i = 0; i < n; i++) {
		crc ^= p[i];
		for (b = 0; b < 8; b++)
			crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
	}

	return ~crc;
}

/*
 * The arithmetic is only the vendor's if every multiplication and every addition rounds on its own. A compiler that
 * is allowed to fuse them (-ffp-contract on a machine with a fused multiply-add: the board's arm64) changes the last
 * bit, and that moves a sample now and then. The product of a and b is exact only when it is not rounded first.
 */
bool gamma_arith_ok(void)
{
	volatile double v = 1.0 + 0x1p-30;	/* volatile: nothing here is a constant to fold */
	double a = v, b = v, c = -(1.0 + 0x1p-29);

	return a * b + c == 0.0;
}

/* ------------------------------------------------------------------ *
 * The raw curves of the board
 * ------------------------------------------------------------------ */

#define BASE_HEAD	16
#define BASE_MAGIC	"H7GS"

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int gamma_base_read(struct gamma_base *b, const char *path, char *why, size_t n)
{
	uint8_t head[BASE_HEAD], buf[2 * GAMMA_N];
	unsigned int s, c, i, left = 0, usable = 0;
	uint32_t mask;
	FILE *f;
	long size;

	memset(b, 0, sizeof(*b));
	f = fopen(path, "rb");
	if (!f) {
		snprintf(why, n, "%s: %s", path, strerror(errno));
		return 0;
	}
	if (fread(head, 1, sizeof(head), f) != sizeof(head) || memcmp(head, BASE_MAGIC, 4)) {
		snprintf(why, n, "%s is not a file of the board's curves", path);
		fclose(f);
		return 0;
	}
	if (le32(head + 4) != 1) {
		snprintf(why, n, "%s: version %u, this program knows 1", path, le32(head + 4));
		fclose(f);
		return 0;
	}
	mask = le32(head + 8);
	if (!mask || mask >> GAMMA_SLOTS) {
		snprintf(why, n, "%s: the list of states (0x%x) is empty or names a state above %d", path, mask, GAMMA_SLOTS - 1);
		fclose(f);
		return 0;
	}
	for (s = 0; s < GAMMA_SLOTS; s++)
		left += (mask >> s) & 1u;
	if (fseek(f, 0, SEEK_END) || (size = ftell(f)) < 0 || (unsigned long)size != BASE_HEAD + (unsigned long)left * sizeof(gamma_curve) ||
	    fseek(f, BASE_HEAD, SEEK_SET)) {
		snprintf(why, n, "%s is not %u states long", path, left);
		fclose(f);
		return 0;
	}
	b->project = le32(head + 12);
	why[0] = '\0';
	for (s = 0; s < GAMMA_SLOTS; s++) {
		bool bad = false;

		if (!(mask >> s & 1u))
			continue;
		for (c = 0; c < 3; c++) {
			if (fread(buf, 1, sizeof(buf), f) != sizeof(buf)) {
				snprintf(why, n, "%s ends early", path);
				fclose(f);
				memset(b, 0, sizeof(*b));
				return 0;
			}
			for (i = 0; i < GAMMA_N; i++) {
				unsigned int v = buf[2 * i] | (unsigned int)buf[2 * i + 1] << 8;

				if (v > GAMMA_MAX)
					bad = true;
				b->slot[s][c][i] = (uint16_t)v;
			}
		}
		if (bad) {
			snprintf(why, n, "state %u has a sample above %d - left out", s, GAMMA_MAX);
		} else if (!ends_ok(b->slot[s])) {
			snprintf(why, n, "state %u ends in 0 in a channel - left out", s);
		} else {
			b->mask |= 1u << s;
			usable++;
			continue;
		}
		memset(b->slot[s], 0, sizeof(b->slot[s]));
	}
	fclose(f);
	if (!usable && !why[0])
		snprintf(why, n, "no usable state in %s", path);

	return (int)usable;
}

/* ------------------------------------------------------------------ *
 * The control
 *
 *   gamma               0..4       the exponent 1.8 2.0 2.1 2.2 2.4 over 2.2 on the raw curve of the colour temperature
 *   colour_temperature  auto       the raw curve the picture mode asks for (the vendor's own rule: cinema and hdr warm,
 *                                  vivid cool, the rest normal), or normal, cool, warm
 *
 * A board whose TSE has fewer states (cool or warm missing) gets the normal curve instead, and the journal says so.
 * ------------------------------------------------------------------ */

static const char *const temp_name[GAMMA_T_N] = { "auto", "normal", "cool", "warm" };
static const char *const slot_name[GAMMA_SLOTS] = {
	"normal", "cool", "warm", "user", "warmer", "cooler", "expert_1", "expert_2", "computer",
};
static const char *const gamma_name[GAMMA_LEVELS] = { "1.8", "2.0", "2.1", "2.2", "2.4" };

static struct {
	struct gamma_io io;
	bool attached;
	char why[200];		/* why the control is not there */
	struct gamma_base base;
	int level, temp;	/* what is wanted */
	int mode_slot;		/* the colour temperature of the picture mode */
	bool on;		/* a curve of ours is on the CRTC ... */
	int slot, on_level;	/* ... this one */
	uint32_t crc;
	double ms;
	unsigned int applies, failures;
	char last[200];		/* the last refusal */
	int said;		/* the missing state the journal has said so about: want * 16 + got, -1 none */
} g = { .level = GAMMA_LEVEL_DEFAULT, .temp = GAMMA_T_AUTO, .said = -1 };

void gamma_init(void)
{
	memset(&g, 0, sizeof(g));
	g.level = GAMMA_LEVEL_DEFAULT;
	g.temp = GAMMA_T_AUTO;
	g.said = -1;
}

void gamma_adopt(const bool *have, const int *value)
{
	if (have[0] && value[0] >= 0 && value[0] < GAMMA_LEVELS)
		g.level = value[0];
	if (have[1] && value[1] >= 0 && value[1] < GAMMA_T_N)
		g.temp = value[1];
	if (g.level != GAMMA_LEVEL_DEFAULT || g.temp != GAMMA_T_AUTO)
		info("saved           gamma %s, colour temperature %s", gamma_name[g.level], temp_name[g.temp]);
}

static int want_slot(void)
{
	return g.temp == GAMMA_T_AUTO ? g.mode_slot : g.temp - GAMMA_T_NORMAL;
}

/* the state that is used for the wanted one: itself, or the lowest there is (normal) */
static int use_slot(int want)
{
	int s;

	if (g.base.mask >> want & 1u)
		return want;
	for (s = 0; s < GAMMA_SLOTS; s++)
		if (g.base.mask >> s & 1u)
			return s;

	return 0;
}

static void states_text(char *buf, size_t n)
{
	size_t l = 0;
	int s;

	buf[0] = '\0';
	for (s = 0; s < GAMMA_SLOTS && l + 1 < n; s++)
		if (g.base.mask >> s & 1u)
			l += (size_t)snprintf(buf + l, n - l, "%s%s", l ? " " : "", slot_name[s]);
}

/* the colour temperature as a person reads it: what was asked, and what is in force when that is something else */
static void temp_text(char *buf, size_t n)
{
	int want = want_slot(), got = use_slot(want);

	if (g.temp == GAMMA_T_AUTO)
		snprintf(buf, n, "auto (%s)", slot_name[got]);
	else if (got != want)
		snprintf(buf, n, "%s (%s: this board has no %s curve)", temp_name[g.temp], slot_name[got], temp_name[g.temp]);
	else
		snprintf(buf, n, "%s", temp_name[g.temp]);
}

/*
 * Compute what is wanted and put it on the CRTC if that is not what is there. force: also then (the start, where
 * nothing of ours is there yet).
 */
static bool refresh(const char *why, bool force, char *msg, size_t n)
{
	int want = want_slot(), got = use_slot(want);
	gamma_curve *lut;
	uint8_t *bytes;
	struct timespec t0, t1;
	char text[120], states[120];
	bool ok = false;

	if (got != want) {
		if (g.said != want * 16 + got) {
			g.said = want * 16 + got;
			states_text(states, sizeof(states));
			info("gamma           %s is not among this board's curves (%s) -- %s applies", slot_name[want], states, slot_name[got]);
		}
	} else {
		g.said = -1;
	}
	if (!force && g.on && got == g.slot && g.level == g.on_level)
		return true;
	lut = malloc(sizeof(*lut));
	bytes = malloc(GAMMA_BYTES);
	if (!lut || !bytes) {
		snprintf(msg, n, "out of memory");
		goto out;
	}
	clock_gettime(CLOCK_MONOTONIC, &t0);
	if (!gamma_compute(g.base.slot[got], (unsigned int)g.level, NULL, *lut)) {
		snprintf(msg, n, "the curve of %s cannot be computed", slot_name[got]);
		goto out;
	}
	if (!g.io.apply((const uint16_t (*)[GAMMA_N])*lut, msg, n)) {
		g.failures++;
		snprintf(g.last, sizeof(g.last), "%s", msg);
		goto out;
	}
	clock_gettime(CLOCK_MONOTONIC, &t1);
	gamma_pack((const uint16_t (*)[GAMMA_N])*lut, bytes);
	g.on = true;
	g.slot = got;
	g.on_level = g.level;
	g.crc = gamma_crc32(bytes, GAMMA_BYTES);
	g.ms = (double)(t1.tv_sec - t0.tv_sec) * 1e3 + (double)(t1.tv_nsec - t0.tv_nsec) / 1e6;
	g.applies++;
	temp_text(text, sizeof(text));
	info("gamma           level %d (%s), colour temperature %s, after %s: curve %08x, %.1f ms", g.level, gamma_name[g.level], text, why,
	     g.crc, g.ms);
	ok = true;
out:
	free(lut);
	free(bytes);

	return ok;
}

bool gamma_attach(const char *slots, const struct gamma_io *io, char *why, size_t n)
{
	char note[200] = "", states[120];
	int usable;

	g.attached = false;
	g.io = *io;
	if (!gamma_arith_ok()) {
		snprintf(why, n, "this build rounds a multiplication and an addition together; the vendor's arithmetic is not reproduced");
		snprintf(g.why, sizeof(g.why), "%s", why);
		return false;
	}
	usable = gamma_base_read(&g.base, slots, note, sizeof(note));
	if (!usable) {
		snprintf(why, n, "%s", note);
		snprintf(g.why, sizeof(g.why), "%s", note);
		return false;
	}
	if (note[0])
		warn("gamma           %s", note);
	g.attached = true;
	g.why[0] = '\0';
	states_text(states, sizeof(states));
	info("gamma           this board's own curves (ProjectID 0x%02x): %s", g.base.project, states);

	return true;
}

void gamma_unavailable(const char *why)
{
	g.attached = false;
	snprintf(g.why, sizeof(g.why), "%s", why);
}

bool gamma_start(void)
{
	char msg[200] = "";

	if (!g.attached)
		return false;
	if (refresh("the start", true, msg, sizeof(msg)))
		return true;
	warn("gamma           the start: %s", msg);
	g.attached = false;
	snprintf(g.why, sizeof(g.why), "the start: %s", msg);

	return false;
}

bool gamma_active(void)
{
	return g.attached;
}

void gamma_mode_temp(int slot, const char *why)
{
	char msg[200] = "";

	if (slot < 0 || slot >= GAMMA_SLOTS)
		return;
	g.mode_slot = slot;
	/* refresh() sends nothing when the curve in force is the one wanted, so a mode said twice costs nothing - and a
	 * curve the CRTC refused is tried again with the next mode */
	if (!g.attached || g.temp != GAMMA_T_AUTO || !g.on)
		return;
	if (!refresh(why, false, msg, sizeof(msg)))
		warn("gamma           after %s: %s", why, msg);
}

/* ---- ctl ---- */

int gamma_key(const char *name)
{
	if (!strcmp(name, "gamma"))
		return 0;
	if (!strcmp(name, "colour_temperature"))
		return 1;

	return -1;
}

/* "0".."4", or the exponent in the form the menu shows it: 1.8 2.0 2.1 2.2 2.4 */
static bool parse_level(const char *s, int *out)
{
	unsigned int i;
	char *end;
	long v;

	if (!s || !*s)
		return false;
	if (strchr(s, '.')) {
		for (i = 0; i < GAMMA_LEVELS; i++)
			if (!strcmp(s, gamma_name[i])) {
				*out = (int)i;
				return true;
			}
		return false;
	}
	errno = 0;
	v = strtol(s, &end, 10);
	if (end == s || *end || errno || v < 0 || v >= GAMMA_LEVELS)
		return false;
	*out = (int)v;

	return true;
}

/* a name, or its place in the list (auto 0, normal 1, cool 2, warm 3) */
static bool parse_temp(const char *s, int *out)
{
	unsigned int i;
	char *end;
	long v;

	if (!s || !*s)
		return false;
	for (i = 0; i < GAMMA_T_N; i++)
		if (!strcasecmp(s, temp_name[i])) {
			*out = (int)i;
			return true;
		}
	if (!strcasecmp(s, "standard")) {
		*out = GAMMA_T_NORMAL;
		return true;
	}
	errno = 0;
	v = strtol(s, &end, 10);
	if (end == s || *end || errno || v < 0 || v >= GAMMA_T_N)
		return false;
	*out = (int)v;

	return true;
}

static const char *const key_name[2] = { "gamma", "colour_temperature" };

void gamma_get(struct reply *r, int idx)
{
	char text[160];

	if (!g.attached) {
		reply_fail(r, "%s is not available: %s", key_name[idx], g.why[0] ? g.why : "the board's curves were not read");
		return;
	}
	if (idx == 0) {
		reply_add(r, "ok gamma = %d (%s)\n", g.level, gamma_name[g.level]);
		return;
	}
	temp_text(text, sizeof(text));
	reply_add(r, "ok colour_temperature = %s\n", text);
}

void gamma_set(struct reply *r, int idx, const char *value)
{
	int old_level = g.level, old_temp = g.temp, v;
	char msg[200] = "";

	if (!g.attached) {
		reply_fail(r, "%s is not available: %s", key_name[idx], g.why[0] ? g.why : "the board's curves were not read");
		return;
	}
	if (idx == 0) {
		if (!parse_level(value, &v)) {
			reply_fail(r, "gamma does not know \"%s\" - possible: 0..4 or 1.8 2.0 2.1 2.2 2.4", value);
			return;
		}
		g.level = v;
	} else {
		if (!parse_temp(value, &v)) {
			reply_fail(r, "colour_temperature does not know \"%s\" - possible: auto normal cool warm", value);
			return;
		}
		g.temp = v;
	}
	if (!refresh(idx == 0 ? "ctl set gamma" : "ctl set colour_temperature", false, msg, sizeof(msg))) {
		g.level = old_level;
		g.temp = old_temp;
		reply_fail(r, "%s = %s: %s", key_name[idx], value, msg);
		return;
	}
	gamma_get(r, idx);
}

void gamma_list(struct reply *r)
{
	char text[160];

	if (!g.attached)
		return;
	reply_add(r, "  %-26s %d (%s)  menu 0..%d\n", "gamma", g.level, gamma_name[g.level], GAMMA_LEVELS - 1);
	temp_text(text, sizeof(text));
	reply_add(r, "  %-26s %s  menu auto|normal|cool|warm\n", "colour_temperature", text);
}

void gamma_status(struct reply *r)
{
	char text[160], states[120];

	if (!g.attached) {
		reply_add(r, "gamma           not available: %s\n", g.why[0] ? g.why : "the board's curves were not read");
		return;
	}
	temp_text(text, sizeof(text));
	states_text(states, sizeof(states));
	reply_add(r, "gamma           level %d (%s), colour temperature %s; curves of ProjectID 0x%02x: %s\n", g.level, gamma_name[g.level], text,
		  g.base.project, states);
	if (g.on)
		reply_add(r, "                on the CRTC: %s, level %d, curve %08x (%.1f ms, %u sent, %u refused)\n", slot_name[g.slot], g.on_level, g.crc,
			  g.ms, g.applies, g.failures);
	else
		reply_add(r, "                NOT on the CRTC yet%s%s\n", g.last[0] ? ": " : "", g.last);
}

/* ---- the file werte ---- */

int gamma_parse_kept(const char *key, const char *value, int *idx, int *out)
{
	int k = gamma_key(key), v;

	if (k < 0)
		return 0;
	if (!(k == 0 ? parse_level(value, &v) : parse_temp(value, &v)))
		return -1;
	*idx = k;
	*out = v;

	return 1;
}

size_t gamma_kept_lines(FILE *f, char *msg, size_t n, size_t l)
{
	if (!g.attached && g.level == GAMMA_LEVEL_DEFAULT && g.temp == GAMMA_T_AUTO)
		return l;
	fprintf(f, "# gamma 0..4 (1.8 2.0 2.1 2.2 2.4) and the colour temperature: auto, normal, cool or warm\n");
	fprintf(f, "gamma       = %d\ncolour_temperature = %s\n", g.level, temp_name[g.temp]);
	if (l + 1 < n)
		l += (size_t)snprintf(msg + l, n - l, " gamma=%d colour_temperature=%s", g.level, temp_name[g.temp]);

	return l;
}
