#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mkimage-selbsttest.py -- der ganze Weg einmal durchgespielt, ohne Geraet.

Was hier geprueft wird, ist genau das, was zwischen dem Abbild-Bauer und dem
Installer schiefgehen kann:

  1. hy310-install.platzhalter_fuellen() nimmt unsere Tabelle an und schreibt
     die 30 geraeteeigenen Dateien in eine Kopie von Teil B.
  2. Danach findet der ext4-Leser sie UEBER DAS DATEISYSTEM wieder -- nicht am
     Rohoffset, sondern als /mips/display.bin & Co. Nur das beweist, dass die
     Offsets die richtigen Bloecke getroffen haben.
  3. Ein dd auf eine Attrappe (sparse, 7,28 GiB) legt die drei Teile an ihre
     Sektoren; danach muss der gesperrte Bereich unveraendert sein und die
     GPT der Attrappe unsere sechs Partitionen zeigen.

Aufruf:
    python3 mkimage-selbsttest.py out/hy310-v0.1.tabelle.json \\
            [--vendor out/vendor] [--tmp VERZ] [--behalten]

Seit doku/121 Stufe 1 laeuft der Test ueber das Paket h713 (kein Laden per Pfad mehr).
"""

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

from pathlib import Path                                                   # noqa: E402

from h713 import layout                                                     # noqa: E402
from h713.blockdev import LOCK_FIRST, LOCK_LAST, SECTORS_EXPECTED           # noqa: E402
from h713.fs.ext4 import Ext4                                              # noqa: E402
from h713.gpt import Gpt, check_gpt                                        # noqa: E402
from h713.install import check_placeholders, fill_placeholders             # noqa: E402
from h713.log import Log                                                   # noqa: E402
from h713.source import FileSource                                         # noqa: E402

SECT = 512


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tabelle")
    p.add_argument("--vendor", default=os.path.join(HIER, "out", "vendor"))
    p.add_argument("--tmp", default=os.path.join(HIER, "tmp"))
    p.add_argument("--behalten", action="store_true", help="Zwischenstaende nicht loeschen")
    a = p.parse_args()


    verz = os.path.dirname(os.path.abspath(a.tabelle))
    with open(a.tabelle, encoding="utf-8") as f:
        d = json.load(f)
    os.makedirs(a.tmp, exist_ok=True)
    fehler = 0

    def ok(t):
        print("  OK   %s" % t)

    def bad(t):
        nonlocal fehler
        print("  FEHL %s" % t, file=sys.stderr)
        fehler += 1

    # ---------------------------------------------------------------- 1
    print("\n[1] Sperre in hy310-install passt zur Tabelle")
    if (LOCK_FIRST, LOCK_LAST) == \
            (d["loch"]["lba"], d["loch"]["lba"] + d["loch"]["sektoren"] - 1):
        ok("SPERRE_ERSTER/LETZTER %d..%d -- gleich" % (LOCK_FIRST, LOCK_LAST))
    else:
        bad("Installer sperrt %d..%d, die Tabelle nennt %d.."
            % (LOCK_FIRST, LOCK_LAST, d["loch"]["lba"]))
    if SECTORS_EXPECTED == d["disk_sektoren"]:
        ok("Sektorzahl %d -- gleich" % SECTORS_EXPECTED)
    else:
        bad("Sektorzahl weicht ab")

    # ---------------------------------------------------------------- 2
    print("\n[2] platzhalter_fuellen() mit den echten Vendor-Dateien")
    quellen = {}
    for name in d["platzhalter"]:
        q = os.path.join(a.vendor, name)
        if not os.path.isfile(q):
            bad("Quelle fehlt: %s" % q)
            return 1
        with open(q, "rb") as f:
            quellen[name] = f.read()
    tabelle = {k: tuple(v) for k, v in d["platzhalter"].items()}
    probe = os.path.join(a.tmp, "probe-b-gefuellt.img")
    t0 = time.time()
    shutil.copyfile(os.path.join(verz, d["platzhalter_datei"]), probe)
    ok("Kopie von %s in %.1f s" % (d["platzhalter_datei"], time.time() - t0))

    class Still:
        @staticmethod
        def ok(_t):
            pass

    t0 = time.time()
    fill_placeholders(probe, tabelle, quellen, log=Still)
    ok("30 Dateien gefuellt in %.2f s" % (time.time() - t0))
    schlecht = check_placeholders(probe, tabelle, quellen)
    if schlecht:
        bad("platzhalter_pruefen beanstandet: %s" % schlecht)
    else:
        ok("platzhalter_pruefen: alle 30 stimmen am Rohoffset")

    # ---------------------------------------------------------------- 3
    print("\n[3] Gegenprobe UEBER das Dateisystem (nicht am Rohoffset)")
    q = FileSource(Path(probe))
    basis = {"hy310-boot": (layout.LBA_BOOT - layout.PART_B_LBA) * SECT,
             "hy310-rootfs": (layout.LBA_ROOTFS - layout.PART_B_LBA) * SECT}
    laenge = {"hy310-boot": 262144 * SECT, "hy310-rootfs": os.path.getsize(probe) - basis["hy310-rootfs"]}
    fs = {}
    for teil in basis:
        fs[teil] = Ext4(q.sub(basis[teil], laenge[teil], teil), label=teil)
        ok("%-13s als ext4 geoeffnet: %s" % (teil, fs[teil].label_fs))
    gut = 0
    for name, groesse, teil, pfad in layout.PLACEHOLDERS:
        gelesen = fs[teil].read(pfad)
        if gelesen == quellen[name]:
            gut += 1
        else:
            bad("%s: ueber das Dateisystem gelesen weicht ab (%d vs %d Byte)"
                % (pfad, len(gelesen), len(quellen[name])))
    if gut == len(layout.PLACEHOLDERS):
        ok("alle %d Dateien lesen sich ueber ext4 byteidentisch zur Quelle" % gut)
    # der Kernel-FIT muss unberuehrt geblieben sein. Bis 12.09. stand hier eine
    # feste Laenge (7987476, das FIT vom 11.09.) -- jeder neue Kernel liess den
    # Test dann "beschaedigt" melden. Jetzt: die Kennung d00dfeed, und die
    # Gesamtlaenge aus dem FDT-Kopf (Byte 4..8, big-endian) muss der Dateilaenge
    # entsprechen -- das prueft die Struktur, nicht eine Momentaufnahme. Liegt
    # die Quelle daneben (tmp/boot-baum, von mkimage-eingaben.sh), wird
    # zusaetzlich byteweise verglichen.
    fit = fs["hy310-boot"].read("/" + layout.KERNEL_FIT)
    kopf_ok = fit[:4] == b"\xd0\x0d\xfe\xed" and len(fit) >= 8 and \
        int.from_bytes(fit[4:8], "big") == len(fit)
    quelle_fit = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "boot-baum", layout.KERNEL_FIT)
    if kopf_ok and os.path.isfile(quelle_fit):
        with open(quelle_fit, "rb") as f:
            gleich = f.read() == fit
        if gleich:
            ok("h713-kernel.fit unveraendert: %d Byte, Kennung d00dfeed, byteidentisch zu tmp/boot-baum" % len(fit))
        else:
            bad("h713-kernel.fit weicht von tmp/boot-baum ab")
    elif kopf_ok:
        ok("h713-kernel.fit unveraendert: %d Byte, Kennung d00dfeed, FDT-Laenge stimmt" % len(fit))
    else:
        bad("h713-kernel.fit beschaedigt (Kennung oder FDT-Laenge)")
    # eine Datei, die NICHT Platzhalter ist, darf sich nicht geaendert haben
    fstab = fs["hy310-rootfs"].read("/etc/fstab")
    if b"hy310-rootfs" in fstab:
        ok("/etc/fstab im Rootfs unversehrt (%d Byte)" % len(fstab))
    else:
        bad("/etc/fstab sieht falsch aus")

    # ---------------------------------------------------------------- 4
    print("\n[4] dd auf eine Attrappe (sparse, %d Sektoren)" % d["disk_sektoren"])
    att = os.path.join(a.tmp, "attrappe.img")
    marke = b"SECURE-STORAGE-DARF-NICHT-ANGEFASST-WERDEN " * 24
    with open(att, "wb") as f:
        f.truncate(d["disk_sektoren"] * SECT)
        # Den gesperrten Bereich vorher mit einer Marke fuellen, damit ein
        # Treffer auffiele. 2048 Sektoren = 1 MiB.
        f.seek(d["loch"]["lba"] * SECT)
        block = (marke * (1 + (1 << 20) // len(marke)))[:d["loch"]["sektoren"] * SECT]
        f.write(block)
    vorher = hashlib.sha256(block).hexdigest()
    t0 = time.time()
    with open(att, "r+b") as z:
        for t in d["teile"]:
            with open(os.path.join(verz, t["datei"]), "rb") as f:
                z.seek(t["lba"] * SECT)
                while True:
                    b = f.read(8 << 20)
                    if not b:
                        break
                    z.write(b)
        z.flush()
        os.fsync(z.fileno())
    ok("drei Teile geschrieben in %.1f s" % (time.time() - t0))
    with open(att, "rb") as f:
        f.seek(d["loch"]["lba"] * SECT)
        nachher = hashlib.sha256(f.read(d["loch"]["sektoren"] * SECT)).hexdigest()
    if nachher == vorher:
        ok("Secure Storage unveraendert: sha256 %s… vorher wie nachher" % vorher[:16])
    else:
        bad("SECURE STORAGE UEBERSCHRIEBEN -- %s statt %s" % (nachher[:16], vorher[:16]))

    print("\n[5] Die Attrappe als Datentraeger lesen")
    aq = FileSource(Path(att))
    if Gpt.is_gpt(aq):
        g = Gpt(aq, Log(quiet=True))
        namen = [p[0] if isinstance(p, (list, tuple)) else p for p in
                 (g.parts.keys() if hasattr(g, "parts") else [])]
        ok("GPT erkannt")
    else:
        bad("die Attrappe traegt keine erkennbare GPT")
    # Partitionstabelle roh nachlesen
    kopf = aq.read(0, 9 * SECT)
    probleme = check_gpt(kopf, aq.read(layout.PART_C_LBA * SECT, layout.PART_C_SECTORS * SECT),
                              d["disk_sektoren"])
    for x in probleme:
        bad(x)
    if not probleme:
        ok("sechs Partitionen, CRCs stimmen, Sicherungskopie am Plattenende stimmt")
    # SPL und U-Boot an ihrem Platz?
    if aq.read(layout.LBA_SPL * SECT + 4, 8) == b"eGON.BT0":
        ok("eGON.BT0 steht bei LBA %d" % layout.LBA_SPL)
    else:
        bad("bei LBA %d steht keine SPL" % layout.LBA_SPL)
    # Umgebung: bis v0.8 musste der Bereich leer sein; seit 12.09. liegt dort
    # die eingebaute Vorgabe des mitgelieferten U-Boot -- 64 KiB, vorn CRC32
    # ueber den Rest, und h713_gate muss darin vorkommen.
    import zlib, struct
    umg = aq.read(layout.LBA_ENV * SECT, layout.ENV_BYTES)
    crc = struct.unpack("<I", umg[:4])[0]
    if crc == (zlib.crc32(umg[4:]) & 0xffffffff) and b"h713_gate=" in umg:
        gate = [e for e in umg[4:].split(b"\0") if e.startswith(b"h713_gate=")][0].decode()
        ok("hy310-env (LBA %d) traegt eine gueltige Umgebung: CRC %08x, %s" % (layout.LBA_ENV, crc, gate))
    elif not any(umg):
        bad("hy310-env ist leer -- U-Boot meldete dann 'bad CRC' und liefe auf Vorgaben (Stand vor 12.09.)")
    else:
        bad("hy310-env: CRC %08x passt nicht oder h713_gate fehlt" % crc)
    # Und die beiden Dateisysteme direkt aus der Attrappe
    for teil, lba, n in (("hy310-boot", layout.LBA_BOOT, 262144 * SECT),
                         ("hy310-rootfs", layout.LBA_ROOTFS, 1 << 30)):
        f2 = Ext4(aq.sub(lba * SECT, n, teil), label=teil)
        anzahl = len(list(f2.walk("/", max_depth=2)))
        ok("%-13s aus der Attrappe lesbar (Label '%s', %d Eintraege in zwei Ebenen)"
           % (teil, f2.label_fs, anzahl))

    if not a.behalten:
        for x in (probe, att):
            try:
                os.remove(x)
            except OSError:
                pass
        print("\n  Zwischenstaende geloescht (--behalten haelt sie).")

    print("\n%s" % ("ALLES GRUEN" if not fehler else "%d FEHLER" % fehler))
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
