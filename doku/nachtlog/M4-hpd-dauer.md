# M4 - Wie lange muss HPD unten liegen? (Board-Agent = Hauptsitzung, 22:51-22:54)

Auftrag: Paket J, Messung M4. `arisc_edid_init.sh` hält HPD **10 s** unten. J führt das als Workaround-Verdacht
(„`sleep 10` als HPD-Low-Dauer ohne Stock-Beleg - Stock arbeitet mit 200", `SetHPDTimeInterval from 200 to 200`).

## Vorgehen

Board im Zustand nach der A-Abnahme, Bild live. Je Dauer *d*: `PullHotPlug DOWN` → `sleep d` → `UP`, dann 8 s
warten und drei Dinge prüfen: meldet der Zuspieler `connected`, zählt `0x06940104` wieder, und steht
`0x06940928` Bit 31. Abzüge in `re/captures/weltneuheit/ours-20260907-nacht/M4/`.

| HPD unten | Zuspieler | `0x06940928` | INCAP zählt | Wand vs. Referenz |
|---|---|---|---|---|
| **0,3 s** | `connected` | `0xE0020438` | ja (+61/s) | mean 1,13 - **0,00 %** > 25 |
| **1 s** | `connected` | `0xE0020438` | ja (+61/s) | mean 1,19 - **0,00 %** > 25 |
| **3 s** | `connected` | `0xE0020438` | ja | mean 47,06 - 65,03 % > 25 |

## Der Ausreißer bei 3 s ist die Quelle, nicht der Beamer

Zwei Aufnahmen **ohne jeden Eingriff** im Abstand von 4 s: 0,00 % Unterschied - die Quelle ist kurzfristig
stabil. Über die Messreihe hinweg driftet sie aber (Referenz mean 123,9 → Ruhe 113,5 ohne Zutun): die
Firefox-Seite hat ein wechselndes Element. Der 65-%-Sprung fällt also mit einem Wechsel dieses Elements
zusammen, nicht mit der HPD-Dauer - Verbindung, Freigabebit und Zähler waren bei 3 s genauso in Ordnung wie
bei 0,3 s.

## Ergebnis

**0,3 s genügen**, um nach einem HPD-Zyklus wieder eine verbundene Quelle und eine laufende Capture zu haben.
Die 10 s sind für **diesen** Zweck nicht nötig.

## Eine wichtige Einschränkung, die diese Messung *nicht* deckt

Gemessen wurde der **Wiederanlauf-Zyklus** - die Quelle hatte das EDID bereits gelesen. In
`arisc_edid_init.sh` steht das `sleep 10` an einer **anderen** Stelle: unmittelbar nach dem Hochladen der acht
EDID-Fragmente, wo der Zuspieler ein **neues** EDID lesen soll. Ob dafür 0,3 s reichen, ist damit **nicht**
gezeigt. Wer die 10 s dort streichen will, misst genau diesen Fall: EDID hochladen, kurze HPD-Senke, und dann
prüfen, ob der Zuspieler das EDID „SGD SX8" wirklich neu gelesen hat (nicht nur, ob er `connected` meldet).

## Was daraus für die Pakete folgt

Paket **D**/**E**: der HPD-Zyklus, der die Capture nach dem Descriptor wieder scharf macht (siehe
`A-abnahme-board.md`), darf **kurz** sein - 0,3 s sind belegt. Das ist kein „einmal pulsen", sondern der
Stock-Unterbefehl `0x0211 PullHotPlug` in seiner regulären Verwendung; die Dauer ist jetzt gemessen statt geraten.
