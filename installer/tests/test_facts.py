"""h713.facts: the image JSON package A1 froze, and the same sections read off a device.

The three JSON files under fixtures/images/ are the contract for `image_facts()`: byte for byte,
sorted keys, indent 2. `device_facts()` has no frozen file -- a device is not a repository fixture,
so the fake stock eMMC is checked against the values the HY310 profile declares.
"""

import json
import os
import sys
import unittest

import support                 # imported first: it puts the test directory on sys.path
import fakedisk

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE not in sys.path:
    sys.path.insert(0, PACKAGE)

from h713.facts import device_facts, dumps, image_facts          # noqa: E402
from h713.profiles import PROFILES                               # noqa: E402
from h713.source import FileSource                               # noqa: E402

#: board (key of fakedisk.IMAGES) -> the frozen JSON, as it lies in fixtures/images/. The first three
#: were written by A1 on 14.09.2026; the two HY300 Pro+ images came with package F1 (15.09.2026) and
#: live under umbau/fixtures-local, so their tests run with run.sh --local only.
FROZEN = {"hy310": "hy310-update.img.json", "hy300-t08": "hy300-t08.json", "hy350": "hy350.json",
          "hy300-pro-plus-ddr3": "hy300-pro-plus-ddr3-0922.json",
          "hy300-pro-plus-lpddr3": "hy300-pro-plus-lpddr3-0710.json"}


def frozen_path(name):
    return os.path.join(fakedisk.FIXTURES, "images", name)


class ImageFacts(unittest.TestCase):
    """image_facts() must reproduce A1's JSON exactly -- that is what makes it a move, not a rewrite."""

    def _check(self, board):
        support.need([fakedisk.IMAGES[board], frozen_path(FROZEN[board])])
        with open(frozen_path(FROZEN[board]), "r", encoding="utf-8") as fh:
            want = fh.read()
        with support.quiet():
            got = dumps(image_facts(fakedisk.IMAGES[board]))
        self.assertEqual(got, want, "%s: image_facts differs from the frozen JSON" % board)

    def test_hy310(self):
        self._check("hy310")

    def test_hy300_t08(self):
        self._check("hy300-t08")

    def test_hy350(self):
        self._check("hy350")

    def test_hy300_pro_plus_ddr3(self):
        self._check("hy300-pro-plus-ddr3")

    def test_hy300_pro_plus_lpddr3(self):
        self._check("hy300-pro-plus-lpddr3")

    def test_every_frozen_file_is_covered(self):
        listed = sorted(n for n in os.listdir(os.path.join(fakedisk.FIXTURES, "images"))
                        if n.endswith(".json"))
        self.assertEqual(listed, sorted(FROZEN.values()))


class DeviceFacts(unittest.TestCase):
    """The same sections off the fake stock eMMC: everything the HY310 profile declares is there."""

    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK)
        self.disk = fakedisk.make_stock_disk(os.path.join(support.workdir(self), "emmc.img"))
        self.before = fakedisk.journal(self.disk)
        source = FileSource(self.disk)
        try:
            with support.quiet():
                self.facts = device_facts(source)
        finally:
            source.fh.close()

    def test_nothing_was_written(self):
        self.assertEqual(fakedisk.journal(self.disk), self.before)

    def test_gpt_is_the_stock_layout(self):
        layout = PROFILES["hy310"]["layout"]
        self.assertEqual(self.facts["gpt"]["header"]["entries"], layout["entries"])
        self.assertEqual(self.facts["gpt"]["header"]["first_usable"], layout["first_usable"])
        self.assertEqual([e["name"] for e in self.facts["gpt"]["entries"]],
                         [p[0] for p in layout["partitions"]])

    def test_boot0_gives_the_dram_block(self):
        dram = PROFILES["hy310"]["dram"]
        self.assertEqual(self.facts["boot0"]["magic"], "eGON.BT0")
        self.assertEqual(self.facts["boot0"]["lba"], 16)
        self.assertEqual(self.facts["boot0"]["dram_clk_mhz"], dram["clk"])
        self.assertEqual(self.facts["boot0"]["dram"]["tpr11"], dram["tpr11"])

    def test_boot_package_gives_items_and_versions(self):
        expected = PROFILES["hy310"]["expected"]
        package = self.facts["boot_package"]
        self.assertTrue(package["checksum_ok"])
        self.assertEqual(package["lba"], 24576)
        self.assertEqual(dict((i["name"], i["sha256"]) for i in package["items"]),
                         expected["package_item_sha256"])
        self.assertEqual(dict((i["name"], i["size"]) for i in package["items"]),
                         expected["package_items"])
        self.assertTrue(package["uboot_version"].startswith(expected["uboot_version"]))
        self.assertTrue(package["arisc_version"].startswith(expected["arisc_version"]))
        self.assertIn(expected["dtb_compatible"], package["dtb_compatible"])

    def test_bootloader_fat_gives_the_mips_files(self):
        expected = PROFILES["hy310"]["expected"]
        for slot in ("bootloader_a", "bootloader_b"):
            files = self.facts["mips"][slot]
            self.assertEqual(len(files), 19, slot)
            self.assertEqual(files["database.TSE"]["sha256"], expected["mips_database_sha256"], slot)
        display = self.facts["mips_files"]["display_bin"]
        self.assertEqual(display["sha256"], PROFILES["hy310"]["mips"]["revisions"][0]["sha256"])
        self.assertEqual(display["size"], PROFILES["hy310"]["mips"]["revisions"][0]["size"])

    def test_sections_a_device_cannot_answer_are_none(self):
        # super is all zeros on the fake disk, so there is no vendor and no build.prop; the
        # section has to say so instead of pretending (fakedisk.py: "geraet_erkennen gives up").
        self.assertIsNone(self.facts["super"]["partitions"])
        self.assertIsNone(self.facts["vendor_build_prop"]["ro.vendor.build.fingerprint"])
        for key in ("imagewty", "sunxi_version", "sunxi_gpt", "sys_config"):
            self.assertIsNone(self.facts[key], key)

    def test_the_facts_are_json(self):
        json.loads(dumps(self.facts))
