/* SPDX-License-Identifier: GPL-2.0 */
/*
 * libh713geom -- the keystone geometry of the H713 projectors, shared by h713-warp, which draws the picture
 * through it, and h713-osd, which pre-distorts its overlays with the very same map (TODO 2.44): the eight
 * per-mille corner values and the vendor's matrix (matrix.c), /etc/h713/warp.conf (config.c), and the way back
 * from the panel to the source (inverse.c). A source library: a program compiles the files it needs into itself
 * and provides warn() for the journal. README.md in this directory.
 */
#ifndef H713_GEOM_H
#define H713_GEOM_H

#include <stdbool.h>
#include <stddef.h>

#define WARP_CONF	"/etc/h713/warp.conf"

#define WARP_KEYS	8	/* four corners, x and y, per-mille inward */
#define EDGE_DEFAULT	4	/* the soft border in panel pixels: the vendor's alias.scale (gl.c) */
#define EDGE_MAX	64

/* one journal line, provided by the program (h713-warp: main.c) */
__attribute__((format(printf, 1, 2))) void warn(const char *fmt, ...);

/* ---------------- the eight values and the matrix (matrix.c) ----------- */
/* our key order: the PHYSICAL corner on the wall, tl tr bl br, x before y.
 * The vendor's parcel order is a different one and lives in matrix.c alone.
 */
enum warp_corner { CORNER_TL, CORNER_TR, CORNER_BL, CORNER_BR };
/* the projection mode: how the picture is mirrored for the mount (matrix.c) */
enum warp_mode { MODE_FRONT, MODE_REAR, MODE_CEILING, MODE_REAR_CEILING };

extern const char *const warp_corner_name[4];
extern const char *const warp_key_name[WARP_KEYS];	/* "tl_x" .. "br_y" */
extern const char *const warp_mode_name[4];		/* "front" .. "rear-ceiling" */

int warp_key(const char *corner, const char *axis);	/* 0..7, -1 unknown */
int warp_key_by_name(const char *key);			/* "tl_x" -> 0..7 */
void warp_clamp(int v[WARP_KEYS]);			/* all four, as the app does */
int warp_clamp_key(int v[WARP_KEYS], int key, int want);	/* one, as a key press does */
int warp_limit(const int v[WARP_KEYS], int key);		/* the most that key may take now */
bool warp_identity(const int v[WARP_KEYS]);		/* all eight zero */
bool warp_matrix(const int v[WARP_KEYS], double m[16]);	/* false: refused */
int warp_mode_by_name(const char *name);			/* 0..3, -1 unknown */
void warp_mirror(int mode, double m[16]);		/* m = flip(mode) * m */
void warp_remount(int from, int to, int v[WARP_KEYS]);	/* the eight re-sorted for a new mode */
void warp_point(const double m[16], double x, double y, double out[2]);
void warp_corner_ndc(int corner, double out[2]);

struct warp_conf {
	const char *path;
	bool present;			/* the file was there */
	bool start_on;			/* "warp = on" */
	int v[WARP_KEYS];
	int zoom;			/* screen zoom in percent, 100 = none (S7) */
	int edge;			/* the soft border in panel pixels, 0 = a hard edge */
	int mode;			/* enum warp_mode, "mode =" in the file */
};

/* The eight the matrix sees: the keystone with the screen zoom in it (the
 * vendor's "Digital scaling", AP2i rows 6-8: the panel's square scaled about
 * its centre and carried through the keystone's homography), clamped the
 * vendor's way. */
void warp_effective(const struct warp_conf *c, int out[WARP_KEYS]);

void conf_read(struct warp_conf *c);
bool conf_write(const struct warp_conf *c, char *why, size_t n);

/* ---------------- from the panel back to the source (inverse.c) ---------- */
/* the map warp_point() makes, with the quad's z = -1 folded in, as a 3 x 3 homography, inverted: false when it
 * cannot be (a degenerate quad). warp_unpoint() takes a panel point back to the source point the warp shows
 * there - how an overlay is pre-distorted so that it sits in the picture like the picture itself. */
bool warp_inverse(const double m[16], double h[9]);
void warp_unpoint(const double h[9], double x, double y, double out[2]);

#endif /* H713_GEOM_H */
