#!/usr/bin/env python3
"""envrestore2.py REF: make the U-Boot env equal to REF (fw_printenv output), names with spaces included (split at
the first '='); one fw_setenv NAME [VALUE] per change, argv-safe. Spec side, 2026-11-04."""
import subprocess, sys
def parse(lines):
    d = {}
    for l in lines:
        k, sep, v = l.rstrip("\n").partition("=")
        if sep:
            d[k] = v
    return d
ref = parse(open(sys.argv[1]))
cur = parse(subprocess.run(["fw_printenv"], capture_output=True, text=True).stdout.splitlines())
for k in cur:
    if k not in ref:
        subprocess.run(["fw_setenv", k], check=True); print("unset", k[:50])
for k, v in ref.items():
    if cur.get(k) != v:
        subprocess.run(["fw_setenv", k, v], check=True); print("set", k[:50])
