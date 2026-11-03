#!/usr/bin/env python3
"""Resume re-init after a standby, firmware never started (spec side, 2026-11-04). rsm.py LOG BEFORE_LOG STEPS
STEPS (comma list, in this order): ccu = write back every CCU word 0x02001d00..0x02001dff and the PLLs 0x02001040,
0x02001048, 0x02001050, 0x02001068 that differ from the BEFORE_LOG snapshot (wdump format); tvtop = the TV-top
sequence (+4 0x01111117, +8 0x404, +0 0x00111111, 12 ms, all 0, 12 ms, again); tvtop504 = +8 0x504; ppu = power the
TVFE/TVCAP domains on if they are not; cap = read CAP 0x06940000 and RX_CTL 0x068008fc (each logged before).
Every write and every first read is logged and fsynced first (blog.py)."""
import re, sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
openlog(sys.argv[1])
before = {}
for l in open(sys.argv[2]):
    m = re.search(r"DUMP \S+ w (0x[0-9a-f]+): (.*)", l)
    if m:
        a = int(m.group(1), 16)
        for i, v in enumerate(m.group(2).split()):
            before[a + 4 * i] = int(v, 16)
steps = sys.argv[3].split(",")
def W(a, v):
    log(f"W32 {a:#010x} = {v:08x} (was {rd(a):08x})"); wr(a, v); log(f"   read back {rd(a):08x}")
for st in steps:
    log(f"RSM step {st}")
    if st == "ccu":
        for a in [0x02001040, 0x02001048, 0x02001050, 0x02001068] + list(range(0x02001d00, 0x02001e00, 4)):
            if a in before and rd(a) != before[a]:
                W(a, before[a]); time.sleep(0.012)
    elif st == "tvtop":
        for vals in ((0x01111117, 0x404, 0x00111111), (0, 0, 0), (0x01111117, 0x404, 0x00111111)):
            W(0x06e00004, vals[0]); W(0x06e00008, vals[1]); W(0x06e00000, vals[2]); time.sleep(0.012)
    elif st == "tvtop504":
        W(0x06e00008, 0x504)
    elif st == "ppu":
        for d, n in ((1, "tvfe"), (2, "tvcap")):
            b = 0x07001014 + 0x80 * d
            s = rd(b + 0x10)
            log(f"PPU {n} status {s:08x} ctrl {rd(b + 0x0c):08x}")
            if (s & 0x30000) != 0x10000:
                W(b + 0x0, 8); W(b + 0x4, 0x00080808); W(b + 0x8, 0x00080808); W(b + 0x0c, 1)
                t0 = time.monotonic()
                while time.monotonic() - t0 < 0.1 and (rd(b + 0x10) & 0x30000) != 0x10000:
                    time.sleep(0.001)
                log(f"PPU {n} status now {rd(b + 0x10):08x}")
    elif st == "cap":
        log("BEFORE-READ CAP 0x06940000")
        log(f"CAP 0x06940000 = {rd(0x06940000):08x}, 0x104 = {rd(0x06940104):08x}")
        log("BEFORE-READ RX_CTL 0x068008fc (8-bit)")
        m, o = _page(0x068008fc)
        log(f"RX_CTL 0x068008fc = {m[o]:02x}")
log("RSM done")
