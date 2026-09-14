# SPDX-License-Identifier: GPL-2.0
"""Putting the manufacturer's firmware back onto the eMMC.

Stage 1 of plan doku/121: moved from hy310-install.py (I:1732-1882). Every
printed string and every exception text is unchanged. What used to be loaded
out of h713-extract at runtime now comes from the package itself: the IMAGEWTY
reader, the file source, the sparse writer and the stock GPT builder.
"""

from __future__ import annotations

import gzip
import os
import pathlib

from .blockdev import SECT
from .fex import stock_plan
from .fs.sparse import is_sparse, write_sparse
from .gpt import build_stock_gpt
from .imagewty import Imagewty
from .log import Log, console
from .source import FileSource
from .util import mib


def restore_stock(disk, image_file, extractor=None, log=console, dry_run=False, data_dir=None):
    """Install the manufacturer's firmware from an IMAGEWTY container.

    The secure storage at LBA 12288 is not touched while doing it: the raw
    targets lie at 16, 256, 24576 and 32800, the first partition begins at
    73728. The lock in Disk.write() watches over it all the same.

    `extractor` is the path to h713-extract. It is still taken so that callers
    do not change, and it is no longer used -- the package brings its own
    IMAGEWTY reader (api-h713.md: `_extraktor_laden` is deleted).
    """
    q = FileSource(pathlib.Path(image_file))
    if not Imagewty.is_imagewty(q):
        raise RuntimeError("%s ist kein IMAGEWTY-Container" % image_file)
    img = Imagewty(q, Log())
    partitions, raw = stock_plan(img)

    log.info("%d Partitionen laut sys_partition.fex" % len(partitions))
    written = 0
    missing = []

    # 0. Partition table -- without it Android does not find its partitions.
    gpt = build_stock_gpt(partitions, disk.sectors)
    if not dry_run:
        for lba in sorted(gpt):
            disk.write(lba, gpt[lba])
    log.ok("%-22s -> GPT (Schutz-MBR, Kopf, Tabelle, Sicherungskopien)" % "sys_partition.fex")

    # 1. Raw regions in front of the first partition
    for name, target_lba in raw:
        d = img.file(name)
        if d is None:
            missing.append(name)
            continue
        data = d.read(0, d.size)
        if not dry_run:
            disk.write(target_lba, data)
        written += len(data)
        log.ok("%-22s -> LBA %-6d %7.2f MiB" % (name, target_lba, mib(len(data))))

    # 2. Partitions
    for pname, plba, psect, source in partitions:
        if not source:
            continue                    # B slots and runtime data: stay empty
        d = img.file(source)
        if d is None:
            missing.append(source)
            continue
        if is_sparse(d.read(0, 28)):
            n = write_sparse(disk, d, plba, dry_run)
            if psect and n > psect * SECT:
                raise RuntimeError("%s entpackt %.1f MiB, %s fasst nur %.1f MiB"
                                   % (source, mib(n), pname, mib(psect * SECT)))
            written += n
            log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB entpackt (Sparse, Datei %.0f MiB)"
                   % (source, pname, plba, mib(n), mib(d.size)))
            continue
        data = d.read(0, d.size)
        if psect and len(data) > psect * SECT:
            raise RuntimeError("%s (%.1f MiB) passt nicht in %s (%.1f MiB)"
                               % (source, mib(len(data)), pname, mib(psect * SECT)))
        if not dry_run:
            disk.write(plba, data)
        written += len(data)
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB"
               % (source, pname, plba, mib(len(data))))

    # 3. Whatever has no source has to be zeroed (finding S46 B8).
    #
    #    The manufacturer's tool erases the eMMC before it writes. We write only
    #    what stands in the image -- everything else keeps the content of the
    #    previous system. Android then finds no ext4 in "metadata", gives up and
    #    boots back into the bootloader. Happened exactly that way on 10.09.:
    #    "EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem", p19 = metadata.
    #
    #    Left out are the regions that exist only on this one device and that no
    #    image brings back. The secure storage is protected by the lock in
    #    Disk.write() anyway.
    #    Whoever gets a filesystem right away (step 4) is not zeroed first.
    FILESYSTEMS = {"metadata": "metadata-leer-16m.ext4.gz"}
    DO_NOT_ZERO = {"private", "reserve0_a", "reserve0_b"}
    HEAD_SECTORS = 131072               # 64 MiB kill an ext4 including its backup superblocks
    zeros = b"\0" * (1 << 20)
    for pname, plba, psect, source in partitions:
        if source:
            continue
        if pname.lower() in DO_NOT_ZERO:
            log.info("  %-16s bleibt unangetastet -- gibt es nur auf diesem Geraet"
                     % pname)
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
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB genullt%s"
               % ("(kein Abbild)", pname, plba, mib(sect * SECT),
                  "" if sect == left else " (Kopf)"))

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
            log.warn("%s fehlt -- %s bleibt ohne Dateisystem, Android startet "
                     "dann nicht durch" % (blob, pname))
            continue
        with gzip.open(blob_path, "rb") as fh:
            data = fh.read()
        if psect and len(data) > psect * SECT:
            raise RuntimeError("%s (%.1f MiB) passt nicht in %s"
                               % (blob, mib(len(data)), pname))
        if not dry_run:
            disk.write(plba, data)
        written += len(data)
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB leeres ext4"
               % (blob, pname, plba, mib(len(data))))

    if missing:
        log.warn("nicht im Image und daher ausgelassen: %s" % ", ".join(sorted(set(missing))))
    if not dry_run:
        disk.sync()
    return written, partitions
