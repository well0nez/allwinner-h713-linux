"""h713-extract on the three vendor images: the MANIFEST.json file list, frozen.
Slow (6 GB of reading), so gated twice: images present AND H713_SLOW_TESTS=1."""

import json
import os
import subprocess
import sys
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from h713-extract 0.4: board -> (exit code, recognised
# device, files, digest of the sorted (path, size, sha256) list).  Exit 1 on
# the two ADT-3 images is documented behaviour, not a failure: no device profile
# matches them, so the extractor reports a best effort.
#
# doku/121 stage 3 ("stage 3 texts") renamed the MANIFEST keys this test reads --
# manifest["artefakte"] -> manifest["files"], a["pfad"/"groesse"] -> a["path"/"size"]
# (the full table is in TEXTS-extract.md).  Not one value changed with it, so all
# three digests below stayed exactly as they were frozen; nothing was re-frozen here.
#
# Re-frozen on 2026-09-14 for stage 2 C-D (second MIPS source): the ADT-3 images have no mips/ in
# their bootloader FAT, so the extractor found nothing there; now it also reads the vendor copy in
# vendor:/etc/display/mips/ and both images yield the 19 files under boot/mips/.  Only those 19
# artefacts are new -- every other artefact is byte for byte the one of stage 1, and the HY310 row
# is untouched (its FAT copy still wins, the vendor copy is only cross-checked).
#   hy300-t08: was (1, None, 20, "f347466ecb7721bc8f982bddacdb6cd096a845202facff54c872db7dfa3c35e1")
#   hy350:     was (1, None, 21, "7bfa4452385130b716684666608a52a9f7638bfddb019bcc89ac8453d1acd811")
#
# Re-frozen on 2026-09-15 by G1, the hy310 row only: the extractor now also takes bootlogo.bmp out
# of the FAT ROOT of the bootloader partition (44 instead of 43 artefacts), because `h713_disp init
# <id> logo` reads it (doku/40, last section). Exit code and device unchanged, and every other
# artefact is byte for byte the one before.
#   hy310: was (0, "hy310", 43, "ced1b8aeb61bb265d488d7ff09d39beb149ef4698f17cbf96a45d5e73bdce162")
# The two ADT-3 rows did NOT move: their bootloader FAT carries no mips/, so the extractor reads
# their display artefacts out of vendor:/etc/display/mips/, and that copy has no logo. Their FAT
# root does hold one (2764854 B on the T08, 6220854 B on the HY350) -- see REPORT.txt of G1.
MANIFESTS = {
    "hy310": (0, "hy310", 44,
              "0d1a388784c31035805d9d0f6f2f20a85e5efdf00cec560a993384494623dcb7"),
    "hy300-t08": (1, None, 39,
                  "3c84815992b349d09f12b562e0e2ef7f1d74dbf351f2125d8866f577d62b9b9e"),
    "hy350": (1, None, 40,
              "2cfcca38d4b1eb09a81e932f997e2db1290dc7fe5a672e023f55f51bb68b3f7f"),
}


class ExtractManifest(unittest.TestCase):
    def _check(self, board):
        support.slow_or_skip()
        support.need([fakedisk.IMAGES[board], support.EXTRACT_PY])
        want_code, want_device, want_count, want_digest = MANIFESTS[board]
        out = os.path.join(support.workdir(self), "out")
        proc = subprocess.Popen(
            [sys.executable, support.EXTRACT_PY, fakedisk.IMAGES[board], "-o", out, "-q"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = proc.communicate()[0].decode("utf-8", "replace")
        with open(os.path.join(out, "MANIFEST.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual((proc.returncode, manifest["exit_code"], manifest["device"]),
                         (want_code, want_code, want_device), text)
        rows = sorted((a["path"], a["size"], a["sha256"])
                      for a in manifest["files"])
        names = [r[0] for r in rows]
        self.assertEqual(len(rows), want_count, names)
        self.assertEqual(support.digest(rows), want_digest, names)
        # nothing out of the locked regions may ever appear in an extractor run
        self.assertEqual([n for n in names if "secure" in n.lower()], [])

    def test_all_three_images(self):
        for board in sorted(MANIFESTS):
            self._check(board)
