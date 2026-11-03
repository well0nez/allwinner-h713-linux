#!/usr/bin/env python3
"""Polled delay video vsync status (0x056000c0 bit 0) -> next RGB done status (0x05600168 bit 1), 0.5 s."""
import sys, time
sys.path.insert(0, "/data/bench")
from blog import rd, wr
SC = 0x05600000
wr(SC + 0xC0, 1); wr(SC + 0x168, 2); tv, tr = [], []; t0 = time.perf_counter()
while time.perf_counter() - t0 < 0.5:
    if rd(SC + 0xC0) & 1: tv.append(time.perf_counter()); wr(SC + 0xC0, 1)
    if rd(SC + 0x168) & 2: tr.append(time.perf_counter()); wr(SC + 0x168, 2)
d = sorted((min([x for x in tr if x > v], default=v) - v) * 1e3 for v in tv); d = [x for x in d if x > 0]
print(f"POLLED vsync status -> RGB done status: median {d[len(d)//2]:.4f} ms (min {d[0]:.4f} max {d[-1]:.4f}, {len(tv)} vsync, {len(tr)} done)" if d else f"POLLED none: {len(tv)} vsync {len(tr)} done")
