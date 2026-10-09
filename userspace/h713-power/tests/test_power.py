"""Tests for h713-power against a made-up /sys, /dev and systemctl (no device, no logind)."""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "h713-power")
S = 10**9


def load():
    loader = importlib.machinery.SourceFileLoader("h713_power", TOOL)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("h713_power", loader))
    loader.exec_module(mod)
    return mod


class Root:
    """A temporary root: power.conf, mem_sleep, suspend_stats, the arisc state, one event device; with mips the
    state of sun50i-h713-mips, and an h713-mips-restart stand-in that logs into the systemctl log."""

    def __init__(self, mem_sleep="s2idle [deep]", ready="1", conf="", mips=None, suspend_ok=True, restart_rc=0):
        self.tmp = tempfile.TemporaryDirectory()        # removed with this object
        self.dir = self.tmp.name
        self.put("etc/h713/power.conf", conf)
        self.put("sys/power/mem_sleep", mem_sleep)
        self.put("sys/power/suspend_stats/success", "0")
        self.put("sys/power/suspend_stats/fail", "0")
        self.put("sys/bus/platform/drivers/sun50i-h713-arisc/100000.arisc/state",
                 "version=5\nwake=none\nresume_ns=0\nready=%s\n" % ready)
        self.put("sys/class/input/event0/device/capabilities/key", "10000000000000 0")
        self.put("sys/class/input/event0/device/id/bustype", "0019")
        self.fifo = self.p("dev/input/event0")
        os.makedirs(os.path.dirname(self.fifo))
        os.mkfifo(self.fifo)
        self.log = self.p("systemctl.log")
        self.put("systemctl", '#!/bin/sh\necho "$@" >> %s\n[ "$1" = suspend ] && echo 1 > %s\nexit 0\n'
                 % (self.log, self.p("sys/power/suspend_stats/" + ("success" if suspend_ok else "fail"))))
        os.chmod(self.p("systemctl"), 0o755)
        if mips:
            self.put("sys/bus/platform/drivers/sun50i-h713-mips/3061000.mips/state",
                     "%s\n0x02001600=0x00000000 0x0200160c=0x00000000\n" % mips)
        self.put("mips-restart", '#!/bin/sh\necho mips-restart >> %s\nexit %d\n' % (self.log, restart_rc))
        os.chmod(self.p("mips-restart"), 0o755)
        self.restart_tool = self.p("mips-restart")

    def __del__(self):
        self.tmp.cleanup()                               # now, without the ResourceWarning of a late cleanup

    def p(self, rel):
        return os.path.join(self.dir, rel)

    def put(self, rel, text):
        os.makedirs(os.path.dirname(self.p(rel)), exist_ok=True)
        with open(self.p(rel), "w") as f:
            f.write(text)

    def press(self, *events):
        """Run 'h713-power run --once' while (value, delay_s) events reach the fifo; -> systemctl calls."""
        def feed():
            with open(self.fifo, "wb") as f:
                for value, delay in events:
                    time.sleep(delay)
                    f.write(struct_event(value))
                    f.flush()
                time.sleep(1.5)
        threading.Thread(target=feed, daemon=True).start()
        env = dict(os.environ, H713_POWER_ROOT=self.dir, H713_SYSTEMCTL=self.p("systemctl"),
                   H713_MIPS_RESTART=self.restart_tool)
        out = subprocess.run([sys.executable, TOOL, "run", "--once"], env=env, capture_output=True,
                             text=True, timeout=20)
        calls = []
        if os.path.exists(self.log):
            with open(self.log) as f:
                calls = f.read().split()
        return calls, out.stdout


def struct_event(value):
    ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    return EVENT.pack(ns // S, ns % S // 1000, 1, 116, value)


EVENT = load().EVENT


class KeyRules(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.k = self.m.Key()

    def ev(self, ts, value, state=None):
        return self.k.event(ts, value, 3 * S, 2 * S, state or {})

    def test_a_short_press_acts_on_the_release(self):
        self.assertIsNone(self.ev(10 * S, 1))
        self.assertIsNone(self.ev(10 * S, 2))                  # autorepeat
        self.assertEqual(self.ev(10 * S + S // 3, 0), "short")

    def test_a_long_press_fires_once_while_held_and_not_again_on_release(self):
        self.ev(10 * S, 1)
        self.assertIsNone(self.k.tick(12 * S, 3 * S))
        self.assertEqual(self.k.tick(13 * S, 3 * S), "long")
        self.assertIsNone(self.k.tick(14 * S, 3 * S))
        self.assertIsNone(self.ev(15 * S, 0))

    def test_the_press_that_woke_the_box_is_ignored_with_its_release(self):
        key_wake = {"wake": "key", "resume_ns": str(100 * S)}
        self.assertIsNone(self.ev(100 * S + S // 2, 1, key_wake))
        self.assertIsNone(self.ev(101 * S, 0, key_wake))
        self.ev(103 * S, 1, key_wake)                        # after the window: a new press
        self.assertEqual(self.ev(103 * S + S // 5, 0, key_wake), "short")

    def test_after_a_timer_wake_the_first_press_counts(self):
        timer_wake = {"wake": "timer", "resume_ns": str(100 * S)}
        self.ev(100 * S + S // 2, 1, timer_wake)
        self.assertEqual(self.ev(100 * S + S, 0, timer_wake), "short")


class Readiness(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def refusal(self, **kw):
        r = Root(**kw)
        self.m.ROOT = r.dir
        return self.m.standby_refusal(self.m.config()[0])

    def test_deep_and_ready_allow_the_standby(self):
        self.assertIsNone(self.refusal())

    def test_s2idle_crust_not_ready_or_short_poweroff_refuse_it(self):
        self.assertIn("not [deep]", self.refusal(mem_sleep="[s2idle] deep"))
        self.assertIn("ready=0", self.refusal(ready="0"))
        self.assertIn("short = poweroff", self.refusal(conf="short = poweroff\n"))

    def test_a_bad_config_line_is_named_and_its_default_kept(self):
        r = Root(conf="short = sleep\nlong_s = 5\n")
        self.m.ROOT = r.dir
        conf, bad = self.m.config()
        self.assertEqual((conf["short"], conf["long_s"]), ("standby", "5"))
        self.assertEqual(len(bad), 1)

    def test_the_power_key_bit_in_a_capability_bitmap(self):
        self.assertTrue(self.m.has_power_key("10000000000000 0"))
        self.assertFalse(self.m.has_power_key("0 ffffffffffffffff"))


class Verdict(unittest.TestCase):
    """suspend() on a clock that jumps where systemd freezes the tool for the standby (awake time, not sleep)."""

    def verdict(self, awake_s=None, success="1", fail="0", late=0):
        m, r = load(), Root()
        m.ROOT, m.SYSTEMCTL = r.dir, ["true"]
        clock, sleeps = [1000.0], [0]

        def sleep(s):
            clock[0] += s
            sleeps[0] += 1
            if awake_s is not None and sleeps[0] == 1:
                clock[0] += awake_s                     # freeze, the devices' suspend and resume
            if awake_s is not None and sleeps[0] == 1 + late:
                r.put("sys/power/suspend_stats/success", success)
                r.put("sys/power/suspend_stats/fail", fail)
        return m.suspend(lambda: clock[0], sleep), clock[0] - 1000

    def test_a_standby_that_took_longer_than_30_s_awake_is_a_standby(self):
        self.assertTrue(self.verdict(awake_s=35)[0])
        self.assertTrue(self.verdict(awake_s=35, late=3)[0])   # the counter moves only after the thaw

    def test_a_short_standby_and_a_refused_one(self):
        self.assertTrue(self.verdict(awake_s=5)[0])
        self.assertFalse(self.verdict(awake_s=35, success="0", fail="1")[0])

    def test_no_verdict_in_30_s_is_a_refusal(self):
        ok, waited = self.verdict()
        self.assertFalse(ok)
        self.assertTrue(30 <= waited < 31, waited)


class Run(unittest.TestCase):
    def test_a_short_press_suspends(self):
        calls, out = Root().press((1, 0.3), (0, 0.2))
        self.assertEqual(calls, ["suspend"], out)

    def test_a_short_press_without_deep_sleep_powers_off(self):
        calls, out = Root(mem_sleep="[s2idle] deep").press((1, 0.3), (0, 0.2))
        self.assertEqual(calls, ["poweroff"], out)
        self.assertIn("not [deep]", out)

    def test_a_held_key_powers_off_without_a_release(self):
        calls, out = Root(conf="long_s = 0.5\n").press((1, 0.3))
        self.assertEqual(calls, ["poweroff"], out)
        self.assertIn("long press", out)


class KeysOfTheStandby(unittest.TestCase):
    """Review U1 (09.10.2026): what the keys sent while suspend() waited is dropped, not judged after the wake."""

    def test_queued_events_and_a_held_key_are_forgotten(self):
        m = load()
        r, w = os.pipe()
        os.set_blocking(r, False)
        key = m.Key()
        key.event(10 * S, 1, 3 * S, 2 * S, {})                  # held when the box fell asleep
        for value in (1, 0):                                   # a second press while it fell asleep
            os.write(w, m.EVENT.pack(11, 0, m.EV_KEY, m.KEY_POWER, value))
        buf = {"p": b"\0\0"}
        try:
            m.drop_queued({"p": (r, True, key)}, buf)
            self.assertIsNone(key.down)
            self.assertNotIn("p", buf)
            with self.assertRaises(BlockingIOError):
                os.read(r, 64)
            self.assertIsNone(key.event(20 * S, 0, 3 * S, 2 * S, {}))   # its release after the wake: nothing
        finally:
            os.close(r)
            os.close(w)


class AfterTheStandby(unittest.TestCase):
    """A standby parks the display MIPS; h713-mips-restart brings the picture back, only from the park."""

    SHORT = ((1, 0.3), (0, 0.2))

    def test_a_parked_mips_is_restarted_after_the_standby(self):
        calls, out = Root(mips="parked").press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "mips-restart"], out)
        self.assertIn("the display MIPS is parked: h713-mips-restart", out)
        self.assertIn("h713-mips-restart: the picture path is back", out)

    def test_a_running_mips_or_no_driver_is_left_alone(self):
        calls, out = Root(mips="running").press(*self.SHORT)
        self.assertEqual(calls, ["suspend"], out)
        self.assertIn("h713-power: the display MIPS is running: no restart", out)
        calls, out = Root().press(*self.SHORT)
        self.assertEqual(calls, ["suspend"], out)
        self.assertIn("<4>h713-power: the display MIPS is not known (no sun50i-h713-mips driver)", out)

    def test_a_failed_restart_is_a_warning_not_a_power_off(self):
        calls, out = Root(mips="parked", restart_rc=3).press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "mips-restart"], out)
        self.assertIn("<4>h713-power: h713-mips-restart ended with 3", out)

    def test_a_missing_restart_tool_is_a_warning(self):
        r = Root(mips="parked")
        r.restart_tool = r.p("no-such-tool")
        calls, out = r.press(*self.SHORT)
        self.assertEqual(calls, ["suspend"], out)
        self.assertIn("<4>h713-power: h713-mips-restart cannot start", out)

    def test_a_refused_standby_restarts_a_parked_mips_only_when_the_projector_stays_on(self):
        calls, out = Root(mips="parked", suspend_ok=False, conf="refused = log\n").press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "mips-restart"], out)
        calls, out = Root(mips="parked", suspend_ok=False).press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "poweroff"], out)

    def test_while_the_picture_comes_back_a_short_press_does_nothing_a_long_one_powers_off(self):
        m, r = load(), Root(mips="parked")
        m.ROOT, m.SYSTEMCTL = r.dir, [r.p("systemctl")]

        class Running:
            def poll(self):
                return None
        m.restart = Running()
        m.act("short", m.config()[0])
        self.assertFalse(os.path.exists(r.log))
        m.act("long", m.config()[0])
        with open(r.log) as f:
            self.assertEqual(f.read().split(), ["poweroff"])

    def test_status_names_the_mips_state(self):
        r = Root(mips="parked")
        env = dict(os.environ, H713_POWER_ROOT=r.dir)
        out = subprocess.run([sys.executable, TOOL, "status"], env=env, capture_output=True, text=True).stdout
        self.assertIn("display MIPS: parked", out)


if __name__ == "__main__":
    unittest.main()
