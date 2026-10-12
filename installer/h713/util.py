"""Small shared helpers: sizes, durations, hashes, hexdump, crc32."""

from __future__ import annotations

import hashlib
import os
import time
import zlib

SECTOR = 512          # bytes per eMMC sector; the one definition for the whole package


def mib(b):
    return b / 2**20


def duration(seconds):
    if seconds < 90:
        return "%.0f s" % seconds
    return "%.0f min" % (seconds / 60)


def relpath_or_abs(p, base):
    """Relative to the project root when that works -- under Windows paths
    live on different drives, and then relpath raises."""
    try:
        return os.path.relpath(p, base)
    except ValueError:
        return os.path.abspath(p)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path, chunk: int = 8 << 20, log=None) -> str:
    h = hashlib.sha256()
    n = 0
    t0 = time.time()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
            n += len(b)
    if log:
        log.info(f"sha256 over {n} B in {time.time() - t0:.1f} s")
    return h.hexdigest()


def hexdump_short(b: bytes, n: int = 16) -> str:
    return " ".join(f"{x:02x}" for x in b[:n])


def crc32(b: bytes) -> int:
    return zlib.crc32(b) & 0xFFFFFFFF


def sudo_owner():
    """(uid, gid) of the user who ran this under sudo, or None: not root, not under sudo, sudo from root, or no
    os.geteuid (Windows)."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return None
    uid, gid = os.environ.get("SUDO_UID", ""), os.environ.get("SUDO_GID", "")
    if not (uid.isdigit() and gid.isdigit()) or int(uid) == 0:
        return None
    return int(uid), int(gid)


def give_back(roots, since, existed, owner=None):
    """What this run made under <roots> belongs to the user who ran sudo, not to root (TODO 5.11, Marco 12.10.2026:
    the dump is the user's own, under their own account). Only what is root's and changed since <since> - the run
    itself - and a root itself only when it did not exist before the run (existed: {root: bool}): a directory
    named by mistake (/root, /etc) keeps its owner, and nothing older than the run is touched. Symbolic links
    are neither followed nor changed. Returns (given, failed); a file system without owners (FAT on a stick)
    counts as failed and stops nothing."""
    owner = owner or sudo_owner()
    if owner is None:
        return 0, 0
    given = failed = 0
    seen = set()

    def one(p, is_root=False):
        nonlocal given, failed
        try:
            st = os.lstat(p)
        except OSError:
            return
        if st.st_uid != 0 or (is_root and existed.get(p, True)) or (not is_root and st.st_ctime < since):
            return
        if os.path.islink(p):
            return
        try:
            os.chown(p, owner[0], owner[1], follow_symlinks=False)
            given += 1
        except OSError:
            failed += 1

    for root in roots:
        if not root or root in seen or not os.path.lexists(root):
            continue
        seen.add(root)
        one(root, is_root=True)
        if os.path.isdir(root) and not os.path.islink(root):
            for top, dirs, files in os.walk(root):
                for name in dirs + files:
                    one(os.path.join(top, name))
    return given, failed
