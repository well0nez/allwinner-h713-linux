# SPDX-License-Identifier: GPL-2.0
"""The installation path itself: putting the device's own files into a built image,
checking the image package, carrying the intent keys of the old U-Boot environment
over, and writing everything onto the eMMC in one go.

Stage 1 of plan doku/121: moved from hy310-install.py (I:656-694, 696-923,
1222-1402, 1436-1453). Layout v4 (P-layout-v4, 16.09.2026) took the placeholders
out: the files are no longer written into fixed-size holes at measured offsets but
copied into the image's two ext4 file systems as ordinary files, so a firmware whose
files are bigger than the HY310's (issue #1, HY300 Pro) simply fits.

Plan and executor are apart. Everything here is pure Python on the table -- which
file goes into which partition at which path, which ones a firmware may not have,
what a rehearsal would do. The mounting itself is `h713.mountfs`, and only a real
run reaches it.
"""

from __future__ import annotations

import collections
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import time

from . import mountfs
from .blockdev import LOCK_FIRST, LOCK_LAST, SECT, SECTORS_EXPECTED
from .env import ENV_BYTES, ENV_CARRY_OVER, env_read, env_write
from .log import Quiet, console
from .util import duration, mib
from .verify import verify_image, write_image

# What a vendor file looks like in the finished file system (P-layout-v4): root's, readable
# by everyone, in directories everyone may walk through. The user's own file says its own
# modes in the table -- sshd's StrictModes has an opinion about those.
VENDOR_MODE, DIR_MODE = 0o644, 0o755
OWNERS = {"root": (0, 0)}


# ---------------------------------------------------------------- SSH key

KEY_TYPES = (b"ssh-ed25519", b"ssh-rsa", b"ecdsa-sha2-nistp256",
             b"ecdsa-sha2-nistp384", b"ecdsa-sha2-nistp521",
             b"sk-ssh-ed25519@openssh.com", b"sk-ecdsa-sha2-nistp256@openssh.com")
KEY_MAX = 1 << 16                     # 64 KiB of authorized_keys is several hundred keys


def read_public_key(path):
    """--ssh-key: the public key as the content of /root/.ssh/authorized_keys.

    What is checked is what a typo would cost: a private key (that must never go
    into the image), a file without a single key line, NUL bytes. Nothing is
    padded any more -- layout v4 writes the file with the length it has.
    Return value: (content, number of keys).
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(KEY_MAX + 1)
    except OSError as e:
        raise RuntimeError("--ssh-key %s: %s" % (path, e))
    if b"PRIVATE KEY" in raw:
        raise RuntimeError("--ssh-key %s is a PRIVATE key -- what is meant is "
                           "the .pub file. Nothing written." % path)
    if b"\0" in raw:
        raise RuntimeError("--ssh-key %s contains NUL bytes -- no key file" % path)
    if len(raw) > KEY_MAX:
        raise RuntimeError("--ssh-key %s is longer than %d bytes -- no key file"
                           % (path, KEY_MAX))
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = [line.strip() for line in text.split(b"\n")]
    lines = [line for line in lines if line]
    hits = [line for line in lines if not line.startswith(b"#") and
            any(line.startswith(kind + b" ") or (b" " + kind + b" ") in line for kind in KEY_TYPES)]
    if not hits:
        raise RuntimeError("--ssh-key %s: no line looks like a public "
                           "OpenSSH key (%s ...)"
                           % (path, ", ".join(kind.decode() for kind in KEY_TYPES[:3])))
    return b"\n".join(lines) + b"\n", len(hits)


def _mode(text, fallback):
    return int(text, 8) if text else fallback


def user_entries(args, rows, log=console):
    """The files the table lists under `nutzer` -- today just authorized_keys. Same
    mechanics as the vendor files, other source: it does not come out of the device, and
    it has to be settable without any vendor file at all. Modes and owner come from the
    table, because sshd (StrictModes) refuses the key if they are wrong.

    Returns partition -> [mountfs.Entry]; without --ssh-key nothing is written, and then
    the device simply has no authorized_keys.
    """
    out = collections.OrderedDict()
    for row in rows:
        if row["name"] != "authorized_keys":
            raise RuntimeError("the table names a file of the user this script does not "
                               "know: %s -- a newer h713-install is needed" % row["name"])
        owner = row.get("besitzer", "root")
        if owner not in OWNERS:
            raise RuntimeError("%s is to belong to %s -- this script only writes root's"
                               % (row["pfad"], owner))
        if not args.ssh_key:
            log.warn("no --ssh-key: %s is not written -- the device is then reachable "
                     "only over the serial console" % row["pfad"])
            continue
        data, n = read_public_key(args.ssh_key)
        uid, gid = OWNERS[owner]
        out.setdefault(row["partition"], []).append(mountfs.Entry(
            row["pfad"], data, None, _mode(row.get("modus"), 0o600), uid, gid,
            _mode(row.get("verzeichnis_modus"), 0o700)))
        log.ok("authorized_keys: %d key(s) from %s, %d bytes -> %s (mode %s, %s)"
               % (n, args.ssh_key, len(data), row["pfad"],
                  row.get("modus", "0600"), owner))
    return out


# ---------------------------------------------------------------- the old command line
# Stage 3 (api-stufe3.md): h713-install has subcommands, the v0.5-beta switches live on
# as hidden aliases for one release, and hy310-install.py forwards through the very same
# translate() -- so the forwarder and the hidden aliases can never drift apart.

# The German switches of v0.5-beta: hidden, accepted for one release (Marco, 13.09.).
#   old flag -> (subcommand it implies, new flag, what happens to its value)
#      "pos"  the value becomes the subcommand's positional     "drop" flag and value fall away
#      "flag" the value follows the new flag                    None   the old flag takes no value
#      "size" klein|voll becomes --small|--full
ALIASES = {
    "--abbild":         ("install", None, "pos"),
    "--tabelle":        (None, "--table", "flag"),
    "--authorized-key": (None, "--ssh-key", "flag"),
    "--arbeitskopie":   (None, "--work-copy", "flag"),
    "--sicherung":      (None, "--dump", "flag"),
    "--abzug":          ("dump", None, "size"),
    "--nur-abzug":      ("dump", None, None),
    "--restore":        ("restore", None, "pos"),
    "--restore-stock":  ("restore-stock", None, "pos"),
    "--extraktor":      (None, None, "drop"),
    "--env-neu":        (None, "--fresh-env", None),
    "--ohne-erkennung": (None, "--skip-identify", None),
    "--dry-run":        (None, "--no-write", None),
}
HINTS = {
    "--abbild": "install TABLE", "--tabelle": "--table", "--authorized-key": "--ssh-key",
    "--arbeitskopie": "--work-copy", "--sicherung": "--dump DIR (with dump: -o DIR)",
    "--abzug": "dump --small|--full", "--nur-abzug": "dump", "--restore": "restore DUMP.img",
    "--restore-stock": "restore-stock UPDATE.img", "--env-neu": "--fresh-env",
    "--ohne-erkennung": "--skip-identify", "--dry-run": "--no-write",
    "--extraktor": "gone -- the package brings its own reader (ignored)",
}
STRONG = ("install", "restore", "restore-stock", "dump")     # --nur-abzug beat --abbild before
WRITES = ("install", "restore", "restore-stock")             # the subcommands that may write
COMMANDS = ("identify", "dump", "install", "restore", "restore-stock", "extract")
COMMON = {"--device": 1, "--sunxi-fel": 1, "--uboot": 1,     # option -> how many values
          "--no-write": 0, "--skip-identify": 0, "--yes": 0}


def _command_of(argv):
    """(subcommand, the rest) -- argparse wants the subcommand first, people write the
    common options in front of it (`--device /dev/sdb dump`). So it is looked for behind
    them as well, but only behind options whose arity is known."""
    if argv and not argv[0].startswith("-"):
        return argv[0], argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] in COMMANDS:
            return argv[i], argv[:i] + argv[i + 1:]
        flag, glued, _value = argv[i].partition("=")
        if flag not in COMMON:
            break
        i += 1 + (0 if glued else COMMON[flag])
    return None, argv


def translate(argv):
    """Old command line -> new one. Returns (argv, hints), one hint line per alias used."""
    command, rest = _command_of(list(argv))
    out, hints, positional, implied, i = [], [], None, None, 0
    while i < len(rest):
        flag, glued, inline = rest[i].partition("=")
        if flag not in ALIASES:
            out.append(rest[i])
            i += 1
            continue
        wants, new, kind = ALIASES[flag]
        value = inline
        if kind is not None and not glued:
            i += 1
            value = rest[i] if i < len(rest) else ""
        hints.append("%s is now %s" % (flag, HINTS[flag]))
        if wants and (implied is None or STRONG.index(wants) > STRONG.index(implied)):
            implied = wants
        if kind == "pos":
            positional = value
        elif kind == "flag":
            out += [new, value]
        elif kind == "size":
            out.append("--full" if value.startswith(("f", "v")) else "--small")
        elif new:
            out.append(new)
        i += 1
    if command is None and not (set(rest) & {"-h", "--help", "--version"}):
        command = implied or "dump"           # the old tool without --abbild only dumped
    if positional is not None and command in WRITES:
        out.insert(0, positional)
    if command == "dump":
        out = ["-o" if a == "--dump" else a for a in out]
    return ([command] if command else []) + out, hints

# ---------------------------------------------------------------- image package

RELEASE_FILES = {"uboot": ("u-boot-installer.bin",),
                 "fel": ("sunxi-fel.exe", "sunxi-fel")}

# The `format` key of every table h713-mkimage has ever written starts with this; what tells
# the layouts apart are the keys, not the string, so a suffix P1 adds to it changes nothing
# here. A v4 table lists `dateien`, a v3 one `platzhalter`.
TABLE_FORMAT = "hy310-abbild-tabelle"
V3_REFUSED = ("this image was built for the placeholder layout v3 - use the installer of its "
              "release, or a v4 image")


def table_layout(tab):
    """"v4" for a table that lists its files, "v3" for one that lists placeholders, None for
    anything else. Read off the keys the installer actually uses, so no image can be half
    accepted: what it does not find, it does not fill in."""
    if isinstance(tab.get("dateien"), list):
        return "v4"
    if "platzhalter" in tab or "platzhalter_datei" in tab:
        return "v3"
    return None


# The dump's file and directory names, English since stage 4. A dump made by
# v0.5-beta carries the German names; in_dump() still finds those, so the way
# back through an old dump stays open.
DUMP_DEFAULT = "h713-dump"                  # v0.5-beta: hy310-sicherung
DUMP_FULL = "emmc-full.img"                 # v0.5-beta: emmc-voll.img
EXTRACT_DIR = "extract"                     # v0.5-beta: extrakt
WORK_COPY = "image-filled.img"              # v0.5-beta: abbild-gefuellt.img (written, never read back)
OLD_NAMES = {DUMP_FULL: "emmc-voll.img", EXTRACT_DIR: "extrakt"}


def in_dump(dump_dir, name, log=console):
    """The path of `name` in a dump directory. When it is missing but the v0.5-beta
    spelling is there, that one is returned (and said), so old dumps keep working."""
    new = os.path.join(dump_dir, name)
    old = OLD_NAMES.get(name)
    if old and not os.path.exists(new) and os.path.exists(os.path.join(dump_dir, old)):
        log.info("  %s: reading the v0.5-beta name %s" % (name, old))
        return os.path.join(dump_dir, old)
    return new


def release_files(directory):
    """What a release folder brings along besides the table: {"uboot": path, "fel": path}.

    Stage 3 (api-stufe3.md): `install RELEASE-DIR` finds u-boot-installer.bin and
    sunxi-fel next to the table, so that nobody has to name six paths by hand.
    --uboot/--sunxi-fel keep precedence; what is not there is simply not in the dict.
    """
    found = {}
    for key, names in RELEASE_FILES.items():
        for name in names:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                found[key] = path
                break
    return found


def unpack_parts(directory, table, log=console):
    """Image parts that lie only as `.img.zst`: unpack them with the `zstd` binary.

    The release ships the parts packed (1.15 GB -> 56 MiB). Without `zstd` on the PC
    this says so in one line and names the file instead of failing somewhere deeper.
    """
    packed = [t["datei"] for t in table["teile"]
              if not os.path.isfile(os.path.join(directory, t["datei"]))
              and os.path.isfile(os.path.join(directory, t["datei"] + ".zst"))]
    if not packed:
        return
    zstd = shutil.which("zstd")
    if not zstd:
        raise RuntimeError("%d part(s) lie only packed (%s) and `zstd` is not on this PC -- "
                           "install zstd or unpack by hand (`zstd -d *.img.zst`)"
                           % (len(packed), ", ".join(name + ".zst" for name in packed)))
    for name in packed:
        source = os.path.join(directory, name + ".zst")
        log.info("unpacking %s (zstd, %.0f MiB packed)" % (name + ".zst", mib(os.path.getsize(source))))
        subprocess.run([zstd, "-d", "-q", "-f", source, "-o", os.path.join(directory, name)],
                       check=True)


def image_package(path):
    """Resolve the image to be written. Three things are allowed:

      * the table itself         out/hy310-v0.1.tabelle.json
      * the directory around it  out/          (a release folder)
      * a single file            anything.img   (then it needs --table)

    Return value: (directory, table|None). The table comes out of h713-mkimage;
    its structure is documented there.
    """
    if os.path.isdir(path):
        hits = sorted(x for x in os.listdir(path) if x.endswith(".tabelle.json"))
        if len(hits) != 1:
            raise RuntimeError(
                "%s holds %d files *.tabelle.json -- please name the right one "
                "directly" % (path, len(hits)))
        path = os.path.join(path, hits[0])
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if not str(d.get("format", "")).startswith(TABLE_FORMAT):
            raise RuntimeError("%s is no image table of h713-mkimage" % path)
        return os.path.dirname(os.path.abspath(path)), d
    return os.path.dirname(os.path.abspath(path)), None


def table_test_for(image, table=None):
    """The `test_for` key of the image's table -- read before the device is touched.

    None for a normal image, for a single .img without a table, and for anything that is
    not a table at all (the later steps report that in their own words).
    """
    for candidate in (image, table):
        if not candidate:
            continue
        try:
            _directory, d = image_package(candidate)
        except (RuntimeError, OSError, ValueError):
            continue
        if d and d.get("test_for"):
            return d["test_for"]
    return None


def test_image_allowed(ident, test_for, asked, log=console):
    """Stage 5: may this TEST IMAGE be written onto the device in front of us?

    Two conditions, both required (stufe-5.md): the user asked for it (--test-image), and
    the device is the board the image was built for. The identification is printed here
    instead of by report_device(), whose verdict is about released images.
    """
    for level, text in ident.get("_lines", ()):
        getattr(log, level, log.info)(text)
    found = ident.get("profile")
    if found != test_for:
        log.error("This is a TEST IMAGE for the board '%s'. This device is %s, so nothing "
                  "is written." % (test_for, "'%s'" % found if found else "no board we know"))
        log.info("  A test image carries the device tree, the U-Boot and the panel settings of")
        log.info("  one single board; on any other board those are a guess, and guessing is what")
        log.info("  this tool exists to avoid. What fits this device is the image built for it.")
        log.info("  Whatever you write to any device, the way back is a full dump taken first:")
        log.info("  h713-install dump --full")
        return False
    if not asked:
        log.error("This is a TEST IMAGE for the board '%s' -- it is written only when you ask "
                  "for it, and you did not." % test_for)
        log.info("  Nobody has reported a green run of this system on this board yet, so the")
        log.info("  image is not a release: it was built for its owner to try. If that is you,")
        log.info("  take a full dump first -- it is the way back -- and say so on the command line:")
        log.info("  h713-install dump --full")
        log.info("  h713-install install <release folder> --test-image")
        return False
    log.warn("TEST IMAGE for '%s': this device is that board, and --test-image was given."
             % test_for)
    log.info("  Nobody has reported a green run here yet. Your full dump is the way back.")
    return True


def check_package(directory, d, log=console):
    """Sizes and checksums of the pieces, before anything is written."""
    for t in d["teile"]:
        p = os.path.join(directory, t["datei"])
        if not os.path.isfile(p):
            raise RuntimeError("%s is missing -- the image is incomplete" % t["datei"])
        if os.path.getsize(p) != t["bytes"]:
            raise RuntimeError("%s is %d bytes, expected %d"
                               % (t["datei"], os.path.getsize(p), t["bytes"]))
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                b = f.read(8 << 20)
                if not b:
                    break
                h.update(b)
        if t.get("sha256") and h.hexdigest() != t["sha256"]:
            raise RuntimeError("%s: sha256 does not match -- broken transfer?" % t["datei"])
        log.ok("%-34s LBA %-9d %11d bytes  %s"
               % (t["datei"], t["lba"], t["bytes"],
                  "sha256 ok" if t.get("sha256") else "sha256 " + h.hexdigest()[:16] + "…"))
    hole = d.get("loch")
    if hole and (hole["lba"], hole["lba"] + hole["sektoren"] - 1) != (LOCK_FIRST, LOCK_LAST):
        raise RuntimeError("the table locks LBA %d..%d, this script %d..%d -- "
                           "they do not belong together"
                           % (hole["lba"], hole["lba"] + hole["sektoren"] - 1,
                              LOCK_FIRST, LOCK_LAST))
    if d.get("disk_sektoren") != SECTORS_EXPECTED:
        raise RuntimeError("the table is built for %s sectors, %d are expected here"
                           % (d.get("disk_sektoren"), SECTORS_EXPECTED))


# ------------------------------------------------- the file set of layout v4
# Where each vendor file goes is in the table (`dateien`: name, partition, path, group,
# optional); this here is what the ABSENCE of one costs. The table says what a group is,
# the installer says what the device does without it.
# (HY300 Pro, issue #1, 16.09.2026: the Android 10 vendor image has no
# fw_patch_8800d80_u02_ext0.bin, no pq_picturemode.ini and no pqcontrol_custom_setting.xml;
# a firmware may also ship no WLAN firmware at all, because not every H713 board carries the
# AIC8800 chip, and h713-extract expressly does not treat that as an error.)
CONSEQUENCE = {
    "wlan": "WLAN stays off",
    "pq": "h713-pq has no presets, the picture itself is unaffected",
    "logo": "U-Boot boots without a logo",
}


def partition_window(tab, name):
    """(part file, byte offset in it, byte size) of the partition `name` -- everything the
    mount needs, out of the table alone: `partitionen` says where the partition starts and
    how long it is, `teile` where the part that carries it is written (P-layout-v4).

    None when no part of this run holds the partition: whoever writes only the boot chain
    does not touch the file systems, and then there is nothing to fill.

    The size is capped at what the part really holds. hy310-rootfs is 7.1 GiB on the device
    but its file system in the image is 1 GiB (the partition is bigger than the ext4 in it),
    and a window may not reach past the end of the file it is cut out of."""
    part = next((p for p in tab.get("partitionen") or [] if p["name"] == name), None)
    if part is None:
        raise RuntimeError("the table knows no partition %s" % name)
    piece = next((t for t in tab["teile"]
                  if t["lba"] <= part["lba"] < t["lba"] + t["sektoren"]), None)
    if piece is None:
        return None
    offset = (part["lba"] - piece["lba"]) * SECT
    return (piece["datei"], offset,
            min(part["sektoren"] * SECT, piece["sektoren"] * SECT - offset))


def say_optional(tab, files, missing, where, absent, log=console):
    """Sort the files there is no source for into the ones a firmware may not have and the
    ones that stop the run -- one line per group, as before.

    `where` names the source in that line ("in the dump", "on this device"), `absent` says
    what "missing" means there. Returns the names that are still a problem."""
    described = tab.get("gruppen") or {}
    optional = set(f["name"] for f in files if f.get("optional"))
    gone = [n for n in missing if n in optional]
    for group in sorted(set(f["gruppe"] for f in files if f["name"] in gone)):
        whole = [f["name"] for f in files if f["gruppe"] == group]
        out = [n for n in whole if n in gone]
        what = described.get(group, group)
        why = CONSEQUENCE.get(group, "the device does without it")
        if len(whole) == 1:
            log.warn("%s: %s -- no %s. %s." % (out[0], absent, what, why))
        elif len(out) == len(whole):
            log.warn("%s: none of the %d files %s -- this firmware has no %s. They are not "
                     "installed, %s." % (group, len(whole), where, what, why))
        else:
            log.warn("%s: %d of %d files %s (%s) -- this firmware ships another %s set. "
                     "Those are not installed, %s."
                     % (group, len(out), len(whole), absent,
                        ", ".join(os.path.basename(n) for n in sorted(out)[:3]), what, why))
    return [n for n in missing if n not in optional]


def vendor_sources(directory, tab, files, log=console):
    """Read in the device's own files that h713-extract put down. The names in the table are
    exactly the paths below the --out of h713-extract, so this is a putting-together and not
    a matching-up. A file this firmware may not have is said and left out; everything else
    missing is an abort. Nothing is ever written empty."""
    sources, missing = {}, []
    for f in files:
        p = os.path.join(directory, f["name"].replace("/", os.sep))
        if not os.path.isfile(p):
            missing.append(f["name"])
            continue
        with open(p, "rb") as fh:
            sources[f["name"]] = fh.read()
    left = say_optional(tab, files, missing, "in the dump", "not in %s" % directory, log)
    if left:
        raise RuntimeError("in %s %d file(s) are missing, e.g. %s"
                           % (directory, len(left), ", ".join(sorted(left)[:3])))
    return sources


def copy_entries(files, sources):
    """partition -> [mountfs.Entry], in the order of the table: everything there is a source
    for, as root's file with mode 0644. A name whose source is None is a rehearsal entry --
    it says WHERE the file would go without having read it (`--no-write`)."""
    out = collections.OrderedDict()
    for f in files:
        if f["name"] in sources:
            out.setdefault(f["partition"], []).append(mountfs.Entry(
                f["pfad"], sources[f["name"]], None, VENDOR_MODE, 0, 0, DIR_MODE))
    return out


# ------------------------------------------- the device's own file systems (N2, layout v4)
# On a device that already runs our layout the 44 vendor files are not gone: they lie in its
# two ext4 file systems under the very paths the table names. Reading them back is cheaper
# than a dump and needs nothing the owner has to keep (doku/61 B, Marco 15.09.). Under
# layout v3 that was raw block arithmetic and needed a magic-byte check to notice a
# read-back landing on the wrong bytes; a file read out of a file system is the file.

def gpt_partitions(disk):
    """name -> (number, first LBA, sectors), read out of the GPT the device carries. The
    number is the GPT entry slot -- that is what Linux calls /dev/sdX<n>, and it is read
    here, never assumed."""
    head = disk.read(1, 1)
    if head[:8] != b"EFI PART":
        return {}
    entry_lba, count, size = struct.unpack_from("<QII", head, 72)
    if count > 128 or size not in (128, 256):
        return {}
    table = disk.read(entry_lba, (count * size + SECT - 1) // SECT)
    found = {}
    for i in range(count):
        e = table[i * size:(i + 1) * size]
        if len(e) < 128 or e[:16] == b"\0" * 16:
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        found[e[56:128].decode("utf-16-le", "replace").rstrip("\0")] = (i + 1, first,
                                                                       last - first + 1)
    return found


def partition_node(device, number):
    """What Linux calls that partition: /dev/sdb + 5 -> /dev/sdb5; mmcblk0, nvme0n1 and
    loop0 take a `p` in between."""
    return "%s%s%d" % (device, "p" if device[-1:].isdigit() else "", number)


def readback_plan(disk, files):
    """What has to be read to get the file set off a device that runs our layout:
    [(partition, node, byte offset, byte size, {path in it: name})]. Pure Python -- only the
    GPT is read and nothing is mounted, so a rehearsal can print it."""
    found = gpt_partitions(disk)
    plan = []
    for name in sorted(set(f["partition"] for f in files)):
        if name not in found:
            raise RuntimeError("the device has no partition %s -- give --vendor" % name)
        number, lba, sectors = found[name]
        plan.append((name, partition_node(disk.path, number), lba * SECT, sectors * SECT,
                     dict((f["pfad"], f["name"]) for f in files if f["partition"] == name)))
    return plan


def device_sources(disk, tab, files, log=console):
    """Read the vendor files back out of the device's own file systems: every partition the
    table names is mounted read-only and the files are copied out as files.

    The window comes from the device's own GPT, so the mount is the same command as on the
    working copy. The partition node is named in the log for the reader, but not mounted:
    the installer holds the whole drive open exclusively (h713.blockdev.Disk), and while it
    does, the kernel refuses to mount a partition of it.

    Returns (sources, problem). `problem` is None when the set is complete; otherwise it is
    the line that goes under the "no vendor source" block, and `sources` is unusable."""
    sources = {}
    try:
        for name, node, offset, size, wanted in readback_plan(disk, files):
            log.info("  %s = %s, %d file(s) wanted" % (name, node, len(wanted)))
            for path, data in mountfs.copy_out(disk.path, offset, size,
                                               sorted(wanted), log).items():
                sources[wanted[path]] = data
    except RuntimeError as e:
        return {}, str(e)
    missing = [f["name"] for f in files if f["name"] not in sources]
    left = say_optional(tab, files, missing, "on this device", "not on the device", log)
    if left:
        return {}, "the device has no %s -- give --vendor" % ", ".join(sorted(left)[:3])
    log.ok("%d files read back from the device" % len(sources))
    return sources, None


def check_copies(work, windows, plan, log=Quiet):
    """Read the files back out of the working copy and compare byte for byte -- on the PC,
    costs seconds. Returns the paths that differ."""
    bad = []
    for name, (_file, offset, size) in windows.items():
        entries = plan.get(name) or []
        if not entries:
            continue
        back = mountfs.copy_out(work, offset, size, [e.path for e in entries], log)
        bad += [e.path for e in entries if back.get(e.path) != e.data]
    return bad



def no_vendor_source(dump_dir, count, log=console, extra=None):
    """Exit 8: no source for the device's own files. Unchanged for a stock device; the
    read-back adds one line saying what the device itself could not supply."""
    log.error("There is neither --vendor nor a full dump in %s." % dump_dir)
    log.info("  The %d files (display artefacts, boot logo, firmware, PQ, WLAN) stand only"
             % count)
    log.info("  on your own device. Without them the picture stays black.")
    log.info("  So: take the FULL dump (dump --full) or name a directory")
    log.info("  from h713-extract with --vendor.")
    if extra:
        log.error(extra)
    return 8


def _load_extractor(path=None, search_dir=None):
    """Load h713-extract as a module -- there sit the IMAGEWTY reader and the
    source classes that we reuse here instead of rebuilding them.
    `search_dir`: where the script ships (the installer directory, passed by the
    calling script); the module directory only as a fallback."""
    if path is None:
        here = search_dir or os.path.dirname(os.path.abspath(__file__))
        for candidate in (os.path.join(here, "h713-extract"),
                          os.path.join(here, "..", "r2-extract", "h713-extract")):
            if os.path.isfile(candidate):
                path = candidate
                break
    if not path or not os.path.isfile(path):
        raise SystemExit("h713-extract not found -- it belongs next to this script.")
    spec = importlib.util.spec_from_loader(
        "h713_extract", importlib.machinery.SourceFileLoader("h713_extract", path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_extractor(dump, target, extractor=None, log=console, search_dir=None):
    """Let h713-extract loose on the dump (plan 110 §3): the user reads the
    proprietary parts out of their own device, not out of a download."""
    ex = _load_extractor(extractor, search_dir)
    log.info("h713-extract %s -> %s" % (os.path.basename(dump), target))
    rc = ex.main([dump, "--out", target, "-q"])
    if rc == 0:
        log.ok("extraction complete and checked against the reference")
    elif rc == 1:
        log.warn("h713-extract reports differences (unknown build or missing "
                 "parts) -- the output lies in %s all the same" % target)
    else:
        raise RuntimeError("h713-extract exited with error %d" % rc)
    return rc


# ---------------------------------------------------------------- run

# Stage 3: `--yes` says the confirmation in advance, for runs without a terminal
# (h713-install sets it). It replaces the pseudo-TTY of installer-fahren.py, which
# typed the JA into the prompt from outside -- the promise is given, not bypassed:
# the warning block is printed either way and the answer stands in the log.
ASSUME_YES = False


def ask(text, default=None):
    if not sys.stdin.isatty():
        return default
    try:
        answer = input(text).strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nAborted.")
    return answer or default


def confirm(what):
    """A typed confirmation, not a comfortable [y/N] -- and the same abort rule
    at every place that writes (finding S46 B15, plan 110 §9)."""
    console.info("")
    console.warn(what)
    console.info("")
    console.info("  This here is a beta. If something goes wrong while it writes:")
    console.info("  do NOT pull the power and reboot. Put the device into FEL mode")
    console.info("  (hold reset, plug the power in) and start from the beginning --")
    console.info("  the boot chain is always reachable from there.")
    console.info("")
    if ASSUME_YES:
        console.info("  Type YES to continue: YES   (--yes on the command line)")
        return True
    # ask() gives the answer back in lower case -- the comparison has to fit
    # that, otherwise every confirmation fails (10.09.). "ja" stays accepted for
    # one release (api-stufe3.md: YES and JA).
    return ask("  Type YES to continue: ", "") in ("yes", "ja")


def _image_env_block(tab, work, part_file, log):
    """Locate the U-Boot environment inside the working copy of the part that carries the
    file systems. Returns (offset, env dict) or None (no block, wrong part) -- a broken CRC
    is reported and returned as (offset, None)."""
    block = (tab.get("bausteine") or {}).get("env")
    if not block:
        return None
    part_lba = next((t["lba"] for t in tab["teile"] if t["datei"] == part_file), None)
    if part_lba is None or block["lba"] < part_lba:
        log.warn("the environment does not lie in the part with the file systems -- carry-over skipped")
        return None
    off = (block["lba"] - part_lba) * SECT
    with open(work, "rb") as f:
        f.seek(off)
        env = env_read(f.read(ENV_BYTES))
    if env is None:
        log.error("the environment in the image at offset 0x%x has no valid CRC" % off)
    return off, env


def _store_image_env(work, off, env, log):
    """Write `env` back into the working copy at `off` and read it back. Returns 0 or 11."""
    with open(work, "r+b") as f:
        f.seek(off)
        f.write(env_write(env))
        f.flush()
        os.fsync(f.fileno())
        f.seek(off)
        if env_read(f.read(ENV_BYTES)) != env:
            log.error("the environment is not as expected after writing")
            return 11
    return 0


def write_env_keys(tab, work, part_file, keys, log=console):
    """Set the given keys in the image's environment (working copy of part B) -- stage 2 C9:
    what the board declared and our layout no longer carries as a partition, e.g.
    h713_project from Reserve0's panel_config.ini (doku/121 §4). Returns 0,
    11 on a broken environment; nothing happens when the image has no environment block."""
    if not keys:
        return 0
    found = _image_env_block(tab, work, part_file, log)
    if found is None:
        log.info("Environment: this image carries none -- %s not stored" % ", ".join(sorted(keys)))
        return 0
    off, env = found
    if env is None:
        return 11
    changed = {k: v for k, v in keys.items() if env.get(k) != v}
    if not changed:
        log.ok("Environment: %s already set as declared" % ", ".join("%s=%s" % kv for kv in sorted(keys.items())))
        return 0
    env.update(changed)
    rc = _store_image_env(work, off, env, log)
    if rc == 0:
        log.ok("Environment: stored what the board declares: %s"
               % ", ".join("%s=%s" % kv for kv in sorted(changed.items())))
    return rc


def kept_copy(args, name):
    """What the small dump would have left for the later steps, when it was skipped on our
    own layout: the copy `keep_copy()` read into memory before the write (N2)."""
    return (getattr(args, "_kept", None) or {}).get(name)


def old_env(args):
    """The environment the device had before this run: out of the small dump when one was
    taken, else out of the copy read into memory instead. Returns (dict or None, path or
    None) -- the path is what the user can still look at afterwards."""
    path = os.path.join(args.dump_dir, "uboot-env.bin")
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return env_read(f.read()), path
    raw = kept_copy(args, "uboot-env")
    return (env_read(raw) if raw else None), None


def carry_env(args, tab, work, part_file, log=console):
    """Write the intent keys of the old environment into the new one -- in the
    working copy of part B, before anything goes onto the eMMC.

    Only when: our layout (otherwise there is no old one), the image brings an
    environment along (bausteine.env, since 12.09.2026; older images have zeros
    there, nothing is invented), the old one was valid, and the user did not say
    --env-neu.
    """
    if args.fresh_env or not args._our_layout:
        return 0
    block = (tab.get("bausteine") or {}).get("env")
    if not block:
        log.info("Environment: this image brings none along (older than 12.09.) -- nothing to carry over")
        return 0
    old, old_path = old_env(args)
    if not old:
        return 0
    part_lba = next((t["lba"] for t in tab["teile"] if t["datei"] == part_file), None)
    if part_lba is None or block["lba"] < part_lba:
        log.warn("the environment does not lie in the part with the file systems -- carry-over skipped")
        return 0
    off = (block["lba"] - part_lba) * SECT
    with open(work, "r+b") as f:
        f.seek(off)
        new = env_read(f.read(ENV_BYTES))
        if new is None:
            log.error("the environment in the image at offset 0x%x has no valid CRC" % off)
            return 11
        taken = []
        for k in ENV_CARRY_OVER:
            if k in old and old[k] != new.get(k):
                taken.append("%s=%s (image: %s)" % (k, old[k], new.get(k, "-")))
                new[k] = old[k]
        if not taken:
            log.ok("Environment: %s agree with the image's default -- nothing to carry over"
                   % ", ".join(ENV_CARRY_OVER))
            return 0
        f.seek(off)
        f.write(env_write(new))
        f.flush()
        os.fsync(f.fileno())
        f.seek(off)
        if env_read(f.read(ENV_BYTES)) != new:
            log.error("the environment is not as expected after writing")
            return 11
    log.ok("Environment: carried over from the old one: %s" % "; ".join(taken))
    if old_path:
        log.info("  Everything else comes from the image's U-Boot. The old one lies in %s." % old_path)
    else:
        log.info("  Everything else comes from the image's U-Boot. The old one was read off the "
                 "device and not saved -- --dump keeps a copy.")
    return 0


def write_package(args, disk, path, directory, tab, here=None):
    """The installation path out of plan 110 §1, steps 4 and 5.

    The order is on purpose (Marco, 10.09.): a working copy of the part that carries the two
    file systems is filled and read back HERE, on the PC, and only then does EVERYTHING go
    onto the eMMC in one go. The other way round -- write first, add later -- costs a second
    pass at 7.7 MB/s, and an abort in between would leave half a system.
    """
    console.step(4, "Check the image (%s, %s)" % (tab.get("abbild"), tab.get("layout")))
    if table_layout(tab) != "v4":
        console.error(V3_REFUSED)
        return 2
    check_package(directory, tab, console)
    console.info("Hole at LBA %d..%d (%s) -- stays untouched"
                 % (tab["loch"]["lba"], tab["loch"]["lba"] + tab["loch"]["sektoren"] - 1,
                    tab["loch"]["partition"]))

    # Whoever writes only ONE part -- the boot chain for instance, to renew the bootloader
    # without loading the whole system anew -- does not touch the file systems at all:
    # partition_window() finds no part for them, and they fall away here. Without this the
    # tool laid down a 1.15 GB working copy, filled it and threw it away.
    rows = list(tab.get("dateien") or [])
    files = [f for f in rows if partition_window(tab, f["partition"])]
    user = [u for u in (tab.get("nutzer") or []) if partition_window(tab, u["partition"])]
    if len(files) != len(rows):
        console.info("%d file(s) skipped: the part they live in is not written in this run"
                     % (len(rows) - len(files)))
    if args.ssh_key and not user:
        if not tab.get("nutzer"):
            raise RuntimeError("--ssh-key: this image has no place for authorized_keys (a "
                               "table without `nutzer`, older than layout v4) -- the key "
                               "would not arrive. Aborted.")
        console.warn("--ssh-key therefore has no effect")

    sources = {}
    if files:
        console.step(5, "Put the device's own files in (%d files)" % len(files))
        vendor = args.vendor
        if not vendor:
            full = in_dump(args.dump_dir, DUMP_FULL)
            if os.path.isfile(full):
                vendor = in_dump(args.dump_dir, EXTRACT_DIR)
                os.makedirs(vendor, exist_ok=True)
                run_extractor(full, vendor, None, search_dir=here)
            elif not getattr(args, "_our_layout", False):
                return no_vendor_source(args.dump_dir, len(files), console)
        if vendor:
            sources = vendor_sources(vendor, tab, files, console)
            console.ok("%d files from %s" % (len(sources), vendor))
        elif args.no_write:
            # Our layout is on the device and the files sit in its file systems (N2). Reading
            # them back is a mount; a rehearsal mounts nothing, so it says what it would read
            # and which files it would look for, and leaves it at that.
            try:
                for name, node, offset, size, wanted in readback_plan(disk, files):
                    console.info("WOULD: read %d file(s) back from %s (%s, LBA %d)"
                                 % (len(wanted), name, node, offset // SECT))
            except RuntimeError as e:
                return no_vendor_source(args.dump_dir, len(files), console, str(e))
            sources = dict((f["name"], None) for f in files)
        else:
            why = mountfs.unusable()
            if why:
                console.error(why)
                return 2
            sources, problem = device_sources(disk, tab, files, console)
            if problem:
                return no_vendor_source(args.dump_dir, len(files), console, problem)

    # The user's key: same mechanics, other source. Here and not in vendor_sources(), because
    # it does not come out of the device -- and because it must be settable without vendor
    # files as well.
    plan = copy_entries(files, sources)
    if user:
        if not files:
            console.step(5, "Put your own SSH key in")
        for part, entries in user_entries(args, user, console).items():
            plan.setdefault(part, []).extend(entries)

    # Every partition that gets something, with the window to mount it through. They all lie
    # in one part of the image (layout v4: part B carries hy310-boot and hy310-rootfs), and
    # that is the part the working copy is made of.
    windows = collections.OrderedDict()
    for row in files + user:
        windows.setdefault(row["partition"], partition_window(tab, row["partition"]))
    part_files = sorted(set(w[0] for w in windows.values()))
    if len(part_files) > 1:
        raise RuntimeError("the file systems lie in %d different parts (%s) -- this installer "
                           "fills one working copy" % (len(part_files), ", ".join(part_files)))

    part_file, work = (part_files[0] if part_files else None), None
    if windows:
        work = args.work_copy or os.path.join(args.dump_dir, WORK_COPY)
        total = sum(len(v) for v in plan.values())
        if args.no_write:
            console.info("WOULD: copy %s to %s and put %d file(s) into it"
                         % (part_file, work, total))
            for name, (_f, offset, size) in windows.items():
                console.info("WOULD: %-13s %2d file(s), mounted at offset %d (%d bytes)"
                             % (name, len(plan.get(name, ())), offset, size))
        else:
            source_part = os.path.join(directory, part_file)
            console.info("Working copy: %s (%.0f MiB)" % (work, mib(os.path.getsize(source_part))))
            os.makedirs(os.path.dirname(os.path.abspath(work)), exist_ok=True)   # N2: no dump made it
            shutil.copyfile(source_part, work)
            for name, (_f, offset, size) in windows.items():
                if plan.get(name):
                    console.info("  %s: %d file(s)" % (name, len(plan[name])))
                    mountfs.copy_in(work, offset, size, plan[name], log=Quiet)
            bad = check_copies(work, windows, plan)
            if bad:
                console.error("differ after copying: %s" % ", ".join(bad))
                return 9
            console.ok("%d files copied in and read back -- all equal" % total)
            rc = carry_env(args, tab, work, part_file, console)
            if rc:
                return rc
            rc = write_env_keys(tab, work, part_file, getattr(args, "_env_keys", None) or {}, console)   # stage 2 C9
            if rc:
                return rc

    console.step(6, "Write onto the eMMC")
    for t in tab["teile"]:
        console.info("  %-34s from LBA %-9d %11d bytes" % (t["datei"], t["lba"], t["bytes"]))
    if args.no_write:
        console.info("No-write run -- nothing written.")
        return 0
    if not confirm("This overwrites the eMMC."):
        return 1
    t0 = time.time()
    for t in tab["teile"]:
        file = work if (work and t["datei"] == part_file) else os.path.join(directory, t["datei"])
        write_image(disk, file, lba0=t["lba"])
        console.ok("%s written" % t["datei"])
    console.ok("everything written in %s" % duration(time.time() - t0))

    console.step(7, "Compare back")
    errors = 0
    for t in tab["teile"]:
        file = work if (work and t["datei"] == part_file) else os.path.join(directory, t["datei"])
        errors += verify_image(disk, file, samples=4, lba0=t["lba"])
    if errors:
        console.error("%d sample(s) differ -- do not reboot, ask." % errors)
        return 6
    console.ok("samples match")
    # And the acid test: the locked region must not have changed. The small dump
    # has been there since step 3.
    ss = os.path.join(args.dump_dir, "secure-storage.bin")
    before = None
    if os.path.isfile(ss):
        with open(ss, "rb") as f:
            before = f.read()
    else:
        # No dump on our own layout (N2): the comparison runs against the copy that was
        # read into memory before the write -- the check is the point, not the file.
        before = kept_copy(args, "secure-storage")
    if before is not None:
        after = disk.read(LOCK_FIRST, len(before) // SECT)
        if after == before:
            console.ok("Secure Storage unchanged (compared byte for byte against the dump)")
        else:
            if not os.path.isfile(ss):
                # The copy in memory is now the only record of what stood there.
                os.makedirs(args.dump_dir, exist_ok=True)
                with open(ss, "wb") as f:
                    f.write(before)
            console.error("THE SECURE STORAGE HAS CHANGED -- please report it, do "
                          "nothing further, keep %s." % ss)
            return 10
    console.info("")
    console.info("Done. Unplug the power and plug it in again.")
    return 0
