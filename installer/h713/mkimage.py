# -*- coding: utf-8 -*-
"""Build and check the installable image for the HY310/H713 projector.

Out of the available building blocks (SPL, U-Boot proper, kernel FIT, the two
ext4 file systems) `build` makes an image following layout v3 (doku/109 §2),
plus the offset table, a manifest, checksums and a readme file; `check`
validates a finished image against its table. The trees for the two ext4 file
systems come from `tree_boot`/`tree_rootfs` -- what is in them and where it
goes is `h713.layout`.

Moved from hy310-mkimage.py (M:408-1152), stage 1 (doku/121). The CLI
(`main()`, the argument parser and the tool docstring shown as its epilog)
stays in installer/hy310-mkimage.py.
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
from h713.log import console
from h713.source import FileSource
from h713.util import mib, relpath_or_abs, sha256_file

# Version of the hy310-mkimage tool (M:70), not the version of the package
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
            raise SystemExit("%s traegt keine FIT-Kennung d00dfeed" % fit)
        log.ok("%-34s %9d Byte (echt)" % (KERNEL_FIT, os.path.getsize(target)))
        n += 1
    for name, size, part, path in PLACEHOLDERS:
        if part != "hy310-boot":
            continue
        target = os.path.join(directory, path.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as dst:
            dst.write(pattern(name, size))
        n += 1
    log.ok("%d Dateien in %s" % (n, directory))
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
    # (mkimage-eingaben.sh checks it); step 5 checks it in the ext4 afterwards.
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
    log.ok("%d Platzhalter in %s (davon %d vom Nutzer zu fuellen: %s)"
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
                raise SystemExit("%s: %s gibt es nicht" % (image, path))
            inode = fs.inode(ino)
            size = inode["groesse"]
            block_map = _block_map(fs, ino, inode)
            if not block_map:
                raise SystemExit("%s: %s hat keine Datenbloecke" % (image, path))
            lb0, _n0, pb0 = block_map[0]
            if lb0 != 0:
                raise SystemExit("%s: %s beginnt mit einem Loch" % (image, path))
            seen, expected_p = 0, pb0
            for lb, n, pb in block_map:
                if lb != seen or pb != expected_p:
                    raise SystemExit(
                        "%s: %s liegt nicht am Stueck (%d Fragmente) -- ein "
                        "einzelner Offset waere falsch" % (image, path, len(block_map)))
                seen += n
                expected_p += n
            if seen * bs < size:
                raise SystemExit("%s: %s hat ein Loch am Ende" % (image, path))
            off = pb0 * bs
            raw.seek(off)
            if raw.read(size) != fs.read(path):
                raise SystemExit("%s: %s -- Gegenprobe am Offset %d schlug fehl"
                                 % (image, path, off))
            out[path] = (off, size)
        log.ok("%-22s Blockgroesse %d, %d Datei(en) am Stueck, Gegenprobe gleich"
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
            problems.append("%s fehlt" % path)
            continue
        i = fs.inode(ino)
        actual = i["mode"] & 0o7777
        if (i["uid"], i["gid"]) != (uid, gid):
            problems.append("%s gehoert %d:%d statt %d:%d" % (path, i["uid"], i["gid"], uid, gid))
        if mode is not None and actual != mode:
            problems.append("%s hat Modus %04o statt %04o" % (path, actual, mode))
    if problems:
        for x in problems:
            log.error(x)
        raise SystemExit("%s: Besitz/Rechte stimmen nicht -- der Baum wurde nicht als "
                         "root ausgepackt? (mkimage-eingaben.sh im Container mit "
                         "`podman exec -u root` ausfuehren)" % os.path.basename(image))
    log.ok("%-22s Besitz root:root und Modi geprueft (%d Pfade, darunter /root/.ssh 0700, authorized_keys 0600)"
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


def build(args):
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
            raise SystemExit("%s: %s nicht gefunden" % (w, p))

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
    console.step(1, "Bausteine pruefen")
    n_spl, n_ub = os.path.getsize(spl), os.path.getsize(ub)
    v_spl, v_ub = uboot_version(spl), uboot_version(ub)
    for what, path, version in (("SPL", spl, v_spl), ("U-Boot", ub, v_ub)):
        if version:
            console.info("  %-7s %s  (%s)" % (what, version, os.path.basename(path)))
        else:
            console.warn("%s: keine Versionskennung in %s gefunden" % (what, path))
    n_boot, n_root = os.path.getsize(boot), os.path.getsize(root)
    if open(spl, "rb").read(12)[4:12] != b"eGON.BT0":
        raise SystemExit("%s traegt keine eGON.BT0-Kennung -- das ist keine SPL" % spl)
    if n_spl > 64 * SECTOR:
        raise SystemExit("SPL ist %d Byte, hy310-spl fasst %d" % (n_spl, 64 * SECTOR))
    if n_ub > 10240 * SECTOR:
        raise SystemExit("U-Boot ist %d Byte, hy310-uboot fasst %d" % (n_ub, 10240 * SECTOR))
    if n_boot != 262144 * SECTOR:
        raise SystemExit("hy310-boot.ext4 ist %d Byte, die Partition hat %d"
                         % (n_boot, 262144 * SECTOR))
    if n_root % SECTOR or n_root > 14991327 * SECTOR:
        raise SystemExit("hy310-rootfs.ext4 passt nicht (%d Byte)" % n_root)
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
        raise SystemExit("%s ist %d Byte, die Umgebung hat %d (CONFIG_ENV_SIZE)" % (env, n_env, ENV_BYTES))
    with open(env, "rb") as f:
        env_raw = f.read()
    env_crc = struct.unpack("<I", env_raw[:4])[0]
    if env_crc != (zlib.crc32(env_raw[4:]) & 0xffffffff):
        raise SystemExit("%s: CRC32 im Kopf (%08x) passt nicht zum Inhalt -- keine U-Boot-Umgebung"
                         % (env, env_crc))
    env_entries = [e.decode("ascii", "replace") for e in env_raw[4:].split(b"\0") if e and e != b"\xff" * len(e)]
    env_gate = [e for e in env_entries if e.startswith("h713_gate=")]
    for w, p, n in (("SPL", spl, n_spl), ("U-Boot proper", ub, n_ub), ("Umgebung", env, n_env),
                    ("hy310-boot.ext4", boot, n_boot), ("hy310-rootfs.ext4", root, n_root)):
        console.ok("%-16s %11d Byte  %s" % (w, n, relpath_or_abs(p, project_root)))
    console.info("  Umgebung: %d Eintraege, CRC %08x, %s" % (len(env_entries), env_crc,
                 ", ".join(env_gate) if env_gate else "KEIN h713_gate -- pruefen"))

    # --- 2. Piece A: GPT + SPL + U-Boot, LBA 0..12287
    console.step(2, "Teil A -- Boot-Kette (LBA %d..%d)" % (PART_A_LBA, PART_A_SECTORS - 1))
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
    console.ok("%s  %d Byte (%.0f MiB)" % (os.path.basename(a_file), len(a), mib(len(a))))

    # --- 3. Piece C: backup copy of the GPT at the end of the disk (finding S46 B7)
    console.step(3, "Teil C -- Sicherungskopie der GPT (LBA %d, %d Sektoren)"
                 % (PART_C_LBA, PART_C_SECTORS))
    c = bytearray(PART_C_SECTORS * SECTOR)
    back_arr = DISK_SECTORS - 1 - GPT_ARRAY_SECTORS
    c[(back_arr - PART_C_LBA) * SECTOR:(back_arr - PART_C_LBA) * SECTOR + len(gpt[back_arr])] = gpt[back_arr]
    c[(DISK_SECTORS - 1 - PART_C_LBA) * SECTOR:] = gpt[DISK_SECTORS - 1]
    with open(c_file, "wb") as f:
        f.write(bytes(c))
    console.ok("%s  %d Byte -- raeumt zugleich Reste der alten Tabelle weg"
               % (os.path.basename(c_file), len(c)))

    problems = check_gpt(bytes(a[:9 * SECTOR]), bytes(c))
    if problems:
        for x in problems:
            console.error(x)
        raise SystemExit("die gebaute GPT ist nicht in Ordnung")
    console.ok("GPT nachgerechnet: CRCs, FirstUsable %d, %d Eintraege, sechs Partitionen, "
               "Sicherungskopie stimmt" % (FIRST_USABLE, GPT_ENTRY_COUNT))

    # --- 4. Piece B: environment + rest of hy310-env (SPL parking space, empty)
    #        + hy310-boot + hy310-rootfs
    console.step(4, "Teil B -- System (LBA %d ...)" % PART_B_LBA)
    with open(b_file, "wb") as f:
        f.write(env_raw)                                                # hy310-env: the environment, LBA 14336
        f.write(b"\0" * ((LBA_BOOT - PART_B_LBA) * SECTOR - n_env))     # rest of the partition (SPL parking space 14464), empty
        _copy(f, boot)
        _copy(f, root)
    n_b = os.path.getsize(b_file)
    want_b = (LBA_BOOT - PART_B_LBA) * SECTOR + n_boot + n_root
    assert n_b == want_b, (n_b, want_b)
    console.ok("%s  %d Byte (%.0f MiB)" % (os.path.basename(b_file), n_b, mib(n_b)))
    console.info("hy310-env traegt die eingebaute Vorgabe des mitgelieferten U-Boot (%s) -- gueltig ab dem ersten Start"
                 % (", ".join(env_gate) if env_gate else "ohne h713_gate"))

    # --- 5. find the placeholder offsets
    console.step(5, "Platzhalter im Abbild finden")
    off_boot = ext4_offsets(boot, [p for _n, _g, t, p in PLACEHOLDERS if t == "hy310-boot"])
    off_root = ext4_offsets(root, [p for _n, _g, t, p in PLACEHOLDERS if t == "hy310-rootfs"] +
                            [p for _n, _g, t, p, _m in USER_PLACEHOLDERS if t == "hy310-rootfs"])
    ext4_check_permissions(root)
    base_boot = (LBA_BOOT - PART_B_LBA) * SECTOR
    base_root = (LBA_ROOTFS - PART_B_LBA) * SECTOR

    table, user, info = {}, {}, {}
    all_entries = [(n, g, t, p, "h713-extract") for n, g, t, p in PLACEHOLDERS] + \
                  [(n, g, t, p, "hy310-install --authorized-key") for n, g, t, p, _m in USER_PLACEHOLDERS]
    for name, size, part, path, source in all_entries:
        if part == "hy310-boot":
            o, g = off_boot[path]
            o += base_boot
        else:
            o, g = off_root[path]
            o += base_root
        if g != size:
            raise SystemExit("%s: %d Byte im Dateisystem, %d in der Tabelle"
                             % (name, g, size))
        (user if is_user_placeholder(name) else table)[name] = [o, g]
        info[name] = {
            "ziel": "%s:%s" % (part, path),
            "laenge": g,
            "lba": (PART_B_LBA * SECTOR + o) // SECTOR,
            "disk_offset": PART_B_LBA * SECTOR + o,
            "quelle": source,
            "fuellung": "zeilenumbrueche" if is_user_placeholder(name) else "muster",
            "sha256_muster": hashlib.sha256(filling(name, g)).hexdigest(),
        }
    console.ok("%d Platzhalter fuer h713-extract, zusammen %d Byte"
               % (len(table), sum(g for _o, g in table.values())))
    console.ok("%d Platzhalter fuer den Nutzer: %s"
               % (len(user), ", ".join("%s (%d Byte, Zeilenumbrueche)" % (n, g)
                                       for n, (_o, g) in user.items())))

    # Counter-check: is the filling really at the computed offset in piece B?
    with open(b_file, "rb") as f:
        for name, (o, g) in list(table.items()) + list(user.items()):
            f.seek(o)
            if f.read(g) != filling(name, g):
                raise SystemExit("%s: an Offset %d steht nicht die erwartete Fuellung" % (name, o))
    console.ok("alle %d Offsets in Teil B gegengeprueft" % (len(table) + len(user)))

    # --- 6. check the hole
    console.step(6, "Der gesperrte Bereich")
    pieces = [(a_file, PART_A_LBA), (b_file, PART_B_LBA), (c_file, PART_C_LBA)]
    for file_name, lba in pieces:
        end = lba + os.path.getsize(file_name) // SECTOR - 1
        if lba <= LOCK_LAST and end >= LOCK_FIRST:
            raise SystemExit("%s deckt LBA %d..%d ab und beruehrt damit den "
                             "Secure Storage" % (file_name, lba, end))
    console.ok("kein Teil beruehrt LBA %d..%d -- auch ein dd von Hand kann den Secure "
               "Storage nicht treffen" % (LOCK_FIRST, LOCK_LAST))

    # --- 7. checksums, table, manifest, readme
    console.step(7, "Tabelle, Manifest, Liesmich")
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
        "werkzeug": "hy310-mkimage " + VERSION,
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
            "warum": ("Secure Storage: HDCP-Schluessel, WLAN-/BT-MAC-Adressen und "
                      "Seriennummer. Geraetespezifisch, in keinem Firmware-Abbild, "
                      "nicht wiederherstellbar (doku/109 §2.3). Deshalb steht dieser "
                      "Bereich in keinem Teil des Abbilds."),
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
        # Exactly the format that fill_placeholders() in hy310-install.py
        # expects: name -> (byte offset, length), offset inside the file named
        # under "platzhalter_datei".
        "platzhalter_datei": os.path.basename(b_file),
        "platzhalter": table,
        # Same shape, different source: hy310-install fills these from
        # --authorized-key, padded with line breaks. An installer that does not
        # know about the key leaves the file empty (line breaks only) -- valid.
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

    readme = stem + "-LIESMICH.txt"
    with open(readme, "w", encoding="utf-8") as f:
        f.write(readme_text(data))
    console.ok(os.path.basename(readme))

    total = sum(t["bytes"] for t in piece_list)
    console.step(8, "Fertig")
    console.info("drei Teile, zusammen %.0f MiB (%.2f GB)" % (mib(total), total / 1e9))
    console.info("Verzeichnis: %s" % directory)
    console.info("Pruefen mit:  %s --pruefen %s"
                 % (os.path.basename(sys.argv[0]), relpath_or_abs(t_file, os.getcwd())))
    return 0


# ---------------------------------------------------------------- Checking

def check(table_file, log=console):
    directory = os.path.dirname(os.path.abspath(table_file))
    with open(table_file, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("format") != "hy310-abbild-tabelle":
        raise SystemExit("%s ist keine Abbild-Tabelle" % table_file)
    bad = 0

    log.step(1, "Teile: Groesse und Pruefsumme")
    pieces = {}
    for t in d["teile"]:
        p = os.path.join(directory, t["datei"])
        if not os.path.isfile(p):
            log.error("%s fehlt" % t["datei"])
            bad += 1
            continue
        n = os.path.getsize(p)
        if n != t["bytes"]:
            log.error("%s ist %d Byte, erwartet %d" % (t["datei"], n, t["bytes"]))
            bad += 1
            continue
        h = sha256_file(p)
        if h != t["sha256"]:
            log.error("%s: sha256 %s…, erwartet %s…" % (t["datei"], h[:16], t["sha256"][:16]))
            bad += 1
            continue
        pieces[t["datei"]] = (p, t["lba"], n)
        log.ok("%-34s LBA %-9d %11d Byte  %s…" % (t["datei"], t["lba"], n, h[:16]))

    log.step(2, "Der gesperrte Bereich (Secure Storage)")
    first = d["loch"]["lba"]
    last = first + d["loch"]["sektoren"] - 1
    if (first, last) != (LOCK_FIRST, LOCK_LAST):
        log.error("die Tabelle nennt LBA %d..%d, dieses Werkzeug kennt %d..%d"
                  % (first, last, LOCK_FIRST, LOCK_LAST))
        bad += 1
    touched = False
    for name, (p, lba, n) in pieces.items():
        end = lba + n // SECTOR - 1
        if lba <= last and end >= first:
            log.error("%s deckt LBA %d..%d ab und beruehrt den Secure Storage"
                      % (name, lba, end))
            touched = True
            bad += 1
    if not touched:
        log.ok("kein Teil beruehrt LBA %d..%d -- der Bereich bleibt, wie er ist"
               % (first, last))

    log.step(3, "Partitionstabelle")
    a = [x for x in d["teile"] if x["lba"] == 0]
    c = [x for x in d["teile"] if x["lba"] == DISK_SECTORS - 33]
    if not a or a[0]["datei"] not in pieces:
        log.error("kein Teil bei LBA 0 -- GPT nicht pruefbar")
        bad += 1
    else:
        head = open(pieces[a[0]["datei"]][0], "rb").read(9 * SECTOR)
        cbytes = open(pieces[c[0]["datei"]][0], "rb").read() if c and c[0]["datei"] in pieces else None
        problems = check_gpt(head, cbytes, d["disk_sektoren"])
        for x in problems:
            log.error(x)
        bad += len(problems)
        if not problems:
            log.ok("CRCs stimmen, FirstUsableLBA %d, %d Eintraege, sechs Partitionen"
                   % (FIRST_USABLE, GPT_ENTRY_COUNT))
            log.ok("Sicherungskopie am Plattenende vorhanden und gleich (Befund S46 B7)")

    log.step(4, "Platzhalter")
    pd = d["platzhalter_datei"]
    if pd not in pieces:
        log.error("%s fehlt -- Platzhalter nicht pruefbar" % pd)
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
                log.error("%s: Offset %d + %d liegt ausserhalb von %s"
                          % (name, off, length, pd))
                broken += 1
                continue
            disk = plba * SECTOR + off
            if info.get("disk_offset") not in (None, disk):
                log.error("%s: disk_offset in der Tabelle passt nicht zum Teil" % name)
                broken += 1
                continue
            lock_from, lock_to = first * SECTOR, (last + 1) * SECTOR
            if disk < lock_to and disk + length > lock_from:
                log.error("%s liegt im gesperrten Bereich" % name)
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
    log.ok("%d Platzhalter geprueft: %d unbefuellt (Fuellung steht), %d bereits gefuellt"
           % (len(both), unfilled, filled))
    if broken:
        log.error("%d Platzhalter stimmen nicht" % broken)
        bad += broken
    if filled:
        log.warn("dieses Abbild ist nicht mehr das Verteilstueck -- es traegt "
                 "geraeteeigene Daten und gehoert nicht weitergegeben")

    log.step(5, "Ergebnis")
    if bad:
        log.error("%d Beanstandung(en)" % bad)
        return 1
    log.ok("alles in Ordnung")
    return 0


# ---------------------------------------------------------------- Readme

# Wording from doku/110-plan-installationsweg.md §9, or rather from the box at
# the very top of it. doku/110 §9: "Der Kasten oben ist keine Formsache und
# darf nicht wegredigiert werden." That is why it stands here verbatim.
BETA_WARNING = """\
 ⚠ Was jedem Nutzer vor dem ersten Schritt gesagt werden muss

 Das hier ist eine Beta. Nicht im Sinne von „ein paar Ecken sind unrund",
 sondern: es kann schiefgehen, und dann steht ein Gerät da, das nicht mehr
 startet.

 Deshalb gilt, ohne Ausnahme und in dieser Reihenfolge:

 1. Mach einen Vollabzug. Nicht den kleinen — den vollen, 7,3 GB, 17 Minuten.
    Damit spielst du dein Gerät genau so zurück, wie es war.
 2. Oder halte die passende Herstellerfirmware bereit, bevor du anfängst.
    Nicht danach suchen, wenn es klemmt.
 3. Erst dann loslegen.

 Wer beides überspringt, riskiert ein Gerät ohne Rückweg. Der FEL-Modus rettet
 die Boot-Kette, aber er stellt keine Daten wieder her, die niemand gesichert
 hat.
"""


def readme_text(d):
    lines = []
    b = lines.append
    b("HY310/H713-Beamer — Abbild %s" % d["abbild"])
    b("=" * (28 + len(d["abbild"])))
    b("")
    b("Gebaut am %s mit %s." % (d["erzeugt"], d["werkzeug"]))
    b("")
    b("-" * 78)
    b(BETA_WARNING.rstrip())
    b("-" * 78)
    b("")
    b("")
    b("Was hier liegt")
    b("--------------")
    b("")
    b("Das Abbild besteht aus DREI Dateien. Das ist kein Versehen, sondern der")
    b("Kern der Sache — siehe den nächsten Abschnitt.")
    b("")
    for t in d["teile"]:
        b("  %-34s %11d Byte   ab Sektor %d" % (t["datei"], t["bytes"], t["lba"]))
    b("  %-34s             wo die Platzhalter liegen" % (d["abbild"] + ".tabelle.json"))
    b("  %-34s             Prüfsummen" % (d["abbild"] + ".sha256"))
    b("")
    b("")
    b("Warum drei Dateien und nicht eine")
    b("---------------------------------")
    b("")
    b("Zwischen den Teilen A und B liegt eine Lücke: die Sektoren %d bis %d,"
      % (d["loch"]["lba"], d["loch"]["lba"] + d["loch"]["sektoren"] - 1))
    b("also 1 MiB. Dort steht das Secure Storage deines Geräts:")
    b("")
    b("  * die HDCP-Schlüssel (ohne sie kein geschütztes Bild über HDMI)")
    b("  * die MAC-Adressen von WLAN und Bluetooth")
    b("  * die Seriennummer")
    b("")
    b("Diese Daten gibt es NUR auf deinem Gerät. Sie stehen in keinem")
    b("Firmware-Abbild, auch nicht in dem des Herstellers, und niemand kann sie")
    b("nachbauen. Wer sie überschreibt, hat sie für immer verloren.")
    b("")
    b("Ein durchgehendes Abbild würde sie beim Schreiben mit Nullen zudecken.")
    b("Deshalb kommt der Bereich in keiner der drei Dateien vor. Du kannst ihn")
    b("gar nicht treffen — auch nicht mit einem dd von Hand, auch nicht, wenn du")
    b("einen Befehl vergisst.")
    b("")
    b("")
    b("Einspielen")
    b("----------")
    b("")
    b("Gerät in den FEL-Modus bringen (Reset-Taste halten, Strom einstecken),")
    b("dann mit hy310-install die Laufwerksfreigabe starten. Danach ist die eMMC")
    b("ein ganz normales USB-Laufwerk.")
    b("")
    b("Der bequeme Weg — hy310-install macht Sicherung, Extraktion und Schreiben:")
    b("")
    b("    hy310-install --uboot u-boot-sunxi-with-spl.bin \\")
    b("                  --abbild %s.tabelle.json" % d["abbild"])
    b("")
    b("Der Weg von Hand, wenn die eMMC schon als /dev/sdX zu sehen ist. ALLE DREI")
    b("Befehle, in dieser Reihenfolge, und /dev/sdX vorher zweimal prüfen:")
    b("")
    for t in d["teile"]:
        b("    dd if=%s of=/dev/sdX bs=512 seek=%d conv=fsync"
          % (t["datei"], t["lba"]))
    b("")
    b("(Teil B geht mit bs=1M seek=7 schneller — dasselbe Ziel, weil Sektor")
    b("%d genau 7 MiB sind.)" % PART_B_LBA)
    b("")
    b("Danach Strom abziehen und wieder einstecken.")
    b("")
    b("")
    b("Was danach noch fehlt")
    b("---------------------")
    b("")
    b("Im Abbild stecken %d Platzhalter: Dateien in der richtigen Größe, aber mit"
      % len(d["platzhalter"]))
    b("Füllmuster statt Inhalt. Es sind die Teile, die dem Hersteller gehören und")
    b("die wir nicht mitverteilen dürfen:")
    b("")
    b("  * 19 Anzeige-Artefakte (mips/) — ohne sie bleibt das Bild schwarz")
    b("  * 3 Firmware-Dateien (ARISC, EDID, MSP-Patch)")
    b("  * 8 PQ-Dateien (Bildabstimmung)")
    b("")
    b("Sie kommen aus deinem eigenen Gerät: h713-extract liest sie aus dem")
    b("Vollabzug, den du vorher gezogen hast, und hy310-install schreibt sie an")
    b("die Stellen, die in %s.tabelle.json stehen — am PC," % d["abbild"])
    b("bevor überhaupt etwas auf die eMMC geht.")
    b("")
    b("Solange sie nicht gefüllt sind, startet das System zwar, aber ohne Bild.")
    b("")
    b("Ein Platzhalter mehr gehört dir selbst: /root/.ssh/authorized_keys. Im")
    b("Abbild ist die Datei leer (4096 Zeilenumbrüche). Mit")
    b("")
    b("    hy310-install ... --authorized-key ~/.ssh/id_ed25519.pub")
    b("")
    b("kommt dein öffentlicher SSH-Schlüssel hinein, und du kommst per ssh als")
    b("root auf das Gerät. Ohne den Schalter bleibt nur die serielle Konsole")
    b("(Passwort-Login ist aus). Kein Schlüssel wird mitverteilt.")
    b("")
    b("")
    b("Wenn etwas schiefgeht")
    b("---------------------")
    b("")
    b("NICHT den Strom ziehen und hoffen. Das Gerät in den FEL-Modus bringen")
    b("(Reset halten, Strom einstecken) und von vorn anfangen — die Boot-Kette")
    b("ist von dort immer erreichbar. Wenn du einen Vollabzug hast, spielt")
    b("hy310-install --restore ihn zurück.")
    b("")
    return "\n".join(lines) + "\n"
