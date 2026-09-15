"""The boot logo travels with the image (doku/40, last section; fork commit 80eae99).

`h713_disp init <id> logo` reads `bootlogo.bmp` from the ROOT of the partition the display
artefacts come from -- `/boot/bootlogo.bmp` on an installed device. So the extractor takes it out
of the bootloader FAT, the image carries a placeholder for it, and the installer fills that
placeholder -- but treats a missing or oversized logo as a warning, never as a failed install.

Nothing here freezes a new vendor hash: the one digest below already stands in
`installer/h713/profiles/hy310.py` and in `h713_vendor_bootlogos[]` in U-Boot, and the test asserts
the two agree instead of carrying a second copy of the truth.
"""

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713 import extract, log                                        # noqa: E402
from h713.install import OPTIONAL_FILES, vendor_sources              # noqa: E402
from h713.layout import PLACEHOLDERS                                 # noqa: E402
from h713.mkimage import readme_text, tree_boot                      # noqa: E402
from h713.profiles import PROFILES                                   # noqa: E402
from h713.vendorfiles import BOOT_ROOT_FILES, MIPS_NOT_OURS, check_bootlogo   # noqa: E402

NAME = "boot/bootlogo.bmp"
LOGO_SIZE = 6220854                    # 1920 x 1080 x 3 + 54
LOGO_SHA = "9684ef71483eb19901adf25e55ad617eb2b41d7065d9e257e1081c5c26095033"
HY310_PANEL = {"width": 1920, "height": 1080}


def bmp(width=1920, height=1080, bpp=24, planes=1, compression=0):
    """The 54 bytes U-Boot reads before it touches a pixel -- no pixel array behind them."""
    return (struct.pack("<2sIHHI", b"BM", 54, 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, width, height, planes, bpp, compression,
                          0, 0, 0, 0, 0))


class CheckBootlogo(unittest.TestCase):
    """check_bootlogo() reports, it never raises -- the file is copied either way."""

    def test_the_stock_header_is_sound(self):
        self.assertEqual(check_bootlogo(bmp(), HY310_PANEL), [])

    def test_wrong_bit_depth(self):
        found = check_bootlogo(bmp(bpp=32), HY310_PANEL)
        self.assertEqual(len(found), 1, found)
        self.assertIn("32 bpp instead of 24", found[0])

    def test_wrong_size_against_the_panel_of_this_board(self):
        found = check_bootlogo(bmp(width=1280, height=720), HY310_PANEL)
        self.assertEqual(len(found), 1, found)
        self.assertIn("1280x720", found[0])
        self.assertIn("1920x1080", found[0])

    def test_negative_height_is_named_but_the_geometry_still_counts(self):
        found = check_bootlogo(bmp(height=-1080), HY310_PANEL)
        self.assertEqual(len(found), 1, found)               # the size itself is right
        self.assertIn("top-down", found[0])

    def test_without_a_profile_only_a_plausible_size_is_asked_for(self):
        self.assertEqual(check_bootlogo(bmp(width=1280, height=720)), [])
        self.assertEqual(check_bootlogo(bmp(width=1280, height=720), None), [])
        found = check_bootlogo(bmp(width=8, height=8))
        self.assertEqual(len(found), 1, found)
        self.assertIn("320..4096", found[0])

    def test_a_profile_without_a_panel_does_not_pretend_to_know_one(self):
        self.assertIsNone(PROFILES["hy300_pro"]["panel"]["width"])
        self.assertEqual(check_bootlogo(bmp(width=1280, height=720),
                                        PROFILES["hy300_pro"]["panel"]), [])

    def test_compression_and_planes(self):
        self.assertIn("compression 1", check_bootlogo(bmp(compression=1), HY310_PANEL)[0])
        self.assertIn("2 plane(s)", check_bootlogo(bmp(planes=2), HY310_PANEL)[0])

    def test_something_that_is_no_bmp(self):
        for blob in (b"", b"MZ" + b"\0" * 100, b"BM"):
            found = check_bootlogo(blob, HY310_PANEL)
            self.assertEqual(len(found), 1, found)
            self.assertIn("no BMP header", found[0])


class TheTableAndTheTree(unittest.TestCase):
    """The placeholder sits at the ROOT of hy310-boot, and the tree builder puts it there."""

    def test_the_placeholder_is_in_the_table(self):
        rows = [row for row in PLACEHOLDERS if row[0] == NAME]
        self.assertEqual(rows, [(NAME, LOGO_SIZE, "hy310-boot", "/bootlogo.bmp")])

    def test_the_profile_and_this_test_agree_on_the_digest(self):
        self.assertEqual(PROFILES["hy310"]["reference"][NAME], (LOGO_SIZE, LOGO_SHA))

    def test_the_logo_left_the_not_ours_list_and_the_rest_stayed(self):
        self.assertEqual(BOOT_ROOT_FILES, ("bootlogo.bmp",))
        self.assertNotIn("bootlogo.bmp", MIPS_NOT_OURS)
        self.assertEqual(MIPS_NOT_OURS, ("fastbootlogo.bmp", "font24.sft", "font32.sft",
                                         "magic.bin", "bat", "wavefile"))

    def test_tree_boot_writes_it_at_the_partition_root(self):
        directory = os.path.join(support.workdir(self), "boot")
        n = tree_boot(directory, log=support.Recorder())
        self.assertEqual(n, len([r for r in PLACEHOLDERS if r[2] == "hy310-boot"]))
        path = os.path.join(directory, "bootlogo.bmp")
        self.assertEqual(os.path.getsize(path), LOGO_SIZE)
        self.assertTrue(os.path.isdir(os.path.join(directory, "mips")))

    def test_the_readme_names_it(self):
        text = readme_text({"abbild": "x", "erzeugt": "t", "werkzeug": "w",
                            "teile": [], "loch": {"lba": 12288, "sektoren": 2048},
                            "platzhalter": dict((r[0], [0, r[1]]) for r in PLACEHOLDERS)})
        self.assertIn("The image holds %d placeholders" % len(PLACEHOLDERS), text)
        self.assertIn("  * the boot logo (bootlogo.bmp) -- without it the panel stays black "
                      "until Linux", text)
        self.assertIn("  * 19 display artefacts (mips/)", text)


class OptionalForTheInstaller(unittest.TestCase):
    """vendor_sources(): the logo is optional PER FILE -- missing or too big is a warning, and
    the entry leaves the table so the placeholder keeps its fill pattern."""

    def setUp(self):
        self.directory = support.workdir(self)
        os.makedirs(os.path.join(self.directory, "boot"))
        with open(os.path.join(self.directory, "keep.bin"), "wb") as fh:
            fh.write(b"\xa5" * 8)
        self.log = support.Recorder()

    def _table(self):
        return {"keep.bin": (0, 8), NAME: (16, 64)}

    def _logo(self, size):
        with open(os.path.join(self.directory, "boot", "bootlogo.bmp"), "wb") as fh:
            fh.write(b"BM" + b"\0" * (size - 2))

    def test_the_logo_is_declared_optional(self):
        self.assertEqual(OPTIONAL_FILES, (NAME,))

    def test_a_logo_that_is_there_is_simply_used(self):
        self._logo(64)
        table = self._table()
        sources = vendor_sources(self.directory, table, self.log)
        self.assertEqual(sorted(sources), ["boot/bootlogo.bmp", "keep.bin"])
        self.assertIn(NAME, table)
        self.assertEqual(self.log.lines, [])

    def test_a_missing_logo_is_a_warning_and_nothing_else(self):
        table = self._table()
        sources = vendor_sources(self.directory, table, self.log)
        self.assertEqual(sorted(sources), ["keep.bin"])
        self.assertNotIn(NAME, table)
        self.assertEqual(len(self.log.lines), 1, self.log.text)
        self.assertIn("no boot logo", self.log.text)
        self.assertIn("The placeholder stays a pattern and U-Boot boots without a logo",
                      self.log.text)

    def test_a_logo_too_big_for_the_placeholder_is_skipped(self):
        self._logo(65)
        table = self._table()
        sources = vendor_sources(self.directory, table, self.log)
        self.assertEqual(sorted(sources), ["keep.bin"])
        self.assertNotIn(NAME, table)
        self.assertEqual(len(self.log.lines), 1, self.log.text)
        self.assertIn("65 bytes, the placeholder holds 64", self.log.text)

    def test_everything_else_missing_still_aborts(self):
        self._logo(64)
        os.remove(os.path.join(self.directory, "keep.bin"))
        with self.assertRaises(RuntimeError) as caught:
            vendor_sources(self.directory, self._table(), self.log)
        self.assertIn("keep.bin", str(caught.exception))


class ASourceWithoutALogo(unittest.TestCase):
    """The vendor copy inside super carries no bootlogo.bmp: one warning, one `not_extracted`
    line, and not one artefact more (the ADT-3 images take exactly this path)."""

    def _run(self):
        out = support.workdir(self)
        args = argparse.Namespace(out=out, tmp=os.path.join(out, "tmp"), use_debugfs=False)
        run = extract.Run(args, log.Log(True))
        read_set = {"origin": "vendor:/etc/display/mips/", "fs": "ext4 (synthetic)",
                    "type": "ext4", "kind": "vendor", "files": {"display.bin": b"not a revision"},
                    "root_files": {}, "short_names": {}, "problems": [], "leftover": [],
                    "others": []}
        run.mips_read_sets = lambda: ([read_set], [{"source": "vendor:/etc/display/mips",
                                                    "origin": read_set["origin"], "files": 1,
                                                    "role": None}])
        run.declared_project_id = lambda: {"id": None, "source": None, "note": "synthetic input"}
        run.extract_mips()
        return run

    def test_only_a_warning_and_a_not_extracted_line(self):
        run = self._run()
        self.assertEqual([p for p in run.not_extracted if "bootlogo" in p],
                         [NAME + " (not at the root of vendor:/etc/display/mips/)"])
        self.assertEqual([w for w in run.log.warnings if "boot logo" in w],
                         ["no boot logo in the source (bootlogo.bmp is not at the root of "
                          "vendor:/etc/display/mips/)"])
        self.assertEqual([a["path"] for a in run.artefacts], ["boot/mips/display.bin"])


class OutOfTheStockFat(unittest.TestCase):
    """The real tool over the real stock bootloader FAT (H713_FIXTURES_LOCAL): the logo comes out
    as boot/bootlogo.bmp, matches the hy310 reference, and is no longer reported as left behind."""

    def setUp(self):
        support.need([fakedisk.STOCK_BOOTLOADER, support.EXTRACT_PY])
        self.out = os.path.join(support.workdir(self), "out")
        proc = subprocess.Popen(
            [sys.executable, support.EXTRACT_PY, "--part",
             "bootloader_b=" + fakedisk.STOCK_BOOTLOADER, "-o", self.out, "-q"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.text = proc.communicate()[0].decode("utf-8", "replace")
        with open(os.path.join(self.out, "MANIFEST.json"), encoding="utf-8") as fh:
            self.manifest = json.load(fh)

    def _row(self):
        rows = [a for a in self.manifest["files"] if a["path"] == NAME]
        self.assertEqual(len(rows), 1, self.text)
        return rows[0]

    def test_the_file_is_written_and_is_the_vendor_logo(self):
        with open(os.path.join(self.out, "boot", "bootlogo.bmp"), "rb") as fh:
            data = fh.read()
        self.assertEqual(len(data), LOGO_SIZE)
        self.assertEqual(hashlib.sha256(data).hexdigest(), LOGO_SHA)
        self.assertEqual(check_bootlogo(data, PROFILES["hy310"]["panel"]), [])

    def test_the_manifest_row_says_where_it_came_from_and_that_it_matched(self):
        row = self._row()
        self.assertEqual((row["size"], row["sha256"]), (LOGO_SIZE, LOGO_SHA))
        self.assertIs(row["reference_ok"], True)
        self.assertEqual(row["reference_device"], "hy310")
        self.assertIs(row["error"], False)
        self.assertIn("/bootlogo.bmp", row["origin"])
        self.assertTrue(any("BMP header sound" in c for c in row["checks"]), row["checks"])

    def test_it_is_no_longer_one_of_the_files_we_leave_behind(self):
        rest = self.manifest["mips"]["not_extracted_same_partition"]
        self.assertNotIn("bootlogo.bmp (%d B)" % LOGO_SIZE, rest)
        self.assertIn("fastbootlogo.bmp (189966 B)", rest)          # the rest is untouched
        self.assertEqual([n for n in self.manifest["not_extracted"] if "bootlogo" in n], [])

    def test_the_report_carries_the_same_lines(self):
        with open(os.path.join(self.out, "REPORT.txt"), encoding="utf-8") as fh:
            report = fh.read()
        self.assertIn("  %s: %d B sha256 %s" % (NAME, LOGO_SIZE, LOGO_SHA), report)
        self.assertIn("BMP header sound: 24 bpp, uncompressed, one plane, 1920x1080", report)


if __name__ == "__main__":
    unittest.main()
