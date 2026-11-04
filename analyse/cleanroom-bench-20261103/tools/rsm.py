#!/usr/bin/env python3
"""Resume re-init after a standby, firmware never started (spec side, 2026-11-04). rsm.py LOG BEFORE_LOG STEPS
STEPS (comma list, in this order): ccu = write back every CCU word 0x02001d00..0x02001dff and the PLLs 0x02001040,
0x02001048, 0x02001050, 0x02001068 that differ from the BEFORE_LOG snapshot (wdump format); tvtop = the TV-top
sequence (+4 0x01111117, +8 0x404, +0 0x00111111, 12 ms, all 0, 12 ms, again); tvtop504 = +8 0x504; ppu = power the
TVFE/TVCAP domains on if they are not; cap = read CAP 0x06940000 and RX_CTL 0x068008fc (each logged before).
Every write and every first read is logged and fsynced first (blog.py)."""
import re, sys, time
sys.path.insert(0, "/data/bench")
from blog import _page, log, openlog, rd, wr  # noqa: E402
openlog(sys.argv[1])
before = {}
for l in open(sys.argv[2]):
    m = re.search(r"DUMP \S+ w (0x[0-9a-f]+): (.*)", l)
    if m:
        a = int(m.group(1), 16)
        for i, v in enumerate(m.group(2).split()):
            before[a + 4 * i] = int(v, 16)
steps = sys.argv[3].split(",")
def W(a, v):
    log(f"W32 {a:#010x} = {v:08x} (was {rd(a):08x})"); wr(a, v); log(f"   read back {rd(a):08x}")
for st in steps:
    log(f"RSM step {st}")
    if st == "ccu":
        for a in [0x02001040, 0x02001048, 0x02001050, 0x02001068] + list(range(0x02001d00, 0x02001e00, 4)):
            if a in before and rd(a) != before[a]:
                W(a, before[a]); time.sleep(0.012)
    elif st == "tvtop":
        for vals in ((0x01111117, 0x404, 0x00111111), (0, 0, 0), (0x01111117, 0x404, 0x00111111)):
            W(0x06e00004, vals[0]); W(0x06e00008, vals[1]); W(0x06e00000, vals[2]); time.sleep(0.012)
        for k in range(3):
            log(f"TVTOP after the sequence +{k * 50} ms: " + " ".join(f"{rd(0x06e00000 + o):08x}" for o in range(0, 0x40, 4))
                + f" | PPU tvfe {rd(0x070010a4):08x} tvcap {rd(0x07001124):08x} | d88 {rd(0x02001d88):08x}")
            time.sleep(0.05)
    elif st == "tvtop504":
        W(0x06e00008, 0x504)
    elif st == "ppu":
        for d, n in ((1, "tvfe"), (2, "tvcap")):
            b = 0x07001014 + 0x80 * d
            s = rd(b + 0x10)
            log(f"PPU {n} status {s:08x} ctrl {rd(b + 0x0c):08x}")
            if (s & 0x30000) != 0x10000:
                W(b + 0x0, 8); W(b + 0x4, 0x00080808); W(b + 0x8, 0x00080808); W(b + 0x0c, 1)
                t0 = time.monotonic()
                while time.monotonic() - t0 < 0.1 and (rd(b + 0x10) & 0x30000) != 0x10000:
                    time.sleep(0.001)
                log(f"PPU {n} status now {rd(b + 0x10):08x}")
    elif st == "tvoff":
        W(0x06e00000, 0); W(0x06e00004, 0); W(0x06e00008, 0); time.sleep(0.012)
        W(0x02001d88, rd(0x02001d88) & ~0x10000); time.sleep(0.012)
        for d, n in ((2, "tvcap"), (1, "tvfe")):
            b = 0x07001014 + 0x80 * d
            W(b + 0x0c, 2)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.1 and (rd(b + 0x10) & 0x30000) == 0x10000:
                time.sleep(0.001)
            log(f"PPU {n} status after off {rd(b + 0x10):08x}")
    elif st == "d88on":
        W(0x02001d88, 0x00010001); time.sleep(0.012)
    elif st == "irqoff":
        log(f"SCANOUT 0x0c0 {rd(0x056000c0):08x} 0x0c4 {rd(0x056000c4):08x} 0x168 {rd(0x05600168):08x} 0x16c {rd(0x0560016c):08x}")
        W(0x056000c4, rd(0x056000c4) & ~1); W(0x0560016c, rd(0x0560016c) & ~0x10)
        W(0x056000c0, 1); W(0x05600168, 2)
        log(f"GIC pending word 4 (ids 128-159) {rd(0x03021210):08x}")
    elif st == "vpbdisable":
        import subprocess
        out = subprocess.run("/root/vp-bench apply --mode disable --log " + sys.argv[1] + ".vpb | tail -1", shell=True, capture_output=True, text=True).stdout.strip()
        log(f"vp-bench disable: {out}")
        log(f"SCANOUT 0x010 {rd(0x05600010):08x} 0x014 {rd(0x05600014):08x} 0x058 {rd(0x05600058):08x} 0x05c {rd(0x0560005c):08x}; PNL 0x174 {rd(0x051c0174):08x}")
        time.sleep(0.1)
        log(f"100 ms later: SCANOUT 0x058 {rd(0x05600058):08x} 0x05c {rd(0x0560005c):08x}; PNL 0x174 {rd(0x051c0174):08x}; 0x310 {rd(0x05600310):08x}")
    elif st == "nrcoff":
        for a in (0x05000178, 0x050001b8, 0x05000278, 0x050002b8):
            W(a, rd(a) & ~0x80000000)
        time.sleep(0.05)
    elif st in ("vpbapply", "vpbapplyskip"):
        import subprocess
        skip = " --skip 0x06940400" if st == "vpbapplyskip" else ""
        sh = ("/root/vp-bench frame P1 0x4c000000 1920 1080 nv12 >/dev/null 2>&1; "
              "/root/vp-bench apply --db /boot/mips/database.TSE --luma 0x4c000000" + skip + " --log " + sys.argv[1] + ".vpb | tail -1; "
              "/root/vp-bench verify scan --log " + sys.argv[1] + ".vpb | tail -1; "
              "/root/vp-bench verify hist --expect p1 --log " + sys.argv[1] + ".vpb | grep -E 'PASS P1|FAIL' | head -1")
        out = subprocess.run(sh, shell=True, capture_output=True, text=True).stdout
        for l in out.splitlines():
            log(f"after the wake: {l}")
    elif st == "rgboff":
        W(0x05600140, 0x83001900); W(0x05600144, 1)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.2 and rd(0x05600144) & 1:
            time.sleep(0.001)
        log(f"RGB latch {rd(0x05600144):08x} after {1000 * (time.monotonic() - t0):.1f} ms")
    elif st == "scan":
        import subprocess
        out = subprocess.run("/root/vp-bench verify scan | grep -E 'FAIL|verify scan:'", shell=True, capture_output=True, text=True).stdout
        for l in out.splitlines():
            log(f"after the wake: {l[:150]}")
    elif st.startswith("wait"):
        ms = int(st[4:] or 200); time.sleep(ms / 1000); log(f"waited {ms} ms")
    elif st == "ubootclk":
        for a, v in ((0x02001d88, 0x00010001), (0x02001040, 0xb8003501), (0x02001d6c, 0x80000305),
                     (0x02001068, 0xb8002f01), (0x02001d74, 0x81000001), (0x02001d84, 0x80000000),
                     (0x02001d80, 0xc0000000)):
            W(a, v); time.sleep(0.012)
    elif st == "clkwait":
        # the same writes, but after each PLL write the lock bit (28) is polled for 50 ms and its course logged;
        # 100 ms settle at the end (Q-SLEEP-1 hypothesis a)
        log("PLL words before: " + " ".join(f"{a:#x}={rd(a):08x}" for a in range(0x02001000, 0x02001080, 8)))
        for a, v in ((0x02001d88, 0x00010001), (0x02001040, 0xb8003501), (0x02001d6c, 0x80000305),
                     (0x02001068, 0xb8002f01), (0x02001d74, 0x81000001), (0x02001d84, 0x80000000),
                     (0x02001d80, 0xc0000000)):
            W(a, v)
            if a in (0x02001040, 0x02001068):
                t0 = time.monotonic(); n = 0; low = 0; first_low = last_low = None
                while time.monotonic() - t0 < 0.05:
                    x = rd(a); n += 1
                    if not x & 0x10000000:
                        low += 1; dt = time.monotonic() - t0
                        first_low = dt if first_low is None else first_low; last_low = dt
                f = lambda d: "-" if d is None else f"{d * 1e6:.0f} us"
                log(f"PLL {a:#x} lock bit 28 low in {low} of {n} reads over 50 ms (first {f(first_low)}, last {f(last_low)}); now {rd(a):08x}")
            else:
                time.sleep(0.012)
        time.sleep(0.1); log("settled 100 ms")
    elif st == "rstpulse":
        # RST_BUS_DEMOD (0xd64 bit 16) and RST_BUS_TVCAP (0xd88 bit 16) asserted together for 2 ms, then released
        # (Q-SLEEP-1 hypothesis b; bench only)
        a1, a2 = rd(0x02001d64), rd(0x02001d88)
        W(0x02001d64, a1 & ~0x10000); W(0x02001d88, a2 & ~0x10000); time.sleep(0.002)
        W(0x02001d64, a1 | 0x10000); W(0x02001d88, a2 | 0x10000); time.sleep(0.02)
        log(f"TVTOP after the pulse: {rd(0x06e00000):08x} {rd(0x06e00004):08x} {rd(0x06e00008):08x}")
    elif st == "rx":
        log("BEFORE-READ RX_CTL 0x068008fc (8-bit)")
        m, o = _page(0x068008fc)
        log(f"RX_CTL 0x068008fc = {m[o]:02x}")
    elif st == "tvcaprst":
        v = rd(0x02001d88)
        W(0x02001d88, v & ~0x10000); time.sleep(0.002); W(0x02001d88, v | 0x10001); time.sleep(0.012)
    elif st == "ppucycle":
        for d, n in ((1, "tvfe"), (2, "tvcap")):
            b = 0x07001014 + 0x80 * d
            log(f"PPU {n} status {rd(b + 0x10):08x}; off")
            W(b + 0x0c, 2)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.1 and (rd(b + 0x10) & 0x30000) == 0x10000:
                time.sleep(0.001)
            log(f"PPU {n} status after off {rd(b + 0x10):08x}; on")
            W(b + 0x0c, 1)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.1 and (rd(b + 0x10) & 0x30000) != 0x10000:
                time.sleep(0.001)
            log(f"PPU {n} status after on {rd(b + 0x10):08x}")
    elif st == "hpd":
        import os, subprocess
        os.system("rmmod spx4 2>/dev/null; insmod /data/bench/spx4-73.ko port=1 hpd=3")
        out = subprocess.run("dmesg | grep 'spx4: hpd' | tail -1", shell=True, capture_output=True, text=True).stdout.strip()
        log(f"provider: {out}")
        for i in range(10):
            time.sleep(0.3)
            m, o = _page(0x068008fc); a = m[o]; m, o = _page(0x068009ab); b = m[o]
            log(f"TMDS check +{0.3 * (i + 1):.1f} s: 0x068008fc = {a:02x} (bit 7 = TMDS), 0x068009ab = {b:02x}")
    elif st == "rxtime":
        import subprocess
        out = subprocess.run("python3 /data/bench/rxtime.py " + sys.argv[1] + ".rxtime | grep RXTIME", shell=True, capture_output=True, text=True).stdout
        for l in out.splitlines():
            log(l[11:])
    elif st == "cap":
        log("BEFORE-READ CAP 0x06940000")
        log(f"CAP 0x06940000 = {rd(0x06940000):08x}, 0x104 = {rd(0x06940104):08x}")
        log("BEFORE-READ RX_CTL 0x068008fc (8-bit)")
        m, o = _page(0x068008fc)
        log(f"RX_CTL 0x068008fc = {m[o]:02x}")
log("RSM done")
