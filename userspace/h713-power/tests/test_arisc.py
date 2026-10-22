"""Tests for h713-arisc (rootfs/overlay): the ARISC firmware choice, against a made-up /sys, /etc and /lib."""
import importlib.machinery
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                    "rootfs", "overlay", "usr", "local", "sbin", "h713-arisc")
STATE = "sys/bus/platform/drivers/sun50i-h713-arisc/100000.arisc/state"


def load():
    loader = importlib.machinery.SourceFileLoader("h713_arisc", TOOL)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("h713_arisc", loader))
    loader.exec_module(mod)
    return mod


class Root:
    def __init__(self, firmware="hy310-crust.bin", source="device tree", build2="0x01003318", ready="1",
                 vendor=True, crust=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        if firmware is not None:
            self.put(STATE, "firmware=%s\nfirmware_from=%s\nversion=5\nbuild2=%s\nready=%s\n"
                     % (firmware, source, build2, ready))
        if vendor:
            self.put("lib/firmware/h713-arisc.bin", "x")
        if crust:
            self.put("lib/firmware/hy310-crust.bin", "x")

    def put(self, rel, text):
        p = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.dir, rel)) as f:
            return f.read()


class Arisc(unittest.TestCase):
    def run_tool(self, r, *args):
        m = load()
        m.ROOT = r.dir
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = m.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    def test_status_on_crust_from_the_device_tree(self):
        rc, out, _ = self.run_tool(Root(), "status")
        self.assertEqual(rc, 0)
        self.assertIn("running: crust (hy310-crust.bin), chosen by the device tree", out)
        self.assertIn("standby ready; a power-off switches the rails off", out)
        self.assertIn("next boot: what the device tree names (no /etc/modprobe.d/h713-arisc.conf)", out)
        self.assertIn("this image carries: the vendor firmware, hy310-crust.bin", out)

    def test_status_on_the_vendor_firmware_by_the_option(self):
        r = Root(firmware="h713-arisc.bin", source="module option")
        r.put("etc/modprobe.d/h713-arisc.conf", "options sun50i_h713_arisc firmware=vendor\n")
        rc, out, _ = self.run_tool(r, "status")
        self.assertEqual(rc, 0)
        self.assertIn("running: the vendor firmware from your dump, chosen by the module option", out)
        self.assertIn("no standby; a power-off ends in the power-on gate", out)
        self.assertIn("next boot: the vendor firmware (/etc/modprobe.d/h713-arisc.conf)", out)

    def test_status_names_a_crust_that_cannot_power_off_and_a_driver_that_is_not_there(self):
        rc, out, _ = self.run_tool(Root(build2="0x00003318", ready="0"), "status")
        self.assertIn("standby not ready (ready=0); a power-off ends in the power-on gate", out)
        rc, out, _ = self.run_tool(Root(firmware=None), "status")
        self.assertEqual(rc, 0)
        self.assertIn("running: none (the driver is not bound", out)

    def test_set_vendor_writes_the_option_and_set_crust_does_too(self):
        r = Root()
        rc, out, _ = self.run_tool(r, "set", "vendor")
        self.assertEqual(rc, 0)
        self.assertIn("firmware = vendor (from the next boot on", out)
        self.assertIn("options sun50i_h713_arisc firmware=vendor\n", r.read("etc/modprobe.d/h713-arisc.conf"))
        rc, _, _ = self.run_tool(r, "set", "crust")
        self.assertEqual(rc, 0)
        self.assertIn("firmware=crust\n", r.read("etc/modprobe.d/h713-arisc.conf"))
        self.assertIn("next boot: crust (", self.run_tool(r, "status")[1])

    def test_the_release_default_and_crust_tried_on_it(self):
        # 22.10.2026: the image says firmware=vendor; crust chosen on an image without the standby
        r = Root(firmware="hy310-crust.bin", source="module option")
        r.put("etc/modprobe.d/h713-arisc.conf", "options sun50i_h713_arisc firmware=crust\n")
        r.put("etc/systemd/sleep.conf.d/10-h713.conf", "[Sleep]\nAllowSuspend=no\n")
        rc, out, _ = self.run_tool(r, "status")
        self.assertIn("standby not on this image (built without it); a power-off switches the rails off", out)
        rc, out, _ = self.run_tool(r, "set", "crust")
        self.assertEqual(rc, 0)
        self.assertIn("crust is experimental: the power supply may hum", out)
        self.assertNotIn("experimental", self.run_tool(r, "set", "vendor")[1])

    def test_status_when_the_vendor_image_is_missing(self):
        # kernel 0327: the option asked for the vendor image, the dump lacked it, the driver loaded crust
        r = Root(source="device tree, the vendor image missing", vendor=False)
        r.put("etc/modprobe.d/h713-arisc.conf", "options sun50i_h713_arisc firmware=vendor\n")
        rc, out, _ = self.run_tool(r, "status")
        self.assertIn("running: crust (hy310-crust.bin), chosen by the device tree, the vendor image missing", out)
        self.assertIn("this image carries: no vendor firmware, hy310-crust.bin", out)

    def test_set_refuses_what_the_image_does_not_carry(self):
        rc, _, err = self.run_tool(Root(vendor=False), "set", "vendor")
        self.assertEqual(rc, 1)
        self.assertIn("carries no h713-arisc.bin", err)
        rc, _, err = self.run_tool(Root(crust=False), "set", "crust")
        self.assertEqual(rc, 1)
        self.assertIn("no crust image for this board", err)

    def test_a_conf_that_cannot_be_written_is_1_not_a_traceback(self):
        r = Root()
        r.put("etc/modprobe.d/h713-arisc.conf", "")
        os.chmod(os.path.join(r.dir, "etc/modprobe.d/h713-arisc.conf"), 0o444)
        os.chmod(os.path.join(r.dir, "etc/modprobe.d"), 0o555)
        try:
            if os.geteuid() == 0:
                raise unittest.SkipTest("root writes anywhere")
            rc, _, err = self.run_tool(r, "set", "vendor")
            self.assertEqual(rc, 1)
            self.assertIn("not written", err)
        finally:
            os.chmod(os.path.join(r.dir, "etc/modprobe.d"), 0o755)

    def test_at_most_130_lines_no_long_dashes(self):
        with open(TOOL, encoding="utf-8") as f:
            text = f.read()
        self.assertLessEqual(len(text.splitlines()), 130)
        self.assertFalse(set(text) & {chr(0x2013), chr(0x2014)})


if __name__ == "__main__":
    unittest.main()
