"""TODO 5.26: a release image goes only onto the board it was built for.

Until 26.10.2026 h713-install compared a release image with the device by the eMMC's size alone,
and the L018 and the HY310 share it (15 269 888 sectors): either one's image went onto the other,
with a foreign device tree. Since then h713-mkimage writes the board into the table (key "board",
the installer's name for the unit, <board>/<variant> for a board with variants), and an older
table names it in its image name (h713-<board id>[-<variant>]-v<version>...). A known board that is
not the image's is refused, in a rehearsal too; a device whose board cannot be read (an install
older than 22.09.2026 left no /etc/h713/board) is a warning, as before.
"""

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
import warnings
from unittest import mock

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk
from test_hy200_qz713df_a1 import _inputs, _sparse_copy
from test_test_image import Recorder, _release

sys.path.insert(0, support.TOOLS)
from h713 import mkimage                                                       # noqa: E402
from h713.install import board_of_name, release_board_allowed, table_board    # noqa: E402

TOOL = os.path.join(support.TOOLS, "h713-install")


class TheBoardInTheName(unittest.TestCase):
    """The tables published before the key: v0.97-beta's two and v0.97.1-beta's one."""

    def test_the_published_names(self):
        for name, unit in (("h713-hy310-v0.97-beta-media-desktop", "hy310"),
                           ("h713-l018-v0.97.1-beta-media-desktop", "l018"),
                           ("h713-hy200-qz713df-a1-projector05061226-v0.97-beta-media-desktop",
                            "hy200_qz713df_a1/projector05061226"),
                           ("h713-hy310-v0.5-beta", "hy310"),
                           ("h713-hy300-t08-v0.11-TEST", "hy300_t08")):
            self.assertEqual(board_of_name(name), unit, name)

    def test_what_names_no_board(self):
        # hy300-pro's test images are named test<N>, not v<N>; a board with variants needs one
        for name in ("h713-hy300-pro-test11", "h713-hy310-vX", "h713-hy200-qz713df-a1-v0.97",
                     "something.img", "", None):
            self.assertIsNone(board_of_name(name), name)

    def test_the_key_beats_the_name(self):
        rel = os.path.join(support.workdir(self), "rel")
        table = _release(rel, name="h713-l018-v0.97.1-beta-media-desktop")
        self.assertEqual(table_board(table), ("l018", "name"))
        with open(table, encoding="utf-8") as fh:
            d = json.load(fh)
        d["board"] = "hy310"
        with open(table, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        self.assertEqual(table_board(table), ("hy310", "table"))
        self.assertEqual(table_board(os.path.dirname(table)), ("hy310", "table"))

    def test_no_table_no_board(self):
        plain = os.path.join(support.workdir(self), "plain.img")
        open(plain, "wb").close()
        self.assertEqual(table_board(plain), (None, None))


class Decision(unittest.TestCase):
    """release_board_allowed(), without a device."""

    def test_another_board_is_a_no(self):
        for writing in (True, False):
            log = Recorder()
            self.assertFalse(release_board_allowed("hy310", "l018", "name", writing, log))
            self.assertIn("This image is for the board 'l018' (its name). This device is 'hy310'",
                          log.text)
            self.assertIn("Take the release archive of your own board.", log.text)

    def test_its_own_board_is_a_yes(self):
        log = Recorder()
        self.assertTrue(release_board_allowed("hy200_qz713df_a1/projector05061226",
                                              "hy200_qz713df_a1/projector05061226", "table", True, log))
        self.assertIn("this device is that board", log.text)

    def test_a_board_that_cannot_be_read_is_a_warning(self):
        log = Recorder()
        self.assertTrue(release_board_allowed(None, "l018", "table", True, log))
        self.assertIn("could not be read, so that is not compared", log.text)
        log = Recorder()
        self.assertTrue(release_board_allowed(None, "l018", "table", False, log))
        self.assertIn("WOULD: compare the board of this device with the image's 'l018'", log.text)

    def test_an_image_that_names_no_board_is_not_compared(self):
        log = Recorder()
        self.assertTrue(release_board_allowed("hy310", None, None, True, log))
        self.assertEqual(log.text, "")


class MkimageWritesTheKey(unittest.TestCase):
    """h713-mkimage build --board puts "board" into the table; without it the key stays out."""

    def _build(self, directory, board):
        p = _inputs(os.path.join(directory, "in"))
        args = argparse.Namespace(out=os.path.join(directory, "out", "img.img"), spl=p["spl"],
                                  uboot=p["uboot"], env=p["env"], boot_ext4=p["boot"],
                                  rootfs_ext4=p["root"], test_for=None, board=board)
        with mock.patch.object(mkimage, "Ext4", lambda *a, **k: None), \
                mock.patch.object(mkimage, "ext4_check_tree", lambda *a, **k: []), \
                mock.patch.object(mkimage, "ext4_check_permissions", lambda *a, **k: None), \
                mock.patch.object(mkimage, "_copy", _sparse_copy), \
                contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            mkimage.build(args, here=support.TOOLS)
        with open(os.path.join(directory, "out", "img.tabelle.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_the_key(self):
        tmp = support.workdir(self)
        table = self._build(os.path.join(tmp, "l018"), "l018")
        self.assertEqual(table["board"], "l018")
        self.assertEqual(list(table)[:2], ["format", "board"])
        self.assertNotIn("board", self._build(os.path.join(tmp, "none"), None))

    def test_check_names_it(self):
        directory = os.path.join(support.workdir(self), "rel")
        table = _release(directory, name="h713-l018-v0.97.1-beta-media-desktop")
        with open(table, encoding="utf-8") as fh:
            d = json.load(fh)
        d["board"] = "l018"
        with open(table, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        log = Recorder()
        mkimage.check(table, log=log)
        self.assertIn("for the board profile 'l018'", log.text)

    def test_build_all_passes_the_board(self):
        script = os.path.join(os.path.dirname(support.TOOLS), "release", "build-all.sh")
        support.need([script])
        with open(script, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('--board "$TEST_PROFILE"', text)
        self.assertIn("TEST_PROFILE=$PROFILE${VARIANT:+/$VARIANT}", text)


class _Run(unittest.TestCase):

    def run_install(self, disk, table, *extra):
        with open(table, encoding="utf-8") as fh:
            image = os.path.join(os.path.dirname(table), json.load(fh)["teile"][0]["datei"])
        proc = subprocess.Popen(
            [sys.executable, TOOL, "install", image, "--table", table, "--device", disk,
             "--dump", os.path.join(self.tmp, "backup"), "--small", "--no-write"] + list(extra),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=self.tmp, env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        return proc.wait(), proc.communicate()[0].decode("utf-8", "replace")


class OnTheHY310(_Run):
    """The HY310 stock disk: the L018's release image has its size and is still refused."""

    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK + (TOOL,))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_stock_disk(os.path.join(self.tmp, "emmc.img"))
        self.before = fakedisk.journal(self.disk)

    def test_the_l018_image_is_refused(self):
        table = _release(os.path.join(self.tmp, "rel"), name="h713-l018-v0.97.1-beta-media-desktop")
        code, out = self.run_install(self.disk, table)
        self.assertEqual(code, 1, out)
        self.assertIn("This image is for the board 'l018' (its name). This device is 'hy310'", out)
        self.assertNotIn("Write onto the eMMC", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_its_own_image_goes_on(self):
        table = _release(os.path.join(self.tmp, "rel"), name="h713-hy310-v0.97-beta-media-desktop")
        code, out = self.run_install(self.disk, table)
        self.assertEqual(code, 0, out)
        self.assertIn("the image is for 'hy310' (its name) -- this device is that board", out)
        self.assertIn("No-write run -- nothing written.", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)

    def test_skip_identify_says_nothing_compares(self):
        table = _release(os.path.join(self.tmp, "rel"), name="h713-l018-v0.97.1-beta-media-desktop")
        code, out = self.run_install(self.disk, table, "--skip-identify")
        self.assertIn("with --skip-identify nothing compares that with this device", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)


class OverOurLayout(_Run):
    """Our layout and no full dump: a rehearsal cannot read the board and says what it would do."""

    OUR_PARTS = (("hy310-boot", 14336, 262144), ("hy310-rootfs", 276480, 2097152))

    def setUp(self):
        support.need((TOOL,))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_our_layout_disk(os.path.join(self.tmp, "ours.img"), self.OUR_PARTS)
        self.before = fakedisk.journal(self.disk)

    def test_the_rehearsal_names_the_comparison(self):
        table = _release(os.path.join(self.tmp, "rel"), name="h713-l018-v0.97.1-beta-media-desktop")
        code, out = self.run_install(self.disk, table)
        self.assertEqual(code, 0, out)
        self.assertIn("WOULD: compare the board of this device with the image's 'l018' (its name)", out)
        self.assertEqual(fakedisk.journal(self.disk), self.before, out)



class OverOurLayoutWithTheFirstDump(_Run):
    """Our layout and the full dump of the first install in --dump: the rehearsal knows the board
    from the dump (as for a test image since 23.09.2026) and compares -- the way the L018 was
    reinstalled with v0.97.1-beta (doku/223), here on the fake hy300-t08."""

    OUR_PARTS = (("hy310-boot", 14336, 262144), ("hy310-rootfs", 276480, 2097152))

    def setUp(self):
        support.need(fakedisk.needs_adt3("hy300-t08") + (TOOL,))
        self.tmp = support.workdir(self)
        first = _release(os.path.join(self.tmp, "first"), test_for="hy300_t08")
        stock = fakedisk.make_adt3_disk(os.path.join(self.tmp, "t08.img"), "hy300-t08")
        proc = subprocess.Popen(
            [sys.executable, TOOL, "install", os.path.join(self.tmp, "first"), "--table", first,
             "--device", stock, "--dump", os.path.join(self.tmp, "backup"), "--full", "--no-write",
             "--test-image"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=self.tmp, env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        code, out = proc.wait(), proc.communicate()[0].decode("utf-8", "replace")
        self.assertEqual(code, 0, out)                       # the first install's full dump
        self.ours = fakedisk.make_our_layout_disk(os.path.join(self.tmp, "ours.img"), self.OUR_PARTS)
        self.before = fakedisk.journal(self.ours)

    def test_its_own_image(self):
        table = _release(os.path.join(self.tmp, "rel"), name="h713-hy300-t08-v0.12")
        code, out = self.run_install(self.ours, table)
        self.assertEqual(code, 0, out)
        self.assertIn("the board is known from the dump of the first install", out)
        self.assertIn("the image is for 'hy300_t08' (its name) -- this device is that board", out)
        self.assertEqual(fakedisk.journal(self.ours), self.before, out)

    def test_another_boards_image(self):
        table = _release(os.path.join(self.tmp, "rel"), name="h713-l018-v0.97.1-beta-media-desktop")
        code, out = self.run_install(self.ours, table)
        self.assertEqual(code, 1, out)
        self.assertIn("the dump in", out)
        self.assertIn("This image is for the board 'l018' (its name). This device is 'hy300_t08'", out)
        self.assertEqual(fakedisk.journal(self.ours), self.before, out)

if __name__ == "__main__":
    unittest.main()
