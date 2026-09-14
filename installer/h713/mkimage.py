# -*- coding: utf-8 -*-
"""Build and check the installable image for the HY310/H713 projector.

Out of the available building blocks (SPL, U-Boot proper, kernel FIT, the two
ext4 file systems) `build` makes an image following layout v3 (doku/109 §2),
plus the offset table, a manifest, checksums and a README file; `check`
validates a finished image against its table. The trees for the two ext4 file
systems come from `tree_boot`/`tree_rootfs` -- what is in them and where it
goes is `h713.layout`.

Moved from hy310-mkimage.py (M:408-1152), stage 1 (doku/121); stage 3 made
every printed line and the README English and renamed the README file from
<stem>-LIESMICH.txt to <stem>-README.txt. The table keys are unchanged
(format string "hy310-abbild-tabelle" included) until stage 4. The CLI
(`main()`, the argument parser and the tool docstring shown as its epilog)
stays in installer/h713-mkimage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import time
import zlib

from h713.blockdev import LOCK_FIRST, LOCK_LAST
from h713.fs.ext4 import Ext4
from h713.gpt import build_layout_gpt, check_gpt
from h713.layout import (
    DISK_SECTORS, ENV_BYTES, FIRST_USABLE, GPT_ARRAY_SECTORS, GPT_ENTRY_COUNT,
    KERNEL_FIT, LBA_BOOT, LBA_ENV, LBA_ROOTFS, LBA_SPL, LBA_UBOOT,
    PART_A_LBA, PART_A_SECTORS, PART_B_LBA, PART_C_LBA, PART_C_SECTORS,
    PARTITIONS, PLACEHOLDERS, ROOTFS_PERMISSIONS, SECTOR, USER_DIRECTORIES,
    USER_PLACEHOLDERS, filling, is_user_placeholder, pattern,
)
from h713.log import Console
from h713.source import FileSource
from h713.util import mib, relpath_or_abs, sha256_file

# hy310-mkimage's own look (its old class K), kept byte for byte -- doku/121 stage 1.
console = Console(style="mkimage")

# Version of the h713-mkimage tool (M:70), not the version of the package
# (h713.VERSION): it goes into the table as "werkzeug" and the installer reads
# tables that were written with it.
VERSION = "0.1"


def _block_map(fs, ino, inode):
    """The block map of an inode: [(logical start, blocks, physical start)].

    `Ext4._karte` (X:1415) is a private helper, so api-h713.md does not fix an
    English name for it; accept both spellings until B3 is merged (REPORT.md).
    """
    fn = getattr(fs, "_map", None)
    if fn is None:
        fn = fs._karte
    return fn(ino, inode)


# ---------------------------------------------------------------- Trees

def tree_boot(directory, fit=None, log=console):
    """The file tree hy310-boot.ext4 is made from."""
    os.makedirs(os.path.join(directory, "mips"), exist_ok=True)
    n = 0
    if fit:
        target = os.path.join(directory, KERNEL_FIT)
        with open(fit, "rb") as src, open(target, "wb") as dst:
            while True:
                b = src.read(8 << 20)
                if not b:
                    break
                dst.write(b)
        head = open(target, "rb").read(4)
        if head != b"\xd0\x0d\xfe\xed":
            raise SystemExit("%s carries no FIT identifier d00dfeed" % fit)
        log.ok("%-34s %9d bytes (real)" % (KERNEL_FIT, os.path.getsize(target)))
        n += 1
    for name, size, part, path in PLACEHOLDERS:
        if part != "hy310-boot":
            continue
        target = os.path.join(directory, path.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as dst:
            dst.write(pattern(name, size))
        n += 1
    log.ok("%d files in %s" % (n, directory))
    return n


def tree_rootfs(directory, log=console):
    """Only the placeholders that belong into the rootfs -- as an overlay over
    the unpacked tree from hy310-rootfs.tar."""
    n = 0
    for name, size, part, path in PLACEHOLDERS:
        if part != "hy310-rootfs":
            continue
        target = os.path.join(directory, path.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as dst:
            dst.write(pattern(name, size))
        n += 1
    # The user placeholders: modes set explicitly, not left to the umask.
    # The owner is whoever writes the tree -- so that has to be root
    # (mkimage-inputs.sh checks it); step 5 checks it in the ext4 afterwards.
    for path, mode in USER_DIRECTORIES:
        target = os.path.join(directory, path.lstrip("/").replace("/", os.sep))
        os.makedirs(target, exist_ok=True)
        os.chmod(target, mode)
    for name, size, part, path, mode in USER_PLACEHOLDERS:
        if part != "hy310-rootfs":
            continue
        target = os.path.join(directory, path.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as dst:
            dst.write(filling(name, size))
        os.chmod(target, mode)
        n += 1
    log.ok("%d placeholders in %s (%d of them for the user to fill: %s)"
           % (n, directory, len(USER_PLACEHOLDERS),
              ", ".join(p for _n, _s, _t, p, _m in USER_PLACEHOLDERS)))
    return n


# ---------------------------------------------------------------- ext4 offsets

def ext4_offsets(image, paths, log=console):
    """Find the byte offset of the data of every path in the ext4 image.

    Condition: the file has to be ONE contiguous piece, otherwise a single
    (offset, length) would be wrong. That is checked, not assumed. As a
    counter-check every file is read once through the ext4 reader and once raw
    at the computed offset, and the two are compared.
    """
    from pathlib import Path
    q = FileSource(Path(image))
    fs = Ext4(q, label=os.path.basename(image))
    bs = fs.block_size
    raw = open(image, "rb")
    try:
        out = {}
        for path in paths:
            ino = fs.path_inode(path)
            if ino is None:
                raise SystemExit("%s: %s does not exist" % (image, path))
            inode = fs.inode(ino)
            size = inode["groesse"]
            block_map = _block_map(fs, ino, inode)
            if not block_map:
                raise SystemExit("%s: %s has no data blocks" % (image, path))
            lb0, _n0, pb0 = block_map[0]
            if lb0 != 0:
                raise SystemExit("%s: %s starts with a hole" % (image, path))
            seen, expected_p = 0, pb0
            for lb, n, pb in block_map:
                if lb != seen or pb != expected_p:
                    raise SystemExit(
                        "%s: %s does not lie in one piece (%d fragments) -- a "
                        "single offset would be wrong" % (image, path, len(block_map)))
                seen += n
                expected_p += n
            if seen * bs < size:
                raise SystemExit("%s: %s has a hole at the end" % (image, path))
            off = pb0 * bs
            raw.seek(off)
            if raw.read(size) != fs.read(path):
                raise SystemExit("%s: %s -- the counter-check at offset %d failed"
                                 % (image, path, off))
            out[path] = (off, size)
        log.ok("%-22s block size %d, %d file(s) in one piece, counter-check equal"
               % (os.path.basename(image), bs, len(out)))
        return out
    finally:
        raw.close()


def ext4_check_permissions(image, expectation=ROOTFS_PERMISSIONS, log=console):
    """Look up owner and mode of a few files in the finished ext4.

    Why: mke2fs -d takes uid/gid/mode from the tree. If the tree is unpacked as
    a normal user, EVERYTHING belongs to uid 1000 afterwards -- /etc/shadow,
    /root, sshd's authorized_keys. The system still boots, but sshd refuses the
    key (StrictModes), and much else is wrong. That is exactly how it was in
    image v0.5 (11.09.2026). Which is why this aborts instead of warning.
    """
    from pathlib import Path
    fs = Ext4(FileSource(Path(image)), label=os.path.basename(image))
    problems = []
    for path, mode, uid, gid in expectation:
        ino = fs.path_inode(path)
        if ino is None:
            problems.append("%s is missing" % path)
            continue
        i = fs.inode(ino)
        actual = i["mode"] & 0o7777
        if (i["uid"], i["gid"]) != (uid, gid):
            problems.append("%s belongs to %d:%d instead of %d:%d" % (path, i["uid"], i["gid"], uid, gid))
        if mode is not None and actual != mode:
            problems.append("%s has mode %04o instead of %04o" % (path, actual, mode))
    if problems:
        for x in problems:
            log.error(x)
        raise SystemExit("%s: owner/permissions are wrong -- was the tree unpacked as "
                         "root? (run mkimage-inputs.sh in the container with "
                         "`podman exec -u root`)" % os.path.basename(image))
    log.ok("%-22s owner root:root and the modes checked (%d paths, among them /root/.ssh 0700, authorized_keys 0600)"
           % (os.path.basename(image), len(expectation)))


# ---------------------------------------------------------------- Building

def _copy(target_f, source, log=None):
    n = 0
    with open(source, "rb") as src:
        while True:
            b = src.read(8 << 20)
            if not b:
                break
            target_f.write(b)
            n += len(b)
    return n


def uboot_version(path):
    """Pull the version line out of a U-Boot or SPL image.

    On 10.09. an image went out with a U-Boot two commits old. It was missing
    `net.ifnames=0`, so the network interface was named after the MAC,
    `allow-hotplug eth0` never took hold and the device was not on the network.
    The builder now says on every run what it puts in, and writes it into the
    table -- an old state then shows up at once.
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    m = re.search(rb"U-Boot(?: SPL)? \d{4}\.\d{2}[-\w.+]*", raw)
    return m.group(0).decode("latin1") if m else None


def build(args, here=None):
    """`here`: the directory of the calling script (the installer directory, where
    mkimage-inputs.sh puts tmp/); the module's own directory when not given."""
    if here is None:
        here = os.path.dirname(os.path.abspath(__file__))
    # Project root: the next parent directory with mainline/build/build.sh --
    # holds in the working directory (analyse/release/arbeit/r0-fel) as well as
    # in the release repository (installer/ directly under the root),
    # doku/116 P3. If nothing is found: the old pattern.
    project_root = here
    while project_root != os.path.dirname(project_root) and not os.path.isfile(
            os.path.join(project_root, "mainline", "build", "build.sh")):
        project_root = os.path.dirname(project_root)
    if not os.path.isfile(os.path.join(project_root, "mainline", "build", "build.sh")):
        project_root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))

    def under_root(p):
        return os.path.join(project_root, p)

    # Defaults: what release/build-all.sh puts under mainline/build/out/. tftp/
    # was the place things were put by hand until v0.9 and stays only as a
    # fallback for when nothing is there.
    def building_block(name):
        p = under_root("mainline/build/out/" + name)
        return p if os.path.isfile(p) else under_root("tftp/" + name)
    spl = args.spl or building_block("spl-release.bin")
    ub = args.uboot or building_block("uboot-proper-release.bin")
    env = args.env or building_block("hy310-env-release.bin")
    boot = args.boot_ext4 or os.path.join(here, "tmp", "hy310-boot.ext4")
    root = args.rootfs_ext4 or os.path.join(here, "tmp", "hy310-rootfs-platz.ext4")
    for w, p in (("--spl", spl), ("--uboot", ub), ("--env", env),
                 ("--boot-ext4", boot), ("--rootfs-ext4", root)):
        if not os.path.isfile(p):
            raise SystemExit("%s: %s not found" % (w, p))

    target = os.path.abspath(args.out)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    stem = target[:-4] if target.lower().endswith(".img") else target
    base = os.path.basename(stem)
    a_file = stem + "-a-bootkette.img"
    b_file = stem + "-b-system.img"
    c_file = stem + "-c-gptkopie.img"
    t_file = stem + ".tabelle.json"

    # --- 1. check the sizes before anything is written
    console.step(1, "check the building blocks")
    n_spl, n_ub = os.path.getsize(spl), os.path.getsize(ub)
    v_spl, v_ub = uboot_version(spl), uboot_version(ub)
    for what, path, version in (("SPL", spl, v_spl), ("U-Boot", ub, v_ub)):
        if version:
            console.info("  %-7s %s  (%s)" % (what, version, os.path.basename(path)))
        else:
            console.warn("%s: no version identifier found in %s" % (what, path))
    n_boot, n_root = os.path.getsize(boot), os.path.getsize(root)
    if open(spl, "rb").read(12)[4:12] != b"eGON.BT0":
        raise SystemExit("%s carries no eGON.BT0 identifier -- that is not an SPL" % spl)
    if n_spl > 64 * SECTOR:
        raise SystemExit("the SPL is %d bytes, hy310-spl holds %d" % (n_spl, 64 * SECTOR))
    if n_ub > 10240 * SECTOR:
        raise SystemExit("U-Boot is %d bytes, hy310-uboot holds %d" % (n_ub, 10240 * SECTOR))
    if n_boot != 262144 * SECTOR:
        raise SystemExit("hy310-boot.ext4 is %d bytes, the partition has %d"
                         % (n_boot, 262144 * SECTOR))
    if n_root % SECTOR or n_root > 14991327 * SECTOR:
        raise SystemExit("hy310-rootfs.ext4 does not fit (%d bytes)" % n_root)
    # The environment: 64 KiB, a CRC32 (little-endian) over the rest in front --
    # that is how U-Boot reads it (env/mmc.c, CONFIG_ENV_SIZE=0x10000, one
    # copy). Until v0.8 a block of zeros was written here; U-Boot then reported
    # "bad CRC, using default environment" twice on every start, and every
    # installation wiped the stored environment (Marco, 12.09.: "das geht
    # nicht"). Now the built-in default of the U-Boot that ships with the image
    # comes along, out of `make u-boot-initial-env` + mkenvimage -- the same
    # values, but valid, and h713_gate=1 is expressly in there.
    n_env = os.path.getsize(env)
    if n_env != ENV_BYTES:
        raise SystemExit("%s is %d bytes, the environment has %d (CONFIG_ENV_SIZE)" % (env, n_env, ENV_BYTES))
    with open(env, "rb") as f:
        env_raw = f.read()
    env_crc = struct.unpack("<I", env_raw[:4])[0]
    if env_crc != (zlib.crc32(env_raw[4:]) & 0xffffffff):
        raise SystemExit("%s: the CRC32 in the header (%08x) does not fit the content -- not a U-Boot environment"
                         % (env, env_crc))
    env_entries = [e.decode("ascii", "replace") for e in env_raw[4:].split(b"\0") if e and e != b"\xff" * len(e)]
    env_gate = [e for e in env_entries if e.startswith("h713_gate=")]
    for w, p, n in (("SPL", spl, n_spl), ("U-Boot proper", ub, n_ub), ("environment", env, n_env),
                    ("hy310-boot.ext4", boot, n_boot), ("hy310-rootfs.ext4", root, n_root)):
        console.ok("%-16s %11d bytes  %s" % (w, n, relpath_or_abs(p, project_root)))
    console.info("  environment: %d entries, CRC %08x, %s" % (len(env_entries), env_crc,
                 ", ".join(env_gate) if env_gate else "NO h713_gate -- check it"))

    # --- 2. Piece A: GPT + SPL + U-Boot, LBA 0..12287
    console.step(2, "piece A -- boot chain (LBA %d..%d)" % (PART_A_LBA, PART_A_SECTORS - 1))
    gpt = build_layout_gpt()
    a = bytearray(PART_A_SECTORS * SECTOR)
    a[0:SECTOR] = gpt[0]
    a[SECTOR:2 * SECTOR] = gpt[1]
    a[2 * SECTOR:2 * SECTOR + len(gpt[2])] = gpt[2]
    with open(spl, "rb") as f:
        a[LBA_SPL * SECTOR:LBA_SPL * SECTOR + n_spl] = f.read()
    with open(ub, "rb") as f:
        a[LBA_UBOOT * SECTOR:LBA_UBOOT * SECTOR + n_ub] = f.read()
    with open(a_file, "wb") as f:
        f.write(bytes(a))
    console.ok("%s  %d bytes (%.0f MiB)" % (os.path.basename(a_file), len(a), mib(len(a))))

    # --- 3. Piece C: backup copy of the GPT at the end of the disk (finding S46 B7)
    console.step(3, "piece C -- backup copy of the GPT (LBA %d, %d sectors)"
                 % (PART_C_LBA, PART_C_SECTORS))
    c = bytearray(PART_C_SECTORS * SECTOR)
    back_arr = DISK_SECTORS - 1 - GPT_ARRAY_SECTORS
    c[(back_arr - PART_C_LBA) * SECTOR:(back_arr - PART_C_LBA) * SECTOR + len(gpt[back_arr])] = gpt[back_arr]
    c[(DISK_SECTORS - 1 - PART_C_LBA) * SECTOR:] = gpt[DISK_SECTORS - 1]
    with open(c_file, "wb") as f:
        f.write(bytes(c))
    console.ok("%s  %d bytes -- it also clears away leftovers of the old table"
               % (os.path.basename(c_file), len(c)))

    problems = check_gpt(bytes(a[:9 * SECTOR]), bytes(c))
    if problems:
        for x in problems:
            console.error(x)
        raise SystemExit("the GPT that was built is not in order")
    console.ok("GPT recomputed: CRCs, FirstUsable %d, %d entries, six partitions, "
               "backup copy matches" % (FIRST_USABLE, GPT_ENTRY_COUNT))

    # --- 4. Piece B: environment + rest of hy310-env (SPL parking space, empty)
    #        + hy310-boot + hy310-rootfs
    console.step(4, "piece B -- system (LBA %d ...)" % PART_B_LBA)
    with open(b_file, "wb") as f:
        f.write(env_raw)                                                # hy310-env: the environment, LBA 14336
        f.write(b"\0" * ((LBA_BOOT - PART_B_LBA) * SECTOR - n_env))     # rest of the partition (SPL parking space 14464), empty
        _copy(f, boot)
        _copy(f, root)
    n_b = os.path.getsize(b_file)
    want_b = (LBA_BOOT - PART_B_LBA) * SECTOR + n_boot + n_root
    assert n_b == want_b, (n_b, want_b)
    console.ok("%s  %d bytes (%.0f MiB)" % (os.path.basename(b_file), n_b, mib(n_b)))
    console.info("hy310-env carries the built-in default of the U-Boot that ships with the image (%s) -- valid from the first start"
                 % (", ".join(env_gate) if env_gate else "without h713_gate"))

    # --- 5. find the placeholder offsets
    console.step(5, "find the placeholders in the image")
    off_boot = ext4_offsets(boot, [p for _n, _g, t, p in PLACEHOLDERS if t == "hy310-boot"])
    off_root = ext4_offsets(root, [p for _n, _g, t, p in PLACEHOLDERS if t == "hy310-rootfs"] +
                            [p for _n, _g, t, p, _m in USER_PLACEHOLDERS if t == "hy310-rootfs"])
    ext4_check_permissions(root)
    base_boot = (LBA_BOOT - PART_B_LBA) * SECTOR
    base_root = (LBA_ROOTFS - PART_B_LBA) * SECTOR

    table, user, info = {}, {}, {}
    all_entries = [(n, g, t, p, "h713-extract") for n, g, t, p in PLACEHOLDERS] + \
                  [(n, g, t, p, "h713-install --ssh-key") for n, g, t, p, _m in USER_PLACEHOLDERS]
    for name, size, part, path, source in all_entries:
        if part == "hy310-boot":
            o, g = off_boot[path]
            o += base_boot
        else:
            o, g = off_root[path]
            o += base_root
        if g != size:
            raise SystemExit("%s: %d bytes in the file system, %d in the table"
                             % (name, g, size))
        (user if is_user_placeholder(name) else table)[name] = [o, g]
        info[name] = {
            "ziel": "%s:%s" % (part, path),
            "laenge": g,
            "lba": (PART_B_LBA * SECTOR + o) // SECTOR,
            "disk_offset": PART_B_LBA * SECTOR + o,
            "quelle": source,
            "fuellung": "zeilenumbrueche" if is_user_placeholder(name) else "muster",   # table keys/values: stage 4
            "sha256_muster": hashlib.sha256(filling(name, g)).hexdigest(),
        }
    console.ok("%d placeholders for h713-extract, %d bytes in all"
               % (len(table), sum(g for _o, g in table.values())))
    console.ok("%d placeholder(s) for the user: %s"
               % (len(user), ", ".join("%s (%d bytes, line breaks)" % (n, g)
                                       for n, (_o, g) in user.items())))

    # Counter-check: is the filling really at the computed offset in piece B?
    with open(b_file, "rb") as f:
        for name, (o, g) in list(table.items()) + list(user.items()):
            f.seek(o)
            if f.read(g) != filling(name, g):
                raise SystemExit("%s: the expected filling is not at offset %d" % (name, o))
    console.ok("all %d offsets counter-checked in piece B" % (len(table) + len(user)))

    # --- 6. check the hole
    console.step(6, "the locked range")
    pieces = [(a_file, PART_A_LBA), (b_file, PART_B_LBA), (c_file, PART_C_LBA)]
    for file_name, lba in pieces:
        end = lba + os.path.getsize(file_name) // SECTOR - 1
        if lba <= LOCK_LAST and end >= LOCK_FIRST:
            raise SystemExit("%s covers LBA %d..%d and so touches the "
                             "secure storage" % (file_name, lba, end))
    console.ok("no piece touches LBA %d..%d -- not even a dd by hand can hit the secure "
               "storage" % (LOCK_FIRST, LOCK_LAST))

    # --- 7. checksums, table, manifest, readme
    console.step(7, "table, manifest, README")
    piece_list = []
    for file_name, lba in pieces:
        n = os.path.getsize(file_name)
        piece_list.append({
            "datei": os.path.basename(file_name),
            "lba": lba,
            "sektoren": n // SECTOR,
            "bytes": n,
            "sha256": sha256_file(file_name),
            "dd": "dd if=%s of=/dev/sdX bs=512 seek=%d conv=fsync"
                  % (os.path.basename(file_name), lba),
        })
    data = {
        "format": "hy310-abbild-tabelle",
        "version": 1,
        "werkzeug": "h713-mkimage " + VERSION,     # key stays (stage 4), the tool is renamed in stage 3
        "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abbild": base,
        "sektorgroesse": SECTOR,
        "disk_sektoren": DISK_SECTORS,
        "layout": "v3 (doku/109 §2.2)",
        "partitionen": [{"name": n, "lba": l, "sektoren": s, "guid": g}
                        for n, l, s, g in PARTITIONS],
        "loch": {
            "lba": LOCK_FIRST,
            "sektoren": LOCK_LAST - LOCK_FIRST + 1,
            "partition": "hy310-keys",
            # The key stays German until stage 4; the prose is English from stage 3 on.
            "warum": ("secure storage: HDCP keys, the WLAN/BT MAC addresses and the "
                      "serial number. Device-specific, in no firmware image, not "
                      "restorable (doku/109 §2.3). That is why this range is in no "
                      "piece of the image."),
        },
        "teile": piece_list,
        "bausteine": {
            "spl": {"datei": relpath_or_abs(spl, project_root), "bytes": n_spl,
                    "sha256": sha256_file(spl), "lba": LBA_SPL,
                    "version": v_spl},
            "uboot": {"datei": relpath_or_abs(ub, project_root), "bytes": n_ub,
                      "sha256": sha256_file(ub), "lba": LBA_UBOOT,
                      "version": v_ub},
            "env": {"datei": relpath_or_abs(env, project_root), "bytes": n_env,
                    "sha256": sha256_file(env), "lba": LBA_ENV,
                    "crc32": "%08x" % env_crc, "eintraege": len(env_entries)},
            "boot_ext4": {"datei": relpath_or_abs(boot, project_root), "bytes": n_boot,
                          "sha256": sha256_file(boot), "lba": LBA_BOOT},
            "rootfs_ext4": {"datei": relpath_or_abs(root, project_root), "bytes": n_root,
                            "sha256": sha256_file(root), "lba": LBA_ROOTFS},
        },
        # Exactly the format that fill_placeholders() in h713.install expects:
        # name -> (byte offset, length), offset inside the file named under
        # "platzhalter_datei".
        "platzhalter_datei": os.path.basename(b_file),
        "platzhalter": table,
        # Same shape, different source: h713-install fills these from --ssh-key,
        # padded with line breaks. An installer that does not know about the key
        # leaves the file empty (line breaks only) -- valid.
        "platzhalter_nutzer": user,
        "platzhalter_info": info,
    }
    with open(t_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    console.ok(os.path.basename(t_file))

    sums = stem + ".sha256"
    with open(sums, "w", encoding="utf-8") as f:
        for t in piece_list:
            f.write("%s  %s\n" % (t["sha256"], t["datei"]))
        f.write("%s  %s\n" % (sha256_file(t_file), os.path.basename(t_file)))
    console.ok(os.path.basename(sums))

    # doku/121 stage 3: the README is English and is called <stem>-README.txt;
    # <stem>-LIESMICH.txt is not written any more.
    readme = stem + "-README.txt"
    with open(readme, "w", encoding="utf-8") as f:
        f.write(readme_text(data))
    console.ok(os.path.basename(readme))

    total = sum(t["bytes"] for t in piece_list)
    console.step(8, "done")
    console.info("three pieces, %.0f MiB in all (%.2f GB)" % (mib(total), total / 1e9))
    console.info("directory: %s" % directory)
    console.info("check with:  %s check %s"
                 % (os.path.basename(sys.argv[0]), relpath_or_abs(t_file, os.getcwd())))
    return 0


# ---------------------------------------------------------------- Checking

def check(table_file, log=console):
    directory = os.path.dirname(os.path.abspath(table_file))
    with open(table_file, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("format") != "hy310-abbild-tabelle":
        raise SystemExit("%s is not an image table" % table_file)
    bad = 0

    log.step(1, "pieces: size and checksum")
    pieces = {}
    for t in d["teile"]:
        p = os.path.join(directory, t["datei"])
        if not os.path.isfile(p):
            log.error("%s is missing" % t["datei"])
            bad += 1
            continue
        n = os.path.getsize(p)
        if n != t["bytes"]:
            log.error("%s is %d bytes, expected %d" % (t["datei"], n, t["bytes"]))
            bad += 1
            continue
        h = sha256_file(p)
        if h != t["sha256"]:
            log.error("%s: sha256 %s..., expected %s..." % (t["datei"], h[:16], t["sha256"][:16]))
            bad += 1
            continue
        pieces[t["datei"]] = (p, t["lba"], n)
        log.ok("%-34s LBA %-9d %11d bytes  %s..." % (t["datei"], t["lba"], n, h[:16]))

    log.step(2, "the locked range (secure storage)")
    first = d["loch"]["lba"]
    last = first + d["loch"]["sektoren"] - 1
    if (first, last) != (LOCK_FIRST, LOCK_LAST):
        log.error("the table says LBA %d..%d, this tool knows %d..%d"
                  % (first, last, LOCK_FIRST, LOCK_LAST))
        bad += 1
    touched = False
    for name, (p, lba, n) in pieces.items():
        end = lba + n // SECTOR - 1
        if lba <= last and end >= first:
            log.error("%s covers LBA %d..%d and touches the secure storage"
                      % (name, lba, end))
            touched = True
            bad += 1
    if not touched:
        log.ok("no piece touches LBA %d..%d -- the range stays as it is"
               % (first, last))

    log.step(3, "partition table")
    a = [x for x in d["teile"] if x["lba"] == 0]
    c = [x for x in d["teile"] if x["lba"] == DISK_SECTORS - 33]
    if not a or a[0]["datei"] not in pieces:
        log.error("no piece at LBA 0 -- the GPT cannot be checked")
        bad += 1
    else:
        head = open(pieces[a[0]["datei"]][0], "rb").read(9 * SECTOR)
        cbytes = open(pieces[c[0]["datei"]][0], "rb").read() if c and c[0]["datei"] in pieces else None
        problems = check_gpt(head, cbytes, d["disk_sektoren"])
        for x in problems:
            log.error(x)
        bad += len(problems)
        if not problems:
            log.ok("the CRCs match, FirstUsableLBA %d, %d entries, six partitions"
                   % (FIRST_USABLE, GPT_ENTRY_COUNT))
            log.ok("the backup copy at the end of the disk is there and equal (finding S46 B7)")

    log.step(4, "placeholders")
    pd = d["platzhalter_datei"]
    if pd not in pieces:
        log.error("%s is missing -- the placeholders cannot be checked" % pd)
        return 1
    path, plba, pn = pieces[pd]
    unfilled, filled, broken = 0, 0, 0
    both = dict(d["platzhalter"])
    both.update(d.get("platzhalter_nutzer", {}))
    with open(path, "rb") as f:
        for name in sorted(both):
            off, length = both[name]
            info = d.get("platzhalter_info", {}).get(name, {})
            if off < 0 or off + length > pn:
                log.error("%s: offset %d + %d lies outside %s"
                          % (name, off, length, pd))
                broken += 1
                continue
            disk = plba * SECTOR + off
            if info.get("disk_offset") not in (None, disk):
                log.error("%s: disk_offset in the table does not fit the piece" % name)
                broken += 1
                continue
            lock_from, lock_to = first * SECTOR, (last + 1) * SECTOR
            if disk < lock_to and disk + length > lock_from:
                log.error("%s lies inside the locked range" % name)
                broken += 1
                continue
            f.seek(off)
            b = f.read(length)
            if b == filling(name, length):
                unfilled += 1
            elif info.get("sha256_muster") and \
                    hashlib.sha256(b).hexdigest() == info["sha256_muster"]:
                unfilled += 1
            else:
                filled += 1
    log.ok("%d placeholders checked: %d unfilled (the filling is in place), %d already filled"
           % (len(both), unfilled, filled))
    if broken:
        log.error("%d placeholders are wrong" % broken)
        bad += broken
    if filled:
        log.warn("this image is no longer the one to hand out -- it carries "
                 "device-specific data and should not be passed on")

    log.step(5, "result")
    if bad:
        log.error("%d complaint(s)" % bad)
        return 1
    log.ok("everything in order")
    return 0


# ---------------------------------------------------------------- README

# Wording from doku/110-plan-installationsweg.md section 9, or rather from the box
# at the very top of it. doku/110 section 9: "Der Kasten oben ist keine Formsache
# und darf nicht wegredigiert werden." -- the box at the top is not a formality and
# must not be edited away. Stage 3 translates it; not a word of its content changed.
BETA_WARNING = """\
 ! What every user has to be told before the first step

 This is a beta. Not in the sense of "a few rough edges", but: it can go wrong,
 and then there is a device standing there that does not start any more.

 So this holds, without exception and in this order:

 1. Make a full dump. Not the small one -- the full one, 7.3 GB, 17 minutes.
    With it you put your device back exactly the way it was.
 2. Or have the matching manufacturer firmware ready before you start.
    Do not go looking for it once you are stuck.
 3. Only then begin.

 Whoever skips both risks a device with no way back. FEL mode saves the boot
 chain, but it restores no data that nobody backed up.
"""


def readme_text(d):
    lines = []
    b = lines.append
    b("HY310/H713 projector -- image %s" % d["abbild"])
    b("=" * (31 + len(d["abbild"])))
    b("")
    b("Built on %s with %s." % (d["erzeugt"], d["werkzeug"]))
    b("")
    b("-" * 78)
    b(BETA_WARNING.rstrip())
    b("-" * 78)
    b("")
    b("")
    b("What is here")
    b("------------")
    b("")
    b("The image consists of THREE files. That is not an oversight but the heart")
    b("of the matter -- see the next section.")
    b("")
    for t in d["teile"]:
        b("  %-34s %11d bytes   from sector %d" % (t["datei"], t["bytes"], t["lba"]))
    b("  %-34s             where the placeholders lie" % (d["abbild"] + ".tabelle.json"))
    b("  %-34s             checksums" % (d["abbild"] + ".sha256"))
    b("")
    b("")
    b("Why three files and not one")
    b("---------------------------")
    b("")
    b("Between pieces A and B there is a gap: sectors %d to %d,"
      % (d["loch"]["lba"], d["loch"]["lba"] + d["loch"]["sektoren"] - 1))
    b("that is 1 MiB. The secure storage of your device sits there:")
    b("")
    b("  * the HDCP keys (without them no protected picture over HDMI)")
    b("  * the MAC addresses of WLAN and Bluetooth")
    b("  * the serial number")
    b("")
    b("This data exists ONLY on your device. It is in no firmware image, not even")
    b("in the manufacturer's, and nobody can rebuild it. Whoever overwrites it has")
    b("lost it for good.")
    b("")
    b("A single continuous image would cover it with zeros while writing.")
    b("That is why the range is in none of the three files. You cannot hit it at")
    b("all -- not with a dd by hand either, and not if you forget a command.")
    b("")
    b("")
    b("Installing")
    b("----------")
    b("")
    b("Put the device into FEL mode (hold the reset button, plug the power in),")
    b("then start the drive share with h713-install. After that the eMMC is an")
    b("ordinary USB drive.")
    b("")
    b("The comfortable way -- h713-install does dump, extraction and writing:")
    b("")
    b("    h713-install install %s.tabelle.json \\" % d["abbild"])
    b("                 --uboot u-boot-sunxi-with-spl.bin")
    b("")
    b("The way by hand, once the eMMC shows up as /dev/sdX. ALL THREE commands,")
    b("in this order, and check /dev/sdX twice beforehand:")
    b("")
    for t in d["teile"]:
        b("    dd if=%s of=/dev/sdX bs=512 seek=%d conv=fsync"
          % (t["datei"], t["lba"]))
    b("")
    b("(Piece B is faster with bs=1M seek=7 -- the same target, because sector")
    b("%d is exactly 7 MiB.)" % PART_B_LBA)
    b("")
    b("Afterwards pull the power and plug it in again.")
    b("")
    b("")
    b("What is still missing afterwards")
    b("--------------------------------")
    b("")
    b("The image holds %d placeholders: files of the right size, but with a fill"
      % len(d["platzhalter"]))
    b("pattern instead of content. They are the parts that belong to the")
    b("manufacturer and that we may not hand out:")
    b("")
    b("  * 19 display artefacts (mips/) -- without them the picture stays black")
    b("  * 3 firmware files (ARISC, EDID, MSP patch)")
    b("  * 8 PQ files (picture tuning)")
    b("  * 13 WLAN firmware files (aic8800)")
    b("")
    b("They come out of your own device: h713-extract reads them from the full")
    b("dump you pulled beforehand, and h713-install writes them to the places")
    b("listed in %s.tabelle.json -- on the PC, before anything" % d["abbild"])
    b("goes onto the eMMC at all.")
    b("")
    b("As long as they are not filled the system does start, but without a picture.")
    b("")
    b("One more placeholder is yours: /root/.ssh/authorized_keys. In the image the")
    b("file is empty (4096 line breaks). With")
    b("")
    b("    h713-install install ... --ssh-key ~/.ssh/id_ed25519.pub")
    b("")
    b("your public SSH key goes in, and you get onto the device over ssh as root.")
    b("Without that switch only the serial console is left (password login is")
    b("off). No key is ever handed out with the image.")
    b("")
    b("")
    b("If something goes wrong")
    b("-----------------------")
    b("")
    b("Do NOT pull the power and hope. Put the device into FEL mode (hold reset,")
    b("plug the power in) and start over -- the boot chain is always reachable")
    b("from there. If you have a full dump, h713-install restore puts it back.")
    b("")
    return "\n".join(lines) + "\n"
