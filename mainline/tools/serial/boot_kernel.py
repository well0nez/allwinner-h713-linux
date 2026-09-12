#!/usr/bin/env python3
"""Set BL31-safe placement + bootargs, bootm a FIT, capture console.

Defaults to the Debian root on eMMC p26.  Pass --rdinit for an initramfs-only
smoke FIT: booting one of those args with the other panics before WiFi comes up,
and U-Boot then overwrites the uploaded image on its restart.

The FIT is normally already in DRAM (load_fit.py).  With --load it is read from
the board's own rootfs instead, which avoids an 11-minute UART upload per boot:

  boot_kernel.py --load /root/fits/test.fit

Usage: boot_kernel.py [--secs 30] [--addr 0x50000000] [--rdinit]
                      [--root DEV] [--load PATH] [--dev "mmc 1:1a"] [--extra ARGS]
"""
import os, sys, time, termios, argparse

PORT = "/dev/ttyUSB0"
COMMON = "console=ttyS0,115200 earlycon loglevel=8 panic=10 clk_ignore_unused pd_ignore_unused"
RDINIT_ARGS = COMMON + " rdinit=/init"
ROOT_ARGS = (COMMON + " root=%s rootwait rootfstype=ext4 rw net.ifnames=0 cma=128M")

def open_port():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def cmd(fd, s, settle=0.4):
    os.write(fd, s.encode() + b"\n")
    time.sleep(settle)
    out = b""
    t0 = time.time()
    while time.time() - t0 < 1.5:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        if b:
            out += b
        else:
            time.sleep(0.02)
    return out.decode("utf-8", "replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=30.0)
    ap.add_argument("--addr", default="0x50000000")
    ap.add_argument("--rdinit", action="store_true",
                    help="initramfs FIT (rdinit=/init) instead of the Debian root")
    ap.add_argument("--root", default="/dev/mmcblk0p26", help="root device")
    ap.add_argument("--load", help="ext4load this path from the board rootfs first")
    ap.add_argument("--dev", default="mmc 1:1a",
                    help="U-Boot device for --load; the partition index is hex")
    ap.add_argument("--extra", default="", help="extra kernel command line args")
    args = ap.parse_args()

    bootargs = RDINIT_ARGS if args.rdinit else ROOT_ARGS % args.root
    if args.extra:
        bootargs += " " + args.extra

    fd = open_port()
    time.sleep(0.2)
    # drain
    while True:
        try:
            if not os.read(fd, 4096):
                break
        except BlockingIOError:
            break

    print("--- setenv fdt_high ---");   print(cmd(fd, "setenv fdt_high 0x4f000000"))
    print("--- setenv initrd_high ---");print(cmd(fd, "setenv initrd_high 0x4f000000"))
    print("--- setenv bootargs ---");   print(cmd(fd, "setenv bootargs '%s'" % bootargs))
    if args.load:
        out = cmd(fd, "ext4load %s %s %s" % (args.dev, args.addr, args.load), settle=8.0)
        print("--- ext4load ---"); print(out)
        if "bytes read" not in out:
            print("!! ext4load failed -- is the path on the board rootfs?")
            os.close(fd)
            sys.exit(1)
    print("--- iminfo ---");            print(cmd(fd, "iminfo %s" % args.addr))

    print("=== bootm (%s), capturing %.0fs ===" % (args.addr, args.secs), flush=True)
    os.write(fd, ("bootm %s\n" % args.addr).encode())
    t0 = time.time()
    total = 0
    while time.time() - t0 < args.secs:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        except OSError as e:
            print("\n[console EIO: %s]" % e); break
        if b:
            sys.stdout.write(b.decode("utf-8", "replace"))
            sys.stdout.flush()
            total += len(b)
        else:
            time.sleep(0.02)
    os.close(fd)
    print("\n=== capture end (%d bytes) ===" % total)

if __name__ == "__main__":
    main()
