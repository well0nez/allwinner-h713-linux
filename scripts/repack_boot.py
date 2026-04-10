#!/usr/bin/env python3
"""Repack zImage + DTB into Android boot image with 4MB chunks for HY310 U-Boot.

Usage:
    python3 repack_with_dtb.py [--outdir DIR] [--zimage PATH] [--dtb PATH] [--cmdline STR]

Defaults assume HY310 workspace paths (../kernel/build/output_arm32).
"""

import argparse
import struct
import os
import sys

DEFAULT_OUTDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "build", "output_arm32")
)
DEFAULT_CMDLINE = (
    "console=ttyS0,115200 earlycon earlyprintk loglevel=8 "
    "root=/dev/sda2 rootwait rootfstype=ext4 clk_ignore_unused"
)

PAGE_SIZE = 4096
HEADER_SIZE = 1580
CHUNK_SIZE = 4 * 1024 * 1024
LOAD_ADDR = 0x45000000


def page_align(size):
    return ((size + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE


def find_dtb(outdir):
    """Find the newest sun50i-h713-hy310 DTB in outdir."""
    candidates = sorted(
        [
            f
            for f in os.listdir(outdir)
            if f.startswith("sun50i-h713-hy310") and f.endswith(".dtb")
        ],
        key=lambda f: os.path.getmtime(os.path.join(outdir, f)),
        reverse=True,
    )
    if not candidates:
        return None
    return os.path.join(outdir, candidates[0])


def main():
    parser = argparse.ArgumentParser(
        description="Repack zImage+DTB into Android boot image"
    )
    parser.add_argument("--outdir", default=DEFAULT_OUTDIR, help="Output directory")
    parser.add_argument(
        "--zimage", default=None, help="zImage path (default: outdir/zImage)"
    )
    parser.add_argument(
        "--dtb", default=None, help="DTB path (default: newest hy310 DTB in outdir)"
    )
    parser.add_argument(
        "--cmdline", default=DEFAULT_CMDLINE, help="Kernel command line"
    )
    args = parser.parse_args()

    outdir = args.outdir
    zimage_path = args.zimage or os.path.join(outdir, "zImage")
    dtb_path = args.dtb or find_dtb(outdir)

    if not os.path.isfile(zimage_path):
        print(f"ERROR: zImage not found: {zimage_path}", file=sys.stderr)
        sys.exit(1)
    if not dtb_path or not os.path.isfile(dtb_path):
        print(f"ERROR: DTB not found in {outdir}", file=sys.stderr)
        sys.exit(1)

    zimage = open(zimage_path, "rb").read()
    dtb = open(dtb_path, "rb").read()

    print(
        f"zImage:     {len(zimage):>10} bytes  ({len(zimage) / 1024 / 1024:.1f} MB)  {zimage_path}"
    )
    print(f"DTB:        {len(dtb):>10} bytes  ({len(dtb) / 1024:.1f} KB)  {dtb_path}")

    # Append DTB to zImage (CONFIG_ARM_APPENDED_DTB)
    kernel_with_dtb = zimage + dtb
    print(
        f"zImage+DTB: {len(kernel_with_dtb):>10} bytes  ({len(kernel_with_dtb) / 1024 / 1024:.1f} MB)"
    )

    # Build Android boot image v3 header
    cmdline_bytes = args.cmdline.encode("ascii")
    if len(cmdline_bytes) > 1536:
        print(f"ERROR: cmdline too long ({len(cmdline_bytes)} > 1536)", file=sys.stderr)
        sys.exit(1)

    header = bytearray(HEADER_SIZE)
    header[0:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(kernel_with_dtb))  # kernel size
    struct.pack_into("<I", header, 12, 0)  # ramdisk size
    struct.pack_into("<I", header, 16, 0x16000162)  # second addr
    struct.pack_into("<I", header, 20, HEADER_SIZE)  # page size (overloaded)
    struct.pack_into("<I", header, 40, 3)  # header version
    header[44 : 44 + len(cmdline_bytes)] = cmdline_bytes

    header_padded = bytes(header) + b"\x00" * (page_align(HEADER_SIZE) - HEADER_SIZE)
    kernel_padded = kernel_with_dtb + b"\x00" * (
        page_align(len(kernel_with_dtb)) - len(kernel_with_dtb)
    )
    image = header_padded + kernel_padded

    # Write boot image
    img_path = os.path.join(outdir, "hy310-mainline-arm32-boot.img")
    with open(img_path, "wb") as f:
        f.write(image)
    print(
        f"Boot image: {len(image):>10} bytes  ({len(image) / 1024 / 1024:.1f} MB)  {img_path}"
    )

    # Remove old chunks
    for f in os.listdir(outdir):
        if f.startswith("mboot32."):
            os.remove(os.path.join(outdir, f))

    # Create 4MB chunks
    offset = 0
    idx = 0
    while offset < len(image):
        end = min(offset + CHUNK_SIZE, len(image))
        chunk = image[offset:end]
        name = f"mboot32.{idx:02d}"
        with open(os.path.join(outdir, name), "wb") as f:
            f.write(chunk)
        offset = end
        idx += 1

    print(f"Chunks:     {idx}")
    print(f"cmdline:    {args.cmdline}")
    print()
    print("=== U-Boot commands ===")
    print("usb start")
    for i in range(idx):
        addr = LOAD_ADDR + i * CHUNK_SIZE
        print(f"fatload usb 0:1 0x{addr:08x} mboot32.{i:02d}")
    print(f"bootm 0x{LOAD_ADDR:08x}")


if __name__ == "__main__":
    main()
