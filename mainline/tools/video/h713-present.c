// SPDX-License-Identifier: GPL-2.0
/*
 * h713-present -- put frames on the H713 panel from Linux, through the AFBD
 * scanout path U-Boot already proved.
 *
 * Runs ON THE TARGET. Build with: gcc -O2 -o h713-present h713-present.c
 *
 * This is the Linux-side twin of h713_disp's fb-anim / fb-anim-db. It writes
 * a frame into the reserved scanout buffer, points the AFBD source register at
 * it, and commits using the exact order recovered from the stock ge2d_dev.ko:
 *
 *     clear the write-one-to-clear IRQ status  (+0x168)
 *     set bit 0 of the channel control         (+0x140)
 *     write literal 1 to the channel ready     (+0x144)
 *     poll for the completion bit              (+0x168 BIT(1))
 *
 * The `bar` mode is deliberately synthetic and decoder-independent: it is the
 * controlled reference that a decoder fault cannot masquerade as. Get `bar`
 * working before believing anything about a decoded frame.
 *
 * WHY THIS WORKS WITHOUT A KERNEL DRIVER: CONFIG_STRICT_DEVMEM=y blocks
 * /dev/mem on System RAM, but uboot-scanout@6c100000 is a `no-map` reservation,
 * so it is carved out of System RAM and appears as a top-level /proc/iomem
 * entry. page_is_ram() is false for it, and devmem_is_allowed() therefore
 * permits the mapping.
 *
 * CONSEQUENCE, and it matters for M3: because pfn_is_map_memory() is false,
 * arm64's phys_mem_access_prot() maps it pgprot_noncached -- Device-nGnRnE, not
 * write-combining. Bulk stores to it are slow and do not burst. `--time`
 * reports the achieved fill bandwidth so this is measured, not assumed.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define W               1280
#define H               720
#define FB_BYTES        (W * H * 4)             /* ARGB8888 */
#define FB_FRONT        0x6c100000UL
#define FB_BACK         0x6c500000UL
#define FB_WINDOW       0x800000UL              /* both buffers, per patch 0024 */

#define AFBD_BASE       0x05600000UL
#define AFBD_CTRL       0x140
#define AFBD_READY      0x144
#define AFBD_STATUS     0x168
#define AFBD_STRIDE     0x170
#define AFBD_SRC        0x178
#define AFBD_DIRTY      0x6c

/*
 * The real vblank signal, from the vendor's dec_irq_query() (patch 0013,
 * decd_hw.c): status at workaround+96 = 0x056000c0, interrupt enable at
 * +100 = 0x056000c4, acked by writing bit 0 back to +0xc0. The vendor swaps
 * buffers INSIDE this interrupt (dec_vsync_handler -> sync_cb); bar-vs
 * mirrors that order from userspace via wait_vblank().
 */
#define AFBD_IRQ_ST0    0xc0
#define AFBD_IRQ_ST1    0xc4

/*
 * CCU, always clocked, so reading it is safe from any state. Bit 31 is the
 * AFBD clock gate. The display blocks wedge the interconnect when read while
 * gated, so this is the precondition check that keeps a cold run from hanging
 * the board -- the same reason h713_disp's scanrate/regscan refuse cold.
 */
#define CCU_AFBD_CLK    0x02001dc0UL

static volatile uint32_t *regs, *ccu;
static volatile uint32_t *fb_front, *fb_back;

static uint32_t rd(volatile uint32_t *base, unsigned off) { return base[off / 4]; }
static void wr(volatile uint32_t *base, unsigned off, uint32_t v) { base[off / 4] = v; }

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

/* Returns wait time in us, or -1 if the completion bit never arrived. */
static double commit(void)
{
	uint32_t pending = rd(regs, AFBD_STATUS);
	uint32_t ctrl;
	double t0;

	if (pending)
		wr(regs, AFBD_STATUS, pending);         /* write-one-to-clear */

	ctrl = rd(regs, AFBD_CTRL);
	wr(regs, AFBD_CTRL, ctrl | 1u);
	wr(regs, AFBD_READY, 1);

	t0 = now_ms();
	while (now_ms() - t0 < 50.0) {
		if (rd(regs, AFBD_STATUS) & 2u)
			return (now_ms() - t0) * 1000.0;
		usleep(100);
	}
	return -1.0;
}

/*
 * Barrier before the flip, and it is not paranoia: the framebuffer is written
 * through a plain pointer so the compiler can vectorise the fill, while the
 * source register goes through a volatile one to a different peripheral --
 * nothing else orders the two. Flipping to a buffer whose stores have not
 * drained shows the raster a half-written surface.
 */
static void flip_to(unsigned long phys)
{
	__sync_synchronize();                   /* dsb: drain the fill first */
	wr(regs, AFBD_SRC, (uint32_t)phys);
}

/*
 * Poll the vendor's vsync condition and ack it, mirroring dec_irq_query().
 * Returns the wait in ms, or -1 on timeout. Reading a byte register through the
 * 32-bit accessor would straddle neighbours, so use the byte view.
 */
static double wait_vblank(void)
{
	volatile uint8_t *b = (volatile uint8_t *)regs;
	double t0 = now_ms();

	/*
	 * 0xc0 ONLY, not the vendor's 0xc0 && 0xc4. dec_irq_query() requires
	 * bit 0 in both, but 0xc4 is the hardware interrupt ENABLE, which
	 * nothing in this tool sets -- the vendor's condition is "status set
	 * AND interrupt enabled", correct for a handler, wrong for a poller.
	 * 0xc0 bit 0 alone is MEASURED to be the vblank event: acked and
	 * re-polled it fires at 16.74 ms intervals (19 of 20 identical)
	 * against the panel's computed 16.75 ms period.
	 */
	while (now_ms() - t0 < 50.0) {
		if (b[AFBD_IRQ_ST0] & 1u) {
			b[AFBD_IRQ_ST0] = b[AFBD_IRQ_ST0] | 1u;   /* ack */
			return now_ms() - t0;
		}
	}
	return -1.0;
}

/*
 * BT.709 for >=720p, BT.601 below it. Integer math, limited range in.
 *
 * PERFORMANCE, learned the hard way (2026-08-09): the destination MUST NOT be
 * `volatile`. The first version wrote straight into the mmap'd framebuffer
 * through a volatile pointer, which forbids the compiler from vectorising or
 * merging stores -- one scalar store per pixel, 921600 times. That measured
 * 84 ms/frame, i.e. 11.95 fps on a 30 fps clip.
 *
 * Converting into an ordinary cached staging buffer lets the compiler
 * autovectorise, and a single bulk copy then moves it to the framebuffer at the
 * ~307 MB/s the `bar` fill demonstrates. Splitting rows across cores is nearly
 * free on top: three of the four A53s are idle during playback.
 */
struct conv_job {
	const uint8_t *y, *uv;
	uint32_t *out;
	int w, ystride, uvstride, bt709, row0, row1;
};

static void *conv_worker(void *arg)
{
	const struct conv_job *j = arg;
	const int kr = j->bt709 ? 459 : 409;    /* 1.793 / 1.596 in Q8 */
	const int kb = j->bt709 ? 541 : 516;    /* 2.115 / 2.017 */
	const int kgu = j->bt709 ? 55 : 100;
	const int kgv = j->bt709 ? 136 : 208;
	int x, row;

	for (row = j->row0; row < j->row1; row++) {
		const uint8_t *yr = j->y + (size_t)row * j->ystride;
		const uint8_t *cr = j->uv + (size_t)(row >> 1) * j->uvstride;
		uint32_t *o = j->out + (size_t)row * W;

		for (x = 0; x < j->w; x++) {
			int c = yr[x] - 16;
			int d = cr[(x & ~1)] - 128;
			int e = cr[(x & ~1) + 1] - 128;
			int r = (298 * c + kr * e + 128) >> 8;
			int g = (298 * c - kgu * d - kgv * e + 128) >> 8;
			int b = (298 * c + kb * d + 128) >> 8;

			r = r < 0 ? 0 : (r > 255 ? 255 : r);
			g = g < 0 ? 0 : (g > 255 ? 255 : g);
			b = b < 0 ? 0 : (b > 255 ? 255 : b);
			o[x] = 0xff000000u | (r << 16) | (g << 8) | b;
		}
	}
	return NULL;
}

/*
 * Tunable because the obvious value is not the best one. With 4 threads the
 * conversion saturates all four A53s and starves the decoder feeding our pipe:
 * a reader thread added on top moved 2 ms out of "read" and straight into
 * "convert" for no net gain (28.33 -> 28.14 fps). Leaving a core for GStreamer
 * may beat using every core for pixels. Set CONV_THREADS=n to sweep it.
 */
#define CONV_THREADS_MAX 4
static int conv_threads = CONV_THREADS_MAX;
/*
 * Bar step in px/frame, default 16. BAR_STEP=0 gives a MOVING-BAR-FREE
 * control that still does the identical per-frame work: same two-phase
 * fill, same buffer alternation, same vblank swap, same rate -- only the
 * motion is removed.
 *
 * This exists because the negative control used so far was a STATIC panel
 * with nothing running (0.74%), while every test run had a bar sweeping at
 * ~955 px/s. An LCD's pixel response smears a moving bar, and the metric
 * needs redness > 40 over a contiguous run, so motion alone can drop rows
 * below threshold. If BAR_STEP=0 also reads ~26%, the tearing figure is a
 * motion artefact and the presentation path is fine.
 */
static int bar_step = 16;

static void conv_threads_init(void)
{
	const char *e = getenv("CONV_THREADS");
	int v = e ? atoi(e) : 0;

	if (v >= 1 && v <= CONV_THREADS_MAX)
		conv_threads = v;
}

static void nv12_to_argb(const uint8_t *y, const uint8_t *uv, int w, int h,
			 int ystride, int uvstride, uint32_t *out, int bt709)
{
	pthread_t th[CONV_THREADS_MAX];
	struct conv_job jobs[CONV_THREADS_MAX];
	int started[CONV_THREADS_MAX];
	const int CONV_THREADS = conv_threads;
	int n, rows = h / CONV_THREADS;

	for (n = 0; n < CONV_THREADS; n++) {
		jobs[n] = (struct conv_job){
			.y = y, .uv = uv, .out = out, .w = w,
			.ystride = ystride, .uvstride = uvstride, .bt709 = bt709,
			.row0 = n * rows,
			.row1 = (n == CONV_THREADS - 1) ? h : (n + 1) * rows,
		};
		/*
		 * Splitting at any row is safe, even an odd one: every row
		 * derives its own chroma row as uv + (row >> 1) * uvstride, so
		 * the halves of a chroma pair never share mutable state.
		 */
		started[n] = (pthread_create(&th[n], NULL, conv_worker, &jobs[n]) == 0);
		if (!started[n])
			conv_worker(&jobs[n]);      /* degrade to inline */
	}
	for (n = 0; n < CONV_THREADS; n++)
		if (started[n])
			pthread_join(th[n], NULL);
}

/*
 * Frame reader, on its own thread.
 *
 * Reading was the single largest per-frame cost once the conversion was fixed
 * (14.8 ms of a ~35 ms frame) and it is pure waiting -- the decoder filling a
 * pipe. Overlapping it with convert/blit/commit hides nearly all of it. The VE
 * decodes this content at 268 fps, so the reader is never the limit; it just
 * has to run ahead.
 *
 * A short ring rather than a single handoff, so a hiccup in either stage does
 * not immediately stall the other.
 */
#define RING_SLOTS 3

struct reader {
	int fd;
	size_t fsz;
	uint8_t *slot[RING_SLOTS];
	int filled[RING_SLOTS];
	int head, tail;                 /* producer writes head, consumer takes tail */
	int eof, stop;
	pthread_mutex_t m;
	pthread_cond_t space, item;
};

static void *reader_thread(void *arg)
{
	struct reader *r = arg;

	for (;;) {
		size_t got = 0;
		int slot;

		pthread_mutex_lock(&r->m);
		while (r->filled[r->head] && !r->stop)
			pthread_cond_wait(&r->space, &r->m);
		if (r->stop) { pthread_mutex_unlock(&r->m); return NULL; }
		slot = r->head;
		pthread_mutex_unlock(&r->m);

		while (got < r->fsz) {
			ssize_t k = read(r->fd, r->slot[slot] + got, r->fsz - got);
			if (k <= 0)
				break;
			got += (size_t)k;
		}

		pthread_mutex_lock(&r->m);
		if (got != r->fsz) {
			r->eof = 1;
			pthread_cond_broadcast(&r->item);
			pthread_mutex_unlock(&r->m);
			return NULL;
		}
		r->filled[slot] = 1;
		r->head = (r->head + 1) % RING_SLOTS;
		pthread_cond_signal(&r->item);
		pthread_mutex_unlock(&r->m);
	}
}

/* Returns the next frame buffer, or NULL at end of stream. */
static uint8_t *reader_get(struct reader *r)
{
	uint8_t *p;

	pthread_mutex_lock(&r->m);
	while (!r->filled[r->tail] && !r->eof)
		pthread_cond_wait(&r->item, &r->m);
	if (!r->filled[r->tail]) { pthread_mutex_unlock(&r->m); return NULL; }
	p = r->slot[r->tail];
	pthread_mutex_unlock(&r->m);
	return p;
}

static void reader_release(struct reader *r)
{
	pthread_mutex_lock(&r->m);
	r->filled[r->tail] = 0;
	r->tail = (r->tail + 1) % RING_SLOTS;
	pthread_cond_signal(&r->space);
	pthread_mutex_unlock(&r->m);
}

/*
 * TWO PHASE, and it must stay that way: blue the whole surface, THEN draw the
 * bar. tools/display/tear-measure.py scores "rows with no bar at all", which
 * only exists as a signal because of this ordering -- a raster passing through
 * mid-fill finds a surface that has been blued but not yet barred.
 *
 * A single-pass fill (bar-or-blue per pixel, which this was originally) leaves
 * every row carrying a bar at either the old or the new position, so the metric
 * reads 0% whether or not the panel tears. That is a meaningless pass, not a
 * clean one.
 *
 * Rolling shutter can shift the bar but can never delete it, which is why this
 * metric is specific to single-buffered corruption and the step size is not.
 */
static void fill_bar(volatile uint32_t *fb, int x0)
{
	uint32_t *p = (uint32_t *)fb;           /* non-volatile: let it vectorise */
	int y, k;
	size_t i;

	for (i = 0; i < (size_t)W * H; i++)
		p[i] = 0xff0000ffu;                     /* phase 1: all blue */

	for (y = 0; y < H; y++) {
		uint32_t *row = p + (size_t)y * W;
		for (k = 0; k < 64; k++)                /* phase 2: the bar */
			row[(x0 + k) % W] = 0xffff0000u;
	}
}

/*
 * The DECD-half registers: format byte, plane strides, plane addresses. Names
 * from the vendor sunxi_decd driver (patch 0013), whose only format function,
 * dec_reg_video_channel_attr_config(), writes +0x10/+0x11/+0x13 -- and has no
 * caller anywhere in the port.
 *
 * KNOWN NOT TO REACH SCANOUT (test_54, 2026-08-14): the format byte at +0x11
 * accepts a value, retains it across the latch, and the fetch stays 4
 * bytes/pixel. The vendor's LogoRegData.bin DE blocks -- the thing that
 * actually configures the panel -- never write any register in this group.
 * The instruments below still program them because DECD does, and isolating
 * DECD's half from the scanout half is exactly what refuted the claim.
 */
#define AFBD_G_FLAGS    0x10
#define AFBD_G_FORMAT   0x11
#define AFBD_G_LINEAR   0x13
#define AFBD_G_STRIDE0  0x40
#define AFBD_G_STRIDE1  0x44
/*
 * The latch: dec_reg_set_dirty() writes workaround + 12 = afbd + 0x6c after
 * every config change. Without it the bytes at +0x10..+0x13 sit in a shadow
 * register (measured: a stride change took while the format did not).
 */

static volatile uint8_t *regs8;

/* Read a whole raw NV12 frame; returns a malloc'd buffer or NULL. */
static uint8_t *read_frame(const char *path, size_t fsz)
{
	uint8_t *buf = malloc(fsz);
	int fd = open(path, O_RDONLY);
	size_t got = 0;

	if (fd < 0 || !buf) {
		perror(path);
		free(buf);
		if (fd >= 0)
			close(fd);
		return NULL;
	}
	while (got < fsz) {
		ssize_t r = read(fd, buf + got, fsz - got);

		if (r <= 0)
			break;
		got += (size_t)r;
	}
	close(fd);
	if (got != fsz) {
		fprintf(stderr, "%s: short frame, %zu of %zu\n", path, got, fsz);
		free(buf);
		return NULL;
	}
	return buf;
}

/* Latch the shadow config, commit, report. Returns the commit wait in us. */
static double latch_commit(const char *what)
{
	double us;

	wr(regs, AFBD_DIRTY, 1);
	us = commit();
	printf("%s: commit %s %.0f us\n", what,
	       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);
	return us;
}

/*
 * dump_channel -- the video-channel half of the block, which the one-line `regs`
 * dump does not cover.
 *
 * It exists because sunxi-decd and this tool program DIFFERENT halves of the
 * same registers. The driver writes the plane addresses (0x70/0x84, via its
 * regs->workaround = afbd + 0x60) and the dirty latch, and nothing else: its
 * only format-programming function, dec_reg_video_channel_attr_config(), has no
 * caller anywhere in the port, and it handles only the two 10-bit modes even if
 * one were added. So after a DECD FRAME_SUBMIT the plane registers should carry
 * the submitted addresses while the format byte still carries whatever U-Boot's
 * logo left behind. Printing both halves is what tells those two apart, and it
 * settles by readout what would otherwise be a question about what the panel
 * looked like.
 */
static void dump_channel(void)
{
	static const unsigned y_off[] = { 0x70, 0x74, 0x78, 0x7c };
	static const unsigned c_off[] = { 0x84, 0x88, 0x8c, 0x90 };
	unsigned i;

	printf("AFBD cfg   flags=%08x fmt=%u linear=%02x stride0=%08x stride1=%08x\n",
	       rd(regs, AFBD_G_FLAGS), regs8[AFBD_G_FORMAT], regs8[AFBD_G_LINEAR],
	       rd(regs, AFBD_G_STRIDE0), rd(regs, AFBD_G_STRIDE1));
	printf("AFBD ch    enable=%02x mux=%02x dirty=%08x irq=%08x/%08x\n",
	       regs8[0x60], regs8[0x68], rd(regs, AFBD_DIRTY),
	       rd(regs, AFBD_IRQ_ST0), rd(regs, AFBD_IRQ_ST1));
	for (i = 0; i < 4; i++)
		printf("AFBD plane%u Y=%08x C=%08x info=%08x\n", i,
		       rd(regs, y_off[i]), rd(regs, c_off[i]),
		       rd(regs, 0x98 + 4 * i));
}

/*
 * fmt -- program ONLY the format and strides, then latch and commit.
 *
 * The isolating control for the DECD test: sunxi-decd supplies the plane
 * addresses via FRAME_SUBMIT and this supplies the format the driver never
 * programs, touching nothing else. Outcome so far (test_54): the combination
 * does NOT change the fetch -- see the group comment above.
 *
 * dwell 0 means set and exit WITHOUT restoring, for leaving the state in place
 * while something else runs. Any other dwell restores, so a wrong code cannot
 * outlive the run that tried it.
 */
static int fmt_bridge(unsigned code, unsigned stride, unsigned dwell_ms)
{
	uint32_t s_10, s_s0, s_s1, s_str;
	char what[64];
	double us;

	s_10 = rd(regs, AFBD_G_FLAGS);          /* covers bytes 0x10..0x13 */
	s_s0 = rd(regs, AFBD_G_STRIDE0);
	s_s1 = rd(regs, AFBD_G_STRIDE1);
	s_str = rd(regs, AFBD_STRIDE);
	printf("saved: 0x10=%08x s0=%08x s1=%08x stride=%08x\n",
	       s_10, s_s0, s_s1, s_str);

	regs8[AFBD_G_FORMAT] = (uint8_t)code;
	wr(regs, AFBD_G_STRIDE0, stride);
	wr(regs, AFBD_G_STRIDE1, stride);
	wr(regs, AFBD_STRIDE, stride);
	snprintf(what, sizeof(what), "fmt %u stride %u", code, stride);
	us = latch_commit(what);
	dump_channel();

	if (!dwell_ms) {
		printf("left in place (dwell 0) -- a reboot restores\n");
		return us < 0 ? 1 : 0;
	}

	printf("holding %u ms -- look at the panel\n", dwell_ms);
	usleep(dwell_ms * 1000);

	wr(regs, AFBD_G_STRIDE0, s_s0);
	wr(regs, AFBD_G_STRIDE1, s_s1);
	wr(regs, AFBD_STRIDE, s_str);
	wr(regs, AFBD_G_FLAGS, s_10);
	latch_commit("restore");
	return us < 0 ? 1 : 0;
}

/*
 * info -- rewrite the four per-slot video-info-page addresses, latch, commit.
 *
 * sunxi-decd's linear path sets the info address to y_phys + 4096
 * (video_info_buffer_init()), which lands 4 KB INSIDE the luma plane -- the
 * "info page" is pixel data. Confirmed on hardware: info=6c101000 with
 * Y=6c100000. `info 0` undoes that while testing DECD. Probed as the blocker
 * on 2026-08-14 (test_54/IMG_0695): it is not -- zeroing changed nothing.
 * Offsets are dec_reg_set_address()'s info table, workaround + {56,60,64,68}.
 */
static int info_probe(uint32_t val, unsigned dwell_ms)
{
	static const unsigned off[] = { 0x98, 0x9c, 0xa0, 0xa4 };
	uint32_t save[4];
	char what[32];
	unsigned i;
	double us;

	for (i = 0; i < 4; i++)
		save[i] = rd(regs, off[i]);
	printf("saved info: %08x %08x %08x %08x\n",
	       save[0], save[1], save[2], save[3]);

	for (i = 0; i < 4; i++)
		wr(regs, off[i], val);
	snprintf(what, sizeof(what), "info <- %08x", val);
	us = latch_commit(what);
	dump_channel();

	if (!dwell_ms)
		return us < 0 ? 1 : 0;

	printf("holding %u ms -- look at the panel\n", dwell_ms);
	usleep(dwell_ms * 1000);
	for (i = 0; i < 4; i++)
		wr(regs, off[i], save[i]);
	latch_commit("restore");
	return us < 0 ? 1 : 0;
}

/*
 * load -- copy a raw NV12 frame into the scanout buffer and exit, touching no
 * registers at all.
 *
 * The sweep for the real format field needs the pixels in place while the
 * registers stay exactly as the vendor's DE-block replay left them, so that a
 * following `poke` changes ONE field against an otherwise untouched vendor
 * configuration. Neither yuv2 nor fmt can do that: both program format, strides
 * and (for yuv2) plane addresses as a package, which is three variables at once
 * and is how this file talked itself into a false positive before.
 *
 * With the vendor's stride of 5120 still in place a 1280x720 NV12 frame covers
 * the top 270 rows as ARGB garbage -- the test_53 picture. That is the expected
 * starting point, not a fault.
 */
static int load_raw_frame(const char *path)
{
	size_t fsz = (size_t)W * H * 3 / 2;
	uint8_t *buf = read_frame(path, fsz);

	if (!buf)
		return 1;
	memcpy((void *)fb_front, buf, fsz);
	__sync_synchronize();
	free(buf);
	printf("loaded %s: %zu bytes -> %#lx, registers untouched\n",
	       path, fsz, FB_FRONT);
	dump_channel();
	return 0;
}

/*
 * poke -- one 32-bit write into the AFBD window, latched and committed.
 *
 * For bisecting the rest of what DECD writes and userspace does not (the aux
 * bytes at +0x80/+0x94, the field bytes at +0xa8). Restores unless dwell is 0.
 */
static int poke(unsigned off, uint32_t val, unsigned dwell_ms)
{
	uint32_t save;
	char what[48];
	double us;

	if (off > 0xffc || (off & 3)) {
		fprintf(stderr, "offset must be 32-bit aligned and < 0x1000\n");
		return 2;
	}
	save = rd(regs, off);
	wr(regs, off, val);
	snprintf(what, sizeof(what), "poke +%#05x: %08x -> %08x", off, save, val);
	us = latch_commit(what);
	dump_channel();

	if (!dwell_ms)
		return us < 0 ? 1 : 0;

	printf("holding %u ms -- look at the panel\n", dwell_ms);
	usleep(dwell_ms * 1000);
	wr(regs, off, save);
	latch_commit("restore");
	return us < 0 ? 1 : 0;
}

static void usage(void)
{
	fprintf(stderr,
		"usage: h713-present <mode> [args]\n"
		"  regs                 dump the AFBD registers (safe once display is up)\n"
		"  fill <0xAARRGGBB>    solid fill of the front buffer, then commit\n"
		"  bar [frames]         moving red bar on blue, double-buffered (default 600)\n"
		"  bar-sb [frames]      same bar, SINGLE-buffered -- the tearing positive control\n"
		"  bar-vs [frames]      same bar, flip inside vblank -- the M3 candidate\n"
		"  nv12 <file> [frames] present NV12 frames from a raw file (the working path)\n"
		"  load <file.nv12>     copy a frame into the scanout buffer, touch NO\n"
		"                       registers -- the base state for a poke sweep\n"
		"  poke <off> <val> [ms]  one 32-bit write into the AFBD window + commit;\n"
		"                       ms=0 leaves it set, otherwise restores\n"
		"  fmt <code> [stride] [ms]  set format byte + strides only (the DECD half;\n"
		"                       known NOT to reach scanout -- see test_54)\n"
		"  info <val> [ms]      rewrite the 4 video-info-page addresses\n"
		"  yuv2 <f.nv12> <code> <idx> [ms]  the refuted direct-YUV control (test_54)\n"
		"\nThe display must already be up (h713_disp in U-Boot). This refuses to\n"
		"touch the display blocks otherwise -- reading them gated hangs the board.\n");
}

int main(int argc, char **argv)
{
	int fd;
	uint32_t gate;

	if (argc < 2) { usage(); return 2; }

	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) { perror("open /dev/mem"); return 1; }

	ccu = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED, fd, CCU_AFBD_CLK & ~0xfffUL);
	if (ccu == MAP_FAILED) { perror("mmap ccu"); return 1; }

	gate = ccu[(CCU_AFBD_CLK & 0xfff) / 4];
	if (!(gate & (1u << 31))) {
		fprintf(stderr,
			"refusing: AFBD clock gate is closed (0x%08x at 0x%08lx).\n"
			"The display is not up. Run 'h713_disp auto 0x34 logo' (or a\n"
			"panel-test) in U-Boot before booting, then retry.\n",
			gate, CCU_AFBD_CLK);
		return 1;
	}

	regs = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, AFBD_BASE);
	if (regs == MAP_FAILED) { perror("mmap afbd"); return 1; }

	fb_front = mmap(NULL, FB_WINDOW, PROT_READ | PROT_WRITE, MAP_SHARED, fd, FB_FRONT);
	if (fb_front == MAP_FAILED) {
		perror("mmap scanout");
		fprintf(stderr, "If this is EPERM, CONFIG_STRICT_DEVMEM rejected the\n"
				"range -- check /proc/iomem shows uboot-scanout as a\n"
				"TOP-LEVEL entry, not a child of System RAM.\n");
		return 1;
	}
	fb_back = fb_front + (FB_BACK - FB_FRONT) / 4;

	printf("AFBD ctrl=%08x ready=%08x status=%08x stride=%08x src=%08x\n",
	       rd(regs, AFBD_CTRL), rd(regs, AFBD_READY), rd(regs, AFBD_STATUS),
	       rd(regs, AFBD_STRIDE), rd(regs, AFBD_SRC));

	regs8 = (volatile uint8_t *)regs;
	conv_threads_init();
	if (getenv("BAR_STEP"))
		bar_step = atoi(getenv("BAR_STEP"));

	if (!strcmp(argv[1], "regs")) {
		dump_channel();
		return 0;
	}

	if (!strcmp(argv[1], "fmt") && argc >= 3)
		return fmt_bridge(strtoul(argv[2], NULL, 0),
				  argc >= 4 ? strtoul(argv[3], NULL, 0) : W,
				  argc >= 5 ? strtoul(argv[4], NULL, 0) : 8000);

	if (!strcmp(argv[1], "load") && argc >= 3)
		return load_raw_frame(argv[2]);

	if (!strcmp(argv[1], "info") && argc >= 3)
		return info_probe(strtoul(argv[2], NULL, 0),
				  argc >= 4 ? strtoul(argv[3], NULL, 0) : 0);

	if (!strcmp(argv[1], "poke") && argc >= 4)
		return poke(strtoul(argv[2], NULL, 0), strtoul(argv[3], NULL, 0),
			    argc >= 5 ? strtoul(argv[4], NULL, 0) : 0);

	if (!strcmp(argv[1], "fill") && argc >= 3) {
		uint32_t v = strtoul(argv[2], NULL, 0);
		double t0 = now_ms(), t1, us;
		size_t i;

		for (i = 0; i < FB_BYTES / 4; i++)
			fb_front[i] = v;
		t1 = now_ms();
		flip_to(FB_FRONT);
		us = commit();
		printf("fill %08x: %.1f ms (%.1f MB/s), commit %s %.0f us\n",
		       v, t1 - t0, FB_BYTES / 1024.0 / 1024.0 / ((t1 - t0) / 1000.0),
		       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);
		return us < 0 ? 1 : 0;
	}

	/*
	 * yuv2 -- CONTROL A of the 2026-08-14 refutation, kept to reproduce it.
	 *
	 * Programs the DECD half in full: format byte, plane strides, and the
	 * per-slot Y/C plane addresses (workaround + {16,36}[idx], i.e.
	 * 0x70/0x84 for idx 0) the way dec_sync_frame_to_hardware() does.
	 * Refuted as a scanout path: run cold, it produces the 4x-repeat
	 * greyscale (test_54/IMG_0691), because none of these registers are in
	 * the fetch path the vendor's DE table configures. It was once believed
	 * to put NV12 on the panel; that claim rested on a misattributed photo.
	 *
	 * usage: yuv2 <file.nv12> <format-code> <idx> [dwell-ms]
	 */
	if (!strcmp(argv[1], "yuv2") && argc >= 5) {
		unsigned code = strtoul(argv[3], NULL, 0);
		unsigned idx = strtoul(argv[4], NULL, 0);
		unsigned dwell = argc >= 6 ? strtoul(argv[5], NULL, 0) : 8000;
		static const unsigned y_off[] = { 0x70, 0x74, 0x78, 0x7c };
		static const unsigned c_off[] = { 0x84, 0x88, 0x8c, 0x90 };
		size_t fsz = (size_t)W * H * 3 / 2;
		uint32_t s_flags, s_str, s_src, s_s0, s_s1, s_y, s_c;
		unsigned long y_phys = FB_FRONT, c_phys = FB_FRONT + (unsigned long)W * H;
		uint8_t *buf;
		double us;

		if (idx > 3) { fprintf(stderr, "idx must be 0..3\n"); return 2; }
		buf = read_frame(argv[2], fsz);
		if (!buf)
			return 1;

		s_flags = rd(regs, AFBD_G_FLAGS);
		s_str = rd(regs, AFBD_STRIDE);
		s_src = rd(regs, AFBD_SRC);
		s_s0 = rd(regs, AFBD_G_STRIDE0);
		s_s1 = rd(regs, AFBD_G_STRIDE1);
		s_y = rd(regs, y_off[idx]);
		s_c = rd(regs, c_off[idx]);
		printf("saved: flags=%08x stride=%08x src=%08x s0=%08x s1=%08x "
		       "Y[%u]=%08x C[%u]=%08x\n",
		       s_flags, s_str, s_src, s_s0, s_s1, idx, s_y, idx, s_c);

		/* NV12 laid out contiguously: Y plane, then interleaved chroma. */
		memcpy((void *)fb_front, buf, fsz);
		__sync_synchronize();

		regs8[AFBD_G_FORMAT] = (uint8_t)code;
		wr(regs, AFBD_G_STRIDE0, W);
		wr(regs, AFBD_G_STRIDE1, W);
		wr(regs, AFBD_STRIDE, W);
		wr(regs, y_off[idx], (uint32_t)y_phys);   /* the vendor's Y plane */
		wr(regs, c_off[idx], (uint32_t)c_phys);   /* the vendor's C plane */
		wr(regs, AFBD_DIRTY, 1);
		us = commit();
		printf("code %u idx %u: Y=%08x C=%08x flags=%08x commit %s %.0f us\n",
		       code, idx, rd(regs, y_off[idx]), rd(regs, c_off[idx]),
		       rd(regs, AFBD_G_FLAGS), us < 0 ? "TIMEOUT" : "ok",
		       us < 0 ? 0 : us);

		usleep(dwell * 1000);

		wr(regs, y_off[idx], s_y);
		wr(regs, c_off[idx], s_c);
		wr(regs, AFBD_G_FLAGS, s_flags);
		wr(regs, AFBD_G_STRIDE0, s_s0);
		wr(regs, AFBD_G_STRIDE1, s_s1);
		wr(regs, AFBD_STRIDE, s_str);
		wr(regs, AFBD_SRC, s_src);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		printf("restored\n");
		free(buf);
		return 0;
	}

	/*
	 * bar-vs: the vendor's swap order -- wait for the real vblank, THEN
	 * write the address, THEN latch. This is M3's candidate presentation
	 * loop, kept alongside plain `bar` (which flips whenever the fill
	 * happens to finish) so the two orders can be scored against each
	 * other with tools/display/tear-measure.py.
	 */
	if (!strcmp(argv[1], "bar-vs")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0, vmiss = 0;
		double fill_tot = 0, vb_tot = 0, t0 = now_ms();

		for (n = 0; n < frames; n++) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a = now_ms(), b, vb, us;

			fill_bar(target, (n * bar_step) % W);
			b = now_ms();

			vb = wait_vblank();
			if (vb < 0) vmiss++;
			flip_to(phys);
			wr(regs, AFBD_DIRTY, 1);        /* latch, as the vendor does */
			us = commit();
			if (us < 0) timeouts++;
			fill_tot += b - a;
			vb_tot += vb < 0 ? 0 : vb;
		}
		fill_bar(fb_front, ((frames - 1) * bar_step) % W);
		flip_to(FB_FRONT);
		wr(regs, AFBD_DIRTY, 1);
		commit();

		printf("bar-vs: %d frames in %.0f ms (%.2f fps), %d timeouts, "
		       "%d vblank misses\n"
		       "        fill mean %.2f ms, vblank wait mean %.2f ms\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts, vmiss, fill_tot / frames, vb_tot / frames);
		return timeouts ? 1 : 0;
	}

	/*
	 * bar-sb is the POSITIVE CONTROL for the tearing measurement: it
	 * writes into the buffer the hardware is scanning, so the raster can
	 * catch the surface blued-but-not-yet-barred. Without a run the metric
	 * is known to flag, a 0% double-buffered result cannot be told apart
	 * from a metric that does not work. Expected magnitude is printed with
	 * the results: about (phase-1 fill time / frame period).
	 */
	if (!strcmp(argv[1], "bar-sb")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0;
		double fill_tot = 0, wait_tot = 0, t0 = now_ms();

		flip_to(FB_FRONT);
		for (n = 0; n < frames; n++) {
			double a = now_ms(), b, us;

			fill_bar(fb_front, (n * bar_step) % W);   /* the live surface */
			b = now_ms();
			us = commit();
			if (us < 0) timeouts++;
			fill_tot += b - a;
			wait_tot += us < 0 ? 0 : us / 1000.0;
		}
		printf("bar-sb: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
		       "        fill mean %.2f ms, commit wait mean %.2f ms\n"
		       "        predicted rows-with-no-bar ~%.1f%% "
		       "(fill / 16.75 ms frame)\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts, fill_tot / frames, wait_tot / frames,
		       100.0 * (fill_tot / frames) / 16.75);
		return timeouts ? 1 : 0;
	}

	if (!strcmp(argv[1], "bar")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0;
		double fill_tot = 0, wait_tot = 0, t0 = now_ms();

		for (n = 0; n < frames; n++) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a = now_ms(), b, us;

			fill_bar(target, (n * bar_step) % W);
			b = now_ms();
			flip_to(phys);
			us = commit();
			if (us < 0) { timeouts++; if (timeouts == 1)
				printf("first commit timeout at frame %d\n", n); }
			fill_tot += b - a;
			wait_tot += us < 0 ? 0 : us / 1000.0;
		}
		/*
		 * Always finish on the front buffer: every other consumer of this
		 * path writes 0x6c100000 and none of them touch the source
		 * register, so leaving the hardware reading the back buffer would
		 * silently break whatever runs next.
		 */
		fill_bar(fb_front, ((frames - 1) * bar_step) % W);
		flip_to(FB_FRONT);
		commit();

		printf("bar: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
		       "     fill mean %.2f ms, commit wait mean %.2f ms\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts, fill_tot / frames, wait_tot / frames);
		return timeouts ? 1 : 0;
	}

	if (!strcmp(argv[1], "nv12") && argc >= 3) {
		int frames = argc >= 4 ? atoi(argv[3]) : 1 << 30;
		size_t fsz = (size_t)W * H * 3 / 2;
		uint32_t *stage = aligned_alloc(64, FB_BYTES);
		int vfd = open(argv[2], O_RDONLY);
		int n = 0, timeouts = 0, i;
		double read_tot = 0, conv_tot = 0, blit_tot = 0, wait_tot = 0;
		double t0;
		struct reader rd_ctx = { 0 };
		pthread_t rd_th;

		if (vfd < 0 || !stage) { perror("nv12 setup"); return 1; }
		/*
		 * Raw read() in frame-sized gulps, NOT stdio. fread() on a FILE*
		 * uses a 4 KB buffer, so a 1.38 MB frame became ~337 blocking
		 * reads that ping-pong with the writer -- measured at 31.7 ms
		 * per frame, which dwarfed decode (268 fps) and conversion
		 * (11 ms) combined. Enlarging the pipe cuts the round trips
		 * further; failure is harmless, so it is not checked.
		 */
		/*
		 * Verify, do not assume. F_SETPIPE_SZ is capped by
		 * /proc/sys/fs/pipe-max-size (1 MB by default) and silently
		 * clamps; a 64 KB pipe needs ~22 fill/drain round trips per
		 * 1.38 MB frame, each waiting on the writer to be scheduled,
		 * which is the right order to explain a 12-15 ms "read" that
		 * should take 2-3 ms.
		 */
		if (fcntl(vfd, F_SETPIPE_SZ, 4 << 20) < 0)
			fcntl(vfd, F_SETPIPE_SZ, 1 << 20);
		{
			int got = fcntl(vfd, F_GETPIPE_SZ);
			if (got > 0)
				printf("pipe size: %d bytes (%.2f frames)\n",
				       got, got / (double)fsz);
			else
				printf("pipe size: not a pipe (regular file)\n");
		}

		rd_ctx.fd = vfd;
		rd_ctx.fsz = fsz;
		for (i = 0; i < RING_SLOTS; i++) {
			rd_ctx.slot[i] = malloc(fsz);
			if (!rd_ctx.slot[i]) { perror("ring"); return 1; }
		}
		pthread_mutex_init(&rd_ctx.m, NULL);
		pthread_cond_init(&rd_ctx.space, NULL);
		pthread_cond_init(&rd_ctx.item, NULL);
		if (pthread_create(&rd_th, NULL, reader_thread, &rd_ctx)) {
			perror("reader thread");
			return 1;
		}

		t0 = now_ms();
		while (n < frames) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a, b, c, d, us;
			uint8_t *buf;

			a = now_ms();
			buf = reader_get(&rd_ctx);
			if (!buf)
				break;
			b = now_ms();
			nv12_to_argb(buf, buf + (size_t)W * H, W, H, W, W, stage, 1);
			c = now_ms();
			/* buf is consumed once converted -- hand the slot back
			 * before the blit so the reader can run further ahead. */
			reader_release(&rd_ctx);
			/*
			 * One bulk copy rather than per-pixel volatile stores.
			 * The cast is deliberate: the framebuffer is only
			 * volatile to stop the compiler caching the register
			 * window, and memcpy to it is exactly what we want.
			 */
			memcpy((void *)target, stage, FB_BYTES);
			d = now_ms();
			flip_to(phys);
			us = commit();
			if (us < 0) timeouts++;

			read_tot += b - a; conv_tot += c - b;
			blit_tot += d - c; wait_tot += us < 0 ? 0 : us / 1000.0;
			n++;
		}
		pthread_mutex_lock(&rd_ctx.m);
		rd_ctx.stop = 1;
		pthread_cond_broadcast(&rd_ctx.space);
		pthread_mutex_unlock(&rd_ctx.m);
		pthread_join(rd_th, NULL);
		close(vfd);
		flip_to(FB_FRONT);
		if (n)
			printf("nv12: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
			       "      mean read %.2f  convert %.2f  blit %.2f  "
			       "commit-wait %.2f ms\n",
			       n, now_ms() - t0, n / ((now_ms() - t0) / 1000.0),
			       timeouts, read_tot / n, conv_tot / n,
			       blit_tot / n, wait_tot / n);
		return n ? 0 : 1;
	}

	usage();
	return 2;
}
