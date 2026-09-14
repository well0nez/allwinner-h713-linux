"""mkimage-selftest.py as a subprocess -- the one end-to-end check the tools
already had.  It needs a built image (out/*.tabelle.json plus its three parts) and
a vendor directory holding every placeholder the table names; without those it
skips and says which.  It writes ~1.3 GB into --tmp and removes it again.  Its
default --vendor (r2-extract/out-hy310, 10.09.) is stale for tables built after
12.09. -- the 13 aic8800 WLAN files are missing there."""

import glob
import json
import os
import re
import subprocess
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from mkimage-selbsttest.py (image h713-hy310-v0.12, vendor
# out-hy310-20260912): 18 green checks, no red one, exit 0.
OK_LINES = 18
VENDOR_DIRS = (support.VENDOR_OUT + "-20260912", support.VENDOR_OUT)

# doku/121 stage 3 ("stage 3 texts"): the self-test was renamed
# mkimage-selbsttest.py -> mkimage-selftest.py and its output is English.
#   was SELFTEST = support.SELFTEST_PY  (installer/mkimage-selbsttest.py)
#   was the markers ("ALLES GRUEN", "Secure Storage unveraendert",
#                    "eGON.BT0 steht bei LBA 16") and assertNotIn("FEHL")
# The count of green lines (18) and the exit code are unchanged -- only the
# wording moved, no check was added or dropped.
SELFTEST = os.path.join(support.TOOLS, "mkimage-selftest.py")
MARKERS = ("ALL GREEN", "Secure Storage unchanged", "eGON.BT0 sits at LBA 16")


def _pick():
    """The newest usable table, by mtime -- not by name.

    The selftest compares the kernel FIT inside the image against whatever sits
    in r0-fel/tmp/boot-baum right now, so an older build fails a check that says
    nothing about that build.
    """
    tables = glob.glob(os.path.join(support.BUILD_OUT, "*.tabelle.json"))
    for table in sorted(tables, key=os.path.getmtime, reverse=True):
        with open(table, encoding="utf-8") as fh:
            data = json.load(fh)
        if fakedisk.missing([os.path.join(support.BUILD_OUT, t["datei"])
                             for t in data["teile"]]):
            continue
        for vendor in VENDOR_DIRS:
            if not fakedisk.missing([os.path.join(vendor, n)
                                     for n in data["platzhalter"]]):
                return table, vendor
    return None, None


class MkimageSelfTest(unittest.TestCase):
    def test_the_whole_way_once_through(self):
        support.need([SELFTEST])
        table, vendor = _pick()
        if not table:
            raise unittest.SkipTest(
                "no built image in %s with a complete vendor directory "
                "(mkimage-inputs.sh + h713-mkimage build one)" % support.BUILD_OUT)
        tmp = support.workdir(self)
        proc = subprocess.Popen(
            [sys.executable, SELFTEST, table, "--vendor", vendor,
             "--tmp", os.path.join(tmp, "work")],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=tmp)
        text = proc.communicate()[0].decode("utf-8", "replace")
        self.assertEqual(proc.returncode, 0, text)
        self.assertEqual(len(re.findall(r"^  OK   ", text, re.M)), OK_LINES, text)
        self.assertNotIn("FAIL", text)
        for marker in MARKERS:
            self.assertIn(marker, text)
