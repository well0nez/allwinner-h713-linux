#!/usr/bin/env python3
"""Send one command to the U-Boot console on the H713 ACM tty and print the reply.

Port defaults to 'auto': resolves the board tty by USB vendor ID 1f3a
(survives USB-port and ttyACM-number changes across re-enumeration).
"""
import argparse
import os
import sys
import termios
import time

from h713_tty import resolve_port

def open_port(path):
    path = resolve_port(path)
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def read_avail(fd):
    try:
        return os.read(fd, 65536)
    except BlockingIOError:
        return b""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="")
    ap.add_argument("--port", default="auto")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--no-wait-prompt", action="store_true")
    args = ap.parse_args()

    fd = open_port(args.port)
    time.sleep(0.2)
    stale = b""
    while True:
        b = read_avail(fd)
        if not b:
            break
        stale += b
        time.sleep(0.05)
    if stale:
        sys.stderr.write("[stale] %s\n" % stale.decode("utf-8", "replace"))

    os.write(fd, args.cmd.encode() + b"\n")

    out = b""
    deadline = time.time() + args.timeout
    last_data = time.time()
    while time.time() < deadline:
        b = read_avail(fd)
        if b:
            out += b
            last_data = time.time()
            if not args.no_wait_prompt and out.rstrip(b" ").endswith(b"\n=>"):
                time.sleep(0.15); out += read_avail(fd); break
            if not args.no_wait_prompt and out.endswith(b"=> "):
                break
        else:
            if args.no_wait_prompt and out and time.time() - last_data > 1.0:
                break
            time.sleep(0.02)
    os.close(fd)
    sys.stdout.write(out.decode("utf-8", "replace"))
    if not out:
        sys.stderr.write("[no response]\n"); sys.exit(2)

if __name__ == "__main__":
    main()
