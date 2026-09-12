"""modell.py -- Rechnen: Stock-PQ-Daten in Kernel-Schnittstellenwerte umsetzen.

Dieses Modul liest keine Dateien und druckt nichts. Es bekommt einen
``quellen.Datenbestand`` und rechnet daraus die Kette

    Eingang x Bildmodus  ->  Benutzerwert (0..100)
                         ->  RPC-Argument (0..100)
                         ->  Register (die Firmware rechnet, nicht wir)

Der Bruch mit der ersten Fassung (07.09., doku/nachtlog/G-korrektur-saettigung.md):
frueher rechnete dieses Modul den **Registerwert** der Saettigung selbst aus
(Benutzerwert -> Werkskurve -> Gain-Byte). Die Messung am Geraet
(doku/nachtlog/K5-board-verifikation.md Abschnitt f) zeigt, dass das der falsche
Weg ist. ``THal_Vp_SetSaturation`` bekommt ein Argument 0..100 und schreibt
daraufhin **selbst** zwei Register:

    SetSaturation(N)  ->  0x05001238 [15:0]  = N                (1:1)
                      ->  0x05140508 [23:16] = floor(N * 1,28)  (Chroma-Gain)

Gemessen bei N = 0 / 50 / 59 / 60 / 100 -> 0x00 / 0x40 / 0x4B / 0x4C / 0x80.
N = 59 und N = 60 unterscheiden ``floor`` von ``round`` und belegen ``floor``.

Deshalb gibt dieses Modul fuer die Saettigung das **RPC-Argument** aus. Das
Gain-Byte bleibt als Kontrollwert erhalten -- ausdruecklich als
``floor(Argument * 1,28)`` und nicht als Ergebnis der Werkskurve.

Was belegt ist und was nicht, steht je Groesse in ``PQ_ZIELE`` und wird bis in
die Ausgabe durchgereicht. Die Werkskurve bleibt als Vendor-Datum stehen, ihr
Verbraucher ist offen -- siehe ``rpc_argument`` und ``kurve_als_argument``.

Zielwerte ausserhalb der PQ-RPCs:
  * Gamma -> DE2-Gamma-LUT 0x05208000 / 0x05208800 / 0x05209000 (Paket H).
    Unveraendert: die LUT laeuft nicht ueber einen RPC, sie wird vom Kernel
    geschrieben und ist bitgleich zum Legacy-Rechner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import quellen
from . import __version__

# --------------------------------------------------------------------------
# Registerkonstanten -- jede mit Beleg
# --------------------------------------------------------------------------

#: PQ-Registerblock der MIPS-Firmware ("NEST-SW-Register"), ARM 0x05001000..0x050015FC.
#: Beleg: doku/85 Abschnitt A.1..A.3 (statisch, UIvalueMapping-Tabelle) und
#: doku/nachtlog/K5-board-verifikation.md Abschnitt c/e/f (am Geraet nachgemessen).
REG_PQ_BLOCK = 0x05001000
REG_PQ_SHARPNESS = 0x05001228      # [23:8]  Schaerfe
REG_PQ_BRIGHT_CONTRAST = 0x05001234  # [15:0] Helligkeit, [31:16] Kontrast
REG_PQ_SAT_HUE = 0x05001238        # [15:0]  Saettigung, [31:16] Farbton
#: Betriebsart des Blocks; untere vier Bit == 0xA sperren jedes Registerschreiben.
#: Am Geraet gemessen: 0x00000000, also nicht gesperrt (K5-Abnahme Abschnitt a).
REG_PQ_MODUS = 0x0500121C

#: PROC-/"route"-Block, Chroma-Gain, Gain-Feld in [23:16].
#: Firmware-Vorgabe nach dem Start: 0x144C0000, Gain 0x4C.
#: Beleg: doku/76 Abschnitt 10 + 13, doku/77 Abschnitt 4,
#: cstenger Commit 5718e4c (0x00/0x01 grau, 0x26 blass, 0x4C richtig, 0xFF uebersaettigt).
REG_CHROMA_GAIN = 0x05140508
REG_CHROMA_GAIN_STOCK = 0x144C0000
CHROMA_GAIN_SHIFT = 16
CHROMA_GAIN_MASKE = 0x00FF0000

#: Abbildung RPC-Argument -> Gain-Feld, die die **Firmware** vornimmt:
#: Gain = floor(Argument * 128 / 100) = floor(Argument * 1,28).
#: Am Geraet gemessen (K5-Abnahme Abschnitt f, 07.09.):
#:   SetSaturation 0 -> 0x00, 50 -> 0x40, 59 -> 0x4B, 60 -> 0x4C, 100 -> 0x80.
#: Die beiden Nachbarpunkte 59/60 entscheiden zwischen Abrunden und kaufmaennisch
#: Runden: 59 * 1,28 = 75,52; gemessen ist 75 (0x4B), nicht 76. Also floor.
#: Die Firmware nutzt fuer Argumente 0..100 damit nur den Feldbereich 0x00..0x80;
#: 0xFF ist im Feld darstellbar (cstenger: uebersaettigt), ueber den RPC aber
#: nicht erreichbar.
CHROMA_GAIN_ZAEHLER = 128
CHROMA_GAIN_NENNER = 100

#: Firmware-Vorgabe 0x4C entspricht genau ``SetSaturation 60`` -- prep_after_boot.sh
#: ruft SetSaturation gar nicht auf (K5-Abnahme Abschnitt f).
ARGUMENT_DER_FIRMWARE_VORGABE = 60

#: Groesster Benutzerwert / groesstes RPC-Argument der PQ-Skala.
BENUTZERWERT_MAX = 100

#: DE2-Gamma-LUT, drei Baenke a 512 u32.
#: Beleg: legacy/userspace/hy310-pqd/BACKGROUND.md Abschnitt 5.1
#: (RE aus libhaldisplay.so::WriteGammaLUTByColor, sub_0xB881).
REG_LUT_R = 0x05208000
REG_LUT_G = 0x05208800
REG_LUT_B = 0x05209000
#: Steuerregister der Schreibsequenz (BACKGROUND.md Abschnitt 5.2/5.3).
REG_DISPLAY_CTRL = 0x051C00E8
REG_DISPLAY_STAT = 0x051C0174

LUT_EINTRAEGE = 1024        # Abtastwerte je Farbkanal
LUT_DWORDS = 512            # u32-Woerter je Bank (zwei Abtastwerte je Wort)
LUT_BITS = 12
LUT_MAX = (1 << LUT_BITS) - 1   # 4095
STUETZPUNKTE = 33           # tvpq.db::Gamma_Point hat 33 Zeilen

# --------------------------------------------------------------------------
# Eingaenge
# --------------------------------------------------------------------------
# Die Eingangsnamen kommen aus den Sektionen von pq_picturemode.ini.
# Die Werkskurven- und Farbtemperatur-Gruppen kommen aus den Sektionsnamen
# von pq_factory_extern.ini ([PICTURE_CURVE_*]) bzw. pq_colortemp.ini
# ([COLOR_TEMP_*]). HDMI1..3 teilen sich die HDMI-Gruppe -- es gibt in den
# Vendor-Dateien keine eigene Kurve je HDMI-Port.
# Fuer VGA1..3 existiert KEINE Werkskurve; das wird gemeldet, nicht geraten.
EINGANG_GRUPPE = {
    "HDMI1": "HDMI", "HDMI2": "HDMI", "HDMI3": "HDMI",
    "CVBS": "CVBS",
    "ATV": "ATV",
    "DTV": "DTV",
    "VIDEODEC": "VIDEODEC",
    "VGA1": None, "VGA2": None, "VGA3": None,
}

#: Die fuenf Groessen, fuer die pq_factory_extern.ini eine Werkskurve fuehrt
#: (PICTURE_CURVE_SETTINGS[1..5]) und fuer die es je einen eigenen PQ-RPC gibt.
#: Der Name ist historisch -- die Kurve liegt seit der Korrektur vom 07.09. nicht
#: mehr auf dem Rechenweg (siehe rpc_argument), sie wird nur noch angezeigt.
KURVENGROESSEN = ("brightness", "contrast", "saturation", "hue", "sharpness")

#: Groessen, die als Index/Schalter in die MIPS-PQ gehen (RPCs, Paket I),
#: nicht ueber eine Werkskurve.
INDEXGROESSEN = ("tnr", "snr", "colortemperature", "gamma", "dci",
                 "blackextension", "backlight", "dynamic_backlight")

#: Die neun Groessen, die ein Preset ausmacht, in der Reihenfolge, in der
#: h713-tv sie sendet (Bildmodus zuerst, dann diese neun -- doku/nachtlog/S14
#: Abschnitt 4). Genau diese neun stehen im JSON-Satz unter "regler".
PRESET_GROESSEN = ("brightness", "contrast", "saturation", "hue", "sharpness",
                   "tnr", "snr", "dci", "blackextension")

#: Die uebrigen vier Spalten von pq_picturemode.ini. Sie gehen heute an keinen
#: Regler des Treibers (es gibt weder ein backlight- noch ein
#: colortemperature-Control, doku/nachtlog/S14 Abschnitt 4), werden aber
#: mitgeliefert, damit der Satz die INI-Zeile vollstaendig abbildet.
WEITERE_GROESSEN = ("colortemperature", "gamma", "backlight", "dynamic_backlight")

# --------------------------------------------------------------------------
# Bildmodusnummer der Firmware
# --------------------------------------------------------------------------
# Diese Nummer steht in KEINER der acht Vendor-Dateien: tvpq.db fuehrt in
# Picture_Mode.mode ihre eigene Zaehlung (0 standard, 1 cinema, 2 vivid,
# 3 game, 4 computer, 5 hdr, 6 custom), und die ARM-Bibliothek libvideo.so
# eine dritte. Fuer THal_Vp_SetPictureMode -- und damit fuer das Control
# "picture_mode" des Treibers -- zaehlt allein die MIPS-Firmware:
#
#   0 Vivid, 1 Standard, 2 Mild, 3 Game, 4 Calibrated, 5 Calibrated_Dark,
#   6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR,
#   13 Graphic
#
# Beleg: doku/nachtlog/S14-re-picture-mode.md Abschnitt 1.2 (Tabelle
# dword_8B1F2120 + TSE-Gruppennamen; fuer standard -> 1 zusaetzlich elog und
# XML). Die Zuordnung INI-Name -> TSE-Name laeuft ueber Namensgleichheit.
#
# Die Nummer gehoert hierher und nicht in eine zweite Tabelle in h713-tv:
# sie ist die letzte Groesse, die dem Satz "Eingang x Bildmodus -> was zu
# senden ist" noch fehlte (Plan 113 Abschnitt A.3, "eine Quelle der
# Wahrheit").
FIRMWARE_MODUS = {
    "vivid": 0,
    "standard": 1,
    "game": 3,
    "computer": 6,
    "cinema": 7,
    "hdr": 12,
}

#: energy_saving und custom haben **keinen** eigenen Firmware-Modus (S14
#: Abschnitt 4): energy_saving unterscheidet sich von standard nur im
#: Backlight 80, custom ist nur eine Zeile in tvpq.db. Beide laufen deshalb
#: unter der Standardnummer -- ihre neun Regler kommen trotzdem aus ihrer
#: eigenen Zeile.
FIRMWARE_MODUS_ERSATZ = 1


def firmware_modus(name: str) -> tuple[int, bool]:
    """Bildmodusname -> (Nummer fuer THal_Vp_SetPictureMode, eigene Nummer?).

    Das zweite Feld ist False, wenn die Firmware fuer diesen Namen keinen
    eigenen Modus fuehrt und deshalb die Standardnummer eingesetzt wird.
    """
    n = FIRMWARE_MODUS.get(name.lower())
    if n is None:
        return FIRMWARE_MODUS_ERSATZ, False
    return n, True


# --------------------------------------------------------------------------
# Wo die fuenf Kurvengroessen landen -- Stand je Stufe, ohne Rateanteil
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PqZiel:
    """Ein PQ-RPC und das Register, das er im PQ-Block bedient."""
    groesse: str
    rpc: str              # ohne das Praefix THal_Vp_
    item_id: int          # UIvalueMapping-Item, doku/85 A.1
    register: int
    maske: int
    shift: int
    stand: str            # Stand der Register-Zuordnung
    argument_1zu1: bool   # Register == RPC-Argument, am Geraet nachgemessen?
    beleg: str
    wirkung: str          # was die Wand dazu sagt

    @property
    def feld(self) -> str:
        hi = self.maske.bit_length() - 1
        lo = self.shift
        return f"[{hi}:{lo}]"

    def registerausdruck(self, argument: int | None = None) -> str:
        t = f"0x{self.register:08X} {self.feld}"
        if argument is not None:
            t += f" = {argument}"
        return t


#: Quelle: doku/85 Abschnitt A.1 (statische RE der UIvalueMapping-Tabelle) und
#: doku/nachtlog/K5-board-verifikation.md Abschnitt c/e/f (Messung am Geraet).
#: Wichtig: **alle** am Geraet gemessenen Felder dieses Blocks enthalten das
#: RPC-Argument unveraendert. Der Faktor 1,28 der Saettigung sitzt nicht hier,
#: sondern auf dem zusaetzlichen Schreibzugriff in den PROC-Block.
#:
#: Stand 11.09.2026 (Plan 113 Abschnitt A.6): die Tabelle war an drei Stellen
#: ueberholt und ist hier nachgezogen.
#:   * ``brightness`` stand auf "gemessen, ohne Wirkung". Widerlegt: die
#:     0,00 % der ersten Messung liefen gegen eine fast weisse Vorlage, auf
#:     der Helligkeit nicht anschlagen kann. Gegen dunkles Material am
#:     07.09. nachgemessen (doku/nachtlog/I0-helligkeit-nachgemessen.md):
#:     std 12,6 -> 22,7, p95 151 -> 185, monoton bis 100. Am 11.09. mit dem
#:     Auge bestaetigt (doku/81 Abschnitt 7 Punkt 4).
#:   * ``hue`` und ``sharpness`` standen auf "RE belegt, ungemessen". Am
#:     11.09. mit anliegendem 1080p-Signal gesetzt und ueber /dev/mem
#:     zurueckgelesen, eins zu eins ueber 0..100 bei 0/25/50/75/100
#:     (doku/81 Abschnitt 7 Punkt 3). Fuer ``hue`` ist die Wirkung am Bild
#:     bestaetigt (0 magenta, 100 gruen); fuer ``sharpness`` ist das
#:     Register belegt, die Bildwirkung nicht einzeln vermessen.
PQ_ZIELE = {
    "brightness": PqZiel(
        "brightness", "SetBrightness", 3, REG_PQ_BRIGHT_CONTRAST, 0x0000FFFF, 0,
        "gemessen, wirkt", True,
        "K5-Abnahme e: 100 -> 0x64; Wirkung nachtlog/I0 (07.09.)",
        "belegt -- gegen dunkles Material std 12,6->22,7, p95 151->185, "
        "monoton bis 100 (nachtlog/I0); 11.09. mit dem Auge bestaetigt"),
    "contrast": PqZiel(
        "contrast", "SetContrast", 4, REG_PQ_BRIGHT_CONTRAST, 0xFFFF0000, 16,
        "gemessen, wirkt", True,
        "K5-Abnahme c: 20/80/100 -> 0x14/0x50/0x64",
        "belegt -- 0->100 aendert 12,16 % der Bildpunkte (K5-Abnahme d)"),
    "saturation": PqZiel(
        "saturation", "SetSaturation", 5, REG_PQ_SAT_HUE, 0x0000FFFF, 0,
        "gemessen, wirkt", True,
        "K5-Abnahme f: 0/50/100 -> 0x00/0x32/0x64",
        "belegt -- 60->100 aendert 0,56 % (Quelle ueberwiegend weiss)"),
    "hue": PqZiel(
        "hue", "SetHue", 6, REG_PQ_SAT_HUE, 0xFFFF0000, 16,
        "gemessen, wirkt", True,
        "doku/81 Abschnitt 7.3 (11.09.): 0/25/50/75/100 -> 1:1 in [31:16]",
        "belegt -- 0 magenta, 100 gruen, am Bild bestaetigt (11.09.)"),
    "sharpness": PqZiel(
        "sharpness", "SetSharpness", 7, REG_PQ_SHARPNESS, 0x00FFFF00, 8,
        "gemessen (Register)", True,
        "doku/81 Abschnitt 7.3 (11.09.): 0/25/50/75/100 -> 1:1 in [23:8]",
        "Register belegt; Bildwirkung nicht einzeln vermessen"),
}

#: Dieselbe Frage fuer die Index-/Schaltergroessen. Auch hier ist der
#: Registerinhalt das RPC-Argument, kein umgerechneter Wert. Groessen, deren RPC
#: gar kein Register schreibt, stehen weiter unten in PQ_OHNE_REGISTER.
REG_PQ_DCI = 0x0500123C            # [7:0]
REG_PQ_SNR = 0x05001248            # [7:0]

PQ_ZIELE_INDEX = {
    "dci": PqZiel(
        "dci", "SetDCI", 9, REG_PQ_DCI, 0x000000FF, 0,
        "gemessen", True,
        "K5-Abnahme b: prep SetDCI 2, gelesen 2",
        "nicht einzeln vermessen"),
    "snr": PqZiel(
        "snr", "SetSNR", 12, REG_PQ_SNR, 0x000000FF, 0,
        "gemessen", True,
        "K5-Abnahme b: prep SetSNR 1, gelesen 1",
        "nicht einzeln vermessen"),
}

#: RPCs mit Item-ID, aber ohne Registeradresse in der UIMapping-Tabelle
#: (doku/85 A.1/A.5) -- sie schreiben nachweislich kein Register dieses Blocks.
PQ_OHNE_REGISTER = {
    "tnr": ("SetTNR", 13),
    "blackextension": ("SetBlackExtension", 8),
}


# --------------------------------------------------------------------------
# Werkskurve
# --------------------------------------------------------------------------

def kurvenwert(stuetzstellen: list[int], benutzerwert: float) -> float:
    """Werkskurve auswerten.

    Die fuenf Stuetzstellen liegen bei Benutzerwert 0 / 25 / 50 / 75 / 100
    (doku/77 Abschnitt 4); dazwischen wird linear interpoliert.
    """
    if not stuetzstellen:
        raise ValueError("leere Werkskurve")
    n = len(stuetzstellen)
    schritt = 100.0 / (n - 1)
    x = [i * schritt for i in range(n)]
    u = max(0.0, min(100.0, float(benutzerwert)))
    for i in range(n - 1):
        if x[i] <= u <= x[i + 1]:
            y0, y1 = stuetzstellen[i], stuetzstellen[i + 1]
            return y0 + (u - x[i]) * (y1 - y0) / (x[i + 1] - x[i])
    return float(stuetzstellen[-1])


def kurve_als_argument(stuetzstellen: list[int], benutzerwert: float) -> int:
    """Kontrollrechnung: die Werkskurve auf die RPC-Skala 0..100 normiert.

    Diese Funktion ist **nicht** der Rechenweg von ``h713-pq`` -- sie
    beantwortet nur die Frage, ob es einen Unterschied machen wuerde, wenn die
    Werkskurve doch zwischen Benutzerwert und RPC-Argument saesse (siehe
    ``rpc_argument``). Normiert wird auf die letzte Stuetzstelle, weil die
    RPC-Skala und die Kurve denselben Endpunkt haben muessten.

    Fuer die Saettigungskurve HDMI (0,48,96,145,192) weicht das Ergebnis vom
    Benutzerwert an **genau einer** Stelle ab: Benutzerwert 75 -> 76. Kein
    Bildmodus dieser Vendor-Daten benutzt 75 (vorkommende Werte: 45, 50, 60).
    Die offene Stufe hat auf die heutige Ausgabe also keine Auswirkung -- das
    ist der Grund, warum sie offen bleiben darf, statt geraten zu werden.
    """
    if not stuetzstellen or stuetzstellen[-1] == 0:
        raise ValueError("Werkskurve ohne brauchbaren Endpunkt")
    y = kurvenwert(stuetzstellen, benutzerwert)
    return int(round(BENUTZERWERT_MAX * y / stuetzstellen[-1]))


def rpc_argument(benutzerwert: int) -> int:
    """Benutzerwert aus pq_picturemode.ini -> Argument des PQ-RPC.

    **Diese Stufe ist nicht gemessen.** Belegt ist nur, was rechts und links
    davon steht:

    * Der Benutzerwert der Vendor-Presets laeuft von 0 bis 100
      (pq_picturemode.ini, Kommentarkopf).
    * Der RPC nimmt ebenfalls 0..100 und der PQ-Block spiegelt das Argument
      1:1 -- gemessen fuer SetContrast (20/80/100), SetBrightness (100) und
      SetSaturation (0/50/100), siehe ``PQ_ZIELE``.

    Die Werkskurve kann diese Stufe **nicht** sein: ihre Werte laufen bis 192
    (Saettigung) bzw. 3588 (Kontrast), das Argument nachweislich nur bis 100,
    und der Registerinhalt ist das Argument, nicht der Kurvenwert. Was die
    Werkskurve statt dessen bedient, ist offen (doku/81 Abschnitt 3.2).

    ``h713-pq`` reicht den Benutzerwert deshalb unveraendert durch und schreibt
    an jede Ausgabestelle dazu, dass diese Stufe ungemessen ist.
    ``kurve_als_argument`` zeigt, dass die einzige ernsthafte Alternative fuer
    alle Preset-Werte dieser Vendor-Daten dasselbe Ergebnis liefert.
    """
    return max(0, min(BENUTZERWERT_MAX, int(benutzerwert)))


def chroma_gain(argument: int) -> int:
    """RPC-Argument -> Gain-Feld 0x05140508 [23:16], **wie die Firmware rechnet**.

    ``floor(Argument * 1,28)``, am Geraet an fuenf Punkten gemessen
    (K5-Abnahme Abschnitt f). Ganzzahlig gerechnet, damit kein
    Gleitkomma-Rundungsfehler die Messpunkte verfehlt.

    Das ist eine **Kontrollrechnung**: geschrieben wird das Register von der
    Firmware, nicht von uns. Wer den Wert selbst ins Register schreibt, umgeht
    den PQ-Block 0x05001238 und damit alles, was daran haengt.
    """
    a = max(0, min(BENUTZERWERT_MAX, int(argument)))
    return (a * CHROMA_GAIN_ZAEHLER) // CHROMA_GAIN_NENNER


def chroma_gain_register(gain: int, basis: int = REG_CHROMA_GAIN_STOCK) -> int:
    """Gain-Byte in das Registerwort einsetzen (uebrige Bits bleiben stehen)."""
    return (basis & ~CHROMA_GAIN_MASKE) | ((gain & 0xFF) << CHROMA_GAIN_SHIFT)


# --------------------------------------------------------------------------
# Gamma
# --------------------------------------------------------------------------

def _lround(x: float) -> int:
    """C-``lround``: kaufmaennisch runden, von der Null weg."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def _idiv(a: int, b: int) -> int:
    """C-Ganzzahldivision: Abschneiden Richtung Null."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def stuetzpunkte_aus_exponent(exponent: float) -> list[int]:
    """33 Stuetzpunkte einer Potenzkurve, 12 Bit.

    1:1 wie ``GammaCurve::from_exponent`` in
    legacy/userspace/hy310-pqd/src/pqgamma.cpp:
        points[i] = lround(pow(i / 32, exponent) * 4095)
    """
    n = STUETZPUNKTE
    return [_lround(math.pow(i / (n - 1), exponent) * LUT_MAX) for i in range(n)]


def stuetzpunkte_identitaet() -> list[int]:
    """Gerade Rampe, wie ``GammaCurve::identity()``."""
    n = STUETZPUNKTE
    return [_lround(i / (n - 1) * LUT_MAX) for i in range(n)]


def interpolieren(punkte: list[int]) -> list[int]:
    """33 Stuetzpunkte -> 1024 LUT-Eintraege, stueckweise linear.

    Bitgenauer Nachbau von ``hy310::pqgamma::interpolate`` (pqgamma.cpp):
    Q16-Festkomma fuer die Segmentgrenzen, C-Ganzzahldivision fuer den
    Anteil, Endpunkte hart gesetzt.
    """
    if len(punkte) != STUETZPUNKTE:
        raise ValueError(f"{STUETZPUNKTE} Stuetzpunkte erwartet, {len(punkte)} bekommen")
    lut = [0] * LUT_EINTRAEGE
    segmente = STUETZPUNKTE - 1                     # 32
    schritt_q16 = ((LUT_EINTRAEGE - 1) << 16) // segmente
    for seg in range(segmente):
        x0 = (schritt_q16 * seg) >> 16
        x1 = (schritt_q16 * (seg + 1)) >> 16
        y0, y1 = punkte[seg], punkte[seg + 1]
        dx, dy = x1 - x0, y1 - y0
        x = x0
        while x <= x1 and x < LUT_EINTRAEGE:
            anteil = _idiv((x - x0) * dy, dx) if dx > 0 else 0
            v = y0 + anteil
            v = 0 if v < 0 else (LUT_MAX if v > LUT_MAX else v)
            lut[x] = v
            x += 1
    lut[0] = punkte[0]
    lut[LUT_EINTRAEGE - 1] = punkte[segmente]
    return lut


def packen(lut: list[int]) -> list[int]:
    """1024 Abtastwerte -> 512 u32 im DE2-Bulk-Format.

    ``u32[i] = (lut[2i+1] << 12) | lut[2i]`` -- BACKGROUND.md Abschnitt 5.4,
    aus der NEON-Schleife von WriteGammaLUTByColor.
    """
    if len(lut) != LUT_EINTRAEGE:
        raise ValueError(f"{LUT_EINTRAEGE} Eintraege erwartet, {len(lut)} bekommen")
    return [((lut[2 * i + 1] & LUT_MAX) << LUT_BITS) | (lut[2 * i] & LUT_MAX)
            for i in range(LUT_DWORDS)]


def lut_bytes(gepackt: list[int]) -> bytes:
    """512 u32 -> 2048 Byte, little-endian (Schreibreihenfolge der Bank)."""
    aus = bytearray()
    for w in gepackt:
        aus += int(w & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(aus)


@dataclass(frozen=True)
class GammaErgebnis:
    exponent: float
    punkte: list[int]
    lut: list[int]
    gepackt: list[int]

    @property
    def bytes_einer_bank(self) -> bytes:
        return lut_bytes(self.gepackt)


def gamma_rechnen(exponent: float) -> GammaErgebnis:
    punkte = stuetzpunkte_aus_exponent(exponent)
    lut = interpolieren(punkte)
    return GammaErgebnis(exponent, punkte, lut, packen(lut))


def gamma_exponent(best: quellen.Datenbestand, index: int) -> float | None:
    """Gamma-Index aus den Presets -> Exponent.

    Quelle: pqcontrol_config_setting.xml, ``<transform><item name="gamma"
    level0..level4>`` = 1.8 / 2.0 / 2.1 / 2.2 / 2.4. Dieselben fuenf Werte
    stehen als Kommentar in pq_picturemode.ini
    ("#gamma :0-1.8,1-2.0,2-2.1,3-2.2,4-2.4") und als Tabelle dword_4A50
    (180/200/210/220/240) in libhaldisplay.so -- drei unabhaengige Belege.
    """
    if 0 <= index < len(best.gamma_stufen):
        return best.gamma_stufen[index]
    return None


# --------------------------------------------------------------------------
# Kette Eingang x Bildmodus -> Zielwerte
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Zielwert:
    groesse: str
    benutzerwert: int
    kurvenwert: float | None   # Vendor-Datum, Verbraucher offen (siehe rpc_argument)
    argument: int | None       # das, was der RPC bekommt -- oder None ohne RPC
    ziel: str                  # Registerausdruck oder "-"
    stand: str                 # "am Geraet gemessen" / "RE, ungemessen" / ...
    hinweis: str = ""


@dataclass(frozen=True)
class Kette:
    eingang: str
    modus: str
    gruppe: str | None
    quelle_preset: str
    zielwerte: list[Zielwert]
    #: RPC-Argument der Saettigung -- das Ergebnis, mit dem gearbeitet wird.
    saettigung_argument: int | None
    #: Kontrollwerte: was die Firmware daraus im Chroma-Gain macht.
    gain: int | None
    gain_register: int | None
    gamma_index: int | None
    gamma_exponent: float | None
    db_abgleich: str


def eingaenge(best: quellen.Datenbestand) -> list[str]:
    return sorted(best.presets.keys())


def modi(best: quellen.Datenbestand, eingang: str) -> list[str]:
    """Bildmodi eines Eingangs.

    Grundlage ist die INI-Sektion des Eingangs. Angehaengt werden nur Modi,
    die in *keiner* INI-Sektion vorkommen, die Datenbank aber fuehrt -- das
    ist genau "custom", das pq_picturemode.ini in [CONFIG] als special_mode
    nennt, aber je Eingang nicht auffuehrt.
    """
    aus = list(best.preset_reihenfolge.get(eingang, []))
    alle_ini = {m for liste in best.preset_reihenfolge.values() for m in liste}
    nur_db = sorted({z.name for z in best.db_picture_mode} - alle_ini)
    return aus + [m for m in nur_db if m not in aus]


def preset(best: quellen.Datenbestand, eingang: str, modus: str) -> quellen.Bildmodus:
    """Benutzerwerte eines Bildmodus.

    Erste Quelle ist pq_picturemode.ini -- nur dort sind die Eingaenge
    namentlich benannt. Kennt die INI den Modus nicht (z. B. "custom"),
    wird auf tvpq.db::Picture_Mode ueber die Spalte ``name`` zurueckgegriffen.
    """
    if eingang not in best.presets:
        raise KeyError(f"unbekannter Eingang: {eingang}")
    modi_ini = best.presets[eingang]
    if modus in modi_ini:
        return modi_ini[modus]
    treffer = [z for z in best.db_picture_mode if z.name == modus]
    if treffer:
        werte = dict(treffer[0].werte)
        return quellen.Bildmodus(eingang, modus, werte,
                                 f"{quellen.DATEI_DB} (Picture_Mode, name='{modus}')")
    raise KeyError(f"unbekannter Bildmodus fuer {eingang}: {modus}")


def db_abgleich(best: quellen.Datenbestand, bm: quellen.Bildmodus) -> str:
    """Kreuzprobe INI gegen tvpq.db ueber den Modusnamen.

    Die Datenbank nummeriert die Eingaenge (Spalte ``tvin``), die INI benennt
    sie. Die Nummerierung laesst sich aus den ausgelieferten Dateien nicht
    aufloesen (siehe tvin_zuordnung), deshalb wird ueber den Modusnamen
    verglichen -- und geprueft, ob die Datenbank fuer diesen Namen ueberhaupt
    ueber alle tvin hinweg dieselben Werte fuehrt.
    """
    zeilen = [z for z in best.db_picture_mode if z.name == bm.name]
    if not zeilen:
        return f"tvpq.db kennt den Modus '{bm.name}' nicht"
    uneinig = [z for z in zeilen[1:] if z.werte != zeilen[0].werte]
    if uneinig:
        return (f"tvpq.db fuehrt '{bm.name}' je tvin unterschiedlich "
                f"({len(zeilen)} Zeilen) -- kein eindeutiger Abgleich moeglich")
    abweichungen = []
    for k, v in zeilen[0].werte.items():
        if k in bm.werte and bm.werte[k] != v:
            abweichungen.append(f"{k}: INI {bm.werte[k]} != db {v}")
    if abweichungen:
        return ("tvpq.db weicht ab: " + ", ".join(abweichungen))
    return (f"tvpq.db Picture_Mode (name='{bm.name}', {len(zeilen)} Zeilen, "
            f"tvin {min(z.tvin for z in zeilen)}..{max(z.tvin for z in zeilen)}) "
            f"stimmt Wert fuer Wert ueberein")


def kette(best: quellen.Datenbestand, eingang: str, modus: str) -> Kette:
    bm = preset(best, eingang, modus)
    gruppe = EINGANG_GRUPPE.get(eingang)
    kurven = best.werkskurven.get(gruppe or "", {})

    zielwerte: list[Zielwert] = []
    sat_arg = None
    gain = None
    gain_reg = None

    for groesse in KURVENGROESSEN:
        if groesse not in bm.werte:
            continue
        u = bm.werte[groesse]
        stuetz = kurven.get(groesse)
        kw = kurvenwert(stuetz, u) if stuetz else None
        ziel = PQ_ZIELE[groesse]
        arg = rpc_argument(u)

        hinweis = f"{ziel.rpc}/Item {ziel.item_id}; {ziel.beleg}"
        if not stuetz:
            hinweis += ("; keine Werkskurve fuer " + gruppe) if gruppe else \
                       "; keine Kurvengruppe"

        if groesse == "saturation":
            sat_arg = arg
            gain = chroma_gain(arg)
            gain_reg = chroma_gain_register(gain)
            zielwerte.append(Zielwert(
                groesse, u, kw, arg,
                f"{ziel.registerausdruck(arg)}  + 0x{REG_CHROMA_GAIN:08X} "
                f"[23:16] = 0x{gain:02X}",
                ziel.stand, hinweis))
        else:
            zielwerte.append(Zielwert(
                groesse, u, kw, arg,
                ziel.registerausdruck(arg) if ziel.argument_1zu1
                else ziel.registerausdruck() + " (Wert ungemessen)",
                ziel.stand, hinweis))

    for groesse in INDEXGROESSEN:
        if groesse not in bm.werte:
            continue
        u = bm.werte[groesse]
        if groesse == "gamma":
            exp = gamma_exponent(best, u)
            zielwerte.append(Zielwert(
                groesse, u, exp, None,
                f"DE2-LUT 0x{REG_LUT_R:08X}/0x{REG_LUT_G:08X}/0x{REG_LUT_B:08X}",
                "belegt (kein RPC)",
                f"Exponent {exp} (pqcontrol_config_setting.xml); "
                f"Schreibsequenz BACKGROUND.md 5.3, Paket H"))
        elif groesse == "colortemperature":
            zielwerte.append(Zielwert(
                groesse, u, None, None, "Weissabgleich (CTM, Paket H)",
                "neutral in den Daten", _farbtemp_hinweis(best, gruppe, u)))
        elif groesse in PQ_ZIELE_INDEX:
            zi = PQ_ZIELE_INDEX[groesse]
            zielwerte.append(Zielwert(
                groesse, u, None, u, zi.registerausdruck(u), zi.stand,
                f"{zi.rpc}/Item {zi.item_id}; {zi.beleg}"))
        elif groesse in PQ_OHNE_REGISTER:
            rpc, item = PQ_OHNE_REGISTER[groesse]
            zielwerte.append(Zielwert(
                groesse, u, None, u, "kein Register", "kein Registerschreiben",
                f"{rpc}/Item {item}; doku/85 A.1/A.5: Adresse 0, wirkt nur "
                f"ueber das PQ-Treiberobjekt"))
        else:
            zielwerte.append(Zielwert(groesse, u, None, u, "-",
                                      "kein RPC-Ziel bekannt",
                                      "doku/85 A.1 nennt keine Item-ID -- "
                                      "nicht geraten"))

    gamma_index = bm.werte.get("gamma")
    exp = gamma_exponent(best, gamma_index) if gamma_index is not None else None

    return Kette(eingang, modus, gruppe, bm.herkunft, zielwerte,
                 sat_arg, gain, gain_reg, gamma_index, exp, db_abgleich(best, bm))


# --------------------------------------------------------------------------
# Der maschinenlesbare Satz (Plan 113 Abschnitt A.3)
# --------------------------------------------------------------------------
# Was h713-tv beim Start braucht, in einem Stueck: die Bildmodusnummer, die
# neun Regler, der Gamma-Exponent und der Pfad der geschriebenen LUT.
#
# Dazu **alle** Bildmodi, die diese Daten fuer diesen Eingang hergeben, jeder
# mit seinen neun Werten. Grund: h713-tv soll `ctl preset energy_saving` auch
# dann beantworten koennen, wenn die Extraktion diesen Modus mitbringt, ohne
# h713-pq im Betrieb ein zweites Mal zu rufen (Plan 113 Abschnitt A.5,
# "wird angeboten, sobald die Daten da sind"). Acht Modi sind ein paar hundert
# Byte; ein zweiter Prozessstart waere teurer als die ganze Liste.
#
# Die angeforderte Zeile steht zusaetzlich flach im Satz (``modus``,
# ``regler``, ``weitere``), damit ein Leser, der nur diese eine Antwort will,
# nicht erst eine Liste durchsuchen muss. Beides kommt aus derselben Funktion,
# kann also nicht auseinanderlaufen.
#
# Diese Funktion rechnet und liest nichts von der Platte; das Serialisieren
# macht ausgabe.drucke_satz, das Schreiben der LUT ausgabe.schreibe_lut.

#: Fassung des Satzes. Wird erhoeht, wenn sich Bedeutung oder Pflichtfelder
#: aendern; h713-tv prueft sie und verwirft, was es nicht kennt.
SATZ_VERSION = 1


def _preset_satz(best: quellen.Datenbestand, eingang: str, modus: str) -> dict:
    """Eine Preset-Zeile, so wie h713-tv sie senden muss."""
    bm = preset(best, eingang, modus)
    nummer, eigene = firmware_modus(modus)
    index = bm.werte.get("gamma")
    return {
        "name": modus,
        "modus": nummer,
        "modus_eigen": eigene,
        "quelle": bm.herkunft,
        "regler": {g: rpc_argument(bm.werte[g]) for g in PRESET_GROESSEN
                   if g in bm.werte},
        "weitere": {g: bm.werte[g] for g in WEITERE_GROESSEN if g in bm.werte},
        "gamma_index": index,
        "gamma_exponent": gamma_exponent(best, index) if index is not None else None,
    }


def satz(best: quellen.Datenbestand, eingang: str, modus: str,
         lut_pfad: str | None = None, lut_bytes: int = 0,
         lut_sha256: str | None = None) -> dict:
    """Eingang x Bildmodus -> ein Satz, wie ihn h713-tv beim Start liest."""
    dieser = _preset_satz(best, eingang, modus)

    alle = []
    for name in modi(best, eingang):
        try:
            alle.append(_preset_satz(best, eingang, name))
        except KeyError:
            # Ein Modus, den modi() aus der Datenbank kennt, zu dem sich aber
            # keine Werte aufloesen lassen. Er wird weggelassen und nicht
            # geraten -- h713-tv bietet dann eben nur die uebrigen an.
            continue

    return {
        "version": SATZ_VERSION,
        "erzeuger": f"h713-pq {__version__}",
        "daten": str(best.verzeichnis),
        "eingang": eingang,
        "preset": modus,
        "quelle": dieser["quelle"],
        "modus": dieser["modus"],
        "modus_eigen": dieser["modus_eigen"],
        "regler": dieser["regler"],
        "weitere": dieser["weitere"],
        "gamma_index": dieser["gamma_index"],
        "gamma_exponent": dieser["gamma_exponent"],
        "lut": lut_pfad,
        "lut_bytes": lut_bytes,
        "lut_sha256": lut_sha256,
        "presets": alle,
        "fehlende_dateien": list(best.fehlende_dateien),
    }


#: Reihenfolge der Farbtemperatur-Namen, wie sie in pq_colortemp.ini stehen
#: und wie sie pq_picturemode.ini kommentiert
#: ("#colortemperature :0-standard,1-cool,2-warm").
FARBTEMP_NAMEN = ("STANDARD", "COOL", "WARM", "USER")


def _farbtemp_hinweis(best: quellen.Datenbestand, gruppe: str | None, index: int) -> str:
    if gruppe is None:
        return ""
    eintraege = best.farbtemperaturen.get(gruppe, {})
    if index < 0 or index >= len(FARBTEMP_NAMEN):
        return f"Index {index} ausserhalb {FARBTEMP_NAMEN}"
    name = FARBTEMP_NAMEN[index]
    ft = eintraege.get(name)
    if not ft:
        return f"{name}: kein Eintrag in pq_colortemp.ini"
    return (f"{name}: Gain {ft.rgain}/{ft.ggain}/{ft.bgain}, "
            f"Offset {ft.roffset}/{ft.goffset}/{ft.boffset}")


# --------------------------------------------------------------------------
# tvin-Nummerierung: was die Daten hergeben und was nicht
# --------------------------------------------------------------------------

def tvin_zuordnung(best: quellen.Datenbestand) -> list[tuple[int, list[str], list[str]]]:
    """Welche Eingaenge kommen fuer eine tvin-Nummer in Frage?

    Auswertbar ist allein die Menge der Bildmodi: die Datenbank fuehrt je
    ``tvin`` nur die Modi, die dieser Eingang hat. Der Modusname steht in der
    Spalte ``name``, also laesst sich die Modusmenge je tvin mit den
    Sektionen von pq_picturemode.ini vergleichen. Mehrdeutigkeiten bleiben
    stehen -- sie werden nicht geraten.
    """
    aus: list[tuple[int, list[str], list[str]]] = []
    ini_mengen = {sekt: set(m) for sekt, m in best.preset_reihenfolge.items()}
    tvins = sorted({z.tvin for z in best.db_picture_mode})
    for tvin in tvins:
        namen = sorted({z.name for z in best.db_picture_mode if z.tvin == tvin})
        kandidaten = []
        for sekt, menge in sorted(ini_mengen.items()):
            # energy_saving fehlt in der Datenbank durchgaengig; ebenso kennt
            # die Datenbank "custom", das keine INI-Sektion fuehrt. Verglichen
            # wird deshalb der Schnitt beider Modusnamen-Mengen.
            gemeinsam = menge | set(namen)
            fehlt_in_ini = set(namen) - menge - {"custom"}
            fehlt_in_db = menge - set(namen) - {"energy_saving"}
            if not fehlt_in_ini and not fehlt_in_db and gemeinsam:
                kandidaten.append(sekt)
        aus.append((tvin, namen, kandidaten))
    return aus
