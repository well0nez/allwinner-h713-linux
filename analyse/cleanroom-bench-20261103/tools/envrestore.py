#!/usr/bin/env python3
"""Restore the U-Boot env to a reference, touching only well-formed names (no spaces) that differ."""
import subprocess, sys
def parse(lines):
    d = {}
    for l in lines:
        k, sep, v = l.rstrip("\n").partition("=")
        if sep and " " not in k:
            d[k] = v
    return d
ref = parse(open(sys.argv[1]))
cur = parse(subprocess.run(["fw_printenv"], capture_output=True, text=True).stdout.splitlines())
for k in cur:
    if k not in ref:
        subprocess.run(["fw_setenv", k]); print("unset", k)
for k, v in ref.items():
    if cur.get(k) != v:
        subprocess.run(["fw_setenv", k, v]); print("set", k)
