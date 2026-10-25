/* SPDX-License-Identifier: GPL-2.0 */
/* The page as pictures: what is drawn where, in the 1920x1080 design of the mockup, scaled to the panel. */
#ifndef H713_SETTINGS_UI_H
#define H713_SETTINGS_UI_H

#include "osd.h"
#include "settings.h"

/* F_SLIDER and F_CORNERS leave the opaque page: only one pill over the real picture, so that the effect can be seen */
enum focus { F_AREAS, F_ROWS, F_CHOICE, F_CORNERS, F_SLIDER };

struct view {
	enum focus f;
	int area;		/* the area that is open */
	int row;		/* the selected row, as an index into the visible ones */
	int choice;		/* F_CHOICE: the highlighted option */
	int corner;		/* F_CORNERS: tl tr bl br */
	char corner_at[24];	/* F_CORNERS: the corner's two values as text */
};

#define D_ROW(i)	(1u << (i))		/* one row, by its place among the visible ones (up to 10) */
#define D_AREA(i)	(1u << (10 + (i)))	/* one area's pill (up to 10) */
#define D_RIGHT		(1u << 20)		/* every row of the right pane, or the options of a choice */
#define D_NOTE		(1u << 21)		/* the sentence under the rows and the line of keys */
#define D_SLIDER	(1u << 22)		/* the one pill of a slider over the picture */
#define D_ALL		(1u << 30)		/* everything, including the ground */

#define MAXBOX 8

/* draw what `dirty` names into the canvas; box[i] = x, y, w, h of what was touched, as separate rectangles - a row and the
 * note at the foot are two small ones, not the big one around both (what h713-osd puts through a keystone is paid for by
 * the pixel); returns how many */
int ui_draw(struct osd_canvas *c, const struct view *v, unsigned dirty, int box[][4]);

/* the sentence under the rows for the selected one: its own, or for a choice or a slider with named stops the one of the value it stands on; NULL: none */
const char *ui_note(const struct view *v, const struct row *sel);

int visible_rows(const struct area *a);
struct row *visible_row(struct area *a, int i);

#endif
