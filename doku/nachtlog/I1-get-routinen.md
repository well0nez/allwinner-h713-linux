# I1 — Die `Get*`-Routinen der Firmware liefern konstant 0

07.09.2026, 12:35–12:55 · Board-Sitzung · Paket I (`0101`)

## Wie es aufgefallen ist

Der Entwurf von Paket I fragte beim Probe für jedes Control `THal_Vp_Get<Größe>` ab und nahm die
Antwort als Ist- **und** Vorgabewert. Er hatte dafür eine Selbstprüfung eingebaut: die Init-Sequenz
setzt TNR, SNR, DCI und die Schwarzdehnung auf bekannte Werte, also lassen sich vier der neun
Antworten gegen etwas halten. Beim ersten Kaltstart mit dem Patch:

```
THal_Vp_GetTNR liefert 0, die Init-Sequenz hat 2 gesetzt
THal_Vp_GetSNR liefert 0, die Init-Sequenz hat 1 gesetzt
THal_Vp_GetDCI liefert 0, die Init-Sequenz hat 2 gesetzt
THal_Vp_GetBlackExtension liefert 0, die Init-Sequenz hat 1 gesetzt
Bildwerte: 9 von 9 aus der Firmware gelesen, 0 von 4 gegen die Init-Sequenz bestaetigt
```

**Genau dafür war die Prüfung da, und sie hat gehalten.** Offen blieb: liegt die Rückfrage falsch
oder die Erwartung?

## Die Gegenprobe entscheidet es

Register gelesen, unmittelbar danach dieselben Größen erfragt:

| | Register | Rückfrage |
|---|---|---|
| SNR | `0x05001248[7:0]` = **1** | `GetSNR` → 0 |
| DCI | `0x0500123C[7:0]` = **2** | `GetDCI` → 0 |

Die Register bestätigen die Init-Sequenz. Die Rückfrage liegt falsch.

Und der Fall, der nichts offenlässt — erst schreiben, dann fragen:

```
v4l2-ctl --set-ctrl=contrast=80   ->  0x05001234 = 0x00500000   (0x50 = 80 in [31:16])
THal_Vp_GetContrast               ->  ok, 1 value(s) 0x00000000
```

Der Schreibweg wirkt nachweislich, und die Rückfrage sagt trotzdem 0. Dasselbe für
`GetBrightness`, `GetSaturation`, `GetHue`, `GetSharpness` — **alle fünf konstant 0**. Auch
`THal_Vp_GetSource` antwortet 0, während die Quelle auf HDMI-1 steht.

Die Übertragung ist dabei in Ordnung: `ok, 1 value(s)` — ein Rückgabewort, wie die Dekompilate es
beschreiben. Die Firmware liefert die Null selbst.

## Was daraus folgt

Die `Get*`-Routinen sind als Quelle unbrauchbar. Sie sind aus `0101` **ersatzlos entfernt** — samt
dem `.get`-Feld der Tabelle, damit niemand sie versehentlich wiederbelebt. Die Startwerte kommen
jetzt aus dem, was der Treiber ohnehin weiß:

* **vier Menüs** (TNR, SNR, DCI, Schwarzdehnung): aus der eigenen Init-Sequenz-Tabelle gelesen, nicht
  ein zweites Mal aufgeschrieben. Die Register bestätigen diese Werte.
* **fünf Skalare**: 0, der Ruhewert von `0x05001234`, `0x05001238` und `0x05001228` auf diesem Board.

Der Ersatzwert 50 aus `pq_picturemode.ini` wäre falsch gewesen: das ist der Startwert der
Vendor-**Oberfläche**, nicht der Zustand, in dem die Hardware hochkommt. Ihn anzukündigen wäre eine
Behauptung über ein Register, das dieser Treiber nie beschrieben hat.

Beim Kaltstart danach:

```
Bildwerte: 4 von 9 aus der Init-Sequenz, der Rest im Ruhewert
temporal_noise_reduction  default=2 value=2 (Middle)
spatial_noise_reduction   default=1 value=1 (Low)
dynamic_contrast          default=2 value=2 (Middle)
black_extension           default=1 value=1 (Low)
```

Keine Warnung mehr, und die Werte stimmen mit den Registern überein.

## Nebenbei belegt: `hue` und `sharpness`

Beide standen im Entwurf als **[D]** — aus der Vendor-Datei erschlossen, am Gerät nie gemessen.
Jetzt gemessen:

| gesetzt | `hue` → `0x05001238[31:16]` | `sharpness` → `0x05001228[23:8]` |
|---|---|---|
| 25 | `0x19` = 25 | `0x19` = 25 |
| 75 | `0x4B` = 75 | `0x4B` = 75 |
| 100 | `0x64` = 100 | `0x64` = 100 |

Die Registerzuordnung im Entwurf stimmt für beide.

**Und eine dritte Warnung vor dem blinden Kriterium.** Die Bildwirkung von `hue 100` maß
`wandcheck.py` mit **0,08 %** der Bildpunkte über der Schwelle — also praktisch nichts. Das Bild
zeigt etwas anderes: das rote Logo ist grüngrau, die ganze Seite kippt ins Grün-Violette. Der
Grund ist derselbe wie heute Morgen bei der Helligkeit: `wandcheck.py` rechnet in **Graustufen**,
und eine Farbtonverschiebung ändert die Helligkeit kaum. Das Kriterium konnte nicht anschlagen.
**Für Farbregler ist `wandcheck.py` kein Nachweis — man muss das Bild ansehen.**

---

## Korrektur 13:05 — der Ruhewert 0 ist kein Istwert. Meine erste Korrektur war falsch.

Oben steht, die Vorgabewerte der fünf Skalare seien 0, „der Ruhewert von `0x05001234`,
`0x05001238` und `0x05001228` auf diesem Board", und der Vendor-Wert 50 wäre „der Startwert der
Oberfläche, nicht der Zustand, in dem die Hardware hochkommt". **Das ist widerlegt**, und zwar von
der einfachsten möglichen Probe: hinsehen.

| Zustand | Register `0x05001238[31:16]` | Wand |
|---|---|---|
| nach dem Booten, nie geschrieben | `0x0000` | Farben richtig, Logo **rot** |
| `hue = 100` | `0x0064` | kippt ins **Grüne**, Logo grüngrau |
| `hue = 0` | `0x0000` — **derselbe Wert wie beim Booten** | Logo **blau** |
| `hue = 50` | `0x0032` | Farben wieder richtig, Logo **rot** |

Zeile 1 und Zeile 3 haben denselben Registerinhalt und ein völlig verschiedenes Bild. Daraus folgt:

**Ein Register auf 0 heißt hier nicht „der Wert 0 wirkt", sondern „die Firmware wendet diesen
Regler noch gar nicht an".** Das erste `Set` schaltet ihn ein; von da an ist 0 der volle Ausschlag
nach unten. Die Gegenprobe mit allen fünf zusammen auf 50 gibt exakt das Boot-Bild zurück
(`0x05001234 = 0x00320032`, `0x05001238 = 0x00320032`, `0x05001228 = 0x01003200`,
Chroma-Gain `0x14400000` = `floor(50 × 1,28)` = 0x40).

Die Vorgabewerte stehen deshalb wieder auf **50**, wie im Entwurf des Agenten. Mein Schluss vom
Registerinhalt auf den Istwert war der Fehler — dieselbe Art Fehlschluss wie die
Brightness-Messung heute Morgen, nur andersherum: dort hat ein Kriterium nicht anschlagen können,
hier hat eine Beobachtung eine Bedeutung bekommen, die sie nicht trägt.

Was von der ersten Korrektur **bleibt**: die `Get*`-Rückfrage ist und bleibt draußen. Die ist
unabhängig davon gemessen und unabhängig davon falsch.

Und daraus folgt die zweite Auflage, die jetzt im Kommentar steht: **`v4l2_ctrl_handler_setup()`
darf nicht gerufen werden.** Ein Vorgabewert, den anzukündigen richtig ist, ist nicht automatisch
einer, den zu schreiben richtig ist — beim Booten wendet die Firmware die fünf Regler noch nicht
an, und der Treiber hat keinen Grund, das zu ändern.

## Nebenbefund: zwei Schreiber auf dem Chroma-Gain

`0x05140508` hat zwei Herren. `THal_Vp_SetSaturation` schreibt das Gain-Byte
(`floor(Argument × 1,28)`), und der Anzeigetreiber schreibt beim Einschalten der Plane dasselbe
Register aus der Plane-Eigenschaft `saturation` (`sun50i-h713-afbd.c`, `route_regs + 0x508`).
Beobachtet: nach `V4L2_CID_SATURATION = 0` stand dort später wieder `0x144C0100`, also Gain 0x4C —
der Vorgabewert des Anzeigetreibers, nicht der gesetzte Wert.

Das ist kein Fehler in `0101`, aber eine Falle: wer die Sättigung über V4L2 setzt und danach die
Plane neu einschaltet, verliert seinen Wert. Für Paket I ist die Frage nicht entschieden, welcher
der beiden Wege der richtige ist. **Offen.**
