#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""
hy310-install -- HY310/H713-Beamer auf Linux umstellen, von einem PC aus.

Laeuft unter Linux und Windows, mit Python 3.9+ und ohne weitere Pakete.
Vorgabe: doku/110-plan-installationsweg.md.

Der ganze Ablauf in vier Schritten:

  1. Geraet in den FEL-Modus bringen: Reset-Taste halten, Strom einstecken.
     (Kein Gehaeuse oeffnen, kein Pad, kein Loeten.)
  2. Dieses Skript starten. Es laedt U-Boot fluechtig ueber USB -- dabei wird
     KEIN Byte auf die eMMC geschrieben -- und laesst es die eMMC als
     USB-Laufwerk freigeben.
  3. Es zieht einen Abzug (Groesse zur Wahl), holt die geraeteeigenen Teile
     daraus und schreibt das neue Abbild.
  4. Strom aus und wieder an. Fertig.

Aus der Laufwerksfreigabe kommt man nur durch Stromabschalten heraus -- das
ist kein Mangel, sondern der Abschluss: danach startet ohnehin das neue System.

Mit --authorized-key DATEI kommt der eigene oeffentliche SSH-Schluessel ins
Abbild (Platzhalter /root/.ssh/authorized_keys, 4096 Byte, aufgefuellt mit
Zeilenumbruechen). Ohne ihn gibt es keinen ssh-Zugang, nur die serielle
Konsole -- das Abbild traegt absichtlich keinen Schluessel (doku/107 §3).
"""

# Stage 1 of doku/121: the installer is a thin script over the h713 package -- main() and
# _arbeiten() are the old ones with the package's English names; every flag and every printed
# line is unchanged (German output until stage 3).

import argparse
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from h713.blockdev import (Disk, LOCK_FIRST, LOCK_LAST, SECTORS_EXPECTED,   # noqa: E402
                           device_kind, find_drive)
from h713.dump import (choose_dump, dump_full, dump_small, verify_dump,     # noqa: E402
                       write_manifest)
from h713.env import ENV_CARRY_OVER                                        # noqa: E402
from h713.fel import fel_instructions, fel_present, fel_tool                # noqa: E402
from h713.identify import identify_device, report_device                    # noqa: E402
from h713.install import ask, confirm, image_package, write_package         # noqa: E402
from h713.log import console                                               # noqa: E402
from h713.stock import restore_stock                                       # noqa: E402
from h713.util import duration as dauer, mib                               # noqa: E402
from h713.verify import verify_image, write_image                          # noqa: E402

VERSION = "0.1 (Entwurf, doku/110)"
ENV_UEBERNEHMEN = ENV_CARRY_OVER


def main(argv=None):
    p = argparse.ArgumentParser(
        description="HY310/H713-Beamer auf Linux umstellen (doku/110).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--abbild", metavar="TABELLE|VERZ|DATEI",
                   help="das zu schreibende Abbild: die *.tabelle.json von "
                        "hy310-mkimage, das Verzeichnis darum, oder eine "
                        "einzelne .img-Datei")
    p.add_argument("--tabelle", help="Offsettabelle, wenn --abbild eine einzelne Datei ist")
    p.add_argument("--vendor", metavar="VERZ",
                   help="fertige Ausgabe von h713-extract; ohne das wird aus "
                        "dem Vollabzug extrahiert")
    p.add_argument("--authorized-key", metavar="DATEI",
                   help="oeffentlicher SSH-Schluessel (z. B. ~/.ssh/id_ed25519.pub) fuer "
                        "/root/.ssh/authorized_keys im Abbild; ohne ihn kein ssh-Zugang")
    p.add_argument("--arbeitskopie", metavar="DATEI",
                   help="wohin die gefuellte Kopie des Abbilds geht "
                        "(Vorgabe: <sicherung>/abbild-gefuellt.img, ~1,2 GB)")
    p.add_argument("--sicherung", default="hy310-sicherung",
                   help="Verzeichnis fuer den Abzug (Vorgabe: %(default)s)")
    p.add_argument("--abzug", choices=["klein", "voll"],
                   help="ohne Rueckfrage: welcher Abzug")
    p.add_argument("--uboot", help="U-Boot fuer die Laufwerksfreigabe (u-boot-sunxi-with-spl.bin)")
    p.add_argument("--sunxi-fel", dest="fel", help="Pfad zu sunxi-fel")
    p.add_argument("--device", help="Laufwerk von Hand angeben (sonst gesucht)")
    p.add_argument("--nur-abzug", action="store_true",
                   help="nur sichern, nichts schreiben")
    p.add_argument("--restore", metavar="ABZUG",
                   help="einen Vollabzug zurueckspielen statt zu installieren")
    p.add_argument("--restore-stock", metavar="UPDATE.IMG",
                   help="die Herstellerfirmware (IMAGEWTY-Container) einspielen")
    p.add_argument("--extraktor", help="Pfad zu h713-extract (sonst daneben gesucht)")
    p.add_argument("--env-neu", dest="env_neu", action="store_true",
                   help="bei einer Neuinstallation auf unserem Layout NICHTS aus der alten "
                        "U-Boot-Umgebung uebernehmen (Vorgabe: %s werden uebernommen)"
                        % ", ".join(ENV_UEBERNEHMEN))
    p.add_argument("--ohne-erkennung", dest="ohne_erkennung", action="store_true",
                   help="die Geraeteerkennung ueberspringen (Plan 110 §8). Nur fuer "
                        "Entwicklung -- sie ist der Schutz davor, auf einer fremden "
                        "Firmware zu raten.")
    p.add_argument("--dry-run", action="store_true", help="nichts schreiben")
    p.add_argument("--version", action="version", version="hy310-install " + VERSION)
    args = p.parse_args(argv)

    print("hy310-install %s   (%s)" % (VERSION, platform.system()))

    # --- 0. Haengt die eMMC schon als Laufwerk? Dann ist FEL erledigt.
    #        (Aus der Freigabe kommt man nur durch Stromabschalten heraus;
    #         wer das Skript zweimal startet, soll nicht neu anfangen muessen.)
    schon_da = find_drive()
    if args.device and not schon_da and os.path.exists(args.device):
        # Wer den Pfad ausdruecklich nennt, meint ihn auch -- etwa wenn die
        # Erkennung das Geraet nicht mag. Frueher fiel dieser Fall in den
        # FEL-Zweig und scheiterte dort, weil das Geraet laengst U-Boot fuhr.
        schon_da = [(args.device, 0, "--device")]
    if schon_da:
        if args.device:
            pfad = args.device
        elif len(schon_da) > 1:
            console.error("Mehrere Laufwerke passen: %s. Bitte --device angeben."
                     % ", ".join(t[0] for t in schon_da))
            return 3
        else:
            pfad = schon_da[0][0]
        console.step(1, "eMMC haengt bereits als Laufwerk")
        try:
            art = device_kind(pfad)
        except PermissionError:
            console.error("Keine Leserechte auf %s. Das Skript braucht erhoehte "
                     "Rechte (unter Linux sudo, unter Windows als "
                     "Administrator)." % pfad)
            return 3
        if not art:
            console.error("%s hat die richtige Groesse, sieht aber nicht wie der "
                     "Beamer aus (weder unser noch das Stock-Layout)." % pfad)
            console.info("  Mit --device laesst es sich erzwingen -- aber sieh vorher nach,")
            console.info("  was das fuer ein Laufwerk ist.")
            return 3
        sekt = next((t[1] for t in schon_da if t[0] == pfad), 0)
        console.ok("%s, %s Sektoren, %s -- FEL und Freigabe uebersprungen"
             % (pfad, sekt or "?", art))
        return _arbeiten(args, pfad)

    # --- 1. FEL
    console.step(1, "Geraet im FEL-Modus suchen")
    fel = fel_tool(args.fel, search_dir=HERE)
    kennung = fel_present(fel)
    if not kennung:
        console.warn("Kein Geraet im FEL-Modus gefunden.")
        fel_instructions()
        if ask("\n  Nochmal versuchen? [J/n] ", "j").startswith("n"):
            return 1
        kennung = fel_present(fel)
        if not kennung:
            console.error("Immer noch nichts. Steckt das A-auf-A-Kabel?")
            return 1
    console.ok(kennung.split("\n")[0])
    # An der SoC-ID pruefen, nicht am Namen: der Name in soc=00001860(<name>)
    # kommt aus der sunxi-fel-Tabelle und fehlt bei aelteren Staenden ("unknown").
    # 0x1860 ist der H713 (Issue #1: distro-sunxi-fel meldete "(unknown)").
    if "00001860" not in kennung:
        console.error("Das ist kein H713 (SoC-ID 0x1860 nicht gefunden). Abbruch.")
        return 1
    if "1860(H713)" not in kennung and "(sun50iw12" not in kennung:
        console.warn("sunxi-fel kennt diesen SoC nicht beim Namen -- nimm das "
               "sunxi-fel aus dem Release, sonst scheitert der naechste Schritt.")

    # --- 2. Laufwerksfreigabe
    console.step(2, "eMMC als USB-Laufwerk freigeben")
    if not args.uboot:
        console.error("--uboot fehlt (U-Boot mit Laufwerksfreigabe).")
        return 2
    console.info("laedt U-Boot fluechtig -- kein Byte auf die eMMC")
    subprocess.run([fel, "uboot", args.uboot], check=True, timeout=120)
    for _ in range(20):
        time.sleep(1)
        treffer = find_drive()
        if treffer:
            break
    else:
        console.error("Es ist kein Laufwerk erschienen.")
        return 3
    if args.device:
        pfad = args.device
    elif len(treffer) > 1:
        console.error("Mehrere passende Laufwerke: %s -- bitte --device angeben."
                 % ", ".join(t[0] for t in treffer))
        return 3
    else:
        pfad = treffer[0][0]
    console.ok("%s, %d Sektoren (7,28 GiB)" % (pfad, treffer[0][1]))
    return _arbeiten(args, pfad)


def _arbeiten(args, pfad):
    schreiben = not (args.dry_run or args.nur_abzug)
    platte = Disk(pfad, writable=schreiben)
    # Fuer die Umgebung zaehlt allein die GPT: hy310-* heisst unser Layout. Das
    # ist unabhaengig von --ohne-erkennung, weil es nichts raet -- es liest
    # Partitionsnamen, 1 KiB.
    args._unser_layout = (device_kind(pfad) or "").startswith("unser Layout")
    args._alte_env = None
    try:
        # Vor dem ersten Schreibzugriff: womit haben wir es zu tun? (Plan 110 §8)
        # Kostet 1,2 MiB und Bruchteile einer Sekunde und verhindert, dass wir
        # auf einer unbekannten Firmware raten.
        if not args.ohne_erkennung:
            console.step("1b", "Geraet erkennen")
            erk = identify_device(platte, args.extraktor)
            if not report_device(erk, writing=schreiben) and schreiben:
                return 10
        if platte.sectors != SECTORS_EXPECTED:
            console.error("%s hat %d Sektoren, erwartet %d -- falsches Laufwerk?"
                     % (pfad, platte.sectors, SECTORS_EXPECTED))
            return 4

        # --- Herstellerfirmware einspielen
        if args.restore_stock:
            # Plan 110 §2: vor jedem Schreibzugriff der kleine Abzug. Er kostet
            # Sekunden und rettet, was kein Image zurueckbringt (Befund S46 B2).
            # Stage 2 C5 (Marco, 14.09.): only when the device still carries the stock
            # layout -- on our own layout there is nothing stock-specific left to save,
            # and the dump exists since the first installation.
            if not args.dry_run and not args._unser_layout:
                console.step(2, "Kleiner Abzug (Pflicht, auch vor dem Zuruecksetzen)")
                os.makedirs(args.sicherung, exist_ok=True)
                mf = dump_small(platte, args.sicherung, our_layout=args._unser_layout)
                write_manifest(args.sicherung, mf, pfad)
            elif not args.dry_run:
                console.info("Our layout is on the device: no mandatory dump before the restore "
                             "(nothing stock-specific is left to save; use the dump of your first install).")
            console.step(3, "Herstellerfirmware einspielen")
            if not os.path.isfile(args.restore_stock):
                console.error("%s nicht gefunden" % args.restore_stock)
                return 5
            console.info("%s (%.0f MiB)" % (args.restore_stock, mib(os.path.getsize(args.restore_stock))))
            console.info("Der Secure Storage (LBA %d..%d) bleibt dabei unberuehrt."
                   % (LOCK_FIRST, LOCK_LAST))
            if args.dry_run:
                restore_stock(platte, args.restore_stock, args.extraktor, dry_run=True, data_dir=HERE)
                console.info("Trockenlauf -- nichts geschrieben.")
                return 0
            if not confirm("Das ueberschreibt die eMMC mit Android."):
                return 1
            t0 = time.time()
            n, parts = restore_stock(platte, args.restore_stock, args.extraktor, data_dir=HERE)
            console.ok("%.0f MiB in %s geschrieben" % (mib(n), dauer(time.time() - t0)))
            console.info("")
            console.info("Jetzt Strom abziehen und wieder einstecken.")
            return 0

        # --- Zurueckspielen statt installieren
        if args.restore:
            if not args.dry_run and not args._unser_layout:      # stage 2 C5, see above
                console.step(2, "Kleiner Abzug (Pflicht, auch vor dem Zuruecksetzen)")
                os.makedirs(args.sicherung, exist_ok=True)
                mf = dump_small(platte, args.sicherung, our_layout=args._unser_layout)
                write_manifest(args.sicherung, mf, pfad)
            elif not args.dry_run:
                console.info("Our layout is on the device: no mandatory dump before the restore "
                             "(nothing stock-specific is left to save; use the dump of your first install).")
            console.step(3, "Vollabzug zurueckspielen")
            if not os.path.isfile(args.restore):
                console.error("%s nicht gefunden" % args.restore)
                return 5
            console.info("%s (%.1f MiB)" % (args.restore, mib(os.path.getsize(args.restore))))
            if not confirm("Das ueberschreibt die eMMC mit deinem Abzug."):
                return 1
            t = write_image(platte, args.restore)
            console.ok("zurueckgespielt in %s" % dauer(t))
            console.info("")
            console.info("Jetzt Strom abziehen und wieder einstecken.")
            return 0

        # --- 3. Abzug
        wahl = choose_dump(args)
        console.step(3, "Abzug ziehen (%s)" % wahl)
        os.makedirs(args.sicherung, exist_ok=True)
        manifest = dump_small(platte, args.sicherung, our_layout=args._unser_layout)   # immer, auch bei "voll"
        if wahl == "voll":
            datei = os.path.join(args.sicherung, "emmc-voll.img")
            console.info("7,3 GB, das dauert. Zwischenstand:")
            h, t = dump_full(platte, datei)
            console.ok("%s  sha256 %s…  in %s" % (datei, h[:16], dauer(t)))
            # Ein Abzug, den niemand geprueft hat, ist kein Failsafe.
            console.info("Stichproben gegen das Geraet:")
            schlecht = verify_dump(platte, datei)
            if schlecht:
                console.error("%d Stichprobe(n) weichen ab -- der Abzug taugt nicht. "
                         "Abbruch, bevor irgendetwas geschrieben wird." % schlecht)
                return 7
            console.ok("Abzug stimmt mit dem Geraet ueberein")
            manifest.append(("emmc-voll", 0, platte.sectors, h, "vollstaendiger Klon"))
        write_manifest(args.sicherung, manifest, pfad)
        console.ok("Sicherung liegt in %s" % os.path.abspath(args.sicherung))

        if args.nur_abzug:
            console.info("\n--nur-abzug: es wird nichts geschrieben. Strom aus und an.")
            return 0

        # --- 4. Abbild vorbereiten (am PC!) und schreiben
        if not args.abbild:
            console.warn("--abbild fehlt -- es wurde nur gesichert.")
            console.info("  Ein Abbild baut hy310-mkimage (liegt daneben); --abbild nimmt")
            console.info("  dessen Tabelle oder das Verzeichnis, in dem sie liegt.")
            return 0

        verz_p, tab = image_package(args.abbild)
        if tab is None and args.tabelle:
            # Einzeldatei plus eigene Tabelle: dieselbe Mechanik, ein Teil.
            verz_p, tab = image_package(args.tabelle)
            if tab is None:
                console.error("%s ist keine Abbild-Tabelle" % args.tabelle)
                return 5
            tab = dict(tab)
            tab["teile"] = [t for t in tab["teile"]
                            if t["datei"] == os.path.basename(args.abbild)] or [{
                                "datei": os.path.basename(args.abbild), "lba": 0,
                                "bytes": os.path.getsize(args.abbild),
                                "sha256": None}]
            verz_p = os.path.dirname(os.path.abspath(args.abbild)) or "."
        if tab is not None:
            return write_package(args, platte, pfad, verz_p, tab, here=HERE)

        # Einzeldatei ohne Tabelle: ein Stueck ab LBA 0, ohne Platzhalter.
        console.step(4, "Abbild schreiben")
        if args.dry_run:
            console.info("WUERDE: %s auf %s schreiben (%.1f MiB)"
                   % (args.abbild, pfad, mib(os.path.getsize(args.abbild))))
            return 0
        console.info("%s (%.1f MiB)" % (args.abbild, mib(os.path.getsize(args.abbild))))
        if not confirm("Das ueberschreibt die eMMC."):
            return 1
        t = write_image(platte, args.abbild)
        console.ok("geschrieben in %s" % dauer(t))
        fehler = verify_image(platte, args.abbild)
        if fehler:
            console.error("%d Stichprobe(n) weichen ab -- nicht neu starten, nachfragen." % fehler)
            return 6
        console.ok("Stichproben stimmen")
        console.info("")
        console.info("Fertig. Strom abziehen und wieder einstecken.")
        return 0
    finally:
        platte.close()




if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        sys.exit(130)
