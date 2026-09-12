"""zustand.py -- motor_limit auslegen und entscheiden, ob gefahren werden darf.

Dieses Modul liest keine Datei und bewegt nichts. Es bekommt Text und liefert
eine Auslegung plus ein Urteil. Genau deshalb ist es vollstaendig ohne Geraet
testbar -- und die Sicherheitsregeln stehen an einer Stelle statt verstreut.

Was PH14 ist -- und was nicht
-----------------------------
PH14 ist ein BEREICHSWAECHTER, kein Endschalter. Er liest active_level (hier:
HIGH), *solange* die Mechanik im erlaubten Fahrbereich steht; der Rand wird am
WEGFALL des Pegels erkannt.

Belegt (analyse/boot/motor-bereichswaechter-20260912.txt, am Geraet gemessen):

    raw=1 ... step=-204
    raw=0 ... step=-206      <== Rand
    raw=1 ... edge_dn=1 step=-207    (Treiber kehrt um, merkt die Kante, haelt)

Das Umkehren und Kantenmerken macht der Treiber selbst
(motor_run_dn_control()). Dieses Werkzeug baut das NICHT nach. Es muss aber
damit umgehen koennen -- und vor allem erkennen, wann der Treiber gar nicht
umkehren *kann*.

Die Zeile von motor_limit
-------------------------
    1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=1 step=-207
    ^ Stock-Feld: motor_limiter_status(0), also "im Bereich" 1/0

Das erste Feld ist Stock-kompatibel, der Rest kam mit Patch 0154 dazu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AUF = "auf"
AB = "ab"
RICHTUNGEN = (AUF, AB)

#: Wie viele msteps der Treiber hoechstens zurueckfaehrt, um wieder in den
#: Bereich zu kommen (RECOVERY_MAX in motor_run_up_control/_dn_control).
#: Steht in keinem sysfs-Attribut -- deshalb hier, aus dem Treiberquelltext.
ERHOLUNG_MAX = 40


class ZeileUnlesbar(Exception):
    """motor_limit lieferte etwas, das nicht ausgelegt werden kann."""


@dataclass(frozen=True)
class Grenze:
    """Eine ausgelegte Zeile von motor_limit."""

    #: Erstes Feld: was motor_limiter_status(0) sagt. ACHTUNG -- das ist nicht
    #: dasselbe wie "der Geber meldet im Bereich": ohne angeforderten Limiter
    #: liefert die Funktion im Treiber bedingungslos 1. Deshalb ist num
    #: mitzupruefen, nicht nur dieses Feld.
    im_bereich: bool
    num: int                    # angeforderte Limiter-GPIOs (HY310: 1)
    act: int                    # active_level aus dem Geraetebaum (HY310: 1)
    edge_up: bool               # obere Kante gemerkt
    edge_dn: bool               # untere Kante gemerkt
    step: int                   # Zaehlerstand, NICHT die physische Position
    raw: int | None = None      # Rohpegel; None = Feld fehlt (Treiber < 0154)
    up: int | None = None
    dn: int | None = None
    roh: str = ""
    unbekannt: dict[str, str] = field(default_factory=dict)

    @property
    def rohpegel_passt(self) -> bool | None:
        """Liest der Pin den Pegel, der 'im Bereich' bedeutet? None = unbekannt."""
        if self.raw is None or self.raw < 0:
            return None
        return self.raw == self.act

    def kante(self, richtung: str) -> bool:
        return self.edge_up if richtung == AUF else self.edge_dn


def lies_grenze(zeile: str) -> Grenze:
    """'1 up=1 dn=1 num=1 raw=1 act=1 edge_up=0 edge_dn=1 step=-207' auslegen.

    Unbekannte Schluessel werden aufgehoben statt verworfen -- ein kuenftiger
    Treiber darf Felder ergaenzen, ohne dass dieses Werkzeug stehen bleibt.
    Fehlende Pflichtfelder sind dagegen ein Fehler und kein Anlass zum Raten.
    """
    roh = (zeile or "").strip()
    if not roh:
        raise ZeileUnlesbar("motor_limit war leer")

    teile = roh.split()
    try:
        erstes = int(teile[0])
    except ValueError as e:
        raise ZeileUnlesbar(
            f"erstes Feld von motor_limit ist keine Zahl: {teile[0]!r}") from e

    paare: dict[str, str] = {}
    for t in teile[1:]:
        if "=" not in t:
            continue
        k, v = t.split("=", 1)
        paare[k] = v

    def zahl(name: str) -> int | None:
        if name not in paare:
            return None
        try:
            return int(paare[name])
        except ValueError:
            return None

    bekannt = {"up", "dn", "num", "raw", "act", "edge_up", "edge_dn", "step"}
    # Pflichtfelder. Vor Patch 0154 gab motor_limit nur
    # "%d up=%d dn=%d num=%d" aus -- daraus laesst sich weder eine Position
    # noch ein Pegel ableiten, und geraten wird hier nichts. Eine solche Zeile
    # ist deshalb unlesbar, nicht halb lesbar.
    fehlt = [n for n in ("num", "act", "edge_up", "edge_dn", "step")
             if zahl(n) is None]
    if fehlt:
        raise ZeileUnlesbar(
            "motor_limit ohne die Felder " + ", ".join(fehlt)
            + f" -- gelesen wurde: {roh!r}. Erwartet wird das Format ab Patch "
              "0154 (rohpegel-des-endschalters-in-motor-limit-zeigen); davor "
              "gab der Treiber nur 'N up=N dn=N num=N' aus.")

    return Grenze(
        im_bereich=bool(erstes),
        num=zahl("num"),
        act=zahl("act"),
        edge_up=bool(zahl("edge_up")),
        edge_dn=bool(zahl("edge_dn")),
        step=zahl("step"),
        raw=zahl("raw"),
        up=zahl("up"),
        dn=zahl("dn"),
        roh=roh,
        unbekannt={k: v for k, v in paare.items() if k not in bekannt},
    )


# ── Die Sicherheitsregeln ────────────────────────────────────────────────
#
# Eine Regel je Absatz, jede mit ihrem Beleg. Wer eine davon lockert, soll
# hier nachlesen koennen, was sie verhindert hat.

def pruefe(g: Grenze, richtung: str, no_limit: int | None = 0) -> str | None:
    """Darf in diese Richtung gefahren werden? None = ja, sonst der Grund.

    Die Reihenfolge ist nicht beliebig: zuerst kommt, was die Schutzfunktion
    des Treibers ganz ausser Kraft setzt (num, no_limit), dann der gemessene
    Pegel, dann die gemerkten Kanten.
    """
    if richtung not in RICHTUNGEN:
        raise ValueError(f"unbekannte Richtung: {richtung!r}")

    # 1. Ohne angeforderten Bereichswaechter gibt es keinen Schutz.
    #    motor_limiter_status() liefert bei limiter_num == 0 bedingungslos 1
    #    ("im Bereich"), und motor_run_*_control kehrt dann NIE um. Das erste
    #    Feld der Zeile sieht dabei genauso aus wie im gesunden Fall -- es ist
    #    also gerade dann wertlos, wenn es darauf ankaeme.
    if g.num < 1:
        return ("num=0 -- der Treiber hat keinen Bereichswaechter angefordert. "
                "Dann meldet er dauerhaft 'im Bereich' und kehrt am Rand nicht "
                "um; jede Fahrt geht ungebremst bis in den Anschlag.")

    # 2. motor_ctrl_no_limit schaltet die Pruefung ausdruecklich ab.
    #    Im Treiber: `if (!m->no_limit && !motor_limiter_status(...))`.
    #    h713-focus schreibt das Attribut nie -- aber jemand anders kann es
    #    gesetzt haben, und dann ist der Schutz weg.
    if no_limit:
        return ("motor_ctrl_no_limit = 1 -- die Bereichspruefung ist "
                "abgeschaltet, der Treiber kehrt am Rand nicht um. "
                "Erst 'echo 0 > motor_ctrl_no_limit' (von Hand), dann wieder "
                "hier weitermachen.")

    # 3. Der Rohpegel ist die einzige Groesse, die wirklich vom Pin kommt.
    #    Fehlt er (Treiber aelter als 0154) oder ist er -1 (der Treiber konnte
    #    den Pin nicht lesen), faehrt dieses Werkzeug nicht. Beim NTC hat genau
    #    diese Luecke eine erfundene Temperatur aus einem offenen Eingang
    #    erzeugt (analyse/boot/ntc-gpadc-messung-20260911.txt).
    if g.raw is None:
        return ("motor_limit nennt keinen Rohpegel (raw=) -- der Treiber ist "
                "aelter als Patch 0154 oder veraendert. Ohne den Pegel ist "
                "nicht zu sehen, ob der Waechter ueberhaupt etwas liefert. "
                "Anzeigen ja, fahren nein.")
    if g.raw < 0:
        return ("raw=-1 -- der Treiber konnte den Pegel des Waechters nicht "
                "lesen. Damit ist auch das Feld 'im Bereich' ohne Aussage.")

    # 4. Der Rand selbst: in-Bereich ist act (hier HIGH). Faellt der Pegel weg,
    #    steht die Mechanik ausserhalb des erlaubten Fahrbereichs.
    if g.raw != g.act:
        return (f"raw={g.raw}, erwartet wird act={g.act} -- die Mechanik steht "
                f"ausserhalb des Fahrbereichs. Nicht weiterfahren; der Treiber "
                f"raeumt das beim naechsten Befehl selbst oder gar nicht.")

    # 5. Und was der Treiber selbst schon gesehen hat.
    if not g.im_bereich:
        return ("motor_limit meldet 'ausserhalb' (erstes Feld 0), obwohl der "
                "Rohpegel passt -- widerspruechlich. Nicht fahren, sondern "
                "nachsehen.")

    # 6. Die gemerkte Kante in Fahrtrichtung. Der Treiber verwirft solche
    #    Befehle ohnehin still (motor_run_up_dn prueft edge_up/edge_dn vor dem
    #    Einreihen) -- aber still ist genau das Falsche: der Mensch soll
    #    erfahren, dass nichts passiert ist.
    if g.kante(richtung):
        gegen = AB if richtung == AUF else AUF
        return (f"edge_{'up' if richtung == AUF else 'dn'}=1 -- der Rand in "
                f"Richtung '{richtung}' ist gemerkt. Der Treiber verwirft jeden "
                f"weiteren Befehl dorthin. Ein mstep '{gegen}' loescht die "
                f"Kante wieder (der Treiber setzt beim Fahren in die "
                f"Gegenrichtung die andere Kante selbst zurueck).")

    return None


def kante_erreicht(vorher: Grenze, nachher: Grenze, richtung: str) -> bool:
    """Ist waehrend dieses Schritts der Rand in Fahrtrichtung aufgetreten?"""
    return nachher.kante(richtung) and not vorher.kante(richtung)


# ── Was der Zaehlerstand wert ist ────────────────────────────────────────

def zaehler_versatz(back_step: int) -> tuple[int, int]:
    """Um wie viele msteps laufen Zaehler und Mechanik bei EINEM Randereignis
    auseinander? Liefert (typisch, hoechstens).

    Hergang, aus motor_run_dn_control() (aufwaerts spiegelbildlich):
    der Rand-mstep faehrt physisch einen Schritt hinaus, dann k msteps zurueck,
    bis der Waechter wieder passt (k >= 1, hoechstens ERHOLUNG_MAX), dann
    back_step weitere msteps hinein. Am Ende steht `m->step_cur--` -- EINMAL,
    egal wie viele msteps die Erholung gekostet hat.

    Physisch also  -1 + k + back_step,  im Zaehler  -1.
    Die Mechanik steht am Ende rund (k + back_step) msteps INNERHALB des
    Randes, der Zaehler aber einen mstep dahinter.

    Gegenprobe an der Messung vom 12.09.: raw fiel bei step=-206 weg, der
    Ruhezustand danach ist step=-207 bei raw=1 -- ein mstep weniger im Zaehler,
    physisch rund back_step+1 = 6 msteps in die andere Richtung.

    Deshalb ist `step` ein Zaehlerstand und keine Position. Nach dem ersten
    Randereignis stimmen die beiden nicht mehr ueberein, und jedes weitere
    vergroessert den Versatz.
    """
    return 1 + back_step, 1 + ERHOLUNG_MAX + back_step
