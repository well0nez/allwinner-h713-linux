/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* accept4, strtok_r, O_CLOEXEC */
/*
 * The control socket and the client (design AP2d M3), modelled on h713-tv's:
 * /run/h713-warp/ctl, SOCK_STREAM, 0660, one instance behind an flock on
 * /run/h713-warp/lock, one line in, a few lines out, connection closed. Every
 * answer starts with "ok" or "error", so the client's exit code is decided by
 * the first word and nothing has to be parsed further. The verbs are
 * status; on | off (run time only: neither changes the "warp =" line the
 * daemon starts with); keystone set|nudge CORNER AXIS VALUE and keystone
 * reset, each clamped and saved at once; test grid|border|off, which draws a
 * pattern instead of the capture so a corner can be aimed with no source
 * plugged in. "keystone nudge" is the one command a remote control has to
 * reach: it is the one-for-one replacement of the vendor's DPAD path
 * (CorrectionActivity.calculationValue -> setkeystoneValue, AP2 section 1).
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>
#include <poll.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>

#include "warp.h"

#define CTL_DEADLINE_MS	500

void control_lock(struct control *c, const char *path)
{
	char dir[108], lock[128], *slash;

	c->lfd = -1;
	c->lock_fd = -1;
	c->cfd = -1;
	c->path = path;
	if (strlen(path) >= sizeof(((struct sockaddr_un *)0)->sun_path))
		fail("%s: socket path longer than %zu characters", path,
		     sizeof(((struct sockaddr_un *)0)->sun_path) - 1);
	snprintf(dir, sizeof(dir), "%s", path);
	slash = strrchr(dir, '/');
	if (!slash || slash == dir)
		fail("%s: the socket needs a directory", path);
	*slash = '\0';
	if (mkdir(dir, 0755) && errno != EEXIST)
		fail("%s: %s", dir, strerror(errno));
	snprintf(lock, sizeof(lock), "%s/lock", dir);
	c->lock_fd = open(lock, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
	if (c->lock_fd < 0)
		fail("%s: %s -- without the single-instance lock h713-warp does not start",
		     lock, strerror(errno));
	if (flock(c->lock_fd, LOCK_EX | LOCK_NB))
		fail("%s: another instance of h713-warp is already running", lock);
}

void control_listen(struct control *c)
{
	struct sockaddr_un addr;

	c->lfd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
	if (c->lfd < 0) {
		warn("socket: %s -- no control channel", strerror(errno));
		return;
	}
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", c->path);
	unlink(c->path);
	if (bind(c->lfd, (struct sockaddr *)&addr, sizeof(addr)) ||
	    chmod(c->path, 0660) || listen(c->lfd, 4)) {
		warn("%s: %s -- no control channel", c->path, strerror(errno));
		close(c->lfd);
		c->lfd = -1;
		return;
	}
	info("control         %s (h713-warp ctl help)", c->path);
}

void control_close(struct control *c)
{
	if (c->cfd >= 0)
		close(c->cfd);
	c->cfd = -1;
	if (c->lock_fd >= 0)
		close(c->lock_fd);
	c->lock_fd = -1;
	if (c->lfd < 0)
		return;
	close(c->lfd);
	unlink(c->path);
	c->lfd = -1;
}

/* A whole decimal number in lo..hi, as cmd_keystone takes one: "50abc", "4x" and
 * "" are not numbers (atoi took their leading digits, Prüfstand 05.10. 2.8). */
static bool number(const char *s, long lo, long hi, int *out)
{
	char *end;
	long x;

	errno = 0;
	x = strtol(s, &end, 10);
	if (end == s || *end || errno || x < lo || x > hi)
		return false;
	*out = (int)x;

	return true;
}

static void save(struct runtime *r, struct textbuf *t)
{
	char why[WARP_WHY];

	if (!conf_write(&r->conf, why, sizeof(why)))
		text_add(t, "   note: not saved: %s\n", why);
}

static void cmd_keystone(struct runtime *r, struct textbuf *t, const char *verb,
			 const char *corner, const char *axis, const char *value)
{
	int before[WARP_KEYS], k, want, got;
	char *end;
	long x;

	if (!corner || !axis || !value) {
		text_add(t, "error keystone %s needs CORNER AXIS VALUE (CORNER tl tr bl br, AXIS x y)\n",
			 verb);
		return;
	}
	k = warp_key(corner, axis);
	if (k < 0) {
		text_add(t, "error keystone %s does not know the corner \"%s\" axis \"%s\" (tl tr bl br, x y)\n",
			 verb, corner, axis);
		return;
	}
	errno = 0;
	x = strtol(value, &end, 10);
	if (end == value || *end || errno || x < -1000 || x > 1000) {
		text_add(t, "error \"%s\" is not a per-mille number (set: 0..1000, nudge: -1000..1000)\n",
			 value);
		return;
	}
	memcpy(before, r->conf.v, sizeof(before));
	want = !strcmp(verb, "set") ? (int)x : r->conf.v[k] + (int)x;
	got = warp_clamp_key(r->conf.v, k, want);
	if (r->pattern == PATTERN_MASK)
		r->mark_corner = k / 2;
	text_add(t, "ok %s = %d%s\n", warp_key_name[k], got,
		 got == want ? "" : " (clamped against the corner at the other end)");
	if (memcmp(before, r->conf.v, sizeof(before))) {
		warp_solve(r);
		save(r, t);
		warp_apply(r);
	}
	if (r->state != WARP_ON && r->why[0])
		text_add(t, "   note: %s\n", r->why);
}

static void cmd_test(struct runtime *r, struct textbuf *t, const char *what,
		     const char *corner)
{
	int pattern;

	if (!what || !strcasecmp(what, "off"))
		pattern = PATTERN_NONE;
	else if (!strcasecmp(what, "grid"))
		pattern = PATTERN_GRID;
	else if (!strcasecmp(what, "border"))
		pattern = PATTERN_BORDER;
	else if (!strcasecmp(what, "mask"))
		pattern = PATTERN_MASK;
	else {
		text_add(t, "error test knows mask, grid, border and off, not \"%s\"\n", what);
		return;
	}
	if (corner) {
		int k = warp_key(corner, "x");

		if (k < 0) {
			text_add(t, "error test mask takes a corner tl tr bl br, not \"%s\"\n", corner);
			return;
		}
		r->mark_corner = k / 2;
	}
	if (pattern != r->pattern) {
		/* the pattern needs no capture and the capture no pattern: the
		 * GPU path is rebuilt either way - not under a Wayland client,
		 * whose claim the pattern simply draws over
		 */
		if (r->state == WARP_ON && r->src == SRC_RING)
			warp_disengage(r, "the test pattern changed");
		r->pattern = pattern;
		warp_apply(r);
	}
	if (pattern == PATTERN_MASK)
		text_add(t, "ok test mask%s%s%s\n", r->mark_corner >= 0 ? " " : "",
			 r->mark_corner >= 0 ? warp_corner_name[r->mark_corner] : "",
			 r->state == WARP_ON ? "" : " -- nothing is drawn yet");
	else
		text_add(t, "ok test %s%s\n",
			 pattern == PATTERN_GRID ? "grid" :
			 pattern == PATTERN_BORDER ? "border" : "off",
			 r->state == WARP_ON ? "" : " -- nothing is drawn yet");
	if (r->state != WARP_ON && r->why[0])
		text_add(t, "   note: %s\n", r->why);
}

static void cmd_help(struct textbuf *t)
{
	text_add(t, "ok commands\n"
		 "  status                     the warp, the eight values, the source, the panel,\n"
		 "                             the renderer and the last hundred frames\n"
		 "  on | off                   run the warp or leave it; run time only, the state\n"
		 "                             at the next start is \"warp =\" in " WARP_CONF "\n"
		 "  keystone set CORNER AXIS VALUE    absolute, 0..1000 per-mille, inward\n"
		 "  keystone nudge CORNER AXIS DELTA  relative, -1000..1000\n"
		 "  keystone reset             all eight corners to 0 (the identity)\n"
		 "                             CORNER: tl tr bl br as the picture stands on the\n"
		 "                             wall; AXIS: x y. Every change is saved at once\n"
		 "  hold on|off                draw a slot one vsync late (on, the default): the\n"
		 "                             firmware hands a slot on before it is written to\n"
		 "                             the end; off is the old timing, for the check\n"
		 "  dump PATH                  the last drawn frame's luma plane as a PGM file\n"
		 "  check [FRAMES]             the self-check: FRAMES frames (300) drawn twice, 4 ms\n"
		 "                             apart (12 with hold off), 32 rows compared; the result\n"
		 "                             on the status line and one journal line per difference\n"
		 "  zoom [PERCENT]             the screen zoom, 10..100 (100 = none): the picture\n"
		 "                             smaller about its own centre, inside the keystone (S7)\n"
		 "  edge [N]                   the soft border of the warped picture in panel pixels:\n"
		 "                             0 = a hard edge, 4 = the vendor's (the default); saved\n"
		 "  mode [MODE]                the mount: front, rear (mirrored left-right for a\n"
		 "                             screen lit from behind), ceiling (turned over) or\n"
		 "                             rear-ceiling; saved; the corner names stay the wall's\n"
		 "  test mask [CORNER]         the calibration picture of the manual keystone,\n"
		 "                             CORNER tl tr bl br marked; keystone set/nudge marks\n"
		 "                             the corner it touches while the mask is up\n"
		 "  test grid|border|off       draw a pattern instead of the capture, to aim a\n"
		 "                             corner with no source plugged in\n"
		 "  picture                    ok N: the pictures of the Wayland client on the panel\n"
		 "                             since its window was mapped (also those held under an\n"
		 "                             opaque page); error: no client picture on the panel\n"
		 "  help                       this list\n"
		 "With all eight values 0 and mode front the GPU is not started at all and\n"
		 "h713-tv shows the capture ring as it does without this service.\n"
		 "A Wayland client (cage: WAYLAND_DISPLAY=" WAYLAND_SOCKET ") is drawn through the\n"
		 "GPU whenever h713-tv's \"source\" lets it (h713-tv ctl source client|auto); under\n"
		 "\"client\" the last picture stays between two programs, never the ring. Under an\n"
		 "opaque page (h713-tv's \"note cover on\") nothing is drawn.\n"
		 "The answer starts with ok or error; socket %s (root, 0660)\n", WARP_SOCKET);
}

static void dispatch(struct runtime *r, char *line, struct textbuf *t)
{
	char *save_ptr = NULL, *cmd, *a1, *a2, *a3;

	cmd = strtok_r(line, " \t", &save_ptr);
	a1 = strtok_r(NULL, " \t", &save_ptr);
	a2 = strtok_r(NULL, " \t", &save_ptr);
	a3 = strtok_r(NULL, " \t", &save_ptr);
	if (!cmd) {
		text_add(t, "error empty (h713-warp ctl help)\n");
	} else if (!strcmp(cmd, "status") || !strcmp(cmd, "st")) {
		warp_status(r, t->b + t->l, t->n - t->l);
		t->l += strlen(t->b + t->l);
	} else if (!strcmp(cmd, "picture")) {
		long n = server_pictures(r->srv);

		if (n < 0)
			text_add(t, "error no picture of a Wayland client on the panel\n");
		else
			text_add(t, "ok %ld pictures of the Wayland client on the panel since its window was mapped%s\n", n,
				 warp_paused(r) ? " (an opaque page hides them)" : "");
	} else if (!strcmp(cmd, "on")) {
		r->on = true;
		warp_apply(r);
		text_add(t, "ok on%s%s\n", r->state == WARP_ON ? "" : " -- ",
			 r->state == WARP_ON ? "" : r->why);
		/* "warp = on" in the file: the daemon comes up the way it was
		 * left, like every other change (Marco, 23.09.: the warp was
		 * on, the file still said off, the reboot came up without it) */
		r->conf.start_on = true;
		save(r, t);
	} else if (!strcmp(cmd, "off")) {
		r->on = false;
		r->conf.start_on = false;
		save(r, t);
		warp_apply(r);
		text_add(t, "ok off -- h713-tv is on its own mode again\n");
	} else if (!strcmp(cmd, "keystone") && a1 &&
		   (!strcmp(a1, "set") || !strcmp(a1, "nudge"))) {
		char *a4 = strtok_r(NULL, " \t", &save_ptr);

		cmd_keystone(r, t, a1, a2, a3, a4);
	} else if (!strcmp(cmd, "keystone") && a1 && !strcmp(a1, "reset")) {
		memset(r->conf.v, 0, sizeof(r->conf.v));
		warp_solve(r);
		save(r, t);
		warp_apply(r);
		text_add(t, "ok keystone reset -- all eight corners 0, %s\n",
			 !r->on ? "the warp is off" :
			 r->conf.mode != MODE_FRONT ? "the GPU keeps mirroring for the mount" :
			 "h713-tv is back on the ring (the identity needs no GPU)");
	} else if (!strcmp(cmd, "keystone")) {
		text_add(t, "error keystone takes set, nudge or reset (h713-warp ctl help)\n");
	} else if (!strcmp(cmd, "hold")) {
		if (!a1 || (strcmp(a1, "on") && strcmp(a1, "off"))) {
			text_add(t, "error hold takes on or off\n");
		} else {
			r->hold = !strcmp(a1, "on");
			if (!r->hold && r->source.held >= 0) {
				source_queue(&r->source, r->source.held);
				r->source.held = -1;
			}
			text_add(t, "ok hold %s\n", a1);
		}
	} else if (!strcmp(cmd, "dump")) {
		char why[WARP_WHY];
		int last = (r->target + WARP_TARGETS - 1) % WARP_TARGETS;

		if (r->state != WARP_ON)
			text_add(t, "error dump needs the warp on\n");
		else if (!a1)
			text_add(t, "error dump takes a file path\n");
		else if (gl_dump_luma(last, a1, why, sizeof(why)))
			text_add(t, "ok dump %s -- the luma plane of the last drawn frame, PGM%s\n", a1,
				 why[0] ? " (the readback came packed, one byte a pixel)" : "");
		else
			text_add(t, "error dump: %s\n", why);
	} else if (!strcmp(cmd, "trace")) {
		int n = 300;

		if (a1 && !number(a1, 0, 100000, &n)) {
			text_add(t, "error trace takes a dequeue count 0..100000\n");
		} else {
			r->check.trace = n;
			r->check.trace_gpu = a2 && !strcmp(a2, "gpu");
			text_add(t, "ok trace %d dequeues to the journal%s\n", r->check.trace,
				 r->check.trace_gpu ? " (with the GPU's time from the fence)" : "");
		}
	} else if (!strcmp(cmd, "check")) {
		int f = 300;

		if (a1 && !number(a1, 1, 100000, &f)) {
			text_add(t, "error check takes a frame count 1..100000\n");
		} else if (r->state != WARP_ON || r->pattern != PATTERN_NONE || r->src != SRC_RING) {
			text_add(t, "error check needs the warp on with the capture\n");
		} else {
			r->check.want = f;
			r->check.frames = r->check.differing = r->check.rows_max = r->check.late = 0;
			r->check.row_lo = r->check.row_hi = -1;
			text_add(t, "ok check %d frames -- see the journal or \"ctl status\"\n", f);
		}
	} else if (!strcmp(cmd, "zoom")) {
		int z;

		if (!a1) {
			text_add(t, "ok zoom %d\n", r->conf.zoom);
		} else if (!number(a1, 10, 100, &z)) {
			text_add(t, "error zoom takes a percentage 10..100 (100 = none)\n");
		} else {
			r->conf.zoom = z;
			warp_solve(r);
			save(r, t);
			warp_apply(r);
			text_add(t, "ok zoom %d -- the picture at %d per cent, about its centre inside the keystone\n",
				 z, z);
		}
	} else if (!strcmp(cmd, "edge")) {
		int e;

		if (!a1) {
			text_add(t, "ok edge %d\n", r->conf.edge);
		} else if (!number(a1, 0, EDGE_MAX, &e)) {
			text_add(t, "error edge takes a width in panel pixels 0..%d (0 = a hard edge, %d = the vendor's)\n",
				 EDGE_MAX, EDGE_DEFAULT);
		} else {
			r->conf.edge = e;
			gl_edge(warp_edge_for(r));	/* the next drawn frame has it; no rebuild */
			save(r, t);
			text_add(t, "ok edge %d%s\n", e,
				 e ? " -- the picture fades into the border over that many pixels" : " -- a hard edge");
		}
	} else if (!strcmp(cmd, "mode") && a1 && warp_mode_by_name(a1) < 0) {
		text_add(t, "error mode takes front, rear, ceiling or rear-ceiling, not \"%s\"\n", a1);
	} else if (!strcmp(cmd, "mode")) {
		int m = a1 ? warp_mode_by_name(a1) : r->conf.mode;
		bool moved = m != r->conf.mode;

		if (moved) {
			warp_remount(r->conf.mode, m, r->conf.v);
			r->conf.mode = m;
			warp_solve(r);
			save(r, t);
			warp_apply(r);
		}
		text_add(t, "ok mode %s%s\n", warp_mode_name[m],
			 m == MODE_FRONT ? "" : " -- mirrored for the mount, the GPU runs even with all eight corners 0");
		if (moved)
			text_add(t, "   the corners follow the housing: tl %d,%d tr %d,%d bl %d,%d br %d,%d\n",
				 r->conf.v[0], r->conf.v[1], r->conf.v[2], r->conf.v[3],
				 r->conf.v[4], r->conf.v[5], r->conf.v[6], r->conf.v[7]);
		if (r->state != WARP_ON && r->why[0])
			text_add(t, "   note: %s\n", r->why);
	} else if (!strcmp(cmd, "test")) {
		cmd_test(r, t, a1, a2);
	} else if (!strcmp(cmd, "help")) {
		cmd_help(t);
	} else {
		text_add(t, "error unknown: %s (h713-warp ctl help)\n", cmd);
	}
}

static int time_left(const struct timespec *t0)
{
	struct timespec t;
	long used;

	clock_gettime(CLOCK_MONOTONIC, &t);
	used = (t.tv_sec - t0->tv_sec) * 1000 + (t.tv_nsec - t0->tv_nsec) / 1000000;

	return used >= CTL_DEADLINE_MS ? 0 : (int)(CTL_DEADLINE_MS - used);
}

int control_left(const struct control *c)
{
	return c->cfd < 0 ? -1 : time_left(&c->t0);
}

/* The line is in (or the deadline passed, or the client hung up): answer, hang up. */
static void answer(struct control *c, struct runtime *r)
{
	char buf[4096];
	struct textbuf t = { buf, sizeof(buf), 0 };
	struct pollfd pf = { .fd = c->cfd, .events = POLLOUT };
	ssize_t n;
	size_t off = 0;
	int left;

	c->line[c->off] = '\0';
	c->line[strcspn(c->line, "\r\n")] = '\0';
	if (!c->off)
		text_add(&t, "error nothing received\n");
	else
		dispatch(r, c->line, &t);
	while (off < t.l) {
		n = send(c->cfd, t.b + off, t.l - off, MSG_NOSIGNAL);
		if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
			if ((left = time_left(&c->t0)) <= 0 || poll(&pf, 1, left) <= 0)
				break;
			continue;
		}
		if (n <= 0)
			break;
		off += (size_t)n;
	}
	close(c->cfd);
	c->cfd = -1;
}

/* One client: read a line, answer, hang up. One deadline for the whole
 * exchange, not per read -- a client that trickles bytes must not hold the
 * render loop (h713-tv S12 R2). Nor does one that sends no newline: its line
 * waits here between two turns of the loop instead of in a poll() of its own,
 * which held the loop 500 ms (Prüfstand 05.10. 2.9). Called when the listening
 * socket or the pending client is readable, and when control_left() ran out;
 * one client at a time, the next one waits in the listen backlog.
 */
void control_serve(struct control *c, struct runtime *r)
{
	ssize_t n;

	if (c->cfd < 0) {
		c->cfd = accept4(c->lfd, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
		if (c->cfd < 0)
			return;
		c->off = 0;
		clock_gettime(CLOCK_MONOTONIC, &c->t0);
	}
	while (c->off < sizeof(c->line) - 1) {
		n = read(c->cfd, c->line + c->off, sizeof(c->line) - 1 - c->off);
		if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
			if (time_left(&c->t0) > 0)
				return;		/* the rest of the line comes later */
			break;
		}
		if (n <= 0)
			break;
		c->off += (size_t)n;
		if (memchr(c->line, '\n', c->off))
			break;
	}
	answer(c, r);
}

/* h713-warp ctl COMMAND [ARG...] */
int client(int argc, char **argv, const char *path)
{
	struct sockaddr_un addr;
	char line[WARP_LINE], buf[4096];
	size_t len = 0;
	ssize_t n;
	int fd, i, rc;

	line[0] = '\0';
	for (i = 0; i < argc; i++) {
		int k = snprintf(line + len, sizeof(line) - len, "%s%s",
				 len ? " " : "", argv[i]);

		if (k < 0 || (size_t)k >= sizeof(line) - len - 1)
			fail("command too long (at most %zu characters)",
			     sizeof(line) - 2);
		len += (size_t)k;
	}
	if (!len)
		len = (size_t)snprintf(line, sizeof(line), "help");
	line[len++] = '\n';
	line[len] = '\0';

	fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (fd < 0)
		fail("socket: %s", strerror(errno));
	if (strlen(path) >= sizeof(addr.sun_path))
		fail("%s: socket path longer than %zu characters", path,
		     sizeof(addr.sun_path) - 1);
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
	if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)))
		fail("%s: %s -- is h713-warp running? (systemctl status h713-warp)",
		     path, strerror(errno));
	if (send(fd, line, strlen(line), MSG_NOSIGNAL) < 0)
		fail("sending: %s", strerror(errno));
	rc = 1;
	len = 0;
	while ((n = read(fd, buf, sizeof(buf) - 1)) > 0) {
		buf[n] = '\0';
		if (!len)
			rc = strncmp(buf, "ok", 2) ? 1 : 0;
		fputs(buf, stdout);
		len += (size_t)n;
	}
	close(fd);
	if (!len)
		fail("no answer");

	return rc;
}
