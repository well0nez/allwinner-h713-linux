# h713-focus — den Fokusmotor von Hand fahren

Ein Skript, `h713-focus`, Python 3, ohne Abhängigkeiten. Ersatz für
`legacy/tools/focus` (63 Zeilen `sh`) mit denselben Unterbefehlen — nur dass es
vor und nach jeder Bewegung nachsieht, statt blind zu schreiben.

```
h713-focus status          # Wächter, Kanten, Zähler, und was gerade frei ist
h713-focus up 20           # 20 msteps aufwärts, in Häppchen zu 2
h713-focus down 20         # abwärts
h713-focus flush           # Warteschlange leeren (Not-Halt)
h713-focus unlatch         # gemerkte Kanten löschen
```

Zusätzlich: `-n` / `--trocken` (prüfen und zeigen, nichts schreiben),
`--schritt N` (msteps je Schreibvorgang, Vorgabe 2, höchstens 18),
`--sysfs PFAD` bzw. `$H713_FOCUS_SYSFS` (Knoten vorgeben statt suchen).

Rückgabewerte: `0` erledigt · `2` Bedienfehler oder kein Knoten · `3` gesperrt
oder am Rand angehalten · `4` Frist abgelaufen / Befehl verworfen · `130` Strg-C.

## Vorher: das Modul

Seit Patch **0157** ist der Knoten `motor_ctr` aktiv und seit **0156** ist
`homing` standardmäßig **aus** — der Treiber wird beim Booten geladen (`=m`,
über modalias), richtet die Pads ein, zeigt sysfs und bewegt dabei nichts.
Normalerweise ist also nichts zu tun; `h713-focus status` sagt, ob er da ist.

Falls er fehlt (blacklistet, oder Kernel ohne 0157):

```bash
modprobe hy310_focus_motor
```

Auf einem Kernel **vor 0156** ist `homing=0` dabei Pflicht: sonst läuft beim
Laden die Homing-Folge, und die fährt bis zu 100 msteps **aufwärts** — in die
Richtung des mechanischen Anschlags. Ob es dort überhaupt eine Wächterkante
gibt, ist ungeprüft; gemessen wurde nur die untere. Genau deshalb lädt
`h713-focus` den Treiber **nicht** selbst.

## Was PH14 ist — und was nicht

Ein **Bereichswächter**, kein Endschalter. Der Pin liest `active_level` (hier
HIGH), *solange* die Mechanik im erlaubten Fahrbereich steht; der Rand wird am
**Wegfall** des Pegels erkannt. Gemessen am 12.09.2026
(`analyse/boot/motor-bereichswaechter-20260912.txt`):

```
raw=1 ... step=-204
raw=0 ... step=-206            <== Rand
raw=1 ... edge_dn=1 step=-207  (Treiber kehrt um, merkt die Kante, hält)
```

Umkehren und Kantenmerken macht der Treiber selbst. Das Skript baut das nicht
nach — es erkennt, dass es passiert ist, und hört dann auf.

`step` ist ein **Zählerstand, keine Position.** Bei einem Randereignis fährt die
Mechanik physisch `1 + k + back_step` msteps, der Zähler aber nur einen. Nach dem
ersten Rand laufen beide um rund 6 msteps auseinander, und jedes weitere
Ereignis vergrößert den Versatz.

## Wann es nicht fährt

| Befund | warum das zählt |
|---|---|
| `num=0` | Kein Wächter angefordert → `motor_limiter_status()` meldet bedingungslos „im Bereich", der Treiber kehrt **nie** um. Das erste Feld der Zeile sieht dabei gesund aus — es ist also gerade dann wertlos, wenn es darauf ankäme. |
| `motor_ctrl_no_limit = 1` | Die Bereichsprüfung ist abgeschaltet. Das Skript **schreibt dieses Attribut nie**, aber jemand anders kann es gesetzt haben. |
| kein `raw=`, oder `raw=-1` | Ohne Rohpegel ist nicht zu sehen, ob der Wächter überhaupt etwas liefert. Genau diese Lücke hat beim NTC eine erfundene Temperatur aus einem offenen Eingang erzeugt. Anzeigen ja, fahren nein. |
| `raw != act` | Mechanik steht außerhalb des Fahrbereichs. |
| `edge_up`/`edge_dn` in Fahrtrichtung | Der Treiber verwirft solche Befehle **still** — still ist hier das Falsche. |

Dazu eine harte Obergrenze von 400 msteps je Lauf, auch wenn der Wächter
schweigt: ein Wächter, der nichts meldet, ist kein Beleg dafür, dass noch Weg da
ist. Und Strg-C wird abgefangen — die Warteschlange wird geleert, statt den
Prozess mitten in einem Häppchen zu verlassen. Der mstep, der gerade läuft,
läuft zu Ende; den kann der Treiber nicht abbrechen.

## Das Protokoll

`motor_ctrl` nimmt `(cmd << 8) | (steps & 0x7f) | (full_limit ? 0x80 : 0)`.

| cmd | Bedeutung |
|---|---|
| 1 / 2 | auf/ab, **setzt** das Autofokus-Flag → Busy-wait-Timing (`mdelay`). Der Pfad des Stock-Autofokus; das alte `focus`-Skript nahm diesen. |
| 3 | Warteschlange leeren |
| 4 | Schrittzähler setzen |
| 6 | `step_low` setzen |
| 7 | auf Schritt fahren — **im Treiber nicht implementiert**, liefert `-EOPNOTSUPP` |
| **8 / 9** | auf/ab, **löscht** das Autofokus-Flag → schlafendes Timing. Der Pfad für Handbedienung — **den nimmt dieses Skript.** |

Der Treiber kürzt msteps je Schreibvorgang still auf 18 (`MOVE_CLAMP_MAX`). Wer
30 schreibt, bekommt 18 und merkt es nicht; deshalb prüft das Skript selbst und
zerlegt längere Fahrten in Häppchen. Das Bit `0x80` (`full_limit`) ist im
Treiberkopf beschrieben, aber nie geprüft worden — es wird nicht benutzt.

## Was hier absichtlich fehlt

**Autofokus.** Ein Autofokus misst die Schärfe an dem, was gerade projiziert
wird. Auf einer dunklen Szene oder einem Schwarzbild misst er Unsinn und
verstellt den Fokus ins Leere; er gehört auf ein Testbild mit harten Kanten.
Eine automatische Regelung muss also entweder verlangen, dass ein geeignetes
Testbild anliegt, oder es selbst herstellen (`h713-tv`) und danach den
vorherigen Zustand wiederherstellen. Das ist ein eigenes Werkzeug, kein
Unterbefehl hier. Ungeprüft: welches Testbild Stock dafür benutzt.

**Homing.** Es gibt keinen Referenzpunkt außer den beiden Rändern, und an einen
Rand zu fahren, um ihn zu finden, ist genau das, was dieses Skript vermeidet.

## `test-attrappe.py`

Spielt den Treiber in einem Verzeichnis nach (Rand bei step −206 wie gemessen), damit
das Skript ohne Gerät durchläuft: `python3 test-attrappe.py VERZ &` und dann
`H713_FOCUS_SYSFS=VERZ ./h713-focus down 20`. Reproduziert die Messung vom 12.09.
exakt; schreibt `motor_limit` atomar, sonst bricht `h713-focus` an einer leeren
Zeile richtigerweise ab.

## `_entwurf-agent/`

Ein früherer Entwurf als Python-Paket, 2545 Zeilen. Beiseitegelegt, nicht
weggeworfen — die ausformulierte Sicherheitslogik und die Testanleitung sind
lesenswert, wenn jemand das Werkzeug erweitert. Siehe `_entwurf-agent/LIESMICH.md`.
