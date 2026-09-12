#!/usr/bin/env python3
"""
uart-send.py — eine Datei per YMODEM an U-Boots `loady` schicken.

  # in U-Boot:  loady 0x50000000
  ./uart-send.py 0x50000000 build/flash-netboot/uboot-proper.bin

Setzt den loady-Befehl selbst ab, ueberträgt und wartet auf den Prompt.
Eine laufende tio-Sitzung vorher beenden.
"""
import argparse, os, select, sys, termios, time

SOH, STX, EOT, ACK, NAK, CAN = b"\x01", b"\x02", b"\x04", b"\x06", b"\x15", b"\x18"
CRC = b"C"

def crc16(data):
    c = 0
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xffff if c & 0x8000 else (c << 1) & 0xffff
    return c

def open_port(path, baud):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[2] = (a[2] & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB
                     | termios.CRTSCTS)) | termios.CS8 | termios.CLOCAL | termios.CREAD
    a[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY | termios.ICRNL
              | termios.INLCR | termios.IGNCR | termios.ISTRIP | termios.BRKINT)
    a[1] &= ~termios.OPOST
    a[3] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
    a[4] = a[5] = getattr(termios, "B%d" % baud)
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd

def rd(fd, n=1, timeout=10.0):
    end = time.monotonic() + timeout
    out = b""
    while len(out) < n and time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                c = os.read(fd, n - len(out))
            except BlockingIOError:
                continue
            out += c
    return out

def wr(fd, data):
    while data:
        try:
            data = data[os.write(fd, data):]
        except BlockingIOError:
            time.sleep(0.001)

BLK = 128

def block(seq, payload, pad=b"\x1a"):
    """128-Byte-Block mit CRC. U-Boots loady nimmt keine 1K-Bloecke (STX)."""
    head, size = SOH, BLK
    payload = payload.ljust(size, pad)
    body = bytes([seq & 0xff, 0xff - (seq & 0xff)]) + payload
    c = crc16(payload)
    return head + body + bytes([c >> 8, c & 0xff])

LAST = []

def send_block(fd, blk, tries=8):
    for _ in range(tries):
        wr(fd, blk)
        a = rd(fd, 1, 5.0)
        LAST.append(a)
        if a == ACK:
            return True
        if a == CAN:
            return False
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addr")
    ap.add_argument("file")
    ap.add_argument("-p", "--port", default="/dev/ttyACM0")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("--no-cmd", action="store_true",
                    help="loady nicht selbst absetzen, es laeuft schon")
    a = ap.parse_args()

    data = open(a.file, "rb").read()
    name = os.path.basename(a.file)
    fd = open_port(a.port, a.baud)

    if not a.no_cmd:
        wr(fd, b"\r")
        rd(fd, 4096, 1.0)
        wr(fd, ("loady %s\r" % a.addr).encode())

    # Auf das 'C' des Empfaengers warten
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if CRC in rd(fd, 1, 0.5):
            break
    else:
        sys.exit("kein 'C' von loady -- laeuft der Befehl?")

    hdr = (name.encode() + b"\x00" + str(len(data)).encode() + b"\x00")
    if not send_block(fd, block(0, hdr)):
        sys.exit("Kopfblock abgelehnt")
    while CRC not in rd(fd, 1, 0.5):
        pass

    t0 = time.monotonic()
    seq, off = 1, 0
    while off < len(data):
        chunk = data[off:off + BLK]
        if not send_block(fd, block(seq, chunk)):
            sys.exit("Block %d abgelehnt bei Offset %d; Antworten: %r" % (seq, off, LAST[-8:]))
        off += len(chunk); seq += 1
        if seq % 256 == 0:
            el = time.monotonic() - t0
            sys.stderr.write("\r  %6.1f%%  %5.1f KB/s" %
                             (100.0 * off / len(data), off / 1024 / el))
            sys.stderr.flush()

    # EOT: erst NAK, dann ACK. U-Boots loady endet danach -- der
    # YMODEM-Batch-Abschlussblock wuerde als Muell gelten ("aborted").
    wr(fd, EOT)
    if rd(fd, 1, 3.0) == NAK:
        wr(fd, EOT)
    rd(fd, 1, 3.0)
    # Batch-Abschluss: Block 0 aus lauter Nullbytes, nicht mit 0x1a gefuellt.
    while CRC not in rd(fd, 1, 0.5):
        pass
    send_block(fd, block(0, b"", b"\x00"), tries=3)

    el = time.monotonic() - t0
    sys.stderr.write("\r  %d Bytes in %.1f s  =  %.1f KB/s          \n"
                     % (len(data), el, len(data) / 1024 / el))
    tail = rd(fd, 4096, 3.0).decode("utf-8", "replace")
    for line in tail.splitlines():
        if line.strip():
            print("  " + line.strip())
    os.close(fd)

if __name__ == "__main__":
    main()
