# S22 — Warum der HDMI-RX kein `0x3000` („N/CTS neu") liefert: Ereignisweg, RX-Register, Port-Objekt, Testplan

Auftrag der Hauptsitzung vom 08.09.2026 (Messung 13:15–13:30: Zuspieler sendet, ACR rastet ein, Firmware sieht
nichts). Reine statische Analyse der `display.bin` mit idalib (IDA 9.1, DB-Kopie
`analyse/ida/db-audio-mips/display.bin.i64`), dazu die vorhandenen elog-Mitschnitte (Stock und Mainline) und
Registerabzüge. Kein Board, kein Zuspieler, nichts unter `mainline/` oder `userspace/`. Baut auf
[`S18-re-mips-hdmi-audio.md`](S18-re-mips-hdmi-audio.md) auf; Korrekturen zu S17/S18 in §7.
Skripte `analyse/ida/ida_a70.py`…`ida_a74.py`, Rohausgaben `re/captures/weltneuheit/audio-rxev-a7*-20260908.log` (§9).

Adressen: MIPS-Code `0x8Bxxxxxx`; Register als ARM-physische Adressen; `link` = `0x06840000`, `ctrl` = `0x06800800`,
`apll` = `0x06880000`. Port-Objekt-Offsets relativ zum Port-Objekt (Kontext `ctx` = Port+8; in den Handlern ist
`a2 = ctx`). Belegt = aus Dekompilat/Mitschnitt; vermutet = so markiert.

---

## 0. Antwort zuerst

| Frage | Kurzantwort | Beleg |
|---|---|---|
| **1** Warum kein `+0x11[6]` | Alle Freigaben stehen (`+0x10 = 0x4D` enthält Bit 6; `+0x06` gattet die Sammelbits **nicht**, Paket-/Videoereignisse feuern ohne ihr Bit in `+0x06`). Das Bit ist ein W1C-Latch, das nur die Firmware löscht und nur, wenn `+0x05[3]` steht — ein einmal gesetztes Bit hätte der 1-ms-Poll gesehen. Die Hardware hat es also nie gesetzt. **Die APLL ist nicht die Voraussetzung**: die Firmware erwartet das erste `0x3000` bei abgeschalteter APLL (Aktivierung: `sub_8B13BE54` legt `apll+4[1:0] := 3`, `Init` scheitert mit `bPdivCalc Failed`, `PowerUp` läuft nie; Sleep-Entry schreibt `PowerDown`), und **Stock tut exakt dasselbe** (identische Zeilen in `elog-stock-LIVE.bin`). Das gemessene Bild — ACR ja, Statusnibble `+0x40[7:4]` 0, Channel-Status `+0x56` 0, Fs-Messung `+0x15F` 0, kein Audio-InfoFrame-Bit `+0x0F[3]`, N folgt dem 44,1-kHz-Wechsel nicht — ist das Bild „**ACR ohne Audio-Sample-Pakete**": ACR sendet i915, sobald die Audio-Funktion des Transcoders an ist; Sample-Pakete und Audio-InfoFrame kommen nur vom HDA-Pin, auf dem der Strom wirklich läuft. **Erstverdächtiger ist die Quelle (falscher HDMI-Pin/PCM-Device)**, Zweitverdächtiger ARM-seitige Versorgung (Demod-Bus/Audio-Top), Drittverdächtiger die APLL. Alle drei sind am Board unterscheidbar (§6). | §2, §3 |
| **2** RX-Kern-Register | Es gibt **keinen** separaten 32-bit-Synopsys-Kern in der Firmware: `0x05000000` ist laut Abzug-Kopf und lui-Karte **`DE2_NR_base`** (`NRWinNode__WriteReg`), `0x050C0000` `DE2_DETN` — beides Display-Engine; die rk3588-Offsets lesen deshalb 0. Der HDMI-RX ist vollständig der Byte-Registerblock `0x0680xxxx/0x0684xxxx/0x0688xxxx` (Trident „TV303"). Audio-relevante Schreibungen: Aktivierung `link+0x02 := 0x27`, Impuls `[6]`,`[5]`; Zustand 4 `+0x10 := 0x4D`, `+0x12 := 0x27`, `+0x0C/0x0D := 0x87/0x8F`; neues Timing `PD_Reset` (`+0x02[5],[6]` Impuls); Signal stabil `+0x40[2:0] := 7`; erst **nach** `0x3000`: APLL (`apll+0…0x18`), Route `+0x160/+0x15E[6:4]/+0x4B[1]`. Der gescheiterte Init lässt nur die APLL im Reset zurück (`apll+4[1:0] = 3`, `+0xC[31] = 1`, `+0x18[3] = 0`); `link+0x02` endet bei `0x07` — wie gemessen und wie Stock. Takte/Resets des Blocks stellt die Firmware nicht; ARM-seitig sind `hdmi-audio 0xd84`, `bus-hdmi-audio 0xd80[31]`, `pd_tvcap` an, `bus-demod 0xd64` aus. | §4 |
| **3** Port-Objekt | Gates: `+1325` Aktiv-Flag (für `0x3000`, `0x3005`, `0x2006…0x2008`; `0x3001…0x3004` zusätzlich Zustand 5), `+188 ≥ 3` und `+1325` für den ISR-Poll, `+1302` für den Port-Poll, `+1301` für die Zustandsmaschine. Kein DVI-/Deep-Colour-/Double-Sampling-Gate. `link+0x1D[2:1]` ist **Pixelformat** (AVI-Y: 1 → 01, 3 → 10), nicht DVI/HDMI; DVI/HDMI steht in `Port+12` (1 = HDMI, 2 = DVI). Weg vom ARM: `[0x4BAC1A5C]` → DeviceManager → `+24` THDMIRx (Kontrolle: `+0 = 0x8B1F590C`) → `+232` aktiver Port (`+236/240/244` Ports 1–3) → Felder §5; Paketpuffer VSI/AVI/SPD/**Audio** bei Port+537/568/599/**630** (AVI/SPD als Positivkontrolle). | §5 |
| **4** Test | Der Rebind-/`SetSource`-Test **greift nicht**: `sub_8B13C4EC` nimmt CTS/N aus `info` (Port+128/+132, nur von `Get_N_CTS` beim Ereignis gefüllt), nicht aus `link+0x45…`, und `DP_Port_Select` nullt `info` unmittelbar davor. Stattdessen drei Stufen mit je einem Kriterium, das scheitern kann: **(A)** Quelle/Paketweg — Port+630 (Audio-InfoFrame) und `+0x0F[3]` beim Neustart des Tons auf dem **richtigen** HDA-Pin (§6.1); **(B)** ARM-Versorgung — Demod-Bus/Audio-Top nach S16-Versuch 4, dann `+0x11/+0x40/+0x56` erneut (§6.2); **(C)** Henne-Ei brechen — SRAM-Poke `info` + Nibble-Merker, die Firmware programmiert die APLL selbst und protokolliert jeden Schritt; Beleg `PllPowerUp success!` und `+0x15F[6:4] = 3` (§6.3, Risiko benannt). | §6 |

---

## 1. Datenlage und Instrumente

* **Firmware-Dekompilate** (a70–a74): alle audio-relevanten Funktionen des HDMI-RX-Treibers samt Rohdisassembly der
  kritischen Aufrufstellen; Ops-Tabelle `0x8b22f280…0x8b22f35c` (versteckte Aufrufer über Funktionszeiger) vollständig
  aufgelöst — `sub_8B13C4EC` hat genau **einen** Aufrufer (`THDMIRx_DP_Init_Stage2`), `PowerUpAPLL`/`sub_8B13BE54`
  haben keinen Tabellen-Leser.
* **elog-Mitschnitte** (`re/captures/weltneuheit/`): Stock (`elog-stock-LIVE.bin`, normiert `stock-live-norm.txt`),
  Mainline (`elog-mainline.bin`, `mainline-elog-Y2-postpatch.txt`, `elog2-mainline-v3run.txt`, `elog-noWIPE.bin`,
  `elog-current.txt`, `s11-…/elog-run4.txt`, `s16-audio-…/elog-audio1-…`). **Der Stock-Mitschnitt lief mit einer
  DVI-Quelle** (`Conver signalID,isDVI:1 signal:0x20057`, `Update HDMI mode to 2`) — er kann für den Audio-Weg nichts
  belegen, wohl aber für die Gleichheit der Firmware-Sequenz (§2.5).
* **Registerabzüge**: `stock-pre/post-hdmi-v2.txt` (nur Vielfache von 4), die Byte-Messung der Hauptsitzung vom 08.09.
* **Was `0x05000000` ist**: Abzug-Kopfzeile `=== DE2_NR_base @ 0x05000000 ===`, `=== DE2_DETN @ 0x050C0000 ===`;
  lui-Karte der Firmware (`audio-audif-a63`): `0xBA00 → 0x05000000 NRWinNode__WriteReg, WCETop__SetWindow,
  memory_agent_onoff`. Das Legacy-Skript `analyse/hdmi-seq/hdmirx_ctrl_enable.py` nannte `0x050C0000` „Synopsys" und
  schrieb rk3588-Offsets dorthin — das war die Display-Engine. `MAINUNIT_STATUS 0x0150 = 0x04d4f300` ist ein NR-Register.

---

## 2. Der Ereignisweg in der Firmware (belegt)

### 2.1 Freigaben — `HdmiRx_State4_HW_EnableIRQs 0x8b13c754` (Eintritt Zustand 4, Ops-Slot `0x8b22f2bc`)

| Byte | Wert | Bedeutung (aus `ScanISR_Packet`) |
|---|---|---|
| `link+0x06` | `\|= 0x6A` | Sammel-Freigabe Bits 1,3,5,6 — **gattet `+0x05` nicht** (s. 2.2) |
| `link+0x10` | `\|= 0x4D` | Audio-Gruppe A: Bit 0 `0x3005`, Bit 2 `0x3001`, Bit 3 `0x3002`, **Bit 6 `0x3000`** |
| `link+0x12` | `\|= 0x06`, `\|= 0x21` | Gruppe B: Bit 1 `0x3003`, Bit 2 `0x3004`, Bit 5 `0x4003`, Bit 0 `0x4004` |
| `link+0x0C` | `\|= 0x87` | Paketgruppe `+0x0E` |
| `link+0x0D` | `\|= 0x8F` | Paketgruppe `+0x0F`: Bit 0 VSI, Bit 1 AVI, Bit 2 SPD, **Bit 3 Audio-InfoFrame**, Bit 7 |
| `link+0x0B[0]`, `link+0x16[0]` | 1 | Video-/`+0x17`-Gruppe |

Gegenstück `sub_8B13E90C(link, 0)` (Sleep-PreAction) löscht dieselben Bytes. Gemessen am 08.09.: `+0x0C = 0x87`,
`+0x0D = 0x8F`, `+0x10 = 0x4D`, `+0x12 = 0x27`, `+0x06 = 0x6A` — alles wie geschrieben. **Es fehlt keine Freigabe.**
`+0x28…+0x3F` sind Timing-Zähler (H/V-Total, Aktiv, Offsets), die `sub_8B13F9F8` nur liest — keine Freigabestufe.

### 2.2 Poll — `HdmiRx_ScanISR_Packet 0x8b13ef54` (alle 10 ms, nur Zustand ≥ 3 ∧ Aktiv-Flag, `sub_8B136078`)

```
Byte = rd(+0x05)                       # Sammelstatus
[7] → rd/wr(+0x17): [0] → 0x1005
[0] → rd/wr(+0x07): [5] → 0x1003 (DVI), [3] → 0x1004, [1] → 0x2000, [2] → 0x1006 ; liest +0xA9
[2] → rd/wr(+0x0E): [0] → 0x2002, [7] → 0x2009
      rd/wr(+0x0F): [0] → 0x2002, [2] → 0x2004, [1] → 0x2005 (+ log "Receive MSG_HDMIRX_INTR_PKT_DIFF_AVI"), [3] → 0x2006
[3] → rd/wr(+0x11): [6] → 0x3000, [2] → 0x3001, [3] → 0x3002, [0] → 0x3005
[4] → rd(+0x13), wr masked 0x06: [1] → 0x3003, [2] → 0x3004 ; wr masked 0x21: [5] → 0x4003, [0] → 0x4004 (nur wenn +0x422[0]==0)
```

Drei Folgerungen: (a) `+0x11` wird **nur** gelesen und gelöscht, wenn `+0x05[3]` steht; ein Bit in `+0x11` ohne
`+0x05[3]` bliebe für den ARM sichtbar stehen. (b) `+0x05` wird nicht von `+0x06` gegattet: `+0x06 = 0x6A` enthält
weder Bit 0 noch Bit 2, trotzdem kamen `0x1003` („Update HDMI mode") und die Paketereignisse (AVI/SPD/VSI-Dumps im
S16-Mitschnitt). (c) Die Statusbits sind W1C-Latches (die Firmware schreibt den gelesenen Wert zurück). Der 1-ms-Poll
über 9 s hat `+0x11` und `+0x05[3]` nie gesehen ⇒ die Hardware hat `+0x11[6]` **nicht gesetzt**, weder pegel- noch
flankenartig. `+0x05 = 0x40` (Bit 6 dauerhaft) gehört zu einer Gruppe, die `ScanISR_Packet` nicht bedient (Bits 1, 5, 6
haben keinen Statusbyte-Leser; `+0x09` liest der HDCP-Thread über `sub_8B13D1A8` bei `+0x05[1]`) — offen, s. §8.

### 2.3 Filter und Handler

`sub_8B135950 0x8b135950`: `0x3000` und `0x3005` → Aktiv-Flag (`ctx+1317` = Port+1325); `0x3001…0x3004` → Aktiv-Flag ∧
Zustand 5; `0x2006/0x2007/0x2008` → Aktiv-Flag (**Korrektur zu S18**, dort „immer"); `0x1003/0x1004` → Zustand 5;
Rest frei. `ISREventHandle 0x8b1359e8`, Fall `0x3000`: `Get_N_CTS(link, info)` (`+0x45..0x4A` → `info+0` CTS, `info+4`
N, log `Audio N 0x%x CTS 0x%x`), darin `sub_8B13C1D8` (`+0x15F[6:4]` → `info+12` kHz), dann `sub_8B13C3D8`
(`+0x56[3:0]` → `info+8` Hz), log `audio param:%d %d %d %d %d` (CTS, N, Fs Hz, Fs kHz, Nibble-Merker `info+16`),
`info+40/+44 := 0`. Fall `0x2006`: `sub_8B1366B4(ctx+188, link, ctx+188)` — Rohdisassembly `8b135c24`: `addiu $a2,$a1,0xBC`
— liest Pakettyp `0x84` nach `(ctx+188)+434` = **Port+630**, ruft bei Aktiv-Flag den Handler `dword_8B22F288`
(nirgends registriert). Kein Log.

### 2.4 Running-Tick und APLL — `sub_8B139E78 0x8b139e78` (Zustand 5, Aktiv-Flag, alle 10 ms)

```
nibble = rd(+0x40) & 0xF0
if info+16 != nibble:  info+16 = nibble; HdmiRx_Audio_SetAPLL(apll, info); Route(link, nibble)
sub_8B13C1D8(link, info)        # Fs-Messung → info+12
```
`SetAPLL 0x8b13c01c`: `if (info+4 == info+48 && info+8 == info+52) return;` — ohne vorheriges `0x3000` (N = 0 = Merker)
passiert **nichts**. Sonst log `Audio: N change from … fs change from …, CTS = …`, `sub_8B13BE54(apll)`
(`apll+4 |= 3`, `apll+0xC |= 0x80000000`, `apll+0x18 &= ~8`), dann Lesen von `apll+0xC..0xF`: Bit 31 gesetzt →
`%s: Calling Init` (`0x8b13b7b0`), sonst `Calling Update` (`0x8b13baf8`). Weil BE54 Bit 31 unmittelbar davor setzt,
ist der Init-Zweig der erwartete (falls das Bit nicht selbstlöschend ist — vermutet).

`Init`: `CalculateDividerSettings({CTS, N, Fs})` → bei Erfolg `PowerDownAPLL` (`apll+4 := 0x50000003`, log
`HdmiRxAudioPllPowerDown success!`), `apll+0 := 0x0D326667`, `apll+4 := (alt & 0xFFFF01FF) | pDiv<<9 | 0x10`,
`PowerUpAPLL` (`apll+4[0] := 0`, `apll+0x10[2:0] := 3`, log `HdmiRxAudioPllPowerUp success!`), **unbegrenzte**
Warteschleife `while (rd(apll+8) & 2)`, `apll+4[1] := 0`, `apll+0xC := 0x40000000 | mInt<<15 | mRem`, dann `| 0x60000000`.
Rechnung (Soft-Float, Zuordnung aus dem Stage-Log belegt: `sub_8B1CEBC8` = div, `sub_8B1CF16C` = mul):
TMDS = CTS/N·128·Fs; Fin = TMDS/CTS·2^xDiv = 128·Fs/N·2^xDiv (kleinstes xDiv mit Fin ≥ 2 800 001); Fout = 128·Fs;
mDiv = v·Fout/Fin mit v ∈ {32,16,8,4} ↔ pDiv ∈ {8,17,11,2}, erster Treffer mit 24 ≤ mDiv < 93; mInt/mRem aus
Fout·v/Fin. **Die APLL-Referenz ist der wiedergewonnene TMDS-Takt** (Fin ≈ 4 MHz), nicht der CCU-Takt `hdmi-audio`.
Nachgerechnet (`float32`) für {148494, 6144, 48000}: TMDS `0x8d9d6b0`, xDiv 1, Fin 4 096 000, Fout 6 144 000,
mDiv 48, pDiv 8, mInt 48, mRem 0 → `apll+4` Bits `0x1010`, `apll+0xC = 0x60180000`; für 44,1 kHz (N 6272): mDiv 49,
`0x60188000`. `Init` schreibt xDiv **nicht** (nur `Update` schreibt `apll+0x18 = (alt & ~6) | xDiv<<1 | 8`).

### 2.5 Aktivierung und Zustandswechsel — bei uns wie in Stock

`THDMIRx_SwitchPort 0x8b131c00(…,1)`: `SetActiveFlag(1)` → `DP_Port_Select` (**`HdmiRx_Context_Memzero_Helper(ctx)`**,
sofern Zustand ≠ 4 — nullt `info`, Paketkontext, Timing) → `Connect_Link_Path` (Modus 1: `Port_Select`,
`PHY_PreConfigClear`, `PHY_Reset`, `Reset_HDCP_DDC`, `IDCLK`, DDC/HPD an) → `DP_Init_Stage1` (`+0x1D[6] := 1`,
`+0x1D[0] := 1`) → `DP_Init_Stage2` → **`sub_8B13C4EC(link, apll, info)`**:

```
sub_8B13C1D8(link, info)                 # Fs-Code +0x15F → info+12 (ohne Signal: 0 → 32 kHz)
wr(+0x02, 0x27); wr_masked(+0x02, 0x40, 0x40)
sub_8B13BE54(apll)                       # apll+4 |= 3 (Reset/PD), apll+0xC |= 1<<31, apll+0x18 &= ~8
Init(apll, {info+0 CTS, info+4 N, 1000*info+12})   # CTS = N = 0
wr_masked(+0x02, 0x40, 0); wr_masked(+0x02, 0x20, 0)   → +0x02 = 0x07
```
Mit CTS = N = 0 liefert Stage 0 `TMDS=ffffffff` (int(NaN)), Stage 1 „Pass" mit `SPad=-1`, Stage 2 `Fin=-1`, Stage 3
viermal `Calc Prog`, dann **`bPdivCalc Failed`** (nicht `bXdivCalc` — Korrektur zu S18) → `Init` kehrt **vor**
`PowerDown/PowerUp` zurück. Danach Zustand 1→2 (`Sleep_Entry`: `PowerDownAPLL` weil Aktiv-Flag) →3→4→5.

**Stock identisch** (`elog-stock-LIVE.bin` Z. 752–8087; `elog-mainline.bin` Z. 752–4202 u. a.): Boot `HdmiRx_MAC_Init
link_base:0x6840000` + `HdmiRxAudioPllPowerDown success!` (aus `HdmiRx_HDCP22_GetPkf_AndInit` in `InitAllLinks`) +
`read efuse pkf`; Aktivierung `SetActivePort 1` → `DDC and PHY select prot 1` (Modus 1) → `HdmiRx_Port_Select
base=6800800 port 1` → `AUDIO PLL CALC: Stage 0 TMDS=ffffffff OutputFs=3e8000` → … → `bPdivCalc Failed` →
`HdmiRxAudioPllPowerDown success!` bei 1→2. In keinem Stock- oder Mainline-Mitschnitt gibt es `Audio N`,
`audio param`, `N change`, `Calling Init/Update` oder `PowerUp`; der Stock-Mitschnitt hatte eine DVI-Quelle.

Zustandswechsel (`THDMIRx_StateMachine_Dispatcher 0x8b138738`): 2 `Sleep_PreAction` (`+0xA9[2] := 0`, `+0x1B |= 0x15`,
IRQs aus, AEC aus) + `PowerDownAPLL`; 3 `Idle_PreAction` (`+0x1B &= ~0x14`, `+0x00[6] := 1` TMDS-Reset, AEC an) +
`PD_Reset`; 4 `HW_EnableIRQs`; 5 `Running_PreAction` (`+0x00[6] := 0`, IDCLK-Impuls `+0x00[7]`) + `SetMute(1,1)`.
Bei neuem Timing in 5: `TimingMonitorTask` → `PD_Reset` (`reset system_pd_audio_t!!!`), unabhängig vom Aktiv-Flag.
`0x3001/0x3002` bzw. `0x3003/0x3004` ≥ 11× → `audio error(0x%x) !!!!`, `info` löschen, `PD_Reset` (Gruppe B zusätzlich
`HdmiRxFixedEQ_Update(4)`).

---

## 3. Warum kein `+0x11[6]` — Bewertung

1. **Freigaben, Filter, Zustand, Poll**: alle offen bzw. aktiv (belegt: Registerwerte, `prot:1 set signal ID`,
   `set AV mute:0 0` setzen das Aktiv-Flag voraus). Kein Softwaregrund.
2. **APLL-Henne-Ei**: Die Firmware ist so gebaut, dass das erste `0x3000` bei abgeschalteter APLL kommt — anders
   könnte sie nie Audio starten, denn `SetAPLL` reagiert nur auf ein gefülltes `info` und `sub_8B13C4EC` läuft genau
   einmal, mit Nullen. Stock durchläuft dieselbe Sequenz (§2.5). Der Trident-Entwurf setzt also einen N/CTS-Detektor
   voraus, der ohne APLL arbeitet (TMDS-/Paketdomäne). Ob **diese Hardware** das einlöst, ist statisch nicht
   beweisbar — aber es ist nicht der erste Verdächtige.
3. **Das gemessene Bild ist „ACR ohne Audio-Samples"** (Bewertung, aus dem Firmware-Verhalten abgeleitet):
   * ACR-Bytes `+0x45..0x4A` folgen dem Relock — der Paketdecoder läuft. ACR (N/CTS) erzeugt i915 hardwareseitig,
     sobald die Audio-Funktion des Transcoders aktiv ist (ELD vorhanden) — **unabhängig davon, ob ein Strom fließt**.
   * Audio-Sample-Pakete und der Audio-InfoFrame kommen nur vom HDA-Pin, auf dem die PCM wirklich läuft (den
     Audio-InfoFrame schreibt der HDA-Codec-Treiber beim Prepare in den Pin). Bei uns: `+0x0F[3]` nie, Statusnibble
     `+0x40[7:4]` 0, `+0x56` 0 (kein Channel-Status), `+0x15F` 0, keine `0x3001…0x3004`-Fehler (ein FIFO ohne Eingang
     läuft nicht leer).
   * **N blieb bei 6144 nach dem Wechsel auf 44,1 kHz**: i915 setzt N pro Verbinder über `sync_audio_rate` des Pins,
     auf dem die PCM geöffnet wird. Läuft sie auf einem anderen Pin, bleibt N von `HDMI-A-2` unverändert — genau so
     gemessen.
   * S16: PipeWire meldete das gewählte HDMI-Profil (`hdmi-stereo-extra1`) dauerhaft **„available: no"** — das ist
     die Jack-/ELD-Verfügbarkeit **dieses Pins**; `eld#2.3` (Pin-Index 3) ist ein anderer Pin als `extra1` (Pin-Index 1).
   Statisch nicht entscheidbar, am Board in einer Minute (§6.1). Wenn dort der Audio-InfoFrame erscheint, ist Punkt 3
   erledigt und es bleibt 4/5.
4. **ARM-seitige Versorgung** (vermutet): Der Audioausgang des RX geht in den Audio-Top (AUDIF/SPDI1, Demod-Bus
   `0xd64`, bei uns beim Boot aus). Ob die Statuslogik des RX-Audioteils (Fs-Messung, Channel-Status) einen Takt aus
   dieser Richtung braucht, ist unbekannt; `hdmi-audio 0xd84`, `bus-hdmi-audio 0xd80[31]` und `pd_tvcap` sind an. Die
   Firmware schaltet dort nichts (S18 §7). Test §6.2.
5. **APLL** (vermutet, zuletzt): Falls die Fs-Messung/Channel-Status in der Audiotakt-Domäne liegen, bleiben sie ohne
   APLL still — das erklärt aber nicht das fehlende `+0x0F[3]` (Paketgruppe, in der AVI/SPD feuern). Test §6.3.

---

## 4. RX-Register für Audio (Frage 2)

Kein Zugriff der Firmware auf ein 32-bit-Kernfenster; alle Audio-Zugriffe (a2a-Registerkarte + a70) sind Byte-Zugriffe:

| Register | Schreiber | Zeitpunkt | Wert/Bit | Bei uns gemessen |
|---|---|---|---|---|
| `link+0x02` | `sub_8B13C4EC`; `PD_Reset 0x8b13c67c`; `sub_8B13D160` | Aktivierung; neues Timing/Idle/Fehler; HDCP-Key | `:= 0x27`, Impuls `[6]`, `[5]`; `[4]`-Impuls | `0x07` (= Stock) |
| `link+0x06/0x10/0x12/0x0C/0x0D/0x0B/0x16` | `HW_EnableIRQs` / `sub_8B13E90C` | Zustand 4 / Sleep | s. §2.1 | wie geschrieben |
| `link+0x11/0x13/0x0E/0x0F/0x07/0x17` | `ScanISR_Packet` (W1C) | alle 10 ms | Rückschreiben | `0`, `0`, `0`, `0` |
| `link+0x40[2:0]` | `loc_8B13E830` (SetMute) | Running-Entry 0, SignalMonitor 0, App-Kette 7; `0x3005` setzt `[2]` | 7 = Audio auf | `0x07` |
| `link+0x40[7:4]` | Hardware | — | Statusnibble → `SetAPLL`/Route | `0` |
| `link+0x45..0x4A` | Hardware | — | N/CTS (20 bit) | 6144 / 148494 |
| `link+0x4B[1]` | `sub_8B13C5B0` | nach Nibble-Änderung | Übernahme | — |
| `link+0x56[3:0]` | Hardware | — | Channel-Status Fs | `0` |
| `link+0x15E[6:4]`, `+0x160` | `sub_8B13C5B0` | nach Nibble-Änderung | Route roh/PCM | `0`, `0` |
| `link+0x15F[6:4]` | Hardware | — | gemessener Fs-Code | `0` |
| `link+0x1D[0]` | SetMute | Running/Signal | Video-Mute | `0xE1` → Bild an |
| `link+0x1D[2:1]` | `sub_8B140184` bei `0x2005` | AVI-Y 1 → 01, 3 → 10 | Pixelformat (RGB: nichts) | `00` (RGB) |
| `apll+0x00…0x18` | `PowerDownAPLL` (Boot via `HDCP22_GetPkf_AndInit`, Sleep-Entry), `BE54` (Aktivierung, SetAPLL), `Init/Update/PowerUp` (nur nach `0x3000`) | s. §2.4 | nach Aktivierung erwartet: `+4[1:0] = 3`, `+0xF[7] = 1`, `+0x18[3] = 0` | nicht gemessen |
| `0x068000A7[0]`, `0x06E00020[0]` | ARC-RPCs | — | ARC-Rückkanal | nicht Audio-Eingang |

Was nach dem gescheiterten Init **abgeschaltet bleibt**: nur die APLL selbst (Reset/PD-Bits aus `BE54`, später
`PowerDown` in Sleep). `link+0x02[6:5]` werden in jedem Pfad wieder gelöscht (Impuls). Es gibt im Link-Fenster keinen
weiteren „Audio-Takt-/Path-Enable", den die Firmware kennt; `HdmiRx_MAC_Init 0x8b13dfa8` (Boot, beide Systeme) schreibt
`+0x1A[0] := 0`, `+0xC9[4:0] := 0x14`, `+0x310[6:5] := 3`, `+0x186/0x187 := 0`, `+0x23[3] := 0`, `+0x64/0x65 := 2` — nichts
davon ist als Audio erkennbar, `+0x64 = 2` steht auch im Stock-Abzug.

ARM-Seite (S17/S16, zur Einordnung): `hdmi_audio_clk 0xd84 = 0x80000000` (an, Mux pll-video3-4x, Teiler 1),
`bus_hdmi_audio 0xd80[31]` an, kein Reset für hdmi-audio; `bus_demod 0xd64 = 0` (aus, Reset anliegend) bis zum
S16-Rezept. `pll-video3`: CCU-Dump 07.09. `0xb8006300` (N 0x63 → 2400 MHz, S17 §5.4 hatte Recht für diesen Stand),
Messung 08.09. `0xb8002f00` (N 0x2f → **1152 MHz**, Stock-gleich). Beide Lesungen sind echt — die PLL wird zwischen
Boots/Konfigurationen umprogrammiert (offen, wer). Für den RX ist das nachrangig: die APLL-Referenz ist der TMDS-Takt
(§2.4); wofür der 1152-MHz-Takt im RX dient (Fs-Messung? Ausgangsresampler?), ist unbelegt.

---

## 5. Port-Objekt und der Weg vom ARM (Frage 3)

**Zeigerkette** (belegt: `DeviceManager_GetInstance 0x8b183a54` = `[0x8BAC1A5C]`; `DeviceManager_Ctor 0x8b1830cc`
`a1[6] = CreateDeviceHDMI()`; `THDMIRx_Ctor 0x8b131958`; MIPS-VA → ARM: `(va & 0x1FFFFFFF) + 0x40000000`, doku/98):

```
dm      = rd32(0x4BAC1A5C)                     # MIPS-VA des DeviceManagers
thdmirx = rd32(arm(dm) + 24)                   # Kontrolle: rd32(arm(thdmirx) + 0) == 0x8B1F590C (vtable)
port    = rd32(arm(thdmirx) + 232)             # aktiver Port; +236/+240/+244 = Ports 1..3
```

| Port-Offset | Inhalt | Setzer / Bedeutung |
|---|---|---|
| `+12` | 1 = HDMI, 2 = DVI | `0x1004/0x2000` → 1, `0x1003` → 2 (`isDVI` in `SignalMonitor`) |
| `+128 / +132` | CTS / N | `Get_N_CTS` beim `0x3000` — sonst 0 |
| `+136 / +140` | Fs Hz (Channel-Status) / Fs kHz (Messung) | `sub_8B13C3D8` / `sub_8B13C1D8` (jeder Running-Tick: ohne Signal 32) |
| `+144` | Nibble-Merker (`+0x40[7:4]`) | `sub_8B139E78` |
| `+148 / +152` | Fehlerzähler `0x3001/2` / `0x3003/4` | `ISREventHandle` |
| `+176 / +180` | letztes N / letztes Fs (SetAPLL-Merker) | `SetAPLL` |
| `+184` | `0x06880000` | `HdmiRx_PHY_ContextReset_Memzero` |
| `+188` | Zustand 1…5 | `SwitchState` |
| `+537 / +568 / +599 / +630` | Rohpakete VSI `81 01 04…` / AVI `82 02 0d…` / SPD `83 01 19…` / **Audio-InfoFrame `84 01 0a…`** (je 31 Byte: HB0–HB2 + PB) | `sub_8B1372F4` / `sub_8B137FE0` / `sub_8B1379D4` / `sub_8B1366B4` (Aufrufstellen mit `$a2 = ctx+188`, a74) |
| `+1301` | HPD-Enable (Zustandsmaschine läuft nur dann) | `Connect_Link_Path` |
| `+1302` | Port aktiv (Poll) | `Port_Init` = 1 |
| `+1303` | Port-ID | |
| `+1308` | `link` = `0x06840000` | |
| `+1319` | AV-Mute-Status | |
| `+1325` | **Aktiv-Flag** (Gate für `0x3000/0x3005/0x2006…8`, ISR-Poll, Running-Tick-Audio) | `SwitchPort` |
| `+1326` | Signal valid (`+0x37A`) | `sub_8B139050` |

Kein Feld unterdrückt Audio-Ereignisse außer `+1325`/`+188`; `dwUseDoubleSampling` ist TSE-Video (S18). Alles im
MIPS-RAM, für den ARM ohne Hänger lesbar (doku/72:1281); `port+568` (AVI) und `port+599` (SPD, „Intel") sind die
**Positivkontrollen** des Lesers — sie müssen gefüllt sein, weil diese Ereignisse im S16-Mitschnitt geloggt wurden.

---

## 6. Testplan (Frage 4) — drei Stufen, jede mit Scheiterkriterium

Vorab zum vorgeschlagenen Rebind-Test: `SetSource` → `SetActivePort` → `SwitchPort(port,1)` → `DP_Port_Select` nullt
`info` (Zustand ≠ 4) → `Stage2` → `sub_8B13C4EC` rechnet wieder mit CTS = N = 0 → `bPdivCalc Failed`. Die
eingerasteten ACR-Bytes liest dieser Pfad nicht. Ergebnis wäre nur ein PHY-Reset mit Bildaussetzer. **Nicht sinnvoll.**

### 6.1 Stufe A — Sieht der RX Audio-Pakete? (nur SRAM lesen, kein MMIO-Risiko)

1. Zeigerkette §5, Kontrollen: vtable `0x8B1F590C`, `port+1308 == 0x06840000`, `port+1325 == 1`, `port+188 == 5`,
   `port+568` beginnt mit `82 02 0d`, `port+599` mit `83 01 19`. Scheitert eine, ist der Leser falsch — abbrechen.
2. `port+630`: `84 01 0a …` ⇒ der RX hat mindestens einmal einen Audio-InfoFrame verarbeitet (Paketweg und Quelle in
   Ordnung) → weiter mit B/C. `00 …` ⇒ nie ein Audio-InfoFrame → Quelle prüfen:
   * Zuspieler: welcher Pin hat `monitor_present 1` (`/proc/asound/card0/eld#*`), welches PCM-Device gehört dazu
     (`/proc/asound/card0/codec#<addr>`, Pin-Node → `Device: … device=N`), läuft die PCM auf **diesem** Device
     (`/proc/asound/card0/pcm<N>p/sub0/status`)? PipeWire-Port mit `available: yes` wählen, nicht `extra1` blind.
   * Ton stoppen, 1-ms-Poll auf `+0x0F` starten (Bit 3), Ton auf dem richtigen Device starten: Kriterium
     `+0x0F[3]` mindestens einmal 1 **und** `port+630 = 84 01 0a …` danach. Erwartete elog-Zeilen bei Erfolg des
     ganzen Weges: `Audio N 0x1800 CTS 0x2440e` → `audio param:148494 6144 48000 … ` → (nächster Tick, falls
     Nibble ≠ 0) `Audio: N change from 0x0 to 0x1800, fs change from 0x0 to bb80, CTS = 0x2440e` → `Calling Init` →
     `AUDIO PLL CALC: Stage 0 TMDS=8d9d6b0 OutputFs=5dc000` … `Stage 6 xDiv=1 pDiv=8 mDiv=48 mInt=48 mRem=0` →
     `HdmiRxAudioPllPowerDown success!` → `HdmiRxAudioPllPowerUp success!`; Register: `+0x40[7:4] ≠ 0`, `+0x56 = 2`,
     `+0x15F[6:4] = 3`, Positivkontrolle 44,1 kHz: `+0x56 = 0`, `+0x15F[6:4] = 2`, N `0x1880`.
   Bleibt `+0x0F[3]` aus, obwohl AVI-Diff bei einem Modeset feuert (Kontrolle der Gruppe), sendet die Quelle keinen
   Audio-InfoFrame — dann ist alles Weitere am Board Zeitverschwendung.

### 6.2 Stufe B — ARM-Versorgung (nur wenn A den Audio-InfoFrame zeigt, aber kein `0x3000` kommt)

Demod-Bus + 16 TVFE-Gates + Router + `audio_top_clk_init` nach dem hängerfreien S16-Versuch 4 (kein AUDIF-Zugriff!),
Ton neu starten, dieselben Bytes: `+0x11`, `+0x40`, `+0x56`, `+0x15F`, elog. Ändert sich nichts ⇒ Versorgung ist es
nicht (für die Statuslogik des RX).

### 6.3 Stufe C — Henne-Ei brechen: die Firmware programmiert die APLL selbst (SRAM-Poke)

Idee: `sub_8B139E78` ruft `SetAPLL` bei Nibble-Änderung; `SetAPLL` rechnet mit `info`. Der ARM füllt `info` und
verstellt den Merker — die Firmware macht den Rest und protokolliert jeden Schritt (Stufe 3):
1. Vorher lesen (Erwartung nach gescheitertem Init, Bytezugriff wie `rdb`): `0x06880004[1:0] = 3`, `0x0688000F[7] = 1`,
   `0x06880018[3] = 0`. Liest es anders, stimmt das APLL-Modell nicht — dann nicht poken. (Der Block wird von der
   Firmware bei Boot und Sleep-Entry byteweise beschrieben, bei uns ohne Hänger; ARM-Lesbarkeit ist unbelegt —
   moderates Risiko, Legacy-Modul schrieb dort byteweise ohne Hänger, doku/72 Lauf 35.)
2. Schreiben (32-bit, MIPS-RAM): `port+128 := 148494` (CTS, aus `+0x48..0x4A` genommen), `port+132 := 6144`,
   `port+136 := 48000`, zuletzt `port+144 := 0x10` (≠ Nibble 0).
3. Innerhalb von 10 ms erwartet: `Audio: N change from 0x0 to 0x1800, fs change from 0x0 to bb80, CTS = 0x2440e`,
   `HdmiRx_Audio_SetAPLL: Calling Init`, Stage 0–6 wie in 6.1, `PowerDown success`, `PowerUp success`; danach
   `0x06880004[1:0] = 0`, `0x0688000C..0F = 0x60180000`. Kriterien, die scheitern können: **`+0x15F[6:4]` wird 3**
   (Fs-Messung lebt ⇒ sie hing an der APLL) und/oder **`+0x11[6]`/`Audio N`-Zeile** erscheint (Detektor hing an der
   APLL). Bleibt beides aus bei gelockter APLL ⇒ die APLL ist nicht das Gate; Rest liegt bei Quelle/Versorgung.
4. Risiko: die Lock-Schleife `while (rd(apll+8) & 2)` ist unbegrenzt — rastet die APLL nicht ein, hängt der
   **HDMI_SM-Thread** (Bild bleibt, Timing-Änderungen würden nicht mehr verarbeitet, kein ARM-Hänger). Erkennbar: nach
   `PowerUp success!` keine weitere `hdmi_driver`-Zeile und kein `new timing` bei einem Modeset. Rückweg: Neustart.
   Zweitwirkung: `Route(link, 0)` schreibt `+0x160 := 0`, `+0x15E[6:4] := 0`, `+0x4B[1] := 1` — Stock-Default.
Alternative ohne Firmware: die ARM-Seite schreibt die APLL-Register direkt in der Init-Reihenfolge (§2.4) — gleiche
Kriterien, aber ohne Firmware-Log und mit Bitbedeutungen nur aus dem Dekompilat; nur als Ersatz, falls der Poke nicht
gewünscht ist.

---

## 7. Korrekturen zu S17/S18

* S18 §3.1: bei der Aktivierung scheitert `bPdivCalc` (Stage 3), nicht `bXdivCalc`; Stage 0 liefert `TMDS=ffffffff`
  (int(NaN)), Stage 1 „Pass" mit `SPad=-1` — belegt durch alle Mitschnitte.
* S18 §3.3: `0x2006` (und `0x2007/0x2008`) verlangt das Aktiv-Flag, nicht „immer".
* S18 §4.1: `link+0x1D[2:1]` ist Pixelformat aus AVI-Y (`sub_8B140184(link, Y)`: 1 → 01, 3 → 10, 2 → `+0x22[3,1]`),
  nicht „HDMI-Modus"; DVI/HDMI steht in `Port+12`.
* S18 §2: `apll+0xC[31]` wird von `BE54` **vor** der Init/Update-Entscheidung gesetzt; die Entscheidung fällt daher
  praktisch immer auf `Init` (falls das Bit nicht selbstlöschend ist) — die Deutung „1 = programmiert" ist unsicher.
* S18 §4.2: `Init` schreibt xDiv nicht; nur `Update` schreibt `apll+0x18`.
* S17 §5.4: `pll-video3` stand am 07.09. bei 2400 MHz (Dump), am 08.09. bei 1152 MHz (Messung) — beides echt; der
  Wert ist nicht stabil zwischen Boots. Unabhängig davon ist `hdmi-audio` nicht die APLL-Referenz.
* Prämisse des Auftrags: `0x05000000` ist kein RX-Kern-Fenster (§1); die rk3588-Registerkarte ist hier nicht anwendbar.

---

## 8. Offen / vermutet

* Welche Gruppe `+0x05[6]` (dauerhaft gesetzt) meldet — kein Statusbyte-Leser in der Firmware; einmal `+0x00…+0x1F`
  byteweise abziehen (`+0x08/+0x09/+0x0A/+0x14/+0x15`).
* Bedeutung der Nibble-Bits `+0x40[7:4]` und ob der `+0x11[6]`-Detektor in der TMDS- oder Audiotakt-Domäne sitzt —
  entscheidet Stufe C.
* ARM-Lesbarkeit von `0x06880000` (nur Schreibzugriffe belegt).
* Wer `pll-video3` zwischen den Boots umstellt.
* Der 1152-MHz-Takt `hdmi-audio`: Verwendung im RX unbekannt.

---

## 9. Skripte und Rohausgaben

| Skript | Log | Inhalt |
|---|---|---|
| `ida_a70.py` | `audio-rxev-a70-kernfunktionen-20260908.log` | Dekompilate: `HW_EnableIRQs`, `sub_8B13E90C`, `ScanISR_Packet`, Filter, `ISREventHandle`, Poll-Kette, `sub_8B13C4EC`, `BE54`, APLL Init/Update/SetAPLL/PowerDown/PowerUp/Calc, `PD_Reset`, `Get_N_CTS`, Running-Tick, State-Entries/Handler, Aktivierungssequenz, Rohdisassembly `HW_EnableIRQs`/`sub_8B13C4EC` |
| `ida_a71.py` | `audio-rxev-a71-opstabelle-aktivierung-20260908.log` | Ops-Tabelle `0x8b22f280…35c` mit allen Lesern; PreActions; Port_Select/PHY_Reset/IDCLK/DDC; Paketleser `sub_8B13EB58`, `sub_8B1366B4`, AVI; `CreateDeviceHDMI`, `OnHalHdmiARCAudioPathChange` |
| `ida_a72.py` | `audio-rxev-a72-softfloat-objekt-heap-20260908.log` | Soft-Float-Helfer; `THDMIRx_Ctor` (Layout), `DeviceManager_Ctor/GetInstance`, malloc, SM-/Event-Thread, `sub_8B13D1A8` (+0x09), `sub_8B135F74`, `sub_8B1401D4` |
| `ida_a73.py` | `audio-rxev-a73-linkselect-modus-20260908.log` | `g_THDMIRx_LinkPathMode` (Abbild 1) und alle Nutzer; `MAC_Init`, `PHY_EQ_Init`, `HDCP22_GetPkf_AndInit`, `InitAllLinks`, `DataPath_Init`, `ConfigLinkForPort`, `Link_Select`, `SCDC_Detect`, `EQ_RateConfig`; HAL-Tabelle Typ 6 (PortMap) |
| `ida_a74.py` | `audio-rxev-a74-infoframe-ablage-20260908.log` | Rohdisassembly der Aufrufstellen `0x2006`/`0x2005` (`$a2 = ctx+0xBC`), `sub_8B1366B4` roh, `DeviceManager::GetDevice` |

Referenzen: `re/captures/weltneuheit/elog-stock-LIVE.bin` (Stock, DVI-Quelle), `elog-mainline.bin` u. a. (Mainline),
`s16-audio-20260908/elog-audio1-hdmi-ton-ohne-audiozeilen.txt`, `stock-pre/post-hdmi-v2.txt`,
`analyse/hdmi-seq/ccu-dump-after-prep-20260907.txt`, `analyse/hdmi-seq/hdmirx_ctrl_enable.py` (Legacy, nur gelesen).
