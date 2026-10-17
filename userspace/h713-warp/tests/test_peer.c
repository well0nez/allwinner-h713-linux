/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE
/*
 * The peer link to h713-tv (peer.c) against a scripted h713-tv: the claim, frames, the switch of a standing claim
 * ("warp switch client|ring") and the note h713-tv says unasked ("note source X") - alone between two exchanges, in
 * front of an answer, behind it, in the same read or in a read of its own, with and without a flip fence; the page's
 * notes ("note cover on|off") and "client" said again (a program starts); and "source auto" on a connection of its own
 * (the program has ended). The want link (P3): "warp want ring|none" said once per change on a connection of its own,
 * h713-tv's "note claim" heard on it, the link made again after h713-tv went (at most once a second), and an h713-tv
 * that does not know the line asked no more. No GPU, no device: the fake answers on a Unix socket, the three panel
 * buffers are memfds.
 *
 *   test_peer          exit 0 when every case passed
 */
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>

#include "warp.h"

void info(const char *fmt, ...) { (void)fmt; }
void warn(const char *fmt, ...) { (void)fmt; }
double now_s(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}

static int failed;

static void check(bool ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		failed++;
}

static void send_fds(int c, const char *line, int nfd)
{
	char cbuf[CMSG_SPACE(sizeof(int) * WARP_TARGETS)] = { 0 };
	struct iovec io = { (void *)line, strlen(line) };
	struct msghdr m = { .msg_iov = &io, .msg_iovlen = 1, .msg_control = cbuf, .msg_controllen = CMSG_SPACE(sizeof(int) * nfd) };
	struct cmsghdr *cm = CMSG_FIRSTHDR(&m);
	int fds[WARP_TARGETS], i;

	for (i = 0; i < nfd; i++)
		fds[i] = memfd_create("t", 0);
	cm->cmsg_level = SOL_SOCKET;
	cm->cmsg_type = SCM_RIGHTS;
	cm->cmsg_len = CMSG_LEN(sizeof(int) * nfd);
	memcpy(CMSG_DATA(cm), fds, sizeof(int) * nfd);
	if (sendmsg(c, &m, 0) < 0)
		_exit(3);
	for (i = 0; i < nfd; i++)
		close(fds[i]);
}

static void say(int c, const char *s)
{
	if (send(c, s, strlen(s), 0) < 0)
		_exit(3);
}

/* the scripted h713-tv: one connection, one reaction per line it is sent */
static void fake_tv(const char *path)
{
	struct sockaddr_un a = { .sun_family = AF_UNIX };
	char buf[256];
	int l = socket(AF_UNIX, SOCK_STREAM, 0), c;
	ssize_t got;

	snprintf(a.sun_path, sizeof(a.sun_path), "%s", path);
	if (l < 0 || bind(l, (struct sockaddr *)&a, sizeof(a)) || listen(l, 2))
		_exit(2);
	c = accept(l, NULL, NULL);
	while ((got = recv(c, buf, sizeof(buf) - 1, 0)) > 0) {
		buf[got] = '\0';
		buf[strcspn(buf, "\n")] = '\0';
		if (!strcmp(buf, "warp claim")) {
			send_fds(c, "ok 64 32 64 nv12 2048 source hdmi\n", WARP_TARGETS);
		} else if (!strcmp(buf, "warp frame 0")) {		/* a note in a send of its own, then the answer */
			say(c, "note source hdmi\n");
			usleep(30000);
			say(c, "ok\n");
		} else if (!strcmp(buf, "warp frame 1")) {		/* note and answer in one send */
			say(c, "note source auto\nok\n");
		} else if (!strcmp(buf, "warp frame 2")) {		/* the answer, the note behind it in the same send */
			say(c, "ok\nnote source client\n");
		} else if (!strcmp(buf, "warp switch client")) {	/* the answer, then a note between two exchanges */
			say(c, "ok source auto\n");
			usleep(30000);
			say(c, "note source hdmi\n");
		} else if (!strcmp(buf, "warp switch ring")) {
			say(c, "error source is client -- no switch to the ring\n");
		} else if (!strcmp(buf, "warp frame 3")) {		/* a note, then the answer with a client's flip fence */
			say(c, "note source auto\n");
			usleep(20000);
			send_fds(c, "ok\n", 1);
		} else if (!strcmp(buf, "warp frame 4")) {		/* an opaque page came: the note in front of the answer */
			say(c, "note cover on\nok\n");
		} else if (!strcmp(buf, "warp frame 5")) {		/* the page went, and a program says it starts */
			say(c, "ok\nnote cover off\nnote source client\n");
		} else if (!strcmp(buf, "warp release")) {
			say(c, "ok\n");
			break;
		} else {
			say(c, "error unknown\n");
		}
	}
	close(c);
	/* the program has ended: "source auto" on a connection of its own, answered and closed */
	c = accept(l, NULL, NULL);
	got = recv(c, buf, sizeof(buf) - 1, 0);
	if (got <= 0)
		_exit(4);
	buf[got] = '\0';
	say(c, strcmp(buf, "source auto\n") ? "error unknown\n" : "ok source auto\n");
	close(c);
	close(l);
	_exit(0);
}

/* one line in, or nothing within a second */
static bool hear(int c, const char *want_line)
{
	struct pollfd pf = { .fd = c, .events = POLLIN };
	char buf[128];
	ssize_t got;

	if (poll(&pf, 1, 1000) != 1)
		return false;
	got = recv(c, buf, sizeof(buf) - 1, 0);
	if (got <= 0)
		return false;
	buf[got] = '\0';
	return !strcmp(buf, want_line);
}

/* the scripted h713-tv for the want link: ring + note, none, a restart (the link closed), then an h713-tv that does not know it */
static void fake_tv_want(const char *path)
{
	struct sockaddr_un a = { .sun_family = AF_UNIX };
	int l = socket(AF_UNIX, SOCK_STREAM, 0), c, bad = 0;

	snprintf(a.sun_path, sizeof(a.sun_path), "%s", path);
	if (l < 0 || bind(l, (struct sockaddr *)&a, sizeof(a)) || listen(l, 2))
		_exit(2);
	c = accept(l, NULL, NULL);
	if (hear(c, "warp want ring\n"))
		say(c, "ok want ring\nnote claim\n");
	else
		bad |= 1;
	if (hear(c, "warp want none\n"))
		say(c, "ok want none\n");
	else
		bad |= 2;
	usleep(50000);
	close(c);			/* h713-tv went (a restart) */
	c = accept(l, NULL, NULL);	/* the link again, the word again */
	if (hear(c, "warp want ring\n"))
		say(c, "error warp knows \"status\" here\n");	/* an h713-tv of before the want link */
	else
		bad |= 4;
	close(c);
	close(l);
	_exit(bad ? 10 + bad : 0);
}

static bool readable(int fd, int ms)
{
	struct pollfd pf = { .fd = fd, .events = POLLIN };

	return poll(&pf, 1, ms) == 1 && (pf.revents & POLLIN);
}

int main(void)
{
	char dir[] = "/tmp/test-peer-XXXXXX", path[sizeof(((struct sockaddr_un *)0)->sun_path)], why[WARP_WHY];
	struct peer p;
	pid_t pid;
	int flip = -1, rc, i, st;

	if (!mkdtemp(dir))
		return 2;
	snprintf(path, sizeof(path), "%s/ctl", dir);
	pid = fork();
	if (pid == 0)
		fake_tv(path);
	for (i = 0; i < 100 && access(path, F_OK); i++)
		usleep(10000);

	peer_init(&p, path);
	check(peer_claim(&p, SRC_RING, why, sizeof(why)) && p.width == 64 && p.coff == 2048, "the claim: three buffers, the geometry");
	check(p.tv_source == TV_HDMI && !p.noted, "the claim's answer names the source, no note");

	rc = peer_frame(&p, 0, -1, &flip, why, sizeof(why));
	check(rc == 0 && flip < 0, "a note in a read of its own in front of the answer: the frame is committed");
	check(p.noted && p.tv_source == TV_HDMI, "... and the note is heard: source hdmi");
	p.noted = false;

	rc = peer_frame(&p, 1, -1, &flip, why, sizeof(why));
	check(rc == 0 && p.noted && p.tv_source == TV_AUTO, "note and answer in one read: committed, source auto");
	p.noted = false;

	rc = peer_frame(&p, 2, -1, &flip, why, sizeof(why));
	check(rc == 0 && p.noted && p.tv_source == TV_CLIENT, "the note behind the answer in the same read: source client");
	p.noted = false;

	check(peer_switch(&p, SRC_CLIENT, why, sizeof(why)) && p.tv_source == TV_AUTO && !p.noted,
	      "warp switch client: ok, the answer's source is taken");
	check(readable(p.fd, 1000) && peer_notes(&p) && p.noted && p.tv_source == TV_HDMI,
	      "a note between two exchanges: read by peer_notes, source hdmi");
	p.noted = false;
	check(!readable(p.fd, 50) && peer_notes(&p) && !p.noted, "nothing to read: peer_notes keeps the link, no note");

	check(!peer_switch(&p, SRC_RING, why, sizeof(why)) && strstr(why, "no switch to the ring") && p.tv_source == TV_CLIENT,
	      "warp switch ring refused: false, why names it, the source of the refusal is taken");

	rc = peer_frame(&p, 3, -1, &flip, why, sizeof(why));
	check(rc == 0 && flip >= 0 && p.noted && p.tv_source == TV_AUTO, "a note, then the answer with a flip fence: the fence arrives");
	if (flip >= 0)
		close(flip);
	p.noted = false;

	rc = peer_frame(&p, 4, -1, &flip, why, sizeof(why));
	check(rc == 0 && p.cover && !p.noted, "\"note cover on\" in front of the answer: the page is heard, no source note");
	rc = peer_frame(&p, 5, -1, &flip, why, sizeof(why));
	check(rc == 0 && !p.cover && p.noted && p.tv_source == TV_CLIENT && p.client_said > 0,
	      "\"note cover off\" and \"note source client\" behind the answer: the page went, a program starts");
	p.noted = false;

	peer_release(&p);
	check(p.fd < 0 && !p.cover, "the release closes the link, and the page's word goes with it");
	check(peer_set_source(&p, "auto") && p.tv_source == TV_AUTO, "source auto on a connection of its own: ok, source auto");
	waitpid(pid, &st, 0);
	check(WIFEXITED(st) && WEXITSTATUS(st) == 0, "the fake h713-tv saw every line it expected");
	unlink(path);

	/* the want link (P3) */
	snprintf(path, sizeof(path), "%s/want", dir);
	pid = fork();
	if (pid == 0)
		fake_tv_want(path);
	for (i = 0; i < 100 && access(path, F_OK); i++)
		usleep(10000);
	peer_init(&p, path);
	peer_want(&p, true, false);
	check(p.want_fd < 0, "want: no link made when it is not asked for (warp = off)");
	peer_want(&p, true, true);
	check(p.want_fd >= 0 && p.want_said == 1, "want: the link made, \"warp want ring\" said");
	check(readable(p.want_fd, 1000) && peer_want_notes(&p) && p.claim_noted, "want: the answer and \"note claim\" heard");
	p.claim_noted = false;
	peer_want(&p, true, true);
	check(p.want_said == 1 && !readable(p.want_fd, 50), "want: the same word is not said again");
	peer_want(&p, false, true);
	check(p.want_said == 0 && readable(p.want_fd, 1000) && peer_want_notes(&p) && !p.claim_noted,
	      "want: \"warp want none\" said when the word changes, answered, no note");
	check(readable(p.want_fd, 1000) && !peer_want_notes(&p) && p.want_fd < 0 && p.want_said < 0,
	      "want: h713-tv went - the link is closed, the word unsaid");
	peer_want(&p, true, true);
	check(p.want_fd < 0, "want: not made again within a second");
	p.want_tried = 0;
	peer_want(&p, true, true);
	check(p.want_fd >= 0 && p.want_said == 1, "want: made again after the second, the word said again");
	check(readable(p.want_fd, 1000) && !peer_want_notes(&p) && p.want_refused && p.want_fd < 0,
	      "want: an h713-tv that does not know the line - the link closed and not asked again");
	p.want_tried = 0;
	peer_want(&p, true, true);
	check(p.want_fd < 0, "want: ... not even after the second");
	waitpid(pid, &st, 0);
	check(WIFEXITED(st) && WEXITSTATUS(st) == 0, "want: the fake h713-tv saw every line it expected");
	unlink(path);
	rmdir(dir);
	printf("%s: %d failed\n", failed ? "FAILED" : "PASSED", failed);

	return failed ? 1 : 0;
}
