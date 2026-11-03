#!/usr/bin/env python3
"""Q-ALN-1: horizontal total 2201 (or 2199) for only m lines; does the RGB image move by exactly m columns?
Timing by the video raster's line counter PNL 0x051c0174 [15:0] (same rate as the RGB raster, fixed offset).
Needs the aligned state of 05 §2.1 (r10.py setup + align3.py).  aln1.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402
import meas  # noqa: E402

def run_start(vis, width, total, window):
    """Start of the lost window from per-band visible counts (bands of `width`), panel extent len(vis)*width."""
    n = len(vis) * width
    lost = [width - v for v in vis]
    bands = [k for k, l in enumerate(lost) if l > 0.5]
    if not bands:
        return n  # aligned (the window lies in the blanking)
    k0 = bands[0]
    L = round(sum(lost))
    if abs(L - window) <= 1:
        return k0 * width + round(vis[k0])  # whole window inside the panel
    if k0 == 0:
        return (n + L) % total  # window wraps from the blanking into the start
    return n - L  # window starts inside and runs into the blanking

R = 0x0525C000
LINE = 0x051C0174
openlog(sys.argv[1])
ORIG = rd(R)


def line():
    return rd(LINE) & 0xFFFF


def mlines(h, m, l0):
    """Write horizontal total h at video line l0, restore when the line counter reaches l0 + m."""
    l1 = (l0 + m) % 1125
    t0 = time.perf_counter()
    while line() != l0:
        if time.perf_counter() - t0 > 0.1:
            return None
    wr(R, (ORIG & 0xFFFF0000) | (h - 1))
    a = line()
    while line() != l1:
        pass
    wr(R, ORIG)
    b = line()
    return a, b


def s_now():
    m = meas.measure()
    return run_start(m["col"], 80, 2200, 280), run_start(m["row"], 45, 1125, 45), m


s0, r0, m0 = s_now()
log(f"ALN1 start: s={s0} r={r0}; {meas.fmt(m0)}")
for h, m, l0 in [(2201, 1, 200), (2201, 1, 200), (2201, 2, 200), (2201, 5, 200), (2201, 10, 200), (2201, 25, 200),
                 (2199, 25, 200), (2199, 10, 200), (2199, 5, 200), (2199, 2, 200), (2199, 1, 200), (2199, 1, 200),
                 (2201, 10, 700), (2199, 10, 700), (2201, 10, 1100), (2199, 10, 1100),
                 (2201, 10, 1120), (2199, 10, 1120)]:
    s_a, r_a, _ = s_now()
    res = mlines(h, m, l0)
    s_b, r_b, mm = s_now()
    ds = (s_b - s_a + 1100) % 2200 - 1100
    log(f"ALN1 h={h} m={m} from video line {l0}: written at line {res[0] if res else None}, restored at {res[1] if res else None}; "
        f"s {s_a} -> {s_b} (moved {ds:+d} columns), r {r_a} -> {r_b}")
s1, r1, m1 = s_now()
log(f"ALN1 end: s={s1} r={r1}; {meas.fmt(m1)}")
