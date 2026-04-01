#!/usr/bin/env python3
"""Read R_PIO (R-domain pinctrl) registers from H713 to determine PL/PM pin mux table."""

import mmap, struct, os, sys

R_PIO_BASE = 0x07022000
SIZE = 0x800  # Full R_PIO register space

f = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(f, SIZE, mmap.MAP_SHARED, mmap.PROT_READ, offset=R_PIO_BASE)


def rd(off):
    return struct.unpack_from("<I", m, off)[0]


# Allwinner pinctrl register layout per bank:
# 0x00-0x0C: PL_CFG0-PL_CFG3 (pin mux, 4 bits per pin)
# 0x10-0x14: PL_DAT (data register)
# 0x14-0x1C: PL_DRV0-PL_DRV1 (drive strength, 2 bits per pin) -- old layout
# For new layout (0x30 spacing like D1):
#   offset = bank * 0x30
#   CFG0 = base + 0x00, CFG1 = base + 0x04, CFG2 = base + 0x08, CFG3 = base + 0x0C
#   DAT  = base + 0x10
#   DRV0 = base + 0x14, DRV1 = base + 0x18, DRV2 = base + 0x1C, DRV3 = base + 0x20
#   PUL0 = base + 0x24, PUL1 = base + 0x28

# Try both old (0x24 spacing) and new (0x30 spacing) layouts
print("=== R_PIO Raw Register Dump ===")
print(f"Base: 0x{R_PIO_BASE:08x}")
print()

for off in range(0, 0x100, 4):
    val = rd(off)
    if val != 0:
        print(f"  0x{off:03x}: 0x{val:08x}")

print()
print("=== PL Bank (Bank 0) - Old Layout (0x24 spacing) ===")
for i in range(4):
    val = rd(i * 4)
    print(f"  PL_CFG{i} (0x{i * 4:02x}): 0x{val:08x}")
    for bit in range(8):
        pin = i * 8 + bit
        func = (val >> (bit * 4)) & 0xF
        if func != 0 or pin < 16:
            names = {
                0: "in",
                1: "out",
                2: "fn2",
                3: "fn3",
                4: "fn4",
                5: "fn5",
                6: "irq",
                7: "dis",
            }
            fname = names.get(func, f"fn{func}")
            print(f"    PL{pin}: mux={func} ({fname})")

print()
print(f"  PL_DAT (0x10): 0x{rd(0x10):08x}")
print(f"  PL_DRV0 (0x14): 0x{rd(0x14):08x}")
print(f"  PL_DRV1 (0x18): 0x{rd(0x18):08x}")
print(f"  PL_PUL0 (0x1C): 0x{rd(0x1C):08x}")
print(f"  PL_PUL1 (0x20): 0x{rd(0x20):08x}")

print()
print("=== PL Bank - New Layout (0x30 spacing) ===")
base = 0x00
for i in range(4):
    val = rd(base + i * 4)
    print(f"  PL_CFG{i} (0x{base + i * 4:02x}): 0x{val:08x}")
print(f"  PL_DAT  (0x{base + 0x10:02x}): 0x{rd(base + 0x10):08x}")
for i in range(4):
    print(f"  PL_DRV{i} (0x{base + 0x14 + i * 4:02x}): 0x{rd(base + 0x14 + i * 4):08x}")
for i in range(2):
    print(f"  PL_PUL{i} (0x{base + 0x24 + i * 4:02x}): 0x{rd(base + 0x24 + i * 4):08x}")

print()
print("=== PM Bank - New Layout (0x30 spacing, offset=0x30) ===")
base = 0x30
for i in range(4):
    val = rd(base + i * 4)
    print(f"  PM_CFG{i} (0x{base + i * 4:02x}): 0x{val:08x}")
print(f"  PM_DAT  (0x{base + 0x10:02x}): 0x{rd(base + 0x10):08x}")
for i in range(4):
    print(f"  PM_DRV{i} (0x{base + 0x14 + i * 4:02x}): 0x{rd(base + 0x14 + i * 4):08x}")
for i in range(2):
    print(f"  PM_PUL{i} (0x{base + 0x24 + i * 4:02x}): 0x{rd(base + 0x24 + i * 4):08x}")

print()
print("=== Interrupt config (EINT) ===")
# Old: 0x200+, New: varies
for off in [0x200, 0x210, 0x214, 0x220, 0x230, 0x240, 0x250, 0x260]:
    val = rd(off)
    if val != 0:
        print(f"  0x{off:03x}: 0x{val:08x}")

# Also try new-layout EINT at different offsets
for off in range(0x100, 0x300, 4):
    val = rd(off)
    if val != 0:
        print(f"  0x{off:03x}: 0x{val:08x}")

m.close()
os.close(f)
print()
print("Done.")
