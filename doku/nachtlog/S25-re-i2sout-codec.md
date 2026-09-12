# S25 — Von I2SOUT1 zum Codec-DAC: die fehlenden Registerwerte (Auftrag F7)

**08.09.2026. Reine statische Analyse — kein Board.** **[B]** belegt, **[V]** abgeleitet, **[offen]**.
Quellen: Stock-Kernel `re/vendor/HY310/extracted/vmlinux.elf` (ARM32, 5.4, **volle Symbole + DWARF**, CU
`.../longan/kernel/linux-5.4/sound/soc/sunxi/sun50iw12-codec.c`), `snd_alsa_trid.ko`, `libmspdriver.so`.
IDA-Kopien `analyse/ida/db-audio-f7/`, Skripte `analyse/audio/arbeit/f7-i2sout-codec/ida_f7_*.py`,
Dekompilate `re/captures/weltneuheit/audio-f7-01…10-*.log`.

## Kurzfassung

1. **Registernamen beider Codec-Fenster belegt** (`codec_reg_labels` @`0xc149cfac`, `i2s_reg_labels`
   @`0xc149ce98`). Komplette I2S-Fensterfolge (`sunxi_codec_i2s_init` @`0xc0845230`, 21 Schreibzugriffe) und
   `DAC Src Select = I2S` (`sunxi_codec_set_dacsrc_mode` @`0xc0844fbc`): §1/§2/§4. **Das Codec-I2S ist
   Takt-MASTER und empfängt** (`CTL` Bit 1 = RXEN, Bits 18:17 = 0) — DSP-`I2SOUT1` ist Slave.
2. `DAC_DPC` (`0x02030000`): **Bit 31 = DAC_EN**, **Bit 29 = Quelle (1 = I2S, 0 = APB)**, **Bit 30 = Beipack
   zu 29**, **Bit 0 = Audio-Hub-Ausgang** (§3). **Unser Port macht die I2S-Seite bereits vollständig**
   (Patch `0050`, „Fix D"); es fehlt genau **eine** Schreibung: `0x02030000` Bit 29 setzen statt löschen (§5).
3. **Korrektur zu S23 §6.2:** `ABPO1` ist **nicht** die Senke von `I2SOUT1`, sondern der AUDIF-I2S-**Sender**
   des AUDBRG-ISTREAM (ARM-Wiedergabe); `0x06146008` = Fehlerstatus, nicht Kanalfreigabe; `0x0614601C[15:0]`
   = Rahmenlänge, kein Formatwort. §6
4. **Frage 3 verneint [B]:** kein Quellenfeld im OSTREAM; OSTREAM0/1 fest an SPDI1/2. §7
5. **Frage 4 verneint [B]:** `MAPI_AUD_GetI2SInputStatus` liest ein Software-Flag; echte Messung über
   **QPEAK** (DSP `0x00B2/0x00B3`) bzw. die SPDIF-RX-Statusregister. §8

## 1. Registernamen beider Fenster [B]

Debug-Tabellen des Stock-Treibers (`{name, offset, wert}`, 12 B je Eintrag).
`codec_reg_labels` @`0xc149cfac`, Basis **`0x02030000`**: `000 DAC_DPC`, `004 DAC_VOL_CTRL`, `010 DAC_FIFOC`,
`014 DAC_FIFOS`, `024 DAC_CNT`, `028 DAC_DG`, `030 ADC_FIFOC`, `034 ADC_VOL_CTRL`, `038 ADC_FIFOS`, `044
ADC_CNT`, `04c ADC_DG`, `0f0 DAC_DAP_CTL`, `0f8 ADC_DAP_CTL`, `300 ADCL_REG`, `304 ADCR_REG`, `310 DAC_REG`,
`318 MICBIAS_REG`, `320 BIAS_REG`, `324 HP_REG`, `328 HMIC_CTRL`, `32c HMIC_STS`.
`i2s_reg_labels` @`0xc149ce98`, Basis **`0x02031000`**, Präfix `INTER_I2S_`: `00 CTL`, `04 FMT0`, `08 FMT1`,
`24 CLKDIV`, `30 CHCFG`, `34/38/3c/40 TX0..3CHSEL`, `44…60 TXnCHMAP0/1`, `64 RXCHSEL`, `68…74 RXCHMAP0..3`.
`sunxi_i2s_regmap_config` @`0xc0ee8a54`: `max_register = 0x7c` — **identische Registerkarte wie `sunxi-daudio`**;
damit liefern `sunxi_daudio_init` @`0xc08424d0`, `_set_fmt` @`0xc08420a8`, `_set_clkdiv` @`0xc0842334`,
`_hw_params` @`0xc0842c00`, `_rxctrl_enable` @`0xc0841eac` die Felder:

`CTL[0]` GEN · `CTL[1]` **RXEN** · `CTL[5:4]` MODE_SEL (0 = PCM/DSP, **1 = I2S/Left-J**, 2 = Right-J) ·
`CTL[18:17]` Taktrichtung (**0 = Master**, 3 = Slave; `set_fmt`: `CBM_CFM → 0x60000`) · `FMT0[2:0]` Slotbreite
`(slot_width/4)−1` · `FMT0[6:4]` Auflösung `(bits/4)−1` · `FMT0[7]`/`[19]` BCLK-/LRCK-Polarität ·
`FMT0[17:8]` `pcm_lrck_period−1` · `FMT0[30]` `frame_type` · `FMT1[1:0]/[3:2]` tx-/rx_data_mode · `FMT1[5:4]`
`sign_extend` · `FMT1[6]/[7]` `msb_lsb_first` · `CLKDIV[3:0]` MCLK-, `CLKDIV[7:4]` BCLK-Teiler (Codes 1→1,
2→2, 3→4, **4→6**, 5→8, 6→12, 7→16, **8→24**, 9→32, 10→48, 11→64, 12→96, 13→128, 14→176, 15→192) ·
`CLKDIV[8]` MCLK-Ausgang · `CHCFG[3:0]/[7:4]` TX-/RX-Slotzahl−1 · `TXnCHSEL[19:16]`, `RXCHSEL[19:16]`
Kanalzahl−1, `[21:20]` Offset · `TX0CHSEL[15:0]` Slotmaske.

## 2. `sunxi_codec_i2s_init` @`0xc0845230` — Fenster `0x02031000`, 21 Schreibzugriffe [B]

Wird von `sunxi_codec_probe` @`0xc0846498` **nach** `sunxi_codec_init` aufgerufen. Reihenfolge exakt so;
**keine Wartezeiten**. Format „Adresse | Maske | Wert" (Read-Modify-Write, außer wo „=" steht).

```
 1  0x02031000 CTL        0x00000001  0x00000001   GEN ein
 2  0x02031004 FMT0       0x40000000  0            frame_type = 0
 3  0x02031004 FMT0       0x0003FF00  0x00001F00   LRCK-Periode = 32
 4  0x02031004 FMT0       0x00000007  0x00000005   Slotbreite = 24 bit
 5  0x02031024 CLKDIV     0x0000000F  0x00000004   MCLK-Teiler Code 4 = /6
 6  0x02031024 CLKDIV     0x00000100  0x00000100   MCLK-Ausgang ein
 7  0x02031000 CTL        0x00000030  0x00000010   MODE_SEL = I2S
 8  0x02031004 FMT0       0x00080000  0x00080000   LRCK-Polaritaet invertiert
 9  0x02031004 FMT0       0x00000080  0            BCLK-Polaritaet normal
10  0x02031024 CLKDIV     0x000000F0  0x00000080   BCLK-Teiler Code 8 = /24
11  0x02031008 FMT1       0x00000040  0            msb_first TX
12  0x02031008 FMT1       0x00000080  0            msb_first RX
13  0x02031008 FMT1       0x00000030  0x00000030   sign_extend = 3
14  0x02031004 FMT0       0x00000070  0x00000050   Aufloesung = 24 bit
15  0x02031074 RXCHMAP3   (Direktschreibung)       = 0x00000100
16  0x02031064 RXCHSEL    0x000F0000  0x00010000   RX-Kanaele = 2
17  0x02031030 CHCFG      0x000000F0  0x00000010   RX-Slots = 2
18  0x02031048 TX0CHMAP1  (Direktschreibung)       = 0x00003210
19  0x02031034 TX0CHSEL   0x000F0000  0x00010000   TX-Kanaele = 2
20  0x02031030 CHCFG      0x0000000F  0x00000001   TX-Slots = 2
21  0x02031034 TX0CHSEL   0x0000FFFF  0x00000003   TX-Slots 0+1 frei
```

**Der Codec-Treiber liest die DT-Werte `audio_format`, `daudio_master`, `pcm_lrck_period`, `slot_width_select`,
`tdm_config`, `mclk_div`, `frametype`, `signal_inversion` NICHT** — `sunxi_internal_codec_probe` @`0xc0846544`
liest nur `digital_vol`, `speaker_vol`, `headphone_vol`, `spk_used`, `pa_level`, `pa_msleep_time`,
`dac/adc*_used`, `dac_swap_en`, `adc_swap_en`, `gpio-spk` [B]. Abweichung zum DT: Slotbreite 24 statt 32,
MCLK ÷6 statt ÷4.

**[offen] Taktrechnung.** LRCK-Periode 32 × BCLK-Teiler 24 × 48 kHz = **36,864 MHz** Modultakt.
`sunxi_codec_set_sysclk` @`0xc0845f44` setzt für 48 kHz aber `pll_audio = 98 304 000`, `codec_dac = 24 576 000`
(`sunxi_card_hw_params` @`0xc0847880`: 44,1-kHz-Familie → 22 579 200, sonst 24 576 000) und wird auf dem
I2S-Weg **gar nicht** aufgerufen; mit 24,576 MHz käme LRCK = 32 kHz heraus → **am Gerät messen**.

## 3. `DAC_DPC` (`0x02030000`) — Bits 31/30/29/0 [B]

**Bit 31** `DAC_EN`, globale DAC-Freigabe (`sunxi_codec_dac_route_enable` @`0xc0844868`: Maske `0x80000000`
← `enable<<31`) · **Bit 30** Beipack zur I2S-Quelle, wird beim Zurückschalten auf APB **nicht** gelöscht ·
**Bit 29 = DAC-Quellenwahl, 1 = I2S, 0 = APB** (`sunxi_codec_get_dacsrc_mode` @`0xc08457b0` liefert
`(DAC_DPC>>29)&1`; Enum `sunxi_codec_or_i2s_select` @`0xc0ee8f7c` = {`APB`,`I2S`}) · **Bits [17:12]**
digitale Lautstärke · **Bit 0** `HUB_EN`, Kontrolle „Audio Hub Output" (`sunxi_codec_set/get_hub_mode`
@`0xc08450c8`/`0xc0845828`).
Reihenfolge im Stock: erst Bit 31 (in `sunxi_codec_init` über `dac_route_enable`), dann beim Mixer-Pfad
Bit 30, dann Bit 29. Bit 0 rührt kein Stock-Pfad an (bleibt 0). `dac_route_enable` löscht dabei
`DAC_FIFOC[31:29] = 0` = Ratenklasse 44,1/48 kHz (`sample_rate_conv` @`0xc0ee7da4`: 48000 → 0).

## 4. Fertige Schreibfolgen für „DAC bekommt sein PCM vom I2S"

### 4.0 Einschalten (`sunxi_internal_codec_probe`, CCU-Ebene) [B]
`RST_BUS_AUDIO_CODEC` freigeben → `codec_dac`/`codec_adc` auf Elter `pll_audio` → `pll_audio = 98 304 000`,
`pll_tvfe = 1 296 000 000` → einschalten in der Reihenfolge `codec_bus`, `pll_audio`, `pll_tvfe`, `codec_dac`,
`codec_adc` (für 48 kHz zusätzlich `codec_dac = 24 576 000` wie `set_sysclk` — §2 offen).

### 4.1 `sunxi_codec_init` @`0xc084494c` — Fenster `0x02030000`, in dieser Reihenfolge [B]
```
0x02030004 DAC_VOL_CTRL  maske 0x00010000 wert 0x00010000
0x02030030 ADC_FIFOC     maske 0x00020000 wert 0x00020000
0x02030030 ADC_FIFOC     maske 0x0E000000 wert 0x0E000000
0x02030000 DAC_DPC       maske 0x0003F000 wert digital_vol<<12      # Stock-DTB 0x00 → 0
0x02030310 DAC_REG       maske 0x0000001F wert speaker_vol          # DTB 0x1A
0x02030310 DAC_REG       maske 0x70000000 wert headphone_vol<<28    # DTB 0
0x02030300 ADCL_REG      maske 0x000000FF wert 0x00000055
0x02030304 ADCR_REG      maske 0x000000FF wert 0x00000055
0x02030324 HP_REG        maske 0x000000C0 wert 0x00000080
0x02030310 DAC_REG       maske 0x00000040 wert 0x00000040
0x02030310 DAC_REG       maske 0x00000020 wert 0x00000020
0x02030000 DAC_DPC       maske 0x80000000 wert 0x80000000           # DAC_EN
0x02030010 DAC_FIFOC     maske 0xE0000000 wert 0                    # Ratenfeld = 0 (48 kHz)
0x02030010 DAC_FIFOC     maske 0x00000020 wert 0
0x02030010 DAC_FIFOC     maske 0x00000040 wert 0
0x02030310 DAC_REG       maske 0x00008000 wert 0x00008000
0x02030310 DAC_REG       maske 0x00004000 wert 0x00004000
0x02030310 DAC_REG       maske 0x00001000 wert 0x00001000
0x02030310 DAC_REG       maske 0x00000400 wert 0x00000400
0x02030324 HP_REG        maske 0x00000008 wert 0x00000008
0x02030324 HP_REG        maske 0x00000300 wert 0x00000300
0x02030310 DAC_REG       maske 0x08000000 wert 0x08000000
0x02030310 DAC_REG       maske 0x03000000 wert 0x03000000
```
(optional `dac_swap_en` → `0x02030028` Maske `0x40`, `adc_swap_en` → `0x0203004C` Maske `0x01000000`.) Danach
die 21 Zeilen aus §2 (Fenster `0x02031000`).

### 4.2 Mixer-Pfad `media-speaker-i2s`, Reihenfolge aus `audio_mixer_paths.xml` [B]
```
# ctl "DAC Src Select" = I2S   (sunxi_codec_set_dacsrc_mode @0xc0844fbc, Zweig val==1)
0x02031000 INTER_I2S_CTL maske 0x00020000 wert 0            # BCLK als Ausgang (Master)
0x02031000 INTER_I2S_CTL maske 0x00040000 wert 0            # LRCK als Ausgang (Master)
0x02031000 INTER_I2S_CTL maske 0x00000002 wert 0x00000002   # RXEN
0x02030000 DAC_DPC       maske 0x40000000 wert 0x40000000   # Bit 30
0x02030000 DAC_DPC       maske 0x20000000 wert 0x20000000   # Bit 29 = Quelle I2S
# ctl "Speaker" = On           (sunxi_codec_set_spk_status @0xc0845b14)
0x02030310 DAC_REG       maske 0x00002000 wert 0x00002000
0x02030310 DAC_REG       maske 0x00000800 wert 0x00000800
   msleep(pa_msleep_time = 160)                             # nur wenn spk_used
   gpio_direction_output(PL2, 1); gpio_set_value(PL2, pa_level = 1)
# ctl "Headphone" = On         (sunxi_codec_set_hp_status @0xc0844c78)
0x02030324 HP_REG        maske 0x00000800 wert 0x00000800
0x02030324 HP_REG        maske 0x00000400 wert 0x00000400
0x02030324 HP_REG        maske 0x00008000 wert 0x00008000
```
Zurück auf APB: **nur** `0x02030000` Maske `0x20000000` ← 0 (Bit 30 bleibt stehen) [B]. Ausschalten von
Speaker/Headphone: dieselben Bits auf 0 (Speaker: erst GPIO auf `!pa_level`, `msleep`, dann `0x2000`, `0x800`).

## 5. Was unser Port schon kann, und was fehlt [B]

`mainline/patches/kernel/0050-asoc-sunxi-add-the-h713-internal-audio-codec.patch` enthält
`sunxi_codec_i2s_init` bereits **Schreibung für Schreibung identisch** (21 Zeilen) und unter „Fix D" auch die
drei `INTER_I2S_CTL`-Bits. Es fehlt genau eine Änderung: `regmap_update_bits(regmap, SUNXI_DAC_DPC,
DAC_SRC_I2S_EN, 0)` („Force APB path") muss entfallen bzw. `DAC_SRC_I2S_EN` setzen. Vier Kommentare im Port
sind falsch benannt: `I2S_CTL_TXGE BIT(1)` ist **RXEN**; „`FMT0` mode [2:0] = 5" ist die **Slotbreite** (24 bit);
„`CLKDIV` slot width [3:0] = 4" ist der **MCLK-Teiler** (÷6); „`CTL` TX enable [5:4]" ist **MODE_SEL = I2S**.

## 6. Frage 2 — `ABPO1`: Korrektur zu S23 §6.2

**`ABPO1/2/3` sind die I2S-Ausgänge des AUDIF, gespeist vom AUDBRG-ISTREAM (ARM-Wiedergabe aus DRAM) — nicht
die Senke des DSP-`I2SOUT1`** [B, `snd_alsa_trid.ko`]: `Trid_Audio_Output_Istream_Open` @`0x6bec` holt
`AudIf_GetHandle_abpo1/2/3` **und** `AudIf_GetHandle_istream`; `audbrg_istream_start` @`0x3558` setzt
`handle[21] = AudIf_GetHandle_abpo(n)`; `audbrg_istream_get_audif_info` @`0x3760` bindet ISTREAM 0–2 an
`AudIf_i2so_*`, ISTREAM 3 an `AudIf_spdo_*`; `AudIf_i2so_Interrupt` @`0x45a8` meldet „I2S1 output buffer
underrun" / „SCC input stream 1 data overflow" — der AUDIF **sendet** I2S und **holt** aus der Bridge.
**[V]** Quelle des Stock-Lautsprecherwegs ist folglich `I2SOUT1` (Preset-Gerät `SPEAKER`, S23 §4), `ABPO1`
speist den DSP (`DECODER3` → `MIXER2`). **[offen]** mangels Registerbeleg — am Gerät entscheidbar: über
`ABPO1` ohne DSP-Graph einen Ton senden; kommt er am Lautsprecher an, war die Annahme falsch.

Die abgefragte ABPO1-Folge trotzdem vollständig [B, `AudIf_i2so_*`]:
```
# Open (AudIf_i2so_Open @0x435c)
0x06146000 = 0x00040000              # IRQ-Status W1C (ABPO1; ABPO2 0x20000, ABPO3 0x10000)
0x06146008 = 0x00000003              # SCC-Fehlerstatus W1C (ABPO1 Bits 1:0; ABPO2 0xC, ABPO3 0x30)
0x06146004 = read(0x06146004) | 0x00040000     # IRQ-Freigabe
# activate (AudIf_i2so_activate @0x48d8) — je Frame
0x0614601C = 0xC0000000 | ((cfg & 0x0F) << 16) | rahmenlaenge16
0x06146018 = 0x1A5E0000              # AudIf_i2so_setFs: round(324e6/48000)=6750 im 8.8-Format, <<8
# jeder Folgeframe im IRQ (AudIf_i2so_Interrupt): Bit 30 gelöscht
0x0614601C = 0x80000000 | ((cfg & 0x0F) << 16) | rahmenlaenge16
# Close (AudIf_i2so_Close @0x43fc)
0x06146018 = 0 ; 0x0614601C = wert_ohne_Bit31 ; 0x06146004 &= ~0x00040000
```
**Korrekturen zu S23 §6.2:** (a) `0x06146008` ist **keine Kanalfreigabe**, sondern SCC-Fehlerstatus (W1C,
je Kanal 2 Bits Underflow/Overflow) — belegt in `AudIf_i2so_Interrupt`. (b) `0x0614601C[15:0]` ist **kein
Formatwort, sondern die Rahmenlänge in Samples**: `Thal_Alsa_Audio_Play_Start` @`0x82a8` übergibt
`AlsaHandle+44` = **512**, `AlsaHandle+40` = Fs. Stock-Wort 48 kHz/2 Kanäle: **`0xC0000200`**, Folgeframes
`0x80000200`; Bit 31 = gültig, Bit 30 = erster Rahmen, Bit 20 = Pause, Bits 19:16 = `cfg & 0xF` (ALSA: 0).
**Statusbits in `0x06146000`** [B, `Handle_AudIf_ISR_interrupt` @`0x62b0`, Maske `0x77000`]: Bit **18** =
ABPO1-Rahmen verbraucht, Bit 17 = ABPO2, Bit 16 = ABPO3; Bit 14/13/12 = SCC-Fehler Stream 1/2/3.

## 7. Frage 3 — AUDBRG-OSTREAM mit ABPO1/I2SOUT1 als Quelle? **Nein [B]**

`audbrg_ostream_config` @`0x3be0` schreibt genau `START`, `END`, `STEP`, `CFG` (+ `0x06142044`-Nibble,
`0x06148390 = 0`); `CFG = (mode<<12) | (breite<<11) | (bps<<8) | (schwelle>>4)` — **kein Quellenfeld**,
`mode` auf 0…2 begrenzt. `Trid_Audio_Output_Ostream_Open` @`0x6fa0` lehnt Index > 1 ab und bindet **fest**
`idx 0 → AudIf_GetHandle_spdi1`, `idx 1 → AudIf_GetHandle_spdi2`; `AudIf_i2so_*`-Handles kommen im
OSTREAM-Pfad nirgends vor. **Ein digitaler Abgriff des DSP-Ausgangs über den AUDBRG ist im Stock-Register-
modell nicht vorgesehen.** Der DSP-Katalog kennt `AUD_MODULE_DTVOUT1` (`0x9500`, Preset-Gerät `ABP_DTV`,
8 Eingänge/0 Ausgänge, `Init_Module_Dtvout` @`0x174b0`) als Weg „DSP → Applikationsprozessor", aber
`snd_alsa_trid.ko` implementiert dafür keinen Kanal. **[offen]**

## 8. Frage 4 — DSP-seitige Eingangsanzeige

**`MAPI_AUD_GetI2SInputStatus` @`0x19e90` taugt nicht** [B]: sie ruft `mod+144` = `func_get_i2sin_status`
@`0x10f9a` = `{ if (mod) *out = *(_DWORD *)(mod + 132); return 0; }`. `mod+132` setzt ausschließlich
`func_enable_i2sin` @`0x10f74` (`a1[33] = (a2 != 0)`) — ein **Software-Flag „Schnittstelle eingeschaltet"**,
kein DSP-Lesezugriff, kein Fs, kein Lock. `I2SOUT1` (`Init_Module_I2SOUT` @`0x17ef8`) hat nur Mute-Flag-Getter.
Modulfelder I2SIN (`Init_Module_I2SIN` @`0x17600`) [B]: I2SIN1 Konfig/Freigabe **`0x0012`** (Masken `0x23FF`
bzw. `0x8000`), Vorverstärkung **`0x0013`** Maske `0xFF00` Schiebung 8; I2SIN2 `0x0014`/`0x0015`;
I2SIN3 `0x0016`/`0x0017` — bestätigt S23 §4.3.

**Was statt dessen wirklich messbar ist:**

1. **QPEAK — der Pegelmesser des DSP [B].** `Init_Module_Qpeak` @`0x181b8`: `AUD_MODULE_QPEAK`, Index 176,
   **Handle `0x8E00`**, 2 Eingänge; Ports `IN[0] reg 0x80B2 maske 0xFFFF`, `IN[1] reg 0x80B3 maske 0xFFFF`
   (Log `audio-graph-a85`). `func_get_qpeak` @`0x123b0` liest `tdAudioDSPReadRegWord(0, 0x00B2)` und
   `(0, 0x00B3)` (`mod+104`/`mod+108`). **Messrezept** nach dem Graphaufbau: `DSP 0x80B2 maske 0xFFFF wert
   0x0016` und `DSP 0x80B3 maske 0xFFFF wert 0x0017` (= `I2SIN1.out0/out1 → QPEAK.in0/in1`), dann zyklisch
   `DSP 0x00B2`/`0x00B3` lesen. Werte ≠ 0 und schwankend = **PCM kommt an I2SIN1 an**. Mit den Quellcodes aus
   S23 §4.2 an jedem Punkt der Kette einsetzbar (`DELAY1.out0 = 0x2E`); `Mute_All_Modules` nullt sie vorher.
2. **SPDIF-RX-Status [B]** (`func_get_spdif_input_status` @`0x1104c`, Deskriptor `Init_Module_SPDIF_RX`
   @`0x17990`): echte DSP-Lesungen. `SPDIF_RX1` (`0x9700`): Status `0x8006`/`0xFF`, `0x0007`/`0xFFFF`
   (Bits 7…0 = Kategorie), `0x8007`/`0xFF`; Freigabe+Quelle `0x0004` (Freigabe `0x8000`, Quelle `0x7000` <<12,
   Konfig `0x10`), Vorverstärkung `0x0005`/`0xFF00`/8. `SPDIF_RX2` (`0x9701`, Preset `HDMI5`): Status `0x800A`,
   `0x000B`, `0x800B`; Freigabe/Quelle `0x0008`; Vorverstärkung `0x0009`. Bitbedeutungen **[offen]**.
3. Alle übrigen echten DSP-Lesewege (Xrefs in `audio-f7-07`): Firmware-Versionen, Download-Status, Demod,
   SIF, Master-Volume/Control, Surround-Modus, SRS — **keiner zeigt I2S-Eingangsaktivität.**

## 9. Dateien

IDA-Kopien `analyse/ida/db-audio-f7/` (`vmlinux.elf.i64`, `libmspdriver.so.i64`, `snd_alsa_trid.ko`); Skripte
`analyse/audio/arbeit/f7-i2sout-codec/ida_f7_{vmlinux,daudio,trid,trid2,msp,msp2,msp3,msp4,msp5,msp6}.py`;
Dekompilate `re/captures/weltneuheit/audio-f7-{01-vmlinux-codec, 02-trid-abpo, 03-vmlinux-daudio,
04-trid-playback, 05-msp-i2sin, 06-msp-status, 07-msp-lesewege, 08-msp-spdifrx, 09-msp-spdifcfg, 10-msp-qpeak}.log`.

## 10. Offene Punkte

1. **Modultakt des `INTER_I2S`** — die festen Teiler verlangen für 48 kHz 36,864 MHz, `codec_dac` steht auf
   24,576 MHz; am Gerät prüfen (§2), sonst falsche Tonhöhe.
2. **Physische Verdrahtung `I2SOUT1 → INTER_I2S`** ist [V], nicht [B] (§6).
3. `INTER_I2S_RXCHMAP3 = 0x100` (Feldaufteilung unbekannt, Wert übernehmen); `DAC_DPC` Bit 30 (wird gesetzt,
   nie gelöscht); Bitbedeutungen der SPDIF-RX-Statusregister.
