#!/usr/bin/env python3
"""Q-PQ-11: the owner's third curve (ProjectID_0x0030.TSE state 3, decoded per 40 §6) on the probe words.
Needs the 12 state; runs on the video plane alone with neutral levels, white balance neutral, dither 0.
For each Y frame: 0x051c0144 = the LUT input (10 bit, per channel), 0x051c0304 = the LUT output; compare with the
decoded sample at that input (12 bit; the probe shows 10 bits).  q11.py LOG"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

PNL = 0x051C0000
E8 = PNL + 0xE8
PORTS = (0x05208000, 0x05208800, 0x05209000)
V = 0x6CA00000
openlog(sys.argv[1])
_vm, _vo = map_ram(V, 1920 * 1080 * 3 // 2)
curve = json.load(open("/data/bench/pidcurves.json"))[2]


def ch(v):
    return v >> 20 & 0x3FF, v & 0x3FF, v >> 10 & 0x3FF


def yframe(y):
    _vm[_vo:_vo + 1920 * 1080] = bytes([y]) * (1920 * 1080)
    _vm[_vo + 1920 * 1080:_vo + 1920 * 1080 * 3 // 2] = b"\x80" * (1920 * 540)
    time.sleep(0.12)


wr(PNL + 0x6C, 0x39000000)
for a, v in ((0x051C00D4, 0), (0x051C00D8, 0), (0x051C00DC, 0x08000800), (0x051C00E0, 0x08000000),
             (0x051405BC, 0x80), (0x05140D34, 0x09580958), (0x05140D38, 0x00400958), (0x05140508, 0x04400000),
             (0x051C00EC, 0), (0x051C0268, (3 << 16) | 3)):
    wr(a, v)
# upload into the hidden bank, then show it
e8 = rd(E8) | (1 << 26) | (0xF << 20)
wr(E8, e8 | (1 << 30))
for base, s in zip(PORTS, curve):
    for i in range(512):
        wr(base + 4 * i, (s[2 * i] & 0xFFF) | ((s[2 * i + 1] & 0xFFF) << 12))
wr(E8, e8 & ~(1 << 30))
wr(E8, rd(E8) ^ (1 << 28))
log(f"Q11 third curve uploaded; e8 {rd(E8):#010x}; dither {rd(0x051C00EC):#x}; probe at {rd(0x051C0268):#010x}")
worst = 0
for y in (16, 24, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 235):
    yframe(y)
    i = ch(rd(PNL + 0x144))
    o = ch(rd(PNL + 0x304))
    want = tuple(curve[c][i[c]] >> 2 for c in range(3))
    d = tuple(o[c] - want[c] for c in range(3))
    worst = max(worst, max(abs(x) for x in d))
    log(f"Q11 Y {y:3d}: input R/G/B {i}, output {o}, decoded sample/4 {want}, difference {d}")
log(f"Q11 largest difference {worst} (10-bit steps) over 16 grey levels x 3 channels")
wr(E8, rd(E8) & ~(1 << 26))
wr(0x051C00EC, 0x14141400)
wr(0x051C0268, 0x076C000A)
log("Q11 restored: LUT off, dither 0x14141400, probe (1900, 10)")
