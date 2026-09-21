# SPDX-License-Identifier: GPL-2.0
"""R1 item 1: the beta warning of README, in the installer's own output.

It is said on a stock device, before the dump and before anything is written -- once, three
lines, `--no-write` included. On our own layout it is not said (there is no Android left to
lose, N2), and on a test image the sentence test_image_allowed() prints about the owner's own
full dump stays instead, so the two never arrive together.

Everything here runs on fake disks the repository's own fixtures build, so it runs in the
default mode of run.sh as well.
"""

import os
import subprocess
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.install import BETA_WARNING, beta_warning                 # noqa: E402

TOOL = os.path.join(support.TOOLS, "h713-install")
OUR_PARTS = [("hy310-keys", 12288, 2048), ("hy310-env", 14336, 2048),
             ("hy310-boot", 16384, 8192)]


class WhenItIsSaid(unittest.TestCase):
    def test_a_stock_device_gets_all_three_lines(self):
        log = support.Recorder()
        self.assertTrue(beta_warning(True, False, log))
        self.assertEqual(len(log.lines), 3, log.text)
        for line in BETA_WARNING:
            self.assertIn(line, log.text)
        self.assertTrue(log.lines[0].startswith("WARN "), log.text)

    def test_our_own_layout_gets_nothing(self):
        log = support.Recorder()
        self.assertFalse(beta_warning(False, False, log))
        self.assertEqual(log.lines, [])

    def test_a_test_image_keeps_its_own_sentence_instead(self):
        log = support.Recorder()
        self.assertFalse(beta_warning(True, True, log))
        self.assertEqual(log.lines, [])


class ThroughTheTool(unittest.TestCase):
    """`install --no-write` end to end: the identification decides, and the warning stands
    in front of step 3 -- so it is on screen before the dump and before any write."""

    def _run(self, disk):
        tmp = os.path.dirname(disk)
        image = os.path.join(tmp, "one-part.img")
        with open(image, "wb") as fh:
            fh.write(b"\xa5" * (1 << 16))
        proc = subprocess.run(
            [sys.executable, TOOL, "install", image, "--device", disk, "--no-write",
             "--small", "--dump", os.path.join(tmp, "backup")],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=tmp,
            env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        return out

    def test_a_stock_device_is_warned_once_and_before_the_dump(self):
        support.need(fakedisk.NEEDS_STOCK_GPT + (TOOL,))
        tmp = support.workdir(self)
        out = self._run(fakedisk.make_stock_gpt_disk(os.path.join(tmp, "emmc.img")))
        self.assertEqual(out.count(BETA_WARNING[0]), 1, out)
        for line in BETA_WARNING[1:]:
            self.assertIn(line, out)
        self.assertLess(out.index(BETA_WARNING[0]), out.index("Take the dump"), out)
        self.assertIn("WOULD: write", out)

    def test_our_own_layout_is_not_warned(self):
        support.need([TOOL])
        tmp = support.workdir(self)
        disk = fakedisk.make_our_layout_disk(os.path.join(tmp, "emmc.img"), OUR_PARTS)
        out = self._run(disk)
        for line in BETA_WARNING:
            self.assertNotIn(line, out)
        self.assertIn("our layout (v3, doku/109) on this device", out)
        self.assertIn("WOULD: write", out)


if __name__ == "__main__":
    unittest.main()
