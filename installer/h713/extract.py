# SPDX-License-Identifier: GPL-2.0
"""One extractor run: read an input, put the proprietary parts of an H713 projector next to it.

`Run` is the old `Lauf` of h713-extract (X:1999-3103); `main()` stays in the CLI script.
Stage 1 of doku/121: identifiers, comments and docstrings are English, every user-visible string
(log lines, MANIFEST.json keys, BERICHT.txt, exit codes) is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import time
from pathlib import Path
from typing import Dict, List, Optional

from h713 import hdcpsite
from h713.fex import panel_config_id
from h713.fs import Ext4, Ext4Base, Ext4Debugfs, Fat, LpSuper
from h713.gpt import SECTOR, Gpt
from h713.identify import ID_FEATURES, KNOWN_IMAGES, STRONG_FEATURES, feature_matches, features_of
from h713.imagewty import (Imagewty, SunxiPackage, check_scp, fdt_root, find_sunxi_packages,
                           uboot_version_string)
from h713.log import Abort, Log
from h713.profiles import PROFILES, UBOOT_FW_REVS, legacy_devices
from h713.source import FileSource, SparseSource, Source
from h713.util import hexdump_short, sha256_bytes, sha256_file
from h713.vendorfiles import (AIC_FW_DIR, AIC_FW_TARGET, EDID_14, EDID_20, FALLBACK_MIPS_SOURCES,
                              MIPS_FEX, MIPS_FILES, MIPS_OUTPUT_DIR, MIPS_PART_KEYS, MIPS_PART_NAMES,
                              MIPS_PROJECTID, MIPS_SOURCE_DIR, MSP_LIB_CANDIDATES,
                              PANEL_CONFIG_CANDIDATES, PQ_FILES, REQUIRED_FILES, TVCONFIG,
                              VENDOR_MIPS_DIR, VENDOR_MIPS_SOURCE, check_display_cfg,
                              check_edid_block, check_pq, check_tse, edid_name, edid_vendor,
                              elf_symbol, find_mspm_chain, firmware_revision_of, parse_mspm,
                              read_vendor_mips)

#: X:52 -- the extractor's own version; it goes into MANIFEST.json and BERICHT.txt, and the CLI
#: prints it for --version.
VERSION = "0.4 (S45: eigener ext4-Leser, kein debugfs mehr; ext4 über e2fsprogs nur noch mit --use-debugfs)"

#: X:98 GERAETE -- the two boards this run compares against, in that order.
DEVICES = legacy_devices()


def _va(address: Optional[int]) -> Optional[str]:
    """A virtual address the way the profiles write it, or None -- stage 2 C-D."""
    return None if address is None else "0x%08x" % address


def profile_status(board_id: Optional[str]) -> Optional[str]:
    """The `status` of a board profile: "verified", "profile-only", "partial" -- or None.

    Stage 2 C-D: the report names it next to the board, and only a "verified" profile may still end
    in exit code 0 (doku/121 section 5: nothing else has been run against the hardware)."""
    profile = PROFILES.get(board_id) if board_id else None
    return (profile or {}).get("status")


class Run:
    def __init__(self, args, log: Log):
        self.args = args
        self.log = log
        self.out = Path(args.out)
        self.tmp = Path(args.tmp) if args.tmp else self.out / "tmp"
        self.artefacts: List[dict] = []
        self.observations: Dict[str, object] = {}
        self.input_facts: Dict[str, object] = {}
        self.device: Optional[str] = None     # profile key: hy310 / l018 / None (unknown)
        self.device_fixed = False             # True: recognised by the image fingerprint (sha256), not revisable
        self.detection: Dict[str, object] = {"ueber": None, "merkmale": [], "hinweise": []}
        self.features: Dict[str, object] = {}  # what the input tells about itself (hashes, version strings, sizes)
        self.reference_device: Optional[str] = None  # which profile was compared against (unknown: the closest)
        self.old_device: Optional[str] = None  # device of a manifest already lying in <out>
        self.out_locked = False               # True: <out> belongs to another device -- write nothing into it
        self.not_extracted: List[str] = []    # what could not be extracted
        self.deviations: List[str] = []       # differences from the stock of the reference device (unknown: „hier drohen Probleme")
        self.package: Optional[SunxiPackage] = None
        self.packages: List[SunxiPackage] = []
        self.super_source: Optional[Source] = None
        self.vendor_source: Optional[Source] = None
        self.vendor: Optional[Ext4Base] = None
        self.open_sources: List[FileSource] = []
        self.mips_sources: List[tuple] = []    # FAT16 images with mips/ (bootloader_b/_a, boot-resource.fex)
        self.mips: Dict[str, object] = {}      # findings for the manifest (project ids, sources, what was not taken)

    # ---- Inputs ---------------------------------------------------------------------------------

    def open(self, path: str) -> FileSource:
        p = Path(path)
        if not p.is_file():
            raise Abort(f"Eingang nicht gefunden: {path}")
        q = FileSource(p)
        self.open_sources.append(q)
        return q

    def fingerprint(self, q: FileSource, role: str):
        self.log.heading(f"Fingerabdruck {role}: {q.path} ({q.size} B)")
        if self.args.no_hash:
            self.log.info("sha256 übersprungen (--no-hash) — Gerät wird nur inhaltlich erkannt")
            h = None
        else:
            h = sha256_file(q.path, log=self.log)
            self.log.info(f"sha256 {h}")
        self.input_facts.update({"pfad": str(q.path), "groesse": q.size, "sha256": h, "rolle": role})
        known = KNOWN_IMAGES.get(h) if h else None
        if known:
            self.input_facts["bekannt_als"] = known[1]
            self.log.info(f"BEKANNT: {known[1]}")
            self.set_device(known[0], "sha256", fix=True)
        else:
            self.input_facts["bekannt_als"] = None
            self.log.info("Image-Fingerabdruck unbekannt — Gerät wird inhaltlich bestimmt (Paket-Hashes, U-Boot/ARISC-Kennung, "
                          "Vendor-Fingerprint); passt kein Profil, bleibt das Image unbekannt (Best-Effort, Exit 1)")

    def input_imagewty(self, q: FileSource):
        self.input_facts["typ"] = "IMAGEWTY"
        self.log.heading("IMAGEWTY-Container")
        img = Imagewty(q, self.log)
        self.input_facts["imagewty"] = {"header_version": img.header_version, "num_files": img.num_files,
                                        "dateien": {n: {"maintype": e["maintype"], "subtype": e["subtype"], "offset": e["offset"],
                                                        "original": e["original"], "stored": e["stored"]}
                                                    for n, e in img.entries.items()}}
        bp = img.file("boot_package.fex")
        if bp is None:
            self.log.warn("boot_package.fex fehlt im Image — kein scp.bin aus diesem Eingang")
        else:
            self.package_from_source(bp, "boot_package.fex im Image")
        # toc1.fex is only an 8-byte placeholder in both images
        t1 = img.file("toc1.fex")
        if t1 is not None:
            self.log.info(f"toc1.fex: {t1.size} B ({'Platzhalter' if t1.size < 1024 else 'echtes TOC1?'})")
        br = img.file(MIPS_FEX)
        if br is None:
            self.log.warn(f"{MIPS_FEX} fehlt im Image — keine MIPS-/Display-Artefakte aus diesem Eingang")
        else:
            # boot-resource.fex is exactly what the flasher writes to bootloader_a and bootloader_b
            # (sys_partition.fex: downloadfile="boot-resource.fex" for both).
            self.mips_source(br, f"{MIPS_FEX} im Image (= bootloader_a und bootloader_b)",
                             ("bootloader_b", "bootloader_a"))
        sup = img.file("super.fex")
        if sup is None:
            self.log.warn("super.fex fehlt im Image — kein EDID/MSP/PQ aus diesem Eingang")
        else:
            self.super_from_source(sup)
        # Side findings for the report
        for n in ("sys_partition.fex", "sunxi_version.fex"):
            d = img.file(n)
            if d is not None and d.size < 65536:
                self.observations[n] = d.read(0, d.size).decode("utf-8", "replace")
        sv = (self.observations.get("sunxi_version.fex") or "").strip()
        if sv:
            self.features["sunxi_version"] = sv
            self.log.info(f"sunxi_version.fex: {sv}")
            self.detect_device("sunxi_version.fex")

    def input_emmc(self, q: FileSource):
        self.input_facts["typ"] = "eMMC-Dump"
        self.log.heading("Roher eMMC-Dump")
        gpt = Gpt(q, self.log)
        self.input_facts["gpt"] = {n: {"start_lba": s, "sektoren": c} for n, (s, c) in gpt.parts.items()}
        for lba in (16, 256):
            b = q.read(lba * SECTOR, 32)
            if b[4:12] == b"eGON.BT0":
                self.log.info(f"LBA {lba}: eGON.BT0 (boot0/SPL) — Länge {struct.unpack_from('<I', b, 16)[0]} B")
            else:
                self.log.info(f"LBA {lba}: kein eGON.BT0 ({hexdump_short(b, 12)})")
        # TOC1 at the known LBAs and by search
        candidates = []
        for lba in (24576, 32800):
            off = lba * SECTOR
            if off + 0x40 <= q.size and q.read(off, 13) == SunxiPackage.NAME:
                candidates.append((off, f"LBA {lba}"))
        self.log.info("Suche nach weiteren 'sunxi-package'-Köpfen im Dump …")
        for off in find_sunxi_packages(q, self.log):
            if all(off != k[0] for k in candidates):
                candidates.append((off, f"Suche @{off:#x} (LBA {off // SECTOR})"))
        if not candidates:
            self.log.warn("kein sunxi-package im Dump — kein scp.bin aus diesem Eingang")
        for off, where in candidates:
            try:
                self.package_from_source(q, f"Dump {where}", off)
            except Abort as e:
                self.log.warn(str(e))
        for n in MIPS_PART_NAMES:
            p = gpt.partition(q, n)
            if p is None:
                s = gpt.parts.get(n)
                self.log.warn(f"{n} liegt {'bei LBA %d+%d, ' % s if s else ''}nicht (vollständig) im Dump")
                continue
            if Fat.is_fat(p):
                self.mips_source(p, f"Dump: Partition {n} (LBA {gpt.parts[n][0]}, {gpt.parts[n][1]} Sektoren)", (n,))
            else:
                self.log.warn(f"{n}: kein FAT-Bootsektor ({hexdump_short(p.read(0, 8))}) — MIPS-Dateien nicht lesbar")
        if "private" in gpt.parts:
            s0, c0 = gpt.parts["private"]
            self.log.info(f"private@{s0}+{c0}: Secure Storage (HDCP-Keys laut doku/68) — wird nicht gelesen")
            self.observations["hdcp_hinweise_gpt"] = [f"private@{s0}+{c0} (Secure Storage, nicht gelesen)"]
        sup = gpt.partition(q, "super")
        if sup is None:
            s = gpt.parts.get("super")
            self.log.warn(f"'super' liegt {'bei LBA %d+%d, ' % s if s else ''}nicht (vollständig) im Dump — "
                          f"kein EDID/MSP/PQ aus diesem Eingang")
            self.not_extracted.append("super nicht im Dump (EDID, MSP-Patch, PQ)")
        else:
            self.super_from_source(sup)

    def input_parts(self):
        self.input_facts["typ"] = "Einzelteile"
        self.log.heading("Einzelne Partitions-/.fex-Dateien")
        parts = dict(self.args.part or [])
        if self.args.fex_dir:
            d = Path(self.args.fex_dir)
            for n, k in (("boot_package.fex", "boot_package"), ("super.fex", "super"), (MIPS_FEX, "boot-resource")):
                if (d / n).is_file():
                    parts.setdefault(k, str(d / n))
                else:
                    self.log.warn(f"{d / n} fehlt")
        if not parts:
            raise Abort("keine Eingänge (--part … / --fex-dir …)")
        self.input_facts["teile"] = {}
        for k, v in parts.items():
            pv = Path(v)
            if not pv.is_file():
                raise Abort(f"--part {k}: Datei fehlt: {v}")
            h = None if self.args.no_hash else sha256_file(pv)
            self.input_facts["teile"][k] = {"pfad": str(pv), "groesse": pv.stat().st_size, "sha256": h}
            self.log.info(f"{k}: {pv} ({pv.stat().st_size} B) sha256 {h}")
        for k in ("boot_package", "bootloader_a", "bootloader_b", "bootloader", "boot-resource", "boot_resource",
                  "mips", "toc1"):
            if k not in parts:
                continue
            q = self.open(parts[k])
            self.log.info(f"{k}: {q.path} ({q.size} B)")
            if k in MIPS_PART_KEYS and Fat.is_fat(q):
                # bootloader_a/_b and boot-resource.fex are FAT16 with mips/ -- no sunxi-package in them.
                # A named slot serves that slot only; boot-resource.fex/bootloader/mips serve both.
                self.mips_source(q, f"{k} ({q.path.name})",
                                 (k,) if k in MIPS_PART_NAMES else ("bootloader_b", "bootloader_a"))
                continue
            offs = [0] if q.read(0, 13) == SunxiPackage.NAME else find_sunxi_packages(q, self.log)
            if not offs:
                self.log.warn(f"{k}: kein sunxi-package gefunden")
            for off in offs:
                # known bug, stage 2 C: this also swallows the Abort of check_output_dir(), so with
                # --part a foreign <out> only produces a warning and exit 1 instead of exit 2.
                try:
                    self.package_from_source(q, f"{k} ({q.path.name}) @{off:#x}", off)
                except Abort as e:
                    self.log.warn(str(e))
        if "super" in parts:
            q = self.open(parts["super"])
            self.log.info(f"super: {q.path} ({q.size} B)")
            self.super_from_source(q)
        elif "vendor" in parts:
            q = self.open(parts["vendor"])
            self.log.info(f"vendor: {q.path} ({q.size} B)")
            vq: Source = SparseSource(q, self.log) if SparseSource.is_sparse(q) else q
            self.vendor_source = vq
        if "emmc" in parts:
            q = self.open(parts["emmc"])
            if not Gpt.is_gpt(q):
                raise Abort("emmc: keine GPT bei LBA 1")
            self.input_emmc(q)

    # ---- sunxi-package / scp --------------------------------------------------------------------

    def package_from_source(self, q: Source, origin: str, off: int = 0):
        if q.read(off, 13) != SunxiPackage.NAME:
            # boot_package.fex can also be a container with a header -- search
            offs = find_sunxi_packages(q, self.log, max_bytes=min(q.size, 64 << 20))
            if not offs:
                raise Abort(f"{origin}: kein sunxi-package")
            off = offs[0]
        pk = SunxiPackage(q, off, self.log, origin)
        self.packages.append(pk)
        if self.package is None:
            self.package = pk
            hashes = {}
            for n, (o, l) in pk.items.items():
                hashes[n] = {"offset": o, "len": l, "sha256": sha256_bytes(q.read(off + o, l))}
            self.input_facts["sunxi_package"] = {"herkunft": origin, "offset": off, "items": hashes, "valid_len": pk.valid_len,
                                                 "pruefsumme_ok": pk.checksum_ok, "probleme": pk.problems}
            # Features for recognition and comparison
            self.features["paket_items"] = {n: l for n, (o, l) in pk.items.items()}
            self.features["paket_item_sha256"] = {n: h["sha256"] for n, h in hashes.items()}
            for item, key in (("scp", "scp_sha256"), ("u-boot", "uboot_sha256"), ("dtb", "dtb_sha256")):
                if item in hashes:
                    self.features[key] = hashes[item]["sha256"]
            ub = pk.item("u-boot")
            if ub:
                k = uboot_version_string(ub)
                if k:
                    self.features["uboot_version"] = k
                    self.log.info(f"U-Boot-Kennung: {k}")
            dtb = pk.item("dtb")
            if dtb:
                w = fdt_root(dtb)
                if w:
                    self.features["dtb_compatible"] = w.get("compatible", "")
                    self.features["dtb_model"] = w.get("model", "")
                    self.log.info(f"dtb-Wurzel: model '{w.get('model', '')}', compatible '{w.get('compatible', '')}'")
            self.detect_device(origin)

    def extract_scp(self):
        self.log.heading("h713-arisc.bin (= scp aus dem sunxi-package)")
        if not self.packages:
            self.log.warn("kein sunxi-package — h713-arisc.bin nicht extrahiert")
            self.not_extracted.append("h713-arisc.bin (kein sunxi-package im Eingang)")
            return
        seen: Dict[str, List[str]] = {}
        first = None
        for pk in self.packages:
            scp = pk.item("scp")
            if scp is None:
                self.log.warn(f"{pk.origin}: kein 'scp'-Item (Items: {', '.join(pk.items)})")
                continue
            seen.setdefault(sha256_bytes(scp), []).append(pk.origin)
            if first is None:
                first = (pk, scp)
        if first is None:
            self.not_extracted.append("h713-arisc.bin (kein scp-Item)")
            return
        if len(seen) > 1:
            self.log.warn("die gefundenen scp-Blobs unterscheiden sich: " +
                          "; ".join(f"{h[:12]}… aus {', '.join(w)}" for h, w in seen.items()))
        else:
            h, where = next(iter(seen.items()))
            self.log.info(f"scp identisch in: {', '.join(where)}")
        pk, scp = first
        findings = check_scp(scp, self.log)
        for b in findings:
            self.log.info("Struktur: " + b)
            if b.startswith("Versionsstring: '"):
                self.features["arisc_version"] = b[len("Versionsstring: '"):].rstrip("'")
        if "arisc_version" in self.features:
            self.detect_device("ARISC-Versionsstring")
        checks = ["sunxi-package Prüfsumme " + ("ok" if pk.checksum_ok else "FALSCH")] + [
            "Item-Tabelle ok" if not pk.problems else "Paketprobleme: " + "; ".join(pk.problems)] + findings
        error = (not pk.checksum_ok) or bool(pk.problems) or any("kein l.j" in b or "nicht 'CPUs'" in b or "leer" in b for b in findings)
        self.store("lib/firmware/h713-arisc.bin", scp,
                   origin=f"{pk.origin}: Item 'scp' @{pk.off + pk.items['scp'][0]:#x}, {len(scp)} B "
                          f"(Paket: {', '.join(f'{n}={l}' for n, (o, l) in pk.items.items())})",
                   checks=checks, error=error)

    # ---- super / vendor -------------------------------------------------------------------------

    def super_from_source(self, q: Source):
        self.log.heading("super → LP-Metadaten → vendor")
        if SparseSource.is_sparse(q):
            sq = SparseSource(q, self.log)
            self.log.info(sq.description)
            self.input_facts["super_sparse"] = sq.description
            q = sq
        else:
            self.log.info(f"{q.name}: kein Sparse-Kopf, wird als rohes Abbild gelesen")
        self.super_source = q
        lp = LpSuper(q, self.log)
        self.input_facts["lp"] = {"version": lp.version, "lage": lp.location,
                                  "partitionen": {n: {"size": p["size"], "gruppe": p["gruppe"],
                                                      "extents": [list(e) for e in p["extents"]]} for n, p in lp.parts.items()}}
        for n in ("vendor_a", "vendor"):
            vq = lp.partition(n, self.log)
            if vq is not None:
                self.log.info(f"vendor-Partition: {n} ({vq.size} B)")
                self.input_facts["vendor_partition"] = n
                self.vendor_source = vq
                self.features["vendor_size"] = vq.size
                self.detect_device("LP-Partition " + n)
                return
        self.log.warn("keine Partition vendor_a/vendor in den LP-Metadaten: " + ", ".join(lp.parts))
        self.not_extracted.append("vendor-Partition nicht gefunden (EDID, MSP-Patch, PQ)")

    def open_vendor(self) -> bool:
        if self.vendor is not None:
            return True
        if self.vendor_source is None:
            return False
        self.log.heading("vendor-Dateisystem")
        self.tmp.mkdir(parents=True, exist_ok=True)
        reader = Ext4Debugfs if getattr(self.args, "use_debugfs", False) else Ext4
        self.vendor = reader(self.vendor_source, self.tmp, "vendor", self.log)
        self.input_facts["vendor_fs"] = self.vendor.description
        # Version string of the vendor firmware (build.prop) -- helps with unknown images
        if self.vendor.exists("/build.prop"):
            props = {}
            for line in self.vendor.read("/build.prop", self.tmp).decode("utf-8", "replace").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k in ("ro.vendor.build.fingerprint", "ro.vendor.build.date", "ro.product.vendor.model",
                             "ro.product.vendor.name", "ro.product.vendor.brand"):
                        props[k] = v.strip()
            self.input_facts["vendor_build"] = props
            for k, v in props.items():
                self.log.info(f"build.prop {k} = {v}")
            fp = props.get("ro.vendor.build.fingerprint", "")
            if fp:
                self.features["build_fingerprint"] = fp
                self.detect_device("vendor build.prop")
        return True

    def extract_edid(self):
        self.log.heading("hy310-edid.bin (= HDMI_EDID_14.bin + HDMI_EDID_20.bin)")
        if not self.open_vendor():
            self.log.warn("keine vendor-Partition — hy310-edid.bin nicht extrahiert")
            self.not_extracted.append("hy310-edid.bin (keine vendor-Partition)")
            return
        parts, checks, error = [], [], False
        for pf in (EDID_14, EDID_20):
            entry = self.vendor.exists(pf)
            if not entry:
                self.log.warn(f"{pf} fehlt in vendor")
                error = True
                continue
            b = self.vendor.read(pf, self.tmp)
            problems = check_edid_block(b, Path(pf).name)
            if len(b) == 256:
                checks.append(f"{Path(pf).name}: {len(b)} B, Hersteller {edid_vendor(b)}, Name '{edid_name(b)}', "
                              f"Byte 168 {b[168]:#04x}" + (", Blockprüfsummen 0" if not problems else ""))
            for p in problems:
                self.log.warn(p)
                checks.append(p)
            error = error or bool(problems)
            parts.append(b)
        if len(parts) != 2:
            self.not_extracted.append("hy310-edid.bin (EDID-Dateien fehlen)")
            return
        edid = parts[0] + parts[1]
        if len(edid) != 512:
            checks.append(f"Gesamtlänge {len(edid)} statt 512")
            error = True
        self.store("lib/firmware/hy310-edid.bin", edid,
                   origin=f"vendor:{EDID_14} ({len(parts[0])} B) + vendor:{EDID_20} ({len(parts[1])} B), unverändert aneinandergehängt",
                   checks=checks, error=error)

    def extract_msp(self):
        self.log.heading("h713/msp-patch.bin (= Symbol patch_msp aus libmspsound.so)")
        if not self.open_vendor():
            self.log.warn("keine vendor-Partition — msp-patch.bin nicht extrahiert")
            self.not_extracted.append("msp-patch.bin (keine vendor-Partition)")
            return
        lib = None
        for k in MSP_LIB_CANDIDATES:
            if self.vendor.exists(k):
                lib = k
                break
        if lib is None:
            for pf, e in self.vendor.walk("/lib", 2):
                if e["name"] == "libmspsound.so":
                    lib = pf
                    break
        if lib is None:
            self.log.warn("libmspsound.so nicht in vendor gefunden — msp-patch.bin nicht extrahiert")
            self.not_extracted.append("msp-patch.bin (libmspsound.so fehlt)")
            return
        data = self.vendor.read(lib, self.tmp)
        self.log.info(f"{lib}: {len(data)} B, sha256 {sha256_bytes(data)}")
        checks = [f"libmspsound.so sha256 {sha256_bytes(data)}"]
        self.features["libmspsound_sha256"] = sha256_bytes(data)
        sym = elf_symbol(data, "patch_msp")
        if sym is None:
            self.log.warn("Symbol patch_msp nicht in der Symboltabelle — Rückfall auf MSPM-Kettensuche")
            chain = find_mspm_chain(data)
            if chain is None:
                self.not_extracted.append("msp-patch.bin (weder Symbol noch MSPM-Kette)")
                return
            off, size = chain[0], chain[1] - chain[0]
            checks.append(f"Herkunft per MSPM-Suche @{off:#x}, {size} B (kein Symbol!)")
            error = True
        else:
            off, size, sect = sym
            checks.append(f"Symbol patch_msp: Dateioffset {off:#x}, st_size {size}, Sektion {sect}")
            error = False
        blob = data[off:off + size]
        blocks, problems = parse_mspm(blob)
        pairs = sum(b["paare"] for b in blocks)
        checks.append(f"MSPM: {len(blocks)} Blöcke, {pairs} Paare, Ziele " +
                      "/".join(f"{b['ziel']}:{b['laenge']}" for b in blocks))
        for p in problems:
            self.log.warn("MSPM: " + p)
            checks.append("MSPM: " + p)
        if len(blob) % 4:
            checks.append(f"Länge {len(blob)} nicht durch 4 teilbar (Treiber verlangt das)")
        error = error or bool(problems) or (len(blob) % 4 != 0)
        self.store("lib/firmware/h713/msp-patch.bin", blob,
                   origin=f"vendor:{lib}, Symbol patch_msp (Dateioffset {off:#x}, {size} B)",
                   checks=checks, error=error)

    def extract_pq(self):
        self.log.heading("PQ-Quellen (die Dateien, die h713-pq liest)")
        if not self.open_vendor():
            self.log.warn("keine vendor-Partition — PQ nicht extrahiert")
            self.not_extracted.append("PQ-Dateien (keine vendor-Partition)")
            return
        present = {e["name"]: e for e in self.vendor.ls(TVCONFIG)}
        self.observations["tvconfig_inhalt"] = sorted(f"{n} ({e['size']} B)" for n, e in present.items())
        for n in PQ_FILES:
            if n not in present:
                self.log.warn(f"{TVCONFIG}/{n} fehlt")
                self.not_extracted.append(f"pq/{n} (fehlt in vendor)")
                continue
            b = self.vendor.read(f"{TVCONFIG}/{n}", self.tmp)
            problems = check_pq(n, b, self.tmp)
            for p in problems:
                self.log.warn(f"{n}: {p}")
            self.store(f"pq/{n}", b, origin=f"vendor:{TVCONFIG}/{n}",
                       checks=(["Pflichtschlüssel ok"] if not problems else problems), error=bool(problems))

    def extract_wlan(self):
        """Take over the AIC8800D80 firmware from vendor:/etc/firmware/aic8800d80/.

        Copied unchanged, file by file -- nothing is assembled and nothing is
        renamed. If the directory is missing that is NO error: not every H713 device has
        this radio chip. Reference values exist so far only for the hy310 profile; on a
        device without a reference the files pass through as "not referenced", without
        tipping the exit code (grade() skips artefacts without a reference entry).
        """
        self.log.heading(f"WLAN-Firmware (= vendor:{AIC_FW_DIR}/)")
        if not self.open_vendor():
            self.log.warn("keine vendor-Partition — WLAN-Firmware nicht extrahiert")
            self.not_extracted.append("WLAN-Firmware (keine vendor-Partition)")
            return
        if not self.vendor.exists(AIC_FW_DIR):
            self.log.info(f"{AIC_FW_DIR} nicht vorhanden — dieses Geraet hat keine AIC8800-Firmware")
            self.observations["aic8800_firmware"] = "nicht vorhanden"
            return
        files = [e for e in self.vendor.ls(AIC_FW_DIR) if e.get("typ") != "d"]
        if not files:
            self.log.warn(f"{AIC_FW_DIR} ist leer")
            self.not_extracted.append("WLAN-Firmware (Verzeichnis leer)")
            self.observations["aic8800_firmware"] = "Verzeichnis leer"
            return
        self.observations["aic8800_firmware"] = sorted(
            f"{e['name']} ({e['size']} B)" for e in files)
        for e in sorted(files, key=lambda x: x["name"]):
            b = self.vendor.read(f"{AIC_FW_DIR}/{e['name']}", self.tmp)
            problems = []
            if len(b) != e["size"]:
                problems.append(f"gelesen {len(b)} B, Verzeichniseintrag sagt {e['size']} B")
            if not b:
                problems.append("leere Datei")
            self.store(f"{AIC_FW_TARGET}/{e['name']}", b,
                       origin=f"vendor:{AIC_FW_DIR}/{e['name']}, unveraendert uebernommen",
                       checks=problems or ["unveraendert uebernommen"],
                       error=bool(problems))

    # ---- MIPS/display artefacts (plan 108 §1/§4.2/§4.5) -----------------------------------------

    def mips_source(self, q: Source, origin: str, keys=("bootloader_b", "bootloader_a")):
        """Remember a FAT image with mips/. `keys` are the profile source keys it serves."""
        self.mips_sources.append((origin, q, tuple(keys)))
        self.log.info(f"MIPS-Quelle gemerkt: {origin} ({q.size} B)")

    def _read_mips(self, origin: str, q: Source) -> Optional[dict]:
        """Open a FAT image and take exactly the files out of it that our chain uses."""
        try:
            fs = Fat(q, self.log, origin)
        except Abort as e:
            self.log.warn(str(e))
            return None
        entries = fs.directory(MIPS_SOURCE_DIR)
        if entries is None:
            self.log.warn(f"{origin}: kein Verzeichnis '{MIPS_SOURCE_DIR}/' im {fs.type} "
                          f"(Wurzel: {', '.join(sorted(e['name'] for e in fs.entries(0))) or 'leer'})")
            return None
        files: Dict[str, bytes] = {}
        problems: List[str] = list(fs.problems)
        leftover: List[str] = []
        short_names: Dict[str, str] = {}
        for e in sorted(entries, key=lambda x: x["name"]):
            if e["verzeichnis"]:
                leftover.append(f"{MIPS_SOURCE_DIR}/{e['name']}/ (Verzeichnis)")
                continue
            wanted = e["name"] in MIPS_FILES or bool(MIPS_PROJECTID.match(e["name"]))
            if not wanted:
                leftover.append(f"{MIPS_SOURCE_DIR}/{e['name']} ({e['groesse']} B)")
                continue
            try:
                files[e["name"]] = fs.read(e)
            except Abort as ex:
                problems.append(str(ex))
                self.log.warn(str(ex))
                continue
            short_names[e["name"]] = e["kurz"]
            if not e["lang"]:
                problems.append(f"{e['name']}: kein Langname im Verzeichnis — 8.3-Name genommen")
        # What else lies in the partition (plan 108 §1: BOOTLOGO, fonts, BAT/, WAVEFILE/ -- not our chain)
        others = []
        for e in sorted(fs.entries(0), key=lambda x: x["name"]):
            if e["name"].lower() == MIPS_SOURCE_DIR:
                continue
            others.append(f"{e['name']}{'/' if e['verzeichnis'] else ''} ({'Verzeichnis' if e['verzeichnis'] else str(e['groesse']) + ' B'})")
        return {"herkunft": origin, "fs": fs.description, "typ": fs.type, "art": "fat", "dateien": files,
                "kurznamen": short_names, "probleme": problems, "uebrig": leftover, "sonst": others}

    def _read_mips_vendor(self) -> Optional[dict]:
        """The second source (stage 2 C-D): the vendor copy of mips/ inside super (lpsuper + ext4).

        Same read set as _read_mips(); the vendor filesystem has no 8.3 names, "kurznamen" stays empty."""
        try:
            if self.vendor is None and not self.open_vendor():
                self.log.info(f"{VENDOR_MIPS_SOURCE}: no vendor partition in this input")
                return None
        except Abort as e:
            self.log.warn(f"{VENDOR_MIPS_SOURCE}: vendor filesystem not readable ({e})")
            return None
        if not self.vendor.exists(VENDOR_MIPS_DIR):
            self.log.info(f"{VENDOR_MIPS_SOURCE}: not present in the vendor partition")
            return None
        files, leftover, problems = read_vendor_mips(self.vendor, VENDOR_MIPS_DIR, self.tmp)
        for p in problems:
            self.log.warn(f"{VENDOR_MIPS_SOURCE}: {p}")
        self.log.info(f"{VENDOR_MIPS_SOURCE}: {len(files)} file(s) for our chain, {len(leftover)} more there")
        return {"herkunft": VENDOR_MIPS_SOURCE + "/", "fs": self.vendor.description, "typ": "ext4",
                "art": "vendor", "dateien": files, "kurznamen": {}, "probleme": problems,
                "uebrig": leftover, "sonst": []}

    def mips_source_order(self) -> tuple:
        """The source keys of the identified profile, or the fallback order of api-stufe2.md."""
        profile = PROFILES.get(self.device) if self.device else None
        order = ((profile or {}).get("mips") or {}).get("sources")
        return tuple(order) if order else FALLBACK_MIPS_SOURCES

    def mips_read_sets(self) -> tuple:
        """Read every MIPS source, in the order of the profile. Returns (read sets, source notes).

        One note per profile source key: what it was and how many files it held. `role` is filled in
        here only where nothing was read; extract_mips() marks the rest used/cross-check."""
        order = self.mips_source_order()
        self.log.info("MIPS sources in profile order: " + ", ".join(order))
        sets, notes, taken = [], [], {}

        def take(key, origin, reader):
            if origin in taken:      # bootloader_a and bootloader_b are one boot-resource.fex in an image
                notes.append({"source": key, "origin": origin, "files": None,
                              "role": f"same image as {taken[origin]}"})
                return
            taken[origin] = key
            r = reader()
            notes.append({"source": key, "origin": origin, "files": len(r["dateien"]) if r else None,
                          "role": None if r else "not present"})
            if r:
                sets.append(r)

        for key in order:
            if key == VENDOR_MIPS_SOURCE:
                take(key, VENDOR_MIPS_SOURCE + "/", self._read_mips_vendor)
                continue
            for origin, q, keys in self.mips_sources:
                if key in keys:
                    take(key, origin, lambda o=origin, s=q: self._read_mips(o, s))
        # A source the input offers but the profile does not name keeps its old place: at the end.
        for origin, q, keys in self.mips_sources:
            if origin not in taken:
                take(keys[0] if keys else "?", origin, lambda o=origin, s=q: self._read_mips(o, s))
        return sets, notes

    def declared_project_id(self) -> dict:
        """panel_config.ini in the vendor filesystem: it is reported, but not used (plan 108 §4.5 thirdly)."""
        try:
            if self.vendor is None and not self.open_vendor():
                return {"id": None, "quelle": None, "hinweis": "keine vendor-Partition im Eingang — nicht ermittelbar"}
        except Abort as e:
            return {"id": None, "quelle": None, "hinweis": f"vendor-Dateisystem nicht lesbar ({e})"}
        for pf in PANEL_CONFIG_CANDIDATES:
            if not self.vendor.exists(pf):
                continue
            text = self.vendor.read(pf, self.tmp).decode("utf-8", "replace")
            pid = panel_config_id(text)
            return {"id": pid, "quelle": f"vendor:{pf}",
                    "hinweis": None if pid is not None else "ProjectID-Zeile nicht gefunden"}
        return {"id": None, "quelle": None,
                "hinweis": "panel_config.ini nicht in vendor gefunden (" + ", ".join(PANEL_CONFIG_CANDIDATES) + ")"}

    def extract_mips(self):
        self.log.heading(f"{MIPS_OUTPUT_DIR}/… (MIPS/display artefacts from the bootloader FAT and the vendor copy)")
        read_sets, source_notes = self.mips_read_sets()
        if not read_sets:
            tried = ", ".join(n["source"] for n in source_notes) or "none"
            self.log.warn(f"no readable {MIPS_SOURCE_DIR}/ in this input (sources tried: {tried}) — "
                          f"{MIPS_OUTPUT_DIR}/* not extracted")
            self.not_extracted.append(f"{MIPS_OUTPUT_DIR}/* (no readable {MIPS_SOURCE_DIR}/; tried: {tried})")
            return
        # The first source that has the whole set wins; failing that the first that has display.bin.
        main_set = ([r for r in read_sets if all(n in r["dateien"] for n in MIPS_FILES)] or
                    [r for r in read_sets if "display.bin" in r["dateien"]] or read_sets)[0]
        for note in source_notes:
            if note["role"] is None:
                note["role"] = "used" if note["origin"] == main_set["herkunft"] else "cross-check"
        # Every other source is cross-checked file by file; every difference is reported.
        comparison: List[str] = []
        for w in [r for r in read_sets if r is not main_set]:
            a, b = main_set["dateien"], w["dateien"]
            difference = ([f"only in {main_set['herkunft']}: {n}" for n in sorted(set(a) - set(b))] +
                          [f"only in {w['herkunft']}: {n}" for n in sorted(set(b) - set(a))] +
                          [f"{n} differs: {len(a[n])} B sha256 {sha256_bytes(a[n])[:12]}… against "
                           f"{len(b[n])} B sha256 {sha256_bytes(b[n])[:12]}…"
                           for n in sorted(set(a) & set(b)) if a[n] != b[n]])
            if difference:
                comparison.append(f"{w['herkunft']} differs from {main_set['herkunft']}: " + "; ".join(difference))
                self.log.warn(comparison[-1])
            else:
                comparison.append(f"{w['herkunft']} is byte-identical to {main_set['herkunft']} ({len(b)} files)")
                self.log.info(comparison[-1])
        files = main_set["dateien"]
        # database.TSE is the only MIPS file that tells HY310 and L018 apart (S42 §9) -- with it even a
        # bare bootloader partition can be assigned to a device.
        if "database.TSE" in files:
            self.features["mips_database_sha256"] = sha256_bytes(files["database.TSE"])
            self.detect_device("mips/database.TSE")
        self.log.info(f"Quelle: {main_set['herkunft']} — {main_set['fs']}")
        self.log.info(f"mips/: {len(files)} Dateien für unsere Kette, {len(main_set['uebrig'])} weitere darin")
        for n, k in sorted(main_set["kurznamen"].items()):
            if k.lower() != n.lower():
                self.log.info(f"  Langname '{n}' (8.3 wäre '{k}')")

        # ---- (c) list of all ProjectID files (needed for the revision row below) --------------------
        found_ids: List[str] = []
        for n in sorted(files):
            m = MIPS_PROJECTID.match(n)
            if m:
                found_ids.append(f"0x{int(m.group(1), 16):04x}")

        # ---- (b) the used project id: sha256 of the display.bin through h713_mips_fw_revs[] --------
        rev = None
        revision: Optional[dict] = None
        db = files.get("display.bin")
        display_checks: List[str] = []
        display_error = False
        if db is None:
            self.log.warn("display.bin fehlt in mips/ — die benutzte Projekt-ID ist damit nicht bestimmbar")
        else:
            # Stage 2 C-D: profiles.FIRMWARE_REVISIONS, not only the rows h713_mips_fw_revs[] declares.
            rev = firmware_revision_of(db)
            if rev:
                revision = {"name": rev["board"], "size": rev["size"], "sha256": rev["sha256"],
                            "hdcp_wait_va": _va(rev["hdcp_wait_va"]), "project_ids_seen": found_ids,
                            "known": True, "hdcp_wait_va_source": "profiles.FIRMWARE_REVISIONS"}
            if rev and rev["project_id"] is None:
                # Measured, but declared by no row of h713_mips_fw_revs[]: no project id, no panel --
                # what it does carry is the HDCP wait site (api-stufe2.md, "Extractor").
                display_checks.append(f"FIRMWARE_REVISIONS: {rev['board']}, {rev['size']} B, HDCP wait site "
                                      f"{_va(rev['hdcp_wait_va']) or 'unknown'} — no row in h713_mips_fw_revs[], "
                                      f"so no project id comes from it")
                self.log.info(f"display.bin: known revision '{rev['board']}' ({rev['size']} B, HDCP wait site "
                              f"{_va(rev['hdcp_wait_va']) or 'unknown'}) — h713_mips_fw_revs[] does not declare it, "
                              f"so the used project id stays undetermined")
            elif rev:
                display_checks.append(f"h713_mips_fw_revs[]: {rev['board']}, Projekt {rev['project_id']:#04x}, "
                                      f"Panel {rev['panel']}, Sollgröße {rev['size']} B")
                self.log.info(f"display.bin: bekannt — {rev['board']}, Projekt-ID {rev['project_id']:#04x}, Panel {rev['panel']}")
                display_checks.append(f"HDCP wait site of this revision: {_va(rev['hdcp_wait_va']) or 'unknown'}")
                if self.device and DEVICES[self.device]["name"].lower() not in rev["board"].lower():
                    # e.g. L018: the same display.bin as the HY310. The name in h713_mips_fw_revs[] says *from which*
                    # board the revision was read, not which device lies here in the input.
                    note = (f"display.bin dieses {DEVICES[self.device]['name']} ist byteidentisch mit der Revision, die in "
                            f"h713_mips_fw_revs[] unter '{rev['board']}' steht — der Name dort bezeichnet die Herkunft der "
                            f"Revision, nicht das Gerät. Projekt-ID {rev['project_id']:#04x} gilt trotzdem.")
                    display_checks.append(note)
                    self.log.info(note)
                if len(db) != rev["size"]:
                    display_checks.append(f"Größe {len(db)} B statt {rev['size']} B (Revisionstabelle)")
                    self.log.warn(display_checks[-1])
                    display_error = True
                else:
                    display_checks.append(f"Größe {len(db)} B = Revisionstabelle")
            else:
                display_error = True
                display_checks.append(f"sha256 {sha256_bytes(db)} steht NICHT in h713_mips_fw_revs[] — "
                                      f"Projekt-ID unbekannt")
                self.log.warn(f"display.bin ({len(db)} B, sha256 {sha256_bytes(db)}) ist keine der bekannten Revisionen "
                              f"({', '.join(r['board'] + ' ' + hex(r['project_id']) for r in UBOOT_FW_REVS)}) — "
                              f"die benutzte Projekt-ID lässt sich nicht bestimmen")
                self.log.warn("Ausweg: alle ProjectID-Dateien liegen in der Ausgabe; die richtige zur Laufzeit wählen "
                              "(setenv h713_project 0x…; saveenv), Plan 108 §4.5 drittens")
                # Stage 2 C-D: an unknown revision gets its HDCP wait site searched (A5's rule), and the
                # report prints the complete row a profile would need.
                found = hdcpsite.search(db)
                revision = {"name": "unknown", "size": len(db), "sha256": sha256_bytes(db),
                            "hdcp_wait_va": _va(found["hdcp_wait_va"]) or found["status"],
                            "project_ids_seen": found_ids, "known": False,
                            "hdcp_wait_va_source": f"searched by h713.hdcpsite (base {_va(found['base'])})"}
                self.log.info(f"unknown revision — searching the HDCP wait site over {len(db)} B "
                              f"(base {_va(found['base'])}, {len(found['hits'])} candidate word(s)):")
                for line in found["text"]:
                    self.log.info("  " + line)
                self.log.info("HDCP wait site: " + hdcpsite.describe(found))
                display_checks.append("HDCP wait site (searched): " + hdcpsite.describe(found))

        # ---- (c) the declared id: report it, do not use it ----------------------------------------
        declared = self.declared_project_id()
        if declared["id"] is not None:
            self.log.info(f"deklarierte Projekt-ID: {declared['id']:#04x} ({declared['id']} dezimal) aus {declared['quelle']} — "
                          f"wird gemeldet, nicht benutzt (Plan 108 §4.5)")
        else:
            self.log.info(f"deklarierte Projekt-ID: {declared['hinweis']}")
        used = rev["project_id"] if rev else None
        if used is not None and declared["id"] is not None and used != declared["id"]:
            self.log.warn(f"benutzte Projekt-ID {used:#04x} und deklarierte {declared['id']:#04x} gehen auseinander — "
                          f"benutzt wird {used:#04x} (aus display.bin), Plan 108 §3/§6")
        if used is not None and f"0x{used:04x}" not in found_ids:
            self.log.warn(f"ProjectID_0x{used:04x}.TSE fehlt in mips/, obwohl display.bin genau diese ID verlangt")

        self.mips = {
            "quelle": main_set["herkunft"],
            "dateisystem": main_set["fs"],
            # Stage 2 C-D, English keys for the new facts: the sources tried in profile order, the
            # file-by-file cross-check against the ones not used, and the display.bin revision (its
            # HDCP wait site searched when no row of FIRMWARE_REVISIONS fits).
            "sources": source_notes,
            "cross_check": comparison,
            "revision": revision,
            "projekt_id_benutzt": f"{used:#04x}" if used is not None else None,
            "projekt_id_benutzt_woher": (f"sha256 der display.bin in h713_mips_fw_revs[] -> {rev['board']}, "
                                         f"Panel {rev['panel']}" if rev and rev["project_id"] is not None else
                                         f"undetermined: the revision is '{rev['board']}', which no row of "
                                         f"h713_mips_fw_revs[] declares" if rev else
                                         "unbestimmbar: display.bin steht nicht in h713_mips_fw_revs[]"),
            "projekt_id_deklariert": f"{declared['id']:#04x}" if declared["id"] is not None else None,
            "projekt_id_deklariert_quelle": declared["quelle"],
            "projekt_id_deklariert_hinweis": declared["hinweis"],
            "projekt_id_deklariert_benutzt": False,
            "projekt_id_dateien": found_ids,
            "display_bin_bekannt": bool(rev),
            "revisionstabelle": [f"{r['board']}: {r['project_id']:#04x}, Panel {r['panel']}, {r['size']} B, "
                                 f"sha256 {r['sha256'][:16]}…" for r in UBOOT_FW_REVS],
            "nicht_extrahiert_gleiche_partition": main_set["sonst"] + main_set["uebrig"],
        }
        self.observations["bootloader_partition_rest"] = main_set["sonst"] + main_set["uebrig"]
        if main_set["sonst"] or main_set["uebrig"]:
            self.log.info("in derselben Partition, von unserer Kette ungenutzt (wird nicht kopiert, Plan 108 §1): "
                          + ", ".join(main_set["sonst"] + main_set["uebrig"]))

        # ---- Store --------------------------------------------------------------------------------
        fat = main_set["art"] == "fat"
        for n in sorted(files, key=lambda x: (bool(MIPS_PROJECTID.match(x)), x)):
            d = files[n]
            # The vendor copy has no 8.3 short names -- its own line says where the file came from.
            checks: List[str] = [f"aus {main_set['herkunft']}, {MIPS_SOURCE_DIR}/{n} "
                                 f"(8.3-Kurzname '{main_set['kurznamen'].get(n, '?')}')"] if fat else \
                                [f"from {main_set['herkunft']}{n} ({len(d)} B, vendor copy)"]
            error = False
            if n == "display.bin":
                checks += display_checks
                error = display_error
            elif n == "display_cfg.xml":
                p = check_display_cfg(d)
                checks += p
                error = any("nicht parsebar" in x for x in p)
                if error:
                    self.log.warn(p[0])
            elif n.endswith(".TSE"):
                p, _id = check_tse(n, d)
                checks += p
                error = any("Magic fehlt" in x or "passt nicht zusammen" in x for x in p)
                for x in p:
                    if "Magic fehlt" in x or "passt nicht zusammen" in x:
                        self.log.warn(x)
            for x in main_set["probleme"]:
                if x.startswith(n + ":"):
                    checks.append(x)
            self.store(f"{MIPS_OUTPUT_DIR}/{n}", d,
                       origin=f"{main_set['herkunft']}: {MIPS_SOURCE_DIR}/{n} ({len(d)} B, FAT-Langname)" if fat
                              else f"{main_set['herkunft']}{n} ({len(d)} B, vendor copy inside super)",
                       checks=checks, error=error)
        for n in MIPS_FILES:
            if n not in files:
                self.log.warn(f"{MIPS_SOURCE_DIR}/{n} fehlt in der Quelle")
                self.not_extracted.append(f"{MIPS_OUTPUT_DIR}/{n} (fehlt in {main_set['herkunft']})")
        if not found_ids:
            self.log.warn("keine einzige ProjectID_0x*.TSE in mips/ gefunden")
            self.not_extracted.append(f"{MIPS_OUTPUT_DIR}/ProjectID_0x*.TSE (keine gefunden)")

    def observe(self):
        """Only establish, copy nothing: aic8800 firmware, HDCP hints."""
        self.log.heading("Beobachtungen (nichts davon wird extrahiert)")
        if not self.open_vendor():
            self.log.info("keine vendor-Partition — keine Beobachtungen möglich")
            return
        aic, hdcp, licence = [], [], []
        aic_pattern = re.compile(r"(aic|8800|fmacfw|lmacfw|fw_patch|fw_adid)", re.I)
        hdcp_pattern = re.compile(r"hdcp", re.I)
        for pf, e in self.vendor.walk("/", 6):
            if aic_pattern.search(e["name"]):
                aic.append(f"{pf} ({e['size']} B)")
            if hdcp_pattern.search(e["name"]):
                hdcp.append(f"{pf} ({e['size']} B)")
            if re.search(r"(licen[cs]e|notice|copyright)", e["name"], re.I):
                licence.append(f"{pf} ({e['size']} B)")
        # Module licence strings of the aic8800 drivers (modinfo section) -- pure observation
        modules = []
        for pf, e in self.vendor.walk("/lib/modules", 3):
            if e["name"].startswith("aic") and e["name"].endswith(".ko"):
                d = self.vendor.read(pf, self.tmp)
                infos = sorted(set(m.decode("latin1") for m in re.findall(rb"(?:license|vermagic|version|author)=[^\0]{1,80}", d)))
                modules.append({"pfad": pf, "groesse": e["size"], "modinfo": infos})
        # Licence/origin strings in the aic8800 firmware itself
        fw_strings = {}
        for entry in aic:
            pf = entry.split(" (")[0]
            if "/etc/firmware/" in pf and re.search(r"(fmacfw|lmacfw|fw_patch|fw_adid)", pf):
                d = self.vendor.read(pf, self.tmp)
                hits = sorted(set(m.decode("latin1") for m in re.findall(rb"[ -~]{6,}", d)
                                  if re.search(rb"(?i)(licen[cs]e|copyright|\(c\)|aicsemi|rivierawaves)", m)))[:8]
                if hits:
                    fw_strings[pf] = hits
        # NOTICE.xml.gz of the vendor image: is the AIC firmware in there with a licence?
        notice = None
        if self.vendor.exists("/etc/NOTICE.xml.gz"):
            import gzip
            try:
                x = gzip.decompress(self.vendor.read("/etc/NOTICE.xml.gz", self.tmp)).decode("utf-8", "replace")
                files = re.findall(r"<file-name[^>]*>([^<]*)</file-name>", x)
                aic_entries = [d for d in files if re.search(r"(?i)(aic|8800|fmacfw|lmacfw)", d)]
                notice = {"eintraege": len(files), "aic_eintraege": aic_entries}
            except Exception as e:  # noqa: BLE001
                notice = {"fehler": str(e)}
        self.observations["notice_xml"] = notice
        self.observations["aic8800_dateien"] = sorted(aic)
        self.observations["aic8800_module"] = modules
        self.observations["aic8800_firmware_strings"] = fw_strings
        self.observations["hdcp_hinweise"] = sorted(hdcp)
        self.observations["lizenzdateien"] = sorted(licence)
        if notice is not None:
            self.log.info(f"/etc/NOTICE.xml.gz: {notice.get('eintraege')} Dateieinträge, davon zu aic8800: "
                          f"{len(notice.get('aic_eintraege', []))} — {'keine Lizenzangabe zur AIC-Firmware' if not notice.get('aic_eintraege') else notice['aic_eintraege']}")
        self.log.info(f"aic8800-bezogene Dateien: {len(aic)}")
        for line in sorted(aic):
            self.log.info("  " + line)
        for m in modules:
            self.log.info(f"  Modul {m['pfad']}: " + "; ".join(m["modinfo"]))
        for pf, found in fw_strings.items():
            self.log.info(f"  Strings in {pf}: " + " | ".join(found))
        self.log.info(f"HDCP-Hinweise (Dateinamen, nicht angefasst): {len(hdcp)}")
        for line in sorted(hdcp):
            self.log.info("  " + line)
        self.log.info(f"Lizenz-/Notice-Dateien: {len(licence)}")
        for line in sorted(licence)[:20]:
            self.log.info("  " + line)
        if isinstance(self.vendor, Ext4):
            self.log.info("ext4-Leser: " + self.vendor.stats())
            for pr in self.vendor.problems:
                self.log.warn("ext4: " + pr)

    # ---- Recognise the device, protect the output directory ------------------------------------

    def read_old_manifest(self):
        """If a MANIFEST.json already lies in <out>, remember for which device -- two devices are not mixed."""
        mp = self.out / "MANIFEST.json"
        if not mp.is_file():
            return
        try:
            old = json.loads(mp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            self.log.warn(f"{mp}: vorhandenes Manifest unlesbar ({e}) — wird überschrieben")
            return
        g = old.get("device") or (old.get("image_typ") or "").lower() or None   # image_typ: manifests of version 0.1
        self.old_device = g if g in DEVICES else None
        self.log.info(f"{mp}: vorhandenes Manifest ({old.get('werkzeug', '?')}, {old.get('zeit', '?')}) für Gerät "
                      f"{self.old_device or 'unbekannt/keins'}")

    def check_output_dir(self):
        if self.old_device and self.device and self.old_device != self.device:
            self.out_locked = True
            raise Abort(f"Ausgabeverzeichnis {self.out} enthält schon Ergebnisse für Gerät '{self.old_device}', dieser Eingang "
                        f"ist '{self.device}' — Ergebnisse zweier Geräte werden nicht vermischt. Anderes --out wählen "
                        f"(nichts wurde überschrieben).")

    def set_device(self, gid: Optional[str], via: str, fix: bool = False, features: Optional[List[str]] = None):
        if gid == self.device and not fix:
            return
        self.device = gid
        self.device_fixed = fix
        self.detection = {"ueber": via if gid else None, "merkmale": features or [], "hinweise": self.detection.get("hinweise", [])}
        if gid:
            self.log.info(f"GERÄT: {gid} — {DEVICES[gid]['beschreibung']} (erkannt über {via}"
                          + (": " + ", ".join(features) if features else "") + ")")
        self.check_output_dir()

    def detect_device(self, reason: str):
        """Determine the device from the features collected so far -- only if the image fingerprint gave nothing.
        A profile fits if at least one strong feature matches and none contradicts; if several fit or the parts
        contradict each other (e.g. package from L018, super from HY310), the device stays unknown."""
        if self.device_fixed:
            return
        votes = {}
        for gid, profile in DEVICES.items():
            k = features_of(profile)
            hits = [m for m in ID_FEATURES if m in self.features and feature_matches(m, self.features[m], k[m])]
            against = [m for m in ID_FEATURES if m in self.features and not feature_matches(m, self.features[m], k[m])]
            votes[gid] = (hits, against)
        self.detection["stimmen"] = {g: {"treffer": t, "widerspruch": w} for g, (t, w) in votes.items()}
        fitting = [g for g, (t, w) in votes.items() if any(m in STRONG_FEATURES for m in t) and not w]
        if len(fitting) == 1:
            if fitting[0] == self.device:
                self.detection["merkmale"] = votes[fitting[0]][0]   # write down later confirmations as well
            else:
                self.set_device(fitting[0], "Inhalt", features=votes[fitting[0]][0])
            return
        mixed = [g for g, (t, w) in votes.items() if t and w]
        if mixed:
            seen = self.detection.setdefault("_gesehen", [])
            for g in mixed:
                t, w = votes[g]
                key = f"{g}:{','.join(w)}"
                if key in seen:
                    continue
                seen.append(key)
                note = (f"Merkmale widersprüchlich für {g}: passt bei {', '.join(t)}, nicht bei "
                        f"{', '.join(f'{m}={self.features[m]!r}' for m in w)}")
                self.detection["hinweise"].append(note)
                self.log.warn(note + f" (nach {reason})")
            if self.device is not None:
                self.log.warn(f"Gerät {self.device} wieder zurückgenommen — Eingangsteile passen nicht zu einem Gerät")
                self.set_device(None, reason)
        elif len(fitting) > 1:
            self.log.warn(f"Merkmale passen zu mehreren Profilen ({', '.join(fitting)}) — Gerät bleibt unbekannt")

    def closest_profile(self) -> str:
        """For an unknown image: the profile with the most hits (tie/none: hy310) for the deviation list."""
        best, best_n = "hy310", -1
        for gid, profile in DEVICES.items():
            k = features_of(profile)
            n = sum(1 for m in ID_FEATURES if m in self.features and feature_matches(m, self.features[m], k[m]))
            if n > best_n:
                best, best_n = gid, n
        return best

    def deviations_from(self, gid: str) -> List[str]:
        """Observed features against the target values of a profile -- empty list = stock of this device."""
        e, nm, m, out = DEVICES[gid]["erwartung"], DEVICES[gid]["name"], self.features, []
        if "paket_items" in m:
            for n, expected in e["paket_items"].items():
                if n not in m["paket_items"]:
                    out.append(f"Paket-Item {n} fehlt ({nm} hat es)")
                elif m["paket_items"][n] != expected:
                    out.append(f"Paket-Item {n}: {m['paket_items'][n]} B statt {expected} B ({nm})")
            for n, sh in e["paket_item_sha256"].items():
                actual = m["paket_item_sha256"].get(n)
                if actual and actual != sh:
                    out.append(f"Paket-Item {n}: Inhalt anders als {nm} (sha256 {actual[:16]}…)")
        if "uboot_version" in m and not feature_matches("uboot_version", m["uboot_version"], e["uboot_version"]):
            out.append(f"U-Boot-Kennung '{m['uboot_version']}' statt '{e['uboot_version']} …' ({nm})")
        if "dtb_compatible" in m and e["dtb_compatible"] not in m["dtb_compatible"]:
            out.append(f"dtb compatible '{m['dtb_compatible']}' ohne '{e['dtb_compatible']}' — andere SoC-Familie?")
        if "arisc_version" in m and not feature_matches("arisc_version", m["arisc_version"], e["arisc_version"]):
            out.append(f"ARISC-Versionsstring '{m['arisc_version']}' statt '{e['arisc_version']} …' ({nm})")
        if "vendor_size" in m and m["vendor_size"] != e["vendor_size"]:
            out.append(f"vendor-Partition {m['vendor_size']} B statt {e['vendor_size']} B ({nm})")
        if "libmspsound_sha256" in m and m["libmspsound_sha256"] != e["libmspsound_sha256"]:
            out.append(f"libmspsound.so anders als {nm} (sha256 {m['libmspsound_sha256'][:16]}…) — Patchstrom prüfen")
        if "build_fingerprint" in m and m["build_fingerprint"] != e["build_fingerprint"]:
            out.append(f"Vendor-Fingerprint '{m['build_fingerprint']}' statt '{e['build_fingerprint']}' ({nm})")
        if "mips_database_sha256" in m and m["mips_database_sha256"] != e["mips_database_sha256"]:
            out.append(f"mips/database.TSE anders als {nm} (sha256 {m['mips_database_sha256'][:16]}…) — "
                       f"andere Vendor-Displaydaten")
        if "sunxi_version" in m and m["sunxi_version"] != e["sunxi_version"]:
            out.append(f"sunxi_version {m['sunxi_version']} statt {e['sunxi_version']} ({nm})")
        return out

    def grade(self) -> int:
        """Pin the device down, compare the artefacts against its reference, list deviations, determine the exit code."""
        self.log.heading("Gerät und Referenzabgleich")
        if self.device:
            self.reference_device = self.device
            if self.device_fixed:   # recognised by sha256: which content features confirm that, for the manifest
                k = features_of(DEVICES[self.device])
                self.detection["merkmale"] = [m for m in ID_FEATURES
                                              if m in self.features and feature_matches(m, self.features[m], k[m])]
            self.log.info(f"Gerät: {self.device} [profile status: {profile_status(self.device)}] — "
                          f"{DEVICES[self.device]['beschreibung']}; erkannt über {self.detection['ueber']}"
                          + (f" ({'bestätigt durch' if self.device_fixed else 'Merkmale'}: " + ", ".join(self.detection["merkmale"]) + ")"
                             if self.detection["merkmale"] else ""))
        else:
            self.reference_device = self.closest_profile()
            self.log.warn(f"UNBEKANNTES IMAGE — kein Geräteprofil passt (bekannt: {', '.join(DEVICES)}). Best-Effort: Abgleich "
                          f"gegen das ähnlichste Profil '{self.reference_device}'; jede Abweichung unten ist ein Warnzeichen")
        profile = DEVICES[self.reference_device]
        for a in self.artefacts:
            ref = profile["referenz"].get(a["pfad"])
            if ref is None:
                continue
            a["referenzgeraet"] = self.reference_device
            a["referenz_stimmt"] = (a["groesse"] == ref[0] and a["sha256"] == ref[1])
            if a["referenz_stimmt"]:
                a["pruefung"].append(f"Referenz {self.reference_device} stimmt ({ref[1][:16]}…)")
                self.log.info(f"{a['pfad']}: Referenz {self.reference_device} stimmt")
            else:
                a["pruefung"].append(f"Referenz {self.reference_device} weicht ab: erwartet {ref[0]} B {ref[1][:16]}…, "
                                     f"ist {a['groesse']} B {a['sha256'][:16]}…")
                (self.log.warn if self.device else self.log.info)(
                    f"{a['pfad']}: weicht von der Referenz {self.reference_device} ab"
                    + ("!" if self.device else " (unbekanntes Image — erwartbar)"))
        self.deviations = self.deviations_from(self.reference_device)
        if self.deviations:
            if self.device:
                self.log.warn(f"Eingang weicht vom {profile['name']}-Stock ab, obwohl das Gerät erkannt wurde — Profil oder Eingang prüfen")
            self.log.heading(f"Abweichungen vom {profile['name']}-Stock" + (" — hier drohen Probleme" if not self.device else ""))
            for a in self.deviations:
                self.log.info("- " + a)
        if self.old_device and not self.device:
            self.log.warn(f"{self.out} enthielt ein Manifest für Gerät '{self.old_device}'; dieser Lauf ist unbekannt — "
                          f"Verzeichnisinhalt ist jetzt gemischt, besser trennen")
        errors = [a for a in self.artefacts if a["fehler"]]
        ref_no = [a for a in self.artefacts if a["referenz_stimmt"] is False]
        missing = [p for p in REQUIRED_FILES if not any(a["pfad"] == p for a in self.artefacts)]
        # Stage 2 C-D: exit 0 stays reserved for a *verified* profile whose references are all equal.
        status = profile_status(self.device)
        if self.device and status != "verified":
            self.log.warn(f"profile '{self.device}' has status '{status}', not 'verified' — exit code stays 1 "
                          f"(doku/121 section 5: only a verified profile has run against the hardware)")
        code = 0
        if (self.device is None or status != "verified" or errors or ref_no or missing
                or self.not_extracted or self.deviations):
            code = 1
        if not self.artefacts:
            code = 2
        return code

    # ---- Storing --------------------------------------------------------------------------------

    def store(self, rel: str, data: bytes, origin: str, checks: List[str], error: bool):
        target = self.out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        h = sha256_bytes(data)
        # The reference comparison only happens in grade(): with single parts the device can be settled
        # only after the vendor partition
        self.artefacts.append({"pfad": rel, "groesse": len(data), "sha256": h, "md5": hashlib.md5(data).hexdigest(),
                               "herkunft": origin, "pruefung": checks, "fehler": error, "referenz_stimmt": None,
                               "referenzgeraet": None})
        state = "FEHLER" if error else "ok"
        self.log.info(f"-> {rel}: {len(data)} B, sha256 {h}, Prüfung {state}")

    # ---- Main course ----------------------------------------------------------------------------

    def run(self) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        try:
            self.read_old_manifest()
            if self.args.input:
                q = self.open(self.args.input)
                self.fingerprint(q, "Eingang")
                if Imagewty.is_imagewty(q):
                    self.input_imagewty(q)
                elif Gpt.is_gpt(q):
                    self.input_emmc(q)
                elif q.read(0, 13) == SunxiPackage.NAME:
                    self.input_facts["typ"] = "sunxi-package"
                    self.package_from_source(q, q.path.name)
                elif SparseSource.is_sparse(q) or q.read(4096, 4) == b"gDla":
                    self.input_facts["typ"] = "super"
                    self.super_from_source(q)
                elif q.size > 0x800 and struct.unpack_from("<H", q.read(0x438, 2), 0)[0] == 0xEF53:
                    self.input_facts["typ"] = "ext4 (vendor)"
                    self.vendor_source = q
                elif Fat.is_fat(q):
                    self.input_facts["typ"] = "FAT (bootloader_a/_b bzw. boot-resource.fex)"
                    self.mips_source(q, f"{q.path.name} (FAT-Abbild)", ("bootloader_b", "bootloader_a"))
                else:
                    raise Abort(f"Eingang nicht erkannt: {q.path} ({hexdump_short(q.read(0, 16))}) — "
                                f"weder IMAGEWTY, GPT-Dump, sunxi-package, Sparse/LP-super, ext4 noch FAT")
            else:
                self.input_parts()
            self.extract_scp()
            self.extract_edid()
            self.extract_msp()
            if not self.args.no_pq:
                self.extract_pq()
            if not self.args.no_mips:
                self.extract_mips()
            if not self.args.no_wlan:
                self.extract_wlan()
            self.observe()
        except Abort as e:
            self.log.error(str(e))
            if self.out_locked:
                self.log.heading("Ergebnis: Exit 2 — Ausgabeverzeichnis gehört einem anderen Gerät, nichts geschrieben")
                return 2
            self.write_manifest(2)
            return 2
        finally:
            self.cleanup()
        code = self.grade()
        self.write_manifest(code)
        return code

    def cleanup(self):
        for q in self.open_sources:
            try:
                q.fh.close()
            except Exception:  # noqa: BLE001
                pass
        if self.args.keep_tmp:
            self.log.info(f"Zwischenstände bleiben (--keep-tmp): {self.tmp}")
            return
        if self.tmp.exists():
            size = sum(p.stat().st_size for p in self.tmp.rglob("*") if p.is_file())
            shutil.rmtree(self.tmp, ignore_errors=True)
            self.log.info(f"Zwischenstände gelöscht ({size} B in {self.tmp})")

    def write_manifest(self, code: int):
        if code == 0:
            result = f"bekanntes Gerät {self.device}, alles geprüft und referenzgleich"
        elif code == 1:
            result = ("unbekanntes Image (kein Geräteprofil passt) — Ausgabe liegt, aber prüfen" if self.device is None
                      else f"Gerät {self.device} erkannt, aber Teile fehlen, weichen ab oder sind fehlerhaft — Ausgabe liegt, aber prüfen")
        else:
            result = "Fehler"
        man = {
            "werkzeug": f"h713-extract {VERSION}",
            "zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_code": code,
            "ergebnis": result,
            "device": self.device,
            "device_name": DEVICES[self.device]["name"] if self.device else None,
            "device_beschreibung": DEVICES[self.device]["beschreibung"] if self.device else None,
            "device_status": profile_status(self.device),   # stage 2 C-D: verified / profile-only / partial
            "device_erkennung": {k: v for k, v in self.detection.items() if not k.startswith("_")},
            "referenzgeraet": self.reference_device,
            "merkmale": self.features,
            "eingang": self.input_facts,
            "mips": self.mips,
            "artefakte": self.artefacts,
            "nicht_extrahiert": self.not_extracted,
            "abweichungen": self.deviations,
            "warnungen": self.log.warnings,
            "beobachtungen": self.observations,
            "nicht_angefasst": ["HDCP-/DRM-Schlüssel (Secure Storage, private-Partition, hdcp*-Dateien)",
                                "WLAN/BT-Firmware aic8800 (nur benannt)", "APKs, Android system/boot"],
        }
        (self.out / "MANIFEST.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # Readable report
        report = [f"h713-extract {VERSION} — Bericht {man['zeit']}", "",
             f"Eingang: {self.input_facts.get('pfad') or self.input_facts.get('teile')} ({self.input_facts.get('typ')})",
             f"sha256:  {self.input_facts.get('sha256')}",
             f"Bekannt: {self.input_facts.get('bekannt_als') or 'kein bekannter Image-Fingerabdruck'}",
             f"Gerät:   " + (f"{self.device} [profile status: {profile_status(self.device)}] — "
                             f"{DEVICES[self.device]['beschreibung']} (erkannt über {self.detection['ueber']}"
                             + ((", bestätigt durch " if self.device_fixed else ": ") + ", ".join(self.detection["merkmale"])
                                if self.detection["merkmale"] else "") + ")"
                             if self.device else
                             f"UNBEKANNT — kein Profil passt (bekannt: {', '.join(DEVICES)}); Best-Effort gegen '{self.reference_device}'"),
             f"Ergebnis: Exit {code} — {result}", ""]
        if self.mips:
            m = self.mips
            report += ["Projekt-ID (Plan 108 §4.5):",
                  f"  benutzt:     {m['projekt_id_benutzt'] or 'UNBESTIMMT'}  ({m['projekt_id_benutzt_woher']})",
                  f"  deklariert:  {m['projekt_id_deklariert'] or '—'}"
                  + (f"  ({m['projekt_id_deklariert_quelle']})" if m["projekt_id_deklariert_quelle"]
                     else f"  ({m['projekt_id_deklariert_hinweis']})") + "  — gemeldet, NICHT benutzt",
                  f"  vorhanden:   {len(m['projekt_id_dateien'])} ProjectID-Dateien: {', '.join(m['projekt_id_dateien'])}",
                  f"  Quelle:      {m['quelle']} ({m['dateisystem']})"]
            # Stage 2 C-D: which sources were tried in which order, and the cross-check against them.
            report.append("  Sources:     " + ", ".join(
                f"{s['source']} [{s['role']}" + (f", {s['files']} files]" if s["files"] is not None else "]")
                for s in m["sources"]))
            for v in m["cross_check"]:
                report.append(f"  Cross-check: {v}")
            r = m["revision"]
            if r:
                # The row a profile's mips.revisions needs -- the field names of the profile schema.
                report += ["  display.bin revision" + (":" if r["known"] else " — UNKNOWN, the row a profile would need:"),
                           f"    name:             {r['name']}",
                           f"    size:             {r['size']}",
                           f"    sha256:           {r['sha256']}",
                           f"    hdcp_wait_va:     {r['hdcp_wait_va']}  ({r['hdcp_wait_va_source']})",
                           f"    project_ids_seen: {', '.join(r['project_ids_seen']) or '—'}"]
            if not m["display_bin_bekannt"]:
                report += ["  ACHTUNG: display.bin ist keine bekannte Revision — die benutzte ID ist nicht bestimmbar.",
                      "           Alle ProjectID-Dateien liegen in der Ausgabe; die richtige zur Laufzeit wählen",
                      "           (setenv h713_project 0x…; saveenv). Bekannte Revisionen:"]
                report += [f"             {r}" for r in m["revisionstabelle"]]
            if m["nicht_extrahiert_gleiche_partition"]:
                report += ["  Dieselbe Partition enthält (nicht kopiert, unsere Kette nutzt es nicht):",
                      "    " + ", ".join(m["nicht_extrahiert_gleiche_partition"])]
            report.append("")
        report.append("Artefakte:")
        for a in self.artefacts:
            report.append(f"  {a['pfad']}: {a['groesse']} B sha256 {a['sha256']}")
            report.append(f"      Herkunft: {a['herkunft']}")
            for p in a["pruefung"]:
                report.append(f"      Prüfung:  {p}")
            report.append(f"      Ergebnis: {'FEHLER' if a['fehler'] else 'ok'}, Referenz "
                     f"{'stimmt' if a['referenz_stimmt'] else 'weicht ab' if a['referenz_stimmt'] is False else 'keine'}"
                     + (f" ({a['referenzgeraet']})" if a.get("referenzgeraet") else ""))
        if self.deviations:
            report += ["", f"Abweichungen vom {DEVICES[self.reference_device]['name']}-Stock"
                  + (" — unbekanntes Image, hier drohen Probleme:" if not self.device else " (trotz erkanntem Gerät — prüfen!):")
                  ] + [f"  - {a}" for a in self.deviations]
        if self.not_extracted:
            report += ["", "Nicht extrahiert:"] + [f"  - {o}" for o in self.not_extracted]
        if self.log.warnings:
            report += ["", "Warnungen:"] + [f"  - {w}" for w in self.log.warnings]
        report += ["", "Nicht angefasst: " + "; ".join(man["nicht_angefasst"]), "", "Protokoll:"] + self.log.lines
        (self.out / "BERICHT.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
        self.log.heading(f"Ergebnis: Exit {code} — {result}")
        self.log.info(f"Ausgabe: {self.out}  (MANIFEST.json, BERICHT.txt)")
