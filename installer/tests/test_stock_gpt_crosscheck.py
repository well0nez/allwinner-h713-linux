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
                        moved_unique_regions)

# rows as stock_gpt_differences() returns them: (name, our lba, our sectors, their lba, theirs)
HY310_ROWS = [("media_data", 4932608, 557056, 4932608, 524288),
              ("Reserve0_a", 5489664, 32768, 5456896, 32768),
              ("Reserve0_b", 5522432, 32768, 5489664, 32768),
              ("UDISK", 5555200, 9714655, 5522432, 9747423)]
# what the HY310's own table says about the regions that exist only on it (dump.regions_from_gpt)
HY310_DEVICE = {"secure-storage": (12288, 2048), "private": (4891648, 32768),
                "Reserve0_a": (5489664, 32768), "Reserve0_b": (5522432, 32768)}


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

    def test_an_image_whose_tables_agree_says_one_line(self):
        stop, log = self._check("hy350", self._stock_disk())
        self.assertIsNone(stop, log.text)
        self.assertIn("agrees with sys_partition.fex", log.text)
        self.assertNotIn("disagree", log.text)

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
