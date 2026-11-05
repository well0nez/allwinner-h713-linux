#!/usr/bin/env python3
"""Align the RGB raster (RASTER 0x0525c000 totals) to the video raster by changing its totals for single frames.
A frame with totals HxV moves the RGB raster by 2200*1125 - H*V pixel clocks against the video raster.
Feedback: the panel histogram with a white RGB buffer over the black video frame at alpha 0xff (uncovered = low bins).
align2.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402

SC = 0x05600000
PNL = 0x051C0000
R = 0x0525C000
ORIG = rd(R)
openlog(sys.argv[1])


def wait_done():
    wr(SC + 0x168, 2)
    t0 = time.perf_counter()
    while not rd(SC + 0x168) & 2:
        if time.perf_counter() - t0 > 0.1:
            raise SystemExit("no RGB done within 100 ms")


def frame(h, v):
    """One RGB frame with totals h x v: written half a frame after the done bit, restored half a frame after the next."""
    wait_done()
    wr(R, ((v - 1) << 16) | (h - 1))
    wait_done()
    wr(R, ORIG)


def unc():
    time.sleep(0.045)
    h = [rd(PNL + 0x380 + 4 * i) for i in range(32)]
    return sum(h[:9])


def phase(sec=0.1):
    wr(SC + 0x0C0, 1)
    wr(SC + 0x168, 2)
    tv, tr = [], []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < sec:
        if rd(SC + 0x0C0) & 1:
            tv.append(time.perf_counter())
            wr(SC + 0x0C0, 1)
        if rd(SC + 0x168) & 2:
            tr.append(time.perf_counter())
            wr(SC + 0x168, 2)
    d = sorted((min([r for r in tr if r > v], default=v) - v) * 1e3 for v in tv)
    d = [x for x in d if x > 0]
    return d[len(d) // 2] if d else -1.0


SAT = 376200
u = unc()
log(f"ALIGN start: uncovered {u}, phase {phase():.4f} ms, RASTER {ORIG:#x}")

# A: +1125 px per frame until the horizontal overlap leaves saturation
n = 0
while u >= SAT and n < 100:
    frame(2199, 1125)
    n += 1
    u = unc()
log(f"ALIGN A: {n} frames of 2199x1125 -> uncovered {u}")

# B: fine horizontal. Pair P = (2199x1124, 2201x1125) moves +2199 (= +1 line -1 px); pair M = (2201x1126, 2199x1125)
# moves -2201 (= -1 line -1 px)... use P and its mirror Q = (2201x1126 then 2199x1125)? Instead: try both single-px
# moves and keep the one that lowers the count.
def px_minus():  # -2201 = -1 line, -1 px (only lengthened frames: a shortened V can be passed already)
    frame(2201, 1126)
    frame(2199, 1125)


def px_plus():  # +2201 = +1 line, +1 px: (2199x1124) +3324, then (2201x1126)... compute: 2475000-2201*1126=-3326 -> no
    frame(2199, 1126)  # -1074
    frame(2201, 1125)  # -1125 -> total -2199 = -1 line, +1 px
    

best = u
for name, mv in (("minus", px_minus), ("plus", px_plus)):
    k = 0
    while k < 400:
        mv()
        k += 1
        nu = unc()
        if nu > best:
            log(f"ALIGN B {name}: step {k} rose to {nu}; best {best}")
            # undo one step by the other move
            (px_plus if name == "minus" else px_minus)()
            nu = unc()
            log(f"ALIGN B {name}: undone -> {nu}")
            best = nu
            break
        best = nu
    log(f"ALIGN B {name}: after {k} steps uncovered {best} ({best / 1920:.2f} lines), phase {phase():.4f} ms")

# C: vertical. Coarse 25 lines per frame (2200x1100) until the count leaves the 45-row saturation, then 1 line
u = unc()
k = 0
while u >= 86400 and k < 60:
    frame(2200, 1150)
    k += 1
    u = unc()
log(f"ALIGN C coarse: {k} frames of 2200x1150 -> uncovered {u} ({u / 1920:.2f} lines)")
for name, (h, v) in (("down", (2200, 1126)),):
    k = 0
    while k < 120 and u > 0:
        frame(h, v)
        k += 1
        nu = unc()
        if nu > u:
            log(f"ALIGN C {name}: rose at step {k} to {nu}")
        if nu == 0:
            u = 0
            break
        u = nu
    log(f"ALIGN C {name}: after {k} steps uncovered {u} ({u / 1920:.2f} lines), phase {phase():.4f} ms")
    if u == 0:
        break
log("ALIGN DONE")
