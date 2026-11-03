#!/usr/bin/env python3
"""RGB over video: which firmware PNL word (0x051c0000..007c) closes the uncovered band; phase RGB-done vs video vsync.
Needs the Q1 state with minimize.py all (black video frame).  r10.py LOG STEP ...
setup        white XRGB buffer on the RGB channel, PNL_SEL 0x29000000, alpha 0xff
state        uncovered, histogram, phase
pnl          firmware PNL words one at a time (cumulative), state after each
one ADDR VAL write one word, state
alpha        histograms at alpha 0xff, 0x80, 0x40, 0"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr, wr_logged  # noqa: E402

SC = 0x05600000
PNL = 0x051C0000
A = 0x4B200000
FW = [(0x000, 0x707F0000), (0x004, 0x00050005), (0x008, 0x01000000), (0x00C, 0x3), (0x014, 0x18000005),
      (0x020, 0x00301F30), (0x028, 0x1F300030), (0x02C, 0x00300030), (0x030, 0x30), (0x038, 0x02000000),
      (0x03C, 0x07800000), (0x040, 0x04380000), (0x048, 0x200), (0x050, 0x38), (0x078, 0x200), (0x07C, 0x300)]
openlog(sys.argv[1])


def hist():
    return [rd(PNL + 0x380 + 4 * i) for i in range(32)]


def phase(seconds=0.25):
    """Mean time from each video vsync (SC+0x0c0 bit 0) to the next RGB done (SC+0x168 bit 1), in ms; vsync rate."""
    wr(SC + 0x0C0, 1)
    wr(SC + 0x168, 2)
    tv, tr = [], []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        if rd(SC + 0x0C0) & 1:
            tv.append(time.perf_counter())
            wr(SC + 0x0C0, 1)
        if rd(SC + 0x168) & 2:
            tr.append(time.perf_counter())
            wr(SC + 0x168, 2)
    d = []
    for v in tv:
        nxt = [r for r in tr if r > v]
        if nxt:
            d.append((nxt[0] - v) * 1000)
    if not d:
        return f"phase: vsync {len(tv)} rgb {len(tr)} (no pairs)"
    d.sort()
    med = d[len(d) // 2]
    return f"phase: vsync->rgb-done median {med:.3f} ms = {med / 0.013563:.0f} lines (min {d[0]:.3f} max {d[-1]:.3f}, {len(tv)} vsync, {len(tr)} rgb in {seconds} s)"


def state(label):
    time.sleep(0.1)
    h = hist()
    lo, mid, hi = sum(h[:9]), sum(h[9:24]), sum(h[24:])
    nz = " ".join(f"{i}:{v}" for i, v in enumerate(h) if v)
    log(f"STATE {label}: low {lo} ({lo / 1920:.2f} lines) mid {mid} high {hi}; bins {nz}; {phase()}")
    return lo


def setup():
    m, off = map_ram(A, 7680 * 1080)
    m[off:off + 7680 * 1080] = b"\xff\xff\xff\xff" * (1920 * 1080)
    wr(SC + 0x178, A)
    wr(SC + 0x170, 0x1E00)
    wr(SC + 0x174, 0x04381E00)
    wr_logged(SC + 0x140, 0x03001901, "RGB on")
    wr(SC + 0x144, 1)
    wr_logged(PNL + 0x06C, 0x29000000, "PNL_SEL RGB over video")
    wr_logged(PNL + 0x070, (rd(PNL + 0x070) & ~0xFF) | 0xFF, "alpha 0xff")
    state("setup")


def pnl():
    for o, v in FW:
        old = rd(PNL + o)
        wr_logged(PNL + o, v, f"firmware PNL {o:#05x} (was {old:#x})")
        state(f"PNL {o:#05x}={v:#x} (was {old:#x}) rb {rd(PNL + o):#x}")


def alpha():
    for a in (0xFF, 0x80, 0x40, 0x00):
        wr(PNL + 0x070, (rd(PNL + 0x070) & ~0xFF) | a)
        state(f"alpha {a:#04x}")
    wr(PNL + 0x070, (rd(PNL + 0x070) & ~0xFF) | 0xFF)


args = sys.argv[2:]
i = 0
while i < len(args):
    a = args[i]
    if a == "one":
        ad, v = int(args[i + 1], 0), int(args[i + 2], 0)
        old = rd(ad)
        wr_logged(ad, v, f"one (was {old:#x})")
        state(f"{ad:#010x}={v:#x} (was {old:#x})")
        i += 3
    else:
        {"setup": setup, "state": lambda: state("now"), "pnl": pnl, "alpha": alpha}[a]()
        i += 1
log("R10 DONE")
