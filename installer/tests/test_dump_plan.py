"""abzug_klein(): what the mandatory small backup takes off the device, and what
of it may go on screen (fix B4 of 13.09.: no secure-storage hash in a log)."""

import hashlib
import os
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
EMPTY_16M = "080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e"
V3_ENV_ROW = ("uboot-env", 14336, 128,
              "U-Boot-Umgebung, 77 Eintraege (h713_gate=1, h713_boot=emmc)")


def _dump(case, build, our_layout):
    tmp = support.workdir(case)
    disk = build(os.path.join(tmp, "emmc.img"))
    out, log = os.path.join(tmp, "backup"), support.Recorder()
    inst = support.tool("install")
    platte = inst.Platte(disk, schreiben=False)
    try:
        manifest = inst.abzug_klein(platte, out, log=log, unser_layout=our_layout)
    finally:
        platte.close()
    return manifest, log, out


def _saved(out, name):
    with open(os.path.join(out, "%s.bin" % name), "rb") as fh:
        return fh.read()


class StockDisk(unittest.TestCase):
    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK)
        self.manifest, self.log, self.out = _dump(self, fakedisk.make_stock_disk, False)

    def test_manifest_and_saved_bytes_are_what_was_on_the_disk(self):
        self.assertEqual([(n, l, s, z) for n, l, s, _h, z in self.manifest],
                         [(n, l, s, p) for n, l, s, _t, p in REGIONS])
        for (name, lba, sectors, tag, _p), row in zip(REGIONS, self.manifest):
            want = fakedisk.pattern(tag, lba, sectors)
            self.assertEqual(_saved(self.out, name), want, name)
            self.assertEqual(row[3], hashlib.sha256(want).hexdigest(), name)
        self.assertEqual(sorted(os.listdir(self.out)),
                         ["private.bin", "reserve0-a.bin", "reserve0-b.bin",
                          "secure-storage.bin"])
        self.assertNotIn("leer", self.log.text)

    def test_screen_never_shows_a_device_fingerprint(self):
        rows = dict((r[0], r[3]) for r in self.manifest)
        for name in ("secure-storage", "private"):
            self.assertNotIn(rows[name][:16], self.log.text, name)
            self.assertIn("%s " % name, self.log.text)
        # Reserve0 is device-only too (EINMALIG says so) and its hash IS shown.
        # Frozen as today's behaviour -- stage 2 decides whether that is right.
        for name in ("reserve0-a", "reserve0-b"):
            self.assertIn(rows[name][:16], self.log.text, name)


class LayoutV3Disk(unittest.TestCase):
    def setUp(self):
        support.need(fakedisk.NEEDS_V3)
        self.manifest, self.log, self.out = _dump(self, fakedisk.make_v3_disk, True)

    def test_manifest_adds_the_uboot_environment(self):
        self.assertEqual([m[0] for m in self.manifest],
                         ["secure-storage", "private", "reserve0-a", "reserve0-b",
                          "uboot-env"])
        row = self.manifest[-1]
        self.assertEqual((row[0], row[1], row[2], row[4]), V3_ENV_ROW)
        with open(fakedisk.V3_ENV, "rb") as fh:
            self.assertEqual(_saved(self.out, "uboot-env"), fh.read())

    def test_android_regions_are_empty_on_our_layout(self):
        for row in self.manifest[1:4]:
            self.assertEqual(row[3], EMPTY_16M, row[0])
            self.assertIn("[leer]", row[4], row[0])
        self.assertIn("WARN Leer und damit ohne Inhalt: private, reserve0-a, "
                      "reserve0-b.", self.log.lines)

    def test_secure_storage_is_there_and_still_not_on_screen(self):
        want = fakedisk.pattern("secure-storage", 12288, 2048)
        self.assertEqual(_saved(self.out, "secure-storage"), want)
        self.assertNotIn(hashlib.sha256(want).hexdigest()[:16], self.log.text)
