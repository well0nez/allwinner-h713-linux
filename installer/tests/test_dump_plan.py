"""abzug_klein(): what the mandatory small backup takes off the device, and what
of it may go on screen (fix B4 of 13.09.: no secure-storage hash in a log).

Stage 2 C-B: the regions are looked up in the device's own GPT by name, the MIPS/display
artefacts of both bootloader slots are saved as well, and no hash of a device-only region
goes on screen. Every re-frozen value below names the old one and the reason.
"""

import hashlib
import os
import shutil
import tempfile
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from hy310-install.py 0.1 (EINMALIG + ENV_LBA).  The hashes
# are NOT frozen as literals: they are recomputed from fakedisk.pattern(), so a
# changed fake disk cannot silently make this test pass.
REGIONS = (
    ("secure-storage", 12288, 2048, "secure-storage",
     "HDCP-Schluessel, WLAN-/BT-MAC-Adressen, Seriennummer"),
    ("private", 4891648, 32768, "private", "Android Secure-Storage-Partition"),
    ("reserve0-a", 5489664, 32768, "Reserve0_a", "Reserve0, Slot A"),
    ("reserve0-b", 5522432, 32768, "Reserve0_b", "Reserve0, Slot B"))
# The same table for the HY300 T08, read off its own sunxi_gpt.fex: one single Reserve0,
# and private 2 GiB further out than on the HY310. Frozen 2026-09-14 by C-B.
ADT3_REGIONS = (
    ("secure-storage", 12288, 2048, "HDCP-Schluessel, WLAN-/BT-MAC-Adressen, Seriennummer"),
    ("private", 6988800, 32768, "Android Secure-Storage-Partition"),
    ("reserve0", 7062528, 32768, "Reserve0 (single slot)"))
EMPTY_16M = "080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e"
V3_ENV_ROW = ("uboot-env", 14336, 128,
              "U-Boot-Umgebung, 77 Eintraege (h713_gate=1, h713_boot=emmc)")
# mips/ of the stock bootloader partition (fixture hy310-stock-bootloader_b-20260831.fat),
# frozen 2026-09-14 by C-B. Names and total size only -- the sha256 of every file is
# checked against the saved bytes, so no vendor hash has to stand in the repository.
MIPS_FILES = ("LogoRegData.bin", "ProjectID_0x0001.TSE", "ProjectID_0x0012.TSE",
              "ProjectID_0x0013.TSE", "ProjectID_0x0014.TSE", "ProjectID_0x0015.TSE",
              "ProjectID_0x0016.TSE", "ProjectID_0x0020.TSE", "ProjectID_0x0030.TSE",
              "ProjectID_0x0031.TSE", "ProjectID_0x0032.TSE", "ProjectID_0x0033.TSE",
              "ProjectID_0x0034.TSE", "ProjectID_0x0035.TSE", "database.TSE",
              "display.bin", "display_cfg.xml", "pq_custom.TSE", "projecttable.TSE")
MIPS_BYTES = 1973242


def _dump(cls, build, our_layout, *args):
    """Fake disk and small backup, once per class -- the stock disk costs 130 MiB."""
    tmp = tempfile.mkdtemp(prefix="cb-dump-")
    cls.addClassCleanup(shutil.rmtree, tmp, True)
    disk = build(os.path.join(tmp, "emmc.img"), *args)
    out, log = os.path.join(tmp, "backup"), support.Recorder()
    inst = support.tool("install")
    platte = inst.Platte(disk, schreiben=False)
    try:
        cls.manifest = inst.abzug_klein(platte, out, log=log, unser_layout=our_layout)
    finally:
        platte.close()
    cls.log, cls.out = log, out


def _saved(out, *name):
    with open(os.path.join(out, *name), "rb") as fh:
        return fh.read()


def _info(manifest, key):
    """What stage 2 added to the manifest but not to a row (DumpResult.info)."""
    info = getattr(manifest, "info", None)
    if info is None:
        raise unittest.SkipTest("DumpResult.info: stage 2 C-B, not in these tools")
    return info[key]


class StockDisk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.need(fakedisk.NEEDS_STOCK)
        _dump(cls, fakedisk.make_stock_disk, False)

    def test_manifest_and_saved_bytes_are_what_was_on_the_disk(self):
        self.assertEqual([(n, l, s, z) for n, l, s, _h, z in self.manifest],
                         [(n, l, s, p) for n, l, s, _t, p in REGIONS])
        for (name, lba, sectors, tag, _p), row in zip(REGIONS, self.manifest):
            want = fakedisk.pattern(tag, lba, sectors)
            self.assertEqual(_saved(self.out, "%s.bin" % name), want, name)
            self.assertEqual(row[3], hashlib.sha256(want).hexdigest(), name)
        # was without "mips" until stage 2 C-B: the backup now also carries the
        # MIPS/display artefacts of both bootloader slots (brief CB §2).
        self.assertEqual(sorted(os.listdir(self.out)),
                         ["mips", "private.bin", "reserve0-a.bin", "reserve0-b.bin",
                          "secure-storage.bin"])
        self.assertNotIn("leer", self.log.text)

    def test_screen_never_shows_a_device_fingerprint(self):
        rows = dict((r[0], r[3]) for r in self.manifest)
        # was: only secure-storage and private were hidden, the reserve0-a/-b hashes
        # went on screen ("known bug" in dump.py). Stage 2 C-B hides all four -- they
        # are device-only just as much (brief CB §3).
        for name in ("secure-storage", "private", "reserve0-a", "reserve0-b"):
            self.assertNotIn(rows[name][:16], self.log.text, name)
            self.assertIn("%s " % name, self.log.text)

    def test_mips_comes_out_of_both_bootloader_slots(self):
        mips = _info(self.manifest, "mips")
        for slot in ("bootloader_a", "bootloader_b"):
            self.assertEqual(tuple(sorted(mips[slot])), MIPS_FILES, slot)
            self.assertEqual(sum(f["size"] for f in mips[slot].values()), MIPS_BYTES, slot)
            for name, f in mips[slot].items():
                data = _saved(self.out, "mips", slot, name)
                self.assertEqual(len(data), f["size"], name)
                self.assertEqual(hashlib.sha256(data).hexdigest(), f["sha256"], name)
        self.assertEqual(mips["bootloader_a"], mips["bootloader_b"])
        self.assertIn("OK mips/: the two bootloader slots hold the same 19 files",
                      self.log.lines)

    def test_the_sources_that_this_disk_cannot_offer_are_named_not_thrown(self):
        # super, Reserve0_a and media_data are zeros resp. pattern on the fake disk:
        # every one of them has to be skipped cleanly and said out loud.
        mips = _info(self.manifest, "mips")
        for source, said in (("vendor", "mips/: vendor is not there or not readable"),
                             ("reserve0", "mips/: Reserve0_a carries no FAT filesystem"),
                             ("media_data", "mips/: media_data not readable")):
            self.assertIsNone(mips[source], source)
            self.assertIn(said, self.log.text, source)
        self.assertIsNone(_info(self.manifest, "active_slot"))
        self.assertIn("INFO mips/: active slot unknown (no readable bootloader_control)",
                      self.log.lines)

    def test_the_manifest_says_the_regions_were_found_by_name(self):
        self.assertIs(_info(self.manifest, "regions_by_name"), True)


class Adt3Disk(unittest.TestCase):
    """A board we have never held: one single Reserve0, private 2 GiB further out,
    and no mips/ in either bootloader slot."""

    @classmethod
    def setUpClass(cls):
        support.need(fakedisk.needs_adt3("hy300-t08"))
        _dump(cls, fakedisk.make_adt3_disk, False, "hy300-t08")

    def test_the_regions_sit_where_this_board_s_gpt_says(self):
        self.assertEqual([(n, l, s, z) for n, l, s, _h, z in self.manifest],
                         list(ADT3_REGIONS))
        self.assertEqual(sorted(os.listdir(self.out)),
                         ["private.bin", "reserve0.bin", "secure-storage.bin"])
        for name, lba, sectors, _p in ADT3_REGIONS[1:]:
            tag = {"private": "private", "reserve0": "Reserve0"}[name]
            self.assertEqual(_saved(self.out, "%s.bin" % name),
                             fakedisk.pattern(tag, lba, sectors), name)

    def test_no_mips_in_either_slot_and_the_vendor_copy_is_skipped_cleanly(self):
        mips = _info(self.manifest, "mips")
        self.assertEqual([k for k, v in mips.items() if v], [])
        self.assertIn("INFO mips/: bootloader_a has no mips/ directory", self.log.lines)
        self.assertIn("INFO mips/: bootloader_b carries no FAT filesystem", self.log.lines)
        self.assertIn("INFO mips/: a bootloader slot without mips/ is the normal state "
                      "of the ADT-3 family", self.log.lines)
        self.assertIn("mips/: vendor is not there or not readable", self.log.text)
        self.assertFalse(os.path.exists(os.path.join(self.out, "mips")))


class LayoutV3Disk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.need(fakedisk.NEEDS_V3)
        _dump(cls, fakedisk.make_v3_disk, True)

    def test_manifest_is_the_keys_and_the_environment(self):
        # was ["secure-storage", "private", "reserve0-a", "reserve0-b", "uboot-env"]
        # with the three Android regions saved as 16 MiB of zeros (EMPTY_16M) and
        # reported as "Leer und damit ohne Inhalt: private, reserve0-a, reserve0-b."
        # Stage 2 C-B: our layout has no such partitions in its GPT, so the by-name
        # lookup finds none -- keys plus environment is what is left (brief CB §1).
        _info(self.manifest, "regions_by_name")       # skips on the pre-stage-2 tools
        self.assertEqual([m[0] for m in self.manifest], ["secure-storage", "uboot-env"])
        self.assertEqual(sorted(os.listdir(self.out)),
                         ["secure-storage.bin", "uboot-env.bin"])
        self.assertNotIn(EMPTY_16M, [m[3] for m in self.manifest])
        self.assertNotIn("Leer und damit ohne Inhalt", self.log.text)

    def test_manifest_adds_the_uboot_environment(self):
        row = self.manifest[-1]
        self.assertEqual((row[0], row[1], row[2], row[4]), V3_ENV_ROW)
        with open(fakedisk.V3_ENV, "rb") as fh:
            self.assertEqual(_saved(self.out, "uboot-env.bin"), fh.read())

    def test_secure_storage_is_there_and_still_not_on_screen(self):
        want = fakedisk.pattern("secure-storage", 12288, 2048)
        self.assertEqual(_saved(self.out, "secure-storage.bin"), want)
        self.assertNotIn(hashlib.sha256(want).hexdigest()[:16], self.log.text)

    def test_our_layout_has_no_bootloader_slots_and_says_so(self):
        self.assertEqual([k for k, v in _info(self.manifest, "mips").items() if v], [])
        self.assertIn("INFO mips/: no partition bootloader_a in the GPT", self.log.lines)
