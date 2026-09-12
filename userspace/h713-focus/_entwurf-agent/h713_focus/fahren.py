"""fahren.py -- der bewachte Fahrlauf.

Ein Lauf ist: kleine Haeppchen, vor jedem Haeppchen pruefen, nach jedem
Haeppchen nachsehen, bei jedem Haeppchen eine Zeile ausgeben, und jederzeit
abbrechbar. Das Umkehren am Rand macht der Treiber; dieses Modul erkennt, dass
es passiert ist, und hoert dann auf.

Die vier Sicherungen dieses Moduls
----------------------------------
1. **Nie blind.** Vor jedem Haeppchen wird motor_limit gelesen und durch
   zustand.pruefe() geschickt; danach noch einmal.
2. **Harte Obergrenze je Lauf** (LAUF_MAX_HART), auch wenn der Waechter
   schweigt. Ein Waechter, der nichts meldet, ist kein Beweis dafuer, dass
   noch Weg da ist.
3. **Abbruch.** Strg-C wird waehrend des Laufs abgefangen: die Warteschlange
   wird geleert und der Lauf endet geordnet, statt mitten in einem Haeppchen
   den Prozess zu verlassen.
4. **Ende bei jedem Zweifel.** Rand erreicht, Rohpegel weg, Befehl verworfen,
   Frist abgelaufen -- jedes davon beendet den Lauf, keines wird ausgesessen.
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass, field

from . import geraet as g_mod
from . import zustand
from .zustand import AUF, Grenze

#: Absolute Obergrenze fuer einen einzelnen Lauf, in msteps. Nicht ueberschreibbar.
#:
#: Bezugsgroessen: der einzige gemessene Weg bis an einen Rand sind 206 msteps
#: (12.09., unterer Rand). Der Geraetebaum nennt motor-step-num-Gesamtweg 800
#: (MOTOR_STEP_TOTAL) -- diese Zahl ist am Geraet NICHT geprueft. 400 ist das
#: Doppelte des Gemessenen und die Haelfte des Behaupteten. Wird innerhalb von
#: 400 msteps kein Rand gefunden, ist das ein Befund und kein Grund
#: weiterzufahren.
LAUF_MAX_HART = 400

#: Vorgabe fuer die Haeppchengroesse. 2 msteps ist das Raster, in dem die
#: Messung vom 12.09. den Rand gefunden hat -- klein genug, um mitzulesen.
SCHRITT_VORGABE = 2

#: Wartetakt beim Nachsehen, ms.
TAKT_MS = 25

#: Sicherheitsfaktor auf die gerechnete Fahrzeit, bevor eine Frist ablaeuft.
FRIST_FAKTOR = 1.5
FRIST_ZUSCHLAG_MS = 300


class Abbruch:
    """Faengt SIGINT waehrend eines Laufs ab, statt den Prozess zu verlassen."""

    def __init__(self) -> None:
        self.gesetzt = False
        self._alt = None

    def __enter__(self) -> "Abbruch":
        def haendler(signum, rahmen):      # noqa: ARG001
            self.gesetzt = True
        try:
            self._alt = signal.signal(signal.SIGINT, haendler)
        except ValueError:
            # Nicht im Hauptthread -- dann gibt es eben keinen Handler.
            self._alt = None
        return self

    def __exit__(self, *_) -> None:
        if self._alt is not None:
            signal.signal(signal.SIGINT, self._alt)


@dataclass
class Haeppchen:
    """Ein einzelner Schreibvorgang mit dem, was danach zu sehen war."""
    msteps: int
    wort: int
    vorher: Grenze
    nachher: Grenze
    wie: str


@dataclass
class Ergebnis:
    richtung: str
    gewollt: int
    gefahren: int = 0
    grund: str = "fertig"
    text: str = ""
    start: Grenze | None = None
    ende: Grenze | None = None
    #: Zaehlerstand, bei dem der Rohpegel weggefallen bzw. die Kante aufgetreten
    #: ist. Das ist der Messwert, um den es bei 'range' geht.
    rand_bei: int | None = None
    haeppchen: list[Haeppchen] = field(default_factory=list)

    @property
    def rand_gefunden(self) -> bool:
        return self.grund in ("rand", "ausserhalb")


def lies_grenze(ger: g_mod.Geraet) -> Grenze:
    return zustand.lies_grenze(ger.lies(g_mod.ATTR_LIMIT))


def _still(*_a, **_k) -> None:
    pass


def _frist_ms(n: int, p: g_mod.Parameter) -> float:
    """Wie lange darf ein Haeppchen von n msteps hoechstens dauern?

    Gerechnet wird der schlimmste Fall, den der Treiber selbst vorsieht: die n
    msteps plus eine volle Erholungsfahrt (ERHOLUNG_MAX) plus back_step, mal
    Sicherheitsfaktor. Eine zu knappe Frist waere ein Abbruch mitten in einer
    Bewegung -- das waere schlechter als eine Sekunde zu lange zu warten.
    """
    msteps = n + zustand.ERHOLUNG_MAX + p.back_step
    return msteps * p.mstep_ms * FRIST_FAKTOR + FRIST_ZUSCHLAG_MS


def _warte_auf_ruhe(ger: g_mod.Geraet, p: g_mod.Parameter,
                    ab: Abbruch) -> Grenze | None:
    """Warten, bis der Treiber seine Erholungsfahrt beendet hat.

    Wer ``raw=0`` gesehen hat, hat einen ZWISCHENZUSTAND gesehen: der Pegel ist
    weg, der Treiber faehrt gerade zurueck, der Zaehler ist noch nicht
    weitergelaufen und die Kante noch nicht gesetzt. Wer in diesem Moment den
    naechsten Befehl schickt oder den Zustand als Ergebnis meldet, beschreibt
    etwas, das es eine Zehntelsekunde spaeter nicht mehr gibt.

    Liefert die Ruhelage, oder None, wenn der Treiber nicht in den Bereich
    zurueckgekommen ist -- auch das ist ein Befund (er behauptet die Kante dann
    nach ERHOLUNG_MAX vergeblichen msteps einfach).
    """
    msteps = zustand.ERHOLUNG_MAX + p.back_step + 2
    ende = time.monotonic() + (msteps * p.mstep_ms * FRIST_FAKTOR
                               + FRIST_ZUSCHLAG_MS) / 1000.0
    while True:
        if ab.gesetzt:
            return None
        try:
            jetzt = lies_grenze(ger)
        except (OSError, zustand.ZeileUnlesbar):
            return None
        if jetzt.rohpegel_passt is True:
            return jetzt
        if time.monotonic() >= ende:
            return None
        time.sleep(TAKT_MS / 1000.0)


def _warte(ger: g_mod.Geraet, richtung: str, vorher: Grenze, erwartet: int,
           frist_ms: float, ab: Abbruch) -> tuple[Grenze, str]:
    """Auf das Ende eines Haeppchens warten. Liefert (Zustand, Grund).

    Gruende: fertig | rand | ausserhalb | abbruch | zeit

    Warum ueberhaupt gewartet werden muss: motor_ctrl reiht nur ein und stoesst
    einen Workqueue-Handler an (motor_run_up_dn -> queue_work). Der Schreibaufruf
    kehrt sofort zurueck, die Mechanik laeuft danach noch. Wer sofort wieder
    schreibt, faehrt in eine Bewegung hinein, die er nicht gesehen hat.
    """
    ende = time.monotonic() + frist_ms / 1000.0
    jetzt = vorher
    while True:
        if ab.gesetzt:
            return jetzt, "abbruch"
        try:
            jetzt = lies_grenze(ger)
        except (OSError, zustand.ZeileUnlesbar):
            # Ein misslungener Lesevorgang ist kein Grund weiterzufahren.
            return jetzt, "zeit"

        # Reihenfolge: der Rand zuerst. Trifft das letzte mstep eines
        # Haeppchens den Rand, ist der Zaehler zufaellig auch am Ziel -- dann
        # ist "rand" die richtige Meldung, nicht "fertig".
        if zustand.kante_erreicht(vorher, jetzt, richtung):
            return jetzt, "rand"
        if jetzt.rohpegel_passt is False:
            return jetzt, "ausserhalb"
        if jetzt.step == erwartet:
            return jetzt, "fertig"
        if time.monotonic() >= ende:
            return jetzt, "zeit"
        time.sleep(TAKT_MS / 1000.0)


def lauf(ger: g_mod.Geraet, richtung: str, anzahl: int, *,
         schritt: int = SCHRITT_VORGABE,
         hoechstens: int | None = None,
         melde=_still,
         param: g_mod.Parameter | None = None) -> Ergebnis:
    """``anzahl`` msteps in ``richtung`` fahren -- bewacht, in Haeppchen.

    Liefert immer ein Ergebnis; geworfen wird nur bei Bedienfehlern
    (unbekannte Richtung, unsinnige Schrittweite) und bei I/O.
    """
    if richtung not in zustand.RICHTUNGEN:
        raise ValueError(f"unbekannte Richtung: {richtung!r}")
    if not 1 <= schritt <= g_mod.MSTEPS_JE_BEFEHL_MAX:
        raise ValueError(
            f"Schrittweite {schritt} ausserhalb 1..{g_mod.MSTEPS_JE_BEFEHL_MAX}. "
            f"Der Treiber kuerzt alles darueber still auf "
            f"{g_mod.MSTEPS_JE_BEFEHL_MAX} (MOVE_CLAMP_MAX in motor_run_up_dn).")

    deckel = LAUF_MAX_HART if hoechstens is None else min(hoechstens, LAUF_MAX_HART)
    if anzahl < 1:
        raise ValueError("anzahl muss mindestens 1 sein")

    erg = Ergebnis(richtung=richtung, gewollt=min(anzahl, deckel))
    if anzahl > deckel:
        melde(f"  Hinweis: {anzahl} msteps auf {deckel} gekuerzt "
              f"(harte Obergrenze fuer einen Lauf).")

    param = param or ger.parameter()
    cmd = g_mod.CMD_AUF if richtung == AUF else g_mod.CMD_AB
    vorzeichen = 1 if richtung == AUF else -1
    no_limit = ger.no_limit()

    erg.start = erg.ende = lies_grenze(ger)

    # -- Trockenlauf: pruefen, den Plan zeigen, nichts schreiben -------------
    if ger.trocken:
        grund = zustand.pruefe(erg.start, richtung, no_limit)
        if grund:
            erg.grund, erg.text = "gesperrt", grund
            return erg
        n = min(schritt, erg.gewollt)
        # Derselbe Weg wie im Ernstfall: befehl() schreibt im Trockenlauf
        # nichts, sondern merkt das Wort in ger.geplant vor. So wird genau das
        # gezeigt, was sonst geschrieben wuerde -- und nicht etwas daneben
        # Gerechnetes.
        wort = ger.befehl(cmd, n)
        erg.grund = "trocken"
        erg.text = (
            f"Trockenlauf: es wuerde {erg.gewollt} msteps '{richtung}' fahren, "
            f"in Haeppchen zu {schritt}. Der erste Schreibvorgang waere "
            f"'{wort}' nach {g_mod.ATTR_CTRL} "
            f"(= ({cmd} << 8) | {n}). Geschrieben wurde nichts.")
        return erg

    with Abbruch() as ab:
        rest = erg.gewollt
        while rest > 0:
            if ab.gesetzt:
                erg.grund, erg.text = "abbruch", "abgebrochen (Strg-C)"
                break

            vorher = lies_grenze(ger)
            erg.ende = vorher
            grund = zustand.pruefe(vorher, richtung, no_limit)
            if grund:
                erg.grund, erg.text = "gesperrt", grund
                break

            n = min(schritt, rest)
            erwartet = vorher.step + vorzeichen * n
            wort = ger.befehl(cmd, n)
            nachher, wie = _warte(ger, richtung, vorher, erwartet,
                                  _frist_ms(n, param), ab)
            erg.ende = nachher
            gefahren = abs(nachher.step - vorher.step)
            erg.gefahren += gefahren
            rest -= n
            erg.haeppchen.append(Haeppchen(n, wort, vorher, nachher, wie))

            melde(f"  {richtung:>3} {n:2d} msteps -> step={nachher.step:<6d} "
                  f"raw={_rohtext(nachher)} "
                  f"edge_up={int(nachher.edge_up)} edge_dn={int(nachher.edge_dn)}"
                  f"{'' if wie == 'fertig' else '   [' + wie + ']'}")

            if wie == "rand":
                erg.grund = "rand"
                erg.rand_bei = nachher.step
                erg.text = (
                    f"Rand in Richtung '{richtung}' erreicht: der Treiber hat "
                    f"umgekehrt und die Kante gemerkt "
                    f"(edge_{'up' if richtung == AUF else 'dn'}=1).")
                break
            if wie == "ausserhalb":
                erg.grund = "ausserhalb"
                erg.rand_bei = nachher.step
                erg.text = (
                    f"Der Rohpegel ist weggefallen (raw={nachher.raw}, "
                    f"act={nachher.act}) -- die Mechanik steht am Bereichsrand. "
                    f"Angehalten, bevor der Treiber selbst nachzieht.")
                # Das Gesehene ist ein Zwischenzustand. Erst die Ruhelage
                # abwarten, sonst wird eine Momentaufnahme als Ergebnis
                # gemeldet -- und der naechste Befehl liefe in eine Bewegung
                # hinein, die noch laeuft.
                melde("  Der Treiber faehrt zurueck; warte auf die Ruhelage ...")
                ruhe = _warte_auf_ruhe(ger, param, ab)
                if ruhe is not None:
                    erg.ende = ruhe
                    erg.text += (f" Ruhelage danach: step={ruhe.step}, "
                                 f"edge_up={int(ruhe.edge_up)} "
                                 f"edge_dn={int(ruhe.edge_dn)}.")
                else:
                    erg.text += (" Der Treiber ist NICHT in den Bereich "
                                 "zurueckgekehrt -- nachsehen, bevor hier "
                                 "irgendetwas weiterfaehrt.")
                break
            if wie == "abbruch":
                erg.grund, erg.text = "abbruch", "abgebrochen (Strg-C)"
                break
            if wie == "zeit":
                if gefahren == 0:
                    erg.grund = "verworfen"
                    erg.text = (
                        "Der Zaehler hat sich nicht bewegt -- der Treiber hat "
                        "den Befehl verworfen. Haeufigster Grund: eine gemerkte "
                        "Kante in Fahrtrichtung, die zwischen Pruefung und "
                        "Schreibvorgang gesetzt wurde.")
                else:
                    erg.grund = "zeit"
                    erg.text = (
                        f"Die Frist fuer dieses Haeppchen ist abgelaufen "
                        f"({gefahren} von {n} msteps im Zaehler). Angehalten.")
                break
        else:
            erg.grund, erg.text = "fertig", f"{erg.gefahren} msteps gefahren."

        if erg.grund == "abbruch":
            _notbremse(ger, melde)

    return erg


def _rohtext(g: Grenze) -> str:
    if g.raw is None:
        return "?"
    return str(g.raw)


def _notbremse(ger: g_mod.Geraet, melde=_still) -> None:
    """Warteschlange leeren. Der laufende mstep laeuft zu Ende."""
    try:
        ger.leeren()
        melde("  Warteschlange geleert. Der mstep, der gerade lief, laeuft "
              "noch zu Ende -- der Treiber kann ihn nicht abbrechen.")
    except (OSError, g_mod.MotorFehler) as e:
        melde(f"  Warteschlange konnte nicht geleert werden: {e}")


def stopp(ger: g_mod.Geraet, melde=_still) -> Grenze:
    """Sicherer Abbruch von aussen: leeren und den Zustand zurueckgeben."""
    _notbremse(ger, melde)
    return lies_grenze(ger)
