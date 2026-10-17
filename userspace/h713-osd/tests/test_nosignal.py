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
