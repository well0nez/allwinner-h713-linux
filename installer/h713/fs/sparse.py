# -*- coding: utf-8 -*-
"""Android sparse images: the writer (installer) and the magic/chunk constants.

Stage 1 of plan doku/121: moved verbatim from `hy310-install.py` (I:1657-1731), identifiers and comments
translated to English, every user-visible string kept byte-identical.

The sparse *reader* is `SparseSource` in `h713.source`; it is re-exported here for convenience. Note that
`SparseSource.is_sparse(source)` takes a source, while `is_sparse(header)` here takes the first bytes.
"""

from __future__ import annotations

import struct

from h713.source import SparseSource

from h713.util import SECTOR   # one definition for the whole package

SPARSE_MAGIC = 0xed26ff3a
_CHUNK_RAW, _CHUNK_FILL, _CHUNK_DONT_CARE, _CHUNK_CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4

__all__ = ["SPARSE_MAGIC", "SparseSource", "is_sparse", "write_sparse"]


def is_sparse(header):
    """An Android sparse image? The first four bytes give it away."""
    return len(header) >= 28 and struct.unpack_from("<I", header, 0)[0] == SPARSE_MAGIC


def write_sparse(disk, data, part_lba, dry_run=False):
    """Unpack an Android sparse image and write it at part_lba.

    super.fex is packed like this: 1537 MiB file, 2048 MiB content. Whoever
    writes the container raw onto the partition leaves data garbage there --
    Android then does not find system, vendor and product and boots back into
    the bootloader (happened exactly that way on 10.09., without any message).

    `disk` is a block device with write(lba, bytes) and read(lba, n) (h713.blockdev.Disk);
    `data` is a source with read(offset, n) (h713.source.Source).

    Returns: the number of bytes written.
    """
    (_, maj, _mn, fhsz, chsz, blk, nblk, nchunk, _crc) = struct.unpack(
        "<IHHHHIIII", data.read(0, 28))
    if maj != 1:
        raise RuntimeError("sparse version %d is not supported" % maj)
    if blk % SECTOR:
        raise RuntimeError("sparse block size %d is not a multiple of %d" % (blk, SECTOR))
    step = 1 << 20                        # write in 1 MiB steps
    pos, block, written = fhsz, 0, 0

    def write_at(bl, buf):
        if not dry_run:
            disk.write(part_lba + bl * (blk // SECTOR), buf)

    for _ in range(nchunk):
        ctype, _res, cblk, csz = struct.unpack("<HHII", data.read(pos, chsz))
        src, length = pos + chsz, csz - chsz
        if ctype == _CHUNK_RAW:
            off = 0
            while off < length:
                n = min(step, length - off)
                write_at(block + off // blk, data.read(src + off, n))
                off += n
            written += length
        elif ctype == _CHUNK_FILL:
            pattern = data.read(src, 4)
            total = cblk * blk
            full = pattern * (step // 4)
            off = 0
            while off < total:
                n = min(step, total - off)
                write_at(block + off // blk, full[:n])
                off += n
            written += total
        elif ctype == _CHUNK_DONT_CARE:
            # "don't care" means, on a freshly erased device: zeros. Here the
            # previous system would otherwise stand there.
            total = cblk * blk
            zeros = b"\0" * step
            off = 0
            while off < total:
                n = min(step, total - off)
                write_at(block + off // blk, zeros[:n])
                off += n
            written += total
        elif ctype == _CHUNK_CRC32:
            pass
        else:
            raise RuntimeError("unknown sparse chunk type 0x%04x" % ctype)
        block += cblk
        pos += csz
    if block != nblk:
        raise RuntimeError("sparse image incomplete: %d of %d blocks"
                           % (block, nblk))
    return written
