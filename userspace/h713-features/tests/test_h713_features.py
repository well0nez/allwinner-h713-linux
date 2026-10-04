#!/usr/bin/env python3
"""Tests for h713-features.  No device: the sysfs tree is a temporary
directory handed over in $H713_SYS, the record a file beside it.

    python3 -m unittest discover -s tests -v          # from h713-features/
"""

import argparse
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "h713-features")
loader = importlib.machinery.SourceFileLoader("h713_features", TOOL)
hf = importlib.util.module_from_spec(importlib.util.spec_from_loader("h713_features", loader))
loader.exec_module(hf)


class Board(object):
    """A sysfs tree with the nodes the HY310 shows, or some of them."""

    def __init__(self, *have, record=None):
        self.root = tempfile.mkdtemp(prefix="h713-features-")
        self.sys = os.path.join(self.root, "sys")
        self.write("class/video4linux/video0/name", "cedrus")          # never the camera
        self.write("class/video4linux/video1/name", "sun50i-h713-hdmirx")
        self.write("bus/iio/devices/trigger0/name", "not an accelerometer")
        if "camera" in have:
            self.write("class/video4linux/video2/name", "Generic HD camera: Generic HD c")
        if "accelerometer" in have:
            self.write("bus/iio/devices/iio:device0/name", "sc7a20")
            self.write("bus/iio/devices/iio:device0/in_accel_x_raw", "26")
        if "focus-motor" in have:
            self.write("bus/platform/drivers/hy310-focus-motor/motor-ctr/motor_limit", "1 up=1")
        self.record = os.path.join(self.root, "features")
        if record is not None:
            with open(self.record, "wb") as fh:
                fh.write(record.encode("ascii"))

    def write(self, relative, text):
        path = os.path.join(self.sys, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write((text + "\n").encode("ascii"))

    def run(self, *argv):
        env = dict(os.environ, H713_SYS=self.sys)
        return subprocess.run([sys.executable, TOOL, "--record", self.record] + list(argv),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, env=env, timeout=60)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


HY310 = "board = hy310\nfeatures = camera accelerometer focus-motor\n"
GEU = "# written by install-projekt.sh\nboard = hy200-qz713df-a1\nfeatures = accelerometer\n"


class Features(unittest.TestCase):

    def board(self, *have, record=None):
        board = Board(*have, record=record)
        self.addCleanup(board.close)
        return board

    def test_the_hy310_has_all_three_and_the_check_is_quiet(self):
        board = self.board("camera", "accelerometer", "focus-motor", record=HY310)
        status = board.run("status")
        self.assertEqual(status.returncode, 0)
        self.assertIn("camera          present  /dev/video2", status.stdout)
        self.assertIn("accelerometer   present  iio:device0 (sc7a20)", status.stdout)
        self.assertIn("focus-motor     present  ", status.stdout)
        check = board.run("check", "--wait", "0")
        self.assertEqual((check.returncode, check.stderr), (0, ""))
        self.assertEqual(check.stdout.count("\nok "), 3, check.stdout)

    def test_the_geu_says_not_present_and_warns_about_nothing(self):
        board = self.board("accelerometer", record=GEU)
        status = board.run()                                   # status is the default
        self.assertIn("board hy200-qz713df-a1, FEATURES: accelerometer", status.stdout)
        self.assertIn("camera          not present on this board\n", status.stdout)
        self.assertIn("focus-motor     not present on this board\n", status.stdout)
        check = board.run("check", "--wait", "0")
        self.assertEqual((check.returncode, check.stderr), (0, ""))

    def test_a_listed_feature_that_is_missing_is_one_warning_and_exit_0(self):
        board = self.board("accelerometer", "focus-motor", record=HY310)
        check = board.run("check", "--wait", "0")
        self.assertEqual(check.returncode, 0)
        self.assertEqual(check.stderr.splitlines(), [
            "warning: camera: not present on this board - but boards/hy310 FEATURES "
            "lists it, so h713-cam, h713-autofocus stay off"])
        status = board.run("status")                     # the page reads the first word
        self.assertIn("camera          not present on this board - but", status.stdout)

    def test_the_check_waits_for_a_late_camera(self):
        board = self.board("accelerometer", "focus-motor", record=HY310)
        now, naps = [0.0], []

        def sleep(seconds):
            naps.append(seconds)
            now[0] += seconds
            if len(naps) == 2:                           # it enumerates during the wait
                board.write("class/video4linux/video3/name", "Generic HD camera")
        args = argparse.Namespace(record=board.record, wait=30.0)
        hf.SYS, err = board.sys, io.StringIO()
        self.addCleanup(setattr, hf, "SYS", "/sys")
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(err):
            self.assertEqual(hf.do_check(args, sleep, lambda: now[0]), 0)
        self.assertEqual((len(naps), err.getvalue()), (2, ""))
        self.assertIn("ok camera: present  /dev/video3", out.getvalue())

    def test_present_but_not_listed_is_said_and_not_a_warning(self):
        board = self.board("camera", "accelerometer", record=GEU)
        check = board.run("check", "--wait", "0")
        self.assertEqual(check.stderr, "")
        self.assertIn("ok camera: present  /dev/video2  (h713-cam, h713-autofocus, "
                      "not in FEATURES)", check.stdout)

    def test_without_a_record_the_nodes_decide(self):
        board = self.board("accelerometer")
        for argv in (("status",), ("check", "--wait", "5")):
            out = board.run(*argv)
            self.assertEqual((out.returncode, out.stderr), (0, ""))
            self.assertIn("no record of what this board should have", out.stdout)
        self.assertEqual(hf.read_record(board.record), (None, None))

    def test_the_record_keeps_unset_and_empty_apart(self):
        board = self.board(record="board = x\n# features = camera\n")
        self.assertEqual(hf.read_record(board.record), ("x", None))
        board = self.board(record="board = x\nfeatures =\n")
        self.assertEqual(hf.read_record(board.record), ("x", set()))
        self.assertIn("FEATURES: none", board.run().stdout)

    def test_the_search_rules_are_the_tools_own(self):
        """A rule that drifts from the tool's would hide a control the tool can use."""
        userspace = os.path.dirname(os.path.dirname(TOOL))
        for tool, line in (("h713-cam/h713-cam", 'CAMERA_NAME = "%s"' % hf.CAMERA_NAME),
                           ("h713-autofocus/h713-autofocus", 'CAMERA_NAME = "%s"' % hf.CAMERA_NAME),
                           ("h713-autofocus/h713-autofocus", 'DRIVER = "%s"' % hf.MOTOR_DRIVER),
                           ("h713-focus/h713-focus", 'DRIVER = "%s"' % hf.MOTOR_DRIVER),
                           ("h713-keystone/h713-keystone-auto.service", "in_accel_x_raw")):
            path = os.path.join(userspace, tool)
            if not os.path.exists(path):
                self.skipTest("%s is not beside this tool" % tool)
            with open(path, "rb") as fh:
                self.assertIn(line, fh.read().decode("utf-8"), tool)


if __name__ == "__main__":
    unittest.main()
