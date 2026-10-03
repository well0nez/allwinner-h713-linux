/* SPDX-License-Identifier: GPL-2.0 */
/*
 * T2 (AP2d test plan): h713-warp's matrix IS the vendor's matrix.
 *
 * The driver reads the vectors and the expected numbers of matrix_ref.py --
 * which computes them with the AP2f reference model, the tested port of
 * getKeyStoneMatrix -- from stdin and compares them with what
 * h713-warp/matrix.c makes of the same eight per-mille values:
 *
 *     python3 matrix_ref.py | ./test_matrix
 *
 * Tolerances are AP2d T2's: the sixteen floats to 1e-6, the four transformed
 * corner positions to 1e-5. The clamp and the range check are tested with the
 * same reference in the same run ("c" and "r" lines).
 *
 * The projection modes ("f" lines, FB-MIRROR): the reference lands six source
 * points the VENDOR's way - the insets permuted into the slots of the mounted
 * picture as LocalService does, the matrix solved on them, the source flipped
 * underneath as the firmware flips the frame - and h713-warp's F * K (the wall
 * keystone first, warp_mirror after) must put every point at the same place
 * to 1e-5. Negative control: in any mode but front the flipped map must move
 * at least one corner away from where the unflipped keystone puts it, and in
 * front none (an inset of 450 per-mille leaves a corner 0.1 from the centre,
 * so its flip moves it by 0.2 - the threshold is 0.05).
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../warp.h"

#define TOL_M	1e-6
#define TOL_P	1e-5

static long checked, failed;

static double next_number(char **p)
{
	return strtod(*p, p);
}

static void complain(const char *what, int i, const int *v, double got,
		     double want)
{
	if (failed++ < 10)
		printf("FAIL %s[%d] %d %d %d %d %d %d %d %d: %.17g != %.17g\n",
		       what, i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
		       got, want);
}

static void line_matrix(char *p)
{
	double want[16], point[8], m[16], q[2], c[2];
	int v[WARP_KEYS], i;

	for (i = 0; i < WARP_KEYS; i++)
		v[i] = (int)next_number(&p);
	for (i = 0; i < 16; i++)
		want[i] = next_number(&p);
	for (i = 0; i < 8; i++)
		point[i] = next_number(&p);
	if (!warp_matrix(v, m)) {
		complain("refused", 0, v, 0, 0);
		return;
	}
	for (i = 0; i < 16; i++)
		if (fabs(m[i] - want[i]) > TOL_M)
			complain("matrix", i, v, m[i], want[i]);
	for (i = 0; i < 4; i++) {
		warp_corner_ndc(i, c);
		warp_point(m, c[0], c[1], q);
		if (fabs(q[0] - point[2 * i]) > TOL_P)
			complain("corner x", i, v, q[0], point[2 * i]);
		if (fabs(q[1] - point[2 * i + 1]) > TOL_P)
			complain("corner y", i, v, q[1], point[2 * i + 1]);
	}
	checked++;
}

static void line_clamp(char *p)
{
	int v[WARP_KEYS], want[WARP_KEYS], i;

	for (i = 0; i < WARP_KEYS; i++)
		v[i] = (int)next_number(&p);
	for (i = 0; i < WARP_KEYS; i++)
		want[i] = (int)next_number(&p);
	warp_clamp(v);
	for (i = 0; i < WARP_KEYS; i++)
		if (v[i] != want[i])
			complain("clamp", i, want, v[i], want[i]);
	checked++;
}

#define FLIP_POINTS	6

/* f MODE V0..V7 X0 Y0 .. X5 Y5: the four corners tl tr bl br, the centre and
 * (0.3, -0.7), where the vendor's permuted slots under the firmware's flip put
 * them; ours is warp_mirror(mode, warp_matrix(v)) */
static void line_flip(char *p)
{
	static const double src[FLIP_POINTS][2] = {
		{ -1, -1 }, { 1, -1 }, { -1, 1 }, { 1, 1 }, { 0, 0 }, { 0.3, -0.7 },
	};
	double want[2 * FLIP_POINTS], m[16], k[16], q[2], u[2];
	int v[WARP_KEYS], mode, i, moved = 0;

	mode = (int)next_number(&p);
	for (i = 0; i < WARP_KEYS; i++)
		v[i] = (int)next_number(&p);
	for (i = 0; i < 2 * FLIP_POINTS; i++)
		want[i] = next_number(&p);
	if (mode < 0 || mode > 3 || !warp_matrix(v, k)) {
		complain("flip refused", mode, v, 0, 0);
		return;
	}
	memcpy(m, k, sizeof(m));
	warp_mirror(mode, m);
	for (i = 0; i < FLIP_POINTS; i++) {
		warp_point(m, src[i][0], src[i][1], q);
		if (fabs(q[0] - want[2 * i]) > TOL_P)
			complain("flip x", mode * 10 + i, v, q[0], want[2 * i]);
		if (fabs(q[1] - want[2 * i + 1]) > TOL_P)
			complain("flip y", mode * 10 + i, v, q[1], want[2 * i + 1]);
		warp_point(k, src[i][0], src[i][1], u);
		if (i < 4 && (fabs(q[0] - u[0]) > 0.05 || fabs(q[1] - u[1]) > 0.05))
			moved++;
	}
	/* the negative control (see the head of this file) */
	if (mode ? moved < 1 : moved != 0)
		complain("flip moved corners", mode, v, moved, mode ? 1 : 0);
	checked++;
}

/* the names and the four flips themselves, with no reference needed */
static void mode_table(void)
{
	static const char *const names[4] = { "front", "rear", "ceiling", "rear-ceiling" };
	static const double sx[4] = { 1, -1, -1, 1 }, sy[4] = { 1, 1, -1, -1 };
	int mode, i, bad = 0;

	for (mode = 0; mode < 4; mode++) {
		double m[16] = { 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1 };

		bad += warp_mode_by_name(names[mode]) != mode;
		bad += strcmp(warp_mode_name[mode], names[mode]) != 0;
		warp_mirror(mode, m);
		for (i = 0; i < 16; i++) {
			double want = i == 0 ? sx[mode] : i == 5 ? sy[mode] : (i % 5 == 0);

			bad += m[i] != want;
		}
	}
	bad += warp_mode_by_name("hv") != -1;
	bad += warp_mode_by_name("Front") != -1;
	bad += warp_mode_by_name("") != -1;
	bad += warp_mode_by_name(NULL) != -1;
	if (bad) {
		printf("FAIL mode table: %d of the names or flips are wrong\n", bad);
		failed++;
	}
	checked++;
}

static void line_reject(char *p)
{
	double m[16];
	int v[WARP_KEYS], i;

	for (i = 0; i < WARP_KEYS; i++)
		v[i] = (int)next_number(&p);
	if (warp_matrix(v, m))
		complain("accepted", 0, v, 1, 0);
	checked++;
}

int main(void)
{
	char line[4096];

	mode_table();
	while (fgets(line, sizeof(line), stdin)) {
		char *p = line + 1;

		if (line[0] == 'm')
			line_matrix(p);
		else if (line[0] == 'c')
			line_clamp(p);
		else if (line[0] == 'r')
			line_reject(p);
		else if (line[0] == 'f')
			line_flip(p);
		else if (line[0] != '\n' && line[0] != '#')
			printf("FAIL unknown line: %s", line);
	}
	printf("%s T2 matrix: %ld vectors, %ld deviations (16 floats to %g, corners to %g; the four projection modes against the vendor's permuted slots)\n",
	       failed ? "FAIL" : "ok", checked, failed, TOL_M, TOL_P);

	return failed || !checked ? 1 : 0;
}
