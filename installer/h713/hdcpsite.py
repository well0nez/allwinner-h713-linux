# SPDX-License-Identifier: GPL-2.0
"""Locate the HDCP 1.4 key-load wait site in an H713 MIPS display.bin.

Mirrors h713_mips_hdcp_context() / h713_mips_find_hdcp_wait() in U-Boot's h713_mips.c (fork commit
80397f0): same word, window, scan, tie-breaking. Package A5's `hdcp_site.py` moved into the package
(stage 2 C-D); the CLI of that script is gone, the rule is unchanged. The extractor calls `search()`
when a display.bin matches no row of profiles.FIRMWARE_REVISIONS -- the result is the row a profile
would need.
"""

from __future__ import annotations

import struct
from typing import List, Optional, Tuple

WAIT_ORIG = 0x2C630033      # "sltiu v1,v1,0x33", H713_MIPS_HDCP_WAIT_ORIG
CTX_HI = 0x0684             # halves of the polled HDMI-RX register 0x06840093
CTX_LO = 0x0093
CTX_WIN = 0x400             # H713_MIPS_HDCP_CTX_WIN
DEFAULT_BASE = 0x4B100000   # H713_MIPS_FW_ADDR


def context_counts(data: bytes, base: int, va: int) -> Tuple[int, int]:
    """Count both register halves in the +/-1 KiB window around va."""
    # C: from = (va - first > WIN) ? va - WIN : first; to = min(va + WIN, last)
    start = va - CTX_WIN if va - base > CTX_WIN else base
    stop = min(va + CTX_WIN, base + len(data))
    hi = lo = 0
    # C: for (p = from; p + 2 <= to; p += 2) -- aligned, non-overlapping u16
    for p in range(start, stop - 1, 2):
        half = struct.unpack_from("<H", data, p - base)[0]
        if half == CTX_HI:
            hi += 1
        elif half == CTX_LO:
            lo += 1
    return hi, lo


def find_hits(data: bytes, base: int = DEFAULT_BASE) -> List[dict]:
    """Every 4-byte-aligned WAIT_ORIG word, in address order, with its context."""
    hits = []
    for off in range(0, len(data) - 3, 4):
        if struct.unpack_from("<I", data, off)[0] == WAIT_ORIG:
            hi, lo = context_counts(data, base, base + off)
            # "context" is the C predicate "return hi && lo": each half at least once
            hits.append({"offset": off, "va": base + off, "count_0684": hi,
                         "count_0093": lo, "context": hi > 0 and lo > 0})
    return hits


def choose(hits: List[dict]) -> Tuple[Optional[int], str]:
    """Return (va, status): "ok", "ambiguous" (>1 with context) or "none"."""
    good = [h for h in hits if h["context"]]
    if len(good) == 1:
        return good[0]["va"], "ok"
    return None, "ambiguous" if good else "none"


def search(data: bytes, base: int = DEFAULT_BASE) -> dict:
    """The whole search over one display.bin, as the extractor reports it.

    Keys: "hdcp_wait_va" (None unless the status is "ok"), "status" ("ok"/"ambiguous"/"none"),
    "hdcp_wait_file_offset", "hits" (every candidate) and "text" (one line per candidate).
    """
    hits = find_hits(data, base)
    va, status = choose(hits)
    return {"hdcp_wait_va": va, "status": status, "base": base,
            "hdcp_wait_file_offset": None if va is None else va - base, "hits": hits,
            "text": ["offset 0x%06x  va 0x%08x  0x0684 x%d  0x0093 x%d%s"
                     % (h["offset"], h["va"], h["count_0684"], h["count_0093"],
                        "  <- context" if h["context"] else "") for h in hits]}


def describe(result: dict) -> str:
    """One line saying what the search found -- "0x4b13d1f0", "ambiguous" or "none"."""
    if result["status"] == "ok":
        return "0x%08x (file offset 0x%x)" % (result["hdcp_wait_va"], result["hdcp_wait_file_offset"])
    if result["status"] == "ambiguous":
        return "ambiguous: " + " and ".join("0x%08x" % h["va"] for h in result["hits"] if h["context"])
    return "none: %d word(s) with the instruction, none with context" % len(result["hits"])
