/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* mkstemp */
/*
 * T3 (FB-MIRROR): warp.conf carries the projection mode. What conf_write puts
 * down, conf_read takes up again - the eight corners, the zoom, the start
 * state and the mode - and a mode the file does not name, or names wrongly,
 * comes up as front. Runs on any host: the file is a temporary one in the
 * current directory, removed at the end.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../geom.h"

static int warnings;

/* config.c wants the program's journal line (geom.h) */
void warn(const char *fmt, ...) { (void)fmt; warnings++; }

static int failed;

static void expect(int ok, const char *what)
{
	if (!ok) {
		printf("FAIL conf: %s\n", what);
		failed++;
	}
}

static void put(const char *path, const char *text)
{
	FILE *f = fopen(path, "w");

	if (!f || fputs(text, f) < 0 || fclose(f))
		exit(1);
}

int main(void)
{
	char path[] = "conf-XXXXXX", why[256];
	struct warp_conf c, back;
	int fd = mkstemp(path), mode, i;

	if (fd < 0)
		return 1;
	close(fd);
	memset(&c, 0, sizeof(c));
	c.path = path;
	back.path = path;
	for (mode = 0; mode < 4; mode++) {
		for (i = 0; i < WARP_KEYS; i++)
			c.v[i] = 10 * (i + 1) + mode;
		c.zoom = 90 - mode;
		c.start_on = mode & 1;
		c.mode = mode;
		expect(conf_write(&c, why, sizeof(why)), "conf_write");
		conf_read(&back);
		expect(back.present, "the file is there");
		expect(back.mode == mode, "the mode comes back");
		expect(back.zoom == c.zoom, "the zoom comes back");
		expect(back.start_on == c.start_on, "the start state comes back");
		expect(!memcmp(back.v, c.v, sizeof(c.v)), "the eight come back");
	}
	expect(!warnings, "no warning on a written file");
	put(path, "tl_x = 5\nmode = rear-ceiling\n");
	conf_read(&back);
	expect(back.mode == MODE_REAR_CEILING && back.v[0] == 5, "a hand-written mode");
	put(path, "tl_x = 5\n");
	conf_read(&back);
	expect(back.mode == MODE_FRONT, "no mode line is front");
	warnings = 0;
	put(path, "mode = upside-down\nzoom = 80\n");
	conf_read(&back);
	expect(back.mode == MODE_FRONT && back.zoom == 80 && warnings == 1,
	       "an unknown mode is front, with one warning, and the rest is read");
	remove(path);
	printf("%s T3 conf: the mode survives the file, %d deviations\n",
	       failed ? "FAIL" : "ok", failed);

	return failed ? 1 : 0;
}
