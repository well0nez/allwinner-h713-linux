# S10 - Warum die MIPS-Firmware nach dem 20. Rückruf in `cmdfifo.type=0` hängt

08.09.2026, 00:30-02:30 · reine Analyse (Agent) · Fortsetzung von [`C5`](C5-rpc-ursache-behoben.md) und
[`CALLBACK-luecke`](CALLBACK-luecke.md) · Anlass: Hänger nach dem Rückruf `MipsHalCallback_SignalChange`
Session `0x40000014` (Post-mortem 00:20)

**Rahmen:** Board **nicht** angefasst, nichts unter `mainline/patches/` geändert. IDA nur auf Kopien in
`analyse/ida/db-cpucomm/` (`display.bin.i64`, `cpu_comm_dev.ko.i64`); Skripte `analyse/ida/ida_q67.py` - `ida_q70.py`.
Post-mortem-Material: `shm-kipp.bin` (5 MiB ab ARM-phys `0x4E300000`), `postmortem-kipp-cpucomm.txt`,
`postmortem-kipp-dmesg.txt`, `elog-run3-switch-kipp.txt`, `elog-run1-720to1080.txt` (Scratchpad, nicht dauerhaft).

---

## Das Ergebnis zuerst

Der Verdacht stimmt in der Sache und ist im Detail schärfer als vermutet:

1. **Der MIPS steckt nicht in `Comm_GetFreeCall`, sondern eine Prüfung davor.** Die Zeile
   `cpu_comm_core.c:473 cmdfifo.type=0, target cpu=0` ist die Warteschleife
   `while (fifo_isNearlyFull(share_seq_w + 32, 1)) { elog; yield; }` in `SendComm2CPUEx` (`0x8b11fc2c`).
   `share_seq_w + 32` ist die **CallCmd-/NewCall-Ringliste des ARM-eigenen ShareSeq (0,1,0)** bei
   ARM-phys `0x4E3013C8`. Sie steht im Abzug auf **rd=0, wr=19** - Schwelle `cap−1−margin = 21−1−1 = 19` erreicht,
   Schleife terminiert nie. Der FreeCall-Pool desselben ShareSeq hat noch **einen** freien Slot (rd=19, wr=20);
   die Pool-Erschöpfung („free call,type=%d", Zeile 479) wäre erst beim nächsten Ruf gekommen.
2. **Beide Zähler wachsen aus demselben Grund:** unser `command_action()` legt für Rufe mit `chan ≤ 4`
   per `Comm_Add2NewCallFifo()` nur eine *Referenz* in die Ringliste und weckt einen Kanal, den niemand liest.
   Im Stock-Protokoll holt ein **Kanalleser** den Eintrag ab (`Comm_GetCallbyChannel` rückt `rd` vor), kopiert
   ihn und gibt den Slot mit `Comm_ReleaseFreeCall()` zurück. Diesen Leser gibt es im Mainline-Treiber nicht -
   auf dem Stock-ARM war es der ioctl `0xC0087F03`, auf dem MIPS ist es `BG_Thread`.
3. **`MipsHalCallback_SignalChange` ist ein NOTIFY** (Flags `+6 = 0x0001`): der MIPS erwartet **keinen RETURN**,
   nur den CALL_ACK (den wir senden) und irgendwann die Rückgabe des Slots. Ein RETURN auf ein NOTIFY würde
   den MIPS in einem `ASSERT` (`command_action` Zeile 119) endlos schleifen lassen - also **nie** „sicherheitshalber"
   antworten.
4. **Zahlen:** seit dem Kaltstart 19 Rückrufe (Sessions `0x40000001…13`, `rx_calls 19`), alle 19 Einträge im
   Pool (0,1,0) belegt, 19 Referenzen ungelesen im Ring. Der 20. (`0x40000014`) hängt. Die „16" des
   Handler-Zählers sind nicht die Vergleichsgröße (siehe §7).
5. **Fix (Skizze in §5):** im `≤ 4`-Zweig statt `Comm_Add2NewCallFifo()` das tun, was der fehlende Leser täte -
   Kopie (liegt schon vor), nach dem ACK `Comm_ReleaseFreeCall(share_seq_r, entry)`, RETURN nur wenn
   `!(flags & NOTIFY) || (flags & RETURN_ACK)`. Kein Ring-Eintrag, kein Slot-Leck.

---

## 1. Frage A - welche Firmware-Funktion, welche Schleife, warum terminiert sie nicht

### 1.1 Die Funktion

Der String `cmdfifo.type=%d, target cpu=%d` (`0x8b1ef2c8`) hat genau einen Verweis: `0x8b11fff0` in
**`sub_8B11FC2C` = `SendComm2CPUEx`** (Firmware-Quelle `./cpu_comm_core.c`, Argumente `(msg, type)`,
`type 0 = CALL, 1 = RETURN`; Wrapper `sub_8B12079C(msg, type)` = `SendComm2CPUEx(msg, type, -1)`).
Das ist die Sendefunktion - dieselbe Vendor-Routine, die unser `SendComm2CPUEx` in `cpu_comm_proto.c` portiert.

### 1.2 Die Schleife (Dekompilat, gekürzt, Adressen aus `ida_q67.py`)

```c
// sub_8B11FC2C @ 0x8b11fc2c - SendComm2CPUEx(msg a1, type a2)
elog(412/414, "%s - ENTER, session%x", ...);                     // "Call - ENTER, session40000014"
if (type == CALL && FindRoutine(*(u32*)(a1+40), &rt))  return -3; // 425 "ERROR: not find routine"
tgt   = rt.target_cpu;                                          // v4 = 0 (ARM)
seqW  = getShareSeq(tgt, myCPU, type);                          // sub_8B1194C0 -> ShareSeq(0,1,0) fuer CALL an ARM
sock  = getSeq(tgt);                                            // sub_8B1194EC -> 0x8B253A98 fuer cpu0
sem   = type ? sock+992 : sock+8;                               // CALL-Sende-Semaphore 0x8B253AA0
osal_semaphore_get(sem, -1);   elog(452, "osal_semaphore_get()->_r=0, sem = 8B253AA0");
if (!isCPUAppReady(tgt)) { ret=-1; goto out; }                  // 976 "cpu0 - is APPready"

/* ---- HIER haengt es ---- */
while (fifo_isNearlyFull(seqW + 32, 1)) {                       // sub_8B117F30(&CallCmd-Ring des Empfaengers, margin 1)
    elog(473, "cmdfifo.type=%d, target cpu=%d", type, tgt);     // 0x8b11fff0
    osal_thread_yield();                                        // sub_8B15B5CC: SWI-Reschedule, kein Schlaf
}
/* erst danach: */
slot = cache[2*tgt+type] (0x8B2543B8);                          // Sende-Slot-Cache
if (!slot) while (!(slot = Comm_GetFreeCall(seqW))) {           // sub_8B118ABC, Pool seqW+120
    elog(479, "free call,type=%d,target cpu=%d", type, tgt); yield(); }
memcpy(slot, a1, 104); ... session = (myCPU<<30)|++0x8B2543C8;  // 0x40000014
elog(543, "Session%x(CALL): %s, tgetCPU=%d, chanId=%d, Pid=%x, Index=%d", ...);
slot->flags2 |= 4 (SENT); SendCommLow(...);                     // Tuerklopfer
elog(570, "WAIT ACK completion"); osal_semaphore_get(ack_sem);  // 575/607
cache[2*tgt+type] = 0;  osal_semaphore_set(sem);                // 620
```

`fifo_isNearlyFull` (`sub_8B117F30 @ 0x8b117f30`) ist exakt unsere `fifo_isNearlyFull`:

```c
BOOL sub_8B117F30(u32 *f, int margin) {            // f[0]=rd f[1]=wr f[4]=cap
    int cnt = f[1] - f[0]; if (cnt < 0) cnt += f[4];
    return margin >= f[4] - cnt - 1;                // <=> cnt >= cap - 1 - margin  = 19 bei cap 21
}
```

Die „Warte"-Funktion `sub_8B15B5CC` (`0x8b15b5cc`, Disassembly in `ida_q70.py`-Ausgabe) setzt nur
`0x8B232C04 = 1` und löst über `Cause.IP0` einen Software-Interrupt aus (ThreadX-artiger Reschedule); im
ISR-Kontext gibt sie `0x060E0007` zurück. Es ist also ein **Yield ohne Schlaf**: gleichrangige Threads kommen
dran, niedrigere nie, und die CALL-Sende-Semaphore `0x8B253AA0` bleibt die ganze Zeit **gehalten**.

### 1.3 Warum sie nicht terminiert

Die Schleife prüft nicht den FreeCall-Pool, sondern die **Ringliste `ShareSeq(0,1,0) + 32`** („CallCmd", ARM-phys
`0x4E3013C8`). Die füllt auf dem ARM ausschließlich `Comm_Add2NewCallFifo()` (Referenz je eingehendem
`≤ 4`-Ruf) und leert ausschließlich der Kanalleser (`Comm_GetCallbyChannel` → `fifo_ItemRdNext`). Ohne Leser:
`rd` bleibt 0, `wr` zählt die Rufe. Bei `wr − rd = 19` ist die Schwelle erreicht - für immer.

Normaler Ablauf zum Vergleich (elog Session `0x4000000f`, Z. 242 ff.): nach `976 cpu0 - is APPready` folgt
**direkt** `543 Session…(CALL)` - **keine** 473-Zeile. Die Zeile erscheint nur, wenn die Schwelle steht.

### 1.4 Folgen im Gerät (was das Post-mortem dazu sagt)

* Die Sende-Semaphore für CALLs an cpu0 ist gehalten. RETURNs des MIPS an den ARM nehmen zwar eine
  andere Semaphore (`sock+992`), aber:
* Die beiden ARM→MIPS-Rufe `0x2e`/`0x2f` (die `-110`) liegen im **MIPS-Ring `ShareSeq(1,0,0)+32`** ungelesen
  (`rd=3, wr=5`), ihre Einträge tragen `flags2 = 0x1d` (SENT|received|dispatched): die MIPS-ISR-Seite hat sie
  quittiert und eingereiht, **der BG_Thread hat sie nie abgeholt**. Das passt zu einem Yield-Spinner in einem
  Thread höherer Priorität als BG_Thread/Debug-Shell (vermutet, §6).
* Die elog-Zeitmarken laufen in der Schleife weiter (`2685155 → 2685179`), der Timer-Interrupt lief also
  zumindest anfangs; „Tick steht" ist damit nicht aus meinem Material entscheidbar.

---

## 2. Frage B - Pool-Größe, wer gibt frei, was steht in den Flags

### 2.1 Layout und Größe (belegt aus `cpu_comm_mem.c`, MIPS-`Comm_GetFreeCall`, Abzug)

`getShareSeq(local, remote, dir) = ShMem + 152 + 9760·local + 4880·remote + 2440·dir`; **local = Besitzer =
Empfänger**, remote = Sender, dir 0 = CALL, 1 = RETURN. Je ShareSeq: `+32` CallCmd/ReturnCmd-Ring (Kopf im
Shmem, Items im Socket des Besitzers), `+120` FreeCall/FreeReturn-Ring (Kopf und Items im Shmem, physische
Adressen), `+360` **20 Einträge à 104 Byte**. Ring-`cap = 21` → **20 nutzbare Slots je Richtung und Paar**
(`InitCommShareSeqMem` füllt 20, MIPS-`Comm_GetFreeCall` asserts `index < 0x14`).

| ShareSeq | ARM-phys | Bedeutung |
|---|---|---|
| (0,1,0) | `0x4E3013A8` | **MIPS → ARM CALL** (Rückrufe). Pool gehört dem ARM; MIPS entnimmt, **ARM gibt zurück** |
| (0,1,1) | `0x4E301D30` | MIPS → ARM RETURN (Antworten auf unsere Rufe); ARM gibt zurück (`cpu_comm_call_ex`, `rpc.c:721`) |
| (1,0,0) | `0x4E3026B8` | ARM → MIPS CALL. Pool gehört dem MIPS; MIPS gibt zurück (BG_Thread). Das ist der Ring aus C4/C5 und aus `watch` |
| (1,0,1) | `0x4E303040` | ARM → MIPS RETURN |

Der Sender prüft vor jedem Ruf `fifo_isNearlyFull(Empfänger-ShareSeq+32, 1)` und entnimmt dann aus
`Empfänger-ShareSeq+120`; `Comm_ReleaseFreeCall` verlangt `seq[0] == eigene CPU` (MIPS `0x8b118b84` Z. 426,
ARM `cpu_comm_channel.c:612`) - **nur der Empfänger darf zurücklegen.**

### 2.2 Wer gibt den Slot frei - drei Belege

**(a) MIPS als Empfänger (`BG_Thread_entry @ 0x8b1239e4`, Spiegelbild dessen, was wir tun müssten):**

```c
for (;;) {
    Comm_GetCallbyChannel(pool 0x8B254428, token, &call);   // 0x8b11d81c: down(chan+16); moveNewCallsfromFifo2Chan:
                                                            //   liest getShareSeq(me,i,0)+32 fuer i=0,1, haengt Eintraege in
                                                            //   die Kanalliste, fifo_ItemRdNext(ring)  <- rueckt rd vor
    if (call->flags2 & 8 /*CLOSE*/) break;
    elog(69, "Get a call - chan:%d, pid:%d, SessionID:%x, Attribute:%x, ParaCount:%d, FuncId:%lx");
    memcpy(local, call, 104);
    Comm_ReleaseFreeCall(getShareSeq_self(call->src_cpu, 0), call);  // 0x8b118b84, elog 424..437 (sem 8B253E20)
    if (FindRoutine(local.comp, &rt)) { result[0]=15; elog(92,"[S]Find no matched Routine"); }
    else { elog(87,"[S]Find matched Routine"); rt.fn(&params, &result); }
    if (!(local.flags & 1 /*NOTIFY*/)) {                    // Attribute-Bit 0
        if (result[0] != 15) { local.ParaCount = result[0]; copy result -> +44.. }
        if (SendComm2CPUEx(local, RETURN)) elog(104, "[S]Failed to send return");
    }
}
```

Genau diese Abfolge steht im elog für jeden ARM→MIPS-Ruf (`comm_request.c 1805/1812/1814 → 1743/1745 → 1766 →
trid_util_cpucomm.c 69 → comm_request.c 424/429/436/437 → 1174 → …87 → Return - ENTER`).

**(b) Stock-ARM-Treiber `cpu_comm_dev.ko` (`ida_q69.py`):** `Comm_GetCallbyChannel @ 0x80d8` hat **einen**
Aufrufer, `cpu_comm_ioctl @ 0xdd0`, Fall **`0xC0087F03`**:

```c
get_user(token);
Comm_GetCallbyChannel(pcpu_comm_dev+48, token, &entry);     // blockiert in down_interruptible(chan+16)
if (entry) {
    entry->flags2 |= 0x80;
    IsCPUReset(entry->src) || copy_to_user(user, entry, 104);
    Comm_ReleaseFreeCall(getShareSeqR(entry->src /*+2*/, 0), entry);   // <- Freigabe durch den Empfaenger, im Leser
} else { /* Kanal geschlossen: 104-Byte-Satz mit Attribute 8, Comm_RemoveChannel */ }
```

Der RETURN kommt danach aus dem Userspace (Fall `0xC0087F01` → `SendComm2CPU`). `Comm_ReleaseFreeCall @ 0x3c40`
hat dort drei Aufrufer: dieser ioctl (Slots aus `getShareSeqR(cpu,0)` = eingehende CALLs `≤ 4`),
`comm_CallWorkAction @ 0x102c8` (CALLs `> 4`, „copy → release → FindRoutine → run → RETURN wenn verlangt"), und
`CPUComm_CallEx @ 0x10614` (RETURN-Slots `getShareSeqR(cpu,1)`). **Für `≤ 4` gibt es im Stock keine andere
Freigabe als den Leser-ioctl.** Im Mainline-Zielbaum existiert weder `0xC0087F03` noch ein anderer Aufrufer
von `Comm_GetCallbyChannel` (grep: nur die Definition) - und `cpu_comm_user_read()` liefert Kopien aus
`cpu_comm_userspace_deliver()`, ohne je einen Slot anzufassen.

**(c) Stock-`command_action @ 0xdbf8`** macht für `≤ 4` nur `Comm_Add2NewCallFifo(pool, ShareSeqR+32, entry)` und
dann `SendAckLow` - **kein** Release; das ist Sache des Lesers. Unser `command_action` ist hier stockgetreu
portiert, nur der Leser fehlt.

### 2.3 Die Flags der Rückruf-Einträge (`+6`, Abzug, alle 19 identisch)

```
+0 chan=0  +2 dst=1(*)  +4 idx=n  +6 flags=0x0001  +8 ParaCount=2  +10 flags2=0x001d
+12 session=0x400000nn  +16 chan_pid=0  +32/+36 wait=0  +40 comp=0x3e7fbc46  +44.. p1=1|3, p2=0x4e332000, ...
(*) +2 haben wir selbst auf remote_cpu=1 ueberschrieben (command_action)
```

* `+6 = 0x0001 = MSG_FLAG_NOTIFY`, Bit 1 (`RETURN_ACK`) **nicht** gesetzt. Im MIPS-`SendComm2CPUEx` gilt
  `if ((flags & 1) == 0 || (flags & 2)) { Wartobjekt anlegen, +32/+36 setzen } else { +32 = +36 = 0 }` - für
  unsere Rückrufe wird **kein Wartobjekt** angelegt (im Abzug `+32 = 0`), der Sender wartet nur auf den
  **CALL_ACK** (elog `570 WAIT ACK completion` → `CallACK handler` → Ende) und gibt danach die Semaphore frei.
  Dieselbe Bedingung steht in unserem `comm_CallWorkAction` (`!(msg[6]&1) || (msg[6]&2)`).
* **Warnung:** MIPS-`command_action` (`0x8b120a94`) für ein eingehendes RETURN ohne `RETURN_ACK`-Bit asserted, wenn
  das Wartobjekt bei `+32` null ist (Z. 119, `while(1)`). Ein RETURN auf ein NOTIFY hängt die Firmware.
* `+10 = 0x1d` = `0x04 SENT` (MIPS) | `0x08 received` | `0x10 dispatched` (beides wir) | `0x01`(MIPS `msg_type`
  „local call"). `0x40`/`0x80` („in Kanalliste"/„abgeholt") fehlen - der Eintrag ist nie abgeholt worden.

**Antwort B in einem Satz:** 20 Slots je Richtung; den Slot eines MIPS→ARM-Rufs gibt der **ARM als Empfänger**
über `Comm_ReleaseFreeCall(getShareSeqR(1,0), entry)` zurück, im Stock aus dem Kanalleser nach der Kopie; der
Ring `+32` wird vom selben Leser geräumt; für `SignalChange`/`HotPlug` (NOTIFY) ist **kein RETURN** vorgesehen.

---

## 3. Frage C - der Abzug (`shm-kipp.bin`), Leck bestätigt

Alle acht ShareSeqs geparst (Skript im Scratchpad, Layout wie in §2.1). Die vier unbeteiligten
(`(0,0,*)`, `(1,1,*)`) sind jungfräulich (`rd=0, wr=20`, Ringe leer).

| ShareSeq (phys) | CallCmd/ReturnCmd `+32` | FreeCall/FreeReturn `+120` | belegt |
|---|---|---|---|
| **(0,1,0) `0x4E3013A8`** MIPS→ARM CALL | **rd=0 wr=19** (19 ungelesen, `peak 19`) | **rd=19 wr=20** cap 21 → **1 frei** | **19** Einträge idx 0…18, Sessions `0x40000001…13`, alle `comp 0x3e7fbc46`, `flags 0x0001`, `flags2 0x1d` |
| (0,1,1) `0x4E301D30` MIPS→ARM RETURN | rd=3 wr=3 (leer) | rd=3 wr=2 → 20 frei | 0 (Einträge zeigen alte Sessions `0x1a…0x2d`, `flags2 0`) |
| (1,0,0) `0x4E3026B8` ARM→MIPS CALL | rd=3 **wr=5** (2 ungelesen) | rd=5 wr=2 → 18 frei | 2: idx 5/6 = Sessions **`0x2e`/`0x2f`** (`flags2 0x1d`) - die beiden `-110` |
| (1,0,1) `0x4E303040` ARM→MIPS RETURN | leer | rd=0 wr=20 | 0 |

Kopf (0,1,0): `+8 = 01`, `+16 seq_idx = 20` (von uns zurückgesetzt), `+20 = 0x40000013` (letzte zugestellte
Session), `+105 = 01`, `+112 = 0x80001398`.

**Arithmetik.** `rx_calls 19` (watch) = 19 Einträge = 19 Ring-Referenzen = Sessions 01…13. Der 20. Ruf
(`0x40000014`, elog Z. 1474) trifft auf `wr−rd = 19 = cap−1−margin` → Endlosschleife **vor** der Slot-Entnahme.
Der Pool hätte für genau diesen Ruf noch Slot 19 (`0x4E301CC8`) gehabt; erst der 21. wäre am Pool gescheitert
(„free call", Z. 479). Die Schätzung „16 verlorene Slots + Pool 21" stimmt daher nicht - richtig ist
**19 verlorene Referenzen ≥ Schwelle 19**, und der Pool ist um 19 von 20 geleert. Beides ist dasselbe Leck.
„Kippen nach vier bis fünf Wechseln" (doku/97 §3b) mit ~3-4 Rückrufen je Wechsel landet bei ~19 - **passt**,
ist aber damit nicht bewiesen.

Warum `watch` das nicht zeigt: `freecall rd=5 wr=2 cap=21, belegt 3` liest **`getShareSeqW(1,0)` = (1,0,0)**, den
ausgehenden Pool (C4/C5-Thema). Der hier maßgebliche ist **`getShareSeqR(1,0)` = (0,1,0)** und dessen Ring `+32`.
`dmesg` bestätigt außerdem `userspace_deliver … ctx_count=0` bei jedem Ruf: kein `/dev/cpu_comm` war offen.

---

## 4. Frage D - was im Mainline-Treiber fehlt

### 4.1 Der Pfad heute (`cpu_comm_proto.c`, `command_action`, Zielbaum Z. 893 ff.)

```
IRQ msgbox → cpu_comm_msg_cb → cpu_comm_handle_CPU2_call → queueAction → schedule_work
  → comm_WorkAction → comm_Action → command_action(remote_cpu=1, dir=0)     [Prozesskontext, Workqueue]
      entry = share_seq_r + 360 + 104*seq_idx      share_seq_r = getShareSeqR(1,0) = (0,1,0)
      entry+10 |= 8; entry+2 = remote_cpu
      cpu_comm_userspace_deliver(entry)   -> Kopie in fd-Queues (kmalloc)
      cpu_comm_kernel_deliver(entry)      -> memcpy_fromio in local[], Handler laeuft
      if (entry_cmd <= 4) Comm_Add2NewCallFifo(pool, share_seq_r+32, entry)   <- Ring+1, up(Kanal 0x1), NIEMAND liest
      else                Comm_Add2Call2WQ(entry)   -> comm_CallWorkAction: memcpy, Comm_ReleaseFreeCall, RETURN wenn verlangt
      share_seq_r+16 = 20; SendAckLow(...)
```

Für `> 4` ist alles da (`rpc.c:1034`). Für `≤ 4` fehlt **beides**: das Vorrücken von `rd` im Ring (`+32`) und
`Comm_ReleaseFreeCall` auf `(0,1,0)`. Der Kommentar über `cpu_comm_userspace_deliver()` („without this entry_cmd<=4
messages … sit in the channel FIFO unread") beschreibt die Ursache bereits, zieht aber nicht die Folgerung.

`Comm_Add2NewCallFifo` braucht den Eintrag **als Zeiger** (legt `cc_ref(entry)` in den Ring); beide Zustellungen
arbeiten auf **Kopien**. Nach der Zustellung wird der Shmem-Eintrag also von niemandem mehr gebraucht - außer
vom MIPS-Sender bis zum CALL_ACK, und der liest ihn danach nicht mehr (`memcpy(a1, slot)` passiert vor dem
Türklopfer; nach `607 … got!` nur `cache = 0`, `sem set`).

### 4.2 Minimale, protokollgetreue Ergänzung (Vorschlag - **nicht angewendet**)

Reihenfolge wie im Stock-Leser (Kopie → Freigabe) und wie Stock-`command_action` (ACK zuerst; die Freigabe
kam dort *später* aus dem Leser-Thread, hier also nach `SendAckLow`). Der Ring `+32` wird nicht mehr befüllt,
also braucht er auch kein `rd++`. `Comm_ReleaseFreeCall` darf schlafen (Semaphore) - Workqueue-Kontext ist in
Ordnung, `comm_CallWorkAction` tut dasselbe.

```diff
--- a/drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c
+++ b/drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c
@@ void command_action(u32 remote_cpu, u32 direction)
 	unsigned long entry_base;		/* virtual address of the call entry */
 	u16 component_id;
 	u32 session_id;
+	u8 local_msg[COMM_MSG_SIZE] __aligned(8);
+	bool release_call = false;
@@
-		if (entry_cmd <= 4)
-			Comm_Add2NewCallFifo(
-				(void *)((u8 *)pcpu_comm_dev + 48),
-				(u32 *)(share_seq_r + 32),
-				entry_base);
-		else
+		if (entry_cmd <= 4) {
+			/*
+			 * Stock legt hier nur eine Referenz in den CallCmd-Ring
+			 * (share_seq_r + 32) und weckt den Kanal; abgeholt, kopiert
+			 * und mit Comm_ReleaseFreeCall() zurueckgegeben wird der
+			 * Eintrag erst vom Kanalleser (Stock-ARM: ioctl 0xC0087F03,
+			 * MIPS: BG_Thread). Diesen Leser gibt es hier nicht, die
+			 * Zustellung oben arbeitet auf Kopien. Ohne Leser waechst der
+			 * Ring, und der MIPS-Sender dreht ab 19 Eintraegen in
+			 * fifo_isNearlyFull(share_seq + 32, 1) endlos; der Slot bleibt
+			 * belegt (S10). Also tun wir, was der Leser taete.
+			 */
+			memcpy_fromio(local_msg, (const void __iomem *)entry_base,
+				      COMM_MSG_SIZE);
+			release_call = true;
+		} else
 			Comm_Add2Call2WQ((void *)entry_base);
@@
 	/* Reset sequence index and send ACK */
 	*(u8 *)(share_seq_r + 16) = 20;
 	SendAckLow((void *)share_seq_w,
 		   *(u8 *)(share_seq_r + 16),
 		   *(u8 *)(share_seq_r + 8),
 		   *(u32 *)(share_seq_r + 20),
 		   *(u32 *)(share_seq_r + 24));
+
+	if (release_call) {
+		/* Empfaengerpflicht: Slot in den Pool des Senders zurueck. share_seq_r
+		 * ist getShareSeqR(remote_cpu, 0), local_cpu = wir -- der Waechter in
+		 * Comm_ReleaseFreeCall() ("cpu mismatch") laesst das durch. */
+		Comm_ReleaseFreeCall((void *)share_seq_r, (void *)entry_base);
+
+		/* RETURN nur, wenn der Sender einen erwartet -- exakt die Bedingung
+		 * aus comm_CallWorkAction(). Beide bekannten Rueckrufe sind NOTIFY
+		 * (+6 = 0x0001): dort NIE antworten, der MIPS asserted sonst in
+		 * command_action Z. 119 (kein Wartobjekt bei +32). */
+		if (!(local_msg[6] & MSG_FLAG_NOTIFY) ||
+		    (local_msg[6] & MSG_FLAG_RETURN_ACK)) {
+			*(u16 *)(local_msg + 8) = 0;	/* 0 Rueckgabewerte (ParaCount) */
+			if (SendComm2CPUEx((unsigned long)local_msg, remote_cpu, 0))
+				pr_warn_ratelimited("cpu_comm: command_action: RETURN comp=0x%08x fehlgeschlagen\n",
+						    *(u32 *)(local_msg + 40));
+		}
+	}
 }
```

Anmerkungen zur Skizze:

* **Reihenfolge relativ zu `Comm_Add2NewCallFifo`:** ersetzt ihn im Kernel-Pfad vollständig. Die Kanal-Semaphore
  (Kanal `0x1`, `channel … registered` in `watch`) wird dann nicht mehr hochgezählt - sie hatte ohnehin keinen
  Nehmer.
* **Reihenfolge relativ zum ACK:** Freigabe nach `SendAckLow` spiegelt Stock (ACK in `command_action`, Release im
  Leser). Vor dem ACK wäre es in der Praxis auch sicher (der MIPS-Sender hält bis zum ACK seine Sende-Semaphore,
  niemand sonst kann in diesen Pool greifen), aber ohne Not.
* **Ergebniszahl bei `+8`, nicht `+4`:** `+4` ist der Slot-Index und wird in `SendComm2CPUEx` (Schritt 9/11) sowieso
  auf den neuen Slot gesetzt; Stock-`CPUComm_CallEx` liest die Anzahl aus `+8` (`v34[4]`), Werte ab `+44`.
* **Wenn doch ein Userspace-Leser existiert:** heute kann keiner freigeben oder antworten - `read()` bekommt
  Kopien, der Stock-ioctl `0xC0087F03` ist nicht portiert. Deshalb muss der Kernel **immer** freigeben. Sollte der
  Stock-Leser-ioctl je nachgezogen werden, ist das Kriterium `chan_pid (+16) == 0` (Kernel-Routine, Kanal `0x1`)
  → Kernel gibt frei, sonst (pid-Schlüssel) → `Comm_Add2NewCallFifo` und Freigabe im ioctl wie Stock.
* **Die zwei Altfehler:** `RemovePidRoutines()` (pid bei `+28` statt `+4`) betrifft nur das Abräumen der
  Routinentabelle beim `close()`, nicht Slots oder Ring - hier **irrelevant**. Die Kanalprüfung in
  `Comm_Add2NewCallFifo()` (obere 16 Bit des Schlüssels, pids < 4096) wird für den Kernel-Pfad durch die Skizze
  **umgangen** (der Aufruf entfällt); für den Hänger war sie nicht ursächlich (Kanal `0x1` wurde gefunden, sonst
  stünde `no channel for id` im dmesg - steht dort nicht). Beide bleiben, wie in 00-STATUS notiert, eigene Sitzung.
* **Messgerät dazu:** `watch` sollte zusätzlich `(0,1,0)` zeigen - `FreeCall rd/wr` **und** `CallCmd rd/wr`
  („eingehend"). Mit dem Fix müssen dort `wr` dem `rd` folgen (FreeCall) und der Ring leer bleiben.

---

## 5. Frage E - schneller Beleg am lebenden Gerät (nur lesend)

Alles wortweise 32 Bit lesen (Alignment-Regel, doku/69). Adressen ARM-phys:

| Was | Adresse | Erwartung heute (ohne Fix) |
|---|---|---|
| **CallCmd-Ring (0,1,0)** `rd` / `wr` / `cap` | `0x4E3013C8` / `0x4E3013CC` / `0x4E3013D8` | `rd` bleibt 0, `wr` = Zahl der Rückrufe seit Kaltstart; **bei `wr−rd = 19` hängt der nächste Ruf** |
| **FreeCall (0,1,0)** `rd` / `wr` / `cap` | `0x4E301420` / `0x4E301424` / `0x4E301430` | `rd` +1 je Rückruf, `wr` bleibt 20 |
| Einträge (0,1,0) | `0x4E301510 + 104·i`, `+6` flags, `+10` flags2, `+12` session, `+40` comp | `flags 0x0001`, `flags2 0x1d`, Sessions lückenlos |
| Letzte Session (Kopf `+20`) | `0x4E3013BC` | `0x400000nn` |
| MIPS Sende-Slot-Cache `cache[2·cpu+type]` | MIPS `0x8B2543B8` → ARM `0x4B2543B8` (`[0]` = cpu0/CALL) | 0 zwischen Rufen; **≠ 0 dauerhaft** = Sender steckt in `SendComm2CPUEx` |
| MIPS Session-Zähler | MIPS `0x8B2543C8` → ARM `0x4B2543C8` | `0x400000nn`, +1 je Ruf |

Vor/nach einem Auflösungswechsel (oder einem ARISC-HotPlug wie in CALLBACK-luecke §8 Schritt 6):

```bash
ssh root@192.168.8.141 'python3 - <<EOF
import mmap, os, struct
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m  = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x4E301000)
r  = lambda a: struct.unpack_from("<I", m, a - 0x4E301000)[0]
print("CallCmd(0,1,0) rd=%d wr=%d cap=%d -> ungelesen %d (Schwelle 19)" % (r(0x4E3013C8), r(0x4E3013CC), r(0x4E3013D8), (r(0x4E3013CC)-r(0x4E3013C8)) % 21))
print("FreeCall(0,1,0) rd=%d wr=%d -> frei %d" % (r(0x4E301420), r(0x4E301424), (r(0x4E301424)-r(0x4E301420)) % 21))
print("letzte Session %08x" % r(0x4E3013BC))
EOF'
```

Vorhersage ohne Fix: je Rückruf `CallCmd wr` +1, `FreeCall rd` +1, `frei` −1; Hänger bei `ungelesen = 19`.
Vorhersage mit Fix: `CallCmd rd == wr` (leer), `FreeCall wr` folgt `rd` nach (`frei` bleibt 20 oder 19 kurzzeitig).
Dazu die Positivkontrolle: `THal_Vp_SetBacklightLevel`-RPC (Gegenrichtung) darf **keinen** dieser Werte bewegen.

---

## 6. Belegt / vermutet

**Belegt (Dekompilat, Quelltext beider Bäume, Abzug, elog):**

* `cmdfifo.type=%d, target cpu=%d` (Z. 473) druckt `SendComm2CPUEx @ 0x8b11fc2c` in
  `while (fifo_isNearlyFull(seqW+32, 1)) { elog; yield; }`, **vor** `Comm_GetFreeCall`; Schwelle 19 bei cap 21.
* Ring `(0,1,0)+32` im Abzug: `rd=0, wr=19`; Pool `(0,1,0)+120`: `rd=19, wr=20`; 19 belegte Einträge mit
  `flags=0x0001`, alle `0x3e7fbc46`, Sessions `0x40000001…13`; hängende Session `0x40000014`.
* Der Ring wird auf dem ARM nur von `Comm_Add2NewCallFifo` gefüllt; im Zielbaum gibt es keinen Aufrufer von
  `Comm_GetCallbyChannel`, `Comm_ReleaseFreeCall` läuft nur für `> 4` (`rpc.c:1034`) und RETURN-Slots (`rpc.c:721`).
* Stock-ARM: `≤ 4` wird über ioctl `0xC0087F03` abgeholt (`Comm_GetCallbyChannel` → `copy_to_user` →
  `Comm_ReleaseFreeCall(getShareSeqR(src,0))`); MIPS-BG_Thread macht dasselbe (`memcpy` → `Comm_ReleaseFreeCall` →
  Routine → RETURN nur ohne NOTIFY).
* NOTIFY-Semantik: MIPS legt bei `flags&1 && !(flags&2)` kein Wartobjekt an, wartet nur auf CALL_ACK; MIPS-
  `command_action` asserted bei RETURN ohne Wartobjekt (Z. 119).
* `command_action` läuft im Workqueue-Kontext (`queueAction → schedule_work → comm_WorkAction`).

**Vermutet (plausibel, nicht gemessen):**

* Dass der spinnende Thread höher priorisiert ist als BG_Thread und Debug-Shell (erklärt `-110`, die zwei
  ungelesenen Einträge im MIPS-Ring und die tote Shell). ThreadX-Yield lässt nur Gleichrangige laufen.
* Dass das „Kippen nach vier bis fünf Wechseln" (doku/97 §3b) genau dieser Mechanismus ist - die Zahl passt,
  die Messung in §5 entscheidet es.
* Dass die Skizze in §4.2 ohne weitere Nebenwirkung ist. Nicht gebaut, nicht gefahren.

---

## 7. Nebenbefunde

* **`hits 16` vs. `rx_calls 19`:** der Abzug hat 19 Einträge; `rx_calls` zählt global, `hits` je Registrierung
  (Neuregistrierung setzt ihn zurück). Der dmesg-Ausschnitt beginnt erst bei 2110 s, die drei fehlenden liegen
  davor. Für Pool und Ring zählt 19. (Nicht weiter verfolgt.)
* **Mainline-`Comm_GetCallbyChannel` ist eine Fehlportierung** (liest `channel_ptr+32` als Ring). Stock/MIPS lesen
  `getShareSeqR(i,0)+32` für beide `i`, hängen die Einträge in die **Kanal-Liste** und rücken `rd` vor
  (`moveNewCallsfromFifo2Chan`). Heute toter Code - relevant erst, wenn jemand den Leser-ioctl portiert.
* **Doppelte Userspace-Zustellung für `> 4`:** `command_action` ruft `cpu_comm_userspace_deliver`, danach
  `comm_CallWorkAction` noch einmal. Für die Rückrufe (`≤ 4`) nicht wirksam.
* **`watch` misst für diese Frage den falschen Pool** (§3). Vorschlag in §4.2.
* **MIPS-Sende-Slot-Cache `0x8B2543B8`** ist das Gegenstück des in doku/65 aus Patch 0014 entfernten „Cache-Hacks" -
  auf dem MIPS ist er Stock, wird aber nach jedem CALL_ACK genullt (`SendComm2CPUEx` nach Z. 607), ist also nur
  ein „Slot in Arbeit"-Zeiger, kein dauerhafter Cache.

## Dateien

* IDA-Skripte: `analyse/ida/ida_q67.py` (Strings, `SendComm2CPUEx`, `Comm_GetFreeCall`, `BG_Thread_entry`,
  `Comm_Add2NewCallFifo`, `Comm_GetCallbyChannel` des MIPS), `ida_q68.py` (`fifo_isNearlyFull`, Yield,
  MIPS-`Comm_ReleaseFreeCall`, MIPS-`command_action`, Slot-Cache), `ida_q69.py` (Stock-ARM `cpu_comm_dev.ko`:
  Aufrufer, ioctl `0xC0087F03/04`, `comm_CallWorkAction`), `ida_q70.py` (Disassembly `sub_8B15B5CC`).
* DB-Kopien: `analyse/ida/db-cpucomm/display.bin.i64`, `analyse/ida/db-cpucomm/cpu_comm_dev.ko.i64`.
* Ausgaben und Abzug-Parser: Scratchpad der Sitzung (`ida_q6{7,8,9}.out`, `ida_q70.out`) - **nicht dauerhaft**,
  bei Bedarf Skripte erneut laufen lassen.
