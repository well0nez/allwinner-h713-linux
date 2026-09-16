# SPDX-License-Identifier: GPL-2.0
"""The installation path itself: filling the placeholders of a built image with
the device's own files, checking the image package, carrying the intent keys of
the old U-Boot environment over, and writing everything onto the eMMC in one go.

Stage 1 of plan doku/121: moved from hy310-install.py (I:656-694, 696-923,
1222-1402, 1436-1453). Every printed string, every prompt and every exit code is
unchanged.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

from .blockdev import LOCK_FIRST, LOCK_LAST, SECT, SECTORS_EXPECTED
from .env import ENV_BYTES, ENV_CARRY_OVER, env_read, env_write
from .layout import pattern
from .log import Quiet, console
from .util import duration, mib
from .verify import verify_image, write_image


def fill_placeholders(image, table, sources, log=console):
    """Write the device's own files into the LOCAL image file, before anything
    at all goes onto the eMMC.

    The order is on purpose (Marco, 10.09.): the image is finished on the PC and
    then written ONCE. The other way round -- write first, add later -- costs a
    second pass at 7.7 MB/s, and an abort in between would leave half a system.

    'table' is the offset table that comes out of building the image:
    name -> (byte_offset, length). The image carries placeholders of the right
    size there, so nobody needs an ext4 writer.
    """
    missing = [n for n in table if n not in sources]
    if missing:
        raise RuntimeError("no source for: %s" % ", ".join(sorted(missing)))
    with open(image, "r+b") as f:
        for name in sorted(table):
            off, length = table[name]
            data = sources[name]
            if len(data) > length:
                raise RuntimeError(
                    "%s is %d bytes, the placeholder only holds %d"
                    % (name, len(data), length))
            f.seek(off)
            f.write(data)
            if len(data) < length:
                f.write(b"\0" * (length - len(data)))   # zero the rest cleanly
            log.ok("%-28s %7d bytes at offset 0x%x" % (name, len(data), off))
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------- SSH key

KEY_TYPES = (b"ssh-ed25519", b"ssh-rsa", b"ecdsa-sha2-nistp256",
             b"ecdsa-sha2-nistp384", b"ecdsa-sha2-nistp521",
             b"sk-ssh-ed25519@openssh.com", b"sk-ecdsa-sha2-nistp256@openssh.com")


def read_public_key(path, length):
    """--ssh-key: prepare the public key as the content for the
    placeholder /root/.ssh/authorized_keys.

    What is checked is what a typo would cost: a private key (that must never
    go into the image), a file without a single key line, NUL bytes, overlength.
    Padding is done with newlines up to the placeholder length -- sshd skips
    empty lines, NUL bytes would make the file unusable (doku/60 point 13, here
    the special case "file smaller than the placeholder"). Return value: exactly
    `length` bytes.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(length + 1)
    except OSError as e:
        raise RuntimeError("--ssh-key %s: %s" % (path, e))
    if b"PRIVATE KEY" in raw:
        raise RuntimeError("--ssh-key %s is a PRIVATE key -- what is meant is "
                           "the .pub file. Nothing written." % path)
    if b"\0" in raw:
        raise RuntimeError("--ssh-key %s contains NUL bytes -- no key file" % path)
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = [line.strip() for line in text.split(b"\n")]
    lines = [line for line in lines if line]
    hits = [line for line in lines if not line.startswith(b"#") and
            any(line.startswith(kind + b" ") or (b" " + kind + b" ") in line for kind in KEY_TYPES)]
    if not hits:
        raise RuntimeError("--ssh-key %s: no line looks like a public "
                           "OpenSSH key (%s ...)"
                           % (path, ", ".join(kind.decode() for kind in KEY_TYPES[:3])))
    content = b"\n".join(lines) + b"\n"
    if len(content) > length:
        raise RuntimeError("--ssh-key %s: %d bytes, the placeholder holds %d -- fewer "
                           "keys or shorter comments" % (path, len(content), length))
    return content.ljust(length, b"\n"), len(hits)


def user_sources(args, user, log=console):
    """Fill the user placeholders of the table (today: authorized_keys).
    Return value: name -> bytes in the full placeholder length, or {} when there
    is nothing to do (then the file stays as built: empty, only newlines)."""
    sources = {}
    if "authorized_keys" in user:
        off, length = user["authorized_keys"]
        if args.ssh_key:
            data, n = read_public_key(args.ssh_key, length)
            sources["authorized_keys"] = data
            log.ok("authorized_keys: %d key(s) from %s, %d bytes, padded with newlines to %d"
                   % (n, args.ssh_key, len(data.rstrip(b"\n")) + 1, length))
        else:
            log.warn("no --ssh-key: /root/.ssh/authorized_keys stays empty -- the device "
                     "is then reachable only over the serial console")
    elif args.ssh_key:
        raise RuntimeError("--ssh-key: this image has no placeholder for "
                           "authorized_keys (table without platzhalter_nutzer, older than "
                           "11.09.2026) -- the key would not arrive. Aborted.")
    unknown = [n for n in user if n != "authorized_keys"]
    if unknown:
        raise RuntimeError("the table names user placeholders this script does not "
                           "know: %s -- a newer h713-install is needed" % ", ".join(unknown))
    return sources


def check_placeholders(image, table, sources):
    """Compare back after filling -- on the PC, costs seconds."""
    bad = []
    with open(image, "rb") as f:
        for name, (off, length) in table.items():
            f.seek(off)
            if f.read(len(sources[name])) != sources[name]:
                bad.append(name)
    return bad


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
        if d.get("format") != "hy310-abbild-tabelle":
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


# Placeholders a device may also NOT have. Today only the WLAN firmware: not
# every H713 device carries the AIC8800 chip, and h713-extract expressly does
# not treat a missing vendor:/etc/firmware/aic8800d80/ as an error (12.09.2026).
# If the WHOLE set is missing, the placeholders stay zeroed and h713-wifi
# reports "Firmware fehlt" on the device. If only a part is missing, that is a
# finding and no special case -- then abort as with everything else.
OPTIONAL_GROUPS = ("lib/firmware/aic8800_fw/",)

# Placeholders a device may be missing ON ITS OWN, not only as a whole group. Today exactly one:
# the boot logo. A dump without it, or with one too big for the placeholder, still installs -- the
# placeholder keeps its fill pattern, and `h713_disp init <id> logo` in U-Boot treats a missing logo
# as a warning, not as a failed boot (doku/40, last section). It costs a picture, not a boot.
OPTIONAL_FILES = ("boot/bootlogo.bmp",)


def _sort_out_optional(sources, table, missing, too_big, where, absent, log):
    """The two kinds of placeholder a device may not be able to supply, for both sources
    (a directory from h713-extract, and the device's own filled placeholders).

    `where` names the source in the WLAN line, `absent` says what "missing" means there.
    Returns (missing, too_big) with the optional ones taken out -- `table` loses an optional
    file, so the caller neither fills it nor counts it."""
    for prefix in OPTIONAL_GROUPS:
        group = [n for n in table if n.startswith(prefix)]
        gone = [n for n in group if n in missing]
        if group and len(gone) == len(group):
            log.warn("%s: none of the %d files %s -- this device probably "
                     "does not have the chip. The placeholders stay zeroed, WLAN stays off."
                     % (prefix, len(group), where))
            for n in gone:
                sources[n] = b""
                missing.remove(n)
    for name in OPTIONAL_FILES:
        if name not in table:
            continue
        if name in missing:
            why = absent
        elif len(sources.get(name, b"")) > table[name][1]:
            why = "%d bytes, the placeholder holds %d" % (len(sources[name]), table[name][1])
        else:
            continue
        log.warn("%s: %s -- no boot logo. The placeholder stays a pattern and U-Boot "
                 "boots without a logo." % (name, why))
        missing = [n for n in missing if n != name]
        too_big = [t for t in too_big if not t.startswith(name + " (")]
        sources.pop(name, None)
        del table[name]
    return missing, too_big


def vendor_sources(directory, table, log=console):
    """Read in the device's own files that h713-extract put down. The names in
    the table are exactly the paths below the --out of h713-extract, so this is
    a putting-together and not a matching-up. An OPTIONAL_FILES entry that is missing or too big
    leaves `table` as well, so the caller neither looks for it nor counts it; everything else
    missing is still an abort."""
    sources, missing, too_big = {}, [], []
    for name, (_off, length) in table.items():
        p = os.path.join(directory, name.replace("/", os.sep))
        if not os.path.isfile(p):
            missing.append(name)
            continue
        with open(p, "rb") as f:
            b = f.read()
        if len(b) > length:
            too_big.append("%s (%d > %d)" % (name, len(b), length))
        sources[name] = b
    missing, too_big = _sort_out_optional(sources, table, missing, too_big, "in the dump",
                                          "not in %s" % directory, log)
    if missing:
        raise RuntimeError("in %s %d file(s) are missing, e.g. %s"
                           % (directory, len(missing), ", ".join(sorted(missing)[:3])))
    if too_big:
        raise RuntimeError("does not fit into the placeholder: %s" % ", ".join(too_big))
    too_small = [n for n, b in sources.items() if len(b) < table[n][1]]
    if too_small:
        # No abort: the placeholder is filled up with zeros. But it means that
        # this firmware has other sizes than the one the image was built
        # against -- that belongs said.
        log.warn("%d file(s) are smaller than their placeholder (%s) -- the rest "
                 "is zeroed. Other firmware than when the image was built?"
                 % (len(too_small), ", ".join(sorted(too_small)[:3])))
    return sources


# ------------------------------------------------- the device's own placeholders (N2)
# On a device that already runs our layout the 44 vendor files are not gone: they sit in
# the placeholders the last install filled, and the table says where. Reading them back is
# cheaper than a dump and needs nothing the owner has to keep (doku/61 B, Marco 15.09.).

# What a filled placeholder must begin with, where the file kind says so -- the magics
# h713-extract itself checks (h713.vendorfiles: TSE_MAGIC, check_bootlogo,
# check_display_cfg, check_pq). It is the one cheap test that notices a read-back landing
# on the wrong bytes because the device was installed by a build whose placeholders lie
# somewhere else (see REPORT: they moved once, between v0.6-beta and v0.7-beta).
# Every entry is measured against the HY310's real files, not assumed: display_cfg.xml
# begins with a comment, not with "<?xml", and the ARISC firmware begins with 16 zero bytes
# (out-hy310-20260912). Whoever adds a row here holds the real file next to it first.
MAGIC = ((".TSE", b"TSE"), ("bootlogo.bmp", b"BM"), ("display_cfg.xml", b"<"),
         ("tvpq.db", b"SQLite format 3\0"))


def _unfilled(name, data):
    """A placeholder nobody has filled: still the builder's fill pattern (h713.layout),
    or all zeros -- which is what an install writes where the dump had no file, and what
    an ext4 hands out for blocks no file of this build occupies."""
    return data[:64] == pattern(name, 64) or data.count(0) == len(data)


def _wrong_kind(name, data):
    return any(name.endswith(end) and not data.startswith(magic) for end, magic in MAGIC)


def read_placeholders(disk, tab, table, log=console):
    """Read the vendor files back out of the device's own placeholders.

    `table` is the image's placeholder table (name -> byte offset in the part named by
    `platzhalter_datei`, and length); that part is written at a known LBA, so the offset is
    an LBA on the device. Nothing is trimmed: a file shorter than its placeholder was zero
    padded when it was installed and goes back in the same way.

    Returns (sources, problem). `problem` is None when the set is complete; otherwise it is
    the line that goes under the "no vendor source" block, and `sources` is unusable.
    """
    part_file = tab.get("platzhalter_datei")
    part_lba = next((t["lba"] for t in tab.get("teile", []) if t["datei"] == part_file), None)
    if part_lba is None:
        return {}, "the table names no part %s to read the placeholders out of" % part_file
    sources, missing, doubtful = {}, [], []
    for name in sorted(table):
        off, length = table[name]
        lba, skip = part_lba + off // SECT, off % SECT
        data = disk.read(lba, (skip + length + SECT - 1) // SECT)[skip:skip + length]
        if len(data) != length or _unfilled(name, data):
            missing.append(name)
        elif _wrong_kind(name, data):
            doubtful.append(name)
        else:
            sources[name] = data
    if doubtful:
        log.error("%d placeholder(s) hold something else than the file the table names: %s."
                  % (len(doubtful), ", ".join(sorted(doubtful)[:3])))
        return {}, ("this device was installed by a build whose placeholders lie elsewhere "
                    "-- give --vendor or a full dump")
    missing, _too_big = _sort_out_optional(sources, table, missing, [], "on this device",
                                           "the placeholder was never filled", log)
    if missing:
        return {}, ("the device has no %s -- give --vendor"
                    % ", ".join(sorted(missing)[:3]))
    log.ok("%d files read back from the device's own placeholders" % len(sources))
    return sources, None


def no_vendor_source(dump_dir, count, log=console, extra=None):
    """Exit 8: nothing to fill the placeholders with. Unchanged for a stock device; the
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
    placeholders. Returns (offset, env dict) or None (no block, wrong part) -- a broken CRC
    is reported and returned as (offset, None)."""
    block = (tab.get("bausteine") or {}).get("env")
    if not block:
        return None
    part_lba = next((t["lba"] for t in tab["teile"] if t["datei"] == part_file), None)
    if part_lba is None or block["lba"] < part_lba:
        log.warn("the environment does not lie in the part with the placeholders -- carry-over skipped")
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
        log.warn("the environment does not lie in the part with the placeholders -- carry-over skipped")
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

    The order is on purpose (see fill_placeholders): first a working copy of the
    part with the placeholders is filled and read back on the PC, then
    EVERYTHING goes onto the eMMC in one go. An abort on the PC costs nothing;
    an abort in the middle of a second write pass would have left half a system.
    """
    console.step(4, "Check the image (%s, %s)" % (tab.get("abbild"), tab.get("layout")))
    check_package(directory, tab, console)
    console.info("Hole at LBA %d..%d (%s) -- stays untouched"
                 % (tab["loch"]["lba"], tab["loch"]["lba"] + tab["loch"]["sektoren"] - 1,
                    tab["loch"]["partition"]))

    table = {k: tuple(v) for k, v in tab.get("platzhalter", {}).items()}
    user = {k: tuple(v) for k, v in tab.get("platzhalter_nutzer", {}).items()}
    part_file = tab.get("platzhalter_datei")
    work = None

    # Whoever writes only ONE part -- the boot chain for instance, to renew the
    # bootloader without loading the whole system anew -- does not need the
    # placeholders: they sit in a part that is not touched at all. Without this
    # check the tool laid down a 1.15 GB working copy, filled it and threw it
    # away.
    chosen = {t["datei"] for t in tab["teile"]}
    if (table or user) and part_file not in chosen:
        console.info("placeholders skipped: %s is not written in this run"
                     % part_file)
        if args.ssh_key:
            console.warn("--ssh-key therefore has no effect")
        table, user = {}, {}

    sources = {}
    if table:
        console.step(5, "Put the device's own files in (%d placeholders)" % len(table))
        vendor = args.vendor
        if not vendor:
            full = in_dump(args.dump_dir, DUMP_FULL)
            if os.path.isfile(full):
                vendor = in_dump(args.dump_dir, EXTRACT_DIR)
                os.makedirs(vendor, exist_ok=True)
                run_extractor(full, vendor, None, search_dir=here)
            elif getattr(args, "_our_layout", False):
                # Our layout is already on the device: the files are in its placeholders,
                # so neither a dump nor --vendor is needed (N2).
                sources, problem = read_placeholders(disk, tab, table, console)
                if problem:
                    return no_vendor_source(args.dump_dir, len(table), console, problem)
            else:
                return no_vendor_source(args.dump_dir, len(table), console)
        if vendor:
            sources = vendor_sources(vendor, table, console)
            console.ok("%d files from %s" % (len(sources), vendor))

    # The user's key: same mechanics, other source. Here and not in
    # vendor_sources(), because it does not come out of the device -- and
    # because it must be settable without vendor files as well.
    if user:
        if not table:
            console.step(5, "Put your own SSH key in")
        own = user_sources(args, user, console)
        # Only the filled ones are written; an empty placeholder stays as it was
        # built (newlines), and is valid that way.
        for name in own:
            table[name] = user[name]
            sources[name] = own[name]

    if table:
        work = args.work_copy or os.path.join(args.dump_dir, WORK_COPY)
        source_part = os.path.join(directory, part_file)
        if args.no_write:
            console.info("WOULD: copy %s to %s and fill %d placeholders"
                         % (part_file, work, len(table)))
        else:
            console.info("Working copy: %s (%.0f MiB)" % (work, mib(os.path.getsize(source_part))))
            # Without a dump nobody has made the directory yet (N2).
            os.makedirs(os.path.dirname(os.path.abspath(work)), exist_ok=True)
            shutil.copyfile(source_part, work)
            fill_placeholders(work, table, sources, log=Quiet)
            bad = check_placeholders(work, table, sources)
            if bad:
                console.error("differ after filling: %s" % ", ".join(bad))
                return 9
            console.ok("%d placeholders filled and read back -- all equal" % len(table))
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
