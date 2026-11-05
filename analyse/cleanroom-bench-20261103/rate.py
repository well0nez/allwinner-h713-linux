#!/usr/bin/env python3
"""Read-only: raster rates over SECONDS. rate.py LOG LABEL [SECONDS]
PNL frame counter 0x051c0174[31:16]; number of value changes per second of the lock blocks' time stamps (fe64 input,
fe68 panel) and of channel 2's status word; rising edges of SCANOUT 0x056000c0 bit 0 (not cleared here)."""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd  # noqa: E402

openlog(sys.argv[1])
label = sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
stamps = {"PROC_LOCK fe64": 0x0514FE64, "PROC_LOCK fe68": 0x0514FE68, "PNL_LOCK fe64": 0x051CFE64,
          "PNL_LOCK fe68": 0x051CFE68}
schg = {k: 0 for k in stamps}
slast = {k: rd(a) for k, a in stamps.items()}
f0 = rd(0x051C0174) >> 16
edges = 0
prev_st = rd(0x056000C0) & 1
n = 0
t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    for k, a in stamps.items():
        v = rd(a)
        if v != slast[k]:
            schg[k] += 1
            slast[k] = v
    st = rd(0x056000C0) & 1
    if st and not prev_st:
        edges += 1
    prev_st = st
    n += 1
dt = time.monotonic() - t0
f1 = rd(0x051C0174) >> 16
log(f"RATE {label}: {n} samples, {dt:.2f} s; PNL frames {((f1 - f0) & 0xFFFF) / dt:.2f}/s; "
    + "; ".join(f"{k} changes {v / dt:.2f}/s" for k, v in schg.items()) + f"; 0x0c0 bit0 rising {edges / dt:.2f}/s")
