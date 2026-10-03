# SPDX-License-Identifier: GPL-2.0
"""FB-INSTALL item 2 (doku/61 rows 81 and 82): `h713-install install` without an image finds
the release folder beside itself and asks only for the key and the dump directory; a `.zst`
part is read by Python 3.14's own zstd module where there is one, by the binary elsewhere.
expose_drive() is stood in for: under test is what main() has settled before the device."""

import contextlib
import gzip
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
from h713 import install as install_mod                                       # noqa: E402
from h713.install import (DUMP_DEFAULT, image_package, release_beside,        # noqa: E402
                          unpack_parts)

TOOL = os.path.join(support.TOOLS, "h713-install")
TABLE = "h713-hy310-v0.5-beta.tabelle.json"


def _release(directory):
    """The real v0.5-beta table with empty parts, u-boot-installer.bin and sunxi-fel beside it."""
    os.makedirs(directory)
    source = os.path.join(fakedisk.FIXTURES, "release", TABLE)
    support.need([source])
    shutil.copyfile(source, os.path.join(directory, TABLE))
    _dir, table = image_package(directory)
    for part in table["teile"]:
        open(os.path.join(directory, part["datei"]), "wb").close()
    for name in ("u-boot-installer.bin", "sunxi-fel"):
        with open(os.path.join(directory, name), "wb") as fh:
            fh.write(b"\x7fELF" + b"\0" * 60)
    return table


class WithoutAnImage(unittest.TestCase):
    def setUp(self):
        support.need([TOOL])
        self.tmp = support.workdir(self)
        self.release = os.path.join(self.tmp, "release")
        _release(self.release)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.release)
        spec = importlib.util.spec_from_loader(
            "h713_install_beside", importlib.machinery.SourceFileLoader("h713_install_beside", TOOL))
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.seen = {}
        self.tool.expose_drive = lambda args, here: (self.seen.update(args=args), (None, 0))[1]
        # ask() answers by a word of the prompt, else the default -- what a run without a
        # terminal gets; every prompt is recorded
        self.answers, self.asked = {}, []
        self.addCleanup(setattr, install_mod, "ask", install_mod.ask)
        self.addCleanup(setattr, install_mod, "ask_path", install_mod.ask_path)
        install_mod.ask = lambda text, default=None: (
            self.asked.append(text) or next((a for w, a in self.answers.items() if w in text), default))
        # the two prompts are paths since the deep review (ask_path keeps the case)
        install_mod.ask_path = lambda text, default="", **kw: (
            self.asked.append(text) or next((a for w, a in self.answers.items() if w in text), default))

    def _run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = self.tool.main(["install"] + list(argv))
        return code, out.getvalue()

    def test_the_folder_it_is_run_from_is_the_release_folder_and_the_defaults_stand(self):
        code, out = self._run("--no-write")
        self.assertEqual(code, 0, out)
        args = self.seen["args"]
        self.assertEqual(args.image, self.release)
        self.assertEqual(args.uboot, os.path.join(self.release, "u-boot-installer.bin"))
        self.assertEqual(args.fel, os.path.join(self.release, "sunxi-fel"))
        self.assertIn("release folder %s (found beside the tool)" % self.release, out)
        self.assertIsNone(args.ssh_key)                          # Enter, Enter
        self.assertEqual((args.dump_dir, args._dump_given), (DUMP_DEFAULT, False))
        self.assertEqual(len(self.asked), 2, self.asked)

    def test_it_asks_only_for_the_key_and_the_dump_directory(self):
        key = os.path.join(self.tmp, "id.pub")
        open(key, "w").close()
        self.answers = {"key": key, "Dump": os.path.join(self.tmp, "mine")}
        code, out = self._run("--no-write")
        self.assertEqual(code, 0, out)
        args = self.seen["args"]
        self.assertEqual(args.ssh_key, key)
        self.assertEqual((args.dump_dir, args._dump_given), (os.path.join(self.tmp, "mine"), True))
        self.assertTrue(all("key" in t or "Dump" in t for t in self.asked), self.asked)

    def test_a_key_file_that_is_not_there_stops_before_the_device(self):
        self.answers = {"key": os.path.join(self.tmp, "nowhere.pub")}
        code, out = self._run("--no-write")
        self.assertEqual((code, "args" in self.seen), (5, False), out)
        self.assertIn("nowhere.pub not found", out)

    def test_the_flags_beat_the_questions_and_a_named_folder_asks_nothing(self):
        key = os.path.join(self.tmp, "id.pub")
        open(key, "w").close()
        self._run("--ssh-key", key, "--dump", "there", "--no-write")
        args = self.seen["args"]
        self.assertEqual((args.ssh_key, args.dump_dir, args._dump_given), (key, "there", True))
        os.chdir(self.tmp)
        self.assertEqual(self._run(self.release, "--no-write")[0], 0)
        self.assertEqual((self.asked, self.seen["args"].image), ([], self.release))

    def test_no_table_anywhere_is_exit_5_and_says_where_it_looked(self):
        os.chdir(self.tmp)
        code, out = self._run("--no-write")
        self.assertEqual((code, "args" in self.seen), (5, False), out)
        self.assertIn("no *.tabelle.json in %s or in %s" % (self.tmp, os.path.dirname(TOOL)), out)
        self.assertIn("h713-install install RELEASE-DIR", out)

    def test_release_beside_takes_the_current_directory_first_then_the_tools_own(self):
        here = os.path.join(self.tmp, "installer")
        os.makedirs(here)
        os.chdir(self.tmp)
        self.assertIsNone(release_beside(here))
        open(os.path.join(here, "x.tabelle.json"), "w").close()
        self.assertEqual(release_beside(here), here)
        self.assertEqual(release_beside(os.path.join(self.tmp, "missing")), None)   # skipped
        os.chdir(self.release)
        self.assertEqual(release_beside(here), self.release)


class PackedPartsWithoutTheBinary(unittest.TestCase):
    """Python 3.14 reads .zst itself. On the interpreter that runs this the module is stood in
    for by gzip: under test is the plumbing -- the choice, the streaming copy, the file it
    leaves -- not zstd's format. The binary's path has its tests in test_installer_dryrun."""

    def setUp(self):
        self.release = os.path.join(support.workdir(self), "release")
        self.table = _release(self.release)
        self.name = self.table["teile"][0]["datei"]
        path = os.path.join(self.release, self.name)
        with gzip.open(path + ".zst", "wb") as fh:
            fh.write(b"h713" * 4096)
        os.remove(path)
        for attr in ("_zstd_module", "shutil"):
            self.addCleanup(setattr, install_mod, attr, getattr(install_mod, attr))
        install_mod._zstd_module = lambda: types.SimpleNamespace(open=gzip.open)

    def test_the_module_is_taken_before_the_binary_and_streams_the_file(self):
        install_mod.shutil = types.SimpleNamespace(
            which=lambda _n: self.fail("the binary was looked for"), copyfileobj=shutil.copyfileobj)
        log = support.Recorder()
        unpack_parts(self.release, self.table, log)
        with open(os.path.join(self.release, self.name), "rb") as fh:
            self.assertEqual(fh.read(), b"h713" * 4096)
        self.assertIn("unpacking %s.zst (Python's zstd" % self.name, log.text)

    def test_without_the_module_the_binary_is_looked_for_and_its_absence_named(self):
        install_mod._zstd_module = lambda: None
        install_mod.shutil = types.SimpleNamespace(which=lambda _n: None)
        with self.assertRaises(RuntimeError) as caught:
            unpack_parts(self.release, self.table, support.Recorder())
        self.assertIn(self.name + ".zst", str(caught.exception))
        self.assertIn("Python 3.14", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
