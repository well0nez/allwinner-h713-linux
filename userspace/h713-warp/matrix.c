/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The warp matrix (design AP2d M7) -- a line-by-line port of the vendor's
 * ACTIVE warp, getKeyStoneMatrix @ 0x000031E8 in system_a_libkeystone.so, by
 * way of the tested reference umbau/work/AP2f/model/keystone_matrix.py. The
 * host test tests/test_matrix.c compares the sixteen floats of this file
 * against that reference to 1e-6 (AP2d T2).
 *
 * K = M1 * diag(0.5, 0.5, 1, 1) * translate(1, 1, 1), column major, applied
 * right to left: translate, halve, warp (AP2f section 2, amendment 6b). The
 * +1 in the translate's z is not a leftover: it is why the quad has to sit at
 * z = -1 in the vertex shader. With z = -1 the translate makes z_clip 0, and
 * no division by the homography's w can push it out of [-w, +w]; with z = 0 it
 * would be 1, and every vertex whose w drops below 1 -- the side the keystone
 * pulls in -- would be clipped at the far plane.
 *
 * WHICH PHYSICAL CORNER IS WHICH SLOT. The vendor's eight parcel floats are
 * numbered 0..3 and its own two name sets contradict each other (AP2 open
 * question 4). We do not inherit the ambiguity: this program names the corner
 * as the picture stands on the wall and derives the slot from geometry.
 * getKeyStoneMatrix maps the four NDC corners, in slot order, onto
 *   slot 0 (-1, +1)   slot 1 (-1, -1)   slot 2 (+1, -1)   slot 3 (+1, +1),
 * and in our render target NDC y = -1 is the FIRST row in memory, which the
 * scanout shows at the TOP of the panel (h713-gpu-probe/scanout.c, draw()).
 * So slot 0 is the wall's bottom left, slot 1 its top left, slot 2 its top
 * right, slot 3 its bottom right -- exactly the order the vendor's apps use
 * for the parcel (lb, lt, rt, rb). CORNER_OF_SLOT below is that, in one
 * place; the wall settles it with one nudge and one photo (plan S5, T21), and
 * if top and bottom come out exchanged, its two first lines swap.
 */
#include <string.h>

#include "warp.h"

const char *const warp_corner_name[4] = { "tl", "tr", "bl", "br" };
const char *const warp_key_name[WARP_KEYS] = {
	"tl_x", "tl_y", "tr_x", "tr_y", "bl_x", "bl_y", "br_x", "br_y",
};

/* vendor slot -> our corner: lb, lt, rt, rb (see the comment above) */
static const int CORNER_OF_SLOT[4] = {
	CORNER_BL, CORNER_TL, CORNER_TR, CORNER_BR,
};
/* The vendor's clamp, KeystoneUtils.setkeystoneValue (AP2 section 1): x of a
 * corner against the one at the other end of its panel ROW, y against the one
 * at the other end of its COLUMN, so two opposite corners can never pull the
 * picture past its own width or height (tl<->tr and bl<->br share a row).
 */
static const int ROW_PARTNER[4] = { CORNER_TR, CORNER_TL, CORNER_BR, CORNER_BL };
static const int COL_PARTNER[4] = { CORNER_BL, CORNER_BR, CORNER_TL, CORNER_TR };

#define MIN_H		1000	/* KeystoneUtils.minH_size (Config default) */
#define MIN_V		1000	/* KeystoneUtils.minV_size */

int warp_key(const char *corner, const char *axis)
{
	int c, a;

	if (!corner || !axis || !axis[0] || axis[1])
		return -1;
	a = axis[0] == 'x' ? 0 : axis[0] == 'y' ? 1 : -1;
	if (a < 0)
		return -1;
	for (c = 0; c < 4; c++)
		if (!strcmp(corner, warp_corner_name[c]))
			return 2 * c + a;

	return -1;
}

int warp_key_by_name(const char *key)
{
	int i;

	for (i = 0; i < WARP_KEYS; i++)
		if (!strcmp(key, warp_key_name[i]))
			return i;

	return -1;
}

bool warp_identity(const int v[WARP_KEYS])
{
	int i;

	for (i = 0; i < WARP_KEYS; i++)
		if (v[i])
			return false;

	return true;
}

/* Four setkeystoneValue calls in the vendor's slot order 0,1,2,3, because the
 * order decides a tie at the limit (AP2f 5). Negative becomes 0; the upper
 * limit is not clamped to zero again -- that is the vendor's behaviour.
 */
void warp_clamp(int v[WARP_KEYS])
{
	int slot;

	for (slot = 0; slot < 4; slot++) {
		int c = CORNER_OF_SLOT[slot];
		int x = v[2 * c], y = v[2 * c + 1];
		int px = v[2 * ROW_PARTNER[c]], py = v[2 * COL_PARTNER[c] + 1];

		v[2 * c] = x < 0 ? 0 : x < MIN_H - px ? x : MIN_H - px;
		v[2 * c + 1] = y < 0 ? 0 : y < MIN_V - py ? y : MIN_V - py;
	}
}

/* One corner, one axis, as KeystoneUtils.setkeystoneValue really runs it: the
 * value being set gives way, the partner keeps what it has (warp_clamp above
 * is the app's "all four at once" form, for a hand-edited file).
 */
int warp_clamp_key(int v[WARP_KEYS], int key, int want)
{
	int c = key / 2, axis = key % 2;
	int partner = axis ? COL_PARTNER[c] : ROW_PARTNER[c];
	int limit = (axis ? MIN_V : MIN_H) - v[2 * partner + axis];

	if (limit < 0)
		limit = 0;
	v[key] = want < 0 ? 0 : want > limit ? limit : want;

	return v[key];
}

static double f32(double value)
{
	return (double)(float)value;
}

/* sub_3658 @ 0x00003658: out = a * b, column major, NEON on the device */
static void mat_mul(const double *a, const double *b, double *out)
{
	int j, r;

	for (j = 0; j < 4; j++)
		for (r = 0; r < 4; r++)
			out[4 * j + r] = a[r] * b[4 * j] + a[4 + r] * b[4 * j + 1] +
					 a[8 + r] * b[4 * j + 2] + a[12 + r] * b[4 * j + 3];
}

/* The eight per-mille insets in, the 4x4 SurfaceFlinger post-multiplies out.
 * False where the vendor logs "wrong input translation para" and keeps the
 * previous matrix: a corner outside [-1, +1]. The solve has no pivoting, no
 * branch and no degeneracy test in the vendor code, and none here -- a
 * degenerate quad divides by zero and the caller sees the NaN.
 */
bool warp_matrix(const int v[WARP_KEYS], double m[16])
{
	static const double S[16] = {		/* diag(0.5, 0.5, 1, 1), sp+0xD0 */
		0.5, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0,
		0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
	};
	static const double T[16] = {		/* translate(1, 1, 1), sp+0x110 */
		1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
		0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0,
	};
	double t[WARP_KEYS], c[4][2], m1[16], scratch[16];
	double a, b, n, d, g, h;
	int slot;

	for (slot = 0; slot < 4; slot++) {
		int k = 2 * CORNER_OF_SLOT[slot];

		t[2 * slot] = f32(v[k] * 0.001);
		t[2 * slot + 1] = f32(v[k + 1] * 0.001);
	}
	/* step 1 @ +0xD4..+0x254: eight fractions -> the four NDC corners */
	c[0][0] = t[0] + t[0] - 1.0;	c[0][1] = 1.0 - (t[1] + t[1]);
	c[1][0] = t[2] + t[2] - 1.0;	c[1][1] = t[3] + t[3] - 1.0;
	c[2][0] = 1.0 - (t[4] + t[4]);	c[2][1] = t[5] + t[5] - 1.0;
	c[3][0] = 1.0 - (t[6] + t[6]);	c[3][1] = 1.0 - (t[7] + t[7]);
	for (slot = 0; slot < 4; slot++) {
		double x = c[slot][0], y = c[slot][1];

		if (slot < 3 ? (y < -1.0 || x > 1.0 || x < -1.0 || y > 1.0)
			     : !(y >= -1.0 && x <= 1.0 && x >= -1.0 && y <= 1.0))
			return false;
	}
	/* step 2 @ +0x258..+0x31C: the unit square onto (v1, v2, v3, v0) */
	a = (c[0][0] - c[3][0]) * (c[2][1] - c[3][1]);
	b = (c[2][0] - c[3][0]) * (c[0][1] - c[3][1]);
	n = (c[1][0] + (c[3][0] - c[2][0])) - c[0][0];
	d = (c[1][1] + (c[3][1] - c[2][1])) - c[0][1];
	g = ((c[2][0] - c[3][0]) * d - n * (c[2][1] - c[3][1])) / (b - a);
	h = ((c[0][0] - c[3][0]) * d - n * (c[0][1] - c[3][1])) / (a - b);
	memset(m1, 0, sizeof(m1));
	m1[0] = c[2][0] - c[1][0] + c[2][0] * h;
	m1[1] = c[2][1] - c[1][1] + c[2][1] * h;
	m1[3] = h;
	m1[4] = c[0][0] - c[1][0] + c[0][0] * g;
	m1[5] = c[0][1] - c[1][1] + c[0][1] * g;
	m1[7] = g;
	m1[10] = 1.0;
	m1[12] = c[1][0];
	m1[13] = c[1][1];
	m1[15] = 1.0;
	/* the two sub_3658 calls at 0x000034F8 and 0x00003504 */
	mat_mul(m1, S, scratch);
	mat_mul(scratch, T, m);

	return true;
}

/* one point through a column-major 4x4, w divided out as the rasteriser does */
void warp_point(const double m[16], double x, double y, double out[2])
{
	double z = -1.0;	/* the quad's z, see the head of this file */
	double w = m[3] * x + m[7] * y + m[11] * z + m[15];

	out[0] = (m[0] * x + m[4] * y + m[8] * z + m[12]) / w;
	out[1] = (m[1] * x + m[5] * y + m[9] * z + m[13]) / w;
}

/* the corner of the untouched panel that belongs to one of our corner names */
void warp_corner_ndc(int corner, double out[2])
{
	out[0] = (corner == CORNER_TL || corner == CORNER_BL) ? -1.0 : 1.0;
	out[1] = (corner == CORNER_TL || corner == CORNER_TR) ? -1.0 : 1.0;
}
