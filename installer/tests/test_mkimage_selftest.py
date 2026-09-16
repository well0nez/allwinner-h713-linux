"""mkimage-selftest.py as a subprocess -- the one end-to-end check the tools
already had.  It needs a built image (out/*.tabelle.json plus its three parts); since
layout v4 it needs no vendor directory any more, because there is nothing to fill: the
copy through a mount is step 4 of the self-test and needs root, which this test does not
have.  It writes the dummy disk into --tmp and removes it again."""

import glob
import json
import os
import re
import subprocess
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.mkimage import TABLE_FORMAT                            # noqa: E402

# re-frozen 2026-09-16 for layout v4 (plan/briefs/P-layout-v4.md): the self-test does
# not fill placeholders any more.  Was 18 green lines with the image h713-hy310-v0.12 and
# the vendor directory out-hy310-20260912; now 25 without a vendor directory -- step 2
# (the table against h713.layout) and step 3 (the target directories, one line each)
# replaced the two fill steps.  Exit code 0 and "no FAIL" are unchanged.
OK_LINES = 25
VENDOR_DIRS = (support.VENDOR_OUT + "-20260912", support.VENDOR_OUT)

SELFTEST = os.path.join(support.TOOLS, "mkimage-selftest.py")
MARKERS = ("ALL GREEN", "Secure Storage unchanged", "eGON.BT0 sits at LBA 16",
           "equal to layout.FILES", "none of the 44 files of h713.layout is in the image")


def _pick():
    """The newest usable v4 table, by mtime -- not by name.

    The selftest compares the kernel FIT inside the image against whatever sits
    in r0-fel/tmp/boot-baum right now, so an older build fails a check that says
    nothing about that build.  A v3 table (v0.7-beta and older) is not for this
    tool: it carries placeholders, not a file list.
    """
    tables = glob.glob(os.path.join(support.BUILD_OUT, "*.tabelle.json"))
    for table in sorted(tables, key=os.path.getmtime, reverse=True):
        with open(table, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != TABLE_FORMAT:
            continue
        if fakedisk.missing([os.path.join(support.BUILD_OUT, t["datei"])
                             for t in data["teile"]]):
            continue
        return table
    return None


class MkimageSelfTest(unittest.TestCase):
    def test_the_whole_way_once_through(self):
        support.need([SELFTEST])
        table = _pick()
        if not table:
            raise unittest.SkipTest(
                "no built layout v4 image in %s (mkimage-inputs.sh + h713-mkimage build one)"
                % support.BUILD_OUT)
        tmp = support.workdir(self)
        vendor = next((v for v in VENDOR_DIRS if os.path.isdir(v)), VENDOR_DIRS[-1])
        proc = subprocess.Popen(
            [sys.executable, SELFTEST, table, "--vendor", vendor,
             "--tmp", os.path.join(tmp, "work")],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=tmp)
        text = proc.communicate()[0].decode("utf-8", "replace")
        self.assertEqual(proc.returncode, 0, text)
        self.assertNotIn("FAIL", text)
        for marker in MARKERS:
            self.assertIn(marker, text)
        found = len(re.findall(r"^  OK   ", text, re.M))
        if os.environ.get("H713_ROOT_TESTS") == "1":
            self.assertGreaterEqual(found, OK_LINES, text)     # step 4 adds lines with root
        else:
            self.assertEqual(found, OK_LINES, text)
