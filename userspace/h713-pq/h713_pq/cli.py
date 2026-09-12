"""cli.py -- Befehlszeile von h713-pq.

h713-pq rechnet und druckt. Es fasst keine Register an, oeffnet kein
/dev/mem und redet mit keinem Board. Ein Schreibpfad wird als Befehlszeile
oder als Datei ausgegeben.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ausgabe, modell, quellen

BESCHREIBUNG = """\
Stock-PQ-Daten des HY310 lesen und in Kernel-Schnittstellen umrechnen.

Datenquellen (Vendor, werden nur gelesen):
  tvpq.db, pq_picturemode.ini, pq_factory_extern.ini, pq_colortemp.ini,
  pqcontrol_config_setting.xml, pqcontrol_custom_setting.xml, portmap.cfg
"""

BEISPIELE = """\
Beispiele:
  h713-pq list
  h713-pq show HDMI1 vivid
  h713-pq show HDMI1 standard --lut gamma-standard.bin
  h713-pq saturation HDMI1 cinema
  h713-pq saturation HDMI1 72
  h713-pq gamma 2.2 --lut out.bin
  h713-pq gamma 2.2 --kanal all --lut gamma-rgb.bin
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="h713-pq",
        description=BESCHREIBUNG,
        epilog=BEISPIELE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--daten", metavar="VERZEICHNIS", default=None,
                   help="tvconfig-Verzeichnis (sonst $H713_TVCONFIG, "
                        "/etc/h713/tvconfig, dann re/vendor/... im Baum)")
    unter = p.add_subparsers(dest="befehl", required=True)

    unter.add_parser("list", help="Eingaenge, Bildmodi, Werkskurven, Datenlage")

    s = unter.add_parser("show", help="Kette Eingang x Bildmodus -> Zielwerte")
    s.add_argument("eingang")
    s.add_argument("modus")
    s.add_argument("--lut", metavar="DATEI", type=Path, default=None,
                   help="Gamma-LUT dieses Bildmodus in DATEI schreiben")
    s.add_argument("--kanal", choices=("r", "g", "b", "all"), default="r",
                   help="LUT-Bank (Vorgabe r; alle drei Baenke sind hier gleich)")
    s.add_argument("--json", action="store_true",
                   help="statt der Tabelle einen maschinenlesbaren Satz auf "
                        "stdout: Bildmodusnummer, die neun Regler, "
                        "Gamma-Exponent, LUT-Pfad und -Pruefsumme, die "
                        "Bildmodi dieses Eingangs (siehe README)")

    t = unter.add_parser("saturation",
                         help="Saettigung -> RPC-Argument (plus Kontrollwerte "
                              "0x05001238 und Chroma-Gain 0x05140508)")
    t.add_argument("eingang")
    t.add_argument("wert", help="Bildmodus oder Benutzerwert 0..100")

    g = unter.add_parser("gamma", help="Gamma-Exponent -> DE2-LUT")
    g.add_argument("exponent", type=float)
    g.add_argument("--lut", metavar="DATEI", type=Path, default=None)
    g.add_argument("--kanal", choices=("r", "g", "b", "all"), default="r")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Mit --json liest h713-tv beim Start mit. Dann wird nur gelesen, was in
    # den Satz eingeht -- das spart auf dem Geraet rund 90 ms Bild (siehe
    # quellen.DATEIEN_FUER_SATZ). Jede andere Ausgabe zeigt alles und liest
    # deshalb auch alles.
    nur = quellen.DATEIEN_FUER_SATZ if getattr(args, "json", False) else None
    try:
        best = quellen.lade(args.daten, nur)
    except FileNotFoundError as e:
        print(f"h713-pq: {e}", file=sys.stderr)
        return 2

    if args.befehl == "list":
        ausgabe.drucke_liste(best)
        return 0

    if args.befehl == "show":
        try:
            k = modell.kette(best, args.eingang, args.modus)
        except KeyError as e:
            print(f"h713-pq: {e.args[0] if e.args else e}", file=sys.stderr)
            if args.eingang in best.presets:
                print("Bekannte Bildmodi: "
                      + ", ".join(modell.modi(best, args.eingang)), file=sys.stderr)
            else:
                print("Bekannte Eingaenge: " + ", ".join(modell.eingaenge(best)),
                      file=sys.stderr)
            return 2

        # Die LUT wird in beiden Faellen gleich geschrieben; nur die Meldung
        # daneben unterscheidet sich. Mit --json geht sie nach stderr, damit
        # auf stdout nichts steht als der Satz selbst.
        lut_pfad = lut_summe = None
        lut_bytes = 0
        if args.lut is not None:
            if k.gamma_exponent is None:
                print("h713-pq: kein Gamma-Exponent fuer diesen Modus "
                      "(pqcontrol_config_setting.xml fehlt?)", file=sys.stderr)
                return 2
            erg = modell.gamma_rechnen(k.gamma_exponent)
            try:
                lut_bytes = ausgabe.schreibe_lut(args.lut, erg, args.kanal)
            except OSError as e:
                print(f"h713-pq: {args.lut}: {e.strerror}", file=sys.stderr)
                return 2
            lut_pfad = str(args.lut)
            lut_summe = ausgabe.sha256_datei(args.lut)

        if args.json:
            ausgabe.drucke_satz(modell.satz(best, args.eingang, args.modus,
                                            lut_pfad, lut_bytes, lut_summe))
            if lut_pfad:
                print(f"h713-pq: LUT geschrieben: {lut_pfad} ({lut_bytes} Byte, "
                      f"Kanal {args.kanal}, Exponent {k.gamma_exponent})",
                      file=sys.stderr)
            return 0

        ausgabe.drucke_kette(best, k)
        if lut_pfad:
            print()
            print(f"LUT geschrieben: {lut_pfad} ({lut_bytes} Byte, "
                  f"Kanal {args.kanal}, Exponent {k.gamma_exponent})")
            print(f"  sha256       : {lut_summe}")
        return 0

    if args.befehl == "saturation":
        if args.eingang not in best.presets:
            print(f"h713-pq: unbekannter Eingang: {args.eingang}", file=sys.stderr)
            print("Bekannte Eingaenge: " + ", ".join(modell.eingaenge(best)),
                  file=sys.stderr)
            return 2
        gruppe = modell.EINGANG_GRUPPE.get(args.eingang)
        # Die Werkskurve wird nur noch als Nebenbefund angezeigt. Sie liegt seit
        # der Korrektur vom 07.09. nicht mehr auf dem Rechenweg, deshalb ist ihr
        # Fehlen (VGA1..3) kein Abbruchgrund mehr.
        stuetz = best.werkskurven.get(gruppe or "", {}).get("saturation")
        if args.wert.lstrip("+-").isdigit():
            u = int(args.wert)
            bezeichner = f"Benutzerwert {u}"
        else:
            try:
                bm = modell.preset(best, args.eingang, args.wert)
            except KeyError as e:
                print(f"h713-pq: {e.args[0] if e.args else e}", file=sys.stderr)
                return 2
            u = bm.werte["saturation"]
            bezeichner = f"Bildmodus {args.wert}"
        arg = modell.rpc_argument(u)
        gain = modell.chroma_gain(arg)
        kw = modell.kurvenwert(stuetz, u) if stuetz else None
        kw_norm = modell.kurve_als_argument(stuetz, u) if stuetz else None
        ausgabe.drucke_saettigung(args.eingang, gruppe, bezeichner, u, kw, arg,
                                  gain, modell.chroma_gain_register(gain), kw_norm)
        return 0

    if args.befehl == "gamma":
        erg = modell.gamma_rechnen(args.exponent)
        ausgabe.drucke_gamma(erg, args.kanal)
        if args.lut is not None:
            n = ausgabe.schreibe_lut(args.lut, erg, args.kanal)
            print(f"  Datei        : {args.lut} ({n} Byte)")
        return 0

    return 2
