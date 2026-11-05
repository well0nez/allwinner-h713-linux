#!/usr/bin/env python3
"""Read-only register snapshot of the stage-2 blocks (two passes 50 ms apart). snap.py LOG LABEL"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, rd_logged  # noqa: E402

openlog(sys.argv[1])
log(f"--- SNAP {sys.argv[2]}")
regions = [
    ("CCU", 0x02001600, 4), ("CCU-db0", 0x02001DB0, 12), ("GP5", 0x07090114, 1),
    ("DTOP", 0x05700000, 35), ("TVTOP", 0x06E00000, 3),
    ("SCANOUT", 0x05600000, 0x400 // 4),
    ("PNL", 0x051C0000, 0x400 // 4), ("PNL_LOCK", 0x051CFE00, 0xA0 // 4),
    ("PROC", 0x05140000, 0xE0C // 4), ("PROC_LOCK", 0x0514FE00, 0x94 // 4),
    ("SCL", 0x05180000, 0x400 // 4), ("BORDER", 0x05200000, 12),
    ("NRC", 0x05000000, 0xA9C // 4), ("NRC2", 0x05001000, 0x40 // 4),
    ("DEI", 0x050C0000, 0x800 // 4), ("DEI-c90", 0x050C0C90, 8),
    ("MIX", 0x058C0000, 16), ("TCON", 0x05880000, 16), ("OSD", 0x0524C000, 32), ("RASTER", 0x0525C000, 14),
    ("CAP", 0x06940000, 0x1000 // 4),
]
first = {}
for label, a, n in regions:
    first[label] = rd_logged(a, n, label)
time.sleep(0.05)
for label, a, n in regions:
    b = [rd(a + 4 * i) for i in range(n)]
    moved = [(a + 4 * i, x, y) for i, (x, y) in enumerate(zip(first[label], b)) if x != y]
    if moved:
        log(f"MOVING {label}: " + ", ".join(f"{p:#010x} {x:08x}->{y:08x}" for p, x, y in moved))
log("SNAP DONE")
