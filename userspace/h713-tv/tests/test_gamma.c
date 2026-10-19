/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's gamma curve and colour temperature, on the host: main.c and gamma.c are compiled into this file, and the
 * place that puts a curve on the CRTC is replaced by a function that keeps what it was given.
 *
 * What is checked:
 *   - the arithmetic against an independent description of the display firmware's library (written in Python): for a
 *     board with invented raw curves, 15 curves in the form the library is in after every start, the same 15 by the
 *     power law, and 5 curves with the factory menu's points - as checksums of the 6144 bytes (tests/gamma-vectors.txt);
 *   - the root solver and the Bezier form on their own, and the properties that do not depend on any description
 *     (the end points, the range, the refusals);
 *   - the file of raw curves h713-pq writes: a good one, and each way it can be wrong;
 *   - the control: what "set gamma" and "set colour_temperature" put on the CRTC, "auto" following the picture mode,
 *     a board with fewer curves, a refusal by the CRTC, nothing sent twice, the text of list and status;
 *   - main.c's side: the picture mode's colour temperature out of the data (and out of the compiled table), the entries
 *     of GAMMA_LUT, the file "werte".
 *
 *   test_gamma      exit 0 when every case passed
 */
#define main h713_tv_main
#include "../main.c"
#undef main
#include "../gamma.c"

static int failed;

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

/* ---- SHA-256, for the checksums of the vectors ---- */

struct sha {
	uint32_t h[8];
	uint8_t buf[64];
	uint64_t len;
	unsigned int n;
};

static const uint32_t sha_k[64] = {
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha_block(struct sha *s, const uint8_t *p)
{
	uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2;
	int i;

	for (i = 0; i < 16; i++)
		w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
	for (i = 16; i < 64; i++) {
		uint32_t s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
		uint32_t s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);

		w[i] = w[i - 16] + s0 + w[i - 7] + s1;
	}
	a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3]; e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
	for (i = 0; i < 64; i++) {
		t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + sha_k[i] + w[i];
		t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
		h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
	}
	s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d; s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}

static void sha_init(struct sha *s)
{
	static const uint32_t iv[8] = { 0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19 };

	memcpy(s->h, iv, sizeof(iv));
	s->len = 0;
	s->n = 0;
}

static void sha_add(struct sha *s, const uint8_t *p, size_t n)
{
	s->len += n;
	while (n--) {
		s->buf[s->n++] = *p++;
		if (s->n == 64) {
			sha_block(s, s->buf);
			s->n = 0;
		}
	}
}

static void sha_hex(struct sha *s, char out[65])
{
	uint64_t bits = s->len * 8;
	uint8_t pad = 0x80, zero = 0, lenb[8];
	int i;

	sha_add(s, &pad, 1);
	while (s->n != 56)
		sha_add(s, &zero, 1);
	for (i = 0; i < 8; i++)
		lenb[i] = (uint8_t)(bits >> (56 - 8 * i));
	sha_add(s, lenb, 8);
	for (i = 0; i < 8; i++)
		snprintf(out + 8 * i, 9, "%08x", s->h[i]);
}

static void sha_of(const void *p, size_t n, char out[65])
{
	struct sha s;

	sha_init(&s);
	sha_add(&s, p, n);
	sha_hex(&s, out);
}

/* ---- the invented board: the raw curves of three colour temperatures ---- */

static struct gamma_base synth;

static uint16_t synth_bank(int i, double e, double end)
{
	return (uint16_t)rint(pow(i / 1023.0, e) * end);
}

static void make_synth(void)
{
	static const double e[3][3] = { { 1.0, 1.05, 0.97 }, { 1.04, 1.0, 0.95 }, { 0.96, 1.02, 1.12 } };
	static const double end[3][3] = { { 4092, 4092, 4092 }, { 4000, 4092, 4092 }, { 4092, 3900, 3600 } };
	int s, c, i;

	memset(&synth, 0, sizeof(synth));
	for (s = 0; s < 3; s++)
		for (c = 0; c < 3; c++)
			for (i = 0; i < GAMMA_N; i++)
				synth.slot[s][c][i] = synth_bank(i, e[s][c], end[s][c]);
	synth.mask = 7;
	synth.project = 0x30;
}

static void raw_bytes(const gamma_curve c, uint8_t *out)
{
	int k, i;

	for (k = 0; k < 3; k++)
		for (i = 0; i < GAMMA_N; i++) {
			*out++ = (uint8_t)c[k][i];
			*out++ = (uint8_t)(c[k][i] >> 8);
		}
}

static void curve_sha(const gamma_curve lut, char out[65])
{
	uint8_t bytes[GAMMA_BYTES];

	gamma_pack(lut, bytes);
	sha_of(bytes, sizeof(bytes), out);
}

static const char *const state_names[3] = { "normal", "cool", "warm" };

/* ---- the vectors ---- */

static char vec_stock[3][5][65], vec_pow[3][5][65], vec_table[3][65];
static char vec_points_sha[8][65];
static char vec_points_name[8][40];
static int vec_points[8][GAMMA_POINTS];
static int vec_points_n, vec_n;

/* the solver, root by root (bit patterns), and the Bezier form over made-up knot values */
#define VEC_SOLVE_MAX	128
#define VEC_KNOT_MAX	64
static double vec_solve[VEC_SOLVE_MAX][7];
static unsigned int vec_solve_n;
static char vec_knot_sha[VEC_KNOT_MAX][65];
static unsigned int vec_knot_y[VEC_KNOT_MAX][12];
static unsigned int vec_knot_n;

static int state_index(const char *name)
{
	int i;

	for (i = 0; i < 3; i++)
		if (!strcmp(name, state_names[i]))
			return i;

	return -1;
}

static bool vectors_load(const char *path)
{
	char line[1024], name[40], sha[80];
	int level;
	FILE *f = fopen(path, "r");

	if (!f)
		return false;
	while (fgets(line, sizeof(line), f)) {
		int s;

		if (line[0] == '#' || line[0] == '\n')
			continue;
		if (sscanf(line, "table %39s %79s", name, sha) == 2 && (s = state_index(name)) >= 0) {
			snprintf(vec_table[s], 65, "%s", sha);
			vec_n++;
		} else if (sscanf(line, "stock %39s %d %79s", name, &level, sha) == 3 && (s = state_index(name)) >= 0 && level >= 0 && level < 5) {
			snprintf(vec_stock[s][level], 65, "%s", sha);
			vec_n++;
		} else if (sscanf(line, "pow %39s %d %79s", name, &level, sha) == 3 && (s = state_index(name)) >= 0 && level >= 0 && level < 5) {
			snprintf(vec_pow[s][level], 65, "%s", sha);
			vec_n++;
		} else if (!strncmp(line, "solve ", 6) && vec_solve_n < VEC_SOLVE_MAX) {
			char *p = line + 6;
			int k;

			for (k = 0; k < 7; k++)
				vec_solve[vec_solve_n][k] = strtod(p, &p);
			vec_solve_n++;
			vec_n++;
		} else if (!strncmp(line, "bezier ", 7) && vec_knot_n < VEC_KNOT_MAX) {
			char *p = line + 7;
			int k;

			if (sscanf(p, "%64s", vec_knot_sha[vec_knot_n]) != 1)
				continue;
			p += 65;
			for (k = 0; k < 12; k++)
				vec_knot_y[vec_knot_n][k] = (unsigned int)strtoul(p, &p, 10);
			vec_knot_n++;
			vec_n++;
		} else if (!strncmp(line, "points ", 7) && vec_points_n < 8) {
			char *p = line + 7;
			int k, n = vec_points_n;

			if (sscanf(p, "%39s %79s", vec_points_name[n], vec_points_sha[n]) != 2)
				continue;
			p += strlen(vec_points_name[n]) + 1 + strlen(vec_points_sha[n]);
			for (k = 0; k < GAMMA_POINTS; k++)
				vec_points[n][k] = (int)strtol(p, &p, 10);
			vec_points_n++;
			vec_n++;
		}
	}
	fclose(f);

	return true;
}

/* ---- a fake CRTC ---- */

static gamma_curve fake_lut;
static unsigned int fake_calls;
static bool fake_fail;

static bool fake_apply(const gamma_curve lut, char *why, size_t n)
{
	fake_calls++;
	if (fake_fail) {
		snprintf(why, n, "the commit was refused: Device or resource busy");
		return false;
	}
	memcpy(fake_lut, lut, sizeof(fake_lut));

	return true;
}

static const struct gamma_io fake_io = { .apply = fake_apply };

static void reply_clear(struct reply *r)
{
	memset(r, 0, sizeof(*r));
}

static void write_base_file(const char *path, uint32_t mask, uint32_t version, const struct gamma_base *b, long cut)
{
	FILE *f = fopen(path, "wb");
	uint8_t head[16] = "H7GS", raw[GAMMA_BYTES];
	int s;

	head[4] = (uint8_t)version;
	head[8] = (uint8_t)mask;
	head[9] = (uint8_t)(mask >> 8);
	head[12] = (uint8_t)b->project;
	fwrite(head, 1, sizeof(head), f);
	for (s = 0; s < GAMMA_SLOTS; s++)
		if (mask >> s & 1u) {
			raw_bytes(b->slot[s], raw);
			fwrite(raw, 1, sizeof(raw), f);
		}
	if (cut > 0) {
		fflush(f);
		if (ftruncate(fileno(f), cut))
			perror("ftruncate");
	}
	fclose(f);
}

static void expect_curve(const char *vec, const char *what)
{
	char sha[65];

	curve_sha(fake_lut, sha);
	check(!strcmp(sha, vec), what);
}

int main(void)
{
	static struct gamma_base other;
	char sha[65], why[240], path[] = "/tmp/h713-tv-test-gamma-XXXXXX";
	struct reply r;
	gamma_curve lut, lut2;
	int s, l, k, fd;
	bool ok;

	/* ---- the checksum itself, and the arithmetic ---- */
	sha_of("abc", 3, sha);
	check(!strcmp(sha, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "sha256 of \"abc\"");
	sha_of("", 0, sha);
	check(!strcmp(sha, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"), "sha256 of nothing");
	check(gamma_arith_ok(), "no multiplication is rounded together with an addition in this build");

	/* ---- the vectors ---- */
	check(vectors_load("gamma-vectors.txt") || vectors_load("tests/gamma-vectors.txt"), "the file of vectors is there");
	check(vec_n == 3 + 15 + 15 + 5 + 75 + 18 && vec_solve_n == 75 && vec_knot_n == 18,
	      "and holds 3 tables, 15 + 15 curves, 5 with points, 75 cases of the solver and 18 of the Bezier form over made-up knots");
	make_synth();
	for (s = 0; s < 3; s++) {
		uint8_t raw[GAMMA_BYTES];

		raw_bytes(synth.slot[s], raw);
		sha_of(raw, sizeof(raw), sha);
		check(!strcmp(sha, vec_table[s]), "the invented raw curve is the one the vectors were made for");
	}
	for (s = 0; s < 3; s++)
		for (l = 0; l < 5; l++) {
			char what[100];

			ok = gamma_compute(synth.slot[s], (unsigned int)l, NULL, lut);
			curve_sha(lut, sha);
			snprintf(what, sizeof(what), "%s, level %d, the form after every start: all 6144 bytes", state_names[s], l);
			check(ok && !strcmp(sha, vec_stock[s][l]), what);
			ok = gamma_compute_pow(synth.slot[s], (unsigned int)l, lut);
			curve_sha(lut, sha);
			snprintf(what, sizeof(what), "%s, level %d, by the power law over 1024 samples: all 6144 bytes", state_names[s], l);
			check(ok && !strcmp(sha, vec_pow[s][l]), what);
		}
	check(vec_points_n == 5, "five cases with points");
	for (k = 0; k < vec_points_n; k++) {
		char what[100];

		ok = gamma_compute(synth.slot[0], 3, vec_points[k], lut);
		curve_sha(lut, sha);
		snprintf(what, sizeof(what), "points %s: all 6144 bytes", vec_points_name[k]);
		check(ok && !strcmp(sha, vec_points_sha[k]), what);
	}
	{
		int zero[GAMMA_POINTS] = { 0 };

		gamma_compute(synth.slot[1], 2, NULL, lut);
		gamma_compute(synth.slot[1], 2, zero, lut2);
		check(!memcmp(lut, lut2, sizeof(lut)), "no points is the same as 33 zeros");
	}

	/* the solver: every root of every case, bit for bit (a root of -1 is "none here") */
	{
		unsigned int i, same = 0;
		unsigned int knot_same = 0;
		int xs[12];

		for (i = 0; i < 12; i++)
			xs[i] = knot_x[i];
		for (i = 0; i < vec_solve_n; i++) {
			double root[3];

			solve3(vec_solve[i][0], vec_solve[i][1], vec_solve[i][2], vec_solve[i][3], root);
			if (!memcmp(root, &vec_solve[i][4], sizeof(root)))
				same++;
			else
				printf("      solver case %u: got %a %a %a, expected %a %a %a\n", i, root[0], root[1], root[2],
				       vec_solve[i][4], vec_solve[i][5], vec_solve[i][6]);
		}
		check(same == vec_solve_n && same > 0, "the solver gives the very same roots in all its branches (no constant term, a line, a quadratic, a cubic with and without extremes)");
		for (i = 0; i < vec_knot_n; i++) {
			double curve[GAMMA_N];
			uint8_t raw[2 * GAMMA_N];
			unsigned int j;

			bezier_fit(xs, vec_knot_y[i], 12, curve);
			for (j = 0; j < GAMMA_N; j++) {
				uint16_t v = to_u16(curve[j]);

				raw[2 * j] = (uint8_t)v;
				raw[2 * j + 1] = (uint8_t)(v >> 8);
			}
			sha_of(raw, sizeof(raw), sha);
			if (!strcmp(sha, vec_knot_sha[i]))
				knot_same++;
			else
				printf("      Bezier case %u differs\n", i);
		}
		check(knot_same == vec_knot_n && knot_same > 0,
		      "the Bezier form over made-up knots: steps, equal neighbours, tangents too long, the straight line, a second root - all 1024 samples");
	}
	check(fma(1.0 + 0x1p-30, 1.0 + 0x1p-30, -(1.0 + 0x1p-29)) != 0.0, "the numbers of the arithmetic check do tell a fused multiply-add from two roundings");

	/* ---- what does not depend on any description ---- */
	gamma_compute(synth.slot[2], 3, NULL, lut);
	check(lut[0][1023] >= synth.slot[2][0][1023] - 1 && lut[1][1023] >= synth.slot[2][1][1023] - 1 &&
	      lut[2][1023] >= synth.slot[2][2][1023] - 1 && lut[2][1023] <= synth.slot[2][2][1023],
	      "the end point of each channel stays (at most one lower: the Bezier form loses a count at the knots)");
	check(lut[0][0] == 0 && lut[1][0] == 0 && lut[2][0] == 0, "the first sample is 0");
	for (l = 0; l < 5; l++) {
		gamma_compute_pow(synth.slot[2], (unsigned int)l, lut);
		check(lut[0][1023] == synth.slot[2][0][1023] && lut[1][1023] == synth.slot[2][1][1023] &&
		      lut[2][1023] == synth.slot[2][2][1023], "the power law keeps the end points of a board with different ones, every level");
	}
	gamma_compute_pow(synth.slot[0], 0, lut);
	gamma_compute_pow(synth.slot[0], 4, lut2);
	check(lut[0][512] > synth.slot[0][0][512] && lut2[0][512] < synth.slot[0][0][512], "level 0 lifts the middle, level 4 lowers it");
	check(!gamma_compute(synth.slot[0], 5, NULL, lut) && !gamma_compute(synth.slot[0], 255, NULL, lut) &&
	      !gamma_compute_pow(synth.slot[0], 5, lut), "a level above 4 is refused (the library would black the picture)");
	memcpy(other.slot[0], synth.slot[0], sizeof(other.slot[0]));
	other.slot[0][1][1023] = 0;
	check(!gamma_compute(other.slot[0], 3, NULL, lut) && !gamma_compute_pow(other.slot[0], 3, lut),
	      "a channel that ends in 0 is refused (the samples are divided by it)");
	{
		int pts[GAMMA_POINTS] = { 0 }, big[GAMMA_POINTS] = { 0 };

		pts[3 * 4 + 1] = 50;
		gamma_compute(synth.slot[0], 3, NULL, lut);
		gamma_compute(synth.slot[0], 3, pts, lut2);
		check(lut2[1][409] > lut[1][409] && lut2[0][409] == lut[0][409] && lut2[2][409] == lut[2][409],
		      "a point moves its own channel at its own knot and nothing else there");
		big[0] = 30000;
		big[1] = -32768;
		check(gamma_compute(synth.slot[0], 3, big, lut2), "points beyond 16 bit are folded as the library does and do not crash");
	}

	/* ---- the solver and the Bezier form on their own ---- */
	{
		double root[3];
		int xs[12] = { 0, 51, 102, 204, 306, 409, 511, 613, 716, 818, 920, 1023 };
		unsigned int ys[12];
		double out[GAMMA_N];
		int i, worst = 0;

		solve3(1.0, -6.0, 11.0, -6.0, root);
		{
			double a = root[0], b = root[1], c = root[2], t;

			if (a > b) { t = a; a = b; b = t; }
			if (b > c) { t = b; b = c; c = t; }
			if (a > b) { t = a; a = b; b = t; }
			check(fabs(a - 1.0) < 1e-4 && fabs(b - 2.0) < 1e-4 && fabs(c - 3.0) < 1e-4, "solver: (t-1)(t-2)(t-3)");
		}
		solve3(1.0, 0.0, 1.0, -2.0, root);
		check(fabs(root[0] - 1.0) < 1e-4 && root[1] == -1.0 && root[2] == -1.0, "solver: a monotone cubic has the one root");
		solve3(2.0, 0.0, 0.0, 0.0, root);
		check(root[0] == 0.0, "solver: no constant term, t = 0 is a root");
		solve3(0.0, 1.0, 0.0, -4.0, root);
		check(root[0] == -2.0 && root[1] == 2.0, "solver: a quadratic, the roots in order");
		solve3(0.0, 0.0, 2.0, -3.0, root);
		check(root[0] == 1.5 && root[1] == 1.5 && root[2] == -1.0, "solver: a line");
		solve3(1.0, 0.0, 1.0, 1.0, root);
		check(root[0] < 0.0 && root[1] == -1.0, "solver: the one root of a monotone cubic can be negative");
		for (i = 0; i < 12; i++)
			ys[i] = (unsigned int)xs[i] * 4;
		bezier_fit(xs, ys, 12, out);
		for (i = 0; i < GAMMA_N; i++) {
			int d = abs((int)to_u16(out[i]) - 4 * i);

			if (d > worst)
				worst = d;
		}
		check(worst <= 1, "a straight line through the knots stays a straight line (within the one count lost to the cut)");
		check(to_u16(-1.0) == 0 && to_u16(0.9) == 0 && to_u16(4095.9) == 4095 && to_u16(1e12) == 0xffff && to_u16(NAN) == 0,
		      "the cut toward zero, and what is not a number is 0");
		check(sxth(0x7fff) == 32767 && sxth(0x8000) == -32768 && sxth(-1) == -1 && sxth(0x10005) == 5, "sxth");
		check(clamp_knot(4000, 100) == 4095 && clamp_knot(10, -50) == 0 && clamp_knot(100, 20) == 120 &&
		      clamp_knot(20000, 20000) == 0, "a knot plus its offset: 4095 at most, 0 at least, an overflow of 16 bit is 0");
	}

	/* ---- the file of raw curves ---- */
	fd = mkstemp(path);
	close(fd);
	write_base_file(path, 7, 1, &synth, 0);
	ok = gamma_base_read(&other, path, why, sizeof(why)) == 3;
	check(ok && other.mask == 7 && other.project == 0x30 && !memcmp(other.slot[1], synth.slot[1], sizeof(other.slot[1])) &&
	      !memcmp(other.slot[2], synth.slot[2], sizeof(other.slot[2])), "a good file: three states, the board, the samples");
	write_base_file(path, 1, 1, &synth, 0);
	check(gamma_base_read(&other, path, why, sizeof(why)) == 1 && other.mask == 1, "a file with the normal state only");
	memcpy(&other, &synth, sizeof(other));
	memcpy(other.slot[8], synth.slot[0], sizeof(other.slot[8]));
	write_base_file(path, 0x104, 1, &other, 0);
	check(gamma_base_read(&other, path, why, sizeof(why)) == 2 && other.mask == 0x104 &&
	      !memcmp(other.slot[8], synth.slot[0], sizeof(other.slot[8])), "states are named by their number, the ninth too");
	write_base_file(path, 7, 2, &synth, 0);
	check(!gamma_base_read(&other, path, why, sizeof(why)) && strstr(why, "version 2"), "another version is refused, and named");
	write_base_file(path, 0, 1, &synth, 0);
	check(!gamma_base_read(&other, path, why, sizeof(why)) && other.mask == 0, "an empty list of states is refused");
	write_base_file(path, 0x200, 1, &synth, 0);
	check(!gamma_base_read(&other, path, why, sizeof(why)), "a tenth state is refused");
	write_base_file(path, 7, 1, &synth, 16 + 2 * 6144 + 100);
	check(!gamma_base_read(&other, path, why, sizeof(why)) && strstr(why, "3 states long"), "a file that is too short is refused");
	write_base_file(path, 7, 1, &synth, 10);
	check(!gamma_base_read(&other, path, why, sizeof(why)), "a file shorter than its head is refused");
	{
		FILE *f = fopen(path, "wb");

		fwrite("XXXX000000000000", 1, 16, f);
		fclose(f);
	}
	check(!gamma_base_read(&other, path, why, sizeof(why)) && strstr(why, "not a file of the board's curves"), "another file is not taken for it");
	check(!gamma_base_read(&other, "/tmp/h713-tv-test-gamma-none", why, sizeof(why)) && strstr(why, "No such file"), "no file: the reason is the system's");
	memcpy(&other, &synth, sizeof(other));
	other.slot[1][2][700] = 4096;
	other.slot[2][0][1023] = 0;
	write_base_file(path, 7, 1, &other, 0);
	ok = gamma_base_read(&other, path, why, sizeof(why)) == 1;
	check(ok && other.mask == 1 && strstr(why, "state 2 ends in 0"), "a state with a sample above 4095 or an end point of 0 is left out, the rest stays");
	check(!other.slot[1][2][700] && !other.slot[2][0][1023], "and what was left out is not kept");

	/* ---- the control ---- */
	write_base_file(path, 7, 1, &synth, 0);
	gamma_init();
	fake_calls = 0;
	fake_fail = false;
	check(!gamma_start() && !gamma_active(), "before anything is attached there is nothing to start");
	reply_clear(&r);
	gamma_set(&r, 0, "2");
	check(r.failed && strstr(r.buf, "gamma is not available"), "a control that is not attached says so");
	reply_clear(&r);
	gamma_list(&r);
	check(r.len == 0, "and is not listed");
	check(gamma_attach(path, &fake_io, why, sizeof(why)) && gamma_active(), "attached to a board with three curves");
	check(fake_calls == 0, "attaching puts nothing on the CRTC");
	gamma_mode_temp(2, "the start");
	check(fake_calls == 0, "the picture mode's wish before the start puts nothing on the CRTC either");
	gamma_mode_temp(0, "the start");
	check(gamma_start() && fake_calls == 1, "the start puts the first curve on the CRTC");
	expect_curve(vec_stock[0][3], "the first curve is normal, level 3, in the form after every start");
	gamma_init();
	gamma_attach(path, &fake_io, why, sizeof(why));
	fake_calls = 0;
	gamma_mode_temp(2, "the start");
	check(gamma_start() && fake_calls == 1, "a start with a picture mode that wants warm");
	expect_curve(vec_stock[2][3], "... puts the warm curve first, with no normal curve before it");
	gamma_init();
	gamma_attach(path, &fake_io, why, sizeof(why));
	fake_calls = 0;
	gamma_start();
	reply_clear(&r);
	gamma_get(&r, 0);
	check(!strcmp(r.buf, "ok gamma = 3 (2.2)\n"), "get gamma");
	reply_clear(&r);
	gamma_get(&r, 1);
	check(!strcmp(r.buf, "ok colour_temperature = auto (normal)\n"), "get colour_temperature: auto, and what it comes to");
	reply_clear(&r);
	gamma_list(&r);
	check(strstr(r.buf, "  gamma                      3 (2.2)  menu 0..4\n") &&
	      strstr(r.buf, "  colour_temperature         auto (normal)  menu auto|normal|cool|warm\n"), "list shows both");
	reply_clear(&r);
	gamma_status(&r);
	check(strstr(r.buf, "level 3 (2.2), colour temperature auto (normal); curves of ProjectID 0x30: normal cool warm") &&
	      strstr(r.buf, "on the CRTC: normal, level 3, curve ") && strstr(r.buf, "1 sent, 0 refused"), "status shows the state and what is on the CRTC");

	reply_clear(&r);
	gamma_set(&r, 0, "0");
	check(!r.failed && !strcmp(r.buf, "ok gamma = 0 (1.8)\n") && fake_calls == 2, "set gamma 0");
	expect_curve(vec_stock[0][0], "the curve is normal, level 0");
	reply_clear(&r);
	gamma_set(&r, 0, "0");
	check(!r.failed && fake_calls == 2, "the same level again sends nothing");
	for (l = 0; l < 5; l++) {
		static const char *const exp[5] = { "1.8", "2.0", "2.1", "2.2", "2.4" };
		char num[8];

		reply_clear(&r);
		gamma_set(&r, 0, exp[l]);
		snprintf(num, sizeof(num), "%d", l);
		check(!r.failed, "the exponent as text is a level");
		expect_curve(vec_stock[0][l], "... and the curve is that level's");
		reply_clear(&r);
		gamma_set(&r, 0, num);
		check(!r.failed && fake_calls >= 2, "the number is a level");
	}
	fake_calls = 0;
	for (k = 0; k < 7; k++) {
		static const char *const bad[7] = { "5", "-1", "2.00", "2.3", "abc", "", "0x2" };

		reply_clear(&r);
		gamma_set(&r, 0, bad[k]);
		check(r.failed && strstr(r.buf, "possible: 0..4 or 1.8 2.0 2.1 2.2 2.4"), "a value gamma does not know is refused");
	}
	check(fake_calls == 0, "and nothing is sent for them");
	reply_clear(&r);
	gamma_get(&r, 0);
	check(!strcmp(r.buf, "ok gamma = 4 (2.4)\n"), "the refusals leave the level where it was");

	reply_clear(&r);
	gamma_set(&r, 0, "3");
	gamma_set(&r, 1, "cool");
	check(!r.failed && strstr(r.buf, "ok colour_temperature = cool\n"), "set colour_temperature cool");
	expect_curve(vec_stock[1][3], "the curve is cool, level 3");
	reply_clear(&r);
	gamma_set(&r, 1, "WARM");
	expect_curve(vec_stock[2][3], "warm, in any case");
	reply_clear(&r);
	gamma_set(&r, 1, "standard");
	check(strstr(r.buf, "ok colour_temperature = normal\n"), "standard is normal");
	expect_curve(vec_stock[0][3], "back to normal");
	reply_clear(&r);
	gamma_set(&r, 1, "3");
	expect_curve(vec_stock[2][3], "3 is the fourth of auto normal cool warm");
	fake_calls = 0;
	reply_clear(&r);
	gamma_set(&r, 1, "lukewarm");
	check(r.failed && strstr(r.buf, "possible: auto normal cool warm") && fake_calls == 0, "a colour temperature it does not know is refused");

	/* auto follows the picture mode */
	reply_clear(&r);
	gamma_set(&r, 1, "auto");
	expect_curve(vec_stock[0][3], "auto comes to normal while the picture mode wants normal");
	fake_calls = 0;
	gamma_mode_temp(2, "a picture mode");
	expect_curve(vec_stock[2][3], "the picture mode wants warm: the warm curve");
	check(fake_calls == 1, "... once");
	gamma_mode_temp(2, "a picture mode");
	check(fake_calls == 1, "the same mode again sends nothing");
	reply_clear(&r);
	gamma_get(&r, 1);
	check(!strcmp(r.buf, "ok colour_temperature = auto (warm)\n"), "get says what auto comes to");
	gamma_mode_temp(1, "a picture mode");
	expect_curve(vec_stock[1][3], "vivid: cool");
	gamma_mode_temp(0, "a picture mode");
	expect_curve(vec_stock[0][3], "standard: normal");
	reply_clear(&r);
	gamma_set(&r, 1, "cool");
	fake_calls = 0;
	gamma_mode_temp(2, "a picture mode");
	check(fake_calls == 0, "a colour temperature that was asked for does not follow the picture mode");
	expect_curve(vec_stock[1][3], "... the cool curve stays");
	reply_clear(&r);
	gamma_set(&r, 1, "auto");
	expect_curve(vec_stock[2][3], "and auto takes the picture mode's wish up again (warm was the last)");
	gamma_mode_temp(9, "x");
	gamma_mode_temp(-1, "x");
	expect_curve(vec_stock[2][3], "a mode number outside the nine states changes nothing");

	/* a refusal by the CRTC */
	fake_fail = true;
	fake_calls = 0;
	reply_clear(&r);
	gamma_set(&r, 0, "1");
	check(r.failed && strstr(r.buf, "gamma = 1: the commit was refused") && fake_calls == 1, "the CRTC refuses: the control says so");
	reply_clear(&r);
	gamma_get(&r, 0);
	check(!strcmp(r.buf, "ok gamma = 3 (2.2)\n"), "and the level is what it was");
	expect_curve(vec_stock[2][3], "and so is the curve on the CRTC");
	gamma_mode_temp(0, "a picture mode");
	reply_clear(&r);
	gamma_status(&r);
	check(strstr(r.buf, "2 refused"), "status counts the refusals");
	fake_fail = false;
	gamma_mode_temp(0, "a picture mode");
	expect_curve(vec_stock[0][3], "later it goes again");

	/* the kept values */
	{
		bool have[2] = { true, true };
		int val[2] = { 1, GAMMA_T_WARM };
		FILE *f;
		char msg[200] = "";
		struct saved_values sv;
		int idx = -1, out = -1;

		gamma_init();
		gamma_adopt(have, val);
		gamma_attach(path, &fake_io, why, sizeof(why));
		fake_calls = 0;
		check(gamma_start(), "a start with kept values");
		expect_curve(vec_stock[2][1], "the first curve is the kept warm, level 1");
		f = fopen(path, "w");
		gamma_kept_lines(f, msg, sizeof(msg), 0);
		fclose(f);
		check(!strcmp(msg, " gamma=1 colour_temperature=warm"), "save names both in its answer");
		memset(&sv, 0, sizeof(sv));
		sv.path = path;
		saved_read(&sv);
		check(sv.gm_have[0] && sv.gm[0] == 1 && sv.gm_have[1] && sv.gm[1] == GAMMA_T_WARM, "read back: both");
		check(gamma_parse_kept("gamma", "4", &idx, &out) == 1 && idx == 0 && out == 4, "parse: gamma");
		check(gamma_parse_kept("gamma", "2.1", &idx, &out) == 1 && out == 2, "parse: gamma as the exponent");
		check(gamma_parse_kept("colour_temperature", "cool", &idx, &out) == 1 && idx == 1 && out == GAMMA_T_COOL, "parse: colour_temperature");
		check(gamma_parse_kept("gamma", "9", &idx, &out) == -1 && gamma_parse_kept("colour_temperature", "hot", &idx, &out) == -1,
		      "parse: not a value");
		check(gamma_parse_kept("wb_r_gain", "9", &idx, &out) == 0 && gamma_parse_kept("brightness", "9", &idx, &out) == 0, "parse: not ours");

		f = fopen(path, "w");
		fprintf(f, "gamma = 7\ncolour_temperature = warm\nbrightness = 50\nwb_r_gain = 480\n");
		fclose(f);
		memset(&sv, 0, sizeof(sv));
		sv.path = path;
		saved_read(&sv);
		check(!sv.gm_have[0] && sv.gm_have[1] && sv.gm[1] == GAMMA_T_WARM, "a level out of range is dropped by itself");
		check(sv.have[0] && sv.value[0] == 50 && sv.wb_have[0] && sv.wb[0] == 480, "and the other lines stay");
		saved_delete(&sv, msg, sizeof(msg));
		check(!sv.gm_have[0] && !sv.gm_have[1], "\"save off\" forgets them");

		/* nothing attached, nothing changed: no lines */
		gamma_init();
		f = fopen(path, "w");
		msg[0] = '\0';
		gamma_kept_lines(f, msg, sizeof(msg), 0);
		fclose(f);
		check(!msg[0], "a board without the control writes no lines");
		/* with a value that is not the default: kept even when the control is not there */
		have[0] = true;
		have[1] = false;
		val[0] = 0;
		gamma_adopt(have, val);
		f = fopen(path, "w");
		gamma_kept_lines(f, msg, sizeof(msg), 0);
		fclose(f);
		check(!strcmp(msg, " gamma=0 colour_temperature=auto"), "a value that was kept is not lost when the control is not there");
	}

	/* a board with fewer curves */
	write_base_file(path, 1, 1, &synth, 0);
	gamma_init();
	gamma_attach(path, &fake_io, why, sizeof(why));
	gamma_start();
	reply_clear(&r);
	gamma_set(&r, 1, "warm");
	check(!r.failed && strstr(r.buf, "ok colour_temperature = warm (normal: this board has no warm curve)\n"),
	      "warm on a board that only has normal: accepted, and says what applies");
	expect_curve(vec_stock[0][3], "the normal curve is the one on the CRTC");
	gamma_set(&r, 1, "auto");
	gamma_mode_temp(1, "a picture mode");
	reply_clear(&r);
	gamma_get(&r, 1);
	check(!strcmp(r.buf, "ok colour_temperature = auto (normal)\n"), "auto with a cool picture mode on such a board: normal");
	write_base_file(path, 6, 1, &synth, 0);
	gamma_init();
	gamma_attach(path, &fake_io, why, sizeof(why));
	gamma_start();
	expect_curve(vec_stock[1][3], "a board without normal uses the lowest state it has");

	/* the curve comes from somewhere else, or the start fails */
	gamma_init();
	gamma_unavailable("-g gives the curve");
	reply_clear(&r);
	gamma_set(&r, 1, "cool");
	check(r.failed && strstr(r.buf, "colour_temperature is not available: -g gives the curve"), "with -g the control says why it is not there");
	reply_clear(&r);
	gamma_status(&r);
	check(!strcmp(r.buf, "gamma           not available: -g gives the curve\n"), "and so does status");
	gamma_init();
	gamma_attach(path, &fake_io, why, sizeof(why));
	fake_fail = true;
	check(!gamma_start() && !gamma_active(), "a first curve that the CRTC refuses: the control is gone");
	reply_clear(&r);
	gamma_set(&r, 0, "1");
	check(r.failed && strstr(r.buf, "gamma is not available: the start: the commit was refused"), "and says why");
	fake_fail = false;
	gamma_init();
	write_base_file(path, 7, 2, &synth, 0);
	check(!gamma_attach(path, &fake_io, why, sizeof(why)) && !gamma_active() && strstr(why, "version 2"), "a file that does not read: not attached, and why");
	reply_clear(&r);
	gamma_get(&r, 0);
	check(r.failed && strstr(r.buf, "version 2"), "get says it as well");

	/* ---- main.c's side ---- */
	{
		static const char json[] =
			"{\"version\": 1, \"daten\": \"/x\", \"preset\": \"standard\", \"lut_bytes\": 0, \"gamma_exponent\": 2.2, \"presets\": ["
			"{\"name\": \"standard\", \"modus\": 1, \"regler\": {\"brightness\": 50, \"contrast\": 50, \"saturation\": 50, \"hue\": 50, "
			"\"sharpness\": 50, \"tnr\": 2, \"snr\": 1, \"dci\": 2, \"blackextension\": 1}, \"weitere\": {\"backlight\": 100, "
			"\"colortemperature\": 0, \"gamma\": 3}, \"gamma_exponent\": 2.2},"
			"{\"name\": \"cinema\", \"modus\": 7, \"regler\": {\"brightness\": 50, \"contrast\": 45, \"saturation\": 45, \"hue\": 50, "
			"\"sharpness\": 40, \"tnr\": 2, \"snr\": 1, \"dci\": 0, \"blackextension\": 0}, \"weitere\": {\"backlight\": 100, "
			"\"colortemperature\": 2, \"gamma\": 3}, \"gamma_exponent\": 2.2},"
			"{\"name\": \"vivid\", \"modus\": 0, \"regler\": {\"brightness\": 50, \"contrast\": 55, \"saturation\": 60, \"hue\": 50, "
			"\"sharpness\": 60, \"tnr\": 2, \"snr\": 1, \"dci\": 3, \"blackextension\": 1}, \"weitere\": {\"backlight\": 100, "
			"\"colortemperature\": 1, \"gamma\": 3}, \"gamma_exponent\": 2.2},"
			"{\"name\": \"hdr\", \"modus\": 12, \"regler\": {\"brightness\": 50, \"contrast\": 50, \"saturation\": 50, \"hue\": 50, "
			"\"sharpness\": 50, \"tnr\": 2, \"snr\": 1, \"dci\": 2, \"blackextension\": 1}, \"weitere\": {\"colortemperature\": 9}},"
			"{\"name\": \"odd\", \"modus\": 5, \"regler\": {\"brightness\": 50, \"contrast\": 50, \"saturation\": 50}, "
			"\"weitere\": {\"colortemperature\": 2}}"
			"]}";
		struct pq pt = { .pid = -1, .fd = -1 };

		/* with no data: the compiled table, and the vendor's rule by name */
		pq_presets_n = 0;
		check(preset_ctemp(preset_find("cinema")) == 2 && preset_ctemp(preset_find("hdr")) == 2 &&
		      preset_ctemp(preset_find("vivid")) == 1 && preset_ctemp(preset_find("standard")) == 0 &&
		      preset_ctemp(preset_find("game")) == 0 && preset_ctemp(preset_find("computer")) == 0, "no data: cinema and hdr warm, vivid cool, the rest normal");
		check(mode_ctemp(7) == 2 && mode_ctemp(12) == 2 && mode_ctemp(0) == 1 && mode_ctemp(1) == 0 && mode_ctemp(3) == 0 &&
		      mode_ctemp(6) == 0 && mode_ctemp(9) == 0, "... by the mode number as well, and a mode without a preset is normal");
		check(preset_ctemp(NULL) == 0, "no preset: normal");

		snprintf(pt.raw, sizeof(pt.raw), "%s", json);
		pt.len = strlen(json);
		check(pq_parse(&pt) && pq_presets_n == 4, "a record with colour temperatures is read (a preset with an incomplete row is skipped)");
		check(pq_ctemp[0] == 0 && pq_ctemp[1] == 2 && pq_ctemp[2] == 1 && pq_ctemp[3] == -1,
		      "the colour temperature of each preset comes out of the data, and one that is no colour temperature is not taken");
		check(preset_ctemp(preset_find("cinema")) == 2 && preset_ctemp(preset_find("vivid")) == 1 && preset_ctemp(preset_find("standard")) == 0,
		      "preset_ctemp takes it from there");
		check(mode_ctemp(7) == 2 && mode_ctemp(0) == 1 && mode_ctemp(1) == 0, "and mode_ctemp from the preset with that mode number");
		check(preset_ctemp(preset_find("hdr")) == 2 && mode_ctemp(12) == 2, "a preset whose data say nothing usable falls back to the rule by name");
		pq_presets_n = 0;
	}
	{
		struct drm_color_lut e[GAMMA_ENTRIES];
		gamma_curve c;
		unsigned int v;
		bool inverse = true;

		memset(c, 0, sizeof(c));
		for (v = 0; v < GAMMA_N; v++) {
			c[0][v] = (uint16_t)(v * 4 % 4096);
			c[1][v] = (uint16_t)(4095 - v * 3 % 4096);
			c[2][v] = (uint16_t)v;
		}
		c[0][1023] = 4095;
		c[1][0] = 2048;
		gamma_lut_entries(c, e);
		check(e[0].red == 0 && e[1023].red == 65535 && e[0].green == (2048u * 65535u + 2047u) / 4095u && e[5].blue == (5 * 65535u + 2047u) / 4095u && e[7].reserved == 0,
		      "the entries of GAMMA_LUT: 12 bit spread to 16 bit, sample for sample");
		for (v = 0; v <= GAMMA_MAX; v++) {
			/* drm_color_lut_extract(x, 12) of the kernel the CRTC driver is built for (6.18): DIV_ROUND_CLOSEST(x * 4095, 65535) */
			unsigned int back = (gamma_12_to_16(v) * 4095u + 32767u) / 65535u;

			if (back != v)
				inverse = false;
		}
		check(inverse, "the kernel's way back (drm_color_lut_extract) gives the 12 bit back for every sample");
	}

	unlink(path);
	printf("%s: %d failed\n", failed ? "FAILED" : "PASSED", failed);

	return failed ? 1 : 0;
}
