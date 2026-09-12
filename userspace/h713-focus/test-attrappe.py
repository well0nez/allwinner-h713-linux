#!/usr/bin/env python3
"""test-attrappe.py -- den Treiber nachspielen, damit h713-focus ohne Geraet laeuft.

Legt in einem Verzeichnis motor_ctrl, motor_limit und motor_ctrl_no_limit an
und reagiert auf Schreibvorgaenge wie hy310-focus-motor: cmd 8/9 bewegt den
Zaehler in msteps, am Rand (Vorgabe step -206, wie am 12.09.2026 gemessen)
faellt raw auf 0, dann kehrt die Attrappe um, setzt edge_dn und haelt bei
-207. Ein Befehl gegen eine gemerkte Kante wird still verworfen -- wie im
Treiber. cmd 3 leert (tut hier nichts).

    python3 test-attrappe.py VERZ [RAND] &
    H713_FOCUS_SYSFS=VERZ ../h713-focus down 20      # laeuft in den Rand
    H713_FOCUS_SYSFS=VERZ ../h713-focus down 4       # gesperrt: edge_dn=1
    H713_FOCUS_SYSFS=VERZ ../h713-focus up 4         # frei

Damit wurde am 12.09.2026 der ganze Ablauf des Skripts geprueft, bevor es aufs
Geraet kam (Ergebnis: reproduziert die Messung exakt). Die Attrappe loescht
edge_dn beim Aufwaertsfahren NICHT -- das tut der echte Treiber; wer das
braucht, ergaenzt es hier. Endet nach 60 s von selbst.
"""
import pathlib
import sys
import time

d = pathlib.Path(sys.argv[1])
rand = int(sys.argv[2]) if len(sys.argv) > 2 else -206
d.mkdir(parents=True, exist_ok=True)
step, edge_dn, edge_up, raw = -200, 0, 0, 1


def schreibe():
    # Atomar (schreiben + umbenennen): sysfs liefert eine Zeile immer ganz,
    # eine Datei mit truncate+write dagegen kurz leer -- und h713-focus bricht
    # bei einer unlesbaren Zeile richtigerweise ab (12.09.: so aufgefallen).
    tmp = d / ".motor_limit.neu"
    tmp.write_text(
        f"{1 if raw == 1 else 0} up=1 dn=1 num=1 raw={raw} act=1 "
        f"edge_up={edge_up} edge_dn={edge_dn} step={step}\n")
    tmp.replace(d / "motor_limit")


schreibe()
(d / "motor_ctrl_no_limit").write_text("0\n")
(d / "motor_ctrl").write_text("0\n")
letzte = 0.0
ende = time.time() + 60
while time.time() < ende:
    try:
        m = (d / "motor_ctrl").stat().st_mtime
    except OSError:
        m = letzte
    if m != letzte:
        letzte = m
        try:
            wort = int((d / "motor_ctrl").read_text().strip())
        except ValueError:
            wort = 0
        cmd, n = wort >> 8, wort & 0x7f
        if cmd in (8, 9):
            ab = (cmd == 9)
            if (ab and edge_dn) or (not ab and edge_up):
                continue                        # Treiber verwirft still
            for _ in range(max(1, n)):
                step += -1 if ab else 1
                if ab and step <= rand:         # Pegel faellt weg
                    raw = 0
                    schreibe()
                    time.sleep(0.08)
                    step -= 1                   # Treiber: ein mstep weiter, dann zurueck
                    raw = 1
                    edge_dn = 1
                    schreibe()
                    break
                schreibe()
                time.sleep(0.03)
    time.sleep(0.01)
