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
import shutil
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


class NativeMetric(unittest.TestCase):
    """The C helper must give the Python metric's integer, not one near it.

    The helper is built here the way the Makefile builds it natively, so the
    test needs a compiler; without one it skips rather than pass quietly. The
    cross build for the device is the same source and the same flags.
    """

    @classmethod
    def setUpClass(cls):
        cls.binary = None
        cc = os.environ.get("CC") or "cc"
        source = os.path.join(os.path.dirname(HERE), "afmetric.c")
        if not shutil.which(cc) or not os.path.exists(source):
            return
        cls.box = tempfile.TemporaryDirectory()
        binary = os.path.join(cls.box.name, "h713-afmetric")
        built = subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Wshadow",
                                "-Wvla", "-o", binary, source],
                               stderr=subprocess.PIPE)
        if built.returncode:
            cls.box.cleanup()
            raise AssertionError("afmetric.c does not compile:\n"
                                 + built.stderr.decode())
        cls.binary = binary
        cls.frame = mf.frame(2.0)

    @classmethod
    def tearDownClass(cls):
        if cls.binary:
            cls.box.cleanup()

    def setUp(self):
        if not self.binary:
            self.skipTest("no C compiler -- the helper cannot be built here")

    def _sums(self, data, args):
        out = subprocess.run([self.binary] + args, input=data,
                             stdout=subprocess.PIPE, check=True)
        return [int(line) for line in out.stdout.split()]

    def test_the_c_helper_equals_the_python_metric(self):
        for window in sorted(af.WINDOWS):
            for stride in (1, 2, 3, 5):
                got = self._sums(self.frame, ["--window", window,
                                              "--stride", str(stride)])
                self.assertEqual(got, [af.sharpness_sum(self.frame, window,
                                                        stride)],
                                 "%s stride %d" % (window, stride))

    def test_the_c_helper_is_not_the_wrong_grouping(self):
        """Negative control: the cheap mistake gives a different number."""
        w, one = af.FRAME_W, self.frame
        wrong = 0
        for y in range(120, 360, 3):
            for x in range(106, 530, 3):
                r0, r1, r2 = (y - 1) * w, y * w, (y + 1) * w
                right3 = (one[r0 + x + 1] + one[r1 + x + 1]
                          + one[r2 + x + 1]) // 3
                bot3 = (one[r2 + x - 1] + one[r2 + x] + one[r2 + x + 1]) // 3
                dx = abs(((one[r1 + x - 1] + one[r1 + x]) >> 1) - right3) >> 1
                dy = abs(((one[r0 + x] + one[r1 + x]) >> 1) - bot3) >> 1
                wrong += (dx ** 3 + dy ** 3) >> 2
        right = self._sums(self.frame, ["--window", "crect", "--stride", "3"])
        self.assertEqual(right, [af.sharpness_sum(self.frame, "crect", 3)])
        self.assertNotEqual(right[0], wrong)

    def test_the_yuyv_mode_reads_the_even_bytes(self):
        """The camera buffer straight in: C takes the luma plane itself."""
        rnd = random.Random(713)
        buffer_ = bytearray(len(self.frame) * 2)
        buffer_[0::2] = self.frame
        buffer_[1::2] = bytes(rnd.randrange(256)
                              for _ in range(len(self.frame)))
        got = self._sums(bytes(buffer_), ["--window", "crect", "--stride", "3",
                                          "--yuyv"])
        self.assertEqual(got, [af.sharpness_sum(self.frame, "crect", 3)])

    def test_one_process_answers_frame_after_frame(self):
        """The run mode: three frames over one pipe, three sums, in order."""
        frames = [mf.frame(r) for r in (1.5, 3.0, 6.0)]
        got = self._sums(b"".join(frames), ["--window", "crect",
                                            "--stride", "3"])
        self.assertEqual(got, [af.sharpness_sum(f, "crect", 3)
                               for f in frames])
        self.assertEqual(got, sorted(got, reverse=True))   # blur lowers it

    def test_a_yuyv_metric_equals_a_luma_metric_divisor_and_all(self):
        """Q11 3: the search feeds whole buffers, the numbers may not move."""
        rnd = random.Random(20260922)
        frames = [mf.frame(r) for r in (1.5, 2.5, 4.0)]
        buffers = []
        for one in frames:
            both = bytearray(len(one) * 2)
            both[0::2] = one
            both[1::2] = bytes(rnd.randrange(256) for _ in range(len(one)))
            buffers.append(bytes(both))
        helper = af.Helper(self.binary, "crect", 3, yuyv=True)
        try:
            over_yuyv = af.Metric("crect", 3, helper)
            got = [over_yuyv(b) for b in buffers]
        finally:
            helper.close()
        plain = af.Metric("crect", 3)
        self.assertEqual(got, [plain(one) for one in frames])
        self.assertEqual(over_yuyv.lev, plain.lev)

    def test_the_helper_refuses_a_short_frame(self):
        out = subprocess.run([self.binary], input=b"\0" * 100,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(out.returncode, 2)
        self.assertIn(b"640x480 frame has", out.stderr)

    def test_the_tool_uses_the_helper_and_agrees_with_python(self):
        """End to end: `measure --metric-only` with and without the helper."""
        with tempfile.TemporaryDirectory() as box:
            path = os.path.join(box, "one.gray")
            with open(path, "wb") as fh:
                fh.write(self.frame)
            lines = []
            for extra in (["--helper", self.binary], ["--no-helper"]):
                out = subprocess.run([sys.executable, TOOL] + extra
                                     + ["measure", "--metric-only", path],
                                     stdout=subprocess.PIPE, check=True)
                lines.append(out.stdout.decode().split("   ")[:3])
            self.assertEqual(lines[0], lines[1])
            self.assertIn("sum %d" % af.sharpness_sum(self.frame, "crect", 3),
                          lines[0][1])


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


class FixtureProducer(unittest.TestCase):
    """What h713-cam writes must be what this tool reads (Q11 4)."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                            "h713-cam", "h713-cam")
        if not os.path.exists(path):
            self.skipTest("h713-cam is not beside this tool")
        try:
            self.cam = _load("h713_cam", path)
        except ImportError as exc:          # fcntl/mmap: Linux only
            self.skipTest(str(exc))
        self.luma = mf.frame(2.0)
        rnd = random.Random(4)
        buffer_ = bytearray(len(self.luma) * 2)
        buffer_[0::2] = self.luma
        buffer_[1::2] = bytes(rnd.randrange(256)
                              for _ in range(len(self.luma)))
        self.buffer = bytes(buffer_)

    def test_the_raw_grab_is_the_plane_the_metric_measures(self):
        plane = self.cam.luma_plane(self.buffer, af.FRAME_W, af.FRAME_H,
                                    af.FRAME_W * 2)
        self.assertEqual(len(plane), af.FRAME_BYTES)
        self.assertEqual(plane, self.luma)
        self.assertEqual(af.sharpness_sum(plane, "crect", 3),
                         af.sharpness_sum(self.luma, "crect", 3))

    def test_a_padded_line_does_not_skew_the_plane(self):
        """Why it goes line by line and not buffer[0::2] in one slice."""
        bpl, line = af.FRAME_W * 2 + 16, af.FRAME_W * 2
        padded = bytearray(bpl * af.FRAME_H)
        for y in range(af.FRAME_H):
            padded[y * bpl:y * bpl + line] = self.buffer[y * line:(y + 1) * line]
        self.assertEqual(self.cam.luma_plane(bytes(padded), af.FRAME_W,
                                             af.FRAME_H, bpl), self.luma)
        self.assertNotEqual(bytes(padded)[0::2][:af.FRAME_BYTES], self.luma)


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
