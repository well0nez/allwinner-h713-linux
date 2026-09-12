# E4 — Die Quellgeometrie steht vollständig lesbar im INCAP-Block

07.09.2026, 13:30 · Board-Sitzung · Paket E, Vorarbeit zum neuen Plan

## Anlass

`E3-geometrie-im-register.md` fand `0x06940928[15:0]` als Zeilenzahl und hielt fest: „**Was noch
fehlt, bevor daraus Code wird: die Breite.** … Nächster Schritt: `dump_state.py` vor und nach dem
Wechsel ziehen und den Block `0x0694` diffen, wie A6-4 es vorschreibt."

Genau das ist jetzt gefahren.

## Aufbau

`dump_state.py` bei 1920x1080, Zuspieler auf 1280x720, Quellenwechsel weg-und-zurück (damit die
Firmware neu einrastet), zweiter Abzug. Dann beide Abzüge auf Register durchsucht, deren Hälften
**exakt** von 1920/1080 auf 1280/720 springen — beziehungsweise auf die zugehörigen Totalwerte
2200/1125 → 1650/750.

Das ist eine Suche, die leer ausgehen kann; für die Synchronlagen ist sie es auch (siehe unten).

## Befund: ein Wort trägt die ganze aktive Geometrie

| Register | 1920x1080 | 1280x720 | Bedeutung |
|---|---|---|---|
| **`0x06940874`** | `0x07800438` | `0x050002d0` | **Breite `[31:16]`, Höhe `[15:0]`** |
| `0x0694086c` | `0x00000780` | `0x00000500` | Breite, einzeln |
| `0x06940870` | `0x00000438` | `0x000002d0` | Höhe, einzeln |
| `0x06940464` | `0x00000780` | `0x00000500` | Breite, zweite Ablage |
| `0x06940468` | `0x00000438` | `0x000002d0` | Höhe, zweite Ablage |
| `0x06940928` | `0xe0020438` | `0xe00202d0` | Höhe `[15:0]`; Bit 31 = **Ausgabefreigabe**, nicht „eingerastet“ (Korrektur unten) |
| `0x06940968` | `0xe0020438` | `0xe00202d0` | Zwilling von `0x928` |

Und die Totalwerte:

| Register | 1920x1080 | 1280x720 | Bedeutung |
|---|---|---|---|
| **`0x06940548`** | `0x04650898` | `0x02ee0672` | **v_total `[31:16]` = 1125/750, h_total `[15:0]` = 2200/1650** |
| `0x06940558` | `0x04650898` | `0x02ee0672` | Zwilling |
| `0x06940a2c` | `0x00000898` | `0x00000672` | h_total, einzeln |
| `0x06940a30` | `0x00000465` | `0x000002ee` | v_total, einzeln |
| `0x06940598` | `0x00000465` | `0x000002ee` | v_total, einzeln |
| `0x06940540` | `0x18000464` | `0x180002ed` | v_total **minus 1** in `[15:0]` |

Alle Werte exakt, keine Näherung. `0x780` = 1920, `0x500` = 1280, `0x438` = 1080, `0x2d0` = 720,
`0x898` = 2200, `0x672` = 1650, `0x465` = 1125, `0x2ee` = 750.

## Was das für Paket E heißt

`QUERY_DV_TIMINGS` liefert heute eine **Übersetzungszeit-Konstante** und `V4L2_EVENT_SOURCE_CHANGE`
feuert bei einem reinen Geometriewechsel nicht, weil beides am `SignalChange`-Callback hängt. Mit
diesen Registern braucht keines von beidem einen Callback:

* **aktive Geometrie** aus `0x06940874`, ein Lesezugriff,
* **Totale** aus `0x06940548`,
* **Ausgabefreigabe** aus `0x06940928` Bit 31 — **nicht** „eingerastet“, siehe Korrektur unten.

Der Treiber darf INCAP **lesen** (Nachtplan Abschnitt 0 verbietet nur das Schreiben). Damit ist
`QUERY_DV_TIMINGS` ehrlich beantwortbar, und ein Geometriewechsel ist erkennbar, ohne zu pollen —
der Aufnahmetreiber hat mit dem AFBD-Vsync-Notifier bereits ein Ereignis, an dem er das ansehen
kann, ohne einen eigenen Takt zu erfinden.

## Was **nicht** gefunden wurde

**Die Synchronlagen.** Gesucht wurde nach Registern, die von den CTA-Werten für 1080p60 auf die
für 720p60 springen — `hfront` 88→110, `hsync` 44→40, `hback` 148→220, `vfront` 4→5, `vback` 36→20,
sowie den Austastlücken 280→370 und 45→30. **Kein einziger Treffer** im ganzen INCAP-Block.

Drei mögliche Erklärungen, keine davon geprüft:
1. die Werte stehen nicht in diesem Block,
2. sie sind anders kodiert (Summen, Versätze, Startpositionen statt Breiten),
3. der Zuspieler fährt andere Zeitlagen als die CTA-Norm.

Für `V4L2_DV_TIMINGS` sind sie Pflichtfelder. Ohne sie bleibt nur, sie aus den bekannten
Norm-Zeitlagen zur gemessenen Geometrie zu erschließen — was eine erfundene Zahl wäre, sobald die
Quelle etwas anderes fährt. **Das ist der offene Rest.**

Zum Vergleich: insgesamt haben sich zwischen den beiden Abzügen 33 INCAP-Register geändert (ohne
die bekannten Zähler `+0x104`, `+0x544`, `+0x588`, `+0x59c`, `+0x600…61c`); 18 davon sind oben
zugeordnet. Die übrigen 15 sind nicht untersucht.

## Der Pixeltakt

`hy310-tv` meldet heute `148500000 Hz Pixeltakt` bei 1080p — die Zahl kommt aus derselben
fest verdrahteten Konstante wie die Timings und ist damit **kein Messwert**. Ob der Takt irgendwo
lesbar ist, wurde nicht gesucht. Aus h_total × v_total × 60 ergäbe sich 148,5 MHz für 1080p60 und
74,25 MHz für 720p60 — das ist eine Rechnung, keine Messung, und sie setzt 60 Hz voraus.


---

## Korrektur 14:00 — zwei Fehler in dieser Seite

**1. Bit 31 ist nicht „eingerastet“.** Es ist ida-belegt `VIncap_EnableCaptureOutput`
(`re/notes/CURRENT-TRUTH.md:65`, `re/work/weltneuheit/re_chain/mem_agent.txt:2`, `doku/84` §4.3) —
die INCAP-**Ausgabefreigabe**. Am Gerät steht es auf 0, während ein Signal anliegt und eingerastet
ist: unmittelbar nach jedem Descriptor-Schreiben (`A-abnahme-board.md:101-106`) und 20 s lang nach
`SetSource(VideoDec)` (`M4-nachpruefung.md`). Ein Einrast-Wächter darauf meldet Fehlalarm. Der Satz
oben, damit sei „liegt ein Signal an“ beantwortbar, trägt so **nicht**.

**2. Warum die Breite in `0x928` strukturell nicht stehen kann.** Die Suche nach ihr in der oberen
Hälfte war aussichtslos, und das stand schon im Projekt: `CapWinNode__WriteReg` baut das Wort als
`0x60020000 | Höhe` (`doku/84-re-capture-ring.md:388`). Die obere Hälfte ist ein **Literal**, kein
Feld. Dieselbe Stelle nennt auch `0x924`/`0x964` und die Capture-Fenster-Register
`0x440/0x444/0x448/0x464/0x468` — dort hätte die Suche anfangen können.

## Nachtrag 14:00 — der Zeilenabstand der Capture

Aus denselben zwei Abzügen:

| Register | 1920x1080 | 1280x720 |
|---|---|---|
| `0x06940924` | `0x00780078` | **`0x00500050`** |
| `0x06940964` | `0x00780078` | **`0x00500050`** |
| `0x0694084c` | `0x04000c00` | `0x04000c00` (unverändert) |

`0x78` = 120 = 1920/16, `0x50` = 80 = **1280**/16; der elog nennt das Feld `m_psu_rowbyte_y`
(`CapWinNode.cpp 235`). **Die Capture schreibt bei 720p ein 1280 breites Bild in den Ring.** Eine
Offline-Messung an `E/frame720.png`, die auf 640 Byte je Zeile kam, ist damit widerlegt — die
640er-Periode entsteht im Rekonstruktionswerkzeug, nicht in der Capture.

Das entscheidet die teuerste Weggabelung bei Punkt 2: der Ring enthält bei 720p wirklich ein
1280x720-Bild, und der Weg „die Plane nimmt die Quellgeometrie an“ steht auf einer Messung statt
auf einer Annahme.
