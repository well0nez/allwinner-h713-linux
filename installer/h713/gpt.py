# -*- coding: utf-8 -*-
"""GPT: reader for a raw eMMC dump, one builder for both of our tables, and the checker.

Three implementations existed before stage 1 and are merged here (plan doku/121):

  * the reader ``Gpt`` of ``h713-extract``                       (X:632),
  * ``gpt_bauen`` for our layout v3 and ``gpt_pruefen``          (M:294, M:344),
  * ``stock_gpt_bauen`` for the vendor table of sys_partition.fex (I:1883).

Both builders write the same protective MBR, the same header layout, the same backup
placement and compute the CRCs in the same order; they differ only in the values that
``build_gpt`` now takes as parameters (entry count, first usable LBA, GUID scheme,
attributes, the reserved header field). The two thin wrappers ``build_layout_gpt`` and
``build_stock_gpt`` carry the old defaults, so the bytes are identical to what the two
tools produced before. Parameter-by-parameter mapping: see RENAMES.md / REPORT.md.
"""

from __future__ import annotations

import struct
import uuid
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from h713.log import Log
from h713.source import Source
from h713.util import crc32

from h713.util import SECTOR   # one definition for the whole package
GPT_ENTRY_SIZE = 128
GPT_HEADER_LBA = 1
GPT_ENTRIES = 26                 # M:81 "mehr Eintraege reichten in die SPL" -- 128 entries
                                 # would be 32 sectors and reach into hy310-spl at LBA 16.
GPT_ENTRIES_LBA = 2

# --------------------------------------------------------------------------------- defaults
# Our layout v3 (partitions, GUIDs, first usable LBA, part C) lives in h713/layout.py (B6,
# M:77-111). gpt.py must not import layout at module level (the import graph runs
# layout -> gpt), so build_layout_gpt() and check_gpt() fetch their defaults lazily; both stay
# callable without arguments, exactly as gpt_bauen()/gpt_pruefen() are today.

DEFAULT_DISK_SECTORS = 15269888                             # M:78, I:45 -- 7.28 GiB, the HY310 eMMC


def _layout():
    from h713 import layout          # lazy: layout imports gpt, not the other way round
    return layout


STOCK_DISK_GUID = "ab6f3888-569a-4926-9668-80941dcb40bc"        # I:1884
STOCK_GUID_BASE = "a0085546-4166-744a-a353-fca9272b8e45"        # I:1885
STOCK_TYPE_GUID = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"        # I:1899, the usual Allwinner one
STOCK_FIRST_USABLE = 73728                                      # I:1903, first partition as measured


# --------------------------------------------------------------------------------- reader

class Gpt:
    """Read the GPT of a raw eMMC dump (X:632)."""

    @staticmethod
    def is_gpt(q: Source) -> bool:
        return q.size >= 34 * SECTOR and q.read(SECTOR, 8) == b"EFI PART"

    def __init__(self, q: Source, log: Log):
        h = q.read(SECTOR, 92)
        sig, rev, hsz, hcrc, _z, cur, bak, first, last = struct.unpack_from("<8sIIIIQQQQ", h, 0)
        pe_lba, pe_n, pe_sz, pe_crc = struct.unpack_from("<QIII", h, 72)
        hh = bytearray(h[:hsz])
        struct.pack_into("<I", hh, 16, 0)
        self.header_ok = crc32(bytes(hh)) == hcrc
        self.disk_guid = h[56:72]
        tab = q.read(pe_lba * SECTOR, pe_n * pe_sz)
        self.table_ok = crc32(tab) == pe_crc
        self.first, self.last, self.backup_lba = first, last, bak
        self.parts: Dict[str, Tuple[int, int]] = {}
        for i in range(pe_n):
            e = tab[i * pe_sz:(i + 1) * pe_sz]
            if len(e) < 128 or e[:16] == b"\0" * 16:
                continue
            s, en = struct.unpack_from("<QQ", e, 32)
            name = e[56:128].decode("utf-16le", "replace").rstrip("\0")
            self.parts[name] = (s, en - s + 1)
        log.info(f"GPT: header CRC {'ok' if self.header_ok else 'WRONG'}, table CRC {'ok' if self.table_ok else 'WRONG'}, "
                 f"{pe_n} entries of {pe_sz} B from LBA {pe_lba}, usable {first}..{last}, backup header LBA {bak}")
        log.info("partitions: " + ", ".join(f"{n}@{s}+{c}" for n, (s, c) in self.parts.items()))

    def partition(self, q: Source, name: str) -> Optional[Source]:
        p = self.parts.get(name)
        if not p:
            return None
        s, c = p
        if (s + c) * SECTOR > q.size:
            return None
        return q.sub(s * SECTOR, c * SECTOR, f"partition {name} (LBA {s}, {c} sectors)")


# --------------------------------------------------------------------------------- builder

def _unique_guid_lookup(unique_guids: Union[str, Sequence[str]]) -> Callable[[int, str], uuid.UUID]:
    """How the unique GUID of entry *i* is found.

    A string is a base GUID that is counted up per index -- p1 ends in 8e45, p2 in 8e46
    and so forth (I:1911). A sequence holds one fixed GUID per partition (M:87, M:308).
    """
    if isinstance(unique_guids, str):
        base = uuid.UUID(unique_guids)
        base_number = int.from_bytes(base.bytes[-6:], "big")

        def counted(i: int, name: str) -> uuid.UUID:
            return uuid.UUID(bytes=base.bytes[:10] + (base_number + i).to_bytes(6, "big"))

        return counted
    fixed = list(unique_guids)
    return lambda i, name: uuid.UUID(fixed[i])


def build_gpt(disk_sectors, partitions, *, first_usable, disk_guid, type_guid, unique_guids,
              entry_count, attributes=0, last_usable=None, entry_size=GPT_ENTRY_SIZE,
              entries_lba=GPT_ENTRIES_LBA, header_reserved=0) -> Dict[int, bytes]:
    """Protective MBR, primary header, entry table and both backup copies.

    Return value: {lba: bytes}. One builder for both tables we write; the differences
    between our layout v3 and the stock table are deliberate and stand in doku/109 §2.2:
    FirstUsableLBA 16 instead of 73728, six entries, and the reserved field at offset 20
    stays 0 (the manufacturer writes 1 there).

    ``attributes`` is either one value for every entry or a callable (index, name) -> int.
    ``unique_guids`` is a base GUID (counted up) or one GUID per partition, see
    ``_unique_guid_lookup``. ``partitions`` are (name, start_lba, sectors, ...) tuples;
    everything after the third field is ignored here (it is the unique GUID in M:87 and
    the source file name in I:1621).
    """
    if last_usable is None:
        last_usable = disk_sectors - 34
    type_le = uuid.UUID(type_guid).bytes_le
    unique_of = _unique_guid_lookup(unique_guids)
    attributes_of = attributes if callable(attributes) else (lambda i, name: attributes)

    arr = bytearray()
    for i in range(entry_count):
        if i < len(partitions):
            name, lba, sectors = partitions[i][0], partitions[i][1], partitions[i][2]
            # A partition declared with size 0 (UDISK) runs to the last usable sector (I:1910).
            end = (last_usable if not sectors else lba + sectors - 1)
            e = (type_le + unique_of(i, name).bytes_le +
                 struct.pack("<QQQ", lba, end, attributes_of(i, name)) +
                 name.encode("utf-16-le").ljust(72, b"\0")[:72])
        else:
            e = b"\0" * entry_size
        arr += e[:entry_size]
    entry_crc = crc32(bytes(arr))

    def header(my_lba, alt_lba, table_lba):
        h = bytearray(92)
        h[0:8] = b"EFI PART"
        struct.pack_into("<III", h, 8, 0x10000, 92, 0)      # revision, header size, CRC = 0
        struct.pack_into("<I", h, 20, header_reserved)      # reserved per UEFI, must be 0;
        #                                                     the manufacturer writes 1 (I:1930)
        struct.pack_into("<QQQQ", h, 24, my_lba, alt_lba, first_usable, last_usable)
        h[56:72] = uuid.UUID(disk_guid).bytes_le
        struct.pack_into("<QIII", h, 72, table_lba, entry_count, entry_size, entry_crc)
        struct.pack_into("<I", h, 16, crc32(bytes(h)))
        return bytes(h).ljust(SECTOR, b"\0")

    array_sectors = (entry_count * entry_size + SECTOR - 1) // SECTOR
    backup_table_lba = disk_sectors - 1 - array_sectors
    mbr = bytearray(SECTOR)
    mbr[510:512] = b"\x55\xaa"
    # As measured on the device: type 0xEE over the whole disk, size 0xFFFFFFFF instead of
    # the real sector count (usual for protective MBRs).
    mbr[446:462] = (b"\x00\x00\x02\x00\xee\xff\xff\xff" +
                    struct.pack("<II", 1, 0xFFFFFFFF))
    table = bytes(arr).ljust(array_sectors * SECTOR, b"\0")
    return {
        0: bytes(mbr),
        GPT_HEADER_LBA: header(GPT_HEADER_LBA, disk_sectors - 1, entries_lba),
        entries_lba: table,
        backup_table_lba: table,
        disk_sectors - 1: header(disk_sectors - 1, GPT_HEADER_LBA, backup_table_lba),
    }


def build_layout_gpt(disk_sectors=None, partitions=None,
                     disk_guid=None, type_guid=None) -> Dict[int, bytes]:
    """The GPT of our layout v3 (M:294 gpt_bauen), byte for byte. Defaults from h713.layout."""
    L = _layout()
    disk_sectors = L.DISK_SECTORS if disk_sectors is None else disk_sectors
    partitions = L.PARTITIONS if partitions is None else partitions
    disk_guid = L.DISK_GUID if disk_guid is None else disk_guid
    type_guid = L.TYPE_GUID if type_guid is None else type_guid
    return build_gpt(disk_sectors, partitions,
                     first_usable=L.FIRST_USABLE,
                     disk_guid=disk_guid,
                     type_guid=type_guid,
                     unique_guids=[p[3] for p in partitions],
                     entry_count=GPT_ENTRIES,
                     attributes=0,
                     header_reserved=0)


def _stock_attributes(index: int, name: str) -> int:
    # Attributes as measured on the stock dump: bit 63 on every partition, and "frp"
    # carries bit 47 in addition (I:1915).
    return (1 << 63) | ((1 << 47) if name == "frp" else 0)


def build_stock_gpt(partitions, disk_sectors=DEFAULT_DISK_SECTORS,
                    disk_guid=STOCK_DISK_GUID,
                    guid_base=STOCK_GUID_BASE,
                    entry_count=None) -> Dict[int, bytes]:
    """Rebuild the stock partition table from sys_partition.fex (I:1883 stock_gpt_bauen).

    Without it Android does not find its partitions -- the manufacturer's tool writes it,
    so we have to as well. The values are read off the device (dump taken before the
    conversion): 26 entries of 128 bytes from LBA 2, FirstUsable 73728, the type GUID
    throughout the usual Allwinner one, and the unique GUIDs are simply numbered through --
    p1 ends in 8e45, p2 in 8e46 and so forth.

    `entry_count` defaults to the number of partitions the image declares -- 26 for the
    HY310, 25 for the two ADT-3 images -- which is what the vendor's own sunxi_gpt.fex
    does (doku/121 section 2 finding 5). Until stage 2 C-C the header said 26 for every
    image, so a 25-partition table carried one all-zero entry inside its CRC. The HY310
    bytes do not change (26 partitions, 26 entries), and neither does the backup
    placement: a table of 25 and one of 26 entries both need seven sectors.
    """
    if entry_count is None:
        entry_count = len(partitions) or GPT_ENTRIES
    return build_gpt(disk_sectors, partitions,
                     first_usable=partitions[0][1] if partitions else STOCK_FIRST_USABLE,
                     disk_guid=disk_guid,
                     type_guid=STOCK_TYPE_GUID,
                     unique_guids=guid_base,
                     entry_count=entry_count,
                     attributes=_stock_attributes,
                     header_reserved=1)


# --------------------------------------------------------------------------------- checker

def check_gpt(mbr_header_table, part_c, disk_sectors=None, *,
              first_usable=None, partitions=None,
              entry_count=GPT_ENTRIES, entry_size=GPT_ENTRY_SIZE,
              part_c_lba=None) -> List[str]:
    """Recompute a built or read GPT (M:344 gpt_pruefen). Return value: list of problems.
    Defaults (disk size, first usable LBA, partitions, part C) come from h713.layout."""
    L = _layout()
    disk_sectors = L.DISK_SECTORS if disk_sectors is None else disk_sectors
    first_usable = L.FIRST_USABLE if first_usable is None else first_usable
    partitions = L.PARTITIONS if partitions is None else partitions
    part_c_lba = L.PART_C_LBA if part_c_lba is None else part_c_lba
    p = []
    if mbr_header_table[510:512] != b"\x55\xaa":
        p.append("Schutz-MBR ohne 55AA")
    if mbr_header_table[450] != 0xEE:
        p.append("protective MBR: the first entry is not type 0xEE")
    hdr = mbr_header_table[SECTOR:2 * SECTOR]
    if hdr[:8] != b"EFI PART":
        p.append("primary GPT header without a signature")
        return p
    hsz = struct.unpack_from("<I", hdr, 12)[0]
    stored = struct.unpack_from("<I", hdr, 16)[0]
    raw = bytearray(hdr[:hsz])
    struct.pack_into("<I", raw, 16, 0)
    if crc32(bytes(raw)) != stored:
        p.append("CRC of the primary GPT header does not match")
    my_lba, alt_lba, first, last = struct.unpack_from("<QQQQ", hdr, 24)
    table_lba, nent, entsz, entry_crc = struct.unpack_from("<QIII", hdr, 72)
    if (my_lba, alt_lba) != (1, disk_sectors - 1):
        p.append("MyLBA/AlternateLBA wrong (%d/%d)" % (my_lba, alt_lba))
    if first != first_usable:
        p.append("FirstUsableLBA is %d, expected %d" % (first, first_usable))
    if last != disk_sectors - 34:
        p.append("LastUsableLBA is %d, expected %d" % (last, disk_sectors - 34))
    if (nent, entsz) != (entry_count, entry_size):
        p.append("%d entries of %d bytes, expected %d of %d" % (nent, entsz, entry_count, entry_size))
    tab = mbr_header_table[table_lba * SECTOR:table_lba * SECTOR + nent * entsz]
    if crc32(tab) != entry_crc:
        p.append("CRC of the partition table does not match")
    found = []
    for i in range(nent):
        e = tab[i * entsz:(i + 1) * entsz]
        if not any(e[:16]):
            continue
        s, en, _at = struct.unpack_from("<QQQ", e, 32)
        found.append((e[56:128].decode("utf-16-le").rstrip("\0"), s, en - s + 1))
    expected = [(pt[0], pt[1], pt[2]) for pt in partitions]
    if found != expected:
        p.append("Partitionsliste weicht ab: %r" % (found,))
    # backup copy
    if part_c is not None:
        bhdr = part_c[(disk_sectors - 1 - part_c_lba) * SECTOR:][:SECTOR]
        if bhdr[:8] != b"EFI PART":
            p.append("the backup copy of the GPT header is missing at the end of the disk (finding S46 B7)")
        else:
            bmy, balt, _bf, _bl = struct.unpack_from("<QQQQ", bhdr, 24)
            btable_lba = struct.unpack_from("<Q", bhdr, 72)[0]
            if (bmy, balt) != (disk_sectors - 1, 1):
                p.append("backup header: MyLBA/AlternateLBA wrong")
            btab = part_c[(btable_lba - part_c_lba) * SECTOR:][:nent * entsz]
            if btab != tab:
                p.append("the backup table differs from the primary one")
            bhsz = struct.unpack_from("<I", bhdr, 12)[0]
            bstored = struct.unpack_from("<I", bhdr, 16)[0]
            braw = bytearray(bhdr[:bhsz])
            struct.pack_into("<I", braw, 16, 0)
            if crc32(bytes(braw)) != bstored:
                p.append("CRC of the backup header does not match")
    return p
