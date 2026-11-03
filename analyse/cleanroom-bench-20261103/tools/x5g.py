#!/usr/bin/env python3
"""59 X5 follow-up 6: the 0x06841000 view's bytes that differ from the normal boot (+0x001 = 0x05, +0x014..0x017 =
01 ff ff ff), then the RX_LINK write test."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog  # noqa: E402
L, L2 = 0x06840000, 0x06841000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; log(f"W8 {a:#010x} = {v:02x} (was {old:02x})"); m[o] = v; r = m[o]
    log(f"   read back {r:02x}{'' if r == v else ' DIFFERENT'}")
openlog(sys.argv[1])
wb(L + 0x376, 0x02)
for o, v in ((0x001, 0x05), (0x014, 0x01), (0x015, 0xff), (0x016, 0xff), (0x017, 0xff)):
    wb(L2 + o, v)
    time.sleep(0.05)
    wb(L + 0x376, 0x02)
time.sleep(0.2)
log(f"link 000..00f {bytes(rb(L + i) for i in range(16)).hex()} 37a={rb(L + 0x37a):02x} timing {bytes(rb(L + 0x28 + i) for i in range(0x18)).hex()}")
log(f"link2 000..01f {bytes(rb(L2 + i) for i in range(32)).hex()}")
