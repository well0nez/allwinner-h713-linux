"""Host tests for h713-keys: a fake /sys and /dev/input, a fake h713-tv and h713-osd socket, a fake h713-focus.

python3 -m unittest discover -s tests -v   (from userspace/h713-keys)
"""

import glob
import importlib.machinery
import importlib.util
import os
import re
import select
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
       "select": 353, "enter": 28, "compose": 127, "nav_up": 103, "nav_down": 108, "ok": 352, "back": 158, "left": 105}


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
        self.signal = "signal          1920x1080p59.94, 148.4 MHz (last measured)\n"

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
            return ("ok status\nmode            %s\n%s"
                    % ("automatic" if self.mode == "auto" else "off (console forced)", self.signal))
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
        os.makedirs(os.path.join(self.root, "run"))
        self.booted = os.path.join(self.root, "run/h713-keys.booted")
        open(self.booted, "w").close()                  # not the first start after a boot: the tests that want one remove it
        self.device(0, name="sunxi-ir", ids=("0001", "0001"))
        self.device(1, name="h713 remote", ids=("1d5a", "c081"))
        self.device(2, name="USB keyboard", ids=("046d", "c31c"))
        systemctl = os.path.join(self.root, "systemctl")
        self.systemctl_log = os.path.join(self.root, "systemctl.log")
        with open(systemctl, "w") as f:
            f.write('#!/bin/sh\necho "$@" >> %s\ncase "$1" in is-active) exit $(cat %s.rc 2>/dev/null || echo 3) ;;'
                    ' is-system-running) cat %s.state 2>/dev/null ;; esac\nexit 0\n'
                    % (self.systemctl_log, systemctl, systemctl))
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
        self.assertIn("focus up edge", self.osds.lines)     # the edge picture is the other direction's

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
        self.assertEqual(shown, ["focus down edge"])     # a run up ends with the other direction's edge picture
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


    # --- the launcher ----------------------------------------------------------------------------------

    def keys(self, *names):
        """presses in order; a Home is followed by its release, as a real remote sends it (the grab waits for it)"""
        for k in names:
            self.press(k)
            if k == "home":
                self.press("home", value=0)

    def launcher_d(self, **files):
        """etc/h713/launcher.d/<name>.conf = the given text; the defaults are the three entries"""
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

    def test_the_header_follows_the_signal_while_the_launcher_is_open(self):
        # the start's launcher came before the signal and said "HDMI no signal" over a standing 1080p60 (HY310, 18.10.2026)
        self.launcher_d()
        self.tv.signal = "signal          none\n"
        launcher = self.mod.Launcher()
        self.assertTrue(launcher.open({}))
        self.assertTrue(self.osds.lines[-1].startswith("launcher 0;HDMI no signal;"), self.osds.lines)
        defs = lambda: [l for l in self.osds.lines if l.startswith("launcher ")]   # the definitions (a `status` asked between them is not one)
        n = len(defs())
        launcher.header_follow()
        self.assertEqual(len(defs()), n)                             # the same signal: nothing sent
        self.tv.signal = "signal          1920x1080p59.94, 148.4 MHz (last measured)\n"
        launcher.header_follow()
        self.assertEqual(defs()[-1], "launcher 0;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby")
        launcher.header_follow()
        self.assertEqual(len(defs()), n + 1)                         # and once only

    def test_a_restarted_osd_keeps_its_launcher_closed(self):
        # after a restart of h713-osd under the open launcher it said "closed"; the next change of signal opened it unasked (Mythos 19.10.2026)
        self.launcher_d()
        self.tv.signal = "signal          none\n"
        launcher = self.mod.Launcher()
        self.assertTrue(launcher.open({}))
        n = len(self.osds.lines)
        self.osds.answer = lambda line: "ok status\nlauncher        closed\npage            closed\n" if line == "status" else "ok\n"
        self.tv.signal = "signal          1920x1080p59.94, 148.4 MHz (last measured)\n"
        launcher.header_follow({})
        self.assertFalse([l for l in self.osds.lines[n:] if l.startswith("launcher ") and ";" in l], self.osds.lines[n:])
        self.assertIsNone(launcher.entries)                          # closed here too: no grab, no keys taken
        self.osds.answer = lambda line: "ok status\nlauncher        open\n" if line == "status" else "ok\n"
        launcher2 = self.mod.Launcher()
        self.tv.signal = "signal          none\n"
        self.assertTrue(launcher2.open({}))
        self.tv.signal = "signal          1920x1080p59.94, 148.4 MHz (last measured)\n"
        launcher2.header_follow({})
        self.assertEqual(self.osds.lines[-1], "launcher 0;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby")   # open there: it follows

    def test_home_opens_the_launcher_and_holds_the_remote(self):
        self.launcher_d()
        calls = self.grabs()
        self.keys("home")
        self.run_once()
        self.assertEqual(self.osds.lines, ["launcher 0;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby"])   # 59.94 -> 60
        self.assertEqual(sorted(calls), [("event0", True), ("event1", True)])      # the IR receiver and the remote, no keyboard

    def test_the_grab_waits_for_the_release_of_home(self):
        """15.10.2026: a grab while Home is down lost its release for cage, cage held Home down and Kodi repeated it at 30 Hz"""
        self.launcher_d()
        calls = self.grabs()
        fds = {"event0": os.open(os.path.join(self.root, "dev/input/event0"), os.O_RDONLY | os.O_NONBLOCK),
               "event1": os.open(os.path.join(self.root, "dev/input/event1"), os.O_RDONLY | os.O_NONBLOCK)}
        l = self.mod.Launcher()
        l.open(fds)                                  # the press of Home
        self.assertEqual((l.entries is not None, calls), (True, []))
        l.hold(fds)                                  # its release
        self.assertEqual(sorted(calls), [("event0", True), ("event1", True)])
        l.hold(fds)                                  # another release: nothing is grabbed twice
        self.assertEqual(len(calls), 2)
        l.close(fds)
        l.hold(fds)                                  # the release of the Home that closed it: nothing
        self.assertEqual([c for c in calls if c[1]], [("event0", True), ("event1", True)])
        for fd in fds.values():
            os.close(fd)

    def test_down_ok_starts_kodi_and_lets_go(self):
        self.launcher_d()
        calls = self.grabs()
        self.keys("home", "nav_down", "ok")
        self.run_once()
        # OK sends the selection once more before it starts the row: h713-osd must still show the page
        self.assertEqual(self.osds.lines[1:], ["launcher 1", "launcher 1", "launcher close"])
        self.assertEqual(sorted(c for c in calls if not c[1]), [("event0", False), ("event1", False)])
        time.sleep(0.2)
        self.assertEqual(self.systemctl_calls(), ["is-active --quiet h713-kodi.service", "start --no-block h713-kodi.service"])

    def osd_restarted(self):
        """h713-osd restarted under the open launcher: the page is gone, a command for it finds no launcher"""
        self.osds.answer = lambda line: "ok\n" if ";" in line or line == "launcher close" else "error the launcher is not open\n"

    def test_a_restarted_osd_closes_the_launcher_at_the_next_move(self):
        self.launcher_d()
        calls = self.grabs()
        self.osd_restarted()
        self.keys("home", "nav_down", "nav_down")
        self.run_once()
        self.assertEqual([l.split(";")[0] for l in self.osds.lines], ["launcher 0", "launcher 1", "launcher close"])   # the second Down is not the launcher's
        self.assertEqual(sorted(c for c in calls if c[1]), [("event0", True), ("event1", True)])
        self.assertEqual(sorted(c for c in calls if not c[1]), [("event0", False), ("event1", False)])      # held, then let go at once
        self.assertEqual(self.systemctl_calls(), ["is-active --quiet h713-kodi.service"])

    def test_ok_starts_nothing_when_osd_no_longer_shows_the_launcher(self):
        self.launcher_d()
        calls = self.grabs()
        self.osd_restarted()
        self.keys("home", "ok")
        self.run_once()
        time.sleep(0.2)
        self.assertEqual([l.split(";")[0] for l in self.osds.lines], ["launcher 0", "launcher 0", "launcher close"])
        self.assertNotIn("start --no-block h713-kodi.service", self.systemctl_calls())
        self.assertEqual(sorted(c for c in calls if not c[1]), [("event0", False), ("event1", False)])

    def test_enter_is_ok_in_the_launcher(self):
        """70-h713-remote.rules turns the remote's OK into KEY_ENTER: the launcher takes it as OK"""
        self.launcher_d()
        self.grabs()
        self.keys("home", "nav_down", "enter")
        self.run_once()
        time.sleep(0.2)
        self.assertEqual(self.systemctl_calls(), ["is-active --quiet h713-kodi.service", "start --no-block h713-kodi.service"])

    def test_enter_and_compose_with_the_launcher_closed_are_kodis(self):
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        self.press("enter")
        self.press("compose")
        self.run_once()
        self.assertIn("KEY_OK: recognised, no action yet", out)
        self.assertIn("127: recognised, no action yet", out)
        self.assertFalse([m for m in out if "no meaning here" in m], out)

    def test_the_udev_rule_names_the_scancodes_of_the_ir_keymap(self):
        """the rule's IR scancodes are the keymap's for KEY_OK and KEY_MENU (kernel 0254) - they must not drift apart"""
        root = os.path.join(HERE, "..", "..", "..")
        with open(glob.glob(os.path.join(root, "mainline", "patches", "kernel", "0254-*.patch"))[0]) as f:
            keymap = f.read()
        with open(os.path.join(HERE, "..", "70-h713-remote.rules")) as f:
            rule = f.read()
        ok = re.search(r"\{ 0x0([0-9a-f]{3}), KEY_OK \}", keymap).group(1)
        menu = re.search(r"\{ 0x0([0-9a-f]{3}), KEY_MENU \}", keymap).group(1)
        self.assertIn('ENV{KEYBOARD_KEY_%s}="enter"' % ok, rule)
        self.assertIn('ENV{KEYBOARD_KEY_%s}="compose"' % menu, rule)
        self.assertGreater(rule.index('IMPORT{builtin}="keyboard"'), rule.rindex('ENV{KEYBOARD_KEY_'))    # udev runs an IMPORT before the assignments of its own line

    def test_the_launcher_opens_when_the_box_has_started(self):
        self.launcher_d()
        os.remove(self.booted)                           # the first start after a boot
        calls = self.grabs()
        self.run_once()
        self.assertTrue(self.osds.lines[0].startswith("launcher 0;HDMI 1080p60;"), self.osds.lines)    # HDMI input is the chosen one
        self.assertEqual(sorted(c for c in calls if c[1]), [("event0", True), ("event1", True)])         # no Home was pressed: held at once
        self.assertTrue(os.path.exists(self.booted))     # once per boot
        del self.osds.lines[:]
        self.press("mute")
        self.run_once()                                  # a restart of the service, a standby: not again
        self.assertEqual([x for x in self.osds.lines if x.startswith("launcher")], [])

    def test_on_start_hdmi_opens_nothing(self):
        self.launcher_d()
        os.remove(self.booted)
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("on_start = hdmi\n")
        self.press("mute")
        self.run_once()
        self.assertEqual([x for x in self.osds.lines if x.startswith("launcher")], [])
        self.assertTrue(os.path.exists(self.booted))

    def test_a_bad_on_start_is_the_default(self):
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("on_start = android\n")
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        self.assertEqual(self.mod.Config().values["on_start"], "launcher")
        self.assertIn("keys.conf:1: 'on_start = android' ignored", out)

    def start_state(self, until=100, slept=0):
        now = time.monotonic()
        return {"until": now + until, "next": 0.0, "slept": time.clock_gettime(time.CLOCK_BOOTTIME) - now - slept}

    def test_a_start_without_a_picture_tries_again_and_gives_up(self):
        self.launcher_d()
        self.osds.answer = lambda line: "ok unseen\n"   # no signal: nothing to show it on
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        conf, launcher, boot = self.mod.Config(), self.mod.Launcher(), self.start_state()
        self.assertFalse(self.mod.boot_launcher(launcher, {}, conf, boot))
        n = len(self.osds.lines)
        self.assertEqual((launcher.entries, out), (None, []))        # no launcher, and not a word in the journal
        self.assertFalse(self.mod.boot_launcher(launcher, {}, conf, boot))
        self.assertEqual(len(self.osds.lines), n)                    # the next try is BOOT_RETRY_S away
        self.osds.answer = lambda line: "ok\n"
        boot["next"] = 0.0
        self.assertTrue(self.mod.boot_launcher(launcher, {}, conf, boot))
        self.assertIsNotNone(launcher.entries)
        self.assertEqual(launcher.last, float("inf"))                # it waits for the first key
        late = self.mod.Launcher()
        self.assertTrue(self.mod.boot_launcher(late, {}, conf, self.start_state(until=-1)))
        self.assertIsNone(late.entries)
        self.assertIn("start: no launcher within 180 s - h713-osd has no picture to show it on, or there are no entries", out)

    def test_the_start_waits_for_h713_tv_not_for_a_period(self):
        self.launcher_d()
        conf, launcher, boot = self.mod.Config(), self.mod.Launcher(), self.start_state()
        tv, self.mod.TV_SOCK = self.mod.TV_SOCK, os.path.join(self.root, "no-tv.sock")
        try:
            self.assertFalse(self.mod.boot_launcher(launcher, {}, conf, boot))      # h713-tv not up: h713-osd is not asked
            self.assertEqual(self.osds.lines, [])
        finally:
            self.mod.TV_SOCK = tv
        self.assertLessEqual(boot["next"] - time.monotonic(), self.mod.BOOT_RETRY_S)
        boot["next"] = 0.0                                                       # BOOT_RETRY_S later, h713-tv is there
        self.assertTrue(self.mod.boot_launcher(launcher, {}, conf, boot))
        self.assertIsNotNone(launcher.entries)
        self.assertLessEqual(self.mod.BOOT_RETRY_S, 1)                           # not the 5 s that let HDMI show first

    def test_a_standby_in_between_ends_it(self):
        self.launcher_d()
        launcher = self.mod.Launcher()
        self.assertTrue(self.mod.boot_launcher(launcher, {}, self.mod.Config(), self.start_state(slept=30)))   # 30 s of sleep since the start
        self.assertEqual((launcher.entries, self.osds.lines), (None, []))                 # the mode from before stays

    def test_a_launcher_that_waits_for_a_key_does_not_time_out(self):
        self.launcher_d()
        conf, launcher = self.mod.Config(), self.mod.Launcher()
        self.mod.boot_launcher(launcher, {}, conf, self.start_state())
        self.mod.LAUNCHER_IDLE_S = 0
        launcher.tick({})
        self.assertIsNotNone(launcher.entries)                       # a launcher opened by Home would be closed now
        launcher.key(103, 1, {})                                      # the first key: the idle limit counts from here
        time.sleep(0.01)
        launcher.tick({})
        self.assertIsNone(launcher.entries)

    def script(self, name, rc=0):
        """an executable whose exit status is the number in <name>.rc: a stand-in for an entry's `active` and `wait` commands"""
        path = os.path.join(self.root, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\nexit $(cat %s.rc)\n" % path)
        os.chmod(path, 0o755)
        self.set_rc(name, rc)
        return path

    def set_rc(self, name, rc):
        with open(os.path.join(self.root, name + ".rc"), "w") as f:
            f.write(str(rc))

    def waiting_launcher(self):
        """HDMI input and a Browser entry that waits for its first picture; the launcher open, Browser chosen"""
        act, ready = self.script("active", 1), self.script("ready", 1)
        self.launcher_d(**{
            "10-hdmi": "label = HDMI input\nicon = hdmi\nexec = %s/mode hdmi\nnow = HDMI {signal}\nfallback = yes\n" % self.root,
            "25-browser": "label = Browser\nicon = globe\nunit = h713-browser.service\nactive = %s\nwait = %s\n" % (act, ready)})
        launcher = self.mod.Launcher()
        launcher.open({})
        launcher.key(108, 1, {})
        return launcher

    def test_an_entry_with_wait_keeps_the_page_until_its_first_picture(self):
        launcher = self.waiting_launcher()
        self.assertTrue(launcher.key(352, 1, {}))
        self.assertEqual(self.osds.lines[-1], "launcher 1;Starting Browser...;hdmi:HDMI input;globe:Browser")   # the header says what is going on
        time.sleep(0.2)                                              # (systemctl is started, not waited for)
        self.assertIn("start --no-block h713-browser.service", self.systemctl_calls())
        self.assertIsNotNone(launcher.entries)                       # the page stays: nothing but the ground until Firefox has a window
        self.assertTrue(launcher.key(352, 1, {}))                    # a second OK and a move are swallowed ...
        self.assertTrue(launcher.key(108, 1, {}))
        time.sleep(0.2)
        self.assertEqual(self.systemctl_calls().count("start --no-block h713-browser.service"), 1)
        self.assertFalse(launcher.key(115, 1, {}))                   # ... the volume is still the normal one's
        launcher.starting["next"] = 0.0
        launcher.tick({})                                            # the unit is not up (active: 1)
        self.set_rc("active", 0)
        launcher.starting["next"] = 0.0
        launcher.tick({})                                            # up, but the wait command says no picture yet
        self.assertIsNotNone(launcher.entries)
        self.set_rc("ready", 0)
        launcher.starting["next"] = 0.0
        launcher.tick({})
        self.assertIsNone(launcher.entries)                          # the picture is there: the page goes, the client shows
        self.assertEqual(self.osds.lines[-1], "launcher close")

    def test_an_entry_that_shows_nothing_is_let_go_after_the_wait(self):
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        launcher = self.waiting_launcher()
        launcher.key(352, 1, {})
        launcher.starting["next"], launcher.starting["until"] = 0.0, 0.0
        launcher.tick({})
        self.assertIsNone(launcher.entries)
        self.assertIn("launcher: Browser shows nothing after 30 s", out)
        time.sleep(0.2)                                              # (systemctl is started, not waited for: it must be done before the directory goes)

    def test_back_closes_a_starting_page_and_an_entry_without_wait_closes_at_once(self):
        launcher = self.waiting_launcher()
        launcher.key(352, 1, {})
        self.assertTrue(launcher.key(158, 1, {}))
        self.assertEqual((launcher.entries, launcher.starting), (None, None))     # the unit goes on starting; only the page is gone
        launcher = self.mod.Launcher()
        launcher.open({})
        launcher.key(352, 1, {})                                                  # HDMI input: no wait
        self.assertIsNone(launcher.entries)

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
        self.keys("home", "back", "home", "home")
        self.run_once()
        self.assertEqual([l.split(";")[0] for l in self.osds.lines], ["launcher 0", "launcher close", "launcher 0", "launcher close"])
        self.assertEqual([c for c in self.systemctl_calls() if c.startswith("start")], [])

    def test_the_launcher_leaves_volume_alone(self):
        """volume, mute and focus work with the launcher open; Left, Menu, the other keys are nobody's"""
        self.launcher_d()
        self.grabs()
        self.keys("home", "up", "left")
        self.run_once()
        self.assertEqual(self.tv.volume, 55)
        self.assertIn("volume 55", self.osds.lines)
        self.assertEqual(self.osds.lines.count("launcher close"), 0)

    def test_power_closes_the_launcher_and_goes_on_to_h713_power(self):
        self.launcher_d()
        calls = self.grabs()
        self.keys("home", "power")
        self.run_once()
        self.assertEqual(self.osds.lines[-1], "launcher close")
        self.assertTrue(all(not c[1] for c in calls[-2:]))
        self.assertEqual(self.power.recv(64), b"down")

    def test_no_picture_no_launcher_and_no_grab(self):
        self.launcher_d()
        self.osds.answer = lambda line: "ok unseen\n"
        calls = self.grabs()
        self.keys("home", "nav_down")
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
        self.keys("home")
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
        self.keys("home", "nav_down", "ok")
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
        self.assertIsNotNone(l.entries)
        l.tick({"event1": fd})
        self.assertIsNotNone(l.entries)
        l.last -= self.mod.LAUNCHER_IDLE_S + 1
        l.tick({"event1": fd})
        self.assertIsNone(l.entries)
        self.assertEqual(self.osds.lines[-1], "launcher close")
        self.assertEqual(grabbed[-1][1], False)
        os.close(fd)

    def test_home_without_entries_does_nothing(self):
        calls = self.grabs()
        self.press("home")
        self.run_once()
        self.assertEqual((calls, self.osds.lines), ([], []))


    # --- the ways back (17.10.2026) -------------------------------------------------------------------------

    def settings_launcher(self, rc=0):
        """HDMI input and a Settings entry that runs a stand-in program and `return = launcher`s; the launcher open, Settings chosen"""
        prog = self.script("settings-run", rc)
        self.launcher_d(**{
            "10-hdmi": "label = HDMI input\nicon = hdmi\nexec = %s/mode hdmi\nnow = HDMI {signal}\nfallback = yes\n" % self.root,
            "50-settings": "label = Settings\nicon = sliders\nexec = %s\nreturn = launcher\n" % prog})
        launcher = self.mod.Launcher()
        launcher.open({})
        launcher.key(108, 1, {})
        return launcher

    def ended(self, launcher):
        """the stand-in program ends; one tick of the launcher sees it"""
        launcher.back["proc"].wait(timeout=5)
        launcher.tick({})

    def test_an_entry_has_an_id_and_return_only_on_exec(self):
        self.launcher_d(**{"20-kodi": "label = Kodi\nicon = film\nunit = h713-kodi.service\nreturn = launcher\n",
                           "50-settings": "label = Settings\nicon = sliders\nexec = /x/y\nreturn = launcher\n",
                           "60-other": "label = Other\nicon = sliders\nexec = /x/y\nreturn = home\n"})
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        entries = {e["id"]: e for e in self.mod.launcher_entries()}
        self.assertEqual(sorted(entries), ["kodi", "other", "settings"])       # "20-kodi.conf" is "kodi"
        self.assertNotIn("return", entries["kodi"])                            # a unit has the mode watch, not a way back
        self.assertEqual(entries["settings"]["return"], "launcher")
        self.assertNotIn("return", entries["other"])
        self.assertEqual(len([m for m in out if "ignored" in m]), 2)

    def test_back_in_settings_opens_the_launcher_again_with_settings_chosen(self):
        launcher = self.settings_launcher(rc=0)
        self.assertTrue(launcher.key(352, 1, {}))                              # OK on Settings: the launcher lets go, the page starts
        self.assertIsNone(launcher.entries)
        self.assertEqual(self.osds.lines[-1], "launcher close keep")           # a page follows: h713-osd hands the wall over to it
        self.ended(launcher)                                                   # Back at the top: exit 0
        launcher.tick({})
        self.assertIsNotNone(launcher.entries)
        self.assertEqual((launcher.sel, launcher.entries[launcher.sel]["label"]), (1, "Settings"))     # the way back is the way that was come
        self.assertEqual(self.osds.lines[-1], "launcher 1;HDMI 1080p60;hdmi:HDMI input;sliders:Settings")  # the header says what runs, not what is chosen

    def test_ok_on_an_entry_that_is_no_page_closes_the_launcher_plainly(self):
        """only an `exec` entry with `return = launcher` (a page) keeps the launcher for its successor; HDMI input closes it at once"""
        launcher = self.settings_launcher(rc=0)
        launcher.key(103, 1, {})                                               # up: HDMI input
        self.assertTrue(launcher.key(352, 1, {}))
        self.assertEqual(self.osds.lines[-1], "launcher close")

    def test_home_power_idle_and_a_crash_in_settings_open_no_launcher(self):
        for rc in (10, 11, 12, 13, 14, 15, 1, 127):
            del self.osds.lines[:]
            launcher = self.settings_launcher(rc=rc)
            launcher.key(352, 1, {})
            self.ended(launcher)
            launcher.tick({})
            self.assertIsNone(launcher.entries, rc)
            self.assertIsNone(launcher.reopen, rc)
            self.assertEqual([l for l in self.osds.lines if l.startswith("launcher ") and ";" in l][1:], [], rc)   # only the opening of the first round

    def test_the_launcher_comes_back_when_h713_osd_has_seen_the_page_go(self):
        """h713-osd answers "error the page is open" until it has seen the page's connection end: tried again, 0.1 s apart"""
        launcher = self.settings_launcher()
        answers = ["error the page is open\n", "error the page is open\n"]
        self.osds.answer = lambda line: answers.pop(0) if answers and ";" in line else "ok\n"
        launcher.key(352, 1, {})
        self.ended(launcher)
        for _ in range(5):
            time.sleep(0.12)
            launcher.tick({})
        self.assertIsNotNone(launcher.entries)
        self.assertIsNone(launcher.reopen)

    def test_the_launcher_does_not_come_back_without_a_page_to_show_it_on(self):
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        launcher = self.settings_launcher()
        self.osds.answer = lambda line: "ok unseen\n" if ";" in line else "ok\n"
        launcher.key(352, 1, {})
        self.ended(launcher)
        launcher.reopen["until"], launcher.reopen["next"] = 0.0, 0.0
        launcher.tick({})
        self.assertIsNone(launcher.entries)
        self.assertIsNone(launcher.reopen)
        self.assertIn("launcher: not opened again - h713-osd has no page to show it on", out)

    def test_a_way_back_that_finds_the_launcher_open_does_nothing(self):
        launcher = self.settings_launcher()
        launcher.key(352, 1, {})
        launcher.back["proc"].wait(timeout=5)
        launcher.tick({})                                                      # the reopen is due ...
        launcher.close({})
        launcher.open({})                                                      # ... but a Home came first
        launcher.reopen = {"select": "settings", "until": time.monotonic() + 5, "next": 0.0}
        n = len(self.osds.lines)
        launcher.tick({})
        self.assertEqual((launcher.reopen, len(self.osds.lines)), (None, n))

    def test_the_way_back_asks_nothing_again_it_draws(self):
        """the wall shows the HDMI picture from the page's end to the launcher's drawing: the full open (3 x systemctl is-active, h713-tv's
        status) took 350 ms of it on the HY310 - the way back uses what the last full open found"""
        launcher = self.settings_launcher()                                    # the full open
        asks, tvs = len([c for c in self.systemctl_calls() if c.startswith("is-active")]), len(self.tvs.lines)
        self.assertGreater(tvs, 0)                                             # the full open asked h713-tv for the signal
        launcher.key(352, 1, {})
        self.ended(launcher)
        launcher.tick({})
        self.assertIsNotNone(launcher.entries)
        self.assertEqual(len([c for c in self.systemctl_calls() if c.startswith("is-active")]), asks)
        self.assertEqual(len(self.tvs.lines), tvs)
        self.assertEqual(self.osds.lines[-1], "launcher 1;HDMI 1080p60;hdmi:HDMI input;sliders:Settings")

    def test_a_mode_that_changed_behind_the_page_is_looked_at_again(self):
        """Kodi ends behind Settings: the header of the launcher that comes back says what runs now, so that one is a full open"""
        launcher = self.settings_launcher()
        launcher.snap["act"] = 1                                               # what the last open found: something ran
        launcher.key(352, 1, {})
        self.mod.MODE_GONE_S = 0
        modes = self.mod.Modes()
        modes.mode = "h713-kodi.service"
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.assertIsNone(launcher.snap)
        self.assertIsNone(launcher.reopen)                                     # a page is up: no attempt now (each would be a full open), its Back opens the launcher
        self.ended(launcher)
        launcher.tick({})
        self.assertEqual(self.osds.lines[-1], "launcher 1;HDMI 1080p60;hdmi:HDMI input;sliders:Settings")

    def test_the_program_that_must_end_wakes_the_loop_at_once(self):
        launcher = self.settings_launcher()
        launcher.key(352, 1, {})
        fd = launcher.back["fd"]
        self.assertIsNotNone(fd)                                               # a pidfd: readable when the program has ended
        launcher.back["proc"].wait(timeout=5)
        self.assertEqual(select.select([fd], [], [], 1)[0], [fd])
        launcher.tick({})
        self.assertIsNone(launcher.back)
        with self.assertRaises(OSError):
            os.fstat(fd)                                                       # and closed again

    def test_an_entry_that_ends_while_it_starts_does_not_keep_its_page_for_30_seconds(self):
        launcher = self.waiting_launcher()
        self.cgroup("h713-browser.service")
        self.mod.MODE_GONE_S = 0
        modes = self.mod.Modes()
        modes.tick(launcher, {})
        launcher.key(352, 1, {})
        self.assertEqual(self.osds.lines[-1], "launcher 1;Starting Browser...;hdmi:HDMI input;globe:Browser")
        launcher.started = float("-inf")                                       # (the quiet seconds after a start are over)
        self.cgroup("h713-browser.service", False)                             # Firefox died before its first window
        modes.tick(launcher, {})
        self.assertIsNone(launcher.starting)
        self.assertEqual((launcher.entries is not None, launcher.sel), (True, 0))      # the list again, HDMI input chosen
        self.assertEqual(self.osds.lines[-1], "launcher 0;HDMI 1080p60;hdmi:HDMI input;globe:Browser")
        time.sleep(0.2)                                                        # (systemctl is started, not waited for)

    # --- a mode that ends by itself (cgroup of the unit = it is up) ------------------------------------------

    def cgroup(self, unit, up=True):
        d = os.path.join(self.root, "sys/fs/cgroup/system.slice", unit)
        if up:
            os.makedirs(d, exist_ok=True)
        elif os.path.isdir(d):
            os.rmdir(d)

    def last_mode(self):
        try:
            with open(os.path.join(self.root, "var/lib/h713-keys/last-mode")) as f:
                return f.read().strip()
        except OSError:
            return None

    def watch(self):
        """the default entries (HDMI input, Kodi, Standby), Kodi up, one look: the mode is Kodi"""
        self.launcher_d()
        self.cgroup("h713-kodi.service")
        self.mod.MODE_GONE_S = 0
        launcher, modes = self.mod.Launcher(), self.mod.Modes()
        modes.tick(launcher, {})
        self.assertEqual((modes.mode, self.last_mode()), ("h713-kodi.service", "h713-kodi.service"))
        return launcher, modes

    def test_a_mode_that_ends_by_itself_opens_the_launcher_with_hdmi_input_chosen(self):
        """Kodi's Exit, the browser or the terminal closed, a crash: whoever ends a program has the remote in hand and chooses (Marco)"""
        out = []
        self.mod.log = lambda msg, level="": out.append(msg)
        launcher, modes = self.watch()
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.assertIn("mode h713-kodi.service ended by itself: the launcher opens, HDMI input chosen", out)
        launcher.tick({})
        self.assertIsNotNone(launcher.entries)
        self.assertEqual(launcher.entries[launcher.sel]["label"], "HDMI input")
        self.assertEqual(self.osds.lines[-1], "launcher 0;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby")
        self.assertEqual(self.last_mode(), "hdmi")                              # the box is on HDMI now
        modes.tick(launcher, {})
        self.assertEqual(len([l for l in self.osds.lines if ";" in l]), 1)      # once

    def test_a_gap_shorter_than_a_moment_is_a_switch_not_an_end(self):
        launcher, modes = self.watch()
        self.mod.MODE_GONE_S = 60
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.cgroup("h713-kodi.service")                                        # a restart of the unit: back at once
        modes.tick(launcher, {})
        self.assertEqual((modes.mode, modes.gone, launcher.reopen), ("h713-kodi.service", None, None))

    def test_the_end_a_launcher_start_brings_is_not_judged(self):
        launcher, modes = self.watch()
        launcher.started = time.monotonic()                                     # the launcher has just started the next mode
        self.cgroup("h713-kodi.service", False)                                 # the old one is down, the new one not up yet
        modes.tick(launcher, {})
        self.assertEqual((modes.mode, launcher.reopen), ("h713-kodi.service", None))
        self.cgroup("h713-desktop.service")
        modes.units.append("h713-desktop.service")
        modes.tick(launcher, {})
        self.assertEqual((modes.mode, self.last_mode(), launcher.reopen), ("h713-desktop.service", "h713-desktop.service", None))

    def test_h713_mode_hdmi_is_the_users_end_and_opens_no_launcher(self):
        launcher, modes = self.watch()
        open(os.path.join(self.root, "run/h713-mode.ended"), "w").close()       # h713-mode hdmi touches it before it ends the modes
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.assertEqual((modes.mode, launcher.reopen, self.last_mode()), ("hdmi", None, "hdmi"))

    def test_a_stale_mark_of_h713_mode_does_not_hide_a_crash(self):
        launcher, modes = self.watch()
        mark = os.path.join(self.root, "run/h713-mode.ended")
        open(mark, "w").close()
        os.utime(mark, (time.time() - 600, time.time() - 600))                  # ten minutes ago
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.assertEqual(launcher.reopen["select"], self.mod.FALLBACK)

    def test_a_sleep_ends_the_mode_and_the_mode_is_remembered_through_it(self):
        launcher, modes = self.watch()
        open(os.path.join(self.root, "run/h713-mode.resume"), "w").write("h713-kodi.service\n")    # h713-mode sleep-pre
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.assertEqual((launcher.reopen, self.last_mode()), (None, "h713-kodi.service"))      # not "hdmi": the sleep brings Kodi back

    def test_the_shutdown_ends_the_mode_and_last_mode_stays(self):
        """the mode that ran when the box went off is the one `last` brings back (the units end because of the shutdown, not the user)"""
        launcher, modes = self.watch()
        with open(os.path.join(self.root, "systemctl.state"), "w") as f:
            f.write("stopping\n")
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        self.assertEqual((launcher.reopen, self.last_mode()), (None, "h713-kodi.service"))
        self.assertIn("is-system-running", self.systemctl_calls())

    def test_a_mode_that_ends_behind_an_open_launcher_opens_no_second_one(self):
        launcher, modes = self.watch()
        launcher.open({})
        n = len(self.osds.lines)
        self.cgroup("h713-kodi.service", False)
        modes.tick(launcher, {})
        launcher.tick({})
        self.assertEqual((launcher.reopen, len(self.osds.lines)), (None, n))
        self.assertEqual(self.last_mode(), "hdmi")

    def test_last_mode_says_hdmi_where_nothing_runs_and_is_not_written_twice(self):
        self.launcher_d()
        self.mod.MODE_GONE_S = 0
        launcher, modes = self.mod.Launcher(), self.mod.Modes()
        modes.tick(launcher, {})
        self.assertEqual(self.last_mode(), "hdmi")
        stamp = os.stat(os.path.join(self.root, "var/lib/h713-keys/last-mode")).st_mtime_ns
        modes.tick(launcher, {})
        self.assertEqual(os.stat(os.path.join(self.root, "var/lib/h713-keys/last-mode")).st_mtime_ns, stamp)

    def test_the_mode_watch_costs_no_process(self):
        launcher, modes = self.watch()
        before = self.systemctl_calls()
        for _ in range(20):
            modes.tick(launcher, {})
        self.assertEqual(self.systemctl_calls(), before)                        # a stat of the unit's cgroup, nothing is started

    def test_the_watch_waits_for_the_start_to_be_settled(self):
        """last-mode must still say what ran when the box went off while the start (on_start = last) is under way"""
        self.launcher_d()
        self.grabs()
        os.makedirs(os.path.join(self.root, "var/lib/h713-keys"))
        with open(os.path.join(self.root, "var/lib/h713-keys/last-mode"), "w") as f:
            f.write("h713-kodi.service\n")
        os.remove(self.booted)
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("on_start = last\n")
        self.press("mute")
        self.run_once()                                                        # the start: Kodi is started, nothing runs yet
        self.assertEqual(self.last_mode(), "h713-kodi.service")

    # --- on_start: launcher, hdmi, an entry, last ------------------------------------------------------------

    def test_on_start_names_launcher_hdmi_last_or_an_entry_with_a_unit(self):
        self.launcher_d()
        for value, kept in (("launcher", "launcher"), ("hdmi", "hdmi"), ("last", "last"), ("kodi", "kodi"),
                            ("standby", "launcher"), ("android", "launcher")):     # an entry without a unit is no mode; unknown: the default
            with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
                f.write("on_start = %s\n" % value)
            self.mod.log = lambda msg, level="": None
            self.assertEqual(self.mod.Config().values["on_start"], kept, value)

    def boot_with(self, on_start, last_mode=None, entries=None):
        self.launcher_d(**(entries or {}))
        if last_mode:
            os.makedirs(os.path.join(self.root, "var/lib/h713-keys"), exist_ok=True)
            with open(os.path.join(self.root, "var/lib/h713-keys/last-mode"), "w") as f:
                f.write(last_mode + "\n")
        with open(os.path.join(self.root, "etc/h713/keys.conf"), "w") as f:
            f.write("on_start = %s\n" % on_start)
        launcher = self.mod.Launcher()
        done = self.mod.boot_launcher(launcher, {}, self.mod.Config(), self.start_state())
        time.sleep(0.2)                                                         # (systemctl is started, not waited for)
        return launcher, done

    def test_on_start_kodi_starts_kodi_straight_away(self):
        launcher, done = self.boot_with("kodi")
        self.assertTrue(done)
        self.assertEqual(self.osds.lines, ["launcher 1;HDMI 1080p60;hdmi:HDMI input;film:Kodi;>power:Standby", "launcher 1", "launcher close"])
        self.assertEqual([c for c in self.systemctl_calls() if c.startswith("start")], ["start --no-block h713-kodi.service"])
        self.assertIsNone(launcher.entries)                                     # an entry without `wait`: the page goes at the OK

    def test_on_start_with_an_entry_that_waits_keeps_the_page_until_its_first_picture(self):
        act, ready = self.script("active", 1), self.script("ready", 1)
        entries = {"10-hdmi": "label = HDMI input\nicon = hdmi\nexec = %s/mode hdmi\nnow = HDMI {signal}\nfallback = yes\n" % self.root,
                   "25-browser": "label = Browser\nicon = globe\nunit = h713-browser.service\nactive = %s\nwait = %s\n" % (act, ready)}
        launcher, done = self.boot_with("browser", entries=entries)
        self.assertTrue(done)
        self.assertEqual(self.osds.lines[-1], "launcher 1;Starting Browser...;hdmi:HDMI input;globe:Browser")
        self.assertIsNotNone(launcher.starting)                                 # "Starting Browser..." until the first picture, then it goes
        self.assertEqual(launcher.entries[launcher.sel]["id"], "browser")

    def test_on_start_last_brings_back_what_ran(self):
        launcher, done = self.boot_with("last", last_mode="h713-kodi.service")
        self.assertTrue(done)
        self.assertEqual([c for c in self.systemctl_calls() if c.startswith("start")], ["start --no-block h713-kodi.service"])

    def test_on_start_last_after_hdmi_is_hdmi(self):
        launcher, done = self.boot_with("last", last_mode="hdmi")
        self.assertTrue(done)
        self.assertEqual((self.osds.lines, launcher.entries), ([], None))      # nothing: the HDMI picture comes by itself

    def test_on_start_last_without_a_memory_or_with_a_gone_entry_is_the_launcher(self):
        launcher, done = self.boot_with("last")
        self.assertTrue(done)
        self.assertEqual(self.osds.lines[0].split(";")[0], "launcher 0")
        self.assertEqual(launcher.last, float("inf"))                           # it waits for the first key, as the start launcher does
        del self.osds.lines[:]
        launcher, done = self.boot_with("last", last_mode="h713-gone.service")
        self.assertEqual(self.osds.lines[0].split(";")[0], "launcher 0")

    def test_on_start_kodi_without_a_picture_waits_like_the_launcher(self):
        self.osds.answer = lambda line: "ok unseen\n"
        launcher, done = self.boot_with("kodi")
        self.assertFalse(done)                                                  # tried again every BOOT_RETRY_S
        self.assertEqual([c for c in self.systemctl_calls() if c.startswith("start")], [])   # nothing is started blind


if __name__ == "__main__":
    unittest.main()
