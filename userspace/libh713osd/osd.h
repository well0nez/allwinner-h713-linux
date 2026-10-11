/* SPDX-License-Identifier: GPL-2.0 */
/*
 * libh713osd - the overlays of the H713 projectors as ARGB pictures, and nothing else: no DRM, no sockets,
 * no clock. A caller (h713-osd, a test, later a desktop) says what is to be shown; the library draws it into
 * a buffer. Everything is a signed distance field evaluated per pixel, so it is crisp at any panel size and
 * needs no font or image file. README.md in this directory describes the shapes, the looks and the places.
 */
#ifndef H713_OSD_H
#define H713_OSD_H

#include <stdint.h>

/* a picture: ARGB8888 as DRM means it (little endian: B, G, R, A in memory), straight (not premultiplied)
 * alpha; stride in pixels */
struct osd_canvas {
	uint32_t *px;
	int w, h, stride;
};

enum osd_kind {
	OSD_VOLUME,		/* value 0..100 */
	OSD_MUTE,		/* value = the volume underneath, 0..100; drawn dimmed with the speaker crossed out */
	OSD_FOCUS,		/* value +1 up, -1 down; flags OSD_EDGE: stopped at the end of the travel (red) */
	OSD_INPUT,		/* value 0 HDMI, 1 console */
	OSD_MUTE_BADGE,		/* the small sign that stays while muted; value unused */
};

#define OSD_EDGE	1

/* where the strip goes */
enum osd_place {
	OSD_BOTTOM,		/* centred above the lower edge - where the stock firmware puts its volume */
	OSD_TOP_RIGHT,
	OSD_CENTER,
};

enum osd_look {
	OSD_PILL,		/* a dark translucent panel with fully rounded ends behind white lines */
	OSD_BARE,		/* no panel: white lines with a soft shadow, the picture stays visible around them */
};

struct osd_style {
	enum osd_place place;
	enum osd_look look;
	float scale;		/* 1.0 = the size meant for the panel height; the user's choice on top */
};

struct osd_item {
	enum osd_kind kind;
	int value;
	int flags;
	float alpha;		/* 0..1, the fade; 1 = fully there */
};

/* everything transparent */
void osd_clear(struct osd_canvas *c);
/* one rectangle (x, y, w, h, as osd_draw returns it) transparent: cheaper than a whole panel */
void osd_clear_box(struct osd_canvas *c, const int box[4]);

/* draw one item where the style puts it (a badge always goes to its corner); returns the touched rectangle in
 * box[4] = x, y, w, h, so a caller can copy or pre-distort only that part. Items drawn one after another stack
 * (the later one over the earlier one). Not reentrant: one static work buffer. */
void osd_draw(struct osd_canvas *c, const struct osd_style *s, const struct osd_item *it, int box[4]);

#endif
