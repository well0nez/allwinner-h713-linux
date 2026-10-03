#!/usr/bin/env python3
"""A bluetoothctl stand-in for the tests: answers the commands h713-remote-pair sends.

Scenario from FAKE_SCENARIO: found (default), none, pairfail, unconnected, empty.
Every received command and the argv are appended to FAKE_LOG when it is set.
The prompt carries bluetoothctl's colour escapes so the cleaner is exercised.
"""
import os
import sys

PROMPT = "\x01\x1b[0;94m\x02[bluetooth]\x01\x1b[0m\x02# "
REMOTE, FOREIGN, CTRL = "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "11:22:33:44:55:66"
scenario = os.environ.get("FAKE_SCENARIO", "found")
log = os.environ.get("FAKE_LOG")
attempts = 0
connected = scenario not in ("unconnected", "connectfail", "flakyconnect", "abortonce")


def note(text):
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def say(*lines):
    for line in lines:
        sys.stdout.write(PROMPT + "\r" + line + "\n")
    sys.stdout.flush()


note("argv " + " ".join(sys.argv[1:]))
if "--agent" not in sys.argv or sys.argv[sys.argv.index("--agent") + 1] != "NoInputNoOutput":
    say("Agent registration failed: no NoInputNoOutput agent asked for")
    sys.exit(9)
say("Agent registered", "[CHG] Controller %s Pairable: yes" % CTRL)
for raw in sys.stdin:
    cmd = raw.strip()
    note("cmd " + cmd)
    if scenario == "nocontroller" and cmd in ("power on", "devices Paired", "show"):
        say("No default controller available")
        continue
    if cmd == "power on":
        say("Changing power on succeeded")
    elif cmd in ("scan on", "scan le"):
        say("Discovery started", "[CHG] Controller %s Discovering: yes" % CTRL)
        if scenario == "speaker_advert":
            say("[NEW] Device %s JVIN Soundbar" % REMOTE)
        elif scenario not in ("none", "speaker"):
            say("[NEW] Device %s Foo Remote" % FOREIGN, "[NEW] Device %s BLE_X_RMC" % REMOTE)
    elif cmd == "scan off":
        say("Discovery stopped")
    elif cmd.startswith("pair "):
        say("Attempting to pair with " + cmd[5:])
        say("Failed to pair: org.bluez.Error.AuthenticationCanceled" if scenario == "pairfail" else "Pairing successful")
    elif cmd.startswith("trust "):
        say("Changing %s trust succeeded" % cmd[6:])
    elif cmd.startswith("connect "):
        say("Attempting to connect to " + cmd[8:])
        attempts += 1
        if scenario == "abortonce" and attempts == 1:
            say("Failed to connect: org.bluez.Error.Failed le-connection-abort-by-local")
            continue
        if scenario in ("connectfail", "flakyconnect", "flakypair"):
            if scenario in ("flakyconnect", "flakypair"):
                say("[CHG] Device %s Connected: yes" % REMOTE)
            say("Failed to connect: org.bluez.Error.AuthenticationFailed")
        else:
            connected = True
            say("Connection successful")
    elif cmd == "devices Paired":
        if scenario == "speaker":
            say("Device %s JVIN Soundbar" % REMOTE)
        elif scenario not in ("none", "empty"):
            say("Device %s BLE_X_RMC" % REMOTE, "Device %s Foo Remote" % FOREIGN)
    elif cmd == "show":
        say("Controller %s (public)" % CTRL, "\tName: h713", "\tPowered: yes")
    elif cmd.startswith("info "):
        if scenario in ("speaker", "speaker_advert"):     # paired, connected, a stock-list word in the name, no HoG
            say("Device %s (public)" % cmd[5:], "\tName: JVIN Soundbar", "\tConnected: yes",
                "\tUUID: Audio Sink                (0000110b-0000-1000-8000-00805f9b34fb)")
        else:
            say("Device %s (public)" % cmd[5:], "\tName: BLE_X_RMC",
                "\tConnected: %s" % ("yes" if connected else "no"),
                "\tUUID: Human Interface Device    (00001812-0000-1000-8000-00805f9b34fb)")
    elif cmd.startswith("remove "):
        say("Device has been removed")
    elif cmd == "quit":
        break
    else:
        say("")     # menu scan, uuids, transport, back: silent like the real one
