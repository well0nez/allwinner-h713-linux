# SPDX-License-Identifier: GPL-2.0
"""Read the HDCP key items out of an H713 secure-storage region - structure only.

Why this module exists
----------------------
The boot loader hands this device's own HDCP 1.4 key set to its receiver, reading it
straight out of the secure storage on the eMMC (arch/arm/mach-sunxi/h713_hdcp14.c).
The installer therefore does not have to extract, store or carry the key anywhere -
its whole job is to leave the region alone, which install.py already verifies byte for
byte after writing.

What was missing was the positive statement. Nobody found out at install time whether
the key set is actually intact: a device with a damaged or missing item installs
perfectly and then simply has no protected playback, with no hint why. This module
answers that question, in the same way the C code does - by the item's own structure,
never by a constant offset - so if one of the two disagrees, that is a real finding
and not a parser difference.

It never returns key bytes. The caller gets lengths, verdicts and a fingerprint; the
fingerprint is a SHA-256 and therefore one-way, which is what makes it safe to print
and to compare against the known sets.

Why the key is never written into the repository: it is a DRM secret, and - measured
on two devices with different serial numbers - one and the same key set sits in all of
them, so publishing it would hand everyone the means to circumvent (section 95a UrhG),
while reading our own device stays covered by sections 69d/69e UrhG. See
installer/tests/no_key_material.py, the guard that keeps it that way.

Layout (measured, doku/148 section 1)
-------------------------------------
    region   LBA 12288, 2048 sectors = 1 MiB, slots of 4096 bytes, every item twice
    0x00     u32  magic 0x17253948
    0x08     char name[0x40]
    0x60     u32  payload length
    0x64     u8   payload
             short items (snum, *_hash, wifiBleDatas) keep their data right here
             blob items (hdcpkey, hdcpkeyV22) nest a second header:
    0x64     char name[0x40]
    0xa4     u32  inner length (320 for 1.4, 912 for 2.2)
    0xa8     u32  flags 0x10000001
    0xb0     u8   the key material
"""

from __future__ import annotations

import hashlib
import struct
from typing import Dict, List, Optional

SECTOR = 512
REGION_LBA = 12288
REGION_SECTORS = 2048
SLOT_BYTES = 4096
MAGIC = 0x17253948
NAME_OFF = 0x08
NAME_MAX = 0x40
OUTER_LEN_OFF = 0x60
OUTER_DATA_OFF = 0x64
INNER_LEN_OFF = 0x40
INNER_DATA_OFF = 0x4C
HDCP14_KEY_LEN = 288
HDCP14_RECORD_LEN = 320
HDCP22_RECORD_LEN = 912

# Fingerprints of the key sets we have seen, so a device can be told apart from a
# surprise. Hashes only - see the module docstring.
#
# Measured across two devices with two different serial numbers (an HY310 and an
# HY300 Pro), and the two behave differently:
#
#   HDCP 1.4  the SAME key set in both - a shared key over the product line
#   HDCP 2.2  a DIFFERENT one in each   - device-bound
#
# Which is why a foreign secure-storage region must never be restored onto a device:
# it would overwrite that device's own 2.2 set, its serial number and its MAC
# addresses. install.py compares the region byte for byte after writing and stops with
# exit 10 if it changed.
KNOWN_SETS = {
    # HDCP 1.4, 288 bytes - both devices
    "d743dcf4afe08c23ff5da56931000556a4e4692a8431604134f1cc4031389ea2":
        "the known vendor HDCP 1.4 key set",
    # HDCP 2.2, 912 bytes - per device
    "595989518ba2ff77ce4c146fdb97a4d9ce5bdbb279529b696e353a0b3ce32f61":
        "the HDCP 2.2 key set of the reference HY310",
    "fa0a8bd88f056a5f2a94cda6cac3283ffb313225edd13bffc1b262975a711ba4":
        "the HDCP 2.2 key set of the reference HY300 Pro",
}


def _name_at(slot: bytes, off: int) -> Optional[str]:
    """The NUL-terminated name in a 0x40-byte field, or None if there is none."""
    field = slot[off:off + NAME_MAX]
    if len(field) < NAME_MAX or b"\0" not in field:
        return None
    raw = field.split(b"\0", 1)[0]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def parse_slot(slot: bytes) -> Optional[Dict]:
    """One slot as a dict, or None when there is no item in it.

    The returned dict carries `name`, `outer`, and for a blob item `inner`, `flags`
    and `payload`. A structural problem is reported in `error` instead of raising:
    the caller wants to say what is wrong with a device, not stop.
    """
    if len(slot) < SLOT_BYTES or struct.unpack_from("<I", slot, 0)[0] != MAGIC:
        return None
    name = _name_at(slot, NAME_OFF)
    if name is None:
        return {"name": None, "error": "name field has no terminator"}

    outer = struct.unpack_from("<I", slot, OUTER_LEN_OFF)[0]
    item: Dict = {"name": name, "outer": outer}
    if outer == 0 or OUTER_DATA_OFF + outer > SLOT_BYTES:
        item["error"] = "payload length %d is out of range" % outer
        return item

    data = slot[OUTER_DATA_OFF:OUTER_DATA_OFF + outer]
    # A blob item repeats its own name; a short item just holds raw bytes.
    if _name_at(data, 0) != name:
        item["short"] = True
        item["payload"] = data
        return item

    inner = struct.unpack_from("<I", data, INNER_LEN_OFF)[0]
    item["inner"] = inner
    item["flags"] = struct.unpack_from("<I", data, INNER_LEN_OFF + 4)[0]
    if INNER_DATA_OFF + inner != outer:
        item["error"] = ("inner length %d does not fit outer %d"
                         % (inner, outer))
        return item
    item["payload"] = data[INNER_DATA_OFF:INNER_DATA_OFF + inner]
    return item


def items(region: bytes, slots: int = 32) -> Dict[str, List[Dict]]:
    """Every item of a region, grouped by name, in slot order."""
    out: Dict[str, List[Dict]] = {}
    for index in range(min(slots, len(region) // SLOT_BYTES)):
        item = parse_slot(region[index * SLOT_BYTES:(index + 1) * SLOT_BYTES])
        if item is None:
            continue
        item["slot"] = index
        out.setdefault(item.get("name") or "?", []).append(item)
    return out


def hdcp14_status(region: bytes) -> Dict:
    """What to say about this device's HDCP 1.4 key set.

    Returns a dict with `ok`, a one-line `text` fit to print, and - when there is a
    key set - `length` and `fingerprint`. Mirrors the checks the boot loader makes,
    so a "yes" here means the boot loader will accept it too.
    """
    found = items(region).get("hdcpkey", [])
    if not found:
        return {"ok": False, "copies": 0,
                "text": "no HDCP 1.4 key set in the secure storage - the device "
                        "will boot, but without protected playback"}

    broken = [i for i in found if "error" in i]
    if broken:
        return {"ok": False, "copies": len(found),
                "text": "the HDCP 1.4 item is damaged (%s)" % broken[0]["error"]}

    payloads = [i["payload"] for i in found]
    if any(len(p) < HDCP14_KEY_LEN for p in payloads):
        return {"ok": False, "copies": len(found),
                "text": "the HDCP 1.4 key set is only %d bytes, %d are needed"
                        % (min(len(p) for p in payloads), HDCP14_KEY_LEN)}

    keys = [bytes(p[:HDCP14_KEY_LEN]) for p in payloads]
    if len(set(keys)) != 1:
        return {"ok": False, "copies": len(found),
                "text": "the %d stored copies of the HDCP 1.4 key set differ - the "
                        "boot loader will refuse it" % len(found)}
    if keys[0] == bytes(HDCP14_KEY_LEN) or keys[0] == b"\xff" * HDCP14_KEY_LEN:
        return {"ok": False, "copies": len(found),
                "text": "the HDCP 1.4 key set is blank"}
    if len(found) < 2:
        return {"ok": False, "copies": len(found),
                "text": "only one copy of the HDCP 1.4 key set - the boot loader "
                        "wants both and will refuse it"}

    fingerprint = hashlib.sha256(keys[0]).hexdigest()
    known = KNOWN_SETS.get(fingerprint)
    return {
        "ok": True,
        "copies": len(found),
        "length": len(payloads[0]),
        "fingerprint": fingerprint,
        "text": "HDCP 1.4 key set present and consistent (%d bytes, %d copies, %s)"
                % (len(payloads[0]), len(found),
                   known if known else "fingerprint %s - not one we have seen, "
                                       "please report it" % fingerprint[:16]),
    }


def hdcp14_status_of_file(path: str, offset: int = 0) -> Dict:
    """hdcp14_status() for a region file, or a whole dump at REGION_LBA."""
    with open(path, "rb") as handle:
        handle.seek(offset)
        return hdcp14_status(handle.read(REGION_SECTORS * SECTOR))


# ---------------------------------------------------------------------------
# Unknown board: find the items instead of assuming where they are
# ---------------------------------------------------------------------------
#
# Everything above reads the region at its known place (LBA 12288). That is right for
# the boards we have measured and wrong as a general assumption: a board we have never
# seen may keep its secure storage somewhere else entirely, and then "no key set" would
# be a lie - we simply did not look in the right place.
#
# So this part searches. It walks a whole dump for the slot magic, parses whatever it
# finds, and prints the fingerprints in a form that can be pasted into KNOWN_SETS. On
# an unknown device that turns "I do not recognise this" into "here is exactly what it
# has and here are the hashes to record".
#
# Only fingerprints are ever printed, never key bytes.

SCAN_ALIGN = 512        # a slot always starts on a sector boundary
SCAN_CHUNK = 8 << 20    # read in 8 MiB pieces so a full eMMC dump stays affordable


def find_slots(handle, align: int = SCAN_ALIGN, limit: Optional[int] = None):
    """Yield (byte offset, slot bytes) for every slot magic in an open file.

    Reads in chunks with an overlap of one slot, so a slot that straddles a chunk
    boundary is still found whole.
    """
    magic = struct.pack("<I", MAGIC)
    base = 0
    carry = b""
    while True:
        chunk = handle.read(SCAN_CHUNK)
        if not chunk:
            break
        blob = carry + chunk
        start = base - len(carry)
        pos = 0
        while True:
            pos = blob.find(magic, pos)
            if pos < 0:
                break
            offset = start + pos
            if offset % align == 0 and pos + SLOT_BYTES <= len(blob):
                yield offset, blob[pos:pos + SLOT_BYTES]
            pos += align if offset % align == 0 else 1
        carry = blob[-SLOT_BYTES:] if len(blob) >= SLOT_BYTES else blob
        base += len(chunk)
        if limit is not None and base >= limit:
            break


def survey(path: str, limit: Optional[int] = None) -> List[Dict]:
    """Every secure-storage item in a dump, wherever it lies.

    Each entry: offset, lba, name, lengths, and for a key item its fingerprint and
    whether we know that key set. Written for the unknown-board case, so it makes no
    assumption about the region's position.
    """
    out: List[Dict] = []
    with open(path, "rb") as handle:
        for offset, slot in find_slots(handle, limit=limit):
            item = parse_slot(slot)
            if item is None:
                continue
            row = {"offset": offset, "lba": offset // SECTOR,
                   "name": item.get("name"), "outer": item.get("outer"),
                   "inner": item.get("inner"), "error": item.get("error")}
            payload = item.get("payload")
            if payload and (item.get("name") or "").startswith("hdcpkey") \
                    and not item.get("short"):
                # Two fingerprints matter and they are not the same one: the 1.4 set
                # is the first 288 bytes of a 320-byte record, while the 2.2 set is
                # its whole 912-byte payload. Looking only at the 288-byte prefix
                # reported the known 2.2 set as unknown.
                whole = hashlib.sha256(bytes(payload)).hexdigest()
                row["fingerprint"] = whole
                row["known"] = KNOWN_SETS.get(whole)
                if len(payload) >= HDCP14_KEY_LEN:
                    prefix = hashlib.sha256(
                        bytes(payload[:HDCP14_KEY_LEN])).hexdigest()
                    row["key_fingerprint"] = prefix
                    if row["known"] is None:
                        row["known"] = KNOWN_SETS.get(prefix)
                if row["known"] is None:
                    # The hash worth recording is the one over the whole payload.
                    row["record_me"] = whole
            elif payload and item.get("short"):
                # Short items are serial numbers and MAC blocks: device-bound, and
                # printable in the clear is exactly what we do NOT want by default.
                row["short_len"] = len(payload)
            out.append(row)
    return out


def survey_report(path: str, limit: Optional[int] = None) -> str:
    """survey() as text for a human, with the lines to paste into KNOWN_SETS."""
    rows = survey(path, limit=limit)
    lines = ["secure-storage items in %s" % path]
    if not rows:
        lines.append("  none found - either this board keeps them elsewhere, or the "
                     "dump does not cover them")
        lines.append("  (a '*-filled' image does NOT: the region sits in a gap "
                     "between partitions and is zeroed there)")
        return "\n".join(lines)

    regions = sorted(set(r["lba"] - (r["lba"] % REGION_SECTORS) for r in rows))
    lines.append("  %d item(s), region start(s) at LBA %s"
                 % (len(rows), ", ".join(str(x) for x in regions)))
    unknown = []
    for r in rows:
        note = ""
        if r.get("error"):
            note = "  !! %s" % r["error"]
        elif r.get("known"):
            note = "  %s" % r["known"]
        elif r.get("record_me"):
            note = "  UNKNOWN key set"
            unknown.append((r["name"], r["record_me"]))
        lines.append("  LBA %-8d slot@0x%-9x %-18s outer=%-5s inner=%-5s%s"
                     % (r["lba"], r["offset"], r["name"], r["outer"],
                        r["inner"] if r["inner"] is not None else "-", note))
    if unknown:
        # Every item exists twice; list each distinct set once.
        seen = set()
        unknown = [u for u in unknown
                   if not (u[1] in seen or seen.add(u[1]))]
        lines.append("")
        lines.append("  Not seen before. To record them, add to KNOWN_SETS in "
                     "installer/h713/hdcpitems.py:")
        for name, digest in unknown:
            lines.append('      "%s":' % digest)
            lines.append('          "%s key set of <board>",' % name)
        lines.append("  and to KNOWN in installer/tests/no_key_material.py, so the "
                     "guard knows them too.")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    """h713.hdcpkey <dump or region file> [--limit BYTES]

    Says what HDCP key material a device has and where, by searching rather than by
    assuming - the tool to reach for when a board is not one we know.
    """
    args = [a for a in argv[1:] if not a.startswith("--")]
    limit = None
    for a in argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=", 1)[1], 0)
    if not args:
        print(main.__doc__)
        return 2
    for path in args:
        print(survey_report(path, limit=limit))
        status = hdcp14_status_of_file(path, REGION_LBA * SECTOR) \
            if _looks_like_dump(path) else hdcp14_status_of_file(path)
        print("  verdict at the known region: %s" % status["text"])
    return 0


def _looks_like_dump(path: str) -> bool:
    """A region file is 1 MiB; anything much larger is a whole-disk dump."""
    import os

    try:
        return os.path.getsize(path) > REGION_SECTORS * SECTOR * 2
    except OSError:
        return False


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv))
