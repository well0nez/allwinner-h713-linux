"""Host tests for h713-keys: a fake /sys and /dev/input, a fake h713-tv and h713-osd socket, a fake h713-focus.

python3 -m unittest discover -s tests -v   (from userspace/h713-keys)
"""

import importlib.machinery
import importlib.util
import os
import socket
import struct
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "h713-keys")
EVENT = struct.Struct("qqHHi")
KEY = {"up": 115, "down": 114, "mute": 113, "f4": 62, "f5": 63, "record": 167, "power": 116, "home": 172, "search": 217}


class FakeServer(threading.Thread):
    """A one-line-per-connection control socket that records what it got."""

    def __init__(self, path, answer):
        super().__init__(daemon=True)
        self.path, self.answer, self.lines = path, answer, []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(8)

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            with c:
                data = b""
                while not data.endswith(b"\n"):
                    b = c.recv(1024)
                    if not b:
                        break
                    data += b
                line = data.decode().strip()
                self.lines.append(line)
                c.sendall(self.answer(line).encode())

    def stop(self):
        self.sock.close()


class Tv:
    """h713-tv's answers, with a state the tests set."""

    def __init__(self):
        self.volume, self.muted, self.mode = 50, False, "auto"

    def __call__(self, line):
        w = line.split()
        if w == ["volume"]:
            return "ok volume %d (-22.0 dB)\n" % self.volume
        if w[0] == "volume":
            self.volume = int(w[1])
            return "ok volume %d (-22.0 dB)\n" % self.volume
        if w == ["mute"]:
            return "ok mute %s (DSP and codec)\n" % ("on" if self.muted else "off")
        if w[0] == "mute":
            self.muted = w[1] == "on"
            return "ok mute %s\n" % w[1]
        if line == "status brief":
            return "ok status\nmode            %s\n" % ("automatic" if self.mode == "auto" else "off (console forced)")
        if line in ("off", "auto"):
            self.mode = line
            return "ok %s\n" % line
        return "error unknown command\n"


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.tv = Tv()
        self.tvs = FakeServer(os.path.join(self.root, "tv.sock"), self.tv)
        self.osds = FakeServer(os.path.join(self.root, "osd.sock"), lambda line: "ok\n")
        self.tvs.start()
        self.osds.start()
        self.focus_log = os.path.join(self.root, "focus.log")
        self.focus_rc = os.path.join(self.root, "focus.rc")
        focus = os.path.join(self.root, "h713-focus")
        with open(focus, "w") as f:
            f.write('#!/bin/sh\necho "$@" >> %s\nexit $(cat %s 2>/dev/null || echo 0)\n' % (self.focus_log, self.focus_rc))
        os.chmod(focus, 0o755)
        os.makedirs(os.path.join(self.root, "etc/h713"))
        self.device(0, name="sunxi-ir", ids=("0001", "0001"))
        self.device(1, name="h713 remote", ids=("1d5a", "c081"))
        self.device(2, name="USB keyboard", ids=("046d", "c31c"))
        os.environ.update(H713_KEYS_ROOT=self.root, H713_KEYS_TV=self.tvs.path,
                          H713_KEYS_OSD=self.osds.path, H713_KEYS_FOCUS=focus)
        loader = importlib.machinery.SourceFileLoader("h713keys", PROG)
        spec = importlib.util.spec_from_loader("h713keys", loader)
        self.mod = importlib.util.module_from_spec(spec)
        loader.exec_module(self.mod)

    def tearDown(self):
        self.tvs.stop()
        self.osds.stop()
        self.tmp.cleanup()

    def device(self, n, name, ids):
        d = os.path.join(self.root, "sys/class/input/event%d/device" % n)
        os.makedirs(os.path.join(d, "id"))
        for f, v in (("name", name), ("id/vendor", ids[0]), ("id/product", ids[1])):
            with open(os.path.join(d, f), "w") as fh:
                fh.write(v + "\n")
        os.makedirs(os.path.join(self.root, "dev/input"), exist_ok=True)
        open(os.path.join(self.root, "dev/input/event%d" % n), "wb").close()

    def press(self, key, dev=1, value=1):
        with open(os.path.join(self.root, "dev/input/event%d" % dev), "ab") as f:
            f.write(EVENT.pack(0, 0, 1, KEY[key], value) + EVENT.pack(0, 0, 0, 0, 0))

    def run_once(self):
        self.mod.run(once=True)
        time.sleep(0.05)
        for n in range(3):                  # the next round starts with empty devices
            open(os.path.join(self.root, "dev/input/event%d" % n), "wb").close()

    def test_louder(self):
        self.press("up")
        self.run_once()
        self.assertEqual(self.tv.volume, 55)
        self.assertIn("volume 55", self.osds.lines)

    def test_louder_lifts_mute(self):
        self.tv.muted = True
        self.press("up")
        self.run_once()
        self.assertIn("mute off", self.tvs.lines)
        self.assertFalse(self.tv.muted)

    def test_quieter_lifts_mute(self):
        self.tv.muted = True
        self.press("down")
        self.run_once()
        self.assertIn("mute off", self.tvs.lines)
        self.assertEqual(self.tv.volume, 45)

    def test_mute_toggles_and_shows(self):
        self.press("mute")
        self.run_once()
        self.assertTrue(self.tv.muted)
        self.assertIn("mute on 50", self.osds.lines)

    def test_mute_repeat_does_nothing(self):
        self.press("mute", value=2)
        self.press("home")
        self.run_once()
        self.assertFalse(self.tv.muted)

    def test_no_input_key_by_default(self):
        self.press("record")
        self.run_once()
        self.assertEqual(self.tv.mode, "auto")

    def test_input_to_console_and_back(self):
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("input_keys = KEY_RECORD\n")
        self.press("record")
        self.run_once()
        self.assertEqual(self.tv.mode, "off")
        self.assertIn("input console", self.osds.lines)
        self.press("record")
        self.run_once()
        self.assertEqual(self.tv.mode, "auto")
        self.assertIn("input hdmi", self.osds.lines)

    def test_focus_runs_and_shows(self):
        self.press("f4")
        self.run_once()
        with open(self.focus_log) as f:
            self.assertEqual(f.read().split(), ["up", "20"])
        self.assertIn("focus up", self.osds.lines)

    def test_focus_edge(self):
        with open(self.focus_rc, "w") as f:
            f.write("3")
        self.press("f5")
        self.run_once()
        self.assertIn("focus down edge", self.osds.lines)

    def test_no_focus_motor_stops_asking(self):
        with open(self.focus_rc, "w") as f:
            f.write("7")
        focus = self.mod.Focus()
        focus.press("up", 3)
        focus.press("down", 3)              # waiting while the first run says exit 7
        while focus.proc is not None:
            focus.tick()
            time.sleep(0.01)
        focus.press("up", 3)
        self.assertIsNone(focus.proc)
        with open(self.focus_log) as f:
            self.assertEqual(f.read().split(), ["up", "3"])     # h713-focus ran once
        self.assertEqual(self.osds.lines, [])

    def test_an_unknown_key_is_logged_once(self):
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        self.press("search")
        self.press("search")
        self.run_once()
        self.assertEqual(out.count("KEY_SEARCH (code 217): no meaning here"), 1)

    def test_edge_drops_what_waits_that_way(self):
        with open(self.focus_rc, "w") as f:
            f.write("3")
        shown = []
        self.mod.osd = lambda *a: shown.append(" ".join(a))
        focus = self.mod.Focus()
        focus.press("up", 20)
        focus.press("up", 20)               # held: waits behind the first run
        focus.press("up", 20)
        self.assertEqual(focus.pending, {"up": 40})     # at most two presses wait
        while focus.proc is not None:
            focus.tick()
            time.sleep(0.01)
        self.assertEqual(shown, ["focus up edge"])
        with open(self.focus_log) as f:
            self.assertEqual(f.read().split(), ["up", "20"])    # the edge ended it, nothing ran after

    def test_focus_steps_up_to_100(self):
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("focus_steps = 60\n")
        self.press("f4")
        self.run_once()
        with open(self.focus_log) as f:
            self.assertEqual(f.read().split(), ["up", "60"])

    def test_a_keyboard_is_not_the_remote(self):
        self.press("f4", dev=2)
        self.press("home")                  # a key on the remote ends the round
        self.run_once()
        self.assertFalse(os.path.exists(self.focus_log))

    def test_ir_receiver_is_read(self):
        self.press("up", dev=0)
        self.run_once()
        self.assertEqual(self.tv.volume, 55)

    def test_power_is_left_to_h713_power(self):
        self.press("power")
        self.run_once()
        self.assertEqual(self.tvs.lines, [])
        self.assertEqual(self.osds.lines, [])

    def test_volume_step_from_keys_conf(self):
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("volume_step = 10\n")
        self.press("up")
        self.run_once()
        self.assertEqual(self.tv.volume, 60)

    def test_no_osd_daemon_is_no_error(self):
        os.unlink(self.osds.path)
        self.press("up")
        self.run_once()
        self.assertEqual(self.tv.volume, 55)

    def test_focus_switch_shows_the_run_that_ended(self):
        shown = []
        self.mod.osd = lambda *a: shown.append(" ".join(a))
        focus = self.mod.Focus()
        focus.press("up", 3)                # starts at once
        focus.press("down", 3)              # waits for the next run
        while focus.running == "up":
            focus.tick()
            time.sleep(0.01)
        self.assertEqual(shown[0], "focus up")
        while focus.proc is not None:
            focus.tick()
            time.sleep(0.01)
        self.assertEqual(shown[1], "focus down")
        with open(self.focus_log) as f:
            self.assertEqual(f.read().split(), ["up", "3", "down", "3"])


if __name__ == "__main__":
    unittest.main()
