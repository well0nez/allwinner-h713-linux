"""h713-remote-pair watch against tests/fake_world.py: the remote and the kernel with the times measured on the
HY300PRO-G-EU (20.10.2026). Left + Right at several points of watch's round and with all times halved or
doubled must pair afresh in one press, without a single connection on the dropped key."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.environ.get("H713_REMOTE_PAIR_TOOL") or next(
    p for p in (os.path.join(HERE, "..", "h713-remote-pair"), os.path.join(HERE, "..", "tools", "h713-remote-pair"))
    if os.path.exists(p))
WORLD = os.path.join(HERE, "fake_world.py")


def run_worlds(cases, tool=TOOL):
    """Run watch once per case (plan, press, scale) at the same time; -> {case: (status, output, commands)}"""
    runs = []
    with tempfile.TemporaryDirectory() as d:
        for i, (plan, press, scale) in enumerate(cases):
            base = os.path.join(d, str(i))
            os.mkfifo(base + ".hci")
            env = dict(os.environ, WORLD_PLAN=plan, WORLD_PRESS=str(press), WORLD_SCALE=str(scale),
                       FAKE_HCI=base + ".hci", WORLD_STATUS=base + ".status", FAKE_LOG=base + ".log",
                       H713_HCI_MONITOR=base + ".hci", H713_HCI_MGMT=base + ".mgmt",
                       H713_BLUETOOTHCTL=sys.executable + " " + WORLD)
            p = subprocess.Popen([sys.executable, TOOL if tool is None else tool, "watch", "--interval", "3",
                                  "--timeout", "20"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            runs.append(((plan, press, scale), base, p, time.monotonic() + press + (25 if plan.endswith("twice") else 16) * scale + 4))
        out = {}
        for case, base, p, end in runs:
            while time.monotonic() < end:
                try:
                    st = json.load(open(base + ".status"))
                except (OSError, ValueError):
                    st = {}
                done = st.get("pairings", 0) >= (2 if case[0].endswith("twice") else 1)
                if done or (case[0].startswith("wake") and st.get("connected")):
                    time.sleep(1.0)     # what watch does right after
                    break
                time.sleep(0.2)
            p.kill()
            text = p.communicate()[0]
            try:
                st = json.load(open(base + ".status"))
            except (OSError, ValueError):
                st = {}
            log = open(base + ".log").read() if os.path.exists(base + ".log") else ""
            out[case] = (st, text, log)
        return out


class World(unittest.TestCase):
    def test_left_right_pairs_afresh_in_one_press_at_any_time(self):
        """stale bond (remote paired elsewhere) and valid bond (the press itself drops the key)"""
        cases = [(plan, press, scale) for plan in ("stale-press", "valid-press")
                 for press in (3.2, 4.0, 4.8, 5.6) for scale in (0.5, 1.0, 2.0)]
        for case, (st, text, log) in run_worlds(cases).items():
            with self.subTest(case=case):
                self.assertTrue(st.get("paired_afresh"), "\n".join(st.get("events", [])) + "\n" + text)
                self.assertEqual(st.get("failures"), 0, st.get("events"))
                self.assertEqual(st.get("kernel_connects"), 0, st.get("events"))
                self.assertEqual(log.count("cmd pair "), 1, text)

    def test_the_second_press_pairs_as_well(self):
        """after each pairing bluetoothd lets the kernel connect on any advert again; watch takes it back"""
        for case, (st, text, log) in run_worlds([("valid-press-twice", 3.2, 1.0), ("valid-press-twice", 4.4, 0.5)]).items():
            with self.subTest(case=case):
                self.assertEqual(st.get("pairings"), 2, "\n".join(st.get("events", [])) + "\n" + text)
                self.assertEqual(st.get("failures"), 0, st.get("events"))
                self.assertEqual(st.get("kernel_connects"), 0, st.get("events"))

    def test_a_remote_that_wakes_is_never_forgotten(self):
        """control: a directed advert is connected by the kernel, an undirected one by watch; no forget"""
        cases = [("wake", 3.2, 1.0), ("wake", 4.8, 1.0), ("wake", 4.0, 2.0), ("wake-undirected", 4.0, 1.0)]
        for case, (st, text, log) in run_worlds(cases).items():
            with self.subTest(case=case):
                self.assertTrue(st.get("connected"), "\n".join(st.get("events", [])) + "\n" + text)
                self.assertEqual(st.get("failures"), 0)
                self.assertNotIn("cmd remove ", log)
                self.assertNotIn("cmd pair ", log)
                if case[0] == "wake":
                    self.assertNotIn("cmd connect ", log, "the kernel connects a directed advert")


if __name__ == "__main__":
    unittest.main()
