"""Host tests for h713-settings: a fake h713-tv and a fake h713-warp on Unix sockets (their answers copied from the real
daemons' source: "ok ..." / "error ...", one line in, one answer, hang up), stand-in tools in a directory, and a
temporary /etc/h713. The program runs with --test: keys as lines on stdin, "dump" prints the model, "snap FILE" the
canvas. What a row sends to a tool is read from the fakes' logs; what it keeps for the next boot, from the files.

python3 -m unittest discover -s tests -v   (from userspace/h713-settings, after `make host OSD=...`)
"""

import os
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
        super().__init__(path)

    def answer(self, line):
        w = line.split()
        if w[0] == "list":
            rows = "".join("  %-26s %d  (0..100)\n" % (k, v) for k, v in self.c.items())
            return "ok controls\n" + rows + "  mode                       1 (standard)  menu 0..5\n"
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
            return "ok status\nmode            auto\npreset          %s (from the device data)\nsaved           nothing\n" % self.preset
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
    "h713-keystone": 'echo "$@" >> "$LOG/keystone.log"; sleep "${JOBTIME:-0.3}"; exit "${JOBEXIT:-0}"\n',
    "h713-autofocus": 'echo "$@" >> "$LOG/autofocus.log"; sleep "${JOBTIME:-0.3}"; exit "${JOBEXIT:-0}"\n',
    "h713-focus": 'echo "$@" >> "$LOG/focus.log"; sleep 0.2\n',
    "systemctl": 'echo "$@" >> "$LOG/systemctl.log"\n',
    "iw": 'printf "Connected to aa:bb:cc:dd:ee:ff (on wlan0)\\n\\tSSID: Wohnzimmer\\n\\tfreq: 2437\\n\\tsignal: -52 dBm\\n"\n',
    "ip": 'echo "wlan0            UP             192.168.8.131/24"\n',
}


class Box:
    """The tools, the files and the program, in one temporary directory."""

    def __init__(self, features="all", standby="offered in the countdown", wifi_mode="sta", extra_env=None):
        self.dir = tempfile.mkdtemp(prefix="h713-settings-")
        self.etc = os.path.join(self.dir, "etc")
        self.bin = os.path.join(self.dir, "bin")
        self.log = os.path.join(self.dir, "log")
        for d in (self.etc, self.bin, self.log):
            os.mkdir(d)
        for name, body in TOOLS.items():
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n" + body)
            os.chmod(path, 0o755)
        present = "present  /dev/x  (stand-in)"
        absent = "not present on this board"
        have = lambda on: present if features in ("all", on) else absent
        self.env = dict(os.environ, H713_SETTINGS_ETC=self.etc, H713_SETTINGS_BIN=self.bin, LOG=self.log, ETC=self.etc,
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
        b.keys("ok", "down", "down", "ok")                 # Adjust corners by hand: top left, the mask on
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
        b.keys("ok", "down", "down", "ok")
        b.dump()
        self.assertEqual(b.warp.pattern, "tl")
        b.finish()
        self.assertIsNone(b.warp.pattern)

    def test_zoom_projection_reset(self):
        b = self.box().start("Keystone")
        b.keys("ok", "down", "down", "down", "left", "left")        # Zoom 100 -> 90
        d = b.dump()
        self.assertIn("Zoom slider 90 50..100", d)
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
        self.assertNotIn("(hidden) Zoom", d)               # these need the warp, not the sensor
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
        self.assertEqual(b.tool_log("autofocus"), ["run -q"])
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
    def test_source_choice_is_sent_and_kept(self):
        b = self.box().start("Input")
        b.keys("ok", "ok", "up", "ok")                        # Source > Automatic (it stands on HDMI only)
        d = b.dump()
        self.assertEqual(b.tv.source, "auto")
        self.assertIn("source = auto", b.read("tv.conf"))     # h713-tv reads this as the start value
        self.assertIn("Source choice [*Automatic|HDMI only]", d)
        b.keys("ok", "ok")                                    # the same again: nothing is sent, nothing written
        b.dump()
        self.assertEqual([x for x in b.tv.log if x.startswith("source ")], ["source auto"])
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
        b.keys(*["down"] * 6)
        self.assertIn("area Wi-Fi", b.dump())
        b.keys("back")
        self.assertEqual(b.proc.wait(timeout=5), 0)


# the kernel's key codes, as h713-keys reads them
UP, DOWN, LEFT, RIGHT, OK, SELECT, BACK, HOME, POWER = 103, 108, 105, 106, 352, 353, 158, 172, 116
VOLUP, VOLDOWN, MUTE, F4, F5 = 115, 114, 113, 62, 63


@unittest.skipUnless(any(f and os.path.exists(f) for f in FONTS), "no font (set H713_TEST_FONT)")
class Device(Base):
    def test_opens_on_the_wall_first_then_takes_the_remote(self):
        b = self.box().start_device("Sound")
        self.assertTrue(wait_for(lambda: any(l.startswith("page show") for l in b.osd.log), 5))
        self.assertEqual(b.osd.log[0], "page open")
        self.assertEqual(b.osd.log[1], "page show 0 0 %d %d" % (b.osd.W, b.osd.H))     # the whole page once
        self.assertEqual(b.osd.pixel(3, 3) >> 24, 128)                                  # the dimmed ground is in the canvas
        b.press(BACK)
        self.assertEqual(b.proc.wait(timeout=5), 0)
        self.assertTrue(wait_for(lambda: b.osd.closed))                                 # the connection ends: the page is gone

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

    def test_both_devices_are_read(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(OK, device=1)                                    # (two devices have no order between them: let one finish)
        time.sleep(0.3)
        b.press(RIGHT, device=0)
        self.assertTrue(wait_for(lambda: b.tv.volume == 95, 5))
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 0)

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
        self.assertEqual(b.proc.wait(timeout=5), 0)
        self.assertFalse(b.tv.mute)

    def test_power_is_handed_to_h713_power(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.press(POWER)
        self.assertEqual(b.power.recv(32), b"short")
        self.assertEqual(b.proc.wait(timeout=5), 0)
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
        self.assertEqual(b.proc.wait(timeout=8), 0)
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
        self.assertEqual(b.proc.wait(timeout=5), 0)

    def test_closes_when_h713_osd_is_gone(self):
        b = self.box().start_device("Sound")
        wait_for(lambda: len(b.osd.log) > 1)
        b.osd.drop()
        b.press(OK)                                              # the next drawing finds nobody
        self.assertEqual(b.proc.wait(timeout=5), 0)              # the page is closed and the remote is given back
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
        self.assertEqual(b.proc.wait(timeout=8), 0)
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
        self.assertRegex(err, r"drawn [\d.]+ ms \(640x360 px\), shown [\d.]+ ms\n")                 # the first, whole page: no key
        self.assertRegex(err, r"drawn [\d.]+ ms \(\d+x\d+ px\), shown [\d.]+ ms, key to answer [\d.]+ ms")

    def test_a_key_keeps_it_open(self):
        b = self.box().start_device("Sound", idle=2)
        for _ in range(4):
            time.sleep(0.8)
            b.press(DOWN)                                        # nothing to do in the areas but it counts as a key
        self.assertIsNone(b.proc.poll())
        b.press(HOME)
        b.proc.wait(timeout=5)


OSD_DIR = os.path.join(HERE, "..", "..", "h713-osd")
OSD_BIN = os.path.join(OSD_DIR, "h713-osd")


@unittest.skipUnless(os.path.exists(OSD_BIN) and any(f and os.path.exists(f) for f in FONTS),
                     "needs the real h713-osd (make -C ../h713-osd host) and a font")
class Stack(Base):
    """h713-settings, the real h713-osd and a fake h713-tv (the one of h713-osd's own tests): the page as the wall gets it."""

    def setUp(self):
        sys.path.insert(0, os.path.join(OSD_DIR, "tests"))
        import test_osd
        self.W, self.H, self.PITCH = test_osd.W, test_osd.H, test_osd.PITCH
        self.dir = tempfile.mkdtemp(prefix="h713-stack-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.osd_tv = test_osd.FakeTv(os.path.join(self.dir, "wall.sock"))
        self.osd_tv.start()
        self.addCleanup(self.osd_tv.stop)
        self.osd_sock = os.path.join(self.dir, "osd.sock")
        self.daemon = None
        self.addCleanup(self.stop_daemon)

    def start_daemon(self):
        env = dict(os.environ, H713_OSD_SOCKET=self.osd_sock, H713_OSD_TV=os.path.join(self.dir, "wall.sock"),
                   H713_OSD_WARP_CONF=os.path.join(self.dir, "warp.conf"), H713_OSD_CONF=os.path.join(self.dir, "osd.conf"),
                   H713_OSD_FONT=[f for f in FONTS if f and os.path.exists(f)][0])
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

    def test_the_page_is_on_the_wall_and_follows_the_keys(self):
        self.start_daemon()
        b = self.box().start_device("Picture", osd_socket=self.osd_sock)
        self.assertTrue(wait_for(lambda: self.shown() is not None, 8))
        time.sleep(0.3)
        page = self.shown()
        a = lambda x, y: page[(y * self.W + x) * 4 + 3]
        self.assertEqual(a(3, 3), 128)                           # the dimmed ground reaches every corner
        self.assertEqual(a(self.W - 4, self.H - 4), 128)
        self.assertGreater(a(int(331 / 3), int(198 / 3)), 150)   # the pill of the open area, at the mockup's place (u = 1/3)
        b.press(OK)                                              # into the rows: the first row is lit
        time.sleep(0.8)
        page = self.shown()
        b.press(RIGHT)                                           # Brightness 55: its slider grows
        self.assertTrue(wait_for(lambda: b.tv.c["brightness"] == 55, 5))
        time.sleep(0.5)
        after = self.shown()
        self.assertNotEqual(after, page)
        row = int(202 / 3)                                       # only the rows of the slider's row differ
        changed = [y for y in range(self.H) if after[y * self.PITCH:(y + 1) * self.PITCH] != page[y * self.PITCH:(y + 1) * self.PITCH]]
        self.assertTrue(changed and min(changed) >= row - 25 and max(changed) <= row + 25, (min(changed), max(changed)))
        b.press(HOME)
        self.assertEqual(b.proc.wait(timeout=5), 0)
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
        self.assertEqual(a(self.W // 2, 3), 128)                 # the top edge is whole
        self.assertEqual(a(2, self.H - 4), 0)                    # the pulled-in bottom corner is not: it went through the matrix
        b.press(HOME)
        b.proc.wait(timeout=5)


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
        self.assertEqual(self.px(img, 5, 5), (0, 0, 0, 128))                       # the dimmed ground
        self.assertGreater(self.px(img, int(1260 * s), int(202 * s))[3], 150)      # the pill of the selected row
        edge = [self.px(img, x, int(202 * s)) for x in range(int(700 * s) - 1, int(700 * s) + 3)]
        self.assertTrue(any(min(p) >= 250 for p in edge), edge)                    # its outline, white and whole
        self.assertEqual(self.px(img, int(1000 * s), int(296 * s))[3], 128)        # no pill under the next row
        self.assertGreater(self.px(img, int(331 * s), int(198 * s))[3], 150)       # the area pill
        # the slider: lit up to 50 % of 540 px, dim beyond
        self.assertEqual(self.px(img, int((1110 + 100) * s), int(202 * s))[:3], (255, 255, 255))
        lit = self.px(img, int((1110 + 400) * s), int(202 * s))
        self.assertLess(lit[0] * lit[3], 255 * 255)


if __name__ == "__main__":
    unittest.main()
