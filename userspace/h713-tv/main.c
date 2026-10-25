// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE		/* accept4 */
/*
 * h713-tv -- show the HDMI input on the projector, and hand the panel back
 * to the console when the signal goes away.
 *
 * Two devices, two jobs:
 *
 *   /dev/videoN (sun50i-h713-hdmirx, patch 0094) is asked *whether* there is
 *      a signal, and it says when that changes. The MIPS firmware fires its
 *      SignalChange callback by itself both on loss and on return (measured,
 *      doku/nachtlog/K4-hotplug.md) and the driver turns that into
 *      V4L2_EVENT_SOURCE_CHANGE. So this program sits in poll() and never
 *      sleeps on a hunch. The one timer it has asks again, a bounded number
 *      of times, while the driver reports a change in flight (-ENOLCK, see
 *      struct retry); nothing else is decided by time.
 *
 *      N is *not* 0 on this board: /dev/video0 is cedrus, the capture came up
 *      as /dev/video1 (measured 07.09.2026). Nothing here counts device
 *      numbers -- the device is found by its name, the same string the udev
 *      rule matches, and confirmed with VIDIOC_QUERYCAP.
 *
 *   /dev/dri/cardN (sun50i-h713-afbd, patch 0093) shows the picture. Its
 *      overlay plane "video-0" in "hdmi-ring" mode sources the capture ring
 *      itself and follows the firmware's flip pointers in its vsync handler.
 *      The frames are never touched here, let alone copied.
 *
 *      N is not 0 here either: card0 is Panfrost, the display is card1
 *      (measured; doku/nachtlog/H-abnahme-board.md, D-abnahme-board.md). On
 *      our board this is connector 33, CRTC 36, plane 38 -- none of those
 *      numbers is wired in, they are what the search below is expected to
 *      find.
 *
 * NV16 and NV16M are two different statements about the same pixels and both
 * are correct: the capture device offers V4L2_PIX_FMT_NV16M, two *separate*
 * planes of 2073600 bytes, because Y and C sit 0x5FD000 apart in the ring.
 * The KMS framebuffer here is DRM_FORMAT_NV16, which is a two-plane fourcc in
 * one buffer object -- and in "hdmi-ring" mode it carries nothing but format,
 * geometry and stride anyway. There is no conversion and no contradiction.
 *
 * Why the frames do not travel through this program at all: the capture
 * driver hands out the three ring slots as V4L2 buffers, but it has no
 * VIDIOC_EXPBUF yet (doku/88 section 4), so there is no dma-buf to import
 * into KMS. Pushing the pixels to the plane through a memcpy would be
 * 250 MB/s of pointless work, and the plane can read the ring by itself.
 * Once the export lands, the per-frame "DQBUF -> plane flip" of doku/78
 * appendix A.4 becomes a second mode in display_show(); nothing else about
 * the state machine changes. That mode will have to skip the first one or
 * two dequeued buffers, which are measurably empty -- they are queued before
 * the first flip fills them (frames 0 and 1 all zero, measured 07.09.2026).
 * This program never dequeues, so the effect cannot reach it here.
 *
 * Picture and console are mutually exclusive in hardware -- the mux behind
 * AFBD source 0 lets either the video path or the RGB path reach the encoder
 * (doku/86 section 1) -- so "plane off" is literally "console on". The plane
 * driver restores the RGB channel and the encoder selector when it is
 * disabled; this program additionally drops DRM master in standby, because a
 * held master stops the kernel's own console client from painting.
 *
 *      +------------ SOURCE_CHANGE, no signal -------------+
 *      v                                                   |
 *   STANDBY: plane off, master dropped              PICTURE: plane on,
 *   (console owns the panel)                        master held
 *      |                                                   ^
 *      +------------ SOURCE_CHANGE, signal there ----------+
 *
 * The sound follows the same rule through the same door: while a picture
 * stands and the source says it is sending PCM, the MSP audio DSP and the
 * codec are switched into the speaker path (ALSA cards "hy310hdmi" and
 * "H713 Audio Codec", plan doku/101); everything else is mute. That part is
 * optional -- without the cards it switches itself off, says so once, and
 * the picture never notices. See "The sound: the audio path follows the
 * picture" below.
 *
 * SIGTERM and SIGINT leave through the same door as a signal loss, so a
 * "systemctl stop" never leaves a frozen frame standing on the wall -- nor a
 * tone standing in the room.
 *
 * The picture values -- the nine sliders and the gamma curve -- come in three
 * layers, each with a known origin, applied in this order (plan 113 A.2):
 *
 *   1. the vendor's own data, computed at start from /etc/h713/tvconfig by
 *      h713-pq, for the chosen preset;
 *   2. which preset that is, from /etc/h713/tv.conf;
 *   3. the single sliders the user has moved and kept, from
 *      /var/lib/h713-tv/werte, laid on top.
 *
 * A missing layer falls through to the one below it, and a device without the
 * extraction still shows a picture: the table compiled in below is the last
 * fallback, not the first source. h713-pq is run once, as a child, with a
 * two second deadline; it is not a service, not a library and not a
 * dependency the picture path may fail on. Everything about that is in
 * "The picture values" further down.
 */
#include <ctype.h>
#include <errno.h>
#include <sys/sysmacros.h>
#include <dirent.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>

#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/signalfd.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/timerfd.h>
#include <sys/un.h>
#include <sys/wait.h>

#include <linux/kd.h>
#include <linux/tiocl.h>
#include <linux/videodev2.h>

#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>

#include <alloca.h>		/* the snd_*_alloca() macros of libasound */
#include <alsa/asoundlib.h>

#include "color.h"
#include "gamma.h"

#define DRM_DRIVER	"sun50i-h713-afbd"	/* patch 0093 */
#define V4L2_DRIVER	"sun50i-h713-hdmirx"	/* patch 0094 */

/* the smallest window the driver publishes, one AFBD block (0133f) */
#define WINDOW_MIN	16u

/*
 * The payload of the plane properties "src-window" and "dst-window" (kernel
 * 0133f): one window in panel pixels, as the driver's struct h713_window.
 * w = 0 means "do not send this one", which is the firmware's own default.
 */
struct window {
	uint32_t x, y, w, h;
};

/* The three zooms; what each one sends is in display_zoom_apply(). */
enum zoom_mode { ZOOM_OFF, ZOOM_IN, ZOOM_OUT };


/* ------------------------------------------------------------------ *
 * Talking to the journal
 * ------------------------------------------------------------------ */

__attribute__((format(printf, 1, 2)))
void info(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	putchar('\n');
	fflush(stdout);
}

__attribute__((format(printf, 1, 2)))
void warn(const char *fmt, ...)
{
	va_list ap;

	fputs("warning: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
}

/* Every fail() ends the process; saying so keeps the analyzer honest. */
__attribute__((format(printf, 1, 2)))
_Noreturn static void fail(const char *fmt, ...)
{
	va_list ap;

	fputs("error: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	exit(1);
}

/* ------------------------------------------------------------------ *
 * The capture device: is there a signal, and when does that change?
 * ------------------------------------------------------------------ */

struct capture {
	int fd;
	char path[32];
	int last_sig;			/* last capture_signal() result seen by evaluate() */
	struct v4l2_dv_timings last_t;	/* the last timing measured (sig == 1), kept across a change in flight */
};

/*
 * The device name as the kernel publishes it in sysfs. This is
 * video_device.name from patch 0094, i.e. the very string the udev rule
 * matches on -- so the program and the rule agree by construction.
 */
static bool capture_name_matches(unsigned int n)
{
	char path[64], name[64];
	ssize_t len;
	int fd;

	snprintf(path, sizeof(path), "/sys/class/video4linux/video%u/name", n);
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return false;
	len = read(fd, name, sizeof(name) - 1);
	close(fd);
	if (len <= 0)
		return false;
	name[len] = '\0';
	while (len > 0 && (name[len - 1] == '\n' || name[len - 1] == ' '))
		name[--len] = '\0';

	return !strcmp(name, V4L2_DRIVER);
}

/*
 * Find the device by name instead of by number. Two reasons, both measured:
 * the hdmirx driver probes asynchronously (its EDID sequence takes over ten
 * seconds), and /dev/video0 belongs to cedrus -- the capture came up as
 * /dev/video1. Unrelated device nodes are not even opened: sysfs answers the
 * question first, QUERYCAP then confirms it on the node that was opened.
 */
static void capture_open(struct capture *cap, const char *want_path)
{
	struct v4l2_capability vcap;
	unsigned int i, tries;

	for (i = 0; i < 64; i++) {
		if (want_path)
			snprintf(cap->path, sizeof(cap->path), "%s", want_path);
		else if (capture_name_matches(i))
			snprintf(cap->path, sizeof(cap->path),
				 "/dev/video%u", i);
		else
			continue;

		/*
		 * The first open of the boot registers the firmware callbacks
		 * (0100); a second opener meeting that moment gets EBUSY for a
		 * short while. Wait it out rather than giving up (S12 A6).
		 */
		for (tries = 0; ; tries++) {
			cap->fd = open(cap->path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
			if (cap->fd >= 0 || errno != EBUSY || tries >= 20)
				break;
			usleep(100000);
		}
		if (cap->fd < 0) {
			if (want_path)
				fail("%s cannot be opened: %s",
				     cap->path, strerror(errno));
			continue;
		}
		memset(&vcap, 0, sizeof(vcap));
		/*
		 * Compare only as far as the ABI can carry. v4l2_capability
		 * has __u8 driver[16], so the kernel reports at most 15
		 * characters plus the terminator -- "sun50i-h713-hdm" for our
		 * 18-character name. A strcmp() against the full string can
		 * therefore never match, on any board: it is a test that
		 * cannot succeed, which is as useless as one that cannot fail.
		 * The full name is what /sys/class/video4linux/videoN/name
		 * carries and what selected this node a few lines up; QUERYCAP
		 * only confirms that the node we opened is still that driver.
		 * Measured 07.09.2026: hdmirx_test printed the same truncation
		 * ("Treiber: sun50i-h713-hdm").
		 */
		if (!ioctl(cap->fd, VIDIOC_QUERYCAP, &vcap) &&
		    !strncmp((const char *)vcap.driver, V4L2_DRIVER,
			     sizeof(vcap.driver) - 1)) {
			info("capture         %s (%s, %s)", cap->path, vcap.driver,
			     vcap.card);
			return;
		}
		close(cap->fd);
		cap->fd = -1;
		if (want_path)
			fail("%s does not belong to \"%.*s\" but to \"%s\"",
			     cap->path, (int)sizeof(vcap.driver) - 1,
			     V4L2_DRIVER, vcap.driver);
	}
	fail("no V4L2 device with the name \"%s\" -- is the kernel running patch 0094, and is the probe through? (dmesg | grep hdmirx; grep -H . /sys/class/video4linux/video*/name)",
	     V4L2_DRIVER);
}

/*
 * Stage 5 of appendix A: tell the firmware which source is active. It is a
 * repeat of SetSource(3) when HDMI-1 is already the active source, which is
 * normal and not an error (doku/76 section 2.2), and it is a statement of
 * intent, not the trigger of the picture chain -- so a refusal is worth a
 * line in the journal but is not a reason to give up.
 *
 * It is explicitly *not* the "source change" that re-arms a capture the
 * descriptor switched off: that one is SetSource away and back
 * (doku/nachtlog/B2-quellenwechsel.md, 3 -> 1 -> 3). A repeated SetSource(3)
 * has never been measured to do anything, and guessing that it might is the
 * kind of hopeful call this program does not make.
 */
static void capture_select_input(struct capture *cap)
{
	unsigned int input = 0;

	if (ioctl(cap->fd, VIDIOC_S_INPUT, &input))
		warn("S_INPUT(0) refused: %s -- the firmware stays on the source it has",
		     strerror(errno));
}

static void capture_subscribe(struct capture *cap)
{
	struct v4l2_event_subscription sub;

	memset(&sub, 0, sizeof(sub));
	sub.type = V4L2_EVENT_SOURCE_CHANGE;
	if (ioctl(cap->fd, VIDIOC_SUBSCRIBE_EVENT, &sub))
		fail("SUBSCRIBE_EVENT(SOURCE_CHANGE) refused: %s -- without events there is only polling, and that is not what this program does",
		     strerror(errno));
}

/*
 * Take every pending event off the queue and say what kinds were on it. The
 * caller re-reads the state, but not all of it: a SOURCE_CHANGE is a question
 * to QUERY_DV_TIMINGS and costs 20 ms of measurement, a control event of the
 * audio status is not (see the sound section below).
 */
#define EV_SOURCE_CHANGE	(1u << 0)
#define EV_CTRL			(1u << 1)

static unsigned int capture_drain_events(struct capture *cap)
{
	struct v4l2_event ev;
	unsigned int seen = 0;

	while (!ioctl(cap->fd, VIDIOC_DQEVENT, &ev)) {
		if (ev.type == V4L2_EVENT_SOURCE_CHANGE) {
			seen |= EV_SOURCE_CHANGE;
			info("event           SOURCE_CHANGE (changes 0x%x, seq %u)",
			     ev.u.src_change.changes, ev.sequence);
		} else if (ev.type == V4L2_EVENT_CTRL) {
			seen |= EV_CTRL;
			info("event           CTRL 0x%08x = %d (changes 0x%x, seq %u)",
			     ev.id, ev.u.ctrl.value, ev.u.ctrl.changes,
			     ev.sequence);
		} else {
			info("event           type %u", ev.type);
		}
	}
	if (errno != ENOENT && errno != EAGAIN)
		warn("DQEVENT: %s", strerror(errno));

	return seen;
}

/*
 * "Is there a signal" is a measurement in the driver, not a register bit: it
 * reads the ring's flip pointers, waits 20 ms and reads them again, and
 * answers -ENOLINK when they did not move (0094,
 * h713_hdmirx_signal_present()). That costs about 20 ms per call, which is
 * why it is only called on an event.
 *
 * The measurement cannot tell *why* the pointers stand still. A pulled cable
 * and a capture the descriptor switched off look exactly the same from here.
 * That ambiguity is real and is named in the README; it is not papered over
 * with a guess.
 *
 * Returns 1 with *t filled in, 2 for a change in flight, 3 for a source the
 * receiver will not lock, 0 for "no signal", -1 for a broken device. In case
 * 3 *t is filled in as well -- QUERY_DV_TIMINGS returns its measurement
 * together with the error.
 */
static int capture_signal(struct capture *cap, struct v4l2_dv_timings *t)
{
	memset(t, 0, sizeof(*t));
	if (!ioctl(cap->fd, VIDIOC_QUERY_DV_TIMINGS, t))
		return 1;
	if (errno == ENOLCK)
		return 2;	/* a change in flight, see struct retry */
	if (errno == ERANGE)
		return 3;	/* measured, but in none of the firmware's mode
				 * records, so it will never lock (kernel 0136m)
				 */
	if (errno == ENOLINK || errno == ENODATA)
		return 0;

	warn("QUERY_DV_TIMINGS: %s", strerror(errno));

	return -1;
}

/*
 * The signal as one string: geometry, scan type, frame rate and pixel clock,
 * "1920x1080p50, 148.5 MHz". The frame rate is not a field of the timing -- it
 * is the pixel clock over the whole raster -- and without it 50 and 60, and 24
 * and 30, read alike in the journal and in ctl status (21.09.2026, finding 4).
 * A rate that is not a whole number of hertz is printed with its two decimals,
 * so 59.94 is not shown as 60.
 */
static const char *signal_text(const struct v4l2_dv_timings *t, char *buf,
			       size_t len)
{
	const struct v4l2_bt_timings *bt = &t->bt;
	unsigned long long raster = (unsigned long long)V4L2_DV_BT_FRAME_WIDTH(bt) *
				    V4L2_DV_BT_FRAME_HEIGHT(bt);
	unsigned long long clk = bt->pixelclock;
	unsigned int hz100 = raster ? (unsigned int)((clk * 100 + raster / 2) / raster) : 0;
	char rate[16];

	if (!hz100)
		snprintf(rate, sizeof(rate), "?");
	else if (hz100 % 100)
		snprintf(rate, sizeof(rate), "%u.%02u", hz100 / 100, hz100 % 100);
	else
		snprintf(rate, sizeof(rate), "%u", hz100 / 100);
	/* rounded, not cut: the record of a 1024x768 says 64 995 840 Hz */
	clk = (clk + 50000) / 100000;
	snprintf(buf, len, "%ux%u%s%s, %llu.%llu MHz", bt->width, bt->height,
		 bt->interlaced ? "i" : "p", rate, clk / 10, clk % 10);

	return buf;
}

/*
 * The capture RING, as the driver reports it in the format: the size the
 * capture writes and the line pitch (bytesperline = INCAP rowbyte * 16,
 * kernel 0131). This is not the source signal. Where the firmware scales in
 * its capture path the ring is smaller than the source -- a 1920x1080 source
 * on a 1280x720 panel lands in the ring 864 bytes wide (kernel 0136f) -- and
 * the ring is what the plane must be given, or it reads the ring with the
 * wrong size and stride and the picture shears. The pitch is the width
 * rounded up to a multiple of 16 (1920, 1280, 1376 for 1366, 864 for 852), and
 * the plane must be told that pitch, not the width, or a 1366-wide picture
 * slips ten bytes per line. Asked after QUERY_DV_TIMINGS, which is what makes
 * the format follow the signal. When G_FMT fails the source stands in, with
 * the rounding rule for the pitch and a line in the journal.
 */
static void capture_format(struct capture *cap,
			   const struct v4l2_dv_timings *sig,
			   unsigned int *w, unsigned int *h, unsigned int *pitch)
{
	struct v4l2_format f;

	memset(&f, 0, sizeof(f));
	f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	if (ioctl(cap->fd, VIDIOC_G_FMT, &f)) {
		*w = sig->bt.width;
		*h = sig->bt.height;
		*pitch = (*w + 15) & ~15u;
		warn("G_FMT: %s -- ring %ux%u, line pitch %u by the rule of 16",
		     strerror(errno), *w, *h, *pitch);
		return;
	}
	*w = f.fmt.pix_mp.width;
	*h = f.fmt.pix_mp.height;
	*pitch = f.fmt.pix_mp.plane_fmt[0].bytesperline;
	if (*pitch < *w) {
		unsigned int rounded = (*w + 15) & ~15u;

		warn("G_FMT reports %ux%u with line pitch %u below the width -- line pitch %u by the rule of 16",
		     *w, *h, *pitch, rounded);
		*pitch = rounded;
	}
}

/*
 * What the capture format says about colour. Since kernel 0136n the driver
 * fills it from the firmware's own signal record -- the colorimetry the AVI
 * InfoFrame carried, the range out of the HDMI default rule -- instead of
 * answering BT.709 limited for every source. So this is the source's verdict
 * carried through, and it belongs in the status beside the geometry: a
 * picture that comes out washed out or crushed is answered here.
 */
static const char *capture_colour(struct capture *cap, char *buf, size_t len)
{
	static const char *const space[] = {
		[V4L2_COLORSPACE_SMPTE170M] = "BT.601",
		[V4L2_COLORSPACE_REC709] = "BT.709",
		[V4L2_COLORSPACE_SRGB] = "sRGB",
		[V4L2_COLORSPACE_BT2020] = "BT.2020",
	};
	struct v4l2_pix_format_mplane *pix;
	struct v4l2_format f;
	const char *cs = NULL;
	const char *enc = "";

	memset(&f, 0, sizeof(f));
	f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	if (ioctl(cap->fd, VIDIOC_G_FMT, &f)) {
		snprintf(buf, len, "not readable (%s)", strerror(errno));
		return buf;
	}
	pix = &f.fmt.pix_mp;
	if (pix->colorspace < sizeof(space) / sizeof(space[0]))
		cs = space[pix->colorspace];
	if (pix->ycbcr_enc == V4L2_YCBCR_ENC_BT2020_CONST_LUM)
		enc = ", constant luminance";
	else if (pix->ycbcr_enc == V4L2_YCBCR_ENC_XV709)
		enc = ", xvYCC";
	snprintf(buf, len, "%s, %s range%s", cs ? cs : "unnamed",
		 pix->quantization == V4L2_QUANTIZATION_FULL_RANGE ? "full"
								   : "limited",
		 enc);

	return buf;
}

/* ------------------------------------------------------------------ *
 * The display: one overlay plane, driven in "hdmi-ring" mode
 * ------------------------------------------------------------------ */

struct props {
	drmModeObjectProperties *list;
	drmModePropertyRes **info;
};

static bool props_get(int fd, uint32_t id, uint32_t type, struct props *p)
{
	unsigned int i;

	p->list = drmModeObjectGetProperties(fd, id, type);
	if (!p->list)
		return false;
	p->info = calloc(p->list->count_props, sizeof(*p->info));
	if (!p->info)
		fail("out of memory");
	for (i = 0; i < p->list->count_props; i++)
		p->info[i] = drmModeGetProperty(fd, p->list->props[i]);

	return true;
}

static void props_put(struct props *p)
{
	unsigned int i;

	if (!p->list)
		return;
	for (i = 0; i < p->list->count_props; i++)
		if (p->info[i])
			drmModeFreeProperty(p->info[i]);
	free(p->info);
	drmModeFreeObjectProperties(p->list);
	p->list = NULL;
	p->info = NULL;
}

static uint32_t prop_id(const struct props *p, const char *name)
{
	unsigned int i;

	for (i = 0; i < p->list->count_props; i++)
		if (p->info[i] && !strcmp(p->info[i]->name, name))
			return p->info[i]->prop_id;

	return 0;
}

static bool prop_value(const struct props *p, const char *name, uint64_t *out)
{
	unsigned int i;

	for (i = 0; i < p->list->count_props; i++)
		if (p->info[i] && !strcmp(p->info[i]->name, name)) {
			*out = p->list->prop_values[i];
			return true;
		}

	return false;
}

static const drmModePropertyRes *prop_info(const struct props *p,
					   const char *name)
{
	unsigned int i;

	for (i = 0; i < p->list->count_props; i++)
		if (p->info[i] && !strcmp(p->info[i]->name, name))
			return p->info[i];

	return NULL;
}

/* the name the kernel gives an enum value, or NULL */
static const char *prop_enum_name(const struct props *p, const char *name,
				  uint64_t val)
{
	const drmModePropertyRes *r = prop_info(p, name);
	int i;

	if (!r || !(r->flags & DRM_MODE_PROP_ENUM))
		return NULL;
	for (i = 0; i < r->count_enums; i++)
		if (r->enums[i].value == val)
			return r->enums[i].name;

	return NULL;
}

/* an enum value by its kernel name (case-insensitive) or by number */
static bool prop_enum_parse(const struct props *p, const char *name,
			    const char *text, uint64_t *val)
{
	const drmModePropertyRes *r = prop_info(p, name);
	char *end;
	unsigned long long n;
	int i;

	if (!r || !(r->flags & DRM_MODE_PROP_ENUM))
		return false;
	n = strtoull(text, &end, 0);
	for (i = 0; i < r->count_enums; i++) {
		if ((!*end && r->enums[i].value == n) ||
		    !strcasecmp(r->enums[i].name, text)) {
			*val = r->enums[i].value;
			return true;
		}
	}

	return false;
}

struct display {
	int fd;
	uint32_t crtc_id;
	unsigned int crtc_index;	/* bit position in possible_crtcs */
	uint32_t plane_id;
	unsigned int width;		/* panel mode (CRTC) */
	unsigned int height;
	unsigned int src_w;		/* source geometry (framebuffer + SRC_) */
	unsigned int src_h;
	unsigned int src_pitch;		/* ring line pitch (capture bytesperline) */
	bool has_aspect;		/* the plane offers the "aspect" property (0133) */
	uint64_t aspect;		/* its value, sent with every show */
	bool has_windows;		/* it offers src-window/dst-window (0133f) */
	/* the zoom, and the three things display_zoom_apply() derives from it */
	enum zoom_mode zoom;
	unsigned int zoom_arg;		/* ZOOM_IN: factor x 100; ZOOM_OUT: percent */
	struct window src_win, dst_win;	/* w = 0: not sent, the firmware's default */
	unsigned int win_x, win_y, win_w, win_h;	/* the plane on the panel */
	struct props crtc_props;
	uint32_t gamma_blob;		/* GAMMA_LUT blob from -g, 0 = none */
	struct props plane_props;
	/* framebuffer: geometry and format carrier only, never shown */
	uint32_t fb_handle;
	uint32_t fb_id;
	uint64_t fb_size;
	bool master;
	bool on;
	bool warped;			/* h713-warp draws on the video plane (NV12) */
};

/*
 * card0 is Panfrost on this board, so the driver name decides, not the
 * number. Render nodes are not considered: modesetting needs the primary
 * node.
 */
static int display_open_card(const char *want_path)
{
	char path[64];
	unsigned int i;
	int fd;

	for (i = 0; i < 16; i++) {
		drmVersionPtr v;
		bool match;

		if (want_path)
			snprintf(path, sizeof(path), "%s", want_path);
		else
			snprintf(path, sizeof(path), "/dev/dri/card%u", i);

		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0) {
			if (want_path)
				fail("%s cannot be opened: %s", path,
				     strerror(errno));
			continue;
		}
		v = drmGetVersion(fd);
		match = v && !strcmp(v->name, DRM_DRIVER);
		if (v)
			drmFreeVersion(v);
		if (match) {
			info("display         %s (%s)", path, DRM_DRIVER);
			return fd;
		}
		close(fd);
		if (want_path)
			fail("%s is not served by \"%s\"", path,
			     DRM_DRIVER);
	}
	fail("no DRM device with the driver \"%s\"", DRM_DRIVER);

	return -1;
}

/*
 * The panel is up before this program starts: the console runs on it. So the
 * CRTC and its mode are taken as they are; this program never sets a mode and
 * never touches the panel timing. On our board this finds CRTC 36 behind
 * connector 33, in 1920x1080.
 */
static void display_find_crtc(struct display *d)
{
	drmModeRes *res = drmModeGetResources(d->fd);
	unsigned int i;

	if (!res)
		fail("no KMS resources: %s", strerror(errno));

	for (i = 0; i < (unsigned int)res->count_crtcs; i++) {
		drmModeCrtc *c = drmModeGetCrtc(d->fd, res->crtcs[i]);

		if (c && c->mode_valid) {
			d->crtc_id = c->crtc_id;
			d->width = c->mode.hdisplay;
			d->height = c->mode.vdisplay;
			d->win_w = d->width;
			d->win_h = d->height;
			d->crtc_index = i;
			drmModeFreeCrtc(c);
			break;
		}
		if (c)
			drmModeFreeCrtc(c);
	}
	drmModeFreeResources(res);

	if (!d->crtc_id)
		fail("no CRTC drives a mode -- is the console running? (dmesg | grep afbd)");
	info("crtc            %u, mode %ux%u", d->crtc_id, d->width, d->height);
}

/*
 * The video plane is the overlay on this CRTC that can do NV16 and has the
 * driver-private "hdmi-ring" property. That is plane 38, named "video-0", on
 * our board -- but the number is found, not assumed.
 */
static void display_find_plane(struct display *d)
{
	drmModePlaneRes *planes = drmModeGetPlaneResources(d->fd);
	unsigned int i;

	if (!planes)
		fail("no plane resources: %s", strerror(errno));

	for (i = 0; i < planes->count_planes && !d->plane_id; i++) {
		drmModePlane *p = drmModeGetPlane(d->fd, planes->planes[i]);
		struct props pp = { 0 };
		uint64_t type = 0;
		unsigned int f;
		bool nv16 = false;

		if (!p)
			continue;
		if ((p->possible_crtcs & (1u << d->crtc_index)) &&
		    props_get(d->fd, p->plane_id, DRM_MODE_OBJECT_PLANE, &pp)) {
			prop_value(&pp, "type", &type);
			for (f = 0; f < p->count_formats; f++)
				if (p->formats[f] == DRM_FORMAT_NV16)
					nv16 = true;
			if (nv16 && type == DRM_PLANE_TYPE_OVERLAY &&
			    prop_id(&pp, "hdmi-ring")) {
				d->plane_id = p->plane_id;
				d->plane_props = pp;
				memset(&pp, 0, sizeof(pp));
			}
			props_put(&pp);
		}
		drmModeFreePlane(p);
	}
	drmModeFreePlaneResources(planes);

	if (!d->plane_id)
		fail("no overlay plane with NV16 and the property \"hdmi-ring\" -- is the kernel running patch 0093?");
	/*
	 * "aspect" (kernel 0133) is how the firmware fits a source that is not
	 * the panel's shape; its start value is the kernel's default, and it
	 * is sent with every show from then on so that h713-tv ctl aspect can
	 * change it. A kernel without the property gets no such word.
	 */
	d->has_aspect = prop_value(&d->plane_props, "aspect", &d->aspect);
	/*
	 * "src-window" and "dst-window" (kernel 0133f) are the descriptor's own
	 * two windows, in panel pixels and independent of where the plane sits.
	 * Without them only "zoom off" is possible.
	 */
	d->has_windows = prop_id(&d->plane_props, "src-window") &&
			 prop_id(&d->plane_props, "dst-window");
	info("plane           %u, NV16, mode hdmi-ring%s%s%s", d->plane_id,
	     d->has_aspect ? ", format " : "",
	     d->has_aspect ? prop_enum_name(&d->plane_props, "aspect", d->aspect) : "",
	     d->has_windows ? ", zoom windows" : ", no zoom windows (kernel < 0133f)");
}

/*
 * A dumb buffer the size of the mode. In hdmi-ring mode the plane takes the
 * addresses from the capture ring and never reads this memory; the
 * framebuffer only states format, geometry and stride. NV16 has a
 * full-height chroma plane, so the allocation is twice the height of one
 * 8 bit plane and the second plane starts one picture below the first.
 *
 * Two things about this buffer are load-bearing:
 *
 *  - The pitch must be exactly the ring's. The plane programs Y_STRIDE from
 *    fb->pitches[0] and the chroma stride from 2 * fb->pitches[1] (0093),
 *    and those strides describe the *ring*, whose lines are one capture
 *    rowbyte apart: the width rounded up to 16 (1376 for 1366, see
 *    capture_format()). The dumb buffer is therefore allocated with the pitch
 *    as its width, and a pitch the kernel padded any further would
 *    mis-program the hardware for data this buffer does not own. Hence the
 *    hard check.
 *
 *  - Its content stays as the kernel hands it over, that is all zero. That
 *    is deliberate. If the plane cannot read a valid flip pair when it comes
 *    up, 0093 falls back to these addresses -- and all-zero NV16 is exactly
 *    the flat green that the empty ring produces
 *    (doku/nachtlog/A-abnahme-board.md). Keeping both cases green keeps one
 *    known fingerprint for one condition, "nothing wrote any pixels",
 *    instead of inventing a second colour for the same fact.
 */
static void display_create_fb(struct display *d)
{
	struct drm_mode_create_dumb creq;
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };

	memset(&creq, 0, sizeof(creq));
	creq.width = d->src_pitch;
	creq.height = d->src_h * 2;
	creq.bpp = 8;
	if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq))
		fail("CREATE_DUMB %ux%u: %s", d->src_pitch, d->src_h * 2,
		     strerror(errno));
	if (creq.pitch != d->src_pitch)
		fail("the dumb buffer has line pitch %u instead of %u -- the plane programs the ring stride from it, and a padded buffer would set the hardware up for data it does not own",
		     creq.pitch, d->src_pitch);

	d->fb_handle = creq.handle;
	d->fb_size = creq.size;

	handles[0] = handles[1] = creq.handle;
	pitches[0] = pitches[1] = creq.pitch;
	offsets[1] = creq.pitch * d->src_h;
	if (drmModeAddFB2(d->fd, d->src_w, d->src_h, DRM_FORMAT_NV16, handles,
			  pitches, offsets, &d->fb_id, 0))
		fail("AddFB2: %s", strerror(errno));
}

static void display_destroy_fb(struct display *d)
{
	struct drm_mode_destroy_dumb dreq;

	if (d->fb_id)
		drmModeRmFB(d->fd, d->fb_id);
	if (d->fb_handle) {
		memset(&dreq, 0, sizeof(dreq));
		dreq.handle = d->fb_handle;
		drmIoctl(d->fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dreq);
	}
	d->fb_id = 0;
	d->fb_handle = 0;
}

static bool add(drmModeAtomicReq *req, const struct display *d,
		const char *name, uint64_t value)
{
	uint32_t id = prop_id(&d->plane_props, name);

	if (!id) {
		warn("the plane has no property \"%s\"", name);
		return false;
	}
	if (drmModeAtomicAddProperty(req, d->plane_id, id, value) < 0) {
		warn("%s=%llu cannot be queued: %s", name,
		     (unsigned long long)value, strerror(errno));
		return false;
	}

	return true;
}

/*
 * The kernel's own console client stops painting while a userspace master
 * exists (drm_master_internal_acquire), so the master is only held while the
 * picture is up. Dropping it does not disturb the plane state; it hands the
 * panel back to whoever paints the console.
 *
 * While it is held, no other DRM client on the board can do anything --
 * gamma_test refused with EACCES for exactly this reason while the plane was
 * up (doku/nachtlog/H-abnahme-board.md, addendum 06:20). Stop this unit
 * before running another KMS tool; that is a fact about DRM, not a defect.
 */
static bool display_take_master(struct display *d)
{
	if (d->master)
		return true;
	if (drmSetMaster(d->fd)) {
		warn("SET_MASTER: %s -- another client holds the display",
		     strerror(errno));
		return false;
	}
	d->master = true;

	return true;
}

static void wall_black_end(struct display *d);	/* the black wall between a release and the ring: the console's framebuffer first */
static void under_black_off(struct display *d);	/* the black frame under a page off the video plane, before the master goes */
static struct {
	uint32_t handle, fb_id;
	bool up;		/* the video plane carries the black frame under a page (under_black_up()) */
} under;

static void display_release_master(struct display *d)
{
	if (!d->master)
		return;
	under_black_off(d);
	wall_black_end(d);
	if (drmDropMaster(d->fd))
		warn("DROP_MASTER: %s", strerror(errno));
	d->master = false;
}

/*
 * The display gamma. The stock firmware runs the panel through the DE2 gamma
 * stage with a 2.2 curve (pq_picturemode.ini gamma index 3, doku/81 section 4);
 * the MIPS does not load it ("Can not get MP GAMMAModuleID" at every start),
 * the Android side did. Without it the panel shows the identity ramp, which
 * is not the stock picture. The curve comes as one DE2 bank from h713-pq
 * (512 u32, two 12-bit samples each, doku/87 section 2) and goes to the
 * CRTC's GAMMA_LUT (kernel 0095) as a property blob. It is a property of the
 * CRTC, not of the plane, so it colours the console as well -- as on stock.
 */
#define DE2_BANK_DWORDS	512
#define GAMMA_ENTRIES	(2 * DE2_BANK_DWORDS)

_Static_assert(GAMMA_ENTRIES == GAMMA_N, "the CRTC's table and the computed curve have the same length");

static uint16_t gamma_12_to_16(uint32_t v)
{
	/* the inverse of drm_color_lut_extract() for 12 bits, see gamma_test.c */
	return (uint16_t)((v * 65535u + 2047u) / 4095u);
}

/* three curves of 1024 12-bit samples -> the entries of GAMMA_LUT (the file and the computed curve both end here) */
static void gamma_lut_entries(const gamma_curve c, struct drm_color_lut lut[GAMMA_ENTRIES])
{
	unsigned int i;

	for (i = 0; i < GAMMA_ENTRIES; i++) {
		lut[i].red = gamma_12_to_16(c[0][i] & 0xfff);
		lut[i].green = gamma_12_to_16(c[1][i] & 0xfff);
		lut[i].blue = gamma_12_to_16(c[2][i] & 0xfff);
		lut[i].reserved = 0;
	}
}

/* does the CRTC have a GAMMA_LUT of the length this program writes (kernel 0095)? */
static bool display_gamma_ready(struct display *d)
{
	uint64_t size = 0;

	if (!props_get(d->fd, d->crtc_id, DRM_MODE_OBJECT_CRTC, &d->crtc_props)) {
		warn("gamma           CRTC properties not readable: %s", strerror(errno));
		return false;
	}
	if (!prop_id(&d->crtc_props, "GAMMA_LUT") ||
	    !prop_value(&d->crtc_props, "GAMMA_LUT_SIZE", &size) ||
	    size != GAMMA_ENTRIES) {
		warn("gamma           CRTC %u has no GAMMA_LUT with %u entries (kernel 0095) -- the identity ramp stays",
		     d->crtc_id, GAMMA_ENTRIES);
		return false;
	}

	return true;
}

static void display_gamma_load(struct display *d, const char *path)
{
	struct drm_color_lut lut[GAMMA_ENTRIES];
	gamma_curve curve;
	uint32_t bank[3][DE2_BANK_DWORDS];
	unsigned int i, channels;
	size_t got;
	FILE *f;

	d->gamma_blob = 0;
	if (!path || !strcasecmp(path, "none"))
		return;
	if (!display_gamma_ready(d))
		return;
	f = fopen(path, "rb");
	if (!f) {
		warn("gamma           %s: %s -- the identity ramp stays", path, strerror(errno));
		return;
	}
	got = fread(bank, 1, sizeof(bank), f);
	bool invalid = ferror(f) || fgetc(f) != EOF;
	fclose(f);
	if (invalid || (got != sizeof(bank[0]) && got != sizeof(bank))) {
		warn("gamma           %s: expected one or three complete DE2 banks (2048 or 6144 bytes) -- the identity ramp stays",
		     path);
		return;
	}
	channels = got / sizeof(bank[0]);
	for (i = 0; i < DE2_BANK_DWORDS; i++) {
		uint32_t r = bank[0][i];
		uint32_t g = bank[channels == 3 ? 1 : 0][i];
		uint32_t b = bank[channels == 3 ? 2 : 0][i];

		curve[0][2 * i] = r & 0xfff;
		curve[1][2 * i] = g & 0xfff;
		curve[2][2 * i] = b & 0xfff;
		curve[0][2 * i + 1] = (r >> 12) & 0xfff;
		curve[1][2 * i + 1] = (g >> 12) & 0xfff;
		curve[2][2 * i + 1] = (b >> 12) & 0xfff;
	}
	gamma_lut_entries((const uint16_t (*)[GAMMA_N])curve, lut);
	if (drmModeCreatePropertyBlob(d->fd, lut, sizeof(lut), &d->gamma_blob)) {
		warn("gamma           blob: %s -- the identity ramp stays", strerror(errno));
		d->gamma_blob = 0;
		return;
	}
	info("gamma           %s -> GAMMA_LUT (%u entries, middle %u/65535)", path,
	     GAMMA_ENTRIES, lut[GAMMA_ENTRIES / 2].red);
}

static bool display_take_master(struct display *d);
static void display_release_master(struct display *d);

/* queue the LUT on the CRTC; part of every show, and once at start */
static bool add_gamma(drmModeAtomicReq *req, const struct display *d)
{
	uint32_t id;

	if (!d->gamma_blob)
		return true;
	id = prop_id(&d->crtc_props, "GAMMA_LUT");
	if (drmModeAtomicAddProperty(req, d->crtc_id, id, d->gamma_blob) < 0) {
		warn("GAMMA_LUT cannot be queued: %s", strerror(errno));
		return false;
	}

	return true;
}

/*
 * Set the gamma while nothing is shown: take the master for one commit that
 * touches only the CRTC's LUT and give it back. The console keeps running on
 * its framebuffer, now through the stock curve.
 */
static void display_gamma_apply(struct display *d)
{
	drmModeAtomicReq *req;
	int ret;

	if (!d->gamma_blob || d->on)
		return;
	if (!display_take_master(d))
		return;
	req = drmModeAtomicAlloc();
	if (!req)
		fail("out of memory");
	if (!add_gamma(req, d)) {
		drmModeAtomicFree(req);
		display_release_master(d);
		return;
	}
	ret = drmModeAtomicCommit(d->fd, req, 0, NULL);
	drmModeAtomicFree(req);
	if (ret)
		warn("gamma           commit refused: %s", strerror(errno));
	display_release_master(d);
}

/*
 * A curve that gamma.c has computed, while the program runs: a new blob, one commit that carries only GAMMA_LUT (kernel
 * 0095 writes the banks when it changes, with a picture standing as well as without one), and the old blob let go.
 * The master is taken for the commit if nobody here holds it and given back after it, as display_gamma_apply() does at
 * the start; with a picture up it is ours already. The blob stays in the display, so that every show carries it.
 */
static struct display *gamma_disp;	/* where the curve goes: set once in main() */

static bool display_gamma_commit(struct display *d, uint32_t blob, char *why, size_t n)
{
	drmModeAtomicReq *req;
	bool had = d->master, ok = true;
	uint32_t id = prop_id(&d->crtc_props, "GAMMA_LUT");

	if (!id) {
		snprintf(why, n, "the CRTC has no GAMMA_LUT");
		return false;
	}
	if (!had && !display_take_master(d)) {
		snprintf(why, n, "another client holds the display");
		return false;
	}
	req = drmModeAtomicAlloc();
	if (!req)
		fail("out of memory");
	if (drmModeAtomicAddProperty(req, d->crtc_id, id, blob) < 0) {
		snprintf(why, n, "GAMMA_LUT cannot be queued: %s", strerror(errno));
		ok = false;
	} else if (drmModeAtomicCommit(d->fd, req, 0, NULL)) {
		snprintf(why, n, "the commit was refused: %s", strerror(errno));
		ok = false;
	}
	drmModeAtomicFree(req);
	if (!had)
		display_release_master(d);

	return ok;
}

static bool gamma_io_apply(const gamma_curve lut, char *why, size_t n)
{
	struct display *d = gamma_disp;
	struct drm_color_lut entries[GAMMA_ENTRIES];
	uint32_t blob = 0, old;

	if (!d) {
		snprintf(why, n, "no display");
		return false;
	}
	gamma_lut_entries(lut, entries);
	if (drmModeCreatePropertyBlob(d->fd, entries, sizeof(entries), &blob)) {
		snprintf(why, n, "blob: %s", strerror(errno));
		return false;
	}
	if (!display_gamma_commit(d, blob, why, n)) {
		drmModeDestroyPropertyBlob(d->fd, blob);
		return false;
	}
	old = d->gamma_blob;
	d->gamma_blob = blob;
	if (old)
		drmModeDestroyPropertyBlob(d->fd, old);

	return true;
}

static const struct gamma_io gamma_io = { .apply = gamma_io_apply };

/* a width down to a whole AFBD block, a height down to an even line count */
static unsigned int zoom_block(unsigned int v)
{
	return v & ~(WINDOW_MIN - 1);
}

static unsigned int zoom_even(unsigned int v)
{
	return v & ~1u;
}

/* and never below the one block the driver insists on (kernel 0133f) */
static unsigned int zoom_floor(unsigned int v)
{
	return v < WINDOW_MIN ? WINDOW_MIN : v;
}

/*
 * The three numbers a zoom is sent as, out of the mode and its argument.
 * Measured on 22.09.2026 (dev21, "Q15 bench"), step by step:
 *
 *   in f   source window = the centre 1/f of the frame, destination absent,
 *          plane over the whole panel. The firmware scales that window up
 *          into the whole ring - at f = 2 the centre quarter filled the panel
 *          and the cell pitch of the test pattern doubled (step c).
 *   out p  destination window = W x H at the RING's origin, W and H the panel
 *          times p; source window = the frame less two pixels, because with a
 *          source window the firmware calls full it skips its scaler and
 *          nothing moves (steps a, f, g). The plane crops the region the
 *          firmware filled and places it centred (step h).
 *   off    neither window; the plane covers the panel, as before any of this.
 */
static void display_zoom_apply(struct display *d)
{
	unsigned int w, h;

	memset(&d->src_win, 0, sizeof(d->src_win));
	memset(&d->dst_win, 0, sizeof(d->dst_win));
	d->win_x = 0;
	d->win_y = 0;
	d->win_w = d->width;
	d->win_h = d->height;
	if (d->zoom == ZOOM_IN) {
		w = zoom_floor(zoom_block(d->width * 100 / d->zoom_arg));
		h = zoom_floor(zoom_even(d->height * 100 / d->zoom_arg));
		/* the origin needs no rounding: only the size decides what the
		 * firmware scales, and half a pixel of centring is free
		 */
		d->src_win.x = (d->width - w) / 2;
		d->src_win.y = (d->height - h) / 2;
		d->src_win.w = w;
		d->src_win.h = h;
	} else if (d->zoom == ZOOM_OUT) {
		w = zoom_floor(zoom_block(d->width * d->zoom_arg / 100));
		h = zoom_floor(zoom_even(d->height * d->zoom_arg / 100));
		d->src_win.w = d->width - 2;
		d->src_win.h = d->height - 2;
		d->dst_win.w = w;
		d->dst_win.h = h;
		d->win_x = (d->width - w) / 2;
		d->win_y = (d->height - h) / 2;
		d->win_w = w;
		d->win_h = h;
	}
}

/* the zoom as one word: "off", "in 2.00", "out 80" -- the saved file's form */
static void zoom_text(const struct display *d, char *out, size_t n)
{
	if (d->zoom == ZOOM_IN)
		snprintf(out, n, "in %u.%02u", d->zoom_arg / 100,
			 d->zoom_arg % 100);
	else if (d->zoom == ZOOM_OUT)
		snprintf(out, n, "out %u", d->zoom_arg);
	else
		snprintf(out, n, "off");
}

/* one window for a status line */
static const char *window_text(const struct window *w, char *buf, size_t n)
{
	if (w->w)
		snprintf(buf, n, "%u,%u %ux%u", w->x, w->y, w->w, w->h);
	else
		snprintf(buf, n, "absent (the whole picture)");

	return buf;
}

/*
 * The part of the ring that carries a picture, which is what the plane reads
 * (SRC_W/SRC_H, kernel 0133c; it crops from the ring's first byte and no
 * other, so there is no SRC_X/SRC_Y here). At zoom off and zoom in the
 * firmware fills the whole ring and the ring is taken as it is -- which keeps
 * a ring whose width is no multiple of 16 (1366, kernel 0131) exactly the
 * buffer it was. At zoom out it filled the ring's top left corner by the
 * destination window's share, and the rest of the ring still holds the last
 * frame that filled it; the rectangle is rounded DOWN to a block of columns
 * and an even line count, because rounding up would show a strip of that old
 * frame. On the HY310, where the ring is the panel, this is the destination
 * window itself.
 */
static void display_source_rect(const struct display *d, unsigned int *w,
				unsigned int *h)
{
	if (d->zoom != ZOOM_OUT) {
		*w = d->src_w;
		*h = d->src_h;
		return;
	}
	*w = zoom_floor(zoom_block((unsigned int)((uint64_t)d->src_w *
						  d->zoom_arg / 100)));
	*h = zoom_floor(zoom_even((unsigned int)((uint64_t)d->src_h *
						 d->zoom_arg / 100)));
}

/* one window as a property blob, 0 for "absent" and for a blob we cannot make */
static uint32_t window_blob(const struct display *d, const struct window *win)
{
	uint32_t id = 0;

	if (win->w && drmModeCreatePropertyBlob(d->fd, win, sizeof(*win), &id)) {
		warn("window blob: %s -- the window is not sent", strerror(errno));
		return 0;
	}

	return id;
}

/* the kernel keeps its own reference while the state lives, so drop ours */
static void window_blobs_free(const struct display *d, uint32_t a, uint32_t b)
{
	if (a)
		drmModeDestroyPropertyBlob(d->fd, a);
	if (b)
		drmModeDestroyPropertyBlob(d->fd, b);
}

static void osd_drop(struct display *d);	/* the overlay off the panel: before every release of the master */
static void osd_resume(struct display *d);	/* ... and back when the picture is */
static bool osd_state_add(drmModeAtomicReq *req, struct display *d, bool picture);	/* the primary plane into a commit */
static void osd_state_committed(bool committed, bool picture);
static int osd_wanted(bool picture);	/* the buffer the primary plane is to carry, -1: the console's */
static bool osd_on_panel(void);		/* one of our buffers is on the primary plane */
static void console_keys(bool on);	/* the console's keyboard: off while anything else is on the panel */
static bool wall_black_wanted(const struct display *d);	/* a client's claim goes and the straight ring is to come (TODO 2.124) */
static bool wall_black_up(struct display *d);		/* ... the wall black for the ring's own commit */
static bool wall_black_is(uint32_t fb);			/* fb is that black framebuffer */
static bool ring_off_for_claim(struct display *d);	/* the straight ring goes for a claim's first frame: black, not the console */

static bool display_show(struct display *d)
{
	drmModeAtomicReq *req;
	uint32_t sb = 0, db = 0;
	unsigned int sw, sh;
	bool ok = true;
	int ret;

	if (d->on)
		return true;
	if (!display_take_master(d))
		return false;

	req = drmModeAtomicAlloc();
	if (!req)
		fail("out of memory");

	ok &= add(req, d, "FB_ID", d->fb_id);
	ok &= add(req, d, "CRTC_ID", d->crtc_id);
	ok &= add(req, d, "SRC_X", 0);
	ok &= add(req, d, "SRC_Y", 0);
	display_source_rect(d, &sw, &sh);
	ok &= add(req, d, "SRC_W", (uint64_t)sw << 16);
	ok &= add(req, d, "SRC_H", (uint64_t)sh << 16);
	ok &= add(req, d, "CRTC_X", d->win_x);
	ok &= add(req, d, "CRTC_Y", d->win_y);
	ok &= add(req, d, "CRTC_W", d->win_w);
	ok &= add(req, d, "CRTC_H", d->win_h);
	ok &= add(req, d, "hdmi-ring", 1);
	if (d->has_aspect)
		ok &= add(req, d, "aspect", d->aspect);
	if (d->has_windows) {
		sb = window_blob(d, &d->src_win);
		db = window_blob(d, &d->dst_win);
		ok &= add(req, d, "src-window", sb);
		ok &= add(req, d, "dst-window", db);
	}
	ok &= add_gamma(req, d);
	/*
	 * No "saturation" here. The chroma gain has one owner -- the firmware's
	 * SetSaturation RPC behind V4L2_CID_SATURATION on the capture node; the
	 * display driver stopped writing it (patch 0104, doku/nachtlog/I3). Set
	 * it with h713-tv ctl set saturation 0..100; it survives plane
	 * off/on because nothing resets the register any more.
	 */
	/* and the primary plane with it: the whole panel is said here, not only what changed */
	bool primary = ok && osd_state_add(req, d, true);

	if (!ok) {
		drmModeAtomicFree(req);
		window_blobs_free(d, sb, db);
		display_release_master(d);
		return false;
	}

	ret = drmModeAtomicCommit(d->fd, req, 0, NULL);
	drmModeAtomicFree(req);
	window_blobs_free(d, sb, db);
	if (primary)
		osd_state_committed(!ret, true);

	if (ret) {
		warn("atomic commit refused: %s", strerror(errno));
		if (errno == EOPNOTSUPP)
			warn("  the display node lacks memory-region-names = \"hdmi-ring\", \"viddec-info\" (check the DTB)");
		if (errno == EINVAL)
			warn("  geometry != mode, a non-linear modifier, unequal line pitches, or a width not divisible by 16");
		display_release_master(d);
		return false;
	}

	d->on = true;
	under.up = false;
	console_keys(false);
	info("picture         plane %u on, %ux%u out of the capture ring at %u,%u %ux%u on the panel%s",
	     d->plane_id, sw, sh, d->win_x, d->win_y, d->win_w, d->win_h,
	     d->zoom == ZOOM_IN ? ", zoomed in" :
	     d->zoom == ZOOM_OUT ? ", zoomed out" : "");

	return true;
}

/*
 * Returns false when the plane is still up. In that case the master is kept
 * and the state stays "on": claiming the console is back while a frame is
 * standing on the wall would be the one lie this program must not tell.
 */
static void console_restore(void);
static void console_login_clean(void);

/*
 * Black under an opaque page, not nothing (20.10.2026). On the HY300PRO-G-EU the RGB channel lies two pixels to the right of the
 * picture: the panel side reads the RGB layer's window at 50 + the layer's x origin (0x051C01A8; the origin 0x0528008C is 0
 * already and does not go below), the picture's at 48 (0x051C0180, the display firmware's own window word 0x0520000C). So the
 * first two columns of the panel always show the video plane, and with the plane off under a page that was the stopped
 * source - green zeros, or the colours of its last frame: a narrow line at the left edge of every page (Marco, 20.10.2026; stock
 * has the RGB layer on the picture's column and a video layer under its interface all the time). The video plane carries a still
 * black NV12 frame of the panel's size under the page now: one commit from the straight ring or the warp's frame, one back to
 * them, and no new descriptor - the ring's record stays published, the capture, the link and the claim stay as they did (the warp's
 * frames have the same geometry, the driver only flips). The AFBD reads 1.4 MB a frame for it at 720p (3.1 MB at 1080p), nothing
 * else runs. Without a page the plane goes off as before (display_hide()), and it never stays behind when the master goes.
 */
/* the black frame, made once: luma 16, chroma 128 (BT.709 limited range black), the chroma below the luma as the warp's */
static bool under_black_fb(struct display *d)
{
	struct drm_mode_create_dumb creq = { .width = d->width, .height = d->height * 3 / 2, .bpp = 8 };
	struct drm_mode_map_dumb mreq = { 0 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	uint8_t *p;

	if (under.fb_id)
		return true;
	if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq))
		return false;
	under.handle = mreq.handle = creq.handle;
	p = drmIoctl(d->fd, DRM_IOCTL_MODE_MAP_DUMB, &mreq) ? MAP_FAILED :
	    mmap(NULL, creq.size, PROT_WRITE, MAP_SHARED, d->fd, (off_t)mreq.offset);
	if (p != MAP_FAILED) {
		memset(p, 16, (size_t)creq.pitch * d->height);
		memset(p + (size_t)creq.pitch * d->height, 128, (size_t)creq.pitch * d->height / 2);
		munmap(p, creq.size);
		handles[0] = handles[1] = creq.handle;
		pitches[0] = pitches[1] = creq.pitch;
		offsets[1] = creq.pitch * d->height;
		if (!drmModeAddFB2(d->fd, d->width, d->height, DRM_FORMAT_NV12, handles, pitches, offsets, &under.fb_id, 0))
			return true;
	}
	warn("cover           no black frame for under the page (%s) -- the video plane goes off as before", strerror(errno));
	under.fb_id = 0;
	return false;
}

/* the black frame on the video plane and the primary plane as it is to be without a picture (the page), in one commit */
static bool under_black_up(struct display *d)
{
	static const char *const name[] = { "FB_ID", "CRTC_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H", "CRTC_X", "CRTC_Y",
					    "CRTC_W", "CRTC_H", "hdmi-ring" };
	drmModeAtomicReq *req;
	unsigned int i;
	bool ok, primary = false;
	int ret = -1;

	if (!d->master || !under_black_fb(d) || !(req = drmModeAtomicAlloc()))
		return false;
	uint64_t val[11] = { under.fb_id, d->crtc_id, 0, 0, (uint64_t)d->width << 16, (uint64_t)d->height << 16, 0, 0,
			     d->width, d->height, 0 };

	for (i = 0, ok = true; ok && i < 11; i++)
		ok = add(req, d, name[i], val[i]);
	if (ok && d->has_windows)
		ok = add(req, d, "src-window", 0) && add(req, d, "dst-window", 0);
	if (ok)
		primary = osd_state_add(req, d, false);
	if (ok && primary)
		ret = drmModeAtomicCommit(d->fd, req, 0, NULL);
	drmModeAtomicFree(req);
	if (primary)
		osd_state_committed(!ret, false);
	if (ret) {
		warn("cover           the black frame did not go under the page (%s) -- the video plane goes off as before",
		     ok && primary ? strerror(errno) : "a property is missing");
		return false;
	}
	if (!under.up)
		info("cover           black under the page on the video plane (the RGB channel leaves the first two columns to it)");
	under.up = true;
	d->on = false;
	return true;
}

static int display_plane_off(struct display *d);

/* before the master goes, or when the page goes and no picture comes: the black frame off the video plane */
static void under_black_off(struct display *d)
{
	if (under.up && d->master)
		display_plane_off(d);
}

/*
 * The video plane off and the primary plane as it is to be without a picture, in one commit: the console's
 * framebuffer at zpos 0 - no overlay over a plane that goes, channel 2 alone would show it - or an opaque page that
 * stays. 0: done; -1: refused (errno); -2: a property is missing.
 */
static int display_plane_off(struct display *d)
{
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	bool ok, primary;
	int ret;

	if (!req)
		fail("out of memory");
	primary = osd_state_add(req, d, false);
	if (!primary)
		osd_drop(d);	/* the primary plane is not known: the overlay off on its own first, as before */
	ok = add(req, d, "FB_ID", 0);
	ok &= add(req, d, "CRTC_ID", 0);
	ret = ok ? drmModeAtomicCommit(d->fd, req, 0, NULL) : -2;
	drmModeAtomicFree(req);
	if (primary && ok)
		osd_state_committed(!ret, false);
	if (!ret)
		under.up = false;

	return ret ? (ok ? -1 : -2) : 0;
}

static bool display_hide(struct display *d)
{
	int ret;

	if (!d->on && !(under.up && osd_wanted(false) < 0)) {	/* the black frame under a page that goes: off as a picture */
		if (!d->warped) {	/* the warp holds the master (A3) */
			if (osd_wanted(false) >= 0) {	/* an opaque page stays, over black */
				osd_resume(d);
				return true;
			}
			osd_drop(d);
			if (d->master) {
				display_release_master(d);
				console_restore();
			}
		}
		return true;
	}

	ret = display_plane_off(d);
	if (ret) {
		warn("the plane cannot be switched off (%s) -- the picture is still up, the console is NOT back",
		     ret == -1 ? strerror(errno) : "property missing");
		return false;
	}

	d->on = false;
	if (osd_on_panel()) {
		info("picture         plane off -- the opaque page stays, over black");
		return true;
	}
	display_release_master(d);
	console_restore();
	info("console         plane off, RGB channel and selector back, console unblanked");

	return true;
}

/* ------------------------------------------------------------------ *
 * The warp: h713-warp renders, this program shows (design AP2d A1-A4)
 *
 * h713-warp owns the render node, the capture buffers, the shader and the
 * matrix and owns no display: this program stays the only DRM master and the
 * only client that commits, so the two cannot race for the card. Three lines
 * cross the control socket, the file descriptors in SCM_RIGHTS on the same
 * connection: "warp claim" makes the three targets and hands their dma-bufs
 * over, "warp frame N" commits buffer N on the PRIMARY plane with the
 * daemon's out-fence as IN_FENCE_FD and the video plane off, "warp release"
 * gives the panel back (README 6e, docs/tools/h713-warp.md). The connection
 * IS the lifetime: a daemon that dies leaves a hangup here and this program
 * releases by itself. Video plane and warp are mutually exclusive, and this
 * program decides which is up. The picture is up either way, so the audio
 * follows d->on || d->warped - a warp must never mute the source.
 *
 * A claim is for the ring or for a Wayland client, and "warp switch client|ring" on the same connection turns one
 * into the other: the three buffers, the master and the video plane stay, only what h713-warp draws into the
 * buffers changes, so the wall goes from the last frame of the one to the first of the other. Releasing and
 * claiming again put the ring on the plane directly in between and switched the plane off for the new claim -
 * a flash at every change between HDMI and a client (16.10.2026). A "source" that no longer allows the claim is
 * said to h713-warp on the connection, unasked ("note source hdmi"), and h713-warp switches or releases; if it does
 * neither within WARP_REVOKE_MS, the claim is released here as before.
 * ------------------------------------------------------------------ */

#define WARP_BUFS	3
#define TIMING_SAY_S	10	/* late warp frames and slow commits: one summary line at most this often */
#define WARP_REVOKE_MS	1500	/* a claim the source no longer allows: h713-warp's time to switch or release */

struct warp {
	int peer;			/* the daemon's connection, -1: none */
	bool claimed;
	bool client;			/* it draws a Wayland client, not the ring: no signal needed */
	int flip;			/* client: our dup of the last commit's OUT_FENCE (the flip), -1 none */
	int told;			/* the "source" h713-warp last heard (with the claim or a frame's "ok"), -1 none */
	int revoke_fd;			/* timerfd: the claim's grace after a "note source", -1 none */
	bool revoking;			/* ... armed */
	struct timespec last_frame;	/* the previous "warp frame" of this claim, for the timing line; 0: none */
	struct timespec claimed_at;	/* when this claim was made: the journal line of its first frame */
	uint32_t handle[WARP_BUFS], fb_id[WARP_BUFS];
	unsigned int pitch, coff;	/* NV12: the line pitch, the chroma plane's offset */
	unsigned long commits, busy, errors;
};

static struct warp warp = { .peer = -1, .flip = -1, .told = -1, .revoke_fd = -1 };

/*
 * An opaque page on the wall (the launcher, a settings page) hides the whole picture, and the mode under it pauses:
 * h713-warp hears "note cover on" on its claim's connection and stops drawing, and the video plane goes OFF - nothing
 * of HDMI lies behind the page, and the display reads no picture nobody sees (Marco, 17.10.2026: "HDMI should lie
 * behind nothing, I do not want to waste resources"); the claim, the capture, the link and HDCP stay. A frame the warp
 * sends while the page stands is answered and not committed. The HDMI sound goes behind the DSP's mute and nothing
 * more (the path stays routed: no click, no DAC source change). "note cover off" when the page goes, or turns into a
 * pill over the picture: the warp's first frame turns the video plane on again and carries the change of the primary
 * plane, so the wall goes from the page to a new picture in one commit, and the sound comes back with it. Without a
 * warp claim (the ring straight on the plane) the plane goes off under the page the same way and the ring comes back
 * after it. Only a page that IS on the wall covers: one that waits for the warp's next frame to ride on does not, or
 * that frame would never come.
 */
#define COVER_RESUME_MS	100	/* "note cover off": the change waits this long for the warp's frame, then goes alone */

static struct {
	bool on;		/* what h713-warp and the sound were last told */
	bool plane_off;		/* the video plane was switched off for the page: the warp's next frame turns it on */
	bool resuming;		/* "note cover off" was said: an overlay change waits for the warp's next frame */
	int resume_fd;		/* timerfd: ... at most COVER_RESUME_MS */
} cover = { .resume_fd = -1 };

/*
 * The warp's word, and the wait for its claim (P3 of the media side project, 17.10.2026). h713-warp keeps a connection of
 * its own open and says on it whether it will claim the ring when it may: "warp want ring" (a keystone, a mirrored mount,
 * a test pattern) or "warp want none" (the identity, "warp = off", no GPU, a ring the GPU refused). With "ring",
 * evaluate() does not put the straight ring on the video plane once the signal stands - when it comes, when it comes
 * back, after "ctl auto", after the warp's release: it says "note claim" on that connection and waits for the claim, at
 * most WARP_HOLD_MS. The claim finds the plane off and its first frame turns it on: one switch, from black (the console,
 * or a page) to the warped picture. Before, the straight ring stood on the whole panel for 0.12-1.2 s, the claim switched
 * the plane off and its first frame on again, and a frame with false colours stood at that edge (HY310, 17.10.2026: the
 * box's camera at 12 of 12 claims, Marco's eye "often green after the switch"). Without a claim within WARP_HOLD_MS the
 * straight ring comes after all, said in the journal, and stays until a claim's first frame. A connection that closes
 * while it says "ring" - h713-warp restarting - leaves "ring" standing for WARP_HOLD_MS; a new connection with "ring"
 * starts the wait anew. Without a connection (no h713-warp, or one of before 17.10.2026) the ring comes at once, as
 * always. Under an opaque page nothing waits - nothing of ours is shown under it - but h713-warp hears "note claim" all
 * the same: its claim pauses under the page, and its first frame after the page carries the page's end.
 */
#define WARP_HOLD_MS	1000
#define WARP_CTL_SOCKET	"/run/h713-warp/ctl"	/* h713-warp's own control socket: it runs */

static struct {
	int peer;		/* h713-warp's "warp want" connection, -1: none */
	bool ring;		/* its last word: it claims the ring when it may */
	struct timespec gone;	/* the connection closed while it said "ring" (zero: it did not) */
	int fd;			/* timerfd: the end of the wait, -1 none */
	bool armed;		/* ... running */
	struct timespec since;	/* the wait for the claim began (zero: no wait) */
	bool noted;		/* "note claim" went since the last claim, loss of signal or new connection */
	bool fallback;		/* the wait ran out: the straight ring, until a claim's first frame */
} wish = { .peer = -1, .fd = -1 };

static bool ts_zero(const struct timespec *t)
{
	return !t->tv_sec && !t->tv_nsec;
}

/* milliseconds from t to now */
static long ms_since(const struct timespec *t)
{
	struct timespec now;

	clock_gettime(CLOCK_MONOTONIC, &now);
	return (now.tv_sec - t->tv_sec) * 1000 + (now.tv_nsec - t->tv_nsec) / 1000000;
}

/* h713-warp will claim the ring when it may: its word, or the word of a connection that closed less than WARP_HOLD_MS ago */
static bool warp_wants_ring(void)
{
	if (!wish.ring)
		return false;
	return wish.peer >= 0 || (!ts_zero(&wish.gone) && ms_since(&wish.gone) < WARP_HOLD_MS);
}

static void want_disarm(void)
{
	struct itimerspec its;

	if (!wish.armed)
		return;
	memset(&its, 0, sizeof(its));
	if (wish.fd >= 0)
		timerfd_settime(wish.fd, 0, &its, NULL);
	wish.armed = false;
}

/* no wait any more: a claim's first frame, a lost signal, "ctl off", a page, "warp want none" */
static void want_hold_end(void)
{
	want_disarm();
	memset(&wish.since, 0, sizeof(wish.since));
	wish.fallback = false;
}

/* "note claim" on h713-warp's connection: a claim of the ring is taken now. Once until the next claim or loss of signal. */
static void want_note_claim(void)
{
	if (wish.noted || wish.peer < 0)
		return;
	if (send(wish.peer, "note claim\n", 11, MSG_NOSIGNAL | MSG_DONTWAIT) == 11)
		wish.noted = true;
	else
		warn("warp            \"note claim\" did not go (%s) -- h713-warp claims at its next try", strerror(errno));
}

/*
 * evaluate() is about to put the straight ring on the video plane: true while it waits for h713-warp's claim instead,
 * the plane off. The first call starts the wait and tells h713-warp; once WARP_HOLD_MS are over (the timer brings
 * evaluate() back), or h713-warp is gone or says "none", the ring goes through - said in the journal.
 */
static bool want_hold(const struct display *d)
{
	struct itimerspec its = { 0 };
	long ms;

	if (d->on || warp.claimed || wish.fallback)
		return false;
	if (!warp_wants_ring()) {
		if (!ts_zero(&wish.since))
			info("warp            no claim to wait for any more (%s) -- the straight ring",
			     wish.ring ? "h713-warp's connection is gone" : "h713-warp says it will not claim the ring");
		want_hold_end();
		return false;
	}
	if (ts_zero(&wish.since)) {
		clock_gettime(CLOCK_MONOTONIC, &wish.since);
		info("warp            the straight ring waits for h713-warp's claim, at most %d ms -- the video plane stays off until its first frame",
		     WARP_HOLD_MS);
	}
	ms = ms_since(&wish.since);
	if (ms >= WARP_HOLD_MS - 2) {
		want_disarm();
		wish.fallback = true;
		warn("warp            h713-warp did not claim within %ld ms -- the straight ring after all, until a claim's first frame",
		     ms);
		return false;
	}
	want_note_claim();
	if (!wish.armed) {
		if (wish.fd < 0)
			wish.fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
		its.it_value.tv_sec = (WARP_HOLD_MS - ms) / 1000;
		its.it_value.tv_nsec = (WARP_HOLD_MS - ms) % 1000 * 1000000L;
		wish.armed = wish.fd >= 0 && !timerfd_settime(wish.fd, 0, &its, NULL);
		if (!wish.armed) {
			warn("warp            no timer for the wait (%s) -- the straight ring at once", strerror(errno));
			wish.fallback = true;
			return false;
		}
	}
	return true;
}

/* the want line of "ctl status" */
static const char *want_text(char *buf, size_t n)
{
	if (!ts_zero(&wish.since) && !wish.fallback && !warp.claimed)
		snprintf(buf, n, "ring -- the straight ring waits for h713-warp's claim (%ld of %d ms)", ms_since(&wish.since),
			 WARP_HOLD_MS);
	else if (wish.fallback)
		snprintf(buf, n, "%s -- the wait ran out: the straight ring until a claim's first frame", wish.ring ? "ring" : "none");
	else if (wish.peer >= 0)
		snprintf(buf, n, "%s (h713-warp's word: %s)", wish.ring ? "ring" : "none", wish.ring ?
			 "the straight ring waits up to 1000 ms for its claim" : "the straight ring at once");
	else if (warp_wants_ring())
		snprintf(buf, n, "ring (h713-warp's connection closed %ld ms ago: its restart is waited for)", ms_since(&wish.gone));
	else
		snprintf(buf, n, "none (no word from h713-warp: the straight ring at once)");
	return buf;
}

/* the grace for h713-warp ends: switched or released in time, or nothing more to wait for */
static void warp_revoke_stop(void)
{
	struct itimerspec its;

	if (!warp.revoking)
		return;
	memset(&its, 0, sizeof(its));
	if (warp.revoke_fd >= 0)
		timerfd_settime(warp.revoke_fd, 0, &its, NULL);
	warp.revoking = false;
}

static void warp_free(struct display *d)
{
	struct drm_mode_destroy_dumb dreq;
	int i;

	for (i = 0; i < WARP_BUFS; i++) {
		if (warp.fb_id[i])
			drmModeRmFB(d->fd, warp.fb_id[i]);
		if (warp.handle[i]) {
			memset(&dreq, 0, sizeof(dreq));
			dreq.handle = warp.handle[i];
			drmIoctl(d->fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dreq);
		}
		warp.fb_id[i] = 0;
		warp.handle[i] = 0;
	}
}

/* three targets (M9): 8 294 400 bytes each, 24.9 MB of the 128 MiB CMA */
static bool warp_alloc(struct display *d, int *fds)
{
	struct drm_mode_create_dumb creq;
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	int i;

	/*
	 * NV12, the luma plane and the chroma plane in one dumb buffer, the
	 * chroma below the luma (23.09.2026): the warp's frames go on the VIDEO
	 * plane, the channel the firmware runs its nine picture controls on,
	 * so they act on the warped picture exactly as on the ring. The video
	 * plane takes NV12 and NV16; NV16 shows with every other chroma line
	 * dropped (measured on the wall, 23.09.), so NV12 loses nothing and
	 * carries a third of the bytes XRGB did. The driver wants the pitch
	 * equal to the width and the same pitch on both planes.
	 */
	for (i = 0; i < WARP_BUFS; i++) {
		memset(&creq, 0, sizeof(creq));
		creq.width = d->width;
		creq.height = d->height * 3 / 2;
		creq.bpp = 8;
		if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq))
			return false;
		warp.handle[i] = creq.handle;
		warp.pitch = creq.pitch;
		warp.coff = creq.pitch * d->height;
		handles[0] = handles[1] = creq.handle;
		pitches[0] = pitches[1] = creq.pitch;
		offsets[1] = warp.coff;
		if (drmModeAddFB2(d->fd, d->width, d->height, DRM_FORMAT_NV12,
				  handles, pitches, offsets, &warp.fb_id[i], 0) ||
		    drmPrimeHandleToFD(d->fd, creq.handle, DRM_CLOEXEC | DRM_RDWR,
				       &fds[i]))
			return false;
	}

	return true;
}

/* One fenced commit: drm_atomic_helper_commit waits the IN_FENCE_FD out
 * before the commit tail writes AFBD_SRC, so GPU and scanout never overlap on
 * a buffer, and the fd stays ours. Non-blocking and without a page-flip
 * event, because this program must not wait a vsync per frame -- the kernel's
 * EBUSY for a commit still in flight is the "the daemon was early" answer.
 */
static bool warp_commit(struct display *d, int n, int fence, bool *busy, int *flip)
{
	int32_t out = -1;		/* the client's flip fence (OUT_FENCE_PTR) */
	static const char *const name[] = {
		"FB_ID", "CRTC_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H",
		"CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H", "IN_FENCE_FD",
	};
	uint64_t val[11] = {
		warp.fb_id[n], d->crtc_id, 0, 0, (uint64_t)d->width << 16,
		(uint64_t)d->height << 16, 0, 0, d->width, d->height,
		(uint64_t)fence,
	};
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	uint32_t flags = DRM_MODE_ATOMIC_NONBLOCK |
			 (warp.commits ? 0u : DRM_MODE_ATOMIC_ALLOW_MODESET);
	bool ok = req != NULL;
	unsigned int i;
	int ret;

	*busy = false;
	/* the VIDEO plane, without the ring: our NV12 frame, the whole panel */
	for (i = 0; ok && i < (fence >= 0 ? 11u : 10u); i++)
		ok = add(req, d, name[i], val[i]);
	if (ok)
		ok = add(req, d, "hdmi-ring", 0);
	/*
	 * And no window. The two window properties are plane state and
	 * survive display_hide(): a "zoom in" set on the ring before the warp
	 * claimed stays in the state, reaches the descriptor with the warp's
	 * frame and makes the firmware zoom into the centre of the warped
	 * picture (measured 05.10.2026: scaler window 640x360 over the
	 * warp's 1920x1080 frame, regs-Z2). The warp's own zoom is the
	 * keystone matrix; the firmware's windows belong to the ring, and
	 * display_show() sends them again when the ring comes back.
	 */
	if (ok && d->has_windows)
		ok = add(req, d, "src-window", 0) && add(req, d, "dst-window", 0);
	/*
	 * A Wayland client is paced by the flip itself: the CRTC's OUT_FENCE signals when
	 * this frame is on the panel (the afbd driver arms the event at the vsync IRQ), and h713-warp gets it
	 * with the answer. The ring's warp is paced by the capture and stays as it was.
	 */
	if (ok && warp.client)
		ok = drmModeAtomicAddProperty(req, d->crtc_id, prop_id(&d->crtc_props, "OUT_FENCE_PTR"),
					      (uint64_t)(uintptr_t)&out) >= 0;
	/*
	 * The primary plane goes with every frame, as this program wants it: the overlay or the console's framebuffer
	 * under the video. An overlay change waiting for this frame goes with it (one commit, no EBUSY between the
	 * two, 6h), and whatever else committed the primary plane meanwhile is undone by the next frame - the kernel's
	 * fbdev emulation does that on a switch of the VT to text mode, past the DRM master (drm_fb_helper_set_par(),
	 * FB_ACTIVATE_KD_TEXT), and laid the console over the picture (16.10.2026, every change between two clients).
	 * The plane is in the commit anyway: the simple pipe's CRTC check adds every plane of the CRTC.
	 */
	bool rides = ok && osd_state_add(req, d, true);
	ret = ok ? drmModeAtomicCommit(d->fd, req, flags, NULL) : -EINVAL;
	drmModeAtomicFree(req);
	if (rides)
		osd_state_committed(!ret, true);
	if (!ret) {
		warp.commits++;
		under.up = false;	/* a frame of the warp's took the video plane from the black one */
		*flip = out;
		return true;
	}
	if (ok && errno == EBUSY) {
		warp.busy++;
		*busy = true;
		return false;
	}
	warp.errors++;
	warn("warp            commit refused: %s",
	     ok ? strerror(errno) : "a plane property is missing");

	return false;
}

/* the panel back: on "warp release", on the daemon's hangup, on "ctl off" and
 * on the way out -- each has to end with a picture, so the console comes back
 * here and evaluate() puts the ring up again
 */
static void warp_release(struct display *d)
{
	if (warp.peer >= 0)
		close(warp.peer);
	warp.peer = -1;
	warp_revoke_stop();
	cover.resuming = false;		/* nothing will carry a waiting overlay change: the release commits it */
	memset(&warp.last_frame, 0, sizeof(warp.last_frame));
	if (!warp.claimed)
		return;
	/*
	 * The video plane off and the console (or an opaque page) on the primary plane in one commit, before the
	 * buffers go. Removing a framebuffer that is on a plane switches the plane off by itself (atomic_remove_fb),
	 * which is how it went before - after a commit of its own for the console's framebuffer. A client's claim that
	 * goes while the straight ring is to come leaves the wall black instead, for the ring's own commit (TODO 2.124).
	 */
	bool black = wall_black_wanted(d) && wall_black_up(d);

	if (!black && display_plane_off(d))
		warn("warp            the video plane did not go off with the release (%s) -- removing the buffers takes it off",
		     strerror(errno));
	warp_free(d);
	warp.claimed = false;
	warp.client = false;
	if (warp.flip >= 0)
		close(warp.flip);
	warp.flip = -1;
	d->warped = false;
	if (black) {
		info("wall            black with the client's release -- the straight ring takes it in its own commit");
	} else if (!osd_on_panel()) {
		display_release_master(d);
		console_restore();
		info("console         back with the warp's release, no page on the wall");
	}
	info("warp            released: %lu commits, %lu busy, %lu refused -- the panel is ours again%s",
	     warp.commits, warp.busy, warp.errors, osd_on_panel() ? ", the opaque page stays over black" : "");
	warp.commits = warp.busy = warp.errors = 0;
}

/* ------------------------------------------------------------------ *
 * The overlay: h713-osd draws, this program shows (TODO 2.43-2.46)
 *
 * Volume, mute, focus and input go over the picture on the PRIMARY plane -
 * the console's plane, the AFBD's channel 2. Since kernel 0251 that plane at
 * zpos 2 with an ARGB8888 framebuffer is mixed over the video plane with an
 * alpha per pixel, over the ring and over the warp alike (the warp draws on
 * the video plane). h713-osd draws (libh713osd), this program stays the only
 * DRM master and the only client that commits, as with the warp: "osd claim"
 * makes two ARGB8888 buffers the size of the panel and hands their dma-bufs
 * over (SCM_RIGHTS, with the answer), "osd show N" lays buffer N over the
 * picture, "osd hide" takes it away, "osd release" frees the buffers; the
 * connection is the lifetime.
 *
 * The console's own framebuffer is learnt from the plane the first time
 * this program commits it, and goes back onto the plane, at zpos 0, before
 * this program lets the master go - on every way the picture leaves
 * (display_hide, warp_release, the exit). Otherwise the console would come
 * back under an overlay, or not at all.
 *
 * Every commit of this program carries the primary plane as this program
 * wants it - the picture's (display_show), every warp frame, the overlay's
 * own - so the panel is what this program says, whoever committed in
 * between. The kernel's fbdev emulation does commit in between: a switch of
 * the VT to text mode forces its own state past the DRM master
 * (drm_fb_helper_set_par(), FB_ACTIVATE_KD_TEXT), the console's framebuffer
 * on the primary plane at the zpos it found and every other plane off.
 *
 * Without a picture (no signal, "off") a popup has nothing to lay itself
 * over: "show" keeps it as wanted and shows it when the picture is back. An
 * opaque page ("osd show N cover": the launcher, the settings) needs nothing
 * under it and is shown over black: the master is taken for it and given
 * back, with the console, when the page goes.
 * ------------------------------------------------------------------ */

#define OSD_BUFS	2

struct osd {
	int peer;			/* h713-osd's connection, -1: none */
	bool claimed;
	bool shown;			/* our buffer is on the plane at zpos 2 */
	int want;			/* the buffer h713-osd wants shown, -1: none */
	bool cover;			/* ... and it is an opaque page: shown without a picture too */
	bool queued;			/* while the warp draws: the change goes with its next frame */
	uint32_t plane_id;		/* the primary plane of our CRTC */
	struct props props;
	uint32_t console_fb;		/* the plane's framebuffer when it was first looked at: the console's */
	bool console_known;
	uint32_t handle[OSD_BUFS], fb_id[OSD_BUFS];
	unsigned int pitch;
	unsigned long shows, busy, errors;
};

static struct osd osd = { .peer = -1, .want = -1 };

/*
 * Bare: nothing of ours on the wall for a while, "ctl bare SECONDS" (TODO 4.9h, 25.10.2026). The autofocus draws its chessboard on
 * the console's framebuffer and hands the panel over with "ctl off" - but "off" leaves an opaque page standing over black (the
 * launcher over the console is wanted), so the launcher, the settings or the page without a signal stood over the board, and the
 * camera saw them and not the board ("no picture", L018 25.10.2026). While bare holds, osd_wanted() wants nothing on the primary
 * plane: the page goes - with the black frame under it - and with no picture the master and the console go back as display_hide()
 * gives them; h713-osd's "osd show" is kept as wanted and answered "ok waiting". At the end - "ctl bare 0" from the autofocus, or
 * the time given, a net for a caller that died - what h713-osd wanted last comes back (osd_resume(), as with a picture that came
 * back): nobody has to press a key. The picture path does not change: "ctl off" is still the console's mode, and a picture that
 * is up stays up under a bare overlay.
 */
#define BARE_MAX_S	600

static struct {
	bool on;
	int fd;			/* the timerfd of its end, -1: none made yet */
} bare = { .fd = -1 };

/*
 * No signal as a page (P5 of the media side project, 17.10.2026). In the mode HDMI with nothing to show - no signal, a source the
 * display cannot take - the wall shows h713-osd's opaque page "No signal on HDMI" (a line below: "HOME: menu"), not the console:
 * the wall shows nothing that nobody ordered (Marco), and the console is the service's - "ctl off" - and an image's without
 * h713-osd. This program tells h713-osd on the overlay connection, unasked: "note signal none" while the page is wanted, "note
 * signal TEXT" when it is not (the signal's name; "off" when the console is forced or a program is the mode). h713-osd also asks
 * once after each claim ("osd signal"), so a restart of either side, a standby, finds the page where it belongs. Under a program
 * the signal does not matter: no page. The launcher and the settings are h713-osd's to put in front of the page and take away
 * again - this program does not know them.
 *
 * The wall between the signal's loss and the page: the last picture stands until the page is on the wall (the ring or the warp's
 * last frame, frozen, at most NOSIG_WAIT_MS - h713-osd needs ~0.1 s through the keystone), and the page then covers it; before, the
 * claim went and the console showed for that tenth of a second. Without a page after NOSIG_WAIT_MS: the console, as it always was.
 * The way back: when the signal stands again and h713-warp is to claim the ring, the page stays until the claim is made (it pauses
 * under the page, its first frame carries the page's end: one commit from the page to the picture), at most WARP_HOLD_MS.
 */
#define NOSIG_WAIT_MS	1000	/* the last picture stands for the page this long, then the console after all */

static struct {
	bool lost;		/* nothing to show in the mode HDMI, and the signal is not back with its claim yet */
	bool said;		/* h713-osd's last word was "none" */
	struct timespec since;	/* the last picture has waited for the page since (zero: not waiting) */
	struct timespec back;	/* the signal stands again, the page has waited for h713-warp's claim since (zero: not waiting) */
	char text[64];		/* the signal's name: the word that takes the page away */
} nosig;

static bool nosig_page_ok(void);		/* the page can stand for "no signal" (h713-osd claimed, no console forced, no program) */
static bool nosig_linger(struct display *d);	/* h713-warp lets go while the page is not up: the claim and the last frame stay */
static const char *nosig_word(void);		/* what h713-osd is to hear now: "none", or what is not none */
static void nosig_said(bool said);
static void hold_console_note(uint32_t fb);	/* the console's framebuffer, for the start after a held restart (TODO 2.96) */
static uint32_t hold_console_fb(struct display *d, uint32_t fb);	/* fb is the holder's: the console's from the note, 0 */
static bool osd_handover(const struct display *d);	/* a page that goes leaves the wall to the ring's own commit */

/* a claim of the ring was made: that needed a signal, so the signal is back and the page can go (nosig_follow() says so) */
static void nosig_claimed(void)
{
	nosig.lost = false;
	memset(&nosig.back, 0, sizeof(nosig.back));
	memset(&nosig.since, 0, sizeof(nosig.since));
}

/* the primary plane of our CRTC with "zpos" (kernel 0251) and ARGB8888 */
static bool osd_find_plane(struct display *d)
{
	drmModePlaneRes *planes;
	unsigned int i, f;

	if (osd.plane_id)
		return true;
	planes = drmModeGetPlaneResources(d->fd);
	if (!planes)
		return false;
	for (i = 0; i < planes->count_planes && !osd.plane_id; i++) {
		drmModePlane *p = drmModeGetPlane(d->fd, planes->planes[i]);
		struct props pp = { 0 };
		uint64_t type = 0;
		bool argb = false;

		if (!p)
			continue;
		if ((p->possible_crtcs & (1u << d->crtc_index)) &&
		    props_get(d->fd, p->plane_id, DRM_MODE_OBJECT_PLANE, &pp)) {
			prop_value(&pp, "type", &type);
			for (f = 0; f < p->count_formats; f++)
				if (p->formats[f] == DRM_FORMAT_ARGB8888)
					argb = true;
			if (type == DRM_PLANE_TYPE_PRIMARY && argb && prop_id(&pp, "zpos")) {
				osd.plane_id = p->plane_id;
				osd.props = pp;
				memset(&pp, 0, sizeof(pp));
			}
			props_put(&pp);
		}
		drmModeFreePlane(p);
	}
	drmModeFreePlaneResources(planes);

	return osd.plane_id != 0;
}

static void osd_free(struct display *d)
{
	struct drm_mode_destroy_dumb dreq;
	int i;

	for (i = 0; i < OSD_BUFS; i++) {
		if (osd.fb_id[i])
			drmModeRmFB(d->fd, osd.fb_id[i]);
		if (osd.handle[i]) {
			memset(&dreq, 0, sizeof(dreq));
			dreq.handle = osd.handle[i];
			drmIoctl(d->fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dreq);
		}
		osd.fb_id[i] = 0;
		osd.handle[i] = 0;
	}
}

/* two buffers the size of the panel: 8 294 400 bytes each at 1080p */
static bool osd_alloc(struct display *d, int *fds)
{
	struct drm_mode_create_dumb creq;
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	int i;

	for (i = 0; i < OSD_BUFS; i++) {
		memset(&creq, 0, sizeof(creq));
		creq.width = d->width;
		creq.height = d->height;
		creq.bpp = 32;
		if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq))
			return false;
		osd.handle[i] = creq.handle;
		osd.pitch = creq.pitch;
		handles[0] = creq.handle;
		pitches[0] = creq.pitch;
		if (drmModeAddFB2(d->fd, d->width, d->height, DRM_FORMAT_ARGB8888,
				  handles, pitches, offsets, &osd.fb_id[i], 0) ||
		    drmPrimeHandleToFD(d->fd, creq.handle, DRM_CLOEXEC | DRM_RDWR, &fds[i]))
			return false;
	}

	return true;
}

/* the primary plane's eleven properties: framebuffer fb at zpos z, the whole panel; fb 0 is the plane off */
static bool osd_props(drmModeAtomicReq *req, const struct display *d, uint32_t fb, uint64_t z)
{
	static const char *const name[] = {
		"FB_ID", "CRTC_ID", "zpos", "SRC_X", "SRC_Y", "SRC_W", "SRC_H",
		"CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H",
	};
	uint64_t val[11] = {
		fb, fb ? d->crtc_id : 0, z, 0, 0, (uint64_t)d->width << 16, (uint64_t)d->height << 16,
		0, 0, d->width, d->height,
	};
	unsigned int i;

	for (i = 0; i < (fb ? 11u : 3u); i++) {
		uint32_t id = prop_id(&osd.props, name[i]);

		if (!id || drmModeAtomicAddProperty(req, osd.plane_id, id, val[i]) < 0)
			return false;
	}
	return true;
}

/*
 * The plane and the console's framebuffer, looked up the first time they are needed - before the first commit of
 * a picture or a warp, h713-osd or not. The framebuffer is whatever the plane holds then, unless it is one of ours:
 * the console's (the fbdev emulation's), or 0 when the plane is off - then "the console" is the plane off, and the
 * kernel's client paints it again once the master is gone and it is asked to (a switch to text mode, the last
 * close).
 */
static bool osd_learn(struct display *d)
{
	drmModePlane *p;

	if (!osd_find_plane(d))
		return false;
	if (osd.console_known)
		return true;
	p = drmModeGetPlane(d->fd, osd.plane_id);
	if (!p)
		return false;
	if (wall_black_is(p->fb_id) && osd.console_fb) {
		osd.console_known = true;	/* our own black wall (TODO 2.124) is no console: the one learnt before stays */
	} else if (!osd.claimed || (p->fb_id != osd.fb_id[0] && p->fb_id != osd.fb_id[1])) {
		uint32_t con = hold_console_fb(d, p->fb_id);	/* the holder's black one (TODO 2.96): the console's is written down */

		osd.console_fb = con ? con : p->fb_id;
		osd.console_known = true;
		if (!p->fb_id)
			warn("osd             the primary plane %u is off -- the console comes back only when the kernel repaints it",
			     osd.plane_id);
		hold_console_note(p->fb_id);	/* for the start after a held restart (TODO 2.96) */
	}
	drmModeFreePlane(p);

	return osd.console_known;
}

/* the buffer the primary plane is to carry, -1: the console's framebuffer under the video */
static int osd_wanted(bool picture)
{
	if (!osd.claimed || osd.want < 0 || bare.on)
		return -1;
	return picture || osd.cover ? osd.want : -1;
}

static bool osd_on_panel(void)
{
	return osd.claimed && osd.shown;
}

/* an opaque page is on the wall and hides the picture: the mode under it pauses (cover) */
static bool osd_covering(void)
{
	return osd.claimed && osd.shown && osd.cover && osd.want >= 0;
}

/*
 * The primary plane as this program wants it, into a commit that is being made anyway: every picture, every warp
 * frame (warp_commit). picture: the commit puts a picture up or keeps one there. A change of the overlay waiting
 * for the warp's next frame goes in the same commit (the warp's non-blocking commits would otherwise meet ours,
 * EBUSY, and a blocking retry held the loop 45 ms, 11.10.2026).
 */
static bool osd_state_add(drmModeAtomicReq *req, struct display *d, bool picture)
{
	int w;

	if (!osd_learn(d))
		return false;
	w = osd_wanted(picture);
	return osd_props(req, d, w >= 0 ? osd.fb_id[w] : osd.console_fb, w >= 0 ? 2 : 0);
}

static void osd_state_committed(bool committed, bool picture)
{
	int w = osd_wanted(picture);

	if (!committed)
		return;		/* the frame was dropped: a change waits for the next one */
	if (w >= 0 && (osd.queued || !osd.shown))
		osd.shows++;
	osd.queued = false;
	osd.shown = w >= 0;
}

/* One commit of the primary plane on its own (no warp, or the master is about to go): non-blocking
 * first; on EBUSY once more blocking - nothing else commits then but a page flip in flight. */
static bool osd_commit(struct display *d, uint32_t fb, uint64_t z)
{
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	bool ok = req != NULL && osd_props(req, d, fb, z);
	int ret = -1;

	if (ok) {
		ret = drmModeAtomicCommit(d->fd, req, DRM_MODE_ATOMIC_NONBLOCK, NULL);
		if (ret && errno == EBUSY) {
			osd.busy++;
			ret = drmModeAtomicCommit(d->fd, req, 0, NULL);
		}
	}
	drmModeAtomicFree(req);
	if (!ret)
		return true;
	osd.errors++;
	warn("osd             commit refused (framebuffer %u, zpos %llu): %s", fb,
	     (unsigned long long)z, ok ? strerror(errno) : "a plane property is missing");

	return false;
}

/* the console's framebuffer back at zpos 0 - before every release of the
 * master; the overlay stays wanted and comes back with the picture */
static void osd_drop(struct display *d)
{
	osd.queued = false;
	if (!osd.shown)
		return;
	if (osd_commit(d, osd.console_fb, 0))
		osd.shown = false;
}

/*
 * A Wayland client may rest for seconds (Kodi's menu: 0.1 frames a second), so under it an overlay change
 * cannot wait for the warp's next frame: once the last flip is on the panel and no warp line is
 * waiting, the primary plane is committed on its own; otherwise the change rides as with the ring, and the loop looks
 * again when the flip fence signals (osd_settle). The ring's warp keeps riding: it sends a frame every vsync.
 */
static bool osd_alone(const struct display *d)
{
	struct pollfd pf[2] = { { .fd = warp.flip, .events = POLLIN }, { .fd = warp.peer, .events = POLLIN } };

	if (!d->warped || cover.resuming)
		return false;		/* none, or the warp's first frame after a page is on its way and carries the change */
	if (warp.peer < 0)
		return true;		/* a claim whose daemon let go (nosig_linger()): no frame will come to carry the change */
	/*
	 * The warp pauses under a page: a page that stays (the launcher's next row) goes on its own, there is no frame to
	 * ride on; one that goes rides with the warp's first frame after "note cover off" (cover_follow()).
	 */
	if (cover.on)
		return osd.cover && osd.want >= 0;
	if (!warp.client)
		return false;
	if (warp.flip >= 0 && poll(pf, 1, 0) != 1)
		return false;		/* the last flip is still in flight */
	return poll(pf + 1, 1, 0) == 0;	/* and no frame is waiting to be committed */
}

/*
 * The wanted buffer over the picture, if there is a picture to lay it over; an opaque page also without one, over
 * black: the master is taken for it (the video plane is off then, and channel 2 alone shows the page).
 */
static void osd_resume(struct display *d)
{
	bool picture = d->on || d->warped;

	if (osd_wanted(picture) < 0)
		return;
	if (!picture) {
		if (!display_take_master(d))
			return;
		if (osd_learn(d) && osd_commit(d, osd.fb_id[osd.want], 2)) {
			if (!osd.shown)
				info("osd             an opaque page over black -- there is no picture under it");
			osd.shown = true;
			osd.shows++;
			console_keys(false);
		} else if (!osd.shown) {
			display_release_master(d);
		}
		return;
	}
	if (!d->master)
		return;
	if (d->warped && !osd_alone(d)) {	/* with the warp's next frame */
		osd.queued = true;
		return;
	}
	osd.queued = false;
	if (osd_commit(d, osd.fb_id[osd.want], 2)) {
		osd.shown = true;
		osd.shows++;
	}
}

/* the opaque page went and there is no picture: the master and the console back, as display_hide() gives them */
static void osd_uncover(struct display *d)
{
	if (d->on || d->warped || osd.shown || !d->master)
		return;
	display_release_master(d);
	console_restore();
	info("console         the opaque page is gone and there is no picture -- the console is back");
}

/* the flip a queued change waited for is on the panel (client only): the change goes now, on its own */
static void osd_settle(struct display *d)
{
	if (!osd.queued || !osd_alone(d))
		return;
	if (osd_wanted(true) >= 0)	/* not osd.want: under "bare" the console's framebuffer goes, and nothing stays queued */
		osd_resume(d);
	else
		osd_drop(d);
}

static void osd_release(struct display *d)
{
	if (osd.peer >= 0)
		close(osd.peer);
	osd.peer = -1;
	if (!osd.claimed)
		return;
	osd.want = -1;
	osd.cover = false;
	nosig_said(false);
	osd_drop(d);
	osd_free(d);
	osd.claimed = false;
	osd_uncover(d);
	info("osd             released: %lu shown, %lu busy, %lu refused", osd.shows, osd.busy,
	     osd.errors);
	osd.shows = osd.busy = osd.errors = 0;
}

/* The peer's connection, one line per message as with the warp. */
static void osd_serve(struct display *d)
{
	char buf[64], word[16] = "", sigans[96];
	const char *answer = "error unknown (osd show N [cover] | osd hide | osd picture | osd signal | osd release)\n";
	ssize_t got;
	int n = -1;

	got = recv(osd.peer, buf, sizeof(buf) - 1, MSG_DONTWAIT);
	if (got <= 0) {			/* h713-osd is gone: the overlay goes with it */
		osd_release(d);
		return;
	}
	buf[got] = '\0';
	buf[strcspn(buf, "\r\n")] = '\0';
	if (!strcmp(buf, "osd release")) {
		if (send(osd.peer, "ok\n", 3, MSG_NOSIGNAL) < 0)
			warn("osd             answering the release: %s", strerror(errno));
		osd_release(d);
		return;
	}
	if (sscanf(buf, "osd show %d %15s", &n, word) >= 1 && n >= 0 && n < OSD_BUFS) {
		osd.want = n;
		osd.cover = !strcmp(word, "cover");	/* an opaque page: it needs no picture under it */
		if (bare.on) {
			/* kept as wanted, nothing on the wall: the end of "ctl bare" shows it (bare_end()) */
			answer = "ok waiting -- ctl bare: nothing of ours on the wall, it comes when that ends\n";
		} else if (!(d->on || d->warped) && osd.cover) {
			osd_resume(d);
			answer = osd.shown ? "ok cover -- over black, there is no picture under it\n"
					   : "error the commit was refused\n";
		} else if (!(d->on || d->warped)) {
			/* an opaque page before it goes: a popup does not stand over black - unless the ring is to come, whose
			 * commit takes the wall from the page and lays the popup over the picture (osd_handover()) */
			if (!osd_handover(d)) {
				osd_drop(d);
				osd_uncover(d);
			}
			answer = "ok waiting -- no picture to lay it over, it comes with the picture\n";
		} else if (d->warped) {
			osd_resume(d);		/* queued: the warp's next frame carries it */
			answer = "ok\n";
		} else {
			osd.shown = false;
			osd_resume(d);
			answer = osd.shown ? "ok\n" : "error the commit was refused\n";
		}
	} else if (!strcmp(buf, "osd hide")) {
		osd.want = -1;
		osd.cover = false;
		if (d->warped && osd.shown && !osd_alone(d)) {
			osd.queued = true;	/* the console's framebuffer back with the next frame */
			answer = "ok\n";
		} else if (osd_handover(d)) {
			answer = "ok\n";	/* the page stays until the ring's commit takes the wall, or display_hide() drops it */
		} else {
			osd_drop(d);
			answer = osd.shown ? "error the console framebuffer could not go back\n" : "ok\n";
			osd_uncover(d);
		}
	} else if (!strcmp(buf, "osd picture")) {
		/* what lies under the overlay: h713-osd pre-distorts only over the warp */
		answer = d->warped ? "ok warped\n" : d->on ? "ok ring\n" : "ok none\n";
	} else if (!strcmp(buf, "osd signal")) {
		/* the word on the signal, asked after every claim: "none" is the page without a signal (see "No signal as a page") */
		snprintf(sigans, sizeof(sigans), "ok signal %s\n", nosig_word());
		nosig_said(!strcmp(nosig_word(), "none"));
		answer = sigans;
	}
	if (send(osd.peer, answer, strlen(answer), MSG_NOSIGNAL) < 0) {
		warn("osd             answering \"%s\": %s", buf, strerror(errno));
		osd_release(d);
	}
}

/*
 * "bare" begins (the story is with struct bare): what is ours goes off the primary plane as with "osd hide", only the wish stays.
 * Over the warp's frames the console's framebuffer goes with the next one; with no picture display_hide() takes the page and the
 * black frame under it off in one commit and gives the master and the console back; over a picture the console's framebuffer goes
 * under it again.
 */
static void bare_begin(struct display *d)
{
	if (d->warped && osd.shown && !osd_alone(d)) {
		osd.queued = true;	/* osd_state_add() wants nothing now: the warp's next frame carries the console's framebuffer */
		return;
	}
	osd.queued = false;
	if (!d->on && !d->warped)
		display_hide(d);
	else
		osd_drop(d);
}

/* ... and ends: "ctl bare 0", or its time is over */
static void bare_end(struct display *d, const char *why)
{
	struct itimerspec off = { 0 };

	if (!bare.on)
		return;
	bare.on = false;
	if (bare.fd >= 0)
		timerfd_settime(bare.fd, 0, &off, NULL);
	info("bare            %s -- %s", why, osd_wanted(d->on || d->warped) >= 0 ? "h713-osd's overlay comes back" : "nothing to come back");
	osd_resume(d);		/* what h713-osd wanted last: over the picture, or an opaque page over black */
}

/* the seconds "bare" holds yet, 0 when it does not */
static long bare_left(void)
{
	struct itimerspec its;

	if (!bare.on || bare.fd < 0 || timerfd_gettime(bare.fd, &its))
		return 0;
	return its.it_value.tv_sec + (its.it_value.tv_nsec > 0);
}


/* ------------------------------------------------------------------ *
 * The wall held black over a restart of the picture path (TODO 2.96)
 *
 * h713-mips-restart stops this program to restart the display MIPS (the receiver's node has to be closed for its unbind) and
 * starts it again. The way out handed the panel to the console, and the next start unblanked it once more, so the wall showed
 * the console from the stop to the next picture or page: after every standby 7 to 8 s (HY300PRO-G-EU, 20.10.2026). The console
 * is the kernel's own client: it paints the panel whenever no DRM master does and it is asked to (an unblank, the last close of
 * the card). So the restart first starts "h713-tv --hold-wall": a second process of this program that opens the card - it is
 * then not closed for the last time - makes a framebuffer of the panel's size, black as the kernel hands it over, names itself
 * and it in HOLD_FILE and waits. This program, stopped while that file names a live holder, puts the holder's framebuffer on the
 * primary plane and the video plane off in one commit and leaves without the console (hold_take()); the next start leaves the
 * console dark while that framebuffer is on the plane (hold_adopt()), and its first picture or page takes the wall in its own
 * commit. A framebuffer belongs to the file that made it but any master may show it, which is how the console's own one is
 * shown under the picture. The holder ends when its framebuffer is on no plane any more; if nobody takes the wall within
 * HOLD_MAX_S, or it is told to stop, it gives the console back first: the console stays the view of last resort. It never takes
 * its framebuffer away while that is shown (hold_give_back()).
 *
 * The console's framebuffer is learnt from the plane (osd_learn()), and after a held restart the plane holds the black one: so
 * the run that learns it writes it into CONSOLE_FB_FILE, and the next start takes it from there, checked against the card.
 * /run/h713-tv-state outlives a stop of the unit (its RuntimeDirectory does not).
 * ------------------------------------------------------------------ */

#define HOLD_FILE	"/run/h713-tv-state/hold"	/* "PID FB": the holder of the wall */
#define CONSOLE_FB_FILE	"/run/h713-tv-state/console-fb"	/* the console's framebuffer, as osd_learn() found it */
#define HOLD_MAX_S	90	/* nobody took the wall: the console after all - above the restart's own budget, its 60 s wait for the
				 * receiver's node and h713-tv's start; a restart that fails stops the holder itself (h713-mips-restart) */
#define HOLD_UNUSED_S	10	/* nobody put the black framebuffer up: no h713-tv was stopped for the restart */

static const char *hold_file = HOLD_FILE;		/* the tests point these elsewhere */
static const char *console_fb_file = CONSOLE_FB_FILE;

/* the holder HOLD_FILE names, if it runs: its PID, and its framebuffer in *fb; 0: none */
static pid_t hold_read(uint32_t *fb)
{
	FILE *f = fopen(hold_file, "r");
	long pid = 0;
	unsigned long id = 0;

	if (!f)
		return 0;
	if (fscanf(f, "%ld %lu", &pid, &id) != 2 || pid <= 0 || !id || kill((pid_t)pid, 0))
		pid = 0;
	fclose(f);
	*fb = (uint32_t)id;

	return (pid_t)pid;
}

/* the framebuffer the primary plane holds, 0: none or not known */
static uint32_t hold_primary_fb(struct display *d)
{
	drmModePlane *p;
	uint32_t fb;

	if (!osd_find_plane(d) || !(p = drmModeGetPlane(d->fd, osd.plane_id)))
		return 0;
	fb = p->fb_id;
	drmModeFreePlane(p);

	return fb;
}

/* osd_learn() found the console's framebuffer: for the start after a held restart (never the holder's black one) */
static void hold_console_note(uint32_t fb)
{
	uint32_t black = 0;
	FILE *f;

	if (!fb || (hold_read(&black) && black == fb) || !(f = fopen(console_fb_file, "w")))
		return;
	fprintf(f, "%u\n", fb);
	fclose(f);
}

/* the way out, while a holder runs: its framebuffer on the primary plane, the video plane off - one commit, the master gone */
static bool hold_take(struct display *d)
{
	drmModeAtomicReq *req;
	uint32_t fb = 0;
	pid_t pid = hold_read(&fb);
	bool ok;

	if (!pid || !osd_find_plane(d) || !display_take_master(d))
		return false;
	req = drmModeAtomicAlloc();
	ok = req && add(req, d, "FB_ID", 0) && add(req, d, "CRTC_ID", 0) && osd_props(req, d, fb, 0) &&
	     !drmModeAtomicCommit(d->fd, req, 0, NULL);
	if (req)
		drmModeAtomicFree(req);
	if (ok)
		under.up = false;	/* the video plane is off: no black frame of a page to take away before the master goes */
	display_release_master(d);
	if (!ok) {
		warn("wall            the black framebuffer %u of PID %d did not go up (%s) -- the console, as without it", fb,
		     (int)pid, strerror(errno));
		return false;
	}
	d->on = d->warped = false;
	info("wall            held black by PID %d (framebuffer %u) for a restart -- the console stays dark", (int)pid, fb);

	return true;
}

/* the console's framebuffer as CONSOLE_FB_FILE names it, if the card knows it, it is not black and it is XRGB8888 of the panel's
 * size; 0 otherwise. GETFB2 hands a root caller a GEM handle per call: closed at once, or every call kept the buffer referenced */
static uint32_t hold_console_known(struct display *d, uint32_t black)
{
	uint32_t con = 0;
	drmModeFB2 *f;
	FILE *cf;
	bool ok;
	int i;

	if ((cf = fopen(console_fb_file, "r"))) {
		if (fscanf(cf, "%u", &con) != 1)
			con = 0;
		fclose(cf);
	}
	f = con && con != black ? drmModeGetFB2(d->fd, con) : NULL;
	ok = f && f->pixel_format == DRM_FORMAT_XRGB8888 && f->width == d->width && f->height == d->height;
	for (i = 0; f && i < 4; i++)
		if (f->handles[i] && (i == 0 || f->handles[i] != f->handles[0]))
			drmCloseBufferHandle(d->fd, f->handles[i]);
	if (f)
		drmModeFreeFB2(f);
	if (!ok)
		warn("wall            the console's framebuffer is not known (%s: %u)", console_fb_file, con);

	return ok ? con : 0;
}

/*
 * fb is the black one of a running holder: the console's framebuffer as CONSOLE_FB_FILE names it, if the card knows it and it is
 * the console's kind (XRGB8888, the panel's size; a page is ARGB8888); 0 otherwise - also when fb is not the holder's. Every
 * look at the plane asks this (osd_learn(): the start, and again at every claim of h713-osd's): the holder's framebuffer taken
 * for the console's went with the holder, and every commit of "the console" after it was refused - the picture never came back,
 * and the run's way out left the CRTC without a plane (HY300PRO-G-EU, 20.10.2026, the first try of this).
 */
static uint32_t hold_console_fb(struct display *d, uint32_t fb)
{
	uint32_t black = 0;

	if (!fb || !hold_read(&black) || black != fb)
		return 0;

	return hold_console_known(d, fb);
}

/* the start, after a held restart: the black framebuffer is on the plane and the console's is known - then no console */
static bool hold_adopt(struct display *d)
{
	uint32_t fb = 0, con;
	pid_t pid = hold_read(&fb);

	if (!pid || hold_primary_fb(d) != fb)
		return false;
	if (!(con = hold_console_fb(d, fb))) {
		warn("wall            held black by PID %d, but the console's framebuffer is not known -- the console", (int)pid);
		return false;
	}
	osd.console_fb = con;
	osd.console_known = true;
	info("wall            held black by PID %d -- no console at the start; the first picture or page takes the wall", (int)pid);

	return true;
}

/* "h713-tv --hold-wall": the holder. Ready (READY=1 to systemd) once HOLD_FILE names it */
static volatile sig_atomic_t hold_stop;

static void hold_signal(int sig)
{
	(void)sig;
	hold_stop = 1;
}

/* the framebuffer is on one of the planes */
static bool hold_shown(int fd, uint32_t fb)
{
	drmModePlaneRes *r = drmModeGetPlaneResources(fd);
	bool on = false;
	unsigned int i;

	for (i = 0; r && i < r->count_planes && !on; i++) {
		drmModePlane *p = drmModeGetPlane(fd, r->planes[i]);

		on = p && p->fb_id == fb;
		if (p)
			drmModeFreePlane(p);
	}
	if (r)
		drmModeFreePlaneResources(r);

	return on;
}

/*
 * The holder ends while its framebuffer is still on a plane (nobody took the wall, or it was told to stop): the console takes the
 * plane first, and only then does the framebuffer go. A framebuffer taken away while shown is taken off its plane by the kernel,
 * and on the primary plane the CRTC goes with it: no plane, no mode, and no h713-tv starts until fbcon is unblanked (HY300PRO-G-EU,
 * 20.10.2026, the state after the first try of this). fbcon repaints when no master holds the card (console_restore()); if one does
 * just then - h713-tv or h713-osd around a commit - the holder takes the master itself for one commit and puts the console's
 * framebuffer up (CONSOLE_FB_FILE, checked against the card). Again every 50 ms until the framebuffer is on no plane: no limit, a
 * master is held around commits only; a line every 10 s while it waits. hold_console_back is console_restore() (the tests count).
 */
static void (*hold_console_back)(void) = console_restore;

static void hold_give_back(struct display *d, uint32_t fb)
{
	uint32_t con = hold_console_known(d, fb);
	unsigned int n;

	for (n = 0; hold_shown(d->fd, fb); n++) {
		drmModeAtomicReq *req;

		if (n % 200 == 0)
			info("hold            the console takes the wall back%s", n ? " -- still waiting: a master holds the card" : "");
		if (n % 20 == 0)
			hold_console_back();
		if (!hold_shown(d->fd, fb))
			break;
		if (con && osd_find_plane(d) && !drmSetMaster(d->fd)) {
			req = drmModeAtomicAlloc();
			if (req && osd_props(req, d, con, 0) && drmModeAtomicCommit(d->fd, req, 0, NULL))
				warn("hold            the console's framebuffer %u did not go up: %s", con, strerror(errno));
			if (req)
				drmModeAtomicFree(req);
			drmDropMaster(d->fd);
			if (!hold_shown(d->fd, fb))
				break;
		}
		usleep(50 * 1000);
	}
}

static void hold_notify(const char *what)
{
	const char *s = getenv("NOTIFY_SOCKET");
	struct sockaddr_un sa = { .sun_family = AF_UNIX };
	size_t n = s ? strlen(s) : 0;
	int fd;

	if (!n || n >= sizeof(sa.sun_path) || (s[0] != '/' && s[0] != '@'))
		return;
	memcpy(sa.sun_path, s, n);
	if (s[0] == '@')
		sa.sun_path[0] = '\0';
	fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
	if (fd < 0)
		return;
	if (sendto(fd, what, strlen(what), 0, (struct sockaddr *)&sa, offsetof(struct sockaddr_un, sun_path) + n) < 0)
		warn("hold            %s to systemd: %s", what, strerror(errno));
	close(fd);
}

static int hold_wall(const char *card)
{
	struct display d = { .fd = -1 };
	struct drm_mode_create_dumb creq = { 0 };
	struct drm_mode_destroy_dumb dreq = { 0 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 }, fb = 0, other = 0;
	char tmp[64];
	struct timespec t0, t;
	bool shown = false, gone = false;
	FILE *f;
	long s;

	signal(SIGTERM, hold_signal);
	signal(SIGINT, hold_signal);
	d.fd = display_open_card(card);
	if (drmSetClientCap(d.fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1))
		fail("universal planes: %s", strerror(errno));
	display_find_crtc(&d);
	/* the first client to open the card becomes its master: given back at once, h713-tv needs it */
	if (drmDropMaster(d.fd) && errno != EINVAL)
		warn("DROP_MASTER: %s", strerror(errno));
	creq.width = d.width;
	creq.height = d.height;
	creq.bpp = 32;
	if (drmIoctl(d.fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq))
		fail("CREATE_DUMB %ux%u: %s", d.width, d.height, strerror(errno));
	handles[0] = creq.handle;
	pitches[0] = creq.pitch;
	if (drmModeAddFB2(d.fd, d.width, d.height, DRM_FORMAT_XRGB8888, handles, pitches, offsets, &fb, 0))
		fail("AddFB2: %s", strerror(errno));
	snprintf(tmp, sizeof(tmp), "%s.%d", hold_file, (int)getpid());
	if (!(f = fopen(tmp, "w")) || fprintf(f, "%d %u\n", (int)getpid(), fb) < 0 || fclose(f) || rename(tmp, hold_file))
		fail("%s: %s", hold_file, strerror(errno));
	info("hold            the wall can be held black: framebuffer %u (%ux%u) for h713-tv's restart", fb, d.width, d.height);
	hold_notify("READY=1");
	clock_gettime(CLOCK_MONOTONIC, &t0);
	for (;;) {
		bool on = hold_shown(d.fd, fb);

		clock_gettime(CLOCK_MONOTONIC, &t);
		s = t.tv_sec - t0.tv_sec;
		if (on && !shown)
			info("hold            the wall is black (framebuffer %u up)", fb);
		shown |= on;
		if ((gone = shown && !on) || hold_stop || (!shown && s >= HOLD_UNUSED_S) || s >= HOLD_MAX_S)
			break;
		usleep(50 * 1000);
	}
	if (gone)
		info("hold            the wall is taken after %ld s -- done", s);
	else if (!shown)
		info("hold            nobody put the black framebuffer up within %ld s -- done", s);
	else {
		info("hold            %s after %ld s with the wall still black -- the console back", hold_stop ? "stopped" : "nobody took the wall", s);
		hold_give_back(&d, fb);
	}
	if (hold_read(&other) == getpid() && unlink(hold_file))
		warn("%s: %s", hold_file, strerror(errno));
	drmModeRmFB(d.fd, fb);
	dreq.handle = creq.handle;
	drmIoctl(d.fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dreq);
	close(d.fd);

	return 0;
}


/* ------------------------------------------------------------------ *
 * The state machine
 * ------------------------------------------------------------------ */

struct opts {
	const char *video;
	const char *card;
	const char *preset;	/* -p; NULL: whatever tv.conf says, else "standard" */
	const char *gamma;	/* DE2 bank file for GAMMA_LUT; "none" leaves the CRTC alone */
	bool gamma_set;	/* -g was given: it wins over h713-pq's own LUT */
	const char *calculator;	/* --calculator, overrides "calculator" */
	const char *data;	/* --data,       overrides "data" */
	const char *input;	/* --input, which input h713-pq is asked about */
	const char *lut;	/* --lut,     where h713-pq writes its curve */
	const char *audio;	/* auto|on|off|none, see enum audio_policy */
	const char *trim;	/* --hdmi-trim, dB <= 0, see audio_trim_parse() */
	bool report_only;
};

/* ------------------------------------------------------------------ *
 * A change in flight
 *
 * QUERY_DV_TIMINGS answers -ENOLCK while the capture geometry and the
 * firmware's record disagree ("not locked yet", 0107): a resolution change
 * is under way. That is neither "no signal" nor a timing to act on -- treating
 * it as the former took the picture down and put it back for every change
 * (doku/nachtlog/S12 A2). Ask again a little later, a bounded number of
 * times, and leave the wall alone meanwhile.
 *
 * This replaces the ring watch of the earlier versions: since 0121 the flip
 * pointers move whether or not the capture writes, so sampling them after an
 * enable measured nothing (0121 commit message, S12 A4).
 * ------------------------------------------------------------------ */

#define RETRY_MS	50
#define RETRY_MAX	40	/* 2 s in all */
#define RETRY_SLOW_MS	500	/* afterwards, while the console is up */

struct retry {
	int fd;			/* one-shot timerfd */
	unsigned int n;		/* attempts so far in this change */
};

static void retry_stop(struct retry *r)
{
	struct itimerspec its;

	memset(&its, 0, sizeof(its));
	if (r->fd >= 0 && timerfd_settime(r->fd, 0, &its, NULL))
		warn("timerfd_settime(off): %s", strerror(errno));
	r->n = 0;
}

static void retry_arm(struct retry *r, unsigned int ms)
{
	struct itimerspec its;

	if (r->fd < 0)
		return;
	memset(&its, 0, sizeof(its));
	its.it_value.tv_sec = ms / 1000;
	its.it_value.tv_nsec = (long)(ms % 1000) * 1000000L;
	if (timerfd_settime(r->fd, 0, &its, NULL))
		warn("timerfd_settime: %s -- the change is looked at again only on the next event",
		     strerror(errno));
}

/* ------------------------------------------------------------------ *
 * Console handback: unblank and show the cursor
 *
 * Measured 08.09.2026: after a run the console came back with the frame
 * buffer blanked (fb0/blank = 4) and the cursor hidden (DECTCEM), so fbcon
 * neither repainted nor blinked -- the wall showed a frozen login prompt.
 * Neither state was set by this program, and the kernel's own blank timer
 * is off (consoleblank = 0); who did it was not found. Since this is the
 * program that takes the panel away and gives it back, it also leaves the
 * console in a usable state: unblanked, cursor visible, blank timer off.
 * Everything here is best effort and says so once when it cannot.
 * ------------------------------------------------------------------ */

#define CONSOLE_TTY	"/dev/tty0"

static void console_restore(void)
{
	static bool complained;
	char unblank = TIOCL_UNBLANKSCREEN;
	static const char seq[] = "\033[?25h\033[9;0]\033[14;0]";
	int fd;

	fd = open(CONSOLE_TTY, O_WRONLY | O_NOCTTY | O_CLOEXEC);
	if (fd < 0) {
		if (!complained)
			warn("%s: %s -- the console is not unblanked", CONSOLE_TTY,
			     strerror(errno));
		complained = true;
		return;
	}
	if (ioctl(fd, TIOCLINUX, &unblank) && !complained) {
		warn("TIOCL_UNBLANKSCREEN: %s", strerror(errno));
		complained = true;
	}
	if (write(fd, seq, sizeof(seq) - 1) != (ssize_t)(sizeof(seq) - 1) &&
	    !complained) {
		warn("%s: cursor sequence not written: %s", CONSOLE_TTY,
		     strerror(errno));
		complained = true;
	}
	close(fd);
	console_keys(true);

	/*
	 * fbcon's own record of the blank state. The unblank above paints and
	 * blinks again, but fb0/blank kept reading 4 (measured); this puts the
	 * bookkeeping where the picture is. Best effort like the rest.
	 */
	fd = open("/sys/class/graphics/fb0/blank", O_WRONLY | O_CLOEXEC);
	if (fd >= 0) {
		if (write(fd, "0", 1) < 0 && !complained) {
			warn("fb0/blank: %s", strerror(errno));
			complained = true;
		}
		close(fd);
	}

	console_login_clean();
}

/*
 * The console's keyboard is off while anything but the console is on the panel - the picture, a warp, an opaque
 * page - and on again with the console (console_restore()). The remote is a keyboard to the kernel (see below), and
 * so is a keyboard on the desktop: with the console's keyboard on, every key typed into Kodi, labwc or the browser
 * reached the hidden login prompt on tty1 as well, an Enter included, and ctrl-alt-del rebooted the box. seatd did
 * this while a compositor had the seat (K_OFF on open, K_UNICODE on close); it no longer manages the VT, so this
 * program, which owns the panel, owns this switch. Programs that read the keys themselves (h713-keys, libinput in
 * cage and labwc) read the input devices, which a VT's keyboard mode does not touch. The first call (the start)
 * puts a keyboard left off by an earlier run back on; the mode before "off" is restored, K_UNICODE if it was
 * unknown. Best effort, said once.
 */
static void console_keys(bool on)
{
	static int state = -1;		/* -1 unknown (the start), 0 on, 1 off */
	static int before = K_UNICODE;
	static bool complained;
	int fd, mode = -1;

	if (state == (on ? 0 : 1))
		return;
	fd = open(CONSOLE_TTY, O_RDWR | O_NOCTTY | O_CLOEXEC);
	if (fd < 0) {
		if (!complained)
			warn("%s: %s -- the console's keyboard is left as it is", CONSOLE_TTY, strerror(errno));
		complained = true;
		return;
	}
	if (ioctl(fd, KDGKBMODE, &mode))
		mode = -1;
	if (!on && mode >= 0 && mode != K_OFF)
		before = mode;
	if (on && state < 0 && mode != K_OFF) {
		state = 0;		/* the start, and it is on: nothing to do */
	} else if (ioctl(fd, KDSKBMODE, on ? before : K_OFF)) {
		if (!complained)
			warn("KDSKBMODE %s: %s -- the console's keyboard is left as it is", on ? "on" : "off", strerror(errno));
		complained = true;
	} else {
		if (on && state < 0)
			info("console         the keyboard was off (an earlier run) -- on again");
		state = on ? 0 : 1;
	}
	close(fd);
}

/*
 * The remote is a keyboard to the kernel as well (sunxi-ir and the BLE remote
 * both hang on the "kbd" handler): arrows and F4..F6 pressed while the HDMI
 * picture is up land as escape sequences in the hidden login prompt on tty1
 * and show the moment the console is back, "hy310 login: ^[[A^[[D" (TODO
 * 2.55, shown 12.10.2026 by injecting KEY_UP and KEY_LEFT). So whenever the
 * console comes back and tty1 still shows the login prompt with something
 * typed behind it, its getty is told to start over -- SIGTERM, getty@tty1
 * restarts on its own -- and the prompt is clean. A tty1 where somebody is
 * logged in (no prompt), or whose prompt is clean, is left alone. The remote
 * stays a keyboard: it will drive a desktop one day, and keeping it off the
 * VT is that desktop's business.
 */
static void console_login_clean(void)
{
	static char screen[256 * 256];
	unsigned char hdr[4];
	const char *row, *p;
	unsigned int rows, cols, y;
	ssize_t n;
	int fd, dirty = -1;

	fd = open("/dev/vcsa1", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return;
	n = read(fd, hdr, sizeof(hdr));
	close(fd);
	if (n != sizeof(hdr))
		return;
	rows = hdr[0];
	cols = hdr[1];
	if (!rows || !cols || rows * cols > sizeof(screen))
		return;
	fd = open("/dev/vcs1", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return;
	n = read(fd, screen, rows * cols);
	close(fd);
	if (n != (ssize_t)(rows * cols))
		return;

	/* the last prompt on the screen, and whether anything stands behind it */
	for (y = 0; y < rows; y++) {
		row = screen + y * cols;
		p = memmem(row, cols, "login:", 6);
		if (!p)
			continue;
		dirty = 0;
		for (p += 6; p < row + cols; p++)
			if (*p != ' ' && *p != '\0')
				dirty = 1;
	}
	if (dirty != 1)
		return;

	/* the getty on tty1 (major 4, minor 1), by its controlling terminal */
	{
		DIR *proc = opendir("/proc");
		struct dirent *de;
		char path[64], stat_line[512], comm[32];
		int tty_nr;

		if (!proc)
			return;
		while ((de = readdir(proc))) {
			FILE *f;
			char *paren;

			if (de->d_name[0] < '1' || de->d_name[0] > '9')
				continue;
			snprintf(path, sizeof(path), "/proc/%s/stat", de->d_name);
			f = fopen(path, "r");
			if (!f)
				continue;
			stat_line[0] = '\0';
			if (!fgets(stat_line, sizeof(stat_line), f)) {
				fclose(f);
				continue;
			}
			fclose(f);
			/* "pid (comm) state ppid pgrp session tty_nr ..." -- comm may hold spaces */
			paren = strrchr(stat_line, ')');
			if (!paren || sscanf(paren + 1, " %*c %*d %*d %*d %d", &tty_nr) != 1)
				continue;
			if (tty_nr != (int)makedev(4, 1))
				continue;
			sscanf(stat_line, "%*d (%31[^)])", comm);
			if (strcmp(comm, "agetty"))
				continue;
			if (!kill((pid_t)atoi(de->d_name), SIGTERM))
				info("console         the login prompt on tty1 carried keystrokes from the remote -- getty restarted");
			break;
		}
		closedir(proc);
	}
}

/* ------------------------------------------------------------------ *
 * Picture controls by name (the V4L2 controls of the capture node)
 * ------------------------------------------------------------------ */

/* "Temporal Noise Reduction" -> "temporal_noise_reduction" */
static void ctrl_key(const char *name, char *out, size_t n)
{
	size_t i, j = 0;

	for (i = 0; name[i] && j + 1 < n; i++) {
		unsigned char c = (unsigned char)name[i];

		if (c == ' ' || c == '-')
			out[j++] = '_';
		else
			out[j++] = (char)tolower(c);
	}
	out[j] = '\0';
}

/* a few short names on top of the kernel's own */
static const struct { const char *short_name; const char *full_name; } ctrl_alias[] = {
	{ "tnr", "temporal_noise_reduction" },
	{ "snr", "spatial_noise_reduction" },
	{ "dci", "dynamic_contrast" },
	{ "black", "black_extension" },
	{ "range", "video_range" },
	{ "mode", "picture_mode" },
	{ NULL, NULL },
};

static bool ctrl_find(int fd, const char *want, struct v4l2_query_ext_ctrl *q)
{
	char key[64], w[64];
	unsigned int i;

	ctrl_key(want, w, sizeof(w));
	for (i = 0; ctrl_alias[i].short_name; i++)
		if (!strcmp(w, ctrl_alias[i].short_name)) {
			snprintf(w, sizeof(w), "%s", ctrl_alias[i].full_name);
			break;
		}

	memset(q, 0, sizeof(*q));
	q->id = V4L2_CTRL_FLAG_NEXT_CTRL;
	while (!ioctl(fd, VIDIOC_QUERY_EXT_CTRL, q)) {
		if (!(q->flags & V4L2_CTRL_FLAG_DISABLED) &&
		    q->type != V4L2_CTRL_TYPE_CTRL_CLASS) {
			ctrl_key(q->name, key, sizeof(key));
			if (!strcmp(key, w))
				return true;
		}
		q->id |= V4L2_CTRL_FLAG_NEXT_CTRL;
	}

	return false;
}

static int ctrl_get(int fd, const struct v4l2_query_ext_ctrl *q, int64_t *val)
{
	struct v4l2_ext_control c = { .id = q->id };
	struct v4l2_ext_controls cs = {
		.which = V4L2_CTRL_ID2WHICH(q->id), .count = 1, .controls = &c,
	};

	if (ioctl(fd, VIDIOC_G_EXT_CTRLS, &cs))
		return -errno;
	*val = q->type == V4L2_CTRL_TYPE_INTEGER64 ? c.value64 : c.value;

	return 0;
}

static int ctrl_set(int fd, const struct v4l2_query_ext_ctrl *q, int64_t val)
{
	struct v4l2_ext_control c = { .id = q->id };
	struct v4l2_ext_controls cs = {
		.which = V4L2_CTRL_ID2WHICH(q->id), .count = 1, .controls = &c,
	};

	if (q->type == V4L2_CTRL_TYPE_INTEGER64)
		c.value64 = val;
	else
		c.value = (int32_t)val;
	if (ioctl(fd, VIDIOC_S_EXT_CTRLS, &cs))
		return -errno;

	return 0;
}

/* the menu text of a value, or NULL for integer controls */
static const char *ctrl_menu_text(int fd, const struct v4l2_query_ext_ctrl *q,
				  int64_t val, char *buf, size_t n)
{
	struct v4l2_querymenu m = { .id = q->id, .index = (uint32_t)val };

	if (q->type != V4L2_CTRL_TYPE_MENU)
		return NULL;
	if (ioctl(fd, VIDIOC_QUERYMENU, &m))
		return NULL;
	snprintf(buf, n, "%s", (const char *)m.name);

	return buf;
}

/* ------------------------------------------------------------------ *
 * The sound: the audio path follows the picture
 *
 * The pixels take the capture ring, the samples take a chain of their own,
 * and none of it runs through this program either:
 *
 *   HDMI-RX --I2S--> MSP-DSP1 --I2SOUT1--> codec I2S input --> DAC --> speaker
 *      |                 |                       |
 *      | patch 0136      | patch 0137            | patch 0135
 *      | three V4L2      | ALSA card             | controls "DAC Source"
 *      | controls        | "hy310hdmi"           | and "I2S Rate"
 *
 * Three drivers own that chain (plan doku/101 packages B, C, D); this
 * program decides only *when* it is switched on, because it is the only
 * place that knows both halves -- whether a picture is standing on the wall
 * and what the source says about its audio. The rule, doku/101 section 1 E:
 *
 *   picture up AND "H713 Audio Present" AND NOT "H713 Audio Compressed"
 *      => "I2S Rate" := the source's rate, "DAC Source" := I2S,
 *         "HDMI Audio Switch" := 1, "HDMI Mute Switch" := 0
 *   anything else
 *      => "HDMI Mute Switch" := 1, "HDMI Audio Switch" := 0,
 *         "DAC Source" := APB
 *
 * Four measured facts shape how that is carried out (S16, 17:55-20:45):
 *
 *  - The DSP's master mute (0x0050/0x0051 = 0x8000, behind "HDMI Mute
 *    Switch") is silent within a sample, while routing and rate changes are
 *    not. So every change of the path happens *behind* the mute: mute,
 *    change, unmute -- never the other way round.
 *  - The codec's sample rate has to follow the source's, and nobody else
 *    does it: with the codec left at 48 kHz a 32 kHz source stayed silent
 *    although the signal was measurably present as far as VOLUME (S16
 *    20:45). A rate change is therefore a short mute, a new "I2S Rate", and
 *    loud again -- not a re-route.
 *  - The DSP has a volume of its own (0x0052/0x0053 in quarter dB, measured:
 *    0xFB00 = -5 dB gave -4.9 dB at the microphone, S16 18:00) and the master
 *    mute above. The mute is the automaton's silence. The volume carries the
 *    listener's slider on the stock curve where the DSP mixes both sources
 *    (kernel 0176); otherwise it is a fixed level match between HDMI and the
 *    box's own tones (0 dB unless --hdmi-trim says otherwise) and the slider
 *    is the *codec's* "DAC Playback Volume", because that one then sits
 *    behind both sources and a volume that changed with the input would be
 *    two volumes (decision 08.09. 22:10; the curve: FB-DSPVOL). "ctl mute"
 *    takes the DSP mute and, where the codec offers a switch, that one too.
 *  - "Present" follows the source's own decisions and can flap while a mode
 *    or a stream changes. The way up is therefore debounced by 100 ms: the
 *    path is set up and stays muted, and only a source that is still there
 *    afterwards is let through. The way *down* is never debounced -- silence
 *    is never worth waiting for.
 *
 * The box's own sounds (plan doku/102, package I). The DAC takes one source,
 * and a PC keeps its HDMI stream open even in silence, so device sounds on
 * the codec's own PCM were inaudible whenever HDMI played. With kernel 0176
 * the MSP card carries a playback PCM of its own (hw:hy310hdmi,0, 48 kHz,
 * S16_LE, stereo) that the DSP mixes into the HDMI audio, and a second mute,
 * "HDMI Input Mute Switch", that silences the HDMI branch alone. Where that
 * control exists this program keeps the DAC on I2S for good and parks the
 * codec at 48 kHz whenever HDMI is silent, so that PCM is audible with a
 * picture, without one and with a silent source; the automaton's silence is
 * the input mute, and the master mute belongs to "ctl mute" alone. Without
 * the control (an older kernel) everything behaves as before.
 *
 * All of this is optional. Without the cards, without their controls or
 * without the capture node's audio status the audio part switches itself
 * off, says why, and the picture does not notice: no ALSA call of this
 * program lies on the way to the wall.
 * ------------------------------------------------------------------ */

/* the names are the binding interface of doku/101 section 2 */
#define AUDIO_MSP_CARD		"hy310hdmi"		/* MSP card, 0137 */
#define AUDIO_CODEC_CARD	"H713 Audio Codec"	/* codec card, 0135 */
#define AUDIO_C_SWITCH		"HDMI Audio Switch"
#define AUDIO_C_VOLUME		"HDMI Playback Volume"
#define AUDIO_C_MUTE		"HDMI Mute Switch"
#define AUDIO_C_INMUTE		"HDMI Input Mute Switch"	/* kernel 0176, optional */
#define AUDIO_C_SOURCE		"DAC Source"
#define AUDIO_C_RATE		"I2S Rate"
#define AUDIO_V_PRESENT		"H713 Audio Present"	/* V4L2, 0136 */
#define AUDIO_V_RATE		"H713 Audio Rate"
#define AUDIO_V_COMPRESSED	"H713 Audio Compressed"

/*
 * The listener's controls on the codec card. The volume is the DAC's own
 * (sun4i-codec, "DAC Playback Volume": 0..63, TLV -73.08..0 dB in 1.16 dB
 * steps on this SoC); the mute is whichever switch the card has: the H713
 * codec has no mixer stage and therefore no "DAC Playback Switch" (0135's
 * comment on 0x314), so its "Line Out Playback Switch" (DAC_AC_DAC_REG
 * 0x310, LINEOUT enables) is the one that exists. Neither is required --
 * without them "ctl volume" says so and the mute is the DSP's alone.
 */
#define AUDIO_C_DACVOL		"DAC Playback Volume"
static const char *const audio_codec_mutes[] = {
	"DAC Playback Switch", "Line Out Playback Switch", NULL,
};

#define AUDIO_SETTLE_MS		100	/* debounce before the sound is let through */
#define AUDIO_POLL_MS		250	/* source poll, only without V4L2_EVENT_CTRL */
#define AUDIO_SEARCH_MS		1000	/* retry while a card is still missing */
#define AUDIO_SEARCH_MAX	30	/* ... this often, then it stays off */
#define AUDIO_TRIM_MIN_DB	-100	/* --hdmi-trim: the DSP volume's floor (doku/101 section 2) */
#define AUDIO_BRIDGE_RATE	"48000"	/* the bridge PCM's fixed rate (kernel 0176) */
#define AUDIO_CURVE_OFF_Q	-512	/* slider 0: the stock curve's off (-128 dB) */

struct alsa_card {
	snd_ctl_t *ctl;
	int index;			/* ALSA card number, for /sys/class/sound */
	char id[32];
	char name[64];
};

enum audio_policy { AUDIO_AUTO, AUDIO_ON, AUDIO_OFF, AUDIO_NONE };
enum audio_state { AUDIO_STILL, AUDIO_SETTLING, AUDIO_LOUD };

struct audio {
	bool enabled;			/* cards and their controls are there */
	bool searching;			/* still looking, see audio_search() */
	unsigned int searched;		/* attempts so far */
	char why[256];			/* why it is off -- journal and ctl status */
	bool write_failed;		/* a control write failed; say it once */

	struct alsa_card msp;
	struct alsa_card codec;

	/* the source, from the capture node's read-only controls (0136) */
	bool have_source;		/* the three controls exist */
	bool events;			/* ... and V4L2_EVENT_CTRL is subscribed */
	struct v4l2_query_ext_ctrl q_present, q_rate, q_compressed;
	bool present, compressed;
	unsigned int rate;

	enum audio_policy policy;
	enum audio_state state;
	unsigned int applied_rate;	/* the rate "I2S Rate" is programmed for */
	long trim_q;			/* --hdmi-trim in quarter dB, <= 0 */
	bool have_dacvol;		/* the codec has AUDIO_C_DACVOL */
	bool have_inmute;		/* the MSP has AUDIO_C_INMUTE: the mixed path */
	bool dsp_stage;			/* the slider's stage is the DSP (= have_inmute) */
	const char *codec_mute;		/* its mute switch, or NULL */
	int volume;			/* 0..100 as last asked for with ctl volume */
	bool volume_set;		/* ... and not yet written (cards were missing) */
	bool mute;			/* ctl mute */
	bool covered;			/* an opaque page hides the picture: the HDMI sound behind the DSP's mute (cover) */

	int settle_fd;			/* one-shot, AUDIO_SETTLE_MS */
	int tick_fd;			/* periodic: card search or source poll */
	unsigned int tick_ms;		/* its period, 0 = disarmed */
};

/* ------------------------------------------------------------------ *
 * libasound, by control name
 *
 * Every access looks the element up by name first. That costs one ioctl per
 * write, which is nothing next to how rarely this happens (a handful of
 * times per source change), and it buys the property that a card which lost
 * a control -- reloaded module, driver built without it -- is an error with
 * a name in it instead of a stale element id writing into the void.
 * ------------------------------------------------------------------ */

static bool alsa_find(struct alsa_card *c, const char *name,
		      snd_ctl_elem_info_t *ei)
{
	snd_ctl_elem_id_t *id;

	if (!c->ctl)
		return false;
	snd_ctl_elem_id_alloca(&id);
	snd_ctl_elem_id_set_interface(id, SND_CTL_ELEM_IFACE_MIXER);
	snd_ctl_elem_id_set_name(id, name);
	snd_ctl_elem_info_set_id(ei, id);

	return snd_ctl_elem_info(c->ctl, ei) == 0;
}

static bool alsa_has(struct alsa_card *c, const char *const *names)
{
	snd_ctl_elem_info_t *ei;
	unsigned int i;

	snd_ctl_elem_info_alloca(&ei);
	for (i = 0; names[i]; i++)
		if (!alsa_find(c, names[i], ei))
			return false;

	return true;
}

/*
 * Write one value -- to every channel of the control, because a stereo
 * switch such as the codec's "Line Out Playback Switch" (SOC_DOUBLE) is
 * written whole, and a value struct with only channel 0 filled in would
 * switch the right channel off. Integer controls are clamped into the
 * range the driver reports: the volume scale of doku/101 section 2 is
 * 0..400, and a driver that ends up with a different one has to silence
 * this program's arithmetic, not the loudspeaker.
 */
static int alsa_write(struct alsa_card *c, const char *name, long v)
{
	snd_ctl_elem_info_t *ei;
	snd_ctl_elem_value_t *ev;
	unsigned int i, n;
	int ret;

	snd_ctl_elem_info_alloca(&ei);
	if (!alsa_find(c, name, ei))
		return -ENOENT;
	n = snd_ctl_elem_info_get_count(ei);

	snd_ctl_elem_value_alloca(&ev);
	snd_ctl_elem_value_set_interface(ev, SND_CTL_ELEM_IFACE_MIXER);
	snd_ctl_elem_value_set_name(ev, name);

	switch (snd_ctl_elem_info_get_type(ei)) {
	case SND_CTL_ELEM_TYPE_BOOLEAN:
		for (i = 0; i < n; i++)
			snd_ctl_elem_value_set_boolean(ev, i, v ? 1 : 0);
		break;
	case SND_CTL_ELEM_TYPE_INTEGER:
		if (v < snd_ctl_elem_info_get_min(ei))
			v = snd_ctl_elem_info_get_min(ei);
		if (v > snd_ctl_elem_info_get_max(ei))
			v = snd_ctl_elem_info_get_max(ei);
		for (i = 0; i < n; i++)
			snd_ctl_elem_value_set_integer(ev, i, v);
		break;
	case SND_CTL_ELEM_TYPE_ENUMERATED:
		for (i = 0; i < n; i++)
			snd_ctl_elem_value_set_enumerated(ev, i, (unsigned int)v);
		break;
	default:
		return -EINVAL;
	}
	ret = snd_ctl_elem_write(c->ctl, ev);

	return ret < 0 ? ret : 0;
}

static int alsa_read(struct alsa_card *c, const char *name, long *out)
{
	snd_ctl_elem_info_t *ei;
	snd_ctl_elem_value_t *ev;
	int ret;

	snd_ctl_elem_info_alloca(&ei);
	if (!alsa_find(c, name, ei))
		return -ENOENT;

	snd_ctl_elem_value_alloca(&ev);
	snd_ctl_elem_value_set_interface(ev, SND_CTL_ELEM_IFACE_MIXER);
	snd_ctl_elem_value_set_name(ev, name);
	ret = snd_ctl_elem_read(c->ctl, ev);
	if (ret < 0)
		return ret;

	switch (snd_ctl_elem_info_get_type(ei)) {
	case SND_CTL_ELEM_TYPE_BOOLEAN:
		*out = snd_ctl_elem_value_get_boolean(ev, 0);
		break;
	case SND_CTL_ELEM_TYPE_INTEGER:
		*out = snd_ctl_elem_value_get_integer(ev, 0);
		break;
	case SND_CTL_ELEM_TYPE_ENUMERATED:
		*out = snd_ctl_elem_value_get_enumerated(ev, 0);
		break;
	default:
		return -EINVAL;
	}

	return 0;
}

/*
 * One control as text, for ctl status: what the card actually holds, not
 * what this program believes it set (S12 R7 -- a status reports, it does not
 * guess).
 */
static void alsa_read_text(struct alsa_card *c, const char *name, char *buf,
			   size_t len)
{
	snd_ctl_elem_info_t *ei;
	long v;
	int ret;

	ret = alsa_read(c, name, &v);
	if (ret) {
		snprintf(buf, len, "?(%s)", strerror(-ret));
		return;
	}
	snd_ctl_elem_info_alloca(&ei);
	if (alsa_find(c, name, ei) &&
	    snd_ctl_elem_info_get_type(ei) == SND_CTL_ELEM_TYPE_ENUMERATED) {
		const char *text;

		snd_ctl_elem_info_set_item(ei, (unsigned int)v);
		text = snd_ctl_elem_info(c->ctl, ei) ? NULL
						    : snd_ctl_elem_info_get_item_name(ei);
		snprintf(buf, len, "%s", text ? text : "?");
		return;
	}
	snprintf(buf, len, "%ld", v);
}

/* the index of an enum item by its text, e.g. "I2S" or "48000" */
static int alsa_enum_index(struct alsa_card *c, const char *name,
			   const char *item, long *out)
{
	snd_ctl_elem_info_t *ei;
	unsigned int i, n;

	snd_ctl_elem_info_alloca(&ei);
	if (!alsa_find(c, name, ei))
		return -ENOENT;
	if (snd_ctl_elem_info_get_type(ei) != SND_CTL_ELEM_TYPE_ENUMERATED)
		return -EINVAL;

	n = snd_ctl_elem_info_get_items(ei);
	for (i = 0; i < n; i++) {
		const char *text;

		snd_ctl_elem_info_set_item(ei, i);
		if (snd_ctl_elem_info(c->ctl, ei))
			continue;
		text = snd_ctl_elem_info_get_item_name(ei);
		if (text && !strcasecmp(text, item)) {
			*out = (long)i;
			return 0;
		}
	}

	return -ENOENT;
}

/*
 * A volume control's TLV and range -- the driver says what its steps mean,
 * this program does not assume it (the codec's DAC counts 1.16 dB steps,
 * the DSP quarter dB). False when the control has no readable TLV.
 */
static bool alsa_tlv(struct alsa_card *c, const char *name, unsigned int *tlv,
		     size_t tlv_size, long *min, long *max)
{
	snd_ctl_elem_info_t *ei;
	snd_ctl_elem_id_t *id;

	snd_ctl_elem_info_alloca(&ei);
	if (!alsa_find(c, name, ei) || !snd_ctl_elem_info_is_tlv_readable(ei) ||
	    snd_ctl_elem_info_get_type(ei) != SND_CTL_ELEM_TYPE_INTEGER)
		return false;
	snd_ctl_elem_id_alloca(&id);
	snd_ctl_elem_info_get_id(ei, id);
	if (snd_ctl_elem_tlv_read(c->ctl, id, tlv, tlv_size) < 0)
		return false;
	*min = snd_ctl_elem_info_get_min(ei);
	*max = snd_ctl_elem_info_get_max(ei);

	return true;
}

/* a raw value of a volume control as 1/100 dB */
static bool alsa_db(struct alsa_card *c, const char *name, long v, long *db)
{
	unsigned int tlv[64];
	long min, max;

	return alsa_tlv(c, name, tlv, sizeof(tlv), &min, &max) &&
	       snd_tlv_convert_to_dB(tlv, min, max, v, db) >= 0;
}

/*
 * 1/100 dB -> the raw value of a volume control: the nearer of the two
 * neighbouring steps, clamped into the control's range; -1 without a TLV.
 */
static long alsa_raw_from_db(struct alsa_card *c, const char *name, long db)
{
	unsigned int tlv[64];
	long min, max, lo, hi, dlo, dhi;

	if (!alsa_tlv(c, name, tlv, sizeof(tlv), &min, &max) ||
	    snd_tlv_convert_from_dB(tlv, min, max, db, &lo, 0) < 0 ||
	    snd_tlv_convert_from_dB(tlv, min, max, db, &hi, 1) < 0 ||
	    snd_tlv_convert_to_dB(tlv, min, max, lo, &dlo) < 0 ||
	    snd_tlv_convert_to_dB(tlv, min, max, hi, &dhi) < 0)
		return -1;

	return labs(dhi - db) < labs(db - dlo) ? hi : lo;
}

/*
 * Find the card that carries a set of controls. The plan fixes the names
 * ("hy310hdmi", "H713 Audio Codec") but not the card *numbers* -- those
 * depend on probe order, exactly as /dev/videoN does. So the name decides
 * when it is there and the controls decide otherwise; a card that has
 * neither is not touched.
 */
static bool alsa_open_card(struct alsa_card *out, const char *want,
			   const char *const *need)
{
	struct alsa_card found = { .ctl = NULL, .index = -1 };
	int card = -1;

	while (!snd_card_next(&card) && card >= 0) {
		struct alsa_card c = { .ctl = NULL, .index = card };
		snd_ctl_card_info_t *ci;
		char hw[16];
		bool wanted;

		snprintf(hw, sizeof(hw), "hw:%d", card);
		if (snd_ctl_open(&c.ctl, hw, 0) < 0)
			continue;
		snd_ctl_card_info_alloca(&ci);
		if (snd_ctl_card_info(c.ctl, ci) || !alsa_has(&c, need)) {
			snd_ctl_close(c.ctl);
			continue;
		}
		snprintf(c.id, sizeof(c.id), "%s", snd_ctl_card_info_get_id(ci));
		snprintf(c.name, sizeof(c.name), "%s",
			 snd_ctl_card_info_get_name(ci));
		wanted = !strcasecmp(c.id, want) || !strcasecmp(c.name, want) ||
			 !strcasecmp(snd_ctl_card_info_get_longname(ci), want);

		if (wanted || !found.ctl) {
			if (found.ctl)
				snd_ctl_close(found.ctl);
			found = c;
			if (wanted)
				break;
		} else {
			snd_ctl_close(c.ctl);
		}
	}
	*out = found;

	return found.ctl != NULL;
}

/*
 * One line of a sysfs attribute of a card's device -- "state" and "levels" of
 * the MSP driver (doku/101 section 2). The card number found above is what
 * makes the path; nothing here knows a platform address.
 */
static bool card_sysfs(const struct alsa_card *c, const char *attr, char *buf,
		       size_t len)
{
	char path[96];
	FILE *f;

	if (c->index < 0)
		return false;
	snprintf(path, sizeof(path), "/sys/class/sound/card%d/device/%s",
		 c->index, attr);
	f = fopen(path, "r");
	if (!f)
		return false;
	if (!fgets(buf, (int)len, f)) {
		fclose(f);
		return false;
	}
	fclose(f);
	buf[strcspn(buf, "\n")] = '\0';

	return true;
}

/* one "key: value" line of a PCM's proc file: the value's first word, no unit */
static void proc_value(const char *line, const char *key, char *dst, size_t len)
{
	size_t k = strlen(key);

	if (strncmp(line, key, k) || (line[k] != ':' && line[k] != ' ') ||
	    !(line = strchr(line + k, ':')))
		return;
	line += strspn(line, ": ");
	snprintf(dst, len, "%.*s", (int)strcspn(line, " \n"), line);
}

/*
 * A card's first playback PCM out of /proc/asound/cardN/pcm0p/sub0: "closed",
 * or its state, the pid that holds it and its hw_params -- what tells a program
 * that claims to play from one that holds the device. A test hands in a copy.
 */
static const char *pcm_state_text(const char *dir, char *buf, size_t len)
{
	static const char *const key[] = { "state", "owner_pid", "rate", "format",
					   "channels", "period_size", "buffer_size" };
	char val[7][16] = { "" }, path[96], line[96];
	unsigned int i, k;
	FILE *f;

	for (i = 0; i < 2; i++) {
		snprintf(path, sizeof(path), "%s/%s", dir, i ? "hw_params" : "status");
		f = fopen(path, "r");
		if (!f)
			break;
		while (fgets(line, sizeof(line), f))
			for (k = 0; k < 7; k++)
				proc_value(line, key[k], val[k], sizeof(val[k]));
		fclose(f);
	}
	if (!val[0][0])		/* no such card, or "closed": nobody holds it */
		snprintf(buf, len, "%s", i ? "closed" : "no PCM");
	else if (!val[2][0])	/* opened, hw_params not set yet */
		snprintf(buf, len, "%s by pid %s, no hw_params yet", val[0], val[1]);
	else
		snprintf(buf, len, "%s by pid %s, %s Hz %s %s ch, period %s of %s frames",
			 val[0], val[1], val[2], val[3], val[4], val[5], val[6]);
	return buf;
}

/* ------------------------------------------------------------------ *
 * The two timers
 *
 * Neither decides anything; they only ask again. The one-shot is the 100 ms
 * debounce. The periodic one stands in where there is no event to wait for:
 * while the cards have not appeared yet (nothing here can be told about
 * that) and while the capture node does not deliver V4L2_EVENT_CTRL. With
 * events and both cards in place it is disarmed, and the sound follows the
 * source the way the picture does -- on an event.
 * ------------------------------------------------------------------ */

static void audio_timer(int fd, unsigned int ms, bool repeat)
{
	struct itimerspec its;

	if (fd < 0)
		return;
	memset(&its, 0, sizeof(its));
	its.it_value.tv_sec = ms / 1000;
	its.it_value.tv_nsec = (long)(ms % 1000) * 1000000L;
	if (repeat)
		its.it_interval = its.it_value;
	if (timerfd_settime(fd, 0, &its, NULL))
		warn("audio           timerfd_settime(%u ms): %s", ms, strerror(errno));
}

static void audio_tick_rearm(struct audio *a)
{
	unsigned int ms = 0;

	if (a->searching)
		ms = AUDIO_SEARCH_MS;
	else if (a->enabled && a->have_source && !a->events)
		ms = AUDIO_POLL_MS;
	if (ms == a->tick_ms)
		return;
	a->tick_ms = ms;
	audio_timer(a->tick_fd, ms, ms != 0);
}

/* ------------------------------------------------------------------ *
 * Setting the path
 * ------------------------------------------------------------------ */

static void audio_put(struct audio *a, struct alsa_card *c, const char *name,
		      long v)
{
	int ret = alsa_write(c, name, v);

	if (!ret) {
		a->write_failed = false;
		return;
	}
	if (!a->write_failed)
		warn("audio           \"%s\" on card %s: %s -- the audio path is not set the way this program reports it",
		     name, c->id, strerror(-ret));
	a->write_failed = true;
}

static void audio_put_enum(struct audio *a, struct alsa_card *c,
			   const char *name, const char *item)
{
	long idx;
	int ret = alsa_enum_index(c, name, item, &idx);

	if (ret) {
		if (!a->write_failed)
			warn("audio           \"%s\" does not know \"%s\" (%s) -- the audio path is not set the way this program reports it",
			     name, item, strerror(-ret));
		a->write_failed = true;
		return;
	}
	audio_put(a, c, name, idx);
}

/* ------------------------------------------------------------------ *
 * The listener's volume: the stock curve on one stage
 *
 * The slider 0..100 runs on the stock curve (FB-DSPVOL): the 101 quarter-dB
 * values of [Volume] volume_curve[00..100] in the stock
 * /vendor/etc/tvconfig/audio_config.ini, which the stock HAL (Set_Volume
 * @0x10194 in audio.primary.ares.so) writes unchanged into the DSP's
 * VOLUME1/2 (0x0052/0x0053): two linear pieces, 1..28 in half-dB steps
 * (-41 .. -27.5 dB), 29..100 in quarter-dB steps (-27.25 .. -9.5 dB), 0 the
 * vendor's off (-128 dB). Its stage is the DSP's "HDMI Playback Volume" (the
 * vendor's) where the DSP mixes the box's own sounds into HDMI (kernel 0176,
 * seen as "HDMI Input Mute Switch"), else the codec's "DAC Playback Volume",
 * because on the older kernel that is where both sources meet (decision
 * 08.09. 22:10); the other stage stays at 0 dB, the DSP also carries the
 * HDMI trim. The card is the owner of the value: this program reads the
 * stage back for every answer (the curve backwards) instead of repeating
 * what it last wrote, so an "amixer" from elsewhere shows up in "ctl status".
 * ------------------------------------------------------------------ */

/*
 * A board's own curve (tv.conf "volume_curve = vendor", 25.10.2026): [Volume] volume_curve[00..100] of the device's own
 * audio_config.ini in the extracted vendor data (the data directory, /etc/h713/tvconfig), where the installer puts it next
 * to the PQ files. A line "volume_curve[NN]=a,b,...," holds the values up to index NN. The HY310's file is the curve above,
 * value for value; the L018's runs to +0.5 dB at 100 (-14.75 dB at 50), and its owner heard the DSP at 0 dB clean (hearing
 * test of 25.10.2026, TODO 4.9e). A value above the stage's top ends there (0 dB in the DSP). Without the file, or with one
 * that is not 101 values, rising from 1 to 100 within -512..120, the curve above stays and the journal says why.
 */
#define AUDIO_CURVE_FILE	"audio_config.ini"

static char *trim(char *s);	/* the tv.conf reader's, below */

static long vendor_curve[101];
static bool vendor_curve_on;

static bool audio_curve_load(const char *dir, char *why, size_t len)
{
	char path[200], line[512];
	bool in_volume = false, have[101] = { false };
	long v[101];
	int i;
	FILE *f;

	snprintf(path, sizeof(path), "%s/%s", dir, AUDIO_CURVE_FILE);
	f = fopen(path, "r");
	if (!f) {
		snprintf(why, len, "%s: %s", path, strerror(errno));
		return false;
	}
	while (fgets(line, sizeof(line), f)) {
		char *p = trim(line), *end;
		long last, vals[101];
		int k = 0;

		if (*p == '[') {
			in_volume = !strncmp(p, "[Volume]", 8);
			continue;
		}
		if (!in_volume || strncmp(p, "volume_curve[", 13))
			continue;
		last = strtol(p + 13, &end, 10);
		if (end == p + 13 || strncmp(end, "]=", 2) || last < 0 || last > 100)
			continue;
		for (p = end + 2; *p && k < 101; ) {
			long x = strtol(p, &end, 10);

			if (end == p)
				break;
			vals[k++] = x;
			p = end + strspn(end, ", \t");
		}
		if (k > last + 1) {
			fclose(f);
			snprintf(why, len, "%s: volume_curve[%ld] holds %d values", path, last, k);
			return false;
		}
		for (i = 0; i < k; i++) {
			v[last - k + 1 + i] = vals[i];
			have[last - k + 1 + i] = true;
		}
	}
	fclose(f);
	for (i = 0; i <= 100; i++) {
		if (!have[i]) {
			snprintf(why, len, "%s: no [Volume] volume_curve value %d", path, i);
			return false;
		}
		if (i && (v[i] < -512 || v[i] > 120 || (i > 1 && v[i] < v[i - 1]))) {
			snprintf(why, len, "%s: volume_curve value %d (%ld) is outside -512..120 or below the one before", path, i, v[i]);
			return false;
		}
	}
	memcpy(vendor_curve, v, sizeof(vendor_curve));
	return true;
}

/* slider -> quarter dB */
static long audio_curve_q(int n)
{
	if (n <= 0)
		return AUDIO_CURVE_OFF_Q;
	if (vendor_curve_on)
		return vendor_curve[n > 100 ? 100 : n];

	return n <= 28 ? 2 * n - 166 : n - 138;
}

/* quarter dB -> the nearest slider position; below 1 (-41 dB) is off */
static int audio_curve_n(long q)
{
	int n;

	if (vendor_curve_on) {
		if (q < vendor_curve[1])
			return 0;
		for (n = 1; n <= 100; n++)
			if (vendor_curve[n] >= q)
				return n > 1 && q - vendor_curve[n - 1] < vendor_curve[n] - q ? n - 1 : n;
		return 100;
	}
	if (q < -164)
		return 0;
	if (q <= -110)
		return (int)((q + 167) / 2);

	return q > -38 ? 100 : (int)(q + 138);
}

/* "0 = the floor, 1 = -41 dB, 50 = -22 dB, 100 = -9.5 dB" on the curve in force */
static const char *audio_curve_text(char *buf, size_t len)
{
	snprintf(buf, len, "0 = the floor, 1 = %.2f dB, 50 = %.2f dB, 100 = %.2f dB%s", audio_curve_q(1) / 4.0,
		 audio_curve_q(50) / 4.0, audio_curve_q(100) / 4.0, vendor_curve_on ? ", the board's own curve" : "");
	return buf;
}

static const char *audio_stage_name(const struct audio *a)
{
	return a->dsp_stage ? AUDIO_C_VOLUME : AUDIO_C_DACVOL;
}

/* the DSP's level: the slider on the DSP stage, else 0 dB; plus the trim */
static long audio_dsp_raw(struct audio *a)
{
	long q = a->dsp_stage ? audio_curve_q(a->volume) : 0;

	return alsa_raw_from_db(&a->msp, AUDIO_C_VOLUME, (q + a->trim_q) * 25);
}

/* the stage read back: the slider it stands for, and its dB (1/100) */
static int audio_volume_read(struct audio *a, long *db)
{
	struct alsa_card *c = a->dsp_stage ? &a->msp : &a->codec;
	long trim = a->dsp_stage ? a->trim_q : 0, v;

	if ((!a->dsp_stage && !a->have_dacvol) ||
	    alsa_read(c, audio_stage_name(a), &v) ||
	    !alsa_db(c, audio_stage_name(a), v, db))
		return -1;
	/* what was asked for, as long as the card still holds it */
	if (alsa_raw_from_db(c, audio_stage_name(a),
			     (audio_curve_q(a->volume) + trim) * 25) == v)
		return a->volume;

	return audio_curve_n((*db + (*db < 0 ? -12 : 12)) / 25 - trim);
}

/* write the last "ctl volume" -- now, or as soon as the cards are there */
static void audio_volume_apply(struct audio *a)
{
	long q = a->dsp_stage ? 0 : audio_curve_q(a->volume), raw;

	raw = audio_dsp_raw(a);
	if (raw >= 0)
		audio_put(a, &a->msp, AUDIO_C_VOLUME, raw);
	raw = a->have_dacvol ? alsa_raw_from_db(&a->codec, AUDIO_C_DACVOL, q * 25) : -1;
	if (raw >= 0)
		audio_put(a, &a->codec, AUDIO_C_DACVOL, raw);
	a->volume_set = false;
}

/* "volume 50 (-22.0 dB)" or, without the control, why not */
static const char *audio_volume_text(struct audio *a, char *buf, size_t len)
{
	long db;
	int n = audio_volume_read(a, &db);

	if (n < 0)
		snprintf(buf, len, "volume without a control (\"%s\" is missing)",
			 audio_stage_name(a));
	else	/* one decimal is what a listener can hear */
		snprintf(buf, len, "volume %d (%s%ld.%ld dB)", n, db < 0 ? "-" : "",
			 labs(db) / 100, (labs(db) % 100) / 10);

	return buf;
}

/* the DSP's level match, as text for the journal and ctl status */
static const char *audio_trim_text(const struct audio *a, char *buf, size_t len)
{
	long q = labs(a->trim_q);

	snprintf(buf, len, "HDMI trim %s%ld.%02ld dB", a->trim_q < 0 ? "-" : "",
		 q / 4, (q % 4) * 25);

	return buf;
}

/*
 * --hdmi-trim DB: a level match for the HDMI path against the box's own
 * tones, 0 dB (the DSP at full scale, the measured reference of S16) down
 * to the DSP volume's floor. Quarter dB is what the control counts, so
 * the text is rounded to that; a comma is accepted as the decimal sign.
 */
static bool audio_trim_parse(const char *text, long *q)
{
	char buf[32], *end;
	double db;
	size_t i;

	for (i = 0; i < sizeof(buf) - 1 && text[i]; i++)
		buf[i] = text[i] == ',' ? '.' : text[i];
	buf[i] = '\0';
	if (text[i] || !buf[0])
		return false;
	db = strtod(buf, &end);
	if (*end || db > 0.0 || db < (double)AUDIO_TRIM_MIN_DB)
		return false;
	*q = (long)(db * 4.0 - 0.5);	/* db <= 0: round half away from zero */
	if (*q < AUDIO_TRIM_MIN_DB * 4)
		*q = AUDIO_TRIM_MIN_DB * 4;

	return true;
}

/* silence, in the order that cannot click: mute, switch off, source away */
/*
 * Quiet. With a picture up the DAC STAYS on I2S: a source whose player closes
 * its stream between two sounds, or changes the rate between two apps, goes
 * "no audio" and comes back a dozen times an evening, and every flip of the
 * DAC's source between I2S and APB was a pop from the box (Marco, 23.09.2026).
 * The DSP mute and the switch are silent; the source only moves back to APB
 * when the picture itself is gone, which is when the box's own tones may want
 * the DAC.
 */
static void audio_silence(struct audio *a, bool picture)
{
	if (a->have_inmute) {
		/*
		 * The mixed path: HDMI goes quiet behind its own mute, the DAC
		 * stays on I2S and the codec is parked at the bridge PCM's rate,
		 * so the box's own sounds keep playing through the DSP.
		 */
		audio_put(a, &a->msp, AUDIO_C_INMUTE, 1);
		audio_put(a, &a->msp, AUDIO_C_SWITCH, 0);
		audio_put_enum(a, &a->codec, AUDIO_C_RATE, AUDIO_BRIDGE_RATE);
		audio_put_enum(a, &a->codec, AUDIO_C_SOURCE, "I2S");
		return;
	}
	audio_put(a, &a->msp, AUDIO_C_MUTE, 1);
	audio_put(a, &a->msp, AUDIO_C_SWITCH, 0);
	if (!picture)
		audio_put_enum(a, &a->codec, AUDIO_C_SOURCE, "APB");
}

/* the mute the automaton hides its changes behind: the branch's own, if there is one */
static const char *audio_auto_mute(const struct audio *a)
{
	return a->have_inmute ? AUDIO_C_INMUTE : AUDIO_C_MUTE;
}

/* the path, still muted: rate first, then the route, then the switch */
static void audio_route(struct audio *a, unsigned int rate)
{
	char text[16];

	audio_put(a, &a->msp, audio_auto_mute(a), 1);
	if (rate) {
		snprintf(text, sizeof(text), "%u", rate);
		audio_put_enum(a, &a->codec, AUDIO_C_RATE, text);
	}
	audio_put_enum(a, &a->codec, AUDIO_C_SOURCE, "I2S");
	audio_put(a, &a->msp, AUDIO_C_SWITCH, 1);
}

/*
 * The DSP's level and the two mutes. The DSP mute is the one place where
 * the automaton's silence and the listener's "ctl mute" meet; the codec's
 * switch, where there is one, follows "ctl mute" alone -- it sits behind
 * the box's own tones as well, which is what a listener's mute is for.
 * Order: whatever goes quiet goes quiet first (DSP mute before the codec
 * switch), whatever opens up opens up last (the DSP mute after the level).
 */
static void audio_level(struct audio *a)
{
	bool quiet = a->mute || a->state != AUDIO_LOUD || a->covered;
	long raw;

	if (quiet)
		audio_put(a, &a->msp, audio_auto_mute(a), 1);
	/*
	 * On the mixed path the master mute is the listener's alone: it sits
	 * behind HDMI and the box's own sounds, which is what "ctl mute" means.
	 */
	if (a->have_inmute)
		audio_put(a, &a->msp, AUDIO_C_MUTE, a->mute);
	if (a->codec_mute)
		audio_put(a, &a->codec, a->codec_mute, !a->mute);
	/* the slider, or 0 dB (the top, doku/101 section 2); the trim below it */
	raw = audio_dsp_raw(a);
	if (raw >= 0)
		audio_put(a, &a->msp, AUDIO_C_VOLUME, raw);
	if (!quiet)
		audio_put(a, &a->msp, audio_auto_mute(a), 0);
	else if (a->have_inmute && a->state == AUDIO_LOUD && !a->covered)
		audio_put(a, &a->msp, AUDIO_C_INMUTE, 0);
}

/*
 * An opaque page covers the picture, or goes (cover): the HDMI sound goes quiet with the picture and comes back with
 * it, behind the automaton's own mute alone - the input mute on the mixed path (the box's own sounds play on), the DSP
 * mute otherwise. Route, rate, switch and the DAC's source stay as they are: nothing that could click, and no debounce
 * on the way back, the source did not change. A path that is not loud is quiet anyway; audio_level() keeps the
 * cover when it gets loud under the page.
 */
static void audio_cover(struct audio *a, bool on)
{
	if (a->covered == on)
		return;
	a->covered = on;
	if (!a->enabled || a->state != AUDIO_LOUD)
		return;
	if (on)
		audio_put(a, &a->msp, audio_auto_mute(a), 1);
	else if (a->have_inmute || !a->mute)	/* the listener's mute is the master mute there, the DSP mute here */
		audio_put(a, &a->msp, audio_auto_mute(a), 0);
	info("audio           %s", on ? "muted: an opaque page covers the picture" : "on again with the picture");
}

/* ------------------------------------------------------------------ *
 * The state machine
 * ------------------------------------------------------------------ */

/* does the codec offer this rate? (32000, 44100, 48000 -- doku/101 section 2) */
static bool audio_rate_known(struct audio *a, unsigned int rate)
{
	char text[16];
	long idx;

	if (!rate)
		return false;
	snprintf(text, sizeof(text), "%u", rate);

	return alsa_enum_index(&a->codec, AUDIO_C_RATE, text, &idx) == 0;
}

/* read the three read-only controls of the capture node (0136) */
static void audio_read_source(struct audio *a, struct capture *cap)
{
	int64_t v;

	if (!a->have_source)
		return;
	if (!ctrl_get(cap->fd, &a->q_present, &v))
		a->present = v != 0;
	if (!ctrl_get(cap->fd, &a->q_rate, &v))
		a->rate = v > 0 ? (unsigned int)v : 0;
	if (!ctrl_get(cap->fd, &a->q_compressed, &v))
		a->compressed = v != 0;
}

/* the rule of doku/101 section 1 E, in one place */
static bool audio_want(const struct audio *a, bool picture)
{
	/*
	 * A Wayland client on the panel: the picture is not the HDMI input's, so neither is the sound.
	 * audio_evaluate() silences it with the picture standing - the HDMI branch behind its own mute, the DAC on I2S,
	 * and the bridge (Kodi's sound) goes on playing.
	 */
	if (warp.claimed && warp.client)
		return false;
	switch (a->policy) {
	case AUDIO_ON:
		return true;
	case AUDIO_OFF:
	case AUDIO_NONE:
		return false;
	case AUDIO_AUTO:
	default:
		return picture && a->have_source && a->present && !a->compressed;
	}
}

/* which of the reasons it was -- the journal line has to name one */
static const char *audio_why_quiet(const struct audio *a, bool picture)
{
	if (warp.claimed && warp.client)
		return "a Wayland client is on the panel";
	if (a->policy == AUDIO_OFF)
		return "ctl audio off";
	if (!a->have_source)
		return "the capture node reports no audio status";
	if (!picture)
		return "no picture";
	if (!a->present)
		return "the source sends no audio";
	if (a->compressed)
		return "the source sends no PCM (a bitstream)";

	return "\"I2S Rate\" does not know the source rate";
}

static void audio_evaluate(struct audio *a, struct capture *cap, bool picture);

/*
 * The debounce is over: the source was there 100 ms ago, and the path has
 * stood muted since. Ask once more -- a source that flapped in between never
 * becomes audible -- and only then let the sound through.
 */
static void audio_settled(struct audio *a, struct capture *cap, bool picture)
{
	char vol[64], trim[40];

	if (!a->enabled || a->state != AUDIO_SETTLING)
		return;
	audio_read_source(a, cap);
	if (!audio_want(a, picture) ||
	    (a->policy == AUDIO_AUTO && !audio_rate_known(a, a->rate))) {
		audio_evaluate(a, cap, picture);
		return;
	}
	a->state = AUDIO_LOUD;
	audio_level(a);
	if (a->applied_rate)
		info("audio           on, %u Hz, %s, %s%s", a->applied_rate,
		     audio_volume_text(a, vol, sizeof(vol)),
		     audio_trim_text(a, trim, sizeof(trim)),
		     a->mute ? ", muted (ctl mute)" : "");
	else
		info("audio           on, rate unchanged, %s, %s%s",
		     audio_volume_text(a, vol, sizeof(vol)),
		     audio_trim_text(a, trim, sizeof(trim)),
		     a->mute ? ", muted (ctl mute)" : "");
}

/*
 * Called after every decision about the picture, on every audio event of the
 * capture node and after every ctl command that touches the sound. It is the
 * only writer of the path, so "what is set" and "what this program reports"
 * cannot drift apart.
 */
static void audio_evaluate(struct audio *a, struct capture *cap, bool picture)
{
	unsigned int rate;

	if (!a->enabled)
		return;
	audio_read_source(a, cap);

	if (!audio_want(a, picture) ||
	    (a->policy == AUDIO_AUTO && !audio_rate_known(a, a->rate))) {
		if (a->state != AUDIO_STILL) {
			audio_silence(a, picture && a->have_source);
			a->state = AUDIO_STILL;
			a->applied_rate = 0;
			audio_timer(a->settle_fd, 0, false);
			info("audio           silent (%s)", audio_why_quiet(a, picture));
		}
		return;
	}

	/*
	 * "ctl audio on" can arrive before the source has said anything; the
	 * codec then keeps the rate it has and the next event corrects it.
	 */
	rate = a->rate ? a->rate : a->applied_rate;
	if (a->state == AUDIO_LOUD && rate == a->applied_rate)
		return;				/* nothing to do */

	if (a->state == AUDIO_LOUD)
		info("audio           rate change %u -> %u Hz, briefly silent",
		     a->applied_rate, rate);
	else if (a->state == AUDIO_STILL && rate)
		info("audio           source there, %u Hz -- path on, %d ms of debounce",
		     rate, AUDIO_SETTLE_MS);
	else if (a->state == AUDIO_STILL)
		info("audio           path on, rate unknown (the codec keeps its own) -- %d ms of debounce",
		     AUDIO_SETTLE_MS);

	audio_route(a, rate);
	a->applied_rate = rate;
	a->state = AUDIO_SETTLING;
	audio_timer(a->settle_fd, AUDIO_SETTLE_MS, false);
}

/* ------------------------------------------------------------------ *
 * Finding the pieces
 * ------------------------------------------------------------------ */

static const char *const audio_msp_ctls[] = {
	AUDIO_C_SWITCH, AUDIO_C_VOLUME, AUDIO_C_MUTE, NULL,
};
static const char *const audio_codec_ctls[] = {
	AUDIO_C_SOURCE, AUDIO_C_RATE, NULL,
};

/*
 * Both cards, or none. Volume without a route makes no sound, and a route
 * without a mute cannot be switched off quietly, so half a chain is not a
 * chain: it is named and switched off.
 */
static bool audio_search(struct audio *a)
{
	bool msp, codec;

	msp = alsa_open_card(&a->msp, AUDIO_MSP_CARD, audio_msp_ctls);
	codec = alsa_open_card(&a->codec, AUDIO_CODEC_CARD, audio_codec_ctls);
	if (msp && codec) {
		static const char *const dacvol[] = { AUDIO_C_DACVOL, NULL };
		snd_ctl_elem_info_t *ei;
		unsigned int i;
		long db;
		int n;

		static const char *const inmute[] = { AUDIO_C_INMUTE, NULL };

		a->enabled = true;
		a->searching = false;
		a->why[0] = '\0';
		/* the listener's two controls are welcome, not required */
		a->have_dacvol = alsa_has(&a->codec, dacvol);
		a->have_inmute = alsa_has(&a->msp, inmute);
		a->codec_mute = NULL;
		snd_ctl_elem_info_alloca(&ei);
		for (i = 0; audio_codec_mutes[i] && !a->codec_mute; i++)
			if (alsa_find(&a->codec, audio_codec_mutes[i], ei))
				a->codec_mute = audio_codec_mutes[i];
		/*
		 * The mixed path starts parked: HDMI muted at its input, DAC on
		 * I2S, codec at 48 kHz -- the box's own sounds are audible from
		 * this moment, whether a picture ever comes or not.
		 */
		if (a->have_inmute) {
			audio_silence(a, false);
			/*
			 * The master mute is ours alone on this path, and alsactl may
			 * have restored the old automaton's exit state (muted): set it
			 * to what the listener asked, or the box's sounds stay silent
			 * until an HDMI source has played once (deep review F4).
			 */
			audio_put(a, &a->msp, AUDIO_C_MUTE, a->mute);
		}
		/* the slider's stage: the DSP where it mixes the box's sounds */
		a->dsp_stage = a->have_inmute;
		/*
		 * A volume or mute asked for while the cards were missing is
		 * owed; otherwise the slider starts where its stage stands.
		 */
		if (a->volume_set)
			audio_volume_apply(a);
		else if ((n = audio_volume_read(a, &db)) >= 0) {
			a->volume = n;
			/*
			 * A stage above the curve's top (0 dB at boot, or a level the
			 * old automaton left and alsactl restored) is put onto the
			 * curve, else the box plays 9.5 dB louder than the slider's
			 * maximum until the first change (deep review F3).
			 */
			if (db > (audio_curve_q(100) + (a->dsp_stage ? a->trim_q : 0)) * 25 + 12)
				audio_volume_apply(a);
		}
		if (a->mute)
			audio_level(a);
		return true;
	}
	if (msp)
		snd_ctl_close(a->msp.ctl);
	if (codec)
		snd_ctl_close(a->codec.ctl);
	memset(&a->msp, 0, sizeof(a->msp));
	memset(&a->codec, 0, sizeof(a->codec));
	a->msp.index = -1;
	a->codec.index = -1;
	a->have_dacvol = false;
	a->have_inmute = false;
	a->dsp_stage = false;
	a->codec_mute = NULL;
	a->enabled = false;
	snprintf(a->why, sizeof(a->why),
		 "missing: %s%s%s (aplay -l shows the cards, amixer -c N contents their controls)",
		 msp ? "" : "the card \"" AUDIO_MSP_CARD "\" with \"" AUDIO_C_SWITCH "\"/\"" AUDIO_C_VOLUME "\"/\"" AUDIO_C_MUTE "\" (kernel 0137)",
		 !msp && !codec ? " and " : "",
		 codec ? "" : "the card \"" AUDIO_CODEC_CARD "\" with \"" AUDIO_C_SOURCE "\"/\"" AUDIO_C_RATE "\" (kernel 0135)");

	return false;
}

/*
 * The three read-only controls of the capture node, and their events. Losing
 * them costs the automatic mode, not the sound: "ctl audio on" still sets
 * the path by hand, which is what one wants on a kernel without 0136.
 */
static void audio_open_source(struct audio *a, struct capture *cap)
{
	struct v4l2_event_subscription sub;
	uint32_t ids[3];
	unsigned int i;

	a->have_source = ctrl_find(cap->fd, AUDIO_V_PRESENT, &a->q_present) &&
			 ctrl_find(cap->fd, AUDIO_V_RATE, &a->q_rate) &&
			 ctrl_find(cap->fd, AUDIO_V_COMPRESSED, &a->q_compressed);
	if (!a->have_source) {
		warn("audio           the capture node lacks \"%s\"/\"%s\"/\"%s\" (kernel 0136) -- no automatic mode; \"h713-tv ctl audio on\" sets the path by hand",
		     AUDIO_V_PRESENT, AUDIO_V_RATE, AUDIO_V_COMPRESSED);
		return;
	}

	ids[0] = a->q_present.id;
	ids[1] = a->q_rate.id;
	ids[2] = a->q_compressed.id;
	a->events = true;
	for (i = 0; i < 3; i++) {
		memset(&sub, 0, sizeof(sub));
		sub.type = V4L2_EVENT_CTRL;
		sub.id = ids[i];
		if (ioctl(cap->fd, VIDIOC_SUBSCRIBE_EVENT, &sub))
			a->events = false;
	}
	if (!a->events)
		warn("audio           SUBSCRIBE_EVENT(CTRL) refused: %s -- the audio status is polled every %d ms",
		     strerror(errno), AUDIO_POLL_MS);
}

/*
 * There is no event for a card appearing, and the order is not guaranteed:
 * this program is started by udev when the *capture* device shows up, while
 * the MSP driver boots its island and loads the DSP firmware on its own
 * schedule. So the search is repeated, at a stated rate and a stated number
 * of times, and then it stops for good -- a bounded wait with a reason, not
 * a loop with a hope.
 */
/*
 * "ctl mute" outlives this program, not the boot. The listener's mute was a variable here, and this program is
 * restarted behind the listener's back: after every standby that parked the display MIPS (h713-mips-restart), by
 * the rescue, after a crash - and came back loud (16.10.2026: muted, standby, woken, the box played again). So the
 * mute is kept in MUTE_FILE, on the tmpfs: a restart finds it, a cold start does not, and after switching the box
 * on it is audible, as decided. Not in the unit's RuntimeDirectory, which systemd empties at every stop; the
 * directory comes from tmpfiles.d (h713-tv.tmpfiles), the unit makes it writable (ReadWritePaths=). Without it the
 * mute is this run's alone, as before, and said once.
 */
#define MUTE_FILE	"/run/h713-tv-state/mute"

static bool mute_kept(void)
{
	char word[8] = "";
	FILE *f = fopen(MUTE_FILE, "r");

	if (!f)
		return false;
	if (!fgets(word, sizeof(word), f))
		word[0] = '\0';
	fclose(f);

	return !strncmp(word, "on", 2);
}

static void mute_keep(bool on)
{
	static bool complained;
	FILE *f = fopen(MUTE_FILE ".new", "w");
	bool ok = f && fputs(on ? "on\n" : "off\n", f) >= 0;

	if (f && fclose(f))
		ok = false;
	if (ok && rename(MUTE_FILE ".new", MUTE_FILE))
		ok = false;
	if (!ok && !complained)
		warn("%s: %s -- the mute is not kept over a restart of this program", MUTE_FILE, strerror(errno));
	complained |= !ok;
}

static void audio_open(struct audio *a, struct capture *cap,
		       enum audio_policy policy)
{
	a->policy = policy;
	a->state = AUDIO_STILL;
	a->msp.index = -1;
	a->codec.index = -1;
	a->settle_fd = -1;
	a->tick_fd = -1;
	if (policy == AUDIO_NONE) {
		snprintf(a->why, sizeof(a->why),
			 "-a none: the audio is not touched");
		info("audio           off (-a none) -- no ALSA card is opened");
		return;
	}

	a->settle_fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	a->tick_fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (a->settle_fd < 0 || a->tick_fd < 0)
		fail("timerfd_create for the audio: %s", strerror(errno));

	/* before the cards: audio_search() puts the mute where the listener left it */
	a->mute = mute_kept();
	if (a->mute)
		info("audio           ctl mute on -- kept from the run before (%s)", MUTE_FILE);
	audio_open_source(a, cap);
	a->searching = true;
	a->searched = 1;
	if (audio_search(a)) {
		char vol[64], trim[40];

		audio_read_source(a, cap);
		info("audio           %s (card %d) + %s (card %d), %s, %s, %s, mute switch %s, %s",
		     a->msp.id, a->msp.index, a->codec.name, a->codec.index,
		     !a->have_source ? "without source status" :
				       a->events ? "events" : "polling",
		     audio_volume_text(a, vol, sizeof(vol)),
		     audio_trim_text(a, trim, sizeof(trim)),
		     a->codec_mute ? a->codec_mute : "in the DSP only",
		     policy == AUDIO_ON ? "forced on" :
		     policy == AUDIO_OFF ? "forced off" : "follows the picture");
	} else {
		info("audio           no cards yet: %s", a->why);
	}
	audio_tick_rearm(a);
}

/* the periodic timer fired: look for the cards, or ask the source again */
static void audio_tick(struct audio *a, struct capture *cap, bool picture)
{
	if (a->searching) {
		a->searched++;
		if (audio_search(a))
			info("audio           %s (card %d) + %s (card %d), found on attempt %u",
			     a->msp.id, a->msp.index, a->codec.name,
			     a->codec.index, a->searched);
		else if (a->searched > AUDIO_SEARCH_MAX)
			a->searching = false;
		if (!a->searching && !a->enabled)
			warn("audio           stays off after %u attempts in %u s: %s",
			     a->searched, a->searched * AUDIO_SEARCH_MS / 1000,
			     a->why);
		audio_tick_rearm(a);
	}
	audio_evaluate(a, cap, picture);
}

/*
 * Every way out is the same way out here too: the sound goes before the
 * process does. A "systemctl stop" must no more leave a tone in the room
 * than it leaves a still frame on the wall.
 */
static void audio_close(struct audio *a)
{
	if (a->enabled) {
		audio_silence(a, false);
		a->state = AUDIO_STILL;
		/*
		 * A "ctl mute" is this program's, not the box's: it does not
		 * outlive the process on the codec or in the DSP, or the next
		 * aplay would be silent for a reason nobody can see any more.
		 * On the mixed path the DAC stays on I2S: the DSP keeps mixing
		 * without this program, and hw:hy310hdmi,0 keeps playing.
		 */
		if (a->mute && a->codec_mute)
			audio_put(a, &a->codec, a->codec_mute, 1);
		if (a->mute && a->have_inmute)
			audio_put(a, &a->msp, AUDIO_C_MUTE, 0);
	}
	if (a->msp.ctl)
		snd_ctl_close(a->msp.ctl);
	if (a->codec.ctl)
		snd_ctl_close(a->codec.ctl);
	a->msp.ctl = NULL;
	a->codec.ctl = NULL;
	a->enabled = false;
	if (a->settle_fd >= 0)
		close(a->settle_fd);
	if (a->tick_fd >= 0)
		close(a->tick_fd);
	a->settle_fd = -1;
	a->tick_fd = -1;
	/* libasound keeps its parsed configuration in a global; give it back */
	snd_config_update_free_global();
}

/* a name for ctl status and the journal */
static const char *audio_state_text(const struct audio *a)
{
	switch (a->state) {
	case AUDIO_LOUD:
		return "on";
	case AUDIO_SETTLING:
		return "debounce";
	case AUDIO_STILL:
	default:
		return "silent";
	}
}

static const char *audio_policy_text(const struct audio *a)
{
	switch (a->policy) {
	case AUDIO_ON:
		return "on";
	case AUDIO_OFF:
		return "off";
	case AUDIO_NONE:
		return "none";
	case AUDIO_AUTO:
	default:
		return "auto";
	}
}

static bool audio_policy_parse(const char *text, enum audio_policy *p)
{
	if (!strcasecmp(text, "auto"))
		*p = AUDIO_AUTO;
	else if (!strcasecmp(text, "on") || !strcasecmp(text, "an"))
		*p = AUDIO_ON;
	else if (!strcasecmp(text, "off") || !strcasecmp(text, "aus"))
		*p = AUDIO_OFF;
	else if (!strcasecmp(text, "none"))
		*p = AUDIO_NONE;
	else
		return false;

	return true;
}

/* ------------------------------------------------------------------ *
 * The control socket
 *
 * One line in, a few lines out, connection closed. Lines start with "ok"
 * or "error", so the client's exit code is decided by the first word.
 * ------------------------------------------------------------------ */

#define GAMMA_FILE	"/usr/local/share/h713-tv/gamma-standard.bin"
#define CTL_SOCKET	"/run/h713-tv/ctl"
#define CTL_MAXLINE	512

enum policy { POLICY_AUTO, POLICY_OFF };
/* what the panel shows: the HDMI input, a Wayland client through h713-warp's server, or
 * the client while there is one and the input otherwise. "ctl source" at run time, "source =" in tv.conf at the start. */
enum source { SOURCE_HDMI, SOURCE_CLIENT, SOURCE_AUTO };
static const char *const source_name[] = { "hdmi", "client", "auto" };

static int source_by_name(const char *w)
{
	int i;

	for (i = 0; i < 3; i++)
		if (w && !strcasecmp(w, source_name[i]))
			return i;
	return -1;
}

/* ------------------------------------------------------------------ *
 * The start mode, and the mode last set: /etc/h713/tv.conf
 *
 * Until 11.09.2026 every start was an "auto" start (doku/60, Marco 09.09.):
 * there was no way to come up on the console and switch to the HDMI input
 * on purpose, and an "off" given over the socket did not survive a restart.
 * Both are settings of the kind a television keeps.
 *
 * Two files, two jobs. Plan 107 section 8 keeps /etc/h713/tvconfig for the
 * directory of the extracted PQ files; the service configuration is
 *
 *   /etc/h713/tv.conf          read once at start, "key = value", # comments
 *       start = auto            picture follows the signal (as without the file)
 *       start = manual          console until "ctl on" or "ctl auto"
 *       start = last            the mode last set with ctl; auto when none is known
 *       state = PATH | none     where the last mode is kept; none = do not keep
 *       preset = NAME|last      which picture preset to come up with (11.09.)
 *       data = DIR | none       the extracted vendor data; none = do not use it
 *       calculator = PATH|none  h713-pq; none = do not compute anything
 *       edid = block0 | block1  which half of the EDID file port 0 serves
 *                               (FB-EDID); absent: the driver's default, block 0
 *       edid_prefer = file | panel  file (the default since kernel 0255, doku/200):
 *                               the file's order as it is, 1080p first on every
 *                               board; panel: a panel smaller than the file's
 *                               first detailed timing gets its own CTA timing put
 *                               first, so a source that follows the EDID sends the
 *                               panel's resolution (doku/198) - the answer of
 *                               11.10. midday, before the capture slot came from
 *                               the capture's own index and 1080p60 on a 720p
 *                               panel was shown frame for frame
 *       source = hdmi | client | auto  what the panel shows at the start: the HDMI
 *                               input (the default), a Wayland client drawn by h713-warp, or
 *                               the client while there is one; "ctl source" changes it until
 *                               the next start
 *       volume_curve = builtin | vendor  the volume slider's curve: the HY310's (the
 *                               default), or the device's own from audio_config.ini in the
 *                               data directory (the L018's board sets it, 25.10.2026)
 *
 * The keys are the file format, and since v0.8-beta they speak English like
 * the values. Their German spellings ("zustand", "daten", "rechner") and the
 * value words ("manuell", "zuletzt") are still accepted without a warning. The
 * same holds for the two state files below: /var/lib/h713-tv/modus and its
 * sibling "werte" keep their names and their content, because renaming
 * either would throw away what a device running an older release has
 * saved -- the mode it came up in, and the sliders somebody set by hand.
 *
 *   /var/lib/h713-tv/modus     one word, "auto" or "off". Written when a ctl
 *       command changes the mode and only then -- the eMMC is not a place for
 *       idle writes (plan 107 section 4). Under /var and not /etc because it
 *       is state, not configuration, and not in the journal because the
 *       journal is volatile here. The unit hands the directory over with
 *       StateDirectory=, which is what makes it writable under
 *       ProtectSystem=strict.
 *
 * No tv.conf: exactly the behaviour of before. Unknown keys and values are
 * named in the journal and ignored, so a typo does not turn into a silent
 * "auto".
 * ------------------------------------------------------------------ */

#define CONF_FILE	"/etc/h713/tv.conf"
#define STATE_FILE	"/var/lib/h713-tv/modus"
/* the values kept by "ctl save", a sibling of the mode file (plan 113 A.4) */
#define SAVED_NAME	"werte"

/* h713-pq and what it is asked about; see "The picture values" below */
#define PQ_BIN		"/usr/local/bin/h713-pq"
#define PQ_DATA	"/etc/h713/tvconfig"
#define PQ_INPUT	"HDMI1"
#define PQ_LUT		"/run/h713-tv/gamma-laufzeit.bin"

/* the board's own gamma curve; see "The gamma curve of this board" below */
#define BOARD_FILE	"/etc/h713/board"
#define DT_COMPATIBLE	"/proc/device-tree/compatible"
#define TSE_DIR	"/boot/mips"
#define TSE_SLOTS	"/run/h713-tv/gamma-slots.bin"

enum start_mode { START_AUTO, START_MANUAL, START_LAST };

struct conf {
	const char *path;	/* -C; CONF_FILE by default */
	bool present;		/* the file was there and has been read */
	enum start_mode start;
	bool keep;		/* state != none */
	char state_path[200];
	char saved_path[208];	/* <dirname(state_path)>/werte, "" when not kept */
	char preset[32];	/* preset = NAME | last; "" = not said here */
	char data[160];	/* data = DIR; "none" = do not use vendor data */
	char calculator[160];	/* calculator = PATH; "none" = do not compute */
	int edid;		/* edid = block0 | block1; -1 = not said */
	bool edid_panel;	/* edid_prefer = panel (true) | file */
	int source;		/* source = hdmi | client | auto (enum source) */
	bool volume_vendor;	/* volume_curve = vendor (true) | builtin */
	char input[24];	/* --input; the input h713-pq is asked about */
	char lut[160];		/* where h713-pq is told to write the LUT */
};

/* <dirname(state_path)>/werte -- the two files live together or not at all */
static void conf_saved_path(struct conf *c)
{
	char dir[200], *slash;

	c->saved_path[0] = '\0';
	if (!c->keep)
		return;
	snprintf(dir, sizeof(dir), "%s", c->state_path);
	slash = strrchr(dir, '/');
	if (!slash || slash == dir)
		return;
	*slash = '\0';
	snprintf(c->saved_path, sizeof(c->saved_path), "%s/%s", dir, SAVED_NAME);
}

static const char *start_mode_text(enum start_mode m)
{
	return m == START_MANUAL ? "manual" : m == START_LAST ? "last" : "auto";
}

static char *trim(char *s)
{
	size_t n;

	while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')
		s++;
	n = strlen(s);
	while (n && (s[n - 1] == ' ' || s[n - 1] == '\t' || s[n - 1] == '\r' ||
		     s[n - 1] == '\n'))
		s[--n] = '\0';

	return s;
}

static void conf_read(struct conf *c)
{
	char line[256];
	unsigned int n = 0;
	FILE *f;

	c->present = false;
	c->start = START_AUTO;
	c->keep = true;
	snprintf(c->state_path, sizeof(c->state_path), "%s", STATE_FILE);
	c->preset[0] = '\0';
	c->edid = -1;
	c->edid_panel = false;
	c->source = SOURCE_HDMI;
	c->volume_vendor = false;
	snprintf(c->data, sizeof(c->data), "%s", PQ_DATA);
	snprintf(c->calculator, sizeof(c->calculator), "%s", PQ_BIN);
	snprintf(c->input, sizeof(c->input), "%s", PQ_INPUT);
	snprintf(c->lut, sizeof(c->lut), "%s", PQ_LUT);

	f = fopen(c->path, "r");
	if (!f) {
		/* a missing file is the documented default; anything else is worth a line */
		if (errno != ENOENT)
			warn("%s: %s -- the defaults apply (start = auto)", c->path,
			     strerror(errno));
		conf_saved_path(c);
		return;
	}
	c->present = true;
	while (fgets(line, sizeof(line), f)) {
		char *key, *val, *hash;

		n++;
		hash = strchr(line, '#');
		if (hash)
			*hash = '\0';
		key = trim(line);
		if (!*key)
			continue;
		val = strpbrk(key, "= \t");
		if (!val) {
			warn("%s:%u: \"%s\" without a value -- ignored", c->path, n, key);
			continue;
		}
		*val++ = '\0';
		while (*val == ' ' || *val == '\t' || *val == '=')
			val++;
		val = trim(val);
		if (!strcasecmp(key, "start")) {
			if (!strcasecmp(val, "auto"))
				c->start = START_AUTO;
			/*
			 * "manuell" and "zuletzt" are the words this file used
			 * before the tools spoke English. They stay accepted,
			 * without a warning: a device may carry an older
			 * tv.conf, and a start mode that silently fell back to
			 * "auto" would be a picture nobody asked for.
			 */
			else if (!strcasecmp(val, "manual") || !strcasecmp(val, "manuell"))
				c->start = START_MANUAL;
			else if (!strcasecmp(val, "last") || !strcasecmp(val, "zuletzt"))
				c->start = START_LAST;
			else
				warn("%s:%u: start = \"%s\" unknown (auto manual last) -- auto",
				     c->path, n, val);
		} else if (!strcasecmp(key, "state") ||
			   !strcasecmp(key, "zustand")) {	/* GERMAN ALIAS */
			if (!strcasecmp(val, "none") || !strcasecmp(val, "keiner") ||
			    !strcasecmp(val, "nein"))
				c->keep = false;
			else if (*val != '/' || strlen(val) >= sizeof(c->state_path) - 8)
				warn("%s:%u: %s = \"%s\" is not an absolute path (or too long) -- default %s",
				     c->path, n, key, val, STATE_FILE);
			else
				snprintf(c->state_path, sizeof(c->state_path), "%s", val);
		} else if (!strcasecmp(key, "preset")) {
			/*
			 * Only the length is checked here. Whether the name
			 * exists cannot be decided yet: which presets there
			 * are depends on the vendor data, which is read after
			 * this file (plan 113 A.5). An unknown name is caught
			 * where the preset is applied, and falls back there.
			 */
			if (strlen(val) >= sizeof(c->preset))
				warn("%s:%u: preset = \"%s\" is too long -- ignored",
				     c->path, n, val);
			else
				snprintf(c->preset, sizeof(c->preset), "%s", val);
		} else if (!strcasecmp(key, "data") ||
			   !strcasecmp(key, "daten")) {	/* GERMAN ALIAS */
			if (strlen(val) >= sizeof(c->data))
				warn("%s:%u: %s = \"%s\" is too long -- default %s",
				     c->path, n, key, val, PQ_DATA);
			else
				snprintf(c->data, sizeof(c->data), "%s", val);
		} else if (!strcasecmp(key, "calculator") ||
			   !strcasecmp(key, "rechner")) {	/* GERMAN ALIAS */
			if (strlen(val) >= sizeof(c->calculator))
				warn("%s:%u: %s = \"%s\" is too long -- default %s",
				     c->path, n, key, val, PQ_BIN);
			else
				snprintf(c->calculator, sizeof(c->calculator), "%s", val);
		} else if (!strcasecmp(key, "edid")) {
			if (!strcasecmp(val, "block0") || !strcmp(val, "0"))
				c->edid = 0;
			else if (!strcasecmp(val, "block1") || !strcmp(val, "1"))
				c->edid = 1;
			else
				warn("%s:%u: edid = \"%s\" unknown (block0 block1) -- the driver's default stays",
				     c->path, n, val);
		} else if (!strcasecmp(key, "edid_prefer")) {
			if (!strcasecmp(val, "panel"))
				c->edid_panel = true;
			else if (!strcasecmp(val, "file"))
				c->edid_panel = false;
			else
				warn("%s:%u: edid_prefer = \"%s\" unknown (panel file) -- panel stays",
				     c->path, n, val);
		} else if (!strcasecmp(key, "source")) {
			if (source_by_name(val) >= 0)
				c->source = source_by_name(val);
			else
				warn("%s:%u: source = \"%s\" unknown (hdmi client auto) -- hdmi stays",
				     c->path, n, val);
		} else if (!strcasecmp(key, "volume_curve")) {
			if (!strcasecmp(val, "vendor"))
				c->volume_vendor = true;
			else if (!strcasecmp(val, "builtin"))
				c->volume_vendor = false;
			else
				warn("%s:%u: volume_curve = \"%s\" unknown (builtin vendor) -- builtin stays",
				     c->path, n, val);
		} else {
			warn("%s:%u: unknown key \"%s\" -- ignored (start, state, preset, data, calculator, edid, edid_prefer, source, volume_curve)",
			     c->path, n, key);
		}
	}
	fclose(f);
	conf_saved_path(c);
}

struct control {
	int lfd;
	int lock_fd;		/* flock on <dir>/lock: one instance per socket */
	const char *path;
	enum policy policy;
	int source;		/* enum source: what the panel shows, "ctl source" */
	const struct conf *conf;
	const char *state_path;	/* NULL: the mode is not kept */
	char state_known[8];	/* what the state file holds: "auto", "off", "" */
	bool state_complained;
};

static const char *policy_word(enum policy p)
{
	return p == POLICY_OFF ? "off" : "auto";
}

/* what the state file holds right now -- "" for none, unreadable or garbage */
static void state_read(struct control *c)
{
	char line[32];
	FILE *f;

	c->state_known[0] = '\0';
	if (!c->state_path)
		return;
	f = fopen(c->state_path, "r");
	if (!f) {
		if (errno != ENOENT)
			warn("%s: %s -- counts as nothing saved", c->state_path, strerror(errno));
		return;
	}
	if (fgets(line, sizeof(line), f)) {
		const char *w = trim(line);

		if (!strcmp(w, "auto") || !strcmp(w, "off"))
			snprintf(c->state_known, sizeof(c->state_known), "%s", w);
		else
			warn("%s: \"%s\" is not a mode (auto, off) -- counts as nothing saved",
			     c->state_path, w);
	}
	fclose(f);
}

/*
 * Keep the mode across restarts: written whole into a sibling file and
 * renamed over, so a power cut leaves either the old word or the new one,
 * never half a line. Nothing is written when the file already says the same
 * -- that is the rule, not an optimisation (plan 107 section 4).
 */
static void state_write(struct control *c, enum policy p)
{
	const char *mode = policy_word(p);
	char tmp[224], dir[224], *slash;
	int fd;

	if (!c->state_path || !strcmp(c->state_known, mode))
		return;
	snprintf(tmp, sizeof(tmp), "%s.new", c->state_path);
	fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0 && errno == ENOENT) {
		/* started by hand, without the unit's StateDirectory */
		snprintf(dir, sizeof(dir), "%s", c->state_path);
		slash = strrchr(dir, '/');
		if (slash && slash != dir) {
			*slash = '\0';
			if (!mkdir(dir, 0755) || errno == EEXIST)
				fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
		}
	}
	if (fd < 0) {
		if (!c->state_complained)
			warn("%s: %s -- the mode is not saved", tmp, strerror(errno));
		c->state_complained = true;
		return;
	}
	if (dprintf(fd, "%s\n", mode) < 0 || fsync(fd) || close(fd) ||
	    rename(tmp, c->state_path)) {
		if (!c->state_complained)
			warn("%s: %s -- the mode is not saved", c->state_path,
			     strerror(errno));
		c->state_complained = true;
		unlink(tmp);
		return;
	}
	snprintf(c->state_known, sizeof(c->state_known), "%s", mode);
	info("mode            %s -- saved in %s", mode, c->state_path);
}

/*
 * The mode to start in, decided from tv.conf and the state file, and said
 * in one line so the journal shows why the wall looks the way it does.
 */
static enum policy start_policy(struct control *c)
{
	const struct conf *cf = c->conf;
	const char *why;
	bool console;

	switch (cf->start) {
	case START_MANUAL:
		console = true;
		why = "start = manual";
		break;
	case START_LAST:
		console = !strcmp(c->state_known, "off");
		why = c->state_known[0] ? "start = last, saved" : "start = last, nothing saved";
		break;
	default:
		console = false;
		why = cf->present ? "start = auto" : "default start = auto";
		break;
	}
	info("config          %s%s: %s -> %s; %s%s", cf->path, cf->present ? "" : " missing", why,
	     console ? "console until \"h713-tv ctl on\"" : "the picture follows the signal",
	     c->state_path ? "the mode is saved in " : "the mode is not saved (state = none)",
	     c->state_path ? c->state_path : "");

	return console ? POLICY_OFF : POLICY_AUTO;
}

struct reply {
	/* status is the longest answer: its own lines, then the kernel's,
	 * cpu_comm's, the ARISC's and the five HDCP lines (S12 R7 wants them
	 * all in one place); 4 KiB was tight for that */
	char buf[8192];
	size_t len;
	bool failed;
};

__attribute__((format(printf, 2, 3)))
void reply_add(struct reply *r, const char *fmt, ...)
{
	va_list ap;
	int n;

	if (r->len >= sizeof(r->buf) - 1)
		return;
	va_start(ap, fmt);
	n = vsnprintf(r->buf + r->len, sizeof(r->buf) - r->len, fmt, ap);
	va_end(ap);
	if (n > 0)
		r->len += (size_t)n < sizeof(r->buf) - r->len ? (size_t)n
							    : sizeof(r->buf) - 1 - r->len;
}

__attribute__((format(printf, 2, 3)))
void reply_fail(struct reply *r, const char *fmt, ...)
{
	va_list ap;
	char msg[512];

	va_start(ap, fmt);
	vsnprintf(msg, sizeof(msg), fmt, ap);
	va_end(ap);
	r->failed = true;
	reply_add(r, "error %s\n", msg);
}

/*
 * One instance per socket. A second h713-tv would fight the first for the
 * plane, the master and the source; refuse it before anything is touched --
 * before the capture node is opened, before the master is dropped, before
 * S_INPUT (S12 D, F2). No lock, no start: without it the second instance
 * would pull the first one's socket away.
 */
static void control_lock(struct control *c, const char *path)
{
	char dir[108], lock[128];
	char *slash;

	c->lfd = -1;
	c->lock_fd = -1;
	c->path = path;
	c->policy = POLICY_AUTO;

	if (strlen(path) >= sizeof(((struct sockaddr_un *)0)->sun_path))
		fail("%s: socket path longer than %zu characters", path,
		     sizeof(((struct sockaddr_un *)0)->sun_path) - 1);

	snprintf(dir, sizeof(dir), "%s", path);
	slash = strrchr(dir, '/');
	if (!slash || slash == dir)
		fail("%s: the socket needs a directory", path);
	*slash = '\0';
	if (mkdir(dir, 0755) && errno != EEXIST)
		fail("%s: %s", dir, strerror(errno));
	snprintf(lock, sizeof(lock), "%s/lock", dir);
	c->lock_fd = open(lock, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
	if (c->lock_fd < 0)
		fail("%s: %s -- without the single-instance lock h713-tv does not start", lock,
		     strerror(errno));
	if (flock(c->lock_fd, LOCK_EX | LOCK_NB))
		fail("%s: another instance of h713-tv is already running", lock);
}

static void control_listen(struct control *c)
{
	struct sockaddr_un addr;
	const char *path = c->path;

	c->lfd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
	if (c->lfd < 0) {
		warn("socket: %s -- no control channel", strerror(errno));
		return;
	}
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
	unlink(path);
	if (bind(c->lfd, (struct sockaddr *)&addr, sizeof(addr)) ||
	    chmod(path, 0660) || listen(c->lfd, 4)) {
		warn("%s: %s -- no control channel", path, strerror(errno));
		close(c->lfd);
		c->lfd = -1;
		return;
	}
	info("control         %s (h713-tv ctl help)", path);
}

static void control_close(struct control *c)
{
	if (c->lock_fd >= 0) {
		close(c->lock_fd);
		c->lock_fd = -1;
	}
	if (c->lfd < 0)
		return;
	close(c->lfd);
	unlink(c->path);
	c->lfd = -1;
}

/* a few lines of a file, prefixed; for the kernel's own status */
static void reply_file_lines(struct reply *r, const char *path,
			     const char *const *keys, const char *prefix)
{
	char line[256];
	FILE *f;

	f = fopen(path, "r");
	if (!f) {
		reply_add(r, "%s%s: %s\n", prefix, path, strerror(errno));
		return;
	}
	while (fgets(line, sizeof(line), f)) {
		unsigned int i;

		for (i = 0; keys[i]; i++)
			if (!strncmp(line, keys[i], strlen(keys[i]))) {
				reply_add(r, "%s%s", prefix, line);
				break;
			}
	}
	fclose(f);
}

/*
 * The sound in ctl status. The first line is what this program decided, the
 * second what the two cards actually hold, the third what the source says --
 * three answers that have to agree, and a status that hides the difference
 * would be worth nothing (S12 R7).
 */
static void cmd_status_audio(struct reply *r, struct audio *a, bool live)
{
	char text[64], trim[40], sw[32], vol[32], mu[32], src[32], rate[32];
	char dac[32], cmu[32], imu[32], pcm[96], dir[48];

	if (a->policy == AUDIO_NONE) {
		reply_add(r, "audio           not touched (-a none)\n");
		return;
	}
	if (!a->enabled) {
		reply_add(r, "audio           off -- %s\n", a->why);
		return;
	}
	if (a->state == AUDIO_LOUD && a->applied_rate)
		reply_add(r, "audio           %s (%s), %u Hz, %s, %s%s%s\n",
			  audio_state_text(a), audio_policy_text(a),
			  a->applied_rate, audio_volume_text(a, text, sizeof(text)),
			  audio_trim_text(a, trim, sizeof(trim)),
			  a->mute ? ", ctl mute on" : "", a->covered ? ", muted under an opaque page" : "");
	else
		reply_add(r, "audio           %s (%s)%s, %s, %s%s%s\n",
			  audio_state_text(a), audio_policy_text(a),
			  a->state == AUDIO_STILL ? "" : ", rate unknown",
			  audio_volume_text(a, text, sizeof(text)),
			  audio_trim_text(a, trim, sizeof(trim)),
			  a->mute ? ", ctl mute on" : "", a->covered && a->state != AUDIO_STILL ? ", muted under an opaque page" : "");
	/*
	 * The card lines read the controls back from the hardware, seven
	 * reads that cost this single-threaded program about 50 ms in all -
	 * long enough for the warp's frame to wait behind a status while the
	 * settings page polls every three seconds (measured 23.09.2026: a
	 * 40-55 ms answer every poll, none without the page). "status brief"
	 * reports what this program last wrote instead and reads nothing.
	 */
	if (!live) {
		snprintf(sw, sizeof(sw), "-");
		snprintf(vol, sizeof(vol), "-");
		snprintf(mu, sizeof(mu), "-");
		snprintf(src, sizeof(src), "-");
		snprintf(rate, sizeof(rate), "-");
		snprintf(dac, sizeof(dac), "-");
		snprintf(cmu, sizeof(cmu), "-");
		snprintf(imu, sizeof(imu), "-");
	} else {
		alsa_read_text(&a->msp, AUDIO_C_SWITCH, sw, sizeof(sw));
		alsa_read_text(&a->msp, AUDIO_C_VOLUME, vol, sizeof(vol));
		alsa_read_text(&a->msp, AUDIO_C_MUTE, mu, sizeof(mu));
		if (a->have_inmute)
			alsa_read_text(&a->msp, AUDIO_C_INMUTE, imu, sizeof(imu));
		else
			snprintf(imu, sizeof(imu), "none");
		alsa_read_text(&a->codec, AUDIO_C_SOURCE, src, sizeof(src));
		alsa_read_text(&a->codec, AUDIO_C_RATE, rate, sizeof(rate));
		if (a->have_dacvol)
			alsa_read_text(&a->codec, AUDIO_C_DACVOL, dac, sizeof(dac));
		else
			snprintf(dac, sizeof(dac), "missing");
		if (a->codec_mute)
			alsa_read_text(&a->codec, a->codec_mute, cmu, sizeof(cmu));
		else
			snprintf(cmu, sizeof(cmu), "none");
	}
	reply_add(r, "audio cards     %s (card %d): Switch %s, Volume %s, Mute %s, Input Mute %s | %s (card %d): Source %s, Rate %s, DAC Volume %s, switch %s%s%s\n",
		  a->msp.id, a->msp.index, sw, vol, mu, imu, a->codec.id,
		  a->codec.index, src, rate, dac,
		  a->codec_mute ? a->codec_mute : "", a->codec_mute ? " " : "",
		  cmu);
	/* the PCM's own state: two proc reads, no firmware -- brief skips them all the same */
	snprintf(dir, sizeof(dir), "/proc/asound/card%d/pcm0p/sub0",
		 a->have_inmute ? a->msp.index : a->codec.index);
	if (a->have_inmute)
		reply_add(r, "audio sounds    the box's own sounds: hw:%s,0 (48 kHz, mixed into HDMI by the DSP), the DAC stays on I2S; PCM %s\n",
			  a->msp.id, live ? pcm_state_text(dir, pcm, sizeof(pcm)) : "-");
	else
		reply_add(r, "audio sounds    the box's own sounds: hw:%s,0 (codec APB) -- audible only while HDMI is silent (no bridge PCM, kernel before 0176); PCM %s\n",
			  a->codec.id, live ? pcm_state_text(dir, pcm, sizeof(pcm)) : "-");
	if (!a->have_source)
		reply_add(r, "audio source    no controls \"%s\"/\"%s\"/\"%s\" on the capture node (kernel 0136)\n",
			  AUDIO_V_PRESENT, AUDIO_V_RATE, AUDIO_V_COMPRESSED);
	else
		reply_add(r, "audio source    present=%d rate=%u compressed=%d (%s)\n",
			  a->present, a->rate, a->compressed,
			  a->events ? "events" : "polling");
	/* the two sysfs reads below ask the firmware, about 25 ms each - brief skips them */
	if (live && card_sysfs(&a->msp, "state", sw, sizeof(sw)))
		reply_add(r, "audio msp       state=%s\n", sw);
	if (live && card_sysfs(&a->msp, "levels", vol, sizeof(vol)))
		reply_add(r, "audio level     %s\n", vol);
}

/*
 * The three layers of the picture values, as they stand right now. Defined
 * down with the presets, because that is where the state it reports lives;
 * declared here so the status keeps reading top to bottom.
 */
static void cmd_status_picture_values(struct reply *r);
static void cmd_status_edid(struct reply *r, struct capture *cap);

static double status_ms(struct timespec *a)
{
	struct timespec b;
	double ms;

	clock_gettime(CLOCK_MONOTONIC, &b);
	ms = (b.tv_sec - a->tv_sec) * 1e3 + (b.tv_nsec - a->tv_nsec) / 1e6;
	*a = b;
	return ms;
}

/*
 * HDCP, as the kernel's hdcp file says it (kernel 0174): five lines copied
 * through. "version:" and "authenticated:" are the two to read before and
 * after a protected source is plugged in; "firmware:" is the display
 * firmware's own last word on it, out of its log ring. The file is a sysfs
 * attribute of the hdmirx platform device, which is the parent of the video
 * node -- sysfs and not debugfs, because the release kernel has no debugfs
 * ("unknown filesystem type" on the HY300 Pro's test image).
 */
static const char *const hdcp_keys[] = {
	"version:", "authenticated:", "key-1.4:", "key-2.2:", "firmware:", NULL,
};

/* /sys/class/video4linux/videoN/device/hdcp for the node that was opened */
static const char *hdcp_path(const struct capture *cap, char *buf, size_t len)
{
	const char *node = strrchr(cap->path, '/');

	snprintf(buf, len, "/sys/class/video4linux/%s/device/hdcp",
		 node ? node + 1 : cap->path);
	return buf;
}

static void cmd_status(struct reply *r, struct control *c, struct capture *cap,
		       struct display *d, struct audio *a, bool live)
{
	struct timespec st_t;
	double st_head, st_colour, st_rest, st_pic, st_audio;

	clock_gettime(CLOCK_MONOTONIC, &st_t);
	static const char *const kern[] = {
		"format:", "incap:", "capture:", "converter:", "signal:", "timings:",
		/* what the firmware's own record says about the source (kernel 0136n) */
		"colour:", "hdr:", NULL,
	};
	static const char *const comm[] = { "rx_calls", "eingehend", NULL };
	/* which of the firmware's two EDID blocks each HDMI port is served */
	static const char *const edid[] = { "edid_version_mask:", NULL };
	/* the last measurement evaluate() made -- a status is a report, not a probe (S12 R7) */
	const struct v4l2_dv_timings *t = &cap->last_t;
	int sig = cap->last_sig;
	char sigbuf[64], colbuf[64], hdcpbuf[64];

	reply_add(r, "ok status\n");
	reply_add(r, "mode            %s\n", c->policy == POLICY_OFF ? "off (console forced)"
								  : "automatic");
	if (c->conf)
		reply_add(r, "config          %s%s: start=%s; saved=%s%s%s\n", c->conf->path,
			  c->conf->present ? "" : " (missing)", start_mode_text(c->conf->start),
			  c->state_known[0] ? c->state_known : "-",
			  c->state_path ? " in " : " (state = none)",
			  c->state_path ? c->state_path : "");
	if (sig == 1)
		reply_add(r, "signal          %s (last measured)\n",
			  signal_text(t, sigbuf, sizeof(sigbuf)));
	else if (sig == 2 && t->bt.width)
		reply_add(r, "signal          change in flight (the geometry has not locked yet; last measured %s)\n",
			  signal_text(t, sigbuf, sizeof(sigbuf)));
	else if (sig == 2)
		reply_add(r, "signal          change in flight (the geometry has not locked yet)\n");
	else if (sig == 3 && t->bt.width)
		reply_add(r, "signal          %s not in the firmware's table -- console\n",
			  signal_text(t, sigbuf, sizeof(sigbuf)));
	else if (sig == 3)
		reply_add(r, "signal          a source the firmware's table does not carry -- console\n");
	else
		reply_add(r, "signal          %s\n", sig == 0 ? "no signal" : "not readable");
	st_head = status_ms(&st_t);
	reply_add(r, "colour          %s\n", capture_colour(cap, colbuf, sizeof(colbuf)));
	st_colour = status_ms(&st_t);
	reply_add(r, "picture         %s%s\n",
		  d->warped ? "warped (h713-warp draws on the video plane)" :
		  d->on ? "plane on" : "console",
		  d->master ? ", DRM master held" : "");
	reply_add(r, "source          %s\n", source_name[c->source]);
	reply_add(r, "cover           %s\n", cover.on ? (cover.plane_off || !d->warped ? "an opaque page hides the picture: h713-warp pauses, the video plane is off, the HDMI sound is muted" :
		  "an opaque page hides the picture: h713-warp pauses, the HDMI sound is muted (the video plane could not go off)") :
		  cover.resuming ? "the page went: the overlay's change waits for h713-warp's next frame" : "none");
	if (bare.on)
		reply_add(r, "bare            on, %ld s left: nothing of ours on the wall%s\n", bare_left(),
			  osd.want >= 0 ? ", h713-osd's overlay waits" : "");
	else
		reply_add(r, "bare            off\n");
	/* "page" first on the line when the wall shows the page: h713-settings reads "nosignal        page" for "No HDMI signal" */
	reply_add(r, "nosignal        %s\n", !nosig.lost ? "none" :
		  !nosig_page_ok() ? "no page: nothing to show, but h713-osd is not claimed, the console is forced or a program is the mode" :
		  osd_covering() ? "page: h713-osd shows \"No signal on HDMI\"" :
		  "waiting for the page: h713-osd draws it, the last picture stands until it is up");
	if (warp.claimed)
		reply_add(r, "warp            on (%s), video plane %u: %lu commits, %lu busy, %lu refused\n",
			  warp.client ? "a Wayland client" : "the ring", d->plane_id, warp.commits, warp.busy,
			  warp.errors);
	{
		char wbuf[160];

		reply_add(r, "want            %s\n", want_text(wbuf, sizeof(wbuf)));
	}
	if (d->src_w)
		reply_add(r, "buffer          %ux%u NV16, line pitch %u on panel %ux%u\n", d->src_w, d->src_h, d->src_pitch,
			  d->width, d->height);
	if (d->has_aspect)
		reply_add(r, "format          %s (aspect %llu)\n",
			  prop_enum_name(&d->plane_props, "aspect", d->aspect),
			  (unsigned long long)d->aspect);
	{
		char zbuf[32], sbuf[48], dbuf[48];

		zoom_text(d, zbuf, sizeof(zbuf));
		reply_add(r, "zoom            %s%s\n", zbuf,
			  d->has_windows ? "" :
				  " (the kernel has no zoom windows)");
		reply_add(r, "                src-window %s, dst-window %s (descriptor words 27..30 / 31..34)\n",
			  window_text(&d->src_win, sbuf, sizeof(sbuf)),
			  window_text(&d->dst_win, dbuf, sizeof(dbuf)));
		reply_add(r, "                plane %u,%u %ux%u on panel %ux%u\n",
			  d->win_x, d->win_y, d->win_w, d->win_h, d->width,
			  d->height);
		if (d->src_w && d->zoom == ZOOM_OUT) {
			unsigned int sw, sh;

			display_source_rect(d, &sw, &sh);
			reply_add(r, "                the firmware fits the picture into %ux%u of the ring, the rest is the last full frame\n",
				  sw, sh);
		}
	}
	st_rest = status_ms(&st_t);
	cmd_status_picture_values(r);
	st_pic = status_ms(&st_t);
	cmd_status_audio(r, a, live);
	st_audio = status_ms(&st_t);
	if (st_head + st_colour + st_rest + st_pic + st_audio > 5.0)
		info("timing          status: head %.1f, colour %.1f, display %.1f, picture %.1f, audio %.1f ms",
		     st_head, st_colour, st_rest, st_pic, st_audio);
	if (!live)
		return;
	cmd_status_edid(r, cap);
	reply_file_lines(r, "/sys/kernel/debug/" V4L2_DRIVER "/status", kern, "kernel          ");
	reply_file_lines(r, "/sys/kernel/debug/cpu_comm/watch", comm, "cpu_comm        ");
	reply_file_lines(r, "/sys/kernel/debug/h713-arisc/status", edid, "arisc           ");
	reply_file_lines(r, hdcp_path(cap, hdcpbuf, sizeof(hdcpbuf)), hdcp_keys,
			 "hdcp            ");
}

/* "hdcp": the five HDCP lines alone, without the rest of status */
static void cmd_hdcp(struct reply *r, struct capture *cap)
{
	char path[64];

	reply_add(r, "ok hdcp\n");
	reply_file_lines(r, hdcp_path(cap, path, sizeof(path)), hdcp_keys,
			 "hdcp            ");
}

static void cmd_list(struct reply *r, struct capture *cap)
{
	struct v4l2_query_ext_ctrl q;
	char key[64], menu[64];
	int64_t val;

	reply_add(r, "ok controls\n");
	memset(&q, 0, sizeof(q));
	q.id = V4L2_CTRL_FLAG_NEXT_CTRL;
	while (!ioctl(cap->fd, VIDIOC_QUERY_EXT_CTRL, &q)) {
		if (!(q.flags & V4L2_CTRL_FLAG_DISABLED) &&
		    q.type != V4L2_CTRL_TYPE_CTRL_CLASS) {
			ctrl_key(q.name, key, sizeof(key));
			if (ctrl_get(cap->fd, &q, &val))
				reply_add(r, "  %-26s ?  (%lld..%lld)\n", key,
					  (long long)q.minimum, (long long)q.maximum);
			else if (ctrl_menu_text(cap->fd, &q, val, menu, sizeof(menu)))
				reply_add(r, "  %-26s %lld (%s)  menu 0..%lld\n", key,
					  (long long)val, menu, (long long)q.maximum);
			else
				reply_add(r, "  %-26s %lld  (%lld..%lld)\n", key,
					  (long long)val, (long long)q.minimum,
					  (long long)q.maximum);
		}
		q.id |= V4L2_CTRL_FLAG_NEXT_CTRL;
	}
	/* the firmware's own: held here, not in the capture driver */
	fwc_list(r);
	gamma_list(r);
}

static int mode_ctemp(int mode);	/* the colour temperature a picture mode asks for: 0 normal, 1 cool, 2 warm */

static void cmd_get(struct reply *r, struct capture *cap, const char *name)
{
	struct v4l2_query_ext_ctrl q;
	char menu[64];
	int64_t val;
	int ret;

	if (fwc_key(name) >= 0) {
		fwc_get(r, fwc_key(name));
		return;
	}
	if (gamma_key(name) >= 0) {
		gamma_get(r, gamma_key(name));
		return;
	}
	if (!ctrl_find(cap->fd, name, &q)) {
		reply_fail(r, "no control \"%s\" (h713-tv ctl list)", name);
		return;
	}
	ret = ctrl_get(cap->fd, &q, &val);
	if (ret) {
		reply_fail(r, "reading %s: %s", q.name, strerror(-ret));
		return;
	}
	if (ctrl_menu_text(cap->fd, &q, val, menu, sizeof(menu)))
		reply_add(r, "ok %s = %lld (%s)\n", q.name, (long long)val, menu);
	else
		reply_add(r, "ok %s = %lld\n", q.name, (long long)val);
}

static void cmd_set(struct reply *r, struct capture *cap, const char *name,
		    const char *value)
{
	struct v4l2_query_ext_ctrl q;
	char menu[64], *end;
	long long val;
	int ret;

	if (fwc_key(name) >= 0) {
		fwc_set(r, fwc_key(name), value);
		return;
	}
	if (gamma_key(name) >= 0) {
		gamma_set(r, gamma_key(name), value);
		return;
	}
	if (!ctrl_find(cap->fd, name, &q)) {
		reply_fail(r, "no control \"%s\" (h713-tv ctl list)", name);
		return;
	}
	val = strtoll(value, &end, 0);
	if (*end && q.type == V4L2_CTRL_TYPE_MENU) {
		/* a menu entry by its text, e.g. "full" */
		char k1[64], k2[64];

		ctrl_key(value, k2, sizeof(k2));
		for (val = q.minimum; val <= q.maximum; val++) {
			if (!ctrl_menu_text(cap->fd, &q, val, menu, sizeof(menu)))
				continue;
			ctrl_key(menu, k1, sizeof(k1));
			if (!strcmp(k1, k2))
				break;
		}
		if (val > q.maximum) {
			reply_fail(r, "%s does not know \"%s\"", q.name, value);
			return;
		}
	} else if (*end) {
		reply_fail(r, "\"%s\" is not a number", value);
		return;
	}
	if (val < q.minimum || val > q.maximum) {
		reply_fail(r, "%s: %lld is outside %lld..%lld", q.name, val,
			   (long long)q.minimum, (long long)q.maximum);
		return;
	}
	{
		char key[64];
		bool mode;

		/* a picture mode makes the firmware write its own colour again: see fwc_mode_begin() */
		ctrl_key(q.name, key, sizeof(key));
		mode = !strcmp(key, "picture_mode");
		if (mode)
			fwc_mode_begin();
		ret = ctrl_set(cap->fd, &q, val);
		if (mode)
			fwc_mode_end("a picture mode");
		if (mode && !ret)
			gamma_mode_temp(mode_ctemp((int)val), "a picture mode");
	}
	if (ret) {
		reply_fail(r, "%s = %lld: %s", q.name, val, strerror(-ret));
		return;
	}
	if (ctrl_menu_text(cap->fd, &q, val, menu, sizeof(menu)))
		reply_add(r, "ok %s = %lld (%s)\n", q.name, val, menu);
	else
		reply_add(r, "ok %s = %lld\n", q.name, val);
}

/*
 * An RPC by name, straight to the firmware, through the kernel's debugfs
 * prompt (doku/83 section 4). This is the door for everything the driver has
 * no control for -- THal_Vp_DisableBlackScreen, THal_Vp_SetSource 3 -- and it
 * is deliberately as raw as the prompt itself: the firmware's own rules apply,
 * and a call that the drivers are not prepared for can still take the picture
 * away. The result line is the kernel's.
 */
static void cmd_rpc(struct reply *r, const char *line)
{
	static const char path[] = "/sys/kernel/debug/cpu_comm/call";
	char out[256];
	ssize_t n;
	int fd;

	/* the kernel's line buffer is 160 bytes; say so instead of a bare EINVAL */
	if (strlen(line) >= 159) {
		reply_fail(r, "RPC line longer than 158 characters");
		return;
	}
	fd = open(path, O_WRONLY | O_CLOEXEC);
	if (fd < 0) {
		reply_fail(r, "%s: %s", path, strerror(errno));
		return;
	}
	n = write(fd, line, strlen(line));
	close(fd);
	if (n < 0) {
		reply_fail(r, "%s: %s", line, strerror(errno));
		return;
	}
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		reply_fail(r, "reading %s: %s", path, strerror(errno));
		return;
	}
	n = read(fd, out, sizeof(out) - 1);
	close(fd);
	if (n <= 0) {
		reply_fail(r, "no answer to %s", line);
		return;
	}
	out[n] = '\0';
	out[strcspn(out, "\n")] = '\0';
	/*
	 * The kernel runs the call inside write() and reports a failure as the
	 * write's error, so a successful write already means "-> ok"; the read
	 * only fetches the values. The check stays for the unlikely second
	 * writer in between.
	 */
	if (strstr(out, "-> error"))
		reply_fail(r, "%s -> %s", line, out);
	else
		reply_add(r, "ok %s -> %s\n", line, out);
}

/*
 * The firmware's "zoom" aspect (5) is refused here even where the kernel
 * still lists it (before 0185): with it the firmware does not take the plane
 * again -- enable and disable time out, the capture stops for good, and a
 * saved one did the same at the next start (06.10.2026, HY310, 1080p60).
 */
static bool aspect_refused(const char *name)
{
	return name && !strcasecmp(name, "zoom");
}

/* the kernel's enum names of "aspect" that may be set, space-separated, for messages */
static void aspect_names(const struct display *d, char *buf, size_t n)
{
	const drmModePropertyRes *p = prop_info(&d->plane_props, "aspect");
	size_t l = 0;
	int i;

	buf[0] = '\0';
	for (i = 0; p && i < p->count_enums && l + 1 < n; i++)
		if (!aspect_refused(p->enums[i].name))
			l += (size_t)snprintf(buf + l, n - l, "%s%s", l ? " " : "",
					      p->enums[i].name);
}

/* ------------------------------------------------------------------ *
 * replug: an unplug and a replug, as the source sees it
 *
 * The hotplug pin belongs to the ARISC firmware, and the capture driver
 * exposes it the V4L2 way (doku/88 section 3): VIDIOC_S_EDID with
 * blocks == 0 pulls it low; VIDIOC_S_EDID with the four-block EDID runs the
 * whole stock sequence again -- reset the EDID module, upload, confirm,
 * audio mode, +5 V, pin low for 200 ms, pin high (0091,
 * arisc_hdmi_edid_init()). To the source that is a cable pulled and put
 * back: it drops the link, reads the EDID afresh and negotiates anew. That
 * is what one wants when a mode did not lock (S12 C), or when a source
 * sleeps on a link it believes to be up.
 *
 * The EDID that goes back is the one read from the firmware right before
 * (G_EDID: 512 bytes, the HDMI 1.4 block and the HDMI 2.0 block back to
 * back). It is checked before the pin is touched -- both headers and the
 * four block checksums -- so a failed read-back can never become an
 * uploaded garbage EDID, and a copy of the last good one is kept for the
 * case that the firmware does not answer next time (after blocks == 0 the
 * driver has no fallback of its own, it has just been told there is none).
 *
 * 300 ms low is the measured minimum for a source to see the cycle (M4);
 * the driver's own 200 ms come on top. The program blocks for the whole
 * cycle, like it does for "rpc" -- about a second. Returns true when
 * evaluate() has to run.
 *
 * With half >= 0 the EDID that goes back is that half of the file alone, as
 * one 256-byte EDID (S_EDID with two blocks, kernel 0170): the firmware then
 * serves it on port 0 whatever its per-port block mask says. That is how
 * "edid = block1" in tv.conf and "ctl edid block1" put the file's second
 * half - 1080p100/120 on the HY310 - in front of the source (FB-EDID).
 * ------------------------------------------------------------------ */

#define EDID_BLOCKS	4
#define EDID_BYTES	(EDID_BLOCKS * 128)
#define REPLUG_LOW_MS	300

static bool edid_plausible(const uint8_t *e, char *why, size_t n)
{
	static const uint8_t header[8] = { 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00 };
	unsigned int b, i, sum;

	/* two EDIDs back to back: byte 0 and byte 256 each start a header */
	for (b = 0; b < EDID_BLOCKS; b += 2)
		if (memcmp(e + b * 128, header, sizeof(header))) {
			snprintf(why, n, "no EDID header at byte %u (%02x %02x %02x %02x %02x %02x %02x %02x)",
				 b * 128, e[b * 128], e[b * 128 + 1], e[b * 128 + 2],
				 e[b * 128 + 3], e[b * 128 + 4], e[b * 128 + 5],
				 e[b * 128 + 6], e[b * 128 + 7]);
			return false;
		}
	for (b = 0; b < EDID_BLOCKS; b++) {
		for (sum = 0, i = 0; i < 128; i++)
			sum += e[b * 128 + i];
		if (sum & 0xff) {
			snprintf(why, n, "block %u: checksum %02x instead of 00", b, sum & 0xff);
			return false;
		}
	}

	return true;
}

/*
 * Where the EDID comes from when the driver cannot hand it back.
 *
 * G_EDID goes through arisc_hdmi_get_edid(), and on this board that read-back
 * returns ENODATA -- doku/88 section 8 listed it as unmeasured, 11.09.2026
 * measured it. Without a way back there is no replug: pulling HPD down with
 * nothing to upload afterwards leaves the source staring at a dead port.
 *
 * The file is the same 512 bytes the boot chain uploads, extracted from the
 * device by h713-extract (HDMI_EDID_14.bin and HDMI_EDID_20.bin back to
 * back). It is checked like any other source: header, four checksums.
 */
#define EDID_FILE	"/lib/firmware/hy310-edid.bin"

static bool edid_from_file(const char *path, uint8_t *out, char *why, size_t n)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	ssize_t got;

	if (fd < 0) {
		snprintf(why, n, "%s: %s", path, strerror(errno));
		return false;
	}
	got = read(fd, out, EDID_BYTES);
	close(fd);
	if (got != (ssize_t)EDID_BYTES) {
		snprintf(why, n, "%s: read %zd of %u bytes", path, got,
			 (unsigned int)EDID_BYTES);
		return false;
	}

	return edid_plausible(out, why, n);
}

/* the VICs the firmware's table carries, one bit each (kernel 0172) */
static void edid_table_have(struct capture *cap, uint8_t have[16])
{
	struct v4l2_enum_dv_timings et;

	memset(have, 0, 16);
	memset(&et, 0, sizeof(et));
	for (; !ioctl(cap->fd, VIDIOC_ENUM_DV_TIMINGS, &et); et.index++)
		if ((et.timings.bt.flags & V4L2_DV_FL_HAS_CEA861_VIC) && et.timings.bt.cea861_vic < 128)
			have[et.timings.bt.cea861_vic / 8] |= 1 << (et.timings.bt.cea861_vic % 8);
}

/* a VIC as the table tags it: the native bit off, the aspect twin under the lower code */
static unsigned int edid_vic_lookup(unsigned int vic)
{
	static const uint8_t twin[][2] = { { 3, 2 }, { 7, 6 }, { 18, 17 }, { 22, 21 } };
	unsigned int j;

	vic = vic >= 129 && vic <= 192 ? vic - 128 : vic;
	for (j = 0; j < sizeof(twin) / sizeof(twin[0]); j++)
		if (vic == twin[j][0])
			return twin[j][1];
	return vic;
}

/*
 * Take every short video descriptor the firmware's table does not carry out
 * of one 256-byte EDID. An offered mode that never locks is a black wall for
 * the source that picks it: the HY310's file offers 480i and 576i (VICs 6, 7,
 * 21) and the firmware has no record for them (status line since 04.10.2026,
 * confirmed on the v0.96-beta image 05.10.). The video data block shrinks,
 * what follows it moves up, the freed bytes are zero in front of the
 * checksum, and the checksum is recomputed. Returns how many were dropped;
 * `list` gets them as text.
 */
static unsigned int edid_prune(uint8_t *edid, const uint8_t have[16], char *list, size_t n)
{
	uint8_t *ext = edid + 128;
	unsigned int i, k, dropped = 0, sum = 0;

	if (list && n)
		list[0] = '\0';
	if (!edid[0x7e] || ext[0] != 0x02 || ext[2] < 4)
		return 0;
	for (i = 4; i < ext[2] && i < 127; i += (ext[i] & 0x1f) + 1) {
		if (ext[i] >> 5 != 2)
			continue;
		for (k = 1; k <= (ext[i] & 0x1fu) && i + k < 127;) {
			unsigned int vic = ext[i + k], look = edid_vic_lookup(vic);

			if (look < 128 && have[look / 8] >> (look % 8) & 1) {
				k++;
				continue;
			}
			/* the byte goes, everything up to the checksum moves up one */
			memmove(ext + i + k, ext + i + k + 1, 126 - (i + k));
			ext[126] = 0;
			ext[i]--;
			ext[2]--;
			dropped++;
			if (list && n)
				snprintf(list + strlen(list), n - strlen(list), " %u",
					 vic >= 129 && vic <= 192 ? vic - 128 : vic);
		}
	}
	if (dropped) {
		for (i = 0; i < 127; i++)
			sum += ext[i];
		ext[127] = (uint8_t)(-(int)sum);
	}

	return dropped;
}

/*
 * Take Deep Colour out of one 256-byte EDID.
 *
 * The display firmware does not take Deep Colour: a source that renegotiates to 10 or 12 bits per channel
 * (a replug, a standby, the return from a parked capture) sends a pixel clock the firmware's table has no record
 * for (1080p60 at 12 bit is 222.8 MHz) and the wall shows the console instead of a picture. The vendor's file
 * offers it all the same, in two places of the CTA extension:
 *
 *  - the HDMI vendor block (OUI 00-0C-03), flags byte (payload byte 5): DC_48bit (bit 6), DC_36bit (5),
 *    DC_30bit (4) and DC_Y444 (3), the last being "Deep Colour in YCbCr 4:4:4 as well"; Supports_AI (bit 7)
 *    and DVI_Dual (bit 0) are not Deep Colour and stay;
 *  - the HDMI Forum vendor block (OUI C4-5D-D8), payload byte 6: DC_48bit_420, DC_36bit_420, DC_30bit_420
 *    (bits 2..0), Deep Colour of the YCbCr 4:2:0 modes. The vendor's file has none of it; a file that does gets it
 *    cleared the same way.
 *
 * Only those bits change, so a source is left with 8 bits per channel everywhere. The maximum TMDS clock of both
 * blocks, the modes and every other vendor block (Dolby Vision, HDR) are not touched: the clock is a limit that
 * 8-bit modes need as much as Deep Colour ones, and a mode is no Deep Colour statement. The extension's
 * checksum is computed again. Returns how many bits were cleared (0: nothing to do, nothing changed); `list`
 * gets their names, each with a blank in front.
 */
static unsigned int edid_strip_dc(uint8_t *edid, char *list, size_t n)
{
	static const char *const hdmi_dc[] = { NULL, NULL, NULL, "DC_Y444", "DC_30bit", "DC_36bit", "DC_48bit" };
	static const char *const forum_dc[] = { "DC_30bit_420", "DC_36bit_420", "DC_48bit_420" };
	uint8_t *ext = edid + 128;
	unsigned int i, b, cleared = 0, sum = 0;

	if (list && n)
		list[0] = '\0';
	if (!edid[0x7e] || ext[0] != 0x02 || ext[2] < 4)
		return 0;
	for (i = 4; i < ext[2] && i < 127; i += (ext[i] & 0x1f) + 1) {
		unsigned int len = ext[i] & 0x1f;
		uint8_t *flags = NULL;
		const char *const *names = NULL;
		uint8_t mask = 0;

		if (ext[i] >> 5 != 3 || i + len >= 127)	/* a vendor block that lies inside the extension */
			continue;
		if (len >= 6 && ext[i + 1] == 0x03 && ext[i + 2] == 0x0c && ext[i + 3] == 0x00) {
			flags = &ext[i + 6];
			names = hdmi_dc;
			mask = 0x78;
		} else if (len >= 7 && ext[i + 1] == 0xd8 && ext[i + 2] == 0x5d && ext[i + 3] == 0xc4) {
			flags = &ext[i + 7];
			names = forum_dc;
			mask = 0x07;
		}
		for (b = 0; flags && b < 8; b++) {
			if (!(*flags & mask & (1u << b)))
				continue;
			*flags &= (uint8_t)~(1u << b);
			cleared++;
			if (list && n)
				snprintf(list + strlen(list), n - strlen(list), " %s", names[b]);
		}
	}
	if (cleared) {
		for (i = 0; i < 127; i++)
			sum += ext[i];
		ext[127] = (uint8_t)(-(int)sum);
	}

	return cleared;
}

/*
 * The panel's own timing first.
 *
 * A source follows the EDID's first detailed timing. The vendor's file puts
 * 1920x1080p60 there on every board, the 1280x720 panels included, and a
 * 1080p60 picture on a 720p panel goes through the firmware's downscaler --
 * where the capture ring's three slots lose every fourth to fifth frame
 * (measured 11.10.2026 on the HY300PRO-G-EU: 43..57 of 60 shown, doku/197;
 * the mechanism, doku/198). A 720p60 source on the same panel is shown
 * frame for frame (59.7 of 60). So, with tv.conf edid_prefer = panel, a
 * panel smaller than the file's first timing gets the CTA timing of its own
 * size as the first detailed timing; the file's first timing moves down to
 * the second slot (the second timing of the file goes, it stays listed as a
 * VIC), and the image size, borders and sync flags are the file's. The
 * extension block with its VIC list is not touched: 1080p stays selectable.
 *
 * Off by default since the evening of 11.10.2026: kernel patch 0255 takes the
 * capture slot from the capture's own write index and a 1080p60 source on a
 * 720p panel is shown frame for frame (doku/200), so the source may keep
 * sending its native 1080p and the firmware's scaler does the rest. The rule
 * stays for a device that wants it (edid_prefer = panel).
 *
 * Only the two panel sizes this project has met are in the table. A panel
 * without a CTA timing of its own size keeps the file's order.
 */
static const struct {
	unsigned int w, h;
	uint8_t dtd[12];	/* pixel clock .. sync widths of the CTA timing */
} edid_panel_timings[] = {
	/* CTA VIC 4: 1280x720p60, 74.25 MHz, hblank 370, vblank 30, +H +V */
	{ 1280, 720, { 0x01, 0x1d, 0x00, 0x72, 0x51, 0xd0, 0x1e, 0x20, 0x6e, 0x28, 0x55, 0x00 } },
	/* CTA VIC 16: 1920x1080p60, 148.5 MHz, hblank 280, vblank 45, +H +V */
	{ 1920, 1080, { 0x02, 0x3a, 0x80, 0x18, 0x71, 0x38, 0x2d, 0x40, 0x58, 0x2c, 0x45, 0x00 } },
};

static unsigned int edid_dtd_w(const uint8_t *t) { return t[2] | (unsigned int)(t[4] >> 4) << 8; }
static unsigned int edid_dtd_h(const uint8_t *t) { return t[5] | (unsigned int)(t[7] >> 4) << 8; }

static bool edid_prefer_panel = false;		/* tv.conf edid_prefer */
static unsigned int edid_panel_w, edid_panel_h;	/* the panel, once the display knows it */
static char edid_panel_note[96];		/* what edid_panel_first did to the half published last */
static char edid_dc_note[128];			/* what edid_strip_dc took out of the half published last */

static bool edid_panel_first(uint8_t *edid, unsigned int w, unsigned int h, char *what, size_t n)
{
	uint8_t *d1 = edid + 54, *d2 = edid + 72, old[18];
	const uint8_t *tim = NULL;
	unsigned int i, sum = 0;

	if (what && n)
		what[0] = '\0';
	if (!w || !h || !(d1[0] | d1[1]))	/* no panel known, or no timing in the first slot */
		return false;
	if (edid_dtd_w(d1) <= w && edid_dtd_h(d1) <= h)
		return false;			/* the file's first choice fits the panel */
	for (i = 0; i < sizeof(edid_panel_timings) / sizeof(edid_panel_timings[0]); i++)
		if (edid_panel_timings[i].w == w && edid_panel_timings[i].h == h)
			tim = edid_panel_timings[i].dtd;
	if (!tim)
		return false;
	memcpy(old, d1, sizeof(old));
	memcpy(d1, tim, 12);
	memcpy(d1 + 12, old + 12, 6);		/* image size, borders, sync flags: the file's */
	if (d2[0] | d2[1])			/* a second timing: the file's first takes its slot */
		memcpy(d2, old, sizeof(old));
	for (i = 0; i < 127; i++)
		sum += edid[i];
	edid[127] = (uint8_t)(-(int)sum);
	if (what && n)
		snprintf(what, n, "%ux%u first for the %ux%u panel (the file puts %ux%u first)",
			 w, h, w, h, edid_dtd_w(old), edid_dtd_h(old));

	return true;
}

/* what edid_strip_dc did, in the words the answer and the journal use ("" when it did nothing) */
static void edid_dc_say(char *note, size_t n, unsigned int cleared, const char *list)
{
	if (cleared)
		snprintf(note, n, "without deep colour (%s)", list + 1);
	else if (n)
		note[0] = '\0';
}

/*
 * half `half` of the file as this program publishes it: the panel's timing first, without the modes the table
 * lacks, without Deep Colour
 */
static bool edid_file_half(struct capture *cap, int half, uint8_t *out, unsigned int *dropped,
			   char *list, size_t n, char *why, size_t wn)
{
	uint8_t file[EDID_BYTES], have[16];
	char dc[96];

	if (!edid_from_file(EDID_FILE, file, why, wn))
		return false;
	memcpy(out, file + half * (EDID_BYTES / 2), EDID_BYTES / 2);
	edid_panel_note[0] = '\0';
	if (edid_prefer_panel)
		edid_panel_first(out, edid_panel_w, edid_panel_h, edid_panel_note, sizeof(edid_panel_note));
	edid_table_have(cap, have);
	*dropped = edid_prune(out, have, list, n);
	edid_dc_say(edid_dc_note, sizeof(edid_dc_note), edid_strip_dc(out, dc, sizeof(dc)), dc);

	return true;
}

/* the half this program published last, -1 for none: the driver's default */
static int edid_published = -1;
static int edid_served = -3;	/* the half port 0 serves, as last known; -3: not read yet */

static bool cmd_replug(struct reply *r, struct capture *cap, struct display *d,
		       struct retry *rt, int half)
{
	static uint8_t last_good[EDID_BYTES];
	static bool have_last;
	struct timespec low = { .tv_sec = 0, .tv_nsec = REPLUG_LOW_MS * 1000000L };
	uint8_t buf[EDID_BYTES], pub[EDID_BYTES / 2];
	struct v4l2_edid e;
	char why[160], what[320] = "EDID loaded again", list[64], extra[160] = "";
	const char *origin = "";
	bool copy = false;
	unsigned int dropped = 0;

	if (d->width && d->height) {
		edid_panel_w = d->width;
		edid_panel_h = d->height;
	}
	if (half >= 0 && !edid_file_half(cap, half, pub, &dropped, list, sizeof(list), why, sizeof(why))) {
		reply_fail(r, "%s -- nothing to publish, HPD is not touched", why);
		return false;
	}
	memset(&e, 0, sizeof(e));
	e.blocks = EDID_BLOCKS;
	e.edid = buf;
	if (ioctl(cap->fd, VIDIOC_G_EDID, &e) || e.blocks != EDID_BLOCKS) {
		snprintf(why, sizeof(why), "G_EDID: %s", strerror(errno));
		copy = true;
	} else if (!edid_plausible(buf, why, sizeof(why))) {
		copy = true;
	}
	if (copy) {
		char why2[160];

		if (have_last) {
			warn("replug          %s -- the copy of the last good read goes back", why);
			memcpy(buf, last_good, sizeof(buf));
			origin = " (copy of the last read)";
		} else if (edid_from_file(EDID_FILE, buf, why2, sizeof(why2))) {
			warn("replug          %s -- %s goes back", why, EDID_FILE);
			memcpy(last_good, buf, sizeof(last_good));
			have_last = true;
			origin = " (from " EDID_FILE ")";
		} else {
			reply_fail(r, "%s, and %s -- without an EDID, HPD is not touched",
				   why, why2);
			return false;
		}
	} else {
		memcpy(last_good, buf, sizeof(last_good));
		have_last = true;
	}

	/* the picture goes first, or the ring freezes on its last frame for a second */
	retry_stop(rt);
	if (d->on && !display_hide(d)) {
		reply_fail(r, "the plane cannot be switched off -- no replug");
		return false;
	}

	memset(&e, 0, sizeof(e));	/* blocks == 0: no EDID, pin low */
	if (ioctl(cap->fd, VIDIOC_S_EDID, &e)) {
		reply_fail(r, "S_EDID(blocks=0): %s -- HPD not pulled", strerror(errno));
		return true;
	}
	info("replug          HPD low (S_EDID blocks=0), %u ms", REPLUG_LOW_MS);
	nanosleep(&low, NULL);

	memset(&e, 0, sizeof(e));
	e.blocks = EDID_BLOCKS;
	e.edid = buf;
	if (half >= 0) {
		size_t w;

		e.blocks = EDID_BLOCKS / 2;
		e.edid = pub;
		w = (size_t)snprintf(what, sizeof(what), "block %d of %s published", half, EDID_FILE);
		if (dropped && w < sizeof(what))
			w += (size_t)snprintf(what + w, sizeof(what) - w, " without %u VIC%s the firmware's table lacks (%s)",
					      dropped, dropped == 1 ? "" : "s", list + 1);
		if (edid_dc_note[0] && w < sizeof(what))
			w += (size_t)snprintf(what + w, sizeof(what) - w, "%s%s", dropped ? ", " : " ", edid_dc_note);
		if (edid_panel_note[0] && w < sizeof(what))
			snprintf(what + w, sizeof(what) - w, ", %s", edid_panel_note);
		origin = "";
	} else {
		/*
		 * The plain replug sends the read-back (or the copy, or the file): none of them is
		 * the half as edid_file_half makes it, and the file offers Deep Colour. Both EDIDs
		 * of the four blocks lose it, so no way of publishing brings it back.
		 */
		char dc0[96], dc1[96];
		unsigned int c0 = edid_strip_dc(buf, dc0, sizeof(dc0));
		unsigned int c1 = edid_strip_dc(buf + EDID_BYTES / 2, dc1, sizeof(dc1));

		edid_dc_say(edid_dc_note, sizeof(edid_dc_note), c0 + c1, c0 ? dc0 : dc1);
		if (edid_dc_note[0])
			snprintf(extra, sizeof(extra), ", %s%s", edid_dc_note, c0 && c1 ? " in both EDIDs" : "");
	}
	if (ioctl(cap->fd, VIDIOC_S_EDID, &e)) {
		int err = errno;

		warn("replug          S_EDID(%u blocks): %s -- HPD is LOW, the source sees no device",
		     e.blocks, strerror(err));
		reply_fail(r, "S_EDID with the EDID: %s -- HPD is low! run \"replug\" once more (it takes the copy), or rebind the driver",
			   strerror(err));
		return true;
	}
	if (half >= 0)
		edid_published = half;
	if (half >= 0) {
		edid_served = half;
	} else {
		/*
		 * The four-block republish carries the half written last in its
		 * first 256 bytes (the driver keeps it there, 0170 s_edid), so a
		 * plain replug keeps the served half; only a copy from the file
		 * is the first half again. Device test 02.10.2026, B1 step 6.
		 */
		uint8_t halves[EDID_BYTES];
		unsigned int i, d0 = 0, d1 = 0;

		if (edid_from_file(EDID_FILE, halves, why, sizeof(why))) {
			for (i = 0; i < EDID_BYTES / 2; i++) {
				d0 += buf[i] != halves[i];
				d1 += buf[i] != halves[i + EDID_BYTES / 2];
			}
			edid_served = d0 > 8 && d1 > 8 ? -2 : (int)(d1 < d0);
		}
	}
	info("replug          %s%s%s, HPD high -- the source renegotiates", what, origin, extra);
	reply_add(r, "ok replug -- HPD %u ms low, %s%s%s, the source renegotiates\n",
		  REPLUG_LOW_MS, what, origin, extra);

	return true;
}

/*
 * Which half of the EDID file the source is served: G_EDID reads the 256 bytes
 * port 0 publishes (readable from boot on, unlike the four-block read), the
 * firmware rewrites two of them and the file's halves differ in 73, so the
 * half with the fewer differences is the one. -1: not readable, -2: neither.
 */
static int edid_half_served(struct capture *cap, uint8_t *served)
{
	struct v4l2_edid e = { .blocks = EDID_BLOCKS / 2, .edid = served };
	uint8_t file[EDID_BYTES];
	unsigned int i, diff[2] = { 0, 0 };
	char why[160];

	if (ioctl(cap->fd, VIDIOC_G_EDID, &e) || e.blocks != EDID_BLOCKS / 2)
		return -1;
	if (!edid_from_file(EDID_FILE, file, why, sizeof(why)))
		return -2;
	for (i = 0; i < EDID_BYTES; i++)
		diff[i / (EDID_BYTES / 2)] += served[i % (EDID_BYTES / 2)] != file[i];
	/* the driver's default is the raw file; what this program publishes is the
	 * half without the modes the table lacks -- both count as that half */
	for (i = 0; i < 2; i++) {
		uint8_t pub[EDID_BYTES / 2];
		unsigned int k, d = 0, dropped;

		if (!edid_file_half(cap, (int)i, pub, &dropped, NULL, 0, why, sizeof(why)))
			break;
		for (k = 0; k < EDID_BYTES / 2; k++)
			d += served[k] != pub[k];
		if (d < diff[i])
			diff[i] = d;
	}
	if (diff[0] > 8 && diff[1] > 8)
		return -2;
	return diff[1] < diff[0];
}

/*
 * The served half, and how much of what it offers the firmware's table
 * carries: ENUM_DV_TIMINGS lists the table's records with their CEA VIC
 * (kernel 0172; an older kernel lists its presets there and this line then
 * overstates), the CEA extension's video data block lists what the source is
 * offered. A VIC that differs from a listed one in aspect only counts as
 * that one, because the table is tagged with the lower of the two.
 */
/*
 * The served half as last known. G_EDID with two blocks makes the ARISC take
 * the EDID off all three ports for the read (RequestEDID, doku/82), which a
 * status query must not do while a source may be reading it: one read at the
 * first call, from then on the cache follows the publications, and the bytes
 * come from the file's half (the firmware rewrites two of them, which the VIC
 * list does not need). Deep review 27.09.2026.
 */
static int edid_served_known(struct capture *cap, uint8_t *served)
{
	char why[160];

	if (edid_served == -3)
		edid_served = edid_half_served(cap, served);
	else if (edid_served >= 0) {
		unsigned int dropped;

		if (!edid_file_half(cap, edid_served, served, &dropped, NULL, 0, why, sizeof(why)))
			return -2;
	}
	return edid_served;
}

static void cmd_status_edid(struct reply *r, struct capture *cap)
{
	uint8_t served[EDID_BYTES / 2] = { 0 }, have[16];	/* one bit per VIC 0..127 */
	const uint8_t *ext = served + 128;
	unsigned int i, k, n = 0, miss = 0;
	char list[128] = "", which[96], dc[96];
	int half = edid_served_known(cap, served);

	if (half == -1) {	/* no read-back: what this program published is still known */
		if (edid_published < 0)
			reply_add(r, "edid            the driver's default, block 0 of %s (nothing published from here; G_EDID: %s)\n", EDID_FILE, strerror(errno));
		else
			reply_add(r, "edid            block %d of %s published from here (G_EDID: %s)\n", edid_published, EDID_FILE, strerror(errno));
		return;
	}
	edid_table_have(cap, have);
	/* tag 2 is the video data block: one VIC per byte, 129..192 = 1..64 flagged native */
	if (served[0x7e] && ext[0] == 0x02 && ext[2] >= 4)
		for (i = 4; i < ext[2] && i < 127; i += (ext[i] & 0x1f) + 1) {
			if (ext[i] >> 5 != 2)
				continue;
			for (k = 1; k <= (ext[i] & 0x1fu) && i + k < 127; k++, n++) {
				unsigned int vic = ext[i + k], look = edid_vic_lookup(vic);

				vic = vic >= 129 && vic <= 192 ? vic - 128 : vic;
				if (look < 128 && have[look / 8] >> (look % 8) & 1)
					continue;
				miss++;
				snprintf(list + strlen(list), sizeof(list) - strlen(list), " %u", vic);
			}
		}
	if (half < 0)
		snprintf(which, sizeof(which), "an EDID that is not a half of %s", EDID_FILE);
	else
		snprintf(which, sizeof(which), "block %d of %s", half, EDID_FILE);
	reply_add(r, "edid            %s served (%u VICs offered, %s%s)\n", which, n,
		  miss ? "not in the firmware's table: VIC" : "all in the firmware's table", list);
	if (ext[0] == 0x02) {	/* the Deep Colour bits are read off what is served, on a copy */
		uint8_t copy[EDID_BYTES / 2];

		memcpy(copy, served, sizeof(copy));
		if (edid_strip_dc(copy, dc, sizeof(dc)))
			reply_add(r, "                deep colour offered:%s -- a source may negotiate more than 8 bit\n", dc);
		else
			reply_add(r, "                no deep colour offered, a source sends 8 bit\n");
	}
	if (half >= 0 && edid_panel_note[0])
		reply_add(r, "                %s\n", edid_panel_note);
}

/*
 * edid = block0 | block1 in tv.conf: once at start, before the first picture
 * is judged. It costs the source one renegotiation (about a second of
 * console), which is why the key is for the half the driver does not serve
 * by itself. A refusal is a warning, not a stop.
 */
static void edid_apply_start(const struct conf *cf, struct capture *cap,
			     struct display *d, struct retry *rt)
{
	uint8_t served[EDID_BYTES / 2];
	struct reply r;

	edid_prefer_panel = cf->edid_panel;
	if (d->width && d->height) {
		edid_panel_w = d->width;
		edid_panel_h = d->height;
	}
	if (cf->edid < 0) {
		/*
		 * No half asked for: the driver's default is the raw file, and if
		 * that offers modes the firmware's table has no record for, or Deep
		 * Colour, the same half goes out once more without them (edid_prune,
		 * edid_strip_dc). One HPD pulse at start; a restart of this program
		 * finds the pruned EDID served and does nothing.
		 */
		uint8_t have[16];
		char list[64], dc[96], first[96] = "";
		int half = edid_served_known(cap, served);
		unsigned int pruned, cleared;
		bool moved;

		if (half < 0)
			return;
		moved = edid_prefer_panel && edid_panel_first(served, edid_panel_w, edid_panel_h, first, sizeof(first));
		edid_table_have(cap, have);
		pruned = edid_prune(served, have, list, sizeof(list));
		cleared = edid_strip_dc(served, dc, sizeof(dc));
		if (!pruned && !cleared && !moved) {
			info("edid            block %d of %s is served, all of it in the firmware's table, no deep colour%s", half, EDID_FILE,
			     edid_panel_w && edid_panel_h ? ", its first timing fits the panel" : "");
			return;
		}
		if (moved)
			info("edid            block %d of %s is served -- %s: published again", half, EDID_FILE, first);
		if (pruned)
			info("edid            block %d of %s offers VIC%s the firmware's table lacks -- published again without them",
			     half, EDID_FILE, list);
		if (cleared)
			info("edid            block %d of %s offers deep colour (%s) -- published again without it",
			     half, EDID_FILE, dc + 1);
		memset(&r, 0, sizeof(r));
		cmd_replug(&r, cap, d, rt, half);
		r.buf[strcspn(r.buf, "\n")] = '\0';
		(r.failed ? warn : info)("edid            %s", r.buf);
		return;
	}
	/* already served, as after a restart of this program: no second sequence, unless it still offers Deep Colour */
	if (edid_served_known(cap, served) == cf->edid) {
		char dc[96];

		if (!edid_strip_dc(served, dc, sizeof(dc))) {
			info("edid            block %d of %s is served -- as tv.conf says", cf->edid, EDID_FILE);
			return;
		}
		info("edid            block %d of %s is served, but offers deep colour (%s) -- published again without it",
		     cf->edid, EDID_FILE, dc + 1);
	}
	memset(&r, 0, sizeof(r));
	cmd_replug(&r, cap, d, rt, cf->edid);
	r.buf[strcspn(r.buf, "\n")] = '\0';
	(r.failed ? warn : info)("edid            tv.conf edid = block%d: %s", cf->edid, r.buf);
}

/*
 * aspect [NAME]: how the firmware's window manager fits the source into the
 * panel (descriptor word 35 through the plane property, kernel 0133). It is
 * read at the next publication, so a change on a live plane takes the plane
 * down here and lets evaluate() bring it up again -- the same round trip a
 * geometry change makes, about half a second of console. Returns true when
 * evaluate() has to run.
 */
static bool cmd_aspect(struct reply *r, struct display *d, const char *text)
{
	char names[128];
	uint64_t val;

	if (!d->has_aspect) {
		reply_fail(r, "the plane has no property \"aspect\" (kernel 0133)");
		return false;
	}
	aspect_names(d, names, sizeof(names));
	if (!text) {
		reply_add(r, "ok aspect %s (%llu) -- possible: %s\n",
			  prop_enum_name(&d->plane_props, "aspect", d->aspect),
			  (unsigned long long)d->aspect, names);
		return false;
	}
	if (aspect_refused(text)) {
		reply_fail(r, "aspect zoom is refused: the firmware stops the picture with it -- possible: %s",
			   names);
		return false;
	}
	if (!prop_enum_parse(&d->plane_props, "aspect", text, &val)) {
		reply_fail(r, "aspect does not know \"%s\" -- possible: %s", text, names);
		return false;
	}
	if (val == d->aspect) {
		reply_add(r, "ok aspect %s (%llu), unchanged\n",
			  prop_enum_name(&d->plane_props, "aspect", val),
			  (unsigned long long)val);
		return false;
	}
	d->aspect = val;
	if (d->on && !display_hide(d)) {
		reply_fail(r, "aspect %s saved, but the plane could not be switched off -- it applies from the next picture on",
			   prop_enum_name(&d->plane_props, "aspect", val));
		return false;
	}
	reply_add(r, "ok aspect %s (%llu)%s\n",
		  prop_enum_name(&d->plane_props, "aspect", val),
		  (unsigned long long)val,
		  d->master ? " -- the picture is rebuilt" : "");

	return true;
}

/*
 * "off" | "in [1.0..4.0]" | "out [1..100]". The factor and the percentage
 * have defaults, because "zoom in" without a number is what a remote control
 * sends. False for anything else.
 */
static bool zoom_parse(const char *verb, const char *arg, enum zoom_mode *m,
		       unsigned int *v)
{
	char *end;
	double f;
	long p;

	if (!strcasecmp(verb, "off") || !strcasecmp(verb, "full")) {
		*m = ZOOM_OFF;
		*v = 0;
		return !arg;
	}
	if (!strcasecmp(verb, "in")) {
		errno = 0;
		f = 2.0;
		if (arg) {
			f = strtod(arg, &end);
			if (end == arg || *end || errno || f < 1.0 || f > 4.0)
				return false;
		}
		*m = ZOOM_IN;
		*v = (unsigned int)(f * 100 + 0.5);
		return true;
	}
	if (!strcasecmp(verb, "out")) {
		/*
		 * Retired 23.09.2026: the DE's picture scaler only enlarges. A
		 * destination window smaller than the frame left its ratio at
		 * unity and showed the top-left crop of the picture, centred
		 * (measured at 0x05180008 on the HY310; the vendor shrinks on the
		 * GPU, AP3e). The projection area is h713-warp's zoom. A saved
		 * "zoom = out N" from before reads as off.
		 */
		(void)p;
		(void)end;
		*m = ZOOM_OFF;
		*v = 0;
		return true;
	}

	return false;
}

/* the same as one string, which is the form the saved file keeps */
static bool zoom_parse_text(const char *text, enum zoom_mode *m,
			    unsigned int *v)
{
	char verb[12], arg[16], tail[4];
	int n = sscanf(text, "%11s %15s %3s", verb, arg, tail);

	if (n == 1)
		return zoom_parse(verb, NULL, m, v);

	return n == 2 && zoom_parse(verb, arg, m, v);
}

/*
 * zoom [off | in FACTOR | out PERCENT]: the two descriptor windows, and the
 * plane's rectangle as the placement that follows from them (kernel 0133f;
 * the model is the bench of 22.09.2026, see display_zoom_apply()). Nothing
 * here scales: zoom in is the firmware blowing a smaller source window up
 * into the whole ring, zoom out is the firmware fitting the picture into a
 * smaller window of the ring and the plane cropping and placing that. Read at
 * the next publication, so a change on a live plane takes the plane down here
 * and lets evaluate() bring it up again. Returns true when evaluate() has to
 * run.
 */
static bool cmd_zoom(struct reply *r, struct display *d, const char *verb,
		     const char *arg)
{
	enum zoom_mode m;
	unsigned int v;
	char text[32];

	/* the video plane is off while the warp draws, so the firmware's two
	 * windows would move nothing anybody can see (plan S7)
	 */
	if (warp.claimed) {
		reply_fail(r, "the warp is on - use h713-warp ctl zoom");
		return false;
	}
	if (verb && !strcasecmp(verb, "out")) {
		reply_fail(r, "zoom out is gone (23.09.): the DE scaler only enlarges, it cropped instead of shrinking; the projection area is \"h713-warp ctl zoom PERCENT\"");
		return false;
	}
	if (!verb) {
		zoom_text(d, text, sizeof(text));
		reply_add(r, "ok zoom %s\n", text);
		return false;
	}
	if (strchr(verb, ',')) {
		reply_fail(r, "zoom no longer takes a rectangle. A window somewhere else in the ring would need the plane to crop at SRC_X/SRC_Y, and it crops from the ring's first byte only (kernel 0133c). Use \"in FACTOR\" or \"off\"");
		return false;
	}
	if (!zoom_parse(verb, arg, &m, &v)) {
		reply_fail(r, "zoom takes \"in [1.0..4.0]\" or \"off\", not \"%s%s%s\"",
			   verb, arg ? " " : "", arg ? arg : "");
		return false;
	}
	if (m != ZOOM_OFF && !d->has_windows) {
		reply_fail(r, "this plane has no \"src-window\"/\"dst-window\" -- the kernel is older than patch 0133f, and only \"zoom off\" is possible");
		return false;
	}
	if (m == d->zoom && v == d->zoom_arg) {
		zoom_text(d, text, sizeof(text));
		reply_add(r, "ok zoom %s, unchanged\n", text);
		return false;
	}
	d->zoom = m;
	d->zoom_arg = v;
	display_zoom_apply(d);
	zoom_text(d, text, sizeof(text));
	if (d->on && !display_hide(d)) {
		reply_fail(r, "zoom %s saved, but the plane could not be switched off -- it applies from the next picture on",
			   text);
		return false;
	}
	reply_add(r, "ok zoom %s%s\n", text,
		  d->master ? " -- the picture is rebuilt" : "");

	return true;
}

static struct control ctl;	/* defined with the control socket below */

/* the overlay's change went with a warp frame (or alone, COVER_RESUME_MS later): nothing waits any more */
static void cover_resume_stop(void)
{
	struct itimerspec its;

	if (!cover.resuming)
		return;
	memset(&its, 0, sizeof(its));
	if (cover.resume_fd >= 0)
		timerfd_settime(cover.resume_fd, 0, &its, NULL);
	cover.resuming = false;
}

/* one line to h713-warp on its claim's connection, unasked ("note ..."); false when it could not go */
static bool warp_note(const char *line)
{
	size_t len = strlen(line);

	return warp.peer >= 0 && send(warp.peer, line, len, MSG_NOSIGNAL | MSG_DONTWAIT) == (ssize_t)len;
}

/* a ring claim this program cannot take (no plane, no buffers, no master) while the straight ring waits for it: no use
 * waiting for the next one - true, and evaluate() puts the ring up */
static bool want_give_up(bool client, const char *why)
{
	if (client || ts_zero(&wish.since) || wish.fallback)
		return false;
	want_disarm();
	wish.fallback = true;
	warn("warp            the claim failed here (%s) -- the straight ring without waiting further", why);
	return true;
}

/* "warp claim" (A2): the three targets, their fds with the answer. A video
 * plane that shows the straight ring goes down first and the master is taken
 * for the whole warp; the answer goes out here, because the fds have to
 * travel with that line. A plane that is off (the straight ring waited for
 * this claim, want_hold()) stays off: the warp's first frame turns it on,
 * one switch instead of three. True: the caller has to run evaluate() - the
 * straight ring waited for this claim and it failed here.
 */
static bool cmd_warp_claim(struct reply *r, struct capture *cap, struct display *d, int conn,
			   const char *what)
{
	/* "warp claim client": h713-warp draws a Wayland client; plain "warp claim" is the ring */
	bool client = what && !strcmp(what, "client");
	bool allowed = client ? ctl.source != SOURCE_HDMI : ctl.source != SOURCE_CLIENT;
	bool was_on = d->on;
	char cbuf[CMSG_SPACE(sizeof(int) * WARP_BUFS)] = { 0 }, line[64], waited[64] = "";
	int fds[WARP_BUFS] = { -1, -1, -1 };
	struct iovec io = { line, 0 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1,
			      .msg_control = cbuf, .msg_controllen = sizeof(cbuf) };
	struct cmsghdr *cm;
	int i, bad;

	if (warp.claimed || conn < 0) {
		reply_fail(r, "%s", warp.claimed ? "the warp is already claimed"
			   : "\"warp claim\" needs the connection it is sent on");
		return false;
	}
	if (!d->plane_id || !prop_id(&d->plane_props, "IN_FENCE_FD")) {
		reply_fail(r, "no video plane with IN_FENCE_FD on CRTC %u", d->crtc_id);
		return want_give_up(client, "no video plane with IN_FENCE_FD");
	}
	if (what && !client && strcmp(what, "ring")) {
		reply_fail(r, "warp claim takes ring or client, not \"%s\"", what);
		return false;
	}
	if (client && !d->crtc_props.list)
		props_get(d->fd, d->crtc_id, DRM_MODE_OBJECT_CRTC, &d->crtc_props);
	if (client && !prop_id(&d->crtc_props, "OUT_FENCE_PTR")) {
		reply_fail(r, "CRTC %u has no OUT_FENCE_PTR -- a client cannot be paced", d->crtc_id);
		return false;
	}
	/* "off" holds until "auto": without this the warp, asking once a second,
	 * took the picture back about a second after "off" (TODO 2.27)
	 */
	if (ctl.policy == POLICY_OFF) {
		reply_fail(r, "console forced (\"ctl off\") -- ask again");
		return false;
	}
	/* the source decides; h713-warp reads the policy from this line and asks again */
	if (!allowed) {
		reply_fail(r, "source is %s -- no %s claim, ask again", source_name[ctl.source],
			   client ? "client" : "ring");
		return false;
	}
	if (!client && cap->last_sig != 1) {
		/* the warp asks again once a second, or at once on "note claim"; the console stays until then */
		reply_fail(r, "no signal to warp -- the console stays, ask again");
		return false;
	}
	if ((d->on && !ring_off_for_claim(d)) || !display_take_master(d)) {
		reply_fail(r, "the video plane or the DRM master could not be taken over: %s",
			   strerror(errno));
		return want_give_up(client, "the video plane or the DRM master");
	}
	bad = !warp_alloc(d, fds);
	if (bad) {
		reply_fail(r, "the three %ux%u NV12 buffers could not be made (%s) -- the ring stays",
			   d->width, d->height, strerror(errno));
	} else {
		io.iov_len = (size_t)snprintf(line, sizeof(line), "ok %u %u %u nv12 %u source %s\n",
					      d->width, d->height, warp.pitch, warp.coff,
					      source_name[ctl.source]);
		cm = CMSG_FIRSTHDR(&msg);
		cm->cmsg_level = SOL_SOCKET;
		cm->cmsg_type = SCM_RIGHTS;
		cm->cmsg_len = CMSG_LEN(sizeof(int) * WARP_BUFS);
		memcpy(CMSG_DATA(cm), fds, sizeof(int) * WARP_BUFS);
		bad = sendmsg(conn, &msg, MSG_NOSIGNAL) < 0;
		if (bad)
			reply_fail(r, "the buffers could not be handed over: %s",
				   strerror(errno));
	}
	for (i = 0; i < WARP_BUFS; i++)
		if (fds[i] >= 0)
			close(fds[i]);	/* the peer has its own copies now */
	if (bad) {
		warp_free(d);
		display_release_master(d);
		return want_give_up(client, "the buffers");
	}
	warp.claimed = true;
	warp.client = client;
	warp.told = (int)ctl.source;
	warp.peer = conn;
	if (!client)
		nosig_claimed();	/* a ring claim needs the signal: it is back, the page may go (it waited for this) */
	memset(&warp.last_frame, 0, sizeof(warp.last_frame));
	clock_gettime(CLOCK_MONOTONIC, &warp.claimed_at);
	d->warped = true;
	console_keys(false);
	/* the wait is over with the claim's first frame (warp_serve()); a claim that ends before one does not start it anew */
	want_disarm();
	wish.noted = false;
	if (!ts_zero(&wish.since) && !wish.fallback)
		snprintf(waited, sizeof(waited), " (the straight ring waited %ld ms for it)", ms_since(&wish.since));
	info("warp            claimed%s: three %ux%u NV12 buffers, line pitch %u, chroma at %u, video plane %u%s%s",
	     client ? " for a Wayland client (no signal needed, the HDMI sound silent)" : "",
	     d->width, d->height, warp.pitch, warp.coff, d->plane_id,
	     cover.on ? " -- under an opaque page: it pauses at once, the video plane stays off" :
	     was_on ? " -- the straight ring off, the first frame turns the plane on" :
	     " -- the video plane is off and comes on with the first frame", waited);
	/* claimed under a page: the video plane is off (display_hide above) and stays off; the warp draws from the page's end */
	if (cover.on)
		cover.plane_off = true;	/* "ctl status": off under the page (it said "could not go off" for a claim made under it) */
	if (cover.on && !warp_note("note cover on\n"))
		warn("warp            \"note cover on\" did not go (%s) -- the warp draws under the page", strerror(errno));
	return false;
}

/*
 * "warp switch client|ring" on a standing claim (see "The warp" above): the same three buffers, the master and the
 * video plane stay, and h713-warp draws the other source into them. Allowed under the same rules as a claim of
 * that source. True when it switched; the answer, "ok source X" or "error ...", goes into ans.
 */
static bool warp_switch(struct capture *cap, struct display *d, const char *what, char *ans, size_t n)
{
	bool client = !strcmp(what, "client");
	struct v4l2_dv_timings t;
	int sig;

	if (!client && strcmp(what, "ring")) {
		snprintf(ans, n, "error warp switch takes client or ring, not \"%s\"\n", what);
		return false;
	}
	if (client == warp.client) {
		snprintf(ans, n, "ok source %s -- already %s\n", source_name[ctl.source], what);
		return false;
	}
	if (ctl.policy == POLICY_OFF) {
		snprintf(ans, n, "error console forced (\"ctl off\") -- the claim stays as it is\n");
		return false;
	}
	if (client ? ctl.source == SOURCE_HDMI : ctl.source == SOURCE_CLIENT) {
		snprintf(ans, n, "error source is %s -- no switch to the %s\n", source_name[ctl.source], what);
		return false;
	}
	if (client && !d->crtc_props.list)
		props_get(d->fd, d->crtc_id, DRM_MODE_OBJECT_CRTC, &d->crtc_props);
	if (client && !prop_id(&d->crtc_props, "OUT_FENCE_PTR")) {
		snprintf(ans, n, "error CRTC %u has no OUT_FENCE_PTR -- a client cannot be paced\n", d->crtc_id);
		return false;
	}
	if (!client) {
		/* a client's claim leaves the signal unmeasured (evaluate() returns early): measured now */
		sig = capture_signal(cap, &t);
		cap->last_sig = sig;
		if (sig != 2)
			cap->last_t = t;
		if (sig != 1) {
			snprintf(ans, n, "error no signal to warp -- the claim stays as it is\n");
			return false;
		}
	}
	warp.client = client;
	warp.told = (int)ctl.source;
	warp_revoke_stop();
	memset(&warp.last_frame, 0, sizeof(warp.last_frame));
	if (!client && warp.flip >= 0) {	/* the ring is paced by the capture, not by flips */
		close(warp.flip);
		warp.flip = -1;
	}
	info("warp            switched to %s on the same three buffers -- the video plane stays up (%lu commits so far)",
	     client ? "a Wayland client (the HDMI sound silent)" : "the ring", warp.commits);
	snprintf(ans, n, "ok source %s\n", source_name[ctl.source]);

	return true;
}

/* The peer's connection: one line per message, and the daemon waits for the
 * answer before the next, so a line cannot arrive in halves. True when the
 * caller has to run evaluate() -- the warp has just ended, or switched (the
 * sound follows what is drawn).
 */
static bool warp_serve(struct capture *cap, struct display *d)
{
	char cbuf[CMSG_SPACE(sizeof(int))] = { 0 }, buf[128], told[96], what[16];
	const char *answer = "error unknown (warp frame N | warp switch client|ring | warp release)\n";
	bool switched = false;
	struct iovec io = { buf, sizeof(buf) - 1 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1,
			      .msg_control = cbuf, .msg_controllen = sizeof(cbuf) };
	struct cmsghdr *cm;
	bool busy = false;
	ssize_t got;
	int fence = -1, n = -1, flip = -1;

	got = recvmsg(warp.peer, &msg, MSG_DONTWAIT);
	if (got <= 0) {			/* the daemon is gone: A2's lifetime */
		if (!nosig_linger(d))
			warp_release(d);
		return true;
	}
	buf[got] = '\0';
	buf[strcspn(buf, "\r\n")] = '\0';
	for (cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm))
		if (cm->cmsg_level == SOL_SOCKET && cm->cmsg_type == SCM_RIGHTS)
			memcpy(&fence, CMSG_DATA(cm), sizeof(fence));
	if (!strcmp(buf, "warp release")) {
		if (send(warp.peer, "ok\n", 3, MSG_NOSIGNAL) < 0)
			warn("warp            answering the release: %s", strerror(errno));
		if (!nosig_linger(d))
			warp_release(d);
		return true;
	}
	if (sscanf(buf, "warp switch %15s", what) == 1) {
		switched = warp_switch(cap, d, what, told, sizeof(told));
		answer = told;
	} else if (sscanf(buf, "warp frame %d", &n) == 1 && n >= 0 && n < WARP_BUFS)
		{
			/*
			 * A frame that arrived late, or a commit that took long: the
			 * loop was held (23.09.: a status with its two firmware-backed
			 * sysfs reads, 50 ms; "status brief" reads nothing back). Counted,
			 * and said at most every TIMING_SAY_S with the worst of each: a
			 * line per frame was 27 lines a second when the source sends 30
			 * distinct frames (a still picture, 11.10.2026, HY300PRO-G-EU):
			 * 1.5 % of a core in journald, ~100 000 lines an hour in RAM.
			 */
			static struct timespec said;
			static unsigned long late, slow;
			static double late_worst, slow_worst;
			struct timespec c0, c1, prev = warp.last_frame;
			double gap, took;

			clock_gettime(CLOCK_MONOTONIC, &c0);
			gap = prev.tv_sec ? (c0.tv_sec - prev.tv_sec) * 1e3 + (c0.tv_nsec - prev.tv_nsec) / 1e6 : 0;
			/* under an opaque page the video plane is off and stays off: a frame sent before the warp heard the
			 * page is answered and not shown (the warp draws nothing more after "note cover on") */
			if (cover.on)
				answer = "ok\n";
			else
				answer = warp_commit(d, n, fence, &busy, &flip) ? "ok\n" :
					 busy ? "ok busy\n" : "error the commit was refused\n";
			if (!cover.on && answer[2] == '\n') {
				cover_resume_stop();	/* the first frame after a page carried the overlay's change */
				cover.plane_off = false;	/* ... and turned the video plane on again */
				if (warp.commits == 1) {	/* the claim's first frame: the plane is on, the wait is over */
					info("warp            first frame: the video plane on with h713-warp's picture, %ld ms after the claim",
					     ms_since(&warp.claimed_at));
					want_hold_end();
				}
			}
			/* "source" changed while the claim stood: the next "ok" says so, h713-warp reads it there */
			if (!strncmp(answer, "ok", 2) && warp.told != (int)ctl.source) {
				snprintf(told, sizeof(told), "%.*s source %s\n", (int)strcspn(answer, "\n"), answer,
					 source_name[ctl.source]);
				answer = told;
				warp.told = (int)ctl.source;
			}
			clock_gettime(CLOCK_MONOTONIC, &c1);
			took = (c1.tv_sec - c0.tv_sec) * 1e3 + (c1.tv_nsec - c0.tv_nsec) / 1e6;
			if (gap > 25.0 && !warp.client) {	/* a client draws when it has something to show */
				late++;
				if (gap > late_worst)
					late_worst = gap;
			}
			if (took > 10.0) {
				slow++;
				if (took > slow_worst)
					slow_worst = took;
			}
			if ((late || slow) && c1.tv_sec - said.tv_sec >= TIMING_SAY_S) {
				if (said.tv_sec)
					info("timing          in %ld s: %lu warp frames more than 25 ms after the previous one (worst %.1f ms), %lu commits over 10 ms (worst %.1f ms)",
					     (long)(c1.tv_sec - said.tv_sec), late, late_worst, slow, slow_worst);
				said = c1;
				late = slow = 0;
				late_worst = slow_worst = 0;
			}
			warp.last_frame = c1;
		}
	if (fence >= 0)
		close(fence);
	if (flip >= 0) {
		/* the client's flip fence goes with the "ok"; our dup is what an overlay change waits for */
		char fbuf[CMSG_SPACE(sizeof(int))] = { 0 };
		struct iovec fio = { (void *)(uintptr_t)answer, strlen(answer) };
		struct msghdr fm = { .msg_iov = &fio, .msg_iovlen = 1, .msg_control = fbuf,
				     .msg_controllen = sizeof(fbuf) };
		struct cmsghdr *fc = CMSG_FIRSTHDR(&fm);
		ssize_t sent;

		fc->cmsg_level = SOL_SOCKET;
		fc->cmsg_type = SCM_RIGHTS;
		fc->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(fc), &flip, sizeof(int));
		sent = sendmsg(warp.peer, &fm, MSG_NOSIGNAL);
		if (warp.flip >= 0)
			close(warp.flip);
		warp.flip = flip;
		if (sent >= 0)
			return false;
	} else if (send(warp.peer, answer, strlen(answer), MSG_NOSIGNAL) >= 0) {
		return switched;
	}
	warn("warp            answering \"%s\": %s", buf, strerror(errno));
	warp_release(d);

	return true;
}

/*
 * "warp want ring|none" (P3, see want above): h713-warp's word whether it claims the ring when it may. The first line makes
 * the connection h713-warp's want connection - it stays open, "note claim" goes back on it, and a newer one replaces it (a
 * restarted h713-warp); later lines come through want_serve(). True: the caller has to run evaluate() - the straight ring
 * no longer waits ("none"), or a new h713-warp says "ring" and the wait (with its "note claim") begins anew.
 */
static bool cmd_warp_want(struct reply *r, int conn, const char *what)
{
	bool ring = what && !strcmp(what, "ring"), fresh = conn != wish.peer, was = warp_wants_ring();

	if (!what || (!ring && strcmp(what, "none"))) {
		reply_fail(r, "warp want takes ring or none, not \"%s\"", what ? what : "");
		return false;
	}
	if (conn < 0) {
		reply_fail(r, "\"warp want\" needs the connection it is sent on");
		return false;
	}
	if (fresh) {
		if (wish.peer >= 0)
			close(wish.peer);	/* an older h713-warp's: the newer one's word counts */
		wish.peer = conn;
		memset(&wish.gone, 0, sizeof(wish.gone));
		wish.noted = false;
	}
	wish.ring = ring;
	reply_add(r, "ok want %s\n", ring ? "ring" : "none");
	if (fresh || was != ring)
		info("warp            h713-warp %s: %s", fresh ? "says" : "says now",
		     ring ? "it claims the ring when it may -- the straight ring waits for its claim (at most 1000 ms)" :
		     "it will not claim the ring -- the straight ring at once");
	if (!ring) {
		bool waiting = !ts_zero(&wish.since);

		want_hold_end();
		return waiting;
	}
	if (fresh && !ts_zero(&wish.since) && !wish.fallback) {
		clock_gettime(CLOCK_MONOTONIC, &wish.since);	/* a restarted h713-warp: its time begins now */
		want_disarm();
	}
	return fresh;
}

/* h713-warp's want connection is readable: its lines, or its end. True: the caller has to run evaluate(). */
static bool want_serve(void)
{
	char buf[256], *line, *next;
	bool again = false;
	ssize_t got;

	got = recv(wish.peer, buf, sizeof(buf) - 1, MSG_DONTWAIT);
	if (got < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
		return false;
	if (got <= 0) {
		close(wish.peer);
		wish.peer = -1;
		if (wish.ring)
			clock_gettime(CLOCK_MONOTONIC, &wish.gone);
		info("warp            h713-warp's want connection closed%s", wish.ring ?
		     " -- \"ring\" stands for 1000 ms more (a restart comes back within it)" : "");
		return false;	/* a wait that runs ends with its timer */
	}
	buf[got] = '\0';
	for (line = buf; *line; line = next) {
		struct reply r = { .len = 0, .failed = false };
		char *save = NULL, *w1, *w2, *w3;

		next = line + strcspn(line, "\n");
		if (*next)
			*next++ = '\0';
		line[strcspn(line, "\r")] = '\0';
		w1 = strtok_r(line, " \t", &save);
		w2 = strtok_r(NULL, " \t", &save);
		w3 = strtok_r(NULL, " \t", &save);
		if (!w1)
			continue;
		if (w2 && !strcmp(w1, "warp") && !strcmp(w2, "want"))
			again |= cmd_warp_want(&r, wish.peer, w3);
		else
			reply_fail(&r, "this connection takes \"warp want ring|none\" only");
		if (wish.peer >= 0 && send(wish.peer, r.buf, r.len, MSG_NOSIGNAL | MSG_DONTWAIT) < 0)
			warn("warp            answering h713-warp's want line: %s", strerror(errno));
	}
	return again;
}

/* the end of the wait: WARP_HOLD_MS are over - evaluate() decides (the ring, unless the claim came in time) */
static bool want_hold_due(void)
{
	uint64_t ticks;

	if (read(wish.fd, &ticks, sizeof(ticks)) != sizeof(ticks))
		ticks = 0;
	wish.armed = false;
	return !ts_zero(&wish.since) && !warp.claimed;
}

/* warp [status] for the human; "claim" is h713-warp's (A1) */
static bool cmd_warp(struct reply *r, struct capture *cap, struct display *d, const char *what,
		     const char *src, int conn)
{
	if (what && !strcmp(what, "claim")) {
		bool again = cmd_warp_claim(r, cap, d, conn, src);

		return again || (warp.claimed && warp.client);	/* the ring after a failed wait; the sound goes quiet behind a client */
	}
	if (what && !strcmp(what, "want"))
		return cmd_warp_want(r, conn, src);
	if (what && strcmp(what, "status"))
		reply_fail(r, "warp knows \"status\" here; on, off and the keystone are h713-warp ctl");
	else if (!warp.claimed)
		reply_add(r, "ok warp off -- nothing claimed; \"h713-warp ctl status\" says why\n");
	else
		reply_add(r, "ok warp on -- h713-warp draws %s, video plane %u, %ux%u NV12, line pitch %u, %lu commits, %lu busy, %lu refused\n",
			  warp.client ? "a Wayland client" : "the ring", d->plane_id, d->width, d->height,
			  warp.pitch, warp.commits, warp.busy, warp.errors);
	return false;
}

/*
 * The source no longer allows the standing claim: h713-warp hears it at once, unasked, on the claim's connection
 * ("note source hdmi"), and switches the claim to what is allowed or gives it back; a client at rest sends no
 * frame whose answer could carry it. WARP_REVOKE_MS later the claim is released here if it still stands - an
 * h713-warp that cannot switch, or one of before 16.10.2026, which knows no notes.
 */
static void warp_revoke(struct display *d)
{
	struct itimerspec its = { .it_value = { WARP_REVOKE_MS / 1000, (WARP_REVOKE_MS % 1000) * 1000000L } };
	char line[32];
	int len = snprintf(line, sizeof(line), "note source %s\n", source_name[ctl.source]);

	if (warp.revoke_fd < 0)
		warp.revoke_fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (warp.peer < 0 || warp.revoke_fd < 0 ||
	    send(warp.peer, line, (size_t)len, MSG_NOSIGNAL | MSG_DONTWAIT) != len ||
	    timerfd_settime(warp.revoke_fd, 0, &its, NULL)) {
		warn("warp            h713-warp could not be told (%s) -- the claim is given back", strerror(errno));
		warp_release(d);
		return;
	}
	warp.told = (int)ctl.source;
	warp.revoking = true;
}

/* the source to h713-warp on a claim that stands: a client claim at rest sends no frame whose "ok" could carry it */
static void warp_tell_source(void)
{
	char line[32];

	snprintf(line, sizeof(line), "note source %s\n", source_name[ctl.source]);
	if (warp_note(line))
		warp.told = (int)ctl.source;
	else
		warn("warp            \"%.*s\" did not go (%s) -- h713-warp hears it with its next frame",
		     (int)strlen(line) - 1, line, strerror(errno));
}

/* a change that waited for a warp frame goes on its own: the frame did not come */
static void osd_flush(struct display *d)
{
	if (!osd.queued)
		return;
	osd.queued = false;
	if (osd.want < 0 || bare.on) {
		osd_drop(d);
		osd_uncover(d);
	} else if (osd_commit(d, osd.fb_id[osd.want], 2)) {
		osd.shown = true;
		osd.shows++;
	}
}

/*
 * After every handler of the loop: is an opaque page on the wall now (cover)? A change goes to h713-warp ("note cover
 * on|off") and to the sound. When the page goes, the overlay's change waits for the warp's next frame - the first after
 * the pause, so that the wall goes from the page to a new picture in one commit (osd_alone()) - but no longer than
 * COVER_RESUME_MS; then it goes on its own (cover_resume_due()).
 */
static void reevaluate(struct capture *cap, struct display *d, struct retry *rt, struct audio *a);

static void cover_follow(struct capture *cap, struct display *d, struct retry *rt, struct audio *a)
{
	struct itimerspec its = { .it_value = { 0, COVER_RESUME_MS * 1000000L } };
	bool on = osd_covering();

	if (on == cover.on)
		return;
	cover.on = on;
	memset(&warp.last_frame, 0, sizeof(warp.last_frame));	/* a pause is not a late frame */
	audio_cover(a, on);
	if (!warp.claimed) {
		/* the ring straight on the video plane (no warp): off under the page, and back from evaluate() after it */
		info("cover           %s", on ? "an opaque page is on the wall -- the video plane goes off under it" :
		     "the page is gone -- the picture comes back");
		if (on && d->on && !under_black_up(d))
			display_hide(d);	/* the page stays, over black (osd_on_panel()) */
		else if (!on)
			reevaluate(cap, d, rt, a);
		return;
	}
	if (warp.peer < 0) {		/* a claim whose daemon let go (nosig_linger()): nobody to tell, it is released under the page */
		if (!on)
			osd_flush(d);
		return;
	}
	if (!warp_note(on ? "note cover on\n" : "note cover off\n")) {
		warn("warp            \"note cover %s\" did not go (%s)", on ? "on" : "off", strerror(errno));
		if (!on)
			osd_flush(d);
		return;
	}
	info("cover           %s", on ? "an opaque page hides the picture -- h713-warp pauses, the video plane goes off, the HDMI sound is muted" :
	     "the page is gone -- h713-warp draws again, its first frame turns the video plane on and carries the change");
	if (on && d->warped) {
		int rc = under_black_up(d) ? 0 : display_plane_off(d);	/* the page stays on the primary plane: osd_wanted() keeps it */

		cover.plane_off = !rc;
		if (rc)
			warn("cover           the video plane did not go off under the page (%s)", rc == -1 ? strerror(errno) : "a property is missing");
	}
	if (on || !osd.queued)
		return;
	if (cover.resume_fd < 0)
		cover.resume_fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	cover.resuming = cover.resume_fd >= 0 && !timerfd_settime(cover.resume_fd, 0, &its, NULL);
	if (!cover.resuming)
		osd_flush(d);
}

/*
 * Is the HDMI capture needed now? Not under an opaque page, not while a program is the mode ("source client", or a client drawn under
 * "auto"). This is the one place that knows when the box leaves the mode HDMI and when it comes back: today it says so in the journal;
 * the firmware's own switch of its capture (P7 of the media side project, THal_Vp_SetSource) belongs here, behind the pause, which
 * already stops everything of ours.
 */
static void capture_follow(void)
{
	static int need = -1;
	int n = !cover.on && ctl.source != SOURCE_CLIENT && !(warp.claimed && warp.client);

	if (n == need)
		return;
	need = n;
	info("capture         %s", n ? "needed: HDMI is the mode and on the wall" :
	     cover.on ? "not needed: an opaque page covers the panel" : "not needed: a program is the mode");
}

/*
 * No signal as a page: the functions (the story is with struct nosig). The page can stand for "no signal" when h713-osd is here, the
 * console is not forced and no program is the mode - under a program the signal is none of the wall's business.
 */
static bool nosig_page_ok(void)
{
	return osd.claimed && osd.peer >= 0 && ctl.policy != POLICY_OFF && ctl.source != SOURCE_CLIENT && !(warp.claimed && warp.client);
}

/*
 * An opaque page goes ("osd hide") with no picture under it, and evaluate() is to put the straight ring up next: the page was
 * covering, the mode is HDMI with a signal, no console forced, no claim of h713-warp's (whose first frame carries a page's end
 * already, cover_follow()). Then the page stays on the plane as it is: cover_follow() re-evaluates at once, and display_show()
 * puts the ring on the video plane and the console's framebuffer under it in one commit - from the page to the picture with
 * nothing between. If evaluate() decides on no picture after all, display_hide() drops the page and gives the console back as
 * before. Until 20.10.2026 the page went first, alone, and the console stood on the wall for the 0.1 s until the ring came
 * (HY300PRO-G-EU without a keystone: after every closed launcher and after the page without a signal - so after every wake).
 * The same when the page goes for a popup that stays ("osd show N" without "cover": the mute badge after a closed launcher,
 * 0.10-0.12 s of console until 20.10.2026): the page stays, and the ring's commit lays the popup over the picture.
 */
static bool osd_handover(const struct display *d)
{
	return !d->on && !d->warped && osd.shown && cover.on && !warp.claimed && !nosig.lost && ctl.policy != POLICY_OFF &&
	       ctl.source != SOURCE_CLIENT;
}

/*
 * The wall black between a client's release and the straight ring (TODO 2.124). From Kodi to HDMI without a keystone h713-warp
 * gives its client claim back, and the straight ring follows a tenth of a second later (evaluate(): the signal measured, the
 * ring's descriptor published, the firmware's chain rebuilt); the release put the console's framebuffer up for that tenth
 * (HY300PRO-G-EU, 20.10.2026: 0.12 s). Now the release puts a black framebuffer of this program's up when the ring is to
 * come, keeps the master, and the ring's commit takes the wall from it, as from a page that goes before the ring
 * (osd_handover()). Whatever comes instead - no signal, "off", a page, a new claim - takes the wall in its own commit, and the
 * master never goes while the black framebuffer is on the plane: the console's goes up first (wall_black_end()). It is never
 * removed while it is shown either: removing the primary plane's framebuffer switches the CRTC off (atomic_remove_fb), and no
 * h713-tv starts after that (TODO 2.125). Made when it is needed, freed when the plane holds another: 3.7 MB of CMA at 720p,
 * 8.3 MB at 1080p, for a tenth of a second. The same wall stands when a keystone goes (h713-warp gives its ring claim back) and
 * when one comes (the straight ring goes for the claim's first frame, ring_off_for_claim()).
 */
static struct {
	uint32_t handle, fb_id;
} wall_black;

static bool leaving;		/* the way out: nothing is to follow */

static bool wall_black_is(uint32_t fb)
{
	return fb && fb == wall_black.fb_id;
}

/*
 * A claim goes, and the straight ring is to come: the mode is HDMI, nothing forces the console, no opaque page on the wall (a
 * popup that rode on the picture - the mute badge over Kodi - comes back with the ring's commit) - and for a
 * claim of the ring the signal stands (the keystone set back to the identity: h713-warp gives the ring back, 0.10-0.12 s of
 * console until 20.10.2026; a claim that goes with the signal is the page's or the console's, as before). The signal is not
 * followed under a client's claim, so there it is not asked.
 */
static bool wall_black_wanted(const struct display *d)
{
	return (warp.client || !nosig.lost) && !leaving && !d->on && !osd_covering() && !cover.on && ctl.policy != POLICY_OFF &&
	       ctl.source != SOURCE_CLIENT;
}

/* the dumb buffer gone, once no plane shows its framebuffer (or there is none) */
static void wall_black_free(struct display *d)
{
	struct drm_mode_destroy_dumb dreq = { .handle = wall_black.handle };

	if (wall_black.fb_id) {
		drmModePlane *p = drmModeGetPlane(d->fd, osd.plane_id);
		bool shown = !p || p->fb_id == wall_black.fb_id;

		if (p)
			drmModeFreePlane(p);
		if (shown)
			return;		/* on the plane, or not known: it stays */
		drmModeRmFB(d->fd, wall_black.fb_id);
	}
	if (wall_black.handle)
		drmIoctl(d->fd, DRM_IOCTL_MODE_DESTROY_DUMB, &dreq);
	wall_black.fb_id = wall_black.handle = 0;
}

/* the video plane off and a black framebuffer of the panel's size on the primary plane, zpos 0, in one commit; false: nothing
 * changed, the caller does what it did before. The console's framebuffer has to be known, for wall_black_end() */
static bool wall_black_up(struct display *d)
{
	struct drm_mode_create_dumb creq = { .width = d->width, .height = d->height, .bpp = 32 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	drmModeAtomicReq *req;
	bool ok;

	if (!d->master || !osd_learn(d) || !osd.console_fb)
		return false;
	if (!wall_black.fb_id) {
		if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &creq)) {
			warn("wall            no black framebuffer (%s) -- the console, as before", strerror(errno));
			return false;
		}
		wall_black.handle = handles[0] = creq.handle;
		pitches[0] = creq.pitch;
		if (drmModeAddFB2(d->fd, d->width, d->height, DRM_FORMAT_XRGB8888, handles, pitches, offsets,
				  &wall_black.fb_id, 0)) {
			wall_black.fb_id = 0;
			wall_black_free(d);
			return false;
		}
	}
	req = drmModeAtomicAlloc();
	ok = req && add(req, d, "FB_ID", 0) && add(req, d, "CRTC_ID", 0) && osd_props(req, d, wall_black.fb_id, 0) &&
	     !drmModeAtomicCommit(d->fd, req, 0, NULL);
	if (req)
		drmModeAtomicFree(req);
	if (!ok) {
		warn("wall            the black framebuffer did not go up (%s) -- the console, as before", strerror(errno));
		wall_black_free(d);
		return false;
	}
	under.up = false;	/* the video plane is off */
	osd.shown = false;	/* a popup that rode on the picture is off the plane now; the ring's commit lays it again */
	return true;
}

/*
 * The straight ring goes for h713-warp's claim (a keystone set from the identity): its first frame comes 30 ms later and turns the
 * video plane on again. The wall is black for those 30 ms, not the console (0.03 s of console until 20.10.2026); with a page on
 * the wall, or without a black framebuffer, display_hide() as before.
 */
static bool ring_off_for_claim(struct display *d)
{
	if (!d->on || osd_covering() || cover.on || !wall_black_up(d))
		return display_hide(d);
	d->on = false;
	info("wall            black -- the straight ring goes for h713-warp's first frame");
	return true;
}

/* before the master goes: the console's framebuffer over the black one, then the black one away */
static void wall_black_end(struct display *d)
{
	drmModePlane *p;
	bool shown;

	if (!wall_black.fb_id || !d->master)
		return;
	p = drmModeGetPlane(d->fd, osd.plane_id);
	shown = p && p->fb_id == wall_black.fb_id;
	if (p)
		drmModeFreePlane(p);
	if (shown && !osd_commit(d, osd.console_fb, 0))
		warn("wall            the console's framebuffer did not go over the black one -- it stays until the plane changes");
	wall_black_free(d);
}

/* what h713-osd is to hear: "none" while the page is wanted; "off" when there is no signal and no page (console forced, a program);
 * else the signal's name */
static const char *nosig_word(void)
{
	if (nosig.lost)
		return nosig_page_ok() ? "none" : "off";
	return nosig.text[0] ? nosig.text : "ok";
}

static void nosig_said(bool said)
{
	nosig.said = said;
}

/* h713-osd hears a change of the word, once */
static void nosig_tell(void)
{
	bool want = nosig.lost && nosig_page_ok();
	char line[96];
	int len;

	if (osd.peer < 0 || !osd.claimed) {
		nosig.said = false;
		return;
	}
	if (want == nosig.said)
		return;
	len = snprintf(line, sizeof(line), "note signal %s\n", nosig_word());
	if (len <= 0 || send(osd.peer, line, (size_t)len, MSG_NOSIGNAL | MSG_DONTWAIT) != len) {
		warn("nosignal       \"note signal ...\" did not go (%s) -- h713-osd hears it at its next claim", strerror(errno));
		return;
	}
	nosig.said = want;
	info("nosignal       h713-osd is told: %s", want ? "no signal -- its page \"No signal on HDMI\"" :
	     nosig.lost ? "no page (the console forced, or a program the mode) -- the page goes" : "the signal is back -- the page goes");
}

/*
 * evaluate() found nothing to show in the mode HDMI. decided: no signal, or one the display cannot take (not a change in flight, not a
 * reading that failed). True: the picture on the wall stays for now, the page is on its way (the caller returns).
 */
static bool nosig_defer(struct display *d, struct retry *rt, bool decided)
{
	long left;

	if (!decided)
		return false;
	if (!nosig.lost) {
		nosig.lost = true;
		memset(&nosig.back, 0, sizeof(nosig.back));
		memset(&nosig.since, 0, sizeof(nosig.since));
		nosig.text[0] = '\0';
		info("nosignal       nothing to show in the mode HDMI%s", nosig_page_ok() ? " -- h713-osd is to put its page up" :
		     " -- no page (h713-osd not claimed, the console forced or a program the mode): the console");
	}
	if (!nosig_page_ok() || osd_covering() || !(d->on || d->warped))
		return false;		/* no page wanted, the page already stands, or no picture to hold */
	if (ts_zero(&nosig.since))
		clock_gettime(CLOCK_MONOTONIC, &nosig.since);
	left = NOSIG_WAIT_MS - ms_since(&nosig.since);
	if (left <= 0) {
		warn("nosignal       h713-osd put no page up within %d ms -- the console after all", NOSIG_WAIT_MS);
		return false;
	}
	retry_arm(rt, (unsigned int)left + 5);
	return true;
}

/*
 * h713-warp lets go of its claim (its own QUERY_DV_TIMINGS saw the signal go too, a tenth of a second after this program did) while h713-osd's
 * page is not on the wall yet: the claim stays, without its connection, and with it the last frame on the video plane - until the page covers
 * (nosig_follow() then releases the claim under it, evaluate()) or NOSIG_WAIT_MS are over. Releasing at once gave the console for that tenth of a
 * second (HY310, 17.10.2026, journal: the release, then the page 150 ms later). True: the release is left for later.
 */
static bool nosig_linger(struct display *d)
{
	if (!warp.claimed || warp.client || !d->warped || !nosig.lost || !nosig_page_ok() || osd_covering())
		return false;
	if (!ts_zero(&nosig.since) && ms_since(&nosig.since) >= NOSIG_WAIT_MS)
		return false;
	if (ts_zero(&nosig.since))
		clock_gettime(CLOCK_MONOTONIC, &nosig.since);
	if (warp.peer >= 0)
		close(warp.peer);
	warp.peer = -1;
	warp_revoke_stop();
	info("nosignal       h713-warp let go -- its claim and the last frame stay until the page is up (at most %d ms)", NOSIG_WAIT_MS);
	return true;
}

/*
 * evaluate() measured a signal the display can take. The page goes with the word "signal"; with a claim of h713-warp's to come it goes
 * after the claim, at most WARP_HOLD_MS (nosig_claimed(), nosig_follow()).
 */
static void nosig_back(struct retry *rt, const struct v4l2_dv_timings *t)
{
	char text[64];

	snprintf(nosig.text, sizeof(nosig.text), "%s", signal_text(t, text, sizeof(text)));
	memset(&nosig.since, 0, sizeof(nosig.since));
	if (!nosig.lost)
		return;
	if (nosig_page_ok() && warp_wants_ring() && !warp.claimed) {
		long left;

		if (ts_zero(&nosig.back))
			clock_gettime(CLOCK_MONOTONIC, &nosig.back);
		left = WARP_HOLD_MS - ms_since(&nosig.back);
		if (left > 0) {
			retry_arm(rt, (unsigned int)left + 5);
			return;
		}
		warn("nosignal       h713-warp made no claim within %d ms -- the page goes without it", WARP_HOLD_MS);
	}
	nosig.lost = false;
	memset(&nosig.back, 0, sizeof(nosig.back));
	info("nosignal       the signal is back (%s)", nosig.text);
}

/* after every handler of the loop: h713-osd hears a change; a claim that stood while the page came goes under the page now */
static void nosig_follow(struct capture *cap, struct display *d, struct retry *rt, struct audio *a)
{
	nosig_tell();
	/* the signal went, the last picture stayed for the page, the page is on the wall now: the claim goes under it */
	if (nosig.lost && warp.claimed && !warp.client && cover.on && cap->last_sig != 1) {
		reevaluate(cap, d, rt, a);
		nosig_tell();
	}
}

/* COVER_RESUME_MS after "note cover off" and no frame of h713-warp's: the overlay's change on its own */
static void cover_resume_due(struct display *d)
{
	uint64_t ticks;

	if (read(cover.resume_fd, &ticks, sizeof(ticks)) != sizeof(ticks))
		ticks = 0;
	if (!cover.resuming)
		return;
	cover.resuming = false;
	if (!osd.queued)
		return;
	warn("cover           h713-warp drew no frame within %d ms of \"note cover off\" -- the overlay's change goes on its own",
	     COVER_RESUME_MS);
	osd_flush(d);
}

/* the grace is over: a claim the source still does not allow is released here */
static bool warp_revoke_due(struct display *d)
{
	uint64_t ticks;
	bool stands = warp.claimed && (warp.client ? ctl.source != SOURCE_HDMI : ctl.source != SOURCE_CLIENT);

	if (read(warp.revoke_fd, &ticks, sizeof(ticks)) != sizeof(ticks))
		ticks = 0;
	if (!warp.revoking)
		return false;
	warp.revoking = false;
	if (!warp.claimed || stands)
		return false;
	warn("warp            h713-warp neither switched nor gave the claim back within %d ms of \"source %s\" -- released here",
	     WARP_REVOKE_MS, source_name[ctl.source]);
	warp_release(d);

	return true;
}

/*
 * "source [hdmi|client|auto]": what the panel shows - the mode. "hdmi" is the HDMI input; "client" is a program (a mode
 * unit says it at its start): its picture only, never the ring - while the program starts, between two programs and
 * while one builds its window anew, h713-warp keeps the last picture on the video plane until the program's first
 * (P2b of the media side project: HDMI is a mode, not what fills a gap); "auto" is the client while there is one and
 * the ring otherwise (the test clients', and h713-warp's own once a program has ended for good).
 * A standing warp claim the new policy forbids - a ring claim under "client", a client claim under "hdmi" - is said
 * to h713-warp at once (warp_revoke()), which switches it to the source that is allowed or gives it back. One it
 * allows stands - giving it back took the panel off the ring and back for "hdmi" <-> "auto" (the wall blinked) - and
 * h713-warp hears the new policy at once all the same ("note source auto"): a client claim at rest sends no frame
 * whose answer could carry it. "client" said again while a claim stands is a program that starts: h713-warp hears
 * that too, it decides whether a picture between two programs is held (a program follows) or the program has ended.
 * h713-warp asks again at once after a release and learns the policy from the answer.
 * Not saved; "source =" in tv.conf is the start value.
 */
static bool cmd_source(struct reply *r, struct display *d, const char *what)
{
	int s = what ? source_by_name(what) : ctl.source;

	if (s < 0) {
		reply_fail(r, "source takes hdmi, client or auto, not \"%s\"", what);
		return false;
	}
	if (what && s != ctl.source) {
		bool stands = warp.claimed && (warp.client ? s != SOURCE_HDMI : s != SOURCE_CLIENT);

		ctl.source = s;
		info("source          %s%s", source_name[s], !warp.claimed ? "" : stands ?
		     " -- the warp's claim stands, h713-warp is told" :
		     " -- h713-warp is told: it switches the claim or gives it back");
		if (!stands)
			warp_revoke(d);
		else
			warp_tell_source();
		reply_add(r, "ok source %s\n", source_name[s]);
		return true;		/* the ring, the console, or the claim h713-warp sends next */
	}
	if (what && s == SOURCE_CLIENT && warp.claimed) {
		info("source          client again -- a program starts, h713-warp is told");
		warp_tell_source();
	}
	reply_add(r, "ok source %s%s\n", source_name[s],
		  !warp.claimed ? "" : warp.client ? " -- h713-warp shows a Wayland client" : " -- h713-warp shows the ring");
	return false;
}

/* "osd claim": the two buffers, their fds with the answer */
static void cmd_osd_claim(struct reply *r, struct display *d, int conn)
{
	char cbuf[CMSG_SPACE(sizeof(int) * OSD_BUFS)] = { 0 }, line[64];
	int fds[OSD_BUFS] = { -1, -1 };
	struct iovec io = { line, 0 };
	struct msghdr msg = { .msg_iov = &io, .msg_iovlen = 1,
			      .msg_control = cbuf, .msg_controllen = sizeof(cbuf) };
	struct cmsghdr *cm;
	int i, bad;

	if (osd.claimed || conn < 0) {
		reply_fail(r, "%s", osd.claimed ? "the overlay is already claimed"
			   : "\"osd claim\" needs the connection it is sent on");
		return;
	}
	if (!osd_find_plane(d)) {
		reply_fail(r, "no primary plane with zpos and ARGB8888 on CRTC %u -- kernel 0251?", d->crtc_id);
		return;
	}
	/* the console's framebuffer, read again: nothing of ours is on the plane before a claim */
	osd.console_known = false;
	osd_learn(d);
	bad = !osd_alloc(d, fds);
	if (bad) {
		reply_fail(r, "the two %ux%u ARGB8888 buffers could not be made: %s", d->width,
			   d->height, strerror(errno));
	} else {
		io.iov_len = (size_t)snprintf(line, sizeof(line), "ok %u %u %u argb8888\n",
					      d->width, d->height, osd.pitch);
		cm = CMSG_FIRSTHDR(&msg);
		cm->cmsg_level = SOL_SOCKET;
		cm->cmsg_type = SCM_RIGHTS;
		cm->cmsg_len = CMSG_LEN(sizeof(int) * OSD_BUFS);
		memcpy(CMSG_DATA(cm), fds, sizeof(int) * OSD_BUFS);
		bad = sendmsg(conn, &msg, MSG_NOSIGNAL) < 0;
		if (bad)
			reply_fail(r, "the buffers could not be handed over: %s", strerror(errno));
	}
	for (i = 0; i < OSD_BUFS; i++)
		if (fds[i] >= 0)
			close(fds[i]);	/* the peer has its own copies now */
	if (bad) {
		osd_free(d);
		return;
	}
	osd.claimed = true;
	osd.peer = conn;
	osd.want = -1;
	nosig_said(false);	/* a new h713-osd knows nothing: it asks */
	info("osd             claimed: two %ux%u ARGB8888 buffers, line pitch %u, primary plane %u, console framebuffer %u",
	     d->width, d->height, osd.pitch, osd.plane_id, osd.console_fb);
}

/* osd [status] for the human; "claim" is h713-osd's */
static void cmd_osd(struct reply *r, struct display *d, const char *what, int conn)
{
	if (what && !strcmp(what, "claim"))
		cmd_osd_claim(r, d, conn);
	else if (what && strcmp(what, "status"))
		reply_fail(r, "osd knows \"status\" here; the overlays are h713-osd ctl");
	else if (!osd.claimed)
		reply_add(r, "ok osd off -- nothing claimed\n");
	else
		reply_add(r, "ok osd claimed -- %s, primary plane %u, %ux%u ARGB8888, %lu shown, %lu busy, %lu refused\n",
			  osd.shown ? "shown" : osd.want >= 0 && bare.on ? "held back (ctl bare)" :
			  osd.want >= 0 ? "waiting for a picture" : "hidden",
			  osd.plane_id, d->width, d->height, osd.shows, osd.busy, osd.errors);
}

/* bare [SECONDS]: nothing of ours on the wall for that long, 0 ends it (struct bare); without a number: show it */
static void cmd_bare(struct reply *r, struct display *d, const char *arg)
{
	struct itimerspec its = { 0 };
	char *end = NULL;
	long s;

	if (!arg) {
		if (bare.on)
			reply_add(r, "ok bare on -- %ld s left, nothing of ours on the wall\n", bare_left());
		else
			reply_add(r, "ok bare off\n");
		return;
	}
	s = strtol(arg, &end, 10);
	if (end == arg || *end || s < 0 || s > BARE_MAX_S) {
		reply_fail(r, "bare takes SECONDS, 0..%d (0 ends it)", BARE_MAX_S);
		return;
	}
	if (!s) {
		bool was = bare.on;

		bare_end(d, "ended (ctl bare 0)");
		reply_add(r, "ok bare off%s\n", was ? " -- what h713-osd wants is back" : "");
		return;
	}
	if (bare.fd < 0)
		bare.fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	its.it_value.tv_sec = s;
	if (bare.fd < 0 || timerfd_settime(bare.fd, 0, &its, NULL)) {
		reply_fail(r, "no timer for its end (%s) -- bare not begun", strerror(errno));
		return;
	}
	if (!bare.on) {
		bare.on = true;
		bare_begin(d);
		info("bare            for %ld s: nothing of ours on the wall%s", s,
		     osd.want >= 0 ? " -- h713-osd's overlay waits" : "");
	}
	reply_add(r, "ok bare %ld -- nothing of ours on the wall until \"bare 0\" or %ld s\n", s, s);
}

/*
 * The vendor's picture presets for the HDMI inputs, pq_picturemode.ini
 * [HDMI1] (= HDMI2 = HDMI3), keyed by the firmware's mode number
 * (doku/nachtlog/S14 section 4). SetPictureMode alone changes none of these
 * nine values -- the stock UI sends them as the ordinary Set RPCs after the
 * mode, and so does this: mode first, then the nine controls. energy_saving
 * differs from standard only in the backlight and custom is a database row,
 * neither has a firmware mode of its own.
 *
 * Since 11.09.2026 this table is the *last* fallback, not the source: what is
 * normally applied is computed at start from the device's own extraction by
 * h713-pq (plan 113 A.2/A.3, see "The picture values" below). The table
 * stays because a device without the extraction has to show a picture too --
 * it is right for this panel, it is just not derived from this panel's data.
 */
struct preset {
	const char *name;
	int mode;
	int value[9];	/* brightness contrast saturation hue sharpness tnr snr dci black */
};

static const struct preset presets[] = {
	{ "standard", 1,  { 50, 50, 50, 50, 50, 2, 1, 2, 1 } },
	{ "cinema",   7,  { 50, 45, 45, 50, 40, 2, 1, 0, 0 } },
	{ "vivid",    0,  { 50, 55, 60, 50, 60, 2, 1, 3, 1 } },
	{ "game",     3,  { 50, 50, 50, 50, 50, 1, 0, 0, 0 } },
	{ "computer", 6,  { 50, 50, 50, 50,  0, 0, 0, 0, 0 } },
	{ "hdr",      12, { 50, 50, 50, 50, 50, 1, 1, 0, 0 } },
};

/* the nine, by the driver's control names ... */
static const char *const preset_ctrl[9] = {
	"brightness", "contrast", "saturation", "hue", "sharpness",
	"tnr", "snr", "dci", "black",
};

/*
 * ... and the same nine by the names h713-pq uses in its record, which are
 * the vendor's own column names from pq_picturemode.ini. Two lists and not
 * one, because neither side should have to rename anything: the driver calls
 * it "black_extension" (short: "black"), the vendor file "blackextenstion",
 * and h713-pq stays faithful to its data model.
 */
static const char *const preset_pq_key[9] = {
	"brightness", "contrast", "saturation", "hue", "sharpness",
	"tnr", "snr", "dci", "blackextension",
};

/* ------------------------------------------------------------------ *
 * The picture values: who computes them (plan 113 A.3, way (a))
 *
 * h713-pq reads the eight extracted vendor files in /etc/h713/tvconfig and
 * works out, for one input and one preset, the nine sliders, the firmware's
 * mode number and the gamma curve. That computation exists once, in Python,
 * and is not repeated here in C -- doing the same arithmetic twice is what
 * produced the saturation error of 07.09. (doku/nachtlog/G). So this program
 * asks and applies; it does not compute.
 *
 * How it asks:
 *
 *   h713-pq --data DIR show INPUT PRESET --json --lut /run/.../gamma.bin
 *
 * One child process, started as early as possible -- before the capture and
 * the DRM device are opened, which is where the start spends its time anyway
 * -- and collected just before the gamma curve is needed. So the roughly
 * 200 ms of a Python start run *alongside* work that has to happen anyway
 * instead of being added to it. Not a service, not a library, no second
 * process later: one call, one answer, done.
 *
 * What may go wrong, and what happens then (plan 113 A.5). Every one of these
 * ends in the compiled table above and a line in the journal, never in an
 * exit:
 *
 *   * the data directory is missing or incomplete   -> h713-pq exits 2
 *   * h713-pq is not installed or not executable   -> not even started
 *   * it crashes, or writes something unparseable   -> record rejected
 *   * it takes longer than PQ_DEADLINE_MS           -> killed, record dropped
 *   * "calculator = none" or "data = none" in tv.conf -> not started at all
 *
 * The record carries *all* presets the data has for this input, not only the
 * one asked for. That is why "ctl preset energy_saving" works on a device
 * with the extraction and says "unknown" on one without it, without ever
 * starting a second Python process while the picture is running.
 * ------------------------------------------------------------------ */

#define PQ_DEADLINE_MS	2000	/* plan 113 A.5: h713-pq must not hold the start */
#define PQ_RECORD_VERSION	1	/* what h713-pq calls "version" in its record */
#define PQ_RAW_MAX	16384	/* the record is ~3,5 kB for eight presets */
#define PQ_PRESETS_MAX	16
#define PQ_WAIT_MS	5	/* poll interval while reaping the child */

/* the presets that came from the device's own data; empty without them */
static struct preset pq_presets[PQ_PRESETS_MAX];
static char pq_names[PQ_PRESETS_MAX][32];
static double pq_gamma[PQ_PRESETS_MAX];
static int pq_ctemp[PQ_PRESETS_MAX];	/* the colour temperature of the preset: 0 normal, 1 cool, 2 warm, -1 not said */
static unsigned int pq_presets_n;

struct pq {
	pid_t pid;
	int fd;			/* read end of the pipe, -1: nothing running */
	struct timespec t0;
	bool ok;		/* a record was read and understood */
	unsigned int ms;	/* how long the call took */
	char why[224];		/* why not, in the words that go in the journal */
	/* out of the record */
	char data[160];
	char preset[32];
	char lut[184];
	long lut_bytes;
	double gamma;
	char raw[PQ_RAW_MAX];
	size_t len;
};

/*
 * -1 and not 0: without a run there must be no descriptor here that
 * pq_collect() would poll -- fd 0 is stdin.
 */
static struct pq pq = { .pid = -1, .fd = -1 };

/* ---- a very small JSON reader, for this one record and nothing else ---- *
 *
 * Not a general parser. It knows objects, arrays, strings and numbers just
 * far enough to find a key on *this* level of a region [b,e). Nested things
 * are skipped, not entered -- otherwise a lookup of "brightness" would find
 * the one belonging to some other preset. Anything it does not understand
 * makes the lookup fail, which is the same as "no record": the table above
 * takes over. It never allocates and never writes outside the caller's
 * buffer.
 */

/* the end of the string that starts at b (on its opening quote) */
static const char *js_string_end(const char *b, const char *e)
{
	for (b++; b < e; b++) {
		if (*b == '\\' && b + 1 < e)
			b++;
		else if (*b == '"')
			return b + 1;
	}

	return e;
}

/* the end of the value that starts at b: object, array, string or number */
static const char *js_value_end(const char *b, const char *e)
{
	int depth = 0;

	while (b < e) {
		char c = *b;

		if (c == '"') {
			b = js_string_end(b, e);
			if (!depth)
				return b;
			continue;
		}
		if (c == '{' || c == '[') {
			depth++;
		} else if (c == '}' || c == ']') {
			if (!depth)
				return b;	/* the parent's closing bracket */
			if (!--depth)
				return b + 1;
		} else if (!depth && c == ',') {
			return b;
		}
		b++;
	}

	return e;
}

static const char *js_space(const char *b, const char *e)
{
	while (b < e && (*b == ' ' || *b == '\t' || *b == '\n' || *b == '\r' ||
			 *b == ','))
		b++;

	return b;
}

/* [b,e) is the inside of an object; returns the start of key's value */
static const char *js_field(const char *b, const char *e, const char *key)
{
	size_t kl = strlen(key);

	while (b < e) {
		const char *ks, *ke;

		b = js_space(b, e);
		if (b >= e || *b != '"')
			return NULL;
		ks = b + 1;
		b = js_string_end(b, e);
		ke = b > ks ? b - 1 : ks;	/* the closing quote */
		while (b < e && (*b == ' ' || *b == '\t' || *b == '\n' || *b == '\r'))
			b++;
		if (b >= e || *b != ':')
			return NULL;
		for (b++; b < e && (*b == ' ' || *b == '\t' || *b == '\n' ||
				    *b == '\r'); b++)
			;
		if ((size_t)(ke - ks) == kl && !strncmp(ks, key, kl))
			return b;
		b = js_value_end(b, e);
	}

	return NULL;
}

static bool js_text(const char *b, const char *e, const char *key, char *out,
		    size_t n)
{
	const char *v = js_field(b, e, key), *end;
	size_t i = 0;

	if (!v || *v != '"')
		return false;
	end = js_string_end(v, e);
	if (end > v)
		end--;				/* the closing quote */
	for (v++; v < end && i + 1 < n; v++) {
		if (*v == '\\' && v + 1 < end)
			v++;			/* \" \\ \/ -- nothing else here */
		out[i++] = *v;
	}
	out[i] = '\0';

	return true;
}

/*
 * strtol/strtod on the raw buffer: it is NUL-terminated as a whole, and a
 * number in JSON always ends on one of , } ] or space, all of which stop the
 * conversion. So neither can run past its value.
 */
static bool js_number(const char *b, const char *e, const char *key, long *out)
{
	const char *v = js_field(b, e, key);
	char *end;
	long x;

	if (!v || (*v != '-' && !isdigit((unsigned char)*v)))
		return false;
	errno = 0;
	x = strtol(v, &end, 10);
	if (end == v || errno)
		return false;
	*out = x;

	return true;
}

static bool js_double(const char *b, const char *e, const char *key,
			  double *out)
{
	const char *v = js_field(b, e, key);
	char *end;
	double x;

	if (!v || (*v != '-' && !isdigit((unsigned char)*v)))
		return false;
	errno = 0;
	x = strtod(v, &end);
	if (end == v || errno)
		return false;
	*out = x;

	return true;
}

/* the inside of the object or array under key */
static bool js_inside(const char *b, const char *e, const char *key,
		       const char **ib, const char **ie)
{
	const char *v = js_field(b, e, key), *end;

	if (!v || (*v != '{' && *v != '['))
		return false;
	end = js_value_end(v, e);
	*ib = v + 1;
	*ie = end > v + 1 ? end - 1 : v + 1;

	return true;
}

/* the next {...} in [*b,e); hands out its inside and steps *b past it */
static bool js_element(const char **b, const char *e, const char **ib,
		       const char **ie)
{
	const char *p = *b, *end;

	while (p < e && *p != '{')
		p++;
	if (p >= e)
		return false;
	end = js_value_end(p, e);
	*ib = p + 1;
	*ie = end > p + 1 ? end - 1 : p + 1;
	*b = end;

	return true;
}

/* ---- running h713-pq ---- */

static int pq_time_left(const struct pq *p)
{
	struct timespec now;
	long used;

	clock_gettime(CLOCK_MONOTONIC, &now);
	used = (now.tv_sec - p->t0.tv_sec) * 1000 +
	       (now.tv_nsec - p->t0.tv_nsec) / 1000000;

	return used >= PQ_DEADLINE_MS ? 0 : (int)(PQ_DEADLINE_MS - used);
}

static unsigned int pq_time_used(const struct pq *p)
{
	struct timespec now;
	long used;

	clock_gettime(CLOCK_MONOTONIC, &now);
	used = (now.tv_sec - p->t0.tv_sec) * 1000 +
	       (now.tv_nsec - p->t0.tv_nsec) / 1000000;

	return used < 0 ? 0 : (unsigned int)used;
}

/*
 * Start the child. Everything that can be decided without forking is decided
 * here, so that a device without h713-pq costs exactly one access().
 */
static void pq_start(struct pq *p, const struct conf *c, const char *preset)
{
	int fds[2];

	memset(p, 0, sizeof(*p));
	p->pid = -1;
	p->fd = -1;

	if (!strcasecmp(c->calculator, "none")) {
		snprintf(p->why, sizeof(p->why), "calculator = none");
		return;
	}
	if (!strcasecmp(c->data, "none")) {
		snprintf(p->why, sizeof(p->why), "data = none");
		return;
	}
	if (access(c->calculator, X_OK)) {
		snprintf(p->why, sizeof(p->why), "%s: %s", c->calculator,
			 strerror(errno));
		return;
	}
	if (pipe2(fds, O_CLOEXEC)) {
		snprintf(p->why, sizeof(p->why), "pipe: %s", strerror(errno));
		return;
	}
	clock_gettime(CLOCK_MONOTONIC, &p->t0);
	p->pid = fork();
	if (p->pid < 0) {
		snprintf(p->why, sizeof(p->why), "fork: %s", strerror(errno));
		close(fds[0]);
		close(fds[1]);
		p->pid = -1;
		return;
	}
	if (!p->pid) {
		int null = open("/dev/null", O_RDONLY);

		/*
		 * The child is a plain program, not a copy of this one: it
		 * gets stdout on the pipe (dup2 clears the pipe's CLOEXEC),
		 * stderr as it is -- h713-pq's own messages belong in the
		 * journal -- and no inherited SIGPIPE handling.
		 */
		signal(SIGPIPE, SIG_DFL);
		if (null >= 0)
			dup2(null, STDIN_FILENO);
		if (dup2(fds[1], STDOUT_FILENO) < 0)
			_exit(127);
		execl(c->calculator, "h713-pq", "--data", c->data, "show",
		      c->input, preset, "--json", "--lut", c->lut,
		      (char *)NULL);
		_exit(127);
	}
	close(fds[1]);
	p->fd = fds[0];
	snprintf(p->lut, sizeof(p->lut), "%s", c->lut);
}

/* reap the child inside what is left of the budget; SIGKILL when it is up */
static bool pq_reap(struct pq *p, int *status)
{
	if (p->pid < 0)
		return false;
	for (;;) {
		pid_t r = waitpid(p->pid, status, WNOHANG);

		if (r == p->pid)
			break;
		if (r < 0 && errno != EINTR) {
			snprintf(p->why, sizeof(p->why), "waitpid: %s",
				 strerror(errno));
			p->pid = -1;
			return false;
		}
		if (pq_time_left(p) <= 0) {
			struct timespec ts = { 0, 200 * 1000 * 1000 };

			kill(p->pid, SIGKILL);
			/* after SIGKILL the wait is bounded by the kernel */
			while (waitpid(p->pid, status, WNOHANG) != p->pid &&
			       ts.tv_nsec > 0) {
				struct timespec nap = { 0, 1000 * 1000 };

				nanosleep(&nap, NULL);
				ts.tv_nsec -= 1000 * 1000;
			}
			snprintf(p->why, sizeof(p->why),
				 "longer than %d ms -- aborted", PQ_DEADLINE_MS);
			p->pid = -1;
			return false;
		}
		{
			struct timespec nap = { 0, PQ_WAIT_MS * 1000 * 1000 };

			nanosleep(&nap, NULL);
		}
	}
	p->pid = -1;

	return true;
}

/* the record -> pq_presets[]; false means "use the compiled table" */
static bool pq_parse(struct pq *p)
{
	const char *b = p->raw, *e = p->raw + p->len, *ab, *ae, *lb, *le;
	long v;

	while (b < e && *b != '{')
		b++;
	if (b >= e) {
		snprintf(p->why, sizeof(p->why), "no JSON output (%zu bytes)",
			 p->len);
		return false;
	}
	le = js_value_end(b, e);
	b++;
	e = le > b ? le - 1 : b;

	if (!js_number(b, e, "version", &v) || v != PQ_RECORD_VERSION) {
		snprintf(p->why, sizeof(p->why),
			 "record version %ld, this program knows %d", v,
			 PQ_RECORD_VERSION);
		return false;
	}
	js_text(b, e, "daten", p->data, sizeof(p->data));
	js_text(b, e, "preset", p->preset, sizeof(p->preset));
	if (js_number(b, e, "lut_bytes", &v))
		p->lut_bytes = v;
	js_double(b, e, "gamma_exponent", &p->gamma);

	if (!js_inside(b, e, "presets", &ab, &ae)) {
		snprintf(p->why, sizeof(p->why), "no field \"presets\" in the record");
		return false;
	}
	pq_presets_n = 0;
	while (pq_presets_n < PQ_PRESETS_MAX && js_element(&ab, ae, &lb, &le)) {
		struct preset *t = &pq_presets[pq_presets_n];
		const char *rb, *re;
		unsigned int i;
		long mode;

		if (!js_text(lb, le, "name", pq_names[pq_presets_n],
			     sizeof(pq_names[0])) ||
		    !js_number(lb, le, "modus", &mode) ||
		    !js_inside(lb, le, "regler", &rb, &re))
			continue;
		for (i = 0; i < 9; i++) {
			if (!js_number(rb, re, preset_pq_key[i], &v))
				break;
			t->value[i] = (int)v;
		}
		if (i < 9)
			continue;		/* incomplete -- not guessed */
		t->name = pq_names[pq_presets_n];
		t->mode = (int)mode;
		pq_gamma[pq_presets_n] = 0.0;
		js_double(lb, le, "gamma_exponent", &pq_gamma[pq_presets_n]);
		/* "weitere": the columns that have no control of their own; colortemperature 0 standard, 1 cool, 2 warm */
		pq_ctemp[pq_presets_n] = -1;
		if (js_inside(lb, le, "weitere", &rb, &re) && js_number(rb, re, "colortemperature", &v) && v >= 0 && v <= 2)
			pq_ctemp[pq_presets_n] = (int)v;
		pq_presets_n++;
	}
	if (!pq_presets_n) {
		snprintf(p->why, sizeof(p->why), "no usable preset in the record");
		return false;
	}

	return true;
}

/*
 * Collect what the child said. Called once, from the start, at the point
 * where the answer is first needed -- everything before this ran in
 * parallel with it.
 */
static void pq_collect(struct pq *p)
{
	struct pollfd pfd;
	int status = 0;

	if (p->fd < 0) {
		if (!p->why[0])
			snprintf(p->why, sizeof(p->why), "not started");
		return;
	}
	pfd.fd = p->fd;
	pfd.events = POLLIN;
	for (;;) {
		int rest = pq_time_left(p);
		ssize_t k;

		if (rest <= 0 || poll(&pfd, 1, rest) <= 0)
			break;
		k = read(p->fd, p->raw + p->len, sizeof(p->raw) - 1 - p->len);
		if (k <= 0)
			break;
		p->len += (size_t)k;
		if (p->len >= sizeof(p->raw) - 1)
			break;
	}
	p->raw[p->len] = '\0';
	close(p->fd);
	p->fd = -1;

	if (!pq_reap(p, &status)) {
		p->ms = pq_time_used(p);
		return;
	}
	p->ms = pq_time_used(p);
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		if (WIFSIGNALED(status))
			snprintf(p->why, sizeof(p->why), "ended by signal %d",
				 WTERMSIG(status));
		else
			snprintf(p->why, sizeof(p->why), "exit code %d "
				 "(data directory incomplete?)",
				 WEXITSTATUS(status));
		return;
	}
	p->ok = pq_parse(p);
}

/* which presets can be offered right now, for a message */
static void preset_names(char *buf, size_t n)
{
	unsigned int i;
	size_t l = 0;

	buf[0] = '\0';
	if (pq_presets_n) {
		for (i = 0; i < pq_presets_n && l + 1 < n; i++)
			l += (size_t)snprintf(buf + l, n - l, "%s%s", l ? " " : "",
					      pq_presets[i].name);
		return;
	}
	for (i = 0; i < sizeof(presets) / sizeof(presets[0]) && l + 1 < n; i++)
		l += (size_t)snprintf(buf + l, n - l, "%s%s", l ? " " : "",
				      presets[i].name);
}

/* ------------------------------------------------------------------ *
 * The gamma curve of this board
 *
 * The shipped curve is a synthetic 2.2 power law; the panel's real one is measured and sits in the board's own
 * ProjectID_0x00NN.TSE, one state per colour temperature (normal, cool, warm), three channels each. Measured over the
 * bridge 22.09.2026: the HY300 Pro's panel curve runs at about 48 % where the synthetic one is at 22 %, and his wall
 * said the same (doku/128); a board that bakes a different end point per channel into its curve (HY300 Pro:
 * 4087/3863/3459) keeps that white balance only with three banks.
 *
 * h713-pq reads the TSE once at the start and hands over the raw curves of all the states:
 *
 *   h713-pq --data DIR gamma --export-slots /run/.../gamma-slots.bin --project 0xNN --tse /boot/mips/ProjectID_0x00NN.TSE
 *
 * and gamma.c does the rest, as the display firmware's own library does (the gamma level, the colour temperature, the
 * twelve-knot form it is always in). --data is a GLOBAL option, before the subcommand; h713-pq wants a tvconfig
 * directory for `gamma` too ($H713_TVCONFIG does the same job). WHICH ProjectID this board carries is not readable
 * from /boot/mips, which holds all 13, so it is told: /etc/h713/board, written by the installer out of the board
 * profile, and where that is missing the device tree (kernel patches 0160/0161/0181). If none of it works the shipped
 * file applies exactly as before, with one journal line saying why, and the two controls say so when they are used.
 * ------------------------------------------------------------------ */

static const struct {
	const char *compatible;
	int project;
} board_of_dt[] = {
	{ "magcubic,hy310", 0x30 },		/* patch 0160 */
	{ "magcubic,hy300-pro", 0x34 },	/* patch 0161 */
	{ "magcubic,hy200-qz713df-a1", 0x34 },	/* patch 0181: HY300PRO-G-EU, HY300 Pro+ */
};

/* this board's ProjectID, or -1 with `why` saying what was missing */
static int board_project_id(char *why, size_t n)
{
	char line[256], buf[512], id[32], *end;
	size_t got, i, k;
	long v;
	FILE *f;

	/* /etc/h713/board is "key = value" like tv.conf; `board =` is for the
	 * reader, only project_id is a number this program acts on. */
	f = fopen(BOARD_FILE, "r");
	while (f && fgets(line, sizeof(line), f)) {
		if (sscanf(line, " project_id = %31s", id) != 1)
			continue;
		fclose(f);
		v = strtol(id, &end, 0);
		if (*end || v <= 0 || v > 0xffff) {
			snprintf(why, n, "%s: project_id = \"%s\" is no id",
				 BOARD_FILE, id);
			return -1;
		}
		return (int)v;
	}
	if (f)
		fclose(f);
	f = fopen(DT_COMPATIBLE, "rb");
	if (!f) {
		snprintf(why, n, "neither %s nor %s: %s", BOARD_FILE,
			 DT_COMPATIBLE, strerror(errno));
		return -1;
	}
	got = fread(buf, 1, sizeof(buf) - 1, f);
	fclose(f);
	buf[got] = '\0';
	/* the property is a list of strings, each one NUL terminated */
	for (i = 0; i < got; i += strlen(buf + i) + 1)
		for (k = 0; k < sizeof(board_of_dt) / sizeof(board_of_dt[0]); k++)
			if (!strcmp(buf + i, board_of_dt[k].compatible))
				return board_of_dt[k].project;
	snprintf(why, n, "%s carries no project_id and %s no board this program "
		 "knows", BOARD_FILE, DT_COMPATIBLE);
	return -1;
}

struct tse_gamma {
	pid_t pid;		/* -1: nothing running */
	int project;
	char why[240];		/* why the shipped curve applies instead */
	bool ok;		/* TSE_SLOTS holds this board's own curves */
};

static struct tse_gamma tsegamma = { .pid = -1 };

/* what display_gamma_load() was handed at start -- for `ctl status` */
static const char *gamma_loaded;

/*
 * Start the child. Next to pq_start() and for its reason: two Python starts
 * alongside the device opening cost what one of them costs.
 */
static void tse_gamma_start(struct tse_gamma *t, const struct conf *c)
{
	char tse[sizeof(TSE_DIR) + 32], project[16];

	t->pid = -1;
	t->ok = false;
	if (!strcasecmp(c->calculator, "none") || !strcasecmp(c->data, "none")) {
		snprintf(t->why, sizeof(t->why), "the computation is switched off");
		return;
	}
	t->project = board_project_id(t->why, sizeof(t->why));
	if (t->project < 0)
		return;
	snprintf(tse, sizeof(tse), "%s/ProjectID_0x%04x.TSE", TSE_DIR, t->project);
	snprintf(project, sizeof(project), "0x%02x", t->project);
	if (access(tse, R_OK)) {
		snprintf(t->why, sizeof(t->why), "%s: %s", tse, strerror(errno));
		return;
	}
	t->pid = fork();
	if (t->pid < 0) {
		snprintf(t->why, sizeof(t->why), "fork: %s", strerror(errno));
		t->pid = -1;
		return;
	}
	if (!t->pid) {
		int null = open("/dev/null", O_RDWR);	/* its table reads nobody */

		if (null >= 0) {
			dup2(null, STDIN_FILENO);
			dup2(null, STDOUT_FILENO);
		}
		execl(c->calculator, "h713-pq", "--data", c->data, "gamma",
		      "--export-slots", TSE_SLOTS, "--project", project,
		      "--tse", tse, (char *)NULL);
		_exit(127);
	}
}

/* Wait for it and look at what it wrote; false means "the shipped curve". gamma.c reads the file itself. */
static bool tse_gamma_collect(struct tse_gamma *t)
{
	struct stat st;
	int status = 0;

	if (t->pid < 0)
		return false;
	if (waitpid(t->pid, &status, 0) != t->pid)
		snprintf(t->why, sizeof(t->why), "waitpid: %s", strerror(errno));
	else if (!WIFEXITED(status) || WEXITSTATUS(status))
		snprintf(t->why, sizeof(t->why), "h713-pq gamma --export-slots: "
			 "exit code %d", WEXITSTATUS(status));
	else if (stat(TSE_SLOTS, &st) || st.st_size <= 0)
		snprintf(t->why, sizeof(t->why), "%s was not written", TSE_SLOTS);
	else
		t->ok = true;
	t->pid = -1;

	return t->ok;
}

/*
 * The device's own data first, the compiled table second. Both are searched,
 * not only the first: if the extraction is missing exactly one preset the
 * user asks for, the table can still answer -- and the answer says where it
 * came from, because preset_is_from_data() below is what the status line
 * reports.
 */
static const struct preset *preset_find(const char *name)
{
	unsigned int i;

	if (!name)
		return NULL;
	for (i = 0; i < pq_presets_n; i++)
		if (!strcasecmp(pq_presets[i].name, name))
			return &pq_presets[i];
	for (i = 0; i < sizeof(presets) / sizeof(presets[0]); i++)
		if (!strcasecmp(presets[i].name, name))
			return &presets[i];

	return NULL;
}

static bool preset_is_from_data(const struct preset *p)
{
	return p >= &pq_presets[0] && p < &pq_presets[PQ_PRESETS_MAX];
}

/* the gamma exponent that belongs to a preset, 0 when it is not known */
static double preset_gamma(const struct preset *p)
{
	if (!preset_is_from_data(p))
		return 0.0;

	return pq_gamma[p - &pq_presets[0]];
}

/*
 * The colour temperature a preset asks for, as the vendor's own table has it (pq_picturemode.ini, HDMI: cinema and hdr
 * warm, vivid cool, the rest standard). From the device's data when there is some; the compiled table has no such
 * column and says the same by name.
 */
static int preset_ctemp(const struct preset *p)
{
	if (!p)
		return 0;
	if (preset_is_from_data(p) && pq_ctemp[p - &pq_presets[0]] >= 0)
		return pq_ctemp[p - &pq_presets[0]];
	if (!strcasecmp(p->name, "cinema") || !strcasecmp(p->name, "hdr"))
		return 2;

	return !strcasecmp(p->name, "vivid") ? 1 : 0;
}

/* ... and by the firmware's picture mode number (ctl set mode N): the first preset with that number, 0 for a mode without one */
static int mode_ctemp(int mode)
{
	unsigned int i;

	for (i = 0; i < pq_presets_n; i++)
		if (pq_presets[i].mode == mode)
			return preset_ctemp(&pq_presets[i]);
	for (i = 0; i < sizeof(presets) / sizeof(presets[0]); i++)
		if (presets[i].mode == mode)
			return preset_ctemp(&presets[i]);

	return 0;
}

/*
 * Send one preset: the mode first, then the nine values. Writes what was
 * sent (or what failed) into msg, returns 0 when everything went, -1 when the
 * mode could not be set at all, otherwise the number of values that failed.
 *
 * Once is enough: the firmware keeps these across a source switch, a
 * resolution change and HDMI off/on (measured 08.09.2026: the PQ registers
 * held the cinema values through all three), so nothing here has to be
 * repeated when the plane is rebuilt.
 */
static int preset_apply(struct capture *cap, const struct preset *p, char *msg,
			size_t n)
{
	struct v4l2_query_ext_ctrl q;
	unsigned int i, failed = 0;
	size_t l = 0;
	int ret;

	if (!ctrl_find(cap->fd, "mode", &q)) {
		snprintf(msg, n, "no control picture_mode (kernel 0126)");
		return -1;
	}
	if (p->mode > q.maximum) {
		snprintf(msg, n, "%s needs picture mode %d, the kernel knows only 0..%lld (0132)",
			 p->name, p->mode, (long long)q.maximum);
		return -1;
	}
	fwc_mode_begin();
	ret = ctrl_set(cap->fd, &q, p->mode);
	if (ret) {
		snprintf(msg, n, "picture_mode = %d: %s", p->mode, strerror(-ret));
		fwc_mode_end("a preset");
		return -1;
	}
	l += (size_t)snprintf(msg + l, n - l, "%s: mode=%d", p->name, p->mode);
	for (i = 0; i < 9 && l + 1 < n; i++) {
		/*
		 * The firmware skips a Set whose value equals its own software
		 * state, and that state starts at 50 for the five sliders: a
		 * "50" sent after a cold start writes no register (measured
		 * 08.09.2026 -- contrast and sharpness stayed at their reset
		 * content until 49 had been sent first). A preset has to end in
		 * a known register state, so each slider is nudged by one step
		 * and then set; the two writes land before the first picture.
		 */
		if (i < 5 && ctrl_find(cap->fd, preset_ctrl[i], &q))
			ctrl_set(cap->fd, &q,
				 p->value[i] > 0 ? p->value[i] - 1 : 1);
		if (!ctrl_find(cap->fd, preset_ctrl[i], &q) ||
		    (ret = ctrl_set(cap->fd, &q, p->value[i]))) {
			l += (size_t)snprintf(msg + l, n - l, " %s=ERROR", preset_ctrl[i]);
			failed++;
			continue;
		}
		l += (size_t)snprintf(msg + l, n - l, " %s=%d", preset_ctrl[i],
				      p->value[i]);
	}
	fwc_mode_end("a preset");
	gamma_mode_temp(preset_ctemp(p), "a preset");

	return (int)failed;
}

/* ------------------------------------------------------------------ *
 * The third layer: what the user turned, kept on purpose
 *
 *   /var/lib/h713-tv/werte     "key = value", the same format as tv.conf,
 *       preset = vivid              which preset these values belong to
 *       brightness = 50             the nine, by their ctl names
 *       ...
 *       aspect = proportional       and how the source is fitted
 *       zoom = out 80               and the digital zoom: off, in F, out P
 *
 * Written by "h713-tv ctl save" and by nothing else -- **not** by every
 * "ctl set" (plan 113 A.4). Somebody looking for the right sharpness runs the
 * slider from end to end; writing every step would mean the device remembers
 * whichever value the power cut happened to catch, and it would write to the
 * eMMC dozens of times for one decision. The mode auto/off is the exception
 * that proves the rule and keeps writing itself immediately: it is a
 * decision, not a search.
 *
 * At start the file is laid *over* the preset, not instead of it: the preset
 * decides all nine, then the kept values overwrite what they name. A kept
 * value out of the driver's range is dropped by itself, with its line number
 * -- one bad line must not cost the other eight.
 *
 * The "preset =" line is what makes that honest. The kept values are
 * deviations *from a preset*; laying vivid's numbers over a start in cinema
 * would silently turn cinema into vivid. So they are applied when they belong
 * to the preset being started, and otherwise named in the journal and left
 * alone. With "preset = last" in tv.conf -- the setting this was built for
 * -- the two always agree.
 * ------------------------------------------------------------------ */

struct saved_values {
	const char *path;	/* NULL: nothing is kept */
	bool present;
	char preset[32];
	int value[9];
	bool have[9];
	unsigned int line[9];
	char aspect[24];
	unsigned int aspect_line;
	char zoom[24];
	unsigned int zoom_line;
	/* the firmware's white balance and colour management: the device's, not the preset's */
	int wb[FWC_WB_N];
	bool wb_have[FWC_WB_N];
	int cm[FWC_CM_N];
	bool cm_have[FWC_CM_N];
	/* the gamma level and the colour temperature (GAMMA_T_*): the device's as well */
	int gm[2];
	bool gm_have[2];
	bool complained;
};

static struct saved_values saved;

/* which preset is in force right now, and where it came from */
static char preset_current[32] = "";
static bool preset_current_from_data;

static void saved_read(struct saved_values *w)
{
	char line[256];
	unsigned int n = 0;
	FILE *f;

	w->present = false;
	w->preset[0] = '\0';
	w->aspect[0] = '\0';
	w->zoom[0] = '\0';
	memset(w->have, 0, sizeof(w->have));
	memset(w->wb_have, 0, sizeof(w->wb_have));
	memset(w->cm_have, 0, sizeof(w->cm_have));
	memset(w->gm_have, 0, sizeof(w->gm_have));
	if (!w->path)
		return;
	f = fopen(w->path, "r");
	if (!f) {
		if (errno != ENOENT)
			warn("%s: %s -- the preset alone applies", w->path,
			     strerror(errno));
		return;
	}
	w->present = true;
	while (fgets(line, sizeof(line), f)) {
		char *key, *val, *hash, *end;
		unsigned int i;
		long x;

		n++;
		hash = strchr(line, '#');
		if (hash)
			*hash = '\0';
		key = trim(line);
		if (!*key)
			continue;
		val = strpbrk(key, "= \t");
		if (!val) {
			warn("%s:%u: \"%s\" without a value -- ignored", w->path, n, key);
			continue;
		}
		*val++ = '\0';
		while (*val == ' ' || *val == '\t' || *val == '=')
			val++;
		val = trim(val);
		if (!strcasecmp(key, "preset")) {
			snprintf(w->preset, sizeof(w->preset), "%s", val);
			continue;
		}
		if (!strcasecmp(key, "aspect")) {
			snprintf(w->aspect, sizeof(w->aspect), "%s", val);
			w->aspect_line = n;
			continue;
		}
		if (!strcasecmp(key, "zoom")) {
			snprintf(w->zoom, sizeof(w->zoom), "%s", val);
			w->zoom_line = n;
			continue;
		}
		{
			int idx = 0, kept = 0;
			long y;
			int got = gamma_parse_kept(key, val, &idx, &kept);

			if (got < 0) {
				warn("%s:%u: %s = \"%s\" is not a value it knows -- dropped", w->path, n, key, val);
				continue;
			}
			if (got > 0) {
				w->gm[idx] = kept;
				w->gm_have[idx] = true;
				continue;
			}
			errno = 0;
			y = strtol(val, &end, 10);
			if (end == val || *end || errno) {
				got = fwc_key(key) >= 0 ? -1 : 0;
			} else {
				got = fwc_parse_kept(key, y, &idx, &kept);
			}
			if (got < 0) {
				warn("%s:%u: %s = \"%s\" is not a number in its range -- dropped", w->path, n, key, val);
				continue;
			}
			if (got > 0) {
				if (idx < FWC_WB_N) {
					w->wb[idx] = kept;
					w->wb_have[idx] = true;
				} else {
					w->cm[idx - FWC_WB_N] = kept;
					w->cm_have[idx - FWC_WB_N] = true;
				}
				continue;
			}
		}
		for (i = 0; i < 9; i++)
			if (!strcasecmp(key, preset_ctrl[i]))
				break;
		if (i == 9) {
			warn("%s:%u: unknown key \"%s\" -- ignored",
			     w->path, n, key);
			continue;
		}
		errno = 0;
		x = strtol(val, &end, 10);
		if (end == val || *end || errno || x < 0 || x > 10000) {
			warn("%s:%u: %s = \"%s\" is not a number -- dropped",
			     w->path, n, key, val);
			continue;
		}
		w->value[i] = (int)x;
		w->have[i] = true;
		w->line[i] = n;
	}
	fclose(f);
}

/*
 * Lay the kept values over the preset that has just been sent. The range is
 * the driver's own (VIDIOC_QUERY_EXT_CTRL), not a second table here -- so a
 * kernel that widens a control does not need a change in this file.
 */
static int saved_apply(struct capture *cap, const struct saved_values *w,
		       const char *preset_name, char *msg, size_t n)
{
	struct v4l2_query_ext_ctrl q;
	unsigned int i, applied = 0;
	size_t l = 0;

	msg[0] = '\0';
	if (!w->path || !w->present)
		return 0;
	if (w->preset[0] && strcasecmp(w->preset, preset_name)) {
		snprintf(msg, n, "saved for preset %s, starting with %s -- "
			 "not applied", w->preset, preset_name);
		return -1;
	}
	for (i = 0; i < 9; i++) {
		if (!w->have[i])
			continue;
		if (!ctrl_find(cap->fd, preset_ctrl[i], &q)) {
			warn("%s:%u: no control \"%s\" -- dropped", w->path,
			     w->line[i], preset_ctrl[i]);
			continue;
		}
		if (w->value[i] < q.minimum || w->value[i] > q.maximum) {
			warn("%s:%u: %s = %d is outside %lld..%lld -- dropped",
			     w->path, w->line[i], preset_ctrl[i], w->value[i],
			     (long long)q.minimum, (long long)q.maximum);
			continue;
		}
		if (ctrl_set(cap->fd, &q, w->value[i])) {
			warn("%s:%u: %s = %d could not be set", w->path,
			     w->line[i], preset_ctrl[i], w->value[i]);
			continue;
		}
		if (l + 1 < n)
			l += (size_t)snprintf(msg + l, n - l, "%s%s=%d", l ? " " : "",
					      preset_ctrl[i], w->value[i]);
		applied++;
	}

	return (int)applied;
}

/*
 * Write the current state. What is written is read back from the driver, not
 * remembered along the way: the driver is the one place that knows what the
 * nine controls really hold, and a bookkeeping copy could only ever be a
 * second version of the truth. That also settles the rule of plan 113 A.4
 * that "ctl preset" discards the kept deviations -- after a preset the
 * driver holds the preset's values, so that is what a later save writes.
 */
static bool saved_write(struct saved_values *w, struct capture *cap,
			const struct display *d, char *msg, size_t n)
{
	struct v4l2_query_ext_ctrl q;
	char tmp[240], dir[240], *slash;
	unsigned int i;
	size_t l = 0;
	int fd;
	FILE *f;

	if (!w->path) {
		snprintf(msg, n, "nothing is saved (state = none in tv.conf)");
		return false;
	}
	snprintf(tmp, sizeof(tmp), "%s.new", w->path);
	fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0 && errno == ENOENT) {
		/* started by hand, without the unit's StateDirectory */
		snprintf(dir, sizeof(dir), "%s", w->path);
		slash = strrchr(dir, '/');
		if (slash && slash != dir) {
			*slash = '\0';
			if (!mkdir(dir, 0755) || errno == EEXIST)
				fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC |
					  O_CLOEXEC, 0644);
		}
	}
	if (fd < 0) {
		snprintf(msg, n, "%s: %s", tmp, strerror(errno));
		return false;
	}
	f = fdopen(fd, "w");
	if (!f) {
		snprintf(msg, n, "%s: %s", tmp, strerror(errno));
		close(fd);
		unlink(tmp);
		return false;
	}
	fprintf(f, "# h713-tv: the picture values that \"h713-tv ctl save\" has\n"
		"# saved. At the start they are laid over the preset named in\n"
		"# the \"preset\" line. \"h713-tv ctl save off\" deletes the file\n"
		"# again. Editing it by hand is allowed: values outside a\n"
		"# control's range are dropped one by one and named in the\n"
		"# journal with their line number.\n");
	/*
	 * No preset line when none was sent (-p none): the values then belong
	 * to no preset and are applied whatever the next start comes up with.
	 */
	if (preset_current[0])
		fprintf(f, "preset      = %s\n", preset_current);
	for (i = 0; i < 9; i++) {
		int64_t v;

		if (!ctrl_find(cap->fd, preset_ctrl[i], &q) ||
		    ctrl_get(cap->fd, &q, &v))
			continue;
		fprintf(f, "%-11s = %lld\n", preset_ctrl[i], (long long)v);
		if (l + 1 < n)
			l += (size_t)snprintf(msg + l, n - l, "%s%s=%lld", l ? " " : "",
					      preset_ctrl[i], (long long)v);
	}
	if (d->has_aspect) {
		const char *a = prop_enum_name(&d->plane_props, "aspect", d->aspect);

		fprintf(f, "aspect      = %s\n", a);
		if (l + 1 < n)
			l += (size_t)snprintf(msg + l, n - l, " aspect=%s", a);
	}
	{
		char zbuf[32];

		zoom_text(d, zbuf, sizeof(zbuf));
		fprintf(f, "zoom        = %s\n", zbuf);
		if (l + 1 < n)
			l += (size_t)snprintf(msg + l, n - l, " zoom=%s", zbuf);
	}
	fprintf(f, "# the firmware's white balance (512 neutral) and colour management (a step, 0 neutral; only the changed)\n");
	l = fwc_kept_lines(f, msg, n, l);
	l = gamma_kept_lines(f, msg, n, l);
	if (fflush(f) || fsync(fileno(f)) || fclose(f)) {
		snprintf(msg, n, "%s: %s", tmp, strerror(errno));
		unlink(tmp);
		return false;
	}
	if (rename(tmp, w->path)) {
		snprintf(msg, n, "%s: %s", w->path, strerror(errno));
		unlink(tmp);
		return false;
	}
	saved_read(w);		/* what is on disk is now the truth again */

	return true;
}

static bool saved_delete(struct saved_values *w, char *msg, size_t n)
{
	if (!w->path) {
		snprintf(msg, n, "nothing is saved (state = none in tv.conf)");
		return false;
	}
	if (unlink(w->path) && errno != ENOENT) {
		snprintf(msg, n, "%s: %s", w->path, strerror(errno));
		return false;
	}
	w->present = false;
	memset(w->have, 0, sizeof(w->have));
	memset(w->wb_have, 0, sizeof(w->wb_have));
	memset(w->cm_have, 0, sizeof(w->cm_have));
	memset(w->gm_have, 0, sizeof(w->gm_have));
	w->zoom[0] = '\0';
	w->preset[0] = '\0';
	w->aspect[0] = '\0';

	return true;
}

static void cmd_preset(struct reply *r, struct capture *cap, const char *name)
{
	const struct preset *p = preset_find(name);
	char msg[256], names[192];
	double g;
	int ret;

	preset_names(names, sizeof(names));
	if (!p) {
		reply_fail(r, "preset needs a name: %s", names);
		return;
	}
	ret = preset_apply(cap, p, msg, sizeof(msg));
	if (ret < 0) {
		reply_fail(r, "%s", msg);
		return;
	}
	snprintf(preset_current, sizeof(preset_current), "%s", p->name);
	preset_current_from_data = preset_is_from_data(p);
	reply_add(r, "ok preset %s%s (%s)\n", msg,
		  ret ? " (not everything was set)" : "",
		  preset_current_from_data ? "from the device data"
					   : "the compiled-in table");
	/*
	 * The gamma curve is loaded once, at start, for the preset started
	 * with; changing it at run time would mean another h713-pq call and
	 * a CRTC commit in the middle of a picture. In this device's data all
	 * eight presets use gamma index 3 (2.2), so the case does not arise
	 * -- but silence would be the wrong answer if it ever did.
	 */
	g = preset_gamma(p);
	if (!gamma_active() && g > 0.0 && pq.gamma > 0.0 && g != pq.gamma)
		reply_add(r, "   note: %s wants gamma %.2f, loaded is %.2f -- "
			  "restart the service for that\n", p->name, g, pq.gamma);
	reply_add(r, "   the saved deviations are dropped; \"ctl save\" "
		  "writes this state down\n");
}

/*
 * save [--aus]: write the nine sliders, the preset they belong to and the
 * aspect, or throw the file away again. Deliberately explicit -- see the
 * comment above struct saved_values.
 */
static void cmd_save(struct reply *r, struct capture *cap,
		     const struct display *d, const char *arg)
{
	char msg[512];

	if (arg && (!strcmp(arg, "--aus") || !strcmp(arg, "aus") ||
		    !strcmp(arg, "off"))) {
		if (saved_delete(&saved, msg, sizeof(msg)))
			reply_add(r, "ok nothing saved any more -- at the next start "
				  "the preset alone applies\n");
		else
			reply_fail(r, "%s", msg);
		return;
	}
	if (arg) {
		reply_fail(r, "save knows only \"off\" (or \"--aus\") as its argument");
		return;
	}
	if (saved_write(&saved, cap, d, msg, sizeof(msg)))
		reply_add(r, "ok saved in %s: preset=%s %s\n", saved.path,
			  preset_current[0] ? preset_current : "-", msg);
	else
		reply_fail(r, "%s", msg);
}

/* the three layers, each with where it came from (declared above cmd_status) */
static void cmd_status_picture_values(struct reply *r)
{
	unsigned int i;

	if (pq.ok)
		reply_add(r, "picture values  %u presets from %s (h713-pq, %u ms), "
			  "gamma %.2f, LUT %ld bytes\n", pq_presets_n,
			  pq.data[0] ? pq.data : "the device data", pq.ms,
			  pq.gamma, pq.lut_bytes);
	else
		reply_add(r, "picture values  the compiled-in table -- %s\n",
			  pq.why[0] ? pq.why : "h713-pq was not asked");
	reply_add(r, "preset          %s (%s)\n",
		  preset_current[0] ? preset_current : "-",
		  preset_current_from_data ? "from the device data"
					   : "the compiled-in table");
	/* which curve is on the CRTC, and whose it is */
	if (gamma_active())
		reply_add(r, "gamma curve     computed here from this board's own curves (ProjectID 0x%02x)\n",
			  tsegamma.project);
	else
		reply_add(r, "gamma curve     %s (computed) -- %s\n",
			  gamma_loaded ? gamma_loaded : "-",
			  tsegamma.why[0] ? tsegamma.why : "no board TSE asked for");
	gamma_status(r);
	fwc_status(r);
	if (!saved.path)
		reply_add(r, "saved           nothing (state = none in tv.conf)\n");
	else if (!saved.present)
		reply_add(r, "saved           nothing in %s -- \"ctl save\" writes it\n",
			  saved.path);
	else {
		char list[256];
		size_t l = 0;

		list[0] = '\0';
		for (i = 0; i < 9; i++)
			if (saved.have[i] && l + 1 < sizeof(list))
				l += (size_t)snprintf(list + l, sizeof(list) - l,
						      "%s%s=%d", l ? " " : "",
						      preset_ctrl[i], saved.value[i]);
		reply_add(r, "saved           %s: preset=%s %s%s%s%s%s\n", saved.path,
			  saved.preset[0] ? saved.preset : "-", list,
			  saved.aspect[0] ? " aspect=" : "",
			  saved.aspect[0] ? saved.aspect : "",
			  saved.zoom[0] ? " zoom=" : "",
			  saved.zoom[0] ? saved.zoom : "");
	}
}

/*
 * audio [on|off|auto]: "on" and "off" force the path, "auto" lets it follow
 * the picture (doku/101 section 1 E). "none" is not a run-time state -- with
 * -a none nothing was opened and there is nothing to switch. Returns true
 * when the automaton has to run.
 */
static bool cmd_audio(struct reply *r, struct audio *a, const char *text)
{
	enum audio_policy p;

	if (!text) {
		reply_add(r, "ok audio %s -- %s\n", audio_policy_text(a),
			  a->enabled ? audio_state_text(a) : a->why);
		return false;
	}
	if (a->policy == AUDIO_NONE) {
		reply_fail(r, "the audio is switched off with \"-a none\" -- start the service without that option for this");
		return false;
	}
	if (!audio_policy_parse(text, &p) || p == AUDIO_NONE) {
		reply_fail(r, "audio does not know \"%s\" -- possible: on off auto", text);
		return false;
	}
	a->policy = p;
	if (a->enabled)
		reply_add(r, "ok audio %s\n", audio_policy_text(a));
	else
		reply_add(r, "ok audio %s -- saved, but %s\n",
			  audio_policy_text(a), a->why);

	return true;
}

/*
 * volume [0..100]: the slider on the stock curve (audio_curve_q()), on the
 * DSP or on the codec (audio_volume_apply()). The answer is read back from
 * the card, not echoed. Without an argument: show.
 */
static void cmd_volume(struct reply *r, struct audio *a, const char *text)
{
	char vol[64], *end;
	long n;

	if (a->policy == AUDIO_NONE) {
		reply_fail(r, "the audio is switched off with \"-a none\" -- start the service without that option for this");
		return;
	}
	if (text) {
		n = strtol(text, &end, 0);
		if (*end || n < 0 || n > 100) {
			char curve[96];

			reply_fail(r, "volume needs 0..100 (%s), not \"%s\"", audio_curve_text(curve, sizeof(curve)), text);
			return;
		}
		a->volume = (int)n;
		a->volume_set = true;
		if (!a->enabled) {
			reply_add(r, "ok volume %d -- saved, %s\n", a->volume,
				  a->why);
			return;
		}
		if (!a->dsp_stage && !a->have_dacvol) {
			reply_fail(r, "the card \"%s\" has no control \"%s\" -- the volume stays where it is",
				   a->codec.name, AUDIO_C_DACVOL);
			return;
		}
		audio_volume_apply(a);
		if (a->write_failed) {
			reply_fail(r, "\"%s\" could not be written (see the journal)",
				   audio_stage_name(a));
			return;
		}
	} else if (!a->enabled) {
		reply_add(r, "ok volume %s -- %s\n",
			  a->volume_set ? "saved" : "unknown", a->why);
		return;
	}
	reply_add(r, "ok %s\n", audio_volume_text(a, vol, sizeof(vol)));
}

/*
 * mute [on|off]: the listener's mute, on top of the automaton's -- the DSP
 * mute while HDMI plays, and the codec's switch (if it has one) for
 * everything the box plays. Without an argument: show.
 */
static void cmd_mute(struct reply *r, struct audio *a, const char *text)
{
	if (a->policy == AUDIO_NONE) {
		reply_fail(r, "the audio is switched off with \"-a none\" -- start the service without that option for this");
		return;
	}
	if (text) {
		if (!strcasecmp(text, "on") || !strcasecmp(text, "an") ||
		    !strcmp(text, "1"))
			a->mute = true;
		else if (!strcasecmp(text, "off") || !strcasecmp(text, "aus") ||
			 !strcmp(text, "0"))
			a->mute = false;
		else {
			reply_fail(r, "mute does not know \"%s\" -- possible: on off",
				   text);
			return;
		}
		if (a->enabled)
			audio_level(a);
		mute_keep(a->mute);
	}
	if (!a->enabled)
		reply_add(r, "ok mute %s -- saved, %s\n", a->mute ? "on" : "off",
			  a->why);
	else
		reply_add(r, "ok mute %s (DSP%s%s)\n", a->mute ? "on" : "off",
			  a->codec_mute ? " and codec " : ", the codec has no switch",
			  a->codec_mute ? a->codec_mute : "");
}

static void cmd_help(struct reply *r, const struct control *c)
{
	char names[192];

	preset_names(names, sizeof(names));
	reply_add(r, "ok commands\n"
		  "  status (st) [brief]   state of the program, the kernel and cpu_comm; brief\n"
		  "                        reads nothing back from the cards or the kernel\n"
		  "  auto (on)             the picture follows the signal (the default without tv.conf)\n"
		  "  off                   force the console, until auto\n"
		  "                        auto/off are saved (state in /etc/h713/tv.conf);\n"
		  "                        what applies at the start is start = auto|manual|last there\n"
		  "  console               unblank the console, show the cursor\n"
		  "  list                  all picture controls with value and range\n"
		  "  get CONTROL           read one control\n"
		  "  set CONTROL VALUE     set one control (a number or the menu text)\n"
		  "                        controls: brightness contrast saturation hue sharpness\n"
		  "                        tnr snr dci black range(auto|limited|full)\n"
		  "                        mode(0..13 or a name: standard cinema vivid game computer hdr ...)\n"
		  "  set wb_r_gain|wb_g_gain|wb_b_gain|wb_r_offset|wb_g_offset|wb_b_offset N\n"
		  "                        the firmware's white balance, 0..1023, 512 neutral (all six are always sent)\n"
		  "  set cm_AXIS_hue|sat|value N   colour management, -255..255 on the picture mode's own value, 0 neutral;\n"
		  "                        AXIS: red lips skintone yellow yellow_green green cyan blue blue_purple purple\n"
		  "  set gamma 0..4        the panel's gamma level: 0..4 or 1.8 2.0 2.1 2.2 2.4 (default 3 = 2.2); the display\n"
		  "                        firmware's own computation on this board's measured curves\n"
		  "  set colour_temperature auto|normal|cool|warm   which of the board's curves; auto takes the picture mode's\n"
		  "                        (cinema and hdr warm, vivid cool, the others normal); both are kept by \"save\"\n"
		  "  wb [R G B RO GO BO|reset]   show / set all six white balance values in one call\n"
		  "  cm [AXIS [H S V]|reset]     show the changed entries / one axis / set the three of an axis / all neutral\n"
		  "  preset NAME           vendor preset: picture mode + nine controls.\n"
		  "                        Possible: %s\n"
		  "                        (from /etc/h713/tvconfig, else compiled in);\n"
		  "                        drops the saved deviations in memory\n"
		  "  save [off]            save the current state of the nine controls, the preset,\n"
		  "                        aspect and zoom (%s); \"off\" deletes the file again.\n"
		  "                        Only here is anything written, not on every \"set\"\n"
		  "  aspect [NAME]         how the source is fitted (auto proportional full 16:9 4:3);\n"
		  "                        without NAME: show it. A change rebuilds the picture (~0.5 s)\n"
		  "  zoom [off|in F]       the digital zoom: \"in\" enlarges the centre of the picture by\n"
		  "                        a factor 1.0..4.0 (default 2), \"off\" is the baseline; without\n"
		  "                        an argument: show it. Rebuilds as aspect does. The firmware\n"
		  "                        scales, the placement is ours. \"out\" is gone (23.09.): the\n"
		  "                        projection area is \"h713-warp ctl zoom PERCENT\"\n"
		  "  audio [on|off|auto]   audio: forced on, forced silent, or following the picture\n"
		  "                        (default auto); without an argument: show it\n"
		  "  volume [0..100]       volume on the stock curve (0 = the floor, 1 = -41 dB, 50 = -22 dB,\n"
		  "                        100 = -9.5 dB; tv.conf volume_curve = vendor: the device's own,\n"
		  "                        which status names): in the DSP where it mixes the device's own tones\n"
		  "                        (kernel 0176), else in the codec's DAC; without a number: show it\n"
		  "  mute [on|off]         mute: the DSP master mute (HDMI and device sounds) and the codec's switch\n"
		  "  resync                select the source again (S_INPUT 0 = SetSource HDMI-1)\n"
		  "  replug                play an unplug and a replug to the source: HPD 300 ms low\n"
		  "                        (S_EDID blocks=0), load the EDID again, HPD high (~1 s, blocks)\n"
		  "  edid block0|block1    publish that half of " EDID_FILE " to the source (a replug\n"
		  "                        with it); tv.conf \"edid =\" makes it the standing setting\n"
		  "  source [hdmi|client|auto]  what the panel shows - the mode: the HDMI input; a program\n"
		  "                        (a Wayland client through h713-warp, never the ring: between two\n"
		  "                        programs the last picture stays; \"client\" again = a program starts);\n"
		  "                        or the client while there is one and the ring otherwise; not\n"
		  "                        saved (tv.conf \"source =\" is the start value)\n"
		  "  warp [status]         has h713-warp the video plane? plus its counters\n"
		  "  osd [status]          has h713-osd an overlay over the picture? plus its counters\n"
		  "  bare [SECONDS]        nothing of ours on the wall for SECONDS (1..600): no overlay, no opaque\n"
		  "                        page - without a picture the console has the panel (the autofocus's\n"
		  "                        chessboard); h713-osd's page waits and comes back with \"bare 0\" or\n"
		  "                        at the end; without a number: show it\n"
		  "  hdcp                  HDCP: version negotiated, authenticated, the 1.4 and 2.2 keys and the\n"
		  "                        firmware's last HDCP line (sysfs, kernel 0174; status shows the same)\n"
	  "  rpc NAME [ARG...]     an RPC to the firmware, e.g. rpc THal_Vp_DisableBlackScreen\n"
		  "                        (raw; blocks the program for the duration of the call)\n"
		  "  help                  this list\n"
		  "The answer starts with ok or error; socket %s (root, 0660)\n",
		  names, saved.path ? saved.path : "switched off", c->path);
}

/* true if the caller has to run evaluate() afterwards */
static bool control_dispatch(struct control *c, struct capture *cap,
			     struct display *d, struct retry *rt,
			     struct audio *a, char *line, struct reply *r,
			     int conn)
{
	char *save = NULL, *cmd, *a1, *a2;

	cmd = strtok_r(line, " \t", &save);
	a1 = strtok_r(NULL, " \t", &save);
	a2 = strtok_r(NULL, " \t", &save);
	if (!cmd) {
		reply_fail(r, "empty (h713-tv ctl help)");
		return false;
	}
	if (!strcmp(cmd, "status") || !strcmp(cmd, "st")) {
		/* "status brief": nothing read back from the cards or the kernel */
		cmd_status(r, c, cap, d, a, !(a1 && !strcmp(a1, "brief")));
	} else if (!strcmp(cmd, "hdcp")) {
		cmd_hdcp(r, cap);
	} else if (!strcmp(cmd, "auto") || !strcmp(cmd, "on")) {
		c->policy = POLICY_AUTO;
		state_write(c, c->policy);
		reply_add(r, "ok automatic -- the picture follows the signal\n");
		return true;
	} else if (!strcmp(cmd, "off")) {
		c->policy = POLICY_OFF;
		state_write(c, c->policy);
		retry_stop(rt);
		warp_release(d);	/* the console was asked for, not a warp */
		if (display_hide(d))
			reply_add(r, "ok console -- until \"auto\"\n");
		else
			reply_fail(r, "the plane cannot be switched off");
	} else if (!strcmp(cmd, "console")) {
		console_restore();
		if (d->on || d->warped || osd_on_panel())
			console_keys(false);	/* the console is not on the panel: its keyboard stays off */
		reply_add(r, "ok console unblanked, cursor on\n");
	} else if (!strcmp(cmd, "list")) {
		cmd_list(r, cap);
	} else if (!strcmp(cmd, "get") && a1) {
		cmd_get(r, cap, a1);
	} else if (!strcmp(cmd, "set") && a1 && a2) {
		cmd_set(r, cap, a1, a2);
	} else if (!strcmp(cmd, "wb") || !strcmp(cmd, "cm")) {
		char *arg[FWC_WB_N];
		unsigned int n = 0;

		/* up to six words after the command: wb R G B RO GO BO, cm AXIS H S V */
		if (a1)
			arg[n++] = a1;
		if (a2)
			arg[n++] = a2;
		while (n < FWC_WB_N && (arg[n] = strtok_r(NULL, " \t", &save)))
			n++;
		if (!strcmp(cmd, "wb"))
			cmd_wb(r, arg, n);
		else
			cmd_cm(r, arg, n);
	} else if (!strcmp(cmd, "preset")) {
		cmd_preset(r, cap, a1);
	} else if (!strcmp(cmd, "save")) {
		cmd_save(r, cap, d, a1);
	} else if (!strcmp(cmd, "aspect")) {
		return cmd_aspect(r, d, a1);
	} else if (!strcmp(cmd, "zoom")) {
		return cmd_zoom(r, d, a1, a2);
	} else if (!strcmp(cmd, "warp")) {
		bool again = cmd_warp(r, cap, d, a1, a2, conn);

		/* a ring claim on a plane that was off (the straight ring waited for it): the sound follows the picture the warp
		 * is about to draw - nothing else re-evaluates it, and evaluate() would ask the capture for its timings while the
		 * warp waits for the answer to its first frame */
		if (a1 && !strcmp(a1, "claim") && warp.claimed && !warp.client)
			audio_evaluate(a, cap, true);
		return again;
	} else if (!strcmp(cmd, "source")) {
		return cmd_source(r, d, a1);
	} else if (!strcmp(cmd, "osd")) {
		cmd_osd(r, d, a1, conn);
	} else if (!strcmp(cmd, "bare")) {
		cmd_bare(r, d, a1);
	} else if (!strcmp(cmd, "audio")) {
		/*
		 * The sound is decided here and not by the caller's
		 * evaluate(): a policy change is no reason to ask the capture
		 * device for its timings again (20 ms, S12 R7).
		 */
		if (cmd_audio(r, a, a1))
			audio_evaluate(a, cap, d->on || d->warped);
	} else if (!strcmp(cmd, "volume") || !strcmp(cmd, "vol")) {
		cmd_volume(r, a, a1);
	} else if (!strcmp(cmd, "mute")) {
		cmd_mute(r, a, a1);
	} else if (!strcmp(cmd, "resync")) {
		capture_select_input(cap);
		fwc_sync("a resync");
		reply_add(r, "ok source selected again\n");
		return true;
	} else if (!strcmp(cmd, "replug")) {
		return cmd_replug(r, cap, d, rt, -1);
	} else if (!strcmp(cmd, "edid") && a1 && (!strcmp(a1, "block0") || !strcmp(a1, "block1"))) {
		return cmd_replug(r, cap, d, rt, a1[5] - '0');
	} else if (!strcmp(cmd, "edid")) {
		reply_fail(r, "edid needs block0 or block1 (h713-tv ctl help)");
	} else if (!strcmp(cmd, "rpc") && a1) {
		char call[CTL_MAXLINE];

		snprintf(call, sizeof(call), "%s%s%s", a1, a2 ? " " : "", a2 ? a2 : "");
		while ((a2 = strtok_r(NULL, " \t", &save))) {
			size_t l = strlen(call);

			snprintf(call + l, sizeof(call) - l, " %s", a2);
		}
		cmd_rpc(r, call);
	} else if (!strcmp(cmd, "help")) {
		cmd_help(r, c);
	} else if (!strcmp(cmd, "get") || !strcmp(cmd, "set") || !strcmp(cmd, "rpc")) {
		reply_fail(r, "%s needs arguments (h713-tv ctl help)", cmd);
	} else {
		reply_fail(r, "unknown: %s (h713-tv ctl help)", cmd);
	}

	return false;
}

/* one client: read a line, answer, hang up. Never blocks the main loop for long. */
#define CTL_DEADLINE_MS	500

/* milliseconds left of the exchange's budget, 0 when it is used up */
static int ctl_time_left(const struct timespec *t0)
{
	struct timespec now;
	long used;

	clock_gettime(CLOCK_MONOTONIC, &now);
	used = (now.tv_sec - t0->tv_sec) * 1000 + (now.tv_nsec - t0->tv_nsec) / 1000000;

	return used >= CTL_DEADLINE_MS ? 0 : (int)(CTL_DEADLINE_MS - used);
}

static bool control_serve(struct control *c, struct capture *cap,
			  struct display *d, struct retry *rt, struct audio *a)
{
	char line[CTL_MAXLINE];
	struct reply r = { .len = 0, .failed = false };
	struct timespec t0;
	struct pollfd pfd;
	ssize_t n = 0, off = 0;
	bool reevaluate = false;
	int fd, left;

	fd = accept4(c->lfd, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
	if (fd < 0)
		return false;

	/*
	 * One deadline for the whole exchange, not per read: a client that
	 * trickles bytes must not hold the main loop, the picture is more
	 * important than its status line (S12 R2).
	 */
	clock_gettime(CLOCK_MONOTONIC, &t0);
	pfd.fd = fd;
	pfd.events = POLLIN;
	while (off < (ssize_t)sizeof(line) - 1) {
		if ((left = ctl_time_left(&t0)) <= 0 || poll(&pfd, 1, left) <= 0)
			break;
		n = read(fd, line + off, sizeof(line) - 1 - (size_t)off);
		if (n <= 0)
			break;
		off += n;
		if (memchr(line, '\n', (size_t)off))
			break;
	}
	line[off] = '\0';
	line[strcspn(line, "\r\n")] = '\0';

	if (off <= 0)
		reply_fail(&r, "nothing received");
	else
		reevaluate = control_dispatch(c, cap, d, rt, a, line, &r, fd);

	off = 0;
	pfd.events = POLLOUT;
	while ((size_t)off < r.len) {
		/* MSG_NOSIGNAL: a client that hung up must not kill the daemon (S12 F1) */
		n = send(fd, r.buf + off, r.len - (size_t)off, MSG_NOSIGNAL);
		if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
			if ((left = ctl_time_left(&t0)) <= 0 || poll(&pfd, 1, left) <= 0)
				break;
			continue;
		}
		if (n <= 0)
			break;
		off += n;
	}
	if (fd != warp.peer && fd != osd.peer && fd != wish.peer)	/* the warp's, the overlay's and the want connections live on (A2) */
		close(fd);

	return reevaluate;
}

/* ------------------------------------------------------------------ *
 * Client mode: h713-tv ctl COMMAND [ARG...]
 * ------------------------------------------------------------------ */

static int client(int argc, char **argv, const char *path)
{
	struct sockaddr_un addr;
	char line[CTL_MAXLINE], buf[4096];
	size_t len = 0;
	ssize_t n;
	int fd, i, rc;

	line[0] = '\0';
	for (i = 0; i < argc; i++) {
		int k = snprintf(line + len, sizeof(line) - len, "%s%s", len ? " " : "",
				 argv[i]);

		if (k < 0 || (size_t)k >= sizeof(line) - len - 1)
			fail("command too long (at most %zu characters)", sizeof(line) - 2);
		len += (size_t)k;
	}
	if (!len)
		len = (size_t)snprintf(line, sizeof(line), "help");
	line[len++] = '\n';
	line[len] = '\0';

	fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (fd < 0)
		fail("socket: %s", strerror(errno));
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
	if (strlen(path) >= sizeof(addr.sun_path))
		fail("%s: socket path longer than %zu characters", path, sizeof(addr.sun_path) - 1);
	if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)))
		fail("%s: %s -- is h713-tv running? (systemctl status 'h713-tv@*')", path,
		     strerror(errno));
	if (send(fd, line, strlen(line), MSG_NOSIGNAL) < 0)
		fail("sending: %s", strerror(errno));

	rc = 1;
	len = 0;
	while ((n = read(fd, buf, sizeof(buf) - 1)) > 0) {
		buf[n] = '\0';
		if (!len)
			rc = strncmp(buf, "ok", 2) ? 1 : 0;
		fputs(buf, stdout);
		len += (size_t)n;
	}
	close(fd);
	if (!len)
		fail("no answer");

	return rc;
}

static struct control ctl = { .lfd = -1, .lock_fd = -1 };

static void evaluate(struct capture *cap, struct display *d,
		     struct retry *rt)
{
	struct v4l2_dv_timings t;
	unsigned int ring_w, ring_h, ring_pitch;
	char sigbuf[64];
	int sig, was;

	/* while the warp is on the panel is h713-warp's: measure, report, and
	 * touch nothing (A3) - as long as there is a signal. Without one the
	 * ring goes on handing out its last frame and the warp would go on
	 * drawing it (the wall froze on the first unplug, 23.09.2026), so the
	 * warp is released here: its peer connection closes, it falls back to
	 * bypass and asks again once a second; "warp claim" is refused until a
	 * signal is back, and the state below shows the console meanwhile.
	 */
	/* a Wayland client needs no signal: signal events leave its claim alone */
	if (warp.claimed && warp.client) {
		retry_stop(rt);
		return;
	}
	if (warp.claimed) {
		retry_stop(rt);
		sig = capture_signal(cap, &t);
		cap->last_sig = sig;
		if (sig != 2)
			cap->last_t = t;
		/* a claim whose daemon let go (nosig_linger()) is nobody's to draw into: it is released whatever the signal does */
		if (sig == 1 && warp.peer >= 0) {
			nosig_back(rt, &t);	/* a signal back under the claim that never let go: the page, if it came, goes now */
			return;
		}
		/* gone, or one the display cannot take: h713-osd's page "No signal on HDMI" instead of the console - the last picture
		 * stands until the page is on the wall, the claim goes under it (nosig_follow()) */
		if (sig != 1 && nosig_defer(d, rt, sig == 0 || sig == 3))
			return;
		info("signal          %s while the warp is on -- the warp is released, %s until a signal is back",
		     sig == 0 ? "gone" : sig == 1 ? "back, but the warp's daemon had let go" : sig == 2 ? "changing" :
		     sig == 3 ? "not in the firmware's table" : "not readable",
		     nosig.lost && nosig_page_ok() && osd_covering() ? "the page" : "the console");
		warp_release(d);
	}
	/* "off" over the control socket: the console stays, whatever the signal does */
	if (ctl.policy == POLICY_OFF) {
		retry_stop(rt);
		want_hold_end();
		display_hide(d);
		return;
	}
	/* "source client" and no client claimed yet: the console, until h713-warp has one to show */
	if (ctl.source == SOURCE_CLIENT) {
		retry_stop(rt);
		display_hide(d);
		return;
	}

	sig = capture_signal(cap, &t);
	was = cap->last_sig;
	cap->last_sig = sig;
	/*
	 * The last measurement, not the last attempt: a change in flight has
	 * no timing, and ctl status is more useful naming what was measured
	 * before it than naming nothing.
	 */
	if (sig != 2)
		cap->last_t = t;
	if (sig == 2) {
		if (rt->n < RETRY_MAX) {
			if (!rt->n)
				info("signal          change in flight -- the geometry is not settled yet, waiting");
			rt->n++;
			retry_arm(rt, RETRY_MS);
			return;
		}
		/*
		 * Still undecided after the budget. Keep what is on the wall: a
		 * standing picture is real HDMI content, and the driver has not
		 * said the signal is gone (that would be ENOLINK, not ENOLCK).
		 * Measured 08.09.2026: treating this as "no signal" sent a correct
		 * 1080p picture to the console for ten seconds (S12 Umsetzung).
		 * And keep asking, slowly, until the driver decides -- with the
		 * plane on as well. The wall does not need the answer, the
		 * status does: measured 20.09.2026 (dev17), a release that ran
		 * longer than this budget left "change in flight" standing over
		 * a correct 720p picture for as long as no event came, because
		 * a direct release ends without one. The driver now sends one
		 * (0136f); this is the second line of defence, at a cost of one
		 * QUERY_DV_TIMINGS every 500 ms for as long as the state lasts.
		 */
		if (rt->n == RETRY_MAX) {
			warn("the geometry has not locked after %u retries -- %s stays, asking again every %u ms",
			     RETRY_MAX, d->on ? "the picture" : "the console",
			     RETRY_SLOW_MS);
			rt->n++;
			if (wall_black.fb_id && !d->on && !d->warped)
				display_hide(d);	/* the black wall waited for the ring: the console, as without it */
		}
		retry_arm(rt, RETRY_SLOW_MS);
		return;
	}
	/* decided: whatever is still scheduled would only measure again (S12 R4) */
	retry_stop(rt);

	/*
	 * The driver measured the source and the display firmware's own mode
	 * table has no record for it (kernel 0136m, -ERANGE). That is not a
	 * change in flight: it will not lock, now or later, so nothing is
	 * retried and the console stays. One line per state change -- the
	 * driver ratelimits its own line the same way.
	 */
	if (sig == 3) {
		if (was != 3 && t.bt.width)
			info("signal          %s not in the firmware's table -- console",
			     signal_text(&t, sigbuf, sizeof(sigbuf)));
		else if (was != 3)
			info("signal          a source the firmware's table does not carry -- console");
		want_hold_end();
		wish.noted = false;
		if (nosig_defer(d, rt, true))
			return;
		display_hide(d);
		return;
	}

	if (sig <= 0) {
		if (sig == 0)
			info("signal          no signal (the flip pointers stand still)");
		want_hold_end();
		wish.noted = false;
		if (nosig_defer(d, rt, sig == 0))
			return;
		display_hide(d);
		return;
	}

	info("signal          %s", signal_text(&t, sigbuf, sizeof(sigbuf)));

	/*
	 * What goes on the plane is the capture RING, not the source signal.
	 * Where the firmware scales in its capture path the ring is smaller
	 * than the source -- a 1920x1080 source on a 1280x720 panel lands in
	 * the ring 864 bytes wide (kernel 0136f) -- so the plane takes the ring
	 * and the AFBD scales it up to the panel. The refusal therefore
	 * compares the ring with the panel: a ring the firmware left larger
	 * than the panel cannot be scaled down and is refused, whatever the
	 * source is; a source larger than the panel whose ring fits is shown.
	 * Until 0136f this compared the source, and a 1920x1080 source kept a
	 * 1280x720 panel on the console although its ring fitted (issue #1).
	 */
	capture_format(cap, &t, &ring_w, &ring_h, &ring_pitch);
	if (ring_w != t.bt.width || ring_h != t.bt.height)
		info("ring            %ux%u, line pitch %u -- smaller than the source, the firmware scales",
		     ring_w, ring_h, ring_pitch);

	if (ring_w > d->width || ring_h > d->height || (ring_h & 1)) {
		warn("the plane does not take the ring geometry %ux%u (larger than the panel %ux%u, or an odd height); source %ux%u -- the console stays",
		     ring_w, ring_h, d->width, d->height, t.bt.width, t.bt.height);
		if (nosig_defer(d, rt, true))
			return;
		display_hide(d);
		return;
	}
	/*
	 * Sub-panel rings are scaled to the panel by the firmware itself: the
	 * rebuilt framebuffer below republishes the VidDec record with the new
	 * geometry (kernel 0117/0120), the firmware recomputes its window chain
	 * and programs the scaler (doku/96 sections 3-6), and the capture
	 * driver puts the input colour converter back and re-enables the
	 * capture (0121-0123). Until 08.09.2026 a lock here sent every
	 * non-panel geometry to the console, with H713_TV_SKALIERTEST as the
	 * way around it for testing; both are gone since 720p and 1080p run
	 * clean over any number of changes (doku/nachtlog/S11).
	 *
	 * The pitch is part of the geometry: the same 1280x720 ring can come
	 * with a 1280-byte pitch (a 720p source) or, for one moment of a change
	 * in flight, with the previous source's, and the plane programs the
	 * stride from the framebuffer -- so a changed pitch rebuilds it too.
	 */
	if (ring_w != d->src_w || ring_h != d->src_h || ring_pitch != d->src_pitch) {
		/* a refused disable is a plane still showing the old buffer -- say so and stop */
		if (d->on && !display_hide(d))
			return;
		if (d->fb_id)
			display_destroy_fb(d);
		d->src_w = ring_w;
		d->src_h = ring_h;
		d->src_pitch = ring_pitch;
		display_create_fb(d);
		info("buffer          %ux%u NV16, line pitch %u on panel %ux%u",
		     d->src_w, d->src_h, d->src_pitch, d->width, d->height);
	}

	/*
	 * An opaque page on the wall: no picture of our own under it (cover_follow() brings it back when the page goes). The
	 * signal is measured all the same, so that a claim of the warp is taken under the page: it pauses at once, and its
	 * first frame after the page carries the page's end - the page goes straight to the warped picture (before, the
	 * claim was refused under the page and the straight ring came after it, until the warp asked again).
	 */
	nosig_back(rt, &t);	/* the page without a signal goes with this - after h713-warp's claim, if one is to come */
	if (cover.on) {
		want_hold_end();
		if (d->on && !under_black_up(d))
			display_hide(d);
		if (warp_wants_ring())
			want_note_claim();
		return;
	}
	/* h713-warp will draw the ring: the plane stays off until its claim's first frame (want_hold(), at most WARP_HOLD_MS) */
	if (want_hold(d))
		return;
	display_show(d);
}

/*
 * One place where picture and sound are brought up to date, and in that
 * order: the sound follows the picture, so the picture is decided first.
 */
static void reevaluate(struct capture *cap, struct display *d, struct retry *rt,
		       struct audio *a)
{
	evaluate(cap, d, rt);
	audio_evaluate(a, cap, d->on || d->warped);
}

static int signal_fd(void)
{
	sigset_t mask;
	int fd;

	sigemptyset(&mask);
	sigaddset(&mask, SIGTERM);
	sigaddset(&mask, SIGINT);
	sigaddset(&mask, SIGHUP);
	if (sigprocmask(SIG_BLOCK, &mask, NULL))
		fail("sigprocmask: %s", strerror(errno));

	fd = signalfd(-1, &mask, SFD_CLOEXEC);
	if (fd < 0)
		fail("signalfd: %s", strerror(errno));

	return fd;
}

_Noreturn static void usage(const char *me)
{
	fprintf(stderr,
		"usage: %s [-d /dev/videoN] [-c /dev/dri/cardN] [-s SOCKET] [-p PRESET] [-g LUT]\n"
		"                 [-a AUDIO] [-t DB] [-C CONFIG] [--calculator PATH] [--data DIR]\n"
		"                 [--input NAME] [--lut PATH] [-n]\n"
		"        %s ctl [-s SOCKET] COMMAND [ARG...]      (h713-tv ctl help)\n"
		"        %s --hold-wall [-c /dev/dri/cardN]       (h713-mips-restart: the wall black over the restart)\n"
		"\n"
		"  -s PATH     control socket; default %s\n"
		"  -C FILE     configuration (start = auto|manual|last, state = PATH|none,\n"
		"              preset = NAME|last, data = DIR|none, calculator = PATH|none);\n"
		"              default %s; without it: start = auto, the mode saved in %s\n"
		"  -d DEVICE   capture device; without it the name \"%s\" is searched for\n"
		"              (on this board /dev/video1 -- video0 is cedrus)\n"
		"  -c DEVICE   DRM device; without it the driver \"%s\" is searched for\n"
		"              (on this board /dev/dri/card1 -- card0 is Panfrost)\n"
		"  -p PRESET   picture preset at the start (standard cinema vivid game computer hdr,\n"
		"              with device data also energy_saving and custom; last = the saved one,\n"
		"              none = send nothing). Without it the preset from the configuration\n"
		"              applies, else standard. Otherwise the firmware starts with empty\n"
		"              contrast and brightness registers and saturation 60\n"
		"  --calculator P\n"
		"              h713-pq, which computes the values from the device data (none =\n"
		"              do not compute, take the compiled-in table); default %s\n"
		"  --data D    directory of the unpacked vendor data (none = do not use it);\n"
		"              default %s\n"
		"  --input N   the input h713-pq is asked about; default %s\n"
		"  --lut PATH  where h713-pq writes its gamma curve; default %s\n"
		"  -g LUT      gamma curve for the CRTC when h713-pq delivers none (one DE2 bank,\n"
		"              2048 bytes; none = leave the identity ramp); default %s\n"
		"  -a AUDIO    audio at the start: auto (follows the picture, the default), on\n"
		"              (forced), off (forced silent), none (do not touch any ALSA card)\n"
		"  -t DB       HDMI level trim in the audio DSP (also --hdmi-trim DB): 0 (the\n"
		"              default) down to -100, in quarter dB; the volume itself is\n"
		"              h713-tv ctl volume\n"
		"  Controls, picture on/off, audio, RPCs while it runs: h713-tv ctl help\n"
		"  -n          only report what was found, then exit -- the display is untouched\n",
		me, me, me, CTL_SOCKET, CONF_FILE, STATE_FILE, V4L2_DRIVER, DRM_DRIVER,
		PQ_BIN, PQ_DATA, PQ_INPUT, PQ_LUT, GAMMA_FILE);
	exit(2);
}

/* Loop instrumentation (23.09.2026): which handler holds the loop while the
 * warp waits for its answer. Logs any handler over 10 ms. */
static double loop_ms(const struct timespec *a, const struct timespec *b)
{
	return (b->tv_sec - a->tv_sec) * 1e3 + (b->tv_nsec - a->tv_nsec) / 1e6;
}
#define LOOP_TIMED(name, stmt) do { \
	struct timespec _a, _b; \
	clock_gettime(CLOCK_MONOTONIC, &_a); \
	stmt; \
	clock_gettime(CLOCK_MONOTONIC, &_b); \
	if (loop_ms(&_a, &_b) > 10.0) \
		info("timing          %s held the loop %.1f ms", name, loop_ms(&_a, &_b)); \
} while (0)

int main(int argc, char **argv)
{
	struct opts o = { .gamma = GAMMA_FILE, .audio = "auto", .trim = "0" };
	struct capture cap = { .fd = -1 };
	struct display d = { .fd = -1 };
	struct retry rt = { .fd = -1 };
	/*
	 * The volume starts where its stage stands (audio_search()) and moves
	 * only with "ctl volume"; the DSP starts at 0 dB (S16's reference) and
	 * unmuted as far as the listener is concerned -- the automaton mutes it.
	 */
	struct audio au = { .settle_fd = -1, .tick_fd = -1 };
	struct conf conf = { .path = CONF_FILE };
	enum audio_policy apol;
	struct pollfd fds[14];
	const char *sock = CTL_SOCKET;
	const char *startpreset = "standard";
	bool gamma_own = false;		/* the curve is computed here (gamma.c) and not read from a file */
	int sfd, arg, rc = 0;

	setvbuf(stdout, NULL, _IOLBF, 0);

	if (argc >= 2 && !strcmp(argv[1], "--hold-wall"))
		return hold_wall(argc >= 4 && !strcmp(argv[2], "-c") ? argv[3] : NULL);
	if (argc >= 2 && !strcmp(argv[1], "ctl")) {
		int a = 2;

		if (argc >= 4 && !strcmp(argv[2], "-s")) {
			sock = argv[3];
			a = 4;
		}
		return client(argc - a, argv + a, sock);
	}

	for (arg = 1; arg < argc; arg++) {
		if (!strcmp(argv[arg], "-d") && arg + 1 < argc)
			o.video = argv[++arg];
		else if (!strcmp(argv[arg], "-c") && arg + 1 < argc)
			o.card = argv[++arg];
		else if (!strcmp(argv[arg], "-s") && arg + 1 < argc)
			sock = argv[++arg];
		else if (!strcmp(argv[arg], "-p") && arg + 1 < argc)
			o.preset = argv[++arg];
		else if (!strcmp(argv[arg], "-g") && arg + 1 < argc) {
			o.gamma = argv[++arg];
			o.gamma_set = true;
		} else if ((!strcmp(argv[arg], "--calculator") ||
			    !strcmp(argv[arg], "--rechner")) && arg + 1 < argc)	/* GERMAN ALIAS */
			o.calculator = argv[++arg];
		/* every GERMAN ALIAS name here goes out after v0.8-beta */
		else if ((!strcmp(argv[arg], "--data") ||
			  !strcmp(argv[arg], "--daten")) && arg + 1 < argc)	/* GERMAN ALIAS */
			o.data = argv[++arg];
		else if ((!strcmp(argv[arg], "--input") ||
			  !strcmp(argv[arg], "--eingang")) && arg + 1 < argc)	/* GERMAN ALIAS */
			o.input = argv[++arg];
		else if (!strcmp(argv[arg], "--lut") && arg + 1 < argc)
			o.lut = argv[++arg];
		else if (!strcmp(argv[arg], "-a") && arg + 1 < argc)
			o.audio = argv[++arg];
		else if ((!strcmp(argv[arg], "-t") ||
			  !strcmp(argv[arg], "--hdmi-trim")) && arg + 1 < argc)
			o.trim = argv[++arg];
		else if (!strcmp(argv[arg], "-C") && arg + 1 < argc)
			conf.path = argv[++arg];
		else if (!strcmp(argv[arg], "-n"))
			o.report_only = true;
		else
			usage(argv[0]);
	}

	if (!audio_policy_parse(o.audio, &apol))
		fail("-a %s: unknown (auto on off none)", o.audio);
	if (!audio_trim_parse(o.trim, &au.trim_q))
		fail("--hdmi-trim %s: a number in dB from %d to 0 is expected",
		     o.trim, AUDIO_TRIM_MIN_DB);

	/* first the lock, then the devices -- see control_lock() */
	if (!o.report_only)
		control_lock(&ctl, sock);
	/*
	 * The start mode comes from tv.conf and the state file, and it is
	 * decided before anything is shown: the first evaluate() below is the
	 * one that puts the picture up or leaves the console.
	 */
	fwc_init();
	gamma_init();
	conf_read(&conf);
	if (o.calculator)
		snprintf(conf.calculator, sizeof(conf.calculator), "%s", o.calculator);
	if (o.data)
		snprintf(conf.data, sizeof(conf.data), "%s", o.data);
	if (conf.volume_vendor) {
		char why[240], curve[96];

		if (!strcmp(conf.data, "none"))
			warn("volume_curve = vendor, but data = none -- the built-in curve");
		else if (!audio_curve_load(conf.data, why, sizeof(why)))
			warn("volume_curve = vendor: %s -- the built-in curve", why);
		else {
			vendor_curve_on = true;
			info("volume          the device's own curve (%s/%s): %s", conf.data, AUDIO_CURVE_FILE,
			     audio_curve_text(curve, sizeof(curve)));
		}
	}
	if (o.input)
		snprintf(conf.input, sizeof(conf.input), "%s", o.input);
	if (o.lut)
		snprintf(conf.lut, sizeof(conf.lut), "%s", o.lut);
	ctl.conf = &conf;
	ctl.state_path = conf.keep ? conf.state_path : NULL;
	state_read(&ctl);
	ctl.policy = start_policy(&ctl);
	ctl.source = conf.source;
	/* a client that hangs up mid-answer must not take the daemon with it (S12 F1) */
	signal(SIGPIPE, SIG_IGN);

	/*
	 * Which preset to come up with, and which values were kept for it.
	 * The order is -p, then tv.conf, then "standard" -- the command line
	 * is the last word, the file the standing setting. "last" (and the
	 * older "zuletzt") takes the name out of the kept values; without
	 * them it is "standard".
	 */
	saved.path = conf.saved_path[0] && !o.report_only ? conf.saved_path : NULL;
	saved_read(&saved);
	/* the firmware's own colour that was kept: the steps are known before the preset's mode is sent (fwc_mode_begin) */
	if (!o.report_only) {
		fwc_adopt(saved.wb_have, saved.wb, saved.cm_have, saved.cm);
		gamma_adopt(saved.gm_have, saved.gm);
	}
	startpreset = o.preset ? o.preset : (conf.preset[0] ? conf.preset : "standard");
	if (!strcasecmp(startpreset, "last") || !strcasecmp(startpreset, "zuletzt"))
		startpreset = saved.preset[0] ? saved.preset : "standard";

	/*
	 * h713-pq is started here and collected after the devices are open:
	 * a Python start costs about 200 ms, and the capture and DRM devices
	 * cost their own time -- there is no reason to spend both one after
	 * the other (plan 113 A.3).
	 */
	if (!o.report_only && strcasecmp(startpreset, "none"))
		pq_start(&pq, &conf, startpreset);
	/* the board's own gamma curve, asked for alongside the first child */
	if (!o.report_only)
		tse_gamma_start(&tsegamma, &conf);

	capture_open(&cap, o.video);

	d.fd = display_open_card(o.card);
	if (drmSetClientCap(d.fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) ||
	    drmSetClientCap(d.fd, DRM_CLIENT_CAP_ATOMIC, 1))
		fail("this kernel does not hand out atomic and universal planes: %s",
		     strerror(errno));
	display_find_crtc(&d);
	display_find_plane(&d);

	/*
	 * Opening the card as its first client made this process the DRM master
	 * (drm_open_helper). display_release_master() cannot know that -- its
	 * flag starts at false -- so it never gave that master back, and the
	 * console ran with a foreign master over it even while nothing was
	 * shown (S12 A1). Drop it here; a failure means somebody else holds it,
	 * which is the state wanted anyway.
	 */
	if (drmDropMaster(d.fd) && errno != EINVAL)
		warn("DROP_MASTER at the start: %s", strerror(errno));
	d.master = false;

	/*
	 * The answer from h713-pq, collected at the last moment before the
	 * gamma curve is needed. Everything above ran alongside it.
	 */
	if (!o.report_only) {
		pq_collect(&pq);
		if (pq.ok)
			info("picture values  %u presets and gamma %.2f from %s (h713-pq, %u ms)",
			     pq_presets_n, pq.gamma, pq.data, pq.ms);
		else
			warn("picture values  %s -- the compiled-in table applies",
			     pq.why);
		/*
		 * The curve h713-pq just wrote is the one that belongs to
		 * this device's data. -g on the command line still wins: it
		 * is an explicit order, and it is how a curve can be tried
		 * without touching anything else.
		 */
		if (pq.ok && pq.lut_bytes && !o.gamma_set)
			o.gamma = pq.lut;
		/*
		 * And the board's own measured curve beats both computed
		 * ones -- it is this panel's, not a power law. -g is an
		 * explicit order and still wins over all of it.
		 */
		if (tse_gamma_collect(&tsegamma) && o.gamma_set)
			tsegamma.ok = false;		/* -g wins; said below */
		if (tsegamma.ok) {
			char why[200] = "";

			gamma_disp = &d;
			if (!display_gamma_ready(&d))
				snprintf(why, sizeof(why), "the CRTC has no GAMMA_LUT of the length this needs");
			else if (!gamma_attach(TSE_SLOTS, &gamma_io, why, sizeof(why)))
				;			/* why says why */
			else
				gamma_own = true;
			if (!gamma_own) {
				tsegamma.ok = false;
				snprintf(tsegamma.why, sizeof(tsegamma.why), "%s", why);
			}
		}
		if (gamma_own) {
			/* the picture mode asks for its colour temperature before the first curve is made */
			gamma_mode_temp(preset_ctemp(preset_find(startpreset)), "the start");
		} else {
			gamma_unavailable(tsegamma.why[0] ? tsegamma.why : "-g gives the curve");
			warn("gamma           %s -- %s applies",
			     tsegamma.why[0] ? tsegamma.why : "-g was given",
			     o.gamma);
		}
	}
	if (!o.report_only) {
		gamma_loaded = o.gamma;
		if (!gamma_own)
			display_gamma_load(&d, o.gamma);
	}

	if (o.report_only) {
		struct v4l2_dv_timings t;
		char sigbuf[64];
		int sig = capture_signal(&cap, &t);

		/*
		 * A refused source is measured, only not locked, and -n is
		 * the command someone runs to find out what is on the cable.
		 * QUERY_DV_TIMINGS hands the measurement back with the error
		 * (kernel 0136m/0136v), so name it here too.
		 */
		if (sig == 3 && t.bt.width)
			info("signal          %s, not in the firmware's table",
			     signal_text(&t, sigbuf, sizeof(sigbuf)));
		else
			info("signal          %s", sig == 1 ? "present" :
			     sig == 2 ? "change in flight" :
			     sig == 3 ? "not in the firmware's table" :
			     sig == 0 ? "no signal" : "not readable");
		/*
		 * The audio chain, looked at and not touched: -n reports, it
		 * does not switch. So no audio_open() here -- it would set the
		 * path -- and no audio_close() either, which would mute.
		 */
		if (apol != AUDIO_NONE) {
			char vol[64];

			if (audio_search(&au))
				info("audio           %s (card %d) + %s (card %d), %s, mute switch %s",
				     au.msp.id, au.msp.index, au.codec.name,
				     au.codec.index,
				     audio_volume_text(&au, vol, sizeof(vol)),
				     au.codec_mute ? au.codec_mute : "in the DSP only");
			else
				info("audio           %s", au.why);
			if (au.msp.ctl)
				snd_ctl_close(au.msp.ctl);
			if (au.codec.ctl)
				snd_ctl_close(au.codec.ctl);
			snd_config_update_free_global();
		}
		props_put(&d.plane_props);
		close(d.fd);
		close(cap.fd);
		return sig == 1 ? 0 : 1;
	}

	/* a previous run may have left the console dark; see console_restore() - unless the wall is held over a restart (TODO 2.96) */
	if (!hold_adopt(&d))
		console_restore();
	if (!gamma_own || !gamma_start()) {
		if (gamma_own) {
			/* the first curve did not go on the CRTC: the file applies, and the two controls say so */
			warn("gamma           the computed curve could not be put on the CRTC -- %s applies", o.gamma);
			snprintf(tsegamma.why, sizeof(tsegamma.why), "the computed curve could not be put on the CRTC");
			display_gamma_load(&d, o.gamma);
		}
		display_gamma_apply(&d);
	}

	capture_select_input(&cap);
	/*
	 * The vendor preset is part of bringing the picture path up: without it
	 * the firmware runs with whatever its registers hold after reset, which
	 * is not even "standard" (contrast/brightness registers empty,
	 * saturation 60; measured 08.09.2026). The kernel's init sequence sends
	 * the four steps and the mode, the nine values are this program's job.
	 * Once per start, see preset_apply().
	 */
	if (strcasecmp(startpreset, "none")) {
		const struct preset *p = preset_find(startpreset);
		char msg[512], names[192];
		int ret;

		preset_names(names, sizeof(names));
		if (!p) {
			/*
			 * A name that does not exist is not a reason to leave
			 * the wall dark. It was right to abort while the table
			 * was compiled in and complete; now the set of names
			 * depends on the extraction, and a preset that the
			 * data does not carry must not cost the picture
			 * (plan 113 A.5).
			 */
			warn("preset          \"%s\" does not exist (%s) -- standard", startpreset,
			     names);
			startpreset = "standard";
			p = preset_find(startpreset);
		}
		ret = p ? preset_apply(&cap, p, msg, sizeof(msg)) : -1;
		if (ret < 0)
			warn("preset          %s -- not sent", p ? msg : "no preset");
		else if (ret)
			warn("preset          %s -- %d values not set", msg, ret);
		else
			info("preset          %s (%s)", msg,
			     preset_is_from_data(p) ? "from the device data"
						     : "the compiled-in table");
		if (p && ret >= 0) {
			snprintf(preset_current, sizeof(preset_current), "%s", p->name);
			preset_current_from_data = preset_is_from_data(p);

			/* the third layer, on top of the second */
			ret = saved_apply(&cap, &saved, p->name, msg, sizeof(msg));
			if (ret < 0)
				warn("saved           %s", msg);
			else if (ret)
				info("saved           %d value%s from %s: %s", ret,
				     ret == 1 ? "" : "s", saved.path, msg);
		}
	}
	/*
	 * The aspect is part of what was kept. It is set before the first
	 * picture, so no plane has to be taken down for it.
	 */
	if (saved.present && saved.aspect[0] && d.has_aspect) {
		uint64_t val;

		if (aspect_refused(saved.aspect)) {
			warn("%s:%u: aspect = \"%s\" stops the picture -- dropped, the plane keeps %s",
			     saved.path, saved.aspect_line, saved.aspect,
			     prop_enum_name(&d.plane_props, "aspect", d.aspect));
		} else if (prop_enum_parse(&d.plane_props, "aspect", saved.aspect, &val)) {
			d.aspect = val;
			info("saved           aspect %s", saved.aspect);
		} else {
			char names[128];

			aspect_names(&d, names, sizeof(names));
			warn("%s:%u: the plane does not know aspect = \"%s\" (%s) -- dropped",
			     saved.path, saved.aspect_line, saved.aspect, names);
		}
	}
	/* and the zoom, for the same reason and at the same moment */
	if (saved.present && saved.zoom[0]) {
		enum zoom_mode m;
		unsigned int v, x, y, w, hh;

		if (zoom_parse_text(saved.zoom, &m, &v) &&
		    (m == ZOOM_OFF || d.has_windows)) {
			d.zoom = m;
			d.zoom_arg = v;
			display_zoom_apply(&d);
			info("saved           zoom %s", saved.zoom);
		} else if (sscanf(saved.zoom, "%u,%u,%u,%u", &x, &y, &w, &hh) == 4 &&
			   !x && !y && w == d.width && hh == d.height) {
			/*
			 * The full-panel rectangle every version before 0133f
			 * wrote. It meant "no zoom", and that is what it still
			 * gets; any other rectangle of that era meant a window
			 * this program no longer has and is dropped below.
			 */
			info("saved           zoom off (the rectangle of an older version)");
		} else {
			warn("%s:%u: zoom = \"%s\" is not \"off\", \"in FACTOR\" or \"out PERCENT\"%s -- dropped",
			     saved.path, saved.zoom_line, saved.zoom,
			     d.has_windows ? "" :
				     ", and this kernel has no zoom windows");
		}
	}
	/*
	 * The firmware's own colour: what was kept for it, then a look at the registers. It does not depend on the preset
	 * (the white balance belongs to the device), so it is laid on whatever preset came up.
	 */
	if (!o.report_only)
		fwc_sync("the start");
	capture_subscribe(&cap);
	audio_open(&au, &cap, apol);
	control_listen(&ctl);
	sfd = signal_fd();
	rt.fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (rt.fd < 0)
		fail("timerfd_create: %s", strerror(errno));


	/* the EDID half tv.conf asks for, before the first picture is judged */
	edid_apply_start(&conf, &cap, &d, &rt);
	/*
	 * h713-warp runs (its control socket is there) but has had no chance to say its word on the want link yet - this
	 * program's socket is only just up: its "ring" is assumed for WARP_HOLD_MS, as after a restart of h713-warp, so that
	 * the first picture waits for its claim instead of showing the straight ring first (17.10.2026, HY310: h713-tv
	 * restarted, the signal stood at once, the straight ring 0.5 s before the claim). "warp want none" ends it at once.
	 */
	if (!access(WARP_CTL_SOCKET, F_OK)) {
		wish.ring = true;
		clock_gettime(CLOCK_MONOTONIC, &wish.gone);
		info("warp            h713-warp runs (%s) -- its word on the want link is waited for, at most %d ms", WARP_CTL_SOCKET,
		     WARP_HOLD_MS);
	}
	/* The state at startup counts as much as any later change. */
	reevaluate(&cap, &d, &rt, &au);

	/*
	 * Six sources, three of which may be absent: the control socket when
	 * its bind failed, and the two audio timers with -a none; then the
	 * warp's and the overlay's connections, set in the loop, a client's
	 * flip fence while an overlay change waits for it, the warp's grace
	 * after a "note source", the wait for the warp's first frame after
	 * an opaque page went ("note cover off"), and the end of "ctl bare". poll()
	 * ignores an entry with a negative fd and reports revents 0 for it, so
	 * the table keeps its fixed indices instead of shifting.
	 */
	fds[0].fd = cap.fd;
	fds[0].events = POLLPRI;
	fds[1].fd = sfd;
	fds[1].events = POLLIN;
	fds[2].fd = rt.fd;
	fds[2].events = POLLIN;
	fds[3].fd = ctl.lfd;
	fds[3].events = POLLIN;
	fds[4].fd = au.settle_fd;
	fds[4].events = POLLIN;
	fds[5].fd = au.tick_fd;
	fds[5].events = POLLIN;

	int rc_poll;

	for (;;) {
		fds[6].fd = warp.peer;	/* only while the warp has claimed */
		fds[6].events = POLLIN;
		fds[7].fd = osd.peer;	/* only while h713-osd has claimed */
		fds[7].events = POLLIN;
		/* an overlay change waiting for a client's flip (not one waiting for the first frame after a page) */
		fds[8].fd = osd.queued && warp.client && !cover.on && !cover.resuming ? warp.flip : -1;
		fds[8].events = POLLIN;
		/* a claim the source no longer allows: h713-warp's grace (warp_revoke()) */
		fds[9].fd = warp.revoking ? warp.revoke_fd : -1;
		fds[9].events = POLLIN;
		/* the page went: the overlay's change waits for the warp's next frame, this long at most */
		fds[10].fd = cover.resuming ? cover.resume_fd : -1;
		fds[10].events = POLLIN;
		/* h713-warp's word whether it claims the ring (P3), and the end of the straight ring's wait for that claim */
		fds[11].fd = wish.peer;
		fds[11].events = POLLIN;
		fds[12].fd = wish.armed ? wish.fd : -1;
		fds[12].events = POLLIN;
		/* the end of "ctl bare": its time, a net for a caller that did not say "bare 0" */
		fds[13].fd = bare.on ? bare.fd : -1;
		fds[13].events = POLLIN;
		{
			static struct timespec last_ret;
			struct timespec now;

			clock_gettime(CLOCK_MONOTONIC, &now);
			if (last_ret.tv_sec && loop_ms(&last_ret, &now) > 10.0)
				info("timing          the loop body took %.1f ms before polling again", loop_ms(&last_ret, &now));
			rc_poll = poll(fds, sizeof(fds) / sizeof(fds[0]), -1);
			clock_gettime(CLOCK_MONOTONIC, &last_ret);
		}
		if (rc_poll < 0) {
			if (errno == EINTR)
				continue;
			warn("poll: %s", strerror(errno));
			rc = 1;
			break;
		}
		if (fds[1].revents & POLLIN) {
			struct signalfd_siginfo si;

			if (read(sfd, &si, sizeof(si)) != sizeof(si))
				si.ssi_signo = 0;
			if (si.ssi_signo == SIGHUP) {
				/* not an exit: look again, the way a reload would */
				info("reload          SIGHUP -- the state is evaluated again");
				reevaluate(&cap, &d, &rt, &au);
				continue;
			}
			info("exit            signal %u received", si.ssi_signo);
			break;
		}
		if (fds[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
			/*
			 * The device went away under us (driver unbound or
			 * unloaded). That is not this program's failure: the
			 * unit is bound to the device (BindsTo) and systemd is
			 * about to stop it anyway, and an exit code of 1 here
			 * would only leave it standing as "failed" instead of
			 * "inactive". Measured 08.09.2026: the unbind reached
			 * this poll before systemd's stop did.
			 */
			info("exit            the capture device is gone (poll 0x%x) -- the unit follows the device",
			     fds[0].revents);
			break;
		}
		if (fds[2].revents & POLLIN) {
			uint64_t ticks;

			if (read(rt.fd, &ticks, sizeof(ticks)) != sizeof(ticks))
				warn("reading the timerfd: %s", strerror(errno));
			LOOP_TIMED("the retry timer\'s re-evaluation", reevaluate(&cap, &d, &rt, &au));
		}
		if (fds[0].revents & POLLPRI) {
			unsigned int seen = capture_drain_events(&cap);

			/*
			 * A control event carries the audio status and nothing
			 * else; asking QUERY_DV_TIMINGS about it would cost
			 * 20 ms for an answer nobody wanted. An event of an
			 * unknown kind is treated as before, i.e. as a reason
			 * to look at everything.
			 */
			if (!seen || (seen & EV_SOURCE_CHANGE)) {
				LOOP_TIMED("a capture event's evaluation", evaluate(&cap, &d, &rt));
				LOOP_TIMED("the colour check after a source change", fwc_sync("a source change"));
			}
			LOOP_TIMED("a capture event's audio evaluation", audio_evaluate(&au, &cap, d.on || d.warped));
		}
		/* before the warp's own connection: "warp want none" is said before a release, and is to be heard first */
		if (fds[11].fd >= 0 && fds[11].revents && want_serve())
			LOOP_TIMED("the warp's word", reevaluate(&cap, &d, &rt, &au));
		if (fds[6].fd >= 0 && fds[6].revents) {
			bool again = false;

			LOOP_TIMED("the warp's frame", again = warp_serve(&cap, &d));
			if (again)
				LOOP_TIMED("the warp's re-evaluation", reevaluate(&cap, &d, &rt, &au));
			else if (osd.want >= 0 && !osd.shown)	/* the warp's first frame is up: the overlay back over it */
				LOOP_TIMED("the overlay over the warp", osd_resume(&d));
		}
		if (fds[7].fd >= 0 && fds[7].revents)
			LOOP_TIMED("an overlay line", osd_serve(&d));
		if (fds[9].fd >= 0 && (fds[9].revents & POLLIN) && warp_revoke_due(&d))
			LOOP_TIMED("the end of the warp's grace", reevaluate(&cap, &d, &rt, &au));
		if (fds[8].fd >= 0 && fds[8].revents)
			LOOP_TIMED("the overlay after a client's flip", osd_settle(&d));
		if (fds[3].revents & POLLIN) {
			struct timespec t0, t1, t2;
			bool again;

			clock_gettime(CLOCK_MONOTONIC, &t0);
			again = control_serve(&ctl, &cap, &d, &rt, &au);
			clock_gettime(CLOCK_MONOTONIC, &t1);
			if (again)
				reevaluate(&cap, &d, &rt, &au);
			clock_gettime(CLOCK_MONOTONIC, &t2);
			if ((t2.tv_sec - t0.tv_sec) * 1e3 + (t2.tv_nsec - t0.tv_nsec) / 1e6 > 10.0)
				info("timing          a control command took %.1f ms to serve%s%.1f ms to re-evaluate",
				     (t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6,
				     again ? " and " : " (no re-evaluation) ",
				     again ? (t2.tv_sec - t1.tv_sec) * 1e3 + (t2.tv_nsec - t1.tv_nsec) / 1e6 : 0.0);
		}
		if (fds[4].revents & POLLIN) {
			uint64_t ticks;

			if (read(au.settle_fd, &ticks, sizeof(ticks)) != sizeof(ticks))
				warn("audio           reading the timerfd: %s", strerror(errno));
			LOOP_TIMED("the audio settle", audio_settled(&au, &cap, d.on || d.warped));
		}
		if (fds[5].revents & POLLIN) {
			uint64_t ticks;

			if (read(au.tick_fd, &ticks, sizeof(ticks)) != sizeof(ticks))
				warn("audio           reading the timerfd: %s", strerror(errno));
			LOOP_TIMED("the audio tick", audio_tick(&au, &cap, d.on || d.warped));
		}
		if (fds[10].fd >= 0 && (fds[10].revents & POLLIN))
			LOOP_TIMED("the overlay after a page, alone", cover_resume_due(&d));
		if (fds[12].fd >= 0 && (fds[12].revents & POLLIN) && want_hold_due())
			LOOP_TIMED("the end of the wait for the warp's claim", reevaluate(&cap, &d, &rt, &au));
		if (fds[13].fd >= 0 && (fds[13].revents & POLLIN)) {
			uint64_t ticks;

			if (read(bare.fd, &ticks, sizeof(ticks)) != sizeof(ticks))
				warn("bare            reading the timerfd: %s", strerror(errno));
			LOOP_TIMED("the end of bare", bare_end(&d, "its time is over (nobody said \"bare 0\")"));
		}
		/* whatever the handlers did with the overlay: does an opaque page hide the picture now? */
		cover_follow(&cap, &d, &rt, &au);
		nosig_follow(&cap, &d, &rt, &au);
		capture_follow();
		if (wall_black.fb_id)
			wall_black_free(&d);	/* the ring, a page or a claim took the wall from the black framebuffer */
	}

	/*
	 * The same door for every way out: sound off, picture off, console
	 * back. A "systemctl stop" must not leave a still frame standing on
	 * the wall, nor a tone in the room, so a refused disable is an error
	 * exit, not a silent one.
	 */
	retry_stop(&rt);
	audio_close(&au);
	leaving = true;
	/* stopped for a restart of the picture path while a holder runs: the wall black, not the console (TODO 2.96) */
	if (!hold_take(&d)) {
		warp_release(&d);
		osd_release(&d);	/* an opaque page over black goes too: the console, and its keyboard, are back */
		if (!display_hide(&d))
			rc = 1;
	}
	control_close(&ctl);
	display_destroy_fb(&d);
	if (d.gamma_blob)
		drmModeDestroyPropertyBlob(d.fd, d.gamma_blob);
	props_put(&d.crtc_props);
	props_put(&d.plane_props);
	close(d.fd);
	close(rt.fd);
	if (warp.revoke_fd >= 0)
		close(warp.revoke_fd);
	if (cover.resume_fd >= 0)
		close(cover.resume_fd);
	if (bare.fd >= 0)
		close(bare.fd);
	if (wish.peer >= 0)
		close(wish.peer);
	if (wish.fd >= 0)
		close(wish.fd);
	close(sfd);
	close(cap.fd);

	return rc;
}
