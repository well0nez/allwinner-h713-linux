# SPDX-License-Identifier: GPL-2.0
"""The one module that mounts something -- the executor of layout v4 (P-layout-v4).

What goes WHERE is pure Python in `h713.install`; here are the four steps that need a Linux
kernel and root: mount, copy, chmod/chown, umount. One code path for both directions -- the
source is always a file (or a device) plus a byte window, so the working copy of the image and
a partition of the device in front of us take the same command, only `ro` differs. The kernel's
ext4 is an implementation nobody has to take our word for, and it takes a vendor file of any
length: layout v3 wrote them into placeholders of a measured size, and a firmware whose files
are bigger (issue #1, HY300 Pro) had nowhere to put them.
"""

from __future__ import annotations

import collections
import contextlib
import os
import subprocess
import sys
import tempfile

from .log import console

# One file to put into a file system: where it goes, where the bytes come from (`data` in hand
# or `source` as a path on the PC), how it must look, and the mode for directories made on the way.
Entry = collections.namedtuple("Entry", "path data source mode uid gid dir_mode",
                               defaults=(None, None, 0o644, 0, 0, 0o755))

TIMEOUT = 120                 # seconds for one mount/umount -- a hung mount must not hang us


def unusable():
    """Why this machine cannot copy through a mount -- or None when it can. A question and not
    an exception, so the caller says it in its own words (`--no-write` never even asks)."""
    if sys.platform != "linux":
        return ("the files are copied into the image through a mount, and mounting an ext4 "
                "needs Linux -- this is %s" % sys.platform)
    if os.geteuid() != 0:        # Linux only: os.geteuid does not exist on Windows
        return "mounting the image needs root -- start h713-install with sudo"
    return None


def _run(command):
    r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=TIMEOUT)
    if r.returncode != 0:
        said = r.stdout.decode("utf-8", "replace").strip() or "exit %d" % r.returncode
        raise RuntimeError("%s: %s" % (" ".join(command), said))


def _leftovers(source):
    """What of `source` is mounted right now -- itself, or a loop device carrying it. A run cut
    off between mount and umount leaves exactly this; taking it over silently would write into
    a file system somebody else holds open."""
    real, rows = os.path.realpath(source), []
    holders = {real}
    for name in sorted(os.listdir("/sys/block")):
        try:
            with open("/sys/block/%s/loop/backing_file" % name) as f:
                if os.path.realpath(f.read().strip()) == real:
                    holders.add("/dev/" + name)
        except OSError:
            continue
    try:
        with open("/proc/self/mounts") as f:
            rows = [line.split()[:2] for line in f if len(line.split()) > 1]
    except OSError:
        pass
    return ["%s on %s" % (d, p) for d, p in rows if os.path.realpath(d) in holders]


def _inside(point, path):
    """`path` out of the table, resolved under the mount point -- and never outside it."""
    whole = os.path.normpath(os.path.join(point, path.lstrip("/")))
    if whole != point and not whole.startswith(point + os.sep):
        raise RuntimeError("%s does not lie inside the file system" % path)
    return whole


@contextlib.contextmanager
def mounted(source, offset, size, read_only, log=console):
    """The ext4 at `offset`/`size` inside `source`, on a private mount point of our own for the
    length of the block. Always unmounted again; `umount` on the mount point frees the loop
    device by itself, so none is allocated by hand."""
    why = unusable()
    if why:
        raise RuntimeError(why)
    left = _leftovers(source)
    if left:
        raise RuntimeError("%s is still mounted (%s) -- a run was cut off there. Free it with "
                           "`umount %s` and start again; nothing of it is reused."
                           % (source, ", ".join(left), left[0].split(" on ")[1]))
    options = "loop,offset=%d,sizelimit=%d" % (offset, size)
    point = tempfile.mkdtemp(prefix="h713-mount-")
    command = ["mount", "-t", "ext4", "-o", ("ro," + options) if read_only else options,
               source, point]
    log.info("  %s" % " ".join(command))
    try:
        _run(command)
        yield point
    finally:
        try:
            if os.path.ismount(point):
                _run(["umount", point])
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            raise RuntimeError("%s is still mounted at %s (%s) -- `umount %s` frees it"
                               % (source, point, e, point))
        os.rmdir(point)


def _make_way(point, path, mode, uid, gid, log):
    """The directories above `path`: the image brings the ones it knows along, a firmware with
    one ours does not have gets it made here, with the mode it must have."""
    here = point
    for part in path.strip("/").split("/")[:-1]:
        here = _inside(here, part)
        if not os.path.isdir(here):
            os.mkdir(here)
            os.chmod(here, mode)       # mkdir's mode goes through the umask, chmod does not
            os.chown(here, uid, gid)
            log.info("  made %s" % here[len(point):])


def copy_in(image_path, offset, size, entries, log=console):
    """Write `entries` into the ext4 at `offset`/`size` inside `image_path`; returns how many
    files. Nothing is padded or trimmed: every file arrives with the length it has."""
    for e in entries:
        if (e.data is None) == (e.source is None):
            raise RuntimeError("%s: a file comes either as bytes or from a path" % e.path)
    with mounted(image_path, offset, size, False, log) as point:
        for e in entries:
            _make_way(point, e.path, e.dir_mode, e.uid, e.gid, log)
            data = e.data
            if data is None:
                with open(e.source, "rb") as f:
                    data = f.read()
            whole = _inside(point, e.path)
            with open(whole, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(whole, e.mode)
            os.chown(whole, e.uid, e.gid)
            log.ok("%-52s %8d bytes" % (e.path, len(data)))
        os.sync()
    return len(entries)


def copy_out(source, offset, size, paths, log=console):
    """Read `paths` out of the ext4 at `offset`/`size` inside `source` (the working copy, or the
    device itself), mounted read-only. Returns {path: bytes} for the ones that are there -- who
    may be absent is the plan's decision, not ours."""
    out = {}
    with mounted(source, offset, size, True, log) as point:
        for path in paths:
            whole = _inside(point, path)
            if os.path.isfile(whole):
                with open(whole, "rb") as f:
                    out[path] = f.read()
    return out
