#!/usr/bin/env python3
"""59 X1/H11 on the normal boot (firmware running): is RX_LINK writable here? Packet reader: type to +0x112, packet
from +0x1c0..+0x1de; the old selector is put back."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog  # noqa: E402
L = 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); old = m[o]; m[o] = v; r = m[o]
    log(f"W8 {a:#010x} = {v:02x} (was {old:02x}) read back {r:02x}{'' if r == v else ' DIFFERENT'}")
    return old
openlog(sys.argv[1])
old = rb(L + 0x112)
for t in (0x82, 0x84, 0x83, 0x81):
    wb(L + 0x112, t)
    time.sleep(0.005)
    log(f"type {t:02x}: +0x1c0..1de {bytes(rb(L + 0x1c0 + i) for i in range(31)).hex()}")
wb(L + 0x112, old)
