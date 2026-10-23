"""Tests for h713-kodi-switch source (the start of a mode unit) and ready (the launcher's wait for Kodi) against a made-up
root, h713-tv and h713-warp: no device, no systemd. The unit starts the program even when h713-tv is not there yet; a h713-tv
that is there and does not take the command stops the start. `source` says "client": a program is the mode."""
import os
import socket
import subprocess
import tempfile
import threading
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "rootfs", "overlay-desktop",
                    "usr", "local", "sbin", "h713-kodi-switch")


class Root:
    def __init__(self, tv_rc=0, socket_up=True, pictures="grow"):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.log = os.path.join(self.d, "log")
        self.tv = os.path.join(self.d, "tv")
        with open(self.tv, "w") as f:
            f.write('#!/bin/sh\necho "tv $@" >> %s\nexit %d\n' % (self.log, tv_rc))
        os.chmod(self.tv, 0o755)
        # h713-warp ctl picture: "grow" one more picture at every question, "stand" always the same, "none" no client picture
        self.warp = os.path.join(self.d, "warp")
        count = os.path.join(self.d, "pictures")
        with open(self.warp, "w") as f:
            if pictures == "none":
                f.write('#!/bin/sh\necho "error no picture of a Wayland client on the panel"\nexit 1\n')
            else:
                f.write('#!/bin/sh\nn=$(cat %s 2>/dev/null || echo 5)\n%s\necho "ok $n pictures of the Wayland client on the panel"\n'
                        % (count, 'echo $((n + 1)) > %s' % count if pictures == "grow" else ":"))
        os.chmod(self.warp, 0o755)
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
        env = dict(os.environ, H713_ROOT=self.d, H713_TV=self.tv, H713_WARP=self.warp, H713_KODI_PORT=str(getattr(self, "port", 9)))
        return subprocess.run(["sh", TOOL, *args], env=env, capture_output=True, text=True, timeout=20)

    def calls(self):
        try:
            with open(self.log) as f:
                return [l.strip() for l in f]
        except FileNotFoundError:
            return []


class TestSource(unittest.TestCase):
    def test_tells_h713_tv_client(self):
        # a program is the mode: its picture only, never the ring between two programs (h713-warp holds the last one)
        r = Root()
        self.assertEqual(r.run("source").returncode, 0)
        self.assertEqual(r.calls(), ["tv ctl source client"])

    def test_no_h713_tv_yet_is_no_error(self):
        # the first seconds after the boot, the 5 s after a crash: Kodi starts, h713-tv comes up on auto by tv.conf
        r = Root(socket_up=False)
        self.assertEqual(r.run("source").returncode, 0)
        self.assertEqual(r.calls(), [])

    def test_h713_tv_that_refuses_stops_the_start(self):
        r = Root(tv_rc=1)
        self.assertEqual(r.run("source").returncode, 1)
        self.assertEqual(r.calls(), ["tv ctl source client"])

    def test_quit_without_a_pid_is_still_nothing_to_wait_for(self):
        self.assertEqual(Root(socket_up=False).run("quit").returncode, 0)

    def test_usage(self):
        r = Root(socket_up=False).run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("source", r.stderr)


if __name__ == "__main__":
    unittest.main()


class TestReady(unittest.TestCase):
    """`ready`: exit 0 once Kodi answers JSONRPC.Ping and h713-warp holds a picture of Kodi's from after that answer (the
    launcher's "Starting Kodi..." waits for it: cage's first picture is black, the answer alone comes before the picture)"""

    def serve(self, answer, pictures="grow"):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        self.addCleanup(srv.close)

        def loop():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                with c:
                    c.recv(512)
                    c.sendall(answer)
        threading.Thread(target=loop, daemon=True).start()
        r = Root(pictures=pictures)
        r.port = srv.getsockname()[1]
        return r

    def test_kodi_answers(self):
        r = self.serve(b'{"id":1,"jsonrpc":"2.0","result":"pong"}')
        self.assertEqual(r.run("ready").returncode, 0)

    def test_no_picture_after_the_answer_is_not_ready(self):
        # Kodi answers, but h713-warp has no picture of it since: the page would go over cage's black or an old picture
        r = self.serve(b'{"id":1,"jsonrpc":"2.0","result":"pong"}', pictures="stand")
        self.assertEqual(r.run("ready").returncode, 1)

    def test_no_client_on_the_panel_is_not_ready(self):
        r = self.serve(b'{"id":1,"jsonrpc":"2.0","result":"pong"}', pictures="none")
        self.assertEqual(r.run("ready").returncode, 1)

    def test_kodi_is_not_there(self):
        r = Root()                                   # nothing listens on the port (9, discard, closed)
        self.assertEqual(r.run("ready").returncode, 1)

    def test_something_else_answers(self):
        r = self.serve(b'{"id":1,"jsonrpc":"2.0","error":{"code":-32601}}')
        self.assertEqual(r.run("ready").returncode, 1)
