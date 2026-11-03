#!/usr/bin/env python3
"""Picture-processing probes on the bench (no firmware). Needs the aligned RGB-over-video state (r10.py setup +
align3.py): the histogram then counts the RGB plane (alpha 0xff) or the video (PNL_SEL video alone).
gam.py LOG CMD [args] ...   commands:
  fill PAT        RGB buffer: q (left 480 columns white, rest black) | ramp (grey 0..255 left to right) |
                  grey N | rgb R G B | rramp/gramp/bramp (one channel 0..255 left to right)
  vfill PAT       NV12 video frame: yramp (Y 0..255 left to right, C 128) | y N | q
  sel rgb|video   PNL_SEL 0x29000000 (RGB over video, alpha 0xff) | 0x39000000 (video alone)
  hist LABEL      log the histogram (and probe words)
  ports KIND      write the three gamma ports: id | inv | zero | thr | half | pidN (owner's curve N) | redzero
  e8 VALUE        write 0x051c00e8; e8set BIT / e8clr BIT / e8tog BIT: read-modify-write one bit
  wr ADDR VALUE   any word
  rd ADDR
  sleep S"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

SC = 0x05600000
PNL = 0x051C0000
E8 = 0x051C00E8
PORTS = (0x05208000, 0x05208800, 0x05209000)
A = 0x4B200000  # RGB buffer (meas.py's)
V = 0x6CA00000  # the 12 state's video frame (luma; chroma after 1920*1080)
openlog(sys.argv[1])
_m, _o = map_ram(A, 7680 * 1080)
_vm, _vo = map_ram(V, 1920 * 1080 * 3 // 2)
PROBES = (0x051C0144, 0x051C0304, 0x05140600, 0x05140604)


def put_rgb(line):
    _m[_o:_o + 7680 * 1080] = bytes(line) * 1080


def fill(pat, *a):
    if pat == "q":
        put_rgb(b"\xff\xff\xff\xff" * 480 + b"\x00\x00\x00\xff" * 1440)
    elif pat == "ramp":
        put_rgb(b"".join(bytes([g, g, g, 0xFF]) for g in (c * 256 // 1920 for c in range(1920))))
    elif pat == "grey":
        g = int(a[0], 0)
        put_rgb(bytes([g, g, g, 0xFF]) * 1920)
    elif pat == "rgb":
        r, g, b = (int(x, 0) for x in a[:3])
        put_rgb(bytes([b, g, r, 0xFF]) * 1920)
    elif pat in ("rramp", "gramp", "bramp"):
        k = {"rramp": 2, "gramp": 1, "bramp": 0}[pat]
        px = []
        for c in range(1920):
            p = [0, 0, 0, 0xFF]
            p[k] = c * 256 // 1920
            px += p
        put_rgb(bytes(px))
    else:
        raise SystemExit(f"fill {pat}")


def vfill(pat, *a):
    if pat == "yramp":
        line = bytes(c * 256 // 1920 for c in range(1920))
    elif pat == "y":
        line = bytes([int(a[0], 0)]) * 1920
    elif pat == "q":
        line = b"\xeb" * 480 + b"\x10" * 1440
    else:
        raise SystemExit(f"vfill {pat}")
    _vm[_vo:_vo + 1920 * 1080] = line * 1080
    _vm[_vo + 1920 * 1080:_vo + 1920 * 1080 * 3 // 2] = b"\x80" * (1920 * 540)


def hist(label):
    time.sleep(0.1)
    h = [rd(PNL + 0x380 + 4 * i) for i in range(32)]
    mean = sum(i * v for i, v in enumerate(h)) / max(1, sum(h))
    nz = " ".join(f"{i}:{v}" for i, v in enumerate(h) if v)
    pr = " ".join(f"{a & 0xfffff:05x}={rd(a):08x}" for a in PROBES)
    log(f"HIST {label}: mean bin {mean:.2f}; {nz}; e8 {rd(E8):08x}; {pr}")


def samples(kind):
    ident = [min(4095, i * 4 + i // 256) for i in range(1024)]
    if kind == "id":
        return [ident] * 3
    if kind == "inv":
        return [[4095 - v for v in ident]] * 3
    if kind == "zero":
        return [[0] * 1024] * 3
    if kind == "thr":
        return [[0 if i < 512 else 4095 for i in range(1024)]] * 3
    if kind == "half":
        return [[v // 2 for v in ident]] * 3
    if kind == "redzero":
        return [[0] * 1024, ident, ident]
    if kind.startswith("pid"):
        return json.load(open("/data/bench/pidcurves.json"))[int(kind[3:])]
    raise SystemExit(f"ports {kind}")


def ports(kind):
    ch = samples(kind)
    for base, s in zip(PORTS, ch):
        for i in range(512):
            wr(base + 4 * i, (s[2 * i] & 0xFFF) | ((s[2 * i + 1] & 0xFFF) << 12))
    log(f"PORTS {kind} written (3 x 512 words); e8 {rd(E8):08x}; port reads {[hex(rd(p)) for p in PORTS]}")


def rmw(bit, how):
    v = rd(E8)
    n = v | (1 << bit) if how == "set" else v & ~(1 << bit) if how == "clr" else v ^ (1 << bit)
    wr(E8, n)
    log(f"E8 {how} bit {bit}: {v:08x} -> wrote {n:08x}, reads {rd(E8):08x}")


args = sys.argv[2:]
i = 0
while i < len(args):
    c = args[i]
    if c == "fill":
        n = {"grey": 1, "rgb": 3}.get(args[i + 1], 0)
        fill(*args[i + 1:i + 2 + n]); i += 2 + n
    elif c == "vfill":
        n = 1 if args[i + 1] == "y" else 0
        vfill(*args[i + 1:i + 2 + n]); i += 2 + n
    elif c == "sel":
        wr(PNL + 0x6C, 0x29000000 if args[i + 1] == "rgb" else 0x39000000); i += 2
    elif c == "hist":
        hist(args[i + 1]); i += 2
    elif c == "ports":
        ports(args[i + 1]); i += 2
    elif c == "e8":
        v = int(args[i + 1], 0); o = rd(E8); wr(E8, v); log(f"E8 {o:08x} -> wrote {v:08x}, reads {rd(E8):08x}"); i += 2
    elif c in ("e8set", "e8clr", "e8tog"):
        rmw(int(args[i + 1]), c[2:]); i += 2
    elif c == "wr":
        a, v = int(args[i + 1], 0), int(args[i + 2], 0); o = rd(a); wr(a, v)
        log(f"WR {a:#010x}: {o:#010x} -> {v:#010x}, reads {rd(a):#010x}"); i += 3
    elif c == "rd":
        a = int(args[i + 1], 0); log(f"RD {a:#010x} = {rd(a):#010x}"); i += 2
    elif c == "sleep":
        time.sleep(float(args[i + 1])); i += 2
    else:
        raise SystemExit(f"unknown {c}")
