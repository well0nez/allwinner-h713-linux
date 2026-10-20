/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-settings - the box's settings as one page on the wall, driven by the remote.
 *
 * The model: areas (Picture, Keystone, ...) hold rows; a row is a slider, a switch, a choice, an action or a line of
 * text. Every row is one existing command of this project - h713-tv ctl, h713-warp ctl, h713-power set, a key of a
 * file in /etc/h713 - and nothing else: a tool that cannot do something has no row for it (README.md).
 */
#ifndef H713_SETTINGS_H
#define H713_SETTINGS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "osd.h"

enum kind { R_SLIDER, R_SWITCH, R_CHOICE, R_ACTION, R_INFO, R_CORNERS, R_STEPPER };

#define MAXOPT	10
#define MAXROW	10
#define MAXAREA	9
extern int area_keystone, area_sound, area_wifi;	/* their places in areas[]: the Colour area may be left out (rows_init) */
#define AREA_KEYSTONE	area_keystone
#define AREA_SOUND	area_sound
#define AREA_WIFI	area_wifi

struct row {
	const char *label;
	enum kind kind;
	int min, max, step, val;	/* slider: value; switch: 0/1; choice: index into opt */
	int n;				/* choice: number of options; slider: number of named stops (opt, opt_note), 0: a plain slider */
	char opt[MAXOPT][24];		/* choice: what the page shows ... */
	char arg[MAXOPT][24];		/* ... and what the tool is told */
	char text[64];			/* info: the value; action: what it says while it runs / after; stops: the value if not opt[val] */
	const char *note;		/* a sentence under the page while this row is selected */
	const char *opt_note[MAXOPT];	/* choice: a sentence for each value, instead of note */
	const char *tag;		/* slider: the control's name; action: what it runs */
	bool hidden;			/* the hardware or the tool is not there */
	bool more;			/* the mockup's "›": the row opens or starts something */
	bool over;			/* a slider judged on the picture: adjusted as one pill over the real picture, not on the page */
	const char *hint;		/* over: the line of keys under its pill, instead of the usual one */
	void (*load)(struct row *);			/* read the state the tool holds */
	void (*apply)(struct row *, int dir);		/* slider/switch: a step; choice/action: OK */
};

struct area {
	const char *name;
	const char *icon;
	struct row row[MAXROW];
	int n;
	void (*enter)(struct area *);	/* read the tools once when the area is opened */
};

enum key {
	KE_NONE = 0, KE_UP, KE_DOWN, KE_LEFT, KE_RIGHT, KE_OK, KE_BACK, KE_QUIT, KE_CMD,
	KE_HOME, KE_POWER, KE_VOL_UP, KE_VOL_DOWN, KE_MUTE, KE_FOCUS_UP, KE_FOCUS_DOWN,
};

/* where the tools are: environment overrides for the host tests */
extern const char *p_tv, *p_warp, *p_etc, *p_bin;

/* backend.c */
bool ctl(const char *sock, const char *line, char *out, size_t n);
bool tv(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
bool warp(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
extern char reply[2048];		/* the last answer of tv()/warp() */
int run(const char *const *argv, char *out, size_t n, int timeout_ms);	/* the tool's exit status, -1 not run */
int spawn(const char *const *argv);	/* started, not waited for: the pid */
bool conf_get(const char *file, const char *key, char *out, size_t n);
bool conf_set(const char *file, const char *key, const char *val);
const char *etc(const char *name);	/* p_etc/name */

/* input.c: the remote's devices, held alone while the page is open */
int input_open(void);			/* the number of devices held; 0: none, or one that cannot be held */
void input_close(void);
int input_key(int timeout_ms);		/* a key as enum key, KE_NONE on timeout or for a key the page does not know */
double input_stamp(void);		/* when the last key was pressed (kernel stamp, ms since the epoch), once; 0: no key */
void input_power(void);			/* hand a Power press to h713-power */

/* page.c: h713-osd's page channel - a canvas to draw into, and the word which part of it is new */
int page_open(struct osd_canvas *c, const char *path);
int page_show(const int box[4]);	/* 1 shown, 0 kept for the picture's return, -1 gone */
void page_handover(void);		/* Back to the launcher: h713-osd keeps the page until the launcher is drawn */
void page_close(void);

/* rows.c */
extern struct area areas[MAXAREA];
extern int nareas;
void rows_init(void);
void rows_enter(int area);		/* read the tools for the area that is opened */
void rows_tick(bool *changed);		/* children that ended, the page's timers; *changed: a row needs drawing */
void rows_flush(void);			/* what was held back for the eMMC (picture values) is written now */
bool rows_hotkey(int key);		/* volume, mute, focus: the keys h713-keys would act on; true when the page shows a change */
int rows_wake_ms(void);			/* how long the loop may sleep: -1 for ever */
void corner_load(void);			/* the eight values, from warp.conf */
bool corner_move(int corner, int dx, int dy, char *shown, size_t n);	/* one nudge, answers what the corner is now */
void corner_mask(int corner);		/* mark a corner (-1: the pattern off) */

#endif
