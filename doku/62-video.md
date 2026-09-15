# Video: VE-Dekodierung und Wiedergabe auf dem Panel

Stand 01.09.2026. Ziel war, seine Aussage *„video decode is DONE, 59.71 fps
zero-copy"* auf unserem Board nachzubauen. Das läuft - bei **1920×1080**, wo
er 1280×720 gemessen hat.

## Was läuft

| | |
|---|---|
| H.264-Dekodierung | **bit-exakt**, v01 bis v05, bis 1920×1080 |
| HEVC-Dekodierung | **bit-exakt**, h01 und h02 |
| Zero-Copy-Wiedergabe | **59,41 fps bei 1920×1080**, 2411 Bilder, 0 Commit-Timeouts |
| Ausrichtung | korrigiert, gegen einen Rot-oben/Blau-unten-Clip nachgemessen |
| Pufferung | **doppelt**, seit Patch 0049 den Carveout auf 16 MiB bringt |

Die Leiter, `tools/video/make-test-streams.sh` und ein selbst erzeugter
1080p-Vektor, alle gegen eine **eigene** Host-Referenz gemessen:

```
v01-320x240-baseline   223 ms   bit-exakt
v02-1280x720-baseline 1646 ms   bit-exakt
v03-1280x720-main     1702 ms   bit-exakt
v04-1280x720-high     1706 ms   bit-exakt
h01-640x480-main       357 ms   bit-exakt   HEVC
h02-1280x720-main      768 ms   bit-exakt   HEVC
v05-1920x1080-high    3876 ms   bit-exakt   unser Panel, von ihm nie geprüft
```

## Warum die CPU-Strecke nichts taugt

Stufenweise gemessen, 60 Bilder in 1080p:

| | | |
|---|---|---|
| nur dekodieren (`fakesink`) | 1 797 ms | **33 fps** |
| dazu CPU-Konvertierung NV12→BGRx | 15 641 ms | **3 fps** |
| dazu `fbdevsink` | 16 181 ms | 3 fps |

**97 % der Zeit steckt in der Farbraumkonvertierung.** Die Ausgabe kostet
fast nichts. Das ist derselbe Befund wie sein 28,3-fps-Deckel bei 720p, nur
bei 2,25-facher Pixelzahl.

Der Ausweg ist seiner: die GPU konvertiert, `tools/video/gles-play.c`.

## Fünf Defekte in dem, was übergeben wurde

Alle am Gerät reproduziert, alle behoben.

**1. `emit-signals=true` fehlt am `appsink`.** Ohne das feuert das Signal
`propose-allocation` nie, der Handler bietet `GstVideoMeta` nicht an, und der
Treiber bricht ab:

```
v4l2codecs-h264dec: DMABuf caps negotiated without the mandatory support of VideoMeta
v4l2codecs-h264dec: Failed to negotiate with downstream
```

Das Programm holt die Frames per Pull-API, deshalb steht `emit-signals` auf
der Vorgabe `false`.

**2. Die Vorgabe-Caps widersprechen dem eigenen Kommentar.** Über der Zeile
steht, `memory:DMABuf` sei *„the load-bearing part"*, und im Code stand:

```c
getenv("GLES_CAPS") ? getenv("GLES_CAPS") : "video/x-raw,format=NV12"
```

Also Systemspeicher. Sein dokumentierter Aufruf endet damit in
`REFUSED: 1 buffer(s) were not dma-buf backed`. Vorgabe jetzt
`video/x-raw(memory:DMABuf),format=DMA_DRM`.

**3. `gst_video_info_from_caps()` kann `DMA_DRM` nicht lesen.** Bei
DMABuf-Caps ist `format` das Literal `DMA_DRM`, das echte Pixelformat steht
in `drm-format`. Ergebnis: Format `DMA_DRM`, null Ebenen, und die eigene
NV12-Prüfung wirft die eigene Dekoderausgabe weg - `expected NV12`. Richtig
ist `gst_video_info_dma_drm_from_caps()`, wofür `video-info-dma.h` schon
eingebunden war.

**4. Das Pufferlayout ist auf 720p gerechnet.**

```c
#define FB_FRONT 0x6c100000UL
#define FB_BACK  0x6c500000UL     /* 4 MiB Abstand = ein 720p-ARGB-Frame */
```

Bei 1920×1080 ist ein Frame 7,91 MiB. Der Backbuffer läge im Frontbuffer und
über dem Ende des 8-MiB-Carveouts; der Exporter lehnt ihn ab. Jetzt werden
Basis und Größe zur Laufzeit aus
`/sys/module/sunxi_scanout_dmabuf/parameters/` gelesen und die Slotgröße aus
der Bildgröße gerechnet. Passen zwei nicht, läuft es einfach gepuffert **mit
Ansage**, statt außerhalb der Reservierung zu schreiben.

**5. Das Bild stand auf dem Kopf.** GL rendert von unten nach oben in den
FBO, AFBD liest von oben nach unten - eine Spiegelung gehört in den Shader,
aber welche, ist eine Eigenschaft des Panels. Mit einem Clip aus roter oberer
und blauer unterer Hälfte gemessen:

| Zeile im Scanout-Puffer | sein Shader | korrigiert | Quelle |
|---|---|---|---|
| 0 (Panel oben) | `0xFF000FFF` blau | `0xFFFF1800` **rot** | rot |
| 1079 (Panel unten) | `0xFFFF1800` rot | `0xFF000FFF` **blau** | blau |

Beamer spiegeln für Deckenmontage in der Firmware; das ist die naheliegende
Erklärung, warum derselbe Shader auf seinem Board richtig herum aussah.
`GLES_FLIP_Y=1` stellt sein Vorzeichen wieder her.

**Dazu:** `tools/video/reference-md5.txt` existiert im Baum nicht, obwohl
`m1-decode-test.sh` dagegen vergleicht. Das Gate meldet dann für jeden Vektor
`no reference on file; size only` - es kann nichts durchfallen lassen. Wir
rechnen unsere eigene Referenz, weil ohnehin eine andere x264-Version einen
anderen Bitstrom erzeugt.

## Grenzen der Hardware

**Cedrus kann nur 4:2:0, 8 Bit.** Ein echter Clip mit `High 4:4:4
Predictive` / `yuv444p` wird korrekt abgelehnt:

```
pipeline error: Driver does not support the selected stream.
gstv4l2codech264dec.c(376): gst_v4l2_codec_h264_dec_negotiate
```

Das ist kein Fehler, sondern die Sensorgrenze. Umkodieren mit
`-pix_fmt yuv420p -profile:v high`.

**`gles-play` skaliert nicht.** Es verschiebt nur AFBDs Quelladresse und
fasst Stride und Größe nie an, das Video muss also exakt die Panelgröße
haben. Bei ihm war Video wie Panel 1280×720 und die Annahme unsichtbar; jetzt
wird sie geprüft und mit einer Meldung abgelehnt, statt ein schiefes Bild zu
erzeugen.

## `kmssink` geht nicht

Sein KMS-Treiber setzt

```c
drm->mode_config.min_width = drm->mode_config.max_width = h->mode.hdisplay;
```

Das ist der `simpledrm`-Stil und für sich in Ordnung, aber GStreamers
`kmssink` baut daraus einen `GstIntRange(1920,1920)`:

```
gst_value_collect_int_range: assertion 'collect_values[0].v_int < collect_values[1].v_int' failed
```

Auf seinem Board wäre das genauso; er hat `kmssink` nie benutzt. Nicht
behoben, weil der GPU-Pfad ohnehin der schnellere ist - aber es ist der
Grund, warum die naheliegendste Pipeline nicht startet.

## So läuft es

Auf dem Gerät, Werkzeugkette einmalig:

```bash
apt-get install -y --no-install-recommends gcc libc6-dev pkg-config \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libegl-dev libgles-dev
```

Bauen und abspielen:

```bash
gcc -O2 -o gles-play gles-play.c $(pkg-config --cflags --libs \
    gstreamer-1.0 gstreamer-app-1.0 gstreamer-allocators-1.0 \
    gstreamer-video-1.0) -lEGL -lGLESv2
EGL_PLATFORM=surfaceless ./gles-play clip.h264
```

Quelle vorbereiten, exakt Panelgröße und 4:2:0:

```bash
ffmpeg -i eingabe.mp4 -an -pix_fmt yuv420p -c:v libx264 -profile:v high \
       -vf scale=1920:1080 -f h264 clip.h264
```

## Merge-Schuld: die Reservierung steht an der falschen Stelle

Patch 0049 vergrößert `uboot-scanout` von 8 auf 16 MiB - **in
`sun50i-h713.dtsi`, also auf SoC-Ebene.** Die Größe hängt aber am Panel, und
das ist eine Board-Eigenschaft. So wie es dasteht, reserviert jedes H713-Board
16 MiB, auch eins mit 720p, das 8 davon nie anfasst.

Der Grund dafür ist unangenehmer als der Patch: **wir fahren seine Board-DTS.**
Der FIT lädt `sun50i-h713-hy200-qz713df-a1`, aus seinem Patch 0024, samt
seiner `bootargs` mit `root=/dev/mmcblk0p26`. Es gibt keine Datei im Baum, an
der „dieses Board hat 1920×1080" hinge. Der einzige Ort, an dem unsere
Variante überhaupt auftaucht, ist die ProjectID, die **U-Boot zur Laufzeit**
auswählt - `0x30` bei uns gegen `0x34` bei ihm - und die der Kernel gar nicht
sieht. Sein eigenes U-Boot-Log sagt es beim Start mit:

```
H713 disp: project 0x30 is HY310 (QZ713 V3.1), panel 1920x1080
H713 disp: note: this board declares project 0x34 (panel_config.ini ProjectID = 52)
```

**Vor dem Zurückgeben zu klären:** unsere Variante braucht eine eigene
Board-DTS, und die Reservierung gehört dorthin - als Überschreibung über das
Label, `&framebuf_reserved { reg = <0x6c100000 0x1000000>; };`. Dann trägt
jedes Board seine eigene Größe, und die Frage „woran erkennt sein Build, dass
das ein 1080p-Gerät ist" hat eine Antwort im Devicetree statt nur im
Bootloader. Solange beide Boards dieselbe DTS benutzen, ist die 16-MiB-Zahl
im dtsi der einzige Weg, der auf unserer Hardware funktioniert - aber sie ist
nicht die Fassung, die man ihm schickt.

## Offen

- **Tearing nicht vermessen.** Doppelpufferung läuft, aber seine
  `gles-tear`-Messung (0,00 % gegen 16,94 % Positivkontrolle) haben wir nicht
  wiederholt - die braucht ein Foto der Wand. Bisher nur mit dem Auge geprüft.
- **Kein Ton.** `gles-play` ist reines Video.
- **Kein Container.** Nur Annex-B-Elementarströme; der Dekodierpfad hat
  keinen Demuxer.

## Der eigentliche Konstruktionsfehler: wir fahren die falsche AFBD-Ebene

Aufgefallen am 01.09.2026 durch Marcos Frage „wir dekodieren doch schon NV12,
wozu dann XRGB8888?". Die Antwort steht in `re/notes/DISPLAY-CHAIN-RE.md` und
ist am Gerät bestätigt:

**AFBD hat zwei Kanäle.**

| | Adresse | Format | Quelle |
|---|---|---|---|
| `ch0` | `0x05600100` | **NV12, Video** | `0x05600320` / `0x05600324` |
| `ch1` | `0x05600140` | XRGB, Grafik/OSD | `0x05600178` |

Live auf unserem Board:

```
05600100: 00010000     ch0 aus
05600140: 03001901     ch1 aktiv
05600320: 4C7ED000     ch0-Quellpaar, identisch mit dem Stock-Mitschnitt
05600324: 4CDEA000
```

Im Stock steht es umgekehrt: ch0 = `0x83001901` (NV12 **enabled**), ch1 =
`0x83001900` (Bit 0 = 0, aus). Das Registerlayout der beiden Kanäle ist
deckungsgleich mit 0x40 Versatz - `0x05600124` und `0x05600164` lesen beide
`0x00000808`.

**Folge:** cstengers KMS-Treiber und `gles-play` fahren beide `ch1`. Deshalb
kann der Treiber nur `XRGB8888` anbieten, deshalb muss jemand NV12→RGB
umrechnen, deshalb kostet es die CPU 3 fps oder die GPU einen ganzen
Zwischenschritt. Über `ch0` ginge der Weg **VE → AFBD** ohne eine einzige
Umrechnung, und `kmssink` mit `playbin` wäre ein ganz normaler Player.

**Warum das nicht mal eben gemacht ist:**

- Die ch0-Plane-Konfiguration ist nur teilweise rekonstruiert
  (`init_osd_plane` aus `ge2d_dev`), und der Vendor setzt sie über
  `dec_reg_video_channel_attr_config()` mit einem `mode`-Parameter, dessen
  Werte wir nicht alle kennen.
- Die Notizen nennen zusätzlich ein Enable-Set in DE, INCAP und TVTOP
  (`memory_agent_onoff`), ohne das ch0 nichts ausgibt.
- Genau diese Blöcke (`0x05200000`, `0x0524c000`, `0x0525c000`) **darf man
  aus Linux nicht lesen** - das wedgt den Interconnect, siehe
  [61-plan-vblank.md](61-plan-vblank.md). Der Zustand muss über UART aus
  U-Boot geholt werden.
- Ein früherer Versuch in diese Richtung ist gescheitert und cstenger hat
  seine Behauptung „Direct YUV scanout WORKS" ausdrücklich zurückgezogen.

`/dev/mem`-Schreibzugriffe sind **kein** Hindernis: `0xA5A5` nach
`0x05600110` liest als `0x05A5` zurück - die Bits kommen an, das Register hat
nur ein schmaleres Feld. Die alte Notiz „Pokes wurden rejected" gilt für
diesen Weg nicht.

**Nächster sinnvoller Schritt** wäre nicht weiteres Herumprobieren am
Player, sondern: ch0-Zustand und das DE/TVTOP-Enable-Set **aus U-Boot**
auslesen, gegen einen Stock-Boot vergleichen (der A/B-Umschalter steht,
siehe [90-stock-referenz.md](90-stock-referenz.md)), und ch0 erst dann
scharfschalten.

## ch0/NV12: was in der Nacht 01.09. gemessen wurde

Ausgangspunkt war Marcos Frage. Alles unten ist am Gerät gemessen, mit
**geparktem MIPS** (`h713_disp auto … quiesce`) - das ist der Unterschied zu
allen früheren Sitzungen in `re/notes/`, wo der MIPS die HDMI-Capture-Pipeline
fuhr und die Register laufend selbst beschrieb.

### Neu: ch0 hat eine ARM-schreibbare Quelle

Alle bisherigen Versuche gingen über den **globalen** Page-Flip
`0x05600320/0x324`. Der nimmt keine ARM-Writes - heute erneut bestätigt, und
zwar **auch bei geparktem MIPS**:

```
0x05600320  geschrieben 0x11223000 -> gelesen 0x4C7ED000   verworfen
0x05600324  geschrieben 0x22334000 -> gelesen 0x4CDEA000   verworfen
```

Bit 31 der Kanalsteuerung wählt aber zwischen globalem Page-Flip und
**per-Kanal-Quelle**. Bei ch1 ist die per-Kanal-Quelle `+0x178`; ch0 spiegelt
ch1 mit 0x40 Versatz, und dort liegen **zwei** Adressregister nebeneinander:

```
0x05600138   0 -> 0x6C900000   HAELT     Y-Ebene
0x0560013c   0 -> 0x6CAFA400   HAELT     C-Ebene
```

Das ist genau das Paar, das NV12 braucht, und es gehört uns. In `re/notes/`
ist dieser Weg nirgends geprüft - dort ging es immer um den globalen Ring,
weil der MIPS ihn fährt.

### Die NV12-Geometrie steht bereits

U-Boot hinterlässt sie fertig, passend zu
`NRWinNode_AfbdConfigure` aus `CURRENT-TRUTH.md`:

```
0x05600040 = 0x00000780   Y-Stride 1920
0x05600044 = 0x00000780   C-Stride 1920
0x05600048 = 0x04380780   Y-Geometrie 1920x1080
0x0560004c = 0x021C0780   C-Geometrie 1920x540
0x05600010 = 0x03000010   Bit31=0 (per-Kanal), pixfmt[14:8]=0 (NV12)
```

### Was angewendet wurde

`re/work/weltneuheit/scripts/ch0_nv12_stock_init.py` ist die
disasm-verifizierte `init_osd_plane`-Sequenz. Angewendet, mit **Bit 31
CLEAR** statt gesetzt, weil wir die per-Kanal-Quelle wollen:

| Register | Wert | angenommen |
|---|---|---|
| `0x05600108` | `0x008000FF` | ✓ |
| `0x0560010c` | `0x00FF0080` | ✓ |
| `0x05600110` | `0x043F077F` | ✓ |
| `0x05600124` | `0x00000808` | ✓ |
| `0x05600128` | `0x00000082` | **nein**, bleibt 0 (Status, write-1-clear) |
| `0x0560012c` | `0x00000021` | ✓ |
| `0x05600138/13c` | Y/C | ✓ |
| `0x05600100` | `0x03001901` | ✓ |
| `0x05600140` | `0x03001900` (ch1 aus) | ✓ |
| `0x05600060` | `\|= 0x10` (`dec_reg_int_to_display`) | ✓ |
| `0x05600010` | `\|= 0x3` (memory_agent) | ✓ |
| `0x05600014` | `\|= 0x1` | **nein**, bleibt 0 |
| VBlender `0x0520003c` | Bit-24-RMW | ✓ |
| OSD-Plane `0x05248000` | acht Register | ✓ |

### Ergebnis und der offene Rest

**ch0 rastet nicht ein**: `READY (0x05600104)` bleibt 1, `STATUS (0x05600128)`
bleibt 0. Bei ch1 löscht sich `READY` am Vsync selbst - der Vsync läuft
nachweislich weiter.

Zwei echte Lebenszeichen gibt es trotzdem: der **Quellen-Mux `0x05600300`
stellt sich bei jedem Schritt selbst weiter** (`0x00800210` → `0x00804218` →
`0x0080C218` → `0x008042D8`), die Hardware reagiert also auf die
Konfiguration. Und der VBlender wie die OSD-Plane waren vorher **komplett
null** und nehmen die Werte an.

**Offen ist der DE-Enable-Satz.** `memory_agent_onoff` schaltet laut
`CURRENT-TRUTH.md` noch Register in Blöcken, die wir bis jetzt gar nicht
angefasst haben:

```
0x001 -> TVTOP  0x068B00B8/C4/D0 bit0
0x002 -> TVTOP  0x068B00DC/E8/F4 bit0
0x004 ->        0x068B044C bit18
0x008 -> INCAP  0x06940928/0968 bit31
0x010 -> AFBD   0x05600010 bits0+1 + 0x05600014 bit0
0x020 -> DE     0x05000178/01B8 bit31
0x040 -> DE     0x05000278/02B8 bit31
0x080 -> DE     0x050C06F8/0738 bit31
0x100 -> DE     0x050C07B8 bit31
0x200 -> DE     pool-2 0x050C0478/04F8/0578/05F8/0678 bit31
```

Von diesen ist bei uns nur die AFBD-Zeile gesetzt. Die DE-Blöcke bei
`0x05000000` und `0x050C0000` sind bislang unberührt - und sie sind der
naheliegendste Grund, warum ch0 nicht durchkommt.

### Der vollständige `init_osd_plane`-Replay - und was er ergibt

Nach dem Durchlesen des ganzen Materials (nicht nur des einen Skripts) ist die
Sequenz vollständig bekannt. Die **genaueste** Quelle ist nicht
`re/notes/CH0_INIT_OSD_PLANE_FULL.md`, sondern Marcos C-Rekonstruktion
`legacy/drivers/display/ge2d/sunxi_ge2d_osd.c`, `ge2d_plane_init()`. Sie
weicht an drei Stellen von der Notiz und vom `ch0_nv12_stock_init.py` ab:

| | Notiz / Skript | `sunxi_ge2d_osd.c` |
|---|---|---|
| `0x05248000` | `0x80FC0208` | **`0x80FF0008`** |
| `0x05248010` | `0x04650898` | **`0x04650098`** |
| `0x05600100` | `0x83001901` | **`0x83000201`** |

Dazu zwei Blöcke, die im Skript **fehlen**:

- `ge2d_config_vblender_irq()`: `0x05240018 |= BIT(14)`
- `ge2d_plane_vblender_writes[]`: `0x05200040 = 0x1A000005`,
  `0x05200050 = 0x00350000`, `0x05200054 = 0x08100035`

Und der Commit-Strobe ist **kein** RMW auf `0x0520003c`, wie das Skript es
macht, sondern **lesen von `0x05200048`, schreiben nach `0x0520003c`** mit
Bit 24 clear/set/clear. Die VBlender-Basis ist damit auch aufgelöst:
`0x0520002C`, nicht das in der Notiz vermutete `~0x05208000` - dort liest der
ganze Block 32× denselben Wert `0x00001800`, das ist kein Steuerblock.

Alles davon wurde in der Treiber-Reihenfolge angewendet, `/root/video/plane_init.sh`.
**Jedes einzelne Register nimmt seinen Wert an.** Der Zustand danach:

```
ch0 CTRL=0x83000201  READY=1  STATUS=0
pool-2 0x320=0x4C7ED000  0x324=0x4CDEA000   (unverändert)
```

### Das entscheidende Experiment

ch0 wurde anschließend **Register für Register auf ch1 angeglichen** - bis auf
die beabsichtigten Unterschiede (Stride 0x780 statt 0x1E00, eigene Y/C-Adressen):

```
      ch0          ch1
+0x00 0x03001901   0x03001901     identisch
+0x08 0x008000FF   0x008000FF
+0x0c 0x00000080   0x00000080
+0x10 0x043F077F   0x043F077F
+0x14 0x00430077   0x00430077
+0x20 0x04380780   0x04380780
+0x24 0x00000808   0x00000808
+0x2c 0x00000021   0x00000021
+0x04 READY  1          0        <-- ch1 rastet ein, ch0 nie
+0x28 STATUS 0          2        <-- ch1 DONE, ch0 nie
```

**Bei identischer Konfiguration rastet ch1 ein und ch0 nicht.** Damit liegt
die Ursache nachweislich *außerhalb* des Kanal-Registerblocks. Auch
`0x05240018` komplett auf `0xFFFFFFFF` (alle Interruptquellen frei) ändert
nichts.

### Was daraus folgt

ch1 rastet am **Display-Vsync** ein - dem Interrupt, den wir heute Nacht zum
Laufen gebracht haben. ch0 tut das nicht, obwohl derselbe Vsync läuft. Der
Frame-Trigger von ch0 kommt also aus einer anderen Quelle, und die
naheliegendste ist die **Video-Pipeline des MIPS**: `pool-2` (`0x320/0x324`)
bewegt sich bei uns überhaupt nicht, weil die Page-Flip-Engine erst nach
MIPS-Signal-Valid läuft - unser U-Boot parkt den Coprozessor ausdrücklich
(`MIPS core quiesced, display clocks retained`).

In den früheren Sitzungen war es umgekehrt: der MIPS lief und hat ARM-Writes
auf `0x320/0x324` innerhalb von ~16 ms überschrieben. Beide Male ist pool-2
unerreichbar, aus entgegengesetzten Gründen.

**Nächstes Experiment, klar umrissen:** kalt starten mit `h713_disp init 0x30`
**ohne** `quiesce`, also mit laufendem MIPS, und denselben Replay wiederholen.
Wenn ch0 dann einrastet, ist der Trigger identifiziert und die Frage wird, wie
man den MIPS dazu bringt, aus *unserem* Cedrus-Puffer zu flippen statt aus dem
HDMI-Capture. Wenn er auch dann nicht einrastet, fehlt noch etwas Drittes und
die Suche geht im DE-Enable-Satz weiter (`0x05000000`, `0x050C0000`).

### Nebenbefund, der viel wert ist

**Die Display-Blöcke sind aus Linux jetzt lesbar.** `0x05200048` liest sauber
`0x00000000`, der SoC überlebt es. Vor der `clk_ignore_unused`-Reparatur hat
genau dieser Zugriff das Board gewedgt. Damit ist die ganze Kette - DE,
Mixer, VBlender, TCON - zum ersten Mal aus dem laufenden Linux beobachtbar,
statt nur über UART aus U-Boot.


## Nachtrag: die Registerkarte stimmt jetzt, und die alte Schlussfolgerung fällt

Nach dem vollständigen Durchlesen von `re/notes/`, `re/work/weltneuheit/` und
einem eigenen IDA-Lauf gegen `display.bin` ist die AFBD-Karte aufgelöst. Ich
hatte sie vorher an drei Stellen falsch.

### Was wo steht - dekompiliert, nicht geraten

Eigener IDA-Headless-Lauf (`idat -A -S…` gegen
`re/ida/weltneuheit/re_chain/display.bin.i64`, auf einer Kopie):

| Funktion | schreibt |
|---|---|
| `NRWinNode_WriteAfbdBufStride` @`0x8b1a38ac` | **`0x05600040`** Y-Stride, **`0x05600044`** C-Stride |
| `NRWinNode_WriteAfbdCropWin` @`0x8b1a3940` | **`0x05600048`** Y 1920×1080, **`0x0560004C`** C 1920×540 |
| `sub_8B1A3800` @`0x8b1a3800` | `0x05600020`, `0x05600024`, `0x05600030` |
| `NRWinNode_ColorFormatConvert` @`0x8b1a2908` | Format → **`0x05600010` Bits [14:8]**, **0 = NV12** |

**Die gesamte NV12-Geometrie ist global**, nicht per Kanal. Das Kanalregister
trägt nur Enable und Quelladresse. Auf unserem Board stehen **alle** globalen
Werte bereits korrekt:

```
0x05600020 = 0x043F077F   0x05600040 = 0x00000780
0x05600024 = 0x00420077   0x05600044 = 0x00000780
0x05600030 = 0x04380780   0x05600048 = 0x04380780
                          0x0560004C = 0x021C0780
0x05600010 = 0x03000010   Format [14:8] = 0 = NV12
```

### Drei Messungen am lebenden Prüfstand

Der NV12-Frame wurde in **den Puffer geschrieben, den AFBD gerade anzeigt**
(`0x6c100000`), damit die Adresse als Variable wegfällt. Das Bild änderte sich
sofort zur typischen Vierfach-Wiederholung - der Prüfstand ist also live.

1. **Formatfeld im Kanal-CTRL `0x05600140` [15:8]**: alle 17 Werte
   (`0x00`…`0x0f`, `0x19`) durchgefahren - **keine sichtbare Änderung**.
2. **Formatfeld im globalen `0x05600010` [14:8]**: alle acht dokumentierten
   Werte - **keine Änderung**. Ebenso `0x05600164`.
3. **`0x05600010` Bit 31** (laut Dekompilat der Source-Mode): gesetzt, ch1
   rastet ein - aber das Panel liest **weiterhin `0x178`**, nicht pool-2. Bit 31
   schaltet die Quelle also **nicht** um.

### Der Deskriptor ist der Auslöser - und der MIPS der Ausführende

`_videodec_poke.py` aus `weltneuheit` läuft unverändert auf unserem Board
(`0x4d95f000` liegt auch bei uns im reservierten `decoder@4d941000`). Der
144-Byte-Deskriptor wird geschrieben, `0x05600098` hält den Zeiger:

```
0x098 = 0x4D95F000    HÄLT
0x320 = 0x4C7ED000    unverändert
0x010 = 0x03000010    unverändert
0x06c = 0             kein Commit
```

Im Gerätetest vom 13.06.2026 hat genau dieser Poke die **komplette Kette**
gefeuert, und danach hat *der MIPS* `0x010 = 0x03000013` geschrieben und
pool-2 auf ein sauberes Y/C-Paar geflippt. Bei uns passiert nichts.

**Der Unterschied ist der geparkte Coprozessor.** Unser `bootcmd` fährt
`h713_disp auto 0x30 logo`, und das endet mit `MIPS core quiesced`.

### Damit fällt die alte Schlussfolgerung

`re/work/weltneuheit/scripts/ch1_nv12_test.py` schließt mit:

> kein ARM-register-poke gibt clean color. Einziger Weg = CPU/NEON
> NV12→XRGB in ch1-`+0x178`-Buffer

Das ist als Beobachtung richtig und als Schlussfolgerung falsch. Stock zeigt
NV12 in Farbe, der HDMI-Eingang läuft ausschließlich über diesen Pfad, und
nirgendwo rechnet dabei eine CPU um. Die Hardware kann es - sie wird vom MIPS
gefahren, und der war in allen diesen Versuchen entweder mit der
HDMI-Capture beschäftigt oder, wie bei uns, abgeschaltet. „Einziger Weg" war
der Weg mit abgestelltem Motor.

### Der Test, der das entscheidet

`tools/uart-mips-live.py` setzt `bootcmd` auf `h713_disp init 0x30` statt
`auto 0x30 logo` - `init` lässt den MIPS **laufen** (siehe
[70-sackgassen.md](70-sackgassen.md)). Das Panel bleibt dabei schwarz, weil
dieser Pfad keinen Inhalt veröffentlicht; das ist erwartet und kein Befund.

Danach auf dem Gerät, alles vorbereitet unter `/root/video/`:

1. NV12-Frame nach DRAM (`ch0load load frame.nv12`)
2. pool-1 füllen: `0x05600070` = Y, `0x05600084` = C
3. Deskriptor setzen: `python3 videodec_poke.py poke`
4. beobachten, ob `0x05600320/324` auf unsere Adressen flippen

Flippt pool-2, ist der Pfad offen und die GPU-Konvertierung wird überflüssig -
dann ist `playbin` mit `kmssink` und `alsasink` ein ganz normaler Player, der
die A/V-Synchronisation selbst macht.


## Der MIPS-Lauf: die Kette feuert - und wo sie stehenbleibt

Durchgeführt in der Nacht 01.09. nach Marcos Hinweis, dass Stock NV12 in Farbe
zeigt und die HDMI-Eingabe ausschließlich über diesen Pfad läuft. Er hatte
recht: „CPU-Konvertierung ist der einzige Weg" ist keine Messung, sondern eine
Kapitulation vor einem abgeschalteten Coprozessor.

### Der Aufbau

`tools/uart-mips-live.py` setzt `bootcmd` auf `h713_disp init 0x30` statt
`auto 0x30 logo`. U-Boot bestätigt es selbst:

```
H713 disp: display initialised with the firmware running;
           scanrate, regscan and clkfind can run now. Power-cycle before another init.
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
H713 MIPS: application readiness proven
```

Kein `quiesced`. Der KMS-Treiber bindet trotzdem und nimmt ch1 mit dem
CMA-Puffer (`0x05600178 = 0x76D00000`), die Konsole ist also da.

### Was der Deskriptor-Poke jetzt auslöst

`videodec_poke.py poke` schreibt den 144-Byte-Deskriptor nach `0x4d95f000`
und den Zeiger nach `0x05600098`. **Mit laufendem MIPS reagiert die Hardware
von selbst** - das folgende hat kein ARM-Write verursacht:

```
0x05600010:  0x03000010 -> 0x03000013      bits[1:0] = memory_agent capture enable
0x05600310:  toggelt 0x00800210 <-> 0x00A00210    Bit 21 ("ch0 ready")
0x05600300:  wandert 0x00804218 <-> 0x0080C218 <-> 0x0080C258   (die Stock-Werte)
```

Mit geparktem MIPS blieb bei identischem Poke **alles** stehen. Damit ist
belegt, dass der Deskriptor der Auslöser und der MIPS der Ausführende ist -
genau wie im Gerätetest vom 13.06.2026.

Zweiter Beleg, dass der Pfad lebt: ch1 abzuschalten macht das Panel jetzt
**schwarz**. Mit geparktem MIPS blieb das letzte Bild eingefroren stehen.

### Der DE-Enable-Satz, bisher völlig unbeachtet

`memory_agent_onoff` schaltet laut `CURRENT-TRUTH.md` neben AFBD auch DE- und
TVTOP-Register. Zum ersten Mal ausgelesen (möglich erst seit
`clk_ignore_unused`):

| Maske | Register | Wert | Bit 31 |
|---|---|---|---|
| `0x020` | `0x05000178` / `0x050001B8` | `0xE002021C` / `0xE0020438` | **gesetzt** |
| `0x040` | `0x05000278` / `0x050002B8` | `0xE002021C` / `0xE0020438` | **gesetzt** |
| `0x080` | `0x050C06F8` / `0x050C0738` | `0x66020000` / `0x660200F0` | fehlt |
| `0x100` | `0x050C07B8` | `0x660200F0` | fehlt |
| `0x200` | `0x050C0478/04F8/0578/05F8/0678` | `0x6602…` | fehlt |
| `0x001/2/4` | TVTOP `0x068B00B8/DC/044C` | `0` | fehlt |

Maske `0x200` heißt in der Quelle ausdrücklich **„DE pool-2"** - die Gruppe,
die den NV12-Scanout speist. Alle acht `0x050C0…`-Register nehmen Bit 31 an
(`0x6602…` → `0xE602…`). Sicherung: `/root/video/de-save.txt`.

### Wo es stehenbleibt

Auch mit laufendem MIPS, gefeuerter Kette, gesetztem DE-Enable-Satz,
stock-konformer ch0-Konfiguration (`0x83001901`), abgeschaltetem ch1, gefülltem
pool-1 und einem NV12-Frame, der **exakt auf den Adressen liegt, auf die
pool-2 zeigt** (`0x4c7ed000` Y / `0x4cdea000` C):

```
ch0 READY (0x05600104) = 1     rastet nie ein
ch0 STATUS (0x05600128) = 0    nie DONE
Panel: schwarz
```

ch1 rastet bei jeder Änderung sauber ein (`READY` löscht sich, `STATUS = 2`),
ch0 bei keiner - obwohl beide Kanäle registerweise gleich konfiguriert werden
können. Der Frame-Trigger von ch0 kommt weiterhin von woanders.

### Was als nächstes drankommt

- **TVTOP `0x068B00B8/DC/044C` - NICHT aus Linux anfassen.** Die Masken
  `0x001/0x002/0x004` sind die einzigen des `memory_agent_onoff`-Satzes, die
  noch fehlen, aber `0x068B0000` ist ein anderer Block als der
  `tvtop@5700000` unseres Devicetree, er ist nicht getaktet, und **ein
  Lesezugriff darauf wedgt den SoC** (01.09. verifiziert, kostete einen
  Stromzyklus). Er liest sich vorher scheinbar harmlos als `0`, weil der
  erste Zugriff durchgeht und erst der zweite hängt. Der Zustand dieses
  Blocks muss über UART aus U-Boot geholt werden.
- **Der MIPS-elog** wäre das richtige Werkzeug, um zu sehen, wo die Firmware
  stehenbleibt. `mips_elog2.py` liest `0x4B28BD9C`, die Adresse ihres alten
  Builds; unsere `display.bin` (SHA `16c74a28…`) legt ihn woanders ab. Die
  Adresse ist aus dem Binary bestimmbar.
- `h713_disp regscan` / `scanrate` sind laut U-Boot-Meldung in diesem Zustand
  benutzbar und wurden noch nicht ausprobiert.


## Der Signalpfad im MIPS - vollständig aufgelöst

Eigener IDA-Lauf gegen `display.bin.i64`, plus Messungen am laufenden Gerät
mit `bootcmd = h713_disp init 0x30` (MIPS läuft).

### Der Mechanismus

`sub_8B1ABCA0` ist der WindowManager-Singleton-Getter:

```c
if ( MEMORY[0x8BAC4BD8] ) return MEMORY[0x8BAC4BD8];   // Instanzzeiger
```

Der Konstruktor `sub_8B1AB528` registriert **beide** Commit-Callbacks und
setzt die Quelle:

```c
*(_DWORD *)(a1 + 52) = 3;                    // Quelle = HDMI
*(_BYTE  *)(a1 + 64) = 1;
EventDispatcher, 8,  "WinMgrCallback0", sub_8B1ABC60   // VideoDec, HW-IRQ 19
EventDispatcher, 35, "WinMgrCallback1", sub_8B1ABC80   // HDMI, software-posted
```

Und die beiden Callbacks teilen sich die Arbeit über **ein einziges Flag**:

```c
sub_8B1ABC60:  if (  MEMORY[0x8BAC4BDC] ) return sub_8B1ABBD0();   // Event 8
sub_8B1ABC80:  if ( !MEMORY[0x8BAC4BDC] ) return sub_8B1ABBD0();   // Event 35
```

Steht das Flag auf 0, wartet die Kette auf Event 35 - den im mainline-Zustand
niemand postet. Steht es auf 1, erledigt es der Hardware-Interrupt, der pro
Frame von selbst feuert.

### Adressen, aus Linux erreichbar

MIPS-VA minus `0x40000000` ergibt die physische Adresse, und alles davon liegt
in `mips-firmware@4b100000`:

| MIPS-VA | phys | Inhalt |
|---|---|---|
| `0x8BAC4BD8` | `0x4BAC4BD8` | WindowManager-Instanzzeiger |
| `0x8BAC4BDC` | `0x4BAC4BDC` | Routing-Flag |
| `0x8BAC4BDD` | `0x4BAC4BDD` | pending-Byte |
| - | `0x4b89c4d4` | die Instanz selbst (bei diesem Lauf) |

### Was gemessen wurde

Ausgangszustand nach dem Boot:

```
+52 (Quelle)      = 1            bereits VideoDec, nicht 3
+56 (Signal-Mode) = 0x00020003   "kein Signal"
+64 (Bedingung)   = 0
Flag              = 0
```

**Der Deskriptor-Poke wirkt.** Nach `videodec_poke.py poke`:

```
+56: 0x00020003 -> 0x0002007C    = DTV_1920_1080_P, gültiges Signal
```

Der MIPS akzeptiert unseren selbstgebauten Deskriptor und meldet ein gültiges
1080p-Signal. Dazu schaltet er von sich aus `0x05600010` auf `0x03000013`
(memory_agent), lässt `0x310` Bit 21 toggeln und den Mux `0x300` durch die
Stock-Werte wandern.

**Die Kette arbeitet.** Nach `+64 = 1` und `Flag = 1` wird das
`pending`-Byte bei jedem Setzen **vom MIPS konsumiert** (`0x01` → `0x00`
innerhalb einer Sekunde). Die Firmware führt also `FlushPendingCommit`
tatsächlich aus.

### Wo es weiterhin stehenbleibt

Trotz allem: laufender MIPS, gültiges Signal, geroutetes Event 8, konsumierte
Commits, gesetzter DE-Enable-Satz, `capture-done` (`0x05600064` Bit 4) von
Hand gesetzt, ch0 stock-konform auf `0x83001901`, ch1 aus, fbcon abgehängt
(damit er ch1 nicht dauernd neu committet), NV12-Frame exakt auf den
pool-2-Adressen:

```
ch0 READY (0x05600104) = 0    kein Latch
ch0 STATUS (0x05600128) = 0   nie DONE
0x0560006c              = 0   AfbdConfigure committet nicht
pool-2                  unverändert
Panel: der letzte ch1-Commit
```

`StepWceSTM` läuft, aber die Kette erreicht `NRWinNode_AfbdConfigure` nicht -
und genau dort sitzt der abschließende `sw 0xBA60006C`, gated von
`WriteReg(a2 & 0x800)`.

### Nebenbefund

**fbcon ist eine Störquelle.** Der KMS-Treiber committet ch1 bei jeder
Bildschirmänderung neu und überschreibt dabei jede ch0-Konfiguration. Für
Versuche an ch0 gehört er abgehängt:

```bash
echo 0 > /sys/class/vtconsole/vtcon1/bind    # ab
echo 1 > /sys/class/vtconsole/vtcon1/bind    # wieder dran
```

### Der nächste Schritt

Nicht mehr die Register raten, sondern die Zustandsmaschine lesen:
`WindowManager__StepWceSTM` (`0x8b1a8f0c`), `WinMgr_FlushPendingCommit`
(`0x8b1abbd0`) und `WCETop__SetWindow` (`0x8b1a945c`) dekompilieren und
herausfinden, welche Zustände sie durchlaufen muss, damit `SetWindow` →
`NRWinNode_WriteReg` → `AfbdConfigure` überhaupt aufgerufen wird. Die
IDA-Datenbank liegt bereit, der Ablauf ist erprobt:

```bash
cp re/ida/weltneuheit/re_chain/display.bin.i64 /tmp/work.i64
/opt/ida-pro-9.1/idat -A -S<skript.py> -L<log> /tmp/work.i64
```
