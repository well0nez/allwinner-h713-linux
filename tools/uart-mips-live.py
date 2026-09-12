#!/usr/bin/env python3
"""
uart-mips-live.py -- beim Kaltstart einbrechen und bootcmd auf "h713_disp init" setzen,
d.h. den MIPS laufen lassen statt ihn zu parken.

Hammert Strg-C, bis der '=> '-Prompt kommt, setzt dann bootargs samt
clk_ignore_unused / pd_ignore_unused / cma=128M, speichert und startet.

Aufrufen, DANN Strom ziehen und wieder anstecken.
"""
import os, select, sys, time
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
m = SourceFileLoader('uc', os.path.join(HERE, 'uart-capture.py')).load_module()

# h713_disp init statt auto: laesst den MIPS LAUFEN (kein quiesce). Das Panel
# bleibt dabei schwarz -- dieser Pfad veroeffentlicht keinen Inhalt --, aber die
# Video-Pipeline und die AFBD-Page-Flip-Engine sind dann aktiv, was fuer den
# NV12-Scanout Voraussetzung ist. Siehe doku/62-video.md.
# Optionales erstes Argument: Elog-Level 0..5 (0 assert .. 5 verbose).
# Ohne Argument bleibt das Log aus, wie bisher.
_LVL = sys.argv[1] if len(sys.argv) > 1 else None
_ELOG = (" elog=%s" % _LVL) if _LVL else ""
BOOTCMD = ("h713_disp init 0x30%s; dhcp; "
           "tftpboot 0x60000000 192.168.8.104:${bootfile}; "
           "bootm 0x60000000" % _ELOG)

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

for cmd in ["setenv bootcmd '%s'" % BOOTCMD, "printenv bootcmd", "saveenv"]:
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
with open("/opt/Projekte/h713/re/captures/boot-mips-live.log", "w") as fh:
    fh.write("".join(log))
print("\n\nMitschnitt: re/captures/boot-mips-live.log")
