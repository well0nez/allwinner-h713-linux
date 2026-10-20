#!/usr/bin/env python3
"""A bluetoothctl stand-in for the tests: answers the commands h713-remote-pair sends.

Scenario from FAKE_SCENARIO: found (default), none, pairfail, unconnected, empty, stale (a bond the remote
has lost: a connect gives a link that drops right after, until the bond is removed and paired afresh),
stalesilent (the same, but a connect gets no answer at all). As on the HY300PRO-G-EU (20.10.2026), the
kernel's last connect to the stale remote outlives its removal and makes bluez' object again: after a
remove the scan shows the remote only as "[CHG] ... RSSI", never "[NEW]". leftover: no bond, but bluez still
keeps an unpaired object of the remote (seen in pairing mode within its temporary timeout), so a scan
shows it only as "[CHG]" as well.
Every received command and the argv are appended to FAKE_LOG when it is set. In "stale" a connect also
writes the hex frames of FAKE_HCI_FRAMES to the file or FIFO FAKE_HCI, as the remote's adverts would reach
the HCI monitor while it asks to be paired. The prompt carries bluetoothctl's colour escapes so the
cleaner is exercised. Bonds follow pair and remove; info shows the AdvertisingFlags bluez keeps from the
last pairing (05), as the real one does.
"""
import os
import sys

PROMPT = "\x01\x1b[0;94m\x02[bluetooth]\x01\x1b[0m\x02# "
REMOTE, FOREIGN, CTRL = "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "11:22:33:44:55:66"
scenario = os.environ.get("FAKE_SCENARIO", "found")
log = os.environ.get("FAKE_LOG")
attempts = 0
connected = scenario not in ("unconnected", "connectfail", "flakyconnect", "abortonce", "stale", "stalesilent")
bonded = scenario not in ("none", "empty", "leftover")
stale = scenario in ("stale", "stalesilent")
brief = False       # a stale link: info sees it connected once, then it is gone
raced = scenario == "leftover"      # the remote's unpaired object outlived its removal or its last scan


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
        elif raced:
            say("[NEW] Device %s Foo Remote" % FOREIGN, "[CHG] Device %s RSSI: 0xffffffc1 (-63)" % REMOTE)
        elif scenario not in ("none", "speaker"):
            say("[NEW] Device %s Foo Remote" % FOREIGN, "[NEW] Device %s BLE_X_RMC" % REMOTE)
    elif cmd == "scan off":
        say("Discovery stopped")
    elif cmd.startswith("pair "):
        say("Attempting to pair with " + cmd[5:])
        if scenario == "pairfail":
            say("Failed to pair: org.bluez.Error.AuthenticationCanceled")
        else:
            bonded = bonded or cmd[5:] == REMOTE
            say("Pairing successful")
    elif cmd.startswith("trust "):
        say("Changing %s trust succeeded" % cmd[6:])
    elif cmd.startswith("connect "):
        say("Attempting to connect to " + cmd[8:])
        attempts += 1
        if stale:
            hci = os.environ.get("FAKE_HCI")
            try:            # a FIFO nobody reads (a tool without the monitor) gets nothing
                fd = os.open(hci, os.O_WRONLY | os.O_APPEND | os.O_NONBLOCK) if hci else None
            except OSError:
                fd = None
            if fd is not None:
                os.write(fd, bytes.fromhex(os.environ.get("FAKE_HCI_FRAMES", "")))
                os.close(fd)
            if scenario == "stalesilent":
                continue
            connected = brief = True
            say("[CHG] Device %s Connected: yes" % REMOTE, "Connection successful")
            continue
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
    elif cmd == "devices":
        if bonded or raced:
            say("Device %s BLE_X_RMC" % REMOTE)
        if scenario not in ("none", "empty", "leftover", "speaker", "speaker_advert"):
            say("Device %s Foo Remote" % FOREIGN)
    elif cmd == "devices Paired":
        if scenario == "speaker":
            say("Device %s JVIN Soundbar" % REMOTE)
        elif bonded:
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
                "\tUUID: Human Interface Device    (00001812-0000-1000-8000-00805f9b34fb)",
                "\tAdvertisingFlags:", "  05                                               .               ")
            if brief:
                connected = brief = False
    elif cmd.startswith("remove "):
        if cmd[7:] == REMOTE:
            raced = stale or scenario == "leftover"
            bonded = connected = stale = False
        say("Device has been removed")
    elif cmd == "quit":
        break
    else:
        say("")     # menu scan, uuids, transport, back: silent like the real one
