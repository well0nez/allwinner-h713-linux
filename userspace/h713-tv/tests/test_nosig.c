/* SPDX-License-Identifier: GPL-2.0 */
/*
 * h713-tv's side of the page without a signal (P5 of the media side project, 17.10.2026), without a device: main.c is compiled into this
 * file, h713-osd is the other end of a socketpair. What is checked: nothing is said while there is a signal; a signal that is gone (decided,
 * not a change in flight) lets the last picture stand for the page, at most NOSIG_WAIT_MS, and h713-osd hears "note signal none" once;
 * a page that stands, no picture on the wall, or an expired wait let the caller go on to the console; a signal that is back says its name -
 * at once, or after h713-warp's claim when one is to come (at most WARP_HOLD_MS); a console forced with "ctl off", a program as the mode
 * and a missing h713-osd take the page back ("note signal off"); "osd signal" is answered with the word.
 *
 *   test_nosig      exit 0 when every case passed
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
	struct retry rt = { .fd = -1 };
	struct v4l2_dv_timings t = { 0 };
	int sv[2], sw[2];

	if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) || socketpair(AF_UNIX, SOCK_STREAM, 0, sw))
		return 2;
	t.type = V4L2_DV_BT_656_1120;
	t.bt.width = 1920, t.bt.height = 1080, t.bt.pixelclock = 148500000;
	t.bt.hfrontporch = 88, t.bt.hsync = 44, t.bt.hbackporch = 148;
	t.bt.vfrontporch = 4, t.bt.vsync = 5, t.bt.vbackporch = 36;
	ctl.policy = POLICY_AUTO;
	ctl.source = SOURCE_AUTO;

	/* h713-osd is not here: the console, as always */
	d.on = true;
	check(!nosig_page_ok(), "no h713-osd claimed: no page");
	check(!nosig_defer(&d, &rt, true) && nosig.lost, "a signal that is gone, no page possible: the caller goes on to the console");
	check(!strcmp(nosig_word(), "off"), "... the word would be \"off\"");
	nosig_claimed();
	check(!nosig.lost, "a claim of the ring (it needs a signal) ends the loss");

	/* h713-osd claimed on the connection */
	osd.claimed = true;
	osd.peer = sv[0];
	check(nosig_page_ok() && !strcmp(nosig_word(), "ok"), "h713-osd claimed, a signal: the page is possible, the word is \"ok\"");
	nosig_tell();
	check(!*heard(sv[1], 50), "nothing is said while there is a signal");

	/* not decided (a change in flight, a reading that failed): no page, no wait */
	check(!nosig_defer(&d, &rt, false) && !nosig.lost, "a change in flight is not a loss");

	/* a signal that is gone, the picture on the wall (d.on or the warp's), no page yet */
	check(nosig_defer(&d, &rt, true) && nosig.lost && !ts_zero(&nosig.since),
	      "no signal, the ring on the plane: the caller leaves the wall alone (the last picture stands for the page)");
	check(!strcmp(nosig_word(), "none"), "... the word is \"none\"");
	nosig_tell();
	check(!strcmp(heard(sv[1], 200), "note signal none\n") && nosig.said, "... h713-osd hears \"note signal none\"");
	nosig_tell();
	check(!*heard(sv[1], 50), "... once");
	check(nosig_defer(&d, &rt, true), "the wait goes on");

	/* the same with the warp's claim */
	d.on = false;
	d.warped = true;
	check(nosig_defer(&d, &rt, true), "the warp's last frame stands for the page too");

	/* the page is on the wall: the caller goes on (the claim goes under the page) */
	osd.shown = true;
	osd.cover = true;
	osd.want = 0;
	check(osd_covering() && !nosig_defer(&d, &rt, true), "the page stands (osd show N cover): the caller goes on");
	osd.shown = false;
	osd.cover = false;
	osd.want = -1;

	/* no picture on the wall: nothing to hold */
	d.warped = false;
	check(!nosig_defer(&d, &rt, true), "no picture on the wall: nothing to hold, the caller goes on");

	/* an expired wait: the console after all */
	d.on = true;
	back_by(&nosig.since, NOSIG_WAIT_MS + 10);
	check(!nosig_defer(&d, &rt, true), "a page that did not come within NOSIG_WAIT_MS: the console after all");
	memset(&nosig.since, 0, sizeof(nosig.since));
	check(nosig_defer(&d, &rt, true), "a fresh wait begins again");

	/* h713-warp lets go while the page is not up: the claim and the last frame stay (no console for a tenth of a second) */
	warp.claimed = true;
	warp.client = false;
	warp.peer = sw[0];
	d.on = false;
	d.warped = true;
	memset(&nosig.since, 0, sizeof(nosig.since));
	check(nosig_linger(&d) && warp.claimed && warp.peer < 0 && !ts_zero(&nosig.since),
	      "h713-warp lets go, the page is not up: the claim stays, without its connection, the release is left for later");
	check(osd_alone(&d), "... and a change of the primary plane (the page) goes on its own: no frame of the warp will carry it");
	osd.shown = true;
	osd.cover = true;
	osd.want = 0;
	check(!nosig_linger(&d), "the page stands: the release goes ahead (nosig_follow() asks for it)");
	osd.shown = false;
	osd.cover = false;
	osd.want = -1;
	warp.peer = sw[0];
	back_by(&nosig.since, NOSIG_WAIT_MS + 10);
	check(!nosig_linger(&d), "a wait that ran out: released at once, the console after all");
	memset(&nosig.since, 0, sizeof(nosig.since));
	nosig.lost = false;
	check(!nosig_linger(&d), "no loss decided (the daemon let go for another reason): released at once");
	nosig.lost = true;
	ctl.policy = POLICY_OFF;
	check(!nosig_linger(&d), "the console forced: released at once");
	ctl.policy = POLICY_AUTO;
	warp.client = true;
	check(!nosig_linger(&d), "a client's claim: released at once");
	warp.client = false;
	warp.claimed = false;
	warp.peer = -1;
	d.warped = false;
	d.on = true;

	/* "osd signal": answered with the word, and said is set */
	nosig.said = false;
	check(send(sv[1], "osd signal\n", 11, 0) == 11, "h713-osd asks after a claim");
	osd_serve(&d);
	check(!strcmp(heard(sv[1], 200), "ok signal none\n") && nosig.said, "... \"ok signal none\", and the note after it would be a repeat");
	nosig_tell();
	check(!*heard(sv[1], 50), "... so none is said");

	/* a program is the mode, the console forced: no page */
	ctl.source = SOURCE_CLIENT;
	check(!nosig_page_ok() && !strcmp(nosig_word(), "off"), "a program is the mode: no page, the word is \"off\"");
	nosig_tell();
	check(!strcmp(heard(sv[1], 200), "note signal off\n") && !nosig.said, "... h713-osd hears \"note signal off\"");
	ctl.source = SOURCE_AUTO;
	nosig_tell();
	check(!strcmp(heard(sv[1], 200), "note signal none\n") && nosig.said, "the program is over, still no signal: \"none\" again");
	ctl.policy = POLICY_OFF;
	nosig_tell();
	check(!strcmp(heard(sv[1], 200), "note signal off\n"), "\"ctl off\": the page goes, the console is the service's");
	ctl.policy = POLICY_AUTO;
	nosig_tell();
	check(!strcmp(heard(sv[1], 200), "note signal none\n"), "\"ctl auto\": the page again");
	warp.claimed = true;
	warp.client = true;
	check(!nosig_page_ok(), "a client's claim: no page");
	warp.claimed = warp.client = false;

	/* the signal is back; no claim to wait for: the word at once */
	wish.ring = false;
	d.on = true;
	nosig_back(&rt, &t);
	check(!nosig.lost && !strcmp(nosig.text, "1920x1080p60, 148.5 MHz"), "the signal is back, h713-warp does not claim the ring: the loss ends at once");
	nosig_tell();
	check(!strcmp(heard(sv[1], 200), "note signal 1920x1080p60, 148.5 MHz\n") && !nosig.said,
	      "... h713-osd hears the signal's name: the page goes");

	/* the signal is back and h713-warp is to claim: the page waits for the claim */
	nosig.lost = true;
	nosig.said = true;
	check(cmd_warp_want(&(struct reply){ 0 }, sw[0], "ring") && warp_wants_ring(), "h713-warp says it will claim the ring");
	heard(sw[1], 50);
	nosig_back(&rt, &t);
	check(nosig.lost && !ts_zero(&nosig.back), "the signal is back, a claim is to come: the page stays");
	nosig_tell();
	check(!*heard(sv[1], 50), "... h713-osd hears nothing yet");
	nosig_back(&rt, &t);
	check(nosig.lost, "... and it keeps waiting");
	nosig_claimed();
	nosig_tell();
	check(!nosig.lost && !strcmp(heard(sv[1], 200), "note signal 1920x1080p60, 148.5 MHz\n"), "the claim is made: the page goes");

	/* ... a claim that does not come: the second ends it */
	nosig.lost = true;
	nosig.said = true;
	memset(&nosig.back, 0, sizeof(nosig.back));
	nosig_back(&rt, &t);
	check(nosig.lost, "the wait begins anew");
	back_by(&nosig.back, WARP_HOLD_MS + 10);
	nosig_back(&rt, &t);
	check(!nosig.lost, "no claim within WARP_HOLD_MS: the page goes without it");
	nosig_tell();
	check(!strncmp(heard(sv[1], 200), "note signal 1920x1080p60", 24), "... h713-osd hears the signal");

	/* h713-osd went: nothing to say, said is cleared */
	nosig.lost = true;
	nosig.said = true;
	osd.claimed = false;
	nosig_tell();
	check(!nosig.said, "h713-osd released: nothing said, the state forgotten");

	printf("%s: %d failed\n", failed ? "FAILED" : "PASSED", failed);
	return failed ? 1 : 0;
}
