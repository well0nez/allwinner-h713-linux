// SPDX-License-Identifier: GPL-2.0
/*
 * The host's sink, compiled in only with -DH713_TEST (never into the board's binary): keys as lines on stdin (up down left
 * right ok back home power volup voldown mute focusup focusdown), and the commands of the tests - "dump" (the model as text,
 * ending with "--"), "snap FILE" (the canvas as PAM), "sleep MS". A command is an event of its own, so that it runs after
 * the keys before it have been carried out.
 */
#define _GNU_SOURCE
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "ui.h"

extern long test_outside;			/* main.c: pixels changed outside the reported pieces */


extern struct view v;
extern struct osd_canvas canvas;
extern volatile sig_atomic_t quit;
void snap(const char *path);

static char ibuf[4096], cmdline[256];
static size_t ilen;

static void dump(void)
{
	static const char *const kind[] = { "slider", "switch", "choice", "action", "info", "corners", "stepper" };
	static const char *const focus[] = { "areas", "rows", "choice", "corners", "slider" };
	struct area *a = &areas[v.area];

	printf("area %s focus %s row %d choice %d corner %d\n", a->name, focus[v.f], v.row, v.choice, v.corner);
	for (int i = 0; i < a->n; i++) {
		struct row *r = &a->row[i];

		printf("  %s%s %s", r->hidden ? "(hidden) " : "", r->label, kind[r->kind]);
		if (r->kind == R_SLIDER || r->kind == R_SWITCH)
			printf(" %d", r->val);
		if (r->kind == R_SLIDER)
			printf(" %d..%d", r->min, r->max);
		if (r->kind == R_CHOICE || (r->kind == R_SLIDER && r->n)) {		/* a slider with named stops lists them like a choice */
			printf(" [");
			for (int k = 0; k < r->n; k++)
				printf("%s%s%s", k ? "|" : "", k == r->val ? "*" : "", r->opt[k]);
			printf("]");
			if (r->opt_note[v.f == F_CHOICE && visible_row(a, v.row) == r ? v.choice : r->val])	/* the sentence the wall shows for it */
				printf(" note \"%s\"", r->opt_note[v.f == F_CHOICE && visible_row(a, v.row) == r ? v.choice : r->val]);
		}
		if (r->text[0])
			printf(" \"%s\"", r->text);
		printf("\n");
	}
	if (v.f != F_AREAS && visible_rows(a)) {		/* the sentence the wall shows under the rows */
		const char *n = ui_note(&v, visible_row(a, v.row));

		if (n)
			printf("sentence \"%s\"\n", n);
	}
	printf("outside %ld\n", test_outside);
	printf("--\n");
	fflush(stdout);
}

int test_key(int ms)
{
	static const struct { const char *name; int key; } names[] = {
		{ "up", KE_UP }, { "down", KE_DOWN }, { "left", KE_LEFT }, { "right", KE_RIGHT }, { "ok", KE_OK }, { "back", KE_BACK },
		{ "home", KE_HOME }, { "power", KE_POWER }, { "volup", KE_VOL_UP }, { "voldown", KE_VOL_DOWN }, { "mute", KE_MUTE },
		{ "focusup", KE_FOCUS_UP }, { "focusdown", KE_FOCUS_DOWN },
	};

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
		for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++)
			if (!strcmp(word, names[i].name))
				return names[i].key;
		snprintf(cmdline, sizeof(cmdline), "%s", word);
		return KE_CMD;
	}
}

void test_command(void)
{
	if (!strcmp(cmdline, "dump"))
		dump();
	else if (!strncmp(cmdline, "snap ", 5))
		snap(cmdline + 5);
	else if (!strncmp(cmdline, "sleep ", 6))
		usleep((useconds_t)atoi(cmdline + 6) * 1000);
}
