#!/usr/bin/env python3
"""Q1: channel 0 by hand with no firmware.  q1.py LOG CMD [args]

fill PATTERN   write an NV12 1920x1080 frame at FRAME (black|white|grey|P1)
prog           program channel 0 as 10 T1 in the order 10 L4 (no chroma gain), enable and latch
sel            PNL_SEL = 0x39000000, MIX = 0x00000040 (video alone)
unsel          PNL_SEL back, MIX = 0x10000040 (RGB alone)
gate11         VCH_GATE = 0x11, latch
off            channel 0 enable bits off, latch
obs LABEL      read the observation set (channel 0, probes, histogram, counters, 1 s vsync poll)
"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, rd_logged, wr, wr_logged  # noqa: E402

FRAME = 0x4C000000  # inside the firmware's reserved, no-map frame window; the firmware never runs here
W, H = 1920, 1080
SC = 0x05600000
PNL = 0x051C0000
MIX = 0x058C0000

openlog(sys.argv[1])
cmd = sys.argv[2]

# BT.709 limited (Y, Cb, Cr) per 95 section 2
BARS = [(235, 128, 128), (219, 16, 138), (188, 154, 16), (173, 42, 26),
        (78, 214, 230), (63, 102, 240), (32, 240, 118), (16, 128, 128)]


def fill(pattern):
    m, off = map_ram(FRAME, W * H * 3 // 2)
    if pattern in ("black", "white", "grey"):
        y, cb, cr = {"black": (16, 128, 128), "white": (235, 128, 128), "grey": (126, 128, 128)}[pattern]
        m[off:off + W * H] = bytes([y]) * (W * H)
        m[off + W * H:off + W * H * 3 // 2] = bytes([cb, cr]) * (W * H // 4)
    elif pattern == "P1":
        bw = W // 8
        yrow_bars = b"".join(bytes([c[0]]) * bw for c in BARS)
        yrow_ramp = bytes(16 + (235 - 16) * x // (W - 1) for x in range(W))
        top = H * 2 // 3
        m[off:off + top * W] = yrow_bars * top
        m[off + top * W:off + H * W] = yrow_ramp * (H - top)
        crow_bars = b"".join(bytes([c[1], c[2]]) * (bw // 2) for c in BARS)
        crow_grey = bytes([128, 128]) * (W // 2)
        c0 = off + W * H
        m[c0:c0 + (top // 2) * W] = crow_bars * (top // 2)
        m[c0 + (top // 2) * W:c0 + (H // 2) * W] = crow_grey * (H // 2 - top // 2)
    else:
        raise SystemExit("unknown pattern")
    log(f"FILL {pattern} at {FRAME:#x}: luma[0..8] {m[off:off + 8].hex()} luma[last row mid] "
        f"{m[off + (H - 1) * W + W // 2:off + (H - 1) * W + W // 2 + 4].hex()} chroma[0..8] "
        f"{m[off + W * H:off + W * H + 8].hex()}")


def latch_wait(reg, label):
    t0 = time.monotonic()
    seen = []
    for t in (0.020, 0.050, 0.100):
        while time.monotonic() - t0 < t:
            pass
        seen.append(rd(reg))
    log(f"LATCH {label} {reg:#010x} at 20/50/100 ms: " + " ".join(f"{v:#x}" for v in seen))


def prog():
    y = FRAME
    c = FRAME + W * H
    seq = [
        (0x020, 0x043F077F, "VCH_SIZE"), (0x024, 0x00420077, "VCH_BLOCKS"),
        (0x040, 0x780, "VCH_YSTRIDE"), (0x044, 0x780, "VCH_CSTRIDE"),
        (0x048, 0x04380780, "VCH_YCROP"), (0x04C, 0x021C0780, "VCH_CCROP"),
        (0x030, 0x04380780, "VCH_OUTSIZE (T1 value)"),
        (0x060, 0x1, "VCH_GATE"), (0x064, 0x0, "VCH_FIELD"), (0x068, 0x122, "VCH_SRCSEL"),
        (0x080, 0, "unused"), (0x094, 0, "unused"), (0x0A8, 0, "unused"),
        (0x070, y, "Y slot 0"), (0x074, y, "Y slot 1"), (0x078, y, "Y slot 2"), (0x07C, y, "Y slot 3"),
        (0x084, c, "C slot 0"), (0x088, c, "C slot 1"), (0x08C, c, "C slot 2"), (0x090, c, "C slot 3"),
    ]
    for o, v, lab in seq:
        wr_logged(SC + o, v, lab)
    wr_logged(SC + 0x06C, 1, "VCH_ADDR_LATCH")
    latch_wait(SC + 0x06C, "VCH_ADDR_LATCH")
    wr_logged(SC + 0x010, 0x03000013, "VCH_CTRL")
    wr_logged(SC + 0x014, 1, "VCH_LATCH")
    latch_wait(SC + 0x014, "VCH_LATCH")


def vsync_poll(seconds=1.0):
    """Count video vsync status (SCANOUT +0x0c0 bit 0) by polling and write-1-clear."""
    st = SC + 0x0C0
    first = rd(st)
    n = 0
    raw = set()
    stamps = []
    t0 = time.monotonic()
    wr(st, 1)
    while time.monotonic() - t0 < seconds:
        v = rd(st)
        if v:
            raw.add(v)
        if v & 1:
            n += 1
            stamps.append(time.monotonic())
            wr(st, 1)
    iv = [b - a for a, b in zip(stamps, stamps[1:])]
    mean = f"{1000 * sum(iv) / len(iv):.2f} ms" if iv else "-"
    log(f"VSYNC poll {seconds:.1f} s: first read {first:#x}, bit0 events {n}, mean interval {mean}, raw values seen "
        + " ".join(f"{x:#x}" for x in sorted(raw)))


def obs(label):
    log(f"--- OBS {label}")
    rd_logged(SC + 0x010, 1, "VCH_CTRL")
    rd_logged(SC + 0x014, 1, "VCH_LATCH")
    rd_logged(SC + 0x020, 12, "ch0 geometry 0x020..0x04c")
    rd_logged(SC + 0x050, 8, "ch0 0x050..0x06c (ARMED at 0x058/0x05c)")
    rd_logged(SC + 0x070, 12, "ch0 slots 0x070..0x09c")
    rd_logged(SC + 0x0C0, 2, "SCAN_IRQ_STATUS/EN")
    rd_logged(SC + 0x140, 16, "ch2 0x140..0x17c")
    rd_logged(SC + 0x180, 2, "SCANOUT 0x180..0x184")
    rd_logged(SC + 0x300, 10, "SCANOUT 0x300..0x324")
    rd_logged(PNL + 0x06C, 1, "PNL_SEL")
    rd_logged(MIX, 1, "MIX")
    rd_logged(0x05140600, 2, "PROC probe 0x600/0x604")
    rd_logged(PNL + 0x144, 1, "PNL probe 0x144")
    rd_logged(PNL + 0x304, 1, "PNL probe 0x304")
    for k in range(2):
        rd_logged(PNL + 0x174, 1, f"PNL line counter #{k}")
        rd_logged(0x05880000, 1, f"TCON +0 counter #{k}")
        rd_logged(0x0514FE68, 1, f"PROC_LOCK panel vsync stamp #{k}")
        time.sleep(0.1)
    h = rd_logged(PNL + 0x380, 32, "histogram")
    log(f"HIST sum {sum(h)} nonzero bins " + " ".join(f"{i}:{v}" for i, v in enumerate(h) if v))
    vsync_poll(1.0)


if cmd == "fill":
    fill(sys.argv[3])
elif cmd == "prog":
    prog()
elif cmd == "sel":
    wr_logged(PNL + 0x06C, 0x39000000, "PNL_SEL video alone")
    wr_logged(MIX, 0x00000040, "MIX video shown")
elif cmd == "unsel":
    wr_logged(PNL + 0x06C, 0x00000000, "PNL_SEL back to bench value 0")
    wr_logged(MIX, 0x10000040, "MIX RGB alone")
elif cmd == "gate11":
    wr_logged(SC + 0x060, 0x11, "VCH_GATE 0x11")
    wr_logged(SC + 0x014, 1, "VCH_LATCH")
    latch_wait(SC + 0x014, "VCH_LATCH")
elif cmd == "relatch":
    wr_logged(SC + 0x06C, 1, "VCH_ADDR_LATCH")
    latch_wait(SC + 0x06C, "VCH_ADDR_LATCH")
    wr_logged(SC + 0x014, 1, "VCH_LATCH")
    latch_wait(SC + 0x014, "VCH_LATCH")
elif cmd == "wr":
    wr_logged(int(sys.argv[3], 0), int(sys.argv[4], 0), " ".join(sys.argv[5:]))
    log(f"  readback {rd(int(sys.argv[3], 0)):#010x}")
elif cmd == "rd":
    rd_logged(int(sys.argv[3], 0), int(sys.argv[4], 0) if len(sys.argv) > 4 else 1, " ".join(sys.argv[5:]))
elif cmd == "vsync":
    vsync_poll(float(sys.argv[3]) if len(sys.argv) > 3 else 1.0)
elif cmd == "off":
    wr_logged(SC + 0x010, rd(SC + 0x010) & ~3, "VCH_CTRL enable off")
    wr_logged(SC + 0x014, 1, "VCH_LATCH")
    latch_wait(SC + 0x014, "VCH_LATCH")
elif cmd == "obs":
    obs(sys.argv[3])
else:
    raise SystemExit(__doc__)
log(f"DONE {cmd}")
