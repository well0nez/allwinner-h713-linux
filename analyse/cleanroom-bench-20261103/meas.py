#!/usr/bin/env python3
"""Where the RGB plane is missing over the video plane: column bands and row bands of distinct greys.
Import: measure() -> dict; or run: meas.py LOG [move H V [n]]... (frame-synchronous RASTER totals for n frames)."""
import sys
import time

sys.path.insert(0, "/data/bench")
from blog import log, map_ram, openlog, rd, wr  # noqa: E402

SC = 0x05600000
PNL = 0x051C0000
R = 0x0525C000
A = 0x4B200000  # inside the reserved, never-started co-processor region
# grey -> bin calibration (2026-11-03, this path): the middle grey of each bin
G = {0: 0, 1: 10, 2: 18, 3: 26, 4: 34, 7: 54, 8: 62, 9: 70, 10: 78, 11: 86, 12: 94, 13: 102, 14: 110, 15: 118, 16: 126,
     17: 134, 18: 142, 19: 150, 20: 158, 21: 166, 22: 174, 23: 182, 24: 190, 25: 198, 26: 206, 27: 214, 28: 222,
     29: 232, 30: 242, 31: 255}
BINS = [b for b in sorted(G) if b not in (0,)][:24]  # 24 bands; bin 0 left out (too close to the video black)
_m, _off = map_ram(A, 7680 * 1080)


def _fill_cols():
    line = b"".join(bytes([G[b], G[b], G[b], 0xFF]) * 80 for b in BINS)
    _m[_off:_off + 7680 * 1080] = line * 1080


def _fill_rows():
    for k, b in enumerate(BINS):
        _m[_off + k * 45 * 7680:_off + (k + 1) * 45 * 7680] = bytes([G[b], G[b], G[b], 0xFF]) * (1920 * 45)


def hist():
    time.sleep(0.05)
    return [rd(PNL + 0x380 + 4 * i) for i in range(32)]


def measure():
    _fill_cols()
    hc = hist()
    _fill_rows()
    hr = hist()
    rows_vis = max(hc[b] for b in BINS) / 80
    cols_vis = max(hr[b] for b in BINS) / 45
    col = [hc[b] / rows_vis if rows_vis else 0 for b in BINS]  # visible columns per 80-px band
    row = [hr[b] / cols_vis if cols_vis else 0 for b in BINS]  # visible rows per 45-row band
    video = (hc[5] + hc[6])
    return {"video": video, "rows_vis": rows_vis, "cols_vis": cols_vis, "col": col, "row": row}


def fmt(r):
    lc = " ".join(f"{k}:{c:.1f}" for k, c in enumerate(r["col"]) if abs(c - 80) > 0.05)
    lr = " ".join(f"{k}:{c:.1f}" for k, c in enumerate(r["row"]) if abs(c - 45) > 0.05)
    return (f"video px {r['video']}, RGB rows visible {r['rows_vis']:.2f}, cols visible {r['cols_vis']:.2f}; "
            f"short col bands (80 px) [{lc}]; short row bands (45 rows) [{lr}]")


def wait_done():
    wr(SC + 0x168, 2)
    t0 = time.perf_counter()
    while not rd(SC + 0x168) & 2:
        if time.perf_counter() - t0 > 0.1:
            raise SystemExit("no RGB done within 100 ms")


def frames(h, v, n=1):
    orig = rd(R)
    for _ in range(n):
        wait_done()
        wr(R, ((v - 1) << 16) | (h - 1))
        wait_done()
        wr(R, orig)


if __name__ == "__main__":
    openlog(sys.argv[1])
    a = sys.argv[2:]
    log("MEAS start: " + fmt(measure()))
    i = 0
    while i < len(a):
        if a[i] == "move":
            h, v, n = int(a[i + 1]), int(a[i + 2]), int(a[i + 3])
            frames(h, v, n)
            log(f"MEAS after {n} x {h}x{v}: " + fmt(measure()))
            i += 4
        else:
            raise SystemExit(f"unknown {a[i]}")
