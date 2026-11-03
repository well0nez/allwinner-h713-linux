#!/usr/bin/env python3
"""Answers for Q-VP-5, Q-VP-12, Q-VP-13.  r5.py LOG STEP ...
q720  : (after a minimal set on the Q1 state) switch to a 1280x720 frame with the 20 S2 HY320 words; areas of quadrant,
        left half, top half with NRC 0x05000858 = 0x04380010 (unchanged) and = 0x02d00010
nrc2  : (after all of 12) NRC 0x05001028 1:1 value 0x3f000000 against what the bench boot leaves
chroma: (after all of 12, P1 at 1920x1080 on screen) chroma gain variants of PROC 0x05140508"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr, wr_logged  # noqa: E402

SC = 0x05600000
openlog(sys.argv[1])


def hist():
    return [rd(0x051C0380 + 4 * i) for i in range(32)]


def areas(label):
    W, H = 1280, 720
    A = 0x4C000000
    m, off = map_ram(A, W * H * 3 // 2)
    for o in (0x070, 0x074, 0x078, 0x07C):
        wr(SC + o, A)
    for o in (0x084, 0x088, 0x08C, 0x090):
        wr(SC + o, A + W * H)
    wr(SC + 0x06C, 1)
    m[off + W * H:off + W * H * 3 // 2] = bytes([128, 128]) * (W * H // 4)
    out = []
    for kind in ("quad", "left", "top"):
        if kind == "quad":
            m[off:off + (H // 2) * W] = (bytes([235]) * (W // 2) + bytes([16]) * (W // 2)) * (H // 2)
            m[off + (H // 2) * W:off + H * W] = bytes([16]) * (W * H // 2)
        elif kind == "left":
            m[off:off + H * W] = (bytes([235]) * (W // 2) + bytes([16]) * (W // 2)) * H
        else:
            m[off:off + (H // 2) * W] = bytes([235]) * ((H // 2) * W)
            m[off + (H // 2) * W:off + H * W] = bytes([16]) * ((H // 2) * W)
        time.sleep(0.15)
        h = hist()
        s = sum(h)
        out.append(f"{kind} {100.0 * sum(h[24:]) / s:.2f}%/{100.0 * sum(h[:9]) / s:.2f}%")
    log(f"AREAS {label}: high/low " + "; ".join(out) + f" (latch {rd(SC + 0x014)}/{rd(SC + 0x06C)})")


def q720():
    for o, v in [(0x020, 0x02CF04FF), (0x024, 0x002C004F), (0x040, 0x500), (0x044, 0x500), (0x048, 0x02D00500),
                 (0x04C, 0x01680500), (0x030, 0x02D00500), (0x050, 0), (0x054, 0)]:
        wr_logged(SC + o, v, "channel 0 1280x720")
    for a, v, _ in json.load(open("/data/bench/zoom720.json")):
        wr_logged(a, v, "20 S2 HY320 word")
    wr_logged(SC + 0x014, 1, "VCH_LATCH")
    time.sleep(0.1)
    areas("set + S2 HY320, 0x05000858 = %#x" % rd(0x05000858))
    wr_logged(0x05000858, 0x02D00010, "0x858 at source height")
    time.sleep(0.1)
    areas("set + S2 HY320, 0x05000858 = %#x" % rd(0x05000858))
    wr_logged(0x05000858, 0x04380010, "0x858 back")


def show1080(addr):
    for o in (0x070, 0x074, 0x078, 0x07C):
        wr(SC + o, addr)
    for o in (0x084, 0x088, 0x08C, 0x090):
        wr(SC + o, addr + 1920 * 1080)
    wr(SC + 0x06C, 1)


def exact(label):
    res = []
    for addr, name in ((0x4C000000, "white"), (0x6CA00000, "black"), (0x6CD00000, "P1")):
        show1080(addr)
        time.sleep(0.08)
        h = hist()
        res.append(f"{name} " + " ".join(f"{i}:{v}" for i, v in enumerate(h) if v)[:160])
    log(f"EXACT {label}: " + " | ".join(res))


def nrc2():
    old = rd(0x05001028)
    exact(f"0x05001028 = {old:#x} (as left)")
    wr_logged(0x05001028, 0x3F000000, "1:1 value of the firmware")
    log(f"0x05001028 reads {rd(0x05001028):#x}")
    exact("0x05001028 = 0x3f000000")
    wr_logged(0x05001028, old, "back")


def chroma():
    show1080(0x6CD00000)
    for v in (0x04400000, 0x14400000, 0x144C0000, 0x04000000, 0x00000000, 0x04800000):
        wr_logged(0x05140508, v, "chroma gain variant")
        time.sleep(0.1)
        h = hist()
        log(f"CHROMA {v:#010x}: P1 hist " + " ".join(f"{i}:{x}" for i, x in enumerate(h) if x)[:200]
            + f" | PROC 0x600 {rd(0x05140600):#010x} 0x604 {rd(0x05140604):#010x} PNL 0x144 {rd(0x051C0144):#x} 0x304 {rd(0x051C0304):#x}")
    wr_logged(0x05140508, 0x04400000, "back to the HY320 firmware value")





def fix720():
    """after q720 on a minimal set: add 12's blocks one by one (then the S2 HY320 words again) and read the areas"""
    ms = json.load(open("/data/bench/minset.json"))
    zoom = json.load(open("/data/bench/zoom720.json"))
    for g in ["NRC", "PROC", "SCL", "PNL", "DEI", "BORDER"]:
        for a, v, b in ms[g]:
            if g in ("NRC", "DEI") and 0x04000000 <= v < 0x08000000 and (v & 0xFF) == 0:
                continue  # buffer addresses stay as they are
            wr(a, v)
        for a, v, _ in zoom:
            wr(a, v)
        wr(SC + 0x014, 1)
        time.sleep(0.1)
        areas(f"+ 12's {g} words, S2 HY320 words again")


for step in sys.argv[2:]:
    {"q720": q720, "nrc2": nrc2, "chroma": chroma, "fix720": fix720}[step]()
log("R5 DONE")
