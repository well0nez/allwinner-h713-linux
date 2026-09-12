"""quellen.py -- Lesen der Stock-PQ-Daten (SQLite, INI, XML).

Dieses Modul liest ausschliesslich. Es rechnet nichts und gibt nichts aus.
Alle Datenstrukturen sind reine Abbilder der Vendor-Dateien aus
``/vendor/etc/tvconfig`` (im Baum: ``re/vendor/HY310/extracted/vendor_a/etc/tvconfig``).

Die Vendor-Dateien werden zur Laufzeit gelesen und nie kopiert.
"""

from __future__ import annotations

import os
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Dateinamen im tvconfig-Verzeichnis
# --------------------------------------------------------------------------
DATEI_DB = "tvpq.db"
DATEI_PICTUREMODE = "pq_picturemode.ini"
DATEI_FACTORY = "pq_factory_extern.ini"
DATEI_COLORTEMP = "pq_colortemp.ini"
DATEI_OVERSCAN = "pq_overscan_config.ini"
DATEI_CONFIG_XML = "pqcontrol_config_setting.xml"
DATEI_CUSTOM_XML = "pqcontrol_custom_setting.xml"
DATEI_PORTMAP = "portmap.cfg"

# Suchreihenfolge fuer das Datenverzeichnis, wenn keines angegeben ist.
SUCHPFADE = (
    # H713_TVCONFIG ist der Name seit der Umbenennung; HY310_TVCONFIG wird
    # weiter angenommen, damit bestehende Anleitungen und Testlaeufe gehen.
    os.environ.get("H713_TVCONFIG", "") or os.environ.get("HY310_TVCONFIG", ""),
    "/etc/h713/tvconfig",
    # Im Arbeitsbaum: userspace/h713-pq/h713_pq/quellen.py -> Wurzel = ../../..
    str(Path(__file__).resolve().parents[3]
        / "re/vendor/HY310/extracted/vendor_a/etc/tvconfig"),
)


def finde_datenverzeichnis(vorgabe: str | None = None) -> Path:
    """Liefert das tvconfig-Verzeichnis oder wirft FileNotFoundError."""
    kandidaten = [vorgabe] if vorgabe else list(SUCHPFADE)
    for k in kandidaten:
        if not k:
            continue
        p = Path(k)
        if (p / DATEI_PICTUREMODE).is_file() or (p / DATEI_DB).is_file():
            return p
    raise FileNotFoundError(
        "tvconfig-Verzeichnis nicht gefunden. Erwartet wurde eines von: "
        + ", ".join(x for x in kandidaten if x)
    )


# --------------------------------------------------------------------------
# INI: eigener Parser
# --------------------------------------------------------------------------
# Die Vendor-INIs sind kein configparser-Format:
#   * Werte enden auf ",\" (Fortsetzungszeichen des Vendor-Werkzeugs),
#   * Schluessel tragen Indizes wie ``PICTURE_CURVE_SETTINGS[3]`` oder
#     ``ResolutionType[0/1]``,
#   * innerhalb einer Sektion kommen Schluessel doppelt vor
#     (configparser wuerde mit DuplicateOptionError abbrechen).
# Deshalb ein eigener, absichtlich sehr einfacher Leser.

def lies_ini(pfad: Path) -> dict[str, list[tuple[str, str]]]:
    """INI -> {Sektion: [(Schluessel, Rohwert), ...]} in Dateireihenfolge."""
    sektionen: dict[str, list[tuple[str, str]]] = {}
    aktuell: list[tuple[str, str]] = []
    sektionen["__vor_erster_sektion__"] = aktuell
    with pfad.open("r", encoding="utf-8", errors="replace") as f:
        for zeile in f:
            z = zeile.strip()
            if not z or z.startswith("#") or z.startswith(";"):
                continue
            if z.startswith("[") and z.endswith("]"):
                name = z[1:-1].strip()
                aktuell = sektionen.setdefault(name, [])
                continue
            if "=" not in z:
                continue
            schluessel, wert = z.split("=", 1)
            aktuell.append((schluessel.strip(), wert.strip()))
    return sektionen


def zahlenliste(rohwert: str) -> list[int]:
    """"0,48,96,145,192,\\" -> [0, 48, 96, 145, 192]"""
    w = rohwert.rstrip("\\").strip()
    teile = [t.strip() for t in w.split(",")]
    return [int(t) for t in teile if t != ""]


# --------------------------------------------------------------------------
# Datensaetze
# --------------------------------------------------------------------------

# Spaltenreihenfolge der Werte in pq_picturemode.ini, aus dem Kommentarkopf
# der Datei selbst:
#   brightness,contrast,saturation,hue,sharpness,tnr,snr,colortemperature,
#   gamma,dci,blackextenstion,backlight,dynamic_backlight
INI_SPALTEN = (
    "brightness", "contrast", "saturation", "hue", "sharpness",
    "tnr", "snr", "colortemperature", "gamma", "dci", "blackextension",
    "backlight", "dynamic_backlight",
)


@dataclass(frozen=True)
class Bildmodus:
    """Ein Bildmodus-Preset fuer genau einen Eingang."""
    eingang: str          # Sektionsname der INI bzw. abgeleiteter Name
    name: str             # standard / cinema / vivid / game / computer / hdr / ...
    werte: dict[str, int]
    herkunft: str         # welche Datei den Datensatz geliefert hat


@dataclass(frozen=True)
class PictureModeZeile:
    """Eine Zeile aus tvpq.db::Picture_Mode."""
    tvin: int
    mode: int
    name: str
    werte: dict[str, int]


@dataclass(frozen=True)
class WeissabgleichZeile:
    """Eine Zeile aus tvpq.db::White_Balance_Mode."""
    tvin: int
    mode: int
    rgain: int
    ggain: int
    bgain: int
    roffset: int
    goffset: int
    boffset: int


@dataclass(frozen=True)
class Farbtemperatur:
    """Ein Eintrag aus pq_colortemp.ini."""
    gruppe: str           # HDMI / CVBS / ATV / DTV / VIDEODEC
    name: str             # STANDARD / COOL / WARM / USER
    roffset: int
    goffset: int
    boffset: int
    rgain: int
    ggain: int
    bgain: int


@dataclass
class Datenbestand:
    """Alles, was aus den Vendor-Dateien gelesen wurde."""
    verzeichnis: Path
    # pq_picturemode.ini
    presets: dict[str, dict[str, Bildmodus]] = field(default_factory=dict)
    preset_reihenfolge: dict[str, list[str]] = field(default_factory=dict)
    picture_mode_liste: list[str] = field(default_factory=list)
    special_mode_liste: list[str] = field(default_factory=list)
    # pq_factory_extern.ini
    werkskurven: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    pq_enable: dict[str, int] = field(default_factory=dict)
    # pq_colortemp.ini
    farbtemperaturen: dict[str, dict[str, Farbtemperatur]] = field(default_factory=dict)
    # tvpq.db
    db_picture_mode: list[PictureModeZeile] = field(default_factory=list)
    db_weissabgleich: list[WeissabgleichZeile] = field(default_factory=list)
    db_gamma_punkte: list[int] = field(default_factory=list)
    # XML
    gamma_stufen: list[float] = field(default_factory=list)
    xml_vorgaben: dict[str, str] = field(default_factory=dict)
    xml_aktuell: dict[str, str] = field(default_factory=dict)
    xml_aktueller_modus: dict[str, str] = field(default_factory=dict)
    xml_quelle_tvin: int | None = None
    # portmap.cfg
    portmap: list[tuple[int, int, str]] = field(default_factory=list)
    # Was nicht gefunden wurde
    fehlende_dateien: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Einzelleser
# --------------------------------------------------------------------------

def lies_picturemode(pfad: Path, best: Datenbestand) -> None:
    sekt = lies_ini(pfad)
    cfg = dict(sekt.get("CONFIG", []))
    if "picture_mode" in cfg:
        best.picture_mode_liste = [t.strip() for t in cfg["picture_mode"].split(",") if t.strip()]
    if "special_mode" in cfg:
        best.special_mode_liste = [t.strip() for t in cfg["special_mode"].split(",") if t.strip()]

    for name, eintraege in sekt.items():
        if name in ("CONFIG", "__vor_erster_sektion__"):
            continue
        modi: dict[str, Bildmodus] = {}
        reihenfolge: list[str] = []
        for schluessel, rohwert in eintraege:
            zahlen = zahlenliste(rohwert)
            if len(zahlen) != len(INI_SPALTEN):
                continue
            werte = dict(zip(INI_SPALTEN, zahlen))
            modi[schluessel] = Bildmodus(name, schluessel, werte, pfad.name)
            reihenfolge.append(schluessel)
        if modi:
            best.presets[name] = modi
            best.preset_reihenfolge[name] = reihenfolge


def lies_factory(pfad: Path, best: Datenbestand) -> None:
    sekt = lies_ini(pfad)
    for schluessel, wert in sekt.get("PQ_ENABLE", []):
        try:
            best.pq_enable[schluessel] = int(wert.rstrip("\\").strip())
        except ValueError:
            pass
    # [PICTURE_CURVE_<GRUPPE>]: PICTURE_CURVE_SETTINGS[1..5]
    # Die Zuordnung Index -> Groesse steht als Kommentar ueber jeder Zeile
    # in der Datei selbst (#BRIGHTNESS, #CONTRAST, #SATURATION, #HUE, #SHARPNESS).
    index_groesse = {1: "brightness", 2: "contrast", 3: "saturation",
                     4: "hue", 5: "sharpness"}
    for name, eintraege in sekt.items():
        if not name.startswith("PICTURE_CURVE_"):
            continue
        gruppe = name[len("PICTURE_CURVE_"):]
        kurven: dict[str, list[int]] = {}
        for schluessel, rohwert in eintraege:
            if not schluessel.startswith("PICTURE_CURVE_SETTINGS["):
                continue
            try:
                idx = int(schluessel.split("[", 1)[1].rstrip("]"))
            except (IndexError, ValueError):
                continue
            groesse = index_groesse.get(idx)
            if groesse:
                kurven[groesse] = zahlenliste(rohwert)
        if kurven:
            best.werkskurven[gruppe] = kurven


def lies_colortemp(pfad: Path, best: Datenbestand) -> None:
    sekt = lies_ini(pfad)
    for name, eintraege in sekt.items():
        if not name.startswith("COLOR_TEMP_"):
            continue
        gruppe = name[len("COLOR_TEMP_"):]
        eintrag: dict[str, Farbtemperatur] = {}
        for schluessel, rohwert in eintraege:
            z = zahlenliste(rohwert)
            if len(z) != 6:
                continue
            eintrag[schluessel] = Farbtemperatur(gruppe, schluessel, *z)
        if eintrag:
            best.farbtemperaturen[gruppe] = eintrag


DB_SPALTEN = ("brightness", "contrast", "saturation", "hue", "sharpness",
              "tnr", "snr", "backlight", "colortemperature", "gamma", "dci",
              "blackextenstion", "dynamic_backlight")


def lies_db(pfad: Path, best: Datenbestand) -> None:
    # Nur lesend oeffnen -- die Vendor-Datei wird nicht angefasst.
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT * FROM Picture_Mode ORDER BY tvin, mode"):
            werte = {}
            for spalte in DB_SPALTEN:
                zielname = "blackextension" if spalte == "blackextenstion" else spalte
                werte[zielname] = r[spalte]
            best.db_picture_mode.append(
                PictureModeZeile(r["tvin"], r["mode"], r["name"] or "", werte))
        for r in con.execute("SELECT * FROM White_Balance_Mode ORDER BY tvin, mode"):
            best.db_weissabgleich.append(WeissabgleichZeile(
                r["tvin"], r["mode"], r["RGain"], r["GGain"], r["BGain"],
                r["ROffset"], r["GOffset"], r["BOffset"]))
        best.db_gamma_punkte = [
            int(r["value"] or 0)
            for r in con.execute("SELECT id, value FROM Gamma_Point ORDER BY id")
        ]
    finally:
        con.close()


def lies_config_xml(pfad: Path, best: Datenbestand) -> None:
    wurzel = ET.parse(pfad).getroot()
    vorgabe = wurzel.find("default")
    if vorgabe is not None:
        best.xml_vorgaben = dict(vorgabe.attrib)
    # <transform><item name="gamma" level0="1.8" ... level4="2.4"/></transform>
    for item in wurzel.iterfind("./transform/item"):
        if item.get("name") != "gamma":
            continue
        stufen: list[float] = []
        i = 0
        while f"level{i}" in item.attrib:
            stufen.append(float(item.attrib[f"level{i}"]))
            i += 1
        best.gamma_stufen = stufen


def lies_custom_xml(pfad: Path, best: Datenbestand) -> None:
    wurzel = ET.parse(pfad).getroot()
    quelle = wurzel.find("current_source_type")
    if quelle is not None and quelle.get("tvin") is not None:
        best.xml_quelle_tvin = int(quelle.get("tvin"))
    aktuell = wurzel.find("current_data")
    if aktuell is not None:
        best.xml_aktuell = dict(aktuell.attrib)
    modus = wurzel.find("current_mode")
    if modus is not None:
        best.xml_aktueller_modus = dict(modus.attrib)


def lies_portmap(pfad: Path, best: Datenbestand) -> None:
    with pfad.open("r", encoding="utf-8", errors="replace") as f:
        for zeile in f:
            z = zeile.strip()
            if not z or z.startswith("#"):
                continue
            teile = z.split()
            if len(teile) >= 3 and teile[0].isdigit() and teile[1].isdigit():
                best.portmap.append((int(teile[0]), int(teile[1]), teile[2]))


# --------------------------------------------------------------------------
# Gesamtleser
# --------------------------------------------------------------------------

_LESER = (
    (DATEI_PICTUREMODE, lies_picturemode),
    (DATEI_FACTORY, lies_factory),
    (DATEI_COLORTEMP, lies_colortemp),
    (DATEI_DB, lies_db),
    (DATEI_CONFIG_XML, lies_config_xml),
    (DATEI_CUSTOM_XML, lies_custom_xml),
    (DATEI_PORTMAP, lies_portmap),
)


#: Die Dateien, die ein ``satz`` braucht -- und nur die. Gedacht fuer den
#: Aufruf von h713-tv beim Start (``--json``), wo jede Millisekunde Bild
#: kostet: pq_factory_extern.ini ist 592 kB gross und allein 85 ms wert (am
#: Geraet gemessen, 11.09.), liegt aber seit der Korrektur vom 07.09. nicht
#: mehr auf dem Rechenweg -- die Werkskurve ist Nebenbefund der Anzeige.
#: pq_colortemp.ini, pqcontrol_custom_setting.xml und portmap.cfg werden vom
#: Satz ebenfalls nicht gelesen.
#:
#: Gebraucht werden: pq_picturemode.ini (die Presets), tvpq.db (der Modus
#: "custom" und die Kreuzprobe) und pqcontrol_config_setting.xml (die fuenf
#: Gammastufen).
DATEIEN_FUER_SATZ = (DATEI_PICTUREMODE, DATEI_DB, DATEI_CONFIG_XML)


def lade(verzeichnis: str | None = None,
         nur: tuple[str, ...] | None = None) -> Datenbestand:
    """Liest alle bekannten PQ-Dateien.

    ``nur`` schraenkt auf eine Auswahl von Dateinamen ein (s.
    ``DATEIEN_FUER_SATZ``); was nicht gelesen wurde, steht danach unter
    ``fehlende_dateien`` mit dem Vermerk "nicht angefordert", damit keine
    Ausgabe so tut, als haette sie die Datei gesehen.

    Weder eine fehlende noch eine unlesbare Datei ist toedlich: beide landen
    in ``fehlende_dateien`` und der Rest wird trotzdem gelesen. Das ist seit
    dem 11.09. keine Bequemlichkeit mehr, sondern Bedingung -- h713-tv ruft
    dieses Programm beim Start und muss auch mit einer halb kaputten
    Extraktion noch ein Bild bekommen (Plan 113 Abschnitt A.5). Eine
    zerschossene tvpq.db kostet dann die Kreuzprobe, nicht die Presets.

    Was danach wirklich fehlt -- Eingaenge, Bildmodi -- faellt beim Rechnen
    auf, nicht hier: dort steht der Name, um den es geht, und ein
    KeyError mit Namen ist eine bessere Meldung als ein Abbruch beim Lesen.
    """
    pfad = finde_datenverzeichnis(verzeichnis)
    best = Datenbestand(verzeichnis=pfad)
    for datei, leser in _LESER:
        if nur is not None and datei not in nur:
            best.fehlende_dateien.append(f"{datei} (nicht angefordert)")
            continue
        p = pfad / datei
        if not p.is_file():
            best.fehlende_dateien.append(datei)
            continue
        try:
            leser(p, best)
        except Exception as e:               # noqa: BLE001 -- s. Docstring
            best.fehlende_dateien.append(f"{datei} (unlesbar: {e})")
    return best
