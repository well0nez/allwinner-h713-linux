#!/usr/bin/env python3
"""Reboot the board and catch it at the U-Boot prompt.

The autoboot delay is a couple of seconds and there is no way to ask for it
after the fact, so this types into the console continuously across the whole
reset rather than trying to time a single keypress.
"""
import os
import sys
import termios
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
SPAM_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
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


def write_slow(fd, data, per_char=0.002):
    for b in data:
        os.write(fd, bytes([b]))
        time.sleep(per_char)


fd = open_port(PORT)
out = b""

write_slow(fd, b"reboot\n")

end = time.time() + SPAM_SECONDS
last_key = 0.0
while time.time() < end:
    try:
        chunk = os.read(fd, 4096)
    except BlockingIOError:
        chunk = b""
    if chunk:
        out += chunk
        sys.stdout.write(chunk.decode("utf-8", "replace"))
        sys.stdout.flush()
    # A bare space is the safest "any key": it interrupts autoboot, and at a
    # prompt it is just whitespace on an empty line.
    if time.time() - last_key > 0.05:
        os.write(fd, b" ")
        last_key = time.time()
    time.sleep(0.01)

# Clear whatever spaces are sitting on the current line, then ask who we are.
write_slow(fd, b"\x15\n")
time.sleep(0.5)
deadline = time.time() + 3
while time.time() < deadline:
    try:
        chunk = os.read(fd, 4096)
    except BlockingIOError:
        chunk = b""
    if chunk:
        sys.stdout.write(chunk.decode("utf-8", "replace"))
        sys.stdout.flush()
        deadline = time.time() + 1
    time.sleep(0.05)
os.close(fd)
