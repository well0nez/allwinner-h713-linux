/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-afmetric -- the vendor's autofocus sharpness metric, in C.
 *
 * h713-autofocus carries this metric in Python; on the projector's A53 one
 * 640x480 frame cost 1.00 s over the full window and 0.11 s over crect, which
 * is the whole cost of a search (dev20-20260922, "Q6 metric on the A53"). This
 * is the same arithmetic in C, and the Python stays the reference: the golden
 * test compares the two integer for integer on the fixture frames.
 *
 * The arithmetic is the vendor's, AP1 2.7 / Q6 report 3.1: per pixel two 3-tap
 * gradients, each halved, cubed and shifted right by two -- SEPARATELY, which
 * is not the same as cubing, adding and shifting once. The "/ 3" is the
 * vendor's (21846 * v) >> 16, which is exactly v / 3 for every sum three bytes
 * can make, so plain division is the arithmetic and not an estimate of it.
 *
 * What it does NOT do is the normalising divisor: that one is fixed by the
 * first measurement of a run and is halved again when the search rescales, so
 * it belongs to the run and stays in h713-autofocus. This prints the raw sum.
 *
 *     h713-afmetric [--window W] [--stride N] [--width W] [--height H]
 *                   [--yuyv] [FILE...]
 *
 * With file names: one sum per file. Without: frames are read from stdin back
 * to back and one sum is printed per frame, until end of file -- that is the
 * mode h713-autofocus uses, one process for a whole run instead of one fork
 * per frame. --yuyv takes the camera's buffer as it comes and reads the even
 * bytes (the luma plane), which saves the caller a copy of the whole buffer;
 * it assumes a line of exactly 2*width bytes, the same assumption the Python
 * path makes when it writes buffer[0::2].
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct window {
	const char *name;
	int y0, y1, x0, x1;
};

/* The four vendor windows, AP1b 9. "nocen" excludes an open rectangle whose
 * own defaults have x0 == x1, so it excludes nothing and is an alias of full. */
static const struct window WINDOWS[] = {
	{ "full",    8, 471,   8, 631 },
	{ "nocen",   8, 471,   8, 631 },
	{ "band",    8, 471, 160, 479 },
	{ "crect", 120, 359, 106, 529 },
};

static unsigned long long strip(const unsigned char *p, int ps, int w,
				int y, int x0, int x1, int s)
{
	long ra = (long)(y - 1) * w, rb = (long)y * w, rc = (long)(y + 1) * w;
	unsigned long long total = 0;
	int x;

	for (x = x0; x <= x1; x += s) {
		int a_i = p[(ra + x) * ps],     a_1 = p[(ra + x + 1) * ps];
		int b_m = p[(rb + x - 1) * ps], b_i = p[(rb + x) * ps];
		int b_1 = p[(rb + x + 1) * ps];
		int c_m = p[(rc + x - 1) * ps], c_i = p[(rc + x) * ps];
		int c_1 = p[(rc + x + 1) * ps];
		int dx = abs(((b_m + b_i) >> 1) - (a_1 + b_1 + c_1) / 3) >> 1;
		int dy = abs(((a_i + b_i) >> 1) - (c_m + c_i + c_1) / 3) >> 1;

		/* dx, dy <= 127, so the cube fits an int; the sum does not. */
		total += (unsigned long long)((dx * dx * dx) >> 2)
		       + (unsigned long long)((dy * dy * dy) >> 2);
	}
	return total;
}

static unsigned long long sharpness_sum(const unsigned char *p, int ps, int w,
					const struct window *win, int s)
{
	unsigned long long total = 0;
	int y;

	for (y = win->y0; y <= win->y1; y += s)
		total += strip(p, ps, w, y, win->x0, win->x1, s);
	return total;
}

static void usage(FILE *out)
{
	fputs("h713-afmetric [--window full|nocen|band|crect] [--stride N]\n"
	      "              [--width W] [--height H] [--yuyv] [FILE...]\n"
	      "one raw metric sum per frame; without FILE, frames from stdin\n",
	      out);
}

int main(int argc, char **argv)
{
	const char *wname = "crect";
	const struct window *win = NULL;
	int stride = 3, w = 640, h = 480, ps = 1, files = 0, i;
	unsigned char *buf;
	size_t bytes;

	for (i = 1; i < argc; i++) {
		const char *a = argv[i];

		if (!strcmp(a, "--window") && i + 1 < argc)
			wname = argv[++i];
		else if (!strcmp(a, "--stride") && i + 1 < argc)
			stride = atoi(argv[++i]);
		else if (!strcmp(a, "--width") && i + 1 < argc)
			w = atoi(argv[++i]);
		else if (!strcmp(a, "--height") && i + 1 < argc)
			h = atoi(argv[++i]);
		else if (!strcmp(a, "--yuyv"))
			ps = 2;
		else if (!strcmp(a, "--help")) {
			usage(stdout);
			return 0;
		} else if (a[0] == '-' && a[1]) {
			fprintf(stderr, "h713-afmetric: unknown option %s\n", a);
			usage(stderr);
			return 2;
		} else {
			argv[files++] = (char *)a;   /* files <= i: in place */
		}
	}

	for (i = 0; i < (int)(sizeof(WINDOWS) / sizeof(WINDOWS[0])); i++)
		if (!strcmp(wname, WINDOWS[i].name))
			win = &WINDOWS[i];
	if (!win) {
		fprintf(stderr, "h713-afmetric: no window '%s'\n", wname);
		return 2;
	}
	if (stride < 1 || w < 3 || h < 3) {
		fprintf(stderr, "h713-afmetric: stride >= 1 and a frame of at "
				"least 3x3, not %d and %dx%d\n", stride, w, h);
		return 2;
	}
	if (win->y1 + 1 >= h || win->x1 + 1 >= w) {
		fprintf(stderr, "h713-afmetric: window %s reads up to row %d "
				"and column %d, past a %dx%d frame\n",
			win->name, win->y1 + 1, win->x1 + 1, w, h);
		return 2;
	}

	bytes = (size_t)w * (size_t)h * (size_t)ps;
	buf = malloc(bytes);
	if (!buf) {
		fprintf(stderr, "h713-afmetric: no memory for %dx%d\n", w, h);
		return 2;
	}

	for (i = 0; i < files || (!files && !feof(stdin)); i++) {
		FILE *in = stdin;
		size_t got;

		if (files) {
			in = fopen(argv[i], "rb");
			if (!in) {
				perror(argv[i]);
				free(buf);
				return 2;
			}
		}
		got = fread(buf, 1, bytes, in);
		if (files)
			fclose(in);
		if (!got && !files)
			break;                      /* clean end of stream */
		if (got < bytes) {
			fprintf(stderr, "h713-afmetric: %s holds %lu bytes, a "
					"%dx%d frame has %lu\n",
				files ? argv[i] : "stdin",
				(unsigned long)got, w, h,
				(unsigned long)bytes);
			free(buf);
			return 2;
		}
		printf("%llu\n", sharpness_sum(buf, ps, w, win, stride));
		fflush(stdout);
	}
	free(buf);
	return 0;
}
