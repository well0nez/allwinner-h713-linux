#!/usr/bin/env python3
"""Round 4 (stage 1 for the clean side). r4.py LOG STEP ...
handoff  : read the B0 state of the stage-1 blocks (log first)
rate     : 20 s of the RGB channel's done bit (0x05600168 bit 1, write-1-clear): frames per second
gic      : GIC distributor pending/enable words while the display status bits are set/cleared/enabled
rgbflip  : two XRGB buffers in reserved DRAM, address-only flips of the RGB channel with and without its latch
"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, rd_logged, wr, wr_logged  # noqa: E402

SC = 0x05600000
GICD = 0x03021000
openlog(sys.argv[1])


def handoff():
    for label, a, n in [
        ("CCU 0x02001000..0x0200100c", 0x02001000, 4), ("CCU video PLL 0x02001050", 0x02001050, 1),
        ("CCU 0x02001150", 0x02001150, 1), ("CCU co-processor 0x02001600", 0x02001600, 4),
        ("CCU display 0x02001db0..0x02001ddc", 0x02001DB0, 12), ("CCU 0x02001d64", 0x02001D64, 1),
        ("DTOP", 0x05700000, 35), ("TCON 0x05880000..0x058800fc", 0x05880000, 64),
        ("LVDS 0x05800000..0x0580003c", 0x05800000, 16),
        ("MIX 0x058c0000..0x058c003c", 0x058C0000, 16), ("MIX 0x058c1000", 0x058C1000, 2),
        ("OSD 0x0524c000..0x0524c0fc", 0x0524C000, 64), ("RASTER 0x0525c000..0x0525c07c", 0x0525C000, 32),
        ("SCANOUT top 0x05600000..0x0560000c", 0x05600000, 4), ("SCANOUT irq 0x056000c0..0x056000fc", 0x056000C0, 16),
        ("SCANOUT ch1 0x05600100..0x0560013c", 0x05600100, 16), ("SCANOUT ch2 0x05600140..0x056001fc", 0x05600140, 48),
        ("SCANOUT 0x05600300..0x05600324", 0x05600300, 10),
        ("PNL 0x051c0000..0x051c007c", 0x051C0000, 32), ("PNL 0x051c0170..0x051c017c", 0x051C0170, 4),
        ("GIC enable SPI words 0x03021100..0x0302111c", GICD + 0x100, 8),
        ("GIC pending 0x03021200..0x0302121c", GICD + 0x200, 8),
    ]:
        rd_logged(a, n, label)
    first = [rd(0x05880000), rd(0x05600184), rd(0x051C0174)]
    time.sleep(0.037)
    log(f"MOVING? TCON+0 {first[0]:#x}->{rd(0x05880000):#x} SCANOUT 0x184 {first[1]:#x}->{rd(0x05600184):#x} "
        f"PNL line {first[2]:#x}->{rd(0x051C0174):#x}")


def rate(secs=20.0):
    wr(SC + 0x168, 2)
    stamps = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        if rd(SC + 0x168) & 2:
            stamps.append(time.monotonic())
            wr(SC + 0x168, 2)
    n = len(stamps) - 1
    per = (stamps[-1] - stamps[0]) / n
    iv = [b - a for a, b in zip(stamps, stamps[1:])]
    log(f"RATE RGB done bit: {n} intervals over {stamps[-1] - stamps[0]:.3f} s: {1 / per:.3f} frames/s, "
        f"period {per * 1000:.4f} ms (min {min(iv) * 1000:.3f}, max {max(iv) * 1000:.3f}); "
        f"pixel clock at 2200 x 1125 = {2200 * 1125 / per / 1e6:.3f} MHz")


def pend(word=4):
    return rd(GICD + 0x200 + 4 * word)


def gic_snapshot(label):
    p = [rd(GICD + 0x200 + 4 * w) for w in range(1, 8)]
    e = [rd(GICD + 0x100 + 4 * w) for w in range(1, 8)]
    log(f"GIC {label}: pending words 1..7 " + " ".join(f"{x:08x}" for x in p)
        + " | enable words 1..7 " + " ".join(f"{x:08x}" for x in e)
        + f" | SCAN 0x0c0 {rd(SC + 0xC0):#x} 0x0c4 {rd(SC + 0xC4):#x} ch2 0x168 {rd(SC + 0x168):#x} 0x16c {rd(SC + 0x16C):#x}")
    return p


def gic():
    log("GIC: SPI n is GIC id n+32; id 142 (SPI 110) = pending word 4 bit 14")
    a = gic_snapshot("as left")
    wr_logged(SC + 0x168, 2, "clear the RGB done bit")
    b = gic_snapshot("RGB done cleared")
    time.sleep(0.05)
    c = gic_snapshot("50 ms later (done bit set again by the hardware?)")
    # try each low bit of 0x16c as an enable for the done bit; restore after
    orig = rd(SC + 0x16C)
    for bit in range(0, 8):
        v = orig | (1 << bit)
        if v == orig:
            continue
        wr_logged(SC + 0x16C, v, f"0x16c with bit {bit} added")
        time.sleep(0.05)
        gic_snapshot(f"0x16c bit {bit} set")
        wr(SC + 0x168, 2)
        time.sleep(0.002)
        gic_snapshot(f"0x16c bit {bit} set, done bit just cleared")
        wr_logged(SC + 0x16C, orig, "0x16c restored")
    wr_logged(SC + 0xC4, 1, "SCAN_IRQ_EN bit 0")
    time.sleep(0.05)
    gic_snapshot("SCAN_IRQ_EN=1")
    wr(SC + 0xC0, 1)
    time.sleep(0.001)
    gic_snapshot("SCAN_IRQ_EN=1, 0x0c0 just cleared")
    wr_logged(SC + 0xC4, 0, "SCAN_IRQ_EN back to 0")
    time.sleep(0.05)
    gic_snapshot("SCAN_IRQ_EN=0")


def fill_xrgb(addr, word):
    m, off = map_ram(addr, 1920 * 1080 * 4)
    m[off:off + 1920 * 1080 * 4] = word.to_bytes(4, "little") * (1920 * 1080)


def hist():
    h = [rd(0x051C0380 + 4 * i) for i in range(32)]
    return sum(h), sum(h[24:]), sum(h[:9])


def rgbflip():
    A, B = 0x4C000000, 0x4C800000
    fill_xrgb(A, 0xFFFFFFFF)
    fill_xrgb(B, 0xFF000000)
    log(f"buffers: white XRGB at {A:#x}, black at {B:#x}; logo address {rd(SC + 0x178):#x}")
    for addr, name in ((A, "white"), (B, "black")):
        wr_logged(SC + 0x178, addr, f"RGB address -> {name}, no latch")
        time.sleep(0.2)
        s, hi, lo = hist()
        log(f"FLIP no latch {name}: 0x178 {rd(SC + 0x178):#x} 0x144 {rd(SC + 0x144):#x} hist sum {s} high {hi} low {lo}")
        wr_logged(SC + 0x144, 1, "RGB latch")
        t0 = time.monotonic()
        while rd(SC + 0x144) & 1 and time.monotonic() - t0 < 0.2:
            pass
        dt = (time.monotonic() - t0) * 1000
        time.sleep(0.1)
        s, hi, lo = hist()
        log(f"FLIP latched {name}: latch cleared after {dt:.2f} ms (read {rd(SC + 0x144):#x}); hist sum {s} high {hi} low {lo}")


for step in sys.argv[2:]:
    {"handoff": handoff, "rate": rate, "gic": gic, "rgbflip": rgbflip}[step]()
log("R4 DONE")
