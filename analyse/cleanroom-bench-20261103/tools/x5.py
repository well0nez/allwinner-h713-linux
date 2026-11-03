#!/usr/bin/env python3
"""59 X5: bring the HDMI receiver up from the ARM with the display firmware never started, by replaying the
receiver state measured in the normal boot (2026-11-03 HY320, x1-normal.log no signal, x1-sig.log 1080p60) in the
held order H2 -> H3 -> H4 -> H5, after the clock/TV-top words of the normal boot. Every write is logged and fsynced
first (blog.py); after each step the lock signs are sampled.
x5.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402

CTL, LINK = 0x06800000, 0x06840000


def rb(a):
    m, o = _page(a)
    return m[o]


def wb(a, v):
    m, o = _page(a)
    log(f"W8 {a:#010x} = {v:02x} (was {m[o]:02x})")
    m[o] = v & 0xFF
    r = m[o]
    if r != v:
        log(f"   read back {r:02x}")


def ww(a, v):
    log(f"W32 {a:#010x} = {v:08x} (was {rd(a):08x})")
    wr(a, v)
    r = rd(a)
    if r != v:
        log(f"   read back {r:08x}")


def signs(label):
    t = bytes(rb(LINK + 0x28 + i) for i in range(0x18))
    h = lambda o: t[o] << 8 | t[o + 1]  # noqa: E731
    log(f"SIGNS {label}: 37a={rb(LINK + 0x37a):02x} 377={rb(LINK + 0x377):02x} 001={rb(LINK + 0x001):02x} "
        f"005={rb(LINK + 0x005):02x} 007={rb(LINK + 0x007):02x} 0fc={rb(LINK + 0x0fc):02x} "
        f"1ab..1af={' '.join(f'{rb(LINK + 0x1ab + i):02x}' for i in range(5))} ctl8fc={rb(CTL + 0x8fc):02x} "
        f"| timing 28..3f {t.hex()} (htotal {h(0)} hact {h(2)} vtotal {h(0xc)} vact {h(0xe)}) "
        f"| aux1010={rd(0x07091010):08x} 1014={rd(0x07091014):08x} | CAP 104={rd(0x06940104):08x} "
        f"548={rd(0x06940548):08x} 540={rd(0x06940540):08x} | PROC fe64={rd(0x0514fe64):08x}")


openlog(sys.argv[1])
signs("start")

log("X5 step 0: PLL_VIDEO1, CCU 0x02001d10..d64 and TVTOP as in the normal boot")
ww(0x02001048, rd(0x02001048) | 0x80000000)
time.sleep(0.01)
log(f"PLL_VIDEO1 0x02001048 = {rd(0x02001048):08x} (normal boot: b8006202)")
ccu = {0x10: 0x81000005, 0x18: 0x81000004, 0x24: 0x80000007, 0x28: 0x80000002, 0x2c: 0x80000005,
       0x30: 0x80000004, 0x34: 0x80000004, 0x38: 0x8000000b, 0x40: 0x8000020a, 0x48: 0x80000002,
       0x4c: 0x80000002, 0x50: 0x81000002, 0x58: 0x80000002, 0x5c: 0x8000020b, 0x60: 0x8000020b,
       0x64: 0x00010001}
for o, v in ccu.items():
    ww(0x02001d00 + o, v)
ww(0x06e00008, 0x504)
ww(0x06e0001c, 0x1)
signs("after step 0")
log("X5 step 1: the 0x06841000 view's enables as in the normal boot (+0x001 = 0x05 opens RX_LINK for writes)")
for o, v in ((0x001, 0x05), (0x014, 0x01), (0x015, 0xff), (0x016, 0xff), (0x017, 0xff)):
    wb(0x06841000 + o, v)
signs("after step 1")

log("X5 H2: port select")
for a, v in ((CTL + 0x8f1, 0x80), (CTL + 0x8f2, 0x29), (CTL + 0x8f4, 0x80), (LINK + 0x376, 0x02)):
    wb(a, v)
signs("after H2")

log("X5 configuration: the firmware's no-signal bytes where the bench differs (HDCP, status, mirrors left out)")
NOSIG = [
    (CTL + 0x0a7, 0x01), (CTL + 0x2a7, 0x01), (CTL + 0x3a7, 0x01), (CTL + 0x4a7, 0x01), (CTL + 0x6a7, 0x01),
    (CTL + 0x7a7, 0x01), (CTL + 0xea7, 0x01), (CTL + 0xfa7, 0x01),
    (CTL + 0x8fc, 0x33),
    (CTL + 0xaf1, 0x80), (CTL + 0xaf2, 0x29), (CTL + 0xaf4, 0x80), (CTL + 0xafc, 0x33),
    (CTL + 0xbf1, 0x80), (CTL + 0xbf2, 0x29), (CTL + 0xbf4, 0x80), (CTL + 0xbfc, 0x33),
    (CTL + 0xcf1, 0x80), (CTL + 0xcf2, 0x29), (CTL + 0xcf4, 0x80), (CTL + 0xcfc, 0x33),
    (LINK + 0x000, 0x00), (LINK + 0x008, 0x01), (LINK + 0x016, 0x00), (LINK + 0x01a, 0x00),
    (LINK + 0x040, 0x07), (LINK + 0x064, 0x02), (LINK + 0x065, 0x02),
    (LINK + 0x0a1, 0xf0), (LINK + 0x0b9, 0x71), (LINK + 0x0c1, 0x90), (LINK + 0x0c9, 0x34), (LINK + 0x0fc, 0x37),
    (LINK + 0x186, 0x00), (LINK + 0x187, 0x00),
    (LINK + 0x1a9, 0x3f), (LINK + 0x1aa, 0x40), (LINK + 0x1ab, 0x18), (LINK + 0x1ac, 0x10), (LINK + 0x1ae, 0x80),
    (LINK + 0x1af, 0x0e), (LINK + 0x1b1, 0x04),
    (LINK + 0x310, 0x61), (LINK + 0x35e, 0x3a), (LINK + 0x3c5, 0x02),
]
for a, v in NOSIG:
    wb(a, v)
signs("after the no-signal configuration")
time.sleep(1)
signs("+1 s")

log("X5 H3: PHY out of reset: 0x8fc/afc/bfc/cfc bit 7, RX_LINK +0x1b bits 2 and 4 cleared, +0xfc bit 7, EQ on")
for a, v in ((CTL + 0x8fc, 0xb3), (CTL + 0xafc, 0xb3), (CTL + 0xbfc, 0xb3), (CTL + 0xcfc, 0xb3),
             (LINK + 0x01b, 0x01), (LINK + 0x0fc, 0xb7), (LINK + 0x1b5, 0x31)):
    wb(a, v)
for k in range(4):
    time.sleep(0.25)
    signs(f"after H3 +{0.25 * (k + 1):.2f} s")

log("X5 H4: activation +0x02 = 0x27 then 0x07")
wb(LINK + 0x002, 0x27)
time.sleep(0.01)
wb(LINK + 0x002, 0x07)
for k in range(4):
    time.sleep(0.25)
    signs(f"after H4 +{0.25 * (k + 1):.2f} s")

log("X5 H5: enables as with a locked 1080p60")
for o, v in ((0x006, 0x6a), (0x010, 0x4d), (0x012, 0x27), (0x00c, 0x87), (0x00d, 0x8f)):
    wb(LINK + o, rb(LINK + o) | v)
wb(LINK + 0x00b, rb(LINK + 0x00b) | 1)
for k in range(8):
    time.sleep(0.5)
    signs(f"after H5 +{0.5 * (k + 1):.1f} s")
log("X5 DONE")
