# SPDX-License-Identifier: GPL-2.0
"""Rule 10 of release/sperr-scan.py: a MAC address in a text file is a hard finding.

Cause (20.10.2026, TODO 2.127): the address of the owner's remote stood in three journal pages, client and
Ethernet addresses in patch texts and a boot log. The positive control is here: a real-looking address must
fail the scan and the output must not repeat it; the masked form, the test dummies and longer hex runs
(an EDID header, a hexdump) must pass.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(HERE, "..", "..", "release", "sperr-scan.py")
# an address of no device, put together here so that this file does not trip the rule itself
ADDR = ":".join(["3c", "4f", "52", "a1", "07", "9e"])


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
class TestMacRule(unittest.TestCase):
    def test_an_address_is_a_finding_and_not_repeated(self):
        rc, out = scan({"doku/1-x.md": "line one\npaired with %s today\n" % ADDR})
        self.assertEqual(rc, 1, out)
        self.assertIn("doku/1-x.md:2", out)
        self.assertNotIn(ADDR, out)

    def test_upper_case_in_a_patch_text_is_a_finding(self):
        rc, out = scan({"mainline/patches/x/0001-y.patch": "Subject: x\n\n    wlan0: Add sta 2 (%s)\n" % ADDR.upper()})
        self.assertEqual(rc, 1, out)

    def test_a_dummy_prefix_does_not_let_a_real_address_through(self):
        # 00:11:22 is an assigned OUI block, so only the whole dummy addresses pass (Mythos 21.10.2026)
        rc, out = scan({"doku/1-x.md": "seen %s\n" % ":".join(["00", "11", "22", "ab", "cd", "ef"])})
        self.assertEqual(rc, 1, out)

    def test_masked_dummies_and_longer_runs_pass(self):
        rc, out = scan({
            "doku/1-x.md": "remote xx:xx:xx:xx:xx:xx\n",
            "userspace/t/tests/test_x.py": "A = 'AA:BB:CC:DD:EE:01'\nB = '00:11:22:33:44:55'\nC = '11:22:33:44:55:66'\n",
            "doku/2-edid.md": "header 00:ff:ff:ff:ff:ff:ff:00 and ff:ff:ff:ff:ff:ff\n",
            "doku/3-time.md": "between 10:20:14-10:21:41\n",
        })
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
