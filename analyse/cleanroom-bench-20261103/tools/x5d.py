#!/usr/bin/env python3
"""59 X5 follow-up 3: RX_LINK with 32-bit aligned accesses (byte writes were ignored). Logged/fsynced first."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
LINK = 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
openlog(sys.argv[1])
log("BEFORE 32-bit read 0x06840374")
v = rd(LINK + 0x374)
log(f"0x06840374 = {v:08x} (bytes 374..377 by 8-bit: {' '.join(f'{rb(LINK + 0x374 + i):02x}' for i in range(4))})")
nv = (v & ~0x00ff0000) | 0x00020000
log(f"BEFORE 32-bit write 0x06840374 = {nv:08x}")
wr(LINK + 0x374, nv)
log(f"read back {rd(LINK + 0x374):08x}; byte 376 = {rb(LINK + 0x376):02x}")
log("BEFORE 32-bit read 0x06840000")
v0 = rd(LINK)
log(f"0x06840000 = {v0:08x}")
wr(LINK, v0 & ~0xff)
log(f"after 32-bit write of byte 0 = 0: {rd(LINK):08x}")
time.sleep(0.2)
log(f"timing 28..3f {bytes(rb(LINK + 0x28 + i) for i in range(0x18)).hex()} 37a={rb(LINK + 0x37a):02x}")
