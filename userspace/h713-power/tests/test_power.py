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
    state of sun50i-h713-mips, and an h713-mips-restart stand-in that logs into the systemctl log. power.conf
    says short = standby unless conf names short itself: these are the standby's tests, and the shipped
    default is poweroff (Defaults below)."""

    def __init__(self, mem_sleep="s2idle [deep]", ready="1", conf="", mips=None, suspend_ok=True,
                 build2="0x00003318", fail_step=None, wake_irq=None):
        self.tmp = tempfile.TemporaryDirectory()        # removed with this object
        self.dir = self.tmp.name
        self.put("etc/h713/power.conf", conf if conf is None or "short" in conf else "short = standby\n" + conf)
        self.put("sys/power/mem_sleep", mem_sleep)
        self.put("sys/power/suspend_stats/success", "0")
        self.put("sys/power/suspend_stats/fail", "0")
        self.put("sys/bus/platform/drivers/sun50i-h713-arisc/100000.arisc/state",
                 "version=5\nbuild2=%s\nwake=none\nresume_ns=0\nready=%s\n" % (build2, ready))
        self.put("sys/class/input/event0/device/capabilities/key", "10000000000000 0")
        self.put("sys/class/input/event0/device/id/bustype", "0019")
        self.fifo = self.p("dev/input/event0")
        os.makedirs(os.path.dirname(self.fifo))
        os.mkfifo(self.fifo)
        self.log = self.p("systemctl.log")
        # A failed try can name the step it failed in (the kernel's failed_<step> counter) and, with
        # CONFIG_PM_DEBUG, the wake-up interrupt that aborted it (pm_wakeup_irq) - both written by "suspend".
        more = ""
        if fail_step:
            more += "echo 1 > %s\n" % self.p("sys/power/suspend_stats/" + fail_step)
        if wake_irq:
            more += "echo %s > %s\n" % (wake_irq, self.p("sys/power/pm_wakeup_irq"))
        for step in ("failed_freeze", "failed_prepare", "failed_suspend", "failed_suspend_late",
                     "failed_suspend_noirq"):
            self.put("sys/power/suspend_stats/" + step, "0")
        self.put("post-state", "inactive")
        self.put("systemctl", '#!/bin/sh\necho "$@" >> %s\n[ "$1" = is-active ] && { cat %s; exit 0; }\n'
                 '[ "$1" = suspend ] && { echo 1 > %s\n%s}\nexit 0\n'
                 % (self.log, self.p("post-state"), self.p("sys/power/suspend_stats/" + ("success" if suspend_ok else "fail")), more))
        os.chmod(self.p("systemctl"), 0o755)
        if mips:
            self.put("sys/bus/platform/drivers/sun50i-h713-mips/3061000.mips/state",
                     "%s\n0x02001600=0x00000000 0x0200160c=0x00000000\n" % mips)

    def __del__(self):
        self.tmp.cleanup()                               # now, without the ResourceWarning of a late cleanup

    def p(self, rel):
        return os.path.join(self.dir, rel)

    def calls(self):
        """every word the systemctl stand-in was called with, in order (is-active included)"""
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return f.read().split()

    def put(self, rel, text):
        os.makedirs(os.path.dirname(self.p(rel)), exist_ok=True)
        with open(self.p(rel), "w") as f:
            f.write(text)

    def press(self, *events, osd=None):
        """Run 'h713-power run --once' while (value, delay_s[, code]) events reach the fifo; -> systemctl calls.
        osd: the path of a stand-in h713-osd socket; none by default, so no countdown is seen."""
        def feed():
            with open(self.fifo, "wb") as f:
                for ev in events:
                    time.sleep(ev[1])
                    f.write(struct_event(ev[0], *ev[2:]))
                    f.flush()
                time.sleep(1.5)
        threading.Thread(target=feed, daemon=True).start()
        env = dict(os.environ, H713_POWER_ROOT=self.dir, H713_SYSTEMCTL=self.p("systemctl"),
                   H713_POWER_CTL=self.p("power.sock"), H713_POWER_OSD=osd or self.p("no-osd"))
        out = subprocess.run([sys.executable, TOOL, "run", "--once"], env=env, capture_output=True,
                             text=True, timeout=20)
        calls = self.calls()
        while "is-active" in calls:                      # the short press asks whether h713-sleep-post still runs
            i = calls.index("is-active")
            del calls[i:i + 2]
        return calls, out.stdout


def struct_event(value, code=116):
    ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    return EVENT.pack(ns // S, ns % S // 1000, 1, code, value)


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
        self.assertIn("default = poweroff", self.refusal(conf="short = poweroff\n"))   # the old name still read

    def test_a_bad_config_line_is_named_and_its_default_kept(self):
        r = Root(conf="short = sleep\nlong_s = 5\n")
        self.m.ROOT = r.dir
        conf, bad = self.m.config()
        self.assertEqual((conf["default"], conf["long_s"]), ("poweroff", "5"))
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
    """A standby parks the display MIPS; the picture and the mode come back through h713-sleep-post.service (systemd,
    package H), not through this tool: it only waits for the unit and starts it again after a standby that did not happen."""

    SHORT = ((1, 0.3), (0, 0.2))

    def test_the_standby_leaves_the_picture_to_systemd(self):
        calls, out = Root(mips="parked").press(*self.SHORT)
        self.assertEqual(calls, ["suspend"], out)                 # no h713-mips-restart from here
        self.assertNotIn("h713-mips-restart", out)

    def test_a_refused_standby_that_leaves_the_projector_on_runs_the_post_unit_again(self):
        calls, out = Root(mips="parked", suspend_ok=False, conf="refused = log\n").press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "start", "--no-block", "h713-sleep-post.service"], out)
        calls, out = Root(mips="parked", suspend_ok=False).press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "poweroff"], out)

    def test_a_standby_a_wake_up_aborted_stays_on_whatever_refused_says(self):
        # TODO 5.14 U2: a press while the box goes to sleep is no refusal - the projector stays on
        r = Root(mips="parked", suspend_ok=False, fail_step="failed_suspend_noirq", wake_irq="45")
        calls, out = r.press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "start", "--no-block", "h713-sleep-post.service"], out)
        self.assertIn("aborted by a wake-up (IRQ 45): the projector stays on", out)

    def test_a_wake_up_irq_of_an_earlier_cycle_does_not_count(self):
        # pm_wakeup_irq left from the last resume, the try failed before the freezer cleared it: a refusal
        r = Root(mips="parked", suspend_ok=False)
        r.put("sys/power/pm_wakeup_irq", "45")
        calls, out = r.press(*self.SHORT)
        self.assertEqual(calls, ["suspend", "poweroff"], out)
        self.assertNotIn("aborted by a wake-up", out)

    def test_without_pm_wakeup_irq_a_failed_step_is_a_refusal_as_before(self):
        # a kernel without CONFIG_PM_DEBUG has no pm_wakeup_irq: as before, the refusal powers off
        for step in ("failed_suspend_noirq", "failed_suspend", "failed_freeze"):
            calls, out = Root(mips="parked", suspend_ok=False, fail_step=step).press(*self.SHORT)
            self.assertEqual(calls, ["suspend", "poweroff"], (step, out))

    def test_while_the_post_unit_runs_a_short_press_does_nothing_a_long_one_powers_off(self):
        m, r = load(), Root(mips="parked")
        m.ROOT, m.SYSTEMCTL = r.dir, [r.p("systemctl")]
        r.put("post-state", "activating")                            # what `systemctl is-active` says while it runs
        m.act("short", m.config()[0])
        self.assertEqual(r.calls(), ["is-active", "h713-sleep-post.service"])    # asked, nothing else done
        m.act("long", m.config()[0])
        self.assertEqual(r.calls()[-1], "poweroff")
        r.put("post-state", "inactive")                              # done (or hung and failed): the key counts again
        m.act("short", m.config()[0])
        self.assertEqual(r.calls()[-1], "suspend")

    def test_can_standby_says_whether_one_can_happen(self):
        a, b = Root(), Root(ready="0")
        out = subprocess.run([sys.executable, TOOL, "can-standby"], env=dict(os.environ, H713_POWER_ROOT=a.dir),
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "a standby can happen"))
        out = subprocess.run([sys.executable, TOOL, "can-standby"], env=dict(os.environ, H713_POWER_ROOT=b.dir),
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("crust is not ready", out.stdout)

    def test_status_names_the_mips_state(self):
        r = Root(mips="parked")
        env = dict(os.environ, H713_POWER_ROOT=r.dir)
        out = subprocess.run([sys.executable, TOOL, "status"], env=env, capture_output=True, text=True).stdout
        self.assertIn("display MIPS: parked", out)


class Launcher(unittest.TestCase):
    """The launcher's Power press arrives as a datagram; the countdown holds the remote's devices."""

    def test_a_datagram_short_starts_the_countdown_and_the_devices_are_held(self):
        import socket
        r = Root()
        m = load()
        m.ROOT, m.SYSTEMCTL, m.CTL = r.dir, [r.p("systemctl")], r.p("power.sock")
        grabbed = []
        real = m.fcntl.ioctl
        m.fcntl.ioctl = lambda fd, req, arg=0: grabbed.append((req, arg)) if req == m.EVIOCGRAB else real(fd, req, arg)
        said = []
        m.osd = lambda line: said.append(line) or "ok"
        t = threading.Thread(target=lambda: m.run(once=True), daemon=True)
        t.start()
        c = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        for _ in range(100):
            try:
                c.sendto(b"short", r.p("power.sock"))
                break
            except OSError:
                time.sleep(0.02)
        time.sleep(0.6)
        self.assertTrue([l for l in said if l.startswith("power ")], said)           # the countdown is on
        self.assertIn((m.EVIOCGRAB, 1), grabbed)
        # a second datagram is "act now": the choice is carried out, the devices are let go
        c.sendto(b"short", r.p("power.sock"))
        t.join(5)
        c.close()
        self.assertIn((m.EVIOCGRAB, 0), grabbed)
        self.assertIn("suspend", r.calls())                          # the default of this Root is standby

    def test_a_countdown_that_nobody_sees_holds_nothing(self):
        m = load()
        held = []
        cd = m.Countdown({"default": "poweroff"}, say=lambda line: "ok unseen", hold=held.append)
        self.assertFalse(cd.start())
        self.assertEqual(held, [])
        cd = m.Countdown({"default": "poweroff"}, say=lambda line: "ok", hold=held.append)
        self.assertTrue(cd.start())
        cd.close(False)
        self.assertEqual(held, [True, False])


class Defaults(unittest.TestCase):
    """The shipped policy: a short press powers off; the standby is chosen with 'h713-power set short standby'."""

    def tool(self, r, *args):
        env = dict(os.environ, H713_POWER_ROOT=r.dir, H713_POWER_OSD=r.p("no-osd"))
        return subprocess.run([sys.executable, TOOL] + list(args), env=env, capture_output=True, text=True)

    def test_without_a_short_line_a_short_press_powers_off(self):
        m, r = load(), Root()
        r.put("etc/h713/power.conf", "long_s = 3\n")       # no short line at all
        m.ROOT = r.dir
        self.assertEqual(m.config()[0]["default"], "poweroff")
        self.assertIn("default = poweroff", m.standby_refusal(m.config()[0]))

    def test_the_shipped_power_conf_says_poweroff(self):
        with open(os.path.join(os.path.dirname(TOOL), "power.conf")) as f:
            lines = [l.split("#", 1)[0].strip() for l in f]
        self.assertIn("default = poweroff", lines)

    def test_set_replaces_the_line_keeps_the_comments_and_drops_a_later_duplicate(self):
        r = Root(conf="# the key\nshort = poweroff\nlong_s = 3\nshort = poweroff  # again\n")
        p = self.tool(r, "set", "short", "standby")
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(r.p("etc/h713/power.conf")) as f:
            self.assertEqual(f.read(), "# the key\ndefault = standby\nlong_s = 3\n")   # the old name replaced
        m = load()
        m.ROOT = r.dir
        self.assertIsNone(m.standby_refusal(m.config()[0]))

    def test_set_appends_a_missing_key_and_refuses_a_bad_value_or_key(self):
        r = Root(conf="short = poweroff\n")
        self.assertEqual(self.tool(r, "set", "refused", "log").returncode, 0)
        with open(r.p("etc/h713/power.conf")) as f:
            self.assertEqual(f.read(), "short = poweroff\nrefused = log\n")
        self.assertEqual(self.tool(r, "set", "short", "sleep").returncode, 2)
        self.assertEqual(self.tool(r, "set", "colour", "red").returncode, 2)
        self.assertEqual(self.tool(r, "set", "long_s", "x").returncode, 2)
        with open(r.p("etc/h713/power.conf")) as f:
            self.assertEqual(f.read(), "short = poweroff\nrefused = log\n")

    def test_status_names_who_powers_off(self):
        self.assertIn("a power-off: crust (rails off", self.tool(Root(build2="0x01003318"), "status").stdout)
        self.assertIn("a power-off: the power-on gate", self.tool(Root(), "status").stdout)


class FakeOsd:
    """A stand-in h713-osd: answers every line with `answer` and keeps what it was told."""

    def __init__(self, path, answer="ok"):
        import socket
        self.lines, self.answer = [], answer
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        self.srv.listen(8)
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            with c:
                self.lines.append(c.recv(256).decode().strip())
                c.sendall((self.answer + "\n").encode())


class Countdown(unittest.TestCase):
    """TODO 2.38: a short press shows 15 s; Left/Right choose, OK or a second press acts, Back cancels."""

    def countdown(self, root, conf):
        m = load()
        m.ROOT = root.dir
        said, t = [], [100.0]
        cd = m.Countdown(m.config()[0] if conf is None else conf, clock=lambda: t[0], say=said.append)
        return m, cd, said, t

    def test_it_starts_on_the_default_and_left_right_choose(self):
        r = Root(conf="default = poweroff\n")
        m, cd, said, t = self.countdown(r, None)
        self.assertEqual(cd.choice, "poweroff")
        self.assertIn("power 150 off", cd.line())
        self.assertIsNone(cd.key(m.KEY_LEFT))
        self.assertEqual(cd.choice, "standby")
        self.assertTrue(said[-1].startswith("power 150 standby"))
        cd.key(m.KEY_RIGHT)
        self.assertEqual(cd.choice, "poweroff")
        self.assertEqual(cd.key(m.KEY_OK), "act")
        self.assertEqual(cd.key(m.KEY_SELECT), "act")
        self.assertEqual(cd.key(m.KEY_BACK), "cancel")
        t[0] += 6.05
        self.assertIn("power 90 ", cd.line())          # 8.95 s left: the digits say 9

    def test_without_standby_the_ring_alone_and_left_does_nothing(self):
        r = Root(conf="default = standby\n")
        r.put("etc/systemd/sleep.conf.d/10-h713.conf", "[Sleep]\nAllowSuspend=no\n")
        m, cd, said, t = self.countdown(r, None)
        self.assertTrue(cd.only)
        self.assertEqual(cd.choice, "poweroff")
        cd.key(m.KEY_LEFT)
        self.assertEqual(cd.choice, "poweroff")
        self.assertIn(" only ", cd.line())

    def test_a_second_press_acts_on_the_choice(self):
        r = Root(conf="default = poweroff\n")
        osd = FakeOsd(r.p("osd"))
        calls, out = r.press((1, 0.3), (0, 0.15), (1, 0.6, 105), (0, 0.05, 105), (1, 0.4), (0, 0.15), osd=r.p("osd"))
        self.assertEqual(calls, ["suspend"], out)      # Left chose the standby, the second press took it
        self.assertIn("countdown of 15 s, poweroff chosen", out)
        self.assertTrue(any(l.startswith("power ") and " standby " in l for l in osd.lines), osd.lines)
        self.assertEqual(osd.lines[-1], "hide")

    def test_back_cancels_and_nothing_happens(self):
        r = Root(conf="default = poweroff\n")
        osd = FakeOsd(r.p("osd"))
        calls, out = r.press((1, 0.3), (0, 0.15), (1, 0.5, 158), (0, 0.05, 158), (1, 0.5), (0, 0.15),
                             (1, 0.5), (0, 0.15), osd=r.p("osd"))
        self.assertIn("countdown cancelled", out)
        self.assertEqual(calls, ["poweroff"], out)     # the next press counted down again, the third took it

    def test_without_a_picture_the_default_at_once(self):
        r = Root(conf="default = poweroff\n")
        FakeOsd(r.p("osd"), answer="ok unseen")
        calls, out = r.press((1, 0.3), (0, 0.15), osd=r.p("osd"))
        self.assertEqual(calls, ["poweroff"], out)
        self.assertNotIn("countdown of", out)


if __name__ == "__main__":
    unittest.main()
