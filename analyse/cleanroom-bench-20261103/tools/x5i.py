#!/usr/bin/env python3
"""59 X5 follow-up 8: the remaining non-status RX_LINK differences to the locked state, one at a time; watch V."""
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
    log(f"SIGNS {label}: h {h(0)}/{h(2)} v {h(0xc)}/{h(0xe)} 007={rb(L + 7):02x} CAP 104={rd(0x06940104):08x} 548={rd(0x06940548):08x} fe64={rd(0x0514fe64):08x}")
openlog(sys.argv[1])
signs("start")
for o, v in ((0x0a1, 0xfc), (0x092, 0x10), (0x105, 0x20), (0x10e, 0x90), (0x110, 0x01), (0x040, 0x17), (0x004, 0xce)):
    wb(L + o, v)
    for k in range(3):
        time.sleep(0.4); signs(f"after {o:#05x} +{0.4 * (k + 1):.1f}")
wb(L + 0x007, 0xff)
time.sleep(0.3); signs("after clearing +0x007")
