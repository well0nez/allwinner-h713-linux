"""Host tests for the page channel of h713-osd (package S): the fake h713-tv of test_osd.py, the real daemon, and a client that
does what h713-settings does - "page open", draw into the memfd, "page show X Y W H". What is checked is read from the buffer
the fake keeps: that the page is in it, that a partial show leaves exactly what a fresh page shows (straight and through a
keystone, in both buffers), that popups stay off the page, that a page that cannot be seen is not opened and that its end
takes it from the wall.

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
"""

import mmap
import os
import socket
import struct
import subprocess
import time
import unittest

from test_osd import BIN, H, OsdBase, PITCH, W

FONT = os.environ.get("OSD_TEST_FONT", "/usr/share/fonts/truetype/quicksand/Quicksand-Medium.ttf")


def pixel(x, y, a=128):
    """a page with something in every pixel: alpha a, red by the row, green by the column"""
    return struct.pack("<BBBB", (x * 5 + y) % 256, x % 256, y % 256, a)


class Client:
    """h713-settings' side: a connection that stays, one memfd to draw into"""

    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(path)
        self.sock.sendall(b"page open\n")
        msg, fds, _, _ = socket.recv_fds(self.sock, 128, 1)
        self.answer = msg.decode()
        self.fd = fds[0] if fds else None
        self.map = mmap.mmap(self.fd, PITCH * H) if self.fd is not None else None

    def paint(self, y0, y1, a=128, shift=0):
        for y in range(y0, y1):
            self.map[y * PITCH:(y + 1) * PITCH] = b"".join(pixel(x + shift, y, a) for x in range(W))

    def show(self, y, h):
        self.sock.sendall(b"page show 0 %d %d %d\n" % (y, W, h))
        return self.sock.recv(64).decode()

    def close(self):
        self.sock.close()


class PageBase(OsdBase):
    def setUp(self):
        super().setUp()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        super().tearDown()

    def page(self):
        c = Client(self.env["H713_OSD_SOCKET"])
        self.clients.append(c)
        return c

    def shown(self):
        return None if self.tv.shown is None else os.pread(self.tv.bufs[self.tv.shown], PITCH * H, 0)


class PageTest(PageBase):
    def test_open_answers_with_the_size_and_a_canvas(self):
        self.start()
        c = self.page()
        self.assertEqual(c.answer, "ok %d %d %d argb8888\n" % (W, H, PITCH))
        self.assertIsNotNone(c.map)
        self.assertEqual(len(c.map), PITCH * H)
        self.assertIn("page            open", self.ctl("status"))

    def test_the_page_is_in_the_buffer(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        self.assertEqual(c.show(0, H), "ok\n")
        self.assertEqual(self.shown(), bytes(c.map))
        self.assertIn("osd picture", self.tv.lines)

    def test_a_partial_show_is_what_a_fresh_page_shows(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        for y0, y1, shift in ((100, 140, 3), (20, 60, 7), (300, 360, 1), (0, 8, 9), (100, 140, 4)):   # both buffers, edges
            c.paint(y0, y1, shift=shift)
            self.assertEqual(c.show(y0, y1 - y0), "ok\n")
            self.assertEqual(self.shown(), bytes(c.map), "after rows %d-%d" % (y0, y1))
        c.close()
        time.sleep(0.3)
        fresh = self.page()
        self.assertEqual(fresh.answer.split()[0], "ok")
        fresh.map[:] = bytes(c.map)
        fresh.show(0, H)
        self.assertEqual(self.shown(), bytes(c.map))

    def test_through_a_keystone_a_partial_show_leaves_no_seam(self):
        self.write("warp.conf", "bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.tv.picture = "warped"
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        for y0, y1, shift in ((100, 140, 3), (20, 60, 7), (200, 240, 2), (100, 140, 4), (0, 40, 5)):
            c.paint(y0, y1, shift=shift)
            c.show(y0, y1 - y0)
        partial = self.shown()
        c.close()
        time.sleep(0.3)
        fresh = self.page()
        fresh.map[:] = bytes(c.map)
        fresh.show(0, H)
        self.assertEqual(self.shown(), partial)       # bands put one at a time are exactly the page put at once
        self.assertNotEqual(partial, bytes(c.map))     # and it did go through the matrix

    def test_a_row_and_the_note_are_not_one_big_rectangle(self):
        """two small ranges, not their union: put through a keystone every pixel is paid for (the union alternates into the
        other buffer at every second show)"""
        import re
        self.write("warp.conf", "bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.tv.picture = "warped"
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        c.show(0, H)
        pixels = []
        for i in range(6):
            y0, y1 = (100, 140) if i % 2 == 0 else (320, 350)
            c.paint(y0, y1, shift=i)
            c.show(y0, y1 - y0)
            pixels.append(int(re.search(r"\((\d+) pixels\)", self.ctl("status")).group(1)))
        # the first two shows still owe the other buffer the whole page; after that each is its own small piece
        self.assertLess(max(pixels[2:]), W * H * 0.30, pixels)  # one union of rows 100-350 would be over half the panel

    def test_the_end_of_the_page_takes_it_from_the_wall(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        c.close()
        time.sleep(0.3)
        self.assertIsNone(self.tv.shown)
        self.assertIn("osd hide", self.tv.lines)
        self.assertIn("page            closed", self.ctl("status"))
        self.ctl("volume", "40")                       # the next overlay lands in a buffer that held the page
        x0, y0, x1, y1 = self.tv.bbox()
        self.assertTrue(x0 > 150 and y0 > H * 0.7, (x0, y0, x1, y1))

    def test_page_hide_closes_it_too(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        c.sock.sendall(b"page hide\n")
        time.sleep(0.3)
        self.assertIsNone(self.tv.shown)

    def test_popups_stay_off_the_page(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        self.ctl("volume", "40")
        self.mute("on")
        time.sleep(0.2)
        self.assertEqual(self.shown(), bytes(c.map))   # neither the strip nor the badge
        c.close()
        time.sleep(0.4)
        x0, y0, x1, y1 = self.tv.bbox()                # the badge is back, alone (the mute went on while the page was up)
        self.assertTrue(x0 > W * 0.85 and y1 < H * 0.2, (x0, y0, x1, y1))

    def test_a_popup_before_the_page_does_not_leave_a_hole(self):
        self.start()
        self.ctl("volume", "40")
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        self.assertEqual(self.shown(), bytes(c.map))

    def test_the_picture_turning_warped_puts_the_page_again(self):
        self.write("warp.conf", "bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        straight = self.shown()
        self.tv.picture = "warped"
        time.sleep(0.6)                                # the daemon asks every quarter second
        warped = self.shown()
        self.assertNotEqual(warped, straight)
        self.assertEqual(straight, bytes(c.map))

    def test_no_picture_no_page(self):
        self.tv.picture = "none"
        self.start()
        c = self.page()
        self.assertEqual(c.answer, "ok unseen\n")
        self.assertIsNone(c.fd)
        self.assertIn("page            closed", self.ctl("status"))

    def test_waiting_is_said(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        self.tv.show_reply = b"ok waiting\n"
        self.assertEqual(c.show(0, H), "ok waiting\n")
        self.tv.show_reply = b"ok\n"
        self.assertEqual(c.show(0, 10), "ok\n")

    def test_one_page_at_a_time(self):
        self.start()
        first = self.page()
        second = self.page()
        self.assertTrue(second.answer.startswith("error"), second.answer)
        first.paint(0, H)
        self.assertEqual(first.show(0, H), "ok\n")

    def test_bad_lines_do_not_hurt(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.sock.sendall(b"page shove 1 2 3\npage show 0 0 640 0\n")
        time.sleep(0.2)
        self.assertEqual(c.sock.recv(256).decode().count("error"), 2)        # each of the two lines is answered
        self.assertEqual(c.show(0, H), "ok\n")
        self.assertEqual(self.shown(), bytes(c.map))

    def test_the_daemon_ends_with_the_page(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        self.osd.terminate()
        self.osd.wait(5)
        self.assertIn("osd hide", self.tv.lines)
        self.assertIn("osd release", self.tv.lines)
        self.osd = None


@unittest.skipUnless(os.path.exists(FONT), "no font at %s (set OSD_TEST_FONT)" % FONT)
class PageAndLauncher(PageBase):
    def setUp(self):
        super().setUp()
        self.env.update(H713_OSD_FONT=FONT, H713_OSD_CLOCK="20:47")

    def test_the_launcher_does_not_open_over_a_page(self):
        self.start()
        c = self.page()
        c.paint(0, H)
        c.show(0, H)
        r = subprocess.run([BIN, "ctl", "launcher", "0;HDMI;hdmi:HDMI input"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("error the page is open"), r.stdout)

    def test_no_page_over_a_launcher(self):
        self.start()
        r = subprocess.run([BIN, "ctl", "launcher", "0;HDMI;hdmi:HDMI input"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout)
        c = self.page()
        self.assertTrue(c.answer.startswith("error the launcher is open"), c.answer)


if __name__ == "__main__":
    unittest.main()
