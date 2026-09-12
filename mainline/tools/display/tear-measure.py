#!/usr/bin/env python3
"""Measure tearing in an fb-anim capture.

fb-anim draws one red bar on blue and steps it 16 px per frame. A photograph of
it leans for two reasons that are NOT tearing -- keystone, because the projector
is off-axis, and the camera's rolling shutter, because the bar moves while the
sensor is read out. Both are smooth and monotonic in row.

Tearing is different in kind: the panel shows frame N above the tear line and
frame N-1 below it, so the bar's x position takes a STEP. That is what this
measures.

THE STEP IS NOT THE MEASUREMENT. A 30 fps rolling-shutter camera against a
~60 Hz panel sees about one panel-frame boundary cross the sensor per readout,
so a 16 px step appears in every camera frame whether or not the panel tears.
Measuring steps measures the camera. That was tried first and it could not
separate the two cases.

What the camera CAN see is a row with no bar on it at all. The single-buffered
fill blues the whole surface first and draws the bar afterwards, so a raster
passing through mid-fill finds no bar anywhere -- for the 1.95 ms of a 16.75 ms
frame that the fill takes, i.e. about 12% of rows. Rolling shutter can only
shift the bar; it can never delete it. So "rows with no bar" is specific to
single-buffered corruption, and its expected size is predicted by the timing
the console already reports.

Usage:
    tear-measure.py VIDEO.MOV [--frames N] [--start SEC] [--end SEC]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def extract(path, t, dest):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-q:v", "2", str(dest), "-y"],
        check=True)


BAR_PANEL_PX = 64          # h713_disp fill_bar draws this many columns
STEP_PANEL_PX = 16         # and advances this many per frame


def bar_centroid_per_row(img):
    """Return (rows, xs, widths) using only rows with ONE clean red run.

    Requiring a single contiguous run is what makes this trustworthy. It
    rejects the frames where the bar is wrapping (two runs, one at each edge),
    which would otherwise average to a centre in the middle of the screen where
    there is no bar at all -- and those were the 400 px "steps" an earlier and
    looser version of this script reported.
    """
    a = np.asarray(img).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

    lum = r.astype(np.int32) + g + b
    lit = lum > (lum.max() * 0.35)

    # Redness separates bar from field far more reliably than absolute level,
    # which varies with lamp falloff across the frame.
    redness = (r - b).astype(np.float32)
    strong = (redness > 40) & lit

    rows, xs, widths = [], [], []
    for y in range(a.shape[0]):
        cols = np.flatnonzero(strong[y])
        if cols.size < 20:
            continue
        # Split into contiguous runs; accept the row only if there is exactly
        # one, so wraps and speckle are both excluded rather than averaged.
        breaks = np.flatnonzero(np.diff(cols) > 3)
        if breaks.size:
            continue
        w = redness[y, cols]
        rows.append(y)
        xs.append(float((cols * w).sum() / w.sum()))
        widths.append(float(cols.size))
    return np.array(rows), np.array(xs), np.array(widths)


def robust_line(rows, xs, iters=3):
    """Least squares with outlier rejection, so a tear cannot drag the fit."""
    keep = np.ones(rows.size, bool)
    m = c = 0.0
    for _ in range(iters):
        if keep.sum() < 10:
            break
        m, c = np.polyfit(rows[keep], xs[keep], 1)
        resid = xs - (m * rows + c)
        s = np.std(resid[keep])
        if s == 0:
            break
        keep = np.abs(resid) < 2.5 * s
    return m, c


def analyse_frame(path, smooth=9, trim=0.03):
    """Per frame: what fraction of interior rows have lost the bar entirely."""
    img = Image.open(path).convert("RGB")
    a = np.asarray(img).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

    lum = r.astype(np.int32) + g + b
    lit = lum > (lum.max() * 0.35)
    width = lit.sum(1)
    if width.max() < 200:
        return None
    inside = np.flatnonzero(width > 0.6 * width.max())
    if inside.size < 300:
        return None

    # Trim the top and bottom of the projection: the lit mask is unreliable
    # where the image fades into the wall, and a false "no bar" there would be
    # counted as corruption.
    cut = int(inside.size * trim)
    inside = inside[cut:inside.size - cut]

    strong = ((r - b) > 40) & lit
    missing = split = 0
    widths = []
    for y in inside:
        cols = np.flatnonzero(strong[y])
        if cols.size < 20:
            missing += 1
            continue
        if np.count_nonzero(np.diff(cols) > 3):
            split += 1
            continue
        widths.append(float(cols.size))

    if not widths:
        return None
    return {
        "rows": int(inside.size),
        "missing_pct": 100.0 * missing / inside.size,
        "split_pct": 100.0 * split / inside.size,
        "scale": float(np.median(widths)) / BAR_PANEL_PX,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--start", type=float, default=1.0)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    path = Path(args.video)
    dur = probe_duration(path)
    end = args.end if args.end is not None else max(args.start + 1.0, dur - 1.0)
    times = np.linspace(args.start, end, args.frames)

    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "f.jpg"
        for t in times:
            extract(path, t, tmp)
            r = analyse_frame(tmp)
            if r:
                results.append(r)

    if not results:
        sys.exit(f"{path.name}: no frame yielded a usable bar")

    def col(k):
        return np.array([r[k] for r in results])

    miss = col("missing_pct")
    print(f"=== {path.name} ===")
    print(f"  frames analysed        : {len(results)} of {args.frames}")
    print(f"  interior rows/frame    : {int(np.median(col('rows')))}")
    print(f"  scale                  : {np.median(col('scale')):.2f} image px per panel px")
    print()
    print(f"  ROWS WITH NO BAR       : median {np.median(miss):5.2f} %"
          f"   mean {miss.mean():5.2f} %   worst {miss.max():5.2f} %")
    print(f"  rows with a split bar  : median {np.median(col('split_pct')):5.2f} %")
    print()
    print("  Single-buffered prediction: the fill is 1.95 ms of a 16.75 ms frame,")
    print("  and the bar is absent for nearly all of it -> ~11.7 % of rows.")


if __name__ == "__main__":
    main()
