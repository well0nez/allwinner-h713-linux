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
#define FRESH_S		0.010	/* after a pause: a slot handed on this recently is drawn as the next one would be */
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

/* The render node closes when nothing needs it: no claim, and no client buffer imported. The bypass
 * without a client keeps the shipped behaviour: the node is not even open. */
void warp_gl_idle(struct runtime *r)
{
	/*
	 * Kept open while the ring is wanted and only h713-tv's leave is missing (no signal, "ctl off", h713-tv away): the
	 * next claim then costs the capture and the claim, not the EGL start - "ctl auto" to the first frame took 0.28 s
	 * with the start (HY310, 17.10.2026), the straight ring waiting for it. Nothing is drawn meanwhile; the GPU sleeps.
	 */
	if (r->state != WARP_ON && !server_busy(r->srv) && gl_is_open() && !warp_want_ring(r))
		gl_close();
}

static void on_common(struct runtime *r)
{
	r->state = WARP_ON;
	r->source.held = -1;
	r->check.slot = -1;
	r->fails = 0;
	r->frames = r->dropped = r->refused = 0;
	r->f_mark = 0;
	r->t_mark = r->t_start = now_s();
	r->why[0] = '\0';
}

/* The panel for the Wayland client : no capture - the claim needs no signal and the
 * capture ring stays closed (-11.9 MiB, G-M) - only the render node and h713-tv's three targets. */
static bool engage_client(struct runtime *r)
{
	char why[WARP_WHY];

	if (gl_open(r->render_node, why, sizeof(why)) ||
	    !peer_claim(&r->peer, SRC_CLIENT, why, sizeof(why)) ||
	    !gl_targets(&r->peer, why, sizeof(why))) {
		peer_release(&r->peer);
		gl_targets_drop();
		note(r, why);
		warp_gl_idle(r);
		return false;
	}
	r->src = SRC_CLIENT;
	on_common(r);
	gl_edge(r->on ? warp_edge_for(r) : 0);
	info("warp            on: %s renders the Wayland client %ux%u NV12 onto the video plane%s", gl_renderer(),
	     r->peer.width, r->peer.height, r->on ? "" : " (warp = off: no keystone)");
	server_panel(r->srv, r->peer.width, r->peer.height);
	server_engaged(r->srv, true);

	return true;
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
	/*
	 * h713-tv said "source client" the last time: it refuses a ring claim, so the policy is asked alone first - one
	 * short line instead of STREAMON, six EXPBUF and STREAMOFF once a second for a refusal.
	 */
	if (r->peer.tv_source == TV_CLIENT && (!peer_source(&r->peer) || r->peer.tv_source == TV_CLIENT)) {
		note(r, r->peer.tv_source == TV_CLIENT ? "h713-tv's source is client: no ring until it changes"
						       : "h713-tv did not answer \"source\"");
		return false;
	}
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
		gl_source_drop();
		if (!server_busy(r->srv))
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
	if (!peer_claim(&r->peer, SRC_RING, why, sizeof(why)) ||
	    !gl_targets(&r->peer, why, sizeof(why))) {
		if (r->peer.fd >= 0) {		/* claimed, and the GPU did not take h713-tv's buffers */
			r->gpu_failed = true;
			warp_want_tell(r);	/* "none" before the release: h713-tv waits for no claim of ours */
		}
		peer_release(&r->peer);
		gl_targets_drop();
		gl_source_drop();
		warp_gl_idle(r);
		source_stop(&r->source);
		note(r, why);
		return false;
	}
	gl_edge(warp_edge_for(r));
	r->src = SRC_RING;
	on_common(r);
	info("warp            on: %s renders %ux%u NV12 onto the video plane%s",
	     gl_renderer(), r->peer.width, r->peer.height,
	     r->pattern == PATTERN_NONE ? "" : ", test pattern");

	return true;
}

/* the ring is to be drawn through the GPU: a keystone, a mirrored mount or a test pattern (else h713-tv shows it) */
static bool ring_wanted(const struct runtime *r)
{
	int eff[WARP_KEYS];

	warp_effective(&r->conf, eff);
	return r->on && (r->pattern != PATTERN_NONE || !warp_identity(eff) ||
			 r->conf.mode != MODE_FRONT);	/* a mirrored identity needs the GPU */
}

/*
 * The word for h713-tv on the want link (P3 of the media side project): the ring will be claimed as soon as h713-tv lets
 * it - so h713-tv keeps the straight ring off the video plane and waits for the claim (at most a second). Not when the
 * ring is not wanted (the identity, "warp = off": h713-tv's own ring is the picture), when the GPU refused this ring's
 * geometry (until the source changes), or when the GPU failed the last claim (until a frame is drawn again): then the
 * straight ring is the picture, at once.
 */
bool warp_want_ring(const struct runtime *r)
{
	bool refused = r->refused_w && r->source.width == r->refused_w && r->source.height == r->refused_h &&
		       r->source.pitch == r->refused_pitch && r->pattern == PATTERN_NONE;

	return ring_wanted(r) && !r->gpu_failed && !refused;
}

void warp_want_tell(struct runtime *r)
{
	peer_want(&r->peer, warp_want_ring(r), r->on);
}

/*
 * From the ring to the client, and back, on the claim that stands ("warp switch", h713-tv of 16.10.2026): the same
 * three buffers, the video plane up all the time, the wall going from the last frame of the one to the first of
 * the other. Giving the claim back and claiming again put the unwarped ring on the plane for a moment and switched
 * the plane off for the new claim - a flash at every change between HDMI and a client. False when it did not
 * happen: the claim is then as it was, and the caller gives it back and claims again, as before.
 */
static bool switch_to_client(struct runtime *r)
{
	char why[WARP_WHY];

	if (!peer_switch(&r->peer, SRC_CLIENT, why, sizeof(why))) {
		warn("warp            no switch to the client on the ring's buffers: %s", why);
		return false;
	}
	gl_source_drop();
	source_stop(&r->source);
	r->src = SRC_CLIENT;
	on_common(r);
	gl_edge(r->on ? warp_edge_for(r) : 0);
	info("warp            on: the Wayland client takes over the ring's buffers -- %s renders it %ux%u NV12 onto the video plane%s%s",
	     gl_renderer(), r->peer.width, r->peer.height, r->on ? "" : " (warp = off: no keystone)",
	     server_shown(r->srv) ? "" : "; no picture of it yet, the panel keeps the ring's last frame");
	server_panel(r->srv, r->peer.width, r->peer.height);
	server_engaged(r->srv, true);

	return true;
}

static bool switch_to_ring(struct runtime *r)
{
	char why[WARP_WHY];

	if (r->pattern == PATTERN_NONE) {
		if (!source_start(&r->source, why, sizeof(why))) {
			warn("warp            no switch to the ring: %s", why);
			return false;
		}
		if ((r->source.width == r->refused_w && r->source.height == r->refused_h &&
		     r->source.pitch == r->refused_pitch) || !gl_source(&r->source, why, sizeof(why))) {
			gl_source_drop();
			source_stop(&r->source);
			warn("warp            no switch to the ring %ux%u: %s", r->source.width, r->source.height,
			     why[0] ? why : "the GPU refused this geometry before");
			return false;
		}
	}
	server_engaged(r->srv, false);	/* nothing more of the client is presented; it pauses */
	if (!peer_switch(&r->peer, SRC_RING, why, sizeof(why))) {
		warn("warp            no switch to the ring on the client's buffers: %s", why);
		gl_source_drop();
		source_stop(&r->source);
		return false;
	}
	r->src = SRC_RING;
	on_common(r);
	gl_edge(warp_edge_for(r));
	info("warp            on: the ring takes over the client's buffers -- %s renders %ux%u NV12 onto the video plane%s",
	     gl_renderer(), r->peer.width, r->peer.height, r->pattern == PATTERN_NONE ? "" : ", test pattern");

	return true;
}

void warp_disengage(struct runtime *r, const char *why)
{
	bool was = r->state == WARP_ON;

	if (was) {
		if (r->src == SRC_CLIENT)
			server_engaged(r->srv, false);
		gl_source_drop();
		source_stop(&r->source);
		gl_targets_drop();
		peer_release(&r->peer);
	}
	r->state = r->on ? WARP_BYPASS : WARP_OFF;
	r->cover = r->resume = false;	/* the claim is gone, and with it the page's word about it (peer_release) */
	if (was) {
		warp_gl_idle(r);
		info("warp            off: %s", why);
	}
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
	bool want = ring_wanted(r), client = server_shown(r->srv);

	/*
	 * A Wayland client is drawn whenever it is shown and h713-tv lets it: always through the GPU, even
	 * at the identity (there is no other way onto the panel for it). A keystone or pattern change only asks
	 * for the picture again. A ring claim gives way to a client by itself only under "source auto"; under "hdmi"
	 * h713-tv would refuse the client, and every switch would blink the wall.
	 */
	/* h713-tv no longer allows the client ("note source hdmi"): the ring on the same buffers, or the panel back */
	if (r->state == WARP_ON && r->src == SRC_CLIENT && r->peer.tv_source == TV_HDMI) {
		if (want && switch_to_ring(r))
			return;
		warp_disengage(r, "h713-tv's source is hdmi: the client's claim is given back");
	}
	if (r->state == WARP_ON && r->src == SRC_CLIENT) {
		gl_edge(r->on ? warp_edge_for(r) : 0);
		server_redraw(r->srv);
		/* "auto" over a claim that holds a picture and has no client shown: the ring in two seconds, as after a
		 * client that went (a program that said it starts and never came, then "source auto") */
		if (!client && r->peer.tv_source == TV_AUTO)
			server_recheck(r->srv, now_s() + 2.0);
		return;
	}
	/*
	 * A client is shown while the ring stands and h713-tv's last word was "hdmi": ask it. A policy change
	 * reaches the warp with the "ok" of the next ring frame, or at once as a note - and a ring that stalls sends no
	 * frame (HY310, 15.10.2026 after a standby: the ring claimed, 0 frames, Kodi waited five minutes behind it).
	 * main.c asks again once a second.
	 */
	if (r->state == WARP_ON && r->src == SRC_RING && client && r->peer.tv_source != TV_AUTO &&
	    r->peer.tv_source != TV_CLIENT)
		peer_source(&r->peer);
	if (r->state == WARP_ON && r->src == SRC_RING && client &&
	    (r->peer.tv_source == TV_AUTO || r->peer.tv_source == TV_CLIENT)) {
		if (switch_to_client(r))
			return;
		warp_disengage(r, "a Wayland client came, and h713-tv's source puts it before the ring");
	}
	/*
	 * "note source client" - a program is the mode - and no picture of it yet: the ring's claim becomes the client's on
	 * the same buffers. The ring is drawn no more and the video plane keeps its last frame until the program's first
	 * picture: HDMI is a mode, not what fills the time a program needs to start (P2b). If the program does not connect
	 * within PROGRAM_S, warp_client_gone() decides. Only a refused switch gives the claim back (the console until then).
	 */
	if (r->state == WARP_ON && r->src == SRC_RING && !client && r->peer.tv_source == TV_CLIENT) {
		if (switch_to_client(r)) {
			server_recheck(r->srv, now_s() + PROGRAM_S);
			return;
		}
		warp_disengage(r, "h713-tv's source is client, and the ring's claim could not become the client's");
	}
	if (r->state != WARP_ON && client && engage_client(r))
		return;

	if (!want) {
		warp_want_tell(r);	/* "none" before the release: h713-tv puts its ring up at once, without waiting */
		if (r->state == WARP_ON)
			warp_disengage(r, r->on ? "the identity needs no GPU (bypass)"
						: "ctl off");
		warp_gl_idle(r);	/* the render node kept for a ring that is no longer wanted */
		r->state = r->on ? WARP_BYPASS : WARP_OFF;
		if (!client)	/* else the reason stays the client's: h713-tv's refusal */
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
	if (warp_paused(r))
		return true;		/* a page hides the panel: nothing is drawn (the test pattern's heartbeat) */
	gl_timing(tracing);
	if (r->pattern == PATTERN_NONE) {
		if (source_geometry_changed(&r->source) && !source_rebuilt(r))
			return false;
		double prev_dq = r->source.dq_s;

		fresh = source_dequeue(&r->source, why, sizeof(why));
		/*
		 * The first dequeue after a pause: the capture was not asked while the page stood, so every slot came back
		 * done long ago, and the firmware has written each many times since - an old slot may be under its pen
		 * right now. They all go back; the newest is drawn only when it was handed on a moment ago, else the next
		 * hand-on is waited for (a vsync at most).
		 */
		if (r->resume) {
			int k;

			r->resume = false;
			if (r->source.held >= 0) {
				source_queue(&r->source, r->source.held);
				r->source.held = -1;
			}
			while (fresh >= 0 && (k = source_dequeue(&r->source, why, sizeof(why))) >= 0) {
				source_queue(&r->source, fresh);
				fresh = k;
			}
			if (fresh >= 0 && (r->hold || now_s() - r->source.slot_s[fresh] > FRESH_S)) {
				source_queue(&r->source, fresh);
				fresh = -1;
				why[0] = '\0';
			}
			prev_dq = 0;		/* no gap to measure across the pause */
		}
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
			r->gpu_failed = true;
			warp_want_tell(r);	/* "none" before the release */
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
	int flip;

	rc = peer_frame(&r->peer, target, fence, &flip, why, sizeof(why));
	t2 = now_s();
	if (flip >= 0)
		close(flip);	/* a client claim's flip fence: a test pattern does not need it */
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
	r->gpu_failed = false;		/* a frame was drawn: the ring can be promised to h713-tv again */
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
	/* "source auto" came while the ring stood (h713-tv said it with this frame): a client that waits goes first */
	if (r->peer.tv_source == TV_AUTO && server_shown(r->srv)) {
		warp_apply(r);
		return r->state == WARP_ON;
	}

	return true;
}

bool warp_client_live(const struct runtime *r)
{
	return r->state == WARP_ON && r->src == SRC_CLIENT;
}

/*
 * The client's quad: the keystone as for the ring (with "warp = off" none), and a picture smaller
 * than the panel in the middle at its own size (letterbox) - the unit quad scaled first, so K * S.
 */
static void client_matrix(const struct runtime *r, const struct gl_image *im, float out[16])
{
	static const double id[16] = { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1 };
	const double *k = r->on && r->matrix_valid ? r->m : id;
	double sx = (double)gl_image_width(im) / r->peer.width, sy = (double)gl_image_height(im) / r->peer.height;
	int i;

	sx = sx > 1 ? 1 : sx;
	sy = sy > 1 ? 1 : sy;
	for (i = 0; i < 16; i++)	/* column-major: S scales the first two columns */
		out[i] = (float)(k[i] * (i < 4 ? sx : i < 8 ? sy : 1.0));
}

/* after h713-tv's answer: the target moves on a commit, stays on a busy; a broken link ends the claim */
static int client_answer(struct runtime *r, int rc, double t0, const char *why)
{
	if (rc < 0) {
		warp_disengage(r, why);
		return -1;
	}
	if (rc == 0) {
		r->target = (r->target + 1) % WARP_TARGETS;
		r->gpu_failed = false;
		account(r, t0);
	} else {
		r->dropped++;
	}
	return rc;
}

/* One client frame (wayland.c takes the buffer): draw, the render fence to h713-tv and a dup of it back to the
 * server - the buffer is released when it signals - and h713-tv's flip fence, the client's clock. */
int warp_client_frame(struct runtime *r, const struct gl_image *im, int *render, int *flip)
{
	char why[WARP_WHY];
	double t0 = now_s();
	float m[16];
	int fence, rc;

	*render = *flip = -1;
	if (!warp_client_live(r))
		return -1;
	client_matrix(r, im, m);
	if (!gl_draw_client(r->target, im, m, why, sizeof(why))) {
		if (++r->fails >= FAILS_MAX) {
			r->gpu_failed = true;	/* the ring would fail the same way: no ring claim promised to h713-tv */
			warp_disengage(r, why);
			return -1;
		}
		warn("warp            %s (%u of %d)", why, r->fails, FAILS_MAX);
		return 2;
	}
	r->fails = 0;
	fence = gl_fence();
	*render = fence >= 0 ? dup(fence) : -1;
	rc = peer_frame(&r->peer, r->target, fence, flip, why, sizeof(why));
	if (fence >= 0)
		close(fence);
	return client_answer(r, rc, t0, why);
}

/* after "ok busy": the same target, drawn already, once more; render is the frame's render fence or -1 */
int warp_client_resend(struct runtime *r, int render, int *flip)
{
	char why[WARP_WHY];
	int rc;

	*flip = -1;
	if (!warp_client_live(r)) {
		if (render >= 0)
			close(render);
		return -1;
	}
	rc = peer_frame(&r->peer, r->target, render, flip, why, sizeof(why));
	if (render >= 0)
		close(render);
	return client_answer(r, rc, now_s(), why);
}

void warp_client_shown(struct runtime *r)
{
	if (r->state != WARP_ON || r->src != SRC_CLIENT)
		warp_apply(r);
}

/*
 * The client's toplevel is gone for good (two seconds without a new one, wayland.c), or a program was waited for.
 * Under "source client" a program is the mode: while one runs (its connection stands) or has said that it starts
 * (h713-tv's "note source client" after the last connection came) the claim stays and the video plane keeps the last
 * picture - between two programs, while one builds its window anew - and nothing is drawn until the next picture
 * (P2b). Once neither is so, the program has ended: h713-tv's source goes back to "auto", HDMI is the mode again.
 * Then, and under "auto", the ring's warp takes over the buffers if it is wanted; otherwise the panel goes back and
 * h713-tv shows what "source" says.
 */
void warp_client_gone(struct runtime *r)
{
	if (warp_client_live(r) && r->peer.tv_source == TV_CLIENT &&
	    server_program(r->srv, r->peer.client_said)) {
		double left = r->peer.client_said + PROGRAM_S - now_s();

		/* a program said it starts and has not connected yet: asked again when it is overdue (with one, the
		 * last connection's close asks again) */
		if (left > 0)
			server_recheck(r->srv, now_s() + left);
		warp_gl_idle(r);
		return;
	}
	if (warp_client_live(r) && r->peer.tv_source == TV_CLIENT) {
		info("warp            the program has ended (no connection, none said that it starts): h713-tv's source goes back to auto");
		peer_set_source(&r->peer, "auto");
	}
	if (warp_client_live(r) &&
	    !(ring_wanted(r) && r->peer.tv_source != TV_CLIENT && switch_to_ring(r))) {
		warp_disengage(r, "the Wayland client is gone");
		warp_apply(r);
	}
	warp_gl_idle(r);
}

/* paused: a page hides the panel. h713-tv switches the video plane off under it (nothing of HDMI behind a page, 17.10.2026),
 * so nothing is drawn at all - also not for a claim made under the page: the first frame comes at the page's end */
bool warp_paused(const struct runtime *r)
{
	return r->state == WARP_ON && r->peer.cover;
}

/*
 * h713-tv said "note cover on|off" (main.c sees peer.cover change). On: nothing more is drawn - the ring's capture is
 * not asked (main.c), a client's pictures are taken and held, not drawn (wayland.c) - and the slots this daemon holds
 * go back. Off: the next frame is drawn at once - a fresh slot of the ring, the newest picture of the client, or the
 * client's buffer on the panel once more - and h713-tv lays the end of the page on that frame.
 */
void warp_cover(struct runtime *r)
{
	r->cover = r->peer.cover;
	if (r->state != WARP_ON)
		return;
	if (r->cover) {
		if (r->src == SRC_RING && r->source.held >= 0) {
			source_queue(&r->source, r->source.held);
			r->source.held = -1;
		}
		r->paused_at = now_s();
		info("warp            paused: an opaque page hides the panel -- nothing is drawn (h713-tv switches the video plane off)");
		return;
	}
	info("warp            on again: the page is gone after %.1f s -- the next frame is drawn now",
	     r->paused_at > 0 ? now_s() - r->paused_at : 0.0);
	r->paused_at = 0;
	if (r->src == SRC_RING)
		r->resume = r->pattern == PATTERN_NONE;
	else
		server_resume(r->srv, r->peer.commits > 0);
}

/* the client's buffer on the panel committed once more, nothing drawn: the end of a page rides on it */
int warp_client_repeat(struct runtime *r, int *flip)
{
	char why[WARP_WHY];
	int rc;

	*flip = -1;
	if (!warp_client_live(r) || !r->peer.commits)
		return -1;
	rc = peer_frame(&r->peer, (r->target + WARP_TARGETS - 1) % WARP_TARGETS, -1, flip, why, sizeof(why));
	if (rc < 0)
		warp_disengage(r, why);
	return rc;
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
	text_add(&t, "want            %s%s\n", warp_want_ring(r) ? "ring (the ring is claimed when h713-tv lets it)" :
		 r->gpu_failed ? "none (the GPU failed the last claim)" : "none",
		 r->peer.want_refused ? " -- h713-tv does not take \"warp want\"" :
		 r->peer.want_fd < 0 ? " -- not said: no link to h713-tv" :
		 r->peer.want_said == (int)warp_want_ring(r) ? ", said to h713-tv" : ", not said yet");
	text_add(&t, "renderer        %s\n", gl_renderer());
	if (r->state == WARP_ON)
		text_add(&t, "drawing         %s\n", r->src == SRC_CLIENT ? "the Wayland client" : "the capture ring");
	server_status(r->srv, &t);
	text_add(&t, "frames          %lu at %.1f fps, dropped %lu, commits %lu, busy %lu, link errors %lu\n",
		 r->frames, r->fps, r->dropped, r->peer.commits, r->peer.busy,
		 r->peer.errors);
	text_add(&t, "timing          last frame %.1f ms, worst %.1f ms (DQBUF to the answer), capture timeouts %lu, drawn one vsync late %lu, stale slots skipped %lu\n",
		 r->frame_ms, r->frame_ms_max, r->source.timeouts, r->source.settled, r->source.stale);
	text_add(&t, "hold            %s (a slot is drawn one vsync late)\n", r->hold ? "on" : "off");
	if (warp_paused(r))
		text_add(&t, "pause           an opaque page hides the panel: nothing is drawn, the video plane is off (%.1f s)\n",
			 now_s() - r->paused_at);
	if (r->check.frames || r->check.want)
		text_add(&t, "check           %lu frames%s, %lu with differing rows (rows %d..%d, at most %lu of 32 sampled in one frame), %lu late samples skipped\n",
			 r->check.frames, r->check.want ? ", running" : "", r->check.differing,
			 r->check.row_lo, r->check.row_hi, r->check.rows_max, r->check.late);
	text_add(&t, "config          %s%s, start %s\n", r->conf.path,
		 r->conf.present ? "" : " (missing)",
		 r->conf.start_on ? "on" : "off");
}
