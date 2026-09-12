# Plan Restpunkte 08.09.2026 — nach Grünstich, Kippen und `hy310-tv`

> **Erledigt 08.09.2026, 10:40.** Alle Punkte umgesetzt und abgenommen, Protokoll in [`nachtlog/S13-restpunkte.md`](nachtlog/S13-restpunkte.md); Ergebnisse unten je Punkt. Presets/Gamma beim Start: siehe Abschluss-Abschnitte.

Stand 08:30. Fünf Punkte aus dem Handoff plus eine Frage für den Abend. Je Punkt: was gemessen wird,
woran man Erfolg erkennt, was geändert wird, was schiefgehen kann. Ergebnisse werden unten je Punkt
nachgetragen; das Protokoll steht in `nachtlog/S13-restpunkte.md`.

## 1. `0128` provozieren (Erstveröffentlichung trifft auf Neuverhandlung)

**Fehlfall:** die erste Descriptor-Veröffentlichung des Boots löst den Quellenwechsel aus; findet der
kein Signal (Quelle verhandelt gerade), bleibt die Capture aus, bis jemand wechselt (01:55 gesehen).
**Provokation:** Kaltstart; ab ~50 s nach dem Einschalten schaltet der Zuspieler HDMI-2 im 5-s-Takt aus
und an, bis der Dienst gestartet und die erste Veröffentlichung durch ist; danach bleibt HDMI an.
**Kriterium:** im dmesg `Freigabe: nach 2000 ms bewegen sich die Flip-Zeiger nicht … wird wiederholt`
gefolgt von `Signal ist zurueck (1920x1080), der Quellenwechsel wird wiederholt` und
`Capture laeuft wieder`; Bild steht ohne Handgriff (`hy310-tv ctl status`: Plane an, BT.709).
**Risiko:** Trefferquote der Provokation; notfalls zweimal.

## 2. Template-Unit mit `BindsTo`

**Ziel:** die Unit folgt `/dev/videoN` in beide Richtungen: udev startet `hy310-tv@videoN`, das Gerät
bindet sie (`BindsTo=dev-%i.device`, `After=`), verschwindet es, stoppt sie sauber statt in die
Neustartgrenze zu laufen. `hy310-tv.service` bleibt als Alias/Anker für `systemctl status hy310-tv`
weg — ein Name, ein Dienst.
**Kriterium:** Kaltstart ohne Handgriff → `hy310-tv@video1` aktiv; `modprobe -r`/Rebind des Treibers →
Unit stoppt (`inactive`), Bind → startet wieder.
**Risiko:** Rebind des hdmirx-Treibers am lebenden Gerät ist selbst nicht abgenommen (Probe-Sequenz mit
EDID/HPD); der Test wird auf einen Rebind beschränkt, danach Kaltstart.

## 3. `picture_mode` liest die fünf Regler nach

**Messen:** je Modusnummer 0…7 `SetPictureMode N`, dann die PQ-Register (`0x05001234` Helligkeit/Kontrast,
`0x05001238` Sättigung/Farbton, `0x05001228` Schärfe) und die Firmware-`Get`-Routinen
(`THal_Vp_GetBrightness` …) lesen; gegen `pq_picturemode.ini [HDMI1]` legen → Nummer ↔ Name ↔ Werte.
**Ändern:** Treiber (`0130`): nach `SetPictureMode` die fünf Controls auf die gelesenen Werte setzen, ohne
sie erneut zu senden (Sync-Flag im `s_ctrl`); `hy310-tv ctl list` zeigt dann die Wahrheit. Falls die
`Get`-Routinen nichts Brauchbares liefern: Tabelle aus der Messung im Treiber.
**Kriterium:** `set mode N` → `list` zeigt die Werte, die die Register tragen; Wand ändert sich sichtbar
(Foto), `set brightness` danach wirkt vom neuen Stand aus.
**Risiko:** Presets könnten mehr als fünf Regler ändern (TNR/SNR/DCI/Gamma) — dann alle nachziehen.

## 4. 1366×768 — Firmware oder wir?

**Messen:** Zuspieler auf 1366×768 @ 60 (nur HDMI-2), elog Stufe 5 mitlesen: rastet die Firmware ein
(`Set Valid Signal`, INCAP `0x874` = 0x055e0300)? Welchen Zeilenabstand schreibt sie (`0x924` rowbyte,
erwartet 86 → 1376 Byte)? Wo liegen die Ring-Slots, stimmt der Chroma-Versatz?
**Wenn Firmware einrastet (dann ist es unser Problem):** `hy310-tv` baut den Puffer mit Breite 1366 und
Zeilenabstand `rowbyte·16`; die Plane-Prüfung im Treiber (`0107`, 16-Ausrichtung der Breite) wird auf
„Zeilenabstand durch 16 teilbar" gelockert; Descriptor-Wörter 2–5/22 bekommen Breite bzw. Stride.
**Kriterium:** Bild vollflächig ohne Umbruch, Ring-Chroma 128, Foto.
**Risiko:** AFBD-Zuschnitt bei Breite ≠ Stride; Descriptor mit Stride ≠ Breite ist ungetestet.

## 5. 5:4 (1280×1024) wird gestreckt

**Klären:** wie die Firmware das Format entscheidet (`windows_manager_util.c:577` druckt `ratio` und die
Bereiche 4:3 1320–1346, 16:9 1760–1795, 21:9; 5:4 = 1250 liegt außerhalb → `kAFDMapTable`-Zeile?), ob
`app set_wm` (Breitbildmodus, Shell) eine Einstellung hat, die 5:4 mit Balken zeigt, und ob das ohne Shell
erreichbar ist (RPC? Descriptor-Fensterwörter?).
**Messen:** `app set_wm 0…N` über `mipsshell.py` bei anliegendem 1280×1024, je Wert Scaler `0x05180008/3C`
und Foto.
**Ändern:** wenn ein Modus passt und ein Weg ohne Shell existiert → `hy310-tv ctl` bekommt `aspect`; sonst
Doku „Firmware-Regel, per Shell umschaltbar".
**Risiko:** Shell-Kommandos verändern den Zustand der Anzeige; Rückweg Quellenwechsel/Kaltstart.

## 6. 1600×900 — Grenze

Nicht in `kHalSignalID_*`; bleibt. (Marco: nicht unterstützte Größen sind die Grenze.)

## Für heute Abend: PQ-Presets — wird das überhaupt gesendet?

**Frage (Marco):** Werden die Bildvoreinstellungen (`hy310-pq`, Paket G: Gamma-LUT, Bildmodus-Werte je
Eingang aus `pq_picturemode.ini`, Weißabgleich, CTM) heute beim Start mitgesendet — oder läuft das Gerät
nur mit dem, was die Init-Sequenz des Treibers schickt (`SetPictureMode 1`, TNR 2, SNR 1, DCI 2,
BlackExtension 1, VideoRange 0) und den Ruhewerten 50/50/60/50/50?
**Testplan:**
1. `hy310-tv ctl list` nach Kaltstart notieren; PQ-Register `0x05001228…0x05001280` und die Gamma-LUT am
   CRTC (`0095`, `GAMMA_LUT`-Property) lesen: steht dort die Werkskurve oder Identität?
2. `hy310-pq` laufen lassen (README in `userspace/hy310-pq`), dieselben Register/LUT erneut lesen; Foto
   vorher/nachher (Graustufenkeil vom Zuspieler, `analyse/hdmi-seq/pat_load.py` oder ein Testbild).
3. Entscheiden, ob `hy310-pq` als Teil des Dienstes (oder als eigene Unit nach `hy310-tv`) laufen soll.
**Kriterium:** Register/LUT vor und nach `hy310-pq` unterscheiden sich wie in `doku/81` vorhergesagt;
Foto zeigt die Gammaänderung.

---

## Ergebnisse

### 4. 1366×768 — es war unser Problem (gemessen 09:37, Kernel `06623efb`, elog Stufe 5)

- Firmware rastet ein: `port1 new timing HActive:0x556 VActive:0x300`, `Set Valid Signal dwSignal:0x20059`,
  `signal id AI_SIGNAL_MODE_1366_768`, TFD-Gruppe `V_INCAP` mit `Signal_Mode ==> 1366_768`, `VINCAP_ICSC ==> BT709`.
- INCAP `0x874 = 0x05560300` (1366×768), **`0x924 = 0x00560056` → rowbyte 86 → 1376 Byte je Zeile** (10 Byte
  Füllung), Capture freigegeben (`0x928 = 0xe0020300`), Flip-Zeiger wandern (Slot 2), Farbwandler BT.709.
- Abgelehnt haben *wir*: `hy310-tv` („nicht 16x2-ausgerichtet") und die Plane-Prüfung aus 0107
  (`fb->width % 16`, `pitches[0] == width`). Der Ring hat aber nie „Zeilen eine Breite auseinander", sondern
  eine rowbyte·16 auseinander — für 1920 und 1280 fällt das zusammen, für 1366 nicht.
- Fix: Kernel **0131** (Treiber liest `0x924`, meldet `bytesperline`/`sizeimage` = Zeilenabstand, Statuszeile
  `zeilen:`; Plane verlangt `pitch == ALIGN(width, 16)` statt `width % 16 == 0`) und `hy310-tv`
  (`capture_pitch()` per `G_FMT`, Dumb-Puffer mit dem Pitch als Breite, Prüfung auf 16er-Breite gestrichen).
  Abnahme am Board: siehe unten.
- Rohdaten: `re/captures/weltneuheit/s13-20260908/elog-1366.txt`, Foto `wand-aktuell/r14-1366x768.jpg` (Konsole).

### 2. Template-Unit — udev-Start abgenommen (09:50)

`hy310-tv@.service` (`BindsTo=dev-%i.device`, `After=dev-%i.device`, `ExecStart … -d /dev/%I`), Regel
`SYSTEMD_WANTS+="hy310-tv@%k.service"`, alte `hy310-tv.service` entfernt (Makefile `install-data` räumt sie
weg). `udevadm trigger --action=add /sys/class/video4linux/video1` → `hy310-tv@video1` `active running`,
`systemctl show`: `BindsTo=dev-video1.device`, `After=… dev-video1.device`, Gerät `plugged`; Bild nach 110 ms.
Rückrichtung (unbind → Unit stoppt) folgt am Ende des Board-Laufs, danach Kaltstart.

### 3. `picture_mode` — es gibt nichts nachzulesen (RE-Bericht `nachtlog/S14-re-picture-mode.md`, 10:05)

- `THal_Vp_SetPictureMode(N)` zählt in der Firmware **0 Vivid, 1 Standard, 2 Mild, 3 Game, 4 Calibrated,
  5 Calibrated_Dark, 6 Computer, 7 Cinema, 8 Home, 9 Sports, 10 Shop, 11 Animation, 12 HDR, 13 Graphic**
  (`dword_8B1F2120` → TSE-Attribut `UI_PictureModes`); 14/15 → Standard, ≥ 16 „not supported".
- Der Wechsel schreibt **kein PQ-Register und keinen der neun Regler**: er setzt das TFD-Filterattribut,
  schreibt für HDMI die TSE-Gruppe `V_INCAP` neu, meldet N dem MemoryAgent, bei 3/6 zusätzlich
  `SetLowLatency`/`Refresh` (WCE). Die Preset-Werte der INI liest die ARM-Seite (`libvideo.so`) und schickt
  sie als Einzel-RPCs — Stock sendet die fünf Regler für `standard` nie.
- `THal_Vp_GetBrightness/…/GetSNR` sind **Stubs (`return 0`)**, `GetVideoRange` konstant 1; nur
  `GetPictureMode` liefert den zuletzt gesetzten Wert. Deckt sich mit den I1-Messungen.
- **Folge:** die V4L2-Controls bleiben nach `set mode` wahr; ein Rücklesen ist gegenstandslos. Umsetzung
  stattdessen: `Picture Mode` als **Menü mit den Firmware-Namen 0…13** (Kernel), und ein Userspace-Preset
  (`hy310-tv ctl preset standard|cinema|vivid|game|computer|hdr`), das Modus + neun Regler aus
  `pq_picturemode.ini [HDMI1]` sendet (Tabelle S14 §4). Vor Freigabe von 3/6 am Board messen (S14 §5).

### 2. (Fortsetzung) `unbind` am lebenden Gerät (10:08)

`echo hdmi-rx > unbind`: `/dev/video1` weg, `dev-video1.device` inactive, `hy310-tv@video1` **gestoppt** — aber
als `failed` (exit-code 1), weil `hy310-tv` den Geräteverlust vor systemds Stop bemerkt und mit Fehler endet.
Kein Neustartversuch (BindsTo greift). Nachbesserung: Geräteverlust (`ENODEV`/`POLLERR`) ist ein sauberes Ende
mit Rückgabewert 0 → Unit `inactive`.

### 1. `0128`/`0130` provoziert — Fehlfall erzeugt, Wartepfad läuft (09:56, Kernel `829b1161` = Serie 100)

- **Kipp-Takt taugt nicht:** 13× (2 s an / 5 s aus) ab Einschalten traf kein Fenster (erste Veröffentlichung fiel
  in ein An-Fenster, Freigabe nach 652 ms). Der Zuspieler schaltet HDMI-2 beim Hotplug außerdem selbst wieder
  ein; „HDMI aus beim Boot" hält deshalb nicht.
- **Rebind statt Kaltstart:** `unbind`/`bind` des Treibers (Probe 9 s) setzt „erste Freigabe" zurück — aber nur
  eine **geänderte** Geometrie wird veröffentlicht (gleicher Descriptor → kein Neubau → keine Freigabe nötig).
  Also Zuspieler auf 1280×720 (ungleich der letzten Veröffentlichung), Unit gestoppt, Signal steht.
- **Journal-Trigger** (`s13-20260908/provoke.sh`): Unit starten; sobald das Journal `bild … Plane` meldet,
  `xrandr --off` am Zuspieler über eine offene ControlMaster-Verbindung — HDMI war 106 ms nach der Zeile weg.
- **Befund:** `Freigabe: nach 2000 ms bewegen sich die Flip-Zeiger nicht; liegt ein Signal an? Der
  Quellenwechsel wird wiederholt, sobald eines da ist` (557.6 s); Zustand Capture aus, Farbwandler BYPASS,
  Konsole. HDMI wieder an (583.8 s): SignalChange → Wiederholungs-Work nach 2 s Beruhigung →
  `Freigabe: Capture laeuft inzwischen von selbst` (586.0 s) — die Firmware hatte mit dem neuen Einrasten
  die Capture und den Farbwandler (BT.709) selbst zurückgesetzt; `hy310-tv` Plane an ohne Handgriff, Foto
  `r16-0130-wiederholung.jpg` (720p vollflächig, Farbe richtig).
- **Nicht erreicht:** der Zweig „Signal steht, Capture bleibt aus → SetSource-Wiederholung mit 1000 ms Pause".
  Jedes neue Einrasten heilt die Capture selbst; ohne Handschrift an INCAP (verboten) lässt sich „Callback ohne
  Neu-Einrasten" nicht erzeugen. Der Zweig bleibt als Netz für den 01:55-Fall (Quelle verhandelte beim Boot),
  ist kompiliert und wird vom Guard davor abgedeckt.

### 5. 5:4 — die Firmware hat den Schalter, wir haben ihn nie gesetzt (RE `nachtlog/S15-re-aspect-regel.md`, Test 09:59)

- **Regel:** `GetSignalAspectCode` rechnet `ratio = 1000·h/v` und kennt nur 1:1, 4:3 (1301–1365), 2.21:1 —
  alles andere ist 16:9 = Vollbild strecken; 5:4 (1250) und 16:10 (1600) fallen darauf. `app set_wm`, RPC
  `THal_Vp_Wce_SetWindow`, `Pixel2Pixel`: Stubs. **Der lebende Weg ist Descriptor-Wort 35** (`aspect_ratio`,
  `kHalDisplayAspectRatio_{Auto 0, KeepSourceAr 1, Full 2, 16_9 3, 4_3 4, Zoom 5}`), das der Kernel bisher mit 0
  (Auto = AFD-Tabelle) schreibt; `CompareFrameInfo` vergleicht es, eine Änderung allein löst den Neubau aus.
- **Test ohne Kernelbau:** bei anliegendem 1280×1024 Wort 35 der lebenden Descriptor-Seite (`0x4d95f000`,
  Offset 0x8C) per `/dev/mem` auf 1 gesetzt → elog `window_manager.cpp 158 aspect_ratio:1`,
  `display_cfg [285,0,1350,1080]`, Scaler `0x05180008 = 0x3200f2b9` (vorher `0x3200aaaa`), ProcWinNode
  `ratio [62137 x 62137]`; Wand: **5:4 mittig mit Balken** (Foto `r18-1280x1024-w35.jpg`). Kodierung roh (1),
  nicht ×16. Erwartete Nebenwirkung: der Neubau löscht die Capture-Freigabe, und weil der Umweg am
  AFBD-Notifier vorbei ging, gab es keine Freigabe (Standbild; `resync` hilft nicht) — der Rückweg über eine
  Geometrieänderung (Kernel schreibt Wort 35 = 0) stellte alles wieder her.
- **Umsetzung:** AFBD-Plane-Eigenschaft `aspect` (Enum mit den sechs Firmware-Namen, Vorgabe `proportional`
  = 1: für 16:9 Identität, 4:3 wie bisher, 5:4/16:10 mit Balken) → Wort 35; `hy310-tv ctl aspect NAME`.
  Rohdaten `s13-20260908/elog-w35-1280x1024.txt`.

### Abschluss 10:15 — Kernel `GUT-a3097ce7` (Serie 102), `hy310-tv` `00460d4a`

- **2 fertig:** `unbind` → `ende  das Aufnahmegeraet ist weg (poll 0x1a) -- die Unit folgt dem Geraet`,
  `Result=success ActiveState=inactive`; `bind` → udev startet `hy310-tv@video1` in 1 s, `NRestarts=0`, Bild.
  Kaltstart: Unit aktiv, Freigabe nach 643 ms.
- **3 fertig:** Kernel `0132` (`Picture Mode` Menü 0…13 mit Firmware-Namen), `hy310-tv ctl preset NAME`.
  Gemessen: `preset cinema` → Regler 50/45/45/50/40, TNR 2, SNR 1, DCI 0, Black 0, PQ-Register
  `0x05001234 = 0x002d0000` (Kontrast 45), `0x05001238 = 0x2d` (Sättigung 45), `0x05001228 = 0x2800`
  (Schärfe 40); `preset standard` → `0x32` überall. `set mode game`/`computer`: Capture bleibt frei, Scaler
  unverändert, Bild steht (S14 §5 Nebenwirkung unkritisch).
- **4 fertig:** Kernel `0131` + `hy310-tv` Pitch aus `G_FMT`: 1366×768 vollflächig, Zeilenabstand 1376,
  Farbwandler BT.709, Fotos `r15-1366x768-fix.jpg`, `r23-1366x768-neu.jpg`. Nebenbefund: `ringstat.py`
  nahm Pitch = Breite an und stürzte bei 1366 ab — behoben (optionales drittes Argument P, Vorgabe
  Breite auf 16 aufgerundet); bei 1366 Cb/Cr 128,0 in allen Bändern.
- **5 fertig:** Kernel `0133` Plane-Eigenschaft `aspect` (Vorgabe `proportional`), `hy310-tv ctl aspect`.
  Live bei 1280×1024: Wort 35 = 1, Scaler `0x3200f2b9`, Capture frei, **Balken auf der Wand**
  (`r20-1280x1024-proportional.jpg`); `ctl aspect full` → Plane kurz aus/an, Freigabe 221 ms, Scaler
  `0x3200aaaa`, gestreckt (`r21-1280x1024-full.jpg`); zurück ebenso.
- **1 (siehe oben):** Fehlfall provoziert, Wartepfad greift, Firmware heilt beim Neu-Einrasten selbst;
  SetSource-Wiederholungszweig bleibt unbetreten.

### Erledigt 10:25 — Presets gehören zum Start (Marco: „das gehört zum Userspace")

- **Gemessen:** die neun PQ-Werte überleben `resync` (SetSource), Auflösungswechsel 1080p→720p→1080p und
  HDMI aus/an (Register hielten die Cinema-Werte `0x2d`). Also **einmal beim Start**, kein Nachsenden bei
  Bildwechseln. Reset-Zustand ohne Preset: `0x05001234 = 0`, `0x05001228 = 0x01000000`, Sättigung `0x3c` —
  nicht „standard". Es gibt einen Eingang (HDMI-1) und die INI-Zeilen HDMI1/2/3 sind identisch.
- **`hy310-tv`:** `-p PRESET` (Vorgabe `standard`, `none` = aus), gesendet nach `capture_select_input`;
  Journal `preset standard: mode=1 …`, Register danach `0x32`. `-g LUT` (Vorgabe
  `/usr/local/share/hy310-tv/gamma-standard.bin`, `none` = Identität): Stock-Gamma 2,2 als `GAMMA_LUT` auf CRTC 36,
  einmal beim Start (Master kurz genommen) und bei jedem Show; bleibt über `ctl off`/`auto`. Wand: Mitten deutlich
  dunkler (Foto-Median 84 → 57, `r24` vs `r26-1080p-gamma22.jpg`) — das ist die Kurve, die die Vendor-Daten für
  alle Modi vorschreiben (Index 3 = 2,2, doku/81 §4); die DE2-Bank ist nicht rücklesbar. Weißabgleich (CTM) ist
  in den Stock-Daten neutral → nichts zu senden. `hy310-pq` bleibt Rechner/Erzeuger der LUT-Datei.
- **A/B mit Testbild (S13, 10:30–10:40):** Reset → Preset → Preset+Gamma fotografiert (`r28`, `r29`/`r30`, `r31`).
  Sättigung 60→50 messbar, Gamma trennt die Graustufen sichtbar. Firmware-Falle: ein Set mit unverändertem
  Software-Wert (Start 50) schreibt kein Register — `hy310-tv` stupst die fünf Regler um eine Stufe an (Bild
  identisch, Register danach belegt). Reihenfolge: Gamma → SetSource → Modus → Regler → erstes Bild.
- **Gegenprobe an der Quelle:** das Hintergrundbild des Zuspielers ist dunkel (Median 27/255). Ohne LUT stand es
  hellgrau an der Wand (`r24`), mit der 2,2-Kurve dunkel (`r26`) — die Identität war das falsche Bild, die Kurve
  ist die richtige. Rückweg trotzdem vorhanden: `-g none` in der Unit.

### Heute Abend (ursprüngliche Frage, damit beantwortet)

Die **Hersteller-Presets wurden bisher nicht gesendet** — nur die Init-Sequenz des Treibers
(`SetPictureMode 1`, TNR 2, SNR 1, DCI 2, Black 1, VideoRange 0) und die Ruhewerte 50/50/60/50/50. Seit heute
schickt `hy310-tv ctl preset standard` genau die INI-Zeile (Sättigung 50 statt Ruhewert 60!). Offen für den
Abend: (1) soll `preset standard` beim Start automatisch gesendet werden (dann als Schritt in `hy310-tv` nach
der ersten Plane oder als eigene Unit)? (2) `hy310-pq` (Gamma-LUT am CRTC, Weißabgleich, CTM) — Register/LUT vor
und nach dem Lauf lesen, Foto mit Graustufenkeil, dann entscheiden, ob es Teil des Dienstes wird (Plan oben).
