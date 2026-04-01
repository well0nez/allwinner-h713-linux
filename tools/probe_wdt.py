#!/usr/bin/env python3
"""Probe potential watchdog register addresses on H713"""

import mmap, struct, os

addrs = [
    0x030090A0,  # H6/H616 standard watchdog
    0x030090B0,  # H6 watchdog ctrl
    0x030090B8,  # H6 watchdog mode
    0x02051000,  # Possible H713 watchdog (BSP?)
    0x02051010,  # Possible H713 wdt ctrl
    0x02051018,  # Possible H713 wdt mode
    0x03009000,  # Timer base (H6)
    0x07020400,  # R_WDOG (CPUS domain, H6)
]

fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
for addr in addrs:
    try:
        page = addr & ~0xFFF
        off = addr - page
        m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=page)
        val = struct.unpack("<I", m[off : off + 4])[0]
        m.close()
        print(f"0x{addr:08x}: 0x{val:08x}")
    except Exception as e:
        print(f"0x{addr:08x}: FAIL ({e})")
os.close(fd)
