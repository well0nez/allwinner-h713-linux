# CPU_COMM aus Linux: der Round-Trip steht

Stand 04.09.2026. Diese Datei ist die Übergabe: sie soll ausreichen, damit
jemand ohne den Gesprächsverlauf weiterarbeiten kann. Vorgänger:
[66-cpu-comm-arm64-bringup.md](66-cpu-comm-arm64-bringup.md) (erster Round-Trip
aus **U-Boot**) und [65-cpu-comm-abgleich.md](65-cpu-comm-abgleich.md) (die drei
Treibergenerationen gediffed). Was dort im Abschnitt „Der offene Punkt" steht,
ist mit dieser Datei erledigt.

## Das Wichtigste zuerst

**Ein CPU_COMM-Aufruf von Linux an den MIPS läuft vollständig durch, mit
Rückgabewert, reproduzierbar, ohne WARN/BUG/Oops.**

```
[call] 0x2f02f7dd params=[]   RETURN (119.2ms) count=1 values=['0x0']
[call] 0x24efc7c9 params=[]   RETURN (126.7ms) count=1 values=['0x0']
[call] 0x24efc7c9 params=[]   RETURN (126.7ms) count=1 values=['0x0']
[call] 0x2f02f7dd params=[]   RETURN (120.5ms) count=1 values=['0x0']
```

Der Austausch im Treiberprotokoll, ein Aufruf:

```
cpu_comm: msgbox tx raw=0x00000000 (CALL), fifo now 0
cpu_comm: msgbox rx raw=0x00000002 (CALL_ACK)
cpu_comm: TX nach Doorbell: SENT-Bit geloescht -- Firmware hat gelesen (nach 0 x 100us)
cpu_comm: msgbox rx raw=0x00000001 (RETURN)
cpu_comm: msgbox tx raw=0x00000003 (RETURN_ACK), fifo now 0
```

Und die Leitung trägt wirklich Interrupts:

```
332:  12  0  0  0  GICv2  78 Level  cpu_comm-msgbox
```

**Was damit noch nicht gesagt ist:** kein `Set*`-Aufruf ist erprobt, keine
Argumentsignatur ist bekannt, und nichts davon hat bisher ein Bild verändert.
Erprobt sind zwei lesende Routinen.

## Es waren drei Ursachen, nicht eine

### 1. Der MIPS war geparkt - das war der Hauptteil

`bootcmd` lautet ab Werk:

```
bootcmd=h713_disp auto 0x30 logo; dhcp; tftpboot 0x60000000 192.168.8.104:${bootfile}; bootm 0x60000000
```

`h713_disp auto … logo` legt den Coprozessor als **letzte Handlung** still.
Linux startet danach gegen eine tote Firmware: die TX-FIFO `0x03003864` steigt
und fällt nie, das SENT-Bit bleibt stehen, `SendComm2CPUEx` meldet ACK-Timeout.
Es war nie ein Transportfehler - es war niemand da, der abholt.

`0x0306101c` Bit 0 ist der Prüfstein: `1` = Coprozessor läuft. Nach einem
normalen Start steht es auf `0`.

Das hatte der Treiber selbst korrekt gemeldet (`Coprozessor beim Laden steht --
volle Initialisierung`). Diese Meldung wurde am 02.09. als Messfehler abgetan
(„liest vor dem Bus-Gate"). Das war falsch: es ist dasselbe Register und
dasselbe Bit, das cstenger liest, und es ist von Linux aus jederzeit lesbar
(`busybox devmem 0x0306101c`). **Die Fehlersuche verlor daran zwei Tage.**

Unabhängig bestätigt in cstengers `docs/cpu-comm-client-plan.md`, Abschnitt
„Where things stand" (Commit `9ffbc3b`, 03.09.2026).

### 2. `ack_action` gab eine `cc_ref` als Zeiger weiter

`cpu_comm_proto.c`, Ende von `ack_action`. Die Firmware spiegelt bei
`share_seq + 112` die 32-Bit-Referenz zurück, die der CALL mitgegeben hat -
also eine `cc_ref`, keinen nativen Zeiger. Der alte Code:

```c
cpu_comm_sem_up((void *)(unsigned long)*(u32 *)(share_seq + 112));
```

Unsere Semaphoren-Seitentabelle (`cpu_comm_sem.c`, eingeführt weil
`struct semaphore` auf arm64 24 statt 16 Byte hat) sucht nach Adresse. Unter
der getaggten Adresse `0x80001398` fand sie nichts, legte einen **frischen
Semaphor mit Zähler 0** an und weckte niemanden. Symptom: der komplette
Austausch CALL → CALL_ACK → RETURN → RETURN_ACK läuft sauber durch, und
`SendComm2CPUEx` meldet trotzdem ACK-Timeout. Der Hinweis stand im Protokoll:

```
cpu_comm: cc_sem: 80001398 ohne cc_sem_init benutzt, mit Zaehler 0 angelegt
```

Jetzt mit `cc_deref()` davor, plus Fehlerpfad statt stiller Fehlfunktion.
Cstenger hat denselben Fehler unabhängig gefunden und gleich behoben
(Commit `ec53910`).

### 3. Ein 64-Bit-Laden von 4-Byte-Adresse in uncached Memory

`cpu_comm_rpc.c`, `CPUComm_CallEx`, Kopieren der Rückgabewerte:

```c
result[i + 1] = *(unsigned long *)&return_entry[2 * i + 22];   /* falsch */
result[i + 1] = *(u32 *)&return_entry[2 * i + 22];             /* richtig */
```

Die Vorlage stand auf arm32, wo `unsigned long` 32 Bit ist. Auf arm64 wird
daraus `ldr x11, [x8], #4` - ein Doppelwort von einer nur 4-Byte
ausgerichteten Adresse. Die Shared-Region ist uncached gemappt, also
Device-Memory, und dort ist das ein Alignment-Fault (FSC 0x21).

Der **erste** Aufruf überlebte nur, weil er `count=0` lieferte und die Schleife
nie betrat. Der erste Aufruf mit `count=1` riss den Prozess mit:

```
pc : CPUComm_CallEx+0x184/0x28c [hy310_cpu_comm]
Code: 34000148 aa1f03ea 9100b2a8 910012c9 (f840450b)
```

`f840450b` = `ldr x11, [x8], #0x4`. Nach dem Fix `b840450a` = `ldr w10, …`.

Dieselbe Klasse wie cstengers `memcpy`-Fault auf dem Namensfeld der
Routine-Tabelle (`memcpy_fromio` statt `memcpy`). **Es ist die wahrscheinlichste
verbleibende Fehlerklasse im ganzen Treiber:** überall dort, wo die arm32-Vorlage
`unsigned long`, `long` oder einen Zeiger als 32-Bit-Wort behandelt hat.
Der Bestand ist geprüft - es gab genau diese eine Stelle mit
`*(unsigned long *)`, und die `*(u64 *)`-Zugriffe liegen alle auf
8-Byte-Grenzen. Bei jeder Erweiterung erneut prüfen.

## Zwei weitere Fehler, gefunden am 04.09.

### 4. `CPUComm_CallEx` schrieb die tgid über Parameter 3

`cpu_comm_rpc.c`. Die Nutzlast beginnt bei `+0x28` (comp_id); der Adapter
bekommt einen Zeiger dorthin und liest seine Argumente bei `+4/+8/+12`, also
`msg+0x2c/+0x30/+0x34`. **`+0x34` ist damit Parameter 3.** Dort stand:

```c
*(u32 *)(local_msg + 52) = (u32)current->tgid;   /* raus */
```

Für zwei Argumente folgenlos, für drei genau der dritte Ausgabezeiger. Die
Absender-pid steht ohnehin bei `+0x1c` (`cpu_comm_proto.c`, `call_slot + 28`).

**Die abgewendete Gefahr ist konkret:** der Adapter maskiert jedes Argument auf
28 Bit und ODERt `0xa0000000`, also ARM-physisch `(v & 0x1fffffff) + 0x40000000`.
Eine tgid von etwa 1000 ergibt `0x400003e8` - mitten in `secure-bl31@40000000`.
`Wce_GetWindow` hätte den Skalar `2` in TF-As BL31-Region geschrieben. Nach dem
Fix bleibt `+0x34` durch das `memset` null, und der Adapter überspringt
Nullzeiger per `movz` - zu wenige Argumente sind damit harmlos statt gefährlich.

Beweis am Gerät, frischer Scratch, drei Ausgabeadressen:

```
[call] 0xfd483f67 params=['0x4d840000','0x4d840010','0x4d840020']
  RETURN (119.5ms) count=1 values=['0x1']
  OUT1 0x4d840004=0x00007800  0x4d84000c=0x00004380     1920x1080
  OUT2 0x4d840014=0x00007800  0x4d84001c=0x00004380     1920x1080
  OUT3 0x4d840020=0x00000002                            <-- der Skalar
```

`OUT3 = 2` ist exakt, was cstengers Call-Table für `Wce_GetWindow` vorhersagt.
Cstenger hat denselben Fehler unabhängig gefunden (Commit `ec53910`).

### 5. Der RX-Diagnosedruck war um ein Feld verschoben

`cpu_comm_proto.c`, eingehender CALL. Er las `+0x34` als `pid` und sprang dann
auf `+0x38`/`+0x3c` weiter - zeigte also die Parameter **1, 2, 4, 5** und
beschriftete Parameter 3 als pid. Rein diagnostisch, ohne Funktionsfolge - aber
**genau der Druck, an dem die MIPS→ARM-Callbacks abgelesen werden**. Jetzt
korrekt indiziert, plus `chan_pid` bei `+0x10`, dem Feld, das den Aufruf
überhaupt zuordnet.

Ungetestet: der Druck feuert erst bei einem eingehenden CALL, und dafür muss die
Firmware einen Callback auch *benutzen*, nicht nur registriert vorfinden.

**Modulstand:** `fc570ab6cc46e3a1`, 215520 Byte. Die Vorgängerfassung liegt als
`hy310-cpu-comm.ko.05b6daca-backup` daneben.

## Das Rezept - seit 04.09. nur noch Strom an

**Die `bootcmd` ist persistent.** `saveenv` ist geschrieben:

```
bootcmd=h713_disp init 0x30; dhcp; tftpboot 0x60000000 192.168.8.104:${bootfile}; bootm 0x60000000
```

Ein Stromzyklus genügt; der MIPS kommt von selbst hoch. Zweimal verifiziert:
`0x0306101c` liest nach dem Boot ohne jeden Handgriff `1`. Kein UART-Fänger,
kein Prompt, kein `h713_disp init` von Hand - **im Gegenteil, das wäre
schädlich**: `init` gilt einmal pro Stromzyklus, und `bootcmd` ruft es selbst.

Erwartete Belege in der Boot-Ausgabe:

```
H713 MIPS: released, status=0x00000001
H713 MIPS: firmware execution proven (witness overwritten)
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
H713 MIPS: firmware readiness proven by MIPS READY
H713 MIPS: application readiness proven
```

**Preis:** das Gerät startet ohne Bootlogo, das Panel bleibt beim Booten
schwarz. Rückweg jederzeit: `setenv bootcmd 'h713_disp auto 0x30 logo; …'`
plus `saveenv`.

Das Logo-Init steht bei uns in `bootcmd`, **nicht** in `preboot` - dort steht
nur die Fastboot-Magic-Prüfung und `usb start`. (Bei cstenger ist es umgekehrt;
seine Notizen nennen `preboot`.)

Nur wenn man doch an den Prompt muss:

```bash
fuser -v /dev/ttyACM0        # nur EIN Leser, sonst ist jede Messung wertlos
tools/uart-uboot.py catch    # dann Strom ziehen und wieder anstecken
```

`h713_disp init 0x30` **ohne** `elog=`; mit `elog=3` wird der MIPS nicht
rechtzeitig bereit (dreimal belegt, beide Richtungen). Erwartete Belege in der
Ausgabe: `MIPS=00000005`, `firmware readiness proven by MIPS READY`,
`application readiness proven`. Das Panel bleibt bei `init` schwarz, das ist
dort erwartet und kein Befund.

Dann auf dem Board (IP wechselt bei jedem Start, `CONFIG_NET_RANDOM_ETHADDR`;
finden mit `ss -tn | grep :2049` auf dem Host):

```bash
insmod /lib/modules/6.18.38/kernel/drivers/soc/sunxi/cpu_comm/hy310-cpu-comm.ko
python3 /root/rpc_test.py call 0x2f02f7dd      # GetImageBufferAddr, lesend
python3 /root/rpc_test.py call 0x24efc7c9      # GetSource, lesend
```

`modprobe.blacklist=hy310_cpu_comm` steht in den `bootargs`: ein fehlerhaftes
Modul kostet damit ein `insmod`, keinen Startvorgang.

**`rmmod` + `insmod` funktioniert** und der MIPS überlebt es - geprüft am
04.09., zweimal, auch einmal aus einem angeschlagenen (`Tainted: D`) Kernel
heraus. Das ist die schnelle Schleife. Die frühere Notiz „Hot-Swap tötet den
MIPS" bezog sich auf den geparkten Zustand und ist damit erledigt.

## Wo was liegt

| Pfad | Was |
|---|---|
| `analyse/cpu-comm-arm64/` | **die gepflegten Quellen.** Drei-Wege-Merge aus `legacy/drivers/Archived/cpu_comm/` (Basis), `legacy/drivers/cpu_comm/` (unser arm32-Stand) und cstengers Patch 0014. Hier wird editiert. |
| `mainline/patches/kernel/0014-soc-sunxi-add-cpu-comm-ipc.patch` | daraus erzeugt, 10852 Zeilen, sha256 `9ee16de1…` |
| `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig` | `CONFIG_HY310_CPU_COMM=m` |
| `mainline/patches/kernel/0024-…dts….patch` | Msgbox `reg = <0x03003000 0x1000>`, `interrupts = <GIC_SPI 46 …>`, `&cpu_comm { status = "okay" }` |
| `legacy/drivers/cpu_comm/` | unser arm32-Stand, die Herkunft der meisten Kommentare |
| `legacy/drivers/Archived/cpu_comm/` | der ältere Stand, auf dem cstengers Patch 0014 beruht |
| Board: `/lib/modules/6.18.38/kernel/drivers/soc/sunxi/cpu_comm/hy310-cpu-comm.ko` | über NFS aus `/srv/h713-rootfs/usr/lib/…` |
| Board: `/root/rpc_test.py` | der Aufrufer. `call <id|Name> [args…]`, `id <Name>`, `callbacks` |

**Falle beim Patch-Erzeugen:** `analyse/cpu-comm-arm64/Makefile` ist die
**Out-of-Tree**-Fassung (`obj-m +=`, `ccflags-y := -DCONFIG_ARM_CPU_COMM`).
Der Patch braucht die In-Tree-Fassung (`obj-$(CONFIG_HY310_CPU_COMM) +=`, ohne
`ccflags`). Beim Neuerzeugen aus dem Kernelbaum nehmen, nicht aus `analyse/`.

### Patch neu erzeugen

```bash
S=/tmp/scratch; M=/opt/Projekte/h713/analyse/cpu-comm-arm64
K=/opt/Projekte/h713/mainline/build/linux-6.18.38-102233d4db…
mkdir -p $S/gen/a/drivers/soc/sunxi/cpu_comm $S/gen/b/drivers/soc/sunxi/cpu_comm
cp $M/*.c $M/*.h $M/Kconfig $S/gen/b/drivers/soc/sunxi/cpu_comm/
cp $K/drivers/soc/sunxi/cpu_comm/Makefile $S/gen/b/drivers/soc/sunxi/cpu_comm/
printf '*.o\n*.ko\n*.mod*\n*.cmd\n' > $S/gen/b/drivers/soc/sunxi/cpu_comm/.gitignore
(cd $S/gen && diff -ruN a b) > $S/neu.diff
# die beiden Hunks fuers Elternverzeichnis aus dem alten Patch anhaengen:
awk '/^--- a\/drivers\/soc\/sunxi\/Kconfig/,0' <alter-patch> >> $S/neu.diff
```

Danach gegenprüfen: den Patch in ein leeres Verzeichnis auspacken und mit dem
Kernelbaum vergleichen - sie müssen identisch sein.

### Nur das Modul neu bauen (schnell, ohne Container)

Der Container `h713-build` ist leer (LLVM 20 nicht installiert). Der Host hat
clang 18 und die LLVM-Binutils als `-18`; für ein einzelnes Modul reicht das:

```bash
S=/tmp/scratch; mkdir -p $S/bin
for t in ar nm objcopy objdump readelf strip; do ln -sf /usr/bin/llvm-$t-18 $S/bin/llvm-$t; done
ln -sf /usr/bin/clang $S/bin/clang; ln -sf /usr/bin/ld.lld $S/bin/ld.lld
cp $M/*.c $M/*.h $K/drivers/soc/sunxi/cpu_comm/
PATH="$S/bin:$PATH" make -C $K ARCH=arm64 LLVM=1 -j24 modules
cp $K/drivers/soc/sunxi/cpu_comm/hy310-cpu-comm.ko \
   /srv/h713-rootfs/usr/lib/modules/6.18.38/kernel/drivers/soc/sunxi/cpu_comm/ && sync
```

Der volle Serienbau (`build/build.sh kernel`) mit der gepinnten LLVM 20 ist mit
diesem Patchstand **nicht** gelaufen. Der Patch ist auf Quellebene geprüft
(er reproduziert exakt die Dateien, aus denen das laufende Modul gebaut wurde),
aber ein Serienbau steht aus.

Modul: 215520 Byte, sha256 `05b6daca0bee9fe733b3efd652e698d30f0befaf517e7e6a0834a027b592d547`.
`sync` vor jedem Test, und die sha auf dem Board gegen den Host prüfen - ein
veraltetes Modul hat in diesem Projekt schon eine erfundene Messung erzeugt.

## Konstanten

### Msgbox `0x03003000`

| Adresse | Bedeutung |
|---|---|
| `0x03003810` | Version, liest `0x00020000` wenn getaktet |
| `0x03003830` | TX IRQ enable, `BIT(3)` = `BIT(2*port+1)`, MIPS = Port 1 |
| `0x03003864` | TX-FIFO-Zählerstand ARM → MIPS |
| `0x03003874` | TX MSG_DATA - **das ist der Doorbell** |
| `0x03003120` | RX IRQ enable, `BIT(2)` = `BIT(2*port)` |
| `0x03003124` | RX IRQ status, write-1-to-clear |
| `0x03003164` | RX-FIFO-Zählerstand MIPS → ARM |
| `0x03003174` | RX MSG_DATA |
| `0x0200171c` | Bus-Gate, Bits 0 und 16 |

Blockstruktur (von cstenger aus dem Vendor-Treiber belegt, deckt sich mit allen
unseren Adressen): 0x100-Byte-Blöcke je User, darin `+0x20` RX-Enable,
`+0x24` RX-Status (W1C), `+0x30` TX-Enable, `+0x34` TX-Status, `+0x60` FIFO-Zähler
`+ 4*port`, `+0x70` MSG-Daten `+ 4*port`.

Doorbell-Kodierung: **nur der nackte Nachrichtentyp**, 0 = CALL, 1 = RETURN,
2 = CALL_ACK, 3 = RETURN_ACK. Die H713-Msgbox ist flankengesteuert, deshalb
muss `TX_IRQ_EN` gepulst werden (setzen, 10 µs, löschen).

**Achtung:** `cpu_comm_dev.c` schickt beim Probe einen „Doorbell" nach
`0x03003070` - das ist ARMs **eigene** Bank, nicht die des MIPS. Der geht ins
Leere. Altlast aus der arm32-Vorlage, bisher folgenlos, gehört entfernt.

**Doppelte Definitionen:** `cpu_comm_hw.c` definiert `H713_MSGBOX_RX_FIFO`,
`_RX_DATA`, `_TX_DATA`, `_TX_FIFO` zweimal (Zeilen ~78 und ~153), mit identischen
Werten - deshalb ohne Warnung. Beim Aufräumen zusammenlegen.

### Interrupt

Unser DTS: `interrupts = <GIC_SPI 46 IRQ_TYPE_LEVEL_HIGH>` → GICv2 hwirq 78.
**Die Leitung trägt RX** (12 Treffer nach vier Aufrufen), und der Treiber
läuft interruptgetrieben.

`GIC_SPI 21` (hwirq 53) ist die falsche: sie stürmt und wird bei exakt 100000
maskiert. Wir haben das gemessen und cstenger unabhängig ebenfalls - er hält
die Msgbox-IRQ deshalb für unbrauchbar und ist auf einen hrtimer-Poll
ausgewichen (250 µs schnell nach dem Senden, 4 ms im Leerlauf). **Das ist ein
Befund für ihn:** auf SPI 46 funktioniert der Interrupt.

### share_seq, aus den U-Boot-Konstanten

| Name | Wert |
|---|---|
| `H713_COMM_CALL_SEQ_OFF` | `0x26b8` |
| `SEQ_FIFO_OFF` | `0x078` (rd `+0`, wr `+4`, cap `+0x10`, isz `+0x14`, base `+0x18`) |
| `SLOTS_OFF` | `0x168` |
| `RING_OFF` | `0x0c0` |
| `MSG_FLAG_SENT` | Bit 2 bei `share_seq + 0x08` |
| ACK-Semaphor-Referenz | `share_seq + 112` - **immer durch `cc_deref()`** |

Berechnung des Sequenzzeigers (die Stelle, an der die u32-Abschneidung saß):

```c
unsigned long addr = ShMemAddrBase + 9760*1 + 4880*r + 2440*d + 152;
```

### Nachrichtenlayout

| Offset | Feld |
|---|---|
| `+0x00` | chan (u16) |
| `+0x02` | dst_cpu (u16) |
| `+0x04` | index |
| `+0x06` | flags |
| `+0x08` | Parameteranzahl (u16) |
| `+0x0a` | msg_type / flags2, `MSG_FLAG_SENT` |
| `+0x0c` | session |
| `+0x10` | **Kanal-pid** - nicht „dst_cpu erweitert" |
| `+0x20` | Wait-Referenz (`cc_ref`) |
| `+0x28` | comp_id - **der Adapter bekommt einen Zeiger hierauf** |
| `+0x2c` | Parameter 1 |
| `+0x30` | Parameter 2 |
| `+0x34` | Parameter 3 - **nicht nullen** |

Kanalschlüssel: `(pid << 4) | (chan & 0xf)`. Ein CALL, dessen Schlüssel keiner
Zeile der Firmware-Kanaltabelle entspricht, wird auf Transportebene bestätigt
und dann **stillschweigend nie ausgeführt** - Symptom: CALL_ACK, kein RETURN.

**Argument-ABI (von cstenger korrigiert, Commit `ec53910`):** es gibt *keinen*
Dummy-Parameter. Der Adapter erhält die Nachricht bei `+0x28`, seine Ladebefehle
bei `+4/+8/+12` lesen also die ersten drei Nutzwerte ab `+0x2c`. Die alten
U-Boot-Versuche schickten eine führende `0` und haben damit den *ersten*
Ausgabezeiger jedes Adapters genullt; was für `p1` gehalten wurde, bekam in
Wahrheit die zweite Ausgabe. **Die Datei `tools/uboot-hdmi-sequence.txt` ist
danach zu prüfen.**

### Routine-Tabelle

`0x4e3075c0` Version, `+4` Anzahl, Einträge ab `0x4e3075c8`, 96 Byte je Eintrag:
`+0x00` flags, `+0x02` cpu (u16), `+0x04` pid, `+0x08` comp_id/routine id,
`+0x0c` Name (32 Byte, **nicht** nullterminiert), `+0x50` Handler, `+0x5c` next.
U-Boot zeigt Version 162, Anzahl 81.

**Der Name muss mit `memcpy_fromio()` gelesen werden.** Die Region ist uncached
gemappt; `memcpy`s breite unausgerichtete Ladebefehle nehmen dort einen
Alignment-Fault. Dieselbe Falle wie Ursache 3.

Cstenger hat dafür `/proc/cpu_comm/routines` gebaut (Commit `ec53910`) - die
Tabelle live, mit Namen. **Das sollten wir übernehmen**, es ist die Karte von
„Routine, die etwas tut" zu „Zahl, mit der man sie ruft".

### Adressumrechnung

- MIPS-Code/Daten: physisch = VA − `0x40000000`; KSEG genauer:
  `(kseg & 0x1fffffff) + 0x40000000`
- MMIO in `display.bin`: ARM-physisch + `0xB5000000`
- Shared Memory: `0x4E300000`, 5 MiB, `no-map`
- `cc_ref` / `cc_deref`: Bit 31 gelöscht = ARM-physisch in der Shared-Region;
  Bit 31 gesetzt = getaggte, treiberprivate Arena

## Was cstenger seit `176cb7d` neu hat

Sein zweiter Branch `origin/h713-display-video-path` steht bei `83f0974`
(03.09.2026). Neu sind ~90 Commits; für uns zählen zwei:

**`ec53910` - `cpu_comm: correct the argument ABI, and stop BUG()ing on client input`**

- Argument-Indexierung korrigiert (siehe oben), inklusive der Erkenntnis, dass
  `+0x34` Parameter 3 ist und nicht genullt werden darf
- sechs `BUG()` behoben, **alle sechs wurden getroffen, sobald echter Verkehr den
  Pfad zum ersten Mal berührte.** Etwa 90 bleiben stehen - grob 23 in `rpc.c`,
  21 in `channel.c`, 20 in `mem.c`. Sie sind nicht geprüft, nur unbenutzt.
- `errno` ist erstmals aussagekräftig: `ETIME` = Firmware hat bestätigt und nie
  geantwortet, `ESRCH` = MIPS geparkt
- `memcpy_fromio` für die Namensfelder
- `/proc/cpu_comm/routines`
- Kanal-Discovery im Treiber: liest `*(0x8b22efe4) + 0xa8`, 16 Zeilen à 48 Byte,
  mit Selbsttest gegen `getCurCPUID` bei `0x8b1227b4` (`03e00008 24020001`).
  **Diese Konstanten sind auf sein Board kalibriert**, bei uns ungeprüft.
- `cc_ref` grundlegend umgestellt: keine getaggten Refs mehr, echte
  Physadressen; `s_CommSockt` wird `kzalloc`t statt Modul-`.bss`, weil
  `virt_to_phys()` auf Modul-BSS falsch rechnet (gemessen: `0x4124f000` gegen
  echte `0x449ba000`, Folgeseite 27 MiB entfernt).
  **Wir sind hier bewusst anders** - unsere getaggten Refs sind für den MIPS
  undurchsichtig, und der dereferenziert sie nachweislich nicht. Nicht
  vermischen, ohne beides zu verstehen.
- RX per hrtimer-Poll statt IRQ, `rx_irq=1` als Schalter (siehe „Interrupt")

**`9ffbc3b` - `re: CPU_COMM from Linux closes the suppression clears and SetSource`**

- die Voraussetzung „Coprozessor muss leben", `0x0306101c == 1`
- `docs/cpu-comm-client-plan.md`: Ioctl-ABI (168-Byte-Puffer, comp_id bei `+40`,
  Parameter ab `+64`, Ergebnis ab `+120`), Testprotokoll, Gefahrenliste
- drei Unterdrückungs-Aufrufe aus Linux, alle `nret=0`, 30-86 ms - und die
  Feststellung, dass der Test vom 30.08. ungültig war, weil das Logo auf dem
  **OSD**-Kanal `0x05600140` liegt, die Routinen aber auf dem **Video**-Kanal
  `0x05600100` arbeiten. Der Versuch konnte einen Erfolg gar nicht sehen.
- `THal_Vp_GetSource`s Handler bei `0x8b14b524` gibt **immer** 0 zurück, ohne den
  privaten Quellzustand zu lesen. Seine 0 war nie ein Gegenbeweis.

Sein Ergebnisformat ist `RETURN`/`nret`; unsere Laufzeiten liegen bei ~120 ms,
seine bei 17-30 ms. Siehe „Offen".

## Für cstenger

1. **`GIC_SPI 21` ist die falsche Leitung.** Auf `GIC_SPI 46` (GICv2 78) trägt
   die Msgbox-IRQ RX sauber, ohne Sturm, ohne Maskierung. Sein hrtimer-Poll ist
   ein Umweg um ein DTS-Problem.
2. Sein Patch 0014 stammt aus unserem `Archived/`-Stand, nicht aus dem neueren.
   Details in [65-cpu-comm-abgleich.md](65-cpu-comm-abgleich.md).
3. `commdev`-Selbsttest und `H713_COMM_DEV_PTR` sind auf Board B kalibriert und
   gehören hinter `h713_mips_fw_rev`.
4. Der `request_irq`, der sich nie registrierte (in seinem älteren 0014).

## Offen

| Punkt | Was wir wissen |
|---|---|
| **~120 ms je Aufruf** | Er misst 17-30 ms mit Poll, wir 120 ms mit IRQ. Auffällig gleichmäßig, riecht nach einer festen Verzögerung im Pfad, nicht nach Firmwarearbeit. Im Protokoll liegen zwischen CALL und RETURN_ACK nur ~85 ms. Noch nicht untersucht. |
| ~~**~90 `BUG()`**~~ **erledigt 04.09.** | Die Zahl war cstengers und galt seinem Baum. Unserer hat **null** lebende `BUG()` - die zwei `grep`-Treffer stehen im Kommentartext. Nach Kommentar-Entfernung: 0, dazu 64 `WARN_ON` und 0 `BUG_ON`. Der arm32-Zweig hat sie am 22.04. abgeräumt (Session K-night, doc 65). Zum Vergleich: seine Branch-Spitze hat 91. Der `INSTALL_RT`→`AddInRoutine`→`Comm_AddNewChannel`-Pfad ist damit `BUG()`-frei. |
| **Argumentsignaturen** | Unbekannt. Die Tabelle liefert Namen und ids, sonst nichts. Ehrlich klären lässt sich das nur an der Firmware: `tools/mips/disasm.py`, Basis `0x8b100000`, MIPS-VA `0x8b1xxxxx` = ARM-physisch `0x4b1xxxxx`. **Ein erfolgreicher Rückgabewert beweist keine Signatur** - ein CALL mit passendem Schlüssel wird ausgeführt, egal ob die Argumente sinnvoll sind. |
| **`&buf[1]` im Listener-Pfad** | `cpu_comm_dev.c` ~Zeile 815: `*(u64 *)&buf[1]` bei `u8 buf[64]` ist Byte-Offset **1**, der Kommentar meint Offset 4. Kein Absturz (Stack, normales Memory), aber es vergleicht die falschen Bytes. Nicht auf unserem Pfad, ungeprüft. |
| **Serienbau** | Der volle `build/build.sh kernel` mit LLVM 20 ist mit diesem Patchstand nicht gelaufen. |
| ~~**`bootcmd` ist flüchtig**~~ **erledigt 04.09.** | `saveenv` ist geschrieben. `bootcmd=h713_disp init 0x30; dhcp; tftpboot …; bootm …`, zweimal per Kaltstart verifiziert: `0x0306101c` liest ohne Handgriff `1`. **Folge: das Gerät startet ohne Bootlogo**, das Panel bleibt beim Booten schwarz. Rückweg: `setenv bootcmd 'h713_disp auto 0x30 logo; …'` + `saveenv`. Das Logo-Init steht bei uns in `bootcmd`, **nicht** in `preboot` (dort nur Fastboot-Magic + `usb start`). |
| **Nichts hat ein Bild verändert** | Zwei lesende Routinen, beide liefern `0x0`. Der nächste sinnvolle Schritt ist `Wce_GetActiveWindow` mit zwei echten Ausgabeadressen - ein typisierter, lesender Aufruf, der die Argument- und Ergebnispfade wirklich belastet. |

## Betriebliches und Gefahren

- **Niemals `0152f134`** (`THal_Vp_EnableScreenCover`). Wedgt CPU_COMM; danach
  wird auch der No-Op nie wieder angenommen und `reset` gibt keine Ausgabe mehr.
  Nur ein physischer Stromzyklus hilft. Gehört als Sperre in den Aufrufer, nicht
  ins Gedächtnis des Bedieners.
- **`h713_disp init` gilt einmal pro Stromzyklus.** `tools/uart-uboot.py catch`
  prüft das Kaltstart-Banner und wartet weiter, wenn nur der alte Prompt steht.
- **Ein Leser pro UART.** Läuft noch ein Mitschnitt, frisst er die Bytes und
  jede Messung ist wertlos. Einmal passiert, mit falscher Schlussfolgerung.
  `uart-watch.py` prüft das selbst und bricht ab.
- **`SetSource` kommt zuletzt.** Am 01.09. an Position 2 gerufen: kein RETURN,
  der einzige BG_Thread der Firmware blockierte, alle folgenden Aufrufe liefen
  ins Leere. Erholung nur per Stromzyklus.
- **TVTOP `0x068B0000` nicht aus Linux lesen** - wedgt den SoC.
- **Nach einem Modul-Oops nicht `reboot`.** Stattdessen `sync`, dann
  `echo b > /proc/sysrq-trigger`. `sysrq-b` synchronisiert *nicht* selbst - ohne
  `sync` ist ein frisch kopiertes Modul aus dem Seitencache verloren und das
  Board läuft mit dem *vorherigen* Bau weiter, was wie ein Codefehler aussieht.
  **Achtung 04.09.:** im Kernelbaum, gegen den wir bauen, ist
  `CONFIG_MAGIC_SYSRQ` **nicht gesetzt** - dann gibt es weder
  `/proc/sysrq-trigger` noch SysRq über die serielle Konsole. Dieser Rettungsweg
  ist also womöglich gar nicht vorhanden; beim nächsten Boot gegen
  `/proc/config.gz` gegenprüfen. Wer daraus schließt „der Kernel ist tot, weil
  SysRq nicht antwortet", misst mit einem Gerät, das kein Positiv zeigen kann.
- **Warmstart hilft nicht** für den MIPS: er liefert den Prompt, gated aber die
  Display-Blöcke wieder. Statische Speicherinhalte (Call-Tabelle, elog) beweisen
  dann nur, dass er *lief*.
- **`/srv/h713-rootfs` gehört root** und braucht das `sudo` des Nutzers.
- **Kein `strace`** auf echter Echtzeit-HW-IPC.
- `elog=3` verhindert die MIPS-Bereitschaft. Nicht in `bootcmd` speichern.

## Methode

Zwei Fehlschlüsse in dieser Portierung hatten dieselbe Form, und beide haben
Tage gekostet:

1. **Eine Meldung des Systems als Messfehler abtun.** `Coprozessor beim Laden
   steht` war korrekt und wurde wegerklärt. Wer eine Selbstauskunft anzweifelt,
   muss den Zweifel messen - `busybox devmem 0x0306101c` hätte 30 Sekunden
   gedauert.
2. **Eine Suche, die „nichts" antwortet, nicht prüfen.** `grep -r` unter `/tmp`
   lieferte nichts und erzeugte eine komplett falsche Merkmalstabelle; `find`
   mit `hy310_cpu_comm.ko*` fand das Modul nicht, weil es
   `hy310-cpu-comm.ko` heißt. Cstengers eigene Formulierung dafür:
   *„When a scan answers 'none', check that it could have seen one."*

Und eine dritte, die hier gut ausging: der erste Aufruf lief durch und sah nach
Erfolg aus - er lief nur durch, weil `count=0` die fehlerhafte Schleife
übersprang. **Ein grüner erster Versuch ist kein Beweis, solange nicht der Pfad
gelaufen ist, der etwas tun muss.**

## Querverweise

- [65-cpu-comm-abgleich.md](65-cpu-comm-abgleich.md) - die drei Generationen
  gediffed, Merkmalstabelle, Doorbell-Vergleich, FreeCall-FIFO
- [66-cpu-comm-arm64-bringup.md](66-cpu-comm-arm64-bringup.md) - erster
  Round-Trip aus U-Boot, fünf behobene Fehler, Session Z reproduziert
- [50-befehle.md](50-befehle.md) - Bauen, U-Boot-Prompt, `uart-uboot.py`
- [63-mips-elog.md](63-mips-elog.md) - elog-Ring und Dekodierung
- [70-sackgassen.md](70-sackgassen.md) - ausgeschlossen, mit Beleg. Zuerst lesen.
- [95-netboot.md](95-netboot.md) - TFTP, NFS, Environment
- `re/notes/CONTRADICTIONS.md` - die IRQ-Auflösung, jetzt durch Hardware
  entschieden
- `re/notes/cstenger-branch/` - seine Handoffs, gespiegelt
- `tools/uart-uboot.py`, `tools/uart-watch.py`, `tools/uboot-hdmi-sequence.txt`
- cstengers Baum: `docs/cpu-comm-client-plan.md`,
  `docs/reference/cpu-comm-call-table.md`,
  `docs/reference/cpu-comm-routine-table-2026-08-30.txt`
