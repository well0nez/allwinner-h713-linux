#!/usr/bin/env python3
"""h713-focus: rule 4's refusal text here and in h713-autofocus, and a run
against test-stub.py. No device is touched; the stub plays the driver."""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "h713-focus")
STUB = os.path.join(os.path.dirname(HERE), "test-stub.py")
AUTOFOCUS = os.path.join(HERE, "../..", "h713-autofocus", "h713-autofocus")
LINE = "1 up=1 dn=1 num=1 raw=%d act=1 edge_up=0 edge_dn=0 step=110\n"
WAY_BACK = "'modprobe -r hy310_focus_motor && modprobe hy310_focus_motor'"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


def _node(box, raw):
    """A motor node with the counter at 110: raw 0 is outside, 1 in range."""
    for name, text in (("motor_limit", LINE % raw), ("motor_ctrl", "0\n"),
                       ("motor_ctrl_no_limit", "0\n")):
        with open(os.path.join(box, name), "w") as fh:
            fh.write(text)


def _focus(box, *argv):
    return subprocess.run([sys.executable, TOOL, "--sysfs", box] + list(argv),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=60)


fo = _load("h713_focus", TOOL)


class RuleFour(unittest.TestCase):

    def test_outside_the_range_names_the_way_back(self):
        """Since 23.09.: homing, by reboot or module reload. In range is free."""
        for up in (True, False):
            reason = fo.check(fo.Limit(LINE % 0), up, 0)
            for text in ("raw=0, expected is act=1", "outside the permitted "
                         "range", "homing", "reboot", WAY_BACK):
                self.assertIn(text, reason)
            self.assertIsNone(fo.check(fo.Limit(LINE % 1), up, 0))

    def test_the_autofocus_refuses_with_the_same_way_back(self):
        if not os.path.exists(AUTOFOCUS):
            self.skipTest("h713-autofocus is not beside this tool")
        af = _load("h713_autofocus", AUTOFOCUS)
        with tempfile.TemporaryDirectory() as box:
            _node(box, raw=0)
            motor = af.SysfsMotor(box)
            reason = motor.blocked(motor.state())
            _node(box, raw=1)
            self.assertIsNone(motor.blocked(motor.state()))
        for text in ("raw=0, act=1", "outside its range", "homing", WAY_BACK):
            self.assertIn(text, reason)


class StubRun(unittest.TestCase):

    def setUp(self):
        self.box = tempfile.TemporaryDirectory()
        self.stub = subprocess.Popen([sys.executable, STUB, self.box.name],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        while self.stub.poll() is None and \
                not os.path.exists(os.path.join(self.box.name, "motor_ctrl")):
            time.sleep(0.02)                # the stub ends by itself after 60 s

    def tearDown(self):
        self.stub.terminate()
        self.stub.wait(timeout=10)
        self.box.cleanup()

    def test_into_the_lower_edge_then_blocked_towards_it(self):
        """The tool's own fake driver: raw drops at -206, the latch follows."""
        run = _focus(self.box.name, "down", "20")
        self.assertIn("edge_dn=1   (6 msteps driven)", run.stdout.splitlines()[-1])
        self.assertEqual(run.returncode, 3)         # README and docs: 3 at an edge
        again = _focus(self.box.name, "down", "4")
        self.assertEqual(again.returncode, 3)
        self.assertIn("Blocked: edge_dn=1", again.stderr)


class NotPresent(unittest.TestCase):
    """No focus motor on this board (boards/README.md, FEATURES): every
    subcommand ends with exit 7 and the verdict as its last line, the line
    the settings page shows. A wrong --sysfs stays an error: a typo, not a
    board. $H713_SYS is the board's /sys."""

    def _run(self, sysroot, *argv):
        return subprocess.run([sys.executable, TOOL] + list(argv),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=60,
                              env=dict(os.environ, H713_SYS=sysroot, H713_FOCUS_SYSFS=""))

    def test_no_driver_and_no_node_is_not_present(self):
        with tempfile.TemporaryDirectory() as box:
            for argv in (["status"], ["up", "5"], ["flush"], ["unlatch"]):
                run = self._run(box, *argv)
                self.assertEqual(run.returncode, fo.EXIT_NOT_PRESENT, (argv, run.stderr))
                self.assertEqual(run.stderr.splitlines()[-1], fo.NOT_PRESENT)

    def test_a_driver_with_no_device_bound_is_not_present(self):
        with tempfile.TemporaryDirectory() as box:
            driver = os.path.join(box, "bus/platform/drivers", fo.DRIVER)
            os.makedirs(driver)
            for name in ("bind", "unbind", "uevent"):
                open(os.path.join(driver, name), "w").close()
            run = self._run(box, "status")
            self.assertEqual(run.returncode, fo.EXIT_NOT_PRESENT, run.stderr)
            self.assertIn("probably 'disabled'", run.stderr)
            self.assertEqual(run.stderr.splitlines()[-1], fo.NOT_PRESENT)

    def test_a_wrong_sysfs_is_still_an_error(self):
        with tempfile.TemporaryDirectory() as box:
            run = self._run(box, "--sysfs", box, "status")
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertIn("is missing there", run.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
