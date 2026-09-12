# Auflösungswechsel der Quelle — Nachtplan A.6 Punkt 4, erstmals gemessen (07.09., 07:55–08:05)

Der Nachtplan führt das als offen: „**Auflösungswechsel.** Nie gemessen. Erwartung: `SignalChange` mit
neuer Geometrie, WCE rechnet neu, Descriptor und AFBD-Crop müssen mitgehen. Gehört zu Paket E, sobald
`DV_TIMINGS` steht." Seit E abgenommen ist, ist es messbar.

## Aufbau

Board mit der integrierten Serie, `/dev/video1` (`sun50i-h713-hdmirx`) läuft, Signal steht.
Zuspieler von 1920x1080 auf **1280x720** und zurück, jeweils per
`DISPLAY=:0 xrandr --output HDMI-2 --mode …`. Nach jedem Wechsel: E's debugfs gelesen und zehn Bilder
mit `hdmirx_test` aufgezeichnet, ein Bild rekonstruiert.

## Ergebnis: die Erwartung trifft **nicht** zu

| | vor dem Wechsel | Quelle auf 1280x720 | zurück auf 1920x1080 |
|---|---|---|---|
| `signal:` | vorhanden | **vorhanden** (Flip-Zeiger wandern weiter) | vorhanden |
| `timings:` | 1920x1080p | **1920x1080p** — siehe Korrektur unten: **fest verdrahtet**, nicht veraltet | 1920x1080p |
| `format:` | NV16M 1920x1080 | **NV16M 1920x1080** — unverändert | NV16M 1920x1080 |
| `SignalChange:` | 0 mal | **0 mal** — der Callback feuert **nicht** | 0 mal |
| `SOURCE_CHANGE` im Test | — | **0** | 0 |
| INCAP `+0x104` | zählt | zählt weiter (+61/s) | zählt |
| Bilder geliefert | 60/60 | **10/10** — formal fehlerfrei | 10/10 |

**Alles meldet Erfolg, und der Inhalt ist trotzdem Müll.** Das rekonstruierte Bild bei 720p
(`re/captures/weltneuheit/ours-20260907-nacht/E/frame720.png`) zeigt oben das 720p-Bild **dreifach
nebeneinander und zerrissen** — die neue Geometrie wird in einen Ring geschrieben, dessen Zeilenabstand
noch 1920 ist, also wickelt sich jede Zeile um —, und darunter steht unverändert der **alte
1080p-Inhalt** von vor dem Wechsel.

**Der Rückweg ist sauber:** zurück auf 1920x1080 liefert wieder ein einwandfreies Bild
(`frame1080-zurueck.png`), ohne Zutun, ohne Kaltstart.

## Was das für die Pakete heißt

1. **Paket E:** `QUERY_DV_TIMINGS` liefert nach einem Auflösungswechsel einen **veralteten** Wert, und
   `V4L2_EVENT_SOURCE_CHANGE` feuert nicht. Beides ist heute an den `SignalChange`-Callback der Firmware
   gehängt — und der kommt bei einem reinen Geometriewechsel offenbar **nicht**. Ein Verbraucher, der sich
   auf `SOURCE_CHANGE` verlässt, merkt den Wechsel nie. Das ist die eigentliche Lücke.
2. **Paket F:** ein Umschalter, der nur auf `SOURCE_CHANGE` hört, zeigt nach einem Auflösungswechsel
   stillschweigend ein zerrissenes Bild. Er braucht ein zweites Kriterium.
3. **Zur Abgrenzung:** bei Signal**verlust** feuert der Callback sehr wohl — das ist in
   `K4-hotplug.md` am Gerät belegt (`port1 invalid signal`, `CallbackOfSignalChange`,
   `NotifySignalChange`). Es betrifft also gezielt den Geometriewechsel bei durchgehendem Signal.

## Offen

- **Woran ein Geometriewechsel erkennbar wäre**, ohne zu pollen. Kandidaten, die noch niemand gelesen hat:
  die INCAP-Timing-Register, die die Firmware bei jedem Lock neu rechnet (im elog sichtbar als
  `numTotalPixelsPerLine`, `numActiveLines`, `offsetFirstActivePixel` — siehe `K4-hotplug.md`), und der
  Composition-Block `0x05000224`/`0x05000844` (doku/89), der die Panel-Geometrie trägt.
  **Messvorschrift:** vor und nach einem `xrandr --mode`-Wechsel `dump_state.py` ziehen und die Blöcke
  `0x0694` und `0x0500` diffen; was sich mitbewegt, ist der Kandidat für den Auslöser.
- Ob ein Wechsel auf eine Auflösung, die die Firmware nicht kennt, anders ausgeht.


---

## Korrektur 08:55 — die DV-Timings sind nicht „veraltet", sie sind **fest verdrahtet**

Oben stand, `QUERY_DV_TIMINGS` liefere nach dem Auflösungswechsel einen **veralteten** Wert. Das
unterstellt, der Wert würde sonst mitlaufen. Er läuft nie mit. Im erzeugten Baum:

```c
static const struct v4l2_dv_timings h713_hdmirx_timings =
        V4L2_DV_BT_CEA_1920X1080P60;                      /* sun50i-h713-hdmirx.c:1017 */
...
        *t = h713_hdmirx_timings;                         /* query_dv_timings, :1280   */
```

und die Fähigkeitsgrenzen klemmen `min_width == max_width == 1920`, `min_height == max_height == 1080`,
`min_pixelclock == max_pixelclock == 148500000`. `QUERY_DV_TIMINGS` gibt also **immer** 1920x1080p60
zurück, solange überhaupt ein Signal anliegt (sonst `-ENOLINK`) — unabhängig davon, was die Quelle sendet.

**Folgen:**

1. **Die Aussage „nach dem Wechsel stehen veraltete Timings" ist falsch.** Richtig: der Treiber hat
   nie andere Timings gehabt. Dass sie bei 1080p stimmten, ist Zufall der Konstante.
2. **Ein Vergleich zweier `QUERY_DV_TIMINGS`-Abfragen kann einen Auflösungswechsel strukturell nie
   erkennen.** Paket F hat aus genau diesem Grund darauf verzichtet, ein zweites Kriterium darauf zu
   bauen — richtig entschieden: eine Prüfung, die nie feuert, ist derselbe Fehlertyp wie eine
   geratene Wartezeit.
3. **Der Auslöser gehört in `0094`.** Die echten Timings stehen in der Signal-Info, die der
   `SignalChange`-Callback per `Para[2]` als Shmem-Zeiger liefert (Layout-Entwurf:
   `analyse/hdmi-seq/signal_info_buf.py`). Paket E hat in seinem eigenen Log darum gebeten, die
   11 Rohwörter dieser Struktur einmal mit und einmal ohne Signal mitzuschreiben — **genau diese
   Messung** ist jetzt der nächste Schritt, denn sie entschlüsselt das Layout und macht die Timings
   echt.

## Was dadurch an der E-Abnahme zu korrigieren ist

Die Zeile `QUERY_DV_TIMINGS: 1920x1080p, 148 MHz Pixeltakt` aus dem Abnahmelauf ist **kein Beleg** —
sie hätte bei jeder Quellauflösung dasselbe gedruckt. Die E-Abnahme steht unverändert auf dem, was
sie wirklich zeigt: `/dev/video1` existiert und probt, `S_INPUT` setzt die Quelle, **60 von 60
Bildern** geliefert, der Vsync-Notifier zählt 287 Ereignisse, und das rekonstruierte Bild 29 ist ein
**pixelgenauer Screenshot der Quelle**. Das trägt; die Timing-Zeile nicht.
