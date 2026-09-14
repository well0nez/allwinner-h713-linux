# SPDX-License-Identifier: GPL-2.0
"""Putting the manufacturer's firmware back onto the eMMC.

Stage 1 of plan doku/121: moved from hy310-install.py (I:1732-1882). Every
printed string and every exception text is unchanged. What used to be loaded
out of h713-extract at runtime now comes from the package itself: the IMAGEWTY
reader, the file source, the sparse writer and the stock GPT builder.

Stage 2 (package C-C, doku/121 §4) makes the restore follow the board
profile: the GPT header counts the partitions the image really has; a partition the image
brings no file for is zeroed only when neither the profile's `preserve_on_restore` nor the
built-in default keeps it; `boot-resource.fex` never takes `mips/` away from a bootloader
partition; duplicate file-table entries of the container are compared (A1); and a dry run
plans from the file and chunk tables instead of reading 1.7 GiB of payload (A4A6 finding c).
New and changed messages are English (api-stufe2.md); the untouched ones stay German.
"""

from __future__ import annotations

import fnmatch
import gzip
import hashlib
import os
import pathlib

from .blockdev import SECT
from .fex import stock_plan
from .fs.fat16 import Fat
from .fs.sparse import SparseSource, is_sparse, write_sparse
from .gpt import build_stock_gpt
from .imagewty import Imagewty
from .log import Abort, Log, console
from .source import FileSource, Source
from .util import mib

BOOT_RESOURCE = "boot-resource.fex"     # the FAT16 image of bootloader_a/_b
MIPS_DIR = "mips"                       # what the stock U-Boot reads out of it (A0 section 1a)

# Never zeroed when no profile says otherwise -- the conservative fallback for a board we
# could not identify (A0 section 5: bootloader_a/_b are a pair `misc` switches between,
# media_data is /oem and carries TSE overrides, private and Reserve0 exist only on this one
# device, UDISK is the user's data). Until stage 2 C-C the code kept a fixed set
# {"private", "reserve0_a", "reserve0_b"} and zeroed everything else.
DEFAULT_PRESERVE = ("private", "Reserve0*", "media_data", "bootloader_*")
# UDISK is deliberately not in the default: its head was zeroed by every stock restore so far
# (11.09., 12.09., 14.09.) and Android formatted it on first boot -- the proven state (Fable, C-C review).


class DiskRegion(Source):
    """One partition of the open device, read-only, as a Source -- the mips/ guard has to
    look at what is there before it overwrites it, and `Fat` reads through this interface."""

    def __init__(self, disk, lba, sectors):
        self._disk, self._lba = disk, lba
        self.size = sectors * SECT
        self.name = "%s LBA %d" % (disk.path, lba)

    def read(self, off, n):
        if off < 0 or n < 0:
            raise ValueError("negative read")
        if off >= self.size:
            return b""
        n = min(n, self.size - off)
        first, front = off // SECT, off % SECT
        data = self._disk.read(self._lba + first, (front + n + SECT - 1) // SECT)
        return data[front:front + n]


def _has_mips(q, origin):
    """Does this FAT image carry a mips/ directory? None when it is no readable FAT."""
    try:
        if q is None or not Fat.is_fat(q):
            return None
        return Fat(q, Log(quiet=True), origin).directory(MIPS_DIR) is not None
    except Abort:
        return None


def _sha256(q):
    """sha256 over a whole source, without holding it in memory."""
    h, off = hashlib.sha256(), 0
    while off < q.size:
        b = q.read(off, min(4 << 20, q.size - off))
        if not b:
            break
        h.update(b)
        off += len(b)
    return h.hexdigest()


def _check_copies(img, names):
    """Compare the copies a file has in the container's file table.

    A1 found `boot-resource.fex` twice in the HY310 and the HY350 image (one entry per
    slot), byte-identical. If two copies ever differ we cannot know which one the
    manufacturer's tool would have written -- that is an error, not a warning.
    Returns {name: note} for the log line of the files that have more than one copy.
    """
    notes = {}
    for name in sorted(set(names)):
        copies = img.copies.get(name, [])
        if len(copies) < 2:
            continue
        digests = [_sha256(q) for q in img.file_copies(name)]
        places = ", ".join("%#x" % c["offset"] for c in copies)
        if len(set(digests)) > 1:
            raise RuntimeError("%s: the image holds %d copies of this file (%s) and they "
                               "differ -- refusing to restore from an inconsistent container"
                               % (name, len(copies), places))
        notes[name] = " (%d identical copies in the image: %s)" % (len(copies), places)
    return notes


def _sparse_bytes(d):
    """How many bytes write_sparse() would write -- from the chunk table alone; a dry run
    used to unpack the full 1.5 GiB of super.fex for this number (A4A6 finding c). Same
    arithmetic: RAW payload, FILL and DONT_CARE by block count, CRC chunks have no blocks."""
    chunks = SparseSource(d, Log(quiet=True)).regions()
    return sum(length for _start, length, _type, _data in chunks)


def _preserved_by(name, patterns):
    """The pattern that keeps `name` out of the zeroing pass, or None. Case-insensitively,
    with the '*' the profiles use: "Reserve0*" covers the single Reserve0 of the ADT-3
    boards as well as the Reserve0_a/_b pair of the HY310."""
    for pattern in patterns:
        if fnmatch.fnmatchcase(name.lower(), pattern.lower()):
            return pattern
    return None


def restore_stock(disk, image_file, extractor=None, log=console, dry_run=False, data_dir=None,
                  profile=None):
    """Install the manufacturer's firmware from an IMAGEWTY container.

    The secure storage at LBA 12288 is not touched while doing it: the raw
    targets lie at 16, 256, 24576 and 32800, the first partition begins at
    73728. The lock in Disk.write() watches over it all the same.

    `extractor` is the path to h713-extract. It is still taken so that callers
    do not change, and it is no longer used -- the package brings its own
    IMAGEWTY reader (api-h713.md: `_extraktor_laden` is deleted).

    `profile` is the board profile of the device (h713.profiles); its
    `preserve_on_restore` names the partitions that are not zeroed when the image
    brings no file for them. Without a profile DEFAULT_PRESERVE applies.
    """
    q = FileSource(pathlib.Path(image_file))
    if not Imagewty.is_imagewty(q):
        raise RuntimeError("%s is no IMAGEWTY container" % image_file)
    img = Imagewty(q, Log())
    partitions, raw = stock_plan(img)
    if profile and profile.get("preserve_on_restore"):
        preserve = tuple(profile["preserve_on_restore"])
        preserve_from = "profile '%s'" % profile.get("id", "?")
    else:
        preserve, preserve_from = DEFAULT_PRESERVE, "the built-in list"

    log.info("%d partitions according to sys_partition.fex" % len(partitions))
    written = 0
    missing = []
    # Every copy of a file has to say the same thing before we write any of them.
    notes = _check_copies(img, [n for n, _lba in raw] +
                          [s for _p, _l, _s, s in partitions if s])
    # mips/ guard (A0 section 5): does the image bring the directory at all?
    image_mips = (_has_mips(img.file(BOOT_RESOURCE), BOOT_RESOURCE + " (image)")
                  if any(s == BOOT_RESOURCE for _p, _l, _s, s in partitions) else None)

    # 0. Partition table -- without it Android does not find its partitions.
    gpt = build_stock_gpt(partitions, disk.sectors)
    if not dry_run:
        for lba in sorted(gpt):
            disk.write(lba, gpt[lba])
    log.ok("%-22s -> GPT (protective MBR, header, table, backup copies)" % "sys_partition.fex")

    # 1. Raw regions in front of the first partition
    for name, target_lba in raw:
        d = img.file(name)
        if d is None:
            missing.append(name)
            continue
        n = d.size
        if not dry_run:
            data = d.read(0, d.size)
            n = len(data)
            disk.write(target_lba, data)
        written += n
        log.ok("%-22s -> LBA %-6d %7.2f MiB%s" % (name, target_lba, mib(n), notes.get(name, "")))

    # 2. Partitions
    for pname, plba, psect, source in partitions:
        if not source:
            continue                    # B slots and runtime data: stay empty
        d = img.file(source)
        if d is None:
            missing.append(source)
            continue
        # The image has no mips/, the device has: the stock U-Boot of this board loads
        # mips/* from the bootloader partition `misc` selects (A0 section 1a), and the
        # image cannot put it back. Leave the partition alone.
        if source == BOOT_RESOURCE and image_mips is False and \
                _has_mips(DiskRegion(disk, plba, psect), pname) is True:
            log.warn("%s not written: %s in the image has no %s/ directory, but the partition "
                     "on the device has one -- the stock U-Boot reads mips/* from there "
                     "(A0 section 5), and this image could not put it back"
                     % (pname, source, MIPS_DIR))
            continue
        if is_sparse(d.read(0, 28)):
            n = _sparse_bytes(d) if dry_run else write_sparse(disk, d, plba)
            if psect and n > psect * SECT:
                raise RuntimeError("%s unpacks to %.1f MiB, %s only holds %.1f MiB"
                                   % (source, mib(n), pname, mib(psect * SECT)))
            written += n
            log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB unpacked (sparse, file %.0f MiB)"
                   % (source, pname, plba, mib(n), mib(d.size)))
            continue
        n = d.size
        if psect and n > psect * SECT:
            raise RuntimeError("%s (%.1f MiB) does not fit into %s (%.1f MiB)"
                               % (source, mib(n), pname, mib(psect * SECT)))
        if not dry_run:
            data = d.read(0, d.size)
            n = len(data)
            disk.write(plba, data)
        written += n
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB%s"
               % (source, pname, plba, mib(n), notes.get(source, "")))

    # 3. Whatever has no source has to be zeroed (finding S46 B8).
    #
    #    The manufacturer's tool erases the eMMC before it writes. We write only
    #    what stands in the image -- everything else keeps the content of the
    #    previous system. Android then finds no ext4 in "metadata", gives up and
    #    boots back into the bootloader. Happened exactly that way on 10.09.:
    #    "EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem", p19 = metadata.
    #
    #    Left out are the partitions the profile (or DEFAULT_PRESERVE) keeps: they
    #    exist only on this device, or no image brings their content back. The secure
    #    storage is protected by the lock in Disk.write() anyway.
    #    Whoever gets a filesystem right away (step 4) is not zeroed first.
    FILESYSTEMS = {"metadata": "metadata-leer-16m.ext4.gz"}
    HEAD_SECTORS = 131072               # 64 MiB kill an ext4 including its backup superblocks
    zeros = b"\0" * (1 << 20)
    for pname, plba, psect, source in partitions:
        if source:
            continue
        kept = _preserved_by(pname, preserve)
        if kept:
            log.info("  %-16s left untouched -- no file in the image, %s keeps '%s'"
                     % (pname, preserve_from, kept))
            continue
        if pname.lower() in FILESYSTEMS:
            continue                    # gets a filesystem in a moment
        left = psect if psect else disk.sectors - 33 - plba
        if left <= 0:
            continue
        sect = min(left, HEAD_SECTORS)
        if not dry_run:
            done = 0
            while done < sect:
                n = min(len(zeros) // SECT, sect - done)
                disk.write(plba + done, zeros[:n * SECT])
                done += n
        written += sect * SECT
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB zeroed%s"
               % ("(no image)", pname, plba, mib(sect * SECT),
                  "" if sect == left else " (head)"))

    # 4. Create the filesystems the image does not bring along.
    #
    #    The fstab out of the vendor_boot ramdisk (first_stage_ramdisk/fstab.sun50iw12p1)
    #    says for metadata:
    #
    #      /dev/block/by-name/metadata  /metadata  ext4  errors=panic
    #                                   wait,first_stage_mount,formattable,check
    #
    #    "formattable" does not help here: the entry is at the same time
    #    "first_stage_mount", and the first stage of init has no mke2fs -- that
    #    lies in /system only. So it cannot format and boots back into the
    #    bootloader instead:
    #
    #      EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem
    #      reboot: Restarting system with command 'bootloader'
    #
    #    On a factory device the manufacturer's PC tool creates this filesystem.
    #    We ship it as an empty, packed image (17 KB for 16 MiB). UDISK does not
    #    need that: its line is "latemount" without "first_stage_mount", the
    #    second stage formats it itself.
    # `data_dir`: where the shipped filesystem blobs live (the installer directory, passed by
    # the calling script); the module directory only as a fallback (B5 finding 4.3).
    here = data_dir or os.path.dirname(os.path.abspath(__file__))
    for pname, plba, psect, source in partitions:
        blob = FILESYSTEMS.get(pname.lower())
        if not blob:
            continue
        blob_path = os.path.join(here, blob)
        if not os.path.isfile(blob_path):
            log.warn("%s is missing -- %s stays without a filesystem, Android "
                     "then does not boot through" % (blob, pname))
            continue
        with gzip.open(blob_path, "rb") as fh:
            data = fh.read()
        if psect and len(data) > psect * SECT:
            raise RuntimeError("%s (%.1f MiB) does not fit into %s"
                               % (blob, mib(len(data)), pname))
        if not dry_run:
            disk.write(plba, data)
        written += len(data)
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB empty ext4"
               % (blob, pname, plba, mib(len(data))))

    if missing:
        log.warn("not in the image and therefore left out: %s" % ", ".join(sorted(set(missing))))
    if not dry_run:
        disk.sync()
    return written, partitions
