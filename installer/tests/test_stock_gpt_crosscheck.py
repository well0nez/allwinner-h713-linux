# SPDX-License-Identifier: GPL-2.0
"""R1 item 2: the two partition tables of one IMAGEWTY container, compared out loud.

`restore-stock` builds the GPT it writes out of sys_partition.fex. The container also carries a
finished sunxi_gpt.fex, and in the HY310 image the two contradict each other from media_data on
(doku/60 point 12): 256 MiB against 272 MiB, and everything behind it 16 MiB apart. Until now
the installer preferred one of them without saying so.

The refusal is the part that needs proving without a vendor image, so the two functions it is
made of -- `moved_unique_regions()` and `covers_the_lock()` -- are asked directly with tables
written out by hand. Everything else runs against the real container and skips without it.
"""

import os
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.blockdev import Disk, LOCK_FIRST, LOCK_LAST                    # noqa: E402
from h713.identify import identify                                       # noqa: E402
from h713.stock import (check_stock_gpt, covers_the_lock,                # noqa: E402
                        moved_unique_regions, relabelled_regions)

# rows as stock_gpt_differences() returns them: (name, our lba, our sectors, their lba, theirs)
HY310_ROWS = [("media_data", 4932608, 557056, 4932608, 524288),
              ("Reserve0_a", 5489664, 32768, 5456896, 32768),
              ("Reserve0_b", 5522432, 32768, 5489664, 32768),
              ("UDISK", 5555200, 9714655, 5522432, 9747423)]
# what the HY310's own table says about the regions that exist only on it (dump.regions_from_gpt)
HY310_DEVICE = {"secure-storage": (12288, 2048), "private": (4891648, 32768),
                "Reserve0_a": (5489664, 32768), "Reserve0_b": (5522432, 32768)}
# the table restore-stock writes for the HY310, in the shape stock_plan() returns (the rows that matter)
HY310_WRITTEN = [("bootloader_a", 73728, 65536, "boot-resource.fex"), ("private", 4891648, 32768, None),
                 ("media_data", 4932608, 557056, "mediadata.fex"),
                 ("Reserve0_a", 5489664, 32768, "Reserve0.fex"), ("Reserve0_b", 5522432, 32768, None),
                 ("UDISK", 5555200, 0, None)]


class WhatCountsAsDangerous(unittest.TestCase):
    def test_a_device_that_agrees_with_the_written_table_settles_it(self):
        # The HY310 case: sunxi_gpt.fex puts Reserve0_a/_b 16 MiB lower, the device itself does
        # not -- so the difference is information and the restore goes on.
        self.assertEqual(moved_unique_regions(HY310_ROWS, HY310_DEVICE), [])

    def test_a_device_that_carries_the_region_elsewhere_stops_the_restore(self):
        here = dict(HY310_DEVICE, Reserve0_a=(5456896, 32768))
        self.assertEqual(moved_unique_regions(HY310_ROWS, here),
                         [("Reserve0_a", 5456896, 5489664)])

    def test_a_region_the_device_does_not_carry_at_all_is_no_reason_to_stop(self):
        # Our own layout has neither `private` nor `Reserve0*`: the new table creates them,
        # and there are no bytes underneath that could be relabelled.
        self.assertEqual(moved_unique_regions(HY310_ROWS, {"secure-storage": (12288, 2048)}), [])

    def test_only_the_device_unique_names_count(self):
        rows = [("media_data", 4932608, 557056, 4000000, 557056)]
        self.assertEqual(moved_unique_regions(rows, {"media_data": (4000000, 557056)}), [])

    def test_a_partition_reaching_into_the_secure_storage_is_named(self):
        ours = (("boot0", 0, 16384, None), ("bootloader_a", 73728, 65536, None))
        self.assertEqual(covers_the_lock(ours, fakedisk.DISK_SECTORS), ["boot0"])
        self.assertEqual(covers_the_lock(ours[1:], fakedisk.DISK_SECTORS), [])
        # the lock region itself, exactly
        one = (("odd", LOCK_FIRST, LOCK_LAST - LOCK_FIRST + 1, None),)
        self.assertEqual(covers_the_lock(one, fakedisk.DISK_SECTORS), ["odd"])

    def test_a_size_of_zero_runs_to_the_end_of_the_disk(self):
        # UDISK is declared with size 0; without that rule every image would look wrong here.
        self.assertEqual(covers_the_lock((("UDISK", 8, 0, None),), fakedisk.DISK_SECTORS),
                         ["UDISK"])


class WhatTheRowsNeverMention(unittest.TestCase):
    """FB-INSTALL item 1 (doku/61 row 37): the written table against the device itself, whatever
    the container's two tables say to each other -- moved_unique_regions() only ever saw the rows,
    so a container whose tables agree never asked whether the device carries `private` elsewhere."""

    def test_a_device_that_agrees_with_the_written_table_settles_it(self):
        self.assertEqual(relabelled_regions(HY310_WRITTEN, HY310_DEVICE), [])

    def test_a_region_the_device_carries_elsewhere_is_named_without_any_row(self):
        here = dict(HY310_DEVICE, private=(6291456, 32768))
        self.assertEqual(relabelled_regions(HY310_WRITTEN, here), [("private", 6291456, 4891648)])

    def test_a_region_the_written_table_does_not_name_is_named_too(self):
        # an ADT-3 device (single Reserve0) under the HY310's table (Reserve0_a/_b): no partition
        # of that name would be left over the bytes
        here = {"secure-storage": (12288, 2048), "private": (4891648, 32768),
                "Reserve0": (9437184, 32768)}
        self.assertEqual(relabelled_regions(HY310_WRITTEN, here), [("Reserve0", 9437184, None)])

    def test_the_spelling_of_the_device_is_kept_and_compared_loosely(self):
        self.assertEqual(relabelled_regions(HY310_WRITTEN, {"PRIVATE": (4891648, 32768)}), [])
        self.assertEqual(relabelled_regions(HY310_WRITTEN, {"PRIVATE": (4891649, 32768)}),
                         [("PRIVATE", 4891649, 4891648)])

    def test_a_device_without_any_of_them_settles_nothing(self):
        self.assertEqual(relabelled_regions(HY310_WRITTEN, {"secure-storage": (12288, 2048)}), [])
        self.assertEqual(relabelled_regions(HY310_WRITTEN, None), [])

    def test_only_the_device_unique_names_count(self):
        self.assertEqual(relabelled_regions(HY310_WRITTEN, {"UDISK": (1, 1), "media_data": (2, 2)}), [])


class AgainstTheRealContainer(unittest.TestCase):
    """The HY310 image is the one we have where the two tables really differ; the two ADT-3
    images agree with themselves, and that has to stay a quiet line."""

    def _check(self, board, disk):
        support.need([fakedisk.IMAGES[board]])
        log = support.Recorder()
        log.error = lambda t: log.lines.append("ERROR " + t)
        with support.quiet():
            stop = check_stock_gpt(fakedisk.IMAGES[board], disk, log)
        return stop, log

    def _stock_disk(self):
        support.need(fakedisk.NEEDS_STOCK_GPT)
        path = fakedisk.make_stock_gpt_disk(os.path.join(support.workdir(self), "emmc.img"))
        disk = Disk(path, writable=False)
        self.addCleanup(disk.close)
        return disk

    def test_the_hy310_image_lists_its_four_differences_and_goes_on(self):
        stop, log = self._check("hy310", self._stock_disk())
        self.assertIsNone(stop, log.text)
        self.assertIn("disagree on 4 of 26 partitions", log.text)
        for name, lba, sectors, their_lba, their_sectors in HY310_ROWS:
            self.assertIn("%-16s %-29s %s"
                          % (name, "LBA %d +%d" % (lba, sectors),
                             "LBA %d +%d" % (their_lba, their_sectors)), log.text)

    def _own_disk(self, board):
        """A device partitioned the way this image's own sys_partition.fex says -- the device the
        image belongs to. FB-INSTALL: the HY310's table stood in here before, and under it the
        HY350 image relabels `private` (4891648 there, 6988800 here), which is now a refusal."""
        import pathlib
        from h713.fex import stock_plan
        from h713.imagewty import Imagewty
        from h713.log import Log
        from h713.source import FileSource
        q = FileSource(pathlib.Path(fakedisk.IMAGES[board]))
        try:
            partitions, _raw = stock_plan(Imagewty(q, Log(quiet=True)))
        finally:
            q.fh.close()
        path = fakedisk.make_moved_stock_disk(os.path.join(support.workdir(self), "own.img"),
                                              [(n, l, s) for n, l, s, _f in partitions])
        disk = Disk(path, writable=False)
        self.addCleanup(disk.close)
        return disk

    def test_an_image_whose_tables_agree_says_one_line(self):
        stop, log = self._check("hy350", self._own_disk("hy350"))
        self.assertIsNone(stop, log.text)
        self.assertIn("agrees with sys_partition.fex", log.text)
        self.assertNotIn("disagree", log.text)

    def _moved_disk(self):
        """A stock device whose table carries `private` and a single `Reserve0` far from where
        any of our three images put them (fakedisk.MOVED_PARTS, no vendor bytes needed)."""
        path = fakedisk.make_moved_stock_disk(os.path.join(support.workdir(self), "moved.img"))
        disk = Disk(path, writable=False)
        self.addCleanup(disk.close)
        return disk

    def test_a_container_whose_tables_agree_still_asks_the_device(self):
        # HY350: not one row -- and the device carries private at LBA 6291456, which the written
        # table puts elsewhere. Before FB-INSTALL this restore went on and relabelled it.
        stop, log = self._check("hy350", self._moved_disk())
        self.assertIn("agrees with sys_partition.fex", log.text)
        self.assertIsNotNone(stop, log.text)
        self.assertIn("private from LBA 6291456 to ", stop)
        self.assertIn("Reserve0 from LBA 9437184 to ", stop)
        self.assertIn("not moved by a table out of a container", stop)

    def test_the_hy310_image_names_the_region_it_would_leave_without_a_partition(self):
        stop, log = self._check("hy310", self._moved_disk())
        self.assertIsNotNone(stop, log.text)
        self.assertIn("private from LBA 6291456 to 4891648", stop)
        self.assertIn("Reserve0 from LBA 9437184 to no partition of that name", stop)

    def test_our_own_layout_is_no_reason_to_refuse_the_hy310_image(self):
        # It carries neither `private` nor `Reserve0*`, so the four differences stay notes --
        # the way back to the vendor firmware must not close behind the first install.
        support.need(fakedisk.NEEDS_V3)
        path = fakedisk.make_v3_disk(os.path.join(support.workdir(self), "emmc-v3.img"))
        disk = Disk(path, writable=False)
        self.addCleanup(disk.close)
        stop, log = self._check("hy310", disk)
        self.assertIsNone(stop, log.text)
        self.assertIn("disagree on 4 of 26 partitions", log.text)


class IdentifySaysItInOneLine(unittest.TestCase):
    """Item 2a: one line on a firmware image, not one per partition."""

    def _text(self, board):
        support.need([fakedisk.IMAGES[board]])
        with support.quiet():
            return "\n".join(identify(fakedisk.IMAGES[board])["text"])

    def test_the_hy310_image_says_which_partition_it_starts_at(self):
        self.assertIn("sunxi_gpt.fex and sys_partition.fex disagree on 1 partition "
                      "(from media_data on)", self._text("hy310"))

    def test_an_image_that_agrees_with_itself_says_nothing(self):
        self.assertNotIn("disagree", self._text("hy350"))


if __name__ == "__main__":
    unittest.main()
