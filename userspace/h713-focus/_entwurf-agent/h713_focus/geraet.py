"""geraet.py -- die einzige Naht zum Dateisystem.

Hier wird der sysfs-Knoten des Fokusmotors *gesucht* (nie eingetippt),
gelesen und -- sehr sparsam -- geschrieben. Dieses Modul legt nichts aus und
entscheidet nichts ueber Bewegung; das macht zustand.py bzw. fahren.py.

Warum gesucht und nicht hartkodiert
-----------------------------------
Am 12.09.2026 sind in diesem Projekt zwei Fehler genau daran gescheitert, dass
eine Nummer bzw. ein Pfad aus einem fremden Zusammenhang uebernommen wurde
(eine GPIO-Nummer aus einem anderen System, eine Interrupt-Liste nach der
falschen Bank). Der Knoten heisst bei uns "motor-ctr" und bei Stock
"motor_ctr"; er kann kuenftig anders heissen. Verlaesslich ist nur der
Treibername, und der steht als DRIVER_NAME im Modul selbst.

Suchreihenfolge, von belastbar nach notduerftig:
  1. --sysfs PFAD              (Vorgabe des Aufrufers, auch fuer Attrappen)
  2. $H713_FOCUS_SYSFS
  3. /sys/bus/platform/drivers/hy310-focus-motor/*   <- der Treiber selbst
  4. /sys/bus/platform/devices/*motor*
  5. /sys/devices/platform/*/motor_limit
Jeder Fund muss motor_ctrl UND motor_limit haben, sonst zaehlt er nicht.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path

#: Treibername aus dem Modul (DRIVER_NAME in drivers/misc/hy310-focus-motor.c).
#: Geraetespezifische Dinge behalten "hy310" -- das Werkzeug heisst h713-focus,
#: der Treiber wird NICHT umbenannt (doku/60-offen.md, "Werkzeugnamen").
TREIBER = "hy310-focus-motor"

#: So heisst dasselbe Modul fuer insmod/modprobe/lsmod (Bindestrich -> Unterstrich).
MODUL = "hy310_focus_motor"

# ── Die Attribute des Treibers ────────────────────────────────────────────
ATTR_CTRL = "motor_ctrl"          # schreiben: (richtung << 8) | msteps
ATTR_LIMIT = "motor_limit"        # lesen: der Bereichswaechter
ATTR_NO_LIMIT = "motor_ctrl_no_limit"
ATTR_STEP_NUM = "motor_step_num"
ATTR_CYCLE = "motor_cycle"
ATTR_STEP_DELAY = "motor_step_delay"
ATTR_BACK_STEP = "motor_back_step"
ATTR_CTRL_TIME = "motor_ctrl_time"

#: Ohne diese beiden ist ein Verzeichnis nicht unser Motorknoten.
PFLICHT = (ATTR_CTRL, ATTR_LIMIT)

#: Attribute, die dieses Werkzeug unter keinen Umstaenden schreibt.
#:
#: motor_ctrl_no_limit schaltet im Treiber die Bereichspruefung ab -- die
#: Umkehr in motor_run_up_control()/motor_run_dn_control() haengt woertlich an
#: `if (!m->no_limit && !motor_limiter_status(...))`. Mit no_limit = 1 kehrt der
#: Treiber nie um und fahert bis in den Anschlag. Die Sperre steht hier und nicht
#: in der Befehlszeile, damit auch ein kuenftiger Codepfad sie nicht umgehen kann.
VERBOTEN_SCHREIBEN = frozenset({ATTR_NO_LIMIT})

#: Richtungen. 8 = aufwaerts, 9 = abwaerts -- die "manuellen" Befehle des
#: Herstellerprotokolls (motor_ctrl_store, Faelle 8/9). 1/2 waeren dieselbe
#: Bewegung mit der Autofokus-Zeitgebung: die setzt m->autofocus und laesst den
#: Treiber je Phase busy-waiten (mdelay) statt zu schlafen. Fuer Handbetrieb ist
#: das falsch, deshalb nimmt h713-focus ausschliesslich 8/9.
#: (legacy/tools/focus nimmt 1/2 -- das ist der Grund, warum es hier ersetzt wird.)
CMD_AUF = 8
CMD_AB = 9
CMD_LEEREN = 3          # Warteschlange leeren (motor_flush_queue)

#: Der Treiber begrenzt die msteps je Schreibvorgang auf MOVE_CLAMP_MAX = 18
#: (motor_run_up_dn). Alles darueber wird still auf 18 gekuerzt -- wer 30
#: schreibt, bekommt 18 und merkt es nicht. Deshalb prueft das Werkzeug selbst.
MSTEPS_JE_BEFEHL_MAX = 18

#: Vorgabewerte des Treibers, falls ein Parameterattribut fehlt (z. B. bei einer
#: schmalen Attrappe). Belegt aus dem Geraetebaum (0024/0113) bzw. den
#: DEFAULT_*-Konstanten des Treibers. Wird ein Wert von hier benutzt, sagt das
#: Werkzeug das dazu -- es tut nicht so, als haette es ihn gelesen.
VORGABEN = {
    ATTR_STEP_NUM: 8,        # motor-step-num
    ATTR_CYCLE: 2,           # motor-cycle
    ATTR_CTRL_TIME: 1,       # motor-phase-udelay, ms je Phasenwechsel
    ATTR_STEP_DELAY: 1,      # motor-step-mdelay (nur im bipolaren Pfad benutzt)
    ATTR_BACK_STEP: 5,       # DEFAULT_BACK_STEP
}


class MotorFehler(Exception):
    """Oberklasse aller Fehler dieses Werkzeugs."""


class ModulFehlt(MotorFehler):
    """Der Treiber ist gar nicht da -- Modul nicht geladen oder Knoten aus."""


class KnotenFehlt(MotorFehler):
    """Der Treiber ist da, aber kein gebundenes Geraet mit den Attributen."""


class Verboten(MotorFehler):
    """Es wurde versucht, ein gesperrtes Attribut zu schreiben."""


# ── Suche ─────────────────────────────────────────────────────────────────

def _taugt(p: Path) -> bool:
    return p.is_dir() and all((p / a).exists() for a in PFLICHT)


def _ueber_treiber() -> list[tuple[Path, str]]:
    """Der belastbare Weg: was ist an den Treiber gebunden?"""
    wurzel = Path("/sys/bus/platform/drivers") / TREIBER
    if not wurzel.is_dir():
        return []
    treffer = []
    for eintrag in sorted(wurzel.iterdir()):
        # bind/unbind/uevent/module sind Steuerdateien, keine Geraete.
        if eintrag.name in ("bind", "unbind", "uevent", "module"):
            continue
        if not eintrag.is_symlink():
            continue
        ziel = eintrag.resolve()
        if _taugt(ziel):
            treffer.append((ziel, f"gebunden an den Treiber {TREIBER}"))
    return treffer


def _ueber_namen() -> list[tuple[Path, str]]:
    """Notweg, falls der Treiber nicht (mehr) registriert ist."""
    treffer: list[tuple[Path, str]] = []
    gesehen: set[Path] = set()
    muster = (
        ("/sys/bus/platform/devices/*motor*", "Plattformgeraet mit 'motor' im Namen"),
        ("/sys/devices/platform/*/" + ATTR_LIMIT, "Verzeichnis mit " + ATTR_LIMIT),
    )
    for m, wie in muster:
        for roh in sorted(glob.glob(m)):
            p = Path(roh)
            if p.name == ATTR_LIMIT:
                p = p.parent
            p = p.resolve()
            if p in gesehen or not _taugt(p):
                continue
            gesehen.add(p)
            treffer.append((p, wie))
    return treffer


def treiber_registriert() -> bool:
    """Kennt der Kernel den Treiber ueberhaupt? (Modul geladen oder eingebaut)"""
    return (Path("/sys/bus/platform/drivers") / TREIBER).is_dir()


def modul_geladen() -> bool:
    """Liegt das Modul als Modul im Kernel?"""
    return (Path("/sys/module") / MODUL).is_dir()


LADEHINWEIS = f"""\
So wird es sicher geladen -- homing=0 ist Pflicht:

    modprobe {MODUL} homing=0
    # oder, wenn das Modul als Datei vorliegt:
    insmod /lib/modules/$(uname -r)/kernel/drivers/misc/{TREIBER}.ko homing=0

Warum homing=0: ohne diesen Parameter laeuft beim Laden die Homing-Folge, und
die faehrt bis zu 100 msteps AUFWAERTS -- also in die Richtung, in der der
mechanische Anschlag liegt. Steht die Mechanik schon oben, drueckt das Laden
selbst hinein. (motor_initial_homing(), HOMING_UP_MAX = 100.)

Die Blacklist /etc/modprobe.d/{TREIBER}.conf verhindert nur das *automatische*
Laden; ein ausdrueckliches modprobe/insmod geht trotzdem.

h713-focus laedt das Modul NICHT selbst. Ein Werkzeug, das ungefragt Parameter
waehlt, mit denen sich Mechanik bewegt, ist genau der Fehler, den das hier
vermeiden soll."""


def finde_basis(vorgabe: str | None = None) -> tuple[Path, str]:
    """Liefert (Verzeichnis, wie es gefunden wurde) oder wirft.

    ``vorgabe`` ist --sysfs bzw. $H713_FOCUS_SYSFS und wird nicht hinterfragt --
    das ist der Weg, auf dem die Tests gegen eine Attrappe laufen.
    """
    if not vorgabe:
        vorgabe = os.environ.get("H713_FOCUS_SYSFS") or None
        herkunft_vorgabe = "aus $H713_FOCUS_SYSFS"
    else:
        herkunft_vorgabe = "vorgegeben mit --sysfs"

    if vorgabe:
        p = Path(vorgabe)
        if not p.is_dir():
            raise KnotenFehlt(f"{p}: kein Verzeichnis ({herkunft_vorgabe})")
        fehlt = [a for a in PFLICHT if not (p / a).exists()]
        if fehlt:
            raise KnotenFehlt(
                f"{p}: dort fehlt {', '.join(fehlt)} ({herkunft_vorgabe})")
        return p, herkunft_vorgabe

    for p, wie in _ueber_treiber():
        return p, wie

    if not treiber_registriert():
        raise ModulFehlt(
            f"Der Treiber {TREIBER} ist im Kernel nicht registriert -- das Modul "
            f"{MODUL} ist nicht geladen.\n\n" + LADEHINWEIS)

    for p, wie in _ueber_namen():
        return p, wie + " (Notweg: nichts war an den Treiber gebunden)"

    raise KnotenFehlt(
        f"Der Treiber {TREIBER} ist registriert, aber kein Geraet ist an ihn "
        f"gebunden und es liegt kein Verzeichnis mit {', '.join(PFLICHT)} "
        f"unter /sys/devices/platform.\n"
        f"Steht der Geraetebaum-Knoten motor_ctr auf \"disabled\"? "
        f"(Serie 0024/0142 setzt ihn so.)")


# ── Zugriff ───────────────────────────────────────────────────────────────

@dataclass
class Parameter:
    """Die Zeitparameter des Treibers, wie sie gerade eingestellt sind."""
    step_num: int
    cycle: int
    ctrl_time_ms: int
    step_delay_ms: int
    back_step: int
    #: Attribute, die nicht gelesen werden konnten und aus VORGABEN stammen.
    geraten: tuple[str, ...] = ()

    @property
    def mstep_ms(self) -> float:
        """Dauer eines msteps in ms -- obere Schaetzung.

        Ein mstep ist cycle * step_num Phasenwechsel, und jeder Phasenwechsel
        schlaeft motor_delay_ms(ctrl_time) = usleep_range(800*n, 1000*n) us.
        Die obere Kante dieses Bereichs ist 1,0 ms je ms, also rechnen wir mit
        cycle * step_num * ctrl_time. Mit den Werten des Geraetebaums
        (2 * 8 * 1) sind das 16 ms; die Messung vom 12.09. nennt ~14,4 ms.
        Nach oben zu schaetzen ist hier das Richtige: die Zahl geht nur in
        Wartefristen ein, und eine zu kurze Frist waere ein falscher Abbruch
        mitten in der Bewegung.

        Nur fuer den Schrittmotorpfad (motor-type = 0, so ist dieses Board
        verdrahtet). Beim bipolaren Pfad zaehlt step_delay -- den kennt dieses
        Werkzeug, benutzt ihn aber nicht.
        """
        return max(1.0, self.cycle * self.step_num * self.ctrl_time_ms)


class Geraet:
    """Lesender und (sehr sparsamer) schreibender Zugriff auf den Motorknoten.

    Alle hoeheren Module gehen durch diese Klasse. Wer sie ersetzt -- die Tests
    tun das nicht, die benutzen ein echtes Verzeichnis -- ersetzt das gesamte
    I/O des Werkzeugs.
    """

    def __init__(self, basis: Path, herkunft: str = "", trocken: bool = False):
        self.basis = Path(basis)
        self.herkunft = herkunft
        #: Trockenlauf: lesen ja, schreiben nein. Was geschrieben wuerde, landet
        #: in .geplant und wird gedruckt. Bewegt nichts.
        self.trocken = trocken
        self.geplant: list[tuple[str, str]] = []

    # -- lesen --------------------------------------------------------------

    def hat(self, name: str) -> bool:
        return (self.basis / name).exists()

    def lies(self, name: str) -> str:
        """Ein Attribut lesen. Wirft OSError, wenn es nicht geht."""
        with (self.basis / name).open("r") as f:
            return f.read().strip()

    def lies_int(self, name: str, vorgabe: int | None = None) -> int | None:
        try:
            return int(self.lies(name).split()[0])
        except (OSError, ValueError, IndexError):
            return vorgabe

    def parameter(self) -> Parameter:
        """Die Zeitparameter lesen; was fehlt, kommt aus VORGABEN und wird vermerkt."""
        werte: dict[str, int] = {}
        geraten: list[str] = []
        for name, vorgabe in VORGABEN.items():
            gelesen = self.lies_int(name)
            if gelesen is None:
                gelesen = vorgabe
                geraten.append(name)
            werte[name] = gelesen
        return Parameter(
            step_num=werte[ATTR_STEP_NUM],
            cycle=werte[ATTR_CYCLE],
            ctrl_time_ms=werte[ATTR_CTRL_TIME],
            step_delay_ms=werte[ATTR_STEP_DELAY],
            back_step=werte[ATTR_BACK_STEP],
            geraten=tuple(geraten),
        )

    def no_limit(self) -> int | None:
        """Steht die Bereichspruefung ab? None = Attribut nicht lesbar.

        Wird gelesen, nie geschrieben. Ist der Wert 1, hat jemand anders die
        Pruefung abgeschaltet -- dann faehrt dieses Werkzeug nicht.
        """
        if not self.hat(ATTR_NO_LIMIT):
            return None
        return self.lies_int(ATTR_NO_LIMIT)

    # -- schreiben ----------------------------------------------------------

    def schreibe(self, name: str, wert: str | int) -> None:
        """Ein Attribut schreiben. Gesperrte Attribute werden abgewiesen."""
        if name in VERBOTEN_SCHREIBEN:
            raise Verboten(
                f"{name} wird von h713-focus grundsaetzlich nicht geschrieben: "
                f"das schaltet im Treiber die Bereichspruefung ab, und ohne sie "
                f"kehrt er am Rand nicht mehr um.")
        text = str(wert)
        if self.trocken:
            self.geplant.append((name, text))
            return
        with (self.basis / name).open("w") as f:
            f.write(text)

    def befehl(self, cmd: int, msteps: int = 0) -> int:
        """Das Wort fuer motor_ctrl bauen und schreiben; liefert das Wort.

        Protokoll (motor_ctrl_store): (cmd << 8) | (msteps & 0x7F) | 0x80 fuer
        "full_limit". Bit 0x80 wird hier NICHT gesetzt: es ist im Treiber eine
        Drosselung, die Befehle *verwirft*, sobald die Warteschlange laenger als
        drei ist. h713-focus faehrt einen Befehl nach dem anderen und wartet
        dazwischen -- die Warteschlange ist also leer, die Drossel waere ohne
        Wirkung, koennte aber im Fehlerfall still msteps schlucken.
        """
        if not 0 <= msteps <= 0x7F:
            raise MotorFehler(f"msteps ausserhalb 0..127: {msteps}")
        wort = (cmd << 8) | msteps
        self.schreibe(ATTR_CTRL, wort)
        return wort

    def leeren(self) -> int:
        """Warteschlange leeren (cmd 3).

        Das wirft weg, was noch nicht abgearbeitet ist. Der mstep, der gerade
        laeuft, laeuft zu Ende -- der Treiber hat keinen Weg, ihn abzubrechen.
        """
        return self.befehl(CMD_LEEREN, 0)


def oeffne(vorgabe: str | None = None, trocken: bool = False) -> Geraet:
    basis, herkunft = finde_basis(vorgabe)
    return Geraet(basis, herkunft, trocken)
