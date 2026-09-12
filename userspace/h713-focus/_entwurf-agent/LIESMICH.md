# Entwurf des Agenten — beiseitegelegt, nicht weggeworfen

Ein Agent hat hier am 12.09.2026 ein vollstaendiges Python-Paket gebaut:
2545 Zeilen Code (fuenf Module, 624 Zeilen Tests) plus 700 Zeilen Dokumentation —
fuer ein Werkzeug, das hoch, runter und status kann.

Zum Vergleich: `h713-pq` hat 1694 Zeilen und rechnet Stock-PQ-Daten in
RPC-Argumente und Gamma-LUTs um. Das alte `legacy/tools/focus` waren 63 Zeilen sh.
Marco dazu: "das is extrem overkill auf diese art, das sollte schon 1 skript sein".
Er hat recht — der Umfang steht in keinem Verhaeltnis zur Aufgabe.

**Was hier trotzdem lesenswert ist**, und was ins schlanke Werkzeug uebernommen wurde:

* `fahren.py` — harte Obergrenze je Lauf, die auch dann greift, wenn der Waechter
  schweigt; Signal-Handler fuer sauberen Abbruch mit Strg-C; Warten, bis der Motor
  zur Ruhe kommt, statt blind weiterzuschreiben.
* `geraet.py` — den sysfs-Knoten suchen statt raten (`motor-ctr` oder `motor_ctr`).
* `TESTANLEITUNG.md` — die Abbruchkriterien und Gefahrenhinweise.

Wer das Werkzeug erweitert (z. B. um Autofokus), findet hier Vorarbeit.
