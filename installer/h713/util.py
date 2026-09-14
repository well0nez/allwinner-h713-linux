"""Small shared helpers: sizes, durations, hashes, hexdump, crc32."""

from __future__ import annotations

import hashlib
import os
import time
import zlib

SECTOR = 512          # bytes per eMMC sector; the one definition for the whole package


def mib(b):
    return b / 2**20


def duration(seconds):
    if seconds < 90:
        return "%.0f s" % seconds
    return "%.0f min" % (seconds / 60)


def relpath_or_abs(p, base):
    """Relative to the project root when that works -- under Windows paths
    live on different drives, and then relpath raises."""
    try:
        return os.path.relpath(p, base)
    except ValueError:
        return os.path.abspath(p)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path, chunk: int = 8 << 20, log=None) -> str:
    h = hashlib.sha256()
    n = 0
    t0 = time.time()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
            n += len(b)
    if log:
        log.info(f"sha256 over {n} B in {time.time() - t0:.1f} s")
    return h.hexdigest()


def hexdump_short(b: bytes, n: int = 16) -> str:
    return " ".join(f"{x:02x}" for x in b[:n])


def crc32(b: bytes) -> int:
    return zlib.crc32(b) & 0xFFFFFFFF
