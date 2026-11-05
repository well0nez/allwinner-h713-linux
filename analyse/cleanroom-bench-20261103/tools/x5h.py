#!/usr/bin/env python3
"""59 X5 follow-up 7: RX_CTL 0x9b1..0x9bd (no-signal values of the normal boot) on top of the X5 state; watch."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd  # noqa: E402
CTL, L = 0x06800000, 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; log(f"W8 {a:#010x} = {v:02x} (was {old:02x})"); m[o] = v; r = m[o]
    if r != v: log(f"   read back {r:02x} DIFFERENT")
def signs(label):
    t = bytes(rb(L + 0x28 + i) for i in range(0x18)); h = lambda o: t[o] << 8 | t[o + 1]  # noqa: E731
    log(f"SIGNS {label}: 37a={rb(L + 0x37a):02x} 007={rb(L + 0x007):02x} timing htotal {h(0)} hact {h(2)} hblank {h(4)} vtotal {h(0xc)} vact {h(0xe)} | CAP 104={rd(0x06940104):08x} 548={rd(0x06940548):08x} | PROC fe64={rd(0x0514fe64):08x}")
openlog(sys.argv[1])
signs("start")
for a, v in ((0x9b1, 0x6a), (0x9b2, 0x20), (0x9b3, 0x04), (0x9b4, 0xb4), (0x9b5, 0x73), (0x9bb, 0xff), (0x9bd, 0x0f)):
    wb(CTL + a, v)
for k in range(6):
    time.sleep(0.5); signs(f"+{0.5 * (k + 1):.1f} s")
