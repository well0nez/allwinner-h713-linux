"""Tests for tools/h713-remote-pair against tests/fake_bluetoothctl.py (no bluez, no device)."""
import importlib.machinery
import importlib.util
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# the tool beside tests/ (userspace/h713-remote-pair) or under tools/ (the FB-REMOTE package)
TOOL = next(p for p in (os.path.join(HERE, "..", "h713-remote-pair"), os.path.join(HERE, "..", "tools", "h713-remote-pair"))
            if os.path.exists(p))
FAKE = os.path.join(HERE, "fake_bluetoothctl.py")
CTL = sys.executable + " " + FAKE
REMOTE = "AA:BB:CC:DD:EE:01"
FOREIGN = "AA:BB:CC:DD:EE:02"
# The stock remote's advert in pairing mode, byte for byte as captured on 20.10.2026 (HY300PRO-G-EU, btmon):
# flags 0x05 (LE Limited Discoverable, BR/EDR not supported), HID service 0x1812, appearance remote control, name.
PAIRING_AD = bytes.fromhex("020105" "03031218" "03198001") + bytes([17, 0x09]) + b"Bluetooth remote"


def le_addr(addr):
    return bytes.fromhex(addr.replace(":", ""))[::-1]


def adv_report(addr, etype=0x00, data=PAIRING_AD):
    """an HCI LE Advertising Report event with one report (etype 0 ADV_IND, 1 ADV_DIRECT_IND, 3 ADV_NONCONN_IND)"""
    body = bytes([0x02, 1, etype, 0x00]) + le_addr(addr) + bytes([len(data)]) + data + bytes([0xc1])
    return bytes([0x3e, len(body)]) + body


def ext_adv_report(addr, etype=0x0013, data=PAIRING_AD):
    """an HCI LE Extended Advertising Report event with one report (0x0013: a legacy ADV_IND)"""
    rep = (struct.pack("<HB", etype, 0x00) + le_addr(addr) + bytes([1, 0, 0xff, 0x7f, 0xc1]) + struct.pack("<H", 0)
           + bytes(7) + bytes([len(data)]) + data)
    body = bytes([0x0d, 1]) + rep
    return bytes([0x3e, len(body)]) + body


def frames(*events):
    """HCI events as the kernel's monitor channel hands them out (opcode 3: event, index 0)"""
    return b"".join(struct.pack("<HHH", 3, 0, len(e)) + e for e in events)


def load_tool():
    loader = importlib.machinery.SourceFileLoader("h713_remote_pair", TOOL)
    spec = importlib.util.spec_from_loader("h713_remote_pair", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def run(args, scenario="found", log=None, monitor=os.devnull, **extra):
    """monitor: the HCI monitor frames watch reads (default none, never the host's own controller)"""
    env = dict(os.environ, FAKE_SCENARIO=scenario, H713_BLUETOOTHCTL=CTL, H713_HCI_MONITOR=monitor, **extra)
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

    def test_pair_finds_a_remote_whose_unpaired_object_is_left_over(self):
        """HY300PRO-G-EU 20.10.2026: bluez kept the remote's object, the scan showed it only as [CHG] for 40 s"""
        r = run(["pair", "--timeout", "5"], scenario="leftover")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("found " + REMOTE + " BLE_X_RMC", r.stdout)
        self.assertIn("ok paired " + REMOTE, r.stdout)

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

    def test_watch_says_each_line_while_it_runs(self):
        """under systemd stdout is a pipe: the lines must come while watch keeps running, not at its end"""
        import select, time
        env = dict(os.environ, FAKE_SCENARIO="empty", H713_BLUETOOTHCTL=CTL, H713_HCI_MONITOR=os.devnull)
        p = subprocess.Popen([sys.executable, TOOL, "watch", "--interval", "30", "--timeout", "3"], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            got, end = "", time.monotonic() + 10
            while "ok paired" not in got and time.monotonic() < end:
                if select.select([p.stdout], [], [], 0.2)[0]:     # not readline: a second line kept in its
                    got += os.read(p.stdout.fileno(), 4096).decode()    # buffer is invisible to select
            self.assertIsNone(p.poll(), "watch should still be running")
            self.assertIn("found " + REMOTE, got)
            self.assertIn("ok paired " + REMOTE, got)
        finally:
            p.kill()
            p.wait()

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


class Adverts(unittest.TestCase):
    """the pairing-mode advert, read from HCI events"""

    def setUp(self):
        self.m = load_tool()

    def test_the_pairing_advert_is_found(self):
        self.assertEqual(list(self.m.pairing_adverts(adv_report(REMOTE))), [REMOTE])
        self.assertEqual(list(self.m.pairing_adverts(ext_adv_report(REMOTE))), [REMOTE])

    def test_other_adverts_are_no_pairing_request(self):
        general = bytes.fromhex("020106") + PAIRING_AD[3:]          # LE General Discoverable only
        for event in (adv_report(REMOTE, 0x01, b""),                 # ADV_DIRECT_IND: how a bonded remote wakes
                      adv_report(REMOTE, 0x00, general),
                      adv_report(REMOTE, 0x03),                      # not connectable
                      adv_report(REMOTE, 0x04),                      # a scan response
                      ext_adv_report(REMOTE, 0x0015, b""),           # extended: directed
                      ext_adv_report(REMOTE, 0x0010),                # extended: not connectable
                      bytes([0x0e, 4, 1, 0x0c, 0x0c, 0]),            # a command complete
                      adv_report(REMOTE)[:9],                        # cut short
                      bytes([0x3e, 3, 0x02, 9, 0])):                 # claims nine reports, has none
            with self.subTest(event=event.hex()):
                self.assertEqual(list(self.m.pairing_adverts(event)), [])


class StaleBond(unittest.TestCase):
    """TODO 2.92: Left+Right pairs afresh while the box keeps a bond the remote has lost"""

    def test_watch_pairs_afresh_when_the_bonded_remote_is_in_pairing_mode(self):
        with tempfile.TemporaryDirectory() as d:
            log, hci = os.path.join(d, "log"), os.path.join(d, "hci")
            with open(hci, "wb") as f:
                f.write(frames(adv_report(REMOTE)))
            r = run(["watch", "--once", "--timeout", "5"], scenario="stale", log=log, monitor=hci)
            with open(log) as f:
                sent = f.read()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("cmd remove " + REMOTE, sent)
        self.assertLess(sent.index("cmd remove " + REMOTE), sent.index("cmd pair " + REMOTE))
        self.assertIn("ok forgot " + REMOTE, r.stdout)
        self.assertIn("ok paired " + REMOTE, r.stdout)

    def test_the_advert_that_comes_during_a_reconnect_counts(self):
        """as on 20.10.2026: the stale link looks connected for a moment, the advert arrives meanwhile"""
        with tempfile.TemporaryDirectory() as d:
            log, hci = os.path.join(d, "log"), os.path.join(d, "hci")
            os.mkfifo(hci)
            r = run(["watch", "--once", "--timeout", "5"], scenario="stale", log=log, monitor=hci,
                    FAKE_HCI=hci, FAKE_HCI_FRAMES=frames(adv_report(REMOTE)).hex())
            with open(log) as f:
                sent = f.read()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(sent.index("cmd connect " + REMOTE), sent.index("cmd remove " + REMOTE))
        self.assertIn("ok paired " + REMOTE, r.stdout)

    def test_the_advert_ends_a_connect_that_gets_no_answer(self):
        """the connect gets no answer; the advert must not wait for its timeout of 20 s"""
        with tempfile.TemporaryDirectory() as d:
            log, hci = os.path.join(d, "log"), os.path.join(d, "hci")
            os.mkfifo(hci)
            start = time.monotonic()
            r = run(["watch", "--once", "--timeout", "20"], scenario="stalesilent", log=log, monitor=hci,
                    FAKE_HCI=hci, FAKE_HCI_FRAMES=frames(adv_report(REMOTE)).hex())
            took = time.monotonic() - start
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok paired " + REMOTE, r.stdout)
        self.assertLess(took, 15, "the connect was waited out")

    def test_a_normal_reconnect_never_forgets_the_bond(self):
        """control: the bonded remote wakes (directed advert), other adverts of it and a foreign remote in pairing
        mode; bluez's AdvertisingFlags still say 05 from the last pairing"""
        general = bytes.fromhex("020106") + PAIRING_AD[3:]
        with tempfile.TemporaryDirectory() as d:
            log, hci = os.path.join(d, "log"), os.path.join(d, "hci")
            with open(hci, "wb") as f:
                f.write(frames(adv_report(REMOTE, 0x01, b""), adv_report(REMOTE, 0x00, general),
                               adv_report(REMOTE, 0x03), adv_report(FOREIGN)))
            r = run(["watch", "--once", "--timeout", "5"], scenario="unconnected", log=log, monitor=hci)
            with open(log) as f:
                sent = f.read()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok connected " + REMOTE, r.stdout)
        for cmd in ("cmd remove ", "cmd pair ", "cmd scan "):
            self.assertNotIn(cmd, sent)

    def test_a_new_bond_is_kept_after_the_adverts_that_made_it(self):
        """first pairing: the remote's pairing adverts came before the bond; the next rounds must not forget it"""
        with tempfile.TemporaryDirectory() as d:
            log, hci = os.path.join(d, "log"), os.path.join(d, "hci")
            with open(hci, "wb") as f:
                f.write(frames(adv_report(REMOTE)))
            open(log, "w").close()
            env = dict(os.environ, FAKE_SCENARIO="empty", H713_BLUETOOTHCTL=CTL, FAKE_LOG=log, H713_HCI_MONITOR=hci)
            p = subprocess.Popen([sys.executable, TOOL, "watch", "--interval", "0.5", "--timeout", "5"], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                end = time.monotonic() + 30
                while time.monotonic() < end:
                    with open(log) as f:
                        if f.read().count("cmd devices Paired") >= 3:
                            break
                    time.sleep(0.2)
            finally:
                p.kill()
                out = p.communicate()[0]
            with open(log) as f:
                sent = f.read()
        self.assertGreaterEqual(sent.count("cmd devices Paired"), 3, out)
        self.assertIn("ok paired " + REMOTE, out)
        self.assertEqual(sent.count("cmd pair " + REMOTE), 1, out)
        self.assertNotIn("cmd remove ", sent, out)

    def test_watch_without_the_monitor_channel_keeps_working(self):
        r = run(["watch", "--once", "--timeout", "5"], scenario="unconnected", monitor="/nonexistent/hci")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok connected " + REMOTE, r.stdout)
        self.assertIn("HCI monitor", r.stderr)


if __name__ == "__main__":
    unittest.main()
