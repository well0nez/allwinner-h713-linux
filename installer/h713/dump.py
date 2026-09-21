# SPDX-License-Identifier: GPL-2.0
"""The backup the installer takes before it writes anything: the device-only
regions, the whole eMMC, the read-back check, the manifest and the question
which of the two sizes it should be.

Stage 1 of plan doku/121: moved from hy310-install.py (I:42, 48-50, 95-101,
462-574, 925-943, 1405-1435). Every printed string is unchanged.

Stage 2, package C-B (doku/121 §4, stage 2 §"Device-unique
regions and the write lock"): the device-unique regions are looked up in the device's
own GPT BY NAME (`regions_from_gpt`) instead of standing here as constant LBAs; the
MIPS/display artefacts of both bootloader slots are saved as well; and no hash of a
device-unique region goes on screen any more. New and changed messages are English,
the German ones stage 2 does not touch stay until stage 3 translates them.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import random
import struct
import time

from .blockdev import SECT, SECTORS_EXPECTED
from .env import ENV_BYTES, ENV_CARRY_OVER, ENV_LBA, ENV_SECTORS, env_read
from .fs import Ext4, Fat, LpSuper
from .gpt import Gpt
from .install import DUMP_FULL, ask
from .log import Log, console
from .util import duration, mib

# Version of the h713-install tool (I:42), not the version of the package
# (h713.VERSION): it goes into MANIFEST.json as "tool" and into README.txt.
VERSION = "0.1 (draft, doku/110)"

# Secure storage: no partition entry points at it, its position is fixed at LBA 12288 on
# every H713 board seen so far, so it stays a RAW CONSTANT here -- there is no table to ask
# (doku/109 §2.3, I:95). The other device-only regions are looked up by name in the device's
# own GPT -- a constant LBA was the HY310's and would have saved the wrong 16 MiB on a
# HY300 T08 (A0 §5). Key: GPT name lower case -> (file name, purpose).
SECURE_STORAGE = ("secure-storage", 12288, 2048)
BY_NAME = ("private", "Reserve0", "Reserve0_a", "Reserve0_b")
# Where the two lay on the HY310 (hy310-install.py 0.1, UNIQUE_REGIONS): the last resort for a
# device whose table cannot be read or names neither of them. A guess off another board is
# still better than losing the region, but it IS a guess -- so it is taken only when the table
# offers nothing, it is said on screen, and MANIFEST.json marks the row (O1b item 2).
HY310_FALLBACK = (("private", 4891648, 32768), ("Reserve0_a", 5489664, 32768),
                  ("Reserve0_b", 5522432, 32768))
REGION_FILES = {
    "secure-storage": ("secure-storage", "HDCP keys, WLAN/BT MAC addresses, serial number"),
    "private":        ("private",        "Android secure storage partition"),
    "reserve0":       ("reserve0",       "Reserve0 (single slot)"),
    "reserve0_a":     ("reserve0-a",     "Reserve0, Slot A"),
    "reserve0_b":     ("reserve0-b",     "Reserve0, Slot B"),
}

MIPS_DIR = "mips"                        # in the bootloader FAT, in Reserve0 and in /oem
VENDOR_MIPS = "/etc/display/mips"        # profiles/*.py -> mips.sources
PANEL_CONFIG = "panel_config.ini"
# At the ROOT of the bootloader FAT, next to mips/: since 15.09.2026 our U-Boot reads it too
# (vendorfiles.BOOT_ROOT_FILES), so the small dump carries it as well -- 6 MB per slot.
BOOT_LOGO = "bootlogo.bmp"
SLOTS = ("bootloader_a", "bootloader_b")
BOOT_CTRL_OFFSET = 2048                  # Android bootloader_control inside misc
BOOT_CTRL_MAGIC = 0x42414342


class DumpResult(list):
    """The manifest rows of `dump_small()` -- a plain list for every caller (the installer
    appends the full clone to it), plus `info` for what has no row: regions_by_name, mips,
    active_slot. `write_manifest()` picks `info` up."""

    def __init__(self, rows=()):
        list.__init__(self, rows)
        self.info = {}


def _source(disk):
    """A read-only Source over the device -- identify() hands one in, a Disk is wrapped."""
    if not hasattr(disk, "sectors"):
        return disk
    from .identify import DiskSource       # late on purpose: identify() calls us
    return DiskSource(disk)


def _gpt(q):
    """The device's GPT, or None -- our own layout and a fresh eMMC have none."""
    try:
        return Gpt(q, Log(quiet=True)) if Gpt.is_gpt(q) else None
    except Exception:                      # noqa: BLE001 -- a backup never fails on a table
        return None


def unique_regions(partitions, fallback=False, sources=None):
    """The device-unique regions of ONE partition table: {name: (first_lba, sectors)}.

    `partitions` is [(name, first lba, sectors)] as the table spells them -- the device's own
    GPT, or the rows identify() read out of an image's sys_partition.fex. Secure storage is
    fixed; private and Reserve0* are picked out by name, spelled as the table spells them --
    our own layout has none of them.

    fallback: when the table names no `private` -- resp. no `Reserve0*` at all -- put the
    HY310's own LBAs in for that one group (O1b item 2). `sources`, if a dict is handed in,
    is filled with where each region's position came from: "fixed", "gpt", "hy310-constant".

    This is the one place that answers "which regions exist only on this device". `dump`
    asked it through regions_from_gpt() and identify() had its own copy without the
    fallback, so on a stock table that names neither region the two judged differently
    (O1b follow-up b, doku/61).
    """
    out = collections.OrderedDict()
    said = {} if sources is None else sources
    out[SECURE_STORAGE[0]] = (SECURE_STORAGE[1], SECURE_STORAGE[2])
    said[SECURE_STORAGE[0]] = "fixed"
    spelling = dict((name.lower(), (name, lba, sectors)) for name, lba, sectors in partitions)
    for wanted in BY_NAME:
        found = spelling.get(wanted.lower())
        if found is not None:
            out[found[0]] = (found[1], found[2])
            said[found[0]] = "gpt"
    if fallback:
        from_table = [name.lower() for name in out]
        for name, lba, sectors in HY310_FALLBACK:
            group = "reserve0" if name.lower().startswith("reserve0") else "private"
            if not any(n.startswith(group) for n in from_table):
                out[name], said[name] = (lba, sectors), "hy310-constant"
    return out


def regions_from_gpt(disk, fallback=False, sources=None):
    """unique_regions() of the partition table the device in front of us carries."""
    gpt = _gpt(_source(disk))
    rows = [] if gpt is None else [(name, lba, sectors)
                                   for name, (lba, sectors) in gpt.parts.items()]
    return unique_regions(rows, fallback, sources)


def _region_file(name):
    """(file name, purpose) for a region name as the GPT spells it."""
    return REGION_FILES.get(name.lower(), (name.lower(), "device-unique region %s" % name))


def dump_small(disk, target, log=console, our_layout=False, regions=None):
    """Only the regions that exist nowhere else (doku/110 §2).

    our_layout: the GPT carries hy310-* (device_kind). Only then does a U-Boot
    environment lie at LBA 14336; on a stock device Android lies there, and a
    random CRC would be no detection but a coincidence.

    regions: {name: (lba, sectors)} as identify() found them -- by default looked
    up here, never from constants (stage 2 C-B).
    """
    os.makedirs(target, exist_ok=True)
    manifest = DumpResult()
    empty = []
    found_by = {}
    if regions is None:
        # No fallback on our own layout: it has no `private` and no `Reserve0*` at all, and
        # 48 MiB of zeros off the HY310's LBAs would be a backup of nothing (O1b item 2).
        regions = regions_from_gpt(disk, fallback=not our_layout, sources=found_by)
    guessed = [n for n, s in found_by.items() if s == "hy310-constant"]
    if guessed:
        log.warn("This device's partition table names no %s." % ", ".join(guessed))
        log.info("  Saved from the HY310's own LBAs instead. That is a guess, not a")
        log.info("  reading: MANIFEST.json marks those rows with source hy310-constant.")
    sources = collections.OrderedDict()
    for name, (lba, sectors) in regions.items():
        file_name, purpose = _region_file(name)
        sources[file_name] = found_by.get(
            name, "fixed" if name == SECURE_STORAGE[0] else "gpt")
        data = disk.read(lba, sectors)
        path = os.path.join(target, "%s.bin" % file_name)
        with open(path, "wb") as f:
            f.write(data)
        try:
            os.chmod(path, 0o600)      # key material: the owner only
        except OSError:
            pass
        h = hashlib.sha256(data).hexdigest()
        # A region that is empty throughout means: nothing stands here (any more).
        # On a stock device that is unusual -- it has probably been converted once.
        is_empty = data.count(0) == len(data)
        if is_empty:
            empty.append(file_name)
        manifest.append((file_name, lba, sectors, h, purpose + (" [empty]" if is_empty else "")))
        # The hash goes into the manifest (verification), but NOT onto the screen:
        # each of these regions is a fingerprint of this one device, and users post
        # screen output in logs (issue #1). Stage 2 C-B extends that to reserve0*,
        # device-only just as much (brief CB §3); empty regions keep nothing secret.
        secret = not is_empty
        log.ok("%-16s LBA %-8d %5.1f MiB  %s%s"
               % (file_name, lba, mib(len(data)),
                  "saved (hash in the manifest)" if secret else h[:16] + "…",
                  "  (empty)" if is_empty else ""))
    if empty:
        log.warn("Empty and therefore without content: %s." % ", ".join(empty))
        log.info("  On an untouched device something would stand there. Either this")
        log.info("  device has been converted once already, or this firmware does not")
        log.info("  use the regions. The Secure Storage is independent of that.")
    # The U-Boot environment -- only on our layout is there one at all. The new
    # image replaces it with its own default; the intent keys (ENV_CARRY_OVER)
    # are carried over by write_package(), the rest lies here as uboot-env.bin
    # in case someone wants more of it back (fw_setenv).
    if our_layout:
        raw_env = disk.read(ENV_LBA, ENV_SECTORS)
        d = env_read(raw_env) if len(raw_env) == ENV_BYTES else None
        if d is not None:
            path = os.path.join(target, "uboot-env.bin")
            with open(path, "wb") as f:
                f.write(raw_env)
            h = hashlib.sha256(raw_env).hexdigest()
            intent = ", ".join("%s=%s" % (k, d[k]) for k in ENV_CARRY_OVER if k in d) or "no intent keys"
            manifest.append(("uboot-env", ENV_LBA, ENV_SECTORS, h,
                             "U-Boot environment, %d entries (%s)" % (len(d), intent)))
            log.ok("%-16s LBA %-8d %5.1f MiB  %s  (%d entries; %s)"
                   % ("uboot-env", ENV_LBA, mib(len(raw_env)), h[:16] + "…", len(d), intent))
        else:
            log.info("uboot-env: our layout, but no valid environment lies at LBA %d "
                     "(empty or without CRC) -- nothing to save, nothing to carry over" % ENV_LBA)
    mips, active_slot = dump_mips(disk, target, log)
    manifest.info["regions_by_name"] = not guessed
    manifest.info["region_sources"] = sources
    manifest.info["mips"] = mips
    manifest.info["active_slot"] = active_slot
    return manifest


# ----------------------------------------------------------------- MIPS/display artefacts

def active_slot_of(data):
    """The active slot out of Android's `bootloader_control` in misc (offset 2048,
    magic 0x42414342): "_a", "_b" -- or None when it does not decode or two slots are
    equally good. Best effort, never an error."""
    if len(data) < BOOT_CTRL_OFFSET + 32:
        return None
    b = data[BOOT_CTRL_OFFSET:BOOT_CTRL_OFFSET + 32]
    if struct.unpack_from("<I", b, 4)[0] != BOOT_CTRL_MAGIC:
        return None
    best, best_priority = None, 0
    for i in range(max(2, min(4, b[9] & 0x07))):          # nb_slot
        priority = b[12 + 2 * i] & 0x0F                   # slot_info[i].priority
        if priority > best_priority:
            best, best_priority = i, priority
        elif priority == best_priority:
            best = None                                   # a tie is not an answer
    return None if best is None else "_" + "abcd"[best]


def _from_fat(gpt, q, part, extras=()):
    """(files, reason) -- everything under mips/ of a FAT partition, plus the named
    files from its root. `reason` says in plain words why there is nothing."""
    sub = gpt.partition(q, part)
    if sub is None:
        return None, "no partition %s in the GPT" % part
    try:
        if not Fat.is_fat(sub):
            return None, "%s carries no FAT filesystem" % part
        fs = Fat(sub, Log(quiet=True), part)
        entries = fs.directory(MIPS_DIR)
        if entries is None and not extras:
            return None, "%s has no mips/ directory" % part
        files = collections.OrderedDict()
        for e in sorted(entries or [], key=lambda x: x["name"]):
            if not e["verzeichnis"]:
                files[e["name"]] = fs.read(e)
        for e in sorted(fs.entries(0), key=lambda x: x["name"]):
            if not e["verzeichnis"] and e["name"].lower() in extras:
                files[e["name"]] = fs.read(e)
        return (files, None) if files else (None, "%s holds none of the files we look for" % part)
    except Exception as e:                    # noqa: BLE001 -- best effort, never an error
        return None, "%s not readable (%s)" % (part, e)


def _from_ext4(source, label, where, extras=()):
    """The same out of an ext4 filesystem: everything under `where`, plus `extras`."""
    if source is None:
        return None, "%s is not there or not readable" % label
    try:
        fs = Ext4(source, None, label, Log(quiet=True))
        files = collections.OrderedDict()
        for e in sorted(fs.ls(where), key=lambda x: x["name"]):
            if e["typ"] != "d":
                files[e["name"]] = fs.read("%s/%s" % (where.rstrip("/"), e["name"]))
        for e in sorted(fs.ls("/"), key=lambda x: x["name"]):
            if e["typ"] != "d" and e["name"].lower() in extras:
                files[e["name"]] = fs.read("/" + e["name"])
        return (files, None) if files else (None, "%s holds none of the files we look for" % label)
    except Exception as e:                    # noqa: BLE001
        return None, "%s not readable (%s)" % (label, e)


def _vendor_of(gpt, q):
    """The vendor filesystem inside `super` (LP metadata), or None."""
    try:
        sup = gpt.partition(q, "super")
        quiet = Log(quiet=True)
        lp = LpSuper(sup, quiet) if sup is not None else None
        for name in ("vendor_a", "vendor_b", "vendor"):
            ven = lp.partition(name, quiet) if lp is not None else None
            if ven is not None:
                return ven
    except Exception:                         # noqa: BLE001 -- best effort
        pass
    return None


def _store(out, target, where, found, log):
    """One source's result: saved to <target>/mips/<where>/, or named and skipped."""
    files, why = found
    out[where] = None
    if not files:
        log.info("mips/: %s" % why)
        return
    directory = os.path.join(target, MIPS_DIR, where)
    os.makedirs(directory, exist_ok=True)
    saved = collections.OrderedDict()
    for name, data in files.items():
        with open(os.path.join(directory, os.path.basename(name.replace("\\", "/"))), "wb") as f:
            f.write(data)
        saved[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    out[where] = saved
    log.ok("%-16s %2d files  %5.1f MiB  -> %s/%s/"
           % (where, len(saved), mib(sum(len(d) for d in files.values())), MIPS_DIR, where))


def dump_mips(disk, target, log=console):
    """The MIPS/display artefacts into <target>/mips/: both bootloader slots, the
    vendor copy under /etc/display/mips and the overrides (panel_config.ini, mips/)
    in Reserve0 and in media_data (/oem). Returns (mips, active_slot). Best effort:
    a source that cannot be read is named and skipped -- the dump is the user's
    failsafe and must not fail on an unusual filesystem.
    """
    out = collections.OrderedDict()
    q = _source(disk)
    gpt = _gpt(q)
    if gpt is None:
        log.info("mips/: this device has no readable partition table -- nothing to look for")
        return out, None
    for slot in SLOTS:
        _store(out, target, slot, _from_fat(gpt, q, slot, (BOOT_LOGO,)), log)
    both = [out[s] for s in SLOTS]
    if any(out[s] is None and s in gpt.parts for s in SLOTS):
        log.info("mips/: a bootloader slot without mips/ is the normal state of the ADT-3 family")
    elif all(b is not None for b in both):
        same = both[0] == both[1]
        (log.ok if same else log.warn)(
            "mips/: the two bootloader slots hold %s"
            % ("the same %d files" % len(both[0]) if same else "DIFFERENT files"))
    misc = gpt.partition(q, "misc")
    active = active_slot_of(misc.read(0, BOOT_CTRL_OFFSET + 32)) if misc is not None else None
    log.info("mips/: active slot %s" % (active or "unknown (no readable bootloader_control)"))
    _store(out, target, "vendor", _from_ext4(_vendor_of(gpt, q), "vendor", VENDOR_MIPS), log)
    part = ([p for p in ("Reserve0", "Reserve0_a", "Reserve0_b") if p in gpt.parts] + [None])[0]
    _store(out, target, "reserve0", _from_fat(gpt, q, part, (PANEL_CONFIG,)) if part
           else (None, "no Reserve0 partition in the GPT"), log)
    _store(out, target, "media_data",
           _from_ext4(gpt.partition(q, "media_data"), "media_data", "/" + MIPS_DIR, (PANEL_CONFIG,)), log)
    return out, active


def dump_full(disk, file, log=console):
    """The whole eMMC, with progress. That is the user's failsafe."""
    total = disk.sectors * SECT
    chunk = 4 << 20
    h = hashlib.sha256()
    done = 0
    t0 = time.time()
    with open(file, "wb") as f:
        while done < total:
            n = min(chunk, total - done)
            b = disk.read(done // SECT, n // SECT)
            if len(b) != n:
                raise RuntimeError("only %d of %d bytes read at %d" % (len(b), n, done))
            f.write(b)
            h.update(b)
            done += n
            if done % (256 << 20) == 0 or done == total:
                speed = done / max(time.time() - t0, 0.001)
                left = (total - done) / max(speed, 1)
                log.info("  %5.1f%%  %6.1f MiB/s  %s left" %
                         (100.0 * done / total, mib(speed), duration(left)))
        f.flush()
        os.fsync(f.fileno())
    return h.hexdigest(), time.time() - t0


def verify_dump(disk, file, samples=8):
    """Compare the freshly taken dump against the device. Fixed places
    (start, boot chain, secure storage, end) plus random (finding S46 B5)."""
    total = os.path.getsize(file)
    fixed = [0, 1, 16, 2048, 12288, 14336, 16384, disk.sectors - 8]
    places = fixed + [random.randrange(0, disk.sectors - 64)
                      for _ in range(max(0, samples - len(fixed)))]
    bad = 0
    with open(file, "rb") as f:
        for lba in places:
            n = 8
            if (lba + n) * SECT > total:
                continue
            f.seek(lba * SECT)
            want = f.read(n * SECT)
            if disk.read(lba, n) != want:
                bad += 1
    return bad


def manifest_row(dump_dir, name):
    """The MANIFEST.json row of one region of a dump directory, or None.

    None also means "this directory keeps no record of ours": a dump of v0.5-beta writes German
    keys, and a file copied in by hand brings no manifest at all. Callers say what they make of
    that -- `full_dump_state()` replaces such a clone, `install` reads it when it is exactly as
    long as the device (install.full_dump_problem).
    """
    try:
        with open(os.path.join(dump_dir, "MANIFEST.json"), "rb") as f:
            rows = json.load(f).get("regions") or []
    except (OSError, ValueError):
        return None
    return next((entry for entry in reversed(rows) if entry.get("name") == name), None)


def full_dump_state(dump_dir, file, disk_sectors):
    """Is the full dump already in this directory, and is it whole? -> (row, why).

    O1b item 1 (seen 15.09.2026): a second `--full` run into the same `--dump` directory
    truncated the clone that was the way back. `row` is the manifest row of a complete file,
    for the caller to carry over instead of taking a second 17-minute dump; `why` names in one
    line what is wrong with one that is not, so the caller can say what it replaces. Complete
    means: MANIFEST.json lists emmc-full, its sector count is the count of the device in front
    of us, and the file is exactly that many bytes -- an aborted run leaves a shorter one.
    """
    if not os.path.isfile(file):
        return None, None
    name, shown = DUMP_FULL[:-4], os.path.basename(file)
    row = manifest_row(dump_dir, name)
    if row is None:
        return None, "%s lies here but no MANIFEST.json row names it" % shown
    sectors = int(row.get("sectors") or 0)
    if sectors != disk_sectors:
        return None, ("%s was taken off a disk of %d sectors, this one has %d"
                      % (shown, sectors, disk_sectors))
    have = os.path.getsize(file)
    if have != sectors * SECT:
        # Bytes, not MiB: an aborted run can be a single sector short, and "7456.0 of
        # 7456.0 MiB" would tell the user nothing about what is wrong with the file.
        return None, ("%s is incomplete: %d bytes, the manifest records %d (%.1f MiB)"
                      % (shown, have, sectors * SECT, mib(sectors * SECT)))
    return (name, 0, sectors, row.get("sha256"), row.get("purpose") or "complete clone"), None


def board_of(args):
    """The board identify() settled on, by the name its profile carries -- None when nothing
    identified this device (`--skip-identify`). For the texts that would otherwise name the
    HY310 on somebody else's board (R1 item 4)."""
    return (getattr(args, "_profile", None) or {}).get("name")


def write_manifest(directory, manifest, device, board=None):
    # Stage 3: the keys are English (api-stufe3.md) -- "erzeugt"/"werkzeug"/"geraet"/
    # "sektoren"/"teile" became created/tool/device/sectors/regions, the row keys
    # "sektoren"/"zweck" sectors/purpose. The file names inside the dump are unchanged.
    data = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": "h713-install " + VERSION,
        "device": device,
        "board": board,
        "sectors": SECTORS_EXPECTED,
        "regions": [{"name": n, "lba": l, "sectors": s, "sha256": h, "purpose": p}
                    for n, l, s, h, p in manifest],
    }
    # Stage 2 C-B: regions_by_name, mips and active_slot ride on dump_small()'s result
    # (DumpResult.info), so that no caller has to hand them in.
    data.update(getattr(manifest, "info", {}))
    # O1b item 2: every region row says where its LBA came from -- "gpt" the device's own
    # table, "hy310-constant" the fallback, "fixed" the raw secure-storage LBA. It rides in
    # the row and not once more beside it, so a reader sees it where the LBA stands.
    sources = data.pop("region_sources", None) or {}
    for row in data["regions"]:
        if row["name"] in sources:
            row["source"] = sources[row["name"]]
    saved = ["%s/%s" % (MIPS_DIR, name)
             for name, files in (data.get("mips") or {}).items() if files]
    with open(os.path.join(directory, "MANIFEST.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(directory, "README.txt"), "w") as f:
        # R1 item 4: the heading named the HY310, and this dump is taken on whatever board the
        # owner has (boards/, issue #1). Which board it was stands in the line below it -- when
        # the identification knew it, and not as a guess when it did not.
        f.write(
            "Dump of an H713 projector\n"
            "=========================\n\n"
            "Created on %s by h713-install %s.\n"
            "%s\n"
            "What lies here:\n%s\n"
            "Restoring (put the device into FEL mode first: hold reset,\n"
            "plug the power in):\n\n"
            "    h713-install restore emmc-full.img --uboot <u-boot.bin>\n\n"
            "The single .bin files are raw regions of the eMMC. They stand in no\n"
            "firmware image -- without them the device loses HDCP, its MAC\n"
            "addresses and its serial number. Keep them well.\n"
            % (data["created"], VERSION,
               "Board: %s.\n" % board if board else "",
               "".join("  %-18s %s\n" % (t["name"] + (".img" if t["name"] == "emmc-full" else ".bin"),
                                           t["purpose"])
                       for t in data["regions"])))
        if saved:
            f.write("\nDisplay firmware:\n%s"
                    "These directories hold the MIPS/display files of this device -- the\n"
                    "bootloader slots, the vendor copy and the overrides found in Reserve0\n"
                    "and media_data. MANIFEST.json lists every file with its sha256.\n"
                    % "".join("  %s/\n" % name for name in saved))


def dump_asked(args):
    """Did this run ask for a dump of its own? An explicit `--dump DIR` or a size
    (`--small`/`--full`) is a yes; the defaults are not (N2). Only our own layout ever
    asks -- on a stock device the dump is mandatory and nobody is asked."""
    return bool(getattr(args, "_dump_given", False) or getattr(args, "size", None))


def keep_copy(disk):
    """What a skipped small dump would have left behind for the steps that come after it:
    the secure storage (the installer compares against it once everything is written) and
    the U-Boot environment (the intent keys are carried over from it). Read before the
    write, kept in memory, never written anywhere (N2)."""
    return {"secure-storage": disk.read(SECURE_STORAGE[1], SECURE_STORAGE[2]),
            "uboot-env": disk.read(ENV_LBA, ENV_SECTORS)}


def mandatory_dump(args, disk, path, log=console):
    """Plan 110 §2: the small dump before every write. It costs seconds and saves what no
    image brings back (finding S46 B2).

    Stage 2 C5 (Marco, 14.09.): only while the device still carries the stock layout -- on
    our own layout nothing stock-specific is left to save, and the dump has existed since
    the first installation. Stage 3 moved it here out of the installer, where it stood
    three times over (doku/121 §1 point 3). N2: `--dump DIR` takes one on our layout too --
    it is cheap, and the user asked for it.
    """
    if args.no_write:
        return
    if args._our_layout and not dump_asked(args):
        log.info("Our layout is on the device: no mandatory dump before the restore "
                 "(nothing stock-specific is left to save; use the dump of your first install).")
        return
    console.step(2, "Small dump (mandatory, before a restore too)")
    os.makedirs(args.dump_dir, exist_ok=True)
    write_manifest(args.dump_dir, dump_small(disk, args.dump_dir, our_layout=args._our_layout),
                   path, board_of(args))


def choose_dump(chosen=None):
    """"small" or "full" -- `chosen` is what --small/--full said, None means ask."""
    if chosen:
        return chosen
    console.info("")
    console.info("The dump is your backup. Two sizes:")
    console.info("")
    console.info("  small  49 MiB, about 10 seconds.")
    console.info("         Everything that exists ONLY on this device: HDCP keys,")
    console.info("         the MAC addresses of WLAN and Bluetooth, the serial number.")
    console.info("         No firmware image in the world brings that back.")
    console.info("")
    console.info("  full   7.3 GB, about 17 minutes.")
    console.info("         The whole eMMC. With it you restore your device 1:1,")
    console.info("         Android included, without downloading anything.")
    console.info("")
    # "voll"/"klein" stay accepted for one release, like JA at the confirmation.
    answer = ask("  Which dump? [small/full] ", "small")
    return "full" if answer.startswith(("f", "v")) else "small"
