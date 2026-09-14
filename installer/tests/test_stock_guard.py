"""Stage 2 C-C: what the stock restore refuses to do.

The mips/ guard, the duplicate entries of the IMAGEWTY file table, the write journal
of the preserve list, and the promise that a dry run does not read the payload.
These tests call the package directly -- they are new, so they need no adapter.
"""

import os
import struct
import unittest
import warnings

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

import sys
sys.path.insert(0, support.TOOLS)
from h713 import blockdev, stock                             # noqa: E402
from h713.imagewty import Imagewty                           # noqa: E402
from h713.log import Log                                     # noqa: E402
from h713.profiles import PROFILES                           # noqa: E402
from h713.source import FileSource                           # noqa: E402

SECT = fakedisk.SECT
# stage 0 review A1 (doku/121 §4): boot-resource.fex stands twice in the file table of update.img,
# one entry per slot, and the two copies are byte-identical.
HY310_COPIES = (0x67be000, 0x7c7b800)


class Recorder(object):
    """A disk that writes nothing and keeps the write plan (lba, sectors)."""

    def __init__(self, disk):
        self._disk, self.path, self.sectors = disk, disk.path, disk.sectors
        self.writes = []

    def read(self, lba, sectors):
        return self._disk.read(lba, sectors)

    def write(self, lba, data):
        self.writes.append((lba, len(data) // SECT))

    def sync(self):
        pass


def _adt3_disk(case, board, bootloader_a=None):
    """A T08/HY350 fake disk, optionally with a foreign bootloader_a on it."""
    support.need(fakedisk.needs_adt3(board) + (fakedisk.IMAGES[board],))
    path = fakedisk.make_adt3_disk(os.path.join(support.workdir(case), "emmc.img"), board)
    if bootloader_a:
        support.need([bootloader_a])
        with open(path, "r+b") as fh:
            head = fh.read(34 * SECT)
            lba, sectors = dict((n, (l, s)) for n, l, s in
                                fakedisk.gpt_parts(head))["bootloader_a"]
            with open(bootloader_a, "rb") as src:
                fh.seek(lba * SECT)
                fh.write(src.read(sectors * SECT))
    return path


def _restore(case, path, image, dry_run=True, record=False):
    """One restore run against a fake disk; returns (written, partitions, log, disk)."""
    log = support.Recorder()
    disk = blockdev.Disk(path, writable=False)
    target = Recorder(disk) if record else disk
    try:
        with support.quiet():
            written, partitions = stock.restore_stock(target, image, None, log, dry_run,
                                                      data_dir=support.TOOLS)
    finally:
        disk.close()
    return written, partitions, log, target


class MipsGuard(unittest.TestCase):
    def test_an_image_without_mips_does_not_overwrite_a_partition_that_has_it(self):
        path = _adt3_disk(self, "hy300-t08", fakedisk.STOCK_BOOTLOADER)
        written, _parts, log, _d = _restore(self, path, fakedisk.IMAGES["hy300-t08"])
        self.assertIn("WARN bootloader_a not written", log.text)
        self.assertIn("has no mips/ directory", log.text)
        self.assertNotIn("-> bootloader_a", log.text)
        # the 16317440 B of boot-resource.fex are not written any more (T08 plan: 3512839168)
        self.assertEqual(written, 3579948032 - 16317440)   # T08 plan with UDISK head zeroed (Fable, C-C review)

    def test_the_hy310_image_writes_both_bootloader_partitions(self):
        support.need(fakedisk.NEEDS_STOCK + (fakedisk.IMAGES["hy310"],))
        path = fakedisk.make_stock_disk(os.path.join(support.workdir(self), "emmc.img"))
        _written, _parts, log, _d = _restore(self, path, fakedisk.IMAGES["hy310"])
        for name in ("bootloader_a", "bootloader_b"):
            self.assertIn("-> %-16s" % name, log.text)
        self.assertNotIn("not written", log.text)

class PreservedPartitions(unittest.TestCase):
    """The write journal of a full (recorded, not performed) T08 restore."""

    def test_nothing_is_written_into_a_partition_the_preserve_list_keeps(self):
        path = _adt3_disk(self, "hy300-t08")        # boot-resource.fex on both sides
        before = fakedisk.journal(path)
        _written, parts, log, disk = _restore(self, path, fakedisk.IMAGES["hy300-t08"],
                                              dry_run=False, record=True)
        where = dict((n, (lba, sect)) for n, lba, sect, _src in parts)
        for name in ("private", "media_data", "bootloader_b"):   # UDISK is not kept by default (Fable, C-C review)
            lba, sect = where[name]
            end = lba + (sect or disk.sectors - 33 - lba)
            hits = [w for w in disk.writes if w[0] < end and lba < w[0] + w[1]]
            self.assertEqual(hits, [], "%s: %d writes into a kept partition" % (name, len(hits)))
            self.assertIn("  %-16s left untouched" % name, log.text)
        # Reserve0 is not in this list on purpose: this image brings a Reserve0.fex, and a
        # partition the image supplies is restored (api-stufe2.md, "Stock restore").
        for name in ("bootloader_a", "Reserve0"):   # no guard here: neither side has mips/
            self.assertTrue([w for w in disk.writes if w[0] == where[name][0]], name)
        self.assertNotIn("not written", log.text)
        self.assertEqual(fakedisk.journal(path), before, "the recorder wrote to the disk")


class WithTheBoardProfile(unittest.TestCase):
    def test_the_profile_decides_what_is_kept(self):
        support.need(fakedisk.NEEDS_STOCK + (fakedisk.IMAGES["hy310"],))
        path = fakedisk.make_stock_disk(os.path.join(support.workdir(self), "emmc.img"))
        log, disk = support.Recorder(), blockdev.Disk(path, writable=False)
        try:
            with support.quiet():
                written, _parts = stock.restore_stock(disk, fakedisk.IMAGES["hy310"], None, log,
                                                      True, data_dir=support.TOOLS,
                                                      profile=PROFILES["hy310"])
        finally:
            disk.close()
        self.assertIn("profile 'hy310' keeps 'private'", log.text)
        # The HY310 profile does not list UDISK, so with the profile the plan is the one
        # v0.5-beta wrote: 2540453376 B, UDISK's first 64 MiB zeroed.
        self.assertIn("-> UDISK", log.text)
        self.assertEqual(written, 2540453376)


class DuplicateEntries(unittest.TestCase):
    def test_both_copies_of_boot_resource_are_listed_and_identical(self):
        support.need([fakedisk.IMAGES["hy310"]])
        q = FileSource(fakedisk.IMAGES["hy310"])
        try:
            with support.quiet():
                img = Imagewty(q, Log(quiet=True))
            copies = img.copies["boot-resource.fex"]
            self.assertEqual(tuple(c["offset"] for c in copies), HY310_COPIES)
            self.assertEqual(img.entries["boot-resource.fex"]["offset"], HY310_COPIES[0])
            digests = set(stock._sha256(s) for s in img.file_copies("boot-resource.fex"))
            self.assertEqual(len(digests), 1)
            self.assertEqual(stock._check_copies(img, ["boot-resource.fex"]),
                             {"boot-resource.fex": " (2 identical copies in the image: "
                                                   "0x67be000, 0x7c7b800)"})
        finally:
            q.fh.close()

    def test_a_container_whose_two_copies_differ_is_refused(self):
        path = os.path.join(support.workdir(self), "synthetic.img")
        _write_container(path, [("sys_partition.fex", SYS_PARTITION),
                                ("twice.fex", b"A" * 4096), ("twice.fex", b"B" * 4096)])
        with warnings.catch_warnings():     # restore_stock leaks its FileSource (A1, stage 2)
            warnings.simplefilter("ignore", ResourceWarning)
            with self.assertRaises(RuntimeError) as caught:
                _restore(self, path, path)  # the disk is never reached
        self.assertIn("twice.fex", str(caught.exception))
        self.assertIn("differ", str(caught.exception))


class DryRunReads(unittest.TestCase):
    def test_a_dry_run_does_not_read_the_payload(self):
        support.need(fakedisk.NEEDS_STOCK + (fakedisk.IMAGES["hy310"],))
        path = fakedisk.make_stock_disk(os.path.join(support.workdir(self), "emmc.img"))

        class Counting(FileSource):
            total = 0

            def read(self, off, n):
                data = FileSource.read(self, off, n)
                Counting.total += len(data)
                return data

        stock.FileSource = Counting
        try:
            written, _parts, _log, _d = _restore(self, path, fakedisk.IMAGES["hy310"])
        finally:
            stock.FileSource = FileSource
        # super.fex alone is 1538 MiB in the file and 2048 MiB unpacked (A4A6 finding c).
        self.assertLess(Counting.total, 64 << 20, "%d bytes read" % Counting.total)
        self.assertGreater(written, 2 << 30)


SYS_PARTITION = (b"[partition]\r\nname = test_a\r\nsize = 1024\r\n"
                 b"downloadfile = \"twice.fex\"\r\n[partition_end]\r\n")


def _write_container(path, files):
    """A minimal IMAGEWTY v3 container -- a name may appear twice, that is the point."""
    head = bytearray(0x400)
    head[0:8] = b"IMAGEWTY"
    struct.pack_into("<II", head, 8, 0x0300, 0x60)              # header_version, header_size
    struct.pack_into("<8I", head, 0x20, 0x400, 0, 0, 0, 0, 1, 1024, len(files))
    table = bytearray()
    off = 0x400 + len(files) * 0x400
    for name, data in files:
        e = bytearray(0x400)
        struct.pack_into("<II", e, 0, 0x100, 0x400)             # filename_len, total_header_size
        e[8:16], e[16:32] = b"RFSFAT16".ljust(8), b"TEST".ljust(16, b"\0")
        e[36:36 + len(name)] = name.encode("latin1")
        struct.pack_into("<5I", e, 0x124, len(data), 0, len(data), 0, off)
        off += len(data)
        table += e
    with open(path, "wb") as fh:
        fh.write(head + table)
        for _name, data in files:
            fh.write(data)
        struct.pack_into("<Q", head, 0x18, fh.tell())           # image_size
        fh.seek(0)
        fh.write(head)
