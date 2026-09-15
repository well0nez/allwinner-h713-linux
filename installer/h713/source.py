# -*- coding: utf-8 -*-
"""Sources: random read access to a file, a slice, a sparse image, an extent chain.

Stage 1 of plan doku/121: moved verbatim from `h713-extract` (X:338-546 and X:1130), identifiers and comments
translated to English, every user-visible string kept byte-identical.
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

from h713.log import Abort, Log


class Source:
    size: int = 0
    name: str = "?"

    def read(self, off: int, n: int) -> bytes:
        raise NotImplementedError

    def backing(self):
        """(path, offset) if the range lies contiguously in a real file, otherwise None."""
        return None

    def sub(self, off: int, size: int, name: str) -> "Source":
        return SliceSource(self, off, size, name)


class FileSource(Source):
    def __init__(self, path: Path):
        self.path = Path(path)
        self.fh = open(self.path, "rb")
        self.size = self.path.stat().st_size
        self.name = str(self.path)

    def read(self, off, n):
        if off < 0 or n < 0:
            raise ValueError("negativer Lesezugriff")
        self.fh.seek(off)
        return self.fh.read(n)

    def backing(self):
        return (str(self.path), 0)


class SliceSource(Source):
    def __init__(self, parent: Source, off: int, size: int, name: str):
        if off < 0 or off + size > parent.size:
            raise Abort(f"{name}: range {off:#x}+{size:#x} lies outside {parent.name} ({parent.size:#x} B)")
        self.parent, self.off, self.size, self.name = parent, off, size, name

    def read(self, off, n):
        if off >= self.size:
            return b""
        n = min(n, self.size - off)
        return self.parent.read(self.off + off, n)

    def backing(self):
        b = self.parent.backing()
        if b is None:
            return None
        return (b[0], b[1] + self.off)


class SparseSource(Source):
    """Read an Android sparse image (simg) as a logical image - without simg2img."""
    MAGIC = 0xED26FF3A
    RAW, FILL, DONT_CARE, CRC = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4

    @staticmethod
    def is_sparse(q: Source) -> bool:
        return q.size >= 28 and struct.unpack("<I", q.read(0, 4))[0] == SparseSource.MAGIC

    def __init__(self, parent: Source, log: Log):
        self.parent = parent
        self.name = parent.name + " (sparse)"
        h = parent.read(0, 28)
        magic, maj, mi, fhs, chs, self.blk, self.total_blks, self.total_chunks, _cs = struct.unpack("<IHHHHIIII", h)
        if magic != self.MAGIC:
            raise Abort("not a sparse image")
        if (maj, mi) != (1, 0) or fhs != 28 or chs != 12:
            log.warn(f"unusual sparse header: v{maj}.{mi}, header {fhs}, chunk header {chs}")
        self.size = self.blk * self.total_blks
        # chunk map: (logical start, length, type, file offset|fill value)
        self.chunks: list[tuple[int, int, int, int]] = []
        off, lblk = fhs, 0
        types = {self.RAW: 0, self.FILL: 0, self.DONT_CARE: 0, self.CRC: 0}
        for i in range(self.total_chunks):
            t, _r, csz, tsz = struct.unpack("<HHII", parent.read(off, 12))
            if t not in types:
                raise Abort(f"Sparse-Chunk {i}: unbekannter Typ {t:#x}")
            types[t] += 1
            lo, ln = lblk * self.blk, csz * self.blk
            if t == self.RAW:
                if tsz != 12 + ln:
                    raise Abort(f"sparse chunk {i}: RAW length does not fit ({tsz} vs {12 + ln})")
                self.chunks.append((lo, ln, t, off + 12))
            elif t == self.FILL:
                fill = struct.unpack("<I", parent.read(off + 12, 4))[0]
                self.chunks.append((lo, ln, t, fill))
            elif t == self.DONT_CARE:
                self.chunks.append((lo, ln, t, 0))
            else:  # CRC: no blocks
                csz = 0
            off += tsz
            lblk += csz
        if lblk != self.total_blks:
            log.warn(f"sparse: the chunks cover {lblk} blocks, the header says {self.total_blks}")
        self.description = (f"sparse v{maj}.{mi}, block {self.blk}, {self.total_blks} blocks = {self.size} B logical, "
                            f"{self.total_chunks} Chunks (RAW {types[self.RAW]}, FILL {types[self.FILL]}, "
                            f"DONT_CARE {types[self.DONT_CARE]}, CRC {types[self.CRC]})")

    def _find(self, off: int) -> int:
        lo, hi = 0, len(self.chunks) - 1
        while lo <= hi:
            m = (lo + hi) // 2
            s, ln, _t, _d = self.chunks[m]
            if off < s:
                hi = m - 1
            elif off >= s + ln:
                lo = m + 1
            else:
                return m
        return -1

    def read(self, off, n):
        out = bytearray()
        while n > 0 and off < self.size:
            i = self._find(off)
            if i < 0:
                break
            s, ln, t, d = self.chunks[i]
            k = min(n, s + ln - off)
            if t == self.RAW:
                out += self.parent.read(d + (off - s), k)
            elif t == self.FILL:
                pat = struct.pack("<I", d)
                start = (off - s) % 4
                out += (pat * (k // 4 + 2))[start:start + k]
            else:
                out += b"\0" * k
            off += k
            n -= k
        return bytes(out)

    def regions(self):
        """For materializing: (logical start, length, type, data)."""
        return list(self.chunks)


class ChainSource(Source):
    """Several slices one after another (LP extents)."""

    def __init__(self, parts: list[Source], name: str):
        self.parts = parts
        self.name = name
        self.starts = []
        s = 0
        for t in parts:
            self.starts.append(s)
            s += t.size
        self.size = s

    def read(self, off, n):
        out = bytearray()
        for i, t in enumerate(self.parts):
            s = self.starts[i]
            if off >= s + t.size:
                continue
            if n <= 0:
                break
            k = min(n, s + t.size - off)
            out += t.read(off - s, k)
            off += k
            n -= k
        return bytes(out)

    def backing(self):
        if len(self.parts) == 1:
            return self.parts[0].backing()
        return None


class NullSource(Source):
    def __init__(self, size):
        self.size, self.name = size, "zero"

    def read(self, off, n):
        return b"\0" * max(0, min(n, self.size - off))


def materialize(q: Source, target: Path, log: Log):
    """Put a source down as an ordinary file (holes for zero ranges)."""
    t0 = time.time()
    with open(target, "wb") as f:
        # fast path: sparse regions directly
        if isinstance(q, SparseSource):
            for s, ln, t, d in q.regions():
                if t == SparseSource.RAW:
                    f.seek(s)
                    rest, p = ln, d
                    while rest > 0:
                        k = min(rest, 8 << 20)
                        f.write(q.parent.read(p, k))
                        p += k
                        rest -= k
                elif t == SparseSource.FILL and d != 0:
                    f.seek(s)
                    f.write((struct.pack("<I", d) * (ln // 4)))
            f.truncate(q.size)
        else:
            off = 0
            while off < q.size:
                b = q.read(off, 8 << 20)
                if not b:
                    break
                if b.count(0) == len(b):
                    f.seek(off + len(b))
                else:
                    f.seek(off)
                    f.write(b)
                off += len(b)
            f.truncate(q.size)
    log.info(f"{q.name} -> {target.name}: {q.size} B in {time.time() - t0:.1f} s (scratch copy, deleted at the end)")
