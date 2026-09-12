#!/usr/bin/env python3
"""
uart-capture.py — Befehle auf der U-Boot-Konsole ausfuehren und mitschneiden.

Spricht den ESP32-S2-UART-Proxy direkt an (kein pyserial noetig). Schickt jeden
Befehl, wartet auf den Prompt und schreibt alles in eine Datei.

  ./uart-capture.py                      Standardsatz: Display-Register
  ./uart-capture.py -c 'md.l 0x058c0000 12' -c bdinfo
  ./uart-capture.py -f befehle.txt -o /tmp/stock.txt

Wichtig: eine laufende tio-Sitzung auf demselben Port vorher beenden
(Strg-t q), sonst greifen beide auf dieselbe Leitung zu.
"""
import argparse, os, select, sys, termios, time

PORT_BYID = "/dev/serial/by-id/usb-Espressif_Systems_ESP32S2_DEV_0-if00"
PORT_FALLBACK = "/dev/ttyACM0"
PROMPT = b"=> "

# Die Bloecke, die h713_disp dump ausgibt -- Reihenfolge nach Aussagekraft.
DEFAULT_CMDS = [
    "md.l 0x058c0000 12",   # disp-pll: PLL-N und Spread Spectrum
    "md.l 0x02001050 4",    # pll-video2
    "md.l 0x02001db0 8",    # disp-modclk
    "md.l 0x05880000 16",   # lvds / TCON-Timing
    "md.l 0x0524c000 28",   # de
    "md.l 0x0525c000 16",   # mixer
    "md.l 0x05600140 16",   # afbd
    "md.l 0x05600040 16",   # afbd-global
    "md.l 0x05600000 4",    # afbd-top
    "md.l 0x05600300 16",   # afbd-mux
    "md.l 0x051c0000 8",    # lvds-phy
    "md.l 0x051c0020 36",   # lvds-phy-mid
    "md.l 0x051c00b0 16",   # lvds-phy2
    "md.l 0x05200000 16",   # vblender
    "md.l 0x05280080 8",    # de-layers
    "md.l 0x05240000 8",    # de-top
    "md.l 0x05248000 8",    # osd-ch0
    "md.l 0x05700000 8",    # tvtop
    "md.l 0x05140050 4",    # display-route
    "md.l 0x05800000 12",   # lvds-lane
]


def open_port(path, baud):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attr = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attr
    speed = getattr(termios, "B%d" % baud)
    # 8N1, raw, kein Flusssteuerung, lokaler Empfang an
    cflag = (cflag & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB
                       | termios.CRTSCTS)) | termios.CS8 | termios.CLOCAL | termios.CREAD
    iflag &= ~(termios.IXON | termios.IXOFF | termios.IXANY | termios.ICRNL
               | termios.INLCR | termios.IGNCR | termios.ISTRIP | termios.BRKINT)
    oflag &= ~termios.OPOST
    lflag &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
    cc = list(cc)
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, speed, speed, cc])
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def read_until(fd, needle, timeout, idle=0.4):
    """Bis needle oder bis timeout; bricht auch ab, wenn idle Sekunden nichts kommt."""
    buf = b""
    deadline = time.monotonic() + timeout
    last = time.monotonic()
    while time.monotonic() < deadline:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                # select() kann bereit melden, ohne dass Bytes anliegen.
                continue
            if chunk:
                buf += chunk
                last = time.monotonic()
                if buf.rstrip().endswith(needle.strip()):
                    return buf, True
        elif buf and time.monotonic() - last > idle:
            return buf, False
    return buf, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-c", "--cmd", action="append", default=[])
    ap.add_argument("-f", "--file")
    ap.add_argument("-o", "--out")
    ap.add_argument("-t", "--timeout", type=float, default=5.0)
    ap.add_argument("-i", "--idle", type=float, default=0.4,
                    help="Sekunden Stille, nach denen ein Befehl als fertig gilt")
    a = ap.parse_args()

    port = a.port or (PORT_BYID if os.path.exists(PORT_BYID) else PORT_FALLBACK)
    if not os.path.exists(port):
        sys.exit("Port %s existiert nicht -- haengt der ESP32 dran?" % port)

    cmds = list(a.cmd)
    if a.file:
        with open(a.file) as fh:
            cmds += [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    if not cmds:
        cmds = DEFAULT_CMDS

    out = a.out or ("/tmp/uart-capture-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
    fd = open_port(port, a.baud)
    print("Port %s @ %d, %d Befehl(e) -> %s\n" % (port, a.baud, len(cmds), out))

    # Prompt holen: ein Enter, dann schauen was zurueckkommt.
    os.write(fd, b"\r")
    pre, ok = read_until(fd, PROMPT, 2.0)
    if not ok:
        print("WARNUNG: kein '=> '-Prompt gesehen. Gelesen: %r" % pre[-120:])
        print("         Laeuft noch eine tio-Sitzung auf dem Port?\n")

    log = ["# uart-capture %s  port=%s baud=%d" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), port, a.baud), ""]
    fails = 0
    for cmd in cmds:
        os.write(fd, cmd.encode() + b"\r")
        raw, ok = read_until(fd, PROMPT, a.timeout, a.idle)
        text = raw.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
        lines = [l for l in text.split("\n")]
        # Echo des Befehls und die Prompt-Zeile wegwerfen
        if lines and cmd in lines[0]:
            lines = lines[1:]
        body = "\n".join(l for l in lines if l.strip() and l.strip() != "=>").rstrip()
        status = "" if ok else "   [TIMEOUT]"
        print("=> %s%s" % (cmd, status))
        if body:
            print(body)
        print()
        log += ["=> %s%s" % (cmd, status), body, ""]
        if not ok:
            fails += 1

    os.close(fd)
    with open(out, "w") as fh:
        fh.write("\n".join(log) + "\n")
    print("Geschrieben: %s%s" % (out, "  (%d Timeout(s))" % fails if fails else ""))


if __name__ == "__main__":
    main()
