# 124 - Abgleich mit cstengers Zweig `h713-display-video-path` (sein Stand 12.09.2026)

Angelegt 15.09.2026, nachmittags. Anlass: Marcos Frage, was cstenger in den letzten zwei bis drei Wochen
gemacht hat und was davon für uns relevant ist - auch für Module, die wir nicht aktiv nutzen, weil unser
Ziel Stock-Funktionalität ist.

**Grundlage.** Sein Repo `cstenger/allwinner-h713-mainline`: `main` steht unverändert bei `8860991`
(22.08.), das ist genau unser Subtree-Stand. Der Zweig `h713-display-video-path` hat **342 Commits**
darüber, 22.08. bis 12.09., Spitze `b54adaf` ("docs: hand off the scaling driver as it stands on
hardware"). Dazu sein U-Boot-Fork `cstenger/u-boot` Zweig `h713`, Zeiger `7b17805 -> 76eef86`.
Vier Prüfberichte (Opus-Agenten, nur lesend, je Thema beide Bäume gegeneinander) liegen unter
[`analyse/cstenger-abgleich-20260915/`](../analyse/cstenger-abgleich-20260915/): `A-video-decode.md`,
`B-display-mips.md`, `C-cpucomm-audio-hdmi.md`, `D-uboot-tools-infra.md`. Die harten Behauptungen darin
habe ich stichprobenartig selbst nachgeprüft (unten jeweils vermerkt). Sein Board: HY200 Bench, 1280x720
Einport-Panel, Projekt-ID 0x34, MIPS wird von seinem U-Boot geparkt. Unser HY310: 1920x1080 Doppelport,
0x30, MIPS lebt unter Linux durchgehend.

---

## 1 Kurzfassung

1. **Sein Zweig ist die Suche nach Medienwiedergabe ohne GPU auf einem 720p-Board**: Cedrus-Dekodierung
   produktionsreif gemacht (22.-24.08.), VA-API-Shim und mpv gepatcht (bis 03.09.), dann drei Wochen
   Kampf, dekodierte Frames über DECD aufs Panel zu bringen - erst mit geparktem MIPS (31.08.), ab 08.09.
   mit lebendem MIPS - und zuletzt (10.-12.09.) 1080p auf sein 720p-Panel zu skalieren.
2. **Vieles davon haben wir früher und anders gelöst.** Den Zweiachs-Scaler bei `0x05180008/0x0518003C`
   fanden wir am 07.09. (er am 10.09.); bei uns programmiert ihn die Firmware selbst über den
   neu veröffentlichten VidDec-Deskriptor (`0117`/`0120`). MIPS lebend, cpu_comm, SetSource, ARISC mit
   HPD/EDID, HDMI-Eingang als V4L2, HDMI-Audio: alles bei uns fertig, bei ihm an HPD gescheitert.
3. **Er hat drei Dinge, die uns fehlen**: einen kompletten Wiedergabe-Userspace (wir liefern bewusst
   keinen aus), sieben statt drei libva-Patches (HEVC, Skalierungsmatrix, Main10, mpv-Interop), und
   Dekodier-Robustheitsgates (2 h Soak, 3 Clients, 16 defekte Ströme). Das ist der Weg zu "Datei
   abspielen" = Stock-Funktionalität.
4. **Konkrete Fehler bei uns, die der Abgleich aufdeckt** (§4): wir tragen noch sein `0040`, das er am
   23.08. wegen eines Deadlocks aus der Serie geworfen hat; unser `0013` (decd) schreibt in `blue_en`
   in den Y0-Adressslot des Rings; das Phantom-Makro `CONFIG_DEBUG_FS_AIC` steckt auch in unserem
   aic8800-Baum; `MAGIC_SYSRQ` fehlt im Release-Kernel; doku/89 nennt `0x05000174` noch
   "Skalierverhältnis"; doku/62 sagt noch "kmssink geht nicht".
5. **Neue Fakten für uns** (§3): `0x05180034` ist das Eingangsfenster des Proc-Scalers (unsere offene
   Frage aus doku/93), der Block hat vier Instanzen und lebende obere Bits; `0x05600014` retiriert am
   Vsync; die Composition-"Ratio"-Register sind Zeilenpuffer-Deskriptoren; Scaler-Zensus: genau drei
   verhältnistragende Blöcke im ganzen `display.bin`; `VE_VERSION` liest 0 und der beliebige VE-Scaler
   hat keinen Datenpfad.
6. **Widersprüche, bei denen wir die bessere Evidenz haben** (§3.2, §3.3): sein "Formatbyte muss 3
   sein" (widerspricht seinem eigenen 0078 und unserer A/B-Messung), "ARM-Framebuffer und lebender
   MIPS schließen sich aus" (er hat es am 08.09. selbst widerlegt, der Satz steht aber noch in seiner
   status.md), "Never read 0x06940000" (Boardzustand, kein Hardwaregesetz; wir schreiben INCAP täglich).
7. **Wir können ihm ein Dutzend offene Punkte fast kostenlos beantworten** (§5): vier auf der Displayseite
   (Scaler-Modusfelder, die Schur, `0x05600024`, `0x05600030/48/4c`) und seine ganze HDMI-IN-Sackgasse (ARISC-Port 0
   statt 3, Firmware-Ladeweg, `0x07091014` nach ARISC-Init lesbar, EDID-Sequenz, `GIC_SPI 46`, zwei Defekte in
   seinem `0014`). Das ist der wertvollste Teil des Abgleichs.
8. **Neu für uns aus seiner HDMI-IN-Arbeit**: `0x050c0000` ist nur ~`0x0d00` Bytes hinterlegt (erklärt unser
   "DMA-CONFIG-Register lesen 0"), `0x06840000` aliast alle `0x800`, `0x050c0400/0500/0600` sind keine EDID-RAMs;
   und aus seiner MIPS-RE: Event-8-Dispatch über eine Sekundär-vtable, `GetFrameInfo` schreibt in den
   Aufrufer-Puffer, ARM-Lesungen von MIPS-Globals sind nicht cachekohärent.

---

## 2 Was er gemacht hat, nach Thema und Datum

| Zeitraum | Thema | Ergebnis | Belegt |
|---|---|---|---|
| 22.08. | DVFS | 1416-MHz-OPP korrumpiert Speicher unter GPU+Display-Last; Deckel 1296 MHz (`0055`) | HW, 20 min sauber; **tragen wir** |
| 22.-24.08. | Cedrus-Robustheit | `0040` aus der Serie (Deadlock bei 3 Clients), `0059` IRQ-Orphan-Fix, 2 h Soak 195.332 Bilder, 3 Clients 3 h 483.433 Bilder, 16/16 defekte Ströme | HW |
| 22.-24.08. | VA-API | HEVC auf PR-38-Basis (`0004`), Skalierungsmatrix (`0005`), Main10 (`0006`): H.264 5/5 und HEVC 5/5 bitexakt durch unverändertes ffmpeg; Main10 dekodiert (57 dB PSNR), nur 8+2-Ausgabe ohne Fourcc | HW |
| 24.-25.08. | Boot-Konsole | AFBD-Treiber `=y` statt `=m` (fbcon bei 1,25 s statt 6,5 s), dummycon 160x45, `TTYVTDisallocate=no`, aic8800-Logspam gedämpft (`0007`/`0009`) | HW |
| 25.08. | Plane-RE | `ge2d_dev.ko` statisch: keine zweite Plane auf dem Scanout, GE2D ist der Displaycontroller, kein Blitter | RE, HW-Negative |
| 28.-31.08. | DECD bei geparktem MIPS | Stock-Frame-Submit-ABI (`0067`), Chroma-Gain `0x05140508[23:16]` (Stock 0x4C), Selektor `0x051c006c` 0x39000000 kausal, erster sichtbarer NV12-Scanout unter Linux | HW |
| 30.-31.08. | cpu_comm | Fünf Commits an `0014`: Doorbell `0x03003874`, FIFO `0x03003864`, 32-Bit-Shared-Pointer auf arm64, Argument-ABI; Routinentabelle (82 Routinen), Stubs benannt | HW-Roundtrip |
| 01.09. | IOMMU | Master 2 zur Laufzeit übersetzen, Umschaltung `0x7c -> 0x78` nur mit geparkter Quelle (`0076`); Video-Plane `0078`/`0079` | HW, 27 fps |
| 01.-02.09. | Audio | Codec über `sun4i-codec`-Variante, Lautsprecher am HP-Amp, Audio-PLL stand auf 172 MHz (4,8 % zu langsam), `0082`-`0086` | HW; **tragen wir** |
| 02.09. | HDMI-IN | TVFE/TVCAP-Domänen an, Registerkarte gescannt, EDID-Schnittstelle `rx+0x50/0x54`, **an HPD gescheitert** (`0x07091014` hängt den SoC; keine ARISC-Firmware geladen) | HW-Negative |
| 03.09. | mpv | Zero-Copy mit Stock-mpv (`--hwdec=vaapi --vo=gpu`), drei mpv-Patches für `vo=drm` auf die PRIME-Plane, `build-mpv.sh`; Software-Dekodierung schlägt Hardware-plus-Kopie | HW |
| 04.-05.09. | MIPS lebend | Linux bootet mit lebendem MIPS (`h713_disp init`), Debug-Shell, elog (level 5 **und** mode 2), `Vp_Init`, `SetSource(1)`; Hard-Lock war das 60-Hz-Ringschreiben bei lebendem Kern | HW |
| 06.-09.09. | Video mit lebendem MIPS | **Gelöst 08.09.**: Formatbyte, `0x0560006c` (Adressen), `0x05600014` (Konfig, retiriert am Vsync); Route im Treiber (`0095`); dma_buf-Leck begrenzt (`0096`); Hard-Lock ~ fehlende `0071`-`0073` | HW, 29,96 fps |
| 10.-11.09. | Scaler | Composition-"Ratios" sind Zeilenpuffer; Zweiachs-Scaler `0x05180000` gefunden, auf dem Videoraster live, vergrößert nur; Zensus: drei Blöcke; VE skaliert nur um Zweierpotenzen (`0x240`), beliebiger VE-Scaler bei `VE+0xf00` inert | RE + HW |
| 12.09. | 1080p auf 720p | Route VE-Halbierung 960x544 + Proc-Vergrößerung 1,333x (`0098`/`0099`); `0x05180034` = Eingangsfenster; Rest: Scherung bei 1280 Pixel Zeilenlänge, senkrecht wirkungslos | HW, unfertig |
| 28.08.-04.09. | U-Boot | Vp_Init-Tracer, Logo im Preboot, Mixer/DE/TCON-Totale gekoppelt (Revert), PanelWinNode-Trace, `h713_disp logo-live` | vier von sechs Commits haben wir |

Zahlen: 615 Dateien, +147k/-75k Zeilen; davon `docs/reference/` +96k (Messmitschnitte), `tools/display` +8,6k,
`tools/video` +7,2k, `patches/kernel` +11k, `tools/mips` +1,6k, `patches/libva` +1,6k, `patches/mpv` +0,9k.

---

## 3 Abgleich Thema für Thema

### 3.1 Dekodierung und Wiedergabe-Userspace (Bericht A)

**Was er hat und wir nicht.**
- Rootfs mit Video-Laufzeit (~680 MB: gstreamer, mesa, mpv, ffmpeg, v4l-utils). Unser
  `rootfs/packages.txt` schließt genau das aus, Begründung Zeile 89-93: "Der Beamer schiebt HDMI-Eingang
  auf eine DRM-Plane, er decodiert nichts." Auf unserem Abbild gibt es heute **keinen Weg, eine Datei
  abzuspielen**. Stock kann das (lokal, USB, Netz).
- libva-v4l2-request: er 7 Patches, wir 3 (identisch mit seinen 0001-0003). Seine 0004-0007 sind
  hardwaregeprüft. 0007 ist die Ursache, warum Zero-Copy mit mpv geht (Probe-Puffer 128x128 vergifteten
  die späteren Puffer), nicht der Render-Node.
- mpv-Patches (3) für `--vo=drm` direkt auf die PRIME-Plane, plus `build-mpv.sh` (emulierter arm64-Container).
- Gates: `soak-decode.sh`, `decode-concurrency-test.sh`, `decode-robustness-test.sh`, `decode-leak-test.sh`,
  `va-decode-test.sh` mit bekannten MD5s.

**Neu für uns (Fakten).** `VE_VERSION` (`VE+0x0f0`) liest 0. Der beliebige VE-Scaler ist im Vendorcode
real (`H264ConfigNewScaler`, 14 Verhältnisklassen), sein Registerblock `VE+0xf00` rastet jede Schreibung
ein, und es kommt nichts heraus - kein Datenpfad auf diesem Silizium. `VE_H264_CTRL` Bit 11 bricht die
Dekodierung. Ein VE-Timeout wedgt das Board nicht. GStreamer verhandelt ungezwungen das gekachelte
`NV12_32L32`. Das `ve`-Node braucht beide IOMMU-Masterports (`<&iommu 0 1>, <&iommu 1 1>`; nur Port 0 =
stumm korruptes Bild ohne Fehlermeldung) - wir tragen `0042` byteidentisch, sind also richtig. Der
libva-Shim muss **auf dem Board** gebaut werden (Einstiegspunkt `__vaDriverInit_<major>_<minor>` nach
der libva-Version zur Bauzeit). Software-Dekodierung (206,9 fps 720p) schlägt Hardware-plus-Kopie
(137,3 fps); Hardware lohnt nur ohne Rückkopie.

**Patch `0040` - streichen.** Wir tragen es noch (`series` Zeile 57, ohne Kommentar). Sein Header seit
23.08.: *"OUT OF patches/kernel/series ... It causes a deadlock. Three concurrent decode clients wedge the
engine: one client's teardown resets the device while another context has a job in flight ... the next
STREAMOFF waits forever in v4l2_m2m_cancel_job() in D state, beyond the reach of SIGKILL."* A/B im selben
Boot über `sunxi_cedrus.stop_reset`: N gibt 9/9 bitexakt, Y deadlockt in Runde 1. Sein Daseinsgrund
(Speicherkorruption) war der 1416-MHz-Betriebspunkt, den `0055` entfernt - und `0055` tragen wir. Code
byteidentisch, Fehlermodus hardwareunabhängig (m2m-Kontextlogik). Empfehlung: aus der Serie nehmen,
nach `zurueckgenommen/`, ohne eigenen Gerätetest; solange wir keinen Dekodier-Userspace ausliefern, ist
das Risiko latent, mit Schritt 1 unten wird es scharf. `0057`/`0062` (Watchdog/Reset-Varianten) sind bei
ihm out of series (Prämissen widerlegt) und bleiben es bei uns; `0059` haben wir und es ist der einzige
mit demonstriertem Fehlerfall.

**Zu `0099` präzise** (Marco fragte nach "akribisch"): der Patch-Header sagt "Compile-tested only", der
gleichtägige Handoff sagt: Compose-Auswahl läuft am Gerät (1280x720 angefragt auf 1080p-Strom liefert
960x544), Rekonstruktionsrahmen werden belegt (~55 MB), keine Dekodier-Regression (MD5 `879fb659…`
bitidentisch). **Die skalierte Dekodierung selbst ist nie gelaufen** - nichts auf seinem Board setzt ein
Compose-Rechteck. Bewiesen ist die VE-Halbierung nur über die 0097-Messvorrichtung in einen
debugfs-Puffer.

**Für uns irrelevant:** die ganze 1080p-auf-720p-Route (`0097`/`0098`/`0099`, 8,5 dB schlechter als echtes
1,5x, 56 % der Luma-Abtastwerte) - unser Panel ist 1080p; `0074` (64-MiB-Pool, bei ihm seit 01.09.
draußen); die Debug-Patches `0057`/`0058`/`0060`/`0061`/`0062`/`WIP-0007`; AV1 kommt in seinem Baum
nirgends vor.

**Veraltet bei uns:** doku/62 §"kmssink geht nicht" (Zeile 133) - sein `0063` behebt genau das und liegt
seit 12.09. in unserer Serie.

### 3.2 Display, DECD, MIPS-Fensterschicht, Scaler (Bericht B)

**Neu für uns, mit Status.**

| Befund | bei uns |
|---|---|
| **`0x05180034` = Eingangsfenster** des Proc-Scalers, `(w<<16)\|h`; liest `0x050002D0` auf seinem Raster | **neu und beantwortet doku/93 TODO 1** ("woher nimmt der aktive Scaler seine Eingangsgeometrie?"). Unsere drei Kandidaten `0x50`/`0x2C`/`0x44` waren alle falsch |
| Vier Instanzen im Abstand `0x100`; 0 und 1 auf dem Videoraster live, 2 nicht, 3 lief nie | neu |
| Alle Register des Blocks tragen **lebende obere Bits** (`0x08` liest `0x43010000`, `0x00` `0x0F008000`): nur Read-Modify-Write; V-Phase bei Einheit ist 0, nicht 0x10000 | neu als Betriebsregel |
| Seine Messwerte `0xC000`/`0x7000`/`0xE0B6` bestätigen unsere `CalcScaleRatio`-Herleitung (doku/93, `sub_8B1A56B8`) Zahl für Zahl | Gegenprobe, zwei unabhängige Wege |
| `0x05600014` (Quellkonfig-Commit) **retiriert am Vsync**: Polling mit Budget > 16,7 ms, sonst stilles Ignorieren bei korrektem Rücklesen (Bild doppelt in halber Höhe) | teilweise: doku/86 §2.4 kennt das Latch, nicht den Grund; unser `0078` (byteidentisch mit seinem) hat die 50-ms-Schranke in `wait_ready` ohne Begründung, sein `0081` liefert den Kommentar |
| Composition-"Ratio"-Register sind **Zeilenpuffer-Deskriptoren**: `0x1b4` = Y-Rowbyte/LineBufLevel, `0x1b8` = Y-LineNumber, `0x174`/`0x178` dasselbe für Chroma, aus `FrameBuffer::GetPsuPfuWin` (`0x8b1a2668`) | **korrigiert doku/89** Zeile 29 ("96/96 = 1:1, keine Skalierung"); doku/92 hatte das Label schon verworfen, ohne Ersatzdeutung |
| Scaler-Zensus über die Instruktionssignatur `ins rt, rs, 0, 0x16`: genau drei verhältnistragende Blöcke - `0x06940864/87c` (CapWinNode), `0x051c0138` (Panel, nur senkrecht, `dst/src`, Bypass `[26:25]=3`), `0x05180008/3c` (Proc) | neu als Methode und Vollständigkeitsaussage; den Capture-Downscaler kennen wir aus doku/84 |
| Formattabelle der Firmware `0x8b2078a4` (Deskriptor-Selektor -> AFBD-Formatbyte: 0->0, 6->3, 11->4) | neu |
| `0x05600020` = `[12:0] align16(w)-1, [28:16] align16(h)-1`; `0x030` Breite gerade erzwungen; `0x048/0x04c` auf 4 ausgerichtet; `0x020` und `0x030` aus **zwei** Geometriestrukturen (Bild- gegen Ausgabefenster) | neu im Detail; unser `0093` rundet nur die Höhe; für 1366/1280x1024 lohnt ein Abgleich (`0131` hat die Ringteilung korrigiert, die Breite in `0x020` nicht) |
| `NRWinNode::WriteReg`-Abfolge (26 Register), Abschluss `0x05000840` dann `0x05000040` Bit 25 | neu |
| dma_buf-Refcount-Modell in decd: vier Ringslots aliasen ein Frame, `interlace_hold` ist `(void *)1`, FIFO-Tiefe = Referenzzahl (11 beobachtet) | nur decd-relevant |
| IOMMU-Umschaltung Master 2 nur mit geparkter Quelle | derzeit nicht anwendbar, unser Display hängt nicht am IOMMU |
| Hard-Lock ~ fehlende `0071`-`0073` | bei uns von Anfang an in der Serie |

**Drei Widersprüche, bei denen wir die bessere Evidenz haben.**
- *Formatbyte `0x05600011` = 3, "0 = RGB888"* (08.09.). Sein eigener `0078` setzt `0x03000013` (Formatfeld 0)
  und lief mit 59,71 fps NV12; sein 31.08.-Erfolg ebenso. Unsere A/B-Messung (doku/86 §3, Foto `f422.jpg`):
  Formatfeld 0 liefert NV12 **und** NV16 korrekt, `0x...0213` macht das Bild grün. Wahrscheinlicher
  Unterschied: der Ring-Mux `0x05600068 = 0x122`, den 0078 setzt und sein 0095 nicht anfasst. **Nicht
  übernehmen, ohne es selbst zu messen.**
- *"ARM-Framebuffer und lebender Window-Layer schließen sich aus"* (04.09.) steht noch als Tabelle in
  seiner status.md, obwohl er es am 08.09. selbst widerlegt hat. Unser Modell (doku/96 §1: ARM besitzt
  AFBD, MIPS alles dahinter, der VidDec-Deskriptor ist die Signalquelle) ist sauberer.
- *"Never read `0x06940000`"* (TVCAP ungetaktet). Bei ihm ein Boardzustand; wir lesen und schreiben INCAP
  routinemäßig (`0x06940824`, `0x06940928/0968`, Patches `0121`/`0122`/`0131`). Sein Schluss "der
  Capture-Scaler ist unerreichbar" gilt nur für seinen Datenweg (DRAM -> Anzeige).
- *"`0x05180000` vergrößert nur"*: kein Widerspruch zu uns (`ratio = min/max <= unity`), aber schwächer
  belegt als behauptet - sein Downscale-Sweep lief mit unangetastetem `0x34`, also `in == out`.

**Ein Punkt, an dem er uns korrigiert:** `0x05000174` (§ oben, doku/89).

**Übernehmbar:** nur die drei `0013`-Korrekturen (§4) und der `0081`-Kommentar. `0080` (Display an den
IOMMU) kollidiert mit unserer Probe und wäre für den firmwareeigenen Capture-Ring an festen physischen
Adressen (doku/86 §2.2) schädlich. `0095`/`0096` betreffen ein decd-Modul, das bei uns nicht bindet.
`0098` schreibt genau die `atomic_check`/`atomic_update`-Pfade um, die unsere `0093`/`0107`/`0117`/`0120`/
`0131` besitzen (20 Hunks gegen den 0037-Stand, elf eigene Patches an derselben Datei) - nicht als Patch,
nur als Registerkenntnis.

**Irrelevant:** `ring_writes_max=1` und die 852x480-Composition-Episode (Folgen eines eingefrorenen
Ring-Writers, den wir nie hatten, weil der MIPS bei uns den Ring selbst dreht); die
Parked-MIPS-Rezepte; die event8-Trampoline im zweiten Bootloader (bei uns beantwortet elog Stufe 5 plus
Shell dieselben Fragen ohne Flash).

### 3.3 cpu_comm, SetSource, Audio, HDMI-IN, ARISC (Bericht C)

**cpu_comm.** Seine fünf Commits vom 30./31.08. an `0014` (Doorbell `0x03003874`, FIFO-Zähler `0x03003864`,
RX `0x03003164/0x03003174`, Mapping `0x400 -> 0x1000`, blanker Nachrichtentyp, `TX_IRQ_EN`-Puls, `cc_ref` statt
32-Bit-Zeiger, `+0x34` = Parameter 3, sechs `BUG()` raus) sind mit doku/65-67 deckungsgleich; vier Dinge davon
haben wir beim Drei-Wege-Merge übernommen, zwei Defekte haben beide Seiten unabhängig gefunden (doku/67 nennt
`ec53910`). Was wir haben und er nicht: die In-Kernel-API (`0092`), die Slot-Rückgabe nach Callbacks (`0124`; ohne
sie hängt die Firmware nach 19 Rückrufen), keinen zweiten Leser auf dem NewCall-Ring (`0105`; er verliert ~30 %
dichter Calls), `0125`, null lebende `BUG()` gegen seine ~90, und die CRC-32-Ableitung der comp_ids (doku/83; seine
Call-Table sagt "not derivable from the name" - widerlegt gegen alle namentlichen Einträge). Sein `GIC_SPI 21` ist
die S/PDIF-Leitung (richtig 46, doku/66); sein hrtimer-Poll ist ein Umweg um dieses DTS-Problem. Unsere
`0014`-Fassung weicht 3194 Zeilen von seiner ab - eine PR lohnt nicht, eine Notiz mit den zwei Defekten schon.

**SetSource und Signalkette.** Sein Fall ist Quelle 1 (VideoDecoder): `SetSource(1)` erreicht `AppTopSetSource`
und `SetSignalInfo`, aber kein `UpdateWce`; "Signal" für Quelle 1 ist der VideoInfo-Deskriptor in
`0x05600098..a4`, Detektor `CVidDecSignalDetector` (vtable `0x8b1f8d78`, `CheckSignal` Slot 3 `0x8b147dd0`,
`GetFrameInfo` Slot 6 `0x8b147834`), STM `THidTVPro` Slot 16. Unser Fall war `SetSource(3)` = HDMI mit dem
bewiesenen NULL-Zeiger `sgp_hal_signal_info` (doku/74) - andere Klasse. Neu für uns: der Event-8-Dispatch über eine
Sekundär-vtable (`Enable VideoDecoder 0x8b146e34` registriert `callback = self+0xbc`, `DoMessage 0x8b156bf8`, Thunk
`0x8b147678`), `dtv get_fb` als Hebel auf `GetFrameInfo`, `GetFrameInfo` schreibt in den **Aufrufer-Puffer** `a1`
(Nullen in `self+0xb0` beweisen nichts), und **ARM-Lesungen von MIPS-Globals sind nicht cachekohärent** (die
Firmware arbeitet auf gecachtem KSEG0) - das gilt für jede unserer `/dev/mem`-Beobachtungen von Firmware-Objekten.
`Wce_GetWindow` nimmt drei ARM-physische Ausgabeadressen; der Adapter maskiert auf 28 Bit und ODERt `0xa0000000`,
die unveränderte physische Adresse ist richtig. Seine 18 "(unnamed)"-Routinen sind seine eigenen Registrierungen.
`GetSource` gibt bei ihm angeblich immer 0 zurück; unser debugfs-Beispiel (doku/83) zeigt nach `SetSource 3` den
Wert 3 - gegenprüfen, sein ganzer "live source is Dummy"-Faden hing daran.

**event8-Trace.** Acht MIPS-Trampoline in einem Code-Cave, Zähler in `0x4e340080..9c` (KSEG1), 32 gepaarte
Unicorn-Fälle, installiert über einen temporären Flash der zweiten Bootloader-Stufe (zwei flüchtige Wege
faulteten; `event8-table-copy.S` ist "DO NOT RUN"). Ergebnis: Callback und CheckSignal liefen 997 -> 3928 und
stehen unter Linux still, der event8-Zähler bleibt 0 und widerspricht seiner eigenen These. Bei uns nicht direkt
nutzbar (an seinen Firmware-SHA gebunden); das Generator-Muster ist die sauberste MIPS-Instrumentierung im
Projekt und wäre für unsere offene Frage, warum ein Aufruf bei uns ~120 ms dauert (IRQ) und bei ihm 17-30 ms
(Poll), das richtige Werkzeug.

**Audio.** `0082`-`0086` tragen wir byteidentisch; sein Taktbefund (Teiler 1024, Flag **und** `mod_freq_mult = 2`;
440 Hz kamen als 418,97 Hz zurück, die PLL stand auf 172 MHz) und der HP-Amp-Befund (Lautsprecher am
Kopfhörerverstärker, `Line Out Playback Volume` +0,21 dB über den ganzen Bereich) sind bei uns in Betrieb.
"Stock never captures audio" stimmt (analoger Pfad, kein Mikrofon). "HDMI-in audio is a separate path" stimmt,
sein Bild davon nicht: er vermutet eine Capture-Schleife über die Audio-Bridge, genau die Stufe, die wir am 08.09.
gemessen tot verworfen haben (doku/100 §2/§6); der reale Weg ist HDMI-RX -> MSP-DSP-Insel -> I2SOUT1 ->
Codec-I2S-Fenster `0x02031000` -> DAC (`0134`-`0138`). Seine offene Frage, ob der zweite Reg-Bereich `0x02031000`
nötig ist: ja, das ist der ganze HDMI-Audio-Weg. Brauchbar bleibt seine ADC-Registerkarte (`61c5585`: FIFO
`0x030`, RX `0x040`, Analogsteuerung `0x300/0x304`), falls je ein analoger Eingang auftaucht.

**HDMI-IN und ARISC.** Er ist an HPD gescheitert: `0x07091014` hängt den SoC (zweimal), "keine ARISC-Firmware
geladen, SRAM A2 hält boot0", die ARISC-EDID-Handler "hollow by design", Schluss "`0x07091000` is not
ARM-addressable". Alles drei erklärt unser Stand: `0091` lädt die ARISC-Firmware aus dem Stock-Abzug
(ARM-Adresse = ARISC-Adresse + `0x100000`, Fenster `0x00100000 + 0x23000` - seine A2-Suche lag im falschen
Fenster), der Startup-Handshake ist Pflicht, der HDMI-Weg läuft über user1 **Port 0** (`0x03003470`), nicht
Port 3 (Standby-Dispatcher, antwortet auf alles Fremde mit -3 - das war unsere eigene frühere Fehldeutung, am
05.09. in doku/68 zurückgezogen), und `0x07091014` ist nach der ARISC-Initialisierung ARM-lesbar (`0x07`). Drei
harte Negative von ihm sind neu für uns: `0x050c0000` ist nur ~`0x0d00` Bytes hinterlegt (erklärt endlich unser
"DMA-CONFIG-Register lesen 0", doku/75), `0x06840000` aliast alle `0x800`, `0x050c0400/0500/0600` sind
Registerbänke und keine EDID-RAMs. Seine "rx-EDID-Schnittstelle" bei `0x05000050/54` widerspricht unserem
S22-Befund (`0x05000000` = `DE2_NR_base`, Display-Engine) und ist vermutlich eine Fehldeutung; der HDMI-RX ist
vollständig der Byteblock `0x0680xxxx/0x0684xxxx/0x0688xxxx`. Dazu: `sunxi-tvtop` beansprucht `GIC_SPI 110`
(= AFBD) und PB5 (ergänzt doku/71); `clk_summary en=` ist der Framework-Refcount, nicht das Gate (kostete ihn einen
Stromzyklus); TF-A erwartet den SCP in den letzten 16 KiB von SRAM A2 und schaltet mit geladener ARISC auf
SCPI-PSCI - gilt für unsere TF-A-Basis. Sein `0087` (TVFE/TVCAP als PPU-Domänen) brauchen wir nicht, bei uns macht
das U-Boot (doku/71).

### 3.4 U-Boot, Werkzeuge, Build, aic8800 (Bericht D)

**U-Boot.** Sechs Commits im Zeigerbereich; vier haben wir wörtlich (Vp_Init-Tracer `534adc4` =
`h713_mips.c:2340` Marker 7101-7105; Logo im Preboot `80cc220`; das Paar `cbdc6d6`/`8fe568c` hebt sich
auf). Neu: `5d86b50` (PanelWinNode-Trace, Marker 6101-6103, reine Diagnose) und `76eef86`
(`h713_disp logo-live`: `h713_disp_auto_logo()` mit `quiesce`-Bool). Letzteres ist relevanter, als es
aussieht: unser HY310 bootet mit `h713_disp init ${h713_project}` (`board/sunxi/hy310.env:45`, geprüft),
also MIPS lebend, aber **ohne Boot-Logo**; unser `h713_disp_auto_logo()` quiesced (`:11509`). Ein Logo
mit lebendem Kern - Stock zeigt eins - ist bei uns fünf Zeilen plus ein Stromzyklus.
**Lehre aus dem Revert:** Mixer-, DE- und TCON-Totale (`0x0525c000`, `0x0524c010`, `0x05880020`) sind
blockübergreifend gekoppelt; eine Teilmenge ändern gibt Schwarz, und U-Boot meldete dabei "boot logo
published and committed".

**tools/mips** (neu, alles Host-seitig gegen `display.bin`, bei uns `re/ida/IDA_hy310/display.bin.bak`):
`block-survey.py` (lui-Stellen je Block), `block-map.py` (Zugriffe je Register, verfolgt Basen über
Verschiebungen), `vtables.py` (C++-Klassen aus RTTI), `cfg.py` (echte Funktionsausdehnung über
Kontrollfluss), `elf-addr.py`/`arm-callsites.py` (Vendor-`.so`: Segment-Skew, Thumb-Resync, PLT). Echte
Lücken bei uns: die ersten vier. `mips-shell.py` ist ärmer als unsere `analyse/hdmi-seq/mipsshell.py`
(doku/98). Zwei Fallen, die er teuer gelernt hat: die lui-Stellenzahl ist keine Rangliste (`0x05180000`
stand monatelang mit "1 Stelle" unten und ist der Scaler), und ein lui-Tracker muss Register
invalidieren, sobald etwas sie neu definiert (Falschmeldung `0x051c006c`).

**tools/display:** `mmio-rw.c` mit **Byte**-Zugriffen (HDMI-RX-Wrapper `0x06800800` ist bytebreit,
Wortschreiber verschwinden), `mmio-scan.c` (Marker + flush vor jedem Seitenzugriff), `latch-timing.c`
(Vsync-Latch = Streuung 0-16,7 ms, Sofort-Latch = µs), `frame-stage-watch.c`, `page-classify.py`
(vier Proben je Fenster statt zwei, klassifiziert statisch/zustandsgetrieben/freilaufend), `hidtvreg-*`
(Stock-Android-Seite), `tear-measure.py`/`edge-measure.py`. Konzeptionell am interessantesten:
`page-classify.py`.

**tools/serial:** `--wait-for-power-cycle` (nur Unterbrechungstasten, kein `reboot` - genau unsere
FEL-Kabel-Regel), `send_file.py` mit `$`-Prompt, `sysrq.py` mit BREAK über `TIOCSBRK`.

**Build/Config:** Kernel nicht gebumpt (6.18.38, gleicher Tarball-SHA). `build/` ist reines Ausgabeverzeichnis,
Skripte in `tools/build/`, `config/paths.sh` mit `H713_BUILD_DIR`. Seine Aufräum-Lehre: 101 Kernelbäume,
208 GB, 621k Verzeichnisse, `git status` 21 s, fsmonitor tot. **Wir haben dieselbe Form**:
`mainline/build` = 25 GB, elf `linux-6.18.38-*` à 2,1 GB (geprüft). Sein Shipping-Defconfig hat gegenüber
unserem: `AFBD=y` (Boot-Log auf dem Panel), `DUMMY_CONSOLE_COLUMNS/ROWS` 160x45, **`MAGIC_SYSRQ=y` +
`_SERIAL` + `_DEFAULT_ENABLE=0x1`** (nach einem eMMC-Wedge, bei dem `reboot` nicht mehr lief; verifiziert
am Gerät). Unser Release-Kernel hat kein SysRq.

**aic8800:** Submodul statt Tarball (gleicher Commit `df4c783b`, gleiche Bytes - kein Handlungsbedarf,
die Lehre "ein veralteter Zweitbaum schlägt jede Prosa-Warnung" schon). Drei neue Patches, alle
`patch --dry-run` sauber gegen unseren entpackten Baum (`mainline/build/aic8800-df4c783b663e-…/`):
`0007` (zehn `printk`/`netdev_info`-Stellen über `aicwf_dbg_level`), `0008` (`rc_stat`-Queue wurde je
Lauf nur einen Eintrag geleert, plus OOB: `dir_sta[]`/`rc_config[]` 32 groß, Index gegen 36 geprüft),
`0009` (**`CONFIG_DEBUG_FS_AIC` existiert nirgends**, Register unter `CONFIG_DEBUG_FS`, Unregister unter
dem Phantom - bei uns in `rwnx_main.c:3102` und `:3216`, geprüft). Nummernkollision mit unserer `0007`,
also als `0008`-`0010`.

**Sonstiges:** `split-udisk.sh` - die Werks-GPT hat **26 Einträge** (LBA 2..8), Standard-128 belegen
LBA 2..33 und zerstören den SPL bei LBA 16; ist ihm am 28.08. passiert. `boot-switch.sh` bestätigt:
`sunxi-fel -p uboot` geht auf diesem SoC nicht (AArch64-Warmreset), Rettung ist `-p spl`.
`install-kernel-module.sh`: cedrus/afbd/scanout sind Module, ein FIT-Flash erreicht sie nicht - sein
Board lief nachweislich mit einer `sunxi-cedrus.ko` ohne zwei Serienpatches. `upstream/`: vorbereitete,
bewusst nicht abgeschickte PR gegen bootlin #44 ("Sending it is a decision, not a follow-up step").

---

## 4 Fehler und Lücken bei uns, die der Abgleich aufdeckt

| # | Befund | Beleg | Kosten |
|---|---|---|---|
| 1 | **`0040` noch in unserer Serie** (Deadlock bei parallelen Dekodern, Grund mit `0055` weggefallen) | sein Header, A/B 9/9 gegen Deadlock Runde 1; Code byteidentisch | eine Zeile in `series`, Datei nach `zurueckgenommen/` |
| 2 | **`0013` `dec_reg_blue_en` schreibt `workaround + 16`**, und `workaround = afbd + 0x60` (Zeile 108 des Patches), also `0x05600070` = `AFBD_VIDEO_Y0`; aufgerufen in jedem `dec_frame_submit` (Zeilen 2608, 2650). Stock: `workaround + 5`, Bit 0 (`0x05600065`) | selbst geprüft | klein; decd bindet bei uns nicht (`dec@5600000` durch 0038 aus), also schlafend |
| 3 | `0013` `dec_frame_recycle` nimmt `q->lock` doppelt (jeder Aufrufer hält ihn) - Selbstverklemmung sobald `recycle_fifo` nicht leer | sein Diff | dito |
| 4 | `0013` `dec_frame_queue_repeat`: `q->slots[1] = q->slots[0];` fehlt; `force_interlace` -> `repeating` | sein Diff | dito |
| 5 | aic8800: Phantom-Makro `CONFIG_DEBUG_FS_AIC` (`rwnx_main.c:3102`, `:3216`), AP-Debugfs-Unregister nie einkompiliert; `rc_stat`-OOB | Dry-run sauber | drei Patches als `0008`-`0010` |
| 6 | `MAGIC_SYSRQ` fehlt im Release-Kernel | Defconfig-Diff | drei Config-Zeilen; ohne Sonoff wäre `echo b > /proc/sysrq-trigger` unser einziger Softwareweg aus einem Wedge |
| 7 | doku/89 Zeile 29: `0x05000174` "Skalierverhältnis 96/96 = 1:1" - ist Chroma-Rowbyte/LineBufLevel | seine RE `0x8b1a2668` | Doku |
| 8 | doku/62 §"kmssink geht nicht" (Zeile 133) veraltet, `0063` liegt seit 12.09. bei uns | series | Doku |
| 9 | doku/93 TODO 1 offen: Eingangsgeometrie des Scalers = `0x05180034`; die drei Kandidaten falsch | sein 12.09.-Handoff | Doku (doku/93, doku/96) |
| 10 | `mainline/build` 25 GB, elf Kernelbäume; bei ihm wuchs dasselbe auf 208 GB und legte git lahm | `du` | 5 min lokal |
| 11 | Kein Boot-Logo bei lebendem MIPS (`init` statt `auto … logo`) | `hy310.env:45` | `logo-live` portieren, 1 h + Stromzyklus |

---

## 5 Was wir ihm zurückgeben können (fast kostenlos)

Seine vier offenen Punkte vom 12.09., mit unseren Antworten:

1. **"Vertical magnification does nothing."** Er schreibt `ratio_v = 0xC16C` und `phase_v = 0xE0B6`,
   lässt aber per Read-Modify-Write die **Modusfelder** `0x05180008[30:28]/[26:24]` auf den Unity-Werten
   4/3 stehen (`0x4300C000`). Nach unserer Formel (doku/93, `sub_8B1A56B8`) gehört zu `ratio_h = 0xC000`
   `mode_h = 3` und zu `ratio_v = 0xC16C` `mode_v = 2`; `mode_v = 3` heißt "Phase übergelaufen, Phase = 0",
   genau der Zustand, in dem eine geschriebene V-Phase folgenlos bleibt. Vorhersage:
   `0x05180008 = (alt & ~0x77000000) | (3<<28) | (2<<24) | ratio_h`. Schreibtischarbeit, und für uns eine
   Gegenprobe der eigenen Formel.
2. **Die Scherung schmaler Quellen bei 1280 Pixel Zeilenlänge** ist unser K3/S6/S7-Befund: ohne
   `UpdateWce` baut niemand die Fensterkette um; der Auslöser ist die Neuveröffentlichung des
   VidDec-Deskriptors mit geänderter Geometrie (`0117`), wobei die Fensterwörter 28/30/32/34 auf
   **Panelgröße** bleiben müssen (`0120`), sonst staucht `CalcPropRect` die Aufnahme auf 853x480 - exakt
   sein 852x480-Compositionzustand vom 06.09. Sein §5 ("`0x020` und `0x030` aus zwei Strukturen") ist der
   Anfang derselben Antwort.
3. **`0x05600024` ist keine "undecoded constant"**: 16x16-Blockzahl minus eins, `0x002C004F` = (720/16-1)<<16 |
   (1280/16-1); bei 1920x1080 `0x00420077` (doku/86 §2.1, Zeile 108, zwei Messpunkte).
4. **`0x05600030/48/4c` sind nicht "source 1's copies"**: `+0x048` Luma-Crop-Fenster `(h<<16)|w`, `+0x04C`
   Chroma-Crop mit halber Höhe, beide von unserem Treiber geschrieben; `+0x030` gehört der Firmware.
5. Dazu: der Chroma-Gain ist `floor(Wert * 1,28)` und identisch mit `SetSaturation` (doku/86 §2.1), sein 0x4C =
   Sättigung 60; und `0x05180000` kann bei uns beide Achsen (1280x720 -> 1920x1080, `0x3200AAAA`, Bildbeleg doku/93).

Seine HDMI-IN-Sackgasse, die sein ganzes Projekt umlenkt (Bericht C §8):

6. **Der ARISC-HDMI-Weg ist user1 Port 0** (`MSG_DATA 0x03003470`, `FIFO_STAT 0x03003460`), nicht Port 3. Port 3 ist
   der Standby-Dispatcher und antwortet auf alles Fremde mit `-3` - deshalb sah er die EDID-Handler als "hollow by
   design". Sie sind vollständig funktionsfähig (doku/68, doku/82).
7. **Die ARISC-Firmware lädt aus dem Kernel** (`0091`): Takt-Bits in `0x07010110/0114/0118`, Reset `0x07000400`
   Bit 0, die ersten `0x23000` Byte wortweise nach `0x00100000` (ARM-Adresse = ARISC-Adresse + `0x100000`; SRAM A2
   beginnt erst bei `0x00104000`, seine Suche lag im falschen Fenster), `struct arisc_para` nach `0x00104008`,
   Reset setzen. Der Startup-Handshake (Notify auf ARM-RX ch3, Typ `0x90`, quittieren auf user1 Port 3) ist Pflicht,
   sonst blockiert die Firmware ~100 s.
8. **`0x07091014` ist ARM-lesbar, sobald die ARISC den Block initialisiert hat** (`ResetEDIDModule`): danach liest
   es `0x07`. Der Hänger war der uninitialisierte Block, nicht "nicht ARM-adressierbar". Sein Ergebnis (ARISC nötig)
   stimmt, seine Begründung nicht.
9. **Die EDID-Sequenz, die an einem fremden Laptop HPD und EDID erzeugt** (doku/82): `0x2011 ResetEDIDModule` ->
   `0x0011 HostHDMIMAP 0,1,2` -> `0x0311 SetEDIDVersion 2` -> `0x0111 UpdateEDID` Fragmente 0..7 (beide Blöcke, nur
   Fragment 7 setzt das Fertig-Flag) -> `0x0215 CheckEDIDUpdateStatus` -> `0x0315 RequestEDID` -> `0x0511
   SetEDIDAudioMode` -> `0x0411 SET5VFlag 1` -> `0x0211 PullHotPlug 2` -> 10 s -> `PullHotPlug 1`. `PullHotPlug` ist
   zweistufig und selbstprüfend (Zähler 84 -> 1 -> 0).
10. **`GIC_SPI 21` ist die S/PDIF-Leitung**; die Msgbox-RX liegt auf `GIC_SPI 46` (GICv2 78). Sein hrtimer-Poll ist ein
    Umweg um dieses DTS-Problem.
11. **Zwei Defekte stecken noch in seinem `0014`** und treffen ihn, sobald Rückrufe fließen: der zweite Leser auf dem
    NewCall-Ring des MIPS (unser `0105`) und die fehlende Slot-Rückgabe nach Callbacks (unser `0124`; nach 19
    Rückrufen hängt die Firmware). Dazu der SMM-Heap: sobald er `SetSource(3/4)` (HDMI) probiert, trifft ihn unser
    Absturz (`sgp_hal_signal_info` NULL, doku/74); der Fix ist ARM-seitig, Heap vor der MIPS-Freigabe anlegen.
12. Sein offener Punkt "whether the second reg range at 0x02031000 is required": ja, es ist der I2S-Empfänger am DAC
    und der ganze HDMI-Audio-Weg (`0135`/`0135b`).

Das gehört in die PR-/Issue-Liste aus doku/116 (R6, Rückgabe an cstenger), nicht heute. Eine PR gegen seinen Baum
lohnt bei cpu_comm nicht (3194 Zeilen Abstand); eine kurze faktische Antwort mit den Punkten 1-4 und 6-11 schon.

---

## 6 Empfehlung, in Reihenfolge

Nichts davon ist dringend; der Melder aus Issue #1 und die geräteseitigen Werkzeuge (doku/61, 15.09.)
gehen vor. Wenn Marco die Richtung "Medienwiedergabe wie Stock" will, ist Paket 3 der Einstieg.

| # | Paket | Umfang | Aufwand | Gerätetest |
|---|---|---|---|---|
| 1 | **Hygiene** (§4 Nr. 1-8, 10): `0040` raus, drei `0013`-Korrekturen als `0013a`, aic8800 `0008`-`0010`, `MAGIC_SYSRQ` in den Release-Kernel, doku/89/62/93/96 nachtragen, Build-Cache ausmisten | Serie, Doku | ein halber Tag | ein Bau + ein Kaltstart (SysRq am Gerät prüfen, WLAN wie gehabt) |
| 2 | **Werkzeuge holen**: `block-map.py`, `block-survey.py`, `vtables.py`, `cfg.py` nach `tools/`; `--wait-for-power-cycle`-Idee in unsere `uart-*.py`; sieben Workflow-Lehren (§7 des Berichts D) ins Journal | Host-seitig | 2-3 h | keiner |
| 3 | **Dekodieren ohne Anzeige**: libva-Patches `0004`-`0007` + `build-va-driver.sh` + Gates (`va-decode-test.sh`, `hevc-decode-test.sh`, `make-test-streams.sh`, `check-video-stack.sh`); Video-Laufzeit als **optionales** Rootfs-Profil (nicht ins 228-MiB-Standard-Rootfs, doku/107) | Userspace, keine Kernel-Änderung, kein Konflikt mit dem Bildpfad | 2-3 Tage | Dekodierung bitexakt am Gerät |
| 4 | **Anzeige dekodierter Frames**: mpv `--vo=drm --hwdec=vaapi` auf unsere NV12-Plane (`0078`/`0078a`) mit lebendem MIPS - unser Deskriptor-Weg statt seines DECD-Wegs; seine mpv-Patches `0001`-`0003` als Vorlage | Design nötig (Plane teilen mit HDMI-Ring, Audio über den Codec-DAC) | 1 Woche, unsicher | ja, mit Stromzyklen |
| 5 | `logo-live` in unseren U-Boot (Boot-Logo mit lebendem MIPS) | 5 Zeilen `h713_mips.c` | 1 h | ein Stromzyklus |
| 6 | Rückmeldung an cstenger (§5: vier Display-Punkte, ARISC/HDMI-IN-Weg, zwei cpu_comm-Defekte) | Text | 1-2 h | keiner |
| 7 | Doku-Nachträge aus Bericht C: doku/71 (tvtop IRQ 110/PB5), doku/75 (`0x050c0000` nur `0x0d00`), doku/63/98 (Event-8, `a1`-Puffer, KSEG0-Kohärenz) | Doku | 1 h | keiner |

**Nicht übernehmen:** `0080`, `0095`, `0096`, `0097`, `0098`, `0099`, `0100`, `0057`, `0062`, `0074`, seine
DECD-Werkzeuge, `event8-*`, `mips-shell.py`, `flash-standalone.sh`, `split-udisk.sh` (nur die 26-Einträge-Regel).

---

## 7 Zurückgenommene Behauptungen aus seinem Baum (nicht nachbauen)

"Direct YUV scanout works" (12.08.); "der 28-fps-Deckel ist der Prozessübergang" (uncached CMA-Lesen war
es); "`cedrus_stop_streaming()` hält die VE nicht an" als Korruptionsursache (`0040`; es war 1416 MHz); "ein
Timeout wedgt die VE"; "Main10 dekodiert nicht"; "mpv braucht einen Render-Node"; "vo=drm ist verifiziert"
(Panel war schwarz, Log grün); "a DECD submit breaks the display path"; "the AFBD counters are frozen";
"MIPS to scanout" (Ausgabe korrupt); "die IOMMU-Übersetzung ist der Fehler" (Testskript ohne `0x05600014`);
"Composition ist die Ursache" (852x480 selbst verursacht); "der Panel-Down-Scaler ist tot" (Zweig invertiert,
`[26:25]=3` ist Bypass); "drei Blöcke, drei Nullergebnisse" (zwei davon RGB-Pfad nach Software-Fallback);
"`PanelWinNode::update` programmiert den Composition-Scaler" (es ist `NRWinNode`, und es sind keine
Verhältnisse); "`H264JudgeScaleMode`" (erfundenes Symbol); "die 60-Hz-Hard-Lock reproduziert nicht"; der
erste dma_buf-Leckfix (NULL-Slots -> Nulladressen im Ring); "Selektor 6 verursacht die Aussetzer".

Sein Muster, das auch unser Journal kennt: ein Null-Ergebnis zählt erst, wenn der Reiz nachweislich die
Hardware erreicht hat ("A register file latching values is not proof the logic behind it exists"; die 16
sauberen Nullen des ersten SDROT-Sweeps kamen von den falschen Registern).

---

## 8 Entscheidung und Umsetzung (15.09.2026, nachmittags)

Marco: "mach genau das" - Hygiene-Paket und Werkzeuge jetzt; Dekodieren, DECD und Abspielen sind ein spaeteres
Ziel ("klar wollen wir am Ende auch decoding decd und das abspielen, aber fuer den jetzigen Punkt ist alles okay").
Sein Anliegen war der Abgleich selbst: fehlen uns Patches, muss etwas nachgepatcht werden.

### 8.1 Was uns betrifft, was nicht, wo wir noch nicht sind

| Befund aus seinem Zweig | Betrifft uns | Stand |
|---|---|---|
| `0040` in unserer Serie (Deadlock bei parallelen Dekodern) | **jetzt** | erledigt 15.09.: aus der Serie nach `zurueckgenommen/`, README dort |
| drei Korrekturen in `0013` (decd): `blue_en`-Register, Recycle-Lock, `slots[1]` | **jetzt**, schlafend (decd bindet nicht) | erledigt 15.09.: `0013a`, Quelltext nach 0013a byteidentisch mit seinem Zweig (diff -r) |
| aic8800 `0007`/`0008`/`0009` (Logspam, `rc_stat`-Queue + OOB, Phantom-Makro) | **jetzt** | erledigt 15.09.: unsere `0008`-`0010`, byteidentisch, README-Tabelle vervollstaendigt (0006/0007 fehlten) |
| `MAGIC_SYSRQ` im Release-Kernel | **jetzt** | erledigt 15.09.: drei Zeilen im Shipping-Defconfig; Geraeteprobe (`echo h > /proc/sysrq-trigger`, BREAK am UART) beim naechsten Einspielen |
| Doku-Korrekturen (doku/89, 62, 93, 96, 71, 75, 63, 98) | **jetzt** | erledigt 15.09., je ein "Nachtrag 15.09.2026" |
| vier MIPS-Analysewerkzeuge | **jetzt** | erledigt 15.09.: `re/cstenger-tools/` mit README und Rauchtest; **nicht ins Repo**, sein Baum hat keine Lizenz |
| `tools/serial`-Ideen (`--wait-for-power-cycle`, BREAK) | spaeter, klein | offen (doku/61) |
| `h713_disp logo-live` (Boot-Logo mit lebendem MIPS) | **jetzt**, auf Marcos Wunsch | U-Boot-Teil erledigt 15.09. als `h713_disp init … logo` (Fork `44817b2`, nicht sein logo-live: kein DE-Replay, Logo vor Panel-Power), doku/40 Schlussabschnitt; Gerätetest 15.09. bestanden (drei FEL-Läufe, Logo gesehen); offen Installer-Teil und bootcmd (doku/61) |
| Build-Cache `mainline/build` 25 GB | lokal, nicht Repo | offen: nur nach Rueckfrage loeschen (alter Arbeitsbaum, GUT-Staende und `modroot.*` liegen daneben) |
| Rueckmeldung an cstenger (§5) | spaeter, gehoert zu doku/116 R6 | offen; Text ist §5, nichts gepostet |
| libva `0004`-`0007`, Gates, `build-va-driver.sh`, Video-Laufzeit im Rootfs | **noch nicht an dem Punkt** | Ziel steht (Dekodieren, Abspielen wie Stock), Reihenfolge in §6 Paket 3 |
| mpv-Patches, Anzeige dekodierter Frames auf unserer Plane, DECD mit lebendem MIPS | **noch nicht an dem Punkt** | braucht eigenes Design (§6 Paket 4); seine `0095`/`0096` sind dann Vorlage, nicht Patch |
| `0097`/`0098`/`0099`/`0100` (1080p auf 720p) | **nie** | 720p-Panel; fuer 4K-Quellen waere `0099` (VE-Halbierung) die Vorlage |
| `0080` (Display an den IOMMU) | **nie** in dieser Form | kollidiert mit unserer Probe und dem firmwareeigenen Capture-Ring |
| `0057`/`0062`/`0074`, Debug-Patches, `WIP-0007` | **nie** | bei ihm selbst out of series |
| `ring_writes_max`, Parked-MIPS-Rezepte, event8-Flash | **nie** | Folgen seines Aufbaus (MIPS geparkt, 0071-0073 fehlten im Bau) |
| "Formatbyte muss 3 sein" | **nicht ohne Messung** | widerspricht unserer A/B (doku/86 §3) |

### 8.2 Bau und Nachweis

Kernel- und aic8800-Bau aus `umbau/src` im Container (`build/build.sh kernel`, `build/build.sh aic8800`,
Board hy310), Installer-Testsuite, Sperr-Scan: Ergebnis siehe Nachtrag unten. Geraetetest: der naechste
Einspielvorgang (Marco), kein eigener Zyklus fuer dieses Paket.

**Nachtrag 15.09., 16:2x - Bau und Tests.** Kernel und aic8800 aus `umbau/src` im Container gebaut
(`umbau/build/logs/hygiene-20260915-kernel-aic8800.log`): 135 Serienpatches ohne Fuzz angewendet, `h713-kernel.fit`
(7,6 MB), `.config` traegt `MAGIC_SYSRQ=y`, `_SERIAL=y`, `_DEFAULT_ENABLE=0x1`; `sunxi-decd.ko` (65 KiB) aus dem
korrigierten Quelltext (`decd_hw.c:260` liest `workaround + 5`, `decd_types.h:215` hat `repeating`);
`aic8800_fdrv.ko` (843 KiB) aus einem Baum, in dem `CONFIG_DEBUG_FS_AIC` nicht mehr vorkommt (0 Treffer). Die zwei
Compiler-Warnungen im Log (`rwnx_main.c:1129`, doppelte Klammern um `==`) sind Vendorcode und alt.
Installer-Suite `installer/tests/run.sh`: OK, 121 Tests, 39 uebersprungen, 0 FAIL. `release/sperr-scan.py .`: keine
harten Funde. Der Geraetelauf fehlt noch (SysRq-Banner, WLAN wie gehabt); er gehoert zum naechsten Einspielen.

## Nachtrag 22.09. - Delta seit b54adaf (nur gesichtet, nicht geprueft)
Klon ohne Blobs unter `analyse/cstenger-abgleich-20260922/repo`. `h713-display-video-path` steht bei a861df2
(16.09., 23:59 PDT), 32 Commits ueber b54adaf, alle vom 15./16.09., danach nichts mehr. Inhalt: Cedrus H.265
Hardware-Skalierung ueber den VE-Polyphasen-Scaler (VE+0xf00, eigene Koeffizienten, ENUM_FRAMESIZES, 10-bit
Rekonstruktionspuffer), Compliance-Fixes (H.264 ref-index-Bounds-Backport, V4L2_CID_ROTATE inert, Requests ohne
per-frame-Controls abgelehnt), gstreamer/mpv/libva-Patches, Werkzeuge; dazu sechs neue drm-h713-Patches 0100-0111
("small source": Proc-Skalierung eines Fensters des nativen Rasters, Integer-Phasen, Input-Route-Fenster) fuer sein
720p-Board. 73 Dateien, +10174 Zeilen. **GPU/Panfrost/IOMMU: nichts.** Neuer Zweig `wip/crypto-ce-tooling` = ein
Commit vom 24.07. (CE/RNG-Testwerkzeug, "parked, not for merge"), ohne Bezug. U-Boot-Fork unveraendert (76eef86).
Fuer die Keystone-Kette (KS0) ohne Belang; die Cedrus-Fixes sind Kandidaten fuer "Dekodieren/Abspielen spaeter".
