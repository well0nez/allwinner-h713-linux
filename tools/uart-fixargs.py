#!/usr/bin/env python3
"""
uart-fixargs.py -- beim Kaltstart in U-Boot einbrechen und die bootargs setzen.

Hammert Strg-C, bis der '=> '-Prompt kommt, setzt dann bootargs samt
clk_ignore_unused / pd_ignore_unused / cma=128M, speichert und startet.

Aufrufen, DANN Strom ziehen und wieder anstecken.
"""
import os, select, sys, time
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
m = SourceFileLoader('uc', os.path.join(HERE, 'uart-capture.py')).load_module()

BOOTARGS = ("console=ttyS0,115200 earlycon root=/dev/nfs rw "
            "nfsroot=192.168.8.104:/srv/h713-rootfs,vers=3,tcp ip=dhcp rootwait "
            "clk_ignore_unused pd_ignore_unused cma=128M")

port = m.PORT_BYID if os.path.exists(m.PORT_BYID) else m.PORT_FALLBACK
fd = m.open_port(port, 115200)
log = []

def drain(sec):
    buf = b""
    t = time.monotonic()
    while time.monotonic() - t < sec:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                c = os.read(fd, 8192)
            except BlockingIOError:
                continue
            if c:
                buf += c
    return buf

print("Warte auf Kaltstart -- jetzt Strom ziehen und wieder anstecken.")
print("(hammert Strg-C, bricht ab sobald der '=> '-Prompt steht)\n")
sys.stdout.flush()

acc = b""
deadline = time.monotonic() + 300
got = False
while time.monotonic() < deadline:
    os.write(fd, b"\x03")
    acc += drain(0.12)
    if acc.rstrip().endswith(b"=>"):
        got = True
        break

log.append(acc.decode("utf-8", "replace"))
if not got:
    print("KEIN Prompt in 300 s. Roh gelesen (letzte 800 Zeichen):")
    print(log[0][-800:])
    os.close(fd)
    sys.exit(1)

print("U-Boot-Prompt steht.\n")
print(log[0][-1200:])

for cmd in ["setenv bootargs '%s'" % BOOTARGS, "printenv bootargs", "saveenv"]:
    os.write(fd, cmd.encode() + b"\r")
    out = drain(3.0).decode("utf-8", "replace")
    log.append(out)
    print(out)
    sys.stdout.flush()

print("\n=== run bootcmd ===")
os.write(fd, b"run bootcmd\r")
t = time.monotonic()
while time.monotonic() - t < 150:
    out = drain(2.0).decode("utf-8", "replace")
    if out:
        log.append(out)
        sys.stdout.write(out)
        sys.stdout.flush()

os.close(fd)
with open("/opt/Projekte/h713/re/captures/boot-clkignore.log", "w") as fh:
    fh.write("".join(log))
print("\n\nMitschnitt: re/captures/boot-clkignore.log")
