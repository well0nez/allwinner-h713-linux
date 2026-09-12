#!/usr/bin/env python3
"""
uart-watch.py -- einen Startvorgang passiv mitschneiden, ohne einzugreifen.

  ./uart-watch.py                      bis zum Linux-Prompt, dann fertig
  ./uart-watch.py -o /tmp/boot.log     Mitschnitt sichern
  ./uart-watch.py -t 600               laenger warten

Greift nicht ein: kein Strg-C, kein Enter. Fuer den Fall, dass bootcmd
normal durchlaufen soll. Zum Abfangen des U-Boot-Prompts stattdessen
`uart-uboot.py catch`.

WICHTIG: nur EIN Leser pro Leitung. Laeuft daneben noch ein Mitschnitt oder
eine tio-Sitzung, teilen sich beide die Bytes und jede Messung ist wertlos --
in der Nacht 01./02.09. einmal passiert, mit falscher Schlussfolgerung.
Das Skript prueft das selbst und bricht ab.
"""
import argparse, os, select, subprocess, sys, time
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
uc = SourceFileLoader("uc", os.path.join(HERE, "uart-capture.py")).load_module()

COLD = (b"U-Boot SPL", b"DRAM:", b"Hit any key", b"eGON")
DONE = (b"login:", b"root@h713")


def other_readers(port):
    """Wer haelt die Leitung sonst noch? Leere Liste = frei."""
    try:
        out = subprocess.run(["fuser", os.path.realpath(port)],
                             capture_output=True, text=True, timeout=5)
        return [p for p in out.stdout.split() if p.isdigit()
                and int(p) != os.getpid()]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-o", "--out")
    ap.add_argument("-t", "--timeout", type=float, default=420.0)
    a = ap.parse_args()

    port = a.port or (uc.PORT_BYID if os.path.exists(uc.PORT_BYID)
                      else uc.PORT_FALLBACK)
    if not os.path.exists(port):
        sys.exit("Port %s existiert nicht -- haengt der ESP32 dran?" % port)

    busy = other_readers(port)
    if busy:
        sys.exit("Port %s wird schon gelesen (PID %s). Erst beenden, sonst "
                 "teilen sich beide die Bytes." % (port, ", ".join(busy)))

    fd = uc.open_port(port, a.baud)
    print("Hoere mit auf %s -- jetzt Strom ziehen und wieder anstecken." % port)
    sys.stdout.flush()

    acc, saw_cold = b"", False
    deadline = time.monotonic() + a.timeout
    while time.monotonic() < deadline:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                acc += os.read(fd, 8192)
            except BlockingIOError:
                pass
        if not saw_cold and any(k in acc for k in COLD):
            saw_cold = True
            print("Kaltstart gesehen, Boot laeuft ...", flush=True)
        if saw_cold and any(k in acc for k in DONE):
            print("Linux ist oben.", flush=True)
            break
    else:
        print("Zeit abgelaufen (%s Kaltstart gesehen)."
              % ("kein" if not saw_cold else "aber"))

    os.close(fd)
    if a.out:
        with open(a.out, "wb") as fh:
            fh.write(acc)
        print("Mitschnitt: %s (%d Byte)" % (a.out, len(acc)))
    return 0 if saw_cold else 1


if __name__ == "__main__":
    sys.exit(main())
