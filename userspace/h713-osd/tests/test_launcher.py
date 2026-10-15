"""Host tests for the launcher in h713-osd (package H): the fake h713-tv of test_osd.py, the real daemon, a font. What is
checked is read from the buffer the fake keeps: where the column is, that a move of the selection repaints to exactly what
a fresh draw shows (straight and through a keystone), that there is no seam between two bands after the pre-distortion,
that a closed launcher leaves nothing in the buffers, that a volume strip and the launcher live together.

The font is OSD_TEST_FONT, else the image's path; without one the tests are skipped.

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
"""

import os
import subprocess
import time
import unittest

from test_osd import BIN, H, OsdBase, PITCH, W

FONT = os.environ.get("OSD_TEST_FONT", "/usr/share/fonts/truetype/quicksand/Quicksand-Medium.ttf")
ROWS = "hdmi:HDMI input;film:Kodi;>power:Standby"
COLUMN = int(700 * H / 1080 + 0.999)        # the scrim's width at this canvas height


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

    def shown(self):
        """alpha of every pixel of the buffer on the panel, rows of W bytes (None when nothing is shown)"""
        if self.tv.shown is None:
            return None
        data = os.pread(self.tv.bufs[self.tv.shown], PITCH * H, 0)
        return [data[y * PITCH:(y + 1) * PITCH] for y in range(H)]

    def test_open_stays_and_fills_the_column(self):
        self.start()
        self.launcher(line(1))
        time.sleep(1.0)                                  # popups would be gone after 0.6 s: the launcher stays
        rows = self.shown()
        self.assertIsNotNone(rows)
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertEqual((x0, y0, y1), (0, 0, H - 1))    # the scrim from the top edge to the bottom edge
        self.assertTrue(COLUMN - 3 <= x1 <= COLUMN, x1)  # and nothing right of the column (u = 1/3)
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

    def test_move_through_a_keystone_and_no_seam(self):
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
        # Along a column inside the warped scrim the alpha rises by a level or two per row, and nowhere dips: a seam between
        # two bands (their pre-distortion sampling the transparent nothing outside its region) was a dip to 60 % on one
        # row at every band boundary. The column's own end (the keystone's slanted lower edge) is cut off the check.
        rows = self.shown()
        x = 20
        a = [r[4 * x + 3] for r in rows]
        inside = [i for i in range(1, H - 1) if a[i - 1] and a[i] and a[i + 1]]
        self.assertGreater(len(inside), 60)
        worst = max(abs(a[i + 1] - a[i]) for i in inside[4:-8])
        self.assertLess(worst, 6, "alpha along x = %d jumps by %d" % (x, worst))

    def test_close_leaves_nothing(self):
        self.start()
        self.launcher(line(1))
        self.launcher("close")
        self.assertIsNone(self.tv.shown)
        self.assertIn("osd hide", self.tv.lines)
        self.ctl("volume", "40")                         # the next overlay lands in a buffer that held the launcher
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(x0 > 150 and y0 > H * 0.7, (x0, y0, x1, y1))     # only the strip: nothing of the column is left

    def test_volume_over_the_launcher(self):
        self.start()
        self.launcher(line(1))
        self.ctl("volume", "40")
        rows = self.shown()
        self.assertEqual(self.tv.bbox()[0], 0)           # the column is still there
        strip = [i for i in range(H) if any(rows[i][4 * x + 3] for x in range(COLUMN + 20, W - 20))]
        self.assertTrue(strip and min(strip) > H * 0.7, strip[:3])        # and the volume strip at the foot
        time.sleep(0.8)
        self.assertEqual(self.tv.bbox()[0], 0)           # the strip went (0.6 s), the launcher stays
        rows = self.shown()
        self.assertFalse([i for i in range(H) if any(rows[i][4 * x + 3] for x in range(COLUMN + 20, W - 20))])

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
