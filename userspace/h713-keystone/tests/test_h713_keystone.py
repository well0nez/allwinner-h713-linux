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
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
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
    ("rolled",  -292, 161, 1020,  0, +1),   # roll = -x: left side up -> GsX positive
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


class DefaultsTest(unittest.TestCase):
    def test_average_samples_defaults_to_twenty(self):      # TODO 2.108: buffer triples scatter twice as much in z
        self.assertEqual(dict((n, d) for n, d, _ in ks.DEFAULTS)["average_samples"], "20")


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
        """pitch +y, roll -x (the wall, 22.09.2026: with +x the correction
        tilted the picture further; -x kept it level), vertical +z."""
        self.assertEqual((self.conf["axis_pitch"], self.conf["axis_roll"],
                          self.conf["axis_vertical"]),
                         ((1, 1), (0, -1), (2, 1)))

    def test_every_pose_moves_the_axis_the_table_says(self):
        for name, x, y, z, pitch_sign, roll_sign in POSES:
            gs_x, gs_y = angles((x, y, z), self.conf, self.reference)
            self.assertEqual(sign_of(gs_y), pitch_sign, "%s pitch" % name)
            self.assertEqual(sign_of(gs_x), roll_sign, "%s roll" % name)

    def test_the_measured_angles_of_the_three_poses(self):
        expected = {"rest": (0.0, 0.0), "nose-up": (-0.6035, 20.5858),
                    "rolled": (17.1663, -0.5175)}
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
        self.assertEqual(ks.model_triple(raw, conf_with()), (172, -26, 1068))

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
        self.assertEqual(counts, (-26 * 16, 172 * 16, 1068 * 16))

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

    def test_the_file_carries_the_date_it_was_taken(self):
        counts = ak.reference_from_iio(ks.model_triple(REST, self.conf))
        ks.write_reference(self.path, counts, (26.0, 172.0, 1068.0), self.conf)
        found, taken = ks.read_reference_file(self.path, self.conf)
        self.assertEqual(found, counts)
        self.assertRegex(taken, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")

    def test_without_a_file_the_automatic_corrects_against_the_ideal(self):
        """26.09.2026: no file is the ideal level pose, said on the line - not
        a wait, not a refusal, not a silent absolute angle."""
        self.assertEqual(ks.load_reference(self.path, self.conf),
                         (ak.LEVEL_REFERENCE, "reference ideal (0, 0, 1 g) - "
                          "h713-keystone reference refines it"))

    def test_with_a_file_the_automatic_corrects_against_it_and_names_the_date(self):
        counts = ak.reference_from_iio(ks.model_triple(REST, self.conf))
        ks.write_reference(self.path, counts, (26.0, 172.0, 1068.0), self.conf)
        reference, note = ks.load_reference(self.path, self.conf)
        self.assertEqual(reference, counts)
        self.assertRegex(note, r"^reference file \(\d{4}-\d\d-\d\dT")

    def test_a_refused_file_is_said_once_and_the_ideal_applies_meanwhile(self):
        """The two refusals stay refusals - another axis map, a file without
        counts - and read_reference still raises on them (the tests above).
        load_reference no longer does (FB-KSREFb): one warning names why,
        the ideal applies, and the note keeps the word `refused`, so the
        stored pose is not replaced behind the user's back - and the unit
        no longer exits over it (v0.95-beta did, restarted every 5 s)."""
        counts = ak.reference_from_iio(ks.model_triple(REST, self.conf))
        ks.write_reference(self.path, counts, (26.0, 172.0, 1068.0), self.conf)
        err = io.StringIO()
        with redirect_stderr(err):
            found = ks.load_reference(self.path, conf_with(axis_roll="+x"))
        self.assertEqual(found, (ak.LEVEL_REFERENCE, "reference refused - ideal "
                                 "(0, 0, 1 g) applies, h713-keystone status says why"))
        self.assertEqual(err.getvalue(), "warning: reference refused (%s was taken "
                         "with axis_roll = -x, the configuration says +x -- run "
                         "`h713-keystone reference` again) - correcting against the "
                         "ideal (0, 0, 1 g) meanwhile\n" % self.path)
        with open(self.path, "wb") as fh:
            fh.write(b"axis_pitch = +y\naxis_roll = -x\naxis_vertical = +z\n")
        err = io.StringIO()
        with redirect_stderr(err):
            found = ks.load_reference(self.path, self.conf, quiet=True)
        self.assertEqual(found[0], ak.LEVEL_REFERENCE)
        self.assertTrue(found[1].startswith("reference refused - ideal"), found)
        self.assertEqual(err.getvalue(), "")    # -q drops the warning, never the word

    def test_the_ideal_is_what_the_vendor_chain_sees_without_a_factory_value(self):
        """setgsensorInit is never fed on a unit without GsInitXYZ (AP2e: this
        HY310 has none), so get_gsensor_du subtracts the angles of (0, 0, 0)
        - and for GsX and GsY those equal the angles of the ideal (0, 0, 1 g).
        Only GsZ, which nothing reads, differs (0 against 90)."""
        for _, x, y, z, _, _ in POSES:
            counts = ak.reference_from_iio(ks.model_triple((x, y, z), self.conf))
            against_zero = gsa.get_gsensor_du(*counts, init=[0, 0, 0])
            against_ideal = gsa.get_gsensor_du(*counts,
                                               init=list(ak.LEVEL_REFERENCE))
            self.assertEqual(against_zero[:2], against_ideal[:2])
            self.assertNotEqual(against_zero[2], against_ideal[2])


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

    def test_the_status_parser_takes_the_daemon_s_real_line(self):
        """KS4 prints one line: keystone  tl A,B tr C,D bl E,F br G,H."""
        self.answer("ok status\nwarp            on\n"
                    "keystone        tl 1,2 tr 3,4 bl 5,6 br 7,8 (per-mille, positive inward)\n"
                    "corners         tl -0.998,-1.000 tr +1.000,-1.000 bl -1.000,+1.000 br +1.000,+1.000\n")
        self.assertEqual(ks.warp_read_set("h713-warp"), (1, 2, 3, 4, 5, 6, 7, 8))

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

    def _watch(self, after_move, seconds=3.0, reference=True, conf_extra=""):
        """rest, then the nose-up pose after 0.4 s, then still: one move."""
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("after_move = %s\naverage_samples = 1\nmove_degrees = 3\n"
                     "settle_seconds = 0.5\n%s" % (after_move, conf_extra))
        if reference:
            self.assertEqual(self.run_tool("reference")[0], 0)

        def tilt():
            time.sleep(0.4)
            for axis, value in zip("xyz", POSES[1][1:4]):
                self.iio.write("iio:device2/in_accel_%s_raw" % axis, str(value))
        threading.Thread(target=tilt, daemon=True).start()
        return self.run_tool("--last-auto", os.path.join(self.dir, "last-auto"),
                             "watch", "--dry-run", "--for", str(seconds))

    def test_watch_applies_once_after_a_move_has_settled(self):
        code, out = self._watch("keystone")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ok moved"), 1)
        self.assertEqual(out.count("ok apply"), 1, out)
        self.assertIn("pitch 20.586", out)

    def test_watch_with_after_move_off_only_logs_the_move(self):
        code, out = self._watch("off")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ok moved"), 1)
        self.assertIn("after_move = off: nothing applied", out)
        self.assertNotIn("ok apply", out)

    def test_the_gate_names_whose_values_the_warp_carries(self):
        auto = (10, 0, 6, 12, 4, 12, 8, 0)
        self.assertTrue(ks.keystone_by(auto, auto).startswith("auto"))
        self.assertTrue(ks.keystone_by((10, 0, 6, 12, 4, 12, 9, 0), auto).startswith("manual"))
        self.assertTrue(ks.keystone_by(auto, None).startswith("manual"))
        self.assertTrue(ks.keystone_by(None, auto).startswith("unknown"))

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
        self.assertIn("tl 101,20  tr 95,35  bl 0,160  br 4,141", out)

    def test_run_without_a_reference_uses_the_ideal_and_says_so(self):
        """Until 26.09.2026 `run` refused to start without the file.  Now it
        is the automatic against the ideal, like once and watch; the SIGINT
        comes from a thread once the first apply line is out."""
        out = io.StringIO()

        def interrupt():
            for _ in range(250):                  # up to 5 s
                if "ok apply" in out.getvalue():
                    break
                time.sleep(0.02)
            signal.raise_signal(signal.SIGINT)
        threading.Thread(target=interrupt, daemon=True).start()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = ks.main(self.base + ["run", "--dry-run"])
        self.assertEqual(code, 130)
        self.assertIn("ok apply  pitch 9.146  roll -1.377  tl 60,0  tr 47,37  "
                      "bl 0,76  br 11,34  (dry run)  reference ideal",
                      out.getvalue())

    def test_run_without_a_reference_uses_the_ideal_and_says_so_sigterm_is_clean(self):
        """The same stop by SIGTERM, as systemd sends it: exit 0."""
        out = io.StringIO()

        def interrupt():
            for _ in range(250):                  # up to 5 s
                if "ok apply" in out.getvalue():
                    break
                time.sleep(0.02)
            signal.raise_signal(signal.SIGTERM)
        threading.Thread(target=interrupt, daemon=True).start()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = ks.main(self.base + ["run", "--dry-run"])
        self.assertEqual(code, 0)   # systemd stops with SIGTERM: not "failed"
        self.assertIn("ok apply  pitch 9.146  roll -1.377  tl 60,0  tr 47,37  "
                      "bl 0,76  br 11,34  (dry run)  reference ideal",
                      out.getvalue())

    def test_status_reports_and_does_not_raise(self):
        code, out = self.run_tool("--warp", "no-such-warp", "status")
        self.assertEqual(code, 0)
        self.assertIn("sc7a20", out)
        self.assertIn("axis_pitch = +y", out)
        self.assertIn("throw ratio 0.8176", out)

    # --- the ideal reference (FB-KSREF, 26.09.2026) ------------------------

    def test_read_without_a_reference_says_it_is_the_ideal(self):
        code, out = self.run_tool("read")
        self.assertEqual(code, 0)
        self.assertIn("reference ideal (0, 0, 1 g) - h713-keystone reference "
                      "refines it", out)

    def test_once_without_a_reference_is_the_pose_against_the_ideal(self):
        """The 22.09.2026 rest pose stands 9.15 degrees nose-up and 1.38
        degrees rolled against the ideal - the number the device test
        measures on a level surface, where it is the mounting offset."""
        code, out = self.run_tool("once")
        self.assertEqual(code, 0)
        self.assertIn("ok once  pitch 9.146  roll -1.377  tl 60,0  tr 47,37  "
                      "bl 0,76  br 11,34  reference ideal (0, 0, 1 g) - "
                      "h713-keystone reference refines it", out)

    def test_once_with_a_reference_names_the_file_and_its_date(self):
        self.run_tool("reference")
        code, out = self.run_tool("once")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"tl 0,0  tr 0,0  bl 0,0  br 0,0  reference file "
                              r"\(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\)")
        self.assertNotIn("ideal", out)

    def test_once_apply_pushes_the_ideal_correction_into_the_warp(self):
        calls = []
        real = ks.warp_call
        ks.warp_call = lambda tool, args: calls.append(list(args)) or "ok"
        self.addCleanup(setattr, ks, "warp_call", real)
        last_auto = os.path.join(self.dir, "last-auto")
        code, out = self.run_tool("--last-auto", last_auto, "once", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("ok applied through h713-warp", out)
        sets = [c for c in calls if c[0] == "keystone"]
        self.assertEqual(sets[0], ["keystone", "set", "tl", "x", "60"])
        self.assertEqual(len(sets), 8)
        # the mount is asked for once and shared by the reference rule, the
        # sign of the turn to the wall and the permutation (a status is a
        # process of its own on the board, and every one of them is time)
        self.assertEqual([c for c in calls if c[0] == "status"], [["status"]])
        self.assertEqual(ks.read_last_auto(last_auto),
                         (60, 0, 47, 37, 0, 76, 11, 34))

    def test_once_apply_permutes_the_corners_for_a_rear_mount(self):
        """h713-warp set to rear: the vendor's permutation (left and right
        corners swapped) before the values reach the warp and last-auto;
        the warp's own flip then puts them where the wall needs them."""
        calls = []
        real = ks.warp_call
        ks.warp_call = lambda tool, args: calls.append(list(args)) or (
            "ok\nmode            rear (mirrored for the mount)\n" if args == ["status"] else "ok")
        self.addCleanup(setattr, ks, "warp_call", real)
        last_auto = os.path.join(self.dir, "last-auto")
        code, out = self.run_tool("--last-auto", last_auto, "once", "--apply")
        self.assertEqual(code, 0)
        sets = [c for c in calls if c[0] == "keystone"]
        self.assertEqual(sets[0], ["keystone", "set", "tl", "x", "47"])
        self.assertEqual(ks.read_last_auto(last_auto),
                         (47, 37, 60, 0, 11, 34, 0, 76))

    def test_once_with_a_refused_reference_says_so_and_uses_the_ideal(self):
        """The axis map changed under the stored file: once runs against the
        ideal, exit 0, the line says refused; without -q stderr says why, once."""
        self.run_tool("reference")
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("axis_roll = +x\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ks.main([a for a in self.base if a != "--quiet"] + ["once"])
        self.assertEqual(code, 0)
        self.assertRegex(out.getvalue(), r"^ok once  pitch 9\.146  roll 1\.377  tl .*"
                         r"  reference refused - ideal \(0, 0, 1 g\) applies, "
                         r"h713-keystone status says why\n$")
        self.assertEqual(err.getvalue().count("warning: reference refused ("), 1)
        self.assertIn("axis_roll = -x, the configuration says +x -- run `h713-keystone "
                      "reference` again) - correcting against the ideal", err.getvalue())

    def test_reference_prints_the_pose_against_the_ideal(self):
        code, out = self.run_tool("reference")
        self.assertEqual(code, 0)
        self.assertIn("ok offset  pitch 9.15  roll -1.38 degrees, this pose "
                      "against the ideal (0, 0, 1 g)", out)

    def test_watch_without_a_reference_watches_against_the_ideal(self):
        """Until 26.09.2026 the unit waited for the file; a fresh image now
        watches from the first boot, and the ok line says against what."""
        code, out = self._watch("keystone", reference=False)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^ok watch  .*  reference ideal \(0, 0, 1 g\)")
        self.assertEqual(out.count("ok apply"), 1, out)
        self.assertIn("pitch 29.732", out)    # nose-up, absolute against the ideal
        self.assertIn("(dry run)  reference ideal", out)

    def test_watch_with_a_refused_reference_watches_on_against_the_ideal(self):
        """v0.95-beta exited with 2 when the axis map had changed under the
        stored file, and systemd restarted the unit every five seconds (review
        FB-KSREF, 26.09.2026).  Now the header says refused, the one apply
        after the move is against the ideal, and the exit is 0."""
        self.assertEqual(self.run_tool("reference")[0], 0)
        code, out = self._watch("keystone", reference=False,
                                conf_extra="axis_roll = +x\n")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^ok watch  .*  reference refused - ideal \(0, 0, 1 g\) "
                              r"applies, h713-keystone status says why\n")
        self.assertEqual(out.count("ok apply"), 1, out)
        self.assertIn("pitch 29.732", out)    # nose-up against the ideal
        self.assertIn("(dry run)  reference refused", out)

    def test_status_says_refused_and_why(self):
        """The first word is what the settings page shows as `ref refused`."""
        self.run_tool("reference")
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("axis_roll = +x\n")
        code, out = self.run_tool("--warp", "no-such-warp", "status")
        self.assertEqual(code, 0)
        self.assertIn("reference       refused (%s was taken with axis_roll = -x, "
                      "the configuration says +x -- run `h713-keystone reference` "
                      "again)\n" % self.reference, out)

    def test_status_names_the_ideal_or_the_file(self):
        code, out = self.run_tool("--warp", "no-such-warp", "status")
        self.assertIn("reference       ideal (0, 0, 1 g) - h713-keystone "
                      "reference refines it\n", out)
        self.run_tool("reference")
        code, out = self.run_tool("--warp", "no-such-warp", "status")
        self.assertRegex(out, r"reference       file \(\d{4}-\d\d-\d\dT\d\d:\d\d:"
                              r"\d\d\): %s, counts -416 2752 17088\n"
                              % re.escape(self.reference))


class NotPresent(unittest.TestCase):
    """A board without an accelerometer (boards/README.md, FEATURES): exit 7
    and the words "not present on this board", under the unit and by hand -
    never the 3 of a sensor that is there and does not answer."""

    UNIT = os.path.join(os.path.dirname(HERE), "h713-keystone-auto.service")
    RULE = os.path.join(os.path.dirname(HERE), "99-h713-keystone.rules")

    def setUp(self):
        self.sys = tempfile.mkdtemp(prefix="h713-no-iio-")
        self.addCleanup(shutil.rmtree, self.sys, True)
        adc = os.path.join(self.sys, "bus", "iio", "devices", "iio:device0")
        os.makedirs(adc)                       # an IIO device, but no acceleration
        with open(os.path.join(adc, "name"), "wb") as fh:
            fh.write(b"sun50i-adc\n")
        self.iio = os.path.dirname(adc)

    def test_no_accelerometer_at_all_is_not_present(self):
        for directory in (self.iio, os.path.join(self.sys, "no-iio-at-all")):
            with self.assertRaises(ks.Error) as caught:
                ks.Sensor.find("sc7a20", directory=directory)
            self.assertEqual(caught.exception.code, ks.EXIT_NOT_PRESENT)
            self.assertTrue(str(caught.exception).startswith(
                "accelerometer: not present on this board - "), caught.exception)

    def _tool(self, *argv):
        return subprocess.run(
            [sys.executable, TOOL, "-C", os.path.join(self.sys, "none.conf"),
             "--warp", os.path.join(self.sys, "no-warp")] + list(argv),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=dict(os.environ, H713_SYS=self.sys), timeout=60)

    def test_by_hand_and_under_the_unit_it_is_exit_7(self):
        for argv in (["watch"], ["once", "--apply"], ["read"], ["reference"]):
            run = self._tool(*argv)
            self.assertEqual(run.returncode, ks.EXIT_NOT_PRESENT, (argv, run.stderr))
            self.assertTrue(run.stderr.splitlines()[-1].startswith(
                "h713-keystone: accelerometer: not present on this board"), run.stderr)

    def test_status_says_it_in_the_sensor_row_and_exits_0(self):
        run = self._tool("status")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("sensor          accelerometer: not present on this board", run.stdout)

    def test_the_unit_is_skipped_and_the_rule_starts_it_once_the_node_is_there(self):
        with open(self.UNIT, "rb") as fh:
            unit = fh.read().decode("ascii")
        with open(self.RULE, "rb") as fh:
            rule = fh.read().decode("ascii")
        for line in ("ConditionPathExistsGlob=/sys/bus/iio/devices/iio:device*/in_accel_x_raw",
                     "Restart=on-failure", "RestartSec=5", "RestartSteps=5",
                     "RestartMaxDelaySec=60",           # 3 and 5 back off, never stop (stage 3.3)
                     "SuccessExitStatus=%d" % ks.EXIT_NOT_PRESENT,
                     "RestartPreventExitStatus=%d" % ks.EXIT_NOT_PRESENT):
            self.assertIn("\n" + line + "\n", unit)
        for word in ('SUBSYSTEM=="iio"', 'ACTION=="add"', 'TEST=="in_accel_x_raw"',
                     'TAG+="systemd"', 'ENV{SYSTEMD_WANTS}+="h713-keystone-auto.service"'):
            self.assertIn(word, rule)
        # the node both of them wait for is the one the tool reads
        self.assertTrue(ks.Sensor(FakeIio().device).files[0].endswith("in_accel_x_raw"))


if __name__ == "__main__":
    unittest.main()
