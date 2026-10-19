"""Host tests of what the wall gets while the user walks the opaque pages through a strong keystone: the launcher, the settings page
(as h713-settings reports its pieces), the moves of their selections, the change of an area, and the ways between the two - with the
hand-over and without. 19.10.2026, HY310 turned about 24 degrees to the wall: moving the launcher's selection after the settings page,
the ground on the right went transparent - pitch black on the wall, where the picture under an opaque page is off - on every second
key.

After every step the buffer on the panel is held against the same page put whole into a fresh buffer: no pixel that is opaque in the
whole put may be anything else (no hole), and every pixel must be the same (nothing stale). The panel is the box's, 1920x1080, and
the keystones are the HY310's of that morning and stronger ones (turned 30 degrees to either side, pitched up or down as well).

python3 -m unittest discover -s tests -v   (from userspace/h713-osd, after `make host`)
H713_WALL_SAVE=DIR keeps the buffer and the whole put of the first step that differs, as PAM pictures.
"""

import mmap
import os
import re
import socket
import subprocess
import time
import unittest
import zlib

from test_osd import BIN, OsdBase
from test_launcher import FONT

W, H = 1920, 1080                           # the box's panel
PITCH = W * 4
U = H / 1080.0
LAUNCHER = "hdmi:HDMI input;film:Kodi;globe:Browser;desk:Desktop;sliders:Settings;>power:Standby"
SETTINGS_ROW = 4                            # the launcher's entry of the settings page: Back brings it back chosen

# warp.conf's eight insets (per mille, inward): tl_x tl_y tr_x tr_y bl_x bl_y br_x br_y
KEYSTONES = {
    "hy310": (65, 0, 199, 244, 12, 0, 187, 81),            # the HY310 on 19.10.2026, turned to the wall (h713-warp ctl status)
    "turned right 30": (68, 0, 231, 189, 68, 0, 231, 189),  # h713-keystone's chain, turn_to_wall = 30, level
    "turned left 30, pitched up": (238, 294, 89, 1, 213, 75, 24, 0),
    "turned right 30, pitched down": (33, 0, 217, 95, 86, 0, 237, 276),
}

WARP_CONF = ("tl_x = %d\ntl_y = %d\ntr_x = %d\ntr_y = %d\nbl_x = %d\nbl_y = %d\nbr_x = %d\nbr_y = %d\nwarp = on\n")

GROUND, PILL, WHITE = bytes((0x0d, 0x0e, 0x0b, 0xff)), bytes((0x21, 0x23, 0x1c, 0xff)), bytes((0xff, 0xff, 0xff, 0xff))
DIM = bytes((0x75, 0x76, 0x74, 0xff))       # an outline at half strength over the ground


def _texture():
    """64 rows of 2304 pixels of text-like ink over the ground: every grey, sparse strokes"""
    rows = []
    for y in range(64):
        row = bytearray(GROUND * 2304)
        for x in range(2304):
            if (x * 7 + y * 13) % 23 < 6:
                g = 40 + (x * 11 + y * 5) % 216
                row[4 * x:4 * x + 4] = bytes((g, g, g, 255))
        rows.append(bytes(row))
    return rows


TEXTURE = _texture()


def px(v, up=False):
    """a design coordinate (1920x1080) on the panel, as h713-settings rounds the pieces it reports"""
    return min(W if up else W - 1, max(0, int(-(-v * U // 1)) if up else int(v * U // 1)))


class Settings:
    """The settings page as h713-settings draws it (ui.c): an opaque ground, nine areas on the left, the rows of the open area on the
    right, a sentence and a line of keys at the foot - and the pieces it says are new after a key: a moved row is its old and its new
    row's room (690..1830 x y +- 54, the pills reach past the pitch), joined into one piece when they lie within 24 rows; a new area is
    its two area pills, the whole right pane and the foot, which lie within 24 rows of each other and so come as one."""

    AREAS = 9

    def __init__(self, area=0, focus="areas", row=0):
        self.area, self.focus, self.row = area, focus, row

    def state(self):
        return (self.area, self.focus, self.row)

    @staticmethod
    def rows_of(area):
        return 4 + area % 3                 # areas of different length: a shorter one leaves room below its last row

    def render(self):
        img = [bytearray(GROUND * W) for _ in range(H)]

        def fill(x0, y0, x1, y1, colour):
            for y in range(px(y0), px(y1, True)):
                img[y][4 * px(x0):4 * px(x1, True)] = colour * (px(x1, True) - px(x0))

        def ink(x0, y0, x1, y1, seed):
            a, b = px(x0), px(x1, True)
            for y in range(px(y0), px(y1, True)):
                t = TEXTURE[(y + seed * 17) % 64]
                o = (seed * 101) % 256
                img[y][4 * a:4 * b] = t[4 * o:4 * (o + b - a)]

        def pill(x0, y0, x1, y1, line):
            fill(x0, y0, x1, y1, line)
            fill(x0 + 3, y0 + 3, x1 - 3, y1 - 3, PILL)

        for i in range(self.AREAS):
            y = 198 + 94 * i
            if i == self.area:
                pill(96, y - 44, 566, y + 44, WHITE if self.focus == "areas" else DIM)
            ink(124, y - 32, 188, y + 32, 3 * i + 1)                  # the symbol
            ink(214, y - 22, 214 + 120 + 9 * i, y + 12, 3 * i + 2)    # the name
        for k in range(self.rows_of(self.area)):
            y = 202 + 94 * k
            if self.focus == "rows" and k == self.row:
                pill(700, y - 52, 1820, y + 52, WHITE)
            ink(752, y - 22, 952 + 20 * k, y + 12, 7 * self.area + k)   # the label
            fill(1110, y - 3, 1110 + 60 * (k + self.area) % 540 + 20, y + 3, WHITE)    # the slider's track
        note = 11 * self.area + (self.row + 1 if self.focus == "rows" else 0)
        ink(752, 930, 1400 + 3 * note, 958, note)                       # the sentence of the row
        ink(752, 985, 1300 + (40 if self.focus == "rows" else 0), 1005, 50 if self.focus == "rows" else 51)  # the line of keys
        return b"".join(img)

    def pieces(self, before):
        """what ui_draw() reports after the step from the state `before` (area, focus, row) to this one, in design units"""
        area, focus, row = before
        drawn = []
        if area != self.area:               # Up/Down on the areas: both pills, the whole right pane, the foot
            for i in (area, self.area):
                drawn.append((80, 198 + 94 * i - 47, 584, 198 + 94 * i + 47))
            drawn.append((690, 70, 1830, 140))
            n = self.rows_of(self.area)
            drawn.append((690, 202 + 94 * n - 54, 1830, 890))
            drawn += [(690, 202 + 94 * k - 54, 1830, 202 + 94 * k + 54) for k in range(n)]
            drawn.append((690, 890, 1840, 1020))
        elif focus != self.focus:           # OK into the rows / Back to the areas: the area's pill, the row, the foot
            drawn.append((80, 198 + 94 * area - 47, 584, 198 + 94 * area + 47))
            for k in sorted({row, self.row}):
                drawn.append((690, 202 + 94 * k - 54, 1830, 202 + 94 * k + 54))
            drawn.append((690, 890, 1840, 1020))
        else:                               # a row moved: the old and the new one, and the sentence that changed with it
            for k in (row, self.row):
                drawn.append((690, 202 + 94 * k - 54, 1830, 202 + 94 * k + 54))
            drawn.append((690, 890, 1840, 1020))
        boxes = []                          # seal(): a piece joins one that lies within 24 rows of it
        for x0, y0, x1, y1 in drawn:
            b = [px(x0), px(y0), px(x1, True), px(y1, True)]
            for r in boxes:
                if b[1] <= r[3] + 24 and b[3] >= r[1] - 24:
                    r[:] = [min(r[0], b[0]), min(r[1], b[1]), max(r[2], b[2]), max(r[3], b[3])]
                    break
            else:
                boxes.append(b)
        return [(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes]


class PageClient:
    """h713-settings' end of the page channel: one connection, one memfd, "page show X Y W H" per piece"""

    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(path)
        self.sock.sendall(b"page open\n")
        msg, fds, _, _ = socket.recv_fds(self.sock, 128, 1)
        if not msg.startswith(b"ok %d %d %d " % (W, H, PITCH)) or not fds:
            raise AssertionError("page open: %r" % msg)
        self.map = mmap.mmap(fds[0], PITCH * H)
        os.close(fds[0])

    def show(self, image, boxes):
        for x, y, w, h in boxes:
            for r in range(y, y + h):
                self.map[r * PITCH + 4 * x:r * PITCH + 4 * (x + w)] = image[r * PITCH + 4 * x:r * PITCH + 4 * (x + w)]
            self.sock.sendall(b"page show %d %d %d %d\n" % (x, y, w, h))
            answer = self.sock.recv(64)
            if not answer.startswith(b"ok"):
                raise AssertionError("page show: %r" % answer)

    def close(self, handover=False):
        if handover:
            self.sock.sendall(b"page handover\n")
        self.sock.close()
        self.map.close()


OPAQUE = bytes(1 if a == 255 else 0 for a in range(256))
NOT_OPAQUE = bytes(0 if a == 255 else 1 for a in range(256))


def holes(shot, whole):
    """the pixels opaque in the whole put that are not opaque on the panel"""
    a = int.from_bytes(whole[3::4].translate(OPAQUE), "little")
    b = int.from_bytes(shot[3::4].translate(NOT_OPAQUE), "little")
    return (a & b).bit_count()


def differing(shot, whole):
    n, rows = 0, []
    for y in range(H):
        s, w = shot[y * PITCH:(y + 1) * PITCH], whole[y * PITCH:(y + 1) * PITCH]
        if s != w:
            rows.append(y)
            n += sum(1 for p, q in zip(memoryview(s).cast("I"), memoryview(w).cast("I")) if p != q)
    return n, rows


def save_pam(path, data):
    with open(path, "wb") as f:
        f.write(b"P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n" % (W, H))
        rgba = bytearray(data)
        rgba[0::4], rgba[2::4] = data[2::4], data[0::4]             # BGRA as the buffer holds it -> RGBA
        f.write(rgba)


@unittest.skipUnless(os.path.exists(FONT), "no font at %s (set OSD_TEST_FONT)" % FONT)
class WallTest(OsdBase):
    SIZE = (W, H)

    def setUp(self):
        super().setUp()
        self.env.update(H713_OSD_FONT=FONT, H713_OSD_CLOCK="07:52")
        self.page, self.steps, self.costs = None, [], []

    def tearDown(self):
        if self.page:
            self.page.close()
        super().tearDown()

    def launcher(self, words):
        r = subprocess.run([BIN, "ctl", "launcher"] + words.split(), env=self.env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout + r.stderr)
        self.settle()

    def settle(self):
        time.sleep(0.4)                     # the refresh, and the idle time's fill of the other buffer (0.12 s after it)

    def shot(self):
        self.assertIsNotNone(self.tv.shown, "nothing on the wall")
        return os.pread(self.tv.bufs[self.tv.shown], PITCH * H, 0)

    def step(self, name, what):
        self.steps.append((name, what, zlib.compress(self.shot(), 1)))

    def move(self, sel, name):
        """a move of the launcher's selection: the two tiles it changes are put, not the page - the buffer was made ready in the idle
        time after the last key (and a page's pixels that were left in it went then, not at this key)"""
        self.launcher(str(sel))
        self.step(name, ("launcher", sel))
        self.costs.append((name, int(re.search(r"\((\d+) pixels\)", self.ctl("status")).group(1))))

    # --- the walk -------------------------------------------------------------------------------------------------------------

    def open_page(self, s, handover_from_launcher):
        if handover_from_launcher:
            self.launcher("close keep")     # h713-keys on OK on the settings' entry: the launcher stays until the page is drawn
        self.page = PageClient(self.env["H713_OSD_SOCKET"])
        self.page.show(s.render(), [(0, 0, W, H)])      # the first drawing: everything
        self.settle()
        self.step("page opened, area %d" % s.area, ("page", s.state()))

    def key(self, s, area=None, focus=None, row=None, name=""):
        before = s.state()
        s.area = s.area if area is None else area
        s.focus = s.focus if focus is None else focus
        s.row = s.row if row is None else row
        image = s.render()
        self.page.show(image, s.pieces(before))
        self.assertEqual(bytes(self.page.map), image, "the pieces cover what changed")   # the page's own promise (h713-settings' test)
        self.settle()
        self.step(name, ("page", s.state()))

    def close_page(self, handover):
        self.page.close(handover)
        self.page = None
        time.sleep(0.1)

    def walk(self):
        self.launcher("0;HDMI 1080p60;" + LAUNCHER)
        self.step("launcher opened", ("launcher", 0))
        for sel in (1, 2, 3, 4):
            self.move(sel, "launcher down to %d" % sel)
        s = Settings()
        self.open_page(s, handover_from_launcher=True)
        for a in (1, 2):
            self.key(s, area=a, name="page: area down to %d" % a)
        self.key(s, focus="rows", name="page: OK into the rows")
        for r in (1, 2, 3):
            self.key(s, row=r, name="page: row down to %d" % r)
        self.key(s, row=2, name="page: row up to 2")
        self.key(s, focus="areas", name="page: Back to the areas")
        self.close_page(handover=True)      # Back at the top: the launcher comes back with the settings' entry chosen
        self.launcher("%d;HDMI 1080p60;%s" % (SETTINGS_ROW, LAUNCHER))
        self.step("launcher back after the page", ("launcher", SETTINGS_ROW))
        for sel in (5, 4, 3, 2, 1, 0, 1):
            self.move(sel, "launcher after the page, to %d" % sel)
        s = Settings(area=4)
        self.open_page(s, handover_from_launcher=True)
        for a in (5, 4, 3):
            self.key(s, area=a, name="page again: area to %d" % a)
        self.close_page(handover=False)     # Home: the page goes at once, the launcher comes after it
        self.launcher("2;HDMI 1080p60;" + LAUNCHER)
        self.step("launcher after Home", ("launcher", 2))
        for sel in (3, 4, 5, 4):
            self.move(sel, "launcher after Home, to %d" % sel)

    # --- the whole puts -------------------------------------------------------------------------------------------------------

    def whole(self, what):
        """the same page put whole into a buffer that held nothing of it"""
        kind, state = what
        self.launcher("close")
        if kind == "launcher":
            self.launcher("%d;HDMI 1080p60;%s" % (state, LAUNCHER))
            return self.shot()
        s = Settings(*state)
        page = PageClient(self.env["H713_OSD_SOCKET"])
        page.show(s.render(), [(0, 0, W, H)])
        self.settle()
        shot = self.shot()
        page.close()
        time.sleep(0.2)
        return shot

    def check(self, keystone):
        self.write("warp.conf", WARP_CONF % keystone)
        self.tv.picture = "warped"
        self.start()
        self.walk()
        wholes, bad = {}, []
        for name, what, packed in self.steps:
            if what not in wholes:
                wholes[what] = self.whole(what)
            shot, whole = zlib.decompress(packed), wholes[what]
            n_holes, (n_diff, rows) = holes(shot, whole), differing(shot, whole)
            if n_holes or n_diff:
                bad.append("%s: %d holes, %d pixels not as the whole put (rows %d..%d)" % (name, n_holes, n_diff, rows[0], rows[-1]))
                save = os.environ.get("H713_WALL_SAVE")
                if save and len(bad) == 1:
                    os.makedirs(save, exist_ok=True)
                    tag = self.id().rsplit(".", 1)[-1]
                    save_pam(os.path.join(save, tag + "-wall.pam"), shot)
                    save_pam(os.path.join(save, tag + "-whole.pam"), whole)
        mask = sum(wholes[w][3::4].count(255) for w in wholes) // len(wholes)
        self.assertGreater(mask, W * H // 3, "the page stands on the wall")
        self.assertEqual(bad, [], "%d of %d steps differ from the whole put:\n  %s" % (len(bad), len(self.steps), "\n  ".join(bad)))
        dear = [(name, n) for name, n in self.costs if n > W * H * 0.3]
        self.assertEqual(dear, [], "moves that put more than two tiles: %s" % self.costs)

    def test_hy310_turned_to_the_wall(self):
        self.check(KEYSTONES["hy310"])

    def test_turned_right_30(self):
        self.check(KEYSTONES["turned right 30"])

    def test_turned_left_30_pitched_up(self):
        self.check(KEYSTONES["turned left 30, pitched up"])

    def test_turned_right_30_pitched_down(self):
        self.check(KEYSTONES["turned right 30, pitched down"])


if __name__ == "__main__":
    unittest.main()
