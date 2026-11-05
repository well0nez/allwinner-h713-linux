#!/usr/bin/env python3
"""Q-PQ-9: which pixel the probe words sample; Q-PQ-10: red frame at hue 0/50/100 and the YCbCr->RGB matrix.
Needs the aligned RGB-over-video 12 state (r10.py setup + align3.py).  q9.py LOG STEP...
  where      RGB buffer coding the position (R = x & 0xff, G = (x >> 8) | (y >> 8) << 4, B = y & 0xff), gamma off,
             WB neutral: decode 0x051c0304; then NV12 frames coding x and y in Y: decode 0x051c0144
  scan       read PNL 0x100..0x3fc twice; list the words that differ between two probe positions? (dump only)
  try ADDR   write ADDR = old ^ bit for bits 0..31 one at a time, report probe position changes
  matrix     neutral levels; probes for Y/Cb/Cr steps and the red frame at hue +256/0/-256"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

PNL = 0x051C0000
A = 0x4B200000
V = 0x6CA00000
openlog(sys.argv[1])
_m, _o = map_ram(A, 7680 * 1080)
_vm, _vo = map_ram(V, 1920 * 1080 * 3 // 2)


def ch(v):
    return v >> 20 & 0x3FF, v & 0x3FF, v >> 10 & 0x3FF  # R, G, B


_coded = []


def rgb_where():
    if not _coded:
        xs = bytearray(7680)
        for x in range(1920):
            xs[4 * x + 1] = x >> 8
            xs[4 * x + 2] = x & 0xFF
            xs[4 * x + 3] = 0xFF
        rows = []
        for y in range(1080):
            line = bytearray(xs)
            line[0::4] = bytes([y & 0xFF]) * 1920
            line[1::4] = bytes(b | ((y >> 8) << 4) for b in xs[1::4])
            rows.append(bytes(line))
        _m[_o:_o + 7680 * 1080] = b"".join(rows)
        _coded.append(1)
    wr(PNL + 0x6C, 0x29000000)
    time.sleep(0.15)
    r, g, b = ch(rd(PNL + 0x304))
    r8, g8, b8 = r >> 2, g >> 2, b >> 2
    x = ((g8 & 0xF) << 8) | r8
    y = ((g8 >> 4) << 8) | b8
    return x, y, (r, g, b)


def y_frame(f):
    luma = bytearray(1920 * 1080)
    for y in range(1080):
        luma[y * 1920:(y + 1) * 1920] = bytes(f(x, y) for x in range(1920))
    _vm[_vo:_vo + 1920 * 1080] = bytes(luma)
    _vm[_vo + 1920 * 1080:_vo + 1920 * 1080 * 3 // 2] = b"\x80" * (1920 * 540)
    time.sleep(0.15)
    r, g, b = ch(rd(PNL + 0x144))
    return round(g * 219 / 1023 + 16)


def video_where():
    wr(PNL + 0x6C, 0x39000000)
    xl = y_frame(lambda x, y: 16 + x % 200) - 16
    xh = y_frame(lambda x, y: 16 + x // 10) - 16
    yl = y_frame(lambda x, y: 16 + y % 200) - 16
    yh = y_frame(lambda x, y: 16 + y // 10) - 16
    x = [c for c in range(1920) if c % 200 == xl and abs(c // 10 - xh) <= 1]
    yy = [c for c in range(1080) if c % 200 == yl and abs(c // 10 - yh) <= 1]
    return x, yy, (xl, xh, yl, yh)


def neutral():
    wr(PNL + 0xE8, rd(PNL + 0xE8) & ~(1 << 26))
    for a, v in ((0x051C00D4, 0), (0x051C00D8, 0), (0x051C00DC, 0x08000800), (0x051C00E0, 0x08000000),
                 (0x051405BC, 0x80), (0x05140D34, 0x09580958), (0x05140D38, 0x00400958), (0x05140508, 0x04400000)):
        wr(a, v)


def yuv(y, u, v):
    _vm[_vo:_vo + 1920 * 1080] = bytes([y]) * (1920 * 1080)
    _vm[_vo + 1920 * 1080:_vo + 1920 * 1080 * 3 // 2] = bytes([u, v]) * (960 * 540)
    time.sleep(0.15)
    return ch(rd(PNL + 0x144))


args = sys.argv[2:]
i = 0
while i < len(args):
    c = args[i]
    if c == "where":
        neutral()
        x, y, raw = rgb_where()
        log(f"Q9 RGB probe 0x051c0304 samples x={x} y={y} (raw R/G/B {raw})")
        xs, ys, raw = video_where()
        log(f"Q9 video probe 0x051c0144 samples x in {xs} y in {ys} (decoded {raw})")
        i += 1
    elif c == "try":
        a = int(args[i + 1], 0)
        neutral()
        old = rd(a)
        x0, y0, _ = rgb_where()
        for b in range(32):
            wr(a, old ^ (1 << b))
            time.sleep(0.05)
            x, y, raw = rgb_where()
            rb = rd(a)
            wr(a, old)
            if (x, y) != (x0, y0):
                log(f"Q9 TRY {a:#010x} {old:#010x} bit {b} (reads {rb:#010x}): probe moves ({x0},{y0}) -> ({x},{y})")
        log(f"Q9 TRY {a:#010x} done (probe at ({x0},{y0}))")
        i += 2
    elif c == "scan":
        log("Q9 SCAN " + " ".join(f"{o:03x}={rd(PNL + o):08x}" for o in range(0x100, 0x400, 4) if not 0x380 <= o < 0x400))
        i += 1
    elif c == "matrix":
        wr(PNL + 0x6C, 0x39000000)
        neutral()
        for yv in [(128, 128, 128), (160, 128, 128), (128, 160, 128), (128, 128, 160), (128, 96, 128), (128, 128, 96)]:
            log(f"Q10 Y/Cb/Cr {yv}: 0x0144 R/G/B {yuv(*yv)}")
        for h, name in ((0x100, "hue 0 (+256)"), (0x000, "hue 50 (0)"), (0x300, "hue 100 (-256)")):
            wr(0x05140508, 0x04400000 | h)
            log(f"Q10 red Y 128 Cb 64 Cr 192, {name}: 0x0144 R/G/B {yuv(128, 64, 192)}; 0x0304 {ch(rd(PNL + 0x304))}")
        wr(0x05140508, 0x04400000)
        i += 1
    else:
        raise SystemExit(c)
