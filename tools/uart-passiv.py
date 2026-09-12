#!/usr/bin/env python3
"""
uart-passiv.py DATEI [SEK] [--bis MUSTER] -- die UART-Konsole nur mitlesen, nichts senden,
fortlaufend (zeilenweise geflusht) in DATEI schreiben. Endet nach SEK Sekunden (Standard 900)
oder wenn MUSTER im Strom auftaucht (dann noch 5 s nachlesen).
  ./uart-passiv.py /tmp/kaltstart.txt 600 --bis "Starting kernel"
Eine laufende tio-Sitzung vorher beenden. Kein Ctrl-C, kein reset -- dafuer uart-reset-catch.py.
"""
import os, sys, time, importlib.util

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("urc", os.path.join(here, "uart-reset-catch.py"))
urc = importlib.util.module_from_spec(spec); spec.loader.exec_module(urc)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    out = sys.argv[1]; sek = 900.0; bis = None
    rest = sys.argv[2:]
    if rest and not rest[0].startswith("--"):
        sek = float(rest.pop(0))
    if rest[:1] == ["--bis"] and len(rest) >= 2:
        bis = rest[1].encode()
    port = urc.PORT_BYID if os.path.exists(urc.PORT_BYID) else urc.PORT_FALLBACK
    fd = urc.open_port(port, 115200)
    t0 = time.monotonic(); seen = None; tail = b""
    with open(out, "ab", buffering=0) as f:
        while time.monotonic() - t0 < sek:
            c = urc.read_avail(fd, 0.2)
            if c:
                f.write(c)
                tail = (tail + c)[-4096:]
                if bis and seen is None and bis in tail:
                    seen = time.monotonic()
            if seen and time.monotonic() - seen > 5:
                break
    os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
