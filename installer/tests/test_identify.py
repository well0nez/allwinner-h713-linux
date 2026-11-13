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
from h713.identify import ISSUES, identify, match_profiles, report_device  # noqa: E402
from h713.profiles import PROFILES, get                          # noqa: E402

PLUS = "hy200_qz713df_a1/projector09220931"     # the 2025-09-22 firmware of the HY200 QZ713DF A1
T08_OTA = "hy300_t08/ota20240419"               # the HY300 T08's stock OTA image (the issue #7 unit is unit202311)


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


# The identity row the HY300 Pro's owner posted from his v0.6-beta installer run (issue #1, 15.09.2026),
# as identify() would build it from his device. The fingerprint and the MIPS database are the ADT-3
# family's and shared with the HY300 T08 image; the boot package and the dates are his alone.
HY300_PRO_DEVICE = {
    "sunxi_version": None,
    "build_fingerprint": "ADT-3/adt3/adt3:10/QTT1.200116.002.B6/6245789:user/release-keys",
    "uboot_version": "U-Boot 2018.05-00026-g72fa926 (Dec 16 2024 - 03:52:57 +0000) Allwinner Technology",
    "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Dec 25 2024 Time: 17:26:41",
    "scp_sha256": "699dd131d5d3bde351c70e0b395e55183ca17097e8335eab8a4027b7c5b96dc3",
    "uboot_sha256": "e9e7fedf474eb230decbe26fa6d72396b77a60424d855e5241d88e0d5fe5f017",
    "dtb_sha256": "0df826b17d17662cb096887eb898d8721e5ef6f717552400c96b8e79b563c78c",
    "dtb_compatible": "allwinner,tv303 arm,sun50iw12p1",
    "mips_database_sha256": "6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4",
    "vendor_size": 115900416,
}


class HY300ProDevice(unittest.TestCase):
    """The board the test image hy300-pro-test1 is for must be recognised from its own features --
    the first run at the owner's device failed exactly here (the profile declared none)."""

    def test_the_owners_device_matches_the_profile_alone(self):
        profile, candidates, matches = match_profiles(HY300_PRO_DEVICE)
        self.assertEqual((profile, candidates), ("hy300_pro", ["hy300_pro"]))
        for name in PROFILES["hy300_pro"]["stock"]["strong_features"]:
            self.assertTrue(matches["hy300_pro"][name], name)

    def test_the_t08_image_does_not_look_like_the_pro(self):
        from h713.profiles import expected_features
        profile, candidates, _matches = match_profiles(dict(expected_features(get(T08_OTA))))
        self.assertEqual((profile, candidates), (T08_OTA, [T08_OTA]))


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
        self.assertEqual((ident["profile"], ident["status"]), (T08_OTA, "profile-only"))
        self.assertEqual(ident["variant"], "ota20240419")
        self.assertEqual(ident["candidates"], [T08_OTA])
        log = Recorder()
        # profile-only is not a licence to write, whatever the fingerprint says.
        self.assertFalse(report_device(ident, log, writing=True))
        self.assertIn("ERROR", log.text)

    def test_hy350_is_not_an_hy300(self):
        ident = identified("hy350")
        self.assertEqual(ident["profile"], "hy350")
        self.assertEqual(ident["candidates"], ["hy350"])
        for other in (T08_OTA, "hy300_t08/unit202311", "hy300_pro"):
            self.assertNotIn(other, ident["candidates"])
        # ... although the fingerprint is the very same string as the T08's (finding 1).
        self.assertEqual(ident["features"]["build_fingerprint"],
                         get(T08_OTA)["expected"]["build_fingerprint"])
        for name in ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "sunxi_version"):
            self.assertFalse(ident["matches"][T08_OTA][name], name)

    def test_the_issue_10_unit_is_the_t08_s_third_firmware(self):
        # The identify row the owner posted (issue #10, 05.11.2026): the T08's DRAM block, display firmware and
        # database under a boot package of 2023-08 nobody else has, on an eMMC of 14942208 sectors. His first run
        # found no drive, because find_drive knew no such size (test_drive_sizes); match_profiles names the variant.
        row = {"build_fingerprint": get(T08_OTA)["expected"]["build_fingerprint"],
               "uboot_version": "U-Boot 2018.05-00008-gc26a358 (Aug 08 2023 - 02:18:08 +0000) Allwinner Technology",
               "arisc_version": "TV-303  ARISC  00.00.00.09 Date:Aug 12 2023 Time: 20:23:17",
               "scp_sha256": "631e06bd4f1b009e28b8396076847089d5ad0d3fb31a0586566aa103c2d18a66",
               "uboot_sha256": "f2ee7681c5e082a4f4cdb131699ecad7424eb4b9d01bcd7eca9d7b013cc3390f",
               "dtb_sha256": "e0ee997e54bde61be5078563a0172bde55502dea3c9f307923715d878bdfeb46",
               "dtb_compatible": "allwinner,tv303 arm,sun50iw12p1",
               "mips_database_sha256": get(T08_OTA)["expected"]["mips_database_sha256"],
               "vendor_size": 115920896, "sunxi_version": None}
        best, candidates, _matches = match_profiles(row)
        self.assertEqual((best, candidates), ("hy300_t08/fw20250221", ["hy300_t08/fw20250221"]))
        self.assertEqual(get("hy300_t08/fw20250221")["layout"]["disk_sectors"], 14942208)

    def test_the_two_hy300_2023_units_are_the_board_s_two_variants(self):
        # The HY300 with a 2023 firmware has two owners and two boot packages (issues #8 and #11), the same DRAM
        # block, panel and table: one board, variants fw202306 and fw202312. Until 13.11.2026 the first unit was
        # the whole profile "hy300_2023"; the rows are the owners' identify rows (06.11. and 11.11.2026).
        base = {"build_fingerprint": get("hy300_2023/fw202306")["expected"]["build_fingerprint"],
                "dtb_compatible": "allwinner,tv303 arm,sun50iw12p1", "sunxi_version": None}
        unit8 = dict(base, uboot_version="U-Boot 2018.05-00005-g6d2f0a5-dirty (Jun 25 2023 - 15:41:51 +0800) Allwinner Technology",
                     arisc_version="TV-303  ARISC  00.00.00.09 Date:Jun 25 2023 Time: 15:41:51",
                     scp_sha256="50e8725e2309397c33e2f2a9beb363184e225cc7f693ab08ec8b0b7627280b81",
                     uboot_sha256="a8f2bfe87a1c4c46b628b908b978998c8c8c303c879a0f77ec3b02e8e94690e1",
                     dtb_sha256="a84bfbd574210aa0065e2fd4441ed5f3a35cffa966855aab0325d9e3bb102c7e",
                     mips_database_sha256="921c46537805b569c21d74523f7501e5c4ad96924d53b0b80495f50db58fb73b", vendor_size=110755840)
        unit11 = dict(base, uboot_version="U-Boot 2018.05-00017-g1e43c6c (Dec 08 2023 - 11:58:22 +0000) Allwinner Technology",
                      arisc_version="TV-303  ARISC  00.00.00.09 Date:Dec 27 2023 Time: 11:27:06",
                      scp_sha256="d818f98a3d3a4077ba5690b6175a0e449e1d1a4de4460684957233ebd797e355",
                      uboot_sha256="96a07318f6b011531ca53ac1cba5227d78b072743be3a748851292443612fe79",
                      dtb_sha256="68011339ae4f381fa302536aa1dc0981178513e8649ef2383117a1827c90fb8a",
                      mips_database_sha256="6d43b85a5880d34df0428f234c0c713ac1ca7ec28e551554137d967f60c380e4", vendor_size=110202880)
        for row, unit in ((unit8, "hy300_2023/fw202306"), (unit11, "hy300_2023/fw202312")):
            best, candidates, _matches = match_profiles(row)
            self.assertEqual((best, candidates), (unit, [unit]))
        self.assertEqual(get("hy300_2023/fw202312")["mips"]["revisions"][0]["name"], "ADT-3 2024-09")
        self.assertEqual(get("hy300_2023/fw202306")["mips"]["revisions"][0]["name"], "ADT-3 2023-06")

    def test_hy300_pro_plus_ddr3_is_the_qz713df_a1_profile(self):
        # The DDR3 image (0922) is one of the two stock firmwares of the HY200 QZ713DF A1, the
        # board of cstenger's bench and of the HY300PRO-G-EU (package F1, ST3-BOARDMERGE).
        ident = identified("hy300-pro-plus-ddr3")
        self.assertEqual((ident["input"], ident["kind"]), ("image", "stock"))
        self.assertEqual((ident["profile"], ident["status"]), (PLUS, "verified"))
        self.assertEqual(ident["variant"], "projector09220931")
        self.assertEqual(ident["candidates"], [PLUS])
        # Not one string: every feature the variant calls strong agrees, and there are seven ...
        row = ident["matches"][PLUS]
        self.assertEqual(sorted(k for k, v in row.items() if v),
                         sorted(get(PLUS)["stock"]["strong_features"]))
        # ... and none of the other firmware of the same board does.
        other = ident["matches"]["hy200_qz713df_a1/projector05061226"]
        self.assertEqual([k for k, v in other.items() if v], [])
        log = Recorder()
        # verified since issue #4 (30.10.2026): a yes to writing, like the HY310's.
        self.assertTrue(report_device(ident, log, writing=True))
        self.assertNotIn("ERROR", log.text)

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
        self.assertNotIn(PLUS, lpddr3["candidates"])
        for name in ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
                     "build_fingerprint", "sunxi_version"):
            self.assertFalse(ddr3["matches"]["hy200_qz713_v2"][name], name)
            self.assertFalse(lpddr3["matches"][PLUS][name], name)
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
        for board, profile in (("hy300-t08", T08_OTA), ("hy350", "hy350")):
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
        # A profile that names nothing unique must not be a candidate for anything -- not
        # even for a feature set that contradicts nothing. (The HY300 Pro was that profile
        # until its owner's installer run supplied its features, 15.09.2026.)
        blank = dict(PROFILES["hy300_pro"])
        blank["stock"] = dict(blank["stock"], strong_features=())
        _profile, candidates, matches = match_profiles({"build_fingerprint": "whatever"},
                                                        {"blank": blank})
        self.assertNotIn("blank", candidates)
        self.assertEqual(matches["blank"], {})

    def test_nothing_read_means_no_candidate(self):
        profile, candidates, _matches = match_profiles({})
        self.assertEqual((profile, candidates), (None, []))


class AnUnknownFirmwareAsksForAnIssue(unittest.TestCase):
    """TODO 5.23 (Marco 12.10.2026): a board or firmware the table does not know is never guessed at,
    and the refusal says where to report it - an issue with the row the installer printed."""

    UNKNOWN = {"text": "", "_lines": [("info", "the row")], "status": None, "kind": "stock", "profile": None}
    FP = "Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector99999999:user/release-keys"

    def test_a_write_stops_and_names_the_issue_page(self):
        log = Recorder()
        self.assertFalse(report_device(dict(self.UNKNOWN), log, writing=True))
        self.assertIn("ERROR", log.text)
        self.assertIn("open an issue with the row above", log.text)
        self.assertIn(ISSUES, log.text)

    def test_reading_goes_on_and_names_it_too(self):
        log = Recorder()
        self.assertTrue(report_device(dict(self.UNKNOWN), log, writing=False))
        self.assertNotIn("ERROR", log.text)
        self.assertIn(ISSUES, log.text)

    def test_a_known_board_without_a_green_run_is_no_issue(self):
        log = Recorder()
        self.assertFalse(report_device(dict(self.UNKNOWN, profile="hy300_pro", status="partial"), log, writing=True))
        self.assertNotIn(ISSUES, log.text)

    def test_the_old_report_by_fingerprint_names_it(self):
        for writing in (True, False):
            log = Recorder()
            found = {"layout": "stock layout, 26 partitions", "fingerprint": self.FP, "known": False, "device": None}
            self.assertEqual(report_device(found, log, writing=writing), not writing)
            self.assertIn("open an issue with the fingerprint line above", log.text)
            self.assertIn(ISSUES, log.text)

    def test_the_address_is_the_repository_s_issue_page(self):
        self.assertEqual(ISSUES, "https://github.com/well0nez/allwinner-h713-linux/issues")


if __name__ == "__main__":
    unittest.main()
