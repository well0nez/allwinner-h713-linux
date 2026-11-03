#!/usr/bin/env python3
"""Q-DRM-4: one RGB pitch other than the handoff's. Needs the stage-2 state with a black video frame on screen
(minimize.py all leaves it) so that the RGB plane blended at alpha 0xff shows in the histogram (05 §2).
r6.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr, wr_logged  # noqa: E402

SC = 0x05600000
A = 0x4B200000  # mips-firmware reserved region, unused with the co-processor held (05 §6)
openlog(sys.argv[1])


def hist():
    h = [rd(0x051C0380 + 4 * i) for i in range(32)]
    return sum(h[24:]), sum(h[:9]), sum(h) - sum(h[24:]) - sum(h[:9])


def rgb(addr, pitch, word174, label):
    wr(SC + 0x178, addr)
    wr(SC + 0x170, pitch)
    wr(SC + 0x174, word174)
    wr(SC + 0x140, 0x03001901)
    wr(SC + 0x144, 1)
    time.sleep(0.15)
    hi, lo, mid = hist()
    log(f"PITCH {label}: 0x170 {rd(SC + 0x170):#x} 0x174 {rd(SC + 0x174):#x} -> high {hi} low {lo} mid {mid}")


# black video frame (minimize.py's) on channel 0, RGB over it at alpha 0xff
for o in (0x070, 0x074, 0x078, 0x07C):
    wr(SC + o, 0x6CA00000)
for o in (0x084, 0x088, 0x08C, 0x090):
    wr(SC + o, 0x6CA00000 + 1920 * 1080)
wr(SC + 0x06C, 1)
wr_logged(0x051C006C, 0x29000000, "PNL_SEL RGB over video")
wr_logged(0x051C0070, (rd(0x051C0070) & ~0xFF) | 0xFF, "global alpha 0xff")
m, off = map_ram(A, 8192 * 1080)
# all white at pitch 7680 (reference)
m[off:off + 7680 * 1080] = b"\xff\xff\xff\xff" * (1920 * 1080)
rgb(A, 0x1E00, 0x04381E00, "all white, pitch 7680 (handoff words)")
# rows of 1920 white + 128 black pixels at pitch 8192
row = b"\xff\xff\xff\xff" * 1920 + b"\x00\x00\x00\xff" * 128
m[off:off + 8192 * 1080] = row * 1080
rgb(A, 0x2000, 0x04382000, "white rows + 128 black px, pitch 8192, 0x174 = 1080<<16|8192")
rgb(A, 0x2000, 0x04381E00, "same buffer, 0x170 = 8192 only (0x174 as handoff)")
rgb(A, 0x1E00, 0x04382000, "same buffer, 0x174 = ..|8192 only (0x170 7680)")
rgb(A, 0x1E00, 0x04381E00, "same buffer read at pitch 7680 (wrong pitch)")
wr_logged(SC + 0x178, 0x6C100000, "address back to the logo")
wr(SC + 0x170, 0x1E00)
wr(SC + 0x174, 0x04381E00)
wr(SC + 0x144, 1)
log("R6 DONE")
