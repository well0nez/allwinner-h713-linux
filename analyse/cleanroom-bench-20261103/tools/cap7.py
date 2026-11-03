#!/usr/bin/env python3
"""59 X6 with a source: program the capture block CAP (0x06940000) from Linux with an own ring, firmware never started;
leave the outputs on with "keep" (for X7).
Target words: the HY320 normal-boot state with HDMI 1080p60 (2026-11-03, r2-normal.log), status words left out, the
address tables pointing at an own ring inside the reserved region 0x4b100000.. (the never-started co-processor's).
cap7.py LOG [keep]"""
import os
import struct
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

CAP = 0x06940000
openlog(sys.argv[1])
Y = [0x4B100000, 0x4B2FF000, 0x4B4FE000]
C = [y + 0x5FD000 for y in Y]
SLOT = 0x1FF000
STATE = {  # offset: value (normal boot, HDMI 1080p60, HY320)
    0x004: 0x00050000, 0x008: 0x01000300,
    0x400: 0x00000021,
    0x440: 0xE0000000, 0x444: 0x00290438, 0x448: 0x00B70780, 0x44C: 0x47022888,
    0x450: 0x00800020, 0x454: 0x80000002, 0x458: 0x80000002,
    0x460: 0x0C000000, 0x464: 0x00000780, 0x468: 0x00000438, 0x46C: 0x801A4749,
    0x4C0: 0x50000000, 0x4C4: 0x00800020, 0x4C8: 0x88000002, 0x4CC: 0x0E000000,
    0x4D0: 0x08000000, 0x4D4: 0x16000900, 0x4D8: 0x42000002, 0x4DC: 0x00100780,
    0x4E0: 0x00100438, 0x4E4: 0xC0800000,
    0x800: 0x0C000C00, 0x804: 0x04000000, 0x808: 0x04000400, 0x81C: 0x04000000,
    0x820: 0x04000400, 0x824: 0x0000000B, 0x830: 0x02000200, 0x834: 0x009405B9, 0x838: 0x0CD901B3,
    0x83C: 0x0F100417, 0x840: 0x0FA00C49, 0x844: 0x00000417, 0x84C: 0x04000C00,
    0x858: 0x0C020000, 0x85C: 0x0C020C02, 0x864: 0x42010000, 0x868: 0x06000000, 0x86C: 0x00000780,
    0x870: 0x00000438, 0x874: 0x07800438, 0x87C: 0x08010000,
    0x880: 0x00000020, 0x884: 0x04000001, 0x888: 0x07800000, 0x88C: 0x04380000,
    0x8A4: 0x000F0101, 0x8A8: 0x07800000, 0x8AC: 0x04380000, 0x8B0: 0x01000100,
    0x8C0: 0x00000003, 0x8C8: 0x00000003, 0x8D0: 0x60000300,
    0x924: 0x00780078, 0x928: 0x60020438,
    0x964: 0x00780078, 0x968: 0x60020438,
    0x970: 0x0C000000, 0x974: 0x01000100, 0x978: 0x00000003,
}
for i, y in enumerate(Y + [Y[2]] * 3):
    STATE[0x8F0 + 4 * i] = y >> 4
for i, c in enumerate(C + [C[2]] * 3):
    STATE[0x930 + 4 * i] = c >> 4

# the ring: fill with a marker so any write shows
ring = []
for a in Y + C:
    m, off = map_ram(a, SLOT)
    m[off:off + SLOT] = b"\x5a" * SLOT
    ring.append((a, m, off))
log(f"CAP7 ring filled with 0x5a: luma {[hex(a) for a in Y]}, chroma {[hex(a) for a in C]}")


def ring_changed():
    out = []
    for a, m, off in ring:
        n = 0
        for probe in range(0, SLOT, 4096 * 16):
            if m[off + probe] != 0x5A:
                n += 1
        out.append(n)
    return out


def slot_luma():
    out = []
    for a, m, off in ring[:3]:
        v = [m[off + p] for p in range(0, 1920 * 1080, 1920 * 8 + 24)]
        out.append(f"{sum(v) / len(v):.1f}/{min(v)}/{max(v)}")
    return out


def snap(label):
    words = {o: rd(CAP + o) for o in (0x000, 0x100, 0x104, 0x400, 0x540, 0x548, 0x874, 0x928, 0x968, 0xA00, 0xA04,
                                     0xA0C, 0xA20, 0xA24, 0xA28)}
    log(f"CAP7 {label}: " + " ".join(f"{o:03x}={v:08x}" for o, v in words.items()) +
        f" | 0x05600320 {rd(0x05600320):08x} 0x324 {rd(0x05600324):08x} | ring pages changed {ring_changed()}"
        f" | slot luma mean/min/max {slot_luma()}")


if len(sys.argv) > 2 and sys.argv[2] == "tvtop504":
    old = rd(0x06E00008)
    wr(0x06E00008, 0x504)
    log(f"CAP7 TVTOP +8 {old:#x} -> {rd(0x06E00008):#x}")
snap("before")
bad = []
for o, v in sorted(STATE.items()):
    wr(CAP + o, v)
    r = rd(CAP + o)
    if r != v:
        bad.append(f"{o:03x}:{v:08x}->{r:08x}")
log(f"CAP7 {len(STATE)} words written; read back different: {len(bad)}: {' '.join(bad)}")
snap("programmed, outputs off")
time.sleep(0.5)
snap("programmed +0.5 s")
wr(CAP + 0x928, 0xE0020438)
wr(CAP + 0x968, 0xE0020438)
log("CAP7 outputs on (bit 31 of 0x928 and 0x968)")
wr(CAP + 0x000, 0x3A7B)
log(f"CAP7 top word +0x000 = {rd(CAP):08x} (0x3a7b as in the normal boot: starts the capture)")
for k in range(6):
    time.sleep(0.5)
    snap(f"outputs on +{0.5 * (k + 1):.1f} s")
if "keep" in sys.argv[2:]:
    log("CAP7 outputs left on")
    sys.exit(0)
wr(CAP + 0x928, rd(CAP + 0x928) & ~0x80000000)
wr(CAP + 0x968, rd(CAP + 0x968) & ~0x80000000)
time.sleep(0.04)
snap("outputs off again")
log("CAP7 DONE")
