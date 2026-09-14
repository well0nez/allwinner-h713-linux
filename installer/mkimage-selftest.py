#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mkimage-selftest.py -- the whole way played through once, without a device.

What is checked here is exactly what can go wrong between the image builder and
the installer:

  1. h713.install.fill_placeholders() takes our table and writes the 30
     device-specific files into a copy of piece B.
  2. Afterwards the ext4 reader finds them again THROUGH THE FILE SYSTEM -- not
     at the raw offset, but as /mips/display.bin and friends. Only that proves
     that the offsets hit the right blocks.
  3. A dd onto a dummy disk (sparse, 7.28 GiB) puts the three pieces at their
     sectors; after that the locked range must be unchanged and the GPT of the
     dummy must show our six partitions.

Call:
    python3 mkimage-selftest.py out/hy310-v0.1.tabelle.json \\
            [--vendor out/vendor] [--tmp DIR] [--keep]

Since doku/121 stage 1 the test runs over the h713 package (no loading by path
any more); stage 3 renamed it from mkimage-selbsttest.py and made it English.
"""

import argparse
import hashlib
import json
import os
import shutil
import struct
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
from h713.install import check_placeholders, fill_placeholders             # noqa: E402
from h713.log import Log                                                   # noqa: E402
from h713.source import FileSource                                         # noqa: E402

SECT = 512


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
    print("\n[2] fill_placeholders() with the real vendor files")
    sources = {}
    for name in d["platzhalter"]:
        q = os.path.join(a.vendor, name)
        if not os.path.isfile(q):
            bad("source missing: %s" % q)
            return 1
        with open(q, "rb") as f:
            sources[name] = f.read()
    table = {k: tuple(v) for k, v in d["platzhalter"].items()}
    probe = os.path.join(a.tmp, "probe-b-filled.img")
    t0 = time.time()
    shutil.copyfile(os.path.join(directory, d["platzhalter_datei"]), probe)
    ok("copy of %s in %.1f s" % (d["platzhalter_datei"], time.time() - t0))

    class Silent:
        @staticmethod
        def ok(_t):
            pass

    t0 = time.time()
    fill_placeholders(probe, table, sources, log=Silent)
    ok("30 files filled in %.2f s" % (time.time() - t0))
    wrong = check_placeholders(probe, table, sources)
    if wrong:
        bad("check_placeholders complains: %s" % wrong)
    else:
        ok("check_placeholders: all 30 match at the raw offset")

    # ---------------------------------------------------------------- 3
    print("\n[3] counter-check THROUGH the file system (not at the raw offset)")
    q = FileSource(Path(probe))
    base = {"hy310-boot": (layout.LBA_BOOT - layout.PART_B_LBA) * SECT,
            "hy310-rootfs": (layout.LBA_ROOTFS - layout.PART_B_LBA) * SECT}
    length = {"hy310-boot": 262144 * SECT, "hy310-rootfs": os.path.getsize(probe) - base["hy310-rootfs"]}
    fs = {}
    for part in base:
        fs[part] = Ext4(q.sub(base[part], length[part], part), label=part)
        ok("%-13s opened as ext4: %s" % (part, fs[part].label_fs))
    good = 0
    for name, size, part, path in layout.PLACEHOLDERS:
        read = fs[part].read(path)
        if read == sources[name]:
            good += 1
        else:
            bad("%s: read through the file system it deviates (%d vs %d bytes)"
                % (path, len(read), len(sources[name])))
    if good == len(layout.PLACEHOLDERS):
        ok("all %d files read through ext4 byte-identical to the source" % good)
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
    # a file that is NOT a placeholder must not have changed
    fstab = fs["hy310-rootfs"].read("/etc/fstab")
    if b"hy310-rootfs" in fstab:
        ok("/etc/fstab in the rootfs intact (%d bytes)" % len(fstab))
    else:
        bad("/etc/fstab looks wrong")

    # ---------------------------------------------------------------- 4
    print("\n[4] dd onto a dummy disk (sparse, %d sectors)" % d["disk_sektoren"])
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

    print("\n[5] read the dummy as a drive")
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
            try:
                os.remove(x)
            except OSError:
                pass
        print("\n  Scratch files deleted (--keep holds them).")

    print("\n%s" % ("ALL GREEN" if not failures else "%d FAILURES" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
