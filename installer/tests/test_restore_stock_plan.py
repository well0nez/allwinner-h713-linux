"""stock_zurueck(..., trocken=True): the whole restore plan of the three vendor
images, frozen -- and the proof that a dry run touches no byte of the disk."""

import os
import struct
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from hy310-install.py 0.1 with h713-extract 0.4 as the
# IMAGEWTY reader: board -> (bytes it would write, partitions, entries the GPT
# header claims, digest of the plan, digest of the screen output, partitions it
# must leave alone).  Stage 2 C-C re-froze three of the six columns per board;
# the partition list (fourth column) is untouched by the change.
#
#   bytes    : the head of every partition the image brings no file for used to be
#              zeroed. Now the preserve list keeps some of them, and their bytes are
#              gone from the total (see the comment per board).
#   entries  : the header counts the partitions of the image (was 26 for all three).
#   screen   : the "left untouched" lines are new English text, and the two boards
#              whose image carries boot-resource.fex twice say so in its line.
#
# Stage 3 (D1) re-froze the screen column once more, reason "stage 3 texts": every line of
# h713/stock.py is English now ("-> GPT (protective MBR, ...)", "zeroed", "(no image)",
# "unpacked (sparse, file ... MiB)", "empty ext4"). Bytes, partition list and GPT header
# entries are untouched -- the same numbers as before, in other words.
PLANS = {
    # C-C froze 2473344512 with UDISK kept; UDISK is zeroed again, so it is the v0.5-beta value (Fable).
    "hy310": (2540453376, 26, 26,   # UDISK head zeroed again (Fable, C-C review): the v0.5-beta value
              "3724361e2b0fe97e424ca06d3e2f720e3dc40d8fb964800ab3f2f09cc57fee6d",
              # was 9b17ac15fd4b6ec8d3d5579c391095e4fd2507a5bbe550e114ae4b2727b496a3
              # screen: was e3e06cd9… with UDISK kept (C-C), then 9c237246… (Fable, UDISK zeroed again);
              # re-frozen for stage 3 texts (D1) -- same plan, same bytes, English lines:
              "3329f93ba13b6d1d8fbf631574cbccb35630b29e58ab9574c67df05d7e890705",
              ("private", "Reserve0_b")),   # UDISK zeroed again, not kept (Fable, C-C review)
    # was 3630279680: bootloader_b (32 MiB), media_data (16 MiB) and UDISK (64 MiB)
    # are no longer zeroed. Header was 26.
    "hy300-t08": (3579948032, 25, 25,   # + 64 MiB UDISK head (Fable, C-C review)
                  "60d972f2be80db5c09df5ad030414232203ddc48e5001b605cbd54329cc74a0a",
                  # was 2185216886c954f1e64034d8a73dc959a68bf5b2b9a8bec9feaae753c3609f85
                  # screen: was 3f9c2ed9… (C-C), then 0f9828bd… (Fable); stage 3 texts (D1):
                  "2196b6328a884e6668a97f7e39a118b5ffa242248de0bee9e85a841d1013e03a",
                  ("private", "media_data", "bootloader_b")),   # UDISK zeroed again, not kept (Fable, C-C review)
    # was 3083081728: media_data (16 MiB) and UDISK (64 MiB). Header was 26.
    "hy350": (3066304512, 25, 25,   # + 64 MiB UDISK head (Fable, C-C review)
              "8aa4daa85514b87c6baf745a3d71c7662a81ca82ea2e8a9557fde2f199bcbae3",
              # was 9627ad2496f8f7675e40906913f83f25208b3eba2b94b806eec36263a7278c85
              # screen: was e03021d9… (C-C), then c9c27ed2… (Fable); stage 3 texts (D1):
              "27a8b3d20544354f22aab0ccd8ef92ac590dcaf4cfef75551ee9f5f2eb8025ba",
              ("private", "media_data")),   # UDISK zeroed again, not kept (Fable, C-C review)
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
                         want_entries, board)            # = len(partitions), stage 2 C-C
        for name in kept:
            self.assertIn("  %-16s left untouched" % name, log.text, board)
            self.assertNotIn("-> %-16s" % name, log.text, board)
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
