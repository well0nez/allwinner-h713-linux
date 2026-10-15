/* SPDX-License-Identifier: GPL-2.0 */
/* The page as pictures: what is drawn where, in the 1920x1080 design of the mockup, scaled to the panel. */
#ifndef H713_SETTINGS_UI_H
#define H713_SETTINGS_UI_H

#include "osd.h"
#include "settings.h"

enum focus { F_AREAS, F_ROWS, F_CHOICE, F_CORNERS };

struct view {
	enum focus f;
	int area;		/* the area that is open */
	int row;		/* the selected row, as an index into the visible ones */
	int choice;		/* F_CHOICE: the highlighted option */
	int corner;		/* F_CORNERS: tl tr bl br */
	char corner_at[24];	/* F_CORNERS: the corner's two values as text */
};

#define D_ROW(i)	(1u << (i))	/* one row, by its place among the visible ones */
#define D_AREAS		(1u << 20)
#define D_NOTE		(1u << 21)
#define D_ALL		(1u << 30)

#define MAXBOX 8

/* draw what `dirty` names into the canvas; box[i] = x, y, w, h of what was touched, as separate rectangles - a row and the
 * note at the foot are two small ones, not the big one around both (what h713-osd puts through a keystone is paid for by
 * the pixel); returns how many */
int ui_draw(struct osd_canvas *c, const struct view *v, unsigned dirty, int box[][4]);

int visible_rows(const struct area *a);
struct row *visible_row(struct area *a, int i);

#endif
