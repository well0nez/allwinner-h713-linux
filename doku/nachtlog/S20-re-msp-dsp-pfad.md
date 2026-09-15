# S20 - Stock-Weg HDMI-Audio → MSP-DSP → DAC (Frage F4)

**Agent D, 08.09.2026. Reine statische Analyse** (kein Board, kein Zuspieler, nichts unter `mainline/patches/`
oder `userspace/`). Quellen: `re/vendor/HY310-DEV/stock_audio_libs/*.so` (arm32), IDA-Arbeitskopien in
`analyse/ida/db-audio-msp/`, Skripte `analyse/ida/ida_a5*.py`, Rohausgaben
`re/captures/weltneuheit/audio-a5*-20260908.log`.

Konvention: **[B]** = belegt (Adresse + Fundstelle), **[V]** = vermutet/abgeleitet.

## Kurzfassung

1. **Quellwahl.** „Eingang = HDMI" ist im Stock genau ein Aufruf `Sound_Connect(0x89)` (HDMI-IN → Lautsprecher,
   PCM) bzw. `0x8F` / `0x0A`; die Kette läuft rein im ARM-Prozess bis `Sound_Path_Connect` und endet in
   maskierten Schreibzugriffen auf DSP-Register über die Mailbox `0x0614400C`. HDMI-Audio betritt den DSP als
   **I2S-Eingang** (`0x8034` Bit 4 = HDMI-Rx ein, `0x8017` Bit 0 = HDMI-Mute, `0x0012/0x0013` = I2SIN1).
2. **Minimalkette.** `0x0614A000 |= 0x700`, `0x0614A00C = 0x001A5E00` + Bit 24, DSP-Takt `0x00EE`,
   Firmware (724 Paare, Kontrolle `DSP1[0x80FF] != 0 && DSP2[0x80FF] != 0`), globales Enable `0x0002` Bit 15,
   HDMI-Rx ein, I2SIN/I2SOUT konfigurieren, Unmute, Codec `DAC_DPC` Bit 30+29. Klangmodule sind Kür.
3. **Extraktion.** `re/work/audio/patch_msp.bin` (2896 B - nicht 2892) + entpackte Fassung `patch_msp.txt`.
   `sound_preset.bin` und `libmsp_util.so` fehlen im Repo.
4. **Bypass.** Für den Lautsprecherweg **nein** (belegt); die einzigen DSP-freien Umschalter sind
   „APB statt MSP" für S/PDIF-Out und ARC.
5. **MIPS.** Nur Mutex-Partner (`0x02031078` / `0x02032078`) - Firmware und Programmierung macht der ARM.

## 0. Werkzeugstand und Lücken

- IDA-Arbeitskopien: `analyse/ida/db-audio-msp/{libmspsound,libmspdriver}.so.i64` (aus `db-audio-libs/` kopiert),
  dazu die fünf `.so` selbst. Hex-Rays arbeitet auf beiden.
- **[B] Fehlende Vendor-Dateien.** Zwei für den Stock-Pfad zentrale Artefakte liegen **nicht** im Repo:
  - `libmsp_util.so` - enthält die gesamte `BP_AUD_*`-Familie (Board-Profil-Zugriff:
    `BP_AUD_IsValidPath`, `BP_AUD_GetMuxDirector`, `BP_AUD_GetPathDirectorActionByIndex`,
    `BP_AUD_GetPathDeviceIndex`, `BP_AUD_GetYBinByIndicator`, `BP_AUD_GetGraph`, `BP_AUD_GetModule`, …).
    In `libmspsound.so` sind alle diese Symbole **UND** (`readelf -sW libmspsound.so | grep BP_AUD`),
    `DT_NEEDED` nennt `libmsp_util.so`.
  - `sound_preset.bin` - die Board-Profil-Datenbank, aus der `BP_AUD_*` Pfade, Mux-Director-Listen,
    Modul-Listen und die Y-Code-Blobs (`BP_AUD_GetYBin*`) zieht. `find . -iname 'sound_preset*'` findet nichts.
    Die März-Notiz (`re/notes/AGENT_HANDOFF_AUDIO_MIPS_DSP.md`) führt beide unter
    „Build-Server `/opt/captcha/kernel/stock_audio_libs_full/`" bzw. `/root/sound_preset.bin` auf dem Board.
  **Folge:** die konkreten Pfadnummern (z. B. `0x71`) lassen sich statisch **nicht** in Modul-/Mux-Listen
  auflösen. Alles unten zu „welche Module hängen an Pfad X" ist deshalb Struktur, nicht Inhalt.

- Kein Zugriff nötig auf Board/Zuspieler; alle Aussagen aus Dateien. IDA-Skripte
  `analyse/ida/ida_a50.py` … `ida_a57.py`, Logs `re/captures/weltneuheit/audio-a5*-20260908.log`.

| Skript | Log | Inhalt |
|---|---|---|
| `ida_a50.py` | `audio-a50-soundpath-20260908.log` | `libmspsound`: `Sound_Path_Connect/SetMux/Init`, `SlaveRoutine_Thal_Sound_*`, `sound_lowlevel_init`, `DelayLineTimeInit` |
| `ida_a51.py` | `audio-a51-hal-quellwahl-20260908.log` | `audio.primary.ares`: `connect_hdmiin_path`, `Sound_Connect`, `Get_Path`, Mute, Strings |
| `ida_a52.py` | `audio-a52-mspdriver-regs-20260908.log` | `libmspdriver`: Mailbox, `MAPI_*`, `func_*`, `ConnectPort` |
| `ida_a53.py` | `audio-a53-download-20260908.log` | `msp_download_sxl`, `SM_*`, Modul-Download SRS/AC |
| `ida_a54.py` | `audio-a54-halsound-20260908.log` | `libhalsound` vollständig (8 KB) |
| `ida_a55.py` | `audio-a55-hal-quellen-20260908.log` | Quellen-Enum, Aufrufer |
| `ida_a56.py` | `audio-a56-hal-setparams-20260908.log` | `adev_set_parameters`, `create_audio_patch` (Pfadtabelle!) |
| `ida_a57.py` | `audio-a57-modultabelle-20260908.log` | Modul-Tabelle `Init_Module_*`, `mod[]`, Portstruktur |

---

## 1. Quellwahl „Eingang = HDMI" im Stock-Audio-Stack

### 1.1 Die Kette von oben nach unten (alles im ARM-Prozess, **kein** cpu_comm)

```
tvserver (Quelle/Sink)                                    audio.primary.ares.so
  └─ create_audio_patch(dev, audio_source, audio_sink)     @0x00009F74
       └─ connect_hdmiin_path(dev)                         @0x00009630   (nur Quelle 1 = HDMI-IN)
            └─ Sound_Connect(path)                         @0x000110B4
                 ├─ DisconnectPath()                       @0x0000FC00
                 └─ Thal_Sound_Connect(path)               libhalsound.so @0x00001EE8
                      └─ SlaveRoutine_Thal_Sound_Connect() libmspsound.so @0x0000E27C
                           └─ Sound_Path_Connect(path)     libmspsound.so @0x00013ABC
                                ├─ BP_AUD_IsValidPath / GetMuxDirector / GetPathDirectorActionByIndex
                                ├─ SM_Check / SM_Set_Ex    (Mux-Buchführung, sound_mux.c)
                                │    └─ ConnectAll → ConnectPort  libmspdriver.so @0x0000EF9C
                                │         └─ tdAudioDSPWriteRegMaskWord(0, reg, mask, quelle<<shift)
                                └─ UpdateDevice / UpdateDeviceSourceModule (Lautstärke/Mute je Gerät)
```

**[B]** `Thal_Sound_Connect` ist ein dünner Wrapper mit optionaler Umschreibefunktion `pPathHelpRoutine`
(`Thal_Sound_InstallPathHelper`) und ruft direkt `SlaveRoutine_Thal_Sound_Connect` in `libmspsound.so` auf -
**kein RPC, kein `cpu_comm`, kein MIPS**. Belegt durch `readelf -sW`: weder `libmspsound.so` noch
`libmspdriver.so` noch `libhalsound.so` importieren eine `cpu_comm`-Funktion; der einzige Hardware-Zugriff
läuft über `Trid_Util_ReadRegWord` / `Trid_Util_WriteRegWord` (aus `libUtility.so`) auf die physischen
Adressen, die `TriHidtvRegMap` vorher eingeblendet hat.

### 1.2 Die Pfadnummern (das eigentliche „Eingang = HDMI")

**[B] `create_audio_patch(dev, src, sink)` @0x9F74** (`audio-a56-…log`, Zeilen ~1283 ff.):

| `audio_sink` | `audio_source` = 0 | **= 1 (HDMI-IN)** | = 2 (ATV) | = 3 |
|---|---|---|---|---|
| 0 | `Sound_Connect(0x71)` | `0x71` | `0x71` | `0x71` |
| 1 | `Sound_Connect(0x71)` | **`connect_hdmiin_path()`** | `Sound_Connect_ATV(port,1)` | Standby + `0x71` + Thread |
| 2 | `Sound_Connect(0x74)` | **`connect_hdmiin_path()`** + Thread | `Sound_Connect_ATV(port,2)` | `0x74` + Thread |
| 3 | `Sound_Connect(0x74)` | **`Sound_Connect(0x8F)`** | `Sound_Connect_ATV(port,3)` | `0x74` |

Jeder Aufruf endet in `set_audio_out_effect(dev)`; vorher `Sound_hdmirx_detect_enable(0)`.

**[B] `connect_hdmiin_path(dev)` @0x9630** wählt anhand zweier Gerätefelder:

| `dev[488]` (**[V]** Ausgangsmodus) | `dev[503]` (**[V]** HDMI-Eingangsformat) | Pfad |
|---|---|---|
| 0 | - | **kein Connect** (Log „passthrough") |
| 1 | ≤ 1 (PCM) | **`Sound_Connect(0x89)`** = 137 |
| 1 | > 1 (Bitstream) | **`Sound_Connect(0x0A)`** = 10 |
| 2 | ≤ 1 (PCM) | **`Sound_Connect(0x8F)`** = 143 |
| 2 | > 1 (Bitstream) | **`Sound_Connect(0x0A)`** = 10 |

Voraussetzung: `dev[489] == 1` (`SOURCE_HDMIIN`), sonst Abbruch mit
„hdmiin format is changed, but audio source is %d, not SOURCE_HDMIIN".
Danach `set_speaker_delay(dev[509], dev[511])`.

→ **Der gesuchte Wert für „HDMI-2-Ton auf den Lautsprecher" ist Pfad `0x89` (137).**
`0x71` (113) ist der Android-/OTT-Weg (ISTREAM → DSP → DAC), `0x74` (116) ein zweiter Ausgang,
`0x8F` (143) HDMI auf den zweiten Ausgang, `0x0A` (10) der Bitstream-Durchreichweg.
Die März-Notiz nennt `Sound_Path_Connect(0x71)` - das ist der **Playback**-Pfad, nicht der HDMI-Eingangspfad.

**[B]** Quellen-Enum: `get_current_input_source()` @0x9124 holt die Quelle über
`ITvServer::…` und bildet sie mit der Tabelle `dword_7CD8` = `{7,7,1,2,3,7,4,5,7,6,0,1}` ab
(Default 7). `portmap.cfg` (`vendor_a/etc/tvconfig/`) nummeriert HDMI1/2/3 = Port 1/2/3.

### 1.3 Was ein „Connect" auf der Hardware tut

**[B]** `ConnectPort(srcMod, srcPort, dstMod, dstPort)` @0x0000EF9C sucht im Modul-Array `mod[]`
(`libmspdriver.so` `.data` @0x00023968) den Ziel-Port (88 Byte je Port-Deskriptor: +4 = DSP-Register,
+8 = Maske, +12 = Port-ID, +16 = belegt-Flag, +20/+24 = aktuelle Quelle) und schreibt
`tdAudioDSPWriteRegMaskWord(0, reg, mask, quelle<<shift)`; Trennen schreibt Wert 0.
**Ein „Sound Path" ist also nichts anderes als eine Liste maskierter Schreibzugriffe in DSP-Register.**

### 1.4 HDMI-spezifische DSP-Register (die eigentliche Quellwahl)

**[B]**, alle über `tdAudioDSPWriteRegMaskWord(dsp_id=0, addr, mask, value)`:

| Funktion | Adresse (ARM) | DSP-Reg | Maske | Wert | Bedeutung |
|---|---|---|---|---|---|
| `MAPI_AUD_CFG_Enable_HDMI_Rx` | `libmspdriver` 0x0000E438 | **`0x8034`** | `0x90` | `0x10` | HDMI-Rx ein (Bit 4 setzen, Bit 7 löschen) |
| `MAPI_ADU_CFG_SetHDMIMuteForI2sIn` | 0x0000E45E | **`0x8017`** | `0x01` | 0/1 | HDMI-Stummschaltung am **I2S-Eingang** des DSP |
| `MAPI_ADU_CFG_SetDSPClockSpeed` | 0x0000E408 | **`0x00EE`** | `0x7F80` | `speed<<7` | DSP-Takt (gültig 2…8; Stock nutzt 3) |
| `func_set_i2s_input_config` (I2SIN1) | 0x00010F40 | **`0x0012`** | `0x23FF` | Format | I2S-In-1 Format (Bitbreite/Justierung/Polarität) |
| `func_enable_i2sin` (I2SIN1) | 0x00010F74 | **`0x0012`** | `0x8000` | 0/0xFFFF | I2S-In-1 **Enable** |
| `func_set_i2sin_prescaler` (I2SIN1) | 0x00010FA8 | **`0x0013`** | `0xFF00` | gain<<8 | Vorverstärkung I2S-In 1 |
| I2SIN2 analog | | `0x0014` / `0x0015` | | | |
| I2SIN3 analog | | `0x0016` / `0x0017` | | | |
| `func_set_i2s_output_config` | 0x00010FE6 | **`0x001E`, `0x001F`** | `0x7FFF`, `0xF93F` | | I2S-Out-1 Format |
| `func_enable_spdifrx` / `…_spdiftx` | 0x00011128 / 0x000111D6 | aus Modulstruktur | | | SPDIF-RX/TX |

**Modul-IDs** (aus `Init_Module_*`, `libmspdriver`): `I2SIN1 = 304 (0x130)`, `I2SIN2 = 305`, `I2SIN3 = 306`,
`I2SOUT1 = 368 (0x170)`; weitere Namen im Log `audio-a57-…`: `AUD_MODULE_SPDIF_RX1/2`, `SPDIF_TX1`,
`SPDIF_OUT1`, `LINEOUT1/2`, `MIXER1/2`, `MASTERVOLUME1/2`, `VOLUME1…12`, `DELAY1…4`, `DRC1…6`,
`PEQST1…3`, `PEQMO1/2`, `SRSHD4`, `SRS_TRUVOLUME`, `SURRDEC`, `SURRPOSTPRO`, `DTE1`, `AC_CALIBRATOR`,
`DTVOUT1`, `DECODER1…3`, `DEMOD1…4`, `ADC1`, `ANALOG1`, `BASSMGT`, `TONECONTROL1…3`, `VOICE`, `QPEAK`.

**[B] HDMI-Audio erreicht den DSP als I2S, nicht als S/PDIF.** Beleg: der Name und die Wirkung von
`MAPI_ADU_CFG_SetHDMIMuteForI2sIn` (DSP `0x8017` Bit 0) - die HDMI-Stummschaltung sitzt am I2S-Eingang -
zusammen mit `MAPI_AUD_CFG_Enable_HDMI_Rx` und der Tatsache, dass es im DSP-Modulkatalog **keinen**
HDMI-Modul­typ gibt, wohl aber `I2SIN1..3`. Die AUDIF-`SPDI1/2` sind die S/PDIF-Empfänger (ARC/optisch),
nicht der HDMI-Weg. **[V]** HDMI-2 hängt an `I2SIN1` (DSP-Reg `0x12/0x13`) - welcher der drei I2S-Eingänge
welchem HDMI-Port entspricht, steht in `sound_preset.bin` und ist statisch nicht auflösbar.

### 1.5 Datenfluss (Stand der Belege)

```
HDMI-RX (TVFE, MIPS-Domäne)
   │  I2S (Takt/Daten), HdmiRx_AEC_Enable + APLL aus N/CTS von der MIPS-Firmware
   ▼
MSP-Audio-DSP, Modul I2SIN1..3      DSP 0x8034 Bit4 = HDMI-Rx ein, 0x8017 Bit0 = HDMI-Mute
   │                                DSP 0x12 Bit15 = I2SIN1 ein, 0x12 Maske 0x23FF = Format
   ▼   (Graph: ConnectPort-Schreibzugriffe, Topologie aus sound_preset.bin)
Volume / PEQ / DRC / SRS / DTE / Delay …
   ├──► I2SOUT1 (DSP 0x1E/0x1F) ──► AUDIF ABPO1..3 (0x06146018/0x20/0x28 Takt, +0x1c/0x24/0x2c Format)
   │                                   └─► I2S-Pins ──► Codec 0x02031000 ──► DAC_DPC Bit30/29 ──► HP-Amp ──► Lautsprecher
   ├──► SPDIF_OUT/TX ──► AUDIF SPDO (0x0614606c…0x7c), OWA-Quelle 0x02000158[15:12]
   ├──► ARC-TX (Quelle 0x06E00020 Bit0)
   └──► OSTREAM-Ringe im AUDBRG (0x06148100 / 0x06148140) ──► DRAM ──► ARM (Capture)
ARM ──► ISTREAM-Ringe (0x06148280 ff.) ──► DSP  (Android-Playback, Pfad 0x71)
```

**[B]** Codec-Seite: Stock-DTB-Knoten des Codecs hat zwei Fenster `0x02030000/0x32c` (Codec) und
`0x02031000/0x7c` (I2S/daudio) mit `clock-names = "pll_audio","pll_tvfe","codec_dac","codec_adc","codec_bus"`,
`daudio_master = 1`, `audio_format = 3`, `tdm_config = 1`, `pcm_lrck_period = 0x20`, `slot_width_select = 0x20`,
`spk_used = 1`, `speaker_vol = 0x1a`, `gpio-spk`.
**[B]** `DAC_DPC` (`0x02030000`) Bit 30 = I2S-Quelle wählen, Bit 29 = I2S-Quelle einschalten, Bit 31 = DAC ein,
Bit 0 = Audio-Hub (`legacy/drivers/audio/snd-soc-sunxi-h713-codec.c`, Zeilen 85-92, 387-412).
Unser Port **löscht Bit 29 absichtlich** („Force APB path"), damit die CPU über die FIFO spielt.
Für den Stock-Weg muss Bit 29 **gesetzt** sein, dann kommt der DAC-Eingang vom I2S-Fenster.

### 1.6 Mute und Lautstärke bei Quellwechsel

**[B]** `Global_Sound_Mute(dev)` @0x94F4: `set_codec_speaker_mute(mixer, 0)` → `Sound_Set_Mute(Get_Path(), 1)`.
`Check_Sound_Unmute(dev)` @0x9490 hebt beides wieder auf, wenn `Audio_mute` und `Lock_mute` beide 0 sind.
`Sound_Set_Mute(path, mute)` @0x11634 baut eine `Thal_Sound_Set`-Struktur (Pfad, Attribut, Wert) -
bei `path == 0xFF` wartet es 100 ms und nimmt den aktuellen Pfad.
`Sound_hdmirx_detect_enable(en)` @0x1170C setzt Attribut `0x2201` (8705) auf 4 (ein) bzw. 5 (aus).
`Set_Path_In_Prescale(path, val)` @0x10520 setzt die Eingangsvorverstärkung (Ini-Schlüssel `hdmi_prescale = 32`).
Lautstärkekurve und Mode-Gains kommen aus `audio_config.ini`
(`re/vendor/HY310/extracted/vendor_a/etc/tvconfig/audio_config.ini`, Abschnitte `[HDMI2 AudioMode]`,
`[Volume]` mit `volume_curve[0..100]`, `[Prescale] hdmi_prescale = 32`, `[OutGain] speaker_gain = 26`).

---

## 2. Minimale Init-Kette „HDMI → DAC durchreichen"

### 2.1 Was Stock der Reihe nach tut (Belegkette)

`SlaveRoutine_Thal_Sound_Init(pProfile, x)` **libmspsound @0x0000DCCC**:

| # | Schritt | Adresse | Hardware? |
|---|---|---|---|
| 1 | `TriHidtvRegMap()` + `InitMSPRegisterAccess()` | libmspdriver 0x000192A8 | nur MMIO-Mapping + Semaphore `MSP Access` |
| 2 | **`sound_lowlevel_init()`** | libmspsound 0x0000DC04 | **ja, siehe 2.2** |
| 3 | `usleep(200000)` | | 200 ms |
| 4 | `SE_Init()` (Event-Thread `SoundEventThread`) | libmspsound 0x00010584 | nein |
| 5 | **`Sound_Path_Init(profil, len)`** | libmspsound 0x00012198 | **ja, siehe 2.3** |
| 6 | `Sound_UserData_Init`, `Sound_EQ_Init`, `Sound_PEQ_Init`, `Sound_DRC_Init`, `Sound_MelodBass_Init`, `Sound_Surround_Init`, `Sound_VolumeCurve_Init` | | Klangeffekte, **für reines Durchreichen entbehrlich** |

`Sound_Path_Init` @0x12198:
1. `BP_AUD_Init(profil, len)` - `sound_preset.bin` einlesen (aus `libmsp_util.so`)
2. **`msp_download_sxl()`** - DSP-Firmware (2.4)
3. Pfad-Bitmap `byte_21950` (0x400 Bit = Pfade 0…1023) nullen
4. **`MAPI_AUD_Initialization()`** = `Init_Modules()` + `InitAudioGroup()`; `Init_Modules` @0x000130E0 ist
   reine Software-Tabellenanlage und endet mit `Mute_All_Modules()` und
   **`tdAudioDSPWriteRegMaskWord(0, 0x0002, 0x8000, 0x8000)`** - *DSP-Register `0x0002` Bit 15 = globales Enable* **[B]**
5. `BP_AUD_GetGraph()` + `MAPI_AUD_CFG_SetDelayLineMode(0x8D00, 0x08910000, &r)` (`DelayLineTimeInit`, sound_path.c:471)
6. Schleife über `BP_AUD_GetActionByIndex()` → `BH_AUD_DoAction()` (Graph-Grundzustand aus dem Profil)

### 2.2 Pflicht: `sound_lowlevel_init()` - die einzigen direkten MMIO-Schreibzugriffe **[B]**

```
r = read32(0x0614A000);  write32(0x0614A000, r | 0x00000700);
r = read32(0x0614A00C);  write32(0x0614A00C, (r & 0xFF000000) | 0x001A5E00);
r = read32(0x0614A00C);  write32(0x0614A00C, r | 0x01000000);
MAPI_ADU_CFG_SetDSPClockSpeed(3)         -> DSP 0x00EE, Maske 0x7F80, Wert 0x0180
MAPI_AUD_CFG_Enable_HDMI_Rx()            -> DSP 0x8034, Maske 0x90,   Wert 0x10
MAPI_ADU_CFG_SetHDMIMuteForI2sIn(1)      -> DSP 0x8017, Maske 0x01,   Wert 0x01   (stumm während Init)
```

`0x0614A000` und `0x0614A00C` sind genau die Register, die unser Board bisher als 0 liest (Plan §1) -
`TRID_AUDIO_TOP_CLK_CTL` / `_CFG` im Legacy-Port. **Das ist der Einstiegspunkt: ohne diese beiden Schreibzugriffe
antwortet die DSP-Mailbox nicht.**

### 2.3 Pflicht: Mailbox-Protokoll **[B]**

| Adresse | Funktion |
|---|---|
| `0x06144000` | Status: Bit 4 = DSP1 Write busy, Bit 5 = DSP1 Read-Daten bereit, Bit 7 = DSP2 Write busy, Bit 8 = DSP2 Read-Daten bereit |
| `0x0614400C` | DSP1 Write: `(addr << 16) | value16`; mit Bit 31 gesetzt = 8-Bit-Schreiben |
| `0x06144010` | DSP1 Read: schreibe `addr << 16`, dann Bit 5 abwarten, Ergebnis in den unteren 16 Bit lesen |
| `0x06144014` | DSP2 Write (analog, Busy-Bit 7) |
| `0x06144018` | DSP2 Read (analog, Ready-Bit 8) |
| `0x02031078` | SW_REG1, ARM-Seite des Mutex: `0x55` = belegen, `0xAA` = freigeben |
| `0x02032078` | SW_REG2, MIPS-Seite des Mutex: `0x55` = MIPS hält |

`aud_dsp1_write_reg` @libmspdriver 0x0000CED8 baut den Wert mit `pkhbt r8, r1, r0, lsl #16`
(Rohdisassembly, Datei-Offset = VA − 0x1000) - **Hex-Rays zeigt die Adresse fälschlich nicht**, März hatte recht.
Timeout 0xC351 (= 50001 Zeiteinheiten OSA ≈ 5 s), danach wird trotzdem geschrieben.
`WaitDSPFree` @0x0001F0A5 (Thumb, also 0x1F0A4) + Freigabe `write32(0x02031078, 0xAA)` am Ende
jedes `tdAudioDSPWriteRegWord`/`…ReadRegWord`.

Adressraum-Verteilung in `tdAudioDSPWriteRegWord(dsp_id, addr, val)` @0x0001EE08 **[B]**:

| Adressbereich | Ziel |
|---|---|
| `0xFF00…0xFFFF` | DSP1, 16 Bit (`aud_dsp1_write_reg`) |
| `0xF000…0xFEFF`, Bit 8 = 0 | DSP1, 16 Bit |
| `0xF000…0xFEFF`, Bit 8 = 1 | DSP1, 8 Bit (`…_write_reg8`, Bit 31 im Mailbox-Wort) |
| `0xE000…0xEFFF` | DSP2 (16 Bit bei Bit 8 = 0, sonst 8 Bit) |
| `0x80FF` | DSP1 bei `dsp_id = 0`, DSP2 bei `dsp_id = 1` |
| `0x0000…0x7FFF` | `dsp_id = 0` → DSP1; `= 1` → DSP2; sonst Demodulator |
| `0x8000…0xFEFF` | 8-Bit-Variante |

### 2.4 Pflicht: `msp_download_sxl()` **[B]** - libmspsound @0x0000EF10

```
1  tdAudioDSPWriteRegWord(0, 0xFFF7, 0x0000)       // DSP-Reset
2  tdAudioDSPWriteRegWord(0, 0x0000, 0x0000)
3  usleep(200000)                                   // 200 ms  (0x30D40)
4  for (o = 0; o <= 0xB4C; o += 4) {                // 724 Paare, letzte Iteration o = 0xB4C
       usleep(1000);                                // 1 ms VOR jedem Paar (0x3E8)
       aud_dsp1_write_reg(BE16(patch_msp+o), BE16(patch_msp+o+2));
   }
5  tdAudioDSPReadRegWord(0, 0xFFF7, &a)             // gelesen, aber NICHT geprüft
   tdAudioDSPReadRegWord(0, 0x80FF, &b)             // DSP1
   tdAudioDSPReadRegWord(1, 0x80FF, &c)             // DSP2
   Fehler, wenn b == 0 ODER c == 0                  // -> "Download patch failed"
```

**Korrektur zur März-Notiz:** es sind **724 Paare / 2896 Byte**, nicht 723/2892 - das ELF-Symbol
`patch_msp` hat `st_size = 2896` (`readelf -sW libmspsound.so`), und die Schleife läuft einschließlich
`o = 0xB4C`. Die Erfolgskontrolle ist **`DSP1[0x80FF] != 0 && DSP2[0x80FF] != 0`**; `DSP[0xFFF7]` wird nur
gelesen und verworfen. Gesamtdauer ≥ 200 ms + 724 ms Wartezeit ≈ 1 s.

Danach optional die vier Klangmodule; jedes läuft nach demselben Muster (Beispiel `SRS_TSHD4`,
`sound_download.c:741 ff.`): `BP_AUD_GetYBinByIndicator("SRS_TSHD4", userdata, &ybin)` →
Kopfprüfung `*(ybin+20) >= 0x29` und `(size−40) % 4 == 0` → `MAPI_AUD_Init_SRSHD4_DownLoad(0x9C00, …)` →
`0xFFF7 = 0`, `0x0000 = 0`, **`0x4D53 = 0x504D` („MSPM")**, `0x0000 = 0x0100`, `0x0000 = 0x0400`,
`0xFFEF = (chan<<8)|(codeid<<12)`, dann die Paare ab `ybin+40`. AC-Kalibrator: Indikator
`"Acoustics_Calibrator"`, `MAPI_AUD_Init_AC_Calibrator_DownLoad(0x9D00, …)`, danach
`MAPI_AUD_SetAcousticsCalibratorBypassGain(0x9D00, 0x7FFF)` / `…ActiveGain(0x9D00, 0x7FFF)` /
`…State(0x9D00, 0)`. **Alle vier Module hängen an `sound_preset.bin` und sind für reines Durchreichen
nicht nötig** - sie sind EQ/Surround/Kalibrierung.

### 2.5 Vorschlag Minimalkette (Pflicht → Kür)

**Pflicht (alles [B] außer den mit [V] markierten Registern):**

| # | Schritt | Register / Wert | Kontrolle |
|---|---|---|---|
| 0 | Takte/Reset/Power des Audio-Top (Frage **F1**, Bericht S17) | CCU `0xd48/0xd4c/0xd50/0xd80` | `0x06144000`, `0x06146000`, `0x06148000`, `0x0614A000` lesen ≠ 0 |
| 1 | `0x0614A000 \|= 0x700` | | Rücklesen |
| 2 | `0x0614A00C = (alt & 0xFF000000) \| 0x001A5E00`, dann `\|= 0x01000000` | | Rücklesen |
| 3 | Mutex nehmen: warten bis `0x02032078 != 0x55`, `0x02031078 = 0x55` | | |
| 4 | DSP-Takt: `0x00EE` Maske `0x7F80` ← `0x0180` | | Rücklesen über 0x06144010 |
| 5 | **Firmware:** `0xFFF7=0`, `0x0000=0`, 200 ms, 724 Paare aus `patch_msp.bin` je 1 ms | | **`DSP1[0x80FF] != 0` und `DSP2[0x80FF] != 0`** |
| 6 | Globales Enable: `0x0002` Maske `0x8000` ← `0x8000` | | |
| 7 | HDMI-Rx: `0x8034` Maske `0x90` ← `0x10` | | |
| 8 | I2S-In (HDMI): `0x0012` Maske `0x23FF` ← Format, `0x0012` Bit 15 ← 1 | [V] Portzuordnung | |
| 9 | Graph: I2SIN1 → (Volume/Mixer) → I2SOUT1 verbinden | **[V]**, Register kommen aus den Port-Deskriptoren in `libmspdriver.data`, Topologie aus `sound_preset.bin` | |
| 10 | I2S-Out: `0x001E` Maske `0x7FFF`, `0x001F` Maske `0xF93F` | | |
| 11 | Unmute: `0x8017` Maske `0x01` ← 0; Modul-Mutes lösen (`tdEnableMute` @0x0001DD85) | | |
| 12 | Mutex freigeben: `0x02031078 = 0xAA` | | |
| 13 | Codec: `DAC_DPC` (0x02030000) Bit 31 ein, **Bit 30 und Bit 29 setzen**, Bit 0 (Hub), HP-Amp ein; I2S-Fenster `0x02031000` gemäß DT (`daudio_master=1`, `audio_format=3`, `slot_width=32`, `pcm_lrck_period=32`) | | Ton |

**Kür / entbehrlich:** `AC_Calibrator`, `SRS_TSHD4`, `STEREO_PEQ`, `DTE_Stereo`, `Sound_EQ/PEQ/DRC/
MelodBass/Surround/VolumeCurve_Init`, `SetDelayLineMode`, `Sound_UserData_Init` - alle brauchen
`sound_preset.bin`, keiner ist für den Signalweg nötig.

**Warnung zu Erfolgskontrollen [B]:** `func_get_i2sin_status` @0x00010F9A liest **nur ein Software-Feld**
(`*(modul+132)`), fragt also *keine* Hardware. Wer „HDMI-Audio erkannt" messen will, kann sich darauf
**nicht** stützen - dafür taugen nur die HDMI-RX-/AUDIF-Register (Frage F2/F3).

---

## 3. Extraktion

| Datei | Größe | SHA-256 | Herkunft |
|---|---|---|---|
| `re/work/audio/patch_msp.bin` | 2896 B | `8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5` | ELF-Symbol `patch_msp` (`st_value = 0x0000B644`, `st_size = 2896`, Sektion 12 = `.rodata`) aus `re/vendor/HY310-DEV/stock_audio_libs/libmspsound.so` (SHA-256 `61f3494…f237e8c4`). In `.rodata` ist `sh_addr == sh_offset`, also Datei-Offset = `0xB644`. |
| `re/work/audio/patch_msp.txt` | 719 Zeilen | - | Entpackte Klartextfassung derselben Daten (Blockstruktur + alle 724 Register-Paare), von uns erzeugt |

Beide Dateien liegen **unter `re/`**; außerhalb von `re/` wurden keine Vendor-Binärdaten abgelegt.

### 3.1 Aufbau von `patch_msp` (neu, vollständig verifiziert)

Der Blob ist **kein** flacher Strom von Register-Paaren, sondern eine Folge von **MSPM-Blöcken**.
Kopf (12 Byte, alles BE16-Paare, so wie sie in `0x0614400C` geschoben werden):

```
'M''S''P''M'   = Paar (0x4D53, 0x504D)   Magic
0x0000, 0x01TT                            TT = 0x00 -> DSP1, TT = 0x02 -> DSP2
0xHHHH, 0xLL00                            Nutzlast-Länge in Byte = (0xHHHH << 8) | 0xLL
```
Danach `len` Byte = `len/4` Paare `(BE16 DSP-Adresse, BE16 Wert)`.

Der Nachweis, dass die Deutung stimmt, kommt aus zwei unabhängigen Quellen: (a) die Blockkette
konsumiert **genau** 2896 Byte ohne Rest, (b) `msp_download_sxl` schreibt beim Modul-Download exakt
dieselben Kopfpaare von Hand (`tdAudioDSPWriteRegWord(0, 0x4D53, 0x504D)`, `(0, 0x0000, 0x0100)`,
`(0, 0x0000, 0x0400)` - Magic, DSP1, Länge 4).

| Block | Offset | Ziel | Länge | Paare | Inhalt |
|---|---|---|---|---|---|
| 0 | +0x0000 | DSP1 | 4 | 1 | `80FF = 0001` (Patch-OK-Flag DSP1) |
| 1 | +0x0010 | DSP2 | 4 | 1 | `80FF = 0001` (Patch-OK-Flag DSP2) |
| 2 | +0x0020 | DSP1 | 84 | 21 | `FFFF`-Bankwahl + `00CE/00CF/00D2/00D3/00D6/00D7 = 0070`, Ende `00FA=0000 FFFA=0000` |
| 3 | +0x0080 | DSP2 | 16 | 4 | `00D2/00D3 = 0010` |
| 4 | +0x009C | **DSP2** | 1128 | 282 | Codeblock, beginnt `FFF9 = A4ED` |
| 5 | +0x0510 | **DSP1** | 1416 | 354 | Codeblock, beginnt `FFF9 = 4CF5` |
| 6 | +0x0AA4 | DSP2 | 92 | 23 | Nachkonfiguration |
| 7 | +0x0B0C | DSP1 | 56 | 14 | Nachkonfiguration, Ende `00FC = 21FF`, `0001 = 0C19` |

Damit ist auch klar, **warum** die Erfolgskontrolle `0x80FF` auf *beiden* DSPs prüft: Block 0 und 1 setzen
genau dieses Flag, je einmal pro Kern. Der eigentliche DSP-Code steckt in den Blöcken 4 (DSP2, 1128 B)
und 5 (DSP1, 1416 B); `FFF9` ist offenbar das Ladeadress-/Bankregister.

### 3.2 `sound_preset.bin` - **nicht vorhanden** [B]

`find . -iname 'sound_preset*'` findet im ganzen Repo nichts, ebenso wenig `libmsp_util.so`.
Alle `BP_AUD_*`-Symbole sind in `libmspsound.so` **UND**; `DT_NEEDED` verweist auf `libmsp_util.so`.
`find re/vendor/HY310/extracted/vendor_a/etc -iname '*audio*' -o -iname '*sound*'` liefert nur
`tvconfig/audio_config.ini` (Lautstärkekurve, Mode-Gains, PEQ/DRC/AVC/Prescale je Quelle - HDMI1/2/3
eigene Abschnitte) und `tvconfig/portmap.cfg` (HDMI1/2/3 = Port 1/2/3).

**Was ohne diese beiden Dateien fehlt:** die Zuordnung Pfadnummer → Modul-/Mux-Liste (also der Inhalt
von Pfad `0x89`), die YBin-Blobs der vier Klangmodule, und die Zuordnung „HDMI-Port → I2SIN1/2/3".
**Was trotzdem da ist:** sämtliche Modul-Deskriptoren mit ihren DSP-Registern sind in `libmspdriver.so`
**einkompiliert** (`Init_Module_*`, `mod[]` @`.data 0x00023968`) - die Registeradressen für Format,
Enable, Prescaler, Mute und Lautstärke jedes Moduls lassen sich also auch ohne `sound_preset.bin`
rekonstruieren; nur die *Verdrahtung* fehlt.

**Empfehlung:** `sound_preset.bin` und `libmsp_util.so` vom Stock-Android nachziehen
(März-Notiz: `/root/sound_preset.bin` auf dem Board, `/opt/captcha/kernel/stock_audio_libs_full/`
auf dem Build-Server, `/vendor/lib/` unter Stock). Ohne sie bleibt Stufe 2 auf Reverse-Engineering
der Verdrahtung per Registerdump angewiesen.

---

## 4. Gibt es einen DSP-losen Bypass?

**Kurz: für den Lautsprecherweg nein - belegt. Für den Capture-Ring: sehr wahrscheinlich auch nein,
aber das ist die eine Stelle, die ein Messkriterium braucht.**

### 4.1 Was belegt ist

1. **[B] Die einzigen Quellumschalter im Bridge/AUDIF, die den DSP umgehen können, sind
   „APB" statt „MSP" - und nur für S/PDIF-Ausgang und ARC:**
   - `TRID_ARC_SRC = 0x06E00020`, Bit 0: `0` = **APB**, `1` = **MSP**
     (`legacy/drivers/audio/bridge/audio_bridge_pcm.c`, `trid_arc_source_texts[] = {"APB","MSP"}`,
     `trid_arc_source_put`).
   - `TRID_MSP_OWA_OUT_SRC = 0x02000158`, Bits 15…12: `0x0000` = NULL, `0x2000` = **APB**,
     `0x6000` = **MSP** (`trid_msp_owa_out_texts[] = {"NULL","APB","MSP"}`, `trid_msp_owa_out_put`).
   In **beiden** Muxen gibt es genau zwei Quellen: den DSP oder die CPU. **Es gibt keine Stellung
   „HDMI-RX/SPDI direkt".** Für den I2S-Ausgang zum Codec (ABPO) existiert überhaupt kein solcher Mux.

2. **[B] Die AUDIF-„DATA"-Register transportieren keine Audiodaten.**
   `ABPO1/2/3_DATA` (`0x0614601C/0x24/0x2C`) nehmen im IRQ ein **Formatwort** entgegen
   (`trid_i2so_irq_channel`: `s->data_word = s->frames[next_rd].format & 0xFFFF`), `SPDI1/2_DATA`
   (`0x06146040/0x50`) liefern im IRQ das **Präambel-/Kanalstatuswort**, das anschließend nach
   `SPDIx_CFG` zurückgeschrieben wird (`trid_spdi_run_channel`, Zustände sync_lost/sync_found/data_ready).
   Ein „SPDI-DATA lesen → ABPO-DATA schreiben" wäre also **keine** Audiokopie.

3. **[B] Der AUDBRG ist die Speicherbrücke des DSP, nicht ein eigener Datenpfad.**
   `trid_ostream_config` (`audio_bridge_if.c:957`) programmiert nur Ring-Geometrie
   (`START/END/STEP/CFG` mit `cfg = (ch<<8) | (breite<<11)`), `STREAM_SYNC` (`0x06148390`) und die IRQ-Maske -
   **es gibt kein Quellen-Auswahlfeld**. Die Zuordnung „OSTREAM0 ↔ SPDI1, OSTREAM1 ↔ SPDI2"
   in `trid_capture_iface` ist eine Treiberkonvention des Legacy-Ports, kein Registerbit.

4. **[B] Der DSP ist im Stock-Graph die einzige Kreuzschiene.** Alle Modul-zu-Modul-Verbindungen
   entstehen ausschließlich durch `ConnectPort` → maskierte DSP-Registerschreibzugriffe; der
   Modulkatalog enthält Quellen (`I2SIN1..3`, `SPDIF_RX1/2`, `ADC1`, `DEMOD*`, `DECODER*`) und Senken
   (`I2SOUT1`, `SPDIF_OUT1/TX1`, `LINEOUT1/2`, `DTVOUT1`), aber **keinen Bypass-Modultyp**.

### 4.2 Was daraus folgt

- **HDMI → I2SO/ABPO → Codec ohne DSP: klar verneint.** Der einzige Weg vom HDMI-I2S-Eingang zum
  I2S-Ausgang führt durch den MSP (`I2SIN1 → … → I2SOUT1`), und beide Enden werden über
  DSP-Register (`0x12/0x13` bzw. `0x1E/0x1F`) geschaltet.
- **HDMI → OSTREAM (Capture) ohne DSP: [V] sehr wahrscheinlich ebenfalls nein.** Die Argumente:
  der AUDBRG heißt „Bridge" und hängt am `audio_umac`-Takt (`ISTREAM_UMACREQ` @`+0x298`); die
  Gegenrichtung ISTREAM ist nachweislich DSP-getrieben (März: HW-Pointer bewegt sich 16 Byte und
  bleibt stehen, solange der DSP nicht läuft); und `AUD_MODULE_DTVOUT1` im DSP-Katalog ist genau der
  Modultyp, der einen Strom zum Applikationsprozessor ausleitet.
- **Konsequenz für Stufe 1 des Plans (doku/100 §2):** die Annahme „OSTREAM-Ring füllt sich, sobald
  AUDIF/AUDBRG laufen" ist **nicht belegt** und sollte früh geprüft werden, bevor der Treiber
  `sun50i-h713-audbrg` darauf aufbaut.

### 4.3 Das Messkriterium, das scheitern kann

Nach dem Einschaltrezept aus F1, bei laufendem HDMI-Ton, **ohne** jede DSP-Programmierung:
`OSTREAM0_PTR` (`0x06148108`) bzw. `OSTREAM1_PTR` (`0x06148148`) mehrfach lesen.
*Bewegt sich der Zeiger* → es gibt einen DSP-losen Capture-Weg, Stufe 1 trägt.
*Bleibt er stehen* → auch Capture braucht den DSP, und Stufe 1 muss um die Minimalkette aus §2.5
Schritte 1-7 erweitert werden (Firmware laden, globales Enable, HDMI-Rx ein - aber ohne Graph und
ohne Module). Positivkontrolle: derselbe Test mit vorher geladener Firmware.

---

## 5. Rolle der MIPS-Displayfirmware für den Audio-DSP

1. **[B] Für die DSP-Programmierung selbst: nur Mutex-Partner.** Weder `libmspsound.so` noch
   `libmspdriver.so` noch `libhalsound.so` importieren eine `cpu_comm`-Funktion
   (`readelf -sW … | grep -i cpu_comm` ist leer); der einzige Hardwarezugriff läuft über
   `Trid_Util_Read/WriteRegWord`. Die MIPS-Seite erscheint ausschließlich als zweiter Halter des
   Software-Mutex `0x02031078` (ARM) / `0x02032078` (MIPS): ARM wartet, bis `0x02032078 != 0x55`,
   schreibt `0x55` nach `0x02031078`, arbeitet, schreibt `0xAA`. **Der MSP-DSP ist ein eigener
   Coprozessor neben der MIPS-Display-CPU, kein Teil von ihr.**
2. **[B] Das Laden der DSP-Firmware macht die ARM-Seite**, Byte für Byte über die Mailbox
   `0x0614400C` - `patch_msp` liegt in einer ARM-Userspace-Bibliothek, nicht in `display.bin`.
3. **[V] Der „MIPS App Ready"-Blocker von März war ein Mutex-/Verfügbarkeitsproblem, kein
   Firmware-Ladeproblem.** Wenn der MIPS hängt oder `0x02032078` auf `0x55` stehen bleibt, blockiert
   `WaitDSPFree` und alle DSP-Schreibzugriffe laufen in ihr 5-s-Timeout. Da unsere MIPS-App
   inzwischen läuft (cpu_comm 4/4, RPCs, Rückrufe - doku/97), entfällt dieser Blocker.
4. **[B, aus doku/100 §1] Für den HDMI-Zulauf bleibt die MIPS-Firmware zuständig:**
   `THDMIRx_TV303_Audio_Driver.cpp` in `display.bin` rechnet die APLL aus N/CTS, schaltet
   `HdmiRx_AEC_Enable` und die ARC-Pfade. Der DSP sieht davon nur „I2S kommt an" - das ist die
   Schnittstelle zwischen F2 (MIPS) und F4 (DSP).

---

## 6. Offene Punkte

| # | Punkt | Wer |
|---|---|---|
| 1 | `sound_preset.bin` und `libmsp_util.so` fehlen im Repo - ohne sie ist Pfad `0x89` nicht in Modul-/Mux-Listen auflösbar | Beschaffung (Stock-Android `/vendor/`, Build-Server, Board `/root/`) |
| 2 | Welcher der drei I2S-Eingänge (`0x12/0x14/0x16`) hängt an HDMI-2? | Registerdump unter Stock oder `sound_preset.bin` |
| 3 | Bewegt sich `OSTREAM_PTR` ohne DSP? (Kriterium §4.3) - entscheidet über Stufe 1 des Plans | A0/F3 |
| 4 | Die Port-Deskriptoren in `libmspdriver.data` (z. B. `I2SIN1_CPOUT` @0x000265AC, Schrittweite 88, Feld +4 = DSP-Register, +8 = Maske, +12 = Port-ID) systematisch auslesen - damit ließe sich die Verdrahtung auch ohne Profil nachbauen | Folgeauftrag RE |
| 5 | `0x0614A00C = 0x001A5E00` und `0x0614A000 |= 0x700` - Bedeutung der Felder (Teiler? PLL-Wahl?), Abgleich mit dem CCU-Befund aus F1/S17 | S17 + Board |
| 6 | `MAPI_AUD_CFG_SetDelayLineMode(0x8D00, 0x08910000)`: Modul-ID `0x8D00` und Moduswort `0x08910000` sind noch unentschlüsselt | niedrige Priorität |
| 7 | Codec-Seite: unser Port löscht `DAC_DPC` Bit 29 („Force APB path"). Für den Stock-Weg muss Bit 29 gesetzt und das I2S-Fenster `0x02031000` konfiguriert werden - Wechselwirkung mit cstengers Patches `0082` - `0086` prüfen | A3 |
