/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE
/*
 * The Wayland server of h713-warp (wayland.c) on its own, for the host test (package G): no GPU, no h713-tv. The GL
 * side and the warp's loop are stubs - an import is a record, a frame is two eventfds that are readable at once (the
 * render fence and the flip fence). It says what the loop would have been told on stdout, one word a line, for
 * test_wayland.c: "shown", "gone", "frame", "resend".
 *
 *   server_stub SOCKET     runs until stdin closes
 */
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/eventfd.h>
#include <drm_fourcc.h>

#include "warp.h"

struct gl_image {
	int w, h;
};

static struct server *srv;
static bool live;

void info(const char *fmt, ...) { (void)fmt; }
void warn(const char *fmt, ...) { (void)fmt; }
double now_s(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}
void text_add(struct textbuf *t, const char *fmt, ...) { (void)t; (void)fmt; }

int gl_open(const char *node, char *why, size_t n) { (void)node; (void)why; (void)n; return 0; }
bool gl_is_open(void) { return true; }
void gl_close(void) { }
int gl_formats(struct gl_format *out, int max, char *why, size_t n)
{
	static const struct gl_format f[] = {
		{ DRM_FORMAT_XRGB8888, DRM_FORMAT_MOD_LINEAR }, { DRM_FORMAT_ARGB8888, DRM_FORMAT_MOD_LINEAR },
		{ DRM_FORMAT_ARGB2101010, 0x0800000000000062ull },
	};

	(void)why;
	(void)n;
	memcpy(out, f, sizeof(f));
	return max >= 3 ? 3 : 0;
}
static struct gl_image *image(int w, int h)
{
	struct gl_image *im = calloc(1, sizeof(*im));

	im->w = w;
	im->h = h;
	return im;
}
struct gl_image *gl_image_dmabuf(int fd, uint32_t fourcc, uint64_t modifier, int w, int h, uint32_t offset,
				 uint32_t pitch, char *why, size_t n)
{
	(void)fd; (void)fourcc; (void)modifier; (void)offset; (void)pitch; (void)why; (void)n;
	return image(w, h);
}
struct gl_image *gl_image_shm(void) { return image(0, 0); }
bool gl_image_upload(struct gl_image *im, const void *px, int w, int h, int stride, char *why, size_t n)
{
	(void)px; (void)stride; (void)why; (void)n;
	im->w = w;
	im->h = h;
	return true;
}
int gl_image_width(const struct gl_image *im) { return im->w; }
int gl_image_height(const struct gl_image *im) { return im->h; }
bool gl_image_stale(const struct gl_image *im) { (void)im; return false; }
void gl_image_free(struct gl_image *im) { free(im); }

static void say(const char *w)
{
	printf("%s\n", w);
	fflush(stdout);
}
bool warp_client_live(const struct runtime *r) { (void)r; return live; }
int warp_client_frame(struct runtime *r, const struct gl_image *im, int *render, int *flip)
{
	(void)r;
	(void)im;
	*render = eventfd(1, EFD_CLOEXEC);
	*flip = eventfd(1, EFD_CLOEXEC);
	say("frame");
	return 0;
}
int warp_client_resend(struct runtime *r, int render, int *flip)
{
	(void)r;
	if (render >= 0)
		close(render);
	*flip = eventfd(1, EFD_CLOEXEC);
	say("resend");
	return 0;
}
void warp_client_shown(struct runtime *r)
{
	(void)r;
	live = true;
	say("shown");
	server_engaged(srv, true);
}
void warp_client_gone(struct runtime *r)
{
	(void)r;
	if (!live)
		return;
	live = false;
	say("gone");
	server_engaged(srv, false);
}
void warp_gl_idle(struct runtime *r) { (void)r; }

int main(int argc, char **argv)
{
	struct runtime r;
	struct pollfd pf[2];

	if (argc != 2)
		return 2;
	memset(&r, 0, sizeof(r));
	r.render_node = "/dev/null";
	r.client_rate = 1;
	srv = server_start(argv[1], &r);
	if (!srv)
		return 1;
	r.srv = srv;
	say("up");
	for (;;) {
		server_flush(srv);
		pf[0].fd = server_fd(srv);
		pf[0].events = POLLIN;
		pf[1].fd = 0;
		pf[1].events = POLLIN;
		if (poll(pf, 2, 1000) < 0)
			break;
		if (pf[1].revents)
			break;
		if (pf[0].revents)
			server_dispatch(srv);
	}
	server_stop(srv);
	return 0;
}
