"""Stage 2 C-D: the second MIPS source, the firmware revisions, the HDCP wait site.

  * h713.hdcpsite -- the search rule, carried over from package A5 (work/A5/tests/test_hdcp_site.py)
    with the module renamed; fixtures from H713_FIXTURES_LOCAL/mips/.
  * the revision table -- what h713.vendorfiles.firmware_revision_of() makes of a known, an unknown
    and a synthetic display.bin, and what the report prints for the unknown one.
  * the extractor over the three vendor images -- slow, gated like test_extract_manifest.py.
"""

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713 import extract, hdcpsite, log, vendorfiles         # noqa: E402
from h713.vendorfiles import firmware_revision_of            # noqa: E402

FIXTURES_LOCAL = os.environ.get("H713_FIXTURES_LOCAL", "")
HY310_BIN = os.path.join(FIXTURES_LOCAL, "mips", "hy310", "display.bin") if FIXTURES_LOCAL else ""
ADT3_BIN = os.path.join(FIXTURES_LOCAL, "mips", "adt3-2024", "display.bin") if FIXTURES_LOCAL else ""

HY310_SHA = "16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9"
ADT3_SHA = "22a7df113fce3fa182926268de8c7551a107f0c3bc2932f0940bd58b8f424835"


def load(path):
    if not path or not os.path.exists(path):
        raise unittest.SkipTest("fixture missing: %s (set H713_FIXTURES_LOCAL)" % (path or "mips/"))
    with open(path, "rb") as fh:
        return fh.read()


def counted(hits, hi, lo):
    """The hits whose context counts are exactly (hi, lo)."""
    return [h for h in hits if h["count_0684"] == hi and h["count_0093"] == lo]


def synthetic(pattern_offsets, half_offsets, size=0x1000):
    buf = bytearray(size)
    for off in half_offsets:
        struct.pack_into("<H", buf, off, half_offsets[off])
    for off in pattern_offsets:
        struct.pack_into("<I", buf, off, hdcpsite.WAIT_ORIG)
    return bytes(buf)


class HdcpSiteFixtures(unittest.TestCase):
    """A5's golden values, against h713/hdcpsite.py instead of work/A5/hdcp_site.py."""

    def test_hy310_site(self):
        data = load(HY310_BIN)
        self.assertEqual(hashlib.sha256(data).hexdigest(), HY310_SHA)
        hits = hdcpsite.find_hits(data)
        self.assertEqual([h["va"] for h in hits], [0x4B13D0A4, 0x4B161478])
        self.assertEqual(hdcpsite.choose(hits), (0x4B13D0A4, "ok"))
        self.assertEqual((len(counted(hits, 1, 2)), len(counted(hits, 0, 0))), (1, 1))
        self.assertEqual(hdcpsite.search(data)["hdcp_wait_va"], 0x4B13D0A4)

    def test_adt3_site(self):
        data = load(ADT3_BIN)
        self.assertEqual(hashlib.sha256(data).hexdigest(), ADT3_SHA)
        hits = hdcpsite.find_hits(data)
        self.assertEqual([h["va"] for h in hits], [0x4B13D1F0, 0x4B1614E0])
        self.assertEqual(hdcpsite.choose(hits), (0x4B13D1F0, "ok"))
        self.assertEqual((len(counted(hits, 1, 2)), len(counted(hits, 0, 0))), (1, 1))
        self.assertEqual(hdcpsite.describe(hdcpsite.search(data)), "0x4b13d1f0 (file offset 0x3d1f0)")

    def test_file_offset(self):
        """VA minus load base is the file offset U-Boot would patch."""
        self.assertEqual(0x4B13D0A4 - hdcpsite.DEFAULT_BASE, 0x3D0A4)
        self.assertEqual(0x4B13D1F0 - hdcpsite.DEFAULT_BASE, 0x3D1F0)


class HdcpSiteRule(unittest.TestCase):
    """The window and the tie-breaking, without needing a fixture."""

    def test_window_clamped_at_image_start(self):
        data = synthetic([0x10, 0xF00], {0x0: 0x0684, 0x100: 0x0093})
        hits = hdcpsite.find_hits(data)
        self.assertEqual([(h["count_0684"], h["count_0093"]) for h in hits], [(1, 1), (0, 0)])
        self.assertEqual(hdcpsite.choose(hits)[1], "ok")

    def test_no_context_is_none(self):
        found = hdcpsite.search(synthetic([0x10], {}))
        self.assertEqual((found["hdcp_wait_va"], found["status"]), (None, "none"))
        self.assertIn("none:", hdcpsite.describe(found))

    def test_two_with_context_is_ambiguous(self):
        data = synthetic([0x10, 0xF00], {0x0: 0x0684, 0x100: 0x0093, 0xF20: 0x0684, 0xF40: 0x0093})
        found = hdcpsite.search(data)
        self.assertEqual((found["hdcp_wait_va"], found["status"]), (None, "ambiguous"))
        self.assertTrue(hdcpsite.describe(found).startswith("ambiguous: "))

    def test_halves_are_counted_aligned(self):
        """An odd-offset 0x0684 is invisible: the C scan steps by two."""
        hits = hdcpsite.find_hits(synthetic([0x10], {0x101: 0x0684}))
        self.assertEqual(hits[0]["count_0684"], 0)


class Revisions(unittest.TestCase):
    """firmware_revision_of() asks the whole table, not only the U-Boot rows."""

    def test_adt3_is_a_known_revision(self):
        rev = firmware_revision_of(load(ADT3_BIN))
        self.assertEqual((rev["board"], rev["size"], rev["project_id"]), ("ADT-3 2024", 0x131B20, None))
        self.assertEqual(rev["hdcp_wait_va"], 0x4B13D1F0)

    def test_hy310_keeps_its_project_id(self):
        rev = firmware_revision_of(load(HY310_BIN))
        self.assertEqual((rev["board"], rev["project_id"], rev["hdcp_wait_va"]),
                         ("HY310 (QZ713 V3.1)", 0x30, 0x4B13D0A4))

    def test_flipped_byte_is_unknown_but_the_site_is_still_found(self):
        """The synthetic case of the brief: one byte flipped outside the search window."""
        data = bytearray(load(ADT3_BIN))
        data[-1] ^= 0xFF                       # far behind 0x3d1f0 +/- 0x400
        self.assertIsNone(firmware_revision_of(bytes(data)))
        found = hdcpsite.search(bytes(data))
        self.assertEqual((found["hdcp_wait_va"], found["status"]), (0x4B13D1F0, "ok"))


class UnknownRevisionReport(unittest.TestCase):
    """A synthetic display.bin: revision "unknown", site searched, the whole profile row printed.

    The extractor is driven directly (no image): one read set stands in for the vendor copy, so this
    needs the mips fixture directory but none of the 6 GB vendor images."""

    def _files(self):
        directory = os.path.join(FIXTURES_LOCAL, "mips", "adt3-2024") if FIXTURES_LOCAL else ""
        if not directory or not os.path.isdir(directory):
            raise unittest.SkipTest("fixture missing: mips/adt3-2024 (set H713_FIXTURES_LOCAL)")
        files = {}
        for name in sorted(os.listdir(directory)):
            if name in vendorfiles.MIPS_FILES or vendorfiles.MIPS_PROJECTID.match(name):
                with open(os.path.join(directory, name), "rb") as fh:
                    files[name] = fh.read()
        self.assertEqual(len(files), 19, sorted(files))
        blob = bytearray(files["display.bin"])
        blob[-1] ^= 0xFF                       # far outside the 0x3d1f0 +/- 0x400 search window
        files["display.bin"] = bytes(blob)
        return files

    def test_unknown_revision_row(self):
        files = self._files()
        out = support.workdir(self)
        args = argparse.Namespace(out=out, tmp=os.path.join(out, "tmp"), use_debugfs=False)
        run = extract.Run(args, log.Log(True))
        # doku/121 stage 3 ("stage 3 texts"): the read-set keys of h713.extract are English --
        # herkunft/typ/art/dateien/kurznamen/probleme/uebrig/sonst ->
        # origin/type/kind/files/short_names/problems/leftover/others, and
        # declared_project_id() returns id/source/note instead of id/quelle/hinweis.
        read_set = {"origin": "vendor:/etc/display/mips/", "fs": "ext4 (synthetic)", "type": "ext4",
                    "kind": "vendor", "files": files, "short_names": {}, "problems": [],
                    "leftover": [], "others": []}
        run.mips_read_sets = lambda: ([read_set], [{"source": "vendor:/etc/display/mips",
                                                    "origin": read_set["origin"],
                                                    "files": len(files), "role": None}])
        run.declared_project_id = lambda: {"id": None, "source": None, "note": "synthetic input"}
        run.extract_mips()
        run.write_manifest(1)
        revision = run.mips["revision"]
        self.assertEqual(revision["name"], "unknown")
        self.assertEqual(revision["known"], False)
        self.assertEqual(revision["size"], len(files["display.bin"]))
        self.assertNotEqual(revision["sha256"], ADT3_SHA)
        self.assertEqual(revision["hdcp_wait_va"], "0x4b13d1f0")      # the flipped byte is outside the window
        self.assertEqual(revision["project_ids_seen"][:2], ["0x0001", "0x0012"])
        self.assertEqual(len(revision["project_ids_seen"]), 13)
        # stage 3: the report is REPORT.txt (BERICHT.txt is written as a copy for one release)
        with open(os.path.join(out, "REPORT.txt"), encoding="utf-8") as fh:
            report = fh.read()
        with open(os.path.join(out, "BERICHT.txt"), encoding="utf-8") as fh:
            self.assertEqual(report, fh.read())
        for line in ("UNKNOWN, the row a profile would need:", "name:             unknown",
                     "hdcp_wait_va:     0x4b13d1f0", "sha256:           " + revision["sha256"],
                     "size:             %d" % revision["size"]):
            self.assertIn(line, report)
        self.assertIn("project_ids_seen: 0x0001, 0x0012", report)


class AdtImages(unittest.TestCase):
    """ADT-3: 19 files out of vendor:/etc/display/mips/. HY310: the FAT copy wins, vendor cross-checked."""

    def _manifest(self, board):
        support.slow_or_skip()
        support.need([fakedisk.IMAGES[board], support.EXTRACT_PY])
        out = os.path.join(support.workdir(self), "out")
        proc = subprocess.Popen([sys.executable, support.EXTRACT_PY, fakedisk.IMAGES[board], "-o", out, "-q"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = proc.communicate()[0].decode("utf-8", "replace")
        with open(os.path.join(out, "MANIFEST.json"), encoding="utf-8") as fh:
            return json.load(fh), text, out

    def _check_adt3(self, board):
        man, text, out = self._manifest(board)
        mips = man["mips"]
        self.assertEqual(mips["source"], "vendor:/etc/display/mips/", text)
        self.assertEqual([s["source"] for s in mips["sources"]],
                         ["bootloader_b", "bootloader_a", "vendor:/etc/display/mips"], text)
        self.assertEqual([s["role"] for s in mips["sources"]],
                         ["not present", "same image as bootloader_b", "used"], text)
        self.assertEqual(mips["cross_check"], [], text)
        self.assertEqual((mips["revision"]["name"], mips["revision"]["hdcp_wait_va"],
                          mips["revision"]["known"]), ("ADT-3 2024", "0x4b13d1f0", True), text)
        self.assertEqual(mips["revision"]["sha256"], ADT3_SHA, text)
        got = sorted(a["path"] for a in man["files"] if a["path"].startswith("boot/mips/"))
        self.assertEqual(len(got), 19, got)
        self.assertIn("boot/mips/display.bin", got)
        self.assertEqual(len([p for p in got if "ProjectID_0x" in p]), 13, got)
        with open(os.path.join(out, "REPORT.txt"), encoding="utf-8") as fh:
            report = fh.read()
        self.assertIn("hdcp_wait_va:     0x4b13d1f0", report)
        self.assertIn("display.bin revision:", report)

    def test_hy300_t08(self):
        self._check_adt3("hy300-t08")

    def test_hy350(self):
        self._check_adt3("hy350")

    def test_hy310_cross_check_reports_display_cfg(self):
        """The HY310 image: the FAT copy wins, the vendor copy differs in display_cfg.xml only."""
        man, text, _out = self._manifest("hy310")
        mips = man["mips"]
        self.assertTrue(mips["source"].startswith("boot-resource.fex"), text)
        self.assertEqual([s["source"] for s in mips["sources"]],
                         ["bootloader_b", "bootloader_a", "vendor:/etc/display/mips"], text)
        self.assertEqual([s["role"] for s in mips["sources"]],
                         ["used", "same image as bootloader_b", "cross-check"], text)
        self.assertEqual(len(mips["cross_check"]), 1, mips["cross_check"])
        line = mips["cross_check"][0]
        self.assertIn("display_cfg.xml differs", line)
        self.assertIn("4766 B", line)
        self.assertIn("4758 B", line)
        self.assertNotIn("display.bin differs", line)
        self.assertEqual((mips["revision"]["name"], mips["revision"]["hdcp_wait_va"]),
                         ("HY310 (QZ713 V3.1)", "0x4b13d0a4"), text)


if __name__ == "__main__":
    unittest.main()
