# SPDX-License-Identifier: GPL-2.0
"""Rule 9 of release/sperr-scan.py: a source file under mainline/ without an SPDX line is a hard finding.

Cause (13.10.2026, doku/210): cstenger's tree came into mainline/ without a licence statement and 70 files
had to go again. A guard that only ever says "clean" proves nothing, so the positive control is here:
a file without the line must fail the scan, the same file with it must pass, and a patch or a file in a
free place must not be asked for one.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(HERE, "..", "..", "release", "sperr-scan.py")


def scan(files):
    """Run the scan on a throw-away tree made of {relative path: text}; return (exit code, output)."""
    with tempfile.TemporaryDirectory() as root:
        for rel, text in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        r = subprocess.run([sys.executable, SCAN, root], capture_output=True, text=True)
        return r.returncode, r.stdout


@unittest.skipUnless(os.path.isfile(SCAN), "release/sperr-scan.py is not part of this export")
class TestSpdxRule(unittest.TestCase):
    def test_source_without_spdx_is_a_finding(self):
        rc, out = scan({"mainline/tools/probe.c": "int main(void) { return 0; }\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("mainline/tools/probe.c", out)

    def test_source_with_spdx_passes(self):
        rc, out = scan({"mainline/tools/probe.c": "// SPDX-License-Identifier: GPL-2.0\nint main(void) { return 0; }\n"})
        self.assertEqual(rc, 0, out)

    def test_patches_and_free_places_are_not_asked(self):
        rc, out = scan({
            "mainline/patches/kernel/0001-x.patch": "--- a/x.c\n+++ b/x.c\n",
            "mainline/external/u-boot/x.c": "/* Copyright (C) vendor */\n",
            "mainline/build/build.sh": "#!/bin/sh\n",
            "rootfs/x.sh": "#!/bin/sh\n",
        })
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
