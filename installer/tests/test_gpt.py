"""The three partition tables: stock (rebuilt from sys_partition.fex), layout v3
(hy310-mkimage), and what the extractor reads out of the stock GPT fixture."""

import hashlib
import struct
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

SECT = fakedisk.SECT
BLOCK_LBAS = [0, 1, 2, 15269880, 15269887]
RAW_TARGETS = [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
               ("boot_package.fex", 24576), ("boot_package.fex", 32800)]

# frozen 2026-09-14 from hy310-install.py 0.1: board -> (partitions in the plan,
# entries the GPT header claims, digest over {lba: sha256} of every block that
# stock_gpt_bauen() returns).  The header now counts the partitions the image
# declares (stage 2 C-C); the HY310 is unchanged, the two ADT-3 images say 25.
STOCK_TABLES = {
    "hy310": (26, 26, "489a8bb587d54005deb71b986af663293253fbf9e35586c2840410852b365c89"),
    # was (25, 26, "25592ab888978c74d4b18240aab7645215aadee82131f8f5e2ab063806e06ff5")
    # until stage 2 C-C: header entry count 26 -> 25, so header CRC and entry-array CRC
    # change; the 3584 bytes of the table itself and both backup LBAs stay as they were.
    "hy300-t08": (25, 25, "f792beb10954580aa5ea6a54878afd9de9c476de0f8acaa7ff570f62e77f1604"),
    # was (25, 26, "1e2f50117d3a4d2bf5dac357e596388ece25c133267c4c54e88e29ab22938438")
    # until stage 2 C-C, same reason.
    "hy350": (25, 25, "c22638d4733b908ca3b96dc0ac52cd6d71edfc05bcdcd3202deb6ec03c080c7f"),
}
# frozen 2026-09-14 from hy310-mkimage.py 0.1, gpt_bauen() with its defaults
V3_TABLE = "487390f31e556d2476f7ff3904aeb417179f9142858c503ff58ee5073af18ea8"
# frozen 2026-09-14 from h713-extract 0.4, Gpt() on the stock GPT fixture
STOCK_PARTS = (26, "1dd9d25b847d7502dca47139f35c41c531c2cc6cc04e00b106de17e69af12783")


def _blocks(gpt):
    return support.digest(dict((lba, hashlib.sha256(b).hexdigest())
                               for lba, b in gpt.items()))


def _stock_gpt(board):
    inst, ex = support.tool("install"), support.tool("extract")
    with support.image_source(fakedisk.IMAGES[board]) as source:
        with support.quiet():
            _img, partitions, raw = inst.stock_plan(ex, source)
    return partitions, raw, inst.stock_gpt_bauen(partitions, fakedisk.DISK_SECTORS)


class StockTable(unittest.TestCase):
    def test_every_block_of_every_image(self):
        for board, (n_parts, n_header, want) in sorted(STOCK_TABLES.items()):
            support.need([fakedisk.IMAGES[board]])
            partitions, raw, gpt = _stock_gpt(board)
            self.assertEqual((len(partitions), raw), (n_parts, RAW_TARGETS), board)
            self.assertEqual(sorted(gpt), BLOCK_LBAS, board)
            self.assertEqual(_blocks(gpt), want, board)
            self.assertEqual(struct.unpack_from("<I", gpt[1], 80)[0],
                             n_header, board)            # = len(partitions), stage 2 C-C
            if board == "hy310":       # byte for byte the table read off Marco's
                support.need([fakedisk.STOCK_GPT])
                with open(fakedisk.STOCK_GPT, "rb") as fh:
                    self.assertEqual(gpt[0] + gpt[1] + gpt[2], fh.read(9 * SECT))


class LayoutV3Table(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.need(fakedisk.NEEDS_V3)
        cls.mk = support.tool("mkimage")
        cls.gpt = cls.mk.gpt_bauen()
        with open(fakedisk.V3_GPT_PRIMARY, "rb") as fh:
            cls.primary = fh.read()
        with open(fakedisk.V3_GPT_BACKUP, "rb") as fh:
            cls.backup = fh.read()

    def test_blocks_are_frozen_and_equal_to_the_release_fixtures(self):
        self.assertEqual(sorted(self.gpt), BLOCK_LBAS)
        self.assertEqual(_blocks(self.gpt), V3_TABLE)
        self.assertEqual(self.gpt[0] + self.gpt[1] + self.gpt[2], self.primary[:9 * SECT])
        base = fakedisk.DISK_SECTORS - fakedisk.GPT_BACKUP_SECTORS
        for lba in (fakedisk.DISK_SECTORS - 1 - self.mk.ARR_SEKT, fakedisk.DISK_SECTORS - 1):
            off = (lba - base) * SECT
            self.assertEqual(self.gpt[lba], self.backup[off:off + len(self.gpt[lba])], lba)

    def test_gpt_pruefen_accepts_the_release_fixtures(self):
        self.assertEqual(self.mk.gpt_pruefen(self.primary, self.backup), [])


class ExtractorReadsTheStockTable(unittest.TestCase):
    def test_the_names_with_their_lbas(self):
        support.need([fakedisk.STOCK_GPT])
        ex = support.tool("extract")
        with support.image_source(fakedisk.STOCK_GPT) as source:
            self.assertTrue(ex.Gpt.ist_gpt(source))
            with support.quiet():
                gpt = ex.Gpt(source, ex.Log(quiet=True))
        self.assertTrue(gpt.header_ok and gpt.tabelle_ok)
        self.assertEqual((gpt.first, gpt.last, gpt.backup_lba),
                         (73728, 15269854, fakedisk.DISK_SECTORS - 1))
        parts = [(n, s, c) for n, (s, c) in gpt.parts.items()]
        self.assertEqual((len(parts), support.digest(parts)), STOCK_PARTS)
        self.assertEqual([parts[0], parts[19], parts[-1]],
                         [("bootloader_a", 73728, 65536), ("private", 4891648, 32768),
                          ("UDISK", 5555200, 9714655)])
        with open(fakedisk.STOCK_GPT, "rb") as fh:       # what the fake disk serves
            self.assertEqual(parts, fakedisk.gpt_parts(fh.read()))
