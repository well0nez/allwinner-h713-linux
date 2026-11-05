#!/usr/bin/env python3
"""59 X5 follow-up 4: SYS_CFG 0x03000090 (0xe in the normal boot, 0 on the bench) and the link write test."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
LINK = 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; log(f"W8 {a:#010x} = {v:02x} (was {old:02x})"); m[o] = v; r = m[o]
    log(f"   read back {r:02x}{'' if r == v else ' DIFFERENT'}")
openlog(sys.argv[1])
log(f"0x03000090 = {rd(0x03000090):08x}")
log("W32 0x03000090 = 0000000e"); wr(0x03000090, 0xe); log(f"   read back {rd(0x03000090):08x}")
time.sleep(0.1)
wb(LINK + 0x376, 0x02)
log(f"link 000..00f {bytes(rb(LINK + i) for i in range(16)).hex()} 37a={rb(LINK + 0x37a):02x} timing {bytes(rb(LINK + 0x28 + i) for i in range(0x18)).hex()}")
