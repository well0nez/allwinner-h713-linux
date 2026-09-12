"""cli.py -- Befehlszeile von h713-focus.

h713-focus bewegt echte Mechanik. Deshalb gilt hier, quer durch alle
Unterbefehle:

  * vor jeder Bewegung wird motor_limit gelesen und danach noch einmal,
  * jeder Lauf hat eine harte Obergrenze, auch wenn der Waechter schweigt,
  * motor_ctrl_no_limit wird nie geschrieben (die Sperre sitzt in geraet.py),
  * das Kernelmodul wird nie selbst geladen -- es wird gesagt, wie man es
    sicher laedt (homing=0),
  * Strg-C leert die Warteschlange und beendet den Lauf geordnet.
"""

from __future__ import annotations

import argparse
import sys

from . import ausgabe, fahren
from . import geraet as g_mod
from . import zustand
from .zustand import AB, AUF

BESCHREIBUNG = """\
Den Fokusmotor des HY310 bedienen (Treiber hy310-focus-motor).

PH14 ist ein BEREICHSWAECHTER, kein Endschalter: er liest HIGH, solange die
Mechanik im erlaubten Fahrbereich steht. Der Rand wird am WEGFALL des Pegels
erkannt. Das Umkehren und Kantenmerken macht der Treiber selbst; dieses
Werkzeug erkennt, dass es passiert ist, und hoert dann auf.
"""

BEISPIELE = """\
Beispiele:
  h713-focus status                     Position und Zustand, menschenlesbar
  h713-focus status --json              derselbe Zustand als ein JSON-Objekt
  h713-focus down 20                    20 msteps abwaerts, in Haeppchen zu 2
  h713-focus up 6 --schritt 1           6 msteps aufwaerts, einzeln
  h713-focus down 20 --trocken          nur zeigen, was geschrieben wuerde
  h713-focus goto -150                  auf den Zaehlerstand -150 fahren
  h713-focus range                      den UNTEREN Rand suchen und vermessen
  h713-focus range --auch-oben --ja     beide Raender (Vorsicht, siehe README)
  h713-focus stop                       Warteschlange leeren, Bewegung beenden
                                        (auch als "flush", wie im Vorlaeufer)

Abwaerts ist die Richtung WEG vom mechanischen Anschlag. Wer nicht weiss, wo
die Mechanik steht, faehrt zuerst abwaerts -- nie zuerst aufwaerts.
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="h713-focus",
        description=BESCHREIBUNG,
        epilog=BEISPIELE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--sysfs", metavar="PFAD", default=None,
                   help="Verzeichnis des Motorknotens. Ohne Angabe wird gesucht: "
                        "$H713_FOCUS_SYSFS, dann was an den Treiber "
                        f"{g_mod.TREIBER} gebunden ist, dann /sys/bus/platform/"
                        "devices/*motor*. Auch fuer Attrappen (siehe tests/).")
    p.add_argument("--trocken", action="store_true",
                   help="nichts schreiben, nur zeigen, was geschrieben wuerde")
    unter = p.add_subparsers(dest="befehl", required=True)

    s = unter.add_parser("status", help="Position und Zustand anzeigen (liest nur)")
    s.add_argument("--json", action="store_true",
                   help="ein JSON-Objekt auf stdout statt der Tabelle")

    for name, hilfe in (("up", "msteps aufwaerts fahren (Richtung Anschlag!)"),
                        ("down", "msteps abwaerts fahren")):
        f = unter.add_parser(name, help=hilfe)
        f.add_argument("msteps", type=int, help="wie viele msteps")
        _fahrargumente(f)

    z = unter.add_parser("goto", help="auf einen Zaehlerstand fahren")
    z.add_argument("ziel", type=int, help="Zielstand von motor_limit step=")
    _fahrargumente(z)

    r = unter.add_parser(
        "range",
        help="Raender suchen und den nutzbaren Fahrweg vermessen")
    r.add_argument("--auch-oben", action="store_true", dest="auch_oben",
                   help="nach dem unteren auch den OBEREN Rand anfahren. "
                        "Dort liegt der mechanische Anschlag -- Vorgabe ist aus.")
    r.add_argument("--max", type=int, default=300, dest="hoechstens",
                   metavar="N",
                   help=f"msteps je Richtung, Vorgabe 300, hoechstens "
                        f"{fahren.LAUF_MAX_HART}")
    r.add_argument("--schritt", type=int, default=fahren.SCHRITT_VORGABE,
                   metavar="N", help="msteps je Schreibvorgang (Vorgabe 2)")
    r.add_argument("--ja", action="store_true",
                   help="nicht nachfragen (noetig ohne Terminal)")

    # "flush" hiess der Befehl im Vorlaeufer legacy/tools/focus. Er bleibt als
    # Zweitname, damit die Handbewegung weiter stimmt; "stop" ist der Name, der
    # sagt, wofuer man ihn im Zweifel braucht.
    unter.add_parser(
        "stop", aliases=["flush"],
        help="Warteschlange leeren und den Zustand zeigen (sicherer Abbruch)")
    return p


def _fahrargumente(p: argparse.ArgumentParser) -> None:
    p.add_argument("--schritt", type=int, default=fahren.SCHRITT_VORGABE,
                   metavar="N",
                   help=f"msteps je Schreibvorgang, 1..{g_mod.MSTEPS_JE_BEFEHL_MAX} "
                        f"(Vorgabe {fahren.SCHRITT_VORGABE}). Der Treiber kuerzt "
                        f"alles darueber still.")
    p.add_argument("--max", type=int, default=None, dest="hoechstens",
                   metavar="N",
                   help=f"harte Obergrenze fuer diesen Lauf "
                        f"(hoechstens {fahren.LAUF_MAX_HART})")


# ── Hilfen ────────────────────────────────────────────────────────────────

def _bestaetigt(frage: str, ja: bool) -> bool:
    if ja:
        return True
    if not sys.stdin.isatty():
        ausgabe.fehler("ohne Terminal muss --ja angegeben werden")
        return False
    try:
        antwort = input(frage + " [ja/nein] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return antwort.strip().lower() in ("ja", "j")


def _oeffne(args) -> g_mod.Geraet | None:
    try:
        return g_mod.oeffne(args.sysfs, trocken=args.trocken)
    except g_mod.ModulFehlt as e:
        ausgabe.fehler(str(e))
        return None
    except g_mod.MotorFehler as e:
        ausgabe.fehler(str(e))
        return None


def _zustand(ger: g_mod.Geraet):
    """(Grenze, Parameter, no_limit) -- oder None bei unlesbarem motor_limit."""
    try:
        g = fahren.lies_grenze(ger)
    except zustand.ZeileUnlesbar as e:
        ausgabe.fehler(str(e))
        return None
    except OSError as e:
        ausgabe.fehler(f"{ger.basis / g_mod.ATTR_LIMIT}: {e.strerror}")
        return None
    return g, ger.parameter(), ger.no_limit()


#: Gruende, bei denen ein Lauf nicht das getan hat, was verlangt war.
_NICHT_GEWOLLT = ("gesperrt", "abbruch", "zeit", "verworfen")


# ── Unterbefehle ──────────────────────────────────────────────────────────

def _befehl_status(ger, args) -> int:
    z = _zustand(ger)
    if z is None:
        return 2
    g, p, no_limit = z
    if args.json:
        ausgabe.drucke_satz(ausgabe.status_satz(ger, g, p, no_limit))
        return 0
    ausgabe.drucke_status(ger, g, p, no_limit)
    return 0


def _fahre(ger, richtung: str, msteps: int, args) -> int:
    try:
        erg = fahren.lauf(ger, richtung, msteps,
                          schritt=args.schritt,
                          hoechstens=args.hoechstens,
                          melde=ausgabe.melde)
    except ValueError as e:
        ausgabe.fehler(str(e))
        return 2
    except g_mod.Verboten as e:
        ausgabe.fehler(str(e))
        return 2
    except OSError as e:
        ausgabe.fehler(f"{ger.basis}: {e}")
        return 2
    ausgabe.drucke_ergebnis(erg)
    return 1 if erg.grund in _NICHT_GEWOLLT else 0


def _befehl_up(ger, args) -> int:
    if args.msteps < 1:
        ausgabe.fehler("msteps muss mindestens 1 sein")
        return 2
    ausgabe.melde("Aufwaerts ist die Richtung, in der der mechanische Anschlag")
    ausgabe.melde("liegt. Beim ersten anderen Geraeusch: Strg-C.")
    return _fahre(ger, AUF, args.msteps, args)


def _befehl_down(ger, args) -> int:
    if args.msteps < 1:
        ausgabe.fehler("msteps muss mindestens 1 sein")
        return 2
    return _fahre(ger, AB, args.msteps, args)


def _befehl_goto(ger, args) -> int:
    z = _zustand(ger)
    if z is None:
        return 2
    g, _p, _nl = z
    delta = args.ziel - g.step
    if delta == 0:
        ausgabe.melde(f"Der Zaehler steht schon auf {args.ziel}. Nichts zu tun.")
        return 0
    richtung = AUF if delta > 0 else AB
    ausgabe.melde(f"Zaehler {g.step} -> {args.ziel}: {abs(delta)} msteps "
                  f"'{richtung}'.")
    ausgabe.melde("Der Zaehler ist kein Mass fuer die Mechanik -- nach jedem")
    ausgabe.melde("Randereignis laufen beide auseinander (siehe 'status').")
    if richtung == AUF:
        ausgabe.melde("Richtung Anschlag. Beim ersten anderen Geraeusch: Strg-C.")
    return _fahre(ger, richtung, abs(delta), args)


def _befehl_stop(ger, args) -> int:
    try:
        g = fahren.stopp(ger, ausgabe.melde)
    except OSError as e:
        ausgabe.fehler(f"{ger.basis}: {e}")
        return 2
    ausgabe.melde(f"Zustand danach: {g.roh}")
    return 0


def _befehl_range(ger, args) -> int:
    """Die Raender suchen. Abwaerts zuerst -- immer."""
    z = _zustand(ger)
    if z is None:
        return 2
    g, p, no_limit = z

    grund = zustand.pruefe(g, AB, no_limit)
    if grund:
        ausgabe.fehler("abwaerts ist gesperrt, also faengt hier nichts an:")
        ausgabe.fehler(grund)
        return 2

    deckel = min(args.hoechstens, fahren.LAUF_MAX_HART)
    dauer_s = deckel * p.mstep_ms / 1000.0
    ausgabe.melde("Fahrwegvermessung")
    ausgabe.melde(f"  Start          step={g.step}, raw={g.raw}, "
                  f"im Bereich")
    ausgabe.melde(f"  Zuerst         ABWAERTS, hoechstens {deckel} msteps "
                  f"in Haeppchen zu {args.schritt}")
    ausgabe.melde(f"  Dauer          bis zu ~{dauer_s:.0f} s je Richtung "
                  f"(ein mstep ~{p.mstep_ms:.0f} ms)")
    if args.auch_oben:
        ausgabe.melde("  Danach         AUFWAERTS -- dort liegt der mechanische")
        ausgabe.melde("                 Anschlag. Hinhoeren: ein Schrittmotor am")
        ausgabe.melde("                 Anschlag rattert, statt zu ticken.")
    else:
        ausgabe.melde("  Danach         nichts. Der obere Rand wird NICHT")
        ausgabe.melde("                 angefahren (--auch-oben schaltet ihn zu).")
    ausgabe.melde("  Abbruch        Strg-C -- leert die Warteschlange.")
    ausgabe.melde("")

    if not ger.trocken and not _bestaetigt("Fahrt beginnen?", args.ja):
        ausgabe.melde("Nichts getan.")
        return 2

    ausgabe.melde("Abwaerts:")
    unten = fahren.lauf(ger, AB, deckel, schritt=args.schritt,
                        hoechstens=deckel, melde=ausgabe.melde, param=p)
    ausgabe.drucke_ergebnis(unten)

    oben = None
    if args.auch_oben and unten.rand_gefunden and not ger.trocken:
        ausgabe.melde("")
        ausgabe.melde("Aufwaerts (Richtung Anschlag -- hinhoeren!):")
        # Der erste mstep aufwaerts loescht edge_dn im Treiber selbst
        # (motor_run_up_control setzt m->edge_dn = 0). Deshalb ist hier kein
        # Zuruecksetzen von Hand noetig -- und motor_limit wird auch nicht
        # beschrieben: das wuerde BEIDE Kanten loeschen, auch die, die gerade
        # schuetzt.
        schritt_oben = min(args.schritt, 2)
        oben = fahren.lauf(ger, AUF, deckel, schritt=schritt_oben,
                           hoechstens=deckel, melde=ausgabe.melde, param=p)
        ausgabe.drucke_ergebnis(oben)

    _drucke_vermessung(unten, oben, p, deckel, args)
    return 0 if unten.rand_gefunden else 1


def _erlaeutere(grund: str) -> None:
    """Dazuschreiben, welchen Moment der gemeldete Randstand festhaelt."""
    for zeile in ausgabe.umbruch(ausgabe.rand_erlaeuterung(grund), 56):
        ausgabe.melde(f"                 {zeile}")


def _drucke_vermessung(unten, oben, p, deckel, args) -> None:
    typisch, hoechstens = zustand.zaehler_versatz(p.back_step)
    ausgabe.melde("")
    ausgabe.melde("Vermessung")
    if unten.rand_gefunden:
        ausgabe.melde(f"  unterer Rand   step={unten.rand_bei}")
        _erlaeutere(unten.grund)
        if unten.ende:
            ausgabe.melde(f"  Ruhelage       step={unten.ende.step}  "
                          f"(nach der Umkehr des Treibers)")
    else:
        ausgabe.melde(f"  unterer Rand   NICHT gefunden innerhalb von {deckel} "
                      f"msteps ({unten.grund}).")
        ausgabe.melde("                 Das ist ein Befund, kein Grund "
                      "weiterzufahren.")

    if oben is None:
        if args.auch_oben:
            ausgabe.melde("  oberer Rand    nicht angefahren (der untere wurde "
                          "nicht gefunden)")
        else:
            ausgabe.melde("  oberer Rand    nicht angefahren (--auch-oben)")
    elif oben.rand_gefunden:
        ausgabe.melde(f"  oberer Rand    step={oben.rand_bei}")
        _erlaeutere(oben.grund)
    else:
        ausgabe.melde(f"  oberer Rand    NICHT gefunden innerhalb von {deckel} "
                      f"msteps ({oben.grund})")

    if unten.rand_gefunden and oben is not None and oben.rand_gefunden:
        weg = abs(oben.rand_bei - unten.rand_bei)
        ausgabe.melde("")
        ausgabe.melde(f"  Fahrweg        rund {weg} msteps zwischen den beiden")
        ausgabe.melde(f"                 Randereignissen -- im ZAEHLER gemessen.")
        ausgabe.melde(f"                 Der physische Weg ist groesser: das")
        ausgabe.melde(f"                 untere Randereignis hat Zaehler und")
        ausgabe.melde(f"                 Mechanik um rund {typisch} msteps "
                      f"(hoechstens")
        ausgabe.melde(f"                 {hoechstens}) gegeneinander verschoben.")
        ausgabe.melde(f"                 Der Geraetebaum behauptet 800 msteps")
        ausgabe.melde(f"                 (MOTOR_STEP_TOTAL) -- diese Zahl ist am")
        ausgabe.melde(f"                 Geraet nie geprueft worden.")

    if unten.ende is not None and unten.start is not None:
        ausgabe.melde("")
        ausgabe.melde(f"  Zurueck zum Ausgangsstand:  "
                      f"h713-focus goto {unten.start.step}")
        ausgabe.melde("  (nur wenn du das willst -- der Fokus darf auch stehen")
        ausgabe.melde("   bleiben, wo er steht.)")


# ── Einstieg ──────────────────────────────────────────────────────────────

_BEFEHLE = {
    "status": _befehl_status,
    "up": _befehl_up,
    "down": _befehl_down,
    "goto": _befehl_goto,
    "range": _befehl_range,
    "stop": _befehl_stop,
    "flush": _befehl_stop,      # Zweitname aus legacy/tools/focus
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    ger = _oeffne(args)
    if ger is None:
        return 2
    if ger.trocken:
        ausgabe.melde("-- Trockenlauf: es wird nichts geschrieben. --")

    try:
        rueck = _BEFEHLE[args.befehl](ger, args)
    except KeyboardInterrupt:
        # Ausserhalb eines Laufs -- dort faengt fahren.Abbruch selbst ab.
        print()
        ausgabe.fehler("abgebrochen")
        return 1

    if ger.trocken and ger.geplant:
        ausgabe.melde("")
        ausgabe.melde("Was geschrieben worden waere:")
        for name, wert in ger.geplant:
            ausgabe.melde(f"  echo {wert} > {ger.basis / name}")
    return rueck
