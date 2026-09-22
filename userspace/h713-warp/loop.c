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
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "warp.h"

#define FAILS_MAX	5	/* consecutive render failures -> bypass (M10) */
#define FPS_WINDOW	100	/* the last hundred frames, M11 */

void warp_solve(struct runtime *r)
{
	double m[16];
	int i;

	if (!warp_matrix(r->conf.v, m)) {
		warn("keystone        a corner leaves the panel -- the previous matrix stays (the vendor does the same)");
		return;
	}
	for (i = 0; i < 16; i++)
		if (m[i] != m[i] || m[i] > 1e30 || m[i] < -1e30) {
			/* the vendor's solve divides by zero here */
			warn("keystone        the quad is degenerate (two corners coincide) -- the previous matrix stays");
			return;
		}
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
	 * Every failure below takes the same way back, and each of the three
	 * releases there is a no-op for a step that was never reached.
	 */
	if ((r->pattern == PATTERN_NONE && !source_start(&r->source, why, sizeof(why))) ||
	    gl_open(r->render_node, why, sizeof(why)) ||
	    !peer_claim(&r->peer, why, sizeof(why)) ||
	    !gl_targets(&r->peer, why, sizeof(why)) ||
	    (r->pattern == PATTERN_NONE && !gl_source(&r->source, why, sizeof(why)))) {
		peer_release(&r->peer);
		gl_close();
		source_stop(&r->source);
		note(r, why);
		return false;
	}
	r->state = WARP_ON;
	r->fails = 0;
	r->frames = r->dropped = r->refused = 0;
	r->f_mark = 0;
	r->t_mark = r->t_start = now_s();
	r->why[0] = '\0';
	info("warp            on: %s renders %ux%u onto the primary plane%s",
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
void warp_apply(struct runtime *r)
{
	bool want = r->on && (r->pattern != PATTERN_NONE ||
			      !warp_identity(r->conf.v));

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

/* One frame. False when the daemon fell back to bypass, which is the main
 * loop's signal to stop polling the capture.
 */
bool warp_pump(struct runtime *r)
{
	char why[WARP_WHY];
	int slot = 0, target, fence, rc;
	double t0;

	if (r->state != WARP_ON)
		return false;
	if (r->pattern == PATTERN_NONE) {
		if (source_geometry_changed(&r->source) && !source_rebuilt(r))
			return false;
		slot = source_dequeue(&r->source, why, sizeof(why));
		if (slot < 0) {
			if (why[0])
				warn("capture         %s", why);
			return true;		/* nothing ready: nothing to do */
		}
	}
	t0 = now_s();
	target = (int)(r->frames % WARP_TARGETS);
	if (!gl_draw(target, slot, r->mf, r->pattern, why, sizeof(why))) {
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
	fence = gl_fence();
	rc = peer_frame(&r->peer, target, fence, why, sizeof(why));
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
	/* only now: h713-tv has the frame, so the slot may be overwritten */
	if (r->pattern == PATTERN_NONE)
		source_queue(&r->source, slot);
	account(r, t0);

	return true;
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
		text_add(&t, "panel           %ux%u, line pitch %u, three buffers from %s\n",
			 r->peer.width, r->peer.height, r->peer.pitch, r->peer.path);
	else
		text_add(&t, "panel           nothing claimed (%s)\n", r->peer.path);
	text_add(&t, "renderer        %s\n", gl_renderer());
	text_add(&t, "frames          %lu at %.1f fps, dropped %lu, commits %lu, busy %lu, link errors %lu\n",
		 r->frames, r->fps, r->dropped, r->peer.commits, r->peer.busy,
		 r->peer.errors);
	text_add(&t, "timing          last frame %.1f ms, worst %.1f ms (DQBUF to the answer), capture timeouts %lu\n",
		 r->frame_ms, r->frame_ms_max, r->source.timeouts);
	text_add(&t, "config          %s%s, start %s\n", r->conf.path,
		 r->conf.present ? "" : " (missing)",
		 r->conf.start_on ? "on" : "off");
}
