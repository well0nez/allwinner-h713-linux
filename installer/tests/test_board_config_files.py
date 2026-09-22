"""Q7 item 1: the two vendor TEXT files that describe the board.

Item 1 - `pq/panel_config.ini` (AP3g section 9 D1) and `pq/camprjspe.ini` (AP1 section 3) are copied
out of the image, checked for their mandatory keys, hashed into the reference table, and documented.

No vendor file is read: the inis below are written by this test out of the numbers the board profiles
already carry, and the reference digests are compared against the profile, not against an image.
The runs over the real images are in the Q7 report; they cannot run without the firmware archive.
"""

import importlib.machinery
import importlib.util
import os
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path

sys.path.insert(0, support.TOOLS)
from h713 import vendorfiles                                    # noqa: E402
from h713.profiles import PROFILES, legacy_devices              # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(REPO, "docs", "tools", "h713-extract.md")

# A panel_config.ini in the vendor's own shape: [section], '#' comments, spaces around '='.
PANEL_INI = b"""[PanelSetting]
ProjectID = 48
PanelWidth =1920
PanelHeight=1080
#PanelDualPort: 0-single, 1-dual, 2-quad
PanelDualPort   =   1
PanelHTotal          =   2128
PanelVTotal          =   1120
PanelDCLK           =   143001600
"""
# camprjspe.ini has NO section header at all and terminates every value with ';'.
CAM_INI = b"""DLP_AXIS = 0;
F     = 64.555834;
Whalf = 39.478412;
Hhalf = 22.145381;
U1    = 67.484363;
U2    = 66.334363;
Vdec  = 28.200000;
CRC   = 0000000000000000;

[
PID=0x5803;
]
"""


class TextConfigCheck(unittest.TestCase):
    """check_text_config: the mandatory keys, and nothing else."""

    def test_a_complete_panel_config_passes(self):
        self.assertEqual(vendorfiles.check_text_config("panel_config.ini", PANEL_INI), [])

    def test_a_complete_camprjspe_passes_although_it_has_no_section(self):
        """The reason this check does not use parse_ini: every key stands before the first [."""
        self.assertEqual(vendorfiles.check_text_config("camprjspe.ini", CAM_INI), [])

    def test_a_missing_key_is_named_one_by_one(self):
        cut = b"\n".join(l for l in PANEL_INI.split(b"\n") if not l.startswith(b"PanelDCLK"))
        self.assertEqual(vendorfiles.check_text_config("panel_config.ini", cut), ["PanelDCLK missing"])

    def test_the_crc_line_of_camprjspe_is_mandatory(self):
        cut = b"\n".join(l for l in CAM_INI.split(b"\n") if not l.startswith(b"CRC"))
        self.assertEqual(vendorfiles.check_text_config("camprjspe.ini", cut), ["CRC missing"])

    def test_a_comment_that_mentions_a_key_does_not_count_as_the_key(self):
        only_comment = b"[PanelSetting]\n#PanelDCLK = 143001600\n"
        self.assertIn("PanelDCLK missing", vendorfiles.check_text_config("panel_config.ini", only_comment))

    def test_an_unknown_file_name_has_no_mandatory_keys(self):
        self.assertEqual(vendorfiles.check_text_config("something.ini", b""), [])


class WhereTheyLand(unittest.TestCase):

    def test_both_files_land_next_to_the_pq_set(self):
        self.assertEqual(vendorfiles.PANEL_CONFIG_OUTPUT, "pq/panel_config.ini")
        self.assertEqual(vendorfiles.CAMPRJSPE_OUTPUT, "pq/camprjspe.ini")

    def test_panel_config_is_looked_for_where_panelcontrol_looks(self):
        self.assertEqual(vendorfiles.PANEL_CONFIG_CANDIDATES[0],
                         "/etc/tvconfig/panel_config/panel_config.ini")

    def test_camprjspe_is_looked_for_in_the_system_partition(self):
        self.assertIn("/system/camprjspe.ini", vendorfiles.CAMPRJSPE_CANDIDATES)
        self.assertEqual(vendorfiles.SYSTEM_PARTITIONS[0], "system_a")

    def test_the_hy310_profile_carries_a_reference_for_both(self):
        reference = PROFILES["hy310"]["reference"]
        self.assertEqual(reference[vendorfiles.PANEL_CONFIG_OUTPUT],
                         (2709, "b024f6e060580d2a7a4ede4b83e5669c184458437342050a1ba7f33dfd03db99"))
        self.assertEqual(reference[vendorfiles.CAMPRJSPE_OUTPUT],
                         (475, "7ff05ee22562dc721d5701aa2a046ef530c1dc6b03ae96de7e541313ea5f8cc5"))


class TheTableSperrScanReads(unittest.TestCase):
    """release/sperr-scan.py reads the name GERAETE off h713-extract (rule 5 of doku/116 section 2).

    It loads the script itself with a SourceFileLoader and does `getattr(m, "GERAETE", {})`, so the
    test loads it the same way -- an adapter would prove nothing about what that scan sees.
    """

    def load_the_way_sperr_scan_does(self):
        loader = importlib.machinery.SourceFileLoader("h713_extract_for_scan", support.EXTRACT_PY)
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        return module

    def test_the_extractor_still_exports_the_table(self):
        table = getattr(self.load_the_way_sperr_scan_does(), "GERAETE", None)
        self.assertIsNotNone(table, "h713-extract exports no GERAETE -- sperr-scan reads 0 hashes")
        self.assertEqual(sorted(table), sorted(legacy_devices()))

    def test_the_two_new_digests_are_in_it(self):
        digests = set()
        for device in getattr(self.load_the_way_sperr_scan_does(), "GERAETE", {}).values():
            for value in device.get("referenz", {}).values():
                if isinstance(value, tuple) and len(value) == 2:
                    digests.add(value[1])
        self.assertIn("b024f6e060580d2a7a4ede4b83e5669c184458437342050a1ba7f33dfd03db99", digests)
        self.assertIn("7ff05ee22562dc721d5701aa2a046ef530c1dc6b03ae96de7e541313ea5f8cc5", digests)


class TheDocumentation(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(DOCS):
            self.skipTest("docs/tools/h713-extract.md not next to this checkout (%s)" % DOCS)
        with open(DOCS, "rb") as handle:
            self.text = handle.read().decode("utf-8")

    def test_it_names_both_new_files_and_what_they_are_for(self):
        self.assertIn("panel_config.ini", self.text)
        self.assertIn("camprjspe.ini", self.text)



if __name__ == "__main__":
    unittest.main()
