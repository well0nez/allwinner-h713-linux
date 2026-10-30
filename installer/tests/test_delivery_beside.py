# SPDX-License-Identifier: GPL-2.0
"""TODO 5.30 (issue #4): an image built with release/build-all.sh brings its own installer U-Boot
and sunxi-fel, as a release folder does. installer/out holds the images of several boards side by
side, so the U-Boot carries the image's name (<name>.u-boot-installer.bin) and the installer takes
the one of the table it was given. And a sunxi-fel that neither knows the H713 nor is ours stops
before the U-Boot is loaded, with a sentence that says where the right one is. expose_drive() is
stood in for where main() is under test, the device is never touched."""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys
import types
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713 import fel as fel_mod                                               # noqa: E402
from h713.install import image_package, release_files, release_place         # noqa: E402

TOOL = os.path.join(support.TOOLS, "h713-install")
SOURCE = os.path.join(fakedisk.FIXTURES, "release", "h713-hy310-v0.5-beta.tabelle.json")
A, B = "h713-hy310-v9.9-beta", "h713-l018-v9.9-beta"     # two images of one build directory


def _delivery(directory):
    """installer/out after two builds: two tables, their parts, each image's U-Boot, one sunxi-fel."""
    os.makedirs(directory)
    for name in (A, B):
        shutil.copyfile(SOURCE, os.path.join(directory, name + ".tabelle.json"))
        with open(os.path.join(directory, name + ".u-boot-installer.bin"), "wb") as fh:
            fh.write(name.encode())
    _dir, table = image_package(os.path.join(directory, A + ".tabelle.json"))
    for part in table["teile"]:
        open(os.path.join(directory, part["datei"]), "wb").close()
    with open(os.path.join(directory, "sunxi-fel"), "wb") as fh:
        fh.write(b"\x7fELF" + b"\0" * 60 + b"FEL trap door")


class Companions(unittest.TestCase):
    def setUp(self):
        support.need([SOURCE])
        self.out = os.path.join(support.workdir(self), "out")
        _delivery(self.out)

    def test_each_table_gets_its_own_uboot_and_the_one_sunxi_fel(self):
        for name in (A, B):
            self.assertEqual(release_files(self.out, name),
                             {"uboot": os.path.join(self.out, name + ".u-boot-installer.bin"),
                              "fel": os.path.join(self.out, "sunxi-fel")})

    def test_a_folder_of_several_tables_names_no_uboot(self):
        """Without the table's name nothing tells the two U-Boots apart - none is taken."""
        self.assertEqual(release_place(self.out), (self.out, None))
        self.assertEqual(release_files(self.out), {"fel": os.path.join(self.out, "sunxi-fel")})

    def test_the_place_of_a_table_a_one_table_folder_and_a_single_part(self):
        self.assertEqual(release_place(os.path.join(self.out, B + ".tabelle.json")), (self.out, B))
        os.remove(os.path.join(self.out, A + ".tabelle.json"))
        self.assertEqual(release_place(self.out), (self.out, B))
        self.assertEqual(release_place(os.path.join(self.out, "x.img")), (None, None))

    def test_a_release_folder_keeps_its_plain_names(self):
        """The release tar has u-boot-installer.bin without a prefix; the prefixed name only comes first."""
        os.remove(os.path.join(self.out, A + ".u-boot-installer.bin"))
        open(os.path.join(self.out, "u-boot-installer.bin"), "wb").close()
        self.assertEqual(release_files(self.out, A)["uboot"], os.path.join(self.out, "u-boot-installer.bin"))
        self.assertEqual(release_files(self.out, B)["uboot"], os.path.join(self.out, B + ".u-boot-installer.bin"))


class MainTakesThem(unittest.TestCase):
    """`install installer/out/<name>.tabelle.json`: before TODO 5.30 a table named directly brought
    nothing along, and the FEL step fell back to the sunxi-fel of the PATH."""

    def setUp(self):
        support.need([TOOL, SOURCE])
        self.tmp = support.workdir(self)
        self.out = os.path.join(self.tmp, "out")
        _delivery(self.out)
        spec = importlib.util.spec_from_loader(
            "h713_install_delivery", importlib.machinery.SourceFileLoader("h713_install_delivery", TOOL))
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.seen = {}
        self.tool.expose_drive = lambda args, here: (self.seen.update(args=args), (None, 0))[1]
        self.key = os.path.join(self.tmp, "id.pub")
        open(self.key, "w").close()

    def _run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = self.tool.main(["install"] + list(argv) + ["--ssh-key", self.key, "--dump",
                                                              os.path.join(self.tmp, "dump"), "--no-write"])
        return code, out.getvalue()

    def test_a_table_of_the_build_directory_brings_its_uboot_and_sunxi_fel(self):
        code, out = self._run(os.path.join(self.out, B + ".tabelle.json"))
        self.assertEqual(code, 0, out)
        args = self.seen["args"]
        self.assertEqual(args.uboot, os.path.join(self.out, B + ".u-boot-installer.bin"))
        self.assertEqual(args.fel, os.path.join(self.out, "sunxi-fel"))

    def test_the_flags_still_win(self):
        mine = os.path.join(self.tmp, "my-uboot.bin")
        code, out = self._run(os.path.join(self.out, A + ".tabelle.json"), "--uboot", mine)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.seen["args"].uboot, mine)


class ForeignSunxiFel(unittest.TestCase):
    """The FEL step with a sunxi-fel whose banner names no H713: the distribution's stops there,
    ours goes on (to the missing U-Boot, exit 2, which is where this test ends)."""

    BANNER = "AWUSBFEX soc=00001860(unknown) 00000001 ver=0001 44 08 scratchpad=00121500"

    def setUp(self):
        self.tmp = support.workdir(self)
        for name in ("find_drive", "fel_present"):
            self.addCleanup(setattr, fel_mod, name, getattr(fel_mod, name))
        fel_mod.find_drive = lambda: []
        fel_mod.fel_present = lambda fel: self.BANNER

    def _fel(self, name, body):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(b"\x7fELF" + b"\0" * 60 + body)
        return path

    def _expose(self, fel):
        args = types.SimpleNamespace(device=None, fel=fel, uboot=None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = fel_mod.expose_drive(args, self.tmp)
        return result, out.getvalue()

    def test_the_distributions_sunxi_fel_stops_and_says_where_ours_is(self):
        fel = self._fel("sunxi-fel-distro", b"sunxi-fel v1.4.2")
        result, out = self._expose(fel)
        self.assertEqual(result, (None, 1), out)
        self.assertIn("%s does not know the H713 and is not the sunxi-fel of this project" % fel, out)
        self.assertIn("installer/out/", out)
        self.assertNotIn("Expose the eMMC", out)

    def test_ours_without_the_name_only_warns_as_before(self):
        result, out = self._expose(self._fel("sunxi-fel", b"Store entry point in the FEL trap door"))
        self.assertEqual(result, (None, 2), out)                 # --uboot is missing: step 2 reached
        self.assertIn("does not know this SoC by name", out)

    def test_fel_is_ours_reads_the_file_and_never_raises(self):
        self.assertTrue(fel_mod.fel_is_ours(self._fel("a", b"no FEL trap door found")))
        self.assertFalse(fel_mod.fel_is_ours(self._fel("b", b"sunxi-fel")))
        self.assertFalse(fel_mod.fel_is_ours(os.path.join(self.tmp, "nowhere")))


if __name__ == "__main__":
    unittest.main()
