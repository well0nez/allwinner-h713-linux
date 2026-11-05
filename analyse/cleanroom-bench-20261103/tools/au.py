#!/usr/bin/env python3
"""Spec 70 §9 N1-N3 (normal boot, read-only apart from the DSP mailbox read requests). Spec side, 2026-11-04.
au.py LOG dump LABEL      8-bit dumps: RX_APLL 0x06880000..0xff, RX_LINK 0x06840000..0x7ff, 0x06841000..0x7ff
au.py LOG sel SECS        sample RX_LINK +0x112 with +0x113..+0x12f and +0x1c0..+0x1de, grouped by the selector
au.py LOG trace SECS      log every change of RX_LINK 0..0x7ff, 0x1000..0x17ff and RX_APLL 0..0xff (8-bit) with its time
au.py LOG state LABEL     32-bit dumps: AU_TOP, AU_CTL, AU_MBOX (no request), AU_BRG, AU_IF (only if AU_TOP+0 = 0x700),
                          CODEC, CODEC_I2S, CCU audio/codec words, TVFE_RT
au.py LOG dsp LABEL       DSP registers through the mailbox read protocol of 70 §4.3 (reads only)
Every block's first access is logged and fsynced before it happens."""
import mmap, os, struct, sys, time

LOG = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
maps = {}


def log(s):
    os.write(LOG, f"{time.monotonic():10.3f} {s}\n".encode()); os.fsync(LOG)


def page(a):
    b = a & ~0xfff
    if b not in maps:
        log(f"FIRST-ACCESS page {b:#010x}")
        maps[b] = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=b)
    return maps[b], a & 0xfff


def r8(a):
    m, o = page(a); return m[o]


def r32(a):
    m, o = page(a); return struct.unpack_from("<I", m, o)[0]


def w32(a, v):
    m, o = page(a); struct.pack_into("<I", m, o, v)


def bytes_line(base, n):
    return " ".join(f"{r8(base + i):02x}" for i in range(n))


cmd = sys.argv[2]
log(f"=== au.py {' '.join(sys.argv[2:])} boot {open('/proc/sys/kernel/random/boot_id').read().strip()}")
if cmd == "dump":
    lab = sys.argv[3]
    for base, n in ((0x06880000, 0x100), (0x06840000, 0x800), (0x06841000, 0x800)):
        for o in range(0, n, 0x20):
            log(f"D8 {lab} {base + o:#010x}: {bytes_line(base + o, 0x20)}")
elif cmd == "sel":
    secs = float(sys.argv[3]); seen = {}
    t0 = time.monotonic(); n = 0
    while time.monotonic() - t0 < secs:
        s = r8(0x06840112); a = bytes_line(0x06840113, 0x1d); b = bytes_line(0x068401c0, 0x1f); s2 = r8(0x06840112)
        n += 1
        if s == s2:
            seen.setdefault((s, a, b), 0); seen[(s, a, b)] += 1
    log(f"SEL {n} samples, {len(seen)} distinct")
    for (s, a, b), c in sorted(seen.items(), key=lambda x: -x[1]):
        log(f"SEL sel {s:02x} x{c}: +0x113.. {a} | +0x1c0.. {b}")
elif cmd == "trace":
    secs = float(sys.argv[3])
    regions = ((0x06840000, 0x800), (0x06841000, 0x800), (0x06880000, 0x100))
    for b, n in regions:
        page(b)

    def snap():
        out = {}
        for b, n in regions:
            m, _ = page(b); raw = bytes(m[i] for i in range(n))
            for i, v in enumerate(raw):
                out[b + i] = v
        return out
    t0 = time.monotonic(); prev = snap(); k = 0
    log(f"TRACE start, {len(prev)} bytes")
    while time.monotonic() - t0 < secs:
        cur = snap(); k += 1
        ch = [(a, prev[a], v) for a, v in cur.items() if prev[a] != v]
        if ch:
            log(f"T {time.monotonic() - t0:.3f} " + " ".join(f"{a:#010x}:{x:02x}>{y:02x}" for a, x, y in ch))
        prev = cur
    log(f"TRACE end, {k} snapshots")
elif cmd == "state":
    lab = sys.argv[3]

    def words(name, base, n):
        log(f"W32 {lab} {name} {base:#010x}: " + " ".join(f"{r32(base + o):08x}" for o in range(0, n, 4)))
    words("AU_TOP", 0x0614a000, 0x10)
    words("AU_CTL", 0x06142000, 0x80)
    words("AU_MBOX", 0x06144000, 0x20)
    words("AU_BRG", 0x06148000, 0x394)
    if r32(0x0614a000) & 0x700 == 0x700:
        words("AU_IF", 0x06146000, 0x90)
    else:
        log(f"AU_IF skipped: AU_TOP +0 = {r32(0x0614a000):08x}")
    words("TVFE_RT", 0x06700000, 0x10)
    words("CODEC", 0x02030000, 0x330)
    words("CODEC_I2S", 0x02031000, 0x80)
    words("CODEC_LOCK", 0x02031078, 4)
    for a in (0x02001020, 0x02001028, 0x02001068, 0x02001078, 0x02001d48, 0x02001d4c, 0x02001d50, 0x02001d64,
              0x02001d80, 0x02001d84, 0x02001a60, 0x02001a64, 0x02001a6c):
        log(f"CCU {lab} {a:#010x} = {r32(a):08x}")
elif cmd == "dsp":
    lab = sys.argv[3]
    MB = 0x06144000
    regs = [0x0000, 0x0001, 0x00fc, 0x80ff, 0x00ee, 0x0002, 0x8034, 0x0012, 0x0013, 0x0014, 0x0015, 0x0016, 0x0017,
            0x0118, 0x8062, 0x8063, 0x0096, 0x0090, 0x8052, 0x8053, 0x0036, 0x0034, 0x0052, 0x0053, 0x0050, 0x0051,
            0x0020, 0x0021, 0x0022, 0x0023, 0x001e, 0x001f, 0x8017, 0x80b2, 0x80b3, 0x00b2, 0x00b3, 0x0077, 0x007c,
            0x007d, 0x007e, 0x0100, 0x0101, 0x0102, 0x0103, 0x8100, 0x8101, 0x8102, 0x8103, 0x800a]
    log(f"DSP {lab}: mailbox status {r32(MB):08x}")

    def dread(reg):
        # 70 §4.3: +0x10 bit 31 rises with a registered request; the answer is ready when it has fallen again and
        # +0x00 bit 5 is set. A request whose bit 31 is never seen within 50 us is re-issued.
        for attempt in range(4):
            w32(MB + 0x10, reg << 16)
            t0 = time.monotonic(); seen = False
            while time.monotonic() - t0 < (0.005 if seen else 0.00005):
                v = r32(MB + 0x10)
                if v & 0x80000000:
                    seen = True
                elif seen and r32(MB) & 0x20:
                    return v & 0xffff, attempt, (time.monotonic() - t0) * 1e6
        return None, 4, 0
    vals = []
    for reg in regs:
        v, att, us = dread(reg)
        vals.append(f"{reg:04x}={'TIMEOUT' if v is None else f'{v:04x}'}" + (f"(r{att})" if att else ""))
    log(f"DSP {lab}: " + " ".join(vals))
log("=== done")
