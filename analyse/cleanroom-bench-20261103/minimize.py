#!/usr/bin/env python3
"""Minimal picture set: apply all words of 12 (minset.json: [addr, firmware value, bench value]) on top of the Q1
state, then remove (write back the bench value) group by group and word by word, testing whether the panel
histogram still follows the DRAM frame. Two frames: white at WHITE, black at BLACK; a test flips the channel-0 slots
between them by address-only updates.   minimize.py LOG [phase ...]   phases: all groups words verify"""
import json
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

SC = 0x05600000
W, H = 1920, 1080
WHITE, BLACK, P1 = 0x4C000000, 0x6CA00000, 0x6CD00000
ORDER = ["NRC", "PROC", "SCL", "PNL", "DEI", "BORDER", "PROC_LOCK", "PNL_LOCK"]
openlog(sys.argv[1])
ms = json.load(open("/data/bench/minset.json"))


def fill(addr, y):
    m, off = map_ram(addr, W * H * 3 // 2)
    m[off:off + W * H] = bytes([y]) * (W * H)
    m[off + W * H:off + W * H * 3 // 2] = bytes([128, 128]) * (W * H // 4)


def show(addr):
    for o in (0x070, 0x074, 0x078, 0x07C):
        wr(SC + o, addr)
    for o in (0x084, 0x088, 0x08C, 0x090):
        wr(SC + o, addr + W * H)
    wr(SC + 0x06C, 1)


def hist():
    return [rd(0x051C0380 + 4 * i) for i in range(32)]


def test(label):
    res = {}
    for name, addr in (("white", WHITE), ("black", BLACK)):
        show(addr)
        time.sleep(0.06)
        res[name] = (hist(), rd(SC + 0x06C))
    if STRICT:
        show(P1)
        time.sleep(0.06)
        res["p1"] = (hist(), rd(SC + 0x06C))
    hw, lw = res["white"]
    hb, lb = res["black"]
    sw, sb = sum(hw), sum(hb)
    ok = sw > 2000000 and sb > 2000000 and sum(hw[24:]) > 0.9 * sw and sum(hb[:9]) > 0.9 * sb
    if STRICT:
        hp = res["p1"][0]
        spread = sum(1 for v in hp if v >= 1000)
        ok = ok and spread >= 12
        label += f" [P1 bins>=1000: {spread}]"
    clean = ok and hw[31] == sw
    log(f"TEST {label}: {'FOLLOWS' if ok else 'no'}{' clean' if clean else ''}; white sum {sw} top {hw[31]} "
        f"hi {sum(hw[24:])}; black sum {sb} lo {sum(hb[:9])}; addr-latch {lw}/{lb}; VCH_LATCH {rd(SC + 0x014)}")
    return ok


def put(words, which):  # which: 1 firmware value, 2 bench value
    for w in words:
        wr(w[0], w[which])


def is_addr(g, w):
    return g in ("NRC", "DEI") and 0x04000000 <= w[1] < 0x08000000 and (w[1] & 0xFF) == 0


fill(WHITE, 235)
fill(BLACK, 16)
STRICT = "strict" in sys.argv
if STRICT:
    m, off = map_ram(P1, W * H * 3 // 2)
    bars = [(235, 128, 128), (219, 16, 138), (188, 154, 16), (173, 42, 26), (78, 214, 230), (63, 102, 240),
            (32, 240, 118), (16, 128, 128)]
    bw = W // 8
    top = H * 2 // 3
    m[off:off + top * W] = b"".join(bytes([c[0]]) * bw for c in bars) * top
    m[off + top * W:off + H * W] = bytes(16 + 219 * x // (W - 1) for x in range(W)) * (H - top)
    c0 = off + W * H
    m[c0:c0 + (top // 2) * W] = b"".join(bytes([c[1], c[2]]) * (bw // 2) for c in bars) * (top // 2)
    m[c0 + (top // 2) * W:c0 + (H // 2) * W] = bytes([128, 128]) * (W // 2) * (H // 2 - top // 2)
log("frames: white Y235 at %#x, black Y16 at %#x" % (WHITE, BLACK))
phases = [p for p in sys.argv[2:] if p != "strict"] or ["all", "groups", "words", "verify"]
START, START_G = 0, None
for p in list(phases):
    if p.startswith("from="):
        START_G, a = p[5:].split(":")
        START = int(a, 0)
        phases.remove(p)
needed_groups = []
needed = []
if "all" in phases:
    for g in ORDER:
        put(ms[g], 1)
    if not test("all of 12"):
        log("ABORT: the full set does not give a following picture")
        sys.exit(1)
if "groups" in phases:
    for g in ORDER:
        put(ms[g], 2)
        ok = test(f"without {g}")
        put(ms[g], 1)
        if not test(f"{g} back"):
            log(f"ABORT: not recovered after putting {g} back")
            sys.exit(1)
        if not ok:
            needed_groups.append(g)
    log(f"GROUPS needed: {needed_groups}")
if "words" in phases:
    for g in needed_groups:
        for w in ms[g]:
            if START and w[0] < START and g == START_G:
                continue
            if is_addr(g, w):
                log(f"SKIP {g} {w[0]:#010x} = {w[1]:#010x}: DRAM buffer address, not removed alone")
                continue
            wr(w[0], w[2])
            ok = test(f"without {g} {w[0]:#010x} ({w[1]:#010x} -> {w[2]:#010x})")
            wr(w[0], w[1])
            if not ok:
                needed.append(w)
                if not test("back"):
                    log(f"ABORT: not recovered after {w[0]:#010x}")
                    sys.exit(1)
    log("WORDS needed: " + " ".join(f"{a:#010x}={v:#010x}" for a, v, _ in needed))
    json.dump(needed, open("/data/bench/needed.json", "w"))
if "verify" in phases:
    if not needed:
        needed = [tuple(w) for w in json.load(open("/data/bench/needed.json"))]
    keep = {w[0] for w in needed}
    for g in ORDER:
        put([w for w in ms[g] if w[0] not in keep and not is_addr(g, w)], 2)
    test("only the needed words plus the buffer-address words")
    if any(w[1] & 0x80000000 and w[0] < 0x05100000 for w in needed):
        log("not removing the buffer addresses: a kept NRC/DEI word has bit 31 set (a write channel may be on)")
    else:
        for g in ORDER:
            put([w for w in ms[g] if w[0] not in keep and is_addr(g, w)], 2)
        test("only the needed words")

if "greedy" in phases:
    removed = []
    for g in ("DEI", "PROC_LOCK", "PNL_LOCK"):
        put(ms[g], 2)
        removed += [w for w in ms[g]]
    test("greedy: without DEI and the lock words")
    for g in ("BORDER", "PNL", "SCL", "PROC", "NRC"):
        words = [w for w in ms[g] if not is_addr(g, w)]
        for i in range(0, len(words), 8):
            chunk = words[i:i + 8]
            put(chunk, 2)
            if test(f"greedy: drop {g} {chunk[0][0]:#010x}..{chunk[-1][0]:#010x}"):
                removed += chunk
                continue
            put(chunk, 1)
            for w in chunk:
                wr(w[0], w[2])
                if test(f"greedy: drop {g} {w[0]:#010x}"):
                    removed.append(w)
                else:
                    wr(w[0], w[1])
    gone = {w[0] for w in removed}
    kept = [w for g in ORDER for w in ms[g] if w[0] not in gone]
    test("greedy: kept set incl. buffer addresses")
    if any(w[1] & 0x80000000 and w[0] < 0x05100000 and not is_addr("NRC", w) for w in kept):
        log("buffer addresses kept: a kept NRC/DEI word has bit 31 set")
    else:
        addrs = [w for g in ("NRC", "DEI") for w in ms[g] if is_addr(g, w)]
        put(addrs, 2)
        if test("greedy: without the buffer-address words"):
            kept = [w for w in kept if w not in addrs]
        else:
            put(addrs, 1)
    log("KEPT %d: " % len(kept) + " ".join(f"{a:#010x}={v:#010x}" for a, v, _ in kept))
    json.dump(kept, open("/data/bench/kept-strict.json" if STRICT else "/data/bench/kept.json", "w"))
if "kept" in phases:
    kept = json.load(open("/data/bench/kept.json"))
    put(kept, 1)
    for i in range(3):
        test(f"only the {len(kept)} kept words on the Q1 state, try {i}")
        time.sleep(0.5)
if "p1" in phases:
    m, off = map_ram(WHITE, W * H * 3 // 2)
    bars = [(235, 128, 128), (219, 16, 138), (188, 154, 16), (173, 42, 26), (78, 214, 230), (63, 102, 240),
            (32, 240, 118), (16, 128, 128)]
    bw = W // 8
    top = H * 2 // 3
    m[off:off + top * W] = b"".join(bytes([c[0]]) * bw for c in bars) * top
    m[off + top * W:off + H * W] = bytes(16 + 219 * x // (W - 1) for x in range(W)) * (H - top)
    c0 = off + W * H
    m[c0:c0 + (top // 2) * W] = b"".join(bytes([c[1], c[2]]) * (bw // 2) for c in bars) * (top // 2)
    m[c0 + (top // 2) * W:c0 + (H // 2) * W] = bytes([128, 128]) * (W // 2) * (H // 2 - top // 2)
    show(WHITE)
    time.sleep(0.1)
    h = hist()
    log(f"P1 histogram sum {sum(h)}: " + " ".join(f"{i}:{v}" for i, v in enumerate(h) if v))
    log(f"P1 PROC probe {rd(0x05140600):#010x} {rd(0x05140604):#010x}")
