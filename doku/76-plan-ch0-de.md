# ch0 und das DE-Problem: Befundlage, Ursachenkette, Messplan

> **Historisch (Stand 08.09.2026):** Ursache gefunden und gelöst am 07.09.; der aktuelle Stand steht in [`00-STATUS.md`](00-STATUS.md), das Betriebswissen in [`97-handoff-20260908.md`](97-handoff-20260908.md). Die Bedienhinweise in diesem Dokument sind überholt (Prep-Skripte, altes cpu_comm-Modul).

**Stand 06.09.2026, 16:10.** Ausgangspunkt ist der heutige Durchbruch beim HDMI-Eingang: die Quelle wird über die
ARISC erkannt, der HDMI-Empfänger ist **voll gelockt auf 1920×1080p60** (doku/75, Nachträge 14:55 und 15:25).
Damit ist zum ersten Mal messbar, was danach passiert - und was nicht.

Dieses Dokument hält den Stand fest, bevor irgendetwas geschrieben wird: erst die Kette messen, dann die Ursache
benennen, dann den Eingriff an der richtigen Stelle. „ch0 einschalten" ist **nicht** die Aufgabe; ch0 ist ein
Symptom weiter unten in derselben Kette.

## 1. Was gemessen ist (06.09., Board läuft seit Kaltstart 15:21, Signal liegt an)

| Stufe | Registerbefund | Bewertung |
|---|---|---|
| HDMI-RX | `0x06940104` zählt **+60/s** in den oberen Bits, `+0x59c` +1/s | Empfänger arbeitet, 60 fps kommen an |
| RX-Zustand (elog) | `port1 SwitchState 3→4→5`, `Set Valid Signal 0x20000`, Timing 2200×1125, aktiv 1920×1080, `AV mute:0 0` | Signal gültig und entstummt |
| WCE (elog) | `UpdateWce ENTER`, `SetWindow ENTER`, alle fünf Knoten `CalcWindow`, `WriteReg` | **Die Fensterschicht hat komponiert** - genau das, was cstenger am 05./06.09. fehlte |
| TVTOP-Datenpfad | `0x068B00B8/C4/D0`, `0x068B00DC/E8/F4`, `0x068B044C` alle **0** | **AUS** - hier bricht die Kette |
| Capture (INCAP) | vollständig konfiguriert: Y-Ring `0x4C3EF000/0x4C5EE000/0x4C7ED000`, C-Ring `0x4C9EC000/0x4CBEB000/0x4CDEA000`, Fenster 1920×1080, Ausgabe-Bit 31 in `0x06940928/0968` **gesetzt** | eingeschaltet, aber ohne Zulauf |
| DRAM-Puffer | alle sechs statisch, Y=`0x15`, C=`0x80`, **0 Byte Änderung in 2 s** | sauberes Schwarzbild, kein Live-Inhalt |
| AFBD ch0 | `0x05600010 = 0x03000013` (von uns gesetzt), Latch wird verbraucht, Quellenpaar `0x320/0x324` **rotiert** zwischen zwei Slots | Kanal lebt, liest aber die schwarzen Puffer |
| DE2-Schreibkanäle | `0x05000178 = 0x6002021c`, `0x050001B8 = 0x60020438`, `0x05000278`, `0x050002B8` - Werte konfiguriert, **Bit 31 = 0** | **AUS** |
| Fenster-Handle | `*(0x8b4a9da8) = 0`, Frame-Descriptor `0x05600098..a4 = 0` | unverändert offen |

Kurz: **Signal ja, Fensterrechnung ja, Datenpfad nein.** Das Panel zeigt weiterhin die Linux-Konsole
(Webcam: die Projektion liegt links im Bild, x 0..233; die helle Fläche ist die Wand, nicht Projektor-Weiß).

## 2. Die Ursachenkette (Firmware gelesen, nicht geraten)

Alle Freigabe-Bits der Ausgabekette werden von **einer** Funktion gesetzt: `memory_agent_onoff` (0x8b15349c).
Ihre Maske ist vollständig bekannt (IDA, heute nachgeprüft - die Adressen der alten Notizen stimmen mit unserer
Firmware überein):

| Bit | Register |
|---|---|
| 0x001 | TVTOP A `0x068B00B8/C4/D0` Bit 0 |
| 0x002 | TVTOP B `0x068B00DC/E8/F4` Bit 0 |
| 0x004 | `0x068B044C` Bit 18 |
| 0x008 | INCAP `0x06940928/0968` Bit 31 |
| 0x010 | AFBD `0x05600010` Bits 0+1 und `0x05600014` Bit 0 |
| 0x020 | DE `0x05000178/01B8` Bit 31 |
| 0x040 | DE `0x05000278/02B8` Bit 31 |
| 0x080 | DE `0x050C06F8/0738` Bit 31 |
| 0x100 | DE `0x050C07B8` Bit 31 |
| 0x200 | DE pool-2 `0x050C0478/04F8/0578/05F8/0678` Bit 31 |

Unser Registerbild entspricht **exakt** `enable(0x008)` - nur die Capture. Das ist der „kein Signal"-Zweig von
`memory_agent_update_onoff` (0x8b153140): er prüft `MemoryAgent+12` (Signal-ID) und schaltet, wenn dort
`0x20002` oder `0x20003` steht, alles ab **außer** der Capture (Meldung „no signal, disable all memory agent
without capture", die wir im elog sehen). Der Freigabe-Zweig baut dagegen die Maske
`0x300 | 0x80 | 0x70 | 0x8/0x18` plus 7 - also die ganze DE-Seite.

`MemoryAgent+12` wird **ausschließlich** von drei Zustandseintritten der Projektor-Zustandsmaschine geschrieben
(`AppTopProjector_PushSignalToMemoryAgent`, 0x8b1082e0):

- `EnterIdle` (0x8b108394)
- `EnterWaitingWindowsReady` (0x8b108474, Zustand 2) → pusht **NULL** ⇒ `+12 = 0x20003` ⇒ **abschalten**
- `EnterWaitingPipeLineReady` (0x8b108518, Zustand 3) → pusht das **echte** Signal ⇒ **einschalten**

Der Übergang 2 → 3 passiert in `AppTopProjector_ThreadMain` (0x8b1091f4) beim **Timeout** der in Zustand 2
gesetzten Deadline (ein Frame), nicht durch ein äußeres Ereignis. Es braucht also keinen ARM-Anstoß - die
Maschine müsste von allein durchlaufen, **wenn sie gestartet wird**.

**Im elog fehlt jede Zustandsmeldung** (`EnterIdle`, `EnterWaitingWindowsReady`, `EnterWaitingPipeLineReady`,
`EnterSignalSteady` schreiben alle auf Level 3, und Level-3-Meldungen anderer Module sehen wir). Die
Zustandsmaschine läuft bei uns also **gar nicht an**. Damit bleibt `+12` auf dem Startwert `0x20003`, und
`update_onoff` schaltet folgerichtig alles außer der Capture ab.

Warum sie nicht anläuft, ist die eigentliche offene Frage. Zwei Stellen im gelesenen Code kommen dafür infrage:

1. **Ereignistyp.** `AppTopProjector_HandleSignalEvent` (0x8b108644) verzweigt auf den Quellentyp `sig[0]`:
   nur `== 1` (VidDec) führt in die Zustandsprogression, HDMI (3..6) landet ausschließlich in
   `UpdateMemoryAgentSecondaryFlags` - dem Pfad, der `+12` nie anfasst. Das deckt sich mit unserer Beobachtung
   (Secondary-Flag „capture" gesetzt, sonst nichts).
2. **Quellenwechsel.** In `ThreadMain` läuft `ApplyNewSource` nur, wenn die gemeldete Quelle sich von der
   aktiven (`this+224`) **unterscheidet**. Ist die aktive Quelle beim Firmware-Start bereits HDMI-1 (aus
   `sys:source_id` der Vendor-Konfiguration), ist unser `SetSource(3)` ein Nullwechsel und stößt nichts an.
   cstenger beobachtet auf seinem Board das Gegenstück: „SetSource(1) is delivered and inert; the live source is
   Dummy".

## 3. Hypothesen und wie sie zu widerlegen sind

| # | Hypothese | Vorhersage | Messung | Status |
|---|---|---|---|---|
| H1 | Die Zustandsmaschine startet nur bei einem **echten** Quellenwechsel | `SetSource` auf eine andere Quelle, dann zurück auf HDMI ⇒ `EnterIdle`/`EnterWaitingWindowsReady`/`EnterWaitingPipeLineReady` im elog | zwei `SetSource`-Aufrufe, elog Level 4 | offen |
| H2 | Nur ein **VidDec-Ereignis** (Typ 1) treibt die Progression; HDMI-Ereignisse nie | auch nach erzwungenem Wechsel keine Zustandsmeldung | wie H1, Auswertung des Zweigs | offen |
| H3 | Der Zustandsmaschine fehlt ein **Fertig-Signal der Fensterschicht** („windows ready") | Zustand 2 wird betreten, Zustand 3 nie | Zustandswort `AppTopProjector+4` live lesen | offen |
| H4 | Die Firmware wartet auf einen **Frame-Descriptor** (`0x05600098`), den auf Stock der Decoder-Treiber liefert | Descriptor setzen ⇒ Progression läuft an (2026-06-13 device-verified) | Descriptor-Test, **erst nach H1-H3** | offen |
| H5 | TVTOP/DE sind zusätzlich **takt- oder domänenseitig** gesperrt, die Firmware kann gar nicht schalten | Bits lassen sich auch von Hand nicht setzen | ein einzelner Schreibversuch auf `0x068B00B8`, sofort zurück | offen |

Ausdrücklich **nicht** Teil des Plans: das Setzen der zehn Freigabe-Bits von Hand als „Lösung". Das wäre ein
Workaround an der Stelle, an der die Firmware ihre eigene Zustandslogik hat (Regel: kein Quirk, außer Stock macht
es identisch). Als **Messmittel** ist ein einzelner, sofort zurückgenommener Schreibversuch erlaubt - er
unterscheidet „Hardware gesperrt" von „Firmware will nicht".

## 4. Reihenfolge

1. **Instrument.** Webcam-Detektor auf die Projektionsregion (`analyse/hdmi-seq/wandcheck.py`, ROI x 0..260)
   mit Positivkontrolle über `/dev/fb0`. Ohne belegtes Instrument keine Bildaussage.
2. **Zustand lesen.** `AppTopProjector`-Instanz über `AppTopProjector_GetInstance` (0x8b108fb4) auflösen und
   `+4` (Zustand), `+224` (aktive Quelle), `+32` (Signal-Info) live lesen. Damit ist H3 direkt entscheidbar.
3. **H1/H2 messen.** Kaltstart, ARISC-EDID/HPD, dann `SetSource` auf eine Fremdquelle und zurück auf HDMI,
   elog Level 4 mitlesen, Zustandsmeldungen auswerten.
4. **H5 prüfen** (ein Bit, sofort zurück), damit die Deutung von 2./3. eindeutig ist.
5. Erst danach entscheiden, wo der **richtige** Eingriff sitzt: Konfiguration (`sys:source_id`), Reihenfolge der
   RPC-Sequenz, ein fehlender ARM-seitiger Baustein (Descriptor/Decoder-Rolle) oder ein Ereignis, das wir nicht
   liefern. Der Eingriff gehört an die Stelle, an der Stock ihn auch hat.

## 5. Was dabei nicht vergessen wird

- Der **Kanal-Irrtum** ist ausgeräumt: die AFBD-Kanäle sind 0 (Video, `0x05600010`), 1 (`0x05600100`) und
  2 (`0x05600140`, unser Konsolen-Scanout). „ch1 aktiv" in älteren Notizen meint den Kanal bei `0x05600140`.
- Das **Latch-Orakel** (doku/64) bleibt das billigste Messmittel pro Kanal und ist heute erneut bestätigt:
  ch0 und ch2 werden bedient, ch1 nicht.
- Die **Konsole** liegt auf ch2 und ist opak; jeder Bildnachweis für ch0 muss sie berücksichtigen (abschalten
  oder ROI außerhalb).
- cstengers Befund „mit lebendem MIPS führt kein Weg an der WCE vorbei" ist bestätigt und heute ergänzt: die WCE
  **rechnet** bei anliegendem Signal - sein Blocker (kein `UpdateWce`) ist mit dem HDMI-Signal weg.

## 6. Messreihe 06.09., 16:10-16:20 - die Kette lässt sich zünden, das Bild bleibt weiß

**Instrument zuerst.** `analyse/hdmi-seq/wandcheck.py`, Messbereich auf der Projektionsfläche
(x 220..1090, y 40..560 im 1280×720-Bild), Kamerabelichtung **fest** (`v4l2-ctl
--set-ctrl=auto_exposure=1,exposure_time_absolute=60`) - ohne feste Belichtung sind alle Differenzen wertlos,
die ersten beiden Vergleiche des Tages waren genau deshalb Fehlmessungen. Positivkontrolle: `/dev/fb0` schwarz
gegen weiß ⇒ **100 % der Bildpunkte, mittlere Differenz 146**. Das Instrument zeigt an.

**1. Der Descriptor zündet die Zustandsmaschine.** `analyse/hdmi-seq/viddec_descriptor.py set` schreibt den
144-B-Descriptor (Magic `0x61770000`, 1920×1080 progressiv) nach `0x4D95F000` und den Zeiger nach
`0x05600098`. Sofort danach:

| | vorher | nachher |
|---|---|---|
| Zustand `AppTopProjector+4` | 0 | **4** (SignalSteady) |
| `MemoryAgent+12` (Gate) | `0x20003` | **`0x2007C`** (DTV_1920_1080_P) |
| DE `0x05000178/1B8/278/2B8` | `0x6…` (Bit 31 = 0) | **`0xE…` (Bit 31 = 1)** |
| AFBD ch0 `0x05600010` | `0x03000010` | **`0x03000013`** (von der **Firmware** gesetzt) |
| elog | nichts | `vdd`-Dump: `kSourceId_VideoDec`, `AI_SIGNAL_MODE_DTV_1920_1080_P` |

Damit ist der Gate-Mechanismus aus Abschnitt 2 am Gerät bestätigt - und zwar erstmals **mit anliegendem
HDMI-Signal**, was beim Test vom 13.06. nicht der Fall war.

**2. Aber die Firmware schaltet dabei den HDMI-Datenpfad ab.** Der Descriptor meldet die Quelle als
*VideoDec*; der Freigabe-Zweig ruft dann `disable(0x387)` - und `0x387` enthält genau die drei TVTOP-Gruppen.
Gemessen: TVTOP bleibt 0, die Capture verliert ihr Bit 31. Von Hand gesetzt bleibt das Capture-Bit zwar stehen,
**die Ringpuffer bleiben trotzdem statisch** (0 geänderte Bytes in 2 s). Ohne TVTOP kein Zulauf.

**3. Das Panel zeigt Weiß, unabhängig vom Videokanal.** Mit ausgeschaltetem OSD-Kanal (`0x05600140` Bit 0 = 0)
und aktivem ch0 wurde ein Testmuster (obere Hälfte hell, untere dunkel, danach invertiert) in **alle drei**
Y-Ringpuffer und neutrales Chroma in die C-Puffer geschrieben, Latch jeweils gepulst und verbraucht:

- Die Projektionsfläche bleibt **gleichmäßig weiß**, in beiden Musterlagen. Keine Kante, kein Unterschied.
- Mit eingeschaltetem OSD-Kanal folgt das Panel dagegen **sofort** dem Framebuffer (schwarz/weiß/grau,
  99,8 % Bildänderung).

Daraus folgt hart: **ch2 wird angezeigt, ch0 nicht.** Der Videokanal ist im AFBD aktiv, wird bedient (Latch),
liest gültige Puffer - und erscheint trotzdem nicht auf dem Panel. Und ohne OSD-Kanal ist die Fläche nicht
schwarz, sondern **weiß**, obwohl der einzige verbleibende Kanal schwarze Puffer liest. Es gibt also eine Stufe
**hinter** dem AFBD, die den Videokanal nicht einbindet und im Leerfall Weiß ausgibt.

Das ist die neue, konkrete Front: nicht „ch0 einschalten", sondern **die Ebeneneinbindung im DE-Mixer**.
Die weiße Fläche der alten Notizen („NV12 white") ist damit reproduziert und zum ersten Mal von der
Capture-Frage getrennt - sie tritt auch dann auf, wenn der Pufferinhalt bekannt und gültig ist.

**Zustand nach der Reihe:** OSD-Kanal wieder an, Konsole sichtbar, Descriptor bleibt gesetzt (Messmittel),
Capture-Bit von Hand gesetzt. Nichts davon ist eine Lösung; der Descriptor gehört auf Stock ARM-seitig
geschrieben (decd `dec_reg_set_address`), unser Kernel tut es noch nicht.

## 7. Nächste Schritte

1. **DE-Mixer lesen statt raten:** welche Ebenen der Mixer einbindet, woher die weiße Fläche kommt
   (Hintergrundfarbe? Blue-/Black-Screen-Ersatzbild? nicht initialisierter Zwischenpuffer der NR-Stufe?).
   Kandidaten sind die DE-Blöcke `0x050C0…` (NR/DETN, Maske 0x080/0x100/0x200), die der Freigabe-Zweig
   **abgeschaltet** hat, sowie die Panel-Stufe bei `0x051C0…`.
2. **Die Freigabe unter HDMI-Quelle erzwingen**, nicht unter VideoDec: `Flag182` entscheidet über die
   TVTOP-Gruppen, es kommt aus `DeviceManager_GetStatus(source_id)`. Registry lesen, dann den sauberen Weg
   bestimmen (richtige Quelle statt Flag-Poke).
3. Erst danach Bildnachweis erneut - mit demselben Instrument und fester Belichtung.

## 8. Messreihe 16:20-16:30 - **die Capture läuft live**; der Bruch sitzt zwischen DRAM und Panel

**Der wichtigste Befund des Tages.** Ein in den Y-Ringpuffer geschriebenes Markenmuster (`0xA5`) wird
**binnen 200 ms vollständig überschrieben**. Es schreibt also etwas. Und es schreibt das echte Bild:

| Zustand am ThinkPad | Y-Puffer `0x4C3EF000` |
|---|---|
| `xrandr --gamma 1:1:1` | md5 `2f6ef72c`, Mittelwert 26,6, min 17, max 43 |
| `xrandr --gamma 0.3:0.3:0.3` | md5 `bfd2684a`, Mittelwert 16,0, konstant |
| wieder `1:1:1` | md5 `2f6ef72c` - **identisch zum ersten Zustand** |

Der Pufferinhalt folgt reproduzierbar dem Signal der Quelle. Damit ist bewiesen:
**HDMI-RX → Capture → DRAM funktioniert vollständig.** Die frühere Deutung „Capture schreibt nicht" war
falsch - sie beruhte darauf, dass der Laptop ein dunkles Bild sendet (Mittelwert 26 von 255) und der
Vergleich zweier Aufnahmen desselben Standbilds naturgemäß null Änderung ergibt. Ein Standbild ist kein
Stillstand.

**Der Bruch sitzt dahinter.** Bei laufender Capture, aktivem ch0 (`0x05600010 = 0x03000013`, Latch wird
verbraucht), ausgeschaltetem OSD-Kanal und rotierendem Ring zeigt die Wand **keinerlei Reaktion** auf die
Gamma-Umschaltung: 0 von 452 400 Bildpunkten über der Schwelle, während der Puffer nachweislich wechselt.

**Ebenenwahl `0x051C006C`.** Das Register stand bei uns auf `0x29000000`, cstengers als funktionierend
dokumentiertes Rezept nennt `0x39000000`. Der Wechsel ändert das Panelbild vollständig (100 % der Bildpunkte,
mittlere Differenz 149): statt einer gleichmäßig weißen Fläche erscheint eine horizontal gestreifte Struktur
mit scharfer Kante in der Bildmitte. Die Kante **wandert aber nicht** mit einem invertierten Testmuster in den
Ringpuffern - der angezeigte Inhalt stammt also nicht aus ihnen, sondern aus einer Stufe der
Verarbeitungskette (NR/DETN/PROC), deren Zwischenpuffer wir nicht kennen. Das Register ist damit ein
belegter, wirksamer Schalter auf der Panelseite, aber nicht die Lösung.

**TVTOP ist hardwareseitig gesperrt** (H5 beantwortet): `0x068B00B8/C4/D0`, `0x068B00DC/E8/F4` und
`0x068B044C` nehmen einen Schreibversuch **nicht an** und lesen weiter 0. Die Firmware kann sie also nicht
einfach „vergessen" haben; sie sind ohne die passende Domänen-/Taktfreigabe tot. Für die Capture ist das
folgerichtig ohne Belang - sie läuft ja.

### Stand der Hypothesen aus Abschnitt 3

| # | Ergebnis |
|---|---|
| H1/H2 | **bestätigt**: nur ein VideoDec-Ereignis (Quelle 1) treibt die Zustandsmaschine; HDMI-Ereignisse werden nur zwischengespeichert (`+224`) |
| H3 | **beantwortet**: die Maschine stand auf Zustand 0, nicht 2 - sie lief nie an |
| H4 | **bestätigt und ausgeführt**: der Descriptor bringt sie auf Zustand 4 und öffnet die DE-Schreibkanäle |
| H5 | **bestätigt**: TVTOP nimmt keine Schreibzugriffe an |

### Gerätestatus-Registry (live gelesen, erklärt die Maskenwahl)

`DeviceManager` (Zeiger `0x8BAC1A5C`), 10 Einträge: Quellen 7/8/9/10 haben Status **0**, die HDMI-Quellen
3/4/5/6 Status **1**, der Decoder (1) Status **3**, Quelle 0 Status 5. In `memory_agent_update_onoff` führt
**nur Status 0** zur vollen Maske `0x7F` (mit TVTOP); bei Status ≠ 0 entsteht `0x78` - genau unser Registerbild.
Die alte Notiz „VideoDec-Registry-Status 3→1 poken" zielt auf dieses Feld.

## 9. Wo es weitergeht

Die Aufgabe hat sich damit verschoben und ist enger:

1. **Der Weg vom DRAM auf das Panel.** Capture und Puffer sind bewiesen; gesucht ist die Stufe, die den
   Videokanal in die Panelausgabe einbindet. Kandidaten in dieser Reihenfolge: die Panel-Stufe `0x051C0…`
   (Register `0x6C` wirkt nachweislich), die von der Firmware abgeschalteten DETN-Gruppen
   (`0x050C06F8/0738`, `0x050C07B8`, pool-2 `0x050C0478…`), und die Frage, welchen Zwischenpuffer die
   NR-Stufe liest.
2. **Die gestreifte Struktur deuten.** Sie ist die erste sichtbare Ausgabe des Videopfads überhaupt. Ihr
   Ursprung (Zwischenpuffer, Stride, Kompressionsformat) sagt, an welcher Stelle die Kette falsch verdrahtet ist.
3. **Sauberer Ersatz für den Descriptor-Poke.** Er gehört ARM-seitig in den Treiber (Stock: decd
   `dec_reg_set_address`), nicht in ein Messskript.

Werkzeuge dieser Sitzung: `analyse/hdmi-seq/wandcheck.py` (Bilddetektor mit fester Belichtung),
`analyse/hdmi-seq/viddec_descriptor.py` (Descriptor setzen/lesen/entfernen).

## 10. 19:22 - **das HDMI-Bild steht auf der Wand**, über AFBD Source 0 mit cstengers Sequenz

**Korrekturen zu Abschnitt 8 zuerst,** damit niemand den falschen Fährten folgt:

- `0x051C006C` ist kein Ebenenwähler im Sinne eines Mixers, sondern ein Register im **LVDS-Block**
  (RE-Notizen: „LVDS-PHY adjustments … 0x051c006c"); cstenger nennt es den „plane-1 downstream selector".
  Beides passt zusammen: Der Hardware-Mux ist **exklusiv** - Source 0 **oder** der RGB-Kanal erreicht den
  Encoder, keine Mischung (cstenger, Patch 0078). Die „Streifen" waren Source 0 mit leerem pool-1.
- Mein Invertierungstest in Abschnitt 8 war **ungültig**: Die Capture überschreibt die Ringpuffer in unter
  200 ms, die Kamera löst später aus. Er hat nicht gezeigt, dass ch0 unsichtbar ist, sondern nur, dass die
  Capture läuft.
- Bit 31 an ch0 (`0x83000013`) war ein Irrtum; der Firmware- und Stock-Wert ist `0x03000013`.
- Die IOMMU ist **ausgeschlossen**: Master 0 und 1 gehören dem Video-Codec (`iommus = <&iommu 0>, <&iommu 1>`),
  Bypass steht auf `0x7C`, der Display-Knoten hat keine `iommus`-Eigenschaft, keine Faults
  (`INT_STA`, `FAULT_VA` = 0). Stocks pool-1-Werte `0x00800000/0x009fa400` sind IOMMU-Adressen des
  **Vendor**-Kernels - bei uns liest der AFBD physisch, wie der Konsolenkanal beweist.
- TVTOP (`0x068B0…`) gehört zur Maske für **Status-0-Quellen** (CVBS/ATV); für HDMI ist der Capture-Pfad ohne
  TVTOP nachweislich vollständig. Dass die Register nicht beschreibbar sind, ist für HDMI ohne Belang.

**Was gefehlt hat - und was cstenger am 02.09. bereits gelöst hatte** (Patch
`0078-drm-h713-add-fullscreen-nv12-overlay.patch`, Commit 3cdd89f, in seiner Serie, **nicht in unserer**):
Source 0 liest im Ring-Modus (`+0x068 = 0x122`, bei uns von der Firmware gesetzt) aus **pool-1** - den vier
Y/C/Info-Slots `+0x070..+0x07C`, `+0x084..+0x090`, `+0x098..+0x0A4`. Bei uns war pool-1 **leer**; die
Firmware füllt nur pool-2 (`+0x320/+0x324`). Dazu fehlten Chroma-Gain, Dirty-Latch und der Selektor.
Seine fünf Zustandsteile: *source enable, source size, chroma gain, commit latch, plane-1 downstream selector.*

**Die Sequenz** (`analyse/hdmi-seq/afbd_source0.py on`, Werte gemessen 19:22):

| Schritt | Register | Wert |
|---|---|---|
| RGB-Kanal aus und committen | `0x05600140` / `0x05600144` | `0x83001900` / `1` (= Stock-Wert im HDMI-Betrieb) |
| Gate / Field / Ring-Mux | `0x05600060` / `064` / `068` | `1` / `0` / `0x122` |
| vier Y-Slots | `0x05600070..07C` | `0x4C3EF000` (Capture-Ring Slot 0) |
| vier C-Slots | `0x05600084..090` | `0x4C9EC000` |
| vier Info-Slots | `0x05600098..0A4` | `0x4D95F000` (der VidDec-Descriptor aus Abschnitt 6) |
| Aux Y/C/Info | `0x05600080` / `094` / `0A8` | 0 |
| Dirty-Latch | `0x0560006C` | 1 |
| Chroma-Gain | `0x05140508` (PROC-Block, „route") | `0x144C0000` (Ruhe: `0x04000000`) |
| Source 0 an + ready | `0x05600010` / `0x05600014` | `0x03000013` / `1` |
| Selektor | `0x051C006C` (LVDS) | `0x39000000` (RGB: `0x29000000`) |

Alle Latches wurden verbraucht, alle Werte hielten; die Firmware ließ den Zustand stehen (Zustand 4, Gate
`0x2007C`, Source 0 aktiv).

**Beleg, fester Belichtungswert 60, Messbereich auf der Projektionsfläche:**

| Messung | Ergebnis |
|---|---|
| Wand nach der Sequenz (`rezept_a.jpg`) | Sperrbildschirm des ThinkPad: Mint-Logo, Uhr **19:22**, richtige Geometrie |
| Gamma am Laptop 1 → 2,5 (`live_g1` → `live_g25`) | **91,5 %** der Bildpunkte verändert, mittlere Differenz 84 |
| Gamma 2,5 → 1 (`live_g25` → `live_g1b`) | **90,4 %** zurück |
| aufgehellt (`live_g25.jpg`) | kompletter Hintergrund des Sperrbildschirms mit Logo sichtbar |

Damit ist die gesamte Kette gezeigt: HDMI-RX → Capture → DRAM → AFBD Source 0 → PROC → Panel, **live**.

**Was noch nicht stimmt:** Die Capture liefert **NV16** (Chroma in voller Höhe, 04.07.-Notiz), Source 0 liest
NV12 (`+0x04C = 1920×540`) - die Farben sind damit noch falsch, das Luma-Bild ist korrekt. Der Ring wird von der
Firmware über pool-2 gedreht, unsere Slots zeigen fest auf Slot 0 - ein Tearing-Risiko, kein Blocker.

**Wo der richtige Eingriff sitzt:** in cstengers KMS-Treiber als NV12/NV16-Plane auf Source 0 (Patch 0078, plus
0079/0080 für Import und IOMMU), gespeist aus dem Capture-Ring statt aus Cedrus. Seine Serie enthält dazu 14
Patches, die unserer fehlen (0063-0086, siehe `patches/kernel/series` auf `origin/h713-display-video-path`).
Der VidDec-Descriptor bleibt ARM-seitige Pflicht (Stock: decd `dec_reg_set_address`).

## 11. 19:35-20:10 - RE-Antworten, Vendor-Daten, der Descriptor-Fehler und der Kachel-Zustand

Chronologisch, mit dem, was den Ausschlag gegeben hat. Alle Zeiten 06.09., Board seit Kaltstart 15:21 (Lauf 109).

### 11.1 Die drei RE-Fragen aus doku/77 (beantwortet)

**Frage 1 - „Slot fertig"-Ereignis des Capture-Rings.** Die Firmware dreht die Page-Flip-Zeiger `0x05600320/0x324`
mit 60 Hz durch drei Slots (Y `0x4C3EF000/0x4C5EE000/0x4C7ED000`, C `0x4C9EC000/0x4CBEB000/0x4CDEA000`).
Der INCAP (`0x06940000`) führt in `+0x104` einen Zähler: Bits 31..16 = Frame, Bits 15..0 = aktuelle Zeile;
`+0x100` pulst Statusbits. Der ARM bekommt den Takt über den AFBD-Vsync (`GIC 142`), den der KMS-Treiber schon
nutzt. Ein Treiber liest also `0x320/0x324` im Vsync und kennt den zuletzt fertigen Slot - kein eigenes Ereignis nötig.

**Frage 2 - Format-Bits am AFBD.** `NRWinNode_AfbdConfigure` (`0x8b1a3c58`) schreibt die Bits [14:8] des
Source-0-Steuerworts `0x05600010` aus `NRWinNode_ColorFormatConvert` (`0x8b1a2908`): Descriptor-`color_format`
0→0 (NV12), 2→1, 4→2, 6→3, 8/11→4, 9/12→5, 14→7, 15→6; Commit über `+0x6C`. **Stock fährt Code 0.** Der
Chroma-Gain `0x05140508` war *angenommen* bei Stock `0x144C0000` - **das ist unbelegt**:
die Stock-Registerabzüge decken `0x05140000` ab, enden aber bei `0x051400FC`
(`doku/nachtlog/I2`). Der Wert `0x144C0000` (Bits [23:16] = `0x4C`, kalibrierte Sättigung aus der PQ;
`0x04000000` = Chroma aus). Die Geometrie `0x48/0x4C = 0x04380960/0x021C0960` der Firmware ist für **unseren**
Puffer richtig; die Stock-Werte `…0780` (= 1920) verdoppeln bei uns das Bild vertikal (gemessen 19:40).

**Frage 3 - PQ-Fehler der MIPS beim Boot.** Stock-Verhalten: dieselben Meldungen stehen wortgleich in
`re/captures/weltneuheit/elog-stock-LIVE.bin`, und die gesuchten Konfigurationsschlüssel fehlen in jeder
`tvconfig`-Datei des Vendors. Kein Handlungsbedarf, kein Workaround.

### 11.2 Vendor-Daten aus `super.fex` (Marcos Hinweis war richtig)

`re/vendor/HY310/extracted/super.fex` ist ein Android-Sparse-Image; entpackt ist es ein LP-Container
(`system_a` 935 MiB, `vendor_a` 109 MiB ab Sektor 1918976, `product_a` 514 MiB). Aus `vendor_a` gesichert nach
`re/vendor/HY310/extracted/vendor_a/etc/`: `tvconfig/` (`tvpq.db`, `pq_colortemp.ini`, `pq_factory_extern.ini`,
`pq_overscan_config.ini`, `pq_picturemode.ini`, `pqcontrol_config/custom_setting.xml`,
`panel_config/panel_config.ini`, `portmap.cfg`, `HDMI_EDID_14/20.bin`, `tv_default.json`, `audio_config.ini`),
`display/mips/` (`display.bin` md5 `0d2191ca0d…`, `display_cfg.xml` - weicht vom Board-Exemplar ab: Panel
2128×1120/143 MHz, `work_mode 2`, elog Modus 2/Level 5; TSE-Dateien identisch mit `analyse/tse/board`) und
`firmware/` (`EXEC_KERNEL_IMAGE.bin`, `OS_ROM.bin`, `LogoRegData.bin`). Paket G aus doku/77 ist damit erledigt;
die Daten gehören auf das Gerät, nicht ins öffentliche Repo.

### 11.3 Der Fehler, der das Bild gekostet hat (19:44)

Um die Farbfrage (Capture NV16, Source 0 liest NV12) zu prüfen, habe ich im VidDec-Descriptor bei `0x4D95F000`
das Wort 16 (`color_format`) auf 4 und danach auf 2 gesetzt - in der Annahme, das sei nur unsere Eingabe für den
AFBD. **Das war falsch:** der Descriptor ist die Signalquelle der Firmware (Abschnitt 6). Jede Änderung löst
`HandleSignalEvent` → WCE neu aus, und die Firmware konfiguriert NR-, PROC- und Capture-Knoten für das neue
Format um - sie schrieb Stride- und Modusregister, das Bild fror ein bzw. zerfiel in Streifen. Der Rückweg auf
0 stellte den Zustand von 19:22 **nicht** wieder her (welche Register hängen blieben, ist genau der Gegenstand
von Abschnitt 12). Konsequenz: **Der Descriptor darf nur einmal, beim Enable, mit dem Format der Capture
beschrieben werden; Formatversuche laufen ausschließlich über den Kaltstart.**

Die Farbmessungen 19:47-19:52 sind **ungültig**: der Sperrbildschirm des ThinkPad ist fast schwarz, die per
tkinter erzeugten Farbfenster wurden auf dem gesperrten Schirm gar nicht angezeigt. Farbe bleibt ungemessen.
DPMS war nicht die Ursache (der Laptop zeigt Bild - Marco).

### 11.4 Der HPD-Zyklus und was die Firmware dabei umbaut

Um den Zuspieler neu ausgeben zu lassen, habe ich `arisc_edid_init.sh` erneut laufen lassen (PullHotPlug
DOWN 10 s → UP). Danach hatte die Firmware im AFBD verändert (Diff 19:46 → 19:55, nur Nicht-Zähler):

| Register | vorher | nachher | Bedeutung |
|---|---|---|---|
| `0x05600300` | `0x00800210` | `0x00804258` (jetzt `0x008042d8`) | pool-2-Steuerwort, Stock `0x00804218` |
| `0x05600304` | `0x00800000` | `0x00804000` (jetzt `0x0080c000`) | pool-2, Stock `0x00804000` |
| `0x05600310` | `0x00800210` | `0x00a00210` | pool-2, Stock `0x00800210` |
| `0x05600060` | `1` | `0x11` | Gate, Bit 4 von der Firmware (Stock `0x11`) |

Die drei pool-2-Worte lassen sich vom ARM **nicht** überschreiben (Schreiben + Rücklesen unverändert, 20:00);
sie liegen also auf Firmware-/Latch-Seite. Die 19:22-Sequenz erneut angewandt (19:57): das Bild ist **live**
(Uhr läuft), aber **vierfach gekachelt**, Logos rund → Aspekt erhalten, jede Kopie ein Viertel groß.

### 11.5 Was die Kachelung nicht ist - und was sie sein muss

- **Nicht die Capture.** Die Y-Ebene direkt aus dem DRAM gelesen (`0x4C3EF000`, 20:04): ein einzelnes, korrektes
  Bild mit laufender Uhr; Korrelation Spalte x zu x+480 = 0,04 (keine Selbstähnlichkeit), Zeile zu Zeile+4 = 0,84.
- **Nicht die Geometrie** `0x20/0x24/0x30/0x48/0x4C`, nicht die Format-Bits in `0x010` (`0x03000013` wie 19:22),
  nicht der Descriptor (Wort 16 = 0, sonst unverändert, „gültig: ja").
- Ein Leser, der **vier Bytes pro Pixel** konsumiert, erzeugt genau dieses Bild: vier Quellzeilen nebeneinander
  je Ausgabezeile (vier Kopien, je ¼ breit), 270 Zeilen für das ganze Bild (¼ hoch), danach die nächsten
  Ring-Slots als weitere Kachelreihen. Der Schalter dafür liegt außerhalb dessen, was die Sequenz von 19:22
  schreibt - also in dem, was die Firmware beim WCE-Neulauf oder beim HPD-Zyklus gesetzt hat.
- Gegen Stock (nach HDMI) unterscheidet sich die AFBD-Seite außer Zählern/Adressen nur in: Geometrie (`0x0960`
  vs `0x0780`, bewusst), `0x60` (`1` vs `0x11`), **ch1** (`0x100` = `0x00010000` vs `0x83001901`,
  `0x108/0x10c/0x12c` = 0 vs `0x008000ff/0x00ff0080/0x21`, Latch `0x104` bei uns unverbraucht), ch2-Konfiguration
  (`0x168/0x16c/0x184/0x1cc`, unser KMS-Treiber) und pool-2 (`0x300/0x304`).

**ch1 (Marcos Frage 20:07):** bei uns nicht aktiv; Stock hat ihn im HDMI-Betrieb mit Bit 31 an - laut doku/64
heißt Bit 31 „Page-Flip-Zeiger `0x320/0x324` verwenden", also der Ring, den die Firmware dreht. Stock zeigt das
HDMI-Bild demnach vermutlich über ch1 aus dem drehenden Ring, nicht über ch0 mit festem pool-1-Slot wie in
cstengers Rezept (das für Cedrus-Puffer gedacht ist). Offener Versuch, nicht gemessen.

### 11.6 Korrekturen an früheren Aussagen

- `0x051C006C` ist der LVDS-seitige Selektor eines **exklusiven** Mux (Source 0 oder RGB), kein Mixer.
- `0x05600038` ist ein W1C-Statusregister, kein Modusregister. Bit 31 in `0x010` gehört der Firmware (sie löscht es).
- Die Firmware-Geometrie `0x0960` ist richtig; Stock-`0x0780` ist für den Stock-Puffer, nicht für unseren.
- Die IOMMU ist unbeteiligt; TVTOP nur für CVBS/ATV.

### 11.7 Anforderung (Marco, 20:08) und Vorgehen

**Das Bild muss mehrere HDMI-Wechsel überstehen.** Ein Zustand, der nur nach Kaltstart und exakt einer Sequenz
steht, ist keine Lösung. Vorgehen ab 20:09 (Kaltstart): Rezept von 19:22 fahren, **im guten Zustand alle Blöcke
abziehen** (AFBD ganze Seite, PROC, LVDS, DE `0x05000000/0x050C0000`, INCAP, Descriptor) - diese Referenz
fehlte bis jetzt; dann einen HPD-Zyklus auslösen, erneut abziehen, Diff. Was die Firmware dabei umbaut, muss der
Treiber entweder mitgehen (Ring über ch1/pool-2) oder nach dem Wechsel wiederherstellen - und zwar so, wie es
Stock tut, nicht mit einem Poke.


## 12. 20:10-21:00 - **die Farbe ist gefunden: die Capture schreibt RGB, nicht YUV**

Kaltstart 20:09, Prep, `SetSource(3)`, ARISC-EDID-Sequenz, Descriptor, Source-0-Sequenz - Bild wieder auf der Wand
(20:15, einzeln, richtige Geometrie). Alle Registerabzüge dieser Reihe liegen in
`re/captures/weltneuheit/ours-20260906-source0/` (`dump_state.py` + `01_lock` … `08_desc0_again`).

### 12.1 Der Zustand hält HDMI-Wechsel aus

| Prüfung | Ergebnis |
|---|---|
| Zuspieler aus/an (`xrandr --output HDMI-2 --off/--auto`) | Bild kommt von selbst zurück, **keine** strukturelle Registeränderung (nur Zähler und Ring-Zeiger) |
| PullHotPlug DOWN 10 s → UP über die ARISC | Bild bleibt, **0 strukturelle Unterschiede** im Diff `04 → 05` |

Damit ist Marcos Anforderung „das Gerät muss mehrere HDMI-Wechsel überstehen" für den Wiederanlauf erfüllt. Die
Kachelung von 19:57 kam **nicht** vom HPD-Zyklus, sondern von der Descriptor-Änderung davor (Abschnitt 11.3).

### 12.2 Die Messung, die alles erklärt

Gamma am Zuspieler auf eine Farbe gezogen und die Ebenen im DRAM gemessen (`analyse/hdmi-seq/chroma_stat.py`,
Bildmitte, Zeilen 400-500):

| Zuspieler | Y-Ebene `0x4C3EF000` | gerade Bytes der 2. Ebene | ungerade Bytes |
|---|---|---|---|
| nur Rot | 16 (leer) | 16 (leer) | **27,1 (Signal)** |
| nur Grün | **27,4 (Signal)** | 16 | 16 |
| nur Blau | 16 | **28,1 (Signal)** | 16 |
| neutral | 27,4 | 28,1 | 27,1 |

**Die Capture schreibt RGB in einem 4:2:2-Behälter:** Ebene 1 = **Grün** (1 Byte je Pixel, Stride 1920),
Ebene 2 = **Blau und Rot verschachtelt**, horizontal 2:1 unterabgetastet (Stride 1920). Das deckt sich mit dem
Stock-TSE-Log (`VINCAP_ICSC ==> BYPASS` bei `V_INCAP_MP_Format ==> YUV422_888`): der Empfänger liefert RGB, die
Farbraumumsetzung macht Stock **später** in der VPROC, nicht in der Capture.

**Gegenprobe:** dieselben Daten am PC direkt als RGB zusammengesetzt (G aus Ebene 1, B/R aus Ebene 2, horizontal
verdoppelt) ergeben ein **neutralgraues, geometrisch korrektes Bild** (`scratchpad/rgb_direkt.png`) - mit der
YUV-Matrix dagegen ein durchgehend grünes (`rgb_stride1920.png`). Damit ist die Ebenenaufteilung bewiesen.

### 12.3 Der Chroma-Weg zum Panel funktioniert

Testbild in den Ringspeicher geladen (Capture vorher über INCAP `0x06940928/0968` Bit 31 angehalten,
`analyse/hdmi-seq/pat_load.py`) und die AFBD-Formate durchgefahren:

| Einstellung | Wand |
|---|---|
| fmt 0, C-Höhe 540 (`0x10=0x03000013`, `0x4C=0x021C0780`) | **8 Balken, volle Breite, richtige Geometrie, Farbe da** |
| fmt 0, C-Höhe 1080 | wie oben (die C-Höhe ändert nichts) |
| fmt 2 (`0x03000213`) | Geometrie zerfällt, ~2× horizontal gestaucht |
| fmt 4 (`0x03000413`), C-Stride 3840 | Farbe über das ganze Bild, aber Geometrie zerfällt |

Und mit **laufender** Capture: Y-Slots auf den Capture-Ring, C-Slots auf eine feste Fläche bei `0x4D700000`
(links Cb 240/Cr 110, rechts Cb 90/Cr 240) → die Wand zeigt **links blau, rechts rot mit dem Live-Luma darin**
(`wand/chroma_fest.jpg`, Uhr 20:53). Der Chroma-Pfad AFBD → PROC → Panel ist also vollständig in Ordnung;
**fmt 0 mit C-Stride 1920 ist die richtige Einstellung.**

### 12.4 Warum das Bild bis heute grau war

Nicht die Anzeige, sondern der **Inhalt** der zweiten Ebene: Stock-Capture liefert Blau/Rot, der AFBD liest sie als
Cb/Cr. Bei einem unbunten Bild sind Blau und Rot gleich dem Grün, also weit von 128 entfernt - das ergibt (mit der
YUV-Matrix) einen kräftigen Grünstich, kein Grau. Genau das steht seit 20:54 auf der Wand
(`wand/live_chroma.jpg`). Vorher war die Ebene 2 leer, weil die Capture sie gar nicht beschrieb: der Umschalter
dafür ist **INCAP `0x0694084C`** (`0x04000C00` → `0x0C000C00`, mit `0x06940400` `0x21`→`0x61` und `0x06940824`
Bit 31), den die Firmware beim Descriptor-Versuch (11.3) mitgesetzt hat.

> **Widerlegt am 07.09.** `0x06940400 = 0x61` und `0x06940824` Bit 31 kennzeichnen den Zustand **nach** dem
> Descriptor - und in dem ist die Capture **abgeschaltet**. Im laufenden Betrieb steht `0x21` bzw.
> `0x0000000B`, und das Bild läuft einwandfrei; wer die beiden Werte in einer Abnahme als Gutkriterium
> prüft, prüft das Falsche. Einzelheiten und der Korrekturkasten in
> [84-re-capture-ring.md](84-re-capture-ring.md); Messung in
> [`nachtlog/B2-quellenwechsel.md`](nachtlog/B2-quellenwechsel.md) (Korrektur 1 und 2) und
> [`nachtlog/A-abnahme-board.md`](nachtlog/A-abnahme-board.md).

### 12.5 Woran es jetzt hängt - und die drei Wege

Der Panelpfad rechnet YUV→RGB, die Daten sind RGB. Zu lösen ist **eine** Umsetzung, sonst nichts:

1. **Capture umschalten (Stock-Weg).** Die INCAP hat eine eigene Farbraumstufe (`VINCAP_ICSC`, im Stock auf
   `BYPASS`). Steht der Eingang auf RGB, wandelt Stock später in der VPROC. Zu klären: welches Register die
   VPROC-Matrix wählt (Kandidaten im PROC-Block `0x05140300…0x051403C4`, Werte wie `0x55FF0055`, `0x66FF0266`).
2. **PROC-Matrix auf „Eingang ist RGB" stellen** - derselbe Registersatz, andere Wahl.
3. **INCAP-ICSC einschalten**, damit die Capture echtes YUV schreibt; dann passt der ganze Rest ohne Änderung.

   > **Widerlegt am 07.09., soweit es die Registerdeutung betrifft.** Die zu diesem Weg genannten Marken
   > `0x06940400 = 0x61` und `0x06940824` Bit 31 (§12.4) beschreiben den Zustand **nach** dem Descriptor,
   > in dem die Capture abgeschaltet ist - nicht den laufenden Betrieb (dort `0x21` / `0x0000000B`).
   > Siehe den Kasten in §12.4, [84-re-capture-ring.md](84-re-capture-ring.md) und
   > [`nachtlog/B2-quellenwechsel.md`](nachtlog/B2-quellenwechsel.md).

Weg 3 ist der sauberste, wenn Stock ihn bei RGB-Quellen ebenfalls geht; das ist am TSE-Log zu prüfen
(`attr_id:101, VINCAP_ICSC`). Kein Weg braucht einen Quirk.


## 13. 21:10 - **die Farben stimmen: ein verdoppelter Chroma-Zeilenabstand**

**Der Befund.** Marcos Foto (21:05, mit eingezeichnetem Bildrahmen) zeigte den Kern: die Farbe war gegenüber der
Helligkeit **vertikal 2× gedehnt**, verankert oben - Farbe aus der oberen Bildhälfte lag über der unteren, unter
dem Bildrand quollen Farben in die weiße Fläche. Genau das passiert, wenn ein **NV12-Leser** (Chroma halbe Höhe)
einen **NV16-Puffer** (Chroma volle Höhe) liest: für Ausgabezeile *r* holt er Chromazeile ⌊r/2⌋, und die gehört
im NV16-Puffer zu Bildzeile ⌊r/2⌋ statt *r*.

**Die Lösung.** Nicht den Formatcode wechseln (`0x03000213`/fmt 2 zerlegt die Luma-Geometrie und färbt alles
grün, Beleg `wand/f422.jpg`), sondern den **Chroma-Zeilenabstand verdoppeln**:

```
0x05600040 (Y-Stride) = 0x00000780   (1920, unverändert)
0x05600044 (C-Stride) = 0x00000F00   (3840 statt 1920)
0x05600010            = 0x03000013   (Formatcode 0, unverändert)
0x0560004C            = 0x021C0780   (Chroma-Höhe 540, unverändert)
```

Dann ist die Chroma-Adresse für Ausgabezeile *r* gleich ⌊r/2⌋ × 3840 = Zeile *r* (bzw. *r*−1) des NV16-Puffers -
also **exakt 4:2:2**, ohne Formatwechsel und ohne Trick an anderer Stelle. Ein Register, eine Ursache.

**Beleg (Kaltstart 21:08, Lauf mit buntem Zuspielerbild):**

| Zustand | Wand |
|---|---|
| C-Stride 1920 (`wand/ok1.jpg`) | Bild richtig, Farben vertikal 2× verschoben, Spirale blass |
| **C-Stride 3840 (`wand/cstride.jpg`)** | **Spirale deckungsgleich im Rahmen, volle Regenbogenfarben, Weiß neutral, Rot rot** |
| danach Zuspieler aus/an (`wand/nach_wechsel1.jpg`) | unverändert richtig |
| danach PullHotPlug DOWN/UP (`wand/nach_hpd2.jpg`) | unverändert richtig |

`analyse/hdmi-seq/afbd_source0.py on` setzt die beiden Stride-Register jetzt selbst; `off` stellt 1920 zurück.

**Was dabei über die Capture gelernt wurde (und drei Irrtümer von 20:4x korrigiert):**

- Die Capture schreibt **YUV**, nicht RGB: nach Kaltstart und Firmware-eigener Freigabe liegt Cb/Cr um 128
  (gemessen: Cb 130,7, Cr 137,0 bei buntem Bild; ±22 bei fast grauem Sperrbildschirm). Die RGB-artigen Ebenen aus
  Abschnitt 12.2 waren **Folge meines eigenen Eingriffs**: nach dem Descriptor-Versuch und dem manuellen Setzen
  von INCAP `0x06940928/0968` Bit 31 kippt die Capture in eine andere Ausgabeart (Ebene 1 = Grün, Ebene 2 = Blau
  und Rot). Abschnitt 12.2 gilt nur für diesen verstellten Zustand.
- **INCAP-Register nie von Hand setzen.** Das Bit-31-Setzen liefert genau einen Rahmen und verklemmt die Capture
  danach (alle drei Ringplätze identisch, `0x104` zählt weiter). Sauber ist allein: Kaltstart → Prep →
  `SetSource(3)` → EDID-Sequenz → **einmal** `viddec_descriptor.py set` → `afbd_source0.py on`.
- Der Chroma-Pfad selbst ist in Ordnung: mit fester Farbfläche bei `0x4D700000` an den C-Slots zeigt die Wand
  links blau, rechts rot mit dem Live-Luma darin (`wand/chroma_fest.jpg`).
- Der Chroma-Gain `0x05140508` skaliert die Sättigung. Er ist **nicht** die Ursache des Versatzes. Seit 21:2x ist
  er an die Stock-PQ angeschlossen: die Werkskurve für HDMI (`pq_factory_extern.ini`, Sättigung
  `0,48,96,145,192`) trifft mit dem am Stock kalibrierten `0x4C` für Benutzerwert 50 zusammen, daraus rechnen
  sich die Bildmodi (`cinema` `0x44`, `standard` `0x4C`, `vivid` `0x5C`) - Werkzeug
  `analyse/hdmi-seq/pq_saturation.py`, Herleitung und Messung in doku/77 Abschnitt 4.

**Damit ist die Kette vollständig:** HDMI-RX → INCAP-Capture (NV16, YUV) → DRAM-Ring → AFBD Source 0 (fmt 0,
C-Stride 3840) → PROC → LVDS → Panel, **mit richtiger Geometrie und richtigen Farben**, und sie übersteht
Quellenwechsel und Hot-Plug.
