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
 *                      XRGB8888 dumb buffers of the panel mode
 *   "warp frame N"  -> the out-fence fd travels with the line; h713-tv commits
 *                      buffer N on the primary plane with IN_FENCE_FD = that
 *                      fd and the video plane off, and answers "ok" once the
 *                      commit is queued, or "ok busy" when the previous flip
 *                      has not happened yet -- that frame is dropped, which
 *                      is one frame of the wall and not an error
 *   "warp release"  -> "ok"; h713-tv frees the buffers and goes back to its
 *                      own mode (ring or console)
 *
 * ONE connection carries the whole "on" period, and a closed connection means
 * release on both sides (A2's lifetime rule): if this daemon dies h713-tv puts
 * the ring back by itself, if h713-tv dies this one falls back to bypass (M10).
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
#define FRAME_MS	100	/* one commit; longer means something is wrong */

void peer_init(struct peer *p, const char *path)
{
	int i;

	p->path = path;
	p->fd = -1;
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

/* One line out (optionally with one fd in SCM_RIGHTS), one line back
 * (optionally with fds), the answer read with a deadline: a peer that stops
 * talking must not stop this loop.
 */
static bool exchange(struct peer *p, const char *line, int send_fd, char *reply,
		     size_t n, int *fds, int want, int ms, char *why, size_t wn)
{
	char cbuf[CMSG_SPACE(sizeof(int) * WARP_TARGETS)];
	struct cmsghdr *cm;
	struct msghdr msg;
	struct iovec io;
	struct pollfd pf;
	ssize_t got;
	int i, k = 0;

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
	if (poll(&pf, 1, ms) <= 0) {
		snprintf(why, wn, "%s: no answer to \"%.*s\" within %d ms", p->path,
			 (int)strcspn(line, "\n"), line, ms);
		return false;
	}
	memset(&msg, 0, sizeof(msg));
	memset(cbuf, 0, sizeof(cbuf));
	io.iov_base = reply;
	io.iov_len = n - 1;
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
		return false;
	}
	reply[got] = '\0';
	reply[strcspn(reply, "\r\n")] = '\0';
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
	if (k < want) {
		snprintf(why, wn, "%s answered \"%s\" with %d of %d file descriptors",
			 p->path, reply, k, want);
		while (k > 0)
			close(fds[--k]);
		return false;
	}
	why[0] = '\0';

	return true;
}

bool peer_claim(struct peer *p, char *why, size_t n)
{
	struct sockaddr_un addr;
	char reply[WARP_LINE];
	unsigned int w = 0, h = 0, pitch = 0, coff = 0;

	if (p->fd >= 0)
		return true;
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
	if (!exchange(p, "warp claim\n", -1, reply, sizeof(reply), p->target,
		      WARP_TARGETS, CLAIM_MS, why, n)) {
		close(p->fd);
		p->fd = -1;
		return false;
	}
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
int peer_frame(struct peer *p, int index, int fence, char *why, size_t n)
{
	char line[64], reply[WARP_LINE];

	snprintf(line, sizeof(line), "warp frame %d\n", index);
	if (!exchange(p, line, fence, reply, sizeof(reply), NULL, 0, FRAME_MS,
		      why, n)) {
		p->errors++;
		return -1;
	}
	if (strncmp(reply, "ok", 2)) {
		snprintf(why, n, "h713-tv: %s", reply);
		p->errors++;
		return -1;
	}
	if (strstr(reply, "busy")) {
		p->busy++;
		return 1;
	}
	p->commits++;

	return 0;
}

void peer_release(struct peer *p)
{
	char reply[WARP_LINE], why[WARP_WHY];

	if (p->fd >= 0) {
		exchange(p, "warp release\n", -1, reply, sizeof(reply), NULL, 0,
			 FRAME_MS, why, sizeof(why));
		close(p->fd);
	}
	p->fd = -1;
	close_targets(p);
}
