#!/usr/bin/env python3
"""Spec 70 §9 B3/B4 on the bench boot (firmware never started, msp driver blacklisted). Spec side, 2026-11-04.
isl.py LOG up        B3: island up per 70 §4.2 (normal-boot CCU values), self-test reads
isl.py LOG route     B4: the direct route of 70 §4.5 rows 1-20 with 0x0020 = 0x1617, no patch; meter on 0x16/0x17
isl.py LOG meter N   N reads of the level meter (0x00b2/0x00b3) 100 ms apart, meter source left as it is
Every first access of a block is logged and fsynced before it happens; every MMIO write is read back."""
import mmap, os, struct, sys, time

LOG = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
maps = {}
MB = 0x06144000


def log(s):
    os.write(LOG, f"{time.monotonic():10.3f} {s}\n".encode()); os.fsync(LOG)


def page(a):
    b = a & ~0xfff
    if b not in maps:
        log(f"FIRST-ACCESS page {b:#010x}")
        maps[b] = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=b)
    return maps[b], a & 0xfff


def r32(a):
    m, o = page(a); return struct.unpack_from("<I", m, o)[0]


def w32(a, v):
    m, o = page(a)
    log(f"W32 {a:#010x} = {v:08x} (was {struct.unpack_from('<I', m, o)[0]:08x})")
    struct.pack_into("<I", m, o, v)
    log(f"   read back {struct.unpack_from('<I', m, o)[0]:08x}")


def dread(reg):
    # a pending write must have been taken (+0x00 bit 4 clear) before a read is requested (the project driver does
    # the same); a read requested while the write is pending stalls the mailbox (bench 2026-11-04, a1/a2)
    t0 = time.monotonic()
    while r32(MB) & 0x10:
        if time.monotonic() - t0 > 0.05:
            log(f"DSP read {reg:04x}: write-busy for 50 ms"); return None
    for attempt in range(4):
        w32q(MB + 0x10, reg << 16)
        t0 = time.monotonic(); seen = False
        while time.monotonic() - t0 < (0.05 if seen else 0.00005):
            v = r32(MB + 0x10)
            if v & 0x80000000:
                seen = True
            elif seen and r32(MB) & 0x20:
                return v & 0xffff
    return None


def w32q(a, v):
    m, o = page(a); struct.pack_into("<I", m, o, v)


def dwrite(reg, val):
    t0 = time.monotonic()
    while r32(MB) & 0x10:
        if time.monotonic() - t0 > 0.05:
            log(f"DSP write {reg:04x}: write-busy for 50 ms"); return False
    w32q(MB + 0x0c, (reg << 16) | (val & 0xffff))
    return True


def dset(reg, mask, val):
    old = dread(reg)
    if old is None:
        log(f"DSP {reg:04x}: read timeout, write skipped"); return
    new = (old & ~mask) | (val & mask)
    dwrite(reg, new)
    back = dread(reg)
    log(f"DSP {reg:04x}: {old:04x} -> {new:04x}, reads {'TIMEOUT' if back is None else f'{back:04x}'}")


cmd = sys.argv[2]
log(f"=== isl.py {' '.join(sys.argv[2:])} boot {open('/proc/sys/kernel/random/boot_id').read().strip()}")
if cmd == "up":
    normal = {0x02001d10: 0x81000005, 0x02001d18: 0x81000004, 0x02001d20: 0x80000000, 0x02001d24: 0x80000007,
              0x02001d28: 0x80000002, 0x02001d2c: 0x80000005, 0x02001d30: 0x80000004, 0x02001d34: 0x80000004,
              0x02001d38: 0x8000000b, 0x02001d40: 0x8000020a, 0x02001d58: 0x80000002, 0x02001d5c: 0x8000020b,
              0x02001d60: 0x8000020b}
    log("CCU before: " + " ".join(f"{a & 0xfff:03x}={r32(a):08x}" for a in range(0x02001d10, 0x02001d90, 4)))
    for a, v in normal.items():                                   # step 1
        if r32(a) != v:
            w32(a, v)
    v = r32(0x02001d64)                                           # step 2
    w32(0x02001d64, v & ~0x10001); time.sleep(0.01); w32(0x02001d64, 0x00010001); time.sleep(0.01)
    for a, v in ((0x02001d48, 0x80000002), (0x02001d4c, 0x80000002), (0x02001d50, 0x81000002)):   # step 3
        w32(a, v)
    log("BEFORE-READ TVFE_RT 0x06700000")
    log(f"TVFE_RT +0 = {r32(0x06700000):08x}")
    w32(0x06700000, 0x003003ff)                                   # step 4
    log("BEFORE-READ AU_TOP 0x0614a000")
    t = r32(0x0614a000); log(f"AU_TOP before: " + " ".join(f"{r32(0x0614a000 + o):08x}" for o in range(0, 0x10, 4)))
    w32(0x0614a000, t | 0x700)                                    # step 5
    c = r32(0x0614a00c)
    w32(0x0614a00c, (c & 0xff000000) | 0x001a5e00); w32(0x0614a00c, r32(0x0614a00c) | 0x01000000)   # step 6
    a44 = r32(0x06142044)                                         # step 7
    w32(0x06142044, (a44 & ~0xff) | 0x5a); w32(0x06142044, a44)
    time.sleep(0.3)                                               # step 8
    log(f"AU_MBOX status {r32(MB):08x}")
    for reg in (0x0000, 0x00ee, 0x0001, 0x00fc, 0x80ff, 0x0002, 0x8034, 0x8017):
        v = dread(reg); log(f"DSP read {reg:04x} = {'TIMEOUT' if v is None else f'{v:04x}'}")
    log("AU_IF (AU_TOP +0 = %08x): " % r32(0x0614a000) + " ".join(f"{r32(0x06146000 + o):08x}" for o in range(0, 0x90, 4)))
elif cmd == "route":
    rows = ([(0x00ee, 0x7f80, 0x0180)] if "speed" in sys.argv[3:] else []) + [(0x0002, 0x8000, 0x8000), (0x8034, 0x90, 0x10), (0x0012, 0xffff, 0x8180), (0x0013, 0xff00, 0x2000),
            (0x0118, 0xffff, 0x1617), (0x8062, 0xff, 0x92), (0x8063, 0xff, 0x93), (0x0096, 0xffff, 0x7273),
            (0x0090, 0xffff, 0x9a9b), (0x8052, 0xff, 0x98), (0x8053, 0xff, 0x99), (0x0036, 0xffff, 0x6263),
            (0x0052, 0xffc0, 0), (0x0053, 0xffc0, 0), (0x0050, 0xffff, 0), (0x0051, 0xffff, 0),
            (0x0020, 0xffff, 0x6263), (0x001e, 0xffff, 0xa440), (0x001f, 0xf93f, 0x3000), (0x8017, 0x1, 0),
            (0x0020, 0xffff, 0x1617), (0x80b2, 0xff, 0x16), (0x80b3, 0xff, 0x17)]
    for reg, mask, val in rows:
        dset(reg, mask, val)
        if dread(0x0000) is None:
            log(f"mailbox stuck after {reg:04x}: status {r32(MB):08x} +0x10 {r32(MB + 0x10):08x}"); break
elif cmd == "meter":
    n = int(sys.argv[3]); out = []
    for i in range(n):
        a = dread(0x00b2); b = dread(0x00b3); out.append(f"{a if a is None else f'{a:04x}'}/{b if b is None else f'{b:04x}'}")
        time.sleep(0.1)
    log(f"METER 0x00b2/0x00b3 (source {dread(0x80b2)}/{dread(0x80b3)}): " + " ".join(out))
elif cmd == "fix":
    dset(0x0053, 0xffc0, 0); dset(0x0051, 0xffff, 0)
elif cmd == "state":
    vals = []
    for r in (0x0002, 0x8034, 0x0012, 0x0013, 0x0118, 0x8062, 0x8063, 0x0096, 0x0090, 0x8052, 0x8053, 0x0036, 0x0052,
              0x0053, 0x0050, 0x0051, 0x0020, 0x001e, 0x001f, 0x8017, 0x80b2, 0x80b3, 0x00b2, 0x00b3, 0x0000, 0x00ee,
              0x80ff):
        v = dread(r); vals.append(f"{r:04x}=" + ("TIMEOUT" if v is None else f"{v:04x}"))
    log("ROUTE STATE " + " ".join(vals))
log("=== done")
