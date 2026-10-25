/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's volume curve on the host: main.c is compiled into this file, and audio_curve_load(), audio_curve_q() and
 * audio_curve_n() are run on made-up audio_config.ini files in a temporary directory (no vendor file is carried here).
 * What is checked: without "volume_curve = vendor" the built-in curve; a file written from the built-in curve gives the
 * same quarter dB for every slider position; a board's own curve is read value for value, with "volume_curve[NN]" as the
 * last index of its line and only inside [Volume]; the way back from the card's dB lands on the nearest position, below
 * position 1 on 0; a file that is short, falls between two positions or leaves -512..120 is refused with a reason.
 *
 *   test_curve     exit 0 when every case passed
 */
#define main h713_tv_main
#include "../main.c"
#undef main

static int failed;
static char dir[64];

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

/* the file with v[0..100], ten values a line as the vendor writes it; extra: a line put before [Volume] */
static void write_ini(const long *v, const char *extra)
{
	char path[96];
	FILE *f;
	int line, i;

	snprintf(path, sizeof(path), "%s/%s", dir, AUDIO_CURVE_FILE);
	f = fopen(path, "w");
	fprintf(f, "[AudioMode]\n%s\nmode = 1\n\n[Volume]\nspeaker_max = 0\n#volume_curve:-512~120\n", extra ? extra : "");
	fprintf(f, "volume_curve[00]=%ld,\n", v[0]);
	for (line = 10; line <= 100; line += 10) {
		fprintf(f, "volume_curve[%d]=", line);
		for (i = line - 9; i <= line; i++)
			fprintf(f, "%ld,", v[i]);
		fprintf(f, "\n");
	}
	fprintf(f, "\n[Peq]\npeq1_freq = 1,10,10,10,10\n");
	fclose(f);
}

int main(void)
{
	long builtin[101], own[101], v[101];
	char why[240];
	int n, bad;

	snprintf(dir, sizeof(dir), "/tmp/h713-tv-curve-XXXXXX");
	if (!mkdtemp(dir))
		return 2;

	vendor_curve_on = false;
	check(audio_curve_q(0) == AUDIO_CURVE_OFF_Q && audio_curve_q(1) == -164 && audio_curve_q(50) == -88 &&
	      audio_curve_q(100) == -38, "built in: 0 off, 1 = -41 dB, 50 = -22 dB, 100 = -9.5 dB");
	for (n = 0; n <= 100; n++)
		builtin[n] = audio_curve_q(n);
	builtin[0] = -512;

	/* the built-in curve written as a file: the same curve */
	write_ini(builtin, NULL);
	check(audio_curve_load(dir, why, sizeof(why)), "a file of the built-in curve is read");
	vendor_curve_on = true;
	for (bad = 0, n = 1; n <= 100; n++)
		bad += audio_curve_q(n) != builtin[n];
	check(bad == 0, "... and gives the built-in quarter dB at every position");
	for (bad = 0, n = 1; n <= 100; n++)
		bad += audio_curve_n(builtin[n]) != n;
	check(bad == 0, "... and every position's quarter dB leads back to it");
	vendor_curve_on = false;

	/* a board's own: steeper below, to +0.5 dB at 100 (made up in the shape of the L018's) */
	own[0] = -512;
	for (n = 1; n <= 100; n++)
		own[n] = n <= 10 ? -209 + 9 * n : n <= 20 ? -147 + 3 * n : n <= 30 ? -128 + 2 * n : n - 98;
	write_ini(own, "volume_curve[50]=-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,");
	check(audio_curve_load(dir, why, sizeof(why)), "a board's own curve is read; the line outside [Volume] counts for nothing");
	vendor_curve_on = true;
	check(audio_curve_q(1) == -200 && audio_curve_q(10) == -119 && audio_curve_q(50) == -48 && audio_curve_q(100) == 2,
	      "its values, value for value (1 = -50 dB, 50 = -12 dB, 100 = +0.5 dB)");
	check(audio_curve_q(0) == AUDIO_CURVE_OFF_Q, "position 0 stays the floor");
	check(audio_curve_n(-300) == 0 && audio_curve_n(-201) == 0, "below position 1: 0");
	check(audio_curve_n(-200) == 1 && audio_curve_n(-196) == 1 && audio_curve_n(-195) == 2,
	      "between two positions: the nearer, the upper one at a tie");
	check(audio_curve_n(0) == 98 && audio_curve_n(400) == 100, "0 dB on the card: the first position there; above all: 100");
	vendor_curve_on = false;

	/* refused, each with a reason */
	memcpy(v, own, sizeof(v));
	v[60] = v[59] - 1;
	write_ini(v, NULL);
	check(!audio_curve_load(dir, why, sizeof(why)) && strstr(why, "value 60"), "a value below the one before is refused");
	memcpy(v, own, sizeof(v));
	v[100] = 121;
	write_ini(v, NULL);
	check(!audio_curve_load(dir, why, sizeof(why)) && strstr(why, "value 100"), "a value above 120 is refused");
	{
		char path[96];
		FILE *f;

		snprintf(path, sizeof(path), "%s/%s", dir, AUDIO_CURVE_FILE);
		f = fopen(path, "w");
		fprintf(f, "[Volume]\nvolume_curve[00]=-512,\nvolume_curve[10]=-200,-191,\n");
		fclose(f);
		check(!audio_curve_load(dir, why, sizeof(why)) && strstr(why, "no [Volume] volume_curve value 1"),
		      "a short file is refused");
		unlink(path);
	}
	check(!audio_curve_load(dir, why, sizeof(why)) && strstr(why, "No such file"), "no file: refused, the curve stays");
	check(!vendor_curve_on && audio_curve_q(100) == -38, "after every refusal the built-in curve");

	rmdir(dir);
	printf("%s\n", failed ? "FAILED" : "all passed");
	return failed ? 1 : 0;
}
