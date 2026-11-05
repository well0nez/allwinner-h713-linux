#!/usr/bin/env python3
"""Q-ALN-1 part 2: horizontal total 2201/2199 for n lines, written d us after the video line counter steps.
Each trial: wait for the line counter to step to l0, wait d us, write; wait for it to step to l0 + n, wait d us,
restore. Then the column/row move from the bands. A move of -30 rows and +464 columns is 65536 pixel clocks.
aln1b.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402
import meas  # noqa: E402


def run_start(vis, width, total, window):
    n = len(vis) * width
    lost = [width - v for v in vis]
    bands = [k for k, l in enumerate(lost) if l > 0.5]
    if not bands:
        return n
    k0 = bands[0]
    L = round(sum(lost))
    if abs(L - window) <= 1:
        return k0 * width + round(vis[k0])
    if k0 == 0:
        return (n + L) % total
    return n - L


R = 0x0525C000
LINE = 0x051C0174
openlog(sys.argv[1])
ORIG = rd(R)


def line():
    return rd(LINE) & 0xFFFF


def edge(target):
    """Spin until the line counter steps to target; return perf_counter at the step."""
    t0 = time.perf_counter()
    prev = line()
    while True:
        cur = line()
        if cur != prev and cur == target:
            return time.perf_counter()
        prev = cur
        if time.perf_counter() - t0 > 0.1:
            return None


def spin(t, us):
    while time.perf_counter() - t < us * 1e-6:
        pass


def trial(h, n, l0, d):
    t = edge(l0)
    if t is None:
        return None
    spin(t, d)
    wr(R, (ORIG & 0xFFFF0000) | (h - 1))
    a = line()
    t = edge((l0 + n) % 1125)
    spin(t, d)
    wr(R, ORIG)
    b = line()
    return a, b, (time.perf_counter() - t) * 1e6


def pos():
    m = meas.measure()
    return run_start(m["col"], 80, 2200, 280), run_start(m["row"], 45, 1125, 45)


if __name__ == "__main__":
    s, r = pos()
    log(f"ALN1B start s={s} r={r}")
    for d in [0, 2, 4, 6, 8, 10]:
        for k in range(4):
            h = 2201 if k % 2 == 0 else 2199
            for l0 in (300, 1100):
                s0, r0 = pos()
                res = trial(h, 8, l0, d)
                s1, r1 = pos()
                ds = (s1 - s0 + 1100) % 2200 - 1100
                dr = (r1 - r0 + 562) % 1125 - 562
                clocks = dr * 2200 - ds if False else None
                log(f"ALN1B d={d} us h={h} n=8 l0={l0}: lines at write/restore {res[0] if res else None}/{res[1] if res else None}; "
                    f"columns {ds:+d}, rows {dr:+d}")
                if abs(ds) > 40 or dr:
                    # put it back roughly: undo by the opposite move is not reliable; re-align happens outside
                    pass
    s, r = pos()
    log(f"ALN1B end s={s} r={r}")
