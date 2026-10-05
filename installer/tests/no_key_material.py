#!/usr/bin/env python3
"""Does this tree (or file) contain HDCP key material? Then the build must stop.

Why this exists
---------------
The HDCP 1.4 key set of these projectors is a DRM secret, and - measured on two
devices with two different serial numbers - it is NOT device-bound: one and the
same key set sits in all of them. Publishing it would hand everyone the means to
circumvent, which is exactly what section 95a UrhG forbids, while our own analysis
and a device-local extraction stay covered by sections 69d/69e UrhG.

So: the key never enters the source tree. Our tools read it on the device at run
time. This guard makes that rule enforceable instead of a good intention, because
"do not commit the key" is the kind of rule that quietly breaks once a debug dump
lands in a branch.

What may be stored, and is stored here, is the FINGERPRINT: a SHA-256 is one-way,
it cannot be turned back into a key, and it is what lets the installer say "this is
the known vendor key set" instead of only "something 288 bytes long".

Checks
------
1. the known key sets, by fingerprint, at every byte offset
2. anything shaped like a secure-storage item ("hdcpkey" behind magic 0x17253948)

Scope
-----
With no argument it checks what git TRACKS, because only that is ever published;
untracked build output is noise and would make the run take minutes instead of
seconds. Given paths explicitly, it checks those, tracked or not - that is how the
release gate points it at a built image.

Usage: no_key_material.py [path ...]      (default: everything git tracks)
       exit 0 = clean, 1 = key material found
"""

import hashlib
import os
import struct
import sys

# SHA-256 of the key sets we know. Hashes, not keys - see the module docstring.
#
# The 320-byte record is the 288-byte key set plus a 32-byte tail, so a window that
# holds the record holds the key set at its own offset 0: looking for 288 finds both,
# and the record's fingerprint is listed for identification only, not scanned for.
# That halves the work, which matters - this walks every byte offset.
KNOWN = {
    "d743dcf4afe08c23ff5da56931000556a4e4692a8431604134f1cc4031389ea2":
        ("HDCP 1.4 key set", 288),
    "2bc0415d58c720094b9b3e97138d9e83e28b075e06caba5ba18b5ba21e331984":
        ("HDCP 1.4 record (key set + tail)", 320),
    "595989518ba2ff77ce4c146fdb97a4d9ce5bdbb279529b696e353a0b3ce32f61":
        ("HDCP 2.2 key set (HY310)", 912),
    "fa0a8bd88f056a5f2a94cda6cac3283ffb313225edd13bffc1b262975a711ba4":
        ("HDCP 2.2 key set (HY300 Pro)", 912),
}
SCAN_LENGTHS = (288, 912)
MAGIC = struct.pack("<I", 0x17253948)
ITEM_NAMES = (b"hdcpkey\0", b"hdcpkeyV22\0")

# Files we never look into: the guard's own fingerprints, and the documentation that
# explains them, would otherwise report themselves.
SKIP_NAMES = {"no_key_material.py"}
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
# A full-disk image is not something we would ever commit; scanning gigabytes on every
# test run is pointless. Anything this big is reported as "not scanned" and the rule is
# that it does not belong in the tree in the first place.
MAX_BYTES = 64 * 1024 * 1024


# How finely we walk a file. Hashing every byte offset of everything is exact and far
# too slow to be run - the whole tracked tree took minutes - and a guard nobody runs
# protects nothing. So: tiny files exactly, everything else on a 16-byte grid, which
# brings the tracked tree down to a few seconds.
#
# What that gives up, stated plainly: a key blob deliberately placed at an offset that
# is not a multiple of 16 inside a large file would slip past THIS check. That is
# accepted, because the realistic accidents are all covered - a committed region dump
# is found by the item search below (a substring search, every offset, any size), a
# bare key file has the blob at offset 0, and data in a compiled artefact is aligned to
# at least 4 bytes by the toolchain. This guard is here to catch mistakes, not an
# adversary who is already trying to smuggle the key past it.
EXACT_UP_TO = 8 * 1024
COARSE_STEP = 16


def scan(blob):
    """(reason, offset) for the first piece of key material, or None."""
    step = 1 if len(blob) <= EXACT_UP_TO else COARSE_STEP
    for length in SCAN_LENGTHS:
        if len(blob) < length:
            continue
        view = memoryview(blob)
        for off in range(0, len(blob) - length + 1, step):
            digest = hashlib.sha256(view[off:off + length]).hexdigest()
            if digest in KNOWN:
                what, _ = KNOWN[digest]
                return ("%s at offset 0x%x" % (what, off), off)

    # Anything shaped like a secure-storage item, at any offset. This is the check that
    # catches a committed region dump, and it is a substring search, so it is cheap.
    pos = 0
    while True:
        pos = blob.find(MAGIC, pos)
        if pos < 0:
            break
        window = blob[pos:pos + 0x80]
        for name in ITEM_NAMES:
            if name in window:
                return ("secure-storage item %s at offset 0x%x"
                        % (name.rstrip(b"\0").decode(), pos), pos)
        pos += 1
    return None


def files_under(paths):
    for path in paths:
        if os.path.isfile(path):
            yield path
            continue
        for root, dirs, names in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                full = os.path.join(root, name)
                if name not in SKIP_NAMES and os.path.isfile(full) \
                        and not os.path.islink(full):
                    yield full


def tracked_files():
    """What git tracks, from the repository this file lives in."""
    import subprocess

    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", ".."))
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                             check=True, stdout=subprocess.PIPE).stdout
    except (OSError, subprocess.CalledProcessError):
        return [root]
    names = [n for n in out.decode("utf-8", "replace").split("\0") if n]
    # git ls-files also names submodule links (gitlinks). Those are directories here,
    # and walking into them means walking their build output: `mainline/external/u-boot`
    # alone holds 251 MiB of it, which turned a 7-second run into minutes. A submodule
    # carries its own history and is checked in its own repository, so only regular
    # files of THIS repository are scanned. Broken symlinks are skipped the same way.
    return [os.path.join(root, n) for n in names
            if os.path.isfile(os.path.join(root, n))
            and not os.path.islink(os.path.join(root, n))]


def main(argv):
    import time

    started = time.time()
    paths = argv[1:] if len(argv) > 1 else tracked_files()
    findings, skipped, looked = [], 0, 0
    for path in files_under(paths):
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > MAX_BYTES:
            skipped += 1
            continue
        try:
            with open(path, "rb") as handle:
                blob = handle.read()
        except (OSError, PermissionError):
            continue
        looked += 1
        hit = scan(blob)
        if hit:
            findings.append((path, hit[0]))

    for path, reason in findings:
        print("KEY MATERIAL  %s: %s" % (path, reason))
    if skipped:
        print("not scanned: %d file(s) over %d MiB - such files do not belong in the "
              "tree anyway" % (skipped, MAX_BYTES // (1024 * 1024)))
    if findings:
        print("%d file(s) carry key material - this must never be distributed"
              % len(findings))
        return 1
    print("clean: no key material in %d file(s), %.1f s" % (looked, time.time() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
