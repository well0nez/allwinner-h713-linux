#!/usr/bin/env python3
"""Closed-loop alignment of the RGB raster to the video raster (feedback: meas.py column/row bands).
s = first RGB column that falls into the video's horizontal blanking window (aligned: s = 1920);
r = first RGB row that falls into the video's vertical blanking (aligned: r = 1080).
align3.py LOG"""
import sys

sys.path.insert(0, "/data/bench")
from blog import log, openlog  # noqa: E402
import meas  # noqa: E402

openlog(sys.argv[1])


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
def state():
    m = meas.measure()
    s = run_start(m["col"], 80, 2200, 280)
    r = run_start(m["row"], 45, 1125, 45)
    return s, r, m


s, r, m = state()
log(f"ALIGN3 start: s={s} r={r}; {meas.fmt(m)}")
for it in range(60):
    d = (1920 - s) % 2200
    if d == 0:
        break
    if d > 1100:  # go the other way
        d -= 2200
    if abs(d) >= 50:
        n = min(abs(d) // 50, 8)
        if d > 0:
            meas.frames(2199, 1125, 2 * n)  # +50 px per two frames
        else:
            meas.frames(2201, 1125, 2 * n)  # -50 px per two frames
        what = f"{2 * n} x {'2199' if d > 0 else '2201'}x1125"
    else:
        n = min(abs(d), 10)
        for _ in range(n):
            if d > 0:
                meas.frames(2199, 1126)
                meas.frames(2201, 1125)
            else:
                meas.frames(2201, 1126)
                meas.frames(2199, 1125)
        what = f"{n} pairs {'+' if d > 0 else '-'}1 px"
    s, r, m = state()
    log(f"ALIGN3 h {it}: {what} -> s={s} r={r}")
log(f"ALIGN3 horizontal done: s={s} r={r}; {meas.fmt(m)}")
for it in range(10):
    d = (r - 1080) % 1125  # rows to move the cut up; a frame lengthened by c lines moves it up by c rows
    if d == 0:
        break
    T = d if d >= 25 else d + 1125  # frames lengthened by 1 line disturbed the horizontal phase; use >= 25
    parts = []
    while T > 0:
        c = min(100, T)
        if 0 < T - c < 25:
            c = T - 25
        parts.append(c)
        T -= c
    for c in parts:
        meas.frames(2200, 1125 + c)
    s, r, m = state()
    log(f"ALIGN3 v {it}: lengthened frames {parts} -> s={s} r={r}")
log(f"ALIGN3 done: s={s} r={r}; {meas.fmt(m)}")
