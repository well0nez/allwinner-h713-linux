#!/usr/bin/env python3
"""The turn to the wall (turn_to_wall, du_r of the vendor's chain).

The sign is the thing that cannot be taken from the model: it is a question of
which way the projector stands and how it hangs.  So it is settled here against
a ray model of the wall that shares nothing with the vendor's search for the
inscribed rectangle: every panel pixel is a ray, the wall is a plane, and a
corrected picture is right when its four corners are a RECTANGLE on the wall.

    python3 -m unittest discover -s tests -v          # from h713-keystone/

The physical premises, spelled out because the test stands on them:

  * "turn" is said by the viewer: positive when the RIGHT side of the picture
    is the higher one.  The higher side is the farther one: the projector
    stands turned towards it.
  * front: the viewer stands behind the projector, his right is the
    projector's right.
  * ceiling: the same viewer, the projector hangs upside down (rolled 180
    degrees about the beam); its accelerometer reads z < 0.
  * rear: the projector stands behind a screen and throws towards the viewer;
    his right is the projector's LEFT.  rear-ceiling: both.
  * a mode says how the picture is put on the panel: rear mirrors it, ceiling
    turns it round, rear-ceiling flips it top to bottom (SEEN below).
"""

import io
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_h713_keystone as t   # noqa: E402

ks, ak = t.ks, t.ak
kge = ks.kge

W, H = 1920, 1080
INI = ks.optics(t.conf_with())
_OPT = kge.reset_tou_she_bi(INI, kge.itrunc(kge.f32(INI["fdd"])))
TAN_X, TAN_Y = _OPT["tan_lr_v"], _OPT["tan_hp_v"]    # the half field, from the vendor's optics

# (upside down, sign of the wall's yaw for "the viewer's right side is higher")
PHYSICS = {"front": (False, 1), "ceiling": (True, 1), "rear": (False, -1), "rear-ceiling": (True, -1)}
# which corner of the PANEL shows the picture's corner (tl tr bl br), the geometry of the three flips
SEEN = {"front": ("tl", "tr", "bl", "br"), "rear": ("tr", "tl", "br", "bl"),
        "ceiling": ("br", "bl", "tr", "tl"), "rear-ceiling": ("bl", "br", "tl", "tr")}
CORNERS = ("tl", "tr", "bl", "br")
TOLERANCE = 0.005          # the corners are whole pixels, the search is a scanline search: 0.5 % of the picture


def wall_point(px, py, yaw, pitch, upside_down):
    """A panel pixel (row 0 at the top) as a point on the wall, by a ray: the
    panel is a window of the half field TAN_X by TAN_Y, the projector pitched
    nose up by `pitch`, rolled 180 degrees when it hangs, and then turned by
    `yaw` about the vertical (positive: the world's right side is farther)."""
    x, y = (2.0 * px / W - 1.0) * TAN_X, (1.0 - 2.0 * py / H) * TAN_Y
    if upside_down:
        x, y = -x, -y
    th, ps = math.radians(pitch), math.radians(yaw)
    ray = (x, math.sin(th) + y * math.cos(th), math.cos(th) - y * math.sin(th))
    wx = ray[0] * math.cos(ps) + ray[2] * math.sin(ps)
    wz = -ray[0] * math.sin(ps) + ray[2] * math.cos(ps)
    return wx / wz, ray[1] / wz


def panel_corners(pixels):
    """The eight insets of the chain (APP order, inward from the own edge) as
    the four corner pixels, row 0 at the top."""
    lt, rt, lb, rb = pixels[0:2], pixels[2:4], pixels[4:6], pixels[6:8]
    return {"tl": (lt[0], lt[1]), "tr": (W - 1 - rt[0], rt[1]),
            "bl": (lb[0], H - 1 - lb[1]), "br": (W - 1 - rb[0], H - 1 - rb[1])}


def rectangle_error(pixels, yaw, pitch, upside_down):
    """How far the four corners are from a rectangle on the wall, as a share
    of the picture: 0 is a rectangle, a turn left alone is 0.13 at 12 degrees."""
    p = dict((k, wall_point(x, y, yaw, pitch, upside_down))
             for k, (x, y) in panel_corners(pixels).items())
    width = abs((p["tr"][0] - p["tl"][0]) + (p["br"][0] - p["bl"][0])) / 2
    height = abs((p["tl"][1] - p["bl"][1]) + (p["tr"][1] - p["br"][1])) / 2
    return max(abs(p["tl"][1] - p["tr"][1]) / height, abs(p["bl"][1] - p["br"][1]) / height,
               abs(p["tl"][0] - p["bl"][0]) / width, abs(p["tr"][0] - p["br"][0]) / width)


def pose(pitch, upside_down=False):
    """in_accel_{x,y,z}_raw of a projector pitched nose up by `pitch` degrees
    (y carries the pitch, z the vertical: tests/test_h713_keystone.py POSES),
    hanging upside down when asked (rolled 180 degrees about the beam)."""
    s, c = math.sin(math.radians(pitch)) * 1000, math.cos(math.radians(pitch)) * 1000
    return (0, int(round(s)), int(round(-c if upside_down else c)))


def row_for(mode, turn, pitch=0.0):
    upside_down = PHYSICS[mode][0]
    return ks.chain(pose(pitch, upside_down), t.conf_with(turn_to_wall=str(turn)), ak.LEVEL_REFERENCE, INI, mode)


class Configuration(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="h713-turn-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "keystone.conf")

    def load(self, text):
        with open(self.path, "w") as fh:
            fh.write(text)
        return ks.load_conf(self.path)

    def test_it_is_not_turned_by_default(self):
        self.assertEqual(t.conf_with()["turn_to_wall"], 0.0)

    def test_it_takes_degrees_to_either_side_up_to_30(self):
        for text, value in (("12", 12.0), ("-30", -30.0), ("30", 30.0), ("0", 0.0), ("7.5", 7.5)):
            self.assertEqual(self.load("turn_to_wall = %s\n" % text)["turn_to_wall"], value)

    def test_more_than_30_or_not_a_number_is_an_error_that_names_the_key(self):
        for text in ("31", "-30.5", "twelve", "nan"):
            with self.assertRaises(ks.Error) as caught:
                self.load("turn_to_wall = %s\n" % text)
            self.assertEqual(caught.exception.code, ks.EXIT_CONFIG)
            self.assertIn("turn_to_wall", str(caught.exception))

    def test_the_last_line_wins_as_everywhere_in_the_file(self):
        self.assertEqual(self.load("turn_to_wall = 3\nturn_to_wall = -4\n")["turn_to_wall"], -4.0)

    def test_the_running_unit_reads_the_file_again(self):
        with open(self.path, "w") as fh:
            fh.write("after_move = keystone\nturn_to_wall = 12   # the page\n")
        self.assertEqual(ks.read_turn(self.path, 0.0), 12.0)

    def test_a_value_it_cannot_read_leaves_what_the_unit_has(self):
        with open(self.path, "w") as fh:
            fh.write("turn_to_wall = 45\n")
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(ks.read_turn(self.path, 5.0), 5.0)
        self.assertIn("turn_to_wall = \"45\"", err.getvalue())          # said, not guessed
        self.assertEqual(ks.read_turn(os.path.join(self.dir, "none"), 5.0), 5.0)


class TheReportsNumbers(unittest.TestCase):
    """du_r = 12 gave 214 px across and 110 px at top and bottom on the side
    the model pulls in and almost nothing on the other.  Said in the viewer's
    words: the left side higher is a turn of -12, the right side is +12."""

    def test_the_left_side_higher_pulls_the_left_side_in(self):
        self.assertEqual(row_for("front", -12)["pixels"], [214, 110, 25, 1, 214, 110, 25, 1])

    def test_the_right_side_higher_pulls_the_right_side_in(self):
        self.assertEqual(row_for("front", 12)["pixels"], [25, 1, 214, 110, 25, 1, 214, 110])

    def test_no_turn_is_the_old_chain_exactly(self):
        zero = row_for("front", 0)
        plain = ak.auto_keystone(t.ks.model_triple(pose(0), t.conf_with()), ini=INI)
        self.assertEqual(zero["pixels"], plain["pixels"])
        self.assertEqual(zero["pixels"], [1, 0, 1, 0, 1, 0, 1, 0])


class TheWall(unittest.TestCase):
    """The picture is right when it is a rectangle on the wall."""

    def test_the_uncorrected_picture_is_not_one(self):
        """The oracle is sensitive: nothing applied at 12 degrees is 13 % off,
        and the wall's far edge is 1.30 times the near one (the report's 30 %)."""
        flat = [0] * 8
        self.assertGreater(rectangle_error(flat, 12, 0, False), 0.10)
        high_left = wall_point(0, 0, 12, 0, False)[1] - wall_point(0, H - 1, 12, 0, False)[1]
        high_right = wall_point(W - 1, 0, 12, 0, False)[1] - wall_point(W - 1, H - 1, 12, 0, False)[1]
        self.assertAlmostEqual(high_right / high_left, 1.30, delta=0.01)     # turned to the right: the right side is higher

    def test_a_turned_projector_in_front_mount_becomes_a_rectangle(self):
        for turn in (3, 6, 12, 20, 30, -12, -30):
            row = row_for("front", turn)
            self.assertLess(rectangle_error(row["pixels"], turn, 0, False), TOLERANCE, "turn %s" % turn)

    def test_the_opposite_sign_would_not(self):
        for turn in (6, 12, -12):
            row = ak.auto_keystone(ks.model_triple(pose(0), t.conf_with()), ini=INI, du_r=float(turn))
            self.assertGreater(rectangle_error(row["pixels"], turn, 0, False), 0.05, "turn %s" % turn)

    def test_a_tilt_and_a_turn_are_corrected_together(self):
        for pitch in (-15, -8, 8, 15, 20):
            for turn in (12, -12, 25):
                row = row_for("front", turn, pitch)
                self.assertLess(rectangle_error(row["pixels"], turn, pitch, False), TOLERANCE,
                                "pitch %s turn %s" % (pitch, turn))

    def test_without_a_turn_the_tilt_is_corrected_as_before(self):
        for pitch in (-15, 8, 20):
            row = row_for("front", 0, pitch)
            self.assertLess(rectangle_error(row["pixels"], 0, pitch, False), TOLERANCE)

    def test_the_sign_follows_the_mount(self):
        """The four mounts, level and tilted: the corrected picture is a
        rectangle on the wall for the turn the viewer names."""
        for mode, (upside_down, yaw_sign) in sorted(PHYSICS.items()):
            for pitch in (0, 8, -8):
                for turn in (12, -12, 25):
                    row = row_for(mode, turn, pitch)
                    yaw = yaw_sign * turn
                    self.assertLess(rectangle_error(row["pixels"], yaw, pitch, upside_down), TOLERANCE,
                                    "%s pitch %s turn %s" % (mode, pitch, turn))

    def test_one_sign_for_all_mounts_would_fail_in_two_of_them(self):
        """Every mount with the front's sign: rear and ceiling are wrong."""
        for mode in ("rear", "ceiling"):
            upside_down, yaw_sign = PHYSICS[mode]
            row = ak.auto_keystone(ks.model_triple(pose(0, upside_down), t.conf_with()), ini=INI, du_r=-12.0)
            self.assertGreater(rectangle_error(row["pixels"], yaw_sign * 12, 0, upside_down), 0.05, mode)

    def test_the_signs_follow_the_permutation(self):
        """The table of signs is not a second opinion about the mount: it is
        +1 exactly where the permutation takes a right panel corner to the
        picture's top left."""
        for mode, order in ks.MODE_PERM.items():
            self.assertEqual(ks.TURN_SIGN[mode], 1.0 if order[0] % 2 else -1.0, mode)
            self.assertEqual(ks.turn_to_du_r(12, mode), ks.TURN_SIGN[mode] * 12)

    def test_the_permutation_is_the_geometry_of_the_flips(self):
        """MODE_PERM against SEEN, which is written from the flips alone."""
        index = {"tl": 0, "tr": 1, "bl": 2, "br": 3}
        for mode, seen in SEEN.items():
            self.assertEqual(tuple(index[name] for name in seen), ks.MODE_PERM[mode], mode)


class OnTheWarp(unittest.TestCase):
    """The warp's own corners: the pulled side is the one the viewer named."""

    def setUp(self):
        self.real = ks.warp_call
        self.mode = "front"
        self.calls = []
        ks.warp_call = self.call
        self.addCleanup(setattr, ks, "warp_call", self.real)

    def call(self, tool, args):
        self.calls.append(list(args))
        if args == ["status"]:
            return "ok\nmode            %s (for the mount)\n" % self.mode
        return "ok"

    def slots(self, mode, turn):
        """The eight values `once --apply` hands the warp, by corner: {corner: (x, y)}."""
        self.mode, self.calls[:] = mode, []
        row = row_for(mode, turn)
        applied = ks.for_the_mount("h713-warp", row["permille"], mode)
        return row, dict((name, (applied[2 * i], applied[2 * i + 1])) for i, name in enumerate(CORNERS))

    def test_the_picture_corner_gets_what_the_panel_corner_that_shows_it_needs(self):
        for mode in SEEN:
            row, slots = self.slots(mode, 12)
            panel = dict(zip(CORNERS, (row["permille"][2 * i:2 * i + 2] for i in range(4))))
            for name, shown_at in zip(CORNERS, SEEN[mode]):
                self.assertEqual(tuple(slots[name]), tuple(panel[shown_at]), "%s %s" % (mode, name))

    def test_the_higher_side_as_the_viewer_sees_it_is_pulled_in_in_every_mount(self):
        for mode in SEEN:
            for turn, side, other in ((12, ("tr", "br"), ("tl", "bl")), (-12, ("tl", "bl"), ("tr", "br"))):
                _, slots = self.slots(mode, turn)
                pulled = sum(slots[c][0] + slots[c][1] for c in side)
                spared = sum(slots[c][0] + slots[c][1] for c in other)
                self.assertGreater(pulled, 10 * max(spared, 1), "%s turn %s: %s" % (mode, turn, slots))
                # the per-mille the report's 214 px and 110 px come to: 111 across, 101 up and down
                self.assertEqual(slots[side[0]], (111, 101), "%s turn %s" % (mode, turn))

    def test_once_apply_sends_the_eight_values_with_the_turn_in_them(self):
        base = ["-C", os.path.join(self._dir(), "keystone.conf")]
        with open(base[1], "w") as fh:
            fh.write("turn_to_wall = 12\n")
        iio = t.FakeIio(raw=(0, 0, 1000))
        self.addCleanup(iio.close)
        out = self._once(base + ["--reference", os.path.join(self._dir(), "ref"), "--device", iio.device, "--quiet",
                                 "--last-auto", os.path.join(self._dir(), "last"), "once", "--apply"])
        self.assertIn("wall turn +12 degrees", out)
        sets = [c for c in self.calls if c[0] == "keystone"]
        self.assertEqual(sets, [["keystone", "set", corner, axis, value] for corner, axis, value in (
            ("tl", "x", "13"), ("tl", "y", "0"), ("tr", "x", "111"), ("tr", "y", "101"),
            ("bl", "x", "13"), ("bl", "y", "0"), ("br", "x", "111"), ("br", "y", "101"))])
        self.assertEqual(ks.read_last_auto(os.path.join(self._dir(), "last")),
                         (13, 0, 111, 101, 13, 0, 111, 101))

    def _dir(self):
        if not hasattr(self, "_tmp"):
            self._tmp = tempfile.mkdtemp(prefix="h713-turn-")
            self.addCleanup(shutil.rmtree, self._tmp, True)
        return self._tmp

    def _once(self, argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(ks.main(argv), 0)
        return out.getvalue()


class AfterAMove(t.Commands):
    """The unit: the turn is used after a move, as the page has set it, and it
    stays where it was put."""

    def _conf_text(self, turn, after_move="keystone"):
        return ("after_move = %s\naverage_samples = 1\nmove_degrees = 3\nsettle_seconds = 0.5\n%s"
                % (after_move, "turn_to_wall = %s\n" % turn if turn is not None else ""))

    def _watch_with(self, text, change_to=None, seconds=3.0, dry_run=True):
        path = os.path.join(self.dir, "keystone.conf")
        for axis, value in zip("xyz", t.REST):                  # at rest, as a watch starts
            self.iio.write("iio:device2/in_accel_%s_raw" % axis, str(value))
        with open(path, "w") as fh:
            fh.write(text)
        self.assertEqual(self.run_tool("reference")[0], 0)

        def move():
            time.sleep(0.4)
            if change_to is not None:                 # what the settings page does, while the unit runs
                with open(path, "w") as fh:
                    fh.write(self._conf_text(change_to))
            for axis, value in zip("xyz", t.POSES[1][1:4]):
                self.iio.write("iio:device2/in_accel_%s_raw" % axis, str(value))
        threading.Thread(target=move, daemon=True).start()
        return self.run_tool("--last-auto", os.path.join(self.dir, "last-auto"), "watch",
                             *(["--dry-run"] if dry_run else []), "--for", str(seconds))

    def _recording_warp(self):
        calls = []
        real = ks.warp_call
        ks.warp_call = lambda tool, args: calls.append(list(args)) or "ok"
        self.addCleanup(setattr, ks, "warp_call", real)
        return calls

    def test_a_move_is_corrected_with_the_turn_in_the_file(self):
        code, out = self._watch_with(self._conf_text("12"))
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ok apply"), 1, out)
        self.assertIn("wall turn +12 degrees", out)

    def test_a_turn_set_after_the_unit_started_counts_at_the_next_move(self):
        code, out = self._watch_with(self._conf_text(None), change_to="-9")
        self.assertEqual(out.count("ok apply"), 1, out)
        self.assertIn("wall turn -9 degrees", out)

    def test_the_turn_changes_the_insets_of_the_move(self):
        _, plain = self._watch_with(self._conf_text(None))
        _, turned = self._watch_with(self._conf_text("12"))
        inset = lambda out: out[out.index("tl "):out.index("  (dry run)")]
        self.assertNotEqual(inset(plain), inset(turned))

    def test_with_after_move_off_the_turn_waits(self):
        code, out = self._watch_with(self._conf_text("12", "off"))
        self.assertIn("after_move = off: nothing applied", out)
        self.assertNotIn("ok apply", out)

    def test_a_move_writes_the_corners_to_the_warp_with_the_turn_in_them(self):
        """Not a dry run: the eight values reach the warp, and with a turn to the right the right corners are pulled in further."""
        for turn, wide in (("12", True), ("0", False)):
            calls = self._recording_warp()
            code, out = self._watch_with(self._conf_text(turn), dry_run=False)
            self.assertEqual(out.count("ok apply"), 1, out)
            sets = dict(((c[2], c[3]), int(c[4])) for c in calls if c[:2] == ["keystone", "set"])
            self.assertEqual(len(sets), 8)
            gap = sets[("tr", "x")] - sets[("tl", "x")]
            if wide:
                self.assertGreater(gap, 40, sets)
            else:
                self.assertLess(abs(gap), 15, sets)      # the pose has a little roll of its own
            self.assertEqual(ks.read_last_auto(os.path.join(self.dir, "last-auto")),
                             tuple(sets[(c, a)] for c in CORNERS for a in "xy"))

    def test_the_unit_never_changes_the_value(self):
        """After a real apply, and after a second one: the file is as the page left it. The value stays until it is changed."""
        path = os.path.join(self.dir, "keystone.conf")
        self._recording_warp()
        self._watch_with(self._conf_text("12"), dry_run=False)
        with open(path) as fh:
            self.assertEqual(fh.read(), self._conf_text("12"))
        self._watch_with(self._conf_text("12"), dry_run=False)       # the next move
        with open(path) as fh:
            self.assertEqual(fh.read(), self._conf_text("12"))

    def test_status_says_which_side_is_the_higher_one(self):
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("turn_to_wall = -7\n")
        code, out = self.run_tool("status")
        self.assertEqual(code, 0)
        self.assertIn("wall turn       7 degrees to the left (the left side of the picture is the higher one)", out)
        self.assertIn("turn_to_wall = -7", out)

    def test_a_turned_run_says_so_and_an_untouched_one_says_nothing(self):
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("turn_to_wall = 12\n")
        self.assertIn("wall turn +12 degrees", self.run_tool("once")[1])
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("turn_to_wall = 0\n")
        self.assertNotIn("wall turn", self.run_tool("once")[1])


# AfterAMove inherits Commands (the fake node, run_tool): its own copies of those tests are not repeated here.
for _name in [n for n in dir(t.Commands) if n.startswith("test_")]:
    setattr(AfterAMove, _name, None)


if __name__ == "__main__":
    unittest.main()
