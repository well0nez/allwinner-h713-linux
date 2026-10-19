/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's gamma curve, computed the way the display firmware's own picture library computes it (gamma.c).
 *
 * Two layers. The first is arithmetic and nothing else: a board's raw colour temperature curves (what h713-pq
 * reads out of the board's TSE file and hands over at the start) and a gamma level give the 3 x 1024 samples
 * of the CRTC's GAMMA_LUT, sample for sample what the vendor's library writes. The second is the control: the two
 * settings "gamma" and "colour_temperature", what a picture mode wants, the file "werte", and one function pointer
 * to the place that puts a curve on the CRTC (main.c). Nothing here touches the display.
 */
#ifndef H713_TV_GAMMA_H
#define H713_TV_GAMMA_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "color.h"

#pragma GCC visibility push(hidden)

#define GAMMA_N		1024		/* samples per channel */
#define GAMMA_SLOTS	9		/* the vendor's colour temperature states: 0 normal, 1 cool, 2 warm, 3.. unused here */
#define GAMMA_LEVELS	5		/* gamma 1.8 2.0 2.1 2.2 2.4 */
#define GAMMA_LEVEL_DEFAULT	3	/* 2.2: the exponent 1.0, the raw curve */
#define GAMMA_POINTS	33		/* the factory menu's points: 11 knots, red green blue each, -50..50 */
#define GAMMA_MAX	4095		/* 12 bit */
#define GAMMA_BYTES	(3 * 4 * (GAMMA_N / 2))	/* the file the CRTC's banks are written from: 3 banks of 512 words */

/* red, green, blue; 12 bit samples */
typedef uint16_t gamma_curve[3][GAMMA_N];

/*
 * The computation. base is one colour temperature's raw curve, level 0..4 the gamma level. points is the factory
 * menu's 33 points (knot after knot, red green blue each, 0 for none) or NULL, which is the same as all 0: the form
 * the vendor's library is in after every start (the points are sent even when all are 0, and from then on every
 * curve goes through the twelve knots). false: level out of range, or a channel that ends in 0.
 */
bool gamma_compute(const gamma_curve base, unsigned int level, const int *points, gamma_curve out);

/* the form before the first points: every one of the 1024 samples by the power law (what h713-pq has always written) */
bool gamma_compute_pow(const gamma_curve base, unsigned int level, gamma_curve out);

/* the three banks as the file and the registers have them: (sample 2i+1 << 12) | sample 2i, little endian */
void gamma_pack(const gamma_curve lut, uint8_t out[GAMMA_BYTES]);

uint32_t gamma_crc32(const uint8_t *p, size_t n);

/* false when this build rounds a multiplication and an addition together (the arithmetic then is not the vendor's) */
bool gamma_arith_ok(void);

/*
 * The raw curves of a board, as h713-pq writes them (gamma --export-slots): 16 bytes "H7GS", version 1, the mask of
 * the states that follow, the board's ProjectID (little endian words); then for each state in the mask, lowest first,
 * red, green and blue as 1024 little endian 16-bit samples of 12 bit. A state that ends in 0 in a channel cannot be
 * used and is left out, with the reason in why.
 */
struct gamma_base {
	uint32_t mask;			/* bit n: state n is here and usable */
	unsigned int project;
	gamma_curve slot[GAMMA_SLOTS];
};

/* the number of usable states, 0 with the reason in why */
int gamma_base_read(struct gamma_base *b, const char *path, char *why, size_t n);

/* ---- the control ---- */

enum { GAMMA_T_AUTO, GAMMA_T_NORMAL, GAMMA_T_COOL, GAMMA_T_WARM, GAMMA_T_N };

struct gamma_io {
	/* put the curve on the CRTC; false with the reason */
	bool (*apply)(const gamma_curve lut, char *why, size_t n);
};

void gamma_init(void);

/* what the kept file says (have[i], value[i]: 0 the level, 1 the colour temperature as GAMMA_T_*); before the start */
void gamma_adopt(const bool *have, const int *value);

/* read the board's curves and keep io; false: the control is not there, why says why (and ctl says so) */
bool gamma_attach(const char *slots, const struct gamma_io *io, char *why, size_t n);

/* the curve comes from somewhere else (-g, no data); ctl set says so */
void gamma_unavailable(const char *why);

/* compute and apply the first time; false: it did not go. After that the control is gone until the next start */
bool gamma_start(void);

bool gamma_active(void);

/* a picture mode wants this colour temperature (0 normal, 1 cool, 2 warm); with "auto" it moves the curve */
void gamma_mode_temp(int slot, const char *why);

/* ctl: the names of "set" and "get" (0 gamma, 1 colour_temperature, -1 not ours) */
int gamma_key(const char *name);
void gamma_set(struct reply *r, int idx, const char *value);
void gamma_get(struct reply *r, int idx);
void gamma_list(struct reply *r);
void gamma_status(struct reply *r);

/* the file "werte": a line taken over (0 not ours, 1 taken, -1 ours but not a value) and the lines "ctl save" adds */
int gamma_parse_kept(const char *key, const char *value, int *idx, int *out);
size_t gamma_kept_lines(FILE *f, char *msg, size_t n, size_t l);

#pragma GCC visibility pop

#endif /* H713_TV_GAMMA_H */
