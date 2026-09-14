"""stock_zurueck(..., trocken=True): the whole restore plan of the three vendor
images, frozen -- and the proof that a dry run touches no byte of the disk."""

import os
import struct
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from hy310-install.py 0.1 with h713-extract 0.4 as the
# IMAGEWTY reader: board -> (bytes it would write, partitions, entries the GPT
# header claims, digest of the plan, digest of the screen output, regions it
# must leave alone).  25 partitions and still 26 entries in the header on the
# two ADT-3 images -- known bug, stage 2 C4.
PLANS = {
    "hy310": (2540453376, 26, 26,
              "3724361e2b0fe97e424ca06d3e2f720e3dc40d8fb964800ab3f2f09cc57fee6d",
              "9b17ac15fd4b6ec8d3d5579c391095e4fd2507a5bbe550e114ae4b2727b496a3",
              ("private", "Reserve0_b")),
    "hy300-t08": (3630279680, 25, 26,
                  "60d972f2be80db5c09df5ad030414232203ddc48e5001b605cbd54329cc74a0a",
                  "2185216886c954f1e64034d8a73dc959a68bf5b2b9a8bec9feaae753c3609f85",
                  ("private",)),
    "hy350": (3083081728, 25, 26,
              "8aa4daa85514b87c6baf745a3d71c7662a81ca82ea2e8a9557fde2f199bcbae3",
              "9627ad2496f8f7675e40906913f83f25208b3eba2b94b806eec36263a7278c85",
              ("private",)),
}


class RestorePlan(unittest.TestCase):
    def _check(self, board):
        inst = support.tool("install")
        support.need([fakedisk.IMAGES[board]])
        path = os.path.join(support.workdir(self), "emmc.img")
        if board == "hy310":
            support.need(fakedisk.NEEDS_STOCK)
            disk = fakedisk.make_stock_disk(path)
        else:
            support.need(fakedisk.needs_adt3(board))
            disk = fakedisk.make_adt3_disk(path, board)
        want_bytes, want_parts, want_entries, plan, screen, kept = PLANS[board]
        before, log = fakedisk.journal(disk), support.Recorder()
        platte = inst.Platte(disk, schreiben=False)
        try:
            with support.quiet():
                written, partitions = inst.stock_zurueck(
                    platte, fakedisk.IMAGES[board], None, log=log, trocken=True)
        finally:
            platte.close()
        self.assertEqual((written, len(partitions)), (want_bytes, want_parts), board)
        self.assertEqual(support.digest(partitions), plan, board)
        self.assertEqual(support.digest(log.lines), screen, board)
        gpt = inst.stock_gpt_bauen(partitions, fakedisk.DISK_SECTORS)
        self.assertEqual(struct.unpack_from("<I", gpt[1], 80)[0],
                         want_entries, board)            # known bug, stage 2 C4
        for name in kept:
            self.assertIn("  %-16s bleibt unangetastet" % name, log.text, board)
        self.assertEqual(fakedisk.journal(disk), before,
                         "%s: the dry run changed the disk" % board)

    def test_all_three_images(self):
        for board in sorted(PLANS):
            self._check(board)

    def test_no_target_of_the_plan_reaches_the_locked_block(self):
        inst, ex = support.tool("install"), support.tool("extract")
        support.need([fakedisk.IMAGES["hy310"]])
        with support.image_source(fakedisk.IMAGES["hy310"]) as source:
            with support.quiet():
                _img, partitions, raw = inst.stock_plan(ex, source)
        for _name, lba in raw:
            self.assertTrue(lba > inst.SPERRE_LETZTER or lba < 12288 - 2432, lba)
        self.assertEqual(min(lba for _n, lba, _s, _q in partitions), 73728)
