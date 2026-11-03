#!/usr/bin/env python3
"""32-bit dumps, each window's first read logged and fsynced first. wdump.py LOG LABEL BASE:SIZE ..."""
import sys
sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd  # noqa: E402
openlog(sys.argv[1])
for w in sys.argv[3:]:
    b, s = (int(x, 16) for x in w.split(":"))
    log(f"BEFORE-READ {sys.argv[2]} {b:#010x}+{s:#x}")
    for a in range(b, b + s, 16):
        log(f"DUMP {sys.argv[2]} w {a:#010x}: " + " ".join(f"{rd(a + 4 * i):08x}" for i in range(4)))
