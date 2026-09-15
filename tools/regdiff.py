#!/usr/bin/env python3
"""
regdiff.py - zwei uart-capture-Mitschnitte vergleichen.

  ./regdiff.py stock.txt ours.txt

Liest alle 'ADDR: w0 w1 w2 w3' Zeilen aus beiden Dateien und meldet jede
Adresse, die sich unterscheidet oder nur in einer Datei vorkommt.
"""
import re, sys

LINE = re.compile(r"^([0-9a-f]{8}):((?:\s+[0-9a-f]{8})+)", re.I)

def load(path):
    regs = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = LINE.match(line.strip())
        if not m:
            continue
        base = int(m.group(1), 16)
        for i, w in enumerate(m.group(2).split()):
            regs[base + i * 4] = int(w, 16)
    return regs

def main():
    if len(sys.argv) != 3:
        sys.exit("usage: regdiff.py <a.txt> <b.txt>")
    a, b = load(sys.argv[1]), load(sys.argv[2])
    na, nb = sys.argv[1].split("/")[-1], sys.argv[2].split("/")[-1]
    both = sorted(set(a) | set(b))
    diff = [x for x in both if x in a and x in b and a[x] != b[x]]
    only_a = [x for x in both if x in a and x not in b]
    only_b = [x for x in both if x in b and x not in a]

    print("%d Adressen in %s, %d in %s, %d gemeinsam\n"
          % (len(a), na, len(b), nb, len(set(a) & set(b))))
    if diff:
        print("%-12s %-10s %-10s" % ("Adresse", na[:10], nb[:10]))
        print("-" * 36)
        for x in diff:
            print("%08x     %08x   %08x" % (x, a[x], b[x]))
    else:
        print("keine Unterschiede an gemeinsamen Adressen")
    for name, lst in ((na, only_a), (nb, only_b)):
        if lst:
            print("\nnur in %s: %d Adressen (%08x .. %08x)"
                  % (name, len(lst), lst[0], lst[-1]))

if __name__ == "__main__":
    main()
