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
 * The menu (osd.c): the pieces of the launcher - Strichsymbole, a row and a hint line - drawn in the look of the overlays
 * (pill, white lines, bright and dim) on the launcher's opaque page. Geometry is in "1080-line units": the
 * mock-up's numbers, scaled by canvas height / 1080, so 720p and 1080p get the same layout. Package H's launcher and
 * package S's settings are built from these; text needs osd_font_open() first (below).
 */
enum osd_icon { OSD_ICON_HDMI, OSD_ICON_FILM, OSD_ICON_GLOBE, OSD_ICON_DESK, OSD_ICON_SLIDERS, OSD_ICON_POWER, OSD_ICONS };

/* the symbol's name in a launcher entry file ("hdmi", "film", "globe", "desk", "sliders", "power"); -1 if unknown */
int osd_icon_by_name(const char *name);

/* The opaque page's colours (the same as h713-settings' ui.c, so that the launcher and the settings are one line): the ground
 * of the whole page, ARGB, fully opaque, and the lit pill of the chosen row, a little lighter (RGB). */
#define OSD_PAGE_GROUND	0xff0b0e0du
#define OSD_PAGE_PILL	0x1c2321u
/* Nothing of the launcher but the ground may lie in the outer 5 % of the page on each side (96 px left and right, 54 px
 * top and bottom at 1080p; 64 and 36 at 720p) - the part of a projected wall that is cut off or distorted most. */
#define OSD_SAFE_PERCENT 5

/* One row: a stadium (the pill) at x, y with width w and height h - the launcher's is 520 x 104 at x 118 - with a
 * symbol at its left, the label after it, both bright inside a pill that is drawn (the lit pill's fill and a white outline)
 * when selected, both dim and with no pill when not. Everything inside scales with h (the symbol is 0.69 h, the label 0.37 h).
 * The label is clipped to the pill (no ellipsis). Mixed over what the canvas holds; box = the touched rectangle
 * (the pill with a margin) when not NULL. Not reentrant. */
struct osd_row {
	int icon;		/* enum osd_icon */
	const char *label;	/* UTF-8; needs osd_font_open() */
	int selected;
	double x, y, w, h;	/* the pill, in 1080-line units */
};
void osd_draw_row(struct osd_canvas *c, const struct osd_row *r, int box[4]);

/* A dim hint line, 26 units high, its baseline at y (1080-line units, x too): with arrows != 0 the marks for up and
 * down (drawn as shapes, the face has no such glyphs) come first and the text after them. */
void osd_draw_hint(struct osd_canvas *c, double x, double baseline, const char *text, int arrows);

/*
 * The launcher: an OPAQUE page over the whole canvas (Marco, 15.10.2026: it must have a ground, it is not an overlay over the
 * picture) in the ground colour, with the mock-up's "Launcher C" list in the column on the left - a header line, up to six rows,
 * a hint line - and the rest calm. Everything but the ground stays inside the safe margin (OSD_SAFE_PERCENT). It is cut into
 * TILES, so a caller can repaint only the tiles that changed (a move of the selection changes two rows' tiles, 700 x 124 units
 * each) and copy or pre-distort only those. A band is a strip of the page: band 0 the header, band 1 + i row i, band n + 1 the
 * foot, band n + 2 the gap between the rows at the top and those at the foot (empty, height 0, when there is none). Tile k < n + 3
 * is the band's left part, the column x 0..700 where its content is; tile n + 3 + k its right part, to the canvas' edge, the
 * ground alone. The tiles tile the canvas; they are not in the order of their y.
 */
#define OSD_LAUNCHER_ROWS 6

struct osd_launcher {
	const char *head;	/* the header line, 30 units, dim: "20:47 \u00b7 HDMI 1080p60" (UTF-8) */
	int n, sel;		/* the rows, the chosen one */
	struct {
		int icon;		/* enum osd_icon */
		const char *label;
		int end;		/* 1: in the group at the foot (Standby): bottom-anchored, apart from the others */
	} row[OSD_LAUNCHER_ROWS];	/* the rows with end = 0 first, then those with end = 1 */
};

/* the rectangles (x, y, w, h in canvas pixels) of the tiles; returns their count, 2 * (n + 3) (0 for no rows); box needs
 * 2 * (OSD_LAUNCHER_ROWS + 3) entries */
int osd_launcher_bands(const struct osd_canvas *c, const struct osd_launcher *l, int box[][4]);

/* repaint one tile: the ground REPLACES its pixels, then its content is drawn over it. All of them, in any order, make the whole
 * opaque page; the hint's words are fixed ("select, OK open, BACK close"). Needs osd_font_open(). */
void osd_launcher_draw(struct osd_canvas *c, const struct osd_launcher *l, int tile);

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
