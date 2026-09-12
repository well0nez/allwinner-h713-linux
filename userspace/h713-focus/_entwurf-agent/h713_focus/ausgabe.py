"""ausgabe.py -- druckt. Rechnet nicht, liest nichts, faehrt nichts.

Der Ton ist der von h713-pq: sagen, was gemessen ist, und danebenschreiben,
was nur angenommen ist. Die rohe Zeile von motor_limit steht am Ende jeder
Statusausgabe -- nicht als Ersatz fuer die Auslegung, sondern als Beleg dafuer.
"""

from __future__ import annotations

import json
import sys

from . import geraet as g_mod
from . import zustand
from .fahren import Ergebnis
from .zustand import AB, AUF, Grenze


def melde(text: str = "") -> None:
    """Zwischenmeldung. Wird sofort ausgegeben -- der Mensch liest mit."""
    print(text, flush=True)


def fehler(text: str) -> None:
    print(f"h713-focus: {text}", file=sys.stderr, flush=True)


def _ja_nein(b: bool, ja: str, nein: str) -> str:
    return ja if b else nein


def _bereichstext(g: Grenze) -> str:
    passt = g.rohpegel_passt
    if passt is None:
        return "unbekannt -- der Treiber nennt keinen brauchbaren Rohpegel"
    if passt:
        return "im Fahrbereich"
    return "AUSSERHALB des Fahrbereichs (der Pegel ist weggefallen)"


def drucke_status(ger: g_mod.Geraet, g: Grenze, p: g_mod.Parameter,
                  no_limit: int | None) -> None:
    print("Fokusmotor")
    print(f"  sysfs           {ger.basis}")
    if ger.herkunft:
        print(f"                  ({ger.herkunft})")
    print()

    print("Bereichswaechter -- PH14, ein Pin fuer beide Richtungen")
    if g.raw is None:
        print("  Rohpegel        nicht vorhanden (Treiber aelter als Patch 0154)")
    elif g.raw < 0:
        print("  Rohpegel        -1 -- der Treiber konnte den Pin nicht lesen")
    else:
        print(f"  Rohpegel        {g.raw}   "
              f"(act={g.act} bedeutet 'im Bereich')")
    print(f"  Auslegung       {_bereichstext(g)}")
    if g.num < 1:
        print("  Limiter         num=0  -- KEIN Waechter angefordert. Der Treiber")
        print("                  meldet dann dauerhaft 'im Bereich' und kehrt")
        print("                  am Rand nicht um. Fahren ist gesperrt.")
    else:
        print(f"  Limiter         num={g.num}  (angefordert)")
    print(f"  Kante aufwaerts {_ja_nein(g.edge_up, 'GEMERKT -- aufwaerts gesperrt', 'frei')}")
    print(f"  Kante abwaerts  {_ja_nein(g.edge_dn, 'GEMERKT -- abwaerts gesperrt', 'frei')}")
    if no_limit is None:
        print(f"  Pruefung        {g_mod.ATTR_NO_LIMIT} nicht lesbar")
    elif no_limit:
        print(f"  Pruefung        {g_mod.ATTR_NO_LIMIT} = 1  -- ABGESCHALTET.")
        print("                  Der Treiber kehrt am Rand NICHT um. Fahren ist")
        print("                  gesperrt, bis das jemand von Hand auf 0 setzt.")
    else:
        print(f"  Pruefung        {g_mod.ATTR_NO_LIMIT} = 0  (Bereichspruefung aktiv)")
    print()

    typisch, hoechstens = zustand.zaehler_versatz(p.back_step)
    print("Position")
    print(f"  Zaehlerstand    {g.step} msteps")
    print(f"  Bezugspunkt     der Stand beim Laden des Moduls (step=0), nicht")
    print(f"                  der Rand und nicht die Mechanik.")
    print(f"  Versatz je Rand rund {typisch} msteps, hoechstens {hoechstens}")
    print(f"                  -- nach einem Randereignis zaehlt der Treiber einen")
    print(f"                  mstep weiter, faehrt aber back_step+1 msteps zurueck")
    print(f"                  in den Bereich. Zaehler und Mechanik laufen dabei")
    print(f"                  auseinander; jeder weitere Rand vergroessert das.")
    print()

    print("Fahren")
    for richtung, wort in ((AUF, "aufwaerts"), (AB, "abwaerts ")):
        grund = zustand.pruefe(g, richtung, no_limit)
        if grund is None:
            print(f"  {wort}       erlaubt")
        else:
            print(f"  {wort}       GESPERRT")
            for zeile in umbruch(grund, 64):
                print(f"                  {zeile}")
    print()

    print("Parameter (aus sysfs gelesen, soweit vorhanden)")
    zeilen = [
        (g_mod.ATTR_STEP_NUM, p.step_num, "Phasenschritte je Folge"),
        (g_mod.ATTR_CYCLE, p.cycle, "Folgen je mstep"),
        (g_mod.ATTR_CTRL_TIME, p.ctrl_time_ms, "ms je Phasenwechsel"),
        (g_mod.ATTR_STEP_DELAY, p.step_delay_ms, "ms je Schritt (nur bipolar)"),
        (g_mod.ATTR_BACK_STEP, p.back_step, "msteps zurueck nach dem Rand"),
    ]
    for name, wert, was in zeilen:
        vermerk = "   [Vorgabe, nicht gelesen]" if name in p.geraten else ""
        print(f"  {name:<18} {wert:<5} {was}{vermerk}")
    print(f"  ein mstep          ~{p.mstep_ms:.0f} ms   "
          f"({p.cycle} x {p.step_num} x {p.ctrl_time_ms} ms, obere Schaetzung)")
    print()

    if g.unbekannt:
        print("Unbekannte Felder in motor_limit (der Treiber ist neuer als dieses")
        print("Werkzeug -- sie werden nur weitergereicht, nicht ausgelegt):")
        print("  " + " ".join(f"{k}={v}" for k, v in g.unbekannt.items()))
        print()

    print(f"motor_limit (roh)  {g.roh}")


def umbruch(text: str, breite: int) -> list[str]:
    """Einen Fliesstext auf eine Breite umbrechen."""
    worte = text.split()
    zeilen: list[str] = []
    aktuell = ""
    for w in worte:
        if aktuell and len(aktuell) + 1 + len(w) > breite:
            zeilen.append(aktuell)
            aktuell = w
        else:
            aktuell = f"{aktuell} {w}".strip()
    if aktuell:
        zeilen.append(aktuell)
    return zeilen


def status_satz(ger: g_mod.Geraet, g: Grenze, p: g_mod.Parameter,
                no_limit: int | None) -> dict:
    """Maschinenlesbarer Satz -- ein JSON-Objekt, wie h713-pq show --json.

    Gedacht fuer Skripte und fuer die Tests. Die Schluessel sind fest; was ein
    Leser nicht kennt, verwirft er.
    """
    typisch, hoechstens = zustand.zaehler_versatz(p.back_step)
    return {
        "version": 1,
        "erzeuger": "h713-focus",
        "sysfs": str(ger.basis),
        "herkunft": ger.herkunft,
        "roh": g.roh,
        "im_bereich": g.im_bereich,
        "raw": g.raw,
        "act": g.act,
        "rohpegel_passt": g.rohpegel_passt,
        "num": g.num,
        "edge_up": g.edge_up,
        "edge_dn": g.edge_dn,
        "step": g.step,
        "no_limit": no_limit,
        "darf_auf": zustand.pruefe(g, AUF, no_limit) is None,
        "darf_ab": zustand.pruefe(g, AB, no_limit) is None,
        "grund_auf": zustand.pruefe(g, AUF, no_limit),
        "grund_ab": zustand.pruefe(g, AB, no_limit),
        "parameter": {
            "step_num": p.step_num,
            "cycle": p.cycle,
            "ctrl_time_ms": p.ctrl_time_ms,
            "step_delay_ms": p.step_delay_ms,
            "back_step": p.back_step,
            "mstep_ms": round(p.mstep_ms, 1),
            "geraten": list(p.geraten),
        },
        "zaehler_versatz_je_rand": {"typisch": typisch, "hoechstens": hoechstens},
        "unbekannte_felder": g.unbekannt,
    }


def drucke_satz(satz: dict) -> None:
    print(json.dumps(satz, ensure_ascii=False, sort_keys=True))


ABSCHLUSS = {
    "fertig": "fertig",
    "rand": "RAND ERREICHT",
    "ausserhalb": "RAND ERREICHT (Rohpegel weggefallen)",
    "gesperrt": "nicht gefahren",
    "abbruch": "ABGEBROCHEN",
    "zeit": "Frist abgelaufen",
    "verworfen": "Befehl verworfen",
    "trocken": "Trockenlauf",
}


def drucke_ergebnis(erg: Ergebnis) -> None:
    print()
    print(f"Ergebnis: {ABSCHLUSS.get(erg.grund, erg.grund)}")
    for zeile in umbruch(erg.text, 72):
        print(f"  {zeile}")
    if erg.grund != "trocken":
        print(f"  gefahren        {erg.gefahren} von {erg.gewollt} msteps "
              f"(im Zaehler)")
        if erg.start and erg.ende:
            print(f"  Zaehler         {erg.start.step} -> {erg.ende.step}")
        if erg.rand_bei is not None:
            print(f"  Rand bei        step={erg.rand_bei}")
            for zeile in umbruch(rand_erlaeuterung(erg.grund), 56):
                print(f"                  {zeile}")


def rand_erlaeuterung(grund: str) -> str:
    """Was der gemeldete Randstand genau ist -- das haengt davon ab, welchen
    Moment der Lesevorgang getroffen hat.

    Der Treiber setzt die Kante erst NACH seiner Erholungsfahrt und laesst den
    Zaehler dabei einen mstep weiterlaufen. Wer den Wegfall des Pegels sieht,
    liest deshalb einen mstep weniger als wer die fertige Kante sieht. Beides
    ist richtig; welches von beidem es war, gehoert dazugeschrieben.
    """
    if grund == "ausserhalb":
        return "Zaehlerstand in dem Moment, als der Pegel wegfiel"
    return ("Zaehlerstand nach der Umkehr; der Wegfall des Pegels lag einen "
            "mstep davor")
