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
#include <pthread.h>
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

#define LINE	768	/* a launcher line carries the rows too */

/* the paths, each with an environment override for the host tests */
static const char *osd_socket, *tv_socket, *warp_conf, *osd_conf, *fake_clock;
static bool trace;			/* H713_OSD_TRACE=1: one journal line per refresh with wall-clock times (package H, gate HL) */
static double t_cmd;			/* CLOCK_REALTIME when the last command reached the socket */

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

static double real_s(void)
{
	struct timespec t;

	clock_gettime(CLOCK_REALTIME, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

/* --- what is to be seen ------------------------------------------------------------------------------ */

static struct {
	struct osd_item popup;		/* the overlay of the last event */
	double until;			/* when it goes; 0: none */
	bool muted;			/* the badge stays while this is true */
} want = { .popup = { .alpha = 1.0f } };

/*
 * The launcher (package H of the media side project): an OPAQUE page over the whole panel - a ground, the list on the left, the rest calm
 * (Marco, 15.10.2026: "it must have a ground, it is not an overlay over the picture") - that stays until it is closed. It is cut into
 * tiles (libh713osd: the bands of the page - the header, one per row, the foot, the gap - each in a left part, the column, and a right
 * part, the ground alone). A tile is repainted in the canvas when it changes and put into a buffer when that buffer does not hold its
 * current picture - a move of the selection costs two tiles of the column, not the page (the pre-distortion walks every pixel of what it
 * puts). gen[] is what each tile should show, cgen[] what the canvas was painted with, ver[] the canvas' version of it (a volume strip
 * drawn over it is a new version), held[][] the version each of the two buffers holds. The volume, mute and the power countdown are
 * drawn into the page's canvas too and ride in the tiles they touch. The buffer that is not shown is filled in the idle time after a
 * refresh (prefill_at), so that the next key finds it ready.
 */
#define BANDS (OSD_LAUNCHER_ROWS + 3)
#define TILES (2 * BANDS)
#define PREFILL_S 0.12
static struct {
	bool open;
	struct osd_launcher l;
	char now[48], head[80], label[OSD_LAUNCHER_ROWS][48];
	unsigned counter, gen[TILES], cgen[TILES], ver[TILES], held[2][TILES];
	bool live[2], skew[2], wipe[2];	/* the buffer holds launcher pixels / they went through the matrix / clear them first */
	double prefill_at;		/* when the buffer that is not shown is filled; 0: nothing due */
} lau;

/*
 * The page channel (package S of the media side project, h713-settings): a program draws a whole page into a canvas the
 * size of the panel - a memfd that "page open" hands over - and says which rows are new ("page show X Y W H"). This daemon
 * copies those rows, the panel's full width, into its canvas, puts them into the buffer h713-tv shows - straight, or through
 * the matrix in bands like the launcher's, so that there is no seam - and shows it, then answers "ok" (or "ok waiting": no
 * picture at the moment, the page is kept for its return). It stays the one holder of the overlay channel; the page's
 * connection is the page's life. Popups and the mute badge are not drawn while a page is open: the page covers the panel.
 * Rows are kept as up to PAGE_RANGES ranges [y0, y1) (y0 >= y1: none): a row and the note at the foot are two small ranges,
 * not the one big rectangle around both - what is put through a keystone is paid for by the pixel. A range also keeps the columns
 * [x0, x1) its "page show"s named (the union): a pill in the middle of the panel is not put from edge to edge.
 */
#define PAGE_RANGES 4
static struct {
	int fd;				/* the page's connection, -1: none */
	uint32_t *px;			/* the page's canvas, shared with the client */
	size_t len;
	bool open;
	int owe;			/* answers owed: one per "page show", given after the refresh */
	int cnew[PAGE_RANGES][4];	/* the rows (y0, y1) and columns (x0, x1) not yet copied into the canvas */
	int dirty[2][PAGE_RANGES][4];	/* per buffer: the same for what is not yet put there */
	bool live[2], skew[2];		/* the buffer holds page pixels / they went through the matrix */
	char buf[160];
	size_t blen;
} page = { .fd = -1 };

static bool osd_waiting;		/* the last refresh was not seen: no picture, or no channel */

/* y0..y1 x x0..x1 into the ranges: merged with one it touches or lies within 24 rows of (the columns united), else a free place, else
 * into the last one */
static void rows_add(int r[PAGE_RANGES][4], int y0, int y1, int x0, int x1)
{
	int free_at = -1;

	for (int i = 0; i < PAGE_RANGES; i++) {
		if (r[i][0] >= r[i][1]) {
			free_at = free_at < 0 ? i : free_at;
		} else if (y0 <= r[i][1] + 24 && y1 >= r[i][0] - 24) {
			r[i][0] = y0 < r[i][0] ? y0 : r[i][0];
			r[i][1] = y1 > r[i][1] ? y1 : r[i][1];
			r[i][2] = x0 < r[i][2] ? x0 : r[i][2];
			r[i][3] = x1 > r[i][3] ? x1 : r[i][3];
			return;
		}
	}
	if (free_at >= 0) {
		r[free_at][0] = y0, r[free_at][1] = y1, r[free_at][2] = x0, r[free_at][3] = x1;
	} else {
		int *l = r[PAGE_RANGES - 1];

		l[0] = y0 < l[0] ? y0 : l[0];
		l[1] = y1 > l[1] ? y1 : l[1];
		l[2] = x0 < l[2] ? x0 : l[2];
		l[3] = x1 > l[3] ? x1 : l[3];
	}
}

static void rows_set(int r[PAGE_RANGES][4], int y0, int y1)	/* exactly this: none or the whole page */
{
	memset(r, 0, sizeof(int) * PAGE_RANGES * 4);
	r[0][0] = y0, r[0][1] = y1, r[0][2] = 0, r[0][3] = 1 << 30;	/* the columns: the whole width, cut to the canvas where used */
}

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
		lau.wipe[0] = lau.wipe[1] = true;	/* the launcher's footprint on the panel moved */
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
		memset(lau.held[i], 0, sizeof(lau.held[i]));
		lau.live[i] = lau.wipe[i] = false;
		page.live[i] = false;
		rows_set(page.dirty[i], 0, page.open ? canvas.h : 0);	/* the next claim puts the whole page */
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

/* h713-tv's own word on the mute: 1 on, 0 off, -1 unknown. Asked at the start and before every claim, on a
 * connection of its own, so the badge survives a restart of either daemon (an update, a standby). */
static int tv_mute(void)
{
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	struct timeval tmo = { 1, 0 };
	char buf[128];
	ssize_t got;
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0), r = -1;

	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", tv_socket);
	if (fd < 0)
		return -1;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tmo, sizeof(tmo));
	if (!connect(fd, (struct sockaddr *)&addr, sizeof(addr)) && send(fd, "mute\n", 5, MSG_NOSIGNAL) == 5 &&
	    (got = recv(fd, buf, sizeof(buf) - 1, 0)) > 0) {
		buf[got] = '\0';
		r = !strncmp(buf, "ok mute on", 10) ? 1 : !strncmp(buf, "ok mute off", 11) ? 0 : -1;
	}
	close(fd);
	return r;
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

	int mute;

	if (tv.fd >= 0)
		return true;
	if (now_s() < tv.retry)
		return false;
	tv.retry = now_s() + 1.0;
	mute = tv_mute();
	if (mute >= 0)
		want.muted = mute;
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

static void lau_dirty(int tile)
{
	lau.gen[tile] = ++lau.counter;
}

/* the tiles that a rectangle of the canvas touches: wanted again (repaint, to take a volume strip off) or in a new version (put again) */
static void lau_rect(const int rc[4], bool repaint)
{
	int box[TILES][4], n;

	if (!lau.open || !rc[2] || !rc[3])
		return;
	n = osd_launcher_bands(&canvas, &lau.l, box);
	for (int k = 0; k < n; k++)
		if (box[k][3] && rc[0] < box[k][0] + box[k][2] && rc[0] + rc[2] > box[k][0] && rc[1] < box[k][1] + box[k][3] &&
		    rc[1] + rc[3] > box[k][1]) {
			if (repaint)
				lau_dirty(k);
			else
				lau.ver[k] = ++lau.counter;
		}
}

/* the header is "HH:MM \xc2\xb7 NOW" - NOW is the caller's (HDMI 1080p60, Kodi); a new minute is a new header */
static void lau_clock(void)
{
	time_t t = time(NULL);
	struct tm tm;
	char head[sizeof(lau.head)];

	localtime_r(&t, &tm);
	snprintf(head, sizeof(head), "%02d:%02d \xc2\xb7 %s", tm.tm_hour, tm.tm_min, lau.now);
	if (*fake_clock)	/* the tests: a fixed time, so that two draws are the same picture */
		snprintf(head, sizeof(head), "%.5s \xc2\xb7 %s", fake_clock, lau.now);
	if (strcmp(head, lau.head)) {
		memcpy(lau.head, head, sizeof(head));
		lau_dirty(0);
	}
}

static bool lau_clock_changed(void)
{
	unsigned before = lau.gen[0];

	lau_clock();
	return lau.gen[0] != before;
}

/* the tiles the canvas does not show in their current state, drawn again */
static void lau_paint(void)
{
	int box[TILES][4], n = osd_launcher_bands(&canvas, &lau.l, box);

	for (int k = 0; k < n; k++)
		if (lau.cgen[k] != lau.gen[k]) {
			osd_launcher_draw(&canvas, &lau.l, k);
			lau.cgen[k] = lau.gen[k];
			lau.ver[k] = ++lau.counter;
		}
}

/* what is to be seen, drawn: region 0 the overlay, region 1 the mute badge, each with its own rectangle - kept
 * apart, because together they span most of the panel and the pre-distortion would walk all of it (227 ms).
 * The two never overlap (the badge sits in the corner the overlays leave free, libh713osd), which put_warped()
 * relies on: it writes each row of a region whole. */
static bool compose(int box[2][4])
{
	struct osd_item badge = { OSD_MUTE_BADGE, 0, 0, 1.0f };

	memset(box, 0, 2 * 4 * sizeof(int));
	if (lau.open) {		/* the strips of the last time come off by repainting the tiles under them: the page is not transparent */
		lau_rect(cbox[0], true);
		lau_rect(cbox[1], true);
		lau_clock();
		lau_paint();
	} else {
		osd_clear_box(&canvas, cbox[0]);
		osd_clear_box(&canvas, cbox[1]);
	}
	if (page.open) {	/* after the clearing above: a popup's last place is the page's again */
		for (int i = 0; i < PAGE_RANGES; i++)
			for (int y = page.cnew[i][0]; y < page.cnew[i][1]; y++) {
				int cx0 = page.cnew[i][2], cx1 = page.cnew[i][3] < canvas.w ? page.cnew[i][3] : canvas.w;

				if (cx1 > cx0)
					memcpy(canvas.px + (size_t)y * canvas.stride + cx0, page.px + (size_t)y * canvas.stride + cx0, (size_t)(cx1 - cx0) * 4);
			}
		rows_set(page.cnew, 0, 0);
	} else {
		if (want.until > now_s())
			osd_draw(&canvas, &style, &want.popup, box[0]);
		if (want.muted)
			osd_draw(&canvas, &style, &badge, box[1]);	/* over the overlay, where they meet */
		lau_rect(box[0], false);	/* over the page they are part of the tiles they touch */
		lau_rect(box[1], false);
	}
	memcpy(cbox, box, sizeof(cbox));
	return (box[0][2] && box[0][3]) || (box[1][2] && box[1][3]) || lau.open || page.open;
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

/*
 * The flat map of the premultiplied region: per block of FB x FB texels the colour if every texel of it has that colour. A page is
 * mostly its ground: a run of panel pixels whose source texels (with the bilinear neighbours) all lie in flat blocks of one colour
 * has that colour, and is written without a division per pixel (the ground of the settings page, 16.10.2026).
 */
#define FB 8
#define FLAT_RUN 16			/* panel pixels per test: two homography divisions instead of sixteen */
static uint32_t *fcol;
static uint8_t *fflat;
static int fbw, fbh;
static size_t fcap;
static bool flat_ok;			/* the map belongs to the region of the last premultiply */

static inline uint32_t mul255(uint32_t c, uint32_t a)	/* c * a / 255, rounded */
{
	uint32_t t = c * a + 128;

	return (t + (t >> 8)) >> 8;
}

/* fn over the units [lo, hi), cut into pieces of whole `align` units for up to four threads when the work (pixels) is large enough:
 * the pre-distortion of a page is a few million pixels, and the board has four cores (16.10.2026). The calling thread does the last piece. */
#define MAX_THREADS 4
struct part {
	void (*fn)(void *, int, int);
	void *arg;
	int lo, hi;
};

static void *part_main(void *p)
{
	struct part *q = p;

	q->fn(q->arg, q->lo, q->hi);
	return NULL;
}

static void parallel(void (*fn)(void *, int, int), void *arg, int lo, int hi, int align, size_t work)
{
	static int ncpu;
	pthread_t tid[MAX_THREADS];
	struct part part[MAX_THREADS];
	bool started[MAX_THREADS] = { false };
	const char *e = getenv("H713_OSD_THREADS");	/* the benches and the tests: 1 = none */
	int n, per, nlast;

	if (!ncpu) {
		long c = sysconf(_SC_NPROCESSORS_ONLN);

		ncpu = c < 1 ? 1 : c > MAX_THREADS ? MAX_THREADS : (int)c;
	}
	n = e ? atoi(e) : ncpu;
	n = n > MAX_THREADS ? MAX_THREADS : n;
	if (work < 60000 || hi - lo < 4 * align)
		n = 1;
	if (n < 2) {
		fn(arg, lo, hi);
		return;
	}
	per = ((hi - lo + n - 1) / n + align - 1) / align * align;
	for (nlast = 0; nlast < n - 1 && lo + (nlast + 1) * per < hi; nlast++)
		;
	for (int i = 0; i < nlast; i++) {
		part[i] = (struct part){ fn, arg, lo + i * per, lo + (i + 1) * per };
		started[i] = pthread_create(&tid[i], NULL, part_main, &part[i]) == 0;
		if (!started[i])
			fn(arg, part[i].lo, part[i].hi);
	}
	fn(arg, lo + nlast * per, hi);
	for (int i = 0; i < nlast; i++)
		if (started[i])
			pthread_join(tid[i], NULL);
}

static inline uint32_t premul1(uint32_t v)
{
	uint32_t a = v >> 24;

	return a == 255 ? v : a ? a << 24 | mul255(v >> 16 & 255, a) << 16 | mul255(v >> 8 & 255, a) << 8 | mul255(v & 255, a) : 0;
}

struct pmjob {
	int box[4];
	bool map;
};

/* the rows lo..hi-1 of the region, premultiplied, and their blocks' flat map (lo is a multiple of FB: a block row is one thread's) */
static void pm_rows(void *arg, int lo, int hi)
{
	const struct pmjob *j = arg;
	const int *box = j->box;
	bool map = j->map;

	for (int y = lo; y < hi; y++) {
		const uint32_t *src = canvas.px + (size_t)(box[1] + y) * canvas.stride + box[0];
		uint32_t *dst = pm + (size_t)y * box[2];

		if (!map) {
			for (int x = 0; x < box[2]; x++)
				dst[x] = premul1(src[x]);
			continue;
		}
		/* the flat map in the same pass: per block of FB texels the colour of its first texel, and whether every texel of the block has it */
		uint32_t *cc = fcol + (size_t)(y / FB) * fbw;
		uint8_t *ff = fflat + (size_t)(y / FB) * fbw;

		for (int bx = 0, xs = 0; bx < fbw; bx++, xs += FB) {
			int xe = xs + FB < box[2] ? xs + FB : box[2];
			uint32_t diff = 0, c0;

			for (int x = xs; x < xe; x++)
				dst[x] = premul1(src[x]);
			if (y % FB == 0)
				cc[bx] = dst[xs], ff[bx] = 1;
			c0 = cc[bx];
			for (int x = xs; x < xe; x++)
				diff |= dst[x] ^ c0;
			if (diff)
				ff[bx] = 0;
		}
	}
}

static bool premultiply(const int box[4])
{
	size_t n = (size_t)box[2] * box[3];
	static int noflat = -1;
	bool map;

	if (noflat < 0)
		noflat = getenv("H713_OSD_NOFLAT") != NULL;	/* the tests: every pixel through the inverse, as before the flat runs */
	map = !noflat && box[2] >= 4 * FB && box[3] >= 4 * FB && n >= 16384;

	if (n > pm_cap) {
		uint32_t *q = realloc(pm, n * sizeof(*pm));

		if (!q)
			return false;
		pm = q, pm_cap = n;
	}
	if (!recip[1])
		for (uint32_t a = 1; a < 256; a++)
			recip[a] = ((255u << 16) + a / 2) / a;
	flat_ok = false;
	if (map) {
		size_t nb = (size_t)((box[2] + FB - 1) / FB) * ((box[3] + FB - 1) / FB);

		fbw = (box[2] + FB - 1) / FB, fbh = (box[3] + FB - 1) / FB;
		if (nb > fcap) {
			uint32_t *c = realloc(fcol, nb * sizeof(*fcol));
			uint8_t *f;

			if (c)
				fcol = c;
			f = c ? realloc(fflat, nb) : NULL;
			if (f)
				fflat = f, fcap = nb;
			else
				map = false;
		}
	}
	{
		struct pmjob job = { { box[0], box[1], box[2], box[3] }, map };

		parallel(pm_rows, &job, 0, box[3], FB, n);
	}
	memcpy(pm_box, box, sizeof(pm_box));
	flat_ok = map;
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
	static __thread uint32_t last_in, last_out;	/* per thread: the pre-distortion runs on several */
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

/* do FLAT_RUN panel pixels from the accumulators (nu, nv, nw at the first) take one flat colour? Along a row the source point is a
 * projective function of the pixel, monotonic where w > 0: the texels it touches (with the bilinear neighbours) lie between those of
 * the two ends. All in flat blocks of one colour: that colour, back to straight alpha, is what sample() would return for each. */
static bool flat_run(double nu, double nv, double nw, double du, double dv, double dw, double W, double H, uint32_t *out)
{
	double ax = (nu / nw + 1) * 0.5 * W - 0.5, ay = (nv / nw + 1) * 0.5 * H - 0.5;
	double e = FLAT_RUN - 1, bw = nw + dw * e;
	double bx = ((nu + du * e) / bw + 1) * 0.5 * W - 0.5, by = ((nv + dv * e) / bw + 1) * 0.5 * H - 0.5;
	int tx0 = (int)floor(fmin(ax, bx)) - pm_box[0], tx1 = (int)floor(fmax(ax, bx)) + 1 - pm_box[0];
	int ty0 = (int)floor(fmin(ay, by)) - pm_box[1], ty1 = (int)floor(fmax(ay, by)) + 1 - pm_box[1];
	uint32_t c;

	if (tx0 < 0 || ty0 < 0 || tx1 >= pm_box[2] || ty1 >= pm_box[3])
		return false;
	c = fcol[(size_t)(ty0 / FB) * fbw + tx0 / FB];
	for (int y = ty0 / FB; y <= ty1 / FB; y++)
		for (int x = tx0 / FB; x <= tx1 / FB; x++)
			if (!fflat[(size_t)y * fbw + x] || fcol[(size_t)y * fbw + x] != c)
				return false;
	*out = straight(c);
	return true;
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
/* what a row of the pre-distortion needs, once for the whole put */
struct wjob {
	uint32_t *dst;
	int x0, x1;
	double W, H, step, bx0, sxlo, sxhi, sylo, syhi, ulo, uhi, vlo, vhi;
};

static void warp_rows(void *arg, int ya, int yb)
{
	const struct wjob *j = arg;
	const double W = j->W, H = j->H, step = j->step, bx0 = j->bx0, sxlo = j->sxlo, sxhi = j->sxhi, sylo = j->sylo, syhi = j->syhi;
	const int x0 = j->x0, x1 = j->x1;
	/* a row is made in cached memory and copied once: single stores into the write-combined scanout buffer
	 * cost more than the sampling */
	uint32_t rowbuf[8192];

	for (int y = ya; y < yb; y++) {
		uint32_t *row = rowbuf - x0;
		double ny = (y + 0.5) / H * 2 - 1;
		double nu = hinv[0] * bx0 + hinv[1] * ny + hinv[2], du = hinv[0] * step;
		double nv = hinv[3] * bx0 + hinv[4] * ny + hinv[5], dv = hinv[3] * step;
		double nw = hinv[6] * bx0 + hinv[7] * ny + hinv[8], dw = hinv[6] * step;
		double kmin = 0, kmax = x1 - x0 - 1;
		int ks, ke;

		above(nw, dw, &kmin, &kmax);				/* in front of the horizon */
		above(nu - j->ulo * nw, du - j->ulo * dw, &kmin, &kmax);	/* right of the box's left edge */
		above(j->uhi * nw - nu, j->uhi * dw - du, &kmin, &kmax);	/* left of its right edge */
		above(nv - j->vlo * nw, dv - j->vlo * dw, &kmin, &kmax);
		above(j->vhi * nw - nv, j->vhi * dw - dv, &kmin, &kmax);
		if (kmin > kmax)
			continue;
		ks = (int)ceil(kmin) - 1, ke = (int)floor(kmax) + 1;	/* a pixel of margin: the test below decides */
		ks = ks < 0 ? 0 : ks, ke = ke > x1 - x0 - 1 ? x1 - x0 - 1 : ke;
		if (ke < ks || ke - ks >= (int)(sizeof(rowbuf) / sizeof(rowbuf[0])))
			continue;
		nu += du * ks, nv += dv * ks, nw += dw * ks;
		int first = -1, lastx = -2;	/* the run of pixels that count: only those are written */
		/* pixels a whole pixel inside the analytic run certainly pass the test below: those may be written in runs of FLAT_RUN */
		int in0 = flat_ok ? (int)ceil(kmin) + 1 : ke + 1, in1 = (int)floor(kmax) - 1;

		for (int x = x0 + ks; x <= x0 + ke; x++, nu += du, nv += dv, nw += dw) {
			double iw, sx, sy;
			uint32_t flat;

			if (x - x0 >= in0 && x - x0 + FLAT_RUN - 1 <= in1 && flat_run(nu, nv, nw, du, dv, dw, W, H, &flat)) {
				for (int i = 0; i < FLAT_RUN; i++)
					row[x + i] = flat;
				first = first < 0 ? x - x0 : first;
				lastx = x - x0 + FLAT_RUN - 1;
				nu += du * (FLAT_RUN - 1), nv += dv * (FLAT_RUN - 1), nw += dw * (FLAT_RUN - 1);
				x += FLAT_RUN - 1;
				continue;
			}
			iw = 1.0 / nw, sx = (nu * iw + 1) * 0.5 * W - 0.5, sy = (nv * iw + 1) * 0.5 * H - 0.5;
			/* false for NaN too; sxlo >= -1 keeps the floor in sample() right */
			if (sx > sxlo && sx < sxhi && sy > sylo && sy < syhi) {
				row[x] = sample(sx, sy);
				first = first < 0 ? x - x0 : first;
				lastx = x - x0;
			}
		}
		/* not the margin pixels of the run, which the test above turned down: they belong to a neighbouring tile (the page's tiles
		 * meet along slanted lines through the matrix), and a zero written there is a hole in the page */
		if (first >= 0)
			memcpy((char *)j->dst + (size_t)y * tv.pitch + (size_t)(x0 + first) * 4, rowbuf + first, (size_t)(lastx - first + 1) * 4);
	}
}

static void put_warped(uint32_t *dst, const int box[4], const double *xr, const double *yr, int out[4])
{
	double W = canvas.w, H = canvas.h, lo[2] = { 1e9, 1e9 }, hi[2] = { -1e9, -1e9 };
	/* the source columns and rows that count: xr, yr = { low, high } (exclusive), or the box's own with half a pixel of fade */
	double sxlo = xr ? xr[0] : box[0] - 1, sxhi = xr ? xr[1] : box[0] + box[2];
	double sylo = yr ? yr[0] : box[1] - 1, syhi = yr ? yr[1] : box[1] + box[3];
	struct wjob job;
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
	job = (struct wjob){ dst, x0, x1, W, H, 2.0 / W, (x0 + 0.5) * (2.0 / W) - 1, sxlo, sxhi, sylo, syhi,
			     (sxlo + 0.5) / W * 2 - 1, (sxhi + 0.5) / W * 2 - 1,	/* the same edges in NDC */
			     (sylo + 0.5) / H * 2 - 1, (syhi + 0.5) / H * 2 - 1 };
	parallel(warp_rows, &job, y0, y1, 1, (size_t)(x1 - x0) * (size_t)(y1 - y0));
	out[0] = x0, out[1] = y0, out[2] = x1 - x0, out[3] = y1 - y0;
}

/* the launcher's tiles into buffer b - those it does not hold in their current version - straight or through the matrix.
 * Each tile is put from a source with LAU_MARGIN rows and columns of its neighbours' pixels around it, but only the panel pixels
 * whose source lies in the tile itself are written: the tiles' footprints tile the page, and the bilinear sample at a tile's
 * edge sees the neighbour's pixels instead of the transparent nothing outside a region (a seam at every boundary
 * otherwise: alpha down to 60 % on a line, 11 rows of 1 pixel on the panel). Returns the pixels put. */
#define LAU_MARGIN 2

static int lau_put(int b, bool skew)
{
	int box[TILES][4], n = osd_launcher_bands(&canvas, &lau.l, box), area = 0;

	for (int k = 0; k < n; k++) {
		int x0 = box[k][0] > LAU_MARGIN ? box[k][0] - LAU_MARGIN : 0, y0 = box[k][1] > LAU_MARGIN ? box[k][1] - LAU_MARGIN : 0, out[4];
		int x1 = box[k][0] + box[k][2] + LAU_MARGIN < canvas.w ? box[k][0] + box[k][2] + LAU_MARGIN : canvas.w;
		int y1 = box[k][1] + box[k][3] + LAU_MARGIN < canvas.h ? box[k][1] + box[k][3] + LAU_MARGIN : canvas.h;
		int r[4] = { x0, y0, x1 - x0, y1 - y0 };

		if (!box[k][2] || !box[k][3] || lau.held[b][k] == lau.ver[k])
			continue;
		if (skew) {	/* source column/row i is the pixel between i - 0.5 and i + 0.5; the canvas' edges keep their fade */
			double xr[2] = { box[k][0] ? box[k][0] - 0.5 : -1, box[k][0] + box[k][2] < canvas.w ? box[k][0] + box[k][2] - 0.5 : canvas.w };
			double yr[2] = { box[k][1] ? box[k][1] - 0.5 : -1, box[k][1] + box[k][3] < canvas.h ? box[k][1] + box[k][3] - 0.5 : canvas.h };

			put_warped(tv.map[b], r, xr, yr, out);
		} else {
			put_straight(tv.map[b], r, out);
		}
		area += out[2] * out[3];
		lau.held[b][k] = lau.ver[k];
	}
	lau.live[b] = true;
	lau.skew[b] = skew;
	lau.wipe[b] = false;	/* a buffer that held nothing needed no wipe: the flag must not make the next refresh wipe it */
	return area;
}

/* the launcher's pixels out of buffer b: the page covers all of it, straight or through the matrix */
static void lau_wipe(int b)
{
	memset(tv.map[b], 0, (size_t)tv.pitch * tv.h);
	memset(lau.held[b], 0, sizeof(lau.held[b]));
	lau.live[b] = lau.wipe[b] = false;
}

/* does buffer b lack a tile in its current version? */
static bool lau_stale(int b)
{
	int box[TILES][4], n = osd_launcher_bands(&canvas, &lau.l, box);

	for (int k = 0; k < n; k++)
		if (box[k][2] && box[k][3] && lau.held[b][k] != lau.ver[k])
			return true;
	return false;
}

/* the page's new rows into buffer b, as a band: LAU_MARGIN rows of the neighbours around it for the sampling, only the panel
 * pixels whose source row lies in the band written (the same reasoning as the launcher's bands, lau_put) */
static int page_put(int b, bool skew)
{
	int area = 0;

	for (int i = 0; i < PAGE_RANGES; i++) {
		int y0 = page.dirty[b][i][0], y1 = page.dirty[b][i][1], r[4], out[4];
		int x0 = page.dirty[b][i][2] > 0 ? page.dirty[b][i][2] : 0, x1 = page.dirty[b][i][3] < canvas.w ? page.dirty[b][i][3] : canvas.w;

		if (y0 >= y1 || x0 >= x1)
			continue;
		r[0] = x0 > LAU_MARGIN ? x0 - LAU_MARGIN : 0;
		r[1] = y0 > LAU_MARGIN ? y0 - LAU_MARGIN : 0;
		r[2] = (x1 + LAU_MARGIN < canvas.w ? x1 + LAU_MARGIN : canvas.w) - r[0];
		r[3] = (y1 + LAU_MARGIN < canvas.h ? y1 + LAU_MARGIN : canvas.h) - r[1];
		if (skew) {
			/* A panel pixel whose source row is s reads rows floor(s) and floor(s) + 1, so the rows y0..y1-1 reach the pixels
			 * with s in (y0 - 1, y1): those are written, a half row more on each side than the band tiles (y0 - 0.5, y1 - 0.5).
			 * The neighbours' pixels they read are the page's own, so what is written is what a whole put writes. */
			double xr[2] = { x0 ? x0 - 1 : -1, x1 < canvas.w ? x1 : canvas.w };	/* the columns the same way; the canvas' own edges keep their fade */
			double yr[2] = { y0 ? y0 - 1 : -1, y1 < canvas.h ? y1 : canvas.h };

			put_warped(tv.map[b], r, xr, yr, out);
		} else {
			put_straight(tv.map[b], r, out);
		}
		area += out[2] * out[3];
	}
	rows_set(page.dirty[b], 0, 0);
	page.live[b] = true;
	page.skew[b] = skew;
	return area;
}

/* more than a third of the panel's rows still to be put into the buffer the next refresh draws into: after a whole page was
 * shown (the buffer on the panel got it), the other one owes it too - and would take it at the next key, a key's worth late */
static bool page_owes_much(void)
{
	int rows = 0;

	for (int i = 0; i < PAGE_RANGES; i++)
		rows += page.dirty[tv.next][i][1] > page.dirty[tv.next][i][0] ? page.dirty[tv.next][i][1] - page.dirty[tv.next][i][0] : 0;
	return page.open && rows * 3 > canvas.h;
}

/* the page's pixels out of buffer b: the whole buffer (through the matrix they are everywhere), and all of it again to put */
static void page_wipe(int b)
{
	memset(tv.map[b], 0, (size_t)tv.pitch * tv.h);
	page.live[b] = false;
	rows_set(page.dirty[b], 0, page.open ? canvas.h : 0);
}

static void buf_sync(int fd, unsigned long long flags)
{
	struct dma_buf_sync s = { flags };

	ioctl(fd, DMA_BUF_IOCTL_SYNC, &s);	/* a memfd in the host tests says ENOTTY: nothing to sync there */
}

/* the buffer that is not shown, brought up to date in the idle time after a refresh: the next key then finds the page in it and
 * puts the two tiles it changes, instead of the page (an opaque page over a keystone is two million pixels through the matrix). */
static void lau_prefill(void)
{
	int b = tv.next;
	bool skew = last.skew;
	double t0 = now_s();
	int px;

	if (!lau.open || tv.fd < 0 || !tv.shown || !lau_stale(b))
		return;
	buf_sync(tv.dmabuf[b], DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE);
	if (lau.live[b] && (lau.wipe[b] || lau.skew[b] != skew))
		lau_wipe(b);
	px = lau_put(b, skew);
	buf_sync(tv.dmabuf[b], DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE);
	if (trace)
		info("trace: prefill of buffer %d took %.1f ms (%d pixels, %s)", b, (now_s() - t0) * 1e3, px, skew ? "pre-distorted" : "copied");
}

/* --- one refresh: compose, put, show ------------------------------------------------------------------------ */

static void refresh(void)
{
	char answer[128];
	int box[2][4], out[2][4] = { { 0 } }, b, area = 0;
	bool warped, skew;
	double t0;

	osd_waiting = true;
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
	if (lau.live[b] && (lau.wipe[b] || !lau.open || lau.skew[b] != skew))
		lau_wipe(b);	/* closed, a new geometry, or the picture under it turned warped or straight */
	if (page.live[b] && (!page.open || page.skew[b] != skew))
		page_wipe(b);	/* the page is gone, or the picture under it turned warped or straight */
	for (int r = 0; r < 2; r++)	/* what this buffer showed before */
		for (int y = tv.box[b][r][1]; y < tv.box[b][r][1] + tv.box[b][r][3]; y++)
			memset((char *)tv.map[b] + (size_t)y * tv.pitch + (size_t)tv.box[b][r][0] * 4, 0,
			       (size_t)tv.box[b][r][2] * 4);
	last.clear = (now_s() - t0) * 1e3;
	t0 = now_s();
	for (int r = 0; r < 2; r++) {
		if (!box[r][2] || !box[r][3] || lau.open)	/* over the page they ride in its tiles */
			continue;
		if (skew)
			put_warped(tv.map[b], box[r], NULL, NULL, out[r]);
		else
			put_straight(tv.map[b], box[r], out[r]);
		area += out[r][2] * out[r][3];
	}
	if (lau.open)
		area += lau_put(b, skew);
	if (page.open)
		area += page_put(b, skew);
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
		osd_waiting = strstr(answer, "waiting") != NULL;
		if (trace)
			info("trace: command %.4f, show answered %.4f (%.1f ms; draw %.1f, put %.1f, show %.1f)", t_cmd, real_s(),
			     (real_s() - t_cmd) * 1e3, last.draw, last.put, (now_s() - t0) * 1e3);
	} else if (tv.fd >= 0) {
		warn("h713-tv refused the overlay: %s", answer);
	}
	last.show = (now_s() - t0) * 1e3;
	if (lau.open)
		lau.prefill_at = now_s() + PREFILL_S;
	if (last.draw + last.ask + last.clear + last.put + last.show > 50)
		info("refresh took %.0f ms: draw %.1f, ask %.1f, clear %.1f, %s %.1f (%d pixels), show %.1f",
		     last.draw + last.ask + last.clear + last.put + last.show, last.draw, last.ask, last.clear,
		     skew ? "pre-distort" : "copy", last.put, area, last.show);
}

/* --- the control socket ------------------------------------------------------------------------------------- */

/*
 * "launcher SEL;NOW;[>]icon:label;..." opens the launcher (or defines it anew): SEL the chosen row, NOW the header's
 * second half ("HDMI 1080p60"), then the rows - a ">" in front puts a row in the group at the foot, which comes last.
 * "launcher SEL" moves the selection, "launcher close" closes it. "ok unseen" when nothing can be seen (no signal:
 * the console; no h713-tv): then it is not open and the caller does not take the keys from anybody.
 * H713_OSD_FONT is the font file (libh713osd's default is the image's Quicksand).
 */
static bool launcher_cmd(const char *args, char *reply, size_t n)
{
	char buf[LINE], answer[64], *f[BANDS + 1], *p = buf, *t;
	int k = 0, sel, rows = 0;
	bool end = false;

	snprintf(buf, sizeof(buf), "%s", args + strspn(args, " "));
	if (!strcmp(buf, "close")) {
		lau.open = false;
		lau.prefill_at = 0;
		osd_clear(&canvas);		/* the page was drawn all over it: a volume strip next must not find the ground under it */
		memset(cbox, 0, sizeof(cbox));
		snprintf(reply, n, "ok\n");
		return true;
	}
	if (page.open) {
		snprintf(reply, n, "error the page is open\n");
		return false;
	}
	while (k < BANDS + 1 && (t = strsep(&p, ";")))
		f[k++] = t;
	if (!k || sscanf(f[0], "%d", &sel) != 1) {
		snprintf(reply, n, "error usage: launcher SEL;NOW;[>]icon:label;... | launcher SEL | launcher close\n");
		return false;
	}
	if (k == 1) {		/* a move: two bands change */
		if (!lau.open) {
			snprintf(reply, n, "error the launcher is not open\n");
			return false;
		}
		sel = sel < 0 ? 0 : sel >= lau.l.n ? lau.l.n - 1 : sel;
		if (sel != lau.l.sel) {
			lau_dirty(1 + lau.l.sel);
			lau_dirty(1 + sel);
			lau.l.sel = sel;
		}
		snprintf(reply, n, "ok\n");
		return true;
	}
	if (osd_font_open(env("H713_OSD_FONT", OSD_FONT))) {
		snprintf(reply, n, "error no font (%s)\n", env("H713_OSD_FONT", OSD_FONT));
		return false;
	}
	memset(&lau.l, 0, sizeof(lau.l));
	for (int i = 2; i < k; i++, rows++) {
		char *colon;

		if (rows == OSD_LAUNCHER_ROWS) {
			snprintf(reply, n, "error at most %d rows\n", OSD_LAUNCHER_ROWS);
			return false;
		}
		lau.l.row[rows].end = *f[i] == '>';
		t = f[i] + lau.l.row[rows].end;
		if (!(colon = strchr(t, ':')) || (*colon = '\0', (lau.l.row[rows].icon = osd_icon_by_name(t)) < 0) ||
		    (end && !lau.l.row[rows].end)) {
			snprintf(reply, n, "error row %d: icon:label with a known icon, rows at the foot (>) last\n", rows);
			return false;
		}
		end = lau.l.row[rows].end;
		snprintf(lau.label[rows], sizeof(lau.label[rows]), "%s", colon + 1);
		lau.l.row[rows].label = lau.label[rows];
	}
	if (!rows) {
		snprintf(reply, n, "error no rows\n");
		return false;
	}
	lau.l.n = rows;
	lau.l.sel = sel < 0 ? 0 : sel >= rows ? rows - 1 : sel;
	lau.l.head = lau.head;
	snprintf(lau.now, sizeof(lau.now), "%s", f[1]);
	lau.head[0] = '\0';
	if (!tv_claim() || !tv_say("osd picture\n", answer, sizeof(answer)) || !strcmp(answer, "ok none")) {
		lau.open = false;
		snprintf(reply, n, "ok unseen\n");
		return false;
	}
	lau.open = true;
	for (int ti = 0; ti < TILES; ti++)
		lau_dirty(ti);
	lau.wipe[0] = lau.wipe[1] = true;	/* whatever the buffers held of an earlier launcher is not this one */
	snprintf(reply, n, "ok\n");
	return true;
}

/* one command; the answer into reply; true when the picture has to be drawn again */
static bool handle(const char *line, char *reply, size_t n)
{
	if (!strncmp(line, "launcher", 8) && (line[8] == ' ' || !line[8]))
		return launcher_cmd(line + 8, reply, n);
	char a[16] = "", b[16] = "", c[16] = "", d[16] = "", e[16] = "", answer[32];
	int v = 0, k = sscanf(line, "%15s %15s %15s %15s %15s", a, b, c, d, e);
	struct osd_item it = { OSD_VOLUME, 0, 0, 1.0f };
	double stay = seconds;

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
	} else if (k >= 3 && !strcmp(a, "power") && sscanf(b, "%d", &v) == 1 &&
		   (!strcmp(c, "standby") || !strcmp(c, "off"))) {
		/*
		 * The power key's countdown (TODO 2.38), sent by h713-power about ten times a second: "power TENTHS
		 * standby|off [only] [ALPHA%]". Each line keeps it a second, so a dead h713-power leaves nothing
		 * behind. "ok unseen" when nothing can be seen (no signal: the console; no h713-tv): then h713-power
		 * does not wait for a choice nobody sees.
		 */
		const char *opt[2] = { d, e };

		it.kind = OSD_POWER;
		it.value = v;
		it.flags = !strcmp(c, "standby") ? OSD_PWR_STANDBY : 0;
		for (int i = 0; i < 2 && i < k - 3; i++) {
			int pct;

			if (!strcmp(opt[i], "only"))
				it.flags |= OSD_PWR_OFF_ONLY;
			else if (sscanf(opt[i], "%d%%", &pct) == 1)
				it.alpha = pct < 0 ? 0 : pct > 100 ? 1 : pct / 100.0f;
		}
		stay = 1.0;
		if (!tv_claim() || !tv_say("osd picture\n", answer, sizeof(answer)) || !strcmp(answer, "ok none")) {
			want.until = 0;
			snprintf(reply, n, "ok unseen\n");
			return true;
		}
	} else if (k == 1 && !strcmp(a, "pair")) {
		it.kind = OSD_PAIR;	/* "hold Left + Right" after the remote was forgotten (TODO 2.54) */
		stay = 10;
	} else if (k == 1 && !strcmp(a, "hide")) {
		want.until = 0;
		snprintf(reply, n, "ok hidden%s\n", want.muted ? " (the mute badge stays)" : "");
		return true;
	} else if (k == 1 && !strcmp(a, "status")) {
		snprintf(reply, n, "ok status\noverlay         %s\nmuted           %s\nchannel         %s\nmatrix          %s\nstyle           place %s, look %s, scale %.2f, %.1f s\nlauncher        %s\npage            %s\nlast refresh    draw %.1f ms, ask %.1f ms, clear %.1f ms, %s %.1f ms (%d pixels), show %.1f ms\n",
			 want.until > now_s() ? "shown" : "none", want.muted ? "yes (badge)" : "no",
			 tv.fd >= 0 ? (tv.shown ? "claimed, shown" : "claimed") : "not claimed (h713-tv not running, or no event yet)",
			 m_identity ? "identity (straight)" :
			 m_valid ? "from warp.conf (pre-distorted while the picture under it is warped)" : "refused",
			 style.place == OSD_BOTTOM ? "bottom" : style.place == OSD_TOP_RIGHT ? "top-right" : "center",
			 style.look == OSD_PILL ? "pill" : "bare", style.scale, seconds,
			 lau.open ? "open" : "closed", page.open ? "open" : "closed", last.draw, last.ask, last.clear, last.skew ? "pre-distort" : "copy", last.put, last.pixels, last.show);
		return false;
	} else {
		snprintf(reply, n, "error unknown: volume N | mute on|off N | focus up|down [edge] | input console|hdmi | power TENTHS standby|off [only] [ALPHA%%] | pair | launcher ... | hide | status\n");
		return false;
	}
	want.popup = it;
	want.until = now_s() + stay;
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

/* the page's way in: "page open" keeps its connection (the page's life) and answers with the size and one memfd */
static bool page_open_cmd(int fd)
{
	char cbuf[CMSG_SPACE(sizeof(int))] = { 0 }, line[96], answer[64];
	struct iovec io = { line, 0 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = cbuf, .msg_controllen = sizeof(cbuf) };
	const char *err = NULL;
	struct cmsghdr *cm;
	void *map = MAP_FAILED;
	size_t len;
	int mem = -1;

	if (page.open || lau.open)
		err = page.open ? "error the page is open\n" : "error the launcher is open\n";
	else if (!tv_claim() || !tv_say("osd picture\n", answer, sizeof(answer)) || !strcmp(answer, "ok none"))
		err = "ok unseen\n";	/* nothing can be seen: no page, and the caller takes the keys from nobody */
	if (!err) {
		len = (size_t)canvas.stride * canvas.h * 4;
		mem = memfd_create("h713-page", MFD_CLOEXEC);
		if (mem < 0 || ftruncate(mem, (off_t)len) ||
		    (map = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, mem, 0)) == MAP_FAILED)
			err = "error no memory for the page\n";
	}
	if (!err) {
		io.iov_len = (size_t)snprintf(line, sizeof(line), "ok %d %d %d argb8888\n", canvas.w, canvas.h, canvas.stride * 4);
		cm = CMSG_FIRSTHDR(&msg);
		cm->cmsg_level = SOL_SOCKET;
		cm->cmsg_type = SCM_RIGHTS;
		cm->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(cm), &mem, sizeof(int));
		if (sendmsg(fd, &msg, MSG_NOSIGNAL) < 0)
			err = "";
	}
	if (mem >= 0)
		close(mem);
	if (err) {
		if (*err)
			send(fd, err, strlen(err), MSG_NOSIGNAL);
		if (map != MAP_FAILED)
			munmap(map, len);
		close(fd);
		return false;
	}
	page.fd = fd;
	page.px = map;
	page.len = len;
	page.open = true;
	page.blen = 0;
	page.owe = 0;
	rows_set(page.cnew, 0, 0);
	for (int b = 0; b < 2; b++)
		rows_set(page.dirty[b], 0, canvas.h);
	info("page opened: %dx%d", canvas.w, canvas.h);
	return false;
}

static void page_close(void)
{
	if (page.fd >= 0)
		close(page.fd);
	if (page.px)
		munmap(page.px, page.len);
	page.fd = -1;
	page.px = NULL;
	page.open = false;
	page.blen = 0;
	page.owe = 0;
	info("page closed");
}

/* the page's lines: "page show X Y W H" - those rows are new (the answer comes after the refresh), "page hide"; true when
 * the picture is to be drawn again */
static bool page_read(void)
{
	ssize_t got = recv(page.fd, page.buf + page.blen, sizeof(page.buf) - page.blen - 1, MSG_DONTWAIT);
	bool again = false;
	char *nl;

	if (got == 0 || (got < 0 && errno != EAGAIN && errno != EINTR)) {
		page_close();	/* the page's program ended: it is gone from the wall */
		return true;
	}
	if (got > 0)
		page.blen += (size_t)got;
	page.buf[page.blen] = '\0';
	while ((nl = strchr(page.buf, '\n'))) {
		int x, y, w, h;
		size_t used = (size_t)(nl - page.buf) + 1;

		*nl = '\0';
		t_cmd = real_s();
		if (sscanf(page.buf, "page show %d %d %d %d", &x, &y, &w, &h) == 4 && h > 0) {
			int y0 = y < 0 ? 0 : y, y1 = y + h > canvas.h ? canvas.h : y + h;
			/* a width of 0 or less is the whole width (the first version's "page show"s said it no other way) */
			int x0 = w > 0 && x > 0 ? x : 0, x1 = w > 0 && x + w < canvas.w ? x + w : canvas.w;

			if (w > 0 && x + w <= 0)
				x1 = x0;		/* entirely left of the panel: nothing */
			rows_add(page.cnew, y0, y1, x0, x1);
			rows_add(page.dirty[0], y0, y1, x0, x1);
			rows_add(page.dirty[1], y0, y1, x0, x1);
			page.owe++;
			again = true;
		} else if (!strcmp(page.buf, "page hide")) {
			page_close();
			return true;
		} else {
			send(page.fd, "error page show X Y W H | page hide\n", 36, MSG_NOSIGNAL);
		}
		memmove(page.buf, page.buf + used, page.blen - used + 1);
		page.blen -= used;
	}
	if (page.blen >= sizeof(page.buf) - 1)
		page.blen = 0;	/* a line that does not end: dropped */
	return again;
}

static void page_answer(void)
{
	while (page.owe > 0 && page.fd >= 0) {
		const char *r = osd_waiting ? "ok waiting\n" : "ok\n";

		if (send(page.fd, r, strlen(r), MSG_NOSIGNAL) < 0) {
			page_close();
			break;
		}
		page.owe--;
	}
	page.owe = 0;
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
	t_cmd = real_s();
	line[got] = '\0';
	line[strcspn(line, "\r\n")] = '\0';
	if (!strcmp(line, "page open"))
		return page_open_cmd(fd);	/* the connection stays: it is the page's life */
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

/* What lies under a shown overlay can change without an event of ours: the signal comes back over the ring and
 * the warp takes over a second later, or the warp is switched off and on. A badge drawn for the one stays put
 * over the other (11.10., G-EU: straight over the warped picture). So while something is to be seen over a
 * keystone, h713-tv is asked every WATCH_S, and a change of what it says draws the picture again. */
#define WATCH_S 0.25
static double watch_at;			/* the next question; 0: none due */

static bool watching(void)
{
	return tv.fd >= 0 && tv.shown && (want.muted || lau.open || page.open || want.until > now_s()) && m_valid && !m_identity;
}

/* true when the picture under the overlay no longer matches the way it was drawn */
static bool picture_changed(void)
{
	char answer[64];
	bool skew;

	watch_at = 0;
	if (!tv_say("osd picture\n", answer, sizeof(answer)) || !strcmp(answer, "ok none"))
		return false;		/* gone (claimed again at the next event), or no picture: nothing is seen */
	skew = !strcmp(answer, "ok warped");
	if (skew == last.skew)
		return false;
	info("the picture under the overlay is %s now -- drawn again", skew ? "warped" : "straight");
	return true;
}

/* the next thing to do: an overlay's end, or - while something is to be seen and h713-tv is not claimed (it
 * restarted, after a standby too) - the next claim, so the mute badge comes back without a key; or the next
 * question what lies under it */
static void arm(int tfd)
{
	struct itimerspec its = { 0 };
	double next = want.until > 0 ? want.until : 0, dt;

	if (tv.fd < 0 && (want.muted || lau.open || page.open || want.until > 0)) {
		double r = tv.retry > now_s() ? tv.retry : now_s() + 1.0;

		if (!next || r < next)
			next = r;
	}
	if (lau.open && lau.prefill_at > 0 && (!next || lau.prefill_at < next))
		next = lau.prefill_at;
	if (lau.open) {		/* the clock in the header: the next full minute */
		double nm = now_s() + 60 - (double)(time(NULL) % 60) + 0.1;

		if (!next || nm < next)
			next = nm;
	}
	if (watching()) {
		if (!watch_at)
			watch_at = now_s() + WATCH_S;
		if (!next || watch_at < next)
			next = watch_at;
	} else {
		watch_at = 0;
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
	struct pollfd p[6];
	sigset_t mask;
	char dir[256], *slash, ev[4096];
	int lfd, tfd, ifd, sfd;

	conf_load();
	geom_load();
	if (tv_mute() == 1)	/* muted before this start: the badge, without waiting for a key */
		want.muted = true;
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
	if (want.muted)
		refresh();
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
		p[5] = (struct pollfd){ page.fd, POLLIN, 0 };	/* -1: ignored */
		if (poll(p, 6, -1) < 0 && errno != EINTR)
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
		if (p[5].revents && page.fd >= 0)
			again |= page_read();
		if (p[1].revents) {
			uint64_t ticks;

			if (read(tfd, &ticks, sizeof(ticks)) > 0) {
				if (want.until && want.until <= now_s()) {
					want.until = 0;
					again = true;
				}
				if (tv.fd < 0 && (want.muted || lau.open || page.open || want.until))
					again = true;	/* the claim again */
				if (lau.open && lau_clock_changed())
					again = true;	/* a new minute: the header is drawn again */
				if (lau.prefill_at && lau.prefill_at <= now_s()) {
					lau.prefill_at = 0;
					if (!again)
						lau_prefill();	/* idle: the buffer that is not shown gets the page */
				}
				if (!again && watch_at && watch_at <= now_s() && watching())
					again = picture_changed();
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
		page_answer();
		if (again && page_owes_much())
			refresh();	/* the page has its answer: the other buffer takes its share now, not at the next key */
		arm(tfd);
	}
	if (page.fd >= 0)
		page_close();
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
	fake_clock = env("H713_OSD_CLOCK", "");
	trace = *env("H713_OSD_TRACE", "") == '1';
	if (argc >= 2 && !strcmp(argv[1], "run"))
		return run();
	if (argc >= 3 && !strcmp(argv[1], "ctl"))
		return client(argc - 2, argv + 2);
	fprintf(stderr, "usage: h713-osd run | h713-osd ctl volume N | mute on|off N | focus up|down [edge] | input console|hdmi | power TENTHS standby|off [only] [ALPHA%%] | pair | launcher SEL;NOW;[>]icon:label;... | launcher close | hide | status\n");
	return 2;
}
