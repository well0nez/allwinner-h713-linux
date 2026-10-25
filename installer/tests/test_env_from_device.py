"""TODO 2.137: the intent keys of the U-Boot environment come off the device, not out of the dump.

On 22.10.2026 (G-EU) and 23.10.2026 (HY310) a reinstall with the dump directory of an earlier
run said "carried over from the old one: h713_gate=0 (image: 1)" while the device said 1: the
run had read the environment off the device (keep_copy()), and old_env() took the dump's
uboot-env.bin of the 20th all the same. The device's value counts; where the dump disagrees,
the run says so.
"""

import argparse
import importlib.machinery
import importlib.util
import os
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.blockdev import Disk                                 # noqa: E402
from h713.env import ENV_BYTES, env_read, env_write            # noqa: E402
from h713.install import carry_env, old_env                    # noqa: E402

SECT = 512
TOOL = os.path.join(support.TOOLS, "h713-install")


class Recorder(support.Recorder):
    def error(self, t):
        self.lines.append("ERROR " + t)


def _args(dump_dir, device=None):
    """What the run hands carry_env(): our layout, the default --keep-env, and the copy
    keep_copy() read off the device (None: nothing was read)."""
    args = argparse.Namespace(dump_dir=dump_dir, fresh_env=False, _our_layout=True)
    if device is not None:
        args._kept = {"uboot-env": device}
    return args


class OldEnv(unittest.TestCase):
    def setUp(self):
        self.tmp = support.workdir(self)
        self.log = Recorder()

    def dump(self, env):
        with open(os.path.join(self.tmp, "uboot-env.bin"), "wb") as f:
            f.write(env_write(env) if isinstance(env, dict) else env)

    def test_the_device_wins_over_an_older_dump(self):
        """The G-EU of 22.10.2026: gate 1 on the device, 0 in the dump of the 20th."""
        self.dump({"h713_gate": "0", "h713_boot": "emmc"})
        env, path = old_env(_args(self.tmp, env_write({"h713_gate": "1", "h713_boot": "emmc"})), self.log)
        self.assertEqual(env["h713_gate"], "1")
        self.assertIsNone(path, "the dump's file is not what was taken")
        self.assertIn("disagree", self.log.text)
        self.assertIn("h713_gate=1 on the device, 0 in the dump", self.log.text)
        self.assertNotIn("h713_boot", self.log.text, "only the keys that differ are named")

    def test_agreeing_dump_is_named_as_the_copy_and_nothing_is_said(self):
        self.dump({"h713_gate": "1", "bootcmd": "x"})
        env, path = old_env(_args(self.tmp, env_write({"h713_gate": "1", "bootcmd": "y"})), self.log)
        self.assertEqual(env["bootcmd"], "y")
        self.assertEqual(path, os.path.join(self.tmp, "uboot-env.bin"))
        self.assertEqual(self.log.lines, [])

    def test_a_device_without_a_valid_environment_takes_nothing_from_the_dump(self):
        self.dump({"h713_gate": "0"})
        env, _path = old_env(_args(self.tmp, b"\0" * ENV_BYTES), self.log)
        self.assertIsNone(env)
        self.assertIn("the device carries none that is valid", self.log.text)
        self.assertIn("h713_gate=0", self.log.text)
        self.assertIn("not taken", self.log.text)

    def test_nothing_read_off_the_device_falls_back_to_the_dump_loudly(self):
        self.dump({"h713_gate": "0"})
        env, path = old_env(_args(self.tmp), self.log)
        self.assertEqual(env["h713_gate"], "0")
        self.assertEqual(path, os.path.join(self.tmp, "uboot-env.bin"))
        self.assertIn("WARN Environment: not read off the device in this run", self.log.text)

    def test_no_dump_at_all_is_the_device_silently(self):
        env, path = old_env(_args(self.tmp, env_write({"h713_gate": "0"})), self.log)
        self.assertEqual(env, {"h713_gate": "0"})
        self.assertIsNone(path)
        self.assertEqual(self.log.lines, [])


class CarryEnv(unittest.TestCase):
    """carry_env() on a working copy of part B, the way write_package() calls it."""

    def setUp(self):
        self.tmp = support.workdir(self)
        self.log = Recorder()
        self.dump_dir = os.path.join(self.tmp, "dump")
        os.makedirs(self.dump_dir)

    def run_it(self, image, device, dumped=None):
        work = os.path.join(self.tmp, "part-b.img")
        with open(work, "wb") as f:
            f.write(b"\xaa" * (4 * SECT))
            f.write(env_write(image))
            f.write(b"\x55" * (4 * SECT))
        if dumped is not None:
            with open(os.path.join(self.dump_dir, "uboot-env.bin"), "wb") as f:
                f.write(env_write(dumped))
        tab = {"bausteine": {"env": {"lba": 14336 + 4}}, "teile": [{"datei": "b.img", "lba": 14336}]}
        rc = carry_env(_args(self.dump_dir, env_write(device)), tab, work, "b.img", self.log)
        with open(work, "rb") as f:
            f.seek(4 * SECT)
            return rc, env_read(f.read(ENV_BYTES))

    def test_the_case_of_22_10_carries_nothing_and_says_why(self):
        rc, env = self.run_it({"h713_gate": "1", "h713_boot": "emmc"},
                              {"h713_gate": "1", "h713_boot": "emmc"},
                              {"h713_gate": "0", "h713_boot": "emmc"})
        self.assertEqual(rc, 0)
        self.assertEqual(env["h713_gate"], "1", self.log.text)
        self.assertIn("agree with the image's default -- nothing to carry over", self.log.text)
        self.assertIn("h713_gate=1 on the device, 0 in the dump", self.log.text)
        self.assertNotIn("carried over", self.log.text)

    def test_a_gate_switched_off_on_the_device_is_carried_from_the_device(self):
        rc, env = self.run_it({"h713_gate": "1"}, {"h713_gate": "0"}, {"h713_gate": "1"})
        self.assertEqual(rc, 0)
        self.assertEqual(env["h713_gate"], "0")
        self.assertIn("OK Environment: carried over from the device: h713_gate=0 (image: 1)",
                      self.log.lines)
        self.assertIn("the dump's copy is older", self.log.text)

    def test_without_a_dump_it_is_the_device_as_before(self):
        rc, env = self.run_it({"h713_gate": "1"}, {"h713_gate": "0"})
        self.assertEqual((rc, env["h713_gate"]), (0, "0"))
        self.assertIn("read off the device and not saved -- --dump keeps a copy", self.log.text)


class TheDumpStep(unittest.TestCase):
    """_dump() of h713-install: whichever way step 3 goes on our layout, the environment the
    later steps take is the one read off the device in this run."""

    def setUp(self):
        support.need(fakedisk.NEEDS_V3 + (TOOL,))
        spec = importlib.util.spec_from_loader(
            "h713_install_env_cli", importlib.machinery.SourceFileLoader("h713_install_env_cli", TOOL))
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.tmp = support.workdir(self)
        self.disk_path = fakedisk.make_v3_disk(os.path.join(self.tmp, "emmc.img"))

    def step3(self, dump_dir):
        args = argparse.Namespace(command="install", _our_layout=True, dump_dir=dump_dir,
                                  size="small", _dump_given=True, force=False, no_write=True)
        disk = Disk(self.disk_path, writable=False)
        try:
            with support.quiet():
                self.assertEqual(self.cli._dump(args, disk, self.disk_path), 0)
            return args
        finally:
            disk.close()

    def test_a_new_dump_directory_keeps_the_device_copy_too(self):
        args = self.step3(os.path.join(self.tmp, "new-dump"))
        self.assertIn("uboot-env", getattr(args, "_kept", None) or {})

    def test_the_first_installs_directory_keeps_it_as_before(self):
        first = os.path.join(self.tmp, "first")
        os.makedirs(first)
        with open(os.path.join(first, "MANIFEST.json"), "w") as f:
            f.write("{}")
        args = self.step3(first)
        self.assertIn("uboot-env", getattr(args, "_kept", None) or {})


if __name__ == "__main__":
    unittest.main()
