#!/usr/bin/env python3
"""Read-only: sample the channel-0 activity words for SECONDS and say which moved. mon.py LOG LABEL [SECONDS]"""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, rd_logged  # noqa: E402

openlog(sys.argv[1])
label = sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
words = [
    ("VCH_CTRL", 0x05600010), ("VCH_LATCH", 0x05600014), ("VCH_ARMED0", 0x05600058), ("VCH_ARMED1", 0x0560005C),
    ("VCH_ADDR_LATCH", 0x0560006C), ("VCH_Y0", 0x05600070), ("SCAN_ST", 0x056000C0), ("SC_300", 0x05600300),
    ("SC_304", 0x05600304), ("SC_30C", 0x0560030C), ("SC_310", 0x05600310), ("SC_320", 0x05600320),
    ("SC_324", 0x05600324), ("PNL_LINE", 0x051C0174), ("PL_FE64", 0x0514FE64), ("PL_FE68", 0x0514FE68),
    ("PNL_SEL", 0x051C006C), ("MIX", 0x058C0000), ("CH2_CTRL", 0x05600140),
]
for name, a in words:
    rd_logged(a, 1, f"{label} {name}")
seen = {name: set() for name, _ in words}
n = 0
t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    for name, a in words:
        if len(seen[name]) < 64:
            seen[name].add(rd(a))
    n += 1
log(f"MON {label}: {n} samples over {secs:.1f} s")
for name, a in words:
    s = sorted(seen[name])
    tag = "MOVES" if len(s) > 1 else "still"
    shown = " ".join(f"{v:#x}" for v in s[:6]) + (" ..." if len(s) > 6 else "")
    log(f"  {name:15s} {a:#010x} {tag} ({len(s)} values) {shown}")
