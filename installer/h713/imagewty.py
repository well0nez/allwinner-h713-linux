"""IMAGEWTY (Allwinner PhoenixSuit image) and sunxi-package (TOC1 boot package)."""

from __future__ import annotations

import re
import struct
from typing import Optional

from h713.log import Abort, Log
from h713.source import Source


class Imagewty:
    MAGIC = b"IMAGEWTY"

    @staticmethod
    def is_imagewty(q: Source) -> bool:
        return q.size >= 0x400 and q.read(0, 8) == Imagewty.MAGIC

    def __init__(self, q: Source, log: Log):
        self.q = q
        h = q.read(0, 0x60)
        self.header_version, self.header_size = struct.unpack_from("<II", h, 8)
        self.ram_base, self.version = struct.unpack_from("<II", h, 0x10)
        if self.header_version >= 0x0300:
            # v3/v4 layout (0x0300, 0x0415): image_size as u64 at 0x18, then image_header_size, pid, vid, hw, fw, 1, 1024, num_files
            (self.image_size,) = struct.unpack_from("<Q", h, 0x18)
            (self.image_header_size, self.pid, self.vid, self.hardware_id, self.firmware_id,
             _val1, _val1024, self.num_files) = struct.unpack_from("<8I", h, 0x20)
            self.layout = "v3"
        else:
            # v1 (0x0100, header_size 0x50): image_size u32 at 0x18 — untested
            (self.image_size, self.image_header_size, self.pid, self.vid, self.hardware_id, self.firmware_id,
             _val1, _val1024, self.num_files) = struct.unpack_from("<9I", h, 0x18)
            self.layout = "v1"
            log.warn("IMAGEWTY v1-Kopf (0x0100) — Layout aus awimage übernommen, hier ungetestet")
        log.info(f"IMAGEWTY header_version {self.header_version:#06x} ({self.layout}), header_size {self.header_size:#x}, "
                 f"image_size {self.image_size} B (Datei {q.size} B), image_header_size {self.image_header_size:#x}, "
                 f"pid {self.pid:#x} vid {self.vid:#x} hw {self.hardware_id:#x} fw {self.firmware_id:#x}, {self.num_files} Dateien")
        if self.image_header_size not in (0x400,):
            log.warn(f"image_header_size {self.image_header_size:#x} statt 0x400 — Tabellenlayout unsicher")
        if self.num_files == 0 or self.num_files > 512:
            raise Abort(f"IMAGEWTY: unplausible Dateizahl {self.num_files}")
        # Range 0x60..0x400: fill pattern n^2 mod 256 (observation only, no cipher text)
        pad = q.read(self.header_size, 64)
        quad = bytes(((i * i) & 0xFF) for i in range(64))
        diff = bytes((a - b) & 0xFF for a, b in zip(pad, quad))
        if diff[:4] * 16 == diff:
            log.info("Bereich 0x60..0x3ff: Füllmuster n² mod 256 (kein Chiffrat, keine Nutzdaten)")
        self.entries: dict[str, dict] = {}
        tab = 0x400
        for i in range(self.num_files):
            e = q.read(tab + i * 0x400, 0x400)
            if len(e) < 0x400:
                raise Abort("IMAGEWTY: Dateitabelle abgeschnitten")
            filename_len, total_header_size = struct.unpack_from("<II", e, 0)
            maintype = e[8:16].decode("latin1")
            subtype = e[16:32].decode("latin1")
            if self.layout == "v3":
                fn = e[36:36 + 256].split(b"\0")[0].decode("latin1")
                # filename[256] ends at 0x124 -> stored_length @0x124, pad, original_length @0x12c, pad, offset @0x134
                stored, _p1, original, _p2, off = struct.unpack_from("<5I", e, 0x124)
            else:
                stored, original, off = struct.unpack_from("<3I", e, 36)
                fn = e[52:52 + 256].split(b"\0")[0].decode("latin1")
            if total_header_size != 0x400 or filename_len != 0x100 or not fn:
                raise Abort(f"IMAGEWTY: Dateitabelle bei {tab + i * 0x400:#x} unlesbar (total_header_size {total_header_size:#x}, "
                            f"filename_len {filename_len:#x}) — verschlüsselter Container (RC6)? Dann extern entpacken und --fex-dir nutzen.")
            if off + stored > q.size or original > stored:
                log.warn(f"IMAGEWTY: {fn}: Offset {off:#x} + {stored} überschreitet das Image oder original>stored")
            self.entries.setdefault(fn, {"name": fn, "maintype": maintype, "subtype": subtype,
                                         "offset": off, "stored": stored, "original": original})
        log.info("Dateien: " + ", ".join(self.entries))
        end = max((e["offset"] + e["stored"] for e in self.entries.values()), default=0)
        log.info(f"letzte Nutzdaten enden bei {end:#x} ({end} B); Kopf image_size {self.image_size}, Datei {q.size}")
        if end > q.size:
            log.warn(f"Image abgeschnitten: Nutzdaten reichen bis {end}, Datei hat nur {q.size} B")
        elif self.image_size != q.size:
            log.info(f"Kopf image_size weicht um {self.image_size - q.size:+d} B von der Dateigröße ab — Nutzdaten sind vollständig, "
                     f"nur Beobachtung")

    def file(self, name: str) -> Optional[Source]:
        e = self.entries.get(name)
        if not e:
            return None
        return self.q.sub(e["offset"], e["original"], f"{name} (im Image @{e['offset']:#x})")


class SunxiPackage:
    MAGIC = 0x89119800
    STAMP = 0x5F0A6C39
    NAME = b"sunxi-package"

    def __init__(self, q: Source, off: int, log: Log, origin: str):
        self.origin = origin
        self.off = off
        h = q.read(off, 0x40)
        if h[:13] != self.NAME:
            raise Abort(f"{origin}: kein sunxi-package bei {off:#x}")
        magic, add_sum, serial, status, items_nr, valid_len, vmain, vsub = struct.unpack_from("<8I", h, 16)
        self.problems: list[str] = []
        if magic != self.MAGIC:
            self.problems.append(f"Magic {magic:#x} statt 0x89119800")
        if h[0x3C:0x40] != b"MIE;":
            self.problems.append(f"Kopf-Ende {h[0x3C:0x40]!r} statt 'MIE;'")
        if not (1 <= items_nr <= 32):
            raise Abort(f"{origin}: items_nr {items_nr} unplausibel")
        if valid_len < 0x40 + items_nr * 0x170 or off + valid_len > q.size:
            raise Abort(f"{origin}: valid_len {valid_len:#x} unplausibel")
        buf = bytearray(q.read(off, valid_len))
        struct.pack_into("<I", buf, 20, self.STAMP)
        n4 = len(buf) // 4
        total = sum(struct.unpack_from(f"<{n4}I", buf, 0)) & 0xFFFFFFFF
        self.checksum_ok = total == add_sum
        if not self.checksum_ok:
            self.problems.append(f"add_sum {add_sum:#x}, gerechnet {total:#x}")
        self.items: dict[str, tuple[int, int]] = {}
        for i in range(items_nr):
            o = 0x40 + i * 0x170
            e = buf[o:o + 0x170]
            name = bytes(e[:64]).split(b"\0")[0].decode("latin1", "replace")
            doff, dlen, enc, typ, run, idx = struct.unpack_from("<6I", e, 64)
            if bytes(e[0x16C:0x170]) != b"IIE;":
                self.problems.append(f"Item {i} ({name}): Ende {bytes(e[0x16C:0x170])!r} statt 'IIE;'")
            if doff + dlen > valid_len:
                self.problems.append(f"Item {name}: {doff:#x}+{dlen} überschreitet valid_len")
            if enc:
                self.problems.append(f"Item {name}: encrypt={enc}")
            self.items[name] = (doff, dlen)
        self.q, self.valid_len, self.items_nr = q, valid_len, items_nr
        self.serial, self.status, self.vmain, self.vsub = serial, status, vmain, vsub
        log.info(f"{origin}: sunxi-package @{off:#x}, {items_nr} Items, valid_len {valid_len:#x}, "
                 f"Prüfsumme {'ok' if self.checksum_ok else 'FALSCH'}: " +
                 ", ".join(f"{n}@{o:#x}+{l}" for n, (o, l) in self.items.items()))
        for p in self.problems:
            log.warn(f"{origin}: {p}")

    def item(self, name: str) -> Optional[bytes]:
        it = self.items.get(name)
        if not it:
            return None
        return self.q.read(self.off + it[0], it[1])


def find_sunxi_packages(q: Source, log: Log, max_bytes: Optional[int] = None) -> list[int]:
    """Byte-wise search for 'sunxi-package' (chunks with overlap) — grep is no good for it (doku/105 §6)."""
    hits = []
    chunk, overlap = 8 << 20, 32
    end = q.size if max_bytes is None else min(q.size, max_bytes)
    off = 0
    while off < end:
        b = q.read(off, min(chunk + overlap, end - off))
        i = b.find(SunxiPackage.NAME + b"\0")
        while i >= 0 and i < chunk:
            pos = off + i
            if struct.unpack_from("<I", b, i + 16)[0] == SunxiPackage.MAGIC if i + 20 <= len(b) else False:
                hits.append(pos)
            i = b.find(SunxiPackage.NAME + b"\0", i + 1)
        off += chunk
    return hits


def uboot_version_string(ub: bytes) -> Optional[str]:
    """Version string of the vendor U-Boot ('U-Boot 2018.05-… (Jul 24 2025 - 10:17:21 +0800) Allwinner Technology')."""
    m = re.search(rb"U-Boot [0-9][ -~]{0,120}", ub)
    return m.group(0).decode("latin1") if m else None


def fdt_root(dtb: bytes) -> dict[str, str]:
    """model/compatible of the root of a Flattened Device Tree (observation only, robust against garbage)."""
    try:
        magic, _total, off_struct, off_strings = struct.unpack_from(">IIII", dtb, 0)
        if magic != 0xD00DFEED:
            return {}
        p, depth, props = off_struct, 0, {}
        while p + 4 <= len(dtb):
            tok = struct.unpack_from(">I", dtb, p)[0]
            p += 4
            if tok == 1:      # BEGIN_NODE
                nm = dtb[p:dtb.index(b"\0", p)]
                p = (p + len(nm) + 1 + 3) & ~3
                depth += 1
            elif tok == 3:    # PROP
                ln, noff = struct.unpack_from(">II", dtb, p)
                p += 8
                val = dtb[p:p + ln]
                p = (p + ln + 3) & ~3
                pn = dtb[off_strings + noff:dtb.index(b"\0", off_strings + noff)].decode("latin1")
                if depth == 1 and pn in ("model", "compatible"):
                    props[pn] = " ".join(t.decode("latin1", "replace") for t in val.split(b"\0") if t)
            elif tok == 2:    # END_NODE
                depth -= 1
                if depth <= 0:
                    break
            elif tok == 4:    # NOP
                continue
            else:             # END or garbage
                break
        return props
    except Exception:  # noqa: BLE001
        return {}


def check_scp(scp: bytes, log: Log) -> list[str]:
    """Structural check of the ARISC blob (OR1K, stored word-wise mirrored — analyse/arisc/BEFUND.md)."""
    findings = []
    if len(scp) % 4:
        findings.append(f"Länge {len(scp)} nicht durch 4 teilbar")
    if scp.count(0) == len(scp):
        findings.append("Blob ist leer (nur Nullen)")
        return findings
    if len(scp) >= 0x104:
        w = scp[0x100:0x104][::-1]  # un-mirrored
        op = w[0] >> 2
        if op == 0x00:
            target = 0x100 + (int.from_bytes(w, "big") & 0x3FFFFFF) * 4
            findings.append(f"Reset-Vektor @0x100 = l.j {target:#x} (OR1K, plausibel)")
        else:
            findings.append(f"Reset-Vektor @0x100 ist kein l.j (Opcode {op:#x}) — Byte-Ordnung oder Blob fraglich")
    if len(scp) >= 0x4008:
        head = scp[0x4000:0x4008]
        if head[4:8] == b"CPUs":
            findings.append("Parameterkopf @0x4000: 'CPUs' vorhanden")
        else:
            findings.append(f"Parameterkopf @0x4004 ist {head[4:8]!r}, nicht 'CPUs'")
    # Version string (strings lie word-wise mirrored in the blob)
    mirrored = b"".join(scp[i:i + 4][::-1] for i in range(0, len(scp) - 3, 4))
    m = re.search(rb"[ -~]{0,40}ARISC[ -~]{0,60}", mirrored)
    if m:
        findings.append("Versionsstring: '" + m.group(0).decode("latin1").strip() + "'")
    else:
        findings.append("kein 'ARISC'-Versionsstring gefunden")
    # Share of word-aligned l.nop (0x15000000) after un-mirroring
    nops = 0
    for i in range(0, min(len(scp), 0x20000) - 3, 4):
        if scp[i:i + 4] == b"\x00\x00\x00\x15":
            nops += 1
    findings.append(f"{nops} wortausgerichtete l.nop in den ersten 128 KiB")
    return findings
