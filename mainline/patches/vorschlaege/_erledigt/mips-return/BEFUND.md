# Warum der MIPS BG-Thread den RETURN auslässt — Befund

Unteragent, 07.09.2026, ~17:15–18:30. **Kein Board angefasst** (kein `ssh`, kein `sonoff_ctl`, kein
`scp`, nichts nach `tftp/`, kein `tio`). Kein `git commit`/`push`, kein `sudo`, **nicht gebaut**, kein
podman. Geschrieben wurde nur in dieses Verzeichnis. `doku/78`, `doku/79`, `memory/` nicht angefasst.

| Datei | |
|---|---|
| `BEFUND.md` | dies |
| `0105-soc-sunxi-cpu-comm-stop-reading-the-mips-newcall-ring.patch` | Vorschlag, `diff -ruN`, sha256 `ee44cf60bbc9e5f8e6700aba56e68744b00d4361066e0abe9948570e7c7cb269`, 152 Zeilen |

**Nummer 0105, nicht 0104:** die Serie hat inzwischen **77** Zeilen (sha256
`aa3242b109807f26d016f80137fc04eb20c44488d460550f64a2a33032710540`), und die Hauptsitzung hat
`0104-drm-media-h713-give-the-chroma-gain-one-owner.patch` aufgenommen, nachdem der Auftrag
formuliert war. Der Vorschlag ist gegen **diese** 77er-Serie erzeugt und geprüft.

Sprachregelung wie gefordert: **belegt** = Adresse im Disassemblat oder Datei:Zeile im Quelltext;
**erschlossen** = aus belegten Stücken zusammengesetzt, ohne eigene Messung; **Vermutung** = weder noch.

---

## 0. Die Antwort in fünf Sätzen

Der MIPS lässt den RETURN nicht aus — **er bekommt den Ruf nie zu sehen.** Zwischen dem CALL_ACK
(gesendet von der MIPS-ISR-Seite in `command_action`) und der Abholung durch den BG-Thread liegt der
Ruf als Zeiger in der **NewCall-FIFO des MIPS** (`share_seq(local=MIPS, remote=ARM, dir=0) + 0x20`,
ARM-phys `0x4E3026D8`/`0x4E3026DC`). Diese FIFO hat genau einen Schreiber (MIPS-ISR-Seite) und
genau einen Leser (MIPS-BG-Thread) — **und einen zweiten Leser: uns.** `SendComm2CPUEx` auf dem ARM
ruft unmittelbar nach dem erfolgreichen CALL_ACK `fifo_ItemRdNext((u32 *)(share_seq_w + 32))` auf
(`cpu_comm_proto.c:602`), also `rd++` auf genau dieser FIFO. Kommt unser `rd++` vor dem
`fifo_getItemRd` des BG-Threads, sieht der BG-Thread einen leeren Ring, bekommt `NULL` und legt sich
wieder schlafen: kein `Comm_ReleaseFreeCall` (daher der dauerhaft belegte Slot), kein Handler, kein
RETURN, kein elog. Kommt der BG-Thread zuerst, ist unser `rd++` ein Leerlauf (`rd == wr`).

Der Zeitpunkt unseres `rd++` ist **das Aufwachen aus der ACK-Semaphore** — und das ist exakt die
Größe, die `tx_delay_post_us`, die Konsolenzeilen und der Legacy-Settle verschoben haben. Alles in
C3/C4 Gemessene fällt darunter (§5). Der Fix ist auf der ARM-Seite und besteht darin, die Zeile zu
entfernen (§7).

Damit ist die Frage des Auftrags — *welche Bedingung im Weg des MIPS BG-Threads vom CALL_ACK bis zum
SEND_RETURN lässt ihn den RETURN auslassen* — so zu beantworten: **keine.** Auf dem Weg des
BG-Threads gibt es keine Frist, keine Abbruchschleife und keinen Blick auf ein ARM-Register, der
davon abhinge, was der ARM in den 200 µs tut (§3, §4). Der Weg wird gar nicht betreten.

---

## 1. Material und Methode

* `re/ida/HY310-DEV/display.bin` (2 MiB, md5 `c4a59bc5…`) und `re/ida/IDA_hy310/display.bin.bak`
  (1 256 216 B, md5 `0d2191ca…`) sind **im Codebereich identisch**: erste Abweichung bei Byte
  1 232 745 = `0x8B22CFE9` (Datenbereich). Alle hier zitierten Adressen liegen unter `0x8B180000`.
  Verwendet: das 2-MiB-Abbild, Ladebasis `0x8B100000`.
* Beide IDA-Brücken tot (`ida-headless`: SSE-Verbindung; `ida-pro-mcp`: Binary fehlt). Disassembliert
  mit capstone 5.0.7 (MIPS32 LE) über ein eigenes Skript mit `lui/addiu`-Auflösung und
  String-Annotation (Scratchpad, nicht im Repo). Funktionsnamen stammen aus den elog-Strings, die
  jede Firmware-Funktion beim Eintritt mit Datei, Funktion und Zeile ausgibt — das macht die
  Zuordnung belastbar (`./cpu_comm_core.c`, `./comm_request.c`, `./trid_util_cpucomm.c`).
* ARM-Seite: `mainline/build/linux-6.18.38-5d504188…/drivers/soc/sunxi/cpu_comm/` — byte-gleich mit
  dem 77er-Serienbaum aus dem Trockenlauf (`cmp` auf `cpu_comm_proto.c`, `cpu_comm_api.c`,
  `cpu_comm.h`).

### Die vier Ringe (belegt, beide Seiten)

`getShareSeq(local, remote, dir) = ShMem + 9760·local + 4880·remote + 2440·dir + 0x98` — gleiche
Arithmetik auf dem ARM (`cpu_comm_mem.c:663–669`) und auf dem MIPS (`0x8b1192ac`, Faktoren 9760 /
4880 / 2440 / 0x98 an `0x8b119334`, `0x8b119324`, `0x8b11931c`, `0x8b11932c`). Der Ring gehört dem
**Empfänger** (`local`):

| Ring | (local, remote, dir) | ARM-phys | Wer schreibt Nachrichten hinein |
|---|---|---|---|
| **R_B** | (MIPS, ARM, 0) | `0x4E3026B8` | ARM: CALLs an den MIPS (`getShareSeqW(1,0)`, C4 „ausgehend") |
| R_A | (ARM, MIPS, 0) | `0x4E3013A8` | MIPS: CALLs an den ARM; MIPS-CALL_ACK bei `+104…+119` |
| R_C | (ARM, MIPS, 1) | `0x4E301D30` | MIPS: RETURNs an den ARM (`getShareSeqR(1,1)`, C4 „eingehend") |
| R_D | (MIPS, ARM, 1) | `0x4E303040` | ARM: RETURN_ACK bei `+104…+119` |

In jedem Ring: `+0x08` Status (Bit 2 = SENT), `+0x10` Slot-Index, `+0x20` **NewCall-/ReturnCmd-FIFO**
(Kopf `rd,wr,peak,mode,cap,isz,base`), `+0x78` FreeCall-FIFO, `+0x168` Slots à 104 B.

---

## 2. Der Pfad im MIPS — Adressliste mit Bedingung je Verzweigung (belegt)

### 2.1 ISR-Seite: vom Msgbox-Wort zum CALL_ACK

| Adresse | Was | Verzweigung / Bedingung |
|---|---|---|
| `0x8b122678` | `cpu_comm_cb`: Wort 0 → `jal 0x8b11ef78` | — |
| `0x8b11ef78` | `cpu_comm_handle_CPU2_call(cpu)` | `0x8b11f054` cpu == ich → ASSERT (Endlosschleife `b .`) |
| `0x8b11f060` | `seq_r = getShareSeq(ich, cpu, 0)` = **R_B** | |
| `0x8b11f06c–74` | `R_B[8] & 4`? | **nicht gesetzt → `0x8b11f1d8` „End", nichts weiter** (Störimpuls) |
| `0x8b11f128` | `R_B[0x10] < 20`? | sonst ASSERT Zeile 0xf0 |
| `0x8b11f1b8–c0` | `R_B[8] &= ~4` (Bit löschen) | |
| `0x8b11f1c4–cc` | Rücklesen `R_B[8] & 4` | **noch gesetzt → „End" ohne queueAction** (Einmal-Prüfung) |
| `0x8b11f224` | `queueAction(0, cpu)` → `osa_hisr_activate` (`0x8b11edd4`) | Arbeitsobjekt bei `pDev+0x6d4+32·(4·dir+cpu)`, Felder `+0x18/+0x1c` müssen (dir,cpu) tragen, sonst ASSERT 0xca/0xcb |
| `0x8b1211a0` | `comm_Action`: Typ 0/1 → `command_action`, 2/3 → `ack_action(0x8b11eb70)` | |
| `0x8b120a94` | `command_action(cpu, dir)` | `0x8b120afc` cpu ≥ 2 → ASSERT 0x45 |
| `0x8b120b4c/5c` | `seq_r = R_B`, `seq_w = R_A` | |
| `0x8b120b64–74` | `idx = R_B[0x10]`; `idx < 20`? | **sonst `0x8b120c58`: „pItem->Index=%d >= %d, nonsense!" (Pegel 4), „End", `return` — kein ACK, keine Verarbeitung** |
| `0x8b120bb8–c0` | `R_B[8] & 4` noch gesetzt? | → ASSERT 0x4e (Endlosschleife) |
| `0x8b120be8–f4` | `slot+0x0a |= 8` | |
| `0x8b120c0c` | `slot+2 == ich`? | sonst ASSERT 0x52 |
| `0x8b120d34` | `slot+2 = cpu` (Absender) | |
| `0x8b120e40` | dir == 0 → `0x8b121174` | |
| `0x8b121184` | **`Comm_Add2NewCallFifo(pDev+0x18, R_B+0x20, slot)`** — Rückgabe **verworfen** | |
| `0x8b12118c–9c` | `pDev+4 += 1` (Zähler „empfangene Rufe") | |
| `0x8b120e54–58` | `R_B[0x10] = 20` | |
| `0x8b120e80` | **`SendAckLow(R_A, 20, R_B[8], R_B+0x14, R_B+0x18, R_B+0x1c)`** → CALL_ACK | |

`Comm_Add2NewCallFifo` (`0x8b11d418`):

| Adresse | Was | Bedingung |
|---|---|---|
| `0x8b11d478` | `fifo_getItemWr(R_B+0x20)` | NULL (voll) → „ERROR: New call fifo overflow!" + ASSERT 0x6aa |
| `0x8b11d48c` | **`*wr_slot = slot`** (Zeiger in die FIFO) | |
| `0x8b11d488` | `fifo_requestItemWr` (wr++) | 0 → ASSERT |
| `0x8b11d4a4` | `slot+0x0a |= 0x10` | |
| `0x8b11d4ac–bc` | Schlüssel = `slot[0x10] << 4 \| slot[0] & 0xf` | |
| `0x8b11d4c0` | `QueryChannel(pDev+0x18, key)` (`0x8b11cbc0`) | **NULL → `0x8b11d7b0`: Meldung Pegel 4, Rückgabe −2; Eintrag bleibt in der FIFO, kein Signal** |
| `0x8b11d510/520/540` | `chan+2 == slot[0]`, `chan+8 == slot[0x10]`, `chan+0xc == key` | sonst ASSERT 0x6b8/0x6b9/0x6ba |
| `0x8b11d6dc` | **`osal_semaphore_set(chan+0x10)`** — weckt den BG-Thread | Fehler → ASSERT 0x6be |

### 2.2 BG-Thread: von der Weckung bis zum SEND_RETURN

`BG_Thread` (`0x8b123a40`, `./trid_util_cpucomm.c`; Token `s7`, Index `s6`):

| Adresse | Was | Bedingung |
|---|---|---|
| `0x8b123bf8` | **`Comm_GetCallbyChannel(pDev+0x18, token, &entry)`** | `0x8b123c00` Rückgabe ≠ 0 → ASSERT 0x3b |
| `0x8b123c0c` | **`entry == NULL` → zurück nach `0x8b123bf0` (wieder warten)** | **stiller Weg** |
| `0x8b123c14–1c` | `entry+6 & 8` (CPU_COMM_ATTR_CLOSE_BG_THREAD) | → `0x8b123efc`: Meldung Pegel 3, Token gelöscht, **Thread beendet sich** |
| `0x8b123c7c` | elog „Get a call - chan:%d, pid:%d, SessionID:%x, Attribute:%x, ParaCount:%d, FuncId:%lx" (Pegel 4, Z. 0x45) | |
| `0x8b123c8c` | `memcpy(sp+0x30, entry, 0x68)` | |
| `0x8b123ca4` | `entry+2 < 2`? | sonst ASSERT 0x49 |
| `0x8b123cb4` | `seq = getShareSeq(ich, entry+2, 0)` = **R_B** | |
| **`0x8b123cc0`** | **`Comm_ReleaseFreeCall(R_B, entry)`** — der ARM-Slot kommt in den FreeCall-Ring zurück | intern: `osal_semaphore_get(…, −1)`, `fifo_getItemWr(R_B+0x78)` NULL → ASSERT 0x1af; Slot-Zeiger als phys (`ext 0,29` + `0x40000000`) in kseg1 (`\| 0xa0000000`) geschrieben |
| `0x8b123ccc` | `FindRoutineEx(entry+0x28, &info)` | ≠ 0 → „[S]Find no matched Routine for FuncID:%#lx" (Pegel **1**), Ergebnis 0xf — **RETURN wird trotzdem gesendet** |
| `0x8b123d10–18` | `msg+6 & 1` (NOTIFY) | gesetzt → **kein RETURN, absichtlich** |
| `0x8b123e20` | `jalr handler(&args@sp+0xe8, &result@sp+0x124)` | |
| `0x8b123d20–34`, `0x8b123e30–70` | Ergebniszahl nach `msg+8`, Werte nach `msg+0x2c…` | |
| **`0x8b123d3c`** | **`jal 0x8b12079c` = `j 0x8b11fc2c` mit `a2=−1`: `SendComm2CPUEx(msg, 1 /*Return*/, −1)`** | `0x8b123d44` Rückgabe 0 → Schleife; sonst „[S]Failed to send return, FuncID:%#lx" (Pegel 1, Z. 0x68) → Schleife |

`Comm_GetCallbyChannel` (`0x8b11d81c`, `./comm_request.c`):

| Adresse | Was | Bedingung |
|---|---|---|
| `0x8b11d890` | `chan = QueryChannel(pDev+0x18, token)` | NULL → `0x8b11dc08`: Meldung Z. 0x723, „End", `return 0`, **`*entry` unangetastet** |
| `0x8b11d8a4` | `chan+0xc == token` | sonst ASSERT 0x709 |
| **`0x8b11d958`** | **`osal_semaphore_get(chan+0x10, −1)`** — Warten auf den Ruf, **ohne Frist** | Fehler → ASSERT 0x70d |
| `0x8b11da14` | `osal_semaphore_get(pDev+0x20, −1)` — Geräte-Mutex | Fehler → ASSERT 0x716 |
| `0x8b11dac0–ae0` | *moveNewCallsfromFifo2Chan*, je Fern-CPU 0 und 1 (`0x38(sp)`): `seq = getShareSeq(ich, cpu, 0)`; **`item = fifo_getItemRd(seq+0x20)` (`0x8b117fc0`)** | **`0x8b11dae8`: `item == NULL` (rd == wr) → nächste CPU / fertig** |
| `0x8b11daf4–f8` | `entry = *item` | NULL → ASSERT 0x6f6 |
| `0x8b11dba0` | `chan2 = QueryChannel(key)` | **NULL → `0x8b11de28`: „ERROR!!! no Channel for chan:%d, …" (Pegel 4, Z. 0x6e0) → `0x8b11dd9c` → `fifo_ItemRdNext` — Eintrag verworfen** |
| `0x8b11dbc0/dc9c/dcfc` | `chan2+2/+8/+0xc` gegen Eintrag | sonst ASSERT 0x6d7/0x6d8/0x6d9 |
| `0x8b11dd44–98` | *addNewCall2Chan*: `entry+0x0a |= 0x40`, Listenknoten **im Slot** bei `entry+0x58`, an `chan2+0x18/+0x20`, Zähler `chan2+4` | |
| `0x8b11ddc0` | **`fifo_ItemRdNext(seq+0x20)` (`0x8b1184c4`)** — der legitime `rd++` | ≠ 0 → nächster Eintrag |
| `0x8b11de90–98` | Liste `chan+0x18` leer? | **leer → `0x8b11dfc4`: `v0 = 0` → `0x8b11def0`: `*entry = NULL`, Mutex frei, „End", `return 0`** |
| `0x8b11de9c–ee8` | Knoten aushängen, Zähler−−, `entry = node − 0x58` | Zähler < 0 → ASSERT 0x71d |
| `0x8b11def0–f8` | `*entry = …`; `osal_semaphore_set(pDev+0x20)` | |

### 2.3 Der RETURN selbst: `SendComm2CPUEx(msg, 1, −1)` (`0x8b11fc2c`, `./cpu_comm_core.c`)

| Adresse | Was | Bedingung |
|---|---|---|
| `0x8b11fd48` | `msg == NULL` | → ASSERT 0x1a1 |
| `0x8b11fd4c` | `mode < 2` | sonst ASSERT 0x1a2 |
| `0x8b11fd98–a8` | `dst = msg+2`; **`IsCPUReset(dst)` (`0x8b11a7f4`)** | **≠ 0 → `0x8b11fdf8`: ret = −512, „Return - END, session%x, ret=%d" (Pegel 4), `return` — kein RETURN** |
| `0x8b11fdb0` | `dst < 2` | sonst ASSERT 0x1bb |
| `0x8b11fed4` | `seq_w = getShareSeq(dst, ich, 1)` = **R_C** | |
| `0x8b11fee0–f4` | `sock = getSeq(dst)` (MIPS-privat, `0x8b253a98 + 0x490·cpu`); `sem = sock+0x3e0` | |
| `0x8b11ff00` | `osal_semaphore_get(sem, −1)` | Fehler → ASSERT 0x1c4 |
| `0x8b11ffc4–cc` | **`IsCPUReset(dst)`** erneut | **→ `0x8b12024c`: „CPU is Reset, ret=%d" (Pegel 1), −512, Semaphore frei, `return`** |
| `0x8b11ffd4–dc` | **`isCPUAppReady(dst)` (`0x8b11a5f4`)** | **0 → `0x8b12056c`: „CPU is not Ready, ret=%d" (Pegel 1), −1, `return`** |
| `0x8b120034–50` | **`while (fifo_isNearlyFull(R_C+0x20, 1))`** → Meldung Z. 0x1d9 + `0x8b15b5cc` (schlafen), **unbegrenzt** | blockiert, überspringt nicht |
| `0x8b120058–7c` | Slot-Cache `0x8b2543b8[2·dst+mode]`; leer → `0x8b1204e4`: **`while (!(fp = Comm_GetFreeCall(R_C)))`** Meldung Z. 0x1df + schlafen, **unbegrenzt** | blockiert, überspringt nicht |
| `0x8b12008c` | `memcpy(fp, msg, 0x68)` | |
| `0x8b1200bc–c4` | `fp+4 = idx`, `fp+0x0a = 2`; `fp == R_C+0x168+104·idx`? | sonst ASSERT 0x1f0 |
| `0x8b120204` | dieselbe Prüfung erneut | sonst ASSERT 0x227 |
| `0x8b12030c` | `memcpy(msg, fp, 0x68)` zurück | |
| `0x8b120324–28` | `fp+0x0a |= 4` | |
| **`0x8b120340`** | **`SendCommLow(R_C, idx, msg+6 & 0xff, msg+0xc, sem+4)`** (`0x8b11f8c0`) — **Rückgabe nicht geprüft** | |
| **`0x8b120388`** | **`osal_semaphore_get(sem+4, −1)`** — „WAIT ACK completion" auf RETURN_ACK, **ohne Frist** | Fehler → ASSERT 0x23f |
| `0x8b120444–60` | Cache leeren, Semaphore frei, „got!" | |

`SendCommLow` (`0x8b11f8c0`):

| Adresse | Was | Bedingung |
|---|---|---|
| `0x8b11f934/944/954/95c` | `seq`, `seq[1] == ich`, `seq[2] < 2`, `slot < 20` | sonst ASSERT 0x299/0x29a/0x29b/0x29e |
| `0x8b11f964–6c` | **`R_C[8] & 4` schon gesetzt** | **→ ASSERT 0x29f (Endlosschleife)** |
| `0x8b11fa88–9c` | `R_C[0x10]=slot`, `R_C+4 += 1`, `R_C+0x14 = session`, `R_C+0x18 = sem`, `R_C+0x1c = 0`, `R_C[8] = type` | |
| `0x8b11fb10` | `seq[0] == seq[1]` (lokal) → `queueAction` | |
| `0x8b11fb18–24` | **`R_C[8] |= 4`** | |
| `0x8b11fb28–30` | **Rücklesen `R_C[8] & 4`: 0 → `0x8b11fba0` „End" — kein Msgbox-Wort** (Einmal-Prüfung, `beql`) | |
| `0x8b11fb3c` | `DoIntr2CPU2(seq[2]=1, seq[0]=ARM, 0)` (`0x8b11e8ac`) | |

`DoIntr2CPU2` → `send_u32_to_arm_endpoint` (`0x8b121cb0`) → `arisc_endpoint_send(0x8b2543f4, &wort, 4)`
(`0x8b121870`): Wort = `isAck ? (dir ? 3 : 2) : dir` (`0x8b11e968–990`); **`0x8b12193c–4c`:
`do { v = readl_checked(FIFO_COUNT) } while (v == 8)` — unbegrenzt, keine Zählung, kein Abbruch**;
dann `writel(MSG_DATA, wort)` über `0x8b17fd10`. Beide MMIO-Helfer fragen vorher das Fenster-Gate
`0x8b17f8ec`: `0x03003174` fällt in das Fenster `0x03002000–0x03004fff` (`0x8b17f938–944`) → Rückgabe
0 bei `0x8b17fa58` → Zugriff wird **ausgeführt**. (Nur Adressen außerhalb aller Fenster werden mit
Meldung Pegel 1 und Rückgabe 1 übersprungen, `0x8b17fa40–50`.)

---

## 3. Jede Stelle, an der der RETURN ausbleiben kann — und ob der ARM sie im Fenster erreicht

| # | Stelle | Bedingung im Klartext | Sichtbar? | ARM-Einfluss in den ~200 µs nach dem Türklopfer | Bewertung |
|---|---|---|---|---|---|
| C1 | `command_action 0x8b120b74` | Slot-Index in R_B[0x10] ≥ 20 | Meldung Pegel 4 | R_B[0x10] schreibt der ARM **vor** dem Türklopfer (`SendCommLow`, `proto.c:127` `seq[16] = slot`, Slot ≤ 19 durch `Comm_GetFreeCall`-Prüfung `channel.c:572`) | **scheidet aus: dann käme kein CALL_ACK** |
| C2 | `Comm_Add2NewCallFifo 0x8b11d500` | Kanal zum Schlüssel `pid<<4 \| chan` nicht gefunden | Meldung Pegel 4 | Schlüssel steht im Slot (ARM schreibt ihn vor dem Türklopfer, C4: konstant `0xb8f31600`); Kanaltabelle `pDev+0x18` liegt in MIPS-privatem RAM (`0x8b22f1f4`), ARM hat keinen Zugriff | **scheidet aus** (verzögert nur; s. C3) |
| C3 | `moveNewCallsfromFifo2Chan 0x8b11dbac` | Kanal nicht gefunden → Eintrag **verworfen** | Meldung Pegel 4 | wie C2; `QueryChannel` ist eine deterministische Hash-Suche (`0x8b11cbc0`: 4-Bit-Index aus Bits 0,1,4,5 des Schlüssels, Kette über `+0x28`), dieselbe Eingabe liefert dasselbe Ergebnis | **scheidet aus** (70 % desselben Schlüssels gelingen) |
| **C4** | **`moveNewCallsfromFifo2Chan 0x8b11dae0/dae8`** | **`fifo_getItemRd(R_B+0x20)` liefert NULL, weil `rd == wr`** | **stumm** (nur „End") | **JA: `cpu_comm_proto.c:602` `fifo_ItemRdNext((u32 *)(share_seq_w + 32))` mit `share_seq_w = R_B` — der ARM erhöht `rd` dieser FIFO unmittelbar nach dem Aufwachen aus der CALL_ACK-Semaphore (`proto.c:582–583`)** | **die Antwort — §4** |
| C5 | `BG_Thread 0x8b123c1c` | Attribut Bit 3 (CLOSE_BG_THREAD) im Ruf | Meldung Pegel 3, Thread endet | ARM setzt `+6` auf 0 (`cpu_comm_rpc.c`: `memset` + `&= ~NOTIFY`) | scheidet aus (wäre dauerhaft) |
| C6 | `BG_Thread 0x8b123d18` | NOTIFY-Bit → kein RETURN gewollt | — | ARM löscht es (`rpc.c`) | scheidet aus |
| C7 | `SendComm2CPUEx 0x8b11fda8`, `0x8b11ffcc` | `IsCPUReset(ARM)`: Bit 1 des Wortes `ShMem+0x4CDC` **oder** Magic-Fehler (`0x8b11a8ec` liefert 2) | Pegel 4 bzw. 1 („CPU is Reset") | Das Wort schreibt der ARM nur in `setCPUReady`/`setCPUnotReady` (`cpu_comm_mem.c:176–212`), nicht im Fenster | scheidet aus. **Nebenbefund:** MIPS prüft **Bit 1**, der ARM nennt Bit 1 `NOT_READY` und definiert `CPU_FLAG_RESET = BIT(3)` (`mem.c:88`) |
| C8 | `SendComm2CPUEx 0x8b11ffdc` | `isCPUAppReady(ARM)`: Magic1/2 und Bit 2 des Flag-Wortes (`0x8b11a798–b4`) | Pegel 1 („CPU is not Ready") | nur Init | scheidet aus |
| C9 | `SendCommLow 0x8b11fb30` | Rücklesen von `R_C[8] & 4` nach dem Setzen ergibt 0 | stumm („End") | Einziger ARM-Schreiber auf `R_C[8]` ist `cpu_comm_sync_mips_cache(1,1,8)` (`proto.c:744–768`), das nur auf ein Msgbox-Wort 1 hin läuft — im Fenster liegt keins vor. **Und:** danach wartete der BG-Thread ohne Frist auf ein RETURN_ACK, das nie käme (`0x8b120388`) → der Thread wäre tot, alle Folgerufe verloren | scheidet aus für ein 30-%-Bild |
| C10 | `0x8b17fd10` Gate | Adresse außerhalb der MMIO-Fenster | Pegel 1 | `0x03003174` liegt im Fenster | scheidet aus |
| W1 | `SendComm2CPUEx 0x8b120034` | `fifo_isNearlyFull(R_C+0x20, 1)` — die **ReturnCmd-FIFO des ARM** (ARM füllt sie in `command_action` per `AddReturn2Fifo`, `proto.c:985`, und leert sie in `returnPipeLine`, `channel.c:893ff`) | Pegel 4, **Endlosschleife** | füllt sich nur, wenn der ARM 19 RETURNs nicht abholt | blockiert, überspringt nicht |
| W2 | `SendComm2CPUEx 0x8b120530` | `Comm_GetFreeCall(R_C)` leer — der ARM gibt Return-Slots in `cpu_comm_call_ex` zurück (`rpc.c:721–723`) | Pegel 4, Endlosschleife | C4: eingehender Ring Abstand 1, konstant | blockiert, überspringt nicht |
| W3 | `arisc_endpoint_send 0x8b12193c` | Msgbox-FIFO-Zähler == 8 | stumm, Endlosschleife | ARM leert im IRQ-Handler | blockiert, überspringt nicht |
| A | `SendAckLow 0x8b120840` | `R_A[105] & 4` noch gesetzt, wenn der nächste CALL_ACK raus soll | ASSERT 0x2c2, Endlosschleife | ARM löscht es in `ack_action` (`proto.c:1100`) | **passt zu C4 §4 „Löschen entfernt → −62"**: MIPS quittiert dann nie wieder |

**Fristen auf dem MIPS-Weg: keine.** Alle `osal_semaphore_get` laufen mit `−1` (`0x8b11d954`,
`0x8b11da10`, `0x8b11fef8`, `0x8b12038c`, `0x8b118c28`), die FIFO-Schleifen und die
Msgbox-Zählerschleife haben keinen Zähler. Es gibt nichts, das „nach N nicht mehr sendet".

**ARM-Register liest der MIPS nur eines:** den Msgbox-FIFO-Zähler (`0x8b121934`, Fenster-Basis
`0x03003060 + …`). RX_IRQ_EN, IRQ-Status/W1C, GIC oder CPU-Power-Zustände tauchen im Sendepfad nicht
auf. Dass unser IRQ-Handler RX_IRQ_EN während des Leerens maskiert (`cpu_comm_hw.c:273–282`), ist
für den MIPS unsichtbar. Punkt 4 des Auftrags: **nein.**

---

## 4. Die Bedingung: zwei Leser auf einem Ring mit einem Leser

### Belegt

1. Der ARM schreibt seinen CALL in einen Slot von **R_B** und klopft. Der MIPS legt in `command_action`
   den Slot-Zeiger in **R_B+0x20** ab (`0x8b121180–84` → `0x8b11d48c`, `wr++` bei `0x8b11d488`),
   weckt den BG-Thread (`0x8b11d6dc`) und sendet **danach** den CALL_ACK (`0x8b120e80`).
2. Der BG-Thread holt den Zeiger mit `fifo_getItemRd(R_B+0x20)` (`0x8b11dae0`) und rückt `rd` mit
   `fifo_ItemRdNext` vor (`0x8b11ddc0`). Liefert `fifo_getItemRd` NULL (`rd == wr`, `0x8b117fe8/ff0`),
   bleibt die Kanalliste leer, `Comm_GetCallbyChannel` gibt `*entry = NULL` zurück (`0x8b11dfc4` →
   `0x8b11def0`), und `BG_Thread` geht ohne weitere Meldung zurück ins Warten (`0x8b123c0c`).
3. Der ARM ruft nach erfolgreichem `cpu_comm_sem_down_timeout(sem_ptr+16)` (CALL_ACK)
   **`fifo_ItemRdNext((u32 *)(share_seq_w + 32))`** mit `share_seq_w = getShareSeqW(1, 0) = R_B`
   (`cpu_comm_proto.c:600–603`). Das ist derselbe Ring, derselbe Kopf (`rd` bei `+0x20`), dieselbe
   Operation wie beim BG-Thread. Die ARM-`fifo_ItemRdNext` (`cpu_comm_fifo.c:174ff`) tut bei
   `rd == wr` nichts und rückt sonst `rd` vor.
4. `Comm_ReleaseFreeCall(R_B, entry)` — der einzige Weg, auf dem der ARM-Slot in den FreeCall-Ring
   von R_B zurückkommt — steht im BG-Thread **nach** der Abholung und **vor** allem Weiteren
   (`0x8b123cc0`). Erreicht der Ruf den BG-Thread nicht, bleibt der Slot belegt.
5. Zwischen `SendCommLow` und diesem `fifo_ItemRdNext` schreibt der ARM **nichts anderes** in einen
   Ring oder Slot, den der MIPS liest (durchgesehen: `proto.c:554–603`, `ack_action` schreibt `R_A[105]`,
   der IRQ-Handler nur Msgbox-Register).

### Erschlossen

* **Ordnung → Ausgang.** BG-Thread zuerst: unser `rd++` ist Leerlauf, alles läuft. ARM zuerst: der
  BG-Thread findet nichts, der Ruf ist quittiert, aber nie bearbeitet — kein „Get a call", kein
  Handler, kein RETURN, ein Slot dauerhaft belegt, `unmatched` bleibt 0, nichts im Msgbox. Der Ring
  ist danach konsistent (`rd == wr`), der nächste Ruf läuft normal. Ein Verlust pro Wettlauf, kein
  Folgeschaden außer dem Slot.
* **Zeitpunkt unseres `rd++`.** Er liegt am Ende von `SendComm2CPUEx`, unmittelbar nach dem Aufwachen
  aus der ACK-Semaphore. Schlafen wir in der Semaphore, weckt uns `ack_action` (kworker) Mikrosekunden
  nach dem CALL_ACK; sind wir in `udelay(post)` oder in einer Konsolenzeile, kommt der `rd++` erst
  danach. Der BG-Thread braucht nach dem CALL_ACK seinerseits einige Dutzend Mikrosekunden bis zum
  `fifo_getItemRd` (Weckung aus der Semaphore, Geräte-Mutex, drei bis vier elog-Aufrufe davor —
  jeder einzelne mit Pegel- und Tag-Filter, auch wenn er nichts schreibt; zur Größenordnung: der
  ISR-Pfad mit rund zehn solchen Aufrufen braucht vom Türklopfer bis zum CALL_ACK ~134 µs, C4 §3).
  Zwei Ereignisse gleicher Größenordnung → ein Wettlauf mit ~30 % Verlust ist plausibel; 200 µs
  Vorsprung reichen meist, 1 ms immer. Die Priorität der MIPS-Threads (ISR-Seite vor BG-Thread) habe
  ich **nicht** belegt; der Befund hängt nicht daran.
* **Die Begründung der Zeile trägt nicht.** „MIPS's update via KSEG0 cache never propagates" — wäre der
  `rd` des MIPS für den ARM unsichtbar, dann hätte in jedem Lauf mit eingeschalteter Konsole (unser
  `rd++` kam dort Millisekunden nach dem des BG-Threads, also auf einen leeren Ring: Leerlauf) die
  Prüfung `fifo_isNearlyFull(share_seq_w + 32, 1)` in Schritt 7 (`proto.c:320`) nach 19 Rufen mit
  „DBG1: FIFO nearly full" abgebrochen. C2 meldet 500/500, C3 40/40 mit Konsole. Der MIPS räumt den
  Ring selbst, für uns sichtbar. (Passend dazu greift die Firmware auf den geteilten Speicher über
  kseg1 zu: `Comm_ReleaseFreeCall` bildet Slot-Adressen ausdrücklich mit `\| 0xa0000000`,
  `0x8b118d58`.)
* **Herkunft der Zeile.** Sie stammt aus Sitzung F (18.04.): als Versuch gegen den damaligen
  Slot-Verlust eingebaut und dort als **wirkungslos** protokolliert (`re/notes/HANDOFF-PQD-SESSION-
  20260418-F.md:151`, `re/notes/DEAD-ENDS.md:228–229`), trotzdem in `0014` gelandet
  (`0014-…patch:8565–8567`) mit der neuen Begründung „−EBUSY at 19". Der Slot-Verlust jener Zeit hatte
  eine andere Ursache (BG-Thread stand nach `Vp_Init`-Absturz, `re/notes/CURRENT-TRUTH.md:193`); mit
  stehendem BG-Thread füllte sich die NewCall-FIFO, und unser `rd++` hat genau das verdeckt. Seit der
  BG-Thread läuft, stiehlt dieselbe Zeile Rufe. Das ist eine Deutung der Geschichte, kein Beleg.

---

## 5. Abgleich mit jeder Messung aus C3/C4

| Messung | Erwartung unter §4 | Passt |
|---|---|---|
| Konsole an: 0/40 (C3), Umlauf ~94 ms | drei `pr_info` vor der Semaphore (`proto.c:528–576`) → `rd++` ~8 ms nach dem CALL_ACK → Leerlauf | ja |
| Konsole stumm, dicht: 32/100 (C3), ~30 % (C4) | Wettlauf | ja |
| `post_us` 100/200/500/1000: 7/8 · 4/40 · 2/40 · 0/40 | `rd++` verschiebt sich um `post`, Verlust fällt monoton, bei 1 ms weg | ja |
| `pre_us` 200/1000: 11/20, 15/20 | verschiebt den Türklopfer, nicht den Abstand CALL_ACK→`rd++` | ja |
| 120 ms Pause zwischen Rufen: 15/20 | der Wettlauf liegt innerhalb eines Rufs | ja |
| `dsb(sy)` statt `dmb(ish)`: unverändert | kein Ordnungsproblem, ein Logikproblem | ja |
| Kanalschlüssel konstant, auch bei Fehlern | C2/C3 scheiden aus; Schlüssel spielt keine Rolle | ja |
| `+105`-Löschen entfernt → −62 | MIPS-`SendAckLow` ASSERT 0x2c2 (`0x8b120840`) bei gesetztem Bit → nie wieder ein ACK | ja, unabhängig bestätigt |
| `+105`-Löschen hinter den RETURN verschoben: 20/100 | unabhängig vom Wettlauf | ja |
| Aufrufer-Kern 0/1/3, IRQ-Kern-Spinner: kein Muster | ändert nur Weck-Latenzen um Mikrosekunden, Fenster bleibt | ja |
| Spinner auf allen Kernen: 15/21 | verzögert das Aufwachen nicht um ≥ 200 µs | kein Widerspruch |
| 1-ms-Poll neben dem IRQ: 20/101, FIFO leer | MIPS sendet für den Ruf nichts | ja |
| Slot-Leck **nur** im ausgehenden Ring, 1 je Fehler, dauerhaft | `Comm_ReleaseFreeCall(R_B)` entfällt (`0x8b123cc0`) | ja |
| eingehender Ring Abstand 1 | R_C unberührt | ja |
| `unmatched` 0, keine späte Antwort | es gibt keine Antwort | ja |
| kein elog für den Ruf | nach `command_action` läuft für ihn nichts mehr | ja (zur Totalstille §6) |
| CALL_ACK ~134 µs nach dem Türklopfer | ISR-Pfad, setzt die Zeitskala | ja |
| Legacy `CALL_GAP_MS=500`, „Symptom des FreeCall-Pools" (doku/77:153) | jeder gestohlene Ruf leckt einen Slot; Konsole und Drossel verdeckten es | ja |
| „Init-Sequenz feuert 22 RPCs ohne Pause", zwei der drei Vorfälle darin (C3) | dichteste Rufe des Systems | plausibel, nicht gemessen |

Eine Messung, die **nicht** passt, habe ich nicht gefunden.

---

## 6. Zu den Prüfpunkten des Auftrags

1. **Liest der MIPS im Weg etwas, das der ARM im Fenster schreibt oder nicht schreibt?** Ja, genau
   eines: den Lesezeiger `rd` von R_B+0x20 (`0x8b11dae0`), den der ARM in `proto.c:602` erhöht.
   Nicht gelesen werden: `share_seq_w[8]` (das SENT-Bit löscht der MIPS selbst, `0x8b11f1bc`, der ARM
   schreibt es vor dem Türklopfer), das Wait-Objekt `+8/+32` (die Referenz bei `+0x20` läuft nur durch die
   beiden `memcpy` des BG-Threads, `0x8b123c8c` und `0x8b12008c`, in den RETURN-Slot zurück; kein
   Befehl auf dem Weg dereferenziert sie), `share_seq+105` (MIPS schreibt es, ARM löscht es;
   zeitkritisch erst, wenn der ARM einen ganzen Ruf lang säumt — dann ASSERT, kein stiller Verlust),
   Msgbox-IRQ-Status/-Enable (nie), FIFO-Zähler (nur die Vollschleife W3).
2. **Frist oder Abbruchschleife?** Keine (§3). Der MIPS wartet überall mit `−1`.
3. **elog und RETURN am selben Zustand?** Für den verlorenen Ruf: ja, trivialerweise — beides wird
   nicht ausgeführt, weil der BG-Thread den Ruf nie hat. Die **Totalstille** in C4 §5 (128 Rufe, kein
   einziges Byte, auch nicht die Pegel-4-Zeilen von `command_action`, die jeder Ruf erzeugt) ist ein
   **anderer** Zustand: `elog_output` (`0x8b150068`) kehrt um, wenn `output_enabled` = Byte
   `0x8b48be99` (ARM-phys `0x4b48be99`) null ist (`0x8b150108–140`), oder wenn der Tag-Pegel unter dem
   Meldungspegel liegt (`0x8b150144–150`; bei `0x8b48be98 == 0` gilt der globale Pegel `0x8b48bd9c`,
   sonst die Tag-Tabelle ab `0x8b48bdc0`, `0x8b150cc4–cfc`), oder wenn der Tag den Filterstring ab
   `0x8b48bd9d` nicht enthält (`0x8b150160–168`). C4 schreibt „`0x4b48be98 := 0` per Wort-RMW" — das
   Byte **daneben**, `0x4b48be99`, ist `output_enabled`. Ob es den Wort-Zugriff überlebt hat, weiß nur,
   wer es zurückliest. **Prüfung, die scheitern kann:** `0x4b48be99` muss `01` sein; `0x4b48bd9d` muss
   `00` sein oder ein Teilstring von `cpucomm`. Ist eines davon nicht so, ist die Stille erklärt.
   (Nicht belegt: dass `0x8b1bd654` `strstr` ist — erschlossen aus dem EasyLogger-Aufbau.)
4. **WFI/ARM-Registerzustand?** Nein (§3). Der Kernzustand wirkt nur indirekt: er bestimmt, wie schnell
   der Aufrufer nach dem CALL_ACK wieder läuft — und damit, wann `proto.c:602` zuschlägt.

---

## 7. Der Vorschlag: `0105`

Eine Änderung, ein Zähler:

* **`cpu_comm_proto.c`:** der `else`-Zweig nach dem CALL_ACK ruft `fifo_ItemRdNext(share_seq_w + 32)`
  nicht mehr. An seine Stelle tritt ein **reiner Lesezugriff**: `fifo_getCount(share_seq_w + 32) > 0`
  → `atomic_inc(&cpu_comm_newcall_pending_at_ack)`. Jede Erhöhung ist ein Ruf, den die alte Zeile
  gestohlen hätte.
* **`cpu_comm_api.c` / `cpu_comm.h`:** Zähler definiert/deklariert; `watch` zeigt eine neue Zeile
  `newcall N mal beim CALL_ACK noch ungelesen` direkt unter `calls_out`.

Sonst nichts. `fifo_ItemRdNext` bleibt an seinen legitimen Stellen (ARM-eigene Ringe,
`channel.c:244/275/581/916/956`).

**Trockenlauf — sauber.** Frischer Tarball (`build/cache/linux-6.18.38.tar.xz`) in ein
Temp-Verzeichnis, alle 77 Zeilen der Serie mit `patch -s -p1 -N`: **77 angewandt, 0 fehlgeschlagen,
0 .rej, 18 .orig** (aus der Serie selbst). Die drei betroffenen Dateien sind danach byte-gleich mit
`build/linux-6.18.38-5d504188…`. Dann `0105`: `--dry-run` und echt, **3 Dateien, kein Offset, kein
Fuzz, 0 .rej, keine neue .orig**.

**Nicht geprüft: der Übersetzer.** Der Auftrag verbietet das Bauen. Durchgesehen: `fifo_getCount` ist
in `cpu_comm.h:634` deklariert, `atomic_t` ist in `proto.c` über `cpu_comm.h` verfügbar (dort werden
`cpu_comm_calls_out`/`cpu_comm_timeouts` genauso genutzt), die `scnprintf`-Argumentliste hat ein `%u`
und ein Argument mehr an derselben Stelle.

**Risiko, ausdrücklich:** Wäre die Begründung der alten Zeile doch richtig (MIPS-`rd` unsichtbar),
dann füllt sich R_B+0x20 aus ARM-Sicht und Schritt 7 bricht nach 19 Rufen mit `-EBUSY` und
„DBG1: FIFO nearly full" ab. Das ist ein lauter, sofort erkennbarer Ausfall — und genau die Messung
in §8 Punkt 3.

---

## 8. Messvorschrift für die Hauptsitzung — jede Zeile kann scheitern

Voraussetzung: Kernel mit `0105`, `tx_delay_post_us = 0`, `tx_delay_pre_us = 0`, Konsole stumm
(`/proc/sys/kernel/printk`), frischer Boot, kein `hy310-hdmird`. Rufe über
`/sys/kernel/debug/cpu_comm/call` mit `os.open/os.write/os.close` im `try` (C3-Lehre).

1. **Der Verlust muss weg sein.** 100 dichte `THal_Vp_GetSource` ohne Pause.
   *Bestanden:* `calls_out +100`, `ohne Antwort +0`, kein `no RETURN` in dmesg.
   *Gescheitert:* irgendein `-110`. Dann ist §4 falsch, und `0105` gehört raus. (Vergleich: C3 hatte
   32/100 in genau dieser Anordnung.)
2. **Der Zähler muss den alten Verlust zeigen.** Im selben Lauf muss `newcall … ungelesen` **> 0**
   sein, Größenordnung 20–40 von 100.
   *Bleibt er 0, während Punkt 1 besteht:* dann hat der Verlust aus einem anderen Grund aufgehört als
   dem hier beschriebenen — der Befund wäre in seiner Erklärung widerlegt, auch wenn das Gerät läuft.
   Nachtlog, nicht feiern.
3. **Der Ring darf sich nicht füllen.** ≥ 500 Rufe ohne Pause. *Bestanden:* kein `DBG1: FIFO nearly
   full`, kein `-EBUSY`, `freecall … belegt` konstant, und per `/dev/mem` `0x4E3026D8 == 0x4E3026DC`
   (rd == wr von R_B+0x20) in Ruhe davor und danach.
   *Gescheitert:* `-EBUSY` nach ~19 Rufen — die Begründung der alten Zeile war richtig, §4 falsch.
4. **Gegenprobe mit dem alten Hebel.** `tx_delay_post_us = 1000`, 100 Rufe: `newcall … ungelesen`
   darf **nicht** weiter steigen (der BG-Thread hat den Eintrag längst). Steigt er trotzdem, misst der
   Zähler etwas anderes als gedacht.
5. **Der Hochlauf.** Kaltstart mit stummer Konsole: „Init-Sequenz vollständig (22 Aufrufe)" ohne
   `-110`. Das ist der Zustand, den C3 als „bisher nur mit Konsolen-Drossel" beschreibt.
6. **Nebenbei, ohne neuen Kernel:** die elog-Bytes aus §6.3 zurücklesen (`0x4b48be99`, `0x4b48bd9d`).

---

## 9. Was ich **nicht** belegen konnte

* **Den Wettlauf am Gerät.** Alles in §4 ist aus zwei Quelltexten und den vorliegenden Messungen
  zusammengesetzt; die Reihenfolge der beiden `rd++` hat niemand mitgeschnitten. §8 Punkt 2 ist die
  Messung dafür.
* **Die Prioritäten der MIPS-Threads** (ISR-Seite vor BG-Thread) und die absolute Laufzeit des
  BG-Threads bis zum `fifo_getItemRd`. Erschlossen aus der 134-µs-Zahl; nicht gemessen.
* **Dass der Firmware-Zeiger `0x8b2543d4` (ShMem-Basis) eine kseg1-Adresse ist.** Erschlossen aus der
  `0xa0000000`-Umrechnung in `Comm_ReleaseFreeCall` und aus der Messung (Ring füllt sich nicht bei
  500 Rufen), nicht aus dem Abbild — der Wert wird zur Laufzeit gesetzt.
* **Die Geschichte der Zeile** (§4, letzter Punkt) — plausibel, aber Deutung.
* **Warum der elog in C4 §5 gänzlich schwieg.** §6.3 nennt die drei Bytes, die es entscheiden; gelesen
  hat sie niemand.
* **Dass `0105` übersetzt.** Nicht gebaut.
* **Dass die drei Vorfälle vom 07.09. im Hochlauf denselben Mechanismus hatten.** Passt (22 dichte
  Rufe), ist aber ohne deren dmesg nicht zu zeigen — dieselbe Lücke wie in `callback2/BEFUND.md` §8.
* **Sitzung X (04.05.): „`DoIntr2CPU2 End` geloggt, aber kein `writel(…,1)`".** Statisch gibt es auf dem
  Weg `DoIntr2CPU2 → arisc_endpoint_send → 0x8b17fd10` für `0x03003174` **keinen** überspringenden
  Zweig (das Gate lässt die Adresse durch, die Zählerschleife hat kein Ende). Das steht gegen den
  damaligen Befund, und ich kann den Widerspruch von hier nicht auflösen — die damalige Zählstelle war
  ein Patch im Abbild, dessen Wirkung ich nicht nachgestellt habe.

## 10. Nebenbefunde, gefunden und **nicht** angefasst

* **Bit-Belegung `IsCPUReset`.** MIPS prüft Bit 1 von `ShMem+0x4CDC+4·cpu` (`0x8b11a844` `ext 1,1`),
  der ARM definiert `CPU_FLAG_RESET = BIT(3)` und Bit 1 als `NOT_READY` (`cpu_comm_mem.c:85–88`).
  Ein `setCPUnotReady(0)` auf dem ARM würde vom MIPS als „ARM in Reset" gelesen und jeden RETURN mit
  −512 abbrechen (C7). Heute ruft das niemand. `0014`-Gebiet.
* **Stiller Verlust auf der ARM-Seite.** `cpu_comm_handle_CPU2_return` verwirft ein RETURN-Wort ohne
  Meldung, wenn `R_C[8] & 4` nicht gesetzt ist (`proto.c:744–789`), und schickt dann **kein**
  RETURN_ACK — der MIPS-BG-Thread stünde danach für immer in „WAIT ACK completion" (`0x8b120388`,
  Frist −1). Kein Zähler sieht das. Nicht unser Fall (nichts im Msgbox), aber ein zweiter Weg, auf dem
  „ACK ja, RETURN nie" **dauerhaft** würde. Ein `pr_warn_ratelimited` an der Stelle wäre billig.
* **Rate-limitierte Zählung.** „6 RETURN-Worte für 8 Rufe" (C4 §2) stammt, wenn aus `dmesg`, aus
  `pr_info_ratelimited` in `cpu_comm_msgbox_drain` (`hw.c:235`) — zehn Meldungen je 5 s. Für dichte
  Serien ist das kein Zähler. `msgbox_irq_msgs_drained` (`hw.c:196`) ist einer.
* **Socket-Semaphore mit Umgehung.** `SendComm2CPUEx` gibt die Sende-Semaphore nach 100 ms frei
  („sem timeout, bypassing", `proto.c:298–303`). Zwei gleichzeitige Sender könnten so den Ring
  gleichzeitig beschreiben. Heute gibt es einen Sender. `0014`-Gebiet.
