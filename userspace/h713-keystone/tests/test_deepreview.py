"""Deep review (geometry, 27.09.2026): the watch against the reference taken
while it runs, a dead sensor, and the search that must not run per reading."""
import io
import os
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_h713_keystone as t   # noqa: E402

ks, ak, POSES, REST = t.ks, t.ak, t.POSES, t.REST


class Watch(t.Commands):
    def _conf(self, after_move):
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("after_move = %s\naverage_samples = 1\nmove_degrees = 3\n"
                     "settle_seconds = 0.5\n" % after_move)

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ks.main([a for a in self.base if a != "--quiet"] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_a_reference_taken_while_watching_counts_from_the_next_apply(self):
        """The page's Level reference does not restart the unit: the watch
        started without a file must apply against the file written since."""
        self._conf("keystone")
        conf = ks.load_conf(os.path.join(self.dir, "keystone.conf"))

        def later():
            time.sleep(0.2)
            counts = ak.reference_from_iio(ks.model_triple(REST, conf))
            ks.write_reference(self.reference, counts, tuple(map(float, REST)), conf)
            time.sleep(0.2)
            for axis, value in zip("xyz", POSES[1][1:4]):
                self.iio.write("iio:device2/in_accel_%s_raw" % axis, str(value))
        threading.Thread(target=later, daemon=True).start()
        code, out, _ = self._run("--last-auto", os.path.join(self.dir, "la"),
                                 "watch", "--dry-run", "--for", "3")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("ok apply"), 1, out)
        self.assertIn("pitch 20.586", out)          # against the file, not 29.732
        self.assertIn("(dry run)  reference file (", out)

    def test_a_dead_sensor_is_not_a_level_projector(self):
        for axis in "xyz":
            self.iio.write("iio:device2/in_accel_%s_raw" % axis, "0")
        with self.assertRaises(ks.Error) as caught:
            self.run_tool("once", "--apply")
        self.assertEqual(caught.exception.code, ks.EXIT_NO_SENSOR)

    def test_the_watch_says_a_dead_sensor_once_and_stays_up(self):
        self._conf("keystone")
        for axis in "xyz":
            self.iio.write("iio:device2/in_accel_%s_raw" % axis, "0")
        code, out, err = self._run("watch", "--dry-run", "--for", "1")
        self.assertEqual(code, 0)
        self.assertEqual(err.count("not about 1 g"), 1, err)
        self.assertNotIn("ok apply", out)

    def test_the_search_runs_only_when_something_is_applied(self):
        """At rest with after_move = off nothing is applied, so the corner
        search (3.3 s per reading at 58 degrees on the review host) never runs."""
        self._conf("off")
        calls = []
        real = ks.ak.auto_keystone
        ks.ak.auto_keystone = lambda *a, **k: calls.append(1) or real(*a, **k)
        self.addCleanup(setattr, ks.ak, "auto_keystone", real)
        code, out, _ = self._run("watch", "--dry-run", "--for", "1")
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
