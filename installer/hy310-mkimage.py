#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hy310-mkimage -- das einspielbare Abbild fuer den HY310/H713-Beamer bauen.

Erzeugt aus den vorhandenen Bausteinen (SPL, U-Boot proper, Kernel-FIT, den
beiden ext4-Dateisystemen) ein Abbild nach Layout v3 (doku/109 §2), dazu die
Offsettabelle, ein Manifest, Pruefsummen und eine Liesmich-Datei.

DAS ABBILD HAT EIN LOCH.
Bei LBA 12288..14335 liegt der Secure Storage: HDCP-Schluessel, die WLAN- und
Bluetooth-MAC-Adressen und die Seriennummer des Geraets. Geraetespezifisch, in
keinem Firmware-Abbild, nicht wiederherstellbar (doku/109 §2.3). Deshalb ist
das Abbild NICHT eine durchgehende Datei, sondern drei Stuecke, und der
gesperrte Bereich kommt in keinem davon vor. Ein `dd` von Hand kann ihn damit
gar nicht ueberschreiben -- auch nicht, wenn der Nutzer die Sperre des
Installers nicht hat. Begruendung ausfuehrlich in doku/nachtlog/S47.

DIE PROPRIETAEREN DATEIEN SIND PLATZHALTER.
43 Dateien (19 Anzeige-Artefakte, 3 Firmware-Dateien, 8 PQ-Dateien, 13 WLAN-
Firmware-Dateien) duerfen nicht mitverteilt werden. Im Abbild stehen an ihrer Stelle Platzhalter genau
richtiger Groesse; `hy310-install` fuellt sie aus dem, was `h713-extract` aus
dem Geraet des Nutzers geholt hat. Wo sie liegen, steht in der Offsettabelle.

DER SSH-SCHLUESSEL DES NUTZERS IST AUCH EIN PLATZHALTER.
/root/.ssh/authorized_keys liegt im Abbild als Datei fester Groesse (4096 B),
gefuellt mit Zeilenumbruechen -- fuer sshd eine leere Datei, also gueltig, auch
wenn niemand sie fuellt. `hy310-install --authorized-key DATEI` schreibt den
oeffentlichen Schluessel hinein, aufgefuellt mit Zeilenumbruechen (Nullbytes
machten die Datei kaputt). Kein Schluessel im verteilten Abbild (doku/107 §3),
kein ext4-Schreiber noetig. Die Offsets kommen aus dem ext4, nicht aus dem
Fuellmuster, deshalb darf dieser Platzhalter anders aussehen als die anderen.
Besitz und Rechte (root:root, /root/.ssh 0700, Datei 0600) stellt der Baum
sicher -- und Schritt 5 prueft sie im fertigen ext4, weil sshd sonst den
Schluessel stillschweigend ignoriert.

Aufrufe:

  hy310-mkimage.py --out out/hy310-v0.1.img
        Abbild (drei Teile) + Tabelle + Manifest + LIESMICH erzeugen.

  hy310-mkimage.py --pruefen out/hy310-v0.1.tabelle.json
        Ein fertiges Abbild gegen seine Tabelle validieren: Groessen,
        Pruefsummen, GPT, Lage der Platzhalter, Loch frei.

  hy310-mkimage.py --baum-boot VERZ
  hy310-mkimage.py --baum-rootfs VERZ
        Nur die Dateibaeume mit den Platzhaltern schreiben. Aus ihnen bauen
        wir (im Container, NICHT beim Nutzer) mit mke2fs die beiden ext4 --
        siehe mkimage-eingaben.sh.

Laeuft unter Linux und Windows: Python 3.9+, reine Standardbibliothek, keine
externen Programme. Der einzige Programmteil, der mehr braucht, ist das Suchen
der Platzhalter-Offsets im fertigen ext4 -- dafuer wird der ext4-Leser aus
h713-extract geladen (auch reines Python, S45). Das geschieht beim Bau, nicht
beim Nutzer; --pruefen kommt ohne ihn aus.
"""

# Stage 1 of doku/121: the tool is a thin script over the h713 package; every flag and every
# printed line is the same as before. English identifiers, German output until stage 3.

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from h713.mkimage import VERSION, build, check, tree_boot, tree_rootfs   # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Das einspielbare Abbild fuer den HY310/H713-Beamer bauen (doku/109, doku/110).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--out", metavar="DATEI.img",
                   help="Ziel; daneben entstehen Tabelle, Pruefsummen und LIESMICH")
    p.add_argument("--pruefen", metavar="TABELLE.json",
                   help="ein fertiges Abbild gegen seine Tabelle validieren")
    p.add_argument("--baum-boot", metavar="VERZ",
                   help="nur den Dateibaum fuer hy310-boot schreiben")
    p.add_argument("--baum-rootfs", metavar="VERZ",
                   help="nur die Rootfs-Platzhalter schreiben (Overlay)")
    p.add_argument("--fit", help="Kernel-FIT fuer --baum-boot")
    p.add_argument("--spl", help="SPL (Vorgabe: tftp/spl-release.bin)")
    p.add_argument("--uboot", help="U-Boot proper (Vorgabe: tftp/uboot-proper-release.bin)")
    p.add_argument("--env", help="U-Boot-Umgebung, 64 KiB mit CRC aus mkenvimage (Vorgabe: tftp/hy310-env-release.bin)")
    p.add_argument("--boot-ext4", help="fertiges hy310-boot.ext4 (128 MiB)")
    p.add_argument("--rootfs-ext4", help="fertiges hy310-rootfs.ext4 mit Platzhaltern")
    p.add_argument("--extraktor", help="Pfad zu h713-extract (sonst daneben gesucht)")
    p.add_argument("--version", action="version", version="hy310-mkimage " + VERSION)
    args = p.parse_args(argv)

    print("hy310-mkimage %s" % VERSION)
    if args.baum_boot:
        return 0 if tree_boot(args.baum_boot, args.fit) else 1
    if args.baum_rootfs:
        return 0 if tree_rootfs(args.baum_rootfs) else 1
    if args.pruefen:
        return check(args.pruefen)
    if args.out:
        return build(args, here=os.path.dirname(os.path.abspath(__file__)))
    p.print_help()
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        sys.exit(130)
