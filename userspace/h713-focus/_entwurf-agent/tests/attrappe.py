"""attrappe.py -- ein Pruefstand fuer h713-focus, ohne Gerät und ohne Mechanik.

Zwei Dinge stecken hier drin:

``Treibermodell``
    Nachbau der Bewegungslogik von ``drivers/misc/hy310-focus-motor.c``, soweit
    sie von aussen ueber sysfs sichtbar ist: motor_run_up_control /
    motor_run_dn_control mit Umkehr am Rand, back_step, Kanten merken und die
    Kante der Gegenrichtung loeschen, MOVE_CLAMP_MAX, und die Zeile von
    motor_limit im Format ab Patch 0154.

``Verzeichnis``
    macht daraus ein echtes Verzeichnis mit echten Dateien, damit
    ``h713-focus --sysfs PFAD`` unveraendert dagegen laeuft -- derselbe Code,
    derselbe Pfad durch geraet.py, nur ohne Motor.

**Was das Modell NICHT ist:** ein Beweis darueber, wie sich der Treiber
verhaelt. Es ist aus dem Quelltext abgeschrieben, nicht am Gerät gemessen. Was
es prueft, ist das Verhalten von h713-focus -- ob das Werkzeug bei raw=0
anhaelt, ob es eine gemerkte Kante bemerkt, ob es seine Obergrenze einhaelt.
Ob der Treiber sich seinerseits so verhaelt, steht in
``analyse/boot/motor-bereichswaechter-20260912.txt`` und nirgends hier.

Zwei bewusste Abweichungen vom Treiber:

* Der echte Treiber arbeitet asynchron (motor_ctrl reiht ein, ein
  Workqueue-Handler faehrt). Die Attrappe faehrt einen mstep je Takt ihres
  Hintergrundfadens -- asynchron genug, dass die Wartelogik von
  ``fahren._warte()`` wirklich durchlaufen wird, aber deterministisch.
* Der Rand-mstep und die Erholungsfahrt danach sind in zwei Takte getrennt,
  und ``rand_pause_ms`` haelt den Zwischenzustand fest. Das ist der Zustand,
  in dem am 12.09. am Gerät ``raw=0`` abgelesen wurde: der Pegel ist weg, der
  Zaehler noch nicht weitergelaufen, die Kante noch nicht gesetzt. Ohne diese
  Pause waere der Zustand zu kurz, um ihn in einem Test verlaesslich zu
  treffen.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# Konstanten des Treibers (dortige #defines).
MOVE_CLAMP_MAX = 18
RECOVERY_MAX = 40

CMD_AUF = 8
CMD_AB = 9
CMD_LEEREN = 3

DATEINAMEN = ("motor_ctrl", "motor_limit", "motor_ctrl_no_limit",
              "motor_step_num", "motor_cycle", "motor_step_delay",
              "motor_back_step", "motor_ctrl_time")


@dataclass
class Treibermodell:
    """Der Motor, wie ihn der Treiber nach aussen zeigt."""

    #: Physische Lage in msteps. Willkuerlicher Nullpunkt, anfangs gleich dem
    #: Zaehler -- so wie beim Laden des Moduls.
    pos: int = 0
    #: Zaehlerstand (m->step_cur). Laeuft nach einem Randereignis von pos weg.
    step: int = 0

    #: Der erlaubte Fahrbereich in derselben Einheit wie pos: ausserhalb faellt
    #: der Pegel weg. None = dieser Rand liegt ausser Reichweite.
    rand_unten: int | None = None
    rand_oben: int | None = None

    num: int = 1               # limiter_num
    act: int = 1               # active_level
    back_step: int = 5
    no_limit: int = 0

    step_num: int = 1          # klein, damit die Tests schnell sind
    cycle: int = 1
    ctrl_time: int = 1
    step_delay: int = 1

    edge_up: bool = False
    edge_dn: bool = False
    step_inc: int = 0

    #: Wie lange der Zustand "Pegel weg, Zaehler noch alt" stehen bleibt.
    rand_pause_ms: float = 0.0

    #: Noch nicht gefahrene msteps: +1 aufwaerts, -1 abwaerts.
    warteschlange: list[int] = field(default_factory=list)
    protokoll: list[str] = field(default_factory=list)

    _erholung_fuer: int = 0    # 0 = keine faellig, sonst die Fahrtrichtung

    # -- Waechter ----------------------------------------------------------

    @property
    def im_fahrbereich(self) -> bool:
        if self.rand_unten is not None and self.pos < self.rand_unten:
            return False
        if self.rand_oben is not None and self.pos > self.rand_oben:
            return False
        return True

    def raw(self) -> int:
        """Was gpiod_get_raw_value() liefern wuerde; -1 ohne Pin."""
        if self.num < 1:
            return -1
        return self.act if self.im_fahrbereich else 1 - self.act

    def limiter_status(self) -> int:
        """motor_limiter_status(). Ohne Pin bedingungslos 1 -- genau das ist
        die Falle, gegen die zustand.pruefe() die Regel num >= 1 hat."""
        if self.num < 1:
            return 1
        return 1 if self.raw() == self.act else 0

    # -- Bewegung ----------------------------------------------------------

    def _mstep(self, richtung: int) -> None:
        self.pos += richtung

    def _zaehler(self, richtung: int) -> None:
        # Der Zaehler laeuft EINMAL weiter, egal wie viele msteps die Erholung
        # gekostet hat -- daher der Versatz (zustand.zaehler_versatz).
        self.step += 1 if richtung > 0 else -1
        # Fahren in eine Richtung loescht die Kante der Gegenrichtung.
        if richtung > 0:
            self.edge_dn = False
        else:
            self.edge_up = False
        self.step_inc = self.step_inc + 1 if self.step_inc < 10 else 0

    def _erholen(self, richtung: int) -> None:
        """Zurueck in den Bereich, back_step weiter hinein, Kante merken."""
        n = 0
        gelatcht = False
        while True:
            self._mstep(-richtung)
            if self.limiter_status():
                break
            n += 1
            if n == RECOVERY_MAX:
                self.protokoll.append("limiter did not return in range")
                gelatcht = True
                break
        if not gelatcht:
            for _ in range(self.back_step):
                self._mstep(-richtung)
        if richtung > 0:
            self.edge_up = True
        else:
            self.edge_dn = True
        self._zaehler(richtung)

    @property
    def erholung_faellig(self) -> bool:
        return self._erholung_fuer != 0

    def ein_mstep(self) -> bool:
        """Einen Takt arbeiten. Liefert, ob etwas getan wurde."""
        if self._erholung_fuer:
            r, self._erholung_fuer = self._erholung_fuer, 0
            self._erholen(r)
            return True
        if not self.warteschlange:
            return False

        r = self.warteschlange.pop(0)
        if (r > 0 and self.edge_up) or (r < 0 and self.edge_dn):
            return True                      # verworfen, wie im Treiber

        self._mstep(r)
        if not self.no_limit and not self.limiter_status():
            # Zwischenzustand: Pegel weg, Zaehler noch alt, Kante noch offen.
            self._erholung_fuer = r
            return True
        self._zaehler(r)
        return True

    def abarbeiten(self) -> None:
        while self.ein_mstep():
            pass

    # -- sysfs -------------------------------------------------------------

    def ctrl_write(self, text: str) -> None:
        """motor_ctrl beschreiben: (cmd << 8) | msteps."""
        try:
            wert = int(text.strip())
        except ValueError:
            raise OSError(22, "Invalid argument")
        cmd = (wert >> 8) & 0xFF
        msteps = wert & 0x7F
        if cmd == CMD_LEEREN:
            self.warteschlange.clear()
            return
        if cmd not in (CMD_AUF, CMD_AB):
            # 1/2 (Autofokus-Zeitgebung, busy-wait) baut die Attrappe
            # absichtlich nicht nach: h713-focus darf sie nie schicken, und ein
            # Test, der das trotzdem tut, soll auffallen.
            raise OSError(22, f"Invalid argument (cmd {cmd})")

        richtung = 1 if cmd == CMD_AUF else -1
        if richtung > 0 and self.edge_up:
            return
        if richtung < 0 and self.edge_dn:
            return
        n = 1 if msteps <= 0 else min(msteps, MOVE_CLAMP_MAX)
        self.warteschlange.extend([richtung] * n)

    def limit_zeile(self) -> str:
        s = self.limiter_status()
        return (f"{s} up={s} dn={s} num={self.num} raw={self.raw()} "
                f"act={self.act} edge_up={int(self.edge_up)} "
                f"edge_dn={int(self.edge_dn)} step={self.step}")

    def ctrl_zeile(self) -> str:
        return f"{self.step} {self.step_inc % 10} {self.limiter_status()}"

    def dateien(self) -> dict[str, str]:
        return {
            "motor_ctrl": self.ctrl_zeile(),
            "motor_limit": self.limit_zeile(),
            "motor_ctrl_no_limit": str(self.no_limit),
            "motor_step_num": str(self.step_num),
            "motor_cycle": str(self.cycle),
            "motor_step_delay": str(self.step_delay),
            "motor_back_step": str(self.back_step),
            "motor_ctrl_time": str(self.ctrl_time),
        }


def _schreibe_atomar(pfad: Path, text: str) -> None:
    """Damit ein Leser nie eine halbe Zeile sieht."""
    neben = pfad.with_name(pfad.name + ".neu")
    neben.write_text(text + "\n")
    os.replace(neben, pfad)


def lege_an(verzeichnis, modell: Treibermodell) -> Path:
    """Ein stehendes Verzeichnis erzeugen -- fuer Tests ohne Bewegung."""
    p = Path(verzeichnis)
    p.mkdir(parents=True, exist_ok=True)
    for name, inhalt in modell.dateien().items():
        _schreibe_atomar(p / name, inhalt)
    return p


class Verzeichnis:
    """Ein laufendes Attrappen-Verzeichnis mit Hintergrundfaden.

    Ein Schreibvorgang auf motor_ctrl hinterlaesst dort genau eine Zahl; der
    Faden erkennt das daran (die Anzeigeform hat drei Felder), nimmt den Befehl
    an und stellt die Anzeigeform wieder her. Danach faehrt er einen mstep je
    Takt und schreibt motor_limit fort.
    """

    def __init__(self, verzeichnis, modell: Treibermodell,
                 takt_ms: float = 1.0):
        self.pfad = Path(verzeichnis)
        self.modell = modell
        self.takt = takt_ms / 1000.0
        #: Mitschrift aller angenommenen Woerter -- damit ein Test pruefen kann,
        #: WAS geschrieben wurde, nicht nur was dabei herauskam.
        self.geschrieben: list[int] = []
        self._lauf = False
        self._faden: threading.Thread | None = None

    def __enter__(self) -> "Verzeichnis":
        lege_an(self.pfad, self.modell)
        self._lauf = True
        self._faden = threading.Thread(target=self._schleife, daemon=True)
        self._faden.start()
        return self

    def __exit__(self, *_) -> None:
        self._lauf = False
        if self._faden:
            self._faden.join(timeout=2.0)
        # Nachlesen: ein Schreibvorgang, der keine Bewegung ausloest (stop),
        # kann kurz vor dem Ende des Fadens gekommen sein. Ohne diesen letzten
        # Durchgang haengt der Test davon ab, wer schneller war.
        self._einmal()

    def _einmal(self) -> float:
        """Einen Durchgang: Befehl annehmen, einen mstep fahren.

        Liefert, wie lange danach zu warten ist.
        """
        ctrl = self.pfad / "motor_ctrl"
        limit = self.pfad / "motor_limit"
        try:
            roh = ctrl.read_text().strip()
        except OSError:
            roh = ""
        if roh and len(roh.split()) == 1:
            try:
                self.geschrieben.append(int(roh))
                self.modell.ctrl_write(roh)
            except (OSError, ValueError):
                pass
            try:
                _schreibe_atomar(ctrl, self.modell.ctrl_zeile())
            except OSError:
                pass

        pause = self.takt
        if self.modell.ein_mstep():
            if self.modell.erholung_faellig:
                pause = max(pause, self.modell.rand_pause_ms / 1000.0)
            try:
                _schreibe_atomar(limit, self.modell.limit_zeile())
            except OSError:
                pass
        return pause

    def _schleife(self) -> None:
        while self._lauf:
            time.sleep(self._einmal())
