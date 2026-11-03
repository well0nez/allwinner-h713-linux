#!/usr/bin/env python3
"""Which 4 KiB pages after RX_CTL / RX_LINK hold something other than an alias (8-bit reads, each page logged first)."""
import sys
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog  # noqa: E402
def rb(a):
    m, o = _page(a); return m[o]
openlog(sys.argv[1])
for base, ref in ((0x06800000, None), (0x06840000, None), (0x06880000, None)):
    pages = []
    for p in range(0, 0x40000, 0x1000):
        a = base + p
        log(f"BEFORE-READ {a:#010x}")
        b = bytes(rb(a + i) for i in range(0x1000))
        pages.append(b)
        nz = sum(1 for x in b if x)
        same = [f"{base + q * 0x1000:#x}" for q in range(len(pages) - 1) if pages[q] == b][:1]
        log(f"PAGE {a:#010x} nonzero {nz} {'= ' + same[0] if same else 'distinct'}")
