#!/usr/bin/env python3
"""Q-HDMI-1: the minimal receiver set of 50 §9 (L, C, no-signal groups b, c, e) written with no pauses, then the time
to lock (RX_LINK +0x28..0x3f = 2200/1920/1125/1080) polled every 2 ms; then the capture writes of 55 §8 without pauses
and the time to the first counted frame. No display-block reads (safe without clk_ignore_unused).
rxtime.py LOG"""
import re, sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
C, L = 0x06800000, 0x06840000
def rb(a):
    m, o = _page(a); return m[o]
def wb(a, v):
    m, o = _page(a); m[o] = v
openlog(sys.argv[1])
x5 = open("/data/bench/x5.py").read()
nos = re.findall(r"\((CTL|LINK) \+ (0x[0-9a-f]+), (0x[0-9a-f]+)\)", x5[x5.index("NOSIG = ["):x5.index("for a, v in NOSIG")])
W = [(0x06841001, 5), (0x06841014, 1), (0x06841015, 0xff), (0x06841016, 0xff), (0x06841017, 0xff), (0x06801017, 3), (0x0680101a, 0x20)]
for blk, o, v in nos:
    o = int(o, 16); v = int(v, 16)
    if blk == "CTL" and (o & 0xff) != 0xa7:
        W.append((C + o, v))
    elif blk == "LINK" and (o < 0x100 or o >= 0x200):
        W.append((L + o, v))
def timing():
    t = bytes(rb(L + 0x28 + i) for i in range(0x18)); h = lambda o: t[o] << 8 | t[o + 1]  # noqa: E731
    return h(0), h(2), h(0xc), h(0xe)
log("BEFORE-READ RX_CTL 0x068008fc / RX_LINK timing")
log(f"RXTIME start: TMDS {rb(C + 0x8fc) >> 7} 9ab={rb(C + 0x9ab):02x} timing {timing()}; {len(W)} writes")
t0 = time.monotonic()
for a, v in W:
    wb(a, v)
t1 = time.monotonic(); first_h = None
while time.monotonic() - t0 < 10:
    h = timing()
    if first_h is None and h[:2] == (2200, 1920):
        first_h = time.monotonic() - t0
    if h == (2200, 1920, 1125, 1080):
        break
    time.sleep(0.002)
tl = time.monotonic() - t0
log(f"RXTIME writes took {1000 * (t1 - t0):.2f} ms; horizontal valid after {first_h if first_h is None else round(1000 * first_h, 1)} ms; lock {timing()} after {1000 * tl:.1f} ms")
src = open("/data/bench/cap7.py").read(); ns = {}
exec(src[src.index("Y = ["):src.index("# the ring")], ns)
t2 = time.monotonic()
for o, v in sorted(ns["STATE"].items()):
    wr(0x06940000 + o, v)
wr(0x06940928, 0xE0020438); wr(0x06940968, 0xE0020438); wr(0x06940000, 0x3A7B)
c0 = rd(0x06940104) >> 16
while time.monotonic() - t2 < 2 and (rd(0x06940104) >> 16) == c0:
    time.sleep(0.001)
log(f"RXTIME capture: first frame counted {1000 * (time.monotonic() - t2):.1f} ms after the first capture write; 0x104 {rd(0x06940104):08x} 0xa0c {rd(0x06940a0c)}")
time.sleep(1)
a = rd(0x06940104); time.sleep(0.5); b = rd(0x06940104)
log(f"RXTIME capture frames in 0.5 s: {((b >> 16) - (a >> 16)) & 0xffff}")
import mmap, os
_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
SL = [mmap.mmap(_fd, 0x1FF000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=a) for a in (0x4B100000, 0x4B2FF000, 0x4B4FE000)]
def ringcheck(lbl):
    for s in SL:
        s[540 * 1920:540 * 1920 + 16] = b"\xa5" * 16
    time.sleep(0.1)
    log(f"RXTIME ring {lbl}: slots written in 100 ms {[s[540 * 1920] != 0xA5 for s in SL]}; 0x104 {rd(0x06940104):08x} 0x100 {rd(0x06940100):08x}")
ringcheck("after the no-pause start")
wr(0x06940928, rd(0x06940928) & ~0x80000000); wr(0x06940968, rd(0x06940968) & ~0x80000000); wr(0x06940000, 1)
time.sleep(0.1)
for o, v in sorted(ns["STATE"].items()):
    wr(0x06940000 + o, v)
time.sleep(0.5)
wr(0x06940928, 0xE0020438); wr(0x06940968, 0xE0020438); wr(0x06940000, 0x3A7B)
time.sleep(0.2)
ringcheck("after a start with 0.5 s between the programming and the output enables")
