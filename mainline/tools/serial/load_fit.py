#!/usr/bin/env python3
"""Combined U-Boot `loady` + YMODEM-1K send over one held-open tty.

Opens the port once, issues `loady <addr>`, waits for the receiver's 'C',
then streams the file — no close/reopen race. For large FITs over serial.

Usage: load_fit.py FILE [--port auto|/dev/ttyUSB0] [--addr 0x50000000]
"""
import argparse
import os
import sys
import termios
import time

from h713_tty import resolve_port

SOH, STX, EOT, ACK, NAK, CAN, CRCC = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43

def open_port(path):
    fd = os.open(resolve_port(path), os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xffff if crc & 0x8000 else (crc << 1) & 0xffff
    return crc

def getb(fd, timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = os.read(fd, 1)
        except BlockingIOError:
            b = b""
        if b:
            return b[0]
        time.sleep(0.003)
    return None

def wait_for(fd, wanted, timeout, label):
    end = time.time() + timeout
    seen = []
    while time.time() < end:
        c = getb(fd, end - time.time())
        if c is None:
            break
        seen.append(c)
        if c in wanted:
            return c
    raise SystemExit("timeout waiting for %s (saw %r)" % (label, bytes(seen[-32:])))

def send_block(fd, blknum, payload):
    hdr = STX if len(payload) == 1024 else SOH
    frame = bytes([hdr, blknum & 0xff, 0xff - (blknum & 0xff)]) + payload
    c = crc16(payload)
    frame += bytes([c >> 8, c & 0xff])
    for _ in range(12):
        os.write(fd, frame)
        r = wait_for(fd, (ACK, NAK, CAN, CRCC), 15, "ACK blk %d" % blknum)
        if r == ACK:
            return
        if r == CAN:
            raise SystemExit("cancelled at blk %d" % blknum)
    raise SystemExit("too many retries at blk %d" % blknum)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--port", default="auto")
    ap.add_argument("--addr", default="0x50000000")
    args = ap.parse_args()

    data = open(args.file, "rb").read()
    name = os.path.basename(args.file).encode()
    fd = open_port(args.port)

    # drain
    time.sleep(0.2)
    while True:
        try:
            if not os.read(fd, 4096):
                break
        except BlockingIOError:
            break

    os.write(fd, ("loady %s\n" % args.addr).encode())
    sys.stderr.write("issued loady %s\n" % args.addr)

    # ymodem header block
    hdr = name + b"\0" + str(len(data)).encode() + b"\0"
    hdr += b"\0" * ((128 if len(hdr) <= 128 else 1024) - len(hdr))

    wait_for(fd, (CRCC,), 30, "initial 'C'")
    send_block(fd, 0, hdr)
    wait_for(fd, (CRCC,), 30, "'C' before data")

    nblocks = (len(data) + 1023) // 1024
    t0 = time.time()
    for i in range(nblocks):
        chunk = data[i * 1024:(i + 1) * 1024]
        if len(chunk) < 1024:
            chunk += b"\x1a" * (1024 - len(chunk))
        send_block(fd, i + 1, chunk)
        if (i + 1) % 200 == 0 or i + 1 == nblocks:
            sys.stderr.write("\r%d/%d blocks (%.1f KB/s)" %
                             (i + 1, nblocks, (i + 1) / max(time.time() - t0, 0.01)))
            sys.stderr.flush()
    sys.stderr.write("\n")

    os.write(fd, bytes([EOT]))
    r = wait_for(fd, (ACK, NAK), 15, "EOT ack")
    if r == NAK:
        os.write(fd, bytes([EOT]))
        wait_for(fd, (ACK,), 15, "EOT ack 2")
    wait_for(fd, (CRCC,), 15, "'C' after EOT")
    send_block(fd, 0, b"\0" * 128)

    time.sleep(0.6)
    out = b""
    end = time.time() + 3
    while time.time() < end:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        if b:
            out += b; end = time.time() + 1
        else:
            time.sleep(0.05)
    os.close(fd)
    sys.stdout.write(out.decode("utf-8", "replace"))

if __name__ == "__main__":
    main()
