#!/usr/bin/env python3
"""Spec-side check after the clean side's T2 apply: 1280x720 frame with a white 640x360 top-left quadrant at the
frame address channel 0 already shows; histogram share in the high bins (correct 1.5x scaling: 25.00 %)."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr
openlog(sys.argv[1])
A = int(sys.argv[2], 0); W, H = 1280, 720
m, off = map_ram(A, W * H * 3 // 2)
for kind in ("quad", "left", "top"):
    if kind == "quad":
        m[off:off + (H // 2) * W] = (bytes([235]) * (W // 2) + bytes([16]) * (W // 2)) * (H // 2)
        m[off + (H // 2) * W:off + H * W] = bytes([16]) * (W * H // 2)
    elif kind == "left":
        m[off:off + H * W] = (bytes([235]) * (W // 2) + bytes([16]) * (W // 2)) * H
    else:
        m[off:off + (H // 2) * W] = bytes([235]) * ((H // 2) * W)
        m[off + (H // 2) * W:off + H * W] = bytes([16]) * ((H // 2) * W)
    m[off + W * H:off + W * H * 3 // 2] = bytes([128, 128]) * (W * H // 4)
    time.sleep(0.15)
    h = [rd(0x051C0380 + 4 * i) for i in range(32)]
    s = sum(h)
    log(f"QUAD {kind}: sum {s} high {sum(h[24:])} = {100.0 * sum(h[24:]) / s:.2f} % low {sum(h[:9])} = {100.0 * sum(h[:9]) / s:.2f} %")
