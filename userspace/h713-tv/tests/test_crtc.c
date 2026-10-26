/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The start after a run that left no mode on the CRTC (TODO 2.125), without a device: main.c is compiled into this file, the
 * libdrm calls of the CRTC search are made up here, and so are the console's two files (/dev/tty0, fb0/blank) - open(), write(),
 * ioctl() and close() of this program are taken over for them, every other path is refused. The made-up kernel does what 6.18's
 * does: the CRTC has a mode or none; a "0" written to fb0/blank commits the fbdev helper's mode (and its framebuffer on the
 * primary plane) unless a file is the master just then, and the write never says which (drm_fb_helper_blank() returns 0); the
 * unblank of tty0 paints only a blanked console and is not needed for the mode. What the kernel does to get there - the last
 * run's framebuffer taken off with its file, the CRTC switched off with its primary plane, no last close while another file holds
 * the card - is given as the state, not made. Each start is a child process (fail() ends one), the kernel is shared memory.
 * What is checked: a start finds a mode that is there and touches nothing; a start after a refused way out (A) or after a SIGKILL
 * (B) gives the master it got with the open back, restores the console and finds the console's mode - again and again in one
 * boot, there is no count; a start while another file is the master tries once and ends with the old message; the holder's
 * search takes the wall as it is.
 *
 *   test_crtc      exit 0 when every case passed
 */
#define main h713_tv_main
#include "../main.c"
#undef main

#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/wait.h>

static int failed;

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

/* the made-up kernel, shared with the starts */
static struct kernel {
	bool mode;		/* the CRTC drives a mode */
	bool master;		/* the program's file is the master (the open made it one) */
	bool other;		/* another file is the master just now (the holder, h713-osd around a commit) */
	bool fbdev;		/* the fbdev helper has a mode to give (it has on the box) */
	int seq, drops, drop_at, blanks, blank_at, restores;
	uint32_t crtc;		/* what the start found */
	unsigned int w, h;
} *k;

#define TTY_FD		900	/* /dev/tty0 */
#define BLANK_FD	901	/* /sys/class/graphics/fb0/blank */

int open(const char *path, int flags, ...)
{
	va_list ap;
	mode_t m = 0;

	if (!strcmp(path, CONSOLE_TTY))
		return TTY_FD;
	if (!strcmp(path, "/sys/class/graphics/fb0/blank"))
		return BLANK_FD;
	if (!strncmp(path, "/dev/", 5) || !strncmp(path, "/sys/", 5)) {
		errno = ENOENT;		/* /dev/vcsa1 and every other device: none here */
		return -1;
	}
	if (flags & O_CREAT) {
		va_start(ap, flags);
		m = va_arg(ap, mode_t);
		va_end(ap);
	}
	return (int)syscall(SYS_openat, AT_FDCWD, path, flags, m);
}

ssize_t write(int fd, const void *buf, size_t n)
{
	if (fd == TTY_FD)
		return (ssize_t)n;
	if (fd == BLANK_FD) {
		if (n && ((const char *)buf)[0] == '0') {
			k->blanks++;
			k->blank_at = ++k->seq;
			if (!k->master && !k->other && k->fbdev) {
				k->mode = true;
				k->restores++;
			}
		}
		return (ssize_t)n;
	}
	return (ssize_t)syscall(SYS_write, fd, buf, n);
}

int ioctl(int fd, unsigned long req, ...)
{
	va_list ap;
	void *arg;

	va_start(ap, req);
	arg = va_arg(ap, void *);
	va_end(ap);
	if (fd == TTY_FD) {
		if (req == KDGKBMODE)
			*(int *)arg = K_UNICODE;
		return 0;
	}
	return (int)syscall(SYS_ioctl, fd, req, arg);
}

int close(int fd)
{
	if (fd == TTY_FD || fd == BLANK_FD)
		return 0;
	return (int)syscall(SYS_close, fd);
}

/* one CRTC, 36, and the console's mode on the HY300PRO-G-EU */
drmModeResPtr drmModeGetResources(int fd)
{
	static uint32_t crtcs[] = { 36 };
	drmModeResPtr r = calloc(1, sizeof(*r));

	(void)fd;
	r->count_crtcs = 1;
	r->crtcs = crtcs;
	return r;
}

void drmModeFreeResources(drmModeResPtr r)
{
	free(r);
}

drmModeCrtcPtr drmModeGetCrtc(int fd, uint32_t id)
{
	drmModeCrtcPtr c = calloc(1, sizeof(*c));

	(void)fd;
	c->crtc_id = id;
	c->mode_valid = k->mode;
	if (k->mode)
		c->mode.hdisplay = 1280, c->mode.vdisplay = 720;
	return c;
}

void drmModeFreeCrtc(drmModeCrtcPtr c)
{
	free(c);
}

int drmDropMaster(int fd)
{
	(void)fd;
	if (!k->master) {
		errno = EINVAL;		/* not the master: what the kernel says */
		return -1;
	}
	k->master = false;
	k->drops++;
	k->drop_at = ++k->seq;
	return 0;
}

/* one start: its exit status, what it said in out */
static int start(void (*search)(struct display *), char *out, size_t size)
{
	int p[2], status;
	ssize_t n, got = 0;
	pid_t pid;

	k->seq = k->drops = k->drop_at = k->blanks = k->blank_at = k->restores = 0;
	k->crtc = 0, k->w = k->h = 0;
	fflush(stdout);
	if (pipe(p))
		return -1;
	pid = fork();
	if (!pid) {
		struct display d = { .fd = 7 };

		dup2(p[1], 1);
		dup2(p[1], 2);
		search(&d);
		k->crtc = d.crtc_id, k->w = d.width, k->h = d.height;
		fflush(stdout);
		_exit(0);
	}
	close(p[1]);
	while (got < (ssize_t)size - 1 && (n = read(p[0], out + got, size - 1 - got)) > 0)
		got += n;
	out[got] = '\0';
	close(p[0]);
	if (pid < 0 || waitpid(pid, &status, 0) != pid || !WIFEXITED(status))
		return -1;
	return WEXITSTATUS(status);
}

static bool found(void)
{
	return k->crtc == 36 && k->w == 1280 && k->h == 720;
}

int main(void)
{
	char out[4096];
	int rc, i;

	k = mmap(NULL, sizeof(*k), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	if (k == MAP_FAILED)
		return 2;
	*k = (struct kernel){ .fbdev = true };

	/* the console or the holder's black framebuffer drives the panel: found, nothing touched */
	k->mode = true, k->master = true;
	rc = start(display_find_crtc_start, out, sizeof(out));
	check(rc == 0 && found(), "a mode on the CRTC (the console, or the holder's black framebuffer): found at once");
	check(!k->blanks && !k->drops && k->master, "... the console is not touched, the master is left for main() to give back");

	/* (A) the way out's commit was refused: the run's framebuffer went with its file, the CRTC with its primary plane */
	k->mode = false, k->master = true;
	rc = start(display_find_crtc_start, out, sizeof(out));
	check(rc == 0 && found(), "(A) no mode after a refused way out: the start finds the console's mode, 1280x720 on CRTC 36");
	check(k->drops == 1 && k->restores == 1 && k->drop_at < k->blank_at,
	      "... the master it got with the open given back first, then the console restored (fb0/blank)");
	check(strstr(out, "none drives a mode") && !strstr(out, "error:"), "... and the journal says so in one line");

	/* (B) a SIGKILL with the warp's or a client's frame on the primary plane, three times in one boot */
	for (i = 1; i <= 3; i++) {
		char what[128];

		k->mode = false, k->master = true;
		rc = start(display_find_crtc_start, out, sizeof(out));
		snprintf(what, sizeof(what), "(B) crash %d of the boot, the next start (Restart=): the console's mode, no count", i);
		check(rc == 0 && found() && k->restores == 1, what);
	}

	/* another file is the master just as the start looks: fbcon may not paint, the start ends as before */
	k->mode = false, k->master = false, k->other = true;
	rc = start(display_find_crtc_start, out, sizeof(out));
	check(rc == 1 && strstr(out, "error: no CRTC drives a mode"), "another master holds the card: the start ends with the old message");
	check(k->blanks == 1 && !k->mode, "... after one try, no loop (systemd's Restart= is the next try)");
	k->other = false;

	/* a panel the console has no mode for (no fbdev): no endless search either */
	k->mode = false, k->master = true, k->fbdev = false;
	rc = start(display_find_crtc_start, out, sizeof(out));
	check(rc == 1 && strstr(out, "error: no CRTC drives a mode") && k->blanks == 1, "no mode the console could give: the old end, after one try");
	k->fbdev = true;

	/* the holder (and -n) take the wall as it is */
	k->mode = false, k->master = true;
	rc = start(display_find_crtc, out, sizeof(out));
	check(rc == 1 && strstr(out, "error: no CRTC drives a mode -- is the console running?") && !k->blanks,
	      "the holder's search with no mode: the old message, the console not touched");

	printf("%s\n", failed ? "FAILED" : "all passed");
	return failed ? 1 : 0;
}
