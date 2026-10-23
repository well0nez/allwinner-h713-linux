# 128 - Abgleich mit cstengers Zweig `h713-display-video-path`, zweiter Durchgang (sein Stand 16.09.2026)

Angelegt 17.09.2026, nachmittags. Anlass: Marcos Frage, ob cstengers Arbeit an H.265, Decoder, GPU "etc." inzwischen
weit genug ist, dass wir etwas übernehmen oder portieren sollten. Fortsetzung von [`124`](124-cstenger-abgleich-20260915.md)
(sein Stand 12.09., Spitze `b54adaf`); dort steht alles bis zum 12.09., hier nur, was seitdem dazukam, und die Antwort.

**Grundlage.** Frischer Klon des Zweigs, Spitze `a861df2` ("Share H713 decoder scaler and fix Cedrus control
compliance", 16.09. 23:59 PDT = 17.09. 08:59 MESZ). `main` steht weiter bei `8860991` = unser Subtree. Der Zweig
hat 374 Commits über `main`, davon **32 seit `b54adaf`** (15./16.09.); 73 Dateien, +10.174/-1.121 Zeilen, davon
Patches +3.541, Doku und Messmitschnitte ~4.500, Werkzeuge ~1.700. U-Boot-Fork, TF-A, sunxi-tools, aic8800 und
Defconfig unverändert seit 12.09. Alles unten habe ich selbst geprüft, nicht aus seinen Handoffs abgeschrieben:
Byteidentität, Anwendbarkeit auf unsere Serie, Übersetzbarkeit, Gating. Ablage der Prüfung: Scratchpad der Sitzung
(`cstenger/`, `k/` = 6.18.38 + unsere 142 Patches, `k-cedrus/` = dasselbe + seine 19 sauberen Patches).

---

## 1 Kurzfassung

1. **Seit dem 12.09. hat er ausschließlich am Decoder gearbeitet.** Kein GPU-, kein Mali-, kein Panfrost-Commit
   (`git log b54adaf..HEAD | grep -i gpu|mali|panfrost`: leer), kein AV1 (im ganzen Zweig kein Treffer), kein U-Boot.
   "GPU" bleibt bei uns, was es war: Panfrost-Patch `0053` in der Serie, im Abbild ungetestet.
2. **Der Decoder-Teil ist jetzt reif genug, um ihn zu übernehmen - als Patches, byteidentisch, ohne Portierung.**
   17 Cedrus-Patches (`0099`-`0121`) plus 2 decd-Patches (`0095`/`0096`) wenden sich **ohne einen einzigen Reject**
   auf 6.18.38 + unsere 142er-Serie an (§3) und übersetzen mit `clang -W1` **ohne eine Warnung** (§3). Sein Stand:
   `v4l2-compliance` 49/49 ohne Warnung, 53 Pixelmessungen, sieben H.265- und fünf H.264-Vektoren, Main10, zwei
   parallele Kontexte - auf seinem Board, aber die VE ist dasselbe Silizium wie bei uns, und der neue Datenpfad ist
   per `of_machine_is_compatible("allwinner,sun50i-h713")` gegattert, also auf HY200, HY310 und HY300 Pro gleich
   (Regel "eine Software für beide Boards", doku/127).
3. **Was er *nicht* hat, und wir deshalb auch nicht bekommen:** einen Player. Seine Validierung ist headless
   (Decoder -> Puffer -> PSNR gegen Software-Skalierung). libva-Shim, mpv und GStreamer verhandeln die skalierten
   Flächen noch nicht (GStreamer-Patches "NOT yet on the board"); "Datei abspielen" auf dem Panel gibt es bei ihm
   nur unskaliert über seinen DECD-Weg vom 08.09., der mit unserem Anzeigedesign kollidiert (124 §3.2). Für uns
   ändert das an der Entscheidung vom 15.09. (124 §8: Dekodieren und Abspielen ist ein späteres Ziel, Paket 3 der
   Einstieg) nichts - es macht Paket 3 nur billiger, weil die Kernelseite fertig wäre.
4. **Die sieben Display-Patches (`0080`, `0098`, `0103`, `0105`, `0106`, `0108`, `0111`) bleiben draußen**, wie in
   124 begründet: alle sieben scheitern gegen unseren `sun50i-h713-afbd.c` (elf eigene Patches an der Datei), unser
   Panel ist 1080p (seine ganze Route ist "1080p auf 720p"), und die Skalierung macht bei uns die Firmware über den
   VidDec-Deskriptor. Übernehmbar ist nur Registerwissen, und davon bestätigt eins unsere eigene Formel (§4).
5. **Ein Haken im neuen API, den man kennen muss, bevor je ein Player darauf gebaut wird** (§5): `S_FMT` auf der
   CAPTURE-Queue skaliert jetzt *jede* Größe zwischen 1x und 4x, auch 1920x1080 auf einem 1920x1088-Strom - Mainline-
   cedrus gäbe 1088 zurück und überließe den Beschnitt der Selection-API. Er weiß es ("the known trap") und hat es als
   nächsten Punkt notiert; gelöst ist es nicht.
6. **Empfehlung** (§6): die 19 Patches als eigenen Serienabschnitt übernehmen, zusammen mit seinen vier Prüfwerkzeugen
   und einem Gerätetest, der ohne Video-Laufzeit auskommt (`v4l2-compliance` + seine zwei C-Tests). Ein halber Tag
   plus ein Einspielen. Kein Zwang: solange nichts auf unserem Abbild `/dev/video0` zum Dekodieren öffnet, ist die
   Änderung schlafend - bis auf `0112`, das ein echter Sicherheitsfix ist (§2).

---

## 2 Was seit dem 12.09. dazukam

| Commits | Thema | Ergebnis | Belegt |
|---|---|---|---|
| `2952b81`-`699013c` (15.09.) | Proc-Scaler auf seinem Panel | der graue Streifen war `proc+0x50[15:0]` = Zeilenfenster **max(in_h, out_h)**, nicht `in_h`; skaliert 960x544 und gedreht 90/180 sauber, 59,71 fps, sd 0,02 ms | HW, Panel |
| `5981130` (15.09.) | GStreamer | zwei Patches (`v4l2codecs`: Compose-Größe, H.264-Transformationen) - **"NOT yet on the board"** | Bau |
| `ad2bc4b`, `a779bc3` (15.09.) | `v4l2-compliance` | Baseline "48/49" war aufgebläht: `testRequests` braucht ein INTEGER/BOOLEAN-Control, cedrus hatte keins, die Suite lief nie. Sein `V4L2_CID_ROTATE` (`0110`) war das erste, und dann fielen zwei *alte* cedrus-Defekte auf | HW |
| `d5a4d98` (15.09.) | Backports | `0112` DPB-Index aus Userspace ungeprüft (16..255 lesen hinter dem Array, KASAN-UAF, Chen-Yu Tsai; linux-media v2, Acked-by Jernej Skrabec) und `0113` `v4l2_fh_exit()` im Fehlerpfad (Andrey Skvortsov, Acked-by Paul Kocialkowski). "Carry until it lands upstream" | HW, bitidentisch vorher/nachher |
| `21fc7af` (15.09.) | `0114` | `cedrus_request_validate()` prüfte nie, ob die Per-Frame-Controls im Request sind; jetzt `-ENOENT` wie die Stateless-uAPI es vorschreibt. SPS/PPS bewusst *nicht* Pflicht (libva wiederholt sie, GStreamer setzt HEVC-SPS einmal) | HW, 46 -> 48/49 |
| `794f330`, `fe65505` (16.09.) | Aufräumen | EXPERIMENT-Patches `0097`/`0100`/`0109` aus der Serie gelöscht; **keine EXPERIMENT-Patches mehr in seiner Serie** | Serie |
| `cb367a5`-`df0decd` (16.09.) | H.265-RE | die Vendor-*Quelle* für H.265 (`gh search`, libcedarc) statt Blob-RE; `reg50` Bits 12/13 = Interlace, kein Rotate-Feld in Hardware (`~0` liest `0x3f00`, `0117`) | RE + HW |
| `3ec8006`, `b3e22bb`, `3dc07a8` (16.09.) | **H.265-Scaler** | der zweite Ausgang skaliert nicht über den Shifter (der hängt die Engine), sondern über einen **4-Tap/32-Phasen-Polyphasen-Scaler bei `VE+0xf00`** ("Group 7"), beliebige Verhältnisse; Koeffizienten selbst erzeugt (`gen-scaler-coef.py`), nicht aus dem Blob. 1280x720 -> 640x360: 55,45 dB Luma (H.264-Shifter: 46,10 dB) | HW, 7/7 Vektoren |
| `10ea6a6`, `bb66f3b` (16.09.) | 10 Bit | Rekonstruktionspuffer um die 2-Bit-Ebene vergrößert (`0115`), Offsets aus der Rekonstruktion (`0116`); Main10 skaliert 53,6 dB | HW |
| `179a6b5` (16.09.) | `ENUM_FRAMESIZES` | implementiert (`0119`); vorher war der Scaler unauffindbar, `v4l2-compliance` meldete "Scaling: Not Supported" | HW |
| `a861df2` (17.09. MESZ) | **H.264 auf denselben Scaler** (`0120`) | `H264ConfigNewScaler` aus `libawh264.so` (Thumb `0xdb71`): `H264_CTRL` Bit 9 (SDROT) *löschen*, Bit 11 setzen, `VE_CHROMA_BUF_LEN` Bit 29 - damit läuft H.264 durch denselben `VE+0xf00`-Block; SDROT-Shifter und `V4L2_CID_ROTATE` wieder entfernt ("by user decision"). 2x: 55,33 dB (Shifter 46,42). Dazu `0116a` (fehlende H.265-Voraussetzungen, ohne die die Serie ab `0117` nicht anwendbar war) und `0121` (HEVC-SPS-Default 4:2:0, `TRY_EXT_CTRLS` ohne Nebenwirkungen) - **49/49, null Warnungen** | HW, 53 Messungen |

Zurückgenommen von ihm selbst seit 124: "der beliebige VE-Scaler hat keinen Datenpfad" (124 §3.1, "VE+0xf00 inert") - falsch,
der Block war nur nie mit Geometrie gefüttert; "die VE skaliert nur um Zweierpotenzen" - falsch; "Rotation über SDROT
behalten" - aufgegeben. Seine `status.md` markiert die 12.09.-Erzählung als "Superseded".

**HEVC-Alignment-Fund** (neu, gilt für jeden, der den zweiten Ausgang benutzt): Sekundär-Chroma korrupt, wenn seine Basis
32 mod 64 ist (258x242, Pitch 272: U/V 9,2/5,3 dB; Pitch 288 oder Höhe 244: sauber). Auch bei 8 Bit. Regel: Pitch auf
32 Byte, Canvas-Höhe gerade => Chroma-Basis 64-Byte-ausgerichtet.

**4:2:2** (`chroma-422-assessment-2026-09-17.md`): Vendor-HEVC lehnt `chroma_format_idc != 1` im SPS-Parser ab
(`libawh265.so` `0x11f98`), Vendor-H.264 programmiert *immer* 4:2:0 ins Register (`0xe47c`, `bfi ... #19, #3`). Bleibt
unsupported; er sagt selbst, das ist kein Siliziumbeweis.

---

## 3 Prüfung: Byteidentität, Anwendbarkeit, Übersetzung

**Byteidentität unserer 17 Zweig-Patches** (`0051`…`0086`): alle noch byteidentisch mit seiner Spitze (`cmp` gegen jede
Datei seiner `series`). Abweichungen nur bei `0013`, `0014`, `0024` - das sind die Basis-Patches, die er am 28.-31.08. in
place geändert hat; unser `0013`+`0013a` ergibt denselben decd-Quelltext wie sein `0013` (`diff -r`: identisch), und
`0014`/`0024` sind bei uns seit 124 §3.3 bewusst weiter (In-Kernel-API, Slot-Rückgabe, drei Msgbox-Leitungen).

**Anwendbarkeitsprobe.** 6.18.38-Tarball (`mainline/build/cache/`) + unsere 142 Patches in Serienreihenfolge (`patch -p1`;
`0001` und `0067` brauchen Fuzz 1 - das ist alt und liegt am Tarball, nicht an uns), dann seine 26 fehlenden Patches
in *seiner* Serienreihenfolge:

| Gruppe | Patches | Ergebnis |
|---|---|---|
| **Cedrus** (17) | `0099`, `0101`, `0102`, `0104`, `0107`, `0110`, `0112`, `0113`, `0114`, `0115`, `0116`, `0116a`, `0117`, `0118`, `0119`, `0120`, `0121` | **alle sauber** (`0118` Fuzz 1 in einem Hunk, kein Offset-Problem); +1.315/-460 Patchzeilen, netto +813/-76 in zehn Dateien plus die neue `cedrus_scaler_coef.h` (194 Zeilen). Wir tragen selbst keinen einzigen Cedrus-Patch außer seinen, deshalb kein Konflikt |
| **decd** (2) | `0095` (Quellroute aus dem Deskriptor), `0096` (dma_buf-Leck begrenzt) | **sauber**; +262/-1. `dec@5600000` ist bei uns `status = "disabled"` (`0038`), das Modul bindet nicht - schlafend |
| **afbd / IOMMU / DTS** (7) | `0080`, `0098`, `0103`, `0105`, `0106`, `0108`, `0111` | **alle scheitern** (Rejects in `sun50i-h713-afbd.c` und `sun50i-h713.dtsi`; `0108` "gelingt" nur mit Fuzz 2, weil seine Hunks ohne `0098` sinnlos einhängen). Erwartet: unsere `0093`/`0095`/`0104`/`0107`/`0117`/`0120`/`0131`/`0133`/`0078a` besitzen genau diese `atomic_check`/`atomic_update`-Pfade |

**Übersetzungsprobe** (Host-clang 18.1.3, `ARCH=arm64 LLVM=1`, unser `hy200_qz713df_a1_defconfig`, `modules_prepare`, dann
`M=drivers/staging/media/sunxi/cedrus` und `M=drivers/misc/sunxi_decd` mit `W=1`): **beide Module übersetzen ohne eine
Compiler-Warnung** (`sunxi-cedrus.ko` 117 KiB, `sunxi-decd.ko` 76 KiB; die modpost-Meldungen sind nur das fehlende
`Module.symvers` eines Teilbaus). Sein Bau ist LLVM 20; unser Container hat 20, der Host 18 - reichte.

**Gating.** `0120`: `if (of_machine_is_compatible("allwinner,sun50i-h713")) capabilities |= POLYPHASE` - unser HY310-DTS
(`0160`) hat `compatible = "magcubic,hy310", "allwinner,sun50i-h713"`, der VE-Knoten ist `sun50i-h6-video-engine` mit
`iommus = <&iommu 0 1>, <&iommu 1 1>` und `status = "okay"` - also **lädt cedrus auf unserem Abbild**, und der neue Pfad
wäre aktiv, sobald ein Client H.264/HEVC öffnet. Der Line-Buffer des Scalers ist 64 KiB je streamendem Kontext
(`dma_alloc_attrs`, nur bei `cedrus_can_scale()`), vernachlässigbar.

**Was von seinen Zahlen für uns gilt.** Die VE, ihre Register, der `VE+0xf00`-Block und die IOMMU-Masterports sind SoC-intern
und auf HY200/HY310/HY300 Pro identisch; sein Board unterscheidet sich in DRAM, Panel und Projekt-ID (0x34 vs. 0x30), nichts
davon berührt Cedrus. Seine 49/49 und 53 Messungen sind deshalb eine starke Vorhersage, aber nach unserer Regel
("Works = am Beamer verifiziert") kein Nachweis. Der Nachweis kostet einen Einspielvorgang (§6).

---

## 4 Registerwissen aus den Display-Patches (nicht als Patch, als Notiz)

| Befund (sein Patch) | bei uns |
|---|---|
| `proc+0x50` `FRAME_LINES`: `[31:16]` Startzeile, `[15:0]` Länge = **max(in_h, out_h)**, aus `ProcWinNode::CalcWindow` `0x8b1a6470` (`slt`/`movz`); `proc+0x40` `OUT_W_DUP` trägt in Bit 31 das V-Enable (`0103`) | neu; beantwortet, was bei ihm der graue Streifen war. Bei uns programmiert die Firmware das selbst (`0117`/`0120`), aber für jede eigene Proc-Programmierung (doku/93) ist es die fehlende Zeile |
| Integer-Phasenfelder `0x05180008[30:28]`/`[26:24]`: **3 und 2 beim Vergrößern, 4 und 3 bei Einheit** (`0108`) | **bestätigt 124 §5.1 Punkt 1 Zahl für Zahl** - genau das hatten wir ihm als Vorhersage aus `sub_8B1A56B8` aufgeschrieben (`mode_h = 3`, `mode_v = 2`), er hat es unabhängig aus `CalcWindow` gezogen und am Panel bestätigt. Unsere Formel aus doku/93 ist damit zweifach belegt |
| Vor dem Proc-Scaler programmiert `ProcWinNode::WriteReg` die **Route-Fenster** (Quell- und Bildfenster) des Display-Wegs; bleiben sie auf Panelgröße, entsteht bei *vertikaler* Skalierung ein kurzes ungültiges Segment am Zeilenende (`0111`) | neu; unser K3/S6/S7-Bild (Fensterwörter 28/30/32/34 auf Panelgröße, 124 §5.2) war die Scherung, das hier ist ein anderer, kleinerer Effekt. Wert, wenn wir je selbst vertikal skalieren |
| VideoInfo-Wort `0x58` ist der **Pitch**, nicht die sichtbare Breite (`0105`) | wir schreiben dort `w` (unser `0093`, Panelbreite = Pitch, deshalb unauffällig); für 1366/1280x1024 (`0131`) lohnt der Blick |
| AFBD-Fetch ignoriert ein kleineres Raster auch bei gepolstertem Pitch: 960x544 wickelt sich dreimal über den oberen Rand, Rest grün (`0106`) | passt zu doku/86 §2.1: `0x020`/`0x024` sind 16er-Blockzahlen des *Rasters*; Fensterung geht nur über Proc-`0x34` |

---

## 5 Risiken und offene Punkte, falls wir übernehmen

1. **`S_FMT`-Falle** (`cedrus_try_fmt_vid_cap_p` nach `0120`): auf H713 mit NV12 wird jede angefragte CAPTURE-Größe per
   `cedrus_scale_size()` auf `[coded/4, coded]` geklemmt und `scaling = (w,h) != coded` - **1920x1080 auf einem
   1920x1088-Strom skaliert vertikal 1088 -> 1080 mit dem Polyphasenfilter**, statt wie Mainline 1088 zurückzugeben.
   Ein Standard-Client, der die *sichtbare* Größe setzt, bekommt ein resampeltes Bild, kein bitexaktes. Sein VA-Shim
   umgeht das zufällig (er setzt 1088 aus den Surfaces), GStreamer über seinen Patch 0001. Hantro (der Mainline-Präzedenzfall)
   macht `DIV_ROUND_CLOSEST(src/dst)` und skaliert erst ab Faktor 2. Das ist ein API-Fehler, kein Hardwareproblem; er nennt
   ihn selbst "Next work 2". **Vor einem eigenen Player: Toleranz für Beschnitt innerhalb der Makroblock-Polsterung
   (<= 15 Zeilen) einbauen oder den Client die codierte Größe setzen lassen.**
2. **Validierung ist headless und seine.** PSNR "gegen Software-Bicubic, kein absoluter Maßstab" (sein Wortlaut). Nichts
   davon lief auf einem Panel; die 4x-Stufe ist in einem Fall schlechter als der alte Shifter (45,02 vs. 46,42 dB).
3. **`0114` verschärft den Request-Vertrag**: ein Client, der Per-Frame-Controls weglässt, bekommt jetzt `-ENOENT` statt
   Müll. Richtig nach uAPI, aber ein Verhaltenswechsel für jeden bestehenden Client. Seine beiden (libva-Shim, GStreamer)
   laufen damit.
4. **Serie trägt Geschichte**: `0110` fügt `V4L2_CID_ROTATE` hinzu, `0120` entfernt es wieder; `0117` ist reine Doku. Wir
   übernehmen byteidentisch, also alle 17, oder gar nichts - das Repo-Prinzip (124 §8, PROVENANCE).
5. **Keine LICENSE-Datei in seinem Repo** (geprüft). Die Kernelpatches sind als Kernel-Derivat GPL-2.0, wie bisher; seine
   Werkzeuge (`cedrus-scaler-api-test.c`, `cedrus-control-test.c`, `cedrus-scaler-check.py`, `gen-scaler-coef.py`,
   `cedrus-compose-probe.c`) bleiben wie die MIPS-Werkzeuge in `re/cstenger-tools/`, nicht im Repo.
   *Nachtrag 23.10.2026 (Doku-Runde, TODO 1.10 h): im Abgleich vom 19.10.2026 trugen 40 seiner Werkzeugdateien einen
   SPDX-Kopf GPL-2.0; der Satz oben beschreibt den Stand vom 17.09.2026.*
6. **`0112` ist ohne Player relevant**: der DPB-Index kommt ungeprüft aus dem Userspace, jeder mit Zugriff auf `/dev/video0`
   erreicht den Out-of-bounds-Lesezugriff. Bei uns lädt cedrus (§3: DT `okay`, Modul in der Defconfig), `/dev/video*` gehört root bzw. der Gruppe `video`,
   und die Shell ist SSH key-only - Exposition gering, aber der Fix ist upstream-acked und kostet nichts.
7. **Rückmeldung an ihn bleibt gestrichen** (Marco, 17.09., doku/127 §5) - auch für die `S_FMT`-Falle. Notiert hier, nicht
   bei ihm.

---

## 6 Empfehlung

Nichts davon ist dringend; test4-Antwort und die A/Bs für den HY300 Pro (doku/127) gehen vor.

| # | Paket | Umfang | Aufwand | Gerätetest |
|---|---|---|---|---|
| 1 | **Cedrus-Serie übernehmen**: die 17 Patches als neuen Abschnitt "3b. cstengers Zweig, Decoder (Stand 16.09.)" hinter `0086`, byteidentisch, `series`-Kommentar mit Herkunft und Gate; `0095`/`0096` dazu in Abschnitt 3 (schlafend, hält decd byteidentisch für Paket 4 aus 124); PROVENANCE 142 -> 161, `docs/subsystems/video.md` und `docs/kernel-patches.md` nachziehen | Serie, Doku | halber Tag | `v4l2-compliance -d <cedrus-Node>` (v4l-utils ist klein, ohne GStreamer/mpv) + seine `cedrus-scaler-api-test` und `cedrus-control-test` (reines API, kein Strom nötig) beim nächsten Einspielen; Sollwert 49/49, null Warnungen. HDMI-Weg wie gehabt gegenprüfen - die Patches berühren ihn nicht, aber der Kernel ist neu |
| 2 | **Werkzeuge holen** nach `re/cstenger-tools/video/`: die vier aus §5.5 plus `cedrus-compose-probe.c` (LD_PRELOAD-Messadapter) und `hevc-rotation-check.sh`; README wie bei den MIPS-Werkzeugen | Host | 1 h | keiner |
| 3 | **124 Paket 3 ("Dekodieren ohne Anzeige") vorziehen, wenn Marco die Richtung will**: libva `0004`-`0007` (unverändert seit 12.09.), `build-va-driver.sh`, Gates mit bekannten MD5s; Video-Laufzeit als optionales Rootfs-Profil. Mit Paket 1 ist die Kernelseite dafür fertig; vorher die `S_FMT`-Falle (§5.1) entschärfen | Userspace | 2-3 Tage | Dekodierung bitexakt am Gerät |
| 4 | **Nicht übernehmen**: `0080`, `0098`, `0103`, `0105`, `0106`, `0108`, `0111` (Display, §3/§4); GStreamer-Patches (bei ihm selbst nicht auf dem Board); `WIP-0007-resolution-change` (libva, unvollständig) | - | - | - |

Wenn nur eins: Paket 1. Es kostet fast nichts, hält uns mit seinem Cedrus-Stand byteidentisch (jeder spätere Abgleich
wird ein `cmp`), bringt zwei upstream-acked Fixes, und wenn "Datei abspielen wie Stock" kommt, ist die Decoder-Hälfte da.

---

## 7 Zurückgenommene Behauptungen aus seinem Baum seit 124 (nicht nachbauen)

"Der beliebige VE-Scaler bei `VE+0xf00` hat keinen Datenpfad / rastet nur ein" (12.09.; er war nie mit Geometrie gefüttert,
`write_sc_rt_pic` ohne Konfiguration ist genau der beobachtete Timeout); "die VE skaliert nur um Zweierpotenzen"; "H.265
Scale/Rotate braucht RE from scratch" (die Vendor-Quelle steht auf GitHub); "SDROT für Rotation behalten"; das
"Format-Register" als Ursache des H.265-Hängers (`6e86828`, mit Eliminationsliste); die 48/49-Baseline (die Request-Suite lief
nie). Und aus 124 §3.1 bei *uns* zu korrigieren: "`VE_VERSION` liest 0 und der beliebige VE-Scaler hat keinen Datenpfad" -
die erste Hälfte bleibt, die zweite ist widerlegt.

---

## 8 Entscheidung (17.09.2026, nachmittags)

Marco: nur die Einschätzung war gefragt, keine Umsetzung. Priorität ist die Stabilität des Systems; die Cedrus-Übernahme
(§6 Paket 1-3) kommt mit den übrigen offenen Punkten (doku/61) dran, **sobald der HY300 Pro fertig ist** - bis dahin keinerlei
Priorität. Nichts angelegt, nichts in `repo-neu` geändert; die Prüfbäume liegen nur im Scratchpad dieser Sitzung.
