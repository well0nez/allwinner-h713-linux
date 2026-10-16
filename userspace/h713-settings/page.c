// SPDX-License-Identifier: GPL-2.0
/*
 * The page's way to the wall: the page channel of h713-osd. h713-osd is the one program that holds the display's overlay
 * channel of h713-tv and knows how to put a picture over the HDMI picture - straight, or through the keystone's matrix -
 * so the page does not claim anything itself: it asks h713-osd for a canvas ("page open": the answer carries one memfd the
 * size of the panel, ARGB8888, which the page maps and draws into) and says which rectangle of it is new ("page show X Y W
 * H"). h713-osd copies or pre-distorts that rectangle before it answers; the canvas is the page's again at once. The
 * connection is the page's life: it ends, and the page is gone from the wall.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>

#include "settings.h"

static int sock = -1;
static size_t map_len;

/* 0: the page is on the wall's side; -1: it cannot be seen (no signal, h713-osd not running), so it is not opened */
int page_open(struct osd_canvas *c, const char *path)
{
	char cbuf[CMSG_SPACE(sizeof(int))] = { 0 }, line[160];
	struct iovec io = { line, sizeof(line) - 1 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = cbuf, .msg_controllen = sizeof(cbuf) };
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	struct timeval tmo = { 3, 0 };
	unsigned w, h, pitch;
	struct cmsghdr *cm;
	int fd = -1;
	ssize_t got;
	void *m;

	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
	sock = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (sock < 0 || connect(sock, (struct sockaddr *)&addr, sizeof(addr))) {
		fprintf(stderr, "h713-settings: %s: %s -- is h713-osd running?\n", path, strerror(errno));
		page_close();
		return -1;
	}
	setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tmo, sizeof(tmo));
	if (send(sock, "page open\n", 10, MSG_NOSIGNAL) < 0 || (got = recvmsg(sock, &msg, MSG_CMSG_CLOEXEC)) <= 0) {
		fprintf(stderr, "h713-settings: \"page open\" got no answer: %s\n", strerror(errno));
		page_close();
		return -1;
	}
	line[got] = '\0';
	for (cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm))
		if (cm->cmsg_level == SOL_SOCKET && cm->cmsg_type == SCM_RIGHTS)
			memcpy(&fd, CMSG_DATA(cm), sizeof(fd));
	if (sscanf(line, "ok %u %u %u argb8888", &w, &h, &pitch) != 3 || fd < 0 || pitch < w * 4) {
		line[strcspn(line, "\n")] = '\0';
		fprintf(stderr, "h713-settings: h713-osd answers \"%s\" -- no page\n", line);
		if (fd >= 0)
			close(fd);
		page_close();
		return -1;
	}
	map_len = (size_t)pitch * h;
	m = mmap(NULL, map_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	close(fd);
	if (m == MAP_FAILED) {
		fprintf(stderr, "h713-settings: mapping the canvas: %s\n", strerror(errno));
		page_close();
		return -1;
	}
	c->px = m;
	c->w = (int)w, c->h = (int)h, c->stride = (int)(pitch / 4);
	return 0;
}

/* 1: the rectangle is on the wall; 0: h713-osd keeps it and shows it when the picture is back (no signal at the moment: the
 * autofocus has the panel, a source that changes its mode); -1: h713-osd is gone or refuses */
int page_show(const int box[4])
{
	char line[96], answer[96];
	ssize_t got;

	if (sock < 0)
		return -1;
	if (!box[2] || !box[3])
		return 1;
	snprintf(line, sizeof(line), "page show %d %d %d %d\n", box[0], box[1], box[2], box[3]);
	if (send(sock, line, strlen(line), MSG_NOSIGNAL) < 0 || (got = recv(sock, answer, sizeof(answer) - 1, 0)) <= 0)
		return -1;
	answer[got] = '\0';
	if (strncmp(answer, "ok", 2))
		return -1;
	return strstr(answer, "waiting") || strstr(answer, "unseen") ? 0 : 1;
}

void page_close(void)
{
	if (sock >= 0)
		close(sock);		/* h713-osd takes the page away with the connection */
	sock = -1;
}
