# S19 - RE: Capture-Rezept des Audio-Bridge (AUDIF/AUDBRG) **ohne DSP**

**08.09.2026, reine statische Analyse.** Board, Zuspieler, `mainline/patches/`, `userspace/` nicht angefasst.
Arbeitskopie `analyse/ida/db-audio-trid/` (neu angelegt, `snd_alsa_trid.ko` als ELF-Relocatable direkt in idalib 9.1
geöffnet, Hex-Rays ARM aktiv). Skripte `analyse/ida/ida_a30.py` … `ida_a3a.py`, Rohausgaben
`re/captures/weltneuheit/audio-trid-a3*-20260908.log`. Auftrag: doku/100 §3 Frage **F3**, Architektur §2 Stufe 1.

Adressen sind ARM-physisch. **belegt** = aus Disassembly/Dekompilat oder Stock-DTB direkt ablesbar;
**vermutet** = aus dem Zusammenhang geschlossen, am Board noch nicht geprüft.

---

## 0. Kurzfassung

| Frage | Antwort | Stand |
|---|---|---|
| **Bypass ohne DSP?** | **Ja.** Im ganzen `snd_alsa_trid.ko` berührt der Capture-Pfad den MSP-DSP **an keiner Stelle**. Die DSP-Mailbox-Helfer (`aud_dsp1_*`, `tdAudioDSP*`, `WaitDSPFree`) haben genau drei Aufrufer, alle in der **Delayline**-Verwaltung. Der Ton läuft HDMI-RX → AUDIF-SPDI1 → AUDBRG-OSTREAM0-DMA → DRAM-Ring; die CPU liest nur einen Zeiger | belegt (Xref-Liste `a32`-Log) |
| Wer füllt den Ring? | Der AUDBRG-**WLB**-Kanal (Write-Line-Buffer) OSTREAM0 schreibt autonom in den Ring. `audbrg_ostream_start` schaltet **kein Enable-Bit** - der Kanal läuft, sobald START/END/STEP/CFG stehen und der AUDIF Daten liefert | belegt |
| Quelle | Fest verdrahtet: **SPDI1 → OSTREAM0**, **SPDI2 → OSTREAM1**. Der Stock-Treiber programmiert **keinen** HDMI→SPDI-Multiplexer. `ARC_SRC 0x06E00020` und `MSP_OWA_OUT 0x02000158` sind **Ausgangs**-Muxe (ARC-TX bzw. S/PDIF-Out: „APB" vs. „MSP"), nicht die Eingangswahl | belegt |
| Bleibt offen | Ob HDMI-RX-Audio **ohne** MIPS-Zutun an SPDI1 anliegt. Das programmiert der Stock-ALSA-Treiber nicht; das macht `display.bin` (`HdmiRx_AEC_Enable`, `TurnOnARCAudioPath`) → Frage **F2** | offen |
| Format im Ring | S16_LE, 2 Kanäle, interleaved, 4 Byte/Frame, feste 48 kHz in der Stock-PCM-Deklaration; Ring **0x10000 = 64 KiB** je OSTREAM (nicht 0x20000 - das ist der ALSA-seitige `buffer_bytes_max`) | belegt (ALSA-hw + CFG-Bits), Sinus-Nachweis fehlt |
| IRQ-Zuordnung | Stock-DTB `audbrg@203042c`: `interrupts = <0 0x73 4>, <0 0x71 4>` → **Index 0 = SPI 115 = AUDBRG**, **Index 1 = SPI 113 = AUDIF/„abp dtv"**. In `mainline/.../sun50i-h713.dtsi` stehen sie **vertauscht** (113 zuerst) | belegt |
| IOMMU | Stock-Node hat `iommus = <&mmu_aw 6 1>`; der Treiber holt die Adresse aus `dma_buf_map_attachment()` auf dem audbrg-`platform_device`, d. h. die DMA geht **durch die IOMMU** (Master 6). Unser Baum hat die IOMMU aus → dann ist es eine echte Physadresse aus CMA, was funktionieren muss (die Register nehmen volle 32 bit) | belegt (Stock), Mainline-Folgerung |
| `high-addr-ctl 0x06142044` | Bits **[3:0] = A[31:28] für alle RLB-Kanäle** (ISTREAM 0-3 + Delayline-Lesen), Bits **[7:4] = A[31:28] für alle WLB-Kanäle** (OSTREAM 0-1 + Delayline-Schreiben). Globale 4-Bit-Adresserweiterung → **alle Puffer einer Richtung müssen im selben 256-MiB-Fenster liegen** | belegt |
| Alternative I2S2/OWA? | **Nein.** OWA0/OWA1 und I2S0-2 sind Standard-Allwinner-Blöcke ohne HDMI-RX-Anbindung; ihre Takte kommen aus `pll_audio`/`pll_periph0_2x`, `hdmi_audio_clk` gehört im Stock-DTB allein dem `tvtop`. Stock nutzt **`owa1` als HDMI-ARC-Sender** (`super.fex`: `sndowa1 → AUDIO_ARC`, `TridentALSA → AUDIO_SPEAKER`), owa0 und i2s2 sind abgeschaltet | belegt (§13) |
| Kürzester Weg | AUDBRG-Capture-Treiber (Stufe 1 aus doku/100) - Registerbild ist vollständig, kein DSP, kein Daemon, ein Ring, ein IRQ. Voraussetzung bleibt das Einschaltrezept aus **F1** (der Block liest aktuell 0) | Empfehlung |

---

## 1. Quellen und Methode

`re/vendor/HY310-DEV/stock_modules/modules_full/snd_alsa_trid.ko` ist ein **nicht gestripptes** ARM32-Relocatable mit
**313 benannten Funktionen** in `.text` (0xb464 Bytes) - die komplette Vendor-Bibliothek ist einkompiliert
(`AudIf_*`, `audbrg_*`, `Trid_Audio_*`, `Thal_Alsa_*`, `REG_*`, `aud_dsp*`). Ein Cross-`objdump` für ARM gibt es auf
dem Rechner nicht; idalib 9.1 öffnet das Relocatable aber problemlos (`idapro.open_database(pfad, True)` +
`ida_auto.auto_wait()`), Hex-Rays ARM läuft.

| Skript | Inhalt | Rohausgabe |
|---|---|---|
| `ida_a30.py` | PCM-Ops, `Thal_Alsa_*`, `ConfigAlsaHandle`/`GetAlsaHandle` | `audio-trid-a30-pcmops-20260908.log` |
| `ida_a31.py` | OSTREAM (Capture), OWA-Input, WLB/RLB-IRQ, `AudBrg_Init` | `audio-trid-a31-ostream-20260908.log` |
| `ida_a32.py` | SPDI-Eingang, AudIf-ISR, `REG_Init`, `snd_trid_probe`, **DSP-Xrefs** | `audio-trid-a32-spdi-20260908.log` |
| `ida_a33.py` | ALSA-Puffer, `internal_snd_card_trid_*`, ISTREAM, Mixer-Kontrollen, Systimer | `audio-trid-a33-alsa-istream-20260908.log` |
| `ida_a34.py` | **Roh-Disassembly** der kritischen Funktionen (Argumentzahl, Bitfelder) | `audio-trid-a34-disasm-20260908.log` |
| `ida_a35.py` | Tabellen: Mixer-Namen, `audIf_owa_dataTypeTable`/`formatTable`, PCM-Ops, `snd_pcm_hardware` | `audio-trid-a35-tabellen-20260908.log` |
| `ida_a36.py` | AUDIF I2SO/SPDO/Delayline, AUDBRG-Delayline | `audio-trid-a36-audif-map-20260908.log` |
| `ida_a37.py` | **automatischer Scan aller MMIO-Konstanten je Funktion** (Basis der Registerkarte) | `audio-trid-a37-regmap-20260908.log` |
| `ida_a38.py` | Initialwerte der Handle-Strukturen, SPDO-Config | `audio-trid-a38-handles-20260908.log` |
| `ida_a39.py`, `ida_a3a.py` | Aufrufgraph, `HISR_AudioGroup_Handler`, Suche nach cpu_comm/MIPS | `audio-trid-a39-callgraph-…`, `audio-trid-a3a-hisr-…` |
| `ida_a43.py` … `ida_a46.py` | Stock-`vmlinux`: `sunxi-owa`/`sunxi-daudio`, CCU `sun50iw12_hw_clks` (Alternativweg, §13) | `audio-vmlinux-a43…a46-*-20260908.log` |

Der Vendor-Kernel ist **Linux 5.4** (Pfad in einem `warn_slowpath_fmt`:
`…/H713_SDK_V1.3_NEW/longan/kernel/linux-5.4/include/linux/thread_info.h`).

---

## 2. Registerkarte AUDIF - `0x06146000`, Fenster **0x88**

`REG_Init@0x7738` mappt: `ioremap(0x06146000, 0x88)`, `ioremap(0x06148000, 0x394)`, `ioremap(0x0614A000, 0x0F)`,
`ioremap(0x06142044, 4)`, `ioremap(0x02031078, 4)`, `ioremap(0x02032078, 4)`. **Alle Zugriffe laufen über
`REG_Read`/`REG_Write`/`REG_Write_Mask`, die die Physadresse auf das passende Fenster abbilden** - deshalb stehen
im Code überall die vollen Physadressen (das war der Schlüssel für den automatischen Scan in `ida_a37.py`).

| Offset | Name | Richtung | Bedeutung | Stand |
|---|---|---|---|---|
| **+0x00** | `IRQ_STATUS` | R / **W1C** | Sammelstatus. Handler: `v = REG_Read(+0x00); REG_Write(+0x00, v);` dann Verteilung | belegt |
| **+0x04** | `IRQ_MASK` | R/W | 1 = Quelle darf IRQ auslösen | belegt |
| **+0x08** | `ERR_STATUS` | R / **W1C** | Fehler-/Overflow-Bits, eigene Bitbelegung (s. u.). **Nicht** „IRQ-Route" - der Legacy-Port schreibt hier Registeradressen hinein, das ist falsch | belegt |
| **+0x0C** | - | | in keiner Funktion benutzt | - |
| **+0x10** | `SPDS_STATUS` | R | S/PDIF-Statuswort. `AudIf_spds_Interrupt` beobachtet die Low-Byte-Felder `0x1F`, `0x60`, `0x80`; `AudIf_spdi_Interrupt` prüft **Bit 25 (0x2000000) = SPDI1 Status-Änderung** und **Bit 9 (0x200) = SPDI2 Status-Änderung** | Offsets/Bits belegt, Feldbedeutung vermutet |
| **+0x14** | - | | nicht benutzt | - |
| **+0x18 / +0x1C** | `ABPO1_CLK` / `ABPO1_DATA` | W | I2S-Ausgang 1. `AudIf_i2so_setFs` schreibt `CLK = DATA-4` | belegt |
| **+0x20 / +0x24** | `ABPO2_CLK` / `ABPO2_DATA` | W | I2S-Ausgang 2 | belegt |
| **+0x28 / +0x2C** | `ABPO3_CLK` / `ABPO3_DATA` | W | I2S-Ausgang 3 | belegt |
| **+0x30** | `SPDO_DATA` | W | S/PDIF-Ausgang Frame-/Datenregister | belegt |
| **+0x34** | **`SPDI1_CTRL_A`** | R/W | **Bit 31 = Enable/Run**, **Bit 28 = zusätzliches Enable (nur SPDI1)**; sonst 0. Aktiv: **`0x90000000`** | belegt |
| **+0x38** | **`SPDI1_CTRL_B`** | R/W | Bits [7:0] = Burstlänge/64 − 1; Bit 9 = Formatflag aus `audIf_owa_formatTable`; **Bit 10 = 1 → Daten gehen an die Bridge (kein SW-Callback)**; Bit 11 = 0; Bits [14:12] = Betriebsart (3 = LPCM, 0 = IEC-61937-Burst); Bit 15 = 1, wenn Datentyp ≠ 2 (komprimiert) | belegt |
| **+0x3C** | **`SPDI1_STATUS`** | R | Bits [1:0]: **0 = Sync verloren, 1 = Sync gefunden, 2 = Daten bereit** | belegt |
| **+0x40** | **`SPDI1_DATA`** | R | **[15:0] = Pc der IEC-61937-Präambel** (Bits [4:0] Datentyp, [6:5] Zusatz), **[31:16] = Burstlänge/Framezahl** | belegt |
| **+0x44 / +0x48 / +0x4C / +0x50** | `SPDI2_CTRL_A/B/STATUS/DATA` | | identisch, 0x10 versetzt. Aktiv: CTRL_A = **`0x80000000`** (kein Bit 28) | belegt |
| **+0x54** | `DLY_CFG` | R/W | Delaylines, **oberstes Byte**: Bit 31/30 = Line 0 run/open, 29/28 = Line 1, 27/26 = Line 2, 25/24 = Line 3 | belegt |
| **+0x58 / +0x5C / +0x60 / +0x64** | `DLY1..4_DELAY` | R/W | Verzögerung in Ticks; `Trid_Audio_Output_DelayLine_Set` rechnet `(48768·ms + 500)/1000` | belegt |
| **+0x68** | `SPDO_DIV` | R/W | MCLK-Teiler; unteres Byte bleibt erhalten (`(alt & 0xFF) | (neu << 8)`) | belegt |
| **+0x6C** | `SPDO_CFG0` | W | Kanal-/Breiten-Konfiguration | belegt (Rolle vermutet) |
| **+0x74** | `SPDO_CFG1` | W | Fs-/Kategoriecode | belegt (Rolle vermutet) |
| **+0x78** | `SPDO_CS` | W | IEC-60958-Channel-Status | belegt |
| **+0x7C** | `SPDO_CFG3` | W | Bit 31 + Bits [27:24] Wortbreite | belegt |

### 2.1 Bitbelegung `IRQ_STATUS/IRQ_MASK` (+0x00 / +0x04)

Aus `AudIf_*_GetW1cMask` / `GetStatusMask` und der Verteilung in `Handle_AudIf_ISR_interrupt@0x62b0`:

| Bit(s) | Maske | Quelle | Beleg |
|---|---|---|---|
| 1, 4, 6, 20, 21 | `0x300052` | **SPDI1** (`AudIf_spdi_GetW1cMask(0)`) | belegt |
| 0, 3, 5, 20, 21 | `0x300029` | **SPDI2** (`AudIf_spdi_GetW1cMask(1)`) | belegt |
| 1 | `0x02` | SPDI1 „Ereignis" (Sync/Daten) | belegt (ISR-Zweig) |
| 0 | `0x01` | SPDI2 „Ereignis" | belegt |
| 6 | `0x40` | SPDI1 **HW-Fehler** | belegt |
| 5 | `0x20` | SPDI2 **HW-Fehler** | belegt |
| 3, 4 | | SPDI2 / SPDI1, Zweitbit - im Handler nicht ausgewertet | vermutet |
| 7, 8, 9, 10 | `0x780` | Delayline 3, 2, 1, 0 (`AudIf_dly_GetStatusMask`: Line0 = 0x400, Line1 = 0x200, Line2 = 0x100, Line3 = 0x80) | belegt |
| 2, 11, 15 | `0x8804` | **SPDO** (`AudIf_spdo_GetStatusMask() = 34820`) | belegt |
| 16, 17, 18 | `0x10000/0x20000/0x40000` | **I2SO2 / I2SO1 / I2SO0** (ABPO3/2/1) | belegt |
| 20, 21 | `0x300000` | **SPDS**; wird nur behandelt, wenn **beide** Maskenbits gesetzt sind | belegt |
| Verteiler | | `0x300000`→SPDS, `0x77000`→I2SO, `0x780`→DLY, `0x8804`→SPDO, `0x10007B`→SPDI | belegt |

### 2.2 Bitbelegung `ERR_STATUS` (+0x08)

Jeder Block schreibt beim `Open` seine eigene Maske hinein (W1C) und liest sie im Fehlerzweig:

| Maske | Quelle | Beleg |
|---|---|---|
| `0x400` | **SPDI1** - gelesen: gesetzt ⇒ „S/PDIF input 1 data overflow", sonst „unspecified HW error" | belegt (`AudIf_GetHandle_spdi1` schreibt 0x400 nach Handle+0x10, `AudIf_spdi_Open` schreibt Handle+0x10 nach +0x08) |
| `0x800` | **SPDI2** - „S/PDIF input 2 data overflow" | belegt |
| `0xF000` | **alle vier Delaylines** (`AudIf_GetHandle_dly1` → Handle+0x10 = `0xF000`) | belegt |
| `abpDtv_i2so_state[+552]` | I2SO je Kanal | belegt (Wert nicht ausgelesen) |

---

## 3. Registerkarte AUDBRG - `0x06148000`, Fenster **0x394**

Der Block besteht aus **14 DMA-Kanälen zu je 0x40 Byte** plus vier globalen Registern. Alle Basen sind aus dem
Disassembly exakt belegt (`ida_a37.py`, Abschnitt „errechnete Basen"):

| Bereich | Kanäle | Basis | Beleg |
|---|---|---|---|
| **Delayline-WLB** (Bridge → Speicher) | 0-3 | `0x06148000 + n·0x40` | `audbrg_delayline_config`: `(n+1593862)<<6 − 384` |
| **OSTREAM-WLB** (Bridge → Speicher) = **Capture** | 0-1 | **`0x06148100 + n·0x40`** | `audbrg_ostream_config`: `(n+1593860)<<6` |
| **Delayline-RLB** (Speicher → Bridge) | 0-3 | `0x06148180 + n·0x40` | `audbrg_delayline_config`: `(n+1593862)<<6` |
| **ISTREAM-RLB** (Speicher → Bridge) = Playback | 0-3 | `0x06148280 + n·0x40` | `audbrg_istream_config`: `(n+1593866)<<6` |
| global | | `0x06148384…0x06148390` | belegt |

### 3.1 Kanalregister

**WLB (Bridge → Speicher, Capture/Delayline-Schreiben)** - Basis `B`:

| Offset | Name | Bedeutung | Stand |
|---|---|---|---|
| `B+0x00` | `START` | `(dma_addr >> 4) & 0xFFFFFF` - Ringanfang in 16-Byte-Einheiten | belegt |
| `B+0x04` | `END` | `((dma_addr + size − 1) >> 4) & 0xFFFFFF` - **letztes Byte**, inklusiv | belegt |
| `B+0x08` | (nur Delayline) | `(x>>4) | (flag<<31)` - Schwelle/zweite Adresse | belegt, Bedeutung vermutet |
| `B+0x0C` | `STEP` | `step_bytes >> 4`. Stock-Capture: 1024 B (OSTREAM0), 384 B (OSTREAM1), Default 3072 B | belegt |
| `B+0x10` | `CFG` | s. u. | belegt |
| `B+0x14` | `FLUSH` | Bit 0: 1 schreiben, dann 0 → Kanal zurücksetzen | belegt |
| `B+0x18` | **`PTR`** | **R:** aktueller HW-Schreibzeiger, `(PTR & 0xFFFFFF) << 4` + High-Nibble = Physadresse | belegt |

> **Korrektur zum Legacy-Port:** `audio_bridge.h` setzt `TRID_AUDBRG_OSTREAM_PTR(n) = +0x108 + n·0x40`.
> Richtig ist **`+0x118 + n·0x40`** (`audbrg_ostream_putdata2SW@0x3f5c` liest `(n<<6) + 102007064 = 0x06148118`).

**RLB (Speicher → Bridge, Playback/Delayline-Lesen)** - Basis `B`: wie oben, zusätzlich

| Offset | Name | Bedeutung | Stand |
|---|---|---|---|
| `B+0x18` | `UMACREQ` | `audbrg_istream_umacreq_trigger`: 1 schreiben, dann 0 → Anforderung an den UMAC | belegt |
| `B+0x1C` | **`PTR`** | R: aktueller HW-Lesezeiger | belegt |

### 3.2 `CFG` (`B+0x10`)

Aus dem Disassembly (`ida_a34`), nicht aus dem Dekompilat:

```
OSTREAM (WLB):  CFG = (mode        << 12) | (width << 11) | (bytes_per_sample << 8) | (thresh >> 4)
ISTREAM (RLB):  CFG = (format_code << 12) | (width << 11) | (bytes_per_sample << 8) | (thresh >> 4)
                    | (channels << 14)
```

* Bits **[7:0]** = `handle[0x14] >> 4`. Statisch vorbelegt: **`0x70` bei OSTREAM (⇒ 0x07)**, **`0x80` bei ISTREAM
  (⇒ 0x08)**. Nirgends im Modul überschrieben. *(Wert belegt, Bedeutung vermutet: FIFO-/Burst-Schwelle.)*
* Bits **[10:8]** = 1…4 (Prüfung `(a2−1) > 3 → Fehler` - dieselbe Prüfung, die beim ISTREAM auf
  *Bytes je Sample* liegt; beim OSTREAM gibt es **keinen** Kanalparameter). **Im Capture-Fall ist die
  Unterscheidung „Bytes je Sample" gegen „Kanalzahl" nicht auflösbar, weil beides 2 ist** - der zu
  schreibende Wert ist so oder so 2. *(Prüfung und Wert belegt, Bedeutung vermutet.)*
* Bit **11** = Breiten-/Vorzeichenflag, im Capture-Pfad **0**.
* Bits **[13:12]** = Betriebsart. Capture setzt **2**.
* Bits **[16:14]** = Kanalzahl - **nur ISTREAM**; der OSTREAM hat gar keinen Kanalparameter (die Framestruktur
  kommt vom AUDIF).

**Stock-Capture-Werte:** OSTREAM0 → `CFG = (2<<12) | (2<<8) | 0x07 = **0x2207**`;
OSTREAM1 → `CFG = (2<<12) | (4<<8) | 0x07 = **0x2407**`.

### 3.3 Globale Register

| Adresse | Name | Bedeutung | Stand |
|---|---|---|---|
| **`0x06148384`** | `GLOBAL_IRQ_EN` | Bit 0 = Gesamtfreigabe (`audbrg_interrupt_enable`) | belegt |
| **`0x06148388`** | `IRQ_MASK` | 14 Bits, s. u. | belegt |
| **`0x0614838C`** | `IRQ_STATUS` | 14 Bits, **W1C über Read-Modify-Write mit Maske 0x3FFF** | belegt |
| **`0x06148390`** | `STREAM_SYNC` | wird von `*_config` immer auf **0** gesetzt (keine Sync-Gruppe) | belegt, Bedeutung vermutet |

**IRQ-Bitkarte (Maske und Status identisch, `0x3FFF`):**

| Bit | Kanal | Beleg |
|---|---|---|
| 0-3 | Delayline-WLB 0-3 | `audbrg_delayline_wlb_interrupt_enable`: `1 << n` |
| **4-5** | **OSTREAM 0-1 (Capture)** | `audbrg_ostream_interrupt_enable`: `1 << (n+4)` |
| 6-9 | Delayline-RLB 0-3 | `1 << (n+6)` |
| 10-13 | ISTREAM 0-3 (Playback) | `1 << (n+10)` |

Der Handler `Handle_audbrg_ISR_interrupt@0x2e2c`:
```c
v = REG_Read(0x0614838C);  v &= 0x3FFF;
REG_Write_Mask(0x0614838C, v, 0x3FFF);      /* W1C */
if (v & 0x0030) Handle_WLB_Interrupt(v);    /* OSTREAM 0/1 */
if (v & 0x3C00) Handle_RLB_Interrupt(v);    /* ISTREAM 0..3 */
```
`Handle_WLB_Interrupt` ruft für Bit 4 bzw. 5 nur `audbrg_ostream_putdata2SW(n)` - **das ist der ganze
Capture-IRQ**: Zeiger lesen, umrechnen, in den SW-Deskriptor schreiben. Kein DSP, kein Datenkopieren.
(Die Delayline-Bits 0-3 und 6-9 werden im Handler gar nicht ausgewertet.)

---

## 4. Nebenregister

| Adresse | Name | Bedeutung | Stand |
|---|---|---|---|
| **`0x06142044`** | `HIGH_ADDR_CTL` | **[3:0] = A[31:28] aller RLB-Kanäle**, **[7:4] = A[31:28] aller WLB-Kanäle**. `audbrg_ostream_config`: `REG_Write_Mask(0x06142044, (phys>>28)<<4, 0xF0)`; `audbrg_istream_config`: Maske `0x0F`; `audbrg_delayline_config` setzt **beide** Nibbles (Maske `0xFF`) | belegt |
| `0x0614A000` | `AUDIO_TOP_CLK_CTL` | `audio_top_clk_init`: `|= 0x700` | belegt |
| `0x0614A00C` | `AUDIO_TOP_CLK_CFG` | `(alt & 0xFF000000) | 0x1A5E00`, danach `|= 0x01000000` | belegt |
| `0x06E00020` | `ARC_SRC` | Bit 0: **0 = APB, 1 = MSP** (Mixer „ARC source selector"). `snd_trid_probe` setzt Bit 0 = **0** | belegt |
| `0x02000158` | `MSP_OWA_OUT` | Bits [15:12]: `0x2000` = APB, `0x6000` = MSP, sonst NULL (Mixer „MSP OWA OUT selector"). Wird nur auf Anforderung gesetzt | belegt |
| `0x06144000/0C/10/14/18` | DSP-Mailbox (DSP1 Write/Read, DSP2 Write/Read) | **nur Delayline** | belegt |
| `0x02031078` / `0x02032078` | ARM-/MIPS-Mutex (`WaitDSPFree`/`ReleaseDSP`) | **nur Delayline** | belegt |

> **`audio_top_clk_init@0x2d0c` wird im ausgelieferten Modul nirgends aufgerufen** (nur `__mcount_loc`/`.ARM.exidx`
> referenzieren es). Die Takte müssen also von außen kommen - beim Stock von `sunxi-tvtop`. Für uns: Die beiden
> Schreibvorgänge sind trotzdem verwertbar, siehe Handtest Schritt 0 und Frage **F1** (S17).

---

## 5. Speicherlayout

`AudioOutput_ConfigMemMap@0x69e8` (aufgerufen aus `snd_trid_probe`):

```c
ion_alloc(0x160000, 1, 0);                       /* 1 441 792 Byte */
vir = ion_heap_map_kernel(...);
att = dma_buf_attach(dmabuf, &pdev->dev);        /* audbrg-Gerät → IOMMU-Master 6 */
sgt = dma_buf_map_attachment(att);
phy = sg_dma_address(sgt->sgl);                  /* *(sgt->sgl + 12) */
audbrg_istream_ConfigMemMap  (phy + 0x00000, vir + 0x00000);   /* 4 × 0x10000 */
audbrg_ostream_ConfigMemMap  (phy + 0x40000, vir + 0x40000);   /* 2 × 0x10000 */
audbrg_delayline_ConfigMemMap(phy + 0x60000, vir + 0x60000);   /* 4 × 0x40000 */
```

| Bereich | Offset | Größe je Kanal | Anzahl | Beleg |
|---|---|---|---|---|
| ISTREAM (Playback) | `+0x00000` | `0x10000` | 4 | belegt |
| **OSTREAM (Capture)** | `+0x40000` | **`0x10000` = 64 KiB** | 2 | belegt |
| Delayline | `+0x60000` | `0x40000` | 4 | belegt |

Die **`0x20000`** aus dem Auftragstext ist **nicht** die Ringgröße, sondern
(a) `buffer_bytes_max` in `trid_pcm_capture_hardware` und
(b) die Größe der vier reinen **Software**-Ringe für Playback (`Alsa_AudioBuffer_Config` → `kmalloc_order_trace(0x20000)`).

**ES-Deskriptor** (was der PCM-Layer sieht, 5 × u32, `audbrg_ostream_get_esbuf@0x3d90`):
`{ [0] virt_start, [1] virt_end (inklusiv), [2] Schreibzeiger, [3] Lesezeiger, [4] Slot }`.
Der WLB-IRQ aktualisiert `[2]` in **allen** angehängten Deskriptoren (bis zu 4 pro Ring).

`trid_pcm_capture_hardware` (`.rodata @0xb638`, roh nachgeprüft):

```
info               0x00040103   = MMAP | MMAP_VALID | INTERLEAVED | RESUME
formats            0x0000000000000004 = SNDRV_PCM_FMTBIT_S16_LE
rates              0x00000080   = SNDRV_PCM_RATE_48000
rate_min/max       48000 / 48000
channels_min/max   2 / 2
buffer_bytes_max   0x20000
period_bytes_min   0x100        period_bytes_max 0x4000
periods_min/max    1 / 8        fifo_size 128
```
> Die Märznotiz `AGENT_TASK_AUDIO_BRIDGE_FIXES.md` H1 nennt `0x40203` und leitet daraus `SYNC_APPLPTR` ab -
> das ist ein Lesefehler; `262403 = 0x40103`.

Für Playback (Kartenvorgabe in `snd_trid_probe`): `rates = 0x14FE` (8 k…192 k), `rate_min 8000`, `rate_max 192000`,
`channels 1…2`, sonst identisch.

---

## 6. Stock-Sequenz Capture, Register für Register

Aufrufkette (alles belegt, `ida_a39`-Aufrufgraph):

```
trid_pcm_capture_open      → internal_snd_card_trid_init/_open → Alsa_Audio_Open → Thal_Alsa_Audio_Open(dir=1)
                               → Trid_Audio_Output_Ostream_Open(idx) → AudIf_GetHandle_ostream + AudIf_GetHandle_spdiN
                                                                     → AudIf_spdi_Open
                               → ConfigAlsaHandle → audbrg_interrupt_enable(1)
                               → Trid_Audio_Output_Set_ESBuf → audbrg_ostream_set_esbuf
trid_pcm_hw_params         → nur printk (return 0)
trid_pcm_capture_prepare   → internal_snd_card_trid_prepare → convertType → Alsa_Audio_Config → Thal_Alsa_Audio_Config
trid_pcm_capture_trigger   → internal_snd_card_trid_start → Alsa_Audio_Start → Thal_Alsa_Audio_Start(dir=1)
                               → Thal_Alsa_Audio_Capture_Start → Trid_Audio_Output_OWA_Input
                                   → audbrg_ostream_config → audbrg_ostream_start
                                   → DeclareNewFrameAvail(spdi, NULL) → AudIf_spdi_Run → AudIf_spdi_activate
IRQ 115 (AUDBRG)           → Handle_audbrg_ISR_interrupt → Handle_WLB_Interrupt → audbrg_ostream_putdata2SW
IRQ 113 (AUDIF)            → Handle_AudIf_ISR_interrupt  → AudIf_spdi_Interrupt (Sync-Automat)
trid_pcm_pointer           → trid_systimer_pointer  (rein jiffies-basiert!)
trid_pcm_capture_copy      → ReadIntoBufferOnceAvailable (copy_to_user aus dem Ring)
```

### 6.1 `open` - SPDI-Kanal freischalten

`Trid_Audio_Output_Ostream_Open(idx)`: `idx 0 → SPDI1`, `idx 1 → SPDI2` (**fest**, kein Register).
`AudIf_GetHandle_spdi1@0x4c24` setzt statisch `Handle+0x08 = 0x06146034` und `Handle+0x10 = 0x400`
(spdi2: `0x06146044` / `0x800`). `AudIf_spdi_Open@0x4d6c`:

| # | Schreiben | Wert (SPDI1) | Wert (SPDI2) |
|---|---|---|---|
| 1 | `0x06146000` (IRQ_STATUS, W1C) | `0x00300052` | `0x00300029` |
| 2 | `0x06146008` (ERR_STATUS, W1C) | `0x00000400` | `0x00000800` |
| 3 | `0x06146004` (IRQ_MASK) `|=` | `0x00300052` | `0x00300029` |

Vorher hat `AudIf_spdi_ClearState` bereits `REG_Write(CTRL_A, 0)` und `REG_Write(CTRL_B, 0)` ausgeführt.
`ConfigAlsaHandle@0x7c84` setzt danach `0x06148384` Bit 0 = 1 (AUDBRG-Gesamt-IRQ).

### 6.2 `hw_params`

Macht **nichts** außer einem `printk`. Die Parameter kommen erst in `prepare` an.

### 6.3 `prepare` - Formatumrechnung, nur Software

`internal_snd_card_trid_convertType@0x100` bildet `runtime->format` ab:
`S16_LE/U16_LE → (16 bit, endian 0)`, `S16_BE/U16_BE → (16, 1)`, `S32_LE/U32_LE → (32, 0)`, `S32_BE/U32_BE → (32, 1)`;
Rate muss aus {8000, 11025, 16000, 22050, 24000, 32000, 44056, 44100, 47250, 48000, 50000, 50400, 88200, 96000,
176400, 192000, 2822400} sein, Kanäle 1 oder 2. Ergebnis-Array
`{bits, channels, rate, 512, endian}` → `Thal_Alsa_Audio_Config@0x8210` legt es im Handle ab und rechnet
`bytes = bits · 2 · channels · 512 / 8`. **Kein Registerzugriff.**

### 6.4 `trigger(START)` - die eigentliche Scharfschaltung

`Thal_Alsa_Audio_Capture_Start@0x84c0` ruft `Trid_Audio_Output_OWA_Input(idx, 0, mode, 2)` mit
**`mode = 2` für idx 0** und **`mode = 3` für idx 1** (aus dem Disassembly: `MOV R3,#2; CMP R4,#1; MOVNE R2,R3;
MOVEQ R2,#3`). Bestätigt durch `HISR_AudioGroup_Handler`, der dieselben Argumente explizit setzt.

`Trid_Audio_Output_OWA_Input@0x736c` → `audbrg_ostream_config(handle, bps, width, irq_en, step, mode)`:

| idx | `bps` | `width` | `irq_en` | `step` | `mode` |
|---|---|---|---|---|---|
| 0 (SPDI1) | 2 | 0 | 1 | 1024 | 2 |
| 1 (SPDI2) | 4 | 0 | 1 | 384 | 2 |

**Registerschreibungen für OSTREAM0** (`audbrg_ostream_config@0x3be0`, `B = 0x06148100`):

| # | Register | Wert |
|---|---|---|
| 1 | `0x06142044` RMW Maske `0xF0` | `(dma >> 28) << 4` |
| 2 | `B+0x00` START | `(dma >> 4) & 0xFFFFFF` |
| 3 | `B+0x04` END | `((dma + 0x10000 − 1) >> 4) & 0xFFFFFF` |
| 4 | `B+0x0C` STEP | `1024 >> 4 = 0x40` |
| 5 | `B+0x10` CFG | **`0x2207`** |
| 6 | `0x06148390` STREAM_SYNC | `0` |
| 7 | `0x06148388` IRQ_MASK RMW | Bit 4 setzen |
| 8 | `0x0614838C` IRQ_STATUS | Bit 4 W1C |

Danach `audbrg_ostream_start@0x3cf8`:

| # | Aktion |
|---|---|
| 9 | `B+0x14` FLUSH = 1, dann 0 |
| 10 | SW-Zeiger auf Ringanfang, **`memset(ring, 0, 0x10000)`** |
| 11 | Zustand „gestartet" (nur Software) |

**Es gibt kein Enable-Bit für den WLB-Kanal.** Er läuft, sobald der AUDIF liefert.

Dann `DeclareNewFrameAvail(spdi_handle, NULL)` - **Callback bewusst 0**, damit der SPDI die Daten an die Bridge
gibt statt an die Software - und `AudIf_spdi_Run` → `AudIf_spdi_activate@0x4cc0`:

| # | Register | Wert SPDI1 (LPCM) | Wert SPDI2 (Burst) |
|---|---|---|---|
| 12 | `0x06146038` / `0x06146048` CTRL_B | **`0x00003000`** (Bits 12,13 = Modus 3 = LPCM; Bit 15 = 0) | **`0x00008017`** (Modus 0, Bit 15 = 1, Burst = 23) |
| 13 | `0x06146034` / `0x06146044` CTRL_A | **`0x90000000`** (Bit 31 Enable + Bit 28) | **`0x80000000`** |

Reihenfolge ist **CTRL_B zuerst, dann CTRL_A** (`REG_Write(base+4, …); REG_Write(base, …)`).

### 6.5 AUDIF-IRQ (SPI 113) - der Sync-Automat

`AudIf_spdi_Interrupt@0x4ff8`, Zustand in `Handle+0x04` (`2` = wartet auf Sync, `3` = läuft):

```
if (status & 0x40)                       /* SPDI1 HW-Fehler */
    e = REG_Read(0x06146008); REG_Write(0x06146008, 0x400);
    err(e & 0x400 ? "data overflow" : "unspecified HW error");
else if (status & 0x02) {
    s = REG_Read(0x0614603C) & 3;
    if (state == 2 && s == 1) {                     /* Sync gefunden  */
        d = REG_Read(0x06146040);                   /* Pc + Burstlänge */
        AudIf_spdi_ExtractFormatFromPc(handle);     /* → CTRL_B[7:0], Bit 9 */
        Handle[0x19] |= 0x04;                       /* CTRL_B Bit 10 = an die Bridge */
        REG_Write(0x06146038, CTRL_B);
        state = 3;
    } else if (state == 3 && s == 2) {              /* Daten bereit    */
        /* Callback ist NULL → nichts; nur d neu einlesen */
    } else if (state == 3 && s == 1) {              /* Neusynchronisation */
        ExtractFormatFromPc(); REG_Write(0x06146038, CTRL_B);
    } else if (state == 3 && s == 0) {              /* Sync verloren   */
        err("S/PDIF input 1 sync lost!");
        AudIf_spdi_activate(handle, 0, 0);          /* zurück auf state 2 */
    }
}
if (status & 0x100000) {                            /* SPDS            */
    v = REG_Read(0x06146010);
    if (v & 0x2000000) StatusChangeCb_SPDI1(v);
    if (v & 0x200)     StatusChangeCb_SPDI2(v);
}
```

`AudIf_spdi_ExtractFormatFromPc@0x4ed8`: `Pc = REG_Read(SPDI_DATA) & 0xFFFF`;
`typ = audIf_owa_dataTypeTable[4·(Pc & 0x1F) + ((Pc >> 5) & 3)]` (128-Byte-Tabelle @`0xbb00`, 0 = LPCM, 3 = AC-3,
0x0D…0x0F = DTS I/II/III …); daraus 16 Byte aus `audIf_owa_formatTable` (@`0xbb80`, 26 Einträge; Eintrag 3 enthält
das AC-3-Syncwort `0x0B77`), Burstlänge → `CTRL_B[7:0] = (Samples/64) − 1` (LPCM ⇒ `0xFF`, AC-3 1536 ⇒ 23).

### 6.6 AUDBRG-IRQ (SPI 115) - Zeigerfortschritt

`audbrg_ostream_putdata2SW@0x3f5c` - das ist die **gesamte** Datenlogik:

```c
hi  = REG_Read(0x06142044) & 0xF0;
p   = REG_Read(0x06148118 + n*0x40) & 0xFFFFFF;
phys = (hi << 24) | (p << 4);
handle[10] = phys + handle[1] /*virt_start*/ - ostream_phy_addr[n];   /* virtuelle Adresse */
for (jeder angehängte ES-Deskriptor) desc[2] = handle[10];
```

### 6.7 `pointer` und Datenübergabe

`trid_pcm_pointer` → `trid_systimer_pointer@0xe54`: **rein jiffies-basiert** (Kopie aus `snd-dummy`), liest
**kein** Hardware-Register. Der Hardwarezeiger geht ausschließlich in den ES-Deskriptor.
Die Daten holt `trid_pcm_capture_copy@0x10d4` → `ReadIntoBufferOnceAvailable@0x7c4`: wartet in
3-Jiffy-Schritten, bis `desc[2] − desc[3] ≥ Bytes`, und macht dann `copy_to_user` direkt aus dem Ring
(mit Umbruch am Ringende). `Thal_Alsa_Audio_Read_Avaliable` / `UpdateReadRp` bilden dieselbe Rechnung ab.

**Für unseren Treiber ist das der Punkt, an dem wir es besser machen:** wir geben den DMA-Ring direkt als
ALSA-Puffer heraus, lesen `PTR` im `pointer()`-Callback und rufen `snd_pcm_period_elapsed()` aus dem WLB-IRQ.

---

## 7. Quellwahl - woher weiß der AUDIF, dass HDMI-RX die Quelle ist?

**Antwort: aus diesem Treiber gar nicht.** Belegt:

* `SPDI1 → OSTREAM0` und `SPDI2 → OSTREAM1` sind im Code **fest verdrahtet**
  (`Trid_Audio_Output_Ostream_Open`: `idx==0 → AudIf_GetHandle_spdi1`, `idx==1 → AudIf_GetHandle_spdi2`).
  Es gibt **kein** Routing-Register zwischen AUDIF und AUDBRG.
* `ARC_SRC 0x06E00020` Bit 0 ist der Mixer **„ARC source selector"** mit den Werten **APB / MSP**
  (`trid_apb_or_msp_select`). `snd_trid_probe` setzt ihn beim Laden auf **APB (0)**. Das ist der
  **Audio-Return-Channel-Sender**, nicht der HDMI-Eingang.
* `MSP_OWA_OUT 0x02000158` Bits [15:12] ist der Mixer **„MSP OWA OUT selector"** mit **NULL / APB / MSP**
  (`trid_apb_or_msp_select_null`; `0x2000` = APB, `0x6000` = MSP). Das ist die Quelle des
  **S/PDIF-Ausgangs** der MSP-Insel.
* Der einzige Rest, der eine Betriebsart wählt, sind die drei Bits `CTRL_B[14:12]` (3 = LPCM, 0 = IEC-61937-Burst)
  und `CTRL_B[15]`.

**Folgerung (vermutet, für F2 zu bestätigen):** Der Weg HDMI-RX → AUDIF-SPDI1 wird von der MIPS-Firmware
geschaltet (`display.bin`: `THDMIRx_TV303_Audio_Driver.cpp`, `HdmiRx_AEC_Enable`, APLL aus N/CTS,
`SetHandlerOnNewAudioInfoPacket`). Für Stufe 1 heißt das: **unsere MIPS-App muss laufen** (tut sie, doku/97),
und ggf. muss ein RPC/Callback den HDMI-Audioausgang scharfschalten. Der Bridge-Teil selbst braucht dafür nichts.

---

## 8. Fs-Erkennung

| Weg | Was es liefert | Stand |
|---|---|---|
| `SPDI_DATA +0x40` `[15:0]` | IEC-61937-**Pc**, daraus Datentyp (LPCM/AC-3/DTS/…) und Burstlänge - **nicht** die Abtastrate | belegt |
| `SPDS_STATUS +0x10` Low-Byte | Felder `0x1F` (5 bit), `0x60` (2 bit), `0x80` (1 bit); `AudIf_spds_Interrupt@0x4fa4` merkt sich nur Änderungen in `last_status`. **Sehr wahrscheinlich Fs-Code + Kanalstatus + Lock** - der Stock-Treiber wertet es nicht aus | Register/Bits belegt, Bedeutung **vermutet** |
| `SPDS_STATUS` Bit 25 / Bit 9 | „Status geändert" für SPDI1 / SPDI2 → Callback (`DeclareStatusChange`) | belegt |
| Stock-ALSA | deklariert Capture **hart auf 48 000 Hz** und liest keine Rate aus | belegt |

Es gibt im ganzen Modul **keine** Funktion, die eine Abtastrate aus dem SPDI liest. Rate-Erkennung muss also
entweder über `SPDS_STATUS` (am Board zu verifizieren, siehe Handtest Schritt 7) oder über die MIPS-Seite
(HDMI-RX-N/CTS, F2) laufen. Für Stufe 1 reicht 48 kHz - der Zuspieler liefert laut doku/100 §1 genau das.

---

## 9. IOMMU und DMA-Randbedingungen

* Stock-DTB: `audbrg@203042c { compatible = "vs,trid-audio-bridge"; interrupts = <0 0x73 4>, <0 0x71 4>;
  iommus = <0x11 0x06 0x01>; status = "okay"; }` - **kein `reg`, keine `clocks`, keine `resets`**.
  Phandle `0x11` = `iommu@2010000` (`allwinner,sunxi-iommu`, `#iommu-cells = <2>`, SPI 0x47 = 71,
  Takt `<&ccu 0x30>`). Also **Master 6, TLB-ID 1**.
* Der Treiber nimmt `sg_dma_address(sgt->sgl)` aus `dma_buf_map_attachment()` **auf dem audbrg-Gerät** - das ist
  bei aktivem IOMMU eine IOVA. **Die AUDBRG-DMA geht durch die IOMMU** (belegt).
* Unser Mainline-Baum hat die IOMMU bewusst aus (Kommentarblock in `sun50i-h713.dtsi`). Dann muss der Puffer
  **physisch zusammenhängend** sein → `dma_alloc_coherent` / CMA. Die Register können das:
  `START/END/PTR` sind 24 bit in 16-Byte-Einheiten (28 bit) + 4 bit aus `0x06142044` = volle 32 bit.
* **Ausrichtung:** 16 Byte (Registergranularität). **Größe:** Vielfaches von 16.
* **256-MiB-Falle:** `0x06142044` hat nur **ein** Nibble je Richtung. Alle WLB-Puffer (beide OSTREAMs +
  Delayline-Schreiben) müssen im selben 256-MiB-Fenster liegen, ebenso alle RLB-Puffer. Für einen reinen
  Capture-Treiber mit einem Ring ist das unkritisch, muss aber als Konstante im Kopf bleiben.
* Der Ring wird von der DMA beschrieben → **kohärent allozieren** (`SNDRV_DMA_TYPE_DEV`), nicht cachbar
  mit manueller Invalidierung.

---

## 10. Handtest am Board (`rd.py`), Schritt für Schritt

Werkzeuge auf dem Board (doku/50, doku/97): `python3 /root/rd.py ADDR…` liest, `python3 /root/rd.py -w ADDR WERT`
schreibt **und gibt alt → neu → Rückleseprobe aus** - damit ist jeder Schreibvorgang gleichzeitig eine
Positivkontrolle. Für den Ringinhalt `python3 /root/pm_read.py dump PHYS LEN DATEI`
(`analyse/hdmi-seq/pm_read.py`, liest wortweise aus `/dev/mem`).

Ablauf für **HDMI-2, 1-kHz-Sinus, 48 kHz Stereo LPCM** am Zuspieler (vorher `xrandr --output HDMI-2 --set audio on`
**plus Modeset**, doku/100 F5). Alle Adressen hex ohne Präfix, wie `rd.py` sie erwartet.

> **Voraussetzung / Abbruchkriterium:** Ohne das Einschaltrezept aus **F1/S17** liest der ganze Audio-Top 0
> (doku/100 §1). **Schritt 0 muss grün sein, sonst misst der Rest nichts.**
>
> **Puffer:** `P` ist die Physadresse eines 64-KiB-Blocks, den der Kernel nicht benutzt und `/dev/mem` lesen darf -
> eine `reserved-memory`-Region mit `no-map` (wie in doku/73 §10) oder ein bekannter CMA-Block. `P` muss
> 16-Byte-ausgerichtet sein und mit `P + 0xFFFF` im selben 256-MiB-Fenster liegen. Im Folgenden als Beispiel
> `P = 0x4A000000` (⇒ `P_hi = 4`, `P_lo = 0x4A00000`, `E_lo = 0x4A00FFF`).

### Schritt 0 - lebt der Block? (zwei unabhängige Positivkontrollen)

```sh
python3 /root/rd.py 0614A000 0614A00C 06146000 06146004 06148384 06148388
# Audio-Top-Takt anwerfen (aus audio_top_clk_init, im Stock-Modul toter Code):
python3 /root/rd.py -w 0614A000 <alt|0x700>
python3 /root/rd.py -w 0614A00C <(alt & 0xFF000000)|0x001A5E00>
python3 /root/rd.py -w 0614A00C <derselbe Wert | 0x01000000>
# Positivkontrolle 1: START-Register von OSTREAM0 ist ein einfaches 24-bit-R/W-Register
python3 /root/rd.py -w 06148100 00ABCDEF     # erwartet: "-> 0x00abcdef (gelesen 0x00abcdef)"
# Positivkontrolle 2: anderes Register, andere Breite
python3 /root/rd.py -w 06148388 00003FFF     # erwartet: gelesen 0x00003fff
python3 /root/rd.py -w 06148388 0
python3 /root/rd.py -w 06148100 0
```

**Liest eine der beiden Kontrollen `0` zurück, ist der Block noch abgeschaltet → F1-Rezept fehlt, abbrechen.**
Ein Test, der auch bei totem Block „unauffällig" aussieht, prüft nichts.

### Schritt 1 - Ring vorbereiten

```sh
# 64 KiB mit einem Muster füllen, das kein Audiosignal sein kann
python3 - <<'EOF'
import mmap, os, ctypes
P, N = 0x4A000000, 0x10000
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, N, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=P)
v = (ctypes.c_uint32 * (N // 4)).from_buffer(m)
for i in range(N // 4): v[i] = 0xA5A5A5A5
print("Ring gefuellt")
EOF
```

### Schritt 2 - OSTREAM0 konfigurieren

```sh
python3 /root/rd.py 06142044                       # alten Wert merken
python3 /root/rd.py -w 06142044 <(alt & ~0xF0)|0x40>   # Bits[7:4] = P_hi = 4
python3 /root/rd.py -w 06148100 04A00000           # START = (P>>4) & 0xFFFFFF
python3 /root/rd.py -w 06148104 04A00FFF           # END   = ((P+0xFFFF)>>4) & 0xFFFFFF
python3 /root/rd.py -w 0614810C 00000040           # STEP  = 1024 >> 4
python3 /root/rd.py -w 06148110 00002207           # CFG   = mode2 | bps2 | thresh
python3 /root/rd.py -w 06148390 0                  # STREAM_SYNC
python3 /root/rd.py -w 06148114 1                  # FLUSH an
python3 /root/rd.py -w 06148114 0                  # FLUSH aus
python3 /root/rd.py -w 06148384 1                  # AUDBRG-Gesamt-IRQ
python3 /root/rd.py 06148100 06148104 0614810C 06148110 06142044
```
Alle fünf Rücklesewerte müssen exakt dem Geschriebenen entsprechen.

### Schritt 3 - SPDI1 freischalten

```sh
python3 /root/rd.py -w 06146000 00300052           # IRQ_STATUS W1C
python3 /root/rd.py -w 06146008 00000400           # ERR_STATUS W1C
python3 /root/rd.py 06146004                       # alten Maskenwert merken
python3 /root/rd.py -w 06146004 <alt|0x00300052>
python3 /root/rd.py -w 06146038 00003000           # CTRL_B: LPCM-Modus
python3 /root/rd.py -w 06146034 90000000           # CTRL_A: Enable (Bit31) + Bit28
```

### Schritt 4 - Sync und Format (was sonst der AUDIF-IRQ macht)

```sh
for i in $(seq 20); do python3 /root/rd.py 06146000 0614603C 06146040; sleep 0.2; done
```

| Beobachtung | Bedeutung |
|---|---|
| `06146000` bekommt **Bit 1 (`0x02`)** | SPDI1 meldet ein Ereignis - der HDMI-Ton erreicht den AUDIF |
| `06146000` bleibt ohne Bit 1 **und** `0614603C & 3 == 0` | **Am AUDIF kommt nichts an.** Der Bridge ist unschuldig → Frage **F2**: die MIPS-Firmware muss den HDMI-RX-Audioausgang scharfschalten |
| `0614603C & 3` == 1 | Sync gefunden |
| `0614603C & 3` == 2 | Daten bereit (Dauerzustand im Betrieb) |
| `06146040 & 0xFFFF` | Pc der IEC-61937-Präambel. **LPCM ⇒ 0.** ≠ 0 ⇒ komprimierter Strom, dann Zuspieler auf PCM stellen |

Danach den Formatschritt des ISR von Hand nachziehen:

```sh
python3 /root/rd.py -w 06146038 000034FF   # Bit10 = an die Bridge, [7:0]=0xFF (LPCM)
python3 /root/rd.py -w 06146000 00300052   # Status quittieren
```

### Schritt 5 - wandert der Zeiger?

```sh
python3 /root/rd.py 06148118; sleep 1; python3 /root/rd.py 06148118
python3 /root/rd.py 0614838C
```

| Prüfung | Erwartung |
|---|---|
| `06148118` ändert sich | ja. `phys = ((0x06142044 & 0xF0) << 24) | ((PTR & 0xFFFFFF) << 4)` liegt in `[P, P+0x10000)` |
| Differenz über 1 s (mit Ringumbruch gerechnet) | ≈ **192 000 Byte** = 48 000 × 2 ch × 2 Byte ⇒ etwa 3 Ringumläufe |
| `0614838C` | **Bit 4 (`0x10`) gesetzt**. Quittieren: `rd.py -w 0614838C 10` |
| **Negativkontrolle** | Ton am Zuspieler stumm → Zeiger bleibt stehen **oder** der Ring füllt sich mit Nullen. Bleibt der Zeiger auch **mit** Ton stehen, ist die DMA nicht scharf |

### Schritt 6 - steht ein Sinus im Ring?

```sh
python3 /root/pm_read.py dump 0x4A000000 0x4000 /tmp/ring.bin
```
Auf dem Arbeitsrechner:
```python
import numpy as np
d = np.fromfile("/tmp/ring.bin", dtype="<i2")
assert (d != np.int16(0xA5A5)).any(), "Ring unveraendert -> keine DMA"
l, r = d[0::2].astype(float), d[1::2].astype(float)
S = np.abs(np.fft.rfft(l * np.hanning(len(l))))
f = np.fft.rfftfreq(len(l), 1/48000)
print("Spitze bei %.1f Hz, %.1f dB ueber Median" % (f[S.argmax()], 20*np.log10(S.max()/np.median(S))))
```

| Prüfung | Erwartung |
|---|---|
| Muster `0xA5A5` verschwunden | ja |
| FFT-Spitze | **1000 Hz ± 5 Hz**, ≥ 40 dB über dem Median |
| **Gegenprobe Frequenz:** Zuspieler auf 500 Hz | Spitze wandert auf 500 Hz. *Wandert sie nicht, misst der Test das Falsche* |
| **Gegenprobe Kanäle:** nur links spielen | `r` bleibt ≈ 0, `l` nicht. Bestätigt „interleaved, 4 Byte/Frame" |
| **Gegenprobe Format:** als `>i2` (big endian) lesen | muss **schlechter** aussehen als `<i2`, sonst ist die Byteordnung anders |

### Schritt 7 - `SPDS_STATUS` als Fs-Anzeige prüfen (offene Frage §8)

```sh
python3 /root/rd.py 06146010          # bei 48 kHz  -> Wert A
# Zuspieler auf 44,1 kHz umstellen (Modeset!), dann:
python3 /root/rd.py 06146010          # -> Wert B
```

| `A ^ B` | Schluss |
|---|---|
| nur Bits im 5-Bit-Feld `0x1F` | das ist der Fs-Code → Tabelle 32 k / 44,1 k / 48 k / 96 k aufnehmen und im Treiber auswerten |
| Bits in `0x60` / `0x80` mit | Kanalstatus / Lock mit dabei |
| gar keine Änderung | Fs ist hier **nicht** ablesbar → Rate muss von der MIPS-Seite kommen (F2, HDMI-RX N/CTS) |

### Schritt 8 - sauber abschalten

```sh
python3 /root/rd.py -w 06146034 0
python3 /root/rd.py -w 06146038 0
python3 /root/rd.py -w 06146004 <alt aus Schritt 3>
python3 /root/rd.py -w 06148388 0
python3 /root/rd.py -w 06148114 1
python3 /root/rd.py -w 06148114 0
python3 /root/rd.py -w 06148384 0
python3 /root/rd.py -w 06142044 <alt aus Schritt 2>
```

> **Board-Protokoll (doku/100 §5, Memory „Kurze Schritte"):** Jeder Block einzeln, Timeout 20-30 s, nach jedem
> Schreibvorgang die Rückleseprobe ansehen. Der H713 hat keinen aktiven Watchdog - bleibt das Board hängen, ist
> nur ein Kaltstart übrig.

## 11. Treiberentwurf `sun50i-h713-audbrg`

### 11.1 Dateien

```
sound/soc/sunxi/sun50i-h713-audbrg.h    Registerdefinitionen (§2 - §4 dieses Berichts)
sound/soc/sunxi/sun50i-h713-audbrg.c    Platform-Treiber + snd_card + Capture-PCM + IRQ + debugfs
sound/soc/sunxi/Kconfig                 SND_SUN50I_H713_AUDBRG (depends on ARCH_SUNXI, select SND_PCM)
sound/soc/sunxi/Makefile
Documentation/devicetree/bindings/sound/allwinner,sun50i-h713-audio-bridge.yaml
```

Kein ASoC-Kartenverbund nötig: eine eigenständige `snd_card` mit **einem** Capture-PCM ist die kleinste
funktionierende Form und entspricht dem, was Stock tut. `hy310-tv` kopiert dann Karte 1 Capture → Karte 0 Playback
(Paket A2 in doku/100).

### 11.2 DT-Bindung

Anders als Stock **alle** Fenster explizit ins `reg` (kein Hardcoding von Physadressen im Treiber):

```dts
audio_bridge: audio-bridge@6148000 {
        compatible = "allwinner,sun50i-h713-audio-bridge";
        reg = <0x06148000 0x394>,   /* audbrg */
              <0x06146000 0x88>,    /* audif  */
              <0x0614a000 0x10>,    /* topclk */
              <0x06142044 0x4>;     /* highaddr */
        reg-names = "audbrg", "audif", "topclk", "highaddr";
        /* Reihenfolge wie im Stock-DTB: audbrg zuerst! */
        interrupts = <GIC_SPI 115 IRQ_TYPE_LEVEL_HIGH>,
                     <GIC_SPI 113 IRQ_TYPE_LEVEL_HIGH>;
        interrupt-names = "audbrg", "audif";
        clocks = <&ccu CLK_AUDIO_CPU>, <&ccu CLK_AUDIO_UMAC>,
                 <&ccu CLK_AUDIO_IHB>, <&ccu CLK_HDMI_AUDIO>,
                 <&ccu CLK_BUS_HDMI_AUDIO>;
        clock-names = "cpu", "umac", "ihb", "hdmi-audio", "bus-hdmi-audio";
        /* iommus = <&mmu_aw 6 1>; - erst, wenn die IOMMU im Baum lebt */
        status = "okay";
};
```

> **Achtung, echter Fehler im aktuellen Baum:** `mainline/.../sun50i-h713.dtsi` listet
> `interrupts = <GIC_SPI 113 …>, <GIC_SPI 115 …>` - die Reihenfolge ist gegenüber dem Stock-DTB **vertauscht**.
> Mit dieser Reihenfolge landet der AUDBRG-Handler auf dem AUDIF-Interrupt. (Nicht geändert - gehört der
> Hauptsitzung.)
> Die Taktliste ist F1/S17 vorbehalten; `CLK_AUDIO_*` sind in unserem CCU nur AHB-Gates mit Parent `ahb` 100 MHz,
> Stock fährt 400/200/200 MHz und `hdmi_audio_clk` 1152 MHz.

### 11.3 Datenstruktur

```c
struct h713_audbrg {
        struct device       *dev;
        void __iomem        *audbrg, *audif, *topclk, *highaddr;
        struct clk_bulk_data clks[5];
        int                  irq_brg, irq_if;
        spinlock_t           lock;

        struct snd_card             *card;
        struct snd_pcm              *pcm;
        struct snd_pcm_substream    *cap;      /* genau ein Capture-Stream */
        struct snd_dma_buffer        ring;     /* 64 KiB kohärent, 16-Byte-ausgerichtet */
        unsigned int                 period_bytes;
        unsigned int                 hw_base;  /* Byte-Offset im Ring */
        enum { SPDI_IDLE, SPDI_WAIT_SYNC = 2, SPDI_RUN = 3 } spdi_state;
        u32                          owa_pc;   /* zuletzt gelesene Pc */
};
```

### 11.4 PCM-Hardware und Constraints

```c
static const struct snd_pcm_hardware h713_audbrg_capture_hw = {
        .info = SNDRV_PCM_INFO_MMAP | SNDRV_PCM_INFO_MMAP_VALID |
                SNDRV_PCM_INFO_INTERLEAVED | SNDRV_PCM_INFO_BLOCK_TRANSFER,
        .formats          = SNDRV_PCM_FMTBIT_S16_LE,
        .rates            = SNDRV_PCM_RATE_48000,   /* später 32/44.1/48 nach §8 */
        .rate_min = 48000, .rate_max = 48000,
        .channels_min = 2, .channels_max = 2,
        .buffer_bytes_max = H713_OSTREAM_RING,      /* 0x10000 */
        .period_bytes_min = 512,
        .period_bytes_max = H713_OSTREAM_RING / 2,
        .periods_min = 2, .periods_max = 64,
        .fifo_size = 128,
};
```

Zwingende Constraints in `.open`:

```c
/* Der ALSA-Puffer IST der HW-Ring - Größe ist nicht verhandelbar. */
snd_pcm_hw_constraint_minmax(rt, SNDRV_PCM_HW_PARAM_BUFFER_BYTES,
                             H713_OSTREAM_RING, H713_OSTREAM_RING);
/* STEP zählt in 16-Byte-Einheiten, und der Ring muss ganzzahlig in Perioden zerfallen. */
snd_pcm_hw_constraint_step(rt, 0, SNDRV_PCM_HW_PARAM_PERIOD_BYTES, 16);
snd_pcm_hw_constraint_integer(rt, SNDRV_PCM_HW_PARAM_PERIODS);
```

Puffer: `snd_pcm_set_managed_buffer(pcm, SNDRV_DMA_TYPE_DEV, dev, RING, RING)` - kohärent, damit die
CPU sieht, was die DMA schreibt. Physadresse aus `runtime->dma_addr`; prüfen, dass
`(dma_addr >> 28) == ((dma_addr + RING - 1) >> 28)` (256-MiB-Fenster), sonst `-EINVAL`.

### 11.5 PCM-Ops

```c
open      snd_soc_set_runtime_hwparams()-Äquivalent, Constraints, SPDI-Kanal reservieren:
          audif: +0x00 = 0x300052 (W1C); +0x08 = 0x400 (W1C); +0x04 |= 0x300052
          audbrg: +0x384 |= BIT(0)
          spdi_state = SPDI_WAIT_SYNC
hw_params nichts (Puffer ist managed)
prepare   period_bytes merken; OSTREAM0 programmieren:
          highaddr RMW 0xF0 <- (dma>>28)<<4
          +0x100 = (dma>>4)&0xFFFFFF
          +0x104 = ((dma+RING-1)>>4)&0xFFFFFF
          +0x10C = period_bytes >> 4          /* STEP = Periode → ein IRQ je Periode */
          +0x110 = 0x2207
          +0x390 = 0
          +0x114 = 1; +0x114 = 0              /* Flush   */
          memset(ring, 0, RING);  hw_base = 0
trigger   START: +0x38C = BIT(4) (W1C); +0x388 |= BIT(4);
                 audif +0x38 = 0x3000; audif +0x34 = 0x90000000
          STOP:  audif +0x34 = 0; audif +0x38 = 0;
                 +0x388 &= ~BIT(4); +0x114 = 1; +0x114 = 0
pointer   p = readl(audbrg + 0x118);
          hi = readl(highaddr) & 0xF0;
          phys = ((u64)hi << 24) | ((p & 0xFFFFFF) << 4);
          off = phys - runtime->dma_addr;         /* < RING */
          return bytes_to_frames(runtime, off);
close     SPDI aus, IRQ-Maske aus
```

`STEP = period_bytes` ist die Kernaussage aus §3.1/§6.4. Beleg aus `audbrg_istream_config@0x32e8`:

```c
bytes_per_sec = channels * bytes_per_sample * rate;
step = (channels * bytes_per_sample * 10 * rate / 1000) & ~0xF;   /* 10 ms, 16-Byte-gerundet */
if (1000 * step / bytes_per_sec > 50)                              /* > 50 ms?              */
        step = (40 * bytes_per_sec / 1000) & ~0xF;                 /* dann 40 ms            */
if (2 * step >= 0x10000) size = 0x10000; else size = (2 * step) & ~0x7F;   /* Ring = 2 Perioden */
```

STEP ist also eine **Periodenlänge in Zeit** (10 ms, gedeckelt auf 40 ms), und der Ring wird als **zwei
Perioden** dimensioniert. Stock nutzt beim Capture-OSTREAM0 fest 1024 B - bei 48 kHz/Stereo/16 bit
≈ 5,3 ms, also 64 Schritte je Ringumlauf. *(Zahlen und Formel belegt; „ein WLB-IRQ je STEP" ist die
naheliegende Lesart, **vermutet** - Handtest Schritt 5.3 weist es nach.)*

### 11.6 Interrupts

```c
/* SPI 115, AUDBRG - threaded, IRQF_ONESHOT (wie Stock) */
static irqreturn_t audbrg_thread(int irq, void *d) {
        u32 st = readl(a->audbrg + 0x38C) & 0x3FFF;
        if (!st) return IRQ_NONE;
        writel(st, a->audbrg + 0x38C);              /* W1C */
        if (st & BIT(4) && a->cap) snd_pcm_period_elapsed(a->cap);
        return IRQ_HANDLED;
}

/* SPI 113, AUDIF - SPDI-Sync-Automat aus §6.5 */
static irqreturn_t audif_thread(int irq, void *d) {
        u32 st = readl(a->audif + 0x00);
        if (!st) return IRQ_NONE;
        writel(st, a->audif + 0x00);                /* immer alles quittieren */
        if (st & 0x40) { u32 e = readl(a->audif + 0x08);
                         writel(0x400, a->audif + 0x08);
                         dev_warn_ratelimited(...); return IRQ_HANDLED; }
        if (st & 0x02) h713_spdi1_event(a);
        if (st & 0x100000) h713_spds_event(a);      /* Fs/Statuswechsel melden */
        return IRQ_HANDLED;
}
```

`h713_spdi1_event` implementiert Zustand 2→3 (Sync gefunden: `+0x40` lesen, Pc merken, `+0x38 = 0x34FF`),
3 (Resync), 3→2 (Sync verloren: `+0x34` neu schreiben, `SNDRV_PCM_STATE_XRUN` melden).

### 11.7 debugfs

`/sys/kernel/debug/h713-audbrg/regs` mit AUDIF `0x00…0x84` und AUDBRG `0x100…0x118` + `0x384…0x390`,
plus `pc`, `spdi_state`, `hw_ptr`. Ohne diesen Dump ist die Inbetriebnahme blind.

### 11.8 Reihenfolge der Inbetriebnahme

1. F1-Rezept im `probe` (Takte/Reset/Power) → Schritt 0 des Handtests muss aus dem Treiber heraus grün sein,
   sonst `-ENODEV` mit klarer Meldung. Kein Treiber, der stillschweigend auf 0-Registern arbeitet.
2. debugfs-Dump, `arecord -D hw:1,0 -f S16_LE -r 48000 -c 2 -d 5 /tmp/a.wav`.
3. FFT der Datei → 1 kHz.

---

## 12. Was der DSP zwingend beisteuert

**Für Capture: nichts.** Vollständige Xref-Liste (`ida_a32`-Log, Abschnitt „XREFS auf DSP-Funktionen"):

| DSP-Funktion | Aufrufer im Modul |
|---|---|
| `tdAudioDSPReadRegWord` | `Trid_Audio_Output_DelayLine_Set`, `tdAudioDSPWriteRegMaskWord` |
| `tdAudioDSPReadRegMaskWord` | `MAPI_AUD_CFG_GetDelayLineMode` |
| `tdAudioDSPWriteRegMaskWord` | `setdelaylinemode` |
| `aud_dsp1_*`, `aud_dsp2_*`, `WaitDSPFree`, `ReleaseDSP`, `MSPRegMutex` | nur untereinander und aus den `tdAudioDSP*` |

Es gibt **keinen** Pfad von `trid_pcm_capture_*`, `Thal_Alsa_Audio_Capture_Start`,
`Trid_Audio_Output_OWA_Input`, `audbrg_ostream_*`, `AudIf_spdi_*` oder `Handle_WLB_Interrupt` zu einer
DSP-Funktion. Ebenso enthält das Modul **keine** cpu_comm-/Mailbox-/RPC-Symbole (Suche in `ida_a3a`).

Der DSP ist zuständig für:

* **Delaylines** (`0x06146054/58/5C/60/64` plus DSP-Register über die Mailbox) - für Stufe 1 nicht nötig.
* **Wiedergabe** in Stock: der Playback-ISTREAM-Zeiger blieb im März stehen, weil der MIPS/DSP nicht aus dem
  ISTREAM las (`AGENT_HANDOFF_AUDIO_MIPS_DSP.md`). Das betrifft **RLB**, nicht WLB, und damit nicht Capture.
* Klangverarbeitung (SRS/PEQ/DTE) und `Sound_Path_Connect` - Stufe 2.

**Einschränkung, ehrlich benannt:** Der Bridge-Capture braucht den DSP nicht. Ob der **HDMI-RX** ohne MIPS-Zutun
überhaupt auf SPDI1 sendet, ist damit *nicht* beantwortet (§7) - das ist F2. Unsere MIPS-App läuft, also ist das
kein Blocker, aber eventuell eine zusätzliche RPC-Zeile.

---

## 13. Alternative: I2S2 / OWA0-RX statt Bridge

**Ergebnis: nein.** OWA0/OWA1 und I2S0-2 sind im Stock reine Allwinner-Standardschnittstellen ohne jede
Anbindung an den HDMI-RX. Ein Mainline-`sun4i-spdif`/`sun4i-i2s` wäre billig zu haben, liefert aber nicht den
HDMI-Eingangston. *(Parallellauf gegen `re/vendor/HY310/extracted/vmlinux.elf` und `super.fex`, Skripte
`analyse/ida/ida_a43.py` … `ida_a46.py`, Logs `re/captures/weltneuheit/audio-vmlinux-a4[3-6]-*-20260908.log`;
die IDA-Arbeitskopie wurde nach dem Lauf wieder gelöscht.)*

### 13.1 Stock-DTB

| Knoten | Adresse | Stock-Status | IRQ | Pins |
|---|---|---|---|---|
| `owa@2036000` (owa0) | `0x02036000` | **`disabled`** | SPI 23 (`0x17`) | `owa@0` = PH19 |
| `owa@2037000` (owa1) | `0x02037000` | `okay` | SPI 24 (`0x18`) | **keine** (`pinctrl_used = <0>`) |
| `daudio@2034000` (I2S2) | `0x02034000` | **`disabled`** | - | `daudio2@0` = PH10-PH13, Funktion `d_i2s2` |
| `audbrg@203042c` | (kein `reg`) | **`okay`** | SPI 115 + 113 | - |

### 13.2 Wofür Stock owa1 benutzt - nachgeprüft

In `re/vendor/HY310/extracted/super.fex` steht ab Byte-Offset **1 011 846 420** eine Paartabelle
(ALSA-Kartenname → logisches Gerät, Schrittweite 32 Byte), die ich selbst nachgelesen habe:

```
audiocodec  → AUDIO_CODEC      sndowa0    → AUDIO_OWA      sndowa1    → AUDIO_ARC
TridentALSA → AUDIO_SPEAKER    snddaudio0 → AUDIO_DAUDIO0  snddaudio1 → AUDIO_DAUDIO1
snddaudio2  → AUDIO_CAPTURE
```

Bei Offset 1 011 776 092 steht dazu die Liste `AUDIO_SPEAKER,AUDIO_OWA,AUDIO_ARC,AUDIO_HEADPHONE,AUDIO_A2DP`
unter „out playback"/„out gain" - es sind **Ausgabe**geräte. **`owa1` ist der HDMI-ARC-Sender**, deshalb auch ohne
Pins (der ARC-Draht sitzt im HDMI-Stecker). **`TridentALSA` ist AUDIO_SPEAKER** - die Karte, um die es hier geht.
*(belegt)*

### 13.3 Registerbild `sunxi-owa` (Stock-`vmlinux`, `sound/soc/sunxi/sunxi-owa.c`)

Fenster 0x00…0x58, Registersatz **1:1 wie der Mainline-H6-S/PDIF**:

| Offset | Bits | Bedeutung | Stand |
|---|---|---|---|
| 0x00 `CTL` | 0, 1 | Reset / GEN (global enable), in `prepare` beide gesetzt | belegt |
| 0x04 `TXCFG` | 0 TXEN, 1 CHSTMODE, [3:2] Breite, [8:4] Div, 16 PCM/DTS, 31 Mono/Stereo | | belegt |
| 0x08 `RXCFG` | 0 RXEN, 1 RX-Reset | in `trigger` | belegt |
| 0x0C `INT_STA` | | in `prepare` gelesen und zurückgeschrieben | belegt |
| 0x14 `FIFO_CTL` | 31 HUB_EN, 30 FTX, **29 FRX**, [19:12] TXTL=0x40, [10:4] RXTL=0x20, [1:0] RXOM | | belegt |
| 0x1C `INT` | 7 TX-DRQ, **2 RX-DRQ** | | belegt |
| 0x24/0x28 | TXCNT / RXCNT | in `prepare` genullt | belegt |
| 0x34 `RXCHSTA0` | [27:24] RX-Fs, [23:20] Kanäle | | belegt |
| 0x38 `RXCHSTA1` | [7:4] Originalfrequenz, [3:1] Wortbreite | | belegt |
| **0x40** | **14 = RX-Datentyp (0 = IEC-60958, 1 = IEC-61937)** | `sunxi_owa_set_rx_data_type` | belegt |
| **0x4C** | [15:0] RX-Frequenzzähler → `sunxi_owa_get_params_info` rechnet daraus die reale Rate | | belegt |

**Es gibt in diesem Fenster kein Bit, das eine Signalquelle wählt** - die einzigen Enums des Treibers sind
`owa_rx_data_type` = {IEC-60958, IEC-61937}, `owa_hub_function` und `owa_format_function` = {PCM, DTS}. *(belegt)*

### 13.4 Warum das trotzdem nicht der HDMI-Weg ist

1. Im OWA-/daudio-Code des Stock-`vmlinux` gibt es **keinen** String und kein Symbol mit HDMI-Bezug
   (`hdmi_audio`, `hdmirx`, `owa0-rx` stehen nur im CCU-Treiber). `sunxi_hdmiaudio_set/get_audio_mode`
   gehört zu `sunxi-simple-card.c` und schreibt nur ein Feld im Card-Privatdatensatz.
2. Die OWA-Takte kommen aus `pll_audio` (TX) und `pll_periph0_2x` (RX, 200 MHz) -
   **nie** aus `hdmi_audio`. `hdmi_audio_clk` (CCU 0xD84) und `bus_hdmi_audio_clk` (0xD80) beansprucht im
   Stock-DTB **ausschließlich** `tvtop@5700000`, zusammen mit `audio_cpu/umac/ihb` und `vincap_dma`.
3. `daudio@2034000` hat zwar im Register `CTL` Bits [11:8] für einen „HDMI-Modus", der ist aber der
   I2S→HDMI-**Sende**pfad (`daudio_type = 1`, im HY310-DTB nicht gesetzt) und hängt an externen Pins PH10-13.
4. `snd_alsa_trid.ko` mappt **keine** der Adressen `0x02034000/0x02036000/0x02037000` (`REG_Init`, §2) und
   führt mit `audIf_owa_dataTypeTable`, „MSP OWA OUT selector" und „ARC source selector" ein **eigenes**
   OWA/ARC im Trident-Fenster `0x0614xxxx`. Der HDMI-RX-Ton bleibt in der Trident-Domäne.

**Einziges Restargument dafür** (vermutet, ohne Beleg): Es gibt ein ungenutztes CCU-Gate `bus-audio_hub`
(0xA5C Bit 0), vermutlich ein Audio-Hub bei `0x02035000`, ohne DTB-Knoten und ohne Treiber. Falls dieser Hub
HDMI-RX-Audio auf OWA/I2S legen könnte, gäbe es einen zweiten Weg - dafür existiert im Stock kein einziger Beleg.

### 13.5 Nebenbefunde für unseren CCU/DTS-Stand (nur gelesen, nichts geändert)

Aus demselben Lauf, `mainline/build/pruefbau-D-linux-6.18.38/drivers/clk/sunxi-ng/ccu-sun50i-h713.c`
gegen `sun50iw12_hw_clks` im Stock-`vmlinux`:

| Punkt | Mainline | Stock |
|---|---|---|
| `owa1_rx` / `owa0_tx` | `0xa34` / `0xa40` | **vertauscht:** `owa0_tx = 0xA34`, `owa1_rx = 0xA40` |
| Eltern der owa/i2s-Takte | pauschal `{pll-audio, pll-audio-2x, pll-audio-4x}` | `owa_rx_parents` = {pll-periph0-2x, pll-audio, pll-audio, dcxo24M, pll-periph0-800M, pll-periph1-800M, pll-periph0-2x, pll-periph1-2x}; `i2s_owa_tx_parents` = {pll-audio, dcxo24M, …} |
| `bus_hdmi_audio_clk` | `0xd80, BIT(0)` | `0xD80, **BIT(31)**` |
| `hdmi_audio/audio_cpu/umac/ihb` | reine Gates an `ahb` | Mux + Div mit eigenen Elternlisten |
| `spdif@2036000` Taktreihenfolge | `[PLL_AUDIO, BUS_OWA0, OWA0_TX, HDMI_AUDIO, OWA0_RX, AUDIO_CODEC_DAC]` | `[pll_audio, owa0_tx, bus_owa0, pll_periph0_2x, owa0_rx, tvfe_1296M]` - `sunxi_owa_dev_probe` holt per **Index**, also sind Position 1/2 vertauscht und Position 3 falsch |
| owa-Interrupts | 21 / 38 | **23 / 24** (im DTB nachgeprüft, Zeilen 1148 und 1182) |

Das gehört zu **F1/S17** bzw. der Hauptsitzung, nicht in diesen Bericht - hier nur als Fundstelle notiert.

## 14. Korrekturen an bisherigen Notizen

| Stelle | Bisher | Richtig | Beleg |
|---|---|---|---|
| doku/100 §1, Zeile „Stock-Pfad" | „AUDIF … IRQ 115 → AUDBRG … IRQ 113" | **AUDBRG = SPI 115, AUDIF = SPI 113** | Stock-DTB + `platform_get_irq(pdev, 0/1)` |
| `mainline/.../sun50i-h713.dtsi`, `audio-bridge@203042c` | `interrupts = <113>, <115>` | Reihenfolge **vertauscht** gegenüber Stock | dito |
| `legacy/.../audio_bridge.h` | `SPDI1_CFG = +0x38`, `SPDI1_STATUS = +0x3c`, `SPDI1_DATA = +0x40` (3 Register) | **4 Register je Kanal:** `+0x34` CTRL_A, `+0x38` CTRL_B, `+0x3C` STATUS, `+0x40` DATA (SPDI2: `+0x44/48/4C/50`) | `AudIf_GetHandle_spdi1` setzt `Handle+8 = 0x06146034`; `activate` schreibt `base` und `base+4` |
| `legacy/.../audio_bridge.h` | `OSTREAM_PTR = +0x108 + n·0x40` | **`+0x118 + n·0x40`** | `audbrg_ostream_putdata2SW` |
| `legacy/.../audio_bridge_if.c` | `TRID_AUDIF_IRQ_ROUTE` (`+0x08`) bekommt **Registeradressen** geschrieben | `+0x08` ist ein **W1C-Fehlerstatus** mit Bitmaske (`0x400`/`0x800`/`0xF000`) | `AudIf_spdi_Open`, `AudIf_dly_Open`, `AudIf_spdi_Interrupt` |
| `legacy/.../audio_bridge_if.c` | Delayline-Bits in `+0x54` = Bits 0…7 | Bits **24…31** (`byte_117EB` = Byte 3) | `AudIf_dly_SetConfig` |
| `legacy/.../audio_bridge_if.c` | `trid_spdi_config` schreibt `rate` ins STATUS-Register | STATUS (`+0x3C`) ist **nur lesbar**; geschrieben werden CTRL_B (`+0x38`) und CTRL_A (`+0x34`) | `AudIf_spdi_activate` |
| Märznotiz H1 | `info = 0x40203`, daraus `SYNC_APPLPTR` | `262403 = 0x40103` = MMAP\|MMAP_VALID\|INTERLEAVED\|RESUME | `.rodata` `trid_pcm_capture_hardware` |
| Märznotiz H5 | ISTREAM-CFG `a2` = „rate_code" | `a2` = **Kanalzahl** (Bits [16:14]); Bytes/Sample stehen in [10:8] | `audbrg_istream_config`-Disassembly + `Thal_Alsa_Audio_Play_Start` |
| Auftragstext F3 | „Ringgröße 0x20000" | **0x10000 je OSTREAM**; 0x20000 ist der ALSA-`buffer_bytes_max` bzw. die SW-Playback-Ringe | `audbrg_ostream_ConfigMemMap` |
| Auftragstext F3 | „OSTREAM … Start/End/Ptr/Step/Cfg" bei `+0x100+n·0x40` | Reihenfolge ist **START(+0), END(+4), ?(+8), STEP(+0xC), CFG(+0x10), FLUSH(+0x14), PTR(+0x18)** | `ida_a34`-Disassembly |

---

## 15. Offene Punkte

1. **F1/S17:** Einschaltrezept (Takte 400/200/200 MHz, `hdmi_audio_clk` 1152 MHz, Resets, Power-Domäne). Ohne das
   liest der Block 0 und der ganze Handtest fällt bei Schritt 0.3 durch.
2. **F2:** Schaltet die MIPS-Firmware den HDMI-RX-Audioausgang auf SPDI1, und braucht es dafür einen RPC?
   Messbar an Handtest-Schritt 4.1 (Bit 1 in `0x06146000`).
3. **`SPDS_STATUS +0x10`:** Feldbedeutung (Fs-Code?) - Handtest Schritt 7.
4. **`CFG[7:0] = 0x07`** (OSTREAM) bzw. `0x08` (ISTREAM): Bedeutung unbekannt. Werte übernehmen, nicht raten.
5. **`WLB +0x08`:** nur die Delayline schreibt es; für OSTREAM unbenutzt.
6. **`STREAM_SYNC 0x06148390`:** immer 0; Sync-Gruppen ungenutzt.
7. **IOMMU:** Stock nutzt Master 6. Solange unser Baum ohne IOMMU fährt, CMA-Puffer verwenden und die
   256-MiB-Bedingung prüfen.
