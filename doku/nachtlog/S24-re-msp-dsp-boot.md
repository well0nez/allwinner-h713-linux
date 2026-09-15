# S24 (F6) - Warum der MSP-Audio-DSP den `patch_msp`-Download nicht ausführt

Agent F6, 08.09.2026, **reine statische Analyse** (kein Board). Quellen: `snd_alsa_trid.ko`,
`libmspsound.so`, `libmspdriver.so`, `libmsp_util.so`, `libhalsound.so`, `audio.primary.ares.so`,
`libUtility.so`, Stock-`vmlinux.elf`, `u-boot.fex`, `boot_package.fex`, `display.bin`, `super.fex`.
IDA-Arbeitskopien in `analyse/ida/db-audio-boot/` (Originale unberührt), Rohausgaben
`re/captures/weltneuheit/audio-f6-0*-20260908.log`.

Konvention: **[B]** = belegt (Adresse/Fundstelle), **[V]** = abgeleitet, **[?]** = unbekannt.

## 0. Antwort zuerst

**Die wahrscheinlichste fehlende Voraussetzung ist nicht ein weiterer Schreibzugriff, sondern
dass der DSP-Kern den Reset `0xFFF7 = 0` nicht überlebt (bzw. die Insel ihn während des ~1 s
langen Downloads verliert).** Der stärkste statische Beleg dafür ist ein Ausschlussargument:

* `patch_msp` enthält das Paar `80FF = 0001` **genau zweimal** (Block 0 → DSP1, Block 1 → DSP2) und
  in den 720 folgenden Paaren **keine** Adresse `0x00FF`/`0x80FF` (`re/work/audio/patch_msp.txt`) **[B]**.
* Ein *transparenter* Registerpfad müsste `DSP1[0x80FF]` also nach dem Download auf 1 stehen lassen -
  die Registerdatei nimmt genau diesen Schreibzugriff nachweislich an (Messung 08.09.: `:= 1` liest 1).
* Gemessen wurde 0. **Also gehen entweder alle Paare ab dem Reset verloren (Mailbox/Kern nimmt nichts
  mehr an), oder ein Lader konsumiert sie und wendet sie nicht an.** Die zweite Deutung ist mit dem
  Befund aus S16 12:57/13:05 schwer vereinbar: dort blieb nach einem einzigen Schreibzugriff
  `0x06144000` Bit 4 (*write busy*) **stehen** - der Kern hatte die Schreibung nicht quittiert.

Zweitplatzierte Ursache: **Verlust der Insel während des Laufs.** S21 hat belegt, dass
`0x0614A000` zwischen Skriptaufrufen wieder auf 0 fällt, S16 dass die CCU-Gates (`0xd48`, `0xd64`)
nach einem Lauf wieder gelöscht waren. Ein Download dauert ≥ 0,94 s - fällt in dieser Zeit
`0x0614A000` oder `audio_cpu` weg, ist das Ergebnis exakt das beobachtete.

**Ausgeschlossen ist dagegen:** ein weiterer Hardware-Schreibzugriff in der Stock-Initreihenfolge
(§1), ein Boot-Image/Boot-Schritt für den DSP-Kern (§4), und der ARM↔MIPS-Mutex (§3 - er ist gar
kein ARM↔MIPS-Mutex).

---

## 1. Vollständige Stock-Initreihenfolge bis zum ersten `msp_download_sxl` **[B]**

Die Kette ist **kürzer als vermutet**. Zwischen „Insel an" und dem Download stehen genau
**drei MMIO-Schreibzugriffe und drei maskierte DSP-Registerzugriffe**, sonst nichts.

| # | Schritt | Fundstelle | Hardware |
|---|---|---|---|
| 1 | `TriHidtvRegMap()` | `libUtility.so` @0x21718 | nur `open("/dev/hidtvreg")` + 8× `mmap`. Kein Init. `0x0614A000` ist **nicht** in der Liste und wird von `Trid_Util_RegHandle` @0x211C8 per Ad-hoc-`mmap` der 4-KiB-Seite bedient |
| 2 | `InitMSPRegisterAccess()` | `libmspdriver` @0x19298 | nur `OSA_Semaphore_Create("MSP Access")` |
| 3 | `sound_lowlevel_init()` | `libmspsound` @0xDC04 | `0x0614A000 \|= 0x700`; `0x0614A00C = (alt & 0xFF000000) \| 0x001A5E00`; `0x0614A00C \|= 0x01000000` |
| 4 | `MAPI_ADU_CFG_SetDSPClockSpeed(3)` | `libmspdriver` @0xE408 | DSP1 `0x00EE` Maske `0x7F80` ← `0x0180` (Lesen-Ändern-Schreiben, 16 bit) |
| 5 | `MAPI_AUD_CFG_Enable_HDMI_Rx()` | @0xE438 | DSP1 `0x8034` Maske `0x90` ← `0x10` (**8-Bit-Pfad**, Wort-Bit 31 gesetzt) |
| 6 | `MAPI_ADU_CFG_SetHDMIMuteForI2sIn(1)` | @0xE45E | DSP1 `0x8017` Maske `0x01` ← `0x01` (8 Bit) |
| 7 | **`usleep(200000)`** | `SlaveRoutine_Thal_Sound_Init` @0xDCCC | 200 ms **vor** allem Weiteren |
| 8 | `SE_Init()` | @0x10584 | nur Thread |
| 9 | `BP_AUD_Init(profil,len)` | `libmsp_util.so` | **kein Hardwarezugriff** - `libmsp_util.so` importiert weder `Trid_Util_*` noch `aud_*_reg` (`readelf -sW`) |
| 10 | **`msp_download_sxl()`** | `libmspsound` @0xEF10 | `0xFFF7=0`, `0x0000=0`, 200 ms, 724 Paare je 1 ms, Kontrolle |
| 11 | `MAPI_AUD_Initialization()` → `Init_Modules()` | @0x19318 / @0x130E0 | erst **danach**: DSP1 `0x0002` Maske `0x8000` ← `0x8000` |

**Kernelseite (`snd_alsa_trid.ko`) - vollständige Registerkarte** (Konstanten-Scan aller Segmente,
`audio-f6-05-trid-scan-20260908.log`): `0x06142044`, `0x06144000/0C/10/14/18`,
`0x06146000…0x0614607C`, `0x06148000…0x06148390`, `0x0614A000`, `0x0614A00C`, `0x02031078`,
`0x02032078`, `0x02000158`, `0x06E00020`. **Mehr nicht.** Insbesondere **kein** Zugriff auf
`0x06140000-0x06141FFF`, `0x06142000` (nur `+0x44`), `0x0614A004/08`, keine CCU, kein PRCM/PPU.

`snd_trid_probe` @0x2424 ruft: `Alsa_AudioBuffer_Config` → `AudioIO_Init` (= `REG_Init` +
`audbrg_interrupt_enable(1)` + `AudBrg_Init`/`ABP_DTV_Init` = nur IRQ-Anforderung) →
`AudioOutput_ConfigMemMap` → ALSA-Karte → `trid_update_bits(0x06E00020, 1, 0)` (ARC-Quelle = APB).
**`audio_top_clk_init` @0x2D0C wird im Modul von niemandem aufgerufen** (einziger Xref ist die
`__mcount_loc`-Liste) - die drei Schreibzugriffe macht im Stock der Userspace.

Stock-`vmlinux.elf`: die Adressen `0x0614xxxx` kommen **nur in `.debug_info`** vor (Zufallstreffer),
im Code nicht. `u-boot.fex`, `boot0_nand.fex`, `fes1.fex`, `boot_package.fex`, `display.bin`:
kein einziger echter Treffer (die 9 „Treffer" in `display.bin` sind unausgerichtete MIPS-Befehlsbytes).

---

## 2. Semantik der DSP-Register **[B]**, soweit belegt

Adressraum-Verteilung (`tdAudioDSPWriteRegWord` @0x1EE08, `…Read…` @0x1EC98) und Mailbox:

| Mailbox | Ziel | Busy-Bit | Ready-Bit |
|---|---|---|---|
| `0x0614400C` / `0x06144010` | **DSP1** | `0x06144000` Bit 4 | Bit 5 |
| `0x06144014` / `0x06144018` | **DSP2** | Bit 7 | Bit 8 |
| `0x06144004` / `0x06144008` | **Demodulator** (`aud_demod_*_reg` @0xCF98/@0xD26C) | Bit 1 | Bit 2 |

Wortformat: Schreiben `(addr<<16)|val16` nach `+0x0C`; **Adress-Bit 15 wird zu Wort-Bit 31 und
bedeutet 8-Bit-Zugriff**. `0x80FF` ist also nichts anderes als „8-Bit-Zugriff auf Register `0x00FF`".
Lesen: `addr<<16` nach `+0x10` schreiben, Bit 5 abwarten, untere 16 Bit lesen.

| Reg | Bedeutung | Beleg |
|---|---|---|
| `0x0000` | Erweiterungs-/Datenlatch; liefert in `aud_dsp1_read_shared` das **niederwertige Byte** eines 24-Bit-Shared-RAM-Lesevorgangs. `msp_download_sxl` schreibt 0 = Latch löschen | `aud_dsp1_read_shared` @0xD316 (Kernel @0x998C identisch) |
| `0x0001` | **Firmware-Version.** `MAPI_AUD_GetFirmwareVersions` @0xE328 liest genau dieses Register. Board liest `0x0C00`; `patch_msp` schreibt als **letztes Paar** `0001 = 0C19` | @0xE328, `patch_msp.txt` Z. 719 |
| `0x0002` | Bit 15 = globales Enable, gesetzt in `Init_Modules` **nach** dem Download | @0x130E0 |
| `0x00EE` | DSP-Takt, Feld `[14:7]`, gültig 2…8; Stock 3 (`0x0180`); Reset-Vorgabe `0x0200` = 4 | @0xE408 |
| `0x00FA` | 24-Bit-Register, im Blob am Blockende `:= 0x00000D` geschrieben | `patch_msp` Blöcke 2/6/7 |
| `0x00FC` / `0x80FC` | **Interne Firmware-Version**, 24 Bit: `(0x00FC<<8) \| (0x80FC & 0xFF)`. Board liest `0x2209`; Blob schreibt `00FC = 21FF` | `MAPI_AUD_GetInternalFirmwareVersions` @0xE370 |
| `0x00FF` (= `0x80FF`) | **Patch-OK-Flag**, je Kern; Blöcke 0/1 setzen es auf 1; Kontrolle in `msp_download_sxl` | @0xEF10 |
| `0xFFF6` | Seiten-/Bankwahl für Shared-RAM-Lesen (Bits 23:16 der Adresse) | `aud_dsp1_read_shared` |
| `0xFFF7` | **Reset/Modus**; nur in `msp_download_sxl` und den Modul-Downloads, immer `:= 0` | @0xEF10 |
| `0xFFF9` | **[V]** Start-/Ladewort der Code-Blöcke - Block 4 (DSP2) beginnt `FFF9 = A4ED`, Block 5 (DSP1) `FFF9 = 4CF5`; danach folgen Wörter, deren „Adressen" pseudozufällig sind (= Nutzdaten, keine Register) | `patch_msp.txt` |
| `0xFFFA` | **[V]** Abschluss-/Commit-Wort; steht als `FFFA = 0000` am Ende der Blöcke 2, 6, 7 | `patch_msp.txt` |
| `0xFFFB` | Port-Index-Latch für `aud_dsp1/2_read_port` / `…_write_port` | @0xD2D2/@0xD386/@0xD406 |
| `0xFFEF` | Code-ID + Selektor beim **Modul**-Download: `(chan<<8)\|(codeid<<12)` | `msp_download_sxl` |
| `0xFFFF` | **24-Bit-Erweiterungsbyte (LSB)**: `write_reg24` schreibt erst `0xFFFF = val&0xFF`, dann `addr = val>>8`. Deshalb steht im Blob überall `FFFF = 000F` / `00CE = 0070` = 24-Bit-Wert `0x00700F` nach `0xCE` | @0xCE58/@0xD0D4 |
| `0xE0FF \| ((2*code)&0x1E00)` | Download-Steuerregister je Modul: Bit 0 = Enable, **Bit 3 = LOCK** (busy), Bits 1/2/4/7 → Statusbits. `MAPI_AUD_CFG_DownLoadCode(code, 0/1/2/3)` | @0x19020, `MAPI_AUD_Get_DownLoadStatus` @0x191E0 |

**`ResetCheck` ist kein DSP-Zugriff** (`libmspsound` @0x10550): setzt nur die Software-Variable
`dword_20190 = -2` („kein Signal"). Ebenso `EnableCheck`/`DisableValidityFlagCheck`. **[B]**

**Gibt es einen Monitor-/Bootloader-Zustand?** Statisch ist **kein** Kommando belegt, das den Kern
startet oder anhält, außer `0xFFF7`. Der Blob selbst ist die einzige Quelle: Kopf `MSPM`
(Paar `4D53 = 504D`), `0000 = 0x01TT` (TT = 00 → DSP1, 02 → DSP2), `HHHH / LL00` = Länge, dann
`len/4` Paare - dasselbe Kopfformat schreibt `msp_download_sxl` beim Modul-Download **von Hand**
(`4D53=504D`, `0000=0100`, `0000=0400`, `FFEF=…`). Es muss also einen Decoder geben, der auf das
Magic reagiert; ob er in Hardware oder im ROM-Code des Kerns sitzt, ist **[?]**.
**Woran man erkennt, dass der Kern läuft:** `0x0001` (Version, Board `0x0C00`) und `0x00FC`
(intern, Board `0x2209`) liefern plausible Werte ≠ 0 - beides sind ROM-Vorgaben, kein Beweis für
einen laufenden Kern, aber ein Nullwert wäre ein Beweis für das Gegenteil. Der einzige belegte
*Erfolgs*-Indikator ist `0x00FF/0x80FF ≠ 0` auf **beiden** Kernen, plus `0x0001 = 0x0C19` und
`0x00FC = 0x21FF` nach dem Patch.

---

## 3. Mutex - **kein ARM↔MIPS-Mutex** (Korrektur zu S20 §2.3 und zur März-Notiz) **[B]**

| | wartet auf | belegt | gibt frei |
|---|---|---|---|
| **Userspace** `WaitDSPFree` (`libmspdriver` @0x1F0A4) | `0x02032078` (`DSP_ACCESS_KER`) ≠ `0x55` | `0x02031078 := 0x55` (`DSP_ACCESS_USR`) | `0x02031078 := 0xAA` |
| **Kernel** `WaitDSPFree` (`snd_alsa_trid` @0x9F40) | `0x02031078` ≠ `0x55` | `0x02032078 := 0x55` | `0x02032078 := 0xAA` (`ReleaseDSP` @0x9DF0) |

Die Namen stehen in den Fehlertexten des Stock: „DSP_ACCESS_KER == DSP_BUSY" und
„Set DSP_ACCESS_USR Busy, failed". `0x02031078` = **USR** = ARM-Userspace, `0x02032078` = **KER** =
ARM-Kernelmodul. Der MIPS kommt darin nicht vor (deckt sich mit S18). Vorkommende Werte: **`0x55`
(gehalten), `0xAA` (frei)**; jeder andere Wert (unser `0x50`) gilt beiden Seiten als „frei".
Da unser Kernel-Modul nicht geladen ist, hat der Mutex bei uns **keine Wirkung** - die Messung
„mit und ohne Mutex gleich" ist damit erwartungsgemäß und kein Befund.

---

## 4. Weiterer Code für den DSP? Boot-Image? **[B]**

* **Neben `patch_msp` gibt es vier YBin-Module** (`Acoustics_Calibrator`, `SRS_TSHD4`, `STEREO_PEQ`,
  `DTE_Stereo`, dazu `SRS_TruVolume`), alle aus `sound_preset.bin` über `BP_AUD_GetYBinByIndicator`.
  Ablauf je Modul (`msp_download_sxl`): `MAPI_AUD_Init_*_DownLoad(id,…)` → `0xFFF7=0`, `0x0000=0`,
  `4D53=504D`, `0000=0100`, `0000=0400`, `0xFFEF=(chan<<8)|(codeid<<12)`, dann die Paare ab
  `ybin+40` - **ohne** die 200 ms und **ohne** 1 ms je Paar. Kontrolle wieder `0x80FF` auf beiden
  Kernen. Modul-IDs: AC `0x9D00`, SRS-HD4 `0x9C00`, DTE `0x9E00`, TruVolume `0x9C01`, PEQ separat.
  Für „HDMI durchreichen" sind sie entbehrlich (S20 §2.5).
* `Init_Download_Array` (`libmspdriver` @0x130DC) ist ein **Stub** (`return 0`), `download_src_array`/
  `download_out_array`/`mod_peqst3_download` existieren in diesem Build **nicht**.
* `MAPI_AUD_CFG_DownLoadCode` lädt **keinen Code**, es schaltet nur Enable/LOCK-Bits im Register
  `(2*code)&0x1E00 | 0xE0FF`.
* **Kein Boot-Image für den Audio-DSP.** `MSPM` kommt im gesamten Stock-Abbild
  (`super.fex`, 1,6 GB) **nur an einer einzigen Stelle** vor: 8 Treffer bei Dateioffset
  1 017 152 552…1 017 155 380, also innerhalb `libmspsound.so`/`patch_msp`. In
  `boot_package.fex`, `u-boot.fex`, `vmlinux.elf`, `boot-resource.fex`, `mediadata.fex`, `misc.fex`,
  `Reserve0.fex`, `dtbo.fex`: **null** Treffer für `MSPM`, `ybin`, `sound_preset`, `msp_download`.
  ⇒ **Der Kern bootet aus ROM; unser Fehler ist kein fehlendes Firmware-Image, sondern ein
  fehlendes Hardware-Enable bzw. ein sterbender Kern.**
* Fundstück: `sound_preset.bin` (60 480 B) und `libmsp_util.so` liegen seit heute unter
  `re/work/audio/stock/` (Agent F5 aus `super.fex`) - S20 §3.2 („nicht vorhanden") ist überholt.

---

## 5. Experimentliste für die Hauptsitzung

**Regeln:** alles in **einem** Prozess/Skriptlauf (S21: `0x0614A000` fällt zwischen Aufrufen auf 0),
Ausgabe streamen (nie `tail`), 20-30 s je Schritt, **nur lesen** in unbekannten Fenstern, `0x06146000`
(AUDIF) erst nach `audio_top_clk_init` im selben Lauf. Insel-Vorlauf jedes Mal:
16 TVFE-Gates `0xd10…0xd60` Bit 31 → `0xd64 |= 0x10001` → `0x06700000 := 0x003003FF` →
`0x0614A000 |= 0x700` → `0x0614A00C := (alt&0xFF000000)|0x001A5E00`, dann `|= 0x01000000` →
Probe `0x06142044` Bits 7:0 `:= 0x5A` (muss `0x5A` lesen).

| # | Experiment | Genaue Folge | Erwartung / Aussage |
|---|---|---|---|
| **V1** | **Überlebt die Mailbox den Reset?** (wichtigstes) | (a) `0x06144000` lesen → **A**; (b) `DSP1[0x80FF] := 1`, lesen → **B**; (c) `0x06144000` lesen → **C**; (d) `DSP1[0xFFF7] := 0`, `DSP1[0x0000] := 0`, 200 ms; (e) `0x06144000` lesen → **D**; (f) `DSP1[0x80FF] := 1`, lesen → **E** | Positivkontrolle: **B = 1** (bereits gemessen). **E = 1** ⇒ Reset unschädlich, Ursache liegt im Lader. **E = 0 oder D mit Bit 4 = 1** ⇒ **der Reset legt den Kern still - das ist die fehlende Voraussetzung** |
| **V2** | **Blockweise Bisektion** | Reset wie oben, dann nur `patch_msp.bin` Bytes `0x000-0x00F` (Block 0, 4 Paare, 1 ms Abstand), dann `DSP1[0x80FF]` lesen. Danach in einem neuen Lauf `0x000-0x01F` (+Block 1) und zusätzlich `DSP2[0x80FF]` (über `+0x14/+0x18`). Weiter: `…0x09B` (Bl. 0-3), `…0x50F` (+Bl. 4), `…0xAA3` (+Bl. 5), `…0xB4F` (alles, 2896 B) | Block 0 allein: **1** ⇒ Strom wird durchgereicht oder korrekt verarbeitet; **0** ⇒ die Paare werden konsumiert und verworfen. Die erste Stufe, ab der `0x80FF` kippt, benennt den schuldigen Block (Verdacht: Bl. 4/5, `FFF9`-Codeblöcke) |
| **V3** | **Insel-/Taktüberwachung während des Downloads** | vor dem Lauf, nach je 100 Paaren und danach lesen: `0x02001d48`, `0xd4c`, `0xd50`, `0xd64`, `0x0614A000`, `0x0614A00C`, `0x06144000` | Soll durchgehend `0x80000002 / 0x80000002 / 0x80000007 / 0x00010001 / 0x00000700 / 0x011A5E00 / Bit 4 = 0`. Jeder Abfall = Ursache (S16: Gates waren nach dem Lauf gelöscht) |
| **V4** | **Bit-4-Buchführung** | im Download je Paar auf `0x06144000` Bit 4 = 0 warten, max. 1 ms; Anzahl der Zeitüberschreitungen und **Index des ersten** protokollieren | 0 Überschreitungen erwartet. Erster Index ≈ 4 ⇒ der Kern nimmt schon nach dem Reset nichts mehr an; Index in Block 4/5 ⇒ FIFO-Überlauf beim Codeblock |
| **V5** | **Lebt DSP2?** | über `+0x14/+0x18` lesen: `DSP2[0x0000]`, `[0x0001]`, `[0x00FC]`, `[0x80FC]`; dann `DSP2[0x80FF] := 1` und zurücklesen | Positivkontrolle DSP1: `0x5451 / 0x0C00 / 0x2209`. DSP2 alles 0 **und** Schreibtest hält nicht ⇒ DSP2 antwortet nicht, die Stock-Kontrolle kann nie grün werden |
| **V6** | **Stock-Reihenfolge vollständig** | nach `audio_top_clk_init`: `0x00EE` Maske `0x7F80` ← `0x0180`; `0x8034` Maske `0x90` ← `0x10` (8-Bit-Pfad, Wort `0x8034xxxx`); `0x8017` Maske `0x01` ← `0x01`; **200 ms**; dann Download | Bisher fehlten `0x8034`, `0x8017` und die 200 ms. Wahrscheinlichkeit gering, Kosten null. `0x8034` sollte danach `0x10` lesen (heute liest es 0) |
| **V7** | **DSP-Takt nach dem Reset setzen** | Reset → 200 ms → `0x00EE` Maske `0x7F80` ← `0x0180`, zurücklesen → Download | Liest `0x0180` ⇒ Registerdatei lebt nach dem Reset. Liest weiter `0x0200`/0 ⇒ bestätigt V1 |
| **V8** | **`audio_ihb` auf Stock-Elternteil** | `0x02001d50 := 0x81000002` (200 MHz aus pll-periph0) statt `0x80000007` (162 MHz aus pll-video0-4x), dann V2 Stufe 1 | Ändert sich `0x80FF` nach Block 0, ist die Rate des internen Host-Busses die Ursache |
| **V9** | **Download ohne Reset** | Insel an, **kein** `0xFFF7`/`0x0000`, direkt die 724 Paare, dann `0x80FF` beider Kerne, `0x0001`, `0x00FC` | `0x80FF = 1` ⇒ der Reset war das Problem. `0x0001 = 0x0C19` und `0x00FC = 0x21FF` ⇒ der Blob ist vollständig angekommen |
| **V10** | **Unbekannte Register lesen (nur lesen)** | `0x0614A004`, `0x0614A008`; `0x06142000…0x06142040` in 4-Byte-Schritten; `0x06144020…0x0614403C` | Sucht ein DSP-Reset-/Enable-Bit. `0x06142000` liest heute `0x00F003FF` (Bits 0-9 + 20-23) - dieselbe Form wie der TVFE-Router `0x06700000` (`0x7FF` → Stock `0x003003FF`). **Nicht blind schreiben** |

**Nicht empfohlen:** blindes Abtasten unbekannter *DSP*-Registeradressen über die Mailbox (Hänger 5
vom 08.09.), und Schreibzugriffe auf `0x0614A004/08` oder `0x06142000` ohne vorherige Lesewerte.

---

## 6. Offene Punkte

| # | Punkt |
|---|---|
| 1 | Ob der `MSPM`-Decoder in Hardware oder im ROM-Code des Kerns sitzt - statisch nicht entscheidbar; V2 entscheidet es am Gerät |
| 2 | Bedeutung von `0xFFF9`/`0xFFFA` nur aus dem Blob abgeleitet, in keinem Stock-Code referenziert |
| 3 | Es existiert **kein** Stock-Abzug von `0x0614xxxx` im Baum (S17 §5.6 weiterhin offen). Damit ist unklar, ob `0x0614A000 = 0x700` und `0x06142000 = 0x00F003FF` den Stock-Werten entsprechen |
| 4 | `0x0614A004`/`0x0614A008` und `0x06142000` werden von **keinem** Stück Stock-Software geschrieben - sie sind entweder Reset-Vorgaben oder werden von boot0/BROM gesetzt; für uns nicht nachprüfbar |
| 5 | Wer die CCU-Gates (`0xd48`, `0xd64`) und `0x0614A000` nach einem Lauf wieder löscht, ist weiter offen (S16/S21). V3 misst es mit |
| 6 | `0x0000 = 0x5451` (Board) ist unerklärt; als Latch-Restwert plausibel, aber nicht belegt |

## 7. Erzeugte Dateien

| Datei | Inhalt |
|---|---|
| `analyse/ida/db-audio-boot/` | Arbeitskopien `libmspdriver.so.i64`, `libmspsound.so.i64` (aus `db-audio-libs/`), `libmsp_util.so`, `libUtility.so`, **neu** `snd_alsa_trid.ko.i64` |
| `analyse/audio/arbeit/f6-dsp-boot/f6_00_names.py` | Funktionsliste je Datenbank (Regex) |
| `analyse/audio/arbeit/f6-dsp-boot/f6_01_driver.py` | Dekompilat `libmspdriver`: Mailbox, `td*`, Download-Status, Versionen |
| `analyse/audio/arbeit/f6-dsp-boot/f6_02_sound.py` | Dekompilat `libmspsound`: `msp_download_sxl`, `sound_lowlevel_init`, `ResetCheck`, `Sound_Path_Init` |
| `analyse/audio/arbeit/f6-dsp-boot/f6_03_mkdb.py` | erzeugt die IDA-DB für `snd_alsa_trid.ko` |
| `analyse/audio/arbeit/f6-dsp-boot/f6_04_trid.py` | Dekompilat Kernelmodul: `probe`, `REG_Init`, `audio_top_clk_init`, `aud_dsp*`, Mutex |
| `analyse/audio/arbeit/f6-dsp-boot/f6_05_scan.py` | Scan aller Hardware-Adresskonstanten + Xrefs |
| `analyse/audio/arbeit/f6-dsp-boot/f6_06_regs.py` | ctree-Scan aller DSP-Registerzugriffe mit konstanter Adresse |
| `analyse/audio/arbeit/f6-dsp-boot/f6_07_util.py` | Dekompilat `libUtility`: `TriHidtvRegMap`, `Trid_Util_RegHandle` |
| `analyse/audio/arbeit/f6-dsp-boot/f6_08_const.py` | Konstantensuche über alle Stock-Binärdateien |
| `re/captures/weltneuheit/audio-f6-01-driver-20260908.log` | Rohausgabe zu `f6_01` |
| `re/captures/weltneuheit/audio-f6-02-sound-20260908.log` | Rohausgabe zu `f6_02` |
| `re/captures/weltneuheit/audio-f6-04-trid-20260908.log` | Rohausgabe zu `f6_04` |
| `re/captures/weltneuheit/audio-f6-05-trid-scan-20260908.log` | Registerkarte des Kernelmoduls |
| `re/captures/weltneuheit/audio-f6-06-driver-regs-20260908.log` | DSP-Registerzugriffe gruppiert |
| `re/captures/weltneuheit/audio-f6-07-util-20260908.log` | `libUtility`-Dekompilat |
| `re/captures/weltneuheit/audio-f6-08-konstanten-20260908.log` | Konstantensuche in allen Stock-Binaerdateien |
| `re/captures/weltneuheit/audio-f6-09-demod-init-20260908.log` | `aud_demod_*`, `Enable_HDMI_Rx`, `Init_Modules` |

Gelesen, nicht verändert: `re/vendor/**`, `re/ida/IDA_hy310/**`, `re/work/audio/**`, `legacy/**`,
`doku/nachtlog/S16…S21`, `re/notes/AGENT_HANDOFF_AUDIO_MIPS_DSP.md`.
