# S21 (F1b) - Was dem AUDIF (`0x06146000`) fehlt, und wie man ihn anfasst, ohne das Board zu hängen

Auftrag aus [`../100-plan-hdmi-audio.md`](../100-plan-hdmi-audio.md) §3/§5, Anschlussfrage **F1b** zu
[S17](S17-re-audio-top-einschalten.md). Reine statische Analyse; Board, Zuspieler, `mainline/`
und `userspace/` nicht angefasst. Stand 08.09.2026.
Arbeitskopien `analyse/ida/db-audio-msp/`, `db-audio-trid/`, `db-audio-vmlinux/`, neu `db-audif-mips/`
(eigene Kopie von `re/ida/weltneuheit/re_chain/display.bin.i64`, damit der F2-Agent seine
`db-audio-mips/` behält). Skripte `analyse/ida/ida_a60.py` … `ida_a64.py`, Rohausgaben
`re/captures/weltneuheit/audio-audif-a6*-20260908.log`. Board-Skript
**`analyse/hdmi-seq/audif_probe.py`**.

**belegt** = aus Disassembly/Dekompilat, Symboltabelle oder einem Mitschnitt direkt ablesbar.
**vermutet** = geschlossen, am Board nicht geprüft. Adressen sind ARM-physisch.

---

## 0. Antwort zuerst

**Der Audio-Insel fehlt kein CCU-Takt und kein CCU-Reset - es gibt für sie keine. Der einzige
Schalter, den der Stock vor dem ersten AUDIF-Zugriff umlegt und den wir am Board noch nie umgelegt
hatten, sitzt in der Insel selbst: `0x0614A000` Bits 10:8 (`audio_top_clk_init`, im Stock von
*libmspsound* gesetzt, nicht vom Kerneltreiber). Die Reihenfolge „erst `0x0614A000 |= 0x700`, dann
AUDIF lesen" ist am Board noch nie gelaufen: in allen drei mitgeschnittenen Hängern las
`0x0614A000` unmittelbar davor `0x00000000`.**

Leitthese (**vermutet**, Beweis = Schritt S10 des Rezepts): der AUDIF ist der Block der Insel, dessen
Registerschnittstelle in der getakteten Domäne liegt; ohne diesen Takt antwortet er nicht, und die
AXI-Leseoperation kommt nie zurück. Die Stützpfeiler darunter sind belegt:

| # | Befund | Stand |
|---|---|---|
| **B1** | In **jedem** der drei protokollierten Hänger (`versuch3`, `versuch5`, `versuch7`) las `0x0614A000` direkt vor dem AUDIF-Zugriff **0**, und `audio_top_clk_init` war im selben Aufruf **nicht** gelaufen | **belegt** (Mitschnitte, §1) |
| **B2** | In den beiden Läufen, in denen `0x0614A000` auf `0x700` stand (`versuch4`, `versuch6`), antworteten `0x06142044`, die DSP-Mailbox und der AUDBRG - der **AUDIF wurde dort nie angefasst** | **belegt** (§1) |
| **B3** | Der Stock-Kerneltreiber `snd_alsa_trid.ko` fasst in `probe` **kein einziges AUDIF-Register** an. `AudioIO_Init` = `REG_Init` (nur `ioremap`) + `audbrg_interrupt_enable(1)` (schreibt `0x06148384`) + `AudBrg_Init`/`ABP_DTV_Init` (nur `platform_get_irq` + `request_threaded_irq`) + `AudIf_RegisterErrorFunc` | **belegt** (§3) |
| **B4** | Der erste AUDIF-Zugriff im Stock fällt erst bei **PCM-open** an (`AudIf_spdi_Open` → `0x06146000`, `+0x08`, `+0x04`) - also lange nach `sound_lowlevel_init` aus *libmspsound*, das `0x0614A000 \|= 0x700` schreibt | **belegt** (§3) |
| **B5** | In der Vendor-CCU (130 Takte, 58 Resets), im Stock-`vmlinux` (kallsyms + Symboltabelle) und im Stock-U-Boot gibt es **keinen** Takt und **keinen** Reset mit `audif`/`aud_if`/`i2so`/`spdi`/`abpo` im Namen. Für die ganze TV-Insel existieren genau drei Resets: `0xd64`/`0xd88`/`0xdd8` Bit 16 | **belegt** (§4.1) |
| **B6** | Die MIPS-Displayfirmware fasst `0x0614xxxx` **nirgends** an. `reset system_pd_audio_t!!!` kommt aus `HdmiRx_Audio_PD_Reset` (`sub_8B13C67C`, `THDMIRx_TV303_Audio_Driver.cpp:494`) und schreibt zwei Bits in das **HDMI-RX**-Registerfile (`ctx+2`, Bits 5 und 6, gesetzt → gelöscht = Impuls) | **belegt, mit Positivkontrolle** (§4.3) |
| **B7** | In der Audio-Insel schreibt der gesamte Stock-Userspace genau zwei Register: `0x0614A000` und `0x0614A00C` (`sound_lowlevel_init`/`_deinit`, die einzigen Aufrufer von `aud_write_reg` mit fester Adresse). `_deinit` löscht **exakt** Bits 10:8 (`BIC #0x700`) und CFG-Bit 24 | **belegt** (§2) |

Daraus folgt das Rezept in §6: dieselbe Kette wie `versuch6` (die einzige, in der die Insel
nachweislich lebte), plus **zwei Torbedingungen, die scheitern können**, und erst danach der
AUDIF-Zugriff. Beide Tore sind in den Mitschnitten schon einmal *tatsächlich gescheitert* -
sie prüfen also etwas.

---

## 1. Was die Hänger wirklich zeigen

*(Der Auftrag nennt vier Hänger; mitgeschnitten sind drei - `versuch3`, `versuch5`, `versuch7`.
Für den vierten liegt kein Log vor, er ist in der folgenden Auswertung nicht enthalten.)*

Mitschnitte: `re/captures/weltneuheit/s16-audio-20260908/audio-top-versuch{2..7}.log`, erzeugt vom
Skript `audio_top_step.py` (Scratchpad der Hauptsitzung). Aus den Flag-Markern lässt sich für jeden
Lauf genau rekonstruieren, was er getan hat:

| Lauf | Zeit | Schritte | `0x06700000` | `0x0614A000` | Mailbox | AUDBRG | AUDIF |
|---|---|---|---|---|---|---|---|
| v2 | 12:56:44 | `--do` | gelesen `0x7ff` | - | - | - | - |
| **v3** | 12:57:08 | `--do --audio` | `0x7ff` | **gelesen 0** | gelesen 0 | - | **HÄNGT** |
| v4 | 12:59:57 | `--do --router --topclk --probe` | `:= 0x3003ff` ✔ | **`:= 0x700` ✔** | - | - | - |
| **v5** | 13:00:28 | `--do --audio` | (aus v4) | **gelesen 0** | gelesen 0 | - | **HÄNGT** |
| v6 | 13:04:21 | `--do --router --topclk --probe --mbox --audbrg` | `:= 0x3003ff` ✔ | **`:= 0x700` ✔** | `DSP[0x00EE]=0x0200` ✔ | `0xABCDEF` ✔ | - |
| **v7** | 13:04:48 | `--do --mbox --dspclk --audio` | (aus v6) | **gelesen 0** | **keine Antwort**, Status `0x10` | - | **HÄNGT** |
| v8 | ≈13:05-13:10 | `…--topclk --probe` + `ostream_test.py setup` (`ostream-setup.log`) | (gesetzt) | (gesetzt) | - | **voll programmiert** ✔ | - |

`v8` ist der stärkste Beleg für B2: mit gesetztem Audio-Top-Takt nimmt der AUDBRG eine komplette
OSTREAM0-Konfiguration an und liest sie zurück (`START=0x00d00000`, `END=0x00d00fff`, `STEP=0x40`,
`CFG=0x2207`, `+0x118`-Zeiger `0x00d00000`, IRQ-Status `0`) - und auch dieser Lauf hat den AUDIF
nicht angefasst.

Drei Beobachtungen, alle belegt:

1. **Kein einziger AUDIF-Zugriff fand statt, während der Audio-Top-Takt an war.** Die Formulierung
   im Auftrag („hängt mit und ohne `audio_top_clk_init`") lässt sich aus den Mitschnitten **nicht**
   belegen: v3, v5 und v7 haben `audio_top_clk_init` im jeweiligen Aufruf nicht ausgeführt, und in
   allen dreien las `0x0614A000` beim Zugriff `0`.
2. **v7 trennt Router von Audio-Top-Takt.** v7 lief im selben Boot wie v6 (die CCU-Gates standen zu
   Beginn schon auf `0x8xxxxxxx`), hat den Router `0x06700000` also nicht neu geschrieben - er stand
   sehr wahrscheinlich noch auf `0x003003FF` aus v6. Trotzdem antwortete die Mailbox **nicht** mehr,
   und `0x0614A000` las `0`. Die unterscheidende Größe zwischen „Insel antwortet" (v6) und „Insel
   antwortet nicht" (v7) ist damit **nicht** der TVFE-Router, sondern der Audio-Top-Takt.
3. **`0x0614A000` hat seinen Wert zwischen v4→v5 und v6→v7 nicht behalten** (jeweils ~30 s, ohne
   Neustart - die CCU-Gates standen noch). Passend dazu stand die Mailbox in v7 mit Status `0x10`
   (DSP1-Write-Busy) fest, obwohl in v6 der letzte Zugriff sauber mit Status `0x20` endete. Ursache
   offen (§5.2); für das Rezept irrelevant, weil dort ohnehin unmittelbar vor dem AUDIF-Zugriff neu
   geschrieben **und zurückgelesen** wird.

**Was der Hänger technisch ist (vermutet, aber gut gestützt):** ohne `bus-demod` liefert der
Interconnect für den ganzen Trident-Frontend-Raum `0` (deshalb las `0x06146000` vorher einfach `0`,
ohne Hänger). Mit `bus-demod` an wird der Raum echt dekodiert; ein Slave, dessen eigener Takt steht,
gibt keine Antwort, die AXI-Transaktion wird nie abgeschlossen, der Kern bleibt stehen. Genau dieses
Muster ist von `0x068B0000` bekannt (doku/69).

---

## 2. Registerkarte Audio-Top-Takt `0x0614A000` (Fenster 15 Byte)

Der Stock-Kernel-Treiber mappt `ioremap(0x0614A000, 15)` - es gibt also genau vier Register
(`+0x00`, `+0x04`, `+0x08`, `+0x0C`).

| Adresse | Name (Stock-Symbol) | Was der Stock tut | Stand |
|---|---|---|---|
| **`0x0614A000`** | `AUDIO_TOP_CLK_CTL` (`va_audio_top_clk`) | `sound_lowlevel_init`: `\|= 0x700`; `sound_lowlevel_deinit`: `BIC #0x700`. Kein anderes Bit wird je angefasst | Zugriffe **belegt**, Bitbedeutung **vermutet** |
| `0x0614A004` | - | **von keiner Stock-Software je gelesen oder geschrieben** | belegt (Negativbefund) |
| `0x0614A008` | - | dito | belegt (Negativbefund) |
| **`0x0614A00C`** | `AUDIO_TOP_CLK_CFG` | `sound_lowlevel_init`: Bits `[23:0] := 0x001A5E00` (`BFI.W R5, R0, #0, #0x18` - obere 8 Bit bleiben stehen), danach `\|= 0x01000000`. `_deinit`: `[23:0] := 0`, dann Bit 24 löschen | Zugriffe **belegt**, Feldbedeutung **offen** |

Rohdisassembly beider Funktionen: `re/captures/weltneuheit/audio-audif-a64-lowlevel-init-20260908.log`.

**Warum Bits 10:8 Takt-Freigaben sind (vermutet, drei unabhängige Indizien):**
der Registername im Stock-Modul ist `audio_top_clk_ctl` und die schreibende Funktion heißt
`audio_top_clk_init`; `sound_lowlevel_deinit` löscht **genau dieselben drei Bits** wieder (ein
Abschalt-Gegenstück, wie man es von Gates erwartet); und der Legacy-Port hat die Sequenz unter
`TRID_AUDIO_TOP_CLK_CTL` nachgebaut (`legacy/drivers/audio/bridge/audio_bridge_if.c:542`).
**Welches Bit welchen Teilblock taktet, ist nicht belegt** - drei Bits für die drei Blöcke, die
hinter dem Takt-Controller liegen (DSP-Insel, AUDIF, AUDBRG), ist naheliegend, aber unbewiesen.

`0x001A5E00` = 1 728 000. Zwei Lesarten, beide **unbelegt**: eine Frequenz/Zählerkonstante in Hz
(1 728 000 = 36 × 48 000), oder ein 16-Bit-Teiler in `[23:8]` (`0x1A5E` = 6750; 1296 MHz ÷ 6750 =
exakt 192 kHz). Für uns ohne Belang - der Wert ist im Stock konstant und wird unverändert kopiert.

**Wer sonst noch schreiben könnte:** `libmspsound` exportiert `Thal_Sound_ReadReg`/`Thal_Sound_WriteReg`
(`@0x13A88`/`@0x13AA6`), die die Adresse als Argument nehmen. Sie sind die einzigen weiteren Aufrufer
von `aud_read_reg`/`aud_write_reg`; welche Adressen ein RPC-Aufrufer dort hineingibt, steht nicht in
der Bibliothek.

### AUDBRG-Globalregister - kein verstecktes Enable

`REG_Init` mappt `ioremap(0x06148000, 0x394)`; das letzte Register im Fenster ist damit `+0x390`.
Der Stock benutzt `0x06148384` (Gesamt-IRQ-Freigabe), `+0x388` (Maske), `+0x38C` (Status, W1C),
`+0x390` (Stream-Sync, immer `0`). `0x06148380` liegt im Fenster, wird aber **von keiner
Stock-Funktion angefasst** (belegt, `audio-trid-a37-regmap-20260908.log`). Ein AUDIF-Enable steckt
dort nicht. Dass der AUDBRG **ohne** `0x0614A000` funktioniert, ist im Stock durch die Reihenfolge
belegt: `snd_trid_probe` schreibt `0x06148384` Bit 0, bevor irgendein Userspace-Prozess läuft.

---

## 3. Reihenfolge im Stock: wer fasst den AUDIF wann an

Belegt aus `snd_alsa_trid.ko` (`analyse/ida/db-audio-trid/`) und den MSP-Bibliotheken:

```
Kernel, modprobe:
  snd_trid_init -> platform_driver_register
  snd_trid_probe @0x2424
      Alsa_AudioBuffer_Config          (kein MMIO -- REG_Init lief noch nicht)
      AudioIO_Init @0x2d6c
          REG_Init @0x7738             ioremap 0x06146000/0x88, 0x06148000/0x394,
                                       0x0614A000/0x0F, 0x06142044/4, 0x02031078/4, 0x02032078/4
          audbrg_interrupt_enable(1)   ERSTER MMIO-ZUGRIFF: 0x06148384 Bit 0 := 1   (AUDBRG)
          AudBrg_Init                  nur platform_get_irq(0) + request_threaded_irq
          ABP_DTV_Init                 nur platform_get_irq(1) + request_threaded_irq  <-- KEIN MMIO
          AudIf_RegisterErrorFunc      nur Funktionszeiger
      AudioOutput_ConfigMemMap         ion_alloc + dma_buf (kein 0x0614xxxx)
      snd_card_new / PCMs / Mixer
      liest 0x06E00020 (ARC_SRC, TVCAP-Fenster) und loescht dort Bit 0
   ==> im ganzen probe kein einziger Zugriff auf 0x06146xxx.

Userspace, tvservice/msp:
  SlaveRoutine_Thal_Sound_Init @libmspsound 0xDCCC
      TriHidtvRegMap + InitMSPRegisterAccess
      sound_lowlevel_init @0xDC04
          0x0614A000 |= 0x700                       <-- AUDIO-TOP-TAKT AN
          0x0614A00C [23:0] := 0x1A5E00, dann Bit 24
          MAPI_ADU_CFG_SetDSPClockSpeed(3)  -> DSP[0x00EE] Maske 0x7F80 := 0x0180
          MAPI_AUD_CFG_Enable_HDMI_Rx()     -> DSP[0x8034] Maske 0x90   := 0x10
          MAPI_ADU_CFG_SetHDMIMuteForI2sIn(1)->DSP[0x8017] Maske 0x01   := 0x01
      Sound_Path_Init -> msp_download_sxl -> MAPI_AUD_Initialization ...

Audio-HAL, erst bei Wiedergabe/Aufnahme:
  trid_pcm_*_open -> ... -> Trid_Audio_Output_Ostream_Open -> AudIf_spdi_Open @0x4D6C
      ERSTER AUDIF-ZUGRIFF:  0x06146000 := 0x00300052 (W1C)
                             0x06146008 := 0x00000400 (W1C)
                             0x06146004 |= 0x00300052
```

Es gibt in `snd_alsa_trid.ko` **kein** `AudIf_Init`; `REG_Init` ist reines `ioremap`, und
`audio_top_clk_init @0x2d0c` ist im ausgelieferten Modul **toter Code** (nur `__mcount_loc`/
`.ARM.exidx` referenzieren es) - der Vendor verlässt sich darauf, dass der Userspace es macht.

**Damit ist Frage 2 beantwortet:** Vor dem ersten AUDIF-Zugriff liegen im Stock genau diese
Schreibzugriffe: `sunxi_tvtop` (Takte, Reset, Power, `0x06700000 := 0x003003FF`),
`0x06148384` Bit 0 aus dem Modul-probe, `0x06E00020` Bit 0 aus dem Modul-probe und - der Kandidat -
**`0x0614A000 \|= 0x700` plus `0x0614A00C`** aus `sound_lowlevel_init`, gefolgt von drei
DSP-Registern über die Mailbox.

*Nicht belegt, aber sehr wahrscheinlich:* dass `sound_lowlevel_init` zeitlich immer vor dem ersten
PCM-open läuft. Die Reihenfolge steht in keinem Code fest, ergibt sich aber daraus, dass der
MSP-Sounddienst beim Start des tvservice initialisiert und der ALSA-Knoten erst bei Wiedergabe
geöffnet wird (`audio.primary.ares.so` `adev_set_parameters`: `Sound_Init` → `ioctl(0x6666)` →
`init_codec_output_path`).

---

## 4. Was es *nicht* ist - Negativbefunde

### 4.1 Kein CCU-Takt und kein CCU-Reset für den AUDIF

`analyse/hdmi-seq/vendor-ccu-table.txt` (Stock-`vmlinux`, `sun50iw12_ccu_desc`): 130 Takte,
58 Resets. Für die Audio-Insel gibt es **nur**:

| Reg | Name | Rolle | Ist am Board |
|---|---|---|---|
| `0xd48` | `audio_cpu` | TVFE-Gruppe, 400 MHz | Gate gesetzt, `0x80000002` ✔ |
| `0xd4c` | `audio_umac` | TVFE, 200 MHz | `0x80000002` ✔ |
| `0xd50` | `audio_ihb` | TVFE, Stock 200 MHz aus `pll-periph0` | `0x80000007` = 162 MHz aus `pll-video0-4x` (**falscher Mux**) |
| `0xd64` | `bus-demod` Bit 0 + Reset Bit 16 | Registerbus der ganzen Trident-Frontend-Insel | `0x00010001` ✔ |
| `0xd80` | `bus-hdmi-audio` Bit 31, `bus-cap-300M` Bit 30 | TVCAP | `0xc0000000` ✔ |
| `0xd84` | `hdmi-audio` | TVCAP, Stock 1152 MHz | `0x80000000` = **2400 MHz** (`pll-video3-4x` ÷ 1) |

Resets in der TV-Region: **genau drei** - 55 (`0xd64` Bit 16, demod), 56 (`0xd88` Bit 16, tvcap),
57 (`0xdd8` Bit 16, disp). Kein Audio-Reset. `strings`/kallsyms/Symboltabelle des Stock-`vmlinux`
enthalten **kein** `audif`, `aud_if`, `abpo`, `i2so`; `spdi*` nur aus dem IPsec-Stack (`xfrm_*_spdinfo`)
und `spdif_format_xu_info` (USB-Audio). Die einzigen `AudIf_*`-Symbole stammen aus
`snd_alsa_trid.ko` selbst.

### 4.2 U-Boot: nichts

Das Stock-U-Boot (`re/vendor/HY310/extracted/boot_package.fex`, `U-Boot 2018.05-00024-gc128a2c`)
enthält die Zeichenketten `audio_ihb_clk`, `clk_bus_demod`, `hdmi_audio_clk`, `hdmi_audio_bus`,
`reset_bus_demod` - sie liegen aber sämtlich im **eingebetteten DTB** (`tvtop@5700000`-Knoten,
`clock-names`/`reset-names`), nicht im Code. Kein U-Boot-Treiber schaltet die Audio-Takte.

### 4.3 MIPS-Firmware: fasst `0x0614xxxx` nicht an (Schnittstelle zu F2)

Vollständiger `lui`/`li`-Scan über alle Funktionen von `display.bin` nach Immediates im Bereich
`0xB500…0xBFFF` (MIPS-MMIO = ARM-phys + `0xB5000000`) -
`re/captures/weltneuheit/audio-audif-a63-mips-luikarte-20260908.log`:

```
0xB500 -> 0x00000000  MIPS_MMIO_Read/WriteByte, readl_checked, writel_masked ...
0xBA00 -> 0x05000000  NRWinNode__WriteReg, WCETop__SetWindow, memory_agent_onoff ...
0xBA14 -> 0x05140000  ProcWinNode__WriteReg ...
0xBA1C -> 0x051C0000  PanelWinNode__WriteReg ...
0xBA60 -> 0x05600000  NRWinNode_AfbdConfigure, VidDecSignalDetector_GetFrameInfo ...
0xBB50 -> 0x06500000 | 0xBB67 -> 0x06670000 | 0xBB80 -> 0x06800000 (HDMI-RX)
0xBB94 -> 0x06940000  VIncap_EnableCaptureOutput, CapWinNode__WriteReg ...  (INCAP)
0xBCD4 -> 0x07D40000 | 0xBEFA/0xBF00/0xBF80/0xBFF0
   ==> 0xBB64 (= ARM 0x0614xxxx) kommt NICHT vor.
```

Die **Positivkontrolle ist eingebaut**: derselbe Scan findet alle bekannten MIPS-Fenster (AFBD
`0x05600000`, PROC `0x05140000`, Panel `0x051C0000`, INCAP `0x06940000`, HDMI-RX `0x06800000`) in
genau den Funktionen, die aus doku/76 und doku/64 bekannt sind. Ein positiver Befund wäre also
sichtbar gewesen.

`reset system_pd_audio_t!!!` steht in **`HdmiRx_Audio_PD_Reset` (`sub_8B13C67C`)**,
`TV303_Drv/THDMIRx_TV303_Audio_Driver.cpp:494`:

```c
elog_output(3, "hdmi_driver", "…THDMIRx_TV303_Audio_Driver.cpp",
            "HdmiRx_Audio_PD_Reset", 494, "reset system_pd_audio_t!!!");
MIPS_MMIO_WriteByte_Masked(ctx + 2, 0x20, 0x20);   /* Bit 5 setzen   */
MIPS_MMIO_WriteByte_Masked(ctx + 2, 0x40, 0x40);   /* Bit 6 setzen   */
MIPS_MMIO_WriteByte_Masked(ctx + 2, 0x40, 0x00);   /* Bit 6 loeschen */
MIPS_MMIO_WriteByte_Masked(ctx + 2, 0x20, 0x00);   /* Bit 5 loeschen */
```

`ctx` ist die byteadressierte HDMI-RX-Registerbasis (Nachbarn: `HdmiRx_StateMachine_Idle_PreAction`
setzt `ctx+0x1B` für HDCP/DDC-Reset, `ctx+0x00` Bit 6 für TMDS-Reset). **Es ist ein Reset-Impuls im
HDMI-RX, nicht im Audio-Top.** Damit ist die These „die MIPS hält den AUDIF-Takt" **ausgeschlossen**.

**Schnittstelle zu F2 ([S18](S18-re-mips-hdmi-audio.md), nicht dupliziert):** S18 kommt über einen
anderen Weg (alle Adressformen, phys + kseg1, Code + Daten) zum selben Negativbefund und beschreibt,
was die Firmware stattdessen tut - Audio autonom im HDMI-RX, APLL `0x06880000`, Unmute
`link+0x40[2:0] := 7`. Meine Ergänzung ist nur die *Herkunft der elog-Zeile*: sie stammt aus
`HdmiRx_Audio_PD_Reset` und ist ein Reset-Impuls auf `ctx+2` Bits 5/6 im RX. Die Arbeitsteilung ist
damit sauber: die MIPS liefert (oder liefert nicht) den Strom an SPDI1, der **Registerzugang** zum
AUDIF liegt vollständig auf der ARM-Seite und ist Gegenstand dieses Berichts. S18 §8 nennt als
Verdächtigen für die *Quellseite* denselben Takt, den ich hier als Zweig B2 führe: `hdmi-audio`
`0xd84`, bei uns 2400 statt 1152 MHz.

---

## 5. Offene Punkte

1. **Nicht bewiesen, nur konsistent mit allen Messpunkten:** dass `0x0614A000` Bits 10:8 der
   AUDIF-Registerschnittstelle den Takt geben. Beweis = Schritt S10 des Rezepts. Bleibt der Hänger
   auch dann, sind die Zweige B1…B5 aus §6 dran.
2. **Warum `0x0614A000` seinen Wert zwischen zwei Läufen verlor** (§1 Beobachtung 3), ist offen.
   Die MIPS ist als Ursache ausgeschlossen (§4.3); ein Neustart zwischen v4 und v5 bzw. v6 und v7
   ist unwahrscheinlich (die CCU-Gates standen noch), aber aus den Mitschnitten nicht restlos
   auszuschließen. Messung: `audif_probe.py --hold` (schreibt `0x700`, liest bei 0/1/5/30/120 s
   zurück). Ergebnis „hält" ⇒ zwischen den Läufen ist doch neu gebootet worden; „fällt ab" ⇒ echter
   Hardware-Befund und ein eigener Blocker.
3. **`0x0614A004` / `0x0614A008`** werden von keiner Stock-Software angefasst; ob dort ein
   Status- oder Reset-Register liegt, ist unbekannt. Das Rezept liest sie mit (billig, im bereits
   antwortenden Fenster) - ein „AUDIF getaktet"-Statusbit wäre genau dort zu erwarten.
4. **`audio_ihb` läuft mit falschem Elternteil** (162 statt 200 MHz, Mux 0 statt 1). Ob der
   Registerbus der Insel daran hängt: offen. Zweig B1.
5. **`hdmi_audio` (0xd84) läuft mit 2400 statt 1152 MHz.** Das Register gehört zu TVCAP und das
   **Bild läuft damit** - deshalb im Hauptlauf **nicht** anfassen. Zweig B2, mit Bildkontrolle und
   sofortiger Rücknahme.
6. **`0x06E00008` liest bei uns `0x00000504`, Stock schreibt `0x00000404`** (doku/71). Unerklärt,
   niedrig priorisiert; TVCAP antwortet ansonsten sauber.
7. **Keine Stock-Referenzwerte für das AUDIF-Fenster.** Im Baum liegt kein Registerdump von
   `0x06146xxx` aus dem Stock. Der Erfolg von S10 ist deshalb „die Leseoperation kehrt zurück",
   der Beweis, dass es ein echter Slave ist und nicht der Null-Default, kommt aus der
   Schreib-Lese-Probe S11 auf `0x06146058`.
8. **Hinweis aus den März-Notizen (kein Beleg, Notizen sind nachweislich teils falsch, S17 §5.9):**
   `re/notes/AGENT_HANDOFF_AUDIO_MIPS_DSP.md` und `re/notes/WORKLOG.md` beschreiben, dass der
   Legacy-Treiber auf Mainline 6.16.7 einen **AUDIF-Hardware-Interrupt** bekam und
   „AudIF IRQ Status non-zero" las, und dass ein DSP-Mailbox-Rundlauf (`DSP[0x00CE]` schreiben,
   `0x0070` zurücklesen) funktionierte. Genau dieser Treiber ruft in `trid_audioio_init()`
   **zuerst** `0x0614A000 |= 0x700` und **danach** die AUDIF-Register auf
   (`legacy/drivers/audio/bridge/audio_bridge_if.c:537-556`). Das passt zur These und wäre, wenn es
   stimmt, der Nachweis, dass der AUDIF auf Mainline erreichbar ist.

---

## 6. Rezept für den nächsten Versuch

Fertiges Skript: **`analyse/hdmi-seq/audif_probe.py`** (ohne Argument rein lesend).
Es ist genau `versuch6` - der einzige Lauf, in dem die Insel nachweislich antwortete - plus zwei
Tore plus der AUDIF-Zugriff. Jeder Schritt meldet sich **vor** dem Zugriff nach stdout und
`/dev/kmsg`; die letzte Zeile im Log ist der hängende Zugriff. `0x068B0000` und `0xd84` werden
nicht angefasst.

**Aufruf (drei Aufrufe, kurze Schritte, je 20-30 s Timeout):**

```
./audif_probe.py                              # Vorbedingungen, nichts schreiben
./audif_probe.py --do                         # Insel an + beide Tore, AUDIF NICHT anfassen
./audif_probe.py --do --audif --wdt           # derselbe Lauf + AUDIF, mit Watchdog-Netz
```

| # | Aktion | Register / Wert | Erwartung - **Abbruch, wenn nicht** |
|---|---|---|---|
| V0-V2 | Vorbedingungen lesen | `0xd10…0xd64`, `0xd80`, `0xd84`, `0xd88`, PLLs, PPU `0x070010a4`/`0x07001124` | `0xd80 = 0xc0000000`, `0xd88 = 0x00010001`, PDs an (nur Warnung) |
| S1 | alle 16 TVFE-Gates | `0xd10…0xd60` `\|= 0x80000000` | - |
| S2 | Demod-Bus | `0x02001d64 \|= 0x00010001`, 15 ms | liest `0x00010001` |
| **S3** | **Kontrolle Insel-Bus** | lesen `0x06700000` | **≠ 0** (gemessen `0x7ff`) |
| S4 | TVFE-Router (Stock) | `0x06700000 := 0x003003FF` | liest `0x003003FF` |
| **S5** | **Audio-Top-Takt - der neue Schritt** | `0x0614A000 \|= 0x700`; `0x0614A00C := (alt & 0xFF000000) \| 0x001A5E00`, dann `\|= 0x01000000` | `CTL & 0x700 == 0x700`, `CFG = 0x011A5E00`. Vorher werden `+0x04`/`+0x08` mitgelesen (bisher nie gelesen) |
| **S6** | Positivkontrolle 1 | `0x06142044` Bits 7:0 `:= 0x5a`, lesen, zurückschreiben | gelesen `…5a` (v4/v6: ✔) |
| **S7** | Positivkontrolle 2 | `0x06148100 := 0x00ABCDEF`, lesen, zurückschreiben; dann `0x06148380/384/388/38C/390` lesen | gelesen `0x00ABCDEF` (v6: ✔) |
| **S8a** | **TOR 2 - kann scheitern** | Mailbox: `0x06144010 := 0x00EE0000`, ≤200 ms auf `0x06144000` Bit 5 warten, lesen | **Antwort** (v6: `0x0200`; **v7: keine Antwort ⇒ Abbruch**) |
| **S8b** | **TOR 1 - kann scheitern** | `0x0614A000` erneut lesen, unmittelbar vor dem AUDIF-Zugriff | **`& 0x700 == 0x700`** (v3/v5/v7: `0` ⇒ Abbruch) |
| S9 | Netz gegen den Hänger | Watchdog `0x02051000`: `CFG := 0x16aa0001`, `MODE := 0x16aa00B1` (16 s Einmal-Timer), `CTRL := 0x14AF` | belegt seit doku/72 Läufe 66-69: Board startet nach ≤16 s selbst neu, DRAM überlebt (post mortem mit `pm_read`) |
| **S10** | **AUDIF lesen** | `0x06146000` | **die Leseoperation kehrt zurück** (Wert `0` ist zulässig) |
| S10b | Fenster dumpen | `+0x00,04,08,10,18…2C,30,34,38,3C,40,44,48,4C,50,54,58,5C,68,6C,74,78,7C` | Protokoll; interessant `+0x3C`/`+0x4C` (SPDI-Sync) und `+0x10` (SPDS) |
| **S11** | Beweis „echter Slave" | erst `+0x54` (DLY_CFG) lesen, muss `0` sein; dann `0x06146058 := 0x00001234`, lesen, zurückschreiben | gelesen `0x00001234` ⇒ AUDIF lebt; `0` ⇒ nur Null-Default |
| S12 | Watchdog aus | `MODE := 0x16aa0000` | - |

**Warum S8a und S8b keine Alibi-Prüfungen sind:** beide sind in den Mitschnitten schon einmal
*wirklich* gescheitert - S8a in `versuch7`, S8b in `versuch3`, `versuch5` und `versuch7`. Ein
Kriterium, das nicht scheitern kann, prüft nichts; diese beiden können.

**Rückweg:** `0xd64 := 0`, `0xd48/0xd4c/0xd50 := 0x2 / 0x2 / 0x7`,
`0x0614A000 &= ~0x700`, `0x0614A00C &= 0xFF000000` (das ist genau `sound_lowlevel_deinit`).
Ein Neustart stellt den Boot-Zustand ohnehin her; nichts davon liegt in einem Flash.

### Zweige, falls S10 weiterhin hängt

| Zweig | Was | Warum | Risiko |
|---|---|---|---|
| **B0** | `--hold` zuerst laufen lassen (§5.2) | klärt, ob `0x0614A000` überhaupt hält - ohne das ist S8b wertlos | keins |
| **B1** | `--ihb-stock`: `0xd50` Gate aus → `:= 0x01000002` → Gate an (200 MHz aus `pll-periph0`) | `audio_ihb` = plausibler interner Bus der Insel, bei uns falscher Mux | gering, TVFE-seitig; danach S6-S8 wiederholen, um zu sehen, ob es die Insel stört |
| **B2** | `0xd84 := 0x80000001` (2400/2 = 1200 MHz) **oder** `:= 0x81000000` (`pll-periph0-2x`, 1200 MHz) | Stock fährt `hdmi_audio` mit 1152 MHz; 2400 MHz ist doppelt über Spezifikation | **Bild-Risiko** - `hdmi_audio_clk` gehört zu TVCAP. Nur mit Bildkontrolle davor/danach, `pll-video3` **nicht** anfassen (dokumentierter Freeze), sofort zurücksetzen |
| **B3** | `0x0614A004`/`0x0614A008` lesen (macht S5 schon), danach gezielt Bits `0…7` von `0x0614A000` einzeln setzen | im Stock nie benutzt - reine Suche | mittel, unbelegt; nur wenn B1/B2 nichts bringen |
| **B4** | `--no-router`: Lauf ohne `0x06700000 := 0x003003FF` | trennt Router von Audio-Top-Takt sauber (v6/v7 waren konfundiert) | keins |
| **B5** | wie Stock nach dem Takt: DSP `0x00EE` Maske `0x7F80 := 0x0180`, DSP `0x8034` Maske `0x90 := 0x10` über die Mailbox, danach S10 | letzte Stock-Schreibzugriffe vor dem ersten AUDIF-Zugriff | gering; Mailbox kann busy hängenbleiben (v7) - dann Neustart |

### Wenn S10 durchkommt

Direkt anschließen (S19 §10 hat das Capture-Rezept), aber **erst** die Fs-Probe als
Falsifikationstest: am Zuspieler zwischen 44,1 und 48 kHz umschalten (mit Modeset, sonst kommt kein
ELD - S16/F5) und `0x0614603C` (SPDI1_STATUS, Bits 1:0 = Sync-Zustand), `0x06146010` (SPDS_STATUS)
und `0x06146040` (Pc/Burstlänge) beobachten. Ändert sich dort nichts, kommt der HDMI-Ton nicht am
SPDI1 an - und das ist dann Frage **F2**, nicht mehr F1b.

---

## Erzeugte/berührte Dateien

| Datei | Was |
|---|---|
| `analyse/hdmi-seq/audif_probe.py` | **neu** - Rezept aus §6, ohne Argument rein lesend; `--hold` misst §5.2 |
| `analyse/ida/ida_a60.py` | libmspdriver: `Trid_Util_*`, MMIO-Konstantenscan `0x0614xxxx` |
| `analyse/ida/ida_a61.py` | MOVW/MOVT-Rekonstruktion, libmspsound + libmspdriver |
| `analyse/ida/ida_a62.py` | display.bin: `reset system_pd_audio_t` → `HdmiRx_Audio_PD_Reset` |
| `analyse/ida/ida_a63.py` | display.bin: vollständige `lui`-Karte `0xB500…0xBFFF` (Positivkontrolle) |
| `analyse/ida/ida_a64.py` | libmspsound: alle Aufrufer von `aud_read_reg`/`aud_write_reg`, Rohdisassembly `sound_lowlevel_init/_deinit` |
| `analyse/ida/db-audif-mips/display.bin.i64` | eigene Arbeitskopie (der F2-Agent benutzt `db-audio-mips/`) |
| `re/captures/weltneuheit/audio-audif-a6*-20260908.log` | Rohausgaben dazu |

Ausgewertet, nicht verändert: `re/captures/weltneuheit/s16-audio-20260908/audio-top-versuch*.log`,
`re/captures/weltneuheit/audio-{a4,a5,trid-a3}*-20260908.log`, `analyse/hdmi-seq/vendor-ccu-table.txt`,
`legacy/drivers/audio/bridge/`, `legacy/drivers/tvtop/sunxi_tvtop_data.c`,
`re/vendor/HY310/extracted/{vmlinux.elf,kallsyms.txt,boot_package.fex,bootpkg-full.dts}`,
`re/vendor/HY310-DEV/stock_audio_libs/`, `re/vendor/HY310-DEV/stock_modules/modules_full/snd_alsa_trid.ko`,
`re/ida/IDA_hy310/hidtvreg_dev.ko`, `re/notes/{AGENT_HANDOFF_AUDIO_MIPS_DSP,WORKLOG,RE_NOTES}.md`.

**Nebenbefund:** der Userspace erreicht `0x0614A000` nicht über `io-space-n` (dessen `reg`-Liste im
Stock-DTB deckt nur `0x6000000+0x20000`, `0x6100000+0x20000`, `0x6144000+0x1000`, `0x6500000` ab),
sondern über **`hidtvreg_dev.ko`** („HiDTV Register Access Driver", `re/ida/IDA_hy310/`) - ein
generischer `remap_pfn_range`-Treiber ohne Adressfilter. Für einen Mainline-Nachbau heißt das: es
gibt keine Vendor-Whitelist, an der man sich orientieren könnte.
