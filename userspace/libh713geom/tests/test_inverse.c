/* SPDX-License-Identifier: GPL-2.0 */
/*
 * T4: the way back (inverse.c). For the identity, for one-corner and two-corner pulls and for 200 random
 * keystones (clamped the vendor's way), in all four projection modes, every point of a 9 x 9 grid over the
 * source goes through warp_point() and back through warp_unpoint() and has to land where it started, to 1e-9.
 * A matrix of zeros has no inverse and has to be refused.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "../geom.h"

void warn(const char *fmt, ...) { (void)fmt; }

static long checked, failed;
static double worst;

static void round_trip(const int v[WARP_KEYS], int mode)
{
	double m[16], h[9], p[2], q[2];
	int ix, iy;

	if (!warp_matrix(v, m)) {
		printf("FAIL the matrix refused a clamped keystone\n");
		failed++;
		return;
	}
	warp_mirror(mode, m);
	if (!warp_inverse(m, h)) {
		printf("FAIL no inverse for a valid keystone (mode %d)\n", mode);
		failed++;
		return;
	}
	for (iy = 0; iy <= 8; iy++)
		for (ix = 0; ix <= 8; ix++) {
			double x = -1 + ix / 4.0, y = -1 + iy / 4.0, e;

			warp_point(m, x, y, p);
			warp_unpoint(h, p[0], p[1], q);
			e = fmax(fabs(q[0] - x), fabs(q[1] - y));
			if (!(e <= 1e-9)) {
				if (failed < 5)
					printf("FAIL (%g, %g) mode %d came back as (%g, %g)\n", x, y, mode, q[0], q[1]);
				failed++;
			}
			worst = fmax(worst, e);
			checked++;
		}
}

int main(void)
{
	static const int fixed[][WARP_KEYS] = {
		{ 0 }, { 100, 0, 0, 0, 0, 0, 0, 0 }, { 0, 100, 0, 0, 0, 0, 0, 0 }, { 0, 0, 0, 0, 0, 0, 0, 100 },
		{ 100, 100, 0, 0, 0, 0, 100, 100 }, { 250, 0, 250, 0, 0, 0, 0, 0 }, { 0, 0, 0, 0, 0, 120, 0, 120 },
	};
	double m[16] = { 0 }, h[9], p[2];
	unsigned int seed = 12345;
	int v[WARP_KEYS], mode;
	size_t i;

	for (i = 0; i < sizeof(fixed) / sizeof(fixed[0]); i++)
		for (mode = 0; mode < 4; mode++)
			round_trip(fixed[i], mode);
	for (i = 0; i < 200; i++) {
		for (int k = 0; k < WARP_KEYS; k++) {
			seed = seed * 1103515245u + 12345u;
			v[k] = (int)(seed >> 16) % 301;	/* 0..300 per mille */
		}
		warp_clamp(v);
		for (mode = 0; mode < 4; mode++)
			round_trip(v, mode);
	}
	/* the identity's way back is the identity */
	memset(v, 0, sizeof(v));
	warp_matrix(v, m);
	warp_inverse(m, h);
	warp_unpoint(h, 0.3, -0.7, p);
	if (fabs(p[0] - 0.3) > 1e-12 || fabs(p[1] + 0.7) > 1e-12) {
		printf("FAIL the identity maps (0.3, -0.7) to (%g, %g)\n", p[0], p[1]);
		failed++;
	}
	memset(m, 0, sizeof(m));
	if (warp_inverse(m, h)) {
		printf("FAIL a matrix of zeros was inverted\n");
		failed++;
	}
	printf("%s T4 inverse: %ld points through warp_point and back, worst %.1e, %ld deviations\n",
	       failed ? "FAIL" : "ok", checked, worst, failed);
	return failed ? 1 : 0;
}
