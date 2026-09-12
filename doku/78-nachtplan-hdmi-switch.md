# Nachtplan: der HDMI-Switch als Teil des Systems — Aufträge für autonome Agenten

> **Erledigt (Stand 08.09.2026):** dieser Plan ist abgearbeitet und am Gerät abgenommen; was davon abweicht und was übrig blieb, steht in [`00-STATUS.md`](00-STATUS.md) §4 und [`60-offen.md`](60-offen.md). Das Dokument bleibt als Planungsstand und Begründung.

**Stand 06.09.2026, 21:40.** Grundlage: [77-plan-hdmi-integration.md](77-plan-hdmi-integration.md) (Architektur,
Maßstab „natürlich anfühlen"), [76-plan-ch0-de.md](76-plan-ch0-de.md) Abschnitte 10–13 (Bild und Farbe, Register,
Fallen), [75-handoff-20260907.md](75-handoff-20260907.md) (ARISC, EDID, Handshake, Rezepte). Dieses Dokument macht
daraus **Aufträge**, die ein Agent ohne Rückfrage ausführen kann. **Anhang A** (am Ende) beschreibt den
vollständigen Ablauf des Quellenwechsels — sieben Stufen, jede mit Werten, Prüfpunkt, Fehlerbild und der Stelle,
an der sie im Zielbild sitzt; wer an D, E oder F arbeitet, liest ihn zuerst. Es ist die einzige Quelle für die Nacht; wer
etwas nicht hier findet, sucht es in den verlinkten Dokumenten, nicht im Gedächtnis.

---

## 0. Regeln, die über allem stehen

Diese Regeln stammen von Marco und aus teuer bezahlten Fehlern dieser Woche. Sie sind nicht verhandelbar.

1. **Kein Workaround, kein Quirk.** Jede Lösung ist entweder das, was Stock tut (mit Beleg: Stock-Register,
   Stock-elog, Firmware-Disassembly), oder sie ist eine saubere Kernel-/Userspace-Implementierung einer
   Standard-Schnittstelle. Drosseln, Timeouts als Heilmittel, „einmal pulsen", `/dev/mem`-Pokes im Betrieb — nein.
   `legacy/docs/known-issues.md` ist die Pflichtliste: jeder Punkt wird gelöst oder mit Beleg als Stock-Verhalten
   gezeigt.
2. **Bauen nur im Container `h713-build`, nur über `build/build.sh`** (doku/50). Keine Host-Umgehungen, keine
   Einzel-kbuilds als Endstand (Diagnosemodule dürfen so gebaut werden, sind aber als solche zu kennzeichnen).
   Patches kommen in `mainline/patches/kernel/series` mit `diff -ruN`-Form wie die bestehenden.
3. **Das Board ist eine Ressource, nicht zwei.** Es gibt genau **einen Board-Agenten** zur Zeit (Abschnitt 6).
   Alle anderen arbeiten offline: Quelltext, Patches, RE, Dokumentation. Wer das Board braucht, stellt eine
   Anfrage in den Nachtlog und wartet, bis der Board-Agent sie einplant.
4. **Kaltstart ist der Normalfall.** Jeder Messlauf beginnt mit `sonoff_ctl restart --host 192.168.8.179`; nach
   einem Hänger nie auf Selbstheilung warten (kein Watchdog). Vor jedem Neustart prüfen, ob TFTP lauscht
   (`ss -ulnp | grep -w :69`); wenn nicht: **Stopp**, in den Nachtlog schreiben, nicht reparieren (braucht sudo).
5. **Kurze Schritte, harte Timeouts.** Jeder Board-Befehl mit `timeout` (20–60 s), nie minutenlang in einem Aufruf
   hängen. Ein Hänger wird sofort protokolliert, dann Kaltstart.
6. **Zwei Handgriffe sind verboten** (doku/76 Abschnitt 13): den VidDec-Descriptor mehr als **einmal** pro Boot
   schreiben; **INCAP-Register (`0x0694xxxx`) von Hand beschreiben**. Beides verstellt die Firmware und verklemmt
   die Capture; danach hilft nur der Kaltstart.
7. **Webcam-Belichtung nicht anfassen** (`analyse/hdmi-seq/cam_exposure.py` nur, wenn zwingend, und danach
   `auto`). Bilder ansehen, nicht nur Kennzahlen; Positivkontrolle vor jeder Negativaussage
   (Memory `messung-instrument-erst-pruefen`).
8. **UART/`tio` gehört Marco.** Nicht öffnen. Der Board-Zugang ist `ssh root@192.168.8.141` (NFS-Root, TFTP-Kernel),
   der Zuspieler `ssh user@192.168.8.162` (ThinkPad, HDMI-2, `DISPLAY=:0 xrandr`).
9. **Keine Passwörter, keine Schlüssel, keine Vendor-Binärdaten ins öffentliche Repo.** Kein `git commit`/`push`
   in Marcos Repos ohne ausdrücklichen Auftrag; Patches und Dokumente werden als Dateien abgelegt.
10. **Alles in den Nachtlog** `doku/79-nachtlog-20260907.md`: pro Agent ein Abschnitt, jede Board-Aktion mit
    Uhrzeit, jedes Ergebnis mit Beleg (Datei, Foto, Registerwert). Ein Agent, der scheitert, schreibt *warum*.

---

## 0a. Die Falle, die in dieser Nacht zweimal zugeschnappt ist (07.09., 22:15)

**Handänderungen in einem Baubaum überleben keinen Neubau.** Zwei Befunde des Nachtagenten, beide bestätigt:

1. Der DT-Knoten `tvcap@50c0000` stand in **keinem** Patch, sondern nur als Handänderung im alten Baubaum. Ohne
   ihn bindet `h713-tvcap` nie, TVFE/TVCAP bleiben stromlos, der **gesamte INCAP-Block liest `0x00000000`** und
   die Wand zeigt gleichmäßiges Grün (leerer Ring, Y=Cb=Cr=0). Nachgetragen als Patch `0096`.
2. Drei `cpu_comm`-Korrekturen lebten ebenso nur im Baubaum: kein `current->tgid` nach `+0x34` (das ist
   **Parameter 3**, nicht ein PID-Feld), `memset(routine_info)` plus `callwq_kernel_cb`-Riegel (die ROOT CAUSE
   aus doku/72: ein Sprung auf einen nie beschriebenen Funktionszeiger bei eingehenden MIPS→ARM-CALLs), und die
   richtigen Offsets im RX-CALL-Druck. Der Serienpatch `0014` enthält **keine** davon. Nachgetragen als `0097`.

Diese Klasse Fehler fällt nicht beim Bauen auf, sondern erst am Gerät — und beim zweiten Punkt nicht einmal
laut, sondern als stiller ABI-Fehler bei Aufrufen mit drei Argumenten. **Regel für die Nacht:** was am Gerät
wirkt, steht in `patches/kernel/` und in `series`. Wer eine Datei im Baubaum ändert, hat noch nichts geliefert.
Vor jeder Abnahme: `grep` die entscheidende Zeile im **Patch**, nicht im Baum.

---

## 0b. Die Umgebung — was ein Agent wissen muss, um nicht zu raten

| Was | Wert / Zugang |
|---|---|
| Arbeitsrechner (hier) | Linux Mint, `/opt/Projekte/h713`; Container `h713-build` (`podman exec h713-build …`, `/opt/Projekte/h713` = `/work`) |
| **Board** (HY310-Beamer, H713) | `ssh root@192.168.8.141` (Schlüssel, `-o BatchMode=yes -o ConnectTimeout=3`); Root-Dateisystem per NFS vom Arbeitsrechner, über SSH beschreibbar; Kernel per TFTP aus `/opt/Projekte/h713/tftp/` |
| **Strom / Kaltstart** | `sonoff_ctl restart --host 192.168.8.179` (immer mit `--host`); ~40 s bis SSH; Kaltstart an `/proc/uptime` prüfen. Kein Watchdog: ein hängendes Board erholt sich nie von selbst |
| TFTP-Server | `dnsmasq` auf dem Arbeitsrechner, Port 69; prüfen mit `ss -ulnp \| grep -w :69`; läuft er nicht, kann ihn nur Marco starten (sudo) — dann Nachtlog und **nicht** neu starten |
| UART | `/dev/ttyACM0` — **gehört Marco (`tio`), nicht öffnen** |
| **Zuspieler** | ThinkPad, `ssh user@192.168.8.162` (NOPASSWD-sudo), Ausgang **HDMI-2** am einzigen HDMI-Eingang des Beamers (Firmware-Port 0, `SetSource(3)` = HDMI-1); Befehle mit `DISPLAY=:0`: `xrandr --output HDMI-2 --off/--auto` (Quelle aus/an), `--gamma 1:0.2:0.2` (Farbstich als Reiz, `1:1:1` zurück), Verbindung: `cat /sys/class/drm/card0-HDMI-A-2/status` |
| Zuspieler-Bildinhalt | derzeit Firefox mit bunter Regenbogenspirale (otto.de-Seite); sperrt sich der Schirm, ist das Bild fast schwarz → `sudo loginctl unlock-sessions` versuchen, sonst Sperrbildschirm mit Gamma-Reiz nutzen (Uhr und Logo sind hell genug). Bildschirmschoner aus: `xset s off -dpms` |
| **Webcam** | am Arbeitsrechner, `/dev/video0`, zeigt die Projektionsfläche (Wand). Aufnahme und Kennzahlen: `python3 analyse/hdmi-seq/wandcheck.py shot NAME` (Bild + JSON nach `re/captures/weltneuheit/wand-aktuell/`, anderer Ordner per `WAND_DIR=…`; ROI 220,40,1090,560 = Projektion, in `roi.txt` dort); Vergleich `wandcheck.py diff A B`. **Belichtung nicht verstellen**; steht auf `auto` (`analyse/hdmi-seq/cam_exposure.py auto` stellt zurück). Bilder immer ansehen (Read), nicht nur Zahlen. Nachts ist der Raum dunkel — für die Projektion gut; Positivkontrolle: Testbild auf `/dev/fb0` oder Gamma-Reiz am Zuspieler, erst dann Negativaussagen. Firefox am Arbeitsrechner kann die Kamera blockieren |
| Projektion | Beamer wirft auf eine weiße Wand; Bild ist im Foto links/mitte, Lampe strahlt links über; Schwarz des Beamers ist grau. Ein Foto von Marco mit eingezeichnetem Bildrahmen: `re/captures/weltneuheit/ours-20260906-source0/fotos/` (Vergleich) |
| RE-Werkzeuge | IDA 9.1 idalib: `analyse/ida/README.md` (Datenbank-Kopie, Aufruf, Adressumrechnung, Skripte q22–q26). Stock-elog: `re/captures/weltneuheit/elog-stock-LIVE.bin` (`strings -n 8`), unsere elog-Zeilen am Board: `dmesg \| grep elog:` bzw. `/root/elog_tail.out` |
| Firmware-/Schlüsseldateien | ARISC-Blob `analyse/arisc/scp.bin` (am Board `/root/scp.bin`), Loader `analyse/arisc-loader/arisc_load.py`; HDCP `analyse/hdcp-keys/hdcp22-key-912.bin` (912 B, Shmem-Offset `0x36000` → phys `0x4E336000`), `hdcp14-key-320.bin`; EDID `re/work/weltneuheit/HDMI_EDID_14.bin` + `_20.bin` (am Board `/root/edid-send.bin`); MIPS-Firmware `re/vendor/HY310/extracted/vendor_a/etc/display/mips/display.bin`; **nichts davon ins öffentliche Repo** |
| Speicherkarte (DT) | `sun50i-h713.dtsi` `reserved-memory`: `mips_reserved` `0x4B100000` (Boot/Firmware/TSE, 0xE41000), **`mips_framebuf` 26 MB ab `0x4BF41000`** — darin liegen Capture-Ring (`0x4C3EF000…`) und Descriptor-Seite (`0x4D95F000`); `cpu_comm_reserved` (Shmem `0x4E300000`, Vp_Init-Staging `0x4E700000`); `framebuf_reserved` (unser Scanout `0x76D00000`, Patch 0049). Treiber binden sich per `memory-region` an diese Knoten, statt Adressen zu raten |
| Board-DTS | `sun50i-h713-hy200-qz713df-a1.dts` (cstengers Datei, Patch 0024) — unser Board fährt sie; Änderungen ins SoC-`dtsi`, kenntlich machen (doku/60) |
| Zeit | Board-RTC startet 1970/2026-04 (doku/60), Zeitstempel am Board sind unbrauchbar — Uhrzeit vom Arbeitsrechner protokollieren |

---

## 1. Was heute Abend gesichert ist (Grundwahrheit, nicht neu messen)

| Baustein | Stand | Beleg |
|---|---|---|
| MIPS-Start, SMM-Heap | U-Boot, geflasht; `SetSource(3)` ungefährlich | doku/74 |
| ARISC laden + Startup-Handshake | Prep-Skript + `hy310-arisc-hdmi.ko` (Notify ch3, Quittung Port 3) | doku/75 Nachtrag 15:25 |
| HPD/EDID über die ARISC | `arisc_edid_init.sh`: Reset → MAP → Version 2 → 8 Fragmente → Check → Request → AudioMode → 5V → HPD down 10 s → up; ThinkPad `connected`, EDID „SGD SX8" | doku/75 Nachtrag 14:55 |
| Capture | INCAP schreibt **NV16, YUV** (Cb/Cr um 128) in den Ring Y `0x4C3EF000/0x4C5EE000/0x4C7ED000`, C `0x4C9EC000/0x4CBEB000/0x4CDEA000`; Flip-Zeiger `0x05600320/324` drehen mit 60 Hz | doku/76 §12–13, `analyse/hdmi-seq/chroma_stat.py` |
| Zustandsmaschine | `viddec_descriptor.py set` (einmal!) → AppTop Zustand 4, Gate `0x2007c`, DE-Kanäle `0x05000178/1B8/278/2B8` Bit 31 | doku/76 §6, §8 |
| Bild | `afbd_source0.py on`: RGB-Kanal aus, vier Slots (Y/C/Info), Dirty, Gain `0x05140508=0x144C0000`, `0x10=0x03000013` + ready, Selektor `0x051C006C=0x39000000`, **C-Stride `0x05600044=0x0F00`** | doku/76 §10, §13 |
| Farbe | richtig seit 21:10; Sättigung an die Stock-PQ angeschlossen (`pq_saturation.py`) | doku/76 §13, doku/77 §4 |
| Robustheit | Zuspieler aus/an und PullHotPlug DOWN/UP: Bild bleibt, 0 strukturelle Registerunterschiede | `re/captures/weltneuheit/ours-20260906-source0/` |
| PQ-Daten | `re/vendor/HY310/extracted/vendor_a/etc/tvconfig/` (tvpq.db, pq_*.ini, xml, EDIDs, portmap) | doku/77 §4 |

**Die Board-Sequenz, die heute dreimal nach Kaltstart funktioniert hat** (alle Skripte liegen in `/root/` auf dem
Board und in `analyse/hdmi-seq/`):

```bash
sonoff_ctl restart --host 192.168.8.179                     # Kaltstart, ~40 s bis SSH
ssh root@192.168.8.141 'bash /root/prep_after_boot.sh'      # ARISC, cpu_comm, tvcap, arisc-hdmi, Phase 2+3
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource \
     --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3'
ssh root@192.168.8.141 'bash /root/arisc_edid_init.sh'      # ~30 s, enthält HPD down 10 s
sleep 6                                                     # Signal-Lock; INCAP 0x06940104 zählt 60/s
ssh root@192.168.8.141 'python3 /root/viddec_descriptor.py set'   # GENAU EINMAL
ssh root@192.168.8.141 'python3 /root/afbd_source0.py on'
python3 analyse/hdmi-seq/wandcheck.py shot NAME             # Foto; ROI 220,40,1090,560
```

Prüfpunkte: `python3 /root/dump_state.py NAME` (alle Blöcke), `python3 /root/chroma_stat.py` (Cb/Cr-Lage),
`python3 /root/afbd_source0.py show` (Register), `python3 /root/pq_saturation.py` (Sättigung).

---

## 2. Das Zielbild in einem Absatz

Der Kernel besitzt die Firmware-Orchestrierung: ein **ARISC-Treiber** (lädt Firmware, quittiert, bietet EDID/HPD
als Kernel-API), ein **V4L2-Capture-Treiber** `sun50i-h713-hdmirx` (Probe = Stock-Init, `S_INPUT` = SetSource,
EDID-ioctls, DV-Timings und `SOURCE_CHANGE` aus den Callbacks, die drei Ring-Slots als NV16-Puffer per
`DQBUF`/dma-buf), eine **KMS-Video-Plane** in `sun50i-h713-afbd` (NV16 auf Source 0, Descriptor beim Enable,
C-Stride 3840, Slot-Flip pro Vsync, Gamma/CTM als CRTC-Eigenschaften), und `cpu_comm` mit **In-Kernel-API**.
Der Userspace ist klein: `hy310-tv` legt Capture-Frames auf die Plane und fällt bei Signalverlust auf den Desktop
zurück; `hy310-pq` rechnet Stock-Presets in Controls und LUTs um. Kein Daemon, der Register pokt.

---

## 3. Aufträge (Arbeitspakete)

Jedes Paket hat: Ziel, Eingaben (Pfade), Schritte, Ergebnis (Dateien), Abnahme (Befehl + erwartete Ausgabe),
Board-Bedarf, Abhängigkeiten, Fallen. **Offline-Pakete zuerst und parallel**; Board-Zeit ist knapp und seriell.

### A — cstengers fehlende Patches übernehmen (offline, dann 1 Board-Slot)

**Ziel:** Unsere Serie `mainline/patches/kernel/series` enthält cstengers Display-/Video-Patches, damit die
Video-Plane (D) auf seinem validierten Code aufsetzt.

**Eingaben:** `mainline` Branch `origin/h713-display-video-path`; fehlende Patches (Stand 21:30):
`0051-iommu-sun50i-rate-limit-fault-reporting`, `0053-drm-panfrost-do-not-map-imported-buffers-cacheable`,
`0055-arm64-dts-h713-drop-the-1416-mhz-opp-it-corrupts-memory`, `0059-media-cedrus-do-not-disarm-the-watchdog…`,
`0063-drm-h713-afbd-give-userspace-a-well-formed-size-range`, `0064-arm64-dts-h713-put-the-kernel-console-on-the-panel-too`,
`0067/0071/0072/0073 misc-decd-*`, **`0078-drm-h713-add-fullscreen-nv12-overlay`**, **`0079-drm-h713-do-not-vmap-prime-imports`**,
**`0080-drm-h713-attach-the-video-plane-to-the-iommu`**, `0082–0086` (Audio). Unsere Patches, die er nicht hat:
`0040`, `0049` (Scanout-Carveout 1080p), `0050` (Audio-Codec — kollidiert inhaltlich mit seinen 0082–0086),
`0051-soc-sunxi-add-arisc-hdmi-hpd`.

**Schritte:**
1. `git -C mainline show origin/h713-display-video-path:patches/kernel/<name>` für jeden Patch nach
   `mainline/patches/kernel/` holen; Nummernkollisionen (unser 0051 vs. sein 0051) durch Umnummerierung **unserer**
   Patches auflösen (0051 → 0090 z. B.), `series` entsprechend.
2. Konflikte: 0049 (Carveout) gegen 0078/0080 (IOMMU, Plane-Größe) prüfen — die Plane liest den Ring physisch
   (doku/76 §10: IOMMU für den Display-Knoten nicht beteiligt); 0080 muss so übernommen werden, dass **ohne**
   `iommus`-Eigenschaft am Display weiter physisch gelesen wird. 0050 gegen 0082–0086: seine Fassung nehmen, unsere
   0050 fallen lassen, wenn sie dasselbe tut (Diff lesen, entscheiden, begründen).
3. `podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh kernel'` — muss durchlaufen. Neuer
   Baum unter `mainline/build/linux-6.18.38-<hash>/` (Hash aus `series` + Patches, `build/build.sh` Z. 47–70).
4. FIT/Netboot-Artefakt an den Board-Agenten übergeben (Pfad im Nachtlog; `tftp/` enthält die aktuelle FIT,
   Sicherung mit Datum anlegen, **nichts überschreiben**, was der Board-Agent gerade fährt).

**Ergebnis:** aktualisierte `series`, Patchdateien, Baubericht im Nachtlog.
**Abnahme (Board-Agent):** Kaltstart mit dem neuen Kernel, Konsole auf der Wand wie heute; `modetest -M sun50i-h713-afbd`
(oder der passende DRM-Name) listet eine zweite Plane mit `NV12`; die Sequenz aus Abschnitt 1 liefert das Bild.
**Fallen:** Sein 0078 nennt die Plane „NV12" und schreibt `+0x4C` mit halber Chroma-Höhe — das ist für Cedrus
richtig und für unsere Capture falsch (D kümmert sich darum). Nicht „schnell fixen" in A.

### B — ARISC-Treiber: Firmware-Laden, Handshake, HDMI-API im Kernel (offline, dann 1 Board-Slot)

*Ablauf: **Anhang A**, Stufen 2 und 4 (vollständige Befehlstabelle).*

**Ziel:** `hy310-arisc-hdmi.ko` wird `sun50i-h713-arisc`: lädt `arisc-tv303.bin` per `request_firmware`, löst den
Reset, quittiert das Notify, bietet `arisc_hdmi_*()` als Kernel-API; kein Doorbell-Puls, kein `unstick`, kein
`main_loop_alive`.

**Eingaben:** `analyse/arisc-hdmi-drv/arisc_hdmi.c` (heutiger Modulstand, Handshake drin), Patch
`mainline/patches/kernel/0051-soc-sunxi-add-arisc-hdmi-hpd.patch`; Referenzlogik in `analyse/arisc-msg/arisc_hdmi.py`,
`arisc_msg.py`, `arisc_send.py` (Rahmenformat, Sub-Commands `0x2011 ResetEDIDModule`, `0x0011 HostHDMIMAP`,
`0x0311 SetEDIDVersion`, `0x0111 UpdateEDID` 8 Fragmente à 64 B plain, `data[0]` im arg2-Slot, `0x0215 CheckEDIDUpdateStatus`,
`0x0315 RequestEDID`, `0x0511 SetEDIDAudioMode`, `0x0411 SET5VFlag`, `0x0211 PullHotPlug` 2=DOWN/1=UP);
`analyse/hdmi-seq/arisc_edid_init.sh` (Reihenfolge, Wartezeiten); Ladeweg in doku/68 (Blob nach `0x00100000`,
Reset `0x07000400` Bit 0) und `prep_after_boot.sh` Schritt 1 (`arisc_load.py load --blob /root/scp.bin --skip-tail`);
Handshake in doku/75 Nachtrag 15:25 (ch3 `0x0300306c/7c`, 15 Wörter Typ `0x90`, Antwort Port 3 `0x0300347c`: Header
`& 0x00ffffff` + 0). EDID-Quelle: `re/work/weltneuheit/HDMI_EDID_14.bin` + `HDMI_EDID_20.bin` → ein 512-B-Firmware-File
`hy310-edid.bin` (Byte 168 wird von der Firmware selbst gepatcht).

**Schritte:** Treiber umbauen (Probe: Firmware laden → Reset → Notify lesen → quittieren → EDID-Sequenz optional per
Modulparameter/Debugfs auslösbar, später vom V4L2-Treiber gerufen); DT-Knoten (Msgbox-Adressen `0x03003000`
user0, `0x03003400` user1; Reset-Register; Firmware-Name) in `sun50i-h713.dtsi` — auf **unserem** Board-DTS-Stand
(doku/60 „Eigene Board-DTS fehlt": Änderungen ins SoC-dtsi, kenntlich machen). API-Header
`include/linux/soc/sunxi/h713-arisc.h` mit den sechs Funktionen aus doku/77 §2.1 und Rückgabewerten
(Statusantwort auf ch1 auswerten, Timeout als Fehler). Patch 0051 ersetzen, `build.sh kernel`.

**Ergebnis:** neuer Patch `00xx-soc-sunxi-h713-arisc.patch`. Firmware-Dateien: `analyse/arisc/scp.bin` → am Board
`/lib/firmware/h713-arisc.bin` (Name im Treiber), EDID → `/lib/firmware/hy310-edid.bin` (512 B aus den beiden
Blöcken). Binärdaten bleiben außerhalb des öffentlichen Repos; der Patch nennt nur die Namen.
**Abnahme (Board):** Kaltstart **ohne** Prep-Schritt 1; `dmesg` zeigt „notify … quittiert"; debugfs `status`
zeigt `startup_notify: acked`; `echo edid > /sys/kernel/debug/h713-arisc/cmd` (o. ä.) führt die EDID-Sequenz aus →
ThinkPad `connected`, EDID „SGD SX8"; Zeit bis `connected` ≤ 60 s.
**Fallen:** `0x0709xxxx` (HDMI-aux) **nie** lesen, bevor `ResetEDIDModule` verarbeitet ist (SoC-Hänger, doku/75).
Nur Notifies mit Result-Byte 0 und Count > 0 quittieren. Die ARISC pollt — kein Puls nötig (3/3 belegt).

### C — `cpu_comm`: In-Kernel-API (offline, dann Board-Slot gemeinsam mit E)

**Ziel:** `cpu_comm_call(comp_id, args, nargs, ret, nret, timeout)` und
`cpu_comm_register_callback(comp_id, fn, ctx)` als exportierte Kernel-Funktionen; Char-Devices bleiben.

**Eingaben:** `mainline/build/linux-6.18.38-<hash>/drivers/soc/sunxi/cpu_comm/` (`cpu_comm_channel.c`, `_dev.c`,
`_fifo.c`, `_hw.c`, `cpu_comm.h`; Serienpatch dazu in `patches/kernel/`), doku/65–67 (drei Generationen,
`cc_ref/cc_deref`, 64-Bit-Laden auf 4-Byte-Grenze), doku/72 (`callwq`-Testmodul — was davon Serienstand ist, steht
in `prep_after_boot.sh` Z. 2–3: `/root/hy310-cpu-comm-callwq-test.ko` **oder** Serienmodul; der callwq-Fix ist im
Serienbaum: `drivers/soc/sunxi/cpu_comm/cpu_comm_rpc.c` enthält `callwq` — Serienmodul reicht, das Testmodul in
`/root/` ist Diagnose), `analyse/hdmi-seq/hdmi_seq.py` (Aufbau eines
CALL: Name → comp_id-Hash, Argumentlayout, `Vp_Init`-Staging 4 MiB Shmem, Callback-Zustellung
`MipsHalCallback_SignalChange`/`HdmiHotPlugByPortHandler` mit `Para[]`), `mainline/docs/reference/cpu-comm-call-table.md`
(82 benannte Routinen), `legacy/userspace/hy310-hdmird/src` (Callback-Behandlung als Referenz, nicht portieren).

**Schritte:** API definieren (Header), Zustellung der RX-CALLs zusätzlich an Kernel-Handler (heute
`userspace_deliver`), synchroner CALL mit Warteschlange und Timeout, Test-Consumer im Treiber (debugfs: einen
benannten CALL absetzen). Pflichtliste #6 (ACK ohne Cache-Sync gegen Stock) mit Beleg abhaken oder fixen.
**Ergebnis:** Patch; Header `include/linux/soc/sunxi/h713-cpu-comm.h`; Doku der API in `doku/`.
**Abnahme (Board):** aus dem Kernel `THal_Vp_SetSource(3)` absetzen (debugfs), elog zeigt `SetActivePort`, kein
Absturz; `SignalChange`-Callback erreicht den Kernel-Handler (dmesg), `/dev/cpu_comm` funktioniert weiter.

### D — Video-Plane auf den Capture-Ring (offline auf A, dann Board-Slot)

*Ablauf und Registerreihenfolge: **Anhang A**, Stufe 7 und A.4.*

**Ziel:** Die KMS-Plane aus 0078 zeigt den HDMI-Capture-Ring korrekt (Geometrie + Farbe) — als **NV16**-Plane
mit dem heute belegten Registersatz, Descriptor beim Enable, Ring-Folge statt festem Slot.

**Eingaben:** `drivers/gpu/drm/tiny/sun50i-h713-afbd.c` (nach A mit 0078/0079/0080), Registersatz doku/76 §10
(Tabelle) und §13 (`0x40=0x780`, `0x44=0xF00`, `0x48=0x04380780`, `0x4C=0x021C0780`, `0x10=0x03000013`),
Descriptor-Inhalt in `analyse/hdmi-seq/viddec_descriptor.py` (Magic `0x61770000`, Typ 2, 1920×1080, Stride
1920, `color_format` 0 — **bleibt 0**, doku/76 §11.3), Pool-2-Flip-Zeiger `0x05600320/324` (drehen 60 Hz durch
die drei Slots), Vsync `GIC 142` (nutzt der Treiber schon), Firmware-Sicht in `re/captures/weltneuheit/fmt_re.log`
(`NRWinNode_AfbdConfigure`, `WriteAfbdBufStride`, `WriteAfbdCropWin`), Fotos/Abzüge in
`re/captures/weltneuheit/ours-20260906-source0/`.

**Schritte:**
1. Format `DRM_FORMAT_NV16` zusätzlich zu NV12 in der Plane; im Atomic-Update: bei NV16 `+0x44` = 2 × Y-Stride,
   `+0x4C` hi16 = Höhe/2 (**nicht** volle Höhe — der Leser bleibt NV12, der Trick ist der Stride, doku/76 §13),
   Format-Bits `+0x10[14:8]` = 0.
2. „HDMI-Passthrough"-Betrieb der Plane (Zwischenschritt bis E liefert dma-bufs): Modulparameter oder
   DRM-Property `hdmi-ring`, bei dem die Plane die physischen Ring-Adressen selbst kennt (DT-Knoten `mips_framebuf`, 26 MB ab
   `0x4BF41000`, per `memory-region` binden; /proc/iomem zeigt `4b100000-4d960fff reserved`) und pro Vsync den zuletzt fertigen Slot aus `0x320/0x324`
   übernimmt (Y-Slot i ↔ C-Slot i, gleiche Indizes). Descriptor-Seite `0x4D95F000`: beim Enable **einmal** schreiben,
   Zeiger `0x098`; beim Disable nicht löschen (Firmware-Neuanstoß vermeiden).
3. Selektor `0x051C006C` (`0x39000000` Video / `0x29000000` RGB) und RGB-Kanal `0x140/0x144` im Commit — exklusiver
   Mux, wie 0078 es tut; Gain `0x05140508` als Plane-Property „saturation" (Default `0x4C`, doku/77 §4).
4. Bauen, Board-Slot: Konsole → `modetest`/eigenes Testprogramm aktiviert die Plane → Bild.

**Ergebnis:** Patch `00xx-drm-h713-afbd-nv16-hdmi-ring.patch`, Testprogramm `analyse/kms/hdmi_plane_test.c` (libdrm).
**Abnahme (Board):** Kaltstart, Prep, SetSource, EDID (wie Abschnitt 1) → **ohne** `viddec_descriptor.py` und
**ohne** `afbd_source0.py`: Plane aktivieren → Bild in Farbe, Uhr läuft; Foto gegen `cstride.jpg` vergleichen;
Zuspieler aus/an → Bild kommt zurück.
**Fallen:** `0x14`/`0x6C` sind Latches (verbraucht = 0); `+0x38` ist W1C-Status; Bit 31 in `0x10` gehört der
Firmware. Die pool-2-Steuerworte `0x300/0x304/0x310` sind nicht beschreibbar. Nicht mehrfach den Descriptor
schreiben. Keine INCAP-Register.

### E — V4L2-Treiber `sun50i-h713-hdmirx` (offline: Gerüst + Probe-Sequenz; Board nach B+C)

*Ablauf: **Anhang A**, Stufen 3, 5, 6 und A.4.*

**Ziel:** `/dev/videoN` mit Probe = Stock-Init, `S_INPUT` = SetSource, EDID-ioctls über B, DV-Timings/Events
aus den Callbacks über C, die drei Ring-Slots als NV16-Puffer.

**Eingaben:** die vollständige Init-Reihenfolge steht in `analyse/hdmi-seq/hdmi_seq.py` Z. 705–790 als
`Step(...)`-Liste mit Stock-Sessionnummern — **genau diese Reihenfolge und Argumente**: Phase 2 `THal_Vp_Init`
(Staging-Shmem 4 MiB bei `0x4E700000` = `cpu_comm_reserved` + `0x400000`, `hdmi_seq.py` Z. 75), `RegisterSignalChangeCallback(11)`, `SetHDMIHotPlugByPortCallback(1)`; Phase 3
`SetBacklightLevel(0x64)`, `SetBacklightWorkMode(0)`, `SetTNR(2)`, `SetSNR(1)`, `SetDCI(2)`, `SetBlackExtension(1)`,
`SetPictureMode(1)`, `SetVideoRange(0)`, `Wce_SetWindow` (1920×1080, aspect 2), `CvbsSetPedestalMode(1)`,
`HDMI_SetPortMap` ×3 (Stock-Portmap: `portmap.cfg` im tvconfig), `Wce_SetWindow`, `DisableBlackScreen()` (ParaCount 0!),
`TurnOnARCAudioPath(1)`, `SwitchARCTXPath(0)`, `SetHDCP22Key` (Schlüssel `analyse/hdcp-keys/hdcp22-key-912.bin`, 912 B, liegt im Shmem bei Offset `0x36000` =
phys `0x4E336000`; Argument `Para[0]` = diese Adresse; doku/68 Z. 1618; im Treiber per `request_firmware("hy310-hdcp22.bin")`),
`HDMI_SetHPDTimeInterval(0xC8)`; Phase 4 `SetSource(3)`. Callback-Nutzlast: `SignalChange` mit `Para[2]` =
Shmem-Zeiger auf die Signal-Info (1920×1080, 60,00 Hz, Format RGB 12 Bit; Layout in `analyse/hdmi-seq/signal_info_buf.py`).
Puffer: DT-Knoten `mips_framebuf` (26 MB ab `0x4BF41000`, siehe 0b), Slots wie oben, Format NV16 1920×1080,
Slot-Fertig-Ereignis = Wechsel von `0x05600320` (im AFBD-Vsync abfragen) — das ist heute belegt (doku/76 §11.1).
Muster für V4L2-Treiber mit DV-Timings/EDID: `drivers/media/i2c/tc358743.c`, `drivers/media/platform/rockchip/…hdmirx`.

**Schritte:** Gerüst (platform_driver, DT-Knoten, videodev, vb2 mit `VB2_MEMORY_MMAP` über die reservierte Region
oder dma-buf-Export der drei Slots), `VIDIOC_ENUM_INPUT/S_INPUT`, `S_EDID/G_EDID` → B, `QUERY_DV_TIMINGS`,
`SUBSCRIBE_EVENT(SOURCE_CHANGE)`, Streaming: pro Vsync-/Slot-Wechsel `DQBUF` mit dem fertigen Slot (kein Kopieren).
Probe-Sequenz als Tabelle im Code, nicht als Prosa. HDCP-Key-Laden per `request_firmware`.
**Ergebnis:** Patch mit Treiber + DT; `doku/`-Seite mit der Probe-Sequenz und den Callback-Layouts.
**Abnahme (Board, nach B+C):** Kaltstart ohne Prep-Schritte 1–3; `v4l2-ctl -d /dev/videoN --query-dv-timings` →
1920x1080p60; ThinkPad aus/an → `SOURCE_CHANGE`; `v4l2-ctl --stream-mmap --stream-count=60` liefert 60 Frames NV16
(Datei am PC als Bild prüfen: `analyse/hdmi-seq/`-Rekonstruktion wie `rekon_ok.png`).
**Fallen:** `SetSource(3)` ist auf dieser Firmware ein Nullwechsel, wenn die aktive Quelle schon HDMI-1 ist
(doku/76 §2.2); die Zustandsmaschine wurde heute per Descriptor geöffnet (D). Warum die Capture nach einem
Descriptor-Neuanstoß nicht weiterläuft, ist offen (K3). Kein `--gap`-Drosseln übernehmen (Pflichtliste).

### F — `hy310-tv` (offline: Entwurf + Gerüst; Board nach D+E)

*Ablauf: **Anhang A**, A.3 (Wechselfälle) und A.4.*

**Ziel:** Ein kleines Programm/Unit: bei gültigem Signal Capture-Frames auf die Video-Plane, bei Verlust zurück
zum Desktop. Erste Fassung darf `gst-launch-1.0 v4l2src ! kmssink` oder ein 300-Zeilen-C-Programm sein.
**Eingaben:** D (Plane, NV16), E (V4L2), `legacy/userspace/hy310-hdmird/README.md` (Zustandsübergänge als Referenz).
**Ergebnis:** `userspace/hy310-tv/` mit `main.c`, `hy310-tv.service`, README. **Abnahme:** Kaltstart, Stecker rein,
Bild ohne Handgriff; Stecker raus → Konsole.

### G — PQ-Werkzeug `hy310-pq` (offline, komplett)

**Ziel:** Ein CLI, das die Stock-Presets liest und in Kernel-Schnittstellen umsetzt — heute schon belegt für die
Sättigung (`analyse/hdmi-seq/pq_saturation.py`, doku/77 §4), auszubauen.
**Eingaben:** `re/vendor/HY310/extracted/vendor_a/etc/tvconfig/` (`tvpq.db`: Picture_Mode 25 Zeilen,
White_Balance_Mode 20, Gamma_Point 33; `pq_picturemode.ini`; `pq_factory_extern.ini` Abschnitte
`[PICTURE_CURVE_HDMI]` u. a.; `pq_colortemp.ini`), `legacy/userspace/hy310-pqd/CALCULATEGAMMA_RE_GUIDE.md` (Gamma-
Interpolation, RE-belegt) und `BACKGROUND.md` §5 (DE2-LUT-Register `0x05208000/0x05208800/0x05209000`, Steuerung
`0x051C00E8`, Schreibsequenz), doku/77 §4.
**Schritte:** Parser für db/ini/xml; Modell: Eingang × Bildmodus → Benutzerwerte → Werkskurven → Zielwerte;
Ausgabe heute: Sättigung → Register (Board-Skript), Gamma-Punkte → 512-Einträge-LUT (für H); Kontrast/Helligkeit →
zunächst nur als Tabelle (Zielregister offen, siehe K5); später V4L2-Controls (I). Python ist in Ordnung; keine
Daemons. Tests mit den echten Dateien.
**Ergebnis:** `userspace/hy310-pq/` (Code, README, Beispielaufrufe), `doku/`-Seite „PQ-Datenmodell".
**Abnahme:** `hy310-pq show HDMI1 vivid` druckt die Werte; `hy310-pq gamma 2.2 --lut out.bin` erzeugt die LUT, die
der Legacy-Rechner (`hy310-pqd/tests`) auch erzeugt (bitgleich oder Abweichung erklärt).

### H — Gamma/CTM im KMS (offline auf A; Board-Slot kurz)

**Ziel:** `drm_crtc_enable_color_mgmt()` mit `GAMMA_LUT` (DE2-LUT, Register aus G) und `CTM` (Weißabgleich-Gains).
**Abnahme (Board):** `modetest`-Gamma oder ein Testprogramm setzt eine invertierte LUT → Wand messbar invertiert
(wandcheck, ROI), zurücksetzen → normal. **Fallen:** Schreibsequenz exakt wie in `BACKGROUND.md` §5.3.

### I — PQ-Controls im V4L2-Treiber (nach E)

`V4L2_CID_BRIGHTNESS/CONTRAST/SATURATION/HUE/SHARPNESS` → THal-RPCs (`SetBrightness` … in der Call-Tabelle),
Custom-Controls TNR/SNR/DCI/BlackExtension/PictureMode/VideoRange. Abnahme: `v4l2-ctl --set-ctrl=brightness=70`
→ elog zeigt den RPC, Wand ändert sich messbar. **Zu klären vorher (K5):** wirken die MIPS-PQ-RPCs auf unseren
AFBD-Source-0-Pfad überhaupt (sie stellen die VPROC ein, durch die unser Bild läuft — vermutlich ja; messen).

### J — Pflichtliste `legacy/docs/known-issues.md` (offline: Beleg-Recherche; Board: Messungen)

Jeden Punkt in eine Tabelle: Symptom, Ursache heute, Stand (gelöst/Stock-Verhalten/offen), Beleg. Bekannt:
4×1-Graustufen-Kachelung → gelöst (Source 0, doku/76); Msgbox-Puls-Workaround → durch Handshake und
„ARISC pollt" erledigt (B belegt es); Hot-Plug nach dem Boot → **Messung** (K4); IR-NEC, GPU/Wayland, Cedrus →
Stand feststellen, nicht anfassen.

### K — Offene RE-Fragen (offline, mit idalib; kein Board außer K4)

Werkzeug: `analyse/ida/README.md` (Datenbank-**Kopie** anlegen, Original nie öffnen; Aufruf; Adressumrechnung);
Beispielskripte `analyse/ida/ida_q22.py … ida_q26.py`; frühere Ergebnisse `re/captures/weltneuheit/*.log`.
Adressen: MIPS = ARM-phys + `0xB5000000` (MMIO), SRAM/DRAM `0x8Bxxxxxx` = ARM `0x4Bxxxxxx`.

1. **INCAP `0x0694084C`, `0x400`, `0x824`** — was bedeuten die Felder, die die Firmware bei Descriptor-Format 4
   umstellt (`0x04000C00→0x0C000C00`, `0x21→0x61`, Bit 31)? Schreiber finden (register-indirekt; in `CapWinNode_WriteReg`
   `0x8b19f…`/`VIncap_*`, siehe `re/captures/weltneuheit/incap_csc.log`).
2. **Ring-Folge:** Wer schreibt `0x05600320/324`, und gibt es ein „Slot fertig"-Interrupt (INCAP `+0x100` Pulse)?
   Ziel: E ohne Polling.
3. **Warum läuft die Capture nach einem zweiten Descriptor-Anstoß nicht weiter** (`0x928` Bit 31 bleibt 0, alle
   Slots identisch)? Pfad `HandleSignalEvent 0x8b108644` → `EnterWaitingPipeLineReady 0x8b108518` →
   `memory_agent_onoff 0x8b15349c`; MemoryAgent `+12` Gate, `+8` src (steht auf 1 = VideoDec).
4. **Hot-Plug nach dem Boot** (Board, K4 = Messung durch den Board-Agenten): bei stehendem Bild Kabel am ThinkPad
   per `xrandr --off/--auto` ist belegt; **echtes Ziehen** kann nur Marco. Stattdessen: ARISC-Zähler `0x11722c`
   und elog bei `PullHotPlug`; dokumentieren, ob die ARISC auf 5-V-Detect selbst reagiert (Disassembly
   `analyse/arisc-frame/full-disasm.txt`, Handler `0x0411 SET5VFlag`).
5. **Wo landen Helligkeit/Kontrast** (PQ) im Register? Kurven in `pq_factory_extern.ini`; RPC `SetBrightness`/
   `SetContrast` → welches PROC-Register (`0x05140xxx`)? Für G/I nötig. Methode: idalib-Xrefs auf `0xBA140…`
   in den Handlern der Call-Tabelle.
6. **Stocks Compositing** (Marcos Frage nach dem OSD): Stock führt OSD (Android-UI, AFBD-Kanal 2 `0x05600140`)
   und Video durch dieselbe YUV-Kette (cstenger, Commit 5718e4c). Bei uns ist der Mux exklusiv (Source 0 **oder**
   RGB). Für ein echtes Overlay (Menü über dem Video) muss die Blend-Stufe der DE gefunden werden — RE-Frage,
   kein Nachtziel.

### L — Dokumentation (laufend, ein Agent)

Nachtlog führen, am Morgen `doku/00-STATUS.md`, `doku/60-offen.md` und `doku/75` (Handoff) auf den Nachtstand
bringen, Memory-Dateien nicht anfassen (die pflegt die Hauptsitzung).

---

## 4. Reihenfolge für die Nacht

```
parallel, offline:   A (Patches)   B (ARISC)   C (cpu_comm)   G (PQ-Tool)   K1/K2/K3/K5/K6 (RE)   J (Recherche)
                        │              │            │
Board-Slot 1:        A-Abnahme (neuer Kernel bootet, Konsole, Plane sichtbar)
                        │
parallel, offline:   D (Plane, auf A)   H (Gamma, auf A)   E-Gerüst (auf B/C-Header)   F-Entwurf
Board-Slot 2:        B-Abnahme (Kaltstart ohne Prep 1, EDID aus dem Kernel)
Board-Slot 3:        C-Abnahme (SetSource + Callback im Kernel)
Board-Slot 4:        D-Abnahme (Bild aus der Plane, Farbe)  → das ist der sichtbare Meilenstein der Nacht
Board-Slot 5:        H-Abnahme (Gamma-LUT messbar), K4 (HPD-Messung)
danach:              E-Abnahme, F
```

Wer fertig ist und keinen Board-Slot bekommt, schreibt Tests, Doku, oder nimmt eine K-Frage.

---

## 5. Was Marco am Morgen vorfindet (Abnahme der Nacht)

- `doku/79-nachtlog-20260907.md`: pro Paket Stand, Belege, Fehlschläge mit Grund.
- Neue/geänderte Patches in `mainline/patches/kernel/` + `series`, `build.sh kernel` grün, Baumhash im Log.
- Fotos und Registerabzüge jeder Board-Abnahme in `re/captures/weltneuheit/ours-20260907-nacht/`.
- Mindestens: A gebootet, B oder C abgenommen, D-Patch fertig (auch wenn die Abnahme noch aussteht), G als
  Werkzeug lauffähig, K1–K3 mit Antworten oder klar benannten Sackgassen.
- Das Board steht am Ende in einem **definierten** Zustand: Kaltstart + Sequenz aus Abschnitt 1, Bild auf der Wand
  (damit Marco morgens etwas sieht) — oder, wenn das nicht geht, ausgeschaltet mit Vermerk im Log.

---

## 6. Board-Protokoll für den Board-Agenten

1. Sperre setzen: `echo "$(date +%F_%T) <agent> <paket>" > /tmp/claude-1000/h713-board.lock`; jeder andere Agent
   prüft die Datei und wartet. Am Ende löschen.
2. TFTP prüfen (`ss -ulnp | grep -w :69`), dann Kaltstart, dann `for i in $(seq 30); do ssh … uptime && break; sleep 4; done`.
3. Sequenz aus Abschnitt 1 **wörtlich**; nach jedem Schritt eine Zeile ins Log mit Uhrzeit und Rückgabe.
4. Messen: `dump_state.py NAME` vor/nach jeder Änderung; `wandcheck.py shot NAME`; Fotos **ansehen**.
5. Bei Hänger: nicht warten, Log, Kaltstart. Drei Hänger in Folge bei derselben Aktion → Paket abbrechen, Log,
   nächstes Paket.
6. Nie: INCAP schreiben, Descriptor zweimal, Kamera-Belichtung, `tio`, sudo, `apt` im Container live.
7. Ergebnisse (Fotos, Abzüge) nach `re/captures/weltneuheit/ours-20260907-nacht/<paket>/` kopieren.

**Kernel ausrollen (nur der Board-Agent):** Das Board bootet per TFTP `tftp/h713-kernel-netboot.fit` (Bootfile in
U-Boot fest, doku/95); gebaut wird die Netboot-Variante mit

```bash
podman exec h713-build bash -lc 'cd /work/mainline && KERNEL_CONFIG=netboot build/build.sh kernel'
```

Ergebnis `mainline/build/out/h713-kernel-netboot.fit` (Module unter `mainline/build/out/modules/`). Vor dem
Kopieren die laufende FIT sichern: `cp tftp/h713-kernel-netboot.fit tftp/h713-kernel-netboot.fit.bak-<datum>-<paket>`,
dann die neue nach `tftp/` — **erst wenn die Sperre gehalten wird**, denn der nächste Kaltstart bootet sie.
Module per `scp` in das Root des Boards (`/lib/modules/$(uname -r)/…`, das Root liegt per NFS, ist aber über
SSH beschreibbar), danach `depmod -a`. Bei Bootfehler: Sicherung zurückkopieren, Kaltstart, Log. Der normale
Kernel (`h713-kernel.fit`, r8152 als Modul) wird in der Nacht nicht angefasst.

---

## 7. Nachschlagetabelle

**Adressen (ARM-phys):** AFBD `0x05600000` (ch0 `0x010`, ready `0x014`, Geometrie `0x020/0x024/0x030`, Strides
`0x040/0x044`, Crop `0x048/0x04C`, Gate `0x060`, Field `0x064`, Ring-Mux `0x068=0x122`, Dirty `0x06C`, Pool-1 Y
`0x070–0x07C`, C `0x084–0x090`, Info `0x098–0x0A4`, ch1 `0x100`, RGB/OSD `0x140/0x144`, Flip `0x320/0x324`);
PROC/„route" `0x05140000` (Chroma-Gain `0x508`); LVDS `0x051C0000` (Selektor `0x06C`; Gamma-Steuerung `0x0E8`);
DE `0x05000000` (Schreibkanäle `0x178/0x1B8/0x278/0x2B8`), DE-LUT `0x05208000`; INCAP `0x06940000` (Frame/Zeile
`0x104`, Ring Y `0x8F0..`, C `0x930..`, Ausgabe `0x928/0x968` Bit 31 — **nur lesen**); Msgbox user0 `0x03003000`,
user1 `0x03003400`; ARISC-Reset `0x07000400` Bit 0; Descriptor-Seite `0x4D95F000`; AppTopProjector-Objekt ARM
`0x4B8C8D7C` (+4 Zustand, +224 Quelle), MemoryAgent `0x4B89DEA0` (+8 src, +12 Gate); elog-Level `0x4B48BD9C`.

**Skripte (Board `/root/`, Quelle `analyse/hdmi-seq/`):** `prep_after_boot.sh`, `hdmi_seq.py`, `arisc_edid_init.sh`,
`viddec_descriptor.py`, `afbd_source0.py`, `dump_state.py`, `chroma_stat.py`, `pat_load.py`, `pq_saturation.py`,
`elog_tail.py`; Host: `wandcheck.py`, `cam_exposure.py`, `sonoff_ctl`; RE: `analyse/ida/` (README), `analyse/arisc-frame/full-disasm.txt` (ARISC-Disassembly), `tools/or1k-disasm.py`.

**Dokumente:** doku/50 (Bauen, Befehle), 95 (Netboot, TFTP, Bootfile), 68 (ARISC-Laden), 74 (SetSource), 75 (Handoff, ARISC/EDID), 76 (Bild,
Farbe, Register, Fallen), 77 (Architektur, PQ), 90 (Stock-Referenz), cstenger `mainline/docs/kms-display.md`,
`video-decode.md`, `reference/cpu-comm-call-table.md`; Legacy `legacy/userspace/hy310-pqd/BACKGROUND.md`,
`CALCULATEGAMMA_RE_GUIDE.md`, `hy310-hdmird/README.md`, `legacy/docs/known-issues.md`.

---

# Anhang A — Der vollständige Ablauf des Quellenwechsels auf HDMI

Nachtrag vom 06.09.2026, 22:00. Dieser Anhang beschreibt **einen** Vorgang lückenlos: „zeige das Bild des
Geräts, das am HDMI-Eingang steckt" — und zurück. Er hat zwei Spalten: **wie es heute läuft** (Skripte, jeder
Schritt am Gerät belegt) und **wo derselbe Schritt im Zielbild sitzt** (Kernel, Pakete B–F). Wer ein Paket
implementiert, findet hier die Reihenfolge, die Werte und die Prüfpunkte; wer misst, findet die Befehle.

## A.1 Die sieben Stufen auf einen Blick

| # | Stufe | Heute | Ziel | Prüfpunkt |
|---|---|---|---|---|
| 1 | MIPS läuft, Heap steht | U-Boot | U-Boot (unverändert) | `dmesg \| grep elog:` liefert Zeilen |
| 2 | ARISC läuft und ist quittiert | `prep_after_boot.sh` Schritt 1 + `hy310-arisc-hdmi.ko` | Paket B: Treiber-Probe | `R_CPUCFG 0x07000400` = 1, Modul-Log „notify quittiert" |
| 3 | MIPS-RPC initialisiert (24 Aufrufe) | `hdmi_seq.py --phase 3` | Paket E: V4L2-Probe | alle `RETURN nret=…`, kein `FEHLER` |
| 4 | EDID im Empfänger, HPD an | `arisc_edid_init.sh` | Paket B/E: `VIDIOC_S_EDID` | Zuspieler meldet `connected`, EDID „SGD SX8" |
| 5 | **Quelle umschalten** | `hdmi_seq.py --phase 4 --only setsource --source 3` | Paket E: `VIDIOC_S_INPUT` | elog `SetActivePort`, danach `SwitchState 3→4→5` |
| 6 | Signal steht, Capture schreibt | Firmware von allein | Firmware von allein | `0x06940104` zählt 60/s; Cb/Cr um 128 |
| 7 | Bild auf dem Panel | `viddec_descriptor.py set` **+ HPD-Zyklus** + `afbd_source0.py on` | Paket D: Plane einschalten | Foto **mit Gamma-Reiz**: Wand ändert sich; `0x06940928` Bit 31 = 1 |

Stufen 1–4 sind **Vorbereitung** und laufen einmal pro Kaltstart. Der eigentliche **Umschaltvorgang** sind
Stufen 5–7; er ist wiederholbar, ohne Stufen 1–4 zu wiederholen (belegt: Quellenwechsel und HPD-Zyklus am
06.09., 21:14 und 21:15, Registerabzüge `04_after_srcoff`/`05_after_hpd` — **null** strukturelle Unterschiede).

## A.2 Die Stufen im Einzelnen

### Stufe 1 — MIPS und Heap (U-Boot, nichts zu tun)

U-Boot startet die MIPS-Firmware, legt den SMM-Heap an (`h713_mips_init_smm_heap()`, doku/74 — ohne ihn stirbt
der SoC bei `SetSource`), lädt TSE/PQ-Datenbanken und stellt das Fabric-Routing. Der Kernel bootet per TFTP,
Rootfs per NFS.
**Prüfung:** `ssh root@192.168.8.141 'dmesg | grep -c elog:'` > 0.
**Wenn nicht:** MIPS ist nicht hochgekommen — Kaltstart. Nie ohne MIPS weiterarbeiten.

### Stufe 2 — ARISC starten und quittieren

Heute im Prep: Blob `/root/scp.bin` nach `0x00100000`, Reset `0x07000400` Bit 0 lösen
(`arisc_load.py load --blob /root/scp.bin --skip-tail --i-mean-it`), dann Modul `hy310-arisc-hdmi.ko` laden.

Der **Startup-Handshake** ist Pflicht, sonst steht die ARISC 100 s (doku/75, Nachtrag 15:25): Sie schickt auf
**ARM-RX ch3** (Msgbox user0, `FIFO_STAT 0x0300306C`, `MSG_DATA 0x0300307C`) ein Notify aus 15 Wörtern,
Typ `0x90`, mit Versionsstring `projector-tv303-android11-v1.3-3-g293ff69`. Der ARM antwortet auf
**user1 Port 3** (`0x0300347C`) mit zwei Wörtern: `header & 0x00FFFFFF`, dann `0`. Nur Notifies mit
Result-Byte 0 **und** Count > 0 quittieren, sonst Ping-Pong (`fd900200`). **Zum Doorbell-Puls — Korrektur vom 07.09.:** Eine frühere Fassung dieses Plans
schrieb „kein Puls nötig, die ARISC pollt (3/3 belegt)". Das ist **nicht belegt** und war mein Fehler. Belegt ist
nur eine Warteschleife für **Port 3** (`re/notes/arisc-firmware__b7da2fb9.md`: `0x07970 msgbox-recv polling loop
(sub0 port 3 FIFO_STAT)`) — der Notify-/Quittungskanal. Für **Port 0** (die Host-Unterbefehle: EDID, HPD) ist
nichts gemessen; `analyse/arisc-msg/arisc_send.py` pulst `TX_IRQ_EN 0x03003430` Bit 7 ~10 µs und beschreibt die
Msgbox als flankengesteuert.

**Messung, bevor Paket B den Puls streicht** (ein Board-Slot, 10 Minuten): nach Prep und `ResetEDIDModule` einen
harmlosen Host-Unterbefehl **ohne** Puls senden (`arisc_hdmi.py raw --sub-cmd 0x0311 --arg1 2 --arg2 0`, Puls im
Werkzeug abschalten) und die Rückmeldung `classify/Handler gelaufen` lesen: „ja" ⇒ die ARISC pollt auch Port 0,
der Puls darf raus (Pflichtliste #2/#8 erledigt, mit Beleg). „NEIN" ⇒ der Puls bleibt und ist **kein Workaround**,
sondern die flankengesteuerte Msgbox — dann ist der Pflichtlisten-Punkt mit genau dieser Messung als
Stock-Verhalten abzuhaken. Beide Ausgänge sind ein Ergebnis; geraten wird nicht.

**Prüfung:** `busybox devmem 0x07000400` = 1; Modul-Log zeigt die Quittung; erste Sonde nach dem Prep wird in
~20 ms beantwortet (vorher 100 s).
**Ziel (Paket B):** alles im Treiber-Probe, `request_firmware("h713-arisc.bin")`.

### Stufe 3 — MIPS-RPC initialisieren (24 Aufrufe in Stock-Reihenfolge)

`hdmi_seq.py --phase 3` fährt genau die Stock-Sequenz; Reihenfolge und Argumente sind aus dem Stock-Mitschnitt,
die Sessionnummern stehen im Code (`analyse/hdmi-seq/hdmi_seq.py`, Z. 705–790):

| Phase | Aufruf | Argumente | Bemerkung |
|---|---|---|---|
| 2 | `THal_Vp_Init` | `0, 0, 0x4E700000` | Staging = `cpu_comm_reserved` + 4 MiB |
| 2 | `THal_Vp_RegisterSignalChangeCallback` | `11` | liefert später Signal-Info |
| 2 | `THal_Vp_SetHDMIHotPlugByPortCallback` | `1` | Hot-Plug-Meldung der Firmware |
| 3 | `Thal_Vp_SetBacklightLevel` / `SetBacklightWorkMode` | `0x64` / `0` | Session 14/15 |
| 3 | `SetTNR` `2`, `SetSNR` `1`, `SetDCI` `2`, `SetBlackExtension` `1` | | PQ-Vorgaben, Session 17–20 |
| 3 | `SetPictureMode` `1`, `SetVideoRange` `0` | | Session 21/22 |
| 3 | `Wce_SetWindow` | 1920×1080, Aspect 2 | Session 23 — auch wenn der RPC ein No-op ist: Stock ruft ihn |
| 3 | `CvbsSetPedestalMode` `1` | | Session 24 |
| 3 | `HDMI_SetPortMap` ×3 | Stock-Portmap | Session 25–27; `portmap.cfg`: Port 1→Source 1 = HDMI1 |
| 3 | `Wce_SetWindow` (zweites Mal) | | Session 28 |
| 3 | `DisableBlackScreen` | **ParaCount 0** | Session 29 — nicht 1 |
| 3 | `TurnOnARCAudioPath` `1`, `SwitchARCTXPath` `0` | | Session 30/31 |
| 3 | `SetHDCP22Key` | Adresse `0x4E336000`, 912 B | Session 32; Datei `analyse/hdcp-keys/hdcp22-key-912.bin` |
| 3 | `HDMI_SetHPDTimeInterval` | `0xC8` = 200 ms | Session 33 |

**Prüfung:** jeder Schritt liefert `RETURN`; im Prep-Log steht am Ende „fertig (clean)".
**Ziel (Paket E):** genau diese Tabelle als Array im Treiber-Probe, über die `cpu_comm`-Kernel-API (Paket C).

### Stufe 4 — EDID hochladen, HPD anlegen

`arisc_edid_init.sh`, Host-Unterbefehle über Msgbox user1 Port 0 (Nutzlast bei `0x115F59`), Port 0:

| Reihenfolge | Sub-Cmd | arg1 | arg2 | Daten |
|---|---|---|---|---|
| 1 | `0x2011` ResetEDIDModule | 0 | 0 | — |
| 2 | `0x0011` HostHDMIMAP | 0 | 1 | `2` (= MAP 0,1,2) |
| 3 | `0x0311` SetEDIDVersion | 2 | 0 | — |
| 4–11 | `0x0111` UpdateEDID, Fragment 0..7 | Fragment | **erstes Byte** des Fragments | 63 Bytes ab Offset `frag*64+1` |
| 12 | `0x0215` CheckEDIDUpdateStatus | 0 | 0 | Antwort auf ARM-RX ch1: `ff f8 01 01 01 …` |
| 13 | `0x0315` RequestEDID | 0 | 0 | Antwort = EDID zurückgelesen |
| 14 | `0x0511` SetEDIDAudioMode | 0 | 0 | — |
| 15 | `0x0411` SET5VFlag | 0 | 1 | — |
| 16 | `0x0211` PullHotPlug **DOWN** | 0 | 2 | danach **10 s warten** |
| 17 | PullHotPlug **UP** | Port 0 | Wert 1 | Zuspieler liest EDID neu |

Sendedatei `/root/edid-send.bin` = `HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`, 512 B, **plain** (bytesequentiell).
Drei Eigenheiten, alle belegt (doku/75, Nachtrag 14:55): das erste Datenbyte reist im **arg2-Slot**; die Firmware
gibt das EDID **erst nach Fragment 7** aus (`[0x1723E]`, danach Gate `[0x1723F]`) — mit weniger Fragmenten
bekommt der Zuspieler nie ein EDID; die Firmware patcht Byte 168 (Physical Address) und die Prüfsumme selbst.

**Absolute Sperre:** die HDMI-Aux-Register `0x0709xxxx` **niemals** lesen, bevor `ResetEDIDModule` verarbeitet
ist — der SoC hängt sofort (Läufe 103a/b). Das Skript bricht deshalb ab, wenn Schritt 1 nicht „ja" meldet.

**Prüfung am Zuspieler:** `cat /sys/class/drm/card0-HDMI-A-2/status` = `connected`,
`DISPLAY=:0 xrandr | grep -A1 ^HDMI-2` zeigt 1920x1080 60,00.
**Ziel (Paket B/E):** `VIDIOC_S_EDID` schreibt die Blöcke, der ARISC-Treiber führt die Reihenfolge aus.

### Stufe 5 — der Quellenwechsel selbst

```bash
taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it --only setsource \
     --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3
```

`SetSource(3)` = HDMI-1 = die einzige Buchse (Hardware-Port 0, laut `SetPortMap (3,0)`).

**Zwei Eigenheiten, die man kennen muss:**

1. **Ist die aktive Quelle der Firmware bereits HDMI-1, ist `SetSource(3)` ein Nullwechsel** und stößt nichts an
   (doku/76 §2.2: `ApplyNewSource` läuft nur bei Änderung). Genau das war am 21:03 zu sehen: „(nichts hat sich
   bewegt)", und trotzdem lief danach alles. Der Aufruf ist also **notwendig als Zustandsansage**, aber er ist
   nicht der Auslöser der Bildkette.
2. Ein **echter** Wechsel (z. B. `SetSource(4)` und zurück auf `3`, gemessen 21:06) läuft durch, öffnet die
   DE-Schreibkanäle, macht die Capture aber **nicht** von selbst wieder scharf — siehe A.5.

**Prüfung:** elog zeigt `SetActivePort 1`, `port 1 send HPD event`; AppTop-Objekt `0x4B8C8D7C+224` = 3.
**Ziel (Paket E):** `VIDIOC_S_INPUT` bzw. das Öffnen des Capture-Geräts.

### Stufe 6 — Signal steht, Capture schreibt (Firmware allein)

Die Firmware erkennt TMDS, geht `SwitchState 3→4→5`, setzt `Set Valid Signal 0x20000`, rechnet die Fenster
(WCE), konfiguriert INCAP und schreibt **NV16, YUV** in den Ring:

| | |
|---|---|
| Y-Slots | `0x4C3EF000`, `0x4C5EE000`, `0x4C7ED000` (Ring-Ziele INCAP `+0x8F0/8F4/8F8`) |
| C-Slots | `0x4C9EC000`, `0x4CBEB000`, `0x4CDEA000` (`+0x930/934/938`) |
| Ausgabe frei | INCAP `+0x928`/`+0x968` Bit 31 — **von der Firmware gesetzt, nie von Hand** |
| Zähler | `+0x104`: Bits 31..16 = Frame, 15..0 = Zeile |
| Flip-Zeiger | AFBD `0x05600320`/`324` rotieren mit 60 Hz durch die drei Slots |

**Prüfung (beide nötig):**
```bash
ssh root@192.168.8.141 'python3 /root/chroma_stat.py'   # Cb ~130, Cr ~137 = echtes YUV
# Frames/s: 0x06940104 zweimal lesen, obere 16 Bit differenzieren -> 60
```
Ein **statischer** Bildschirm erzeugt keine Änderung im Puffer — Standbild ist kein Stillstand. Liveness immer
mit einem erzwungenen Reiz prüfen (`xrandr --output HDMI-2 --gamma 1:0.2:0.2`, danach `1:1:1`).

### Stufe 7 — Bild auf das Panel

**7a. Zustandsmaschine öffnen — genau einmal pro Boot, und danach die Capture wieder scharf machen:**

```bash
ssh root@192.168.8.141 'python3 /root/viddec_descriptor.py set'
# danach ZWINGEND ein HPD-Zyklus, sonst bleibt das Bild ein Standbild:
ssh root@192.168.8.141 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; \
     sleep 8; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
```

> **Korrektur vom 07.09., 22:35 — mein Fehler, er hat eine Nacht gekostet.** Der Descriptor-Schreibvorgang
> **schaltet die Capture ab**: Die Firmware nimmt ihn als VideoDec-Ereignis, setzt MemoryAgent `+8` auf 1
> (VideoDec), und `memory_agent_onoff` löscht dabei die INCAP-Freigabe `0x06940928/0968` Bit 31, weil die Capture
> nicht zur Maske der Quelle VideoDec gehört. Danach zählt `+0x104` weiter 60/s, aber **nichts wird geschrieben** —
> die Wand zeigt den zuletzt aufgenommenen Rahmen. Beide Hälften des Beweises standen schon in meinen eigenen
> Messungen vom 21:09 (vor dem Descriptor `928=e0020438`, danach `928=60020438`); ich habe sie nicht
> zusammengezogen und ein statisches Webseitenbild für ein laufendes Bild gehalten.
>
> **Der HPD-Zyklus macht sie wieder scharf** (07.09., 22:31 gemessen): Bit 31 zurück auf `e0020438`, alle drei
> Ringplätze folgen einem Gamma-Reiz am Zuspieler und kehren identisch zurück, die Wand ändert sich
> reproduzierbar (9,6 % im Messbereich, hin und zurück deckungsgleich: 43532 / 43476 Bildpunkte).
> **Sauberer ist die andere Reihenfolge:** Descriptor **vor** der EDID/HPD-Sequenz (Stufe 4) — dann macht deren
> `PullHotPlug UP` die Capture ohnehin scharf, und es braucht keinen zweiten Zyklus. Beide Wege sind Stock-Befehle,
> kein Poke.

Schreibt 36 Wörter nach `0x4D95F000` und den Zeiger darauf nach AFBD `0x05600098`:
`[0]=0x61770000` (Magic), `[1]=2`, `[2..5]=1920,1080,1920,1080`, `[6..9]=0,1080,0,1920`, `[13]=[14]=30000`
(Bildrate ×1000), `[15]=0` progressiv, **`[16]=0`** (Farbformat yuv420_888 — **bleibt 0**), `[17]=1` (BT.709),
`[22]=1920` (Stride), `[24]=0` SDR, `[25]=[26]=0`, `[28]/[30]/[32]/[34]=30720/17280/30720/17280`.

Die Firmware liest das als **VideoDec-Ereignis**, geht auf Zustand 4 (`EnterWaitingPipeLineReady`), setzt das
MemoryAgent-Gate auf `0x2007C` und öffnet die vier DE-Schreibkanäle `0x05000178/1B8/278/2B8` (Bit 31).
Auf Stock schreibt diesen Descriptor `decd` je Frame; bei uns ist er die Eintrittskarte.

**Prüfung:** AppTop `+4` = 4; MemoryAgent `0x4B89DEA0+12` = `0x2007C`; DE-Kanäle `0xE00…`.

**7b. AFBD Source 0 auf den Capture-Ring** (`afbd_source0.py on`), in dieser Reihenfolge:

| # | Register | Wert | Zweck |
|---|---|---|---|
| 1 | `0x05600140` / `0x05600144` | `0x83001900` / `1` | RGB-Kanal (Konsole) aus + committen |
| 2 | `0x05600060` / `064` / `068` | `1` / `0` / `0x122` | Gate, Field, Ring-Mux |
| 3 | `0x05600070..07C` | `0x4C3EF000` | vier Y-Slots |
| 4 | `0x05600084..090` | `0x4C9EC000` | vier C-Slots |
| 5 | `0x05600098..0A4` | `0x4D95F000` | vier Info-Slots (Descriptor) |
| 6 | `0x05600080` / `094` / `0A8` | `0` | Aux |
| 7 | `0x05600040` / `0x05600044` | `0x780` / **`0xF00`** | Y-Stride 1920, **C-Stride 3840 = NV16 im NV12-Leser** |
| 8 | `0x0560006C` | `1` | Dirty-Latch |
| 9 | `0x05140508` | `0x144C0000` | Chroma-Gain (Sättigung „standard", doku/77 §4) |
| 10 | `0x05600010` / `0x05600014` | `0x03000013` / `1` | Source 0 an + ready |
| 11 | `0x051C006C` | `0x39000000` | LVDS-Selektor auf Video |

Schritt 7 ist der Farbfix vom 21:10: Der Leser arbeitet als NV12 (Chroma halbe Höhe) und holt für Ausgabezeile
*r* die Chromazeile ⌊r/2⌋; mit dem doppelten Zeilenabstand trifft das genau Zeile *r* des NV16-Puffers
(doku/76 §13). Ohne Schritt 7 ist die Farbe vertikal 2× gedehnt.

Der Mux ist **exklusiv**: Source 0 **oder** RGB erreicht den Encoder, keine Mischung. Deshalb verschwindet die
Konsole, solange das HDMI-Bild steht.

**Prüfung:** `python3 analyse/hdmi-seq/wandcheck.py shot NAME`, Bild **ansehen**; `afbd_source0.py show` zeigt
`vid=03000013 … gain=144c0000 sel=39000000`, `strides: y=00000780 c=00000f00`.

## A.3 Zurückschalten und die vier Wechselfälle

**Zurück zur Konsole** (`afbd_source0.py off`): vier Y/C/Info-Slots auf 0, Aux 0, **C-Stride zurück auf `0x780`**,
Dirty 0, Gain `0x04000000` (Chroma aus), RGB-Kanal `0x03001901` + Latch `1`, Selektor `0x29000000`.

| Fall | Was passiert | Gemessen |
|---|---|---|
| **Zuspieler aus/an** (`xrandr --output HDMI-2 --off/--auto`) | Firmware hält den Zustand; nach ~8 s ist das Bild farbrichtig zurück | 21:14, Foto `nach_wechsel1.jpg`; Diff `03_source0`→`04_after_srcoff`: nur Laufzeitwerte, **0 strukturelle** |
| **HPD-Zyklus** (`PullHotPlug` DOWN 10 s → UP) | Zuspieler liest EDID neu, Bild kommt farbrichtig zurück | 21:15, Foto `nach_hpd2.jpg`; Diff `04`→`05`: **0 strukturelle Unterschiede** |
| **Auf die Konsole und zurück** | `off` → Konsole; `on` → Bild (Descriptor **nicht** erneut schreiben) | 19:22–21:15 mehrfach |
| **Echter Quellenwechsel in der Firmware** (`SetSource(4)`→`(3)`) | Zustand 4 und DE-Kanäle bleiben offen, **die Capture bleibt aber stehen** | 21:06, siehe A.5 |

## A.4 Derselbe Ablauf im Zielbild (was die Pakete bauen)

```
Nutzer/Frontend                Userspace (hy310-tv, Paket F)          Kernel
───────────────────────────────────────────────────────────────────────────────────────────
"HDMI zeigen"      ──▶  open("/dev/video0")              ──▶  E: Probe ist gelaufen (Stufen 2–4)
                        VIDIOC_S_INPUT(0)                ──▶  E: SetSource(3)                (Stufe 5)
                        VIDIOC_QUERY_DV_TIMINGS          ◀──  E: aus SignalChange-Callback   (Stufe 6)
                        VIDIOC_REQBUFS / STREAMON        ──▶  E: Ring-Slots als Puffer
                        drmModeSetPlane(video, dmabuf)   ──▶  D: Descriptor + AFBD-Sequenz   (Stufe 7)
                        pro Frame: DQBUF → Plane-Flip    ──▶  D: Slot-Zeiger + Dirty-Latch
"Desktop zeigen"   ──▶  Plane aus, STREAMOFF             ──▶  D: RGB-Kanal an, Selektor RGB
Signal weg         ◀──  V4L2_EVENT_SOURCE_CHANGE         ◀──  E: aus HotPlugByPort/SignalChange
```

Wichtig für die Umsetzung: **Der Descriptor gehört in den Plane-Enable** (Paket D), nicht in ein Skript und
nicht in eine Schleife — er wird beim Aktivieren **einmal** geschrieben und beim Deaktivieren **nicht** gelöscht.
Die EDID/HPD-Reihenfolge gehört hinter `VIDIOC_S_EDID` (Paket B). Die 24 RPC-Aufrufe gehören in den Probe des
V4L2-Treibers (Paket E), als Tabelle, nicht als Prosa.

## A.5 Fehlerbilder und was sie bedeuten

| Symptom | Ursache | Abhilfe |
|---|---|---|
| **Bild steht still** (Inhalt korrekt und farbrichtig, ändert sich aber nie), `0x06940928` = `0x60020438`, Flip-Zeiger unbewegt, `+0x104` zählt weiter 60/s | Der **Descriptor** hat die Capture abgeschaltet (MemoryAgent `+8` = 1 = VideoDec) — der Normalfall nach Stufe 7a | **HPD-Zyklus** (`PullHotPlug` DOWN 8–10 s → UP); Bit 31 kommt zurück, Ring folgt wieder. Oder Descriptor vor Stufe 4 schreiben |
| Farben vertikal 2× gedehnt, Farbe quillt unter das Bild | C-Stride `0x05600044` steht auf 1920 | auf `0xF00` setzen, Dirty + ready |
| Bild vierfach gekachelt, dunkel | Descriptor mehrfach beschrieben → Firmware hat NR/PROC/Capture umkonfiguriert | **Kaltstart**; Descriptor nur einmal |
| Bild friert ein, alle drei Ring-Slots identisch, `+0x104` zählt weiter | INCAP `+0x928/968` Bit 31 von Hand gesetzt | **Kaltstart**; INCAP nie schreiben |
| Zweite Ebene enthält Rot/Blau statt Cb/Cr (`Cb`≈180, `Cr`≈189) | Folge des vorigen Punktes | **Kaltstart** |
| Alles grün, Geometrie halbiert | AFBD-Formatcode auf 2 gesetzt (`0x03000213`) | zurück auf `0x03000013`, C-Stride `0xF00` |
| Bild vertikal doppelt | Crop `0x48/0x4C` auf Stock-Werte (`…0780` Höhe) gesetzt | Firmware-Werte lassen: `0x04380780` / `0x021C0780` |
| SoC hängt sofort nach dem ersten ARISC-Befehl | `0x0709xxxx` vor `ResetEDIDModule` gelesen | Kaltstart; Reihenfolge einhalten |
| ARISC antwortet ~100 s nicht | Startup-Notify nicht quittiert | Modul mit Handshake laden (Stufe 2) |
| `SetSource` meldet „nichts hat sich bewegt" | Nullwechsel, aktive Quelle ist schon HDMI-1 | normal, kein Fehler |
| Capture steht nach echtem Quellenwechsel | offen (A.6 Punkt 1) | Kaltstart und Sequenz von vorn |

## A.6 Was an diesem Ablauf noch nicht geklärt ist

1. **Capture-Abschaltung durch den Descriptor — 07.09. beantwortet.** Der Descriptor setzt MemoryAgent `+8` auf 1
   (VideoDec); `memory_agent_onoff` löscht daraufhin die INCAP-Freigabe. Ein **HPD-Zyklus** macht sie wieder
   scharf (22:31 belegt, siehe Stufe 7a). Offen bleibt der Rest der Frage: warum ein reiner Quellenwechsel
   `SetSource(4)`→`(3)` das **nicht** tut, obwohl er dieselbe Zustandsmaschine anstößt, und ob es einen Weg gibt,
   die DE-Kanäle zu öffnen **ohne** die Quelle auf VideoDec zu stellen (dann entfiele der HPD-Zyklus ganz).
   Für Paket E ist das entscheidend: `VIDIOC_S_INPUT` darf im Betrieb nicht auf einen Hot-Plug angewiesen sein.
   Bleibt Paket **K3**.
2. **Slot-fertig-Ereignis.** Heute nimmt die Anzeige fest Slot 0. Für tearingfreies Flippen braucht Paket D/E
   den zuletzt fertigen Slot: Kandidaten sind die Flip-Zeiger `0x05600320/324` (im AFBD-Vsync `GIC 142` lesen)
   und die Statuspulse INCAP `+0x100`. Paket **K2**.
3. **Echtes Stecken/Ziehen.** Belegt ist nur das Ab- und Anschalten des Ausgangs am Zuspieler und der
   ARISC-HPD-Zyklus. Ob die ARISC auf 5-V-Detect selbst reagiert (dann muss der Kernel nichts tun), ist offen —
   Paket **K4**, und ein echtes Kabelziehen kann nur Marco.
4. **Auflösungswechsel.** Nie gemessen. Erwartung: `SignalChange` mit neuer Geometrie, WCE rechnet neu, Descriptor
   und AFBD-Crop müssen mitgehen. Gehört zu Paket E, sobald `DV_TIMINGS` steht.
5. **Audio** des HDMI-Eingangs: nicht angefasst, eigenes Kapitel (doku/77 §1 Zeile 13).
