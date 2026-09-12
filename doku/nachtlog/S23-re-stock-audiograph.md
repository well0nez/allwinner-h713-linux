# S23 — Der Stock-Audiograph „HDMI → Lautsprecher" als Registerliste (Auftrag F5)

**08.09.2026. Reine statische Analyse** — kein Board, kein Zuspieler, nichts unter `mainline/` oder `userspace/`.
Konvention: **[B]** = belegt (Datei + Adresse), **[V]** = abgeleitet/vermutet.

Quellen: `re/work/audio/stock/` (neu beschafft, siehe §1), IDA-Arbeitskopien `analyse/ida/db-audio-mspu/`
(neu) und `db-audio-msp/`, `db-audio-trid/` (vorhanden), Skripte `analyse/ida/ida_a80.py` … `ida_a8a.py`,
Auswerter `re/work/audio/parse_sound_preset.py` und `re/work/audio/derive_path_regs.py`,
Rohausgaben `re/captures/weltneuheit/audio-graph-a8*-20260908.log`.

## Kurzfassung

1. **`sound_preset.bin` (60480 B) und `libmsp_util.so` (14452 B) sind gefunden** — in `super.fex`,
   Partition `vendor_a`, als `/vendor/etc/sound_preset.bin` und `/vendor/lib/libmsp_util.so`.
   Damit entfällt der Hauptvorbehalt aus S20 §3.2/§6.1.
2. **Das Format von `sound_preset.bin` ist vollständig entschlüsselt** (Chunks `TRID_AUD`/`DPST`/`GRAF`/
   `DCDR`/`PHDR`/`MSPD`/`USRD`), ebenso die Aktions­tabelle `gActionTable` (69 Einträge, Aktions-ID → `MAPI_AUD_*`).
3. **Pfad `0x89` heißt `HDMI2PCM_MIXED_TO_SPEAKER`**, Gerät 3 = `SPEAKER` = Modul `0x9A00` = `AUD_MODULE_I2SOUT1`.
   **HDMI-Audio kommt auf `AUD_MODULE_I2SIN1` (`0x9600`) an** — DSP `0x0012/0x0013`, Quellcodes `0x16`/`0x17`.
   Damit ist S20-Offenpunkt 2 („welcher der drei I2S-Eingänge?") beantwortet.
4. Die vollständige Registerliste steht in §4 (Durchreichen) und §5 (Klangbearbeitung).
   Der **kürzere Stock-Pfad `0xC1` `HDMI2PCM_TO_SPEAKER`** (ohne Surround/Mixer) braucht nur vier
   Verbindungs­schreibzugriffe und ist die natürliche Minimalkette.
5. **`MSPD` enthält 0 YBIN-Blobs** — SRS/AC-Kalibrator/PEQ3/DTE werden auf diesem Board gar nicht geladen.
   `msp_download_sxl` lädt also nur `patch_msp`; die „Kür" aus S20 §2.4 fällt ersatzlos weg.
6. I2SOUT1-Format: `DSP[0x001E] = 0xA440`, `DSP[0x001F] = 0x3000`; AUDIF-ABPO1: `0x06146018` Taktteiler,
   `0x0614601C` Formatwort, Freigabe­bits `0x3` in `0x06146008`, IRQ-Bit `0x40000` in `0x06146000/04`.

---

## 1. Beschaffung [B]

`super.fex` (`re/vendor/HY310/extracted/`, 1 612 279 680 B) ist ein **Android-Sparse-Image**
(Magic `0xed26ff3a`, Blockgröße 4096, 524288 Blöcke = 2 GiB roh, 4964 Chunks). Entsparst (eigener
Python-Parser, kein `simg2img` nötig) und über die **LP-Metadaten** (Geometrie `gDla` @0x1000,
Header `ALP0` @0x3000, v10.2) zerlegt:

| Partition | Typ | Offset | Größe | FS |
|---|---|---|---|---|
| `system_a` | LINEAR | 1048576 | 980652032 | ext4 |
| `vendor_a` | LINEAR | 982515712 | 114372608 | ext4 |
| `product_a` | LINEAR | 1097859072 | 538517504 | ext4 |

(`*_b` haben 0 Extents.) `vendor_a` mit `dd` ausgekoppelt, Dateien mit `debugfs -R "dump …"`
(e2fsprogs 1.47.0) gezogen — **kein `sudo`, kein `mount`, kein Loop-Device**.

Abgelegt in `re/work/audio/stock/` mit `HERKUNFT.txt` (Image, Pfad, SHA-256):

| Datei | Pfad im Image | Größe | SHA-256 (Anfang) |
|---|---|---|---|
| `sound_preset.bin` | `/vendor/etc/sound_preset.bin` | 60480 | `babda009…e59604` |
| `libmsp_util.so` | `/vendor/lib/libmsp_util.so` | 14452 | `e949a32d…071e447` |
| `libmspsound.so` | `/vendor/lib/libmspsound.so` | 126128 | `61f34944…f237e8c4` |
| `libmspdriver.so` | `/vendor/lib/libmspdriver.so` | 134540 | `a03e6344…98ce88ea` |
| `libhalsound.so` | `/vendor/lib/libhalsound.so` | 8312 | `3bc63326…4f66d96c` |
| `audio_mixer_paths.xml` | `/vendor/etc/` | 1348 | `d10d7689…a0dd9640` |
| `audio_platform_info.xml` | `/vendor/etc/` | 13986 | `9441a23e…20c13896` |
| `audio_policy_configuration.xml` | `/vendor/etc/` | 12358 | `3253294c…3487f90d9` |

Die drei `.so` sind **byteidentisch** mit `re/vendor/HY310-DEV/stock_audio_libs/` — gleiche Build,
alle bisherigen S20-Adressen gelten unverändert. Weitere im selben Image, falls je gebraucht:
`/vendor/lib/hw/audio.primary.ares.so`, `/vendor/etc/tvconfig/{audio_config.ini,portmap.cfg}`.

**`audio_mixer_paths.xml` bestätigt S20 §1.5 [B]:** es gibt genau zwei Lautsprecherwege,
`media-speaker-apb` (`DAC Src Select = APB`, unser Weg) und `media-speaker-i2s`
(`DAC Src Select = I2S`, der Stock-DSP-Weg). Für Stufe 2 muss der Codec auf **I2S** stehen.

> Hinweis: Die IDA-Arbeitskopie von `libmsp_util.so` liegt auftragsgemäß unter
> `analyse/ida/db-audio-mspu/` — also außerhalb von `re/`. Das ist dieselbe Praxis wie bei
> `db-audio-msp/`; wenn die Regel „keine Vendor-Binärdaten außerhalb `re/`" strenger gemeint ist,
> genügt ein `rm` dort, der Auswerter arbeitet auf `re/work/audio/stock/`.

---

## 2. Format von `sound_preset.bin` [B] (aus `libmsp_util.so`, `BP_AUD_Init` @0x2D0C)

Kopf (Datei­anfang):

| Offset | Inhalt |
|---|---|
| +0 | `"TRID_AUD"` |
| +8 | Voll-Version, hier `"UXL\0"` (`BP_AUD_GetFullVersion`) |
| +12 | Preset-Version = 2 (`BP_AUD_GetPresetVersion`) |
| +16 | Gesamtgröße (wird gegen `len` geprüft) = 60480 |
| +20 | Offset `DPST` = `0x0034` — Modul-Depot |
| +24 | Offset `GRAF` = `0x0D6C` — Graph (Mux + Grundzustand) |
| +28 | Offset `DCDR` = `0x2900` — Geräte („Device Director") |
| +32 | Offset `PHDR` = `0x2A5C` — Pfadtabelle |
| +36 | Offset `MSPD` = `0xA07C` — YBIN-Blobs der Klangmodule |
| +40 | Offset `USRD` = `0xA088` — Nutzerdaten (EQ-Presets …) |

Chunk-Bauart durchgehend: `magic(4) | size(4) | count… | Offsettabelle | Nutzdaten`,
alle Offsets **relativ zum Chunk-Anfang**.

| Chunk | Aufbau | Inhalt dieser Datei |
|---|---|---|
| `DPST` | `+8/+12/+16` = drei Zählwerte, `+20` = Offsettabelle über deren Summe | 62 `MODU` |
| `MODU` | `+8` ID, `+12` Klasse (27), `+16` nIn, `+20` nOut, `+24` nAktionen, dann In-, Out-Port-IDs, dann Aktions-IDs | — |
| `GRAF` | `+12` Anzahl `MUX`, `+16` Offset `PRST`, `+20` Offsettabelle | 7 MUX |
| `MUX` | `+4` Name(20), `+28` Mux-ID, `+32/36` nIn/Offset, `+40/44` nOut/Offset; Ports je **32 B**: Name(16), `+16` Port-ID, `+20` Verbindungstyp, `+24` Modul-ID, `+28` Modul-Port | — |
| `PRST` | `+8/+12` Anzahl/Offset **Connects** (je 20 B), `+16/+20` Anzahl/Offsettabelle **Aktionen** | 48 Connects, 77 Aktionen |
| Connect | `[0]` Typ, `[1]` Quellmodul, `[2]` Quellport, `[3]` Zielmodul, `[4]` Zielport | — |
| Aktion | `[0]` Phase (0 = vor den Mux-Schaltungen, 1 = danach), `[1]` Funktions-ID, `[2]` Argumentzahl, `[3…]` Argumente | — |
| `DCDR` | `+8` Anzahl, `+12` Offsettabelle | 6 `DVCE` |
| `DVCE` | `+4` Name(16), `+20` Größe, `+24` n, dann n × `(Modul, Port, Flag)` | `HEADPHONE 0x9B00`, `SCART1 0x9200`, `SCART2 0x9201`, **`SPEAKER 0x9A00`**, `SPDIF 0x9800`, `ABP_DTV 0x9500` |
| `PHDR` | `+8` Anzahl, `+12` Offsettabelle | **210 `PATH`** |
| `PATH` | `+4` Name(20), `+24` Größe, `+28` **Pfad-ID**, `+32` Geräteindex, `+36/40` Anzahl/Offset **Mux-Direktoren** (je 12 B: Mux-ID, **In-ID**, **Out-ID**), `+44/48` Anzahl/Offsettabelle **Pfad-Aktionen** | — |
| `MSPD` | `+8` Anzahl `YBIN` | **0** |
| `USRD` | `+8` Anzahl `DATA`, `DATA`: `+4` Name, `+44` Knotenzahl, Knoten `+36` ID/`+44` Wert | 12 (`GEQ_5Band_Setting` …) |

**Aktionstabelle** `gActionTable` (`libmsp_util.so` `.data.rel.ro` @0x4A34, 69 × 12 B:
`{ID, Signatur, Funktionszeiger}`) + Indextabelle `.rodata` @0x193C (Gruppe = ID>>8).
Die Signatur ist eine Nibble-Kette; ihre Summe muss der Argumentzahl im Preset entsprechen
(`BH_AUD_DoAction` @0x2B0C). Vollständig in `audio-graph-a81-aktionstabelle-20260908.log`.

**Verbindungen** (`BH_AUD_DoConnect` @0x2C30): `[0]` Typ (0 = `MAPI_AUD_SetSourceSelect`,
1 = `MAPI_AUD_SetSourceSelectPort`), `[1]/[2]` Quelle Modul/Port, `[3]/[4]` Ziel Modul/Port;
beim Trennen wird die Quelle durch **`0x8300` = `AUD_MODULE_NONE`** ersetzt.

---

## 3. Wie aus einem Connect ein Registerschreibzugriff wird [B]

`MAPI_AUD_SetSourceSelectPort(idZiel, portZiel, idQuelle, portQuelle)` (`libmspdriver` @0xF3B8)
→ `ConnectPort(idxQuelle, portQuelle, idxZiel, portZiel)` @0xEF9C.

**Handle → Index:** `CalculateModuleID(h) = (h & 0xF) + (h >> 4) − 2096` (@0x19278);
Umkehrung `Anti_CalculateModuleID(i) = (i & 0xF) + ((16·i − 32000) & 0xFF00)` (@0x19330).
Beispiele: `0x9600 → 304 = I2SIN1`, `0x9A00 → 368 = I2SOUT1`, `0x8F01 → 193 = MIXER2`,
`0x8D00 → 160 = DELAY1`, `0x8700 → 64 = DRC1`, `0x8300 → 0 = NONE`.
Die Tabelle `mod[]` liegt in `libmspdriver .data @0x23968` und wird **mit dem Index adressiert**.

**Moduldeskriptor:** `+0` ID, `+4` Basistyp, `+8` Name (`AUD_MODULE_*`), `+72` nIn, `+76` nOut,
`+80` Zeiger auf Eingangsports (**28 B je Eintrag**), `+84` Zeiger auf Ausgangsports (**88 B je Eintrag**).
Eingangsport: `+4` **DSP-Register**, `+8` **Maske**, `+12` Port-ID, `+16` belegt, `+20/+24` aktuelle Quelle.
Ausgangsport: `+4` **Quellcode**, `+8` Codemaske, `+12` Port-ID.

**Der eigentliche Schreibzugriff** (`ConnectPort`, Ende):
```
wert  = Quellcode & Codemaske
shift = Anzahl der Null-Bits unterhalb des niedrigsten gesetzten Bits der Zielmaske
tdAudioDSPWriteRegMaskWord(0, Zielregister, Zielmaske, wert << shift)
Trennen:  … , 0)
```
`tdAudioDSPWriteRegMaskWord` @0x1F010: bei **gesetztem Bit 15 der Adresse und Maske `0xFF`/`0xFFFF`**
wird **direkt** geschrieben (kein Read-Modify-Write), sonst gelesen, maskiert, geschrieben.
Adressen mit Bit 15 (`0x8052`, `0x8100`, …) laufen über den 8-Bit-Pfad der Mailbox
(`tdAudioDSPWriteRegWord`, Bit 31 im Mailbox-Wort, S20 §2.3). **[V]** Sie adressieren einen
**eigenen Byte-Registerraum**, nicht dasselbe Wort wie die gleichnamige 16-Bit-Adresse. Zwei
unabhängige Kollisionen sprechen dafür: Mixer-Quellwahl (`0x8100`, Maske `0xFF`) gegen
Mixer-Verstärkung Ausgang 1 (`0x0100`, Maske `0x00FF`), und Volume1-Quellwahl (`0x8052`, Maske
`0xFF`) gegen Volume1-Pegel (`0x0052`, Maske `0xFFC0`, Bits 15…6). Wären es dieselben Register,
zerstörte jede Quellwahl den Pegel.

**Reihenfolge in `Sound_Path_Init`** (`libmspsound` @0x12198) [B]:
`BP_AUD_Init` → `msp_download_sxl` → `MAPI_AUD_Initialization` (= `Init_Modules`, endet mit
**`Mute_All_Modules`**: `ConnectPort(0, p, m, p)` für **jeden** Eingangsport jedes Moduls, d. h. alle
Verbindungsregister auf 0, dann `DSP[0x0002] |= 0x8000`) → `BP_AUD_GetGraph` →
`MAPI_AUD_CFG_SetDelayLineMode(0x8D00, 0x08910000)` → **Aktionen Phase 0** → **48 PRST-Connects** →
`SM_Init`/`SD_Init` → **Aktionen Phase 1**.

**Reihenfolge in `Sound_Path_Connect(0x89)`** (@0x13ABC) [B]: `BP_AUD_IsValidPath` → `SM_Check` je
Direktor → Pfad-Aktionen Phase 0 → `SM_Set_Ex` je Direktor (→ `ConnectAll` → `ConnectPort`) →
Pfadbit setzen → Pfad-Aktionen Phase 1 → `UpdateDevice`/`UpdateDeviceSourceModule`.
`TraceMuxInToModule` (@0x1115C) löst Mux-an-Mux-Kaskaden bis zum echten Modul auf; deshalb ergibt der
Direktor `MUX_GAME in0 → out0` (Ziel ist selbst ein Mux) **keinen** eigenen Schreibzugriff, sondern
wirkt erst über `MUX_SOURCE`.

---

## 4. Pfad `0x89` — die Registerliste „nötig für Durchreichen"

**Pfad `0x89` = `HDMI2PCM_MIXED_TO_SPEAKER`**, Gerät 3 (`SPEAKER` = `I2SOUT1`), 8 Mux-Direktoren, 0 eigene Aktionen.
Erzeugt mit `re/work/audio/derive_path_regs.py`, Rohausgabe
`re/captures/weltneuheit/audio-graph-a87-pfad89-register-20260908.log`.

### 4.1 Signalweg (Endzustand nach `Sound_Path_Init` + `Sound_Path_Connect(0x89)`)

```
I2SIN1 0x9600 (HDMI)  →  SURRDEC 0x8400  →  SURRPOSTPRO 0x8500  →  MIXER2 0x8F01
   →  DRC1/DRC2 0x8700/0x8701  →  TONECONTROL1 0x8900  →  PEQST2 0x8B01  →  PEQST1 0x8B00
   →  VOLUME1/VOLUME2 0x9002/0x9003  →  DELAY1 0x8D00  →  I2SOUT1 0x9A00  → Codec-I2S
```

### 4.2 Verbindungsregister, in Ausführungsreihenfolge

Alle über `tdAudioDSPWriteRegMaskWord(0, Reg, Maske, Wert)`.
„PRST" = 48 feste Connects aus `Sound_Path_Init`; „0x89" = Mux-Direktoren des Pfades.

| # | Quelle | → Ziel | DSP-Reg | Maske | Wert | Herkunft |
|---|---|---|---|---|---|---|
| 1 | `SURRDEC.out0` (0x80) | `SURRPOSTPRO.in0` | `0x007C` | `0xFF00` | `0x8000` | PRST C34 |
| 2 | `SURRDEC.out1` (0x81) | `SURRPOSTPRO.in1` | `0x007C` | `0x00FF` | `0x0081` | PRST C35 |
| 3 | `SURRDEC.out2` (0x82) | `SURRPOSTPRO.in2` | `0x007D` | `0xFF00` | `0x8200` | PRST C36 |
| 4 | `SURRDEC.out3` (0x83) | `SURRPOSTPRO.in3` | `0x007D` | `0x00FF` | `0x0083` | PRST C37 |
| 5 | `SURRDEC.out4` (0x84) | `SURRPOSTPRO.in4` | `0x007E` | `0xFF00` | `0x8400` | PRST C38 |
| 6 | `SURRDEC.out5` (0x85) | `SURRPOSTPRO.in5` | `0x007E` | `0x00FF` | `0x0085` | PRST C39 |
| 7 | `SURRPOSTPRO.out0` (0x86) | `MIXER2.in2` | `0x8102` | `0x00FF` | `0x0086` | PRST C8 |
| 8 | `SURRPOSTPRO.out1` (0x87) | `MIXER2.in3` | `0x8103` | `0x00FF` | `0x0087` | PRST C9 |
| 9 | `DECODER3.out0` (0x4A) | `MIXER2.in0` | `0x8100` | `0x00FF` | `0x004A` | PRST C6 |
| 10 | `DECODER3.out1` (0x4B) | `MIXER2.in1` | `0x8101` | `0x00FF` | `0x004B` | PRST C7 |
| 11 | `DRC1.out0` (0x92) | `TONECONTROL1.in0` | `0x8062` | `0x00FF` | `0x0092` | PRST C40 |
| 12 | `DRC2.out0` (0x93) | `TONECONTROL1.in1` | `0x8063` | `0x00FF` | `0x0093` | PRST C41 |
| 13 | `TONECONTROL1.out0` (0x72) | `PEQST2.in0` | `0x0096` | `0xFF00` | `0x7200` | PRST C42 |
| 14 | `TONECONTROL1.out1` (0x73) | `PEQST2.in1` | `0x0096` | `0x00FF` | `0x0073` | PRST C43 |
| 15 | `PEQST2.out0` (0x9A) | `PEQST1.in0` | `0x0090` | `0xFF00` | `0x9A00` | PRST C44 |
| 16 | `PEQST2.out1` (0x9B) | `PEQST1.in1` | `0x0090` | `0x00FF` | `0x009B` | PRST C45 |
| 17 | `PEQST1.out0` (0x98) | `VOLUME1.in0` | `0x8052` | `0x00FF` | `0x0098` | PRST C46 |
| 18 | `PEQST1.out1` (0x99) | `VOLUME2.in0` | `0x8053` | `0x00FF` | `0x0099` | PRST C47 |
| 19 | `VOLUME1.out0` (0x62) | `DELAY1.in0` | `0x0036` | `0xFF00` | `0x6200` | PRST C30 |
| 20 | `VOLUME2.out0` (0x63) | `DELAY1.in1` | `0x0036` | `0x00FF` | `0x0063` | PRST C31 |
| **21** | **`I2SIN1.out0` (0x16)** | **`SURRDEC.in0`** | **`0x0077`** | **`0xFF00`** | **`0x1600`** | **0x89, `MUX_EFFECT` in18→out0** |
| **22** | **`I2SIN1.out1` (0x17)** | **`SURRDEC.in1`** | **`0x0077`** | **`0x00FF`** | **`0x0017`** | **0x89, `MUX_EFFECT` in19→out1** |
| **23** | **`MIXER2.out0` (0x7C)** | **`DRC1.in0`** | **`0x0118`** | **`0xFF00`** | **`0x7C00`** | **0x89, `MUX_SOURCE` in2→out0** |
| **24** | **`MIXER2.out1` (0x7D)** | **`DRC2.in0`** | **`0x0118`** | **`0x00FF`** | **`0x007D`** | **0x89, `MUX_SOURCE` in3→out1** |
| **25** | **`DELAY1.out0` (0x2E)** | **`I2SOUT1.in0`** | **`0x0020`** | **`0xFF00`** | **`0x2E00`** | **0x89, `MUX_SPEAKER` in2→out0** |
| **26** | **`DELAY1.out1` (0x2F)** | **`I2SOUT1.in1`** | **`0x0020`** | **`0x00FF`** | **`0x002F`** | **0x89, `MUX_SPEAKER` in3→out1** |

Die Direktoren `MUX_GAME in0→out0` und `in1→out1` erzeugen **keinen** eigenen Schreibzugriff
(Ziel ist `MUX_SOURCE`, also selbst ein Mux — `ConnectAll`/`TraceMuxInToModule`).

### 4.3 Zwingende Grundzustandsaktionen für den Signalweg (aus `PRST`, Phase 0)

| Preset | Aktion | Wirkung [B] |
|---|---|---|
| A65 | `MAPI_AUD_EnableInterface(0x9600)` | `DSP[0x0012]` Maske `0x8000` ← `0x8000` — **I2SIN1 ein** |
| A67 | `MAPI_AUD_CFG_SetI2SInputConfig(0x9600, 0x01800000)` | `DSP[0x0012]` Maske `0x23FF` ← **`0x0180`** — I2S-Eingangsformat |
| A5 | `MAPI_AUD_EnableInterface(0x9A00)` | `DSP[0x001E]` Maske `0x8000` ← `0x8000` — **I2SOUT1 ein** |
| A9 | `MAPI_AUD_CFG_SetI2SOutputConfig(0x9A00, 0x3000A440)` | `DSP[0x001E]` Maske `0x7FFF` ← **`0x2440`**, `DSP[0x001F]` Maske `0xF93F` ← **`0x3000`** |
| A37 | `MAPI_AUD_SetMixer(0x8F01, 0, 0, 32)` | `DSP[0x0100]` Maske `0xFF00` ← `0x2000` |
| A38 | `MAPI_AUD_SetMixer(0x8F01, 0, 2, 32)` | `DSP[0x0102]` Maske `0xFF00` ← `0x2000` — **HDMI-Zweig in den Mixer-Ausgang 0** |
| A39 | `MAPI_AUD_SetMixer(0x8F01, 1, 1, 32)` | `DSP[0x0101]` Maske `0x00FF` ← `0x0020` |
| A40 | `MAPI_AUD_SetMixer(0x8F01, 1, 3, 32)` | `DSP[0x0103]` Maske `0x00FF` ← `0x0020` — **HDMI-Zweig, Ausgang 1** |
| A18/A19 | `SetVolumeInQDecibel(0x9002/0x9003, 0)` | `func_set_volume` @0x10DA8: `DSP[0x0052]`/`DSP[0x0053]` Maske `0xFFC0` ← 0 dB |
| A16/A17 | `SetVolumeInQDecibel(0x9000/0x9001, 0)` | Master-Lautstärke: `DSP[0x0050]`/`DSP[0x0051]` Maske `0xFFC0` ← 0 dB |
| A11/A12 | `CFG_VolumeMasterAssignment(0x9002/0x9003, 1)` | Volume1/2 an Master 1 |

Ohne A37–A40 kommt am Mixerausgang nichts an (Verstärkung 0), ohne A65/A5 laufen die I2S-Schnittstellen
nicht — **beide gehören zwingend zum „Durchreichen"**. Ohne A11–A19 wäre der Pegel undefiniert bzw. stumm.

`func_set_mixer(mod, out, in, gain)` @0x11654 [B]: Register `mod+152+4·in`
(MIXER2 → `0x0100…0x0105`), Maske `0xFF00` (Ausgang 0) bzw. `0x00FF` (Ausgang 1), Wert `gain << 8` bzw. `gain`.

**Fehler im Stock-Preset [B]:** A66 `MAPI_AUD_SetInputPrescale(0x9600, 5, 32)` — `MAPI_AUD_SetInputPrescale`
(@0x1EB88) ignoriert das Handle und wählt das Modul über das zweite Argument; **5 = I2SIN3**
(3 = I2SIN1, 4 = I2SIN2). A66 schreibt also `DSP[0x0017]` (I2SIN3-Vorverstärkung) ein zweites Mal
und lässt I2SIN1s Vorverstärkung (`DSP[0x0013]`, Maske `0xFF00`) auf dem Reset-Wert stehen.
Für einen Nachbau: `DSP[0x0013]` Maske `0xFF00` ← `0x2000` (Verstärkung 32) selbst setzen.

### 4.4 Der kürzere Stock-Weg: Pfad `0xC1` `HDMI2PCM_TO_SPEAKER` [B]

Das Preset enthält denselben Ausgang ohne Surround/Mixer — 4 Direktoren, 0 Aktionen:

| Quelle | → Ziel | DSP-Reg | Maske | Wert |
|---|---|---|---|---|
| `I2SIN1.out0` (0x16) | `DRC1.in0` | `0x0118` | `0xFF00` | `0x1600` |
| `I2SIN1.out1` (0x17) | `DRC2.in0` | `0x0118` | `0x00FF` | `0x0017` |
| `DELAY1.out0` (0x2E) | `I2SOUT1.in0` | `0x0020` | `0xFF00` | `0x2E00` |
| `DELAY1.out1` (0x2F) | `I2SOUT1.in1` | `0x0020` | `0x00FF` | `0x002F` |

plus die festen Zeilen 11–20 aus §4.2 (`DRC1 → TONECONTROL1 → PEQST2 → PEQST1 → VOLUME1/2 → DELAY1`).
Damit entfallen SURRDEC, SURRPOSTPRO, MIXER2 und die Mixer-Verstärkungen A37–A40 komplett.
**Empfehlung für Stufe 2:** zuerst `0xC1` nachbauen (14 Schreibzugriffe), erst danach `0x89`.

---

## 5. Klangbearbeitung (nicht nötig zum Durchreichen)

Aus den 77 `PRST`-Aktionen und dem Init:

| Aktion(en) | Zweck |
|---|---|
| `MAPI_AUD_CFG_SetDelayLineMode(0x8D00, 0x08910000)` (in `Sound_Path_Init`) | Delayline-Betriebsart DELAY1 |
| A30–A35 `CFG_DRCMasterAssignment(0x8700…0x8705, 1/2/3)` | DRC-Gruppen (Speaker/HP/SCART) |
| A29/A36 `SetMeloDBass(0x8A00, 1)`, `CFG_MeloDBass(0x8A00, 0x80010400, 0x1F00, 0x200000, 0, 0)` | Bassanhebung |
| A70–A75 `SetLimiterThreshold(0x9002…0x9007, 243/12)` | Limiter je Lautstärkemodul |
| A76 `VolumeLimiterDecayTime(10)` | Limiter-Abklingzeit |
| A57–A64, A68/A69 `EnableUserMute(…)` (Phase 1) | Dauerstumm auf nicht benutzten Zweigen (SPDIF, SCART, Master) |
| A0–A4, A6–A8, A10, A41–A56, A62 | Fremde Zweige: LineIn/LineOut, SPDIF-In/Out, Demod, ABP-DTV, I2SIN3 |
| `Sound_EQ_Init`, `Sound_PEQ_Init`, `Sound_DRC_Init`, `Sound_MelodBass_Init`, `Sound_Surround_Init`, `Sound_VolumeCurve_Init` (aus `SlaveRoutine_Thal_Sound_Init`) | Kurven/Filter aus `USRD` |
| `BP_AUD_GetYBinByIndicator(...)`-Downloads (SRS_TSHD4, Acoustics_Calibrator, PEQ3, DTE) | **entfallen: `MSPD` hat 0 Einträge** |

**Wichtig [B]:** `MSPD` (`0xA07C`) hat Größe 12 und **Anzahl 0** — dieses Board hat keine YBIN-Blobs.
`msp_download_sxl` lädt also ausschließlich `patch_msp` (2896 B, `re/work/audio/patch_msp.bin`);
S20 §2.4 „danach optional die vier Klangmodule" ist auf diesem Gerät gegenstandslos.

---

## 6. I2SOUT1 und der Weg in den Codec (Auftragspunkt 4)

### 6.1 DSP-seitig — `I2SOUT1` (`0x9A00`, Index 368) [B]

`func_set_i2s_output_config(mod, cfg)` @0x10FE6:
```
tdAudioDSPWriteRegMaskWord(0, 0x001E, 0x7FFF, cfg        & 0x37FF);
tdAudioDSPWriteRegMaskWord(0, 0x001F, 0xF93F, (cfg>>16)  & 0xF93F);
```
`func_enable_i2sout(mod, en)` @0x10FD2: `DSP[0x001E]` Maske `0x8000` ← `0xFFFF` bzw. 0.

Mit dem Stock-Wert `cfg = 0x3000A440` (Aktion A9) ergibt sich:

| DSP-Reg | Maske | Wert | ergibt zusammen mit Enable |
|---|---|---|---|
| `0x001E` | `0x7FFF` | `0x2440` | **`0x001E = 0xA440`** (Bit 15 = Enable) |
| `0x001F` | `0xF93F` | `0x3000` | **`0x001F = 0x3000`** |

Bemerkenswert: `0xA440` ist genau die untere Hälfte des Konfigurationsworts — das Preset trägt den
fertigen Registerinhalt inklusive Enable-Bit, die Maske `0x7FFF` schützt nur das Enable beim Konfigurieren.
Die Eingangsports von `I2SOUT1` liegen auf `0x0020…0x0023`, je zwei Kanäle pro Register
(hohes/niedriges Byte).

Die **Bitbedeutungen von `0x001E/0x001F`** stehen in keiner der Bibliotheken **[offen]**.
Was die Gegenseite laut Stock-DTB erwartet (`daudio_master = 1` → Codec ist **Slave**? — im Sunxi-DTB
heißt `daudio_master = 1` „CPU-DAI ist Master"; `audio_format = 3` = I2S, `tdm_config = 1`,
`pcm_lrck_period = 0x20` = 32 BCLK je LRCK-Periode, `slot_width_select = 0x20` = 32 Bit Slot),
lässt sich damit **nicht** Bit für Bit rückrechnen. **[V]** `0x001F` Bit 13/12 = Taktverhältnis
(64 fs), `0x001E` Bits 14…0 = Format/Slotbreite — das ist eine Vermutung, kein Beleg.
Praktisch ist das kein Blocker: die beiden Wörter sind fertige Werte und können 1:1 gesetzt werden.

### 6.2 AUDIF-seitig — ABPO (`snd_alsa_trid.ko`, IDA `db-audio-trid/`) [B]

`AudIf_GetHandle_abpo1/2/3` @0x4104/0x4150/0x41A0, `AudIf_i2so_Open` @0x435C,
`AudIf_i2so_activate` @0x48D8, `AudIf_i2so_setFs` @0x4294, `AudIf_i2so_GetW1cMask` @0x40A8:

| Register | Bedeutung |
|---|---|
| `0x06146000` | IRQ-Status, Write-1-to-clear |
| `0x06146004` | IRQ-Freigabe |
| `0x06146008` | **Kanalfreigabe**: ABPO1 = `0x3`, ABPO2 = `0xC`, ABPO3 = `0x30` |
| `0x06146018` | **ABPO1 Taktteiler** |
| `0x0614601C` | **ABPO1 Datenwort** (Formatwort des aktuellen Frames, 16 Bit) |
| `0x06146020` / `0x06146024` | ABPO2 Teiler / Datenwort |
| `0x06146028` / `0x0614602C` | ABPO3 Teiler / Datenwort |

W1C-/IRQ-Bits: ABPO1 = `0x40000`, ABPO2 = `0x20000`, ABPO3 = `0x10000`.

`AudIf_i2so_Open(h)`:
```
REG_Write(0x06146000, W1C);                 // anstehende IRQs löschen
REG_Write(0x06146008, kanalmaske);          // 0x3 / 0xC / 0x30
REG_Write(0x06146004, REG_Read(0x06146004) | W1C);
```
`AudIf_i2so_setFs(h, Fs, off)`:
```
teiler_8_8 = round(324000000 / (Fs + off>>8))   // 8.8-Festkomma
REG_Write(ABPOn_DIV, teiler_8_8 << 8)
```
Für 48 kHz: `324000000/48000 = 6750` → `6750<<8 = 0x1A5E00` → Register `0x1A5E0000`.

**Querbezug [B/V]:** `sound_lowlevel_init` schreibt `0x0614A00C = (alt & 0xFF000000) | 0x001A5E00`
und danach Bit 24 (S20 §2.2). `0x1A5E00` ist **derselbe Teilerwert 6750,0 im Format 8.8** —
`0x0614A00C[23:0]` ist also **[V]** der Referenzteiler „324 MHz / 48 kHz" der Audio-Insel,
Bit 24 dessen Freigabe. Das erklärt S20-Offenpunkt 5 zur Hälfte. Gegenprobe aus S16 (13:32):
`SPDO_DIV 0x0614606C = 0x034BC000` → `0x34BC0/256 = 843,75` → `324 MHz/843,75 = 384 kHz` = 8 × 48 kHz,
passt in dasselbe Schema.

`AudIf_i2so_activate` schreibt vor dem Start noch das Formatwort des Frames nach `ABPOn_DATA`
(`0x0614601C`) und ruft `AudIf_i2so_setFs`. Diese Register sind, wie schon in S20 §4.1 festgestellt,
**keine Audiodaten**, sondern Format/Takt.

### 6.3 Codec

`audio_mixer_paths.xml` (neu extrahiert): `media-speaker-i2s` setzt `DAC Src Select = I2S`,
`Speaker = On`, `Headphone = On`. Für Stufe 2 also `DAC_DPC` (`0x02030000`) Bit 31/30/29 setzen
(unser Port löscht Bit 29 absichtlich, S20 §6.7) und das I2S-Fenster `0x02031000` gemäß DTB
konfigurieren.

---

## 7. Was S20 korrigiert/ergänzt wird

| S20 | Neu |
|---|---|
| §3.2 „`sound_preset.bin` und `libmsp_util.so` fehlen" | **gefunden**, §1 |
| Offen 2 „welcher I2S-Eingang ist HDMI-2?" | **`I2SIN1` = `0x9600`**, DSP `0x0012/0x0013`, Quellcodes `0x16/0x17`. Das Preset kennt daneben `HDMIPCM` = `I2SIN3` (`0x9602`), `HDMIAC3` = `DECODER2` (`0x9401`) und `HDMI5` = `SPDIF_RX2` (`0x9701`); der HAL wählt für HDMI-IN/PCM stets `0x89`, also `I2SIN1` |
| Offen 4 „Portdeskriptoren systematisch auslesen" | erledigt, `audio-graph-a85-portregister-20260908.log` (64 Module mit allen Ein-/Ausgangsports) |
| Offen 5 „Bedeutung `0x0614A00C = 0x001A5E00`" | **[V]** 324-MHz-Teiler für 48 kHz im 8.8-Format, Bit 24 = Freigabe (§6.2) |
| Offen 6 „`SetDelayLineMode(0x8D00, 0x08910000)` unentschlüsselt" | Modul-ID bestätigt (`0x8D00 = DELAY1`), Moduswort weiterhin offen — für den Signalweg entbehrlich |
| §1.3 „Portdeskriptor 88 Byte" | **Eingangsports 28 Byte**, Ausgangsports 88 Byte |
| §1.4 „`I2SIN1 = 304`, `I2SOUT1 = 368`" | stimmt — das sind die `mod[]`-Indizes; die Preset-/API-Handles sind `0x9600` bzw. `0x9A00`, Umrechnung §3 |
| §2.4 „danach optional die vier Klangmodule" | auf diesem Board **gegenstandslos**: `MSPD` hat 0 YBIN |

## 8. Offene Punkte

1. **Bitbelegung von `DSP[0x001E]/[0x001F]`** (I2S-Ausgangsformat) und `DSP[0x0012]` (Eingang) —
   in keiner Bibliothek symbolisch; für den Nachbau genügen die fertigen Werte (`0xA440`, `0x3000`, `0x0180`).
2. **`0x8xxx`-Adressraum**: dass Bit 15 einen eigenen Byte-Registerraum adressiert, ist begründet, aber
   nicht direkt belegt (§3). Falls doch dasselbe Wort gemeint ist, kollidieren Mixer-Quellwahl und
   Mixer-Verstärkung — am Gerät leicht zu prüfen (`DSP[0x0100]` lesen, nachdem `0x8100` geschrieben wurde).
3. **`MAPI_AUD_CFG_SetDelayLineMode(0x8D00, 0x08910000)`** — Moduswort unentschlüsselt.
4. **Preset-Fehler A66** (§4.3): I2SIN1-Vorverstärkung bleibt auf Reset. Am Gerät prüfen, ob Stock
   deswegen leiser ist, oder ob die Firmware einen brauchbaren Reset-Wert hat.
5. Der Pfad `0x89` läuft über **`MIXER2`**, dessen Eingänge 0/1 fest von `DECODER3` (`0x9402`) gespeist
   werden, Eingänge 2/3 vom HDMI-Zweig — alle vier mit Verstärkung 32 [B]. **[V]** `DECODER3` ist der
   Android-Ausgabestrom (`ISTREAM`), das „MIXED" im Pfadnamen meint also HDMI + Systemton. Für uns ist
   `0xC1` (§4.4) der schlankere Weg.
6. Alles hier ist **statisch**. Am Gerät fehlt weiterhin der Zulauf: der HDMI-RX gibt ohne
   Audio-Ereignis/APLL kein I2S aus (S16 13:33, S18/S22). Der Graph nützt erst, wenn F2b gelöst ist.

## 9. Dateien

- Vendor-Dateien: `re/work/audio/stock/` (+ `HERKUNFT.txt`)
- Auswerter: `re/work/audio/parse_sound_preset.py`, `re/work/audio/derive_path_regs.py`
- IDA-Skripte: `analyse/ida/ida_a80.py` (libmsp_util dekompiliert), `ida_a81.py` (gActionTable),
  `ida_a83.py` (ConnectPort + Init_Module_*), `ida_a84.py`/`ida_a85.py` (.data-Bild der Portdeskriptoren),
  `ida_a86.py` (SM_/Trace), `ida_a88.py`/`ida_a8a.py` (Aktionen), `ida_a89.py` (`snd_alsa_trid.ko` AUDIF)
- Logs: `re/captures/weltneuheit/audio-graph-a8{0,1,2,3,4,5,6,7,8,9,a}-*-20260908.log`
- IDA-Arbeitskopie: `analyse/ida/db-audio-mspu/libmsp_util.so`
