#!/usr/bin/env python3
"""or1k-disasm.py -- ein kleiner OpenRISC-1000-Dekoder.

Gebaut fuer die ARISC/SCP-Firmware des H713 (analyse/arisc/scp-wordswapped.bin).
Weder IDA 9.1 noch Capstone 5.0.7 bringen ein OR1K-Modul mit -- geprueft, in
IDAs procs/ gibt es kein or1k/openrisc, und CS_ARCH_* kennt keins.

Wichtig zur Datei: der Blob liegt im sunxi-package **wortweise byte-gespiegelt**.
Das Speicherabbild ist die entspiegelte Form (statistisch entschieden: 445
wortausgerichtete l.nop gegen 3, und der Reset-Vektor bei 0x100 wird nur so zu
einem l.j). Dieses Werkzeug erwartet die **entspiegelte** Datei; mit --swap
spiegelt es selbst.

Adressen == Dateioffsets: das Image wird auf OR1K-Adresse 0 geladen.

  or1k-disasm.py <datei> [--swap] dis <start> [laenge]
  or1k-disasm.py <datei> [--swap] refs <lo> [hi]     wer greift auf [lo,hi) zu
  or1k-disasm.py <datei> [--swap] stats
"""

import argparse
import struct
import sys

# Opcode [31:26] -> (Name, Format)
#   I  : opcode | D(5) | A(5) | imm16          l.lwz rD, imm(rA)
#   S  : opcode | imm[15:11] | A(5) | B(5) | imm[10:0]   l.sw imm(rA), rB
#   RI : opcode | D(5) | A(5) | imm16          l.addi rD, rA, imm
#   MOV: opcode | D(5) | ----- | imm16         l.movhi rD, imm
#   J  : opcode | imm26
OPS = {
    0x00: ("l.j",      "J"),
    0x01: ("l.jal",    "J"),
    0x03: ("l.bnf",    "J"),
    0x04: ("l.bf",     "J"),
    0x05: ("l.nop",    "N"),
    0x06: ("l.movhi",  "MOV"),
    0x08: ("l.sys",    "N"),
    0x09: ("l.rfe",    "N"),
    0x11: ("l.jr",     "JR"),
    0x12: ("l.jalr",   "JR"),
    0x21: ("l.lwz",    "I"),
    0x22: ("l.lws",    "I"),
    0x23: ("l.lbz",    "I"),
    0x24: ("l.lbs",    "I"),
    0x25: ("l.lhz",    "I"),
    0x26: ("l.lhs",    "I"),
    0x27: ("l.addi",   "RI"),
    0x28: ("l.addic",  "RI"),
    0x29: ("l.andi",   "RI"),
    0x2A: ("l.ori",    "RI"),
    0x2B: ("l.xori",   "RI"),
    0x2C: ("l.muli",   "RI"),
    0x2D: ("l.mfspr",  "RI"),
    0x2E: ("shift-i",  "SH"),
    0x2F: ("l.sf*i",   "SFI"),
    0x30: ("l.mtspr",  "MT"),
    0x35: ("l.sw",     "S"),
    0x36: ("l.sb",     "S"),
    0x37: ("l.sh",     "S"),
    0x38: ("alu",      "ALU"),
    0x39: ("l.sf*",    "SF"),
}

ALU = {0x0: "l.add", 0x1: "l.addc", 0x2: "l.sub", 0x3: "l.and", 0x4: "l.or",
       0x5: "l.xor", 0x6: "l.mul", 0x8: "shift", 0x9: "l.div", 0xa: "l.divu",
       0xb: "l.mulu", 0xe: "l.cmov", 0xf: "l.ff1"}

SF = {0x0: "sfeq", 0x1: "sfne", 0x2: "sfgtu", 0x3: "sfgeu", 0x4: "sfltu",
      0x5: "sfleu", 0xa: "sfgts", 0xb: "sfges", 0xc: "sflts", 0xd: "sfles"}


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def s26(v):
    return v - 0x4000000 if v & 0x2000000 else v


def decode(w, pc):
    """-> (text, mem_ref_or_None). mem_ref = (basisreg, offset) bei r0-Basis."""
    op = w >> 26
    name, fmt = OPS.get(op, ("?0x%02x" % op, "?"))
    D = (w >> 21) & 0x1F
    A = (w >> 16) & 0x1F
    B = (w >> 11) & 0x1F
    imm16 = w & 0xFFFF

    if fmt == "J":
        tgt = (pc + s26(w & 0x3FFFFFF) * 4) & 0xFFFFFFFF
        return "%-9s 0x%x" % (name, tgt), None
    if fmt == "N":
        return ("l.nop" if w == 0x15000000 else name), None
    if fmt == "JR":
        return "%-9s r%d" % (name, B), None
    if fmt == "MOV":
        return "%-9s r%d, 0x%04x" % (name, D, imm16), None
    if fmt in ("I",):
        off = s16(imm16)
        ref = (A, off)
        return "%-9s r%d, %d(r%d)" % (name, D, off, A), ref
    if fmt == "S":
        off = s16(((w >> 10) & 0xF800) | (w & 0x7FF))
        ref = (A, off)
        return "%-9s %d(r%d), r%d" % (name, off, A, B), ref
    if fmt in ("RI", "SFI"):
        return "%-9s r%d, r%d, 0x%04x" % (name, D, A, imm16), None
    if fmt == "SH":
        kind = {0: "l.slli", 1: "l.srli", 2: "l.srai", 3: "l.rori"}.get((w >> 6) & 3, "l.sh?i")
        return "%-9s r%d, r%d, %d" % (kind, D, A, w & 0x3F), None
    if fmt == "MT":
        off = ((w >> 10) & 0xF800) | (w & 0x7FF)
        return "%-9s r%d, r%d, 0x%x" % (name, A, B, off), None
    if fmt == "ALU":
        kind = ALU.get(w & 0xF, "alu?")
        if (w & 0xF) == 8:
            kind = {0: "l.sll", 1: "l.srl", 2: "l.sra", 3: "l.ror"}.get((w >> 6) & 3, "shift?")
        return "%-9s r%d, r%d, r%d" % (kind, D, A, B), None
    if fmt == "SF":
        return "%-9s r%d, r%d" % ("l." + SF.get((w >> 21) & 0x1F, "sf?"), A, B), None
    return "%-9s 0x%08x" % (name, w), None


def load(path, swap):
    b = open(path, "rb").read()
    if swap:
        b = b"".join(b[i:i + 4][::-1] for i in range(0, len(b) - 3, 4))
    return b


def words(b):
    n = len(b) // 4
    return struct.unpack(">%dI" % n, b[:n * 4])


def cmd_dis(b, start, length):
    w = words(b)
    for pc in range(start, min(start + length, len(w) * 4), 4):
        insn = w[pc // 4]
        txt, _ = decode(insn, pc)
        print("  %06x  %08x  %s" % (pc, insn, txt))


def cmd_refs(b, lo, hi):
    """Alle Zugriffe mit r0-Basis, deren Offset in [lo,hi) faellt.

    r0 ist auf OR1K fest 0, ein Zugriff mit Basis r0 adressiert also absolut.
    """
    w = words(b)
    hits = []
    for i, insn in enumerate(w):
        pc = i * 4
        txt, ref = decode(insn, pc)
        if ref and ref[0] == 0 and lo <= ref[1] < hi:
            hits.append((pc, insn, txt, ref[1]))
    print("Zugriffe mit r0-Basis auf [0x%x,0x%x): %d" % (lo, hi, len(hits)))
    for pc, insn, txt, off in hits:
        print("  %06x  %08x  %-34s -> 0x%x" % (pc, insn, txt, off))
    return hits


def cmd_stats(b):
    w = words(b)
    from collections import Counter
    c = Counter(x >> 26 for x in w if x)
    print("l.nop wortausgerichtet: %d" % sum(1 for x in w if x == 0x15000000))
    print("Opcodes, haeufigste:")
    for op, n in c.most_common(12):
        nm = OPS.get(op, ("?", ""))[0]
        print("  0x%02x %-9s %6d" % (op, nm, n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--swap", action="store_true", help="Datei wortweise spiegeln")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dis");   d.add_argument("start"); d.add_argument("length", nargs="?", default="0x80")
    r = sub.add_parser("refs");  r.add_argument("lo");    r.add_argument("hi", nargs="?")
    sub.add_parser("stats")
    a = ap.parse_args()

    b = load(a.file, a.swap)
    if a.cmd == "dis":
        cmd_dis(b, int(a.start, 0), int(a.length, 0))
    elif a.cmd == "refs":
        lo = int(a.lo, 0)
        hi = int(a.hi, 0) if a.hi else lo + 4
        cmd_refs(b, lo, hi)
    else:
        cmd_stats(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
