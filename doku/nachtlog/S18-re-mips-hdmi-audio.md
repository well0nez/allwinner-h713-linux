# S18 (F2) — Was die MIPS-Firmware mit HDMI-Audio tut, und was der ARM davon sehen kann

Auftrag aus [`../100-plan-hdmi-audio.md`](../100-plan-hdmi-audio.md) §3, Frage **F2**. Reine statische Analyse
der `display.bin` mit idalib (IDA 9.1), Arbeitskopie `analyse/ida/db-audio-mips/display.bin.i64`. Kein Board,
kein Zuspieler, nichts unter `mainline/` oder `userspace/`. Stand 08.09.2026, Nachmittag. Dritter Anlauf dieses
Auftrags; die beiden abgebrochenen Anläufe hinterließen `ida_a20.py`…`ida_a27.py` samt Logs — darauf aufgebaut,
nichts wiederholt. Neue Skripte `ida_a28.py`, `ida_a29.py`, `ida_a2a.py`…`ida_a2e.py`, Rohausgaben
`re/captures/weltneuheit/audio-mips-a2*-20260908.log` (Tabelle in §10).

Adressen: MIPS-Code `0x8Bxxxxxx`; Register als **ARM-physische** Adressen (die Firmware rechnet selbst
`+0xB5000000|0x20000000`, `MIPS_MMIO_ReadByte 0x8b17fa60`). `link` = HDMI-RX-Port-Fenster **`0x06840000`**,
`ctrl` = **`0x06800800`**, `apll` = **`0x06880000`**. Dezimale Offsets aus den Dekompilaten sind in Hex umgerechnet.

---

## 0. Antwort zuerst

| Frage | Kurzantwort | Beleg |
|---|---|---|
| **A** Einrasten | Die Firmware behandelt HDMI-Audio **im HDMI-RX-Block selbst und autonom**: 10-ms-Poll der Interruptbytes, bei „N/CTS neu" (Ereignis `0x3000`) liest sie N/CTS/Fs, rechnet die Audio-PLL (`apll` `0x06880000`) aus, setzt Route-/Formatbits und **entstummt den Audioausgang selbst** (`link+0x40[2:0] := 7` über `SetMute(0,0)` aus `AppTopProjector_ConfigSourceRouting`, im elog als `hdmirx set AV mute:0 0`). Kein RPC nötig. **`HdmiRxAEC_Enable` ist kein Audio** (Adaptive-EQ des PHY, `link+0x1B1/0x1B5`). Wohin der Strom geht, entscheidet die Firmware nicht: sie schreibt **nichts** nach `0x0614xxxx`, `0x0670xxxx`, in die PPU oder in CCU-Audio-Register. | §2, §3, §7 |
| **B** ARM-Messpunkte | N `link+0x45..0x47` (20 bit), CTS `link+0x48..0x4A` (20 bit), Fs aus Channel-Status `link+0x56[3:0]`, Fs gemessen `link+0x15F[6:4]`, Audio-Status `link+0x40[7:4]`, Mute `link+0x40[2:0]`, Interruptbytes `link+0x11`/`0x13` (Freigaben `0x10`/`0x12`), Audio-PD `link+0x02[6:5]`, Audio-InfoFrame per Pakettyp `0x84` (Firmware puffert ihn in `port+630`). **Achtung:** das Fenster ist byteweise; `rd.py` (32-bit, ausgerichtet) liefert nur das Byte der ausgerichteten Adresse viermal — für die ungeraden Offsets braucht es einen Byte-Leser (§4.4). | §4 |
| **C** keine Logzeilen | **Nicht** der Log-Level: `Audio N … CTS`, `audio param`, `N change`, `AUDIO PLL CALC` sind Stufe 3 (`I/`) unter den Tags `hdmi_driver`/`hdmirx`, die im Mitschnitt auf Stufe 3 sichtbar sind. Der Pfad wurde **nicht erreicht**: der Mitschnitt reicht bis 2 min 15 s nach dem Einrasten (über die Tonphase hinweg) und enthält weder `0x3000` (N/CTS) noch `0x2006` (Audio-InfoFrame) noch `audio error`. Der Poll lief nachweislich (Zustand 5, Aktiv-Flag gesetzt, `prot:1 set signal ID`). ⇒ Die Audio-Interruptbits der RX-Hardware (`link+0x05[3]` → `link+0x11[6]`) wurden nie gesetzt. Kandidaten §5. | §5 |
| **D** RPC/Rückrufe | RPC-Tabelle kennt nur `TurnOnARCAudioPath` (`93965d14`) und `SwitchARCTXPath` (`e9b4464d`). Beide sind **je ein Bit**: `TurnOnARCAudioPath(flag)` → Hal-Ereignis Typ 4 → `OnHalHdmiARCAudioPathChange 0x8b10b248` → THDMIRx-Slot 34 → **`0x068000A7[0] := flag`**; `SwitchARCTXPath(flag)` → Typ 5 → `OnHalHdmiARCTXPathChange 0x8b10b300` → Slot 80 → **`0x06E00020[0] := flag`** (TVCAP). THDMIRx-vtable (`0x8b1f590c`) sonst: Slot 17 `GetAudioSampleRate` **liefert immer 0**, Slot 37 `SetMute(video,audio)`, Slot 39 `GetAVMuteStatus` (`port+1319`), Slot 57 `SetHandlerOnNewAudioInfoPacket` (Zeiger `0x8b22f288`, wird bei Ereignis `0x2006` gerufen, **kein Registrierer gefunden**), Slot 59 `SetHandlerOnNewACRPacket` (Zeiger `0x8b22f278`, **wird nirgends gerufen**). Einen Rückruf „Audio-Format geändert" zum ARM gibt es nicht. | §6 |
| **E** Empfehlung | Die Firmware **fasst Demod-Bus, Audio-Top und CCU-Audio nicht an** — alle Adressformen geprüft (§7). Der ARM muss also (1) Bus/Takte/Block nach S17 einschalten und (2) davor mit dem Byte-Leser klären, ob der HDMI-RX überhaupt Audio sieht (N/CTS ≠ 0 bei laufendem Ton — mit Positivkontrolle über den 44,1/48-kHz-Wechsel). Sieht er keins, liegt es **vor** dem Audio-Top; Verdächtige (vermutet): `hdmi-audio`-Takt `0xd84` (bei uns 2400 statt 1152 MHz), fehlende Audio-Takt-/PD-Freigabe im RX. Sieht er welches, sollte die Firmware den Rest im RX von allein tun (APLL, Route, Unmute); dann ist die Frage F3 (AUDIF/AUDBRG) dran. | §8 |

Belegt/vermutet: Alles mit Funktionsadresse ist aus dem Dekompilat belegt; Registerbedeutungen sind aus dem
Code-Kontext **abgeleitet** und so markiert; was reine Hypothese ist, steht unter „vermutet".

---

## 1. Was die Vorarbeit (a20–a27) schon hatte, und was fehlte

Vorhanden (Logs `audio-mips-a20…a27`): Stringinventar; Dekompilate von `HdmiRx_Audio_PowerDownAPLL 0x8b13b0dc`,
`PowerUpAPLL 0x8b13b168`, `CalculateDividerSettings 0x8b13b1dc`, APLL-Init `0x8b13b7b0`, `UpdateAPLL 0x8b13baf8`,
`SetAPLL 0x8b13c01c`, `Get_N_CTS 0x8b13c2d4`, `PD_Reset 0x8b13c67c`, `HdmiRx_AEC_Enable 0x8b13cc34`;
`ISREventHandle 0x8b1359e8` mit den Ereigniscodes; `HdmiRx_ScanISR_Packet 0x8b13ef54`; Zustandsmaschine; Basen
`0x06840000`/`0x06800800`; der lui-/Immediate-Scan nach `0x0614xxxx` (0 Treffer, aber nur ARM-phys-Form).

Fehlte: die **APLL-Basis** (`port+184`), der **Setzer des Aktiv-Flags** (`+1325`), die **Mute-Schreiber**
(`loc_8B13E830` liegt mitten in einer Funktion), die **Route-Stubs** (`off_8B1F7914`, IDA hatte sie nicht als Code),
die Frage **Poll oder IRQ**, die **kseg1-Formen** der Adresssuche (`0xBB14…`, `0xB700…`), die vtables mit
Slotzuordnung, der Audio-InfoFrame-Pfad, und der Abgleich mit dem elog-Mitschnitt.

---

## 2. Architektur des HDMI-Audio-Anteils in der Firmware (belegt)

**Objekte.** `THDMIRx` (Ctor `0x8b131958`, vtable `0x8b1f590c`, Typinfo `_ZTI7THDMIRx 0x8b1f58f8`) hält drei
Port-Objekte à 1352 Byte (`THDMIRx_Port_Init 0x8b1380b4`), einen DataPath (`0x8b1323ec`) und den
`DisplayModuleCtx` (`0x8b133010`). Drei Threads: `HDMI_SM` (Zustandsmaschine, 10 ms, `THDMIRx_SM_Loop 0x8b132120`),
`HDMI_Event` (**Interrupt-Poll**, 10 ms, `sub_8B1322A8 0x8b1322a8` → `sub_8B139050` je Port), `HDMI_Hdcp`.

**Port-Objekt, audio-relevante Felder** (Offsets relativ zum Port-Objekt; im ISR-Handler ist `a2 = port+8`):

| Feld | Bedeutung | Setzer |
|---|---|---|
| `+188` | Zustand 1…5 (5 = Running) | `THDMIRx_Port_SwitchState 0x8b138790` |
| `+1301` | „HPD enable" — nur dann läuft `SM_Step` | `THDMIRx_Port_SetHPDEnable 0x8b138398` (aus `Connect_Link_Path`) |
| `+1308`/`+1316` | `link` = `0x06840000` (für alle Ports gleich, `g_HDMIRx_PortBaseAddr 0x8b1f7fc8`) | `Port_Init` |
| `+1325` | **Aktiv-Flag**: gate für Audio-Ereignisse und ISR-Poll | `THDMIRx_Port_SetActiveFlag 0x8b138380` ← `THDMIRx_SwitchPort 0x8b131c00` ← `SetActivePort 0x8b131d14` ← `AfterEnable 0x8b131e4c` |
| `+1319` | AV-Mute-Status (Rückgabe von `GetAVMuteStatus`) | — |
| `+128 … +183` | **Audio-Info** (`info`): `+0` CTS, `+4` N, `+8` Fs (Hz, aus Channel-Status), `+12` Fs (kHz, aus Hardware-Messung), `+16` letzter Audio-Statusnibble, `+20/+24` Fehlerzähler, `+40/+44` (bei `0x3000` genullt), `+48` letztes N, `+52` letztes Fs | `Get_N_CTS`, `sub_8B13C3D8`, `sub_8B13C1D8`, `SetAPLL` |
| `+184` | **APLL-Basis = `0x06880000`** (`return_HDCP_BASE_06880000 `— der Name aus einer früheren Sitzung ist irreführend; `PowerDownAPLL(0x06880000)` wird auch aus `HdmiRx_HDCP22_GetPkf_AndInit 0x8b13e074` gerufen) | `HdmiRx_PHY_ContextReset_Memzero 0x8b139e04` |
| `+630` | Rohpuffer des zuletzt gelesenen **Audio-InfoFrames** (Typ `0x84`) | `sub_8B1366B4 0x8b1366b4` |

**Zwei Basen, ein Fenster.** `THDMIRx_GetControllerBase 0x8b13c858` = `0x06800800`; `sub_8B13C84C` = `0x06841000`
(HDCP-/Paketregister). Beide liegen im HDMI-RX-Adressraum, der bei uns lesbar ist (Registerabzüge
`re/captures/weltneuheit/stock-*-hdmi-v2.txt`, `analyse/hdmi-seq/ours-pre-hdmi-run36.txt`).

---

## 3. Codepfade mit Adressen

### 3.1 Aktivierung eines Ports (einmalig bei `SetSource`)

`THDMIRx_AfterEnable 0x8b131e4c` → `SetActivePort 0x8b131d14` → `SwitchPort 0x8b131c00(active=1)`:

1. `Port_SetActiveFlag(1)` — `+1325 := 1`
2. `THDMIRx_DP_Port_Select 0x8b132590`
3. `THDMIRx_DataPath_Connect_Link_Path 0x8b132b9c` — Port-Select, PHY-Reset, HDCP/DDC-Reset, IDCLK, DDC/HPD an
4. `THDMIRx_DP_Init_Stage1 0x8b132710` — `link+0x1D[6] := 1` (`sub_8B13E850`), `link+0x1D[0] := 1` (`sub_8B13E820`)
5. `THDMIRx_DP_Init_Stage2 0x8b1327ec` → **`sub_8B13C4EC 0x8b13c4ec(link, apll, info)`** — der einzige Audio-Init:
   liest `link+0x15F[6:4]` (Fs-Code) nach `info+12`, schreibt `link+0x02 := 0x27`, `link+0x02[6] := 1`,
   `sub_8B13BE54(apll)` (APLL-Vorbelegung: `apll+4 |= 3`, `apll+0xC |= 0x80000000`, `apll+0x18 &= ~8`),
   `APLL-Init 0x8b13b7b0(apll, {CTS, N, 1000·Fs_kHz})`, dann `link+0x02[6] := 0`, `link+0x02[5] := 0`.
   **Beim Aktivieren sind CTS = N = 0**, `CalculateDividerSettings` rechnet mit Soft-Float 0/0 → `bXdivCalc Failed`
   (elog Stufe 2) → Init kehrt **vor** jedem PLL-Schreibzugriff zurück. Die APLL bleibt bis zum ersten
   `0x3000`-Ereignis unprogrammiert (belegt aus dem Code; im Mitschnitt nicht sichtbar, weil er erst später beginnt).

### 3.2 Zustandsmaschine (`HDMI_SM`, 10 ms) — Audio-Anteile

| Übergang/Zustand | Funktion | Audio-Wirkung |
|---|---|---|
| → Sleep (2) | `THDMIRx_State_Sleep_Entry 0x8b138590` → `Sleep_PreAction 0x8b13e9a8` | IRQ-Freigaben löschen (`sub_8B13E90C(…,0)`), `HdmiRx_AEC_Enable(0)`; wenn Aktiv-Flag: `PowerDownAPLL(apll)` |
| → Idle (3) | `THDMIRx_State_Idle_Entry 0x8b138618` → `Idle_PreAction 0x8b13ea30` | `HdmiRx_AEC_Enable(1)` (**PHY-Equalizer**, nicht Audio: schreibt `link+0x1B5[4]`, `link+0x1B1[4:2]`); wenn Aktiv-Flag: `HdmiRx_Audio_PD_Reset(link)` |
| → TransitionUp (4) | `HdmiRx_State4_HW_EnableIRQs 0x8b13c754` | Interruptfreigaben: `link+0x06 := 0x6A`, **`link+0x10 := 0x4D`** (Audio-Gruppe A), `link+0x12 := 0x06 \| 0x21` (Gruppe B), `0x0C := 0x87`, `0x0D := 0x8F` (Pakete), `0x0B[0]`, `0x16[0]` |
| → Running (5) | `THDMIRx_State_Running_Entry 0x8b1386c0` | TMDS-Reset lösen, `SetMute(1,1)` (`hdmirx set AV mute:1 1`) |
| in 5, jede 10 ms | `THDMIRx_State5_Handler 0x8b138de4` → `sub_8B138D48` → `TimingMonitorTask 0x8b1389ec` (bei neuem Timing: **`PD_Reset`** = `reset system_pd_audio_t!!!`) → `SignalMonitor sub_8B1396FC 0x8b1396fc` (bei stabilem Signal + Aktiv-Flag: `SetMute(0,1)` = Video auf, Audio zu, `SetSignal`) ; danach **`sub_8B139E78 0x8b139e78(info, port+8)`** | `sub_8B139E78`: liest `link+0x40 & 0xF0` (`sub_8B13C648`); hat sich der Nibble geändert → `HdmiRx_Audio_SetAPLL(apll, info)` und `sub_8B13C5B0(link, nibble)` (Route); immer: `sub_8B13C1D8(link, info)` (Fs-Code → `info+12`) |

`SetMute` (THDMIRx Slot 37, `0x8b1311d4` → `sub_8B134690 0x8b134690`): `link+0x1D[0] := !video_mute`,
**`link+0x40[2:0] := audio_mute ? 0 : 7`** (`loc_8B13E830`, roh: `li $v1,7; li $a2,0xF8; movn $a2,$v1,$a1;
addiu $a0,0x40; j WriteByte_Masked; li $a1,7`). Im Mitschnitt: `set AV mute:1 1` (Running-Entry), `0 1`
(SignalMonitor, Tick 5926713), **`0 0`** (Tick 5926734, 21 Ticks später, innerhalb der von `SetSignal` ausgelösten
App-Kette — `AppTopProjector_ConfigSourceRouting` ruft `SetMute(0,0)` bei `GetStatus(source)==1`, Kommentar
am Dekompilat aus einer früheren Sitzung). Der Stock-Abzug bestätigt das Register: `0x06840040` = `0x03` vor,
**`0x07`** nach HDMI (`stock-pre/post-hdmi-v2.txt` Zeile 682). **Per Default ist der Audioausgang also an,
sobald ein Signal steht; ein RPC ist nicht nötig.**

### 3.3 Interrupt-Poll (`HDMI_Event`, 10 ms) und Audio-Ereignisse

Kein Hardware-IRQ: `sub_8B1322A8` ruft alle 10 ms je Port `sub_8B139050 0x8b139050` → `sub_8B136078` (nur wenn
Zustand ≥ 3 **und** Aktiv-Flag) → `HdmiRx_ScanISR_Packet 0x8b13ef54(link)`: liest `link+0x05` (Sammelstatus), dann
gruppenweise die Statusbytes, schreibt den gelesenen Wert zurück (W1C) und reiht Ereignisse ein
(`sub_8B135290` → `hisr_schedule_via_SWI`). Verarbeitung in `ISREventHandle sub_8B1359E8 0x8b1359e8`, davor der
Filter `sub_8B135950 0x8b135950`.

| Sammelbit `link+0x05` | Statusbyte | Bit | Ereignis | Filter | Wirkung in `ISREventHandle` |
|---|---|---|---|---|---|
| `[3]` | **`link+0x11`** (Freigabe `0x10 = 0x4D`) | `[6]` | **`0x3000` „audio param"** | Aktiv-Flag | `Get_N_CTS 0x8b13c2d4` → `info+0/+4`, log `Audio N 0x%x CTS 0x%x`; `sub_8B13C3D8` (`link+0x56[3:0]` → `info+8` Hz); log `audio param:%d %d %d %d %d` (CTS, N, Fs_Hz, Fs_kHz, Byte `info+... `); `info+40/+44 := 0` |
| | | `[2]` | `0x3001` | Aktiv-Flag ∧ Zustand 5 | Zähler `info+20`; ab 11 → log `audio error(0x3001)`, `info` löschen (`sub_8B139D8C`), `PD_Reset` |
| | | `[3]` | `0x3002` | dito | dito |
| | | `[0]` | `0x3005` | Aktiv-Flag | `link+0x40[2] := 1` |
| `[4]` | **`link+0x13`** (Freigabe `0x12`) | `[1]`/`[2]` | `0x3003`/`0x3004` | Aktiv-Flag ∧ Zustand 5 | Zähler `info+24`; ab 11 → log `audio error`, `PD_Reset`, `HdmiRxFixedEQ_Update(4)` |
| | | `[5]` | `0x4003` | — | `link+0x41C[3] := 1` für 1 s (HDCP-nah) |
| | | `[0]` (nur wenn `link+0x422[0]==0`) | `0x4004` | — | `link+0x6A[0] := 1` für 1 s |
| `[2]` | `link+0x0F` (Freigabe `0x0D`) | `[3]` | **`0x2006` Audio-InfoFrame** | immer | `sub_8B1366B4 0x8b1366b4`: Paket Typ `0x84` nach `port+630` lesen (`sub_8B13EB58(link, 0x84, …)`); wenn Aktiv-Flag und Handler `dword_8B22F288` ≠ 0 → Handler(`port+630`) |

Hinweis zur Freigabe: `link+0x06 = 0x6A` gibt Sammelbits 1, 3, 5, 6 frei — Bit 4 (Gruppe `link+0x13`) **nicht**;
ob das Sammelbit unabhängig von der Freigabe gesetzt wird, ist aus dem Code nicht zu entscheiden.

### 3.4 Von N/CTS zur Audio-PLL

`HdmiRx_Audio_SetAPLL 0x8b13c01c(apll, info)`: nur wenn `N ≠ info+48` oder `Fs ≠ info+52` → log
`Audio: N change from … fs change from …, CTS = …`, `sub_8B13BE54(apll)`; ist `apll+0xC[31] == 0` → `Calling Init`
(`0x8b13b7b0`: `PowerDownAPLL`, `apll+0 := 0x0D326667`, `apll+4 := (alt & 0xFFFF01FF) | pDiv<<9 | 0x10`,
`PowerUpAPLL` (`apll+4[0] := 0`, `apll+0x10[2:0] := 3`), warten bis `apll+8[1] == 0`, `apll+4[1] := 0`,
`apll+0xC := 0x40000000 | mInt<<15 | mRem`, dann `| 0x60000000`), sonst `Calling Update` (`0x8b13baf8`: neues
pDiv nach `apll+4[15:9]` mit Strobe `apll+4[7]`, warten bis 0; `apll+0x18 := (alt & ~6) | xDiv<<1 | 8`, log
`@@ update set 0x18 …`, `Updated!`). Eingang ist `{CTS, N, Fs}`; Rechnung in `CalculateDividerSettings`
(Soft-Float, Stufen 0–6 mit Logzeilen). **Alle diese Zeilen sind Stufe 3 und fehlen im Mitschnitt** — die
APLL wurde nach dem Einrasten nie angefasst.

`sub_8B13C5B0 0x8b13c5b0(link, nibble)`: ist `link+0x40[7]` gesetzt → `link+0x160 := 0xFF`, `link+0x15E[6:4] := 1`;
sonst `:= 0` / `:= 0`; danach `link+0x4B[1] := 1` (Übernahme). Vermutet: Bit 7 = „nicht-PCM/komprimiert",
`0x160/0x15E` = Roh- vs. PCM-Route zum Ausgang.

`sub_8B13C1D8 0x8b13c1d8(link, info)` (Route-Stubs `off_8B1F7914`, erzwungen dekodiert, a2a §1): Index
`link+0x15F[6:4]` → `info+12 :=` 0/1 → 0x20, 2 → 0x2C, 3 → 0x30, 4 → 0x58, 5 → 0x60, 6 → 0xB0, 7 → 0xC0 —
**Fs in kHz** (32, 44,1, 48, 88,2, 96, 176,4, 192), von der Hardware gemessen.

`sub_8B13C3D8 0x8b13c3d8` (Channel-Status-Nibble `link+0x56[3:0]` → `info+8` Hz): 2 → 48000, 3 → 32000,
8 → **82000** (Tippfehler der Firmware für 88 200), 9/0xE → 192000, 0xA → **88200** (nach IEC 60958 wäre 0xA = 96 kHz),
0xC → 176400, sonst 44100. Für die eigene Auswertung IEC-Tabelle nehmen, nicht die der Firmware.

### 3.5 `HdmiRx_Audio_PD_Reset 0x8b13c67c` und `link+0x02`

`link+0x02[5] := 1; [6] := 1; [6] := 0; [5] := 0` — Impuls auf zwei Bits („system_pd_audio_t"). Aufrufer:
`TimingMonitorTask` (bei jedem neuen Timing, **unabhängig** vom Aktiv-Flag — das ist die Zeile im Mitschnitt),
`Idle_Entry` (mit Aktiv-Flag), die beiden Fehlerpfade. `sub_8B13D160` pulst `link+0x02[4]` (HDCP-Schlüssel laden).
Nach der Aktivierung steht `link+0x02 = 0x07` (`0x27`, dann Bit 5 gelöscht).

---

## 4. Registerkarte für die ARM-Seite

### 4.1 HDMI-RX-Port-Fenster `link = 0x06840000` (Byteregister)

| Adresse | Bits | Bedeutung | Status | Quelle |
|---|---|---|---|---|
| `0x06840002` | `[6:5]` | Audio-PD/Reset (Impuls durch `PD_Reset`), `[4]` HDCP-Key-Load-Impuls, `[2:0]` bei Aktivierung `=7` | belegt (Bitzweck: abgeleitet) | `0x8b13c67c`, `0x8b13c4ec`, `0x8b13d160` |
| `0x06840005` | `[3]` Gruppe Audio A (`0x11`), `[4]` Gruppe B (`0x13`), `[2]` Pakete (`0x0E/0x0F`), `[0]` Video (`0x07`), `[7]` (`0x17`) | Interrupt-Sammelstatus | belegt | `ScanISR_Packet` |
| `0x06840006` | `= 0x6A` nach Zustand 4 | Sammel-Freigabe | belegt | `HW_EnableIRQs` |
| `0x0684000F` | `[3]` | **Audio-InfoFrame empfangen** → `0x2006` | belegt | `ScanISR_Packet` |
| `0x06840010` | `= 0x4D` nach Zustand 4 (Stock-Abzug post-HDMI: `0x4d`) | Freigabe Audio-Gruppe A | belegt | `HW_EnableIRQs`, `stock-post-hdmi-v2.txt:670` |
| **`0x06840011`** | `[6]` **N/CTS neu** (`0x3000`), `[2]`/`[3]` Audio-Fehler (`0x3001/0x3002`), `[0]` (`0x3005`) | Audio-Status A, W1C durch die Firmware alle 10 ms | belegt | `ScanISR_Packet` |
| `0x06840012` / `0x13` | Freigabe / Status Gruppe B: `[1]`/`[2]` Fehler (`0x3003/4`), `[5]` (`0x4003`), `[0]` (`0x4004`) | | belegt | dito |
| `0x0684001D` | `[0]` Video-Mute (1 = an), `[6]` (`sub_8B13E850`, bei Init 1), `[2:1]` HDMI-Modus (`sub_8B140184`) | | belegt | `0x8b13e820/e850` |
| **`0x06840040`** | **`[2:0]` Audioausgang: 7 = an, 0 = stumm** (`SetMute`); `[2]` wird bei `0x3005` einzeln gesetzt; **`[7:4]` Audio-Statusnibble** (Änderung → `SetAPLL`+Route; `[7]` vermutet nicht-PCM) | Stock: `0x03` → `0x07` nach HDMI; **mit `rd.py` lesbar** (ausgerichtet) | belegt | `loc_8B13E830`, `sub_8B13C648`, Abzüge |
| **`0x06840045..47`** | `N = b45 \| b46<<8 \| (b47&0xF)<<16` | ACR N | belegt | `Get_N_CTS` |
| **`0x06840048..4A`** | `CTS = b48 \| b49<<8 \| (b4A&0xF)<<16` (`0x48` mit `rd.py` lesbar: Abzüge zeigen `0x18` = Reset-Wert) | ACR CTS | belegt | `Get_N_CTS` |
| `0x0684004B` | `[1]` Übernahme-Strobe nach Route-Änderung | | belegt | `sub_8B13C5B0` |
| **`0x06840056`** | `[3:0]` Fs-Code aus dem Channel-Status (IEC 60958 Byte 3) | | belegt | `sub_8B13C3D8` |
| `0x0684015E` | `[6:4]` Route (1 = roh) | vermutet | `sub_8B13C5B0` |
| **`0x0684015F`** | `[6:4]` **gemessener Fs-Code** 0/1=32, 2=44,1, 3=48, 4=88,2, 5=96, 6=176,4, 7=192 kHz | belegt (Kodierung aus Stubs) | `sub_8B13C1D8` |
| `0x06840160` | `= 0xFF` roh / `0x00` PCM | vermutet | `sub_8B13C5B0` |
| `0x068401B1`, `0x068401B5` | AEC (**PHY-Equalizer**), `0x1B5[4]` = AEC an | belegt — kein Audio | `HdmiRx_AEC_Enable` |
| `0x0684037A` | `[3:0]` Signal-Valid je Port | belegt | `THDMIRx_Port_IsSignalValid` |
| `0x0684041C` `[3]`, `0x0684006A` `[0]`, `0x06840422` `[0]` | HDCP-nahe Bits um `0x4003/0x4004` | belegt, nicht Audio | `sub_8B13DF60/D2D0` |

Audio-InfoFrame: keine festen Statusbytes bekannt; die Firmware holt das Paket über den Paketleser
`sub_8B13EB58(link, typ, ziel)` (Selektor `link+0x112`, Daten ab `link+0x1C0`; Typ `0x84`) und legt es in `port+630`
(`0x4B…`-SRAM des Port-Objekts — Adresse zur Laufzeit, nicht statisch).

### 4.2 Audio-PLL `apll = 0x06880000` (32-bit-Worte, byteweise geschrieben, Bitbedeutung abgeleitet)

| Wort | Bits | Bedeutung | Quelle |
|---|---|---|---|
| `+0x00` | | Konstante `0x0D326667` bei Init | `0x8b13b7b0` |
| `+0x04` | `[1:0]` Reset (PowerDown schreibt `0x50000003`), `[4]` Init, **`[7]` Update-Strobe** (selbstlöschend, wird gepollt), `[15:9]` pDiv | `0x8b13b0dc`, `b168`, `b7b0`, `baf8` |
| `+0x08` | `[1]` busy/lock — nach Init gewartet bis 0 | `0x8b13b7b0` |
| `+0x0C` | **`[31]` = 1 wenn programmiert** (`SetAPLL` entscheidet daran Init/Update), `[30]`, `[29]`, `[23:15]` mInt, `[14:0]` mRem | `0x8b13c01c` |
| `+0x10` | `[2:0] := 3` PowerUp | `0x8b13b168` |
| `+0x18` | `[3]` (Update setzt, Vorbelegung löscht), `[2:1]` xDiv | `0x8b13baf8`, `0x8b13be54` |

Ob dieses Fenster vom ARM aus lesbar ist und wortweise antwortet, ist **nicht belegt** (kein Abzug vorhanden;
`doku/72` erwähnt „Wrapper-Nullen (Basis 0x06880000)" aus dem Legacy-Modul — also hat der ARM dort schon
geschrieben, ohne Hänger).

### 4.3 Abgeleitete Kriterien für die Messung

* **„Audio-Pakete vorhanden"**: `N`/`CTS` ≠ 0 und `CTS` ≈ `f_TMDS·N/(128·Fs)` (1080p60: `f_TMDS` 148,5 MHz,
  48 kHz → N 6144, CTS 148 500 = `0x24414`; 44,1 kHz → N 6272, CTS 148 500 — Positivkontrolle: **N** muss beim
  Wechsel 44,1 ↔ 48 kHz am Zuspieler springen, CTS nicht). Ohne Ton: N = CTS = 0 bzw. Reset-Werte (`0x48` = `0x18`).
* **Fs**: `0x15F[6:4]` (gemessen) und `0x56[3:0]` (gemeldet) müssen übereinstimmen und dem Zuspieler folgen.
* **Kanäle/Format**: nur aus dem Audio-InfoFrame (CC in PB1 `[2:0]`, CT `[7:4]`, SF PB2 `[4:2]`, CA PB4) — kein
  Statusregister gefunden; alternativ `0x40[7]` (roh) als Grobindikator.
* **Mute**: `0x40[2:0] == 7`.
* **Interruptbits** (`0x11`, `0x13`) sind vom ARM nur mit Glück zu sehen, weil die Firmware sie alle 10 ms löscht;
  taugen als Zusatz, nicht als Kriterium.

### 4.4 Zugriffsbreite — wichtige Falle für `rd.py`

Die Abzüge des Port-Fensters zeigen für jedes 32-bit-Wort das **Byte der ausgerichteten Adresse viermal**
(`0x06840040: 0x03030303 → 0x07070707`, `0x0684000c: 0x87878787` = die von `HW_EnableIRQs` an `link+0x0C`
geschriebenen `0x87`, `0x06840010: 0x4d4d4d4d` = `0x4D` an `link+0x10`). `rd.py` liest ausgerichtete Worte über
eine `c_uint32`-Sicht — damit sind nur `0x40`, `0x44`, `0x48`, `0x10`, … erreichbar, **nicht** `0x45/46/47/49/4A/56/5F/11/13/05/02`.
Für die Messung braucht die Hauptsitzung einen Byte-Leser (gleiches Muster wie `rd.py`, `c_uint8`-Sicht):

```python
# rdb.py ADDR [ADDR…] — Byteregister lesen (Device-Speicher, daher ctypes-Sicht statt memcpy)
import ctypes, mmap, os, sys
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC); maps = {}
def view(a):
    b = a & ~0xfff
    if b not in maps:
        m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=b)
        maps[b] = (m, (ctypes.c_uint8 * 4096).from_buffer(m))
    return maps[b][1]
for s in sys.argv[1:]:
    a = int(s, 16); print("0x%08x: 0x%02x" % (a, view(a)[a & 0xfff]))
```

Ob ein Byte-Zugriff auf dieses Fenster vom ARM aus sauber geht, ist unbelegt — die Wortzugriffe gingen
(Abzüge), und die Firmware selbst greift ausschließlich byteweise zu (`sb`/`lbu`).

---

## 5. Warum keine `Audio N/CTS`-Zeilen (Frage C)

**Log-Filter ausgeschlossen (belegt).** `elog_output 0x8b150068` verwirft, wenn `elog_get_filter_tag_lvl(tag) < level`
(`sub_8B150C98`). Stufen: 0 assert, 1 error, 2 warn, **3 info (`I/`)**, 4 debug (`D/`), 5 verbose. Alle Audio-Zeilen
sind Stufe 3 unter `hdmi_driver` (N/CTS, N change, PLL CALC, PD_Reset, AEC) bzw. `hdmirx` (`audio param`,
`audio error`). Der Mitschnitt `s16-audio-20260908/elog-audio1-hdmi-ton-ohne-audiozeilen.txt` zeigt Stufe-3-Zeilen
beider Tags (`reset system_pd_audio_t!!!`, `port1 new timing …`). Pro-Tag-Level lassen sich mit
`elog -l <tag> <level>` setzen (`0x8b1fb0e8`, MIPS-Shell nach doku/98) — nötig ist es nicht.

**Zeitfenster reicht (belegt).** Einrasten bei Tick 5925980…5926734 (Uptime 1 h 38 min 46 s); der Mitschnitt endet bei
Tick 6060617 (1 h 41 min 00 s) mit ausschließlich `D/sys`-Uptime-Zeilen alle 5 s. Datei gespeichert 12:18:24; der Ton
lief laut S16 12:16:49 und 12:17:31–12:18:11 — also **innerhalb** des Fensters. Zwischen `prot:1 set signal ID`
und dem Ende: keine einzige Zeile aus `hdmi_driver`/`hdmirx`.

**Poll lief (belegt).** `SwitchState 3→4→5`, `set AV mute:0 1` und `prot:1 set signal ID:0x20000` (Tick 5926734)
kommen nur mit Aktiv-Flag `+1325` zustande (`SignalMonitor`, `if (*(a6+1317))`); damit war auch
`ScanISR_Packet` alle 10 ms aktiv, und die Filter für `0x3000`/`0x2006` waren offen.

**Folgerung.** Die Hardware hat in > 2 Minuten mit Ton am Kabel weder `link+0x11[6]` (N/CTS) noch `link+0x0F[3]`
(Audio-InfoFrame) noch die Fehlerbits gesetzt. Kandidaten (vermutet, in absteigender Plausibilität):

1. **Audio-Takt des RX fehlt/falsch.** `hdmi-audio` (CCU `0xd84`) läuft bei uns aus `pll-video3-4x` mit Teiler 1 =
   **2400 MHz** statt Stock **1152 MHz** (S17 §1). Die Audio-Detektion (ACR-Zähler, Channel-Status, Fs-Messung)
   sitzt im Audiotaktbereich des RX; ein grob falscher Takt kann den Bereich still lassen. Die Firmware selbst
   programmiert diesen Takt nicht (§7). **Erste Maßnahme des ARM: `0xd84` auf die Stock-Konfiguration** (S17).
2. **Zuspieler sendet keine Audio-Pakete.** Statisch nicht entscheidbar; die Registerprobe aus §4.3 trennt beides:
   N/CTS ≠ 0 ⇒ Pakete kommen an.
3. Audio-PD im RX (`link+0x02[6:5]`) hängt — unwahrscheinlich, PD_Reset lief und die Bits werden gelöscht.
4. Der Audio-FIFO des RX staut, weil der Abnehmer (AUDIF am Demod-Bus) tot ist — würde Datenfehler, aber kaum das
   Ausbleiben der ACR-Erkennung erklären.

Nicht Ursache: Log-Level, Aktiv-Flag, Zustandsmaschine, Mute (Audio war nach `0 0` entstummt).

---

## 6. RPCs, vtable-Slots, Rückrufe (Frage D)

**cpu_comm-Tabelle** (`mainline/docs/reference/cpu-comm-call-table.md`, nur gelesen): audio-bezogen nur
`93965d14 TurnOnARCAudioPath` und `e9b4464d SwitchARCTXPath`. Kein `SetMute`, kein `GetAudioSampleRate`, kein
`SetHandlerOnNewAudioInfoPacket` als RPC — diese sind interne vtable-Methoden.

**THDMIRx-vtable `0x8b1f590c`** (Slot k ↔ `THDMIDummy`-vtable `0x8b1f5538` + 4k liefert die Namen; belegt über
`AfterEnable` Slot 11, `SetMute` Slot 37, `GetAudioSampleRate` Slot 17 — drei unabhängige Treffer):

| Slot | Offset | Name (aus Dummy) | THDMIRx-Implementierung | Wirkung |
|---|---|---|---|---|
| 17 | +68 | `GetAudioSampleRate` | `sub_8B131024 0x8b131024` | **liefert immer 0** (ruft `sub_8B138348`, verwirft das Ergebnis) |
| 34 | +136 | *(namenlos, Dummy `nullsub_8`)* | `sub_8B130974 0x8b130974` | `0x068000A7[0] := arg` — **das ruft `OnHalHdmiARCAudioPathChange 0x8b10b248`** (`hal_func.cpp`, per `dynamic_cast<IDeviceHdmi>`); vermutlich ARC-TX-Pfad an/aus |
| 36 | +144 | `IsVideoStable` | `sub_8B130D28` | — |
| 37 | +148 | **`SetMute(video, audio)`** | `THDMIRx_SetMute 0x8b1311d4` | `link+0x1D[0]`, **`link+0x40[2:0]`** (§3.2) |
| 39 | +156 | `GetAVMuteStatus` | `sub_8B131288 0x8b131288` | `port+1319` |
| 54 | +216 | `SetHandlerOnNewAVIPacket` | `sub_8B130B80` | Zeiger `0x8b22f274`, gerufen bei `0x2005` |
| 57 | +228 | **`SetHandlerOnNewAudioInfoPacket`** | `sub_8B130B88 0x8b130b88` | Zeiger **`0x8b22f288`**, gerufen bei **`0x2006`** mit `port+630` (Audio-InfoFrame) — **kein Aufrufer des Slots gefunden**; im `.bss`, zur Laufzeit prüfbar (`0x4B22F288`) |
| 59 | +236 | **`SetHandlerOnNewACRPacket`** | `sub_8B130B90 0x8b130b90` | Zeiger `0x8b22f278` — **wird nirgends gelesen** (toter Haken) |
| 61/63/65 | +244/252/260 | GC/VSI/SPD-Handler | `sub_8B130B98/BA0/BA8` | Zeiger `0x8b22f27c/280/284`, gerufen bei `0x2003/0x2002·0x2009/0x2004` |
| 80 | +320 | *(namenlos, Dummy `nullsub_9`)* | `sub_8B1309BC 0x8b1309bc` | `0x06E00020[0] := arg` (TVCAP-Fenster) — **das ruft `OnHalHdmiARCTXPathChange 0x8b10b300`** |

**Weg der ARC-RPCs (belegt, a2d/a2e).** Die `THal_Vp_*`-Sender (`0x8b148334 ff.`) reihen `{Typ, Wert}` über
`sub_8B106BEC` beim App-Objekt `0x8b253570` (vtable+12) ein; die Typen sind fortlaufend (0 BacklightWorkMode,
1 PwmInfo, 2 BacklightLevel, 3 HDCP22Key, **4 TurnOnARCAudioPath**, **5 SwitchARCTXPath**, 6 PortMap,
7 ReloadHdcp14Key, 8 HPDInterval, 9 Init, 11…15 Black/Freeze/Cover, 17…29 PQ, 30…34 ATV, 35 Seamless). Die
`OnHal*`-Tabelle `0x8b22f058` (Stride 8, `{Handler, 0}`) ist genau danach indiziert: `+0x00` BacklightWorkMode,
`+0x08` PwmInfo, `+0x10` BacklightLevel, `+0x18` `OnHalHdmiHDCP22KeyChange`, **`+0x20` = `0x8b22f078`
`OnHalHdmiARCAudioPathChange`**, **`+0x28` `OnHalHdmiARCTXPathChange`**, `+0x30` PortMap, `+0x38`
RELOADHDCP14KEY, `+0x40` SetHPDInterval — neun Einträge in Folge passend, das ist keine Zufallsdeckung. Beide
Handler holen `DeviceManager->GetDevice(3)`, casten nach `IDeviceHdmi` und rufen den Slot mit `(wert != 0)`:

* `TurnOnARCAudioPath(flag)` (RPC `93965d14`, Adapter `0x8b10ac84`) ⇒ **`0x068000A7` Bit 0 := flag** (HDMI-RX-Ctrl-Bereich).
* `SwitchARCTXPath(flag)` (RPC `e9b4464d`) ⇒ **`0x06E00020` Bit 0 := flag** (TVCAP-Fenster `0x06E00000`).

Keiner der beiden berührt Audio-Top, CCU oder den HDMI-Audio-Empfangspfad — ARC ist ein Rückkanal zum
Fernseher-Ausgang und laut Plan außerhalb des Ziels. (`OnCommonEvent 0x8b1089b4` Fall 4 „seamless" ist ein
anderer Ereignisraum — die App-Warteschlange, nicht die Hal-Tabelle; Typ 35 der Hal-Tabelle ist Seamless.)

**Rückruf zum ARM „Audio-Format geändert": gibt es nicht.** Die Rückrufliste der Tabelle (Signal-Change,
Display-Latency, HPD-by-Port) enthält nichts mit Audio; der Audio-InfoFrame-Handler ist ein MIPS-interner
Funktionszeiger, kein cpu_comm-Rückruf.

`dwUseDoubleSampling` (`0x8b10e964`, `tse_init_data`) ist ein TSE-Misc-Parameter (`0xB0001` → Config-Schlüssel) —
Video (Double-Sampling), nicht Audio.

---

## 7. Fasst die Firmware Demod-Bus, Audio-Top, TVFE-Top, PPU oder CCU-Audio an? — Nein (belegt)

Suche `ida_a29.py` über das **ganze** Segment `0x8b100000–0x8b232b18`, drei Formen: (A) `lui`-Paare mit dem
folgenden `addiu/ori/lw/sw/li` desselben Registers, (B) von IDA zusammengefasste `li`-Immediates, (C) alle
Datenwörter — jeweils für ARM-phys **und** kseg1 (`+0xB5000000`: `0xBB14…`, `0xBB70…`, `0xB7001…`, `0xBC001…`).
Kontrolle: dieselbe Suche findet die bekannten HDMI-RX-Konstanten (`0x06800800`, `0x06840000` ×4 im
`g_HDMIRx_PortBaseAddr`, `0x06841000`, `0x0684037A`, …), die kseg1-Formen `0xBA0C0000`/`0xBA000000` der
DE-Schreiber und den einzigen CCU-Zugriff — das Instrument zeigt also positiv.

| Bereich | Treffer | Bedeutung |
|---|---|---|
| Audio-Top `0x06140000–0x0615FFFF` (AUDIF/AUDBRG/DSP-Mailbox) | **0** (phys + kseg1, Code + Daten) | Firmware kennt den Block nicht |
| TVFE-Top `0x06700000` | **0** | dito |
| PPU `0x07001000` | **0** | keine Domänenschaltung |
| ARM↔MIPS-Mutex `0x02031078/0x02032078` | **0** | kein DSP-Protokoll im MIPS |
| CCU `0x02001000–0x02001FFF` | **1**: `readl_checked(0x02001DB4) & 1` in `sub_8B15C070` (Pixeltakt 74,25/148,5 MHz) | nur Lesen, kein Audio-Gate, kein `0xd64/d48/d4c/d50/d84` |

Einschränkung: tabellengetriebene Schreiber (TSE-Initialtabellen, `write_init_table`) laufen über die
Modul-Schreibfunktionen der Anzeigekette, deren Basen alle fest im Code stehen (`0xBA00…`, `0xBA0C…`); ein
versteckter Weg nach `0x0614…` ist damit nicht ausgeschlossen, aber nichts deutet darauf. Zur Laufzeit gebaute
Adressen aus `.bss` kann eine statische Suche nicht sehen.

Damit ist auch klar: der Hänger beim Einschaltversuch des Demod-Busses (S16/S17) kann **nicht** durch einen
Konflikt mit der Firmware entstanden sein — sie berührt weder Bus noch Block.

---

## 8. Empfehlung und Messplan (Frage E)

Reihenfolge für die Hauptsitzung, jeder Schritt mit einem Kriterium, das scheitern kann:

1. **Vorher**: Byte-Leser (§4.4) auf das Board; Kontrolle am bekannten Wert: `rdb 0x06840040` muss `0x07`
   liefern, solange das Bild steht, `rdb 0x06840010` `0x4d`. Liefert er anderes, ist der Byte-Zugriff nicht
   vertrauenswürdig — dann erst `rd.py 0x06840040` (Wortform `0x07070707`) als Ersatz.
2. **Sieht der RX Audio?** Ton am Zuspieler an, 48 kHz: `rdb 0x06840045 46 47 48 49 4a 56 5f 40`. Kriterium:
   N = `0x1800` (6144), CTS ≈ `0x24414`, `0x56[3:0] = 2`, `0x5F[6:4] = 3`. **Positivkontrolle:** Zuspieler auf
   44,1 kHz → N `0x1880` (6272), `0x56 = 0`, `0x5F = 2`. Bleibt alles 0/Reset-Wert (`0x48 = 0x18`) ⇒ Kandidat 1
   aus §5 zuerst: `hdmi-audio` `0xd84` nach S17 auf Stock-Parent/-Teiler, dann Schritt 2 wiederholen.
   (Der Weg über das elog ist gleichwertig: sobald `0x3000` kommt, erscheinen `Audio N … CTS …`, `audio param`,
   `N change`, `AUDIO PLL CALC`.)
3. **Erst dann** Demod-Bus/Audio-Top nach S17 einschalten (das ist der Hänger-Kandidat) und F3 (AUDIF-Status,
   SPDI-Eingang) messen. Was der RX an seinem Audioausgang liefert, entscheidet die Firmware allein (APLL, Route
   `0x160/0x15E`, Unmute); ein ARM-RPC ist nicht vorgesehen und keiner vorhanden.
4. Optional, wenn der Audio-InfoFrame gebraucht wird (Kanäle, CA): Laufzeitprüfung `0x4B22F288` (Handler
   registriert?) und `port+630` — Adresse des Port-Objekts über `THDMIRx+236` (Ports 1…3) aus `0x4B…`-SRAM.

Was der ARM **nicht** tun muss: AEC schalten, APLL programmieren, Mute lösen, IRQs freigeben — alles Firmware.

---

## 9. Offen / vermutet

* Bedeutung der Bits `link+0x40[7:4]` (Audio-Statusnibble) und `0x160/0x15E` — nur aus dem Kontext abgeleitet.
* Byte-Zugriff vom ARM auf das Port-Fenster: belegt sind nur Wortzugriffe (Abzüge).
* `0x06880000` (APLL) vom ARM lesbar? Kein Abzug; Legacy-Modul hat dort geschrieben („Wrapper-Nullen").
* Ob der Audio-InfoFrame-Handler (`0x8b22f288`) zur Laufzeit gesetzt ist — statisch kein Registrierer; am Board
  `0x4B22F288` lesen.
* Firmware-Tabellen für Fs enthalten Tippfehler (`82000`, `0xA → 88200`); für eigene Auswertungen IEC-Tabelle.

---

## 10. Skripte und Rohausgaben

| Skript | Log | Inhalt |
|---|---|---|
| `ida_a20.py`…`ida_a27.py` (Vorarbeit) | `audio-mips-a20…a27-*.log` | Strings, Kernfunktionen, ISR, Basen, lui-Scan (ARM-phys), Port-Init, Aktiv-Flag-Leser |
| `ida_a28.py` | `audio-mips-a28-aktivflag-apllbasis-20260908.log` | `SwitchPort`, `port+184` = `0x06880000`, Ctor/AfterEnable, Mute-Schreiber, Poll-Kette, Event-Thread, vtables |
| `ida_a29.py` | `audio-mips-a29-adressformen-20260908.log` | Adresssuche phys+kseg1+Daten für Audio-Top/TVFE/CCU/PPU/Mutex, CCU-Zugriffe dekompiliert |
| `ida_a2a.py` | `audio-mips-a2a-route-vtable-regkarte-20260908.log` | Route-Stubs erzwungen dekodiert, `DP_Init_Stage1/2`, `Connect_Link_Path`, Handler-Slots, `+1301`-Setzer, Typinfo, **vollständige Registerkarte** aller Byte-Zugriffe `0x8b12e000–0x8b144000` |
| `ida_a2b.py` | `audio-mips-a2b-handler-arc-elog-20260908.log` | Handler-Zeiger `0x8b22f27x/288` und ihre Leser, Tabellen mit `OnHalHdmiARCAudioPathChange`, `OnCommonEvent` Fall 4, `elog_output`-Filter, Paketkonfiguration |
| `ida_a2c.py` | `audio-mips-a2c-audioinfoframe-20260908.log` | Ereignis `0x2006` = Audio-InfoFrame (`0x84`), Zuordnung der Paket-Ereignisse, Aufrufstellen der Handler |
| `ida_a2d.py` | `audio-mips-a2d-arc-weg-20260908.log` | Ereignistypen aller `THal_`-Sender, `OnHal*`-Tabelle `0x8b22f058`, `hal_adapter_init` |
| `ida_a2e.py` | `audio-mips-a2e-arctx-20260908.log` | `OnHalHdmiARCTXPathChange` → Slot 80 → `0x06E00020[0]`; `THal_Vp_SwitchARCTXPath` |

Referenz-Mitschnitt: `re/captures/weltneuheit/s16-audio-20260908/elog-audio1-hdmi-ton-ohne-audiozeilen.txt`;
Registerabzüge `re/captures/weltneuheit/stock-pre-hdmi-v2.txt`, `stock-post-hdmi-v2.txt`,
`analyse/hdmi-seq/ours-pre-hdmi-run36.txt` (Port-Fenster nur bis `0x068400FC`).
