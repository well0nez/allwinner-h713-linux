// SPDX-License-Identifier: GPL-2.0
/*
 * h713-osd - the overlays over the picture: volume, mute, focus, input (TODO 2.43-2.46).
 *
 * Whoever knows that something happened - h713-keys after a key, a shell - says so in one line on
 * /run/h713-osd/ctl ("volume 40", "mute on 40", "focus up edge", "input console"). This daemon draws the overlay
 * with libh713osd into a picture the size of the panel, pre-distorts it with the warp's own matrix when the
 * picture under it is warped (libh713geom: /etc/h713/warp.conf, the same solve as h713-warp), and hands it to
 * h713-tv, which lays it over the picture on the primary plane (h713-tv README 6h): two ARGB8888 buffers from
 * "osd claim", drawn alternately, "osd show N". An overlay stays `seconds` (osd.conf, 2.5 s); the mute badge
 * stays while muted. README.md in this directory, docs/tools/h713-osd.md.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>
#include <sys/inotify.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/timerfd.h>
#include <sys/un.h>
#include <linux/dma-buf.h>

#include "geom.h"
#include "osd.h"

#define LINE	256

/* the paths, each with an environment override for the host tests */
static const char *osd_socket, *tv_socket, *warp_conf, *osd_conf;

static const char *env(const char *name, const char *def)
{
	const char *v = getenv(name);

	return v && *v ? v : def;
}

/* --- the journal ------------------------------------------------------------------------------------- */

static void say(const char *prefix, const char *fmt, va_list ap)
{
	fputs(prefix, stderr);
	vfprintf(stderr, fmt, ap);
	fputc('\n', stderr);
}

__attribute__((format(printf, 1, 2))) static void info(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	say("", fmt, ap);
	va_end(ap);
}

/* the program's journal line for libh713geom (geom.h); "<4>" is a warning for systemd */
void warn(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	say("<4>", fmt, ap);
	va_end(ap);
}

static double now_s(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

/* --- what is to be seen ------------------------------------------------------------------------------ */

static struct {
	struct osd_item popup;		/* the overlay of the last event */
	double until;			/* when it goes; 0: none */
	bool muted;			/* the badge stays while this is true */
} want = { .popup = { .alpha = 1.0f } };

/* --- osd.conf: place, look, scale, seconds - read again when it changes ------------------------------ */

static struct osd_style style = { OSD_BOTTOM, OSD_PILL, 1.0f };
static double seconds = 2.5;

static void conf_load(void)
{
	char line[LINE];
	FILE *f = fopen(osd_conf, "r");
	int n = 0;

	style = (struct osd_style){ OSD_BOTTOM, OSD_PILL, 1.0f };
	seconds = 2.5;
	if (!f)
		return;		/* no file: the defaults, the owner's choice of 11.10.2026 */
	while (fgets(line, sizeof(line), f)) {
		char key[32], val[32];
		double x;

		n++;
		line[strcspn(line, "#\n")] = '\0';
		if (sscanf(line, " %31[a-z_] = %31s", key, val) != 2)
			continue;
		if (!strcmp(key, "place") && !strcmp(val, "bottom"))
			style.place = OSD_BOTTOM;
		else if (!strcmp(key, "place") && !strcmp(val, "top-right"))
			style.place = OSD_TOP_RIGHT;
		else if (!strcmp(key, "place") && !strcmp(val, "center"))
			style.place = OSD_CENTER;
		else if (!strcmp(key, "look") && !strcmp(val, "pill"))
			style.look = OSD_PILL;
		else if (!strcmp(key, "look") && !strcmp(val, "bare"))
			style.look = OSD_BARE;
		else if (!strcmp(key, "scale") && (x = atof(val)) >= 0.5 && x <= 2.0)
			style.scale = (float)x;
		else if (!strcmp(key, "seconds") && (x = atof(val)) >= 0.5 && x <= 10)
			seconds = x;
		else
			warn("%s:%d: \"%s = %s\" ignored (place bottom|top-right|center, look pill|bare, scale 0.5..2, seconds 0.5..10)",
			     osd_conf, n, key, val);
	}
	fclose(f);
}

/* --- the matrix: warp.conf, solved as h713-warp solves it (warp_solve, loop.c) ------------------------- */

static struct warp_conf geom = { 0 };
static double m[16], hinv[9];
static bool m_valid, m_identity = true;

static void geom_load(void)
{
	int eff[WARP_KEYS];
	double k[16];

	geom.path = warp_conf;
	conf_read(&geom);
	warp_effective(&geom, eff);
	m_identity = warp_identity(eff) && geom.mode == MODE_FRONT;
	if (!warp_matrix(eff, k))
		return;		/* refused: the previous matrix stays, as in the warp */
	for (int i = 0; i < 16; i++)
		if (!isfinite(k[i]))
			return;
	warp_mirror(geom.mode, k);
	if (warp_inverse(k, hinv)) {
		memcpy(m, k, sizeof(m));
		m_valid = true;
	}
}

/* --- h713-tv: the two buffers ------------------------------------------------------------------------ */

static struct {
	int fd;				/* the claimed connection, -1: none */
	int dmabuf[2];
	uint32_t *map[2];
	unsigned int w, h, pitch;
	int next;			/* the buffer to draw into */
	int box[2][2][4];		/* what each buffer holds, in panel pixels: the overlay, the badge */
	bool shown;
	double retry;			/* not before then: the last claim failed */
} tv = { .fd = -1, .dmabuf = { -1, -1 } };

static struct osd_canvas canvas;	/* the overlays straight, in the source's (= panel's) pixels */

/* where the last refresh spent its time, ms (ctl status) - measured, so that the slow part is known */
static struct {
	double draw, ask, clear, put, show;
	int pixels;
	bool skew;
} last;
static int cbox[2][4];			/* what the canvas holds: the overlay, the badge */

static void tv_drop(void)
{
	for (int i = 0; i < 2; i++) {
		if (tv.map[i] && tv.map[i] != MAP_FAILED)
			munmap(tv.map[i], (size_t)tv.pitch * tv.h);
		tv.map[i] = NULL;
		if (tv.dmabuf[i] >= 0)
			close(tv.dmabuf[i]);
		tv.dmabuf[i] = -1;
		memset(tv.box[i], 0, sizeof(tv.box[i]));
	}
	if (tv.fd >= 0)
		close(tv.fd);
	tv.fd = -1;
	tv.shown = false;
}

/* one line to h713-tv, its answer; false when the connection broke (then it is dropped) or the answer is no "ok" */
static bool tv_say(const char *line, char *answer, size_t n)
{
	ssize_t got;

	if (tv.fd < 0)
		return false;
	if (send(tv.fd, line, strlen(line), MSG_NOSIGNAL) < 0 || (got = recv(tv.fd, answer, n - 1, 0)) <= 0) {
		warn("h713-tv: \"%.*s\" got no answer (%s) -- the overlay channel is gone, claimed again at the next event",
		     (int)strcspn(line, "\n"), line, strerror(errno));
		tv_drop();
		return false;
	}
	answer[got] = '\0';
	answer[strcspn(answer, "\n")] = '\0';
	return !strncmp(answer, "ok", 2);
}

static bool tv_claim(void)
{
	char cbuf[CMSG_SPACE(sizeof(int) * 2)] = { 0 }, line[128];
	struct iovec io = { line, sizeof(line) - 1 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = cbuf,
			      .msg_controllen = sizeof(cbuf) };
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	struct timeval tmo = { 2, 0 };
	struct cmsghdr *cm;
	unsigned int w, h, pitch;
	ssize_t got;

	if (tv.fd >= 0)
		return true;
	if (now_s() < tv.retry)
		return false;
	tv.retry = now_s() + 1.0;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", tv_socket);
	tv.fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (tv.fd < 0 || connect(tv.fd, (struct sockaddr *)&addr, sizeof(addr))) {
		tv_drop();
		return false;	/* h713-tv is not running (yet): quietly, the next event asks again */
	}
	setsockopt(tv.fd, SOL_SOCKET, SO_RCVTIMEO, &tmo, sizeof(tmo));
	if (send(tv.fd, "osd claim\n", 10, MSG_NOSIGNAL) < 0 || (got = recvmsg(tv.fd, &msg, MSG_CMSG_CLOEXEC)) <= 0) {
		warn("h713-tv: \"osd claim\" got no answer: %s", strerror(errno));
		tv_drop();
		return false;
	}
	line[got] = '\0';
	line[strcspn(line, "\n")] = '\0';
	for (cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm))
		if (cm->cmsg_level == SOL_SOCKET && cm->cmsg_type == SCM_RIGHTS)
			memcpy(tv.dmabuf, CMSG_DATA(cm), sizeof(tv.dmabuf));
	if (sscanf(line, "ok %u %u %u argb8888", &w, &h, &pitch) != 3 || tv.dmabuf[0] < 0 || tv.dmabuf[1] < 0 ||
	    pitch < w * 4) {
		warn("h713-tv: \"osd claim\" answered \"%s\" -- no overlay (kernel 0251? another h713-osd?)", line);
		tv_drop();
		return false;
	}
	tv.w = w, tv.h = h, tv.pitch = pitch, tv.next = 0;
	for (int i = 0; i < 2; i++) {
		tv.map[i] = mmap(NULL, (size_t)pitch * h, PROT_READ | PROT_WRITE, MAP_SHARED, tv.dmabuf[i], 0);
		if (tv.map[i] == MAP_FAILED) {
			warn("mapping the overlay buffer %d: %s", i, strerror(errno));
			tv_drop();
			return false;
		}
	}
	if (canvas.w != (int)w || canvas.h != (int)h) {
		free(canvas.px);
		canvas.px = calloc((size_t)w * h, 4);
		if (!canvas.px) {
			warn("no memory for a %ux%u canvas", w, h);
			tv_drop();
			return false;
		}
		canvas.w = (int)w, canvas.h = (int)h, canvas.stride = (int)w;
		memset(cbox, 0, sizeof(cbox));
	}
	info("h713-tv: overlay claimed, two %ux%u ARGB8888 buffers", w, h);
	return true;
}

/* --- composing: the overlays into the canvas ------------------------------------------------------------ */

/* what is to be seen, drawn: region 0 the overlay, region 1 the mute badge, each with its own rectangle - kept
 * apart, because together they span most of the panel and the pre-distortion would walk all of it (227 ms).
 * The two never overlap (the badge sits in the corner the overlays leave free, libh713osd), which put_warped()
 * relies on: it writes each row of a region whole. */
static bool compose(int box[2][4])
{
	struct osd_item badge = { OSD_MUTE_BADGE, 0, 0, 1.0f };

	osd_clear_box(&canvas, cbox[0]);
	osd_clear_box(&canvas, cbox[1]);
	memset(box, 0, 2 * 4 * sizeof(int));
	if (want.until > now_s())
		osd_draw(&canvas, &style, &want.popup, box[0]);
	if (want.muted)
		osd_draw(&canvas, &style, &badge, box[1]);	/* over the overlay, where they meet */
	memcpy(cbox, box, sizeof(cbox));
	return (box[0][2] && box[0][3]) || (box[1][2] && box[1][3]);
}

/* --- into a buffer: straight, or through the warp's matrix ------------------------------------------------ */

static void put_straight(uint32_t *dst, const int box[4], int out[4])
{
	for (int y = box[1]; y < box[1] + box[3]; y++)
		memcpy((char *)dst + (size_t)y * tv.pitch + (size_t)box[0] * 4,
		       canvas.px + (size_t)y * canvas.stride + box[0], (size_t)box[2] * 4);
	memcpy(out, box, 4 * sizeof(int));
}

/*
 * The pre-distortion samples a premultiplied copy of the region (bytes A, R*A, G*A, B*A) with integer weights and
 * turns the result back into straight alpha through a table of reciprocals: no floating point per channel, no
 * division per pixel but the one of the homography (11.10.2026 on the board: the volume strip from 23 ms).
 */
static uint32_t *pm;			/* the region, premultiplied */
static int pm_box[4];
static size_t pm_cap;
static uint32_t recip[256];		/* (255 << 16) / a: a premultiplied channel back to straight */

static inline uint32_t mul255(uint32_t c, uint32_t a)	/* c * a / 255, rounded */
{
	uint32_t t = c * a + 128;

	return (t + (t >> 8)) >> 8;
}

static bool premultiply(const int box[4])
{
	size_t n = (size_t)box[2] * box[3];

	if (n > pm_cap) {
		uint32_t *q = realloc(pm, n * sizeof(*pm));

		if (!q)
			return false;
		pm = q, pm_cap = n;
	}
	if (!recip[1])
		for (uint32_t a = 1; a < 256; a++)
			recip[a] = ((255u << 16) + a / 2) / a;
	for (int y = 0; y < box[3]; y++) {
		const uint32_t *src = canvas.px + (size_t)(box[1] + y) * canvas.stride + box[0];
		uint32_t *dst = pm + (size_t)y * box[2];

		for (int x = 0; x < box[2]; x++) {
			uint32_t v = src[x], a = v >> 24;

			dst[x] = a ? a << 24 | mul255(v >> 16 & 255, a) << 16 | mul255(v >> 8 & 255, a) << 8 | mul255(v & 255, a) : 0;
		}
	}
	memcpy(pm_box, box, sizeof(pm_box));
	return true;
}

static inline uint32_t pm_at(int x, int y)	/* transparent outside the region (it has its margin of clear pixels) */
{
	x -= pm_box[0], y -= pm_box[1];
	if ((unsigned)x >= (unsigned)pm_box[2] || (unsigned)y >= (unsigned)pm_box[3])
		return 0;
	return pm[(size_t)y * pm_box[2] + x];
}

/* one premultiplied texel back to straight alpha */
static inline uint32_t straight(uint32_t v)
{
	uint32_t a = v >> 24, r = ((v >> 16 & 255) * recip[a] + 32768) >> 16, g = ((v >> 8 & 255) * recip[a] + 32768) >> 16;
	uint32_t b = ((v & 255) * recip[a] + 32768) >> 16;

	return a ? a << 24 | (r > 255 ? 255 : r) << 16 | (g > 255 ? 255 : g) << 8 | (b > 255 ? 255 : b) : 0;
}

/* bilinear, weights in 1/256, the sum 65536; back to straight alpha. The plain inside of a pill has four equal
 * neighbours: then the texel is the answer, and the last one's conversion is kept */
static inline uint32_t sample(double sx, double sy)
{
	static uint32_t last_in, last_out;
	int x = (int)(sx + 1) - 1, y = (int)(sy + 1) - 1;	/* floor for sx, sy > -1, which the caller ensures */
	int lx = x - pm_box[0], ly = y - pm_box[1];
	uint32_t fx = (uint32_t)((sx - x) * 256), fy = (uint32_t)((sy - y) * 256);
	uint32_t p00, p01, p10, p11, w00, w01, w10, w11, c[4];

	if ((unsigned)lx < (unsigned)(pm_box[2] - 1) && (unsigned)ly < (unsigned)(pm_box[3] - 1)) {
		const uint32_t *q = pm + (size_t)ly * pm_box[2] + lx;

		p00 = q[0], p01 = q[1], p10 = q[pm_box[2]], p11 = q[pm_box[2] + 1];
	} else {
		p00 = pm_at(x, y), p01 = pm_at(x + 1, y), p10 = pm_at(x, y + 1), p11 = pm_at(x + 1, y + 1);
	}
	if (p00 == p01 && p00 == p10 && p00 == p11) {
		if (p00 != last_in)
			last_in = p00, last_out = straight(p00);
		return last_out;
	}
	w00 = (256 - fx) * (256 - fy), w01 = fx * (256 - fy), w10 = (256 - fx) * fy, w11 = fx * fy;
	for (int i = 0, sh = 24; i < 4; i++, sh -= 8)
		c[i] = ((p00 >> sh & 255) * w00 + (p01 >> sh & 255) * w01 + (p10 >> sh & 255) * w10 +
			(p11 >> sh & 255) * w11 + 32768) >> 16;
	if (!c[0])
		return 0;
	for (int i = 1; i < 4; i++) {
		c[i] = (c[i] * recip[c[0]] + 32768) >> 16;
		if (c[i] > 255)
			c[i] = 255;
	}
	return c[0] << 24 | c[1] << 16 | c[2] << 8 | c[3];
}

/* a + b k > 0 narrows [kmin, kmax] */
static void above(double a, double b, double *kmin, double *kmax)
{
	if (b > 0)
		*kmin = fmax(*kmin, -a / b);
	else if (b < 0)
		*kmax = fmin(*kmax, -a / b);
	else if (a <= 0)
		*kmin = 1e18;
}

/*
 * The overlay as the warp would have drawn it: the box's corners through the matrix give the rectangle on the
 * panel; every pixel there goes back through the inverse to the canvas and takes what lies there. Along a row the
 * homography's three rows are linear in x, so they are stepped, one division per pixel; and the pixels whose
 * source lies in the box are known before the row is walked (five linear conditions: w > 0, and the two
 * coordinates between the box's edges), so the rest of the rectangle costs nothing. NDC as in the warp: x = -1
 * the left column, y = -1 the top row (matrix.c, gl.c's quad).
 */
static void put_warped(uint32_t *dst, const int box[4], int out[4])
{
	double W = canvas.w, H = canvas.h, lo[2] = { 1e9, 1e9 }, hi[2] = { -1e9, -1e9 };
	double step = 2.0 / W, bx0;
	double sxlo = box[0] - 1, sxhi = box[0] + box[2], sylo = box[1] - 1, syhi = box[1] + box[3];
	double ulo = (sxlo + 0.5) / W * 2 - 1, uhi = (sxhi + 0.5) / W * 2 - 1;	/* the same edges in NDC */
	double vlo = (sylo + 0.5) / H * 2 - 1, vhi = (syhi + 0.5) / H * 2 - 1;
	int x0, y0, x1, y1;

	memset(out, 0, 4 * sizeof(int));
	if (!premultiply(box))
		return;
	for (int i = 0; i < 4; i++) {
		double sx = (box[0] + (i & 1 ? box[2] : 0)) / W * 2 - 1, sy = (box[1] + (i & 2 ? box[3] : 0)) / H * 2 - 1, p[2];

		warp_point(m, sx, sy, p);
		p[0] = (p[0] + 1) / 2 * W, p[1] = (p[1] + 1) / 2 * H;
		lo[0] = fmin(lo[0], p[0]), lo[1] = fmin(lo[1], p[1]);
		hi[0] = fmax(hi[0], p[0]), hi[1] = fmax(hi[1], p[1]);
	}
	x0 = (int)floor(lo[0]) - 1, y0 = (int)floor(lo[1]) - 1, x1 = (int)ceil(hi[0]) + 1, y1 = (int)ceil(hi[1]) + 1;
	x0 = x0 < 0 ? 0 : x0, y0 = y0 < 0 ? 0 : y0;
	x1 = x1 > canvas.w ? canvas.w : x1, y1 = y1 > canvas.h ? canvas.h : y1;
	if (x1 <= x0 || y1 <= y0)
		return;
	bx0 = (x0 + 0.5) * step - 1;
	/* a row is made in cached memory and copied once: single stores into the write-combined scanout buffer
	 * cost more than the sampling */
	static uint32_t rowbuf[8192];

	for (int y = y0; y < y1; y++) {
		uint32_t *row = rowbuf - x0;
		double ny = (y + 0.5) / H * 2 - 1;
		double nu = hinv[0] * bx0 + hinv[1] * ny + hinv[2], du = hinv[0] * step;
		double nv = hinv[3] * bx0 + hinv[4] * ny + hinv[5], dv = hinv[3] * step;
		double nw = hinv[6] * bx0 + hinv[7] * ny + hinv[8], dw = hinv[6] * step;
		double kmin = 0, kmax = x1 - x0 - 1;
		int ks, ke;

		above(nw, dw, &kmin, &kmax);				/* in front of the horizon */
		above(nu - ulo * nw, du - ulo * dw, &kmin, &kmax);	/* right of the box's left edge */
		above(uhi * nw - nu, uhi * dw - du, &kmin, &kmax);	/* left of its right edge */
		above(nv - vlo * nw, dv - vlo * dw, &kmin, &kmax);
		above(vhi * nw - nv, vhi * dw - dv, &kmin, &kmax);
		if (kmin > kmax)
			continue;
		ks = (int)ceil(kmin) - 1, ke = (int)floor(kmax) + 1;	/* a pixel of margin: the test below decides */
		ks = ks < 0 ? 0 : ks, ke = ke > x1 - x0 - 1 ? x1 - x0 - 1 : ke;
		if (ke < ks || ke - ks >= (int)(sizeof(rowbuf) / sizeof(rowbuf[0])))
			continue;
		nu += du * ks, nv += dv * ks, nw += dw * ks;
		for (int x = x0 + ks; x <= x0 + ke; x++, nu += du, nv += dv, nw += dw) {
			double iw = 1.0 / nw, sx = (nu * iw + 1) * 0.5 * W - 0.5, sy = (nv * iw + 1) * 0.5 * H - 0.5;

			/* false for NaN too; sxlo >= -1 keeps the floor in sample() right */
			row[x] = sx > sxlo && sx < sxhi && sy > sylo && sy < syhi ? sample(sx, sy) : 0;
		}
		memcpy((char *)dst + (size_t)y * tv.pitch + (size_t)(x0 + ks) * 4, rowbuf + ks, (size_t)(ke - ks + 1) * 4);
	}
	out[0] = x0, out[1] = y0, out[2] = x1 - x0, out[3] = y1 - y0;
}

static void buf_sync(int fd, unsigned long long flags)
{
	struct dma_buf_sync s = { flags };

	ioctl(fd, DMA_BUF_IOCTL_SYNC, &s);	/* a memfd in the host tests says ENOTTY: nothing to sync there */
}

/* --- one refresh: compose, put, show ------------------------------------------------------------------------ */

static void refresh(void)
{
	char answer[128];
	int box[2][4], out[2][4] = { { 0 } }, b, area = 0;
	bool warped, skew;
	double t0;

	if (!tv_claim())
		return;
	t0 = now_s();
	if (!compose(box)) {
		if (tv.shown && tv_say("osd hide\n", answer, sizeof(answer)))
			tv.shown = false;
		return;
	}
	last.draw = (now_s() - t0) * 1e3;
	t0 = now_s();
	warped = tv_say("osd picture\n", answer, sizeof(answer)) && !strcmp(answer, "ok warped");
	if (tv.fd < 0)
		return;
	skew = warped && m_valid && !m_identity;
	b = tv.next;
	last.ask = (now_s() - t0) * 1e3;	/* the question to h713-tv: its loop may be in a warp frame */
	t0 = now_s();
	buf_sync(tv.dmabuf[b], DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE);
	for (int r = 0; r < 2; r++)	/* what this buffer showed before */
		for (int y = tv.box[b][r][1]; y < tv.box[b][r][1] + tv.box[b][r][3]; y++)
			memset((char *)tv.map[b] + (size_t)y * tv.pitch + (size_t)tv.box[b][r][0] * 4, 0,
			       (size_t)tv.box[b][r][2] * 4);
	last.clear = (now_s() - t0) * 1e3;
	t0 = now_s();
	for (int r = 0; r < 2; r++) {
		if (!box[r][2] || !box[r][3])
			continue;
		if (skew)
			put_warped(tv.map[b], box[r], out[r]);
		else
			put_straight(tv.map[b], box[r], out[r]);
		area += out[r][2] * out[r][3];
	}
	buf_sync(tv.dmabuf[b], DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE);
	last.put = (now_s() - t0) * 1e3;
	last.pixels = area;
	last.skew = skew;
	t0 = now_s();
	memcpy(tv.box[b], out, sizeof(out));
	snprintf(answer, sizeof(answer), "osd show %d\n", b);
	if (tv_say(answer, answer, sizeof(answer))) {
		tv.shown = true;
		tv.next ^= 1;
	} else if (tv.fd >= 0) {
		warn("h713-tv refused the overlay: %s", answer);
	}
	last.show = (now_s() - t0) * 1e3;
	if (last.draw + last.ask + last.clear + last.put + last.show > 50)
		info("refresh took %.0f ms: draw %.1f, ask %.1f, clear %.1f, %s %.1f (%d pixels), show %.1f",
		     last.draw + last.ask + last.clear + last.put + last.show, last.draw, last.ask, last.clear,
		     skew ? "pre-distort" : "copy", last.put, area, last.show);
}

/* --- the control socket ------------------------------------------------------------------------------------- */

/* one command; the answer into reply; true when the picture has to be drawn again */
static bool handle(const char *line, char *reply, size_t n)
{
	char a[16] = "", b[16] = "", c[16] = "";
	int v = 0, k = sscanf(line, "%15s %15s %15s", a, b, c);
	struct osd_item it = { OSD_VOLUME, 0, 0, 1.0f };

	if (k >= 2 && !strcmp(a, "volume") && sscanf(b, "%d", &v) == 1) {
		it.value = v;
		want.muted = false;		/* a volume change lifts a mute (h713-keys does the same) */
	} else if (k >= 3 && !strcmp(a, "mute") && (!strcmp(b, "on") || !strcmp(b, "off")) && sscanf(c, "%d", &v) == 1) {
		want.muted = !strcmp(b, "on");
		it.kind = want.muted ? OSD_MUTE : OSD_VOLUME;
		it.value = v;
	} else if (k >= 2 && !strcmp(a, "focus") && (!strcmp(b, "up") || !strcmp(b, "down"))) {
		it.kind = OSD_FOCUS;
		it.value = !strcmp(b, "up") ? 1 : -1;
		it.flags = k == 3 && !strcmp(c, "edge") ? OSD_EDGE : 0;
	} else if (k == 2 && !strcmp(a, "input") && (!strcmp(b, "console") || !strcmp(b, "hdmi"))) {
		it.kind = OSD_INPUT;
		it.value = !strcmp(b, "console");
	} else if (k == 1 && !strcmp(a, "hide")) {
		want.until = 0;
		snprintf(reply, n, "ok hidden%s\n", want.muted ? " (the mute badge stays)" : "");
		return true;
	} else if (k == 1 && !strcmp(a, "status")) {
		snprintf(reply, n, "ok status\noverlay         %s\nmuted           %s\nchannel         %s\nmatrix          %s\nstyle           place %s, look %s, scale %.2f, %.1f s\nlast refresh    draw %.1f ms, ask %.1f ms, clear %.1f ms, %s %.1f ms (%d pixels), show %.1f ms\n",
			 want.until > now_s() ? "shown" : "none", want.muted ? "yes (badge)" : "no",
			 tv.fd >= 0 ? (tv.shown ? "claimed, shown" : "claimed") : "not claimed (h713-tv not running, or no event yet)",
			 m_identity ? "identity (straight)" : m_valid ? "from warp.conf (pre-distorted over the warp)" : "refused",
			 style.place == OSD_BOTTOM ? "bottom" : style.place == OSD_TOP_RIGHT ? "top-right" : "center",
			 style.look == OSD_PILL ? "pill" : "bare", style.scale, seconds,
			 last.draw, last.ask, last.clear, last.skew ? "pre-distort" : "copy", last.put, last.pixels, last.show);
		return false;
	} else {
		snprintf(reply, n, "error unknown: volume N | mute on|off N | focus up|down [edge] | input console|hdmi | hide | status\n");
		return false;
	}
	want.popup = it;
	want.until = now_s() + seconds;
	snprintf(reply, n, "ok\n");
	return true;
}

static int listen_on(const char *path)
{
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);

	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
	unlink(path);
	if (fd < 0 || bind(fd, (struct sockaddr *)&addr, sizeof(addr)) || listen(fd, 8)) {
		warn("%s: %s", path, strerror(errno));
		return -1;
	}
	chmod(path, 0660);
	return fd;
}

/* one connection, one line, one answer */
static bool serve(int lfd)
{
	char line[LINE], reply[1024];
	struct timeval tmo = { 1, 0 };
	ssize_t got;
	bool again;
	int fd = accept4(lfd, NULL, NULL, SOCK_CLOEXEC);

	if (fd < 0)
		return false;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tmo, sizeof(tmo));
	got = recv(fd, line, sizeof(line) - 1, 0);
	if (got <= 0) {
		close(fd);
		return false;
	}
	line[got] = '\0';
	line[strcspn(line, "\r\n")] = '\0';
	again = handle(line, reply, sizeof(reply));
	if (send(fd, reply, strlen(reply), MSG_NOSIGNAL) < 0)
		warn("answering \"%s\": %s", line, strerror(errno));
	close(fd);
	return again;
}

/* the client: h713-osd ctl COMMAND... */
static int client(int argc, char **argv)
{
	char line[LINE] = "", buf[1024];
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	size_t len = 0;
	ssize_t n;
	int fd, rc = 1;

	for (int i = 0; i < argc && len < sizeof(line) - 2; i++)
		len += (size_t)snprintf(line + len, sizeof(line) - len, "%s%s", i ? " " : "", argv[i]);
	snprintf(line + len, sizeof(line) - len, "\n");
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", osd_socket);
	fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (fd < 0 || connect(fd, (struct sockaddr *)&addr, sizeof(addr))) {
		fprintf(stderr, "%s: %s -- is h713-osd running?\n", osd_socket, strerror(errno));
		return 1;
	}
	if (send(fd, line, strlen(line), MSG_NOSIGNAL) < 0)
		return 1;
	while ((n = read(fd, buf, sizeof(buf) - 1)) > 0) {
		buf[n] = '\0';
		if (rc == 1)
			rc = strncmp(buf, "ok", 2) ? 1 : 0;
		fputs(buf, stdout);
	}
	close(fd);
	return rc;
}

/* --- the loop ----------------------------------------------------------------------------------------------- */

/* the next thing to do: an overlay's end, or - while something is to be seen and h713-tv is not claimed (it
 * restarted, after a standby too) - the next claim, so the mute badge comes back without a key */
static void arm(int tfd)
{
	struct itimerspec its = { 0 };
	double next = want.until > 0 ? want.until : 0, dt;

	if (tv.fd < 0 && (want.muted || want.until > 0)) {
		double r = tv.retry > now_s() ? tv.retry : now_s() + 1.0;

		if (!next || r < next)
			next = r;
	}

	if (next > 0) {
		dt = next - now_s();
		if (dt < 0.001)
			dt = 0.001;
		its.it_value.tv_sec = (time_t)dt;
		its.it_value.tv_nsec = (long)((dt - (time_t)dt) * 1e9);
	}
	timerfd_settime(tfd, 0, &its, NULL);
}

static int run(void)
{
	struct pollfd p[5];
	sigset_t mask;
	char dir[256], *slash, ev[4096];
	int lfd, tfd, ifd, sfd;

	conf_load();
	geom_load();
	lfd = listen_on(osd_socket);
	if (lfd < 0)
		return 1;
	tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	ifd = inotify_init1(IN_CLOEXEC | IN_NONBLOCK);
	snprintf(dir, sizeof(dir), "%s", warp_conf);
	slash = strrchr(dir, '/');
	if (slash)
		*slash = '\0';
	/* warp.conf is rewritten whole and renamed over (config.c); osd.conf by hand, in place or renamed */
	if (ifd >= 0 && inotify_add_watch(ifd, dir, IN_CLOSE_WRITE | IN_MOVED_TO) < 0)
		warn("watching %s: %s -- a new keystone reaches the overlay at the next restart", dir, strerror(errno));
	sigemptyset(&mask);
	sigaddset(&mask, SIGTERM);
	sigaddset(&mask, SIGINT);
	sigprocmask(SIG_BLOCK, &mask, NULL);
	sfd = signalfd(-1, &mask, SFD_CLOEXEC);
	info("ready: %s; place %s, look %s; keystone %s", osd_socket,
	     style.place == OSD_BOTTOM ? "bottom" : style.place == OSD_TOP_RIGHT ? "top-right" : "center",
	     style.look == OSD_PILL ? "pill" : "bare", m_identity ? "none" : m_valid ? "from warp.conf" : "refused");

	for (;;) {
		bool again = false;

		p[0] = (struct pollfd){ lfd, POLLIN, 0 };
		p[1] = (struct pollfd){ tfd, POLLIN, 0 };
		p[2] = (struct pollfd){ ifd, POLLIN, 0 };
		p[3] = (struct pollfd){ sfd, POLLIN, 0 };
		p[4] = (struct pollfd){ tv.fd, POLLIN, 0 };	/* only a hangup is expected here */
		if (poll(p, 5, -1) < 0 && errno != EINTR)
			break;
		if (p[3].revents)
			break;
		if (p[4].revents) {
			char c;

			if (recv(tv.fd, &c, 1, MSG_DONTWAIT) <= 0) {
				info("h713-tv went away -- the overlay is claimed again at the next event");
				tv_drop();
			}
		}
		if (p[0].revents)
			again |= serve(lfd);
		if (p[1].revents) {
			uint64_t ticks;

			if (read(tfd, &ticks, sizeof(ticks)) > 0) {
				if (want.until && want.until <= now_s()) {
					want.until = 0;
					again = true;
				}
				if (tv.fd < 0 && (want.muted || want.until))
					again = true;	/* the claim again */
			}
		}
		if (p[2].revents) {
			ssize_t len = read(ifd, ev, sizeof(ev));

			for (char *q = ev; len > 0 && q < ev + len;) {
				struct inotify_event *e = (struct inotify_event *)q;
				const char *base = strrchr(warp_conf, '/');
				const char *obase = strrchr(osd_conf, '/');

				if (e->len && base && !strcmp(e->name, base + 1)) {
					geom_load();
					again = true;
				} else if (e->len && obase && !strcmp(e->name, obase + 1)) {
					conf_load();
					again = true;
				}
				q += sizeof(*e) + e->len;
			}
		}
		if (again)
			refresh();
		arm(tfd);
	}
	info("exit: the overlay off, the buffers back");
	if (tv.fd >= 0) {
		char answer[64];

		tv_say("osd hide\n", answer, sizeof(answer));
		tv_say("osd release\n", answer, sizeof(answer));
	}
	tv_drop();
	unlink(osd_socket);
	return 0;
}

int main(int argc, char **argv)
{
	osd_socket = env("H713_OSD_SOCKET", "/run/h713-osd/ctl");
	tv_socket = env("H713_OSD_TV", "/run/h713-tv/ctl");
	warp_conf = env("H713_OSD_WARP_CONF", WARP_CONF);
	osd_conf = env("H713_OSD_CONF", "/etc/h713/osd.conf");
	if (argc >= 2 && !strcmp(argv[1], "run"))
		return run();
	if (argc >= 3 && !strcmp(argv[1], "ctl"))
		return client(argc - 2, argv + 2);
	fprintf(stderr, "usage: h713-osd run | h713-osd ctl volume N | mute on|off N | focus up|down [edge] | input console|hdmi | hide | status\n");
	return 2;
}
