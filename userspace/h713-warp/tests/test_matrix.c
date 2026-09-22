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
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../h713-warp/warp.h"

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

	while (fgets(line, sizeof(line), stdin)) {
		char *p = line + 1;

		if (line[0] == 'm')
			line_matrix(p);
		else if (line[0] == 'c')
			line_clamp(p);
		else if (line[0] == 'r')
			line_reject(p);
		else if (line[0] != '\n' && line[0] != '#')
			printf("FAIL unknown line: %s", line);
	}
	printf("%s T2 matrix: %ld vectors, %ld deviations (16 floats to %g, corners to %g)\n",
	       failed ? "FAIL" : "ok", checked, failed, TOL_M, TOL_P);

	return failed || !checked ? 1 : 0;
}
