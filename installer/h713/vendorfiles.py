# SPDX-License-Identifier: GPL-2.0
"""The vendor files the extractor pulls out, and the checks that say whether they are sound.

Where they live in the vendor partition (X:208-262), how a symbol is found in an ELF, how the MSPM
block chain, an EDID block, the PQ files, a TSE header and display_cfg.xml are checked
(X:1674-1998). Stage 1 of doku/121: identifiers and comments are English, every user-visible string
and every dict key is unchanged.
"""

from __future__ import annotations

import re
import sqlite3
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

from h713.fex import ini_numbers, parse_ini
from h713.log import Abort
from h713.profiles import FIRMWARE_REVISIONS
from h713.util import hexdump_short, sha256_bytes

REQUIRED_FILES = ("lib/firmware/h713-arisc.bin", "lib/firmware/hy310-edid.bin", "lib/firmware/h713/msp-patch.bin")

# Exactly the files userspace/h713-pq reads (h713_pq/sources.py)
PQ_FILES = (
    "tvpq.db",
    "pq_picturemode.ini",
    "pq_factory_extern.ini",
    "pq_colortemp.ini",
    "pq_overscan_config.ini",
    "pqcontrol_config_setting.xml",
    "pqcontrol_custom_setting.xml",
    "portmap.cfg",
)
TVCONFIG = "/etc/tvconfig"          # relative to the root of the vendor partition (= /vendor in Android)
EDID_14 = TVCONFIG + "/HDMI_EDID_14.bin"
EDID_20 = TVCONFIG + "/HDMI_EDID_20.bin"
MSP_LIB_CANDIDATES = ("/lib/libmspsound.so", "/lib64/libmspsound.so", "/lib/hw/libmspsound.so")

# WLAN firmware of the AIC8800D80 (SDIO), relative to the root of the vendor partition.
# The target directory MUST match the driver's CONFIG_AIC_FW_PATH; radxa's
# patch fix-sdio-firmware-path.patch sets it to /lib/firmware/aic8800_fw/SDIO/aic8800D80
# (formerly aic8800_sdio/aic8800). If the two differ, the driver loads no
# firmware and wlan0 never appears -- the log then only says "file failed to open".
# Checked on the device (12.09.2026): with exactly this set mmc1, wlan0 and phy0
# come up; the driver loads fw_patch_table/fw_adid/fw_patch/fmacfw. So nothing
# proprietary has to be shipped -- the user gets the firmware of their own
# device, as with HDCP, ARISC and the MIPS firmware.
AIC_FW_DIR = "/etc/firmware/aic8800d80"
AIC_FW_TARGET = "lib/firmware/aic8800_fw/SDIO/aic8800D80"

# --------------------------------------------------------------------------------------------------
# MIPS/display artefacts (tool 0.3, plan 108 §1/§2/§4.2/§4.5)
# --------------------------------------------------------------------------------------------------

# U-Boot reads them with h713_disp_read("mips/<name>", …) out of a filesystem (mainline/external/u-boot/
# arch/arm/mach-sunxi/h713_mips.c). The names below are the *long names* in the FAT16 -- the 8.3 short
# names are useless (the ProjectID files are called e.g. "PR§÷pð~1.TSE" there).
MIPS_SOURCE_DIR = "mips"                # subdirectory in bootloader_a/bootloader_b
MIPS_OUTPUT_DIR = "boot/mips"           # output under --out; exactly the names U-Boot expects
MIPS_FILES = ("display.bin", "display_cfg.xml", "LogoRegData.bin", "database.TSE", "pq_custom.TSE", "projecttable.TSE")
MIPS_PROJECTID = re.compile(r"^ProjectID_0x([0-9A-Fa-f]{4})\.TSE$")
# Taken from the ROOT of the same FAT, not from mips/ -- output boot/<name>. `h713_disp init <id> logo`
# reads bootlogo.bmp there (fork 80eae99, device-proven 15.09.2026, doku/40 last section), so an
# installed device needs /boot/bootlogo.bmp; plan 108 §1 left it out when nothing of ours read it.
BOOT_ROOT_FILES = ("bootlogo.bmp",)
BOOT_ROOT_OUTPUT_DIR = "boot"
# Lies in the same partition, our chain does not use it (plan 108 §1) -- only named in the report,
# not copied. Why each stays out (decision 15.09.2026): fastbootlogo.bmp is the fastboot-mode logo
# and our U-Boot has no such mode; font24/32.sft are the vendor bootloader's text fonts; magic.bin
# is 512 B of ASCII of unknown purpose; bat/ and wavefile/ are a tablet template's battery icons
# and e-paper waveforms. None is read by our chain, none stands for a stock behaviour we lack.
MIPS_NOT_OURS = ("fastbootlogo.bmp", "font24.sft", "font32.sft", "magic.bin", "bat", "wavefile")
# Partition names (GPT) resp. --part keys behind which this FAT16 sits. bootloader_b first: that is the
# partition U-Boot reads from today (mmc 1:2, plan 108 §1).
MIPS_PART_NAMES = ("bootloader_b", "bootloader_a")
MIPS_PART_KEYS = ("bootloader_b", "bootloader_a", "bootloader", "boot-resource", "boot_resource", "mips")
MIPS_FEX = "boot-resource.fex"          # that is what the image is called in the IMAGEWTY container and in --fex-dir

# Stage 2 C-D, second MIPS source: the same set lies a second time inside super, in the vendor
# partition (A0 section 4 -- where the vendor U-Boot falls back to, and the only place the two ADT-3
# images have it: their bootloader FAT carries no mips/ at all). VENDOR_MIPS_SOURCE is the name the
# profiles use in mips.sources, FALLBACK_MIPS_SOURCES the order of api-stufe2.md without a profile.
VENDOR_MIPS_DIR = "/etc/display/mips"   # relative to the root of the vendor partition
VENDOR_MIPS_SOURCE = "vendor:" + VENDOR_MIPS_DIR
FALLBACK_MIPS_SOURCES = ("bootloader_b", "bootloader_a", VENDOR_MIPS_SOURCE)

TSE_MAGIC = b"TSE"
TSE_ID_OFFSET = 14                      # u16 little-endian in the 16-byte header (plan 108 §4.5 „erstens")

# panel_config.ini in the vendor filesystem: the project id the board *declares*. It is reported, but never
# used (plan 108 §4.5 „drittens" / §3).
PANEL_CONFIG_CANDIDATES = ("/etc/tvconfig/panel_config/panel_config.ini", "/etc/tvconfig/panel_config.ini")


def elf_symbol(data: bytes, symbol: str) -> Optional[Tuple[int, int, str]]:
    """(file offset, size, section) of a symbol out of .dynsym/.symtab; mapped through the section (sh_addr -> sh_offset)."""
    if data[:4] != b"\x7fELF":
        raise Abort("not an ELF file")
    cls, endian = data[4], data[5]
    E = "<" if endian == 1 else ">"
    if cls == 1:
        e_shoff, = struct.unpack_from(E + "I", data, 0x20)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(E + "HHH", data, 0x2E)
        sh_fmt, sh_len = E + "IIIIIIIIII", 40
        sym_fmt, sym_len = E + "IIIBBH", 16
    else:
        e_shoff, = struct.unpack_from(E + "Q", data, 0x28)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(E + "HHH", data, 0x3A)
        sh_fmt, sh_len = E + "IIQQQQIIQQ", 64
        sym_fmt, sym_len = E + "IBBHQQ", 24
    sects = []
    for i in range(e_shnum):
        s = struct.unpack_from(sh_fmt, data, e_shoff + i * e_shentsize)
        if cls == 1:
            name, sh_type, flags, addr, off, size, link, info, align, entsize = s
        else:
            name, sh_type, flags, addr, off, size, link, info, align, entsize = s
        sects.append({"name": name, "type": sh_type, "addr": addr, "off": off, "size": size, "link": link, "entsize": entsize})
    shstr = sects[e_shstrndx] if e_shstrndx < len(sects) else None

    def sname(i):
        if shstr is None:
            return "?"
        o = shstr["off"] + i
        return data[o:data.find(b"\0", o)].decode("latin1", "replace")

    for s in sects:
        s["sname"] = sname(s["name"])
    for s in sects:
        if s["type"] not in (2, 11):  # SYMTAB, DYNSYM
            continue
        strtab = sects[s["link"]]
        n = s["size"] // sym_len
        for i in range(n):
            o = s["off"] + i * sym_len
            if cls == 1:
                st_name, st_value, st_size, st_info, st_other, st_shndx = struct.unpack_from(sym_fmt, data, o)
            else:
                st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(sym_fmt, data, o)
            no = strtab["off"] + st_name
            nm = data[no:data.find(b"\0", no)]
            if nm == symbol.encode():
                if st_shndx == 0 or st_shndx >= len(sects):
                    return None
                sec = sects[st_shndx]
                if sec["type"] == 8:  # NOBITS
                    return None
                return (sec["off"] + (st_value - sec["addr"]), st_size, sec["sname"])
    return None


def parse_mspm(blob: bytes) -> Tuple[List[dict], List[str]]:
    """MSPM block chain: 'MSPM' | u16 0 | u16 0x01TT | u32 BE (length<<8). Returns blocks and findings."""
    blocks, problems = [], []
    o = 0
    while o < len(blob):
        h = blob[o:o + 12]
        if len(h) < 12 or h[:4] != b"MSPM":
            problems.append(f"at +{o:#x}: no MSPM header ({h[:4]!r})")
            break
        zero, target, raw = struct.unpack(">HHI", h[4:12])
        length = raw >> 8
        if zero != 0 or (target >> 8) != 1 or (raw & 0xFF) != 0:
            problems.append(f"block {len(blocks)} at +{o:#x}: header fields {zero:#x} {target:#x} {raw:#x} unexpected")
        if length % 4 or o + 12 + length > len(blob):
            problems.append(f"block {len(blocks)} at +{o:#x}: length {length} does not fit")
            break
        dsp = {0x100: "DSP1", 0x102: "DSP2"}.get(target, f"?{target:#x}")
        blocks.append({"offset": o, "target": dsp, "length": length, "pairs": length // 4})
        o += 12 + length
    if o != len(blob):
        problems.append(f"the chain ends at +{o:#x}, the blob has {len(blob)} B")
    if not blocks:
        problems.append("not a single MSPM block")
    return blocks, problems


def find_mspm_chain(data: bytes) -> Optional[Tuple[int, int]]:
    """Fallback without a symbol table: the longest gapless MSPM chain in the file."""
    best = None
    i = data.find(b"MSPM")
    while i >= 0:
        o, n = i, 0
        while data[o:o + 4] == b"MSPM" and o + 12 <= len(data):
            raw = struct.unpack(">I", data[o + 8:o + 12])[0]
            ln = raw >> 8
            if ln % 4 or ln == 0 or o + 12 + ln > len(data):
                break
            o += 12 + ln
            n += 1
        if n >= 2 and (best is None or (o - i) > (best[1] - best[0])):
            best = (i, o)
        i = data.find(b"MSPM", i + 1)
    return best


# --------------------------------------------------------------------------------------------------
# EDID
# --------------------------------------------------------------------------------------------------

def check_edid_block(b: bytes, who: str) -> List[str]:
    findings = []
    if len(b) != 256:
        findings.append(f"{who}: {len(b)} B statt 256")
        return findings
    if b[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        findings.append(f"{who}: EDID header missing ({hexdump_short(b, 8)})")
    for i in (0, 128):
        s = sum(b[i:i + 128]) & 0xFF
        if s:
            findings.append(f"{who}: block {i // 128} checksum {s:#04x} instead of 0")
    if b[126] != 1:
        findings.append(f"{who}: extension counter {b[126]} instead of 1")
    if b[128] != 0x02:
        findings.append(f"{who}: block 1 is not CEA-861 (tag {b[128]:#04x})")
    return findings


def edid_vendor(b: bytes) -> str:
    v = struct.unpack(">H", b[8:10])[0]
    return "".join(chr(64 + ((v >> s) & 0x1F)) for s in (10, 5, 0))


def edid_name(b: bytes) -> str:
    for i in range(54, 126, 18):
        d = b[i:i + 18]
        if d[:3] == b"\0\0\0" and d[3] == 0xFC:
            return d[5:18].decode("latin1", "replace").strip("\n ")
    return ""


# --------------------------------------------------------------------------------------------------
# Check the PQ files
# --------------------------------------------------------------------------------------------------

def check_pq(name: str, data: bytes, tmp: Path) -> List[str]:
    """Empty list = ok. Otherwise findings (each one is trouble ahead)."""
    findings = []
    try:
        if name.endswith(".ini") or name.endswith(".cfg"):
            text = data.decode("utf-8", "replace")
        if name == "pq_picturemode.ini":
            s = parse_ini(text)
            cfg = dict(s.get("CONFIG", []))
            if "picture_mode" not in cfg:
                findings.append("[CONFIG] picture_mode missing")
            modes = [m.strip() for m in cfg.get("picture_mode", "").split(",") if m.strip()]
            for input_name in ("HDMI1", "HDMI2", "HDMI3"):
                if input_name not in s:
                    findings.append(f"section [{input_name}] missing")
                    continue
                d = dict(s[input_name])
                for m in modes:
                    if m not in d:
                        findings.append(f"[{input_name}] mode {m} missing")
                    elif len(ini_numbers(d[m])) != 13:
                        findings.append(f"[{input_name}] {m}: {len(ini_numbers(d[m]))} statt 13 Werte")
        elif name == "pq_factory_extern.ini":
            s = parse_ini(text)
            if "PQ_ENABLE" not in s:
                findings.append("[PQ_ENABLE] missing")
            if "PICTURE_CURVE_HDMI" not in s:
                findings.append("[PICTURE_CURVE_HDMI] missing")
            else:
                d = dict(s["PICTURE_CURVE_HDMI"])
                for i in range(1, 6):
                    k = f"PICTURE_CURVE_SETTINGS[{i}]"
                    if k not in d:
                        findings.append(f"[PICTURE_CURVE_HDMI] {k} missing")
                    elif len(ini_numbers(d[k])) != 5:
                        findings.append(f"[PICTURE_CURVE_HDMI] {k}: {len(ini_numbers(d[k]))} instead of 5 support points")
        elif name == "pq_colortemp.ini":
            s = parse_ini(text)
            if "COLOR_TEMP_HDMI" not in s:
                findings.append("[COLOR_TEMP_HDMI] missing")
            else:
                d = dict(s["COLOR_TEMP_HDMI"])
                for k in ("STANDARD", "COOL", "WARM", "USER"):
                    if k not in d:
                        findings.append(f"[COLOR_TEMP_HDMI] {k} missing")
                    elif len(ini_numbers(d[k])) != 6:
                        findings.append(f"[COLOR_TEMP_HDMI] {k}: {len(ini_numbers(d[k]))} statt 6 Werte")
        elif name == "pq_overscan_config.ini":
            s = parse_ini(text)
            if "HDMIOverscanSetting" not in s:
                findings.append("[HDMIOverscanSetting] missing")
        elif name.endswith(".xml"):
            root = ET.fromstring(data)
            if name == "pqcontrol_config_setting.xml":
                items = [it for it in root.iter("item") if it.get("name") == "gamma"]
                if not items:
                    findings.append("<transform><item name=\"gamma\"> missing")
                elif not all(items[0].get(f"level{i}") for i in range(5)):
                    findings.append("gamma level0..level4 incomplete")
        elif name == "tvpq.db":
            if data[:16] != b"SQLite format 3\0":
                findings.append("no SQLite header")
            else:
                dbp = tmp / "pruef-tvpq.db"
                dbp.write_bytes(data)
                try:
                    c = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
                    tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
                    for t in ("Picture_Mode", "White_Balance_Mode", "Gamma_Point"):
                        if t not in tables:
                            findings.append(f"table {t} missing")
                        else:
                            n = c.execute(f"select count(*) from {t}").fetchone()[0]
                            if n == 0:
                                findings.append(f"table {t} empty")
                    c.close()
                finally:
                    dbp.unlink(missing_ok=True)
        elif name == "portmap.cfg":
            lines = [line.split() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
            if not lines or any(len(line) < 3 for line in lines):
                findings.append("no three-column port rows")
            elif not any(line[2].startswith("HDMI") for line in lines):
                findings.append("no HDMI port")
    except Exception as e:  # noqa: BLE001 - every unreadability is a finding, not a stop
        findings.append(f"not readable: {e}")
    return findings


# --------------------------------------------------------------------------------------------------
# MIPS/display artefacts: TSE header, display.bin against h713_mips_fw_revs[], display_cfg.xml
# --------------------------------------------------------------------------------------------------

def tse_header(data: bytes) -> dict:
    """The 16-byte TSE header: magic 'TSE' and at offset 14 the project id as u16 little-endian (plan 108 §4.5)."""
    if len(data) < 16:
        return {"magic_ok": False, "id": None, "header": data.hex()}
    return {"magic_ok": data[:3] == TSE_MAGIC,
            "id": struct.unpack_from("<H", data, TSE_ID_OFFSET)[0],
            "header": data[:16].hex()}


def check_tse(name: str, data: bytes) -> Tuple[List[str], Optional[int]]:
    """Findings and the id written in the header. For ProjectID_0x*.TSE the file name must match the id field."""
    findings: List[str] = []
    k = tse_header(data)
    if not k["magic_ok"]:
        findings.append(f"{name}: TSE magic missing (header {k['header']})")
        return findings, None
    m = MIPS_PROJECTID.match(name)
    if m:
        from_name = int(m.group(1), 16)
        if k["id"] != from_name:
            findings.append(f"{name}: the header says ID {k['id']:#06x}, the file name says {from_name:#06x} -- they do not match")
        else:
            findings.append(f"{name}: TSE header {k['header']}, ID {k['id']:#06x} = file name")
    else:
        findings.append(f"{name}: TSE header {k['header']}, ID field {k['id']:#06x}")
    return findings, k["id"]


def read_vendor_mips(fs, directory: str = VENDOR_MIPS_DIR, tmp: Optional[Path] = None):
    """The vendor copy of mips/ out of an open vendor filesystem (`fs`: an h713.fs.Ext4Base). Returns
    what the FAT reader in h713.extract returns: the files our chain uses, what else lies in that
    directory, and the problems met on the way."""
    files, leftover, problems = {}, [], []   # type: (dict, List[str], List[str])
    for e in sorted(fs.ls(directory), key=lambda x: x["name"]):
        name = e["name"]
        if e["typ"] == "d":
            leftover.append(f"{directory}/{name}/ (directory)")
        elif name in MIPS_FILES or MIPS_PROJECTID.match(name):
            try:
                files[name] = fs.read(f"{directory}/{name}", tmp)
            except Abort as ex:
                problems.append(f"{name}: {ex}")
        else:
            leftover.append(f"{directory}/{name} ({e['size']} B)")
    return files, leftover, problems


def firmware_revision_of(data: bytes) -> Optional[dict]:
    """The display.bin revision this blob is, by sha256, out of profiles.FIRMWARE_REVISIONS. Wider
    than h713.identify.firmware_revision_of(), which asks UBOOT_FW_REVS -- only the two rows
    h713_mips_fw_revs[] declares. Stage 2 C-D needs "ADT-3 2024" (both ADT-3 images) and "HY300 Pro"
    (the owner's report) too: they carry the HDCP wait site."""
    h = sha256_bytes(data)
    for r in FIRMWARE_REVISIONS:
        if r["sha256"] == h:
            return r
    return None


def check_display_cfg(data: bytes) -> List[str]:
    """Parse display_cfg.xml. The stock file ends on a null byte behind </root> -- that is not an error,
    U-Boot hands the file on to the MIPS firmware unchanged anyway; it is only reported."""
    notes = []
    raw = data
    if raw.rstrip(b"\r\n\t \0") != raw.rstrip():
        notes.append("display_cfg.xml: ends on null byte(s) behind </root> (a stock quirk, copied unchanged)")
    text = raw.rstrip(b"\r\n\t \0").decode("utf-8", "replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return notes + [f"display_cfg.xml: not parsable ({e})"]
    children = [k.tag for k in root]
    return notes + [f"display_cfg.xml: well formed, root <{root.tag}>, {len(children)} children"
                    + (": " + ", ".join(sorted(set(children))[:8]) if children else "")]


def check_bootlogo(data: bytes, panel: Optional[dict] = None) -> List[str]:
    """What h713_disp_publish_bmp() in U-Boot will accept, read off the BMP header here.

    `panel` is the board profile's "panel" when the board is known, else None -- then only a
    plausible geometry is asked for. Every entry of the result is a finding, never an abort."""
    if len(data) < 54 or data[:2] != b"BM":
        return [f"no BMP header ({hexdump_short(data, 8)}, {len(data)} B)"]
    width, height, planes, bpp, compression = struct.unpack_from("<iiHHI", data, 18)
    rows = -height if height < 0 else height
    findings = []
    if planes != 1:
        findings.append(f"{planes} plane(s) instead of 1")
    if bpp != 24:
        findings.append(f"{bpp} bpp instead of 24 -- the blitter reads 24-bit BGR only")
    if compression != 0:
        findings.append(f"compression {compression} instead of 0 (BI_RGB) -- uncompressed only")
    if height < 0:
        findings.append(f"height {height}: top-down; the stock logo is bottom-up (positive height)")
    if panel and panel.get("width") and panel.get("height"):
        if (width, rows) != (panel["width"], panel["height"]):
            findings.append(f"{width}x{rows}, but this board's panel is {panel['width']}x{panel['height']} -- U-Boot takes no other size")
    elif not (320 <= width <= 4096 and 320 <= rows <= 4096):
        findings.append(f"{width}x{rows} is not a plausible panel size (320..4096)")
    return findings
