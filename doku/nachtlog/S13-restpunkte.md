# S13 - Restpunkte 08.09.2026 (09:30-10:20): Protokoll

Plan und Kurzfassung der Ergebnisse stehen in [`../99-plan-restpunkte-20260908.md`](../99-plan-restpunkte-20260908.md);
hier der Ablauf mit Zeiten, Messwerten und Dateien. Kernel-Stände: Start Serie 99 (`0130`, Baum `06623efb`),
dann `0131` (`829b1161`), `0132` (`7d23a3ea`), `0133` (`a3097ce7` = **GUT**). `hy310-tv`: `3290f74d` →
`d8ebd805` (Pitch) → `34549c33` (Unit-Texte) → `61d3daab` (sauberes Ende) → **`00460d4a`** (`preset`, `aspect`).
Zwei RE-Agenten liefen parallel ([`S14`](S14-re-picture-mode.md) Bildmodus, [`S15`](S15-re-aspect-regel.md)
Formatregel). Rohdaten: `re/captures/weltneuheit/s13-20260908/`, Fotos `wand-aktuell/r14…r24`.

## 09:32 Kaltstart auf `0130`, Kipp-Provokation (Punkt 1, erster Versuch)

13× (2 s an / 5 s aus) ab 6 s nach `sonoff on` (`toggle.sh`). Board nach 55 s da; erste Veröffentlichung bei
24,1 s Kernelzeit fiel in ein An-Fenster: `Freigabe: Capture laeuft wieder, nach 652 ms`. Kein Treffer.

## 09:37 1366×768 mit elog Stufe 5 (Punkt 4) - Kernel `06623efb`

`wechsel.sh 1366x768 r14-1366x768 59.79`. Firmware: `port1 new timing HActive:0x556 VActive:0x300`,
`Set Valid Signal dwSignal:0x20059`, `AI_SIGNAL_MODE_1366_768`, `WriteModules V_INCAP` (`Signal_Mode ==> 1366_768`,
`VINCAP_ICSC ==> BT709`). Register: `0x874 = 0x05560300`, **`0x924 = 0x00560056`** (rowbyte 86 → 1376 Byte),
`0x928 = 0xe0020300` (frei), `0x824 = 0x0b` (BT.709), Flip-Zeiger wandern (Slot 2), Treiberformat
`NV16M 1366x768, 2 Ebenen a 1049088` (= 1366·768, also falsch, weil Pitch = Breite angenommen).
`hy310-tv`: `Quellgeometrie 1366x768 nimmt die Plane nicht an (… nicht 16x2-ausgerichtet)`; Wand Konsole
(`r14-1366x768.jpg`). Befund: Firmware kann es, wir lehnen ab. elog: `s13-20260908/elog-1366.txt`.

## 09:40 Patch `0131` + `hy310-tv` Pitch

- Treiber: `H713_INCAP_ROWBYTE 0x924`, `rx->stride`, `detect_timings(rx, t, &stride)` (Fallback
  `ALIGN(width,16)` mit Warnung, wenn Y≠C oder Pitch < Breite), `fill_fmt` setzt `bytesperline`/`sizeimage`,
  Statuszeilen `format: … Zeilenabstand N` und `zeilen: N Byte Abstand (0x924 = …)`, `plane_size = stride·h`.
- Plane (`afbd`): `pitches[0] % 16` statt `width % 16`; Ring: `pitches[0] == ALIGN(width, 16)`; ohne Ring
  zusätzlich `pitches[0] == width`. `h713_video_block_m1` rundet Spalten ab (wie die Firmware, gemessen unten).
- `hy310-tv`: `capture_pitch()` (`G_FMT`, Fallback 16er-Regel), `src_pitch`, Dumb-Puffer mit Pitch als Breite,
  Prüfung `width & 15` gestrichen, `puffer`-Zeile zeigt den Pitch.
- Build 09:43-09:46, Baum `829b1161`.

## 09:46-09:52 Template-Unit (Punkt 2) und Kaltstart auf `0131`

`hy310-tv@.service` (`BindsTo=dev-%i.device`, `After=dev-%i.device`, `ExecStart=… -d /dev/%I`), Regel
`SYSTEMD_WANTS+="hy310-tv@%k.service"`, `install-data` entfernt die alte Unit. Am laufenden Board:
`udevadm trigger --action=add /sys/class/video4linux/video1` → `hy310-tv@video1 active running`,
`BindsTo=dev-video1.device`, `dev-video1.device plugged`, Bild nach 110 ms. Kaltstart 09:46 (HDMI-2 am Zuspieler
vorher aus - der Zuspieler schaltete es beim Hotplug selbst wieder ein): Unit per udev aktiv, Freigabe nach 662 ms.

## 09:48 1366×768 mit `0131` - läuft

`wechsel.sh 1366x768 r15-1366x768-fix 59.79`: `Freigabe: Capture direkt freigegeben, kein Quellenwechsel, nach
164 ms`; `hy310-tv`: `puffer 1366x768 NV16, Zeilenabstand 1376`, `bild Plane 38 an`; Status `format: NV16M
1366x768, Zeilenabstand 1376, 2 Ebenen a 1056768 Byte`, `zeilen: 1376 (0x924 = 0x00560056)`; AFBD nach dem
Firmware-Neubau: `0x020 = 0x02ff0555`, **`0x024 = 0x002f0054`** (84 Spaltenblöcke = abgerundet, wie unsere
Formel), `0x048 = 0x03000556`, `0x04c = 0x01800556`, Y-Stride `0x040 = 0x560` (1376), C-Stride `0x044 = 0xac0`
(2752, NV16-Verdopplung erhalten). Wand: vollflächig, scharf, Farbe richtig (`r15-1366x768-fix.jpg`).
Nebenbefund: `ringstat.py 1366 768` → Bus error (nahm Pitch = Breite); 10:18 behoben (Argument P, Vorgabe
Breite auf 16 aufgerundet): bei 1366 Cb/Cr 128,0 in allen vier Bändern, Ring sauber.

## 09:52-09:57 Provokation der ersten Freigabe (Punkt 1) - getroffen

- `unbind`/`bind` (Probe 9 s) setzt „erste Freigabe" zurück; aber nach einem Rebind mit **gleicher** Geometrie
  gibt es keine neue Veröffentlichung (Descriptor unverändert → `publish_video_info` schreibt nichts → keine
  Freigabe nötig; so erklärt sich, dass nach den Rebinds keine `Freigabe:`-Zeile kam).
- Unbind am lebenden Gerät: Unit **gestoppt, aber `failed`** (Programm sah den Geräteverlust vor systemds
  Stop, Rückgabewert 1) → `hy310-tv`: Geräteverlust ist ein sauberes Ende (`ende  das Aufnahmegeraet ist weg`,
  Rückgabewert 0).
- Erster Trigger-Versuch mit festen `sleep`-Offsets: Zuspieler war schneller als die Board-SSH, HDMI ging vor
  dem Start aus, keine Veröffentlichung.
- **Journal-Trigger** (`provoke.sh`): Zuspieler auf 1280×720 (≠ letzte Veröffentlichung 1080p), Unit gestoppt,
  Signal steht; Start der Unit, Journalzeile `bild … Plane` → `xrandr --off` über ControlMaster **106 ms**
  später. Ergebnis 557,6 s: `Freigabe: nach 2000 ms bewegen sich die Flip-Zeiger nicht; liegt ein Signal an?
  Der Quellenwechsel wird wiederholt, sobald eines da ist`; Zustand Capture aus (`0x600202d0`), Farbwandler
  **BYPASS**, Konsole. HDMI an (583,8 s): SignalChange → `hy310-tv` Plane an (583,9) → Wiederholungs-Work nach
  2 s: `Freigabe: Capture laeuft inzwischen von selbst` (586,0 s) - Capture frei, BT.709, Bild 720p vollflächig
  farbrichtig (`r16-0130-wiederholung.jpg`). Der SetSource-Wiederholungszweig wurde nicht gebraucht; er ist
  nur erreichbar, wenn ein Callback kommt, ohne dass die Firmware neu einrastet - am Gerät nicht erzeugbar,
  ohne INCAP von Hand zu schreiben.

## 09:54-10:02 `0132` (Bildmodus-Menü) und `0133` (`aspect`)

- S14 (10:05 fertig): `SetPictureMode` zählt 0 Vivid … 13 Graphic, schreibt keinen Regler, `Get*` sind Stubs.
  → `0132`: `Picture Mode` Menü 0…13 mit den Firmware-Namen, Kommentare korrigiert.
- S15 (10:14 fertig, Kernaussage schon 09:58 vorab genutzt): Formatregel `1000·h/v` mit den Klassen 1:1, 4:3,
  2,21:1, sonst 16:9 = Vollbild; `set_wm`/`Wce_SetWindow` Stubs; **Descriptor-Wort 35** ist der lebende Weg.
- **Test ohne Kernelbau 09:59:** 1280×1024 anliegend (`r17-1280x1024-vor.jpg`, Scaler `0x3200aaaa`),
  Descriptor-Seite `AFBD 0x098 = 0x4d95f000`, Wort 35 per `/dev/mem` := 1 → elog `window_manager.cpp 158
  aspect_ratio:1`, `UpdateWce 320 aspect_ratio : 1`, `display_cfg [285, 0, 1350, 1080][0, 0, 1920, 1080]`,
  `ProcWinNode ratio [62137 x 62137]`; Scaler **`0x3200f2b9`**; Wand 5:4 mit Balken (`r18-1280x1024-w35.jpg`).
  Nebenwirkung wie erwartet: Neubau ohne AFBD-Notifier → Capture aus (`0x60020400`), kein Rearm, `resync`
  hilft nicht; Rückweg über Geometriewechsel (Kernel schreibt Wort 35 = 0). elog `s13-20260908/elog-w35-1280x1024.txt`.
- → `0133`: `enum h713_aspect`, Plane-Enum `aspect` (`auto proportional full 16:9 4:3 zoom`, Vorgabe
  `proportional`), `rec[35] = aspect`, State reset/duplicate/get/set.
- `hy310-tv 00460d4a`: `prop_info/prop_enum_name/prop_enum_parse`, `has_aspect/aspect` (Startwert aus der
  Plane), `add(req, "aspect")` bei jedem Show, `ctl aspect [NAME]` (Plane kurz aus → `evaluate()` baut neu),
  `ctl preset NAME` (Tabelle aus `pq_picturemode.ini [HDMI1]`, erst `picture_mode`, dann neun Regler),
  Statuszeile `format`, Hilfe, README §6a/§8.

## 10:04 Kaltstart auf `GUT-a3097ce7` - Abnahme

- Unit per udev aktiv, `Freigabe: Capture laeuft wieder, nach 643 ms`, `format proportional (aspect 1)`,
  `picture_mode … menu min=0 max=13 default=1 value=1 (Standard)`.
- **1280×1024:** Descriptor `W35 = 1`, Scaler `0x3200f2b9`, Capture frei, BT.709, Balken live
  (`r20-1280x1024-proportional.jpg`). `ctl aspect full` → `konsole`/`bild` innerhalb 100 ms, Freigabe 221 ms,
  Scaler `0x3200aaaa`, gestreckt (`r21-1280x1024-full.jpg`); `ctl aspect proportional` → `0x3200f2b9`.
- **Presets:** `preset cinema` → `list` 50/45/45/50/40, TNR 2, SNR 1, DCI 0, Black 0, Modus 7 (Cinema); Register
  `0x05001234 = 0x002d0000`, `0x05001238 = 0x2d`, `0x05001228 = 0x2800`. `set mode game`, `set mode computer`:
  Capture frei, Scaler unverändert, Bild steht. `preset standard` → Register `0x32`. (`r22-…-nach-presets.jpg`)
- **1366×768 erneut:** Pitch 1376, Bild (`r23-1366x768-neu.jpg`). Zurück 1080p gespiegelt.
- **BindsTo Rückrichtung:** `unbind` → `ende  das Aufnahmegeraet ist weg (poll 0x1a) -- die Unit folgt dem
  Geraet`, `Result=success ActiveState=inactive`; `bind` → Unit nach 1 s aktiv, `NRestarts=0`, Bild.
- Abschließender Kaltstart 10:09: alles wie oben (`r24-endstand-1080p.jpg`).

## 10:20-10:25 Nachtrag: Presets gehören zum Start

Marcos Frage, ob die Voreinstellungen bei der Display-Initialisierung gefahren werden: bisher nein. Gemessen:
die neun PQ-Werte überleben `resync`, 1080p→720p→1080p und HDMI aus/an (Cinema-Register `0x2d` blieben) → einmal
beim Start reicht. `hy310-tv fd5d89c4`: `-p PRESET` (Vorgabe standard) nach `capture_select_input`, `-g LUT`
(Stock-Gamma 2,2 aus `hy310-pq`, Vorgabe `/usr/local/share/hy310-tv/gamma-standard.bin`) als `GAMMA_LUT` auf CRTC 36
beim Start (Master kurz genommen) und bei jedem Show. Wand: Median 84 → 57 (`r24` → `r26-1080p-gamma22.jpg`);
Gegenprobe: das Hintergrundbild des Zuspielers hat Median 27/255, ohne LUT stand es hellgrau - die Kurve ist
richtig. DE2-Bank liest konstant zurück (`0x0092ceb5`), kein Instrument. CTM: Stock neutral, nichts zu tun.

## 10:30-10:40 A/B mit Testbild (Marco: „mit Bild bestätigt?")

Testbild am Zuspieler (`xviewer -f`, Farbbalken / 16-Stufen-Graukeil / Farbfelder), gleiche Kamera, Auswertung
`scratchpad/wedge.py` (Graukeil-Stufen in Kamera-L, Sättigung der Balken):

| Zustand | Foto | Graukeil (Spanne) | Sättigung gelb/cyan/blau |
|---|---|---|---|
| Kaltstart, `-p none -g none` (Reset) | `r28` | 120…103…160 (60), dunkle Stufen kaum getrennt | 0,24 / 0,40 / 0,67 |
| `-p standard -g none` | `r29` | wie r28 (59) | 0,22 / 0,39 / 0,65 (Sättigung 60→50) |
| dazu Regler 49→50 erzwungen | `r30` | identisch zu r29 (59) | identisch |
| `-p standard` + Gamma 2,2 | `r27`/`r31` | 138…74…187, Stufen klar getrennt | Balken wie r29, Weiß/Gelb heller |

**Befund Firmware:** ein `Set` mit dem Wert, den ihr Software-Zustand schon hat (Start 50), schreibt **kein
Register** - nach einem Kaltstart blieb `preset standard` für Kontrast/Schärfe/Helligkeit ohne Registerschreiben
(`0x05001234 = 0`), erst `49` dann `50` schrieb `0x32`. Bild identisch (r29 = r30): der Reset-Inhalt *ist* die 50.
`hy310-tv 6f046f93` stupst die fünf Regler deshalb um eine Stufe an, bevor es setzt - der Zustand ist danach
bekannt, nicht nur angenommen. Reihenfolge im Journal: `plane` → `gamma` → `preset` → `steuerung` → `signal` →
`bild`; das erste Bild erscheint mit fertigen Werten.

## Dateien

- Patches `0131` - `0133` (Kopien in `s13-20260908/`), Serie gesichert `patches-snapshots/20260908-0940-vor-0131/`
  und `…-1015-serie102/`; FITs `tftp/h713-kernel-netboot.fit.GUT-a3097ce7`, Sicherungen `*.bak-20260908-vor-013x`.
- `userspace/hy310-tv/`: `main.c`, `hy310-tv@.service`, `99-hy310-tv.rules`, `Makefile`, `README.md`.
- Werkzeuge: `s13-20260908/provoke.sh` (+ `provoke-0956.log`), `scratchpad/toggle.sh` (Kipp-Takt, verworfen).
- Memory: `ring-pitch-rowbyte-1366`, `aspect-descriptor-wort-35`, `picture-mode-ohne-preset`,
  `hy310-tv-dienst-und-ctl` (aktualisiert).
