#!/usr/bin/env python3
"""FB-AFSEARCH: the search turns round on a falling metric and comes back.

The fixtures are metric-versus-position curves served to the real Search by
a ReplayMotor (the position) and a table metric (the sum), so a device run's
shape replays in milliseconds. RUN1 is af-run1.log of 26.09.2026 (HY310,
first run after a boot): the mean sum per position of the long downward
sweep, passes 240..133, and the climb of passes 260..255 above it, shifted
by -491 to join at +16, with the run's maximum (11568 - 491) at the upper
edge. The knot at +44 sits below the maximum, as the pass that meets the
edge does on the device, so the replay takes the device's path through
state 3 and its fall-back.
"""

import contextlib
import math
import os
import tempfile
import unittest

from test_h713_autofocus import af, mf

RUN1 = [(-400, 789), (-395, 782), (-387, 777), (-382, 768), (-379, 782),
        (-374, 770), (-371, 778), (-369, 805), (-366, 782), (-363, 778),
        (-361, 800), (-360, 802), (-356, 785), (-354, 782), (-353, 793),
        (-352, 819), (-348, 792), (-345, 795), (-344, 833), (-342, 756),
        (-340, 803), (-338, 831), (-337, 798), (-336, 795), (-332, 828),
        (-330, 768), (-329, 817), (-328, 863), (-326, 837), (-324, 804),
        (-320, 887), (-314, 881), (-312, 954), (-308, 917), (-304, 927),
        (-302, 937), (-296, 975), (-290, 1059), (-284, 1109), (-278, 1135),
        (-272, 1150), (-266, 1184), (-260, 1241), (-254, 1235), (-248, 1276),
        (-242, 1342), (-236, 1405), (-230, 1450), (-224, 1467), (-218, 1536),
        (-212, 1581), (-206, 1642), (-200, 1676), (-194, 1743), (-188, 1786),
        (-182, 1835), (-176, 1930), (-170, 2082), (-164, 2155), (-158, 2237),
        (-152, 2287), (-146, 2422), (-140, 2557), (-134, 2647), (-128, 2776),
        (-122, 2849), (-116, 2939), (-110, 3076), (-104, 3274), (-98, 3429),
        (-92, 3649), (-86, 3909), (-80, 4144), (-74, 4410), (-68, 4611),
        (-62, 4866), (-56, 5203), (-50, 5429), (-44, 5634), (-38, 5831),
        (-32, 6053), (-26, 6252), (-20, 6627), (-14, 7105), (-8, 7582),
        (-2, 8134), (4, 8766), (10, 9049), (16, 9069), (24, 10565),
        (32, 10619), (40, 11077), (44, 11000)]
RUN1_PEAK = 40


class Curve:
    """Linear interpolation between the knots; what Search asks of a metric."""

    def __init__(self, knots):
        self.knots, self.lev = sorted(knots), 1

    def __call__(self, pos):
        knots = self.knots
        if pos <= knots[0][0]:
            return knots[0][1]
        if pos >= knots[-1][0]:
            return knots[-1][1]
        for (p0, v0), (p1, v1) in zip(knots, knots[1:]):
            if p0 <= pos <= p1:
                return v0 + (v1 - v0) * (pos - p0) // (p1 - p0)


def bell(peak, lo, hi, height=2200, base=2900, width=40):
    """Run 2's amplitude (5100 at the peak, 2900 far away) as a curve."""
    return [(p, int(base + height * math.exp(-((p - peak) / float(width)) ** 2)))
            for p in range(lo, hi + 1)]


def replay(knots, start, direction):
    """One run: reason, final position, the Search, the motor, the log."""
    lo, hi = min(p for p, _ in knots), max(p for p, _ in knots)
    motor = af.ReplayMotor([(p, "") for p in range(lo, hi + 1)], start, direction)
    turns, original, lines = [], motor.change_direct, []
    motor.change_direct = lambda: (turns.append(1), original())
    search = af.Search(motor, lambda: motor.state().step, Curve(knots),
                       af.PROFILES["hy310"], lines.append)
    try:
        reason = search.run()[0]
    except af.Edge as exc:
        reason = "edge: %s" % exc
    falls = max(int(line.split("W:")[1].split()[0]) for line in lines)
    return reason, motor.state().step, search, motor, len(turns), falls


class Run1(unittest.TestCase):

    def test_run_1_ends_in_a_peak_at_its_maximum(self):
        """26.09.: 9069 -> 858 over 350 msteps without a turn, exit 5."""
        reason, position, search, motor, turns, falls = replay(RUN1, 0, 0)
        self.assertEqual(reason, "peak")
        self.assertLessEqual(abs(position - RUN1_PEAK), 8, position)
        self.assertLessEqual(abs(search.best_step - RUN1_PEAK), 8)
        self.assertLessEqual(motor.reversals, af.EDGE_REVERSE_CAP)
        self.assertLessEqual((turns, falls), (3, af.FALL_RUN))
        self.assertLess(search.passes, 40)

    def test_the_fall_run_turns_the_search_round_within_five_passes(self):
        """Run 1's curve with its maximum inside the range: past it the
        search falls back from state 3 and must turn on the fifth fall
        (W:4), as the vendor does - the device counted W up to 43."""
        knots = RUN1[:-1] + [(48, 10700), (56, 10200), (64, 9600), (80, 8500)]
        reason, position, search, motor, turns, falls = replay(knots, 0, 0)
        self.assertEqual((reason, motor.reversals), ("peak", 0))
        self.assertLessEqual(abs(position - RUN1_PEAK), 8, position)
        self.assertEqual(falls, af.FALL_RUN)
        self.assertLessEqual(turns, 3)
        for start in (-300, -100):
            reason, position = replay(knots, start, 0)[:2]
            self.assertEqual(reason, "peak", start)
            self.assertLessEqual(abs(position - RUN1_PEAK), 8, (start, position))


class Run2(unittest.TestCase):
    """Run 2 started 4 below the upper edge, walked away from its peak first,
    turned after a fall run and confirmed: exit 0. Three placements of the
    peak, always starting at -4 going down."""

    def test_run_2s_shape_still_ends_in_a_peak(self):
        for knots, peak in ((bell(12, -400, 40), 12), (bell(12, -400, 12), 12),
                            (bell(-24, -400, 40), -24)):
            reason, position, search, motor, turns, falls = replay(knots, -4, 1)
            self.assertEqual(reason, "peak", peak)
            self.assertLessEqual(abs(position - peak), 8, (peak, position))
            self.assertLessEqual(motor.reversals, af.EDGE_REVERSE_CAP)
            self.assertLessEqual(falls, af.FALL_RUN)


class RealFrames(unittest.TestCase):

    def test_a_peak_beyond_the_edge_is_found_at_the_edge(self):
        """The 23.09. shape on real frames: the sharpest frame lies beyond the
        upper edge. FB-AFWAIT saw five turn-arounds and exit 5; now the run
        ends at the edge with a peak, and nothing has to walk back."""
        with tempfile.TemporaryDirectory() as box, \
                open(os.path.join(box, "out"), "w+") as out, \
                open(os.devnull, "w") as null, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(null):
            mf.build(box, 60, 90, 0.03, 1.5)
            code = af.main(["--no-helper", "-q", "run", "--dry-run", box,
                            "--start", "30", "--timeout", "0"])
            out.seek(0)
            line = out.read().splitlines()[-1]
        self.assertEqual(code, 0)
        self.assertIn("stopped: peak", line)
        self.assertGreaterEqual(int(line.split("position")[1].split()[0]), 52)


if __name__ == "__main__":
    unittest.main(verbosity=2)
