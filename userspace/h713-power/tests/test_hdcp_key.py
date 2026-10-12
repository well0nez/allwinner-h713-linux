"""Tests for h713-hdcp-key --bind (rootfs/overlay), the bind h713-mips-restart uses after a new start of the MIPS.

No device and no key: the Secure Storage is a temporary file with one made-up item of the right shape, built
here at run time (its payload is a counting pattern, not key material); the firmware directory, the
firmware_class path parameter and the driver's bind file are temporary files. What counts: the payload lies in
the firmware directory (0600) and the path parameter points there exactly while the receiver is bound, and
both are gone afterwards, whatever the bind did.
"""
import importlib.machinery
import importlib.util
import os
import signal
import struct
import sys
import tempfile
import types
import unittest
import zlib

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                    "rootfs", "overlay", "usr", "local", "sbin", "h713-hdcp-key")


def load():
    loader = importlib.machinery.SourceFileLoader("h713_hdcp_key", TOOL)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("h713_hdcp_key", loader))
    loader.exec_module(mod)
    return mod


def storage(m, payload):
    """One 4 KiB slot holding a store_object_t named m.ITEM around payload, with its CRC."""
    data = m.ITEM.encode().ljust(64, b"\0") + struct.pack("<III", len(payload), 0x10000001, 1) + payload
    head = struct.pack("<II", m.MAGIC, 1) + m.ITEM.encode().ljust(64, b"\0") + bytes(24)
    obj = head + struct.pack("<I", 76 + len(payload)) + data.ljust(m.DATA, b"\0")
    obj += struct.pack("<I", zlib.crc32(obj) & 0xffffffff)
    return obj.ljust(m.SLOT, b"\0")


class Bind(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.m = m = load()
        self.payload = bytes(i % 251 for i in range(m.ERWARTET))
        m.PARTLABEL = os.path.join(d, "hy310-keys")
        with open(m.PARTLABEL, "wb") as f:
            f.write(storage(m, self.payload))
        m.FW_DIR = os.path.join(d, "run", "firmware")
        m.FW_PATH_PARAM = os.path.join(d, "path")
        m.BIND = os.path.join(d, "bind")
        with open(m.FW_PATH_PARAM, "w") as f:
            f.write("\n")
        self.calls, self.seen = [], []
        m.subprocess = types.SimpleNamespace(run=lambda *a, **k: self.calls.append(a[0]))   # this module only
        m.modul_geladen = lambda: False
        real = m.binden

        def spy(dev):                                  # what the probe would find at the bind
            key = os.path.join(m.FW_DIR, m.FW_NAME)
            with open(m.FW_PATH_PARAM) as f:
                param = f.read()
            got = mode = None
            if os.path.exists(key):
                with open(key, "rb") as f:
                    got, mode = f.read(), os.stat(key).st_mode & 0o777
            self.seen.append((dev, got, mode, param))
            return real(dev)
        m.binden = spy

    def main(self, *args):
        self.addCleanup(setattr, sys, "argv", sys.argv)
        sys.argv = ["h713-hdcp-key"] + list(args)
        return self.m.main()

    def after(self):
        """Nothing of the key is left, the path parameter is empty again."""
        self.assertFalse(os.path.exists(os.path.join(self.m.FW_DIR, self.m.FW_NAME)))
        with open(self.m.FW_PATH_PARAM) as f:
            self.assertEqual(f.read(), "\n")

    def test_bind_with_the_key_lying_there(self):
        self.assertEqual(self.main("--bind", "hdmi-rx"), 0)
        self.assertEqual(self.seen, [("hdmi-rx", self.payload, 0o600, self.m.FW_DIR)])
        with open(self.m.BIND) as f:
            self.assertEqual(f.read(), "hdmi-rx")
        self.assertEqual(self.calls, [])                # no modprobe, no systemctl
        self.after()

    def test_no_key_found_still_binds_and_says_3(self):
        with open(self.m.PARTLABEL, "wb") as f:
            f.write(bytes(self.m.SLOT))
        self.assertEqual(self.main("--bind", "hdmi-rx"), 3)
        self.assertEqual(self.seen, [("hdmi-rx", None, None, "\n")])
        self.after()

    def test_a_failed_bind_is_1_and_the_key_is_gone(self):
        os.mkdir(self.m.BIND)                           # the write fails like a probe that fails
        self.assertEqual(self.main("--bind", "hdmi-rx"), 1)
        self.assertEqual(len(self.seen), 1)
        self.after()

    def test_bind_without_a_device_writes_nothing(self):
        self.assertEqual(self.main("--bind"), 2)
        self.assertEqual(self.seen, [])
        self.assertFalse(os.path.exists(self.m.FW_DIR))

    def keep_signals(self):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))

    def test_a_write_that_fails_leaves_no_key_behind(self):
        # TODO 5.14 U3: the file exists from os.open on - its write is inside the try that deletes it
        self.keep_signals()
        real = self.m.os.write

        def full(fd, data):
            real(fd, data[:100])
            raise OSError(28, "No space left on device")
        self.m.os = types.SimpleNamespace(**{k: getattr(os, k) for k in dir(os) if not k.startswith("__")})
        self.m.os.write, self.m.os.path = full, os.path
        with self.assertRaises(OSError):
            self.main("--bind", "hdmi-rx")
        self.assertEqual(self.seen, [])
        self.after()

    def test_sigterm_during_the_bind_ends_through_the_cleanup(self):
        self.keep_signals()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        bind = self.m.binden

        def killed(dev):
            os.kill(os.getpid(), signal.SIGTERM)        # systemd stopping the unit, say
            return bind(dev)
        self.m.binden = killed
        with self.assertRaises(SystemExit) as end:
            self.main("--bind", "hdmi-rx")
        self.assertEqual(end.exception.code, 128 + signal.SIGTERM)
        self.after()

    def test_a_signal_the_caller_ignores_stays_ignored(self):
        # h713-mips-restart starts the tool with INT, TERM and HUP ignored: the write must not be cut
        self.keep_signals()
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        self.assertEqual(self.main("--bind", "hdmi-rx"), 0)
        self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_IGN)
        self.assertIs(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)
        self.after()

    def test_without_bind_the_boot_path_is_unchanged(self):
        self.assertEqual(self.main(), 0)
        self.assertEqual(self.calls, [["modprobe", self.m.MODUL]])
        self.assertEqual(self.seen, [])
        self.after()


if __name__ == "__main__":
    unittest.main()
