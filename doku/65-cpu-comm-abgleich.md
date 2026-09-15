# cpu_comm: drei Generationen, abgeglichen

Stand 01.09.2026. Anlass: cstengers arm64-Portierung sitzt auf einem alten
Stand unseres Treibers, und der U-Boot-Weg (`h713_disp commcall`) erbt dessen
Annahmen teilweise. Hier steht, was sich zwischen den Generationen geändert
hat, wer was hat, und wo sie sich widersprechen.

Alles unten ist aus den Quellbäumen diffed, nicht aus Notizen übernommen.

## Die drei Bäume

| | Zeilen | `cpu_comm_user.c` | |
|---|---|---|---|
| `re/work/HY310-DEV/cpu_comm/` | 8179 | - | 21. - 31.03., der älteste |
| `legacy/drivers/Archived/cpu_comm/` | 8361 | - | **= sein Patch 0014** |
| `legacy/drivers/cpu_comm/` | 9968 | **ja**, 234 Z. | unser Stand, der richtige |

Dass Patch 0014 aus `Archived/` stammt, ist dateiweise belegt - die Zeilenzahlen
stimmen alle überein (861/1521/257/642/888/2221/902/1069). Steht so auch in
[60-offen.md](60-offen.md): der Ordner hat ihn einen Tag gekostet.

Der Diff `Archived → cpu_comm` umfasst **3709 Zeilen** über neun Dateien:

```
cpu_comm_hw.c        14 Hunks   +503  -62
cpu_comm_dev.c       21 Hunks   +487  -128
cpu_comm_proto.c     22 Hunks   +324  -90
cpu_comm_mem.c       25 Hunks   +235  -106
cpu_comm_rpc.c       18 Hunks   +140  -59
cpu_comm_channel.c   19 Hunks   +111  -28
cpu_comm.h            7 Hunks   +78   -43
cpu_comm_fifo.c       1 Hunk    +9    -6
cpu_comm_user.c      NEU        +234
```

## Merkmalstabelle

`alt` = `Archived/`, `neu` = unser aktueller Baum, `arm64` = seine Branch-Spitze
`h713-display-video-path` (Patch 0014 plus seine vier `cpu_comm:`-Commits).

| Merkmal | alt | neu | arm64 | |
|---|---|---|---|---|
| `cpu_comm_user.c` (Callback-Loop) | - | **6 Dateien** | - | `.read`/`.poll`, per-fd-Ringpuffer |
| `userspace_deliver` | - | **4** | - | Hook in `comm_CallWorkAction` + `handle_CPU2_call` |
| `sync_mips_cache` (DMB-Muster) | - | **1** | - | Session W |
| `cpu_comm_is_mips_va` | - | **3** | - | Session Z, KSEG0-Range-Check |
| `sema_init` | 1 | **5** | 1 | Y2: Linux-`struct semaphore` |
| FreeCall-Cache-Hack raus | - | **ja** | - | K-night, s.u. |
| `HW_SPINLOCK_COUNT` | 14 | **9** | 14 | Session W |
| `cc_ref` | - | - | **6** | **nur er**: 32-Bit-Zeigermodell für arm64 |
| TX_IRQ_EN-Puls zum MIPS | - | - | **ja** | **nur er** |

Zwei Dinge hat **er**, die uns fehlen; alles andere fehlt **ihm**.

## Der Doorbell - der Punkt, an dem es zusammenläuft

Für einen frischen CALL an den MIPS:

| | geschriebenes Wort | Puls |
|---|---|---|
| alt (= sein Patch 0014, unverändert) | `(dir<<16) \| INTR_TYPE_SEND` = **`0x00000002`** | nein |
| neu (unser Baum) | `(0<<16) \| MSG_TYPE_CALL` = **`0x00000000`** | nein |
| sein arm64-Treiber (nach seinen Fixes) | `msg_type & 3` = **`0x00000000`** | **ja** |
| sein U-Boot `commcall` | **`0x00000000`** | **ja** |

Der alte Wert `0x2` ist der dokumentierte Fehlgriff: die Firmware liest ihn als
**CALL_ACK** und verwirft die Nachricht. Steht als Sackgasse vom 16.04. in
`re/notes/DEAD-ENDS.md` („INTR_TYPE_SEND=2 is the forward-CALL message type ✗").

Er hat die Funktion korrigiert (`raw = msg_type & 0x3`), die Aufrufstellen aber
gelassen (`send_intr_to_mips(dir, INTR_TYPE_SEND, 0)`). Das geht gut, weil `dir`
0/1 ist und `MSG_TYPE_CALL/RETURN` ebenfalls 0/1 - derselbe Wert wie bei unserer
expliziten Fassung, aber aus einem anderen Grund.

**Der Puls fehlt bei uns.** Unser einziger `TX_IRQ_EN`-Schreibzugriff steht im
ARISC-Pfad (`H713_MSGBOX_ARISC_TX_IRQ_EN = 0x430`, `cpu_comm_hw.c:1245`), nicht
im MIPS-Pfad. Genau das führt [60-offen.md](60-offen.md) als offenen Defekt im
öffentlichen Repo, und `CURRENT-TRUTH.md` sagt device-verified, dass MSG_DATA
allein auf dem H713 verworfen wird - der Block ist flankengetriggert, nicht
pegelgetriggert wie beim H6.

Die Transportadressen sind in allen vier Fassungen gleich und stimmen mit dem
Gerät überein: TX `0x03003874` (Zähler `0x03003864`), RX `0x03003164`/`0x03003174`,
Version `0x03003810` (liest `0x00020000`), Bus-Gate `0x0200171c` Bit 0 + Bit 16.

## Die FreeCall-FIFO - gelöst, und was der Zähler wirklich sagt

Der Pool hat 21 Plätze bei `share_seq + 120`. Der **Sender entnimmt**
(`Comm_GetFreeCall`), der **MIPS legt zurück** (`Comm_ReleaseFreeCall`, nachdem
sein BG_Thread den Call verarbeitet hat).

Alt, und damit in seinem Patch 0014:

```c
cache_idx = 2 * dst_cpu + target_cpu + 8;
call_slot = (u8 *)comm_intrsem[cache_idx];   /* Slot dauerhaft gecacht */
...
comm_intrsem[cache_idx] = (u32)call_slot;
```

`Comm_GetFreeCall` lief **einmal**, danach nie wieder - während der MIPS in
jedem Zyklus einen Slot zurücklegte. Die FIFO lief nach einem Zyklus über.

Gelöst am 22.04. (Session K-night), in unserem Baum:

- Cache-Hack raus, frisches `Comm_GetFreeCall` pro Send - stock-konform.
  Entnahme und Rückgabe balancieren sich wieder.
- `fifo_isNearlyFull`-Warteschleife auf 100 Spins begrenzt, dann `-EBUSY`
  statt Endlosschleife.
- Sämtliche `BUG()` in `Comm_ReleaseFreeCall` durch `return` ersetzt.

**Noch offen, und im Quelltext als `TODO: SLOT-RELEASE-WAIT` vermerkt:** die
100 Spins sind ein Behelf. Sauber wäre `cpu_comm_sem_down_timeout` auf der
Slot-Release-Semaphore (`s_CommSockt[remote] + 235`). Behelfsmäßig gedrosselt
wird stattdessen im Userspace, `CALL_GAP_MS = 500` in `hy310-hdmird`.

**Für die Deutung von `commcall` heißt das:** ein hochlaufender `rd`-Zähler ist
kein Leck und kein Fehler des Werkzeugs, sondern das Anzeichen, dass der MIPS
die Nachricht nicht angenommen hat. Am 01.09. gemessen:

```
FreeCall  rd=0 wr=20 cap=21        vor dem ersten Aufruf
FreeCall  rd=1 wr=20  idx=00 state=04    nach dem ersten
FreeCall  rd=2 wr=20  idx=01 state=04    nach dem zweiten
```

`state=04` ist `MSG_FLAG_SENT`, noch gesetzt - die Firmware hat das Flag nie
gelöscht, also nie zugegriffen. Solange das so bleibt, kommt kein Slot zurück
und nach zwanzig Aufrufen meldet `commcall` „no free slot (ring empty)".
Der Zähler ist damit ein brauchbares Orakel: **läuft er hoch und bleibt oben,
verarbeitet der MIPS nicht.**

## Was ihm sonst fehlt, mit Wirkung

- **Semaphoren.** Alt: roher 4-Byte-Zähler, `sock[31] = 1`. Neu: echte
  `struct semaphore`, Basis `sock[30]` (`sock+120`), dazu `sock[234]`
  (`sock+936`) - der Y2-Off-by-4. Die alten Kommentare sagten ausdrücklich
  „sem at sock[31] NOT sock[30]", was für den Zähler stimmte und für die
  Linux-Primitive falsch ist.
- **`IOCTL_INSTALL_RT` ruft `Comm_AddNewChannel`** nach `AddInRoutine` (Y2,
  stock-konform bei `0x1518`). Ohne das schlägt die ChanPID-Suche für
  MIPS→ARM-CALLs fehl - also genau für Callbacks.
- **`GetReturnbySessionId`** gibt `-ENOENT` statt 0-mit-NULL zurück (Session W).
  Die alte Semantik führte zu `ReleaseWaitComm` mit Müllzeiger.
- **Cache-Kohärenz.** Stock macht `DMB ISHST` + Spin-Wait auf das gelöschte
  Flag, bevor es die Nachricht verarbeitet. Flag-Offsets `+8` für CALL/RETURN,
  `+105` für die ACKs.

## Was er hat, das wir brauchen

**`cc_ref`.** Unser Treiber speichert `(u32)&x` und holt den Zeiger mit
`p | 0xffff800000000000` zurück. Auf arm32 verlustfrei, auf arm64 Unsinn. Seine
Kodierung: Bit 31 gelöscht = ARM-physische Adresse in der geteilten Region,
Bit 31 gesetzt = getaggte treiber-private Arena. Das deckt auch die Zeiger ab,
die die `Vir2Mid`/`Mid2Vir`-Schicht allein nicht abgedeckt hätte.

Beim Portieren geht das **vor** unseren Fixes rein, nicht danach - sonst
zeigt jede Listenverkettung ins Leere.

## Folge für den U-Boot-Weg

`h713_disp commcall` schreibt das Shared Memory direkt und braucht keinen
Linux-Treiber. Sein Doorbell-Verhalten ist korrekt (blanker Typ + Puls). Was er
davon **nicht** erbt, sind die Dinge oberhalb des Transports - Semaphoren,
Channel-Add, Cache-Sync - , und die betreffen erst die Antwortrichtung.

Zwei Fallen, beide am 01.09. am Gerät gesehen:

- **Das Bus-Gate.** `commcall` **liest** `0x0200171c` und druckt es, schaltet es
  aber nicht ein. Ohne vorheriges `h713_disp init` steht es auf 0, das
  Versionsregister liest 0, und der Doorbell wird schweigend verschluckt -
  `fifo count now 0`. Von Hand: `mw.l 0x0200171c 0x00010001`, danach liest
  `0x03003810` = `0x00020000`.
- **Der Selbsttest von `commdev` ist auf Board B kalibriert.** Er erwartet
  `03e00008 24020001` bei `0x8b1227b4`; unsere Firmware hat dort echten Code
  (`00a08025 00809025`). Er erklärt daraufhin alle KSEG-Lesevorgänge für
  ungültig - zu Unrecht: `fwmd 0x8b48c2a4` liefert `00000757 00000757`, also
  genau die 1879, die `mipslog state` unter Linux meldet. Gleiche Fehlerklasse
  wie die HDCP-Adresse (`0x4b13d6f8` bei ihm, `0x4b13d0a4` bei uns).

## Methodenwarnung

`grep -r` liefert in dieser Umgebung auf Verzeichnissen unter `/tmp` **keine
Treffer**, obwohl `grep` mit Glob dieselben Dateien findet. Eine erste Fassung
der Merkmalstabelle war dadurch komplett falsch (überall `0`). Dieselbe Lehre
steht in cstengers Handoff vom 30.08.: *„When a scan answers 'none', check that
it could have seen one."*

## Was hier noch nicht steht

Der Diff ist vollständig erzeugt und pro Datei ausgezählt, aber nicht
zeilenweise durchgearbeitet. Nicht abgeglichen sind bisher `cpu_comm_dev.c`
(487 neue Zeilen, davon der größte Teil Probe/Clock/IRQ-Aufbau),
`cpu_comm_mem.c` jenseits der Semaphoren-Offsets und `cpu_comm_rpc.c`. Der
Rohdiff liegt reproduzierbar vor:

```bash
cd /opt/Projekte/h713/legacy/drivers
diff -upr Archived/cpu_comm cpu_comm
```

## Der zusammengeführte Baum - `analyse/cpu-comm-arm64/`

Erzeugt am 01.09.2026 als **Drei-Wege-Merge** mit `Archived/` als gemeinsamem
Vorfahren (`git merge-file`), nicht als Neuschreiben. Beide Seiten sind vom
selben Stand ausgegangen, also war das das richtige Werkzeug.

28 Konflikte, `cpu_comm.h` ging konfliktfrei durch. Die Regel war fast
durchgängig **unsere Logik, seine Typbreiten** - mit vier Ausnahmen, wo seine
Lösung die bessere ist:

| Stelle | genommen | warum |
|---|---|---|
| Shared-Region-Adoption | seine | bedingt statt `#if 0`; kein Wipe bei laufendem MIPS |
| msgbox-Taktung | seine | nur deassert, kein Puls - der MIPS kann in einer Queue stecken |
| RX-Modell + Doorbell | seine | gegen U-Boots funktionierenden Transport verifiziert |
| Spinlock-Feldinit | seine | `writel` + benannte Konstanten |

Beim **Doorbell** mussten beide verbunden werden: sein Draht-Format (blanker
Typ, `TX_IRQ_EN`-Puls auf `0x03003830`), aber unsere Aufrufkonvention - seine
Funktion nimmt den Typ aus dem ersten Argument, unsere Aufrufer legen ihn ins
zweite. Unverändert übernommen hätten wir immer `0` gesendet.

### Die Semaphoren: `cpu_comm_sem.c`

Statt die Objekte an Stock-Byte-Offsets zu quetschen, bleibt die **Adresse der
Schlüssel** und das Objekt zieht in eine Seitentabelle. Damit bleibt jeder
Offset unverändert, die Y2-Semantik bleibt, und auf arm64 überläuft nichts.

Zulässig ist das, weil alle über `cpu_comm_sem_*` angefassten Semaphoren in
`s_CommSockt[]` liegen - einem statischen Kernel-Array (`cpu_comm_mem.c:38`) -
oder in dessen Wait-Objekten. Der MIPS liest keine davon. Die eine Stelle, die
er wirklich liest (`sock[248]`, Offset 0x3E0, aus `display.bin` 0x8B11FEEC),
ist ein roher u32 und läuft nicht über diese Schnittstelle.

Der Vorgabewert beim Anlegen ist **Zähler 0**: die einzigen Adressen ohne
ausdrückliches Init sind die Wait-Objekte, und die sind im Stock-Layout genau
so gebaut (`entry[3]=0` lock, `entry[4]=0` count, `entry[5..6]`
selbstreferenziell) - eine gültige 16-Byte-Semaphore ohne `sema_init`.

### Zwei Funde beim Bauen

**Die Cache-Invalidierung aus Session W ist auf arm64 gegenstandslos.** Die
Region wird per `ioremap` abgebildet, Device/uncached; es gibt keinen Cache,
der etwas Veraltetes zurückhalten könnte. Der Aufruf stammt aus der Zeit, als
dort `vmap()` stand. `invalidate_kernel_vmap_range` existiert auf arm64 auch
gar nicht. Der Grund steht jetzt im Code - wer die Abbildung je auf
cachefähig umstellt, braucht die Invalidierung wieder.

**Ein Semaphoren-Leck in unserem Baum.** `Comm_ReleaseFreeCall` gibt im
FIFO-voll-Pfad zurück, ohne die Semaphore freizugeben. Folge unserer
`BUG()`→`return`-Umstellung: `BUG()` kam nie zurück, `return` schon. Gefixt.

### Stand

```
hy310-cpu-comm.ko   196.872 Bytes, ELF aarch64
md5 fc2003fad3af0692721dbad35ec4109d
0 Fehler, 0 Warnungen
```

Bauen:

```bash
podman exec h713-build bash -lc 'cd /work/analyse/cpu-comm-arm64 && \
  make -C /work/mainline/build/linux-6.18.38-f5372f69*/ M=$PWD ARCH=arm64 LLVM=1 modules'
```

Sieben Zeiger-Abschneidungen wurden dabei einzeln entschieden, nicht pauschal
gecastet - darunter `cpu_comm_is_mips_va()`, das ein `u32` nahm und auf arm64
Kernelzeiger stutzte, bevor es fragte, ob sie wie `0x8xxxxxxx` aussehen. Ein
gültiger Rückgabewert wäre damit zufällig verworfen worden.

**Nicht getestet.** Das Modul ist gebaut, nicht geladen. Auf dem Gerät läuft
derzeit kein cpu_comm (`/dev/cpu_comm` fehlt, `0x03003000` ist in
`/proc/iomem` unbeansprucht).
