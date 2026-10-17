/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's side of the want link and the straight ring's wait (P3 of the media side project, 17.10.2026), without a
 * device: main.c is compiled into this file, h713-warp is the other end of a socketpair. What is checked: without a word
 * from h713-warp the ring comes at once; "warp want ring" makes the ring wait and says "note claim" once; a plane that is
 * on, a standing claim, "none", a claim that failed here and the end of the second each let the ring through; a want
 * connection that closes keeps "ring" for the second (a restart), a new one starts the wait anew and replaces the old;
 * a line the connection does not take is refused.
 *
 *   test_want      exit 0 when every case passed
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

/* what h713-tv said on the other end, "" when nothing within ms */
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

static void back_by(struct timespec *t, long ms)
{
	clock_gettime(CLOCK_MONOTONIC, t);
	t->tv_sec -= ms / 1000;
	t->tv_nsec -= (ms % 1000) * 1000000L;
	if (t->tv_nsec < 0) {
		t->tv_sec--;
		t->tv_nsec += 1000000000L;
	}
}

int main(void)
{
	struct display d = { 0 };
	struct reply r = { 0 };
	int sv[2], sv2[2];

	/* no word from h713-warp: the ring at once, as before */
	check(!warp_wants_ring() && !want_hold(&d), "no want connection: the straight ring at once");

	/* "warp want ring" on a new connection */
	if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) || socketpair(AF_UNIX, SOCK_STREAM, 0, sv2))
		return 2;
	check(cmd_warp_want(&r, sv[0], "ring") && wish.peer == sv[0] && wish.ring && !strcmp(r.buf, "ok want ring\n"),
	      "\"warp want ring\": the connection is kept, answered \"ok want ring\", evaluate() asked for");
	check(warp_wants_ring(), "... h713-warp will claim the ring");
	check(want_hold(&d) && wish.armed && !ts_zero(&wish.since), "the plane off and no ring yet: the ring waits, the timer runs");
	check(!strcmp(heard(sv[1], 200), "note claim\n"), "... and h713-warp hears \"note claim\"");
	check(want_hold(&d) && !*heard(sv[1], 50), "the wait goes on, \"note claim\" not said twice");

	/* what lets the ring through */
	d.on = true;
	check(!want_hold(&d), "a plane that shows the ring already: no wait");
	d.on = false;
	warp.claimed = true;
	check(!want_hold(&d), "a standing claim: nothing to wait for");
	warp.claimed = false;
	back_by(&wish.since, WARP_HOLD_MS);
	check(!want_hold(&d) && wish.fallback && !wish.armed, "a second without a claim: the straight ring after all");
	check(!want_hold(&d), "... and it stays (until a claim's first frame)");
	want_hold_end();
	check(want_hold(&d), "after a first frame (want_hold_end) the next return waits again");
	check(want_give_up(false, "test") && wish.fallback && !want_hold(&d),
	      "a ring claim that fails here (no plane, no buffers): the ring without waiting further");
	check(!want_give_up(false, "test"), "... said once");
	want_hold_end();
	check(!want_give_up(true, "test") && !wish.fallback, "a client claim that fails does not end the ring's wait");

	/* "warp want none" through want_serve(): the wait ends, evaluate() asked for */
	want_hold_end();
	wish.noted = false;
	check(want_hold(&d) && !strcmp(heard(sv[1], 200), "note claim\n"), "a new wait, a new note");
	check(send(sv[1], "warp want none\n", 15, 0) == 15 && want_serve() && ts_zero(&wish.since) && !wish.ring,
	      "\"warp want none\" while the ring waits: the wait ends, evaluate() asked for");
	check(!strcmp(heard(sv[1], 200), "ok want none\n"), "... answered \"ok want none\"");
	check(!want_hold(&d), "... and the ring comes at once");
	check(send(sv[1], "warp want ring\nwarp want none\n", 30, 0) == 30 && !want_serve() && !wish.ring,
	      "two lines in one read: both taken, the last word counts");
	check(!strcmp(heard(sv[1], 200), "ok want ring\nok want none\n"), "... both answered");
	check(send(sv[1], "warp maybe\n", 11, 0) == 11 && !want_serve() && !strncmp(heard(sv[1], 200), "error", 5),
	      "a line the want connection does not take: refused");

	/* the connection closes while it says "ring" (h713-warp restarts), and a new one comes */
	check(send(sv[1], "warp want ring\n", 15, 0) == 15 && !want_serve() && wish.ring, "\"ring\" again");
	heard(sv[1], 100);
	check(want_hold(&d), "the ring waits");
	close(sv[1]);
	check(!want_serve() && wish.peer < 0 && !ts_zero(&wish.gone), "the connection closes: no peer, the time noted");
	check(warp_wants_ring() && want_hold(&d), "... \"ring\" stands for the second: the ring still waits");
	back_by(&wish.since, 600);
	check(cmd_warp_want(&r, sv2[0], "ring") && wish.peer == sv2[0] && ms_since(&wish.since) < 100,
	      "a new connection with \"ring\" (the restarted h713-warp): its wait begins now");
	check(want_hold(&d) && !strcmp(heard(sv2[1], 200), "note claim\n"), "... and it hears \"note claim\"");
	back_by(&wish.gone, WARP_HOLD_MS + 10);
	check(warp_wants_ring(), "the peer is back: \"ring\" does not lapse with the old connection's second");
	{
		int sv3[2];

		if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv3))
			return 2;
		r.len = 0;
		check(cmd_warp_want(&r, sv3[0], "none") && wish.peer == sv3[0] && !wish.ring,
		      "a third connection replaces the second (the newer h713-warp's word counts), \"none\" ends the wait");
		check(recv(sv2[1], r.buf, 1, MSG_DONTWAIT) == 0, "... the older connection is closed");
		close(sv3[1]);
		check(!want_serve() && wish.peer < 0 && !warp_wants_ring(), "a connection that closes while it says \"none\": no ring is waited for");
	}
	want_hold_end();
	back_by(&wish.gone, WARP_HOLD_MS + 10);
	wish.ring = true;
	check(!warp_wants_ring() && !want_hold(&d), "a connection gone for more than the second: the ring at once");

	printf("%s: %d failed\n", failed ? "FAILED" : "PASSED", failed);
	return failed ? 1 : 0;
}
