#!/usr/bin/env python3
"""Tests for h713-lamp.  No device: the sysfs tree is a temporary directory
handed over in $H713_SYS, the kept mode a file beside it ($H713_LAMP_CONF).

    python3 -m unittest discover -s tests -v          # from h713-lamp/
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "h713-lamp")
DEV = "bus/platform/drivers/hy310-board-mgr/fan"


class Board(object):
    """A sysfs tree with the board manager's lamp attributes (the L018), or without them."""

    def __init__(self, lamp=True, thermal="0", conf=None):
        self.root = tempfile.mkdtemp(prefix="h713-lamp-")
        self.sys = os.path.join(self.root, "sys")
        self.write(DEV + "/hwmon/hwmon2/fan1_input", "3180")
        if lamp:
            self.write(DEV + "/lamp_mode", "std")
            self.write(DEV + "/lamp_modes", "std low high")
            self.write(DEV + "/hwmon/hwmon2/temp1_input", "21500")
            if thermal is not None:
                self.write(DEV + "/thermal_mode", thermal)
        self.conf = os.path.join(self.root, "etc", "lamp.conf")
        if conf is not None:
            os.makedirs(os.path.dirname(self.conf))
            with open(self.conf, "w") as fh:
                fh.write(conf)

    def write(self, relative, text):
        path = os.path.join(self.sys, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text + "\n")

    def read(self, relative):
        with open(os.path.join(self.sys, relative)) as fh:
            return fh.read().strip()

    def run(self, *argv):
        env = dict(os.environ, H713_SYS=self.sys, H713_LAMP_CONF=self.conf)
        return subprocess.run([sys.executable, TOOL] + list(argv), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, env=env, timeout=60)

    def close(self):
        shutil.rmtree(self.root)


class LampTest(unittest.TestCase):
    def board(self, **kw):
        b = Board(**kw)
        self.addCleanup(b.close)
        return b

    def test_status(self):
        out = self.board().run("status")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("mode     std", out.stdout)
        self.assertIn("modes    std low high", out.stdout)
        self.assertIn("thermal  off", out.stdout)
        self.assertIn("fan      3180 RPM", out.stdout)
        self.assertIn("ntc      21.5 C", out.stdout)
        self.assertIn("kept     nothing", out.stdout)

    def test_status_is_the_default(self):
        self.assertIn("mode     std", self.board().run().stdout)

    def test_thermal_on_and_absent(self):
        self.assertIn("thermal  on", self.board(thermal="1").run("status").stdout)
        self.assertIn("thermal  none on this board", self.board(thermal=None).run("status").stdout)

    def test_set_writes_and_keeps(self):
        b = self.board()
        out = b.run("set", "high")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(b.read(DEV + "/lamp_mode"), "high")
        with open(b.conf) as fh:
            self.assertIn("mode = high\n", fh.read())
        self.assertIn("kept     high", b.run("status").stdout)

    def test_set_refuses_an_unknown_mode(self):
        b = self.board()
        out = b.run("set", "max")
        self.assertEqual(out.returncode, 2)
        self.assertIn("not a mode of this board (std low high)", out.stderr)
        self.assertEqual(b.read(DEV + "/lamp_mode"), "std")
        self.assertFalse(os.path.exists(b.conf))

    def test_restore_sets_the_kept_mode(self):
        b = self.board(conf="# x\nmode = low   # the quiet one\n")
        out = b.run("restore")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(b.read(DEV + "/lamp_mode"), "low")
        self.assertIn("lamp mode low", out.stdout)

    def test_restore_without_a_kept_mode(self):
        b = self.board()
        out = b.run("restore")
        self.assertEqual(out.returncode, 0)
        self.assertIn("nothing kept - the lamp stays at std", out.stdout)
        self.assertEqual(b.read(DEV + "/lamp_mode"), "std")

    def test_restore_ignores_a_bad_kept_mode(self):
        b = self.board(conf="mode = blinding\n")
        out = b.run("restore")
        self.assertEqual(out.returncode, 0)
        self.assertIn("not a mode of this board", out.stderr)
        self.assertEqual(b.read(DEV + "/lamp_mode"), "std")

    def test_other_boards(self):
        b = self.board(lamp=False, conf="mode = high\n")
        for argv in (("status",), ("set", "high")):
            out = b.run(*argv)
            self.assertEqual(out.returncode, 7, argv)
            self.assertIn("not present on this board", out.stderr)
        out = b.run("restore", "--wait", "0")
        self.assertEqual(out.returncode, 0)
        self.assertIn("no lamp modes on this board", out.stdout)


if __name__ == "__main__":
    unittest.main()
