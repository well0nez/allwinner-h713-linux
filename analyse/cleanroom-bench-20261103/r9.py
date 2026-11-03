#!/usr/bin/env python3
"""RGB plane over the video plane: the uncovered lines and the word that moves them.
Needs all of 12 on the Q1 state (minimize.py all leaves a black video frame).  r9.py LOG STEP ...
setup  : white XRGB buffer, RGB channel on, PNL_SEL 0x29000000, alpha 0xff; read the histogram
roll W V : write word W = V (a raster total shortened by one line), sample the uncovered pixels every frame until
         they reach 0 or 5 s pass, then restore W and watch 3 s
alpha  : histograms at alpha 0xff, 0x80, 0x40, 0x00"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr, wr_logged  # noqa: E402

SC = 0x05600000
A = 0x4B200000
openlog(sys.argv[1])


def hist():
    return [rd(0x051C0380 + 4 * i) for i in range(32)]


def low():
    h = hist()
    return sum(h[:9]), sum(h[24:]), h


def setup():
    m, off = map_ram(A, 7680 * 1080)
    m[off:off + 7680 * 1080] = b"\xff\xff\xff\xff" * (1920 * 1080)
    for o in (0x070, 0x074, 0x078, 0x07C):
        wr(SC + o, 0x6CA00000)
    for o in (0x084, 0x088, 0x08C, 0x090):
        wr(SC + o, 0x6CA00000 + 1920 * 1080)
    wr(SC + 0x06C, 1)
    wr(SC + 0x178, A)
    wr(SC + 0x170, 0x1E00)
    wr(SC + 0x174, 0x04381E00)
    wr_logged(SC + 0x140, 0x03001901, "RGB on")
    wr(SC + 0x144, 1)
    wr_logged(0x051C006C, 0x29000000, "PNL_SEL RGB over video")
    wr_logged(0x051C0070, (rd(0x051C0070) & ~0xFF) | 0xFF, "alpha 0xff")
    time.sleep(0.1)
    lo, hi, h = low()
    log(f"SETUP: uncovered (low bins) {lo} = {lo / 1920:.2f} lines, high {hi}; RASTER {rd(0x0525C000):#x} OSD {rd(0x0524C010):#x} TCON {rd(0x05880020):#x}")


def roll(word, val):
    old = rd(word)
    wr_logged(word, val, "one line shorter")
    t0 = time.monotonic()
    series = []
    last = None
    while time.monotonic() - t0 < 5.0:
        lo, hi, _ = low()
        if lo != last:
            series.append((round(time.monotonic() - t0, 3), lo))
            last = lo
        if lo == 0:
            break
    wr_logged(word, old, "restored")
    log(f"ROLL {word:#x}={val:#x}: uncovered over time (s, pixels): {series[:40]}{' ...' if len(series) > 40 else ''}")
    t1 = time.monotonic()
    vals = set()
    while time.monotonic() - t1 < 3.0:
        vals.add(low()[0])
    log(f"ROLL after restore, 3 s: uncovered values seen {sorted(vals)[:10]}; RGB done rate check next")
    n = 0
    wr(SC + 0x168, 2)
    t2 = time.monotonic()
    while time.monotonic() - t2 < 2.0:
        if rd(SC + 0x168) & 2:
            n += 1
            wr(SC + 0x168, 2)
    log(f"ROLL RGB done {n / 2:.1f}/s, line counter {rd(0x051C0174):#x}")


def alpha():
    for a in (0xFF, 0x80, 0x40, 0x00):
        wr(0x051C0070, (rd(0x051C0070) & ~0xFF) | a)
        time.sleep(0.1)
        lo, hi, h = low()
        log(f"ALPHA {a:#04x}: " + " ".join(f"{i}:{v}" for i, v in enumerate(h) if v))


args = sys.argv[2:]
i = 0
while i < len(args):
    if args[i] == "roll":
        roll(int(args[i + 1], 0), int(args[i + 2], 0))
        i += 3
    else:
        {"setup": setup, "alpha": alpha}[args[i]]()
        i += 1
log("R9 DONE")
