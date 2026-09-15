# I2 - Der Chroma-Gain hat zwei Schreiber, und das V4L2-Control lügt dabei

07.09.2026, 13:20 · Board-Sitzung · Pakete D/I, Vorarbeit zum neuen Plan

## Der Befund in einer Tabelle

Gemessen auf dem Stand `381eef47`, ein Durchgang, `0x05140508` nach jedem Schritt gelesen:

| Schritt | `0x05140508` | Gain `[23:16]` |
|---|---|---|
| 1. Plane aus, nichts gesetzt | `0x04000000` | `0x00` |
| 2. Plane an (`hy310-tv`) | `0x144C0000` | **`0x4C`** - Vorgabe des Anzeigetreibers |
| 3. `V4L2_CID_SATURATION = 100` | `0x14800000` | `0x80` = `floor(100 × 1,28)` ✓ |
| 4. Plane aus | `0x04000000` | `0x00` |
| 5. Plane wieder an | `0x144C0000` | **`0x4C` - der gesetzte Wert ist weg** |

Und danach meldet `v4l2-ctl --get-ctrl=saturation` weiterhin **100**.

## Was daran schlimmer ist als bisher beschrieben

Bisher stand im Nachtlog nur, dass „der Wert verlorengeht". Der eigentliche Schaden ist, dass
**das Control weiter behauptet, er sei gesetzt.** Das ist dieselbe Fehlerart wie die Vorgabewerte
von heute Mittag: eine Schnittstelle sagt etwas über die Hardware, das die Hardware widerlegt.
V4L2 hat dafür kein Schlupfloch - `G_CTRL` soll den geltenden Wert liefern.

Der Verlust braucht dabei **kein** Zutun des Benutzers: jedes Aus- und Einschalten der Video-Plane
genügt, und das passiert bei jedem Signalwechsel, seit F auf die Konsole zurückfällt und wieder
zurückschaltet. In der Praxis überlebt eine über V4L2 gesetzte Sättigung also den nächsten
Signalverlust nicht.

## Das obere Byte ist erklärt

`0x04` gegen `0x14` in `[31:24]` stand als „nicht erklärt" im Nachtlog. Es ist keins:

* `H713_VIDEO_GAIN` ist im Anzeigetreiber die **ganze Wortkonstante** `0x144c0000`
  (`sun50i-h713-afbd.c:142`), aus der beim Einschalten nur das Sättigungsfeld ersetzt wird
  (`:915`). Das `0x14` kommt also von uns.
* `0x04000000` ist der beim Probe gelesene Ruhewert `h->gain_idle` (`:1735`), den der
  Abschaltpfad zurückstellt (`:747`).

Damit sind beide Werte Treiberverhalten und keine Firmware-Eigenheit.

## Die drei Schreiber, genau benannt

1. **`THal_Vp_SetSaturation`** (Firmware-RPC, über `V4L2_CID_SATURATION` aus `0101`) - schreibt
   `floor(Argument × 1,28)` ins Gain-Byte, belegt in `K5-board-verifikation.md` (f) und oben
   Schritt 3.
2. **Der Anzeigetreiber beim Einschalten der Plane** - schreibt `H713_VIDEO_GAIN` mit der
   DRM-Plane-Eigenschaft `saturation` (Vorgabe `H713_VIDEO_SAT_DEFAULT = 0x4c`).
3. **Der Anzeigetreiber beim Abschalten der Plane** - stellt `gain_idle` zurück.

Schreiber 2 und 3 wissen nichts von 1.

## Was das für den Plan heißt

Die Frage ist nicht „wie synchronisiert man die beiden", sondern **wem der Regler gehört**. Drei
Möglichkeiten, alle mit Folgen:

* **Dem V4L2-Knoten.** Dann darf der Anzeigetreiber das Register nicht mehr aus eigener Vorgabe
  beschreiben - und die Plane-Eigenschaft `saturation` samt `hy310-tv -s` fällt weg oder wird zum
  Durchreicher.
* **Dem DRM-Knoten.** Dann gehört `V4L2_CID_SATURATION` nicht angeboten, und die Formel
  `floor(x × 1,28)` gehört in den Anzeigetreiber statt in den RPC.
* **Beiden, mit einem gemeinsamen Eigentümer des Registers.** Das ist der ehrlichste Weg und der
  teuerste: einer der beiden Treiber besitzt `0x05140508`, der andere ruft ihn.

Zu entscheiden ist das nicht nach Geschmack, sondern danach, **wo der Wert hingehört**: die
Sättigung ist eine Eigenschaft des angezeigten Bildes, nicht der Aufnahme - aber der einzige Weg,
sie über die Firmware-Kennlinie zu setzen, führt über den RPC, den nur der Aufnahmetreiber hat.
Genau das ist die Abwägung, die der Plan treffen muss.

## Was **nicht** gemessen ist

* Ob `THal_Vp_SetSaturation` ausser dem Gain-Byte und `0x05001238[15:0]` noch etwas anfasst.
  K5 (f) hat nach Abzug der Zähler „genau zwei Wörter" gefunden - für die Sättigung, nicht für
  alle Werte.
* Ob die Firmware den Gain nach eigenem Ermessen nachzieht (etwa bei einem Bildmoduswechsel).
* Ob `[15:8]` und `[7:0]` des Registers eine Bedeutung haben. In Schritt 3 stand dort `0x0000`,
  in einer früheren Messung `0x0100`. Wodurch, ist offen.
