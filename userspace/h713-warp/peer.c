/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* accept4, strtok_r, O_CLOEXEC */
/*
 * The peer link to h713-tv (design AP2d M4, h713-tv's side A1-A4).
 *
 * h713-tv owns card1 and does the allocating and the committing; this program
 * only renders. The two speak over /run/h713-tv/ctl -- text lines, answers
 * starting with "ok" or "error", exactly like its other commands -- with the
 * file descriptors in SCM_RIGHTS on the same connection:
 *
 *   "warp claim"    -> "ok WIDTH HEIGHT PITCH nv12 COFF" + three dma-buf fds, the
 *                      NV12 dumb buffers of the panel mode
 *   "warp frame N"  -> the out-fence fd travels with the line; h713-tv commits
 *                      buffer N on the video plane (without the ring) with
 *                      IN_FENCE_FD = that fd, and answers "ok" once the
 *                      commit is queued, or "ok busy" when the previous flip
 *                      has not happened yet -- that frame is dropped, which
 *                      is one frame of the wall and not an error
 *   "warp release"  -> "ok"; h713-tv frees the buffers and goes back to its
 *                      own mode (ring or console)
 *   "warp switch client|ring" -> "ok source X"; the claim turns into the other
 *                      source's on the same three buffers (h713-tv of
 *                      16.10.2026): the video plane stays up, only what is
 *                      drawn into the buffers changes
 *
 * and the lines h713-tv says unasked, while a claim stands: "note source X" when
 * its "source" changed (or "client" again: a program starts) - this daemon
 * switches the claim, gives it back or holds the last picture; and "note cover
 * on|off" when an opaque page comes on the wall or goes - this daemon pauses
 * under it and draws again after it. A note can arrive alone, between two
 * frames, or in front of (or behind) the answer to a frame, and is read wherever
 * it comes.
 *
 * ONE connection carries the whole "on" period, and a closed connection means
 * release on both sides (A2's lifetime rule): if this daemon dies h713-tv puts
 * the ring back by itself, if h713-tv dies this one falls back to bypass (M10).
 *
 * A second connection, the want link (P3 of the media side project, 17.10.2026),
 * stays open for as long as both run: "warp want ring" or "warp want none" says
 * whether this daemon will claim the ring when h713-tv lets it, said again only
 * when it changes. With "ring" h713-tv does not put the straight ring on the
 * video plane when the signal comes or "ctl auto" is said: it says "note claim"
 * on this link and waits for the claim up to a second, so the plane goes on once,
 * with the warp's first frame. h713-tv answers each line with "ok want ...".
 */
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

#include "warp.h"

#define CLAIM_MS	1000	/* h713-tv may be allocating three 8 MB buffers */
/*
 * One commit takes h713-tv under a millisecond -- when it gets to it. Its
 * loop is single-threaded, and a control command or a capture event in front
 * of our line holds the answer: a full "h713-tv ctl status" took 388 ms
 * (16:33 and 17:17 on 05.10.2026, the HDCP line read out of the firmware's
 * log ring), a "signal gone" evaluation 317-335 ms, and each time the old
 * 100 ms deadline here declared the link dead -- the warp released, the wall
 * fell back to the ring or the console, and the daemon claimed again a
 * second later: a console flash for a status call. A late answer is a late
 * frame, not a dead peer: the stale guard in loop.c gives the held slot back
 * undrawn, the frame is one drop on the wall, and a peer that is really gone
 * closes the connection, which poll() reports at once whatever the deadline.
 * So the deadline is a hang detector and nothing else, and is sized above
 * every stall measured on h713-tv: its own claim budget.
 */
#define FRAME_MS	1000

void peer_init(struct peer *p, const char *path)
{
	int i;

	p->path = path;
	p->fd = -1;
	p->want_fd = -1;
	p->want_said = -1;
	for (i = 0; i < WARP_TARGETS; i++)
		p->target[i] = -1;
}

static void close_targets(struct peer *p)
{
	int i;

	for (i = 0; i < WARP_TARGETS; i++) {
		if (p->target[i] >= 0)
			close(p->target[i]);
		p->target[i] = -1;
	}
}

static void tv_source(struct peer *p, const char *reply);

/* "note source X": h713-tv's "source" changed under the standing claim, or "client" again: a program starts; the main
 * loop acts on p->noted. "note cover on|off": the main loop compares p->cover with what it did last. */
static void peer_note(struct peer *p, const char *line)
{
	if (!strcmp(line, "note cover on") || !strcmp(line, "note cover off")) {
		p->cover = !strcmp(line, "note cover on");
		return;
	}
	if (strncmp(line, "note source ", 12)) {
		warn("peer            h713-tv said \"%s\" -- not a note this daemon knows", line);
		return;
	}
	tv_source(p, line);
	if (p->tv_source == TV_CLIENT)
		p->client_said = now_s();
	p->noted = true;
	info("peer            h713-tv: %s, the claim follows", line + 5);
}

/*
 * The lines of one read: notes are taken out, the first other line is the answer and lands in reply. h713-tv sends
 * each line with one send() and a line is far shorter than the buffer, so a read holds whole lines. True when the
 * answer was among them.
 */
static bool split_lines(struct peer *p, char *buf, char *reply, size_t n)
{
	bool have = false;
	char *line, *next;

	for (line = buf; *line; line = next) {
		next = line + strcspn(line, "\n");
		if (*next)
			*next++ = '\0';
		line[strcspn(line, "\r")] = '\0';
		if (!strncmp(line, "note ", 5))
			peer_note(p, line);
		else if (!have && *line) {
			memmove(reply, line, strlen(line) + 1 < n ? strlen(line) + 1 : n);
			reply[n - 1] = '\0';
			have = true;
		}
	}
	return have;
}

/* One line out (optionally with one fd in SCM_RIGHTS), one line back
 * (optionally with fds), the answer read with a deadline: a peer that stops
 * talking must not stop this loop. A note of h713-tv's in front of the answer
 * is taken out (split_lines) and the answer waited for further.
 */
static bool exchange(struct peer *p, const char *line, int send_fd, char *reply,
		     size_t n, int *fds, int want, int need, int ms, char *why, size_t wn)
{
	char cbuf[CMSG_SPACE(sizeof(int) * WARP_TARGETS)];
	struct cmsghdr *cm;
	struct msghdr msg;
	struct iovec io;
	struct pollfd pf;
	ssize_t got;
	int i, k = 0;

	reply[0] = '\0';
	memset(&msg, 0, sizeof(msg));
	memset(cbuf, 0, sizeof(cbuf));
	io.iov_base = (void *)(size_t)line;
	io.iov_len = strlen(line);
	msg.msg_iov = &io;
	msg.msg_iovlen = 1;
	if (send_fd >= 0) {
		msg.msg_control = cbuf;
		msg.msg_controllen = CMSG_SPACE(sizeof(int));
		cm = CMSG_FIRSTHDR(&msg);
		cm->cmsg_level = SOL_SOCKET;
		cm->cmsg_type = SCM_RIGHTS;
		cm->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(cm), &send_fd, sizeof(int));
	}
	double x0 = now_s(), x1, x2, x3;

	if (sendmsg(p->fd, &msg, MSG_NOSIGNAL) < 0) {
		snprintf(why, wn, "%s: sending \"%.*s\": %s", p->path,
			 (int)strcspn(line, "\n"), line, strerror(errno));
		return false;
	}
	pf.fd = p->fd;
	pf.events = POLLIN;
	x1 = now_s();
	for (;;) {
		char buf[WARP_LINE];
		int left = ms - (int)((now_s() - x1) * 1e3);

		if (left < 0 || poll(&pf, 1, left) <= 0) {
			snprintf(why, wn, "%s: no answer to \"%.*s\" within %d ms", p->path,
				 (int)strcspn(line, "\n"), line, ms);
			while (k > 0)
				close(fds[--k]);
			return false;
		}
		memset(&msg, 0, sizeof(msg));
		memset(cbuf, 0, sizeof(cbuf));
		io.iov_base = buf;
		io.iov_len = sizeof(buf) - 1;
		msg.msg_iov = &io;
		msg.msg_iovlen = 1;
		msg.msg_control = cbuf;
		msg.msg_controllen = sizeof(cbuf);
		x2 = now_s();
		got = recvmsg(p->fd, &msg, 0);
		x3 = now_s();
		/* the peer took long: h713-tv was held by something (23.09.: its full
		 * status, 50 ms of firmware-backed sysfs reads); the stale guard in
		 * loop.c turns such a frame into a dropped one, this line names it */
		if (x3 - x0 > 0.030)
			info("trace           exchange at %.6f: sendmsg %.1f ms, poll %.1f ms, recvmsg %.1f ms (answer at %.6f)", x0, (x1 - x0) * 1e3, (x2 - x1) * 1e3, (x3 - x2) * 1e3, x3);
		if (got <= 0) {
			snprintf(why, wn, "%s: the connection closed (%s)", p->path,
				 got ? strerror(errno) : "h713-tv hung up");
			while (k > 0)
				close(fds[--k]);
			return false;
		}
		buf[got] = '\0';
		for (cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm)) {
			int have;

			if (cm->cmsg_level != SOL_SOCKET || cm->cmsg_type != SCM_RIGHTS)
				continue;
			have = (int)((cm->cmsg_len - CMSG_LEN(0)) / sizeof(int));
			for (i = 0; i < have; i++) {
				int fd;

				memcpy(&fd, CMSG_DATA(cm) + i * sizeof(int), sizeof(int));
				if (k < want)
					fds[k++] = fd;
				else
					close(fd);	/* more than asked for: not ours */
			}
		}
		if (split_lines(p, buf, reply, n))
			break;
		/* only a note: the answer is still to come */
	}
	if (k < need) {
		snprintf(why, wn, "%s answered \"%s\" with %d of %d file descriptors",
			 p->path, reply, k, need);
		while (k > 0)
			close(fds[--k]);
		return false;
	}
	why[0] = '\0';

	return true;
}

/* h713-tv names its "source" with every answer to a claim: "... source auto", "error source is hdmi ..." */
static void tv_source(struct peer *p, const char *reply)
{
	const char *s = strstr(reply, "source ");
	char w[8] = "";

	if (s) {
		s += 7;
		if (!strncmp(s, "is ", 3))
			s += 3;
		sscanf(s, "%7[a-z]", w);
	}
	p->tv_source = !strcmp(w, "hdmi") ? TV_HDMI : !strcmp(w, "client") ? TV_CLIENT :
		       !strcmp(w, "auto") ? TV_AUTO : TV_UNKNOWN;
}

/* a connection to h713-tv's control socket in p->fd */
static bool peer_connect(struct peer *p, char *why, size_t n)
{
	struct sockaddr_un addr;

	if (strlen(p->path) >= sizeof(addr.sun_path)) {
		snprintf(why, n, "%s: socket path too long", p->path);
		return false;
	}
	p->fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (p->fd < 0) {
		snprintf(why, n, "socket: %s", strerror(errno));
		return false;
	}
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", p->path);
	if (connect(p->fd, (struct sockaddr *)&addr, sizeof(addr))) {
		snprintf(why, n, "%s: %s -- is h713-tv running? (systemctl status 'h713-tv@*')",
			 p->path, strerror(errno));
		close(p->fd);
		p->fd = -1;
		return false;
	}
	return true;
}

/* h713-tv said something unasked between two exchanges (the main loop saw the connection readable): the notes are
 * taken now. False when the connection is gone. */
bool peer_notes(struct peer *p)
{
	char buf[WARP_LINE], rest[WARP_LINE];
	ssize_t got;

	if (p->fd < 0)
		return false;
	got = recv(p->fd, buf, sizeof(buf) - 1, MSG_DONTWAIT);
	if (got == 0)
		return false;
	if (got < 0)
		return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR;
	buf[got] = '\0';
	if (split_lines(p, buf, rest, sizeof(rest)))
		warn("peer            h713-tv said \"%s\" unasked -- not a note, ignored", rest);
	return true;
}

/*
 * "warp switch client|ring" on the standing claim: the same three buffers, the other source drawn into them, the
 * video plane up all the time. False when h713-tv refused it (why says why; the claim is as it was) or the link
 * broke - the caller gives the claim back then, and claims again as before.
 */
bool peer_switch(struct peer *p, int src, char *why, size_t n)
{
	char reply[WARP_LINE];

	if (p->fd < 0) {
		snprintf(why, n, "no claim to switch");
		return false;
	}
	if (!exchange(p, src == SRC_CLIENT ? "warp switch client\n" : "warp switch ring\n", -1, reply, sizeof(reply),
		      NULL, 0, 0, CLAIM_MS, why, n))
		return false;
	tv_source(p, reply);
	if (strncmp(reply, "ok", 2)) {
		snprintf(why, n, "h713-tv: %s", reply);
		return false;
	}
	return true;
}

/*
 * "source" and nothing else: asked before a ring claim while the last answer said "source is client". Under
 * that policy h713-tv refuses the ring, and building it to hear so - STREAMON, six EXPBUF, the claim, STREAMOFF - ran
 * once a second for nothing (measured 15.10.2026: 5 in 6 s). One line on a connection of its own, which h713-tv closes after the answer.
 */
bool peer_source(struct peer *p)
{
	struct peer q = { .path = p->path, .fd = -1 };
	char reply[WARP_LINE], why[WARP_WHY];
	bool ok = peer_connect(&q, why, sizeof(why)) &&
		  exchange(&q, "source\n", -1, reply, sizeof(reply), NULL, 0, 0, CLAIM_MS, why, sizeof(why)) &&
		  !strncmp(reply, "ok", 2);

	if (q.fd >= 0)
		close(q.fd);
	if (ok)
		tv_source(p, reply);
	return ok;
}

/*
 * "source X" (auto) on a connection of its own, as peer_source() asks: the program whose picture this claim holds has
 * ended and none follows - HDMI is the mode again. h713-tv says the new source to the claim as a note, too.
 */
bool peer_set_source(struct peer *p, const char *src)
{
	struct peer q = { .path = p->path, .fd = -1 };
	char line[32], reply[WARP_LINE] = "", why[WARP_WHY] = "";
	bool ok;

	snprintf(line, sizeof(line), "source %s\n", src);
	ok = peer_connect(&q, why, sizeof(why)) &&
	     exchange(&q, line, -1, reply, sizeof(reply), NULL, 0, 0, CLAIM_MS, why, sizeof(why)) &&
	     !strncmp(reply, "ok", 2);
	if (q.fd >= 0)
		close(q.fd);
	if (ok)
		tv_source(p, reply);
	else
		warn("peer            \"source %s\" to h713-tv: %s", src, why[0] ? why : reply);
	return ok;
}

bool peer_claim(struct peer *p, int src, char *why, size_t n)
{
	char reply[WARP_LINE];
	unsigned int w = 0, h = 0, pitch = 0, coff = 0;
	/* the ring's line is the one every h713-tv knows; a client's is new */
	const char *line = src == SRC_CLIENT ? "warp claim client\n" : "warp claim\n";

	if (p->fd >= 0)
		return true;
	p->cover = false;		/* h713-tv says "note cover on" after the answer if a page is up */
	if (!peer_connect(p, why, n))
		return false;
	if (!exchange(p, line, -1, reply, sizeof(reply), p->target,
		      WARP_TARGETS, WARP_TARGETS, CLAIM_MS, why, n)) {
		tv_source(p, reply);
		close(p->fd);
		p->fd = -1;
		return false;
	}
	tv_source(p, reply);
	if (strncmp(reply, "ok", 2) ||
	    sscanf(reply, "ok %u %u %u nv12 %u", &w, &h, &pitch, &coff) != 4 || !w || !h ||
	    pitch < w || coff < pitch * h) {
		/* NV12 since 23.09.2026: the frames go on the video plane, the one
		 * the firmware's picture controls act on; an answer without "nv12"
		 * is an older h713-tv, which drew on the primary plane */
		snprintf(why, n, "h713-tv answered \"%s\" to \"warp claim\" -- it must hand out NV12 buffers (h713-tv of 23.09. or later)",
			 reply);
		close_targets(p);
		close(p->fd);
		p->fd = -1;
		return false;
	}
	p->width = w;
	p->height = h;
	p->pitch = pitch;
	p->coff = coff;
	p->commits = p->busy = p->errors = 0;
	info("peer            %s: three NV12 buffers %ux%u, line pitch %u, chroma at %u",
	     p->path, w, h, pitch, coff);

	return true;
}

/*
 * One frame. Returns 0 when the commit was queued, 1 when h713-tv was still
 * busy with the previous flip (the frame is dropped, the wall keeps the
 * frame before it) and -1 when the link is broken -- which is the caller's
 * signal to fall back to bypass. The fence fd is ours to close either way:
 * the kernel does not take ownership of an IN_FENCE_FD.
 */
int peer_frame(struct peer *p, int index, int fence, int *flip, char *why, size_t n)
{
	char line[64], reply[WARP_LINE];

	*flip = -1;
	snprintf(line, sizeof(line), "warp frame %d\n", index);
	if (!exchange(p, line, fence, reply, sizeof(reply), flip, 1, 0, FRAME_MS,
		      why, n)) {
		p->errors++;
		return -1;
	}
	if (strncmp(reply, "ok", 2) || strstr(reply, "busy")) {
		if (*flip >= 0)
			close(*flip);
		*flip = -1;
	}
	if (strncmp(reply, "ok", 2)) {
		snprintf(why, n, "h713-tv: %s", reply);
		p->errors++;
		return -1;
	}
	if (strstr(reply, " source "))	/* "source" changed, the claim stands */
		tv_source(p, reply);
	if (strstr(reply, "busy")) {
		p->busy++;
		return 1;
	}
	p->commits++;

	return 0;
}

#define WANT_RETRY_S	1.0	/* the want link is tried again at most this often */

/*
 * The want link (P3): made when there is none and connect is asked for (at most once WANT_RETRY_S), and the word said
 * when it changed or the link is new. Non-blocking: h713-tv answers in its own time ("ok want ..."), and its notes come
 * on the same link; peer_want_notes() reads both.
 */
void peer_want(struct peer *p, bool ring, bool connect)
{
	const char *line = ring ? "warp want ring\n" : "warp want none\n";
	char why[WARP_WHY];

	if (p->want_refused)
		return;
	if (p->want_fd < 0) {
		struct peer q = { .path = p->path, .fd = -1 };

		if (!connect || now_s() - p->want_tried < WANT_RETRY_S)
			return;
		p->want_tried = now_s();
		if (!peer_connect(&q, why, sizeof(why)))
			return;			/* h713-tv is not there (yet): again in a second */
		p->want_fd = q.fd;
		p->want_said = -1;
	}
	if (p->want_said == (int)ring)
		return;
	if (send(p->want_fd, line, strlen(line), MSG_NOSIGNAL | MSG_DONTWAIT) != (ssize_t)strlen(line)) {
		warn("peer            \"warp want %s\" to h713-tv: %s -- the link is made again", ring ? "ring" : "none",
		     strerror(errno));
		close(p->want_fd);
		p->want_fd = -1;
		return;
	}
	p->want_said = ring;
	info("peer            to h713-tv: %s", ring ? "\"warp want ring\" -- the ring will be claimed when h713-tv lets it, the straight ring waits for it" :
	     "\"warp want none\" -- no ring claim, h713-tv shows the straight ring at once");
}

bool peer_want_notes(struct peer *p)
{
	char buf[WARP_LINE], *line, *next;
	ssize_t got;

	if (p->want_fd < 0)
		return false;
	got = recv(p->want_fd, buf, sizeof(buf) - 1, MSG_DONTWAIT);
	if (got < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
		return true;
	if (got <= 0) {
		close(p->want_fd);
		p->want_fd = -1;
		p->want_said = -1;
		return false;
	}
	buf[got] = '\0';
	for (line = buf; *line; line = next) {
		next = line + strcspn(line, "\n");
		if (*next)
			*next++ = '\0';
		line[strcspn(line, "\r")] = '\0';
		if (!strcmp(line, "note claim")) {
			p->claim_noted = true;
		} else if (!strncmp(line, "error", 5)) {
			/* an h713-tv of before 17.10.2026: no want link, the ring comes as before (and the claim after it) */
			warn("peer            h713-tv does not take \"warp want\" (%s) -- not asked again", line);
			p->want_refused = true;
			close(p->want_fd);
			p->want_fd = -1;
			return false;
		}
		/* "ok want ...": the word arrived */
	}
	return true;
}

void peer_release(struct peer *p)
{
	char reply[WARP_LINE], why[WARP_WHY];

	if (p->fd >= 0) {
		exchange(p, "warp release\n", -1, reply, sizeof(reply), NULL, 0, 0,
			 FRAME_MS, why, sizeof(why));
		close(p->fd);
	}
	p->fd = -1;
	p->cover = false;
	close_targets(p);
}
