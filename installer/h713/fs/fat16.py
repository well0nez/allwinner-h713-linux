# -*- coding: utf-8 -*-
"""FAT12/16/32 with VFAT long names (bootloader_a / bootloader_b / boot-resource.fex, Reserve0).

Stage 1 of plan doku/121: moved verbatim from `h713-extract` (X:674-866), identifiers and comments translated
to English, every user-visible string and every key of the returned dicts kept byte-identical.
"""

from __future__ import annotations

import struct
from typing import Optional

from h713.log import Abort, Log
from h713.source import Source


class Fat:
    """Read-only FAT with long names (VFAT LFN).

    Needed for the vendor partitions bootloader_a/bootloader_b (FAT16, 32 MiB): that is where the MIPS/display
    artefacts sit, and their 8.3 short names are useless - 'PR§÷pð~1.TSE' is really 'ProjectID_0x0032.TSE'.
    Only the LFN entries (attribute 0x0F, 13 UTF-16 characters per entry, backwards in front of the 8.3 entry)
    yield the name that U-Boot expects in h713_disp_read().
    """

    ATTR_LFN = 0x0F
    ATTR_VOLUME = 0x08
    ATTR_DIR = 0x10

    @staticmethod
    def is_fat(q: Source) -> bool:
        b = q.read(0, 512)
        if len(b) < 512 or b[510:512] != b"\x55\xaa" or b[0] not in (0xEB, 0xE9):
            return False
        bps = struct.unpack_from("<H", b, 11)[0]
        return bps in (512, 1024, 2048, 4096) and b[13] in (1, 2, 4, 8, 16, 32, 64, 128) and b[16] in (1, 2)

    def __init__(self, q: Source, log: Log, origin: str):
        self.q, self.log, self.origin = q, log, origin
        self.problems: list[str] = []
        b = q.read(0, 512)
        if len(b) < 512:
            raise Abort(f"{origin}: too small for a FAT boot sector")
        self.bps = struct.unpack_from("<H", b, 11)[0]
        self.spc = b[13]
        self.reserved = struct.unpack_from("<H", b, 14)[0]
        self.nfats = b[16]
        self.root_entries = struct.unpack_from("<H", b, 17)[0]
        ts16 = struct.unpack_from("<H", b, 19)[0]
        fatsz16 = struct.unpack_from("<H", b, 22)[0]
        ts32 = struct.unpack_from("<I", b, 32)[0]
        if not self.bps or not self.spc or not self.nfats or not self.reserved:
            raise Abort(f"{origin}: no usable FAT BPB (bps {self.bps}, spc {self.spc}, fats {self.nfats})")
        self.total = ts16 or ts32
        self.fatsz = fatsz16 or struct.unpack_from("<I", b, 36)[0]
        self.root_cluster = 0 if fatsz16 else struct.unpack_from("<I", b, 44)[0]
        rootsec = (self.root_entries * 32 + self.bps - 1) // self.bps
        self.fat_start = self.reserved
        self.root_start = self.reserved + self.nfats * self.fatsz
        self.data_start = self.root_start + rootsec
        self.cluster_bytes = self.spc * self.bps
        self.cluster_count = max(0, (self.total - self.data_start) // self.spc)
        if self.cluster_count < 4085:
            self.type, self.eoc = "FAT12", 0xFF8
        elif self.cluster_count < 65525:
            self.type, self.eoc = "FAT16", 0xFFF8
        else:
            self.type, self.eoc = "FAT32", 0x0FFFFFF8
        self.label = b[43:54].decode("latin1", "replace").strip() if fatsz16 else b[71:82].decode("latin1", "replace").strip()
        self.description = (f"{self.type}, {self.bps} B/sector, {self.spc} sectors/cluster ({self.cluster_bytes} B), "
                            f"{self.nfats} FATs of {self.fatsz} sectors, root {self.root_entries} entries, "
                            f"{self.total} sectors = {self.total * self.bps} B, {self.cluster_count} clusters, "
                            f"label '{self.label}'")
        log.info(f"{origin}: {self.description}")
        if self.total * self.bps > q.size:
            # bootloader_a/_b are 32 MiB while the BPB claims 128 MiB; boot-resource.fex is cut off behind the
            # payload. Both are harmless as long as the used clusters lie inside the source - otherwise reading
            # the individual file fails and is reported there.
            note = (f"the FAT volume claims {self.total * self.bps} B, the source has {q.size} B -- "
                    f"only what is there is read")
            self.problems.append(note)
            log.info("  " + note)
        self._fat = q.read(self.fat_start * self.bps, min(self.fatsz * self.bps, max(0, q.size - self.fat_start * self.bps)))
        if len(self._fat) < 4:
            raise Abort(f"{origin}: FAT table not readable")

    # ---- cluster chain --------------------------------------------------------------------------

    def _next(self, c: int) -> int:
        if self.type == "FAT12":
            i = c + (c >> 1)
            if i + 2 > len(self._fat):
                return self.eoc
            v = struct.unpack_from("<H", self._fat, i)[0]
            return (v >> 4) if (c & 1) else (v & 0x0FFF)
        if self.type == "FAT16":
            if c * 2 + 2 > len(self._fat):
                return self.eoc
            return struct.unpack_from("<H", self._fat, c * 2)[0]
        if c * 4 + 4 > len(self._fat):
            return self.eoc
        return struct.unpack_from("<I", self._fat, c * 4)[0] & 0x0FFFFFFF

    def chain(self, c: int, max_cluster: Optional[int] = None) -> list[int]:
        out: list[int] = []
        seen: set[int] = set()
        while 2 <= c < self.eoc:
            if c in seen:
                raise Abort(f"{self.origin}: the cluster chain loops at {c}")
            seen.add(c)
            out.append(c)
            if max_cluster is not None and len(out) >= max_cluster:
                break
            c = self._next(c)
        return out

    def _cluster_offset(self, c: int) -> int:
        return (self.data_start + (c - 2) * self.spc) * self.bps

    # ---- directories ----------------------------------------------------------------------------

    @staticmethod
    def _lfn_part(e: bytes) -> str:
        raw = e[1:11] + e[14:26] + e[28:32]
        s = raw.decode("utf-16le", "replace")
        for stop in ("￿", "\0"):
            i = s.find(stop)
            if i >= 0:
                s = s[:i]
        return s

    def _raw_directory(self, cluster: int) -> bytes:
        if cluster == 0:                    # fixed root (FAT12/16)
            return self.q.read(self.root_start * self.bps, (self.data_start - self.root_start) * self.bps)
        return b"".join(self.q.read(self._cluster_offset(c), self.cluster_bytes) for c in self.chain(cluster))

    def entries(self, cluster: int = 0) -> list[dict]:
        """Entries of one directory; 'name' is the long name (fallback: 8.3), 'kurz' always the 8.3 name.

        The dict keys stay as they are - the extractor's JSON and report depend on them (stage 1).
        """
        data = self._raw_directory(cluster if cluster else (self.root_cluster if self.type == "FAT32" else 0))
        out: list[dict] = []
        lfn: list[bytes] = []
        for i in range(0, len(data) - 31, 32):
            e = data[i:i + 32]
            if e[0] == 0x00:
                break
            if e[0] == 0xE5:                # deleted
                lfn = []
                continue
            attr = e[11]
            if attr == self.ATTR_LFN:
                lfn.append(e)
                continue
            base = e[0:8].decode("latin1", "replace").rstrip()
            ext = e[8:11].decode("latin1", "replace").rstrip()
            short = base + ("." + ext if ext else "")
            if short.startswith("\x05"):
                short = "\xe5" + short[1:]
            long_name = ""
            if lfn:
                # The LFN entries sit backwards in front of the 8.3 entry; bit 0x40 marks the last one (= highest sequence).
                for part in sorted(lfn, key=lambda x: x[0] & 0x3F):
                    long_name += self._lfn_part(part)
            lfn = []
            if attr & self.ATTR_VOLUME:     # volume label, not a file
                continue
            cl = struct.unpack_from("<H", e, 26)[0] | (struct.unpack_from("<H", e, 20)[0] << 16)
            size = struct.unpack_from("<I", e, 28)[0]
            name = long_name or short
            if name in (".", ".."):
                continue
            out.append({"name": name, "kurz": short, "lang": bool(long_name), "verzeichnis": bool(attr & self.ATTR_DIR),
                        "cluster": cl, "groesse": size, "attr": attr})
        return out

    def directory(self, path: str) -> Optional[list[dict]]:
        """Entries under a path ('mips' or 'mips/sub'), names compared case-insensitively."""
        cl = 0
        for part in [t for t in path.split("/") if t]:
            hits = [e for e in self.entries(cl) if e["verzeichnis"] and e["name"].lower() == part.lower()]
            if not hits:
                return None
            cl = hits[0]["cluster"]
        return self.entries(cl)

    def read(self, e: dict) -> bytes:
        if e["groesse"] == 0:
            return b""
        needed = (e["groesse"] + self.cluster_bytes - 1) // self.cluster_bytes
        parts: list[bytes] = []
        got = 0
        for c in self.chain(e["cluster"], needed):
            if c - 2 >= self.cluster_count:
                raise Abort(f"{self.origin}: {e['name']}: cluster {c} lies outside the volume")
            b = self.q.read(self._cluster_offset(c), self.cluster_bytes)
            if len(b) < self.cluster_bytes and got + len(b) < e["groesse"]:
                raise Abort(f"{self.origin}: {e['name']}: the source ends in the middle of cluster {c} "
                            f"({got + len(b)} of {e['groesse']} B) -- image truncated?")
            parts.append(b)
            got += len(b)
        d = b"".join(parts)
        if len(d) < e["groesse"]:
            raise Abort(f"{self.origin}: {e['name']}: the cluster chain ends after {len(d)} of {e['groesse']} B")
        return d[:e["groesse"]]
