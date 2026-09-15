# Die Video-Plane: NV16 aus dem HDMI-Capture-Ring (Patch 0093)

**Stand 07.09.2026, vormittags - am Gerät abgenommen (Abschnitt 0).** Grundlage: [76-plan-ch0-de.md](76-plan-ch0-de.md) §§10-13 (Registersatz,
Farbe, Fallen), [78-nachtplan-hdmi-switch.md](78-nachtplan-hdmi-switch.md) Abschnitt 3 „D",
[nachtlog/A-patches.md](nachtlog/A-patches.md) §5 (was 0078 wirklich schreibt),
[81-pq-datenmodell.md](81-pq-datenmodell.md) (Sättigung). Registerabzüge:
`re/captures/weltneuheit/ours-20260906-source0/` (`01_lock` … `05_after_hpd`), Fotos ebenda unter `fotos/`.

Dieses Dokument beschreibt, **was der Treiber schreibt und warum** - Register für Register, mit dem Beleg für
jeden Wert. Es ist die Referenz für die Abnahme und für jeden, der später an der Plane arbeitet.

> **Nachtrag 07.09.2026, 06:19.** Die Flip-Zeiger `+0x320/+0x324` sind seit dieser Nacht nicht mehr nur
> Treiber-intern: 0093 exportiert sie als **Vsync-Notifier** (`include/linux/soc/sunxi/h713-afbd.h`), damit
> der V4L2-Treiber 0094 sie nicht ein zweites Mal abbildet. Siehe [Abschnitt 5.1](#51-der-vsync-notifier--die-flip-zeiger-als-kernel-schnittstelle)
> und [nachtlog/DE-vsync-notifier.md](nachtlog/DE-vsync-notifier.md).

---

## 0. Stand am Gerät

**Abgenommen am 07.09.2026** - in zwei Anläufen, mit einem echten Fehler dazwischen. Die Reihenfolge
gehört zum Beleg, deshalb steht sie hier vollständig:

| Zeit | Schritt | Ergebnis |
|---|---|---|
| 05:58-06:10 | erste Abnahme ([D-abnahme-board.md](nachtlog/D-abnahme-board.md)) | Bild aus der Plane, NV16, Ring-Folge wandert (`+0x070`: `0x4C3EF000 → 0x4C5EE000`), Farbreiz ändert 38,74 % der Bildpunkte im ROI. **Aber:** der C-Stride stand nur, weil ihn ein früherer Skriptlauf hinterlassen hatte |
| 06:15 | `+0x044` im Sekundentakt über 22 s | bleibt `0x0780` - der **erste** Enable nach einem Kaltstart setzte den NV16-Stride nicht durch (Foto `D/D-10-erstenable-cstride-falsch.jpg`: Farbe quillt aus ihren Kanten) |
| 06:50-07:05 | sechs Läufe, drei Ausgänge ([D-cstride-befund.md](nachtlog/D-cstride-befund.md)) | der Ausgang hängt am **Vorzustand**, nicht am Wert; zwei Zwischenhypothesen dabei widerlegt |
| 07:10-08:30 | Ursache und Änderung ([D-cstride-fix.md](nachtlog/D-cstride-fix.md)) | Descriptor-Veröffentlichung und Registersatz lagen in **einem** Commit - Ursache ist das Signalereignis, [Abschnitt 4.1](#41-das-signalereignis-und-der-chroma-stride) |
| ~08:30 | zweite Abnahme, **fünf Teile** | `+0x044` geht **aus jedem Vorzustand** auf `0x0F00` und beim Abschalten zurück auf `0x0780` |

Die fünf Teile (Vorschrift: [D-cstride-fix.md](nachtlog/D-cstride-fix.md) §4; Belegfoto
`re/captures/weltneuheit/ours-20260907-nacht/D2/D2-A-erstenable.jpg`, ROI-mean 184,91):

| Teil | Was er prüft | Ergebnis |
|---|---|---|
| **A** | Erst-Enable nach Kaltstart, `+0x098` vorher `0` | `+0x044 = 0x0F00` |
| **B** | der zweimal reproduzierte Fehlerfall aus `afbd_source0.py off` | `+0x044 = 0x0F00` - **hier blieb vorher `0x0780`** |
| **C** | Markenmessung: `0x00000044` von Hand, im **Fehler**-Vorzustand | `+0x044 = 0x0F00` |
| **D** | Rückstellung beim Abschalten | `+0x044 = 0x0780`; der Zeiger `+0x098` bleibt stehen, absichtlich |
| **E** | drei Zyklen an/aus hintereinander | jedes Mal `0x0F00` an, `0x0780` aus |

**Warum diese Abnahme scheitern konnte, und die erste nicht.** Teil B ist genau der Lauf, der vorher
zweimal `0x0780` ergeben hat; Teil D prüft eine Rückstellung, die es vor dem 07.09. gar nicht gab. Die
Abnahme vom 06:10 dagegen lief über einen Zustand, in dem `0x0F00` schon vom Skript stand - sie konnte
nicht scheitern und hat deshalb einen kaputten Erst-Enable durchgewinkt. Das ist derselbe Fehlertyp, der
in dieser Sitzung noch zweimal zugeschlagen hat (`portmap: 0,1,2`, `QUERY_DV_TIMINGS`): **ein Kriterium,
das nicht scheitern kann, prüft nichts.**

**Was die Abnahme *nicht* entscheidet.** Ob die Klammer aus Abschnitt 4.1 wirklich gegriffen hat oder in
ihre Frist gelaufen ist, trennt allein die Zeile `did not reprogram the chroma stride` im `dmesg`: bei
Fristablauf programmiert der Treiber Source 0 **trotzdem**, das Ergebnis ist dann ebenfalls `0x0F00`. In
den vorliegenden Protokollen ist dieser `grep` nicht festgehalten, obwohl
[REGEL1-0093-0095.md](nachtlog/REGEL1-0093-0095.md) §4 M1 ihn ausdrücklich als Beifang der Läufe A und B
verlangt. Solange er fehlt, bleibt Abschnitt 8 Punkt 1 offen - die Wirkung ist belegt, der Mechanismus
nicht.

**Beifang aus demselben Boot** (REGEL1 §M2, 09:16): über sämtliche Plane-Zyklen - Erst-Enable, Fehlerfall
aus dem Skriptzustand, Markenmessung, drei Wiederholungszyklen und die Läufe von Paket F - steht
`READY did not clear` **kein einziges Mal** im Log. Die 50-ms-Frist aus `0078` läuft also nicht ab und
verdeckt derzeit nichts.

**Der Vsync-Notifier ist mitabgenommen** (Abschnitt 5.1): im Abnahmelauf des V4L2-Treibers zählt er
**287 Ereignisse**, `/dev/video1` liefert **60 von 60** Bildern, und das rekonstruierte Bild ist ein
pixelgenauer Screenshot der Quelle ([A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md),
Korrektur 08:55).

---

## 1. Was die Plane ist

`video-0` ist **AFBD Source 0**, der Videokanal des Scanout-Blocks. In **unserer** Konfiguration ist der Weg
dahinter exklusiv: entweder Source 0 **oder** der RGB-Kanal (`+0x140`, unsere Konsole) erreicht den
LVDS-Encoder - keine Mischung (doku/76 §10 und §11.6).

**Korrektur 07.09.:** das ist eine Eigenschaft unserer Konfiguration, **nicht** der Hardware. Stock fährt in
`0x051C006C` denselben Wert `0x39000000` wie wir für „Video" und zeigt trotzdem sein Menü - der Unterschied
ist, dass Stock **AFBD-Kanal 1 aktiv und bedient** hat (`0x05600100 = 0x83001901`); das OSD wird dort **vor**
dem PROC in die YUV-Kette gemischt, nicht am Selektor ([K5-K6-re.md](nachtlog/K5-K6-re.md), K6). Die Stufe,
die OSD und Video zusammenführt, ist damit weiter **nicht gefunden**, und ein Overlay im Wortsinn gibt es für
uns heute nicht - aber die Begründung „die Hardware kann es nicht" trägt nicht mehr.

Die Quelle ist der HDMI-Capture-Ring: die MIPS-Firmware schreibt das HDMI-Bild als **NV16** (Chroma in voller
Höhe, YUV mit Cb/Cr um 128) in drei Slots im Carveout `mips_framebuf` und dreht ein Zeigerpaar mit 60 Hz durch
diese Slots.

| | Slot 0 | Slot 1 | Slot 2 |
|---|---|---|---|
| Y | `0x4C3EF000` | `0x4C5EE000` | `0x4C7ED000` |
| C | `0x4C9EC000` | `0x4CBEB000` | `0x4CDEA000` |

Die Adressen stehen hier **nur zur Orientierung**. Der Treiber kennt sie nicht: er liest das Paar aus
`+0x320/+0x324` und prüft es gegen die Grenzen des DT-Knotens.

---

## 2. Der Registersatz, Wert für Wert

Basis AFBD `0x05600000`, PROC/„route" `0x05140000`, LVDS `0x051C0000`. Alle Werte sind am 06.09.2026 nach
Kaltstart dreimal reproduziert worden (doku/76 §13).

### 2.1 Was der Treiber schreibt

| Register | Wert | Begründung |
|---|---|---|
| `+0x140` / `+0x144` | `(gemerkt \| Bit31) & ~Bit0`, dann `1` | RGB-Kanal stilllegen und committen. Der Mux ist exklusiv, also muss RGB **vor** Source 0 aus. Der gemerkte Wert stammt aus dem Probe (`0x03001901` auf unserem Board) - nichts geraten. |
| `+0x020` | `((align16(h) − 1) << 16) \| (w − 1)` | Bildgröße minus 1, Höhe auf eine ganze Blockzeile aufgerundet. 1280×720 → `0x02cf04ff`, 1920×1080 → `0x043f077f`. **Beide Werte sind Messwerte**, nicht Theorie: der erste ist der, den 0078 fest verdrahtet hatte, der zweite der, den die Firmware für die HDMI-Capture programmiert (`03_source0.txt`). Die Formel ist die einzige, die beide trifft. |
| `+0x024` | `((h/16 − 1) << 16) \| (w/16 − 1)` | Blockzahl minus 1; der AFBD arbeitet in 16×16-Blöcken. 1280×720 → `0x002c004f`, 1920×1080 → `0x00420077`. Bei 1080 wird **abgerundet** (67 Blockzeilen, nicht 68) - genau das steht im Firmware-Abzug. |
| `+0x040` | `fb->pitches[0]` | Y-Zeilenabstand. Bei uns 1920 = `0x780`. |
| `+0x044` | NV16: `2 × pitch`, NV12: `pitch` | **Der Kern des Pakets**, siehe Abschnitt 3. Bei uns `0x0F00` = 3840. Der einzige Wert des Satzes, der dem Descriptor **widerspricht** - deshalb der einzige, den ein Signalereignis der Firmware wieder einkassiert (Abschnitt 4.1). |
| `+0x048` | `(h << 16) \| w` | Luma-Crop-Fenster. Bei uns `0x04380780`. 0078 hat dieses Register **gar nicht** geschrieben und sich darauf verlassen, was die Firmware hinterließ. |
| `+0x04C` | `((h/2) << 16) \| w` | Chroma-Crop-Fenster - **halbe Höhe, auch bei NV16**. Der Leser ist und bleibt ein NV12-Leser; ihm wird gesagt, was er zu lesen glaubt. Bei uns `0x021C0780`. |
| `+0x060` | `1` | Gate auf. Die Firmware setzt später selbst Bit 4 dazu (`0x11`, Stock-Wert) - das ist ihre Sache, der Treiber schreibt es nicht zurück. |
| `+0x064` | `0` | Feld: progressiv. |
| `+0x068` | `0x122` | Ring-Modus: Source 0 liest aus **pool 1**, den vier Slots ab `+0x070`. Denselben Wert setzt die Firmware auch selbst. |
| `+0x098` … `+0x0A4` | Descriptor-Adresse | Die vier VideoInfo-Slots. **Der Zeiger, dem die MIPS folgt** (Abschnitt 4). Wird **mit** dem Descriptor veröffentlicht, also einmal beim Übergang aus/an - nicht mehr bei jedem Commit (Abschnitt 4.1). |
| `+0x080` / `+0x094` / `+0x0A8` | `0` | Aux-Slots aus. |
| `+0x070` … `+0x07C` | Y-Adresse | Vier Slots, alle mit demselben Wert. |
| `+0x084` … `+0x090` | C-Adresse | dito. |
| `+0x06C` | `1` | **Dirty-Latch**: übernimmt die Adressen. Verbraucht sich (liest danach 0). |
| `route +0x508` | `0x14000000 \| (sat << 16)` | Chroma-Gain. Nur Bits [23:16] werden ersetzt, der Rest ist der Stock-Wert im HDMI-Betrieb. Default `0x4C`. **Korrektur 07.09.:** das ist nicht „Sättigung 50", sondern der Vorgabewert der Firmware und entspricht `SetSaturation` **60** - die Firmware bildet linear ab, `Gain = floor(Wert × 1,28)`, **fünf** Messpunkte am Gerät (0, 50, 59, 60, 100 - [K5-board-verifikation.md](nachtlog/K5-board-verifikation.md) (f)). `SetSaturation` und dieser Gain sind **derselbe** Regler, nicht zwei; wer beide bedient, überschreibt sich selbst. `0x04000000` = Chroma aus, das ist der Ruhewert, auf den `disable` zurückstellt. |
| `+0x010` | `0x03000013` (Bits [14:8] = 0) | Source 0 an, Formatcode **0** = der NV12-Leser. Bit 31 gehört der Firmware und bleibt aus. |
| `+0x014` | `1` | **Ready-Latch**, übernimmt die Konfiguration am nächsten Vsync. Verbraucht sich. |
| `lvds +0x06C` | `0x39000000` | Selektor auf Video (`0x29000000` = RGB). |

### 2.2 Was der Treiber liest - und nur liest

| Register | Bedeutung |
|---|---|
| `+0x320` / `+0x324` | Die Flip-Zeiger der Firmware, Y und C. Drehen mit 60 Hz durch die drei Ring-Slots und nennen **immer denselben Slot-Index** (`0x4c3ef000`↔`0x4c9ec000`, `0x4c5ee000`↔`0x4cbeb000`, `0x4c7ed000`↔`0x4cdea000` in jedem Abzug). Daraus folgt: kein Slot-Tabelle nötig, das Paar wird genommen, wie es steht. **Dieser Treiber ist ihr einziger Leser** und reicht sie über den Vsync-Notifier weiter (Abschnitt 5.1). |

### 2.3 Was der Treiber bewusst **nicht** anfasst

| Register | Grund |
|---|---|
| `+0x030` | Firmware-eigen; steht bei uns korrekt auf `0x04380780`. 0078 fasst es auch nicht an. |
| `+0x038` | **W1C-Statusregister**, kein Modusregister (doku/76 §11.6). |
| `+0x300` / `+0x304` / `+0x310` | Pool-2-Steuerworte. Vom ARM **nicht beschreibbar** - Schreiben und Rücklesen ergibt den alten Wert (doku/76 §11.4). |
| `+0x100` ff. (ch1) | Stocks eigener Weg für das HDMI-Bild; bei uns nicht aktiv. Offener Versuch, nicht Gegenstand von D. |
| INCAP `0x0694xxxx` | **Niemals schreiben.** Bit 31 in `0x0928/0x0968` von Hand zu setzen liefert genau einen Rahmen und verklemmt die Capture danach (doku/76 §13). Der Treiber liest die INCAP nicht einmal. |

### 2.4 Latches, W1C und firmware-eigene Bits - die Merkliste

* `+0x014` (Ready) und `+0x06C` (Dirty) sind **Latches**: schreiben, dann liest man 0. Ein Wert, der beim
  Rücklesen 0 ist, ist nicht „verlorengegangen", sondern verbraucht.
* `+0x038` ist **write-1-to-clear**.
* **Bit 31 in `+0x010` gehört der Firmware** - sie setzt und löscht es; unser Wert hat es aus.
* `+0x060` Bit 4 setzt die Firmware selbst dazu.
* `+0x300/+0x304/+0x310` ignorieren CPU-Schreibzugriffe vollständig.
* **Der Descriptor-Zeiger `+0x098` ist kein gewöhnliches Register**, sondern ein Anstoß an die Firmware:
  ändert er sich, programmiert die WCE Source 0 aus dem Descriptor nach (Abschnitt 4.1).

---

## 3. Warum NV16 ohne Formatwechsel geht

Source 0 hat **einen** linearen Leser, und der ist ein NV12-Leser: für Ausgabezeile *r* holt er Chromazeile
⌊r/2⌋. NV16 hat pro Bildzeile eine Chromazeile. Mit dem einfachen Zeilenabstand landet Chromazeile ⌊r/2⌋ also
auf Bildzeile ⌊r/2⌋ statt auf *r* - die Farbe ist **vertikal 2× gedehnt, oben verankert** (Belegfoto
`fotos/ok1.jpg`, doku/76 §13).

Verdoppelt man den Chroma-Zeilenabstand, liegt Chromazeile ⌊r/2⌋ bei Byte-Offset ⌊r/2⌋ × 2 × pitch - das ist
Zeile *r* des NV16-Puffers. Ergebnis: **exaktes 4:2:2 aus einem NV12-Leser, ein Register, eine Ursache**
(Belegfoto `fotos/cstride.jpg`).

Der naheliegende Gegenweg, den Formatcode auf 4:2:2 zu stellen (`+0x010 = 0x03000213`), ist gemessen und
falsch: die Luma-Geometrie zerfällt und das Bild wird grün (`fotos/f422.jpg`). Deshalb:

```
+0x010  Bits [14:8] = 0     Formatcode 0, NV12-Leser - für NV12 und NV16 gleich
+0x040               pitch  Y-Stride
+0x044      NV16: 2 × pitch Chroma-Stride, der Trick
+0x04C   ((h/2) << 16) | w  Chroma-Crop bleibt halbe Höhe
```

Für NV12 gilt derselbe Satz mit `+0x044 = pitch` - nichts anderes ändert sich zwischen den beiden Formaten.

---

## 4. Der VidDec-Descriptor: einmal, und nie zurücknehmen

Der 144-Byte-Descriptor ist **die Signalquelle der Firmware**, nicht bloß unsere Eingabe für den AFBD:
`GetFrameInfo` (`0x8b14709c`) folgt dem Zeiger in `+0x098`, `ConvertFrameInfo2SignalInfo` (`0x8b1471b0`) prüft
`[0] == 0x61770000` und baut daraus die Signal-Info. Jede **Änderung** löst `HandleSignalEvent` → WCE aus, und
die Firmware programmiert NR-, PROC- und Capture-Knoten neu (doku/76 §11.3). Genau das hat am 06.09. um 19:44
das Bild gekostet.

**Korrektur 07.09.: warum die Capture danach steht, ist nicht mehr offen.** Das Schreiben des Descriptors
setzt MemoryAgent `+8` auf 1 (VideoDec); `memory_agent_onoff` löscht daraufhin die INCAP-Freigabe
`0x06940928` Bit 31. Der Zähler `+0x104` läuft weiter, geschrieben wird nichts, die Wand zeigt einen
Standrahmen. **Zwei gemessene Wege geben die Capture wieder frei**, beide Stock-RPCs: der
**Quellenwechsel** (`SetSource` weg und zurück, [B2-quellenwechsel.md](nachtlog/B2-quellenwechsel.md)) und
der **HPD-Zyklus** (0,3 s genügen, [M4-hpd-dauer.md](nachtlog/M4-hpd-dauer.md)).
**Korrektur 07.09., 11:55 - „zwei Wege" ist so nicht haltbar** ([M4-nachpruefung.md](nachtlog/M4-nachpruefung.md)).
Als Beleg waren die beiden schon **verschieden stark**: B2 misst die Freigabe mit einem Reiz an der Quelle
(Gamma-Reiz Y 118,5 → 61,5) und verlässt sich ausdrücklich **nicht** auf das Registerbild, weil der Rundlauf
null strukturelle Registerunterschiede hinterlässt; M4 hat nur das Freigabebit `0x06940928` - seine anderen
zwei Spalten („Wand 0,00 % gegen Referenz", „INCAP zählt +61/s") können einen **Standrahmen nicht
ausschließen**, denn `+0x104` zählt auch im abgeschalteten Zustand weiter. Die Gegenprobe ist gefahren: aus
dem Zustand „aktive Quelle ist VideoDec" gibt ein HPD-Zyklus die Capture in **20 s nicht** frei, ein
`SetSource(3)` danach **sofort**. M4s eigener Ausgangszustand ist seit `0099` nicht mehr herstellbar, also
weder bestätigt noch widerlegt - **als Betriebsweg nicht verwenden**. Belegt bleibt der Quellenwechsel.

**Nachtrag 07.09., 11:42 - die Freigabe liegt jetzt im Kernel** (`0099`,
[E2-freigabe.md](nachtlog/E2-freigabe.md)). Der Anzeigetreiber veröffentlicht den Descriptor auf einer
**eigenen** Benachrichtigungskette - getrennt von der Flip-Kette, weil die der Vsync-Interrupt selbst ist und
ihre Mitglieder ihn offen halten - und der Aufnahmetreiber antwortet mit einem Quellenwechsel weg **und
zurück**. Ein **einzelner** `SetSource(HDMI-1)` reicht nicht (dreimal `0x60020438`), und die Freigabe kommt
erst **536-544 ms** nach der Antwort der Firmware. Abnahme Kaltstart 11:42 ohne Handgriff:
`0x928 = 0xE0020438`, `HDMI-1: ok`; nach `h713-tv` „Capture laeuft wieder nach 25 ms"; Zuspieler gedimmt →
**48,16 %** der Bildpunkte geändert. ~~Deshalb braucht jeder Erst-Enable nach dem Descriptor noch eine
Freigabe - der Treiber liefert sie nicht selbst (Abschnitt 8 Punkt 2).~~ Von RE-Frage K3 bleibt nur der
**zweite** Descriptor-Anstoß offen.

Der Treiber zieht daraus drei Konsequenzen:

1. **Einmal schreiben, beim Enable** - Seite **und** Zeiger `+0x098…+0x0A4`. Nicht im Probe, nicht bei
   jedem Commit; und nicht im selben Zug wie die Registerprogrammierung (Abschnitt 4.1).
2. **Inhaltsvergleich statt Merker.** Vor dem Schreiben wird der Ist-Inhalt der Seite mit dem Soll verglichen;
   ist er gleich, wird gar nicht geschrieben. Damit ist ein Modul-Neuladen ungefährlich, denn die reservierte
   Seite überlebt es. Verlangt ein zweiter Enable eine **andere** Geometrie, verweigert der Treiber und schreibt
   eine `drm_warn`-Zeile - er stellt nicht heimlich um.
3. **Beim Disable bleibt der Zeiger stehen.** `+0x098…+0x0A4` werden **nicht** genullt (Y- und C-Slots schon).
   Würde man den Zeiger wegnehmen, müsste der nächste Enable den Descriptor neu veröffentlichen - und das ist
   genau der Handgriff, den die Hardware nicht verträgt.

**Inhalt** (identisch zu `analyse/hdmi-seq/viddec_descriptor.py`, Wort-Index):

| Wort | Wert | Bedeutung |
|---|---|---|
| 0 | `0x61770000` | Magic |
| 1 | `2` | Typ: Videodecoder-Rahmen |
| 2-5 | `w, h, w, h` | Quell- und Zielgröße |
| 6-9 | `0, h, 0, w` | Fenster |
| 13, 14 | `30000` | Bildrate, Stock-Rezept für 60 Hz |
| 15 | `0` | progressiv |
| 16 | `0` | **`color_format` - bleibt 0** |
| 17 | `1` | BT.709 |
| 22 | `pitch` | Stride |
| 24 | `0` | SDR |
| 25, 26 | `0` | HDR-Metadaten: **keine Puffer** |
| 28, 30, 32, 34 | `w·16, h·16, w·16, h·16` | Anzeigefenster in 1/16 px |

Das weicht in vier Wörtern von der Fassung ab, die 0078 für Cedrus geschrieben hat (`+0x64/+0x68`
Selbstzeiger, `+0x48…+0x54`, `+0x8c`). Begründung: Die Seite hat hier **zwei** Leser. Die vier Wörter sind nur
gegen den AFBD gemessen; gegen die Firmware ist ausschließlich die Python-Fassung belegt, und sie ist die, die
dreimal nach Kaltstart die Zustandsmaschine auf 4 gebracht hat. Alles, wogegen die Firmware nicht gemessen ist,
bleibt 0.

### 4.1 Das Signalereignis und der Chroma-Stride

Der Descriptor ist nicht nur „einmal schreiben" - er hat einen **Zeitpunkt**. Bekommt die MIPS einen
Zeiger, den sie noch nicht hatte, läuft `HandleSignalEvent` → WCE, und die Firmware programmiert Source 0
**aus dem Descriptor nach**: Geometrie, Crop, Strides, Modus (doku/76 §11.3, dort am 06.09. gemessen; die
sichtbare Quittung ist INCAP `0x06940928` Bit 31 → 0, doku/78 Stufe 7a).

Fast alles, was die WCE dabei rechnet, ist genau das, was dieser Treiber ohnehin schreibt:

| Register | Treiber | WCE aus dem Descriptor | |
|---|---|---|---|
| `+0x020` | `0x043F077F` | `0x043F077F` | gleich |
| `+0x024` | `0x00420077` | `0x00420077` | gleich |
| `+0x040` | `0x780` | `0x780` (Wort 22) | gleich |
| `+0x048` / `+0x04C` | `0x04380780` / `0x021C0780` | dieselben | gleich |
| **`+0x044`** | **`0x0F00`** | **`0x780`** | **verschieden** |

Der Descriptor kennt **einen** Stride (Wort 22 = 1920). Die Verdopplung aus Abschnitt 3 ist die eine Stelle,
an der der Treiber der Hardware bewusst etwas anderes sagt als dem Descriptor - und deshalb die einzige, die
ein Signalereignis wieder einkassiert. Das erklärt den Befund vom 07.09. vollständig: die Plane kam mit
halbiertem Chroma-Stride und **sonst korrektem Registerbild** hoch, und zwar aus genau den beiden
Vorzuständen, in denen der Zeiger noch nicht stand (Kaltstart; nach `afbd_source0.py off`, das
`+0x098…+0x0A4` nullt) - aus jedem Vorzustand, in dem er stand, war er richtig.

**Konsequenz im Treiber:**

1. Die vier Zeigerworte gehören zur Veröffentlichung und werden dort geschrieben - einmal, beim Übergang
   auf „an". Vorher standen sie im Rumpf des `atomic_update` und wurden bei **jedem** Commit geschrieben;
   damit konnte jeder Commit ein Signalereignis sein.
2. Der Enable **klammert** das Ereignis. Vor der Veröffentlichung wird in `+0x044` eine Marke geparkt, die
   die WCE nicht erzeugen kann (0 ist kein gültiger Stride); danach wartet der Enable, bis die WCE sie
   ersetzt hat, und programmiert Source 0 erst dann. Kein `msleep`, kein zweites Schreiben „zur Sicherheit":
   gewartet wird auf ein Ereignis, das benannt und beobachtet ist.
   **Die Frist steht auf 1 s** (`H713_WCE_TIMEOUT_US`) - das ist die einzige gemessene Schranke: In der
   06:15-Sekundenreihe liegen Zeigerwechsel, Firmware-Antwort (`0x06940928` Bit 31 → 0) und die
   Source-0-Programmierung vollständig zwischen den Abtastungen +1 s und +2 s. Sie war zuvor auf 200 ms
   **geraten** und damit kürzer als diese Messung; korrigiert am 07.09., zusammen mit der Meldekette:
   `h713_afbd_wait_wce()` gibt jetzt `int` zurück, und der Aufrufer meldet den Ablauf als `drm_err`
   ([REGEL1-0093-0095.md](nachtlog/REGEL1-0093-0095.md) §3.1). Die Sekunde ist eine **Schranke, keine
   Latenz** - sie zu verengen ist eine Messung, keine Rechenaufgabe.
3. Nur für **NV16**. Für NV12 rechnet die WCE denselben Chroma-Stride aus, den die Plane will - da gibt es
   nichts zu verlieren und nichts zu warten.

Das ist zugleich die Reihenfolge, die am Gerät seit dem 06.09. funktioniert: das Skriptrezept
veröffentlicht den Descriptor in **Stufe 7a** und konfiguriert Source 0 in **Stufe 7b** - zwei getrennte
Schritte. Dort hat der Chroma-Stride nie gewackelt. Der Treiber hatte beides in einen Commit gezogen; das
war die Abweichung, und sie war nicht begründet.

**Belegt ist:** die Zustandstabelle (sechs Läufe, drei Ausgänge, eine Variable), das Firmware-Verhalten
„Signalereignis → Stride- und Modusregister werden neu geschrieben" (doku/76 §11.3) - und seit dem 07.09.
die **Wirkung** der Klammer: `+0x044` steht nach dem Enable aus jedem Vorzustand auf `0x0F00`
(Abschnitt 0, Teile A/B/C/E).
**Erschlossen, noch nicht einzeln gemessen ist:** dass die WCE genau `+0x044` beschreibt und dass sie das
tut, während Source 0 noch aus ist. Das entscheidet die Abnahme **nicht** mit: bei Fristablauf programmiert
der Treiber Source 0 trotzdem, das Ergebnis wäre wieder `0x0F00`, und nur die `drm_err`-Zeile
`did not reprogram the chroma stride` trennt die beiden Fälle. Sie ist in den Protokollen nicht abgefragt
worden (Abschnitt 0, „Was die Abnahme nicht entscheidet"; Vorschrift in
[nachtlog/D-cstride-fix.md](nachtlog/D-cstride-fix.md) §4 C und
[REGEL1-0093-0095.md](nachtlog/REGEL1-0093-0095.md) M1).

### Wo die Seite liegt - und warum das kein Detail ist

Die Seite hat einen zweiten Leser, der **kein Busmaster** ist: die MIPS liest sie durch ihr eigenes
DRAM-Fenster, in dem ARM `0x4Bxxxxxx` als `0x8Bxxxxxx` erscheint. Der System-CMA-Pool liegt auf diesem Board bei
`0x7DC00000` (Bootlog `re/captures/nfsboot.log`, `cma: Reserved 16 MiB at 0x000000007dc00000`) - **in diesem
Fenster gibt es ihn gar nicht**. Eine kohärente Seite aus dem Pool, wie 0078 sie benutzt, reicht für den AFBD,
aber nicht für die Firmware.

Deshalb kommt die Seite aus einer reservierten Region, benannt im DT:

```
decd_reserved:  decoder@4d941000     0x4d941000 + 0x1e000   (120 KB statt 128 KB)
viddec_info:    viddec-info@4d95f000 0x4d95f000 + 0x2000
```

`0x4D95F000` ist genau die Adresse, an der Stock den Descriptor ablegt (decd `dec_reg_set_address`), und sie
liegt in den letzten 8 KB des Vendor-Decoderpuffers - die deshalb abgetrennt werden. Die Gesamtausdehnung der
Reservierung ändert sich nicht (`0x4d941000 … 0x4d960fff`, wie `/proc/iomem` sie zeigt), `dec@5600000` ist bei
uns ohnehin `disabled`. Gemappt wird **write-combining**, nicht cached: es gibt nichts zu flushen, und die Sicht
der Firmware darf nicht davon abhängen, dass jemand flusht.

---

## 5. Die Ring-Folge

Pro Vsync (GIC 142, den der Treiber schon nutzt) - **einmal lesen, zwei Abnehmer**: die Plane im
Passthrough und, falls angemeldet, der Notifier aus Abschnitt 5.1.

1. `+0x320` lesen, `+0x324` lesen, `+0x320` noch einmal lesen. Hat sich Y dazwischen bewegt, wird die Probe
   **verworfen** - die Firmware schreibt beide Wörter mit 60 Hz, und ein zerrissenes Paar würde Y aus Slot *i*
   mit C aus Slot *i*+1 kombinieren. Eine verworfene Probe wiederholt für einen Vsync das vorige Bild; es gibt
   nichts, worauf man warten könnte.
2. Beide Adressen gegen die Grenzen von `mips_framebuf` prüfen. Was nicht im Ring liegt, geht nicht in die
   Scanout-Warteschlange.
3. Ist Y unverändert, passiert nichts (kein neuer Rahmen).
4. Sonst: Y in `+0x070…+0x07C`, C in `+0x084…+0x090`, dann `+0x06C = 1` (Dirty-Latch). Neun Schreibzugriffe.

`+0x010`/`+0x014` werden dabei **nicht** angefasst - es ändern sich nur Adressen, und dafür ist der Dirty-Latch
da. Das Ready-Latch würde die ganze Source-Konfiguration neu übernehmen.

**Warum die Flip-Zeiger den fertigen Slot nennen:** Stock schaltet seinen eigenen Kanal (ch1) mit Bit 31 auf
„Page-Flip-Zeiger `0x320/0x324` verwenden" (doku/64) und scannt direkt daraus aus. Ein Zeiger, aus dem die
Hardware ausscannt, kann nicht auf den Slot zeigen, den die Capture gerade füllt.

Damit der Vsync überhaupt kommt, hält die Plane im Passthrough-Betrieb eine Vblank-Referenz
(`drm_crtc_vblank_get`). Die Vsync-Maske hat seit dem Notifier **zwei** Nutzer: die Vblank-Maschinerie von
DRM und die Zahl der angemeldeten Notifier. Einer von beiden genügt, damit `+0x0C4` Bit 0 gesetzt bleibt;
sind es null, ist der Vsync maskiert wie vorher.

### 5.1 Der Vsync-Notifier - die Flip-Zeiger als Kernel-Schnittstelle

Die Zeiger `+0x320/+0x324` sind das **einzige** Ereignis „ein Capture-Slot ist fertig", das die ARM-Seite
überhaupt sehen kann: einen Capture-Interrupt gibt es hier nicht, er liegt im MIPS-Interrupt-Controller
(doku/84, RE-Frage K2). Der V4L2-Treiber braucht ihn also auch. Er hatte sich dafür ein eigenes `reg`
genommen - acht Byte bei `0x05600320`, mitten im `0x400`-Fenster, das **dieser** Knoten beansprucht. Das
geht nicht: `/proc/iomem` zeigt `05600000-056003ff : 5600000.display afbd`, `devm_ioremap_resource()`
darauf liefert `-EBUSY`. Und selbst wenn es ginge, wäre es die falsche Form - zwei Treiber, die dasselbe
rotierende Zeigerpaar abtasten, jeder mit eigener Zerrissen-Behandlung.

Also gibt der Erzeuger das Paar heraus, `include/linux/soc/sunxi/h713-afbd.h`:

```c
#define H713_AFBD_EVENT_FLIP	1

struct h713_afbd_flip {
	u32 y;		/* +0x320, fertiger Y-Slot, physisch */
	u32 c;		/* +0x324, der zugehörige C-Slot   */
};

int h713_afbd_register_flip_notifier(struct notifier_block *nb);
int h713_afbd_unregister_flip_notifier(struct notifier_block *nb);
int h713_afbd_read_flip(struct h713_afbd_flip *flip);
```

* **Atomic-Notifier-Kette.** Der Aufruf steht im Vsync-Handler, also im harten Interrupt-Kontext: nichts
  auf dem Pfad alloziert, schläft oder nimmt einen Mutex, und für den Verbraucher gilt dasselbe. Die Kette
  ist statisch, nicht am Gerät - ein Verbraucher kann sich also auch abmelden, nachdem dieser Treiber
  entbunden wurde.
* **Nur bei Änderung.** Der Erzeuger ruft die Kette erst, wenn sich das Paar gegenüber dem letzten Vsync
  bewegt hat. Ein Verbraucher braucht kein eigenes „hat sich was getan".
* **Kein Slot-Index in der Nutzlast.** Die Slot-Tabelle ist gemessenes Wissen der Capture; der
  Anzeigetreiber kennt nur die Grenzen von `mips_framebuf`. Das Paar nennt den fertigen Slot ohnehin über
  seine Adresse.
* **`h713_afbd_read_flip()`** ist die Frage, die nicht auf einen Vsync warten kann - „liegt überhaupt ein
  Signal an", die V4L2 stellt, während gar nicht gestreamt wird. Rückgaben: `0` (Paar), `-EAGAIN`
  (zerrissen oder außerhalb des Rings), `-EPROBE_DEFER` (`display@5600000` noch nicht gebunden),
  `-ENODEV` (Treiber gar nicht im Kernel).
* **Kein Verbraucher, kein Aufwand.** Ist niemand angemeldet und folgt die Plane dem Ring nicht, liest der
  Vsync-Handler das Zeigerpaar nicht einmal.

**Am Gerät abgenommen (07.09.):** `sun50i-h713-hdmirx` meldet sich an (`dmesg`:
`/dev/video1, Slot-Quelle: AFBD vsync notifier (GIC 142)`), die Kette zählt **287 Ereignisse**, und der
Verbraucher bekommt daraus 60 von 60 Bildern. Entwurf, Prüfbau und Abnahme:
[nachtlog/DE-vsync-notifier.md](nachtlog/DE-vsync-notifier.md),
[nachtlog/A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md).

---

## 6. Ablauf

### Enable (`atomic_update`, erster Aufruf)

```
RGB aus:        +0x140 = (gemerkt|Bit31)&~Bit0 ; +0x144 = 1 ; auf Ready warten
Marke:          +0x044 = 0                     (nur NV16, Abschnitt 4.1)
Descriptor:     Seite + Info-Slots +0x098..+0x0A4 veröffentlichen (Abschnitt 4)
WCE abwarten:   +0x044 pollen, bis die Firmware die Marke ersetzt hat (nur NV16; Frist 1 s,
                danach drm_err -- Source 0 wird trotzdem programmiert)
Geometrie:      +0x020, +0x024
Strides:        +0x040, +0x044        (NV16: doppelt)
Crop:           +0x048, +0x04C
Gate/Feld/Mux:  +0x060 = 1, +0x064 = 0, +0x068 = 0x122
Aux:            +0x080, +0x094, +0x0A8 = 0
Adressen:       +0x070.. = Y, +0x084.. = C     (aus dem Ring oder aus dem Framebuffer)
Dirty:          +0x06C = 1
Gain:           route +0x508
Source an:      +0x010, +0x014 = 1 ; auf Ready warten
Selektor:       lvds +0x06C = 0x39000000
Vblank:         Referenz nehmen, wenn hdmi-ring an
```

Marke, Veröffentlichung und Wartezeit laufen nur beim Übergang „aus → an" und nur, wenn die Firmware hier
überhaupt etwas Neues zu sehen bekommt (neue Seite oder neuer Zeiger).

### Update (jeder weitere Commit)

Derselbe Satz ab „Geometrie". Er ist idempotent; Descriptor **und** Info-Slots bleiben unberührt - die
Veröffentlichung hängt am Übergang, nicht am Commit.

### Vsync (nur bei `hdmi-ring`)

Abschnitt 5.

### Disable (`atomic_disable`)

```
Ring-Folge aus, Vblank-Referenz zurückgeben
Source aus:     +0x010 = gemerkter Ruhewert ; +0x014 = 1 ; auf Ready warten
Adressen:       +0x070.. = 0, +0x084.. = 0      -- Info-Slots BLEIBEN
Aux:            0
C-Stride:       +0x044 = gemerkter Ruhewert (bei uns 0x780)
Dirty:          +0x06C = 0
Gain:           route +0x508 = gemerkter Ruhewert (0x04000000)
RGB an:         +0x140 = gemerkter Wert ; +0x144 = 1 ; auf Ready warten
Selektor:       lvds +0x06C = 0x29000000
```

**Warum der C-Stride zurückgestellt wird.** Jedes andere Stück Source-0-Zustand, das diese Plane anfasst,
wird hier aus einem beim Probe gelesenen Wert zurückgestellt - CTRL, Chroma-Gain, RGB-Kanal, Selektor. Der
verdoppelte Stride war der einzige, der stehen blieb. Für die RGB-Konsole ist er folgenlos (sie liest ihn
nicht), aber er ist ein Rest, den der **nächste** Lauf erbt: genau so hat ein kaputter Erst-Enable am
07.09. eine Abnahme bestanden, weil `0x0F00` noch vom vorigen Zyklus stand. Der Wert ist der beim Probe
gelesene, nicht `0x780` fest verdrahtet - dieselbe Regel wie bei CTRL und Selektor, und derselbe Wert, den
`afbd_source0.py off` schreibt (doku/78 A.3).

Panel und Timing werden nie angefasst - der Treiber übernimmt eine laufende Anzeige und könnte sie nicht wieder
hochbringen.

---

## 7. Verhältnis zu 0078

0078 (cstenger, „add the validated fullscreen NV12 plane") ist die Grundlage: die fünf Zustandsteile *source
enable, source size, chroma gain, commit latch, plane-1 downstream selector* und die Reihenfolge des Übergangs
stammen von dort und sind unverändert. Unterschiede:

| | 0078 | 0093 |
|---|---|---|
| Formate | nur `NV12` | `NV12` **und** `NV16` |
| Geometrie | fest 1280×720 (`0x02cf04ff`/`0x002c004f`) | aus dem Framebuffer gerechnet |
| C-Stride `+0x044` | = Y-Stride | NV16: 2 × Y-Stride |
| Crop `+0x048`/`+0x04C` | gar nicht geschrieben | geschrieben |
| `atomic_check` | verlangt exakt 1280×720 → auf unserem Board **immer** `-EINVAL` | verlangt Modusgröße, linear, gleiche Pitches, Breite durch 16 |
| Adressquelle | immer der Framebuffer | Framebuffer **oder** Capture-Ring (`hdmi-ring`) |
| Descriptor-Seite | kohärente Seite aus dem DMA-Pool | reservierte Region aus dem DT (MIPS-sichtbar) |
| Descriptor-Inhalt | vier Wörter mehr (AFBD-Fassung) | Fassung aus `viddec_descriptor.py` |
| Descriptor-Lebensdauer | bei jedem Probe neu aufgebaut | einmal pro Boot, beim Disable nicht zurückgenommen |
| Info-Slots `+0x098` | bei jedem Commit geschrieben | mit dem Descriptor veröffentlicht, einmal beim Übergang |
| Signalereignis der Firmware | unbeachtet | abgewartet, bevor Source 0 programmiert wird (Abschnitt 4.1) |
| Chroma-Gain | fest `0x144C0000` | Plane-Eigenschaft `saturation`, Default `0x4C` |
| Vsync | nur für Vblank-Events | zusätzlich Ring-Folge |

**0080 bleibt draußen.** Unsere Plane liest den Ring **physisch**; der Display-Knoten hat keine
`iommus`-Eigenschaft und bekommt keine (doku/76 §10, nachtlog/A §6.5).

---

## 8. Was offen bleibt

1. **Wie die WCE genau antwortet - offen, obwohl die Abnahme grün ist.** Die Klammer im Enable wartet
   darauf, dass die Firmware `+0x044` beschreibt, solange Source 0 noch aus ist. Dass sie *Stride- und
   Modusregister* schreibt, ist gemessen (doku/76 §11.3); dass `+0x044` dazugehört und wie lange sie
   braucht, ist erschlossen. Die Abnahme entscheidet das **nicht**: bei Fristablauf programmiert der
   Treiber Source 0 trotzdem, und das Ergebnis ist dasselbe `0x0F00`. Was es entscheidet, ist eine einzige
   Zeile - `dmesg | grep -c "did not reprogram the chroma stride"`, Sollwert **0** - mitzunehmen aus einem
   Lauf, der ohnehin stattfindet ([REGEL1-0093-0095.md](nachtlog/REGEL1-0093-0095.md) M1,
   [D-cstride-fix.md](nachtlog/D-cstride-fix.md) §4 C). Erst dann steht auch fest, ob die Frist von 1 s
   verengt werden kann.
2. **K3 - zweiter Descriptor-Anstoß.** Der Treiber vermeidet das Problem (einmal pro Boot), löst es aber nicht.
   Solange es offen ist, kann eine Plane, die einmal mit 1920×1080 lief, in demselben Boot keine andere
   Quellgeometrie annehmen. **Teilantwort vom 07.09.:** die vom Descriptor abgeschaltete Capture lässt sich
   ohne zweites Descriptor-Schreiben wieder freigeben - Quellenwechsel
   ([B2-quellenwechsel.md](nachtlog/B2-quellenwechsel.md)) oder HPD-Zyklus
   ([M4-hpd-dauer.md](nachtlog/M4-hpd-dauer.md) - **der HPD-Zyklus hält der Nachprüfung nicht stand**,
   [M4-nachpruefung.md](nachtlog/M4-nachpruefung.md)); **seit `0099` fährt der Kernel den Quellenwechsel selbst**
   ([E2-freigabe.md](nachtlog/E2-freigabe.md), Abschnitt 4). Was der **zweite Anstoß** anrichtet, ist unverändert
   ungemessen; der Enable-Pfad des Treibers verweigert eine abweichende Geometrie mit `drm_warn`, statt es
   auszuprobieren.
3. **Dirty-Latch pro Vsync - kein Gegenbefund, aber auch kein Beleg.** Dass `+0x06C` allein die neuen
   Adressen übernimmt (ohne `+0x014`), ist die naheliegende und sparsamste Lesart; gemessen ist weiterhin
   nur der Enable-Fall, in dem beide Latches geschrieben werden. Am Gerät ist der Fehlerfall aus der
   Abnahmevorschrift („Bild steht still oder reißt") über mehrere Plane-Zyklen **nicht** eingetreten, und
   die Ring-Folge schreibt nachweislich wandernde Adressen (`+0x070`: `0x4C3EF000 → 0x4C5EE000`). **Das
   schließt die Alternative aber nicht aus:** verwürfe die Hardware die neuen Adressen, überschriebe die
   Firmware den festgehaltenen Slot trotzdem alle drei Bilder - die Wand bliebe also auch dann nicht stehen,
   und ein Farbreiz käme auch dann an. Ein echter Beleg wäre die **ausgescannte** Adresse, und die sieht der
   ARM nicht. Bleibt das Bild doch einmal stehen oder reißt es, ist `+0x014` der erste Schalter.
4. **Kein echtes Overlay** - für uns heute nicht, aber nicht mangels Hardware: siehe die Korrektur in
   Abschnitt 1 und RE-Frage K6 ([K5-K6-re.md](nachtlog/K5-K6-re.md)). Blocker bleibt das Tor für
   AFBD-Kanal 1 (doku/64 §2).
5. **Ring-Ereignis statt Polling.** Der Treiber pollt die Flip-Zeiger im Vsync. Ob die INCAP ein „Slot
   fertig"-Interrupt hat, ist RE-Frage K2; für E wäre das die sauberere Zustellung.
6. **`+0x030`** wird nicht geschrieben. Auf unserem Board steht dort der richtige Wert; für einen Framebuffer
   anderer Größe wäre zu klären, ob er mitgezogen werden muss.
7. **Auflösungswechsel der Quelle - gemessen, und schlechter als erwartet.** Wechselt der Zuspieler auf
   1280×720, meldet **alles** weiter Erfolg (Flip-Zeiger wandern, INCAP zählt, Bilder kommen), aber der
   Ringinhalt ist Müll: die neue Geometrie wird in einen Ring geschrieben, dessen Zeilenabstand noch 1920
   ist, also wickelt sich jede Zeile um. Ein `SignalChange` feuert dabei **nicht**
   ([A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md)). Die Plane merkt davon nichts - sie
   bekommt vom Ring nur Adressen, keine Geometrie. Der Rückweg auf 1920×1080 ist sauber, ohne Zutun.
   Wer hier weitersucht: die Panel-Geometrie steht im Composition-Block `0x05000224`/`0x05000844`
   ([doku/89](89-composition-block.md)), ob **die** sich mitbewegt, ist ebenfalls ungemessen.
8. **Der Chroma-Gain hat zwei Bediener.** Die Plane-Eigenschaft `saturation` schreibt `route +0x508`
   direkt; derselbe Regler hängt auch am Stock-RPC `SetSaturation`
   ([K5-board-verifikation.md](nachtlog/K5-board-verifikation.md) (f)). Wer beide benutzt, überschreibt
   sich selbst - der letzte Schreiber gewinnt. Für Paket I ist das die Stelle, an der zu entscheiden ist,
   welcher der beiden Wege der offizielle wird; gemessen ist die Wechselwirkung nicht.
