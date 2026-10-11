// SPDX-License-Identifier: GPL-2.0
/*
 * osd-mockup DIR [W H] - every place, look and case of libh713osd as one PAM picture each (RGB_ALPHA,
 * straight alpha), DIR/<place>-<look>-<case>.pam, default 1920 x 1080. A host tool: the pictures are laid over
 * a photo to choose a look; it is not installed.
 */
#include <stdio.h>
#include <stdlib.h>

#include "osd.h"

static const char *PLACE[] = { "unten", "obenrechts", "mitte" };
static const char *LOOK[] = { "pille", "frei" };

static const struct {
	const char *name;
	struct osd_item it[2];
	int n;
} CASES[] = {
	{ "lautstaerke", { { OSD_VOLUME, 45, 0, 1 } }, 1 },
	{ "stumm", { { OSD_MUTE, 45, 0, 1 }, { OSD_MUTE_BADGE, 0, 0, 1 } }, 2 },
	{ "nur-stumm-zeichen", { { OSD_MUTE_BADGE, 0, 0, 1 } }, 1 },
	{ "fokus-hoch", { { OSD_FOCUS, 1, 0, 1 } }, 1 },
	{ "fokus-runter", { { OSD_FOCUS, -1, 0, 1 } }, 1 },
	{ "fokus-ende-oben", { { OSD_FOCUS, 1, OSD_EDGE, 1 } }, 1 },
	{ "fokus-ende-unten", { { OSD_FOCUS, -1, OSD_EDGE, 1 } }, 1 },
	{ "eingang-hdmi", { { OSD_INPUT, 0, 0, 1 } }, 1 },
	{ "eingang-konsole", { { OSD_INPUT, 1, 0, 1 } }, 1 },
	{ "lautstaerke-100", { { OSD_VOLUME, 100, 0, 1 } }, 1 },
};

static int write_pam(const char *path, const struct osd_canvas *c)
{
	FILE *f = fopen(path, "wb");

	if (!f)
		return -1;
	fprintf(f, "P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n", c->w, c->h);
	for (int y = 0; y < c->h; y++)
		for (int x = 0; x < c->w; x++) {
			uint32_t p = c->px[(size_t)y * c->stride + x];
			unsigned char q[4] = { p >> 16 & 255, p >> 8 & 255, p & 255, p >> 24 };

			fwrite(q, 1, 4, f);
		}
	return fclose(f);
}

int main(int argc, char **argv)
{
	struct osd_canvas c = { 0 };
	char path[512];

	if (argc != 2 && argc != 4) {
		fprintf(stderr, "usage: osd-mockup DIR [W H]\n");
		return 2;
	}
	c.w = argc == 4 ? atoi(argv[2]) : 1920;
	c.h = argc == 4 ? atoi(argv[3]) : 1080;
	c.stride = c.w;
	c.px = calloc((size_t)c.w * c.h, 4);
	if (!c.px)
		return 1;
	for (int p = 0; p < 3; p++)
		for (int l = 0; l < 2; l++)
			for (size_t k = 0; k < sizeof(CASES) / sizeof(CASES[0]); k++) {
				struct osd_style st = { p, l, 1.0f };

				osd_clear(&c);
				for (int i = 0; i < CASES[k].n; i++)
					osd_draw(&c, &st, &CASES[k].it[i], NULL);
				snprintf(path, sizeof(path), "%s/%s-%s-%s.pam", argv[1], PLACE[p], LOOK[l], CASES[k].name);
				if (write_pam(path, &c)) {
					perror(path);
					return 1;
				}
			}
	return 0;
}
