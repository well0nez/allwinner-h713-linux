#!/usr/bin/env python3
"""Raster start latency in a fresh B0: owner's init tables written in-process, then the time until the video raster
runs (line counter moves, PROC_LOCK fe74[31:16] = fe08[31:16]); then channel 0 per T1 with the two latch words and the
time until the latches are taken and 0x0c0 bit 0 sets.  r7.py LOG"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr  # noqa: E402

SC = 0x05600000
openlog(sys.argv[1])
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
WGAP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
tabs = json.load(open("/data/bench/inittables.json"))
t0 = time.monotonic()


def ms():
    return (time.monotonic() - t0) * 1000


def apply(name):
    for op, a, mask, val in tabs[name]:
        wr(a, val if mask == 0xFFFFFFFF else (rd(a) & ~mask & 0xFFFFFFFF) | (val & mask))
        if WGAP:
            time.sleep(WGAP)
    log(f"T {ms():8.2f} ms: {name} written; line {rd(0x051C0174):#x} fe74 {rd(0x0514FE74):#x} 0x0c0 {rd(SC + 0xC0):#x}")


def watch(label, cond, limit=2.0):
    s = time.monotonic()
    while time.monotonic() - s < limit:
        if cond():
            log(f"T {ms():8.2f} ms: {label} after {1000 * (time.monotonic() - s):.2f} ms")
            return
    log(f"T {ms():8.2f} ms: {label} NOT within {limit} s")


log(f"start: line {rd(0x051C0174):#x} fe74 {rd(0x0514FE74):#x} fe08 {rd(0x0514FE08):#x} 0x0c0 {rd(SC + 0xC0):#x}")
log(f"pacing: {GAP} s between tables, {WGAP} s after each write")
for t in ("INIT_VPANEL", "INIT_VPROC", "INIT_VNR", "INIT_VDEINT", "DBUS_MP_RST_PROJECTOR"):
    apply(t)
    time.sleep(GAP)
wr(0x0514FE08, 0x04640897)
wr(0x051CFE08, 0x04640897)
log(f"T {ms():8.2f} ms: lock totals written")
l0 = rd(0x051C0174)
watch("line counter moved", lambda: rd(0x051C0174) != l0)
watch("fe74[31:16] = 0x0464", lambda: (rd(0x0514FE74) >> 16) == 0x0464)
wr(SC + 0xC0, 1)
time.sleep(0.1)
log(f"T {ms():8.2f} ms: 0x0c0 100 ms after clearing, channel 0 still off: {rd(SC + 0xC0):#x}")
# channel 0 per T1 at a reserved address, then the two latch words
F = 0x4C000000
for o, v in [(0x020, 0x043F077F), (0x024, 0x00420077), (0x040, 0x780), (0x044, 0x780), (0x048, 0x04380780),
             (0x04C, 0x021C0780), (0x030, 0x04380780), (0x060, 1), (0x064, 0), (0x068, 0x122)]:
    wr(SC + o, v)
for o in (0x070, 0x074, 0x078, 0x07C):
    wr(SC + o, F)
for o in (0x084, 0x088, 0x08C, 0x090):
    wr(SC + o, F + 1920 * 1080)
wr(SC + 0x06C, 1)
wr(SC + 0x010, 0x03000013)
wr(SC + 0x014, 1)
log(f"T {ms():8.2f} ms: channel 0 enabled and latched (no latch words yet)")
watch("0x0c0 bit 0 set with channel 0 on", lambda: rd(SC + 0xC0) & 1, 1.0)
wr(0x0500046C, 0x006F81C1)
wr(0x05000840, 0x04390010)
log(f"T {ms():8.2f} ms: NRC latch words written")
watch("VCH_LATCH taken", lambda: rd(SC + 0x014) == 0, 1.0)
log(f"PNL 0x148 {rd(0x051C0148):#x} 0x158 {rd(0x051C0158):#x} line {rd(0x051C0174):#x}")
log("R7 DONE")
