# SPDX-License-Identifier: GPL-2.0
"""R1 item 3: the two follow-ups O1b left open (reviews/O1b.md, doku/61).

(a) `install` reads the device's own files out of the `emmc-full.img` that lies in the dump
    directory. `dump` has asked since O1b whether that file is whole; `install` took it as it
    found it, so an aborted dump -- shorter than the device, and what is missing is its tail --
    went into the image. It now asks the same question with the same sentence and stops.

(b) `identify` picked `private`/`Reserve0*` out of a partition table with a copy of its own and
    no fallback, while `dump` had BY_NAME plus HY310_FALLBACK. On a stock table that names
    neither the two judged the same device differently. There is one helper now
    (`dump.unique_regions()`), and the test below drives both sides over one fake table that
    has no `private` and proves they come out the same, down to where each LBA came from.

Everything here runs on fake disks built from the repository's own fixtures.
"""

import argparse
import contextlib
import io
import json
import os
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.blockdev import Disk, LOCK_FIRST, LOCK_LAST, SECT, SECTORS_EXPECTED   # noqa: E402
from h713.dump import HY310_FALLBACK, dump_small, regions_from_gpt, write_manifest  # noqa: E402
from h713.identify import identify                                              # noqa: E402
from h713.install import DUMP_FULL, full_dump_problem, write_package            # noqa: E402

DISK_SECTORS = 32768                       # 16 MiB: every region of these runs is inside it
# A stock table with a Reserve0 but no `private` -- the half of the case O1b never covered.
NO_PRIVATE = tuple(p for p in fakedisk.MOVED_PARTS if p[0] != "private")
NEITHER = tuple(p for p in fakedisk.MOVED_PARTS if p[0] not in ("private", "Reserve0"))


def _capture(call):
    """What the run printed on stdout and stderr, plus its return value."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        value = call()
    return value, out.getvalue() + err.getvalue()


class TheFullDumpInstallReadsFrom(unittest.TestCase):
    """Item (a), on the question alone and then through write_package()."""

    def setUp(self):
        self.tmp = support.workdir(self)
        self.dump_dir = os.path.join(self.tmp, "backup")
        os.makedirs(self.dump_dir)
        self.full = os.path.join(self.dump_dir, DUMP_FULL)

    def _clone(self, sectors, manifest_sectors=DISK_SECTORS, manifest=True):
        with open(self.full, "wb") as fh:
            fh.truncate(sectors * SECT)
        if manifest:
            with open(os.path.join(self.dump_dir, "MANIFEST.json"), "w") as fh:
                json.dump({"regions": [{"name": "emmc-full", "lba": 0,
                                        "sectors": manifest_sectors, "sha256": None,
                                        "purpose": "complete clone"}]}, fh)

    def test_a_whole_clone_is_no_problem(self):
        self._clone(DISK_SECTORS)
        log = support.Recorder()
        self.assertIsNone(full_dump_problem(self.dump_dir, self.full, DISK_SECTORS, log))
        self.assertEqual(log.lines, [])

    def test_an_aborted_dump_is_named_in_the_words_dump_uses(self):
        self._clone(DISK_SECTORS - 1)
        log = support.Recorder()
        why = full_dump_problem(self.dump_dir, self.full, DISK_SECTORS, log)
        self.assertEqual(why, "%s is incomplete: %d bytes, the manifest records %d (%.1f MiB)"
                         % (DUMP_FULL, (DISK_SECTORS - 1) * SECT, DISK_SECTORS * SECT,
                            DISK_SECTORS * SECT / (1 << 20)))

    def test_a_clone_of_another_device_is_named(self):
        self._clone(DISK_SECTORS, manifest_sectors=DISK_SECTORS * 2)
        self.assertIn("was taken off a disk of", full_dump_problem(
            self.dump_dir, self.full, DISK_SECTORS, support.Recorder()))

    def test_a_clone_without_a_manifest_row_but_the_right_length_is_used_and_said(self):
        # A dump of v0.5-beta carries German manifest keys, and a clone copied here by hand
        # carries no manifest at all. Neither is an aborted dump, and the way back through an
        # old dump has to stay open -- so it is said, not refused.
        self._clone(DISK_SECTORS, manifest=False)
        log = support.Recorder()
        self.assertIsNone(full_dump_problem(self.dump_dir, self.full, DISK_SECTORS, log))
        self.assertIn("no MANIFEST.json row names it", log.text)
        self.assertIn("exactly %d sectors all the same" % DISK_SECTORS, log.text)

    # ------------------------------------------------------------------ through the installer

    def _table(self):
        return {"format": "hy310-abbild-tabelle-v4", "abbild": "r1-test", "layout": "v4",
                "disk_sektoren": SECTORS_EXPECTED,
                "loch": {"lba": LOCK_FIRST, "sektoren": LOCK_LAST - LOCK_FIRST + 1,
                         "partition": "hy310-keys"},
                "teile": [{"datei": "part-b.img", "lba": 16384, "sektoren": 64,
                           "bytes": 64 * SECT, "sha256": None}],
                "partitionen": [{"name": "hy310-boot", "lba": 16384, "sektoren": 64}],
                "gruppen": {"logo": "boot logo"},
                "dateien": [{"name": "boot/bootlogo.bmp", "partition": "hy310-boot",
                             "pfad": "/bootlogo.bmp", "gruppe": "logo"}],
                "nutzer": []}

    def _install(self):
        directory = os.path.join(self.tmp, "release")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "part-b.img"), "wb") as fh:
            fh.truncate(64 * SECT)
        path = os.path.join(self.tmp, "emmc.img")
        with open(path, "wb") as fh:
            fh.truncate(DISK_SECTORS * SECT)
        args = argparse.Namespace(no_write=True, vendor=None, ssh_key=None, work_copy=None,
                                  dump_dir=self.dump_dir, fresh_env=True, command="install",
                                  size=None, _our_layout=False, _dump_given=True)
        disk = Disk(path, writable=False)
        try:
            return _capture(lambda: write_package(args, disk, path, directory, self._table()))
        finally:
            disk.close()

    def test_install_stops_on_an_aborted_dump_and_points_at_dump_full(self):
        self._clone(DISK_SECTORS - 1)
        code, text = self._install()
        self.assertEqual(code, 8, text)
        self.assertIn("is incomplete:", text)
        self.assertIn("h713-install dump --full", text)
        self.assertNotIn("h713-extract", text)          # it never got that far


class OneHelperForBothTools(unittest.TestCase):
    """Item (b): dump and identify over the same table, with and without the fallback."""

    def _disk(self, partitions):
        path = fakedisk.make_moved_stock_disk(os.path.join(support.workdir(self), "emmc.img"),
                                              partitions)
        disk = Disk(path, writable=False)
        self.addCleanup(disk.close)
        return disk

    def _both(self, partitions):
        disk = self._disk(partitions)
        dump_sources = {}
        dump_side = regions_from_gpt(disk, fallback=True, sources=dump_sources)
        with support.quiet():
            ident = identify(disk)
        return ident, dump_side, dump_sources, disk

    def test_a_stock_table_without_private_is_judged_the_same_by_both(self):
        ident, dump_side, dump_sources, _disk = self._both(NO_PRIVATE)
        self.assertEqual(ident["kind"], "stock")
        self.assertEqual(dict(ident["regions"]), dict(dump_side))
        self.assertEqual(ident["region_sources"], dump_sources)
        # Reserve0 is read off this table, private is the HY310's constant -- both sides.
        self.assertEqual(dump_sources["Reserve0"], "gpt")
        self.assertEqual(dump_sources["private"], "hy310-constant")
        self.assertEqual(ident["regions"]["private"], HY310_FALLBACK[0][1:])
        self.assertEqual(ident["regions"]["Reserve0"],
                         dict((n, (l, s)) for n, l, s in NO_PRIVATE)["Reserve0"])

    def test_identify_says_which_names_it_had_to_guess(self):
        ident, _dump_side, _sources, _disk = self._both(NO_PRIVATE)
        said = [line for line in ident["text"] if "stand in above" in line]
        self.assertEqual(len(said), 1, ident["text"])
        self.assertIn("this table names no private", said[0])
        self.assertIn("a guess, not a reading", said[0])

    def test_a_table_with_neither_region_is_judged_the_same_by_both(self):
        ident, dump_side, dump_sources, _disk = self._both(NEITHER)
        self.assertEqual(dict(ident["regions"]), dict(dump_side))
        self.assertEqual(sorted(ident["regions"]),
                         sorted(["secure-storage"] + [n for n, _l, _s in HY310_FALLBACK]))
        self.assertEqual(sorted(n for n, w in ident["region_sources"].items()
                                if w == "hy310-constant"),
                         sorted(n for n, _l, _s in HY310_FALLBACK))

    def test_the_dump_written_from_that_table_lands_where_identify_says(self):
        """The whole way: the small dump of the same disk writes its regions at the LBAs
        identify printed, and MANIFEST.json marks the guessed ones."""
        ident, _dump_side, _sources, disk = self._both(NO_PRIVATE)
        out = os.path.join(support.workdir(self), "backup")
        manifest = dump_small(disk, out, log=support.Recorder(), our_layout=False)
        write_manifest(out, manifest, disk.path)
        with open(os.path.join(out, "MANIFEST.json"), encoding="utf-8") as fh:
            rows = dict((row["name"], row) for row in json.load(fh)["regions"])
        self.assertEqual((rows["private"]["lba"], rows["private"]["source"]),
                         (ident["regions"]["private"][0], "hy310-constant"))
        self.assertEqual((rows["reserve0"]["lba"], rows["reserve0"]["source"]),
                         (ident["regions"]["Reserve0"][0], "gpt"))

    def test_our_own_layout_guesses_nothing_on_either_side(self):
        path = fakedisk.make_our_layout_disk(
            os.path.join(support.workdir(self), "emmc.img"),
            [("hy310-keys", 12288, 2048), ("hy310-boot", 16384, 8192)], DISK_SECTORS)
        disk = Disk(path, writable=False)
        self.addCleanup(disk.close)
        with support.quiet():
            ident = identify(disk)
        self.assertEqual(ident["kind"], "ours")
        self.assertEqual(list(ident["regions"]), ["secure-storage"])
        self.assertEqual(dict(ident["regions"]), dict(regions_from_gpt(disk, fallback=False)))


if __name__ == "__main__":
    unittest.main()
