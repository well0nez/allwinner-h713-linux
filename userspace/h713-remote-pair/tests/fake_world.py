#!/usr/bin/env python3
"""A bluetoothctl stand-in that plays the stock remote and the kernel with the times measured on the
HY300PRO-G-EU (btmon, 20.10.2026), for tests of h713-remote-pair watch.

The remote: Left + Right drops its key and ends a connection; 0.65 s later it advertises undirected with
flags 0x05 (LE Limited Discoverable), again 0.3 s after each advert or failed connection. After three
connections that failed on the dropped key it leaves pairing mode (measured in three of four episodes),
otherwise after 30 s. A remote that wakes with a valid bond sends a directed advert (no data).
The kernel: with a bond it connects on a directed advert when its auto-connect action is 1 or 2, on an
undirected one only with action 2 - bluetoothd's - or for a pending connect or pair. The action is the
last mgmt Add Device for the remote in H713_HCI_MGMT (watch writes it); bluetoothd's action 2 holds until
then and comes back with each pairing (as a monitor frame, like bluetoothd's own command).

Env: WORLD_PLAN stale-press | valid-press | valid-press-twice (again 9 s later) | wake | wake-undirected,
WORLD_PRESS (s after start),
WORLD_SCALE (factor on all measured times), FAKE_HCI (FIFO watch reads as its monitor channel),
H713_HCI_MGMT, FAKE_LOG (commands), WORLD_STATUS (final state, rewritten on each change).
"""
import json
import os
import struct
import sys
import threading
import time

REMOTE, CTRL = "AA:BB:CC:DD:EE:01", "11:22:33:44:55:66"
PAIRING_AD = bytes.fromhex("020105" "03031218" "03198001") + bytes([17, 0x09]) + b"Bluetooth remote"
plan = os.environ.get("WORLD_PLAN", "stale-press")
scale = float(os.environ.get("WORLD_SCALE", "1"))
press = float(os.environ.get("WORLD_PRESS", "4"))
log, status_file, mgmt = os.environ.get("FAKE_LOG"), os.environ.get("WORLD_STATUS"), os.environ.get("H713_HCI_MGMT")
lock = threading.RLock()
st = {"bonded": True, "key_valid": plan != "stale-press", "connected": plan == "valid-press", "object": True,
      "pairing_mode": False, "failures": 0, "paired_afresh": False, "pairings": 0, "kernel_connects": 0, "action_default": 2,
      "scanning": False, "pending_pair": None, "pending_connect": None, "events": []}


def note(text):
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def say(*lines):
    with lock:
        for line in lines:
            sys.stdout.write(line + "\n")
        sys.stdout.flush()


def save():
    if status_file:
        with lock, open(status_file + ".tmp", "w") as f:
            json.dump({k: v for k, v in st.items() if k not in ("pending_pair", "pending_connect")}, f)
        os.replace(status_file + ".tmp", status_file)


def event(what):
    st["events"].append("%.3f %s" % (time.monotonic() - start, what))
    save()


def action():
    """the kernel's auto-connect action for the remote: watch's last Add Device since bluetoothd's own, else 2"""
    if not st["bonded"]:
        return None
    act = st["action_default"]
    if mgmt and os.path.exists(mgmt):
        data = open(mgmt, "rb").read()[st.get("mgmt_seen", 0):]
        while len(data) >= 6:
            op, _, size = struct.unpack_from("<HHH", data)
            if (op == 0x0033 and size >= 8 and ":".join("%02X" % b for b in reversed(data[6:12])) == REMOTE
                    and data[12] == 1):         # LE public, the remote's address type
                act = data[13]
            data = data[6 + size:]
    return act


hci = None


def hci_write(payload_op, payload):
    if hci:
        try:
            hci.write(struct.pack("<HHH", payload_op, 0, len(payload)) + payload)
            hci.flush()
        except OSError:
            pass


def advert(etype, data):
    body = bytes([0x02, 1, etype, 0x00]) + bytes.fromhex(REMOTE.replace(":", ""))[::-1] + bytes([len(data)]) + data + b"\xc1"
    hci_write(3, bytes([0x3e, len(body)]) + body)


def wait(seconds):
    time.sleep(seconds * scale)


def kernel_connect(why):
    """the kernel connects the advertising remote (called without the lock); True when the link holds"""
    with lock:
        st["kernel_connects"] += 1
    wait(0.065)                                     # LE connection complete
    with lock:
        say("[CHG] Device %s Connected: yes" % REMOTE)
        if st["key_valid"]:
            st["connected"] = True
            event("kernel connected (%s), encryption ok" % why)
            return True
    wait(0.11)                                      # LE Start Encryption -> PIN or Key Missing
    with lock:
        st["failures"] += 1
        say("[CHG] Device %s Connected: no" % REMOTE)
        event("kernel connected (%s), PIN or Key Missing #%d" % (why, st["failures"]))
        return False


def pairing_mode():
    with lock:
        if st["connected"]:
            st["connected"] = False
            say("[CHG] Device %s Connected: no" % REMOTE)
        st["key_valid"], st["pairing_mode"] = False, True
        event("Left + Right")
    wait(0.65)
    end = time.monotonic() + 30 * scale
    while time.monotonic() < end:
        with lock:
            advert(0x00, PAIRING_AD)
            act, pending_pair, pending_connect = action(), st["pending_pair"], st["pending_connect"]
            event("pairing advert (bonded %s, action %s)" % (st["bonded"], act))
            if not pending_pair and not (st["bonded"] and (act == 2 or pending_connect)) and st["scanning"]:
                say(("[CHG] Device %s RSSI: 0xffffffc1 (-63)" if st["object"] else "[NEW] Device %s Bluetooth remote") % REMOTE)
                st["object"] = True
        if pending_pair:
            wait(0.6)                                   # connection, pairing, keys
            with lock:
                st.update(bonded=True, key_valid=True, connected=True, pairing_mode=False, paired_afresh=True,
                          object=True, pending_pair=None, pairings=st["pairings"] + 1)
                say("Pairing successful")
                event("paired afresh")
            return
        if st["bonded"] and (act == 2 or pending_connect):
            kernel_connect("pending connect" if pending_connect else "auto-connect 2")
            with lock:
                if pending_connect:
                    st["pending_connect"] = None
                    say("Failed to connect: org.bluez.Error.Failed")
                if st["failures"] >= 3:
                    st["pairing_mode"] = False
                    event("remote leaves pairing mode after three failures")
                    return
        wait(0.3)
    with lock:
        st["pairing_mode"] = False
        event("pairing mode timed out")


def waking(directed):
    with lock:
        event("key pressed, remote wakes")
    for _ in range(20):
        with lock:
            if st["connected"]:
                return
            advert(0x01 if directed else 0x00, b"")
            pending = st["pending_connect"]
            go = st["bonded"] and (pending or action() in ((1, 2) if directed else (2,)))
        if go:
            kernel_connect("directed advert" if directed else "undirected advert")
            with lock:
                if pending:
                    st["pending_connect"] = None
                    say("Connection successful")
            return
        wait(0.3)


def twice():                    # the second press meets the bond of the first and bluetoothd's action 2 again
    pairing_mode()
    time.sleep(max(0.0, press + 9 * scale - (time.monotonic() - start)))
    pairing_mode()


def world():
    global hci
    fifo = os.environ.get("FAKE_HCI")
    if fifo:                                        # read-write: no wait for a reader (a watch without the monitor has none)
        hci = os.fdopen(os.open(fifo, os.O_RDWR), "wb")
    time.sleep(max(0.0, press - (time.monotonic() - start)))
    {"stale-press": pairing_mode, "valid-press": pairing_mode, "valid-press-twice": twice,
     "wake": lambda: waking(True), "wake-undirected": lambda: waking(False)}[plan]()
    save()


start = time.monotonic()
note("argv " + " ".join(sys.argv[1:]))
say("Agent registered")
save()
threading.Thread(target=world, daemon=True).start()
for raw in sys.stdin:
    cmd = raw.strip()
    note("cmd " + cmd)
    with lock:
        if cmd == "power on":
            say("Changing power on succeeded")
        elif cmd in ("devices Paired", "devices"):
            if st["bonded"] or (cmd == "devices" and st["object"]):
                say("Device %s Bluetooth remote" % REMOTE)
        elif cmd == "show":
            say("Controller %s (public)" % CTRL, "\tPowered: yes")
        elif cmd.startswith("info "):
            if st["object"]:
                say("Device %s (public)" % REMOTE, "\tName: Bluetooth remote", "\tPaired: %s" % ("yes" if st["bonded"] else "no"),
                    "\tConnected: %s" % ("yes" if st["connected"] else "no"),
                    "\tUUID: Human Interface Device    (00001812-0000-1000-8000-00805f9b34fb)",
                    "\tAdvertisingFlags:", "  05                                               .               ")
            else:
                say("Device %s not available" % cmd[5:])
        elif cmd == "scan le":
            st["scanning"] = True
            say("Discovery started")
        elif cmd == "scan off":
            st["scanning"] = False
            say("Discovery stopped")
        elif cmd.startswith("pair "):
            if st["bonded"]:
                say("Failed to pair: org.bluez.Error.AlreadyExists")
            else:                       # bluetoothd arms the kernel's auto-connect (any advert) as it starts pairing
                st.update(pending_pair=cmd[5:], action_default=2,
                          mgmt_seen=os.path.getsize(mgmt) if mgmt and os.path.exists(mgmt) else 0)
                hci_write(16, struct.pack("<IH", 1, 0x0033) + bytes.fromhex(REMOTE.replace(":", ""))[::-1] + b"\x01\x02")
                say("Attempting to pair with " + cmd[5:])
        elif cmd.startswith("trust "):
            say("Changing %s trust succeeded" % cmd[6:])
        elif cmd.startswith("connect "):
            if st["connected"]:
                say("Connection successful")
            else:
                st["pending_connect"] = cmd[8:]
                say("Attempting to connect to " + cmd[8:])
        elif cmd.startswith("remove "):
            st.update(bonded=False, connected=False, object=st["pairing_mode"], pending_connect=None)
            event("bond removed")
            say("Device has been removed")
        elif cmd == "quit":
            break
save()
