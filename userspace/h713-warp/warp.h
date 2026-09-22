/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-warp -- the keystone warp daemon. Design AP2d design-h713-warp.txt
 * (modules M1-M11), plan stage S5 (umbau/plan/keystone/PLAN.md).
 *
 * The one sentence that explains the split: h713-warp is a RENDERER, not a
 * display owner. h713-tv keeps card1, allocates the three XRGB8888 targets,
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
#include <stddef.h>

#define WARP_CONF	"/etc/h713/warp.conf"
#define WARP_SOCKET	"/run/h713-warp/ctl"
#define TV_SOCKET	"/run/h713-tv/ctl"
#define RENDER_NODE	"/dev/dri/renderD128"
#define V4L2_NAME	"sun50i-h713-hdmirx"

#define WARP_KEYS	8	/* four corners, x and y, per-mille inward */
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

/* ---------------- the eight values and the matrix (matrix.c) ----------- */
/* our key order: the PHYSICAL corner on the wall, tl tr bl br, x before y.
 * The vendor's parcel order is a different one and lives in matrix.c alone.
 */
enum warp_corner { CORNER_TL, CORNER_TR, CORNER_BL, CORNER_BR };

extern const char *const warp_corner_name[4];
extern const char *const warp_key_name[WARP_KEYS];	/* "tl_x" .. "br_y" */

int warp_key(const char *corner, const char *axis);	/* 0..7, -1 unknown */
int warp_key_by_name(const char *key);			/* "tl_x" -> 0..7 */
void warp_clamp(int v[WARP_KEYS]);			/* all four, as the app does */
int warp_clamp_key(int v[WARP_KEYS], int key, int want);	/* one, as a key press does */
bool warp_identity(const int v[WARP_KEYS]);		/* all eight zero */
bool warp_matrix(const int v[WARP_KEYS], double m[16]);	/* false: refused */
void warp_point(const double m[16], double x, double y, double out[2]);
void warp_corner_ndc(int corner, double out[2]);

struct warp_conf {
	const char *path;
	bool present;			/* the file was there */
	bool start_on;			/* "warp = on" */
	int v[WARP_KEYS];
	int zoom;			/* screen zoom in percent, 100 = none (S7) */
};

/* The eight the matrix sees: the keystone plus the screen zoom (the vendor's
 * "Digital scaling": every corner pulled in by (100 - zoom) * 5 per-mille,
 * AP2i rows 6-8), clamped the vendor's way. */
void warp_effective(const struct warp_conf *c, int out[WARP_KEYS]);

void conf_read(struct warp_conf *c);
bool conf_write(const struct warp_conf *c, char *why, size_t n);

struct peer {
	const char *path;
	int fd;				/* -1: no connection */
	int target[WARP_TARGETS];	/* dma-buf fds of the panel buffers */
	unsigned int width, height, pitch;
	unsigned long commits, busy, errors;
};

void peer_init(struct peer *p, const char *path);
bool peer_claim(struct peer *p, char *why, size_t n);
int peer_frame(struct peer *p, int index, int fence, char *why, size_t n);
void peer_release(struct peer *p);

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
bool gl_draw(int target, int slot, const float m[16], int pattern, int mark_corner,
	     char *why, size_t n);
int gl_fence(void);			/* an out-fence fd, or -1 */

/* the two shader pairs, so the host tests compile the very same strings */
extern const char *const gl_vertex_shader;
extern const char *const gl_fragment_shader;	/* NV16 -> RGB, BT.709 */
extern const char *const gl_pattern_shader;

/* ---------------- what the daemon is doing (loop.c) -------------------- */
enum warp_state {
	WARP_OFF,	/* "warp = off": nothing is claimed, nothing is drawn */
	WARP_BYPASS,	/* on, but identity: no render node, h713-tv's ring */
	WARP_ON		/* the GPU path stands */
};

struct runtime {
	struct warp_conf conf;
	struct peer peer;
	struct source source;
	enum warp_state state;
	bool on;			/* "ctl on"/"ctl off": run time only */
	int pattern;			/* enum warp_pattern */
	int mark_corner;		/* the mask's marked corner, 0..3 tl tr bl br, -1 none */
	char why[WARP_WHY];		/* why it is not WARP_ON */
	const char *render_node;
	double m[16];			/* the matrix in use, column major */
	float mf[16];			/* ... as the uniform wants it */
	bool matrix_valid;
	/* the last hundred frames, M11 */
	unsigned long frames, dropped, refused;
	unsigned int fails;		/* consecutive render failures */
	double fps, frame_ms, frame_ms_max;
	double t_mark;
	unsigned long f_mark;
	double t_start;
};

void warp_solve(struct runtime *r);	/* the eight values -> r->m/r->mf */
bool warp_engage(struct runtime *r);	/* bypass -> on; why on failure */
void warp_disengage(struct runtime *r, const char *why);
void warp_apply(struct runtime *r);	/* put the state where the values ask */
bool warp_pump(struct runtime *r);	/* one capture frame; false: fell back */
void warp_status(struct runtime *r, char *buf, size_t n);

/* ---------------- the control socket and the client (ctl.c) ------------ */
struct control {
	const char *path;
	int lfd;			/* listening socket, -1 */
	int lock_fd;
};

void control_lock(struct control *c, const char *path);
void control_listen(struct control *c);
void control_close(struct control *c);
void control_serve(struct control *c, struct runtime *r);
int client(int argc, char **argv, const char *path);

#endif /* H713_WARP_H */
