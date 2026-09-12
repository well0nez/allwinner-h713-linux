"""ausgabe.py -- Ausgeben: Tabellen, LUT-Dateien, Board-Befehlszeilen.

Dieses Modul rechnet nicht und liest keine Vendor-Dateien. Es schreibt
ausschliesslich das, was der Aufrufer explizit verlangt hat (Text auf stdout,
LUT-Datei auf Wunsch). Es fasst keine Register an -- ein Schreibpfad wird
als Befehlszeile gedruckt, nicht ausgefuehrt.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import modell, quellen


def tabelle(kopf: list[str], zeilen: list[list[str]], einzug: str = "") -> str:
    spalten = len(kopf)
    breite = [len(k) for k in kopf]
    for z in zeilen:
        for i in range(spalten):
            breite[i] = max(breite[i], len(z[i]))
    aus = [einzug + "  ".join(kopf[i].ljust(breite[i]) for i in range(spalten)).rstrip()]
    aus.append(einzug + "  ".join("-" * breite[i] for i in range(spalten)))
    for z in zeilen:
        aus.append(einzug + "  ".join(z[i].ljust(breite[i]) for i in range(spalten)).rstrip())
    return "\n".join(aus)


def _zahl(x: float | None) -> str:
    if x is None:
        return "-"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.1f}"


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------

def drucke_liste(best: quellen.Datenbestand) -> None:
    print(f"Datenverzeichnis: {best.verzeichnis}")
    if best.fehlende_dateien:
        print("fehlende Dateien: " + ", ".join(best.fehlende_dateien))
    print()

    zeilen = []
    for e in modell.eingaenge(best):
        gruppe = modell.EINGANG_GRUPPE.get(e)
        zeilen.append([
            e,
            gruppe or "(keine)",
            ", ".join(modell.modi(best, e)),
        ])
    print("Eingaenge (Sektionen aus pq_picturemode.ini)")
    print(tabelle(["Eingang", "Kurvengruppe", "Bildmodi"], zeilen))
    print()

    print("Gamma-Stufen (pqcontrol_config_setting.xml, <transform name=\"gamma\">)")
    if best.gamma_stufen:
        print("  " + ", ".join(f"{i}={v}" for i, v in enumerate(best.gamma_stufen)))
    else:
        print("  keine gefunden")
    print()

    print("Werkskurven (pq_factory_extern.ini, PICTURE_CURVE_SETTINGS[1..5])")
    print("  Vendor-Datum. Diese Kurven liegen NICHT zwischen Benutzerwert und "
          "PQ-RPC --")
    print("  ihre Werte laufen bis 192/3588, das RPC-Argument bis 100. "
          "Verbraucher offen (doku/81 Abschnitt 3.2).")
    zeilen = []
    for gruppe in sorted(best.werkskurven):
        for groesse in modell.KURVENGROESSEN:
            k = best.werkskurven[gruppe].get(groesse)
            if k:
                zeilen.append([gruppe, groesse, ",".join(str(x) for x in k)])
    print(tabelle(["Gruppe", "Groesse", "Stuetzstellen bei 0/25/50/75/100"], zeilen))
    print()

    print("tvpq.db")
    print(f"  Picture_Mode      : {len(best.db_picture_mode)} Zeilen")
    print(f"  White_Balance_Mode: {len(best.db_weissabgleich)} Zeilen")
    gp = best.db_gamma_punkte
    if gp:
        print(f"  Gamma_Point       : {len(gp)} Zeilen, "
              f"Min {min(gp)} / Max {max(gp)}"
              + ("  -- durchgaengig 0, als Kurve unbrauchbar" if max(gp) == 0 else ""))
    print()

    print("tvin-Nummerierung der Datenbank gegen die benannten INI-Sektionen")
    zeilen = []
    for tvin, namen, kandidaten in modell.tvin_zuordnung(best):
        zeilen.append([str(tvin), ", ".join(namen),
                       ", ".join(kandidaten) if kandidaten else "(kein Treffer)"])
    print(tabelle(["tvin", "Bildmodi der Zeilen", "moegliche Eingaenge"], zeilen))
    print("  Die Zuordnung tvin -> Eingang ist aus den ausgelieferten Dateien "
          "nicht eindeutig aufloesbar.")
    print("  h713-pq rechnet deshalb ueber die benannten INI-Sektionen und "
          "nutzt die Datenbank nur zur Kreuzprobe.")
    print()

    print("Zuletzt am Stock eingestellt (pqcontrol_custom_setting.xml)")
    if best.xml_quelle_tvin is not None:
        print(f"  current_source_type tvin = {best.xml_quelle_tvin}")
    if best.xml_aktueller_modus:
        print("  " + ", ".join(f"{k}={v}" for k, v in best.xml_aktueller_modus.items()))
    if best.xml_aktuell:
        print("  " + ", ".join(f"{k}={v}" for k, v in best.xml_aktuell.items()))
    print()

    if best.pq_enable:
        print("Schalter (pq_factory_extern.ini, [PQ_ENABLE])")
        zeilen = [[k, str(v)] for k, v in best.pq_enable.items()]
        print(tabelle(["Schalter", "Wert"], zeilen))


# --------------------------------------------------------------------------
# show
# --------------------------------------------------------------------------

def drucke_kette(best: quellen.Datenbestand, k: modell.Kette) -> None:
    print(f"Eingang {k.eingang}   Bildmodus {k.modus}"
          + (f"   Kurvengruppe {k.gruppe}" if k.gruppe else "   Kurvengruppe: keine"))
    print(f"Benutzerwerte aus: {k.quelle_preset}")
    print(f"Kreuzprobe       : {k.db_abgleich}")
    print()

    zeilen = []
    for z in k.zielwerte:
        zeilen.append([z.groesse, str(z.benutzerwert),
                       "-" if z.argument is None else str(z.argument),
                       _zahl(z.kurvenwert), z.ziel, z.stand, z.hinweis])
    print(tabelle(["Groesse", "Benutzer", "RPC-Arg", "Kurve/Exp",
                   "Register -- schreibt die Firmware", "Stand", "Beleg / Hinweis"],
                  zeilen))
    print()
    print("Spalte 'RPC-Arg' ist das Ergebnis: der Wert, den THal_Vp_Set<Groesse> bekommt.")
    print("Spalte 'Kurve' ist ein Vendor-Datum aus pq_factory_extern.ini; sie liegt NICHT")
    print("  auf diesem Weg (ihre Werte laufen bis 192 bzw. 3588, das Argument bis 100).")
    print("Der Schritt Benutzerwert -> RPC-Argument ist NICHT gemessen; h713-pq reicht den")
    print("  Benutzerwert durch, weil beide Skalen 0..100 sind. Siehe doku/81 Abschnitt 3.2.")
    print()

    if k.saettigung_argument is not None:
        print("Schreibpfad Saettigung -- ueber den RPC, wie Stock "
              "(wird NICHT von hier geschrieben):")
        print(f"  ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc "
              f"SetSaturation {k.saettigung_argument}'")
        print(f"  Kontrolle danach: 0x{modell.REG_PQ_SAT_HUE:08X} [15:0] = "
              f"{k.saettigung_argument}  und")
        print(f"                    0x{modell.REG_CHROMA_GAIN:08X} [23:16] = "
              f"0x{k.gain:02X} = floor({k.saettigung_argument} x 1,28)"
              f"   (Wort 0x{k.gain_register:08X})")
        print("  Das Gain-Byte selbst ins Register zu schreiben umgeht den PQ-Block "
              "und ist NICHT der Weg der Firmware.")
    if k.gamma_exponent is not None:
        print("Schreibpfad Gamma: DE2-LUT, Paket H (Kernel, GAMMA_LUT) -- kein RPC.")
        print(f"  LUT erzeugen: h713-pq gamma {k.gamma_exponent} --lut gamma.bin")
    print()
    print("Stand 11.09.2026: alle fuenf Regler sind am Geraet gemessen und schreiben ihr")
    print("  Register eins zu eins (doku/81 Abschnitt 7.3). Offen bleibt die Stufe")
    print("  Benutzerwert -> RPC-Argument (Abschnitt 7.1) und der Verbraucher der")
    print("  Werkskurve (Abschnitt 7.5).")


# --------------------------------------------------------------------------
# saturation
# --------------------------------------------------------------------------

def drucke_saettigung(eingang: str, gruppe: str | None, bezeichner: str,
                      benutzerwert: int, kurve: float | None, argument: int,
                      gain: int, register: int,
                      kurve_normiert: int | None = None) -> None:
    print(f"Eingang {eingang} (Kurvengruppe {gruppe or 'keine'})   {bezeichner}")
    print()
    print("Die Kette, Stufe fuer Stufe:")
    print(f"  1. Benutzerwert  : {benutzerwert}      "
          f"pq_picturemode.ini / Eingabe   [belegt: Vendor-Datei]")
    print(f"  2. RPC-Argument  : {argument}      "
          f"THal_Vp_SetSaturation({argument})   [Stufe 1->2 NICHT gemessen, "
          f"1:1 durchgereicht]")
    print(f"  3. PQ-Register   : 0x{modell.REG_PQ_SAT_HUE:08X} [15:0] = {argument}"
          f"   [gemessen: Argument 1:1, K5-Abnahme f]")
    print(f"  4. Chroma-Gain   : 0x{modell.REG_CHROMA_GAIN:08X} [23:16] = 0x{gain:02X}"
          f" = floor({argument} x 1,28)   [gemessen bei 0/50/59/60/100]")
    print(f"     Registerwort  : 0x{register:08X}   (Ruhewert der Firmware "
          f"0x{modell.REG_CHROMA_GAIN_STOCK:08X} = SetSaturation "
          f"{modell.ARGUMENT_DER_FIRMWARE_VORGABE})")
    print()
    print("Nebenbefund aus den Vendor-Daten (liegt NICHT auf dieser Kette):")
    if kurve is None:
        print("  Werkskurve   : keine -- dieser Eingang hat keine Gruppe in "
              "pq_factory_extern.ini")
    else:
        print(f"  Werkskurve   : {kurve:.1f}   "
              f"(pq_factory_extern.ini, PICTURE_CURVE_SETTINGS[3])")
        if kurve_normiert is not None:
            print(f"  auf 0..100 normiert: {kurve_normiert}   "
                  f"-- {'gleich dem' if kurve_normiert == argument else 'ABWEICHEND vom'}"
                  f" Benutzerwert {benutzerwert}")
    print("  Der Kurvenwert ist kein RPC-Argument: die Kurve laeuft bis 192, das "
          "Argument bis 100,")
    print("  und das PQ-Register enthaelt nachweislich das Argument. Verbraucher "
          "der Kurve: offen.")
    print()
    print("Setzen (auf dem Board, nicht von hier):")
    print(f"  ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc "
          f"SetSaturation {argument}'")
    print("  Nicht 0x{:02X} von Hand ins Register schreiben -- das umgeht den "
          "PQ-Block.".format(gain))


# --------------------------------------------------------------------------
# gamma
# --------------------------------------------------------------------------

def drucke_gamma(erg: modell.GammaErgebnis, kanal: str) -> None:
    print(f"Gamma-Exponent {erg.exponent}")
    print(f"  Stuetzpunkte : {modell.STUETZPUNKTE} Werte, 12 Bit "
          f"(Raster wie tvpq.db::Gamma_Point)")
    print("               : " + ", ".join(str(p) for p in erg.punkte[:9]) + ", ...")
    print(f"  LUT          : {modell.LUT_EINTRAEGE} Eintraege, "
          f"lut[0]={erg.lut[0]}  lut[512]={erg.lut[512]}  "
          f"lut[1023]={erg.lut[modell.LUT_EINTRAEGE - 1]}")
    print(f"  DE2-Format   : {modell.LUT_DWORDS} u32 je Bank, "
          f"u32[i] = (lut[2i+1] << 12) | lut[2i]  (BACKGROUND.md 5.4)")
    print("    u32[0..3]: " + ", ".join(f"0x{w:08X}" for w in erg.gepackt[:4]))
    print("  u32[256..]: " + ", ".join(f"0x{w:08X}" for w in erg.gepackt[256:260]))
    print(f"  Baenke       : R 0x{modell.REG_LUT_R:08X}  "
          f"G 0x{modell.REG_LUT_G:08X}  B 0x{modell.REG_LUT_B:08X}")
    print(f"  Steuerung    : 0x{modell.REG_DISPLAY_CTRL:08X} "
          f"(Status 0x{modell.REG_DISPLAY_STAT:08X}), "
          f"Schreibsequenz BACKGROUND.md 5.3 -- ausgefuehrt von Paket H")
    print(f"  Kanal        : {kanal}")


# --------------------------------------------------------------------------
# Maschinenlesbar: ein Satz JSON auf stdout (Plan 113 Abschnitt A.3)
# --------------------------------------------------------------------------
# Ein Satz, eine Zeile Aufruf, kein Dauerlauf. Der Verbraucher ist h713-tv,
# das beim Start einmal `h713-pq --daten V show EINGANG PRESET --json --lut D`
# ruft und die Antwort anwendet. Deshalb:
#   * **alles auf stdout, nichts sonst.** Meldungen gehen nach stderr, damit
#     der Leser den Satz roh durch einen Parser schieben kann.
#   * **ein einziges JSON-Objekt**, mit Zeilenumbruch am Ende.
#   * **feste Schluesselnamen** und eine `version`; was h713-tv nicht kennt,
#     verwirft es und faellt auf seine einkompilierte Tabelle zurueck.
# Die Bedeutung der Felder steht in README.md Abschnitt "Maschinenlesbare
# Ausgabe".

def drucke_satz(satz: dict) -> None:
    """Den Satz als eine JSON-Zeile ausgeben (stdout, sonst nichts)."""
    print(json.dumps(satz, ensure_ascii=False, sort_keys=True))


def sha256_datei(pfad: Path) -> str:
    """Pruefsumme einer geschriebenen Datei -- Gegenprobe fuer den Leser."""
    h = hashlib.sha256()
    with pfad.open("rb") as f:
        for stueck in iter(lambda: f.read(65536), b""):
            h.update(stueck)
    return h.hexdigest()


def schreibe_lut(pfad: Path, erg: modell.GammaErgebnis, kanal: str) -> int:
    """LUT-Datei schreiben. kanal: r|g|b -> eine Bank, all -> R,G,B hintereinander.

    Der Weissabgleich ist in diesen Vendor-Daten neutral (Gain 512/512/512,
    Offset 0), deshalb sind alle drei Baenke gleich; "all" existiert nur,
    damit Paket H eine fertige RGB-Datei bekommt.

    Geschrieben wird ueber eine Nachbardatei mit fsync und os.replace, wie
    h713-tv es fuer seine eigenen Zustandsdateien tut: seit h713-tv diesen
    Aufruf beim Start macht und ihn nach einer Frist abbricht (Plan 113
    Abschnitt A.5), darf ein abgebrochener Lauf keine halbe LUT hinterlassen,
    die beim naechsten Start wie eine gueltige aussieht.
    """
    eine = erg.bytes_einer_bank
    daten = eine * 3 if kanal == "all" else eine
    neben = pfad.with_name(pfad.name + ".neu")
    with neben.open("wb") as f:
        f.write(daten)
        f.flush()
        os.fsync(f.fileno())
    os.replace(neben, pfad)
    return len(daten)
