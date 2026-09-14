# SPDX-License-Identifier: GPL-2.0
"""Board facts of a firmware image and of a device -- read only, nothing is ever written.

`image_facts()` is package A1's `umbau/work/A1/image_facts.py` moved into the package: same
sections, same key names, same values, but on `h713.imagewty` / `h713.fex` / `h713.fs` instead of
loading the old extractor by path (no `--library`). Its JSON (sorted keys, indent 2) is frozen in
`umbau/fixtures/images/*.json`; `tests/test_facts.py` compares byte for byte.

`device_facts()` answers the same sections off a device or a raw dump, as far as one carries them:
GPT (layout), boot0 at LBA 16 (DRAM), the boot package at LBA 24576 (items, versions), the vendor
build.prop through super/LP/ext4, the MIPS files of the bootloader FAT, panel_config.ini of Reserve0.

Only numbers, strings and sha256 digests leave this module -- never vendor bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from typing import Optional

from h713.fex import DRAM_FIELDS, parse_ini
from h713.fs import Ext4, Fat, LpSuper
from h713.imagewty import (Imagewty, SunxiPackage, fdt_root, find_sunxi_packages,
                           uboot_version_string)
from h713.log import Log
from h713.source import FileSource, Source, SparseSource
from h713.util import SECTOR, sha256_bytes

FIRST_PARTITION_LBA = 73728          # first partition of the stock layout, as measured on the device
GPT_HEADER_OFFSET = SECTOR           # the GPT header is in the second sector, in a .fex as on a disk
GPT_HEAD_SECTORS = 34                # protective MBR, header and the whole entry table
BOOT0_LBA = (16, 256)                # eGON.BT0: the BootROM reads LBA 16 and falls back to 256
BOOT_PACKAGE_LBA = (24576, 32800)    # the two sunxi-package copies on the device
MISC_SLOT_OFFSET = 2048              # Android bootloader_control in misc: slot_suffix, then the magic
MISC_SLOT_MAGIC = 0x42414342

IMAGEWTY_FILES = {
    "sys_partition": "sys_partition.fex", "sunxi_gpt": "sunxi_gpt.fex", "boot0": "boot0_sdcard.fex",
    "sys_config": "sys_config.fex", "boot_package": "boot_package.fex",
    "sunxi_version": "sunxi_version.fex", "super": "super.fex",
    "boot_resource": "boot-resource.fex", "reserve0": "Reserve0.fex",
}
PANEL_FIELDS = ("ProjectID", "PanelWidth", "PanelHeight", "PanelDualPort", "PanelHTotal", "PanelVTotal",
                "PanelDCLK", "PanelHsync", "PanelVsync", "PanelHBP", "PanelVBP", "PanelHsyncPol",
                "PanelVsyncPol", "pwm_channel", "pwm_freq", "default_backlight")
PANEL_CONFIG_NAME = "panel_config.ini"          # the file env.fex names (panel_config=panel_config.ini)
VENDOR_PANEL_CONFIG = "/etc/tvconfig/panel_config/panel_config.ini"
VENDOR_MIPS_DIR = "/etc/display/mips"
FAT_MIPS_DIR = "mips"
MIPS_SOURCES = ("boot_resource_fat:mips/", "vendor:/etc/display/mips/")
FIRMWARE_HINTS = ("/bin/loadmips", "/lib/libmips.so", "/bin/hw/tvserver",
                  "/etc/firmware/hdcp_1.bin", "/etc/firmware/hdcp_v22.bin")
BUILD_PROP_KEYS = ("ro.vendor.build.date", "ro.vendor.build.fingerprint", "ro.product.vendor.brand",
                   "ro.product.vendor.model", "ro.product.vendor.name")
VENDOR_PARTITIONS = ("vendor_a", "vendor")
BOOTLOADER_PARTITIONS = ("bootloader_a", "bootloader_b")
RESERVE0_PARTITIONS = ("Reserve0_a", "Reserve0", "Reserve0_b")
READ_CHUNK = 8 << 20


# ---------------------------------------------------------------------------- sources and helpers

class DiskSource(Source):
    """A block device behind the Source interface the readers use. Read only; backing() and
    sub() are what Source already does, so only the sector arithmetic is left here."""

    def __init__(self, disk):
        self._d, self.size, self.name = disk, disk.sectors * SECTOR, disk.path

    def read(self, off, n):
        if off < 0 or n < 0:
            raise ValueError("negative read")
        first, front = off // SECTOR, off % SECTOR
        return self._d.read(first, (front + n + SECTOR - 1) // SECTOR)[front:front + n]


def as_source(thing) -> Source:
    """A Source for whatever was handed in: a path, a `Disk`, or a Source already."""
    if isinstance(thing, Source):
        return thing
    if hasattr(thing, "sectors") and hasattr(thing, "read"):
        return DiskSource(thing)
    return FileSource(thing)


def close_source(q) -> None:
    """Give back the file handle a FileSource holds (it has no close() of its own)."""
    handle = getattr(q, "fh", None)
    if handle is not None:
        handle.close()


def read_safe(reader, *args):
    """Read one file out of a container; None when it cannot deliver it. The readers raise Abort
    for a truncated FAT or a broken ext4 inode -- one unreadable file must not cost us the rest
    of the facts, so it becomes a null hash in the output."""
    try:
        return reader(*args)
    except Exception:                                                            # noqa: BLE001
        return None


def source_text(source):
    """Whole content of a source as text (the .fex files are latin1, mostly with CRLF)."""
    return source.read(0, source.size).decode("latin1")


def source_sha256(source):
    digest = hashlib.sha256()
    off = 0
    while off < source.size:
        chunk = source.read(off, min(READ_CHUNK, source.size - off))
        if not chunk:
            break
        digest.update(chunk)
        off += len(chunk)
    return digest.hexdigest()


def to_number(text):
    """'792' -> 792, '0x1c70' -> 7280; anything else stays the trimmed string."""
    value = text.split(";")[0].split("#")[0].strip()
    try:
        return int(value, 16) if value[:2].lower() == "0x" else int(value, 10)
    except ValueError:
        return text.strip()


def guid_text(raw):
    """Mixed-endian GUID, spelled the way the EFI tools do."""
    first, second, third = struct.unpack_from("<IHH", raw, 0)
    return "%08X-%04X-%04X-%s-%s" % (first, second, third, raw[8:10].hex().upper(), raw[10:16].hex().upper())


def image_file(img, key) -> Optional[Source]:
    """A source for one entry of the IMAGEWTY file table, or None when the image has none."""
    return img.file(IMAGEWTY_FILES[key])


def sys_partition_facts(img):
    """The [partition] blocks of sys_partition.fex, with running start LBA. The file has CRLF
    line ends: without the .strip() the value pattern drags the carriage return into every
    unquoted value, and the partition names then carry an invisible U+000D. Start LBAs are
    cumulative from 73728, the first partition of the stock layout."""
    source = image_file(img, "sys_partition")
    if source is None:
        return []
    partitions = []
    lba = FIRST_PARTITION_LBA
    for block in re.findall(r"\[partition\](.*?)(?=\[partition\]|\[partition_end\]|\Z)",
                            source_text(source), re.S):
        fields = {key: value.strip()
                  for key, value in re.findall(r"^\s*(\w+)\s*=\s*\"?([^\"\r\n]+)\"?\s*$", block, re.M)}
        if "name" not in fields:
            continue
        sectors = int(fields.get("size", "0"))
        partitions.append({"downloadfile": fields.get("downloadfile"), "name": fields["name"],
                           "sectors": sectors, "start_lba": lba})
        lba += sectors
    return partitions


def gpt_facts(raw):
    """The GPT in `raw` -- a whole sunxi_gpt.fex, or the first 34 sectors of a disk."""
    header = raw[GPT_HEADER_OFFSET:GPT_HEADER_OFFSET + 92]
    if header[:8] != b"EFI PART":
        return {"entries": [], "error": "no 'EFI PART' signature at offset %d" % GPT_HEADER_OFFSET,
                "header": None}
    first_usable, last_usable = struct.unpack_from("<QQ", header, 40)
    entries_lba, count, entry_size = struct.unpack_from("<QII", header, 72)
    entries = []
    base = entries_lba * SECTOR
    for index in range(count):
        entry = raw[base + index * entry_size:base + (index + 1) * entry_size]
        if len(entry) < entry_size or entry[:16] == b"\0" * 16:
            break
        first, last = struct.unpack_from("<QQ", entry, 32)
        entries.append({"attributes_hex": "0x%016x" % struct.unpack_from("<Q", entry, 48)[0],
                        "first": first, "last": last,
                        "name": entry[56:128].decode("utf-16le").rstrip("\0")})
    return {"entries": entries,
            "header": {"disk_guid": guid_text(header[56:72]), "entries": count,
                       "entry_size": entry_size, "first_usable": first_usable,
                       "last_usable": last_usable}}


def layout_consistency(partitions, gpt):
    """Partitions whose size differs between sys_partition.fex and sunxi_gpt.fex. A size of 0
    means 'all the rest of the device' (UDISK); the GPT spells that rest out, so the two never
    match there and it is not a disagreement. A difference shifts every following partition, so
    the start LBAs are carried along in each entry."""
    if not gpt or not gpt.get("entries"):
        return []
    by_name = {}
    for entry in gpt["entries"]:
        by_name.setdefault(entry["name"], entry)
    out = []
    for part in partitions:
        if part["sectors"] == 0:
            continue
        entry = by_name.get(part["name"])
        gpt_sectors = None if entry is None else entry["last"] - entry["first"] + 1
        if gpt_sectors == part["sectors"]:
            continue
        out.append({"name": part["name"], "sunxi_gpt_sectors": gpt_sectors,
                    "sunxi_gpt_start_lba": None if entry is None else entry["first"],
                    "sys_partition_sectors": part["sectors"], "sys_partition_start_lba": part["start_lba"]})
    return out


def partition_source(q, parts, name):
    """One partition of a disk as a source, or None when the dump does not reach that far."""
    first, sectors = parts.get(name, (0, 0))
    if not sectors or (first + sectors) * SECTOR > q.size:
        return None
    return read_safe(q.sub, first * SECTOR, sectors * SECTOR, "Partition %s (LBA %d)" % (name, first))


def boot0_facts(head, size):
    """The eGON.BT0 magic and the 24 u32 DRAM parameter block at 0x38."""
    dram = dict(zip(DRAM_FIELDS, struct.unpack_from("<24I", head, 0x38)))
    return {"dram": dram, "dram_clk_mhz": dram["clk"], "magic": head[4:12].decode("latin1"),
            "size": size}


def is_vendor_boot0(head):
    """Is this sector the vendor boot0 -- and not our own SPL, which has the same magic? Our SPL
    sits at LBA 16 on a converted device, so the magic alone lets it through: the first probe run
    on an HY310 printed the SPL's device-tree name as DRAM settings. Mainline marks its header
    with "SPL" at 0x14, where boot0 keeps its header size, and a real DRAM block has a sane clock
    and type -- check both (uboot-h713 patch 0038)."""
    clk, kind = struct.unpack_from("<II", head, 0x38)
    return (len(head) >= 0x100 and head[4:12] == b"eGON.BT0" and head[0x14:0x17] != b"SPL"
            and 300 <= clk <= 1200 and kind in (2, 3, 7))                 # DDR2, DDR3, LPDDR3


def sys_config_facts(source):
    if source is None:
        return None
    sections = parse_ini(source_text(source))
    return {"dram_para": dict(sections.get("dram_para", [])), "sections": list(sections),
            "size": source.size}


def arisc_version(blob):
    """Version string of the ARISC blob; its strings are stored word-mirrored (see check_scp)."""
    mirrored = b"".join(blob[i:i + 4][::-1] for i in range(0, len(blob) - 3, 4))
    found = re.search(rb"[ -~]{0,40}ARISC[ -~]{0,60}", mirrored)
    return found.group(0).decode("latin1").strip() if found else None


def boot_package_facts(source, log, origin, search=True):
    """Items of the sunxi-package; item offsets are relative to the package."""
    if source is None:
        return None
    offset = 0
    if source.read(0, len(SunxiPackage.NAME)) != SunxiPackage.NAME:
        found = find_sunxi_packages(source, log, max_bytes=min(source.size, 64 << 20)) if search else []
        if not found:
            return {"error": "no sunxi-package in %s" % origin, "items": [], "size": source.size}
        offset = found[0]
    package = SunxiPackage(source, offset, log, origin)
    items = []
    for name, (item_offset, length) in package.items.items():
        items.append({"name": name, "offset": item_offset, "size": length,
                      "sha256": sha256_bytes(source.read(offset + item_offset, length))})
    items.sort(key=lambda item: item["offset"])
    uboot, scp, dtb = package.item("u-boot"), package.item("scp"), package.item("dtb")
    root = fdt_root(dtb) if dtb else {}
    return {"arisc_version": arisc_version(scp) if scp else None,
            "checksum_ok": package.checksum_ok, "dtb_compatible": root.get("compatible"),
            "dtb_model": root.get("model"), "items": items, "package_offset": offset,
            "size": source.size, "uboot_version": uboot_version_string(uboot) if uboot else None}


def super_facts(source, log, origin=IMAGEWTY_FILES["super"]):
    """(super section, vendor file system); the file system is None when there is no vendor."""
    if source is None:
        return {"error": "%s missing" % origin, "partitions": None}, None
    if SparseSource.is_sparse(source):
        source = SparseSource(source, log)
    try:
        lp = LpSuper(source, log)
    except Exception as problem:                                                 # noqa: BLE001
        return {"error": str(problem), "partitions": None}, None
    partitions = [{"name": name, "size": part["size"]} for name, part in lp.parts.items()]
    partitions.sort(key=lambda part: part["name"])
    vendor = None
    for name in VENDOR_PARTITIONS:
        part = lp.partition(name, log)
        if part is not None:
            vendor = read_safe(Ext4, part, None, name, log)
            break
    return {"partitions": partitions, "vendor_partition": None if vendor is None else vendor.label}, vendor


def vendor_read(vendor, path):
    """Content of one file of the vendor file system, or None when it is not there."""
    if vendor is None:
        return None
    entry = read_safe(vendor.exists, path)
    if entry is None or entry["typ"] == "d":
        return None
    return read_safe(vendor.read, path)


def vendor_build_prop_facts(vendor):
    data = vendor_read(vendor, "/build.prop")
    props = dict((key, None) for key in BUILD_PROP_KEYS)
    if data is None:
        return props
    for line in data.decode("utf-8", "replace").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in props:
            props[key] = value.strip()
    return props


def firmware_hints_facts(vendor):
    hints = {}
    for path in FIRMWARE_HINTS:
        data = vendor_read(vendor, path)
        hints["vendor:" + path] = {"present": data is not None,
                                   "sha256": None if data is None else sha256_bytes(data),
                                   "size": None if data is None else len(data)}
    return hints


def vendor_mips_files(vendor):
    """name -> {size, sha256} of vendor:/etc/display/mips/, or None when there is none."""
    entry = None if vendor is None else read_safe(vendor.exists, VENDOR_MIPS_DIR)
    if entry is None or entry["typ"] != "d":
        return None
    out = {}
    for item in sorted(vendor.ls(VENDOR_MIPS_DIR), key=lambda x: x["name"]):
        if item["typ"] == "d":
            continue
        data = vendor_read(vendor, VENDOR_MIPS_DIR + "/" + item["name"])
        out[item["name"]] = {"sha256": None if data is None else sha256_bytes(data), "size": item["size"]}
    return out


def open_fat(source, log, origin):
    return None if source is None or not Fat.is_fat(source) else read_safe(Fat, source, log, origin)


def fat_listing(entries):
    listing = [{"is_dir": bool(entry["verzeichnis"]), "name": entry["name"], "size": entry["groesse"]}
               for entry in entries]
    listing.sort(key=lambda item: item["name"])
    return listing


def boot_resource_facts(fat):
    if fat is None:
        return None
    mips = fat.directory(FAT_MIPS_DIR)
    return {"has_mips_dir": mips is not None, "mips": None if mips is None else fat_listing(mips),
            "root": fat_listing(fat.entries(0))}


def reserve0_facts(fat):
    return None if fat is None else {"root": fat_listing(fat.entries(0))}


def fat_mips_files(fat):
    """name -> {size, sha256} of the mips/ directory of one FAT volume, or None."""
    mips = None if fat is None else read_safe(fat.directory, FAT_MIPS_DIR)
    if mips is None:
        return None
    out = {}
    for entry in sorted(mips, key=lambda item: item["name"]):
        if entry["verzeichnis"]:
            continue
        data = read_safe(fat.read, entry)
        out[entry["name"]] = {"sha256": None if data is None else sha256_bytes(data),
                              "size": entry["groesse"]}
    return out


def panel_fields(data):
    """The requested fields of a panel_config.ini; all of them None when there is no file."""
    fields = dict((field, None) for field in PANEL_FIELDS)
    if data is None:
        return fields
    flat = {}
    for pairs in parse_ini(data.decode("latin1")).values():
        for key, value in pairs:
            flat.setdefault(key.strip().lower(), value)
    for field in PANEL_FIELDS:
        if flat.get(field.lower()) is not None:
            fields[field] = to_number(flat[field.lower()])
    return fields


def fat_read(fat, name):
    """Content of one file in the root directory of a FAT volume, or None."""
    for entry in [] if fat is None else fat.entries(0):
        if not entry["verzeichnis"] and entry["name"].lower() == name.lower():
            return read_safe(fat.read, entry)
    return None


def panel_config_facts(reserve0_fat, vendor):
    reserve0 = fat_read(reserve0_fat, PANEL_CONFIG_NAME)
    vendor_ini = vendor_read(vendor, VENDOR_PANEL_CONFIG)
    from_reserve0, from_vendor = panel_fields(reserve0), panel_fields(vendor_ini)
    facts = dict((field, {"reserve0": from_reserve0[field], "vendor": from_vendor[field]})
                 for field in PANEL_FIELDS)
    facts["sources"] = {"reserve0": None if reserve0 is None else "Reserve0.fex:" + PANEL_CONFIG_NAME,
                        "vendor": None if vendor_ini is None else "vendor:" + VENDOR_PANEL_CONFIG}
    return facts


def mips_files_facts(named_sources):
    """The display firmware files of every source that carries them, most trusted first:
    [(source name, files|None), ...]. The first source with a display.bin decides `display_bin`
    -- for an image the FAT copy U-Boot reads, for a device the slot the profile names first."""
    sources, display = {}, None
    for name, files in named_sources:
        if files is None:
            continue
        sources[name] = [{"name": n, "sha256": f["sha256"], "size": f["size"]}
                         for n, f in sorted(files.items())]
        if display is None and "display.bin" in files:
            display = dict(files["display.bin"], source=name)
    return {"display_bin": display, "sources": sources}


# ---------------------------------------------------------------------------- the two drivers

def image_facts(source_or_path, log=None):
    """Every board fact of one image, as one dictionary. A path is opened and closed again."""
    q = as_source(source_or_path)
    log = log or Log(quiet=True)
    try:
        img = Imagewty(q, log)
        partitions = sys_partition_facts(img)
        gpt_source = image_file(img, "sunxi_gpt")
        gpt = None if gpt_source is None else gpt_facts(gpt_source.read(0, gpt_source.size))
        boot0_source, version_source = image_file(img, "boot0"), image_file(img, "sunxi_version")
        config = image_file(img, "sys_config")
        section, vendor = super_facts(image_file(img, "super"), log)
        boot_resource = open_fat(image_file(img, "boot_resource"), log, IMAGEWTY_FILES["boot_resource"])
        reserve0 = open_fat(image_file(img, "reserve0"), log, IMAGEWTY_FILES["reserve0"])
        return {
            "boot0": None if boot0_source is None else boot0_facts(boot0_source.read(0, 0x100),
                                                                   boot0_source.size),
            "boot_package": boot_package_facts(image_file(img, "boot_package"), log,
                                               IMAGEWTY_FILES["boot_package"]),
            "boot_resource_fat": boot_resource_facts(boot_resource),
            "firmware_hints": firmware_hints_facts(vendor),
            "imagewty": {"files": [{"maintype": e["maintype"].strip("\0"), "name": e["name"],
                                    "original": e["original"], "stored": e["stored"],
                                    "subtype": e["subtype"].strip("\0")} for e in img.entries.values()],
                         "firmware_id": img.firmware_id, "hardware_id": img.hardware_id,
                         "header_version": img.header_version, "image_header_size": img.image_header_size,
                         "image_size": img.image_size, "layout": img.layout, "num_files": img.num_files,
                         "pid": img.pid, "vid": img.vid},
            "input": {"name": os.path.basename(q.name), "sha256": source_sha256(q), "size": q.size},
            "layout_consistency": layout_consistency(partitions, gpt),
            "mips_files": mips_files_facts(((MIPS_SOURCES[0], fat_mips_files(boot_resource)),
                                            (MIPS_SOURCES[1], vendor_mips_files(vendor)))),
            "panel_config": panel_config_facts(reserve0, vendor),
            "reserve0_fat": reserve0_facts(reserve0),
            "super": section,
            "sunxi_gpt": gpt,
            "sunxi_version": None if version_source is None else source_text(version_source).strip(),
            "sys_config": sys_config_facts(config),
            "sys_partition": partitions,
            "vendor_build_prop": vendor_build_prop_facts(vendor),
        }
    finally:
        if q is not source_or_path:
            close_source(q)


def active_slot(q, parts):
    """'_a'/'_b' out of the Android bootloader_control in misc, or None when it says nothing."""
    if "misc" not in parts:
        return None
    raw = read_safe(q.read, parts["misc"][0] * SECTOR + MISC_SLOT_OFFSET, 8)
    if not raw or len(raw) < 8 or struct.unpack_from("<I", raw, 4)[0] != MISC_SLOT_MAGIC:
        return None
    suffix = raw[:4].split(b"\0")[0].decode("latin1")
    return suffix if suffix in ("_a", "_b") else None


def device_facts(source, log=None):
    """The sections of image_facts() that a device or a raw dump can answer. Reads about 1.2 MiB
    plus the MIPS files and never writes: GPT, boot0 (LBA 16), boot package (LBA 24576), super ->
    LP -> vendor -> build.prop, the bootloader FAT, Reserve0. Keys the other side cannot answer
    stay None, so both facts dictionaries read the same way."""
    q = as_source(source)
    log = log or Log(quiet=True)
    try:
        return _device_facts(q, log)
    finally:
        if q is not source:
            close_source(q)


def _device_facts(q, log):
    gpt = gpt_facts(q.read(0, GPT_HEAD_SECTORS * SECTOR))
    if gpt.get("header") is None:
        gpt = None
    parts = {}
    for entry in (gpt or {}).get("entries", []):
        parts.setdefault(entry["name"], (entry["first"], entry["last"] - entry["first"] + 1))

    boot0 = None
    for lba in BOOT0_LBA:
        head = read_safe(q.read, lba * SECTOR, 0x100)
        if head and len(head) >= 0x100 and is_vendor_boot0(head):
            boot0 = boot0_facts(head, 0x100)
            boot0["lba"] = lba
            break

    package = None
    for lba in BOOT_PACKAGE_LBA:
        origin = "boot_package (LBA %d)" % lba
        # No search here: the package lies exactly at this LBA or nowhere. Scanning a whole
        # device for the string would read gigabytes for nothing.
        window = None if q.size <= lba * SECTOR else \
            read_safe(q.sub, lba * SECTOR, min(q.size - lba * SECTOR, 16 << 20), origin)
        if window is not None and window.read(0, len(SunxiPackage.NAME)) == SunxiPackage.NAME:
            package = read_safe(boot_package_facts, window, log, origin, False)
        if package is not None:
            package["lba"] = lba
            break

    section, vendor = super_facts(partition_source(q, parts, "super"), log, "partition 'super'")
    slots = dict((name, fat_mips_files(open_fat(partition_source(q, parts, name), log, name)))
                 for name in BOOTLOADER_PARTITIONS)
    reserve0 = None
    for name in RESERVE0_PARTITIONS:
        reserve0 = reserve0 or open_fat(partition_source(q, parts, name), log, name)
    slot, in_vendor = active_slot(q, parts), vendor_mips_files(vendor)
    # The order the profiles name: the slot U-Boot reads first, then the other, then Android's copy.
    order = ("bootloader_a", "bootloader_b") if slot == "_a" else ("bootloader_b", "bootloader_a")
    named = [(name + ":mips/", slots[name]) for name in order] + [(MIPS_SOURCES[1], in_vendor)]
    facts = dict.fromkeys(("boot_resource_fat", "imagewty", "sunxi_gpt", "sunxi_version", "sys_config"))
    facts.update({
        "boot0": boot0, "boot_package": package, "firmware_hints": firmware_hints_facts(vendor),
        "gpt": gpt, "input": {"name": os.path.basename(q.name or ""), "sha256": None, "size": q.size},
        "layout_consistency": [], "mips_files": mips_files_facts(named),
        "mips": {"bootloader_a": slots["bootloader_a"], "bootloader_b": slots["bootloader_b"],
                 "vendor": in_vendor, "active_slot": slot},
        "panel_config": panel_config_facts(reserve0, vendor), "reserve0_fat": reserve0_facts(reserve0),
        "super": section, "sys_partition": [], "vendor_build_prop": vendor_build_prop_facts(vendor),
    })
    return facts


def dumps(facts):
    """The one canonical text form: sorted keys, no timestamps, trailing newline."""
    return json.dumps(facts, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
