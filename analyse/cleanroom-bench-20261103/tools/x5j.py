#!/usr/bin/env python3
"""59 X5 (vertical): the firmware's writes at the moment of lock (normal boot relock trace relock1.log, 3.599 s):
+0x000 bit 6 clear, +0x01d bit 0 clear (video unmute), +0x022 bit 0, +0x040 = 0, +0x0a1 = 0xfc, +0x17e..0x182 = 0,
+0x3c5 = 0x02; watch the timing. x5j.py LOG [watch-only]"""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd  # noqa: E402
L = 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; m[o] = v; r = m[o]
    log(f"W8 {a:#010x} = {v:02x} (was {old:02x}) read back {r:02x}")
def signs(label):
    t = bytes(rb(L + 0x28 + i) for i in range(0x18)); h = lambda o: t[o] << 8 | t[o + 1]  # noqa: E731
    log(f"SIGNS {label}: h {h(0)}/{h(2)} v {h(0xc)}/{h(0xe)} 000={rb(L):02x} 001={rb(L + 1):02x} 007={rb(L + 7):02x} 01d={rb(L + 0x1d):02x} 022={rb(L + 0x22):02x} 37a={rb(L + 0x37a):02x} | CAP 104={rd(0x06940104):08x} 548={rd(0x06940548):08x} fe64={rd(0x0514fe64):08x}")
openlog(sys.argv[1])
signs("start")
if "watch-only" not in sys.argv[2:]:
    for o, v in ((0x000, rb(L) & ~0x40), (0x01d, rb(L + 0x1d) & ~1), (0x022, rb(L + 0x22) | 1), (0x040, 0x00),
                 (0x0a1, 0xfc), (0x17e, 0), (0x180, 0), (0x181, 0), (0x182, 0), (0x3c5, 0x02)):
        wb(L + o, v)
for k in range(10):
    time.sleep(0.3); signs(f"+{0.3 * (k + 1):.1f} s")
