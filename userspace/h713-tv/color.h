/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's side of the display firmware's own colour: the white balance and the colour management (color.c).
 *
 * main.c asks the questions and carries the answers: what is wanted comes in over the control socket, what is kept
 * comes from the file "werte", the picture modes and the source changes call in at the places where the firmware
 * may write its colour again. Everything about the firmware's shared memory, the registers and the base of the
 * colour management is in color.c.
 */
#ifndef H713_TV_COLOR_H
#define H713_TV_COLOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

struct reply;

/*
 * Nothing here is for other objects: hidden, so that the program's dynamic symbols stay what they were (the linker
 * would otherwise export warn(), which libc has as well, and let this one stand in for libc's).
 */
#pragma GCC visibility push(hidden)

#define FWC_WB_N	6
#define FWC_CM_AXES	12
#define FWC_CM_N	(FWC_CM_AXES * 3)

/*
 * What color.c takes from the program (main.c): the journal and the answer to a control command. They are defined
 * there and are the same ones every other part of the program uses.
 */
__attribute__((format(printf, 1, 2))) void info(const char *fmt, ...);
__attribute__((format(printf, 1, 2))) void warn(const char *fmt, ...);
__attribute__((format(printf, 2, 3))) void reply_add(struct reply *r, const char *fmt, ...);
__attribute__((format(printf, 2, 3))) void reply_fail(struct reply *r, const char *fmt, ...);

/* the values: at the start, from the kept file, in the list and in the status */
void fwc_init(void);
void fwc_adopt(const bool *wb_have, const int *wb, const bool *cm_have, const int *cm);
void fwc_list(struct reply *r);
void fwc_status(struct reply *r);

/* the names of "ctl set" and "ctl get": the index of a name of ours (0..5 white balance, 6.. colour management), -1: not ours */
int fwc_key(const char *name);
void fwc_set(struct reply *r, int idx, const char *value);
void fwc_get(struct reply *r, int idx);

/* the commands "wb" and "cm" */
void cmd_wb(struct reply *r, char **arg, unsigned int n);
void cmd_cm(struct reply *r, char **arg, unsigned int n);

/* a picture mode writes the firmware's colour again: before it is sent, and after (why: the words of the journal) */
void fwc_mode_begin(void);
void fwc_mode_end(const char *why);

/* do the registers still hold what is wanted; if not, send again */
void fwc_sync(const char *why);

/* the file "werte": a line taken over (0 not ours, 1 taken, -1 ours but out of range) and the lines "ctl save" adds */
int fwc_parse_kept(const char *key, long x, int *idx, int *out);
size_t fwc_kept_lines(FILE *f, char *msg, size_t n, size_t l);

#pragma GCC visibility pop

#endif /* H713_TV_COLOR_H */
