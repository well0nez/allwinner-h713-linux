/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* accept4, strtok_r, O_CLOEXEC */
/*
 * The state machine, the render-and-flip loop and the status block (design
 * AP2d M9, M10, M11).
 *
 * Three states and one rule. The rule is M10's: every failure leaves a
 * picture on the wall. "off" is "ctl off": nothing claimed, nothing drawn.
 * "bypass" is on with nothing to warp -- all eight values 0 (the identity a
 * fresh image comes up in), or no signal, or no GPU: the render node is not
 * even opened, which is the shipped behaviour bit for bit. "on" is the GPU
 * path: three panel buffers from h713-tv, six capture planes as EGLImages,
 * one draw and one fenced commit per capture frame.
 *
 * Per frame (M9): DQBUF -> draw into the next target -> out-fence ->
 * "warp frame N" with the fence -> QBUF the capture slot back. The QBUF comes
 * LAST on purpose: a slot is overwritten every third frame and the dma-buf
 * carries no fence that says so, so it goes back only after h713-tv has
 * answered for the frame that read it. Pacing is the capture's, not a timer;
 * the one exception is "ctl test", which has no capture and is driven by the
 * poll timeout in main.c.
 */
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "warp.h"

#define FAILS_MAX	5	/* consecutive render failures -> bypass (M10) */
#define FPS_WINDOW	100	/* the last hundred frames, M11 */
/*
 * The firmware hands a slot on BEFORE it is written to the end. Measured on
 * the HY310 on 23.09.2026 through /dev/mem (working journal
 * `keystone-20260922`, "the source race"): the ring pointer moves to a slot
 * anywhere between the start of its write and the end of it, so the bottom
 * line of a published slot still changed up to 11.5 ms after the publish, the
 * middle up to 8.5 ms. A raster display never notices, it reaches those lines
 * later than the writer does; the GPU reads the whole slot in a millisecond
 * and so mixed the previous frame's bottom under the new frame's top - the
 * tearing on fast motion under the warp. A fixed wait (4 ms, first attempt)
 * covered the median, not the tail.
 *
 * So a slot is drawn one vsync late: the slot handed on at this vsync is kept
 * back, the one from the previous vsync is drawn. By then its write is over
 * (a write takes one frame and started no later than its publish), and its
 * next write starts no earlier than two frames after its publish. Two slots
 * are held at a time, the third is queued for the next publish. Cost: one
 * frame of latency, 16.8 ms.
 */

void warp_solve(struct runtime *r)
{
	double m[16], f[16] = { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1 };
	int i;

	int eff[WARP_KEYS];

	/* the flip alone, for the labels: set even when the keystone is refused */
	warp_mirror(r->conf.mode, f);
	for (i = 0; i < 16; i++)
		r->lf[i] = (float)f[i];
	warp_effective(&r->conf, eff);
	if (!warp_matrix(eff, m)) {
		warn("keystone        a corner leaves the panel -- the previous matrix stays (the vendor does the same)");
		return;
	}
	for (i = 0; i < 16; i++)
		if (m[i] != m[i] || m[i] > 1e30 || m[i] < -1e30) {
			/* the vendor's solve divides by zero here */
			warn("keystone        the quad is degenerate (two corners coincide) -- the previous matrix stays");
			return;
		}
	warp_mirror(r->conf.mode, m);	/* F * K: the wall picture onto the panel */
	memcpy(r->m, m, sizeof(r->m));
	for (i = 0; i < 16; i++)
		r->mf[i] = (float)m[i];
	r->matrix_valid = true;
}

static void note(struct runtime *r, const char *why)
{
	snprintf(r->why, sizeof(r->why), "%s", why);
}
bool warp_engage(struct runtime *r)
{
	char why[WARP_WHY];

	if (r->state == WARP_ON)
		return true;
	/*
	 * The source first: without a signal there is nothing to warp, and
	 * claiming the panel to show black would be worse than the ring.
	 * Then the GPU and the capture slots -- BEFORE the panel is claimed:
	 * panfrost refuses a dma-buf whose line pitch is not a multiple of 64
	 * (720x480, 720x576, 1366x768, 1280x1024 ... measured 05.10.2026), and
	 * until that day the claim came first, so every retry took the panel
	 * off the ring and gave it back a moment later: the wall blinked once
	 * a second, green on the first frame of each return. A ring the GPU
	 * refused is not tried again until its geometry changes.
	 */
	if (r->pattern == PATTERN_NONE) {
		if (!source_start(&r->source, why, sizeof(why))) {
			note(r, why);
			return false;
		}
		if (r->source.width == r->refused_w && r->source.height == r->refused_h &&
		    r->source.pitch == r->refused_pitch) {
			source_stop(&r->source);
			return false;	/* said once already, see below */
		}
	}
	if (gl_open(r->render_node, why, sizeof(why)) ||
	    (r->pattern == PATTERN_NONE && !gl_source(&r->source, why, sizeof(why)))) {
		gl_close();
		if (r->pattern == PATTERN_NONE) {
			r->refused_w = r->source.width;
			r->refused_h = r->source.height;
			r->refused_pitch = r->source.pitch;
			warn("warp            %s -- h713-tv keeps the ring %ux%u (pitch %u) until the source changes",
			     why, r->source.width, r->source.height, r->source.pitch);
		}
		source_stop(&r->source);
		note(r, why);
		return false;
	}
	if (!peer_claim(&r->peer, why, sizeof(why)) ||
	    !gl_targets(&r->peer, why, sizeof(why))) {
		peer_release(&r->peer);
		gl_source_drop();
		gl_close();
		source_stop(&r->source);
		note(r, why);
		return false;
	}
	gl_edge(warp_edge_for(r));
	r->state = WARP_ON;
	r->source.held = -1;
	r->check.slot = -1;
	r->fails = 0;
	r->frames = r->dropped = r->refused = 0;
	r->f_mark = 0;
	r->t_mark = r->t_start = now_s();
	r->why[0] = '\0';
	info("warp            on: %s renders %ux%u NV12 onto the video plane%s",
	     gl_renderer(), r->peer.width, r->peer.height,
	     r->pattern == PATTERN_NONE ? "" : ", test pattern");

	return true;
}

void warp_disengage(struct runtime *r, const char *why)
{
	if (r->state == WARP_ON) {
		gl_source_drop();
		source_stop(&r->source);
		peer_release(&r->peer);
		gl_close();
		info("warp            off: %s", why);
	}
	r->state = r->on ? WARP_BYPASS : WARP_OFF;
	note(r, why);
}

/* Put the state where the values ask for it: after every change of the eight
 * values, of "on/off" and of the pattern, and once a second from the main loop
 * while the wanted state cannot be reached (no signal yet, no h713-tv yet).
 */
/* The soft edge belongs to a warped picture: at the identity (a mirrored
 * mount keeps the GPU on there) it would only darken the frame's border. */
int warp_edge_for(struct runtime *r)
{
	int eff[WARP_KEYS];

	warp_effective(&r->conf, eff);
	return warp_identity(eff) ? 0 : r->conf.edge;
}

void warp_apply(struct runtime *r)
{
	int eff[WARP_KEYS];
	bool want;

	warp_effective(&r->conf, eff);
	want = r->on && (r->pattern != PATTERN_NONE || !warp_identity(eff) ||
			 r->conf.mode != MODE_FRONT);	/* a mirrored identity needs the GPU */

	if (!want) {
		if (r->state == WARP_ON)
			warp_disengage(r, r->on ? "the identity needs no GPU (bypass)"
						: "ctl off");
		r->state = r->on ? WARP_BYPASS : WARP_OFF;
		note(r, r->on ? "the identity needs no GPU: h713-tv is on the ring (M10)"
			      : "ctl off");
		return;
	}
	if (r->state != WARP_ON)
		warp_engage(r);
	else
		gl_edge(warp_edge_for(r));	/* a keystone change may have left the identity */
}

static bool source_rebuilt(struct runtime *r)
{
	char why[WARP_WHY];

	gl_source_drop();
	source_stop(&r->source);
	if (!source_start(&r->source, why, sizeof(why)) ||
	    !gl_source(&r->source, why, sizeof(why))) {
		warp_disengage(r, why);
		return false;
	}
	r->source.held = -1;		/* STREAMOFF gave every slot back */
	r->check.slot = -1;
	info("warp            source now %ux%u, the six images are new",
	     r->source.width, r->source.height);

	return true;
}

static void account(struct runtime *r, double t0)
{
	double t = now_s(), ms = (t - t0) * 1e3;

	r->frames++;
	r->frame_ms = ms;
	if (ms > r->frame_ms_max)
		r->frame_ms_max = ms;
	if (r->frames - r->f_mark >= FPS_WINDOW) {
		r->fps = (double)(r->frames - r->f_mark) / (t - r->t_mark);
		r->f_mark = r->frames;
		r->t_mark = t;
	}
}

/* this thread's CPU time, for the trace: what a frame costs the CPU, apart
 * from what the clock governor makes of it */
static unsigned int thread_us(void)
{
	struct timespec t;

	clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
	return (unsigned int)(t.tv_sec * 1000000 + t.tv_nsec / 1000);
}

/* One frame. False when the daemon fell back to bypass, which is the main
 * loop's signal to stop polling the capture.
 */
bool warp_pump(struct runtime *r)
{
	char why[WARP_WHY];
	int slot = 0, fresh, target, fence, rc;
	double t0, t1, t2;
	bool tracing = r->check.trace > 0;
	unsigned int c0 = tracing ? thread_us() : 0, c1 = 0, c2 = 0, c3 = 0, c4 = 0;

	if (r->state != WARP_ON)
		return false;
	gl_timing(tracing);
	if (r->pattern == PATTERN_NONE) {
		if (source_geometry_changed(&r->source) && !source_rebuilt(r))
			return false;
		double prev_dq = r->source.dq_s;

		fresh = source_dequeue(&r->source, why, sizeof(why));
		if (fresh < 0) {
			if (why[0])
				warn("capture         %s", why);
			return true;		/* nothing ready: nothing to do */
		}
		if (tracing) {
			c1 = thread_us();
			r->check.trace--;
			info("trace           slot %d ts %.6f now %.6f", fresh,
			     r->source.slot_s[fresh], now_s());
		}
		if (r->hold) {
			slot = r->source.held;
			r->source.held = fresh;
			if (slot < 0)
				return true;	/* the first slot: kept, drawn next vsync */
			/*
			 * A held slot that is too old is given back undrawn: the
			 * firmware's next write into it begins one ring cycle after
			 * its publish, and the loop only gets here this late when
			 * something stalled it (h713-tv answering a status while the
			 * panel page polls it, 40-55 ms, measured 23.09.). A dropped
			 * frame, not a torn one. "Too old" was a fixed 28 ms, tuned
			 * to a 60 Hz source: a 24 Hz source hands its slots 34 and
			 * 50 ms apart (traced 05.10.2026), so every held slot was
			 * stale by the time the next one arrived and the wall stayed
			 * black (334 stale, 0 frames). The limit follows the
			 * measured gap between the last two slots -- the next write
			 * into the held slot is still two gaps away -- and never
			 * drops below the 28 ms that protect a 60 Hz source.
			 */
			double gap = r->source.dq_s - prev_dq, limit = 0.028;

			if (prev_dq > 0 && gap > 0.020 && gap < 0.120 && gap * 1.25 > limit)
				limit = gap * 1.25;
			if (now_s() - r->source.slot_s[slot] > limit) {
				source_queue(&r->source, slot);
				r->source.stale++;
				return true;
			}
			r->source.settled++;
		} else {
			slot = fresh;	/* the old timing: the self-check's control */
		}
	}
	t0 = now_s();
	if (r->check.trace > 0 && r->check.last_pump && t0 - r->check.last_pump > 0.020)
		info("trace           gap %.1f ms between pumps (poll wake %.1f ms after the timestamp)",
		     (t0 - r->check.last_pump) * 1e3, (t0 - r->source.dq_s) * 1e3);
	/* The target advances only after h713-tv has TAKEN a frame: after an
	 * "ok busy" (the previous commit not yet latched) the same buffer is
	 * drawn again. Advancing on every frame, drops included, put the
	 * render into the buffer still on the wall two frames later - the
	 * tearing Marco saw on fast motion (23.09.). Three buffers: one on
	 * the wall, one pending, one drawn. */
	target = r->target;
	char label[5][40];
	const char *labels[5] = { NULL, NULL, NULL, NULL, NULL };

	if (r->pattern == PATTERN_MASK) {
		int c;

		for (c = 0; c < 4; c++) {
			snprintf(label[c], sizeof(label[c]), "%s%s\nx %d/%d  y %d/%d",
				 warp_corner_name[c], r->mark_corner == c ? " active" : "",
				 r->conf.v[2 * c], warp_limit(r->conf.v, 2 * c),
				 r->conf.v[2 * c + 1], warp_limit(r->conf.v, 2 * c + 1));
			labels[c] = label[c];
		}
		snprintf(label[4], sizeof(label[4]), "zoom %d%%",
			 r->conf.zoom);
		labels[4] = label[4];
	}
	if (!gl_draw(target, slot, r->mf, r->pattern, r->mark_corner, labels, r->lf, why, sizeof(why))) {
		if (r->pattern == PATTERN_NONE)
			source_queue(&r->source, slot);
		if (++r->fails >= FAILS_MAX) {
			warp_disengage(r, why);
			return false;
		}
		warn("warp            %s (%u of %d)", why, r->fails, FAILS_MAX);
		return true;
	}
	r->fails = 0;
	if (tracing)
		c2 = thread_us();
	fence = gl_fence();
	t1 = now_s();
	if (tracing)
		c3 = thread_us();
	rc = peer_frame(&r->peer, target, fence, why, sizeof(why));
	t2 = now_s();
	if (tracing) {
		const struct gl_cost *g = gl_last_cost();
		double gpu_ms = -1;

		c4 = thread_us();
		/*
		 * The GPU's time: from the submit (gl_fence's glFlush) to the
		 * out-fence signalling, waited out here only on "trace N gpu" --
		 * the frame is handed over already, and the next slot is a
		 * vsync away, so the wait costs the loop nothing it would use.
		 */
		if (r->check.trace_gpu && fence >= 0) {
			struct pollfd pf = { .fd = fence, .events = POLLIN };

			if (poll(&pf, 1, 15) > 0)
				gpu_ms = (now_s() - t1) * 1e3;
		}
		info("trace           cost us: dequeue %u, draw %u (luma %u, chroma %u), fence %u, h713-tv %u | gpu busy %.2f ms (submit to fence%s)",
		     c1 - c0, c2 - c1, g->cpu_luma_us, g->cpu_chroma_us, c3 - c2, c4 - c3,
		     gpu_ms, gpu_ms < 0 ? ": not waited, \"trace N gpu\"" : "");
	}
	if (r->check.trace > 0 && (t1 - t0 > 0.010 || t2 - t1 > 0.010))
		info("trace           slow frame %d: draw+fence %.1f ms, sent at %.6f, h713-tv's answer %.1f ms later",
		     target, (t1 - t0) * 1e3, t1, (t2 - t1) * 1e3);
	if (fence >= 0)
		close(fence);		/* the kernel does not take our fd */
	if (rc < 0) {
		if (r->pattern == PATTERN_NONE)
			source_queue(&r->source, slot);
		warp_disengage(r, why);
		return false;
	}
	if (rc > 0)
		r->dropped++;
	else
		r->target = (r->target + 1) % WARP_TARGETS;
	/* only now: h713-tv has the frame, so the slot may be overwritten */
	if (r->pattern == PATTERN_NONE) {
		if (r->check.want > 0 && r->check.slot < 0 && r->frames % 3 == 0) {
			/* kept back for the second draw, queued after it;
			 * every third frame, so the loop keeps its pace */
			r->check.slot = slot;
			r->check.target = target;
			/* the second draw 4 ms after the first: with kernel 0255 the
			 * slot is whole at the first draw (hold on or off), and its
			 * next write begins 33 ms after it was finished -- 12 ms, the
			 * old hold-off timing, ran into that write on the top rows
			 * (11.10.2026, rows 0..34) */
			r->check.due = t0 + 0.004;
			r->check.age0 = t0 - r->source.slot_s[slot];
		} else {
			source_queue(&r->source, slot);
		}
	}
	account(r, t0);
	r->check.last_pump = now_s();

	return true;
}

/* The self-check's second half, from the main loop once the 12 ms are over:
 * the slot the last frame was drawn from is drawn again and compared, then
 * queued back. 12 ms after the first draw the slot is written to the end
 * (11.5 ms measured tail) and its next write has not begun (two frames).
 */
void warp_check_tick(struct runtime *r)
{
	char why[WARP_WHY];
	unsigned long rows;
	int lo, hi;

	if (r->check.slot < 0 || now_s() < r->check.due)
		return;
	if (r->state == WARP_ON && r->check.age0 > (r->hold ? 0.024 : 0.008)) {
		/* the first draw itself was late (the loop stalled): the slot may
		 * have been overwritten from the top by then, which is not what
		 * this measures - a sample only counts with the normal timing */
		r->check.late++;
	} else if (r->state == WARP_ON &&
	    gl_check_compare(r->check.target, r->check.slot, r->mf, &rows, &lo, &hi,
			     why, sizeof(why))) {
		r->check.frames++;
		if (rows) {
			r->check.differing++;
			info("check           frame %lu: %lu of 32 rows differ, rows %d..%d, slot %d, first draw %.1f ms after its vsync, second %.1f ms later",
			     r->check.frames, rows, lo, hi, r->check.slot, r->check.age0 * 1e3,
			     (now_s() - r->check.due + 0.004) * 1e3);
			if (r->check.row_lo < 0 || lo < r->check.row_lo)
				r->check.row_lo = lo;
			if (hi > r->check.row_hi)
				r->check.row_hi = hi;
			if (rows > r->check.rows_max)
				r->check.rows_max = rows;
		}
	} else if (r->state == WARP_ON) {
		warn("check           %s", why);
	}
	if (r->state == WARP_ON)
		source_queue(&r->source, r->check.slot);
	r->check.slot = -1;
	if (--r->check.want <= 0) {
		r->check.want = 0;
		info("check           %lu frames, %lu with differing rows (rows %d..%d, at most %lu of 32 sampled in one frame), %lu late samples skipped, hold %s",
		     r->check.frames, r->check.differing, r->check.row_lo, r->check.row_hi,
		     r->check.rows_max, r->check.late, r->hold ? "on" : "off");
	}
}

static const char *state_text(const struct runtime *r)
{
	return r->state == WARP_ON ? "on" : r->state == WARP_BYPASS ? "bypass" : "off";
}

/* The status block (M11): the eight values, the mode, the reason for a bypass
 * and the last hundred frames' timing -- A11's finding F2, "say it on the
 * status line, not only in the journal".
 */
void warp_status(struct runtime *r, char *buf, size_t n)
{
	struct textbuf t = { buf, n, 0 };
	int c;

	text_add(&t, "ok status\n");
	text_add(&t, "warp            %s%s%s\n", state_text(r),
		 r->why[0] ? " -- " : "", r->why[0] ? r->why : "");
	text_add(&t, "keystone       ");
	for (c = 0; c < 4; c++)
		text_add(&t, " %s %d,%d", warp_corner_name[c], r->conf.v[2 * c],
			 r->conf.v[2 * c + 1]);
	text_add(&t, " (per-mille, positive inward)\n");
	text_add(&t, "zoom            %d percent%s\n", r->conf.zoom,
		 r->conf.zoom == 100 ? " (none)" : " (smaller about its centre, inside the keystone)");
	text_add(&t, "edge            %d%s\n", r->conf.edge,
		 r->conf.edge ? " px (the vendor's soft border: 20/255 over the outer half, a linear ramp over one width)"
			      : " (off: a hard edge)");
	text_add(&t, "mode            %s%s\n", warp_mode_name[r->conf.mode],
		 r->conf.mode == MODE_FRONT ? "" : " (mirrored for the mount; the GPU runs even at the identity)");
	if (r->matrix_valid) {
		text_add(&t, "corners        ");
		for (c = 0; c < 4; c++) {
			double p[2], q[2];

			warp_corner_ndc(c, p);
			warp_point(r->m, p[0], p[1], q);
			text_add(&t, " %s %+.3f,%+.3f", warp_corner_name[c], q[0], q[1]);
		}
		text_add(&t, " (NDC, y = -1 is the top of the panel)\n");
	}
	text_add(&t, "pattern         %s\n",
		 r->pattern == PATTERN_MASK ? (r->mark_corner >= 0 ? "mask (a corner marked)" : "mask") :
		 r->pattern == PATTERN_GRID ? "grid" :
		 r->pattern == PATTERN_BORDER ? "border" : "none (the capture)");
	if (r->source.width)
		text_add(&t, "source          %s %ux%u, line pitch %u/%u, %d dma-buf%s per slot%s\n",
			 r->source.path, r->source.width, r->source.height,
			 r->source.pitch, r->source.cpitch, r->source.planes,
			 r->source.planes == 1 ? "" : "s",
			 r->source.streaming ? "" : " (not streaming)");
	else
		text_add(&t, "source          not open\n");
	if (r->peer.fd >= 0)
		text_add(&t, "panel           %ux%u, line pitch %u, three NV12 buffers from %s (the video plane)\n",
			 r->peer.width, r->peer.height, r->peer.pitch, r->peer.path);
	else
		text_add(&t, "panel           nothing claimed (%s)\n", r->peer.path);
	text_add(&t, "renderer        %s\n", gl_renderer());
	text_add(&t, "frames          %lu at %.1f fps, dropped %lu, commits %lu, busy %lu, link errors %lu\n",
		 r->frames, r->fps, r->dropped, r->peer.commits, r->peer.busy,
		 r->peer.errors);
	text_add(&t, "timing          last frame %.1f ms, worst %.1f ms (DQBUF to the answer), capture timeouts %lu, drawn one vsync late %lu, stale slots skipped %lu\n",
		 r->frame_ms, r->frame_ms_max, r->source.timeouts, r->source.settled, r->source.stale);
	text_add(&t, "hold            %s (a slot is drawn one vsync late)\n", r->hold ? "on" : "off");
	if (r->check.frames || r->check.want)
		text_add(&t, "check           %lu frames%s, %lu with differing rows (rows %d..%d, at most %lu of 32 sampled in one frame), %lu late samples skipped\n",
			 r->check.frames, r->check.want ? ", running" : "", r->check.differing,
			 r->check.row_lo, r->check.row_hi, r->check.rows_max, r->check.late);
	text_add(&t, "config          %s%s, start %s\n", r->conf.path,
		 r->conf.present ? "" : " (missing)",
		 r->conf.start_on ? "on" : "off");
}
