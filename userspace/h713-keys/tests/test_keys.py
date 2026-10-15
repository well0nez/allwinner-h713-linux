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
KEY = {"up": 115, "down": 114, "mute": 113, "f4": 62, "f5": 63, "record": 167, "power": 116, "home": 172, "search": 217,
       "select": 353, "nav_up": 103, "nav_down": 108, "ok": 352, "back": 158, "left": 105}


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
            return ("ok status\nmode            %s\nsignal          1920x1080p59.94, 148.4 MHz (last measured)\n"
                    % ("automatic" if self.mode == "auto" else "off (console forced)"))
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
        systemctl = os.path.join(self.root, "systemctl")
        self.systemctl_log = os.path.join(self.root, "systemctl.log")
        with open(systemctl, "w") as f:
            f.write('#!/bin/sh\necho "$@" >> %s\ncase "$1" in is-active) exit $(cat %s.rc 2>/dev/null || echo 3) ;; esac\nexit 0\n'
                    % (self.systemctl_log, systemctl))
        os.chmod(systemctl, 0o755)
        self.power = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)       # h713-power's, for the Power press
        self.power.bind(os.path.join(self.root, "power.sock"))
        self.power.settimeout(0.5)
        os.environ.update(H713_KEYS_ROOT=self.root, H713_KEYS_TV=self.tvs.path, H713_KEYS_OSD=self.osds.path,
                          H713_KEYS_FOCUS=focus, H713_KEYS_SYSTEMCTL=systemctl,
                          H713_KEYS_POWER=os.path.join(self.root, "power.sock"))
        loader = importlib.machinery.SourceFileLoader("h713keys", PROG)
        spec = importlib.util.spec_from_loader("h713keys", loader)
        self.mod = importlib.util.module_from_spec(spec)
        loader.exec_module(self.mod)

    def tearDown(self):
        self.power.close()
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

    def test_select_is_ok(self):
        """over Bluetooth OK is HID Menu Pick = KEY_SELECT (11.10., G-EU) - the same key as KEY_OK over IR"""
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        self.press("select")
        self.run_once()
        self.assertIn("KEY_OK: recognised, no action yet", out)
        self.assertFalse([m for m in out if "no meaning here" in m], out)

    def test_bluetooth_remote_repeats_like_ir(self):
        calls, out = [], []
        self.mod.log = lambda msg, level="": out.append(msg)
        real = self.mod.fcntl.ioctl
        self.mod.fcntl.ioctl = lambda fd, req, arg=0: calls.append((req, arg))
        try:
            self.press("home")
            self.run_once()
        finally:
            self.mod.fcntl.ioctl = real
        self.assertEqual(calls, [(0x40084503, struct.pack("II", 500, 125))])    # only the Bluetooth remote
        self.assertTrue([m for m in out if m.endswith("event1, repeat 500/125 ms as over IR")], out)

    def test_repeat_refused_is_said(self):
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        self.press("home")
        self.run_once()                     # a plain file here: the ioctl fails, the key still counts
        self.assertTrue([m for m in out if "event1, repeat left at the kernel's" in m], out)

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


    # --- the launcher (package H) ----------------------------------------------------------------------------------

    def launcher_d(self, **files):
        """etc/h713/launcher.d/<name>.conf = the given text; the defaults are the three entries of package H"""
        d = os.path.join(self.root, "etc/h713/launcher.d")
        os.makedirs(d, exist_ok=True)
        files = files or {
            "10-hdmi": "label = HDMI input\nicon = hdmi\nexec = %s/mode hdmi\nnow = HDMI {signal}\nfallback = yes\n" % self.root,
            "20-kodi": "label = Kodi\nicon = film\nunit = h713-kodi.service\nactive = %s is-active --quiet h713-kodi.service\n"
                       % os.path.join(self.root, "systemctl"),
            "90-standby": "label = Standby\nicon = power\nexec = %s suspend\ngroup = end\n" % os.path.join(self.root, "systemctl")}
        for name, text in files.items():
            with open(os.path.join(d, name + ".conf"), "w") as f:
                f.write(text)

    def grabs(self):
        """EVIOCGRAB calls of the next run, as (device file, on). A fake device that has nothing to read counts as a
        remote that went away (EOF), so the IR receiver gets a key of no meaning to stay in the round."""
        self.press("search", dev=0)
        calls = []
        self.mod.grab = lambda fd, on: calls.append((os.path.basename(os.readlink("/proc/self/fd/%d" % fd)), on)) and None
        return calls

    def systemctl_calls(self):
        try:
            with open(self.systemctl_log) as f:
                return f.read().splitlines()
        except OSError:
            return []

    def test_home_opens_the_launcher_and_holds_the_remote(self):
        self.launcher_d()
        calls = self.grabs()
        self.press("home")
        self.run_once()
        self.assertEqual(self.osds.lines, ["launcher 0;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby"])   # 59.94 -> 60
        self.assertEqual(sorted(calls), [("event0", True), ("event1", True)])      # the IR receiver and the remote, no keyboard

    def test_down_ok_starts_kodi_and_lets_go(self):
        self.launcher_d()
        calls = self.grabs()
        for k in ("home", "nav_down", "ok"):
            self.press(k)
        self.run_once()
        self.assertEqual(self.osds.lines[1:], ["launcher 1", "launcher close"])
        self.assertEqual(sorted(c for c in calls if not c[1]), [("event0", False), ("event1", False)])
        time.sleep(0.2)
        self.assertEqual(self.systemctl_calls(), ["is-active --quiet h713-kodi.service", "start --no-block h713-kodi.service"])

    def test_a_running_kodi_is_the_selected_entry(self):
        self.launcher_d()
        self.grabs()
        self.press("home")
        with open(os.path.join(self.root, "systemctl.rc"), "w") as f:       # is-active: 0 for everything: Kodi runs
            f.write("0")
        self.run_once()
        self.assertTrue(self.osds.lines[0].startswith("launcher 1;Kodi;"), self.osds.lines)

    def test_back_and_home_close_without_acting(self):
        self.launcher_d()
        self.grabs()
        for k in ("home", "back", "home", "home"):
            self.press(k)
        self.run_once()
        self.assertEqual([l.split(";")[0] for l in self.osds.lines], ["launcher 0", "launcher close", "launcher 0", "launcher close"])
        self.assertEqual([c for c in self.systemctl_calls() if c.startswith("start")], [])

    def test_the_launcher_leaves_volume_alone(self):
        """volume, mute and focus work with the launcher open; Left, Menu, the other keys are nobody's"""
        self.launcher_d()
        self.grabs()
        for k in ("home", "up", "left"):
            self.press(k)
        self.run_once()
        self.assertEqual(self.tv.volume, 55)
        self.assertIn("volume 55", self.osds.lines)
        self.assertEqual(self.osds.lines.count("launcher close"), 0)

    def test_power_closes_the_launcher_and_goes_on_to_h713_power(self):
        self.launcher_d()
        calls = self.grabs()
        for k in ("home", "power"):
            self.press(k)
        self.run_once()
        self.assertEqual(self.osds.lines[-1], "launcher close")
        self.assertTrue(all(not c[1] for c in calls[-2:]))
        self.assertEqual(self.power.recv(64), b"short")

    def test_no_picture_no_launcher_and_no_grab(self):
        self.launcher_d()
        self.osds.answer = lambda line: "ok unseen\n"
        calls = self.grabs()
        for k in ("home", "nav_down"):
            self.press(k)
        self.run_once()
        self.assertEqual(calls, [])
        self.assertEqual(self.osds.lines, [self.osds.lines[0]])            # the second key found no launcher: not sent

    def test_no_osd_daemon_no_launcher(self):
        self.launcher_d()
        os.unlink(self.osds.path)
        calls = self.grabs()
        self.press("home")
        self.run_once()
        self.assertEqual(calls, [])

    def test_a_remote_that_cannot_be_held_is_no_launcher(self):
        self.launcher_d()
        calls = []
        self.mod.grab = lambda fd, on: calls.append(on) or ("Device or resource busy" if on and len(calls) == 2 else None)
        self.press("search", dev=0)
        self.press("home")
        self.run_once()
        self.assertEqual(self.osds.lines[-1], "launcher close")             # the one that was held is let go again
        self.assertIn(False, calls)

    def test_entries_show_active_exec_and_order(self):
        self.launcher_d(**{"30-b": "label = B\nicon = desk\nexec = %s/runb\n" % self.root,
                           "10-a": "label = A;x\nicon = globe\nunit = a.service\nshow = %s\n" % os.path.join(self.root, "systemctl"),
                           "20-bad": "label = no icon\nunit = c.service\n",
                           "05-hidden": "label = Hidden\nicon = film\nunit = h.service\nshow = /nonexistent/check\n"})
        run = os.path.join(self.root, "runb")
        with open(run, "w") as f:
            f.write("#!/bin/sh\necho ran > %s.out\n" % run)
        os.chmod(run, 0o755)
        self.grabs()
        for k in ("home", "nav_down", "ok"):
            self.press(k)
        self.run_once()
        self.assertEqual(self.osds.lines[0], "launcher 0;A,x;globe:A,x;desk:B")    # sorted by file name, a ";" cannot split a field
        time.sleep(0.3)
        with open(run + ".out") as f:
            self.assertEqual(f.read().strip(), "ran")

    def test_an_idle_launcher_closes(self):
        self.launcher_d()
        grabbed = self.grabs()
        l = self.mod.Launcher()
        fd = os.open(os.path.join(self.root, "dev/input/event1"), os.O_RDONLY | os.O_NONBLOCK)
        l.open({"event1": fd})
        self.assertTrue(l.is_open())
        l.tick({"event1": fd})
        self.assertTrue(l.is_open())
        l.last -= self.mod.LAUNCHER_IDLE_S + 1
        l.tick({"event1": fd})
        self.assertFalse(l.is_open())
        self.assertEqual(self.osds.lines[-1], "launcher close")
        self.assertEqual(grabbed[-1][1], False)
        os.close(fd)

    def test_home_without_entries_does_nothing(self):
        calls = self.grabs()
        self.press("home")
        self.run_once()
        self.assertEqual((calls, self.osds.lines), ([], []))


if __name__ == "__main__":
    unittest.main()
