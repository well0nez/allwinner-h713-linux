# SPDX-License-Identifier: GPL-2.0
"""O1b: the two corrections to the dump.

Item 1 -- a complete `emmc-full.img` is the way back and is never overwritten by accident
(seen 15.09.2026: a second `--full` run into the same directory truncated it). `install --full`
reuses it instead of dumping 7.3 GB a second time, `dump --full` keeps it and says so, `--force`
takes a new one, and only an incomplete clone is named and replaced.

Item 2 -- `private` and `Reserve0*` come out of the device's own GPT by name. Only a table that
names neither falls back to the HY310's LBAs, and then the run says which region it guessed and
MANIFEST.json marks the row. The secure storage stays the raw constant at LBA 12288 either way.

Nothing here is frozen: every value is derived from the fake disk it was written onto, and the
fake disks need no vendor bytes, so all of this runs in the default mode of run.sh.
"""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.blockdev import Disk                                          # noqa: E402
from h713.dump import (HY310_FALLBACK, SECURE_STORAGE, dump_small,      # noqa: E402
                       write_manifest)

SECT = 512
TOOL = os.path.join(support.TOOLS, "h713-install")
FULL = "emmc-full.img"
MOVED = dict((n, (lba, s)) for n, lba, s in fakedisk.MOVED_PARTS)
NO_ANDROID_PARTS = tuple(p for p in fakedisk.MOVED_PARTS
                         if p[0] not in ("private", "Reserve0"))
# Item 1 runs a real `--full`, so its disk is 16 MiB and not 7.3 GB. Our layout is on it: the
# small dump then takes the secure storage and nothing else, which keeps every region of those
# runs inside the file.
SMALL_SECTORS = 32768
SMALL_PARTS = [("hy310-keys", 12288, 2048), ("hy310-env", 14336, 2048),
               ("hy310-boot", 16384, 8192)]


def _rows(directory):
    """The region rows of a MANIFEST.json, by name."""
    with open(os.path.join(directory, "MANIFEST.json"), encoding="utf-8") as fh:
        return dict((row["name"], row) for row in json.load(fh)["regions"])


def _read(directory, name):
    with open(os.path.join(directory, name), "rb") as fh:
        return fh.read()


class RegionsComeFromTheDevicesOwnTable(unittest.TestCase):
    """Item 2, on three fake disks: a table that moves the two regions, one that has neither,
    and our own layout, which is meant to guess nothing at all."""

    def _small(self, make, our_layout=False):
        """Fake disk, small dump, manifest -> (manifest, log, dump directory)."""
        tmp = support.workdir(self)
        path = make(os.path.join(tmp, "emmc.img"))
        out, log = os.path.join(tmp, "backup"), support.Recorder()
        disk = Disk(path, writable=False)
        try:
            manifest = dump_small(disk, out, log=log, our_layout=our_layout)
        finally:
            disk.close()
        write_manifest(out, manifest, path)
        return manifest, log, out

    def test_a_table_that_moves_the_two_regions_is_followed_not_the_hy310_lbas(self):
        manifest, log, out = self._small(fakedisk.make_moved_stock_disk)
        rows = _rows(out)
        for file_name, part in (("private", "private"), ("reserve0", "Reserve0")):
            lba, sectors = MOVED[part]
            self.assertEqual((rows[file_name]["lba"], rows[file_name]["sectors"],
                              rows[file_name]["source"]), (lba, sectors, "gpt"), file_name)
            self.assertEqual(_read(out, "%s.bin" % file_name),
                             fakedisk.pattern(part, lba, sectors), file_name)
        self.assertIs(manifest.info["regions_by_name"], True)
        self.assertNotIn("HY310's own LBAs", log.text)
        # The secure storage has no partition entry anywhere: raw constant, both disks.
        self.assertEqual((rows["secure-storage"]["lba"], rows["secure-storage"]["sectors"],
                          rows["secure-storage"]["source"]),
                         (SECURE_STORAGE[1], SECURE_STORAGE[2], "fixed"))
        self.assertEqual(_read(out, "secure-storage.bin"),
                         fakedisk.pattern("secure-storage", *SECURE_STORAGE[1:]))

    def test_a_table_with_neither_region_falls_back_to_the_hy310_lbas_and_says_so(self):
        name, lba, sectors = HY310_FALLBACK[0]

        def make(path):
            """The HY310's own private LBA is filled, so the fallback can be traced to it."""
            fakedisk.make_moved_stock_disk(path, NO_ANDROID_PARTS)
            with open(path, "r+b") as fh:
                fh.seek(lba * SECT)
                fh.write(fakedisk.pattern(name, lba, sectors))
            return path

        manifest, log, out = self._small(make)
        rows = _rows(out)
        self.assertEqual([(rows[n]["lba"], rows[n]["sectors"], rows[n]["source"])
                          for n in ("private", "reserve0-a", "reserve0-b")],
                         [(l, s, "hy310-constant") for _n, l, s in HY310_FALLBACK])
        self.assertEqual(_read(out, "private.bin"), fakedisk.pattern(name, lba, sectors))
        self.assertIn("names no private, Reserve0_a, Reserve0_b", log.text)
        self.assertIn("HY310's own LBAs", log.text)
        self.assertIs(manifest.info["regions_by_name"], False)

    def test_our_own_layout_guesses_nothing(self):
        # It has no `private` and no `Reserve0*` at all; 48 MiB of zeros off the HY310's LBAs
        # would be a backup of nothing.
        manifest, log, out = self._small(
            lambda p: fakedisk.make_our_layout_disk(p, SMALL_PARTS, SMALL_SECTORS),
            our_layout=True)
        self.assertEqual([row[0] for row in manifest], ["secure-storage"])
        self.assertEqual(_rows(out)["secure-storage"]["source"], "fixed")
        self.assertNotIn("HY310's own LBAs", log.text)


class FullDumpIsNeverOverwrittenByAccident(unittest.TestCase):
    """Item 1, against the tool's own step 3 (`_dump`) on a 16 MiB fake disk."""

    def setUp(self):
        support.need([TOOL])
        spec = importlib.util.spec_from_loader(          # the tool has no .py suffix
            "h713_install_o1b", importlib.machinery.SourceFileLoader("h713_install_o1b", TOOL))
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.tmp = support.workdir(self)
        path = fakedisk.make_our_layout_disk(os.path.join(self.tmp, "emmc.img"),
                                             SMALL_PARTS, SMALL_SECTORS)
        self.dump_dir = os.path.join(self.tmp, "backup")
        self.disk = Disk(path, writable=False)
        self.addCleanup(self.disk.close)

    def _run(self, command="dump", **extra):
        args = argparse.Namespace(size="full", dump_dir=self.dump_dir, with_vendor=False,
                                  force=False, no_write=False, _our_layout=True,
                                  _dump_given=True, command=command)
        for key, value in extra.items():
            setattr(args, key, value)
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = self.tool._dump(args, self.disk, self.disk.path)
        self.assertEqual(code, 0, text.getvalue())
        return text.getvalue()

    def _mark(self):
        """The first bytes of the clone -- a run that took it again cannot leave them."""
        return _read(self.dump_dir, FULL)[:8]

    def _first(self):
        """The clone this directory is supposed to keep, marked so that a second run which
        overwrote it could not hide."""
        text = self._run()
        self.assertEqual(os.path.getsize(os.path.join(self.dump_dir, FULL)),
                         SMALL_SECTORS * SECT, text)
        with open(os.path.join(self.dump_dir, FULL), "r+b") as fh:
            fh.write(b"O1b-MARK")

    def test_a_second_dump_full_keeps_the_clone_and_says_so_in_one_line(self):
        self._first()
        text = self._run()
        self.assertEqual(self._mark(), b"O1b-MARK", text)
        said = [line for line in text.splitlines() if "kept as it is" in line]
        self.assertEqual(len(said), 1, text)
        self.assertIn("--force takes a new one", said[0])
        self.assertNotIn("that takes a while", text)
        self.assertIn("emmc-full", _rows(self.dump_dir))   # the manifest still names it

    def test_force_takes_the_clone_again(self):
        self._first()
        text = self._run(force=True)
        self.assertNotEqual(self._mark(), b"O1b-MARK", text)
        self.assertIn("that takes a while", text)

    def test_an_incomplete_clone_is_named_with_both_sizes_and_replaced(self):
        self._first()
        full = os.path.join(self.dump_dir, FULL)
        with open(full, "r+b") as fh:
            fh.truncate(SMALL_SECTORS * SECT - SECT)
        text = self._run()
        self.assertIn("%s is incomplete: %d bytes, the manifest records %d"
                      % (FULL, SMALL_SECTORS * SECT - SECT, SMALL_SECTORS * SECT), text)
        self.assertEqual(os.path.getsize(full), SMALL_SECTORS * SECT)
        self.assertNotEqual(self._mark(), b"O1b-MARK", text)

    def test_a_clone_no_manifest_row_names_is_replaced(self):
        os.makedirs(self.dump_dir)
        with open(os.path.join(self.dump_dir, FULL), "wb") as fh:
            fh.write(b"O1b-MARK" + b"\0" * (SMALL_SECTORS * SECT - 8))
        text = self._run()
        self.assertIn("no MANIFEST.json row names it", text)
        self.assertNotEqual(self._mark(), b"O1b-MARK", text)

    def test_install_full_reuses_the_clone_instead_of_dumping_again(self):
        self._first()
        text = self._run(command="install")
        self.assertEqual(self._mark(), b"O1b-MARK", text)
        self.assertIn("reused, no second 17-minute dump", text)
        self.assertNotIn("that takes a while", text)


if __name__ == "__main__":
    unittest.main()
