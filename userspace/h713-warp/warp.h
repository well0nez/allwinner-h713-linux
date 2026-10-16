/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-warp -- the keystone warp daemon. Design AP2d design-h713-warp.txt
 * (modules M1-M11), plan stage S5 (working journal `keystone/PLAN`).
 *
 * The one sentence that explains the split: h713-warp is a RENDERER, not a
 * display owner. h713-tv keeps card1, allocates the three NV12 targets,
 * exports them as dma-bufs and does every atomic commit; this program owns
 * /dev/dri/renderD128, the capture buffers, the shader and the matrix, and
 * asks h713-tv to show what it has drawn (peer protocol in peer.c).
 *
 * Everything below is shared between the modules; each module's own state
 * stays in its .c file.
 */
#ifndef H713_WARP_H
#define H713_WARP_H

#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include <stddef.h>

#include "geom.h"	/* the eight values, the matrix, warp.conf: ../libh713geom */

#define WARP_SOCKET	"/run/h713-warp/ctl"
#define TV_SOCKET	"/run/h713-tv/ctl"
#define RENDER_NODE	"/dev/dri/renderD128"
#define V4L2_NAME	"sun50i-h713-hdmirx"
#define WAYLAND_SOCKET	"/run/h713-warp/wayland"	/* the Wayland server: WAYLAND_DISPLAY */

#define WARP_TARGETS	3	/* triple buffering on the panel side (M9) */
#define WARP_SLOTS	3	/* capture ring slots (M5) */
#define WARP_LINE	512	/* one control line, as h713-tv's CTL_MAXLINE */
#define WARP_WHY	256	/* why something is off -- journal and status */

/* ---------------- the journal, h713-tv's house style (main.c) ---------- */
__attribute__((format(printf, 1, 2))) void info(const char *fmt, ...);
__attribute__((format(printf, 1, 2))) void warn(const char *fmt, ...);
__attribute__((format(printf, 1, 2))) _Noreturn void fail(const char *fmt, ...);
double now_s(void);

struct textbuf {
	char *b;
	size_t n, l;
};

__attribute__((format(printf, 2, 3)))
void text_add(struct textbuf *t, const char *fmt, ...);

/* what a claim is for: the capture ring, or a Wayland client of wayland.c */
enum warp_source { SRC_RING, SRC_CLIENT };
/* h713-tv's "source" as its last answer named it: to a claim, to a frame after a change, to "source" */
enum tv_source { TV_UNKNOWN, TV_HDMI, TV_CLIENT, TV_AUTO };

struct peer {
	const char *path;
	int fd;				/* -1: no connection */
	int tv_source;			/* enum tv_source */
	int target[WARP_TARGETS];	/* dma-buf fds of the panel buffers */
	unsigned int width, height, pitch;
	unsigned int coff;		/* NV12: the chroma plane's offset in each buffer */
	unsigned long commits, busy, errors;
};

void peer_init(struct peer *p, const char *path);
bool peer_claim(struct peer *p, int src, char *why, size_t n);
/* flip: the commit's flip fence when h713-tv sends one (a client claim), else -1; ours to close */
int peer_frame(struct peer *p, int index, int fence, int *flip, char *why, size_t n);
void peer_release(struct peer *p);
/* h713-tv's "source" alone, on a short connection of its own; false when h713-tv did not answer */
bool peer_source(struct peer *p);

struct source {
	const char *want;		/* -v PATH, or NULL: search by name */
	char path[32];
	int fd;				/* -1: not open */
	int type;			/* V4L2 buffer type */
	int planes;			/* dma-bufs per slot: 1 or 2 */
	unsigned int width, height;
	unsigned int pitch, cpitch;	/* Y and C bytes per line */
	unsigned int off_c;		/* offset of C when both are one buffer */
	int dmabuf[WARP_SLOTS][2];
	bool streaming;
	unsigned long timeouts, frames;
	double dq_s;			/* the last slot's timestamp: the vsync that handed it on */
	double slot_s[8];		/* the same, per slot */
	int held;			/* the slot kept back one vsync, -1 none (see loop.c) */
	unsigned long settled;		/* frames drawn from a slot one vsync old */
	unsigned long stale;		/* held slots given back undrawn: too old, their next write may have begun */
	unsigned int said_w, said_h, said_pitch;	/* the ring the journal was last told about */
};

void source_init(struct source *s, const char *want);
bool source_start(struct source *s, char *why, size_t n);
void source_stop(struct source *s);
int source_dequeue(struct source *s, char *why, size_t n);	/* slot, -1 */
bool source_queue(struct source *s, int slot);
bool source_geometry_changed(struct source *s);	/* drains the V4L2 events */

/* ---------------- EGL/GLES on the render node (gl.c) ------------------- */
enum warp_pattern { PATTERN_NONE, PATTERN_GRID, PATTERN_BORDER, PATTERN_MASK };

int gl_open(const char *node, char *why, size_t n);
void gl_close(void);
const char *gl_renderer(void);
bool gl_targets(const struct peer *p, char *why, size_t n);
bool gl_source(const struct source *s, char *why, size_t n);
void gl_source_drop(void);
/* labels: five strings drawn unwarped over the mask - the four corners and the
 * centre line - or NULL; only the mask shows them */
bool gl_draw(int target, int slot, const float m[16], int pattern, int mark_corner,
	     const char *const labels[5], const float lm[16], char *why, size_t n);
int gl_fence(void);			/* an out-fence fd, or -1 */
bool gl_is_open(void);
void gl_targets_drop(void);		/* the three panel buffers' images, before their claim is given back */

/* the Wayland client's pictures: RGB in, BT.709 limited range out, in the two passes */
struct gl_format {
	uint32_t fourcc;
	uint64_t modifier;
};
struct gl_image;			/* one imported client buffer, or the wl_shm upload texture */
int gl_formats(struct gl_format *out, int max, char *why, size_t n);	/* the RGB formats EGL imports */
struct gl_image *gl_image_dmabuf(int fd, uint32_t fourcc, uint64_t modifier, int w, int h,
				 uint32_t offset, uint32_t pitch, char *why, size_t n);
struct gl_image *gl_image_shm(void);
bool gl_image_upload(struct gl_image *im, const void *px, int w, int h, int stride, char *why, size_t n);
int gl_image_width(const struct gl_image *im);
int gl_image_height(const struct gl_image *im);
bool gl_image_stale(const struct gl_image *im);	/* made before the last gl_close(): gone with it */
void gl_image_free(struct gl_image *im);
bool gl_draw_client(int target, const struct gl_image *im, const float m[16], char *why, size_t n);
/*
 * What a frame costs, for "ctl trace": CPU microseconds of this thread in the
 * two passes (clock CLOCK_THREAD_CPUTIME_ID, so the clock governor does not
 * blur it -- but it does scale it). Taken only while gl_timing(true) is on.
 */
struct gl_cost {
	unsigned int cpu_luma_us, cpu_chroma_us;
};
void gl_timing(bool on);
const struct gl_cost *gl_last_cost(void);
void gl_edge(int px);			/* the soft border's width for the next draws, 0 = off */
/* the mask's texel count across the quad for a panel of w x h, the vendor's rounding */
void gl_edge_mask(unsigned int w, unsigned int h, int px, int out[2]);
/* the self-check: draw the slot again into a scratch buffer and compare it
 * with the panel buffer the first draw went to; rows = differing rows,
 * lo/hi their span */
/* the last drawn luma plane as a PGM file: eyes for a test without a wall */
bool gl_dump_luma(int target, const char *path, char *why, size_t n);
bool gl_check_compare(int target, int slot, const float m[16], unsigned long *rows,
		      int *lo, int *hi, char *why, size_t n);

/* the two shader pairs, so the host tests compile the very same strings */
extern const char *const gl_vertex_shader;
extern const char *const gl_fragment_shader;	/* NV16 -> RGB, BT.709 (kept for the tests) */
extern const char *const gl_luma_shader;	/* Y in, Y out */
extern const char *const gl_chroma_shader;	/* CbCr in, CbCr out */
extern const char *const gl_edge_shader;	/* the soft border's ring, blended */
void gl_edge_ring(const int e[2], float v[40]);	/* its ten vertices (x, y, u, v) */
extern const char *const gl_pattern_shader;
extern const char *const gl_rgb_luma_shader;	/* RGB in, Y out (the colour maths inside the keystone passes) */
extern const char *const gl_rgb_chroma_shader;	/* RGB in, CbCr out */

/* ---------------- what the daemon is doing (loop.c) -------------------- */
enum warp_state {
	WARP_OFF,	/* "warp = off": nothing is claimed, nothing is drawn */
	WARP_BYPASS,	/* on, but identity: no render node, h713-tv's ring */
	WARP_ON		/* the GPU path stands */
};

struct server;

struct runtime {
	struct warp_conf conf;
	struct peer peer;
	struct source source;
	struct server *srv;		/* the Wayland server, NULL when it could not start */
	enum warp_state state;
	int src;			/* enum warp_source: what the claim is for while WARP_ON */
	int client_rate;		/* 1: a client frame every vsync, 2: every second (--client-rate half) */
	bool on;			/* "ctl on"/"ctl off": run time only */
	int pattern;			/* enum warp_pattern */
	int mark_corner;		/* the mask's marked corner, 0..3 tl tr bl br, -1 none */
	int target;			/* the next panel buffer to draw, advanced on an accepted commit */
	bool hold;			/* draw a slot one vsync late (the source race, loop.c); off = the
					 * old timing, kept as the self-check's control */
	struct {			/* the self-check: a slot drawn twice, 12 ms apart, compared */
		int want;		/* frames still to check, 0 = off */
		int slot;		/* the slot kept back for the second draw, -1 none */
		int target;		/* the panel buffer the first draw went to */
		double due;		/* when the second draw is due */
		double age0;		/* the slot's age at the first draw */
		unsigned long frames, differing, rows_max, late;
		int trace;		/* dequeues still to log with their timestamps */
		bool trace_gpu;		/* "trace N gpu": wait the out-fence out and log the GPU's time */
		double last_pump;	/* when the last pump ended: the loop's gaps */
		int row_lo, row_hi;	/* the rows that differed, over all frames */
	} check;
	char why[WARP_WHY];		/* why it is not WARP_ON */
	const char *render_node;
	const char *wl_group;		/* -g: the Wayland socket's group, so that a client that is not root can connect */
	double m[16];			/* the matrix in use, column major */
	float mf[16];			/* ... as the uniform wants it */
	float lf[16];			/* the mode's flip alone: what the mask's labels go through */
	bool matrix_valid;
	/* the last hundred frames, M11 */
	unsigned long frames, dropped, refused;
	unsigned int fails;		/* consecutive render failures */
	unsigned int refused_w, refused_h, refused_pitch;	/* a ring geometry the GPU would not import (loop.c) */
	double fps, frame_ms, frame_ms_max;
	double t_mark;
	unsigned long f_mark;
	double t_start;
};

void warp_solve(struct runtime *r);	/* the eight values -> r->m/r->mf */
bool warp_engage(struct runtime *r);	/* bypass -> on; why on failure */
void warp_disengage(struct runtime *r, const char *why);
void warp_apply(struct runtime *r);	/* put the state where the values ask */
int warp_edge_for(struct runtime *r);	/* the soft edge, 0 at the identity */
bool warp_pump(struct runtime *r);	/* one capture frame; false: fell back */
void warp_check_tick(struct runtime *r);	/* the self-check's second draw, from the main loop */
void warp_status(struct runtime *r, char *buf, size_t n);

/* for the Wayland side (loop.c): the client is on the panel; one client frame -- 0 committed, 1 h713-tv was busy
 * (the target is drawn and kept), 2 not drawn, -1 the warp fell back; the same target again after a busy */
bool warp_client_live(const struct runtime *r);
int warp_client_frame(struct runtime *r, const struct gl_image *im, int *render, int *flip);
int warp_client_resend(struct runtime *r, int render, int *flip);
void warp_client_shown(struct runtime *r);	/* a toplevel has its first picture: claim the panel for it */
void warp_client_gone(struct runtime *r);	/* ... it is gone for good: give the panel back */
void warp_gl_idle(struct runtime *r);		/* close the render node if nothing needs it */

/* ---------------- the Wayland server (wayland.c) ------------ */
struct server *server_start(const char *path, struct runtime *r);
void server_stop(struct server *s);
int server_fd(const struct server *s);		/* the event loop's fd for poll(), -1 none */
void server_dispatch(struct server *s);
void server_flush(struct server *s);
bool server_shown(const struct server *s);	/* a toplevel with a picture: something to claim for */
bool server_busy(const struct server *s);	/* imports alive: the render node stays open */
void server_engaged(struct server *s, bool on);	/* the warp shows the client now / not any more */
void server_panel(struct server *s, unsigned int w, unsigned int h);
void server_redraw(struct server *s);		/* the keystone moved or a pattern went: draw again */
void server_status(const struct server *s, struct textbuf *t);

/* ---------------- the control socket and the client (ctl.c) ------------ */
struct control {
	const char *path;
	int lfd;			/* listening socket, -1 */
	int lock_fd;
	int cfd;			/* the client whose line is not complete yet, -1 */
	size_t off;			/* bytes of its line so far */
	struct timespec t0;		/* when it was accepted */
	char line[WARP_LINE];
};

void control_lock(struct control *c, const char *path);
void control_listen(struct control *c);
void control_close(struct control *c);
void control_serve(struct control *c, struct runtime *r);
int control_left(const struct control *c);	/* ms until the pending client's deadline, -1 none */
int client(int argc, char **argv, const char *path);

#endif /* H713_WARP_H */
