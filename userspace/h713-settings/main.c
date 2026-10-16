// SPDX-License-Identifier: GPL-2.0
/*
 * h713-settings - the settings page of the box, opened from the launcher and driven by the remote (README.md).
 *
 * The loop: a key arrives, the row it is on sends one command to its tool, the row is drawn again and shown. The keys
 * come from the remote's devices (input.c) and the picture goes to h713-osd's page channel (page.c); the host's build
 * (-DH713_TEST, testsink.c) has a sink of its own: keys as lines on stdin, the canvas as PAM pictures on request.
 */
#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>

#include "ui.h"

struct view v;
struct osd_canvas canvas;
static int row_of[MAXAREA];		/* the row each area was left on */
volatile sig_atomic_t quit;

/* the canvas as a PAM picture (RGB_ALPHA): the evidence of H713_SETTINGS_SNAP and the host tests' "snap" */
void snap(const char *path)
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

#ifdef H713_TEST
long test_outside;			/* pixels a drawing changed outside the pieces it reported: h713-osd puts only those, so each is a stale pixel on the wall */
int test_key(int ms);			/* testsink.c: the host's sink - keys as lines on stdin, the model as text, the canvas on request */
void test_command(void);
#else
#define test_key(ms) KE_QUIT		/* the board's binary has no test sink */
#define test_command() ((void)0)
#endif

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
static int patience = 10;		/* seconds the page waits for the picture to come back (H713_SETTINGS_PATIENCE) */
static double unseen_since;		/* since when h713-osd has only been keeping the page (ms); 0: it is on the wall */
static const char *snapdir = "";	/* H713_SETTINGS_SNAP: a directory; each drawing is kept in it */
static int snapn;
static bool timing;			/* H713_SETTINGS_TIMES: one journal line per drawing, for the key-to-wall measurement */

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
	dirty |= D_AREA(v.area) | D_AREA(i) | D_RIGHT | D_NOTE;	/* the two pills, the whole right pane */
	rows_enter(i);
	v.area = i;
	v.row = row_of[i] < visible_rows(&areas[i]) ? row_of[i] : 0;
}

/* the next slider that is judged on the picture, up or down from the visible row `from`; -1: none */
static int over_row(int from, int dir)
{
	struct area *a = &areas[v.area];

	for (int k = from + dir; k >= 0 && k < visible_rows(a); k += dir)
		if (visible_row(a, k)->over)
			return k;
	return -1;
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

/* a held key arrives as a burst: its presses are summed here and sent to the tool as one command, not one per press */
static int burst(int d)
{
	int k2;

	while ((k2 = next_key(0)) == KE_LEFT || k2 == KE_RIGHT)
		d += k2 == KE_RIGHT ? 1 : -1;
	pending_key = k2;
	return d;
}

/* the slider that is judged on the picture: the page shrinks to its one pill, OK or Back brings the page back */
static void keys_slider(int k)
{
	struct row *r = visible_row(&areas[v.area], v.row);
	int d, to;

	if (k == KE_LEFT || k == KE_RIGHT) {
		d = burst(k == KE_RIGHT ? 1 : -1);
		if (d)
			r->apply(r, d);
		dirty |= D_SLIDER;
	} else if ((k == KE_UP || k == KE_DOWN) && (to = over_row(v.row, k == KE_DOWN ? 1 : -1)) >= 0) {
		v.row = row_of[v.area] = to;
		dirty |= D_SLIDER;
	} else if (k == KE_OK || k == KE_BACK) {
		v.f = F_ROWS;
		dirty |= D_ALL;
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
		dirty |= D_AREA(v.area) | D_ROW(v.row) | D_NOTE;
	} else if ((k == KE_LEFT || k == KE_RIGHT) && (r->kind == R_SWITCH || r->kind == R_SLIDER || r->kind == R_STEPPER)) {
		int d = r->kind == R_SWITCH ? (k == KE_RIGHT ? 1 : -1) : burst(k == KE_RIGHT ? 1 : -1);

		if (d)
			r->apply(r, d);
		if (r->over) {
			v.f = F_SLIDER;		/* the first press on such a slider moves it and takes the page away */
			dirty |= D_ALL;
		} else {
			dirty |= D_ROW(v.row);
		}
	} else if (k == KE_OK) {
		if (r->over) {
			v.f = F_SLIDER;
			dirty |= D_ALL;
		} else if (r->kind == R_SWITCH || r->kind == R_ACTION) {
			r->apply(r, 0);
			dirty |= r->kind == R_ACTION ? D_RIGHT | D_NOTE : D_ROW(v.row);
		} else if (r->kind == R_CHOICE && r->n) {
			v.f = F_CHOICE;
			v.choice = r->val;
			dirty |= D_RIGHT | D_NOTE;
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
		dirty |= D_RIGHT | D_NOTE;
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
		dirty |= D_AREA(v.area) | D_ROW(v.row) | D_NOTE;
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
			dirty |= D_RIGHT;
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
	case F_SLIDER:
		keys_slider(k);
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
		if (!strcmp(argv[i], "--test")) {
#ifdef H713_TEST
			test = true;
#else
			fprintf(stderr, "h713-settings: built without the test sink\n");
			return 2;
#endif
		}
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
	if (osd_font_open(font)) {
		fprintf(stderr, "h713-settings: font %s: not opened%s\n", font, test ? " - the page has no text" : " -- a page without words is not opened");
		if (!test)
			return 5;
	}
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
	patience = atoi(env("H713_SETTINGS_PATIENCE", "10"));
	snapdir = env("H713_SETTINGS_SNAP", "");

	rows_init();
	for (int i = 0; area && i < nareas; i++)
		if (!strcasecmp(areas[i].name, area))
			first = i;
	open_area(first);
	dirty = D_ALL;
	for (;;) {
		bool changed = false;
		int k, box[MAXBOX][4];

		rows_tick(&changed);
		if (changed)
			dirty |= D_RIGHT;
		if (dirty) {
			double t0 = now_ms(), t1;
#ifdef H713_TEST
			uint32_t *before = test ? malloc((size_t)canvas.w * canvas.h * 4) : NULL;

			if (before)
				memcpy(before, canvas.px, (size_t)canvas.w * canvas.h * 4);
#endif
			int pieces = ui_draw(&canvas, &v, dirty, box), shown = 1;
#ifdef H713_TEST
			if (before) {
				for (int y = 0; y < canvas.h; y++)
					for (int x = 0; x < canvas.w; x++) {
						bool in = false;

						if (before[(size_t)y * canvas.w + x] == canvas.px[(size_t)y * canvas.stride + x])
							continue;
						for (int i = 0; i < pieces; i++)
							in |= x >= box[i][0] && x < box[i][0] + box[i][2] && y >= box[i][1] && y < box[i][1] + box[i][3];
						test_outside += !in;
					}
				free(before);
			}
#endif

			t1 = now_ms();
			dirty = 0;
			if (!test)
				for (int i = 0; i < pieces && shown >= 0; i++) {
					int s = page_show(box[i]);

					shown = s < 0 ? s : shown && s;
				}
			if (shown < 0) {
				fprintf(stderr, "h713-settings: h713-osd does not answer -- closing\n");
				break;
			}
			if (!test) {
				if (!shown && !unseen_since)
					unseen_since = now_ms();
				else if (shown)
					unseen_since = 0;
			}
			if (timing) {
				struct timespec rt;
				double key = input_stamp(), done;

				clock_gettime(CLOCK_REALTIME, &rt);
				done = rt.tv_sec * 1e3 + rt.tv_nsec / 1e6;
				fprintf(stderr, "h713-settings: drawn %.1f ms (%d pieces, %d px high), shown %.1f ms", t1 - t0, pieces,
					pieces ? box[pieces - 1][3] : 0, now_ms() - t1);
				if (key > 0 && done - key < 10000)	/* the key's own stamp to h713-osd's answer: the flip is up to a vsync later */
					fprintf(stderr, ", key to answer %.1f ms", done - key);
				fprintf(stderr, "\n");
			}
			if (*snapdir) {		/* evidence: the page's canvas after every drawing, as PAM (pam2png.py) */
				char p[300];

				snprintf(p, sizeof(p), "%s/%04d.pam", snapdir, ++snapn);
				snap(p);
			}
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
				test_command();
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
		/* nothing to be seen for a while (the signal does not come back): the remote is given back */
		if (unseen_since && now_ms() - unseen_since > patience * 1000) {
			fprintf(stderr, "h713-settings: nothing can be seen for %d s -- closing\n", patience);
			break;
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
