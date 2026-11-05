"""Tests for mainline/build/kconfig-check.sh, build.sh's kernel-stage check that kconfig kept every line of the defconfig
and that the module tree carries h713_drm where .config builds it. Run: python3 -m unittest release/tests/test_kconfig_check.py"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LIB = os.path.join(REPO, "mainline", "build", "kconfig-check.sh")
DEFCONFIG = os.path.join(REPO, "mainline", "patches", "kernel", "board", "hy200_qz713df_a1_defconfig")


def bash(script, *args):
    # build.sh's shell options, so that the functions are tested as build.sh runs them
    r = subprocess.run(["bash", "-c", 'set -euo pipefail; shopt -s inherit_errexit; source "$0"; ' + script, LIB, *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


class KconfigCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def file(self, name, *lines):
        p = os.path.join(self.tmp.name, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("".join(l + "\n" for l in lines))
        return p

    def test_a_config_with_every_line_passes(self):
        with open(DEFCONFIG) as f:
            lines = [l.rstrip("\n") for l in f]
        conf = self.file(".config", "# generated", *lines, "CONFIG_EXTRA=y")
        rc, out = bash('kconfig_lost "$1" "$2"', conf, DEFCONFIG)
        self.assertEqual((rc, out), (0, ""))

    def test_a_config_that_lost_rust_names_what_it_lost(self):
        # what kconfig leaves without the Rust toolchain: CONFIG_RUST off, CONFIG_DRM_H713 (depends on RUST) gone
        with open(DEFCONFIG) as f:
            lines = [l.rstrip("\n") for l in f if not l.startswith(("CONFIG_RUST=", "CONFIG_DRM_H713"))]
        conf = self.file(".config", *lines, "# CONFIG_RUST is not set")
        rc, out = bash('kconfig_lost "$1" "$2"', conf, DEFCONFIG)
        self.assertEqual(rc, 1)
        self.assertEqual(out.split("\n")[:-1], ["CONFIG_RUST=y", "CONFIG_DRM_H713=m", "CONFIG_DRM_H713_BENCH=y"])

    def test_a_not_set_line_counts_and_a_fragment_overrides(self):
        defc = self.file("defconfig", "# a comment", "CONFIG_A=y", "# CONFIG_B is not set", "CONFIG_C=m")
        frag = self.file("debug.config", "CONFIG_C=y")
        conf = self.file(".config", "CONFIG_A=y", "CONFIG_B=y", "CONFIG_C=y")
        rc, out = bash('kconfig_lost "$1" "$2" "$3"', conf, defc, frag)
        self.assertEqual((rc, out), (1, "# CONFIG_B is not set\n"))

    def test_h713_drm_must_be_in_the_module_tree_where_config_builds_it(self):
        conf = self.file(".config", "CONFIG_RUST=y", "CONFIG_DRM_H713=m")
        mods = os.path.join(self.tmp.name, "modroot")
        os.makedirs(os.path.join(mods, "lib/modules/7.3.1/kernel/drivers/gpu/drm/h713"))
        rc, out = bash('kconfig_modules_missing "$1" "$2"', conf, mods)
        self.assertEqual((rc, out), (1, "h713_drm.ko (CONFIG_DRM_H713=m)\n"))
        self.file("modroot/lib/modules/7.3.1/kernel/drivers/gpu/drm/h713/h713_drm.ko")
        self.assertEqual(bash('kconfig_modules_missing "$1" "$2"', conf, mods), (0, ""))

    def test_a_config_without_h713_drm_asks_for_no_module(self):
        conf = self.file(".config", "# CONFIG_DRM_H713 is not set")
        self.assertEqual(bash('kconfig_modules_missing "$1" "$2"', conf, self.tmp.name), (0, ""))


if __name__ == "__main__":
    unittest.main()
