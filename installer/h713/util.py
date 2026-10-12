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


def start_state(path):
    """How a place a run may write to stood before the run (give_back): "new" (not there), "ours" (a folder that
    was empty or holds a dump of ours, MANIFEST.json) or "foreign" (anything else - a shared folder, a file)."""
    if not os.path.lexists(path):
        return "new"
    if os.path.isdir(path) and not os.path.islink(path) and \
            (not os.listdir(path) or os.path.isfile(os.path.join(path, "MANIFEST.json"))):
        return "ours"
    return "foreign"


def give_back(roots, since, state, owner=None):
    """What this run made under <roots> belongs to the user who ran sudo, not to root (TODO 5.11, Marco 12.10.2026:
    the dump is the user's own, under their own account). state: {root: start_state(root)} taken before the run.

    A "new" root - the run made it - goes with everything in it; an "ours" folder keeps its owner and gives up
    what in it is root's and changed since <since>, the run itself; a "foreign" one is not touched at all, so a
    folder named by mistake (/root, /tmp, a Downloads folder) keeps its owner and so does whatever another
    program put there meanwhile. Symbolic links are neither followed nor changed. Returns (given, failed); a file
    system without owners (FAT on a stick) counts as failed and stops nothing."""
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
        if st.st_uid != 0 or os.path.islink(p) or (not is_root and st.st_ctime < since):
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
        how = state.get(root, "foreign")
        if how == "foreign":
            continue
        if how == "new":
            one(root, is_root=True)
        if os.path.isdir(root) and not os.path.islink(root):
            for top, dirs, files in os.walk(root):
                for name in dirs + files:
                    one(os.path.join(top, name))
    return given, failed
