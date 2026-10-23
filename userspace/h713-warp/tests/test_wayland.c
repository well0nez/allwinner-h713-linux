/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE
/*
 * Host test of h713-warp's Wayland server: a client against server_stub (wayland.c with the
 * GPU and the warp's loop stubbed), in the build container, no device. What it checks is what cage and Kodi rely on:
 * the protocol set (no wl_seat, no subcompositor), CLOCK_MONOTONIC, a dma-buf
 * feedback with Kodi's AR30/AFBC and renderD128 as the device, the panel as the output's mode and the toplevel's
 * size, the life of a buffer (taken, frame done, released, presented), wl_shm, the refusals (too large, a buffer
 * before the configure, a second toplevel, a fifth connection) and the two seconds after the client is gone; a wl_shm
 * line shorter than 4 x width, a dma-buf shorter than its layout for every modifier, a waiting toplevel that takes the
 * panel over and a fifth connection that is closed; and the pause under an opaque page (the client runs on, nothing is
 * drawn, the newest picture is drawn when the page goes, the panel's buffer once more when there is none).
 *
 *   test_wayland ./server_stub     exit 0: all passed
 */
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <wayland-client.h>
#include <drm_fourcc.h>
#include "xdg-shell-client-protocol.h"
#include "linux-dmabuf-v1-client-protocol.h"
#include "presentation-time-client-protocol.h"

static int fails;
#define CHECK(c, ...) do { int ok_ = !!(c); fails += !ok_; printf("%s ", ok_ ? "ok  " : "FAIL"); \
			   printf(__VA_ARGS__); printf("\n"); } while (0)

struct conn {
	struct wl_display *d;
	struct wl_compositor *comp;
	struct wl_shm *shm;
	struct xdg_wm_base *wm;
	struct zwp_linux_dmabuf_v1 *dmabuf;
	struct wp_presentation *pres;
	struct wl_output *out;
	int forbidden, globals;
};

static struct {
	uint32_t clock, serial, tranche;
	int w, h, refresh, cfg_w, cfg_h, table_hits;
	bool fullscreen, configured, closed, table, device, fb_done, out_done, done, released, presented, failed, created;
	dev_t dev;
} ev;
static FILE *srv;

static void global(void *data, struct wl_registry *reg, uint32_t name, const char *iface, uint32_t version)
{
	struct conn *c = data;

	c->globals++;
	if (!strcmp(iface, "wl_compositor"))
		c->comp = wl_registry_bind(reg, name, &wl_compositor_interface, 4);
	else if (!strcmp(iface, "wl_shm"))
		c->shm = wl_registry_bind(reg, name, &wl_shm_interface, 1);
	else if (!strcmp(iface, "xdg_wm_base"))
		c->wm = wl_registry_bind(reg, name, &xdg_wm_base_interface, 1);
	else if (!strcmp(iface, "zwp_linux_dmabuf_v1") && version >= 4)
		c->dmabuf = wl_registry_bind(reg, name, &zwp_linux_dmabuf_v1_interface, 4);
	else if (!strcmp(iface, "wp_presentation"))
		c->pres = wl_registry_bind(reg, name, &wp_presentation_interface, 1);
	else if (!strcmp(iface, "wl_output"))
		c->out = wl_registry_bind(reg, name, &wl_output_interface, 4);
	else if (!strcmp(iface, "wl_seat") || !strcmp(iface, "wl_subcompositor") || !strcmp(iface, "wp_viewporter"))
		c->forbidden++;
}
static void global_remove(void *d, struct wl_registry *r, uint32_t n) { (void)d; (void)r; (void)n; }
static const struct wl_registry_listener reg_l = { global, global_remove };

static void clock_id(void *d, struct wp_presentation *p, uint32_t clk) { (void)d; (void)p; ev.clock = clk; }
static const struct wp_presentation_listener pres_l = { clock_id };

static void fb_done(void *d, struct zwp_linux_dmabuf_feedback_v1 *f) { (void)d; (void)f; ev.fb_done = true; }
static void fb_table(void *d, struct zwp_linux_dmabuf_feedback_v1 *f, int32_t fd, uint32_t size)
{
	const struct { uint32_t format, pad; uint64_t modifier; } *e = mmap(NULL, size, PROT_READ, MAP_PRIVATE, fd, 0);
	uint32_t i;

	(void)d;
	(void)f;
	ev.table = e != MAP_FAILED && size % 16 == 0;
	for (i = 0; ev.table && i < size / 16; i++)
		ev.table_hits += e[i].format == DRM_FORMAT_ARGB2101010 && e[i].modifier == 0x0800000000000062ull;
	if (e != MAP_FAILED)
		munmap((void *)e, size);
	close(fd);
}
static void fb_device(void *d, struct zwp_linux_dmabuf_feedback_v1 *f, struct wl_array *a)
{
	(void)d;
	(void)f;
	ev.device = a->size == sizeof(dev_t) && !memcmp(a->data, &ev.dev, sizeof(dev_t));
}
static void fb_tdone(void *d, struct zwp_linux_dmabuf_feedback_v1 *f) { (void)d; (void)f; }
static void fb_formats(void *d, struct zwp_linux_dmabuf_feedback_v1 *f, struct wl_array *a)
{
	(void)d;
	(void)f;
	ev.tranche = (uint32_t)(a->size / 2);
}
static void fb_flags(void *d, struct zwp_linux_dmabuf_feedback_v1 *f, uint32_t fl) { (void)d; (void)f; (void)fl; }
static const struct zwp_linux_dmabuf_feedback_v1_listener fb_l = {
	fb_done, fb_table, fb_device, fb_tdone, fb_device, fb_formats, fb_flags,
};

static void o_geometry(void *d, struct wl_output *o, int32_t x, int32_t y, int32_t pw, int32_t ph, int32_t sp,
		       const char *make, const char *model, int32_t t)
{ (void)d; (void)o; (void)x; (void)y; (void)pw; (void)ph; (void)sp; (void)make; (void)model; (void)t; }
static void o_mode(void *d, struct wl_output *o, uint32_t fl, int32_t w, int32_t h, int32_t r)
{
	(void)d;
	(void)o;
	(void)fl;
	ev.w = w;
	ev.h = h;
	ev.refresh = r;
}
static void o_done(void *d, struct wl_output *o) { (void)d; (void)o; ev.out_done = true; }
static void o_scale(void *d, struct wl_output *o, int32_t s) { (void)d; (void)o; (void)s; }
static void o_text(void *d, struct wl_output *o, const char *t) { (void)d; (void)o; (void)t; }
static const struct wl_output_listener out_l = { o_geometry, o_mode, o_done, o_scale, o_text, o_text };

static void ping(void *d, struct xdg_wm_base *wm, uint32_t serial) { (void)d; xdg_wm_base_pong(wm, serial); }
static const struct xdg_wm_base_listener wm_l = { ping };
static void xs_configure(void *d, struct xdg_surface *x, uint32_t serial)
{
	(void)d;
	ev.serial = serial;
	ev.configured = true;
	xdg_surface_ack_configure(x, serial);
}
static const struct xdg_surface_listener xs_l = { xs_configure };
static void tl_configure(void *d, struct xdg_toplevel *t, int32_t w, int32_t h, struct wl_array *st)
{
	uint32_t *s;

	(void)d;
	(void)t;
	ev.cfg_w = w;
	ev.cfg_h = h;
	wl_array_for_each(s, st)
		ev.fullscreen |= *s == XDG_TOPLEVEL_STATE_FULLSCREEN;
}
static void tl_close(void *d, struct xdg_toplevel *t) { (void)d; (void)t; ev.closed = true; }
static const struct xdg_toplevel_listener tl_l = { tl_configure, tl_close, NULL, NULL };

/* A4: the client whose toplevel waits behind the shown one */
static struct {
	int w, h;
	bool fullscreen, closed, done;
} fev;
static void f_xs_configure(void *d, struct xdg_surface *x, uint32_t serial) { (void)d; xdg_surface_ack_configure(x, serial); }
static const struct xdg_surface_listener f_xs_l = { f_xs_configure };
static void f_tl_configure(void *d, struct xdg_toplevel *t, int32_t w, int32_t h, struct wl_array *st)
{
	uint32_t *p;

	(void)d;
	(void)t;
	fev.w = w;
	fev.h = h;
	fev.fullscreen = false;
	wl_array_for_each(p, st)
		fev.fullscreen |= *p == XDG_TOPLEVEL_STATE_FULLSCREEN;
}
static void f_tl_close(void *d, struct xdg_toplevel *t) { (void)d; (void)t; fev.closed = true; }
static const struct xdg_toplevel_listener f_tl_l = { f_tl_configure, f_tl_close, NULL, NULL };
static void f_done(void *d, struct wl_callback *cb, uint32_t t) { (void)d; (void)t; wl_callback_destroy(cb); fev.done = true; }
static const struct wl_callback_listener f_cb_l = { f_done };

static void released(void *d, struct wl_buffer *b) { (void)d; (void)b; ev.released = true; }
static const struct wl_buffer_listener buf_l = { released };
static void cb_done(void *d, struct wl_callback *cb, uint32_t t) { (void)d; (void)t; wl_callback_destroy(cb); ev.done = true; }
static const struct wl_callback_listener cb_l = { cb_done };
static void pf_sync(void *d, struct wp_presentation_feedback *f, struct wl_output *o) { (void)d; (void)f; (void)o; }
static void pf_presented(void *d, struct wp_presentation_feedback *f, uint32_t hi, uint32_t lo, uint32_t ns,
			 uint32_t refresh, uint32_t sh, uint32_t sl, uint32_t flags)
{
	(void)d; (void)hi; (void)lo; (void)ns; (void)sh; (void)sl;
	ev.presented = refresh > 10000000 && (flags & WP_PRESENTATION_FEEDBACK_KIND_VSYNC);
	wp_presentation_feedback_destroy(f);
}
static void pf_discarded(void *d, struct wp_presentation_feedback *f) { (void)d; wp_presentation_feedback_destroy(f); }
static const struct wp_presentation_feedback_listener pf_l = { pf_sync, pf_presented, pf_discarded };
static void p_created(void *d, struct zwp_linux_buffer_params_v1 *p, struct wl_buffer *b)
{
	(void)p;
	ev.created = true;
	if (d)				/* dmabuf_sized: the buffer itself is not wanted */
		wl_buffer_destroy(b);
}
static void p_failed(void *d, struct zwp_linux_buffer_params_v1 *p) { (void)d; (void)p; ev.failed = true; }
static const struct zwp_linux_buffer_params_v1_listener params_l = { p_created, p_failed };

/* the pause test's own flags: one per buffer, callback and feedback */
static void rel_flag(void *d, struct wl_buffer *b) { (void)b; *(bool *)d = true; }
static const struct wl_buffer_listener rel_l = { rel_flag };
static void done_flag(void *d, struct wl_callback *cb, uint32_t t) { (void)t; wl_callback_destroy(cb); *(bool *)d = true; }
static const struct wl_callback_listener done_l = { done_flag };
struct fbk {
	bool presented, discarded;
};
static void k_sync(void *d, struct wp_presentation_feedback *f, struct wl_output *o) { (void)d; (void)f; (void)o; }
static void k_presented(void *d, struct wp_presentation_feedback *f, uint32_t hi, uint32_t lo, uint32_t ns,
			uint32_t refresh, uint32_t sh, uint32_t sl, uint32_t flags)
{
	(void)hi; (void)lo; (void)ns; (void)refresh; (void)sh; (void)sl; (void)flags;
	((struct fbk *)d)->presented = true;
	wp_presentation_feedback_destroy(f);
}
static void k_discarded(void *d, struct wp_presentation_feedback *f)
{
	((struct fbk *)d)->discarded = true;
	wp_presentation_feedback_destroy(f);
}
static const struct wp_presentation_feedback_listener k_l = { k_sync, k_presented, k_discarded };

/* round trips until the flag is up or the time is out */
static bool wait_for(struct conn *c, bool *flag, int ms)
{
	while (!*flag && ms > 0 && wl_display_roundtrip(c->d) >= 0) {
		usleep(10000);
		ms -= 10;
	}
	return *flag;
}

/* the stub's next line that is `word` (it reports what the loop would hear) */
static bool server_says(const char *word, int ms)
{
	char line[64];
	struct pollfd pf = { .fd = fileno(srv), .events = POLLIN };

	while (ms > 0 && poll(&pf, 1, ms) > 0 && fgets(line, sizeof(line), srv)) {
		line[strcspn(line, "\n")] = '\0';
		if (!strcmp(line, word))
			return true;
		ms -= 10;
	}
	return false;
}

static bool connect_to(struct conn *c, const char *path)
{
	memset(c, 0, sizeof(*c));
	c->d = wl_display_connect(path);
	if (!c->d)
		return false;
	wl_registry_add_listener(wl_display_get_registry(c->d), &reg_l, c);
	wl_display_roundtrip(c->d);
	return true;
}

static int memfd(size_t size)
{
	int fd = memfd_create("test-buffer", MFD_CLOEXEC);

	if (fd >= 0 && ftruncate(fd, (off_t)size))
		fd = -1;
	return fd;
}

static struct wl_buffer *dmabuf(struct conn *c, int w, int h, bool immed)
{
	struct zwp_linux_buffer_params_v1 *p = zwp_linux_dmabuf_v1_create_params(c->dmabuf);
	uint32_t pitch = ((uint32_t)w * 4 + 63) & ~63u;
	int fd = memfd((size_t)pitch * (size_t)h);
	struct wl_buffer *b = NULL;

	zwp_linux_buffer_params_v1_add(p, fd, 0, 0, pitch, 0, 0);	/* LINEAR */
	close(fd);
	if (immed) {
		b = zwp_linux_buffer_params_v1_create_immed(p, w, h, DRM_FORMAT_XRGB8888, 0);
	} else {
		zwp_linux_buffer_params_v1_add_listener(p, &params_l, NULL);
		zwp_linux_buffer_params_v1_create(p, w, h, DRM_FORMAT_XRGB8888, 0);
	}
	return b;
}

/* a wl_shm buffer of w x h with this stride in a pool exactly stride * h bytes long */
static struct wl_buffer *shmbuf_stride(struct conn *c, int w, int h, int stride)
{
	int fd = memfd((size_t)stride * (size_t)h);
	struct wl_shm_pool *pool = wl_shm_create_pool(c->shm, fd, stride * h);
	struct wl_buffer *b = wl_shm_pool_create_buffer(pool, 0, w, h, stride, WL_SHM_FORMAT_XRGB8888);

	wl_shm_pool_destroy(pool);
	close(fd);
	return b;
}

/*
 * A3: `size` bytes (a memfd - the server reads only the length; the import is the stub's) described as w x h with this
 * format, modifier and pitch: 1 created, 0 failed, -1 no answer
 */
static int dmabuf_sized(struct conn *c, int w, int h, uint32_t fourcc, uint64_t mod, uint32_t pitch, size_t size)
{
	struct zwp_linux_buffer_params_v1 *p = zwp_linux_dmabuf_v1_create_params(c->dmabuf);
	int fd = memfd(size), ms = 1000;

	ev.created = ev.failed = false;
	zwp_linux_buffer_params_v1_add(p, fd, 0, 0, pitch, (uint32_t)(mod >> 32), (uint32_t)mod);
	close(fd);
	zwp_linux_buffer_params_v1_add_listener(p, &params_l, c);
	zwp_linux_buffer_params_v1_create(p, w, h, fourcc, 0);
	while (!ev.created && !ev.failed && ms > 0 && wl_display_roundtrip(c->d) >= 0)
		ms -= 10;
	zwp_linux_buffer_params_v1_destroy(p);
	return ev.created ? 1 : ev.failed ? 0 : -1;
}

static struct wl_buffer *shmbuf(struct conn *c, int w, int h)
{
	return shmbuf_stride(c, w, h, w * 4);
}

/* a client of its own with a configured toplevel: commits b, says whether the server ended the connection with
 * an error on the wl_buffer of this code */
static bool buffer_error(const char *path, int w, int h, int stride, uint32_t code)
{
	const struct wl_interface *iface = NULL;
	struct conn x;
	struct wl_surface *xs;
	struct xdg_surface *xx;
	uint32_t id, got;
	bool ok;

	if (!connect_to(&x, path) || !x.comp)
		return false;
	xdg_wm_base_add_listener(x.wm, &wm_l, NULL);
	xs = wl_compositor_create_surface(x.comp);
	xx = xdg_wm_base_get_xdg_surface(x.wm, xs);
	xdg_surface_add_listener(xx, &xs_l, NULL);
	xdg_toplevel_add_listener(xdg_surface_get_toplevel(xx), &tl_l, NULL);
	wl_surface_commit(xs);
	ev.configured = false;
	wait_for(&x, &ev.configured, 1000);
	wl_surface_attach(xs, shmbuf_stride(&x, w, h, stride), 0, 0);
	wl_surface_commit(xs);
	wl_display_roundtrip(x.d);
	got = wl_display_get_protocol_error(x.d, &iface, &id);
	ok = wl_display_get_error(x.d) == EPROTO && iface == &wl_buffer_interface && got == code;
	wl_display_disconnect(x.d);
	usleep(100000);
	return ok;
}

/* h713-warp -g GROUP: the named group owns the socket at 0660, so that a client that is not root (Kodi's cage) can connect;
 * a group that does not exist leaves the socket as it was and the server runs. Needs a second group of the user to
 * be able to tell the two apart. */
static void group_test(const char *stub, const char *dir)
{
	gid_t gl[64], other = (gid_t)-1;
	int n = getgroups(64, gl), i, k, in[2], out[2];
	struct group *g;
	struct stat st;
	char path[64];
	pid_t pid;

	for (i = 0; i < n; i++)
		if (gl[i] != getegid())
			other = gl[i];
	g = other != (gid_t)-1 ? getgrgid(other) : NULL;
	if (!g) {
		printf("     (-g: this user has no second group, the socket's group is not checked)\n");
		return;
	}
	for (k = 0; k < 2; k++) {
		const char *name = k ? "h713-no-such-group" : g->gr_name;

		snprintf(path, sizeof(path), "%s/group%d", dir, k);
		if (pipe2(in, O_CLOEXEC) || pipe2(out, O_CLOEXEC))
			exit(2);
		pid = fork();
		if (!pid) {
			dup2(in[0], 0);
			dup2(out[1], 1);
			execl(stub, stub, path, name, (char *)NULL);
			_exit(127);
		}
		close(in[0]);
		close(out[1]);
		srv = fdopen(out[0], "r");
		setvbuf(srv, NULL, _IONBF, 0);
		if (!server_says("up", 3000) || stat(path, &st)) {
			CHECK(0, "-g %s: the server is up with its socket", name);
		} else if (!k) {
			CHECK(st.st_gid == other && (st.st_mode & 0777) == 0660, "-g %s: the socket belongs to that group, 0660", name);
		} else {
			CHECK(st.st_gid == getegid() && (st.st_mode & 0777) == 0660,
			      "-g with a group that does not exist: the server runs, the socket stays as it was");
		}
		fclose(srv);
		close(in[1]);
		waitpid(pid, &i, 0);
		unlink(path);
	}
}

int main(int argc, char **argv)
{
	char dir[] = "/tmp/h713-warp-test-XXXXXX", path[64];
	int in[2], out[2], i, seen = 0;
	struct conn c, e, more[4];
	struct stat st;
	pid_t pid;

	if (argc != 2 || !mkdtemp(dir) || pipe2(in, O_CLOEXEC) || pipe2(out, O_CLOEXEC) || stat("/dev/null", &st))
		return 2;
	ev.dev = st.st_rdev;
	group_test(argv[1], dir);
	snprintf(path, sizeof(path), "%s/wayland", dir);
	pid = fork();
	if (!pid) {
		dup2(in[0], 0);
		dup2(out[1], 1);
		execl(argv[1], argv[1], path, (char *)NULL);
		_exit(127);
	}
	close(in[0]);
	close(out[1]);
	srv = fdopen(out[0], "r");
	setvbuf(srv, NULL, _IONBF, 0);	/* poll() sees the pipe, not stdio's buffer */
	CHECK(server_says("up", 3000), "the server is up on %s", path);
	CHECK(connect_to(&c, path), "a client connects (absolute WAYLAND_DISPLAY)");
	CHECK(c.comp && c.shm && c.wm && c.dmabuf && c.pres && c.out, "globals: compositor, shm, xdg_wm_base, linux-dmabuf v4, presentation, output");
	CHECK(!c.forbidden, "no wl_seat, wl_subcompositor, wp_viewporter");

	wp_presentation_add_listener(c.pres, &pres_l, NULL);
	zwp_linux_dmabuf_feedback_v1_add_listener(zwp_linux_dmabuf_v1_get_default_feedback(c.dmabuf), &fb_l, NULL);
	wl_output_add_listener(c.out, &out_l, NULL);
	xdg_wm_base_add_listener(c.wm, &wm_l, NULL);
	wl_display_roundtrip(c.d);
	CHECK(ev.clock == CLOCK_MONOTONIC, "presentation clock %u = CLOCK_MONOTONIC", ev.clock);
	CHECK(ev.fb_done && ev.table && ev.table_hits == 1 && ev.tranche == 6, "feedback: table with AR30 + AFBC, one tranche of %u", ev.tranche);
	CHECK(ev.device, "feedback: main and target device = the render node's dev_t");
	CHECK(ev.out_done && ev.w > 0 && ev.h > 0 && ev.refresh > 59000 && ev.refresh < 60000, "output %dx%d @ %d mHz", ev.w, ev.h, ev.refresh);

	struct wl_surface *s = wl_compositor_create_surface(c.comp);
	struct xdg_surface *xs = xdg_wm_base_get_xdg_surface(c.wm, s);
	struct xdg_toplevel *tl = xdg_surface_get_toplevel(xs);

	xdg_surface_add_listener(xs, &xs_l, NULL);
	xdg_toplevel_add_listener(tl, &tl_l, NULL);
	wl_surface_commit(s);
	CHECK(wait_for(&c, &ev.configured, 1000) && ev.cfg_w == ev.w && ev.cfg_h == ev.h && ev.fullscreen,
	      "toplevel configured fullscreen %dx%d", ev.cfg_w, ev.cfg_h);

	struct wl_buffer *b = dmabuf(&c, ev.cfg_w, ev.cfg_h, true);

	wl_buffer_add_listener(b, &buf_l, NULL);
	wl_surface_attach(s, b, 0, 0);
	wl_callback_add_listener(wl_surface_frame(s), &cb_l, NULL);
	wp_presentation_feedback_add_listener(wp_presentation_feedback(c.pres, s), &pf_l, NULL);
	wl_surface_commit(s);
	wl_display_flush(c.d);
	CHECK(server_says("shown", 2000), "the first picture claims the panel");
	CHECK(server_says("frame", 2000), "the buffer is taken (ready: the dma-buf is readable)");
	CHECK(wait_for(&c, &ev.done, 2000), "frame callback done");
	CHECK(wait_for(&c, &ev.released, 2000), "buffer released at the render fence");
	CHECK(wait_for(&c, &ev.presented, 2000), "presented, vsync, refresh from the flip");

	ev.released = false;
	ev.configured = false;
	struct wl_buffer *sb = shmbuf(&c, 64, 64);

	wl_buffer_add_listener(sb, &buf_l, NULL);
	wl_surface_attach(s, sb, 0, 0);
	wl_surface_commit(s);
	wl_display_flush(c.d);
	CHECK(server_says("frame", 2000) && wait_for(&c, &ev.released, 2000), "wl_shm 64x64 taken (letterbox) and released");
	CHECK(wait_for(&c, &ev.configured, 1000), "a picture smaller than the panel gets the configure once more (cage)");

	/* a padded line is fine, a line shorter than 4 x width is a protocol error before anything reads it */
	ev.released = false;
	sb = shmbuf_stride(&c, 100, 50, 100 * 4 + 64);
	wl_buffer_add_listener(sb, &buf_l, NULL);
	wl_surface_attach(s, sb, 0, 0);
	wl_surface_commit(s);
	wl_display_flush(c.d);
	CHECK(server_says("frame", 2000) && wait_for(&c, &ev.released, 2000), "wl_shm 100x50, stride 464 (padded): taken and released");
	CHECK(buffer_error(path, 1920, 1080, 1920, WL_SHM_ERROR_INVALID_STRIDE),
	      "wl_shm 1920x1080, stride 1920 (= width, libwayland lets it pass): error invalid_stride on the buffer");
	CHECK(buffer_error(path, 64, 64, 64 * 4 - 4, WL_SHM_ERROR_INVALID_STRIDE),
	      "wl_shm 64x64, stride 252 (one pixel short): error invalid_stride");
	CHECK(!server_says("short-stride", 300), "no short line reached the upload");
	wl_display_roundtrip(c.d);

	dmabuf(&c, ev.cfg_w + 1, ev.cfg_h, false);
	CHECK(wait_for(&c, &ev.failed, 1000), "a dma-buf larger than the panel fails");

	/*
	 * The dma-buf at least as long as the GPU reads, for every modifier. The byte counts are mesa 25.0.7's
	 * panfrost layout, worked out by hand (pan_layout.c): AFBC 32x8 1920x1080 = 60 x 136 superblocks (1088 lines,
	 * render blocks of 16) x 16 B header = 130 560 (a multiple of 128) + body 1920 x 1088 x 4 = 8 355 840.
	 */
	{
		static const struct {
			const char *what;
			int w, h;
			uint32_t fourcc;
			uint64_t mod;
			uint32_t pitch;
			size_t need;
		} k[] = {
			{ "AFBC 32x8 sparse (Kodi's) 1920x1080", 1920, 1080, DRM_FORMAT_ARGB2101010, 0x0800000000000062ull, 7680, 8486400 },
			{ "AFBC 32x8 sparse 1000x300 (1216 x 16 B header + 1024x304x4)", 1000, 300, DRM_FORMAT_ARGB2101010, 0x0800000000000062ull, 4000, 19456 + 1245184 },
			{ "AFBC 16x16 tiled 1920x1080 (header 8640 x 16 to 4096, 1920x1152x4)", 1920, 1080, DRM_FORMAT_ARGB2101010, 0x0800000000000341ull, 7680, 139264 + 8847360 },
			{ "AFBC 16x16 tiled 1000x300 (1024x384)", 1000, 300, DRM_FORMAT_ARGB2101010, 0x0800000000000341ull, 4000, 24576 + 1572864 },
			{ "u-interleaved 1920x1080 (pitch x 1088 lines)", 1920, 1080, DRM_FORMAT_ARGB2101010, 0x0810000000000001ull, 7680, 7680u * 1088 },
			{ "LINEAR 1920x1080 pitch 7680", 1920, 1080, DRM_FORMAT_XRGB8888, DRM_FORMAT_MOD_LINEAR, 7680, 7680u * 1080 },
			{ "a modifier without a layout here (X-tiled): w x h x 4", 1920, 1080, DRM_FORMAT_XRGB8888, 0x0100000000000001ull, 7680, 1920u * 1080 * 4 },
		};
		unsigned int j;

		for (j = 0; j < sizeof(k) / sizeof(k[0]); j++) {
			int at = dmabuf_sized(&c, k[j].w, k[j].h, k[j].fourcc, k[j].mod, k[j].pitch, k[j].need);
			int under = dmabuf_sized(&c, k[j].w, k[j].h, k[j].fourcc, k[j].mod, k[j].pitch, k[j].need - 1);

			CHECK(at == 1 && under == 0, "%s: %zu bytes created, one less failed", k[j].what, k[j].need);
		}
		CHECK(dmabuf_sized(&c, 1920, 1080, DRM_FORMAT_ARGB2101010, 0x0800000000000062ull, 7680, 20480) == 0,
		      "20 KB described as 1920x1080 AFBC (the GPU fault of 15.10.2026) failed");
		CHECK(wl_display_get_error(c.d) == 0, "the client lives on after the refusals");
	}

	struct wl_surface *s2 = wl_compositor_create_surface(c.comp);
	struct xdg_toplevel *tl2 = xdg_surface_get_toplevel(xdg_wm_base_get_xdg_surface(c.wm, s2));

	xdg_toplevel_add_listener(tl2, &tl_l, NULL);
	ev.closed = false;
	wl_surface_commit(s2);
	CHECK(wait_for(&c, &ev.closed, 1000), "a second toplevel is closed at once");

	CHECK(connect_to(&e, path), "a second client");
	struct wl_surface *es = wl_compositor_create_surface(e.comp);
	xdg_surface_get_toplevel(xdg_wm_base_get_xdg_surface(e.wm, es));
	wl_surface_attach(es, shmbuf(&e, 16, 16), 0, 0);
	wl_surface_commit(es);
	wl_display_roundtrip(e.d);
	CHECK(wl_display_get_error(e.d) == EPROTO, "a buffer before the configure is a protocol error");
	wl_display_disconnect(e.d);
	usleep(100000);
	wl_display_roundtrip(c.d);

	for (i = 0; i < 4; i++)
		if (connect_to(&more[i], path) && more[i].comp)
			seen++;
	{
		struct pollfd hp = { .fd = more[3].d ? wl_display_get_fd(more[3].d) : -1, .events = POLLIN };
		char byte;

		CHECK(seen == 3 && more[3].d && wl_display_get_error(more[3].d) == EPROTO,
		      "connections 2-4 see the globals, the fifth gets an error (%d of 4 saw them)", seen);
		/* closed with the client's last request unread: a hangup, and recv says EOF or ECONNRESET */
		int pr = hp.fd >= 0 ? poll(&hp, 1, 1000) : -1;
		ssize_t rr = pr > 0 ? recv(hp.fd, &byte, 1, MSG_DONTWAIT) : -2;

		CHECK((hp.revents & POLLHUP) && (rr == 0 || (rr < 0 && errno == ECONNRESET)),
		      "... and the server closed it, not held it (revents 0x%x)", hp.revents);
	}
	for (i = 0; i < 4; i++)
		if (more[i].d)
			wl_display_disconnect(more[i].d);

	/* a toplevel that waited (told "close", no frame callbacks) takes the panel over when the shown one goes */
	{
		struct conn f;
		struct wl_surface *fs;
		struct xdg_surface *fx;
		struct xdg_toplevel *ftl;
		struct wl_buffer *fb;
		int ms;

		xdg_toplevel_destroy(tl2);	/* c's second toplevel, never acknowledged: out of the way */
		wl_display_roundtrip(c.d);
		CHECK(connect_to(&f, path) && f.comp, "a client whose toplevel will wait");
		xdg_wm_base_add_listener(f.wm, &wm_l, NULL);
		fs = wl_compositor_create_surface(f.comp);
		fx = xdg_wm_base_get_xdg_surface(f.wm, fs);
		xdg_surface_add_listener(fx, &f_xs_l, NULL);
		ftl = xdg_surface_get_toplevel(fx);
		xdg_toplevel_add_listener(ftl, &f_tl_l, NULL);
		wl_surface_commit(fs);
		wl_display_roundtrip(f.d);
		wl_display_roundtrip(f.d);
		CHECK(fev.closed && fev.w == 0, "it waits: told close, configured 0x0");
		wl_surface_attach(fs, shmbuf(&f, 64, 64), 0, 0);	/* a client that draws on the callback: one picture, then waits */
		wl_callback_add_listener(wl_surface_frame(fs), &f_cb_l, NULL);
		wl_surface_commit(fs);
		for (ms = 300; ms > 0 && wl_display_roundtrip(f.d) >= 0; ms -= 10)
			usleep(10000);
		CHECK(!fev.done, "while it waits, its frame callback does not come");
		xdg_toplevel_destroy(tl);
		wl_display_roundtrip(c.d);
		for (ms = 1000; (fev.w != ev.w || !fev.done) && ms > 0 && wl_display_roundtrip(f.d) >= 0; ms -= 10)
			usleep(10000);
		CHECK(fev.w == ev.w && fev.h == ev.h && fev.fullscreen,
		      "the shown toplevel went: the waiting one gets the panel's configure %dx%d fullscreen", fev.w, fev.h);
		CHECK(fev.done, "... and the frame callback it waited for");
		fev.done = false;
		fb = dmabuf(&f, fev.w, fev.h, true);
		wl_surface_attach(fs, fb, 0, 0);
		wl_callback_add_listener(wl_surface_frame(fs), &f_cb_l, NULL);
		wl_surface_commit(fs);
		wl_display_flush(f.d);
		CHECK(server_says("frame", 1500), "its first picture is taken - within the two seconds, no new claim");
		for (ms = 1000; !fev.done && ms > 0 && wl_display_roundtrip(f.d) >= 0; ms -= 10)
			usleep(10000);
		CHECK(fev.done, "... and its frame callback comes");
		xdg_toplevel_destroy(ftl);
		wl_display_roundtrip(f.d);
		CHECK(!server_says("gone", 1500), "the panel is held after the toplevel went (cage restart)");
		CHECK(server_says("gone", 1500), "... and given back after two seconds");
		wl_display_disconnect(f.d);
	}

	/*
	 * An opaque page over the client (h713-tv's "note cover on", the stub's stdin): its pictures are taken - the frame
	 * callback comes, the feedback is discarded - and not drawn; the newest is held, the one before goes back; when the
	 * page goes the held one is drawn at once, and with none held the panel's buffer is committed once more.
	 */
	{
		struct conn g;
		struct wl_surface *gs;
		struct xdg_surface *gx;
		struct xdg_toplevel *gt;
		struct wl_buffer *gb[3];
		bool rel[3] = { false, false, false }, done[3] = { false, false, false };
		struct fbk fk[2] = { { false, false }, { false, false } };
		char line[64] = "";
		int k;

		CHECK(connect_to(&g, path) && g.comp && g.pres, "a client for the pause under a page");
		xdg_wm_base_add_listener(g.wm, &wm_l, NULL);
		gs = wl_compositor_create_surface(g.comp);
		gx = xdg_wm_base_get_xdg_surface(g.wm, gs);
		ev.configured = false;
		xdg_surface_add_listener(gx, &xs_l, NULL);
		gt = xdg_surface_get_toplevel(gx);
		xdg_toplevel_add_listener(gt, &tl_l, NULL);
		wl_surface_commit(gs);
		wait_for(&g, &ev.configured, 1000);
		for (k = 0; k < 3; k++) {
			gb[k] = dmabuf(&g, ev.cfg_w, ev.cfg_h, true);
			wl_buffer_add_listener(gb[k], &rel_l, &rel[k]);
		}
		wl_surface_attach(gs, gb[0], 0, 0);
		wl_callback_add_listener(wl_surface_frame(gs), &done_l, &done[0]);
		wl_surface_commit(gs);
		wl_display_flush(g.d);
		CHECK(server_says("shown", 2000) && server_says("frame", 2000) && wait_for(&g, &done[0], 1000),
		      "its first picture is drawn");
		CHECK(write(in[1], "cover on\n", 9) == 9 && server_says("covered", 1000), "a page covers the panel");
		wl_surface_attach(gs, gb[1], 0, 0);
		wl_callback_add_listener(wl_surface_frame(gs), &done_l, &done[1]);
		wp_presentation_feedback_add_listener(wp_presentation_feedback(g.pres, gs), &k_l, &fk[0]);
		wl_surface_commit(gs);
		wl_display_flush(g.d);
		CHECK(wait_for(&g, &done[1], 1000), "under the page its frame callback still comes: the client runs on");
		CHECK(!server_says("frame", 300), "... and nothing is drawn");
		CHECK(wait_for(&g, &fk[0].discarded, 1000) && !fk[0].presented, "... its feedback is discarded, not presented");
		CHECK(!rel[1], "... and the picture is held, not released");
		wl_surface_attach(gs, gb[2], 0, 0);
		wl_callback_add_listener(wl_surface_frame(gs), &done_l, &done[2]);
		wl_surface_commit(gs);
		wl_display_flush(g.d);
		CHECK(wait_for(&g, &done[2], 1000) && wait_for(&g, &rel[1], 1000) && !rel[2],
		      "a newer picture is held, the one before goes back");
		CHECK(write(in[1], "pictures\n", 9) == 9 && fgets(line, sizeof(line), srv) && !strcmp(line, "pictures 3\n"),
		      "three pictures of the toplevel counted, the two under the page too (%.*s)", (int)strcspn(line, "\n"), line);
		CHECK(write(in[1], "cover off\n", 10) == 10 && server_says("frame", 1000),
		      "the page goes: the held picture is drawn at once");
		CHECK(server_says("uncovered", 1000), "... before the stub has said that the page went");
		wl_display_roundtrip(g.d);
		CHECK(write(in[1], "cover on\n", 9) == 9 && server_says("covered", 1000) &&
		      write(in[1], "cover off\n", 10) == 10 && server_says("repeat", 1000),
		      "a page without a new picture under it: its end rides on the panel's buffer once more");
		wl_display_disconnect(g.d);
		CHECK(server_says("gone", 3000), "the client went: given back after two seconds");
	}

	wl_display_disconnect(c.d);
	close(in[1]);
	waitpid(pid, &i, 0);
	CHECK(WIFEXITED(i) && !WEXITSTATUS(i), "the server stops cleanly");
	unlink(path);
	rmdir(dir);
	printf("%s: %d failed\n", fails ? "FAILED" : "PASSED", fails);
	return fails ? 1 : 0;
}
