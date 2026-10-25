#!/usr/bin/env python3
"""Tests for h713-panel.  No device and no projector: the five tools and
systemctl are shell scripts in a temporary directory that log their argument
vector and print a canned answer, which is exactly what the tool is allowed to
see of them.

    python3 -m unittest discover -s tests -v          # from h713-panel/
    python3 -m unittest                               # from work/KS7/

What is tested is the layer this package adds: the verb table (every button is
one command, with the words in the right order), the range checks, that an
unknown verb and an argument that is not in its range are refused before a
process is started, the status parsing against recorded status output, the
after_move writer against a configuration file with comments, and the page
itself - every verb page.html uses has to exist in the tool.
"""

import base64
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.dirname(HERE)
TOOL = os.path.join(os.path.dirname(HERE), "h713-panel")
PAGE = os.path.join(os.path.dirname(HERE), "page.html")
POSIX = os.name == "posix"


def _load(name, path):
    """Import a file without a .py name, the way the tools are installed."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


panel = _load("h713_panel", TOOL)

# Recorded output of the three statuses the page reads (h713-warp loop.c
# warp_status, h713-tv main.c cmd_status, h713-keystone do_status).
WARP_STATUS = """ok status
warp            on
keystone        tl 120,40 tr 0,0 bl 0,0 br 30,0 (per-mille, positive inward)
zoom            85 percent (smaller about its centre, inside the keystone)
mode            rear-ceiling (mirrored for the mount; the GPU runs even at the identity)
pattern         mask (a corner marked)
source          /dev/video1 1920x1080, line pitch 1920/1920, 1 dma-buf per slot
panel           1920x1080, line pitch 7680, three buffers from /run/h713-tv/ctl
renderer        Mali-G31 (Panfrost)
frames          1800 at 59.4 fps, dropped 0, commits 1800, busy 3, link errors 0
timing          last frame 1.2 ms, worst 4.0 ms (DQBUF to the answer)
config          /etc/h713/warp.conf, start off"""

TV_STATUS = """ok status
mode            automatic
signal          1920x1080p60, 148.5 MHz (last measured)
picture         warped (h713-warp draws on the primary plane)
format          16:9 (aspect 3)
zoom            off
audio           loud (auto), 48000 Hz, volume 62, trim 0 dB"""

TV_LIST = """ok controls
  brightness                 50  (0..100)
  contrast                   48  (0..100)
  saturation                 50  (0..100)
  hue                         0  (-50..50)
  sharpness                   7  (0..15)
  mode                        0 (standard)  menu 0..5"""

KEYSTONE_STATUS = """ok status
config          /etc/h713/keystone.conf
optics          throw ratio 0.8176 (camprjspe.ini), zoom_scale 0
after a move    keystone+focus (more than 3.0 degrees, then 2.0 s still)
reference       file (2026-09-26T10:12:44): /etc/h713/keystone-ref, counts -416 2752 17088
warp            tl 120,40 tr 0,0 bl 0,0 br 30,0
keystone by     manual"""

# The same status on a fresh image (FB-KSREF, 26.09.2026): no reference file,
# the automatic corrects against the ideal level pose.
KEYSTONE_STATUS_IDEAL = KEYSTONE_STATUS.replace(
    "file (2026-09-26T10:12:44): /etc/h713/keystone-ref, counts -416 2752 17088",
    "ideal (0, 0, 1 g) - h713-keystone reference refines it")
KEYSTONE_STATUS_REFUSED = KEYSTONE_STATUS.replace(
    "file (2026-09-26T10:12:44): /etc/h713/keystone-ref, counts -416 2752 17088",
    "refused (/etc/h713/keystone-ref was taken with axis_roll = +x, the "
    "configuration says -x -- run `h713-keystone reference` again)")
# The same refusal as a tool without FB-KSREFb prints it: the raised message
# itself.  A first word the page does not know is "refused" as well.
KEYSTONE_STATUS_REFUSED_OLD = KEYSTONE_STATUS.replace(
    "file (2026-09-26T10:12:44): /etc/h713/keystone-ref, counts -416 2752 17088",
    "/etc/h713/keystone-ref was taken with axis_roll = +x, the configuration "
    "says -x -- run `h713-keystone reference` again")

# h713-features status on the HY300PRO-G-EU: the accelerometer and nothing else.
GEU_FEATURES = """ok features  board hy200-qz713df-a1, FEATURES: accelerometer (/etc/h713/features)
camera          not present on this board
accelerometer   present  iio:device0 (sc7a20)  (h713-keystone, h713-keystone-auto)
focus-motor     not present on this board"""


class Fakes(object):
    """A bin directory of shell scripts: one line per call in calls.log."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="h713-panel-")
        self.log = os.path.join(self.dir, "calls.log")

    def tool(self, name, cases=None, code=0):
        lines = ["#!/bin/sh", 'echo "%s $*" >> "%s"' % (name, self.log),
                 'case "$*" in']
        for match, output in sorted((cases or {}).items()):
            lines.append('  "%s")\ncat <<\'END\'\n%s\nEND\n  ;;' % (match, output))
        lines += ['  *) echo "ok %s $*" ;;' % name, "esac", "exit %d" % code]
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(("\n".join(lines) + "\n").encode("utf-8"))
        os.chmod(path, stat.S_IRWXU)
        return path

    def script(self, name, body):
        """A tool with its own logic: `body` is shell, its calls are logged too."""
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(("#!/bin/sh\necho \"%s $*\" >> \"%s\"\n%s\n" % (name, self.log, body)).encode("utf-8"))
        os.chmod(path, stat.S_IRWXU)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, "rb") as handle:
            return handle.read().decode("utf-8").splitlines()

    def forget(self):
        if os.path.exists(self.log):
            os.remove(self.log)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


@unittest.skipUnless(POSIX, "the fake tools are /bin/sh scripts")
class VerbTest(unittest.TestCase):
    """Every button is one command, and nothing else can be asked for."""

    def setUp(self):
        self.fake = Fakes()
        self.fake.tool("h713-warp", {"ctl status": WARP_STATUS})
        self.fake.tool("h713-tv", {"ctl status": TV_STATUS, "ctl status brief": TV_STATUS, "ctl list": TV_LIST})
        self.fake.tool("h713-keystone", {"status": KEYSTONE_STATUS})
        self.fake.tool("h713-focus")
        self.fake.tool("h713-autofocus")
        self.fake.tool("systemctl")
        self.conf = os.path.join(self.fake.dir, "keystone.conf")
        self.panel = panel.Panel(tools=self.fake.dir, keystone_conf=self.conf,
                                 thermal=os.path.join(self.fake.dir, "thermal"))

    def tearDown(self):
        self.fake.close()

    def call(self, verb, args=None):
        return self.panel.call({"verb": verb, "args": args or []})

    def test_projection_verbs(self):
        for verb, args, expected in (
                ("mask_on", ["tl"], "h713-warp ctl test mask tl"),
                ("mask_off", [], "h713-warp ctl test off"),
                ("nudge", ["br", "y", -10],
                 "h713-warp ctl keystone nudge br y -10"),
                ("nudge", ["tl", "x", 50], "h713-warp ctl keystone nudge tl x 50"),
                ("keystone_set", ["bl", "y", 640],
                 "h713-warp ctl keystone set bl y 640"),
                ("keystone_now", [], "h713-keystone once --apply"),
                ("keystone_ref", [], "h713-keystone reference"),
                ("keystone_res", [], "h713-warp ctl keystone reset"),
                ("mode", ["ceiling"], "h713-warp ctl mode ceiling"),
                ("mode", ["rear-ceiling"], "h713-warp ctl mode rear-ceiling"),
                ("focus", ["up", "20"], "h713-focus up 20"),
                ("autofocus", [], "h713-autofocus run"),
                ("warp", ["off"], "h713-warp ctl off")):
            self.fake.forget()
            answer = self.call(verb, args)
            self.assertTrue(answer["ok"], answer)
            self.assertEqual(self.fake.calls(), [expected])

    def test_the_zoom_slider_turns_the_warp_on(self):
        # warp on: the zoom and a look at the status, nothing switched
        self.assertTrue(self.call("screen_zoom", [85])["ok"])
        self.assertEqual(self.fake.calls(), ["h713-warp ctl zoom 85",
                                             "h713-warp ctl status"])
        # 100 leaves the warp as it is, whatever it is
        self.fake.forget()
        self.assertTrue(self.call("screen_zoom", [100])["ok"])
        self.assertEqual(self.fake.calls(), ["h713-warp ctl zoom 100"])
        # warp off: below 100 it is switched on, the GPU being the only way down
        self.fake.tool("h713-warp", {"ctl status": WARP_STATUS.replace(
            "warp            on", "warp            off -- ctl off")})
        self.fake.forget()
        answer = self.call("screen_zoom", [70])
        self.assertTrue(answer["ok"], answer)
        self.assertIn("the warp is on for it", answer["line"])
        self.assertEqual(self.fake.calls(), ["h713-warp ctl zoom 70",
                                             "h713-warp ctl status",
                                             "h713-warp ctl on"])

    def test_picture_and_sound_verbs(self):
        for verb, args, expected in (
                ("preset", ["cinema"], "h713-tv ctl preset cinema"),
                ("aspect", ["16:9"], "h713-tv ctl aspect 16:9"),
                ("save", [], "h713-tv ctl save"),
                ("volume", [42], "h713-tv ctl volume 42"),
                ("mute", ["on"], "h713-tv ctl mute on"),
                ("audio", ["auto"], "h713-tv ctl audio auto")):
            self.fake.forget()
            answer = self.call(verb, args)
            self.assertTrue(answer["ok"], answer)
            self.assertEqual(self.fake.calls(), [expected])

    def test_picture_set_uses_the_range_of_ctl_list(self):
        self.assertTrue(self.call("picture_set", ["hue", -50])["ok"])
        self.assertIn("h713-tv ctl set hue -50", self.fake.calls())
        self.fake.forget()
        # 40 is inside 0..100 but outside sharpness' own 0..15
        answer = self.call("picture_set", ["sharpness", 40])
        self.assertFalse(answer["ok"])
        self.assertIn("0..15", answer["line"])
        self.assertEqual(self.fake.calls(), [])

    def test_a_refused_argument_starts_no_process(self):
        for verb, args in (("mask_on", ["tl; reboot"]),
                           ("nudge", ["tl", "x", 500]),
                           ("nudge", ["tl", "x", 7]),
                           ("nudge", ["tl", "z", 10]),
                           ("keystone_set", ["tl", "x", 1001]),
                           ("keystone_set", ["tl", "x", -1]),
                           ("keystone_set", ["tl", "x", "500; reboot"]),
                           ("screen_zoom", [83]),
                           ("screen_zoom", [10]),
                           ("screen_zoom", ["85; reboot"]),
                           ("mode", ["upside-down"]),
                           ("mode", ["hv"]),
                           ("mode", ["front; reboot"]),
                           ("volume", [101]),
                           ("volume", [True]),
                           ("focus", ["up", "7"]),
                           ("preset", ["$(id)"]),
                           ("after_move", ["keystone; reboot"]),
                           ("picture_set", ["gamma", 5])):
            answer = self.call(verb, args)
            self.assertFalse(answer["ok"], (verb, args, answer))
            self.assertTrue(answer["line"].startswith("error"), answer)
        self.assertEqual(self.fake.calls(), [])

    def test_unknown_verbs_and_shapes_are_refused(self):
        for request in ({"verb": "rpc"}, {"verb": "run"}, {"verb": "focus_command"},
                        {"verb": "ssh_keys"}, {"verb": "do_status"}, {"verb": None},
                        {"verb": "warp", "args": "on"},
                        {"verb": "warp", "args": [1, 2, 3, 4, 5]},
                        ["warp", "on"], "warp"):
            answer = self.panel.call(request)
            self.assertFalse(answer["ok"], request)
            self.assertTrue(answer["line"].startswith("error"), answer)
        self.assertEqual(self.fake.calls(), [])
        self.assertFalse(self.call("warp", [])["ok"])       # too few arguments

    def test_status_is_read_out_of_the_three_tools(self):
        thermal = os.path.join(self.fake.dir, "thermal")
        for zone, kind, milli in (("thermal_zone0", "cpu-thermal", "54321"),
                                  ("thermal_zone1", "gpu-thermal", "58000")):
            os.makedirs(os.path.join(thermal, zone))
            for name, text in (("type", kind), ("temp", milli)):
                with open(os.path.join(thermal, zone, name), "wb") as handle:
                    handle.write((text + "\n").encode("utf-8"))
        state = self.call("status")
        self.assertEqual(state["warp"], "on")
        self.assertEqual(state["signal"], "1920x1080p60, 148.5 MHz (last measured)")
        self.assertTrue(state["picture"].startswith("warped"))
        self.assertEqual(state["aspect"], "16:9")
        self.assertEqual(state["keystone_by"], "manual")
        self.assertEqual(state["after_move"], "keystone+focus")
        self.assertEqual(state["reference"], "set")
        self.assertEqual(state["screen_zoom"], 85)
        self.assertEqual(state["mode"], "rear-ceiling")
        self.assertEqual(state["fps"], 59.4)
        self.assertEqual(state["pattern"], "mask (a corner marked)")
        self.assertEqual(state["keystone"]["tl_x"], 120)
        self.assertEqual(state["keystone"]["tl_y"], 40)
        self.assertEqual(state["keystone"]["br_x"], 30)
        self.assertEqual(state["max"]["tr_x"], 880)     # 1000 - tl_x
        self.assertEqual(state["temperatures"],
                         [{"name": "cpu-thermal", "c": 54.3},
                          {"name": "gpu-thermal", "c": 58.0}])

    def test_status_takes_the_keystone_facts_in_process(self):
        """With h713-keystone a Python file beside the tools, the status
        computes "after a move", "reference" and "keystone by" in this
        process and does not start the program: on the HY310 that start cost
        0.27 s of CPU every three seconds and made the light pulse."""
        module = """
import re
WARP_SLOTS = (("tl", "x"), ("tl", "y"), ("tr", "x"), ("tr", "y"), ("bl", "x"), ("bl", "y"), ("br", "x"), ("br", "y"))
WARP_VALUE = re.compile(r"\\b(tl|tr|bl|br)[ _-]?([xy])\\b\\s*[=:]?\\s*(-?\\d+)")
WARP_PAIR = re.compile(r"\\b(tl|tr|bl|br)\\s+(-?\\d+),(-?\\d+)")
REF_PATH, LAST_AUTO_PATH = "/nonexistent/ref", "/nonexistent/last-auto"
def load_conf(path):
    return {"after_move": "keystone+focus"}
def _reference_text(path, conf):
    return "file (2026-10-16): %s, counts 1 2 3" % path
def read_last_auto(path):
    return (0, 0, 0, 0, 0, 0, 0, 0)
def keystone_by(warp_set, last_auto):
    return "auto (the last automatic set, untouched since)" if warp_set == last_auto else "manual (changed, %r)" % (warp_set,)
"""
        with open(os.path.join(self.fake.dir, "h713-keystone"), "wb") as handle:
            handle.write(module.encode("utf-8"))
        fresh = panel.Panel(tools=self.fake.dir, keystone_conf=self.conf,
                            thermal=os.path.join(self.fake.dir, "thermal"))
        self.fake.forget()
        state = fresh.call({"verb": "status"})
        self.assertEqual(state["after_move"], "keystone+focus")
        self.assertEqual(state["reference"], "set")
        self.assertEqual(state["keystone_by"], "manual")      # the fake warp status carries non-zero corners
        self.assertEqual([c for c in self.fake.calls() if c.startswith("h713-keystone")], [])
        self.assertEqual(sorted(c.split()[0] for c in self.fake.calls()), ["h713-tv", "h713-warp"])

    def test_status_without_any_tool(self):
        empty = panel.Panel(tools=os.path.join(self.fake.dir, "nothing"),
                            thermal=os.path.join(self.fake.dir, "nothing"))
        state = empty.call({"verb": "status"})
        self.assertTrue(state["ok"])
        self.assertEqual(state["warp"], "unknown")
        self.assertEqual(state["mode"], "-")
        self.assertEqual(state["temperatures"], [])
        self.assertEqual(state["max"]["tl_x"], 1000)
        self.assertEqual(state["reference"], "-")

    def test_the_strip_word_for_the_reference(self):
        """`ref ideal` on a fresh image, `ref set` once a level reference is
        stored, `ref refused` when the file is from another axis map."""
        for status, word in ((KEYSTONE_STATUS_IDEAL, "ideal"),
                             (KEYSTONE_STATUS, "set"),
                             (KEYSTONE_STATUS_REFUSED, "refused"),
                             (KEYSTONE_STATUS_REFUSED_OLD, "refused")):
            self.fake.tool("h713-keystone", {"status": status})
            self.assertEqual(self.call("status")["reference"], word, word)

    def test_controls_carry_the_ranges_and_the_lists(self):
        answer = self.call("controls")
        self.assertTrue(answer["ok"])
        found = dict((c["name"], c) for c in answer["controls"])
        self.assertEqual(found["hue"]["min"], -50)
        self.assertEqual(found["sharpness"]["max"], 15)
        self.assertEqual(found["brightness"]["value"], 50)
        self.assertEqual(list(answer["presets"]), list(panel.PRESETS))
        self.assertEqual(list(answer["corners"]), list(panel.CORNERS))
        self.assertEqual(list(answer["modes"]), list(panel.MODES))
        self.assertEqual(list(answer["steps"]), list(panel.NUDGE_STEPS))

    def test_controls_say_which_hardware_the_board_has(self):
        answer = self.call("controls")         # no h713-features: everything stays (but the colour manager, cm-diagnose 20.10.2026)
        self.assertEqual(answer["features"], {"colour-manager": False})
        self.assertEqual(list(answer["after_move"]), list(panel.AFTER_MOVE))
        self.fake.tool("h713-features", {"status": GEU_FEATURES})
        answer = self.call("controls")
        self.assertEqual(answer["features"], {"camera": False, "accelerometer": True,
                                              "focus-motor": False, "colour-manager": False})
        self.assertEqual(list(answer["after_move"]), ["off", "keystone"])

    def test_after_move_refuses_hardware_the_board_does_not_have(self):
        self.fake.tool("h713-features", {"status": GEU_FEATURES})
        answer = self.call("after_move", ["keystone+focus"])
        self.assertFalse(answer["ok"])
        self.assertIn("needs the camera and the focus-motor - not present on this board",
                      answer["line"])
        self.assertFalse(os.path.exists(self.conf))
        self.assertNotIn("systemctl restart h713-keystone-auto", self.fake.calls())
        self.assertTrue(self.call("after_move", ["keystone"])["ok"])
        self.fake.tool("h713-features", {"status": GEU_FEATURES.replace(
            "present  iio:device0", "not present on this board  iio:device0")})
        self.assertFalse(self.call("after_move", ["keystone"])["ok"])
        self.assertTrue(self.call("after_move", ["off"])["ok"])

    def test_after_move_writes_the_key_and_restarts_the_unit(self):
        with open(self.conf, "wb") as handle:
            handle.write(b"# /etc/h713/keystone.conf\n"
                         b"iio_name           = sc7a20    # not this line\n"
                         b"after_move         = off       # and this one back\n"
                         b"hold_seconds       = 1.0\n")
        answer = self.call("after_move", ["keystone+focus"])
        self.assertTrue(answer["ok"], answer)
        with open(self.conf, "rb") as handle:
            written = handle.read().decode("utf-8").splitlines()
        self.assertEqual(written[0], "# /etc/h713/keystone.conf")
        self.assertEqual(written[1],
                         "iio_name           = sc7a20    # not this line")
        self.assertEqual(written[2],
                         "after_move = keystone+focus   # and this one back")
        self.assertEqual(written[3], "hold_seconds       = 1.0")
        self.assertIn("systemctl restart h713-keystone-auto", self.fake.calls())
        self.assertFalse(os.path.exists(self.conf + ".new"))

    def test_after_move_appends_the_key_to_a_file_without_it(self):
        with open(self.conf, "wb") as handle:
            handle.write(b"hysteresis_degrees = 1.0\n")
        self.assertTrue(self.call("after_move", ["keystone"])["ok"])
        with open(self.conf, "rb") as handle:
            self.assertEqual(handle.read(),
                             b"hysteresis_degrees = 1.0\nafter_move = keystone\n")

    def test_a_tool_that_refuses_is_reported_as_it_answered(self):
        self.fake.tool("h713-tv", code=1)
        answer = self.call("preset", ["cinema"])
        self.assertFalse(answer["ok"])
        self.assertTrue(answer["line"].startswith("ok h713-tv") is False
                        or answer["ok"] is False)
        self.fake.tool("h713-warp", {"ctl on": "error no EGL extension"})
        answer = self.call("warp", ["on"])
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["line"], "error no EGL extension")

    def test_a_missing_tool_is_named(self):
        alone = panel.Panel(tools=os.path.join(self.fake.dir, "nothing"))
        answer = alone.call({"verb": "save", "args": []})
        self.assertFalse(answer["ok"])
        self.assertIn("h713-tv", answer["line"])


class PlainTest(unittest.TestCase):
    """The parts that need no process at all."""

    def test_first_line(self):
        self.assertEqual(panel.first_line("ok zoom 85\nmore\n", 0),
                         (True, "ok zoom 85"))
        self.assertEqual(panel.first_line("warning: x\nerror bad\n", 0),
                         (False, "error bad"))
        self.assertEqual(panel.first_line("ok but the code says no", 2)[0], False)
        self.assertEqual(panel.first_line("", 0), (True, "ok"))
        self.assertEqual(panel.first_line("", 3), (False, "error exit code 3"))
        self.assertEqual(panel.first_line("no verb here\n", 0),
                         (True, "no verb here"))

    def test_labelled_skips_continuation_lines(self):
        fields = panel.labelled("ok status\nzoom            off\n"
                                "                src-window full\n"
                                "keystone by     auto\n")
        self.assertEqual(fields["zoom"], "off")
        self.assertEqual(fields["keystone by"], "auto")
        self.assertNotIn("src-window", fields)

    def test_keystone_limits_are_the_vendor_clamp(self):
        limits = panel.keystone_limits({"tl_x": 120, "tl_y": 40, "br_x": 30})
        self.assertEqual(limits["tr_x"], 880)      # across the row from tl
        self.assertEqual(limits["bl_y"], 960)      # across the column from tl
        self.assertEqual(limits["bl_x"], 970)      # across the row from br
        self.assertEqual(limits["tl_x"], 1000)     # tr is still 0

    def test_every_verb_of_the_page_exists_in_the_tool(self):
        with open(PAGE, "rb") as handle:
            page = handle.read().decode("utf-8")
        # the page builds some of its buttons as HTML, so the quote around the
        # verb may be escaped: act(\'preset\', ...)
        used = set(re.findall(r"\b(?:act|api)\(\s*\\?['\"]([a-z_]+)", page))
        known = set(panel.COMMANDS) | set(panel.SPECIALS)
        self.assertTrue(used, "the page calls no verb at all")
        self.assertEqual(used - known, set())
        # and the other way: nothing in the table is unreachable from the page.
        # A verb the page picks with a ternary (mask_on/mask_off) is only a
        # quoted word, so this direction looks for the word anywhere.
        named = set(re.findall(r"['\"]([a-z_]+)['\"]", page)) | used
        self.assertEqual(known - named, set())

    def test_the_page_draws_the_quadrilateral_from_the_eight_values(self):
        """The diagram is per-mille inward: a corner at 0 sits on the panel's
        own corner, 1000 would be the opposite edge (h713-warp's units)."""
        with open(PAGE, "rb") as handle:
            page = handle.read().decode("utf-8")
        for needed in ('id="quad"', "<polygon", "onpointerdown", "setPointerCapture",
                       "keystone_set", "fromPoint", "getScreenCTM"):
            self.assertIn(needed, page, needed)
        # the panel rectangle of the viewBox has to match what point() divides by
        self.assertIn('x="20" y="18" width="320" height="180"', page)
        self.assertIn("var X0 = 20, Y0 = 18, W = 320, H = 180;", page)

    def test_the_page_shows_the_reference_and_says_what_the_button_refines(self):
        with open(PAGE, "rb") as handle:
            page = handle.read().decode("utf-8")
        self.assertIn('bit("ref", ST.reference', page)
        self.assertIn("ref ideal", page)
        self.assertIn("ref set", page)
        self.assertIn("refines the ideal", page)
        self.assertIn(">Level reference</button>", page)

    def test_the_page_hides_the_controls_of_absent_hardware(self):
        with open(PAGE, "rb") as handle:
            page = handle.read().decode("utf-8")
        wanted = {"keystone_now')": "accelerometer", "keystone_ref')": "accelerometer",
                  "autofocus')": "camera focus-motor", "after\"": "accelerometer"}
        for verb in ("['down', '20']", "['down', '5']", "['up', '5']", "['up', '20']"):
            wanted["act('focus', %s)" % verb] = "focus-motor"
        for anchor, needs in wanted.items():
            tag = re.search(r"<[^<>]*" + re.escape(anchor) + r"[^<>]*>", page)
            self.assertIsNotNone(tag, anchor)
            self.assertIn('data-needs="%s"' % needs, tag.group(0), anchor)
        for needs in re.findall(r'data-needs="([^"]*)"', page):
            self.assertTrue(set(needs.split()) <= set(panel.FEATURE_NAMES) | set(panel.FIRMWARE_FEATURES), needs)
        for needed in ('id="absent"', "FEAT = c.features || {}; features();",
                       "[hidden] { display: none !important; }", 'has("accelerometer")'):
            self.assertIn(needed, page)

    def test_the_page_carries_no_external_reference(self):
        with open(PAGE, "rb") as handle:
            page = handle.read().decode("utf-8")
        self.assertNotIn("http://", page.replace("http://%s", ""))
        self.assertNotIn("https://", page)
        self.assertNotIn("<script src", page)
        self.assertNotIn("@import", page)

    def test_main_without_a_page_file(self):
        missing = os.path.join(tempfile.gettempdir(), "h713-panel-no-such-page")
        self.assertEqual(panel.main(["--page", missing]), 2)


@unittest.skipUnless(POSIX, "the fake tools are /bin/sh scripts")
class HttpTest(unittest.TestCase):
    """The way in: GET / is the page, POST /api is the verb, and there is
    nothing else."""

    def setUp(self):
        self.fake = Fakes()
        self.fake.tool("h713-warp")
        with open(PAGE, "rb") as handle:
            page = handle.read()
        self.server = panel.serve(panel.Panel(tools=self.fake.dir), page,
                                  "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(5)
        self.server.server_close()
        self.fake.close()

    def get(self, path):
        return urllib.request.urlopen("http://127.0.0.1:%d%s"
                                      % (self.port, path), timeout=10)

    def post(self, body):
        request = urllib.request.Request(
            "http://127.0.0.1:%d/api" % self.port, data=body,
            headers={"Content-Type": "application/json",
                     "X-Requested-With": "h713-panel"})
        answer = urllib.request.urlopen(request, timeout=10)
        return json.loads(answer.read().decode("utf-8"))

    def test_the_page_comes_back(self):
        answer = self.get("/")
        self.assertEqual(answer.getcode(), 200)
        self.assertIn(b"h713 panel", answer.read())

    def test_any_other_path_is_not_served(self):
        for path in ("/etc/passwd", "/../h713-panel", "/api"):
            try:
                self.get(path)
                self.fail("%s was served" % path)
            except urllib.error.HTTPError as problem:
                self.assertIn(problem.code, (404, 501))

    def test_a_verb_over_http(self):
        answer = self.post(b'{"verb": "warp", "args": ["on"]}')
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(self.fake.calls(), ["h713-warp ctl on"])

    def test_junk_is_refused(self):
        for body in (b"not json", b"[]", b'{"verb": "rpc"}',
                     b'{"verb": "warp", "args": ["on; reboot"]}',
                     b'{"verb": "volume", "args": ["50"]}' + b" " * 8000):
            answer = self.post(body)
            self.assertFalse(answer["ok"], body)
        self.assertEqual(self.fake.calls(), [])


class AuthTests(unittest.TestCase):
    """The door (05.10.2026): HTTP Basic Auth against the one password in the
    password file; any user name; --no-auth (password None) leaves it open."""

    def setUp(self):
        self.fake = Fakes()
        self.tmp = tempfile.mkdtemp()
        page = b"<html>h713 panel</html>"
        self.server = panel.serve(panel.Panel(tools=self.fake.dir), page, "127.0.0.1", 0,
                                  password="geheim-123")
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(5)
        self.server.server_close()
        self.fake.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, auth=None, path="/"):
        request = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path))
        if auth is not None:
            request.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
        try:
            answer = urllib.request.urlopen(request, timeout=10)
            return answer.getcode(), dict(answer.headers)
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers)

    def test_without_a_password_the_door_is_shut(self):
        code, headers = self._get()
        self.assertEqual(code, 401)
        self.assertIn("Basic realm=", headers.get("WWW-Authenticate", ""))

    def test_a_wrong_password_is_refused_whatever_the_user(self):
        for auth in ("x:geheim-124", "root:", ":geheim-123x", "geheim-123"):
            self.assertEqual(self._get(auth)[0], 401, auth)

    def test_the_right_password_opens_for_any_user_name(self):
        for user in ("", "marco", "h713"):
            self.assertEqual(self._get(user + ":geheim-123")[0], 200, user)

    def test_the_api_is_behind_the_same_door(self):
        request = urllib.request.Request("http://127.0.0.1:%d/api" % self.port,
                                         data=b'{"verb":"status"}',
                                         headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(cm.exception.code, 401)

    def test_the_password_file_round_trip_and_mode(self):
        path = os.path.join(self.tmp, "panel.env")
        self.assertIsNone(panel.read_password(path))
        pw = panel.make_password(path)
        self.assertEqual(panel.read_password(path), pw)
        self.assertGreaterEqual(len(pw), 12)
        if POSIX:
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


# ---- the settings pages (11.10.2026): conf files, remote, power, Wi-Fi, host name, password ----

WIFI_ENV = """# /etc/h713/wifi.env - a comment that has to survive
mode=ap
ssid=h713
password=magcubic
band=2.4
channel=6
country=DE
ap_ip=192.168.4.1
ap_dhcp_start=192.168.4.10
ap_dhcp_end=192.168.4.100
"""
POWER_STATUS = """config: default = poweroff, long_s = 3, ignore_s = 2, remote = on, refused = poweroff
mem_sleep: s2idle [deep]
a short press now: power-off (power.conf says short = poweroff)"""
TV_UNITS = "h713-tv@video3.service loaded active running HY310: HDMI input (video3) on the video plane"
LISTING = "h713-tv@*.service"


class Bench(unittest.TestCase):
    """A panel on a temporary /etc/h713, /etc/hosts and /etc/hostname, with the fake tools."""

    def setUp(self):
        self.fake = Fakes()
        self.etc = os.path.join(self.fake.dir, "etc")
        os.makedirs(self.etc)
        self.hosts = os.path.join(self.fake.dir, "hosts")
        self.hostname = os.path.join(self.fake.dir, "hostname")
        for name in ("h713-warp", "h713-tv", "h713-osd", "h713-wifi", "h713-logs", "systemctl",
                     "systemd-run", "hostnamectl", "h713-keys", "h713-features"):
            self.fake.tool(name)
        self.fake.tool("h713-power", {"status": POWER_STATUS})
        self.fake.tool("h713-warp", {"ctl edge": "ok edge 4"})
        self.panel = panel.Panel(
            tools=self.fake.dir, etc=self.etc, hosts=self.hosts, hostname_file=self.hostname,
            selfpath="/usr/local/lib/h713-panel/h713-panel", keystone_conf=os.path.join(self.etc, "ks.conf"),
            thermal=os.path.join(self.fake.dir, "thermal"))

    def tearDown(self):
        self.fake.close()

    def call(self, verb, args=None):
        return self.panel.call({"verb": verb, "args": args or []})

    def put(self, name, text, base=None):
        with open(os.path.join(base or self.etc, name), "wb") as handle:
            handle.write(text.encode("utf-8"))

    def get(self, name, base=None):
        with open(os.path.join(base or self.etc, name), "rb") as handle:
            return handle.read().decode("utf-8")


class NewVerbTest(Bench):
    def test_the_plain_verbs_are_one_command_each(self):
        for verb, args, expected in (
                ("save_off", [], "h713-tv ctl save off"),
                ("resync", [], "h713-tv ctl resync"),
                ("replug", [], "h713-tv ctl replug"),
                ("edge", [64], "h713-warp ctl edge 64"),
                ("edge", [0], "h713-warp ctl edge 0"),
                ("pattern", ["grid"], "h713-warp ctl test grid"),
                ("pattern", ["border"], "h713-warp ctl test border"),
                ("power_default", ["standby"], "h713-power set default standby"),
                ("power_long", [5], "h713-power set long_s 5"),
                ("power_remote", ["off"], "h713-power set remote off"),
                ("power_refused", ["log"], "h713-power set refused log"),
                ("logs", ["persistent"], "h713-logs persistent"),
                ("logs", ["volatile"], "h713-logs volatile"),
                ("reboot", [], "systemctl reboot"),
                ("poweroff", [], "systemctl poweroff")):
            self.fake.forget()
            answer = self.call(verb, args)
            self.assertTrue(answer["ok"], (verb, answer))
            self.assertEqual(self.fake.calls(), [expected])

    def test_refused_values_start_nothing_and_write_nothing(self):
        for verb, args in (
                ("edge", [65]), ("edge", [-1]), ("edge", ["4; reboot"]), ("pattern", ["mask"]),
                ("power_default", ["suspend"]), ("power_long", [0]), ("power_long", [11]),
                ("power_remote", ["maybe"]), ("power_refused", ["$(id)"]), ("logs", ["syslog"]),
                ("report", ["rpc"]), ("report", []), ("picture_set", ["rpc", 1]),
                ("conf_set", ["tv", "edid", "block1"]), ("conf_set", ["tv", "focus_command", "x"]),
                ("conf_set", ["keys", "volume_step", 21]), ("conf_set", ["keys", "volume_step", 0]),
                ("conf_set", ["keys", "focus_steps", 101]), ("conf_set", ["keys", "focus_steps", "5; x"]),
                ("conf_set", ["osd", "scale", 2.5]), ("conf_set", ["osd", "scale", 0.4]),
                ("conf_set", ["osd", "scale", 0.55]), ("conf_set", ["osd", "seconds", 0.4]),
                ("conf_set", ["osd", "seconds", 11]), ("conf_set", ["osd", "seconds", "nan"]),
                ("conf_set", ["osd", "place", "left"]), ("conf_set", ["osd", "look", True]),
                ("conf_set", ["tv", "start", "auto; reboot"]), ("conf_set", ["tv", "preset", "$(id)"]),
                ("conf_set", ["tv", "edid_prefer", "block1"]), ("conf_set", ["ssh", "key", "x"]),
                ("conf_set", ["keys", "volume_step"]),
                ("hostname_set", ["a.b"]), ("hostname_set", ["-a"]), ("hostname_set", ["a_b"]),
                ("hostname_set", ["a" * 64]), ("hostname_set", [""]), ("hostname_set", ["a b"]),
                ("hostname_set", ["a\nb"]), ("hostname_set", [5]),
                ("panel_password", ["only one"]), ("remote_repair", ["x"] * 5)):
            answer = self.call(verb, args)
            self.assertFalse(answer["ok"], (verb, args, answer))
            self.assertTrue(answer["line"].startswith("error"), answer)
        self.assertEqual(self.fake.calls(), [])
        self.assertEqual(os.listdir(self.etc), [])
        self.assertFalse(os.path.exists(self.hosts))

    def test_a_quality_control_takes_its_range_from_the_long_name_of_ctl_list(self):
        self.fake.tool("h713-tv", {"ctl list": TV_LIST + "\n  spatial_noise_reduction    0 (Off)  menu 0..2"})
        self.panel.ranges = {}
        self.assertFalse(self.call("picture_set", ["snr", 3])["ok"])    # 0..2 on this firmware, not the fallback 3
        self.assertTrue(self.call("picture_set", ["snr", 2])["ok"])
        self.assertEqual(self.fake.calls()[-1], "h713-tv ctl set snr 2")

    def test_the_quality_controls_go_through_ctl_set_in_their_range(self):
        for name, value in (("tnr", 3), ("black", 0)):
            self.fake.forget()
            self.assertTrue(self.call("picture_set", [name, value])["ok"])
            self.assertEqual(self.fake.calls()[-1], "h713-tv ctl set %s %d" % (name, value))
        self.fake.forget()
        for name, value in (("tnr", 4), ("snr", -1), ("dci", "2; reboot")):
            self.assertFalse(self.call("picture_set", [name, value])["ok"])
        self.assertFalse([c for c in self.fake.calls() if " set " in c])

    def test_controls_carry_the_quality_controls_and_the_forms(self):
        # `ctl list` as the HY310 prints it (12.10.2026): the long names; the page and ctl set use the short ones
        self.fake.tool("h713-tv", {"ctl list": TV_LIST + "\n  temporal_noise_reduction   2 (Middle)  menu 0..3"
                                   "\n  black_extension            1 (Low)  menu 0..3"})
        answer = self.call("controls")
        found = dict((c["name"], c) for c in answer["quality"])
        self.assertEqual(sorted(found), ["black", "dci", "snr", "tnr"])
        self.assertEqual((found["tnr"]["value"], found["tnr"]["max"]), (2, 3))
        self.assertEqual(found["black"]["value"], 1)
        self.assertEqual(found["dci"]["max"], 3)                      # not listed: the fallback
        self.assertEqual(list(answer["conf"]["keys"]["volume_step"]), ["number", 1, 20, 1])
        self.assertEqual(json.loads(json.dumps(answer["conf"]["osd"]["place"])), ["choice", ["bottom", "top-right", "center"]])
        self.assertNotIn("focus_command", json.dumps(answer))
        self.assertNotIn("block1", json.dumps(answer))

    def test_conf_set_keeps_comments_and_other_keys(self):
        self.put("keys.conf", "# keys\nvolume_step = 5   # the old step\nfocus_steps = 20\n")
        self.assertTrue(self.call("conf_set", ["keys", "volume_step", 7])["ok"])
        self.assertEqual(self.get("keys.conf"), "# keys\nvolume_step = 7   # the old step\nfocus_steps = 20\n")
        self.assertTrue(self.call("conf_set", ["osd", "scale", 1.5])["ok"])
        self.assertTrue(self.call("conf_set", ["osd", "seconds", "2.5"])["ok"])
        self.assertEqual(self.get("osd.conf"), "scale = 1.5\nseconds = 2.5\n")
        self.assertFalse(os.path.exists(os.path.join(self.etc, "osd.conf.new")))
        self.assertEqual(self.fake.calls(), [])           # keys and osd read their file again by themselves

    def test_tv_conf_restarts_the_instance_it_finds(self):
        self.fake.tool("systemctl", {"list-units --plain --no-legend " + LISTING: TV_UNITS})
        self.put("tv.conf", "start = last\n")
        answer = self.call("conf_set", ["tv", "preset", "last"])
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(self.get("tv.conf"), "start = last\npreset = last\n")
        self.assertEqual(self.fake.calls(), ["systemctl list-units --plain --no-legend " + LISTING,
                                             "systemctl restart h713-tv@video3.service"])
        self.assertIn("h713-tv@video3.service restarted", answer["line"])

    def test_tv_conf_without_a_running_instance(self):
        answer = self.call("conf_set", ["tv", "edid_prefer", "panel"])
        self.assertTrue(answer["ok"], answer)
        self.assertIn("applies at its next start", answer["line"])
        self.assertEqual(self.get("tv.conf"), "edid_prefer = panel\n")
        self.assertFalse([c for c in self.fake.calls() if "restart" in c])

    def test_settings_read_the_files_and_never_the_password(self):
        self.put("keys.conf", "volume_step = 9\n")
        self.put("tv.conf", "start = zuletzt\npreset = cinema\n")
        self.put("wifi.env", WIFI_ENV)
        self.put("osd.conf", "place = center\n")
        with open(self.hostname, "w") as handle:
            handle.write("hy310\n")
        answer = self.call("settings")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(answer["conf"]["keys"], {"volume_step": "9", "focus_steps": "20"})
        self.assertEqual(answer["conf"]["tv"], {"start": "last", "preset": "cinema", "edid_prefer": None})
        self.assertEqual(answer["conf"]["osd"]["place"], "center")
        self.assertEqual(answer["conf"]["osd"]["look"], "pill")
        self.assertEqual(answer["power"], {"default": "poweroff", "long_s": "3", "ignore_s": "2",
                                           "remote": "on", "refused": "poweroff"})
        self.assertEqual((answer["edge"], answer["hostname"]), (4, "hy310"))
        self.assertEqual(answer["wifi"]["ssid"], "h713")
        self.assertTrue(answer["wifi"]["has_password"])
        self.assertIsNone(answer["wifi_pending"])
        self.assertNotIn("magcubic", json.dumps(answer))
        self.assertNotIn("password", answer["wifi"])

    def test_reports_are_the_tools_own_text(self):
        self.fake.tool("h713-tv", {"ctl hdcp": "hdcp version 1.4\nauthenticated yes"})
        answer = self.call("report", ["hdcp"])
        self.assertTrue(answer["ok"])
        self.assertIn("authenticated yes", answer["text"])
        for name, expected in (("features", "h713-features status"), ("keys", "h713-keys status"),
                               ("osd", "h713-osd ctl status"), ("power", "h713-power status"),
                               ("logs", "h713-logs status"), ("wifi", "h713-wifi status")):
            self.fake.forget()
            self.assertTrue(self.call("report", [name])["ok"], name)
            self.assertEqual(self.fake.calls(), [expected])
        self.assertFalse(panel.Panel(tools=os.path.join(self.fake.dir, "nothing")).call(
            {"verb": "report", "args": ["hdcp"]})["ok"])

    def test_nothing_the_owner_excluded_is_in_the_tables(self):
        everything = json.dumps([list(panel.COMMANDS), list(panel.SPECIALS), list(panel.REPORTS),
                                 [(f, list(k)) for f, (_, k) in panel.CONF.items()]])
        for word in ("rpc", "focus_command", "block1", "ssh", "authorized"):
            self.assertNotIn(word, everything)
        # the volume is never kept through a restart: no verb writes it into a file
        self.assertEqual([k for _, (_, keys) in panel.CONF.items() for k in keys if "vol" in k], ["volume_step"])


class RemoteTest(Bench):
    def remote(self, forget_code=0, forget_out="ok forgot 00:11:22:33:44:55", status_code=0,
               status_out="00:11:22:33:44:55 BLE_X_RMC connected"):
        self.fake.script("h713-remote-pair", 'case "$1" in\n  forget) cat <<\'END\'\n%s\nEND\n  exit %d ;;\n'
                         '  status) cat <<\'END\'\n%s\nEND\n  exit %d ;;\nesac' %
                         (forget_out, forget_code, status_out, status_code))

    def test_the_state_of_the_remote(self):
        for out, code, state, name in (
                ("00:11:22:33:44:55 BLE_X_RMC connected", 0, "connected", "BLE_X_RMC"),
                ("00:11:22:33:44:55 BLE_X_RMC bonded, not connected", 0, "bonded", "BLE_X_RMC"),
                ("no remote bonded", 1, "none", "")):
            self.remote(status_out=out, status_code=code)
            answer = self.call("remote")
            self.assertTrue(answer["ok"], answer)
            self.assertEqual((answer["state"], answer["name"]), (state, name))
            self.assertNotIn("00:11", json.dumps(answer))               # the address stays here
        self.remote(status_out="error: no Bluetooth controller", status_code=2)
        self.assertFalse(self.call("remote")["ok"])

    def test_repair_forgets_and_shows_the_hint(self):
        self.remote()
        answer = self.call("remote_repair")
        self.assertTrue(answer["ok"] and answer["forgot"] and answer["hint"], answer)
        self.assertEqual(answer["seconds"], panel.PAIR_WINDOW_S)
        self.assertEqual(self.fake.calls(), ["h713-remote-pair forget", "h713-osd ctl pair"])
        self.assertIn("LEFT + RIGHT", answer["line"])

    def test_repair_with_no_remote_paired_is_a_plain_sentence(self):
        self.remote(forget_code=1, forget_out="")             # forget: exit 1 and not a word
        answer = self.call("remote_repair")
        self.assertTrue(answer["ok"], answer)
        self.assertFalse(answer["forgot"])
        self.assertIn("no remote was paired, so there was nothing to forget", answer["line"])
        self.assertEqual(self.fake.calls(), ["h713-remote-pair forget", "h713-osd ctl pair"])

    def test_repair_stops_when_bluez_refuses(self):
        self.remote(forget_code=2, forget_out="error: forget 00:11:22:33:44:55: no answer")
        answer = self.call("remote_repair")
        self.assertFalse(answer["ok"])
        self.assertIn("no answer", answer["line"])
        self.assertEqual(self.fake.calls(), ["h713-remote-pair forget"])    # no hint for a bond still there

    def test_a_missing_hint_is_said_not_fatal(self):
        self.remote()
        self.fake.script("h713-osd", 'echo "error unknown: volume N | mute on|off N"\nexit 1')
        answer = self.call("remote_repair")
        self.assertTrue(answer["ok"], answer)
        self.assertFalse(answer["hint"])
        self.assertIn("no hint on the projector", answer["line"])

    def test_a_slow_read_does_not_hold_the_motor_lock(self):
        self.assertTrue(self.panel.lock.acquire(False))        # a command is running
        try:
            self.remote()
            self.assertTrue(self.call("remote")["ok"])
            self.assertTrue(self.call("settings")["ok"])
            self.assertTrue(self.call("report", ["hdcp"])["ok"])
        finally:
            self.panel.lock.release()


class WifiTest(Bench):
    FORM = {"mode": "sta", "ssid": "Home net", "password": "s3cret-pass#1", "country": "DE"}

    def setUp(self):
        Bench.setUp(self)
        self.put("wifi.env", WIFI_ENV)
        self.env = os.path.join(self.etc, "wifi.env")

    def apply(self, form=None):
        return self.call("wifi_set", [form if form is not None else self.FORM])

    def test_apply_keeps_the_old_file_sets_the_timer_and_restarts(self):
        answer = self.apply()
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(answer["pending"], panel.ROLLBACK_S)
        new = self.get("wifi.env")
        for line in ("mode=sta", "ssid=Home net", "password=s3cret-pass#1", "band=2.4", "channel=6"):
            self.assertIn("\n" + line + "\n", "\n" + new)
        self.assertTrue(new.startswith("# /etc/h713/wifi.env - a comment that has to survive\n"))
        self.assertEqual(self.get("wifi.env.prev"), WIFI_ENV)
        self.assertEqual(stat.S_IMODE(os.stat(self.env).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.env + ".prev").st_mode), 0o600)
        self.assertEqual(self.fake.calls(), [
            "h713-wifi check %s.next" % self.env,
            "systemd-run --quiet --collect --unit=h713-panel-wifi-rollback --on-active=120 "
            "/usr/local/lib/h713-panel/h713-panel --rollback-wifi --etc " + self.etc,
            "systemctl restart h713-wifi.service"])
        self.assertFalse(os.path.exists(self.env + ".next"))
        self.assertNotIn("s3cret", json.dumps(answer))
        self.assertLessEqual(self.call("status")["wifi_pending"], panel.ROLLBACK_S)
        self.assertEqual(self.call("settings")["wifi"]["mode"], "sta")

    def test_an_empty_password_means_unchanged(self):
        self.assertTrue(self.apply({"ssid": "Other", "password": ""})["ok"])
        new = panel.read_env(self.get("wifi.env"))
        self.assertEqual((new["ssid"], new["password"]), ("Other", "magcubic"))

    def test_the_password_is_never_sent_back(self):
        # even a check that quotes it in its refusal
        self.fake.script("h713-wifi", 'echo "h713-wifi: ERROR: password s3cret-pass#1 is wrong" >&2\nexit 1')
        answer = self.apply()
        self.assertFalse(answer["ok"])
        self.assertNotIn("s3cret", json.dumps(answer))
        # and a refusal of the password itself says nothing of it
        answer = self.apply({"password": "short"})
        self.assertFalse(answer["ok"])
        self.assertNotIn("short", answer["line"])
        for verb in ("settings", "status"):
            self.assertNotIn("magcubic", json.dumps(self.call(verb)))

    def test_a_check_that_fails_touches_nothing(self):
        self.fake.script("h713-wifi", 'echo "h713-wifi: ERROR: band=5 allows only 36, 40, 44, 48" >&2\nexit 1')
        answer = self.apply({"band": "5", "channel": "6"})
        self.assertFalse(answer["ok"])
        self.assertIn("band=5 allows only", answer["line"])
        self.assertEqual(self.get("wifi.env"), WIFI_ENV)
        self.assertEqual(sorted(os.listdir(self.etc)), ["wifi.env"])
        self.assertEqual(len(self.fake.calls()), 1)               # the check, no timer, no restart

    def test_values_that_could_break_the_file_are_refused_before_any_process(self):
        for form in ({"mode": "mesh"}, {"ssid": "a\nmode=off"}, {"ssid": "a\rb"}, {"ssid": ""},
                     {"ssid": "x" * 33}, {"ssid": 'a"b'}, {"ssid": "a\\b"}, {"password": "1234567"},
                     {"password": "12345678\nmode=off"}, {"password": "p" * 64}, {"country": "de"},
                     {"country": "DEU"}, {"band": "6"}, {"channel": "14"}, {"channel": "37"},
                     {"ap_ip": "300.1.1.1"}, {"ap_ip": "1.1.1"}, {"ap_dhcp_end": "1.1.1.1\n2"},
                     {"foo": "bar"}, {"mode": 1}, {"ssid": ["x"]}):
            answer = self.apply(form)
            self.assertFalse(answer["ok"], form)
            self.assertTrue(answer["line"].startswith("error"), answer)
        for args in ([], ["mode=off"], [{}, {}]):
            self.assertFalse(self.call("wifi_set", args)["ok"])
        self.assertEqual(self.fake.calls(), [])
        self.assertEqual(self.get("wifi.env"), WIFI_ENV)

    def test_no_timer_no_change(self):
        self.fake.tool("systemd-run", code=1)
        answer = self.apply()
        self.assertFalse(answer["ok"])
        self.assertIn("nothing was changed", answer["line"])
        self.assertEqual(self.get("wifi.env"), WIFI_ENV)
        self.assertEqual(sorted(os.listdir(self.etc)), ["wifi.env"])
        self.assertFalse([c for c in self.fake.calls() if "restart" in c])

    def test_a_restart_that_fails_puts_the_old_file_back(self):
        self.fake.script("systemctl", 'case "$*" in "restart h713-wifi.service") echo "Job failed"; exit 1;; esac')
        answer = self.apply()
        self.assertFalse(answer["ok"])
        self.assertIn("the old settings are back", answer["line"])
        self.assertEqual(self.get("wifi.env"), WIFI_ENV)
        self.assertFalse(os.path.exists(self.env + ".prev"))
        self.assertIn("systemctl stop h713-panel-wifi-rollback.timer", self.fake.calls())

    def test_a_waiting_change_blocks_the_next_and_confirm_keeps_it(self):
        self.assertTrue(self.apply()["ok"])
        self.assertIn("waits for its confirmation", self.apply({"ssid": "Third"})["line"])
        self.fake.forget()
        answer = self.call("wifi_confirm")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(self.fake.calls(), ["systemctl stop h713-panel-wifi-rollback.timer"])
        self.assertFalse(os.path.exists(self.env + ".prev"))
        self.assertEqual(panel.read_env(self.get("wifi.env"))["ssid"], "Home net")
        self.assertIsNone(self.call("status")["wifi_pending"])
        self.assertFalse(self.call("wifi_confirm")["ok"])           # nothing waits any more

    def test_a_confirm_that_cannot_stop_the_timer_keeps_the_fall_back(self):
        self.assertTrue(self.apply()["ok"])
        self.fake.tool("systemctl", code=1)
        self.assertFalse(self.call("wifi_confirm")["ok"])
        self.assertTrue(os.path.exists(self.env + ".prev"))

    def test_the_fall_back_restores_the_old_file(self):
        self.assertTrue(self.apply()["ok"])
        self.fake.forget()
        self.assertEqual(self.panel.rollback_wifi(), 0)
        self.assertEqual(self.get("wifi.env"), WIFI_ENV)
        self.assertFalse(os.path.exists(self.env + ".prev"))
        self.assertEqual(self.fake.calls(), ["systemctl restart h713-wifi.service"])
        self.fake.forget()
        self.assertEqual(self.panel.rollback_wifi(), 0)            # confirmed or done: nothing to do
        self.assertEqual(self.fake.calls(), [])

    def test_the_command_the_timer_runs_is_this_file(self):
        """systemd-run starts `h713-panel --rollback-wifi --etc DIR`: run it just so."""
        self.assertTrue(self.apply()["ok"])
        self.fake.forget()
        done = subprocess.run([sys.executable, TOOL, "--rollback-wifi", "--etc", self.etc,
                               "--tools", self.fake.dir], stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(self.get("wifi.env"), WIFI_ENV)
        self.assertEqual(self.fake.calls(), ["systemctl restart h713-wifi.service"])


class HostnameTest(Bench):
    def test_the_name_goes_to_hostnamectl_and_to_127_0_1_1(self):
        self.put("hosts", "127.0.0.1\tlocalhost\n127.0.1.1\thy310\n::1\tlocalhost ip6-localhost\n", self.fake.dir)
        answer = self.call("hostname_set", ["Proj-1"])
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(self.fake.calls(), ["hostnamectl set-hostname proj-1"])
        self.assertEqual(self.get("hosts", self.fake.dir),
                         "127.0.0.1\tlocalhost\n127.0.1.1\tproj-1\n::1\tlocalhost ip6-localhost\n")

    def test_a_hosts_file_without_the_line_gets_one(self):
        self.put("hosts", "127.0.0.1\tlocalhost\n", self.fake.dir)
        self.assertTrue(self.call("hostname_set", ["a"])["ok"])
        self.assertEqual(self.get("hosts", self.fake.dir), "127.0.0.1\tlocalhost\n127.0.1.1\ta\n")
        self.assertTrue(self.call("hostname_set", ["x" * 63])["ok"])

    def test_hostnamectl_that_fails_leaves_hosts_alone(self):
        self.put("hosts", "127.0.1.1\told\n", self.fake.dir)
        self.fake.tool("hostnamectl", code=1)
        self.assertFalse(self.call("hostname_set", ["new"])["ok"])
        self.assertEqual(self.get("hosts", self.fake.dir), "127.0.1.1\told\n")


class PasswordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "panel.env")
        panel.write_password(self.file, "old-password")
        self.panel = panel.Panel(tools=self.tmp, etc=self.tmp, password_file=self.file)
        self.server = panel.serve(self.panel, b"<html>h713 panel</html>", "127.0.0.1", 0,
                                  password="old-password")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(5)
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def change(self, *args):
        return self.panel.call({"verb": "panel_password", "args": list(args)})

    def code(self, password):
        request = urllib.request.Request("http://127.0.0.1:%d/" % self.port)
        request.add_header("Authorization", "Basic " + base64.b64encode(("x:" + password).encode()).decode())
        try:
            return urllib.request.urlopen(request, timeout=10).getcode()
        except urllib.error.HTTPError as problem:
            return problem.code

    def test_the_new_password_replaces_the_old_in_the_file_and_at_the_door(self):
        answer = self.change("old-password", "new pass: 12")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(panel.read_password(self.file), "new pass: 12")
        self.assertEqual(stat.S_IMODE(os.stat(self.file).st_mode), 0o600)
        self.assertEqual((self.code("old-password"), self.code("new pass: 12")), (401, 200))
        self.assertNotIn("new pass", json.dumps(answer))

    def test_refusals_change_nothing(self):
        for args in (("wrong", "new-password-1"), ("old-password", "short"), ("old-password", "p" * 65),
                     ("old-password", " leading-space"), ("old-password", "tab\there-1234"),
                     ("old-password",), ("old-password", 12345678)):
            self.assertFalse(self.change(*args)["ok"], args)
        self.assertEqual(panel.read_password(self.file), "old-password")
        self.assertEqual(self.code("old-password"), 200)

    def test_no_password_in_force_means_nothing_to_change(self):
        self.server.password = None
        self.assertFalse(self.change("x", "new-password-1")["ok"])
        self.assertFalse(panel.Panel(etc=self.tmp).call({"verb": "panel_password", "args": ["a", "b" * 9]})["ok"])



# a stand-in h713-tv with a memory: `ctl wb` and `ctl cm` as color.c answers them (docs/tools/h713-tv.md)
TV_COLOUR = r"""
dir="DIR"
case "$*" in
  "ctl wb")
    if [ -f "$dir/absent" ]; then echo "ok wb $(cat "$dir/wb") [not available: not the display firmware]"
    else echo "ok wb $(cat "$dir/wb") sliders $(cat "$dir/sliders") -- R G B gain, R G B offset, then the sliders; 512 is neutral"; fi ;;
  "ctl wb reset") echo "512 512 512 512 512 512" > "$dir/wb"; echo "0 0" > "$dir/sliders"; echo "ok wb 512 512 512 512 512 512 (registers read back, 0 ms)" ;;
  "ctl wb sliders "*) if [ -f "$dir/absent" ]; then echo "error wb: not the display firmware"; else
    set -- $*; echo "$4 $5" > "$dir/sliders"; echo "ok wb sliders $4 $5 (registers read back, 0 ms)"; fi ;;
  "ctl cm") if [ -s "$dir/cm" ]; then echo "ok cm"; cat "$dir/cm"; else echo "ok cm all neutral (0 = as the picture mode has it)"; fi ;;
  "ctl cm reset") : > "$dir/cm"; echo "ok cm all neutral (registers read back, 0 ms)" ;;
  "ctl set cm_"*) set -- $*; grep -v "^  $3 = " "$dir/cm" > "$dir/cm.new"; [ "$4" = 0 ] || echo "  $3 = $4" >> "$dir/cm.new"
    mv "$dir/cm.new" "$dir/cm"; echo "ok $3 = $4 (registers read back, 0 ms)" ;;
  *) echo "ok h713-tv $*" ;;
esac
"""


class ColourTest(Bench):
    """The Colour tab: the white balance as two sliders and the hue and saturation of one primary.  h713-settings
    does the same on the projector's own screen; what the sliders mean in gains is h713-tv's (tests/test_color.c)."""

    def setUp(self):
        super().setUp()
        self.fake.script("h713-tv", TV_COLOUR.replace("DIR", self.fake.dir))
        self.state([512] * 6, "")

    def state(self, wb, cm, sliders="0 0"):
        for name, text in (("wb", " ".join(str(n) for n in wb)), ("cm", cm), ("sliders", sliders)):
            with open(os.path.join(self.fake.dir, name), "w") as handle:
                handle.write(text + "\n" if text else "")

    def held(self, name="wb"):
        with open(os.path.join(self.fake.dir, name)) as handle:
            return handle.read().strip() if name in ("cm", "sliders") else [int(n) for n in handle.read().split()]

    def tv(self):
        return [c for c in self.fake.calls() if c.startswith("h713-tv")]

    def test_a_slider_is_one_ctl_wb_sliders(self):
        answer = self.call("wb_tune", [-12, 6])
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(self.tv(), ["h713-tv ctl wb sliders -12 6"])
        self.assertEqual(self.held("sliders"), "-12 6")
        for cool, magenta in ((50, 50), (-50, -50), (2, 0), (0, 0)):
            self.fake.forget()
            self.assertEqual(self.call("wb_tune", [cool, magenta])["ok"], True)
            self.assertEqual(self.tv(), ["h713-tv ctl wb sliders %d %d" % (cool, magenta)])

    def test_a_value_outside_its_range_starts_nothing(self):
        for verb, args in (("wb_tune", [52, 0]), ("wb_tune", [0, -52]), ("wb_tune", [1, 0]), ("wb_tune", [0, 3]),
                           ("wb_tune", ["2; reboot", 0]), ("wb_tune", [True, 0]), ("wb_tune", [0]), ("wb_tune", [0, 0, 0]),
                           ("cm_set", ["yellow", "hue", 101]), ("cm_set", ["yellow", "sat", -105]), ("cm_set", ["yellow", "hue", 7]),
                           ("cm_set", ["yellow", "hue", "5; reboot"]), ("cm_set", ["yellow", "hue", True]),
                           ("cm_set", ["skintone", "hue", 5]), ("cm_set", ["yellow_green", "hue", 5]), ("cm_set", ["lips", "sat", 5]),
                           ("cm_set", ["yellow", "value", 5]), ("cm_set", ["yellow", "saturation", 5]),
                           ("cm_set", ["yellow; reboot", "hue", 5]), ("cm_set", ["yellow", "hue"]),
                           ("cm_set", ["yellow", "hue", 5, 5]), ("cm_set", [["yellow"], "hue", 5])):
            answer = self.call(verb, args)
            self.assertFalse(answer["ok"], (verb, args, answer))
            self.assertTrue(answer["line"].startswith("error"), answer)
        self.assertEqual(self.fake.calls(), [])
        self.assertEqual((self.held(), self.held("cm")), ([512] * 6, ""))

    def test_a_colour_step_is_one_ctl_set_of_a_fixed_word(self):
        for axis in panel.PRIMARIES:
            for part in panel.CM_PARTS:
                self.fake.forget()
                self.assertTrue(self.call("cm_set", [axis, part, -35])["ok"])
                self.assertEqual(self.fake.calls(), ["h713-tv ctl set cm_%s_%s -35" % (axis, part)])
        self.assertTrue(self.call("cm_set", ["red", "hue", 100])["ok"])
        self.assertTrue(self.call("cm_set", ["red", "sat", -100])["ok"])
        self.assertEqual(self.fake.calls()[-2:], ["h713-tv ctl set cm_red_hue 100", "h713-tv ctl set cm_red_sat -100"])

    def test_the_resets_are_one_command_each(self):
        self.state([480, 500, 512, 512, 512, 512], "  cm_red_hue = 5")
        for verb, expected in (("wb_reset", "h713-tv ctl wb reset"), ("cm_reset", "h713-tv ctl cm reset")):
            self.fake.forget()
            self.assertTrue(self.call(verb)["ok"], verb)
            self.assertEqual(self.fake.calls(), [expected])
        self.assertEqual((self.held(), self.held("cm")), ([512] * 6, ""))

    def test_without_the_calibration_nothing_is_set(self):
        # another display firmware: h713-tv says so in its own words, and the tool sends nothing
        open(os.path.join(self.fake.dir, "absent"), "w").close()
        answer = self.call("wb_tune", [10, 0])
        self.assertFalse(answer["ok"])
        self.assertIn("not the display firmware", answer["line"])
        self.assertFalse(self.call("colour")["ok"])
        self.fake.forget()
        # h713-tv not there at all: it is named, and still nothing is sent
        gone = panel.Panel(tools=os.path.join(self.fake.dir, "nothing"), etc=self.etc)
        for request in ({"verb": "wb_tune", "args": [10, 0]}, {"verb": "colour"}):
            answer = gone.call(request)
            self.assertFalse(answer["ok"], answer)
            self.assertIn("h713-tv" , answer["line"])
        self.assertEqual(self.fake.calls(), [])

    def test_colour_gives_the_sliders_and_the_steps_of_the_six_primaries(self):
        self.state([512] * 6, "  cm_yellow_hue = 10\n  cm_yellow_sat = -15\n  cm_red_sat = 5\n"
                   "  cm_skintone_hue = 40\n  cm_blue_value = 3", "-12 6")        # a colour the page does not offer, a part it does not
        answer = self.call("colour")
        steps = dict((axis, {"hue": 0, "sat": 0}) for axis in panel.PRIMARIES)
        steps["yellow"], steps["red"]["sat"] = {"hue": 10, "sat": -15}, 5
        self.assertEqual(answer, {"ok": True, "line": "ok colour", "wb": {"cool": -12, "magenta": 6}, "wb_other": False, "cm": steps})
        self.assertEqual(self.tv(), ["h713-tv ctl wb", "h713-tv ctl cm"])
        self.state([512] * 6, "")
        self.assertEqual(self.call("colour")["cm"], dict((axis, {"hue": 0, "sat": 0}) for axis in panel.PRIMARIES))

    def test_gains_the_sliders_cannot_make_are_said_so(self):
        for sliders, shown, other in (("0 0 other", (0, 0), True), ("15 10", (15, 10), False), ("-8 -50", (-8, -50), False)):
            self.state([512] * 6, "", sliders)
            answer = self.call("colour")
            self.assertEqual((answer["wb"]["cool"], answer["wb"]["magenta"], answer["wb_other"]), shown + (other,), sliders)

    def test_what_a_slider_set_is_what_colour_reads(self):
        for cool, magenta in ((-12, 6), (50, -50), (-50, 50), (0, 0), (8, -50)):
            self.assertTrue(self.call("wb_tune", [cool, magenta])["ok"])
            answer = self.call("colour")
            self.assertEqual((answer["wb"]["cool"], answer["wb"]["magenta"], answer["wb_other"]), (cool, magenta, False))

    def test_an_h713_tv_without_sliders_in_its_answer_is_said_so(self):
        with open(os.path.join(self.fake.dir, "sliders"), "w") as handle:
            handle.write("\n")
        self.fake.script("h713-tv", TV_COLOUR.replace("DIR", self.fake.dir).replace(
            'sliders $(cat "$dir/sliders") ', ''))
        answer = self.call("colour")
        self.assertFalse(answer["ok"])
        self.assertIn("did not say what the white balance is", answer["line"])

    def test_colour_only_reads_and_does_not_wait_for_the_lock(self):
        self.assertTrue(self.panel.lock.acquire(False))        # a command is running
        try:
            self.assertTrue(self.call("colour")["ok"])
            with unittest.mock.patch.object(panel, "LOCK_WAIT_S", 0.1):
                self.assertTrue(self.call("wb_tune", [0, 0])["busy"])      # a command waits, and gives up
            self.assertEqual(self.tv(), ["h713-tv ctl wb", "h713-tv ctl cm"])
        finally:
            self.panel.lock.release()

    def test_controls_say_whether_the_firmware_has_the_calibration(self):
        self.assertTrue(self.call("controls")["features"]["colour"])
        # cm-diagnose 20.10.2026: the colour manager has no visible effect on the HY310 - the card of the primaries is not offered
        self.assertIs(self.call("controls")["features"]["colour-manager"], False)
        open(os.path.join(self.fake.dir, "absent"), "w").close()
        self.assertFalse(self.call("controls")["features"]["colour"])
        self.fake.tool("h713-tv")                                   # h713-tv answers, but not with a white balance: unknown
        self.assertNotIn("colour", self.call("controls")["features"])


# a stand-in h713-tv with a memory: `ctl get|set gamma` and `colour_temperature` as gamma.c answers them (docs/tools/h713-tv.md)
TV_LOOK = r"""
dir="DIR"
absent() { [ -f "$dir/nocurves" ] && { echo "error $1 is not available: the board's curves were not read"; return 0; }; return 1; }
gamma() { absent gamma && return; g=$(cat "$dir/gamma")
  case "$g" in 0) n=1.8;; 1) n=2.0;; 2) n=2.1;; 3) n=2.2;; 4) n=2.4;; esac; echo "ok gamma = $g ($n)"; }
temp() { absent colour_temperature && return; t=$(cat "$dir/ctemp")
  case "$(cat "$dir/preset")" in cinema|hdr) a=warm;; vivid) a=cool;; *) a=normal;; esac
  if [ "$t" = auto ]; then echo "ok colour_temperature = auto ($a)"
  elif grep -qx "$t" "$dir/missing"; then echo "ok colour_temperature = $t (normal: this board has no $t curve)"
  else echo "ok colour_temperature = $t"; fi; }
case "$*" in
  "ctl get gamma") gamma ;;
  "ctl get colour_temperature") temp ;;
  "ctl set gamma "*) set -- $*; echo "$4" > "$dir/gamma"; gamma ;;
  "ctl set colour_temperature "*) set -- $*; echo "$4" > "$dir/ctemp"; temp ;;
  "ctl preset "*) set -- $*; echo "$3" > "$dir/preset"; echo "ok preset $3 (the compiled-in table)" ;;
  "ctl status brief") printf 'ok status\nmode            automatic\npreset          %s (from the device data)\n' "$(cat "$dir/preset")" ;;
  *) echo "ok h713-tv $*" ;;
esac
"""


class LookTest(Bench):
    """Gamma and colour temperature: two verbs that are one `ctl set` each, and `look` that reads them.  h713-settings (rows.c) offers the
    same two on the projector's own screen."""

    def setUp(self):
        super().setUp()
        self.fake.script("h713-tv", TV_LOOK.replace("DIR", self.fake.dir))
        self.state(3, "auto", "standard")

    def state(self, gamma, ctemp, preset, missing=""):
        for name, text in (("gamma", str(gamma)), ("ctemp", ctemp), ("preset", preset), ("missing", missing)):
            with open(os.path.join(self.fake.dir, name), "w") as handle:
                handle.write(text + "\n")

    def tv(self):
        return [c for c in self.fake.calls() if c.startswith("h713-tv")]

    def test_every_level_and_every_temperature_is_one_ctl_set_of_a_fixed_word(self):
        for level in panel.GAMMA_LEVELS:
            self.fake.forget()
            self.assertTrue(self.call("gamma", [int(level)])["ok"])        # the page sends a number, a text works too
            self.assertTrue(self.call("gamma", [level])["ok"])
            self.assertEqual(self.fake.calls(), ["h713-tv ctl set gamma " + level] * 2)
        for name in panel.TEMPERATURES:
            self.fake.forget()
            self.assertTrue(self.call("colour_temperature", [name])["ok"])
            self.assertEqual(self.fake.calls(), ["h713-tv ctl set colour_temperature " + name])
        self.assertEqual(panel.GAMMA_LEVELS, ("0", "1", "2", "3", "4"))             # h713-tv's levels: 1.8 2.0 2.1 2.2 2.4
        self.assertEqual(panel.TEMPERATURES, ("auto", "warm", "normal", "cool"))

    def test_a_value_outside_its_list_starts_nothing(self):
        for verb, args in (("gamma", [5]), ("gamma", [-1]), ("gamma", ["2.2"]), ("gamma", ["3; reboot"]), ("gamma", [True]),
                           ("gamma", [""]), ("gamma", []), ("gamma", [3, 3]), ("gamma", [[3]]), ("gamma", [None]),
                           ("colour_temperature", ["hot"]), ("colour_temperature", ["AUTO"]), ("colour_temperature", ["auto; reboot"]),
                           ("colour_temperature", [True]), ("colour_temperature", [0]), ("colour_temperature", []),
                           ("colour_temperature", ["warm", "cool"]), ("colour_temperature", [["warm"]]), ("look", [1, 2, 3, 4, 5])):
            answer = self.call(verb, args)
            self.assertFalse(answer["ok"], (verb, args, answer))
            self.assertTrue(answer["line"].startswith("error"), answer)
        self.assertEqual(self.fake.calls(), [])
        with open(os.path.join(self.fake.dir, "gamma")) as handle:
            self.assertEqual(handle.read().strip(), "3")

    def test_look_says_what_is_set_and_what_auto_comes_to(self):
        for gamma, name, ctemp, preset, now in ((3, "2.2", "auto", "standard", "normal"), (0, "1.8", "auto", "cinema", "warm"),
                                               (4, "2.4", "auto", "vivid", "cool"), (2, "2.1", "cool", "cinema", "cool"),
                                               (1, "2.0", "normal", "vivid", "normal"), (3, "2.2", "auto", "hdr", "warm")):
            self.state(gamma, ctemp, preset)
            self.assertEqual(self.call("look"), {"ok": True, "line": "ok look", "gamma": gamma, "gamma_name": name, "ct": ctemp,
                                                 "ct_now": now, "preset": preset})

    def test_what_a_tap_set_is_what_look_reads(self):
        for level in (0, 4, 2, 3):
            self.assertTrue(self.call("gamma", [level])["ok"])
            self.assertEqual(self.call("look")["gamma"], level)
        for name in ("warm", "cool", "normal", "auto"):
            self.assertTrue(self.call("colour_temperature", [name])["ok"])
            self.assertEqual(self.call("look")["ct"], name)

    def test_the_preset_moves_auto_and_leaves_a_temperature_that_was_set(self):
        self.assertTrue(self.call("preset", ["cinema"])["ok"])
        self.assertEqual((self.call("look")["ct"], self.call("look")["ct_now"]), ("auto", "warm"))
        self.assertTrue(self.call("colour_temperature", ["cool"])["ok"])
        self.assertTrue(self.call("preset", ["standard"])["ok"])
        self.assertEqual((self.call("look")["ct"], self.call("look")["ct_now"], self.call("look")["preset"]), ("cool", "cool", "standard"))

    def test_a_board_without_the_curve_says_which_one_is_used(self):
        self.state(3, "warm", "standard", missing="warm")
        answer = self.call("look")
        self.assertEqual((answer["ct"], answer["ct_now"]), ("warm", "normal"))

    def test_look_only_reads_and_does_not_wait_for_the_lock(self):
        self.assertTrue(self.panel.lock.acquire(False))        # a command is running
        try:
            self.assertTrue(self.call("look")["ok"])
            with unittest.mock.patch.object(panel, "LOCK_WAIT_S", 0.1):
                self.assertTrue(self.call("gamma", [1])["busy"])
            self.assertTrue(all(" get " in c or c.endswith("status brief") for c in self.tv()), self.tv())
        finally:
            self.panel.lock.release()

    def test_without_the_curves_look_is_refused_with_the_reason_and_the_tool_has_the_last_word(self):
        open(os.path.join(self.fake.dir, "nocurves"), "w").close()
        answer = self.call("look")
        self.assertFalse(answer["ok"])
        self.assertIn("not available (the board's curves were not read)", answer["line"])
        self.assertFalse(self.call("gamma", [1])["ok"])                      # the tool refuses, its line is the answer
        self.assertIn("is not available", self.call("colour_temperature", ["cool"])["line"])
        # h713-tv not there at all: named, and nothing is sent
        self.fake.forget()
        gone = panel.Panel(tools=os.path.join(self.fake.dir, "nothing"), etc=self.etc)
        answer = gone.call({"verb": "look"})
        self.assertFalse(answer["ok"])
        self.assertIn("h713-tv did not say what the gamma is", answer["line"])
        self.assertEqual(self.fake.calls(), [])

    def test_controls_say_whether_the_board_has_the_curves(self):
        self.assertTrue(self.call("controls")["features"]["gamma"])
        open(os.path.join(self.fake.dir, "nocurves"), "w").close()
        self.assertFalse(self.call("controls")["features"]["gamma"])
        self.fake.tool("h713-tv")                                   # h713-tv answers, but not with a gamma: unknown, the controls stay
        self.assertNotIn("gamma", self.call("controls")["features"])

    def test_look_names_a_preset_only_from_the_list(self):
        self.state(3, "auto", "something-new")
        self.assertEqual(self.call("look")["preset"], "")

class PageTest(unittest.TestCase):
    def setUp(self):
        with open(PAGE, "rb") as handle:
            self.page = handle.read().decode("utf-8")

    def test_seven_tabs_and_their_sections(self):
        for name in ("projection", "picture", "colour", "sound", "remote", "network", "system"):
            self.assertIn('id="tab-%s"' % name, self.page)
            self.assertIn('class="screen%s" id="%s"' % (" on" if name == "projection" else "", name), self.page)
            self.assertIn('"%s"' % name, self.page.split("function show(")[1].split("}")[0])

    def test_what_cannot_be_taken_back_asks_first(self):
        for verb in ("reboot", "poweroff", "replug", "save_off"):
            self.assertRegex(self.page, r"ask\('[^']+', '%s'\)" % verb)
        self.assertIn("window.confirm(", self.page.split("function wifiApply")[1])
        self.assertIn("Forget and re-pair", self.page)                # the mockup's second state
        for text in ("Hold LEFT + RIGHT on the remote", "searching", "Re-pair remote", "always on"):
            self.assertIn(text, self.page)

    def test_the_page_never_fills_a_password_and_never_names_what_stays_out(self):
        self.assertNotIn("wifi.password", self.page)
        self.assertNotIn(".password =", self.page)
        for word in ("focus_command", "rpc", "block1", "authorized", "ssh-"):
            self.assertNotIn(word, self.page)
        self.assertIn('"X-Requested-With": "h713-panel"', self.page)

    def test_the_colour_tab_asks_what_the_tool_checks(self):
        def slider(name):
            return re.search(r'id="%s" min="(-?\d+)" max="(-?\d+)" step="(\d+)"' % name, self.page).groups()
        for name, check in (("wb-warm", panel.WB_SLIDER), ("wb-tint", panel.WB_SLIDER),
                            ("cm-hue", panel.CM_SLIDER), ("cm-sat", panel.CM_SLIDER)):
            self.assertEqual(tuple(int(n) for n in slider(name)), check.spec[1:], name)
        self.assertEqual([p[0] for p in json.loads(re.search(r"var PRIMS = (\[\[.*?\]\]);", self.page, re.S).group(1))],
                         list(panel.PRIMARIES))
        self.assertEqual(re.findall(r"cmSend\('(\w+)'\)", self.page), list(panel.CM_PARTS))
        # a slider sends when it is let go, not on every pixel of the drag
        for name in ("wb-warm", "wb-tint", "cm-hue", "cm-sat"):
            tag = re.search(r'<input[^>]*id="%s"[^>]*>' % name, self.page).group(0)
            self.assertRegex(tag, r'onchange="(wb|cm)Send\(')
            self.assertNotRegex(re.search(r'oninput="([^"]*)"', tag).group(1), r"Send\(|act\(|api\(")

    def test_the_colour_tab_sends_its_arguments_in_the_order_the_tool_checks(self):
        # the page is not run here, so the order is read from its source: wb_tune takes cool, magenta; cm_set colour, part, step
        self.assertIn('act("wb_tune", [WB.cool, WB.magenta])', self.page)
        self.assertIn('act("cm_set", [PRIM, comp, s[comp]])', self.page)
        self.assertIn("s[comp] = +id(\"cm-\" + comp).value;", self.page)
        self.assertEqual(len(re.findall(r"act\(['\"]cm_reset['\"]\)\.then\(loadColour\)", self.page)), 1)
        self.assertIn('<button onclick="wbReset()">Reset white balance</button>', self.page)        # wb_reset, and the temperature to Auto
        self.assertIn('act("wb_reset")', self.page)

    def test_the_colour_tab_goes_with_the_calibration(self):
        for anchor in ('id="tab-colour"', 'class="screen" id="colour"'):         # the tab is there with either: the calibration or the curves
            self.assertIn('data-needs-any="colour gamma"', re.search(r"<[^<>]*" + anchor + r"[^<>]*>", self.page).group(0), anchor)
        self.assertIn('<div class="card" data-needs="colour colour-manager">\n    <h2>Colour</h2>', self.page)   # the primaries: calibration and a colour manager that works
        self.assertIn('if (name === "colour" && READY) { if (has("colour")) { loadColour(); } loadLook(); }', self.page)
        self.assertIn('if (id("colour").hidden && id("colour").classList.contains("on")) { show("projection"); }', self.page)

    def test_the_picture_and_colour_tabs_offer_what_the_tool_checks(self):
        gamma = re.search(r'<div class="seg" id="gm".*?</div>', self.page, re.S).group(0)
        self.assertEqual(re.findall(r'id="gm-(\d)" onclick="gammaSet\((\d)\)">([\d.]+)<', gamma),
                         [(n, n, w) for n, w in zip(panel.GAMMA_LEVELS, ("1.8", "2.0", "2.1", "2.2", "2.4"))])
        temperatures = re.search(r'<div class="seg" id="ct".*?</div>', self.page, re.S).group(0)
        self.assertEqual(re.findall(r"id=\"ct-(\w+)\" onclick=\"ctSet\('(\w+)'\)\">", temperatures),
                         [(n, n) for n in panel.TEMPERATURES])
        self.assertIn('act("colour_temperature", [name]).then(loadLook)', self.page)
        self.assertIn('act("gamma", [level]).then(loadLook)', self.page)
        self.assertIn('api("look")', self.page)
        self.assertEqual(re.findall(r'GAMMAS = (\[[^\]]*\])', self.page), [json.dumps(["1.8", "2.0", "2.1", "2.2", "2.4"])])

    def test_the_gamma_and_temperature_blocks_go_with_the_curves_and_the_fine_tuning_with_the_calibration(self):
        for anchor in ('<h3>Colour temperature</h3>', '<h3>Gamma</h3>'):
            block = self.page[:self.page.index(anchor)].rsplit("<div", 1)[1]
            self.assertTrue(block.startswith(' data-needs="gamma">'), anchor)
        self.assertIn('<div data-needs="colour">\n    <h3 data-needs="gamma">Fine tuning</h3>', self.page)
        self.assertIn('e.hidden = !e.getAttribute("data-needs-any").split(" ").some(has);', self.page)
        self.assertIn("if (!has(\"gamma\")) { return Promise.resolve(); }", self.page)      # no curves: nothing is asked, no error line

    def test_the_page_decides_nothing_about_the_temperature(self):
        # what auto comes to and the picture mode are read from the tool: the page holds no table of them
        self.assertNotIn("CT_OF", self.page)
        self.assertIn("LOOK.ct_now", self.page)
        self.assertEqual(re.findall(r'press\("pr-" \+ p', self.page), ['press("pr-" + p'])
        self.assertIn('["presets", c.presets, "preset", "pr-"]', self.page)

    def test_no_dash_characters(self):
        for path in (PAGE, TOOL, os.path.join(HERE, "test_h713_panel.py")):
            with open(path, "rb") as handle:
                text = handle.read().decode("utf-8")
            self.assertNotIn(chr(0x2014), text, path)
            self.assertNotIn(chr(0x2013), text, path)


class CrossSiteTest(unittest.TestCase):
    def test_a_post_without_the_pages_header_is_refused(self):
        fake = Fakes()
        fake.tool("h713-warp")
        server = panel.serve(panel.Panel(tools=fake.dir), b"x", "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request("http://127.0.0.1:%d/api" % server.server_address[1],
                                             data=b'{"verb": "warp", "args": ["on"]}',
                                             headers={"Content-Type": "text/plain"})
            answer = json.loads(urllib.request.urlopen(request, timeout=10).read().decode("utf-8"))
            self.assertFalse(answer["ok"])
            self.assertEqual(fake.calls(), [])
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()
            fake.close()


if __name__ == "__main__":
    sys.exit(not unittest.main(exit=False).result.wasSuccessful())
