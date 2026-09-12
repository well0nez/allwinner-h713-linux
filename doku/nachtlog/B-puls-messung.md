# Doorbell-Puls — die Messung, die Paket B braucht (Board-Agent = Hauptsitzung)

Auftrag: Nachtplan Stufe 2, Korrektur vom 07.09. Frage: pollt die ARISC auch **Port 0** (die Host-Unterbefehle
für EDID und HPD), oder ist die Msgbox dort flankengesteuert und der Puls damit Stock-Verhalten statt Workaround?

## Werkzeug

`analyse/arisc-msg/arisc_hdmi.py` hatte keinen Schalter dafür. Neu: **`--no-doorbell`** — `doorbell()` gibt dann
nur eine Zeile aus und schlägt nicht. Vorgabe bleibt „pulsen"; der Schalter ist ausdrücklich ein Messmittel.
Die Fassung liegt auch am Board unter `/root/arisc_hdmi.py`.

## Instrument geprüft, bevor gemessen wurde

Die Rückmeldung `classify/Handler gelaufen` unterscheidet nachweislich: im selben Lauf von `arisc_edid_init.sh`
meldete sie für `SetEDIDAudioMode`, `SET5VFlag` und `PullHotPlug-DOWN` **„NEIN (memset-Sonde 0/17 genullt)"**.
Ein „ja" ist also eine Aussage und kein Dauerwert.

## Messung

Harmloser Host-Unterbefehl `0x0311 SetEDIDVersion, arg1 = 2, arg2 = 0`, jeweils nach Kaltstart und `prep`.

| Lauf | Kaltstart | Reihenfolge | Ergebnis |
|---|---|---|---|
| 1 | 22:22:58 | A) mit Puls | `ja (15/17)` |
| 1 | | B) **ohne** Puls | `ja (15/17)` |
| 1 | | C) ohne Puls, Wiederholung | `ja (15/17)` |
| 2 (Gegenprobe) | 22:24:21 | 1) **ohne** Puls, **allererster Host-Unterbefehl seit dem Kaltstart** | `ja (15/17)` |
| 2 | | 2) ohne Puls, Wiederholung | `ja (15/17)` |
| 2 | | 3) mit Puls (Kontrolle) | `ja (15/17)` |

Lauf 2 war nötig, weil in Lauf 1 der gepulste Befehl zuerst kam und die ARISC „geweckt" haben könnte.

## Ergebnis

**Die ARISC verarbeitet Host-Unterbefehle auf Port 0 auch ohne Doorbell-Puls** — belegt in zwei
Kaltstart-Läufen, einmal davon als allererster Befehl. Paket B darf den Puls streichen; sein Treiber tut das
bereits und ist damit gedeckt. Pflichtlisten-Punkte #2/#8 sind damit **gelöst**, nicht „Stock-Verhalten".

## Zwei ehrliche Einschränkungen

1. **Restlicher Störfaktor:** `prep_after_boot.sh` lädt vor der Messung `hy310-arisc-hdmi.ko`, und dieses Modul
   pulst im eigenen Startup-Handshake. „Ohne Puls seit dem Kaltstart" gilt also für **meinen** Befehl, nicht für
   den gesamten Boot. Um das auszuschließen, müsste der Handshake selbst pulsfrei gefahren werden — das kann
   die Abnahme von Paket B leisten, deren Treiber ohnehin keinen Puls mehr schlägt. **Das ist der eigentliche
   Beweis, und er steht noch aus.**
2. Im Hänger um 22:37 stand `FIFO user1 P0 = 4` mit unverarbeitetem `0x2011` — an einem hängenden Gerät ist
   das aber kein Gegenbeleg, sondern womöglich die Folge des Hängers. Nicht als Widerspruch buchen.

## M3 kam nicht zustande — Ursache war das Gerät, nicht der Befehl (23:07)

J's exakte Vorschrift M3 (`0x0215 CheckEDIDUpdateStatus`, dreimal mit und dreimal ohne Puls) wurde angesetzt,
das Board war unmittelbar danach per SSH nicht mehr erreichbar.

**Es war kein Hänger durch den Befehl:** Marco hat gemeldet, dass ihm der **Beamer umgefallen** ist. Der
zeitliche Zusammenfall war Zufall. Ich hatte hier zunächst eine „Vorsichtsregel" notiert, ARISC-Unterbefehle
gehörten nicht in den laufenden Betrieb — **die ist aus dieser Beobachtung nicht belegt** und wieder entfernt.
Dagegen spricht ohnehin, dass um 22:19 zwei `SetEDIDVersion`-Aufrufe bei laufendem Bild ohne Zwischenfall
durchliefen.

Sachlich richtig bleibt nur, dass J's Vorschrift die Vorbereitungsphase vorsieht („nach Prep und
ARISC-Handshake, **vor** `arisc_edid_init.sh`") — dort gehört die Wiederholung hin, aus Gründen der
Vergleichbarkeit, nicht aus Angst vor einem Hänger.

**Der Stand der Puls-Frage bleibt der von 22:22–22:26** (zwei Kaltstart-Läufe mit `0x0311 SetEDIDVersion`,
einmal als allererster Befehl, jeweils „Handler gelaufen: ja"). M3 in J's Fassung mit dem rein lesenden
`0x0215` steht weiterhin aus.

## M3 nachgeholt (23:11–23:14) — und J's Sondenbefehl taugt nicht

Nach dem Kaltstart um 23:10 (Beamer wieder aufgestellt) in der **Vorbereitungsphase**, wie J es vorsieht:
nach `prep_after_boot.sh`, vor `arisc_edid_init.sh`.

### Erst der Instrumententest — und er fiel durch

J's Vorschrift nennt `0x0215 CheckEDIDUpdateStatus`, „harmlos, weil es nur liest". Ergebnis:

| Befehl | mit Puls | ohne Puls |
|---|---|---|
| `0x0215` direkt nach dem Prep | 3× **NEIN** (0/17) | 3× **NEIN** (0/17) |
| `0x2011 ResetEDIDModule` vorgeschaltet, dann `0x0215` | 3× **NEIN** (0/17) | 3× **NEIN** (0/17) |

**`0x0215` wird in diesem Zustand überhaupt nicht bearbeitet** — in beiden Armen gleich. Als Instrument für
die Pulsfrage ist es damit **wertlos**: es kann nicht zwischen „Puls nötig" und „Puls nicht nötig"
unterscheiden, weil es in keinem Fall antwortet. (Das deckt sich mit dem Befund aus `arisc_edid_init.sh`,
wo `CheckEDIDUpdateStatus` erst **nach** den acht EDID-Fragmenten sinnvoll ist.)

### Dann die Messung mit einem Befehl, den der Handler nachweislich verarbeitet

`0x2011 ResetEDIDModule` läuft (`ja`, memset-Sonde **16/17**) und ist idempotent — `arisc_edid_init.sh`
setzt ihn ohnehin als Schritt 1.

| Lauf | mit Puls | ohne Puls |
|---|---|---|
| 1 | ja (16/17) | ja (16/17) |
| 2 | ja (16/17) | ja (16/17) |
| 3 | ja (16/17) | ja (16/17) |

## Gesamtstand der Pulsfrage

Drei unabhängige Läufe, zwei verschiedene Unterbefehle, drei Kaltstarts:

| Beleg | Befehl | Ergebnis |
|---|---|---|
| 22:22, Lauf 1 | `0x0311 SetEDIDVersion` | ohne Puls: ja (2×) |
| 22:24, Lauf 2 (Gegenprobe) | `0x0311`, **allererster** Befehl seit Kaltstart | ohne Puls: ja (2×) |
| 23:13, Lauf 3 (M3) | `0x2011 ResetEDIDModule` | ohne Puls: ja (3×), mit Puls: ja (3×) |

**Die ARISC verarbeitet Host-Unterbefehle auf Port 0 ohne Doorbell-Puls.** Paket B darf ihn streichen;
Pflichtlisten-Punkte #2/#8 sind **gelöst**, nicht „Stock-Verhalten".

Die eine Restunsicherheit von oben bleibt bestehen und ist erst mit der Abnahme von Paket B erledigt:
`prep_after_boot.sh` lädt vorher das **alte** Modul `hy310-arisc-hdmi.ko`, das im eigenen Startup-Handshake
pulst. Der Treiber aus 0091 tut das nicht mehr — läuft dessen Abnahme durch, ist der Beweis vollständig.
