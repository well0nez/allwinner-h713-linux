"""Tests for h713-mips-restart against a made-up sysfs, /proc and systemctl (no device, no kernel driver).

The fake kernel: the state file of sun50i-h713-mips is a FIFO answered at read time, so a read that follows a
write to restart sees its result, as the real attribute does. bind, unbind and restart are plain files a thread
picks up every 2 ms, in the kernel's order unbind, restart, bind; before it answers a state read and before the
systemctl stand-in goes on, it has handled every write made so far, so the events file has the order the real,
synchronous kernel would give. unbind and bind can be FIFOs instead (hang=...): the write then waits until the
test lets the kernel take it, and the kernel has handled it before the next state read, as the real write returns
only after the unbind or the probe. Binding creates the receiver's video node after node_delay seconds. systemctl
and logger are shell stand-ins that log their calls into the same events file. The fake kernel notes what the real one would punish as VIOLATION:
an unbind while h713-tv or h713-warp runs or a process holds the node, a restart while the receiver is bound, a
bind while the MIPS is not running.
"""
import fcntl
import os
import signal
import subprocess
import tempfile
import threading
import time
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "h713-mips-restart")
MIPS = "sys/bus/platform/drivers/sun50i-h713-mips/3061000.mips"
RXD = "sys/bus/platform/drivers/sun50i-h713-hdmirx"
MSP = "sys/bus/platform/drivers/sun50i-h713-msp/6144000.audio-dsp"
REGS = {"parked": "0x02001600=0x00000000 0x0200160c=0x00000000",
        "running": "0x02001600=0x80000002 0x0200160c=0x00070001",
        "failed": "0x02001600=0x80000002 0x0200160c=0x00030001"}
SYSTEMCTL = r"""#!/bin/sh
R=$H713_ROOT
: > "$R/sync.$$"                                        # the kernel handles the writes before this call
while [ -e "$R/sync.$$" ]; do sleep 0.005; done
echo "systemctl $*" >> "$R/events"
case $1 in
is-active) [ -e "$R/active/$3" ]; exit ;;
stop) shift; [ ! -e "$R/stop-delay" ] || sleep "$(cat "$R/stop-delay")"
	for u in "$@"; do case $u in *'*'*) rm -f "$R"/active/h713-tv@* ;; *) rm -f "$R/active/$u" ;; esac; done ;;
start) [ ! -e "$R/fail-start-$2" ] || exit 1; touch "$R/active/$2" ;;
esac
exit 0
"""
LOGGER = '#!/bin/sh\necho "logger $*" >> "$H713_ROOT/events"\n'
KEYTOOL = r"""#!/bin/sh
# stand-in for h713-hdcp-key --bind DEV: binds DEV unless key-rc says 1, exits with key-rc (0 default). The real
# bind write returns after the probe, so the stand-in waits until the fake kernel has taken it, as systemctl does.
R=$H713_ROOT
echo "hdcp-key $*" >> "$R/events"
rc=0; [ ! -e "$R/key-rc" ] || rc=$(cat "$R/key-rc")
[ "$rc" = 1 ] || echo "$2" > "$R/sys/bus/platform/drivers/sun50i-h713-hdmirx/bind"
: > "$R/sync.$$"
while [ -e "$R/sync.$$" ]; do sleep 0.005; done
exit "$rc"
"""


class Box:
    """A temporary root with the fake kernel running; run() starts h713-mips-restart against it."""

    def __init__(self, state="parked", outcome="running", node_delay=0.1, node="video2", warp=True,
                 bound=True, driver=True, keytool=None, hang=(), msp=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.state, self.outcome, self.node_delay, self.node = state, outcome, node_delay, node
        self.lock, self.stop, self.timers = threading.Lock(), False, []
        for d in ("run", "active", "bin", RXD, "proc", "sys/class/video4linux/video0"):
            os.makedirs(self.p(d), exist_ok=True)
        self.put("sys/class/video4linux/video0/name", "HD camera\n")      # not the receiver
        self.put("boot/mips/display.bin", "")
        self.put("events", "")
        self.put("bin/systemctl", SYSTEMCTL)
        self.put("bin/logger", LOGGER)
        for b in ("systemctl", "logger"):
            os.chmod(self.p("bin/" + b), 0o755)
        if keytool:                     # "new" knows --bind, "old" is the tool before it did
            self.put("usr/local/sbin/h713-hdcp-key", KEYTOOL if keytool == "new" else
                     "#!/bin/sh\necho \"hdcp-key $*\" >> \"$H713_ROOT/events\"\n")
            os.chmod(self.p("usr/local/sbin/h713-hdcp-key"), 0o755)
        for a in ("bind", "unbind"):
            if a in hang:
                os.mkfifo(self.p(RXD + "/" + a))     # the write waits for release_rx()
            else:
                self.put(RXD + "/" + a, "")
        self.hang = hang
        if bound:
            os.makedirs(self.p(RXD + "/hdmi-rx"))
            self.make_node()
            self.put("active/h713-tv@%s.service" % node, "")
        if warp:
            self.put("active/h713-warp.service", "")
        self.threads = []
        if driver:
            os.makedirs(self.p(MIPS))
            os.mkfifo(self.p(MIPS + "/state"))
            if outcome == "error":
                os.symlink("/dev/full", self.p(MIPS + "/restart"))       # the write fails like a store() error
            elif outcome == "hang":
                os.mkfifo(self.p(MIPS + "/restart"))                      # the write waits for release()
            else:
                self.put(MIPS + "/restart", "")
            self.threads.append(threading.Thread(target=self.serve_state, daemon=True))
        # msp: None no audio driver; "running"; "error" rebuilt by the first reset; "flaky" by the second; "dead" never
        self.msp, self.msp_resets = msp, 0
        if msp:
            os.makedirs(self.p(MSP))
            self.put(MSP + "/reset", "")
            os.mkfifo(self.p(MSP + "/state"))
            self.msp_state = "running" if msp == "running" else "error"
            self.threads.append(threading.Thread(target=self.serve_msp, daemon=True))
        self.threads.append(threading.Thread(target=self.kernel, daemon=True))
        for t in self.threads:
            t.start()

    def close(self):
        self.stop = True
        for t in self.timers:
            t.cancel()
        for a in self.hang:                     # wakes serve_rx() waiting for a writer
            try:
                os.close(os.open(self.p(RXD + "/" + a), os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
        if os.path.exists(self.p(MSP + "/state")):
            os.close(os.open(self.p(MSP + "/state"), os.O_RDONLY | os.O_NONBLOCK))    # wakes serve_msp
        if os.path.exists(self.p(MIPS + "/state")):
            fd = os.open(self.p(MIPS + "/state"), os.O_RDONLY | os.O_NONBLOCK)   # wakes serve_state
            for t in self.threads:
                t.join(2)
            os.close(fd)
        self.tmp.cleanup()

    def p(self, rel):
        return os.path.join(self.dir, rel)

    def put(self, rel, text):
        os.makedirs(os.path.dirname(self.p(rel)), exist_ok=True)
        with open(self.p(rel), "w") as f:
            f.write(text)

    def note(self, line):
        with open(self.p("events"), "a") as f:
            f.write(line + "\n")

    def make_node(self):
        self.put("sys/class/video4linux/%s/name" % self.node, "sun50i-h713-hdmirx\n")

    def hold(self, pid=4242):
        """A process outside the services that keeps the receiver's node open."""
        os.makedirs(self.p("proc/%d/fd" % pid))
        os.symlink("/dev/" + self.node, self.p("proc/%d/fd/7" % pid))

    def take(self, rel):
        """The value written to a plain attribute file, emptied as the kernel consumes it."""
        if os.path.islink(self.p(rel)) or not os.path.isfile(self.p(rel)):
            return ""
        with open(self.p(rel), "r+") as f:
            v = f.read().strip()
            if v:                       # only then: a write that lands after an empty read must survive
                f.truncate(0)
        return v

    def pending(self):
        """Handle the writes not yet seen, in the kernel's order: unbind, restart, bind."""
        if self.take(RXD + "/unbind") == "hdmi-rx":
            self.unbind()
        fw = self.take(MIPS + "/restart")
        if fw:
            self.restarted(fw)
        if self.take(RXD + "/bind") == "hdmi-rx":
            self.bind()
        if self.msp and self.take(MSP + "/reset") == "1":
            self.msp_resets += 1
            if self.state != "running":
                self.note("VIOLATION msp reset while the MIPS is %s" % self.state)
            ok = {"error": True, "flaky": self.msp_resets >= 2, "dead": False, "running": True}[self.msp]
            self.msp_state = "running" if ok else "error"
            self.note("kernel msp reset -> %s" % self.msp_state)

    def unbind(self):
        busy = [u for u in os.listdir(self.p("active")) if u.startswith(("h713-tv@", "h713-warp"))]
        held = [d for d in os.listdir(self.p("proc")) if os.listdir(self.p("proc/" + d + "/fd"))]
        if busy or held:
            self.note("VIOLATION unbind while %s" % " ".join(busy + held))
        if os.path.isdir(self.p(RXD + "/hdmi-rx")):
            os.rmdir(self.p(RXD + "/hdmi-rx"))
        for f in ("name", ""):
            if os.path.exists(self.p("sys/class/video4linux/%s/%s" % (self.node, f))):
                (os.remove if f else os.rmdir)(self.p("sys/class/video4linux/%s/%s" % (self.node, f)))
        self.note("kernel unbind hdmi-rx")

    def bind(self):
        if self.state != "running":
            self.note("VIOLATION bind while the MIPS is %s" % self.state)
        os.makedirs(self.p(RXD + "/hdmi-rx"), exist_ok=True)
        self.note("kernel bind hdmi-rx")
        if self.node_delay is not None:
            t = threading.Timer(self.node_delay, self.node_appears)
            self.timers.append(t)
            t.start()

    def bound(self):
        return os.path.isdir(self.p(RXD + "/hdmi-rx"))

    def release_rx(self, what):
        """From now on the kernel takes the writes to the FIFO unbind or bind: the one that waits, and every
        later one at once."""
        t = threading.Thread(target=self.serve_rx, args=(what,), daemon=True)
        self.threads.append(t)
        t.start()

    def serve_rx(self, what):
        while not self.stop:
            fd = os.open(self.p(RXD + "/" + what), os.O_RDONLY)      # waits for a writer
            with self.lock:                     # held before the writer is done: the next state read waits
                data = b""
                while True:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    data += chunk
                os.close(fd)
                if not self.stop and data.decode().strip() == "hdmi-rx":
                    (self.unbind if what == "unbind" else self.bind)()

    def restarted(self, fw):
        if os.path.isdir(self.p(RXD + "/hdmi-rx")):
            self.note("VIOLATION restart while hdmi-rx is bound")
        self.note("kernel restart %s from %s" % (fw, self.state))
        self.state = "failed" if self.outcome == "failed" else "running"

    def node_appears(self):
        with self.lock:
            self.make_node()
            self.note("kernel node %s" % self.node)

    def kernel(self):
        while not self.stop:
            with self.lock:
                waiting = [f for f in os.listdir(self.dir) if f.startswith("sync.")]
                self.pending()
                for f in waiting:                      # their writes came before them: handled now
                    os.remove(self.p(f))
            time.sleep(0.002)

    def sync(self):
        with self.lock:
            self.pending()

    def serve_state(self):
        while not self.stop:
            fd = os.open(self.p(MIPS + "/state"), os.O_WRONLY)          # waits for a reader
            if not self.stop:
                time.sleep(0.02)                                         # a release() racing in finishes
                with self.lock:
                    self.pending()
                    text = "%s\n%s\n" % (self.state, REGS[self.state])
                try:
                    os.write(fd, text.encode())
                except BrokenPipeError:
                    pass
            os.close(fd)
            time.sleep(0.03)            # the reader reaches its EOF before a writer is back on the FIFO

    def serve_msp(self):
        """msp's state file: a read is answered after the writes before it (a reset is synchronous in msp)."""
        while not self.stop:
            fd = os.open(self.p(MSP + "/state"), os.O_WRONLY)           # waits for a reader
            if not self.stop:
                time.sleep(0.02)
                with self.lock:
                    self.pending()
                    text = "%s\n" % self.msp_state
                try:
                    os.write(fd, text.encode())
                except BrokenPipeError:
                    pass
            os.close(fd)
            time.sleep(0.03)

    def release(self, fw_state="running"):
        """End a hanging restart write: the kernel reads it and the MIPS ends up in fw_state. A writer that
        died meanwhile wrote nothing, and nothing happens."""
        fd = os.open(self.p(MIPS + "/restart"), os.O_RDONLY | os.O_NONBLOCK)    # wakes a waiting writer
        data, end = b"", time.monotonic() + 5
        try:
            while time.monotonic() < end:
                try:
                    chunk = os.read(fd, 4096)
                except BlockingIOError:                  # the writer is there and has not written yet
                    time.sleep(0.01)
                    continue
                if not chunk:                            # no writer (left, or never came)
                    break
                data += chunk
        finally:
            os.close(fd)
        fw = data.decode().strip()
        if fw:
            with self.lock:
                self.outcome = fw_state
                self.restarted(fw)

    def start(self, *args, journal=False, wait="5", group=False):
        env = dict(os.environ, H713_ROOT=self.dir, H713_WAIT=wait,
                   PATH=self.p("bin") + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"))
        env.pop("JOURNAL_STREAM", None)
        if journal:
            env["JOURNAL_STREAM"] = "8:4711"
        return subprocess.Popen([TOOL] + list(args), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=group)

    def run(self, *args, **kw):
        proc = self.start(*args, **kw)
        out, err = proc.communicate(timeout=30)
        return proc.returncode, out, err

    def events(self):
        self.sync()
        with open(self.p("events")) as f:
            return f.read().splitlines()

    def wait_for(self, line, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if line in self.events():
                return
            time.sleep(0.01)
        raise AssertionError("no %r in %r" % (line, self.events()))


class Base(unittest.TestCase):
    def box(self, **kw):
        b = Box(**kw)
        self.addCleanup(b.close)
        return b

    def ordered(self, events, *lines):
        """lines appear in events in this order (other lines between them are fine)."""
        at = [events.index(x) for x in lines]
        self.assertEqual(at, sorted(at), events)

    def clean(self, events):
        self.assertFalse([e for e in events if e.startswith("VIOLATION")], events)

    def untouched(self, events):
        """Refused before anything: no service stopped, no receiver, no MIPS write."""
        self.assertFalse([e for e in events if not e.startswith(("logger", "systemctl is-active"))], events)


class Success(Base):
    def test_from_the_standby_park_the_picture_path_comes_back_in_the_measured_order(self):
        b = self.box(state="parked")
        rc, out, err = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.clean(ev)
        self.ordered(ev, "systemctl is-active --quiet h713-warp.service",
                     "systemctl stop h713-warp.service h713-tv@*.service", "kernel unbind hdmi-rx",
                     "kernel restart /boot/mips/display.bin from parked", "kernel bind hdmi-rx", "kernel node video2",
                     "systemctl reset-failed h713-warp.service h713-tv@*.service",
                     "systemctl start h713-tv@video2.service", "systemctl start h713-warp.service")
        self.assertTrue(any("picture path back after" in e and "MIPS running 0x02001600=0x80000002" in e
                            and "/dev/video2" in e and "user.notice" in e for e in ev), ev)
        self.assertIn("picture path back", err)                          # a person at the console sees it too
        self.assertEqual(sorted(os.listdir(b.p("active"))), ["h713-tv@video2.service", "h713-warp.service"])

    def test_from_a_running_mips_the_same_sequence_and_another_node_number(self):
        b = self.box(state="running", node="video3")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.clean(ev)
        self.ordered(ev, "kernel unbind hdmi-rx", "kernel restart /boot/mips/display.bin from running",
                     "kernel bind hdmi-rx", "kernel node video3", "systemctl start h713-tv@video3.service")

    def test_another_firmware_file_is_what_the_driver_gets(self):
        b = self.box()
        b.put("srv/fw/display-test.bin", "")
        rc, _, _ = b.run("/srv/fw/display-test.bin")
        self.assertEqual(rc, 0)
        self.assertIn("kernel restart /srv/fw/display-test.bin from parked", b.events())

    def test_a_warp_that_did_not_run_is_not_started(self):
        b = self.box(warp=False)
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.assertIn("systemctl start h713-tv@video2.service", ev)
        self.assertNotIn("systemctl start h713-warp.service", ev)

    def test_under_systemd_only_the_journal_gets_the_lines_with_their_level(self):
        b = self.box()
        rc, out, err = b.run(journal=True)
        ev = b.events()
        self.assertEqual(rc, 0)
        self.assertIn("logger -t h713-mips-restart -p user.notice -- MIPS parked 0x02001600=0x00000000 "
                      "0x0200160c=0x00000000; firmware /boot/mips/display.bin", ev)   # one state read, read once
        self.assertEqual((out, err), ("", ""))          # not a second time through h713-power's stdout

    def test_a_service_that_does_not_start_turns_success_into_3(self):
        b = self.box()
        b.put("fail-start-h713-warp.service", "")
        rc, _, _ = b.run()
        self.assertEqual(rc, 3)
        self.assertTrue(any("h713-warp did not start" in e and "user.warning" in e for e in b.events()))


class AudioDsp(Base):
    """09.10.2026: the standby powers the audio DSP off; after the picture the restart rebuilds it."""

    def test_a_dsp_in_error_is_rebuilt_after_the_picture(self):
        b = self.box(state="parked", msp="error")
        rc, out, err = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.clean(ev)
        self.ordered(ev, "kernel bind hdmi-rx", "systemctl start h713-warp.service", "kernel msp reset -> running")
        self.assertEqual(b.msp_resets, 1)
        self.assertTrue(any("audio DSP rebuilt (attempt 1)" in e for e in ev), ev)
        at = [i for i, e in enumerate(ev) if "picture path back after" in e or "kernel msp reset" in e]
        self.assertIn("picture path back after", ev[at[0]], ev)          # the picture first, then the sound

    def test_a_second_attempt_and_three_that_fail_keep_the_picture(self):
        b = self.box(state="parked", msp="flaky")
        rc, out, err = b.run()
        self.assertEqual((rc, b.msp_resets), (0, 2), b.events())
        self.assertTrue(any("audio DSP rebuilt (attempt 2)" in e for e in b.events()))
        b = self.box(state="parked", msp="dead")
        rc, out, err = b.run()
        ev = b.events()
        self.assertEqual((rc, b.msp_resets), (0, 3), ev)
        self.assertTrue(any("did not come back in 3 attempts" in e and "user.warning" in e for e in ev), ev)

    def test_a_running_dsp_or_no_audio_driver_is_left_alone(self):
        b = self.box(state="parked", msp="running")
        rc, out, err = b.run()
        self.assertEqual((rc, b.msp_resets), (0, 0), b.events())
        self.assertFalse([e for e in b.events() if "audio DSP" in e])
        b = self.box(state="parked")
        rc, out, err = b.run()
        self.assertEqual(rc, 0, b.events())
        self.assertFalse([e for e in b.events() if "audio DSP" in e])

    def test_no_rebuild_when_the_picture_did_not_come_back(self):
        b = self.box(state="parked", outcome="error", msp="error")
        rc, out, err = b.run()
        self.assertEqual((rc, b.msp_resets), (1, 0), b.events())


class DriverError(Base):
    def test_a_failed_write_from_the_park_leaves_the_receiver_unbound_and_restarts_warp(self):
        b = self.box(state="parked", outcome="error")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 1, ev)
        self.clean(ev)
        self.assertTrue(any("the driver refused the restart (" in e and "MIPS parked" in e and "user.err" in e
                            for e in ev), ev)
        self.assertTrue(any("hdmi-rx stays unbound: the MIPS is parked" in e for e in ev), ev)
        self.assertNotIn("kernel bind hdmi-rx", ev)
        self.assertIn("systemctl start h713-warp.service", ev)
        self.assertFalse([e for e in ev if e.startswith("systemctl start h713-tv@")], ev)   # no node, no h713-tv

    def test_a_write_that_works_but_leaves_the_mips_failed(self):
        b = self.box(outcome="failed")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 1, ev)
        self.clean(ev)
        self.assertTrue(any("the MIPS did not come up: failed 0x02001600" in e for e in ev), ev)
        self.assertNotIn("kernel bind hdmi-rx", ev)
        self.ordered(ev, "kernel restart /boot/mips/display.bin from parked", "systemctl start h713-warp.service")

    def test_a_refused_restart_of_a_running_mips_gives_the_receiver_back(self):
        b = self.box(state="running", outcome="error")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 1, ev)
        self.clean(ev)
        self.ordered(ev, "kernel unbind hdmi-rx", "kernel bind hdmi-rx", "systemctl start h713-warp.service")


class NoNode(Base):
    def test_no_video_node_within_the_wait_is_3_and_the_services_come_back(self):
        b = self.box(node_delay=None)
        t = time.monotonic()
        rc, _, _ = b.run(wait="1")
        ev = b.events()
        self.assertEqual(rc, 3, ev)
        self.assertTrue(1 <= time.monotonic() - t < 5)
        self.clean(ev)
        self.assertTrue(any("shows no video node within 1 s" in e and "user.err" in e for e in ev), ev)
        self.assertEqual(ev.count("kernel bind hdmi-rx"), 1, ev)             # bound once, not again on the exit
        self.assertIn("systemctl start h713-warp.service", ev)


class Abort(Base):
    def test_a_signal_while_waiting_for_the_node(self):
        b = self.box(node_delay=None)
        proc = b.start(wait="30")
        b.wait_for("kernel bind hdmi-rx")
        time.sleep(0.3)
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=5)
        ev = b.events()
        self.assertEqual(proc.returncode, 4, ev)
        self.clean(ev)
        self.assertTrue(any("ended by a signal" in e for e in ev), ev)
        self.assertEqual(ev.count("kernel bind hdmi-rx"), 1, ev)
        self.assertIn("systemctl start h713-warp.service", ev)

    def test_a_signal_during_the_restart_write_still_brings_receiver_and_services_back(self):
        b = self.box(outcome="hang", node_delay=0)
        proc = b.start()
        b.wait_for("kernel unbind hdmi-rx")
        time.sleep(0.3)                                                 # the write now waits in the kernel
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.2)
        b.release("running")                                           # the store() returns, then the trap
        proc.communicate(timeout=10)
        ev = b.events()
        self.assertEqual(proc.returncode, 4, ev)
        self.clean(ev)
        self.ordered(ev, "kernel restart /boot/mips/display.bin from parked", "kernel bind hdmi-rx",
                     "systemctl start h713-warp.service")

    def test_a_signal_to_the_whole_group_does_not_cut_the_restart_write(self):
        """Ctrl-C or a stop of h713-power reaches the writing child too: it finishes the write all the same."""
        b = self.box(outcome="hang", node_delay=0)
        proc = b.start(group=True)
        b.wait_for("kernel unbind hdmi-rx")
        time.sleep(0.3)
        os.killpg(proc.pid, signal.SIGTERM)
        time.sleep(0.2)
        b.release("running")
        proc.communicate(timeout=10)
        ev = b.events()
        self.assertEqual(proc.returncode, 4, ev)
        self.clean(ev)
        self.ordered(ev, "kernel restart /boot/mips/display.bin from parked", "kernel bind hdmi-rx",
                     "systemctl start h713-warp.service")

    def test_a_signal_during_the_unbind_write_binds_the_receiver_again(self):
        """Review A, F2: the trap runs after the unbind returned; the exit must see from sysfs that the receiver
        is unbound, the MIPS still runs, and bind it again."""
        b = self.box(state="running", hang=("unbind",), node_delay=0)
        proc = b.start()
        b.wait_for("systemctl stop h713-warp.service h713-tv@*.service")
        time.sleep(0.3)                                                 # the unbind write now waits
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.2)
        b.release_rx("unbind")                                         # it returns, then the trap
        proc.communicate(timeout=10)
        ev = b.events()
        self.assertEqual(proc.returncode, 4, ev)
        self.clean(ev)
        self.assertFalse([e for e in ev if e.startswith("kernel restart")], ev)     # MIPS untouched
        self.ordered(ev, "kernel unbind hdmi-rx", "kernel bind hdmi-rx", "systemctl start h713-warp.service")
        self.assertEqual(ev.count("kernel bind hdmi-rx"), 1, ev)
        self.assertTrue(b.bound(), ev)

    def test_a_signal_during_the_bind_write_binds_once(self):
        """Review A, F3: the trap runs after the bind returned; the exit must not bind a second time."""
        b = self.box(state="parked", hang=("bind",), node_delay=0)
        proc = b.start()
        b.wait_for("kernel restart /boot/mips/display.bin from parked")
        time.sleep(0.3)                                                 # the bind write now waits
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.2)
        b.release_rx("bind")
        proc.communicate(timeout=10)
        ev = b.events()
        self.assertEqual(proc.returncode, 4, ev)
        self.clean(ev)
        self.assertEqual(ev.count("kernel bind hdmi-rx"), 1, ev)
        self.assertFalse([e for e in ev if "bind of hdmi-rx failed" in e], ev)
        self.assertIn("systemctl start h713-warp.service", ev)
        self.assertTrue(b.bound(), ev)

    def test_a_signal_while_the_services_stop_leaves_the_mips_untouched(self):
        b = self.box()
        b.put("stop-delay", "1")
        proc = b.start()
        b.wait_for("systemctl stop h713-warp.service h713-tv@*.service")
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=10)
        ev = b.events()
        self.assertEqual(proc.returncode, 4, ev)
        self.clean(ev)
        self.assertFalse([e for e in ev if e.startswith("kernel")], ev)
        self.assertIn("systemctl start h713-tv@video2.service", ev)
        self.assertIn("systemctl start h713-warp.service", ev)


class Refusals(Base):
    def test_no_driver(self):
        b = self.box(driver=False)
        rc, _, err = b.run()
        self.assertEqual(rc, 2)
        self.untouched(b.events())
        self.assertIn("no sun50i-h713-mips driver bound", err)

    def test_no_firmware_file_and_a_relative_path(self):
        b = self.box()
        os.remove(b.p("boot/mips/display.bin"))
        self.assertEqual(b.run()[0], 2)
        self.assertEqual(b.run("mips/display.bin")[0], 2)
        self.untouched(b.events())

    def test_a_second_run_at_the_same_time(self):
        b = self.box()
        with open(b.p("run/h713-mips-restart.lock"), "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            rc, _, err = b.run()
        self.assertEqual(rc, 2)
        self.assertIn("another h713-mips-restart runs", err)
        self.untouched(b.events())

    def test_a_held_node_is_not_unbound_and_the_services_come_back(self):
        b = self.box()
        b.hold(4242)
        rc, _, err = b.run()
        ev = b.events()
        self.assertEqual(rc, 2, ev)
        self.clean(ev)
        self.assertIn("PID 4242 holds /dev/video2 open", err)
        self.assertFalse([e for e in ev if e.startswith("kernel")], ev)
        self.assertIn("systemctl start h713-tv@video2.service", ev)
        self.assertIn("systemctl start h713-warp.service", ev)


class HdcpKey(Base):
    """The bind goes through h713-hdcp-key --bind, so the probe gets the HDCP 2.2 key again."""

    def test_the_key_tool_binds_the_receiver(self):
        b = self.box(keytool="new")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.clean(ev)
        self.ordered(ev, "kernel restart /boot/mips/display.bin from parked", "hdcp-key --bind hdmi-rx",
                     "kernel bind hdmi-rx", "kernel node video2", "systemctl start h713-warp.service")

    def test_bound_without_the_key_is_a_warning_and_still_the_picture(self):
        b = self.box(keytool="new")
        b.put("key-rc", "3")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.assertTrue(any("hdmi-rx bound without the HDCP 2.2 key" in e and "user.warning" in e for e in ev))

    def test_a_key_tool_that_fails_before_the_bind_gets_a_plain_bind_and_the_picture(self):
        # TODO 5.14 U5: the picture without the HDCP 2.2 key rather than none until the next boot
        b = self.box(keytool="new")
        b.put("key-rc", "1")                             # the stand-in fails without binding
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.clean(ev)
        self.ordered(ev, "hdcp-key --bind hdmi-rx", "kernel bind hdmi-rx", "kernel node video2",
                     "systemctl start h713-warp.service")
        self.assertTrue(any("h713-hdcp-key --bind: exit 1: hdmi-rx bound without the HDCP 2.2 key" in e
                            and "user.warning" in e for e in ev), ev)

    def test_a_key_tool_that_fails_after_its_bind_is_not_bound_twice(self):
        b = self.box(keytool="new")
        b.put("key-rc", "2")                             # the stand-in binds, then fails
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.assertEqual(ev.count("kernel bind hdmi-rx"), 1, ev)
        self.assertTrue(any("exit 2: hdmi-rx bound without the HDCP 2.2 key" in e for e in ev), ev)

    def test_when_the_plain_bind_fails_too_it_is_3(self):
        b = self.box(keytool="new")
        b.put("key-rc", "1")
        os.remove(b.p(RXD + "/bind"))
        os.symlink("/dev/full", b.p(RXD + "/bind"))      # the write fails like a probe that returns an error
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 3, ev)
        self.assertTrue(any("binding hdmi-rx failed" in e for e in ev), ev)
        self.assertNotIn("kernel bind hdmi-rx", ev)
        self.assertIn("systemctl start h713-warp.service", ev)

    def test_a_key_tool_without_bind_is_not_called(self):
        b = self.box(keytool="old")
        rc, _, _ = b.run()
        ev = b.events()
        self.assertEqual(rc, 0, ev)
        self.assertFalse([e for e in ev if e.startswith("hdcp-key")], ev)
        self.assertIn("kernel bind hdmi-rx", ev)


class Size(unittest.TestCase):
    def test_posix_sh_at_most_100_lines_no_long_dashes(self):
        self.assertEqual(subprocess.run(["sh", "-n", TOOL]).returncode, 0)
        with open(TOOL, encoding="utf-8") as f:
            text = f.read()
        self.assertLessEqual(len(text.splitlines()), 100)
        for name in (TOOL, __file__):
            with open(name, encoding="utf-8") as f:
                self.assertFalse(set(f.read()) & {chr(0x2013), chr(0x2014)}, name)


if __name__ == "__main__":
    unittest.main()
