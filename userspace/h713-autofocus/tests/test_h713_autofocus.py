#!/usr/bin/env python3
"""Golden tests for h713-autofocus. No device is touched.

    python3 -m unittest discover -s tests -v
    python3 tests/test_h713_autofocus.py

The two that matter are test_metric_is_the_vendor_arithmetic (the metric is
the vendor's formula, not something close to it) and test_search_converges
(the search finds the sharpest position of a fixture whose sharpest position
is known, from both directions). The rest are the guards around them.
"""

import importlib.machinery
import importlib.util
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "h713-autofocus")


def _load(name, path):
    """Import a file without a .py name, the way the tools are installed."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


af = _load("h713_autofocus", TOOL)
mf = _load("make_fixture", os.path.join(HERE, "make_fixture.py"))

SPAN, PEAK = 200, 100           # the fixture: 201 positions, sharpest at 100


def naive_strip(p, w, y, x0, x1):
    """The metric of AP1 tables/focus-loop.txt, written out line by line."""
    total = 0
    for x in range(x0, x1 + 1):
        r0, r1, r2 = (y - 1) * w, y * w, (y + 1) * w
        right3 = (p[r0 + x + 1] + p[r1 + x + 1] + p[r2 + x + 1]) // 3
        bot3 = (p[r2 + x - 1] + p[r2 + x] + p[r2 + x + 1]) // 3
        dx = abs(((p[r1 + x - 1] + p[r1 + x]) >> 1) - right3) >> 1
        dy = abs(((p[r0 + x] + p[r1 + x]) >> 1) - bot3) >> 1
        total += (dx * dx * dx) >> 2
        total += (dy * dy * dy) >> 2
    return total


class Metric(unittest.TestCase):

    def setUp(self):
        rnd = random.Random(11)
        self.w, self.h = 64, 32
        self.frame = bytes(rnd.randrange(256) for _ in range(self.w * self.h))

    def test_metric_is_the_vendor_arithmetic(self):
        for y in range(1, self.h - 1):
            self.assertEqual(af._strip(self.frame, self.w, y, 1, self.w - 2, 1),
                             naive_strip(self.frame, self.w, y, 1, self.w - 2))

    def test_the_two_cubes_are_shifted_separately(self):
        """Negative control: one shift over the sum is a different number."""
        wrong = 0
        for y in range(1, self.h - 1):
            for x in range(1, self.w - 1):
                r0, r1, r2 = (y - 1) * self.w, y * self.w, (y + 1) * self.w
                p = self.frame
                right3 = (p[r0 + x + 1] + p[r1 + x + 1] + p[r2 + x + 1]) // 3
                bot3 = (p[r2 + x - 1] + p[r2 + x] + p[r2 + x + 1]) // 3
                dx = abs(((p[r1 + x - 1] + p[r1 + x]) >> 1) - right3) >> 1
                dy = abs(((p[r0 + x] + p[r1 + x]) >> 1) - bot3) >> 1
                wrong += (dx ** 3 + dy ** 3) >> 2
        right = sum(af._strip(self.frame, self.w, y, 1, self.w - 2, 1)
                    for y in range(1, self.h - 1))
        self.assertNotEqual(wrong, right)

    def test_divisor_puts_every_first_reading_near_5012(self):
        """total // (total // k) is k again, as long as total is far above k.

        That is the whole trick: the first reading of a run lands near 5012
        whatever the window and the stride, so the thresholds are plain
        numbers. Close above the 12001 floor the integer division is coarse
        (12001 gives 6000), which is the vendor's arithmetic, not a slip.
        """
        for total in (10 ** 6, 123456789, 4 * 10 ** 9):
            value = total // af.pick_divisor(total)
            self.assertTrue(5012 <= value <= 5300,
                            "%d normalises to %d" % (total, value))
        self.assertEqual(af.pick_divisor(12000), 10)
        self.assertEqual(12000 // af.pick_divisor(12000), 1200)

    def test_windows_are_the_four_vendor_areas(self):
        self.assertEqual(af.WINDOWS["full"], (8, 471, 8, 631))
        self.assertEqual(af.WINDOWS["crect"], (120, 359, 106, 529))
        self.assertEqual(af.WINDOWS["band"][2:], (160, 479))
        self.assertEqual(af.WINDOWS["nocen"], af.WINDOWS["full"])

    def test_blur_lowers_the_measurement(self):
        values = [af.sharpness_sum(mf.frame(r), "crect", 4)
                  for r in (1.5, 2.5, 3.5, 4.5)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_black_is_no_picture(self):
        self.assertEqual(af.picture_present(bytes(af.FRAME_BYTES)), 0)
        self.assertGreater(af.picture_present(mf.frame(1.5)),
                           af.NO_PICTURE_LIMIT)


class Frames(unittest.TestCase):

    def test_step_of_reads_the_naming_convention(self):
        self.assertEqual(af.step_of("step-0012.gray"), 12)
        self.assertEqual(af.step_of("-0012.gray"), -12)
        self.assertEqual(af.step_of("frame_-12.raw"), -12)
        self.assertEqual(af.step_of("12.gray"), 12)
        self.assertIsNone(af.step_of("README"))

    def test_read_frames_refuses_a_directory_without_numbers(self):
        with tempfile.TemporaryDirectory() as box:
            open(os.path.join(box, "README"), "wb").close()
            self.assertRaises(af.Error, af.read_frames, box)

    def test_replay_motor_latches_edges_and_keeps_the_cap(self):
        frames = [(i, "/nonexistent/%d" % i) for i in range(10)]
        motor = af.ReplayMotor(frames, start=8, direction=0)
        motor.loop(5)
        self.assertTrue(motor.edge_up)
        self.assertEqual(motor.state().step, 9)
        self.assertRaises(af.Edge, motor.loop, 1)
        motor = af.ReplayMotor(frames, start=5, direction=0)
        motor.moved = af.RUN_MSTEP_CAP
        self.assertRaises(af.Edge, motor.loop, 1)


class Pattern(unittest.TestCase):

    def test_chessboard_has_the_right_size_and_two_colours(self):
        data = af.chessboard(64, 8, 32, 64 * 4, cell=4, origin=(0, 0))
        self.assertEqual(len(data), 64 * 4 * 8)
        self.assertEqual(set(data[:16]), {0x00, 0xFF})
        self.assertNotEqual(data[0:4], data[4 * 4:4 * 5])    # cells alternate
        self.assertEqual(data[0:4], data[4 * 8:4 * 9])       # ... with period 2


class SearchOnFrames(unittest.TestCase):
    """The convergence proof, on a fixture whose sharpest step is known."""

    @classmethod
    def setUpClass(cls):
        cls.box = tempfile.TemporaryDirectory()
        mf.build(cls.box.name, SPAN, PEAK, 0.03, 1.5)
        cls.frames = af.read_frames(cls.box.name)

    @classmethod
    def tearDownClass(cls):
        cls.box.cleanup()

    def _run(self, frames, start, direction, profile="hy310"):
        """One replayed run. An edge or the mstep cap is a result, not a
        crash: do_run turns both into exit code 5."""
        motor = af.ReplayMotor(frames, start, direction)
        search = af.Search(motor, motor.grab, af.Metric("full", 2),
                           af.PROFILES[profile], log=lambda line: None)
        try:
            reason = search.run()[0]
        except af.Edge as exc:
            reason = "edge: %s" % exc
        return reason, motor.state().step, search, motor

    def test_search_converges_from_both_directions(self):
        landed = []
        for start, direction in ((20, 0), (180, 1)):
            reason, position, search, motor = self._run(self.frames, start,
                                                        direction)
            self.assertEqual(reason, "peak", "start %d" % start)
            self.assertLess(abs(position - PEAK), 12,
                            "start %d landed at %d" % (start, position))
            self.assertLess(abs(search.best_step - PEAK), 12)
            self.assertLessEqual(motor.moved, af.RUN_MSTEP_CAP)
            landed.append(position)
        self.assertLess(abs(landed[0] - landed[1]), 16,
                        "the two directions landed at %s" % (landed,))

    def test_a_smaller_step_profile_converges_too(self):
        reason, position, _, _ = self._run(self.frames, 60, 0, "vafo8")
        self.assertEqual(reason, "peak")
        self.assertLess(abs(position - PEAK), 12)

    def test_flat_frames_do_not_produce_a_peak(self):
        with tempfile.TemporaryDirectory() as box:
            mf.build_constant(box, 0, 40)
            reason, _, _, _ = self._run(af.read_frames(box), 20, 0)
            self.assertNotEqual(reason, "peak")

    def test_two_peaks_never_stop_in_the_valley(self):
        """A hill climb may pick either maximum; it may not pick neither."""
        with tempfile.TemporaryDirectory() as box:
            mf.build_two_peaks(box, SPAN, (60, 140), 0.03)
            reason, position, _, _ = self._run(af.read_frames(box), 20, 0)
            if reason == "peak":
                self.assertLess(min(abs(position - 60), abs(position - 140)),
                                16, "landed at %d" % position)
            else:
                self.assertTrue(reason.startswith("edge")
                                or reason in ("budget", "deadline"), reason)


class Profiles(unittest.TestCase):

    def test_hy310_carries_the_ini_values(self):
        hy310 = af.PROFILES["hy310"]
        self.assertEqual(hy310.steps, (8, 6, 2))            # vafo10, AP1b 10
        self.assertEqual(hy310.exposure, (60, 25, 140, 6))  # the l* block
        self.assertEqual(hy310.camera, (0x0BDA, 0x5803))
        self.assertEqual(hy310.vafocus, 10)
        self.assertTrue(hy310.verified)

    def test_every_profile_measures_crect_at_stride_3(self):
        """The device defaults (Q11 1): 4x cheaper, same normalised scale."""
        for profile in af.PROFILES.values():
            self.assertEqual((profile.window, profile.stride), ("crect", 3),
                             profile.name)

    def test_the_second_board_is_marked_unknown(self):
        self.assertFalse(af.PROFILES["hy300-pro"].verified)
        self.assertIn("camprjspe.ini", af.PROFILES["hy300-pro"].note)
        self.assertEqual(af.PROFILES["vafo8"].steps, (2, 2, 1))


class CommandLine(unittest.TestCase):

    def test_metric_only_measures_a_recorded_frame(self):
        with tempfile.TemporaryDirectory() as box:
            path = os.path.join(box, "one.gray")
            with open(path, "wb") as fh:
                fh.write(mf.frame(1.5))
            out = subprocess.run([sys.executable, TOOL, "measure",
                                  "--metric-only", path],
                                 stdout=subprocess.PIPE, check=True)
            line = out.stdout.decode()
            self.assertIn("window crect", line)     # the default since Q11 1
            self.assertIn("normalised", line)

    def test_metric_only_refuses_a_short_frame(self):
        with tempfile.TemporaryDirectory() as box:
            path = os.path.join(box, "short.gray")
            with open(path, "wb") as fh:
                fh.write(b"\0" * 100)
            out = subprocess.run([sys.executable, TOOL, "measure",
                                  "--metric-only", path],
                                 stderr=subprocess.PIPE)
            self.assertEqual(out.returncode, af.EXIT_ERROR)
            self.assertIn(b"640x480 luma frame", out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
