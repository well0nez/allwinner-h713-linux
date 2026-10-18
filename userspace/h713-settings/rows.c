// SPDX-License-Identifier: GPL-2.0
/*
 * The areas and their rows: what each one reads from a tool, and the one command it sends back. The page
 * (main.c, ui.c) knows nothing of h713-tv or h713-warp; this file knows nothing of pixels.
 *
 * What a tool cannot do has no row: no colour temperature or gamma (h713-tv has no runtime control for them; the white
 * balance and the colour by primary are the firmware's own, h713-tv wb / cm),
 * no sound output choice (one output), no autofocus at power-on (nothing runs it), no list of saved Wi-Fi
 * networks (wifi.env holds one). The report lists them.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <math.h>
#include <dirent.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>

#include "settings.h"

struct area areas[MAXAREA];
int nareas;

static char out[4096];
static bool have_accel, have_cam, have_motor, standby_ok;
static int active = -1;			/* the area that is open */

static double now_s(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

static int clampi(int v, int lo, int hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

static void add_opt(struct row *r, const char *arg, const char *label)
{
	if (r->n < MAXOPT) {
		snprintf(r->arg[r->n], sizeof(r->arg[0]), "%s", arg);
		snprintf(r->opt[r->n], sizeof(r->opt[0]), "%s", label);
		r->n++;
	}
}

static int opt_find(const struct row *r, const char *arg)
{
	for (int i = 0; i < r->n; i++)
		if (!strcmp(r->arg[i], arg))
			return i;
	return -1;
}

/* "energy_saving" -> "Energy saving" */
static void title(const char *s, char *d, size_t n)
{
	snprintf(d, n, "%s", s);
	for (char *c = d; *c; c++)
		if (*c == '_')
			*c = ' ';
	d[0] = (char)toupper((unsigned char)d[0]);
}

static struct row *new_row(struct area *a, const char *label, enum kind kind)
{
	struct row *r = &a->row[a->n++];

	r->label = label;
	r->kind = kind;
	return r;
}

/* --- the picture values reach the eMMC once, when the hand has rested (h713-tv ctl save) --------------------- */

static double save_at;			/* when ctl save is due; 0: nothing waits */

static void picture_dirty(void)
{
	save_at = now_s() + 1.5;
}

static void picture_save(void)
{
	char v[32];

	save_at = 0;
	tv("save");
	/* the kept values apply at the start only for the preset they belong to: "last" makes it the one kept */
	if (!conf_get(etc("tv.conf"), "preset", v, sizeof(v)) || strcmp(v, "last"))
		conf_set(etc("tv.conf"), "preset", "last");
}

void rows_flush(void)
{
	if (save_at)
		picture_save();
}

/* --- a few things the tools print --------------------------------------------------------------------------- */

static int num_after(const char *s, const char *tag, int def)
{
	const char *p = strstr(s, tag);

	return p ? atoi(p + strlen(tag)) : def;
}

static void features(void)
{
	const char *argv[] = { "h713-features", "status", NULL };
	static bool known;			/* the hardware does not change: asked once (a Python start is 0.2 s on the board) */
	char *save = NULL, *line;

	if (known)
		return;
	have_accel = have_cam = have_motor = false;
	if (run(argv, out, sizeof(out), 5000) != 0)
		return;		/* unknown: the controls stay hidden, nothing is guessed */
	known = true;
	for (line = strtok_r(out, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
		const char *w = line + strcspn(line, " ");
		bool there;

		w += strspn(w, " ");
		there = !strncmp(w, "present", 7);	/* "not present on this board" starts with "not" */

		if (!strncmp(line, "accelerometer", 13))
			have_accel = there;
		else if (!strncmp(line, "camera", 6))
			have_cam = there;
		else if (!strncmp(line, "focus-motor", 11))
			have_motor = there;
	}
}

/* --- the single job: a tool that runs for seconds (autofocus, measuring, focus by hand) ---------------------- */

static struct { pid_t pid; struct row *row; const char *ok, *bad; } job;
static int focus_pending;		/* presses of focus by hand that wait for the motor */
static struct row *r_focus;

static void focus_start(void);

static bool job_start(struct row *r, const char *const *argv, const char *running, const char *ok, const char *bad)
{
	if (job.pid > 0) {
		snprintf(r->text, sizeof(r->text), "Busy");
		return false;
	}
	job.pid = spawn(argv);
	job.row = r;
	job.ok = ok;
	job.bad = bad;
	snprintf(r->text, sizeof(r->text), "%s", job.pid > 0 ? running : bad);
	return job.pid > 0;
}

/* --- Picture ------------------------------------------------------------------------------------------------- */

static struct row *r_preset, *r_aspect;

static void slider_load_from(struct row *r, const char *list)
{
	/* "  brightness                 50  (0..100)" */
	char key[40], *p = strstr(list, "\n  ");

	for (; p; p = strstr(p + 1, "\n  ")) {
		int v, lo, hi;

		if (sscanf(p + 1, " %39s %d (%d..%d)", key, &v, &lo, &hi) == 4 && !strcmp(key, r->tag)) {
			r->val = v, r->min = lo, r->max = hi;
			r->hidden = false;
			return;
		}
	}
	r->hidden = true;		/* this device has no such control */
}

static void slider_apply(struct row *r, int dir)
{
	int v = clampi(r->val + dir * r->step, r->min, r->max);

	if (v == r->val || !tv("set %s %d", r->tag, v))
		return;
	r->val = v;
	picture_dirty();
}

static const char *aspect_label(const char *a)
{
	return !strcmp(a, "auto") ? "Auto" : !strcmp(a, "proportional") ? "Original" : !strcmp(a, "full") ? "Fill" : a;
}

static void preset_apply(struct row *r, int dir)
{
	(void)dir;
	if (tv("preset %s", r->arg[r->val]))
		picture_dirty();
	areas[0].enter(&areas[0]);	/* the nine controls moved with the preset */
}

/* the value of a choice as the tool says it now (the answer to a bare ask), not as it was asked for: a refusal shows */
static void choice_read(struct row *r, bool (*ask)(const char *fmt, ...), const char *cmd, const char *prefix)
{
	char cur[24] = "";

	if (ask("%s", cmd) && !strncmp(reply, prefix, strlen(prefix)) && sscanf(reply + strlen(prefix), "%23s", cur) == 1 &&
	    opt_find(r, cur) >= 0)
		r->val = opt_find(r, cur);
}

static void aspect_apply(struct row *r, int dir)
{
	(void)dir;
	if (tv("aspect %s", r->arg[r->val]))
		picture_dirty();
	choice_read(r, tv, "aspect", "ok aspect ");
}

static void picture_reset(struct row *r, int dir)
{
	(void)dir;
	tv("preset standard");
	tv("aspect auto");
	picture_save();
	areas[0].enter(&areas[0]);
	snprintf(r->text, sizeof(r->text), "Done");
}

static void picture_enter(struct area *a)
{
	char *p, *save = NULL, cur[40] = "";

	tv("list");
	snprintf(out, sizeof(out), "%s", reply);
	for (int i = 0; i < a->n; i++)
		if (a->row[i].kind == R_SLIDER)
			slider_load_from(&a->row[i], out);
	/* the presets: asking without a name makes h713-tv list the ones this device has */
	r_preset->n = 0;
	tv("preset");
	p = strstr(reply, "name: ");
	if (p)
		for (char *w = strtok_r(p + 6, " \n", &save); w; w = strtok_r(NULL, " \n", &save)) {
			char label[24];

			title(w, label, sizeof(label));
			add_opt(r_preset, w, label);
		}
	r_preset->hidden = !r_preset->n;
	tv("status brief");		/* 8 ms; the full status asks the firmware and takes 55 */
	p = strstr(reply, "\npreset ");
	if (p)
		sscanf(p + 8, " %39s", cur);
	r_preset->val = opt_find(r_preset, cur) < 0 ? 0 : opt_find(r_preset, cur);
	r_aspect->n = 0;
	r_aspect->hidden = !tv("aspect");
	if ((p = strstr(reply, "possible: "))) {
		for (char *w = strtok_r(p + 10, " \n", &save); w; w = strtok_r(NULL, " \n", &save))
			if (strcmp(w, "zoom"))		/* refused: the firmware stops the picture with it */
				add_opt(r_aspect, w, aspect_label(w));
		tv("aspect");
		sscanf(reply, "ok aspect %39s", cur);
		r_aspect->val = opt_find(r_aspect, cur) < 0 ? 0 : opt_find(r_aspect, cur);
	}
}

/* --- White balance and Colour: the firmware's own (h713-tv ctl wb, ctl cm) --------------------------------- */

/*
 * Two sliders for the eye, no instrument: "Warm - Cool" and "Green - Magenta", -50..+50. They only ever LOWER a gain
 * (so white never clips): cool lowers red, warm lowers blue, magenta lowers green, green lowers red and blue; each end is
 * 20 % off (s = 0.004 per step). The six values go to h713-tv in one command; the offsets stay as they are.
 */
#define WB_S 0.004

static struct row *r_wb_warm, *r_wb_tint, *r_wb_gone;
static int wb_off[3] = { 512, 512, 512 };	/* the offsets h713-tv holds: the sliders do not touch them */

static void wb_gains(int w, int t, int g[3])
{
	double kr = (1 - WB_S * (w > 0 ? w : 0)) * (1 - WB_S * (t < 0 ? -t : 0));
	double kg = 1 - WB_S * (t > 0 ? t : 0);
	double kb = (1 - WB_S * (w < 0 ? -w : 0)) * (1 - WB_S * (t < 0 ? -t : 0));

	g[0] = (int)lround(512 * kr);
	g[1] = (int)lround(512 * kg);
	g[2] = (int)lround(512 * kb);
}

/* the sliders a set of gains would have come from (to the nearest step); 0, 0 for gains the sliders cannot make */
static void wb_positions(const int g[3], int *w, int *t)
{
	double r = g[0] / 512.0, gg = g[1] / 512.0, b = g[2] / 512.0, f, tt, ww;

	*w = *t = 0;
	if (g[0] > 512 || g[1] > 512 || g[2] > 512)
		return;
	if (gg < 1) {				/* magenta: green is lowered, red and blue only by the warm/cool slider */
		tt = (1 - gg) / WB_S;
		ww = r < 1 ? (1 - r) / WB_S : b < 1 ? -(1 - b) / WB_S : 0;
	} else {				/* green or none: red and blue share the factor (1 - s|t|) */
		f = r > b ? r : b;
		tt = -(1 - f) / WB_S;
		ww = f > 0 ? (r < b ? (1 - r / f) / WB_S : b < r ? -(1 - b / f) / WB_S : 0) : 0;
	}
	*t = clampi((int)lround(tt), -50, 50);
	*w = clampi((int)lround(ww), -50, 50);
}

static bool wb_send(void)
{
	int g[3];

	wb_gains(r_wb_warm->val, r_wb_tint->val, g);
	return tv("wb %d %d %d %d %d %d", g[0], g[1], g[2], wb_off[0], wb_off[1], wb_off[2]);
}

static void wb_slider_apply(struct row *r, int dir)
{
	int old = r->val, v = clampi(r->val + dir * r->step, r->min, r->max);

	if (v == old)
		return;
	r->val = v;
	if (!wb_send()) {
		r->val = old;
		return;
	}
	picture_dirty();
}

static void wb_reset(struct row *r, int dir)
{
	(void)dir;
	if (tv("wb reset")) {
		r_wb_warm->val = r_wb_tint->val = 0;
		wb_off[0] = wb_off[1] = wb_off[2] = 512;
		picture_save();
		snprintf(r->text, sizeof(r->text), "Done");
	} else {
		snprintf(r->text, sizeof(r->text), "Failed");
	}
}

static void wb_enter(struct area *a)
{
	int v[6], g[3];
	bool there = tv("wb") && !strstr(reply, "not available") &&
		     sscanf(reply, "ok wb %d %d %d %d %d %d", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) == 6;

	for (int i = 0; i < a->n; i++)
		a->row[i].hidden = there ? &a->row[i] == r_wb_gone : &a->row[i] != r_wb_gone;
	if (!there)
		return;
	g[0] = v[0], g[1] = v[1], g[2] = v[2];
	wb_off[0] = v[3], wb_off[1] = v[4], wb_off[2] = v[5];
	wb_positions(g, &r_wb_warm->val, &r_wb_tint->val);
	a->row[2].text[0] = '\0';
}

#ifdef H713_TEST
/* the host test sweeps the whole range: the lowest gain the sliders make, and the worst distance a position comes back from */
void test_wb_sweep(int *lowest, int *worst, int *worst_w, int *worst_t)
{
	*lowest = 512;
	*worst = 0;
	for (int w = -50; w <= 50; w++)
		for (int t = -50; t <= 50; t++) {
			int g[3], w2, t2, d;

			wb_gains(w, t, g);
			for (int i = 0; i < 3; i++)
				if (g[i] < *lowest)
					*lowest = g[i];
			wb_positions(g, &w2, &t2);
			d = abs(w2 - w) > abs(t2 - t) ? abs(w2 - w) : abs(t2 - t);
			if (d > *worst) {
				*worst = d;
				*worst_w = w;
				*worst_t = t;
			}
		}
}
#endif

/*
 * Colour by primary: one choice of the colour, then its hue and its saturation, as a step on what the picture mode itself
 * puts there (0 = as the board comes). Six of the firmware's ten axes are offered: the primaries and secondaries.
 */
static struct row *r_cm_prim, *r_cm_hue, *r_cm_sat, *r_cm_gone;

static const char *cm_axis(void)
{
	return r_cm_prim->arg[r_cm_prim->val];
}

/* the two sliders as h713-tv holds them for the chosen colour */
static void cm_load(void)
{
	int h = 0, sa = 0;
	char *p;

	if (tv("cm %s", cm_axis()) && (p = strstr(reply, "hue ")))
		sscanf(p, "hue %d sat %d", &h, &sa);
	r_cm_hue->val = clampi(h, r_cm_hue->min, r_cm_hue->max);
	r_cm_sat->val = clampi(sa, r_cm_sat->min, r_cm_sat->max);
}

static void cm_prim_apply(struct row *r, int dir)
{
	(void)r;
	(void)dir;
	cm_load();
}

static void cm_slider_apply(struct row *r, int dir)
{
	int old = r->val, v = clampi(r->val + dir * r->step, r->min, r->max);

	if (v == old)
		return;
	r->val = v;
	if (!tv("set cm_%s_%s %d", cm_axis(), r->tag, v)) {
		r->val = old;
		return;
	}
	picture_dirty();
}

static void cm_reset(struct row *r, int dir)
{
	(void)dir;
	if (tv("cm reset")) {
		r_cm_hue->val = r_cm_sat->val = 0;
		picture_save();
		snprintf(r->text, sizeof(r->text), "Done");
	} else {
		snprintf(r->text, sizeof(r->text), "Failed");
	}
}

static void cm_enter(struct area *a)
{
	bool there = tv("wb") && !strstr(reply, "not available");	/* the same machinery as the white balance */

	for (int i = 0; i < a->n; i++)
		a->row[i].hidden = there ? &a->row[i] == r_cm_gone : &a->row[i] != r_cm_gone;
	if (there)
		cm_load();
}

/* --- Keystone ------------------------------------------------------------------------------------------------ */

static const char *const corner_name[4] = { "tl", "tr", "bl", "br" };
static int corner_v[4][2];
static struct row *r_corners, *r_auto, *r_afterfocus;

static void after_move_set(const char *v)
{
	const char *restart[] = { "systemctl", "restart", "--no-block", "h713-keystone-auto", NULL };
	char o[128];

	conf_set(etc("keystone.conf"), "after_move", v);
	run(restart, o, sizeof(o), 5000);	/* the unit reads the key at its start; queued, not waited for */
}

static void after_move_load(void)
{
	char v[32] = "off";

	conf_get(etc("keystone.conf"), "after_move", v, sizeof(v));
	r_auto->val = strcmp(v, "off") != 0;
	r_afterfocus->val = !strcmp(v, "keystone+focus");
}

static void auto_apply(struct row *r, int dir)
{
	r->val = dir ? dir > 0 : !r->val;
	after_move_set(r->val ? "keystone" : "off");
	after_move_load();
}

static void afterfocus_apply(struct row *r, int dir)
{
	r->val = dir ? dir > 0 : !r->val;
	/* the autofocus after a move runs behind the automatic keystone: turning it on turns that on too */
	after_move_set(r->val ? "keystone+focus" : r_auto->val ? "keystone" : "off");
	after_move_load();
}

static void measure_apply(struct row *r, int dir)
{
	const char *argv[] = { "h713-keystone", "once", "--apply", NULL };

	(void)dir;
	job_start(r, argv, "Measuring...", "Done", "Failed");
}

static void zoom_apply(struct row *r, int dir)
{
	int v = clampi(r->val + dir * r->step, r->min, r->max);

	if (v == r->val || !warp("zoom %d", v))
		return;
	if (v < 100)
		warp("on");		/* a screen zoom needs the warp, as the web page does it */
	r->val = v;
}

static void mode_apply(struct row *r, int dir)
{
	(void)dir;
	warp("mode %s", r->arg[r->val]);
	choice_read(r, warp, "mode", "ok mode ");
}

static void keystone_reset(struct row *r, int dir)
{
	(void)dir;
	warp("keystone reset");
	warp("zoom 100");
	memset(corner_v, 0, sizeof(corner_v));
	areas[AREA_KEYSTONE].enter(&areas[AREA_KEYSTONE]);
	snprintf(r->text, sizeof(r->text), "Done");
}

static void keystone_enter(struct area *a)
{
	struct row *z = &a->row[3], *m = &a->row[4];
	static const char *const word[] = { "front", "rear", "ceiling", "rear-ceiling" };
	static const char *const label[] = { "Front", "Rear", "Ceiling", "Rear ceiling" };
	char cur[24] = "front";

	features();
	after_move_load();
	r_auto->hidden = !have_accel;
	a->row[1].hidden = !have_accel;
	r_corners->hidden = !warp("zoom");
	z->hidden = m->hidden = r_corners->hidden;
	z->val = clampi(num_after(reply, "ok zoom ", 100), z->min, z->max);
	if (m->n == 0)
		for (int i = 0; i < 4; i++)
			add_opt(m, word[i], label[i]);
	warp("mode");
	sscanf(reply, "ok mode %23s", cur);
	m->val = opt_find(m, cur) < 0 ? 0 : opt_find(m, cur);
	corner_load();
}

/* the eight values as h713-warp keeps them in warp.conf (it rewrites the file at every change) */
void corner_load(void)
{
	char v[16];

	for (int c = 0; c < 4; c++)
		for (int x = 0; x < 2; x++) {
			char key[8];

			snprintf(key, sizeof(key), "%s_%c", corner_name[c], x ? 'y' : 'x');
			corner_v[c][x] = conf_get(etc("warp.conf"), key, v, sizeof(v)) ? atoi(v) : 0;
		}
}

bool corner_move(int c, int dx, int dy, char *shown, size_t n)
{
	/* the arrow is the way the corner goes on the wall; the warp's numbers count inward (0..1000 per mille) */
	int step[2] = { (c & 1 ? -dx : dx) * 10, (c & 2 ? -dy : dy) * 10 };
	bool ok = true;

	for (int a = 0; a < 2; a++) {
		char key[8];

		if (!step[a])
			continue;
		ok &= warp("keystone nudge %s %c %d", corner_name[c], a ? 'y' : 'x', step[a]);
		snprintf(key, sizeof(key), "%s_%c", corner_name[c], a ? 'y' : 'x');
		if (ok && strstr(reply, key))
			corner_v[c][a] = num_after(reply, " = ", corner_v[c][a]);
	}
	snprintf(shown, n, "%d, %d", corner_v[c][0], corner_v[c][1]);
	return ok;
}

void corner_mask(int c)
{
	if (c < 0)
		warp("test off");
	else
		warp("test mask %s", corner_name[c]);
}

/* --- Sound --------------------------------------------------------------------------------------------------- */

static void volume_apply(struct row *r, int dir)
{
	int v = clampi(r->val + dir * r->step, r->min, r->max);

	if (v != r->val && tv("volume %d", v))
		r->val = v;
}

static void mute_apply(struct row *r, int dir)
{
	r->val = dir ? dir > 0 : !r->val;
	tv("mute %s", r->val ? "on" : "off");
	if (tv("mute"))
		r->val = !strncmp(reply, "ok mute on", 10);
}

static void sound_enter(struct area *a)
{
	tv("volume");
	a->row[0].val = clampi(num_after(reply, "ok volume ", 50), 0, 100);
	a->row[0].hidden = a->row[1].hidden = !strncmp(reply, "error", 5);
	tv("mute");
	a->row[1].val = !strncmp(reply, "ok mute on", 10);
}

/* the keys h713-keys would act on - it sees nothing while the page holds the remote */
bool rows_hotkey(int key)
{
	char v[16];
	int step = 5, cur, vol;

	if (key == KE_VOL_UP || key == KE_VOL_DOWN) {
		if (conf_get(etc("keys.conf"), "volume_step", v, sizeof(v)))
			step = clampi(atoi(v), 1, 20);
		tv("volume");
		cur = num_after(reply, "ok volume ", 50);
		vol = clampi(cur + (key == KE_VOL_UP ? step : -step), 0, 100);
		tv("volume %d", vol);
		tv("mute off");		/* both lift a mute: the owner's choice of 11.10.2026 */
	} else if (key == KE_MUTE) {
		tv("mute");
		tv("mute %s", strncmp(reply, "ok mute on", 10) ? "on" : "off");
	} else if (key == KE_FOCUS_UP || key == KE_FOCUS_DOWN) {
		if (r_focus && !r_focus->hidden)
			r_focus->apply(r_focus, key == KE_FOCUS_UP ? 1 : -1);
		return false;
	} else {
		return false;
	}
	if (active != AREA_SOUND)
		return false;
	sound_enter(&areas[AREA_SOUND]);
	return true;
}

/* --- Focus --------------------------------------------------------------------------------------------------- */

static void autofocus_apply(struct row *r, int dir)
{
	const char *argv[] = { "h713-autofocus", "-q", "run", NULL };

	(void)dir;
	job_start(r, argv, "Focusing...", "Done", "No sharp point found");
}

static void focus_start(void)
{
	char n[16], v[16] = "20", word[8];
	const char *argv[] = { "h713-focus", word, n, NULL };
	int steps = 20;

	if (job.pid > 0 || !focus_pending)
		return;
	if (conf_get(etc("keys.conf"), "focus_steps", v, sizeof(v)))
		steps = clampi(atoi(v), 1, 100);
	snprintf(word, sizeof(word), "%s", focus_pending > 0 ? "up" : "down");
	snprintf(n, sizeof(n), "%d", clampi(abs(focus_pending) * steps, 1, 100));
	focus_pending = 0;
	job.pid = spawn(argv);
	job.row = r_focus;
	job.ok = job.bad = "< >";
}

static void focus_by_hand(struct row *r, int dir)
{
	(void)r;
	if (job.pid > 0 && job.row != r_focus)
		return;			/* the autofocus has the motor: a press now would run when it is over */
	focus_pending += dir;
	focus_start();
}

static void focus_enter(struct area *a)
{
	features();
	after_move_load();
	a->row[0].hidden = !(have_cam && have_motor);
	a->row[1].hidden = !(have_accel && have_cam && have_motor);
	a->row[2].hidden = !have_motor;
}

/* --- Input --------------------------------------------------------------------------------------------------- */

/*
 * What the projector shows when it has started: h713-keys reads `on_start` once, at the start of the box. The options are the
 * launcher, the HDMI input, every mode - a launcher.d entry that names a `unit`: Kodi, and Browser or Desktop with no change here - and
 * the one that ran last. A mode is named by its file (20-kodi.conf: kodi), as h713-keys names it.
 *
 * There is no "Source" row any more (Marco, 17.10.2026): which of the two the wall shows is not a thing to choose - a program that runs
 * is on the wall, with none it is the HDMI input. `h713-tv ctl source` stays a tool for tests and the web page.
 */
struct mode {
	char id[24], label[24], unit[64];
};

static char onstart_note[MAXOPT][128];

/* the modes in file-name order, at most `max`; how many */
static int modes_read(struct mode *m, int max)
{
	struct dirent **names;
	int n = scandir(etc("launcher.d"), &names, NULL, alphasort), k = 0;

	for (int i = 0; i < n; i++) {
		const char *f = names[i]->d_name;
		size_t len = strlen(f), digits = strspn(f, "0123456789");
		const char *id = digits && f[digits] == '-' ? f + digits + 1 : f;	/* "20-kodi.conf" is "kodi" */
		char file[300];

		if (len > 5 && !strcmp(f + len - 5, ".conf") && k < max) {
			snprintf(file, sizeof(file), "%s/%s", etc("launcher.d"), f);
			if (conf_get(file, "unit", m[k].unit, sizeof(m[k].unit)) && m[k].unit[0] &&
			    conf_get(file, "label", m[k].label, sizeof(m[k].label)) && m[k].label[0]) {
				snprintf(m[k].id, sizeof(m[k].id), "%.*s", (int)(len - 5 - (size_t)(id - f)), id);
				k++;
			}
		}
		free(names[i]);
	}
	if (n >= 0)
		free(names);
	return k;
}

static void onstart_apply(struct row *r, int dir)
{
	char v[24];

	(void)dir;
	conf_set(etc("keys.conf"), "on_start", r->arg[r->val]);	/* h713-keys reads it at the next start */
	if (conf_get(etc("keys.conf"), "on_start", v, sizeof(v)) && opt_find(r, v) >= 0)
		r->val = opt_find(r, v);	/* what the file holds, not what was asked */
}

static void input_enter(struct area *a)
{
	struct row *st = &a->row[0], *now = &a->row[1];
	struct mode m[MAXOPT - 3];
	const char *name = NULL;
	char v[24] = "";
	bool client;
	int n = modes_read(m, MAXOPT - 3);

	if (!st->n) {
		add_opt(st, "launcher", "Launcher");
		add_opt(st, "hdmi", "HDMI input");
		for (int i = 0; i < n; i++)
			add_opt(st, m[i].id, m[i].label);
		add_opt(st, "last", "Last used");
		for (int i = 0; i < st->n; i++) {
			if (!strcmp(st->arg[i], "launcher"))
				st->opt_note[i] = "Launcher: when the projector has started, the launcher is on the wall, like the home screen of a phone.";
			else if (!strcmp(st->arg[i], "hdmi"))
				st->opt_note[i] = "HDMI input: the HDMI picture, as soon as there is one.";
			else if (!strcmp(st->arg[i], "last"))
				st->opt_note[i] = "Last used: what ran when the projector was switched off comes back, the HDMI input or a program.";
			else {
				snprintf(onstart_note[i], sizeof(onstart_note[i]), "%s: %s opens by itself when the projector has started.",
					 st->opt[i], st->opt[i]);
				st->opt_note[i] = onstart_note[i];
			}
		}
	}
	conf_get(etc("keys.conf"), "on_start", v, sizeof(v));	/* not in the file: the launcher, h713-keys' default */
	st->val = opt_find(st, v) < 0 ? 0 : opt_find(st, v);
	st->hidden = access(etc("launcher.d"), F_OK) != 0;	/* no launcher in this image */
	now->hidden = !tv("source");
	client = strstr(reply, "Wayland client") != NULL;	/* the next question overwrites the reply */
	for (int i = 0; i < n && !name; i++) {
		const char *argv[] = { "systemctl", "is-active", "--quiet", m[i].unit, NULL };
		char o[64];

		if (run(argv, o, sizeof(o), 3000) == 0)
			name = m[i].label;			/* the mode that runs: its own name, Browser is not Kodi */
	}
	/* the HDMI input with nothing to show: h713-osd's page "No signal on HDMI" is on the wall (h713-tv's status says so: the line
	 * "nosignal        page: ...") - no mode runs, and the wall is not "the HDMI picture" */
	if (!name && !client && !now->hidden && tv("status brief") && strstr(reply, "\nnosignal        page"))
		name = "No HDMI signal";
	snprintf(now->text, sizeof(now->text), "%s", name ? name : client ? "Kodi" : "HDMI picture");
}

/* --- Power --------------------------------------------------------------------------------------------------- */

static void power_apply(struct row *r, int dir)
{
	const char *argv[] = { "h713-power", "set", "default", r->arg[r->val], NULL };
	char o[256];

	(void)dir;
	run(argv, o, sizeof(o), 15000);
	if (conf_get(etc("power.conf"), "default", o, sizeof(o)) && opt_find(r, o) >= 0)
		r->val = opt_find(r, o);	/* what h713-power wrote, not what was asked */
}

static void remote_apply(struct row *r, int dir)
{
	const char *argv[] = { "h713-power", "set", "remote", NULL, NULL };
	char o[256];

	r->val = dir ? dir > 0 : !r->val;
	argv[3] = r->val ? "on" : "off";
	run(argv, o, sizeof(o), 15000);
	if (conf_get(etc("power.conf"), "remote", o, sizeof(o)))
		r->val = strcmp(o, "off") != 0;
}

static void power_enter(struct area *a)
{
	const char *argv[] = { "h713-power", "status", NULL };
	struct row *k = &a->row[0], *rem = &a->row[1];
	char v[24] = "poweroff";

	static bool asked;			/* whether a standby can happen does not change while the box runs */

	if (!k->n)
		add_opt(k, "poweroff", "Power off");
	if (!asked) {
		standby_ok = run(argv, out, sizeof(out), 8000) == 0 && strstr(out, "offered in the countdown");
		asked = true;
	}
	if (standby_ok && k->n == 1)
		add_opt(k, "standby", "Standby");
	if (!conf_get(etc("power.conf"), "default", v, sizeof(v)))
		conf_get(etc("power.conf"), "short", v, sizeof(v));
	k->val = opt_find(k, v) < 0 ? 0 : opt_find(k, v);
	conf_get(etc("power.conf"), "remote", v, sizeof(v));
	rem->val = strcmp(v, "off") != 0;
}

/* --- Wi-Fi: shown, not changed (a password needs a keyboard; wifi.env holds one network) -------------------- */

static double wifi_at;

static void wifi_enter(struct area *a)
{
	const char *iw[] = { "iw", "dev", "wlan0", "link", NULL }, *ip[] = { "ip", "-4", "-brief", "addr", "show", "dev", "wlan0", NULL };
	char mode[16] = "ap", ssid[40] = "-", *p;
	struct row *rm = &a->row[0], *rn = &a->row[1], *rs = &a->row[2], *ra = &a->row[3];

	conf_get(etc("wifi.env"), "mode", mode, sizeof(mode));	/* the password is never read */
	snprintf(rm->text, sizeof(rm->text), "%s", !strcmp(mode, "sta") ? "Client" : !strcmp(mode, "off") ? "Off" : "Access point");
	snprintf(rn->text, sizeof(rn->text), "-");
	snprintf(rs->text, sizeof(rs->text), "-");
	if (!strcmp(mode, "sta") && run(iw, out, sizeof(out), 4000) == 0 && (p = strstr(out, "SSID: "))) {
		int dbm;

		snprintf(rn->text, sizeof(rn->text), "%.*s", (int)strcspn(p + 6, "\n"), p + 6);
		if ((p = strstr(out, "signal: ")) && sscanf(p + 8, "%d", &dbm) == 1)
			snprintf(rs->text, sizeof(rs->text), "%d dBm, %s", dbm,
				 dbm >= -55 ? "excellent" : dbm >= -67 ? "good" : dbm >= -75 ? "fair" : "weak");
	} else if (!strcmp(mode, "sta")) {
		snprintf(rn->text, sizeof(rn->text), "Not connected");
	} else {
		conf_get(etc("wifi.env"), "ssid", ssid, sizeof(ssid));
		snprintf(rn->text, sizeof(rn->text), "%s", ssid);
	}
	snprintf(ra->text, sizeof(ra->text), "-");
	if (run(ip, out, sizeof(out), 4000) == 0 && (p = strstr(out, "UP")))
		sscanf(p + 2, " %39[^/ \n]", ra->text);
	wifi_at = now_s() + 5.0;
}

/* --- the page's timers: jobs that ended, the save when the hand has rested, the Wi-Fi line ------------------ */

void rows_enter(int i)
{
	/*
	 * What an action said after it ran ("Done", "Failed") belongs to that visit of its area: leaving the area clears it
	 * (Marco 18.10.2026: "Reset done" was still there after a change of area). A job that still runs keeps its line; one
	 * that ends while its area is not open shows its result on the next visit, once.
	 */
	if (active >= 0 && active != i)
		for (int k = 0; k < areas[active].n; k++) {
			struct row *r = &areas[active].row[k];

			if (r->kind == R_ACTION && !(job.pid > 0 && job.row == r))
				r->text[0] = 0;
		}
	active = i;
	if (areas[i].enter)
		areas[i].enter(&areas[i]);
}

int rows_wake_ms(void)
{
	double next = 0, t = now_s();

	if (job.pid > 0)
		next = t + 0.2;
	if (save_at && (!next || save_at < next))
		next = save_at;
	if (active == AREA_WIFI && wifi_at && (!next || wifi_at < next))
		next = wifi_at;
	return next ? (int)((next > t ? next - t : 0) * 1000) + 1 : -1;
}

void rows_tick(bool *changed)
{
	int status;

	if (job.pid > 0 && waitpid(job.pid, &status, WNOHANG) == job.pid) {
		bool good = WIFEXITED(status) && WEXITSTATUS(status) == 0;

		snprintf(job.row->text, sizeof(job.row->text), "%s", good ? job.ok : job.bad);
		job.pid = 0;
		*changed = true;
		focus_start();
	}
	if (save_at && now_s() >= save_at)
		picture_save();
	if (active == AREA_WIFI && wifi_at && now_s() >= wifi_at) {
		wifi_enter(&areas[AREA_WIFI]);
		*changed = true;
	}
}

/* --- the tables ---------------------------------------------------------------------------------------------- */

static struct row *slider(struct area *a, const char *label, const char *tag, int step, void (*apply)(struct row *, int))
{
	struct row *r = new_row(a, label, R_SLIDER);

	r->tag = tag;
	r->step = step;
	r->max = 100;
	r->apply = apply;
	r->over = apply != volume_apply;	/* the volume is not judged on the picture */
	return r;
}

static struct row *info(struct area *a, const char *label)
{
	struct row *r = new_row(a, label, R_INFO);

	snprintf(r->text, sizeof(r->text), "-");
	return r;
}

void rows_init(void)
{
	struct area *a;
	struct row *r;

	nareas = 0;
	a = &areas[nareas++];
	a->name = "Picture", a->icon = "pic", a->enter = picture_enter;
	slider(a, "Brightness", "brightness", 5, slider_apply);
	slider(a, "Contrast", "contrast", 5, slider_apply);
	slider(a, "Colour", "saturation", 5, slider_apply);
	slider(a, "Tint", "hue", 5, slider_apply);
	slider(a, "Sharpness", "sharpness", 5, slider_apply);
	r_preset = r = new_row(a, "Picture mode", R_CHOICE);
	r->apply = preset_apply, r->more = true;
	r_aspect = r = new_row(a, "Aspect ratio", R_CHOICE);
	r->apply = aspect_apply, r->more = true;
	r = new_row(a, "Reset picture", R_ACTION);
	r->apply = picture_reset;

	a = &areas[nareas++];
	a->name = "White balance", a->icon = "pic", a->enter = wb_enter;
	r_wb_warm = r = slider(a, "Warm - Cool", "wb_warm", 2, wb_slider_apply);
	r->min = -50, r->max = 50;
	r->note = "Left: warmer, less blue. Right: cooler, less red. Judged on the picture.";
	r_wb_tint = r = slider(a, "Green - Magenta", "wb_tint", 2, wb_slider_apply);
	r->min = -50, r->max = 50;
	r->note = "Left: greener. Right: more magenta. Judged on the picture.";
	r = new_row(a, "Reset", R_ACTION);
	r->apply = wb_reset;
	r_wb_gone = r = info(a, "White balance");
	snprintf(r->text, sizeof(r->text), "Not available");
	r->hidden = true;

	a = &areas[nareas++];
	a->name = "Colour", a->icon = "pic", a->enter = cm_enter;
	r_cm_prim = r = new_row(a, "Primary colour", R_CHOICE);
	r->apply = cm_prim_apply, r->more = true;
	add_opt(r, "red", "Red");
	add_opt(r, "yellow", "Yellow");
	add_opt(r, "green", "Green");
	add_opt(r, "cyan", "Cyan");
	add_opt(r, "blue", "Blue");
	add_opt(r, "purple", "Purple");
	r->val = 1;				/* Yellow: the one that is judged most often */
	r_cm_hue = r = slider(a, "Hue", "hue", 5, cm_slider_apply);
	r->min = -100, r->max = 100;
	r->note = "Turns this colour towards its neighbour on one side or the other. Other colours and white stay.";
	r_cm_sat = r = slider(a, "Saturation", "sat", 5, cm_slider_apply);
	r->min = -100, r->max = 100;
	r->note = "Makes this colour paler or stronger. Other colours and white stay.";
	r = new_row(a, "Reset", R_ACTION);
	r->apply = cm_reset;
	r_cm_gone = r = info(a, "Colour");
	snprintf(r->text, sizeof(r->text), "Not available");
	r->hidden = true;

	a = &areas[nareas++];
	a->name = "Keystone", a->icon = "trap", a->enter = keystone_enter;
	r_auto = r = new_row(a, "Auto keystone", R_SWITCH);
	r->apply = auto_apply;
	r->note = "Corrects the picture once after the projector has been moved.";
	r = new_row(a, "Measure again now", R_ACTION);
	r->apply = measure_apply, r->more = true;
	r_corners = r = new_row(a, "Adjust corners by hand", R_CORNERS);
	r->more = true;
	r = slider(a, "Zoom", "zoom", 5, zoom_apply);
	r->min = 50;
	r = new_row(a, "Projection", R_CHOICE);
	r->apply = mode_apply, r->more = true;
	r = new_row(a, "Reset keystone", R_ACTION);
	r->apply = keystone_reset;

	a = &areas[nareas++];
	a->name = "Sound", a->icon = "speaker", a->enter = sound_enter;
	slider(a, "Volume", NULL, 5, volume_apply);
	r = new_row(a, "Mute", R_SWITCH);
	r->apply = mute_apply;

	a = &areas[nareas++];
	a->name = "Focus", a->icon = "focus", a->enter = focus_enter;
	r = new_row(a, "Autofocus now", R_ACTION);
	r->apply = autofocus_apply, r->more = true;
	r_afterfocus = r = new_row(a, "Autofocus after a move", R_SWITCH);
	r->apply = afterfocus_apply;
	r->note = "Needs Auto keystone: it runs after the keystone has been corrected.";
	r_focus = r = new_row(a, "Focus by hand", R_STEPPER);
	r->apply = focus_by_hand;
	snprintf(r->text, sizeof(r->text), "< >");

	a = &areas[nareas++];
	a->name = "Input", a->icon = "hdmi", a->enter = input_enter;
	r = new_row(a, "On start", R_CHOICE);
	r->apply = onstart_apply, r->more = true;		/* the options and their sentences: input_enter, from launcher.d */
	info(a, "On the wall now");

	a = &areas[nareas++];
	a->name = "Power", a->icon = "power", a->enter = power_enter;
	r = new_row(a, "Power key", R_CHOICE);
	r->apply = power_apply, r->more = true;
	r->note = "What a short press of the power key does after its countdown.";
	r = new_row(a, "Remote power key", R_SWITCH);
	r->apply = remote_apply;

	a = &areas[nareas++];
	a->name = "Wi-Fi", a->icon = "wifi", a->enter = wifi_enter;
	info(a, "Mode");
	info(a, "Network");
	info(a, "Signal");
	info(a, "Address");
	areas[AREA_WIFI].row[0].note = "Changing the network needs a keyboard: use the web page of the projector.";
}
