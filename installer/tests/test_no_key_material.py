# SPDX-License-Identifier: GPL-2.0
"""The guard that keeps HDCP key material out of the repository.

Two things are tested: that the tracked tree is clean right now, and that the guard
would actually notice - a check that only ever says "clean" is worthless.

The positive controls are synthetic. The real key set cannot be used here for the
very reason the guard exists, so the fingerprint path is exercised by putting the
hash of a made-up blob into the table, and the item path by building a slot header
by hand.
"""

import hashlib
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load_guard():
    spec = importlib.util.spec_from_file_location(
        "no_key_material", os.path.join(HERE, "no_key_material.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNoKeyMaterial(unittest.TestCase):
    def setUp(self):
        self.guard = load_guard()

    def test_tracked_tree_is_clean(self):
        """Nothing tracked in this repository carries key material."""
        self.assertEqual(self.guard.main(["no_key_material.py"]), 0)

    def test_submodules_are_not_walked(self):
        """Only regular files of THIS repository, no submodule build output."""
        files = self.guard.tracked_files()
        self.assertTrue(files)
        for path in files:
            self.assertTrue(os.path.isfile(path), path)
            self.assertFalse(os.path.islink(path), path)
            self.assertNotIn("/external/", path)

    def test_fingerprint_is_found(self):
        """A blob whose fingerprint is known is reported, wherever it sits."""
        blob = bytes((i * 31 + 7) % 251 for i in range(288))
        self.guard.KNOWN = dict(self.guard.KNOWN)
        self.guard.KNOWN[hashlib.sha256(blob).hexdigest()] = ("test blob", 288)
        for offset in (0, 16, 4096):
            found = self.guard.scan(bytes(offset) + blob + bytes(64))
            self.assertIsNotNone(found, "not found at offset %d" % offset)
            self.assertEqual(found[1], offset)

    def test_unknown_blob_is_not_reported(self):
        """High-entropy data that is not a known key set stays unreported."""
        self.assertIsNone(self.guard.scan(os.urandom(4096)))

    def test_secure_storage_item_is_found_at_any_offset(self):
        """A committed region dump is caught by the item search, not the grid."""
        slot = bytearray(4096)
        slot[0:4] = self.guard.MAGIC
        slot[8:8 + len(b"hdcpkey")] = b"hdcpkey"
        # 0x2b is deliberately not a multiple of the coarse grid
        blob = bytes(0x2b) + bytes(slot)
        found = self.guard.scan(blob)
        self.assertIsNotNone(found)
        self.assertIn("hdcpkey", found[0])

    def test_a_file_on_disk_is_reported(self):
        """End to end: a file with a known blob makes the run fail."""
        blob = bytes((i * 17 + 3) % 253 for i in range(288))
        self.guard.KNOWN = dict(self.guard.KNOWN)
        self.guard.KNOWN[hashlib.sha256(blob).hexdigest()] = ("test blob", 288)
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            handle.write(blob)
            name = handle.name
        try:
            self.assertEqual(self.guard.main(["no_key_material.py", name]), 1)
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main()
