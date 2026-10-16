"""Tests for h713-kodi-switch source (the start of h713-kodi.service) against a made-up root and h713-tv: no device, no
systemd. The unit starts Kodi even when h713-tv is not there yet; a h713-tv that is there and does not take the command
stops the start."""
import os
import socket
import subprocess
import tempfile
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "rootfs", "overlay-desktop",
                    "usr", "local", "sbin", "h713-kodi-switch")


class Root:
    def __init__(self, tv_rc=0, socket_up=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.log = os.path.join(self.d, "log")
        self.tv = os.path.join(self.d, "tv")
        with open(self.tv, "w") as f:
            f.write('#!/bin/sh\necho "tv $@" >> %s\nexit %d\n' % (self.log, tv_rc))
        os.chmod(self.tv, 0o755)
        self.sock = None
        if socket_up:
            os.makedirs(os.path.join(self.d, "run", "h713-tv"))
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(os.path.join(self.d, "run", "h713-tv", "ctl"))

    def __del__(self):
        if self.sock:
            self.sock.close()
        self.tmp.cleanup()

    def run(self, *args):
        env = dict(os.environ, H713_ROOT=self.d, H713_TV=self.tv)
        return subprocess.run(["sh", TOOL, *args], env=env, capture_output=True, text=True, timeout=20)

    def calls(self):
        try:
            with open(self.log) as f:
                return [l.strip() for l in f]
        except FileNotFoundError:
            return []


class TestSource(unittest.TestCase):
    def test_tells_h713_tv_auto(self):
        r = Root()
        self.assertEqual(r.run("source").returncode, 0)
        self.assertEqual(r.calls(), ["tv ctl source auto"])

    def test_no_h713_tv_yet_is_no_error(self):
        # the first seconds after the boot, the 5 s after a crash: Kodi starts, h713-tv comes up on auto by tv.conf
        r = Root(socket_up=False)
        self.assertEqual(r.run("source").returncode, 0)
        self.assertEqual(r.calls(), [])

    def test_h713_tv_that_refuses_stops_the_start(self):
        r = Root(tv_rc=1)
        self.assertEqual(r.run("source").returncode, 1)
        self.assertEqual(r.calls(), ["tv ctl source auto"])

    def test_quit_without_a_pid_is_still_nothing_to_wait_for(self):
        self.assertEqual(Root(socket_up=False).run("quit").returncode, 0)

    def test_usage(self):
        r = Root(socket_up=False).run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("source", r.stderr)


if __name__ == "__main__":
    unittest.main()
