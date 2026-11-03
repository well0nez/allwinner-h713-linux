#!/usr/bin/env python3
"""Q4: a 1280x720 NV12 frame scaled to the 1920x1080 panel, on top of the full 12 state (minimize.py all).
q4.py LOG    Evidence: panel histogram for an all-white, an all-black and a quadrant frame (white 640x360 top left),
before and after writing the scaled-state words (zoom720.json: [addr, value, 1:1 value]); scaler readback."""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr, wr_logged  # noqa: E402

SC = 0x05600000
W, H = 1280, 720
FR = {"white": 0x4C000000, "black": 0x6CA00000, "quad": 0x6CD00000}
openlog(sys.argv[1])
zoom = json.load(open("/data/bench/zoom720.json"))


def fill(addr, kind):
    m, off = map_ram(addr, W * H * 3 // 2)
    if kind == "quad":
        row_w = bytes([235]) * (W // 2) + bytes([16]) * (W // 2)
        m[off:off + (H // 2) * W] = row_w * (H // 2)
        m[off + (H // 2) * W:off + H * W] = bytes([16]) * (W * H // 2)
    else:
        m[off:off + W * H] = bytes([235 if kind == "white" else 16]) * (W * H)
    m[off + W * H:off + W * H * 3 // 2] = bytes([128, 128]) * (W * H // 4)


def show(addr):
    for o in (0x070, 0x074, 0x078, 0x07C):
        wr(SC + o, addr)
    for o in (0x084, 0x088, 0x08C, 0x090):
        wr(SC + o, addr + W * H)
    wr(SC + 0x06C, 1)


def hist():
    return [rd(0x051C0380 + 4 * i) for i in range(32)]


def test(label):
    for name, addr in FR.items():
        show(addr)
        time.sleep(0.08)
        h = hist()
        s = sum(h)
        log(f"Q4 {label} {name}: sum {s}, high (bins 24..31) {sum(h[24:])} = {100.0 * sum(h[24:]) / max(s, 1):.2f} %, "
            f"low (bins 0..8) {sum(h[:9])}; addr-latch {rd(SC + 0x06C)} VCH_LATCH {rd(SC + 0x014)}")


for k, a in FR.items():
    fill(a, k)
geo = [(0x020, 0x02CF04FF), (0x024, 0x002C004F), (0x040, 0x500), (0x044, 0x500), (0x048, 0x02D00500),
       (0x04C, 0x01680500), (0x030, 0x02D00500), (0x050, 0), (0x054, 0)]
for o, v in geo:
    wr_logged(SC + o, v, "channel 0 at 1280x720 (10 T3, VCH_OUTSIZE as the firmware's scaled state)")
show(FR["white"])
wr_logged(SC + 0x014, 1, "VCH_LATCH")
time.sleep(0.1)
test("channel 0 at 720p, rest of the chain at 1080p")
for a, v, _ in zoom:
    wr_logged(a, v, "scaled-state word")
wr_logged(SC + 0x014, 1, "VCH_LATCH")
time.sleep(0.1)
test("with the scaled-state words")
for base in (0x05180000, 0x05180100):
    log("SCL readback " + " ".join(f"{base + o:#010x}={rd(base + o):#010x}" for o in (0x000, 0x008, 0x014, 0x034, 0x038, 0x03C)))
log("PROC readback " + " ".join(f"{a:#010x}={rd(a):#010x}" for a in (0x05140104, 0x05140108, 0x0514011c, 0x05140124, 0x05140128)))
log("NRC readback " + " ".join(f"{a:#010x}={rd(a):#010x}" for a in (0x05000224, 0x05000804, 0x0500080c, 0x05000840, 0x05000844)))
