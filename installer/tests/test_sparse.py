"""sparse_schreiben(): an Android sparse image unpacked onto a fake disk."""

import os
import struct
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

SECT = fakedisk.SECT
BLK = 4096                                      # 8 sectors per sparse block
RAW, FILL, DONT_CARE, CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4
TARGET = 20000                                  # well clear of the locked block
RAW_BYTES = bytes(bytearray(range(256))) * 32   # 8192 B = 2 blocks
FILL_WORD = b"\xa5\x5a\xa5\x5a"
# frozen 2026-09-14 from hy310-install.py 0.1: RAW 2 blocks + FILL 3 blocks +
# DONT_CARE 2 blocks all count as written, the CRC chunk does not.
WRITTEN = 8192 + 3 * BLK + 2 * BLK


def _chunk(kind, blocks, payload=b""):
    return struct.pack("<HHII", kind, 0, blocks, 12 + len(payload)) + payload


def _image():
    """RAW, FILL, DONT_CARE and a CRC chunk -- every type the writer knows."""
    body = (_chunk(RAW, 2, RAW_BYTES) + _chunk(FILL, 3, FILL_WORD) +
            _chunk(DONT_CARE, 2) + _chunk(CRC32, 0, struct.pack("<I", 0x1234)))
    return struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, BLK, 7, 4, 0) + body


class _Blob(object):
    """The minimal source interface sparse_schreiben() uses."""
    def __init__(self, data):
        self.data, self.size = data, len(data)

    def read(self, off, n):
        return self.data[off:off + n]


class SparseWrite(unittest.TestCase):
    def setUp(self):
        self.inst = support.tool("install")
        path = os.path.join(support.workdir(self), "small.img")
        with open(path, "wb") as fh:
            fh.truncate(131072 * SECT)
            fh.seek(TARGET * SECT)
            fh.write(fakedisk.pattern("sparse-target", TARGET, 64))
        self.platte = self.inst.Platte(path, schreiben=True)
        self.addCleanup(self.platte.close)

    def test_every_chunk_lands_where_it_belongs(self):
        self.assertTrue(self.inst.ist_sparse(_image()[:28]))
        self.assertFalse(self.inst.ist_sparse(b"\0" * 28))
        got = self.inst.sparse_schreiben(self.platte, _Blob(_image()), TARGET)
        self.assertEqual(got, WRITTEN)
        self.assertEqual(self.platte.lies(TARGET, 16), RAW_BYTES)
        self.assertEqual(self.platte.lies(TARGET + 16, 24), FILL_WORD * (3 * BLK // 4))
        # DONT_CARE is written as zeros, not skipped: the tool says so on purpose
        # ("egal heisst auf einem frisch geloeschten Geraet: Nullen"), and the
        # pattern that stood there is gone.  Frozen as today's behaviour.
        self.assertEqual(self.platte.lies(TARGET + 40, 16), b"\0" * (2 * BLK))
        self.assertEqual(self.platte.lies(TARGET + 56, 8),
                         fakedisk.pattern("sparse-target", TARGET + 56, 8))

    def test_a_dry_run_writes_nothing(self):
        before = self.platte.lies(TARGET, 64)
        got = self.inst.sparse_schreiben(self.platte, _Blob(_image()), TARGET, True)
        self.assertEqual(got, WRITTEN)
        self.assertEqual(self.platte.lies(TARGET, 64), before)

    def test_the_write_lock_stops_a_chunk_that_crosses_it(self):
        first, last = self.inst.SPERRE_ERSTER, self.inst.SPERRE_LETZTER
        self.assertEqual((first, last), (12288, 14335))
        with self.assertRaises(RuntimeError) as caught:
            self.inst.sparse_schreiben(self.platte, _Blob(_image()), first - 8)
        self.assertIn("Secure Storage", str(caught.exception))
        self.assertEqual(self.platte.lies(first, 2048), b"\0" * (2048 * SECT))

    def test_a_wrong_block_count_is_refused(self):
        broken = bytearray(_image())
        struct.pack_into("<I", broken, 16, 99)          # total_blks in the header
        with self.assertRaises(RuntimeError):
            self.inst.sparse_schreiben(self.platte, _Blob(bytes(broken)), TARGET)
