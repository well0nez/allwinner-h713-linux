# S26 — RE: DELAY1 (`0x8D00`) — warum es bei uns still ist und was es zum Laufen braucht

**08.09.2026, reine statische Analyse. Kein Board; `mainline/`, `userspace/`, `re/vendor/` unangetastet.**
Auftrag `analyse/audio/arbeit/f8-delayline/AUFTRAG.md` (F8, Fragen 1–4). IDA-Arbeitskopien **nur** in
`analyse/ida/db-audio-f8/` (`libmspdriver.so.i64`, `libmspsound.so.i64`, `audio.primary.ares.so`,
`snd_alsa_trid.ko` → neue DB angelegt). Skripte `analyse/audio/arbeit/f8-delayline/ida_f8_01.py … _08.py`.
Rohausgaben `re/captures/weltneuheit/audio-f8-01…02` (libmspdriver), `…-03…05` (snd_alsa_trid.ko: Namen,
Dekompilate, `.data` + Rohdisassembly), `…-06` (Audio-HAL). **belegt** = aus Dekompilat/Disassembly/Stock-Datei
ablesbar; **vermutet** = geschlossen, nicht gemessen.

---

## 0. Kurzfassung

| Frage | Antwort | Stand |
|---|---|---|
| Warum ist DELAY1 still? | **Zwei Dinge fehlen gleichzeitig.** (a) DSP-Wortregister **`0x0034`** ist bei uns 0, also **`rDEL_EN` (Bit 15) = 0**; Stock setzt `0x0034 = 0x8488`. (b) Das Modul arbeitet über eine **Speicherschleife** DSP → AUDIF-Delayline → AUDBRG-WLB → DRAM-Ring → AUDBRG-RLB → AUDIF → DSP; ohne Ring kein Rückweg, also kein Ausgang | (a) belegt; (b) belegt, dass Stock die Schleife **immer** einrichtet — dass sie zwingend ist: **vermutet** |
| DSP-Register des Moduls | nur **`0x0034`** (16 bit) + Byteregister **`0x8036/37/38/39`, `0x804D`** (je Bit 0). **Länge, Kanal-Enable, Speicherbasis stehen *nicht* im DSP** | belegt |
| Was Stock schreibt | `Sound_Path_Init` → `SetDelayLineMode(0x8D00, 0x08910000)` ⇒ `0x0034 := 0x8488`, die fünf Byteregister Bit 0 := 0 | belegt |
| Puffer | **4 × `0x40000` (256 KiB)** physisch zusammenhängend, 16-Byte-Raster, alle im selben 256-MiB-Fenster | belegt |
| Stock-Verzögerung | INI-Sollwert **0 ms** (`spk_delay = 0` in allen Betriebsarten), Treiber klemmt auf das Minimum **100 Ticks ≈ 2,05 ms** — die Linien **laufen** | belegt |
| Lippensynchronität? | ja, dafür gedacht (HAL `spk_delay`/`spk_delay_offset`, 0…500 ms); HY310-Stock nutzt 0 ms | belegt |
| Ergebnis | Schreibfolge **§6** | — |

---

## 1. DELAY1 im DSP

### 1.1 Moduldeskriptor (`libmspdriver Init_Module_Delay@0x15300`, Log `audio-f8-02` Z. 2 ff.)

`mod_delay1@0x28CB0`: `+0` ID 160, `+4` Basistyp **160** (`AUD_MODULE_DELAY`, von `MAPI_AUD_CFG_SetDelayLineMode@0xE490`
geprüft), `+8` `AUD_MODULE_DELAY1`, `+72/+76` **8 Ein-/8 Ausgänge**, `+80/+84` Portlisten,
**`+104` `func_cfg_setdelaylinemode`**, `+108` `…getdelaylinemode`. `UnInit_Module_Delay@0x1580C` und
`Mute_Module_Delay@0x194EC` sind **leer**. Ports: in0/1 → DSP-Reg `0x0036` (Maske `0xFF00`/`0x00FF`),
in2/3 → `0x0037`, in4/5 → `0x0038`, in6/7 → `0x0039`; Ausgangs-Quellcodes out0…out7 =
`0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35` (deckt sich mit S23 §4.2). `DELAY2…4` (`0x8D01…03`, im Preset
2-kanalig) benutzen **dieselben globalen Register** — die Modul-ID geht nur ins Log.

### 1.2 `func_cfg_setdelaylinemode@0x11B74` — Bitkarte

Rohdisassembly `audio-f8-08` (`0x11BC8`–`0x11C6C`), Dekompilat `audio-f8-02` Z. 293 ff.:

```
WriteRegMaskWord(0, 0x804D, 0x01, (mode>>11)&1)      WriteRegMaskWord(0, 0x8038, 0x01, (mode>>14)&1)
WriteRegMaskWord(0, 0x8036, 0x01, (mode>>12)&1)      WriteRegMaskWord(0, 0x8039, 0x01, (mode>>15)&1)
WriteRegMaskWord(0, 0x8037, 0x01, (mode>>13)&1)
WriteRegMaskWord(0, 0x0034, 0xFFFF, (0xC00&(mode>>10)) + (0x1000&(mode>>7)) + (0x200&(mode>>13))
                                  + (0x180&(mode>>16)) + (0x40&(mode>>19)) + (0x20&(mode>>21))
                                  + (0x18 &(mode>>24)))
WriteRegMaskWord(0, 0x0034, 0x8000, ((mode>>16)&1)<<15)      /* Log-Format: "rDEL_EN = %x" */
```

Feldgrenzen von `0x0034` (belegt; Bedeutung außer Bit 15 **vermutet**): Bit 15 ← mode[16] = **`rDEL_EN`**;
Bits 14:13 von `Set` immer 0; Bit 12 ← mode[19]; Bits 11:10 ← mode[21:20]; Bit 9 ← mode[22];
Bits 8:7 ← mode[24:23]; Bit 6 ← mode[25]; Bit 5 ← mode[26]; Bits 4:3 ← mode[28:27];
**Bits 2:0 nur lesbar** (0 = 2-Kanal-, ≠ 0 = 8-Kanal-Betrieb, siehe §3.2).

**Stock-Moduswort `0x08910000`** (Bits 16, 20, 23, 27) ⇒ `0xC00&(…>>10)=0x400`, `0x180&(…>>16)=0x080`,
`0x18&(…>>24)=0x08`, Rest 0, dann `|0x8000` ⇒ **`0x0034 = 0x8488`**, alle fünf Byteregister Bit 0 = **0**.

`sound_preset.bin`: 36 Pfade führen `SetDelayLineMode(0x8D01, 0x48910000)` aus — **gleiche** Registerwerte
(Bit 30 wird nicht ausgewertet); drei Pfade `0x48910800` setzen zusätzlich `0x804D` Bit 0 = 1.
Pfad **`0x89` hat keine eigene Delay-Aktion**; es wirkt nur `DelayLineTimeInit` (`libmspsound@0x1212C`,
`sound_path.c:471`) mit `0x8D00 / 0x08910000`.

`tdAudioDSPWriteRegMaskWord@0x1F010`: Bit-15-Adressen mit Maske `0xFF`/`0xFFFF` gehen direkt über
`aud_dsp1_write_reg8`; bei Maske `0x01` wird gelesen–maskiert–geschrieben. `0x8036…0x8039` liegen also im
**Byteraum** und sind **nicht** dieselben Register wie die Verbindungsregister `0x0036…0x0039` (S23 §3).

### 1.3 Was der DSP **nicht** hat

`Init_Module_Delay` schreibt **kein** DSP-Register (reine `.data`-Tabellen). Es gibt im `libmspdriver` weder
Delay-Länge noch Speicherbasis noch Kanal-Enable. `MAPI_AUD_CFG_SurrChannelDelay` →
`func_cfg_surrchanneldelay@0x11E08` ist ein **Stub (`return 0`)**; `MAPI_AUD_Set_ABPDTV_Delay@0x1F220`
schreibt nur `path_delays[]` (keine Hardware) und wird in keinem Preset-Pfad ausgeführt.

---

## 2. Die Hardware-Schleife (`snd_alsa_trid.ko`)

### 2.1 AUDIF-Delayline — `0x06146000`

| Adresse | Bedeutung | Beleg |
|---|---|---|
| `0x06146000` | IRQ-Status, W1C. Statusbit je Linie **`0x400 >> n`** (L0 `0x400` … L3 `0x80`) | `AudIf_dly_GetStatusMask@0xABB0`, `AudIf_dly_Open@0xAF1C` |
| `0x06146004` | IRQ-Maske, `|= Statusbit` | `AudIf_dly_Open` |
| `0x06146008` | Fehlerstatus, W1C, Maske je Linie **`0xF000 << 4n`** | `abpDtv_dly_state@0x11324 +0x10`, `AudIf_dly_Open` |
| **`0x06146054`** | globale Konfiguration, **nur Byte 3**: Linie n → Bit `30−2n` („offen") und Bit `31−2n` („läuft"); geschrieben wird immer das ganze Wort (Bytes 0–2 = 0) | `AudIf_dly_SetConfig@0xAC94` |
| **`0x06146058 + 4n`** | Verzögerung in Ticks, **Bits [16:0]** | `abpDtv_dly_state +0x08`, `AudIf_dly_Run@0xAFDC` (`a1[3]&0xFFFE0000 \| a2&0x1FFFF`) |

Fehlerbits je Linie (Nibble ab Bit `12+4n`, `AudIf_dly_Interrupt@0xB1A4`): +0 „delay counter mismatch",
+1 „expected FrameStart error", +2 „data underflow", +3 „data overflow towards memory".

### 2.2 AUDBRG-Delayline-Kanäle — `0x06148000`

`audbrg_delayline_config@0xA930` rechnet `R6 = (n + 0x185206) << 6` ⇒ **RLB-Basis `0x06148180 + 0x40n`**,
**WLB-Basis = R6 − 0x180 = `0x06148000 + 0x40n`** (Rohdisassembly `audio-f8-05`). Aufruf aus
`…_DelayLine_Open@0x8B50`: `audbrg_delayline_config(h, 2, 4, 0, 0, 0)` — 2 Kanäle, 4 B/Sample, kein IRQ, STEP 0.

| Register | Adresse | Stock-Wert | Beleg |
|---|---|---|---|
| WLB START | `0x06148000 + 0x40n` | `(P_n>>4) & 0xFFFFFF` | `REG_Write(R6−0x180)` |
| WLB END | `+0x04` | `((P_n+0x40000−1)>>4) & 0xFFFFFF` (letztes Byte, inklusiv) | `REG_Write(R6−0x17C)` |
| WLB Schwelle | `+0x08` | `(((P_n+128)>>4) & 0xFFFFFF) \| 0x80000000` | `a1[9]=phys+128`, `a1[10]=1` aus `ConfigMemMap@0xA5F8` |
| WLB STEP | `+0x0C` | **0** | `a6 = 0` |
| WLB CFG | `+0x10` | **`0x2407`** `= (4<<8)\|(0x70>>4)\|(0<<11)\|(2<<12)` | `.data audbrg_delay_wlb_state@0x111A4`: `[5]=0x70`, `[8]=2` |
| WLB FLUSH | `+0x14` | 1, dann 0 | `audbrg_delayline_wlb_flush@0xA874` (`0x06148014`) |
| RLB STEP | `0x0614818C + 0x40n` | **0** | `REG_Write(R6+0x0C)` |
| RLB CFG | `0x06148190 + 0x40n` | **`0xA408`** `= (4<<8)\|(0x80>>4)\|(0<<11)\|(2<<12)\|(2<<14)` | `.data audbrg_delay_rlb_state@0x11284`: `[2]=0x80`, `[5]=2` |
| RLB FLUSH | `0x06148194 + 0x40n` | 1, dann 0 | `audbrg_delayline_rlb_flush@0xA8B4` |
| Hoch-Adresse | **`0x06142044`** | Maske **`0xFF`**, Wert `nib \| (nib<<4)`, `nib = P_n>>28` | `REG_Write_Mask(101982276, …, 255)` |
| IRQ-Maske | `0x06148388` | Bits **n** (WLB) / **n+6** (RLB) — Stock ruft mit `a5 = 0`, also **aus** | `audbrg_delayline_{wlb,rlb}_interrupt_enable@0xA7FC/0xA834` |
| IRQ-Status | `0x0614838C` | W1C Bits n / n+6 | `…_clearstatus@0xA7B8/0xA7D8` |

**Belegt:** RLB **START/END werden nie geschrieben** (nur STEP und CFG, Rohdisassembly `0xA9BC`–`0xA9F8`) — der
Lesekanal folgt dem Ring des Schreibkanals. `audbrg_delayline_start@0xAAD0` setzt **kein** Register (Softwareflag).

### 2.3 DRAM-Puffer

`AudioOutput_ConfigMemMap@0x69E8` (aus `snd_trid_probe`): `ion_alloc(0x160000)`; `istream` `+0x00000`,
`ostream` `+0x40000`, **`delayline` `+0x60000`**. `audbrg_delayline_ConfigMemMap@0xA5F8` verteilt **4 × `0x40000`**
und füllt `delay_phy_addr[0..3] = P, P+0x40000, P+0x80000, P+0xC0000`; Ringgröße `a1[3] = 0x40000` fest.
Bestätigt im Stock-dmesg (`re/captures/HY310-DEV/stock_dmesg.txt` Z. 12–15: `DELAYLINE1 phy_addr=0x60000` …).

Anforderungen: **4 × 256 KiB physisch zusammenhängend**, ≥ 16-Byte-Raster (praktisch ≥ 4 KiB), DMA-kohärent.
**Alle AUDBRG-Puffer müssen im selben 256-MiB-Fenster liegen:** `0x06142044` hat je Richtung nur ein Nibble, und
die Delayline-Konfiguration setzt **beide** Nibbles (Maske `0xFF`) aus *ihrer* Adresse — sie überschreibt damit
OSTREAM (Capture) und ISTREAM. Kleinere Ringe gehen, dann sinkt die Höchstverzögerung proportional.

---

## 3. Verzögerung

**Umrechnung** (`trid_delayline1_put@0x1CD8` / `…_get@0x1E80`): `Ticks = (48768·ms + 500)/1000`
(≈ 48,768 Ticks je ms), `ms = (10000·Ticks/48768 + 5)/10`.

**Grenzen** (`Trid_Audio_Output_DelayLine_GetDelayTimeRange@0x9070`): `min = 100` Ticks (**≈ 2,05 ms**),
`max = 0x40000/(4·K)`; K = 2 Kanäle ⇒ **32768 Ticks ≈ 672 ms**, im 8-Kanal-Betrieb (`0x0034[2:0] ≠ 0`, nur Linie 0)
K = 8 ⇒ 8192 Ticks ≈ 168 ms. Daraus das Rahmenformat: **4 Byte je Sample und Kanal**, 2 Kanäle je Linie
⇒ 8 Byte je Frame, `0x40000/8 = 32768` Frames. ALSA-Regler `trid_delayline_info@0xECC`: **0…500 ms**, Schritt 1.

**Stock-Wert.** `audio.primary.ares.so set_speaker_delay@0x93EC` setzt **alle vier** Regler
`DelayLine1…4 Time Set` auf `spk_delay + spk_delay_offset` (`get_speaker_delay@0x158E8`,
`get_speaker_delay_offset@0x159A8`, `minIni::getl`, Vorgabe 0); gerufen beim HAL-Start direkt nach
„audiobridge Init success" (`audio-a56` Z. 302) und bei `adev_set_parameters("spk_delay=…")` (Grenze ≤ 500).
`re/vendor/HY310/extracted/vendor_a/etc/tvconfig/audio_config.ini`: **`spk_delay = 0`, `spk_delay_offset = 0`
in allen sieben Betriebsarten** (ebenso `owa_delay = 0`). Aber `Trid_Audio_Output_DelayLine_Set@0x90F0` klemmt
einen zu kleinen Wert **auf `min = 100` hoch** und führt trotzdem `Open` + `Run` aus:
**der HY310-Stock lässt alle vier Delaylines mit 100 Ticks ≈ 2,05 ms laufen** — genau der Zustand, gegen den
S16 17:55 mit QPEAK gemessen hat.

**Lippensynchronität (Frage 3).** Ja, dafür ist der Weg da: `spk_delay` (Lautsprecher) und `owa_delay`
(S/PDIF/ARC) je mit Offset, 0…500 ms, je Audio-Betriebsart. **Einen Sollwert ≠ 0 gibt es im HY310-Stock nicht.**
`Trid_Audio_Output_SetAudioDelay@0x75C4` (`AudioSyncDelay`, `270·x/12`) ist etwas anderes — ein reiner
Meldewert für die AV-Synchronisation, ohne Hardwarezugriff.

---

## 4. Reihenfolge im Stock (belegt) und Fehlerbehandlung

1. `Sound_Path_Init` (`libmspsound@0x12198`): … `MAPI_AUD_Initialization` → `BP_AUD_GetGraph` →
   **`DelayLineTimeInit` ⇒ `0x0034 := 0x8488`** → 48 PRST-Connects → Pfadaktionen.
2. HAL-Start: `set_speaker_delay(mixer, 0)` → 4 × `trid_delaylineN_put(0)` → `…_DelayLine_Set(n, 0)` → klemmt
   auf 100 → `…_DelayLine_Open(n)` (**erst AUDBRG, dann AUDIF**) → `…_Run(n, 100)`.
3. `Sound_Path_Connect(0x89)` verdrahtet DELAY1 in den Weg (S23 §4.2).

Im `snd_trid_probe` wird **keine** Delayline geöffnet: `…_DelayLine_Open` hat nur zwei Aufrufer, `…_Set` und
`…_ReSet` (Xref-Liste `audio-f8-04`).

`Trid_Audio_Output_errorFunc_Delayline@0x8A5C`: bei Fehlerklasse 4 und `err & 0x0B3BB000` einmalig
`AudIf_dly_DisableAllStreams()` (`0x06146054 := 0`), IRQ-Bits `0x780` in `0x06146004` löschen,
`queue_work_on(system_wq, delayline_reset_work → trid_delayline_reset@0x95BC)`, `delay_needreset[0] = 1`.
Der Work-Handler ruft `…_DelayLine_ReSet@0x93A8`: alle Linien schließen, `setdelaylinemode` mit gesetztem
Bit 15, `msleep(30)`, Linien 1–3 neu öffnen, dann Linie 0. `setdelaylinemode@0x8CEC` im Kernelmodul benutzt
**das Registerformat direkt**: `0x0034 := mode & 0x9FF8` (Linie 0 Maske `0xFFFF`, sonst `0xFFF8`),
`0x8036…0x8039` aus `mode[19:16]`, `0x804D` aus `mode[20]` — andere Bitanordnung als §1.2.

---

## 5. Fertige Schreibfolge (Frage 4)

`n` = Linie 0…3, `P_n` = physische Pufferadresse, `S = 0x40000`, `T` = Ticks.
`dsp_rmw(0, adr, maske, wert)` wie in `re/captures/weltneuheit/s16-audio-20260908/dsp_load.py`.

**Stufe 0 — messen:** `dsp_read(0, 0x0034)` protokollieren. `0x8488` ⇒ DSP-Seite ist schon richtig, Ursache liegt
allein in der Speicherschleife; `0` ⇒ Diagnose aus §0 bestätigt.

**Stufe 1 — nur DSP** (billiger Test, DELAY1 im Weg lassen):
```
dsp_rmw(0, 0x0034, 0xFFFF, 0x8488)     # rDEL_EN=1 + Stock-Felder
dsp_rmw(0, 0x8036, 0x01, 0x00) ; dsp_rmw(0, 0x8037, 0x01, 0x00)
dsp_rmw(0, 0x8038, 0x01, 0x00) ; dsp_rmw(0, 0x8039, 0x01, 0x00)
dsp_rmw(0, 0x804D, 0x01, 0x00)         # Byteraum (aud_dsp1_*_reg8), RMW
sleep 0.03
```
Dann QPEAK auf `0x2E`/`0x2F` (S25 §8). Pegel da ⇒ es war nur `rDEL_EN`. Weiter 0 oder Fehlerbits in
`0x06146008` ⇒ Stufe 2.

**Stufe 2 — Speicherschleife, je Linie n = 0…3 in dieser Reihenfolge:**
```
# A. Hoch-Adressbits (einmal je Fenster; setzt BEIDE Nibbles)
rmw32(0x06142044, 0xFF, (P_n>>28) | ((P_n>>28)<<4))

# B. AUDBRG-Kanal n        W = 0x06148000 + 0x40*n ;  R = 0x06148180 + 0x40*n
wr32(W+0x14, 1) ; wr32(W+0x14, 0)                       # WLB flush
wr32(R+0x14, 1) ; wr32(R+0x14, 0)                       # RLB flush
wr32(R+0x0C, 0)          ; wr32(R+0x10, 0xA408)         # RLB STEP / CFG
wr32(W+0x00, (P_n>>4) & 0xFFFFFF)                       # WLB START
wr32(W+0x04, ((P_n+S-1)>>4) & 0xFFFFFF)                 # WLB END (inklusiv)
wr32(W+0x08, (((P_n+128)>>4) & 0xFFFFFF) | 0x80000000)
wr32(W+0x0C, 0)          ; wr32(W+0x10, 0x2407)         # WLB STEP / CFG
rmw32(0x06148388, 1<<n,     0) ; rmw32(0x0614838C, 1<<n,     1<<n)      # WLB-IRQ aus + quittieren
rmw32(0x06148388, 1<<(n+6), 0) ; rmw32(0x0614838C, 1<<(n+6), 1<<(n+6)) # RLB-IRQ aus + quittieren

# C. AUDIF-Linie n         M = 0x400>>n ;  E = 0xF000 << (4*n)
wr32(0x06146000, M) ; wr32(0x06146008, E)               # Status/Fehler W1C
# optional, nur mit eigener ISR:  wr32(0x06146004, rd32(0x06146004) | M)
cfg &= ~(3 << (30-2*n)) ; wr32(0x06146054, cfg)         # „geschlossen" (Open)
wr32(0x06146058 + 4*n, T & 0x1FFFF)                     # Verzögerung
cfg |=  (3 << (30-2*n)) ; wr32(0x06146054, cfg)         # „offen + läuft" (Run)
```
Für alle vier Linien endet C bei **`0x06146054 = 0xFF000000`**. Reihenfolge zwingend: erst A/B (AUDBRG), dann C
(AUDIF) — so macht es `…_DelayLine_Open` + `…_Run`. Stufe 1 muss **vor** den Graph-Connects laufen.

**Verzögerung ändern** (Stock-Weg): `T = clamp((48768*ms+500)/1000, 100, 32768)`; Linie schließen
(`cfg &= ~(3<<(30-2n))`), beide FLUSH, dann B + C mit dem neuen `T`; `ms = 0` ⇒ `T = 100` = Stock.
**Abschalten:** `wr32(0x06146054, 0)` (= `AudIf_dly_DisableAllStreams@0xAD40`), danach beide FLUSH je Kanal;
wer DELAY1 gar nicht braucht, verdrahtet wie S16 18:00 (`0x0020 := 0x6263`) daran vorbei.

---

## 6. Korrekturen an vorhandener Doku

| Stelle | bisher | richtig | Beleg |
|---|---|---|---|
| S19 §2.2 | `0xF000` = „alle vier Delaylines" | je Linie ein eigenes Nibble `0xF000 << 4n` | `abpDtv_dly_state@0x11324 +0x10` |
| S19 §3.1 | WLB `+0x08` „Bedeutung vermutet" | `= ((Ringanfang+128)>>4) \| Bit 31` | `ConfigMemMap@0xA5F8` |
| S19 §12 | „Delaylines für Stufe 1 nicht nötig" | richtig für Capture; für den **Ausgabepfad mit DELAY1** nötig | §0 |
| `re/notes/RE_NOTES.md` Z. 105–107 | ostream/istream/WLB/RLB-Basen | istream `0x06148280+0x40n`, Delayline-WLB `0x06148000+0x40n` (`0x…014` ist FLUSH), Delayline-RLB `0x06148180+0x40n` | Rohdisassembly `0xA930` |

---

## 7. Offene Punkte

1. **Nicht gemessen:** ob `rDEL_EN` allein reicht. Stock richtet immer beides ein; §5 trennt das am Board in zwei Schritte.
2. Bedeutung der 2-Bit-Felder in `0x0034` (Bits 4:3, 8:7, 11:10 = je 1) **unbestimmt** — `0x8488` nicht abwandeln.
3. Ob DELAY1-Kanal 0/1 auf **Hardware-Linie 0** liegt, ist nicht belegt; Stock richtet immer alle vier ein — wir auch.
4. Der 8-Kanal-Betrieb (`0x0034[2:0] ≠ 0`) wird vom Stock nie eingeschaltet; die Umschaltlogik ist ungetestet.
5. IOMMU: Stock läuft über `iommus = <&mmu_aw 6 1>`, die dmesg-Adressen (`0x60000` …) sind IOMMU-Adressen. Bei uns
   (IOMMU aus) müssen echte Physadressen hinein — die Register nehmen volle 32 bit (High-Nibble `0x06142044`).
