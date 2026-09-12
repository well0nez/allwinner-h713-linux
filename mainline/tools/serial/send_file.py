#!/usr/bin/env python3
"""Copy a file to the target's filesystem over the Linux serial console.

The console is a canonical-mode tty, so a single input line is capped at
~4 KB by the line discipline. Anything larger must be chunked or it is
silently truncated -- which looks like a corrupt file, not a transfer error.

Sends base64 in bounded chunks, appending each, then decodes on the target and
verifies by md5. Slow (~11 KB/s) but needs no USB gadget, which matters because
the gadget only enumerates when Linux has not run since power-on.

usage: send_file.py LOCAL REMOTE [--port /dev/ttyUSB0] [--chunk 1500]
"""
import argparse
import base64
import hashlib
import os
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def run(port, cmd, timeout=20.0):
    """Send one shell line, return everything read back."""
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    while True:                                   # drain
        try:
            if not os.read(fd, 65536):
                break
        except BlockingIOError:
            break
    os.write(fd, cmd.encode() + b"\n")
    out = b""
    end = time.time() + timeout
    last = time.time()
    while time.time() < end:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        if b:
            out += b
            last = time.time()
            if out.rstrip().endswith(b"#"):
                break
        else:
            if out and time.time() - last > 1.5:
                break
            time.sleep(0.02)
    os.close(fd)
    return out.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("local")
    ap.add_argument("remote")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--chunk", type=int, default=1500)
    args = ap.parse_args()

    data = open(args.local, "rb").read()
    want = hashlib.md5(data).hexdigest()
    b64 = base64.b64encode(data).decode()
    chunks = [b64[i:i + args.chunk] for i in range(0, len(b64), args.chunk)]

    print("%s -> %s: %d bytes, md5 %s, %d chunks"
          % (args.local, args.remote, len(data), want, len(chunks)))

    tmp = args.remote + ".b64"
    run(args.port, ": > %s" % tmp)
    for n, c in enumerate(chunks, 1):
        run(args.port, "printf '%%s' '%s' >> %s" % (c, tmp))
        sys.stdout.write("\r  chunk %d/%d" % (n, len(chunks)))
        sys.stdout.flush()
    print()

    run(args.port, "base64 -d %s > %s && rm -f %s" % (tmp, args.remote, tmp))
    out = run(args.port, "md5sum %s" % args.remote)
    got = ""
    for tok in out.split():
        if len(tok) == 32 and all(ch in "0123456789abcdef" for ch in tok):
            got = tok
            break
    if got == want:
        print("OK  md5 %s" % got)
        return 0
    print("FAIL  want %s got %s\n%s" % (want, got or "(none)", out))
    return 1


if __name__ == "__main__":
    sys.exit(main())
