#!/usr/bin/env python3
"""Q-DRM-6: RGB pitch word 0x05600170 - implemented bits, pitches above 8192.
Needs the aligned RGB-over-video state (r10.py setup + align3.py): then the histogram counts the RGB plane alone.
Buffer region 0x4b100000..0x4c3ef000 (reserved by the bench boot, below the spec/12 write-channel area).
pitch.py LOG"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

SC = 0x05600000
PNL = 0x051C0000
A = 0x4B100000
SIZE = 0x4C000000 - A  # below the black video frame at 0x4c000000
openlog(sys.argv[1])
m, off = map_ram(A, SIZE)
WHITE = b"\xff" * 7680
BLACK = b"\x00\x00\x00\xff" * (SIZE // 4)


def hist():
    time.sleep(0.08)
    return [rd(PNL + 0x380 + 4 * i) for i in range(32)]


def show(pitch_word, rows_pitch, label):
    buf = bytearray(BLACK)  # built in normal memory, copied in one aligned piece (device memory faults on
    for y in range(1080):   # unaligned stores)
        o = y * rows_pitch
        if o + 7680 > SIZE:
            break
        buf[o:o + 7680] = WHITE
    m[off:off + SIZE] = bytes(buf)
    wr(SC + 0x178, A)
    wr(SC + 0x170, pitch_word)
    wr(SC + 0x144, 1)
    t0 = time.monotonic()
    while rd(SC + 0x144) & 1 and time.monotonic() - t0 < 0.1:
        pass
    h = hist()
    log(f"PITCH2 {label}: 0x170 written {pitch_word:#x} reads {rd(SC + 0x170):#x}, 0x174 {rd(SC + 0x174):#x}; "
        f"white rows every {rows_pitch} bytes; high (bin 31) {h[31]}, bin 0 {h[0]}, other {sum(h) - h[31] - h[0]}")


for p in (7680, 8192, 8196, 8200, 8208, 8224, 8256, 8320, 8448, 7684, 7696, 7744):
    show(p, p, f"pitch {p}")
show(7680, 7680, "back to 7680")
log("PITCH2 DONE")
