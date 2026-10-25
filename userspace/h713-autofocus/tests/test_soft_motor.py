#!/usr/bin/env python3
"""h713-autofocus on a unit whose end switch says nothing (the L018 of 25.10.2026): with h713-focus's experimental
counted range (focus.conf "limiter = ignore") the search is bounded by that range - SoftMotor."""

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "h713-autofocus")
LINE = "0 up=0 dn=0 num=1 raw=0 act=1 edge_up=0 edge_dn=0 step=%d\n"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


class SoftMotorTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.node = os.path.join(self.dir, "node")
        os.makedirs(self.node)
        self.limit(0)
        for name, text in (("motor_ctrl", "0\n"), ("motor_ctrl_no_limit", "0\n")):
            with open(os.path.join(self.node, name), "w") as fh:
                fh.write(text)
        etc = os.path.join(self.dir, "etc")
        os.makedirs(etc)
        with open(os.path.join(etc, "focus.conf"), "w") as fh:
            fh.write("limiter = ignore\nrange_low = -35\nrange_high = 35\nhome_up = 110\nhome_down = 55\n")
        self.state = os.path.join(self.dir, "focus.state")
        boot = os.path.join(self.dir, "boot_id")
        with open(boot, "w") as fh:
            fh.write("b1\n")
        os.environ.update(H713_ETC=etc, H713_FOCUS_STATE=self.state, H713_BOOT_ID=boot)
        self.af = _load("h713_autofocus_soft", TOOL)
        self.tool = self.af._focus_tool()
        self.soft = self.tool.read_soft()

    def tearDown(self):
        for k in ("H713_ETC", "H713_FOCUS_STATE", "H713_BOOT_ID"):
            os.environ.pop(k, None)

    def limit(self, step):
        with open(os.path.join(self.node, "motor_limit"), "w") as fh:
            fh.write(LINE % step)

    def keep(self, position, step):
        with open(self.state, "w") as fh:
            fh.write("position = %d\nstep = %d\nboot_id = b1\n" % (position, step))

    def test_found_and_switches_the_dead_switch_off(self):
        self.assertIsNotNone(self.soft)
        motor = self.af.SoftMotor(self.node, self.tool, self.soft)
        with open(os.path.join(self.node, "motor_ctrl_no_limit")) as fh:
            self.assertEqual(fh.read().strip(), "1")
        self.assertIn("h713-focus home", motor.blocked(motor.state()))   # no position kept yet

    def test_the_range_ends_are_the_edges(self):
        motor = self.af.SoftMotor(self.node, self.tool, self.soft)
        self.keep(35, 0)
        st = motor.state()
        self.assertIsNone(motor.blocked(st))
        self.assertTrue(motor.edge_ahead(st, True))
        self.assertFalse(motor.edge_ahead(st, False))
        self.keep(-35, 0)
        self.assertTrue(motor.edge_ahead(motor.state(), False))

    def test_a_move_is_cut_at_the_range_and_the_position_kept(self):
        motor = self.af.SoftMotor(self.node, self.tool, self.soft)
        self.keep(30, 0)
        motor._move(18, True)                    # only 5 left: the word written asks for 5 msteps up
        with open(os.path.join(self.node, "motor_ctrl")) as fh:
            self.assertEqual(int(fh.read()), (self.af.CMD_UP << 8) | 5)   # the autofocus timing command
        with open(self.state) as fh:
            self.assertIn("position = 30", fh.read())   # the fake counter did not move: 30 kept, not 35


if __name__ == "__main__":
    unittest.main()
