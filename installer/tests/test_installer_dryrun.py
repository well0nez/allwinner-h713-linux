"""hy310-install.py driven as a subprocess, the way a user drives it.

A regular file IS accepted as --device: main() takes any existing path given with
--device, Platte opens it with os.open(), and the size comes from lseek(SEEK_END).
So the two command lines below are the real ones."""

import os
import platform
import re
import subprocess
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from hy310-install.py 0.1: (exit code, lines, digest of the
# normalised stdout).  Normalisation replaces the temp directory, the device and
# the image path, and the platform name; nothing else in these runs varies.
DUMP_ONLY = (0, 36, "f75069a5c52094e4e29b3700f67b827576ef643d55915d8784c16794fc1dc5e2")
# was (0, 50, "da0ecc92e5649f29597bd72ca1da1fabe6954f0c756d1d068c9c5d13189f305c") until
# stage 2 C-C: still 50 lines, but UDISK's line turned from "genullt" into the new
# English "left untouched", private/Reserve0_b say who keeps them, and the two
# boot-resource.fex lines note the second copy in the container.
# C-C froze "3f61d6c1…" with UDISK in the default preserve list; UDISK is zeroed again (Fable, C-C review):
RESTORE_STOCK = (0, 50, "f89c3e441d75135c64456705eabaf4c5353ce28dabdec94e20b3467077aaef8c")


class InstallerDryRun(unittest.TestCase):
    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK + (support.INSTALL_PY, support.EXTRACT_PY))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_stock_disk(os.path.join(self.tmp, "emmc.img"))
        self.before = fakedisk.journal(self.disk)

    def run_tool(self, *args):
        proc = subprocess.Popen(
            [sys.executable, support.INSTALL_PY, "--device", self.disk] + list(args),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=self.tmp,
            env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        text = proc.communicate()[0].decode("utf-8", "replace")
        for needle, name in ((self.disk, "<DEV>"), (self.tmp, "<TMP>"),
                             (fakedisk.IMAGES["hy310"], "<IMG>"),
                             (platform.system(), "<PLATFORM>")):
            text = text.replace(needle, name)
        return proc.returncode, re.sub(r"[ \t]+$", "", text, flags=re.M)

    def check(self, frozen, got):
        code, lines, want = frozen
        self.assertEqual(got[0], code, got[1])
        self.assertEqual(len(got[1].splitlines()), lines, got[1])
        self.assertEqual(support.digest(got[1]), want, got[1])
        self.assertEqual(fakedisk.journal(self.disk), self.before, got[1])

    def test_backup_only(self):
        got = self.run_tool("--nur-abzug", "--sicherung", "backup", "--dry-run")
        self.check(DUMP_ONLY, got)
        self.assertIn("Stock-Layout, 26 Partitionen", got[1])
        for name in ("secure-storage", "private", "reserve0-a", "reserve0-b"):
            self.assertTrue(os.path.isfile(
                os.path.join(self.tmp, "backup", "%s.bin" % name)), name)

    def test_restore_stock(self):
        support.need([fakedisk.IMAGES["hy310"]])
        got = self.run_tool("--restore-stock", fakedisk.IMAGES["hy310"], "--dry-run")
        self.check(RESTORE_STOCK, got)
        self.assertIn("Trockenlauf -- nichts geschrieben.", got[1])


class NoMandatoryDumpOnOurLayout(unittest.TestCase):
    """Stage 2 C5: on our own layout the restore paths take no mandatory small dump."""

    def test_no_mandatory_dump_on_our_layout(self):
        support.need(fakedisk.NEEDS_V3)
        tmp = support.workdir(self)
        disk = fakedisk.make_v3_disk(os.path.join(tmp, "emmc-v3.img"))
        proc = subprocess.run(
            [sys.executable, support.INSTALL_PY, "--device", disk, "--restore-stock",
             fakedisk.IMAGES["hy310"], "--sicherung", os.path.join(tmp, "backup"), "--ohne-erkennung"],
            input="nein\n", capture_output=True, text=True, cwd=tmp)
        out = proc.stdout + proc.stderr
        self.assertNotIn("Kleiner Abzug (Pflicht", out)
        self.assertIn("no mandatory dump before the restore", out)
        self.assertFalse(os.path.exists(os.path.join(tmp, "backup")))
        self.assertEqual(proc.returncode, 1, out)          # refused at the JA prompt, nothing written
