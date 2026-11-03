#!/usr/bin/env python3
"""Q-HDMI-2: which of the clocks the kernel's cleanup turns off does an ARM read of the receiver need? For each gate:
clear it, log + fsync, read RX_CTL 0x068008fc and RX_LINK 0x06840000 (8-bit), set it again. A hang ends in the bench
watchdog reset; the last log line names the gate. gatetest.py LOG GATE..  (GATE = hexreg:bit)"""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
openlog(sys.argv[1])
for grp in sys.argv[2:]:
    saved = []
    for g in grp.split("+"):
        r, b = g.split(":"); a = 0x02001000 + int(r, 16); b = int(b)
        old = rd(a); saved.append((a, old))
        wr(a, old & ~(1 << b)); time.sleep(0.01)
        log(f"GATE {a:#010x} bit {b} cleared ({old:08x} -> {rd(a):08x})")
    log(f"GATES {grp} off; BEFORE-READ 0x068008fc, 0x06840000")
    m, o = _page(0x068008fc); v1 = m[o]
    m, o = _page(0x06840000); v2 = m[o]
    log(f"GATES {grp} off: read ok 0x068008fc={v1:02x} 0x06840000={v2:02x}")
    for a, old in reversed(saved):
        wr(a, old)
    time.sleep(0.01)
    log(f"GATES {grp} restored")
