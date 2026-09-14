# -*- coding: utf-8 -*-
"""ext4 — read-only, in plain Python (standard library); the old way through debugfs stays as --use-debugfs.

Stage 1 of plan doku/121: moved verbatim from `h713-extract` (X:1142-1673), identifiers and comments translated
to English, every user-visible string and every key of the returned dicts kept byte-identical.
"""

from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional

from h713.log import Abort, Log
from h713.source import Source, materialize


class Ext4Base:
    """Common surface of the two ext4 readers (Python reader and debugfs fallback).

    `exists` and `walk` sit here on purpose: the output of the tool depends on the order in which `walk` runs
    and on the field names of the entries — for both ways these are guaranteed to be the same.
    An entry is {'name', 'ino', 'mode', 'size', 'typ'} with 'typ' out of 'd' (directory), 'l' (symlink),
    'f' (everything else); 'size' is 0 for directories (that is how debugfs `ls -p` prints it).
    """

    description: str = ""

    def ls(self, path: str) -> list[dict]:
        raise NotImplementedError

    def read(self, path: str, tmp: Optional[Path] = None) -> bytes:
        raise NotImplementedError

    def exists(self, path: str) -> Optional[dict]:
        d, n = path.rsplit("/", 1)
        for e in self.ls(d or "/"):
            if e["name"] == n:
                return e
        return None

    def walk(self, root: str = "/", max_depth: int = 6):
        """All files (path, entry) below root."""
        open_list = [(root.rstrip("/") or "/", 0)]
        while open_list:
            path, depth = open_list.pop()
            for e in self.ls(path):
                full = (path.rstrip("/") + "/" + e["name"])
                if e["typ"] == "d":
                    if depth < max_depth:
                        open_list.append((full, depth + 1))
                else:
                    yield full, e


class Ext4(Ext4Base):
    """Read-only ext2/3/4 in plain Python — no debugfs, no mount, no e2fsprogs, runs under Windows as well.

    Needed for the vendor partition (ext4, ~114 MB), the source of EDID, `libmspsound.so`, the PQ files and
    `panel_config.ini`. That partition never sits at the start of a file but as a range inside a bigger file
    (IMAGEWTY → super → LP extent, often Android-sparse on top); this is why the reader reads through a
    `Source` — which is exactly "(file, start offset, length)" and replaces the `?offset=` of debugfs. Putting
    the partition down as an intermediate file is thereby not needed at all.

    Can do: superblock (magic 0xEF53), group descriptors (32 and 64 B, INCOMPAT_64BIT), inodes of any size,
    extents (magic 0xF30A, trees of depth > 0 as well, unwritten extents read as zeros), the old indirect
    blocks (1st/2nd/3rd level), linear directories (also in a `dir_index` filesystem: the hash tree nodes are
    disguised as entries with inode 0 and are skipped), path resolution with symlinks (fast ones in the inode
    as well as slow ones in blocks) and files with holes (sparse).

    Cannot do (and does not need to here): writing, journal replay, encryption, `inline_data`, `bigalloc`,
    `meta_bg`. Every one of these cases is detected and reported loudly, not silently read wrong.
    """

    MAGIC = 0xEF53
    ROOT = 2                                # inode number of the root

    INCOMPAT_COMPRESSION = 0x0001
    INCOMPAT_FILETYPE    = 0x0002
    INCOMPAT_META_BG     = 0x0010
    INCOMPAT_EXTENTS     = 0x0040
    INCOMPAT_64BIT       = 0x0080
    INCOMPAT_INLINE_DATA = 0x8000
    INCOMPAT_ENCRYPT     = 0x10000
    ROCOMPAT_BIGALLOC    = 0x0200

    FL_EXTENTS     = 0x00080000             # EXT4_EXTENTS_FL
    FL_INLINE_DATA = 0x10000000             # EXT4_INLINE_DATA_FL
    FL_ENCRYPT     = 0x00000800             # EXT4_ENCRYPT_FL

    EXT_MAGIC = 0xF30A                      # eh_magic in the extent header
    MAX_SYMLINK = 16                        # symlink chains per path
    BLOCK_CHUNK = 8 << 20                   # largest single read

    def __init__(self, q: Source, tmp: Optional[Path] = None, label: str = "ext4", log: Optional[Log] = None):
        self.q, self.label = q, label
        self.log = log or Log(quiet=True)
        self.problems: list[str] = []
        sb = q.read(0x400, 0x400)
        if len(sb) < 0x100 or struct.unpack_from("<H", sb, 0x38)[0] != self.MAGIC:
            raise Abort(f"{label}: kein ext4-Superblock (Magic bei 0x438 fehlt) — erofs/f2fs? Nicht unterstützt.")
        u32 = lambda o: struct.unpack_from("<I", sb, o)[0]       # noqa: E731
        u16 = lambda o: struct.unpack_from("<H", sb, o)[0]       # noqa: E731
        self.inodes_count = u32(0x00)
        s_blocks_lo = u32(0x04)
        self.first_data_block = u32(0x14)
        log_bs = u32(0x18)
        if log_bs > 16:
            raise Abort(f"{label}: unsinnige Blockgröße im Superblock (s_log_block_size {log_bs})")
        self.block_size = 1024 << log_bs
        self.blocks_per_group = u32(0x20)
        self.clusters_per_group = u32(0x24)
        self.inodes_per_group = u32(0x28)
        self.rev_level = u32(0x4c)
        self.inode_size = u16(0x58) if self.rev_level >= 1 else 128
        self.feat_compat = u32(0x5c)
        self.feat_incompat = u32(0x60)
        self.feat_ro_compat = u32(0x64)
        self.uuid = sb[0x68:0x78].hex()
        vol = sb[0x78:0x88].split(b"\0")[0].decode("latin1", "replace")
        self.label_fs = vol
        desc_size = u16(0xfe)
        blocks_hi = u32(0x150) if (self.feat_incompat & self.INCOMPAT_64BIT) else 0
        self.blocks_count = s_blocks_lo | (blocks_hi << 32)
        # wording as before — it goes into the manifest (eingang.vendor_fs) and into the report exactly like this.
        self.description = (f"ext4, Block {self.block_size}, {s_blocks_lo} Blöcke = {s_blocks_lo * self.block_size} B, "
                            f"Label '{vol}', feature_incompat {self.feat_incompat:#x}")
        self.log.info(f"{label}: {self.description}")

        if not self.inodes_per_group or not self.blocks_per_group or not self.inode_size:
            raise Abort(f"{label}: unbrauchbarer Superblock (inodes/Gruppe {self.inodes_per_group}, "
                        f"Blöcke/Gruppe {self.blocks_per_group}, Inode-Größe {self.inode_size})")
        if self.inode_size & (self.inode_size - 1) or self.inode_size < 128:
            raise Abort(f"{label}: unsinnige Inode-Größe {self.inode_size}")
        for bit, what in ((self.INCOMPAT_COMPRESSION, "compression"), (self.INCOMPAT_ENCRYPT, "encrypt"),
                          (self.INCOMPAT_INLINE_DATA, "inline_data"), (self.INCOMPAT_META_BG, "meta_bg")):
            if self.feat_incompat & bit:
                raise Abort(f"{label}: ext4-Merkmal '{what}' wird von diesem Leser nicht unterstützt "
                            f"(feature_incompat {self.feat_incompat:#x}) — mit --use-debugfs versuchen")
        if self.feat_ro_compat & self.ROCOMPAT_BIGALLOC:
            raise Abort(f"{label}: ext4-Merkmal 'bigalloc' wird von diesem Leser nicht unterstützt "
                        f"— mit --use-debugfs versuchen")

        self.has_64bit = bool(self.feat_incompat & self.INCOMPAT_64BIT)
        self.desc_size = (desc_size or 32) if self.has_64bit else 32
        if self.desc_size < 32 or self.desc_size > self.block_size:
            raise Abort(f"{label}: unsinnige Gruppendeskriptorgröße {self.desc_size}")
        self.has_filetype = bool(self.feat_incompat & self.INCOMPAT_FILETYPE)
        self.groups = max(1, (self.blocks_count - self.first_data_block + self.blocks_per_group - 1)
                          // self.blocks_per_group)
        # the group descriptors sit in the block behind the superblock
        gd_off = (self.first_data_block + 1) * self.block_size
        gd = q.read(gd_off, self.groups * self.desc_size)
        if len(gd) < self.groups * self.desc_size:
            raise Abort(f"{label}: Gruppendeskriptoren unvollständig ({len(gd)} von "
                        f"{self.groups * self.desc_size} B) — Bereich zu klein?")
        self.inode_table: list[int] = []
        for g in range(self.groups):
            d = gd[g * self.desc_size:(g + 1) * self.desc_size]
            lo = struct.unpack_from("<I", d, 8)[0]
            hi = struct.unpack_from("<I", d, 40)[0] if (self.has_64bit and self.desc_size >= 64) else 0
            self.inode_table.append(lo | (hi << 32))
        self.structure = (f"{self.groups} Gruppe(n) à {self.blocks_per_group} Blöcke, {self.inodes_per_group} Inodes; "
                          f"Inode-Größe {self.inode_size}, Deskriptor {self.desc_size} B"
                          f"{' (64bit)' if self.has_64bit else ''}, {self.inodes_count} Inodes, UUID {self.uuid}")

        self._inode_cache: dict[int, dict] = {}
        self._dir_cache: dict[int, list] = {}
        self._map_cache: dict[int, list] = {}
        self._cache: dict[str, list] = {}
        # counter for the report: which ext4 features the filesystem really uses (keys stay, `stats` prints them)
        self.stat = {"inodes": 0, "extent_inodes": 0, "indirekt_inodes": 0, "extent_max_tiefe": 0,
                     "extent_knoten": 0, "extents": 0, "unbelegte_extents": 0, "loecher": 0,
                     "symlink_schnell": 0, "symlink_block": 0, "verzeichnisse": 0, "htree_verzeichnisse": 0,
                     "gelesene_bytes": 0}

    # ---- blocks ---------------------------------------------------------------------------------

    def _block(self, nr: int, count: int = 1) -> bytes:
        """Read physical blocks; block 0 does not exist as a data block (it is called a "hole")."""
        if nr <= 0:
            return b"\0" * (self.block_size * count)
        if nr + count > self.blocks_count:
            raise Abort(f"{self.label}: Block {nr} liegt außerhalb des Dateisystems ({self.blocks_count} Blöcke)")
        out = bytearray()
        rest, p = count * self.block_size, nr * self.block_size
        while rest > 0:
            k = min(rest, self.BLOCK_CHUNK)
            b = self.q.read(p, k)
            if len(b) < k:
                note = (f"{self.label}: Quelle endet bei {p + len(b)} B, Block {nr}+{count} reicht bis "
                        f"{(nr + count) * self.block_size} B — fehlender Rest wird als Nullen gelesen")
                if note not in self.problems:
                    self.problems.append(note)
                    self.log.warn(note)
                b += b"\0" * (k - len(b))
            out += b
            p += k
            rest -= k
        self.stat["gelesene_bytes"] += len(out)
        return bytes(out)

    # ---- inodes ---------------------------------------------------------------------------------

    @staticmethod
    def _type(mode: int) -> str:
        t = mode & 0o170000
        return "d" if t == 0o040000 else "l" if t == 0o120000 else "f"

    def inode(self, ino: int) -> dict:
        c = self._inode_cache.get(ino)
        if c is not None:
            return c
        if ino < 1 or ino > self.inodes_count:
            raise Abort(f"{self.label}: Inode {ino} liegt außerhalb des Dateisystems (1..{self.inodes_count})")
        g, idx = divmod(ino - 1, self.inodes_per_group)
        off = self.inode_table[g] * self.block_size + idx * self.inode_size
        raw = self.q.read(off, self.inode_size)
        if len(raw) < 128:
            raise Abort(f"{self.label}: Inode {ino} nicht lesbar (Tabelle außerhalb der Quelle?)")
        mode, uid_lo, size_lo, _at, _ct, _mt, _dt, gid_lo, links, blocks_lo, flags = struct.unpack_from(
            "<HHIIIIIHHII", raw, 0)
        i_block = raw[40:100]
        file_acl = struct.unpack_from("<I", raw, 104)[0]
        size_hi = struct.unpack_from("<I", raw, 108)[0]
        ftype = self._type(mode)
        # debugfs `ls -p` prints no size for directories (the field stays empty -> 0)
        size = size_lo | (size_hi << 32)
        # dict keys stay as they are — the extractor's JSON depends on them (stage 1)
        d = {"ino": ino, "mode": mode, "typ": ftype, "uid": uid_lo, "gid": gid_lo, "links": links,
             "flags": flags, "blocks_lo": blocks_lo, "file_acl": file_acl, "i_block": i_block,
             "groesse": size_lo if ftype == "d" else size, "groesse_ls": 0 if ftype == "d" else size}
        self._inode_cache[ino] = d
        self.stat["inodes"] += 1
        if flags & self.FL_EXTENTS:
            self.stat["extent_inodes"] += 1
        elif ftype in ("d", "f") and size:
            self.stat["indirekt_inodes"] += 1
        if ftype == "d":
            self.stat["verzeichnisse"] += 1
            if flags & 0x1000:              # EXT4_INDEX_FL — hash tree, is read linearly
                self.stat["htree_verzeichnisse"] += 1
        return d

    # ---- block mapping: extents and the old indirect blocks --------------------------------------

    def _extent_node(self, raw: bytes, ino: int, out: list, level: int = 0):
        if len(raw) < 12:
            raise Abort(f"{self.label}: Inode {ino}: Extent-Knoten zu kurz")
        magic, entries, _max, depth, _gen = struct.unpack_from("<HHHHI", raw, 0)
        if magic != self.EXT_MAGIC:
            raise Abort(f"{self.label}: Inode {ino}: Extent-Kopf ohne Magic 0xF30A (ist {magic:#06x})")
        self.stat["extent_knoten"] += 1
        self.stat["extent_max_tiefe"] = max(self.stat["extent_max_tiefe"], depth + level)
        if 12 + entries * 12 > len(raw):
            raise Abort(f"{self.label}: Inode {ino}: {entries} Extent-Einträge passen nicht in den Knoten")
        for i in range(entries):
            o = 12 + i * 12
            if depth == 0:
                ee_block, ee_len, hi, lo = struct.unpack_from("<IHHI", raw, o)
                written = ee_len <= 32768
                length = ee_len if written else ee_len - 32768
                if not written:
                    self.stat["unbelegte_extents"] += 1
                self.stat["extents"] += 1
                # Unwritten extents (fallocate) read as zeros — so treat them like a hole.
                out.append((ee_block, length, (lo | (hi << 32)) if written else 0))
            else:
                ei_block, leaf_lo, leaf_hi, _u = struct.unpack_from("<IIHH", raw, o)
                child = self._block(leaf_lo | (leaf_hi << 32))
                self._extent_node(child, ino, out, level + 1)

    def _indirect(self, nr: int, level: int, start: int, mapping: list, limit: int):
        """Walk the indirect blocks (ext2/3 style) recursively; `start` is the first logical block below them."""
        per = self.block_size // 4
        span = per ** (level - 1)
        if nr == 0:
            return
        tab = self._block(nr)
        for i in range(per):
            lb = start + i * span
            if lb >= limit:
                break
            p = struct.unpack_from("<I", tab, i * 4)[0]
            if level == 1:
                if p:
                    mapping.append((lb, 1, p))
            else:
                self._indirect(p, level - 1, lb, mapping, limit)

    def _map(self, ino: int, inode: dict) -> list:
        """List of (logical start, number of blocks, physical start); what is missing is a hole."""
        c = self._map_cache.get(ino)
        if c is not None:
            return c
        if inode["flags"] & self.FL_INLINE_DATA:
            raise Abort(f"{self.label}: Inode {ino}: inline_data wird von diesem Leser nicht unterstützt")
        if inode["flags"] & self.FL_ENCRYPT:
            raise Abort(f"{self.label}: Inode {ino}: verschlüsselt — wird nicht gelesen")
        mapping: list = []
        if inode["flags"] & self.FL_EXTENTS:
            self._extent_node(inode["i_block"], ino, mapping)
        else:
            nb = (inode["groesse"] + self.block_size - 1) // self.block_size
            ib = struct.unpack_from("<15I", inode["i_block"], 0)
            for i in range(12):
                if i >= nb:
                    break
                if ib[i]:
                    mapping.append((i, 1, ib[i]))
            per = self.block_size // 4
            self._indirect(ib[12], 1, 12, mapping, nb)
            self._indirect(ib[13], 2, 12 + per, mapping, nb)
            self._indirect(ib[14], 3, 12 + per + per * per, mapping, nb)
        mapping.sort()
        self._map_cache[ino] = mapping
        return mapping

    def _data(self, ino: int, inode: dict) -> bytes:
        size = inode["groesse"]
        if size == 0:
            return b""
        if inode["typ"] == "l" and self._is_fast_symlink(inode):
            return inode["i_block"][:size]
        out = bytearray(size)                           # holes stay zeros (sparse)
        bs = self.block_size
        filled = 0
        for lblk, ln, pblk in self._map(ino, inode):
            if pblk == 0:
                continue
            off = lblk * bs
            if off >= size:
                continue
            n = min(ln * bs, size - off)
            out[off:off + n] = self._block(pblk, ln)[:n]
            filled += n
        if filled < size:
            self.stat["loecher"] += 1
        return bytes(out)

    def _is_fast_symlink(self, inode: dict) -> bool:
        """Fast symlink: the target sits in i_block, no data blocks hang off the inode."""
        ea = (self.block_size >> 9) if inode["file_acl"] else 0
        return inode["blocks_lo"] - ea == 0 and inode["groesse"] <= 60

    def symlink_target(self, ino: int, inode: dict) -> str:
        if self._is_fast_symlink(inode):
            self.stat["symlink_schnell"] += 1
            raw = inode["i_block"][:inode["groesse"]]
        else:
            self.stat["symlink_block"] += 1
            raw = self._data(ino, inode)
        return raw.split(b"\0")[0].decode("utf-8", "replace")

    # ---- directories (linear; hash tree nodes disguise themselves as entries with inode 0) --------

    def _directory(self, ino: int) -> list[tuple[str, int, int]]:
        c = self._dir_cache.get(ino)
        if c is not None:
            return c
        inode = self.inode(ino)
        data = self._data(ino, inode)
        out: list[tuple[str, int, int]] = []
        bs = self.block_size
        for bo in range(0, len(data), bs):
            blk = data[bo:bo + bs]
            off = 0
            while off + 8 <= len(blk):
                child, rec_len, name_len, ftype = struct.unpack_from("<IHBB", blk, off)
                if rec_len < 8 or rec_len % 4 or off + rec_len > len(blk):
                    if child or off == 0:
                        self.problems.append(f"Inode {ino}: kaputter Verzeichniseintrag bei {bo + off} "
                                             f"(rec_len {rec_len})")
                    break
                nl = name_len if self.has_filetype else (name_len | (ftype << 8))
                if child and 8 + nl <= rec_len:
                    name = blk[off + 8:off + 8 + nl].decode("utf-8", "replace")
                    out.append((name, child, ftype if self.has_filetype else 0))
                off += rec_len
        self._dir_cache[ino] = out
        return out

    # ---- paths (with symlinks) -------------------------------------------------------------------

    def _child(self, ino: int, name: str) -> Optional[int]:
        for n, child_ino, _ft in self._directory(ino):
            if n == name:
                return child_ino
        return None

    def path_inode(self, path: str, follow_last: bool = True) -> Optional[int]:
        """Inode number for an absolute path; symlinks are followed (fast ones as well as slow ones)."""
        ino = self.ROOT
        parts = [t for t in path.split("/") if t and t != "."]
        i, links = 0, 0
        while i < len(parts):
            name = parts[i]
            i += 1
            inode = self.inode(ino)
            if inode["typ"] != "d":
                return None
            child = self._child(ino, name)
            if child is None:
                return None
            child_inode = self.inode(child)
            if child_inode["typ"] == "l" and (follow_last or i < len(parts)):
                links += 1
                if links > self.MAX_SYMLINK:
                    raise Abort(f"{self.label}: {path}: Symlinks im Kreis (mehr als {self.MAX_SYMLINK} Stufen)")
                target = self.symlink_target(child, child_inode)
                rest = parts[i:]
                parts = [t for t in target.split("/") if t and t != "."] + rest
                i = 0
                if target.startswith("/"):
                    ino = self.ROOT
                continue                                # relative: `ino` stays the parent directory
            ino = child
        return ino

    # ---- surface (as with the debugfs way) -------------------------------------------------------

    def ls(self, path: str) -> list[dict]:
        if path in self._cache:
            return self._cache[path]
        entries: list[dict] = []
        ino = self.path_inode(path or "/")
        if ino is not None:
            inode = self.inode(ino)
            if inode["typ"] == "d":
                for name, child_ino, _ft in self._directory(ino):
                    if name in (".", ".."):
                        continue
                    ci = self.inode(child_ino)
                    entries.append({"name": name, "ino": child_ino, "mode": ci["mode"], "size": ci["groesse_ls"],
                                    "typ": ci["typ"]})
        self._cache[path] = entries
        return entries

    def read(self, path: str, tmp: Optional[Path] = None) -> bytes:
        ino = self.path_inode(path)
        if ino is None:
            raise Abort(f"{self.label}: {path} nicht gefunden")
        inode = self.inode(ino)
        if inode["typ"] == "d":
            raise Abort(f"{self.label}: {path} ist ein Verzeichnis")
        return self._data(ino, inode)

    def stats(self) -> str:
        s = self.stat
        return (f"{self.structure}; gelesen: {s['inodes']} Inodes ({s['extent_inodes']} mit Extents, "
                f"{s['indirekt_inodes']} indirekt), {s['extents']} Extents in {s['extent_knoten']} Knoten, "
                f"Baumtiefe max {s['extent_max_tiefe']}, {s['unbelegte_extents']} unbelegt, "
                f"{s['verzeichnisse']} Verzeichnisse ({s['htree_verzeichnisse']} mit dir_index-Flag), "
                f"{s['symlink_schnell']}+{s['symlink_block']} Symlinks (schnell+in Blöcken), "
                f"{s['loecher']} Dateien mit Löchern, {s['gelesene_bytes']} B aus der Quelle geholt")


class Ext4Debugfs(Ext4Base):
    """The old way through `debugfs` from e2fsprogs (`--use-debugfs`) — as a cross-check for the Python reader.

    Needs an installed e2fsprogs and therefore does not run everywhere (under Windows not at all); on top of
    that it cannot always read the partition in place and then puts it down as a file in between.
    """

    def __init__(self, q: Source, tmp: Path, label: str, log: Log):
        self.log = log
        sb = q.read(0x400, 0x100)
        if len(sb) < 0x100 or struct.unpack_from("<H", sb, 0x38)[0] != 0xEF53:
            raise Abort(f"{label}: kein ext4-Superblock (Magic bei 0x438 fehlt) — erofs/f2fs? Nicht unterstützt.")
        s_blocks_lo = struct.unpack_from("<I", sb, 4)[0]
        log_bs = struct.unpack_from("<I", sb, 0x18)[0]
        self.block_size = 1024 << log_bs
        vol = sb[0x78:0x88].split(b"\0")[0].decode("latin1", "replace")
        feat_incompat = struct.unpack_from("<I", sb, 0x60)[0]
        self.description = (f"ext4, Block {self.block_size}, {s_blocks_lo} Blöcke = {s_blocks_lo * self.block_size} B, "
                            f"Label '{vol}', feature_incompat {feat_incompat:#x}")
        log.info(f"{label}: {self.description}")
        if shutil.which("debugfs") is None:
            raise Abort("debugfs (e2fsprogs) nicht gefunden — nötig für --use-debugfs (ohne die Option "
                        "liest h713-extract ext4 selbst)")
        b = q.backing()
        self.file: Optional[Path] = None
        if b is not None:
            self.dev = f"{b[0]}?offset={b[1]}"
            # probe: can this debugfs version do '?offset=' ?
            if "Inode: 2" not in self._raw(["stat <2>"]).get("stat <2>", ""):
                log.info("debugfs kann '?offset=' hier nicht — Partition wird zwischengespeichert")
                b = None
        if b is None:
            self.file = tmp / f"{label}.ext4"
            materialize(q, self.file, log)
            self.dev = str(self.file)
        self._cache: dict[str, list] = {}

    def _raw(self, cmds: list[str]) -> dict[str, str]:
        r = subprocess.run(["debugfs", "-f", "-", self.dev], input=("\n".join(cmds) + "\n").encode(),
                           capture_output=True)
        text = r.stdout.decode("utf-8", "replace")
        out: dict[str, str] = {}
        current = None
        for line in text.splitlines():
            if line.startswith("debugfs: "):
                current = line[len("debugfs: "):].strip()
                out.setdefault(current, "")
            elif current is not None:
                out[current] += line + "\n"
        return out

    def ls(self, path: str) -> list[dict]:
        if path in self._cache:
            return self._cache[path]
        cmd = f"ls -p {path}"
        out = self._raw([cmd]).get(cmd, "")
        entries = []
        for line in out.splitlines():
            if not line.startswith("/"):
                continue
            f = line.split("/")
            # /ino/mode/uid/gid/name/size/
            if len(f) < 7:
                continue
            try:
                ino, mode = int(f[1]), int(f[2], 8)
                size = int(f[6]) if f[6] else 0
            except ValueError:
                continue
            name = f[5]
            if name in (".", ".."):
                continue
            entries.append({"name": name, "ino": ino, "mode": mode, "size": size,
                            "typ": "d" if (mode & 0o170000) == 0o040000 else "l" if (mode & 0o170000) == 0o120000 else "f"})
        self._cache[path] = entries
        return entries

    def read(self, path: str, tmp: Optional[Path] = None) -> bytes:
        target = Path(tmp) / ("dump-" + hashlib.md5(path.encode()).hexdigest())
        cmd = f"dump -p {path} {target}"
        self._raw([cmd])
        if not target.exists():
            raise Abort(f"debugfs konnte {path} nicht lesen")
        b = target.read_bytes()
        target.unlink()
        return b
