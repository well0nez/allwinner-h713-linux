/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The wall black between a client's release and the straight ring (TODO 2.124), without a device: main.c is compiled into this
 * file, and the libdrm calls of these paths are made up here and write down what they were asked (the rest stay abort() stubs).
 * What is checked: a client's claim that goes while the straight ring is to come puts a black framebuffer of the panel's size on
 * the primary plane and the video plane off in one commit, keeps the master and never shows the console's framebuffer; the
 * ring's commit takes the wall from it and the black framebuffer goes only once it is off the plane; when no picture comes, the
 * console's framebuffer goes up in a commit of this program's before the master goes and before the black one is removed; a page
 * takes the wall the same way; a claim of the ring that goes while the signal stands (the keystone set back) does the same, and the
 * straight ring that goes for a claim's first frame (a keystone set) leaves black, not the console, for that frame; and where no
 * ring is to follow (a program is the mode, "off", a page on the wall, the signal gone, the way out) the release is what it was:
 * the console, or the page.
 *
 *   test_wall      exit 0 when every case passed
 */
#define main h713_tv_main
#include "../main.c"
#undef main

static int failed;

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

/* the made-up card */
#define PRIMARY	34
#define VIDEO	38
#define CONSOLE	46		/* fbcon's framebuffer */
#define BLACK	90		/* what drmModeAddFB2() hands out */
static uint32_t primary_fb, video_fb;	/* what the planes hold: the committed FB_IDs */
static int commits, creates, destroys, masters = 1;
static uint32_t shown_seq[32];		/* every framebuffer committed on the primary plane, in order */
static int nshown;
static uint32_t removed[16];		/* drmModeRmFB() */
static int nremoved;
static bool removed_shown;		/* a framebuffer was removed while the primary plane held it */
static struct { uint32_t obj, prop; uint64_t val; } sets[64];
static int nsets, pending;
static struct props drm_video_props;	/* the video plane's property ids, for the commit's bookkeeping */

drmModeAtomicReqPtr drmModeAtomicAlloc(void)
{
	pending = 0;
	nsets = 0;
	return (drmModeAtomicReqPtr)calloc(1, 16);
}

int drmModeAtomicAddProperty(drmModeAtomicReqPtr req, uint32_t obj, uint32_t prop, uint64_t val)
{
	(void)req;
	if (nsets < 64) {
		sets[nsets].obj = obj, sets[nsets].prop = prop, sets[nsets].val = val;
		nsets++, pending++;
	}
	return 0;
}

void drmModeAtomicFree(drmModeAtomicReqPtr req)
{
	free(req);
}

int drmModeAtomicCommit(int fd, drmModeAtomicReqPtr req, uint32_t flags, void *data)
{
	int i;

	(void)fd, (void)req, (void)flags, (void)data;
	commits++;
	for (i = 0; i < nsets; i++) {
		if (sets[i].obj == PRIMARY && sets[i].prop == prop_id(&osd.props, "FB_ID")) {
			primary_fb = (uint32_t)sets[i].val;
			if (nshown < 32)
				shown_seq[nshown++] = primary_fb;
		}
		if (sets[i].obj == VIDEO && sets[i].prop == prop_id(&drm_video_props, "FB_ID"))
			video_fb = (uint32_t)sets[i].val;
	}
	return 0;
}

int drmSetMaster(int fd)
{
	(void)fd;
	masters++;
	return 0;
}

int drmDropMaster(int fd)
{
	(void)fd;
	masters--;
	return 0;
}

drmModePlanePtr drmModeGetPlane(int fd, uint32_t id)
{
	drmModePlanePtr p = calloc(1, sizeof(*p));

	(void)fd;
	p->plane_id = id;
	p->fb_id = id == PRIMARY ? primary_fb : video_fb;
	return p;
}

void drmModeFreePlane(drmModePlanePtr p)
{
	free(p);
}

int drmIoctl(int fd, unsigned long request, void *arg)
{
	(void)fd;
	if (request == DRM_IOCTL_MODE_CREATE_DUMB) {
		struct drm_mode_create_dumb *c = arg;

		creates++;
		c->handle = 9;
		c->pitch = c->width * c->bpp / 8;
		c->size = (uint64_t)c->pitch * c->height;
		return 0;
	}
	if (request == DRM_IOCTL_MODE_DESTROY_DUMB) {
		destroys++;
		return 0;
	}
	errno = ENOTTY;
	return -1;
}

int drmModeAddFB2(int fd, uint32_t width, uint32_t height, uint32_t pixel_format, const uint32_t bo_handles[4],
		  const uint32_t pitches[4], const uint32_t offsets[4], uint32_t *buf_id, uint32_t flags)
{
	(void)fd, (void)width, (void)height, (void)pixel_format, (void)bo_handles, (void)pitches, (void)offsets, (void)flags;
	*buf_id = BLACK;
	return 0;
}

int drmModeRmFB(int fd, uint32_t id)
{
	(void)fd;
	if (id == primary_fb)
		removed_shown = true;
	if (nremoved < 16)
		removed[nremoved++] = id;
	return 0;
}

/* a plane's property list as props_get() would leave it: ids base + n in the order of the names */
static void fake_props(struct props *p, const char *const *names, unsigned int n, uint32_t base)
{
	unsigned int i;

	p->list = calloc(1, sizeof(*p->list));
	p->list->count_props = n;
	p->list->props = calloc(n, sizeof(uint32_t));
	p->list->prop_values = calloc(n, sizeof(uint64_t));
	p->info = calloc(n, sizeof(*p->info));
	for (i = 0; i < n; i++) {
		p->info[i] = calloc(1, sizeof(**p->info));
		p->info[i]->prop_id = p->list->props[i] = base + i;
		snprintf(p->info[i]->name, sizeof(p->info[i]->name), "%s", names[i]);
	}
}

/* the value the last commit set for the property NAME of plane OBJ (props P), or -1 */
static int64_t committed(const struct props *p, uint32_t obj, const char *name)
{
	uint32_t id = prop_id(p, name);
	int i;

	for (i = nsets - 1; i >= 0; i--)
		if (sets[i].obj == obj && sets[i].prop == id)
			return (int64_t)sets[i].val;
	return -1;
}

static bool was_removed(uint32_t id)
{
	for (int i = 0; i < nremoved; i++)
		if (removed[i] == id)
			return true;
	return false;
}

static bool console_shown_after(int from)
{
	for (int i = from; i < nshown; i++)
		if (shown_seq[i] == CONSOLE)
			return true;
	return false;
}

/* Kodi on the wall through h713-warp's client claim, the console's framebuffer under it, the mode now HDMI */
static void kodi(struct display *d)
{
	d->on = false;
	d->warped = true;
	d->master = true;
	masters = 1;
	warp.claimed = warp.client = true;
	warp.peer = -1;
	for (int i = 0; i < WARP_BUFS; i++)
		warp.fb_id[i] = 60 + i, warp.handle[i] = 6;
	video_fb = 61;
	primary_fb = CONSOLE;
	osd.claimed = osd.shown = false;
	osd.want = -1;
	cover.on = false;
	ctl.policy = POLICY_AUTO;
	ctl.source = SOURCE_HDMI;
	leaving = false;
	nshown = nremoved = 0;
	removed_shown = false;
	creates = destroys = 0;
}

int main(void)
{
	static const char *const vid[] = { "FB_ID", "CRTC_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H", "CRTC_X", "CRTC_Y",
					   "CRTC_W", "CRTC_H", "hdmi-ring" };
	static const char *const pri[] = { "FB_ID", "CRTC_ID", "zpos", "SRC_X", "SRC_Y", "SRC_W", "SRC_H",
					   "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H" };
	struct display d = { .fd = -1, .plane_id = VIDEO, .crtc_id = 36, .width = 1280, .height = 720,
			     .fb_id = 70, .src_w = 1280, .src_h = 720, .src_pitch = 1280, .win_w = 1280, .win_h = 720 };
	int c0;

	fake_props(&d.plane_props, vid, 11, 100);
	fake_props(&osd.props, pri, 11, 200);
	drm_video_props = d.plane_props;
	osd.plane_id = PRIMARY;
	osd.console_fb = CONSOLE;
	osd.console_known = true;

	/* Kodi -> HDMI without a keystone: the client's claim goes, the straight ring is to come */
	kodi(&d);
	c0 = commits;
	warp_release(&d);
	check(commits == c0 + 1 && committed(&d.plane_props, VIDEO, "FB_ID") == 0 &&
	      committed(&d.plane_props, VIDEO, "CRTC_ID") == 0, "the release: one commit, the video plane off");
	check(primary_fb == BLACK && committed(&osd.props, PRIMARY, "zpos") == 0 && committed(&osd.props, PRIMARY, "CRTC_ID") == 36 &&
	      committed(&osd.props, PRIMARY, "CRTC_W") == 1280 && creates == 1,
	      "... a black framebuffer of the panel's size on the primary plane, zpos 0, in the same commit");
	check(!console_shown_after(0), "... the console's framebuffer is not put up");
	check(d.master && masters == 1 && !d.warped && !warp.claimed, "... the master is kept for the ring's commit");
	check(was_removed(60) && was_removed(61) && was_removed(62) && !removed_shown && !was_removed(BLACK),
	      "... the warp's buffers go, the black one stays");
	wall_black_free(&d);
	check(!was_removed(BLACK) && wall_black.fb_id == BLACK, "the black framebuffer is not removed while it is on the plane");
	c0 = commits;
	check(display_show(&d) && commits == c0 + 1 && video_fb == 70 && committed(&d.plane_props, VIDEO, "hdmi-ring") == 1,
	      "the straight ring: one commit");
	check(primary_fb == CONSOLE && committed(&osd.props, PRIMARY, "zpos") == 0,
	      "... and the console's framebuffer under it, in the same commit: from black to the ring with nothing between");
	wall_black_free(&d);
	check(was_removed(BLACK) && !removed_shown && destroys >= 1 && !wall_black.fb_id,
	      "... then the black framebuffer goes, off the plane");
	d.on = false;

	/* the release, and then no picture: the console's framebuffer up first, by this program, then the black one away */
	kodi(&d);
	warp_release(&d);
	check(primary_fb == BLACK, "the release: black");
	c0 = commits;
	display_hide(&d);
	check(commits == c0 + 1 && primary_fb == CONSOLE && was_removed(BLACK) && !removed_shown && !d.master && masters == 0,
	      "no picture after all: the console's framebuffer committed before the master goes, the black one removed off the plane");

	/* the release, and then a page (the launcher opened in the tenth of a second) */
	kodi(&d);
	warp_release(&d);
	osd.claimed = true;
	osd.fb_id[0] = 48;
	osd.fb_id[1] = 50;
	osd.want = 0;
	osd.cover = true;
	osd_resume(&d);
	check(primary_fb == 48 && d.master, "a page over the black: the page's own commit takes the wall");
	wall_black_free(&d);
	check(was_removed(BLACK) && !removed_shown, "... and the black framebuffer goes, off the plane");
	osd.claimed = osd.shown = false;
	osd.want = -1;
	osd.cover = false;

	/* no ring to follow: the release is what it was */
	kodi(&d);
	ctl.source = SOURCE_CLIENT;		/* Kodi -> the browser: a program follows, h713-warp holds the picture */
	warp_release(&d);
	check(creates == 0 && primary_fb == CONSOLE && !d.master, "a program is the mode: the console, as before (no black framebuffer)");
	kodi(&d);
	ctl.policy = POLICY_OFF;
	warp_release(&d);
	check(creates == 0 && primary_fb == CONSOLE && !d.master, "\"ctl off\": the console");
	kodi(&d);
	warp.client = false;			/* a claim of the ring: the keystone set back to the identity, the signal stands */
	nosig.lost = false;
	warp_release(&d);
	check(creates == 1 && primary_fb == BLACK && d.master && !console_shown_after(0),
	      "a claim of the ring goes while the signal stands (the keystone gone): black, for the ring's commit");
	display_show(&d);
	wall_black_free(&d);
	check(primary_fb == CONSOLE && was_removed(BLACK) && !removed_shown, "... the ring takes the wall, the black one goes");
	d.on = false;
	kodi(&d);
	warp.client = false;
	nosig.lost = true;			/* the signal went: the claim goes for the page or the console */
	warp_release(&d);
	check(creates == 0 && primary_fb == CONSOLE, "a claim of the ring that goes with the signal: as before");
	nosig.lost = false;
	kodi(&d);
	leaving = true;
	warp_release(&d);
	check(creates == 0 && primary_fb == CONSOLE, "the way out: as before");
	kodi(&d);
	osd.claimed = osd.shown = true;		/* an opaque page stands over the paused client */
	osd.fb_id[0] = 48;
	osd.want = 0;
	osd.cover = true;
	cover.on = true;
	warp_release(&d);
	check(creates == 0 && primary_fb == 48 && d.master, "a page on the wall: it stays over black, as before");

	/* a keystone comes: the straight ring goes for h713-warp's claim, its first frame takes the wall */
	kodi(&d);
	warp.claimed = warp.client = false;
	for (int i = 0; i < WARP_BUFS; i++)
		warp.fb_id[i] = 0, warp.handle[i] = 0;
	d.warped = false;
	d.on = true;
	video_fb = 70;
	c0 = commits;
	check(ring_off_for_claim(&d) && commits == c0 + 1 && primary_fb == BLACK && video_fb == 0 && d.master && !d.on,
	      "the straight ring goes for a claim: one commit, the video plane off and black on the primary plane, the master kept");
	check(!console_shown_after(0), "... not the console's framebuffer");
	{
		bool busy;
		int flip = -1;

		warp.claimed = true;
		warp.fb_id[0] = 60;
		d.warped = true;
		check(warp_commit(&d, 0, -1, &busy, &flip) && video_fb == 60 && primary_fb == CONSOLE,
		      "the claim's first frame: the warped picture on the video plane, the console's framebuffer under it, one commit");
		wall_black_free(&d);
		check(was_removed(BLACK) && !removed_shown, "... and the black framebuffer goes, off the plane");
	}
	kodi(&d);
	warp.claimed = warp.client = false;
	d.warped = false;
	d.on = true;
	osd.claimed = osd.shown = true;		/* a page over the ring (it would not be: a page pauses it - the rule, not the case) */
	osd.fb_id[0] = 48;
	osd.want = 0;
	osd.cover = true;
	primary_fb = 48;
	ring_off_for_claim(&d);
	check(creates == 0 && primary_fb == 48, "a page on the wall: display_hide() as before, the page stays");
	osd.claimed = osd.shown = false;
	osd.want = -1;
	osd.cover = false;

	printf("%s\n", failed ? "FAILED" : "all passed");
	return failed ? 1 : 0;
}
