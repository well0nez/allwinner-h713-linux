# Paket C - `cpu_comm` bekommt eine In-Kernel-API

**Agent:** Unteragent C (offline). **Kein Board angefasst**: kein `ssh root@192.168.8.141`,
kein `ssh user@192.168.8.162`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`,
nichts nach `tftp/`. Kein `sudo`, kein `git commit`/`push`, kein `apt` im Container.
**`patches/kernel/series` nicht berührt**, `build/build.sh` nicht aufgerufen.
Uhrzeiten vom Arbeitsrechner (`date '+%H:%M'`), 06./07.09.2026.

Ergebnisdateien:

* `mainline/patches/kernel/0092-soc-sunxi-h713-cpu-comm-kernel-api.patch`
  (sha256 `e2d56b6c6b53882f67c16ac766be1bfd8e7cba8a5381c71426767a8c799c0879`)
* `doku/83-cpu-comm-api.md` - API, Argumentlayout, Callback-Semantik, Timeout,
  Verhältnis zum Char-Device-Pfad, Ergebnis zu Pflichtlisten-Punkt #6
* dieses Teillog

---

## 1. Ablauf

| Zeit | Schritt |
|---|---|
| 21:47 | Nachtplan 78 gelesen (§0 Regeln, §0b Umgebung, §1 gesicherter Stand, §3 „C" und „E", §7 Nachschlagetabelle), `nachtlog/00-koordination.md` (Nummernvertrag: 0092 = C) |
| 21:48-21:53 | Serienquelltext gelesen: `cpu_comm.h`, `_dev.c` (ioctls, Probe, `cpu_comm_init`), `_proto.c` (`SendCommLow`, `SendComm2CPUEx`, `SendAckLow`, `command_action`, `ack_action`, `queueAction`), `_rpc.c` (`CPUComm_CallEx`, `comm_CallWorkAction`), `_user.c` (Zustellung an die Char-Devices) |
| 21:53-21:56 | doku/65, 66, 67, 72 gelesen; `analyse/hdmi-seq/hdmi_seq.py` (CALL-Aufbau, `name2id`, Argumentlayout, Empfänger), `signal_info_buf.py`, `prep_after_boot.sh` Z. 2-3, `legacy/userspace/hy310-hdmird/src/main.cpp` (Callback-Behandlung, nur gelesen), `mainline/docs/reference/cpu-comm-call-table.md` |
| 21:55 | **Namens-Hash nachgerechnet** (siehe §3) - alle Einträge der Call-Tabelle stimmen; damit braucht der Treiber keine Tabelle |
| 21:56 | Vergleich `patches/kernel/0014` ⇄ Baubaum `d9f9ca8b…`: **zwei Handänderungen im Baum, die nicht im Patch stehen** (siehe §5) |
| 21:57-22:01 | Header, `cpu_comm_api.c`, Umbau von `CPUComm_CallEx`, Einhängepunkt in `command_action`, Mutex um `IOCTL_CALL`, Makefile/Kconfig |
| 22:01-22:05 | Prüfbau out-of-tree, Patch erzeugt, gegen frisch entpacktes 0014 mit `-F0` (kein Fuzz) geprüft |
| 22:05-22:10 | Pflichtlisten-Punkt #6 gegen Stock-Disassembly und Quelltext durchgearbeitet (§4) |
| 22:11 | Paket A hat inzwischen neu gebaut → Prüfbau gegen **A's Baum** `e62e8ee3…` wiederholt |
| 22:12 | Patch endgültig, Prüfbau grün, Doku geschrieben |

---

## 2. Prüfbau - Ergebnis

**Ausdrücklich ein Prüfbau, kein Endstand.** Out-of-tree, `M=`-Bau gegen einen
fertigen Serienbaum; der Originalbaum wurde nicht verändert (Quellen liegen in
`analyse/cpu-comm-api-pruefbau/`, das ist ein Arbeitsverzeichnis, kein Repo-Inhalt).
Aufnahme in `series` und Gesamtbau macht die Hauptsitzung.

```bash
# Quellen = 0014 + 0092, ausgepackt; Header über KCFLAGS erreichbar
podman exec h713-build bash -lc 'set -e
  T=/work/mainline/build/linux-6.18.38-e62e8ee3871f363bbe0ea792ad4bf8fac3c400ea663e1247405c1192123b42e0
  M=/work/analyse/cpu-comm-api-pruefbau
  make -C $T M=$M ARCH=arm64 LLVM=1 W=1 KCFLAGS=-I$M/include CONFIG_HY310_CPU_COMM=m -j8 modules'
```

Ergebnis:

* **`hy310-cpu-comm.ko` gebaut, AArch64**, sha256
  `33fcf15f0f715aad5eb084b50b8b47f9c40232f280f395f29591b7764377df38`.
* **Keine neue Warnung, auch mit `W=1`.** Gegengeprobt: derselbe Bau ohne 0092
  (nur 0014) liefert exakt dieselbe eine Warnung -
  `cpu_comm_rpc.c: variable 'prev_idx' set but not used` in `RemoveRoutine`,
  Altbestand, von mir nicht angefasst. `cpu_comm_api.o` selbst ist warnungsfrei.
* Die vier Symbole sind exportiert:
  `cpu_comm_call`, `cpu_comm_register_callback`, `cpu_comm_unregister_callback`,
  `cpu_comm_name2id` - alle `EXPORT_SYMBOL_GPL`.

**Patch-Prüfungen:**

| Ziel | Ergebnis |
|---|---|
| frisch entpacktes `0014` (Stand auf Platte) | `patch -p1 -F0` - **fehlerfrei, ohne Fuzz** |
| A's neuer Serienbaum `e62e8ee3…` | `patch -p1 -F0` - **fehlerfrei, ohne Fuzz** |
| alter Baubaum `d9f9ca8b…` (mit den Handänderungen vom 05.09.) | wendet sich ebenfalls an, mit Versatz und Fuzz 2 in einem Hunk |

Der Patch ist in `diff -ruN`-Form wie 0014/0037/0049, mit `From:`/`Subject:`-Kopf
und `Signed-off-by:`. **Nicht** in `series` eingetragen - das macht die Hauptsitzung.

Toolchain wie `build/build.sh` für den Kernel: `ARCH=arm64 LLVM=1`, clang/ld.lld
im Container `h713-build` (der Bau lief mit clang 20, weil A's Baum damit gebaut
wurde; mit clang 18 ebenfalls durchgelaufen, gleiches Ergebnis).

---

## 3. Was gebaut wurde, in drei Sätzen

`cpu_comm_call(comp_id, args, nargs, ret, nret, timeout_ms)` und
`cpu_comm_register_callback(comp_id, fn, ctx)` (dazu `unregister` und
`cpu_comm_name2id`) in `include/linux/soc/sunxi/h713-cpu-comm.h`, umgesetzt in
einer neuen Datei `cpu_comm_api.c`.

Der synchrone CALL benutzt **denselben** Protokollrumpf wie bisher: der Körper von
`CPUComm_CallEx` heißt jetzt `cpu_comm_call_ex(…, timeout_ms, strict)`,
`CPUComm_CallEx()` ist der Aufruf mit `(0, false)` - der Char-Device-Pfad verhält
sich unverändert - , `cpu_comm_call()` der mit `(timeout_ms, true)` und liefert bei
ausbleibendem RETURN `-ETIMEDOUT` statt stillschweigend Erfolg. Die
64-Bit-Ladeeigenheit auf 4-Byte-Grenze (doku/65-67) ist damit automatisch
mitgelöst: es wird der vorhandene wortweise Kopierer benutzt, kein zweiter gebaut.

Kernel-Handler werden in `command_action()` bedient, eine Zeile **hinter** der
bestehenden `cpu_comm_userspace_deliver()` - Reihenfolge dokumentiert, keine
Prioritäten, beide bekommen dasselbe Ereignis, keiner kann den anderen oder die
Quittung unterdrücken. Der Punkt liegt oberhalb der Verzweigung nach Kanalfeld
(`<=4` FIFO / `>4` Workqueue), also sieht ein Handler beide Klassen genau einmal.

**Namens-Hash statt Tabelle.** `cpu_comm_name2id("THal_Vp_SetSource", 1)` =
`0xEAF13DE5`. Der Hash ist `crc32_le(0x00123456, "<name>_<cpu>_<pid>")` - der
Kernel-Rohrechner passt exakt. Nachgerechnet gegen **alle** namentlichen Einträge
in `mainline/docs/reference/cpu-comm-call-table.md` (24/24, inklusive der beiden
mit dem Vendor-Tippfehler `Thal_`) und gegen die `KNOWN_IDS`/`CALLBACKS` aus
`hdmi_seq.py` (8/8 stichprobenweise, darunter `MipsHalCallback_SignalChange` =
`0x3E7FBC46`). **Die Aussage in `cpu-comm-call-table.md`, die IDs seien aus dem
Namen nicht ableitbar, ist überholt** - sie stimmt nur ohne die Vorbelegung und
ohne den `_<cpu>_<pid>`-Anhang. Die Seite gehört cstengers Baum; korrigiert habe
ich sie **nicht**, die Richtigstellung steht in doku/83 §1.

**Testkonsument im Treiber:** debugfs `/sys/kernel/debug/cpu_comm/{call,watch}`.
`echo 'THal_Vp_SetSource 3' > .../call` setzt den benannten Aufruf ab;
`echo 'MipsHalCallback_SignalChange@0' > .../watch` hängt einen eingebauten
Protokoll-Handler ein, der jedes Ereignis nach `dmesg` schreibt.

**Gegenseitiger Ausschluss:** `cpu_comm_call()` und `IOCTL_CALL` nehmen dieselbe
Mutex. Das ist nötig geworden, weil es ab jetzt zwei Aufrufer gibt und der
vorhandene Riegel in `SendComm2CPUEx` (Sequenz-Semaphore) nach 100 ms aufgibt und
**trotzdem weitermacht**. Der Empfangspfad nimmt die Mutex nicht.

---

## 4. Pflichtliste Punkt #6 - „ACK ohne Cache-Sync gegen Stock"

**Befund: kein fehlender Cache-Sync. Als gleichwertig zu Stock abgehakt, ohne
Codeänderung am ACK-Pfad.** Lange Fassung mit allen Belegen in doku/83 §5; hier
das Nötige zum Eintragen in `legacy/docs/known-issues.md` (die Datei fasse ich
auftragsgemäß nicht an - Paket J trägt ein).

**Kurzfassung für die Pflichtliste:**

> **Stand: Stock-gleichwertig, geschlossen.** Der Bit-2-Test bei `+105` findet
> statt - nicht im IRQ-Handler wie bei Stock, sondern eine Verzögerung später in
> `ack_action()`, an derselben Adresse mit demselben Bit. Zusammen verbrauchen
> beide Fassungen das Bit genau einmal; dass Stocks `ack_action` nicht noch
> einmal prüft, liegt daran, dass sein IRQ-Handler das Bit schon verbraucht hat.
> Ohne Entsprechung bleibt allein Stocks Zurücklese-Schleife, und die kann auf
> unserer Abbildung nichts leisten: `ShMemAddrBase` kommt aus `ioremap()`, auf
> arm64 `PROT_DEVICE_nGnRE` - ungecacht und non-Reordering, ein Lesen derselben
> Adresse nach dem Schreiben liefert den geschriebenen Wert, die Schleife endete
> im ersten Durchlauf. Dasselbe Argument steht schon im Baum als Begründung
> dafür, dass Session Ws `invalidate_kernel_vmap_range()` beim Wechsel von
> `vmap()` auf `ioremap()` entfallen ist. Der ACK-Pfad liest außerdem nur zwei
> Wörter aus dem Shared Memory: das Flag `+105` und die Semaphor-Referenz `+112`,
> und letztere hat der ARM selbst veröffentlicht (`SendCommLow(…, cc_ref(sem_ptr+16))`);
> die Firmware spiegelt sie nur zurück, ein veralteter Wert scheitert laut
> („ungueltige Semaphor-Referenz"). Das ist der Unterschied zum CALL/RETURN-Pfad,
> wo dieselbe Synchronisation eine 104-Byte-Nutzlast voller MIPS-Zeiger schützt
> und deshalb **erforderlich** ist (am 03.05. gemessen).
> **Belege:** `re/notes/HANDOFF-IPC-SESSION-20260503-W.md` (Stock-Disassembly
> `@0xcc94`, Offset-Tabelle je Nachrichtenart), doku/65 „Cache-Kohärenz",
> `cpu_comm_proto.c` (`cpu_comm_sync_mips_cache`, `ack_action`),
> `cpu_comm_dev.c` (ioremap-Kommentar), `arch/arm64/include/asm/io.h`.
> **Wieder aufmachen, wenn** die Shared-Region je cachefähig abgebildet wird -
> dann bekommt die Zurücklese-Schleife Bedeutung, und zwar in **beiden**
> Handlerfamilien.

**Zwei Dinge, die dabei nebenbei geklärt wurden:**

1. Der Kommentar vom 21.04. in `ack_action` vermutet einen „vorherigen
   Verbraucher", der bei Stock das Bit löscht. **Der vorherige Verbraucher ist
   Stocks IRQ-Handler.** Damit ist Stocks invertierte Prüfung logisch, und unsere
   nicht-invertierte ebenfalls - sie stehen nur an verschiedenen Stellen.
2. Die Reihenfolge (wir verzögern, bevor wir prüfen) könnte ein zweites ACT
   verlieren, wenn zwei ACKs derselben Richtung vor dem Work-Item einträfen. Das
   ist strukturell ausgeschlossen: `SendComm2CPUEx` hält die Sequenz-Semaphore
   vom Absenden bis zu dem `up()`, das `ack_action` macht - höchstens ein ACK je
   Richtung ist unterwegs. Der einzige Weg, diese Invariante zu brechen, war der
   100-ms-Bypass derselben Semaphore bei **zwei** Aufrufern; genau den schließt
   0092 mit `cpu_comm_call_mutex`.

**Falle für den, der Session Ws TODO doch noch abarbeiten will:**
`cpu_comm_sync_mips_cache(cpu, dir, 105)` in die ACK-Handler zu setzen, **ohne**
gleichzeitig die Prüfung aus `ack_action` zu entfernen, verbraucht das Bit
zweimal → `ack_action` sieht „no ACK pending" → weckt niemanden → **jeder** Aufruf
endet in „SendComm2CPUEx: ACK timeout". Beides müsste zugleich verschoben werden.
Ich habe das **nicht** gemacht, weil es einen heute funktionierenden Pfad umbaut
für einen auf dieser Abbildung nachweisbar nicht vorhandenen Gewinn.

---

## 5. Nebenbefund, der die Nacht betrifft: der `callwq`-Schutz fehlt im Serienpatch

Der Auftrag sagt, der `callwq`-Fix sei bereits im Serienbaum, und bittet, das im
Quelltext nachzuprüfen. **Nachgeprüft - und so stimmt es nicht mehr.**

| Ort | `callwq` vorhanden? |
|---|---|
| Baubaum vom 05.09. `linux-6.18.38-d9f9ca8b…` | **ja** (Modulparameter, `memset(routine_info, …)`, `is_mips_va`-Riegel) |
| `/root/hy310-cpu-comm-callwq-test.ko` am Board (Diagnose) | ja |
| **`patches/kernel/0014-soc-sunxi-add-cpu-comm-ipc.patch`** (Platte, 04.09. 20:41) | **nein** |
| **A's Nachtbau `linux-6.18.38-e62e8ee3…`** | **nein** - `cpu_comm_rpc.c` ist byte-gleich mit der 0014-Ausgabe |

Die Handänderungen vom 05.09. stehen also **nur im alten Baubaum**, nicht im
Patch. Ohne Gegenmaßnahme ist der Nachtkernel gegenüber dem, was am 06.09.
dreimal nach Kaltstart lief, **zurückgestuft**: `comm_CallWorkAction` springt
wieder auf einen Zeiger aus `routine_info + 88`, den `FindRoutineEx` nie füllt.
Betroffen ist genau der Pfad, den `MipsHalCallback_SignalChange` bei `SetSource`
nimmt (`entry_cmd > 4`, doku/72).

Zwei Dinge fehlen im Patch gegenüber dem alten Baubaum:

1. `cpu_comm_rpc.c`: `callwq_kernel_cb`-Parameter, `memset(routine_info, 0, …)`,
   `is_mips_va`-Riegel vor dem Zeigeraufruf.
2. `cpu_comm_proto.c`: die korrigierte `RX-CALL`-Druckzeile (die alte liest
   `+0x34` als „pid" und zeigt deshalb die Parameter 1, 2, **4**, 5 - genau der
   Druck, an dem die Callbacks abgelesen werden).

**Was 0092 daraus übernimmt und was nicht.** Punkt 1 ist mit 0092 gegenstandslos:
der Zeigeraufruf ist dort **ersatzlos entfernt**, weil der Kernel-Empfang jetzt
einen richtigen Mechanismus hat und in der Routinentabelle ohnehin nie ein
ARM-Kernel-Zeiger stand (doku/72; am Gerät steht dort `0x8b10abb8`, eine
MIPS-Adresse). Das Verhalten entspricht damit genau dem des Moduls, das auf dem
Tisch lief - dort war der Sprung per `callwq_kernel_cb=0` abgeschaltet. Der
Modulparameter selbst wird nicht gebraucht und kommt nicht mit; er war ein
Testschalter.

**Punkt 2 fasse ich nicht an** - das ist eine Diagnosezeile in fremdem
Zuständigkeitsbereich (0014 gehört nicht Paket C). Empfehlung an die
Hauptsitzung: die Druckzeile aus `d9f9ca8b…/drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c`
(Zeile ~907 ff.) in 0014 nachziehen, sonst ist der `RX-CALL`-Druck im Nachtkernel
um ein Feld verschoben. Der Unterschied ist mit

```bash
diff -u mainline/build/linux-6.18.38-e62e8ee3…/drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c \
        mainline/build/linux-6.18.38-d9f9ca8b…/drivers/soc/sunxi/cpu_comm/cpu_comm_proto.c
```

in einer Minute zu sehen (ein Hunk).

---

## 6. Abnahmevorschrift für die Hauptsitzung (kopierbar)

Voraussetzung: `0092` steht in `series`, `build/build.sh kernel` (bzw.
`KERNEL_CONFIG=netboot`) ist grün, FIT und Module sind ausgerollt.
`CONFIG_DEBUG_FS=y` ist im Board-defconfig vorhanden (Z. 233), also ist debugfs da.

**Vorbereitung am Board (einmal, vor dem Kaltstart-Lauf):** `prep_after_boot.sh`
lädt bevorzugt `/root/hy310-cpu-comm-callwq-test.ko` (Z. 8). Das ist das
**Diagnosemodul vom 06.09.** und enthält die neue API nicht. Also beiseitelegen:

```bash
ssh root@192.168.8.141 'mv -f /root/hy310-cpu-comm-callwq-test.ko /root/hy310-cpu-comm-callwq-test.ko.aus 2>/dev/null; ls -l /root/hy310-cpu-comm*.ko*'
```

### Ablauf

```bash
# 0) Kaltstart und Standardsequenz bis einschließlich Phase 3 (ohne SetSource)
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'bash /root/prep_after_boot.sh'

# 1) Kommt das Serienmodul mit der neuen API? (Beweis vor jeder Negativaussage)
ssh root@192.168.8.141 'grep -m1 hy310_cpu_comm /proc/modules; \
  grep -q debugfs /proc/mounts || mount -t debugfs none /sys/kernel/debug; \
  ls -l /sys/kernel/debug/cpu_comm/'
#   erwartet: Verzeichnis mit den Dateien "call" und "watch"

# 2) Userspace-Empfänger halten: meldet die zehn MipsHalCallback_* an,
#    hält /dev/cpu_comm offen und beweist zugleich, dass das Char-Device lebt.
#    PID merken -- NICHT spaeter mit pkill -f suchen, das Muster traefe die
#    eigene ssh-Shell (Memory pgrep-muster-trifft-eigene-shell).
ssh root@192.168.8.141 'nohup taskset -c 1 python3 /root/hdmi_seq.py listen --hold \
  > /root/C-listen.log 2>&1 < /dev/null & echo $! > /root/C-listen.pid; cat /root/C-listen.pid'
sleep 3
ssh root@192.168.8.141 'head -5 /root/C-listen.log'
#   erwartet: zwei Zeilen "Routine-Tabelle vorher/nachher: version=… count=…",
#   count nach der Anmeldung groesser (die zehn MipsHalCallback_*)

# 3) Kernel-Handler fuer SignalChange einhaengen
ssh root@192.168.8.141 'echo MipsHalCallback_SignalChange@0 > /sys/kernel/debug/cpu_comm/watch; \
  cat /sys/kernel/debug/cpu_comm/watch'
#   erwartet genau eine Zeile: 0x3e7fbc46      0 MipsHalCallback_SignalChange

# 4) DER PUNKT: SetSource(3) aus dem Kernel, ohne Userspace-Programm
ssh root@192.168.8.141 'echo "THal_Vp_SetSource 3" > /sys/kernel/debug/cpu_comm/call; \
  cat /sys/kernel/debug/cpu_comm/call'
#   erwartet: comp=0xeaf13de5 nargs=1 -> ok, N value(s) …
#     (N ist das, was die Firmware zurueckgibt -- entscheidend ist "ok", nicht N)
#   NICHT erwartet: "error -110" (das waere -ETIMEDOUT: kein RETURN)

sleep 5

# 5) Belege einsammeln
ssh root@192.168.8.141 'dmesg | grep -E "debugfs call|kernel callback|RX-CALL" | tail -20'
#   erwartet u. a.: cpu_comm: kernel callback comp=0x3e7fbc46 nargs=… args=[0x00000003 …]

ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch'
#   erwartet: Trefferzaehler in Spalte 2 > 0

ssh root@192.168.8.141 'grep -ai "SetActivePort" /root/elog_tail.out | tail -5'
#   erwartet: mindestens eine Zeile (elog-Beleg, dass die Firmware den Port umgeschaltet hat)

ssh root@192.168.8.141 'grep -c CALLBACK /root/C-listen.log'
#   erwartet: >= 1  -> /dev/cpu_comm hat DASSELBE Ereignis bekommen

ssh root@192.168.8.141 'uptime; grep -c "Ready: 1" /proc/cpu_comm/status'
#   erwartet: Board lebt, 4 Ready-Flags -> kein Absturz

# 6) Gegenprobe fuer den Ergebnispfad: ein Aufruf, der einen Wert zurueckgibt
ssh root@192.168.8.141 'echo THal_Vp_GetSource > /sys/kernel/debug/cpu_comm/call; cat /sys/kernel/debug/cpu_comm/call'
#   erwartet: comp=0x24efc7c9 nargs=0 -> ok, 1 value(s) 0x…
#     (der Wert dokumentiert die aktive Quelle; wichtig ist "1 value(s)", also
#      dass der wortweise Ergebnis-Kopierer laeuft -- doku/67, 64-Bit-Falle)

# 7) Aufraeumen
ssh root@192.168.8.141 'echo -MipsHalCallback_SignalChange@0 > /sys/kernel/debug/cpu_comm/watch'
ssh root@192.168.8.141 'kill "$(cat /root/C-listen.pid)" 2>/dev/null; sleep 1; tail -3 /root/C-listen.log'
```

### Bestanden, wenn

1. `/sys/kernel/debug/cpu_comm/call` **und** `watch` existieren (Modul mit API geladen).
2. Schritt 4 antwortet `ok` - kein `-110`, kein `-19`.
3. `dmesg` zeigt `cpu_comm: kernel callback comp=0x3e7fbc46` (SignalChange erreicht den
   **Kernel**-Handler), und `/root/C-listen.log` zeigt dieselbe Nachricht als `CALLBACK`
   (Char-Device läuft weiter, **beide** bekommen das Ereignis).
4. `elog_tail.out` enthält `SetActivePort`.
5. Das Board ist nach Schritt 5 noch da (`uptime`, SSH), keine Oops-Spur in `dmesg`.

### Wenn es schiefgeht

* **Schritt 1 findet kein `/sys/kernel/debug/cpu_comm`** → geladen ist das
  Diagnosemodul oder ein alter Kernel. Modulpfad und `modinfo` prüfen, nicht weiterfahren.
* **Schritt 4 gibt `-110` (`-ETIMEDOUT`)** → der Aufruf ging raus, der MIPS hat nicht
  geantwortet. Das ist ein **echter Befund**, keine API-Panne: vorher lieferte derselbe
  Fall stillschweigend „Erfolg mit 0 Werten". `dmesg | grep "no RETURN"` zeigt, ob die
  Wartung ablief oder die Return-FIFO leer war.
* **Schritt 4 gibt `-19` (`-ENODEV`)** → `FindRoutine` kennt die comp_id nicht: die
  Routinentabelle im Shmem ist leer (Phase 2 lief nicht) oder der MIPS ist im Reset.
* **Board hängt bei Schritt 4** → nicht warten, protokollieren, Kaltstart. Und §5 dieses
  Logs lesen: fehlt der `callwq`-Schutz **und** ist 0092 nicht drin, springt
  `comm_CallWorkAction` auf einen undefinierten Zeiger. Mit 0092 ist dieser Sprung weg.
* **Kein `kernel callback` in `dmesg`, aber `CALLBACK` im Listen-Log** → der Einhängepunkt
  wurde nicht erreicht; `dmesg | grep RX-CALL` zeigt, welche `comp_id` wirklich kam.
  Dann mit `echo 0x<id>@0 > .../watch` auf die tatsächliche ID hängen und wiederholen.

---

## 7. Board-Anfrage

Ein Slot, seriell, ~10 Minuten, **nach** der Abnahme von Paket A (neuer Kernel muss
booten) - im Nachtplan ist das Board-Slot 3.

| Was | Wert |
|---|---|
| Zweck | Abnahme Paket C: `THal_Vp_SetSource(3)` aus dem Kernel über debugfs, `SignalChange` im Kernel-Handler, `/dev/cpu_comm` weiterhin funktionsfähig |
| Voraussetzung | `0092` in `series`, Kernel + Module gebaut und ausgerollt; `/root/hy310-cpu-comm-callwq-test.ko` beiseitegelegt |
| Dauer | ein Kaltstart + Sequenz bis Phase 3 (~2 min) + sieben kurze Befehle |
| Risiko | `SetSource(3)` ist nach der Sequenz aus Nachtplan §1 dreimal gutgegangen; 0092 entfernt zusätzlich den undefinierten Zeigersprung, der bis zum 06.09. auf diesem Pfad lag. Kein neues Register wird geschrieben, keine INCAP, kein Descriptor. |
| Zusammen mit E | möglich - E braucht denselben Zustand (Prep + Phase 3), die Abnahme oben lässt sich unmittelbar davor fahren |
| Artefakte | `dmesg`-Auszug, `/root/C-listen.log`, `/root/elog_tail.out` nach `re/captures/weltneuheit/ours-20260907-nacht/C/` |

**Was ich nicht selbst prüfen konnte:** alles am Gerät. Insbesondere ob debugfs am
Board schon gemountet ist (Befehl ist oben enthalten), ob der MIPS auf einen
CALL aus Kernelkontext genauso antwortet wie auf einen aus dem ioctl (er sieht
dieselbe Nachricht in derselben FIFO - es gibt keinen Grund für einen
Unterschied, aber es ist nicht gemessen), und ob der `SignalChange`-Rückruf bei
diesem Lauf tatsächlich kommt (er kam am 05./06.09., doku/72 Lauf 17).

---

## 8. Für die Zusammenführung in `79-nachtlog-20260907.md`

* **C ist offline fertig.** Patch `0092`, Header, Doku `83`, Prüfbau grün
  (warnungsfrei, gegen A's Baum), Abnahme wartet auf einen Board-Slot.
* **Pflichtliste #6** ist beantwortet: kein fehlender Cache-Sync, mit Belegen
  abgehakt; Text zum Eintragen steht in §4 dieses Logs und ausführlich in
  doku/83 §5. **Ich habe `legacy/docs/known-issues.md` nicht angefasst** (Paket J).
* **Eine Sache braucht eine Entscheidung der Hauptsitzung:** §5 - der `callwq`-Schutz
  steht nicht in `0014` und fehlt daher in A's Nachtbau. 0092 macht den kritischen
  Teil gegenstandslos; die verschobene `RX-CALL`-Druckzeile bleibt offen.
* **Nichts angefasst**, was anderen gehört: `series`, `build.sh`, `0014`,
  `legacy/docs/known-issues.md`, `mainline/docs/reference/cpu-comm-call-table.md`,
  `tftp/`, das Board.
