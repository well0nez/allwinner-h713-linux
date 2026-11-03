#!/usr/bin/env python3
"""Apply one of the owner's init tables (extracted from database.TSE into inittables.json). q1init.py LOG NAME"""
import json
import sys

sys.path.insert(0, "/data/bench")
from blog import log, openlog, rd, wr_logged  # noqa: E402

openlog(sys.argv[1])
name = sys.argv[2]
tab = json.load(open("/data/bench/inittables.json"))[name]
log(f"TABLE {name}: {len(tab)} writes")
for op, a, mask, val in tab:
    if mask == 0xFFFFFFFF:
        new = val
    else:
        new = (rd(a) & ~mask & 0xFFFFFFFF) | (val & mask)
    wr_logged(a, new, f"{name} {op} mask={mask:#x} val={val:#x}")
log(f"TABLE {name} applied")
