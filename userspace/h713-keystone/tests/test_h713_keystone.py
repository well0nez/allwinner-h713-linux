#!/usr/bin/env python3
"""Tests for h713-keystone itself.  No device is touched: the IIO node is a
directory of files in a temporary directory and h713-warp is a recorder.

    python3 -m unittest discover -s tests -v          # from h713-keystone/

The other four files in this directory are the 87 moved model tests (AP2c,
AP2f, AP2g, AP2h), byte-identical; they are the contract for the arithmetic.
What is tested here is the layer the tool adds around it: the IIO reader, the
reference file, the hysteresis, the axis map and the h713-warp verbs.

THE POSES TABLE.  Its format is one row per pose:

    (pose name, raw x, raw y, raw z, expected pitch sign, expected roll sign)

raw x/y/z are in_accel_{x,y,z}_raw as the device reports them, about 1000 LSB
per g, six-second averages at 100 Hz.  The two signs are relative to the row
called "rest", which is the pose stored as the reference: +1 / -1 is the
direction the angle moves, 0 means "stays inside a degree".  Measured on the
HY310 on 22.09.2026; "rolled" is the LEFT side lifted, left as seen from
behind the projector looking at the wall.
"""

import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "h713-keystone")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "model"))

import auto_keystone as ak                                    # noqa: E402
import gsensor_angles as gsa                                  # noqa: E402


def _load(name, path):
    """Import a file without a .py name, the way the tools are installed."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ks = _load("h713_keystone", TOOL)

POSES = (
    ("rest",      26, 172, 1068,  0,  0),
    ("nose-up",   37, 531,  929, +1,  0),
    ("rolled",  -292, 161, 1020,  0, -1),
)
REST = POSES[0][1:4]
SCALE = "0.009806"                # in_accel_x_scale, 1000.07 counts per g


def conf_with(**keys):
    """A configuration dict without touching the file system."""
    path = os.path.join(tempfile.gettempdir(), "h713-keystone-no-such-file")
    conf = ks.load_conf(path)
    for name, value in keys.items():
        conf["_text"][name] = value
        conf[name] = dict((n, p) for n, _, p in ks.DEFAULTS)[name](value)
    return conf


def angles(raw, conf, reference):
    """GsX (roll) and GsY (pitch) for one raw triple, through the axis map."""
    row = ak.auto_keystone(ks.model_triple(raw, conf), reference=reference,
                           ini=ks.optics(conf))
    return row["gs_x"], row["gs_y"]


def sign_of(value, band=1.0):
    return 0 if abs(value) < band else (1 if value > 0 else -1)


class FakeIio(object):
    """A directory that looks like /sys/bus/iio/devices."""

    def __init__(self, name="sc7a20", raw=REST, scale=SCALE, rate="1.000000",
                 available="1 10 25 50 100 200 400 1600"):
        self.root = tempfile.mkdtemp(prefix="h713-iio-")
        self.write("iio:device0/name", "other-sensor")
        self.device = os.path.join(self.root, "iio:device2")
        self.write("iio:device2/name", name)
        self.write("iio:device2/in_accel_x_scale", scale)
        self.write("iio:device2/sampling_frequency", rate)
        self.write("iio:device2/sampling_frequency_available", available)
        for axis, value in zip("xyz", raw):
            self.write("iio:device2/in_accel_%s_raw" % axis, str(value))

    def write(self, relative, text):
        path = os.path.join(self.root, relative)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "wb") as fh:
            fh.write((text + "\n").encode("ascii"))

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Iio(unittest.TestCase):
    """The reader: finding the node, the rate, the averaging."""

    def setUp(self):
        self.iio = FakeIio()
        self.addCleanup(self.iio.close)

    def test_the_device_is_found_by_its_name_not_by_its_number(self):
        self.assertEqual(ks.Sensor.find("sc7a20", directory=self.iio.root),
                         self.iio.device)

    def test_a_missing_sensor_is_an_error_with_its_own_exit_code(self):
        with self.assertRaises(ks.Error) as caught:
            ks.Sensor.find("bmi160", directory=self.iio.root)
        self.assertEqual(caught.exception.code, ks.EXIT_NO_SENSOR)
        self.assertIn("st_accel", str(caught.exception))

    def test_the_sampling_rate_is_written_at_the_start(self):
        """The driver default is 1 Hz and a raw read waits for the next
        sample, so without this one reading would cost three seconds."""
        sensor = ks.Sensor(self.iio.device, 100.0)
        self.assertEqual(sensor.rate, 100.0)
        with open(os.path.join(self.iio.device, "sampling_frequency"),
                  "rb") as fh:
            self.assertEqual(fh.read().strip(), b"100")

    def test_a_status_read_leaves_the_rate_alone(self):
        sensor = ks.Sensor(self.iio.device)
        self.assertEqual(sensor.rate, 1.0)

    def test_counts_per_g_comes_from_the_scale(self):
        self.assertAlmostEqual(ks.Sensor(self.iio.device).counts_per_g,
                               1000.0, places=0)
        self.iio.write("iio:device2/in_accel_x_scale", "nonsense")
        self.assertEqual(ks.Sensor(self.iio.device).counts_per_g,
                         ks.FALLBACK_COUNTS_PER_G)

    def test_one_reading_is_the_average_of_ten_triples(self):
        """Ten averaged triples spread 16/12/11 LSB where one spreads
        77/102/85, which is what the hysteresis is sized against."""
        triples = [(10, 20, 1000), (14, 24, 1004), (12, 22, 1002)]
        queue = [str(v) for triple in triples for v in triple]
        real = ks._read
        ks._read = lambda path: (queue.pop(0) if path.endswith("_raw")
                                 else real(path))
        try:
            self.assertEqual(ks.Sensor(self.iio.device).sample(3),
                             (12.0, 22.0, 1002.0))
        finally:
            ks._read = real

    def test_an_unreadable_channel_is_an_error_and_not_a_zero(self):
        os.remove(os.path.join(self.iio.device, "in_accel_y_raw"))
        with self.assertRaises(ks.Error):
            ks.Sensor(self.iio.device).sample(1)


class AxisMap(unittest.TestCase):
    """The poses table of the module docstring, and what it decided."""

    def setUp(self):
        self.conf = conf_with()
        self.reference = ak.reference_from_iio(
            ks.model_triple(REST, self.conf))

    def test_the_default_map_is_the_measurement(self):
        self.assertEqual((self.conf["axis_pitch"], self.conf["axis_roll"],
                          self.conf["axis_vertical"]),
                         ((1, 1), (0, 1), (2, 1)))

    def test_every_pose_moves_the_axis_the_table_says(self):
        for name, x, y, z, pitch_sign, roll_sign in POSES:
            gs_x, gs_y = angles((x, y, z), self.conf, self.reference)
            self.assertEqual(sign_of(gs_y), pitch_sign, "%s pitch" % name)
            self.assertEqual(sign_of(gs_x), roll_sign, "%s roll" % name)

    def test_the_measured_angles_of_the_three_poses(self):
        expected = {"rest": (0.0, 0.0), "nose-up": (0.6035, 20.5858),
                    "rolled": (-17.1663, -0.5175)}
        for name, x, y, z, _, _ in POSES:
            gs_x, gs_y = angles((x, y, z), self.conf, self.reference)
            self.assertAlmostEqual(gs_x, expected[name][0], places=3)
            self.assertAlmostEqual(gs_y, expected[name][1], places=3)

    def test_nose_up_shrinks_the_top_edge(self):
        """AP2h 3: this is the sign the picture is judged by in slot 10."""
        row = ak.auto_keystone(ks.model_triple(POSES[1][1:4], self.conf),
                               reference=self.reference)
        app = row["permille"]         # LT.x LT.y RT.x RT.y LB.x LB.y RB.x RB.y
        top, bottom = 1000 - app[0] - app[2], 1000 - app[4] - app[6]
        self.assertLess(top, bottom)

    def test_the_vendor_swap_would_call_the_bench_tilt_a_roll(self):
        """The negative control for AP2h NOTE 5: under the vendor's swap the
        nose-up pose comes out as a roll of 20 degrees and a pitch of half a
        degree - which is why the measurement overrules the candidate."""
        swapped = conf_with(axis_pitch="+x", axis_roll="+y")
        reference = ak.reference_from_iio(ks.model_triple(REST, swapped))
        gs_x, gs_y = angles(POSES[1][1:4], swapped, reference)
        self.assertGreater(abs(gs_x), 20.0)
        self.assertLess(abs(gs_y), 1.0)

    def test_the_map_reduces_to_the_models_own_axis_order(self):
        """With the vendor swap configured, model_triple() hands the chain
        exactly what AP2g's iio_to_vendor_counts() would make of the raw
        triple - the tool adds a choice, not another transform."""
        swapped = conf_with(axis_pitch="+x", axis_roll="+y")
        raw = (26.0, 172.0, 1068.0)
        self.assertEqual(ks.model_triple(raw, swapped), (26, 172, 1068))
        self.assertEqual(
            gsa.iio_to_vendor_counts(*ks.model_triple(raw, swapped)),
            gsa.iio_to_vendor_counts(26, 172, 1068))
        self.assertEqual(ks.model_triple(raw, conf_with()), (172, 26, 1068))

    def test_a_negative_sign_turns_the_angle_round(self):
        flipped = conf_with(axis_pitch="-y")
        reference = ak.reference_from_iio(ks.model_triple(REST, flipped))
        _, gs_y = angles(POSES[1][1:4], flipped, reference)
        self.assertLess(gs_y, -20.0)


class Reference(unittest.TestCase):
    """The level pose on disk, and the vendor's 45 degree gate."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="h713-ref-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "keystone-ref")
        self.conf = conf_with()

    def test_it_is_written_and_read_back_as_written(self):
        counts = ak.reference_from_iio(ks.model_triple(REST, self.conf))
        ks.write_reference(self.path, counts, (26.0, 172.0, 1068.0), self.conf)
        self.assertEqual(ks.read_reference(self.path, self.conf), counts)
        self.assertEqual(counts, (26 * 16, 172 * 16, 1068 * 16))

    def test_no_file_is_no_reference_and_not_an_error(self):
        self.assertIsNone(ks.read_reference(self.path, self.conf))

    def test_a_reference_from_another_axis_map_is_refused(self):
        counts = ak.reference_from_iio(ks.model_triple(REST, self.conf))
        ks.write_reference(self.path, counts, (26.0, 172.0, 1068.0), self.conf)
        with self.assertRaises(ks.Error) as caught:
            ks.read_reference(self.path, conf_with(axis_pitch="-y"))
        self.assertIn("reference` again", str(caught.exception))

    def test_a_file_without_counts_is_refused(self):
        with open(self.path, "wb") as fh:
            fh.write(b"axis_pitch = +y\naxis_roll = +x\naxis_vertical = +z\n")
        with self.assertRaises(ks.Error):
            ks.read_reference(self.path, self.conf)

    def test_the_45_degree_gate_refuses_a_pose_on_its_side(self):
        """checkGsensorDataOk, LocalService.java:582 - the vendor's own gate,
        raised here so that no reference is stored from a silly pose."""
        with self.assertRaises(ValueError):
            ak.reference_from_iio(ks.model_triple((900, 100, 400), self.conf))


class Loop(unittest.TestCase):
    """The hysteresis: 1.0 degree of change, held for a second."""

    def setUp(self):
        self.gate = ks.Hysteresis(1.0, 1.0)

    def test_the_first_reading_is_applied_at_once(self):
        self.assertTrue(self.gate.update((0.0, 0.0), 100.0))

    def test_noise_under_the_threshold_never_applies(self):
        self.gate.update((0.0, 0.0), 100.0)
        for step in range(1, 40):
            self.assertFalse(self.gate.update((0.4, -0.9), 100.0 + step))

    def test_a_move_has_to_be_held(self):
        self.gate.update((0.0, 0.0), 100.0)
        self.assertFalse(self.gate.update((0.0, 5.0), 100.0))
        self.assertFalse(self.gate.update((0.0, 5.0), 100.5))
        self.assertTrue(self.gate.update((0.0, 5.1), 101.0))
        self.assertEqual(self.gate.applied, (0.0, 5.1))

    def test_a_move_that_comes_back_inside_the_band_is_forgotten(self):
        self.gate.update((0.0, 0.0), 100.0)
        self.assertFalse(self.gate.update((0.0, 5.0), 100.0))
        self.assertFalse(self.gate.update((0.0, 0.2), 100.5))
        self.assertFalse(self.gate.update((0.0, 5.0), 101.0))
        self.assertTrue(self.gate.update((0.0, 5.0), 102.0))

    def test_either_angle_can_trigger(self):
        self.gate.update((0.0, 0.0), 0.0)
        self.assertFalse(self.gate.update((2.0, 0.0), 0.0))
        self.assertTrue(self.gate.update((2.0, 0.0), 1.0))


class Warp(unittest.TestCase):
    """The three verbs of h713-warp, without running h713-warp."""

    def setUp(self):
        self.real = ks.warp_call
        self.calls = []
        self.addCleanup(setattr, ks, "warp_call", self.real)

    def answer(self, text):
        def call(tool, args):
            self.calls.append(list(args))
            return text
        ks.warp_call = call

    def test_the_status_parser_takes_any_of_the_three_spellings(self):
        for text in ("ok status\nkeystone  tl_x = 1 tl_y = 2 tr_x = 3 "
                     "tr_y = 4 bl_x = 5 bl_y = 6 br_x = 7 br_y = 8\n",
                     "ok status\ntl x 1  tl y 2  tr x 3  tr y 4\n"
                     "bl x 5  bl y 6  br x 7  br y 8\n",
                     "ok status\ntl-x: 1 tl-y: 2 tr-x: 3 tr-y: 4 "
                     "bl-x: 5 bl-y: 6 br-x: 7 br-y: 8\n"):
            self.answer(text)
            self.assertEqual(ks.warp_read_set("h713-warp"),
                             (1, 2, 3, 4, 5, 6, 7, 8))

    def test_a_status_without_all_eight_is_no_answer(self):
        self.answer("ok status\nwarp off\ntl_x = 1 tl_y = 2\n")
        self.assertIsNone(ks.warp_read_set("h713-warp"))

    def test_the_corner_order_is_the_app_order_of_ap2h(self):
        """APP order is LT.x LT.y RT.x RT.y LB.x LB.y RB.x RB.y; h713-warp
        calls those four corners tl, tr, bl, br (KS4)."""
        self.answer("ok")
        ks.warp_apply("h713-warp", (1, 2, 3, 4, 5, 6, 7, 8))
        self.assertEqual(self.calls, [
            ["keystone", "set", "tl", "x", "1"],
            ["keystone", "set", "tl", "y", "2"],
            ["keystone", "set", "tr", "x", "3"],
            ["keystone", "set", "tr", "y", "4"],
            ["keystone", "set", "bl", "x", "5"],
            ["keystone", "set", "bl", "y", "6"],
            ["keystone", "set", "br", "x", "7"],
            ["keystone", "set", "br", "y", "8"]])

    def test_a_warp_that_is_not_there_is_its_own_exit_code(self):
        missing = os.path.join(tempfile.gettempdir(), "h713-no-such-warp")
        with self.assertRaises(ks.Error) as caught:
            self.real(missing, ["status"])
        self.assertEqual(caught.exception.code, ks.EXIT_WARP)
        self.assertIn("warp daemon", str(caught.exception))


class Configuration(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="h713-conf-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "keystone.conf")

    def write(self, text):
        with open(self.path, "wb") as fh:
            fh.write(text.encode("utf-8"))

    def test_an_unknown_key_is_named_and_dropped(self):
        self.write("# a comment\nzoom_scale = 2\nwobble = 3\n")
        errors = io.StringIO()
        with redirect_stderr(errors):
            conf = ks.load_conf(self.path)
        self.assertEqual(conf["zoom_scale"], 2)
        self.assertIn("wobble is not a key", errors.getvalue())
        self.assertIn(":3:", errors.getvalue())

    def test_a_value_that_does_not_parse_is_an_error(self):
        self.write("hysteresis_degrees = 0\n")
        with self.assertRaises(ks.Error) as caught:
            ks.load_conf(self.path)
        self.assertIn("hysteresis_degrees", str(caught.exception))

    def test_a_bad_axis_is_an_error_and_names_the_forms(self):
        self.write("axis_pitch = up\n")
        with self.assertRaises(ks.Error) as caught:
            ks.load_conf(self.path)
        self.assertIn("+x -x +y -y +z", str(caught.exception))

    def test_the_default_optics_are_the_vendor_file_untouched(self):
        self.assertAlmostEqual(ks.implied_ratio(ks.optics(conf_with())),
                               0.81761, places=4)

    def test_a_measured_throw_ratio_reaches_the_geometry(self):
        """The tape measure of AP2c question 1 goes in here, as a number."""
        ini = ks.optics(conf_with(throw_ratio="1.2"))
        self.assertAlmostEqual(ks.implied_ratio(ini), 1.2, places=6)
        self.assertNotAlmostEqual(ini["Whalf"], 39.478412, places=3)


class Commands(unittest.TestCase):
    """The five subcommands end to end, against the fake node."""

    def setUp(self):
        self.iio = FakeIio()
        self.addCleanup(self.iio.close)
        self.dir = tempfile.mkdtemp(prefix="h713-cmd-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.reference = os.path.join(self.dir, "keystone-ref")
        self.base = ["-C", os.path.join(self.dir, "keystone.conf"),
                     "--reference", self.reference,
                     "--device", self.iio.device, "--quiet"]

    def run_tool(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = ks.main(self.base + list(args))
        return code, out.getvalue()

    def test_read_prints_raw_the_g_vector_and_the_two_angles(self):
        code, out = self.run_tool("read")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("ok read"))
        self.assertIn("26.0   172.0  1068.0", out)
        self.assertIn("0.026  0.172  1.068", out)

    def test_reference_stores_the_pose_and_once_then_reads_zero(self):
        self.assertEqual(self.run_tool("reference")[0], 0)
        self.assertTrue(os.path.exists(self.reference))
        code, out = self.run_tool("once")
        self.assertEqual(code, 0)
        self.assertIn("tl 0,0  tr 0,0  bl 0,0  br 0,0", out)

    def test_reference_refuses_a_pose_on_its_side(self):
        for axis, value in zip("xyz", (900, 100, 400)):
            self.iio.write("iio:device2/in_accel_%s_raw" % axis, str(value))
        with self.assertRaises(ks.Error) as caught:
            self.run_tool("reference")
        self.assertEqual(caught.exception.code, ks.EXIT_NOT_LEVEL)

    def test_once_after_a_nose_up_move_shrinks_the_top_edge(self):
        self.run_tool("reference")
        for axis, value in zip("xyz", POSES[1][1:4]):
            self.iio.write("iio:device2/in_accel_%s_raw" % axis, str(value))
        code, out = self.run_tool("once")
        self.assertEqual(code, 0)
        self.assertIn("pitch 20.586", out)
        self.assertIn("tl 95,35  tr 101,20  bl 4,141  br 0,160", out)

    def test_run_without_a_reference_says_what_to_do_first(self):
        with self.assertRaises(ks.Error) as caught:
            self.run_tool("run")
        self.assertIn("h713-keystone reference", str(caught.exception))

    def test_status_reports_and_does_not_raise(self):
        code, out = self.run_tool("--warp", "no-such-warp", "status")
        self.assertEqual(code, 0)
        self.assertIn("sc7a20", out)
        self.assertIn("axis_pitch = +y", out)
        self.assertIn("throw ratio 0.8176", out)


if __name__ == "__main__":
    unittest.main()
