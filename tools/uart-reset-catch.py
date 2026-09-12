#!/usr/bin/env python3
"""
uart-reset-catch.py -- am U-Boot-Prompt `reset` (oder einen anderen Befehl) absetzen,
den Autoboot des Neustarts sofort mit Strg-C abfangen und danach Befehle ausfuehren.
Fuer Messungen, die ueber einen Reset hinweg gehen (RTC-GP-Register, Plan 103 M3/M6).
  ./uart-reset-catch.py                          reset, fangen, GP5 lesen
  ./uart-reset-catch.py -r 'reset' -c 'md.l 0x07090114 1' -c 'md.l 0x07090100 8'
  ./uart-reset-catch.py -r ''  ...               nichts senden, nur fangen (z. B. bei reboot aus Linux)
Eine laufende tio-Sitzung vorher beenden.
"""
import argparse, os, select, sys, termios, time

PORT_BYID = "/dev/serial/by-id/usb-Espressif_Systems_ESP32S2_DEV_0-if00"
PORT_FALLBACK = "/dev/ttyACM0"
PROMPT = b"=> "


def open_port(path, baud):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attr = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attr
    speed = getattr(termios, "B%d" % baud)
    cflag = (cflag & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB
                       | termios.CRTSCTS)) | termios.CS8 | termios.CLOCAL | termios.CREAD
    iflag &= ~(termios.IXON | termios.IXOFF | termios.IXANY | termios.ICRNL
               | termios.INLCR | termios.IGNCR | termios.ISTRIP | termios.BRKINT)
    oflag &= ~termios.OPOST
    lflag &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, speed, speed, cc])
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def read_avail(fd, wait):
    r, _, _ = select.select([fd], [], [], wait)
    if not r:
        return b""
    try:
        return os.read(fd, 4096)
    except BlockingIOError:
        return b""


def read_until(fd, needle, timeout, idle=0.4):
    buf = b""
    deadline = time.monotonic() + timeout
    last = time.monotonic()
    while time.monotonic() < deadline:
        chunk = read_avail(fd, 0.05)
        if chunk:
            buf += chunk
            last = time.monotonic()
            if needle in buf and time.monotonic() - last > -1:
                # kurz nachlesen, damit der Rest der Zeile mitkommt
                time.sleep(idle)
                buf += read_avail(fd, 0.05)
                return buf, True
    return buf, False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-r", "--reset-cmd", default="reset", help="Befehl, der den Neustart ausloest ('' = keiner)")
    ap.add_argument("-c", "--cmd", action="append", default=["md.l 0x07090114 1"])
    ap.add_argument("-t", "--timeout", type=float, default=60.0, help="maximal so lange auf den neuen Prompt warten")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    port = a.port or (PORT_BYID if os.path.exists(PORT_BYID) else PORT_FALLBACK)
    fd = open_port(port, a.baud)
    log = []
    if a.reset_cmd:
        os.write(fd, (a.reset_cmd + "\r").encode())
        log.append("=> " + a.reset_cmd)
        time.sleep(0.3)
    # Autoboot abfangen: Strg-C haemmern, bis nach einem Banner wieder der Prompt steht.
    t0 = time.monotonic()
    buf = b""
    banner = False
    caught = False
    while time.monotonic() - t0 < a.timeout:
        os.write(fd, b"\x03")
        buf += read_avail(fd, 0.1)
        if b"U-Boot" in buf or b"Hit any key" in buf:
            banner = True
        if banner and buf.endswith(PROMPT):
            caught = True
            break
    dt = time.monotonic() - t0
    text = buf.decode("utf-8", "replace")
    lines = [l for l in text.splitlines() if l.strip() and "<INTERRUPT>" not in l]
    log.append("[Neustart: Banner %s, Prompt %s nach %.1f s]" % (banner, "gefangen" if caught else "NICHT gefangen", dt))
    log.extend("  | " + l for l in lines[-12:])
    if caught:
        for cmd in a.cmd:
            termios.tcflush(fd, termios.TCIFLUSH)
            os.write(fd, (cmd + "\r").encode())
            out, ok = read_until(fd, PROMPT, 6.0)
            body = out.decode("utf-8", "replace")
            log.append("=> " + cmd)
            log.extend(l for l in body.splitlines()[1:] if l.strip() and l.strip() != "=>")
    os.close(fd)
    result = "\n".join(log)
    print(result)
    if a.out:
        with open(a.out, "w") as f:
            f.write(result + "\n")
        with open(a.out + ".raw", "w") as f:
            f.write(text)
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
