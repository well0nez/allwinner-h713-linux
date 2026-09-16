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
#include <sys/signalfd.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/timerfd.h>
#include <sys/un.h>
#include <sys/wait.h>

#include <linux/tiocl.h>
#include <linux/videodev2.h>

#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>

#include <alloca.h>		/* the snd_*_alloca() macros of libasound */
#include <alsa/asoundlib.h>

#define DRM_DRIVER	"sun50i-h713-afbd"	/* patch 0093 */
#define V4L2_DRIVER	"sun50i-h713-hdmirx"	/* patch 0094 */


/* ------------------------------------------------------------------ *
 * Talking to the journal
 * ------------------------------------------------------------------ */

__attribute__((format(printf, 1, 2)))
static void info(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	putchar('\n');
	fflush(stdout);
}

__attribute__((format(printf, 1, 2)))
static void warn(const char *fmt, ...)
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
	struct v4l2_dv_timings last_t;
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
 * Returns 1 with *t filled in, 0 for "no signal", -1 for a broken device.
 */
static int capture_signal(struct capture *cap, struct v4l2_dv_timings *t)
{
	memset(t, 0, sizeof(*t));
	if (!ioctl(cap->fd, VIDIOC_QUERY_DV_TIMINGS, t))
		return 1;
	if (errno == ENOLCK)
		return 2;	/* a change in flight, see struct retry */
	if (errno == ENOLINK || errno == ENODATA)
		return 0;

	warn("QUERY_DV_TIMINGS: %s", strerror(errno));

	return -1;
}

/*
 * The ring's line pitch, as the capture driver reports it in the format
 * (bytesperline = INCAP rowbyte * 16, kernel 0131). It is the width for 1920
 * and 1280 and 1376 for 1366: the firmware rounds the pitch up to a multiple
 * of 16, and the plane must be told that pitch, not the width, or it reads
 * a 1366-wide picture with a 1366-byte stride and every line slips ten
 * bytes. Asked after QUERY_DV_TIMINGS, which is what makes the format
 * follow the signal. A format that does not carry the width just measured
 * is a race with a change in flight; then the rounding rule stands in, with
 * a line in the journal.
 */
static unsigned int capture_pitch(struct capture *cap, unsigned int width)
{
	struct v4l2_format f;
	unsigned int rounded = (width + 15) & ~15u;

	memset(&f, 0, sizeof(f));
	f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	if (ioctl(cap->fd, VIDIOC_G_FMT, &f)) {
		warn("G_FMT: %s -- line pitch %u by the rule of 16",
		     strerror(errno), rounded);
		return rounded;
	}
	if (f.fmt.pix_mp.width != width ||
	    f.fmt.pix_mp.plane_fmt[0].bytesperline < width) {
		warn("G_FMT reports %ux%u with line pitch %u instead of width %u -- line pitch %u by the rule of 16",
		     f.fmt.pix_mp.width, f.fmt.pix_mp.height,
		     f.fmt.pix_mp.plane_fmt[0].bytesperline, width, rounded);
		return rounded;
	}

	return f.fmt.pix_mp.plane_fmt[0].bytesperline;
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
	struct props crtc_props;
	uint32_t gamma_blob;		/* GAMMA_LUT blob from -g, 0 = none */
	struct props plane_props;
	/* framebuffer: geometry and format carrier only, never shown */
	uint32_t fb_handle;
	uint32_t fb_id;
	uint64_t fb_size;
	bool master;
	bool on;
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
	info("plane           %u, NV16, mode hdmi-ring%s%s", d->plane_id,
	     d->has_aspect ? ", format " : "",
	     d->has_aspect ? prop_enum_name(&d->plane_props, "aspect", d->aspect) : "");
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
 *    capture_pitch()). The dumb buffer is therefore allocated with the pitch
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

static void display_release_master(struct display *d)
{
	if (!d->master)
		return;
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

static uint16_t gamma_12_to_16(uint32_t v)
{
	/* the inverse of drm_color_lut_extract() for 12 bits, see gamma_test.c */
	return (uint16_t)((v * 65535u + 2047u) / 4095u);
}

static void display_gamma_load(struct display *d, const char *path)
{
	struct drm_color_lut lut[GAMMA_ENTRIES];
	uint32_t bank[DE2_BANK_DWORDS];
	uint64_t size = 0;
	unsigned int i;
	size_t got;
	FILE *f;

	d->gamma_blob = 0;
	if (!path || !strcasecmp(path, "none"))
		return;
	if (!props_get(d->fd, d->crtc_id, DRM_MODE_OBJECT_CRTC, &d->crtc_props)) {
		warn("gamma           CRTC properties not readable: %s", strerror(errno));
		return;
	}
	if (!prop_id(&d->crtc_props, "GAMMA_LUT") ||
	    !prop_value(&d->crtc_props, "GAMMA_LUT_SIZE", &size) ||
	    size != GAMMA_ENTRIES) {
		warn("gamma           CRTC %u has no GAMMA_LUT with %u entries (kernel 0095) -- the identity ramp stays",
		     d->crtc_id, GAMMA_ENTRIES);
		return;
	}
	f = fopen(path, "rb");
	if (!f) {
		warn("gamma           %s: %s -- the identity ramp stays", path, strerror(errno));
		return;
	}
	got = fread(bank, 1, sizeof(bank), f);
	fclose(f);
	if (got != sizeof(bank)) {
		warn("gamma           %s: %zu bytes instead of %zu (one DE2 bank from h713-pq) -- the identity ramp stays",
		     path, got, sizeof(bank));
		return;
	}
	for (i = 0; i < DE2_BANK_DWORDS; i++) {
		uint16_t a = gamma_12_to_16(bank[i] & 0xfff);
		uint16_t b = gamma_12_to_16((bank[i] >> 12) & 0xfff);

		lut[2 * i].red = lut[2 * i].green = lut[2 * i].blue = a;
		lut[2 * i + 1].red = lut[2 * i + 1].green = lut[2 * i + 1].blue = b;
		lut[2 * i].reserved = lut[2 * i + 1].reserved = 0;
	}
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

static bool display_show(struct display *d)
{
	drmModeAtomicReq *req;
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
	ok &= add(req, d, "SRC_W", (uint64_t)d->src_w << 16);
	ok &= add(req, d, "SRC_H", (uint64_t)d->src_h << 16);
	ok &= add(req, d, "CRTC_X", 0);
	ok &= add(req, d, "CRTC_Y", 0);
	ok &= add(req, d, "CRTC_W", d->width);
	ok &= add(req, d, "CRTC_H", d->height);
	ok &= add(req, d, "hdmi-ring", 1);
	if (d->has_aspect)
		ok &= add(req, d, "aspect", d->aspect);
	ok &= add_gamma(req, d);
	/*
	 * No "saturation" here. The chroma gain has one owner -- the firmware's
	 * SetSaturation RPC behind V4L2_CID_SATURATION on the capture node; the
	 * display driver stopped writing it (patch 0104, doku/nachtlog/I3). Set
	 * it with h713-tv ctl set saturation 0..100; it survives plane
	 * off/on because nothing resets the register any more.
	 */

	if (!ok) {
		drmModeAtomicFree(req);
		display_release_master(d);
		return false;
	}

	ret = drmModeAtomicCommit(d->fd, req, 0, NULL);
	drmModeAtomicFree(req);

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
	info("picture         plane %u on, %ux%u out of the capture ring", d->plane_id,
	     d->width, d->height);

	return true;
}

/*
 * Returns false when the plane is still up. In that case the master is kept
 * and the state stays "on": claiming the console is back while a frame is
 * standing on the wall would be the one lie this program must not tell.
 */
static void console_restore(void);

static bool display_hide(struct display *d)
{
	drmModeAtomicReq *req;
	bool ok;
	int ret;

	if (!d->on) {
		display_release_master(d);
		return true;
	}

	req = drmModeAtomicAlloc();
	if (!req)
		fail("out of memory");

	ok = add(req, d, "FB_ID", 0);
	ok &= add(req, d, "CRTC_ID", 0);
	ret = ok ? drmModeAtomicCommit(d->fd, req, 0, NULL) : -EINVAL;
	drmModeAtomicFree(req);

	if (ret) {
		warn("the plane cannot be switched off (%s) -- the picture is still up, the console is NOT back",
		     ok ? strerror(errno) : "property missing");
		return false;
	}

	d->on = false;
	display_release_master(d);
	console_restore();
	info("console         plane off, RGB channel and selector back, console unblanked");

	return true;
}

/* ------------------------------------------------------------------ *
 * The state machine
 * ------------------------------------------------------------------ */

struct opts {
	const char *video;
	const char *card;
	const char *preset;	/* -p; NULL: whatever tv.conf says, else "standard" */
	const char *gamma;	/* DE2 bank file for GAMMA_LUT; "none" leaves the CRTC alone */
	bool gamma_gesetzt;	/* -g was given: it wins over h713-pq's own LUT */
	const char *rechner;	/* --rechner, overrides tv.conf's "rechner" */
	const char *daten;	/* --daten,   overrides tv.conf's "daten" */
	const char *eingang;	/* --eingang, which input h713-pq is asked about */
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
static const struct { const char *kurz; const char *lang; } ctrl_alias[] = {
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
	for (i = 0; ctrl_alias[i].kurz; i++)
		if (!strcmp(w, ctrl_alias[i].kurz)) {
			snprintf(w, sizeof(w), "%s", ctrl_alias[i].lang);
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
 *    mute above. Both stay with the automaton: the volume is a fixed level
 *    match between HDMI and the box's own tones (0 dB unless --hdmi-trim says
 *    otherwise), the mute is the automaton's silence. What the listener
 *    turns with "ctl volume" is the *codec's* "DAC Playback Volume", because
 *    that one sits behind both sources and a volume that changed with the
 *    input would be two volumes (decision 08.09. 22:10). "ctl mute" takes
 *    the DSP mute and, where the codec offers a switch, that one too.
 *  - "Present" follows the source's own decisions and can flap while a mode
 *    or a stream changes. The way up is therefore debounced by 100 ms: the
 *    path is set up and stays muted, and only a source that is still there
 *    afterwards is let through. The way *down* is never debounced -- silence
 *    is never worth waiting for.
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
	const char *codec_mute;		/* its mute switch, or NULL */
	int volume;			/* 0..100 as last asked for with ctl volume */
	bool volume_set;		/* ... and not yet written (cards were missing) */
	bool mute;			/* ctl mute */

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

/* the range the driver reports for an integer control */
static int alsa_range(struct alsa_card *c, const char *name, long *min,
		      long *max)
{
	snd_ctl_elem_info_t *ei;

	snd_ctl_elem_info_alloca(&ei);
	if (!alsa_find(c, name, ei))
		return -ENOENT;
	if (snd_ctl_elem_info_get_type(ei) != SND_CTL_ELEM_TYPE_INTEGER)
		return -EINVAL;
	*min = snd_ctl_elem_info_get_min(ei);
	*max = snd_ctl_elem_info_get_max(ei);

	return 0;
}

/*
 * A raw value of a volume control as decibels, from the control's own TLV
 * -- the driver says what its steps mean, this program does not assume it
 * (the codec's DAC counts 1.16 dB steps, the DSP quarter dB). Empty when
 * the control has no readable TLV.
 */
static const char *alsa_db_text(struct alsa_card *c, const char *name, long v,
				char *buf, size_t len)
{
	snd_ctl_elem_info_t *ei;
	snd_ctl_elem_id_t *id;
	unsigned int tlv[64];
	long min, max, db;

	buf[0] = '\0';
	snd_ctl_elem_info_alloca(&ei);
	if (!alsa_find(c, name, ei) || !snd_ctl_elem_info_is_tlv_readable(ei) ||
	    snd_ctl_elem_info_get_type(ei) != SND_CTL_ELEM_TYPE_INTEGER)
		return buf;
	snd_ctl_elem_id_alloca(&id);
	snd_ctl_elem_info_get_id(ei, id);
	if (snd_ctl_elem_tlv_read(c->ctl, id, tlv, sizeof(tlv)) < 0)
		return buf;
	min = snd_ctl_elem_info_get_min(ei);
	max = snd_ctl_elem_info_get_max(ei);
	if (snd_tlv_convert_to_dB(tlv, min, max, v, &db) < 0)
		return buf;
	/* db is in 1/100 dB; one decimal is what a listener can hear */
	snprintf(buf, len, "%s%ld.%ld dB", db < 0 ? "-" : "", labs(db) / 100,
		 (labs(db) % 100) / 10);

	return buf;
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
 * The listener's volume: the codec's "DAC Playback Volume"
 *
 * 0..100 is mapped linearly onto the control's own range (0 = its minimum,
 * 100 = its maximum), and what that means in dB the control's TLV says --
 * on this codec 63 steps of 1.16 dB, so 50 is about -36 dB and 0 is
 * -73 dB, quiet but not off; off is "ctl mute". The card is the owner of
 * the value: this program reads it back for every answer instead of
 * repeating what it last wrote, so an "amixer" from elsewhere shows up in
 * "ctl status" rather than being overwritten at the next event.
 * ------------------------------------------------------------------ */

/* 0..100 -> control value, and back; -1 when there is no such control */
static long audio_volume_to_raw(struct audio *a, int n)
{
	long min, max;

	if (!a->have_dacvol || alsa_range(&a->codec, AUDIO_C_DACVOL, &min, &max))
		return -1;

	return min + ((max - min) * n + 50) / 100;
}

static int audio_volume_read(struct audio *a, char *db, size_t len)
{
	long min, max, v;

	db[0] = '\0';
	if (!a->have_dacvol || alsa_range(&a->codec, AUDIO_C_DACVOL, &min, &max) ||
	    alsa_read(&a->codec, AUDIO_C_DACVOL, &v) || max <= min)
		return -1;
	alsa_db_text(&a->codec, AUDIO_C_DACVOL, v, db, len);

	return (int)(((v - min) * 100 + (max - min) / 2) / (max - min));
}

/* write the last "ctl volume" -- now, or as soon as the codec is there */
static void audio_volume_apply(struct audio *a)
{
	long raw = audio_volume_to_raw(a, a->volume);

	if (raw < 0)
		return;
	audio_put(a, &a->codec, AUDIO_C_DACVOL, raw);
	a->volume_set = false;
}

/* "Lautstaerke 50 (-36,2 dB)" or, without the control, why not */
static const char *audio_volume_text(struct audio *a, char *buf, size_t len)
{
	char db[24];
	int n = audio_volume_read(a, db, sizeof(db));

	if (n < 0)
		snprintf(buf, len, "volume without a control (\"%s\" is missing)",
			 AUDIO_C_DACVOL);
	else if (db[0])
		snprintf(buf, len, "volume %d (%s)", n, db);
	else
		snprintf(buf, len, "volume %d", n);

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
static void audio_silence(struct audio *a)
{
	audio_put(a, &a->msp, AUDIO_C_MUTE, 1);
	audio_put(a, &a->msp, AUDIO_C_SWITCH, 0);
	audio_put_enum(a, &a->codec, AUDIO_C_SOURCE, "APB");
}

/* the path, still muted: rate first, then the route, then the switch */
static void audio_route(struct audio *a, unsigned int rate)
{
	char text[16];

	audio_put(a, &a->msp, AUDIO_C_MUTE, 1);
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
	bool quiet = a->mute || a->state != AUDIO_LOUD;
	long min, max;

	if (quiet)
		audio_put(a, &a->msp, AUDIO_C_MUTE, 1);
	if (a->codec_mute)
		audio_put(a, &a->codec, a->codec_mute, !a->mute);
	/* 0 dB is the top of the control (doku/101 section 2), the trim below it */
	if (!alsa_range(&a->msp, AUDIO_C_VOLUME, &min, &max))
		audio_put(a, &a->msp, AUDIO_C_VOLUME, max + a->trim_q);
	if (!quiet)
		audio_put(a, &a->msp, AUDIO_C_MUTE, 0);
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
			audio_silence(a);
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

		a->enabled = true;
		a->searching = false;
		a->why[0] = '\0';
		/* the listener's two controls are welcome, not required */
		a->have_dacvol = alsa_has(&a->codec, dacvol);
		a->codec_mute = NULL;
		snd_ctl_elem_info_alloca(&ei);
		for (i = 0; audio_codec_mutes[i] && !a->codec_mute; i++)
			if (alsa_find(&a->codec, audio_codec_mutes[i], ei))
				a->codec_mute = audio_codec_mutes[i];
		/* a volume or mute asked for while the cards were missing is owed */
		if (a->volume_set)
			audio_volume_apply(a);
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
		audio_silence(a);
		a->state = AUDIO_STILL;
		/*
		 * A "ctl mute" is this program's, not the box's: it does not
		 * outlive the process on the codec, or the next aplay would
		 * be silent for a reason nobody can see any more.
		 */
		if (a->mute && a->codec_mute)
			audio_put(a, &a->codec, a->codec_mute, 1);
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
 * or "fehler", so the client's exit code is decided by the first word.
 * ------------------------------------------------------------------ */

#define GAMMA_FILE	"/usr/local/share/h713-tv/gamma-standard.bin"
#define CTL_SOCKET	"/run/h713-tv/ctl"
#define CTL_MAXLINE	512

enum policy { POLICY_AUTO, POLICY_OFF };

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
 *       start = manuell         console until "ctl on" or "ctl auto"
 *       start = zuletzt         the mode last set with ctl; auto when none is known
 *       zustand = PFAD | none   where the last mode is kept; none = do not keep
 *       preset = NAME|zuletzt   which picture preset to come up with (11.09.)
 *       daten = VERZ | none     the extracted vendor data; none = do not use it
 *       rechner = PFAD | none   h713-pq; none = do not compute anything
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
#define WERTE_NAME	"werte"

/* h713-pq and what it is asked about; see "The picture values" below */
#define PQ_BIN		"/usr/local/bin/h713-pq"
#define PQ_DATEN	"/etc/h713/tvconfig"
#define PQ_EINGANG	"HDMI1"
#define PQ_LUT		"/run/h713-tv/gamma-laufzeit.bin"

enum start_mode { START_AUTO, START_MANUELL, START_ZULETZT };

struct conf {
	const char *path;	/* -C; CONF_FILE by default */
	bool present;		/* the file was there and has been read */
	enum start_mode start;
	bool keep;		/* zustand != none */
	char state_path[200];
	char werte_path[208];	/* <dirname(state_path)>/werte, "" when not kept */
	char preset[32];	/* preset = NAME | zuletzt; "" = not said here */
	char daten[160];	/* daten = VERZ; "none" = do not use vendor data */
	char rechner[160];	/* rechner = PFAD; "none" = do not compute */
	char eingang[24];	/* --eingang; the input h713-pq is asked about */
	char lut[160];		/* where h713-pq is told to write the LUT */
};

/* <dirname(state_path)>/werte -- the two files live together or not at all */
static void conf_werte_pfad(struct conf *c)
{
	char dir[200], *slash;

	c->werte_path[0] = '\0';
	if (!c->keep)
		return;
	snprintf(dir, sizeof(dir), "%s", c->state_path);
	slash = strrchr(dir, '/');
	if (!slash || slash == dir)
		return;
	*slash = '\0';
	snprintf(c->werte_path, sizeof(c->werte_path), "%s/%s", dir, WERTE_NAME);
}

static const char *start_mode_text(enum start_mode m)
{
	return m == START_MANUELL ? "manual" : m == START_ZULETZT ? "last" : "auto";
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
	snprintf(c->daten, sizeof(c->daten), "%s", PQ_DATEN);
	snprintf(c->rechner, sizeof(c->rechner), "%s", PQ_BIN);
	snprintf(c->eingang, sizeof(c->eingang), "%s", PQ_EINGANG);
	snprintf(c->lut, sizeof(c->lut), "%s", PQ_LUT);

	f = fopen(c->path, "r");
	if (!f) {
		/* a missing file is the documented default; anything else is worth a line */
		if (errno != ENOENT)
			warn("%s: %s -- the defaults apply (start = auto)", c->path,
			     strerror(errno));
		conf_werte_pfad(c);
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
				c->start = START_MANUELL;
			else if (!strcasecmp(val, "last") || !strcasecmp(val, "zuletzt"))
				c->start = START_ZULETZT;
			else
				warn("%s:%u: start = \"%s\" unknown (auto manual last) -- auto",
				     c->path, n, val);
		} else if (!strcasecmp(key, "zustand")) {
			if (!strcasecmp(val, "none") || !strcasecmp(val, "keiner") ||
			    !strcasecmp(val, "nein"))
				c->keep = false;
			else if (*val != '/' || strlen(val) >= sizeof(c->state_path) - 8)
				warn("%s:%u: zustand = \"%s\" is not an absolute path (or too long) -- default %s",
				     c->path, n, val, STATE_FILE);
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
		} else if (!strcasecmp(key, "daten")) {
			if (strlen(val) >= sizeof(c->daten))
				warn("%s:%u: daten = \"%s\" is too long -- default %s",
				     c->path, n, val, PQ_DATEN);
			else
				snprintf(c->daten, sizeof(c->daten), "%s", val);
		} else if (!strcasecmp(key, "rechner")) {
			if (strlen(val) >= sizeof(c->rechner))
				warn("%s:%u: rechner = \"%s\" is too long -- default %s",
				     c->path, n, val, PQ_BIN);
			else
				snprintf(c->rechner, sizeof(c->rechner), "%s", val);
		} else {
			warn("%s:%u: unknown key \"%s\" -- ignored (start, zustand, preset, daten, rechner)",
			     c->path, n, key);
		}
	}
	fclose(f);
	conf_werte_pfad(c);
}

struct control {
	int lfd;
	int lock_fd;		/* flock on <dir>/lock: one instance per socket */
	const char *path;
	enum policy policy;
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
	case START_MANUELL:
		console = true;
		why = "start = manual";
		break;
	case START_ZULETZT:
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
	     c->state_path ? "the mode is saved in " : "the mode is not saved (zustand = none)",
	     c->state_path ? c->state_path : "");

	return console ? POLICY_OFF : POLICY_AUTO;
}

struct reply {
	char buf[4096];
	size_t len;
	bool failed;
};

__attribute__((format(printf, 2, 3)))
static void reply_add(struct reply *r, const char *fmt, ...)
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
static void reply_fail(struct reply *r, const char *fmt, ...)
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
static void cmd_status_audio(struct reply *r, struct audio *a)
{
	char text[64], trim[40], sw[32], vol[32], mu[32], src[32], rate[32];
	char dac[32], cmu[32];

	if (a->policy == AUDIO_NONE) {
		reply_add(r, "audio           not touched (-a none)\n");
		return;
	}
	if (!a->enabled) {
		reply_add(r, "audio           off -- %s\n", a->why);
		return;
	}
	if (a->state == AUDIO_LOUD && a->applied_rate)
		reply_add(r, "audio           %s (%s), %u Hz, %s, %s%s\n",
			  audio_state_text(a), audio_policy_text(a),
			  a->applied_rate, audio_volume_text(a, text, sizeof(text)),
			  audio_trim_text(a, trim, sizeof(trim)),
			  a->mute ? ", ctl mute on" : "");
	else
		reply_add(r, "audio           %s (%s)%s, %s, %s%s\n",
			  audio_state_text(a), audio_policy_text(a),
			  a->state == AUDIO_STILL ? "" : ", rate unknown",
			  audio_volume_text(a, text, sizeof(text)),
			  audio_trim_text(a, trim, sizeof(trim)),
			  a->mute ? ", ctl mute on" : "");
	alsa_read_text(&a->msp, AUDIO_C_SWITCH, sw, sizeof(sw));
	alsa_read_text(&a->msp, AUDIO_C_VOLUME, vol, sizeof(vol));
	alsa_read_text(&a->msp, AUDIO_C_MUTE, mu, sizeof(mu));
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
	reply_add(r, "audio cards     %s (card %d): Switch %s, Volume %s, Mute %s | %s (card %d): Source %s, Rate %s, DAC Volume %s, switch %s%s%s\n",
		  a->msp.id, a->msp.index, sw, vol, mu, a->codec.id,
		  a->codec.index, src, rate, dac,
		  a->codec_mute ? a->codec_mute : "", a->codec_mute ? " " : "",
		  cmu);
	if (!a->have_source)
		reply_add(r, "audio source    no controls \"%s\"/\"%s\"/\"%s\" on the capture node (kernel 0136)\n",
			  AUDIO_V_PRESENT, AUDIO_V_RATE, AUDIO_V_COMPRESSED);
	else
		reply_add(r, "audio source    present=%d rate=%u compressed=%d (%s)\n",
			  a->present, a->rate, a->compressed,
			  a->events ? "events" : "polling");
	if (card_sysfs(&a->msp, "state", sw, sizeof(sw)))
		reply_add(r, "audio msp       state=%s\n", sw);
	if (card_sysfs(&a->msp, "levels", vol, sizeof(vol)))
		reply_add(r, "audio level     %s\n", vol);
}

/*
 * The three layers of the picture values, as they stand right now. Defined
 * down with the presets, because that is where the state it reports lives;
 * declared here so the status keeps reading top to bottom.
 */
static void cmd_status_bildwerte(struct reply *r);

static void cmd_status(struct reply *r, struct control *c, struct capture *cap,
		       struct display *d, struct audio *a)
{
	static const char *const kern[] = {
		"incap:", "capture:", "farbwandler:", "signal:", "timings:", NULL,
	};
	static const char *const comm[] = { "rx_calls", "eingehend", NULL };
	/* the last measurement evaluate() made -- a status is a report, not a probe (S12 R7) */
	const struct v4l2_dv_timings *t = &cap->last_t;
	int sig = cap->last_sig;

	reply_add(r, "ok status\n");
	reply_add(r, "mode            %s\n", c->policy == POLICY_OFF ? "off (console forced)"
								  : "automatic");
	if (c->conf)
		reply_add(r, "config          %s%s: start=%s; saved=%s%s%s\n", c->conf->path,
			  c->conf->present ? "" : " (missing)", start_mode_text(c->conf->start),
			  c->state_known[0] ? c->state_known : "-",
			  c->state_path ? " in " : " (zustand = none)",
			  c->state_path ? c->state_path : "");
	if (sig == 1)
		reply_add(r, "signal          %ux%u%s, %llu Hz (last measured)\n", t->bt.width,
			  t->bt.height, t->bt.interlaced ? "i" : "p",
			  (unsigned long long)t->bt.pixelclock);
	else if (sig == 2)
		reply_add(r, "signal          change in flight (the geometry has not locked yet)\n");
	else
		reply_add(r, "signal          %s\n", sig == 0 ? "no signal" : "not readable");
	reply_add(r, "picture         %s%s\n", d->on ? "plane on" : "console",
		  d->master ? ", DRM master held" : "");
	if (d->src_w)
		reply_add(r, "buffer          %ux%u NV16, line pitch %u on panel %ux%u\n", d->src_w, d->src_h, d->src_pitch,
			  d->width, d->height);
	if (d->has_aspect)
		reply_add(r, "format          %s (aspect %llu)\n",
			  prop_enum_name(&d->plane_props, "aspect", d->aspect),
			  (unsigned long long)d->aspect);
	cmd_status_bildwerte(r);
	cmd_status_audio(r, a);
	reply_file_lines(r, "/sys/kernel/debug/" V4L2_DRIVER "/status", kern, "kernel          ");
	reply_file_lines(r, "/sys/kernel/debug/cpu_comm/watch", comm, "cpu_comm        ");
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
}

static void cmd_get(struct reply *r, struct capture *cap, const char *name)
{
	struct v4l2_query_ext_ctrl q;
	char menu[64];
	int64_t val;
	int ret;

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
	ret = ctrl_set(cap->fd, &q, val);
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

/* the kernel's enum names of "aspect", space-separated, for messages */
static void aspect_names(const struct display *d, char *buf, size_t n)
{
	const drmModePropertyRes *p = prop_info(&d->plane_props, "aspect");
	size_t l = 0;
	int i;

	buf[0] = '\0';
	for (i = 0; p && i < p->count_enums && l + 1 < n; i++)
		l += (size_t)snprintf(buf + l, n - l, "%s%s", i ? " " : "",
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
#define EDID_DATEI	"/lib/firmware/hy310-edid.bin"

static bool edid_aus_datei(const char *pfad, uint8_t *out, char *why, size_t n)
{
	int fd = open(pfad, O_RDONLY | O_CLOEXEC);
	ssize_t got;

	if (fd < 0) {
		snprintf(why, n, "%s: %s", pfad, strerror(errno));
		return false;
	}
	got = read(fd, out, EDID_BYTES);
	close(fd);
	if (got != (ssize_t)EDID_BYTES) {
		snprintf(why, n, "%s: read %zd of %u bytes", pfad, got,
			 (unsigned int)EDID_BYTES);
		return false;
	}

	return edid_plausible(out, why, n);
}

static bool cmd_replug(struct reply *r, struct capture *cap, struct display *d,
		       struct retry *rt)
{
	static uint8_t last_good[EDID_BYTES];
	static bool have_last;
	struct timespec low = { .tv_sec = 0, .tv_nsec = REPLUG_LOW_MS * 1000000L };
	uint8_t buf[EDID_BYTES];
	struct v4l2_edid e;
	char why[160];
	const char *woher = "";
	bool copy = false;

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
			woher = " (copy of the last read)";
		} else if (edid_aus_datei(EDID_DATEI, buf, why2, sizeof(why2))) {
			warn("replug          %s -- %s goes back", why, EDID_DATEI);
			memcpy(last_good, buf, sizeof(last_good));
			have_last = true;
			woher = " (from " EDID_DATEI ")";
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
	if (ioctl(cap->fd, VIDIOC_S_EDID, &e)) {
		int err = errno;

		warn("replug          S_EDID(%u blocks): %s -- HPD is LOW, the source sees no device",
		     EDID_BLOCKS, strerror(err));
		reply_fail(r, "S_EDID with the EDID: %s -- HPD is low! run \"replug\" once more (it takes the copy), or rebind the driver",
			   strerror(err));
		return true;
	}
	info("replug          EDID loaded again%s, HPD high -- the source renegotiates",
	     woher);
	reply_add(r, "ok replug -- HPD %u ms low, EDID loaded again%s, the source renegotiates\n",
		  REPLUG_LOW_MS, woher);

	return true;
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
 *   h713-pq --daten VERZ show EINGANG PRESET --json --lut /run/.../gamma.bin
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
 *   * it takes longer than PQ_FRIST_MS              -> killed, record dropped
 *   * "rechner = none" or "daten = none" in tv.conf -> not started at all
 *
 * The record carries *all* presets the data has for this input, not only the
 * one asked for. That is why "ctl preset energy_saving" works on a device
 * with the extraction and says "unknown" on one without it, without ever
 * starting a second Python process while the picture is running.
 * ------------------------------------------------------------------ */

#define PQ_FRIST_MS	2000	/* plan 113 A.5: h713-pq must not hold the start */
#define PQ_SATZ_VERSION	1	/* what h713-pq calls "version" in its record */
#define PQ_ROH_MAX	16384	/* the record is ~3,5 kB for eight presets */
#define PQ_PRESETS_MAX	16
#define PQ_WARTE_MS	5	/* poll interval while reaping the child */

/* the presets that came from the device's own data; empty without them */
static struct preset pq_presets[PQ_PRESETS_MAX];
static char pq_namen[PQ_PRESETS_MAX][32];
static double pq_gamma[PQ_PRESETS_MAX];
static unsigned int pq_presets_n;

struct pq {
	pid_t pid;
	int fd;			/* read end of the pipe, -1: nothing running */
	struct timespec t0;
	bool ok;		/* a record was read and understood */
	unsigned int ms;	/* how long the call took */
	char why[224];		/* why not, in the words that go in the journal */
	/* out of the record */
	char daten[160];
	char preset[32];
	char lut[184];
	long lut_bytes;
	double gamma;
	char roh[PQ_ROH_MAX];
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
static const char *js_string_ende(const char *b, const char *e)
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
static const char *js_wert_ende(const char *b, const char *e)
{
	int tiefe = 0;

	while (b < e) {
		char c = *b;

		if (c == '"') {
			b = js_string_ende(b, e);
			if (!tiefe)
				return b;
			continue;
		}
		if (c == '{' || c == '[') {
			tiefe++;
		} else if (c == '}' || c == ']') {
			if (!tiefe)
				return b;	/* the parent's closing bracket */
			if (!--tiefe)
				return b + 1;
		} else if (!tiefe && c == ',') {
			return b;
		}
		b++;
	}

	return e;
}

static const char *js_leer(const char *b, const char *e)
{
	while (b < e && (*b == ' ' || *b == '\t' || *b == '\n' || *b == '\r' ||
			 *b == ','))
		b++;

	return b;
}

/* [b,e) is the inside of an object; returns the start of key's value */
static const char *js_feld(const char *b, const char *e, const char *key)
{
	size_t kl = strlen(key);

	while (b < e) {
		const char *ks, *ke;

		b = js_leer(b, e);
		if (b >= e || *b != '"')
			return NULL;
		ks = b + 1;
		b = js_string_ende(b, e);
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
		b = js_wert_ende(b, e);
	}

	return NULL;
}

static bool js_text(const char *b, const char *e, const char *key, char *out,
		    size_t n)
{
	const char *v = js_feld(b, e, key), *ende;
	size_t i = 0;

	if (!v || *v != '"')
		return false;
	ende = js_string_ende(v, e);
	if (ende > v)
		ende--;				/* the closing quote */
	for (v++; v < ende && i + 1 < n; v++) {
		if (*v == '\\' && v + 1 < ende)
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
static bool js_zahl(const char *b, const char *e, const char *key, long *out)
{
	const char *v = js_feld(b, e, key);
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

static bool js_gleitkomma(const char *b, const char *e, const char *key,
			  double *out)
{
	const char *v = js_feld(b, e, key);
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
static bool js_gebilde(const char *b, const char *e, const char *key,
		       const char **ib, const char **ie)
{
	const char *v = js_feld(b, e, key), *ende;

	if (!v || (*v != '{' && *v != '['))
		return false;
	ende = js_wert_ende(v, e);
	*ib = v + 1;
	*ie = ende > v + 1 ? ende - 1 : v + 1;

	return true;
}

/* the next {...} in [*b,e); hands out its inside and steps *b past it */
static bool js_element(const char **b, const char *e, const char **ib,
		       const char **ie)
{
	const char *p = *b, *ende;

	while (p < e && *p != '{')
		p++;
	if (p >= e)
		return false;
	ende = js_wert_ende(p, e);
	*ib = p + 1;
	*ie = ende > p + 1 ? ende - 1 : p + 1;
	*b = ende;

	return true;
}

/* ---- running h713-pq ---- */

static int pq_zeit_uebrig(const struct pq *p)
{
	struct timespec now;
	long used;

	clock_gettime(CLOCK_MONOTONIC, &now);
	used = (now.tv_sec - p->t0.tv_sec) * 1000 +
	       (now.tv_nsec - p->t0.tv_nsec) / 1000000;

	return used >= PQ_FRIST_MS ? 0 : (int)(PQ_FRIST_MS - used);
}

static unsigned int pq_verbraucht(const struct pq *p)
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

	if (!strcasecmp(c->rechner, "none")) {
		snprintf(p->why, sizeof(p->why), "rechner = none");
		return;
	}
	if (!strcasecmp(c->daten, "none")) {
		snprintf(p->why, sizeof(p->why), "daten = none");
		return;
	}
	if (access(c->rechner, X_OK)) {
		snprintf(p->why, sizeof(p->why), "%s: %s", c->rechner,
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
		execl(c->rechner, "h713-pq", "--daten", c->daten, "show",
		      c->eingang, preset, "--json", "--lut", c->lut,
		      (char *)NULL);
		_exit(127);
	}
	close(fds[1]);
	p->fd = fds[0];
	snprintf(p->lut, sizeof(p->lut), "%s", c->lut);
}

/* reap the child inside what is left of the budget; SIGKILL when it is up */
static bool pq_ernten(struct pq *p, int *status)
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
		if (pq_zeit_uebrig(p) <= 0) {
			struct timespec ts = { 0, 200 * 1000 * 1000 };

			kill(p->pid, SIGKILL);
			/* after SIGKILL the wait is bounded by the kernel */
			while (waitpid(p->pid, status, WNOHANG) != p->pid &&
			       ts.tv_nsec > 0) {
				struct timespec kurz = { 0, 1000 * 1000 };

				nanosleep(&kurz, NULL);
				ts.tv_nsec -= 1000 * 1000;
			}
			snprintf(p->why, sizeof(p->why),
				 "longer than %d ms -- aborted", PQ_FRIST_MS);
			p->pid = -1;
			return false;
		}
		{
			struct timespec kurz = { 0, PQ_WARTE_MS * 1000 * 1000 };

			nanosleep(&kurz, NULL);
		}
	}
	p->pid = -1;

	return true;
}

/* the record -> pq_presets[]; false means "use the compiled table" */
static bool pq_deuten(struct pq *p)
{
	const char *b = p->roh, *e = p->roh + p->len, *ab, *ae, *lb, *le;
	long v;

	while (b < e && *b != '{')
		b++;
	if (b >= e) {
		snprintf(p->why, sizeof(p->why), "no JSON output (%zu bytes)",
			 p->len);
		return false;
	}
	le = js_wert_ende(b, e);
	b++;
	e = le > b ? le - 1 : b;

	if (!js_zahl(b, e, "version", &v) || v != PQ_SATZ_VERSION) {
		snprintf(p->why, sizeof(p->why),
			 "record version %ld, this program knows %d", v,
			 PQ_SATZ_VERSION);
		return false;
	}
	js_text(b, e, "daten", p->daten, sizeof(p->daten));
	js_text(b, e, "preset", p->preset, sizeof(p->preset));
	if (js_zahl(b, e, "lut_bytes", &v))
		p->lut_bytes = v;
	js_gleitkomma(b, e, "gamma_exponent", &p->gamma);

	if (!js_gebilde(b, e, "presets", &ab, &ae)) {
		snprintf(p->why, sizeof(p->why), "no field \"presets\" in the record");
		return false;
	}
	pq_presets_n = 0;
	while (pq_presets_n < PQ_PRESETS_MAX && js_element(&ab, ae, &lb, &le)) {
		struct preset *t = &pq_presets[pq_presets_n];
		const char *rb, *re;
		unsigned int i;
		long mode;

		if (!js_text(lb, le, "name", pq_namen[pq_presets_n],
			     sizeof(pq_namen[0])) ||
		    !js_zahl(lb, le, "modus", &mode) ||
		    !js_gebilde(lb, le, "regler", &rb, &re))
			continue;
		for (i = 0; i < 9; i++) {
			if (!js_zahl(rb, re, preset_pq_key[i], &v))
				break;
			t->value[i] = (int)v;
		}
		if (i < 9)
			continue;		/* incomplete -- not guessed */
		t->name = pq_namen[pq_presets_n];
		t->mode = (int)mode;
		pq_gamma[pq_presets_n] = 0.0;
		js_gleitkomma(lb, le, "gamma_exponent", &pq_gamma[pq_presets_n]);
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
		int rest = pq_zeit_uebrig(p);
		ssize_t k;

		if (rest <= 0 || poll(&pfd, 1, rest) <= 0)
			break;
		k = read(p->fd, p->roh + p->len, sizeof(p->roh) - 1 - p->len);
		if (k <= 0)
			break;
		p->len += (size_t)k;
		if (p->len >= sizeof(p->roh) - 1)
			break;
	}
	p->roh[p->len] = '\0';
	close(p->fd);
	p->fd = -1;

	if (!pq_ernten(p, &status)) {
		p->ms = pq_verbraucht(p);
		return;
	}
	p->ms = pq_verbraucht(p);
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
	p->ok = pq_deuten(p);
}

/* which presets can be offered right now, for a message */
static void preset_namen(char *buf, size_t n)
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

/*
 * The device's own data first, the compiled table second. Both are searched,
 * not only the first: if the extraction is missing exactly one preset the
 * user asks for, the table can still answer -- and the answer says where it
 * came from, because preset_ist_aus_daten() below is what the status line
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

static bool preset_ist_aus_daten(const struct preset *p)
{
	return p >= &pq_presets[0] && p < &pq_presets[PQ_PRESETS_MAX];
}

/* the gamma exponent that belongs to a preset, 0 when it is not known */
static double preset_gamma(const struct preset *p)
{
	if (!preset_ist_aus_daten(p))
		return 0.0;

	return pq_gamma[p - &pq_presets[0]];
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
	ret = ctrl_set(cap->fd, &q, p->mode);
	if (ret) {
		snprintf(msg, n, "picture_mode = %d: %s", p->mode, strerror(-ret));
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
 * alone. With "preset = zuletzt" in tv.conf -- the setting this was built for
 * -- the two always agree.
 * ------------------------------------------------------------------ */

struct werte {
	const char *path;	/* NULL: nothing is kept */
	bool present;
	char preset[32];
	int value[9];
	bool have[9];
	unsigned int line[9];
	char aspect[24];
	unsigned int aspect_line;
	bool complained;
};

static struct werte werte;

/* which preset is in force right now, and where it came from */
static char preset_aktuell[32] = "";
static bool preset_aktuell_aus_daten;

static void werte_read(struct werte *w)
{
	char line[256];
	unsigned int n = 0;
	FILE *f;

	w->present = false;
	w->preset[0] = '\0';
	w->aspect[0] = '\0';
	memset(w->have, 0, sizeof(w->have));
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
static int werte_apply(struct capture *cap, const struct werte *w,
		       const char *preset_name, char *msg, size_t n)
{
	struct v4l2_query_ext_ctrl q;
	unsigned int i, gesetzt = 0;
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
		gesetzt++;
	}

	return (int)gesetzt;
}

/*
 * Write the current state. What is written is read back from the driver, not
 * remembered along the way: the driver is the one place that knows what the
 * nine controls really hold, and a bookkeeping copy could only ever be a
 * second version of the truth. That also settles the rule of plan 113 A.4
 * that "ctl preset" discards the kept deviations -- after a preset the
 * driver holds the preset's values, so that is what a later save writes.
 */
static bool werte_write(struct werte *w, struct capture *cap,
			const struct display *d, char *msg, size_t n)
{
	struct v4l2_query_ext_ctrl q;
	char tmp[240], dir[240], *slash;
	unsigned int i;
	size_t l = 0;
	int fd;
	FILE *f;

	if (!w->path) {
		snprintf(msg, n, "nothing is saved (zustand = none in tv.conf)");
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
	if (preset_aktuell[0])
		fprintf(f, "preset      = %s\n", preset_aktuell);
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
	werte_read(w);		/* what is on disk is now the truth again */

	return true;
}

static bool werte_loeschen(struct werte *w, char *msg, size_t n)
{
	if (!w->path) {
		snprintf(msg, n, "nothing is saved (zustand = none in tv.conf)");
		return false;
	}
	if (unlink(w->path) && errno != ENOENT) {
		snprintf(msg, n, "%s: %s", w->path, strerror(errno));
		return false;
	}
	w->present = false;
	memset(w->have, 0, sizeof(w->have));
	w->preset[0] = '\0';
	w->aspect[0] = '\0';

	return true;
}

static void cmd_preset(struct reply *r, struct capture *cap, const char *name)
{
	const struct preset *p = preset_find(name);
	char msg[256], namen[192];
	double g;
	int ret;

	preset_namen(namen, sizeof(namen));
	if (!p) {
		reply_fail(r, "preset needs a name: %s", namen);
		return;
	}
	ret = preset_apply(cap, p, msg, sizeof(msg));
	if (ret < 0) {
		reply_fail(r, "%s", msg);
		return;
	}
	snprintf(preset_aktuell, sizeof(preset_aktuell), "%s", p->name);
	preset_aktuell_aus_daten = preset_ist_aus_daten(p);
	reply_add(r, "ok preset %s%s (%s)\n", msg,
		  ret ? " (not everything was set)" : "",
		  preset_aktuell_aus_daten ? "from the device data"
					   : "the compiled-in table");
	/*
	 * The gamma curve is loaded once, at start, for the preset started
	 * with; changing it at run time would mean another h713-pq call and
	 * a CRTC commit in the middle of a picture. In this device's data all
	 * eight presets use gamma index 3 (2.2), so the case does not arise
	 * -- but silence would be the wrong answer if it ever did.
	 */
	g = preset_gamma(p);
	if (g > 0.0 && pq.gamma > 0.0 && g != pq.gamma)
		reply_add(r, "   note: %s wants gamma %.2f, loaded is %.2f -- "
			  "restart the service for that\n", p->name, g, pq.gamma);
	reply_add(r, "   the saved deviations are dropped; \"ctl save\" "
		  "writes this state down\n");
}

/*
 * save [--aus]: write the nine sliders, the preset they belong to and the
 * aspect, or throw the file away again. Deliberately explicit -- see the
 * comment above struct werte.
 */
static void cmd_save(struct reply *r, struct capture *cap,
		     const struct display *d, const char *arg)
{
	char msg[512];

	if (arg && (!strcmp(arg, "--aus") || !strcmp(arg, "aus") ||
		    !strcmp(arg, "off"))) {
		if (werte_loeschen(&werte, msg, sizeof(msg)))
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
	if (werte_write(&werte, cap, d, msg, sizeof(msg)))
		reply_add(r, "ok saved in %s: preset=%s %s\n", werte.path,
			  preset_aktuell[0] ? preset_aktuell : "-", msg);
	else
		reply_fail(r, "%s", msg);
}

/* the three layers, each with where it came from (declared above cmd_status) */
static void cmd_status_bildwerte(struct reply *r)
{
	unsigned int i;

	if (pq.ok)
		reply_add(r, "picture values  %u presets from %s (h713-pq, %u ms), "
			  "gamma %.2f, LUT %ld bytes\n", pq_presets_n,
			  pq.daten[0] ? pq.daten : "the device data", pq.ms,
			  pq.gamma, pq.lut_bytes);
	else
		reply_add(r, "picture values  the compiled-in table -- %s\n",
			  pq.why[0] ? pq.why : "h713-pq was not asked");
	reply_add(r, "preset          %s (%s)\n",
		  preset_aktuell[0] ? preset_aktuell : "-",
		  preset_aktuell_aus_daten ? "from the device data"
					   : "the compiled-in table");
	if (!werte.path)
		reply_add(r, "saved           nothing (zustand = none in tv.conf)\n");
	else if (!werte.present)
		reply_add(r, "saved           nothing in %s -- \"ctl save\" writes it\n",
			  werte.path);
	else {
		char liste[256];
		size_t l = 0;

		liste[0] = '\0';
		for (i = 0; i < 9; i++)
			if (werte.have[i] && l + 1 < sizeof(liste))
				l += (size_t)snprintf(liste + l, sizeof(liste) - l,
						      "%s%s=%d", l ? " " : "",
						      preset_ctrl[i], werte.value[i]);
		reply_add(r, "saved           %s: preset=%s %s%s%s\n", werte.path,
			  werte.preset[0] ? werte.preset : "-", liste,
			  werte.aspect[0] ? " aspect=" : "",
			  werte.aspect[0] ? werte.aspect : "");
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
 * volume [0..100]: the codec's "DAC Playback Volume", 0 = its minimum,
 * 100 = its maximum (see audio_volume_to_raw()). The answer is read back
 * from the card, not echoed. Without an argument: show.
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
			reply_fail(r, "volume needs 0..100 (0 = the quietest step, 100 = 0 dB), not \"%s\"",
				   text);
			return;
		}
		a->volume = (int)n;
		a->volume_set = true;
		if (!a->enabled) {
			reply_add(r, "ok volume %d -- saved, %s\n", a->volume,
				  a->why);
			return;
		}
		if (!a->have_dacvol) {
			reply_fail(r, "the card \"%s\" has no control \"%s\" -- the volume stays where it is",
				   a->codec.name, AUDIO_C_DACVOL);
			return;
		}
		audio_volume_apply(a);
		if (a->write_failed) {
			reply_fail(r, "\"%s\" could not be written (see the journal)",
				   AUDIO_C_DACVOL);
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
	char namen[192];

	preset_namen(namen, sizeof(namen));
	reply_add(r, "ok commands\n"
		  "  status (st)           state of the program, the kernel and cpu_comm\n"
		  "  auto (on)             the picture follows the signal (the default without tv.conf)\n"
		  "  off                   force the console, until auto\n"
		  "                        auto/off are saved (zustand in /etc/h713/tv.conf);\n"
		  "                        what applies at the start is start = auto|manual|last there\n"
		  "  console               unblank the console, show the cursor\n"
		  "  list                  all picture controls with value and range\n"
		  "  get CONTROL           read one control\n"
		  "  set CONTROL VALUE     set one control (a number or the menu text)\n"
		  "                        controls: brightness contrast saturation hue sharpness\n"
		  "                        tnr snr dci black range(auto|limited|full)\n"
		  "                        mode(0..13 or a name: standard cinema vivid game computer hdr ...)\n"
		  "  preset NAME           vendor preset: picture mode + nine controls.\n"
		  "                        Possible: %s\n"
		  "                        (from /etc/h713/tvconfig, else compiled in);\n"
		  "                        drops the saved deviations in memory\n"
		  "  save [off]            save the current state of the nine controls, the preset\n"
		  "                        and aspect (%s); \"off\" deletes the file again.\n"
		  "                        Only here is anything written, not on every \"set\"\n"
		  "  aspect [NAME]         how the source is fitted (auto proportional full 16:9 4:3 zoom);\n"
		  "                        without NAME: show it. A change rebuilds the picture (~0.5 s)\n"
		  "  audio [on|off|auto]   audio: forced on, forced silent, or following the picture\n"
		  "                        (default auto); without an argument: show it\n"
		  "  volume [0..100]       volume of the codec (DAC Playback Volume, acts on HDMI and\n"
		  "                        on the device's own tones): 0 = the quietest step, 100 = 0 dB; without a number: show it\n"
		  "  mute [on|off]         mute: the DSP mute (HDMI) and the codec's switch\n"
		  "  resync                select the source again (S_INPUT 0 = SetSource HDMI-1)\n"
		  "  replug                play an unplug and a replug to the source: HPD 300 ms low\n"
		  "                        (S_EDID blocks=0), load the EDID again, HPD high (~1 s, blocks)\n"
		  "  rpc NAME [ARG...]     an RPC to the firmware, e.g. rpc THal_Vp_DisableBlackScreen\n"
		  "                        (raw; blocks the program for the duration of the call)\n"
		  "  help                  this list\n"
		  "The answer starts with ok or error; socket %s (root, 0660)\n",
		  namen, werte.path ? werte.path : "switched off", c->path);
}

/* true if the caller has to run evaluate() afterwards */
static bool control_dispatch(struct control *c, struct capture *cap,
			     struct display *d, struct retry *rt,
			     struct audio *a, char *line, struct reply *r)
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
		cmd_status(r, c, cap, d, a);
	} else if (!strcmp(cmd, "auto") || !strcmp(cmd, "on")) {
		c->policy = POLICY_AUTO;
		state_write(c, c->policy);
		reply_add(r, "ok automatic -- the picture follows the signal\n");
		return true;
	} else if (!strcmp(cmd, "off")) {
		c->policy = POLICY_OFF;
		state_write(c, c->policy);
		retry_stop(rt);
		if (display_hide(d))
			reply_add(r, "ok console -- until \"auto\"\n");
		else
			reply_fail(r, "the plane cannot be switched off");
	} else if (!strcmp(cmd, "console")) {
		console_restore();
		reply_add(r, "ok console unblanked, cursor on\n");
	} else if (!strcmp(cmd, "list")) {
		cmd_list(r, cap);
	} else if (!strcmp(cmd, "get") && a1) {
		cmd_get(r, cap, a1);
	} else if (!strcmp(cmd, "set") && a1 && a2) {
		cmd_set(r, cap, a1, a2);
	} else if (!strcmp(cmd, "preset")) {
		cmd_preset(r, cap, a1);
	} else if (!strcmp(cmd, "save")) {
		cmd_save(r, cap, d, a1);
	} else if (!strcmp(cmd, "aspect")) {
		return cmd_aspect(r, d, a1);
	} else if (!strcmp(cmd, "audio")) {
		/*
		 * The sound is decided here and not by the caller's
		 * evaluate(): a policy change is no reason to ask the capture
		 * device for its timings again (20 ms, S12 R7).
		 */
		if (cmd_audio(r, a, a1))
			audio_evaluate(a, cap, d->on);
	} else if (!strcmp(cmd, "volume") || !strcmp(cmd, "vol")) {
		cmd_volume(r, a, a1);
	} else if (!strcmp(cmd, "mute")) {
		cmd_mute(r, a, a1);
	} else if (!strcmp(cmd, "resync")) {
		capture_select_input(cap);
		reply_add(r, "ok source selected again\n");
		return true;
	} else if (!strcmp(cmd, "replug")) {
		return cmd_replug(r, cap, d, rt);
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
		reevaluate = control_dispatch(c, cap, d, rt, a, line, &r);

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
	close(fd);

	return reevaluate;
}

/* ------------------------------------------------------------------ *
 * Client mode: h713-tv ctl BEFEHL [ARG...]
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
	int sig;

	/* "off" over the control socket: the console stays, whatever the signal does */
	if (ctl.policy == POLICY_OFF) {
		retry_stop(rt);
		display_hide(d);
		return;
	}

	sig = capture_signal(cap, &t);
	cap->last_sig = sig;
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
		 * With the console up there is nothing to keep, and no event may
		 * follow -- so keep asking, slowly, until the driver decides.
		 */
		if (rt->n == RETRY_MAX) {
			warn("the geometry has not locked after %u retries -- %s",
			     RETRY_MAX, d->on ? "the picture stays until the next event comes"
					      : "the console stays, asking again every 500 ms");
			rt->n++;
		}
		if (!d->on)
			retry_arm(rt, RETRY_SLOW_MS);
		return;
	}
	/* decided: whatever is still scheduled would only measure again (S12 R4) */
	retry_stop(rt);

	if (sig <= 0) {
		if (sig == 0)
			info("signal          no signal (the flip pointers stand still)");
		display_hide(d);
		return;
	}

	info("signal          %ux%u%s, %llu Hz pixel clock", t.bt.width, t.bt.height,
	     t.bt.interlaced ? "i" : "p",
	     (unsigned long long)t.bt.pixelclock);

	if (t.bt.width > d->width || t.bt.height > d->height ||
	    (t.bt.height & 1)) {
		warn("the plane does not take the source geometry %ux%u (larger than the panel %ux%u, or an odd height) -- the console stays",
		     t.bt.width, t.bt.height, d->width, d->height);
		display_hide(d);
		return;
	}
	/*
	 * Sub-panel sources are scaled to the panel by the firmware itself: the
	 * rebuilt framebuffer below republishes the VidDec record with the new
	 * geometry (kernel 0117/0120), the firmware recomputes its window chain
	 * and programs the scaler (doku/96 sections 3-6), and the capture
	 * driver puts the input colour converter back and re-enables the
	 * capture (0121-0123). Until 08.09.2026 a lock here sent every
	 * non-panel geometry to the console, with H713_TV_SKALIERTEST as the
	 * way around it for testing; both are gone since 720p and 1080p run
	 * clean over any number of changes (doku/nachtlog/S11).
	 */
	if (t.bt.width != d->src_w || t.bt.height != d->src_h) {
		/* a refused disable is a plane still showing the old buffer -- say so and stop */
		if (d->on && !display_hide(d))
			return;
		if (d->fb_id)
			display_destroy_fb(d);
		d->src_w = t.bt.width;
		d->src_h = t.bt.height;
		d->src_pitch = capture_pitch(cap, t.bt.width);
		display_create_fb(d);
		info("buffer          %ux%u NV16, line pitch %u on panel %ux%u",
		     d->src_w, d->src_h, d->src_pitch, d->width, d->height);
	}

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
	audio_evaluate(a, cap, d->on);
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
		"                 [-a AUDIO] [-t DB] [-C CONFIG] [--rechner PATH] [--daten DIR]\n"
		"                 [--eingang NAME] [--lut PATH] [-n]\n"
		"        %s ctl [-s SOCKET] COMMAND [ARG...]      (h713-tv ctl help)\n"
		"\n"
		"  -s PATH     control socket; default %s\n"
		"  -C FILE     configuration (start = auto|manual|last, zustand = PATH|none,\n"
		"              preset = NAME|last, daten = DIR|none, rechner = PATH|none);\n"
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
		"  --rechner P h713-pq, which computes the values from the device data (none = do\n"
		"              not compute, take the compiled-in table); default %s\n"
		"  --daten D   directory of the unpacked vendor data (none = do not use it);\n"
		"              default %s\n"
		"  --eingang N the input h713-pq is asked about; default %s\n"
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
		me, me, CTL_SOCKET, CONF_FILE, STATE_FILE, V4L2_DRIVER, DRM_DRIVER,
		PQ_BIN, PQ_DATEN, PQ_EINGANG, PQ_LUT, GAMMA_FILE);
	exit(2);
}

int main(int argc, char **argv)
{
	struct opts o = { .gamma = GAMMA_FILE, .audio = "auto", .trim = "0" };
	struct capture cap = { .fd = -1 };
	struct display d = { .fd = -1 };
	struct retry rt = { .fd = -1 };
	/*
	 * The volume is the codec's and stays what it is until "ctl volume"
	 * says otherwise; the DSP starts at 0 dB (S16's reference) and unmuted
	 * as far as the listener is concerned -- the automaton mutes it.
	 */
	struct audio au = { .settle_fd = -1, .tick_fd = -1 };
	struct conf conf = { .path = CONF_FILE };
	enum audio_policy apol;
	struct pollfd fds[6];
	const char *sock = CTL_SOCKET;
	const char *startpreset = "standard";
	int sfd, arg, rc = 0;

	setvbuf(stdout, NULL, _IOLBF, 0);

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
			o.gamma_gesetzt = true;
		} else if (!strcmp(argv[arg], "--rechner") && arg + 1 < argc)
			o.rechner = argv[++arg];
		else if (!strcmp(argv[arg], "--daten") && arg + 1 < argc)
			o.daten = argv[++arg];
		else if (!strcmp(argv[arg], "--eingang") && arg + 1 < argc)
			o.eingang = argv[++arg];
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
	conf_read(&conf);
	if (o.rechner)
		snprintf(conf.rechner, sizeof(conf.rechner), "%s", o.rechner);
	if (o.daten)
		snprintf(conf.daten, sizeof(conf.daten), "%s", o.daten);
	if (o.eingang)
		snprintf(conf.eingang, sizeof(conf.eingang), "%s", o.eingang);
	if (o.lut)
		snprintf(conf.lut, sizeof(conf.lut), "%s", o.lut);
	ctl.conf = &conf;
	ctl.state_path = conf.keep ? conf.state_path : NULL;
	state_read(&ctl);
	ctl.policy = start_policy(&ctl);
	/* a client that hangs up mid-answer must not take the daemon with it (S12 F1) */
	signal(SIGPIPE, SIG_IGN);

	/*
	 * Which preset to come up with, and which values were kept for it.
	 * The order is -p, then tv.conf, then "standard" -- the command line
	 * is the last word, the file the standing setting. "zuletzt" takes
	 * the name out of the kept values; without them it is "standard".
	 */
	werte.path = conf.werte_path[0] && !o.report_only ? conf.werte_path : NULL;
	werte_read(&werte);
	startpreset = o.preset ? o.preset : (conf.preset[0] ? conf.preset : "standard");
	if (!strcasecmp(startpreset, "last") || !strcasecmp(startpreset, "zuletzt"))
		startpreset = werte.preset[0] ? werte.preset : "standard";

	/*
	 * h713-pq is started here and collected after the devices are open:
	 * a Python start costs about 200 ms, and the capture and DRM devices
	 * cost their own time -- there is no reason to spend both one after
	 * the other (plan 113 A.3).
	 */
	if (!o.report_only && strcasecmp(startpreset, "none"))
		pq_start(&pq, &conf, startpreset);

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
			     pq_presets_n, pq.gamma, pq.daten, pq.ms);
		else
			warn("picture values  %s -- the compiled-in table applies",
			     pq.why);
		/*
		 * The curve h713-pq just wrote is the one that belongs to
		 * this device's data. -g on the command line still wins: it
		 * is an explicit order, and it is how a curve can be tried
		 * without touching anything else.
		 */
		if (pq.ok && pq.lut_bytes && !o.gamma_gesetzt)
			o.gamma = pq.lut;
	}
	if (!o.report_only)
		display_gamma_load(&d, o.gamma);

	if (o.report_only) {
		struct v4l2_dv_timings t;
		int sig = capture_signal(&cap, &t);

		info("signal          %s", sig == 1 ? "present" :
		     sig == 2 ? "change in flight" :
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

	/* a previous run may have left the console dark; see console_restore() */
	console_restore();
	display_gamma_apply(&d);

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
		char msg[512], namen[192];
		int ret;

		preset_namen(namen, sizeof(namen));
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
			     namen);
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
			     preset_ist_aus_daten(p) ? "from the device data"
						     : "the compiled-in table");
		if (p && ret >= 0) {
			snprintf(preset_aktuell, sizeof(preset_aktuell), "%s", p->name);
			preset_aktuell_aus_daten = preset_ist_aus_daten(p);

			/* the third layer, on top of the second */
			ret = werte_apply(&cap, &werte, p->name, msg, sizeof(msg));
			if (ret < 0)
				warn("saved           %s", msg);
			else if (ret)
				info("saved           %d value%s from %s: %s", ret,
				     ret == 1 ? "" : "s", werte.path, msg);
		}
	}
	/*
	 * The aspect is part of what was kept. It is set before the first
	 * picture, so no plane has to be taken down for it.
	 */
	if (werte.present && werte.aspect[0] && d.has_aspect) {
		uint64_t val;

		if (prop_enum_parse(&d.plane_props, "aspect", werte.aspect, &val)) {
			d.aspect = val;
			info("saved           aspect %s", werte.aspect);
		} else {
			char namen[128];

			aspect_names(&d, namen, sizeof(namen));
			warn("%s:%u: the plane does not know aspect = \"%s\" (%s) -- dropped",
			     werte.path, werte.aspect_line, werte.aspect, namen);
		}
	}
	capture_subscribe(&cap);
	audio_open(&au, &cap, apol);
	control_listen(&ctl);
	sfd = signal_fd();
	rt.fd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC | TFD_NONBLOCK);
	if (rt.fd < 0)
		fail("timerfd_create: %s", strerror(errno));


	/* The state at startup counts as much as any later change. */
	reevaluate(&cap, &d, &rt, &au);

	/*
	 * Six sources, three of which may be absent: the control socket when
	 * its bind failed, and the two audio timers with -a none. poll()
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

	for (;;) {
		if (poll(fds, sizeof(fds) / sizeof(fds[0]), -1) < 0) {
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
			reevaluate(&cap, &d, &rt, &au);
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
			if (!seen || (seen & EV_SOURCE_CHANGE))
				evaluate(&cap, &d, &rt);
			audio_evaluate(&au, &cap, d.on);
		}
		if (fds[3].revents & POLLIN) {
			if (control_serve(&ctl, &cap, &d, &rt, &au))
				reevaluate(&cap, &d, &rt, &au);
		}
		if (fds[4].revents & POLLIN) {
			uint64_t ticks;

			if (read(au.settle_fd, &ticks, sizeof(ticks)) != sizeof(ticks))
				warn("audio           reading the timerfd: %s", strerror(errno));
			audio_settled(&au, &cap, d.on);
		}
		if (fds[5].revents & POLLIN) {
			uint64_t ticks;

			if (read(au.tick_fd, &ticks, sizeof(ticks)) != sizeof(ticks))
				warn("audio           reading the timerfd: %s", strerror(errno));
			audio_tick(&au, &cap, d.on);
		}
	}

	/*
	 * The same door for every way out: sound off, picture off, console
	 * back. A "systemctl stop" must not leave a still frame standing on
	 * the wall, nor a tone in the room, so a refused disable is an error
	 * exit, not a silent one.
	 */
	retry_stop(&rt);
	audio_close(&au);
	if (!display_hide(&d))
		rc = 1;
	control_close(&ctl);
	display_destroy_fb(&d);
	if (d.gamma_blob)
		drmModeDestroyPropertyBlob(d.fd, d.gamma_blob);
	props_put(&d.crtc_props);
	props_put(&d.plane_props);
	close(d.fd);
	close(rt.fd);
	close(sfd);
	close(cap.fd);

	return rc;
}
