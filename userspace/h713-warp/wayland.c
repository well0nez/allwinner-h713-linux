/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* memfd_create */
/*
 * The Wayland server (media side project, package G; ENTWURF G v3, mythos/PRUEFUNG-M3). A client - cage with Kodi
 * in it, WLR_BACKENDS=wayland,libinput - is a second source next to the capture ring: its buffers come in as dma-bufs,
 * the warp draws them through the keystone into h713-tv's three NV12 targets, h713-tv commits. Nothing here opens a
 * card node or holds a master; the client reads its own input through libinput, so there is no wl_seat (F9).
 *
 * The protocol set and nothing more (M3 2): wl_compositor/wl_surface/wl_region, wl_shm (libwayland's), xdg-shell with
 * one fullscreen toplevel, linux-dmabuf v4 with a format table out of EGL (M3 1), wl_output and wp_presentation
 * (M3 5). One thread: the event loop's fd sits in main.c's poll(), and every buffer, fence and timer of the client is
 * a source of that loop.
 *
 * A buffer's life (v3 section 3): committed = pending (a newer commit releases a pending one at once); ready when its
 * dma-buf is readable (the writer's fence is through - never wait behind a client); taken when it is ready AND the
 * previous commit is on the panel (h713-tv's flip fence, M3 4), the frame callbacks done right then; released when the
 * render fence of the frame that read it signals (M3 3); presented with the flip fence's timestamp (M3 5).
 */
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <linux/sync_file.h>

#include <wayland-server-core.h>
#include <wayland-server-protocol.h>
#include "xdg-shell-server-protocol.h"
#include "linux-dmabuf-v1-server-protocol.h"
#include "presentation-time-server-protocol.h"
#include <drm_fourcc.h>

#include "warp.h"

#define MAX_CLIENTS	4	/* connections that see the globals (v3 section 7) */
#define MAX_SURFACES	8	/* surfaces per client */
#define MAX_IMPORTS	8	/* imported dma-bufs per client (M3 1: imports, not wl_buffer objects) */
#define MAX_BUFFERS	32	/* wl_buffer objects per client: each holds an fd */
#define MAX_FORMATS	128
#define HOLD_MS		2000	/* the panel stays the client's this long after it is gone: a cage restart */
#define BUSY_MS		4	/* "ok busy": the drawn target once more after this (v3 D6) */
#define PERIOD_S	(1.0 / 59.42)	/* the HY310 panel (12.10.), until the flips say otherwise */
#define AFBC_KODI	0x0800000000000062ull	/* Kodi's modifier (G0b): AFBC 32x8, split, sparse */

#ifndef container_of
#define container_of(p, t, m) ((t *)(void *)((char *)(p) - offsetof(t, m)))
#endif
#define MIN(a, b) ((a) < (b) ? (a) : (b))

struct server;

struct import {			/* one imported dma-buf, found again by its inode (cage wraps each frame anew, G0b) */
	struct wl_list link;
	const struct wl_client *owner;	/* a key, never followed; NULL once the client is gone */
	dev_t dev;
	ino_t ino;
	uint32_t fourcc, offset, pitch;
	uint64_t modifier;
	int w, h, fd, refs;		/* fd: our dup, so the inode stays this dma-buf's while the entry lives */
	unsigned long used;		/* the least recently used goes first */
	struct gl_image *im;
};

struct wbuf {			/* one wl_buffer: ours (dma-buf) or libwayland's (wl_shm) */
	struct server *s;
	struct wl_resource *res;	/* NULL once the client destroyed it */
	struct wl_listener gone;
	struct import *imp;		/* NULL: wl_shm */
	int fd, refs;			/* fd: the dma-buf, polled for readiness; refs: pending + in the GPU */
	int w, h;
	bool used;			/* committed: a release is owed when the refs are gone */
};

struct wsurf {
	struct server *s;
	struct wl_resource *res, *xdg, *role;	/* role: the xdg_toplevel or xdg_popup */
	struct wl_resource *p_buf;		/* attached, not committed yet */
	struct wl_listener p_buf_gone;
	bool p_attached, configured, acked, mapped, toplevel, sized;	/* sized: a configure went after a wrong size */
	uint32_t serial;
	struct wl_list p_frames, p_feedback;	/* the next commit's wl_callbacks and presentation feedback */
};

struct wclient {
	struct wl_listener gone;
	struct server *s;
	bool allowed;
	int surfaces, buffers;
};

struct gpu {				/* a frame in flight: its client buffer goes back when the render fence signals */
	struct wbuf *b;
	int fd;
	struct wl_event_source *src;
};

struct server {
	struct runtime *r;
	const char *path;
	struct wl_display *dpy;
	struct wl_event_loop *loop;
	struct wl_listener created;
	int clients, nfmt, table_fd;
	struct gl_format fmt[MAX_FORMATS];
	bool kodi_format, stopping, live, ready, busy;
	dev_t dev;
	unsigned int pw, ph;
	struct wl_list imports, outputs;
	struct gl_image *shm;
	struct wsurf *top;			/* the one toplevel that is shown */
	struct wbuf *pending;			/* committed, not taken */
	struct gpu gpu[2];
	struct wl_event_source *ready_src, *flip_src, *tick, *hold;
	int flip_fd, busy_fd;
	struct wl_list frames, feedback;	/* the pending commit's callbacks and feedback */
	struct wl_list idle, flipped;		/* callbacks of buffer-less commits; feedback of the frame on its way */
	double last_flip, period, take_due, idle_due;
	uint64_t seq;
	unsigned long lru, taken, presented, discarded, busys, released, imports_made, hits, asked;
};

static void unlink_res(struct wl_resource *res)
{
	wl_list_remove(wl_resource_get_link(res));
}

static void destroy_res(struct wl_client *c, struct wl_resource *res)
{
	(void)c;
	wl_resource_destroy(res);
}

static void client_gone(struct wl_listener *l, void *data);

/* a new resource with its implementation; without memory the client is told and NULL comes back */
static struct wl_resource *resource(struct wl_client *c, const struct wl_interface *i, int v, uint32_t id,
				    const void *impl, void *data, wl_resource_destroy_func_t gone)
{
	struct wl_resource *res = wl_resource_create(c, i, v, id);

	if (!res)
		wl_client_post_no_memory(c);
	else
		wl_resource_set_implementation(res, impl, data, gone);
	return res;
}

static struct wclient *wclient_of(struct wl_client *c)
{
	struct wl_listener *l = c ? wl_client_get_destroy_listener(c, client_gone) : NULL;

	return l ? container_of(l, struct wclient, gone) : NULL;
}

/* move every resource of one list to the end of another */
static void move_all(struct wl_list *to, struct wl_list *from)
{
	wl_list_insert_list(to->prev, from);
	wl_list_init(from);
}

/* ---------------- frame callbacks, presentation feedback ---------------- */

static void frames_done(struct wl_list *list)
{
	struct wl_resource *cb, *t;
	uint32_t ms = (uint32_t)(now_s() * 1000);

	wl_resource_for_each_safe(cb, t, list) {
		wl_callback_send_done(cb, ms);
		wl_resource_destroy(cb);
	}
}

static void discard(struct server *s, struct wl_list *list)
{
	struct wl_resource *fb, *t;

	wl_resource_for_each_safe(fb, t, list) {
		wp_presentation_feedback_send_discarded(fb);
		wl_resource_destroy(fb);
		s->discarded++;
	}
}

/* the frame is on the panel: its feedback with the flip's time and the panel's period (M3 5) */
static void present(struct server *s, uint64_t ns)
{
	struct wl_resource *fb, *t, *o;
	uint64_t sec = ns / 1000000000u;
	uint32_t refresh = (uint32_t)(s->period * 1e9 * s->r->client_rate);

	wl_resource_for_each_safe(fb, t, &s->flipped) {
		wl_resource_for_each(o, &s->outputs)
			if (wl_resource_get_client(o) == wl_resource_get_client(fb))
				wp_presentation_feedback_send_sync_output(fb, o);
		wp_presentation_feedback_send_presented(fb, (uint32_t)(sec >> 32), (uint32_t)sec,
			(uint32_t)(ns % 1000000000u), refresh, (uint32_t)(s->seq >> 32), (uint32_t)s->seq,
			WP_PRESENTATION_FEEDBACK_KIND_VSYNC | WP_PRESENTATION_FEEDBACK_KIND_HW_CLOCK |
			WP_PRESENTATION_FEEDBACK_KIND_HW_COMPLETION);
		wl_resource_destroy(fb);
		s->presented++;
	}
}

/* ---------------- imports and buffers ---------------- */

static void import_free(struct server *s, struct import *imp)
{
	wl_list_remove(&imp->link);
	gl_image_free(imp->im);
	close(imp->fd);
	free(imp);
	warp_gl_idle(s->r);
}

static void import_unref(struct server *s, struct import *imp)
{
	if (--imp->refs <= 0 && !imp->owner)
		import_free(s, imp);
}

static void wbuf_free(struct wbuf *b)
{
	if (b->imp)
		import_unref(b->s, b->imp);
	if (b->fd >= 0)
		close(b->fd);
	free(b);
}

/* a reference less; at none the client gets its buffer back (or the record goes, if the client dropped it) */
static void wbuf_unref(struct wbuf *b)
{
	if (!b || --b->refs > 0)
		return;
	if (!b->res) {
		wbuf_free(b);
		return;
	}
	if (b->used) {
		wl_buffer_send_release(b->res);
		b->s->released++;
	}
	b->used = false;
}

static void wbuf_gone(struct wl_listener *l, void *data)
{
	struct wbuf *b = container_of(l, struct wbuf, gone);
	struct wclient *wc = wclient_of(wl_resource_get_client(data));

	wl_list_remove(&b->gone.link);
	if (wc)
		wc->buffers--;
	b->res = NULL;
	if (b->refs <= 0)
		wbuf_free(b);
}

static struct wbuf *wbuf_new(struct server *s, struct wl_resource *res, int fd, struct import *imp)
{
	struct wbuf *b = calloc(1, sizeof(*b));
	struct wclient *wc = wclient_of(wl_resource_get_client(res));

	if (!b)
		return NULL;
	b->s = s;
	b->res = res;
	b->fd = fd;
	b->imp = imp;
	b->w = imp ? imp->w : wl_shm_buffer_get_width(wl_shm_buffer_get(res));
	b->h = imp ? imp->h : wl_shm_buffer_get_height(wl_shm_buffer_get(res));
	b->gone.notify = wbuf_gone;
	wl_resource_add_destroy_listener(res, &b->gone);
	if (wc)
		wc->buffers++;
	return b;
}

/* ours (a dma-buf), or a wl_shm buffer seen for the first time; NULL: not a buffer */
static struct wbuf *wbuf_of(struct server *s, struct wl_resource *res)
{
	struct wl_listener *l = wl_resource_get_destroy_listener(res, wbuf_gone);

	if (l)
		return container_of(l, struct wbuf, gone);
	return wl_shm_buffer_get(res) ? wbuf_new(s, res, -1, NULL) : NULL;
}

/* the render node, opened for an import when no claim holds it open */
static bool gl_ready(struct server *s, char *why, size_t n)
{
	if (gl_is_open() || !gl_open(s->r->render_node, why, n))
		return true;
	gl_close();
	return false;
}

/* the picture of a buffer for the GPU: the import (again, after a gl_close), or the wl_shm pixels uploaded */
static struct gl_image *image_for(struct server *s, struct wbuf *b)
{
	char why[WARP_WHY];
	struct wl_shm_buffer *sb;
	struct import *imp = b->imp;
	bool ok;

	if (imp) {
		if (imp->im && gl_image_stale(imp->im)) {
			gl_image_free(imp->im);
			imp->im = NULL;
		}
		if (!imp->im)
			imp->im = gl_image_dmabuf(imp->fd, imp->fourcc, imp->modifier, imp->w, imp->h,
						  imp->offset, imp->pitch, why, sizeof(why));
		if (!imp->im)
			warn("wayland         %s", why);
		imp->used = ++s->lru;
		return imp->im;
	}
	sb = b->res ? wl_shm_buffer_get(b->res) : NULL;
	if (!sb)
		return NULL;
	if (s->shm && gl_image_stale(s->shm)) {
		gl_image_free(s->shm);
		s->shm = NULL;
	}
	if (!s->shm && !(s->shm = gl_image_shm()))
		return NULL;
	wl_shm_buffer_begin_access(sb);
	ok = gl_image_upload(s->shm, wl_shm_buffer_get_data(sb), wl_shm_buffer_get_width(sb),
			     wl_shm_buffer_get_height(sb), wl_shm_buffer_get_stride(sb), why, sizeof(why));
	wl_shm_buffer_end_access(sb);
	if (!ok)
		warn("wayland         %s", why);
	return ok ? s->shm : NULL;
}

/* ---------------- taking a buffer: the client's clock (M3 3, 4, 5) ---------------- */

static void schedule(struct server *s)
{
	double now = now_s(), due = 0;

	if (s->busy)
		due = now + BUSY_MS / 1e3;
	if (s->take_due > 0 && (!due || s->take_due < due))
		due = s->take_due;
	if (s->live && !wl_list_empty(&s->idle) && s->idle_due > 0 && (!due || s->idle_due < due))
		due = s->idle_due;
	wl_event_source_timer_update(s->tick, due > 0 ? (int)((due - now) * 1e3) + 1 : 0);
}

static void stop_ready(struct server *s)
{
	if (s->ready_src)
		wl_event_source_remove(s->ready_src);
	s->ready_src = NULL;
}

static void stop_flip(struct server *s)
{
	if (s->flip_src)
		wl_event_source_remove(s->flip_src);
	s->flip_src = NULL;
	if (s->flip_fd >= 0)
		close(s->flip_fd);
	s->flip_fd = -1;
}

static void gpu_done(struct gpu *g)
{
	if (g->src)
		wl_event_source_remove(g->src);
	if (g->fd >= 0)
		close(g->fd);
	wbuf_unref(g->b);
	g->b = NULL;
	g->fd = -1;
	g->src = NULL;
}

/* the render fence of a frame signalled: the GPU has read the client's buffer, it goes back (M3 3) */
static int gpu_cb(int fd, uint32_t mask, void *data)
{
	struct server *s = data;
	int i;

	(void)mask;
	for (i = 0; i < 2; i++)
		if (s->gpu[i].b && s->gpu[i].fd == fd)
			gpu_done(&s->gpu[i]);
	return 0;
}

static void try_take(struct server *s);

/* the flip fence: the frame is on the panel - its time, the presentation, the next take (M3 4, 5) */
static int flip_cb(int fd, uint32_t mask, void *data)
{
	struct server *s = data;
	struct sync_fence_info fi;
	struct sync_file_info info;
	uint64_t ns = 0;
	double t, dt;

	(void)mask;
	memset(&fi, 0, sizeof(fi));
	memset(&info, 0, sizeof(info));
	info.num_fences = 1;
	info.sync_fence_info = (uint64_t)(uintptr_t)&fi;
	if (!ioctl(fd, SYNC_IOC_FILE_INFO, &info) && info.status == 1)
		ns = fi.timestamp_ns;		/* CLOCK_MONOTONIC, as the presentation clock says (v3 D1) */
	if (!ns)
		ns = (uint64_t)(now_s() * 1e9);
	t = (double)ns / 1e9;
	dt = t - s->last_flip;
	if (s->last_flip > 0 && dt > 0.5 * s->period && dt < 1.5 * s->period)
		s->period += (dt - s->period) / 8;
	s->seq += s->last_flip > 0 && dt > 0 ? (uint64_t)(dt / s->period + 0.5) : 1;
	s->last_flip = t;
	present(s, ns);
	stop_flip(s);
	frames_done(&s->idle);
	s->idle_due = 0;
	try_take(s);
	schedule(s);
	return 0;
}

static void watch_flip(struct server *s, int flip)
{
	s->flip_fd = flip;
	if (flip >= 0)
		s->flip_src = wl_event_loop_add_fd(s->loop, flip, WL_EVENT_READABLE, flip_cb, s);
	if (flip >= 0 && !s->flip_src)
		stop_flip(s);
	if (flip < 0) {			/* h713-tv sent none: the time of the answer stands in */
		s->last_flip = now_s();
		present(s, (uint64_t)(s->last_flip * 1e9));
	}
}

static void take(struct server *s)
{
	struct wbuf *b = s->pending;
	struct gl_image *im = image_for(s, b);
	int render = -1, flip = -1, rc = -1, i;

	s->pending = NULL;
	s->ready = false;
	s->take_due = 0;
	if (s->busy) {			/* the frame h713-tv refused is never shown now */
		discard(s, &s->flipped);
		s->busy = false;
	}
	if (s->busy_fd >= 0)
		close(s->busy_fd);
	s->busy_fd = -1;
	if (im)
		rc = warp_client_frame(s->r, im, &render, &flip);
	s->taken++;
	frames_done(&s->frames);	/* "done" right after the take (M3 4): the client has a whole period */
	if (rc < 0 || rc == 2) {	/* not drawn, or the warp fell back: the buffer goes back */
		discard(s, &s->feedback);
		if (render >= 0)
			close(render);
		wbuf_unref(b);
		return;
	}
	move_all(&s->flipped, &s->feedback);
	if (rc == 1 && render >= 0)
		s->busy_fd = dup(render);
	for (i = 0; i < 2 && s->gpu[i].b; i++)
		;
	if (b->imp && render >= 0 && i < 2) {
		s->gpu[i].b = b;
		s->gpu[i].fd = render;
		s->gpu[i].src = wl_event_loop_add_fd(s->loop, render, WL_EVENT_READABLE, gpu_cb, s);
		if (!s->gpu[i].src)
			gpu_done(&s->gpu[i]);
	} else {			/* wl_shm was copied; no fence means glFinish ran */
		if (render >= 0)
			close(render);
		wbuf_unref(b);
	}
	if (rc == 1) {
		s->busy = true;
		s->busys++;
		return;
	}
	watch_flip(s, flip);
}

/* ready and the previous commit on the panel: take it (M3 4); at most one client frame a vsync, every second with half */
static void try_take(struct server *s)
{
	if (!s->live || !s->pending || !s->ready || s->r->pattern != PATTERN_NONE || s->flip_fd >= 0)
		return;
	if (s->gpu[0].b && s->gpu[1].b)
		return;			/* two frames still being read: never happens with the flip in between */
	if (s->r->client_rate > 1 && s->last_flip > 0 && now_s() < s->last_flip + 1.1 * s->period) {
		s->take_due = s->last_flip + 1.1 * s->period;
		schedule(s);
		return;
	}
	take(s);
}

static int ready_cb(int fd, uint32_t mask, void *data)
{
	struct server *s = data;

	(void)fd;
	(void)mask;
	stop_ready(s);
	s->ready = true;
	try_take(s);
	schedule(s);
	return 0;
}

/* the timer: "ok busy" once more (v3 D6), half rate due, callbacks of buffer-less commits */
static int tick_cb(void *data)
{
	struct server *s = data;
	int flip = -1, rc;

	if (s->busy && !(s->pending && s->ready)) {
		rc = warp_client_resend(s->r, s->busy_fd >= 0 ? dup(s->busy_fd) : -1, &flip);
		if (rc != 1) {
			s->busy = false;
			if (s->busy_fd >= 0)
				close(s->busy_fd);
			s->busy_fd = -1;
		}
		if (rc == 0)
			watch_flip(s, flip);
		else if (rc < 0)
			discard(s, &s->flipped);
	}
	if (s->live && s->idle_due > 0 && now_s() >= s->idle_due - 0.001 && s->flip_fd < 0) {
		frames_done(&s->idle);
		s->idle_due = 0;
	}
	if (s->take_due > 0 && now_s() >= s->take_due - 0.001)
		s->take_due = 0;
	try_take(s);
	schedule(s);
	return 0;
}

/* ---------------- xdg-shell: one toplevel, fullscreen ---------------- */

static void configure(struct wsurf *w)
{
	struct server *s = w->s;
	struct wl_array st;
	uint32_t *p;

	if (!w->xdg)
		return;
	if (w->toplevel && w->role) {
		wl_array_init(&st);
		if (w == s->top) {
			p = wl_array_add(&st, sizeof(*p));
			if (p)
				*p = XDG_TOPLEVEL_STATE_FULLSCREEN;
			p = wl_array_add(&st, sizeof(*p));
			if (p)
				*p = XDG_TOPLEVEL_STATE_ACTIVATED;
		}
		xdg_toplevel_send_configure(w->role, w == s->top ? (int)s->pw : 0,
					    w == s->top ? (int)s->ph : 0, &st);
		wl_array_release(&st);
	} else if (w->role) {
		xdg_popup_send_configure(w->role, 0, 0, 1, 1);
	}
	w->serial = wl_display_next_serial(s->dpy);
	xdg_surface_send_configure(w->xdg, w->serial);
	w->configured = true;
}

/* no buffer held (M3 3) but the picture is wanted again: a configure of the same size asks cage for a new frame [Ged.] (v3 D5) */
static void ask(struct server *s)
{
	if (s->top && s->top->acked) {
		configure(s->top);
		s->asked++;
	}
}

static int hold_cb(void *data)
{
	struct server *s = data;

	if (!server_shown(s))
		warp_client_gone(s->r);
	return 0;
}

/* the shown toplevel is gone (destroyed) or has no picture any more (a NULL buffer): two seconds for a new one */
static void top_lost(struct server *s, bool destroyed)
{
	if (s->pending) {
		stop_ready(s);
		discard(s, &s->feedback);
		wbuf_unref(s->pending);
		s->pending = NULL;
	}
	s->ready = false;
	if (destroyed)
		s->top = NULL;
	else
		s->top->mapped = false;
	if (s->stopping)
		return;
	if (s->live)
		wl_event_source_timer_update(s->hold, HOLD_MS);
	else
		warp_client_gone(s->r);
}

static void toplevel_destroyed(struct wl_resource *res)
{
	struct wsurf *w = wl_resource_get_user_data(res);

	if (!w)
		return;
	w->role = NULL;
	w->toplevel = false;
	if (w->s->top == w)
		top_lost(w->s, true);
}

static void popup_destroyed(struct wl_resource *res)
{
	struct wsurf *w = wl_resource_get_user_data(res);

	if (w)
		w->role = NULL;
}

static void set_parent(struct wl_client *c, struct wl_resource *r, struct wl_resource *p) { (void)c; (void)r; (void)p; }
static void set_string(struct wl_client *c, struct wl_resource *r, const char *t) { (void)c; (void)r; (void)t; }
static void show_menu(struct wl_client *c, struct wl_resource *r, struct wl_resource *seat, uint32_t serial,
		      int32_t x, int32_t y) { (void)c; (void)r; (void)seat; (void)serial; (void)x; (void)y; }
static void move_req(struct wl_client *c, struct wl_resource *r, struct wl_resource *seat, uint32_t serial)
{ (void)c; (void)r; (void)seat; (void)serial; }
static void resize_req(struct wl_client *c, struct wl_resource *r, struct wl_resource *seat, uint32_t serial,
		       uint32_t edges) { (void)c; (void)r; (void)seat; (void)serial; (void)edges; }
static void size_req(struct wl_client *c, struct wl_resource *r, int32_t w, int32_t h) { (void)c; (void)r; (void)w; (void)h; }
static void no_args(struct wl_client *c, struct wl_resource *r) { (void)c; (void)r; }
static void fullscreen_req(struct wl_client *c, struct wl_resource *r, struct wl_resource *o) { (void)c; (void)r; (void)o; }

static const struct xdg_toplevel_interface toplevel_impl = {
	.destroy = destroy_res, .set_parent = set_parent, .set_title = set_string, .set_app_id = set_string,
	.show_window_menu = show_menu, .move = move_req, .resize = resize_req, .set_max_size = size_req,
	.set_min_size = size_req, .set_maximized = no_args, .unset_maximized = no_args,
	.set_fullscreen = fullscreen_req, .unset_fullscreen = no_args, .set_minimized = no_args,
};

static void popup_grab(struct wl_client *c, struct wl_resource *r, struct wl_resource *seat, uint32_t serial)
{ (void)c; (void)r; (void)seat; (void)serial; }
static void popup_reposition(struct wl_client *c, struct wl_resource *r, struct wl_resource *pos, uint32_t token)
{ (void)c; (void)r; (void)pos; (void)token; }

static const struct xdg_popup_interface popup_impl = {
	.destroy = destroy_res, .grab = popup_grab, .reposition = popup_reposition,
};

static void get_toplevel(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	struct wsurf *w = wl_resource_get_user_data(res);
	struct wl_resource *tl;

	if (!w)
		return;
	if (w->role) {
		wl_resource_post_error(res, XDG_SURFACE_ERROR_ALREADY_CONSTRUCTED, "the surface has a role already");
		return;
	}
	tl = resource(c, &xdg_toplevel_interface, wl_resource_get_version(res), id, &toplevel_impl, w,
		      toplevel_destroyed);
	if (!tl)
		return;
	w->role = tl;
	w->toplevel = true;
	if (wl_resource_get_version(tl) >= XDG_TOPLEVEL_WM_CAPABILITIES_SINCE_VERSION) {
		struct wl_array caps;
		uint32_t *p;

		wl_array_init(&caps);
		p = wl_array_add(&caps, sizeof(*p));
		if (p)
			*p = XDG_TOPLEVEL_WM_CAPABILITIES_FULLSCREEN;
		xdg_toplevel_send_wm_capabilities(tl, &caps);
		wl_array_release(&caps);
	}
	if (!w->s->top)
		w->s->top = w;			/* the first toplevel wins (v3 section 7) */
	else
		xdg_toplevel_send_close(tl);	/* every further one is asked to close at once */
}

static void get_popup(struct wl_client *c, struct wl_resource *res, uint32_t id, struct wl_resource *parent,
		      struct wl_resource *positioner)
{
	struct wsurf *w = wl_resource_get_user_data(res);
	struct wl_resource *p;

	(void)parent;
	(void)positioner;
	if (!w)
		return;
	if (w->role) {
		wl_resource_post_error(res, XDG_SURFACE_ERROR_ALREADY_CONSTRUCTED, "the surface has a role already");
		return;
	}
	p = resource(c, &xdg_popup_interface, wl_resource_get_version(res), id, &popup_impl, w, popup_destroyed);
	if (!p)
		return;
	w->role = p;
	xdg_popup_send_popup_done(p);		/* no popups on a projector: gone before they show */
}

static void set_geometry(struct wl_client *c, struct wl_resource *r, int32_t x, int32_t y, int32_t w, int32_t h)
{ (void)c; (void)r; (void)x; (void)y; (void)w; (void)h; }

static void ack_configure(struct wl_client *c, struct wl_resource *res, uint32_t serial)
{
	struct wsurf *w = wl_resource_get_user_data(res);

	(void)c;
	if (w && w->configured && serial == w->serial)
		w->acked = true;
}

static const struct xdg_surface_interface xdg_surface_impl = {
	.destroy = destroy_res, .get_toplevel = get_toplevel, .get_popup = get_popup,
	.set_window_geometry = set_geometry, .ack_configure = ack_configure,
};

static void xdg_surface_destroyed(struct wl_resource *res)
{
	struct wsurf *w = wl_resource_get_user_data(res);

	if (w)
		w->xdg = NULL;
}

static void pos_size(struct wl_client *c, struct wl_resource *r, int32_t w, int32_t h) { (void)c; (void)r; (void)w; (void)h; }
static void pos_rect(struct wl_client *c, struct wl_resource *r, int32_t x, int32_t y, int32_t w, int32_t h)
{ (void)c; (void)r; (void)x; (void)y; (void)w; (void)h; }
static void pos_u32(struct wl_client *c, struct wl_resource *r, uint32_t v) { (void)c; (void)r; (void)v; }

static const struct xdg_positioner_interface positioner_impl = {
	.destroy = destroy_res, .set_size = pos_size, .set_anchor_rect = pos_rect, .set_anchor = pos_u32,
	.set_gravity = pos_u32, .set_constraint_adjustment = pos_u32, .set_offset = size_req,
	.set_reactive = no_args, .set_parent_size = pos_size, .set_parent_configure = pos_u32,
};

static void create_positioner(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	resource(c, &xdg_positioner_interface, wl_resource_get_version(res), id, &positioner_impl, NULL, NULL);
}

static void get_xdg_surface(struct wl_client *c, struct wl_resource *res, uint32_t id, struct wl_resource *surface)
{
	struct wsurf *w = wl_resource_get_user_data(surface);
	struct wl_resource *x;

	if (w->xdg || w->role) {
		wl_resource_post_error(res, XDG_WM_BASE_ERROR_ROLE, "the surface has a role already");
		return;
	}
	x = resource(c, &xdg_surface_interface, wl_resource_get_version(res), id, &xdg_surface_impl, w,
		     xdg_surface_destroyed);
	if (x)
		w->xdg = x;
}

static void pong(struct wl_client *c, struct wl_resource *r, uint32_t serial) { (void)c; (void)r; (void)serial; }

static const struct xdg_wm_base_interface wm_base_impl = {
	.destroy = destroy_res, .create_positioner = create_positioner, .get_xdg_surface = get_xdg_surface,
	.pong = pong,
};

static void bind_wm_base(struct wl_client *c, void *data, uint32_t version, uint32_t id)
{
	resource(c, &xdg_wm_base_interface, (int)MIN(version, 5), id, &wm_base_impl, data, NULL);
}

/* ---------------- wl_surface, wl_region, wl_compositor ---------------- */

static void p_buf_gone(struct wl_listener *l, void *data)
{
	struct wsurf *w = container_of(l, struct wsurf, p_buf_gone);

	(void)data;
	wl_list_remove(&l->link);
	w->p_buf = NULL;
}

static void surface_attach(struct wl_client *c, struct wl_resource *res, struct wl_resource *buffer,
			   int32_t x, int32_t y)
{
	struct wsurf *w = wl_resource_get_user_data(res);

	(void)c;
	(void)x;
	(void)y;
	if (w->p_buf)
		wl_list_remove(&w->p_buf_gone.link);
	w->p_buf = buffer;
	w->p_attached = true;
	if (buffer) {
		w->p_buf_gone.notify = p_buf_gone;
		wl_resource_add_destroy_listener(buffer, &w->p_buf_gone);
	}
}

static void surface_rect(struct wl_client *c, struct wl_resource *r, int32_t x, int32_t y, int32_t w, int32_t h)
{ (void)c; (void)r; (void)x; (void)y; (void)w; (void)h; }	/* the warp draws the whole picture: damage is moot */
static void surface_region(struct wl_client *c, struct wl_resource *r, struct wl_resource *g) { (void)c; (void)r; (void)g; }
static void surface_int(struct wl_client *c, struct wl_resource *r, int32_t v) { (void)c; (void)r; (void)v; }

static void surface_frame(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	struct wsurf *w = wl_resource_get_user_data(res);
	struct wl_resource *cb = resource(c, &wl_callback_interface, 1, id, NULL, NULL, unlink_res);

	if (cb)
		wl_list_insert(w->p_frames.prev, wl_resource_get_link(cb));
}

/* a new pending buffer for the shown toplevel: a never-taken predecessor goes back at once (v3 section 3) */
static void set_pending(struct server *s, struct wbuf *b)
{
	if (s->pending == b) {		/* the same buffer again, not taken yet: only its feedback is new */
		discard(s, &s->feedback);
		return;
	}
	if (s->pending) {
		stop_ready(s);
		discard(s, &s->feedback);
		wbuf_unref(s->pending);
	}
	s->pending = b;
	b->refs++;
	b->used = true;
	s->ready = b->fd < 0;
	if (!s->ready)
		s->ready_src = wl_event_loop_add_fd(s->loop, b->fd, WL_EVENT_READABLE, ready_cb, s);
	if (!s->ready && !s->ready_src)
		s->ready = true;
}

static void surface_commit(struct wl_client *c, struct wl_resource *res)
{
	struct wsurf *w = wl_resource_get_user_data(res);
	struct server *s = w->s;
	struct wbuf *b = NULL;
	struct wl_shm_buffer *sb;
	bool shown = w == s->top;

	(void)c;
	if (w->p_attached && w->p_buf) {
		b = wbuf_of(s, w->p_buf);
		if (!b) {
			wl_resource_post_error(res, WL_DISPLAY_ERROR_INVALID_OBJECT, "not a buffer of this server");
			return;
		}
		sb = b->imp ? NULL : wl_shm_buffer_get(w->p_buf);
		if (sb && ((unsigned int)wl_shm_buffer_get_width(sb) > s->pw ||
			   (unsigned int)wl_shm_buffer_get_height(sb) > s->ph)) {
			wl_resource_post_error(res, WL_SURFACE_ERROR_INVALID_SIZE, "larger than the panel %ux%u",
					       s->pw, s->ph);
			return;
		}
	}
	if (w->xdg && !w->role && !w->configured) {
		wl_resource_post_error(w->xdg, XDG_SURFACE_ERROR_NOT_CONSTRUCTED, "a commit before get_toplevel");
		return;
	}
	if (w->xdg && (!w->configured || (b && !w->acked))) {
		if (b) {
			wl_resource_post_error(w->xdg, XDG_SURFACE_ERROR_UNCONFIGURED_BUFFER,
					       "a buffer before the first configure was acknowledged");
			return;
		}
		if (!w->configured)
			configure(w);		/* the initial commit gets its configure */
	}
	if (w->p_buf)
		wl_list_remove(&w->p_buf_gone.link);
	/*
	 * cage misses the first configure: it comes while wlroots is still making its output, before cage listens for the
	 * request (G1, 15.10.2026: configure 1920x1080, then 1280x720 buffers and Kodi at 1280x720). Weston's second
	 * configure on the first buffer made the size right (G0b); so here: once more whenever the size is not the panel's.
	 */
	if (shown && b && (b->w != (int)s->pw || b->h != (int)s->ph)) {
		if (!w->sized)
			configure(w);
		w->sized = true;
	} else if (shown && b) {
		w->sized = false;
	}
	if (shown && w->p_attached && b) {
		set_pending(s, b);
		move_all(&s->frames, &w->p_frames);
		move_all(&s->feedback, &w->p_feedback);
	} else if (shown) {
		if (s->idle_due <= 0)
			s->idle_due = now_s() + s->period;
		move_all(&s->idle, &w->p_frames);
		move_all(s->flip_fd >= 0 ? &s->flipped : &s->feedback, &w->p_feedback);
		if (!s->pending)
			discard(s, &s->feedback);
	} else if (b) {			/* nobody sees this surface: the buffer goes straight back */
		b->refs++;
		b->used = true;
		wbuf_unref(b);
	}
	if (shown && w->p_attached && !b && w->mapped)
		top_lost(s, false);
	w->p_attached = false;
	w->p_buf = NULL;
	if (shown && b && !w->mapped) {
		w->mapped = true;
		wl_event_source_timer_update(s->hold, 0);
		if (!s->live)
			warp_client_shown(s->r);	/* claims the panel; engaged, it takes the buffer */
	}
	try_take(s);
	schedule(s);
}

static const struct wl_surface_interface surface_impl = {
	.destroy = destroy_res, .attach = surface_attach, .damage = surface_rect, .frame = surface_frame,
	.set_opaque_region = surface_region, .set_input_region = surface_region, .commit = surface_commit,
	.set_buffer_transform = surface_int, .set_buffer_scale = surface_int, .damage_buffer = surface_rect,
	.offset = size_req,
};

static void unlink_all(struct wl_list *list)
{
	while (!wl_list_empty(list)) {
		struct wl_list *l = list->next;

		wl_list_remove(l);
		wl_list_init(l);
	}
}

static void surface_destroyed(struct wl_resource *res)
{
	struct wsurf *w = wl_resource_get_user_data(res);
	struct wclient *wc = wclient_of(wl_resource_get_client(res));

	if (wc)
		wc->surfaces--;
	if (w->p_buf)
		wl_list_remove(&w->p_buf_gone.link);
	unlink_all(&w->p_frames);
	unlink_all(&w->p_feedback);
	if (w->xdg)
		wl_resource_set_user_data(w->xdg, NULL);
	if (w->role)
		wl_resource_set_user_data(w->role, NULL);
	if (w->s->top == w)
		top_lost(w->s, true);
	free(w);
}

static void create_surface(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	struct server *s = wl_resource_get_user_data(res);
	struct wclient *wc = wclient_of(c);
	struct wsurf *w;

	if (wc && wc->surfaces >= MAX_SURFACES) {
		wl_resource_post_error(res, WL_DISPLAY_ERROR_NO_MEMORY, "more than %d surfaces", MAX_SURFACES);
		return;
	}
	w = calloc(1, sizeof(*w));
	if (!w) {
		wl_client_post_no_memory(c);
		return;
	}
	w->s = s;
	wl_list_init(&w->p_frames);
	wl_list_init(&w->p_feedback);
	w->res = resource(c, &wl_surface_interface, wl_resource_get_version(res), id, &surface_impl, w,
			  surface_destroyed);
	if (!w->res) {
		free(w);
		return;
	}
	if (wc)
		wc->surfaces++;
}

static const struct wl_region_interface region_impl = {
	.destroy = destroy_res, .add = surface_rect, .subtract = surface_rect,
};

static void create_region(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	(void)res;
	resource(c, &wl_region_interface, 1, id, &region_impl, NULL, NULL);
}

static const struct wl_compositor_interface compositor_impl = {
	.create_surface = create_surface, .create_region = create_region,
};

static void bind_compositor(struct wl_client *c, void *data, uint32_t version, uint32_t id)
{
	resource(c, &wl_compositor_interface, (int)MIN(version, 6), id, &compositor_impl, data, NULL);
}

/* ---------------- wl_output, wp_presentation ---------------- */

static void output_send(struct server *s, struct wl_resource *o)
{
	int v = wl_resource_get_version(o);

	wl_output_send_geometry(o, 0, 0, 0, 0, WL_OUTPUT_SUBPIXEL_UNKNOWN, "H713", "projector panel",
				WL_OUTPUT_TRANSFORM_NORMAL);
	wl_output_send_mode(o, WL_OUTPUT_MODE_CURRENT | WL_OUTPUT_MODE_PREFERRED, (int)s->pw, (int)s->ph,
			    (int)(1e3 / (s->period * s->r->client_rate) + 0.5));
	if (v >= WL_OUTPUT_SCALE_SINCE_VERSION)
		wl_output_send_scale(o, 1);
	if (v >= WL_OUTPUT_NAME_SINCE_VERSION) {
		wl_output_send_name(o, "H713-1");
		wl_output_send_description(o, "the projector's panel, through the keystone warp");
	}
	if (v >= WL_OUTPUT_DONE_SINCE_VERSION)
		wl_output_send_done(o);
}

static const struct wl_output_interface output_impl = { .release = destroy_res };

static void bind_output(struct wl_client *c, void *data, uint32_t version, uint32_t id)
{
	struct server *s = data;
	struct wl_resource *o = resource(c, &wl_output_interface, (int)MIN(version, 4), id, &output_impl, s,
					 unlink_res);

	if (!o)
		return;
	wl_list_insert(&s->outputs, wl_resource_get_link(o));
	output_send(s, o);
}

static void presentation_feedback(struct wl_client *c, struct wl_resource *res, struct wl_resource *surface,
				  uint32_t id)
{
	struct wsurf *w = wl_resource_get_user_data(surface);
	struct wl_resource *fb = resource(c, &wp_presentation_feedback_interface, wl_resource_get_version(res), id,
					  NULL, NULL, unlink_res);

	if (fb)
		wl_list_insert(w->p_feedback.prev, wl_resource_get_link(fb));
}

static const struct wp_presentation_interface presentation_impl = {
	.destroy = destroy_res, .feedback = presentation_feedback,
};

static void bind_presentation(struct wl_client *c, void *data, uint32_t version, uint32_t id)
{
	struct wl_resource *res = resource(c, &wp_presentation_interface,
					   (int)MIN(version, (uint32_t)wp_presentation_interface.version), id,
					   &presentation_impl, data, NULL);

	if (!res)
		return;
	/* CLOCK_MONOTONIC and nothing else: wlroots drops a host presentation with another clock (G0b: clock_id 4,
	 * then destroy), and the fence timestamps are that clock (v3 D1) */
	wp_presentation_send_clock_id(res, CLOCK_MONOTONIC);
}

/* ---------------- linux-dmabuf v4 ---------------- */

struct params {
	struct server *s;
	int fd;
	uint32_t offset, pitch;
	uint64_t modifier;
	bool set, used, extra;
};

static void params_add(struct wl_client *c, struct wl_resource *res, int32_t fd, uint32_t idx, uint32_t offset,
		       uint32_t stride, uint32_t hi, uint32_t lo)
{
	struct params *p = wl_resource_get_user_data(res);

	(void)c;
	if (p->used || idx >= 4 || (idx == 0 && p->set)) {
		close(fd);
		wl_resource_post_error(res, p->used ? ZWP_LINUX_BUFFER_PARAMS_V1_ERROR_ALREADY_USED :
				       idx >= 4 ? ZWP_LINUX_BUFFER_PARAMS_V1_ERROR_PLANE_IDX :
				       ZWP_LINUX_BUFFER_PARAMS_V1_ERROR_PLANE_SET, "plane %u", idx);
		return;
	}
	if (idx > 0) {			/* the RGB formats here have one plane: create says so */
		close(fd);
		p->extra = true;
		return;
	}
	p->fd = fd;
	p->offset = offset;
	p->pitch = stride;
	p->modifier = (uint64_t)hi << 32 | lo;
	p->set = true;
}

/* the import of this dma-buf: found again by its inode, else made - at most MAX_IMPORTS per client, unused ones go first */
static struct import *import_get(struct server *s, struct wl_client *c, const struct params *p, uint32_t fourcc,
				 int w, int h, char *why, size_t n)
{
	struct import *imp, *lru = NULL;
	struct stat st;
	int count = 0;

	if (fstat(p->fd, &st)) {
		snprintf(why, n, "fstat: %s", strerror(errno));
		return NULL;
	}
	wl_list_for_each(imp, &s->imports, link) {
		if (imp->owner != c)
			continue;
		if (imp->dev == st.st_dev && imp->ino == st.st_ino && imp->fourcc == fourcc &&
		    imp->modifier == p->modifier && imp->w == w && imp->h == h && imp->offset == p->offset &&
		    imp->pitch == p->pitch) {
			imp->refs++;
			imp->used = ++s->lru;
			s->hits++;
			return imp;
		}
		count++;
		if (imp->refs <= 0 && (!lru || imp->used < lru->used))
			lru = imp;
	}
	if (count >= MAX_IMPORTS && !lru) {
		snprintf(why, n, "more than %d dma-bufs in use", MAX_IMPORTS);
		return NULL;
	}
	if (count >= MAX_IMPORTS)
		import_free(s, lru);
	if (!gl_ready(s, why, n))
		return NULL;
	imp = calloc(1, sizeof(*imp));
	if (!imp || !(imp->im = gl_image_dmabuf(p->fd, fourcc, p->modifier, w, h, p->offset, p->pitch, why, n))) {
		free(imp);
		warp_gl_idle(s->r);
		return NULL;
	}
	imp->owner = c;
	imp->dev = st.st_dev;
	imp->ino = st.st_ino;
	imp->fourcc = fourcc;
	imp->modifier = p->modifier;
	imp->offset = p->offset;
	imp->pitch = p->pitch;
	imp->w = w;
	imp->h = h;
	imp->fd = fcntl(p->fd, F_DUPFD_CLOEXEC, 0);
	imp->refs = 1;
	imp->used = ++s->lru;
	wl_list_insert(&s->imports, &imp->link);
	s->imports_made++;
	return imp;
}

static const struct wl_buffer_interface buffer_impl = { .destroy = destroy_res };

/* checked before anything is imported (v3 section 3): table, size, pitch, the dma-buf's length */
static void params_create(struct wl_client *c, struct wl_resource *res, uint32_t id, int32_t w, int32_t h,
			  uint32_t fourcc, uint32_t flags)
{
	struct params *p = wl_resource_get_user_data(res);
	struct server *s = p->s;
	struct wclient *wc = wclient_of(c);
	struct wl_resource *br;
	struct import *imp = NULL;
	char why[WARP_WHY] = "";
	off_t size;
	int i;

	if (p->used) {
		wl_resource_post_error(res, ZWP_LINUX_BUFFER_PARAMS_V1_ERROR_ALREADY_USED, "used already");
		return;
	}
	p->used = true;
	if (!p->set) {
		wl_resource_post_error(res, ZWP_LINUX_BUFFER_PARAMS_V1_ERROR_INCOMPLETE, "no plane 0");
		return;
	}
	for (i = 0; i < s->nfmt; i++)
		if (s->fmt[i].fourcc == fourcc && s->fmt[i].modifier == p->modifier)
			break;
	size = lseek(p->fd, 0, SEEK_END);
	if (i == s->nfmt)
		snprintf(why, sizeof(why), "%.4s modifier 0x%llx is not offered", (const char *)&fourcc,
			 (unsigned long long)p->modifier);
	else if (flags || p->extra)
		snprintf(why, sizeof(why), "one plane, no flags (y-invert, interlaced)");
	else if (w < 1 || h < 1 || (unsigned int)w > s->pw || (unsigned int)h > s->ph)
		snprintf(why, sizeof(why), "%dx%d does not fit the panel %ux%u", w, h, s->pw, s->ph);
	else if (p->modifier == DRM_FORMAT_MOD_LINEAR &&
		 (p->pitch % 64 || p->pitch < (uint32_t)w * (fourcc == DRM_FORMAT_RGB565 ? 2 : 4) ||
		  (size > 0 && p->offset + (uint64_t)p->pitch * (uint64_t)h > (uint64_t)size)))
		snprintf(why, sizeof(why), "pitch %u for %d pixels (a multiple of 64, inside the dma-buf)", p->pitch, w);
	else if (size > 0 && p->offset >= (uint64_t)size)
		snprintf(why, sizeof(why), "offset %u past the dma-buf", p->offset);
	else if (wc && wc->buffers >= MAX_BUFFERS)
		snprintf(why, sizeof(why), "more than %d wl_buffers", MAX_BUFFERS);
	else
		imp = import_get(s, c, p, fourcc, w, h, why, sizeof(why));
	if (!imp) {
		if (id)
			wl_resource_post_error(res, ZWP_LINUX_BUFFER_PARAMS_V1_ERROR_INVALID_WL_BUFFER, "%s", why);
		else
			zwp_linux_buffer_params_v1_send_failed(res);
		return;
	}
	br = resource(c, &wl_buffer_interface, 1, id, &buffer_impl, NULL, NULL);
	if (!br || !wbuf_new(s, br, p->fd, imp)) {
		if (br)
			wl_resource_destroy(br);
		import_unref(s, imp);
		return;
	}
	p->fd = -1;			/* the buffer's now */
	if (!id)
		zwp_linux_buffer_params_v1_send_created(res, br);
}

static void params_create_req(struct wl_client *c, struct wl_resource *res, int32_t w, int32_t h, uint32_t f,
			      uint32_t flags)
{
	params_create(c, res, 0, w, h, f, flags);
}

static void params_immed(struct wl_client *c, struct wl_resource *res, uint32_t id, int32_t w, int32_t h, uint32_t f,
			 uint32_t flags)
{
	params_create(c, res, id, w, h, f, flags);
}

static const struct zwp_linux_buffer_params_v1_interface params_impl = {
	.destroy = destroy_res, .add = params_add, .create = params_create_req, .create_immed = params_immed,
};

static void params_destroyed(struct wl_resource *res)
{
	struct params *p = wl_resource_get_user_data(res);

	if (p->fd >= 0)
		close(p->fd);
	free(p);
}

static void create_params(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	struct params *p = calloc(1, sizeof(*p));

	if (!p) {
		wl_client_post_no_memory(c);
		return;
	}
	p->fd = -1;
	p->s = wl_resource_get_user_data(res);
	if (!resource(c, &zwp_linux_buffer_params_v1_interface, wl_resource_get_version(res), id, &params_impl, p,
		      params_destroyed))
		free(p);
}

static const struct zwp_linux_dmabuf_feedback_v1_interface feedback_impl = { .destroy = destroy_res };

/* the table as M3 1 asks: one tranche, no scanout flag, renderD128 as main and target device */
static void feedback_new(struct wl_client *c, struct wl_resource *res, uint32_t id)
{
	struct server *s = wl_resource_get_user_data(res);
	struct wl_resource *fb = resource(c, &zwp_linux_dmabuf_feedback_v1_interface, wl_resource_get_version(res),
					  id, &feedback_impl, NULL, NULL);
	struct wl_array dev, idx;
	uint16_t *k;
	int i;

	if (!fb)
		return;
	zwp_linux_dmabuf_feedback_v1_send_format_table(fb, s->table_fd, (uint32_t)(s->nfmt * 16));
	wl_array_init(&dev);
	wl_array_init(&idx);
	if (wl_array_add(&dev, sizeof(dev_t)))
		memcpy(dev.data, &s->dev, sizeof(dev_t));
	for (i = 0; i < s->nfmt; i++)
		if ((k = wl_array_add(&idx, sizeof(*k))))
			*k = (uint16_t)i;
	zwp_linux_dmabuf_feedback_v1_send_main_device(fb, &dev);
	zwp_linux_dmabuf_feedback_v1_send_tranche_target_device(fb, &dev);
	zwp_linux_dmabuf_feedback_v1_send_tranche_flags(fb, 0);
	zwp_linux_dmabuf_feedback_v1_send_tranche_formats(fb, &idx);
	zwp_linux_dmabuf_feedback_v1_send_tranche_done(fb);
	zwp_linux_dmabuf_feedback_v1_send_done(fb);
	wl_array_release(&dev);
	wl_array_release(&idx);
}

static void surface_feedback(struct wl_client *c, struct wl_resource *res, uint32_t id, struct wl_resource *surface)
{
	(void)surface;
	feedback_new(c, res, id);	/* one panel, one GPU: every surface gets the same */
}

static const struct zwp_linux_dmabuf_v1_interface dmabuf_impl = {
	.destroy = destroy_res, .create_params = create_params, .get_default_feedback = feedback_new,
	.get_surface_feedback = surface_feedback,
};

static void bind_dmabuf(struct wl_client *c, void *data, uint32_t version, uint32_t id)
{
	struct server *s = data;
	struct wl_resource *res = resource(c, &zwp_linux_dmabuf_v1_interface, (int)MIN(version, 4), id, &dmabuf_impl,
					   s, NULL);
	int i;

	if (!res)
		return;
	for (i = 0; version < 4 && i < s->nfmt; i++)	/* before v4 the formats come with the bind */
		if (version >= 3)
			zwp_linux_dmabuf_v1_send_modifier(res, s->fmt[i].fourcc, (uint32_t)(s->fmt[i].modifier >> 32),
							  (uint32_t)s->fmt[i].modifier);
		else if (!i || s->fmt[i].fourcc != s->fmt[i - 1].fourcc)
			zwp_linux_dmabuf_v1_send_format(res, s->fmt[i].fourcc);
}

/* ---------------- clients ---------------- */

static void client_gone(struct wl_listener *l, void *data)
{
	struct wclient *wc = container_of(l, struct wclient, gone);
	struct server *s = wc->s;
	struct import *imp, *t;

	wl_list_remove(&wc->gone.link);
	if (wc->allowed)
		s->clients--;
	wl_list_for_each_safe(imp, t, &s->imports, link)
		if (imp->owner == data) {
			imp->owner = NULL;
			if (imp->refs <= 0)
				import_free(s, imp);
		}
	free(wc);
}

static void client_created(struct wl_listener *l, void *data)
{
	struct server *s = container_of(l, struct server, created);
	struct wclient *wc = calloc(1, sizeof(*wc));

	if (!wc)
		return;			/* without a record the filter shows it nothing */
	wc->s = s;
	wc->allowed = s->clients < MAX_CLIENTS;
	if (wc->allowed)
		s->clients++;
	else
		warn("wayland         a connection beyond %d sees no globals", MAX_CLIENTS);
	wc->gone.notify = client_gone;
	wl_client_add_destroy_listener(data, &wc->gone);
}

static bool global_filter(const struct wl_client *c, const struct wl_global *g, void *data)
{
	struct wclient *wc = wclient_of((struct wl_client *)c);

	(void)g;
	(void)data;
	return wc && wc->allowed;
}

/* ---------------- the server ---------------- */

/* the panel before the first claim: the connected connector's first mode (read, card1 is never opened), else
 * 1920x1080; a claim corrects it (v3 D3) */
static void panel_guess(struct server *s)
{
	glob_t g;
	size_t i;

	s->pw = 1920;
	s->ph = 1080;
	if (glob("/sys/class/drm/card*-*/status", 0, NULL, &g))
		return;
	for (i = 0; i < g.gl_pathc; i++) {
		char path[512], line[32] = "";
		unsigned int w, h;
		FILE *f = fopen(g.gl_pathv[i], "r");

		if (!f)
			continue;
		if (!fgets(line, sizeof(line), f))
			line[0] = '\0';
		fclose(f);
		if (strncmp(line, "connected", 9))
			continue;
		snprintf(path, sizeof(path), "%.*smodes", (int)(strlen(g.gl_pathv[i]) - 6), g.gl_pathv[i]);
		f = fopen(path, "r");
		if (f && fscanf(f, "%ux%u", &w, &h) == 2 && w && h) {
			s->pw = w;
			s->ph = h;
		}
		if (f)
			fclose(f);
		break;
	}
	globfree(&g);
}

/* the format table out of EGL (M3 1) into a sealed memfd; renderD128's device number */
static bool formats(struct server *s)
{
	char why[WARP_WHY] = "";
	struct stat st;
	int i;

	if (gl_ready(s, why, sizeof(why)))
		s->nfmt = gl_formats(s->fmt, MAX_FORMATS, why, sizeof(why));
	warp_gl_idle(s->r);
	if (s->nfmt <= 0 || stat(s->r->render_node, &st)) {
		warn("wayland         no dma-buf formats (%s) -- wl_shm only", why[0] ? why : strerror(errno));
		s->nfmt = 0;
		return false;
	}
	s->dev = st.st_rdev;
	s->table_fd = memfd_create("h713-warp-formats", MFD_CLOEXEC | MFD_ALLOW_SEALING);
	for (i = 0; s->table_fd >= 0 && i < s->nfmt; i++) {
		struct { uint32_t format, pad; uint64_t modifier; } e = { s->fmt[i].fourcc, 0, s->fmt[i].modifier };

		if (write(s->table_fd, &e, sizeof(e)) != (ssize_t)sizeof(e))
			break;
		if (e.format == DRM_FORMAT_ARGB2101010 && e.modifier == AFBC_KODI)
			s->kodi_format = true;
	}
	if (s->table_fd < 0 || i < s->nfmt) {
		warn("wayland         the format table: %s -- wl_shm only", strerror(errno));
		s->nfmt = 0;
		return false;
	}
	fcntl(s->table_fd, F_ADD_SEALS, F_SEAL_SHRINK | F_SEAL_GROW | F_SEAL_WRITE | F_SEAL_SEAL);
	if (!s->kodi_format)
		warn("wayland         EGL offers no AR30 with AFBC 0x%llx: cage will copy Kodi's picture (5 ms, F)",
		     (unsigned long long)AFBC_KODI);
	return true;
}

static int listen_on(const char *path)
{
	struct sockaddr_un a;
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);

	memset(&a, 0, sizeof(a));
	a.sun_family = AF_UNIX;
	if (fd < 0 || strlen(path) >= sizeof(a.sun_path)) {
		if (fd >= 0)
			close(fd);
		return -1;
	}
	snprintf(a.sun_path, sizeof(a.sun_path), "%s", path);
	unlink(path);
	if (bind(fd, (struct sockaddr *)&a, sizeof(a)) || chmod(path, 0660) || listen(fd, 4)) {
		close(fd);
		return -1;
	}
	return fd;
}

struct server *server_start(const char *path, struct runtime *r)
{
	struct server *s = calloc(1, sizeof(*s));
	int fd;

	if (!s || !(s->dpy = wl_display_create())) {
		warn("wayland         no server: out of memory");
		free(s);
		return NULL;
	}
	s->r = r;
	s->path = path;
	s->loop = wl_display_get_event_loop(s->dpy);
	s->table_fd = s->flip_fd = s->busy_fd = -1;
	s->gpu[0].fd = s->gpu[1].fd = -1;
	s->period = PERIOD_S;
	wl_list_init(&s->imports);
	wl_list_init(&s->outputs);
	wl_list_init(&s->frames);
	wl_list_init(&s->feedback);
	wl_list_init(&s->idle);
	wl_list_init(&s->flipped);
	panel_guess(s);
	fd = listen_on(path);
	if (fd < 0 || wl_display_add_socket_fd(s->dpy, fd)) {
		warn("wayland         %s: %s -- no Wayland server, the ring works as before", path, strerror(errno));
		if (fd >= 0)
			close(fd);
		wl_display_destroy(s->dpy);
		free(s);
		return NULL;
	}
	wl_display_set_global_filter(s->dpy, global_filter, s);
	s->created.notify = client_created;
	wl_display_add_client_created_listener(s->dpy, &s->created);
	wl_display_init_shm(s->dpy);
	wl_global_create(s->dpy, &wl_compositor_interface, MIN(6, wl_compositor_interface.version), s, bind_compositor);
	wl_global_create(s->dpy, &xdg_wm_base_interface, 5, s, bind_wm_base);
	wl_global_create(s->dpy, &wl_output_interface, 4, s, bind_output);
	wl_global_create(s->dpy, &wp_presentation_interface, MIN(2, wp_presentation_interface.version), s,
			 bind_presentation);
	if (formats(s))
		wl_global_create(s->dpy, &zwp_linux_dmabuf_v1_interface, 4, s, bind_dmabuf);
	s->tick = wl_event_loop_add_timer(s->loop, tick_cb, s);
	s->hold = wl_event_loop_add_timer(s->loop, hold_cb, s);
	info("wayland         %s: %ux%u, %d dma-buf formats (Kodi's AR30 AFBC %s), wl_shm, xdg-shell, presentation; client rate %s",
	     path, s->pw, s->ph, s->nfmt, s->kodi_format ? "offered" : "missing",
	     r->client_rate > 1 ? "half" : "full");
	return s;
}

void server_stop(struct server *s)
{
	struct import *imp, *t;
	int i;

	if (!s)
		return;
	s->stopping = true;
	s->live = false;
	wl_display_destroy_clients(s->dpy);
	stop_flip(s);
	for (i = 0; i < 2; i++)
		if (s->gpu[i].b)
			gpu_done(&s->gpu[i]);
	wl_display_destroy(s->dpy);
	wl_list_for_each_safe(imp, t, &s->imports, link) {
		wl_list_remove(&imp->link);
		gl_image_free(imp->im);
		close(imp->fd);
		free(imp);
	}
	gl_image_free(s->shm);
	if (s->table_fd >= 0)
		close(s->table_fd);
	if (s->busy_fd >= 0)
		close(s->busy_fd);
	unlink(s->path);
	free(s);
}

int server_fd(const struct server *s)
{
	return s ? wl_event_loop_get_fd(s->loop) : -1;
}

void server_dispatch(struct server *s)
{
	if (!s)
		return;
	wl_event_loop_dispatch(s->loop, 0);
	wl_display_flush_clients(s->dpy);
}

void server_flush(struct server *s)
{
	if (s)
		wl_display_flush_clients(s->dpy);
}

bool server_shown(const struct server *s)
{
	return s && s->top && s->top->acked && s->top->mapped;
}

bool server_busy(const struct server *s)
{
	return s && (!wl_list_empty(&s->imports) || s->shm);
}

void server_engaged(struct server *s, bool on)
{
	if (!s)
		return;
	s->live = on;
	if (!on) {			/* h713-tv let go: nothing more is presented, the client pauses (no callbacks) */
		stop_flip(s);
		discard(s, &s->flipped);
		s->busy = false;
		if (s->busy_fd >= 0)
			close(s->busy_fd);
		s->busy_fd = -1;
		s->take_due = 0;
		wl_event_source_timer_update(s->tick, 0);
		return;
	}
	s->last_flip = 0;
	if (s->pending)
		try_take(s);		/* or when it is ready */
	else
		ask(s);			/* the last picture was released (M3 3): a new one, please (v3 D5) */
	if (s->idle_due > 0)
		s->idle_due = now_s();
	schedule(s);
}

void server_panel(struct server *s, unsigned int w, unsigned int h)
{
	struct wl_resource *o;

	if (!s || (w == s->pw && h == s->ph) || !w || !h)
		return;
	info("wayland         the panel is %ux%u (was %ux%u): output and configure follow", w, h, s->pw, s->ph);
	s->pw = w;
	s->ph = h;
	wl_resource_for_each(o, &s->outputs)
		output_send(s, o);
	if (s->top && s->top->configured)
		configure(s->top);
}

void server_redraw(struct server *s)
{
	if (!s || !s->live)
		return;
	if (s->pending && s->ready)
		try_take(s);
	else if (s->r->pattern == PATTERN_NONE)
		ask(s);
	schedule(s);
}

void server_status(const struct server *s, struct textbuf *t)
{
	if (!s) {
		text_add(t, "wayland         no server\n");
		return;
	}
	text_add(t, "wayland         %s: %d client%s, %s; %d dma-buf formats, Kodi's AR30 AFBC %s\n", s->path,
		 s->clients, s->clients == 1 ? "" : "s",
		 !s->top ? "no toplevel" : server_shown(s) ? (s->live ? "a toplevel on the panel" :
							      "a toplevel waiting for h713-tv") :
		 "a toplevel without a picture", s->nfmt, s->kodi_format ? "offered" : "missing");
	text_add(t, "client          %lu taken, %lu presented, %lu discarded, %lu busy, %lu released, %lu asked again; "
		 "%lu imports (%lu found again); rate %s, flip period %.2f ms\n", s->taken, s->presented,
		 s->discarded, s->busys, s->released, s->asked, s->imports_made, s->hits,
		 s->r->client_rate > 1 ? "half" : "full", s->period * 1e3);
}
