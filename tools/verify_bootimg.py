#!/usr/bin/env python3
"""Verify HY310 Android boot image integrity: header, zImage, DTB placement"""

import struct, sys, os

IMG = "/opt/captcha/kernel/output_arm32/hy310-mainline-arm32-boot.img"
ZIMAGE = "/opt/captcha/kernel/output_arm32/zImage"
DTB = "/opt/captcha/kernel/output_arm32/sun50i-h713-hy310-v7.dtb"

img = open(IMG, "rb").read()
print(f"=== BOOT IMAGE: {len(img)} bytes ===")

# 1. Android header
magic = img[0:8]
print(f"Magic: {magic} {'OK' if magic == b'ANDROID!' else 'BROKEN!'}")

kernel_size = struct.unpack_from("<I", img, 8)[0]
print(f"kernel_size in header: {kernel_size} ({kernel_size / 1024 / 1024:.2f} MB)")

header_ver = struct.unpack_from("<I", img, 40)[0]
print(f"header_version: {header_ver}")

cmdline = img[44 : 44 + 512].split(b"\x00")[0].decode("ascii", errors="replace")
print(f"cmdline: {cmdline}")

# 2. Page alignment
PAGE = 4096
payload_offset = PAGE  # header is padded to one page
print(f"\nPayload starts at offset: 0x{payload_offset:x}")

# 3. Check zImage at payload start
payload = img[payload_offset : payload_offset + kernel_size]
arm_nop = b"\x00\x00\xa0\xe1"
if payload[:4] == arm_nop:
    print(f"Payload starts with ARM NOP: OK (zImage)")
else:
    print(f"Payload starts with: {payload[:4].hex()} — NOT ARM NOP!")

# 4. Check zImage magic at offset 0x24
zimg_magic = struct.unpack_from("<I", payload, 0x24)[0]
print(
    f"zImage magic @ +0x24: 0x{zimg_magic:08x} {'OK' if zimg_magic == 0x016F2818 else 'WRONG!'}"
)

# 5. Check DTB appended at end
dtb_magic = b"\xd0\x0d\xfe\xed"  # FDT magic (big-endian 0xd00dfeed)
if os.path.exists(DTB):
    dtb_data = open(DTB, "rb").read()
    dtb_size = len(dtb_data)
    print(f"\n=== DTB: {dtb_size} bytes ===")

    # DTB should be at end of payload
    dtb_in_payload = payload[-dtb_size:]
    if dtb_in_payload == dtb_data:
        print(f"DTB appended at payload end: EXACT MATCH")
    else:
        print(f"DTB at payload end: NO MATCH")
        # Search for DTB magic in payload
        pos = payload.find(dtb_magic)
        if pos >= 0:
            print(
                f"DTB magic found at payload offset 0x{pos:x} (image offset 0x{payload_offset + pos:x})"
            )
            embedded_dtb = payload[pos : pos + dtb_size]
            if embedded_dtb == dtb_data:
                print(f"DTB content matches at this offset: OK")
            else:
                print(f"DTB content DIFFERS at this offset")
        else:
            print(f"DTB magic (d00dfeed) NOT FOUND anywhere in payload!")
else:
    print(f"\nDTB file not found: {DTB}")
    # Still search for FDT magic
    pos = payload.find(dtb_magic)
    if pos >= 0:
        print(f"DTB magic found at payload offset 0x{pos:x}")
        fdt_size = struct.unpack_from(">I", payload, pos + 4)[0]
        print(f"FDT totalsize: {fdt_size} bytes")
    else:
        print(f"NO DTB MAGIC FOUND IN PAYLOAD — THIS IS THE PROBLEM!")

# 6. Compare with standalone zImage
if os.path.exists(ZIMAGE):
    zimg = open(ZIMAGE, "rb").read()
    print(f"\n=== STANDALONE ZIMAGE: {len(zimg)} bytes ===")
    expected_payload = len(zimg) + (len(dtb_data) if os.path.exists(DTB) else 0)
    print(f"Expected payload (zImage+DTB): {expected_payload}")
    print(f"Actual payload (kernel_size):  {kernel_size}")
    if expected_payload == kernel_size:
        print("SIZE MATCH: OK")
    else:
        print(f"SIZE MISMATCH: delta = {kernel_size - expected_payload}")
        if kernel_size == len(zimg):
            print("kernel_size == zImage size — DTB WAS NOT APPENDED!")

    # Check if payload starts with zImage content
    if payload[:1024] == zimg[:1024]:
        print("Payload content matches zImage start: OK (uncompressed)")
    else:
        # Maybe gzipped?
        if payload[:2] == b"\x1f\x8b":
            print("Payload starts with gzip magic — image contains GZIPPED kernel!")
            print("This may be wrong if U-Boot expects raw zImage+DTB")
        else:
            print("Payload does NOT match zImage start")

print("\n=== VERDICT ===")
issues = []
if magic != b"ANDROID!":
    issues.append("Bad ANDROID! magic")
if zimg_magic != 0x016F2818:
    issues.append("Bad zImage magic")
if os.path.exists(DTB):
    if payload.find(dtb_magic) < 0:
        issues.append("NO DTB APPENDED — kernel will crash without device tree!")
if os.path.exists(ZIMAGE):
    zimg = open(ZIMAGE, "rb").read()
    if payload[:2] == b"\x1f\x8b":
        issues.append(
            "Kernel is GZIPPED — U-Boot may not decompress correctly with appended DTB"
        )
if issues:
    for i in issues:
        print(f"  PROBLEM: {i}")
else:
    print("  ALL CHECKS PASSED")
