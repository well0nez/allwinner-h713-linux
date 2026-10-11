// SPDX-License-Identifier: GPL-2.0
/*
 * osd-show - one overlay on the panel through h713-tv's overlay channel, a test tool for the board:
 *
 *   osd-show [-s SOCKET] [-t SECONDS] [--demo] KIND VALUE [edge]
 *
 * KIND volume|mute|focus|input|badge ("mute" draws the mute overlay and the badge that stays); "--demo" runs the volume from 0 to 100 and back, alternating the two
 * buffers, and prints how long drawing, copying and showing took. It claims the overlay ("osd claim", two
 * dma-bufs with the answer), draws with libh713osd into memory, copies the touched rectangle into a buffer,
 * says "osd show N", waits, says "osd hide" and "osd release". h713-osd will do the same as a daemon.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <linux/dma-buf.h>

#include "osd.h"

static double now_ms(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

/* one line to h713-tv on the claimed connection, its answer back */
static int talk(int fd, const char *line, char *answer, size_t n)
{
	ssize_t got;

	if (send(fd, line, strlen(line), MSG_NOSIGNAL) < 0)
		return -1;
	got = recv(fd, answer, n - 1, 0);
	if (got <= 0)
		return -1;
	answer[got] = '\0';
	answer[strcspn(answer, "\n")] = '\0';
	return strncmp(answer, "ok", 2) ? -1 : 0;
}

static void sync_buf(int fd, unsigned long long flags)
{
	struct dma_buf_sync s = { flags };

	ioctl(fd, DMA_BUF_IOCTL_SYNC, &s);
}

/* the rectangle box[] of the canvas into the mapped buffer */
static void copy_box(uint32_t *dst, unsigned int pitch, const struct osd_canvas *c, const int box[4])
{
	for (int y = box[1]; y < box[1] + box[3]; y++)
		memcpy((char *)dst + (size_t)y * pitch + (size_t)box[0] * 4, c->px + (size_t)y * c->stride + box[0],
		       (size_t)box[2] * 4);
}

int main(int argc, char **argv)
{
	const char *sock = "/run/h713-tv/ctl";
	char cbuf[CMSG_SPACE(sizeof(int) * 2)] = { 0 }, line[128], answer[256];
	struct iovec io = { line, sizeof(line) - 1 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = cbuf,
			      .msg_controllen = sizeof(cbuf) };
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	struct osd_style st = { OSD_BOTTOM, OSD_PILL, 1.0f };
	struct osd_item it = { OSD_VOLUME, 45, 0, 1.0f };
	struct osd_canvas c = { 0 };
	unsigned int w, h, pitch;
	int fd, fds[2] = { -1, -1 }, box[4], last[2][4] = { { 0 } }, seconds = 5, demo = 0, a = 1;
	uint32_t *map[2];
	struct cmsghdr *cm;
	ssize_t got;

	for (; a < argc && argv[a][0] == '-'; a++) {
		if (!strcmp(argv[a], "-s") && a + 1 < argc)
			sock = argv[++a];
		else if (!strcmp(argv[a], "-t") && a + 1 < argc)
			seconds = atoi(argv[++a]);
		else if (!strcmp(argv[a], "--demo"))
			demo = 1;
		else
			break;
	}
	if (!demo && argc - a < 2) {
		fprintf(stderr, "usage: osd-show [-s SOCKET] [-t SECONDS] [--demo] volume|mute|focus|input|badge VALUE [edge]\n");
		return 2;
	}
	if (!demo) {
		const char *k = argv[a];

		it.kind = !strcmp(k, "mute") ? OSD_MUTE : !strcmp(k, "focus") ? OSD_FOCUS :
			  !strcmp(k, "input") ? OSD_INPUT : !strcmp(k, "badge") ? OSD_MUTE_BADGE : OSD_VOLUME;
		it.value = atoi(argv[a + 1]);
		it.flags = a + 2 < argc && !strcmp(argv[a + 2], "edge") ? OSD_EDGE : 0;
	}

	fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sock);
	if (fd < 0 || connect(fd, (struct sockaddr *)&addr, sizeof(addr))) {
		perror(sock);
		return 1;
	}
	if (send(fd, "osd claim\n", 10, MSG_NOSIGNAL) < 0 || (got = recvmsg(fd, &msg, 0)) <= 0) {
		perror("osd claim");
		return 1;
	}
	line[got] = '\0';
	for (cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm))
		if (cm->cmsg_level == SOL_SOCKET && cm->cmsg_type == SCM_RIGHTS)
			memcpy(fds, CMSG_DATA(cm), sizeof(fds));
	if (sscanf(line, "ok %u %u %u argb8888", &w, &h, &pitch) != 3 || fds[0] < 0 || fds[1] < 0) {
		fprintf(stderr, "osd claim: %s", line);
		return 1;
	}
	printf("claimed: two %ux%u ARGB8888 buffers, pitch %u\n", w, h, pitch);
	for (int i = 0; i < 2; i++) {
		map[i] = mmap(NULL, (size_t)pitch * h, PROT_READ | PROT_WRITE, MAP_SHARED, fds[i], 0);
		if (map[i] == MAP_FAILED) {
			perror("mmap");
			return 1;
		}
	}
	c.w = (int)w, c.h = (int)h, c.stride = (int)w;
	c.px = calloc((size_t)w * h, 4);
	if (!c.px)
		return 1;

	for (int step = 0, n = 0; step < (demo ? 41 : 1); step++, n ^= 1) {
		double t0, t1, t2, t3;
		int clear[4];

		if (demo)
			it.value = step <= 20 ? step * 5 : (40 - step) * 5;
		t0 = now_ms();
		osd_clear_box(&c, last[n ^ 1]);	/* what the canvas got last time; the rest is still clear */
		osd_draw(&c, &st, &it, box);
		if (it.kind == OSD_MUTE) {	/* the badge comes with it and stays: one rectangle over both */
			struct osd_item badge = { OSD_MUTE_BADGE, 0, 0, 1.0f };
			int b2[4], x1 = box[0] + box[2], y1 = box[1] + box[3];

			osd_draw(&c, &st, &badge, b2);
			box[0] = box[0] < b2[0] ? box[0] : b2[0];
			box[1] = box[1] < b2[1] ? box[1] : b2[1];
			box[2] = (x1 > b2[0] + b2[2] ? x1 : b2[0] + b2[2]) - box[0];
			box[3] = (y1 > b2[1] + b2[3] ? y1 : b2[1] + b2[3]) - box[1];
		}
		t1 = now_ms();
		/* the buffer still holds what it showed two steps ago: clear that rectangle, then the new one */
		sync_buf(fds[n], DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE);
		memcpy(clear, last[n], sizeof(clear));
		for (int y = clear[1]; y < clear[1] + clear[3]; y++)
			memset((char *)map[n] + (size_t)y * pitch + (size_t)clear[0] * 4, 0, (size_t)clear[2] * 4);
		copy_box(map[n], pitch, &c, box);
		sync_buf(fds[n], DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE);
		memcpy(last[n], box, sizeof(box));
		t2 = now_ms();
		snprintf(line, sizeof(line), "osd show %d\n", n);
		if (talk(fd, line, answer, sizeof(answer)))
			fprintf(stderr, "show: %s\n", answer);
		t3 = now_ms();
		printf("%s value %3d: drawn %.1f ms, copied %.1f ms (%dx%d), shown %.1f ms -- %s\n",
		       demo ? "demo" : "item", it.value, t1 - t0, t2 - t1, box[2], box[3], t3 - t2, answer);
		if (demo)
			usleep(150000);
	}
	if (!demo)
		sleep((unsigned int)seconds);
	if (talk(fd, "osd hide\n", answer, sizeof(answer)))
		fprintf(stderr, "hide: %s\n", answer);
	if (talk(fd, "osd release\n", answer, sizeof(answer)))
		fprintf(stderr, "release: %s\n", answer);
	printf("hidden and released\n");
	return 0;
}
