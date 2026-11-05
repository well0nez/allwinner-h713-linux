#!/usr/bin/env python3
"""Q0: which stage-2 blocks read back under the bench boot. Usage: q0.py LOG [skip-label ...]"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd_logged  # noqa: E402

openlog(sys.argv[1])
skip = set(sys.argv[2:])

# Stage-1 blocks first: known readable under the bench boot (doku/227 section 2).
known = [
    ("CCU", 0x02001600, 4), ("CCU-pll", 0x02001050, 1), ("CCU-db0", 0x02001DB0, 12),
    ("GP5", 0x07090114, 1),
    ("DTOP", 0x05700000, 35),
    ("SCANOUT", 0x05600000, 52), ("SCANOUT-ch1", 0x05600100, 16), ("SCANOUT-ch2", 0x05600140, 16),
    ("SCANOUT-300", 0x05600300, 10),
    ("MIX", 0x058C0000, 8), ("TCON", 0x05880000, 16), ("OSD", 0x0524C000, 32), ("RASTER", 0x0525C000, 14),
    ("PNL", 0x051C0000, 256),
]
# The Q0 list (90 Q0), in its order: one word first, then the block.
probe = [
    ("PROC", 0x05140000, 0x05140000, 0xE0C // 4),
    ("SCL", 0x05180008, 0x05180000, 0x400 // 4),
    ("BORDER", 0x05200000, 0x05200000, 12),
    ("NRC", 0x05000000, 0x05000000, 0xA9C // 4),
    ("DEI", 0x050C0000, 0x050C0000, 0x800 // 4),
    ("GAMMA", 0x05208000, 0x05208000, 8),
    ("PROC_LOCK", 0x0514FE00, 0x0514FE00, 0x94 // 4),
    ("PNL_LOCK", 0x051CFE00, 0x051CFE00, 0xA0 // 4),
    ("NRC2", 0x05001000, 0x05001000, 0x600 // 4),
    ("TVTOP", 0x06E00000, 0x06E00000, 3),
]

for label, a, n in known:
    if label not in skip:
        rd_logged(a, n, label)

for k in range(2):
    rd_logged(0x051C0174, 1, f"PNL line counter #{k}")
    time.sleep(0.1)

for label, first, base, n in probe:
    if label in skip:
        log(f"SKIP {label}")
        continue
    rd_logged(first, 1, f"{label} first word")
    log(f"OK {label} first word answered")
    rd_logged(base, n, f"{label} block")
    if label == "GAMMA":
        rd_logged(0x05208800, 4, "GAMMA port 2")
        rd_logged(0x05209000, 4, "GAMMA port 3")

log("Q0 DONE")
