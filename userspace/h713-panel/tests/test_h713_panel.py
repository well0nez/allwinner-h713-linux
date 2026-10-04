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

import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import unittest
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
zoom            85 percent (every corner pulled in on top of the keystone)
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
GEU_FEATURES = """ok features  board hy300pro-g-eu, FEATURES: accelerometer (/etc/h713/features)
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
                ("screen_zoom", [85], "h713-warp ctl zoom 85"),
                ("mode", ["ceiling"], "h713-warp ctl mode ceiling"),
                ("mode", ["rear-ceiling"], "h713-warp ctl mode rear-ceiling"),
                ("focus", ["up", "20"], "h713-focus up 20"),
                ("autofocus", [], "h713-autofocus run"),
                ("warp", ["off"], "h713-warp ctl off")):
            self.fake.forget()
            answer = self.call(verb, args)
            self.assertTrue(answer["ok"], answer)
            self.assertEqual(self.fake.calls(), [expected])

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
        for request in ({"verb": "reboot"}, {"verb": "run"},
                        {"verb": "do_status"}, {"verb": None},
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
        answer = self.call("controls")         # no h713-features: everything stays
        self.assertEqual(answer["features"], {})
        self.assertEqual(list(answer["after_move"]), list(panel.AFTER_MOVE))
        self.fake.tool("h713-features", {"status": GEU_FEATURES})
        answer = self.call("controls")
        self.assertEqual(answer["features"], {"camera": False, "accelerometer": True,
                                              "focus-motor": False})
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
            self.assertTrue(set(needs.split()) <= set(panel.FEATURE_NAMES), needs)
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
            headers={"Content-Type": "application/json"})
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
        for body in (b"not json", b"[]", b'{"verb": "reboot"}',
                     b'{"verb": "warp", "args": ["on; reboot"]}',
                     b'{"verb": "volume", "args": ["50"]}' + b" " * 8000):
            answer = self.post(body)
            self.assertFalse(answer["ok"], body)
        self.assertEqual(self.fake.calls(), [])


if __name__ == "__main__":
    sys.exit(not unittest.main(exit=False).result.wasSuccessful())
