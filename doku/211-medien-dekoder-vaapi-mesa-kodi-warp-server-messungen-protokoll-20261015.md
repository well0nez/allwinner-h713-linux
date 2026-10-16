# 211 - Das Nebenprojekt Medien: Dekoder, VA-API-Treiber, mesa, Kodi und der Wayland-Server im Warp; die Messungen am HY310 (13. bis 15.10.2026)

> *Überholt in Teilen (16.10.2026), neuer Stand in [`doku/212`](212-medien-launcher-einstellungen-desktop-kodi-nutzer-ve-600-va-endbau-protokoll-20261016.md):*
> *§3 "VE-Takt 432 MHz bestanden" - seit `0315` läuft die VE mit 600 MHz, solange der AV1-Knoten aus ist (212 §5);*
> *§8 "VE 28,8 Bilder/s", "4K nicht flüssig" - die Rate war großenteils der Neustart des 10-s-Testclips in der Schleife, nicht die VE (212 §5);*
> *§6 letzte Tabellenzeile "Box: die Pakete des Profils `media` 113,3 MiB" - das sind nur die 77 Pakete, die D auf eine schon bestückte Box legte; das Profil kostet im Baum +446 MiB (Host-`du`: 284,8 auf 730,9 MiB, davon `plugins-bad` +197,8 MiB);*
> *§7 "media +272 MiB, desktop +411 MiB, beide +478 MiB" - Stand vor `plugins-bad`; der Baum des Profils `media,desktop` ist mit Firefox, labwc und polkit 1152 MiB groß (212 §7).*

**Kurz:** Zusammenfassung aller Messungen des Nebenprojekts, das den HY310 zum Mediengerät macht (Hardware-Dekodierung, Kodi,
Desktop-Modi). Dieser Eintrag ist der Beleg, auf den `docs/` für diese Aussagen zeigt; die Rohlogs liegen im lokalen
Arbeitsordner des Nebenprojekts und sind nicht veröffentlicht, die Zahlen unten sind daraus übernommen. **Gemessen wurde nur am
HY310** (Kernel 6.18.38, Zweig `medien`); der HY300PRO-G-EU ist in keinem Punkt nachgemessen, jede Zeile hat dafür einen Eintrag in
`TODO.md`. Was nicht gemessen wurde, steht in §12.

## 1 Aufbau der Messungen

* Quelle am HDMI-Eingang: ThinkPad, 1080p60 (bewegtes Bild), Panel 59,42 Hz. Zeiten UTC, wo nicht anders vermerkt.
* Bit-Genauigkeit eines Dekoders heißt: `framemd5` jedes ausgegebenen Bildes gegen die Software-Referenz (ffmpeg, libdav1d für AV1). Für
  10 Bit gilt die obere-8-Bit-Hälfte der P010-Referenz, weil cedrus 10-Bit-HEVC als 8-Bit-NV12 plus 2-Bit-Ebene ausgibt.
* Gemessen wurde auf dem jeweils aktuellen Stand des Zweigs `medien`; die Patchnummern stehen an der Messung, `PROVENANCE.md` nennt die
  Herkunft. Die Box lief dabei mit dem Gate `h713_gate=0`, damit Stromzyklen und Resets von selbst durchbooten.

## 2 GPU-Takt (Patches `0268` bis `0270`, 13.10.)

| Messung | Ergebnis |
|---|---|
| Vorher: gemessener Takt gegen angezeigten (`drm-cycles-fragment` gegen `clk_get_rate`), vier Stufen 288/432/600/696 MHz | **0,500** an allen vier Stufen: der Ausgangsteiler 2 von `PLL_GPU` war gesetzt (`0xb8001c01`), die GPU lief mit der halben angezeigten Frequenz; Panfrost meldete beim Start `clock rate = 864000000` |
| Nachher: Stufen 150/200/300/600 MHz | gemessen gleich angezeigt (1,000) auf allen Stufen, `PLL_GPU = 0xb8001800` = 600 MHz auf allen vier |
| GPU-Zeit je Warp-Bild (Submit bis Fence) bei 600 MHz | Mittel **2,49 ms** (Median 2,46, Maximum 3,02); frei laufend 5,83 ms vorher, 4,73 ms nachher |
| Dauerlauf 44,5 min, Warp und bewegte Quelle | **59,42** Bilder/s (160 460 Bilder), 0 verspätet, 0 veraltet, GPU-Zone 51,7 bis 54,9 C (Grenze 85), CPU-Zone 49,7 bis 55,0 C; die GPU stand zu 20 % der Zeit auf 600 MHz, 47 % auf 300, 33 % auf 200 |

In den ersten 90 s des Dauerlaufs zählte der Warp 30 verworfene Bilder; sie ließen sich nicht wiederholen (vier passive Gegenläufe nach
Neustart ohne eine Lücke über 25 ms), die Ursache ist nicht geklärt. Die Wärme bei **dauerhaft** 600 MHz maß ein eigener Test (45 min
Vollast auf der GPU, Takt durchgehend 600 MHz, Warp mit 1080p-RGB-Quelle): GPU-Zone nach 5 min 66 C, Plateau 65,7 bis 66,9 C,
**Maximum 67,1 C**, CPU-Zone 63,9 C, Lüfter 4500 bis 4590 U/min, kein Trip (passiv ab 85 C). Im Dauerlauf oben stand die GPU nur zu
einem Fünftel der Zeit auf 600 MHz.

## 3 Dekoder cedrus, VP9, IOMMU an (Patches `0271` bis `0298`, 13.10.)

| Prüfung | Ergebnis |
|---|---|
| Bit-Genauigkeit | H.264, HEVC 8 und 10 Bit, VP8, VP9: **33 Clips bis 4K, jedes Bild bitgenau**; MPEG-2 ist identisch zur Hardware-Ausgabe des alten Kernels, aber nicht zu ffmpeg (IDCT-Rundung) |
| IOMMU-Faults | 0 IOMMU-Faults im Normalbetrieb |
| Dauerlauf | 264 von 264 Durchläufen exakt in 8 Runden, 127 min |
| Dauerlauf mit Anzeige | 2160,1 s, 128 369 Bilder, **59,428 Bilder/s**, 5 verworfene, Bild in Ordnung |
| Zwei Codecs gleichzeitig | zwei Codecs gleichzeitig: H.265 neben VP9 scheiterte an jedem Job, bis `0298` die VE beim Codecwechsel zurücksetzt; mit `0298` bestanden |
| VE-Takt | VE-Takt 432 MHz (`0293`) bestanden |

Die IOMMU ist an (`CONFIG_SUN50I_IOMMU=y`): die VE-Master 0 und 1 laufen übersetzt, die Anzeige (Master 2 bis 6) physisch.

## 4 Der gelatchte IOMMU-Fault nach einem beschädigten H.265-Strom (Patches `0308`, `0309`, 13./14.10.)

* **Fehler:** ein beschädigter 10-Bit-HEVC-Clip löste einen IOMMU-Fault aus; danach lief **jeder** Job **jedes** Codecs in den Watchdog,
  bis die Box neu startete. Ein VE-Reset, ein Stromzyklus der VE-Domäne und ein Neuladen des Moduls halfen nicht. Ein Lauf ohne IOMMU
  (Kontrollarm) starb am selben Clip genauso, der Fehler lag also nicht im Übersetzen.
* **Ursache:** die tote VE hielt ein gesperrter IOMMU-Master-Port, den der Fault-Handler nach seinem Reset nicht mehr freigab, solange die
  Engine weiterlas. Der Hersteller-Kernel (disassembliert, nur das Verhalten am Register beschrieben) quittiert den Fault anders.
* **Fix:** `0308` gibt die Ports frei, nachdem die Engine gestoppt hat, im gehaltenen Bus-Reset; `0309` lehnt einen H.265-Job ab, dessen
  Referenz nicht in der DPB steht (die Engine las sonst Adresse 0 und hing).
* **Gemessen (ohne AV1):** sechs Sätze beschädigter Clips (H.265 8 und 10 Bit, VP9, VP8, MPEG-2, H.264), je 10 Clips mit einer Probe nach
  jedem Clip: **60 von 60 Proben bitgenau, 0 Hänger, 0 Timeouts**. Regression danach: HEVC-Satz 11 von 12 Clips (`hevc8-2160p` direkt nach
  den Fehlersätzen 0/300: Lesefault Master 0, danach Timeout), Paarsatz 19 von 20 Strömen (VP9 598/600, ein Timeout ohne Fault). Dasselbe Muster
  an derselben Stelle der Reihenfolge trat in zwei unabhängigen Läufen auf, ist aber in Einzelversuchen nicht auslösbar (Übergang allein 3
  von 3, Abbruch nach dem ersten Bild 40 von 40, Paar allein 3 von 3 sauber). Die Ursache ist nicht gemessen. Ein Timeout kostet in Kodi
  ein Bild und eine Pause von 2 s.

## 5 AV1 und die geteilte Reset-Leitung (Patches `0300` bis `0307`, `0310`, 13./14.10.)

* **Der AV1-Kern** (Hantro-Treiber auf dem Kern bei `0x01c0d000`) dekodierte 8-Bit-AV1 bitgenau gegen libdav1d: sechs Größen bis 4K, ein
  Auflösungswechsel, 40 Seeks, beschädigte Ströme, eine Stunde Dauerlauf neben HDMI-Erfassung und Warp (Kern-ID `0x0003b16d`).
* **Das Problem:** `RST_BUS_VE` gehört cedrus (Puls bei jedem Codecwechsel durch `0298`, außerdem im Watchdog-Pfad), der AV1-Kern braucht
  dieselbe Leitung frei. Ein Puls in ein laufendes AV1-Bild ließ den Kern und dann den SoC stehen (zwei Watchdog-Resets in den Läufen);
  der Stock-Treiber hat dieselbe Lücke, ein engine-eigener Reset existiert nicht (nur `RST_BUS_VE`, `RST_BUS_AV1`, `RST_BUS_VE3` in der CCU).
* **Der Wächter** `0305` bis `0307` (cedrus pulst nur durch ihn, die AV1-Variante hält die Leitung je Bild): die Läufe b, c und d des
  AV1-neben-anderem-Codec-Tests bestanden. Ein Rest bleibt: die Freigabe des IOMMU-Ports neben laufendem AV1 kostet Bilder oder hält
  den SoC an, in keiner der probierten Varianten ging es gut (fünf SoC-Hänger dabei); `0308` gibt den Port deshalb nur frei, solange kein
  AV1-Strom offen ist.
* **Stand:** Marco entschied am 14.10. ("AV1 ist mir völlig egal, zumindest für jetzt"), den AV1-Dekoder abzuschalten: `0310` setzt den
  Knoten auf `disabled`, der Defconfig baut `hantro_vpu` nicht. Der Code `0300` bis `0307` bleibt in der Serie. Wiederaufnahme:
  `TODO.md` 9.3b.

## 6 Der VA-API-Treiber (`rootfs/libva`, 13. bis 15.10.)

| Prüfung | Ergebnis |
|---|---|
| ffmpeg `-hwaccel vaapi` mit dem Plan-Befehl | **45 von 45 Clips bitgenau**: H.264 8, HEVC 8 6, MPEG-2 4, VP8 4, VP9 5, HEVC 10 Bit 6 (vorher 0 von 6), AV1 8 und 10 Bit je 6; Interrupts gleich Bilder, 0 Treiberzeilen. Die AV1-Zeilen gelten für den Stand vor `0310` |
| GStreamer `va*dec` nach `glimagesink` | H.264 und HEVC 8: 0 Drops bei 30 fps, bei 60 fps 59,3 im Mittel; `vaav1dec` zeigte vor `0010` grün/leer |
| GStreamer `v4l2sl*dec` | H.264 1080p60 nur 48,3 Bilder/s mit 27 Drops (der Dekoder allein 114); HEVC 1080p hängt (Pool leer: die Kopie des 1088 hohen Bildes); beides nicht gepatcht, die Player nehmen den VA-Weg |
| Dekodier-Skalierer | der Treiber skaliert 4K auf 1920x1080 mit PSNR Y/U/V 54,2/48,4/44,0 dB (H.264) und 54,4/48,4/44,1 dB (HEVC 8) über 59 Bilder |
| `0010`, `0011` | AV1 8 Bit über DMA-BUF: 300/300, 300/300, 600/600 (vorher 0); HEVC Main10 meldet NV12, wenn der Dekoder 8 Bit schreibt |
| Dekoder liefert Panelgröße | als Standard **nicht tragfähig**: mpv, Kodi und GStreamer nehmen die Größe für den GL-Import aus dem Strom, nicht aus dem Deskriptor; ein 3840 breiter Import eines 1920er Puffers scheitert in Panfrost (`EGL_BAD_ALLOC` je Bild, Wand schwarz). `0012` (`V4L2_REQUEST_SCALE=panel`, nur auf Anforderung) ist gebaut und **am Gerät nicht gelaufen**; `0013` weist `vaDeriveImage` auf einer verkleinerten Fläche ab |
| mpv 4K ohne Skalierer | HEVC 2160p: 29,97 Bilder/s, 0 verworfen, GPU 43,2 % = 14,4 ms je Bild; H.264 2160p: der VE schafft 26,9 Bilder/s, mpv verwirft 238 in 15 s |
| `0014` HEVC Main10 in Kodi | vorher exportierte der Treiber die 10-Bit-Fläche nicht (Status 1), Kodi schrieb `deepColor no` und dekodierte in Software (351 % eines Kerns); nachher Export Status 0 mit `R8` + `GR88`, Kodi spielt über VA |
| Größe | Box: die Pakete des Profils `media` 113,3 MiB; 561 Pakete, 816,9 MiB installiert |

Ton (14.10., mit Marco im Raum, Urteil nach Gehör): alle sechs Wege gehört (`default` und `bridge` über die DSP-Brücke, Codec direkt mit
`DAC Source` = APB, mit h713-tv gestoppt). PipeWire: bestanden mit der Auflage, die DSP-Brücke zur Standardsenke zu machen (WirePlumber
nahm den Codec, der bei `DAC Source` = I2S stumm ist); 30 s Dauerton ohne Fehler (`pw-top` ERR 0). Bild und Ton gleichzeitig: nach Augenmaß
synchron, **die Grenze 40 ms ist nicht gemessen**.

## 7 mesa (Wayland, glvnd, fünf Attrappen)

* `apt-get install --dry-run cage labwc kodi seatd` gegen den Stand des Grundabbilds: 254 Pakete, **kein `libllvm*`**, kein
  Debian-mesa; ohne die Attrappen 361 Pakete mit allen sechs. Die Dispatcher: `libEGL.so.1` und `libGLESv2.so.2` sind die glvnd-Dispatcher,
  `libgbm.so.1` und die ICD `libEGL_mesa.so.0` kommen aus `/usr/local/lib`.
* Auf dem HY310: `seatd` und `cage -- glmark2-es2-wayland`: Renderer `Mali-G31 (Panfrost)`, OpenGL ES 3.1 Mesa 25.0.7, 1920x1080,
  **Score 76** (33 Szenen), Bild an der Wand.
* Größe: mesa-Tar 14 MB (installiert 8 bis 12 MiB gegen 187 MiB bei Debians mesa mit LLVM). Das Grundabbild wächst um 1,57 MiB
  (Ziel unter 1 MiB verfehlt: `libGLdispatch` allein 1,5 MiB); das Profil `media` kostet 272 MiB, `desktop` 411 MiB, beide 478 MiB.
* Der unveränderte Warp läuft auf dem neuen mesa wie vorher (4,78 und 2,43 ms gegen 4,85 und 2,49 ms).

## 8 Kodi unter cage (Profil `desktop`, 14./15.10.)

| Prüfung | Ergebnis |
|---|---|
| VA unter cage | `Player.Process(videodecoder)` = `ff-h264-vaapi` / `vaapi`, 29,3 VE-Interrupts/s bei 30 fps, `LIBVA_*` und `KODI_AE_SINK=ALSA` kommen in `environ` an, 0 Treiberzeilen |
| 1080p60, 60 s | H.264: **58,2** Bilder/s, GPU 11,2 ms je Bild (Kodi 6,2 + cage 5,1), 66 % GPU, MemAvailable min 483 MiB, 0 verworfen; HEVC 8: 57,8 Bilder/s, 11,5 ms |
| Codecs, je 10 min 1080p30 | H.264, HEVC 8, VP9 und MPEG-2 (VA an) über den VE: **0 verworfen, 0 Treiberereignisse**. HEVC 10 Bit lief in Software (`ff-hevc`, 351,5 % eines Kerns, 24 verworfen) - behoben durch `0014` (§6) |
| 4K HEVC 8 Bit | 55,0 Bilder/s Kodi, **VE 28,8 Bilder/s** (28,4 bis 28,5 in einer späteren Reihe), GPU 91,6 % = 16,7 ms je Bild, MemAvailable min 240 MiB (später 210); 0 verworfen, 0 Treiberereignisse. Marco: "4K nicht flüssig" |
| Verlassen | fünf Mal Kodi und cage beenden, h713-tv und h713-warp zurück |
| Leerlauf | Kodi 15 bis 17 % eines Kerns bei 480 bis 546 MHz plus cage 2,4 %; davon 6,4 % die CEC-Suche (`PeripBusCEC` fragt alle 5 s jeden der 587 tty-Einträge ab). Der Kernel ohne `CONFIG_LEGACY_PTYS` (587 auf 75 Einträge) senkt sie auf 1,2 % und Kodi insgesamt auf 10,0 %; das Ziel unter 5 % ist nicht erreicht (Kodis Hauptthread 8,1 %, cage 2,4 %) |

## 9 Der eMMC-Hänger unter 4K-Last (Patches `0312`, `0313`, 15.10.)

* **Fehler:** beim Abspielen von 4K unter Kodi brach ein Lesen der eMMC mit `data error cmd18` ab, danach lief nichts mehr von der Platte
  (ssh nahm keine Verbindung mehr an), bis ein Stromzyklus kam. Mehrfach beobachtet, einmal ohne gleichzeitiges Schreiben.
* **Wurzel (gemessen):** der eMMC-Host (HS200/HS400) hielt bei voller FIFO den Kartentakt mitten im Block an, wenn die DMA unter der
  Speicherlast zurückfiel. `0313` startet einen Lese-Block erst, wenn die FIFO Platz hat (Lese-Schwelle 512 Byte); `0312` ist das Netz
  (der Controller wird vor dem Stop-Befehl neu initialisiert).
* **Gemessen:** neun Kodi-4K-Läufe bei gleicher Last: **0 Daten-CRC-Fehler auf 30 946 MiB** gegen 1899 auf 19 049 MiB ohne die Schwelle;
  der Anteil "FIFO voll" fiel von 2,89 % auf 0,001 bis 0,002 %. Nebenwirkungen: Kurzprobe auf Bit-Genauigkeit H.264 und HEVC 8 je 300/300 bitgenau,
  Schreibtest 128 MiB gleiche Prüfsumme, `dd` neben Kodi 133 bis 137 MB/s (vorher 45 bis 128). Auf der Linie: 34 680 MiB Kodi-4K-Last mit
  0 `data error`, 0 Neuinitialisierungen, 0 I/O-Fehlern.

## 10 Kodi als Client des Warp (`h713-warp` als Wayland-Server, 15.10.)

* **Am HY310:** cage (`WLR_BACKENDS=wayland,libinput`) bindet den Server; `wayland-info`: `wl_shm 2`, `wl_compositor 6`, `xdg_wm_base 5`,
  `wl_output 4` (1920x1080 bei 59,420 Hz), `wp_presentation 2` (Uhr `CLOCK_MONOTONIC`), `zwp_linux_dmabuf_v1 4` mit 70 Formaten, darunter
  `AR30` mit AFBC. Die Startseite von Kodi steht gewarpt (Trapez) an der Wand.
* **cage reicht durch:** Menü 20 s: cage 0 ns GPU-Zeit, 57,05 Bilder/s; Video H.264 1080p60 über VA: cage 0 ns, Kodi 6,24 ms, Warp 4,46 ms,
  **58,23 Bilder/s**, VE 58,06/s, GPU 62,3 %, 0 Treiberzeilen.
* Einblendungen (`h713-osd`) liegen vorverzerrt über Kodi; die Lautstärketasten erreichen Kodi als `noop` (`h713-keys` setzt die Lautstärke
  90 auf 95 auf 90, Kodi bleibt 100); Pfeiltasten über eine uhid-Fernbedienung kommen als `Up`/`Down` an; die Konsole ist nach dem Ende
  von cage wieder im Textmodus; der Rückweg zur HDMI-Seite dauert +2,3 s (Ring) bzw. +3,6 s (gewarpt).
* HDMI-Betrieb unverändert: `h713-warp ctl check 900` 898 und 900 Bilder, **0 abweichende Zeilen**.
* **Dauerlauf:** 2670 s Video unter Kodi am Warp: 59,321 Bilder/s gezeigt, 289 Verluste (234 an den 22 Schleifennähten des Clips, 38
  durch Screenshots, 17 übrige = 0,006 je s), GPU-Zone **59,2 bis 64,4 C** bei 600 MHz fest, CPU-Zone 57,7 bis 60,9 C, MemAvailable min 396 MiB. Saubere Stopps ohne Leck; ein `SIGKILL` auf die ganze
  Einheit überspringt `ExecStopPost` (7 von 7), darum setzt die Kodi-Einheit `source auto` statt eines Rückwegs beim Beenden.
* **Störfälle:** rund 30 Läufe eines Störclients gegen den Server: dieselbe Server-PID über alle Läufe, zwei GPU-Resets durch einen
  AFBC-Größenfehler des Clients (12:01 UTC), sonst nichts; danach Ring-Check 300 gleich 0.

## 11 Standby und der Index der Erfassung (Patch `0314`, 15.10.)

Nach manchen Standbys lieferte die Erfassung dem Warp keine Bilder mehr, bis zum Warmstart: das Schreibindex-Wort (`INCAP +0xa0c`) hatte
Bits oberhalb von [2:0] gesetzt, und `0255` verglich das ganze Wort mit "kleiner als 3", die Firmware maskiert mit `andi 0x7`. `0314` liest
das Feld [2:0]. **25 Standbys per RTC-Wecker**: in allen 25 kamen Bilder (297 bis 299 in 5 s); die oberen Bits waren nach 9 der 25 gesetzt, in
allen 9 lief der Warp mit 59,40 Bildern/s wie im sauberen Zustand, `ctl check 900` ohne eine abweichende Zeile.

## 12 Nicht gemessen

* Alles am HY300PRO-G-EU (§2, §4, §8, §9, §11).
* Ton im Client-Fall: ob der HDMI-Ton bei einem Wayland-Client stumm bleibt, ist nicht gemessen (die HDMI-Quelle der Läufe sendete keinen Ton).
* Echte Infrarot- und Bluetooth-Eingabe an Kodi unter cage (die Läufe nutzten eine uhid-Tastatur).
* Ton-Synchronität unter 40 ms; Bildinhalt und Latenz im gesetzten Zustand von §11; ein Dauerlauf der VE-Stabilität über mehrere Stunden.
* `V4L2_REQUEST_SCALE=panel` (`0012`) am Gerät; 4K mit dem Dekodier-Skalierer.
* Die Ursache der 30 Drops von §2 und die der Regression von §4; dass die VE neben laufendem AV1 den SoC anhält, ist gemessen, die Ursache nicht.
