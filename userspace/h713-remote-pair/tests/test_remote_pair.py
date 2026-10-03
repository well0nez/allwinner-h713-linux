"""Tests for tools/h713-remote-pair against tests/fake_bluetoothctl.py (no bluez, no device)."""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# the tool beside tests/ (userspace/h713-remote-pair) or under tools/ (the FB-REMOTE package)
TOOL = next(p for p in (os.path.join(HERE, "..", "h713-remote-pair"), os.path.join(HERE, "..", "tools", "h713-remote-pair"))
            if os.path.exists(p))
FAKE = os.path.join(HERE, "fake_bluetoothctl.py")
CTL = sys.executable + " " + FAKE
REMOTE = "AA:BB:CC:DD:EE:01"


def load_tool():
    loader = importlib.machinery.SourceFileLoader("h713_remote_pair", TOOL)
    spec = importlib.util.spec_from_loader("h713_remote_pair", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def run(args, scenario="found", log=None):
    env = dict(os.environ, FAKE_SCENARIO=scenario, H713_BLUETOOTHCTL=CTL)
    if log:
        env["FAKE_LOG"] = log
    return subprocess.run([sys.executable, TOOL] + args, env=env, capture_output=True, text=True, timeout=60)


class Parsing(unittest.TestCase):
    def setUp(self):
        self.m = load_tool()

    def test_clean_strips_bluetoothctl_escapes(self):
        self.assertEqual(self.m.clean("\x01\x1b[0;94m\x02[bluetooth]\x01\x1b[0m\x02# [NEW] Device AA:BB:CC:DD:EE:01 BLE_X_RMC"),
                         "[bluetooth]# [NEW] Device AA:BB:CC:DD:EE:01 BLE_X_RMC")

    def test_device_line_forms(self):
        for line in ("[NEW] Device AA:BB:CC:DD:EE:01 BLE_X_RMC", "Device AA:BB:CC:DD:EE:01 BLE_X_RMC",
                     "[CHG] Device AA:BB:CC:DD:EE:01 Name: BLE_X_RMC"):
            m = self.m.DEVICE_LINE.search(line)
            self.assertIsNotNone(m, line)
            self.assertEqual((m.group(1), m.group(2)), (REMOTE, "BLE_X_RMC"))
        m = self.m.DEVICE_LINE.search("[CHG] Device AA:BB:CC:DD:EE:01 RSSI: -60")
        self.assertFalse(self.m.name_matches(m.group(2), self.m.NAMES), "a property line is no name")

    def test_info_observes_disconnect_after_initial_connected_field(self):
        class StandIn:
            def send(self, cmd):
                pass
            def lines(self, timeout):
                yield "Device %s (public)" % REMOTE
                yield "Connected: yes"
                yield "UUID: Human Interface Device (%s)" % self_uuid
                yield "[CHG] Device %s Connected: no" % REMOTE
        self_uuid = self.m.HOG_UUID
        info = self.m.device_info(StandIn(), REMOTE)
        self.assertTrue(info["hog"])
        self.assertFalse(info["connected"])

    def test_name_matches_is_substring_like_stock(self):
        self.assertTrue(self.m.name_matches("BLE_X_RMC", self.m.NAMES))
        self.assertTrue(self.m.name_matches("Great Wall 2", self.m.NAMES))
        self.assertFalse(self.m.name_matches("JBL Flip", self.m.NAMES))


class Commands(unittest.TestCase):
    def test_pair_bonds_trusts_connects(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log")
            r = run(["pair", "--timeout", "5"], log=log)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("found " + REMOTE + " BLE_X_RMC", r.stdout)
            self.assertIn("ok paired " + REMOTE, r.stdout)
            with open(log, encoding="utf-8") as f:
                sent = f.read()
        self.assertIn("argv --agent NoInputNoOutput", sent)
        self.assertIn("cmd scan le", sent)
        self.assertNotIn("cmd scan on", sent)
        self.assertIn("cmd info " + REMOTE, sent)
        for verb in ("pair", "trust", "connect"):
            self.assertIn("cmd %s %s" % (verb, REMOTE), sent)
        self.assertNotIn("AA:BB:CC:DD:EE:02", sent, "the foreign device must not be paired")

    def test_pair_times_out_without_a_remote(self):
        r = run(["pair", "--timeout", "1"], scenario="none")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no remote in pairing mode", r.stdout)

    def test_pair_reports_bluez_refusal(self):
        r = run(["pair", "--timeout", "5"], scenario="pairfail")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error: pair " + REMOTE, r.stderr)

    def test_name_option_replaces_the_stock_list(self):
        r = run(["--name", "Foo", "pair", "--timeout", "5"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("found AA:BB:CC:DD:EE:02 Foo Remote", r.stdout)

    def test_status_connected_and_not(self):
        r = run(["status"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), REMOTE + " BLE_X_RMC connected")
        r = run(["status"], scenario="unconnected")
        self.assertEqual(r.returncode, 0)
        self.assertIn("bonded, not connected", r.stdout)
        r = run(["status"], scenario="empty")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no remote bonded", r.stdout)

    def test_a_paired_speaker_with_a_stock_name_is_not_a_remote(self):
        """JVIN Soundbar, paired and connected: not HID over GATT, so status says
        none, forget leaves it alone, watch keeps scanning (deep review F5)."""
        r = run(["status"], scenario="speaker")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no remote bonded", r.stdout)
        r = run(["forget"], scenario="speaker")
        self.assertNotIn("ok forgot", r.stdout)
        r = run(["watch", "--once", "--timeout", "1"], scenario="speaker")
        self.assertIn("no remote in pairing mode", r.stdout)

    def test_status_empty_original(self):
        r = run(["status"], scenario="empty")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no remote bonded", r.stdout)

    def test_forget_all_and_one(self):
        r = run(["forget"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "ok forgot " + REMOTE)
        r = run(["forget", "AA:BB:CC:DD:EE:02"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("ok forgot AA:BB:CC:DD:EE:02", r.stdout)

    def test_watch_once_reconnects_a_bonded_remote(self):
        r = run(["watch", "--once", "--timeout", "5"], scenario="unconnected")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ok connected " + REMOTE, r.stdout)
        r = run(["watch", "--once", "--timeout", "5"], scenario="found")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("found", r.stdout, "a connected remote means no scan")

    def test_reconnect_does_not_pair_or_remove_a_bond(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log")
            r = run(["reconnect", "--timeout", "3"], scenario="unconnected", log=log)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(log) as f:
                sent = f.read()
        self.assertIn("cmd connect " + REMOTE, sent)
        self.assertNotIn("cmd pair ", sent)
        self.assertNotIn("cmd remove ", sent)
        self.assertNotIn("cmd scan ", sent)

    def test_watch_does_not_repair_after_connection_failure(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log")
            r = run(["watch", "--once", "--timeout", "3"], scenario="connectfail", log=log)
            self.assertEqual(r.returncode, 2, r.stderr)
            with open(log) as f:
                sent = f.read()
        self.assertNotIn("cmd pair ", sent)
        self.assertNotIn("cmd remove ", sent)
        self.assertIn("wake the remote", r.stderr)

    def test_transient_connected_event_is_not_connection_success(self):
        r = run(["reconnect", "--timeout", "3"], scenario="flakyconnect")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertNotIn("ok connected", r.stdout)

    def test_pair_does_not_accept_transient_connected_before_auth_failure(self):
        r = run(["pair", "--timeout", "3"], scenario="flakypair")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("error: connect", r.stderr)
        self.assertNotIn("ok paired", r.stdout)

    def test_matching_name_without_hog_is_not_paired(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log")
            r = run(["pair", "--timeout", "3"], scenario="speaker_advert", log=log)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            with open(log) as f:
                sent = f.read()
        self.assertNotIn("cmd pair ", sent)

    def test_reconnect_retries_temporary_abort_without_repairing(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log")
            r = run(["reconnect", "--timeout", "8"], scenario="abortonce", log=log)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(log) as f:
                sent = f.read()
        self.assertEqual(sent.count("cmd connect " + REMOTE), 2)
        self.assertNotIn("cmd pair ", sent)
        self.assertNotIn("cmd remove ", sent)

    def test_reconnect_without_bond_does_not_pair(self):
        r = run(["reconnect", "--timeout", "1"], scenario="empty")
        self.assertEqual(r.returncode, 1)
        self.assertIn("use pair for first-time setup", r.stdout)

    def test_missing_controller_is_not_reported_as_missing_bond(self):
        for args in (["status"], ["reconnect"], ["watch", "--once"]):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as d:
                log = os.path.join(d, "log")
                r = run(args, scenario="nocontroller", log=log)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("no Bluetooth controller", r.stderr)
                self.assertNotIn("no remote bonded", r.stdout)
                with open(log) as f:
                    sent = f.read()
                self.assertNotIn("cmd pair ", sent)
                self.assertNotIn("cmd scan ", sent)

    def test_missing_bluetoothctl_is_exit_3(self):
        r = subprocess.run([sys.executable, TOOL, "--ctl", "/nonexistent/bluetoothctl", "status"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 3)
        self.assertIn("cannot run", r.stderr)


if __name__ == "__main__":
    unittest.main()
