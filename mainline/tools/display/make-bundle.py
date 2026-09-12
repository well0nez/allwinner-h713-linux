#!/usr/bin/env python3
"""Build one stageable image holding every artifact the display needs.

The four blobs live within 16 MB of each other, so a single fastboot upload to
0x4b100000 places all of them at once. Staging them separately means four
interleaved U-Boot/host round trips, which is where mistakes happen.

Layout is from display_cfg.xml's own header, except LogoRegData.bin, which the
ARM consumes and which we park above the firmware's working set.
"""
import sys, pathlib

BASE = 0x4b100000
PARTS = [
    (0x4b100000, "display.bin"),
    (0x4be01000, "display_cfg.xml"),
    (0x4be41000, None),            # TSE blob, assembled below
    (0x4c000000, "LogoRegData.bin"),
]
TSE = ["database.TSE", "projecttable.TSE", "ProjectID_0x0012.TSE", "pq_custom.TSE"]
SIZE = 0x1000000                   # 16 MB, covers 0x4b100000..0x4c100000

def main():
    if len(sys.argv) != 3:
        sys.exit("usage: make-bundle.py <vendor-mips-dir> <out.bin>")
    src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    img = bytearray(SIZE)

    for addr, name in PARTS:
        off = addr - BASE
        data = (b"".join((src / t).read_bytes() for t in TSE)
                if name is None else (src / name).read_bytes())
        if off + len(data) > SIZE:
            sys.exit(f"{name or 'TSE'} overruns the bundle")
        img[off:off + len(data)] = data
        print(f"  0x{addr:08x} +0x{off:07x}  {len(data):>8}  "
              f"{name or '+'.join(TSE)}")

    out.write_bytes(img)
    print(f"wrote {out} ({len(img)} bytes)")

main()
