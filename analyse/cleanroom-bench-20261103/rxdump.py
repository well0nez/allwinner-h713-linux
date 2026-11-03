#!/usr/bin/env python3
"""8-bit dumps of the HDMI receiver windows (59 X1/X3). Every block's first read is logged and synced first.
rxdump.py LOG LABEL [BLOCK ...]   blocks: ctl link link2 apll aux cap tvtop ccu ppu   (default: ctl link link2)"""
import mmap
import os
import sys
import time

LOG = open(sys.argv[1], "a")
LABEL = sys.argv[2]
BLOCKS = {
    "ctl": (0x06800000, 0x1000, 1),
    "link": (0x06840000, 0x800, 1),
    "link2": (0x06841000, 0x800, 1),
    "apll": (0x06880000, 0x20, 1),
    "aux": (0x07091000, 0x40, 4),
    "cap": (0x06940000, 0x1000, 4),
    "tvtop": (0x06e00000, 0x20, 4),
    "ccu": (0x02001d00, 0x100, 4),
    "ppu": (0x07001080, 0xb0, 4),
}
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)


def log(s):
    LOG.write(f"{time.monotonic():10.3f} {s}\n")
    LOG.flush()
    os.fsync(LOG.fileno())


for name in sys.argv[3:] or ["ctl", "link", "link2"]:
    base, size, width = BLOCKS[name]
    log(f"BEFORE-READ {LABEL} {name} {base:#010x}+{size:#x} width {width}")
    m = mmap.mmap(fd, (size + 0xfff) & ~0xfff, mmap.MAP_SHARED, mmap.PROT_READ, offset=base & ~0xfff)
    o = base & 0xfff
    if width == 1:
        vals = [m[o + i] for i in range(size)]
        for r in range(0, size, 32):
            log(f"DUMP {LABEL} {name} {base + r:#010x}: " + " ".join(f"{v:02x}" for v in vals[r:r + 32]))
    else:
        import struct
        for r in range(0, size, 16):
            w = [struct.unpack_from("<I", m, o + r + 4 * k)[0] for k in range(min(4, (size - r) // 4))]
            log(f"DUMP {LABEL} {name} {base + r:#010x}: " + " ".join(f"{v:08x}" for v in w))
    m.close()
log(f"DONE {LABEL}")
