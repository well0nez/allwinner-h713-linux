#!/usr/bin/env python3
"""Replay register groups of a firmware-state snapshot onto the bench state; after each group pulse the channel-0
latches and check whether they are taken.  replay.py LOG JSON GROUP [GROUP ...]   (GROUP 'check' = check only)"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr, wr_logged  # noqa: E402

SC = 0x05600000
openlog(sys.argv[1])
groups = json.load(open(sys.argv[2]))


def check(label):
    wr_logged(SC + 0x06C, 1, "VCH_ADDR_LATCH")
    wr_logged(SC + 0x014, 1, "VCH_LATCH")
    t0 = time.monotonic()
    v310, armed = set(), set()
    while time.monotonic() - t0 < 0.2:
        v310.add(rd(SC + 0x310))
        armed.add((rd(SC + 0x058), rd(SC + 0x05C)))
    log(f"CHECK {label}: VCH_LATCH {rd(SC + 0x014):#x} ADDR_LATCH {rd(SC + 0x06C):#x} "
        f"ARMED {sorted(armed)[:4]} 0x310 {[hex(x) for x in sorted(v310)]} 0x320 {rd(SC + 0x320):#x} "
        f"PNL line {rd(0x051C0174):#x} fe64 {rd(0x0514FE64):#x}")


for g in sys.argv[3:]:
    if g == "check":
        check(g)
    elif g.endswith(":each"):
        lst = groups[g[:-5]]
        log(f"REPLAY {g}: {len(lst)} words, one at a time")
        for a, v in lst:
            wr_logged(a, v, f"replay {g}")
            check(f"{g} {a:#010x}={v:#010x}")
            if rd(SC + 0x014) == 0:
                log(f"LATCHED after {a:#010x}")
                break
    else:
        lst = groups[g]
        log(f"REPLAY {g}: {len(lst)} words")
        for a, v in lst:
            wr_logged(a, v, f"replay {g}")
        check(g)
