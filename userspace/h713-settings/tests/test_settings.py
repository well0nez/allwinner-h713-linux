"""Host tests for h713-settings: a fake h713-tv and a fake h713-warp on Unix sockets (their answers copied from the real
daemons' source: "ok ..." / "error ...", one line in, one answer, hang up), stand-in tools in a directory, and a
temporary /etc/h713. The program runs with --test: keys as lines on stdin, "dump" prints the model, "snap FILE" the
canvas. What a row sends to a tool is read from the fakes' logs; what it keeps for the next boot, from the files.

python3 -m unittest discover -s tests -v   (from userspace/h713-settings, after `make host OSD=...`)
"""

import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "h713-settings")
FONTS = [os.environ.get("H713_TEST_FONT", ""), "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
PRESETS = {  # name: (brightness, contrast, saturation, hue, sharpness) - h713-tv's compiled-in table
    "standard": (50, 50, 50, 50, 50), "cinema": (50, 45, 45, 50, 40), "vivid": (50, 55, 60, 50, 60),
    "game": (50, 50, 50, 50, 50), "computer": (50, 50, 50, 50, 0)}


class Ctl(threading.Thread):
    """One line in, one answer, hang up - as h713-tv and h713-warp do."""

    def __init__(self, path):
        super().__init__(daemon=True)
        self.path, self.log = path, []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(8)
        self.start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            with c:
                line = c.recv(256).decode().strip()
                self.log.append(line)
                c.sendall(self.answer(line).encode())

    def stop(self):
        self.sock.close()


class FakeTv(Ctl):
    def __init__(self, path, root):
        self.root = root
        self.c = dict(zip(("brightness", "contrast", "saturation", "hue", "sharpness"), PRESETS["standard"]))
        self.preset, self.aspect, self.volume, self.mute, self.source = "standard", "auto", 90, False, "hdmi"
        self.saved, self.refuse_43 = 0, False
        self.nosignal = False                          # the page "No signal on HDMI" is on the wall (h713-tv's status line)
        self.wb = [512] * 6                            # the firmware's white balance: R G B gain, R G B offset
        self.sliders = (0, 0)                          # what h713-tv says the sliders stand at (it owns the mapping, color.c)
        self.cm = {}                                   # (axis, "hue"|"sat"|"value") -> step; 0 = not there
        self.fw_color = True                           # False: "not available" (another firmware)
        self.curves = False                            # True: h713-tv has the board's gamma curves (ctl get/set gamma, colour_temperature)
        self.gamma_level, self.ctemp, self.missing = 3, "auto", set()   # level 0..4; auto|normal|cool|warm; the temperatures this board has no curve for
        self.refuse = set()                            # "gamma" / "colour_temperature": the CRTC refuses a new curve for it
        self.saved_look = None                         # (gamma level, colour temperature) as of the last save
        super().__init__(path)

    GAMMA_NAMES = ("1.8", "2.0", "2.1", "2.2", "2.4")
    TEMP_OF_MODE = {"cinema": "warm", "hdr": "warm", "vivid": "cool"}      # what auto comes to (h713-tv: from the device data)

    def temp_text(self):
        want = self.ctemp if self.ctemp != "auto" else self.TEMP_OF_MODE.get(self.preset, "normal")
        got = "normal" if want in self.missing else want
        if self.ctemp == "auto":
            return "auto (%s)" % got
        return self.ctemp if got == self.ctemp else "%s (%s: this board has no %s curve)" % (self.ctemp, got, self.ctemp)

    def look_answer(self, key):
        if key == "gamma":
            return "ok gamma = %d (%s)\n" % (self.gamma_level, self.GAMMA_NAMES[self.gamma_level])
        return "ok colour_temperature = %s\n" % self.temp_text()

    def look(self, w):
        """ctl get|set gamma|colour_temperature, answered the way h713-tv's gamma.c does (the answer to a set is the answer to a get)"""
        key = w[1]
        if not self.curves:
            return "error %s is not available: the board's curves were not read\n" % key
        if w[0] == "set":
            if len(w) != 3:
                return "error set needs a name and a value\n"
            if key == "gamma":
                if w[2] in self.GAMMA_NAMES:
                    level = self.GAMMA_NAMES.index(w[2])
                elif w[2].isdigit() and int(w[2]) < 5:
                    level = int(w[2])
                else:
                    return 'error gamma does not know "%s" - possible: 0..4 or 1.8 2.0 2.1 2.2 2.4\n' % w[2]
                if "gamma" in self.refuse:
                    return "error gamma = %s: the CRTC refused the curve\n" % w[2]
                self.gamma_level = level
            else:
                if w[2] not in ("auto", "normal", "cool", "warm"):
                    return 'error colour_temperature does not know "%s" - possible: auto normal cool warm\n' % w[2]
                if "colour_temperature" in self.refuse:
                    return "error colour_temperature = %s: the CRTC refused the curve\n" % w[2]
                self.ctemp = w[2]
        return self.look_answer(key)

    def answer(self, line):
        w = line.split()
        if w[0] == "list":
            rows = "".join("  %-26s %d  (0..100)\n" % (k, v) for k, v in self.c.items())
            more = "  %-26s %d (%s)  menu 0..4\n  %-26s %s  menu auto|normal|cool|warm\n" % (
                "gamma", self.gamma_level, self.GAMMA_NAMES[self.gamma_level], "colour_temperature", self.temp_text()) if self.curves else ""
            return "ok controls\n" + rows + "  mode                       1 (standard)  menu 0..5\n" + more
        if w[0] in ("get", "set") and len(w) >= 2 and w[1] in ("gamma", "colour_temperature"):
            return self.look(w)
        if w[0] == "wb":
            if len(w) == 1:
                if not self.fw_color:
                    return "ok wb %s [not available: not the display firmware these addresses were read from]\n" % " ".join(map(str, self.wb))
                return "ok wb %s sliders %d %d -- R G B gain, R G B offset, then the sliders; 512 is neutral\n" % (
                    " ".join(map(str, self.wb)), self.sliders[0], self.sliders[1])
            if not self.fw_color:
                return "error wb: not the display firmware these addresses were read from\n"
            if w[1] == "reset":
                self.wb = [512] * 6
                self.sliders = (0, 0)
            elif w[1] == "sliders" and len(w) == 4:
                self.sliders = (int(w[2]), int(w[3]))
                self.wb = wb_gains(*self.sliders) + self.wb[3:]
            elif len(w) == 7 and all(x.isdigit() and 0 <= int(x) <= 1023 for x in w[1:]):
                self.wb = [int(x) for x in w[1:]]
            else:
                return "error wb needs six numbers\n"
            return "ok wb %s (registers read back, 0 ms)\n" % " ".join(map(str, self.wb))
        if w[0] == "cm":
            if not self.fw_color:
                return "error cm: not the display firmware these addresses were read from\n"
            if w[1:] == ["reset"]:
                self.cm = {}
                return "ok cm all neutral (registers read back, 0 ms)\n"
            if len(w) == 2:
                return "ok cm %s hue %d sat %d value %d\n" % (w[1], *[self.cm.get((w[1], c), 0) for c in ("hue", "sat", "value")])
            return "error cm AXIS needs hue, saturation and value\n"
        if w[0] == "set" and len(w) == 3 and w[1].startswith("cm_"):
            if not self.fw_color:
                return "error %s: not the display firmware these addresses were read from\n" % w[1]
            axis, _, comp = w[1][3:].rpartition("_")
            if comp not in ("hue", "sat", "value") or not -255 <= int(w[2]) <= 255:
                return "error %s: %s is outside -255..255\n" % (w[1], w[2])
            self.cm[(axis, comp)] = int(w[2])
            return "ok %s = %s (registers read back, 0 ms)\n" % (w[1], w[2])
        if w[0] == "set" and len(w) == 3:
            if w[1] not in self.c:
                return 'error no control "%s" (h713-tv ctl list)\n' % w[1]
            if not 0 <= int(w[2]) <= 100:
                return "error %s: %s is outside 0..100\n" % (w[1], w[2])
            self.c[w[1]] = int(w[2])
            return "ok %s = %s\n" % (w[1].capitalize(), w[2])
        if w[0] == "preset":
            if len(w) == 1 or w[1] not in PRESETS:
                return "error preset needs a name: " + " ".join(PRESETS) + "\n"
            self.preset = w[1]
            self.c = dict(zip(self.c, PRESETS[w[1]]))
            return "ok preset %s (the compiled-in table)\n" % w[1]
        if w[0] == "status":
            return ("ok status\nmode            auto\npreset          %s (from the device data)\nsaved           nothing\n" % self.preset) + (
                'nosignal        page: h713-osd shows "No signal on HDMI"\n' if self.nosignal else "nosignal        none\n")
        if w[0] == "aspect":
            if len(w) == 2 and w[1] == "4:3" and self.refuse_43:
                return "error aspect 4:3 saved, but the plane could not be switched off\n"
            if len(w) == 2:
                self.aspect = w[1]
            return "ok aspect %s (1) -- possible: auto proportional full 16:9 4:3 zoom\n" % self.aspect
        if w[0] == "volume":
            if len(w) == 2:
                self.volume = int(w[1])
            return "ok volume %d (-12.0 dB)\n" % self.volume
        if w[0] == "mute":
            if len(w) == 2:
                self.mute = w[1] == "on"
            return "ok mute %s (DSP, the codec has no switch)\n" % ("on" if self.mute else "off")
        if w[0] == "source":
            if len(w) == 2:
                self.source = w[1]
            return "ok source %s\n" % self.source
        if w[0] == "save":
            self.saved += 1
            self.saved_look = (self.gamma_level, self.ctemp)
            return "ok saved in x: preset=%s\n" % self.preset
        return "error unknown: %s\n" % w[0]


class FakeWarp(Ctl):
    KEYS = ("tl_x", "tl_y", "tr_x", "tr_y", "bl_x", "bl_y", "br_x", "br_y")

    def __init__(self, path, root):
        self.root = root
        self.v = dict.fromkeys(self.KEYS, 0)
        self.zoom, self.mode, self.pattern = 100, "front", None
        super().__init__(path)

    def write(self):
        with open(os.path.join(self.root, "warp.conf"), "w") as f:
            f.write("".join("%s = %d\n" % kv for kv in self.v.items()))

    def answer(self, line):
        w = line.split()
        if w[0] == "zoom":
            if len(w) == 2:
                self.zoom = int(w[1])
            return "ok zoom %d\n" % self.zoom
        if w[0] == "mode":
            if len(w) == 2:
                self.mode = w[1]
            return "ok mode %s\n" % self.mode
        if w[:2] == ["keystone", "nudge"]:
            k = "%s_%s" % (w[2], w[3])
            self.v[k] = max(0, min(1000, self.v[k] + int(w[4])))
            self.write()
            return "ok %s = %d\n" % (k, self.v[k])
        if w[:2] == ["keystone", "reset"]:
            self.v = dict.fromkeys(self.KEYS, 0)
            self.write()
            return "ok keystone reset\n"
        if w[:2] == ["test", "mask"]:
            self.pattern = w[2]
            return "ok test mask %s\n" % w[2]
        if w[:2] == ["test", "off"]:
            self.pattern = None
            return "ok test off\n"
        if w[0] == "on":
            return "ok on\n"
        return "error unknown: %s\n" % w[0]


class FakeOsd(threading.Thread):
    """h713-osd's page channel: "page open" answers with one memfd (the canvas) and the size, "page show X Y W H" is
    logged with the pixels of the rectangle's first pixel row summed up, the answer can be told to say "unseen"."""

    W, H = 640, 360

    def __init__(self, path, answer="ok", refuse=None):
        super().__init__(daemon=True)
        self.path, self.log, self.answer, self.refuse = path, [], answer, refuse
        self.canvas = os.memfd_create("page")
        os.ftruncate(self.canvas, self.W * self.H * 4)
        self.opened = self.closed = False
        self.conn = None
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(2)
        self.start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conn = c
            with c:
                while True:
                    data = c.recv(256)
                    if not data:
                        self.closed = True
                        break
                    line = data.decode().strip()
                    self.log.append(line)
                    if line == "page open":
                        if self.refuse:
                            c.sendall(self.refuse.encode())
                            continue
                        self.opened = True
                        socket.send_fds(c, [b"ok %d %d %d argb8888\n" % (self.W, self.H, self.W * 4)], [self.canvas])
                    elif line.startswith("page show"):
                        c.sendall(("%s\n" % self.answer).encode())

    def drop(self):
        """h713-osd goes away under the page: its end of the connection is closed."""
        self.conn.shutdown(socket.SHUT_RDWR)

    def pixel(self, x, y):
        os.lseek(self.canvas, (y * self.W + x) * 4, os.SEEK_SET)
        return struct.unpack("<I", os.read(self.canvas, 4))[0]

    def stop(self):
        self.sock.close()


TOOLS = {
    "h713-features": """echo "ok features  board hy310, FEATURES: accelerometer camera focus-motor (x)"
printf '%-16s%s\\n' camera "$CAM" accelerometer "$ACC" focus-motor "$MOTOR"
""",
    "h713-power": """echo "$@" >> "$LOG/power.log"
case "$1" in
status) echo "standby: $STANDBY" ;;
set) f="$ETC/power.conf"; if grep -q "^$2 *=" "$f"; then sed -i "s/^$2 *=.*/$2 = $3/" "$f"; else echo "$2 = $3" >> "$f"; fi ;;
esac
""",
    # keystone-turn.log: the turn_to_wall the file held when the run started (what the real tool would have used)
    "h713-keystone": 'echo "$@" >> "$LOG/keystone.log"; sed -n "s/^turn_to_wall *= *//p" "$ETC/keystone.conf" | tail -n 1 >> "$LOG/keystone-turn.log"; sleep "${JOBTIME:-0.3}"; exit "${JOBEXIT:-0}"\n',
    "h713-autofocus": 'echo "$@" >> "$LOG/autofocus.log"; sleep "${JOBTIME:-0.3}"; exit "${JOBEXIT:-0}"\n',
    "h713-focus": 'echo "$@" >> "$LOG/focus.log"; sleep 0.2\n',
    "systemctl": 'echo "$@" >> "$LOG/systemctl.log"\nif [ "$1" = is-active ]; then grep -qx "$3" "$LOG/active" 2>/dev/null; exit $?; fi\n',
    "iw": 'printf "Connected to aa:bb:cc:dd:ee:ff (on wlan0)\\n\\tSSID: Wohnzimmer\\n\\tfreq: 2437\\n\\tsignal: -52 dBm\\n"\n',
    "ip": 'echo "wlan0            UP             192.168.8.131/24"\n',
}


class Box:
    """The tools, the files and the program, in one temporary directory."""

    def __init__(self, features="all", standby="offered in the countdown", wifi_mode="sta", extra_env=None, launcher=True):
        self.dir = tempfile.mkdtemp(prefix="h713-settings-")
        self.etc = os.path.join(self.dir, "etc")
        self.bin = os.path.join(self.dir, "bin")
        self.log = os.path.join(self.dir, "log")
        for d in (self.etc, self.bin, self.log):
            os.mkdir(d)
        if launcher:
            os.mkdir(os.path.join(self.etc, "launcher.d"))            # the image has a launcher (h713-keys' entries)
        for name, body in TOOLS.items():
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n" + body)
            os.chmod(path, 0o755)
        present = "present  /dev/x  (stand-in)"
        absent = "not present on this board"
        have = lambda on: present if features in ("all", on) else absent
        self.env = dict(os.environ, H713_SETTINGS_ETC=self.etc, H713_SETTINGS_BIN=self.bin, LOG=self.log, ETC=self.etc,
                        H713_SETTINGS_COLOUR="1",                # the Colour area (left out on the board since 20.10.2026): the tests keep it
                        H713_SETTINGS_TV=os.path.join(self.dir, "tv.sock"),
                        H713_SETTINGS_WARP=os.path.join(self.dir, "warp.sock"),
                        CAM=have("camera"), ACC=have("accelerometer"), MOTOR=have("focus-motor"), STANDBY=standby)
        if features == "none":
            self.env.update(CAM=absent, ACC=absent, MOTOR=absent)
        self.env.update(extra_env or {})
        self.write("power.conf", "# power\ndefault = poweroff\nlong_s = 3\nremote = on\n")
        self.write("keystone.conf", "# keystone\niio_name = sc7a20\nafter_move = off   # the page writes this\nhysteresis_degrees = 1.0\n")
        self.write("wifi.env", "mode=%s\nssid=Wohnzimmer\npassword=geheim-und-lang\n" % wifi_mode)
        self.tv = FakeTv(self.env["H713_SETTINGS_TV"], self.etc)
        self.warp = FakeWarp(self.env["H713_SETTINGS_WARP"], self.etc)
        self.proc = None

    def write(self, name, text):
        with open(os.path.join(self.etc, name), "w") as f:
            f.write(text)

    def read(self, name):
        try:
            with open(os.path.join(self.etc, name)) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def tool_log(self, name):
        try:
            with open(os.path.join(self.log, name + ".log")) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def start(self, area=None, size="640x360"):
        args = [BIN, "--test", "--size", size]
        for font in FONTS:
            if font and os.path.exists(font):
                args += ["--font", font]
                break
        if area:
            args += ["--area", area]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=self.env, text=True, bufsize=1)
        return self

    def start_device(self, area=None, osd_answer="ok", refuse=None, idle=None, devices=2, font=True, osd_socket=None):
        """The program as the launcher starts it: no --test, the remote's devices as FIFOs, h713-osd's page channel (a fake
        of it, or the real daemon's socket)."""
        self.osd = FakeOsd(os.path.join(self.dir, "osd.sock"), osd_answer, refuse) if not osd_socket else None
        self.fifos = []
        for i in range(devices):
            path = os.path.join(self.dir, "event%d" % i)
            os.mkfifo(path)
            self.fifos.append((path, os.open(path, os.O_RDWR)))      # a writer end of our own keeps the FIFO from hanging up
        self.env.update(H713_SETTINGS_OSD=osd_socket or self.osd.path, H713_SETTINGS_POWER=os.path.join(self.dir, "power.sock"),
                        H713_SETTINGS_INPUT=",".join(p for p, _ in self.fifos))
        self.power = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.power.bind(self.env["H713_SETTINGS_POWER"])
        self.power.settimeout(3)
        args = [BIN]
        for path in FONTS if font else ():
            if path and os.path.exists(path):
                args += ["--font", path]
                break
        if area:
            args += ["--area", area]
        if idle:
            args += ["--idle", str(idle)]
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=self.env, text=True)
        return self

    def press(self, *codes, device=0, value=1):
        for code in codes:
            now = time.time()                                     # the kernel stamps an event with CLOCK_REALTIME
            os.write(self.fifos[device][1], struct.pack("llHHi", int(now), int(now % 1 * 1e6), 1, code, value))

    def keys(self, *keys):
        for k in keys:
            self.proc.stdin.write(k + "\n")
        self.proc.stdin.flush()

    def hold(self, key, n):
        """a held key: n presses that reach the program in one piece, so that it sums them into one command"""
        self.proc.stdin.write((key + "\n") * n)
        self.proc.stdin.flush()

    def dump(self):
        self.keys("dump")
        lines = []
        for line in self.proc.stdout:
            if line.strip() == "--":
                break
            lines.append(line.rstrip("\n"))
        return "\n".join(lines)

    def finish(self, sig=None):
        if sig:
            self.proc.send_signal(sig)
        else:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        err = self.proc.stderr.read()
        self.proc.stdout.close()
        self.proc.stderr.close()
        return err

    def close(self):
        for _, w in getattr(self, "fifos", []):
            os.close(w)
        if getattr(self, "osd", None):
            self.osd.stop()
        if hasattr(self, "power"):
            self.power.close()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr) if self.proc else ():
            try:
                f and f.close()
            except (OSError, ValueError):
                pass
        self.tv.stop()
        self.warp.stop()
        shutil.rmtree(self.dir, ignore_errors=True)


def wait_for(cond, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class Base(unittest.TestCase):
    def box(self, **kw):
        b = Box(**kw)
        self.addCleanup(b.close)
        return b


class Picture(Base):
    def test_rows_come_from_the_tools(self):
        b = self.box().start("Picture")
        d = b.dump()
        self.assertIn("Brightness slider 50 0..100", d)
        self.assertIn("Tint slider 50 0..100", d)
        self.assertIn("Picture mode choice [*Standard|Cinema|Vivid|Game|Computer]", d)
        self.assertIn("Aspect ratio choice [*Auto|Original|Fill|16:9|4:3]", d)    # "zoom" is refused by h713-tv: no row for it
        self.assertNotIn("Zoom|", d)
        b.finish()

    def test_a_held_key_is_one_command(self):
        b = self.box().start("Picture")
        b.keys("right", "ok", "right", "right", "right", "left")   # into the rows; three steps up, one down
        d = b.dump()
        self.assertIn("Brightness slider 60 0..100", d)
        sets = [x for x in b.tv.log if x.startswith("set ")]
        self.assertEqual(sets, ["set brightness 60"])
        b.finish()

    def test_saved_once_and_kept_for_the_start(self):
        b = self.box().start("Picture")
        b.keys("ok", "right", "right", "down", "right")
        b.dump()
        b.finish()                                    # leaving writes what was held back
        self.assertEqual(b.tv.saved, 1)
        self.assertEqual(b.tv.c["brightness"], 60)
        self.assertEqual(b.tv.c["contrast"], 55)
        self.assertIn("preset = last", b.read("tv.conf"))     # the kept values apply only for the preset kept: "last"

    def test_save_waits_for_the_hand_to_rest(self):
        b = self.box().start("Picture")
        b.keys("ok", "right")
        b.dump()
        self.assertEqual(b.tv.saved, 0)
        self.assertTrue(wait_for(lambda: b.tv.saved == 1, 4.0))
        b.finish()

    def test_preset_choice_reloads_the_sliders(self):
        b = self.box().start("Picture")
        b.keys("ok", "down", "down", "down", "down", "down", "ok", "down", "ok")   # Picture mode > Cinema
        d = b.dump()
        self.assertIn("preset cinema", b.tv.log)
        self.assertIn("Contrast slider 45", d)
        self.assertIn("Picture mode choice [Standard|*Cinema", d)
        b.finish()

    def test_aspect_choice_sends_the_tool_name(self):
        b = self.box().start("Picture")
        b.keys("ok", "down", "down", "down", "down", "down", "down", "ok", "down", "ok")    # Aspect ratio > Original
        b.dump()
        self.assertIn("aspect proportional", b.tv.log)
        b.finish()

    def test_a_refused_choice_shows_what_the_tool_holds(self):
        b = self.box()
        b.tv.refuse_43 = True
        b.start("Picture")
        b.keys("ok", *["down"] * 6, "ok", "down", "down", "down", "down", "ok")      # Aspect ratio > 4:3, which h713-tv refuses
        self.assertIn("Aspect ratio choice [*Auto|", b.dump())
        b.finish()

    def test_choice_can_be_cancelled(self):
        b = self.box().start("Picture")
        b.keys("ok", "down", "down", "down", "down", "down", "ok", "down", "back")
        self.assertIn("focus rows", b.dump())
        self.assertNotIn("preset cinema", b.tv.log)
        b.finish()

    def test_reset_picture(self):
        b = self.box().start("Picture")
        b.tv.c["brightness"] = 80
        b.keys("ok", "down", "down", "down", "down", "down", "down", "down", "ok")
        d = b.dump()
        self.assertIn("preset standard", b.tv.log)
        self.assertIn("aspect auto", b.tv.log)
        self.assertEqual(b.tv.saved, 1)
        self.assertIn("Brightness slider 50", d)
        self.assertIn('Reset picture action "Done"', d)
        b.finish()

    def test_a_missing_control_has_no_row(self):
        b = self.box()
        del b.tv.c["hue"]
        d = b.start("Picture").dump()
        self.assertIn("(hidden) Tint slider", d)
        b.finish()


def wb_gains(w, t):
    """The mapping written down once more here, independently of rows.c: the sliders only lower a gain, 0.4 % per step."""
    ks = 0.004
    kr = (1 - ks * max(w, 0)) * (1 - ks * max(-t, 0))
    kg = 1 - ks * max(t, 0)
    kb = (1 - ks * max(-w, 0)) * (1 - ks * max(-t, 0))
    return [int(512 * k + 0.5) for k in (kr, kg, kb)]


class WhiteBalance(Base):
    """18.10.2026: the firmware's white balance (h713-tv ctl wb) as two sliders for the eye, and the colour by primary
    (h713-tv ctl cm / set cm_AXIS_hue|sat). The sliders only ever lower a gain, 0.4 % per step: cool lowers red, warm blue,
    magenta green, green red and blue."""

    def test_the_area_and_its_rows(self):
        b = self.box().start("White balance")
        d = b.dump()
        self.assertIn("area White balance focus areas", d)
        self.assertIn("Warm - Cool slider 0 -50..50", d)
        self.assertIn("Green - Magenta slider 0 -50..50", d)
        self.assertIn("Reset action", d)
        self.assertIn("(hidden) White balance info", d)
        b.finish()

    def test_it_sits_under_picture(self):
        b = self.box().start("Picture")
        b.keys("down")
        self.assertIn("area White balance", b.dump())
        b.keys("down")
        self.assertIn("area Colour", b.dump())
        b.keys("down")
        self.assertIn("area Keystone", b.dump())
        b.finish()

    def test_a_step_sends_the_sliders(self):
        b = self.box().start("White balance")
        b.keys("ok", "right")                                       # Warm - Cool: one step (2) towards cool
        d = b.dump()
        self.assertIn("focus slider", d)
        self.assertIn("Warm - Cool slider 2 -50..50", d)
        self.assertEqual(b.tv.log[-1], "wb sliders 2 0")
        b.keys("down", "right", "right", "right")                   # Green - Magenta: three steps towards magenta
        b.dump()
        self.assertEqual(b.tv.log[-1], "wb sliders 2 6")
        self.assertEqual(b.tv.wb, wb_gains(2, 6) + [512] * 3)
        b.finish()

    def test_every_command_carries_two_slider_positions(self):
        b = self.box().start("White balance")
        b.keys("ok", "right", "right", "left", "down", "left", "left", "left", "up", "left")
        b.dump()
        sent = [l for l in b.tv.log if l.startswith("wb ") and l != "wb"]
        self.assertGreaterEqual(len(sent), 3)             # (a run of presses the same way is one command)
        for line in sent:
            words = line.split()
            self.assertEqual(words[:2], ["wb", "sliders"], line)
            self.assertEqual(len(words), 4, line)
            self.assertTrue(all(-50 <= int(w) <= 50 for w in words[2:]), line)
        b.finish()

    def test_the_other_end_sends_the_other_positions(self):
        b = self.box().start("White balance")
        b.keys("ok", *["left"] * 10)                                # warm
        b.dump()
        self.assertEqual(b.tv.log[-1], "wb sliders -20 0")
        b.keys("down", *["left"] * 5)                               # green
        b.dump()
        self.assertEqual(b.tv.log[-1], "wb sliders -20 -10")
        b.finish()

    def test_the_positions_are_the_ones_h713_tv_names(self):
        for w, t in ((15, 10), (0, 0), (-50, -50), (50, 50), (-50, 50), (20, -30), (-8, 0)):
            b = self.box()
            b.tv.sliders = (w, t)
            b.start("White balance")
            d = b.dump()
            self.assertIn("Warm - Cool slider %d " % w, d)
            self.assertIn("Green - Magenta slider %d " % t, d)
            b.finish()

    def test_gains_the_sliders_cannot_make_show_as_zero(self):
        b = self.box()
        b.tv.wb = [600, 512, 512, 512, 512, 512]                    # h713-tv says sliders 0 0 (other)
        b.start("White balance")
        d = b.dump()
        self.assertIn("Warm - Cool slider 0 ", d)
        self.assertIn("Green - Magenta slider 0 ", d)
        b.finish()

    def test_the_offsets_are_not_touched(self):
        b = self.box()
        b.tv.wb = [512, 512, 512, 530, 500, 512]                    # somebody set offsets with ctl set
        b.start("White balance")
        b.keys("ok", "right")
        b.dump()
        self.assertEqual(b.tv.log[-1], "wb sliders 2 0")
        self.assertEqual(b.tv.wb, [508, 512, 512, 530, 500, 512])
        b.finish()

    def test_reset(self):
        b = self.box().start("White balance")
        b.keys("ok", "right", "right", "back")                      # Warm - Cool 4, back on the page
        b.dump()
        self.assertNotEqual(b.tv.wb[:3], [512] * 3)
        b.keys("down", "down", "ok")                                # Reset (the second slider, then Reset)
        d = b.dump()
        self.assertEqual(b.tv.wb, [512] * 6)
        self.assertIn("Warm - Cool slider 0 ", d)
        self.assertIn('Reset action "Done"', d)
        self.assertEqual(b.tv.saved, 1)                             # and kept: a reset is a decision
        b.finish()

    def test_the_colour_area_is_left_out(self):
        # cm-diagnose 20.10.2026: the colour manager has no visible effect on the HY310; Marco: "Colour ausblenden"
        b = self.box(extra_env={"H713_SETTINGS_COLOUR": ""}).start("White balance")
        b.keys("down")                                              # the area after White balance
        self.assertIn("area Keystone", b.dump())
        b.keys("up", "up")
        self.assertIn("area Picture", b.dump())
        b.finish()
        b = self.box(extra_env={"H713_SETTINGS_COLOUR": ""}).start("Sound")    # the areas after it are found by their new places
        b.keys("volup")                                             # the hot key refreshes the Sound area when it is the open one
        self.assertIn("Volume slider 95", b.dump())
        b.finish()

    def test_done_goes_with_the_area(self):
        # Marco 18.10.2026: "Reset done" stayed after a change of area (Colour and Picture; White balance cleared it itself)
        b = self.box().start("Colour")
        b.keys("ok", "down", "down", "down", "ok")                  # Reset
        self.assertIn('Reset action "Done"', b.dump())
        b.keys("back", "down", "up")                                # the area list, the next area, Colour again
        d = b.dump()
        self.assertIn("Primary colour", d)
        self.assertNotIn('Reset action "Done"', d)
        b.finish()
        b.start("Picture")
        b.keys("ok", *["down"] * 7, "ok")                           # Reset picture
        self.assertIn('Reset picture action "Done"', b.dump())
        b.keys("back", "down", "up")
        d = b.dump()
        self.assertIn("Brightness slider", d)
        self.assertNotIn('Reset picture action "Done"', d)
        b.finish()

    def test_what_was_moved_is_kept_when_the_hand_rests(self):
        b = self.box().start("White balance")
        b.keys("ok", "right")
        b.dump()
        self.assertEqual(b.tv.saved, 0)
        b.finish(signal.SIGTERM)
        self.assertEqual(b.tv.saved, 1)

    def test_a_refused_command_leaves_the_slider(self):
        b = self.box()
        b.tv.fw_color = False
        b.start("White balance")
        d = b.dump()
        self.assertIn("(hidden) Warm - Cool", d)
        self.assertNotIn("(hidden) White balance info", d)           # the line that says why is the one that shows
        self.assertIn('White balance info "Not available"', d)
        b.keys("ok", "right")
        b.dump()
        self.assertEqual([l for l in b.tv.log if l.startswith("wb ")], [])     # nothing is sent
        b.finish()

    def test_no_h713_tv_no_rows_and_nothing_breaks(self):
        b = self.box()
        b.env["H713_SETTINGS_TV"] = os.path.join(b.dir, "nobody.sock")     # nobody listens there
        b.start("White balance")
        d = b.dump()
        self.assertIn("(hidden) Warm - Cool", d)
        self.assertIn('White balance info "Not available"', d)
        b.keys("down")
        self.assertIn("area Colour", b.dump())
        b.finish()


class ColourByPrimary(Base):
    def test_the_rows(self):
        b = self.box().start("Colour")
        d = b.dump()
        self.assertIn("Primary colour choice [Red|*Yellow|Green|Cyan|Blue|Purple]", d)
        self.assertIn("Hue slider 0 -100..100", d)
        self.assertIn("Saturation slider 0 -100..100", d)
        self.assertIn("Reset action", d)
        b.finish()

    def test_yellow_hue_60_is_one_command(self):
        # the wall test of 18.10.: yellow, hue 60 - the Settings reach it with twelve presses of five
        b = self.box().start("Colour")
        b.keys("ok", "down", *["right"] * 12)
        d = b.dump()
        self.assertIn("Hue slider 60 -100..100", d)
        self.assertEqual(b.tv.log[-1], "set cm_yellow_hue 60")
        self.assertEqual(b.tv.cm[("yellow", "hue")], 60)
        b.finish()

    def test_saturation_and_the_other_end(self):
        b = self.box().start("Colour")
        b.keys("ok", "down", "down", "left", "left")                # Saturation -10
        d = b.dump()
        self.assertIn("Saturation slider -10 ", d)
        self.assertEqual(b.tv.cm[("yellow", "sat")], -10)
        b.finish()

    def test_choosing_another_colour_loads_its_values(self):
        b = self.box()
        b.tv.cm[("green", "hue")] = 20
        b.tv.cm[("green", "sat")] = -35
        b.start("Colour")
        b.keys("ok", "ok", "down", "ok")                            # the options of the colour, Green, take it
        d = b.dump()
        self.assertIn("Primary colour choice [Red|Yellow|*Green|Cyan|Blue|Purple]", d)
        self.assertIn("Hue slider 20 ", d)
        self.assertIn("Saturation slider -35 ", d)
        b.keys("down", "right")
        b.dump()
        self.assertEqual(b.tv.log[-1], "set cm_green_hue 25")
        b.finish()

    def test_the_yellow_values_come_from_h713_tv(self):
        b = self.box()
        b.tv.cm[("yellow", "hue")] = 42
        b.start("Colour")
        d = b.dump()
        self.assertIn("Hue slider 42 ", d)
        b.finish()

    def test_reset_is_one_command_and_kept(self):
        b = self.box().start("Colour")
        b.keys("ok", "down", *["right"] * 4, "back")
        b.dump()
        self.assertEqual(b.tv.cm[("yellow", "hue")], 20)
        b.keys("down", "down", "ok")
        d = b.dump()
        self.assertEqual(b.tv.cm, {})
        self.assertEqual(b.tv.log[-1], "save")
        self.assertIn("Hue slider 0 ", d)
        self.assertIn('Reset action "Done"', d)
        b.finish()

    def test_not_available(self):
        b = self.box()
        b.tv.fw_color = False
        b.start("Colour")
        d = b.dump()
        self.assertIn("(hidden) Primary colour", d)
        self.assertIn('Colour info "Not available"', d)
        b.finish()

    def test_a_refused_step_leaves_the_slider(self):
        b = self.box().start("Colour")
        self.assertIn("Hue slider 0 ", b.dump())                    # (the page has read h713-tv: it is there)
        b.tv.fw_color = False                                       # and now the firmware refuses
        b.keys("ok", "down", "right")
        d = b.dump()
        self.assertIn("Hue slider 0 ", d)
        self.assertIn("set cm_yellow_hue 5", b.tv.log)              # it was asked
        b.finish()


class Gamma(Base):
    """19.10.2026: Gamma (Picture) and Colour temperature (White balance) as sliders with named stops, judged on the picture: one pill over
    the real picture. Both are h713-tv's own (ctl set gamma N, ctl set colour_temperature NAME); a row shows what h713-tv answers."""

    def box(self, **kw):
        b = super().box(**kw)
        b.tv.curves = True
        return b

    GAMMA = ["ok"] + ["down"] * 5               # Picture: Brightness Contrast Colour Tint Sharpness [Gamma] Picture mode Aspect ratio Reset picture
    RESET = ["ok"] + ["down"] * 8 + ["ok"]

    def test_gamma_stands_between_sharpness_and_the_picture_mode(self):
        d = self.box().start("Picture").dump()
        lines = [l.strip() for l in d.splitlines()]
        names = [l.split(" slider")[0].split(" choice")[0].split(" action")[0] for l in lines[1:10]]
        self.assertEqual(names, ["Brightness", "Contrast", "Colour", "Tint", "Sharpness", "Gamma", "Picture mode", "Aspect ratio", "Reset picture"])
        self.assertIn("Gamma slider 3 0..4 [1.8|2.0|2.1|*2.2|2.4]", d)
        self.assertNotIn("(hidden) Gamma", d)

    def test_a_step_is_one_command_and_the_page_is_the_pill(self):
        b = self.box().start("Picture")
        b.keys(*self.GAMMA, "right")
        d = b.dump()
        self.assertIn("focus slider row 5", d)
        self.assertIn("Gamma slider 4 0..4 [1.8|2.0|2.1|2.2|*2.4]", d)
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], ["set gamma 4"])
        self.assertEqual(b.tv.gamma_level, 4)
        b.hold("left", 2)
        self.assertIn("Gamma slider 2 0..4 [1.8|2.0|*2.1|2.2|2.4]", b.dump())
        self.assertEqual(b.tv.gamma_level, 2)
        b.finish()

    def test_ok_opens_the_pill_without_moving_it(self):
        b = self.box().start("Picture")
        b.keys(*self.GAMMA, "ok")
        d = b.dump()
        self.assertIn("focus slider row 5", d)
        self.assertIn("Gamma slider 3", d)
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], [])
        b.finish()

    def test_a_held_key_is_one_command_and_the_ends_hold(self):
        b = self.box().start("Picture")
        b.keys(*self.GAMMA)
        b.hold("right", 3)                                      # 3 -> 4 once; the press past the end is no second command
        self.assertIn("Gamma slider 4", b.dump())
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], ["set gamma 4"])
        b.hold("left", 6)                                       # 4 -> 0 in one command, then nothing more
        self.assertIn("Gamma slider 0", b.dump())
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], ["set gamma 4", "set gamma 0"])
        b.keys("left")                                          # at the end: nothing is sent
        b.dump()
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], ["set gamma 4", "set gamma 0"])
        b.finish()

    def test_gamma_is_kept_like_the_other_picture_values(self):
        b = self.box().start("Picture")
        b.keys(*self.GAMMA, "right")
        b.dump()
        self.assertEqual(b.tv.saved, 0)
        self.assertTrue(wait_for(lambda: b.tv.saved == 1, 4.0))                 # when the hand has rested, once
        self.assertEqual(b.tv.saved_look, (4, "auto"))
        b.finish()
        self.assertIn("preset = last", b.read("tv.conf"))

    def test_a_refused_curve_shows_what_the_tool_holds(self):
        b = self.box()
        b.tv.refuse.add("gamma")
        b.start("Picture")
        b.dump()                                                                 # the page has read the tool
        b.tv.gamma_level = 1                                                     # somebody else moved it since the page opened
        b.keys(*self.GAMMA, "right")                                             # 2.4 is asked for and refused: the row shows what the tool holds
        self.assertIn("Gamma slider 1 0..4 [1.8|*2.0|2.1|2.2|2.4]", b.dump())
        b.finish()
        self.assertEqual(b.tv.saved, 0)                                          # nothing changed here, so nothing is kept

    def test_the_row_reads_what_the_tool_holds(self):
        b = self.box()
        b.tv.gamma_level = 1                                                     # the tool holds 2.0 when the page opens
        b.start("Picture")
        self.assertIn("Gamma slider 1 0..4 [1.8|*2.0|2.1|2.2|2.4]", b.dump())
        b.finish()

    def test_a_board_without_the_curves_has_no_gamma_row(self):
        b = self.box()
        b.tv.curves = False
        d = b.start("Picture").dump()
        self.assertIn("(hidden) Gamma slider", d)
        b.keys("ok", *["down"] * 5)
        self.assertIn("focus rows row 5", b.dump())                              # Picture mode is the sixth visible row
        b.keys("ok", "down", "ok")                                               # and it works as before
        b.dump()
        self.assertIn("preset cinema", b.tv.log)
        b.finish()

    def test_reset_picture_brings_gamma_back_and_leaves_the_colour_temperature(self):
        b = self.box()
        b.tv.gamma_level, b.tv.ctemp = 4, "cool"
        b.start("Picture")
        b.keys(*self.RESET)
        d = b.dump()
        self.assertIn("preset standard", b.tv.log)
        self.assertEqual(b.tv.gamma_level, 3)
        self.assertEqual(b.tv.ctemp, "cool")                                     # it has its own Reset, on White balance
        self.assertIn("Gamma slider 3", d)
        self.assertEqual(b.tv.saved, 1)
        self.assertEqual(b.tv.saved_look, (3, "cool"))
        b.finish()

    def test_reset_picture_without_curves_sends_no_gamma(self):
        b = self.box()
        b.tv.curves = False
        b.start("Picture")
        b.keys("ok", *["down"] * 7, "ok")
        self.assertIn('Reset picture action "Done"', b.dump())
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], [])             # no row, nothing is sent: only the asking
        b.finish()

    # -- White balance: Colour temperature on top

    def test_colour_temperature_is_the_first_row_of_white_balance(self):
        d = self.box().start("White balance").dump()
        lines = [l.strip() for l in d.splitlines()]
        self.assertEqual([l.split(" slider")[0].split(" action")[0] for l in lines[1:5]], ["Colour temperature", "Warm - Cool", "Green - Magenta", "Reset"])
        self.assertIn("Colour temperature slider 0 0..3 [*Auto|Warm|Normal|Cool]", d)
        self.assertIn('"Auto: Normal"', d)                                       # Auto says what it comes to

    def test_auto_says_what_the_picture_mode_brings(self):
        b = self.box()
        b.tv.preset = "cinema"
        self.assertIn('"Auto: Warm"', b.start("White balance").dump())
        b.tv.preset = "vivid"
        b.keys("down", "up")                                                     # the area is read again when it is opened
        self.assertIn('"Auto: Cool"', b.dump())
        b.finish()

    def test_a_stop_is_one_command_and_a_set_one_has_no_second_word(self):
        b = self.box().start("White balance")
        b.keys("ok", "right")
        d = b.dump()
        self.assertIn("focus slider row 0", d)
        self.assertIn("Colour temperature slider 1 0..3 [Auto|*Warm|Normal|Cool]", d)
        self.assertNotIn('"Warm', d)                                             # Warm is its own: no "Auto: ..." and no second word
        b.keys("right")
        b.dump()
        b.keys("right")
        self.assertIn("slider 3 0..3 [Auto|Warm|Normal|*Cool]", b.dump())
        b.hold("left", 3)                                                        # held: all the way back, one command
        self.assertIn("Colour temperature slider 0 0..3 [*Auto|Warm|Normal|Cool] note", b.dump())
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")],
                         ["set colour_temperature warm", "set colour_temperature normal", "set colour_temperature cool", "set colour_temperature auto"])
        b.finish()

    def test_a_chosen_temperature_stays_when_the_picture_mode_changes(self):
        b = self.box().start("White balance")
        b.keys("ok")
        b.hold("right", 3)
        b.keys("back", "back")                                                   # Cool, then out to the areas
        b.dump()
        self.assertEqual(b.tv.ctemp, "cool")
        b.tv.preset = "cinema"
        b.keys("up", "down")
        d = b.dump()
        self.assertIn("slider 3 0..3 [Auto|Warm|Normal|*Cool]", d)
        self.assertNotIn('"Auto', d)
        b.finish()

    def test_a_board_without_the_curve_says_so(self):
        b = self.box()
        b.tv.missing = {"warm"}
        b.start("White balance")
        b.keys("ok", "right")
        self.assertIn('Colour temperature slider 1 0..3 [Auto|*Warm|Normal|Cool] note "', b.dump())
        self.assertIn('"Warm: Normal"', b.dump())                                # chosen: what it comes to
        b.finish()

    def test_up_and_down_go_on_to_the_fine_tuning_in_the_same_pill(self):
        b = self.box().start("White balance")
        b.keys("ok", "right", "down")
        self.assertIn("focus slider row 1", b.dump())                            # Warm - Cool, no stop between
        b.keys("down", "up", "up")
        self.assertIn("focus slider row 0", b.dump())
        b.keys("up")                                                             # no slider above: it stays
        self.assertIn("focus slider row 0", b.dump())
        b.finish()

    def test_a_refused_temperature_shows_what_the_tool_holds(self):
        b = self.box()
        b.tv.refuse.add("colour_temperature")
        b.start("White balance")
        b.dump()
        b.tv.ctemp = "normal"                                                    # somebody else set it since the page opened
        b.keys("ok", "right")                                                    # Warm is asked for and refused: the tool holds Normal
        self.assertIn("Colour temperature slider 2 0..3 [Auto|Warm|*Normal|Cool]", b.dump())
        b.finish()
        self.assertEqual(b.tv.saved, 0)                                          # nothing changed, so nothing is kept

    def test_a_temperature_is_kept_like_the_other_picture_values(self):
        b = self.box().start("White balance")
        b.keys("ok", "right", "right")
        b.dump()
        self.assertTrue(wait_for(lambda: b.tv.saved == 1, 4.0))
        self.assertEqual(b.tv.saved_look, (3, "normal"))
        b.finish()

    def test_reset_gives_the_whole_page_back_the_temperature_too(self):
        b = self.box()
        b.tv.ctemp = "cool"
        b.start("White balance")
        b.keys("ok", "down", "right", "right", "back")                           # Warm - Cool 4
        b.dump()
        self.assertNotEqual(b.tv.wb[:3], [512] * 3)
        b.keys("down", "down", "ok")                                             # Green - Magenta, Reset
        d = b.dump()
        self.assertEqual(b.tv.wb, [512] * 6)
        self.assertEqual(b.tv.ctemp, "auto")
        self.assertIn('Reset action "Done"', d)
        self.assertIn("Colour temperature slider 0 0..3 [*Auto", d)
        self.assertEqual(b.tv.saved, 1)
        self.assertEqual(b.tv.saved_look, (3, "auto"))
        b.finish()

    def test_reset_on_auto_sends_no_temperature(self):
        b = self.box().start("White balance")
        b.keys("ok", "down", "right", "back", "down", "down", "ok")
        self.assertIn('Reset action "Done"', b.dump())
        self.assertEqual([x for x in b.tv.log if x.startswith("set colour_temperature")], [])
        b.finish()

    def test_without_the_curves_reset_is_what_it_was(self):
        b = self.box()
        b.tv.curves = False
        b.start("White balance")
        b.keys("ok", "right", "back", "down", "down", "ok")                      # only Warm - Cool, Green - Magenta, Reset are there
        d = b.dump()
        self.assertIn('Reset action "Done"', d)
        self.assertIn("(hidden) Colour temperature", d)
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], [])
        b.finish()

    def test_the_colour_temperature_does_not_wait_for_the_firmware_s_white_balance(self):
        b = self.box()
        b.tv.fw_color = False                                                    # another display firmware: no sliders, but the curves are h713-tv's
        d = b.start("White balance").dump()
        self.assertNotIn("(hidden) Colour temperature", d)
        self.assertIn("(hidden) Warm - Cool", d)
        self.assertIn('White balance info "Not available"', d)
        b.keys("ok", "right")
        self.assertIn("Colour temperature slider 1", b.dump())
        b.finish()

    def test_the_sentence_under_the_page_says_what_the_stop_is_and_what_the_mode_brings(self):
        b = self.box().start("Picture")
        b.keys("ok", *["down"] * 5)
        self.assertIn('sentence "The standard for video. Start here."', b.dump())
        b.keys("down")                                                           # Picture mode
        self.assertIn('sentence "Also sets the colour temperature (White balance) while that is on Auto."', b.dump())
        b.finish()
        b = self.box()
        b.tv.curves = False                                                      # nothing to say about a colour temperature that is not there
        b.start("Picture")
        b.keys("ok", *["down"] * 5)
        self.assertNotIn("sentence", b.dump())
        b.finish()

    def test_the_curves_are_the_makers_and_the_sliders_sit_on_top(self):
        b = self.box().start("White balance")
        b.keys("ok", "right")
        self.assertRegex(b.dump(), r'sentence "Redder whites\. The maker\'s measured warm curve for this panel; it stays when the picture mode changes\."')
        b.keys("right")
        b.dump()
        b.keys("right")
        self.assertRegex(b.dump(), r'sentence "Bluer whites\. The maker\'s measured cool curve')
        b.keys("back", "up")                                                     # no row above Colour temperature: stays
        b.finish()

    def test_what_a_sentence_may_be(self):
        # a sentence of a stop is at most two lines of the pill (880 design px at 26 px, about 70 characters each): not more than 140
        b = self.box().start("White balance")
        for k in range(4):
            b.keys(*(["ok", "right"] if k == 0 else ["right"]))
            note = re.search(r'note "([^"]*)"', [l for l in b.dump().splitlines() if l.strip().startswith("Colour temperature")][0]).group(1)
            self.assertLessEqual(len(note), 142, note)
        b.finish()


class Keystone(Base):
    def test_auto_keystone_writes_the_key_and_restarts_the_unit(self):
        b = self.box().start("Keystone")
        b.keys("ok", "ok")                                  # into the rows; the switch
        d = b.dump()
        self.assertIn("Auto keystone switch 1", d)
        conf = b.read("keystone.conf")
        self.assertIn("after_move = keystone\n", conf)
        self.assertIn("# keystone\n", conf)                  # the rest of the file is as it was
        self.assertIn("iio_name = sc7a20\n", conf)
        self.assertIn("hysteresis_degrees = 1.0\n", conf)
        self.assertEqual(b.tool_log("systemctl"), ["restart --no-block h713-keystone-auto"])
        b.keys("left")
        b.dump()
        self.assertIn("after_move = off\n", b.read("keystone.conf"))
        b.finish()

    def test_measure_again_runs_the_tool_and_says_so(self):
        b = self.box().start("Keystone")
        b.keys("ok", "down", "ok")
        self.assertIn('Measure again now action "Measuring..."', b.dump())
        self.assertTrue(wait_for(lambda: 'Measure again now action "Done"' in b.dump(), 5))
        self.assertEqual(b.tool_log("keystone"), ["once --apply"])
        b.finish()

    def test_a_failed_measurement_is_not_reported_as_done(self):
        b = self.box(extra_env={"JOBEXIT": "5"}).start("Keystone")
        b.keys("ok", "down", "ok")
        self.assertTrue(wait_for(lambda: 'Measure again now action "Failed"' in b.dump(), 5))
        b.finish()

    def test_corners_move_the_way_the_arrow_points(self):
        b = self.box().start("Keystone")
        b.keys("ok", "down", "down", "down", "ok")         # Adjust corners by hand (below Turn to wall): top left, the mask on
        self.assertIn("focus corners", b.dump())
        self.assertEqual(b.warp.pattern, "tl")
        b.keys("right", "down")                            # top left: right and down are inward
        b.dump()
        self.assertEqual((b.warp.v["tl_x"], b.warp.v["tl_y"]), (10, 10))
        b.keys("ok", "left", "up")                         # top right: left is inward, up is outward (clamped at 0)
        b.dump()
        self.assertEqual((b.warp.v["tr_x"], b.warp.v["tr_y"]), (10, 0))
        b.keys("ok", "up")                                 # bottom left: up is inward
        b.dump()
        self.assertEqual(b.warp.v["bl_y"], 10)
        b.keys("back")
        self.assertIn("focus rows", b.dump())
        self.assertIsNone(b.warp.pattern)                  # the pattern is off again
        self.assertIn("tl_x = 10", b.read("warp.conf"))    # the daemon keeps it, not this program
        b.finish()

    def test_leaving_while_a_corner_is_marked_clears_the_pattern(self):
        b = self.box().start("Keystone")
        b.keys("ok", "down", "down", "down", "ok")
        b.dump()
        self.assertEqual(b.warp.pattern, "tl")
        b.finish()
        self.assertIsNone(b.warp.pattern)

    def test_zoom_projection_reset(self):
        b = self.box().start("Keystone")
        b.keys("ok", "down", "down", "down", "down", "left", "left")        # Zoom 100 -> 90: the first press takes the page away
        d = b.dump()
        self.assertIn("focus slider", d)
        self.assertIn("Zoom slider 90 50..100", d)
        b.keys("back")                                              # and Back brings it back, on the Zoom row
        self.assertEqual(b.warp.zoom, 90)
        self.assertIn("on", b.warp.log)                                # a screen zoom needs the warp
        b.keys("down", "ok", "down", "ok")                          # Projection > Rear
        b.dump()
        self.assertEqual(b.warp.mode, "rear")
        b.warp.v["tl_x"] = 40
        b.keys("down", "ok")                                        # Reset keystone
        d = b.dump()
        self.assertEqual(b.warp.v["tl_x"], 0)
        self.assertEqual(b.warp.zoom, 100)
        self.assertIn("Zoom slider 100", d)
        b.finish()

    def test_no_accelerometer_no_auto_keystone(self):
        b = self.box(features="none")
        d = b.start("Keystone").dump()
        self.assertIn("(hidden) Auto keystone", d)
        self.assertIn("(hidden) Measure again now", d)
        self.assertIn("(hidden) Turn to wall", d)          # `h713-keystone once` needs the sensor's tilt
        self.assertNotIn("(hidden) Zoom", d)               # these need the warp, not the sensor
        b.finish()


class KeystoneTurn(Base):
    """Turn to wall: the key of keystone.conf, the pill, the run of the automatic that makes the picture follow."""

    CONF = "# keystone\niio_name = sc7a20\nafter_move = off   # the page writes this\nhysteresis_degrees = 1.0\n"

    def open_turn(self, conf=None, **kw):
        b = self.box(**kw)
        if conf is not None:
            b.write("keystone.conf", conf)
        return b.start("Keystone"), ["ok", "down", "down"]       # the rows; Auto keystone, Measure again now, Turn to wall

    def turns(self, b):
        return b.tool_log("keystone-turn")

    def test_the_row_stands_between_measure_and_the_corners_and_shows_the_file(self):
        b, _ = self.open_turn(self.CONF + "turn_to_wall = 12\n")
        d = b.dump()
        places = [d.index(name) for name in ("Auto keystone", "Measure again now", "Turn to wall", "Adjust corners by hand", "Zoom")]
        self.assertEqual(places, sorted(places))
        self.assertIn("Turn to wall slider 12 -30..30", d)
        b.finish()

    def test_without_the_key_it_is_zero(self):
        b, _ = self.open_turn()
        self.assertIn("Turn to wall slider 0 -30..30", b.dump())
        b.finish()

    def test_right_is_a_turn_to_the_right_and_the_picture_follows(self):
        b, go = self.open_turn()
        b.keys(*go, "right")                                  # the first press moves it and shrinks the page to its pill
        d = b.dump()
        self.assertIn("focus slider row 2", d)
        self.assertIn("Turn to wall slider 1 ", d)
        conf = b.read("keystone.conf")
        self.assertIn("turn_to_wall = 1\n", conf)
        self.assertIn("iio_name = sc7a20\n", conf)           # the rest of the file is as it was
        self.assertIn("# keystone\n", conf)
        self.assertTrue(wait_for(lambda: self.turns(b) == ["1"] and b.tool_log("keystone") == ["once --apply"], 3))
        b.keys("left", "left", "left")                        # Left turns to the left, through 0 to -2: one press is a degree
        b.dump()
        self.assertIn("turn_to_wall = -2\n", b.read("keystone.conf"))
        self.assertIn("Turn to wall slider -2 ", b.dump())
        b.finish()

    def test_a_burst_of_one_key_is_one_change_and_one_run(self):
        b, go = self.open_turn()
        b.keys(*go, *["right"] * 6)                           # a held key arrives as a burst
        b.dump()
        self.assertIn("turn_to_wall = 6\n", b.read("keystone.conf"))
        self.assertTrue(wait_for(lambda: len(self.turns(b)) == 1, 3))
        self.assertEqual(self.turns(b), ["6"])
        b.finish()

    def test_it_stops_at_thirty_degrees_to_either_side(self):
        b, go = self.open_turn()
        b.keys(*go, *["right"] * 40)
        b.dump()
        self.assertIn("turn_to_wall = 30\n", b.read("keystone.conf"))
        b.keys(*["left"] * 70)
        b.dump()
        self.assertIn("turn_to_wall = -30\n", b.read("keystone.conf"))
        self.assertIn("Turn to wall slider -30", b.dump())
        b.finish()

    def test_a_press_while_a_run_is_going_is_not_queued_and_not_lost(self):
        """A run takes 0.5 s here (on the board: about a second). Five presses fall into it: they are not five runs and not four
        dropped ones - the second run takes the last value."""
        b, go = self.open_turn(extra_env={"JOBTIME": "0.5"})
        b.keys(*go, "right")
        for _ in range(4):
            b.keys("sleep 60", "right")
        b.dump()
        self.assertTrue(wait_for(lambda: len(self.turns(b)) == 2, 4))
        self.assertEqual(self.turns(b), ["1", "5"])
        time.sleep(1.3)
        self.assertEqual(self.turns(b), ["1", "5"])             # and no third run for nothing
        self.assertEqual(b.tool_log("keystone"), ["once --apply"] * 2)
        self.assertIn("turn_to_wall = 5\n", b.read("keystone.conf"))
        b.finish()

    def test_a_press_while_another_job_runs_waits_for_it(self):
        """Measure again now is under way (the panel and the warp are its): the turn is written and applied when it is over."""
        b = self.box(extra_env={"JOBTIME": "0.6"})
        b.write("keystone.conf", self.CONF + "turn_to_wall = 0\n")
        b.start("Keystone")
        b.keys("ok", "down", "ok")                              # Measure again now
        self.assertIn('Measure again now action "Measuring..."', b.dump())
        b.keys("down", "right")                                 # Turn to wall, one press
        b.dump()
        self.assertIn("turn_to_wall = 1\n", b.read("keystone.conf"))
        self.assertEqual(b.tool_log("keystone"), ["once --apply"])           # one run, the measurement
        self.assertTrue(wait_for(lambda: len(b.tool_log("keystone")) == 2 and len(self.turns(b)) == 2, 4))
        self.assertEqual(self.turns(b), ["0", "1"])             # the measurement had the old value, the run after it the new one
        b.finish()

    def test_a_run_that_fails_is_said(self):
        b, go = self.open_turn(extra_env={"JOBEXIT": "5"})
        b.keys(*go, "right")
        self.assertTrue(wait_for(lambda: b.tool_log("keystone") == ["once --apply"], 3))
        time.sleep(0.6)
        b.dump()
        err = b.finish()
        self.assertIn("Turn to wall: h713-keystone once --apply did not succeed", err)

    def test_when_the_page_ends_the_last_value_is_still_applied(self):
        b, go = self.open_turn(extra_env={"JOBTIME": "0.6"})
        b.keys(*go, "right", "sleep 50", "right", "sleep 50", "right")
        b.dump()
        self.assertEqual(self.turns(b), ["1"])                   # the first run is going, two presses wait
        b.finish()                                               # the page ends: the run is waited for, the last value runs on its own
        self.assertTrue(wait_for(lambda: len(self.turns(b)) == 2, 4))
        self.assertEqual(self.turns(b), ["1", "3"])
        self.assertIn("turn_to_wall = 3\n", b.read("keystone.conf"))

    def test_when_the_page_ends_during_another_job_the_last_value_is_still_applied(self):
        """Measure again now is under way when Back is pressed: it has read the configuration already, so the turn pressed
        after it has to be run once it is over, by the page that waits for it. (It stayed in the file, unapplied, while the page
        waited only for a run of its own.)"""
        b = self.box(extra_env={"JOBTIME": "0.6"})
        b.write("keystone.conf", self.CONF + "turn_to_wall = 0\n")
        b.start("Keystone")
        b.keys("ok", "down", "ok")                              # Measure again now
        self.assertIn('Measure again now action "Measuring..."', b.dump())
        b.keys("down", "right")                                 # Turn to wall, one press: it waits for the measurement
        b.dump()
        b.finish()
        self.assertTrue(wait_for(lambda: len(b.tool_log("keystone")) == 2 and len(self.turns(b)) == 2, 4))
        self.assertEqual(self.turns(b), ["0", "1"])

    def test_reset_keystone_takes_the_turn_back_and_does_not_run_the_automatic(self):
        b, go = self.open_turn(self.CONF + "turn_to_wall = 12\n")
        b.warp.v["tl_x"] = 40
        b.keys("ok", *["down"] * 6, "ok")                        # Reset keystone
        d = b.dump()
        self.assertIn("Reset keystone action \"Done\"", d)
        self.assertIn("Turn to wall slider 0 ", d)
        self.assertIn("turn_to_wall = 0\n", b.read("keystone.conf"))
        self.assertEqual(b.warp.v["tl_x"], 0)
        time.sleep(0.3)
        self.assertEqual(b.tool_log("keystone"), [])             # a reset is corners 0, not a measurement
        b.finish()

    def test_a_value_with_a_fraction_is_shown_to_the_nearest_degree(self):
        b, _ = self.open_turn(self.CONF + "turn_to_wall = 7.4\n")
        self.assertIn("Turn to wall slider 7 ", b.dump())
        b.finish()

    def test_a_value_out_of_range_is_shown_at_its_end(self):
        b, _ = self.open_turn(self.CONF + "turn_to_wall = -99\n")
        self.assertIn("Turn to wall slider -30 ", b.dump())
        b.finish()


class SoundFocus(Base):
    def test_volume_and_mute(self):
        b = self.box().start("Sound")
        b.keys("ok", "right", "down", "ok")
        d = b.dump()
        self.assertEqual(b.tv.volume, 95)
        self.assertTrue(b.tv.mute)
        self.assertIn("Mute switch 1", d)
        b.keys("left")
        b.dump()
        self.assertFalse(b.tv.mute)
        b.finish()

    def test_volume_stops_at_the_ends(self):
        b = self.box().start("Sound")
        b.keys("ok", *["right"] * 6)
        b.dump()
        self.assertEqual(b.tv.volume, 100)
        b.finish()

    def test_autofocus_and_after_a_move(self):
        b = self.box().start("Focus")
        b.keys("ok", "ok")
        self.assertIn('Autofocus now action "Focusing..."', b.dump())
        self.assertTrue(wait_for(lambda: 'Autofocus now action "Done"' in b.dump(), 5))
        self.assertEqual(b.tool_log("autofocus"), ["-q run"])
        b.keys("down", "ok")
        b.dump()
        self.assertIn("after_move = keystone+focus\n", b.read("keystone.conf"))     # it also turns the automatic on
        b.keys("down", "down", "ok")                          # Focus by hand: nothing; back up and switch off
        b.keys("up", "left")
        b.dump()
        self.assertIn("after_move = keystone\n", b.read("keystone.conf"))
        b.finish()

    def test_focus_by_hand_is_queued_while_the_motor_runs(self):
        b = self.box().start("Focus")
        b.keys("ok", "down", "down", "right")
        wait_for(lambda: b.tool_log("focus") == ["up 20"], 3)
        b.keys("right", "right", "left", "right")             # while the first run is going: counted, one run after it
        self.assertTrue(wait_for(lambda: len(b.tool_log("focus")) == 2, 5))
        self.assertEqual(b.tool_log("focus"), ["up 20", "up 40"])
        b.finish()

    def test_no_motor_no_focus_rows(self):
        b = self.box(features="none")
        d = b.start("Focus").dump()
        self.assertEqual(d.count("(hidden)"), 3)
        self.assertIn("focus areas", d)
        b.keys("right")                                        # nothing to open
        self.assertIn("focus areas", b.dump())
        b.finish()


class InputPowerWifi(Base):
    def modes(self, b, extra=()):
        """the launcher.d of the image: HDMI input, Kodi, Browser, Desktop (modes: they name a unit), Settings, Standby (they do not)"""
        d = os.path.join(b.etc, "launcher.d")
        for name, label, unit in (("10-hdmi", "HDMI input", None), ("20-kodi", "Kodi", "h713-kodi.service"),
                                  ("25-browser", "Browser", "h713-browser.service"), ("30-desktop", "Desktop", "h713-desktop.service"),
                                  ("50-settings", "Settings", None), ("90-standby", "Standby", None)) + tuple(extra):
            with open(os.path.join(d, name + ".conf"), "w") as f:
                f.write("label = %s\nicon = x\n%s\n" % (label, ("unit = " + unit) if unit else "exec = /x/y"))

    def test_there_is_no_source_row(self):
        d = self.box().start("Input").dump()
        self.assertNotIn("Source", d)                          # "Source" went (Marco 17.10.2026): a running program is on the wall, else HDMI
        self.assertIn("On start choice", d)
        self.assertIn("On the wall now info", d)

    def test_on_start_is_kept_for_h713_keys(self):
        b = self.box()
        b.write("keys.conf", "# keys\nvolume_step = 5\n")
        d = b.start("Input").dump()
        self.assertIn("On start choice [*Launcher|HDMI input|Last used]", d)   # nothing in the file: the launcher, h713-keys' default
        b.keys("ok", "ok", "down", "ok")                              # On start > HDMI input
        d = b.dump()
        self.assertIn("On start choice [Launcher|*HDMI input|Last used]", d)
        self.assertIn("on_start = hdmi", b.read("keys.conf"))
        self.assertIn("volume_step = 5", b.read("keys.conf"))         # the rest of the file stays
        b.keys("ok", "up", "ok")                                      # and back to the launcher
        b.dump()
        self.assertEqual(b.read("keys.conf").count("on_start"), 1)    # the same line, not a second one
        self.assertIn("on_start = launcher", b.read("keys.conf"))
        b.finish()

    def test_on_start_offers_the_modes_of_launcher_d_and_last_used(self):
        """Launcher, HDMI input, every entry with a unit in file order (Kodi - and Browser, Desktop with no change here), Last used"""
        b = self.box()
        self.modes(b)
        d = b.start("Input").dump()
        self.assertIn("On start choice [*Launcher|HDMI input|Kodi|Browser|Desktop|Last used]", d)
        b.keys("ok", "ok", "down", "down", "ok")                      # On start > Kodi
        d = b.dump()
        self.assertIn("On start choice [Launcher|HDMI input|*Kodi|Browser|Desktop|Last used]", d)
        self.assertIn("on_start = kodi", b.read("keys.conf"))         # the entry's file name (20-kodi.conf), as h713-keys names it
        b.keys("ok", "down", "down", "down", "down", "ok")            # ... Last used
        b.dump()
        self.assertIn("on_start = last", b.read("keys.conf"))
        b.keys("ok", "up", "up", "ok")                                # ... Browser
        b.dump()
        self.assertIn("on_start = browser", b.read("keys.conf"))
        b.finish()

    def test_a_new_mode_comes_without_a_change_here(self):
        b = self.box()
        self.modes(b, extra=(("40-terminal", "Terminal", "h713-terminal.service"),))
        d = b.start("Input").dump()
        self.assertIn("[*Launcher|HDMI input|Kodi|Browser|Desktop|Terminal|Last used]", d)
        b.keys("ok", "ok", *["down"] * 5, "ok")
        b.dump()
        self.assertIn("on_start = terminal", b.read("keys.conf"))
        b.finish()

    def test_every_option_has_its_sentence_for_the_wall(self):
        b = self.box()
        self.modes(b)
        b.start("Input")
        b.keys("ok", "ok", "down", "down")                            # the choice stands on Kodi
        d = b.dump()
        self.assertIn('note "Kodi: Kodi opens by itself when the projector has started."', d)
        b.keys("down", "down", "down")                                # Last used
        self.assertIn('note "Last used: what ran when the projector was switched off comes back, the HDMI input or a program."', b.dump())
        b.keys("up", "up", "up", "up", "up")                          # Launcher
        self.assertIn('note "Launcher: when the projector has started', b.dump())
        b.finish()

    def test_on_start_shows_what_the_file_holds(self):
        b = self.box()
        self.modes(b)
        b.write("keys.conf", "on_start = hdmi\n")
        self.assertIn("On start choice [Launcher|*HDMI input|Kodi|Browser|Desktop|Last used]", b.start("Input").dump())
        b.finish()
        b = self.box()
        self.modes(b)
        b.write("keys.conf", "on_start = last\n")
        self.assertIn("|*Last used]", b.start("Input").dump())
        b.finish()
        b = self.box()
        self.modes(b)
        b.write("keys.conf", "on_start = gone\n")                     # an entry that was taken away: h713-keys starts the launcher then
        self.assertIn("[*Launcher|", b.start("Input").dump())
        b.finish()

    def test_on_the_wall_now_names_the_mode_that_runs(self):
        b = self.box()
        self.modes(b)
        self.assertIn('On the wall now info "HDMI picture"', b.start("Input").dump())
        b.finish()
        b = self.box()
        self.modes(b)
        with open(os.path.join(b.log, "active"), "w") as f:
            f.write("h713-browser.service\n")
        self.assertIn('On the wall now info "Browser"', b.start("Input").dump())      # not "Kodi" because a client is on the wall
        b.finish()

    def test_on_the_wall_now_says_no_hdmi_signal_when_the_page_stands(self):
        """P5: with no mode running and h713-tv saying that h713-osd's page "No signal on HDMI" is on the wall, the sentence says so"""
        b = self.box()
        self.modes(b)
        b.tv.nosignal = True
        self.assertIn('On the wall now info "No HDMI signal"', b.start("Input").dump())
        b.finish()
        b = self.box()                                                  # the control: the status line says "none"
        self.modes(b)
        self.assertIn('On the wall now info "HDMI picture"', b.start("Input").dump())
        b.finish()
        b = self.box()                                                  # a mode that runs is the wall, whatever the signal does
        self.modes(b)
        b.tv.nosignal = True
        with open(os.path.join(b.log, "active"), "w") as f:
            f.write("h713-browser.service\n")
        self.assertIn('On the wall now info "Browser"', b.start("Input").dump())
        b.finish()

    def test_no_launcher_no_on_start_row(self):
        b = self.box(launcher=False)
        self.assertIn("(hidden) On start", b.start("Input").dump())
        b.finish()

    def test_standby_only_where_it_can_happen(self):
        b = self.box(standby="not offered (no crust)")
        d = b.start("Power").dump()
        self.assertIn("Power key choice [*Power off]", d)
        b.finish()

    def test_power_key_and_remote(self):
        b = self.box().start("Power")
        b.keys("ok", "ok", "down", "ok")                      # Power key > Standby
        b.keys("down", "left")                                # Remote power key off
        b.dump()
        self.assertEqual([x for x in b.tool_log("power") if x.startswith("set")],
                         ["set default standby", "set remote off"])
        self.assertIn("default = standby", b.read("power.conf"))
        self.assertIn("remote = off", b.read("power.conf"))
        b.finish()

    def test_wifi_shows_and_never_the_password(self):
        b = self.box().start("Wi-Fi")
        d = b.dump()
        self.assertIn('Mode info "Client"', d)
        self.assertIn('Network info "Wohnzimmer"', d)
        self.assertIn('Signal info "-52 dBm, excellent"', d)
        self.assertIn('Address info "192.168.8.131"', d)
        self.assertNotIn("geheim", d)
        err = b.finish()
        self.assertNotIn("geheim", err)

    def test_wifi_as_an_access_point(self):
        b = self.box(wifi_mode="ap").start("Wi-Fi")
        d = b.dump()
        self.assertIn('Mode info "Access point"', d)
        self.assertIn('Network info "Wohnzimmer"', d)
        b.finish()


class Life(Base):
    def test_back_in_the_areas_closes(self):
        b = self.box().start()
        b.keys("back")
        self.assertEqual(b.proc.wait(timeout=5), 0)

    def test_how_the_page_ends_is_its_exit_status(self):
        """h713-keys reads it (launcher.d `return = launcher`): only Back at the top is 0 and brings the launcher back; every other
        end leaves the wall to the mode below (Marco 17.10.2026: Back goes one level back, Home goes home)."""
        b = self.box().start()
        b.keys("back")
        self.assertEqual(b.proc.wait(timeout=5), 0)                    # Back in the areas: the launcher
        b = self.box().start()
        b.keys("home")
        self.assertEqual(b.proc.wait(timeout=5), 10)                   # Home: everything closes
        b = self.box().start("Picture")
        b.keys("ok", "home")
        self.assertEqual(b.proc.wait(timeout=5), 10)                   # also from inside a row
        b = self.box().start("Input")
        b.keys("ok", "ok", "home")                                     # also with a choice open
        self.assertEqual(b.proc.wait(timeout=5), 10)
        b = self.box().start()
        b.keys("power")
        self.assertEqual(b.proc.wait(timeout=5), 11)                   # Power: h713-power is told

    def test_back_inside_the_page_is_one_level_not_the_end(self):
        b = self.box().start("Sound")
        b.keys("ok", "back")                                           # rows -> areas
        self.assertIn("focus areas", b.dump())
        self.assertIsNone(b.proc.poll())
        b.keys("back")                                                 # areas -> out, with 0
        self.assertEqual(b.proc.wait(timeout=5), 0)

    def test_a_signal_is_not_a_way_back(self):
        b = self.box().start("Picture")
        b.dump()
        b.finish(signal.SIGTERM)
        self.assertEqual(b.proc.returncode, 15)                        # somebody ended the page: no launcher under it

    def test_areas_remember_their_row(self):
        b = self.box().start("Picture")
        b.keys("ok", "down", "down", "back", "down", "up", "ok")
        self.assertIn("area Picture focus rows row 2", b.dump())
        b.finish()

    def test_sigterm_writes_what_was_held_back(self):
        b = self.box().start("Picture")
        b.keys("ok", "right")
        b.dump()
        b.finish(signal.SIGTERM)
        self.assertEqual(b.tv.saved, 1)

    def test_tools_gone_nothing_breaks(self):
        b = self.box()
        b.tv.stop()
        b.warp.stop()
        b.start()
        d = b.dump()
        self.assertIn("area Picture focus areas", d)
        b.keys(*["down"] * 8)
        self.assertIn("area Wi-Fi", b.dump())
        b.keys("back")
        self.assertEqual(b.proc.wait(timeout=5), 0)


# the kernel's key codes, as h713-keys reads them
UP, DOWN, LEFT, RIGHT, OK, SELECT, BACK, HOME, POWER = 103, 108, 105, 106, 352, 353, 158, 172, 116
BTN_LEFT = 272                                        # the remote's OK in its mouse mode
ENTER, COMPOSE, MENU = 28, 127, 139                    # the remote's OK and Menu since 70-h713-remote.rules; KEY_MENU without it
GROUND, PAGEPILL = 0xff0b0e0d, 0xff1c2321             # the page's opaque ground and its lit pill, ARGB
VOLUP, VOLDOWN, MUTE, F4, F5 = 115, 114, 113, 62, 63


@unittest.skipUnless(any(f and os.path.exists(f) for f in FONTS), "no font (set H713_TEST_FONT)")
class Device(Base):
    def test_opens_on_the_wall_first_then_takes_the_remote(self):
        b = self.box().start_device("Sound")
        self.assertTrue(wait_for(lambda: any(l.startswith("page show") for l in b.osd.log), 5))
        self.assertEqual(b.osd.log[0], "page open")
        self.assertEqual(b.osd.log[1], "page show 0 0 %d %d" % (b.osd.W, b.osd.H))     # the whole page once
        self.assertEqual(b.osd.pixel(3, 3), GROUND)                                     # the opaque ground is in the canvas
        b.press(BACK)
        self.assertEqual(b.proc.wait(timeout=5), 0)
        self.assertTrue(wait_for(lambda: b.osd.closed))                                 # the connection ends: the page is gone

    def test_back_hands_the_wall_over_home_does_not(self):
        """Back at the top brings the launcher back: the page says "page handover" before its connection ends, so that h713-osd keeps
        it on the wall until the launcher is drawn (no HDMI picture between the two, P2c); Home leaves the wall to the mode at once"""
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(BACK)
        self.assertEqual(b.proc.wait(timeout=5), 0)
        self.assertTrue(wait_for(lambda: b.osd.closed))
        self.assertIn("page handover", b.osd.log)
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)
        self.assertTrue(wait_for(lambda: b.osd.closed))
        self.assertNotIn("page handover", b.osd.log)

    def test_the_keys_drive_the_page(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK, RIGHT)                                       # into the rows; Volume up one step
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        n = len(b.osd.log)
        b.press(DOWN, SELECT)                                    # the Bluetooth remote's OK is KEY_SELECT: Mute on
        self.assertTrue(wait_for(lambda: b.tv.mute, 5))
        self.assertTrue(wait_for(lambda: len(b.osd.log) > n + 1, 5))     # and the rows were shown again, not the whole page
        self.assertNotEqual(b.osd.log[-1], "page show 0 0 %d %d" % (b.osd.W, b.osd.H))
        b.press(BACK, BACK)
        self.assertEqual(b.proc.wait(timeout=5), 0)

    def test_the_remotes_ok_as_enter_is_ok_and_menu_is_nothing(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(ENTER, RIGHT)                                    # KEY_ENTER: into the rows; Volume up one step
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        b.press(DOWN, ENTER)                                     # and again as OK: Mute on
        self.assertTrue(wait_for(lambda: b.tv.mute, 5))
        n = len(b.osd.log)
        b.press(COMPOSE, MENU)                                   # Menu: recognised, no meaning here
        time.sleep(0.5)
        self.assertEqual(len(b.osd.log), n)
        self.assertIsNone(b.proc.poll())
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)

    def test_the_remotes_mouse_click_is_ok(self):
        """In its mouse mode the remote sends OK as BTN_LEFT and the page has no pointer: the click is OK (TODO 2.130)"""
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(BTN_LEFT, RIGHT)                                 # BTN_LEFT: into the rows; Volume up one step
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        b.press(DOWN, BTN_LEFT)                                  # and again as OK: Mute on
        self.assertTrue(wait_for(lambda: b.tv.mute, 5))
        b.press(BTN_LEFT, value=0)                               # its release: nothing
        time.sleep(0.3)
        self.assertTrue(b.tv.mute)
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)

    def test_both_devices_are_read(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK, device=1)                                    # (two devices have no order between them: let one finish)
        time.sleep(0.3)
        b.press(RIGHT, device=0)
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)

    def test_held_arrows_repeat_but_other_keys_do_not(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK)
        b.press(RIGHT, value=2)                                 # a repeat of the arrow: a step
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        b.press(DOWN)
        b.press(OK, value=2)                                    # a repeat of OK: nothing (Mute stays off)
        b.press(OK, value=0)                                    # a release: nothing
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)
        self.assertFalse(b.tv.mute)

    def test_an_arrow_press_and_its_release_is_one_step(self):
        # found on the box 15.10.: the real remote sends value 1 then value 0, and the release moved the arrow a second time
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK)
        b.press(RIGHT, value=1)
        b.press(RIGHT, value=0)
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        time.sleep(0.5)
        self.assertEqual(b.tv.volume, 95)                       # not 100
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)

    def test_power_is_handed_to_h713_power(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(POWER)
        self.assertEqual(b.power.recv(32), b"down")
        self.assertEqual(b.proc.wait(timeout=5), 11)
        self.assertTrue(wait_for(lambda: b.osd.closed))

    def test_volume_mute_and_focus_keys_still_work(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.tv.mute = True
        b.press(VOLUP)                                           # louder lifts a mute
        self.assertTrue(wait_for(lambda: b.tv.volume == 95 and not b.tv.mute, 5))
        b.press(VOLDOWN, VOLDOWN)
        self.assertTrue(wait_for(lambda: b.tv.volume == 85, 5))
        b.press(MUTE)
        self.assertTrue(wait_for(lambda: b.tv.mute, 5))
        b.press(MUTE)
        self.assertTrue(wait_for(lambda: not b.tv.mute, 5))
        b.press(HOME)
        b.proc.wait(timeout=5)

    def test_focus_keys_move_the_motor(self):
        b = self.box().start_device("Focus")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK)                                              # into the rows (the first is Autofocus now)
        b.press(F4)
        self.assertTrue(wait_for(lambda: b.tool_log("focus") == ["up 20"], 5))
        b.press(F5)
        self.assertTrue(wait_for(lambda: b.tool_log("focus") == ["up 20", "down 20"], 5))
        b.press(HOME)
        b.proc.wait(timeout=5)

    def test_the_page_is_not_opened_when_it_cannot_be_seen(self):
        b = self.box().start_device("Sound", refuse="ok unseen\n")
        self.assertEqual(b.proc.wait(timeout=5), 3)
        self.assertIn("no page", b.proc.stderr.read())
        b.press(OK)                                              # the remote was never taken: nothing reads this
        self.assertFalse(b.osd.opened)

    def test_waits_for_the_picture_and_then_closes(self):
        b = self.box(extra_env={"H713_SETTINGS_PATIENCE": "2"}).start_device("Sound", osd_answer="ok waiting")
        t0 = time.time()
        self.assertEqual(b.proc.wait(timeout=8), 13)
        self.assertGreaterEqual(time.time() - t0, 1.5)
        self.assertIn("nothing can be seen for 2 s", b.proc.stderr.read())

    def test_a_picture_that_comes_back_in_time_keeps_it_open(self):
        b = self.box(extra_env={"H713_SETTINGS_PATIENCE": "3"}).start_device("Sound", osd_answer="ok waiting")
        wait_for(lambda: len(b.osd.log) > 1)
        time.sleep(1.0)
        b.osd.answer = "ok"                                      # the autofocus gave the panel back
        b.press(OK, DOWN)                                        # the next drawing is shown
        time.sleep(3.5)
        self.assertIsNone(b.proc.poll())
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)

    def test_closes_when_h713_osd_is_gone(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.osd.drop()
        b.press(OK)                                              # the next drawing finds nobody
        self.assertEqual(b.proc.wait(timeout=5), 14)              # the page is closed and the remote is given back
        self.assertIn("h713-osd does not answer", b.proc.stderr.read())

    def test_no_font_no_page(self):
        b = self.box()
        b.env["H713_SETTINGS_FONT"] = "/nonexistent/font.ttf"
        b.start_device("Sound", font=False)
        self.assertEqual(b.proc.wait(timeout=5), 5)
        self.assertFalse(b.osd.opened)                           # nothing was asked of h713-osd, no remote was taken
        self.assertIn("without words", b.proc.stderr.read())

    def test_no_remote_no_page(self):
        b = self.box().start_device("Sound", devices=0)
        self.assertEqual(b.proc.wait(timeout=5), 4)
        self.assertTrue(wait_for(lambda: b.osd.closed))
        self.assertIn("no remote", b.proc.stderr.read())

    def test_closes_by_itself_after_a_while_without_a_key(self):
        b = self.box().start_device("Sound", idle=2)
        t0 = time.time()
        self.assertEqual(b.proc.wait(timeout=8), 12)
        self.assertGreaterEqual(time.time() - t0, 1.5)
        self.assertIn("no key for 2 s", b.proc.stderr.read())

    def test_every_drawing_can_be_kept_as_evidence(self):
        b = self.box()
        snap = os.path.join(b.dir, "snap")
        os.mkdir(snap)
        b.env["H713_SETTINGS_SNAP"] = snap
        b.env["H713_SETTINGS_TIMES"] = "1"
        b.start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK, RIGHT)
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        b.press(HOME)
        b.proc.wait(timeout=5)
        names = sorted(os.listdir(snap))
        self.assertGreaterEqual(len(names), 3)                    # the whole page, the rows after OK, the row after Right
        self.assertEqual(names[0], "0001.pam")
        err = b.proc.stderr.read()
        self.assertRegex(err, r"drawn [\d.]+ ms \(1 pieces, 360 px high\), shown [\d.]+ ms\n")      # the first, whole page: no key
        self.assertRegex(err, r"drawn [\d.]+ ms \(\d+ pieces, \d+ px high\), shown [\d.]+ ms, key to answer [\d.]+ ms")

    def test_a_move_shows_only_what_changed(self):
        # a move between two rows that have no note is one piece: the rows (the note and the keys under them stay as they are)
        b = self.box()
        b.start_device("Picture")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK)                                              # into the rows
        time.sleep(0.5)
        n = len(b.osd.log)
        b.press(DOWN)                                            # Brightness -> Contrast
        self.assertTrue(wait_for(lambda: len(b.osd.log) >= n + 1, 5))
        time.sleep(0.5)
        shows = [l.split() for l in b.osd.log[n:] if l.startswith("page show")]
        self.assertEqual(len(shows), 1, b.osd.log[n:])
        self.assertTrue(int(shows[0][5]) < 360 * 0.4, shows)     # not the big rectangle around both
        b.press(HOME)
        b.proc.wait(timeout=5)

    def test_a_move_onto_a_row_with_a_note_shows_the_note_apart(self):
        b = self.box()
        b.start_device("Keystone")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK)                                              # into the rows: Auto keystone has a sentence
        time.sleep(0.5)
        n = len(b.osd.log)
        b.press(DOWN)                                            # onto Measure again now: the sentence goes, the rows and the note change
        self.assertTrue(wait_for(lambda: len(b.osd.log) >= n + 2, 5))
        time.sleep(0.5)
        shows = [l.split() for l in b.osd.log[n:] if l.startswith("page show")]
        self.assertEqual(len(shows), 2, b.osd.log[n:])
        heights = sorted(int(s[5]) for s in shows)
        self.assertTrue(heights[1] < 360 * 0.4, shows)           # neither is the big rectangle around both
        b.press(HOME)
        b.proc.wait(timeout=5)

    def test_a_key_keeps_it_open(self):
        b = self.box().start_device("Sound", idle=2)
        for _ in range(4):
            time.sleep(0.8)
            b.press(DOWN)                                        # nothing to do in the areas but it counts as a key
        self.assertIsNone(b.proc.poll())
        b.press(HOME)
        b.proc.wait(timeout=5)


class LookKit(Base):
    """The picture of a state: the canvas of --test as PAM, and where its ink is."""

    W, H = 960, 540                     # u = 1/2: the margins are 48 px left and right, 27 px top and bottom

    def snap(self, b, name):
        path = os.path.join(b.dir, name + ".pam")
        b.keys("snap " + path)
        b.dump()
        with open(path, "rb") as f:
            head = b""
            while not head.endswith(b"ENDHDR\n"):
                head += f.readline()
            return f.read()

    def ink(self, data, opaque):
        """(x0, y0, x1, y1) of what is on the picture: on the opaque page every pixel that is not the ground, over the picture every
        pixel with alpha; None when there is none"""
        ground = struct.pack("BBBB", 11, 14, 13, 255)
        w = self.W
        box = None
        for y in range(self.H):
            row = data[y * w * 4:(y + 1) * w * 4]
            if opaque:
                if row == ground * w:
                    continue
                xs = [x for x in range(w) if row[4 * x:4 * x + 4] != ground]
            else:
                if row[3::4].count(0) == w:
                    continue
                xs = [x for x in range(w) if row[4 * x + 3]]
            box = (xs[0], y, xs[-1], y) if box is None else (min(box[0], xs[0]), box[1], max(box[2], xs[-1]), y)
        return box

    def inside(self, box, what):
        self.assertIsNotNone(box, what)
        x0, y0, x1, y1 = box                                       # one pixel of anti-aliasing is allowed
        self.assertGreaterEqual(x0, 47, what)
        self.assertLessEqual(x1, self.W - 48, what)
        self.assertGreaterEqual(y0, 26, what)
        self.assertLessEqual(y1, self.H - 27, what)


class Look(LookKit):
    """What the owner asked for on 15.10.: everything inside a safe margin of 5 %, an opaque calm page, one pill over the picture
    while a value that is judged on the picture is adjusted. The picture of every state is the canvas of --test as PAM."""

    def test_the_last_row_s_pill_is_whole(self):
        # Marco 20.10.2026: the pill of "Reset picture" was cut off at the bottom - the note under the rows cleared its lower edge
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        bright = lambda px: px[0] > 200 and px[1] > 200 and px[2] > 200     # the pill's outline (the text is not in the band looked at)
        for curves in (False, True):                                  # eight rows, and nine with Gamma
            box = self.box()
            box.tv.curves = curves
            b = box.start("Picture", size="%dx%d" % (self.W, self.H))
            b.keys("ok", *["down"] * 10)                              # to the last row: Reset picture
            data = self.snap(b, "last%d" % curves)
            rows = [y for y in range(self.H) for x in (self.W * 3 // 4,) if bright(data[(y * self.W + x) * 4:(y * self.W + x) * 4 + 3])]
            self.assertGreaterEqual(len(rows), 2, "no outline of the pill found (curves %s)" % curves)
            top, bottom = rows[0], rows[-1]
            self.assertLess(bottom, int(890 * self.H / 1080), "the pill reaches the note (curves %s)" % curves)
            self.assertGreater(bottom - top, 20, "only one edge of the pill is there, the other is cut (curves %s)" % curves)
            b.finish()

    def test_a_choice_leaves_nothing_of_the_rows_below_it(self):
        # Mythos 19.10.2026 (gamma-ui): opening Picture mode's five options left the rows below them (Aspect ratio, Reset picture)
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        b = self.box().start("Picture", size="%dx%d" % (self.W, self.H))
        b.keys("ok", *["down"] * 5, "ok")                           # Picture mode: five options over eight rows
        self.assertIn("focus choice", b.dump())
        data = self.snap(b, "choice")
        ground = struct.pack("BBBB", 11, 14, 13, 255)
        u = self.H / 1080
        y0, y1 = int((202 + 94 * 5 - 54) * u) + 1, int(890 * u) - 1  # below the fifth option down to the note
        x0, x1 = int(690 * u) + 1, int(1830 * u) - 1
        stray = sum(data[(y * self.W + x) * 4:(y * self.W + x) * 4 + 4] != ground for y in range(y0, y1) for x in range(x0, x1))
        self.assertEqual(stray, 0, "pixels of the rows below the options are still on the page")

    def test_a_shorter_area_leaves_nothing_of_the_longer_one(self):
        # Marco 19.10.2026: Reset in Colour, then White balance showed two "Reset" rows - the fourth was Colour's, never cleared
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        size = "%dx%d" % (self.W, self.H)
        fresh = self.snap(self.box().start("White balance", size=size), "fresh")
        b = self.box().start("Colour", size=size)
        b.keys("ok", "down", "down", "down", "ok", "back", "up")  # Reset, the areas, White balance (three rows)
        self.assertEqual(self.snap(b, "after"), fresh, "the page after the change differs from White balance opened fresh")
        b = self.box().start("Colour", size=size)
        b.keys("ok", "ok", "back", "back", "up")                    # Primary colour's six options, back, White balance
        self.assertEqual(self.snap(b, "options"), fresh, "what a choice's options left stays on the page")

    def test_every_page_stays_inside_the_safe_margin(self):
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        seen = 0
        for area in ("Picture", "White balance", "Colour", "Keystone", "Sound", "Focus", "Input", "Power", "Wi-Fi"):
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            self.inside(self.ink(self.snap(b, "a"), True), "%s, the areas" % area)         # the areas and the rows, nothing lit
            b.keys("ok")
            for row in range(8):
                self.inside(self.ink(self.snap(b, "r"), True), "%s, row %d" % (area, row))
                seen += 1
                if "focus rows" not in b.dump() or row == 7:
                    break
                b.keys("down")
            b.finish()
        self.assertGreater(seen, 20)

    def test_every_drawing_reports_all_it_changed(self):
        # 16.10.2026: h713-osd puts the columns of a "page show" only; a pixel changed outside the reported pieces is stale on the wall.
        # The program counts them itself in --test mode (it compares the canvas before and after each drawing).
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        walk = ["ok"] + ["down", "right", "left", "ok", "back"] * 3 + ["down", "right", "right", "left", "left", "ok", "up", "back", "back",
                                                                           "down", "ok", "down", "down", "ok", "down", "ok", "back", "up"]
        for area in ("Picture", "White balance", "Colour", "Keystone", "Sound", "Focus", "Input", "Power", "Wi-Fi"):
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            for key in walk + ["down", "up", "ok", "down", "up", "ok"]:
                if key == "back" and "focus areas" in b.dump().splitlines()[0]:
                    continue                                       # Back in the areas closes the page: not here
                b.keys(key)
            dump = b.dump().splitlines()
            self.assertIn("outside 0", dump, "%s: %s" % (area, dump[:1]))
            b.finish()

    def test_a_redrawn_page_is_the_same_picture(self):
        # the symbols and the glyphs are drawn from tables after the first time: the second time is the first time again
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        for area in ("Picture", "Keystone", "Focus"):                     # (the others show what a reading changes by itself: a signal, a volume)
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            first = self.snap(b, "first")
            b.keys("down", "down", "up", "up")                     # the areas' pills and the right pane are drawn again
            self.assertEqual(self.snap(b, "again"), first, area)
            b.keys("ok", "down", "up")
            rows = self.snap(b, "rows")
            b.keys("down", "down", "up", "up")
            self.assertEqual(self.snap(b, "rows again"), rows, area)
            b.finish()

    def test_the_last_area_pill_is_whole(self):
        # owner, 15.10.: the pill round Wi-Fi, the last area, was cut off at the bottom (the note's clear box began inside it)
        # 18.10.2026: nine areas, pitch 94: Wi-Fi is the ninth (centre 950, half height 44), and the hint is no longer under the areas
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        b = self.box().start("Wi-Fi", size="%dx%d" % (self.W, self.H))
        for step in ("areas", "rows"):
            page = self.snap(b, step)
            pill = lambda x, y: page[(y * self.W + x) * 4:][:4]
            for y in (480, 486, 492):                              # design y 960..984: the lower part of the pill (centre 950, half height 44)
                self.assertEqual(pill(165, y), bytes((0x1c, 0x23, 0x21, 255)), "%s: y %d" % (step, y))
            self.assertEqual(pill(165, 499), bytes((11, 14, 13, 255)), "%s: the ground below the pill" % step)
            b.keys("ok")
        b.finish()

    def test_nine_areas_stand_apart(self):
        # every area's pill is whole and touches none of its neighbours: the first and the last one, and the one in the middle
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        for name, centre in (("Picture", 198), ("Sound", 198 + 94 * 4), ("Wi-Fi", 198 + 94 * 8)):
            b = self.box().start(name, size="%dx%d" % (self.W, self.H))
            page = self.snap(b, "a")
            pill = lambda x, y: page[(y * self.W + x) * 4:][:4]
            self.assertEqual(pill(165, centre // 2), bytes((0x1c, 0x23, 0x21, 255)), name)
            self.assertEqual(pill(165, (centre - 44) // 2 + 2), bytes((0x1c, 0x23, 0x21, 255)), "%s: the top of the pill" % name)
            self.assertEqual(pill(165, (centre + 47) // 2 + 1), bytes((11, 14, 13, 255)), "%s: the ground between two areas" % name)
            b.finish()

    def test_the_choice_lists_and_the_hint_stay_inside_too(self):
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        b = self.box().start("Picture", size="%dx%d" % (self.W, self.H))
        b.keys("ok", *["down"] * 5, "ok")                          # the options of Picture mode
        self.assertIn("focus choice", b.dump())
        self.inside(self.ink(self.snap(b, "c"), True), "the options")
        b.keys("back", "down", "ok")                               # Aspect ratio
        self.inside(self.ink(self.snap(b, "c2"), True), "the aspect options")
        b.keys("back")
        b.finish()
        b = self.box().start("Keystone", size="%dx%d" % (self.W, self.H))
        b.keys("ok", "down", "down", "down", "ok")                 # the corners: only the hint over the picture
        self.assertIn("focus corners", b.dump())
        self.inside(self.ink(self.snap(b, "k"), False), "the corner hint")
        b.finish()

    def test_the_page_is_opaque_and_the_pill_alone_over_the_picture(self):
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        b = self.box().start("Picture", size="%dx%d" % (self.W, self.H))
        page = self.snap(b, "p")
        self.assertEqual(page[3::4].count(255), self.W * self.H)                  # every pixel of the page is there
        b.keys("ok", "right")                                       # Brightness: the page shrinks to its pill
        self.assertIn("focus slider", b.dump())
        pill = self.snap(b, "s")
        box = self.ink(pill, False)
        self.inside(box, "the slider pill")
        self.assertGreater(box[1], self.H * 0.75)                                  # at the foot ...
        self.assertEqual(pill[3:self.W * self.H * 2:4].count(255), 0)              # ... and the upper half of the panel is free
        self.assertEqual(sum(1 for a in pill[3::4] if a == 255) > 0, True)         # (the pill's own lines are whole)
        b.keys("ok")                                                # OK: the opaque page is back
        self.assertIn("focus rows", b.dump())
        self.assertEqual(self.snap(b, "q")[3::4].count(255), self.W * self.H)
        b.finish()

    def test_a_slider_judged_on_the_picture_takes_the_page_away_and_the_volume_does_not(self):
        b = self.box().start("Picture")
        b.keys("ok", "right")                                       # Brightness: moved, and the page is only the pill
        d = b.dump()
        self.assertIn("focus slider", d)
        self.assertIn("Brightness slider 55", d)
        b.keys("down", "left", "left")                              # the next slider (Contrast), twice down
        d = b.dump()
        self.assertIn("focus slider row 1", d)
        self.assertIn("Contrast slider 40", d)
        b.keys("up", "right")                                       # back to Brightness: 60
        self.assertIn("Brightness slider 60", b.dump())
        b.keys("back")
        self.assertIn("focus rows row 0", b.dump())
        b.finish()
        b = self.box().start("Sound")
        b.keys("ok", "right")                                       # the volume is not judged on the picture: the page stays
        d = b.dump()
        self.assertIn("focus rows", d)
        self.assertIn("Volume slider 95", d)
        b.finish()

    def test_ok_on_such_a_slider_opens_the_pill_without_moving_it(self):
        b = self.box().start("Picture")
        b.keys("ok", "ok")
        d = b.dump()
        self.assertIn("focus slider", d)
        self.assertIn("Brightness slider 50", d)
        self.assertEqual([x for x in b.tv.log if x.startswith("set ")], [])
        b.keys("ok")
        self.assertIn("focus rows", b.dump())
        b.finish()

    def test_the_turn_pill_stays_inside_the_margin_at_both_ends(self):
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        for key, end in (("right", 40), ("left", 80)):
            b = self.box().start("Keystone", size="%dx%d" % (self.W, self.H))
            b.keys("ok", "down", "down", *[key] * end)
            self.assertIn("focus slider", b.dump())
            self.inside(self.ink(self.snap(b, "t"), False), "the turn pill at %s" % key)
            b.finish()

    def test_the_zoom_is_such_a_slider_too(self):
        b = self.box().start("Keystone")
        b.keys("ok", "down", "down", "down", "down", "left")
        d = b.dump()
        self.assertIn("focus slider", d)
        self.assertIn("Zoom slider 95", d)
        self.assertIn("focus slider row 4", d)
        b.keys("up")                                                # the slider above it is Turn to wall: Up goes there
        self.assertIn("focus slider row 2", b.dump())
        b.keys("up")                                                # and no slider above that one: it stays
        self.assertIn("focus slider row 2", b.dump())
        self.assertEqual(b.warp.zoom, 95)                           # moving between the two changed nothing
        b.finish()


class LookGamma(LookKit):
    """19.10.2026: a page of nine rows (Picture with Gamma) has a narrower pitch, a stop slider has its own pill. Pages of up to eight rows
    are the same as before (the pitch of 94): the pictures of all nine areas were compared byte for byte with the build without the change."""

    PILL = (28, 35, 33, 255)
    GROUND = (11, 14, 13, 255)

    def box(self, **kw):
        b = super().box(**kw)
        b.tv.curves = True
        return b

    def at(self, page, x, y):
        return tuple(page[(y * self.W + x) * 4:][:4])

    def need_font(self):
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")

    def test_nine_rows_take_the_narrow_pitch_and_eight_keep_the_old_one(self):
        self.need_font()
        size = "%dx%d" % (self.W, self.H)
        s = self.W / 1920.0
        b = self.box().start("Picture", size=size)
        b.keys("ok", "down", "down")                                  # the third of nine rows: lit at 202 + 82 * 2
        page = self.snap(b, "nine")
        self.assertEqual(self.at(page, int(1000 * s), int(366 * s)), self.PILL)
        self.assertEqual(self.at(page, int(1000 * s), int(426 * s)), self.GROUND)        # below the pill: the next row is not lit
        b.finish()
        b = self.box().start("Picture", size=size)
        b.keys("ok", *["down"] * 6, "ok", "down", "down")             # the options of Picture mode keep the pitch of 94, whatever the page below had
        page = self.snap(b, "options")
        self.assertEqual(self.at(page, int(1000 * s), int(434 * s)), self.PILL)          # the third option, lit at 202 + 94 * 2, down to 442
        b.finish()
        b = self.box()
        b.tv.curves = False
        b.start("Picture", size=size)
        b.keys("ok", "down", "down")                                  # the third of eight rows: lit at 202 + 94 * 2
        page = self.snap(b, "eight")
        self.assertEqual(self.at(page, int(1000 * s), int(390 * s)), self.PILL)
        self.assertEqual(self.at(page, int(1000 * s), int(366 * s)), self.PILL)          # (the lit pill is 104 px high, down to 442)
        self.assertEqual(self.at(page, int(1000 * s), int(450 * s)), self.GROUND)
        b.finish()

    def test_every_row_of_nine_stays_inside_the_margin_and_above_the_note(self):
        self.need_font()
        b = self.box().start("Picture", size="%dx%d" % (self.W, self.H))
        b.keys("ok")
        for row in range(9):
            page = self.snap(b, "r")
            self.inside(self.ink(page, True), "row %d" % row)
            # the last row's pill (centre 860) ends before the note's text begins (its first line is at 922, 26 px high)
            if row == 8:
                self.assertEqual(self.at(page, 300, int(905 * self.W / 1920.0)), self.GROUND)
            b.keys("down")
        b.finish()

    def test_a_longer_page_and_a_shorter_one_leave_nothing_of_each_other(self):
        self.need_font()
        size = "%dx%d" % (self.W, self.H)
        fresh = {}
        for area in ("Picture", "White balance", "Colour", "Sound"):
            b = self.box().start(area, size=size)
            fresh[area] = self.snap(b, "fresh")
            b.finish()
        b = self.box().start("Picture", size=size)                    # nine rows, then the areas below it
        b.keys("ok", *["down"] * 8, "back")
        for step, area in enumerate(("White balance", "Colour"), 1):
            b.keys("down")
            self.assertEqual(self.snap(b, "after"), fresh[area], "%s after Picture" % area)
        b.keys("down", "down")                                          # Keystone, Sound
        self.assertEqual(self.snap(b, "sound"), fresh["Sound"], "Sound after Picture")
        b.keys("up", "up", "up", "up")                                  # and back up to Picture, nine rows again
        self.assertEqual(self.snap(b, "back"), fresh["Picture"], "Picture after the shorter ones")
        b.finish()

    def test_the_stop_pill_stays_inside_the_margin_and_the_pill(self):
        self.need_font()
        s = self.W / 1920.0
        for area, steps in (("Picture", ["ok"] + ["down"] * 5), ("White balance", ["ok"])):
            for stop in range(5 if area == "Picture" else 4):
                b = self.box()
                b.tv.preset = "cinema"
                b.start(area, size="%dx%d" % (self.W, self.H))
                b.keys(*steps, "ok")                                    # the pill, on the stop the tool holds (Gamma 2.2, Auto)
                if stop:
                    b.hold("right", stop)                               # held: all the way to the stop, one command
                self.assertIn("focus slider", b.dump())
                box = self.ink(self.snap(b, "pill"), False)
                self.inside(box, "%s stop %d" % (area, stop))
                self.assertGreaterEqual(box[0], int(452 * s) - 1, "%s stop %d: the pill's left edge" % (area, stop))
                self.assertLessEqual(box[2], int(1468 * s) + 1, "%s stop %d: the pill's right edge" % (area, stop))
                self.assertGreaterEqual(box[1], int(780 * s), "%s stop %d: the pill stays at the foot" % (area, stop))
                b.finish()

    def test_the_pill_names_its_stops_under_the_track(self):
        self.need_font()
        s = self.W / 1920.0
        for area, keys, track in (("Picture", ["ok"] + ["down"] * 5 + ["ok"], 862), ("White balance", ["ok", "ok"], 832)):    # the track's y in the design
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            b.keys(*keys)
            page = self.snap(b, "names")
            bright = sum(1 for y in range(int((track + 24) * s), int((track + 48) * s)) for x in range(int(870 * s), int(1210 * s))
                         if self.at(page, x, y)[0] > 200 and self.at(page, x, y)[3] > 200)
            self.assertGreater(bright, 5, "%s: the words of the stops" % area)
            b.finish()

    def test_a_long_sentence_makes_the_pill_two_lines_and_taller(self):
        self.need_font()
        tops = {}
        for name, area, keys in (("gamma", "Picture", ["ok"] + ["down"] * 5 + ["ok"]), ("ctemp", "White balance", ["ok", "ok"])):
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            b.keys(*keys)
            tops[name] = self.ink(self.snap(b, name), False)[1]
            b.finish()
        self.assertLess(tops["ctemp"], tops["gamma"] - 10)             # Auto's sentence is two lines: the pill grows upwards, by 30 design px

    def test_the_stop_pills_report_all_they_changed(self):
        # h713-osd puts the columns of a "page show" only: a pixel changed outside the reported pieces is stale on the wall
        self.need_font()
        walk = ["ok", "down", "right", "left", "up", "ok", "down", "ok", "back", "down", "right", "right", "left", "ok", "up", "back"]
        for area in ("Picture", "White balance"):
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            for key in walk + ["down"] * 5 + ["right", "left", "up", "ok", "down", "ok", "up", "up", "back"]:
                if key == "back" and "focus areas" in b.dump().splitlines()[0]:
                    continue
                b.keys(key)
            dump = b.dump().splitlines()
            self.assertIn("outside 0", dump, "%s: %s" % (area, dump[:1]))
            b.finish()

    def test_the_stops_row_is_drawn_the_same_again(self):
        self.need_font()
        for area, down in (("Picture", 5), ("White balance", 0)):
            b = self.box().start(area, size="%dx%d" % (self.W, self.H))
            b.keys("ok", *["down"] * down)
            first = self.snap(b, "first")
            b.keys("down", "up")
            self.assertEqual(self.snap(b, "again"), first, area)
            b.finish()


OSD_DIR = os.path.join(HERE, "..", "..", "h713-osd")
OSD_BIN = os.path.join(OSD_DIR, "h713-osd")


class StackBase(Base):
    """h713-settings, the real h713-osd and a fake h713-tv (the one of h713-osd's own tests): the page as the wall gets it."""
    SIZE = None                                                  # the fake panel: h713-osd's tests' own, or the box's (Wall)

    def setUp(self):
        sys.path.insert(0, os.path.join(OSD_DIR, "tests"))
        import test_osd
        self.W, self.H = self.SIZE or (test_osd.W, test_osd.H)
        self.PITCH = self.W * 4
        self.dir = tempfile.mkdtemp(prefix="h713-stack-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.osd_tv = test_osd.FakeTv(os.path.join(self.dir, "wall.sock"), size=(self.W, self.H))
        self.osd_tv.start()
        self.addCleanup(self.osd_tv.stop)
        self.osd_sock = os.path.join(self.dir, "osd.sock")
        self.daemon = None
        self.addCleanup(self.stop_daemon)

    def start_daemon(self):
        self.osd_env = env = dict(os.environ, H713_OSD_SOCKET=self.osd_sock, H713_OSD_TV=os.path.join(self.dir, "wall.sock"),
                                  H713_OSD_WARP_CONF=os.path.join(self.dir, "warp.conf"), H713_OSD_CONF=os.path.join(self.dir, "osd.conf"),
                                  H713_OSD_FONT=[f for f in FONTS if f and os.path.exists(f)][0], H713_OSD_CLOCK="07:52")
        self.daemon = subprocess.Popen([OSD_BIN, "run"], env=env, stderr=subprocess.PIPE)
        self.assertTrue(wait_for(lambda: os.path.exists(self.osd_sock), 5))

    def stop_daemon(self):
        if self.daemon:
            self.daemon.terminate()
            self.daemon.wait(5)
            self.daemon.stderr.close()
            self.daemon = None

    def shown(self):
        return None if self.osd_tv.shown is None else os.pread(self.osd_tv.bufs[self.osd_tv.shown], self.PITCH * self.H, 0)


@unittest.skipUnless(os.path.exists(OSD_BIN) and any(f and os.path.exists(f) for f in FONTS),
                     "needs the real h713-osd (make -C ../h713-osd host) and a font")
class Stack(StackBase):
    def test_the_page_is_on_the_wall_and_follows_the_keys(self):
        self.start_daemon()
        b = self.box().start_device("Picture", osd_socket=self.osd_sock)
        self.assertTrue(wait_for(lambda: self.shown() is not None, 8))
        time.sleep(0.3)
        page = self.shown()
        a = lambda x, y: page[(y * self.W + x) * 4 + 3]
        self.assertEqual(a(3, 3), 255)                           # the opaque ground reaches every corner
        self.assertEqual(a(self.W - 4, self.H - 4), 255)
        self.assertEqual(page[(int(198 / 3) * self.W + int(450 / 3)) * 4:][:4], bytes((0x21, 0x23, 0x1c, 255)))   # the pill of the open area
        b.press(OK)                                              # into the rows: the first row is lit
        time.sleep(0.8)
        page = self.shown()
        b.press(RIGHT)                                           # Brightness 55: the page shrinks to the one pill over the picture
        self.assertTrue(wait_for(lambda: b.tv.c["brightness"] == 55, 5))
        time.sleep(0.8)
        pill = self.shown()
        alpha = pill[3::4]
        rows = [y for y in range(self.H) if any(alpha[y * self.W:(y + 1) * self.W])]
        self.assertTrue(rows and min(rows) > self.H * 0.75, (min(rows), max(rows)))     # nothing but the pill at the foot: the picture is free
        b.press(OK)                                              # and OK brings the page back, opaque
        time.sleep(0.8)
        again = self.shown()
        self.assertEqual(again[3::4].count(255), self.W * self.H)
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 10)
        self.assertTrue(wait_for(lambda: self.osd_tv.shown is None, 5))      # the end of the page takes it from the wall

    def test_the_page_through_a_keystone(self):
        with open(os.path.join(self.dir, "warp.conf"), "w") as f:
            f.write("bl_x = 90\nbl_y = 60\nbr_x = 90\nbr_y = 60\nwarp = on\n")
        self.osd_tv.picture = "warped"
        self.start_daemon()
        b = self.box().start_device("Sound", osd_socket=self.osd_sock)
        self.assertTrue(wait_for(lambda: self.shown() is not None, 8))
        time.sleep(0.3)
        page = self.shown()
        a = lambda x, y: page[(y * self.W + x) * 4 + 3]
        self.assertEqual(a(self.W // 2, 3), 255)                 # the top edge is whole
        self.assertEqual(a(2, self.H - 4), 0)                    # the pulled-in bottom corner is not: it went through the matrix
        b.press(HOME)
        b.proc.wait(timeout=5)


@unittest.skipUnless(os.path.exists(OSD_BIN) and any(f and os.path.exists(f) for f in FONTS),
                     "needs the real h713-osd (make -C ../h713-osd host) and a font")
class Wall(StackBase):
    """The box's panel through the HY310's keystone of 19.10.2026, turned about 24 degrees to the wall (h713-warp ctl status)."""
    SIZE = (1920, 1080)
    ROWS = "hdmi:HDMI input;film:Kodi;globe:Browser;desk:Desktop;sliders:Settings;>power:Standby"

    def launcher(self, words):
        """what h713-keys says to h713-osd: the launcher opened (with its entries), a move, a close"""
        r = subprocess.run([OSD_BIN, "ctl", "launcher"] + words.split(), env=self.osd_env, capture_output=True, text=True, timeout=5)
        self.assertTrue(r.stdout.startswith("ok"), r.stdout + r.stderr)
        time.sleep(0.4)                                          # the refresh, and the idle time's fill of the other buffer

    def test_back_to_the_launcher_and_its_moves_leave_no_hole(self):
        """19.10.2026: in the launcher after the settings page every second key put two of its tiles on the wall and left the rest
        transparent - the ground on the right pitch black. Each move must stand on the wall as the launcher put whole does."""
        with open(os.path.join(self.dir, "warp.conf"), "w") as f:
            f.write("tl_x = 65\ntl_y = 0\ntr_x = 199\ntr_y = 244\nbl_x = 12\nbl_y = 0\nbr_x = 187\nbr_y = 81\nwarp = on\n")
        self.osd_tv.picture = "warped"
        self.start_daemon()
        self.launcher("4;HDMI 1080p60;" + self.ROWS)
        self.launcher("close keep")                              # OK on Settings: the launcher stays until the page is drawn
        b = self.box().start_device("Picture", osd_socket=self.osd_sock)
        status = lambda: subprocess.run([OSD_BIN, "ctl", "status"], env=self.osd_env, capture_output=True, text=True, timeout=5).stdout
        self.assertTrue(wait_for(lambda: "page            open (opaque" in status(), 8))
        time.sleep(0.5)
        b.press(DOWN)                                            # another area, and back
        time.sleep(0.5)
        b.press(UP)
        time.sleep(0.5)
        b.press(BACK)                                            # Back at the top: the page hands the wall over
        self.assertEqual(b.proc.wait(timeout=5), 0)
        self.launcher("4;HDMI 1080p60;" + self.ROWS)             # h713-keys: the launcher again, Settings chosen
        shots = []
        for sel in (5, 4, 3, 2):
            self.launcher(str(sel))
            shots.append((sel, self.shown()))
        bad = []
        for sel, shot in shots:
            self.launcher("%d;HDMI 1080p60;%s" % (sel, self.ROWS))   # the same launcher put whole
            whole = self.shown()
            holes = sum(1 for i in range(3, len(whole), 4 * 7) if whole[i] == 255 and shot[i] != 255)   # every 7th pixel
            if holes or shot != whole:
                bad.append("move to %d: %d holes in every 7th pixel, %s" % (sel, holes, "the same" if shot == whole else "not the whole put"))
        self.assertEqual(bad, [])


class Render(Base):
    def read_pam(self, path):
        with open(path, "rb") as f:
            head = b""
            while not head.endswith(b"ENDHDR\n"):
                head += f.readline()
            w = int([l for l in head.split(b"\n") if l.startswith(b"WIDTH")][0].split()[1])
            h = int([l for l in head.split(b"\n") if l.startswith(b"HEIGHT")][0].split()[1])
            return w, h, f.read()

    def px(self, img, x, y):
        w, h, data = img
        o = (y * w + x) * 4
        return tuple(data[o:o + 4])

    def test_the_page_is_drawn_where_the_mockup_has_it(self):
        if not any(f and os.path.exists(f) for f in FONTS):
            self.skipTest("no font")
        b = self.box().start("Picture", size="960x540")
        b.keys("ok")
        b.dump()
        path = os.path.join(b.dir, "page.pam")
        b.keys("snap " + path)
        b.dump()
        img = self.read_pam(path)
        b.finish()
        s = 0.5                                              # 960 / 1920
        self.assertEqual(self.px(img, 5, 5), (11, 14, 13, 255))                    # the opaque ground
        self.assertEqual(self.px(img, int(1000 * s), int(202 * s)), (28, 35, 33, 255))   # the lit pill of the selected row
        edge = [self.px(img, x, int(202 * s)) for x in range(int(700 * s) - 1, int(700 * s) + 3)]
        self.assertTrue(any(min(p) >= 250 for p in edge), edge)                    # its outline, white and whole
        self.assertEqual(self.px(img, int(1000 * s), int(296 * s)), (11, 14, 13, 255))   # no pill under the next row
        self.assertEqual(self.px(img, int(450 * s), int(198 * s)), (28, 35, 33, 255))    # the area pill
        # the slider: lit up to 50 % of 540 px, dim beyond
        self.assertEqual(self.px(img, int((1110 + 100) * s), int(202 * s))[:3], (255, 255, 255))
        lit = self.px(img, int((1110 + 400) * s), int(202 * s))
        self.assertLess(lit[0] * lit[3], 255 * 255)


if __name__ == "__main__":
    unittest.main()
