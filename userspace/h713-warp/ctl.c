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
	if (c->lock_fd >= 0)
		close(c->lock_fd);
	c->lock_fd = -1;
	if (c->lfd < 0)
		return;
	close(c->lfd);
	unlink(c->path);
	c->lfd = -1;
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

static void cmd_test(struct runtime *r, struct textbuf *t, const char *what)
{
	int pattern;

	if (!what || !strcasecmp(what, "off"))
		pattern = PATTERN_NONE;
	else if (!strcasecmp(what, "grid"))
		pattern = PATTERN_GRID;
	else if (!strcasecmp(what, "border"))
		pattern = PATTERN_BORDER;
	else {
		text_add(t, "error test knows grid, border and off, not \"%s\"\n", what);
		return;
	}
	if (pattern != r->pattern) {
		/* the pattern needs no capture and the capture no pattern: the
		 * GPU path is rebuilt either way
		 */
		if (r->state == WARP_ON)
			warp_disengage(r, "the test pattern changed");
		r->pattern = pattern;
		warp_apply(r);
	}
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
		 "  zoom [PERCENT]             the screen zoom, 10..100 (100 = none): every corner\n"
		 "                             pulled in by (100 - PERCENT) * 5 per-mille (S7)\n"
		 "  test grid|border|off       draw a pattern instead of the capture, to aim a\n"
		 "                             corner with no source plugged in\n"
		 "  help                       this list\n"
		 "With all eight values 0 the GPU is not started at all and h713-tv shows the\n"
		 "capture ring as it does without this service.\n"
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
	} else if (!strcmp(cmd, "on")) {
		r->on = true;
		warp_apply(r);
		text_add(t, "ok on%s%s\n", r->state == WARP_ON ? "" : " -- ",
			 r->state == WARP_ON ? "" : r->why);
	} else if (!strcmp(cmd, "off")) {
		r->on = false;
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
			 r->on ? "h713-tv is back on the ring (the identity needs no GPU)"
			       : "the warp is off");
	} else if (!strcmp(cmd, "keystone")) {
		text_add(t, "error keystone takes set, nudge or reset (h713-warp ctl help)\n");
	} else if (!strcmp(cmd, "zoom")) {
		int z = a1 ? atoi(a1) : -1;

		if (!a1) {
			text_add(t, "ok zoom %d\n", r->conf.zoom);
		} else if (z < 10 || z > 100) {
			text_add(t, "error zoom takes a percentage 10..100 (100 = none)\n");
		} else {
			r->conf.zoom = z;
			warp_solve(r);
			save(r, t);
			warp_apply(r);
			text_add(t, "ok zoom %d -- every corner pulled in by %d per-mille on top of the keystone\n",
				 z, (100 - z) * 5);
		}
	} else if (!strcmp(cmd, "test")) {
		cmd_test(r, t, a1);
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

/* One client: read a line, answer, hang up. One deadline for the whole
 * exchange, not per read -- a client that trickles bytes must not hold the
 * render loop (h713-tv S12 R2).
 */
void control_serve(struct control *c, struct runtime *r)
{
	char line[WARP_LINE], buf[4096];
	struct textbuf t = { buf, sizeof(buf), 0 };
	struct timespec t0;
	struct pollfd pf;
	ssize_t n = 0, off = 0;
	int fd, left;

	fd = accept4(c->lfd, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
	if (fd < 0)
		return;
	clock_gettime(CLOCK_MONOTONIC, &t0);
	pf.fd = fd;
	pf.events = POLLIN;
	while (off < (ssize_t)sizeof(line) - 1) {
		if ((left = time_left(&t0)) <= 0 || poll(&pf, 1, left) <= 0)
			break;
		n = read(fd, line + off, sizeof(line) - 1 - (size_t)off);
		if (n <= 0)
			break;
		off += n;
		if (memchr(line, '\n', (size_t)off))
			break;
	}
	line[off > 0 ? off : 0] = '\0';
	line[strcspn(line, "\r\n")] = '\0';
	if (off <= 0)
		text_add(&t, "error nothing received\n");
	else
		dispatch(r, line, &t);

	off = 0;
	pf.events = POLLOUT;
	while ((size_t)off < t.l) {
		n = send(fd, t.b + off, t.l - (size_t)off, MSG_NOSIGNAL);
		if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
			if ((left = time_left(&t0)) <= 0 || poll(&pf, 1, left) <= 0)
				break;
			continue;
		}
		if (n <= 0)
			break;
		off += n;
	}
	close(fd);
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
