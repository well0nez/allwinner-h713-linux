#!/usr/bin/env python3
"""59 X5 follow-up: RX_LINK ignored writes after X5. Try the port-1 page bytes of RX_CTL 0x9b1..0x9bd (no-signal
values), then test one RX_LINK write (+0x376) after each step."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd  # noqa: E402
CTL, LINK = 0x06800000, 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; log(f"W8 {a:#010x} = {v:02x} (was {old:02x})"); m[o] = v; r = m[o]
    log(f"   read back {r:02x}{'' if r == v else ' DIFFERENT'}")
def probe(label):
    wb(LINK + 0x376, 0x02)
    log(f"PROBE {label}: link 000..00f {bytes(rb(LINK + i) for i in range(16)).hex()} 37a={rb(LINK + 0x37a):02x} "
        f"timing {bytes(rb(LINK + 0x28 + i) for i in range(0x18)).hex()} ctl 9a9..9bd {bytes(rb(CTL + 0x9a9 + i) for i in range(0x15)).hex()}")
openlog(sys.argv[1])
probe("start")
for a, v in ((0x9b1, 0x6a), (0x9b2, 0x20), (0x9b3, 0x04), (0x9b4, 0xb4), (0x9b5, 0x73), (0x9bb, 0xff), (0x9bd, 0x0f)):
    wb(CTL + a, v)
time.sleep(0.2)
probe("after ctl 0x9b1..0x9bd")
time.sleep(1)
probe("+1 s")
