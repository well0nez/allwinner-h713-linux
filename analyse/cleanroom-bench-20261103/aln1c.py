#!/usr/bin/env python3
"""Q-ALN-1 part 3: is RASTER 0x000 taken once per frame? Writes 8 us after a video line step (safe window, aln1b).
w(L1, val) ... restore at L2 (same frame if L2 > L1, next frame otherwise).  aln1c.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402
import meas  # noqa: E402
from aln1b import edge, pos, spin  # noqa: E402

R = 0x0525C000
openlog(sys.argv[1])
ORIG = rd(R)
D = 8


def window(val, l1, l2):
    t = edge(l1)
    spin(t, D)
    wr(R, val)
    t = edge(l2)
    spin(t, D)
    wr(R, ORIG)


def word(h, v):
    return ((v - 1) << 16) | (h - 1)


def run(label, val, l1, l2, reps=3):
    for _ in range(reps):
        s0, r0 = pos()
        window(val, l1, l2)
        s1, r1 = pos()
        ds = (s1 - s0 + 1100) % 2200 - 1100
        dr = (r1 - r0 + 562) % 1125 - 562
        log(f"ALN1C {label}: {val:#010x} from line {l1} to {l2}: columns {ds:+d}, rows {dr:+d}")


run("H 2201, 800 lines, no frame start between", word(2201, 1125), 200, 1000)
run("H 2201, across one frame start (325 lines)", word(2201, 1125), 1000, 200)
run("H 2199, across one frame start (325 lines)", word(2199, 1125), 1000, 200)
run("H 2201, one whole frame", word(2201, 1125), 600, 600)
run("H 2200 V 1155, across one frame start", word(2200, 1155), 1000, 200)
for c in (25, 30, 37, 49):
    run(f"H 2201 V {1125 + c} across a frame start, then H 2199 across the next", word(2201, 1125 + c), 1000, 200, 1)
    run(f"  (second frame of the c={c} pair)", word(2199, 1125), 1000, 200, 1)
