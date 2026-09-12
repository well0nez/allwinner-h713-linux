#!/usr/bin/env python3
"""Run commands on the H713 console over serial and print what comes back.

Works at the U-Boot prompt and at the Linux shell alike -- it just types and
reads, so it does not care which is on the other end.

    console.py 'version' 'fatls mmc 1:2'          # U-Boot
    console.py --wait 8 'dmesg | tail -5'          # Linux
    console.py --listen 30                         # watch a boot go by

WHY THE WRITES ARE PACED, which is the whole reason this file exists: a long
command line written in one burst comes back with doubled characters --
"ddrivers", "afbbd", "kerneel". That is not a display artifact. The shell
receives the corrupted line and runs it, so a `cp` silently targets a directory
that does not exist and an `&&` chain stops there with no error you will notice.
Writing one character at a time removes it entirely. 2 ms per character is
imperceptible next to a 115200-baud console, and this class of bug costs an hour
to find because every symptom points somewhere else.

Raw termios rather than pyserial, matching the other tools here, so this has no
dependencies beyond the standard library.
"""
import argparse
import os
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h713_tty import resolve_port

# The UART console is a separate USB-serial adapter (CP210x and friends), not
# the board's own CDC ACM gadget, so h713_tty's VID-based lookup does not find
# it -- and the gadget is absent entirely whenever Linux has run since power-on.
# Prefer the explicit --port, try the gadget, then fall back to the UART.
UART_FALLBACK = "/dev/ttyUSB0"


def find_port(path):
    if path != "auto":
        return path
    try:
        return resolve_port("auto")
    except SystemExit:
        if os.path.exists(UART_FALLBACK):
            return UART_FALLBACK
        raise


def open_port(path):
    fd = os.open(find_port(path), os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0
    a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200
    a[5] = termios.B115200
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


def drain(fd, quiet_for, echo=True):
    """Read until the console has been silent for `quiet_for` seconds."""
    out = b""
    end = time.time() + quiet_for
    while time.time() < end:
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            chunk = b""
        if chunk:
            out += chunk
            if echo:
                sys.stdout.write(chunk.decode("utf-8", "replace"))
                sys.stdout.flush()
            end = time.time() + quiet_for   # still talking; keep listening
        else:
            time.sleep(0.05)
    return out


def write_slow(fd, data, per_char=0.002):
    for b in data:
        os.write(fd, bytes([b]))
        time.sleep(per_char)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="auto")
    ap.add_argument("--wait", type=float, default=2.0,
                    help="seconds of silence that ends a read (raise for slow commands)")
    ap.add_argument("--listen", type=float, default=0.0,
                    help="just read for N seconds and exit; IGNORES any commands")
    ap.add_argument("--per-char", type=float, default=0.002)
    ap.add_argument("cmds", nargs="*")
    args = ap.parse_args()

    # --listen is a pure read mode, so combining it with commands silently does
    # nothing at all -- the commands are never typed and the board just sits
    # there. That looked exactly like "the board ignored `reboot`" and cost two
    # debugging cycles. To type something and then watch, use --wait instead:
    #   console.py --wait 30 'reboot'
    if args.listen and args.cmds:
        sys.stderr.write(
            "error: --listen only reads; it would discard %d command(s).\n"
            "       To send a command and then watch, use --wait N instead.\n"
            % len(args.cmds))
        return 2

    fd = open_port(args.port)
    try:
        if args.listen:
            drain(fd, args.listen)
            return 0
        if not args.cmds:
            # A bare newline is the cheapest "is anything alive out there?"
            write_slow(fd, b"\r")
            drain(fd, args.wait)
            return 0
        for c in args.cmds:
            write_slow(fd, c.encode() + b"\n", args.per_char)
            time.sleep(0.3)
            drain(fd, args.wait)
    finally:
        os.close(fd)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
