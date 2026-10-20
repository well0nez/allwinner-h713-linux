/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The wall held black over a restart of the picture path (TODO 2.96), without a device: main.c is compiled into this file, and the
 * few libdrm calls of these paths are made up here and write down what they were asked (the rest stay abort() stubs). What is
 * checked: HOLD_FILE names a live holder or nobody; the way out with a holder puts its framebuffer on the primary plane and the video
 * plane off in one commit and gives the master back, and without one commits nothing; the start after a held restart leaves the
 * console dark only while the holder's framebuffer is on the plane and the console's framebuffer is known and real; no later look
 * at the plane (h713-osd's claim) takes the holder's framebuffer for the console's; the console's framebuffer is written down for
 * that start, never the holder's.
 *
 *   test_hold      exit 0 when every case passed
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

/* the made-up card: what the planes hold, which framebuffers exist, what was committed */
#define PRIMARY	34
#define VIDEO	38
static uint32_t primary_fb;		/* what drmModeGetPlane() says the primary plane holds */
static uint32_t real_fb = 46;		/* the one XRGB8888 framebuffer of the panel's size drmModeGetFB2() knows */
static uint32_t real_format = DRM_FORMAT_XRGB8888;
static int commits, masters;
static struct { uint32_t obj, prop; uint64_t val; } sets[64];
static int nsets, pending;

drmModeAtomicReqPtr drmModeAtomicAlloc(void)
{
	pending = 0;
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

int drmModeAtomicCommit(int fd, drmModeAtomicReqPtr req, uint32_t flags, void *data)
{
	(void)fd, (void)req, (void)flags, (void)data;
	commits++;
	return 0;
}

void drmModeAtomicFree(drmModeAtomicReqPtr req)
{
	free(req);
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
	p->fb_id = id == PRIMARY ? primary_fb : 0;
	return p;
}

void drmModeFreePlane(drmModePlanePtr p)
{
	free(p);
}

drmModeFB2Ptr drmModeGetFB2(int fd, uint32_t id)
{
	drmModeFB2Ptr f;

	(void)fd;
	if (id != real_fb)
		return NULL;
	f = calloc(1, sizeof(*f));
	f->fb_id = id, f->width = 1280, f->height = 720, f->pixel_format = real_format;
	return f;
}

void drmModeFreeFB2(drmModeFB2Ptr f)
{
	free(f);
}

/* a plane's property list as props_get() would leave it: ids 100 + n in the order of the names */
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

	for (i = nsets - 1; i >= nsets - pending && i >= 0; i--)
		if (sets[i].obj == obj && sets[i].prop == id)
			return (int64_t)sets[i].val;
	return -1;
}

static void put(const char *path, const char *text)
{
	FILE *f = fopen(path, "w");

	if (f) {
		fputs(text, f);
		fclose(f);
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

int main(void)
{
	static const char *const vid[] = { "FB_ID", "CRTC_ID" };
	static const char *const pri[] = { "FB_ID", "CRTC_ID", "zpos", "SRC_X", "SRC_Y", "SRC_W", "SRC_H",
					   "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H" };
	char dir[] = "/tmp/test_hold.XXXXXX", hf[96], cf[96], line[64];
	struct display d = { .fd = -1, .plane_id = VIDEO, .crtc_id = 36, .width = 1280, .height = 720 };
	uint32_t fb = 0;
	pid_t dead;
	int sv[2], c0;
	FILE *f;

	if (!mkdtemp(dir) || socketpair(AF_UNIX, SOCK_STREAM, 0, sv))
		return 2;
	snprintf(hf, sizeof(hf), "%s/hold", dir);
	snprintf(cf, sizeof(cf), "%s/console-fb", dir);
	hold_file = hf;
	console_fb_file = cf;
	fake_props(&d.plane_props, vid, 2, 100);
	fake_props(&osd.props, pri, 11, 200);
	osd.plane_id = PRIMARY;

	/* HOLD_FILE */
	check(!hold_read(&fb), "no HOLD_FILE: no holder");
	snprintf(line, sizeof(line), "%d 77\n", (int)getpid());
	put(hf, line);
	check(hold_read(&fb) == getpid() && fb == 77, "HOLD_FILE names a running process and its framebuffer: the holder");
	if (!(dead = fork()))
		_exit(0);
	waitpid(dead, NULL, 0);
	snprintf(line, sizeof(line), "%d 77\n", (int)dead);
	put(hf, line);
	check(!hold_read(&fb), "a holder that is gone: no holder");
	put(hf, "nonsense\n");
	check(!hold_read(&fb), "a file that says nothing: no holder");
	snprintf(line, sizeof(line), "%d 0\n", (int)getpid());
	put(hf, line);
	check(!hold_read(&fb), "no framebuffer: no holder");

	/* the way out, no holder: nothing committed, the caller hands the console back as always */
	unlink(hf);
	c0 = commits;
	check(!hold_take(&d) && commits == c0, "stopped without a holder: no commit here, the console as before");

	/* the way out with a holder: one commit, the video plane off, the black framebuffer on the primary plane at zpos 0 */
	snprintf(line, sizeof(line), "%d 77\n", (int)getpid());
	put(hf, line);
	d.on = true;
	masters = 0;
	check(hold_take(&d) && commits == c0 + 1, "stopped with a holder: one commit");
	check(committed(&d.plane_props, VIDEO, "FB_ID") == 0 && committed(&d.plane_props, VIDEO, "CRTC_ID") == 0,
	      "... the video plane off");
	check(committed(&osd.props, PRIMARY, "FB_ID") == 77 && committed(&osd.props, PRIMARY, "zpos") == 0 &&
	      committed(&osd.props, PRIMARY, "CRTC_ID") == 36 && committed(&osd.props, PRIMARY, "CRTC_W") == 1280,
	      "... the holder's framebuffer on the primary plane, the whole panel, zpos 0");
	check(!d.master && !masters && !d.on, "... and the master given back, nothing of ours on the wall");

	/* the start after a held restart */
	osd.console_known = false;
	primary_fb = 77;
	unlink(cf);
	check(!hold_adopt(&d) && !osd.console_known, "the console's framebuffer not written down: the console after all");
	put(cf, "46\n");
	check(hold_adopt(&d) && osd.console_known && osd.console_fb == 46,
	      "the holder's framebuffer on the plane, the console's known and real: no console at the start, the console is 46");
	osd.console_known = false;
	primary_fb = 46;
	check(!hold_adopt(&d) && !osd.console_known, "the plane holds something else (the hold did not go up): the console");
	primary_fb = 77;
	put(cf, "77\n");
	check(!hold_adopt(&d), "the file names the holder's framebuffer itself: the console");
	put(cf, "45\n");
	check(!hold_adopt(&d), "the file names a framebuffer the card does not know: the console");
	put(cf, "46\n");
	real_format = DRM_FORMAT_ARGB8888;
	check(!hold_adopt(&d), "... or one that is not the console's kind (a page's ARGB8888): the console");
	real_format = DRM_FORMAT_XRGB8888;
	unlink(hf);
	check(!hold_adopt(&d), "no holder: the console, as every start before");

	/* every later look at the plane (h713-osd's claim learns the console again): the holder's framebuffer is never the console */
	snprintf(line, sizeof(line), "%d 77\n", (int)getpid());
	put(hf, line);
	primary_fb = 77;
	osd.claimed = false;
	osd.console_known = false;
	osd.console_fb = 0;
	check(osd_learn(&d) && osd.console_known && osd.console_fb == 46,
	      "the claim looks at the plane while it holds the holder's framebuffer: the console is still 46, not 77");
	primary_fb = 46;
	osd.console_known = false;
	check(osd_learn(&d) && osd.console_fb == 46, "... and with the console on the plane: 46, as always");
	unlink(hf);
	primary_fb = 52;
	osd.console_known = false;
	check(osd_learn(&d) && osd.console_fb == 52, "no holder: whatever the plane holds, as before");

	/* the console's framebuffer written down for that start - never the holder's */
	unlink(cf);
	hold_console_note(46);
	f = fopen(cf, "r");
	check(f && fscanf(f, "%u", &fb) == 1 && fb == 46, "osd_learn() writes the console's framebuffer down");
	if (f)
		fclose(f);
	snprintf(line, sizeof(line), "%d 77\n", (int)getpid());
	put(hf, line);
	hold_console_note(77);
	f = fopen(cf, "r");
	check(f && fscanf(f, "%u", &fb) == 1 && fb == 46, "... but not the holder's black one, should the plane hold it");
	if (f)
		fclose(f);
	unlink(hf);

	unlink(cf);
	rmdir(dir);
	printf("%s\n", failed ? "FAILED" : "all passed");
	return failed ? 1 : 0;
}
