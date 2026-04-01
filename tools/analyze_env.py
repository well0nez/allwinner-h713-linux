#!/usr/bin/env python3
"""Analyze U-Boot env_a - try different CRC offsets to find correct format"""

import struct, zlib

ENV_PATH = "/opt/captcha/kernel/env_a.bin"
data = open(ENV_PATH, "rb").read()
print(f"Size: {len(data)} bytes")
print(f"First 32 bytes: {data[:32].hex()}")

stored_crc = struct.unpack_from("<I", data, 0)[0]
print(f"\nStored CRC (offset 0): 0x{stored_crc:08x}")

# Try different data start offsets
for start in [4, 5, 8, 12, 16]:
    crc = zlib.crc32(data[start:]) & 0xFFFFFFFF
    match = "MATCH!" if crc == stored_crc else ""
    print(f"  CRC32(data[{start}:]): 0x{crc:08x} {match}")

# Try CRC at different positions
for pos in [0, 4, 8, 12, 16]:
    if pos + 4 <= len(data):
        val = struct.unpack_from("<I", data, pos)[0]
        # Try CRC of everything except this position
        test = bytearray(data)
        test[pos : pos + 4] = b"\x00\x00\x00\x00"
        crc = zlib.crc32(bytes(test)) & 0xFFFFFFFF
        match = "MATCH!" if crc == val else ""
        print(
            f"  Word at offset {pos}: 0x{val:08x}, CRC32(zeroed): 0x{crc:08x} {match}"
        )

# Maybe CRC is only over a portion
for env_size in [0x1000, 0x2000, 0x4000, 0x8000, 0x10000, 0x20000, 0x40000]:
    if env_size <= len(data):
        crc = zlib.crc32(data[4:env_size]) & 0xFFFFFFFF
        match = "MATCH!" if crc == stored_crc else ""
        if match:
            print(f"  CRC32(data[4:0x{env_size:x}]): 0x{crc:08x} {match}")

# Show raw hex around env data
print(f"\nFirst env string starts at:", data.find(b"BOOTMODE"))
print(f"Hex at offset 0-16: {data[:16].hex()}")
print(f"Hex at offset 4-8 (possible flags): {data[4:8].hex()}")

# Check if there's a sunxi-specific header
print(f"\n=== Trying sunxi env format ===")
# Some sunxi use: magic(8) + crc(4) + size(4) + data
for magic_len in [0, 8, 16]:
    if magic_len + 4 <= len(data):
        crc_pos = magic_len
        crc_val = struct.unpack_from("<I", data, crc_pos)[0]
        for data_start in [crc_pos + 4, crc_pos + 8]:
            if data_start < len(data):
                crc = zlib.crc32(data[data_start:]) & 0xFFFFFFFF
                match = "MATCH!" if crc == crc_val else ""
                if match:
                    print(
                        f"  CRC at offset {crc_pos}: 0x{crc_val:08x}, data from {data_start}: {match}"
                    )
