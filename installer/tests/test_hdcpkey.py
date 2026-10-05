# SPDX-License-Identifier: GPL-2.0
"""h713.hdcpkey: the secure-storage item reader and the unknown-board survey.

Every fixture here is built by hand. The real key set is deliberately absent from the
repository (installer/tests/no_key_material.py guards that), so these tests check the
STRUCTURE and the verdicts, which is what the code actually decides on. The same
structure is parsed by the boot loader in arch/arm/mach-sunxi/h713_hdcp14.c, and the
cases below mirror the ones its host test covers, so the two cannot drift apart
silently.
"""

import hashlib
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from h713 import hdcpitems as hdcpkey  # noqa: E402

SLOT = hdcpkey.SLOT_BYTES


def slot(name=b"hdcpkey", inner=320, blob=True, magic=hdcpkey.MAGIC,
         outer=None, fill=None, salt=0, terminator=True):
    """One secure-storage slot, built to order."""
    s = bytearray(SLOT)
    struct.pack_into("<I", s, 0, magic)
    s[hdcpkey.NAME_OFF:hdcpkey.NAME_OFF + len(name)] = name
    if not terminator:
        s[hdcpkey.NAME_OFF:hdcpkey.NAME_OFF + hdcpkey.NAME_MAX] = b"a" * hdcpkey.NAME_MAX
    if blob:
        real_outer = hdcpkey.INNER_DATA_OFF + inner if outer is None else outer
        struct.pack_into("<I", s, hdcpkey.OUTER_LEN_OFF, real_outer)
        d = hdcpkey.OUTER_DATA_OFF
        s[d:d + len(name)] = name
        struct.pack_into("<I", s, d + hdcpkey.INNER_LEN_OFF, inner)
        struct.pack_into("<I", s, d + hdcpkey.INNER_LEN_OFF + 4, 0x10000001)
        start = d + hdcpkey.INNER_DATA_OFF
        for i in range(inner):
            s[start + i] = fill if fill is not None else (i * 13 + salt + 5) % 251
    else:
        struct.pack_into("<I", s, hdcpkey.OUTER_LEN_OFF, inner)
        s[hdcpkey.OUTER_DATA_OFF:hdcpkey.OUTER_DATA_OFF + inner] = \
            bytes((i * 7 + 1) % 251 for i in range(inner))
    return bytes(s)


def region(*slots, at=2):
    """A 1 MiB region with the given slots starting at slot index `at`."""
    r = bytearray(hdcpkey.REGION_SECTORS * hdcpkey.SECTOR)
    for n, s in enumerate(slots):
        r[(at + n) * SLOT:(at + n + 1) * SLOT] = s
    return bytes(r)


class TestParseSlot(unittest.TestCase):
    def test_blob_item(self):
        item = hdcpkey.parse_slot(slot())
        self.assertEqual(item["name"], "hdcpkey")
        self.assertEqual((item["outer"], item["inner"]), (396, 320))
        self.assertEqual(item["flags"], 0x10000001)
        self.assertEqual(len(item["payload"]), 320)
        self.assertNotIn("error", item)

    def test_short_item_keeps_its_data_where_it_is(self):
        """snum and the hash items have no inner header."""
        s = slot(name=b"snum", inner=15, blob=False)
        item = hdcpkey.parse_slot(s)
        self.assertEqual(item["name"], "snum")
        self.assertTrue(item["short"])
        self.assertEqual(len(item["payload"]), 15)

    def test_empty_slot(self):
        self.assertIsNone(hdcpkey.parse_slot(bytes(SLOT)))

    def test_wrong_magic(self):
        self.assertIsNone(hdcpkey.parse_slot(slot(magic=0xdeadbeef)))

    def test_name_without_terminator(self):
        item = hdcpkey.parse_slot(slot(terminator=False))
        self.assertIn("error", item)

    def test_outer_length_out_of_range(self):
        for bad in (0, 0xffffff):
            item = hdcpkey.parse_slot(slot(outer=bad))
            self.assertIn("error", item, "outer=%d accepted" % bad)

    def test_inner_does_not_fit_outer(self):
        item = hdcpkey.parse_slot(slot(inner=320, outer=396 + 8))
        self.assertIn("error", item)

    def test_short_slot_is_not_an_item(self):
        self.assertIsNone(hdcpkey.parse_slot(slot()[:100]))


class TestStatus(unittest.TestCase):
    def verdict(self, *slots, **kw):
        return hdcpkey.hdcp14_status(region(*slots, **kw))

    def test_two_matching_copies_are_accepted(self):
        st = self.verdict(slot(), slot())
        self.assertTrue(st["ok"], st["text"])
        self.assertEqual(st["copies"], 2)
        self.assertEqual(st["length"], 320)
        self.assertEqual(len(st["fingerprint"]), 64)

    def test_one_copy_is_refused(self):
        st = self.verdict(slot())
        self.assertFalse(st["ok"])
        self.assertIn("only one copy", st["text"])

    def test_differing_copies_are_refused(self):
        st = self.verdict(slot(), slot(salt=1))
        self.assertFalse(st["ok"])
        self.assertIn("differ", st["text"])

    def test_blank_key_is_refused(self):
        for fill in (0x00, 0xff):
            st = self.verdict(slot(fill=fill), slot(fill=fill))
            self.assertFalse(st["ok"])
            self.assertIn("blank", st["text"])

    def test_too_short_is_refused(self):
        st = self.verdict(slot(inner=128), slot(inner=128))
        self.assertFalse(st["ok"])
        self.assertIn("288", st["text"])

    def test_damaged_item_is_refused(self):
        st = self.verdict(slot(outer=400), slot(outer=400))
        self.assertFalse(st["ok"])
        self.assertIn("damaged", st["text"])

    def test_empty_region_says_so_plainly(self):
        st = hdcpkey.hdcp14_status(bytes(hdcpkey.REGION_SECTORS * hdcpkey.SECTOR))
        self.assertFalse(st["ok"])
        self.assertIn("no HDCP 1.4 key set", st["text"])
        self.assertIn("without protected playback", st["text"])

    def test_position_in_the_region_does_not_matter(self):
        """Found by name, not by a constant slot index."""
        for at in (0, 2, 7, 20):
            st = self.verdict(slot(), slot(), at=at)
            self.assertTrue(st["ok"], "slot %d: %s" % (at, st["text"]))

    def test_a_known_set_is_named(self):
        payload = bytes((i * 13 + 5) % 251 for i in range(320))
        digest = hashlib.sha256(payload[:288]).hexdigest()
        hdcpkey.KNOWN_SETS = dict(hdcpkey.KNOWN_SETS)
        hdcpkey.KNOWN_SETS[digest] = "the test key set"
        try:
            st = self.verdict(slot(), slot())
            self.assertIn("the test key set", st["text"])
        finally:
            del hdcpkey.KNOWN_SETS[digest]

    def test_an_unknown_set_asks_to_be_reported(self):
        st = self.verdict(slot(salt=99), slot(salt=99))
        self.assertTrue(st["ok"])
        self.assertIn("please report", st["text"])


class TestSurvey(unittest.TestCase):
    """The unknown-board path: find the items instead of assuming where they are."""

    def write(self, blob):
        handle = tempfile.NamedTemporaryFile(suffix=".img", delete=False)
        handle.write(blob)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_finds_items_at_an_unexpected_position(self):
        """A board that keeps its region somewhere else is still surveyed."""
        blob = bytes(5 << 20) + region(slot(), slot(), at=0)
        rows = hdcpkey.survey(self.write(blob))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["lba"], (5 << 20) // hdcpkey.SECTOR)
        self.assertTrue(all(r["name"] == "hdcpkey" for r in rows))

    def test_finds_items_across_a_chunk_boundary(self):
        """The read is chunked; a slot on the seam must not be lost."""
        at = hdcpkey.SCAN_CHUNK - SLOT // 2
        blob = bytes(at) + slot() + slot() + bytes(SLOT)
        rows = hdcpkey.survey(self.write(blob))
        self.assertEqual(len(rows), 2, [r["lba"] for r in rows])

    def test_report_offers_the_lines_to_paste(self):
        rows = self.write(region(slot(salt=42), slot(salt=42), at=0))
        text = hdcpkey.survey_report(rows)
        self.assertIn("UNKNOWN key set", text)
        self.assertIn("KNOWN_SETS", text)
        self.assertIn("no_key_material.py", text)
        # once per distinct set, not once per copy
        self.assertEqual(text.count("key set of <board>"), 1)

    def test_report_explains_an_empty_result(self):
        text = hdcpkey.survey_report(self.write(bytes(2 << 20)))
        self.assertIn("none found", text)
        self.assertIn("filled", text)

    def test_no_key_bytes_in_the_report(self):
        """A report may carry fingerprints and structure, never key material."""
        payload = bytes((i * 13 + 5) % 251 for i in range(320))
        text = hdcpkey.survey_report(self.write(region(slot(), slot(), at=0)))
        self.assertNotIn(payload[:32].hex(), text.lower())
        for row in hdcpkey.survey(self.write(region(slot(), slot(), at=0))):
            self.assertNotIn("payload", row)


if __name__ == "__main__":
    unittest.main()
