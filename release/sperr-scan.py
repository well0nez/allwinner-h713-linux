#!/usr/bin/env python3
"""sperr-scan.py -- den Export vor jedem Push absuchen: Schluessel, Vendor-Blobs, Abzuege.

    release/sperr-scan.py VERZEICHNIS [--extraktor PFAD] [--max-mb 5]

Exit 0: nichts gefunden.  Exit 1: harte Funde (unten).  Grosse Dateien sind nur ein
Hinweis fuer den Menschen, kein Fund.

Was ein harter Fund ist (doku/116 §2 "Veroeffentlichen", §7):
  1. Pfade, die nie ins Repo gehoeren: re/, hy310-sicherung*, analyse/hdcp-keys, device-dumps
  2. Dateinamen der proprietaeren Teile (die Blob-Sperre des Installers plus die
     Anzeige-Artefakte): hy310-hdcp22.bin, hdcp_v22.bin, h713-arisc.bin, msp-patch.bin,
     hy310-edid*.bin, fmacfw*, lmacfw*, fw_patch*, fw_adid*, *.TSE, display.bin,
     display_cfg.xml, LogoRegData.bin, hdcpkey*, secure-storage*, emmc-*.img
  3. Abbilder und Baueingaben: *.img, *.ext4, *.bundle, *.simg, *.fex, UPDATE.IMG
  4. Inhalt: private Schluessel ("BEGIN ... PRIVATE KEY"), OpenSSH-Privatschluessel
  5. Hashes: jede Datei, deren sha256 in der Referenztabelle von h713-extract steht --
     ein umbenannter Vendor-Blob faellt so trotzdem auf.
  6. Ein Secure-Storage-Block (Magic 'sunxi-secure-storage' bzw. der Item-Kopf mit
     "hdcpkey")
Ausgenommen: .git/, __pycache__/, die Arbeitsbaeume der Submodule aus .gitmodules
(gepusht wird ihr Commit-Zeiger, nicht ihr Inhalt) und alles, was Zeilen in .sperrscan-ignore treffen
(Zeile = Pfadpraefix relativ zur Wurzel; heute keine).
"""
from __future__ import annotations
import argparse, fnmatch, hashlib, importlib.machinery, importlib.util, os, re, sys

PFADE = ("re/", "hy310-sicherung", "analyse/hdcp-keys", "device-dumps", "mainline/build/", "tftp/", "patches-snapshots/")
# unter den gesperrten Pfaden trotzdem erlaubt: die zwei Bauskripte (alles andere in mainline/build/ ist Bauausgabe)
ERLAUBT = ("mainline/build/build.sh", "mainline/build/uboot-build.sh")
NAMEN = ("hy310-hdcp22.bin", "hdcp_v22.bin", "h713-arisc.bin", "msp-patch.bin", "hy310-edid*.bin",
         "fmacfw*", "lmacfw*", "fw_patch*", "fw_adid*", "*.TSE", "display.bin", "display_cfg.xml",
         "LogoRegData.bin", "hdcpkey*", "secure-storage*", "emmc-*.img", "*.img", "*.ext4", "*.bundle",
         "*.simg", "*.fex", "UPDATE.IMG", "update.img", "boot0*.bin", "*.i64", "*.idb", "*.id0",
         # die acht PQ-Dateien haben im Extraktor keine Hash-Referenz (strukturell geprueft) -- also per Name
         "tvpq.db", "pq_*.ini", "pqcontrol_*.xml", "portmap.cfg")
# (die Kennung geteilt geschrieben, damit dieses Skript sich nicht selbst findet)
INHALT = (re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"), re.compile(rb"PuTTY-User-Key" rb"-File"))
SECURE = (b"sunxi-secure-storage", b"hdcpkeyV22", b"wifiBleDatas")
TEXT_ENDUNGEN = {".md", ".txt", ".py", ".sh", ".c", ".h", ".patch", ".dts", ".dtsi", ".env", ".conf", ".json", ".yaml", ".yml", ".ini", ".xml", ".service", ".rules", ".cfg", ".its", ".mk", ".S", ".s", ".html", ".css", ".js", ".toml", ".gitignore", ".gitmodules", ""}


def referenz_hashes(extraktor: str | None) -> set[str]:
    if not extraktor or not os.path.isfile(extraktor):
        return set()
    try:
        L = importlib.machinery.SourceFileLoader("h713_extract", extraktor)
        m = importlib.util.module_from_spec(importlib.util.spec_from_loader("h713_extract", L))
        L.exec_module(m)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Extraktor nicht ladbar ({e}) -- Hashpruefung entfaellt", file=sys.stderr)
        return set()
    aus = set()
    for g in getattr(m, "GERAETE", {}).values():
        for wert in g.get("referenz", {}).values():
            if isinstance(wert, tuple) and len(wert) == 2 and isinstance(wert[1], str):
                aus.add(wert[1])
            elif isinstance(wert, dict):
                for w in wert.values():
                    if isinstance(w, tuple) and len(w) == 2:
                        aus.add(w[1])
    return aus


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wurzel")
    ap.add_argument("--extraktor", help="h713-extract (fuer die Hashpruefung); Vorgabe: installer/h713-extract unter der Wurzel")
    ap.add_argument("--max-mb", type=float, default=5.0)
    a = ap.parse_args()
    wurzel = os.path.abspath(a.wurzel)
    # Den Extraktor neben diesem Skript suchen (Release-Repo: installer/, Arbeits-
    # verzeichnis: analyse/release/arbeit/r2-extract) -- unabhaengig davon, welches
    # Verzeichnis gescannt wird.
    hier = os.path.dirname(os.path.abspath(__file__)); projekt = os.path.dirname(hier)
    kandidaten = [os.path.join(w, *teile) for w in (wurzel, projekt) for teile in
                  (("installer", "h713-extract"), ("analyse", "release", "arbeit", "r2-extract", "h713-extract"))]
    ex = a.extraktor or next((p for p in kandidaten if os.path.isfile(p)), None)
    hashes = referenz_hashes(ex)
    ignore = []
    ig = os.path.join(wurzel, ".sperrscan-ignore")
    if os.path.isfile(ig):
        ignore = [z.strip() for z in open(ig) if z.strip() and not z.startswith("#")]
    # Submodul-Arbeitsbaeume gehoeren fremden Repos: gepusht wird ihr Commit-Zeiger,
    # nicht ihr Inhalt. Sie mitzuscannen erzeugt nur Rauschen (U-Boot allein bringt
    # 161 Treffer aus mbedtls-Testdaten). Was von ihnen ins Repo geht, ist der Gitlink.
    submodule = set()
    gm = os.path.join(wurzel, ".gitmodules")
    if os.path.isfile(gm):
        for z in open(gm):
            z = z.strip()
            if z.startswith("path"):
                submodule.add(os.path.normpath(os.path.join(wurzel, z.split("=", 1)[1].strip())))
    # In einem Git: nur pruefen, was ein Push mitnehmen kann -- verfolgte Dateien und
    # unverfolgte, die nicht ignoriert sind. Was .gitignore ausschliesst (Bauausgaben,
    # der Tarball-Cache), kann gar nicht veroeffentlicht werden und ist nur Rauschen.
    erlaubte = None
    if os.path.isdir(os.path.join(wurzel, ".git")):
        import subprocess
        r = subprocess.run(["git", "-C", wurzel, "ls-files", "-c", "-o", "--exclude-standard", "-z"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            erlaubte = {x for x in r.stdout.split("\0") if x}
            print("  (Git erkannt: %d Dateien, die ein Push mitnehmen koennte)" % len(erlaubte))

    funde, gross, ignoriert, n = [], [], [], 0
    for d, dirs, files in os.walk(wurzel):
        dirs[:] = [x for x in dirs if x not in (".git", "__pycache__")
                   and os.path.normpath(os.path.join(d, x)) not in submodule]
        for f in files:
            p = os.path.join(d, f); rel = os.path.relpath(p, wurzel)
            if any(rel.startswith(i) for i in ignore):
                continue
            if erlaubte is not None and rel not in erlaubte:
                # Git nimmt die Datei nicht mit -- kein harter Fund. Trotzdem nach Namen
                # und Pfad ansehen und getrennt melden: was heute ignoriert im Baum liegt,
                # kann morgen jemand mit "git add -f" hineinholen.
                for pf in PFADE:
                    if rel not in ERLAUBT and (rel.startswith(pf) or ("/" + pf) in ("/" + rel)):
                        ignoriert.append((rel, pf)); break
                else:
                    for muster in NAMEN:
                        if fnmatch.fnmatch(f, muster):
                            ignoriert.append((rel, muster)); break
                continue
            n += 1
            for pf in PFADE:
                if rel in ERLAUBT:
                    break
                if rel.startswith(pf) or ("/" + pf) in ("/" + rel):
                    funde.append(("Pfad", rel, pf)); break
            for muster in NAMEN:
                if fnmatch.fnmatch(f, muster):
                    funde.append(("Name", rel, muster)); break
            if os.path.islink(p):
                continue
            try:
                groesse = os.path.getsize(p)
            except OSError:
                continue
            if groesse > a.max_mb * 1024 * 1024:
                gross.append((rel, groesse))
            if groesse == 0 or groesse > 512 * 1024 * 1024:
                continue
            with open(p, "rb") as fh:
                daten = fh.read()
            h = hashlib.sha256(daten).hexdigest()
            if h in hashes:
                funde.append(("Vendor-Hash", rel, h[:16]))
            for rx in INHALT:
                if rx.search(daten):
                    funde.append(("Schluessel", rel, rx.pattern.decode()[:30])); break
            for s in SECURE:
                if s in daten and os.path.splitext(f)[1] not in TEXT_ENDUNGEN:
                    funde.append(("Secure-Storage", rel, s.decode())); break
    print(f"sperr-scan: {n} Dateien unter {wurzel}, {len(hashes)} Referenz-Hashes")
    for art, rel, was in funde:
        print(f"  FUND  {art:<14} {rel}  ({was})")
    for rel, g in sorted(gross, key=lambda x: -x[1]):
        print(f"  gross {g/1048576:6.1f} MB  {rel}")
    if ignoriert:
        print(f"  {len(ignoriert)} Datei(en) waeren Funde, aber git ignoriert sie -- ein Push nimmt sie nicht mit:")
        for rel, was in ignoriert[:10]:
            print(f"    ignoriert  {rel}  ({was})")
        if len(ignoriert) > 10:
            print(f"    ... und {len(ignoriert) - 10} weitere")
    if funde:
        print(f"\n{len(funde)} harte Funde -- NICHT pushen.")
        return 1
    print("keine harten Funde." + (f" {len(gross)} grosse Datei(en) zum Ansehen." if gross else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
