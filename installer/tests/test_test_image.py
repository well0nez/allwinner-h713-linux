"""Stage 5, the test-image route: `h713-mkimage build --test-for PROFILE` marks a table, and
`h713-install install ... --test-image` writes such an image only on the board it was built for.

The rule it implements (plan/stufe-5.md, doku/121 §5): no image for a board nobody has tested --
a test image is how a board gets tested, built on purpose, named as such, flashed by its owner,
accepted by the installer only on that board and only when asked for.

Nothing here freezes a golden value: a normal table carries no `test_for` at all, which is what
the first test asserts against the released v0.5-beta table.
"""

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.blockdev import SECTORS_EXPECTED                          # noqa: E402
from h713.env import ENV_BYTES, env_read, env_write                 # noqa: E402
from h713.install import (table_test_for, test_image_allowed,       # noqa: E402
                          write_env_keys)
from h713.mkimage import LOCK_FIRST, LOCK_LAST, readme_text         # noqa: E402

TOOL = os.path.join(support.TOOLS, "h713-install")
SECT = 512
PART_LBA = 14336                      # part B of layout v3 -- where the placeholders would sit


def _tool_module():
    """h713-install as a module (it has no .py suffix, so it is loaded by path)."""
    support.need([TOOL])
    spec = importlib.util.spec_from_loader(
        "h713_install_testimage", importlib.machinery.SourceFileLoader("h713_install_testimage", TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder(object):
    """The installer's console shape, remembering what was said."""

    def __init__(self):
        self.lines = []

    def _add(self, text):
        self.lines.append(text)

    ok = info = warn = error = _add

    def step(self, number, what):
        self.lines.append("[%s] %s" % (number, what))

    @property
    def text(self):
        return "\n".join(self.lines)


def _release(directory, test_for=None, name="h713-hy300-t08-v0.11-TEST"):
    """A minimal but real release: one part at LBA 14336 and the table that describes it.
    Enough for check_package(); the placeholders are what a bigger image adds, not this."""
    os.makedirs(directory, exist_ok=True)
    part = name + "-b-system.img"
    body = b"H713 test image\n" * (1 << 12)
    with open(os.path.join(directory, part), "wb") as fh:
        fh.write(body)
    table = {"format": "hy310-abbild-tabelle"}
    if test_for:
        table["test_for"] = test_for
    table.update({
        "version": 1, "werkzeug": "h713-mkimage 0.1", "erzeugt": "2026-09-15T00:00:00",
        "abbild": name, "sektorgroesse": SECT, "disk_sektoren": SECTORS_EXPECTED,
        "layout": "v3 (doku/109 §2.2)",
        "loch": {"lba": LOCK_FIRST, "sektoren": LOCK_LAST - LOCK_FIRST + 1,
                 "partition": "hy310-keys", "warum": "secure storage"},
        "teile": [{"datei": part, "lba": PART_LBA, "sektoren": len(body) // SECT,
                   "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}],
        "platzhalter_datei": part, "platzhalter": {}, "platzhalter_nutzer": {},
        "platzhalter_info": {},
    })
    path = os.path.join(directory, name + ".tabelle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    return path


class TableKey(unittest.TestCase):
    """The key is new, optional, and absent from every table built so far."""

    def test_a_released_table_carries_no_test_for(self):
        released = os.path.join(fakedisk.FIXTURES, "release",
                                "h713-hy310-v0.5-beta.tabelle.json")
        support.need([released])
        with open(released, encoding="utf-8") as fh:
            self.assertNotIn("test_for", json.load(fh))
        self.assertIsNone(table_test_for(released))

    def test_a_marked_table_is_read_before_the_device_is_touched(self):
        table = _release(os.path.join(support.workdir(self), "rel"), test_for="hy300_t08")
        self.assertEqual(table_test_for(table), "hy300_t08")
        self.assertEqual(table_test_for(os.path.dirname(table)), "hy300_t08")
        self.assertEqual(table_test_for("nothing-here.img", table), "hy300_t08")

    def test_something_that_is_no_table_is_not_an_error_here(self):
        tmp = support.workdir(self)
        plain = os.path.join(tmp, "plain.img")
        open(plain, "wb").close()
        self.assertIsNone(table_test_for(plain))
        self.assertIsNone(table_test_for(os.path.join(tmp, "does-not-exist.json")))


class MkimageTestFor(unittest.TestCase):
    """`build --test-for` puts the key next to `format`, and `check` and the README say so."""

    def test_the_key_sits_next_to_format(self):
        table = _release(os.path.join(support.workdir(self), "rel"), test_for="hy300_pro")
        with open(table, encoding="utf-8") as fh:
            keys = list(json.load(fh).keys())
        self.assertEqual(keys[:2], ["format", "test_for"])

    def test_the_readme_names_the_board_and_the_way_back(self):
        with open(_release(os.path.join(support.workdir(self), "rel"),
                           test_for="hy300_pro"), encoding="utf-8") as fh:
            marked = json.load(fh)
        text = readme_text(marked)
        self.assertIn("TEST IMAGE for hy300_pro", text)
        self.assertIn("--test-image", text)
        self.assertIn("dump --full", text)
        plain = dict(marked)
        del plain["test_for"]
        self.assertNotIn("TEST IMAGE", readme_text(plain))

    def test_check_prints_the_test_for_line(self):
        from h713.mkimage import check
        directory = os.path.join(support.workdir(self), "rel")
        table = _release(directory, test_for="hy300_pro")
        log = Recorder()
        check(table, log=log)            # the parts are not a real image; the line is the point
        self.assertIn("TEST IMAGE for the board profile 'hy300_pro'", log.text)

    def test_the_flag_reaches_the_table_through_the_tool(self):
        """h713-mkimage build --test-for: the flag exists and is carried into build()."""
        mk = os.path.join(support.TOOLS, "h713-mkimage")
        support.need([mk])
        spec = importlib.util.spec_from_loader(
            "h713_mkimage_flag", importlib.machinery.SourceFileLoader("h713_mkimage_flag", mk))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.parser().parse_args(["build", "-o", "x.img", "--test-for", "hy300_pro"])
        self.assertEqual(args.test_for, "hy300_pro")
        self.assertIsNone(module.parser().parse_args(["build", "-o", "x.img"]).test_for)


class Decision(unittest.TestCase):
    """test_image_allowed(): the two conditions, without a device."""

    def test_the_right_board_with_the_flag_is_a_yes(self):
        log = Recorder()
        self.assertTrue(test_image_allowed({"profile": "hy300_t08", "_lines": []},
                                           "hy300_t08", True, log))
        self.assertIn("TEST IMAGE for 'hy300_t08'", log.text)

    def test_the_right_board_without_the_flag_is_a_no(self):
        log = Recorder()
        self.assertFalse(test_image_allowed({"profile": "hy300_t08", "_lines": []},
                                            "hy300_t08", False, log))
        self.assertIn("written only when you ask", log.text)

    def test_another_board_is_a_no_even_with_the_flag(self):
        log = Recorder()
        self.assertFalse(test_image_allowed({"profile": "hy310", "_lines": []},
                                            "hy300_t08", True, log))
        self.assertIn("This device is 'hy310'", log.text)
        self.assertIn("dump --full", log.text)

    def test_an_unknown_board_is_a_no_too(self):
        log = Recorder()
        self.assertFalse(test_image_allowed({"_lines": []}, "hy300_t08", True, log))
        self.assertIn("no board we know", log.text)


class _Run(unittest.TestCase):
    """Drives h713-install as a subprocess against a fake disk, as a user would."""

    def run_install(self, disk, table, *extra):
        with open(table, encoding="utf-8") as fh:
            image = os.path.join(os.path.dirname(table), json.load(fh)["teile"][0]["datei"])
        proc = subprocess.Popen(
            [sys.executable, TOOL, "install", image, "--table", table, "--device", disk,
             "--dump", os.path.join(self.tmp, "backup"), "--small", "--no-write"] + list(extra),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=self.tmp, env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        return proc.wait(), proc.communicate()[0].decode("utf-8", "replace")


class OnTheBoardItIsFor(_Run):
    """The fake ADT-3 disk of hy300-t08: a board we hold a profile for and nobody has run."""

    def setUp(self):
        support.need(fakedisk.needs_adt3("hy300-t08") + (TOOL,))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_adt3_disk(os.path.join(self.tmp, "t08.img"), "hy300-t08")
        self.before = fakedisk.journal(self.disk)
        self.table = _release(os.path.join(self.tmp, "rel"), test_for="hy300_t08")

    def test_without_the_flag_it_is_refused(self):
        code, out = self.run_install(self.disk, self.table)
        self.assertEqual(code, 1, out)
        self.assertIn("TEST IMAGE for the board 'hy300_t08'", out)
        self.assertIn("written only when you ask", out)
        self.assertNotIn("Write onto the eMMC", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_with_the_flag_it_is_accepted(self):
        code, out = self.run_install(self.disk, self.table, "--test-image")
        self.assertEqual(code, 0, out)
        self.assertIn("TEST IMAGE for 'hy300_t08'", out)
        self.assertIn("No-write run -- nothing written.", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_an_unmarked_image_takes_the_old_road(self):
        """Without the key nothing changes: report_device() keeps the verdict it always had
        -- a rehearsal is allowed to go on, a real write on this board is not (exit 10)."""
        plain = _release(os.path.join(self.tmp, "rel-plain"), name="h713-hy300-t08-v0.11")
        code, out = self.run_install(self.disk, plain)
        self.assertEqual(code, 0, out)
        self.assertNotIn("TEST IMAGE", out)
        self.assertIn("This board is known (profile 'hy300_t08')", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_the_flag_on_an_unmarked_image_says_it_changes_nothing(self):
        plain = _release(os.path.join(self.tmp, "rel-plain"), name="h713-hy300-t08-v0.11")
        code, out = self.run_install(self.disk, plain, "--test-image")
        self.assertEqual(code, 0, out)
        self.assertIn("this table carries no test_for", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_skip_identify_does_not_open_the_door(self):
        code, out = self.run_install(self.disk, self.table, "--test-image", "--skip-identify")
        self.assertEqual(code, 1, out)
        self.assertIn("not written with --skip-identify", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)


class OnAnotherBoard(_Run):
    """The same image on the HY310 stock disk: right tool, wrong device."""

    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK + (TOOL,))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_stock_disk(os.path.join(self.tmp, "emmc.img"))
        self.before = fakedisk.journal(self.disk)
        self.table = _release(os.path.join(self.tmp, "rel"), test_for="hy300_t08")

    def test_the_flag_does_not_help_on_the_wrong_board(self):
        code, out = self.run_install(self.disk, self.table, "--test-image")
        self.assertEqual(code, 1, out)
        self.assertIn("This is a TEST IMAGE for the board 'hy300_t08'", out)
        self.assertIn("This device is 'hy310'", out)
        self.assertNotIn("Write onto the eMMC", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)


class DeclaredProjectOnATestBoard(unittest.TestCase):
    """Stage 2 C9 on the test-image route: what the board declares still reaches the image.

    hy300_t08 declares ProjectID 52 = 0x34 in Reserve0's panel_config.ini. The identification
    reads it off the board's own firmware, and write_env_keys() puts it into the environment
    block of the working copy -- that is the whole chain the installer walks on such a board.
    """

    def test_the_profile_declares_0x34(self):
        from h713.profiles import PROFILES
        self.assertEqual(PROFILES["hy300_t08"]["panel"]["declared_project_id"], 0x34)

    def test_the_declared_id_is_read_and_written(self):
        support.need([fakedisk.IMAGES["hy300-t08"]])
        import pathlib

        import h713.identify
        from h713.source import FileSource
        ident = h713.identify.identify(FileSource(pathlib.Path(fakedisk.IMAGES["hy300-t08"])))
        self.assertEqual(ident.get("profile"), "hy300_t08")
        project = _tool_module()._declared_project(ident)
        self.assertEqual(project, "0x34")

        work = os.path.join(support.workdir(self), "part-b.img")
        with open(work, "wb") as fh:
            fh.write(b"\xaa" * (4 * SECT))
            fh.write(env_write({"bootcmd": "run boot_emmc", "h713_gate": "1"}))
            fh.write(b"\x55" * (4 * SECT))
        tab = {"bausteine": {"env": {"lba": PART_LBA + 4}},
               "teile": [{"datei": "b.img", "lba": PART_LBA}]}
        self.assertEqual(write_env_keys(tab, work, "b.img", {"h713_project": project},
                                        Recorder()), 0)
        with open(work, "rb") as fh:
            fh.seek(4 * SECT)
            env = env_read(fh.read(ENV_BYTES))
        self.assertEqual(env["h713_project"], "0x34")
        self.assertEqual(env["h713_gate"], "1")


if __name__ == "__main__":
    unittest.main()
