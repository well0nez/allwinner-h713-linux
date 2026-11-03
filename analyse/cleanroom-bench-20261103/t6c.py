#!/usr/bin/env python3
"""95 S1-T6 / T1 expected histograms with the owner's third curve on (0x051c00e8 = 0x14f00000) and with the LUT off.
Needs the aligned RGB-over-video 12 state (r10.py setup + align3.py).  t6c.py LOG"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

PNL = 0x051C0000
E8 = PNL + 0xE8
PORTS = (0x05208000, 0x05208800, 0x05209000)
A = 0x4B200000
V = 0x6CA00000
openlog(sys.argv[1])
_m, _o = map_ram(A, 7680 * 1080)
_vm, _vo = map_ram(V, 1920 * 1080 * 3 // 2)
curve = json.load(open("/data/bench/pidcurves.json"))[2]


def hist():
    time.sleep(0.12)
    h = [rd(PNL + 0x380 + 4 * i) for i in range(32)]
    return " ".join(f"{i}:{v}" for i, v in enumerate(h) if v)


def probes():
    a, b = rd(PNL + 0x144), rd(PNL + 0x304)
    f = lambda v: f"{v >> 20 & 0x3ff}/{v & 0x3ff}/{v >> 10 & 0x3ff}"  # R/G/B
    return f"0x0144 {f(a)} 0x0304 {f(b)}"


def yframe(y, u=128, v=128):
    _vm[_vo:_vo + 1920 * 1080] = bytes([y]) * (1920 * 1080)
    _vm[_vo + 1920 * 1080:_vo + 1920 * 1080 * 3 // 2] = bytes([u, v]) * (960 * 540)


def upload():
    e8 = rd(E8)
    wr(E8, e8 | (1 << 30))
    for base, s in zip(PORTS, curve):
        for i in range(512):
            wr(base + 4 * i, (s[2 * i] & 0xFFF) | ((s[2 * i + 1] & 0xFFF) << 12))
    wr(E8, e8 & ~(1 << 30))
    wr(E8, rd(E8) ^ (1 << 28))


wr(0x051C0268, (3 << 16) | 3)  # both probes on video pixel (3, 3)
log(f"T6C start: e8 {rd(E8):#010x}, dither {rd(0x051C00EC):#010x}, levels 5bc {rd(0x051405BC):#x} d34 {rd(0x05140D34):#x}")
upload()
for state in ("curve", "off"):
    if state == "curve":
        wr(E8, (rd(E8) & 0x10000000) | 0x04F00000)
    else:
        wr(E8, rd(E8) & ~(1 << 26))
    log(f"T6C ---- {state}: e8 {rd(E8):#010x}")
    wr(PNL + 0x6C, 0x39000000)  # video alone (T1)
    for name, y in (("black Y16", 16), ("white Y235", 235), ("P3 grey Y126", 126)):
        yframe(y)
        log(f"T6C {state} T1 {name}: {hist()}; {probes()}")
    yframe(16)  # S1-T6: white RGB over the black video
    _m[_o:_o + 7680 * 1080] = b"\xff" * (7680 * 1080)
    wr(PNL + 0x6C, 0x29000000)
    for a in (0xFF, 0x80, 0x40, 0x00):
        wr(PNL + 0x70, (rd(PNL + 0x70) & ~0xFF) | a)
        log(f"T6C {state} S1-T6 alpha {a:#04x}: {hist()}; {probes()}")
    wr(PNL + 0x70, (rd(PNL + 0x70) & ~0xFF) | 0xFF)
wr(0x051C0268, 0x076C000A)
log("T6C done")
