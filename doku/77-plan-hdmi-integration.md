# HDMI-Eingang: Integrationsplan — Kernel, Userspace, Zwischenschritte, PQ

> **Erledigt (Stand 08.09.2026):** dieser Plan ist abgearbeitet und am Gerät abgenommen; was davon abweicht und was übrig blieb, steht in [`00-STATUS.md`](00-STATUS.md) §4 und [`60-offen.md`](60-offen.md). Das Dokument bleibt als Planungsstand und Begründung.

**Stand 06.09.2026, 19:35.** Voraussetzung ist der heutige Befund (doku/75, doku/76): Erkennung über die ARISC,
Capture live im DRAM, Bild auf der Wand über AFBD Source 0. Alles davon läuft heute mit Skripten und
Registerzugriffen aus dem Scratchpad. Dieses Dokument legt fest, **wo jeder Baustein hingehört**, damit es sich
am Ende anfühlt wie ein normales Linux-Gerät mit HDMI-Eingang — und nicht wie ein Labor.

## 0. Der Maßstab: „natürlich anfühlen"

Unter Linux hat ein HDMI-Eingang eine feste Gestalt, und die ist nicht die eines Daemons mit Socket:

- Der Empfänger ist ein **V4L2-Capture-Gerät** (`/dev/videoN`), so wie jede HDMI-Capture-Karte und jeder
  HDMI-RX-Chip im Kernel (tc358743, adv7604, Rockchip HDMI-RX). Dort gibt es die richtigen Begriffe schon:
  `VIDIOC_S_EDID`/`G_EDID` für das EDID, `QUERY_DV_TIMINGS` für das erkannte Signal, `V4L2_EVENT_SOURCE_CHANGE`
  für Stecken/Ziehen und Signalwechsel, Standard-Controls für Helligkeit/Kontrast/Schärfe, dma-buf-Export der
  Frames.
- Die Anzeige ist eine **KMS-Plane** mit dem Pixelformat des Empfängers; der Weg vom Capture-Puffer zur Plane ist
  ein dma-buf-Import ohne Kopie. Das ist genau der Weg, den cstenger für dekodiertes Video schon gebaut hat
  (NV12-Plane auf Source 0, drmprime-mpv). Sein Satz dazu passt wörtlich: *„Treat the MIPS as a frame producer
  writing into a buffer we scan out."*
- Gamma und Farbtemperatur sind **KMS-Eigenschaften** (`GAMMA_LUT` am CRTC), nicht `/dev/mem`-Pokes.
- Das „Umschalten auf HDMI" ist damit kein Firmware-Ritual, das ein Daemon nachspielt, sondern: Capture-Gerät
  öffnen, Frames auf die Plane legen. Ob das ein Vollbild-Player (`mpv --hwdec=drm av://v4l2:/dev/video1`), eine
  GStreamer-Pipeline oder ein 300-Zeilen-Programm ist, entscheidet der Nutzer; das Gerät zwingt nichts auf.

Alles, was heute an Skripten existiert, wird an diesem Maßstab einsortiert: entweder es wird ein Kernel-Baustein
mit Standard-Schnittstelle, oder es bleibt Werkzeug für die Diagnose.

## 1. Die Zwischenschritte — was auf Stock wer tut, und wohin es bei uns gehört

| # | Schritt | Stock: wer | Heute bei uns | Ziel |
|---|---|---|---|---|
| 1 | MIPS starten, SMM-Heap, TSE/PQ-Datenbanken laden | Vendor-U-Boot | **U-Boot** (`h713_mips.c`, Heap-Fix 07.09.) | bleibt in U-Boot |
| 2 | ARISC laden, Startup-Notify quittieren | Vendor-BL31 + Kernel-ARISC-Treiber | Prep-Skript + `hy310-arisc-hdmi.ko` (Quittung seit 06.09.) | **Kernel**: ARISC-Treiber lädt Firmware selbst (`request_firmware`), quittiert, übernimmt Port 3 |
| 3 | HDCP-2.2-Schlüssel in den MIPS | Android-HAL beim Start | `hdmi_seq.py` Phase 3 | **Kernel**: HDMI-RX-Treiber lädt `/lib/firmware/hdcp_v22.bin` beim Probe |
| 4 | `Vp_Init`, Callback-Registrierung, 12 Init-Aufrufe (PQ-Defaults, Wce_SetWindow, PortMap, HPD-Intervall) | Android-tvserver | `hdmi_seq.py` Phase 2/3 | **Kernel**: HDMI-RX-Treiber beim Probe, über die In-Kernel-API von `cpu_comm` |
| 5 | EDID beider Versionen hochladen, Port-Map, Audio-Mode, 5-V-Flag | Android-HAL → ARISC | `arisc_edid_init.sh` | **Kernel**: ARISC-Treiber; EDID aus `/lib/firmware/hy310-edid.bin`, änderbar per `VIDIOC_S_EDID` |
| 6 | HPD setzen, nach Boot und beim Stecken | ARISC-Firmware auf 5-V-Detect + HAL-Befehl | `PullHotPlug` per Skript | **Kernel**: ARISC-Treiber meldet Zustand als `SOURCE_CHANGE`; Hot-Plug ohne Neustart ist Pflichtliste #3 |
| 7 | `SetSource(HDMI)` | tvserver beim Quellenwechsel | `hdmi_seq.py --phase 4` | **Kernel**: `VIDIOC_S_INPUT` bzw. beim Öffnen des Capture-Geräts |
| 8 | Signalerkennung, Fensterrechnung (WCE) | MIPS intern | läuft (elog) | bleibt MIPS; der Kernel liest `SignalChange`-Callbacks und meldet `DV_TIMINGS` |
| 9 | VidDec-Descriptor (`0x05600098`), damit die Zustandsmaschine freigibt | Vendor-decd (`dec_reg_set_address`) | `viddec_descriptor.py` | **Kernel**: der KMS-Treiber schreibt ihn beim Aktivieren der Video-Plane (er beschreibt das Frame-Format) |
| 10 | Capture-Ring → AFBD Source 0 → Panel (RGB aus, Slots, Gain, Latch, Selektor) | Vendor-disp2/decd | `afbd_source0.py` | **Kernel**: KMS-Video-Plane (cstenger 0078 als Basis), gespeist aus dem Capture-Ring |
| 11 | PQ: TNR/SNR/DCI/BlackExtension/PictureMode/Backlight | tvserver + libtvpq über cpu_comm | Init-Defaults in Phase 3 | **Kernel** V4L2-Controls (Standard + Custom) im HDMI-RX-Treiber; Presets im Userspace |
| 12 | PQ: Gamma-LUT, Weißabgleich | libhaldisplay direkt in DE2 (`0x051C00E8`, `0x05208000`) | nichts | **Kernel**: `GAMMA_LUT`/`CTM` am CRTC im KMS-Treiber |
| 13 | Audio des HDMI-Eingangs | MIPS (APLL/AEC) + tvserver | nichts | später; ALSA-Capture-Gerät über den I2S-Weg, eigenes Kapitel |

Die Spalte „Ziel" hat eine einzige Regel: **Firmware-Orchestrierung gehört in den Kernel, Nutzerentscheidungen
in den Userspace.** Kein Daemon, der Registerfolgen nachspielt.

## 2. Kernel-Ebene

### 2.1 `hy310-arisc-hdmi` → `sun50i-h713-arisc` (Firmware-Loader + HDMI-Dienste)

Heute: debugfs-Werkzeug mit Hotplug/Probe/Unstick und (seit heute) der Startup-Quittung. Ziel:

- Probe: ARISC-Firmware per `request_firmware("arisc-tv303.bin")` laden, Reset lösen (heute
  `arisc_load.py` im Prep), Notify auf ch3 lesen, auf Port 3 quittieren. Damit entfällt Prep-Schritt 1 und der
  100-s-Stillstand ist konstruktiv ausgeschlossen.
- HDMI-Dienste als In-Kernel-API für den HDMI-RX-Treiber: `arisc_hdmi_reset_edid()`, `arisc_hdmi_set_edid(port,
  block, data)`, `arisc_hdmi_set_portmap()`, `arisc_hdmi_hpd(port, up/down/reset)`, `arisc_hdmi_5v(port, on)`,
  `arisc_hdmi_audio_mode()`. Die Rahmen gehen heute über user1 Port 0 **mit** Doorbell-Puls
  (`arisc_send.py`: `MSG_DATA` schreiben, `TX_IRQ_EN 0x03003430` Bit 7 ~10 µs pulsen). **Korrektur 07.09.:**
  Die frühere Fassung dieses Absatzes behauptete, der Puls sei entbehrlich, „die ARISC pollt, 3/3 belegt" —
  **dafür gibt es keine Fundstelle.** Belegt ist nur eine Empfangs-Warteschleife für **Port 3**
  (`re/notes/arisc-firmware__b7da2fb9.md`: `0x07970 msgbox-recv polling loop (sub0 port 3 FIFO_STAT)`), also für
  den Notify-/Quittungskanal; für Port 0 ist nichts gemessen, und `arisc_send.py` dokumentiert die Msgbox
  ausdrücklich als flankengesteuert. Pflichtliste #2/#8 bleibt damit **offen**; Paket B darf den Puls erst
  streichen, wenn die Messung unten ihn widerlegt.
- Antworten (Status, RequestEDID) über ARM-RX ch1 mit Wartezeit; Fehler nach oben, nicht still.
- Was **weg** kann: `main_loop_alive`/`unstick`/`hpd_delay` — Diagnosen für Symptome, deren Ursache
  (Startup-Handshake) jetzt bekannt ist. Bleiben darf ein `status` in debugfs.
- Offen und zu belegen: die ARISC-Reaktion auf 5-V-Detect (steckt der Nutzer nach dem Boot, muss der Kernel
  nichts tun, oder muss er `PullHotPlug` nachziehen?). Messung: Kabel ziehen/stecken bei laufendem Treiber, elog.

### 2.2 Neuer Treiber `sun50i-h713-hdmirx` (V4L2)

Der Kern des Plans. Ein V4L2-Videodevice, das die MIPS-Seite kapselt:

- **Probe:** `cpu_comm`-Kanal holen (In-Kernel-API, siehe 2.4), HDCP-2.2-Schlüssel laden, `Vp_Init` mit
  Staging-Bereich, Callbacks registrieren (SignalChange, HotPlugByPort, SignalValid, AVI/SPD/VSI-Pakete),
  die 12 Init-Aufrufe in Stock-Reihenfolge, Port-Map, `Wce_SetWindow` (auch wenn der RPC ein No-op ist: Stock
  ruft ihn), `HDMI_SetHPDTimeInterval`. Alles, was heute `hdmi_seq.py` Phase 2/3 tut, als eine Funktion mit
  Rückgabewerten.
- **EDID:** `VIDIOC_S_EDID` schreibt beide Blöcke über den ARISC-Treiber (Fragmente 0..7, plain), `G_EDID` liest per
  `RequestEDID` zurück. Default beim Probe aus `/lib/firmware/hy310-edid.bin` (heute schon dort).
- **Eingänge:** ein `V4L2_INPUT` je HDMI-Port (Stock kennt drei, das Gerät hat eine Buchse = Port 0);
  `VIDIOC_S_INPUT` → `SetSource(3+port)`.
- **Signal:** `SignalChange`-Callback (kommt heute über `cpu_comm_user`) wird im Kernel verarbeitet: Signal-Info
  (1920×1080, 60,00 Hz, RGB 12 Bit — heute belegt) → `V4L2_DV_TIMINGS`, `V4L2_EVENT_SOURCE_CHANGE`; kein Signal →
  Event mit Resolution-Change-Flag.
- **Frames:** Der Capture-Ring ist Firmware-Eigentum (drei Y-/drei C-Puffer, von der MIPS gedreht). Der Treiber
  exportiert die Slots als dma-buf (`VIDIOC_EXPBUF` auf einer `MMAP`-Queue über die reservierte Region) und liefert
  pro Vsync/Frame-Interrupt den aktuellen Slot als `DQBUF`. Format **NV16** (4:2:2, Chroma volle Höhe — Notiz vom
  04.07. und Capture-Register `+0x968` mit 1080 Zeilen). Das ist der Punkt, an dem noch RE fehlt: **welches Ereignis
  sagt „Slot n ist fertig"** (INCAP-Interrupt? das Ring-Register `0x8fc/900`? der MIPS-Vsync?). Ohne das gibt es
  Tearing, aber Bild.
- **Controls:** `V4L2_CID_BRIGHTNESS/CONTRAST/SATURATION/HUE/SHARPNESS` auf die THal-RPCs (`SetBrightness`,
  `SetContrast`, `SetSaturation`, `SetHue`, `SetSharpness` — alle in der Routinenliste), dazu Custom-Controls für
  `TNR`, `SNR`, `DCI`, `BlackExtension`, `PictureMode`, `VideoRange`, `LowLatency`. Das ist die PQ-Schnittstelle,
  auf der der Userspace (Abschnitt 3) aufsetzt.

### 2.3 KMS-Treiber `sun50i-h713-afbd`: die Video-Plane

- cstengers Patches **0078/0079/0080** (Vollbild-NV12-Plane auf Source 0, kein vmap bei PRIME-Imports,
  IOMMU-Anbindung) übernehmen — sie fehlen unserer Serie (0063–0086 insgesamt). Das ist Voraussetzung, nicht Kür:
  sie enthalten die validierte Übergabe RGB ↔ Source 0 (exklusiver Mux, Selektor `0x051C006C`, Gain
  `0x05140508`, vier Slots, Dirty-Latch), die heute das Bild gebracht hat.
- Erweiterung um **NV16** (Chroma-Höhe `+0x04C`, Format-Bits `+0x010[14:8]`) — Stock liest die Capture nicht als
  NV12, sonst wären die Farben falsch; die genauen Bits sind aus `NRWinNode__WriteReg`/`AfbdConfigure` zu holen.
- Der **VidDec-Descriptor** gehört hierher: Er beschreibt das Frame (Magic, 1920×1080, Stride) und wird beim
  Aktivieren der Plane geschrieben, Zeiger in `0x05600098`; ohne ihn bleibt die Zustandsmaschine der Firmware auf 0
  und die DE-Kanäle zu (doku/76 §6). Das ist ARM-Pflicht, Stock tut es in decd.
- Ring statt fester Slot: Die Plane soll pro Vsync den Slot übernehmen, den der Capture-Treiber liefert
  (Page-Flip über die vier Slot-Register statt „viermal Slot 0" wie heute).
- **Gamma/Weißabgleich**: `drm_crtc_enable_color_mgmt()` mit `GAMMA_LUT` (512 Einträge à zwei 12-Bit-Werte in
  `0x05208000/0x05208800/0x05209000`, Steuerung `0x051C00E8`, RE in `hy310-pqd/BACKGROUND.md` §5) und `CTM` für
  die Farbtemperatur-Gains. Damit verschwindet der `/dev/mem`-Pfad des alten pqd vollständig.

### 2.4 `hy310_cpu_comm`: bleibt, bekommt eine In-Kernel-API

Heute: Char-Devices `/dev/cpu_comm`, `/dev/cpu_comm_fd`, Userspace-Zustellung der Callbacks (`cpu_comm_user.c`).
Ziel: dieselbe Zustellung zusätzlich als Kernel-Callback (`cpu_comm_register_handler(comp_id, fn)`), `CALL` mit
Rückgabewerten als Kernel-Funktion, damit HDMI-RX- und ARISC-Treiber ohne Userspace-Umweg arbeiten. Die
Char-Devices bleiben für Diagnose und für PQ-Werkzeuge, die direkt RPCs setzen wollen. Zu prüfen: Pflichtliste #6
(ACK-Pfad ohne Cache-Sync gegen Stock).

### 2.5 U-Boot

Bleibt wie heute (MIPS-Start, SMM-Heap, TSE/PQ-Datenbanken, Fabric-Routing). Neu zu belegen: ob U-Boot alle
PQ-Datenbanken lädt, die die MIPS beim Start vermisst („Can not get gamma LUT data", „mp_dci_data is NULL",
„Can not get PP …ModuleID"). Diese Fehler sind der PQ-Einstieg (Abschnitt 4).

## 3. Userspace-Ebene

Was übrig bleibt, wenn der Kernel die Firmware orchestriert, ist klein und gewöhnlich:

- **`hy310-tv`** (systemd-Dienst, C, wenige hundert Zeilen): wartet auf `SOURCE_CHANGE` des Capture-Geräts,
  legt bei gültigem Signal die Frames per dma-buf auf die KMS-Video-Plane, zeigt bei fehlendem Signal die
  Konsole/den Desktop wieder (RGB-Plane). Optional als GStreamer-Pipeline (`v4l2src ! kmssink`) — dann ist es
  gar kein eigenes Programm mehr. Der „HDMI-Switch" ist damit ein `systemctl start hy310-tv` bzw. ein Tastendruck
  der Fernbedienung, der genau das tut.
- **`hy310-pq`** (CLI + Konfigurationsdateien): liest die Stock-Presets (`tvpq.db`, `pq_picturemode.ini`,
  `pq_colortemp.ini`, `pqcontrol_config_setting.xml`), rechnet Gamma-Punkte zur LUT (die Interpolation aus
  `hy310-pqd` ist RE-belegt und übernehmbar) und setzt: V4L2-Controls für die MIPS-PQ, `GAMMA_LUT`/`CTM` über KMS.
  Kein Daemon, kein Socket; „Bildmodus Kino" ist ein Aufruf mit Argument, den ein Frontend anbinden kann.
- **Diagnose bleibt Diagnose:** `arisc_hdmi.py`, `hdmi_seq.py`, `wandcheck.py`, `viddec_descriptor.py`,
  `afbd_source0.py` bleiben unter `analyse/`, mit Verweis auf den Kernel-Baustein, den sie ersetzt haben.

### Was von den alten Userspace-Werkzeugen relevant ist

| Werkzeug | Relevant | Nicht übernehmen |
|---|---|---|
| `hy310-hdmird` | die RPC-Sequenzen (Boot-Init, Post-Signal), die Callback-Behandlung, das `Wce_SetWindow`-Argumentlayout, das HDCP-Laden — als **Referenz** für Treiber-Probe und `S_INPUT` | der Daemon selbst: Socket, `CALL_GAP_MS`-Drossel (Symptom des FreeCall-Pools), Post-Signal-Fallback-Timeouts, No-op-Callback-Stubs; der Kernel hält die Callbacks selbst |
| `hy310-pqd` | `tvpq.db`-Auswertung, Gamma-Interpolation (`CALCULATEGAMMA_RE_GUIDE.md`), DE2-LUT-Registerbeschreibung, die 34 Routinen-Stubs als Liste dessen, was die MIPS aufruft | `/dev/mem`-Gamma (→ KMS), der Daemon und sein Socket, die eigene RPC-Schicht (→ V4L2-Controls) |
| `h713_hdmi_input.c`, `sun50i-h713-hdmi-rx.ko` (Legacy-Kernel) | der 5-Phasen-PHY-Init und die Register-Karte als Nachschlagewerk | die direkte EDID-/HPD-Programmierung (Patch 0023) — der Stock-Weg ist die ARISC, heute belegt |

Beide Daemons sind C++ mit eigener RPC-Schicht; sie werden nicht portiert, sondern ausgelesen.

## 4. PQ — „die Qualitätsscheiße"

Was fehlt, ist dreierlei, und es hängt zusammen:

1. **Die Daten — gesichert am 06.09.2026.** Sie lagen bereits als `re/vendor/HY310/extracted/super.fex` vor
   (Android-Sparse → LP-Container). Entpackt nach `re/vendor/HY310/extracted/vendor_a/etc/`: `tvconfig/`
   (`tvpq.db`, `pq_picturemode.ini`, `pq_colortemp.ini`, `pq_factory_extern.ini` 592 KB,
   `pq_overscan_config.ini`, `pqcontrol_*_setting.xml`, `panel_config/panel_config.ini`, `portmap.cfg`,
   `HDMI_EDID_14/20.bin`, `tv_default.json`), `display/mips/` und `firmware/`. Aufs Gerät nach
   `/etc/hy310/tvconfig/`, nicht ins öffentliche Repo.

   **Was drinsteht und wie es auf die Hardware trifft** (06.09., am Gerät belegt):

   * `pq_picturemode.ini` und die Tabelle `Picture_Mode` in `tvpq.db` geben je Eingang (ATV/DTV/HDMI1–3/CVBS/
     VideoDec) und Bildmodus die **Benutzerwerte 0..100**: Helligkeit, Kontrast, Sättigung, Farbton, Schärfe,
     TNR, SNR, Farbtemperatur, Gamma, DCI, Schwarzdehnung, Backlight. Modi: `standard`, `cinema` (Kontrast 45,
     Sättigung 45), `vivid` (55/60), `game`, `computer` (Schärfe 0, alle Filter aus), `hdr`, `energy_saving`
     (Backlight 80).
   * `pq_factory_extern.ini` enthält je Eingang die **Umrechnungskurve** von Benutzerwert auf Hardwarewert, mit
     fünf Stützstellen bei 0/25/50/75/100. Für HDMI: Helligkeit `0,256,512,775,1023`, Kontrast
     `1196,1794,2392,3010,3588`, **Sättigung `0,48,96,145,192`**, Farbton `0,256,512,775,1023`, Schärfe
     `0,64,128,193,255`. Dazu die Tabellen für NR, CTI, SSR und die Farbmatrix (CM).
   * `pq_colortemp.ini` und `White_Balance_Mode`: Weißabgleich als Gain 0..1023 und Offset ±512 je Kanal — auf
     diesem Gerät durchweg `512/512/512` und `0/0/0`, also neutral.

   **Die Brücke zum Register.** Unsere Anzeige hängt heute an genau einem PQ-Register: dem Chroma-Gain
   `0x05140508`, Bits [23:16]. cstenger hat den Wert **am Stock-Gerät** charakterisiert (Commit `5718e4c`):
   `0x00`/`0x01` grau, `0x26` blass, **`0x4C` richtig**, `0xFF` übersättigt — eine lineare Sättigungs-Verstärkung,
   kein Freigabebit. `0x4C` entspricht dem Kurvenwert **96** für Sättigung 50, dem Wert aller Standardmodi. Damit
   ist der Maßstab bekannt, und die übrigen Bildmodi rechnen sich direkt aus:

   | Bildmodus | Sättigung | Kurvenwert | Register `0x05140508` |
   |---|---|---|---|
   | `cinema` | 45 | 86,4 | `0x14440000` |
   | `standard` / `game` / `computer` / `hdr` | 50 | 96 | `0x144C0000` |
   | `vivid` | 60 | 115,6 | `0x145C0000` |

   Am Gerät gemessen (06.09., 21:2x, bunter Zuspieler, Farbigkeit im Spiralbereich gegen die weiße Fläche als
   Referenz): cinema 31,0 — standard 33,1 — vivid 36,9, bei konstanter Weißfläche (27,1/26,6/26,5). Monoton,
   ohne Helligkeitsänderung — die Kurve trifft die Hardware. **Das ist der erste vollständige Weg von einer
   Stock-PQ-Datei bis auf die Wand**, und die Vorlage für `hy310-pq`: Bildmodus → Benutzerwert → Werkskurve →
   Register, ohne geratene Konstanten.
2. **Die MIPS-Seite.** Die Boot-Fehler „Can not get gamma LUT data", „mp_dci_data is NULL", „Can not get PP
   BlackExtension/NR/MpegNR ModuleID" bedeuten, dass PQ-Module in der TSE-Datenbank nicht gefunden werden.
   Kandidaten: U-Boot lädt `pq_custom` nicht oder an die falsche Stelle; die ProjectID-Tabelle passt nicht; oder
   Stock liefert die Daten erst per RPC (`SetWhiteBalance` mit Struktur, `SetGamma`). Messung: elog beim Boot mit
   Level 4 (jetzt möglich, `elog_tail.py`), `tools/tse_dump.py` gegen die geladenen Datenbanken.
3. **Der Weg für Einstellungen.** Standard-V4L2-Controls plus Custom-Controls im HDMI-RX-Treiber (2.2), Gamma/CTM
   im KMS (2.3), Presets im Userspace (3). Reihenfolge der Umsetzung: erst Daten sichern und die MIPS-Fehler
   verstehen (ohne Bild-Effekt keine Bewertung möglich), dann Gamma über KMS (sichtbar, messbar mit der Webcam),
   dann die RPC-Controls.

## 5. Arbeitspakete, Reihenfolge, Abnahme

> Ausgearbeitet zu Agenten-Aufträgen mit Eingaben, Schritten, Abnahme und Board-Protokoll in
> [78-nachtplan-hdmi-switch.md](78-nachtplan-hdmi-switch.md) (06.09., 21:40).

> **Überholt am 07.09. — diese Tabelle ist Planung, kein Abnahmestand.** Vier ihrer Kriterien tragen
> nicht mehr, und zwar an der Regel „ein Kriterium, das nicht scheitern kann, prüft nichts" (samt
> Spiegelbild):
>
> * **A** „NV12-Plane in `modetest` sichtbar" — `modetest` gibt es auf dem Board nicht
>   (`doku/79`, Widerspruch 5). Abgenommen wurde gegen die gelistete Plane `video-0` (ID 38) und einen
>   Gamma-Reiz.
> * **E** „`v4l2-ctl --query-dv-timings` meldet 1080p60" — der Wert ist in `0094` eine
>   **Übersetzungszeit-Konstante** (`V4L2_DV_BT_CEA_1920X1080P60`), die Fähigkeitsgrenzen klemmen
>   `min == max`; er wird bei jeder Quellauflösung gedruckt. **Kann nicht scheitern.**
> * **E** „`SOURCE_CHANGE` beim Stecken" — feuert nie, solange die Callback-Lücke steht.
>   **Kann nicht gelingen.**
> * **G** „Boot-elog ohne ‚Can not get …'" — die Meldung steht weiterhin da; G wurde gegen ein
>   **anderes** Kriterium abgenommen (Gamma-LUT bitgleich zum Legacy-Rechner, offline, kein Board).
>
> Die **I**-Zeile („`brightness` wirkt") ist dagegen **gültig geblieben**: Helligkeit wirkt, gemessen am
> 07.09. gegen dunkles Material, Stellbereich 0…100
> ([`nachtlog/I0-helligkeit-nachgemessen.md`](nachtlog/I0-helligkeit-nachgemessen.md)). Die zwischenzeitliche
> Auflage, `V4L2_CID_BRIGHTNESS` **nicht** anzubieten, ist damit hinfällig — sie stützte sich auf eine
> Messung gegen eine fast weiße Vorlage, die gar nicht anschlagen konnte.
>
> Der maßgebliche Stand steht in [`00-STATUS.md`](00-STATUS.md) („Stand je Paket") und
> [`60-offen.md`](60-offen.md); der jüngste operative in
> [`nachtlog/STAND-JETZT.md`](nachtlog/STAND-JETZT.md).

| # | Paket | Abnahme | Abhängigkeit |
|---|---|---|---|
| A | cstengers Serie 0063–0086 in unsere Serie übernehmen (`build.sh kernel`), auf dem Board booten | Konsole wie heute; NV12-Plane in `modetest` sichtbar | — |
| B | ARISC-Treiber: Firmware-Laden im Kernel, Quittung, HDMI-API; Doorbell **nur nach Messung** streichen | Kaltstart ohne Prep-Schritt 1; `status` zeigt Notify quittiert; EDID/HPD-Funktionen aus dem Kernel aufrufbar; Puls-Messung protokolliert | — |
| C | `cpu_comm` In-Kernel-API (Call + Callback-Handler) | HDMI-RX-Treiber kann `SetSource` rufen und `SignalChange` empfangen ohne `/dev/cpu_comm` | — |
| D | Video-Plane auf den Capture-Ring: NV16, Descriptor beim Enable, Slot-Flip | Bild wie heute, aber aus dem Treiber; Farben korrekt (Webcam gegen Laptop-Bild) | A |
| E | `sun50i-h713-hdmirx` V4L2: Probe-Sequenz, EDID, Inputs, DV-Timings, Events, dma-buf-Export der Slots | `v4l2-ctl --query-dv-timings` meldet 1080p60; `SOURCE_CHANGE` beim Stecken; `v4l2-ctl --stream-mmap` liefert Frames | B, C, Slot-Fertig-Ereignis (RE) |
| F | `hy310-tv`: Capture → Plane, Signalverlust → Desktop | Kaltstart, Laptop einstecken, Bild ohne Handgriff; Kabel ziehen → Konsole | D, E |
| G | PQ-Daten aus `super` sichern; MIPS-PQ-Fehler beim Boot klären | Boot-elog ohne „Can not get …"; Datenbestand dokumentiert | — |
| H | Gamma/CTM im KMS, `hy310-pq` mit Stock-Presets | Gamma-Wechsel messbar (Webcam), Presets umschaltbar | A, G |
| I | PQ-Controls im HDMI-RX-Treiber | `v4l2-ctl --set-ctrl=brightness=…` wirkt, elog zeigt den RPC | E |
| J | Pflichtliste abräumen: Hot-Plug nach dem Boot (Messung), FreeCall-Pool (kein Drosseln), ACK-Cache-Sync, `clk_ignore_unused` durch DT-Takte | jeder Punkt mit Beleg oder als Stock-Verhalten belegt | B–F |

A, B, C und G sind unabhängig und können nebeneinander laufen. Der sichtbare Meilenstein ist F.

## 6. Was dieser Plan ausdrücklich nicht tut

- Keinen Daemon, der die Stock-Sequenzen nachspielt. Das war der Legacy-Weg und ist mit seinen Drosseln,
  Fallback-Timeouts und Unstick-Tricks die Pflichtliste, die wir gerade abarbeiten.
- Keine `/dev/mem`-Pokes im Betrieb. Jeder Registerzugriff aus dieser Sitzung hat jetzt einen Kernel-Ort.
- Keine Übergabe des AFBD an die MIPS. Der Grund steht bei cstenger und ist heute bestätigt: Wer den Scanout
  besitzt, besitzt das Bild.

Belege für jede Zeile der Tabellen: doku/74 (SetSource), doku/75 (ARISC, EDID, Handshake), doku/76 (Zustandsmaschine,
Descriptor, Source 0), `legacy/userspace/*/BACKGROUND.md` und `README.md` (Stock-PQ-Fluss), cstengers
`docs/hdmi-in.md` und Patch 0078 (Video-Plane).
