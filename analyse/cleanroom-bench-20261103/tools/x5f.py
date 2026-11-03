#!/usr/bin/env python3
"""59 X5 follow-up 5: other link views (0x06842000.., 0x06843000..) and RX_APLL, 8-bit, each first read logged;
a write test in each link view."""
import sys
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog  # noqa: E402
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; log(f"W8 {a:#010x} = {v:02x} (was {old:02x})"); m[o] = v; r = m[o]
    log(f"   read back {r:02x}{'' if r == v else ' DIFFERENT'}")
openlog(sys.argv[1])
for base in (0x06840800, 0x06842000, 0x06843000, 0x06844000, 0x06848000):
    log(f"BEFORE-READ {base:#010x} 8-bit")
    v = bytes(rb(base + i) for i in range(0x40))
    log(f"  {base:#010x}: {v.hex()} | +376 {rb(base + 0x376):02x} +37a {rb(base + 0x37a):02x}")
    wb(base + 0x376, 0x02)
log("BEFORE-READ RX_APLL 0x06880000 8-bit")
log("  " + bytes(rb(0x06880000 + i) for i in range(0x20)).hex())
