"""Host tests for h713-osd: a fake h713-tv on a Unix socket that hands over two memfds instead of dma-bufs,
answers "osd picture" as told, and keeps what the daemon shows. The overlay's place is read from the buffer:
the rectangle of the pixels with alpha.

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
"""

import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "h713-osd")
W, H = 640, 360
PITCH = W * 4


class FakeTv(threading.Thread):
    """h713-tv's overlay channel: claim, picture, show N, hide, release."""

    def __init__(self, path, picture="ring"):
        super().__init__(daemon=True)
        self.path, self.picture, self.mute = path, picture, "off"
        self.lines, self.shown, self.conn = [], None, None
        self.bufs = []
        for i in range(2):
            fd = os.memfd_create("osd%d" % i)
            os.ftruncate(fd, PITCH * H)
            self.bufs.append(fd)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(4)

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conn = c
            try:
                self.serve(c)
            except OSError:
                pass                            # stopped under a connection
            c.close()

    def serve(self, c):
        while True:
            data = c.recv(256)
            if not data:
                return
            for line in data.decode().splitlines():
                self.lines.append(line)
                if line == "osd claim":
                    socket.send_fds(c, [b"ok %d %d %d argb8888\n" % (W, H, PITCH)], self.bufs)
                elif line == "osd picture":
                    c.sendall(("ok %s\n" % self.picture).encode())
                elif line.startswith("osd show "):
                    self.shown = int(line.split()[2])
                    c.sendall(b"ok\n")
                elif line == "mute":
                    c.sendall(("ok mute %s (DSP)\n" % self.mute).encode())
                elif line == "osd hide":
                    self.shown = None
                    c.sendall(b"ok\n")
                else:
                    c.sendall(b"ok\n")

    def stop(self):
        if self.conn:
            self.conn.close()
        self.sock.close()
        os.unlink(self.path)

    def bbox(self):
        """The rectangle of the shown buffer's pixels with alpha, (x0, y0, x1, y1), or None."""
        if self.shown is None:
            return None
        data = os.pread(self.bufs[self.shown], PITCH * H, 0)
        box = None
        for y in range(H):
            alpha = data[y * PITCH:(y + 1) * PITCH][3::4]
            if alpha.count(0) == W:
                continue
            x0 = W - len(alpha.lstrip(b"\0"))
            x1 = len(alpha.rstrip(b"\0")) - 1
            box = (x0, y, x1, y) if box is None else (min(box[0], x0), box[1], max(box[2], x1), y)
        return box


class OsdBase(unittest.TestCase):
    """the daemon, the fake h713-tv, the helpers (test_launcher.py builds on it)"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.env = dict(os.environ, H713_OSD_SOCKET=os.path.join(d, "osd.sock"), H713_OSD_TV=os.path.join(d, "tv.sock"),
                        H713_OSD_WARP_CONF=os.path.join(d, "warp.conf"), H713_OSD_CONF=os.path.join(d, "osd.conf"))
        self.write("osd.conf", "seconds = 0.6\n")
        self.tv = FakeTv(self.env["H713_OSD_TV"])
        self.tv.start()
        self.osd = None

    def tearDown(self):
        if self.osd:
            self.osd.terminate()
            self.osd.wait(5)
            self.osd.stderr.close()
        self.tv.stop()
        self.tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self.tmp.name, name), "w") as f:
            f.write(text)

    def start(self):
        self.osd = subprocess.Popen([BIN, "run"], env=self.env, stderr=subprocess.PIPE)
        for _ in range(100):
            if os.path.exists(self.env["H713_OSD_SOCKET"]):
                return
            time.sleep(0.02)
        self.fail("h713-osd did not come up")

    def mute(self, state, volume="40"):
        """as h713-keys does it: h713-tv first, then the overlay"""
        self.tv.mute = state
        return self.ctl("mute", state, volume)

    def ctl(self, *words):
        r = subprocess.run([BIN, "ctl"] + list(words), env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout + r.stderr)
        time.sleep(0.15)
        return r.stdout


class OsdTest(OsdBase):
    def test_volume_bottom_centre(self):
        self.start()
        self.ctl("volume", "40")
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(abs((x0 + x1) / 2 - W / 2) < 3, (x0, x1))       # centred
        self.assertTrue(290 < y0 and y1 < 340, (y0, y1))                 # above the lower edge (u = 1/3)
        self.assertIn("osd picture", self.tv.lines)

    def test_overlay_goes_after_its_seconds(self):
        self.start()
        self.ctl("focus", "up")
        self.assertIsNotNone(self.tv.bbox())
        time.sleep(0.8)
        self.assertIsNone(self.tv.shown)
        self.assertIn("osd hide", self.tv.lines)

    def test_mute_badge_stays_and_goes(self):
        self.start()
        self.mute("on")
        time.sleep(0.8)                                                  # the overlay is gone, the badge is not
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(x0 > W * 0.85 and y1 < H * 0.2, (x0, y0, x1, y1))
        self.mute("off")
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(y0 > H * 0.7, (x0, y0, x1, y1))                  # the volume, no badge any more

    def test_keystone_pre_distorts_over_the_warp(self):
        self.write("warp.conf", "bl_x = 150\nbl_y = 200\nbr_x = 150\nbr_y = 200\nwarp = on\n")
        self.tv.picture = "warped"
        self.start()
        self.ctl("volume", "40")
        warped = self.tv.bbox()
        self.tv.picture = "ring"
        self.ctl("volume", "41")
        straight = self.tv.bbox()
        self.assertLess(warped[1], straight[1] - 20)                     # the pulled-in bottom carries it up
        self.assertLess(warped[2] - warped[0], straight[2] - straight[0])    # and narrower

    def test_keystone_follows_warp_conf(self):
        self.tv.picture = "warped"
        self.start()
        self.mute("on")
        time.sleep(0.8)
        before = self.tv.bbox()
        self.write("warp.conf.new", "tr_x = 200\ntr_y = 300\nwarp = on\n")
        os.rename(os.path.join(self.tmp.name, "warp.conf.new"), os.path.join(self.tmp.name, "warp.conf"))
        time.sleep(0.3)
        after = self.tv.bbox()
        self.assertLess(after[2], before[2] - 30)                        # the badge moved in with the corner
        self.assertGreater(after[1], before[1] + 30)

    def test_rear_mode_mirrors(self):
        self.write("warp.conf", "mode = rear\nwarp = on\n")
        self.tv.picture = "warped"
        self.start()
        self.mute("on")
        time.sleep(0.8)
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertLess(x1, W * 0.15, (x0, x1))                           # top right on the wall = top left on the panel

    def test_badge_follows_the_picture_under_it(self):
        """11.10., G-EU: the signal came back over the ring, the warp took over a second later - the badge drawn
        for the ring stayed straight over the warped picture. Now it is drawn again when the picture changes."""
        self.write("warp.conf", "tr_x = 200\ntr_y = 300\nwarp = on\n")
        self.tv.picture = "none"                                         # no signal: the badge waits
        self.start()
        self.mute("on")
        self.tv.picture = "ring"                                         # the signal back, not warped yet
        time.sleep(0.8)
        straight = self.tv.bbox()
        self.tv.picture = "warped"                                       # the warp takes over
        time.sleep(0.5)
        warped = self.tv.bbox()
        self.assertLess(warped[2], straight[2] - 30)                     # moved in with the corner, without a key
        self.assertGreater(warped[1], straight[1] + 30)
        self.tv.picture = "ring"                                         # the warp switched off
        time.sleep(0.5)
        self.assertEqual(self.tv.bbox(), straight)

    def test_no_questions_without_a_keystone(self):
        self.tv.picture = "warped"
        self.start()
        self.mute("on")
        time.sleep(0.9)                                                  # after the overlay's own end (0.6 s)
        asked = self.tv.lines.count("osd picture")
        time.sleep(1.0)
        self.assertEqual(self.tv.lines.count("osd picture"), asked)     # identity: nothing to follow, nothing asked

    def test_claims_again_after_h713_tv_restarts(self):
        self.start()
        self.mute("on")
        self.tv.stop()
        time.sleep(0.2)
        self.tv = FakeTv(self.env["H713_OSD_TV"])
        self.tv.mute = "on"                                              # h713-tv comes back muted (saved)
        self.tv.start()
        time.sleep(1.6)                                                  # the retry, once a second
        self.assertIn("osd claim", self.tv.lines)
        self.assertIsNotNone(self.tv.bbox())                             # the badge is back without a key

    def test_badge_from_h713_tv_at_the_start(self):
        self.tv.mute = "on"                                              # muted before h713-osd starts
        self.start()
        time.sleep(0.5)
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(x0 > W * 0.85 and y1 < H * 0.2, (x0, y0, x1, y1))

    def test_status_and_errors(self):
        self.start()
        out = self.ctl("status")
        self.assertIn("place bottom, look pill", out)
        r = subprocess.run([BIN, "ctl", "volume"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("error"))


if __name__ == "__main__":
    unittest.main()
