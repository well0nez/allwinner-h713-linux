"""Allwinner .fex helpers: sys_partition, the boot0 DRAM block, vendor INI files."""

from __future__ import annotations

import re
import struct
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from h713.imagewty import Imagewty

DRAM_FIELDS = ("clk", "type", "zq", "odt_en", "para1", "para2", "mr0", "mr1", "mr2", "mr3") + \
              tuple("tpr%d" % i for i in range(14))


def parse_sys_partition(text):
    """The [partition] blocks of sys_partition.fex, with running start LBA.

    Returns (name, start_lba, sectors, source file|None) in the order of the file.
    """
    partitions = []
    lba = 73728                       # first partition, as measured in the stock
    for block in re.findall(r"\[partition\](.*?)(?=\[partition\]|\[partition_end\]|\Z)",
                            text, re.S):
        # sys_partition.fex has CRLF line endings: without .strip() the
        # expression pulls the carriage return into every unquoted value, and
        # the GPT partition names then carry an invisible U+000D. Android
        # does not find its partitions any more then (finding S46).
        d = {k: v.strip()
             for k, v in re.findall(r"^\s*(\w+)\s*=\s*\"?([^\"\r\n]+)\"?\s*$",
                                    block, re.M)}
        if "name" not in d:
            continue
        sect = int(d.get("size", "0"))
        partitions.append((d["name"], lba, sect, d.get("downloadfile")))
        lba += sect
    return partitions


def stock_plan(image: "Imagewty"):
    """Read from sys_partition.fex in the image what belongs where.

    Returns: (partitions, raw_targets). partitions are (name, start_lba,
    sectors, source file|None) in the order of the file; raw_targets are the
    places outside of every partition (boot0 and the sunxi-package, twice each).
    """
    sysp = image.file("sys_partition.fex")
    if sysp is None:
        raise RuntimeError("sys_partition.fex is missing from the image -- not a full Allwinner image?")
    text = sysp.read(0, sysp.size if hasattr(sysp, "size") else 1 << 20).decode("latin1")
    partitions = parse_sys_partition(text)
    raw = [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
           ("boot_package.fex", 24576), ("boot_package.fex", 32800)]
    return partitions, raw


def dram_block(boot0: bytes) -> dict:
    """The 24 u32 of the DRAM parameter block at 0x38 of boot0 (eGON.BT0)."""
    d = dict(zip(DRAM_FIELDS, struct.unpack_from("<24I", boot0, 0x38)))
    d["clk_mhz"] = d["clk"]
    return d


def parse_ini(text: str) -> dict[str, list[tuple[str, str]]]:
    """Like h713_pq/quellen.py: vendor INI with duplicate keys and ',\\' continuations."""
    sect: dict[str, list[tuple[str, str]]] = {}
    cur: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = sect.setdefault(line[1:-1].strip(), [])
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            cur.append((k.strip(), v.strip()))
    return sect


def ini_numbers(v: str) -> list[int]:
    return [int(t) for t in v.rstrip("\\").split(",") if t.strip() != ""]


def panel_config_id(text: str) -> Optional[int]:
    """ProjectID from panel_config.ini - decimal in the file ('ProjectID = 48' = 0x30)."""
    for _sect, pairs in parse_ini(text).items():
        for k, v in pairs:
            if k.strip().lower() == "projectid":
                try:
                    return int(v.split(";")[0].strip(), 0)
                except ValueError:
                    return None
    return None
