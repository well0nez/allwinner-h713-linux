"""Tests for h713-mode (the mode before a sleep, the way back after it) against a made-up root, systemctl and
h713-mips-restart: no device, no systemd."""
import os
import subprocess
import tempfile
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "h713-mode")


class Root:
    def __init__(self, active=(), mips=None, restart_rc=0):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(self.p("etc/h713/launcher.d"))
        os.makedirs(self.p("run"))
        self.log = self.p("log")
        self.put("etc/h713/launcher.d/10-hdmi.conf", "label = HDMI input\nicon = hdmi\nexec = /x/h713-mode hdmi\nfallback = yes\n")
        self.put("etc/h713/launcher.d/20-kodi.conf",
                 "# unit = not.this.one.service\nlabel = Kodi\nicon = film\nunit = h713-kodi.service  # the mode\n")
        self.put("etc/h713/launcher.d/30-desktop.conf", "label = Desktop\nicon = desk\n  unit=h713-desktop.service\n")
        self.put("etc/h713/launcher.d/90-standby.conf", "label = Standby\nicon = power\nexec = systemctl suspend\n")
        self.active = list(active)
        self.put("systemctl", '#!/bin/sh\necho "systemctl $@" >> %s\n'
                 'if [ "$1" = is-active ]; then case " %s " in *" $2 "*) echo active; exit 0;; esac; echo inactive; exit 3; fi\n'
                 'exit 0\n' % (self.log, " ".join(self.active)))
        self.state = "sys/bus/platform/drivers/sun50i-h713-mips/3061000.mips/state"
        if mips:
            self.put(self.state, "%s\n0x02001600=0x0\n" % mips)
        self.put("tv", '#!/bin/sh\necho "tv $@" >> %s\nexit 0\n' % self.log)
        self.put("restart", '#!/bin/sh\necho mips-restart >> %s\ncat %s > %s 2>/dev/null\nsed -i 1s/.*/running/ %s\nexit %d\n'
                 % (self.log, self.p("run/h713-mode.resume"), self.p("seen"), self.p(self.state), restart_rc))
        for f in ("systemctl", "restart", "tv"):
            os.chmod(self.p(f), 0o755)

    def __del__(self):
        self.tmp.cleanup()

    def p(self, rel):
        return os.path.join(self.d, rel)

    def put(self, rel, text):
        os.makedirs(os.path.dirname(self.p(rel)), exist_ok=True)
        with open(self.p(rel), "w") as f:
            f.write(text)

    def calls(self):
        try:
            with open(self.log) as f:
                return [l.strip() for l in f if not l.startswith("systemctl is-active")]
        except OSError:
            return []

    def mode(self, *args):
        env = dict(os.environ, H713_ROOT=self.d, H713_SYSTEMCTL=self.p("systemctl"), H713_MIPS_RESTART=self.p("restart"), H713_TV=self.p("tv"))
        env.pop("JOURNAL_STREAM", None)
        return subprocess.run(["sh", TOOL] + list(args), env=env, capture_output=True, text=True, timeout=20)

    def seen_by_restart(self):
        """what /run/h713-mode.resume held while h713-mips-restart ran"""
        try:
            with open(self.p("seen")) as f:
                return f.read().split()
        except OSError:
            return None

    def memory(self):
        try:
            with open(self.p("run/h713-mode.resume")) as f:
                return f.read().split()
        except OSError:
            return None


class ModeTest(unittest.TestCase):
    def test_status_names_the_running_mode_unit_or_hdmi(self):
        self.assertEqual(Root().mode("status").stdout.strip(), "hdmi")
        self.assertEqual(Root(active=["h713-kodi.service"]).mode("status").stdout.strip(), "h713-kodi.service")

    def test_only_the_units_of_the_entries_count(self):
        r = Root(active=["not.this.one.service", "something.service"])      # a comment's unit, and a unit no entry names
        self.assertEqual(r.mode("status").stdout.strip(), "hdmi")

    def test_hdmi_ends_every_mode_unit_and_leaves_the_source_on_auto(self):
        r = Root(active=["h713-kodi.service"])
        self.assertEqual(r.mode("hdmi").returncode, 0)
        self.assertEqual(r.calls(), ["tv ctl source hdmi", "systemctl stop h713-kodi.service", "systemctl stop h713-desktop.service",
                                     "tv ctl source auto"])
        # the picture first: the source goes to hdmi before any unit is ended (the ring is back while Kodi still quits); `auto` last,
        # when no client is left to take the panel again - `source` is not the user's word (Marco 17.10.2026), it stays `auto`

    def test_hdmi_with_no_mode_running_only_says_auto(self):
        r = Root()
        self.assertEqual(r.mode("hdmi").returncode, 0)
        self.assertEqual(r.calls(), ["systemctl stop h713-kodi.service", "systemctl stop h713-desktop.service", "tv ctl source auto"])    # no hdmi/auto toggle of the ring

    def test_hdmi_marks_the_end_as_the_users_before_anything_is_ended(self):
        r = Root(active=["h713-kodi.service"])
        self.assertFalse(os.path.exists(r.p("run/h713-mode.ended")))
        r.mode("hdmi")
        self.assertTrue(os.path.exists(r.p("run/h713-mode.ended")))       # h713-keys opens no launcher for an end that came after it
        r2 = Root(active=["h713-kodi.service"])
        r2.mode("sleep-pre")
        self.assertFalse(os.path.exists(r2.p("run/h713-mode.ended")))     # a sleep has its own mark: the resume file

    def test_hdmi_without_the_run_directory_still_ends_the_modes(self):
        r = Root(active=["h713-kodi.service"])
        os.rmdir(r.p("run"))
        out = r.mode("hdmi")
        self.assertEqual(out.returncode, 0)
        self.assertIn("cannot write", out.stderr)
        self.assertIn("systemctl stop h713-kodi.service", r.calls())

    def test_before_a_sleep_kodi_is_remembered_and_ended(self):
        r = Root(active=["h713-kodi.service"])
        self.assertEqual(r.mode("sleep-pre").returncode, 0)
        self.assertEqual(r.memory(), ["h713-kodi.service"])
        self.assertEqual(r.calls(), ["systemctl stop h713-kodi.service"])      # only what ran

    def test_before_a_sleep_in_hdmi_nothing_is_remembered(self):
        r = Root()
        r.mode("sleep-pre")
        self.assertEqual(r.memory(), [])
        self.assertEqual(r.calls(), [])

    def test_after_a_sleep_the_picture_comes_back_and_then_kodi(self):
        r = Root(active=["h713-kodi.service"], mips="parked")
        r.mode("sleep-pre")
        out = r.mode("sleep-post")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(r.calls(), ["systemctl stop h713-kodi.service", "mips-restart",
                                     "systemctl start --no-block h713-kodi.service"])    # the picture path first
        self.assertIsNone(r.memory())                                       # taken: nothing remembered any more
        self.assertIn("back to h713-kodi.service", out.stderr)

    def test_a_standby_from_hdmi_comes_back_to_hdmi(self):
        r = Root(mips="parked")
        r.mode("sleep-pre")
        r.mode("sleep-post")
        self.assertEqual(r.calls(), ["mips-restart"])

    def test_a_sleep_that_did_not_park_the_mips_starts_no_restart_but_kodi(self):
        r = Root(active=["h713-kodi.service"], mips="running")
        r.mode("sleep-pre")
        r.mode("sleep-post")
        self.assertEqual(r.calls(), ["systemctl stop h713-kodi.service", "systemctl start --no-block h713-kodi.service"])

    def test_no_mips_driver_is_no_restart(self):
        r = Root(active=["h713-kodi.service"])
        r.mode("sleep-pre")
        out = r.mode("sleep-post")
        self.assertNotIn("mips-restart", r.calls())
        self.assertIn("not parked", out.stderr)

    def test_a_failed_restart_is_said_and_kodi_is_still_asked_for(self):
        r = Root(active=["h713-kodi.service"], mips="parked", restart_rc=3)
        r.mode("sleep-pre")
        out = r.mode("sleep-post")
        self.assertEqual(out.returncode, 0)
        self.assertIn("h713-mips-restart ended with 3", out.stderr)
        self.assertIn("systemctl start --no-block h713-kodi.service", r.calls())

    def test_the_post_unit_twice_does_nothing_the_second_time(self):
        """h713-power runs it once more after a standby that did not happen: nothing remembered, nothing parked"""
        r = Root(active=["h713-kodi.service"], mips="parked")
        r.mode("sleep-pre")
        r.mode("sleep-post")
        before = r.calls()
        r.mode("sleep-post")
        self.assertEqual(r.calls(), before)

    def test_a_rescue_restarts_the_mips_and_brings_the_mode_back(self):
        """h713-tv-rescue.service: the restart stops h713-warp, which ends Kodi (BindsTo=); the mode comes back like after a sleep"""
        r = Root(active=["h713-kodi.service"], mips="running")
        out = r.mode("rescue")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(r.calls(), ["mips-restart", "systemctl start --no-block h713-kodi.service"])
        self.assertEqual(r.seen_by_restart(), ["h713-kodi.service"])    # remembered before the restart: h713-keys opens no launcher for the end
        self.assertIsNone(r.memory())                                   # and forgotten after it
        self.assertIn("back to h713-kodi.service", out.stderr)

    def test_a_rescue_brings_back_the_desktop_too(self):
        r = Root(active=["h713-desktop.service"], mips="running")
        r.mode("rescue")
        self.assertEqual(r.calls(), ["mips-restart", "systemctl start --no-block h713-desktop.service"])

    def test_a_rescue_in_hdmi_only_restarts_the_mips(self):
        r = Root(mips="running")
        self.assertEqual(r.mode("rescue").returncode, 0)
        self.assertEqual(r.calls(), ["mips-restart"])
        self.assertEqual(r.seen_by_restart(), [])      # no resume file: nothing ends
        self.assertIsNone(r.memory())

    def test_a_rescue_whose_restart_failed_still_asks_for_the_mode(self):
        """as after a sleep: the restart may have ended the mode before it failed (exit 2 comes after the stop of h713-warp)"""
        r = Root(active=["h713-kodi.service"], mips="running", restart_rc=3)
        out = r.mode("rescue")
        self.assertEqual(out.returncode, 0)
        self.assertIn("h713-mips-restart ended with 3", out.stderr)
        self.assertIn("systemctl start --no-block h713-kodi.service", r.calls())
        self.assertIsNone(r.memory())

    def test_a_rescue_does_not_empty_what_a_sleep_remembers(self):
        """h713-tv failing between h713-sleep-pre and h713-sleep-post: no mode runs, the file is the sleep's"""
        r = Root(mips="running")
        r.put("run/h713-mode.resume", "h713-kodi.service\n")        # h713-sleep-pre ended Kodi and wrote this
        r.mode("rescue")
        self.assertEqual(r.seen_by_restart(), ["h713-kodi.service"])
        self.assertEqual(r.calls()[-1], "systemctl start --no-block h713-kodi.service")

    def test_the_rescue_unit_runs_the_mode_tool(self):
        """the unit is what makes `rescue` run: not h713-mips-restart alone, which would leave Kodi ended"""
        with open(os.path.join(os.path.dirname(TOOL), "h713-tv-rescue.service")) as f:
            unit = f.read()
        self.assertIn("\nExecStart=/usr/local/sbin/h713-mode rescue\n", unit)
        self.assertIn("\nConditionPathExists=/usr/local/sbin/h713-mips-restart\n", unit)   # the restart is still what the mode tool calls

    def test_a_wrong_word_is_a_usage_error(self):
        self.assertEqual(Root().mode("kodi").returncode, 2)


if __name__ == "__main__":
    unittest.main()
