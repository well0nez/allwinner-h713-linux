#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mkimage-selftest.py -- the whole way played through once, without a device.

What is checked here is exactly what can go wrong between the image builder and
the installer:

  1. The table says what h713.layout says: every file with its target, its group
     and its optional flag, and the user's authorized_keys. The installer reads
     the table and nothing else, so the table is what has to be right.
  2. The two file systems in piece B carry the empty target directories with the
     modes the installer relies on -- and not one vendor file. Read THROUGH the
     file system, not at a raw offset.
  3. Only with root (H713_ROOT_TESTS=1 and `sudo -n true`): the real copy through
     h713.mountfs onto a scratch copy of piece B, read back through the ext4
     reader, byte for byte. Without root the step says so and everything else
     still runs -- that is the ordinary case on a build machine.
  4. A dd onto a dummy disk (sparse, 7.28 GiB) puts the three pieces at their
     sectors; after that the locked range must be unchanged and the GPT of the
     dummy must show our six partitions.

Call:
    python3 mkimage-selftest.py out/hy310-v0.1.tabelle.json \\
            [--vendor out/vendor] [--tmp DIR] [--keep]

Since doku/121 stage 1 the test runs over the h713 package (no loading by path
any more); stage 3 renamed it from mkimage-selbsttest.py and made it English.
Layout v4 (plan/briefs/P-layout-v4.md) took the placeholders out of it: there is
nothing to fill any more, so step 2 checks the table and the empty trees, and the
copy itself needs root and happens in step 3.
"""

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pathlib import Path                                                   # noqa: E402

from h713 import layout                                                     # noqa: E402
from h713.blockdev import LOCK_FIRST, LOCK_LAST, SECTORS_EXPECTED           # noqa: E402
from h713.fs.ext4 import Ext4                                              # noqa: E402
from h713.gpt import Gpt, check_gpt                                        # noqa: E402
from h713.log import Log                                                   # noqa: E402
from h713.mkimage import file_table, partition_slices                      # noqa: E402
from h713.source import FileSource                                         # noqa: E402

SECT = 512


def root_available():
    """May this run mount something? Only then does step 3 do anything.

    Two conditions, both deliberate: H713_ROOT_TESTS=1 says a human allowed it,
    and `sudo -n true` says it works without asking for a password. An agent run
    or a build machine has neither, and the rest of this test does not need them.
    """
    if os.environ.get("H713_ROOT_TESTS") != "1":
        return False
    try:
        return subprocess.call(["sudo", "-n", "true"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except OSError:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("table")
    p.add_argument("--vendor", default=os.path.join(HERE, "out", "vendor"))
    p.add_argument("--tmp", default=os.path.join(HERE, "tmp"))
    p.add_argument("--keep", "--behalten", action="store_true", dest="keep",
                   help="do not delete the scratch files")
    a = p.parse_args()

    directory = os.path.dirname(os.path.abspath(a.table))
    with open(a.table, encoding="utf-8") as f:
        d = json.load(f)
    os.makedirs(a.tmp, exist_ok=True)
    failures = 0

    def ok(t):
        print("  OK   %s" % t)

    def bad(t):
        nonlocal failures
        print("  FAIL %s" % t, file=sys.stderr)
        failures += 1

    # ---------------------------------------------------------------- 1
    print("\n[1] the lock in h713-install fits the table")
    if (LOCK_FIRST, LOCK_LAST) == \
            (d["loch"]["lba"], d["loch"]["lba"] + d["loch"]["sektoren"] - 1):
        ok("LOCK_FIRST/LAST %d..%d -- equal" % (LOCK_FIRST, LOCK_LAST))
    else:
        bad("the installer locks %d..%d, the table says %d.."
            % (LOCK_FIRST, LOCK_LAST, d["loch"]["lba"]))
    if SECTORS_EXPECTED == d["disk_sektoren"]:
        ok("sector count %d -- equal" % SECTORS_EXPECTED)
    else:
        bad("the sector count deviates")

    # ---------------------------------------------------------------- 2
    print("\n[2] the table carries the file set of h713.layout")
    wanted = file_table()
    if d.get("dateien") == wanted["dateien"]:
        ok("%d files, each with partition, path, group and optional flag -- equal to layout.FILES"
           % len(wanted["dateien"]))
    else:
        have = {f["name"]: f for f in d.get("dateien", [])}
        for f in wanted["dateien"]:
            if have.get(f["name"]) != f:
                bad("%s: the table says %s, h713.layout says %s" % (f["name"], have.get(f["name"]), f))
        for name in sorted(set(have) - {f["name"] for f in wanted["dateien"]}):
            bad("%s is in the table and not in h713.layout" % name)
    if d.get("gruppen") == wanted["gruppen"]:
        ok("%d groups: %s" % (len(wanted["gruppen"]), ", ".join(wanted["gruppen"])))
    else:
        bad("the groups deviate: %s" % d.get("gruppen"))
    if d.get("nutzer") == wanted["nutzer"]:
        ok("the user's file: %s -> %s:%s, mode %s, directory %s"
           % tuple(wanted["nutzer"][0][k] for k in
                   ("name", "partition", "pfad", "modus", "verzeichnis_modus")))
    else:
        bad("the user's file deviates: %s" % d.get("nutzer"))
    optional = [f["name"] for f in wanted["dateien"] if f["optional"]]
    ok("%d of %d files are optional (a device may be without them): %s"
       % (len(optional), len(wanted["dateien"]),
          ", ".join(sorted({f["gruppe"] for f in wanted["dateien"] if f["optional"]}))))
    for key in ("platzhalter", "platzhalter_nutzer", "platzhalter_datei", "platzhalter_info"):
        if key in d:
            bad("the table still carries %s -- that is layout v3" % key)

    # ---------------------------------------------------------------- 3
    print("\n[3] the file systems in the image: target directories, and nothing of the vendor's")
    where = partition_slices(d)
    sources, fs = {}, {}
    for partition in ("hy310-boot", "hy310-rootfs"):
        datei, offset, length = where[partition]
        sources[partition] = FileSource(Path(os.path.join(directory, datei)))
        fs[partition] = Ext4(sources[partition].sub(offset, length, partition), label=partition)
        ok("%-13s opened as ext4 at offset %d of %s: %s"
           % (partition, offset, datei, fs[partition].label_fs))
    for partition in ("hy310-boot", "hy310-rootfs"):
        for path, mode in layout.target_directories(partition):
            ino = fs[partition].path_inode(path)
            inode = fs[partition].inode(ino) if ino is not None else None
            if inode is None or inode["typ"] != "d":
                bad("%s: %s is not a directory in the image" % (partition, path))
            elif inode["mode"] & 0o7777 != mode:
                bad("%s: %s has mode %04o instead of %04o"
                    % (partition, path, inode["mode"] & 0o7777, mode))
            else:
                # Not "empty": /lib/firmware comes out of Debian with files of its own.
                # That none of OUR files is in it is the check below, per file.
                ok("%-13s %-42s mode %04o, %d entry(s)"
                   % (partition, path, mode, len(fs[partition].ls(path))))
    carried = [f.path for f in layout.FILES if fs[f.partition].path_inode(f.path) is not None]
    if carried:
        bad("the image carries %d file(s) that belong to the manufacturer: %s"
            % (len(carried), ", ".join(carried[:3])))
    else:
        ok("none of the %d files of h713.layout is in the image" % len(layout.FILES))
    # The kernel FIT has to be untouched. Until 12.09. a fixed length stood here
    # (7987476, the FIT of 11.09.) -- every new kernel then made the test report
    # "damaged". Now: the identifier d00dfeed, and the total length out of the FDT
    # header (bytes 4..8, big endian) has to match the file length -- that checks
    # the structure, not a snapshot. If the source is next to it (tmp/boot-baum,
    # from mkimage-inputs.sh), it is compared byte for byte as well.
    fit = fs["hy310-boot"].read("/" + layout.KERNEL_FIT)
    head_ok = fit[:4] == b"\xd0\x0d\xfe\xed" and len(fit) >= 8 and \
        int.from_bytes(fit[4:8], "big") == len(fit)
    fit_source = os.path.join(HERE, "tmp", "boot-baum", layout.KERNEL_FIT)
    if head_ok and os.path.isfile(fit_source):
        with open(fit_source, "rb") as f:
            equal = f.read() == fit
        if equal:
            ok("h713-kernel.fit unchanged: %d bytes, identifier d00dfeed, byte-identical to tmp/boot-baum" % len(fit))
        else:
            bad("h713-kernel.fit deviates from tmp/boot-baum")
    elif head_ok:
        ok("h713-kernel.fit unchanged: %d bytes, identifier d00dfeed, FDT length matches" % len(fit))
    else:
        bad("h713-kernel.fit damaged (identifier or FDT length)")
    fstab = fs["hy310-rootfs"].read("/etc/fstab")
    if b"hy310-rootfs" in fstab:
        ok("/etc/fstab in the rootfs intact (%d bytes)" % len(fstab))
    else:
        bad("/etc/fstab looks wrong")

    # ---------------------------------------------------------------- 4
    print("\n[4] the real copy through a mount (needs root)")
    probe = os.path.join(a.tmp, "probe-b-filled.img")
    if not root_available():
        print("  NOTE no root (H713_ROOT_TESTS=1 and `sudo -n true` decide) -- the copy is "
              "not played through here. h713-install does it while installing, and "
              "installer/tests/test_install_readback.py does it with root.")
        probe = None
    else:
        # h713.mountfs is the installer's executor (package P2): copy_in(image_path,
        # partition_offset, partition_size, files), files = [(source, target, mode, owner)].
        from h713 import mountfs                                            # noqa: F401
        piece = {where[p][0] for p in ("hy310-boot", "hy310-rootfs")}
        if len(piece) != 1:
            bad("hy310-boot and hy310-rootfs lie in different pieces (%s) -- this test "
                "copies into one" % ", ".join(sorted(piece)))
            return 1
        t0 = time.time()
        shutil.copyfile(os.path.join(directory, piece.pop()), probe)
        ok("copy of %s in %.1f s" % (where["hy310-boot"][0], time.time() - t0))
        missing, jobs = [], {}
        for f in layout.FILES:
            source = os.path.join(a.vendor, f.name.replace("/", os.sep))
            if os.path.isfile(source):
                jobs.setdefault(f.partition, []).append(
                    (source, f.path, layout.FILE_MODE, layout.FILE_OWNER))
            elif f.optional:
                missing.append(f.name)
            else:
                bad("%s is missing in %s and is not optional" % (f.name, a.vendor))
        if missing:
            ok("not in %s and optional, left out: %d file(s)" % (a.vendor, len(missing)))
        t0 = time.time()
        for partition, files in sorted(jobs.items()):
            _datei, offset, length = where[partition]
            mountfs.copy_in(probe, offset, length, files)
        ok("%d files copied in in %.2f s" % (sum(len(v) for v in jobs.values()), time.time() - t0))
        q = FileSource(Path(probe))
        good = 0
        for partition, files in sorted(jobs.items()):
            _datei, offset, length = where[partition]
            read_fs = Ext4(q.sub(offset, length, partition), label=partition)
            for source, path, mode, _owner in files:
                with open(source, "rb") as f:
                    expect = f.read()
                if read_fs.read(path) == expect:
                    good += 1
                else:
                    bad("%s: read back through the file system it deviates" % path)
        ok("all %d files read through ext4 byte-identical to the source" % good)

    # ---------------------------------------------------------------- 5
    print("\n[5] dd onto a dummy disk (sparse, %d sectors)" % d["disk_sektoren"])
    dummy = os.path.join(a.tmp, "dummy.img")
    mark = b"SECURE-STORAGE-MUST-NOT-BE-TOUCHED " * 30
    with open(dummy, "wb") as f:
        f.truncate(d["disk_sektoren"] * SECT)
        # Fill the locked range with a mark beforehand, so that a hit would show.
        # 2048 sectors = 1 MiB.
        f.seek(d["loch"]["lba"] * SECT)
        block = (mark * (1 + (1 << 20) // len(mark)))[:d["loch"]["sektoren"] * SECT]
        f.write(block)
    before = hashlib.sha256(block).hexdigest()
    t0 = time.time()
    with open(dummy, "r+b") as z:
        for t in d["teile"]:
            with open(os.path.join(directory, t["datei"]), "rb") as f:
                z.seek(t["lba"] * SECT)
                while True:
                    b = f.read(8 << 20)
                    if not b:
                        break
                    z.write(b)
        z.flush()
        os.fsync(z.fileno())
    ok("three pieces written in %.1f s" % (time.time() - t0))
    with open(dummy, "rb") as f:
        f.seek(d["loch"]["lba"] * SECT)
        after = hashlib.sha256(f.read(d["loch"]["sektoren"] * SECT)).hexdigest()
    if after == before:
        ok("Secure Storage unchanged: sha256 %s... before and after" % before[:16])
    else:
        bad("SECURE STORAGE OVERWRITTEN -- %s instead of %s" % (after[:16], before[:16]))

    print("\n[6] read the dummy as a drive")
    aq = FileSource(Path(dummy))
    if Gpt.is_gpt(aq):
        Gpt(aq, Log(quiet=True))
        ok("GPT recognised")
    else:
        bad("the dummy carries no recognisable GPT")
    # read the partition table raw
    head = aq.read(0, 9 * SECT)
    problems = check_gpt(head, aq.read(layout.PART_C_LBA * SECT, layout.PART_C_SECTORS * SECT),
                         d["disk_sektoren"])
    for x in problems:
        bad(x)
    if not problems:
        ok("six partitions, the CRCs match, the backup copy at the end of the disk matches")
    # SPL and U-Boot in their place?
    if aq.read(layout.LBA_SPL * SECT + 4, 8) == b"eGON.BT0":
        ok("eGON.BT0 sits at LBA %d" % layout.LBA_SPL)
    else:
        bad("there is no SPL at LBA %d" % layout.LBA_SPL)
    # Environment: until v0.8 the range had to be empty; since 12.09. the built-in
    # default of the U-Boot that ships with the image sits there -- 64 KiB, a CRC32
    # over the rest in front, and h713_gate has to occur in it.
    env = aq.read(layout.LBA_ENV * SECT, layout.ENV_BYTES)
    crc = struct.unpack("<I", env[:4])[0]
    if crc == (zlib.crc32(env[4:]) & 0xffffffff) and b"h713_gate=" in env:
        gate = [e for e in env[4:].split(b"\0") if e.startswith(b"h713_gate=")][0].decode()
        ok("hy310-env (LBA %d) carries a valid environment: CRC %08x, %s" % (layout.LBA_ENV, crc, gate))
    elif not any(env):
        bad("hy310-env is empty -- U-Boot would report 'bad CRC' and run on defaults (state before 12.09.)")
    else:
        bad("hy310-env: CRC %08x does not match, or h713_gate is missing" % crc)
    # And the two file systems straight out of the dummy
    for part, lba, n in (("hy310-boot", layout.LBA_BOOT, 262144 * SECT),
                         ("hy310-rootfs", layout.LBA_ROOTFS, 1 << 30)):
        f2 = Ext4(aq.sub(lba * SECT, n, part), label=part)
        count = len(list(f2.walk("/", max_depth=2)))
        ok("%-13s readable out of the dummy (label '%s', %d entries in two levels)"
           % (part, f2.label_fs, count))

    if not a.keep:
        for x in (probe, dummy):
            if not x:
                continue
            try:
                os.remove(x)
            except OSError:
                pass
        print("\n  Scratch files deleted (--keep holds them).")

    print("\n%s" % ("ALL GREEN" if not failures else "%d FAILURES" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
