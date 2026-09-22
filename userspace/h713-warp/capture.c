/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* accept4, strtok_r, O_CLOEXEC */
/*
 * The capture source (design AP2d M5): /dev/videoN of sun50i-h713-hdmirx.
 * REQBUFS 3, VIDIOC_EXPBUF per buffer and plane -- the exporter is kernel
 * patch 0136y, verified over LAN on 22.09.2026 (PLAN section 8) -- then
 * STREAMON and a DQBUF/QBUF loop. The six dma-bufs become six EGLImages once,
 * in gl.c; nothing is imported per frame. Two things this module says out
 * loud: the slot contract is not a fence (a slot is overwritten every 50 ms
 * at 60 Hz and nothing says so -- loop.c holds it until h713-tv has
 * answered), and the geometry comes from V4L2, never from the picture, which
 * is what source_geometry_changed() is for (doku/86 question 7, AP2d T4).
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>

#include <linux/videodev2.h>

#include "warp.h"

void source_init(struct source *s, const char *want)
{
	int i, j;

	s->want = want;
	s->fd = -1;
	s->planes = 1;
	s->streaming = false;
	for (i = 0; i < WARP_SLOTS; i++)
		for (j = 0; j < 2; j++)
			s->dmabuf[i][j] = -1;
}

/*
 * By driver name, not by number: /dev/video0 is cedrus on this board, and
 * v4l2_capability has __u8 driver[16], so the kernel reports at most
 * "sun50i-h713-hdm" of our 18-character name -- only a prefix compare can
 * match (h713-tv capture_open, scanout.c v4l_open).
 */
static bool open_node(struct source *s, char *why, size_t n)
{
	struct v4l2_capability vc;
	unsigned int caps;
	int i;

	for (i = 0; i < 64; i++) {
		if (s->want)
			snprintf(s->path, sizeof(s->path), "%s", s->want);
		else
			snprintf(s->path, sizeof(s->path), "/dev/video%d", i);
		s->fd = open(s->path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
		if (s->fd >= 0) {
			memset(&vc, 0, sizeof(vc));
			if (!ioctl(s->fd, VIDIOC_QUERYCAP, &vc) &&
			    !strncmp((const char *)vc.driver, V4L2_NAME,
				     sizeof(vc.driver) - 1)) {
				caps = vc.device_caps ? vc.device_caps : vc.capabilities;
				s->type = caps & V4L2_CAP_VIDEO_CAPTURE_MPLANE ?
					V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE :
					V4L2_BUF_TYPE_VIDEO_CAPTURE;
				return true;
			}
			close(s->fd);
			s->fd = -1;
		}
		if (s->want) {
			snprintf(why, n, "%s: %s", s->path,
				 s->fd < 0 ? strerror(errno) :
					     "not a " V4L2_NAME " node");
			return false;
		}
	}
	snprintf(why, n, "no /dev/video* belongs to " V4L2_NAME);

	return false;
}

/* the ring as the driver reports it: no S_FMT, the signal is the format */
static bool read_format(struct source *s, char *why, size_t n)
{
	struct v4l2_format f;
	bool mp = s->type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;

	memset(&f, 0, sizeof(f));
	f.type = s->type;
	if (ioctl(s->fd, VIDIOC_G_FMT, &f)) {
		snprintf(why, n, "G_FMT: %s -- is there a signal?", strerror(errno));
		return false;
	}
	s->planes = mp ? (int)f.fmt.pix_mp.num_planes : 1;
	s->width = mp ? f.fmt.pix_mp.width : f.fmt.pix.width;
	s->height = mp ? f.fmt.pix_mp.height : f.fmt.pix.height;
	s->pitch = mp ? f.fmt.pix_mp.plane_fmt[0].bytesperline
		      : f.fmt.pix.bytesperline;
	s->cpitch = mp && s->planes > 1 ? f.fmt.pix_mp.plane_fmt[1].bytesperline
					: s->pitch;
	s->off_c = s->planes > 1 ? 0 : s->pitch * s->height;
	if (!s->width || !s->height || s->pitch < s->width) {
		snprintf(why, n, "the ring is %ux%u with line pitch %u -- not usable",
			 s->width, s->height, s->pitch);
		return false;
	}
	why[0] = '\0';

	return true;
}

static void fill(const struct source *s, struct v4l2_buffer *b,
		 struct v4l2_plane *pl, int index)
{
	memset(b, 0, sizeof(*b));
	memset(pl, 0, sizeof(*pl) * VIDEO_MAX_PLANES);
	b->type = (unsigned int)s->type;
	b->memory = V4L2_MEMORY_MMAP;
	b->index = index < 0 ? 0 : (unsigned int)index;
	b->m.planes = pl;
	b->length = (unsigned int)s->planes;
}

bool source_start(struct source *s, char *why, size_t n)
{
	struct v4l2_event_subscription sub;
	struct v4l2_requestbuffers rb;
	struct v4l2_exportbuffer ex;
	struct v4l2_plane pl[VIDEO_MAX_PLANES];
	struct v4l2_buffer b;
	int i, j;

	if (s->fd < 0 && !open_node(s, why, n))
		return false;
	if (!read_format(s, why, n))
		return false;
	memset(&sub, 0, sizeof(sub));
	sub.type = V4L2_EVENT_SOURCE_CHANGE;
	if (ioctl(s->fd, VIDIOC_SUBSCRIBE_EVENT, &sub))
		warn("capture         SUBSCRIBE_EVENT(SOURCE_CHANGE): %s -- a geometry change is then only seen at the next DQBUF error",
		     strerror(errno));
	memset(&rb, 0, sizeof(rb));
	rb.count = WARP_SLOTS;
	rb.type = (unsigned int)s->type;
	rb.memory = V4L2_MEMORY_MMAP;
	if (ioctl(s->fd, VIDIOC_REQBUFS, &rb) || rb.count < WARP_SLOTS) {
		snprintf(why, n, "REQBUFS: %s (%u of %d slots)", strerror(errno),
			 rb.count, WARP_SLOTS);
		return false;
	}
	for (i = 0; i < WARP_SLOTS; i++) {
		for (j = 0; j < s->planes; j++) {
			memset(&ex, 0, sizeof(ex));
			ex.type = (unsigned int)s->type;
			ex.index = (unsigned int)i;
			ex.plane = (unsigned int)j;
			ex.flags = O_RDONLY | O_CLOEXEC;
			if (ioctl(s->fd, VIDIOC_EXPBUF, &ex)) {
				snprintf(why, n, "EXPBUF slot %d plane %d: %s -- the exporter is kernel patch 0136y, is that one running?",
					 i, j, strerror(errno));
				return false;
			}
			s->dmabuf[i][j] = ex.fd;
		}
		fill(s, &b, pl, i);
		if (ioctl(s->fd, VIDIOC_QBUF, &b)) {
			snprintf(why, n, "QBUF slot %d: %s", i, strerror(errno));
			return false;
		}
	}
	if (ioctl(s->fd, VIDIOC_STREAMON, &s->type)) {
		snprintf(why, n, "STREAMON: %s", strerror(errno));
		return false;
	}
	s->streaming = true;
	info("capture         %s, ring %ux%u, line pitch %u/%u, %d dma-buf%s per slot",
	     s->path, s->width, s->height, s->pitch, s->cpitch, s->planes,
	     s->planes == 1 ? "" : "s");

	return true;
}

void source_stop(struct source *s)
{
	struct v4l2_requestbuffers rb;
	int i, j;

	if (s->fd < 0)
		return;
	if (s->streaming)
		ioctl(s->fd, VIDIOC_STREAMOFF, &s->type);
	s->streaming = false;
	for (i = 0; i < WARP_SLOTS; i++)
		for (j = 0; j < 2; j++) {
			if (s->dmabuf[i][j] >= 0)
				close(s->dmabuf[i][j]);
			s->dmabuf[i][j] = -1;
		}
	memset(&rb, 0, sizeof(rb));
	rb.type = (unsigned int)s->type;
	rb.memory = V4L2_MEMORY_MMAP;
	ioctl(s->fd, VIDIOC_REQBUFS, &rb);	/* count 0: give the slots back */
}

/* the slot that was filled last, or -1 with a reason in why */
int source_dequeue(struct source *s, char *why, size_t n)
{
	struct v4l2_plane pl[VIDEO_MAX_PLANES];
	struct v4l2_buffer b;

	why[0] = '\0';
	fill(s, &b, pl, -1);
	if (ioctl(s->fd, VIDIOC_DQBUF, &b)) {
		if (errno == EAGAIN)
			return -1;		/* nothing ready, no complaint */
		snprintf(why, n, "DQBUF: %s", strerror(errno));
		s->timeouts++;
		return -1;
	}
	s->frames++;

	return (int)b.index;
}

bool source_queue(struct source *s, int index)
{
	struct v4l2_plane pl[VIDEO_MAX_PLANES];
	struct v4l2_buffer b;

	fill(s, &b, pl, index);
	if (ioctl(s->fd, VIDIOC_QBUF, &b)) {
		warn("capture         QBUF slot %d: %s", index, strerror(errno));
		return false;
	}

	return true;
}

/*
 * Drain the event queue and say whether the geometry moved. The event alone
 * is not the answer -- a SOURCE_CHANGE also fires for a colour change -- so
 * the format is read again and compared.
 */
bool source_geometry_changed(struct source *s)
{
	unsigned int w = s->width, h = s->height, p = s->pitch;
	struct v4l2_event ev;
	char why[WARP_WHY];
	bool seen = false;

	while (!ioctl(s->fd, VIDIOC_DQEVENT, &ev))
		seen |= ev.type == V4L2_EVENT_SOURCE_CHANGE;
	if (!seen)
		return false;
	if (!read_format(s, why, sizeof(why))) {
		info("capture         source change: %s", why);
		return true;
	}
	if (w == s->width && h == s->height && p == s->pitch)
		return false;
	info("capture         source change: ring %ux%u line pitch %u (was %ux%u/%u)",
	     s->width, s->height, s->pitch, w, h, p);

	return true;
}
