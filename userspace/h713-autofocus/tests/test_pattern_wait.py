#!/usr/bin/env python3
"""FB-AFWAIT: the wait for the pattern and return_to_best, without a device."""

import contextlib
import io
import os
import tempfile
import types
import unittest

from test_h713_autofocus import af, mf


def _camera(frames):
    """grab() hands the frames out, the last one for ever; expose() is kept."""
    frames, cam = list(frames), types.SimpleNamespace(exposures=[])
    cam.grab = lambda: frames.pop(0) if len(frames) > 1 else frames[0]
    cam.expose = cam.exposures.append
    return cam


class PatternWait(unittest.TestCase):

    def setUp(self):
        self.black, self.lit, self.flat = (bytes(af.FRAME_BYTES), mf.frame(3.0),
                                           mf.frame(20.0))
        self.limit, af.WAIT_LIMIT_S = af.WAIT_LIMIT_S, 0.5

    def tearDown(self):
        af.WAIT_LIMIT_S = self.limit

    def _warm_up(self, frames):
        camera, err = _camera(frames), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = af.warm_up(camera, af.PROFILES["hy310"], af.Metric("crect", 3))
        return code, err.getvalue(), camera

    def test_a_pattern_that_arrives_late_is_waited_for(self):
        """23.09.: 1479 passed the vendor's 100; the lit board read 25816."""
        self.assertEqual(af.PATTERN_LEVEL, 25816)
        self.assertTrue(1479 < af.PATTERN_FLOOR <= af.PATTERN_LEVEL // 4)
        self.assertGreater(af.picture_present(self.flat), af.PATTERN_FLOOR)
        code, log, camera = self._warm_up([self.black] * 40 + [self.lit])
        self.assertEqual(code, 0)
        self.assertIn("the pattern is on the wall", log)
        self.assertIn("after 56 frames", log)              # probes 14/28 dark
        self.assertGreaterEqual(len(camera.exposures), 3)  # the wake-up writes

    def test_the_wait_is_bounded_and_needs_a_plateau(self):
        code, log, _ = self._warm_up([self.black])
        self.assertEqual(code, af.EXIT_NO_PICTURE)
        self.assertIn("waited", log)
        self.assertIn("floor %d" % af.PATTERN_FLOOR, log)
        n = af.LEVEL_EVERY
        swing = ([self.lit] * n + [self.flat] * n) * 40
        self.assertEqual(self._warm_up(swing)[0], af.EXIT_NO_PICTURE)
        code, log, _ = self._warm_up([self.flat] * n + [self.lit] * 3 * n)
        self.assertEqual((code, "after 42 frames" in log), (0, True))


class ReturnToBest(unittest.TestCase):

    def _search(self, start, best):
        motor = af.ReplayMotor([(i, "") for i in range(120)], start, 0)
        search = af.Search(motor, None, None, af.PROFILES["hy310"], lambda _: None)
        search.passes, search.best_step = 7, best
        return search, motor

    def test_the_way_back_goes_up_and_down_in_command_sized_moves(self):
        for start, best in ((20, 61), (90, 61)):
            search, motor = self._search(start, best)
            lines = []
            self.assertEqual(af.return_to_best(search, lines.append), best - start)
            self.assertEqual((motor.state().step, motor.moved, motor.direction),
                             (best, abs(best - start), 0 if best > start else 1))
            self.assertEqual(lines, ["back at the best position seen: %d (%d "
                                     "msteps)" % (best, abs(best - start))])
        self.assertEqual(af.return_to_best(self._search(60, 61)[0], None), 0)

    def test_a_run_without_a_peak_goes_back_to_its_best(self):
        """The vendor's own no-peak exit, the pass budget: 11 passes end the
        run on its first move away from the fixture's sharp end (the 23.09.
        fixture itself now converges, test_search_reversal), so do_run walks
        back to the best position and exits 6."""
        seen, original = [], af.return_to_best
        af.return_to_best = lambda s, log: seen.append((s, original(s, log)))
        profile = af.PROFILES["hy310"]
        af.PROFILES["hy310"] = profile._replace(budget=11)
        try:
            with tempfile.TemporaryDirectory() as box, \
                    open(os.devnull, "w") as null, \
                    contextlib.redirect_stdout(null), contextlib.redirect_stderr(null):
                mf.build(box, 60, 90, 0.03, 1.5)
                code = af.main(["--no-helper", "-q", "run", "--dry-run", box,
                                "--start", "30", "--direction", "1",
                                "--timeout", "0"])
        finally:
            af.return_to_best, af.PROFILES["hy310"] = original, profile
        self.assertEqual(code, af.EXIT_NO_PEAK)
        (search, back), = seen
        self.assertGreater(back, 0)
        self.assertEqual((search.motor.state().step, search.best_step), (30, 30))

    def test_the_way_back_after_a_cap_ended_run_never_turns_round(self):
        """26.09.: the walk back tripped the turn-around cap the run had
        spent. It resets the cap, and a latched edge ahead ends the walk
        instead of turning it - stale from the run (nothing moves) or met on
        the way (the best lay at the edge, the counter had drifted)."""
        search, motor = self._search(0, 61)
        motor.reversals, motor.edge_dn = af.EDGE_REVERSE_CAP + 1, True
        lines = []
        self.assertEqual(af.return_to_best(search, lines.append), 61)
        self.assertEqual((motor.reversals, motor.direction, motor.state().step),
                         (0, 0, 61))
        search, motor = self._search(100, 61)
        motor.edge_dn = True                            # stale, and ahead
        self.assertEqual(af.return_to_best(search, lines.append), 0)
        self.assertIn("lower edge is latched 39 msteps short", lines[-1])
        self.assertEqual((motor.direction, motor.state().step), (1, 100))
        search, motor = self._search(90, 130)           # frames end at 119
        # the motor moved 90 -> 119 = 29 (the driver drops the commands
        # towards the latched edge; 36 were issued), 11 short of 130
        self.assertEqual(af.return_to_best(search, lines.append), 29)
        self.assertIn("upper edge is latched 11 msteps short", lines[-1])
        self.assertEqual((motor.reversals, motor.direction, motor.state().step,
                          motor.edge_up), (0, 0, 119, True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
