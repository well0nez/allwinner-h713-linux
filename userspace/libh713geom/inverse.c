/* SPDX-License-Identifier: GPL-2.0 */
/*
 * From the panel back to the source (TODO 2.44). The warp draws a source point (x, y) at the panel point
 * warp_point(m, x, y): the column-major 4 x 4 with the quad's z = -1 folded in is a plane homography
 *
 *	| m0  m4  m12 - m8  |
 *	| m1  m5  m13 - m9  |	(x, y, 1) -> divide by the third row
 *	| m3  m7  m15 - m11 |
 *
 * and its inverse answers the overlay's question: which point of the straight overlay belongs at this panel
 * pixel, so that the overlay stands in the picture as if the warp had drawn it. h713-warp does not use this
 * file; h713-osd walks its overlay's outline on the panel with it (tests/test_inverse.c checks the round trip).
 */
#include <math.h>

#include "geom.h"

bool warp_inverse(const double m[16], double h[9])
{
	double a = m[0], b = m[4], c = m[12] - m[8];
	double d = m[1], e = m[5], f = m[13] - m[9];
	double g = m[3], k = m[7], i = m[15] - m[11];
	double det = a * (e * i - f * k) - b * (d * i - f * g) + c * (d * k - e * g);

	if (!isfinite(det) || fabs(det) < 1e-12)
		return false;
	h[0] = (e * i - f * k) / det;
	h[1] = (c * k - b * i) / det;
	h[2] = (b * f - c * e) / det;
	h[3] = (f * g - d * i) / det;
	h[4] = (a * i - c * g) / det;
	h[5] = (c * d - a * f) / det;
	h[6] = (d * k - e * g) / det;
	h[7] = (b * g - a * k) / det;
	h[8] = (a * e - b * d) / det;
	return true;
}

/* a panel point (NDC) back to its source point (NDC); not finite where the panel point has no source (it lies
 * on the horizon of the homography, far outside any keystone the clamp allows) */
void warp_unpoint(const double h[9], double x, double y, double out[2])
{
	double w = h[6] * x + h[7] * y + h[8];

	out[0] = (h[0] * x + h[1] * y + h[2]) / w;
	out[1] = (h[3] * x + h[4] * y + h[5]) / w;
}
