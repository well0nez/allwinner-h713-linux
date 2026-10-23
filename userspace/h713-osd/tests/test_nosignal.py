"""Host tests of the page without a signal in h713-osd (P5 of the media side project): the fake h713-tv of test_osd.py says "none" -
asked after the claim ("osd signal") or unasked ("note signal none") - and the real daemon puts an OPAQUE page on the wall that says
"No signal on HDMI" and, a line below, "HOME: menu". What is checked is read from the buffers the fake keeps: that the page is
opaque over the whole panel with nothing but the ground in the outer 5 %, that it is shown with "cover", that the launcher and a
page of the page channel take its place and give it back, that a word "signal" takes it away, that a volume strip rides in it and
comes off it, that it is pre-distorted over a keystone, that it comes back after h713-tv was gone.

The font is OSD_TEST_FONT, else the image's path; without one the tests are skipped.

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
"""

import os
import subprocess
import time
import unittest

from test_launcher import COLUMN, FONT, GROUND, ROWS, SX0, SX1, SY0, SY1, line
from test_osd import BIN, FakeTv, H, PITCH, W
from test_page import PageBase


@unittest.skipUnless(os.path.exists(FONT), "no font at %s (set OSD_TEST_FONT)" % FONT)
class NoSignalTest(PageBase):
    def setUp(self):
        super().setUp()
        self.env.update(H713_OSD_FONT=FONT, H713_OSD_CLOCK="20:47")

    def launcher(self, *words, wait=0.4):
        r = subprocess.run([BIN, "ctl", "launcher"] + list(words), env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout + r.stderr)
        time.sleep(wait)
        return r.stdout

    def status(self):
        return self.ctl("status")

    def px(self, data, x, y):
        return data[y * PITCH + 4 * x:y * PITCH + 4 * x + 4]

    def start_none(self):
        """h713-tv answers "none" to the question after the claim: the page comes without any event"""
        self.tv.signal = "none"
        self.start()
        time.sleep(0.5)

    def shows(self, n):
        return [l for l in self.tv.lines[n:] if l.startswith("osd show") or l == "osd hide"]

    def test_the_word_after_the_claim_opens_the_page_without_an_event(self):
        self.start_none()
        data = self.shown()
        self.assertIsNotNone(data, "no page on the wall")
        self.assertEqual(self.tv.lines.count("osd signal"), 1)
        self.assertTrue([l for l in self.tv.lines if l.startswith("osd show")][-1].endswith(" cover"), self.tv.lines)
        st = self.status()
        self.assertIn("no-signal page  shown", st)
        self.assertIn("launcher        closed", st)

    def test_it_is_an_opaque_page_with_words_inside_the_safe_margin(self):
        self.start_none()
        data = self.shown()
        self.assertEqual(self.tv.bbox(), (0, 0, W - 1, H - 1))                  # over the whole panel
        clear = ink = outside = 0
        for y in range(H):
            for x in range(W):
                p = self.px(data, x, y)
                clear += p[3] != 255
                if p != GROUND:
                    ink += 1
                    outside += not (SX0 <= x < SX1 and SY0 <= y < SY1)
        self.assertEqual(clear, 0, "pixels that are not opaque")
        self.assertEqual(outside, 0, "ink in the outer 5 %")
        self.assertGreater(ink, 300, "the symbol and the words are drawn")
        top = all(self.px(data, x, y) == GROUND for y in range(H // 4) for x in range(W))
        bottom = all(self.px(data, x, y) == GROUND for y in range(H * 3 // 4, H) for x in range(W))
        self.assertTrue(top and bottom, "the ground above and below, nothing else")
        # centred: the ink's middle is the panel's
        xs = [x for y in range(H) for x in range(W) if self.px(data, x, y) != GROUND]
        self.assertLess(abs((min(xs) + max(xs)) / 2 - W / 2), 3)

    def test_a_note_opens_it_and_the_word_signal_takes_it_away(self):
        self.start()
        time.sleep(0.3)
        self.assertIsNone(self.tv.shown)
        self.tv.push("note signal none")
        time.sleep(0.4)
        self.assertIsNotNone(self.tv.shown)
        self.assertIn("no-signal page  shown", self.status())
        n = len(self.tv.lines)
        self.tv.push("note signal 1920x1080p60")
        time.sleep(0.4)
        self.assertIsNone(self.tv.shown)
        self.assertEqual(self.shows(n), ["osd hide"])
        self.assertIn("no-signal page  none", self.status())

    def test_a_note_of_another_kind_is_ignored(self):
        self.start_none()
        n = len(self.tv.lines)
        self.tv.push("note something else entirely")
        time.sleep(0.3)
        self.assertIsNotNone(self.tv.shown)
        self.assertEqual(self.shows(n), [])

    def test_the_launcher_takes_its_place_and_gives_it_back(self):
        self.start_none()
        page = self.shown()
        n = len(self.tv.lines)
        self.launcher(line(1))
        lau = self.shown()
        self.assertNotEqual(lau, page)
        st = self.status()
        self.assertIn("launcher        open", st)
        self.assertIn("no-signal page  wanted, not shown", st)
        self.launcher("close")
        self.assertEqual(self.shown(), page, "the page is back, the same pixels")
        shows = self.shows(n)
        self.assertNotIn("osd hide", shows, "the wall goes from the launcher to the page, never to the picture")
        self.assertTrue(all(l.endswith(" cover") for l in shows), shows)
        self.assertIn("launcher        closed", self.status())

    def test_close_of_a_launcher_that_is_not_open_leaves_the_page(self):
        self.start_none()
        n = len(self.tv.lines)
        self.launcher("close")
        self.launcher("close", "keep")
        self.assertIsNotNone(self.tv.shown)
        self.assertEqual(self.shows(n), [])
        r = subprocess.run([BIN, "ctl", "launcher", "1"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("error the launcher is not open"), r.stdout)

    def test_the_signal_back_under_the_launcher_leaves_the_launcher_and_the_wall_open_after_it(self):
        self.start_none()
        self.launcher(line(1))
        n = len(self.tv.lines)
        self.tv.push("note signal 1920x1080p60")
        time.sleep(0.3)
        self.assertIn("launcher        open", self.status())
        self.assertEqual(self.shows(n), [])                    # the launcher stays on the wall
        self.launcher("close")
        self.assertIsNone(self.tv.shown)
        self.assertIn("osd hide", self.tv.lines)

    def test_a_page_of_the_channel_takes_its_place_and_gives_it_back(self):
        self.start_none()
        page = self.shown()
        c = self.page()
        self.assertEqual(c.answer.split()[0], "ok")
        c.paint(0, H, a=255)
        c.show(0, H)
        time.sleep(0.4)
        self.assertEqual(self.shown(), bytes(c.map))
        self.assertIn("no-signal page  wanted, not shown", self.status())
        n = len(self.tv.lines)
        c.close()
        self.clients.remove(c)
        time.sleep(0.4)
        self.assertEqual(self.shown(), page, "its end gives the wall back to the page, not to the picture")
        self.assertNotIn("osd hide", self.shows(n))

    def test_the_hand_over_to_a_page_is_not_broken_by_it(self):
        """launcher "close keep" over the page without a signal, then the settings: no refresh in between, so no page, no hide"""
        self.start_none()
        self.launcher(line(1))
        n = len(self.tv.lines)
        self.launcher("close", "keep", wait=0.2)
        self.assertEqual(self.shows(n), [], "the launcher stays on the wall until the page is drawn")
        c = self.page()
        c.paint(0, H, a=255)
        c.show(0, H)
        time.sleep(0.4)
        shows = self.shows(n)
        self.assertTrue(shows and "osd hide" not in shows and all(l.endswith(" cover") for l in shows), shows)
        self.assertEqual(self.shown(), bytes(c.map))

    def test_the_hand_over_nobody_takes_ends_with_the_page(self):
        self.start_none()
        page = self.shown()
        self.launcher(line(1))
        n = len(self.tv.lines)
        self.launcher("close", "keep", wait=0.3)
        time.sleep(1.0)
        shows = self.shows(n)
        self.assertEqual(self.shown(), page)
        self.assertNotIn("osd hide", shows)

    def test_the_volume_rides_in_the_page_and_comes_off_it(self):
        self.start_none()
        page = self.shown()
        self.ctl("volume", "40")
        with_strip = self.shown()
        self.assertNotEqual(with_strip, page)
        diff = [(x, y) for y in range(H) for x in range(W) if self.px(with_strip, x, y) != self.px(page, x, y)]
        self.assertTrue(diff)
        self.assertTrue(min(y for _, y in diff) > H * 0.7, "the strip is at the foot")
        self.assertTrue(all(self.px(with_strip, x, y)[3] == 255 for y in range(H) for x in range(0, W, 7)), "the page stays opaque")
        time.sleep(0.9)                                         # the strip's seconds (0.6) are over
        self.assertEqual(self.shown(), page, "nothing of the strip is left in the page")

    def test_the_power_countdown_is_shown_in_the_page_though_no_picture_lies_under_it(self):
        """h713-power asks h713-osd before it counts down: "ok unseen" means nobody would see the choice and it acts at once. Under the
        page without a signal the warp's claim is given back, so h713-tv answers "osd picture" with "none" - and the page is on the wall all
        the same: the countdown rides in it like over the launcher (Marco 18.10.2026: "Power key as always, yes")"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        out = self.ctl("power", "100", "standby")
        self.assertEqual(out, "ok\n", "the countdown is wanted, not unseen")
        with_count = self.shown()
        self.assertNotEqual(with_count, page, "the countdown is in the page")
        diff = [(x, y) for y in range(H) for x in range(W) if self.px(with_count, x, y) != self.px(page, x, y)]
        self.assertTrue(diff)
        self.assertTrue(H * 0.25 < min(y for _, y in diff) and max(y for _, y in diff) < H * 0.75, "large, in the middle of the panel")
        self.assertTrue(all(self.px(with_count, x, y)[3] == 255 for y in range(H) for x in range(0, W, 7)), "the page stays opaque")
        self.assertIn("no-signal page  shown", self.status())
        time.sleep(1.0)                                         # each line keeps it one second
        self.assertEqual(self.shown(), page, "nothing of the countdown is left in the page")

    def test_the_power_countdown_is_shown_in_the_launcher_opened_over_no_signal(self):
        """the same question over the launcher that took the page's place: no signal, no claim, "osd picture" says "none" - the launcher is on the wall"""
        self.tv.picture = "none"
        self.start_none()
        self.launcher(line(1))
        lau = self.shown()
        self.assertIn("launcher        open", self.status())
        out = self.ctl("power", "100", "off")
        self.assertEqual(out, "ok\n")
        self.assertNotEqual(self.shown(), lau, "the countdown is in the launcher")

    def open_settings_page(self, alpha):
        """h713-settings' page over the page without a signal (it takes its place): opaque (alpha 255) or a pill (a clear canvas)"""
        c = self.page()
        c.paint(0, H, a=alpha)
        c.show(0, H)
        time.sleep(0.4)
        return c

    def test_the_power_countdown_is_offered_over_an_open_settings_page_without_a_signal(self):
        """the same hole for the page channel: under an open settings page without a signal the claim is back too, "osd picture" says "none",
        the page without a signal is not due (a page of the channel stands) and the launcher is not open - and the page is on the wall. The rule is
        not "which page" but "does anything of ours stand on the wall"; with a signal the answer was "ok" there all along"""
        self.tv.picture = "none"
        self.start_none()
        self.open_settings_page(255)
        self.assertIn("page            open", self.status())
        out = self.ctl("power", "100", "standby")
        self.assertEqual(out, "ok\n")

    def test_the_power_countdown_is_offered_over_the_settings_pill_without_a_signal(self):
        """a page with transparent pixels over no picture is shown with "cover" all the same (over black): it is on the wall"""
        self.tv.picture = "none"
        self.start_none()
        self.open_settings_page(0)
        self.assertIn("transparent pixels", self.status())
        out = self.ctl("power", "100", "off")
        self.assertEqual(out, "ok\n")

    def test_the_power_countdown_is_still_unseen_when_only_a_waiting_strip_stands(self):
        """the control for "shown": a strip on the console is "shown" for h713-osd (the show was accepted) but h713-tv answers "ok waiting" - there is
        no picture to lay it over, nothing is on the wall. That is not a page of ours that is seen"""
        self.tv.picture = "none"
        self.tv.show_reply = b"ok waiting\n"
        self.start()
        time.sleep(0.3)
        self.ctl("volume", "40")
        self.assertIn("channel         claimed, shown", self.status())
        out = self.ctl("power", "100", "standby")
        self.assertEqual(out, "ok unseen\n")

    def test_the_power_countdown_is_still_unseen_on_the_console(self):
        """the control: no page (the console is forced, a program is the mode: h713-tv says "off", not "none") and no picture - nobody sees a
        countdown, h713-power acts at once"""
        self.tv.picture = "none"
        self.start()
        time.sleep(0.3)
        out = self.ctl("power", "100", "standby")
        self.assertEqual(out, "ok unseen\n")
        self.assertIsNone(self.tv.shown)
        self.assertIn("no-signal page  none", self.status())

    # --- the page takes back its symbol and words while the power countdown runs (Marco, 19.10.2026) --------------------------

    def countdown(self, lines=6, alpha="100%", choice="standby"):
        """h713-power's lines: one about every 0.1 s, "power TENTHS standby|off ALPHA%", each keeps the entry a second"""
        for i in range(lines):
            r = subprocess.run([BIN, "ctl", "power", str(100 - i), choice, alpha], env=self.env, capture_output=True, text=True, timeout=5)
            self.assertEqual(r.stdout, "ok\n")
            time.sleep(0.1)

    def inked(self, data, x0, x1, y0=0, y1=H):
        """how many pixels of the box are not the ground"""
        return sum(1 for y in range(y0, y1) for x in range(x0, x1) if self.px(data, x, y) != GROUND)

    def test_the_page_takes_back_its_symbol_and_words_while_the_power_countdown_runs(self):
        """Over the page "No signal on HDMI" the ring lay over the HDMI symbol and the words and crossed them out (Marco 19.10.2026, variant b): the
        page keeps nothing of them while a power entry stands, the ring is alone on the ground as over the launcher. The entry is asked at no
        strength (ALPHA 0%): it stands, and what is on the wall is what the page keeps in its middle band"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        self.assertGreater(self.inked(page, 0, W, H // 3, H * 2 // 3), 300, "the page has its symbol and words")
        self.assertEqual(self.ctl("power", "100", "standby", "0%"), "ok\n")
        quiet = self.shown()
        self.assertTrue(quiet == GROUND * (W * H), "the ground alone: no symbol, no words - from the first line on")
        self.countdown(3, alpha="0%")
        self.assertTrue(self.shown() == quiet, "and it stays so")
        time.sleep(1.1)
        self.assertTrue(self.shown() == page, "the symbol and the words are back")

    def test_the_ring_stands_alone_on_the_ground_as_over_the_launcher(self):
        """the ring is not changed by this: right of the launcher's column (35 % of the panel, the ring starts at 36.4 %) the launcher's
        page is the ground alone, and the ring over it is the same pixels as over the page - while at the left of the ring, where the page's
        title reached out beyond it, there is nothing but the ground"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        x0 = W * 35 // 100
        self.assertGreater(self.inked(page, 0, x0), 0, "the page's title reaches out to the left of the ring")
        self.countdown(3)
        ring = self.shown()
        self.assertTrue(ring != page, "the countdown is on the wall")
        self.assertEqual(self.inked(ring, 0, x0), 0, "nothing of the page's words at the left of the ring")
        self.assertGreater(self.inked(ring, x0, W), 300, "the ring is there")
        time.sleep(1.1)
        self.launcher(line(1))
        self.countdown(3)
        over_launcher = self.shown()
        self.assertTrue([over_launcher[y * PITCH + 4 * x0:(y + 1) * PITCH] for y in range(H)] ==
                        [ring[y * PITCH + 4 * x0:(y + 1) * PITCH] for y in range(H)], "the ring, pixel for pixel, and nothing else right of x0")

    def test_the_page_comes_back_whole_when_the_countdown_runs_out(self):
        """no hole, no stale pixel, and the wall never goes to the picture in between: the page after the countdown is the page drawn fresh"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        n = len(self.tv.lines)
        for _ in range(2):                                      # twice: both buffers have been the one on the wall
            self.countdown(6)
            self.assertTrue(self.shown() != page, "the countdown is on the wall")
            self.assertEqual(self.inked(self.shown(), 0, W * 35 // 100), 0, "no word of the page at the left of the ring")
            time.sleep(1.2)                                     # the last line's second is over
            self.assertTrue(self.shown() == page, "the page, the same pixels")
        shows = self.shows(n)
        self.assertNotIn("osd hide", shows)
        self.assertTrue(all(l.endswith(" cover") for l in shows), shows)

    def test_the_page_comes_back_whole_when_the_countdown_is_cancelled(self):
        """h713-power ends a cancelled countdown with two fading lines and "hide" (Countdown.close)"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        n = len(self.tv.lines)
        self.countdown(6)
        self.assertEqual(self.inked(self.shown(), 0, W * 35 // 100), 0, "no word of the page at the left of the ring")
        for a in ("60%", "30%"):
            subprocess.run([BIN, "ctl", "power", "50", "standby", a], env=self.env, capture_output=True, text=True, timeout=5)
            time.sleep(0.06)
        self.assertEqual(self.ctl("hide"), "ok hidden\n")
        self.assertTrue(self.shown() == page, "the page, the same pixels, at once")
        shows = self.shows(n)
        self.assertNotIn("osd hide", shows)
        self.assertTrue(all(l.endswith(" cover") for l in shows), shows)

    def test_a_volume_strip_in_the_countdown_does_not_leave_the_page_without_its_words_afterwards(self):
        """the strip replaces the power entry as the overlay of the moment: the words come back with it, and go with the strip's end"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        self.countdown(3)
        self.ctl("volume", "40")
        strip = self.shown()
        self.assertTrue(strip != page, "the strip is on the wall")
        self.assertTrue(strip[:H * 7 // 10 * PITCH] == page[:H * 7 // 10 * PITCH], "the page's words are back, the strip is at the foot")
        time.sleep(0.9)
        self.assertTrue(self.shown() == page, "the page, the same pixels")

    def test_over_a_keystone_the_page_after_the_countdown_is_the_page_drawn_fresh(self):
        """the same through the matrix (test_wall.py has the strong keystones at the box's panel): the band that changes twice is put with its
        neighbours' rows around it, and the page stays opaque over the whole of it, in the countdown and after it. The entry at no strength
        shows what the page keeps in its band: not what the page showed before"""
        self.write("warp.conf", "bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        self.assertEqual(self.px(page, W // 2, H // 2)[3], 255)
        for alpha in ("100%", "0%"):
            for _ in range(2):
                self.countdown(6, alpha=alpha)
                during = self.shown()
                self.assertTrue(during != page, "the countdown is on the wall (%s)" % alpha)
                self.assertEqual(during[3::4].count(255), page[3::4].count(255), "no pixel of the page is lost to the ring")
                time.sleep(1.2)
                self.assertTrue(self.shown() == page, "the page put whole")

    def test_the_launcher_opened_over_no_signal_is_not_changed_by_the_countdown(self):
        """only the page without a signal gives up its middle band: the launcher's rows stay"""
        self.tv.picture = "none"
        self.start_none()
        self.launcher(line(1))
        lau = self.shown()
        self.countdown(3)
        x0 = W * 35 // 100                                      # (the ring starts at 36.4 %)
        self.assertEqual(self.inked(self.shown(), 0, x0), self.inked(lau, 0, x0), "the column is as it was")
        time.sleep(1.1)
        self.assertTrue(self.shown() == lau, "the launcher, the same pixels")

    def test_the_page_that_opens_while_the_countdown_stands_is_quiet_from_its_first_picture(self):
        """the launcher closes under a standing countdown and the page without a signal takes its place (the entry has most of its second to
        go): its first picture is drawn without the words, and they come when the entry ends. The flag is compared at every drawing, so what
        an earlier page left of it does not matter"""
        self.tv.picture = "none"
        self.start_none()
        page = self.shown()
        self.launcher(line(1))
        self.countdown(3)
        self.launcher("close", wait=0.3)
        quiet = self.shown()
        self.assertEqual(self.inked(quiet, 0, W * 35 // 100), 0, "no word of the page at the left of the ring")
        self.assertGreater(self.inked(quiet, W * 35 // 100, W), 300, "the ring is still there")
        self.assertIn("no-signal page  shown", self.status())
        time.sleep(1.1)
        self.assertTrue(self.shown() == page, "the page, the same pixels")

    def test_a_note_between_the_question_and_its_answer_is_taken(self):
        """h713-tv's note comes in the same write as the answer to "osd picture": the page opens, the volume rides in it"""
        self.start()
        time.sleep(0.3)
        self.tv.pre_note = "note signal none"
        self.ctl("volume", "40")                                # (0.15 s later: the strip stays 0.6 s)
        data = self.shown()
        self.assertIn("no-signal page  shown", self.status())
        top = all(self.px(data, x, y) == GROUND for y in range(H // 4) for x in range(W))
        self.assertTrue(top)
        self.assertTrue(any(self.px(data, x, y) != GROUND for y in range(int(H * 0.8), H) for x in range(W)), "the strip rides in it")

    def test_a_note_right_behind_the_answer_is_taken_too(self):
        """h713-tv sends the answer to "osd show" and, a tenth of a millisecond later, the note: one read can hold both. poll() does not fire
        again for bytes already out of the socket, so a note left lying there waited for the next key - "none": no page; a word "signal": the page
        stayed over a signal"""
        self.start()
        time.sleep(0.3)
        self.tv.post_note = "note signal none"
        self.ctl("volume", "40")                                # (0.15 s later: the strip stays 0.6 s)
        self.assertIn("no-signal page  shown", self.status(), "the page, without another event")
        self.tv.shown = None
        time.sleep(0.8)                                         # the strip's seconds are over; the page stands on
        self.assertIsNotNone(self.tv.shown)
        self.tv.post_note = "note signal 1920x1080p60"
        self.ctl("volume", "41")
        self.assertIn("no-signal page  none", self.status(), "the word signal, behind the answer, takes the page away without another event")
        time.sleep(0.8)
        self.assertIsNone(self.tv.shown)

    def test_it_is_pre_distorted_over_a_keystone(self):
        self.write("warp.conf", "bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.tv.picture = "none"
        self.start_none()
        data = self.shown()
        self.assertIsNotNone(data)
        self.assertEqual(self.px(data, 2, H - 2)[3], 0, "the corner the keystone pulls in is clear")
        self.assertEqual(self.px(data, W // 2, H // 2)[3], 255)
        for y in (H // 3, H // 2, H - 40):                      # opaque along the rows inside the keystone's edges
            alpha = bytes(self.px(data, x, y)[3] for x in range(W))
            xs = [x for x in range(W) if alpha[x]]
            self.assertTrue(xs, "nothing at row %d" % y)
            inner = alpha[xs[0] + 3:xs[-1] - 2]
            self.assertEqual(inner.count(255), len(inner), "row %d: alpha %s across the page" % (y, sorted(set(inner))))

    def test_it_comes_back_after_h713_tv_was_gone(self):
        self.start_none()
        self.assertEqual(self.tv.lines.count("osd claim"), 1)
        self.tv.hangup()                                        # h713-tv restarts (a standby): the new one is asked again
        self.tv.shown = None
        time.sleep(2.0)
        self.assertEqual(self.tv.lines.count("osd claim"), 2)
        self.assertEqual(self.tv.lines.count("osd signal"), 2)
        self.assertIsNotNone(self.tv.shown, "the page is back without any event")

    def test_a_h713_tv_that_says_signal_after_a_restart_leaves_the_wall_alone(self):
        self.start_none()
        self.tv.signal = "1920x1080p60"
        self.tv.hangup()
        self.tv.shown = None
        time.sleep(2.0)
        self.assertEqual(self.tv.lines.count("osd signal"), 2)
        self.assertIsNone(self.tv.shown)
        self.assertIn("no-signal page  none", self.status())

    def test_an_h713_tv_of_before_that_does_not_know_the_question_means_a_signal(self):
        self.tv.knows_signal = False
        self.tv.signal = "none"
        self.start()
        time.sleep(0.5)
        self.assertIsNone(self.tv.shown)
        self.assertIn("no-signal page  none", self.status())

    def test_it_claims_when_h713_tv_comes_up_after_it(self):
        """a restart of both (an update, a boot): h713-osd is up first, h713-tv a moment later - no event is needed for the page"""
        self.tv.stop()                                          # h713-tv is not there yet
        self.start()
        time.sleep(0.3)
        self.tv = FakeTv(self.env["H713_OSD_TV"])
        self.tv.signal = "none"
        self.tv.start()
        time.sleep(2.5)                                         # the claim is tried every second
        self.assertEqual(self.tv.lines.count("osd claim"), 1)
        self.assertIsNotNone(self.tv.shown, "the page stands without any event")

    def test_status_names_the_word(self):
        self.start_none()
        self.assertIn("no-signal page  shown (h713-tv: no signal)", self.status())
