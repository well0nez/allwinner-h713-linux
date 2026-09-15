# E3 - Die Auflösung steht lesbar im INCAP-Register

07.09.2026, 12:05-12:20 · Board-Sitzung · Paket E, Nachtplan A.6 Punkt 4

## Die Frage, die offen war

`A6-4-aufloesungswechsel.md` schließt mit:

> **Woran ein Geometriewechsel erkennbar wäre**, ohne zu pollen. Kandidaten, die noch niemand gelesen
> hat: die INCAP-Timing-Register … **Messvorschrift:** vor und nach einem `xrandr --mode`-Wechsel
> `dump_state.py` ziehen und die Blöcke `0x0694` und `0x0500` diffen.

Beim Prüfen des Quellenwechsels als Rettungsweg ist der Kandidat aufgefallen - im Register, das wir
ohnehin schon lesen.

## Befund

`0x06940928`, untere 16 Bit, über vier Modi gemessen. Zwischen jedem Wechsel ein Quellenwechsel
weg-und-zurück:

| Quelle | `0x06940928` | Bit 31 | untere 16 Bit |
|---|---|---|---|
| 1920x1080 | `0xE0020438` | an | **1080** |
| 1280x720 | `0xE00202D0` | an | **720** |
| 1600x1200 | `0x600202D0` | **aus** | 720 (Altwert) |
| 1920x1200 | `0x600202D0` | **aus** | 720 (Altwert) |

`0x438` = 1080, `0x2D0` = 720 - exakt, nicht ungefähr. Damit stehen in **einem** Wort zwei Dinge, die
der Treiber heute beide nicht hat:

1. **Bit 31 - die INCAP-Ausgabefreigabe.** *Korrektur 14:00: nicht „rastet ein“. Bit 31 ist
   ida-belegt `VIncap_EnableCaptureOutput` (`re/notes/CURRENT-TRUTH.md:65`, `doku/84` §4.3) und steht
   nachweislich auf 0, **während** ein Signal anliegt und eingerastet ist - unmittelbar nach jedem
   Descriptor-Schreiben (`A-abnahme-board.md:101-106`) und 20 s lang nach `SetSource(VideoDec)`
   (`M4-nachpruefung.md`). Als Einrast-Anzeige taugt es nicht; ein Wächter darauf meldet Fehlalarm.*
   Bei 1600x1200 und 1920x1200 fiel es aus - Modi, die unser EDID nicht führt, und die Capture stand
   dabei. Was davon „nicht eingerastet“ und was „Ausgabe aus“ ist, trennt diese Messung **nicht**.
2. **Bit 15..0 - die Zeilenzahl des eingerasteten Signals.** Das ist der Auslöser, nach dem A6-4
   gesucht hat.

## Was das für Paket E heißt

`QUERY_DV_TIMINGS` liefert heute eine **Übersetzungszeit-Konstante** (Korrektur 08:55 in A6-4) und
`V4L2_EVENT_SOURCE_CHANGE` feuert nie, weil beides am `SignalChange`-Callback hängt und der nicht
zugestellt wird. Dieses Register hängt an keinem Callback. Es beantwortet beide Fragen, die V4L2
stellt - *liegt ein Signal an* und *welche Geometrie* - , und zwar durch Lesen, nicht durch Warten.

**Was noch fehlt, bevor daraus Code wird:** die Breite. Die Zeilenzahl allein reicht für
`DV_TIMINGS` nicht, und ob die Breite in der oberen Hälfte desselben Wortes steht, ist **nicht**
gemessen - die obere Hälfte war bei allen vier Modi `0xE002` bzw. `0x6002`, hat sich also *nicht*
mitbewegt. Sie steht anderswo. Nächster Schritt: `dump_state.py` vor und nach dem Wechsel ziehen und
den Block `0x0694` diffen, wie A6-4 es vorschreibt - jetzt mit dem Wissen, wonach zu suchen ist.

Der Treiber darf INCAP nur **lesen** (Nachtplan Abschnitt 0). Das genügt hier.

## Der Rettungsweg trägt nicht

Die zweite Frage dieses Durchgangs: holt ein Quellenwechsel das Bild nach einem Auflösungswechsel
zurück? **Nein.**

Nach `xrandr --mode 1280x720` zeigt die Wand das aus A6-4 bekannte Bild - oben der neue 720p-Inhalt
zerrissen, darunter der alte 1080p-Rest. Ein Quellenwechsel weg-und-zurück bringt die **Firmware**
auf die neue Geometrie (`0x928` unten von `0x438` auf `0x2D0`), das Bild bleibt aber unverändert
zerrissen: Ring-Zeilenabstand, Zuschnitt und Descriptor auf der Anzeigeseite stehen weiter auf 1080p,
und der Treiber weigert sich mit gutem Grund, den Descriptor ein zweites Mal zu schreiben.

Zurück auf 1920x1080 ist das Bild sofort wieder einwandfrei, ohne Zutun - wie in A6-4.

**Ein Auflösungswechsel bleibt damit nicht unterstützt.** Neu ist nur, dass er jetzt *erkennbar*
wäre. Was fehlt, ist ein Weg, die Anzeigeseite mitzuziehen, ohne den Descriptor neu zu schreiben -
oder ein belegter Weg, ihn gefahrlos neu zu schreiben. Das bleibt offen.
