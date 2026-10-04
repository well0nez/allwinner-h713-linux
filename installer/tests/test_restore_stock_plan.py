"""stock_zurueck(..., trocken=True): the whole restore plan of the three vendor
images, frozen -- and the proof that a dry run touches no byte of the disk."""

import argparse
import contextlib
import hashlib
import os
import struct
import sys
import unittest
from unittest import mock

import support                 # imported first: it puts the work dir on sys.path
import fakedisk
from test_hy200_qz713df_a1 import GEU, GEU_ID, HY310, PLUS_ID, _disk_with, _tool, read_gpt
from test_hy200_qz713df_a1 import _run as run_tool
from test_stock_guard import _write_container

sys.path.insert(0, support.TOOLS)
from h713.blockdev import SECTORS_KNOWN                                      # noqa: E402
from h713.gpt import build_stock_gpt                                         # noqa: E402
from h713.profiles import PROFILES, units                                    # noqa: E402
from h713.stock import beyond_the_disk                                       # noqa: E402

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


# --------------------------------------------------- ST3-RESTORE: every known eMMC size
# restore-stock builds its table for the device it finds (UDISK runs to the last usable sector), so
# the HY310 image restored onto the 15273600-sector eMMC of the HY300PRO-G-EU is the HY310 row above
# - bytes, partition list, screen lines - except for what follows the disk: the GPT (last usable
# LBA, both backups) and UDISK's reach, 3712 sectors further. Those are frozen here (2026-10-04) from
# build_stock_gpt over the 26 rows of sys_partition.fex; the HY310 digest is the table the dump's
# own primary header matches (test_gpt).
GPT_DIGESTS = {HY310: "15be22121f3b26aa0621a316a9971dcc6350151a927dd73f1efd81765a253690",
               GEU: "c6feca9ad94702ec159be8c7cff8cd4d06d3cd60c8a61122959f1ccbf5c0f87c"}
def _container_table(udisk_sectors=0):
    """The HY310's table as a container's sys_partition.fex, without any file to write - the device
    carries these partitions, so nothing about it is a surprise but the one row this changes."""
    rows = [(name, udisk_sectors if name == "UDISK" else sectors)
            for name, _lba, sectors, _file in PROFILES["hy310"]["layout"]["partitions"]]
    return "".join("[partition]\r\nname = %s\r\nsize = %d\r\n" % row for row in rows).encode() + \
        b"[partition_end]\r\n"


# UDISK with a fixed size that ends at sector 15270000: it fits 15273600 sectors (the backup GPT lies
# from 15273567 on) and does not fit 15269888 (from 15269855 on)
LONG = _container_table(15270000 - 5555200)


def _gpt_digest(blocks):
    return support.digest(sorted((lba, hashlib.sha256(data).hexdigest()) for lba, data in blocks.items()))


class RestorePlanOnEveryKnownSize(unittest.TestCase):
    def test_the_hy310_image_on_both_sizes_is_the_same_plan(self):
        support.need(fakedisk.NEEDS_STOCK + (fakedisk.IMAGES["hy310"],))
        inst = support.tool("install")
        want_bytes, want_parts, _entries, plan, screen, kept = PLANS["hy310"]
        for n in sorted(GPT_DIGESTS):
            path = fakedisk.make_stock_disk(os.path.join(support.workdir(self), "emmc.img"), n)
            before, log = fakedisk.journal(path), support.Recorder()
            disk = inst.Platte(path, schreiben=False)
            try:
                with support.quiet():
                    written, parts = inst.stock_zurueck(disk, fakedisk.IMAGES["hy310"], None,
                                                        log=log, trocken=True)
            finally:
                disk.close()
            self.assertEqual((written, len(parts)), (want_bytes, want_parts), n)
            self.assertEqual((support.digest(parts), support.digest(log.lines)), (plan, screen), n)
            for name in kept:
                self.assertNotIn("-> %-16s" % name, log.text, n)
            self.assertEqual(_gpt_digest(inst.stock_gpt_bauen(parts, n)), GPT_DIGESTS[n], n)
            self.assertEqual(fakedisk.journal(path), before, "%d: the dry run changed the disk" % n)

    def test_the_gpt_of_each_size_is_a_valid_table_that_ends_at_the_disk(self):
        rows = [tuple(r) for r in PROFILES["hy310"]["layout"]["partitions"]]   # the image's 26 rows
        for n in sorted(GPT_DIGESTS):
            blocks = build_stock_gpt(rows, n)
            self.assertEqual(_gpt_digest(blocks), GPT_DIGESTS[n], n)
            problems, facts = read_gpt(_disk_with(os.path.join(support.workdir(self), "g.img"), n, blocks), n)
            self.assertEqual(problems, [], n)
            self.assertEqual(facts["entries"][-1], ("UDISK", 5555200, n - 34), n)   # runs to the end
        self.assertNotEqual(GPT_DIGESTS[GEU], GPT_DIGESTS[HY310])


class WhatRestoreStockDoes(unittest.TestCase):
    """`restore-stock CONTAINER --no-write` against a device that carries the stock table and no
    vendor bytes. The board is named by hand where a test needs one: the disk cannot say."""

    def _run(self, n, sys_text=None, board=None, *extra, **kw):
        tmp = support.workdir(self)
        disk = fakedisk.make_stock_gpt_disk(os.path.join(tmp, "emmc.img"), n)
        image = os.path.join(tmp, "update.img")
        _write_container(image, [("sys_partition.fex", sys_text or _container_table())] +
                         kw.get("files", []))
        before, m = fakedisk.journal(disk), _tool()
        real = m.identify

        def identified_as(device):
            found = real(device)
            found["profile"] = board
            return found
        with (mock.patch.object(m, "identify", identified_as) if board else contextlib.nullcontext()):
            code, out = run_tool(m, ["restore-stock", image, "--device", disk, "--no-write"] + list(extra))
        self.assertEqual(fakedisk.journal(disk), before, out)
        return code, out

    def test_a_size_nobody_knows_is_refused_with_the_known_sizes_and_the_full_dump(self):
        code, out = self._run(15000000)
        self.assertEqual(code, 4, out)
        self.assertIn("has 15000000 sectors, expected %d or %d" % SECTORS_KNOWN, out)
        self.assertIn("full dump: h713-install restore", out)
        self.assertNotIn("HY310's eMMC size only", out)

    def test_both_known_sizes_go_on(self):
        for n in SECTORS_KNOWN:
            code, out = self._run(n)
            self.assertEqual(code, 0, out)
            self.assertIn("No-write run -- nothing written.", out)

    def test_a_partition_that_does_not_fit_is_refused_and_follows_the_device(self):
        code, out = self._run(HY310, LONG)
        self.assertEqual(code, 2, out)
        self.assertIn("nothing is written: UDISK of this image would end behind the last usable "
                      "sector of this device (15269888 sectors, the backup partition table lies "
                      "from LBA 15269855 on)", out)
        self.assertNotIn("No-write run", out)
        code, out = self._run(HY310, LONG, None, "--skip-identify")    # --skip-identify keeps it
        self.assertEqual(code, 2, out)
        code, out = self._run(GEU, LONG)                               # the control: it fits here
        self.assertEqual(code, 0, out)
        self.assertNotIn("would end behind", out)

    def test_udisk_following_the_device_is_no_disagreement_between_the_containers_tables(self):
        """The container's sunxi_gpt.fex is cut for its own eMMC. On the other size UDISK ends elsewhere
        - that is the device, not a disagreement; a table that differs in earnest still says so."""
        rows = [(name, lba, sectors) for name, lba, sectors, _f in PROFILES["hy310"]["layout"]["partitions"]]
        shifted, lba = [], 73728                       # the HY310 image's own case: media_data 16 MiB shorter
        for name, _lba, sectors in rows:
            sectors = 524288 if name == "media_data" else sectors
            shifted.append((name, lba, sectors))
            lba += sectors
        for n in SECTORS_KNOWN:
            for table, want in ((rows, "agrees with sys_partition.fex (26 partitions)"),
                                (shifted, "disagree on 4 of 26 partitions")):
                gpt = build_stock_gpt(table, HY310)    # cut for the HY310's size, whatever the device is
                code, out = self._run(n, None, None, files=[("sunxi_gpt.fex", gpt[0] + gpt[1] + gpt[2])])
                self.assertEqual(code, 0, out)
                self.assertIn(want, out, n)

    def test_a_size_read_off_a_unit_is_held_to_the_device(self):
        # the HY300PRO-G-EU's profile carries UDISK's real extent, so its 15273600 is a unit's
        code, out = self._run(HY310, None, GEU_ID)
        self.assertEqual(code, 4, out)
        self.assertIn("has 15269888 sectors, expected 15273600 -- wrong drive?", out)
        self.assertIn("whose eMMC has 15273600 sectors", out)
        self.assertNotIn("No-write run", out)
        code, out = self._run(GEU, None, GEU_ID)                      # control: the sizes agree
        self.assertEqual(code, 0, out)
        code, out = self._run(HY310, None, GEU_ID, "--skip-identify")  # no identification, no profile
        self.assertEqual(code, 0, out)

    def test_a_size_out_of_a_vendor_image_is_a_note_and_the_run_goes_on(self):
        # the HY310 profile's layout is update.img's (UDISK declared 0): it cannot say what chip
        code, out = self._run(GEU, None, "hy310")
        self.assertEqual(code, 0, out)
        self.assertIn("the profile of this board names 15269888 sectors out of a vendor image's "
                      "table", out)
        self.assertIn("this device has 15273600", out)
        code, out = self._run(HY310, None, "hy310")                   # control: nothing to note
        self.assertEqual(code, 0, out)
        self.assertNotIn("out of a vendor image", out)


class BeyondTheDisk(unittest.TestCase):
    def test_the_edge_is_the_last_usable_sector(self):
        n = HY310                                              # last usable LBA 15269854, backup GPT from 15269855
        fits = (("a", 73728, n - 33 - 73728, None),)           # ends on the last usable sector
        self.assertEqual(beyond_the_disk(fits, n), [])
        self.assertEqual(beyond_the_disk((("a", 73728, n - 33 - 73728 + 1, None),), n), ["a"])
        self.assertEqual(beyond_the_disk((("u", n - 34, 0, None),), n), [])        # size 0: runs to the end
        self.assertEqual(beyond_the_disk((("u", n - 33, 0, None),), n), ["u"])     # but has to start inside
        self.assertEqual(beyond_the_disk(fits, GEU), [])                           # the larger disk takes it


class SizesAllowed(unittest.TestCase):
    def test_which_sizes_each_command_takes(self):
        m = _tool()

        def allowed(command, profile=None, ident=True):
            return m._sizes_allowed(argparse.Namespace(command=command),
                                    {"profile": profile} if ident else None)
        for profile in (None, "hy310", "hy300_t08", GEU_ID, "hy300_pro"):
            self.assertEqual(allowed("dump", profile), SECTORS_KNOWN, profile)
        # restore-stock: every known size - unless the board's size was read off a unit
        self.assertEqual(allowed("restore-stock"), SECTORS_KNOWN)                   # no profile
        self.assertEqual(allowed("restore-stock", ident=False), SECTORS_KNOWN)      # --skip-identify
        for profile in ("hy310", "hy300_t08", "hy350", PLUS_ID):                    # sizes from images
            self.assertEqual(allowed("restore-stock", profile), SECTORS_KNOWN, profile)
        self.assertEqual(allowed("restore-stock", GEU_ID), (GEU,))
        self.assertEqual(allowed("restore-stock", "hy300_pro"), (HY310,))
        # a write that is not restore-stock stays at its profile's size
        self.assertEqual(allowed("install", "hy310"), (HY310,))
        self.assertEqual(allowed("restore", GEU_ID), (GEU,))

    def test_which_profiles_have_a_size_read_off_a_unit(self):
        """Frozen: the rule of _size_is_a_units() against the profiles of today. A profile edit
        that moves a board across the line is then a decision, not a side effect."""
        m = _tool()
        found = sorted(key for key, profile in units().items()
                       if m._size_is_a_units(profile["layout"] or {}))
        self.assertEqual(found, sorted([GEU_ID, "hy300_pro"]))
        self.assertFalse(m._size_is_a_units({"disk_sectors": HY310, "partitions": [("UDISK", 1, 0, None)]}))
        self.assertFalse(m._size_is_a_units({"disk_sectors": None, "partitions": [("UDISK", 1, 5, None)]}))
        self.assertFalse(m._size_is_a_units({}))
