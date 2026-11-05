#!/usr/bin/env python3
"""Q-HDMI-2 function: with the receiver locked and the capture running, gate one clock for 0.5 s and watch the lock
(RX_LINK timing) and the capture frame count; restore; next. gatefn.py LOG GATE.."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
L = 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
import mmap, os
_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
SL = [mmap.mmap(_fd, 0x1FF000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=a) for a in (0x4B100000, 0x4B2FF000, 0x4B4FE000)]
def mark():
    for s in SL:
        s[540 * 1920:540 * 1920 + 16] = b"\xa5" * 16
def written():
    return sum(1 for s in SL if s[540 * 1920] != 0xA5)
def st():
    t = bytes(rb(L + 0x28 + i) for i in range(0x18)); h = lambda o: t[o] << 8 | t[o + 1]  # noqa: E731
    return (h(0), h(2), h(0xc), h(0xe)), rd(0x06940104) >> 16
openlog(sys.argv[1])
for g in sys.argv[2:]:
    r, b = g.split(":"); a = 0x02001000 + int(r, 16); b = int(b)
    t0, f0 = st(); old = rd(a)
    log(f"GATEFN {a:#010x} bit {b} off; before: timing {t0} frame {f0}")
    wr(a, old & ~(1 << b)); time.sleep(0.05); mark(); time.sleep(0.45)
    t1, f1 = st(); w1 = written()
    wr(a, old); time.sleep(0.05); mark(); time.sleep(0.45)
    t2, f2 = st(); w2 = written()
    log(f"GATEFN {a:#010x} bit {b}: during 0.5 s off: timing {t1}, frames +{(f1 - f0) & 0xffff}, ring slots written {w1}/3; 0.5 s after restore: timing {t2}, frames +{(f2 - f1) & 0xffff}, ring slots written {w2}/3")
