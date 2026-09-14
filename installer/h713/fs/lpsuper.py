# -*- coding: utf-8 -*-
"""LP metadata (Android dynamic partitions, "super").

Stage 1 of plan doku/121: moved verbatim from `h713-extract` (X:1024-1129), identifiers and comments translated
to English, every user-visible string and every key of the returned dicts kept byte-identical.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Optional

from h713.log import Abort, Log
from h713.source import ChainSource, NullSource, Source

from h713.util import SECTOR   # one definition for the whole package


class LpSuper:
    GEO_MAGIC = 0x616C4467
    HDR_MAGIC = 0x414C5030

    def __init__(self, q: Source, log: Log):
        self.q = q
        geo = None
        for goff in (4096, 8192):
            g = q.read(goff, 52)
            if len(g) == 52 and struct.unpack_from("<I", g, 0)[0] == self.GEO_MAGIC:
                struct_size = struct.unpack_from("<I", g, 4)[0]
                gg = bytearray(q.read(goff, struct_size))
                chk = bytes(gg[8:40])
                gg[8:40] = b"\0" * 32
                ok = hashlib.sha256(bytes(gg)).digest() == chk
                if ok:
                    geo = g
                    log.info(f"LP-Geometrie @{goff} gültig (sha256 ok)")
                    break
                log.warn(f"LP-Geometrie @{goff}: Prüfsumme falsch")
        if geo is None:
            raise Abort("keine gültige LP-Geometrie bei 4096/8192 — ist das eine 'super'-Partition?")
        self.metadata_max_size, self.slot_count, self.logical_block_size = struct.unpack_from("<III", geo, 40)
        log.info(f"LP: metadata_max_size {self.metadata_max_size}, Slots {self.slot_count}, logical_block {self.logical_block_size}")
        base = 4096 + 2 * 4096
        candidates = [("primär", base)] + [("backup", base + self.slot_count * self.metadata_max_size)]
        self.parts: dict[str, dict] = {}
        found = False
        for location, moff in candidates:
            try:
                self._read_metadata(moff, log, location)
                found = True
                break
            except Abort as e:
                log.warn(f"LP-Metadaten {location} @{moff}: {e}")
        if not found:
            raise Abort("keine gültigen LP-Metadaten")

    def _read_metadata(self, moff: int, log: Log, location: str):
        h = self.q.read(moff, 256)
        magic, major, minor, header_size = struct.unpack_from("<IHHI", h, 0)
        if magic != self.HDR_MAGIC:
            raise Abort(f"Magic {magic:#x}")
        if header_size not in (128, 256):
            raise Abort(f"header_size {header_size}")
        hdr = bytearray(h[:header_size])
        header_checksum = bytes(hdr[12:44])
        hdr[12:44] = b"\0" * 32
        if hashlib.sha256(bytes(hdr)).digest() != header_checksum:
            raise Abort("Kopf-Prüfsumme falsch")
        tables_size = struct.unpack_from("<I", h, 44)[0]
        tables_checksum = h[48:80]
        p_off, p_n, p_sz = struct.unpack_from("<III", h, 80)
        e_off, e_n, e_sz = struct.unpack_from("<III", h, 92)
        g_off, g_n, g_sz = struct.unpack_from("<III", h, 104)
        b_off, b_n, b_sz = struct.unpack_from("<III", h, 116)
        tab = self.q.read(moff + header_size, tables_size)
        if hashlib.sha256(tab).digest() != tables_checksum:
            raise Abort("Tabellen-Prüfsumme falsch")
        extents = []
        for i in range(e_n):
            e = tab[e_off + i * e_sz:e_off + (i + 1) * e_sz]
            num_sectors, target_type, target_data, target_source = struct.unpack_from("<QIQI", e, 0)
            extents.append((num_sectors, target_type, target_data, target_source))
        groups = []
        for i in range(g_n):
            g = tab[g_off + i * g_sz:g_off + (i + 1) * g_sz]
            groups.append(g[:36].split(b"\0")[0].decode("latin1"))
        devices = []
        for i in range(b_n):
            b = tab[b_off + i * b_sz:b_off + (i + 1) * b_sz]
            first_sector, _al, _ao, size = struct.unpack_from("<QIIQ", b, 0)
            devices.append((b[24:60].split(b"\0")[0].decode("latin1"), first_sector, size))
        for i in range(p_n):
            p = tab[p_off + i * p_sz:p_off + (i + 1) * p_sz]
            name = p[:36].split(b"\0")[0].decode("latin1")
            attrs, first_ext, n_ext, grp = struct.unpack_from("<IIII", p, 36)
            exts = extents[first_ext:first_ext + n_ext]
            size = sum(x[0] for x in exts) * SECTOR
            # dict keys stay as they are — the extractor's JSON depends on them (stage 1)
            self.parts[name] = {"attrs": attrs, "extents": exts, "size": size,
                                "gruppe": groups[grp] if grp < len(groups) else "?"}
        self.version = f"{major}.{minor}"
        self.location = location
        self.devices = devices
        log.info(f"LP-Metadaten {location} @{moff}: v{major}.{minor}, header_size {header_size}, {p_n} Partitionen, {e_n} Extents, "
                 f"{g_n} Gruppen, Blockgeräte {', '.join(f'{n}({s} B)' for n, _f, s in devices)}")
        for name, p in self.parts.items():
            ex = "; ".join((f"linear Sektor {d}+{n}" if t == 0 else f"zero {n}") for n, t, d, _s in p["extents"])
            log.info(f"  {name:20s} {p['size']:12d} B  attrs {p['attrs']:#x}  Gruppe {p['gruppe']}  [{ex or 'leer'}]")

    def partition(self, name: str, log: Log) -> Optional[Source]:
        p = self.parts.get(name)
        if not p:
            return None
        pieces = []
        for n, t, d, s in p["extents"]:
            if t == 0:
                pieces.append(self.q.sub(d * SECTOR, n * SECTOR, f"{name} extent"))
            else:
                log.warn(f"LP {name}: Zero-Extent {n} Sektoren — als Nullen gelesen")
                pieces.append(NullSource(n * SECTOR))
        if not pieces:
            return None
        return ChainSource(pieces, f"LP-Partition {name}")
