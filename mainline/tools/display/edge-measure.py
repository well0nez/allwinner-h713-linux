#!/usr/bin/env python3
"""Measure the display fetch stride from photographs of `panel-test ... fb-edge`.

The pattern is red for the first half of every P source words and blue for the
second, written in linear order. Display row Y starts at source word Y*S for
stride S, so its phase is (Y*S) mod P: the red/blue boundary slides (S mod P)
pixels per row and wraps, painting

	N = 720 * min(S mod P, P - (S mod P)) / P

diagonal stripes down a 720-row frame. Counting stripes therefore measures the
stride, and because a count cannot tell +s from -s, the sign is recovered by
running several pitches and keeping the stride consistent with all of them.

Two quantities live in these photographs and they are not the same number:

  stride  S  how far the source pointer advances per display row  -> the stripes
  width   W  how much of the display line receives content        -> the pale band

Conflating them is what aimed the first sweep at 1180..1200 when the stride is
1237. Both are reported here, separately.

Usage:
	edge-measure.py --pitches 1180,1184,1188,1196,1200 photo1.jpg photo2.jpg ...

Photographs must be in step order, one per pitch. Any step that was not
photographed has to be dropped from --pitches too, or the fit is meaningless.
"""

import argparse
import sys

import numpy as np
from PIL import Image

HEIGHT = 720          # display rows per frame
WIDTH = 1280          # display columns per frame


def load(path, width=2400):
    im = Image.open(path).convert("RGB")
    height = int(im.size[1] * width / im.size[0])
    return np.asarray(im.resize((width, height))).astype(float)


def content_box(chroma):
    """Bound the striped area by where red/blue alternates row to row.

    Luminance cannot do this: the pale band is bright too, and the optical path
    normalises luminance away in the first place. Alternation is what only the
    framebuffer content has.
    """
    hp = np.abs(chroma[2:, :] - chroma[:-2, :])
    cols = np.where(hp.mean(0) > hp.mean(0).max() * 0.30)[0]
    rows = np.where(hp.mean(1) > hp.mean(1).max() * 0.30)[0]
    if not len(cols) or not len(rows):
        raise ValueError("no alternating content found -- solid frame?")
    return cols.min(), cols.max(), rows.min(), rows.max(), hp


def stripe_count(chroma, x0, x1, y0, y1):
    """Stripes down the frame, by FFT and by autocorrelation.

    Two methods because a single one has no way to announce that it locked onto
    a harmonic or onto photographic moire. They agree here to about 1%.
    """
    w = x1 - x0 + 1
    col = chroma[y0:y1, x0 + int(w * 0.35):x0 + int(w * 0.65)].mean(1)
    col = col - col.mean()
    n = len(col)

    spec = np.abs(np.fft.rfft(col * np.hanning(n)))
    k = int(np.argmax(spec[3:]) + 3)
    a, b, c = spec[k - 1], spec[k], spec[k + 1]
    fft_n = k + 0.5 * (a - c) / (a - 2 * b + c)

    ac = np.correlate(col, col, "full")[n - 1:]
    ac = ac / ac[0]
    first_neg = int(np.argmax(ac < 0))
    peak = first_neg + int(np.argmax(ac[first_neg:first_neg + n // 4]))
    acorr_n = n / peak if peak else float("nan")

    return fft_n, acorr_n


def content_pads(path):
    """Where content starts and ends, in display px, for the band probe.

    Keys off colour saturation rather than row-to-row alternation. The band is
    pale and the content is strongly red or blue, which holds whatever the
    pattern is -- including a solid fill, where there is no alternation at all.
    The alternation route silently returned 29..254 px on coarse stripes, so it
    was never usable for this.
    """
    a = load(path)
    lum = a.sum(2)
    sat = np.abs(a[:, :, 0] - a[:, :, 2])

    rows = np.where(lum.mean(1) > lum.mean(1).max() * 0.5)[0]
    top, bottom = rows.min(), rows.max()
    inset_y = int((bottom - top) * 0.25)
    xs_lum = lum[top + inset_y:bottom - inset_y].mean(0)
    xs = sat[top + inset_y:bottom - inset_y].mean(0)

    # The panel edge is half way between wall and panel, not a fraction of the
    # panel's own peak. Thresholding on the peak puts the edge inside the pale
    # band -- which is dimmer than saturated content -- and eats ~20 px off a
    # narrow band while barely touching a wide one. That read 123 as 102 and
    # 400 as 401, which looked like a nonlinearity and was not.
    wall = np.median(np.r_[xs_lum[:40], xs_lum[-40:]])
    panel = np.percentile(xs_lum, 90)
    on = np.where(xs_lum > (wall + panel) / 2)[0]
    left, right = on.min(), on.max()

    ys = sat[:, left + (right - left) // 2:right - (right - left) // 10].mean(1)
    smax = np.percentile(xs[left:right], 90)
    cx = np.where(xs[left:right] > smax * 0.5)[0] + left
    cy = np.where(ys[top:bottom] > np.percentile(ys[top:bottom], 90) * 0.5)[0]
    cy = cy + top

    return (WIDTH * (cx.min() - left) / (right - left),
            WIDTH * (right - cx.max()) / (right - left),
            HEIGHT * (cy.min() - top) / (bottom - top),
            HEIGHT * (bottom - cy.max()) / (bottom - top))


def half_max_edge(profile, start, direction):
    inside = np.median(profile[max(0, start - 30):start + 30])
    j = start
    while 0 < j < len(profile) - 1:
        j += direction
        if profile[j] < inside * 0.5:
            break
    prev, cur = profile[j - direction], profile[j]
    if prev == cur:
        return float(j)
    return (j - direction) + (inside * 0.5 - prev) / (cur - prev) * direction


def content_width(lum, hp, x0, x1, y0, y1):
    """The pale band, as a fraction of the panel -- a separate measurement."""
    profile = lum[y0 + 30:y1 - 30, :].mean(0)
    left = half_max_edge(profile, max(10, x0 - 60), -1)
    right = half_max_edge(profile, x1 - 60, +1)
    seg = hp.mean(0)[max(0, x0 - 40):x0 + 40]
    boundary = max(0, x0 - 40) + np.argmax(np.diff(seg)) + 0.5
    return WIDTH * (right - boundary) / (right - left)


def solve_stride(pitches, counts, lo=2, hi=4000):
    """Every stride whose predicted counts match, ranked. Should be unique."""
    pitches = np.asarray(pitches, dtype=float)
    counts = np.asarray(counts, dtype=float)
    out = []
    for s in range(lo, hi):
        m = s % pitches
        pred = HEIGHT * np.minimum(m, pitches - m) / pitches
        out.append((float(np.sqrt(((pred - counts) ** 2).mean())), s))
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--pitches",
                    help="assumed pitch per photo, in step order")
    ap.add_argument("--band", action="store_true",
                    help="score fb-band instead: where content starts")
    args = ap.parse_args()

    if args.band:
        print(f'{"photo":24}{"left":>8}{"right":>8}{"top":>8}{"bottom":>8}'
              "   display px")
        pads = []
        for path in args.photos:
            p = content_pads(path)
            pads.append(p)
            name = path.rsplit("/", 1)[-1]
            print(f"{name:24}{p[0]:8.1f}{p[1]:8.1f}{p[2]:8.1f}{p[3]:8.1f}")
        left = np.array([p[0] for p in pads])
        print(f"\nleft pad {left.mean():.1f} +- {left.std():.1f} px, "
              f"spread {left.max() - left.min():.1f}")
        print("A step that moves the left pad names the register. A spread of "
              "a few px across every step means none of them carries it.")
        return

    if not args.pitches:
        sys.exit("need --pitches (stripe modes) or --band (fb-band)")
    pitches = [int(p) for p in args.pitches.split(",")]
    if len(pitches) != len(args.photos):
        sys.exit(f"{len(args.photos)} photos but {len(pitches)} pitches -- "
                 "drop the pitches whose steps were not photographed")

    counts, widths = [], []
    print(f'{"photo":22}{"pitch":>7}{"FFT":>8}{"autocorr":>10}{"width":>9}')
    for path, pitch in zip(args.photos, pitches):
        a = load(path)
        chroma = a[:, :, 0] - a[:, :, 2]
        x0, x1, y0, y1, hp = content_box(chroma)
        fft_n, acorr_n = stripe_count(chroma, x0, x1, y0, y1)
        width = content_width(a.sum(2), hp, x0, x1, y0, y1)
        counts.append((fft_n + acorr_n) / 2)
        widths.append(width)
        name = path.rsplit("/", 1)[-1]
        print(f"{name:22}{pitch:7d}{fft_n:8.2f}{acorr_n:10.2f}{width:9.1f}")

    ranked = solve_stride(pitches, counts)
    print("\nstride candidates (rms in stripes):")
    for rms, s in ranked[:5]:
        print(f"   S={s:5d}  rms={rms:6.3f}")

    best = ranked[0][1]
    margin = ranked[1][0] - ranked[0][0]
    print(f"\nstride S = {best} px/row   (next candidate is {margin:.2f} "
          f"stripes worse)")
    print(f"content width W = {np.mean(widths):.0f} +- {np.std(widths):.0f} px "
          f"-- the pale band, a different quantity from the stride")


if __name__ == "__main__":
    main()
