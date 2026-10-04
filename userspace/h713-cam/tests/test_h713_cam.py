#!/usr/bin/env python3
"""h713-cam without a camera (boards/README.md, FEATURES). No device: the
board's /sys is a temporary directory handed over in $H713_SYS.

    python3 -m unittest discover -s tests -v          # from h713-cam/
"""

import os
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "h713-cam")


class NotPresent(unittest.TestCase):

    def _run(self, names, *argv):
        with tempfile.TemporaryDirectory() as box:
            for node, name in names.items():
                os.makedirs(os.path.join(box, "class/video4linux", node))
                with open(os.path.join(box, "class/video4linux", node, "name"), "w") as fh:
                    fh.write(name + "\n")
            return subprocess.run([sys.executable, TOOL] + list(argv),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, timeout=60, env=dict(os.environ, H713_SYS=box))

    def test_no_camera_is_exit_7_with_the_verdict_last(self):
        for argv in (["probe"], ["controls"], ["grab", os.devnull]):
            run = self._run({"video0": "cedrus", "video1": "sun50i-h713-hdmirx"}, *argv)
            self.assertEqual(run.returncode, 7, run.stderr)
            self.assertTrue(run.stderr.splitlines()[-1].startswith(
                "h713-cam: camera: not present on this board - "), run.stderr)

    def test_a_named_node_that_does_not_capture_is_still_an_error(self):
        # a node number no host has, so it cannot be opened and never captures
        run = self._run({"video97": "Generic HD camera"}, "probe")
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn("Is uvcvideo loaded?", run.stderr)


if __name__ == "__main__":
    unittest.main()
