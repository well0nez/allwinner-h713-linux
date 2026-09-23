/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE		/* accept4, strtok_r, O_CLOEXEC */
/*
 * h713-warp -- the keystone warp for the HY310 projector (design AP2d
 * design-h713-warp.txt, plan stage S5).
 *
 *   h713-warp [-c CONF] [-s SOCKET] [-t TV_SOCKET] [-r RENDER] [-v VIDEO] run
 *   h713-warp ctl [-s SOCKET] COMMAND [ARG...]
 *
 * "run" is the daemon; systemd owns its lifecycle, nothing here daemonises.
 * Everything else is one line over the control socket -- see ctl.c.
 *
 * Who owns what: h713-tv owns /dev/dri/card1, the DRM master, the video plane
 * and -- with its patch A1-A4 -- the three warp targets and every atomic
 * commit; h713-warp owns /dev/dri/renderD128, the capture buffers, the shader
 * and the matrix, and never opens card1; the kernel keeps the console on the
 * primary plane whenever neither of the two holds the master, which is what
 * makes every failure here end in a picture rather than a dark panel.
 */
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/signalfd.h>

#include "warp.h"

#define RETRY_MS	1000	/* while the wanted state cannot be reached */
#define PATTERN_MS	500	/* the test pattern's heartbeat, see below */

void info(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	putchar('\n');
	fflush(stdout);
}

void warn(const char *fmt, ...)
{
	va_list ap;

	fputs("warning: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
}

void fail(const char *fmt, ...)
{
	va_list ap;

	fputs("error: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	exit(1);
}

void text_add(struct textbuf *t, const char *fmt, ...)
{
	va_list ap;
	int k;

	if (t->l >= t->n - 1)
		return;
	va_start(ap, fmt);
	k = vsnprintf(t->b + t->l, t->n - t->l, fmt, ap);
	va_end(ap);
	if (k > 0)
		t->l += (size_t)k < t->n - t->l ? (size_t)k : t->n - 1 - t->l;
}

double now_s(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);

	return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
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
		"usage: %s [-c CONF] [-s SOCKET] [-t TV_SOCKET] [-r RENDER] [-v VIDEO] run\n"
		"       %s ctl [-s SOCKET] COMMAND [ARG...]      (h713-warp ctl help)\n"
		"\n"
		"  -c FILE     the eight corner values and the start state; default %s\n"
		"  -s PATH     this program's control socket; default %s\n"
		"  -t PATH     h713-tv's control socket, over which the panel buffers and\n"
		"              the frames travel; default %s\n"
		"  -r PATH     the render node; default %s (never a card node: h713-tv\n"
		"              owns the display and does every commit)\n"
		"  -v PATH     the capture device; without it the driver \"%s\" is searched for\n",
		me, me, WARP_CONF, WARP_SOCKET, TV_SOCKET, RENDER_NODE, V4L2_NAME);
	exit(2);
}

int main(int argc, char **argv)
{
	struct runtime r;
	struct control ctl;
	const char *sock = WARP_SOCKET, *tv = TV_SOCKET, *video = NULL;
	struct pollfd fds[4];
	int sfd, arg, rc = 0;

	setvbuf(stdout, NULL, _IOLBF, 0);
	memset(&r, 0, sizeof(r));
	r.conf.path = WARP_CONF;
	r.render_node = RENDER_NODE;

	if (argc >= 2 && !strcmp(argv[1], "ctl")) {
		int a = 2;

		if (argc >= 4 && !strcmp(argv[2], "-s")) {
			sock = argv[3];
			a = 4;
		}
		return client(argc - a, argv + a, sock);
	}
	for (arg = 1; arg < argc; arg++) {
		if (!strcmp(argv[arg], "-c") && arg + 1 < argc)
			r.conf.path = argv[++arg];
		else if (!strcmp(argv[arg], "-s") && arg + 1 < argc)
			sock = argv[++arg];
		else if (!strcmp(argv[arg], "-t") && arg + 1 < argc)
			tv = argv[++arg];
		else if (!strcmp(argv[arg], "-r") && arg + 1 < argc)
			r.render_node = argv[++arg];
		else if (!strcmp(argv[arg], "-v") && arg + 1 < argc)
			video = argv[++arg];
		else if (!strcmp(argv[arg], "run"))
			continue;
		else
			usage(argv[0]);
	}

	control_lock(&ctl, sock);
	conf_read(&r.conf);
	peer_init(&r.peer, tv);
	source_init(&r.source, video);
	r.on = r.conf.start_on;
	r.state = r.on ? WARP_BYPASS : WARP_OFF;
	warp_solve(&r);
	info("config          %s%s: %s, corners %d,%d %d,%d %d,%d %d,%d (tl tr bl br, per-mille)",
	     r.conf.path, r.conf.present ? "" : " missing",
	     r.on ? "warp = on" : "warp = off",
	     r.conf.v[0], r.conf.v[1], r.conf.v[2], r.conf.v[3],
	     r.conf.v[4], r.conf.v[5], r.conf.v[6], r.conf.v[7]);
	/* a client that hangs up mid-answer must not take the daemon with it */
	signal(SIGPIPE, SIG_IGN);
	control_listen(&ctl);
	sfd = signal_fd();
	warp_apply(&r);
	if (r.state != WARP_ON)
		info("warp            %s: %s", r.on ? "bypass" : "off", r.why);

	fds[0].fd = ctl.lfd;
	fds[0].events = POLLIN;
	fds[1].fd = sfd;
	fds[1].events = POLLIN;
	r.hold = true;
	r.check.slot = -1;
	r.source.held = -1;
	for (;;) {
		bool live = r.state == WARP_ON;
		int timeout = -1;

		/*
		 * The capture paces the loop; the peer is polled only for its
		 * hangup, which is h713-tv going away (A2's lifetime rule).
		 * A test pattern has no capture to wait for, so it is redrawn
		 * on a slow heartbeat -- the plane keeps showing the last
		 * buffer in between, this only proves the path is alive.
		 */
		fds[2].fd = live && r.pattern == PATTERN_NONE ? r.source.fd : -1;
		fds[2].events = POLLIN | POLLPRI;
		fds[3].fd = live ? r.peer.fd : -1;
		fds[3].events = 0;
		if (live && r.pattern != PATTERN_NONE)
			timeout = PATTERN_MS;
		else if (!live && r.on)
			timeout = RETRY_MS;
		if (r.check.slot >= 0)
			timeout = 2;		/* the self-check's second draw is due */
		if (poll(fds, 4, timeout) < 0) {
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
				info("reload          SIGHUP -- %s is read again", r.conf.path);
				conf_read(&r.conf);
				warp_solve(&r);
				if (r.state == WARP_ON)
					warp_disengage(&r, "the configuration was read again");
				r.on = r.conf.start_on;
				warp_apply(&r);
				continue;
			}
			info("exit            signal %u received", si.ssi_signo);
			break;
		}
		if (fds[3].fd >= 0 && (fds[3].revents & (POLLHUP | POLLERR | POLLNVAL)))
			warp_disengage(&r, "h713-tv closed the connection");
		else if (fds[2].fd >= 0 && (fds[2].revents & (POLLIN | POLLPRI)))
			warp_pump(&r);
		else if (live && r.pattern != PATTERN_NONE)
			warp_pump(&r);
		else if (!live && r.on)
			warp_apply(&r);
		warp_check_tick(&r);
		if (fds[0].revents & POLLIN)
			control_serve(&ctl, &r);
	}

	/*
	 * The same door for every way out: the panel buffers go back, h713-tv
	 * returns to its own mode, and the wall keeps a picture. A closed peer
	 * connection alone would do it, but saying it is better than implying it.
	 */
	warp_disengage(&r, "h713-warp is stopping");
	control_close(&ctl);
	close(sfd);

	return rc;
}
