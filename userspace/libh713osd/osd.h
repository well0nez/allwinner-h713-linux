/* SPDX-License-Identifier: GPL-2.0 */
/*
 * libh713osd - the overlays of the H713 projectors as ARGB pictures, and nothing else: no DRM, no sockets,
 * no clock. A caller (h713-osd, a test, later a desktop) says what is to be shown; the library draws it into
 * a buffer. The shapes are signed distance fields evaluated per pixel, so they are crisp at any panel size and
 * need no image file; text (osd_text, below) is FreeType's and needs one font file, opened by the caller.
 * README.md in this directory describes the shapes, the looks, the places and the text.
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
	OSD_POWER,		/* the power key's countdown, in the middle: value = time left in tenths of a second
				 * (0..150, the ring is full at 15 s); flags OSD_PWR_STANDBY: standby is the choice (else
				 * off), OSD_PWR_OFF_ONLY: no standby here, the ring alone */
	OSD_PAIR,		/* pairing the remote: hold Left + Right; value = time left in tenths (0..100), 0 = no ring */
};

#define OSD_EDGE	1
#define OSD_PWR_STANDBY		2
#define OSD_PWR_OFF_ONLY	4

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

/*
 * Text (text.c, FreeType - link libfreetype; h713-osd links it statically). The one part of the library that reads
 * a file: the font, opened once by the caller. The package's face on the image is Quicksand Medium
 * (Debian fonts-quicksand, SIL OFL 1.1) at OSD_FONT. A string is UTF-8, drawn left to right on one baseline in one
 * colour; there is no wrapping, no alignment and no cache - a caller that wants a centred or right-aligned
 * string asks osd_text_width() first.
 */
#define OSD_FONT "/usr/share/fonts/truetype/quicksand/Quicksand-Medium.ttf"

/* open the font face at path; 0 on success (and when one is open already), -1 if the file is missing or no font.
 * The first face stays: a second call with another path is a no-op. Without a face osd_text draws nothing. */
int osd_font_open(const char *path);

/* the advance width, in canvas pixels, of utf8 set at px pixels (the em height - 38 for a launcher label on a
 * 1080-line panel); 0 without a font. Unhinted and fractional: the width is what the designer drew. */
double osd_text_width(const char *utf8, double px);

/* utf8 with its left end at x and its baseline at y, px pixels high, in colour rgb (0xRRGGBB) with alpha 0..1 on
 * top of the glyph's own coverage, mixed over the canvas in straight alpha (the same way osd_draw mixes). Pixels
 * outside the canvas are clipped. max_w > 0 stops before the first glyph that would end beyond max_w pixels from
 * x (no ellipsis); 0 = no limit. Returns the advance width of what was drawn. Not reentrant (one face). */
double osd_text(struct osd_canvas *c, const char *utf8, double x, double baseline, double px, unsigned rgb,
		float alpha, double max_w);

#endif
