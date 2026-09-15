"""h713.identify: one answer for an image, a raw dump and a device (doku/121 stage 2, C1/C6).

The point of the change is in test_hy350_is_not_an_hy300: the three ADT-3 boards carry the same
`build_fingerprint`, so the old one-string recognition would have called a HY350 an HY300 Pro.
"""

import os
import sys
import unittest

import support                 # imported first: it puts the test directory on sys.path
import fakedisk

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE not in sys.path:
    sys.path.insert(0, PACKAGE)

from h713.blockdev import Disk                                   # noqa: E402
from h713.identify import identify, match_profiles, report_device  # noqa: E402
from h713.profiles import PROFILES                               # noqa: E402


class Recorder(support.Recorder):
    """support.Recorder plus the error level report_device uses when it refuses."""

    def error(self, t):
        self.lines.append("ERROR " + t)


_SEEN = {}


def identified(board):
    """identify() of one vendor image -- read once, the three of them are 6 GB."""
    support.need([fakedisk.IMAGES[board]])
    if board not in _SEEN:
        with support.quiet():
            _SEEN[board] = identify(fakedisk.IMAGES[board])
    return _SEEN[board]


def on_disk(case, maker, *args):
    path = os.path.join(support.workdir(case), "emmc.img")
    disk = Disk(maker(path, *args) if args else maker(path), writable=False)
    try:
        with support.quiet():
            return identify(disk)
    finally:
        disk.close()


class Images(unittest.TestCase):
    def test_hy310_image_is_verified(self):
        ident = identified("hy310")
        self.assertEqual((ident["input"], ident["kind"]), ("image", "stock"))
        self.assertEqual((ident["profile"], ident["status"]), ("hy310", "verified"))
        self.assertEqual(ident["candidates"], ["hy310"])
        self.assertTrue(all(ident["matches"]["hy310"].values()))
        self.assertTrue(report_device(ident, Recorder(), writing=True))

    def test_hy300_t08_image_is_profile_only(self):
        ident = identified("hy300-t08")
        self.assertEqual((ident["profile"], ident["status"]), ("hy300_t08", "profile-only"))
        self.assertEqual(ident["candidates"], ["hy300_t08"])
        log = Recorder()
        # profile-only is not a licence to write, whatever the fingerprint says.
        self.assertFalse(report_device(ident, log, writing=True))
        self.assertIn("ERROR", log.text)

    def test_hy350_is_not_an_hy300(self):
        ident = identified("hy350")
        self.assertEqual(ident["profile"], "hy350")
        self.assertEqual(ident["candidates"], ["hy350"])
        for other in ("hy300_t08", "hy300_pro"):
            self.assertNotIn(other, ident["candidates"])
        # ... although the fingerprint is the very same string as the T08's (finding 1).
        self.assertEqual(ident["features"]["build_fingerprint"],
                         PROFILES["hy300_t08"]["expected"]["build_fingerprint"])
        for name in ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "sunxi_version"):
            self.assertFalse(ident["matches"]["hy300_t08"][name], name)

    def test_hy300_pro_plus_ddr3_is_the_qz713df_a1_profile(self):
        # The DDR3 image (0922) is the stock firmware of cstenger's bench board (package F1).
        ident = identified("hy300-pro-plus-ddr3")
        self.assertEqual((ident["input"], ident["kind"]), ("image", "stock"))
        self.assertEqual((ident["profile"], ident["status"]), ("hy200_qz713df_a1", "profile-only"))
        self.assertEqual(ident["candidates"], ["hy200_qz713df_a1"])
        # Not one string: every feature the profile calls strong agrees, and there are seven.
        row = ident["matches"]["hy200_qz713df_a1"]
        self.assertEqual(sorted(k for k, v in row.items() if v),
                         sorted(PROFILES["hy200_qz713df_a1"]["stock"]["strong_features"]))
        log = Recorder()
        # profile-only is not a licence to write, however well the image matches.
        self.assertFalse(report_device(ident, log, writing=True))
        self.assertIn("ERROR", log.text)

    def test_hy300_pro_plus_lpddr3_is_the_qz713_v2_profile(self):
        ident = identified("hy300-pro-plus-lpddr3")
        self.assertEqual((ident["input"], ident["kind"]), ("image", "stock"))
        self.assertEqual((ident["profile"], ident["status"]), ("hy200_qz713_v2", "profile-only"))
        self.assertEqual(ident["candidates"], ["hy200_qz713_v2"])
        row = ident["matches"]["hy200_qz713_v2"]
        self.assertEqual(sorted(k for k, v in row.items() if v),
                         sorted(PROFILES["hy200_qz713_v2"]["stock"]["strong_features"]))
        log = Recorder()
        self.assertFalse(report_device(ident, log, writing=True))
        self.assertIn("ERROR", log.text)

    def test_the_two_hy300_pro_plus_images_are_told_apart(self):
        # Same panel, same partition table, same mips/database.TSE -- they differ in the DRAM block,
        # in the display.bin and in every build id, and that is what the profiles compare.
        ddr3, lpddr3 = identified("hy300-pro-plus-ddr3"), identified("hy300-pro-plus-lpddr3")
        self.assertNotIn("hy200_qz713_v2", ddr3["candidates"])
        self.assertNotIn("hy200_qz713df_a1", lpddr3["candidates"])
        for name in ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
                     "build_fingerprint", "sunxi_version"):
            self.assertFalse(ddr3["matches"]["hy200_qz713_v2"][name], name)
            self.assertFalse(lpddr3["matches"]["hy200_qz713df_a1"][name], name)
        self.assertEqual((ddr3["features"]["dram_clk_mhz"], lpddr3["features"]["dram_clk_mhz"]), (624, 720))
        self.assertEqual((ddr3["features"]["dram"]["type"], lpddr3["features"]["dram"]["type"]), (3, 7))
        self.assertNotEqual(ddr3["features"]["display_bin_sha256"], lpddr3["features"]["display_bin_sha256"])
        # ... although the one feature the ADT-3 boards are also confused by is identical here.
        self.assertEqual(ddr3["features"]["mips_database_sha256"],
                         lpddr3["features"]["mips_database_sha256"])

    def test_the_hy310_image_is_still_the_hy310(self):
        # The two new profiles must not steal the image the release is built from.
        ident = identified("hy310")
        self.assertEqual((ident["profile"], ident["candidates"]), ("hy310", ["hy310"]))

    def test_only_the_hy310_image_disagrees_with_itself(self):
        # doku/121 section 2, finding 6: sys_partition.fex says media_data is 557056 sectors,
        # sunxi_gpt.fex says 524288 -- the device follows sys_partition.fex.
        consistency = identified("hy310")["layout"]["consistency"]
        self.assertEqual([(c["name"], c["sys_partition_sectors"], c["sunxi_gpt_sectors"])
                          for c in consistency], [("media_data", 557056, 524288)])
        for board in ("hy300-t08", "hy350"):
            self.assertEqual(identified(board)["layout"]["consistency"], [], board)

    def test_regions_come_from_the_image_not_from_constants(self):
        # The HY310 has the Reserve0_a/_b pair, the ADT-3 boards a single Reserve0 elsewhere.
        self.assertEqual(sorted(identified("hy310")["regions"]),
                         ["Reserve0_a", "Reserve0_b", "private", "secure-storage"])
        self.assertEqual(sorted(identified("hy350")["regions"]),
                         ["Reserve0", "private", "secure-storage"])


class Disks(unittest.TestCase):
    def test_stock_disk_is_the_hy310(self):
        support.need(fakedisk.NEEDS_STOCK)
        ident = on_disk(self, fakedisk.make_stock_disk)
        self.assertEqual((ident["input"], ident["kind"]), ("device", "stock"))
        self.assertEqual((ident["profile"], ident["status"]), ("hy310", "verified"))
        # No build.prop on this disk (super is zero) -- six features still pin the board down,
        # which is exactly what the one-string recognition could not do.
        self.assertIsNone(ident["features"]["build_fingerprint"])
        self.assertIsNone(ident["matches"]["hy310"]["build_fingerprint"])
        self.assertEqual(len(ident["mips"]["bootloader_a"]), 19)

    def test_v3_disk_is_our_layout(self):
        support.need(fakedisk.NEEDS_V3)
        ident = on_disk(self, fakedisk.make_v3_disk)
        self.assertEqual(ident["kind"], "ours")
        self.assertIsNone(ident["profile"])
        # LBA 16 carries our SPL there, and its eGON.BT0 header must not be read as DRAM
        # settings (uboot-h713 patch 0038).
        self.assertIsNone(ident["features"]["dram_clk_mhz"])
        self.assertTrue(report_device(ident, Recorder(), writing=True))

    def test_adt3_disks_are_told_apart_without_android(self):
        # Boards nobody here has held, and their build.prop is out of reach on these disks:
        # boot0 and the boot package alone separate the T08 from the HY350 (finding 1).
        for board, profile in (("hy300-t08", "hy300_t08"), ("hy350", "hy350")):
            support.need(fakedisk.needs_adt3(board))
            ident = on_disk(self, fakedisk.make_adt3_disk, board)
            self.assertEqual((ident["profile"], ident["kind"]), (profile, "stock"), board)
            self.assertIsNone(ident["features"]["build_fingerprint"], board)
            # one Reserve0, at this board's own LBA -- not the HY310 pair (issue #1, defect 2)
            self.assertEqual(sorted(ident["regions"]), ["Reserve0", "private", "secure-storage"], board)

    def test_empty_disk_has_no_gpt_and_prints_the_profile_row(self):
        path = os.path.join(support.workdir(self), "empty.img")
        with open(path, "wb") as fh:
            fh.truncate(fakedisk.DISK_SECTORS * fakedisk.SECT)
        disk = Disk(path, writable=False)
        try:
            with support.quiet():
                ident = identify(disk)
        finally:
            disk.close()
        os.remove(path)
        self.assertEqual((ident["kind"], ident["profile"], ident["candidates"]), ("no-gpt", None, []))
        text = "\n".join(ident["text"])
        self.assertIn("profile row", text)
        for field in ("sunxi_version", "build_fingerprint", "scp_sha256", "mips_database_sha256",
                      "display_bin_sha256", "project_id", "panel"):
            self.assertIn(field, text, field)


class Matching(unittest.TestCase):
    def _twin(self, board_id, scp):
        return {"id": board_id, "name": board_id.upper(), "status": "profile-only",
                "stock": {"strong_features": ("scp_sha256",)},
                "expected": {"package_item_sha256": {"scp": scp}}}

    def test_two_matching_profiles_leave_the_board_open(self):
        twins = {"twin_a": self._twin("twin_a", "a" * 64), "twin_b": self._twin("twin_b", "a" * 64)}
        profile, candidates, matches = match_profiles({"scp_sha256": "a" * 64}, twins)
        self.assertIsNone(profile)
        self.assertEqual(sorted(candidates), ["twin_a", "twin_b"])
        self.assertEqual(matches["twin_a"], {"scp_sha256": True})

    def test_a_profile_without_strong_features_never_matches(self):
        # HY300 Pro: nothing known about it is unique, so it must not be a candidate for
        # anything -- not even for a feature set that contradicts nothing.
        self.assertEqual(PROFILES["hy300_pro"]["stock"]["strong_features"], ())
        _profile, candidates, matches = match_profiles({"build_fingerprint": "whatever"})
        self.assertNotIn("hy300_pro", candidates)
        self.assertEqual(matches["hy300_pro"], {})

    def test_nothing_read_means_no_candidate(self):
        profile, candidates, _matches = match_profiles({})
        self.assertEqual((profile, candidates), (None, []))
