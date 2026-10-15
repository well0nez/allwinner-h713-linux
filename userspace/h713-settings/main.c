// SPDX-License-Identifier: GPL-2.0
/*
 * h713-settings - the settings page of the box, opened from the launcher and driven by the remote (README.md).
 *
 * The loop: a key arrives, the row it is on sends one command to its tool, the row is drawn again and shown. The keys
 * and the picture reach the wall through a "sink": --test is the one for the host (keys as lines on stdin, the canvas
 * as PAM pictures on request); the device's own (package H's input and display path) is added where it is decided.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>

#include "ui.h"

static struct view v;
static struct osd_canvas canvas;
static int row_of[MAXAREA];		/* the row each area was left on */
static volatile sig_atomic_t quit;

/* --- the sink for the host tests: stdin lines in, PAM pictures out -------------------------------------------- */

static char ibuf[4096];
static size_t ilen;

static void dump(void)
{
	static const char *const kind[] = { "slider", "switch", "choice", "action", "info", "corners", "stepper" };
	static const char *const focus[] = { "areas", "rows", "choice", "corners" };
	struct area *a = &areas[v.area];

	printf("area %s focus %s row %d choice %d corner %d\n", a->name, focus[v.f], v.row, v.choice, v.corner);
	for (int i = 0; i < a->n; i++) {
		struct row *r = &a->row[i];

		printf("  %s%s %s", r->hidden ? "(hidden) " : "", r->label, kind[r->kind]);
		if (r->kind == R_SLIDER || r->kind == R_SWITCH)
			printf(" %d", r->val);
		if (r->kind == R_SLIDER)
			printf(" %d..%d", r->min, r->max);
		if (r->kind == R_CHOICE) {
			printf(" [");
			for (int k = 0; k < r->n; k++)
				printf("%s%s%s", k ? "|" : "", k == r->val ? "*" : "", r->opt[k]);
			printf("]");
		}
		if (r->text[0])
			printf(" \"%s\"", r->text);
		printf("\n");
	}
	printf("--\n");		/* the end of a dump, for the test that reads it */
	fflush(stdout);
}

static void snap(const char *path)
{
	FILE *f = fopen(path, "wb");

	if (!f)
		return;
	/* the canvas over the grey of a picture, as PAM (RGB_ALPHA): any viewer or converter takes it */
	fprintf(f, "P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n", canvas.w, canvas.h);
	for (int y = 0; y < canvas.h; y++)
		for (int x = 0; x < canvas.w; x++) {
			uint32_t p = canvas.px[(size_t)y * canvas.stride + x];
			unsigned char b[4] = { (unsigned char)(p >> 16), (unsigned char)(p >> 8), (unsigned char)p,
					       (unsigned char)(p >> 24) };

			fwrite(b, 1, 4, f);
		}
	fclose(f);
}

static char cmdline[256];

/* one line of stdin: a key, or a command of the test (dump, snap FILE, sleep MS) - the command is an event of its
 * own, so that it runs after the keys before it have been carried out */
static int test_key(int ms)
{
	for (;;) {
		char *nl = memchr(ibuf, '\n', ilen), word[256];
		struct pollfd p = { 0, POLLIN, 0 };

		if (quit)
			return KE_QUIT;
		if (!nl) {
			ssize_t got;

			if (poll(&p, 1, ms) <= 0)
				return KE_NONE;
			got = read(0, ibuf + ilen, sizeof(ibuf) - ilen - 1);
			if (got <= 0)
				return KE_QUIT;
			ilen += (size_t)got;
			continue;
		}
		*nl = '\0';
		snprintf(word, sizeof(word), "%.255s", ibuf);
		ilen -= (size_t)(nl + 1 - ibuf);
		memmove(ibuf, nl + 1, ilen);
		if (!strcmp(word, "up"))
			return KE_UP;
		if (!strcmp(word, "down"))
			return KE_DOWN;
		if (!strcmp(word, "left"))
			return KE_LEFT;
		if (!strcmp(word, "right"))
			return KE_RIGHT;
		if (!strcmp(word, "ok"))
			return KE_OK;
		if (!strcmp(word, "back"))
			return KE_BACK;
		if (!strcmp(word, "home"))
			return KE_HOME;
		if (!strcmp(word, "power"))
			return KE_POWER;
		if (!strcmp(word, "volup"))
			return KE_VOL_UP;
		if (!strcmp(word, "voldown"))
			return KE_VOL_DOWN;
		if (!strcmp(word, "mute"))
			return KE_MUTE;
		if (!strcmp(word, "focusup"))
			return KE_FOCUS_UP;
		if (!strcmp(word, "focusdown"))
			return KE_FOCUS_DOWN;
		snprintf(cmdline, sizeof(cmdline), "%s", word);
		return KE_CMD;
	}
}

static void command(void)
{
	if (!strcmp(cmdline, "dump"))
		dump();
	else if (!strncmp(cmdline, "snap ", 5))
		snap(cmdline + 5);
	else if (!strncmp(cmdline, "sleep ", 6))
		usleep((useconds_t)atoi(cmdline + 6) * 1000);
}

static int pending_key;
static bool test;

static int next_key(int ms)
{
	int k = pending_key;

	pending_key = 0;
	return k ? k : test ? test_key(ms) : input_key(ms);
}

/* --- the page ------------------------------------------------------------------------------------------------ */

static unsigned dirty;
static bool timing;			/* H713_SETTINGS_TIMES: one journal line per drawing, for the key-to-wall measurement (S3) */

static double now_ms(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static void select_row(int to)
{
	dirty |= D_ROW(v.row) | D_ROW(to) | D_NOTE;
	v.row = to;
	row_of[v.area] = to;
}

static void open_area(int i)
{
	rows_enter(i);
	v.area = i;
	v.row = row_of[i] < visible_rows(&areas[i]) ? row_of[i] : 0;
	dirty |= D_AREAS;
}

static void corner_show(void)
{
	char shown[24];

	corner_move(v.corner, 0, 0, shown, sizeof(shown));	/* no step: just what the corner is */
	snprintf(v.corner_at, sizeof(v.corner_at), "%s", shown);
	corner_mask(v.corner);
	dirty |= D_NOTE;
}

static void keys_corners(int k)
{
	int dx = k == KE_LEFT ? -1 : k == KE_RIGHT ? 1 : 0, dy = k == KE_UP ? -1 : k == KE_DOWN ? 1 : 0;

	if (k == KE_BACK) {
		corner_mask(-1);
		v.f = F_ROWS;
		dirty |= D_ALL;
	} else if (k == KE_OK) {
		v.corner = (v.corner + 1) & 3;
		corner_show();
	} else if (k >= KE_UP && k <= KE_RIGHT) {
		corner_move(v.corner, dx, dy, v.corner_at, sizeof(v.corner_at));
		dirty |= D_NOTE;
	}
}

static void keys_rows(int k)
{
	struct area *a = &areas[v.area];
	struct row *r = visible_row(a, v.row);
	int n = visible_rows(a);

	if (k == KE_UP && v.row > 0)
		select_row(v.row - 1);
	else if (k == KE_DOWN && v.row < n - 1)
		select_row(v.row + 1);
	else if (k == KE_BACK) {
		v.f = F_AREAS;
		dirty |= D_AREAS;
	} else if ((k == KE_LEFT || k == KE_RIGHT) && (r->kind == R_SWITCH || r->kind == R_SLIDER || r->kind == R_STEPPER)) {
		int d = k == KE_RIGHT ? 1 : -1, k2;

		/* a held key arrives as a burst: one command for all of it, not one per press */
		if (r->kind != R_SWITCH) {
			while ((k2 = next_key(0)) == KE_LEFT || k2 == KE_RIGHT)
				d += k2 == KE_RIGHT ? 1 : -1;
			pending_key = k2;
		}
		if (d)
			r->apply(r, d);
		dirty |= D_ROW(v.row);
	} else if (k == KE_OK) {
		if (r->kind == R_SWITCH || r->kind == R_ACTION) {
			r->apply(r, 0);
			dirty |= r->kind == R_ACTION ? D_AREAS : D_ROW(v.row);
		} else if (r->kind == R_CHOICE && r->n) {
			v.f = F_CHOICE;
			v.choice = r->val;
			dirty |= D_ALL;
		} else if (r->kind == R_CORNERS) {
			corner_load();
			v.f = F_CORNERS;
			v.corner = 0;
			dirty |= D_ALL;
			corner_show();
		}
	}
}

static void keys_choice(int k)
{
	struct row *r = visible_row(&areas[v.area], v.row);

	if (k == KE_UP && v.choice > 0) {
		dirty |= D_ROW(v.choice) | D_ROW(v.choice - 1);
		v.choice--;
	} else if (k == KE_DOWN && v.choice < r->n - 1) {
		dirty |= D_ROW(v.choice) | D_ROW(v.choice + 1);
		v.choice++;
	} else if (k == KE_BACK || k == KE_OK) {
		if (k == KE_OK && v.choice != r->val) {
			r->val = v.choice;
			r->apply(r, 0);
		}
		v.f = F_ROWS;
		dirty |= D_ALL;
	}
}

static void keys_areas(int k)
{
	if (k == KE_UP && v.area > 0)
		open_area(v.area - 1);
	else if (k == KE_DOWN && v.area < nareas - 1)
		open_area(v.area + 1);
	else if ((k == KE_OK || k == KE_RIGHT) && visible_rows(&areas[v.area])) {
		v.f = F_ROWS;
		dirty |= D_AREAS;
	} else if (k == KE_BACK) {
		quit = 1;
	}
}

static void handle(int k)
{
	if (k == KE_HOME || k == KE_POWER) {
		quit = 1;			/* Home: the page closes (the launcher is one Home away); Power: and h713-power is told */
		if (k == KE_POWER && !test) {
			input_close();		/* first: the remote is h713-power's again */
			input_power();
		}
		return;
	}
	if (k >= KE_VOL_UP) {
		if (rows_hotkey(k))
			dirty |= D_AREAS;
		return;
	}
	switch (v.f) {
	case F_AREAS:
		keys_areas(k);
		break;
	case F_ROWS:
		keys_rows(k);
		break;
	case F_CHOICE:
		keys_choice(k);
		break;
	case F_CORNERS:
		keys_corners(k);
		break;
	}
}

static const char *env(const char *name, const char *def)
{
	const char *e = getenv(name);

	return e && *e ? e : def;
}

static bool idle_test;

static void on_term(int sig)
{
	(void)sig;
	quit = 1;
}

int main(int argc, char **argv)
{
	int w = 1920, h = 1080, first = 0, idle = atoi(env("H713_SETTINGS_IDLE", "120"));
	const char *font = env("H713_SETTINGS_FONT", OSD_FONT), *area = NULL;
	struct timespec last;

	p_tv = env("H713_SETTINGS_TV", "/run/h713-tv/ctl");
	p_warp = env("H713_SETTINGS_WARP", "/run/h713-warp/ctl");
	p_etc = env("H713_SETTINGS_ETC", "/etc/h713");
	p_bin = env("H713_SETTINGS_BIN", "");
	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--test"))
			test = true;
		else if (!strcmp(argv[i], "--size") && i + 1 < argc)
			sscanf(argv[++i], "%dx%d", &w, &h);
		else if (!strcmp(argv[i], "--font") && i + 1 < argc)
			font = argv[++i];
		else if (!strcmp(argv[i], "--area") && i + 1 < argc)
			area = argv[++i];
		else if (!strcmp(argv[i], "--idle") && i + 1 < argc)
			idle = atoi(argv[++i]), idle_test = true;
		else {
			fprintf(stderr, "usage: h713-settings [--area NAME] [--idle SECONDS] [--font FILE] | --test [--size WxH]\n");
			return 2;
		}
	}
	signal(SIGTERM, on_term);
	signal(SIGINT, on_term);
	signal(SIGPIPE, SIG_IGN);
	if (osd_font_open(font))
		fprintf(stderr, "h713-settings: font %s: not opened - the page has no text\n", font);
	if (test) {
		canvas.px = calloc((size_t)w * h, 4);
		canvas.w = canvas.stride = w;
		canvas.h = h;
		if (!canvas.px)
			return 1;
	} else {
		/* on the wall first (a page nobody can see is not opened), then the remote: nobody is deaf to a page nobody sees */
		if (page_open(&canvas, env("H713_SETTINGS_OSD", "/run/h713-osd/ctl")))
			return 3;
		if (!input_open()) {
			fprintf(stderr, "h713-settings: no remote to hold -- not opened\n");
			page_close();
			return 4;
		}
	}
	clock_gettime(CLOCK_MONOTONIC, &last);
	timing = *env("H713_SETTINGS_TIMES", "") != '\0';

	rows_init();
	for (int i = 0; area && i < nareas; i++)
		if (!strcasecmp(areas[i].name, area))
			first = i;
	open_area(first);
	dirty = D_ALL;
	for (;;) {
		bool changed = false;
		int k, box[4];

		rows_tick(&changed);
		if (changed)
			dirty |= D_AREAS;
		if (dirty) {
			double t0 = now_ms(), t1;

			ui_draw(&canvas, &v, dirty, box);
			t1 = now_ms();
			dirty = 0;
			if (!test && !page_show(box)) {
				fprintf(stderr, "h713-settings: nothing can be seen any more -- closing\n");
				break;
			}
			if (timing)
				fprintf(stderr, "h713-settings: drawn %.1f ms (%dx%d px), shown %.1f ms\n", t1 - t0, box[2], box[3],
					now_ms() - t1);
		}
		if (quit)
			break;
		k = rows_wake_ms();
		if (idle > 0 && (k < 0 || k > 1000))
			k = 1000;		/* looks at the clock once a second */
		k = next_key(k);
		if (k == KE_QUIT)
			break;
		if (k) {
			clock_gettime(CLOCK_MONOTONIC, &last);
			if (k == KE_CMD)
				command();
			else
				handle(k);
		} else if (!test || idle_test) {
			struct timespec t;

			clock_gettime(CLOCK_MONOTONIC, &t);
			if (idle > 0 && t.tv_sec - last.tv_sec >= idle) {
				fprintf(stderr, "h713-settings: no key for %d s -- closing\n", idle);
				break;
			}
		}
	}
	if (v.f == F_CORNERS)
		corner_mask(-1);
	rows_flush();
	if (!test) {
		input_close();
		page_close();
	}
	return 0;
}
