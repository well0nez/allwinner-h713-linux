# SPDX-License-Identifier: GPL-2.0
"""Which device is this? -- one answer for an image, a raw dump and a device.

Stage 2 C1/C6 (doku/121 section 2, findings 1 and 6): the installer decided "known device, may
write" on a single string, the vendor `build_fingerprint`. The three ADT-3 boards share it, so a
HY350 passed as an HY300 Pro. `identify()` reads every feature the board profiles carry, compares
each profile against the features *that* profile calls strong, and when nothing matches it prints
what it saw in the field names `h713_probe` uses -- so a stranger can post the row as it stands.

`identify_device()` is the installer's old call site (same reads, same keys); stage 3 wired the
installer onto `identify()` and translated every text of both.

Tables and feature helpers come from h713-extract (X:178-207), the drive side from
hy310-install.py (I:1456-1620).
"""

from __future__ import annotations

from typing import Optional, Tuple

from h713.blockdev import device_kind, is_our_layout
from h713.dump import unique_regions
from h713.facts import (DiskSource, MIPS_SOURCES, as_source, close_source, device_facts,
                        image_facts, VENDOR_PARTITIONS)
from h713.fs import Ext4, LpSuper
from h713.gpt import Gpt
from h713.imagewty import Imagewty
from h713.log import Log, console
from h713.profiles import (FEATURE_VOCABULARY, PROFILES, UBOOT_FW_REVS, expected_features,
                           legacy_devices, strong_features_of)
from h713.util import SECTOR, sha256_bytes

# Features a device is recognised by even without an image fingerprint (--part, --fex-dir, --no-hash).
# Order = weight of evidence. Of the MIPS artefacts exactly one file tells two devices apart:
# mips/database.TSE (0.3, S42 §9) -- with it even a bare bootloader partition can be assigned.
ID_FEATURES = FEATURE_VOCABULARY
# X:181 the old global list; it stays because the extractor reads it. Which features pin down *one*
# board is a property of that board -- profiles[..]["stock"]["strong_features"], and that is what
# match_profiles() asks (stage 2 C6: the ADT-3 profiles do not list build_fingerprint).
STRONG_FEATURES = ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
                   "build_fingerprint", "mips_database_sha256")
# The rows a profile needs, in the names h713_probe prints (docs/tools/h713-probe.md).
ROW_FEATURES = ("sunxi_version", "build_fingerprint", "uboot_version", "arisc_version", "scp_sha256",
                "uboot_sha256", "dtb_sha256", "dtb_compatible", "mips_database_sha256", "vendor_size",
                "display_bin_size", "display_bin_sha256", "project_id", "panel")


def features_of(profile: dict) -> dict:
    """X:185 -- what a legacy_devices() row or a board profile declares (h713.profiles)."""
    return expected_features(profile)


def feature_matches(name: str, actual, expected) -> bool:
    if name in ("uboot_version", "arisc_version"):
        return str(actual).startswith(str(expected))
    return actual == expected


# Whole input files recognised by their sha256 -> device (profile key), description
KNOWN_IMAGES = {
    "c518251a00b5cc7b0404e0bb479dc4f18a7558af6df97e9e999d81b31ef3c25d": ("hy310", "HY310 update.img (stock)"),
    "64c629b15538f897f40caf446a52862a92234797328fbb17bc9fd073354a50d6": ("hy310", "HY310 update_rooted.img (stock + root, same firmware)"),
    "812392c7d3de68433b0716aa94155c38d87898956b9fc7e4998cb12b9e111066": ("l018", "L018 update.img (stock)"),
    "5d2c5e1d2c4a3af6accfdcb6f5fdff8d88aec055743ffe29b82ceccff0c74851": ("hy310", "HY310 dev device, raw eMMC dump LBA 0..614399 (300 MiB)"),
}


# The revision lookup lives in h713.vendorfiles (the whole FIRMWARE_REVISIONS table, stage 2 C7);
# re-exported here because identify's callers and the probe row use it (Fable, C-A merge).
from h713.vendorfiles import firmware_revision_of   # noqa: E402,F401


def _files_dict(entries):
    """A [{name, size, sha256}] list of h713.facts back as name -> {size, sha256}."""
    return dict((e["name"], {"sha256": e["sha256"], "size": e["size"]}) for e in entries or [])


def _panel_value(facts, field):
    """One field of panel_config.ini -- the Reserve0 copy is the one U-Boot reads."""
    entry = (facts.get("panel_config") or {}).get(field) or {}
    return entry.get("reserve0") if entry.get("reserve0") is not None else entry.get("vendor")


def features_from_facts(facts: dict) -> dict:
    """Every identification feature plus what a profile row needs, None where unreadable."""
    package = facts.get("boot_package") or {}
    items = dict((i["name"], i) for i in package.get("items") or [])
    mips = facts.get("mips_files") or {}
    database = [_files_dict(e).get("database.TSE", {}).get("sha256")
                for e in mips.get("sources", {}).values()]
    sizes = dict((p["name"], p["size"]) for p in (facts.get("super") or {}).get("partitions") or [])
    display = mips.get("display_bin") or {}
    width, height = _panel_value(facts, "PanelWidth"), _panel_value(facts, "PanelHeight")
    return {
        "scp_sha256": items.get("scp", {}).get("sha256"),
        "uboot_sha256": items.get("u-boot", {}).get("sha256"),
        "dtb_sha256": items.get("dtb", {}).get("sha256"),
        "uboot_version": package.get("uboot_version"),
        "arisc_version": package.get("arisc_version"),
        "build_fingerprint": (facts.get("vendor_build_prop") or {}).get("ro.vendor.build.fingerprint"),
        "mips_database_sha256": next((h for h in database if h), None),
        "sunxi_version": facts.get("sunxi_version"),
        "vendor_size": next((sizes[n] for n in VENDOR_PARTITIONS if n in sizes), None),
        "dtb_compatible": package.get("dtb_compatible"),
        "dram": (facts.get("boot0") or {}).get("dram"),
        "dram_clk_mhz": (facts.get("boot0") or {}).get("dram_clk_mhz"),
        "display_bin_sha256": display.get("sha256"),
        "display_bin_size": display.get("size"),
        "project_id": _panel_value(facts, "ProjectID"),
        "panel": None if not width or not height else "%dx%d" % (width, height),
    }


def match_profiles(features: dict, profiles=None):
    """(profile id or None, candidates, matches) -- every profile whose strong features all agree.

    Strong is per profile (`stock.strong_features`): `build_fingerprint` and `mips_database_sha256`
    count only where a profile lists them, because the three ADT-3 boards share both (doku/121
    section 2, finding 1). A feature neither side supplies is no evidence and is recorded as None;
    a profile with no comparable feature at all (HY300 Pro) is never a candidate, and two
    candidates mean ambiguous -- then there is no profile.
    """
    profiles = PROFILES if profiles is None else profiles
    matches, candidates = {}, []
    for board_id, profile in profiles.items():
        expected = expected_features(profile)
        row, compared, agrees = {}, 0, True
        for name in strong_features_of(profile):
            actual, want = features.get(name), expected.get(name)
            if actual is None or want is None:
                row[name] = None
                continue
            row[name] = feature_matches(name, actual, want)
            compared += 1
            agrees = agrees and row[name]
        matches[board_id] = row
        if compared and agrees:
            candidates.append(board_id)
    return (candidates[0] if len(candidates) == 1 else None), candidates, matches


def _layout_of(facts: dict) -> dict:
    """entries, partitions (name, start LBA, sectors), disk size, layout disagreements.

    An image's partitions are the rows of sys_partition.fex -- that is what the device follows,
    not sunxi_gpt.fex (doku/121 section 2, finding 6); a device has only its GPT entries. The
    disk size is what the table describes, not what was handed in: a raw dump is usually shorter.
    """
    header = ((facts.get("gpt") or facts.get("sunxi_gpt")) or {}).get("header") or {}
    partitions = [(p["name"], p["start_lba"], p["sectors"]) for p in facts.get("sys_partition") or []]
    if not partitions:
        entries = ((facts.get("gpt") or facts.get("sunxi_gpt")) or {}).get("entries") or []
        partitions = [(e["name"], e["first"], e["last"] - e["first"] + 1) for e in entries]
    return {"entries": header.get("entries") or len(partitions), "partitions": partitions,
            "disk_sectors": header["last_usable"] + 34 if header.get("last_usable")
            else (facts.get("input") or {}).get("size", 0) // SECTOR or None,
            "consistency": list(facts.get("layout_consistency") or [])}


def _regions_of(layout: dict, kind: str, sources=None) -> dict:
    """The regions no firmware image brings back, found BY NAME (I:95 EINMALIG, generalised).

    secure-storage is fixed for every H713; private and Reserve0* come from the table of this very
    device, never from the HY310 constants -- the HY300 Pro has one Reserve0 elsewhere (issue #1).

    The picking-out is `dump.unique_regions()`, the call the dump makes, fallback included, so
    the two tools cannot judge one table differently (O1b follow-up b). `sources` records which
    names the fallback had to supply -- the report says so, because it is a guess.
    """
    return unique_regions(layout["partitions"], fallback=kind != "ours", sources=sources)


def _mips_of(facts: dict) -> dict:
    """Where the display firmware sits: per bootloader slot, plus the copy inside Android."""
    if facts.get("mips"):
        return dict(facts["mips"])
    sources = (facts.get("mips_files") or {}).get("sources") or {}
    fat = _files_dict(sources.get(MIPS_SOURCES[0])) or None
    supplies = dict((p["name"], p["downloadfile"]) for p in facts.get("sys_partition") or [])
    out = {"active_slot": None, "vendor": _files_dict(sources.get(MIPS_SOURCES[1])) or None}
    for slot in ("bootloader_a", "bootloader_b"):
        out[slot] = fat if supplies.get(slot) == "boot-resource.fex" else None
    return out


def _kind_of(layout: dict) -> str:
    """What the partition table says -- the same test device_kind() runs, on a table we already read."""
    names = [name for name, _start, _sectors in layout["partitions"]]
    if not names:
        return "no-gpt"
    if is_our_layout(names):
        return "ours"
    if "bootloader_a" in names and "super" in names:
        return "stock"
    return "unknown-gpt"


def _profile_row(ident: dict, add) -> None:
    """The fields a profile needs, in the names h713_probe prints -- to be posted as they stand."""
    features = ident["features"]
    add("info", "-- profile row (post it as it stands, then this board gets a profile) --")
    add("info", "%-21s %s, %s" % ("input", ident["input"], ident["kind"]))
    add("info", "%-21s %d" % ("partitions", len(ident["layout"]["partitions"])))
    for name in ROW_FEATURES:
        value = features.get(name)
        if name == "project_id" and isinstance(value, int):
            value = "0x%02x" % value
        add("info", "%-21s %s" % (name, "-" if value is None else value))
    for name, value in (features.get("dram") or {}).items():
        add("info", "dram_%-6s 0x%08x%s" % (name, value, "   MHz: %d" % value if name == "clk" else ""))


def _render(ident: dict) -> list:
    """The lines report_device() prints, as (level, text)."""
    lines = []

    def add(level, text):
        lines.append((level, text))

    board = PROFILES.get(ident["profile"] or "", {}).get("name", ident["profile"])
    where = "%s (%s)" % (ident["input"], ident["kind"])
    if ident["profile"] and ident["status"] == "verified":
        add("ok", "%s recognised -- %s, verified profile" % (board, where))
    elif ident["profile"]:
        add("warn", "%s matches this %s, but its profile is '%s', not verified -- no writing."
            % (board, ident["input"], ident["status"]))
    elif len(ident["candidates"]) > 1:
        add("warn", "Several profiles match this %s (%s) -- it stays unidentified."
            % (ident["input"], ", ".join(ident["candidates"])))
    elif ident["kind"] == "ours":
        # Our own layout: no Android, no vendor U-Boot, nothing a profile could match on --
        # and nothing to post. The way back to the vendor firmware is what matters here.
        add("ok", "our layout (v3, doku/109) on this %s -- this project's image is installed"
            % ident["input"])
    else:
        add("warn", "No profile matches this %s." % where)
    hit = [name for name, ok in (ident["matches"].get(ident["profile"]) or {}).items() if ok]
    if hit:
        add("info", "matched on %s" % ", ".join(sorted(hit)))
    if ident["features"].get("build_fingerprint"):
        add("info", "fingerprint %s" % ident["features"]["build_fingerprint"])
    layout = ident["layout"]
    add("info", "layout    %s, %d partitions, %s sectors"
        % (ident["kind"], len(layout["partitions"]),
           "?" if layout["disk_sectors"] is None else layout["disk_sectors"]))
    if layout["consistency"]:
        # One line, not one per partition: an image whose two tables drift apart drifts from
        # the first one on, and the rest is arithmetic (doku/60 point 12). `restore-stock`
        # prints the whole comparison, because there it decides what is written.
        add("warn", "sunxi_gpt.fex and sys_partition.fex disagree on %d %s (from %s on) "
                    "-- the device follows sys_partition.fex"
            % (len(layout["consistency"]),
               "partition" if len(layout["consistency"]) == 1 else "partitions",
               layout["consistency"][0]["name"]))
    if ident["regions"]:
        add("info", "device-only %s" % ", ".join("%s@%d+%d" % (n, r[0], r[1])
                                                 for n, r in sorted(ident["regions"].items())))
    guessed = sorted(n for n, where in (ident.get("region_sources") or {}).items()
                     if where == "hy310-constant")
    if guessed:
        # The same guess the dump makes, and said in the same breath: this table names the
        # region nowhere, so the HY310's own LBA stands in for it (O1b item 2).
        add("warn", "this table names no %s -- the HY310's own LBAs stand in above, which is "
                    "a guess, not a reading" % ", ".join(guessed))
    mips = ident["mips"]
    found = ["%s %d files" % (k, len(mips[k])) for k in ("bootloader_a", "bootloader_b", "vendor")
             if mips.get(k)]
    if found:
        add("info", "display firmware in %s%s"
            % (", ".join(found), " (active slot %s)" % mips["active_slot"] if mips["active_slot"] else ""))
    if ident["profile"] is None and ident["kind"] != "ours":
        _profile_row(ident, add)
    return lines


def identify(source, *, log=None) -> dict:
    """What is this? An IMAGEWTY image, a raw dump or the device itself (api-stufe2.md).

    Never writes. Reads what it needs and nothing more: the partition table, boot0 at LBA 16, the
    boot package at LBA 24576, the vendor build.prop through super/LP/ext4, the MIPS files of the
    bootloader FAT and panel_config.ini -- about 1.2 MiB plus the display firmware.
    """
    q = as_source(source)
    reader_log = Log(quiet=True) if log is None else log
    try:
        if Imagewty.is_imagewty(q):
            kind_of_input, facts = "image", image_facts(q, reader_log)
        else:
            kind_of_input = "device" if isinstance(q, DiskSource) else "dump"
            facts = device_facts(q, reader_log)
    finally:
        if q is not source:
            close_source(q)
    features = features_from_facts(facts)
    profile, candidates, matches = match_profiles(features)
    layout = _layout_of(facts)
    kind, region_sources = _kind_of(layout), {}
    # "facts" is everything that was read, so no later step has to open the device a second
    # time; it is an addition to the dict of api-stufe2.md, not part of its contract. So is
    # "region_sources": name -> fixed | gpt | hy310-constant, the same key MANIFEST.json uses.
    ident = {"input": kind_of_input, "kind": kind, "profile": profile,
             "status": PROFILES[profile]["status"] if profile else None, "candidates": candidates,
             "features": features, "matches": matches, "layout": layout,
             "regions": _regions_of(layout, kind, region_sources),
             "region_sources": region_sources, "mips": _mips_of(facts), "facts": facts}
    # "text" is what report_device() prints; "_lines" carries the level per line, because a
    # warning must not arrive as a success (the api names only the plain lines).
    ident["_lines"] = _render(ident)
    ident["text"] = [text for _level, text in ident["_lines"]]
    return ident


# --------------------------------------------------------------------------------- the old call site

def vendor_fingerprint(disk, log):
    """The vendor build.prop the old way: GPT -> super -> LP metadata -> vendor -> build.prop.

    About 1.2 MiB, so fractions of a second; reading the whole eMMC takes 17 minutes. Returns
    (fingerprint or None, name of the LP partition or None) and warns exactly as before.
    """
    found = None                                # the old code set out["lp_partition"] here, so a
    try:                                        # failure further down keeps the name it had found
        q = DiskSource(disk)
        quiet = Log(quiet=True)
        gpt = Gpt(q, quiet)
        sup = gpt.partition(q, "super")
        if sup is None:
            log.warn("Device identification: no partition 'super'")
            return None, found
        lp = LpSuper(sup, quiet)
        # In super the names carry the slot suffix ("vendor_a"), on older
        # states without. First the active slot, then the other, then without.
        ven = None
        for name in ("vendor_a", "vendor_b", "vendor"):
            ven = lp.partition(name, quiet)
            if ven is not None:
                found = name
                break
        if ven is None:
            # known bug, stage 2 C: `%` binds tighter than `or`, so the fallback
            # "none" can never appear -- the formatted line is always truthy.
            log.warn("Device identification: no LP partition 'vendor' (found: %s)"
                     % ", ".join(getattr(lp, "parts", {})) or "none")
            return None, found
        fs = Ext4(ven, None, "vendor", quiet)
        if not fs.exists("/build.prop"):
            log.warn("Device identification: /build.prop is missing in vendor")
            return None, found
        text = fs.read("/build.prop").decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        log.warn("Device identification aborted: %s" % e)
        return None, found
    for line in text.splitlines():
        if line.startswith("ro.vendor.build.fingerprint="):
            return line.split("=", 1)[1].strip(), found
    log.warn("Device identification: no ro.vendor.build.fingerprint in build.prop")
    return None, found


def identify_device(disk, extractor=None, log=console):
    """What are we dealing with? (plan 110 §8) -- the installer's old call site.

    Compatibility wrapper (doku/121 stage 2 C1): same reads, same keys, same German texts as
    before, so the golden dry-run stays byte-identical. `identify()` above is the new answer;
    the installer is wired onto it in a later step, together with the texts.

    `extractor` is the path to h713-extract. It is still taken so that callers
    do not change, and it is no longer used -- the package imports itself.

    Return: dict with 'layout', and on stock additionally 'fingerprint',
    'geraet', 'bekannt'. Never throws -- whoever does not recognise, says so.
    """
    out = {"layout": device_kind(disk.path), "fingerprint": None, "device": None, "known": False}
    # Only a stock layout has a vendor partition with build.prop. The text
    # comes from device_kind() -- "stock layout, N partitions" or
    # "our layout (...)"; check the first words, not the whole sentence
    # (the number of partitions is in it).
    if not (out["layout"] or "").startswith("stock layout"):
        return out
    out["fingerprint"], lp_partition = vendor_fingerprint(disk, log)
    if lp_partition:
        out["lp_partition"] = lp_partition
    if not out["fingerprint"]:
        return out
    for gid, profile in legacy_devices().items():
        if features_of(profile).get("build_fingerprint") == out["fingerprint"]:
            out["device"], out["known"] = profile.get("name", gid), True
            break
    return out


def interpret_fingerprint(fp) -> Tuple[str, str]:
    """Get the Android version and the build date out of the fingerprint.

    Shape (stock HY310):
      Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys
      0        1             2           ^^  3               4          ^^^^^^^^
                                  Android 11                      MMDDHHmm = 24.07., 10:19

    The build date sits as MMDDHHmm in the last number of the build field --
    that is how Android counts its builds. The year is nowhere; HY310 is 2025
    (plan 110 §8), so it is not claimed.
    """
    parts = fp.split("/")
    version = "?"
    if len(parts) > 2 and ":" in parts[2]:
        version = parts[2].rsplit(":", 1)[1] or "?"
    date = "?"
    if len(parts) > 4:
        mark = parts[4].split(":")[0]
        digits = "".join(c for c in mark if c.isdigit())
        if len(digits) == 8:
            mm, dd, hh, mi = digits[:2], digits[2:4], digits[4:6], digits[6:]
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                date = "%s.%s., %s:%s (%s)" % (dd, mm, hh, mi, mark)
            else:
                date = mark
        else:
            date = mark
    return version, date


def report_device(found, log=console, writing=True):
    """Print the recognition in plain words. Return: may writing go on?
    (plan 110 §8, points 3 to 5)

    writing=False (--nur-abzug/--dry-run): an unknown firmware is then no
    reason to stop, but a note -- reading changes nothing anyway
    (issue #1: the message sounded like a stop and then went on).

    Takes an `Identification` of `identify()` (it renders its `text`) as well as the old dict of
    `identify_device()`. Only a verified profile is a yes to writing; `--ohne-erkennung` stays the
    installer's escape hatch for everything else.
    """
    if "text" not in found:
        return _report_legacy(found, log, writing)
    for level, text in found["_lines"]:
        getattr(log, level, log.info)(text)
    if found["status"] == "verified":
        return True
    if found["kind"] == "ours":
        # Our own layout: no Android left, nothing stock-specific to lose -- the restore path
        # has to stay open, exactly as before (I:1620).
        log.info("Our layout is on the device -- restoring the vendor firmware stays possible.")
        return True
    # A known board without a verified run (profile-only, partial) is not an unknown
    # board: its row is already in the table, what is missing is an owner's green
    # report -- and no image exists for it until then (doku/121 section 5).
    known = found.get("profile")
    if not writing:
        if known:
            log.warn("Only reading -- nothing is written. This board is known (profile '%s') but no"
                     % known)
            log.info("owner has reported a green run of our build on it, so no image exists for it yet.")
        else:
            log.warn("Only reading -- nothing is written, so an unknown board is a note, not a stop.")
            log.info("Please post the row above, then the board goes into the table")
            log.info("(github.com/well0nez/allwinner-h713-linux).")
        return True
    log.error("No verified profile for this board -- nothing is written.")
    if known:
        log.info("This board is known (profile '%s'), but nobody has reported a green run of our" % known)
        log.info("build on it, and no image is built for a board nobody has tested (doku/121 section 5).")
    else:
        log.info("Guessing the places of a foreign version costs the secure storage in the")
        log.info("worst case, so this stops here. Post the row above and it goes into the table.")
    return False


def _report_legacy(found, log, writing):
    if found["layout"] and not found["layout"].startswith("stock layout"):
        log.ok("%s -- no Android any more, only the dump makes sense" % found["layout"])
        return True
    if not found["layout"]:
        log.warn("The drive looks like nothing known.")
        return True
    if not found["fingerprint"]:
        log.warn("The firmware could not be determined.")
        return True
    version, date = interpret_fingerprint(found["fingerprint"])
    log.info("  fingerprint   %s" % found["fingerprint"])
    if found["known"]:
        log.ok("%s recognised -- Android %s, build %s" % (found["device"], version, date))
        return True
    if not writing:
        log.warn("Unknown firmware: Android %s, build %s -- only reading, "
                 "nothing is written." % (version, date))
        log.info("  Please report the fingerprint line above, then the device goes")
        log.info("  into the table (github.com/well0nez/allwinner-h713-linux).")
        return True
    log.error("Unknown firmware: Android %s, build %s -- no writing." % (version, date))
    log.info("  Guessing the places of a foreign version costs the Secure Storage")
    log.info("  in the worst case -- so no going on.")
    log.info("  Please report the fingerprint line above, then it goes into the table.")
    return False
