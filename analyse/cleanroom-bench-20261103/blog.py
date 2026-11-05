"""Spec-side bench helper: /dev/mem access with a log line fsynced BEFORE every first access.

Every access that could hang the SoC is announced in the log file and the file is fsynced
before the access happens, so that after a watchdog reset the last line names the access.
"""
import mmap
import os
import struct
import sys
import time

_LOG = None
_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
_maps = {}


def openlog(path):
    global _LOG
    _LOG = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    d = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    os.fsync(d)
    os.close(d)
    boot = open("/proc/sys/kernel/random/boot_id").read().strip()
    log(f"=== open {path} boot {boot} cmdline {open('/proc/cmdline').read().strip()}")


def log(s):
    line = f"{time.monotonic():10.3f} {s}\n"
    if _LOG is not None:
        os.write(_LOG, line.encode())
        os.fsync(_LOG)
    sys.stdout.write(line)
    sys.stdout.flush()


def _page(a):
    base = a & ~0xFFF
    m = _maps.get(base)
    if m is None:
        m = mmap.mmap(_fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
        _maps[base] = m
    return m, a & 0xFFF


def rd(a):
    m, o = _page(a)
    return struct.unpack_from("<I", m, o)[0]


def wr(a, v):
    m, o = _page(a)
    struct.pack_into("<I", m, o, v & 0xFFFFFFFF)


def rd_logged(a, n=1, label=""):
    """Announce (fsync), then read n words; log the values 4 per line."""
    log(f"BEFORE-READ {a:#010x} n={n} {label}")
    vals = [rd(a + 4 * i) for i in range(n)]
    for i in range(0, n, 4):
        log(f"  {a + 4 * i:#010x}: " + " ".join(f"{v:08x}" for v in vals[i:i + 4]))
    return vals


def wr_logged(a, v, label=""):
    log(f"BEFORE-WRITE {a:#010x} <- {v:#010x} {label}")
    wr(a, v)


def map_ram(a, size):
    """Map a physical DRAM window (outside System RAM) for frame data; returns (mmap, offset)."""
    base = a & ~0xFFF
    off = a - base
    m = mmap.mmap(_fd, (size + off + 0xFFF) & ~0xFFF, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
    return m, off
