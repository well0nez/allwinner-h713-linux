#!/usr/bin/env python3
"""Q0b: write/read-back of one harmless word per stage-2 block; which words move by themselves."""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, rd_logged, wr_logged  # noqa: E402

openlog(sys.argv[1])

# write / read back / restore (path idle: channel 0 off, nothing selects these blocks)
tests = [
    ("SCL_INWIN", 0x05180034, 0x07800438),
    ("SCL_VRATIO", 0x0518003C, 0x00010000),
    ("PROC src window", 0x05140104, 0x07800000),
    ("NRC geometry", 0x05000224, 0x04380780),
    ("BORDER +0c", 0x0520000C, 0x078000A4),
]
for label, a, v in tests:
    old = rd_logged(a, 1, label)[0]
    wr_logged(a, v, label)
    back = rd(a)
    wr_logged(a, old, label + " restore")
    log(f"WRB {label} {a:#010x}: before {old:#010x} wrote {v:#010x} read {back:#010x} restored {rd(a):#010x}")

# words that move by themselves: two snapshots 37 ms apart
regions = [
    ("SCANOUT", 0x05600000, 0x328 // 4),
    ("PNL", 0x051C0000, 0x400 // 4),
    ("TCON", 0x05880000, 0x200 // 4),
    ("PROC_LOCK", 0x0514FE00, 0x94 // 4),
    ("PNL_LOCK", 0x051CFE00, 0xA0 // 4),
    ("RASTER", 0x0525C000, 0x38 // 4),
    ("OSD", 0x0524C000, 0x80 // 4),
    ("MIX", 0x058C0000, 0x40 // 4),
]
for label, base, n in regions:
    a = rd_logged(base, n, label + " snap A")
    time.sleep(0.037)
    b = [rd(base + 4 * i) for i in range(n)]
    moved = [(base + 4 * i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    log(f"MOVING {label}: " + ", ".join(f"{p:#010x} {x:08x}->{y:08x}" for p, x, y in moved))
log("Q0b DONE")
