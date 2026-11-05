#!/usr/bin/env python3
"""Q-ALN-1 part 4: horizontal total for m lines inside one frame (no frame start between), written 8 us after the
video line counter steps; m from 4 to 800.  aln1d.py LOG"""
import sys
sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402
from aln1b import edge, pos, spin  # noqa: E402
R = 0x0525C000
openlog(sys.argv[1])
ORIG = rd(R)
for m in (4, 8, 16, 32, 64, 128, 256, 512, 800):
    for h in (2201, 2199):
        for _ in range(2):
            s0, r0 = pos()
            t = edge(200); spin(t, 8); wr(R, (ORIG & 0xFFFF0000) | (h - 1)); a = rd(0x051C0174) & 0xFFFF
            t = edge(200 + m); spin(t, 8); wr(R, ORIG); b = rd(0x051C0174) & 0xFFFF
            s1, r1 = pos()
            ds = (s1 - s0 + 1100) % 2200 - 1100
            dr = (r1 - r0 + 562) % 1125 - 562
            log(f"ALN1D h={h} m={m}: lines read after the writes {a}/{b}; columns {ds:+d}, rows {dr:+d}")
