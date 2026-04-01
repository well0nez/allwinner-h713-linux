#!/usr/bin/env python3
"""
Patch U-Boot env_a: add 'usb start;' to bootcmd for auto USB init.
Format: [CRC32 (4 bytes)] [flags (1 byte)] [env strings... to 0x20000]
CRC is calculated over data[4:0x20000]
"""

import struct, zlib, sys

ENV_PATH = "/opt/captcha/kernel/env_a.bin"
OUT_PATH = "/opt/captcha/kernel/env_a_patched.bin"
ENV_SIZE = 0x20000  # CRC covers first 128KB (from offset 4)

data = bytearray(open(ENV_PATH, "rb").read())
print(f"env_a size: {len(data)} bytes")

# Verify CRC
stored_crc = struct.unpack_from("<I", data, 0)[0]
calc_crc = zlib.crc32(bytes(data[4:ENV_SIZE])) & 0xFFFFFFFF
match = stored_crc == calc_crc
print(f"CRC: stored=0x{stored_crc:08x} calc=0x{calc_crc:08x} match={match}")

if not match:
    print("CRC MISMATCH - aborting!")
    sys.exit(1)

# Parse env (starts at offset 5, flags byte at offset 4)
env_start = 5
env_data = data[env_start:ENV_SIZE]
end = env_data.find(b"\x00\x00")
if end < 0:
    end = len(env_data)
entries = [e for e in env_data[:end].split(b"\x00") if e]

print(f"\n{len(entries)} env variables:")
bootcmd = None
for e in entries:
    s = e.decode("ascii", errors="replace")
    print(f"  {s}")
    if s.startswith("bootcmd="):
        bootcmd = s

if not bootcmd:
    print("\nERROR: No bootcmd found!")
    sys.exit(1)

print(f"\n=== Current bootcmd ===")
print(f"  {bootcmd}")

if "usb start" in bootcmd:
    print("\n'usb start' already present. Nothing to do.")
    sys.exit(0)

# Patch: add 'usb start;' before existing bootcmd value
old_val = bootcmd[len("bootcmd=") :]
new_val = "usb start;" + old_val
old_bytes = bootcmd.encode("ascii")
new_bytes = ("bootcmd=" + new_val).encode("ascii")

print(f"\n=== Patching ===")
print(f"OLD: {bootcmd}")
print(f"NEW: bootcmd={new_val}")
print(f"Size change: {len(new_bytes) - len(old_bytes):+d} bytes")

# Find in binary and replace
idx = data.find(old_bytes)
if idx < 0:
    print("ERROR: bootcmd bytes not found in binary!")
    sys.exit(1)

# Insert new bytes (shifts everything after by size diff)
patched = bytearray(data[:idx]) + new_bytes + data[idx + len(old_bytes) :]

# Ensure total size stays the same
if len(patched) > len(data):
    excess = len(patched) - len(data)
    if patched[-excess:] == b"\x00" * excess:
        patched = patched[: len(data)]
    else:
        print(f"ERROR: Would overwrite non-zero data at end!")
        sys.exit(1)
elif len(patched) < len(data):
    patched += b"\x00" * (len(data) - len(patched))

# Recalculate CRC over data[4:0x20000]
new_crc = zlib.crc32(bytes(patched[4:ENV_SIZE])) & 0xFFFFFFFF
struct.pack_into("<I", patched, 0, new_crc)

# Verify
verify_crc = zlib.crc32(bytes(patched[4:ENV_SIZE])) & 0xFFFFFFFF
verify_stored = struct.unpack_from("<I", patched, 0)[0]
print(f"\nNew CRC: 0x{new_crc:08x}")
print(
    f"Verify: stored=0x{verify_stored:08x} calc=0x{verify_crc:08x} match={verify_stored == verify_crc}"
)

# Show patched bootcmd
patched_env = patched[env_start:ENV_SIZE]
for e in patched_env[: patched_env.find(b"\x00\x00")].split(b"\x00"):
    if e and b"bootcmd=" in e:
        print(f"Patched bootcmd: {e.decode()}")

open(OUT_PATH, "wb").write(patched)
print(f"\nWritten: {OUT_PATH}")
