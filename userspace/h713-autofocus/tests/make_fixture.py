#!/usr/bin/env python3
"""Synthetic replay frames with a known sharpness curve (AP1 follow-up 4).

The real fixture is a directory of raw 640x480 luma frames recorded off the
projector, one per motor position. Nobody has recorded it yet (it needs the
device), so the tests build this one instead: the same chessboard the tool
draws, blurred by an amount that grows with the distance from a chosen peak
position. Sharpness therefore has one maximum, at a step we know, which is
what makes "does the search converge" a question with an answer.

Run standalone to write a fixture somewhere and look at it:

    python3 tests/make_fixture.py /tmp/frames --span 60 --peak 30
"""

import argparse
import os

W, H, CELL = 640, 480, 69


def wave(n, cell, radius):
    """A square wave in -1..1 whose edges are ramps of half-width `radius`."""
    out = []
    for i in range(n):
        distance = i % cell
        edge = min(distance, cell - 1 - distance)
        base = 1.0 if (i // cell) % 2 == 0 else -1.0
        out.append(base * min(1.0, (edge + 0.5) / (radius + 0.5)))
    return out


def frame(radius, w=W, h=H, cell=CELL):
    """One chessboard, blurred by `radius`: sharpest at 0, flatter above."""
    sx, sy = wave(w, cell, radius), wave(h, cell, radius)
    rows, out = {}, bytearray()
    for value in sy:
        key = round(value, 3)
        row = rows.get(key)
        if row is None:
            row = bytes(min(255, max(0, int(128 + 127 * value * across)))
                        for across in sx)
            rows[key] = row
        out += row
    return bytes(out)


def build(directory, span=60, peak=30, blur=0.08, base=1.5, prefix="step"):
    """One file per motor position, named by the step counter.

    `base` is the blur at the peak: a real lens never gives a perfect edge,
    and a fixture whose best frame is pixel-sharp makes the peak a cliff
    instead of a hill. base 1.5 with blur 0.08 over 60 positions gives a
    four-to-one curve, which is the shape a real focus sweep has.
    """
    cache, paths = {}, []
    for step in range(span + 1):
        radius = round(base + abs(step - peak) * blur, 2)
        if radius not in cache:
            cache[radius] = frame(radius)
        path = os.path.join(directory, "%s-%04d.gray" % (prefix, step))
        with open(path, "wb") as fh:
            fh.write(cache[radius])
        paths.append(path)
    return paths


def build_constant(directory, value=0, span=40, prefix="flat"):
    """A negative control: every position the same picture."""
    data = bytes([value]) * (W * H)
    for step in range(span + 1):
        with open(os.path.join(directory,
                               "%s-%04d.gray" % (prefix, step)), "wb") as fh:
            fh.write(data)


def build_two_peaks(directory, span=60, peaks=(15, 45), blur=0.1, base=1.5):
    """A negative control: two maxima, so "it stopped" is not "it was right"."""
    cache = {}
    for step in range(span + 1):
        radius = round(base + min(abs(step - p) for p in peaks) * blur, 2)
        if radius not in cache:
            cache[radius] = frame(radius)
        with open(os.path.join(directory,
                               "twin-%04d.gray" % step), "wb") as fh:
            fh.write(cache[radius])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory")
    parser.add_argument("--span", type=int, default=60)
    parser.add_argument("--peak", type=int, default=30)
    parser.add_argument("--blur", type=float, default=0.08)
    args = parser.parse_args()
    os.makedirs(args.directory, exist_ok=True)
    written = build(args.directory, args.span, args.peak, args.blur)
    print("%d frames in %s, sharpest at step %d"
          % (len(written), args.directory, args.peak))
