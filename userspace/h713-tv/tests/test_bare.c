/* SPDX-License-Identifier: GPL-2.0 */
/*
 * "ctl bare SECONDS" (TODO 4.9h, 25.10.2026), without a device: main.c is compiled into this file, the libdrm calls of these paths
 * are made up here and write down what they were asked (the rest stay abort() stubs), and h713-osd is the other end of a socketpair.
 * What is checked: an opaque page over black (the launcher, the settings, the page without a signal) goes off the wall when bare
 * begins, the master and the console go back, and "ctl off" during it does not take the page again; an "osd show" during it is kept
 * and answered "ok waiting"; "bare 0" puts the page h713-osd wanted last back over black, and so does the end of its time; the page
 * over the ring with the black frame under it goes in one commit; a popup over a picture goes and the picture stays; over the warp the
 * console's framebuffer rides on its next frame and nothing stays queued; without a page bare commits nothing; the argument is checked.
 *
 *   test_bare      exit 0 when every case passed
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
#define PAGE0	48		/* h713-osd's two buffers */
#define PAGE1	50
#define UNDER	92		/* what drmModeAddFB2() hands out for NV12: the black frame under a page */
static uint32_t primary_fb, video_fb;	/* what the planes hold: the committed FB_IDs */
static uint64_t primary_z;
static int commits, masters;
static struct { uint32_t obj, prop; uint64_t val; } sets[64];
static int nsets;
static struct props drm_video_props;	/* the video plane's property ids, for the commit's bookkeeping */

drmModeAtomicReqPtr drmModeAtomicAlloc(void)
{
	nsets = 0;
	return (drmModeAtomicReqPtr)calloc(1, 16);
}

int drmModeAtomicAddProperty(drmModeAtomicReqPtr req, uint32_t obj, uint32_t prop, uint64_t val)
{
	(void)req;
	if (nsets < 64) {
		sets[nsets].obj = obj, sets[nsets].prop = prop, sets[nsets].val = val;
		nsets++;
	}
	return 0;
}

void drmModeAtomicFree(drmModeAtomicReqPtr req)
{
	free(req);
}

int drmModeAtomicCommit(int fd, drmModeAtomicReqPtr req, uint32_t flags, void *data)
{
	(void)fd, (void)req, (void)flags, (void)data;
	commits++;
	for (int i = 0; i < nsets; i++) {
		if (sets[i].obj == PRIMARY && sets[i].prop == prop_id(&osd.props, "FB_ID"))
			primary_fb = (uint32_t)sets[i].val;
		if (sets[i].obj == PRIMARY && sets[i].prop == prop_id(&osd.props, "zpos"))
			primary_z = sets[i].val;
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

		c->handle = 9;
		c->pitch = c->width * c->bpp / 8;
		c->size = (uint64_t)c->pitch * c->height;
		return 0;
	}
	if (request == DRM_IOCTL_MODE_MAP_DUMB) {
		((struct drm_mode_map_dumb *)arg)->offset = 0;
		return 0;
	}
	errno = ENOTTY;
	return -1;
}

int drmModeAddFB2(int fd, uint32_t width, uint32_t height, uint32_t pixel_format, const uint32_t bo_handles[4],
		  const uint32_t pitches[4], const uint32_t offsets[4], uint32_t *buf_id, uint32_t flags)
{
	(void)fd, (void)width, (void)height, (void)pixel_format, (void)bo_handles, (void)pitches, (void)offsets, (void)flags;
	*buf_id = UNDER;
	return 0;
}

/* a plane's property list as props_get() would leave it: ids base + n in the order of the names */
static void fake_props(struct props *p, const char *const *names, unsigned int n, uint32_t base)
{
	p->list = calloc(1, sizeof(*p->list));
	p->list->count_props = n;
	p->list->props = calloc(n, sizeof(uint32_t));
	p->list->prop_values = calloc(n, sizeof(uint64_t));
	p->info = calloc(n, sizeof(*p->info));
	for (unsigned int i = 0; i < n; i++) {
		p->info[i] = calloc(1, sizeof(**p->info));
		p->info[i]->prop_id = p->list->props[i] = base + i;
		snprintf(p->info[i]->name, sizeof(p->info[i]->name), "%s", names[i]);
	}
}

/* what h713-tv answered h713-osd, "" when nothing within ms */
static const char *heard(int fd, int ms)
{
	static char buf[256];
	struct pollfd pf = { .fd = fd, .events = POLLIN };
	ssize_t got;

	buf[0] = '\0';
	if (poll(&pf, 1, ms) == 1 && (got = recv(fd, buf, sizeof(buf) - 1, MSG_DONTWAIT)) > 0)
		buf[got] = '\0';
	return buf;
}

/* one line of h713-osd's, served as the loop would */
static const char *osd_line(struct display *d, int other, const char *line)
{
	if (send(other, line, strlen(line), MSG_NOSIGNAL) < 0)
		return "";
	osd_serve(d);
	return heard(other, 200);
}

static const char *bare_cmd(struct display *d, const char *arg)
{
	static struct reply r;

	memset(&r, 0, sizeof(r));
	cmd_bare(&r, d, arg);
	return r.buf;
}

/* the console on the wall, h713-osd claimed, nothing of ours shown: the start of every case */
static void console(struct display *d)
{
	bare_end(d, "the next case");
	d->on = d->warped = false;
	d->master = false;
	masters = 0;
	primary_fb = CONSOLE;
	primary_z = 0;
	video_fb = 0;
	under.up = false;
	osd.claimed = true;
	osd.shown = osd.queued = false;
	osd.want = -1;
	osd.cover = false;
	cover.on = cover.resuming = false;
	warp.claimed = warp.client = false;
	warp.peer = -1;
	ctl.policy = POLICY_AUTO;
	ctl.source = SOURCE_AUTO;
}

/* an opaque page over black, as "osd show N cover" without a picture puts it */
static void page_over_black(struct display *d, int n)
{
	osd.want = n;
	osd.cover = true;
	osd_resume(d);
}

int main(void)
{
	static const char *const vid[] = { "FB_ID", "CRTC_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H", "CRTC_X", "CRTC_Y",
					   "CRTC_W", "CRTC_H", "hdmi-ring" };
	static const char *const pri[] = { "FB_ID", "CRTC_ID", "zpos", "SRC_X", "SRC_Y", "SRC_W", "SRC_H",
					   "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H" };
	struct display d = { .fd = -1, .plane_id = VIDEO, .crtc_id = 36, .width = 1280, .height = 720,
			     .fb_id = 70, .src_w = 1280, .src_h = 720, .src_pitch = 1280, .win_w = 1280, .win_h = 720 };
	char dir[] = "/tmp/test_bare.XXXXXX", cf[64];
	int sv[2], c0, mfd;

	if (!mkdtemp(dir) || socketpair(AF_UNIX, SOCK_STREAM, 0, sv))
		return 2;
	snprintf(cf, sizeof(cf), "%s/console-fb", dir);
	console_fb_file = cf;			/* osd_learn() writes the console's framebuffer down: not into /run */
	hold_file = cf;
	fake_props(&d.plane_props, vid, 11, 100);
	fake_props(&osd.props, pri, 11, 200);
	drm_video_props = d.plane_props;
	osd.plane_id = PRIMARY;
	osd.console_fb = CONSOLE;
	osd.console_known = true;
	osd.fb_id[0] = PAGE0;
	osd.fb_id[1] = PAGE1;
	osd.peer = sv[0];

	/* the launcher over the console ("ctl off", no signal): the case of the L018, 25.10.2026 */
	console(&d);
	ctl.policy = POLICY_OFF;
	page_over_black(&d, 0);
	check(primary_fb == PAGE0 && primary_z == 2 && d.master && osd.shown, "the launcher over black: on the primary plane, the master held");
	check(display_hide(&d) && primary_fb == PAGE0 && d.master, "... \"ctl off\" leaves it there, as it is meant to");
	check(!strncmp(bare_cmd(&d, "60"), "ok bare 60", 10) && bare.on, "\"bare 60\": ok");
	check(primary_fb == CONSOLE && primary_z == 0 && !d.master && masters == 0 && !osd.shown,
	      "... the page goes, the console's framebuffer is back and the master is given back: the console has the panel");
	check(osd.want == 0 && osd.cover, "... the page stays wanted");
	check(bare_left() > 58 && bare_left() <= 60, "... its time runs");
	c0 = commits;
	check(display_hide(&d) && commits == c0 && !d.master, "\"ctl off\" during it: no page taken back, nothing committed");
	check(!strncmp(osd_line(&d, sv[1], "osd show 1 cover\n"), "ok waiting", 10) && osd.want == 1 && osd.cover &&
	      primary_fb == CONSOLE && !d.master && commits == c0, "\"osd show 1 cover\" during it (the next row): ok waiting, kept, nothing on the wall");
	check(!strncmp(osd_line(&d, sv[1], "osd show 0\n"), "ok waiting", 10) && primary_fb == CONSOLE,
	      "\"osd show 0\" (a popup) during it: ok waiting as well");
	osd_line(&d, sv[1], "osd show 1 cover\n");
	osd_resume(&d);
	osd_settle(&d);
	check(primary_fb == CONSOLE && !d.master, "osd_resume() and osd_settle() put nothing up during it");
	check(!strncmp(bare_cmd(&d, NULL), "ok bare on", 10), "\"bare\" shows it on");
	check(!strncmp(bare_cmd(&d, "0"), "ok bare off", 11) && !bare.on, "\"bare 0\": ok, off");
	check(primary_fb == PAGE1 && primary_z == 2 && d.master && osd.shown,
	      "... the page h713-osd wanted last is back over black, without a key");
	check(!strcmp(bare_cmd(&d, NULL), "ok bare off\n") && !strcmp(bare_cmd(&d, "0"), "ok bare off\n"),
	      "\"bare\" shows it off; \"bare 0\" again changes nothing");

	/* the net: nobody says "bare 0" */
	console(&d);
	ctl.policy = POLICY_OFF;
	page_over_black(&d, 1);
	bare_cmd(&d, "1");
	check(primary_fb == CONSOLE && !d.master, "\"bare 1\": the console");
	{
		struct pollfd pf = { .fd = bare.fd, .events = POLLIN };
		uint64_t ticks;

		check(poll(&pf, 1, 1500) == 1 && read(bare.fd, &ticks, sizeof(ticks)) == sizeof(ticks), "... its timer fires after a second");
	}
	bare_end(&d, "its time is over");
	check(!bare.on && primary_fb == PAGE1 && d.master && osd.shown, "... and at its end the page is back");
	bare_cmd(&d, "30");
	bare_cmd(&d, "2");
	check(bare_left() <= 2 && bare.on, "a second \"bare N\" sets its time anew");
	bare_cmd(&d, "0");

	/* the page goes while bare holds (Back, the launcher closed): nothing comes back at its end */
	console(&d);
	ctl.policy = POLICY_OFF;
	page_over_black(&d, 0);
	bare_cmd(&d, "60");
	check(!strncmp(osd_line(&d, sv[1], "osd hide\n"), "ok", 2) && osd.want < 0, "\"osd hide\" during it: ok");
	bare_cmd(&d, "0");
	check(primary_fb == CONSOLE && !d.master && !osd.shown, "... at its end the console stays");

	/* the launcher over the ring: the black frame under it on the video plane (20.10.2026) */
	mfd = memfd_create("under", 0);
	if (mfd < 0 || ftruncate(mfd, 1280 * 720 * 3 / 2))
		return 2;
	console(&d);
	d.fd = mfd;
	d.on = true;
	d.master = true;
	masters = 1;
	video_fb = 70;
	osd.want = 0;
	osd.cover = true;
	osd.shown = true;
	primary_fb = PAGE0;
	primary_z = 2;
	check(under_black_up(&d) && video_fb == UNDER && primary_fb == PAGE0 && !d.on, "the launcher over the ring: the black frame under it");
	ctl.policy = POLICY_OFF;
	display_hide(&d);
	check(video_fb == UNDER && primary_fb == PAGE0 && d.master, "... \"ctl off\": both stay");
	c0 = commits;
	bare_cmd(&d, "60");
	check(commits == c0 + 1 && video_fb == 0 && primary_fb == CONSOLE && primary_z == 0 && !under.up && !d.master,
	      "\"bare\": the black frame and the page off in one commit, the console has the panel");
	bare_cmd(&d, "0");
	check(primary_fb == PAGE0 && d.master && video_fb == 0, "... \"bare 0\": the page over black");
	d.fd = -1;
	close(mfd);

	/* a popup over the straight ring (the volume strip) while bare is begun on its own: the picture stays */
	console(&d);
	d.on = true;
	d.master = true;
	masters = 1;
	video_fb = 70;
	osd.want = 0;
	osd.shown = true;
	primary_fb = PAGE0;
	primary_z = 2;
	bare_cmd(&d, "60");
	check(primary_fb == CONSOLE && primary_z == 0 && video_fb == 70 && d.on && d.master,
	      "a popup over the ring: it goes, the picture and the master stay");
	bare_cmd(&d, "0");
	check(primary_fb == PAGE0 && primary_z == 2 && video_fb == 70 && osd.shown, "... and comes back over it");

	/* over the warp's ring: the console's framebuffer with the next frame, nothing stays queued */
	console(&d);
	d.warped = true;
	d.master = true;
	masters = 1;
	warp.claimed = true;
	warp.peer = sv[0];		/* a connection: the warp is alive (its frames are not served in this test) */
	warp.fb_id[0] = 60;
	osd.want = 0;
	osd.shown = true;
	primary_fb = PAGE0;
	primary_z = 2;
	c0 = commits;
	bare_cmd(&d, "60");
	check(commits == c0 && osd.queued && primary_fb == PAGE0, "a popup over the warp: queued for its next frame, no commit of its own");
	{
		bool busy;
		int flip = -1;

		check(warp_commit(&d, 0, -1, &busy, &flip) && video_fb == 60 && primary_fb == CONSOLE && primary_z == 0 && !osd.shown &&
		      !osd.queued, "... the frame carries the console's framebuffer, nothing stays queued");
		osd_resume(&d);
		check(primary_fb == CONSOLE && !osd.queued, "... the warp's next frames do not bring the popup back");
		bare_cmd(&d, "0");
		check(osd.queued || primary_fb == PAGE0, "\"bare 0\": the popup goes with the warp's next frame");
		check(warp_commit(&d, 0, -1, &busy, &flip) && primary_fb == PAGE0 && primary_z == 2 && osd.shown,
		      "... and is on the wall with it");
	}
	warp.peer = -1;

	/* without a page: bare changes nothing on the wall */
	console(&d);
	c0 = commits;
	bare_cmd(&d, "60");
	bare_cmd(&d, "0");
	check(commits == c0 && primary_fb == CONSOLE && !d.master, "no page, no picture: bare and its end commit nothing");
	console(&d);
	d.on = true;
	d.master = true;
	masters = 1;
	video_fb = 70;
	c0 = commits;
	bare_cmd(&d, "60");
	bare_cmd(&d, "0");
	check(commits == c0 && video_fb == 70 && d.master, "the ring without an overlay: nothing committed, the picture stays");

	/* the argument */
	check(!strncmp(bare_cmd(&d, "x"), "error", 5) && !strncmp(bare_cmd(&d, "-1"), "error", 5) &&
	      !strncmp(bare_cmd(&d, "601"), "error", 5) && !strncmp(bare_cmd(&d, "5s"), "error", 5) && !bare.on,
	      "\"bare x\", \"-1\", \"601\", \"5s\": refused, not begun");
	check(!strncmp(bare_cmd(&d, "600"), "ok bare 600", 11) && bare.on, "\"bare 600\": the longest");
	bare_end(&d, "the end");

	unlink(cf);
	rmdir(dir);
	printf("%s\n", failed ? "FAILED" : "all passed");
	return failed ? 1 : 0;
}
