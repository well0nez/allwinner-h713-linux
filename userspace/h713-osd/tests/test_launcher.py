"""Host tests for the launcher in h713-osd (package H): the fake h713-tv of test_osd.py, the real daemon, a font. What is checked is
read from the buffer the fake keeps: that the page is OPAQUE over the whole panel (Marco, 15.10.2026: a launcher must have a ground)
and nothing but the ground lies in the outer 5 %, that a move of the selection repaints to exactly what a fresh draw shows (straight
and through a keystone), that there is no seam in the opaque page after the pre-distortion, that the idle time fills the buffer that
is not shown, that the volume strip rides in the page and comes off it, that a closed launcher leaves nothing in the buffers.

The font is OSD_TEST_FONT, else the image's path; without one the tests are skipped.

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
"""

import os
import re
import subprocess
import time
import unittest

from test_osd import BIN, H, OsdBase, PITCH, W

FONT = os.environ.get("OSD_TEST_FONT", "/usr/share/fonts/truetype/quicksand/Quicksand-Medium.ttf")
ROWS = "hdmi:HDMI input;film:Kodi;>power:Standby"
COLUMN = int(700 * H / 1080 + 0.999)        # the column's width at this canvas height
GROUND = bytes([0x0d, 0x0e, 0x0b, 0xff])    # 0xff0b0e0d as the buffer holds it: B, G, R, A
SX0, SX1, SY0, SY1 = W * 5 // 100, W - W * 5 // 100, H * 5 // 100, H - H * 5 // 100


def line(sel, now="HDMI 1080p60", rows=ROWS):
    return "%d;%s;%s" % (sel, now, rows)


@unittest.skipUnless(os.path.exists(FONT), "no font at %s (set OSD_TEST_FONT)" % FONT)
class LauncherTest(OsdBase):
    def setUp(self):
        super().setUp()
        self.env.update(H713_OSD_FONT=FONT, H713_OSD_CLOCK="20:47")

    def launcher(self, *words, wait=0.4):
        r = subprocess.run([BIN, "ctl", "launcher"] + list(words), env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout + r.stderr)
        time.sleep(wait)
        return r.stdout

    def buf(self, n):
        data = os.pread(self.tv.bufs[n], PITCH * H, 0)
        return [data[y * PITCH:(y + 1) * PITCH] for y in range(H)]

    def shown(self):
        """the buffer on the panel, rows of PITCH bytes (None when nothing is shown)"""
        return None if self.tv.shown is None else self.buf(self.tv.shown)

    def test_open_is_an_opaque_page_inside_the_safe_margin(self):
        self.start()
        self.launcher(line(1))
        time.sleep(1.0)                                  # popups would be gone after 0.6 s: the launcher stays
        rows = self.shown()
        self.assertIsNotNone(rows)
        self.assertEqual(self.tv.bbox(), (0, 0, W - 1, H - 1))                 # the page covers the whole panel
        clear = ink = outside = 0
        for y, r in enumerate(rows):
            for x in range(W):
                px = r[4 * x:4 * x + 4]
                clear += px[3] != 255
                if px != GROUND:
                    ink += 1
                    outside += not (SX0 <= x < SX1 and SY0 <= y < SY1)
        self.assertEqual(clear, 0, "pixels that are not opaque")
        self.assertEqual(outside, 0, "pixels of ink in the outer 5 %")
        self.assertGreater(ink, W * H // 200)                                  # and something is drawn
        self.assertIn("launcher        open", self.ctl("status"))

    def test_move_is_what_a_fresh_draw_shows(self):
        self.start()
        self.launcher(line(1))
        for sel in (2, 0, 1, 2):                         # both buffers, several moves: each must equal a fresh open
            self.launcher(str(sel))
            moved = self.shown()
            self.launcher("close")
            self.launcher(line(sel))
            self.assertEqual(self.shown(), moved, "after a move to %d" % sel)

    def test_the_idle_time_fills_the_buffer_that_is_not_shown(self):
        """an opaque page over a keystone is two million pixels through the matrix: the next key must not pay for it"""
        self.start()
        self.launcher(line(1), wait=0.6)
        other = 1 - self.tv.shown
        rows = self.buf(other)
        self.assertEqual(rows, self.buf(self.tv.shown), "the buffer that is not shown holds the same page")
        self.assertEqual(sum(r[3::4].count(255) for r in rows), W * H)

    def test_a_page_through_a_keystone_is_opaque_and_has_no_seam(self):
        self.write("warp.conf", "bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.tv.picture = "warped"
        self.start()
        self.launcher(line(0))
        for sel in (1, 2, 0):
            self.launcher(str(sel))
            moved = self.shown()
            self.launcher("close")
            self.launcher(line(sel))
            self.assertEqual(self.shown(), moved, "through the matrix, after a move to %d" % sel)
        # Inside the warped page every pixel is opaque: a seam between two tiles (their pre-distortion sampling the transparent nothing
        # outside its region) was a dip to 55 % on a line at every boundary - between the rows' bands and between the column and the
        # right part. The page's own edge (the keystone's slanted sides) is cut off the check: three pixels either side.
        rows = self.shown()
        for y in (H // 3, H // 2, H - 40):               # along rows, across the boundary of the column
            a = [r for r in [rows[y][3::4]]][0]
            xs = [x for x in range(W) if a[x]]
            self.assertTrue(xs, "nothing at row %d" % y)
            inner = a[xs[0] + 3:xs[-1] - 2]
            self.assertEqual(inner.count(255), len(inner), "row %d: alpha %s across the page" % (y, sorted(set(inner))))
        for x in (150, COLUMN + 3, COLUMN + 100, W // 2):  # along columns, across the rows' bands (not near the slanted left side)
            a = bytes(rows[y][4 * x + 3] for y in range(H))
            ys = [y for y in range(H) if a[y]]
            self.assertTrue(ys, "nothing at column %d" % x)
            inner = a[ys[0] + 3:ys[-1] - 2]
            self.assertEqual(inner.count(255), len(inner), "column %d: alpha %s down the page" % (x, sorted(set(inner))))

    def test_a_move_puts_two_tiles_not_the_page(self):
        """the point of the tiles: once both buffers are filled, a move costs two row tiles of the column. (A wipe flag that stayed
        set after the first put made the third refresh wipe the buffer and put everything again.)"""
        self.start()
        self.launcher(line(0))
        page = W * H
        for sel in (1, 2, 1, 0, 1, 2):
            self.launcher(str(sel))
            m = re.search(r"\((\d+) pixels\)", self.ctl("status"))
            self.assertIsNotNone(m)
            self.assertLess(int(m.group(1)), page * 0.2, "after a move to %d: %s pixels of the page's %d" % (sel, m.group(1), page))

    def test_close_leaves_nothing(self):
        self.start()
        self.launcher(line(1))
        self.launcher("close")
        self.assertIsNone(self.tv.shown)
        self.assertIn("osd hide", self.tv.lines)
        self.ctl("volume", "40")                         # the next overlay lands in a buffer that held the page
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(x0 > 150 and y0 > H * 0.7, (x0, y0, x1, y1))     # only the strip: nothing of the page is left, no ground under it
        rows = self.shown()
        self.assertFalse([1 for r in rows for x in range(W) if r[4 * x:4 * x + 4] == GROUND])

    def test_volume_rides_in_the_page_and_comes_off_it(self):
        self.start()
        self.launcher(line(1))
        page = self.shown()
        self.ctl("volume", "40")
        rows = self.shown()
        self.assertEqual(self.tv.bbox(), (0, 0, W - 1, H - 1))           # still the page, nothing transparent
        strip = [y for y in range(H) for x in range(COLUMN + 20, W - 20) if rows[y][4 * x:4 * x + 4] != GROUND]
        self.assertTrue(strip and min(strip) > H * 0.7, strip[:3])       # the volume strip at the foot, over the ground
        self.assertGreater(len([1 for y in range(H) for x in range(W) if rows[y][4 * x:4 * x + 4] != page[y][4 * x:4 * x + 4]]), 200)
        time.sleep(0.9)                                  # the strip went (0.6 s): the ground is back, exactly
        self.assertEqual(self.shown(), page, "the page after the strip is the page before it")
        self.assertEqual(self.tv.bbox(), (0, 0, W - 1, H - 1))

    def test_no_picture_no_launcher(self):
        self.tv.picture = "none"
        self.start()
        out = self.launcher(line(1))
        self.assertTrue(out.startswith("ok unseen"), out)
        self.assertIn("launcher        closed", self.ctl("status"))
        r = subprocess.run([BIN, "ctl", "launcher", "2"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("error"), r.stdout)   # a move needs an open launcher

    def test_bad_lines(self):
        self.start()
        for bad in (line(0, rows="hdmi:HDMI input;nope:Kodi"), line(0, rows=";".join(["hdmi:x"] * 7)),
                    line(0, rows=">power:Standby;hdmi:HDMI input"), line(0, rows="hdmi HDMI input"), "x;y"):
            r = subprocess.run([BIN, "ctl", "launcher", bad], env=self.env, capture_output=True, text=True, timeout=5)
            self.assertTrue(r.stdout.startswith("error"), (bad, r.stdout))
        self.assertIn("launcher        closed", self.ctl("status"))

    def test_a_missing_font_is_an_error_not_a_crash(self):
        self.env["H713_OSD_FONT"] = "/nonexistent/font.ttf"
        self.start()
        r = subprocess.run([BIN, "ctl", "launcher", line(1)], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("error no font"), r.stdout)
        self.ctl("volume", "40")                         # the daemon lives on


if __name__ == "__main__":
    unittest.main()
