#!/usr/bin/env python3
"""Reading the accelerometer through its IIO buffer, and the fall back to sysfs.

    python3 -m unittest discover -s tests -v          # from h713-keystone/

No device is touched.  The "kernel" is a directory that looks like /sys/bus/iio/devices with what the buffer adds
(buffer/, scan_elements/, trigger/, the timer trigger's own node), plus a FIFO that stands for /dev/iio:device2: the
test writes the scans into it before the burst, the tool reads them.  What the tool writes into the sysfs files (the
trigger, the channels, buffer/enable) is read back from the files, and the order in which it does things is recorded.

THE SCAN FORMAT is the one the SC7A20 reports on the HY310: `le:s12/16>>4`, three channels of 16 bits, x then y then z,
six bytes a scan - the value is the 16 bit word shifted right by four, 12 bits, signed.
"""

import errno
import io
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_h713_keystone as t   # noqa: E402

ks = t.ks
REAL_MAKEDIRS = os.makedirs


def word(value):
    """The 16 bit word of le:s12/16>>4 for a 12 bit signed value."""
    return struct.pack("<H", (value << 4) & 0xffff)


class FakeKernel(t.FakeIio):
    """FakeIio plus the buffer, the trigger and the node in /dev."""

    def __init__(self, type_="le:s12/16>>4", index=(0, 1, 2), **kw):
        t.FakeIio.__init__(self, rate="100", **kw)
        self.write("iio:device2/buffer/enable", "0")
        self.write("iio:device2/buffer/length", "2")
        self.write("iio:device2/trigger/current_trigger", "")
        for axis, i in zip("xyz", index):
            self.write("iio:device2/scan_elements/in_accel_%s_en" % axis, "0")
            self.write("iio:device2/scan_elements/in_accel_%s_index" % axis, str(i))
            self.write("iio:device2/scan_elements/in_accel_%s_type" % axis, type_)
        self.dev = os.path.join(self.root, "dev")
        os.makedirs(self.dev)
        self.node = os.path.join(self.dev, "iio:device2")
        os.mkfifo(self.node)
        self.feeder = os.open(self.node, os.O_RDWR)      # the writer end, kept open like the kernel's buffer
        self.configfs = os.path.join(self.root, "config")
        os.makedirs(os.path.join(self.configfs, "iio", "triggers", "hrtimer"))
        self.add_trigger()

    def add_trigger(self):
        """What the kernel does when the directory in configfs is made: the trigger's node appears."""
        REAL_MAKEDIRS(os.path.join(self.root, "trigger0"), exist_ok=True)
        for name, text in (("name", ks.TRIGGER), ("sampling_frequency", "0")):
            with open(os.path.join(self.root, "trigger0", name), "w") as fh:
                fh.write(text + "\n")

    def feed(self, triples, pack=word):
        for triple in triples:
            os.write(self.feeder, b"".join(pack(v) for v in triple))

    def sensor(self, rate=100.0, quiet=True):
        sensor = ks.Sensor(self.device, rate, quiet)
        sensor.dev_dir, sensor.configfs = self.dev, self.configfs
        return sensor

    def get(self, relative):
        with open(os.path.join(self.root, relative)) as fh:
            return fh.read().strip()

    def close(self):
        os.close(self.feeder)
        t.FakeIio.close(self)


JUNK = [(1999, -2000, 5)] * ks.SETTLE_SAMPLES        # the first scans after the switch-on: not a pose yet


class Burst(unittest.TestCase):

    def setUp(self):
        self.k = FakeKernel()
        self.addCleanup(self.k.close)

    def test_a_burst_is_the_average_of_the_triples_after_the_settling_ones(self):
        self.k.feed(JUNK + [(10, 20, 1000), (14, 24, 1004), (12, 22, 1002)])
        self.assertEqual(self.k.sensor().sample(3), (12.0, 22.0, 1002.0))

    def test_the_sign_and_the_shift_are_the_sysfs_values(self):
        """The same pose the poses table has, left side up: x is negative."""
        self.k.feed(JUNK + [(-292, 161, 1020)] * 2)
        self.assertEqual(self.k.sensor().sample(2), (-292.0, 161.0, 1020.0))

    def test_the_kernel_is_asked_for_the_trigger_the_channels_and_the_rate(self):
        self.k.feed(JUNK + [(1, 2, 3)])
        self.k.sensor(rate=50.0).sample(1)
        self.assertEqual(self.k.get("iio:device2/trigger/current_trigger"), ks.TRIGGER)
        self.assertEqual([self.k.get("iio:device2/scan_elements/in_accel_%s_en" % a) for a in "xyz"], ["1"] * 3)
        self.assertEqual(self.k.get("iio:device2/buffer/length"), str(ks.BUFFER_TRIPLES))
        self.assertEqual(self.k.get("trigger0/sampling_frequency"), "50")

    def test_the_sensor_is_on_only_while_it_is_read(self):
        """enable is cleared first (a killed run may have left it on), set before the read, and cleared after."""
        log = []
        put, read = ks.Sensor._put, os.read

        def spy_put(sensor, relative, text, base=None):
            if relative == "buffer/enable":
                log.append("enable " + text)
            return put(sensor, relative, text, base)

        def spy_read(fd, n):
            log.append("read")
            return read(fd, n)
        self.k.write("iio:device2/buffer/enable", "1")                  # left on by a killed run
        self.k.feed(JUNK + [(1, 2, 3)] * 2)
        with mock.patch.object(ks.Sensor, "_put", spy_put), mock.patch.object(ks.os, "read", spy_read):
            self.k.sensor().sample(2)
        self.assertEqual(log[:2], ["enable 0", "enable 1"])
        self.assertEqual(log[-1], "enable 0")
        self.assertIn("read", log[2:-1])
        self.assertEqual(self.k.get("iio:device2/buffer/enable"), "0")

    def test_the_sensor_is_switched_off_and_the_node_closed_when_the_burst_fails(self):
        self.k.feed(JUNK)                                      # too few: the burst times out
        opened, real_open, real_close = [], os.open, os.close

        def spy_open(path, *a):
            fd = real_open(path, *a)
            opened.append(fd)
            return fd

        def spy_close(fd):
            if fd in opened:
                opened.remove(fd)
            real_close(fd)
        with mock.patch.object(ks, "BURST_MARGIN_S", 0.05), mock.patch.object(ks.os, "open", spy_open), \
                mock.patch.object(ks.os, "close", spy_close):
            with self.assertRaises(ks.BufferUnavailable) as caught:
                self.k.sensor()._buffer_sample(3)
        self.assertIn("3 of 6 triples", str(caught.exception))
        self.assertEqual(self.k.get("iio:device2/buffer/enable"), "0")
        self.assertEqual(opened, [])

    def test_scans_are_read_in_the_order_and_size_the_kernel_says(self):
        """x last, y first, z second, big endian, 16 bits in 16: the offsets come from index and type."""
        k = FakeKernel(type_="be:s16/16>>0", index=(2, 0, 1))
        self.addCleanup(k.close)
        # the scan holds y, z, x; feed() writes the triple as it is, so it is given in that order
        k.feed(JUNK + [(-20, 1000, 10)] * 2, pack=lambda v: struct.pack(">h", v))
        self.assertEqual(k.sensor().sample(2), (10.0, -20.0, 1000.0))

    def test_a_scan_is_not_split_by_the_reads(self):
        """Scans can arrive in any piece: three bytes now, the rest later."""
        scan = b"".join(word(v) for v in (7, 8, 9))
        os.write(self.k.feeder, b"".join(word(v) for v in JUNK[0]) * ks.SETTLE_SAMPLES)
        os.write(self.k.feeder, scan[:3])
        timer = threading.Timer(0.05, lambda: os.write(self.k.feeder, scan[3:]))
        timer.daemon = True
        timer.start()
        self.addCleanup(timer.cancel)
        self.assertEqual(self.k.sensor().sample(1), (7.0, 8.0, 9.0))

    def test_one_reader_at_a_time_the_second_waits_for_the_first(self):
        """The kernel lets one process open the node; the other waits for the burst of the first."""
        real, calls = os.open, []

        def busy_twice(path, flags, *a):
            calls.append(path)
            if len(calls) <= 2:
                raise OSError(errno.EBUSY, "Device or resource busy")
            return real(path, flags, *a)
        self.k.feed(JUNK + [(1, 2, 3)])
        with mock.patch.object(ks.os, "open", busy_twice):
            self.assertEqual(self.k.sensor().sample(1), (1.0, 2.0, 3.0))
        self.assertEqual(len(calls), 3)


class Trigger(unittest.TestCase):

    def test_the_timer_trigger_is_made_through_configfs_when_it_is_not_there(self):
        k = FakeKernel()
        self.addCleanup(k.close)
        shutil.rmtree(os.path.join(k.root, "trigger0"))
        made = []

        def configfs(path, exist_ok=False):
            REAL_MAKEDIRS(path, exist_ok=exist_ok)
            made.append(path)
            k.add_trigger()
        k.feed(JUNK + [(1, 2, 3)])
        with mock.patch.object(ks.os, "makedirs", configfs):
            self.assertEqual(k.sensor().sample(1), (1.0, 2.0, 3.0))
        self.assertEqual(made, [os.path.join(k.configfs, "iio", "triggers", "hrtimer", ks.TRIGGER)])

    def test_an_existing_trigger_is_used_and_nothing_is_made(self):
        k = FakeKernel()
        self.addCleanup(k.close)
        k.feed(JUNK + [(1, 2, 3)])
        with mock.patch.object(ks.os, "makedirs", side_effect=AssertionError("made again")):
            k.sensor().sample(1)

    def test_a_kernel_without_the_trigger_falls_back_and_says_why(self):
        k = FakeKernel()
        self.addCleanup(k.close)
        shutil.rmtree(os.path.join(k.root, "trigger0"))        # nothing appears when the directory is made
        err = io.StringIO()
        with redirect_stderr(err):
            sample = k.sensor(quiet=False).sample(1)
        self.assertEqual(sample, (26.0, 172.0, 1068.0))        # the sysfs files of the fake
        self.assertIn("did not appear", err.getvalue())


class Fallback(unittest.TestCase):

    def test_a_kernel_without_a_buffer_reads_through_sysfs_and_says_so_once(self):
        iio = t.FakeIio()
        self.addCleanup(iio.close)
        err = io.StringIO()
        sensor = ks.Sensor(iio.device, None, False)
        with redirect_stderr(err):
            self.assertEqual(sensor.sample(2), (26.0, 172.0, 1068.0))
            sensor.sample(2)
        self.assertEqual(err.getvalue().count("warning: no IIO buffer"), 1, err.getvalue())
        self.assertIn("buffer is not there", err.getvalue())
        self.assertIn("about 0.4 s a reading", err.getvalue())

    def test_quiet_says_nothing(self):
        iio = t.FakeIio()
        self.addCleanup(iio.close)
        err = io.StringIO()
        with redirect_stderr(err):
            ks.Sensor(iio.device, None, True).sample(1)
        self.assertEqual(err.getvalue(), "")

    def test_a_failing_buffer_falls_back_to_sysfs_and_tries_the_buffer_again_next_time(self):
        k = FakeKernel()
        self.addCleanup(k.close)
        sensor = k.sensor(quiet=False)
        err = io.StringIO()
        with mock.patch.object(ks, "BURST_MARGIN_S", 0.05), redirect_stderr(err):
            self.assertEqual(sensor.sample(1), (26.0, 172.0, 1068.0))       # nothing in the FIFO
            k.feed(JUNK + [(1, 2, 3)])
            self.assertEqual(sensor.sample(1), (1.0, 2.0, 3.0))             # the buffer again
        self.assertEqual(err.getvalue().count("warning: no IIO buffer"), 1, err.getvalue())

    def test_a_node_that_stays_busy_falls_back(self):
        k = FakeKernel()
        self.addCleanup(k.close)
        err = io.StringIO()
        with mock.patch.object(ks, "BUSY_WAIT_S", 0.05), \
                mock.patch.object(ks.os, "open", side_effect=OSError(errno.EBUSY, "Device or resource busy")), \
                redirect_stderr(err):
            self.assertEqual(k.sensor(quiet=False).sample(1), (26.0, 172.0, 1068.0))
        self.assertIn("Device or resource busy", err.getvalue())

    def test_the_rate_is_not_written_when_the_device_has_it(self):
        """A write is refused while another reader has the buffer on."""
        k = FakeKernel()
        self.addCleanup(k.close)
        real, writes = open, []

        def spy(path, mode="r", *a, **kw):
            if "w" in mode:
                writes.append(os.path.basename(path))
            return real(path, mode, *a, **kw)
        with mock.patch("builtins.open", spy):
            ks.Sensor(k.device, 100.0)                         # the fake has 100 already
            self.assertEqual(writes, [])
            ks.Sensor(k.device, 50.0)
            self.assertEqual(writes, ["sampling_frequency"])


class Commands(unittest.TestCase):
    """The commands against the fake kernel, end to end."""

    def setUp(self):
        self.k = FakeKernel()
        self.addCleanup(self.k.close)
        self.dir = tempfile.mkdtemp(prefix="h713-buf-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        patches = (mock.patch.object(ks, "DEV_DIR", self.k.dev), mock.patch.object(ks, "CONFIGFS", self.k.configfs))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.base = ["-C", os.path.join(self.dir, "keystone.conf"), "--reference", os.path.join(self.dir, "ref"),
                     "--device", self.k.device, "--quiet"]

    def run_tool(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = ks.main(self.base + list(args))
        return code, out.getvalue()

    def test_once_reads_the_nose_up_pose_through_the_buffer(self):
        self.k.feed(JUNK + [t.REST] * 10)
        self.assertEqual(self.run_tool("reference")[0], 0)                  # the level pose, taken through the buffer too
        self.k.feed(JUNK + [t.POSES[1][1:4]] * 10)
        code, out = self.run_tool("once")
        self.assertEqual(code, 0)
        self.assertIn("pitch 20.586", out)

    def test_a_reading_through_the_buffer_equals_the_one_through_sysfs(self):
        self.k.feed(JUNK + [t.REST] * 10)
        buffered = self.run_tool("read")[1]
        shutil.rmtree(os.path.join(self.k.device, "buffer"))                # now the kernel has none
        self.assertEqual(self.run_tool("read")[1], buffered)

    def test_the_fall_back_is_said_unless_the_tool_is_asked_to_be_quiet(self):
        shutil.rmtree(os.path.join(self.k.device, "buffer"))
        for flags, said in (([], True), (["--quiet"], False)):
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(ks.main([a for a in self.base if a != "--quiet"] + flags + ["read"]), 0)
            self.assertEqual("no IIO buffer" in err.getvalue(), said, err.getvalue())

    def test_watch_takes_a_burst_every_half_second_and_not_every_tenth(self):
        """The sensor is on for a burst and the CPU busy for it only: between two readings watch waits WATCH_PAUSE_S."""
        with open(os.path.join(self.dir, "keystone.conf"), "w") as fh:
            fh.write("average_samples = 1\n")
        self.k.feed(JUNK + [t.REST] * 40)
        calls = []
        real = ks.Sensor._buffer_sample

        def spy(sensor, count):
            calls.append(time.monotonic())
            return real(sensor, count)
        with mock.patch.object(ks.Sensor, "_buffer_sample", spy):
            self.assertEqual(self.run_tool("watch", "--dry-run", "--for", "1.4")[0], 0)
        self.assertTrue(2 <= len(calls) <= 4, calls)
        self.assertGreaterEqual(min(b - a for a, b in zip(calls, calls[1:])), ks.WATCH_PAUSE_S)

    def test_the_start_line_of_watch_says_how_the_readings_come(self):
        buffered = self.k.sensor().cadence(10, ks.WATCH_PAUSE_S)
        self.assertEqual(buffered[1], "through the IIO buffer")
        self.assertAlmostEqual(buffered[0], 0.66, places=2)                 # 13 triples at 100 Hz, the setup, the pause
        shutil.rmtree(os.path.join(self.k.device, "buffer"))
        sysfs = self.k.sensor().cadence(10, ks.WATCH_PAUSE_S)
        self.assertIn("through sysfs", sysfs[1])
        self.assertAlmostEqual(sysfs[0], 2.3, places=1)                     # thirty values at 60 ms, the pause
        code, out = self.run_tool("watch", "--dry-run", "--for", "0.2")
        self.assertIn("a reading every ~2.30 s through sysfs", out)


if __name__ == "__main__":
    unittest.main()
