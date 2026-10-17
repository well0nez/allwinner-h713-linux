"""Host tests of the hand-over between two opaque pages (P2c of the media side project): the page that goes says so - "page
handover" before its connection ends (h713-settings on Back), "launcher close keep" (h713-keys on OK on a page's entry) - and stays
on the wall until its successor is shown in its place, at most a second; without the word it goes at once, as before.
The fake h713-tv of test_osd.py records what the daemon says: between the two pages there must be no "osd hide".

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
"""

import os
import subprocess
import time
import unittest

from test_osd import BIN, H, PITCH, W
from test_page import PageBase
from test_launcher import FONT, ROWS


def line(sel, now="HDMI 1080p60", rows=ROWS):
    return "%d;%s;%s" % (sel, now, rows)


@unittest.skipUnless(os.path.exists(FONT), "no font at %s (set OSD_TEST_FONT)" % FONT)
class HandoverTest(PageBase):
    def setUp(self):
        super().setUp()
        self.env.update(H713_OSD_FONT=FONT, H713_OSD_CLOCK="20:47")

    def launcher(self, *words, wait=0.4):
        r = subprocess.run([BIN, "ctl", "launcher"] + list(words), env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout + r.stderr)
        time.sleep(wait)
        return r.stdout

    def lines_since(self, n):
        return [l for l in self.tv.lines[n:] if l.startswith("osd show") or l == "osd hide"]

    def opaque_page(self):
        c = self.page()
        c.paint(0, H, a=255)
        c.show(0, H)
        time.sleep(0.4)             # a whole page is put into the other buffer right after the answer, and shown (test_page)
        return c

    def test_a_page_hands_over_to_the_launcher_without_a_hide(self):
        self.start()
        c = self.opaque_page()
        page = self.shown()
        n = len(self.tv.lines)
        c.sock.sendall(b"page handover\n")
        c.close()
        self.clients.remove(c)
        time.sleep(0.2)
        self.assertEqual(self.lines_since(n), [], "the handed-over page stays on the wall")
        self.assertEqual(self.shown(), page)
        self.assertIn("handed over", self.ctl("status"))
        self.launcher(line(1))
        shows = self.lines_since(n)
        self.assertNotIn("osd hide", shows)
        self.assertTrue(shows and shows[-1].startswith("osd show") and shows[-1].endswith(" cover"), shows)
        self.assertNotEqual(self.shown(), page, "the launcher is on the wall now")

    def test_a_hand_over_nobody_takes_ends_after_a_second(self):
        self.start()
        c = self.opaque_page()
        n = len(self.tv.lines)
        c.sock.sendall(b"page handover\n")
        c.close()
        self.clients.remove(c)
        time.sleep(0.5)
        self.assertEqual(self.lines_since(n), [])
        time.sleep(0.9)
        self.assertEqual(self.lines_since(n), ["osd hide"])

    def test_without_the_word_the_page_goes_at_once(self):
        """the control: a page that just ends (Home, Power, a crash) takes its picture away at once"""
        self.start()
        c = self.opaque_page()
        n = len(self.tv.lines)
        c.close()
        self.clients.remove(c)
        time.sleep(0.3)
        self.assertEqual(self.lines_since(n), ["osd hide"])

    def test_the_launcher_hands_over_to_a_page(self):
        self.start()
        self.launcher(line(1))
        lau = self.shown()
        n = len(self.tv.lines)
        self.launcher("close", "keep", wait=0.2)
        self.assertEqual(self.lines_since(n), [], "the launcher stays until the page is drawn")
        self.assertEqual(self.shown(), lau)
        c = self.opaque_page()
        shows = self.lines_since(n)
        self.assertTrue(shows and "osd hide" not in shows and all(l.endswith(" cover") for l in shows), shows)
        self.assertEqual(self.shown(), bytes(c.map))

    def test_a_launcher_hand_over_nobody_takes_ends_after_a_second(self):
        self.start()
        self.launcher(line(1))
        n = len(self.tv.lines)
        self.launcher("close", "keep", wait=0.5)
        self.assertEqual(self.lines_since(n), [])
        time.sleep(0.9)
        self.assertEqual(self.lines_since(n), ["osd hide"])

    def test_launcher_close_alone_still_hides_at_once(self):
        self.start()
        self.launcher(line(1))
        n = len(self.tv.lines)
        self.launcher("close", wait=0.3)
        self.assertEqual(self.lines_since(n), ["osd hide"])
