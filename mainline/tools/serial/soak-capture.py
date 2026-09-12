#!/usr/bin/env python3
"""Record the H713 console for a long soak and stop when it dies.

    soak-capture.py --out run.log --minutes 60

WHY THIS EXISTS. `console.py --listen N` reads until the console has been
*silent* for N seconds, which is the wrong shape for a soak: a run that prints a
heartbeat every 30 s never satisfies it, so the read only ends N seconds after
the board has already gone quiet -- and "gone quiet" is one of the outcomes we
are trying to time. This reads until a wall-clock deadline instead, and cuts out
early when the kernel says it is dying.

Every line gets a host timestamp *and* a seconds-since-start offset. The kernel
prints its own `[ 1065.175691]` stamps, but those restart at zero on the reboot
that `panic=5` triggers, and half the interesting output (a workload heartbeat,
a shell prompt) has no kernel stamp at all. The offset is what makes "crashed at
T+390 s" readable straight out of the log.

The stop patterns are the ones this board's crashes actually print. After a
match it keeps reading for --grace seconds, because the call trace, the register
dump and the `Rebooting in 5 seconds..` all arrive *after* the first line that
tells you something went wrong.

Exit status is the result, so a shell can branch on it:
    0  deadline reached with nothing matched  -- the run survived
    1  a stop pattern matched                 -- the run crashed
    2  the console went silent past --silence-timeout
"""
import argparse
import os
import re
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h713_tty import resolve_port

UART_FALLBACK = "/dev/ttyUSB0"

# Anything here means the kernel is on its way down. `Internal error` covers the
# Oops variants, `stack-protector` fires before the panic line on a smashed
# stack, and `Unable to handle kernel` catches the paging faults.
STOP_PATTERNS = [
    r"Kernel panic",
    r"Internal error",
    r"Unable to handle kernel",
    r"stack-protector",
    r"Rebooting in \d+ seconds",
]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="auto")
    ap.add_argument("--out", required=True, help="log file (appended to)")
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--grace", type=float, default=20.0,
                    help="keep reading this long after a stop pattern matches")
    ap.add_argument("--silence-timeout", type=float, default=0.0,
                    help="give up if the console says nothing for this long (0 = never)")
    ap.add_argument("--quiet", action="store_true",
                    help="do not echo to stdout; the log file still gets everything")
    args = ap.parse_args()

    stop_re = re.compile("|".join(STOP_PATTERNS))
    fd = open_port(args.port)
    start = time.time()
    deadline = start + args.minutes * 60
    hard_stop = None          # set once a stop pattern matches
    last_byte = start
    status = 0
    pending = b""

    log = open(args.out, "a", buffering=1)
    log.write("=== soak-capture start %s (deadline %.0f min) ===\n"
              % (time.strftime("%Y-%m-%d %H:%M:%S"), args.minutes))

    def emit(line):
        t = time.time()
        stamped = "[%s T+%7.1f] %s" % (time.strftime("%H:%M:%S"), t - start, line)
        log.write(stamped + "\n")
        if not args.quiet:
            sys.stdout.write(stamped + "\n")
            sys.stdout.flush()

    try:
        while True:
            now = time.time()
            if hard_stop is not None:
                if now >= hard_stop:
                    break
            elif now >= deadline:
                break
            if args.silence_timeout and now - last_byte > args.silence_timeout:
                emit("*** console silent for %.0f s -- giving up" % args.silence_timeout)
                status = 2
                break

            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                chunk = b""
            if not chunk:
                time.sleep(0.05)
                continue

            last_byte = now
            pending += chunk
            # Split on either terminator; the console mixes \r\n and bare \n,
            # and mpv's status line is \r-only, which would otherwise buffer
            # forever as one enormous "line".
            parts = re.split(rb"\r\n|\r|\n", pending)
            pending = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", "replace")
                if not line.strip():
                    continue
                emit(line)
                if hard_stop is None and stop_re.search(line):
                    emit("*** stop pattern matched -- capturing %.0f s more" % args.grace)
                    status = 1
                    hard_stop = time.time() + args.grace
    finally:
        if pending.strip():
            emit(pending.decode("utf-8", "replace"))
        elapsed = time.time() - start
        verdict = {0: "SURVIVED", 1: "CRASHED", 2: "SILENT"}[status]
        emit("=== %s after %.0f s (%.1f min) ===" % (verdict, elapsed, elapsed / 60))
        log.close()
        os.close(fd)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
