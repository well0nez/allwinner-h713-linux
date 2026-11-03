#!/usr/bin/env python3
"""55 slot rotation facts (bench boot, capture running from hdmi-clean.sh): write index 0xa0c against the frame/line
counter 0x104; which ring slot is being written; which CAP words change at frame rate; GIC pending bits with the
capture running and stopped. Read-mostly; the only writes are marker bytes into the own ring and the output enables.
cap8.py LOG"""
import mmap, os, struct, sys, time
sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402
CAP = 0x06940000
Y = [0x4B100000, 0x4B2FF000, 0x4B4FE000]
openlog(sys.argv[1])
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
slots = [mmap.mmap(fd, 0x1FF000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=a) for a in Y]
capm = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=CAP)
def cw(o):
    return struct.unpack_from("<I", capm, o)[0]
# 1. write index against the counter, 300 ms at full rate
t0 = time.monotonic(); prev = None; tr = []
while time.monotonic() - t0 < 0.3:
    c, a = cw(0x104), cw(0xa0c)
    if prev is None or (c >> 16) != (prev[0] >> 16) or a != prev[1]:
        tr.append((time.monotonic() - t0, c, a))
    prev = (c, a)
log("WIDX transitions (t, frame, line, a0c): " + " ".join(f"{t * 1000:.2f}ms:{c >> 16}/{c & 0xffff}/{a}" for t, c, a in tr[:40]))
# 2. which slot is written: markers on rows 0, 540, 1079 of every slot; poll until each marker is overwritten
for row in (0, 540, 1079):
    for s in slots:
        s[row * 1920:row * 1920 + 16] = b"\xa5" * 16
    t0 = time.monotonic(); hit = {}
    while len(hit) < 3 and time.monotonic() - t0 < 0.2:
        for i, s in enumerate(slots):
            if i not in hit and s[row * 1920] != 0xA5:
                c, a = cw(0x104), cw(0xa0c)
                hit[i] = (time.monotonic() - t0, c >> 16, c & 0xffff, a)
    log(f"SLOT row {row}: " + " ".join(f"slot{i} after {v[0] * 1000:.2f} ms at frame {v[1]} line {v[2]} a0c {v[3]}" for i, v in sorted(hit.items(), key=lambda kv: kv[1][0])))
# 3. CAP words that change within 50 ms
a = [cw(o) for o in range(0, 0x1000, 4)]; time.sleep(0.05); b = [cw(o) for o in range(0, 0x1000, 4)]
log("CAP words changing in 50 ms: " + " ".join(f"{4 * i:03x}:{x:08x}>{y:08x}" for i, (x, y) in enumerate(zip(a, b)) if x != y))
# 4. GIC distributor pending bits (GICD 0x03021000 + 0x200), capture running / outputs off / back on
def pend():
    return [rd(0x03021200 + 4 * i) for i in range(1, 8)]  # SPI 0..223 (ids 32..255)
def spis(p):
    return [32 * (i + 1) + b - 32 for i, w in enumerate(p) for b in range(32) if w >> b & 1]
ps = [spis(pend()) for _ in range(20)]
log("GIC pending SPIs, capture running (20 reads): " + " ".join(sorted({f"{x}" for p in ps for x in p}, key=int)))
wr(CAP + 0x928, rd(CAP + 0x928) & ~0x80000000); wr(CAP + 0x968, rd(CAP + 0x968) & ~0x80000000)
time.sleep(0.1)
ps = [spis(pend()) for _ in range(20)]
log(f"GIC pending SPIs, outputs off (20 reads; 0x104={cw(0x104):08x}): " + " ".join(sorted({f"{x}" for p in ps for x in p}, key=int)))
wr(CAP + 0x928, rd(CAP + 0x928) | 0x80000000); wr(CAP + 0x968, rd(CAP + 0x968) | 0x80000000)
time.sleep(0.1)
log(f"outputs back on; 0x104={cw(0x104):08x} a0c={cw(0xa0c)}")
