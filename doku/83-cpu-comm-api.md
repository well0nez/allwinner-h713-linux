# Die In-Kernel-API von `cpu_comm`

Stand 07.09.2026, Paket C des Nachtplans
([78-nachtplan-hdmi-switch.md](78-nachtplan-hdmi-switch.md)). Vorgänger:
[65-cpu-comm-abgleich.md](65-cpu-comm-abgleich.md) (die drei Treibergenerationen),
[66-cpu-comm-arm64-bringup.md](66-cpu-comm-arm64-bringup.md),
[67-cpu-comm-linux.md](67-cpu-comm-linux.md) (der Round-Trip aus Linux).
Patch: `mainline/patches/kernel/0092-soc-sunxi-h713-cpu-comm-kernel-api.patch`.

Der MIPS trägt HDMI-Empfang und Bildpipeline; alles, was er kann, ist eine
`THal_Vp_*`-Fernprozedur über das Shared Memory. Bisher führte der einzige Weg
dorthin über `/dev/cpu_comm`, also über ein Userspace-Programm. Die Treiber, die
den Koprozessor wirklich brauchen — der V4L2-HDMI-RX-Treiber (Paket E) und der
ARISC-Treiber (Paket B) —, bekommen mit diesem Patch einen direkten Weg.

**Die Char-Devices bleiben, wie sie waren.** `/dev/cpu_comm`, `/dev/cpu_comm_fd`,
alle ioctls, `read()`/`poll()` und das Shared-Memory-Protokoll sind unverändert;
`hdmi_seq.py` und `hy310-hdmird` laufen weiter.

---

## 1. Die Schnittstelle

`include/linux/soc/sunxi/h713-cpu-comm.h`:

```c
int cpu_comm_call(u32 comp_id, const u32 *args, unsigned int nargs,
                  u32 *ret, unsigned int nret, unsigned int timeout_ms);

int cpu_comm_register_callback(u32 comp_id, cpu_comm_cb_t fn, void *ctx);
int cpu_comm_unregister_callback(u32 comp_id, cpu_comm_cb_t fn);

u32 cpu_comm_name2id(const char *base_name, unsigned int target_cpu);

typedef void (*cpu_comm_cb_t)(u32 comp_id, const u32 *args,
                              unsigned int nargs, void *ctx);
```

Alle vier sind `EXPORT_SYMBOL_GPL`. Ist `CONFIG_HY310_CPU_COMM` aus, liefert der
Header statische Inline-Stümpfe mit `-ENODEV`, damit ein Konsument ohne
Abhängigkeit übersetzt.

`cpu_comm_unregister_callback()` steht nicht im Auftrag, ist aber Pflicht: ohne
sie hinterlässt jedes entladene Modul einen Zeiger in der Tabelle.

### `comp_id` — was das ist

Eine Routine wird über eine 32-Bit-Zahl adressiert, nicht über ihren Namen. Die
Zahl ist ein CRC-32 (LSB-first, Polynom `0xEDB88320`, **ohne** Vor- und
Nachinvertierung) über den vollständigen Routinennamen, mit `0x00123456`
vorbelegt — der Vendor nennt das `Trid_Util_Name2ID` (libUtility.so `@0x1DC61`).
Der Name, der gehasht wird, ist

```
<Basisname>_<CPU, die die Routine trägt, 1 Hexziffer>_<pid, 3 Hexziffern>
```

Alle Stock-Routinen benutzen pid 0. `THal_Vp_SetSource` liegt auf dem MIPS
(CPU 1), also wird `THal_Vp_SetSource_1_000` gehasht, und das ergibt
`0xEAF13DE5`. Die Rückrufe des MIPS in den ARM (`MipsHalCallback_*`) liegen auf
CPU 0.

Genau das macht `cpu_comm_name2id()`; der Kernel hat den passenden Rohrechner
schon (`crc32_le()` invertiert weder vorn noch hinten). Der Treiber trägt also
**keine Tabelle**.

> **Korrektur zu `mainline/docs/reference/cpu-comm-call-table.md`.** Dort steht,
> die IDs seien aus dem Namen nicht ableitbar („crc32, ~crc32, djb2 … all fail").
> Das stimmt nur ohne die Vorbelegung und ohne den `_<cpu>_<pid>`-Anhang. Mit
> beidem stimmen **alle** dort namentlich aufgeführten Einträge, einschließlich
> der beiden mit dem Vendor-Tippfehler `Thal_` statt `THal_`
> (`Thal_Vp_SetBacklightLevel` → `0x51AD877E`,
> `Thal_Vp_SetBacklightPwmInfo` → `0xB46CE545`), und dazu die zehn
> `MipsHalCallback_*` aus `analyse/hdmi-seq/hdmi_seq.py`. Nachgerechnet am
> 07.09.2026 gegen beide Quellen. Die Seite gehört cstengers Baum; die Korrektur
> steht hier, nicht dort.

### Argumentlayout

Argumente und Ergebnisse sind Felder aus 32-Bit-Wörtern, höchstens
`CPU_COMM_MAX_ARGS` = 10 Stück. Diese Grenze ist die des Protokolls; der
Vendor-Wrapper prüft sie ebenso.

Auf der Leitung landen sie in der 104-Byte-Nachricht so:

| Offset | Inhalt |
|---|---|
| `+0x02` | Ziel-CPU (u16) |
| `+0x08` | ParaCount (u16) |
| `+0x0C` | Session-ID |
| `+0x10` | Kanal-pid |
| `+0x28` | `comp_id` |
| `+0x2C` | Argument 1 |
| `+0x30` | Argument 2 |
| `+0x34` | Argument 3 … |

Das ist dasselbe Layout, das `hdmi_seq.py` über `IOCTL_CALL` schreibt
(dort `buf+64` = Anzahl, `buf+68…` = Werte, weil der ioctl den Zeiger auf
`params` eine Struktur später ansetzt). **`+0x34` ist Argument 3 und kein
pid-Feld** — die arm32-Vorlage hatte dort einen `tgid` abgelegt und damit den
dritten Ausgabezeiger von `Wce_GetWindow` zerstört; siehe doku/67, „Argument-ABI".

Typinformation gibt es auf der Leitung nicht. Eine Routine, die einen Puffer
nimmt, nimmt dessen **physische** Adresse als schlichtes `u32`, und der Puffer
muss dort liegen, wo der MIPS ihn sieht. Beispiele aus `hdmi_seq.py`:

* `THal_Vp_Init` — ParaCount 3, `Para[2]` = Staging-Adresse. Der Handler kopiert
  55296 Byte aus seinem `.bss` dorthin; mit 0 ist das ein NULL-`memcpy` und reißt
  die Firmware mit. Benutzt wird Shmem + 4 MiB = `0x4E700000`
  (`hdmi_seq.py` Z. 75).
* `THal_Vp_SetHDCP22Key` — ParaCount 2, `(0x4E336000, 912)`.
* `THal_Vp_DisableBlackScreen` — ParaCount **0**, nicht 1.
* `THal_Vp_SetSource` — ParaCount 1, `3` = HDMI-1.

Ergebnisse kommen genauso zurück: eine Anzahl und so viele Wörter.

Die 32 Bit sind wörtlich zu nehmen. Die Shared-Region ist per `ioremap()`
abgebildet, also Device-Speicher, und ein 64-Bit-Laden von einer nur
4-Byte-ausgerichteten Adresse darin ist ein Alignment-Fault (FSC 0x21). Der
bestehende Ergebnis-Kopierer liest deshalb wortweise
(`*(u32 *)&return_entry[2 * i + 22]`, doku/67); die neue API benutzt **denselben**
Kopierer, statt einen zweiten zu bauen.

### Rückgabe und Zeitüberschreitung

`cpu_comm_call()` liefert die **Anzahl der nach `ret` geschriebenen Wörter**
(0…`nret`) oder einen negativen Fehler. Nicht gefüllte Plätze von `ret` werden
genullt.

| Rückgabe | Bedeutung |
|---|---|
| `>= 0` | Anzahl gelieferter Ergebniswörter |
| `-ETIMEDOUT` | **kein RETURN** innerhalb `timeout_ms` |
| `-ENODATA` | Wartung signalisiert, aber die Return-FIFO war leer |
| `-ENODEV` | IPC nicht oben, Routine unbekannt, oder MIPS im Reset |
| `-EAGAIN` | MIPS noch nicht „app ready" |
| `-EBUSY` | FreeCall-FIFO leer (Slot-Vorrat erschöpft) |
| `-EINVAL` | mehr als 10 Wörter, Zeiger fehlt |

`timeout_ms == 0` wählt die 500 ms, die der bestehende Pfad schon immer benutzt.

**Warum das eigens erwähnt wird.** `CPUComm_CallEx` wartet 500 ms auf den RETURN
und macht danach weiter, egal was war: `GetReturnbySessionId` meldet „keine
passende Session" als Erfolg (Stock-Semantik, IDA `@0x59cc`), `*result` bleibt
unberührt, die Funktion gibt 0 zurück. Eine Routine, die nichts zurückgibt, und
ein Koprozessor, der nie geantwortet hat, sehen damit gleich aus. Für den
ioctl-Pfad bleibt das so — er hat sich immer so verhalten und `IOCTL_CALL`
verdeckt ohnehin jeden Fehler hinter `-EFAULT`. Ein Kernel-Aufrufer bekommt
stattdessen `-ETIMEDOUT`.

Umgesetzt ist das **ohne zweiten Protokollpfad**: der ganze bisherige Rumpf von
`CPUComm_CallEx` heißt jetzt

```c
int cpu_comm_call_ex(int comp_id, int *params, u32 *result,
                     unsigned int timeout_ms, bool strict);
```

`CPUComm_CallEx()` ist der Aufruf mit `(0, false)` — Verhalten unverändert —,
`cpu_comm_call()` der mit `(timeout_ms, true)`.

---

## 2. Callbacks

### Wo zugestellt wird, und in welcher Reihenfolge

Ein eingehender CALL vom MIPS läuft über `command_action()` (`cpu_comm_proto.c`,
Richtung 0). Dort steht seit dem 07.05. die Zustellung an jeden offenen
`/dev/cpu_comm`-Deskriptor. Eine Zeile darunter steht jetzt die Zustellung an den
Kernel-Handler:

```c
cpu_comm_userspace_deliver((const void *)entry_base);   /* wie bisher */
cpu_comm_kernel_deliver((const void *)entry_base);      /* neu */
```

**Reihenfolge: erst die Char-Devices, dann der Kernel-Handler.** Das ist keine
Priorität und keine Bewertung — der Userspace-Pfad stand zuerst da und behält
seinen Platz. Beide sehen dieselbe 104-Byte-Nachricht, keiner kann den anderen
unterdrücken, und keiner kann die Quittung an den MIPS verhindern, die direkt
danach abgeht.

Diese Stelle ist mit Absicht gewählt: sie liegt **vor** der Verzweigung nach
Kanalfeld (`entry_base[0]`),

* `<= 4` → `Comm_Add2NewCallFifo` (so kam der HotPlug-Rückruf bei `SetPortMap`,
  `chan=0x0`, doku/72 Lauf 3),
* `> 4` → `Comm_Add2Call2WQ` → `comm_CallWorkAction` (so kommt `SignalChange`),

und ein Handler sieht damit **beide Klassen genau einmal**. Hätte man stattdessen
in `cpu_comm_userspace_deliver()` selbst eingehakt, bekämen Kernel-Handler die
`>4`-Nachrichten doppelt, weil `comm_CallWorkAction` diese Funktion ein zweites
Mal aufruft.

### Nutzlast im Handler

```c
void my_cb(u32 comp_id, const u32 *args, unsigned int nargs, void *ctx);
```

`args[0]` liegt bei `+0x2C`, `nargs` ist das ParaCount bei `+0x08`, auf 10
begrenzt. Für `MipsHalCallback_SignalChange` gilt: `args[0]` ist der Zustand
(3 = Signal gültig), `args[2]` ein Shmem-**Zeiger** auf die 44-Byte-Signal-Info
(Layout: `analyse/hdmi-seq/signal_info_buf.py`). Den Zeiger aufzulösen ist Sache
des Handlers; die API reicht rohe Wörter durch und deutet nichts.

> **Zählweise, weil sie im Baum uneinheitlich ist.** `args[i]` ist `Para[i]`
> **null-basiert**, so wie `hy310-hdmird` es liest (`main.cpp`: „Para[0] is at
> msg+44") und so wie der Nachtplan die ausgehenden Aufrufe beschreibt
> (`SetHDCP22Key`: `Para[0]` = Adresse; `Vp_Init`: `Para[2]` = Staging). Zwei
> **Diagnosedrucke** zählen dagegen ab 1: die `RX-CALL`-Zeile in
> `cpu_comm_proto.c` („Para 1" für `+0x2c") und der Empfänger in `hdmi_seq.py`
> („Para[1..4]"). Wer eine dmesg-Zeile gegen diese Doku hält, muss die um eins
> verschieben — die Adressen stimmen, nur die Beschriftung zählt anders.

Die Kopie aus dem Shared Memory geht über `memcpy_fromio()` — die Region ist eine
`ioremap()`-Abbildung, kein normaler Speicher.

### Regeln für Handler

* Laufen in **Prozesskontext** auf der Empfangs-Workqueue (`command_action` wird
  über `queueAction` → `schedule_work` gerufen). Schlafen ist erlaubt.
* Aber: sie verzögern die Quittung, auf die der MIPS wartet. Kurz halten, echte
  Arbeit in die eigene Queue.
* **Kein `cpu_comm_call()` aus einem Handler.** Er läuft auf dem Empfangspfad,
  der die Antwort zustellen müsste.
* Ein Handler pro `comp_id`; ein zweiter bekommt `-EBUSY`. Tabellengröße 16.
* `cpu_comm_unregister_callback()` wartet auf einen gerade laufenden Handler,
  danach darf `ctx` freigegeben werden.

### Der alte, kaputte Kernel-Callback ist raus

`comm_CallWorkAction()` las bisher einen Funktionszeiger aus `routine_info + 88`
und sprang ihn an. Zwei Fehler übereinander, beide in doku/72 aufgeschrieben:

1. `FindRoutineEx` füllt den Eintrag bei `+0/+2/+4/+8`, `+12..76` und `+80` —
   die Bytes **88..95 bleiben Stack-Müll**. Das Sprungziel war also
   undefiniert; mal 0 (überlebt), mal ein Restwert (Tod). Das erklärt, warum
   manche Läufe minutenlang standen und andere sofort starben.
2. Selbst am Offset, den der Vendor wirklich benutzt (`+80`), steht dort ein
   **MIPS-kseg0-Zeiger** (`0x8b10abb8` am Gerät). Die Routinentabelle enthält
   Handler-Adressen des MIPS und die Namen, die der Userspace angemeldet hat —
   ein ARM-Kernel-Funktionszeiger stand dort nie.

Es gab dort also nichts, was aufzurufen sich lohnt. Da der Kernel-Empfang jetzt
einen eigenen, richtigen Mechanismus hat, fliegt der Sprung raus, statt ihn zu
umzäunen. Die Quittung an den MIPS bleibt unverändert — genau so verhielt sich
das Modul, das am 06.09. auf dem Tisch lief (dort war der Sprung über den
Modulparameter `callwq_kernel_cb=0` abgeschaltet).

> **Achtung, das ist zugleich eine Rückstufung, die ohne diesen Patch bliebe.**
> Die Schutzmaßnahme vom 06.09. steht **nur** im damaligen Baubaum und im
> Diagnosemodul `/root/hy310-cpu-comm-callwq-test.ko` — **nicht** in
> `patches/kernel/0014-soc-sunxi-add-cpu-comm-ipc.patch`. Der Nachtbau von
> Paket A (`build/linux-6.18.38-e62e8ee3…`) enthält sie folglich nicht.
> Einzelheiten im Teillog.

### Muss die Routine im Shmem angemeldet sein?

**Ja — dieser Abschnitt sagte bis zum 07.09. das Gegenteil und war falsch.**
Richtigstellung samt Belegen: `doku/nachtlog/CALLBACK-luecke.md`.

Kurz: die Zustellung auf dem ARM hängt tatsächlich an `command_action` und nicht
an `FindRoutine` — nur beantwortet das die falsche Frage. Der MIPS sucht den
Empfänger vor dem Senden in der Shmem-Routinentabelle und bricht ohne Eintrag mit
`-3` ab, bevor irgendetwas auf die Leitung geht (`SendComm2CPUEx`, Schritt 2).
Der zweite frühere „Beleg", doku/72 Lauf 18, hing an der Ursachenthese, die
Lauf 21 desselben Dokuments widerlegt hat.

Seit `0092` in der jetzigen Fassung meldet `cpu_comm_register_callback()` die
Routine selbst an (`AddInRoutine` + `Comm_AddNewChannel`, wie `IOCTL_INSTALL_RT`)
und nimmt dafür den **Namen** statt der id. Phase 2 aus `hdmi_seq.py` ist für den
Kernel-Weg damit nicht mehr nötig — und für eine Abnahme des Kernel-Wegs sogar
schädlich, weil sie dieselben Deskriptoren aus dem Userspace anlegt und den
Befund verdeckt.

---

## 3. Verhältnis zum Char-Device-Pfad

| | `/dev/cpu_comm` | In-Kernel-API |
|---|---|---|
| Aufruf | `IOCTL_CALL` → `CPUComm_Call` → `cpu_comm_call_ex(…, 0, false)` | `cpu_comm_call()` → `cpu_comm_call_ex(…, timeout, true)` |
| Fehlender RETURN | Erfolg mit 0 Werten (unverändert) | `-ETIMEDOUT` |
| Fehlercodes | alles wird `-EFAULT` | übersetzt, siehe Tabelle |
| Empfang | `read()`/`poll()`, Ringpuffer 32 tief je Deskriptor | Handler-Aufruf |
| Reihenfolge beim Empfang | zuerst | danach |

**Gegenseitiger Ausschluss.** `cpu_comm_call()` und `IOCTL_CALL` nehmen dieselbe
`cpu_comm_call_mutex`. Unbestritten kostet das nichts und ändert am ioctl-Verhalten
nichts; verhindert wird, dass zwei Aufrufe sich in `SendComm2CPUEx` verschränken.
Dessen eigener Riegel — die Sequenz-Semaphore bei `seq_base + 8` bzw. `+ 1036` —
gibt nach 100 ms auf und macht **trotzdem weiter** („sem timeout, bypassing",
`cpu_comm_proto.c` Schritt 5). Solange es nur einen Aufrufer gab, war das
folgenlos. Ab jetzt gibt es zwei.

Der Empfangspfad nimmt die Mutex **nicht**: ein eingehender Aufruf darf nicht auf
einen ausgehenden warten müssen.

---

## 4. Der debugfs-Prüfstand

Ein Testkonsument im Treiber, damit die Board-Abnahme ohne Userspace-Programm
auskommt. Nur vorhanden, wenn `CONFIG_DEBUG_FS` an ist (im Netboot-Config ist es
das).

```
/sys/kernel/debug/cpu_comm/call     schreiben: Aufruf absetzen, lesen: letztes Ergebnis
/sys/kernel/debug/cpu_comm/watch    schreiben: Handler an/ab, lesen: Tabelle mit Trefferzählern
```

`call` nimmt `<Name|0xID>[@CPU] [Argument …]`. Vorgabe für `@CPU` ist 1 (MIPS);
Argumente gehen durch `kstrtou32(…, 0, …)`, also dezimal oder mit `0x`.

```sh
echo 'THal_Vp_SetSource 3'  > /sys/kernel/debug/cpu_comm/call
cat                           /sys/kernel/debug/cpu_comm/call
# comp=0xeaf13de5 nargs=1 -> ok, 0 value(s)

echo 'THal_Vp_GetSource'    > /sys/kernel/debug/cpu_comm/call
cat                           /sys/kernel/debug/cpu_comm/call
# comp=0x24efc7c9 nargs=0 -> ok, 1 value(s) 0x00000003

echo '0xeaf13de5 3'         > /sys/kernel/debug/cpu_comm/call   # dasselbe roh
```

Ein fehlgeschlagener Aufruf lässt den `write()` mit demselben Fehler scheitern —
`echo` meldet ihn, und die Zeile steht zusätzlich in `dmesg`
(`cpu_comm: debugfs call …`).

`watch` registriert einen eingebauten Protokoll-Handler:

```sh
echo  'MipsHalCallback_SignalChange@0' > /sys/kernel/debug/cpu_comm/watch
echo '-MipsHalCallback_SignalChange@0' > /sys/kernel/debug/cpu_comm/watch   # wieder ab
cat                                      /sys/kernel/debug/cpu_comm/watch
# 0x3e7fbc46      2 MipsHalCallback_SignalChange
```

Jedes Ereignis erzeugt eine `dmesg`-Zeile:

```
cpu_comm: kernel callback comp=0x3e7fbc46 nargs=3 args=[0x00000003 0x00000000 0x4e3ff000]
```

Die Leseansicht zeigt **alle** Kernel-Handler, auch die, die andere Treiber
angemeldet haben; die stehen dort als `(driver)`.

**Gesperrte Routine:** `THal_Vp_EnableScreenCover` (`0x0152F134`) verklemmt
CPU_COMM; nur ein Stromzyklus hilft (doku/67). Der Treiber führt **keine**
Sperrliste — `hdmi_seq.py` tut das und bleibt dafür zuständig. Wer über debugfs
ruft, ruft ungeschützt.

---

## 5. Pflichtliste Punkt #6 — „ACK ohne Cache-Sync gegen Stock"

**Ergebnis: kein fehlender Cache-Sync. Als Stock-gleichwertig abgehakt, ohne
Codeänderung am ACK-Pfad.** Die Begründung im Einzelnen, weil der Punkt seit
Session W (03.05.) als „möglicher Edge-Case" offensteht.

### Was Stock tut

Session W hat `cpu_comm_handle_CPU2_return` `@0xcc94` disassembliert
(`re/notes/HANDOFF-IPC-SESSION-20260503-W.md`):

```
LDRB R3,[R0,#8] / TST #4 / BEQ raus      Bit 2 gesetzt?
AND R3,#0xFB / STRB R3,[R0,#8]           Bit 2 löschen
DMB ISHST
LDRB R3,[R0,#8] / TST #4 / BNE zurück    zurücklesen, bis gelöscht
BL queueAction                            erst dann verzögern
```

und die Offsets je Nachrichtenart aufgeschrieben: `+8` für CALL/RETURN,
**`+105` für die beiden ACKs** (auch doku/65, Abschnitt „Cache-Kohärenz").

### Was wir tun

`cpu_comm_handle_CPU2_callACK`/`_returnACK` verzögern sofort über `queueAction`;
die Prüfung steckt in `ack_action()` (`cpu_comm_proto.c`), das in der Workqueue
läuft:

```c
u8 stat2 = *(u8 *)(share_seq + 105);
if (!(stat2 & 4)) { … "no ACK pending" …; return; }
*(u8 *)(share_seq + 105) = stat2 & ~4;
dmb(ish);
```

Gegenüberstellung:

| Schritt | Stock | wir |
|---|---|---|
| Flag `+105` Bit 2 lesen, sonst raus | ja, im IRQ | ja, in `ack_action` |
| Bit 2 löschen | ja | ja |
| Barriere nach dem Löschen | `DMB ISHST` | `dmb(ish)` (stärker) |
| Zurücklese-Schleife | ja | **fehlt** |
| Reihenfolge | prüfen → verzögern | verzögern → prüfen |
| Semaphore bei `+112` wecken | in `ack_action` | in `ack_action` |

Es fehlt also **nicht** die Prüfung — sie findet an derselben Adresse und mit
demselben Bit statt, nur eine Verzögerung später. Dass Stocks `ack_action` das
Bit nicht noch einmal prüft (unser Kommentar vom 21.04. vermutete einen
„vorherigen Verbraucher"), ist damit erklärt: **der vorherige Verbraucher ist
Stocks IRQ-Handler.** Beide Fassungen verbrauchen das Bit zusammen genau einmal.

Ohne Entsprechung bleibt allein die Zurücklese-Schleife.

### Warum die Schleife hier nichts leisten kann

Sie ist eine Speicher-Abschlussprüfung: warte, bis das gelöschte Bit auch
tatsächlich gelöscht zurückgelesen wird, bevor du weitergehst. Das setzt einen
Cache voraus, der etwas zurückhalten könnte.

`ShMemAddrBase` entsteht in `cpu_comm_init()` aus `ioremap()`. Auf arm64 ist das
`PROT_DEVICE_nGnRE` (`arch/arm64/include/asm/io.h`) — Device-Speicher, ungecacht
und **non-Reordering**: ein Lesen derselben Adresse nach dem Schreiben kann das
Schreiben nicht überholen und liefert den geschriebenen Wert. Die Schleife würde
beim ersten Durchlauf enden. Genau dieses Argument steht schon im Baum, als
Begründung dafür, dass Session Ws `invalidate_kernel_vmap_range()` beim Wechsel
von `vmap()` auf `ioremap()` entfallen ist (`cpu_comm_dev.c`, Kommentar an der
Adoptionsentscheidung): „also gibt es keinen Cache, der etwas Veraltetes
zurückhalten könnte."

Eine Schleife einzubauen, die beweisbar null Durchläufe hat, wäre das
„sicherheitshalber flushen", das Abschnitt 0 des Nachtplans verbietet.

### Warum die andere Reihenfolge hier nichts kostet

Das Flag ist ein einzelnes „ein ACK liegt bereit"-Bit je (CPU, Richtung). Unsere
Fassung könnte ein ACK nur verlieren, wenn ein **zweites** ACK derselben Richtung
einträfe, bevor das erste Work-Item gelaufen ist. Das ist strukturell
ausgeschlossen: `SendComm2CPUEx` nimmt die Sequenz-Semaphore (`seq_base + 8`
lokal, `+1036` entfernt), bevor es den Slot schreibt, und gibt sie erst nach
`cpu_comm_sem_down_timeout(sem_ptr + 16, …)` wieder her — und genau dieses `up()`
macht `ack_action`. Es ist also höchstens ein ACK je Richtung unterwegs.

Der einzige Weg, diese Invariante zu brechen, war der 100-ms-Bypass derselben
Semaphore bei zwei unabhängigen Aufrufern — und den schließt dieser Patch mit
`cpu_comm_call_mutex` (Abschnitt 3).

### Und die Daten, die der ACK-Pfad überhaupt liest

Zwei Wörter: das Flag bei `+105` und die Semaphor-Referenz bei `+112`. Die
Referenz hat der ARM **selbst** veröffentlicht — `SendCommLow(…, cc_ref(sem_ptr + 16))`
legt sie im Schreib-Share-Seq bei `+24` ab; die Firmware spiegelt sie nur zurück
und dereferenziert sie nie (ihr Signalprimitiv `0x8b15c27c` prüft auf NULL und
gibt einen Fehler zurück — deshalb darf U-Boot dort auch 0 hinterlegen, siehe
`cc_ref` in `cpu_comm.h`). Ein veralteter Wert dort scheitert **laut**
(`ack_action: ungueltige Semaphor-Referenz 0x…`), er kann nicht still etwas
zerstören.

Das ist der Unterschied zum CALL/RETURN-Pfad, wo dieselbe Synchronisation
**erforderlich** ist und am 03.05. auch gemessen wurde: dort schützt sie eine
volle 104-Byte-Nutzlast voller MIPS-eigener Zeiger, deren Veralten als
Kernel-Speicherkorruption endete (MIPS-VA `0x8b15b…` in fremden `task_struct`s).
Die Begründung für `+8` überträgt sich nicht auf `+105`.

### Falle für den, der es doch „stock-förmig" machen will

Naiv `cpu_comm_sync_mips_cache(cpu, dir, 105)` in die beiden ACK-Handler zu
setzen, **ohne** gleichzeitig die Prüfung aus `ack_action` zu entfernen,
verbraucht das Bit zweimal: `ack_action` sieht dann „no ACK pending", weckt
niemanden, und **jeder** Aufruf endet in „SendComm2CPUEx: ACK timeout". Das ist
keine Vermutung, sondern folgt direkt aus den beiden Codestellen; es steht so
auch als Warnung im vorhandenen Kommentar.

Eine wirklich stock-förmige Fassung müsste beides zugleich verschieben. Sie ist
möglich und wäre nicht falsch — sie wurde hier **nicht** gemacht, weil sie einen
heute funktionierenden Pfad umbaut für einen auf dieser Abbildung nachweisbar
nicht vorhandenen Gewinn.

**Wann der Punkt wieder aufzumachen ist:** wenn die Shared-Region je cachefähig
abgebildet wird. Dann bekommt die Zurücklese-Schleife wieder eine Bedeutung, und
zwar in **beiden** Handlerfamilien. Der Baum trägt diese Bedingung schon an der
Abbildung selbst: „Wer die Abbildung je auf cachefähig umstellt, braucht hier
wieder eine Invalidierung."

---

## 6. Was der Patch anfasst

| Datei | Art |
|---|---|
| `include/linux/soc/sunxi/h713-cpu-comm.h` | neu — die öffentliche Schnittstelle |
| `drivers/soc/sunxi/cpu_comm/cpu_comm_api.c` | neu — Umsetzung + debugfs |
| `drivers/soc/sunxi/cpu_comm/cpu_comm.h` | interne Deklarationen, `<linux/mutex.h>` |
| `drivers/soc/sunxi/cpu_comm/cpu_comm_rpc.c` | `CPUComm_CallEx` → dünne Hülle um `cpu_comm_call_ex`; der kaputte Zeigeraufruf in `comm_CallWorkAction` entfällt |
| `drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c` | eine Zeile: `cpu_comm_kernel_deliver()` |
| `drivers/soc/sunxi/cpu_comm/cpu_comm_dev.c` | Mutex um `IOCTL_CALL`, debugfs an-/abmelden |
| `drivers/soc/sunxi/cpu_comm/Makefile` | `cpu_comm_api.o` |
| `drivers/soc/sunxi/cpu_comm/Kconfig` | `select CRC32` |

Nicht angefasst: das Shared-Memory-Protokoll, die Semaphorenlage, `cc_ref`,
`SendComm2CPUEx` (bis auf den Aufrufer-Riegel darum herum), der ACK-Pfad,
`cpu_comm_user.c`, alle ioctls außer der Klammer um `IOCTL_CALL`, und die
Zustellung an die Char-Devices (auch die doppelte für `entry_cmd > 4`, die
`comm_CallWorkAction` zusätzlich macht — die bleibt, wie sie ist).

Der Prüfbau steht in [nachtlog/C-cpu-comm.md](nachtlog/C-cpu-comm.md).
