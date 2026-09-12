# S27 (F9) — Was ist DSP2, und hängen die `pll-periph0`-Abgriffe bei uns halbiert?

Agent F9, 08.09.2026, **reine statische Analyse** (kein Board). Arbeitskopien
`analyse/ida/db-audio-f9/{libmspdriver.so,libmspsound.so,vmlinux.elf}.i64` (Originale unberührt),
lesend `re/vendor/HY310/extracted/vmlinux.elf` (DWARF), `re/work/audio/patch_msp.{bin,txt}`,
`mainline/external/u-boot/`, `mainline/build/…/drivers/clk/sunxi-ng/`. Skripte
`analyse/audio/arbeit/f9-dsp2-periph0/f9_*.py`, Logs `re/captures/weltneuheit/audio-f9-*.log`.
**[B]** belegt · **[V]** abgeleitet · **[?]** unbekannt.

## 0. Antwort zuerst

1. **DSP2 ist der Klangeffekt-Kern, kein Decoder.** Sein Fenster `0xE000–0xEFFF` gehört ausschließlich
   fünf herunterladbaren Modulen (SRS-HD4, Acoustics-Calibrator, SRS-TruVolume, DTE, Downloadable-PEQ).
   Der HDMI-PCM-Pfad `0xC1`/`0x89` braucht **nichts** davon.
2. **DSP2 wird nur von DSP1 gestartet**, über die Typ-`0102`-Blöcke, die komplett durch DSP1s Mailbox
   `0x0614400C` laufen. Es gibt in der ganzen Stock-Software **keine** Takt-/Reset-/Enable-Sequenz für DSP2.
3. **Die `0102`-Blöcke dürfen weg** — bei nicht funktionierendem Weiterreichen sogar schädlich (§3.3).
4. **Nicht-PCM** erkennt der Stock zweifach: HDMI-RX `0x06840040[7]` und DSP-seitig **SPDIF_RX2**
   `DSP1[0x800A]` (Bit 7 gültig, Bit 5 komprimiert, Bits [4:0] = IEC-61937-Datentyp) — §4.
5. **`pll-periph0` ist bei uns NICHT halbiert**: physisch 600 / 1200 / 2400 / 800 MHz, exakt wie Stock.
   N=100+Bit0=1 und N=50+Bit0=0 sind gleichwertig. Falsch ist nur unser **Mainline-CCU-Modell** (§6.1).

# Teil A — DSP2

## 1. Was DSP2 überhaupt erreicht **[B]**

`tdAudioDSPWriteRegWord(dsp_id, addr, val)` **libmspdriver @0x0001EE08**, `…ReadRegWord` @0x0001EC98:
`0xFF00–0xFFFF`/`0xF000–0xFEFF` → DSP1 (Bit 8 = 1 → 8 bit); **`0xE000–0xEFFF` → immer DSP2, `dsp_id`
wird ignoriert**; `0x80FF` → `dsp_id` 0 = DSP1, 1 = DSP2; `0x0000–0x7FFF`/`0x8000–0xFEFF` →
0 = DSP1, **1 = DSP2**, sonst Demodulator (`aud_demod_write_reg` @0x0000CF98).

DSP2-Mailbox `aud_dsp2_write_reg` @0x0000CF54 / `…_read_reg` @0x0000D214 / `…_reg8` @0x0000D56A und
@0x0000D3AE: Schreiben `0x06144014` mit `(addr<<16)|val` (8 bit zusätzlich Bit 31), Lesen
`0x06144018`; Busy `0x06144000` Bit 7, Ready Bit 8. Die Adresse steckt im `PKHBT R1,R4,R5,LSL#16`
@0x0000CF7A — Hex-Rays zeigt sie fälschlich nicht (`audio-f9-06-disasm.log`). Zeitgrenze ist eine
Zählschleife (21 000 000), nicht wie bei DSP1 eine Zeitmessung; Fehlerwert `0xDEADBEEF` bzw. `0xEF`.

## 2. Wofür der Stock DSP2 benutzt — vollständig **[B]** (`audio-f9-01/02/04`)

* **56 Aufrufstellen mit `dsp_id = 1` in `libmspdriver.so`**, davon 54 in vier Modulfamilien:
  `func_set_srshd4_*` (@0x000123D0…0x00012B4A), `func_set_srstv_*`/`func_srstv_enable`
  (@0x00012ECC…0x00013096), `func_set_dte_*` + `…_upscale/downscale/energy_limit/energy_decay/
  soft_limiter` (@0x00012BE0…0x00012E86), `func_set_acoustics_calibrator_*` (@0x00012B6C…0x00012BDC);
  die übrigen zwei in `MAPI_AUD_GetInternalFirmwareVersions` @0x0000E370 (Diagnose). **In
  `libmspsound.so` genau 6 Stellen** — alle `tdAudioDSPReadRegWord(1, 0x80FF, …)` in
  `msp_download_sxl` @0x0000EF10, die Erfolgskontrolle.
* Registerbasis dieser Module = **`((code & 0xF) << 9) | 0xE000`**, Feld `+92` der Modulstruktur,
  gesetzt in `Init_Module_SRSHD4` @0x00018288 (`dword_2AB94`), `Init_Module_ACOUSTIC_CALIBRATOR`
  @0x000185B8, `Init_Module_SRS_TruVolume` @0x00018754, `Init_Module_DTE` @0x000189E4 (`dword_295F8`),
  `Init_Module_DownloadablePEQ` @0x00018D50. Beispiele: `srshd4_enable` → `base|5`,
  `srshd4_technologies` → `base|0x104`, `dte_mode` → `base|0xB`, `srstv_enable` → `base|7`.
* **Konstantenscan über den gesamten Code:** `0xE000` kommt **nur** in diesen fünf `Init_Module_*` vor,
  `0xE0FF` nur in `MAPI_AUD_CFG_DownLoadCode` @0x00019020 und `MAPI_AUD_Get_DownLoadStatus` @0x000191E0.
  `DownLoadCode(code, op)` arbeitet auf `((2*code)&0x1E00)|0xE0FF` (Bit 0 Enable, Bit 3 LOCK) — es
  lädt keinen Code, es schaltet nur die Download-Freigabe des Moduls.
* **Gegenprobe:** Decoder (@0x000171EC), Demod (@0x00016EEA), Surround-Decoder (@0x00013658),
  Post-Processing, PEQST/PEQMO, DRC, Volume, Delay, Mixer, I2SIN/OUT, SPDIF — **kein** `0xE000`.
  Demod/SIF laufen mit `dsp_id = 2` (Mailbox `0x06144004/08`); die SIF-Tabelle `unk_222E0`
  @0x000222E0 (32 Einträge, `audio-f9-08-siftab.log`) enthält nur `dsp_id` 0 und 2.
* **Rolle:** SRS TruSurround HD4, SRS TruVolume/TSXT, DTE, Acoustics-Calibrator, ladbarer PEQ —
  reine Nachbearbeitung. Kein Decoder, kein Demod, keine Quelle, keine Senke.

### 2.1 Braucht Pfad `0xC1`/`0x89` DSP2? **Nein [B]**
`Init_Modules` @0x000130E0 legt diese fünf **nicht** an; sie hängen an `init_srshd4_flag`/
`init_srstv_flag`/`init_ac_flag`/`init_dte_flag`/`init_peq_flag`, die erst ein YBIN-Download setzt —
und auf dem HY310 gibt es **keinen** YBIN-Blob (`MSPD`-Anzahl 0, S23 §5). Pfad `0xC1` = `I2SIN1 →
DRC1/2 → TONECONTROL1 → PEQST2 → PEQST1 → VOLUME1/2 → DELAY1 → I2SOUT1` (S23 §4.4), alles DSP1.
Deckt sich mit dem Board: HDMI-Ton läuft seit S16 17:55 mit totem DSP2.

## 3. Wie DSP2 lebendig wird
**3.1 Keine Hardware-Sequenz [B].** `msp_download_sxl` @0x0000EF10 schreibt **jedes** der 724 Paare
mit `aud_dsp1_write_reg` nach `0x0614400C` — auch die der DSP2-Blöcke. In der ganzen Kette kein
einziger Zugriff auf `0x06144014` und kein DSP2-Takt-/Reset-Register. Mit S24 §4 (kein Boot-Image)
und S24 §1 (Kernelmodul kennt nur `0x06144000/0C/10/14/18`): **DSP2 kann nur über DSP1 hochkommen.**

**3.2 Der Blockkopf ist die einzige Steuerung [B].** Rohbytes aus `patch_msp.bin`:

```
+0x0090  4d53 504d 0000 0102 0004 6800   MSPM, DSP2, Länge 0x468 = 1128  (Block 4)
+0x0514  4d53 504d 0000 0100 0005 8800   MSPM, DSP1, Länge 0x588 = 1416  (Block 5)
```
Als Mailboxwörter: `0x0000 := 0x0102` (Zielwahl), dann `0x0004 := 0x6800` / `0x0005 := 0x8800`.
**Ergänzung zu S16 16:00:** `0x0004`/`0x0005` sind keine echten Register, sondern die Adressanteile
des *Längenworts* (Länge = `(HHHH<<8)|LL`). Dass unser Board `0x0004 = 0x6800` zurückliest und
`0x0005 = 0`, heißt: DSP1s Monitor hat das Längenwort des DSP1-Blocks konsumiert, das des
DSP2-Blocks aber durchfallen lassen — **das Weiterreichen für Typ `0102` ist bei uns nicht aktiv.**
Was DSP1s ROM-Monitor mit einem `0102`-Block intern tut, ist statisch **[?]**; belegt ist nur, dass
es einen Decoder auf das `MSPM`-Magic geben muss (dasselbe Kopfformat schreibt `msp_download_sxl`
beim Modul-Download von Hand).

**3.3 Weglassen? Ja [B] — und vermutlich nötig [V].** Betroffen: Blöcke 1 (DSP2-Flag), 3 (4 Paare),
4 (Code, 1128 B), 6 (23 Paare) = 322 Paare (`--dsp1only`). Nichts geht verloren: kein Modul des Pfads
liegt auf DSP2 (§2.1), die übrigen DSP2-Zugriffe sind Diagnose, und die einzige Stelle, die scheitert,
ist die Kontrolle `DSP2[0x80FF] != 0` in `msp_download_sxl` — ein Logzweig, kein Zustand.
Board-Gegenprobe liegt vor (S16 17:05: `--dsp1only` 3/3, voller Strom hängt in ~50 %).
Zusätzlich schreiben die `0102`-Blöcke **dieselben Registernummern** wie die `0100`-Blöcke
(`patch_msp.txt`): Block 2 (DSP1) setzt `00D2/00D3 = 0x00700F/0x007010`, Block 3 (DSP2) dagegen
`0x00100F/0x001010`, Block 6 (DSP2) überschreibt `00D2/00D3/00FC/0040…004A`, und Block 7 (DSP1)
stellt `00D2/00D3` **nicht** wieder her. Wird `0102` nicht weitergereicht, landen 3 und 6 auf DSP1
und zerstören dort genau die Zeiger, die Block 5 (DSP1-Code) braucht — passend zu S16 V2 (Flag fällt
nach Block 4, `0xDEAD` nach Block 5). **Falsifizierbarer Test:** voller Strom, aber
`00D2 := 0x00700F` / `00D3 := 0x007010` unmittelbar vor Block 5 nachziehen.
**Empfehlung:** die `0102`-Blöcke dauerhaft überspringen.

## 4. Nicht-PCM erkennen

### 4.1 DSP-seitig — SPDIF_RX2 mit IEC-61937-Codes **[B]** (neu)
`CalculateStatus` **libmspsound @0x00010464** liest `DSP1[0x800A]` (8 bit), `DSP1[0x000B]` (16 bit)
und `DSP1[0x800B]`. `SE_Thread_Main` @0x00010718 bildet das Ergebnis über die Tabelle `dword_C1B8`
@0x0000C1B8 = `{0x10, 0x01, 0x01, 0x02, 0x04, 0x40, 0x80, 0x100, 0x200, 0x00}` auf `SE_Handler`
@0x000109B0 ab, dessen Logtexte die Bedeutung nennen: `0x001` **PCM**, `0x002` AC3, `0x004` DTS,
`0x040` EAC3, `0x080` DTS-HD, `0x100` MAT, `0x200` 128K, `0x010` **NONE**, `0x020` „AC3/DTS Pause",
`0x10000` Demod-MTS.

Auswertung mit `v = DSP1[0x800A]`: `v & 0x80 == 0` → **kein gültiges Signal** (→ NONE);
`v & 0x20` = **komprimiert**, dann `v & 0x1F` = Datentyp (`1` AC3, `0x0B/0x0C/0x0D/0x11` DTS,
`0x15` EAC3, sonst „unbekannt", kein Ereignis); sonst PCM, mit `DSP1[0x000B] & 0x4000` und `v & 0x40`
als Gültigkeitsgatter (abschaltbar über `DisableValidityFlagCheck` @0x000103AC). Die Zahlen sind
**exakt die IEC-61937-`Pc`-Datentypen** (1 AC-3, 11/12/13 DTS-I/II/III, 17 DTS-HD, 21 E-AC-3).

Diese drei Adressen sind belegbar die **Statusregister von SPDIF_RX2**: `Init_Module_SPDIF_RX`
@0x00017990 legt `mod_spdifrx1` @0x0002A8F0 / `mod_spdifrx2` @0x0002A9B4 an, Feldindizes 27…39
(`audio-f9-13-spdifrx.log`):

| Modul | Quellwahl | Status 1/2/3 | Enable | Vorverstärker |
|---|---|---|---|---|
| **SPDIF_RX2** | `0x0008` Maske `0x7000`, Shift 12 | **`0x800A`/0xFF, `0x000B`/0xFFFF, `0x800B`/0xFF** | `0x0008` Bit 15 | `0x0009` Maske `0xFF00` |
| SPDIF_RX1 | `0x0004` Maske `0x7000`, Shift 12 | `0x8006`, `0x0007`, `0x8007` | `0x0004` Bit 15 | `0x0005` Maske `0xFF00` |

Eingeschaltet wird der Detektor über **Attribut `0x2201` (8705)** in `Sound_Path_SetAttr` @0x000127D8:
Wert 4 → `EnableCheck(1)` @0x00010560 (Polling an) + `MAPI_AUD_EnableInterface(0x9701)` @0x00019DF0 →
`func_enable_spdifrx` @0x00011128 → `DSP1[0x0008]` Maske `0x8000` ← 1; Wert 5 → aus. Das ist
`Sound_hdmirx_detect_enable(en)` der HAL (S20 §1.6). **Praktisch also:** `DSP1[0x0008] |= 0x8000`,
danach `DSP1[0x800A]` zyklisch lesen — kein zweiter Kern, kein neues Fenster nötig.

### 4.2 HDMI-RX-seitig **[B, aus S18 §3.4/§4.1 — konsolidiert]**
`0x06840040[7]` = nicht-PCM (Statusnibble `[7:4]`; `[2:0]` = Ausgang, 7 an / 0 stumm) ·
`0x06840160` = `0xFF` roh / `0x00` PCM · `0x0684015E[6:4]` = 1 roh / 0 PCM · `0x0684004B[1]`
Übernahme-Strobe · `0x06840056[3:0]` Fs (Channel-Status) · `0x0684015F[6:4]` gemessener Fs-Code.

**Empfohlenes Stummschalt-Kriterium:** `0x06840040` Bit 7 als früher, billiger Indikator (ein
ausgerichtetes 32-bit-Lesen genügt), `DSP1[0x800A]` Bit 5 + Bits [4:0] als genauer, der auch das
Format nennt — beide sind unabhängig, für eine Freigabe beide prüfen.

# Teil B — `pll-periph0`

## 5. Struktur und Abgriffe im Stock-Kernel **[B]** (DWARF, `audio-f9-22/-23`)

`pll_periph0_clk` @0xC1464A30 (104 B, `struct ccu_nkmp`, ops `ccu_nkmp_ops` @0xC0EA1AC4):
`enable = BIT(31)`, `lock = BIT(28)`, **`fixed_post_div = 2`**, `n = {offset 1, shift 8, width 8,
min 12}` → N = reg[15:8]+1, `k = {width 0}` → 1, **`m = {shift 1, width 1, offset 1}`** → M = reg[1]+1,
**`p = {shift 0, width 1, offset 1}`**, `common = {reg 0x020, features 8 = CCU_FEATURE_FIXED_POSTDIV}`.
(`pll_periph1_clk` @0xC14649A8 identisch, `reg = 0x028`.)

`ccu_nkmp_recalc_rate` @0xC05695AC (IDA-Dekompilat, `audio-f9-21-nkmp.log`) benutzt `p` **als
Zweierpotenz-Teiler, ohne `offset`**: `p_div = 1 << reg[0]`; dann `rate = parent·N·k/(p_div·M)`, und
wegen `features & 8` noch `/ fixed_post_div`. Also

> **`pll-periph0` = 24 MHz × N / 2^reg[0] / (reg[1]+1) / 2**

Die drei Abgriffe sind `clk_fixed_factor` und bilden eine **Kette**, keine Sterntopologie
(`parent_hws[0]`): `pll_periph0_2x_clk` @0xC146154C = ×2 von `pll_periph0_clk.common.hw` @0xC1464A8C;
`pll_periph0_2400M_clk` @0xC1461518 = ×2 von **`_2x`**; `pll_periph0_800M_clk` @0xC14614E4 = ÷3 von
**`_2400M`**. Mit `pll-periph0` = 600 MHz ergibt das 1200 / 2400 / 800 — die Namen gehen exakt auf.

## 6. Ist bei uns etwas halbiert? **Nein [B]**

| | Register | N | `reg[0]` → `p_div` | `reg[1]` → M | `pll-periph0` | `-2x` | `-2400M` | `-800M` |
|---|---|---|---|---|---|---|---|---|
| **Stock** | `0xB8006301` | 100 | 1 → **2** | 0 → 1 | 24·100/2/1/2 = **600** | 1200 | 2400 | 800 |
| **Wir** | `0xB8003100` | 50 | 0 → **1** | 0 → 1 | 24·50/1/1/2 = **600** | 1200 | 2400 | 800 |

**Die beiden Unterschiede heben sich exakt auf.** Der Abgriff, den der Vendor „pll-periph0-2x" nennt
(Mux-1-Eltern von `audio_cpu`, `i2h`, `cip-*`, `vincap-dma`), führt bei uns **dieselben 1200 MHz**
wie im Stock; `pll-periph0` dieselben 600 MHz. Drei unabhängige Bestätigungen:

1. **Mainline-U-Boot** `clock_get_pll6()` (`arch/arm/mach-sunxi/clock_sun50i_h6.c`):
   `div1 = reg[0]+1`, `div2 = reg[1]+1`, `return 24000000 * n / 2 / div1 / div2;` — identische Formel.
   `CCM_PLL6_DEFAULT` für `MACH_SUN50I_H616 || MACH_SUN50I_H713` ist `0xa8003100`
   (`clock_sun50i_h6.h:98`; Bit 28 kommt beim Rücklesen als LOCK dazu ⇒ `0xb8003100`). Unser Wert
   stammt also aus dem regulären Upstream-SPL und ergibt dort ebenfalls 600 MHz.
2. **Mainline-Kernel für den H616** (`ccu-sun50i-h616.c`) modelliert `pll_periph0_clk` **genau wie der
   Vendor**: `.m = _SUNXI_CCU_DIV(1,1)`, `.p = _SUNXI_CCU_DIV(0,1)`, `.fixed_post_div = 2`.
3. **Konsistenz der Boot-Teiler** (S17 §1): `0xd48 = 0x2` (audio_cpu, Mux 0, M+1 = 3) ergibt nur mit
   1200 MHz die Stock-Rate 400 MHz; `0xd74 = 0x81000001` (vincap-dma, Mux 1, /2) nur mit 600 MHz die
   Soll-300 MHz. Beides stimmt am Board seit dem Boot — der offene Punkt aus S16 16:00 ist damit zu.

### 6.1 Der Modellfehler sitzt im Mainline-H713-Treiber **[B]**
`ccu-sun50i-h713.c:61` definiert `pll_periph0_clk` (und daneben `pll_periph1_clk`) **ohne `.m` und
`.p`, mit `.fixed_post_div = 4`**. Ohne diese Felder gilt M = 1 und `p_div` = 1, also `rate = 24·N/4`:
bei N = 50 sind das **300 MHz statt 600**. Das Modell stimmt nur zufällig für den Stock-Registerwert
(`reg[0] = 1`) und ist für den Wert unseres eigenen U-Boot **um Faktor 2 zu klein**. Folge: ein
`clk_set_rate(x, R)` auf einem Abkömmling programmiert physisch **2·R**.
Betroffene Muxe (`audio-f9-20-periph0-baum.log`): `cpux`, `ahb`, `apb0/1`, `mbus`, `mips`,
`ce`, `ve-core`, `nand0/1`, `mmc0/1/2`, `spi0/1`, `owa0/1-rx`, `i2h`, `cip-mts/-tsx/-mcx`, `hdmi-audio`,
`svp-dtl`, `afbd`, `dtmb-120M`, `vincap-dma`, **`audio_cpu`/`audio_umac`/`audio_ihb`**.

## 7. Verbraucher von `-2400M` und `-800M` **[B]**

Vollauswertung von `sun50iw12_hw_clks` @0xC1461148 (139 Einträge, `f9_23_tree.py`):
`pll-periph0-2400M` → **nur** `pll-periph0-800M`; `pll-periph0-800M` → **nur** `mmc2` (Mux 1);
`pll-periph1-2400M` → nur `pll-periph1-800M`; `pll-periph1-800M` → nur `mmc2` (Mux 2). Bei uns
**nicht betroffen** (§6). **Nebenbefund:** der Vendor-Mux von `mmc2` (`0x838`) ist 3 bit breit mit
`{dcxo24M, pll-periph0-800M, pll-periph1-800M, pll-periph0-2x, pll-periph1-2x}`; unser
`ccu-sun50i-h713.c` benutzt für `mmc0/1/2` die 2-bit-Liste `{osc24M, pll-periph0-2x,
pll-periph1-2x}` — für `mmc2` ist Index 1 falsch. Folgeauftrag.

## 8. Empfehlung: Mainline-Modell korrigieren, U-Boot und Hardware nicht anfassen

1. In `ccu-sun50i-h713.c` bei `pll_periph0_clk` **und** `pll_periph1_clk` ergänzen (wörtlich aus
   `ccu-sun50i-h616.c`): `.m = _SUNXI_CCU_DIV(1, 1)`, `.p = _SUNXI_CCU_DIV(0, 1)`,
   `.fixed_post_div = 2`. Danach rechnet der Kernel 600 MHz, `-2x` = 1200, `-4x` = 2400
   (= Vendor-`-2400M`). Umsetzung gehört der Hauptsitzung (`mainline/patches/` fasse ich nicht an).
   *Risiko:* kein Registerzugriff, kein Live-Umschalten — nur die Arithmetik ändert sich. Aber jede
   spätere `clk_set_rate`/`clk_round_rate` wählt dann **andere Teiler**: bisher programmierte Raten
   waren doppelt so hoch wie angefordert, MMC-/SPI-/NAND-Takte **halbieren sich** auf ihren Sollwert.
   Gewünschte Korrektur, aber echte Verhaltensänderung — mit Board testen, Bootmedium zuerst.
2. **U-Boot nicht ändern.** `0xB8003100` ist der Upstream-Standard für H616/H713 und physisch
   gleichwertig zu Stocks `0xB8006301`. N = 100 + Bit 0 wäre ein Nulleffekt und würde nur den
   Modellfehler kaschieren; Umprogrammieren laufender PLLs ist als Freeze-Risiko dokumentiert, und
   an `pll-periph0` hängen MIPS-, MBUS-, MMC- und AHB-Takte.
3. **Keinen Verbraucher umhängen** — nichts läuft auf einer falschen physischen Rate. Für die
   Audio-Insel (S17 / Patch 0134) bleibt alles gültig: `audio_cpu` 1200/3 = 400, `audio_umac` und
   `audio_ihb` je 600/3 = 200 MHz; diese drei Register weiter direkt schreiben, nicht per
   `clk_set_rate`.

## 9. Offene Punkte

1. Was DSP1s ROM-Monitor mit einem `0102`-Block tut, bleibt **[?]** — nur am Gerät entscheidbar (§3.3).
2. `DSP1[0x000B]` Bit 14 und `DSP1[0x800B]` in `CalculateStatus` sind **[V]** (Gültigkeit/Kanalstatus).
3. Ob `DSP1[0x800A]` schon bei HDMI-**I2S**-Zulauf (Pfad `0xC1`) gültig wird oder erst nach Umschalten
   der RX-Route auf „roh" (`0x06840160 = 0xFF`), ist statisch nicht entscheidbar — am Board mit
   Bitstream-Quelle messen.
4. `mmc2`-Mux im Mainline-Treiber (§7) — eigener Folgeauftrag.
5. Vor der Modellkorrektur `/sys/kernel/debug/clk/clk_summary` sichern: ob überhaupt jemand
   `clk_set_rate` auf einem periph0-Abkömmling ruft (MMC!), habe ich nicht geprüft.

## 10. Erzeugte Dateien

* `analyse/ida/db-audio-f9/` — Arbeitskopien `libmspdriver.so.i64`, `libmspsound.so.i64`, `vmlinux.elf.i64`.
* `analyse/audio/arbeit/f9-dsp2-periph0/f9_*.py` — `f9_01` ctree-Scan `dsp_id=1` + `0xE000`-Fenster,
  `f9_04` Xrefs/Konstantenscan, `f9_08` SIF-Tabelle, `f9_02/06/09/10/11/12` Dekompilat-/Disassembly-/
  Namens-/Xref-Hilfen, `f9_20…f9_23` ELF-/DWARF-Auswerter (PLL-Strukturen, `clk_init_data`, Taktbaum).
* `re/captures/weltneuheit/audio-f9-01…-04` `dsp_id=1`-Aufrufe, Dekompilate, `0xE000`-Scan ·
  `-05…-08` `msp_download_sxl`, DSP2-Mailbox, Rohdisassembly, SIF · `-09…-13` Nicht-PCM
  (`SE_Handler`, `SE_Thread_Main`, `EnableInterface`, SPDIF-RX) · `-20…-23` Vendor-Taktbaum,
  `ccu_nkmp_*`, PLL-Strukturen roh und als DWARF-`ptype`.

Gelesen, nicht verändert: `re/vendor/**`, `re/work/audio/**`, `mainline/**`, `doku/nachtlog/S16…S25`.
