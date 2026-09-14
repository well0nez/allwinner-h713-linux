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
# device, artefakte, digest of the sorted (path, size, sha256) list).  Exit 1 on
# the two ADT-3 images is documented behaviour, not a failure: no device profile
# matches them, so the extractor reports a best effort.
MANIFESTS = {
    "hy310": (0, "hy310", 43,
              "ced1b8aeb61bb265d488d7ff09d39beb149ef4698f17cbf96a45d5e73bdce162"),
    "hy300-t08": (1, None, 20,
                  "f347466ecb7721bc8f982bddacdb6cd096a845202facff54c872db7dfa3c35e1"),
    "hy350": (1, None, 21,
              "7bfa4452385130b716684666608a52a9f7638bfddb019bcc89ac8453d1acd811"),
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
        rows = sorted((a["pfad"], a["groesse"], a["sha256"])
                      for a in manifest["artefakte"])
        names = [r[0] for r in rows]
        self.assertEqual(len(rows), want_count, names)
        self.assertEqual(support.digest(rows), want_digest, names)
        # nothing out of the locked regions may ever appear in an extractor run
        self.assertEqual([n for n in names if "secure" in n.lower()], [])

    def test_all_three_images(self):
        for board in sorted(MANIFESTS):
            self._check(board)
