#!/usr/bin/env python3
"""Sample 0x05600310 for N seconds: share of reads with bit 21 clear, distinct values."""
import sys, time, collections
sys.path.insert(0, "/data/bench")
from blog import rd
sec = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
c = collections.Counter(); n = 0; t0 = time.perf_counter()
while time.perf_counter() - t0 < sec:
    c[rd(0x05600310)] += 1; n += 1
clear = sum(v for k, v in c.items() if not k & (1 << 21))
print(f"S310 {n} reads in {sec} s: bit 21 clear in {clear} ({100.0 * clear / n:.2f} %); values {dict((hex(k), v) for k, v in c.most_common(6))}")
