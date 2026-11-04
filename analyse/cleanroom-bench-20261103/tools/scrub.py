#!/usr/bin/env python3
"""scrub.py DIR...: replace MAC addresses and device serials in text logs with fixed placeholders (in place)."""
import os, re, sys
MAC = re.compile(rb"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
SER = re.compile(rb"(serial#?[=:\s]+)([0-9A-Za-z]{8,})")
n = 0
for root in sys.argv[1:]:
    for dp, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            try:
                b = open(p, "rb").read()
            except OSError:
                continue
            if b"\0" in b[:4096] and not p.endswith((".log", ".txt")):
                continue
            c = MAC.sub(b"xx:xx:xx:xx:xx:xx", b)
            c = SER.sub(lambda m: m.group(1) + b"XXXXXXXXXXXXXXXX", c)
            if c != b:
                open(p, "wb").write(c); n += 1; print("scrubbed", p)
print(n, "files")
