#!/usr/bin/env python3
"""Dump MIPS firmware elog buffer from ARM side via /dev/mem.

MIPS virtual → ARM physical: subtract 0x40000000
  (kseg0 0x8B100000 → phys 0x4B100000, matching reserved-memory region)

Elog output mode flag at MIPS 0x8B48BE9B (phys 0x4B48BE9B):
  mode 1 → ring buffer at 0x8B272D9C (100KB)
  mode 2 → linear buffer at 0x8B28BD9C (2MB)
  else   → console printf (no buffer)
"""

import mmap
import struct
import sys
import os

VIRT_TO_PHYS = 0x40000000
PAGE = 4096

# Addresses (MIPS virtual)
MODE_FLAG_V   = 0x8B48BE9B

# Mode 1 ring buffer
BUF1_V        = 0x8B272D9C
BUF1_SIZE     = 102400       # 0x19000
BUF1_WPTR_V   = 0x8B48C2A8  # write pointer (offset into buffer)
BUF1_RPTR_V   = 0x8B48C2A4  # read pointer (offset into buffer)
BUF1_ENABLE_V = 0x8B48C2AC  # enable flag

# Mode 2 linear buffer
BUF2_V        = 0x8B28BD9C
BUF2_SIZE     = 0x200000     # 2MB
BUF2_WPTR_V   = 0x8B48C2B8  # write pointer (offset into buffer)
BUF2_ENABLE_V = 0x8B48C2AD  # enable flag

# Also check: log enabled flag and log level
LOG_ENABLED_V = 0x8B48BE99
LOG_LEVEL_V   = 0x8B48BE9A  # (guessing adjacent byte)


def v2p(virt):
    return virt - VIRT_TO_PHYS


def read_phys(fd, phys_addr, size):
    """Read `size` bytes from physical address via /dev/mem mmap."""
    page_off = phys_addr & (PAGE - 1)
    base = phys_addr - page_off
    map_size = page_off + size
    # Round up to page
    map_size = ((map_size + PAGE - 1) // PAGE) * PAGE
    mm = mmap.mmap(fd, map_size, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    data = mm[page_off:page_off + size]
    mm.close()
    return data


def read_u8(fd, virt):
    return struct.unpack('B', read_phys(fd, v2p(virt), 1))[0]


def read_u32(fd, virt):
    return struct.unpack('<I', read_phys(fd, v2p(virt), 4))[0]


def main():
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)

    print("=== MIPS elog diagnostics ===")

    # Global logging flags
    log_enabled = read_u8(fd, LOG_ENABLED_V)
    mode_flag = read_u8(fd, MODE_FLAG_V)
    print(f"Log enabled (0x8B48BE99): {log_enabled}")
    print(f"Output mode (0x8B48BE9B): {mode_flag}")
    print()

    # Mode 1 ring buffer
    buf1_en = read_u32(fd, BUF1_ENABLE_V)
    buf1_wp = read_u32(fd, BUF1_WPTR_V)
    buf1_rp = read_u32(fd, BUF1_RPTR_V)
    print(f"--- Mode 1 ring buffer (100KB at 0x{v2p(BUF1_V):08X}) ---")
    print(f"  Enable: {buf1_en}")
    print(f"  Write ptr: {buf1_wp}  Read ptr: {buf1_rp}")

    # Mode 2 linear buffer
    buf2_en = read_u8(fd, BUF2_ENABLE_V)
    buf2_wp = read_u32(fd, BUF2_WPTR_V)
    print(f"--- Mode 2 linear buffer (2MB at 0x{v2p(BUF2_V):08X}) ---")
    print(f"  Enable: {buf2_en}")
    print(f"  Write ptr: {buf2_wp}")
    print()

    # Decide which buffer to dump
    dumped = False

    if mode_flag == 1 and buf1_en:
        print("=== Dumping Mode 1 ring buffer ===")
        used = buf1_wp if buf1_wp >= buf1_rp else buf1_wp + BUF1_SIZE
        if buf1_wp > 0 and buf1_wp <= BUF1_SIZE:
            data = read_phys(fd, v2p(BUF1_V), min(buf1_wp, BUF1_SIZE))
            text = data.decode('ascii', errors='replace').rstrip('\x00')
            print(text[-4096:] if len(text) > 4096 else text)
            dumped = True

    if mode_flag == 2 and buf2_en:
        print("=== Dumping Mode 2 linear buffer ===")
        if buf2_wp > 0 and buf2_wp <= BUF2_SIZE:
            data = read_phys(fd, v2p(BUF2_V), min(buf2_wp, BUF2_SIZE))
            text = data.decode('ascii', errors='replace').rstrip('\x00')
            print(text[-4096:] if len(text) > 4096 else text)
            dumped = True

    # If neither mode buffer is active, try dumping both raw
    if not dumped:
        print("No active mode buffer detected. Dumping raw starts of both buffers...")
        print()

        print("--- Mode 1 buffer first 2KB ---")
        data = read_phys(fd, v2p(BUF1_V), 2048)
        text = data.decode('ascii', errors='replace').rstrip('\x00')
        if text.strip():
            print(text[:2048])
        else:
            print("  (empty/zero)")

        print()
        print("--- Mode 2 buffer first 2KB ---")
        data = read_phys(fd, v2p(BUF2_V), 2048)
        text = data.decode('ascii', errors='replace').rstrip('\x00')
        if text.strip():
            print(text[:2048])
        else:
            print("  (empty/zero)")

    # Also dump the cpu_comm flags for context
    print()
    print("=== cpu_comm shared memory flags ===")
    shmem_base = 0x4E300000
    arm_flag = read_phys(fd, shmem_base + 0x4CDC, 4)
    mips_flag = read_phys(fd, shmem_base + 0x4CE0, 4)
    magic1 = read_phys(fd, shmem_base + 0x90, 4)
    magic2 = read_phys(fd, shmem_base + 0x75B8, 4)
    print(f"  ARM  flag (+0x4CDC): 0x{struct.unpack('<I', arm_flag)[0]:08X}")
    print(f"  MIPS flag (+0x4CE0): 0x{struct.unpack('<I', mips_flag)[0]:08X}")
    print(f"  Magic1    (+0x0090): 0x{struct.unpack('<I', magic1)[0]:08X}")
    print(f"  Magic2    (+0x75B8): 0x{struct.unpack('<I', magic2)[0]:08X}")

    os.close(fd)


if __name__ == '__main__':
    main()
