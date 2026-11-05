#!/usr/bin/env python3
"""59 X5 (1): normal boot, read-only. Sample RX_CTL pages 8/9, RX_LINK 0x000..0x7ff and 0x06841000..0x7ff (8-bit) plus
CAP 0x104/0x548/0x874 and PROC_LOCK fe64 as fast as possible for DUR s; log every change with its time.
relock.py LOG DUR"""
import mmap, os, struct, sys, time
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
def mp(a, n):
    return mmap.mmap(fd, n, mmap.MAP_SHARED, mmap.PROT_READ, offset=a)
ctl = mp(0x06800000, 0x1000); link = mp(0x06840000, 0x1000); link2 = mp(0x06841000, 0x1000)
cap = mp(0x06940000, 0x1000); proc = mp(0x0514f000, 0x1000)
log = open(sys.argv[1], "w"); dur = float(sys.argv[2])
def snap():
    s = {}
    for i in range(0x800, 0xa00):
        s[0x06800000 + i] = ctl[i]
    for i in range(0x800):
        s[0x06840000 + i] = link[i]
        s[0x06841000 + i] = link2[i]
    for o in (0x104, 0x548, 0x874):
        s[0x06940000 + o] = struct.unpack_from("<I", cap, o)[0]
    s[0x0514fe64] = struct.unpack_from("<I", proc, 0xe64)[0]
    return s
t0 = time.monotonic(); prev = snap(); n = 0
log.write(f"0.000 START {len(prev)} values\n")
while time.monotonic() - t0 < dur:
    cur = snap(); n += 1; t = time.monotonic() - t0
    ch = [(k, prev[k], v) for k, v in cur.items() if prev[k] != v]
    if ch:
        log.write(f"{t:.3f} " + " ".join(f"{k:#010x}:{a:x}>{b:x}" for k, a, b in ch) + "\n")
    prev = cur
log.write(f"{time.monotonic() - t0:.3f} END {n} passes\n"); log.close()
