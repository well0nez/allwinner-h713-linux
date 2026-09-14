# Phase 3.5 und 4 am 05.09.2026: `ReloadHdcp14Key` ohne Wirkung, `SetSource(3)` hängt den SoC

Fortsetzung des Plans aus [69-handoff-20260905.md](69-handoff-20260905.md), nach
der Klärung der `tvtop`-Frage in [71-tvtop-noetig.md](71-tvtop-noetig.md).
Alles am Board (`root@192.168.8.141`), Firmware-Belege aus dem
Stock-`display.bin` (md5 `0d2191ca`).

## Ergebnis in drei Sätzen

1. **`THal_Vp_HDMI_ReloadHdcp14Key` (`0x449effe8`) nimmt kein Argument**, läuft
   sauber durch (RETURN, 0 Werte) und bewegt **nichts** — kein elog-Byte, kein
   Flag. Stock ruft es genauso argumentlos in seiner Init-Sequenz.
2. **Der HDCP-1.4-Ladepfad kann in dieser Firmware gar kein Positiv zeigen:**
   U-Boot hat die Warteschleife von `HdmiRx_HDCP14_LoadKey` entschärft
   (`0x4b13d0a4` liest `0x2c630000` statt `0x2c630033`).
3. **`SetSource(3)` hängt den SoC hart** — auch nach vollständiger Phase-3-Sequenz,
   Stock-Reihenfolge, 1 s Pause, Callbacks angemeldet. Dritter Absturz an dieser
   Stelle. **Es gibt keinen Watchdog** — das Board bleibt tot bis zum
   Stromzyklus (das „nach 40 s wieder da" vom 05.09. war der manuelle Neustart
   des Nutzers, kein Watchdog).

## 3.5 — HDCP 1.4

### Die Signatur, aus dem Adapter

Routine-Tabelle (Shmem `0x4e3075c8`), Slot 1000, Handler `0x8B10AC30`:

```
0x8b10ac30  addiu sp,sp,-0x18
0x8b10ac3c  jal   0x8b148c7c          THal_Vp_HDMI_ReloadHdcp14Key
0x8b10ac40  move  s0,a1
0x8b10ac48  sw    zero,0x0(s0)        nret = 0
```

**Kein `lw` aus dem Nachrichtenpuffer** — zum Vergleich der Nachbar
`SetHDCP22Key` (`0x8b10abb8`): `lw v1,0x4(a0)` (Zeiger, auf 28 Bit maskiert,
`| 0xa0000000`) und `lw a1,0x8(a0)` (Größe). Die Frage aus doku/69, ob die
Routine einen Zeiger nimmt, ist damit entschieden: **nein.**

Stock ruft sie so (`re/captures/weltneuheit/main-clean.txt:2461`), direkt
zwischen `SetPortMap` und `SetHPDTimeInterval`:

```
THal_Vp_HDMI_SetPortMap_1_000()        pRoutine:8B10ABF8
THal_Vp_HDMI_ReloadHdcp14Key_1_000()   pRoutine:8B10AC30
THal_Vp_HDMI_SetHPDTimeInterval_1_000() pRoutine:8B10AC58
```

`hdmi_seq.py` kennt diesen Schritt nicht; er fehlt zwischen `hdcp22` und
`hpdint`.

### Was die Routine tut

`0x8b148c7c`: Log (Stufe 4), Geräteobjekt holen (`0x8b183a54`), **vtable[3]
mit Argument 3** rufen; nur wenn das etwas zurückgibt, Nachricht **7** posten
(`0x8b106bec`). Der Empfänger `HDMIRX_Hdcp14_ReloadKey` (`0x8b130800`) ist ein
**Stub, der nur loggt** (Stufe 3, dieselbe Stufe wie die sichtbaren HDCP-2.2-Zeilen).

### Der Aufruf am Gerät

```
elog write vorher: 0x814
[call] 0x449effe8 params=[]   RETURN (186.0ms) count=0 values=[]
elog write nachher: 0x814        <- kein Byte
HPD-Gate 0x4b271c2c: 1 (unverändert)
```

Kein elog-Eintrag, obwohl der Stub auf Stufe 3 loggen würde. Also hat
entweder vtable\[3\](3) ohne aktive Quelle nichts geliefert (dann wird nichts
gepostet), oder die Nachricht landet nirgends. Session N (24.04.) sah dasselbe
(„no visible effect"). **Post-hoc nachladen ist damit als Weg tot**, solange
keine Quelle aktiv ist — und die Quelle aktivieren ist Phase 4 (s. u.).

### Das eigentliche Hindernis: der Ladepfad ist entschärft

`HdmiRx_HDCP14_LoadKey` (`0x8b13d044`): liest Byte `base+0x93`
(= `0x06840093`), Bit 0 gesetzt → „HDCP1.4 key has been loaded!"; sonst
schreibt `0xc0` dorthin und pollt Bit 0 für `0x33` Ticks:

```
0x8b13d0a4  2c630033  sltiu v1,v1,0x33     <- Schleifengrenze
```

Am Board liest `0x4b13d0a4` **`0x2c630000`** — U-Boots
„HDCP key-load wait defeated" (Kommentar in `h713_mips.c`: die Ticks laufen
beim MIPS-Start noch nicht, die Schleife würde ewig drehen). Damit ist die
Grenze 0, `bne` fällt sofort durch, jeder Ladeversuch endet in „time out!" —
**unabhängig davon, was die Hardware tut.** Ein Test von These 1 aus doku/69
(Domains schon in U-Boot an) muss diese Patchstelle zurücknehmen oder die
Ticks anders sichern, sonst misst er mit einem Instrument, das kein Positiv
zeigen kann.

Der Schlüssel selbst wird von `LoadKey` **nicht aus dem Speicher gelesen** —
`0xc0` nach `0x06840093` stößt ein Laden aus dem Schlüsselspeicher der
Hardware an. Wer den füllt, ist im Stock der Bootloader (`down hdcp 1.4`,
`sunxi_smc_refresh_hdcp`, vgl. `sunxi_tvtop_complete`). Die 320 Byte aus
`analyse/hdcp-keys/hdcp14-key-320.bin` haben damit noch keinen Weg in die
Hardware; er liegt in der Secure-World-Schnittstelle, nicht im MIPS.

## 4 — `SetSource(3)`

### Der Lauf

Zustand vorher (frisch nach Neustart, Rezept aus doku/69 gefahren, dann
`hdmi_seq.py run --phase 3 --portmap stock`: 22 Schritte mit RETURN, HPD-Gate
0 → 1, `HdmiRx_HDCP22_LoadKey ok!!`):

```
MIPS lebt 1, TX-FIFO 0, HPD-Gate 1, elog write 2066, ARISC-HPD-Zähler 0 0 0
```

Dann `hdmi_seq.py run --phase 4 --i-mean-it --only setsource --portmap stock
--listen-after 10` (Callbacks werden auch bei `--only` angemeldet; 1 s Pause
vor dem Aufruf wie Stock). Ergebnis:

* keine Ausgabe mehr, kein RETURN; `--log`-Datei leer
* nach ~2 min: **`ssh: No route to host`**, ARP-Eintrag unvollständig — der
  ganze SoC steht, nicht nur ein Firmware-Thread
* Ping erst wieder nach dem **manuellen Stromzyklus** (kein Watchdog),
  `uptime 0 min`, MIPS über die persistente `bootcmd` von selbst hoch

Das ist der dritte Absturz an `SetSource`: 01.09. (Position 2 der Sequenz,
doku/67), heute zweimal (der erste Versuch fiel mit dem manuellen Neustart
zusammen und ist nicht bewertbar; der zweite ist der oben).

### Was der Absturz nicht ist

* **Nicht die Position in der Sequenz.** Heute stand er zuletzt, nach allen
  22 Stock-Schritten, mit Pause.
* **Nicht fehlende Callbacks.** `cmd_run` meldet sie vor jedem Lauf an, auch
  mit `--only`.
* **Nicht „SetSource ist immer tödlich".** `re/captures/weltneuheit/
  mainline-0x5600000-post-hdmird.txt:7`: `THal_Vp_SetSource(0x3) OK in 129ms`
  — auf dem arm32-Mainline der weltneuheit-Ära lief es durch, und Session R
  sah danach `port1 SwitchState 1→2→3` im elog.

### KORREKTUR (dritter Lauf, UART mitgelesen): es ist ein ARM-Kernel-Oops

Der dritte Lauf — volle Sequenz in **einem** Prozess (`run --phase 4`, kein
`--only`) — wurde am UART mitgeschnitten. Er zeigt zwei Dinge, die die
Deutung „Interconnect-Hänger" **aufheben**:

1. **Der erste Callback vom MIPS überhaupt.** Während des ersten
   `SetPortMap` (`0x9ce74c48`, t = 297.43 s) kam ein CALL vom MIPS:

   ```
   RX-CALL from cpu=1 comp_id=0x38d780e2 params=2 p[1..4]=[00000001 00000003 00000001 8b230000]
   userspace_deliver comp=0x38d780e2 ctx_count=1
   ```

   `0x38d780e2` = `MipsHalCallback_HdmiHotPlugByPortHandler`, Argumente
   `(1, 3)`. Das HPD-Gate `0x4b271c2c` kippt an derselben Stelle. Die
   Callback-Verdrahtung funktioniert also in beide Richtungen.

2. **`SetSource(3)` (`0xeaf13de5`, t = 299.62 s) bekommt CALL_ACK** — die
   Firmware hat den Aufruf angenommen — und 0,45 s später, **ohne weitere
   Msgbox-Zeile**, stirbt der ARM-Kernel:

   ```
   [  299.645] cpu_comm: IPC[msg_cb] type=2(CALL_ACK) ...
   [  299.673] cpu_comm: IPC[dispatch] type=2(CALL_ACK) ...
   [  300.097] Unable to handle kernel paging request at virtual address ffff80008112f340
   ```

   Kein RETURN, kein weiterer CALL im Log davor. Der Oops-Text bricht nach
   dieser einen Zeile ab (kein PC, kein Trace) — das ist selbst ein Befund,
   s. u. Das erklärt, warum nach dem ersten Lauf der `--log` leer war.

Was das für die Takt-These unten heißt: sie ist damit **nicht die erste
Adresse mehr.** Ein ungetakteter Block würde den MIPS oder den Bus
festsetzen, nicht den ARM in einem Paging-Fault enden lassen. Kandidaten
für den Oops, nach dem, was doku/67 ohnehin als wahrscheinlichste Fehlerklasse
führt:

* ein Pfad im `cpu_comm`-Treiber, der bei `SetSource` zum ersten Mal läuft
  (die Firmware antwortet auf `SetSource` anders als auf die 22
  Init-Aufrufe — evtl. mit einem Rahmen, den `handle_return`/`ack_action`
  falsch dereferenziert; `cc_deref` auf einem Wert, den der MIPS verändert hat);
* der Listener-Pfad (`cpu_comm_dev.c`, `*(u64 *)&buf[1]`, in doku/67 als
  „nicht auf unserem Pfad, ungeprüft" geführt) — **seit diesem Lauf ist er
  auf unserem Pfad**, denn erstmals wurde ein Callback zugestellt;
* ein MIPS-Schreibzugriff in ARM-Speicher über einen Zeiger, den wir ihm
  gegeben haben (Wce-Fenster, Vp_Init-Staging, Key liegen alle im
  no-map-Shmem — die getaggten `cc_ref`-Wait-Referenzen aber nicht).

Der naheliegendste Treiberpfad, geprüft: `CPUComm_CallEx` wartet nach dem
`CALL_ACK` mit `cpu_comm_sem_down_timeout(wait_obj+8, 500 ms)` auf das
`RETURN` (`cpu_comm_rpc.c:633`), holt dann `GetReturnbySessionId` (bei
ausbleibendem RETURN `NULL`) und gibt am Ende das Wait-Objekt frei — ein
spätes `RETURN` würde es dann freigegeben dereferenzieren. Der Kommentar
im Treiber nennt genau diesen Use-after-free als Grund für die 500 ms.
`SetSource` dauert im MIPS länger als jeder Init-Aufruf (PHY-Reset,
Port-Select). **Aber:** der Oops kam 452 ms nach dem `CALL_ACK`, das
Zeitlimit (HZ=250, 125 Jiffies, Timer-Rad rundet auf) kann frühestens nach
500 ms feuern. Der Timeout-Pfad ist es also **nicht**, es sei denn, das
Warten begann früher, als das Log zeigt.

### Vierter Lauf (06.09., UART per tio beim Nutzer): stirbt STUMM

Gleiche Sequenz, gleiche Stelle — nach `IPC[dispatch] type=2(CALL_ACK)` für
`SetSource` (`0xeaf13de5`, t = 109.37 s) kommt **nichts mehr**, keine
Oops-Zeile. Kein Watchdog, das Board bleibt tot bis zum Stromzyklus. Zusammen
mit dem abgebrochenen Oops-Kopf vom Vortag (eine Zeile, dann Stille) heißt
das: der ARM friert **mitten im Drucken** ein. Das ist das Bild eines
**Interconnect-Hängers**, nicht eines Treiberfehlers — ein Treiber-Oops
druckt seinen Trace zu Ende.

Ein naheliegender Kandidat wäre ein ungetakteter HDMI-Audio-Block: der MIPS
macht bei `SetSource` laut Session-R-elog `AUDIO PLL CALC`. **Diese These ist
am 06.09. widerlegt.**

### WIDERLEGT: die Takte sind alle an — und der Mainline-CCU zählt zwei falsch

Ich hatte `0xd80` Bit 0/1 für die Gates von `bus-hdmi-audio` und `cap-300m`
gehalten (so steht es in unserem `ccu-sun50i-h713.c`) und aus `0xd80 =
0xC0000000` geschlossen, beide seien aus. Das war der falsche Bitindex.

Der Stock-`vmlinux` (`/opt/archive/HY310/extracted/vmlinux.elf`, CCU-Tabelle
über die `clk_init_data`-Namen ausgelesen) sagt:

| Takt | Register | Gate-Bit (Vendor) | unser `ccu-sun50i-h713.c` |
|---|---|---|---|
| `bus-hdmi-audio` | `0xd80` | **Bit 31** | Bit 0 — **falsch** |
| `bus-cap-300m` | `0xd80` | **Bit 30** | Bit 1 — **falsch** |
| `bus-tvcap` | `0xd88` | Bit 0 | Bit 0 ✓ |
| `bus-disp` | `0xdd8` | Bit 0 | Bit 0 ✓ |

Die beiden bekannten (`bus-tvcap`, `bus-disp`) bestätigen die Auslesemethode;
die beiden strittigen kippen. **Am Board sind Bit 31 und 30 gesetzt**
(`0xd80 = 0xC0000000`) — `bus-hdmi-audio` und `bus-cap-300m` laufen also. Der
Treiber weiß es nur nicht: `clk_summary` zeigt `bus-hdmi-audio` mit Zähler 0
(er schaltet Bit 0, wirkungslos) und `bus-cap-300m` mit Zähler 1 (Bit 1,
ebenso wirkungslos), während die echten Bits längst an sind.

Live gegengeprüft (06.09.):

```
0x02001d6c tcd3          = 0x80000305   Bit31 an
0x02001d74 vincap-dma    = 0x81000001   Bit31 an
0x02001d80               = 0xC0000000   Bit31 (hdmi-audio-bus) + Bit30 (cap-300m) an
0x02001d84 hdmi-audio    = 0x80000000   Bit31 an
0x02001d88 bus-tvcap     = 0x00010001   Bit0 an, Reset Bit16 gelöst
```

**Alle Takte, die der MIPS bei `SetSource` anfasst, sind an.** Ein fehlender
Takt ist damit als Ursache des Hängers ausgeschlossen. `SetSource` läuft bei
uns **mit** demselben Taktsatz, den die weltneuheit-Erfolge hatten — der
Unterschied liegt woanders.

Nebenbefund, unabhängig vom Absturz: **unser CCU-Treiber definiert
`bus-hdmi-audio` und `bus-cap-300m` an den falschen Bits** (0/1 statt 31/30).
Folgenlos, solange die Bits aus U-Boot gesetzt bleiben und `clk_ignore_unused`
in den bootargs steht — aber ein `clk_disable` würde ins Leere greifen und der
`clk_summary`-Zustand ist irreführend. Gehört in `ccu-sun50i-h713.c`
korrigiert (Patch 0001), unabhängig von dieser Fehlersuche.

### Damit bleibt: ein stiller Interconnect-Hänger ohne benannte Ursache

Der ARM friert mitten im `printk` ein, ohne Oops-Trace, an genau der Stelle,
wo `SetSource` sein `CALL_ACK` bekommen hat. Der MIPS fängt danach an, die
HDMI-RX-Blöcke umzuschalten (`HdmiRx_Port_Select base=6800800`,
`HdmiRx_PHY_Reset`, `Toggle_PD_IDCLK_Reset` — Session R). Was den ARM dabei
festsetzt, ist **nicht** gezeigt. Mögliche Klassen, keine belegt:

* der MIPS legt beim PHY-Reset kurz einen Bus/Takt lahm, den der ARM gerade
  über `cpu_comm` pollt (der ARM-Poller läuft die ganze Zeit);
* ein Zeiger, den wir dem MIPS mitgegeben haben und den er erst bei
  `SetSource` benutzt (Wce-Fenster, Vp_Init-Staging), zeigt woanders hin als
  er soll;
* ~~etwas an der Quelle~~ — zurückgenommen: die Quelle ist permanent
  angeschlossen (Nutzer, 06.09.).

### Was das für den Plan heißt

`SetSource` bleibt der letzte, gefährliche Schritt und **nur mit Ansage**. Der U-Boot-Weg (`h713_tvcap_prepare()` vor dem MIPS-Start, plus
die `LoadKey`-Schleifengrenze zurück auf `0x33`) prüft in einem Boot auch
HDCP 1.4 — aber er ist ein U-Boot-Neubau und -Flash und ändert an der
Takt-Lage nichts mehr, nachdem die als Ursache ausfällt. Er lohnt erst, wenn
die Quelle-These geprüft ist.

## Nebenbefund: ARISC braucht eine Minute

Nach `arisc_load.py load` steht die Firmware ~60 s lang still (BSS 60,
Stack 35, HPD-Zähler rührt sich nicht, `arisc-hdmi/status` sagt „HAENGT").
Danach läuft die Hauptschleife von selbst an (Zähler 3 → 0, BSS 134,
Stack 130). Das `STARTUP_NOTIFY` im user0-FIFO muss dafür nicht abgeholt
werden (`arisc_send.py drain` dreimal, keine Änderung; der Anlauf kam
trotzdem). Steht jetzt im Rezept in doku/69.

## Was ich NICHT gezeigt habe

* Warum `SetSource` hängt. Die Takt-These ist widerlegt (alle Takte an,
  Vendor-CCU-Tabelle), ein Mechanismus ist nicht benannt; ein elog des
  Absturzlaufs gibt es nicht (DRAM nach dem Stromzyklus neu geladen).
* ~~Ob `SetSource` mit angeschlossener Quelle genauso hängt~~ — die Quelle
  ist permanent angeschlossen (Nutzer, 06.09.); die Annahme „ohne Quelle"
  war falsch.
* Ob `ReloadHdcp14Key` mit aktiver Quelle etwas tut — ohne `SetSource` nicht
  prüfbar.
* ~~Keine Quelle gesehen~~ — es hängt permanent eine Quelle am Projektor
  (Nutzer, 06.09.); ob sie das Board sieht, ist weiterhin nicht gezeigt.

## Werkzeuge und Spuren

* `/root/phase3-*.log`, `/root/phase4-194206.log` (leer — der Aufruf kam nie
  zurück)
* Scratch: `mdis.py` (MIPS-Minidecoder für das LE-abgelegte `display.bin`,
  Befehle `dis`, `refs`, `words`) — liegt nur im Sitzungs-Scratchpad, bei
  Bedarf nach `tools/` heben
* Board nach dem Watchdog wiederhergestellt: ARISC geladen, cpu_comm 4/4
  Ready, `h713-tvcap` und `hy310-arisc-hdmi` geladen. Phase 2/3 **nicht**
  erneut gefahren.

## Fünfter Lauf (06.09.): mit MIPS-elog Level 5 und Herzschlag am UART

Vorbereitung: Level 5 zur Laufzeit (doku/63), `elog_tail.py` mit Filter nach
`/dev/kmsg`, Herzschlag alle 200 ms, Konsole Loglevel 8, tio beim Nutzer.
`run --phase 4 --only setsource`. Ergebnis (UART, gekürzt, Zeilen sind durch
den geteilten 1-KiB-Formatpuffer der Firmware verschränkt):

```
[172.847] cpu_comm: msgbox tx raw=0 (CALL)          SetSource 0xeaf13de5
[172.859] cpu_comm: IPC[dispatch] type=2(CALL_ACK)
[172.861] elog: I/hdmirx  port id=1 isActive=1 tick=175447
[172.862] elog: ... HdmiRx_Port… base=6800800 port 1
[172.862] elog: ... AUDIO PLL CALC: Stage 0 TMD…  OutputFs=3e8000 …
[172.863] elog: ... AUDIO PLL CALC: Stage 3 LoopCnt=2 …
[172.964] elog_tail: hb 511 wr=2604                  <- letzter Herzschlag
                                                     (hb 512 um ~173.17 fehlt)
```

Der ARM stirbt **150–300 ms nach dem `CALL_ACK`**, während der MIPS in
`AUDIO PLL CALC` steht (Stage 3 erreicht). Der Herzschlag bricht **zwischen
zwei Schlägen** ab, nicht mitten in einer Zeile.

### Was `AUDIO PLL CALC` anfasst (Firmware, `tools/mips-dis.py`)

* `HdmiRx_Audio_UpdateAPLL` (`0x8b13baf8`), `SetAPLL` (`0x8b13c01c`),
  `PowerUp/PowerDownAPLL` (`0x8b13b168`/`0x8b13b0dc`) greifen ausschließlich
  über die Byte-Helfer `read8 0x8b17fa60` / `write8 0x8b17fab4` /
  `rmw8 0x8b17fafc` zu: `a0` = **physische Adresse**, Zugriff als
  `(a0 + 0xB5000000) | 0x20000000`.
* Davor steht ein **Wächter** (`0x8b17f8ec`), eine Whitelist: nur
  `0x05000000–0x05FFFFFF`, `0x06800000–0x06FFFFFF`, `0x03000000–0x03000FFF`,
  `0x03002000–0x03004FFF`, `0x03006000–0x03006FFF`, `0x03010000–0x0302FFFF`,
  `0x03040000–0x03041FFF`, `0x03060000–0x030607FF` (und weitere kleine
  Fenster). Außerhalb wird der Zugriff **übersprungen** (`read8` liefert 0).
* Die APLL-Basis kommt aus dem Treiberobjekt (Offsets `+0x04…+0x1b`), also der
  HDMI-RX-Wrapper (`base=6800800`). `UpdateAPLL` schreibt ein 32-Bit-Register
  byteweise (MSB zuerst), **pollt dann Bit 7 eines Bytes ohne Zeitlimit**
  (`0x8b13bcd0…0x8b13bcf4`) und schreibt ein zweites Register.

**Ein Byte-Zugriff des MIPS in seinen eigenen Wrapper friert keinen ARM ein.**
Und die CCU fasst der MIPS in diesem Pfad nicht an (Whitelist).

Nebenbefund: die eine CCU-Stelle der Firmware (`0x8b19ca84`, `0x0200190c`
Bits 4/20) ist die Initialisierung von **UART4** (`0x02501000`; `0x02500000`
ist unsere Konsole UART0). Ohne direkten Aufrufer, vermutlich der
„route uart"-Logmodus. Nicht Teil des `SetSource`-Pfads.

### Deutung und das nächste Experiment

Bleibt: der ARM stirbt, während der MIPS etwas Harmloses tut. Zwei Klassen:

1. **Ein ARM-Kern blockiert mit gesperrten Interrupts** (Deadlock im
   `cpu_comm`-Pfad, der bei `SetSource` erstmals läuft). Er hält die Konsole
   (andere Kerne drucken nur noch in den Puffer) und, wenn die Netz-IRQ auf
   ihm liegt, das Netz. Von außen sieht das aus wie ein toter SoC. Alle
   Spinlocks des Treibers sind `irqsave` — ein offensichtlicher Kandidat fehlt.
2. **Der Interconnect steht** — dann ist jeder Kern tot.

Unterscheidbar per IRQ-Trennung: Msgbox-IRQ auf CPU3, Netz-IRQ auf CPU0,
`hdmi_seq` auf CPU1, `elog_tail` auf CPU2 (`analyse/hdmi-seq/prep_after_boot.sh`).
Antwortet das Board nach dem Hänger noch auf ssh, ist es Klasse 1, und
`/proc/<pid>/task/*/stack` der hängenden Threads zeigt die Stelle. Antwortet
nichts, ist es Klasse 2.

## Sechster Lauf (06.09.): IRQ-Trennung — der ganze SoC steht

`prep_after_boot.sh`: Msgbox-IRQ 332 auf CPU3, USB-Ethernet-IRQ 249 (EHCI
usb5) auf CPU0, `hdmi_seq` per `taskset` auf CPU1, `elog_tail` auf CPU2, tio
beim Nutzer. `SetSource(3)` hängt wie zuvor. Danach vom Host:

```
ping: 2 packets transmitted, 0 received
ssh:  No route to host
```

Kein Kern antwortet — auch nicht CPU0 mit dem USB-Host-Controller, der
nichts mit dem Treiber zu tun hat. **Klasse 1 (Kern-Deadlock im
`cpu_comm`-Treiber) ist damit ausgeschlossen, Klasse 2 bestätigt: der
Interconnect steht.** Der `CONFIG_LOCKUP_DETECTOR` ist nicht gebaut
(`/proc/sys/kernel/watchdog_thresh` fehlt), ein Soft-Lockup hätte sich ohnehin
nicht gemeldet.

Was bei `SetSource` außer den Byte-Zugriffen des MIPS anläuft und einen Bus
festsetzen kann, ist **DMA**: HDMI-RX-Capture nach INCAP → DRAM. Im Vendor-DT
hängen `tvcap@6800000` und `tvdisp@5000000` als
`allwinner,sunxi-tvsystem-iommu-dev` hinter einem eigenen **TV-System-IOMMU**
(`0x02010000`), der laut `re/notes/CURRENT-TRUTH.md` „MISSING in mainline
(U-Boot bypass)" ist. Läuft die Capture-DMA gegen einen IOMMU, den niemand
konfiguriert oder umgeht, blockiert sie den Bus — genau das Bild. Der
arm32-Erfolg der weltneuheit-Ära lief mit dem Vendor-Bootloader, unser
`h713_disp init` ist eine andere Boot-Kette. Das ist die nächste Spur, noch
nicht belegt.

## Siebter Lauf (06.09.): TV-IOMMU geprüft, tvcap-Magic-Puls gefahren — hängt trotzdem

**TV-IOMMU `0x02010000` live** (Gate `0x020017bc` an, Treiber gebunden):

```
+0x00=0x00000014  +0x10=0x8003007F  +0x30=0x0000007C (BYPASS)  +0x40=1  +0x50=0x413F0000 (TTB)  +0x60=0x0003007F
```

Bypass `0x7C` = Master 2–6 durchgereicht, nur 0/1 (Video-Codec, `iommus =
<&iommu 0 1>, <&iommu 1 1>`) übersetzt. Vendor-DT: `tvcap@6800000` ist
**Master 4** (`<&mmu_aw 4 1>`), `tvdisp@5000000` Master 3, `ge2d`/`dec`
Master 2 (Bypass). Master 4 läuft bei uns physisch wie im April
(`0x7F`). **IOMMU ist nicht die Ursache.**

**Magic-Puls** (`analyse/hdmi-seq/tvcap_pulse.py --do`, Stock-Reihenfolge
aus `tvtop_tvcap_enable`, auf `0x06e00000`):

```
vorher        tvcap +0=0x00111111 +4=0x01111117 +8=0x00000504  INCAP+0=0x00003a7b
nach Phase 2  tvcap +0=0          +4=0          +8=0           INCAP+0=0x00000000   <- INCAP hinter dem Router
nach Phase 3  tvcap +0=0x00111111 +4=0x01111117 +8=0x00000404  INCAP+0=0x00003a7b
```

Nebenbefund: mit genulltem `0x06e00000` liest INCAP null — **`0x06e00000`
ist der Fabric-Router der Capture-Blöcke**, analog zu `0x05700000` für die
Display-Blöcke. `+8` stand vor dem Puls auf `0x504` (Boot-Default), Stock
schreibt `0x404`.

Danach `SetSource(3)` auf CPU1: **hängt wie zuvor**, kein Ping, kein ssh.

### Was jetzt ausgeschlossen ist (jeweils am Gerät)

| These | Ergebnis |
|---|---|
| fehlender Takt (`bus-hdmi-audio`, `cap-300m`, …) | alle an (Vendor-CCU-Bits 31/30) |
| Kern-Deadlock im `cpu_comm`-Treiber | IRQ-Trennung: ganzer SoC tot |
| TV-IOMMU übersetzt die Capture-DMA | Bypass `0x7C`, Master 4 physisch |
| fehlender tvcap-Magic-Puls / INCAP-Bit | gefahren, ohne Änderung |
| Position in der Sequenz, fehlende Callbacks | s. o. |

### Was übrig bleibt — zwei Unterschiede zum April, beide ungetestet

1. ~~Keine HDMI-Quelle~~ — **falsch, zurückgenommen (06.09.):** am
   Projektor hängt permanent eine Quelle (Aussage des Nutzers). Die
   Formulierung „ohne Quelle" in dieser und in doku/71 war meine Annahme,
   nie gemessen. Damit ist die Quelle als Unterschied zum April vom Tisch.
2. **Der MIPS startet in U-Boot mit stromlosem TVCAP** (These 1 aus
   doku/69). Sein HDMI-RX-Treiberobjekt wird beim Start initialisiert,
   während der Block nicht antwortet (`HDCP14 time out` ist das sichtbare
   Symptom); `SetSource` arbeitet dann mit einem Objekt aus einer
   fehlgeschlagenen Init. Im April startete Linux den MIPS **nach**
   `sunxi_tvtop`. Test: `h713_tvcap_prepare()` **und** die PPU-Domains
   TVFE/TVCAP in U-Boot vor `h713_mips_release_reset` — ein U-Boot-Neubau
   und -Flash, nur mit Ansage. Dazu gehört die `LoadKey`-Schleifengrenze
   zurück auf `0x33`, damit derselbe Boot auch HDCP 1.4 prüft.

### Vorbehalt zu These 2 (06.09., Hinweis des Nutzers)

„TVFE/TVCAP sind beim Start aus, jeder Zugriff hängt" stammt von **cstengers
Board B** (Patch 0087, `hy200_qz713df_a1`), nicht vom HY310. Auf dem HY310 ist
der PPU-Zustand beim Boot **nicht gemessen** — meine Lesungen von
`0x07001080`/`0x07001100` waren die Domain-Basisregister, nicht die
Statusregister. Nach `sun50i-h713-ppu.c` gilt: Basis `0x07001000`,
Domain d: `pwr_ctrl = +0x20 + d*0x80`, `status = +0x24 + d*0x80`, Bits 17:16
= `01` heißt an. Also TVFE (d=1) `0x070010A0`/`0x070010A4`, TVCAP (d=2)
`0x07001120`/`0x07001124`. U-Boot (`h713_mips.c`) fasst die PPU nicht an.

Nächste Messung, vor jedem Modul: diese beiden Statusregister. Stehen sie
schon auf „an", hatte der MIPS beim Start Strom auf dem Block, und These 2
fällt wie die anderen. Dazu `THal_Vp_HDMI_GetPortStatus` (`0xcbf83247`,
rein lesend) als Blick in das HDMI-RX-Objekt des MIPS.

## Achter/neunter Lauf (06.09.): `0x068B0000` liegt am Demod-Bus — und der Hänger bleibt

**Messung am HY310, vor jedem Modul:** alle fünf PPU-Domains sind beim Boot
an (`pwr_ctrl = 1`, `status = 0x00010000`). These 2 (stromloses TVCAP beim
MIPS-Start) ist auf diesem Board tot. `THal_Vp_HDMI_GetPortStatus`
(`0xcbf83247`) liefert 0, mit und ohne Argument — nicht aussagekräftig.

**CCU-Block `0xd10`–`0xdac` gelesen:** der gesamte TVFE/Demod-Teil ist
ungetaktet (`adc`, `dtmb`, `i2h`, `cip-*`, `tsa-*`, `audio_*`, `mpg0/1` alle
Bit 31 = 0), **`bus-demod` `0xd64 = 0x00000000`** (Gate aus, Reset
angezogen); nur `tvfe_1296M` (`0xd20`) läuft.

**Der entscheidende Test:** `0xd64 := 0x00010001`, dann die bisher tödliche
Lesung von `0x068B0000` vom ARM:

```
0x068b0000 = 0x00000010   0x068b0004 = 0x00000003
0x068b00b8/c4/d0/dc = 0   0x068b044c = 0
```

**Liest, Board lebt.** `0x068B0000` („TVTOP A/B", Ziel von
`memory_agent_onoff`) hängt am **Demod-Bus**; ohne `bus-demod` tötet jeder
Zugriff den Interconnect — vom ARM (Sperre in doku/69) wie vom MIPS. Die
absolute Sperre „`0x068B0000` nie lesen" ist damit erklärt und **bedingt**:
mit `bus-demod` an ist der Block ein normales Register.

Dann `SetSource(3)` mit `bus-demod` an, `--gap 500`, 3 s Pause: **hängt
trotzdem** (13:22:30, diesmal „Connection closed by remote host" statt
stummem Ende). Der Rest des TVFE-Taktsatzes bleibt aus; Stock
`tvtop_tvfe_enable` schaltet alle 15 Takte, Reset und den Router-Wert
`0x003003FF` auf `0x06700000`. Nächster Schritt:
`analyse/hdmi-seq/tvfe_enable.py --do` vor `SetSource`.

## Zehnter/elfter Lauf (06.09.): voller TVFE-Taktsatz — hängt; Black-Box im DRAM

`tvfe_enable.py --do` (alle 15 TVFE-Takte Bit 31, `bus-demod` Gate+Reset,
Router `0x06700000 := 0x003003FF`; vorher las das Register `0x7ff`, mit
`bus-demod` an ist es lebendig), Kontrolle `0x068B0000 = 0x10` ok, dann
`SetSource` mit `--gap 500`: **hängt** (Lauf 10, 13:3x; Lauf 11 identisch).

Beobachtung aus dem UART (Nutzer, Lauf 10): nach dem `CALL_ACK` (113.204)
wuchs der elog-Schreibzeiger von 40613 auf 45580 (~5 KiB) bis zum nächsten
Herzschlag 10 ms später — und dann nichts mehr. In Lauf 5 (ohne
`bus-demod`) kam der MIPS noch bis `AUDIO PLL CALC`; in Lauf 9 (nur
`bus-demod`) blieb der Zeiger sofort stehen. **Die Freigaben verschieben den
Hänger, sie beseitigen ihn nicht.** Was in den 5 KiB stand, hat der UART
nicht geschafft (Filter + 115200 Baud), und die NFS-Kopie hinkt Sekunden
hinterher (letzter Stand Tick 96899 bei `SetSource` um 115372).

Deshalb zwei Änderungen am Mitschreiber (`elog_tail.py`):

* `--kmsg-exclude 'cpucomm|TSEXX|D/sys|app_init' --kmsg-cut 160` — der
  UART bekommt alles außer dem Rauschen, statt nur eine Whitelist.
* **Black-Box im DRAM**: jede Zeile wortweise nach `0x4e710000` (Shmem,
  `no-map`, oberhalb der Vp_Init-Staging; U-Boots `clear_workspace` nullt
  nur `0x4b1xxxxx`–`0x4be01000` und den FB). Kopf: Magic `0x424f5845`,
  Schreiboffset, Wrap-Zähler. `bbox_read.py` liest sie nach einem
  Stromzyklus — **als Erstes**, DDR3 hält Daten nur Sekunden ohne Strom.
  Der elog-Ring selbst liegt im genullten Bereich und taugt nicht.

## Zwölfter Lauf (06.09.): MIPS-Log per UDP — der MIPS stirbt im Resync der Routine-Tabelle

DRAM-Black-Box fiel aus (U-Boot nullt den ganzen Shmem, `h713_mips.c:3056`).
Ersatz: `elog_tail.py --udp 192.168.8.104:5555` schickt jede Zeile ungefiltert
als UDP-Datagramm (USB-Ethernet, 100 Mbit), `udp_listen.py` auf dem Host
schreibt sie mit Zeitstempel. Damit liegt erstmals der letzte MIPS-Zustand vor
dem Tod vollständig vor (`scratchpad/elog-udp.log`, Auszug in
`analyse/hdmi-seq/`).

**Der MIPS bricht vor dem Aufruf der Routine ab.** Letzte Zeilen (Session 18,
`FuncId=eaf13de5`):

```
comm_request.c 1174  Enter, FuncID=eaf13de5
comm_request.c 1184  osal_semaphore_get()  sem = 8B254BE4
tridspinlock.c  305  spinLock(2,quick)-Enter
tridspinlock.c  355  spinLock(2,quick)-End, pSpin->ref=1     <- letzte Zeile
[hb 105, 40 ms später]                                       <- dann Tod
```

Zum Vergleich der erfolgreiche `GetSource` aus demselben Log: nach
`spinLock(2,quick)-End` folgen 7 Ticks später `comm_SpinUnLock(2)`,
`comm_request.c 1192/1229`, `[S]Find matched Routine`, dann die Routine.

**Was zwischen Lock und Unlock steht** (`tools/mips-dis.py dis 0x8b11bf78`,
Funktion zu `comm_request.c:1174`): der **einzige** `spinLock(2)`-Aufruf ist
der Resync-Pfad bei `0x8b11c280`:

```
0x8b11c280  jal spinLock(2)                          0x8b125a98
0x8b11c288  a0 = *(0x8b22f1f4) + 0x7d8               private Kopie der Routine-Tabelle
0x8b11c294  a1 = shmem + 0x75c0                      Tabelle im Shmem (0x4e3075c0)
0x8b11c290  a2 = 0x1cb08                             117 504 Byte = 1224 × 96 + 8
0x8b11c298  jal memcpy                               0x8b1bc654
0x8b11c2a0  jal comm_SpinUnLock(2)                   0x8b125abc
0x8b11c2ac  jal 0x8b15b8f0(private + 0x7d4)          Index neu aufbauen; 0 -> Fehler + Endlosschleife
0x8b11c304  Versionen erneut vergleichen (+0x7d8 vs shmem+0x75c0)
```

Er läuft, wenn die **Versionsnummer** der Tabelle (`0x4e3075c0`) nicht zur
privaten Kopie passt — also nach jedem `INSTALL_RT` (jede Callback-Anmeldung
durch `hdmi_seq`, auch bei `--only setsource`) und nach jeder
Kanalregistrierung des Treibers („MIPS-incoming channel reg"). Der erste
Aufruf danach löst die Kopie aus. Bei `GetSource` überlebte der ARM sie, bei
`SetSource` nicht. Die Funktion hat außerdem vier Assert-Fallen
(`beq zero,zero,<self>` nach einer Fehlermeldung); keine davon wurde geloggt.

**Offen, entscheidend:** wohin `*(0x8b22f1f4) + 0x7d8` zeigt. Reserviert
(`no-map`) sind bei uns `0x4b100000`–`0x4d961000` und der Shmem. Liegt die
private Kopie außerhalb, überschreibt der MIPS bei jedem Resync 117 KB
**Kernel-RAM** — das erklärte den halb gedruckten Oops (Lauf 3), das stumme
Sterben und die Unempfindlichkeit gegen jede Takt-Freigabe. Messung: die
zwei Wörter `0x4b22f1f4` und `0x4b22efe4` nach dem nächsten Boot, gegen
`/proc/iomem`.

### Läufe 13/14 (06.09.): Kopierziel reserviert, ARISC ausgeschlossen, MIPS steht ≥100 ms vor dem ARM

* `*(0x8b22f1f4) = 0x8B254410` → Kopie nach `0x4b254be8`–`0x4b2716f0`,
  vollständig in `mips-firmware` (`no-map`). **Die Resync-Kopie trifft kein
  Kernel-RAM.** (`0x8b22efe4` liest 0, wie in doku/66 — andere Firmware-Revision.)
* **ARISC im Reset** (Schritt 1 der Vorbereitung ausgelassen, `R_CPUCFG = 0`):
  identischer Verlauf, identischer Tod. Die ARISC ist raus.
* UDP-Zeitstempel: `spinLock(2,quick)-End` um 13:47:11.344, letzter
  Herzschlag 13:47:11.451 mit unverändertem elog-Schreibzeiger. **Der MIPS-
  Hauptthread schweigt ≥107 ms, bevor der ARM stirbt.** Bei `GetSource` kam
  `comm_SpinUnLock(2)` nach 7 ms. Der ARM las in dieser Zeit noch DRAM und
  sendete UDP über USB — sein Buspfad lebte noch, während der MIPS-Thread in
  einer DRAM→DRAM-Kopie stand.
* Der doppelte CALL-Doorbell unseres Treibers (zwei `msgbox tx raw=0 (CALL)`
  je Aufruf, `cpu_comm_proto.c:158`) trifft den MIPS mal innerhalb, mal
  außerhalb des Lock-Fensters; keine Korrelation mit dem Tod.

Offen: steht der MIPS-**Kern** (dann stand sein Buspfad vor dem des ARM) oder
nur der Thread? Der ThreadX-Tick liegt bei `0x8b252cc0` (ARM `0x4b252cc0`,
über `get_uptime_ticks 0x8b1521d8 → 0x8b104b04`). `elog_tail.py --tick`
sendet ihn alle 20 ms per UDP, dazu die drei Wörter von SW-Spinlock 2
(`0x4e300018`). Nächster Lauf.

### Lauf 15 (06.09.): der ARM lebt nach dem Hänger — der UART stirbt

Mit Tick-Sonde: der ThreadX-Tick bei `0x4b252cc0` ist für den ARM **stale**
(sekundenlang 219480, während die MIPS-Zeilen 2313xx tragen; er springt nur
bei Cache-Writebacks, z. B. der 117-KiB-Kopie, auf 231387). Der MIPS hält ihn
im D-Cache (kseg0). Als Lebenszeichen unbrauchbar; dieselbe Vorsicht gilt für
jede kseg0-Variable. Der elog-Ring erscheint dagegen zeilenweise (einzelne
`D/sys`-Zeilen alle 5 s), wird also vom Writer zurückgeschrieben.

Entscheidend: nach dem Hänger (13:51:37.5) antwortete das Board **weiter auf
Ping**, bis 13:53:47 — zwei Minuten. Meine ssh-Sitzung hing nur, weil
`hdmi_seq` darin im ioctl stand; der Mitschreiber verstummte 105 ms nach
`spinLock(2)-End`. Deutung: **nicht der SoC stirbt, sondern der UART**
(`0x02500000`, APB). Wer danach auf die Konsole schreibt — `printk` aus dem
Treiber, `/dev/kmsg` aus `elog_tail`, der Oops-Handler — blockiert im
Konsolentreiber für immer. Das erklärt den nach einer Zeile abgebrochenen Oops
(Lauf 3), das Schweigen von tio, und warum in manchen Läufen `ssh` noch mit
„Connection refused"/„closed by remote host" antwortete. Die früheren „kein
Ping"-Befunde nach 4 s sind damit nicht mehr eindeutig (Ping lief auf CPU0,
der Msgbox-IRQ-Handler druckt auf CPU3 …).

Konsequenz für den nächsten Lauf: `printk` auf Konsolen-Loglevel 1 (alles
bleibt in `dmesg`), `SetSource` im Hintergrund, danach eine **frische**
ssh-Sitzung: `dmesg`, `/proc/<pid>/task/*/stack` der hängenden Threads,
MIPS-/Msgbox-Zustand — ohne den UART anzufassen.

### Lauf 16 (06.09.): Konsole stumm — trotzdem tot nach ~3,5 s

`printk`-Konsolenlevel 1, `SetSource` im Hintergrund, frische ssh danach:
**Connection timed out**; Watcher: Ping weg um 13:58:17, der Hänger war um
13:58:13.76. Die UART-These allein trägt also nicht — der ARM stirbt auch,
wenn niemand auf die Konsole schreibt. Lauf 15 (Ping 2 min überlebt) bleibt
der Ausreißer.

Was der Tick jetzt beweist: `spinLock(2)-End` bei MIPS-Tick 266463, der
Tick-Zähler im DRAM springt auf **266470** — die Kopie evictet den Cache
und dauert wie bei `GetSource` 7 Ticks. **Die 117-KiB-Kopie läuft auch im
tödlichen Fall normal durch.** Danach erscheint keine Zeile mehr, der
Mitschreiber verstummt 326 ms nach dem Lock, das Netz 3,5 s danach.

Ob der MIPS danach wirklich schweigt, hängt daran, ob der Ring-Writer
zurückschreibt (kseg0 ist gecacht). Der Tick-Zähler tut es nicht; einzelne
`D/sys`-Zeilen im Leerlauf erscheinen aber zeilenweise. Statische Prüfung:
`cache`-Instruktionen im elog-Pfad (s. u.).

### Der Cache erklärt das Log-Ende — die „MIPS schweigt"-Deutung ist zurückgenommen

Statisch geprüft (`tools/mips-dis.py`): der Ring-Writer (`0x8b151a44`,
`0x8b151c74`, fünf `lui 0x8b27`-Referenzen auf `0x8B272D9C`) ruft **keinen
Cache-Writeback**; die ganze Firmware hat `cache`-Instruktionen nur im
Startcode. Der Ring liegt in kseg0 = gecacht. Zeilen werden für den ARM erst
sichtbar, wenn der MIPS-D-Cache sie verdrängt.

Damit ist das wiederkehrende Log-Ende bei `spinLock(2,quick)-End` ein
**Artefakt**: unmittelbar danach kopiert der MIPS 117 KiB (Resync) — das
verdrängt den gesamten Cache und spült alle *davor* geloggten Zeilen ins
DRAM. Alles *danach* bleibt im Cache, weil keine zweite große Verdrängung
folgt, bis der SoC stirbt. Lauf 9 (kein Resync) zeigte nach dem ACK gar
nichts; Lauf 5 zeigte `hdmirx`-Zeilen, weil dort anders verdrängt wurde.
**Der MIPS läuft nach dem Lock mit hoher Wahrscheinlichkeit normal in
`SetSource` hinein**; der Tod kommt 100–300 ms später, die entscheidenden
Zeilen stecken im MIPS-Cache. Die Läufe 12–16 sagen über den MIPS-Zustand
nach dem Lock **nichts** aus.

Ausweg: Ring-Writer auf kseg1 umbiegen (`lui 0x8b27 → 0xab27`, vier Wörter
bei ARM `0x4b151ac0/1d70/1e28/1ebc`; `analyse/hdmi-seq/elog_uncached_patch.py`).
Sauber gehört das in U-Boot neben den HDCP-Wait-Patch (Image geladen, vor dem
Reset-Lösen, `flush_cache` folgt dort ohnehin). Live aus Linux greift es nur,
wenn der MIPS-I-Cache die heißen Writer-Zeilen neu holt — ein Versuch ohne
Risiko, aber ohne Garantie.

## Lauf 17 (06.09.): Ring ungecacht — der vollständige `SetSource`-Verlauf des MIPS

Der Live-Patch (`elog_uncached_patch.py --do`, vier `lui`-Wörter) **griff**:
der I-Cache holte die Writer-Zeilen neu, ab da kam jede Zeile sofort. Volles
Log: `analyse/hdmi-seq/elog-udp-run17-setsource-uncached.txt`. Nach
`spinLock(2,quick)-End` (14:04:38.643):

```
38.671  D/hal      THal_Vp_SetSource() ENTER, hal_source_id: 3
38.672  I/app      AppTopSetSource
38.673  D/win_mgr  SetSignalInfo
38.674  I/mem_agn  update_onoff / memory_agent_onoff ×2
38.676  I/hdmirx   SetActivePort 1 ; port id=1 isActive=1 ; DDC and PHY select prot 1
38.681  I/hdmi_driver  HdmiRx_Port_Select base=6800800 port 1 ; HdmiRx_PHY_Reset ; toggle SYSTEM_PD_HDCP/DDC reset ; Toggle_PD_IDCLK_Reset
38.682  I/hdmirx   port 1 send HPD event
38.683  I/hdmi_driver  AUDIO PLL CALC Stage 0 TMDS=ffffffff … Stage 3 LoopCnt 0..3 … bPdivCalc Failed
38.689  I/hdmirx   call AfterEnable ; SetSignal dwSignal = 0x20003 ; Vrr mode is 0 ; Set Valid Signal … signal_format:13 color_space:0x440000
38.693  I/app      CallbackOfSignalChange            <- MIPS -> ARM, synchroner CALL
38.694  I/app      Signal Information: kSourceId_HDMI_1, AI_SIGNAL_MODE_NO_SIGNAL, BT709, timing 0
38.703  I/mem_agn  update_onoff / memory_agent_onoff ×2
38.705  I/hdmirx   hdmirx set AV mute:0 0              <- letzte Zeile
(nächster Herzschlag um 38.843 fehlt; ssh danach: Connection timed out)
```

Zwei Befunde: (1) **`TMDS=ffffffff` mit gesteckter Quelle** — der PHY sieht
keinen Takt; die Quelle sendet nicht, weil HPD zu ihr hin nicht steht
(`port 1 send HPD event` geht an einen Empfänger, den es bei uns nicht gibt:
Stock-ARISC-Weg über `SetPortMap`-Gate / Msgbox). Das ist Phase-1.5-Material,
nicht der Absturz. (2) **`CallbackOfSignalChange`** ist der erste synchrone
MIPS→ARM-CALL im ganzen Ablauf. Bis dahin war der einzige Rückruf der
asynchrone HotPlug. Der Tod folgt ≤ 150 ms später.

**Verdacht, jetzt konkret:** der Treiber dereferenziert an vielen Stellen
(`cpu_comm_channel.c` 243/274/319/377/385/403/434/445/513/518/565/788/817/
907/936) Listenglieder per `cc_deref()`; Werte mit Bit 31 gelten als
getaggte Arena-Referenz und werden zu `arena + (ref & 0x7fffffff)`. Ein
MIPS-kseg0-Zeiger (`0x8B25xxxx`) in einem dieser Felder ergibt eine wilde
Kernel-VA — die Form des Oops aus Lauf 3 (`ffff80008112f340`). Nur
`proto.c:1005` hat die `cpu_comm_is_mips_va()`-Prüfung. Der arm32-Treiber
kannte keine Arena-Refs. **Nicht bewiesen.** Gegentest: `--no-callbacks`.

### Lauf 18 (06.09.): `--no-callbacks` — stirbt trotzdem

Ring gepatcht, keine `INSTALL_RT`, `SetSource`: der ARM stirbt, das Log
endet diesmal wieder bei `spinLock(2,quick)-End` (der Tod kam schneller,
< 200 ms nach dem Lock; ob der MIPS noch weiterlief, ist nicht zu sehen).
**Der synchrone `SignalChange`-Callback ist als Ursache damit unwahrscheinlich.**
Nächster Verdächtiger aus dem Lauf-17-Verlauf: `memory_agent_onoff` schaltet
als Erstes AFBD (`0x05600010`), DE2-Kanäle und INCAP um — AFBD gehört auf dem
ARM dem geladenen KMS-Treiber `sun50i_h713_afbd` samt Interrupt
(`GIC_SPI 110`). Test: Treiber vor `SetSource` entladen.

### Lauf 19 (06.09.): ohne AFBD-KMS-Treiber — stirbt trotzdem

`rmmod sun50i_h713_afbd` (IRQ 142 verschwindet aus `/proc/interrupts`),
Ring gepatcht, `SetSource`: Tod wie zuvor. **AFBD-Treiber ausgeschlossen.**

Hinweis des Nutzers: im früheren (arm32-)Aufbau war das **HDMI-RX-Kernelmodul**
(`legacy/patches/0023-…hdmi-rx…`) vor der Init-Sequenz geladen — es
programmiert beim Probe Takte/Resets/Register des HDMI-RX-Blocks, bevor der
MIPS ihn bei `SetSource` umschaltet (`Port_Select`, `PHY_Reset`,
`SYSTEM_PD_HDCP/DDC`, `PD_IDCLK`). Bei uns fehlt das. Nächste Prüfung.

### Lauf 20 (vorbereitet): `h713_hdmi_rx_controller_enable()` des legacy-Moduls nachfahren

Was das Modul beim Probe tat (Patch 0023, Session U): Wrapper `0x06840000`
zehn Byte-Nullen (`+0x40202/10/20/21/30/40/2C0/137/0C0/0`), dann Synopsys
`0x050C0000`: `MAINUNIT_0_INT_MASK_N/CLEAR = 0xFFFFFFFF`, `TIMER_REF_BASE =
428571429`, `CMU_CONFIG0`-Margins (2/1), `DESCRAND_EN_CONTROL` QST=1,
`CED_CONFIG` (VIDDATA|GB|CTRL, CHLOCKMAXER 0x10), `DEFRAMER_CONFIG0`
(REMAPFILTER, ORDER 3), `PHY_CONFIG = RXDATA_WIDTH`, zuletzt
**`GLOBAL_SWENABLE = 0x3B01`**. Takte: nur `bus_disp` („bus"/„mod"), keine
Resets (Kommentar im DTS), PD `pd_tvcap`. Nachbau:
`analyse/hdmi-seq/hdmirx_ctrl_enable.py --do`, vorher Rohlesung derselben
Register (was der MIPS beim Start selbst gesetzt hat). Die Vendor-CCU hat im
Bereich `0xb00`–`0xc70` keine HDMI-Takte — die H6-„Phantome" sind wirklich
Phantome, das Modul lief also allein mit `bus_disp` und diesen Registerwerten.

## ~~ROOT CAUSE~~ WIDERLEGT (Lauf 21): `comm_CallWorkAction`-Zeigeraufruf ist es NICHT

Nach ~20 Läufen ist die Ursache **im ARM-Treiber**, nicht in der Hardware.

Der MIPS schickt bei `SetSource` als einziger Aufruf einen synchronen
Rückruf `CallbackOfSignalChange` (Lauf 17, ungecachter Ring). Ein eingehender
CALL vom MIPS mit `entry_cmd > 4` (`entry_base[0]`) nimmt in `command_action`
(`cpu_comm_proto.c:950`) den Workqueue-Pfad `Comm_Add2Call2WQ` →
`comm_CallWorkAction` (`cpu_comm_rpc.c`). Dort:

```c
FindRoutine(comp_id, routine_info);           /* 96-Byte-Eintrag aus dem Shmem */
void (*callback)(u32 *, u32 *) =
        *(void (**)(u32 *, u32 *))(routine_info + 88);   /* +0x58 */
if (callback)
        callback(params, result);             /* <-- Sprung ins Ungewisse */
```

Zwei Fehler übereinander:

1. **Falscher Offset / uninitialisiert.** `FindRoutineEx` füllt `routine_info`
   nur bei +0/+2/+4/+8, +12..76 und **+80 (u64)** — Bytes **88..95 bleiben
   uninitialisierter Stack**. `callback` ist damit Stack-Müll: mal 0
   (überlebt), mal ein Rest-Wert (Sprung → Tod). Das erklärt die
   Schwankung (Lauf 15 überlebte 2 min, andere starben sofort).
2. **Kein `cpu_comm_is_mips_va`-Riegel.** Jede andere Deref-Stelle des
   Treibers hat nach dem „Y2"-Bug diesen Schutz (`channel.c:715/795/913`,
   `proto.c:1005`). Genau der Callback-Aufruf hat ihn **nicht**. Selbst am
   richtigen Offset (+80) stünde dort ein **MIPS-kseg0-Zeiger** (Slot 19 am
   Gerät: Handler `0x8B10ABB8`) — den der ARM nie aufrufen darf.

**Warum nur `SetSource`:** der HotPlug-Callback bei `SetPortMap` kam mit
`entry_cmd = 0` (Lauf 3, `chan=0x0`), lief also den harmlosen FIFO-Pfad
(`Comm_Add2NewCallFifo`, kein Zeigeraufruf). `SignalChange` ist der einzige
`> 4`-Rückruf. Deshalb blieben Takte, IOMMU, tvcap, AFBD, controller_enable
und ARISC ohne Wirkung — keiner berührt diesen Pfad.

**Warum `--no-callbacks` (Lauf 18) nicht half:** der Schalter unterdrückt nur
`INSTALL_RT` auf der ARM-Seite. Der MIPS schickt den `SignalChange`-CALL
trotzdem, und `comm_CallWorkAction` läuft unabhängig davon
(`cpu_comm_userspace_deliver` „userspace cannot inhibit it").

**Passt zum Oops** aus Lauf 3: Paging-Fault bei `ffff80008112f340`, einer
Kernel-VA, ohne sauberen Trace — genau das Bild eines Sprungs auf einen
kaputten Funktionszeiger (fehlgeschlagener Instruktions-Fetch).

### Der Fix

Die Stock-Semantik ist „fire-and-forget an den Userspace" (0 ARM→MIPS
RETURNs). Der Kernel-seitige `callback()`-Aufruf ist ein Portierungsfehler —
in dieser Tabelle steht kein gültiger ARM-Kernel-Zeiger. In
`comm_CallWorkAction` den rohen Aufruf **entfernen** (bzw. hinter
`cpu_comm_is_mips_va()` + Kernel-Adressprüfung legen, die praktisch immer
ablehnt); `cpu_comm_userspace_deliver` und die leere ACK bleiben. Ein-Ort-
Änderung, deckt sich mit den bestehenden Y2-Riegeln. Danach Modul neu bauen
(Rezept doku/67, clang-18, kein Container) und `SetSource` **einmal** testen.

### Lauf 21 (06.09.): Testmodul mit `callwq_kernel_cb=0` — stirbt trotzdem

Modul neu gebaut (`analyse/cpu-comm-arm64`, `cpu_comm_rpc.c`: Puffer genullt,
Kernel-seitiger Callback hinter `callwq_kernel_cb` (Vorgabe 0) mit
Protokollzeile; sha `3a0e4cb9…`, in `/root/hy310-cpu-comm-callwq-test.ko`,
`prep_after_boot.sh` lädt es bevorzugt). `SetSource`: **Tod wie zuvor**, Netz
weg nach ~3 s. **Die Zeigeraufruf-These ist damit widerlegt**; die
Uninitialisiert-/Riegel-Befunde bleiben echte Fehler im Treiber, sind aber
nicht die Absturzursache. Die Aussage „Root Cause" oben war verfrüht.

Das Ring-Log endete wieder bei `spinLock(2)-End`: der Live-Patch greift nur,
wenn der I-Cache die Writer-Zeilen neu holt (Lauf 17 ja, 18/20/21 nein) —
kein Befund über den MIPS.

**Nächste These (prüfbar ohne Absturz):** `memory_agent_onoff` schaltet
DMA-Engines (TVTOP-A/B, INCAP, AFBD, DE2) ein, deren Zielpuffer der MIPS aus
dem **SMM-Heap** im Shmem bezieht. hdmird-Notiz: „SMM heap nicht initialisiert
in mainline", `Trid_SMM_MallocAttr` liefert 0. Der arm32-Treiber loggte
„cpu_comm: SMM heap initialized". Zieladresse 0 heißt aus MIPS-Sicht ARM-Phys
`0x40000000` = BL31/Kernelanfang. Prüfung: SMM-Heap-Kopf im Shmem lesen,
Treiber vergleichen.

## Was der Testlauf beantwortet hat, und wohin es zeigt (06.09., Stand nach Lauf 21)

**Auftrag des Nutzers:** den Kernel-seitigen Callback testweise herausnehmen und
sehen, ob der Absturz dann ausbleibt. **Antwort: er bleibt nicht aus.** Lauf 21
mit `callwq_kernel_cb=0` (Zeiger nur protokolliert, nicht angesprungen; Puffer
genullt) stirbt wie zuvor. Der Kernel-Callback ist also **nicht** die Ursache.
Er bleibt ein latenter Fehler (uninitialisierter Zeiger, fehlender
`is_mips_va`-Riegel) und muss sauber gemacht werden, **bevor** der Callback-Pfad
je gebraucht wird — aber er hängt den SoC nicht.

**Der Oops zeigt auf Daten, nicht auf Code.** `ffff80008112f340` (Lauf 3) ist
`timekeeper_data` im Kernel-`.bss` (`_edata..__bss_start..`, aufgelöst gegen
`vmlinux`). Ein Sprung auf einen kaputten Funktionszeiger würde beim
Instruktions-Fetch faulten, nicht an einer Datenadresse im `.bss`. Das Bild
passt eher zu **Speicher-Korruption**: irgendetwas überschreibt Kernel-RAM, und
der nächste Zugriff auf die Timer-/Timekeeping-Struktur stürzt ab — was auch
erklärt, warum der ganze SoC „tot" wirkt (Scheduler/Timer hin) und warum es mal
sofort, mal nach Sekunden kippt.

**Verdacht, der dazu passt:** `SetSource` lässt den MIPS `memory_agent_onoff`
laufen (Lauf 17), das schaltet die DMA-Engines INCAP/AFBD/DE2 scharf. Schreibt
eine davon nach `SetSource` (Signal `0x20003` „valid") in einen physischen
Bereich, der in unserer Mainline-Speicherkarte **Kernel-RAM** ist statt in die
reservierten Puffer, überschreibt der Koprozessor per DMA den ARM-Kernel. Die
INCAP-Capture-Ziele (`0x4c7ed000` …) liegen zwar in `framebuf_reserved`, aber
was `memory_agent`/VPROC nach „valid signal" zusätzlich scharfschaltet, ist
nicht vermessen. Der SMM-Heap (`Trid_SMM`) im Shmem ist ein Kandidat für die
Pufferquelle; ob unser Treiber ihn gen.wie Stock aufsetzt (`ShStartAddr`,
VA-Offset), ist offen.

**Nächste Messung (read-only, kein Absturz nötig):** vor jedem `SetSource` die
Ziel-/Enable-Register der DMA-Engines lesen — INCAP `0x06940900/930/938/960`,
AFBD `0x05600010/320/324`, DE2 `0x05000178/1b8/278/2b8` — und prüfen, ob eine
Zieladresse **außerhalb** der reservierten Bereiche (`/proc/iomem`) zeigt. Zeigt
eine in System-RAM, ist die Ursache gefunden, ohne den SoC zu riskieren.

## Läufe 23/24 (06.09., abends): DMA-Abtastung, `memory_agent`-Ziele, SMM-Heap — und ein Fehler im Messinstrument

**Lauf 23 (abgetastete `SetSource`):** `elog_tail.py --mmio` las 23 Register alle
20 ms und meldete Änderungen per UDP (INCAP `0x06940900/928/930/938/960/968`,
AFBD `0x05600010/14/320/324/178/098`, `0x05000178/1b8/278/2b8`, `0x068B00B8…F4/044C`).
Ergebnis: **keine einzige Änderung** bis zum Tod; letzte MIPS-Zeile wieder
`spinLock(2,quick)-End` (Ring gecacht, Patch griff nicht), letzter Herzschlag 200 ms
nach dem Aufruf. Das ist kein starker Negativbefund: die Enables standen vorher
schon auf 0, der Off-Durchlauf von `memory_agent_onoff` ändert nichts Sichtbares,
und das 20-ms-Raster verfehlt einen Tod < 20 ms nach einer Änderung.

**`memory_agent_onoff` aus der Firmware (0x8b15349c) statt aus CURRENT-TRUTH:**

| Maskenbit | Ziel (phys) | Bit |
|---|---|---|
| 0 | `0x068C00B8/C4/D0` (Helfer 0x8b17fd58) | Bit 0 |
| 1 | `0x068C00DC/E8/F4` | Bit 0 |
| 2 | `0x068C038C` | Bit 18 |
| 3 | INCAP `0x06940928/968` | Bit 31 |
| 4 | AFBD `0x05600010` Bits 0+1, `0x05600014` Bit 0 := 1 | |
| 5 | `0x05000178/1B8` | Bit 31 |
| 6 | `0x05000278/2B8` | Bit 31 |
| 7 | `0x050C06F8/0738` | Bit 31 |
| 8 | `0x050C07B8` | Bit 31 |
| 9 | `0x050C0478/4F8/578/5F8/678` | Bit 31 |

Die Tabelle in doku/62 (aus CURRENT-TRUTH) nennt für Bit 0–2 **`0x068B00B8`/`0x068B044C`**;
die Firmware baut **`0x068C…`** (`lui 0x68c`). Lauf 23 hat damit den falschen
Block abgetastet. `0x05000000` ist laut Legacy-DT der HDMI-RX-Kern („rx"),
`0x050C0000` „thdmirx", nicht DE. Der Schreibhelfer prüft nur, ob die Adresse in
einer Liste bekannter Peripheriebereiche liegt (0x02…, 0x03…, 0x05…, 0x068…),
und schreibt dann ungecacht (kseg1).

**Pfad in `update_onoff` (0x8b153140) bei `SetSource`:** aus den geloggten Zeilen
(71, 159, 159 — nie 76/83/87) folgt Signal `0x20002/3`, Flags b5=b6=0 →
`memory_agent_onoff(alle Bits, AUS)` gefolgt von `(0, AN)`. Beide Paare (bei
`AppTopSetSource` und nach `CallbackOfSignalChange`) sind Aus-Durchläufe; das
erste Paar lag 30 ms vor dem Tod und der MIPS lief danach weiter — die
Registerschreibungen selbst hängen den Bus also nicht.

**Weitere Ableitungen, alle mit Positivkontrolle im lui-Scan:** die Firmware
fasst weder CCU (`0x02001xxx`, bis auf Lesen von `0x02001DB4`), PPU (nur
`0x07000000` in 0x8b144d74), DRAM-Controller, TV-IOMMU (`0x02010000`), GIC noch
UART-Register an. Lauf 23 stellt den Demod-Bus-Riegel infrage: das TVFE-Set
und `0xd64` waren in diesem Boot an; nach dem Kaltstart ist `0xd64 = 0` und
das gesamte TVFE-Set aus — der Zustand aus doku/72 „alle Takte an" galt nur für
die fünf dort gelesenen Register. Der Vendor-`tvtop` schaltet 27 Takte; bei uns
fehlen ~15 (ADC, DTMB, I2H, CIP*, TSA*, MPG*, audio_cpu/umac/ihb). Da Lauf 23
mit vollem TVFE-Set trotzdem starb, ist das nicht die alleinige Ursache.

**Lauf 24 (SMM-Heap):** Der arm32-Aufbau lud den MIPS aus Linux
(`sunxi-mipsloader`, legacy/STATUS.md), also **nach** der vollen
Shmem-Initialisierung inkl. `Trid_SMM_Init` („cpu_comm: SMM heap initialized").
Bei uns lädt U-Boot zuerst, der Treiber adoptiert und legt den Heap nie an
(Kopf `0x4E32D000` und Slot `0x4E304D00` null; der MIPS liest den Slot bei jedem
`smmMalloc`, 0x8b123040, und liefert bei null nach „ERROR: heap[%d] is not
initialized!" 0 zurück). `analyse/hdmi-seq/smm_init.py` schreibt die Bytes von
`Trid_SMM_Init` nach (Kopf zuerst, Slot zuletzt). Danach `SetSource` unter den
Bedingungen von Lauf 23: **stirbt genauso** (`elog-udp-run24-smm.txt`).
**SMM-Heap als Ursache ausgeschlossen**; `Trid_SMM_Show`/`GetMemInfo` sind nicht
in der Routinen-Tabelle, eine MIPS-seitige Kontrolle des Heaps fehlt daher.

**Fehler im Messinstrument (wichtig):** vor jedem `SetSource` habe ich
`printk` auf `1 4 1 7` gestellt („Konsole stumm" gegen die elog-Flut). Konsolen-
stufe 1 zeigt nur EMERG; ein Oops (`pr_alert`, Stufe 1) und „Internal error"
werden **unterdrückt**, nur eine Panik käme durch. Die „Stille am UART" war zum
Teil selbstgemacht. Abhilfe: `elog_tail.py --kmsg-level 7` (Debug-Level für
elog/hb-Zeilen), Konsole auf `4 4 1 7`; zusätzlich `kmsg_udp.py` (schickt
`/dev/kmsg` per UDP an den Host, fängt einen Oops, solange eine andere CPU noch
läuft; Panik und Bus-Hänger bleiben UART-Sache). Kernel hat kein NETCONSOLE/
NETPOLL (Config), das bräuchte einen Kernelbau.

Nebenbefund: das Session-Scratchpad wurde beim Kontextwechsel geleert, der
UDP-Mitschnitt von Lauf 23 ist verloren (nur die oben zitierten Auszüge sind
erhalten). Logs liegen ab jetzt unter `analyse/hdmi-seq/`.

## Lauf 25 (06.09., 20:02): Messinstrument repariert — der Oops ist da

Bedingungen wie Lauf 23/24 (TVFE+demod an, SMM-Heap angelegt), aber Konsole auf
Stufe 4, elog-Zeilen als `<7>`, `kmsg_udp.py` auf CPU 3, `--mmio` mit 1-ms-Raster
und Zwangsmeldung alle 10 ms auf den Block des MIPS-HDMI-RX-Treibers
(`0x0680081C/840/8F0/8FC/800`, `0x06840374`, `0x068C00B8/038C`, INCAP `0x06940928`,
AFBD `0x05600014`). Vorher Lesetest dieser Register vom ARM: alle 0 außer
`0x068008FC = 0x33333333`, Board lebt.

Zeitachse (Kernel-Uhr): CALL `SetSource` 109.025 s, CALL_ACK 109.027, MIPS
`spinLock(2)-End` ≈ 109.07, letzter Tail-Sample (CPU 2) **109.191**, danach nichts
mehr per UDP; am UART des Nutzers ab **109.461** ein Oops:
`ESR = 0x96000004`, EC 0x25 DABT (current EL), **FSC 0x04 = Level-0-Translation-
Fault** (kein Eintrag der obersten Tabelle für die Adresse — Wildzeiger oder
zerstörte PGD). Die Adresse, `pc/lr` und der Call-Trace stehen beim Nutzer (tio),
`kmsg_udp` hat sie nicht mehr abgesetzt (Prozess auf CPU 3 kam nicht mehr dran).

Nebenbefund Lauf 25: **kein Register in `0x06800800…` hat sich geändert**, obwohl
der MIPS laut Lauf 17 dort schreibt (`Port_Select` → Byte `0x068008F1`,
Helfer 0x8b17fafc = `lbu/sb` über kseg1). Entweder lief die Sequenz in diesem
Lauf nicht bis dorthin, oder der ARM sieht diesen Block nicht so wie der MIPS.
Offen; Ring war wieder gecacht.

## Lauf 26 (06.09., 20:14) und der Fund dahinter: `CC_REF_LOCAL` zeigt in BL31

**Replik SYS_CFG:** die einzige echte Registeränderung der App-Schreibfolge nach
„AppTopSetSource" (`0x03000000` Bits 3:0 := 0xE) vom ARM nachgespielt — Board
lebt. Ausgeschlossen.

**Kernel-Lage (aus `/proc/iomem`):** Kernel-Code `0x48000000–0x48E9FFFF`, Daten bis
`0x4918FFFF`; `0x40000000–0x400FFFFF` reserviert = **BL31 (ATF)**, am Board per
Strings belegt („BL31: Detected Allwinner %s SoC", „PSCI: System reset failed").
Kommandozeile hat `clk_ignore_unused pd_ignore_unused`.

**Shmem-Scan (read-only):** 406 Wörter im 5-MiB-Shmem liegen im kseg0/kseg1-
Bereich; 186 davon zeigen **weder in MIPS-RAM noch in den Shmem**, 108 eindeutige
Werte. Die auffälligste Gruppe: `0x8000xxxx` mit kleinen Offsets — das sind die
`CC_REF_LOCAL`-Referenzen unseres arm64-Treibers (`BIT(31) | Arena<<28 | Offset`,
cpu_comm.h) auf ARM-privaten Speicher (`s_CommSockt`, `pcpu_comm_dev`). Sie
stehen in den **geteilten Call-Slots** (Stride 0x68): je Slot ein Semaphor-Ref
`0x800014A4+0x20·i` (`SendCommLow(..., cc_ref(sem_ptr+16))`) und als Listen-
Verkettung 40× `0x800017E4` (Listenkopf im ARM-Socket). Für den MIPS sind das
gültige kseg0-Adressen: `0x8000xxxx` → ARM-phys `0x4000xxxx` = **BL31-Code**
(`0x40001398 = d503201f` NOP, `0x400017E4 = eb13029f` …). Im arm32-Treiber standen
an diesen Stellen 32-Bit-Kernel-VAs (`0xC0xxxxxx`), die der MIPS nicht abbilden
kann. Ein `list_del`/Listen-Update des MIPS über `prev->next` schriebe heute in
BL31; die nächste PSCI-Idle-SMC führt dann Müll in EL3 aus — passt zu
Level-0-Fault + unlesbaren Seitentabellen + abgebrochenem Oops-Druck.

**Lauf 26:** `--mmio` mit 1-ms-Raster auf die 30 BL31-Zielwörter, Zwangsmeldung
alle 10 ms, Konsole 4, `kmsg_udp` auf CPU 3. Ergebnis: bis zur letzten
**empfangenen** UDP-Meldung (t = 597.576) keine Änderung. Aber: der Tail lebte laut
kmsg noch bei 597.666 (hb 25), CALL_ACK bei 597.621 — die UDP-Datagramme des Tails
ab 597.576 kamen nicht mehr an, das Todesfenster (≈ 597.6–597.7) ist **nicht
beobachtet**. Kein Negativbefund.

Abhilfe für Lauf 27: Änderungen zusätzlich als `<4>`-Zeile nach `/dev/kmsg`
(UART + CPU-3-Weiterleiter), und statt 30 Wörtern ein **Kanarien-Vergleich des
ganzen BL31-Abbilds** (`--canary 0x40000000,0x10000`, wortweise, ~10 ms Periode,
Ausgabe der geänderten Wörter mit alt→neu). Positivkontrolle vorab an einem
beschreibbaren Bereich.

## Lauf 27 und der Eingriff: Landezone für `CC_REF_LOCAL`

**Lauf 27** (BL31-Kanarie 64 KiB alle 10 ms, Positivkontrolle bestanden:
`0x4e7f0100:00000000->c0ffee01` per UDP und kmsg): stirbt wie zuvor, UDP des Tails
reißt wieder ~20 ms nach dem CALL ab (letztes `mmio=` 109.868, CALL_ACK 109.883),
Kanarie bis dahin still. Das Todesfenster bleibt per UDP unbeobachtbar; nur der
UART (Konsole 4, `<4>CANARY`-Zeilen) könnte es zeigen.

**Eingriff (Entscheidungsexperiment statt weiterer Beobachtung):** die lokalen
Referenzen des Treibers (`cc_ref` auf `s_CommSockt`/`pcpu_comm_dev`) tragen
statt `BIT(31)` den kseg1-Prefix **`0xAE78xxxx`** = ARM-phys `0x4E78xxxx`, das
letzte halbe MiB des Shmem (unbenutzt, von U-Boot genullt). Für den MIPS liest
sich so ein Ref als Null-Struktur; seine Schreibzugriffe landen sichtbar in der
Zone statt in BL31. `cpu_comm.h`/`cpu_comm_mem.c` (Sicherungen `*.vor-landezone`),
Modul `analyse/cpu-comm-arm64/hy310-cpu-comm-landezone.ko` (sha `dd926b98…`,
enthält weiterhin `callwq_kernel_cb`, Vorgabe 0), am Board als
`/root/hy310-cpu-comm-callwq-test.ko` eingesetzt (Original als `.bak`), damit
`prep_after_boot.sh` es lädt. Prüfskript `landing_zone.py`: Zone muss null sein,
Shmem darf keine `0x8000xxxx`-Wörter mehr enthalten, dafür `0xAE78xxxx`-Refs.
Erwartung: überlebt `SetSource`, ist die Kollision mit BL31 die Ursache, und die
Zone zeigt, was der MIPS schreibt; stirbt es weiter, ist die These widerlegt.

## Lauf 28 (06.09., 20:23): Landezone aktiv — und der Absturz bleibt. These widerlegt.

Vorzustand am Board bestätigt: `landing_zone.py` meldet **0** Wörter `0x8000xxxx`
im Shmem (vorher 186) und **86** neue Refs `0xAE78xxxx`; die Landezone
`0x4E780000` ist null. Der Treiber lädt sauber (`adopting the live shared region`),
`SetSource` läuft, CALL_ACK kommt (`IPC[dispatch] type=2(CALL_ACK)` bei 95.170 s),
und **~40 ms später ist der SoC tot** — genau wie mit `BIT(31)`-Refs.

**Damit ist die BL31-Kollisions-These widerlegt.** Das Verschieben der lokalen
Referenzen aus dem BL31-Bereich verhindert den Absturz nicht. Der MIPS
dereferenziert diese Refs auf dem Todespfad also nicht (oder nicht schädlich).
Die Umkodierung bleibt trotzdem richtig (ein Ref `0x8000xxxx` ist grundsätzlich
eine gültige MIPS-kseg0-Adresse in BL31 und darf dort nicht stehen) und wird
beibehalten; sie ist nur nicht die Absturzursache.

**Was Lauf 28 einengt:** Der Tod fällt reproduzierbar mit dem ARM-Handling von
**CALL_ACK** zusammen (`queueAction(CALL_ACK)` → Workqueue → `comm_ackAction`/
`command_action`, proto.c). Der Oops (früher `timekeeper_data`, Level-0-Fault)
passt zu zerstörten **obersten Seitentabellen** (`swapper_pg_dir`, phys ~0x48E91000):
ein Zugriff auf eine gültige Kernel-.bss-Adresse faultet nur, wenn der
TTBR1-Top-Eintrag fehlt. Das ist Korruption der PGD, nicht ein Wildzeiger-Lesen.
Kandidaten, die noch offen sind: der `command_action`-Pfad liest `entry_base` und
`*(u64*)(entry_base+32)` aus geteilten Feldern; ist `entry_base` selbst
verbogen, schreibt `*(u16*)(entry_base+10) |= 0x40` irgendwohin. Und der
`GetReturnbySessionId`-`list_del` schreibt `*(u32*)node_prev` / `*(u32*)(node_next+4)`
— zwei ungeprüfte Schreibziele aus der Liste (nur `is_mips_va`, kein Bereichstest).

**Nächster Schritt (Messung, die den Tod wirklich zeigt):** der UART des Nutzers
ist der einzige Kanal, der einen Oops < 40 ms nach CALL_ACK noch rausbekommt (UDP
stirbt mit dem Bus). Konsole auf 7, elog **nur** per UDP (nicht nach kmsg), damit
der Oops nicht in der elog-Flut untergeht; dann `SetSource` und die vollständige
Rückverfolgung (`pc`, `lr`, `Call trace`, faultende VA) vom UART lesen.

## Lauf 29 (06.09., 20:38): Oops-Erfassung über den UART

Konsole 7, elog **nur** per UDP (`--kmsg-exclude '.'`), Landezone aktiv (0 alte Refs,
86 neue), `SetSource`: stirbt wieder; letzte per UDP erhaltene Kernelzeile ist
„TX nach Doorbell: SENT-Bit gelöscht" bei 68.367 s, unmittelbar nach
`IPC[dispatch] CALL_ACK`. Der vollständige Oops (faultende VA, `pc`, `lr`,
`Call trace`) steht nur auf dem UART des Nutzers. Werkzeug zum Auflösen:
`tools/oops_resolve.sh SYMBOL+0xOFF` (nm + objdump gegen das vmlinux des
laufenden Kernels, Baum `linux-6.18.38-102233d4…`).

## Eingriff 2: Bereichsprüfung in `cc_deref`, Ablaufspur in `ack_action`

Der Tod fällt in allen Läufen mit dem ARM-Handling von CALL_ACK zusammen.
`ack_action` (proto.c) liest `*(u32*)(share_seq+112)` — „die Firmware spiegelt die
32-Bit-Referenz zurück, die der CALL mitgegeben hat" —, macht `cc_deref` und ruft
`cpu_comm_sem_up()` darauf: ein **Schreibzugriff** auf eine Adresse, die aus dem
Shmem stammt. `cc_deref` prüfte für nicht-lokale Refs keinen Bereich: ein
MIPS-Zeiger (`0x8B2544C8`, `0xAE302958`) ergäbe mit `Mid2Vir` eine wilde
Kernel-VA (`vbase + 0x3CF…`), und die wird beschrieben. Gleiches gilt für
`GetReturnbySessionId` (`list_del` schreibt `*(u32*)node_prev`).

Änderung (`cpu_comm_mem.c`): nicht-lokale Refs müssen in `[ShMemAddr, +ShMemSize)`
liegen, sonst `pr_warn` mit Wert und Rückgabe 0. `ack_action` loggt `sem_ref`/
`sem_ptr` (`pr_info`), damit die letzte Kernelzeile vor einem Tod den Wert nennt.
Modul `hy310-cpu-comm-derefcheck.ko` (sha `9cb19fe3…`), am Board wieder als
`/root/hy310-cpu-comm-callwq-test.ko`. Erwartung: überlebt `SetSource`, war es ein
Schreibzugriff über einen ungeprüften Ref (Warnzeile nennt ihn); stirbt es, steht
in der letzten `ack_action`-Zeile, was der MIPS zurückgespiegelt hat.

## Lauf 30 (06.09., 20:46): Bereichsprüfung greift nicht — der ARM stirbt nach korrektem `ack_action`

Letzte Kernelzeile per UDP: `ack_action cpu=1 dir=0 sem_ref=0xae781398
sem_ptr=0xffff80007929a89c` (268.979 s) — der MIPS spiegelt **unsere** Referenz
zurück, `cc_deref` verwirft nichts (0 Warnungen), `sem_up` trifft ein gültiges
Objekt. Danach Tod. Damit sind alle ARM-Treiberpfade als Ursache widerlegt:
Callback (18/21), AFBD-KMS (19), SMM-Heap (24), lokale Refs/BL31 (28),
ungeprüfte Derefs (30). AFBD `+0x178` ist laut Treiber die **Quell**adresse
(Lesen), 0x76d00000 also kein Schreibziel.

Bleibt die Hardware-/MIPS-Seite, mit dem Hinweis, dass die UDP-Lieferung des
Tails ~20 ms nach dem CALL einbricht (Speicherbus belegt?). Nächste Bisektion:
`SetSource` mit einer Nicht-HDMI-Quelle (`--source N`). Stirbt der ARM auch dann,
liegt es nicht im HDMI-RX-Pfad, sondern im gemeinsamen Teil (memory_agent, VPROC,
Anzeige-Umschaltung).

## Zähl-Test (06.09., 20:50) — Anzahl der Aufrufe ist es nicht

Vorschlag des Nutzers: dieselbe Zahl (und mehr) Aufrufe nur mit einem harmlosen
RPC. Restore macht 10 CALLs; danach **35× `THal_Vp_GetSource`** (0x24efc7c9) mit
100 ms Abstand, alle RETURN, keine Warnung, Board lebt (45 CALLs ≫ 20-Slot-FIFO).
Ein Umlauf-/Slot-Fehler in der Portierung, der jeden n-ten Aufruf tötet, ist
damit ausgeschlossen. Der Tod hängt an dem, was der MIPS bei `SetSource` tut.
Außerdem geklärt: der „Mem abort info"-Block stammt aus dem Linux-Kernel
(`arch/arm64/mm/fault.c`), U-Boot hat keinen solchen Drucker.

## Läufe 31/32 (06.09., 20:55/20:57): die Halbierung — Dummy lebt, HDMI_2 ohne Kabel stirbt

Quellen-Enum aus der Firmware (Zeigertabelle 0x8b1f50f0): 0 Dummy, 1 VideoDec,
2 Image, 3 HDMI_1, 4–6 HDMI_2–4, 7–9 CVBS_1–3, 10 ATV.

**Lauf 31, `SetSource(0)` = Dummy:** kompletter Umlauf CALL → CALL_ACK → RETURN →
RETURN_ACK, MIPS loggt `SetSource() ENTER`, `hal_source_id: 0`, `AppTopSetSource`,
`SetSource() LEAVE`; Board lebt (`elog-udp-run31-dummy.txt`). Der RPC-Mechanismus
und die App-Schreibfolge (0x06E0001C, PIO PD_CFG, SYS_CFG) sind damit unschuldig.

**Lauf 32, `SetSource(4)` = HDMI_2, Port ohne Kabel:** stirbt wie HDMI_1
(`elog-udp-run32-hdmi2.txt`). **Der Tod steckt in der HDMI-RX-Initialisierung
auf dem MIPS**, unabhängig vom anliegenden Signal: SetActivePort → „DDC and PHY
select" → `HdmiRx_Port_Select` (Byte `0x068008F1`, `0x06840376`) →
`HdmiRx_PHY_Reset` → „toggle SYSTEM_PD_HDCP SYSTEM_PD_DDC reset" →
`HdmiRx_Toggle_PD_IDCLK_Reset` → „send HPD event" → AUDIO PLL CALC → AfterEnable/
SetSignal → AV mute. Nächster Schritt: diese Registerschreibungen aus der
Firmware extrahieren und vom ARM einzeln nachspielen (Marker + Steckdose), um
den tödlichen Schritt und die fehlende Vorbedingung (Takt/Reset/Power, die der
Legacy-HDMI-RX-Treiber setzte) zu finden.

## Läufe 33/34 (06.09., 21:09/21:15): SetSource ohne Callback-Registrierung

**Lauf 33 zählt nicht:** der Hintergrund-Neustart hatte nicht gegriffen (uptime 9 min),
`prep_nocb.sh` lief auf einem Boot, auf dem prep die 10 `MipsHalCallback_*`-Routinen
schon registriert hatte; `SetSource(4)` starb wie gehabt. Kein Befund.

**Lauf 34:** Steckdosen-Neustart mit Uptime-Guard (< 180 s), `prep_nocb.sh`
(Phase 3 mit `--no-callbacks`), Kontrolle der Routinen-Tabelle, dann
`SetSource(4) --no-callbacks`. Ergebnis: siehe unten.
**Ergebnis Lauf 34:** Board frisch (uptime 25 s), Routinen-Tabelle ohne `MipsHal*`
(0 Einträge), `SetSource(4) --no-callbacks`: letzte Kernelzeile `ack_action …
sem_ref=0xae781398`, dann Tod (`elog-udp-run34-nocb.txt`, `kmsg-udp-run34.txt`).
**Der MIPS→ARM-Callback-Pfad ist als Ursache ausgeschlossen.** Nach CALL_ACK
ist der ARM-Treiber bis zum RETURN passiv; der Tod entsteht allein durch das,
was der MIPS in der HDMI-RX-Initialisierung an der Hardware tut (oder durch
einen von ihm gestarteten DMA/Bus-Effekt).

**Korrektur zu Lauf 24 (Agent-2-Befund, 06.09. 21:35):** Die Aussage „der arm32-Aufbau lud
den MIPS aus Linux" ist falsch: auch dort startete Stock-U-Boot (Fastlogo) den MIPS
(`legacy/README.md:108-112`, `legacy/docs/subsystems/boot.md:70-78`); `sunxi-mipsloader`
schaltete nur MIPS-Takt/Gate/Msgbox-Reset. Der Legacy-`cpu_comm` initialisierte den Shmem
also ebenfalls **nach** dem MIPS-Start (Vollinit über die laufende Firmware).

## Lauf 35 (06.09., 21:26): Legacy-Synopsys-Init mit `SWENABLE = 0x203B01` — stirbt trotzdem

Agent-2-Befund umgesetzt: `hdmirx_ctrl_enable.py` schreibt jetzt `0x203B01` (Bit 21
PHYCTRL_ENABLE, das der Legacy-Treiber setzte; sein `dev_info` druckte irreführend
0x3B01). Vor `SetSource(4)`: Wrapper-Nullen (Basis 0x06880000), IRQ-Masken, TIMER_REF,
CMU/DESCRAND/CED/DEFRAMER/PHY_CONFIG, SWENABLE `0x00203b01` (nachher-Lesung bestätigt).
Ergebnis: Tod wie gehabt nach `ack_action` (`elog-udp-run35-snps.txt`). INCAP `0x06940000`
steht bei uns wie bei Stock auf `0x3A7B` (doku/72:425, Stock-Capture) — U-Boots `writel(1)`
wird vom MIPS beim Boot überschrieben; kein Unterschied.

## Lauf 36 (06.09., 21:35) und der Stock-Vergleich der Registerblöcke

`dump_blocks.py` (Format der Stock-Captures) gegen `re/captures/weltneuheit/stock-pre-hdmi.txt`:
HDMI-RX_ctrl (0x06800000), INCAP, DE2_DETN **identisch**; HDMI-RX_port (0x06840000) bis auf
zwei Zählerbytes (0x70/0x74) identisch; DE2_NR_base nur `0x05000058` Bit 31 (bei uns gesetzt,
Stock 0); DE2_panel_out sechs Timing-Werte. Stock pre→post ändert im HDMI-Port-Block nur
Konfigurationsbytes (0x0c/0x10/0x28/…), keine Takte. **Lauf 36:** `0x05000058 := 0x00040000`
(Stock), `SetSource(4)` → Tod wie gehabt. Die Registerzustände der HDMI-Blöcke sind damit als
Unterschied erschöpft. Nächster Blick: die **Speicherkarte** (CMA/hohes DRAM vs. Vendor-Carve-out,
AFBD-Framebuffer bei 0x76d00000 im CMA-Bereich, Ethernet-Deskriptoren und Seitentabellen im hohen
DRAM — passt zur Symptomfolge UDP-Einbruch → Level-0-Fault).

## Lauf 37 (06.09., 21:45): Kernel verschoben, Vendor-Bereiche reserviert — stirbt trotzdem

FIT `analyse/hdmi-seq/fit-relocated/h713-kernel-reloc.fit` (im TFTP als
`h713-kernel-netboot.fit`, Original `.bak-vor-reloc-20260906`): Kernel `load/entry
0x50000000`, DTB mit `no-map` `0x48000000+0x700000` (Vendor BL31/OP-TEE) und
`0x4E800000+0xB18000` (Vendor-Shmem-Rest, mips.xml). `/proc/iomem` bestätigt: Kernel-Code
`0x50000000–0x50E9FFFF`, `48000000-486fffff reserved`, `4e300000-4f317fff reserved`.
Beide Bereiche mit Kanarie gefüllt (`canary_regions.py`, vor SetSource 0 Änderungen),
`SetSource(4)`: **Tod wie gehabt.** Adresskollision mit diesen Vendor-Bereichen
ausgeschlossen. Das verschobene FIT bleibt vorerst aktiv (neutral, mehr Reservierung).

Zwischenbilanz: Register der HDMI-Blöcke identisch mit Stock, ARM-Treiber nach CALL_ACK
passiv, Speicherkarte (Vendor-Bereiche) neutral — der Tod entsteht aus der HDMI-RX-Init
des MIPS über einen Weg, der die oberste Kernel-Seitentabelle bzw. TTBR trifft. Nächste
These: Secure-Interrupt (Group 0/FIQ) des HDMI-RX/HDCP-Blocks, die im Vendor-System EL3/
OP-TEE bedient, unser BL31 nicht.

## Lauf 38 (06.09., 21:49): DRAM-Sonde und DRAM-Controller-Watch — sauber; der Ethernet-Stau davor

`dram_probe.py` (16 MiB Userspace-Muster, ~30 Vergleiche/s, CPU 0): bis zum letzten
Herzschlag (73.055 s) **0 Fehler**; PLL_DDR `0x02001010`, MBUS `0x02001540`, DRAM-Takt
`0x02001800`, MCTL_COM `0x04810000…10`, DRAMC `0x04820000/04/30`: **keine Änderung** (1-ms-
Raster) bis 73.186 s. `SetSource(4)`-CALL 73.205, CALL_ACK 73.216, `ack_action` 73.287, danach
Ende. Auffällig: das Tail-Datagramm von t = 73.186 kam am Host **nach** der CPU-3-Zeile von
73.287 an — die Ethernet-TX-Queue von CPU 2 hing schon ~100 ms vor dem Ende, CPU 3 sendete
noch. Deutung: **DMA-Master (NIC-TX-Kanal) leiden vor den CPUs**; der Auslöser liegt zeitlich
beim CALL (±30 ms), also bei dem, was der MIPS *sofort* nach dem Doorbell tut (Routine-Tabelle
resync, `SetSource` ENTER, `update_onoff` → `memory_agent_onoff` — das Dummy **nicht** ausführt).
Kernel läuft in diesem Lauf verschoben bei 0x50000000 (FIT-reloc), was nichts ändert.

## Lauf 39 (06.09., 21:52) und H9/H10-Repliken — und eine Warnung zu den UDP-Sonden

**H9/H10 (21:51, vom ARM nachgespielt, Board lebt):** `0x068C00B8/C4/D0/DC/E8/F4` Bit 0 := 0,
`0x068C038C` Bit 18 := 0, `0x068C0014` Feld 26:24 := 4, AFBD `0x05600014 |= 1` (selbstlöschend,
liest danach 0). Nebenbefund: `0x068C0000` ist ein Puffer-Manager mit Adressen `0x04BF4200/
0x04C11200/0x04C2E200` (≙ Framebuffer 0x4BF42000… ≫ 4), also ein DMA-Block mit Zielen im
reservierten `framebuf`.

**Lauf 39:** TV-IOMMU `0x02010000…0x88` im 1-ms-Raster — **keine Änderung** bis zum Ende;
DRAM-Sonde (50-ms-Herzschlag) bis 133.478 s (nach `ack_action` 133.434) **0 Fehler**; danach
Tod. Firmware enthält keine IOMMU-Konstanten/-Strings. TV-IOMMU als Mechanismus ausgeschlossen.

**Warnung (Nutzer, 22:05):** die UDP-Sonden haben zeitweise das ganze Netz blockiert
(1-ms-Abtastung mit Zwangsmeldung alle 10 ms plus elog-Bursts). Ab jetzt nur Änderungen senden,
Herzschlag ≥ 500 ms. Damit ist auch die Deutung „NIC-TX-Queue staut vor dem Tod" (Lauf 38)
als Messartefakt verdächtig und wird nicht weiter als Indiz verwendet.

## Stand 22:40 — Gerät blockiert (TFTP), H11 (RTC/HPD-Block) als nächste These

TFTP-dnsmasq (sudo) ist weg → Board bleibt in U-Boot; nur der Nutzer kann ihn starten (doku/73 §6).
Statisch gefunden: `SendHPDEvent` (0x8b1383a0 → 0x8b135290) ist ein reiner Queue-Post; `PD_IDCLK`
nimmt seine Registeradresse aus `*(port+0x514)`. Der HPD-Pin-Block `0x07091000` ist Teil des
**RTC-Blocks 0x07090000** (Vendor-DT mit Takten `r-ahb-rtc`, `rtc-1k`, `rtc-spi`); bei uns hängt
ein ARM-Zugriff darauf den SoC, Stock/Legacy hatten den RTC-Treiber gebunden. ARISC-Firmware
greift 59-mal auf 0x0709… zu. These H11 samt Vorbehalt und Testrezept steht in doku/73.
Original-FIT ist im TFTP-Verzeichnis wiederhergestellt; Listener auf 5555/5556 laufen gedrosselt.

## 22:55 — H11 mit Registern (Agent 3 aus dem Stock-vmlinux, gegen D1-Treiber verifiziert)

`bus-r-rtc`: R_CCU `0x0701020C` Bit 0 (Gate) / Bit 16 (Reset) — identisch mit `ccu-sun20i-d1-r.c`
(dort CLK_BUS_R_RTC=7, RST_BUS_R_RTC=4). `rtc-spi`: RTC-CCU `0x07090310` Bit 31, Parent r-ahb; im
Stock-`clk_summary` (`re/captures/HY310-DEV/stock_clk_summary.txt`) an, 200 MHz. Mainline hat dafür
keinen Treiber (`rtc-sun6i.c` ohne 0x310), unser DT-RTC-Knoten ohne Bus-Takt/Reset. Die ARISC-HPD-
Routine greift ohne eigenes Gate auf 0x07091014 zu. Vendor-Linux fasst 0x07091xxx nie an (nur ARISC).
Testskript `rtc_hpd_enable.py`; Lauf 40 sobald TFTP wieder läuft. Vorbehalt bleibt: frühere Aussage
„stirbt auch mit ARISC im Reset" — wird mit Gegenprobe geklärt.

## Lauf 40 (07.09., 00:08): H11 widerlegt — Takte waren an, 0x07091014 hängt trotzdem

`rtc_hpd_enable.py`: vorher `R_CCU+0x20C = 0x00010001` (bus-r-rtc Gate **und** Reset an),
`RTC+0x310 = 0x80000009` (rtc-spi **an**), GP0-Schreib/Lese-Kontrolle ok. Der anschließende
Lesezugriff auf `0x07091010/0x07091014` (Marker davor) **hängt den SoC** — Ausgabe endet dort,
Board tot. Der Riegel aus doku/69 ist kein Taktproblem: der Bereich ist vom ARM (non-secure)
nicht erreichbar, die ARISC erreicht ihn (scp.bin HPD-Routine). Konsequenz: nur die ARISC kann
im HDMI-Pfad dort hängen — Gegenprobe `SetSource(4)` mit ARISC im Reset (Lauf 41).
TFTP-dnsmasq wurde mit dem vom Nutzer genannten Passwort per sudo neu gestartet (00:04).

## Lauf 41 (07.09., 00:17): ohne ARISC — stirbt genauso

`prep_noarisc.sh` (kein `arisc_load.py`, 0x07010100 = 0), `SetSource(4)`: letzte Kernelzeile
`ack_action`, dann Tod (`kmsg-udp-run41.txt`). ARISC/HPD-Pfad ausgeschlossen (bestätigt die
alte Aussage). Der Tod entsteht allein aus der MIPS-HDMI-RX-Init, unabhängig von ARM-Treiber,
ARISC, Takten, Speicherkarte und Registervorbedingungen.

**Neue Methode (Firmware-Bisektion aus Linux):** die HDMI-Init-Funktionen laufen vor dem ersten
`SetSource` nie → nicht im I-Cache → ein Live-Patch des Funktionseingangs (`jr ra; move v0,zero`)
über /dev/mem in den MIPS-RAM (ARM-phys = VA − 0x40000000) greift zuverlässig (anders als beim
heißen elog-Writer). Skript `mips_stub.py` (prüft Originalwort `addiu sp`, sichert, stellt
zurück). Bisektion: erst großer Block (SetActivePort), dann halbieren.

## Lauf 42 (07.09., 00:29): Stub SetActivePort (0x8b131d14) — stirbt trotzdem

`mips_stub.py stub 0x8b131d14` (Prolog `27bdffc8 afb00020` → `03e00008 00001025` verifiziert),
`SetSource(4)`: Tod wie gehabt. Da der elog-Ring gecacht bleibt (keine MIPS-Zeilen nach dem
Resync), fehlt die Positivkontrolle, ob der Stub gegriffen hat → Lauf 43: den RPC-Handler
`THal_Vp_SetSource` selbst stubben; überlebt das Board, ist die Methode wirksam und der Tod liegt
im Handler; stirbt es, liegt der Tod davor (Dispatch) oder das Stubben greift nicht.

## Lauf 43 (07.09., 00:39): Stub-Methode validiert — Handler gestubbt, Board lebt

`mips_stub.py stub 0x8b14ab68` (THal_Vp_SetSource-Handler → `jr ra; move v0,zero`), `SetSource(4)`:
RETURN nach 194 ms, `nret=0`, danach `GetSource` normal, Board lebt. **Der Live-Stub greift** (kalter
Code), und der Tod liegt innerhalb des Handlers. Lauf 42 (nur SetActivePort gestubbt) starb → der
tödliche Schritt liegt im Handler außerhalb von SetActivePort 0x8b131d14 (oder in einer zweiten
SetActivePort-Variante). Bisektion über die direkten Aufrufe des Handlers.

## Lauf 44 (07.09., 00:45): feste Aufrufe des App-SetSource gestubbt — stirbt

Struktur: RPC-Handler 0x8b14ab68 → `AppTopSetSource` 0x8b109174 → vtable+0xC = 0x8b107574 = nur
Queue-Post; die Arbeit läuft im App-Thread in 0x8b1091f4 (vtable+0x8, „SetSource End"). Deren
feste Ziele `EnterWaitingPipeLineReady` 0x8b108518, `OnCommonEvent` 0x8b1089b4, 0x8b107e3c,
0x8b107d5c gestubbt (0x8b10d400 kein Prolog) → `SetSource(4)` stirbt. Der tödliche Schritt liegt
in den `jalr`-Aufrufen (virtuelle Methoden des Quellen-Objekts) → vtable live lesen, dann stubben.

## Lauf 45 (07.09., 01:02): 13 HDMI-RX-Funktionen gestubbt — stirbt trotzdem

Gestubbt (alle mit Prolog verifiziert): SetActivePort 0x8b131d14, port-isActive 0x8b131c08,
DDC/PHY-select 0x8b132b9c, Port_Select 0x8b13e2ac, PHY_Reset 0x8b13e36c, PD-Toggle 0x8b13f580,
PD_IDCLK 0x8b140310, SendHPDEvent 0x8b1383a0, Audio-PLL 0x8b13b1dc, AfterEnable-Aufrufer
0x8b131e4c, SetSignal 0x8b134a08, CallbackOfSignalChange 0x8b1071f0, SetAVMute 0x8b134690.
`SetSource(4)`: Tod. **Die HDMI-RX-Init selbst ist nicht der Killer.** Übrig im App-Worker
0x8b1091f4: `update_onoff` 0x8b153140 / `memory_agent_onoff` 0x8b15349c (Funktionen tun mehr als
die vier nachgespielten RMWs, vtable-Aufrufe +0x30/+0x2c) und die Quellen-Schleife (vtable +0x8/+0x24
über Manager 0x8bac1a5c). Lauf 46: kumulativ + update_onoff + memory_agent_onoff.

## Lauf 46 (07.09., 01:12): + update_onoff/memory_agent_onoff gestubbt — stirbt; Quellen-Objekte gelesen

15 Stubs (13 HDMI-RX + `update_onoff` 0x8b153140 + `memory_agent_onoff` 0x8b15349c) → Tod.
Live-Lesung der Quellen-Objekte (Manager 0x8bac1a5c → Einträge {id, Kategorie, +0xC Objekt}):

| Kategorie | IDs | Objekt | vtable | +0x8 | +0x24 | +0x14 |
|---|---|---|---|---|---|---|
| 0 (analog) | 10,7,8,9 | 0x8b828b38 | 0x8b1f8cc4 | 0x8b127944 | 0x8b182c40 | 0x8b1447ac |
| 1 (HDMI) | 3,4,5,6 | 0x8b831bb8 | 0x8b1f590c | 0x8b127944 | **0x8b130aa8** | 0x8b130a54 |
| 3 (VideoDec) | 1 | 0x8b831388 | 0x8b1f900c | 0x8b127944 | 0x8b182c40 | 0x8b14669c |
| 5 (Dummy) | 0 | 0x8b89b7cc | 0x8b1f5538 | 0x8b127944 | 0x8b182c40 | 0x8b12fc00 |

Die Quellen-Schleife in 0x8b1091f4 ruft für jede Kategorie Slot +0x24 mit der neuen Quellen-ID;
nur das HDMI-Objekt hat einen eigenen Handler (0x8b130aa8). Lauf 47: kumulativ + 0x8b130aa8.

## Lauf 47 (07.09., 01:22): + HDMI-Slot-Handler 0x8b130aa8 gestubbt — stirbt

16 Stubs (15 + 0x8b130aa8, das ruft 0x8b134328 „SetBlueScreen/bOutputEnabled" + jalr) → Tod.
Einschränkung: Läufe 44–47 hatten verschiedene Stub-Mengen (44: EnterWaitingPipeLineReady,
OnCommonEvent, 0x8b107e3c, 0x8b107d5c; 45–47 ohne diese). Als Nächstes Container-Test: nur den
App-Worker 0x8b1091f4 stubben (Lauf 48). Überlebt → Killer in dessen Aufrufen (dann alle
kumulativ stubben und zurückhalbieren); stirbt → Tod auf dem Nachrichtenpfad zwischen
`AppTopSetSource` (Post 0x8b107574) und dem Worker.

## Lauf 48 (07.09., 01:33): nur App-Worker 0x8b1091f4 gestubbt — stirbt

Der Worker-Stub greift (kalter Code, wie der Handler-Stub in Lauf 43), der ARM stirbt aber
trotzdem. Zusammen mit Lauf 43 (Handler-Eingang 0x8b14ab68 gestubbt = überlebt) heißt das: der
Killer liegt **nicht** im Worker 0x8b1091f4, sondern in dem, was der Handler 0x8b14ab68 sonst noch
direkt tut. Der Handler ruft (außer Logs) nur `0x8b12bac4` und `AppTopSetSource 0x8b109174`.
Lauf 49: `0x8b109174` stubben (Dummy nutzt es auch und lebt → Stub sollte sicher sein).

## Lauf 49 (07.09., 01:44): scharfe Lokalisierung — der Tod hängt an AppTopSetSource, nicht am Worker

`mips_stub.py stub 0x8b109174` (AppTopSetSource) → `SetSource(4)` **lebt** (RETURN 160 ms, GetSource ok).
Zusammen mit Lauf 48 (Worker 0x8b1091f4 gestubbt → stirbt) und Lauf 43 (Handler 0x8b14ab68 gestubbt →
lebt):

* AppTopSetSource 0x8b109174 ist die pivotale Funktion. Sie loggt und ruft dann
  `obj->vtable[+0xC](obj, &source_id)` mit `obj = *(0x8b253578)` (live: obj=0x8b8c8d7c, vt=0x8b1ebb6c,
  **vt+0xC = 0x8b107574**). 0x8b107574 ist ein reiner Enqueue (`jal 0x8b15bb80`).
* Der Tod entsteht als **Folge dieses Enqueue**, aber **nicht** im Worker 0x8b1091f4 (vt+0x8), denn dessen
  Stub verhindert ihn nicht. Also dispatcht die App-Thread-Schleife die Nachricht an einen **anderen**
  per-Quelle-Handler (Callback im Nachrichtenobjekt), der bei HDMI etwas tut, das den ARM-Kernel
  korrumpiert. Dummy postet dieselbe Nachricht und lebt → der Handler verzweigt nach Quelle.

**Damit ist der Suchraum eine Funktion:** der Konsument der Queue hinter 0x8b15bb80 und sein
per-Quelle-Dispatch. Das ist reines statisches RE (Message-Loop, Callback-Feld im Item) → an einen
Agenten delegiert; Ergebnis (die tödliche Funktion) wird per `mips_stub.py` am Gerät verifiziert.

## Lauf 50 (07.09., 01:55): HDMI-Enable-Methode 0x8b130a54 gestubbt — stirbt

Einzelnes Stubben der HDMI-`Enable`-vtable-Methode (vt+0x14, ruft `HDMIRx_SetHDCP22KeyData`-Pfad)
verhindert den Tod nicht (wie schon vt+0x24 in Lauf 47). Einzelmethoden-Raten ist erschöpft; der
Queue-Konsument/Dispatch (hinter 0x8b15bb80) muss gefunden werden (Agent läuft). Board für den
nächsten Verifikationslauf neu gestartet; Stubs zurückgesetzt.

## Agent 4 + Dispatch-Tail (07.09., 02:10)

Agent-Befund (verifiziert am Disassembly): 0x8b15bb80 = Enqueue (Item {0, source_id} auf dem Stack von
AppTopSetSource, Queue-Handle obj+8, RTOS-Send 0x8b103504/0x8b103910); Konsument ist die
**Message-Loop 0x8b1091f4** selbst: sie parkt im Dequeue 0x8b15bc60 und läuft nach dem Wecken im
**Dispatch-Tail** weiter — ein Eingangs-Stub trifft eine bereits parkende Funktion nicht (erklärt
Lauf 48). Der Tail (0x8b1094d0–0x8b109764) ruft u. a.: OnCommonEvent 0x8b1089b4 („seamless"),
FreeRTOS-Critical-Section (port.c 0x8b102dd8/0x8b102de4) um 0x8b1bc654, IsNeedToUpdateTfdForNewPicMode
0x8b1087f8, 0x8b107770, win_dbg_cmd_set_overscan 0x8b1abd18 (2×), **Quellen-vt+0x14 (2×)**,
AppRegisterCallbackOfSignalChange 0x8b10711c (3×), 0x8b108170, EnterWaitingWindowsReady 0x8b108394,
0x8b108474, 0x8b108644 (2×), AppDbgEnableWinMgr 0x8b108ebc, 0x8b1071b8, 0x8b1ac25c.
In diesem Boot lief vor SetSource keine HDMI-Init (elog 0 Treffer) → Stubs an kalten Funktionen greifen.
Lauf 51: alle stubbaren Tail-Funktionen + vt+0x14 gestubbt.

## Lauf 51 (07.09., 02:12): **ÜBERLEBT** — Killer im Dispatch-Tail eingekreist

14 Stubs: 0x8b107770, 0x8b108170, 0x8b108644, 0x8b108394 (EnterWaitingWindowsReady), 0x8b108474,
0x8b108ebc (AppDbgEnableWinMgr), 0x8b10711c (AppRegisterCallbackOfSignalChange), 0x8b1071b8,
0x8b1ac25c, 0x8b130a54 (HDMI vt+0x14), 0x8b1089b4 (OnCommonEvent), 0x8b108518
(EnterWaitingPipeLineReady), 0x8b107e3c, 0x8b107d5c → `SetSource(4)` RETURN 176 ms, `nret=0`,
GetSource ok, Board lebt. Da Lauf 50 (nur 0x8b130a54) und Lauf 44 (nur 0x8b108518/0x8b1089b4/
0x8b107e3c/0x8b107d5c) starben, liegt der Killer unter den übrigen neun (oder in einer
Kombination). Rückwärts-Halbierung ab Lauf 52.

## Lauf 52 lebt (nur die neun Tail-Funktionen); Lauf 53 ungültig

Lauf 52 (02:15): Stubs nur 0x8b107770, 0x8b108170, 0x8b108644, 0x8b108394, 0x8b108474, 0x8b108ebc,
0x8b10711c, 0x8b1071b8, 0x8b1ac25c → RETURN 161 ms, Board lebt. Der Killer liegt unter diesen neun.
Lauf 53 (Gruppe A) ungültig: `mips_stub.py stub` meldete 0 Stubs (Ursache unklar, evtl. Zustand nach
`restore`), SetSource lief ungeschützt → Tod. Ab jetzt: Stub-Ausgabe vollständig protokollieren und
SetSource nur starten, wenn die Anzahl stimmt.

## Lauf 53b (07.09., 02:28): Gruppe A gestubbt (verifiziert 5) — stirbt → Killer in Gruppe B

Gruppe A = 0x8b107770, 0x8b108170, 0x8b108644, 0x8b108394 (EnterWaitingWindowsReady), 0x8b108474.
Mit Lauf 52 (alle neun leben) folgt: Killer ∈ Gruppe B = 0x8b108ebc (AppDbgEnableWinMgr),
0x8b10711c (AppRegisterCallbackOfSignalChange), 0x8b1071b8 (dto., zweite Variante), 0x8b1ac25c.
Lauf 54: Gruppe B stubben.

## Lauf 54 (07.09., 02:40): Gruppe B gestubbt (verifiziert 4) — stirbt

A allein (53b) tot, B allein (54) tot, A+B (52) lebt. Entweder je ein Killer pro Gruppe, oder der
Killer liegt hinter beiden und wird nur bei „Erfolg" beider Aufrufe erreicht (Stub liefert 0 →
Fehlerpfad umgeht ihn). Klärung über den Kontrollfluss des Tails (0x8b109540–0x8b109770).

## Statik zu Gruppe A/B (07.09., 02:50)

Gruppe B (0x8b108ebc, 0x8b10711c, 0x8b1071b8, 0x8b1ac25c) hat keine festen Callees — sie registriert
Callbacks über vtables. Gruppe A: 0x8b108170 und 0x8b108644 rufen beide **0x8b1080a8** (gemeinsamer
Worker: holt Handle über 0x8b15836c = `*a0 = 0x8b15789c()`, benennt Layer `%s_Top/%s_Bottom`
(0x8b184084), setzt Gerätekommandos über vtable+0x1C (0x8b1583d0, Kommando 0x12E), 0x8b153724 ×3).
0x8b108474 → 0x8b12c2c0; 0x8b107770 → win_dbg_cmd_set_overscan 0x8b1abd18 ×8 + 0x8b12c… Hypothese:
auch die von B registrierten Callbacks enden in 0x8b1080a8 → Lauf 55 stubbt nur 0x8b1080a8.

## Lauf 55 (07.09., 02:58): nur 0x8b1080a8 gestubbt — stirbt

Der gemeinsame A-Worker allein reicht nicht. Modell: zwei unabhängige Killer (je einer in A und B),
jeder für sich tödlich. Bisektion: B dauerhaft gestubbt, A halbiert (A1 = 0x8b107770, 0x8b108170;
A2 = 0x8b108644, 0x8b108394, 0x8b108474); danach A gestubbt, B halbiert (B1 = 0x8b108ebc,
0x8b10711c; B2 = 0x8b1071b8, 0x8b1ac25c).

## Läufe 56/57 (07.09., 03:05): A-Killer = 0x8b108170

Lauf 56: B (0x8b108ebc, 0x8b10711c, 0x8b1071b8, 0x8b1ac25c) + A1 (0x8b107770, 0x8b108170) → lebt.
Lauf 57: B + nur 0x8b108170 → lebt (RETURN 161 ms). Damit ist auf der A-Seite **0x8b108170** die
tödliche Funktion (Callees: 0x8b15836c Handle, 0x8b184084 Layer `%s_Top/%s_Bottom` ×3, 0x8b1080a8,
0x8b1583d0 Kommando 0x12E, 0x8b158394). Lauf 58: B halbieren bei gestubbtem 0x8b108170.

## Lauf 58 (07.09., 03:10): Board stirbt vor dem Stubben — verzögerter Tod nach Lauf 57

Die ssh-Sitzung von Lauf 58 brach sofort ab (kein „Stubs="), d. h. das Board war nach Lauf 57
(B + 0x8b108170 gestubbt, „lebt" nach ~5 s) **mit Verzögerung** gestorben (~15 s). Vorbehalt für
alle „lebt"-Urteile: der MIPS arbeitet nach dem RETURN weiter (Signal-/HPD-Handling, Timer). Ab jetzt
gilt „lebt" erst nach 40 s Nachbeobachtung mit erneutem RPC. Läufe 51/52 hatten längere
Überlebenszeiten (mehrere Folgeläufe), 56/57 nur wenige Sekunden — 57 ist damit fraglich.

## Lauf 58b (07.09., 03:20): 0x8b108170 + B1 → lebt dauerhaft (45 s, 3 RPCs)

Stubs 0x8b108170, 0x8b108ebc, 0x8b10711c → RETURN, GetSource bei t+5/20/40 s ok. B-Killer ∈ B1 =
{0x8b108ebc AppDbgEnableWinMgr, 0x8b10711c AppRegisterCallbackOfSignalChange}. Lauf 59 trennt.

## Lauf 59 (07.09., 03:25): nur 0x8b108170 + 0x8b10711c → lebt (45 s) — Vorbehalt „gleicher Boot"

Auf demselben Boot wie 58b; die Quelle stand schon auf HDMI_2, ein zweites SetSource(4) kann
verkürzt laufen. **Solide (frischer Boot):** leben 51 (14 Stubs), 56 (B + 0x8b107770 + 0x8b108170),
58b (0x8b108170 + 0x8b108ebc + 0x8b10711c); sterben 53b (A), 54 (B), 55 (0x8b1080a8), 50 (vt+0x14).
Protokoll für Folgeläufe ohne Neustart: Stubs zurück → `SetSource(0)` (Dummy) als Rücksetzer →
neue Stubs → `SetSource(4)` → 45 s Nachbeobachtung mit RPCs.

## Lauf 60 (07.09., 03:30): keine Ausgabe — Board bereits tot (verzögerter Tod nach Lauf 59)

Die ssh-Sitzung hing vor der ersten Ausgabe. Wie nach Lauf 57 ist das Board nach dem „lebenden"
Lauf 59 (nur 0x8b108170 + 0x8b10711c, 45 s beobachtet) später gestorben, oder der Rücksetzer
SetSource(0) nach HDMI war tödlich. Same-Boot-Läufe sind damit nicht belastbar. Regel: **nur frische
Boots, eine Variable je Lauf, 45 s Nachbeobachtung.** Solide lebend: {108170,108ebc,10711c} (58b).
Lauf 61: {0x8b108170, 0x8b10711c} frisch; Lauf 62: {0x8b108170, 0x8b108ebc} frisch.

## Lauf 61 (07.09., 03:40): frischer Boot, nur 0x8b108170 + 0x8b10711c gestubbt → lebt 60 s (solide)

RETURN, GetSource bei t+5/20/40/60 s ok. **Ergebnis der Bisektion:** der Tod entsteht, wenn der
MIPS nach `SetSource(HDMI)` das Anzeige-Fenster für die Quelle programmiert — direkt in
**0x8b108170** (Layer-Objekte `%s_Top/%s_Bottom` über 0x8b184084, Layer-vtable +0x10/+0x14/+0x18,
Worker 0x8b1080a8, Gerätekommando 0x12E über 0x8b1583d0, Handle 0x8b15836c/0x8b158394) und/oder über
den in **0x8b10711c** (`AppRegisterCallbackOfSignalChange`, kopiert eine 0xAC-Byte-Callback-Struktur
und registriert sie bei `*(0x8b253574)->vt[+0xC]`) registrierten Signalwechsel-Callback, der
dieselbe Fensterkonfiguration auslöst. Jeder Weg allein ist tödlich (53b/54), beide gestubbt →
lebt (51, 56, 58b, 61). Dummy programmiert kein Fenster → lebt.

**Wichtig (Nutzer):** Stubs sind nur Messwerkzeug. Der Fix gehört auf die ARM-/Umgebungsseite:
es ist zu klären, welche Register/DMA-Ziele die Fensterprogrammierung (DE/AFBD/Scaler/Write-back)
setzt und warum diese bei uns Kernel-RAM treffen (Speicherkarte, Konfigurationswerte wie
`sys:frame_buf_addr`, Zustand der vom ARM-KMS-Treiber belegten Blöcke).

## Statik nach Lauf 61 (07.09., 03:55): Window-Manager-Pfad, Null-Handle

0x8b184084 ist nur ein Getter: `*(0x8bac1a60)` = Window-Manager 0x8b89b9d8 (vtable 0x8b202210:
+0x10=0x8b183ae8, +0x14=0x8b183c8c, +0x18=0x8b183a60 (Setter `*(a0+0x14)=a1`), +0xC=0x8b183d5c).
0x8b108170 ruft winmgr +0x14, +0x10, +0x18, den Worker 0x8b1080a8 und Kommando 0x12F über
0x8b1583d0 (`dev=*(a0); dev->vt[+0x1C](dev,&{0x12F,a1})`). Das Geräteobjekt kommt aus 0x8b15789c =
`*(0x8b4a9da8)` — **live 0**, Flag `0x8b4a9afc` = 0. Der Handle-Schreiber wurde per lui/sw-Muster
nicht gefunden (andere Basisform); offen: wer das Objekt im Stock anlegt (MIPS-intern beim Init
oder ARM-seitig per CPU_COMM/TSE-Konfiguration) und welches DMA-/Registerziel die
Fensterprogrammierung mit Null-Handle trifft. Board wiederhergestellt (Stubs zurück), bleibt oben.

## Agent 5 + Live-Lesungen (07.09., 04:10)

Fensterfreigabe 0x8b183ae8 schreibt DE `0x0500103C` Bits 2/3 — Replik vom ARM (`|= 4`) harmlos (40 s).
Display-Init 0x8b152b2c: WR32-Schleife über DE 0x05001000–0x050015FC, dann `0x05001528` :=
`sys:frame_buf_addr`, `0x0500152C` := `sys:frame_buf_virtual_addr` — live beide = 0x4BF41000
(reservierter `framebuf`), also gesetzt und unkritisch. Handle `*(0x8b4a9da8)` und Flag `0x8b4a9afc`
sind 0, aber Kommando 0x12F wird nur bei a1≠0 geschickt (Null-Deref wäre MIPS-seitig). Layer-/
Fensterklasse: Unterobjekt 0x8b49b4f8 (vtable 0x8b202ea8, Methoden 0x8b186048…0x8b18709c,
0x8b188a84…) — nächster Scan auf Registerblöcke/DMA-Adressfelder.

## 04:20 — Die Fensterprogrammierung ist TSE-datengetrieben (TFDHandler)

Das Unterobjekt 0x8b49b4f8 (vtable 0x8b202ea8) ist der **TFD-Handler** (`TFDHandler.cpp`:
WriteModule 0x8b186d28, WriteModules 0x8b186ebc/0x8b186f94, WriteModulesByUI 0x8b18709c,
„Load TSE", GetPanelTiming 0x8b186aa4/0x8b186bf0, GetStateID, „Cannot find module 0x%08x").
Die Fensterumschaltung schreibt also **Registergruppen aus der TSE-Datenbank** für den HDMI-Zustand —
Daten, die unser U-Boot mit `h713_disp init 0x30` (ProjectID) bereitstellt. Die Guard-Whitelist des
Schreibhelfers (0x8b17f8ec) umfasst neben 0x05…/0x06… auch 0x02000000 (PIO), 0x02010000 (IOMMU),
0x03000000 (SYS_CFG), 0x03002000–0x03005000 (Msgbox/Spinlock), 0x03006000 (SID), **0x03010000–0x0302FFFF
(GIC)**, 0x03040000, 0x03060000 (MIPS-Ctrl). Nächster Schritt: TSE-Module des HDMI-Zustands parsen
(Adressen/Werte) und gegen diese Blöcke prüfen; ARM-seitiger Fix = TSE-Daten/ProjectID bzw.
Schutz der betroffenen Register.

**Korrektur 04:30:** ProjectID 0x30 ist für den HY310 korrekt (doku/40: eigenes MIPS-Log „load group:
ProjectID_0x0030"; 0x34 ist cstengers Board) — keine Fehlspur dort. Die TSE-Module des HDMI-Zustands
(ProjectID_0x0030.TSE + database.TSE) sind zu parsen; U-Boot lädt database, pq_custom, projecttable,
ProjectID (in dieser Reihenfolge) nach 0x4BE41000ff.

## display_cfg.xml (Board, 04:40)

Vendor-Speicherkarte des MIPS: boot 0x4B100000 (4 KiB), C-Code 0x4B101000 (12 MiB), debug
0x4BD01000 (1 MiB), cfg 0x4BE01000 (256 KiB), **TSE 0x4BE41000 (1 MiB)**, **frame_buffer 0x4BF41000
(26 MiB, virtual = physical)** bis 0x4D941000. Deckt sich mit unseren Reservierungen
(mips-firmware 0x4B100000+0xE41000, framebuf 0x4BF41000+0x1A00000, decoder 0x4D941000). Die
DE-Basisregister 0x05001528/2C tragen genau diesen frame_buffer-Wert. TSE-Dateien vom Board sind
identisch mit den Repo-Kopien (md5), liegen unter `analyse/tse/board/`; Agent 6 rekonstruiert das
TSE-Modulformat und listet die HDMI-Module.

## TSE-Format rekonstruiert (Agent 6) und Lauf 62 (07.09., 05:00): ARM-Replik der HDMI-Registermodule lebt

`tools/tse_dump.py` (Agent 6): TSE-Dateiformat, Gruppen/Module/States/Attribute, RegTableFW-Blobs
(13-B-Einträge, Basis+addr·Breite, Maske/Wert big-endian, WR bei Vollmaske sonst RMW über die
Helfer 0x8b17fab4/fbbc/fd10 bzw. 0x8b17fafc/fc04/fd58). Validierung: 170 Module, 4614 Schreibungen,
**100 % in 0x05/0x06**, keine absoluten DRAM-Adressen; Puffer kommen zur Laufzeit aus MemoryFW
(„DynamicMemory_1024M_1024M_PROJECTOR", Speichermanager `*(0x8bac1a90)`). HDMI-Filter (source
0x10013 = HDMI_2, signal 0x20003): 87 States / 1210 Schreibungen, davon 41 States unbedingt (456).
Live-Klassifikation der DMA-Zielregister (INCAP 0x069408xx/09xx, DE 0x050001xx/02xx/07xx, Panel-WB
0x05140xxx, 0x068C00xx): alle echten Pufferzeiger (16-Byte-Einheit) in reserviertem Speicher;
„adressartige" Treffer sind Geometrie (1920/1080/1024) oder Koeffizienten.
**Lauf 62:** `tse_replay.py` (ARM, ohne MIPS) schreibt die 456 unbedingten HDMI-Schreibungen in
TSE-Reihenfolge mit Maske/Breite → Board lebt (45 s, RPCs ok). Lauf 63: alle 1210.

## Lauf 63 (07.09., 05:03): alle 1210 TSE-HDMI-Schreibungen vom ARM → lebt

Damit sind die Registerschreibungen des TSE-HDMI-Programms als Killer **ausgeschlossen** (auch die
bedingten States). Der tödliche Anteil der Fensterprogrammierung ist der **Laufzeitanteil auf dem
MIPS**: Speichermanager/MemoryFW (Pufferanlage, DMA-Basisregister aus Feldern) und Layer-Objekt-
Methoden. Nächste Messung: Speichermanager-Objekt `*(0x8bac1a90)` lesen; dann (frischer Boot) ein
echtes `SetSource(4)` mit 1-ms-Überwachung der Pufferregister (INCAP 0x069408F0–0x06940944,
DE 0x05000140–0x05000194/0x240–0x294, 0x068C00C0–FC, Panel-WB) und Meldung der neuen Werte per
kmsg `<4>`.

## 05:10 — Speichermanager gelesen: Top 0x4D4F3000, 4,3 MiB bis framebuf-Ende; Vendor gibt dem MIPS bis 0x4E300000

`*(0x8bac1a90)` = 0x8b584cb8: Basis +0x0C = 0x4BF42000, Top +0x18 = **0x4D4F3000**, Listen bei
0x8b785xxx. Unser `framebuf` endet bei 0x4D941000 (Rest 4,3 MiB), Vendor-`mips_memory`
(`mips_only_size 0x3200000`) reicht bis **0x4E300000**; 0x4D961000–0x4E2FFFFF ist bei uns Kernel-RAM.
These: HDMI-Pufferallokation läuft über 0x4D941000 hinaus, Capture-DMA schreibt in den Kernel.
Test (Lauf 64): FIT `analyse/hdmi-seq/fit-mipsmem/` mit `no-map` 0x4D961000+0x99F000 (Kernel bleibt
0x48000000), Kanarie in die Zone, `SetSource(4)`, Speichermanager-Top mitlesen.

## Lauf 64 (07.09., 05:07 Board-Uhr): Speicherschwanz reserviert — stirbt trotzdem (H12 negativ)

FIT `analyse/hdmi-seq/fit-mipsmem/` (Kernel 0x48000000, DTB mit `mips-memory-tail@4d961000 { reg = <0x4d961000 0x99f000>; no-map; }`
= Vendor-`mips_memory` bis 0x4E300000). Reservierung aktiv: DT-Knoten unter `/sys/firmware/devicetree/base/reserved-memory/`
vorhanden; `/proc/iomem` verschmilzt sie zu `4b100000-4e7fffff : reserved` (mein grep-Guard auf `4d961000-4e2fffff`
war deshalb falsch und hat die erste Kette abgebrochen). Ablauf: prep, Speichermanager-Top `0x4b584cd0` = 0x4D4F3000
(wie zuvor), Tail mit 1-ms-`--mmio` auf Top + INCAP/DE/TVTOP-Pufferregister, `tvfe_enable`, `SetSource(4)`: CALL_ACK,
`ack_action`, dann Stille (letzter hb t=82.460, ~100 ms nach CALL); **keine** Änderung an einem der 17 abgetasteten
Register bis zum letzten Datagramm. Board tot (kein ssh). Kanarie konnte nicht gefüllt werden (Skript lag noch nicht am
Board — jetzt `analyse/hdmi-seq/canary_tail.py`). **Ergebnis: Die fehlende Reservierung 0x4d961000–0x4e2fffff ist nicht
die Ursache** (als alleiniger ARM-seitiger Fix ausgeschlossen); ob der MIPS dort schreibt, ist weiter ungemessen.
Logs: `elog-udp-run64-mipsmem.txt`, `kmsg-udp-run64.txt`.

## Lauf 65 (07.09., Board-Uhr 04:59): kmsg-Weiterleiter auf CPU1 (SCHED_FIFO 80) — kein Oops sichtbar

Korrektur des Aufbaus: bisher lief `kmsg_udp.py` auf **CPU 3 = Msgbox-IRQ-CPU** (prep setzt IRQ 332 → CPU3). Ein Oops
im Msgbox-IRQ-Kontext auf CPU3 hätte den Weiterleiter dort nie mehr laufen lassen. Lauf 65: `chrt -f 80 taskset -c 1
kmsg_udp.py`, elog-Tail CPU2 (nur UDP, hb 500 ms), Netz-IRQ CPU0, Konsole 4, `SetSource(4)` ohne Stubs. Ergebnis:
identisch — letzte kmsg-Zeile `ack_action … sem_ref=0xae781398`, letzte elog-Zeile `spinLock(2,quick)-End`, ssh
„closed by remote host“, Board tot. **Kein Oops** trotz Weiterleiter auf einer anderen CPU. (Erster Versuch desselben
Laufs ohne Host-Listener verloren — Listener-Guard jetzt hart im Skript.)

Bewertung zusammen mit der Nutzerangabe (UART: in späteren Läufen kein Oops mehr, der eine gesehene Oops war ein
Kernel-Datenabort mit Level-0-Translation-Fault, abgeschnitten nach `ISS2`) und cstengers Befunden vom 05.09.
(`analyse/hdmi-seq/cstenger-commits-20260905.txt`: „two owners of the display hardware locks the SoC“, „Network and
serial both dead“, „a bad address is fatal, not an error“ für MIPS-Zugriffe): **Der Tod ist ein Bus-/SoC-Hänger, kein
Software-Fehler des Kernels.** Ein Level-0-Translation-Fault entsteht auch, wenn der MMU-Tabellenlauf aus einem
hängenden Speicherpfad Nullen liest. Der `select()`-basierte Weiterleiter kann einen Oops, der in `panic()` endet,
grundsätzlich nicht absetzen (`wake_up_klogd` per irq_work auf der druckenden CPU mit gesperrten IRQs) — auch das
erklärt frühere Nicht-Beobachtungen. Netconsole scheidet praktisch aus: r8152 sendet aus einem Tasklet, das im
Oops-/Panic-Kontext nicht läuft.

Konsequenz: Messinstrument wechseln — Hardware-Watchdog (`2051000.watchdog`, sunxi_wdt, 24-MHz-Domäne) scharf halten,
damit der SoC nach dem Hänger von selbst zurückkommt; prüfen, ob DRAM den Warm-Reset überlebt (Kanarie im no-map-
Schwanz). Wenn ja: Kernel-Log-Ring (`__log_buf`), MIPS-elog-Ring und Kanarien **post mortem** lesen (Lauf 66).

### cstengers Commits vom 05.09. (Branch h713-display-video-path) — relevant für uns

* Koexistenz Linux + lebender MIPS ist bei ihm gelöst, indem U-Boot `h713_disp init 0x34` die Firmware vollständig
  hochbringt und nicht quiesziert (identisch zu unserem Aufbau mit 0x30).
* `SetSource(1)` (VideoDec) läuft bei ihm durch, erzeugt aber **keine** Fensterneuberechnung („no UpdateWce, no
  CalcWindow, no PanelWinNode::WriteReg“) — er hat den Punkt, an dem wir sterben, noch nie erreicht.
* Sein DECD-Vsync-Handler, der die AFBD-Ringregister (0x05600070/84/98, int_to_display, Dirty-Latch) 60× pro Sekunde
  neu schreibt, hängt den SoC, sobald die Firmware dieselbe Quelle programmiert; **eine** Schreibung überlebt.
  „Unbound is not quiesced“: nach Unbind des KMS-Treibers scannt die AFBD-Fetch-Engine weiter (IOMMU-Fault Master 2).
  → Unser Lauf 19 (`rmmod sun50i_h713_afbd` → stirbt) schließt den AFBD-Treiber aus, **nicht** einen Zwei-Master-
  Konflikt auf der Hardware, die U-Boot/der Treiber hinterlassen hat.
* Frame-Übergabe an die Firmware ist ein physischer Zeiger in 0x05600098 (Firmware liest, maskiert `& 0x0fffffff |
  0xa0000000`, kopiert 144 Byte); MMIO-Helfer der Firmware: `phys = (addr + 0xB5000000) | 0x20000000`; ein falscher
  Zugriff (`regr 0xba600140`) hängt den SoC sofort.
* WCE-Knoten (Cap/NR/DETN/Proc/Panel, TWCETop +0x68…+0x78) werden per `node->vt[+0x10](node, mask)` mit
  Literal-Masken angewendet (~70 Stellen 0x8b1a8000–0x8b1a9900); PanelWinNode Slot 4 schreibt ~25 LVDS-Register als
  RMW, darunter `0x051c0200/0x051c0204`; NRWinNode Slot 4 schreibt AFBD `0x05600010/14/20–54` + Commit.
  Diese Schreibungen sind **Code-getrieben, nicht TSE-Daten** — unsere TSE-Replik (Läufe 62/63) deckt sie nicht ab.
* Vp_Init (Para[2] = Staging-Adresse, 55296-Byte-memcpy) registriert den Signalwechsel-Callback selbst; drei
  Blue-Screen-Handles (Level 0/1/2, `blue_screen.cpp`).

## Lauf 66 + Watchdog-Charakterisierung (07.09., 05:07–05:45): Einmal-Timer statt Steckdose

**Lauf 66** (Watchdog über `/dev/watchdog`, sunxi_wdt, 16 s, Kanarie im Schwanz, `SetSource(4)`): Board stirbt wie
immer, **kommt aber nicht zurück** (300 s). Positivkontrolle auf gesundem Board: Pinger getötet → kein Reset, Uptime
läuft weiter; Register `CFG 0x02051014 = 0`, `MODE 0x02051018 = 0x1F` — der Treiber (DT-Compatible
`allwinner,sun50i-h6-wdt`/`sun6i-a31-wdt`) schreibt ohne Schlüssel und trifft nichts. Vendor-DT: `allwinner,sun50i-wdt`
(Vendor-Treiber mit Schlüssel).

**Schlüsseltest:** `CFG = 0x16aa0001`, `MODE = 0x16aa00B1` per devmem → Reset nach ≤16 s, Board bootet von selbst
(Rückkehr nach 40 s). DT-Fix: Compatible `allwinner,sun20i-d1-wdt` (gleiches Layout, Schlüssel 0x16aa) — noch nicht
umgesetzt.

**Aber:** jeder **weitere** Schreibzugriff auf den Block nach dem Scharfschalten **hängt den SoC sofort** (ssh weg,
Reset dann durch den laufenden Watchdog): CTRL-Reload `0x16aa14ad`, CTRL `0x16aa0001`, MODE erneut `0x16aa00B1`,
MODE `0x16aa0000` (aus) — je ein Lauf, alle identisch (05:36–05:41). Das erklärt auch Lauf 67 (Pinger im Hintergrund
→ erster Reload → Hänger vor SetSource, Takte nie getestet) und den scheinbar erfolgreichen Vordergrund-Pinger
(6 s, dann Reset — war ebenfalls Hänger + Reset). **Folge:** kein Kick, kein Abschalten möglich → der Watchdog ist
ein **Einmal-Timer** (`analyse/hdmi-seq/wdt_arm.py`): scharf schalten, sofort SetSource, ≤14 s beobachten, Reset
kommt in jedem Fall. Genau das braucht das Post-mortem-Verfahren (Rettungs-FIT `analyse/hdmi-seq/fit-rescue/`,
Kernel bei 0x50000000, `no-map` 0x48000000+0x1200000, `pm_read.py` liest `__log_buf` phys 0x4910cd38 und den
MIPS-elog-Ring 0x4B272D9C). Offen: warum der zweite Schreibzugriff hängt (APB-Takt/Gate des WDT-Blocks? Vendor
schreibt vermutlich mit anderem Protokoll) — für die Fehlersuche nicht nötig.

**Nebenbefund `tvtop_stock_clks.py` (Soll/Ist nach prep, 07.09.):** pll-video1 (0x048) und pll-adc (0x060) **aus**;
Muxe `adc`/`dtmb-120M` (Ist pll-video0/pll-periph0, Soll pll-adc), `i2h` (Ist pll-video0-4x, Soll pll-periph0-2x),
`audio_ihb` (Ist pll-video0-4x, Soll pll-periph0) abweichend; 15 TVFE-Gates + bus-demod aus (prep ruft
`tvfe_enable` nicht). Stock-tvtop hält all das an (27 Takte, 3 Resets, 22 Eltern; Vendor-CCU-Tabelle jetzt
vollständig in `analyse/hdmi-seq/vendor-ccu-table.txt`, Stock-vmlinux). Test = Lauf 68.

## Lauf 68 (07.09., 05:43): Stock-tvtop-Takte gesetzt (H13-Takte) — stirbt; Watchdog beendet den Hänger; DRAM persistiert

Phase A: prep, `tvtop_stock_clks.py --do`: pll-video1/pll-adc an (Lock ok), 16 Takte/Muxe auf Stock-Soll, bus-demod
Gate+Reset, tvdisp +0x88/+0x00 und tvfe 0x003003FF wie Legacy-tvtop → **Board lebt, GetSource RETURN**, Soll = Ist
(0 Abweichungen). Phase B: Watchdog einmalig scharf (16 s), `SetSource(4)` → Tod wie immer (ssh weg). **Der Watchdog
löste aus**: Board bootete ~16 s nach dem Scharfschalten von selbst (Uptime 407 s um 05:50:57 ⇒ Kernelstart ≈ 05:44:10).
Der SoC-Hänger lässt also die 24-MHz-Watchdog-Domäne und die Reset-Logik intakt — Steckdose ist nicht mehr nötig.
**Die Stock-Takte/Eltern/Resets sind nicht der fehlende Baustein** (als alleiniger Fix ausgeschlossen; Vorbedingung
bleibt sinnvoll).

**DRAM überlebt den Warm-Reset:** Kanarie 0x4d961000+0x99f000 nach dem Reboot geprüft — nur 3913 Wörter ab
**0x4e000000** geändert (`6f676f6c` = „logo", Kopf 0x1940a09d, 0x00240168 …: U-Boots Logo-Block beim Neustart),
alles andere intakt. ⇒ (1) der MIPS hat den Schwanz bis zum Hänger **nicht** beschrieben (H12 endgültig zu), (2)
post-mortem-Lesen ist möglich. Fehler im Ablauf: das Rettungs-FIT wurde erst nach 60 s eingespielt, U-Boot hatte das
normale FIT längst geholt → Kernel-Log-Ring des toten Laufs überschrieben. Lauf 69 tauscht das FIT vor dem
Scharfschalten und schreibt zusätzlich einen ARM-Herzschlag (`hb_dram.py`, CPU1, 1 kHz) nach 0x4d970000.

## KORREKTUR (07.09., 06:00) zu Läufen 66–69: Watchdog-Registerlayout war falsch — Resets nach 0,5 s, nicht Hänger

Der Herzschlag im DRAM (Lauf 69, `hb_dram.py`) zeigte: der ARM lief nach dem „Scharfschalten" nur 394 ms weiter,
und im post-mortem gelesenen Kernel-Log-Ring fehlen die CALL-Zeilen — der Reset kam **vor** dem SetSource-CALL.
Ursache im Stock-Treiber nachgelesen (vmlinux `sunxi_wdt_dt_ids` → `allwinner,sun50i-wdt`, regs `0c 10 14 04 03 01`;
`sunxi_wdt_set_timeout`/`_start`/`_ping` disassembliert): **CTRL 0x0C, CFG 0x10, MODE 0x14**, Intervall-Shift 4,
Timeout-Tabelle 1..16 s → 1,2,3,4,5,6,7(8 s),8(10),9(12),10(14),11(16), Schlüssel 0x16aa auf CFG/MODE, Ping-Wert
**0x14AF** auf CTRL (ohne Schlüssel). Ich hatte das sun6i-Layout (0x10/0x14/0x18) angenommen: mein „CFG"-Schreibzugriff
auf 0x14 war MODE mit Intervall 0 (= 0,5 s, EN) → Reset nach ~0,45 s. Damit sind folgende Deutungen **ungültig**:
„jeder weitere Schreibzugriff hängt den SoC" (waren die 0,5-s-Resets), „Watchdog beendet den SetSource-Hänger"
(Lauf 68: Reset vor dem CALL), „Stock-Takte getestet" (Lauf 68: SetSource kam nicht mehr zum Zug). **Gültig bleibt:**
DRAM überlebt den Warm-Reset (Kanarie), der MIPS schreibt den Schwanz nicht, post-mortem-Lesen funktioniert
(`pm_read.py`, Rettungs-FIT), Herzschlag-Methode funktioniert. Neu verifiziert (05:57): mit korrektem Layout hält
Pingen alle 3 s das Board 30 s am Leben, nach Stopp Reset nach ~14–16 s → `wdt_ping.py` (pingbar) / `wdt_arm.py`.
DT-Fix für unseren Kernel: eigener Compatible/Registersatz nötig (weder sun6i noch sun20i-d1 passen: Offsets 0x0C/0x10/0x14
mit Schlüssel).

## Lauf 70 (07.09., 06:00): POST MORTEM — der MIPS-Exception-Handler läuft Amok und überschreibt BL31 + Kernel

Aufbau: prep, `kmsg_udp` CPU1, elog-Tail CPU2, Herzschlag `hb_dram.py` CPU1 (1 kHz nach 0x4d970000), **pingbarer
Watchdog** (korrektes Layout, CPU0, 16 s), Rettungs-FIT vorab im TFTP, `SetSource(4)`. Tod wie immer; Watchdog-Reset;
Rettungskernel (0x50000000, alter Kernelbereich `no-map`) liest DRAM.

* **Herzschlag:** CPU1 lief nach dem Marker noch 1,93 s (Zähler 21515→23278), d. h. ≈0,4 s nach dem CALL — dann Stillstand.
* **Kernel-Log-Ring (`__log_buf` phys 0x4910cd38, statisch, 128 KiB):** enthält die Zeilen bis `ack_action` (wie UDP),
  keine weiteren Kernelmeldungen — **aber in jedem 32-Byte-Block liegen an +0x18/+0x1c die Wörter `0x8baa0000
  0x8b15b464`** (MIPS-Adressen!). Scan: dasselbe Muster in **0x48000018…0x491ffff8 lückenlos (589 822 Treffer, Schritt
  32)** und in **0x4000b078…0x400ffff8 (BL31-Bereich, direkt hinter dem beim Rettungs-Boot neu geladenen BL31-Abbild)**;
  nicht im Shmem, nicht im Schwanz (Kanarie intakt). Der DRAM ab Basis 0x40000000 wurde also mit 32-Byte-Rahmen
  gefüllt, **während der Kernel lief** (Kernel-Code-Bereich betroffen).
* **Deutung aus der Firmware:** 0x8b15b464 ist die Rücksprungadresse des `jal 0x8b15b2f8` in **F = 0x8b15b448**
  (`di; ehb; jal 0x8b15b2f8; lui s0,0x8baa (Delay-Slot); jal 0x8b15b3dc; printf…`). 0x8b15b2f8 sichert alle GPRs und
  CP0 Status/Cause/EPC/BadVAddr in den **Crash-Record 0x8ba99db4** (Magic `crashreg`), 0x8b15b3dc legt einen
  16-KiB-Notstack an → **F ist der Exception-Handler der Firmware.** Sein Rahmen ist 32 Byte (`sw s0,0x18(sp); sw
  ra,0x1c(sp)`), s0 = 0x8baa0000 (aus dem Delay-Slot), ra = 0x8b15b464 — exakt das DRAM-Muster. **Der Handler wird
  rekursiv immer wieder betreten**, jeder Eintritt schiebt 32 Byte; der Stack läuft von der Firmware abwärts durch das
  gesamte DRAM (≥ 0x49200000 → 0x40000000): Kernel-Code/-Daten und BL31 werden zerstört → stiller Tod (Translation
  Faults ohne Konsole, BL31 tot), auch ohne dass der ARM je ein Register anfasst.
* **Warum rekursiv:** in 0x8b15b2f8 steht `sw k1,0x8a(k0)` (0x8b15b390, Wort `af5b008a`; k0 = 0x8ba99db4 → Ziel
  0x8ba99e3e **unausgerichtet**) → Address-Error-Exception **im Handler selbst** → erneuter Handler-Eintritt → endlos.
  Firmware-Bug (Offset 0x8a statt 0x8c) — jede beliebige MIPS-Exception endet so als DRAM-Zerstörung.
* **Folge für die Ursachensuche:** Der Auslöser ist eine **Exception des MIPS während der Fensterprogrammierung**
  (Kandidat: Null-Handle `*(0x8b4a9da8)=0`, doku/72 04:10). Crash-Record nach dem Rettungs-Boot leider genullt
  (MIPS-Init). **Lauf 71 (Diagnose, kein Fix):** Wort 0x8b15b390 live `af5b008a → af5b008c`, damit der Handler nicht
  rekursiert; erwartet: ARM überlebt, Crash-Record zeigt EPC/BadVAddr/Register der **ersten** Exception.

Rohdaten: `pm-logbuf-run70.bin`, `pm-elog-run70.bin`, `pm-shmem-run70.bin`; Werkzeuge `pm_read.py`, `hb_dram.py`,
`mips_patch.py` (auch `crashrec`-Dekoder).

## Läufe 71/72 (07.09., 06:10–06:18): Handler-Patch bestätigt Mechanismus; Handler spinnt in Endlosschleife

**Lauf 71** (Diagnose-Patch 0x8b15b390 `af5b008a→af5b008c`, damit `sw k1,0x8c(k0)` ausgerichtet ist): DRAM **nicht**
mehr zerstört (Muster 0x8baa0000/0x8b15b464 im Kernel-Log-Abzug: **0 Treffer**, vorher lückenlos). Kanarie im Schwanz
intakt. **Der ARM hängt trotzdem** (ssh weg, Watchdog-Reset) — der Absturz kommt also **nicht allein** vom
DRAM-Fressen. Handler-Schwanz disassembliert: nach dem Loggen (`Exception happened at the address 0x%X code 0x%X`,
`Exception caused by %s`, Format bei 0x8b1fd148/17c) steht bei **0x8b15b4fc `beq zero,zero,0x8b15b4fc`** — eine
**Endlosschleife**. Der MIPS nimmt also **eine** Exception, sichert den Crash-Record (`crashreg` @0x8ba99db4:
Status +0x80, Cause +0x84, EPC +0x88, BadVAddr +0x8a→ nach Patch +0x8c), loggt, und dreht sich fest. Der MIPS
bedient danach die Message-Schleife nicht mehr (Lauf 72 kmsg: `TX … SENT-Bit STEHT NOCH … Firmware hat nicht
zugegriffen`). Warum der ARM/SoC dabei hängt (Bus/Interconnect durch den fehlgeschlagenen MIPS-Zugriff, oder der
gepatchte Spin), ist noch offen.

**Lauf 72** (Patch + Live-Auslesen des Crash-Records vom ARM): fehlgeschlagen — ssh brach ~17 s nach SetSource ab
(Watchdog-Reset), der ARM-Poller kam nicht an 0x4ba99db4 heran; der Rettungs-Boot überschreibt den Record
(U-Boot-Reload display.bin bis 0x4bf41000). Nebenbefund: elog zeigte diesmal einen vollständigen TFDManager-Attribut-
Dump (`Chip==>TV303`, `Platform==>PROJECTOR`), also lief die TFD/TSE-Fensterprogrammierung an.
**Lauf 73:** Crash-Record per 2-Wort-Patch (save_stack-Basis 0x8b15b2f8/2fc + F-s0 0x8b15b460/68) nach 0x8d970200
(= phys 0x4d970200, no-map-Schwanz, überlebt Reset + U-Boot) umleiten → post mortem lesen.

## Läufe 73–76 (07.09., 06:22–06:35): Mechanismus verifiziert, H8 widerlegt, Jagd auf den ersten Fault

* **Lauf 73** (Rettungskernel 0x50000000 + 5 Patches: b390 + Record→0x8d970200): SetSource(4) **überlebte** deutlich
  länger (elog bis `thal_display_source.cpp`: color_format YUV420_888, BT601, resolution 0×0), Record-Bereich unberührt.
* **Lauf 74** (Rettungskernel, **ohne** Patch): stirbt wie immer (elog Ende bei spinLock). ⇒ **H8 (Kollision
  Kernel@0x48000000) ist als alleiniger Fix WIDERLEGT** — der verschobene Kernel rettet nicht, weil der rekursive
  Handler-Stack ohnehin von 0x4ba99db4 abwärts auch BL31 (0x40000000) frisst.
* **Lauf 75/76** (mipsmem + Patches): Record blieb 0xDEAD, weil die Umleitung auf die **gecachte** MIPS-Adresse
  0x8d970200 zeigte — die Schreibzugriffe des hängenden MIPS erreichen das DRAM nicht. Korrektur: uncached-Alias
  (kseg1 = gecacht + 0x20000000, wie elog_uncached_patch) **0xad970200** (phys 0x4d970200). Lauf 76 leitet den
  Record dorthin um.
* **Wichtiger Zwischenschluss:** save_stack (0x8b15b2f8, Magic „crashreg" @0x8ba99db4) hat genau zwei Aufrufer,
  0x8b15b45c (Handler F 0x8b15b448) und 0x8b15b530 (zweiter Handler/Panik 0x8b15b504); beide enden nach dem Loggen
  in einer **Endlosschleife** (0x8b15b4fc bzw. 0x8b15b588). Beide sind Exception-/Panik-Handler. Der Tod ist also:
  **MIPS nimmt bei der Fensterprogrammierung eine Exception → Handler → save_stack → fehlausgerichteter `sw
  k1,0x8a(k0)` (0x8b15b390) → Address-Error IM Handler → Endlos-Rekursion → DRAM (BL31+Kernel) zerstört → stiller
  SoC-Tod.** Der b390-Patch (Diagnose) wandelt das in einen verzögerten Tod (kein DRAM-Fressen), beweist damit die
  Rekursion als Verstärker, lässt aber den **ersten** Fault übrig — dessen EPC/BadVAddr Lauf 76 fangen soll.
* **Nächster ARM-/Umgebungs-Fix:** die Bedingung herstellen, unter der der MIPS die erste Exception NICHT nimmt
  (fehlendes Objekt/Handle `*(0x8b4a9da8)=0` bzw. die fehlende Stock-Init der Fensterprogrammierung). Der
  Firmware-Handler-Bug (misaligned store) bleibt eine latente Gefahr und gehört an cstenger/Hersteller gemeldet.
