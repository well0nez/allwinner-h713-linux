#!/usr/bin/env python3
"""59 X5 (vertical): replay the firmware's PHY reset as traced in the normal boot (relock1.log 1.956-1.973 s) and its
lock step (3.591-3.599 s): enables off, +0x1b 0x15, EQ off; port select 0x8f1 0x81 with +0x1b 0x01 and EQ on; 0x8f1
back to 0x80; wait for TMDS (RX_CTL 0x9ab = 0x3c); enables on; lock-step bytes. x5k.py LOG"""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd  # noqa: E402
C, L = 0x06800000, 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; m[o] = v; r = m[o]
    log(f"W8 {a:#010x} = {v:02x} (was {old:02x}) read back {r:02x}")
def signs(label):
    t = bytes(rb(L + 0x28 + i) for i in range(0x18)); h = lambda o: t[o] << 8 | t[o + 1]  # noqa: E731
    log(f"SIGNS {label}: h {h(0)}/{h(2)} v {h(0xc)}/{h(0xe)} 001={rb(L + 1):02x} 007={rb(L + 7):02x} 9ab={rb(C + 0x9ab):02x} 1a9={rb(L + 0x1a9):02x} 1ab={rb(L + 0x1ab):02x} 37a={rb(L + 0x37a):02x} | CAP 104={rd(0x06940104):08x} 548={rd(0x06940548):08x} fe64={rd(0x0514fe64):08x}")
openlog(sys.argv[1])
signs("start")
log("PHY reset, step a")
for o in (0x006, 0x00c, 0x00d, 0x010, 0x012):
    wb(L + o, 0)
wb(L + 0x01b, 0x15); wb(L + 0x01d, rb(L + 0x1d) | 1); wb(L + 0x040, 0x07); wb(L + 0x1b5, 0x21)
time.sleep(0.009)
log("step b: port select 0x81, +0x1b 0x01, EQ on")
wb(C + 0x8f1, 0x81); wb(L + 0x01b, 0x01); wb(L + 0x1b5, 0x31)
time.sleep(0.008)
log("step c: port select back to 0x80")
wb(C + 0x8f1, 0x80)
signs("after the PHY reset")
t0 = time.monotonic()
while time.monotonic() - t0 < 4 and rb(C + 0x9ab) != 0x3c:
    time.sleep(0.005)
signs(f"TMDS wait ended after {time.monotonic() - t0:.3f} s")
for o, v in ((0x006, 0x6a), (0x00c, 0x87), (0x00d, 0x8f), (0x010, 0x4d), (0x012, 0x27)):
    wb(L + o, v)
time.sleep(0.008)
wb(L + 0x000, rb(L) & ~0x40); wb(L + 0x01d, rb(L + 0x1d) & ~1); wb(L + 0x040, 0x00); wb(L + 0x0a1, 0xfc)
for k in range(12):
    time.sleep(0.1 if k < 6 else 0.5); signs(f"lock step +{k}")
