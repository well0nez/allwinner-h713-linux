# SPDX-License-Identifier: GPL-2.0
"""Raw access to the projector's eMMC once U-Boot exposes it as a drive:
opening it, keeping the desktop off it, and recognising it by content.

Stage 1: moved from hy310-install.py (I:44-45, 104-105, 167-419, 613).
Every printed string and every exception text is unchanged.
"""

from __future__ import annotations

import os
import platform
import struct
import subprocess
import time

from .log import console

SECT = 512
SECTORS_EXPECTED = 15269888          # 7.28 GiB -- the eMMC of the HY310

# The secure-storage block is NEVER written, not even with --force. It belongs
# to this one device and cannot be restored (doku/109 §2.3).
LOCK_FIRST = 12288
LOCK_LAST = 14335


class Disk:
    """Raw access to a block device -- /dev/sdX on Linux, \\\\.\\PhysicalDriveN
    on Windows. Python opens both in binary mode; what differs is finding the
    device and the question of who is holding it right now."""

    def __init__(self, path, writable=False, exclusive=None):
        self.path = path
        self.writable = writable
        if exclusive is None:
            exclusive = writable
        if exclusive:
            # Whoever is still mounted writes its cache back over our fresh
            # image -- and a read-back check through that same cache reports
            # "matches" all the same (finding S46). So look first.
            open_ones = mounted(path)
            if open_ones:
                # The desktop mounts the partitions unasked as soon as the
                # drive appears -- and it does so ONE AFTER THE OTHER. A single
                # pass unmounts the first while the second is just arriving
                # (which is exactly what happened on 11.09.). So several
                # passes, until nothing is left twice in a row.
                console.warn("Der Desktop hat Partitionen eingehaengt: %s"
                             % ", ".join(open_ones))
                calm = 0
                for _ in range(12):
                    unmount(path, console)
                    time.sleep(0.4)
                    open_ones = mounted(path)
                    calm = calm + 1 if not open_ones else 0
                    if calm >= 2:
                        break
            if open_ones:
                raise RuntimeError(
                    "Von %s ist noch etwas eingehaengt und laesst sich nicht "
                    "loesen: %s. Dort arbeitet noch jemand -- schliesse das "
                    "Programm oder haenge von Hand aus ('udisksctl unmount -b "
                    "...'), sonst ueberschreibt das laufende Dateisystem, was "
                    "wir schreiben." % (path, ", ".join(open_ones)))
        flags = os.O_RDWR if writable else os.O_RDONLY
        if hasattr(os, "O_BINARY"):          # Windows
            flags |= os.O_BINARY
        if exclusive and hasattr(os, "O_EXCL"):
            flags |= os.O_EXCL               # Linux: keeps mounts away
        # O_EXCL fails with EBUSY even when NOTHING is mounted: the desktop
        # (udisks) holds a freshly appeared drive open for a moment to examine
        # it. That takes fractions of a second, so a few attempts instead of
        # giving up -- and another unmount in between, in case it has mounted
        # something after all.
        last = None
        for attempt in range(10):
            try:
                self.fd = os.open(path, flags)
                break
            except OSError as e:
                last = e
                if not (exclusive and getattr(e, "errno", None) == 16):
                    raise
                if attempt == 0:
                    console.info("  %s ist noch belegt (der Desktop untersucht es) -- "
                                 "ich warte" % path)
                unmount(path)
                time.sleep(0.5)
        else:
            open_ones = mounted(path)
            raise RuntimeError(
                "%s ist nach 5 s immer noch belegt%s. Schliesse das Programm, "
                "das darauf zugreift (Dateimanager, Datentraegerverwaltung), "
                "und versuche es erneut." % (path,
                    " (eingehaengt: %s)" % ", ".join(open_ones) if open_ones else ""))
        self.sectors = self._size() // SECT

    def _size(self):
        if platform.system() == "Windows":
            import ctypes
            import ctypes.wintypes as wt
            # IOCTL_DISK_GET_LENGTH_INFO
            handle = ctypes.windll.kernel32._get_osfhandle(self.fd)
            buf = ctypes.create_string_buffer(8)
            ret = wt.DWORD()
            if not ctypes.windll.kernel32.DeviceIoControl(
                    handle, 0x0007405C, None, 0, buf, 8, ctypes.byref(ret), None):
                raise OSError("Groesse des Laufwerks nicht lesbar")
            return int.from_bytes(buf.raw[:8], "little")
        return os.lseek(self.fd, 0, os.SEEK_END)

    def read(self, lba, sectors):
        os.lseek(self.fd, lba * SECT, os.SEEK_SET)
        rest = sectors * SECT
        parts = []
        while rest:
            b = os.read(self.fd, min(rest, 4 << 20))
            if not b:
                break
            parts.append(b)
            rest -= len(b)
        return b"".join(parts)

    def write(self, lba, data):
        if not self.writable:
            raise RuntimeError("nur zum Lesen geoeffnet")
        end = lba + (len(data) + SECT - 1) // SECT - 1
        if lba <= LOCK_LAST and end >= LOCK_FIRST:
            raise RuntimeError(
                "Schreibversuch auf LBA %d..%d beruehrt den Secure Storage "
                "(%d..%d). Dort stehen HDCP-Schluessel, die MAC-Adressen und "
                "die Seriennummer dieses Geraets -- nicht wiederherstellbar."
                % (lba, end, LOCK_FIRST, LOCK_LAST))
        os.lseek(self.fd, lba * SECT, os.SEEK_SET)
        view = memoryview(data)
        while view:
            n = os.write(self.fd, view[:4 << 20])
            view = view[n:]

    def sync(self):
        try:
            os.fsync(self.fd)
        except OSError:
            pass

    def close(self):
        self.sync()
        os.close(self.fd)


def mounted(path, raw=False):
    """Which partitions of this drive are mounted right now?

    raw=False: list of readable lines for the message.
    raw=True:  list of device paths -- that is what unmount() needs.
    """
    hits = []
    if platform.system() != "Linux":
        return hits
    try:
        with open("/proc/self/mounts") as f:
            lines = f.read().splitlines()
    except OSError:
        return hits
    base = os.path.realpath(path)
    for z in lines:
        parts = z.split()
        if len(parts) < 2:
            continue
        source = os.path.realpath(parts[0])
        if source == base or (source.startswith(base) and source[len(base):].isdigit()):
            hits.append(parts[0] if raw else "%s auf %s" % (parts[0], parts[1]))
    return hits


def unmount(path, log=None):
    """Unmount the partitions of this drive and say what happened.

    Why this exists: as soon as the eMMC appears as a drive, every desktop
    mounts the readable partitions by itself -- on Linux Mint within a second.
    The installer used to give up then and the user had to unmount by hand; on
    the first live run on 10.09. that cost three attempts. Only what belongs to
    THIS drive is unmounted, and only what we are about to write ourselves.

    Returns: (unmounted, left) as lists of device paths.
    """
    unmounted, left = [], []
    for dev in mounted(path, raw=True):
        for command in (["udisksctl", "unmount", "-b", dev],
                        ["umount", dev]):
            try:
                r = subprocess.run(command, capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                continue
            if r.returncode == 0:
                unmounted.append(dev)
                break
        else:
            left.append(dev)
    if log:
        for dev in unmounted:
            log.info("  %s ausgehaengt" % dev)
    return unmounted, left


def device_kind(path):
    """Check by content whether this really is the projector -- the sector
    count alone is not enough, a foreign disk can happen to be the same size
    (finding S46). Recognised is either our own layout or the stock layout;
    both by the partition names of the GPT."""
    try:
        p = Disk(path, writable=False, exclusive=False)
    except PermissionError:
        # Without read permission nothing can be said -- that is something
        # else than "does not look like the projector" and must not sound
        # like it.
        raise
    except OSError:
        return None
    try:
        head = p.read(1, 1)
        if head[:8] != b"EFI PART":
            return "keine GPT"
        entlba, nent, entsz = struct.unpack_from("<QII", head, 72)
        if nent > 128 or entsz not in (128, 256):
            return "GPT unplausibel"
        arr = p.read(entlba, (nent * entsz + SECT - 1) // SECT)
        names = []
        for i in range(nent):
            e = arr[i * entsz:(i + 1) * entsz]
            if e[:16] == b"\0" * 16:
                continue
            names.append(e[56:56 + 72].decode("utf-16-le", "replace").rstrip("\0"))
    finally:
        p.close()
    if any(n.startswith("hy310-") for n in names):
        return "unser Layout (%s)" % ", ".join(n for n in names if n.startswith("hy310-"))
    if "bootloader_a" in names and "super" in names:
        return "Stock-Layout, %d Partitionen" % len(names)
    return None


def find_drive(expected=SECTORS_EXPECTED):
    """Look for the exposed drive: right size AND removable medium.
    The content check happens in device_kind()."""
    system = platform.system()
    hits = []
    if system == "Linux":
        for name in sorted(os.listdir("/sys/block")):
            if not name.startswith(("sd", "vd")):
                continue
            try:
                with open("/sys/block/%s/size" % name) as f:
                    n = int(f.read().strip())
                with open("/sys/block/%s/removable" % name) as f:
                    removable = f.read().strip() == "1"
            except OSError:
                continue
            if n == expected and removable:
                hits.append(("/dev/" + name, n, removable))
    elif system == "Windows":
        for i in range(16):
            path = r"\\.\PhysicalDrive%d" % i
            try:
                p = Disk(path)
                n = p.sectors
                p.close()
            except OSError:
                continue
            if n == expected:
                hits.append((path, n, True))
    else:
        raise SystemExit("Nicht unterstuetztes System: %s" % system)
    return hits


def _around_lock(lba, data):
    """Split one write into the pieces before and behind the secure storage."""
    parts = []
    n = len(data) // SECT
    before = LOCK_FIRST - lba
    if before > 0:
        parts.append((lba, data[:before * SECT]))
    after_lba = LOCK_LAST + 1
    if lba + n > after_lba:
        off = (after_lba - lba) * SECT
        parts.append((after_lba, data[off:]))
    return parts
