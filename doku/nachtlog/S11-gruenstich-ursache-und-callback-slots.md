# S11 - Der Grünstich hat einen Schalter, das Kippen einen Zähler

08.09.2026, 00:00-01:00 · Board-Sitzung mit zwei RE-Agenten im Hintergrund
([`S9`](S9-re-tfd-vincap-icsc.md) Firmware-Farbraumregel, [`S10`](S10-re-cpucomm-callback-slots.md)
cpu_comm-Slots) · Fortsetzung von [`S8`](S8-skalierung-laeuft-und-der-gruenstich.md)

## Das Ergebnis zuerst

1. **Der Grünstich ist ein abgeschalteter Farbwandler in der Aufnahme.** INCAP `0x06940824` Bit 31
   (`MP_ICSC_VINCAP`, 1 = Bypass). Die Firmware schaltet ihn bei jedem Neubau, den unser Descriptor
   auslöst, auf Bypass, weil der Descriptor `yuv420_888` sagt. Danach schreibt die Aufnahme das RGB des
   Zuspielers **ungewandelt** in den NV16-Ring; die Plane liest es als YCbCr → grün.
2. **Er lässt sich ohne Quellenwechsel zurückschalten:** `THal_Vp_SetVideoRange` mit *geändertem* Wert
   (2, dann 0). Gemessen bei 1080p und 720p: `0x824` von `0x8000000B` auf `0x0000000B`, Ring von
   Cb/Cr ≈ Y auf Cb/Cr ≈ 128, Scaler/Strides unverändert, Taskleiste auf der Wand grau.
3. **Das Kippen nach vier bis fünf Wechseln ist ein Slot-Leck im cpu_comm:** der Kernel gibt die Slots
   der MIPS→ARM-Rückrufe nie zurück. Nach 19 Rückrufen (≈ 6 Wechsel à 3) dreht der MIPS-Sender in
   `fifo_isNearlyFull` endlos - Tick steht, Shell tot, jeder RPC `-110`. Am Gerät nachgezählt:
   `CallCmd rd=0 wr=19`, ein freier Slot, `rx_calls 19`.
4. Beides als Patch: **`0123`** (Farbwandler vor der Freigabe zurücksetzen) und **`0124`** (Slot nach
   dem ACK freigeben, `watch` zeigt den eingehenden Pool). Stand beim Schreiben: Module gebaut und
   kompiliert, Vollbau läuft, Abnahme am Gerät folgt unten.

## Das Messinstrument, das den Unterschied gemacht hat

**Den Ring lesen, nicht die Wand fotografieren.** `analyse/hdmi-seq/ringstat.py W H` liest die
Y- und C-Slots aus den AFBD-Zeigern und gibt je Zeilenband Y/Cb/Cr-Mittel aus. Grau muss Cb ≈ Cr ≈ 128
haben. Damit ist die Kette in zwei Hälften geteilt: ist der Ring falsch, liegt es vor dem Ring (Aufnahme);
ist er richtig, dahinter (Plane/Panel). Die Kamera hat automatischen Weißabgleich und ist für Farbe blind.

| Zustand | Taskleiste Y / Cb / Cr | Weißfläche Y / Cb / Cr |
|---|---|---|
| Kaltstart, 1080p, sauber | 40 / 129 / 127 | 219 / 128 / 128 |
| nach dem ersten Wechsel (720p), grün | 40 / **43** / **40** | 225 / **226** / **225** |
| nach `SetVideoRange 2 → 0`, 720p | 40 / 129 / 127 | 225 / 128 / 128 |

Cb ≈ Cr ≈ Y bei Grau heißt: in den drei Ebenen stehen drei gleiche Kanäle - RGB im 4:2:2-Behälter.
Genau das hatte `doku/76` §12.2 am 06.09. schon einmal gemessen und der Handfreigabe der INCAP-Bits
zugeschrieben. Die Zuschreibung war falsch; die Ursache ist dieselbe wie hier.

## Der Mechanismus, aus dem elog auf Stufe 5

Ein Auflösungswechsel läuft in zwei Durchgängen (`elog-run1`, Wechsel 720p → 1080p):

```
2106115  hdmirx  Set Valid Signal 0x20000            HDMI rastet neu ein
2106116  TFD     WriteModules group V_INCAP
                 Signal_Channel HDMI1, Signal_Format RGB_121212, Signal_Range Limit
                 VINCAP_ICSC ==> BT709                                     <- richtig
2106132  win_mgr SetSignalInfo -> UpdateWce           HDMI-Pfad: nur CapWinNode + NRWinNode WriteReg,
                                                      der Scaler bleibt stehen
2106228  vdd     debug_info (VideoDec)                unsere Neuveröffentlichung des Descriptors
2106230  TFD     WriteModules group type[16]
                 Signal_Channel HDMI1, Signal_Format YUV420_888
                 VINCAP_ICSC ==> BYPASS                                    <- der Grünstich
2106250  win_mgr SetSignalInfo/SetCaptureCfg/SetDisplayCfg -> UpdateWce
                 NR/Proc/Panel WriteReg (Scaler folgt), memory_agent_onoff (Capture aus)
```

Der HDMI-Pfad schreibt den Scaler nicht (deshalb bleibt `0117` nötig), der VidDec-Pfad schreibt ihn -
und stellt dabei den Farbwandler ab. Der zweite Schreiber gewinnt.

**Warum die erste Veröffentlichung sauber ist:** auch sie setzt BYPASS (Tick 289944 in `elog-run4`),
aber danach läuft der alte Wiederanlauf über den Quellenwechsel (`Capture laeuft wieder nach 668 ms`),
und der endet mit einem neuen `Set Valid Signal` des HDMI-Pfads → BT709. Ab `0121` (direkte Freigabe
statt Quellenwechsel) fehlt dieser Schritt für alle weiteren Veröffentlichungen - deshalb „ab dem ersten
Wechsel, bleibend".

**Die Regel der Firmware** (`S9` §4): `GetColorSpaceConfig` liest nur Attr 29 `Signal_Format` und
Attr 68 `Signal_ColorSpace`. YUV-Format → `VINCAP_ICSC = BYPASS`; RGB-Format → `= Signal_ColorSpace`.
Attr 29 kommt aus dem Descriptor-Wort 16 (`color_format`); `Signal_Channel` bleibt HDMI1 (aus dem
HDMI-Cache), ist also kein Unterscheidungsmerkmal.

## Die drei Wege, geprüft am Gerät

| Weg | Ergebnis | Bewertung |
|---|---|---|
| HDMI am Zuspieler aus/an (E1), gleiche Geometrie | Ring YCbCr, Scaler bleibt `0xAAAA` | beweist die Richtung, kein Betriebsweg (Blackout, HPD) |
| Descriptor-Wort 16 := 11 (`rgb_888`) | `0x824` → BT709, **aber** AFBD-Format 4 statt NV16, Chroma-Stride 1280, Bild kräftig grün/cyan | **Sackgasse**, wie `S9` §6.4 vorhergesagt; steht seit Juni in DEAD-ENDS |
| `SetVideoRange 2` → `SetVideoRange 0` | `0x824` → BT709, Ring YCbCr, Scaler/Strides unverändert, keine Callbacks verbraucht | **der Weg**; wiederholter gleicher Wert wäre wirkungslos (`S8` hat 0 → 0 gesendet) |

Reihenfolge, damit kein grünes Bild auf die Wand kommt (Marcos Einwand): Capture aus → `SetVideoRange`
→ Capture an. Nachgestellt (Bits 31 in `0x928/0x968` von Hand gelöscht, RPC-Paar, Bits gesetzt): schon der
erste gemessene Rahmen nach der Freigabe ist YCbCr. Der Neubau der Firmware endet ohnehin mit „Capture aus"
(`memory_agent_onoff` unmittelbar nach den WriteRegs), `0123` wartet darauf, korrigiert dann und gibt erst
danach frei.

## Das Kippen: eine Endlosschleife mit Vorwarnung

Beim 4. Wechsel dieser Sitzung (8. dieses Boots) blieb die Firmware stehen. elog-Ende:

```
D/cpucomm [2685178] (./cpu_comm_core.c 473)cmdfifo.type=0, target cpu=0     (endlos, Tick steht)
```

Für diesen Wechsel kam **kein** `SignalChange`-Callback mehr beim Kernel an; die zwei `SetSource`-RPCs
danach liefen in `-110`. Post mortem gesichert (`scratchpad`: `shm-kipp.bin`, `postmortem-kipp-*.txt`,
`elog-run3-switch-kipp.txt`), `S10` hat es ausgewertet: der MIPS-Sender prüft vor jedem Ruf
`fifo_isNearlyFull(CallCmd-Ring des Empfängers)`; der Ring steht bei 19 von 21, weil unser
`command_action` für `chan ≤ 4` nur eine Referenz hineinlegt und niemand sie liest oder den Slot freigibt.
`comm_CallWorkAction` (Prioritätsklasse > 4) macht beides - für die Rückrufe fehlte es.

Vorhersage aus `S10` §5, am frischen Boot geprüft: nach 19 Rückrufen `CallCmd rd=0 wr=19`, `FreeCall frei 1`,
`rx_calls 19` - exakt eine Stufe vor dem Hänger. Die Zahl 20 ist kein Gesamtlimit, sondern die Zahl
gleichzeitig offener Slots; Stock gibt jeden Rückruf-Slot sofort nach dem Kopieren zurück.

## Die Patches

**`0123` media: sun50i-h713-hdmirx** - `h713_hdmirx_restore_icsc()`: liest `0x824`; steht Bit 31,
`SetVideoRange 2`, `SetVideoRange 0`, wartet bis Bit 31 fällt (≤ 500 ms), loggt „Farbwandler: wieder
BT.709 (vor der Freigabe), nach N ms". Im Republish-Pfad: erst warten, bis die Firmware die Capture
abgeschaltet hat (Ende des Neubaus, ≤ 1,5 s), dann Farbwandler, dann die Freigabe von `0122`; nach der
Freigabe und nach dem Quellenwechsel der Erstveröffentlichung eine Kontrolle (soll Leerlauf sein).
`THal_Vp_SetVideoRange` wird beim Probe nachgeschlagen; fehlt es, warnt der Treiber und lässt es.

**`0124` soc: sunxi: cpu_comm** - im `≤ 4`-Zweig von `command_action` Kopie statt `Comm_Add2NewCallFifo`,
nach `SendAckLow` `Comm_ReleaseFreeCall(share_seq_r, entry)`; RETURN nur, wenn der Sender einen erwartet
(gleiche Bedingung wie `comm_CallWorkAction`; die Rückrufe sind NOTIFY). `watch` zeigt zusätzlich
`eingehend CallCmd rd/wr (ungelesen) ; FreeCall rd/wr (frei)` - mit dem Fix muss `ungelesen 0` bleiben.

Beide kompilieren im Container ohne Warnung; Kopien der Module in `scratchpad/ko-quick/`, im NFS-Root
eingespielt (Sicherungen `*.ko.bak-20260908-0100-vor-012x`). Der Vollbau mit der Serie (93 Zeilen) läuft.

## Abnahme

Offizieller Bau der Serie (93 Zeilen, Baum `431a1f88`, FIT `tftp/h713-kernel-netboot.fit`, Module
`mainline/build/modroot.GUT-431a1f88` → NFS-Root), Kaltstart 01:03, Zuspieler gespiegelt, `hy310-tv` mit
`H713_TV_SKALIERTEST=1`, elog Stufe 5 mitgeschnitten (`scratchpad/elog-run5-abnahme.txt`).

| Wechsel | Ziel | `0x824` | Ring Taskleiste Y/Cb/Cr | Scaler `0x05180008` | C-Stride | `rx_calls` | eingehend ungelesen / FreeCall frei | Foto |
|---|---|---|---|---|---|---|---|---|
| Start | 1080p | `0x0000000B` | 40/129/127 | `0x43010000` | `0xF00` | 3 | 0 / 20 | - |
| 1 | 720p | `0x0000000B` | 40/129/127 | `0x3200AAAA` | `0xA00` | 6 | 0 / 20 | `r5-01-720` |
| 2 | 1080p | `0x0000000B` | 40/129/127 | `0x43010000` | `0xF00` | 9 | 0 / 20 | `r5-02-1080` |
| 3 | 720p | `0x0000000B` | 40/129/127 | `0x3200AAAA` | `0xA00` | 12 | 0 / 20 | `r5-03-720` |
| 4 | 1080p | `0x0000000B` | 40/129/127 | `0x43010000` | `0xF00` | 15 | 0 / 20 | `r5-04-1080` |
| 5 | 720p | `0x0000000B` | 40/129/127 | `0x3200AAAA` | `0xA00` | 18 | 0 / 20 | `r5-05-720` |
| 6 | 1080p | `0x0000000B` | 40/129/127 | `0x43010000` | `0xF00` | **21** | 0 / 20 | `r5-06-1080` |
| 7 | 720p | `0x0000000B` | 40/129/127 | `0x3200AAAA` | `0xA00` | 24 | 0 / 20 | `r5-07-720` |
| 8 | 1080p | `0x0000000B` | 40/129/127 | `0x43010000` | `0xF00` | 27 | 0 / 20 | `r5-08-1080` |

Bei jedem Wechsel steht im dmesg zuerst `Farbwandler: wieder BT.709 (vor der Freigabe), nach 0 ms`, dann
`Freigabe: Capture direkt freigegeben, kein Quellenwechsel, nach 166-170 ms` - die Korrektur liegt vor der
Freigabe, kein grüner Rahmen erreicht den Ring. Die Fotos `r5-07-720` und `r5-08-1080` angesehen: Taskleiste
grau, Farben richtig, 720p vollflächig skaliert. Nach 27 Rückrufen (alte Grenze: 19) antwortet die
Firmware-Shell (`cmds`, 917 Byte), der elog-Tick läuft, `GetSource` kommt zurück; der FreeCall-Ring ist
einmal umgelaufen (`rd=0 wr=20` → `rd=6 wr=5`) und hält 20 freie Slots.

**Damit sind (a) Grünstich und (b) Kippen aus `doku/97` §3 erledigt.** Offen bleibt (c): Konsolen-Sperre und
`H713_TV_SKALIERTEST` in `hy310-tv`, sowie die übrigen Auflösungen der `kHalSignalID_*`-Tabelle.

## Betriebswissen aus dieser Sitzung

- **Vor jedem Steckdosen-Neustart `ss -ulnp | grep ':69 '`.** Der TFTP-dnsmasq war weg, das Board stand
  25 Minuten in U-Boot; die Notiz dazu gab es schon, ich habe sie nicht angewandt.
- **Rückruf-Budget je Boot bis zum Fix: 19.** Jeder Auflösungswechsel kostet ~3, jeder Quellenwechsel 2-3.
  `watch` (mit `0124`: Zeile `eingehend`) vorher lesen.
- **`0x06940824` Bit 31 ist der Farbwandler**, direkt lesbar - der schnellste Test auf den Grünstich.
- **Descriptor-Wörter am lebenden Gerät poken** löst den Neubau aus und verstellt AFBD-Stride/-Format;
  unser Treiber repariert das erst beim nächsten Plane-Enable. Nur mit Rückweg.
- **Der elog auf Stufe 5 überläuft** bei einem Neubau; `elog_tail.py --poll 1` verliert weniger.
- Werkzeuge neu: `analyse/hdmi-seq/rd.py` (Register lesen/schreiben, ctypes-Sicht), `ringstat.py`
  (Ring-Chroma), `regpoll.py` (Registeränderungen mit Zeitstempel). Alle auch unter `/root/` am Board.

## Punkt (c): Konsolen-Sperre entfernt, übrige Auflösungen

- `userspace/hy310-tv/main.c`: der Block „der DE-Scaler ist noch nicht programmiert … Konsole bleibt" und der
  Umgehungsschalter `H713_TV_SKALIERTEST` sind raus (Kommentar an der Stelle erklärt, warum). Quer gebaut mit
  `make cross` (Host-Clang gegen `/srv/h713-rootfs`), `hy310-tv.aarch64-linux-gnu` im Repo aktualisiert
  (md5 `a4944fc2…`), am Board als `/root/hy310-tv` eingespielt (Sicherung `/root/hy310-tv.bak-20260908-vor-c`).
  `make install-cross DESTDIR=/srv/h713-rootfs` scheitert vom Host an Rechten (`/usr/local/sbin` gehört root)
- bei Bedarf vom Board aus kopieren. Kein Dienst aktiv, Handstart nach dem Boot.
- Start ohne Schalter bei 720p: Bild sofort da, Scaler `0xAAAA`, `0x824` BT709, Ring sauber (`r5-10`).
- **1600×900:** die HDMI-Firmware rastet nicht ein (`kein Signal`, INCAP bleibt auf 720p, Freigabe aus);
  `hy310-tv` geht sauber auf die Konsole. 1600×900 steht **nicht** in der `kHalSignalID_*`-Tabelle
  (es gibt `XGA1600_1200`, `XGA1440_900`, `XGA1680_1050`, `XGA1280_1024`, `XGA1366_768`, … - vollständige
  Liste per `strings display.bin | grep kHalSignalID_`).
- **1280×1024:** steht in der Tabelle (`kHalSignalID_XGA12801024`), rastete aber innerhalb der 7 s des
  Prüfskripts ebenfalls nicht ein. **Offen:** mit elog Stufe 5 (`SwitchState`, `Set Valid Signal`) prüfen, ob
  die Erkennung länger braucht oder der Modus vom RX abgelehnt wird; ebenso 1440×900/1680×1050.
- Rückweg auf 1080p danach einwandfrei (`r5-13`), 37 Rückrufe im Boot, Slots weiter bei 20 frei - der
  Konsolen-Rückfall bei Signalverlust und die Wiederkehr funktionieren.

## Dateien dieser Sitzung

- Mitschnitte dauerhaft: `re/captures/weltneuheit/s11-20260908/` (elog-Läufe 1-5, dmesg der Abnahme, Post-mortem
  `shm-kipp.bin` + `postmortem-kipp-*.txt`, Register-Polls, Build-Log, die beiden Patches).
- Fotos: `re/captures/weltneuheit/wand-aktuell/r4-*.jpg` (Messreihe), `r5-*.jpg` (Abnahme).
- Werkzeuge: `analyse/hdmi-seq/{rd,ringstat,regpoll}.py`, `wechsel.sh`.
- RE: `doku/nachtlog/S9`, `S10`; IDA-Skripte `analyse/ida/ida_q60` - `ida_q72`, DB-Kopien `db-tfd/`, `db-cpucomm/`.

## Nachtrag 01:40 - VESA-Modi und die EDID

- **1024×768 und 1440×900 (elog Stufe 5):** der HDMI-RX der Firmware sieht die Aktivgeometrie richtig
  (`new timing HActive:0x400 VActive:0x300` bzw. `0x5a0/0x384`), meldet aber alle ~320 ms
  `detect timing failed!!`, weil `numTotalFrameLines` zwischen einem stabilen Wert (813 bzw. 953) und
  wilden Ausreißern (212…770 bzw. 232…870) springt; dazwischen `HdmiRx_Toggle_PD_IDCLK_Reset!`. Ohne
  stabile Messung kein `Set Valid Signal`, also kein Einrasten; `hy310-tv` geht sauber auf die Konsole,
  1080p danach wieder einwandfrei. CEA-Modi (720p/1080p) messen stabil (750/1125 Zeilen).
- **Deep Colour ist es nicht:** unsere EDID bewirbt DC_30/DC_36 (VSDB Byte 6 = `0xB8`, 340 MHz). Mit einer
  EDID ohne diese Bits (`0x80`, Prüfsumme korrigiert; `re/captures/weltneuheit/s11-20260908/hy310-edid.orig.bin`
  ist das Original) nach Kaltstart: identisches Fehlerbild. Original-EDID wieder eingespielt
  (`/lib/firmware/hy310-edid.bin`, Sicherung `…bak-20260908-mit-dc`). `xrandr --set "max bpc" 8` nimmt der
  Zuspieler nicht an (Eigenschaft bleibt 12).
- **Einordnung:** Erkennungsproblem im MIPS-HDMI-RX (TV303-Treiber) für VESA-Timings, nicht in unserer Kette.
  Ansatzpunkte, falls es wichtig wird: RX-Register (0x0709xxxx - gefährlich, nur nach `ResetEDIDModule`),
  Stock-Verhalten mit denselben Quellen vergleichen, `tcd3 dbg` (Mode-Detection-Debug der Shell).
- **Konsole nach dem Rückschalten:** `fb0/blank` stand auf 4 und der Cursor war per DECTCEM versteckt
  (`ESC[?25l`); Quelle nicht auffindbar (`consoleblank` ist 0, kein Skript im Repo sendet es). Nach
  `ESC[?25h` + `cursor_blink=1` blinkt der Cursor (Framebuffer-Hash wechselt im 0,4-s-Takt). Der Fix gehört
  in `hy310-tv` beim Zurückgeben der Konsole (siehe S12).

## Abnahme 2 - Endstand 02:07 (Serie 97, Baum `a0e43f36`, `hy310-tv` als Dienst)

Kaltstart 02:01 mit angeschlossener Quelle (1080p), **kein Handgriff**: `hy310-tv.service` startet per udev bei
19 s, Erstveröffentlichung → `Capture laeuft wieder, nach 653 ms`, Bild steht (`r10-00-autostart`). Danach:

| Schritt | Ergebnis |
|---|---|
| 7 Wechsel 720p ↔ 1080p (`r10-01…03`, `r11-01…04`) | jedes Mal `Farbwandler: wieder BT.709 (vor der Freigabe)`, dann `Capture direkt freigegeben` (164-222 ms); Ring Taskleiste 39/130/127; Scaler `0x3200AAAA` bzw. `0x43010000`; C-Stride `0xA00`/`0xF00` |
| `hy310-tv ctl set range full` + Wechsel | Bereich bleibt `Full` (2), Wandler BT.709, Taskleiste Y 49 statt 39 (Vollbereich sichtbar); `set range auto` zurück |
| `hy310-tv ctl off` | Plane aus, `master n`, `fb0/blank` 0, Cursor blinkt (Framebuffer-Hash wechselt im 0,45-s-Takt, `r10-05-off`) |
| `hy310-tv ctl auto` | Bild sofort zurück (`r10-06-auto`) |
| Slots | 28 Rückrufe, `eingehend … ungelesen 0`, `FreeCall frei 20`, FIFO mehrfach umgelaufen |
| Foto Endstand | `r11-04-1080`: Taskleiste grau, Farben richtig |

Ein Schönheitsfehler wurde dabei gefunden und behoben: die erste Fassung der ENOLCK-Behandlung in `hy310-tv`
schaltete nach 2 s unentschiedener Geometrie auf die Konsole (Wechsel 2, 19:39:37, zehn Sekunden Konsole bei
korrektem Bild); jetzt bleibt der aktuelle Zustand stehen, bis das nächste Ereignis kommt. Die vier Wechsel
danach liefen ohne Auffälligkeit. Der ~1-s-Konsolenmoment je Wechsel ist der echte Signalverlust der Quelle
beim Modewechsel, kein Fehler.

`0128` (Wiederholung des ersten Wiederanlaufs) ist eingebaut und kompiliert; im Kaltstart 02:01 war es nicht
nötig (der Wechsel gelang beim ersten Mal). Der Fall aus 01:55 - Erstveröffentlichung in der HDMI-Neuverhandlung,
Capture bleibt aus - ist der, den es abfängt; die nächste Sitzung sollte ihn einmal provozieren
(Kaltstart mit Quelle, Quelle während der ersten 20 s einmal aus/an).

Dateien: `s11-20260908/elog-run6.txt` (1024×768), `elog-run7.txt` (EDID-Versuch), `journal-hy310-tv-abnahme2.txt`,
`dmesg-abnahme2.txt`, `hy310-tv.aarch64-linux-gnu.56f52db8` (das installierte Programm).

## Nachtrag 08.09., 07:55 - die VESA-Modi laufen; der „Fehler" war mein Testaufbau

Der Nachtrag von 01:40 ist in seiner Schlussfolgerung **falsch**. `xrandr --output HDMI-2 --mode 1024x768`
ohne `--rate` nimmt die **erste** Variante der Modusliste, und die ist auf diesem Zuspieler die 120-Hz-Fassung
(0xdb, 115,5 MHz, vtotal **813**); bei 1440×900 ebenso (0xc7, 182,75 MHz, vtotal **953**). Genau diese
Zeilenzahlen hat der HDMI-RX gemessen - er hat richtig gemessen, die Timings stehen nur nicht in seiner Tabelle,
also `detect timing failed`, Reset, Neumessung (die Ausreißer sind angeschnittene Zählungen nach dem Reset).

Mit `--rate 60` (Skript `wechsel.sh WxH NAME RATE`, eDP aus, damit die Quelle wirklich diesen Modus fährt):

| Modus | Quelle (xrandr) | INCAP `0x874` | Scaler `0x05180008` | Ring Taskleiste | Wand |
|---|---|---|---|---|---|
| 1024×768 @ 60,00 | 65 MHz, vtotal 806 | `0x04000300` | `0x3200B60B` (1024→1440, 4:3 mit Balken) | 48/130/126 | 4:3 mittig, korrekt (`r12-01`) |
| 1440×900 @ 59,90 | 88,75 MHz, vtotal 926 | `0x05A00384` | `0x3200C000` (1440→1920) | 40/129/127 | korrekt (`r12-02`) |
| 1280×1024 @ 60,02 | 108 MHz, vtotal 1066 | `0x05000400` | `0x3200AAAA` (1280→1920) | 40/129/127 | **auf 16:9 gestreckt** (`r12-03`) - Firmware-Proportionstabelle für 5:4 |
| 1600×900 @ 60,00 | 108 MHz, vtotal 1000 | bleibt auf 1280×1024 | - | - | kein Einrasten: 1600×900 steht nicht in `kHalSignalID_*` (nur 1600×1200); Konsole, wie vorgesehen |

Farbwandler jedes Mal `wieder BT.709 (vor der Freigabe)`, Slots stabil (18 Rückrufe, frei 20), Rückkehr auf
1080p sauber. Die EDID-Änderung von 01:xx war damit überflüssig (Original ist eingespielt). Für 1280×1024
ließe sich die Firmware-Breitbildregel über `app set_wm` / `win os` (Shell, doku/98) beeinflussen - nicht
untersucht.

Kleinigkeit am Rande: `QUERY_DV_TIMINGS` meldet nach einem VidDec-Neubau für 1080p `74250000 Hz` (30-Hz-Preset),
weil die Signal-Info der Firmware dann die Bildrate aus unserem Descriptor (`30000`) trägt; die Aufnahme läuft
mit 60 Hz. Kosmetisch, in `hy310-tv ctl status` sichtbar; Descriptor-Wort 13/14 nicht ohne Messung ändern.
