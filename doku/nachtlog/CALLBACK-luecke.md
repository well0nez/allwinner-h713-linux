# Die Callback-Lücke - verfolgt, gefunden, behoben (Unteragent, 07.09. vormittags)

**Kein Board angefasst:** kein `ssh`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`,
nichts nach `tftp/`. Kein `sudo`, kein `git commit`/`push`. **`patches/kernel/series` nicht angefasst**,
`build/build.sh` nicht aufgerufen, `0091`/`0093`/`0095`/`0096`/`0097` nicht angefasst. Der Prüfbau lief
in einer gekennzeichneten Wegwerf-Kopie (`/tmp/pruefbau-callback` **im Container** `h713-build`, also
außerhalb des Repos), am Ende gelöscht; die Baubäume unter `mainline/build/` wurden nur **gelesen**.

## Ergebnisdateien

| Datei | sha256 |
|---|---|
| `mainline/patches/kernel/0092-soc-sunxi-h713-cpu-comm-kernel-api.patch` | `4e660655138baa091212c86cd4cf4274b690bc218ca2a3f26f3ee116f74b4bde` |
| `mainline/patches/kernel/0094-media-sun50i-h713-hdmirx.patch` | `02f2255b3cc7f51fc2380009faaba6ebbc49cd8cc3acabd9a8d996510949d8ad` |

Beide in `diff -ruN`-Form mit Kopf wie `0049` und **genau einer** `Signed-off-by:`-Zeile.
Die Serie ist nachweislich weiter anwendbar (siehe §7).

---

## 1. Der verfolgte Weg - ein eingehender CALL, Schritt für Schritt

Gelesen wurde im **erzeugten Baum** (frischer Tarball + alle 71 Zeilen der `series` mit `patch -p1`,
wie `build/build.sh` Z. 143-155), nicht im Patch. Zeilennummern unten beziehen sich auf diesen Baum.

| # | Station | Datei | Zustand |
|---|---|---|---|
| 1 | Firmware entscheidet, den Rückruf zu machen | MIPS, `app_callback.cpp:66 NotifySignalChange` | **feuert** (elog Stufe 5, 07.09. 09:11) |
| 2 | Firmware sucht den Empfänger: `FindRoutine(comp_id)` in der Routinentabelle im Shmem | `cpu_comm_proto.c:231` (unsere Portierung derselben Vendor-Funktion) | **hier bricht es ab** |
| 3 | Firmware füllt die Nachricht, u. a. `+0x10` aus dem Tabelleneintrag `+4` | `cpu_comm_proto.c:447` | wird nie erreicht |
| 4 | Msgbox-Doorbell → `command_action(cpu, 0)` | `cpu_comm_proto.c:846` | wird nie erreicht |
| 5 | Zustellung an alle offenen `/dev/cpu_comm` | `cpu_comm_proto.c:942` | wird nie erreicht |
| 6 | Zustellung an Kernel-Handler | `cpu_comm_proto.c:950` | wird nie erreicht |
| 7 | Verzweigung `entry_cmd <= 4` / `> 4` | `cpu_comm_proto.c:952` | wird nie erreicht |

**Schritt 6 ist nachgeprüft und in Ordnung** - das war die erste Frage des Auftrags. Der Aufruf von
`cpu_comm_kernel_deliver()` steht in Zeile 950, eine Zeile hinter `cpu_comm_userspace_deliver()` (942)
und **zwei** Zeilen über der Verzweigung (952). Beide Nachrichtenklassen kommen also genau einmal
vorbei. Der Einhängepunkt ist nicht der Fehler.

**Die comp_ids stimmen ebenfalls.** `cpu_comm_name2id()` baut `"%s_%1x_%3.3x"`, der Userspace
`routine_name(base, target_cpu, 0)` = `"%s_%x_%03x"` - für `pid = 0` **byteweise dieselbe
Zeichenkette**. Nachgerechnet:

```
MipsHalCallback_SignalChange_0_000               -> 0x3e7fbc46
MipsHalCallback_HdmiHotPlugByPortHandler_0_000   -> 0x38d780e2
```

Genau diese beiden Werte meldet `0094` an (`CPU_COMM_CPU_ARM` = 0), und genau diese beiden stehen in
den Mitschnitten der Nacht als `comp_id=` der eingehenden CALLs. **Der Hash war nie der Fehler.**

---

## 2. Die Stelle des Verlusts - und der Beleg dafür

> `cpu_comm_register_callback()` trug den Handler **nur in eine treiberinterne Tabelle** ein.
> Niemand meldete die Routine in der **Routinentabelle im Shared Memory** an. Die Firmware sucht den
> Empfänger dort - findet nichts - und schickt die Nachricht gar nicht erst ab.

### Beleg A - der Riegel im Quelltext (`cpu_comm_proto.c:230`)

```c
if (FindRoutine(comp_id, routine_find_buf) != 0)
        return -3; /* ESRCH - routine not found */
```

`SendComm2CPUEx` bricht **vor** der Sequenz, vor dem FIFO, vor dem Doorbell ab. Unsere eigene
Fehlertabelle in `cpu_comm_api.c` sagt dasselbe: `case -3: /* FindRoutine() found no entry for this
comp_id */`. Das ist die ARM-Portierung derselben Vendor-Routine, die auf dem MIPS den Rückruf
absetzt.

### Beleg B - jeder je gemessene eingehende CALL trägt den Beweis mit sich

`SendComm2CPUEx` füllt das Feld `+0x10` der Nachricht ausschließlich im Zweig `routine_found`
(`cpu_comm_proto.c:447`):

```c
*(u32 *)(call_slot + 16) = *(u32 *)(routine_find_buf + 4);
```

`routine_find_buf + 4` ist das **Besitzerfeld des Tabelleneintrags** - bei einem per `INSTALL_RT`
angemeldeten ARM-Callback die `os.getpid()` des anmeldenden Prozesses
(`hdmi_seq.py`, `install()`: `struct.pack_into("<I", buf, 4, os.getpid())`).

Und genau das steht in allen sechs Mitschnitten, in denen je ein Callback ankam:

```
analyse/hdmi-seq/kmsg-udp-run81.txt
  10:45:59.209  RX-CALL from cpu=1 chan=0x0 comp_id=0x3e7fbc46 ... chan_pid=0x000001ad params=2
analyse/hdmi-seq/kmsg-udp-run59.txt
  01:57:52.373  RX-CALL from cpu=1 chan=0x0 comp_id=0x38d780e2 ... chan_pid=0x0000019b params=2
```

`0x1ad` = 429, `0x19b` = 411 - **Linux-pids**. Der MIPS kann diese Zahl nirgends anders herhaben als
aus einem Eintrag, den die ARM-Seite in die Shmem-Tabelle geschrieben hat. Er hat also
nachweislich nachgeschlagen. (Weiterer Mitschnitt: run80 `0x1c4`, run83 `0x1ae`, run84 `0x1b2`,
run85 `0x1b7`.)

### Beleg C - im Kernel-Weg macht das niemand

`cpu_comm_dev.c` sagt es im Probe selbst, als Entwurfsentscheidung:

> „Design now: MIPS owns the routing table. Userspace clients install their own proxy entries
> on-demand via ioctl INSTALL_RT (cpu_comm_ioctl → AddInRoutine)."

Im gesamten Baum ruft **nur** `IOCTL_INSTALL_RT` (`cpu_comm_dev.c:264`) `AddInRoutine()` auf.
`cpu_comm_register_callback()` schrieb ausschließlich in `cpu_comm_kcbs[]`.

### Beleg D - die Messung vom 09:11 lief ohne jeden Userspace-Eintrag

Die gültige Abnahmevorschrift von F (`F-korrektur.md` §4, Schritt 2) lautet ausdrücklich
„**KEIN prep-Skript, KEIN hdmi_seq.py**". In diesem Boot hat also niemand `INSTALL_RT` gefahren, die
Tabelle enthielt nur, was der MIPS selbst registriert. Damit passt der Befund lückenlos: Firmware
feuert (elog), Treiber zählt null (debugfs), und dazwischen fehlt der Eintrag.

Der HotPlug-Callback zählt aus demselben Grund null - es ist **ein** Fehler für beide, wie der
Messbefund es nahegelegt hat.

---

## 3. Warum der bisherige Gegenbeweis nicht trägt

`doku/83-cpu-comm-api.md` sagt unter „Muss die Routine im Shmem angemeldet sein?": *„Für den
Kernel-Handler **nein**"*, mit zwei Belegen. Beide halten nicht:

1. **„Der Zustellpunkt liegt oberhalb jeder Kanal- oder Routinensuche."** Stimmt - und sagt nichts
   zur Sache. Es ist eine Aussage über den **Empfangs**pfad auf dem ARM. Die Frage ist, ob der MIPS
   überhaupt **sendet**. Der Satz beantwortet die falsche Frage.

2. **„doku/72 Lauf 18 zeigt, dass der MIPS den `SignalChange`-CALL auch dann schickt, wenn
   `INSTALL_RT` unterdrückt wurde (`--no-callbacks`)."** Lauf 18 hat gar nichts von einem CALL
   gesehen. Beobachtet wurde nur, dass **der ARM trotzdem stirbt**. Dass daraus „der CALL kam an"
   folgte, hing vollständig an der damaligen Ursachenthese („der Tod kommt aus
   `comm_CallWorkAction`, das nur bei einem eingehenden CALL läuft"). **Lauf 21 hat genau diese
   These widerlegt** (doku/72: „~~ROOT CAUSE~~ WIDERLEGT"). Mit der These fällt der Schluss. Übrig
   bleibt ein Absturz ohne bekannte Ursache - kein Beleg für einen zugestellten Callback.

Das ist derselbe Fehlertyp wie der aus `F-abnahme-und-callback-luecke.md`: ein Kriterium, das nicht
scheitern konnte. Hier: ein Beleg, der nie ein Beleg war.

---

## 4. Die Änderung

### `0092` - `cpu_comm_register_callback()` meldet die Routine an

Die API nimmt jetzt den **Namen** statt der id:

```c
int cpu_comm_register_callback(const char *base_name, cpu_comm_cb_t fn, void *ctx);
int cpu_comm_unregister_callback(const char *base_name, cpu_comm_cb_t fn);
```

Das ist keine Bequemlichkeit: der Deskriptor **trägt den Namen** (Feld `+0x0c`, 64 Byte), und vom
Hash führt kein Weg zurück. Registrieren tut jetzt beides, in dieser Reihenfolge:

1. `AddInRoutine()` mit einem 96-Byte-Deskriptor - `+0 channel`, `+2 target_cpu = 0 (ARM)`,
   `+4 owner`, `+8 comp_id`, `+12 voller Name` (`…_0_000`, wie `INSTALL_RT` ihn schreibt),
   `+92 next = -1`. Schlägt das fehl, wird **kein** Handler eingetragen: ein Handler, der nie laufen
   kann, ist schlechter als ein Fehler.
2. `Comm_AddNewChannel()` für den MIPS-eingehenden Kanal, wie `IOCTL_INSTALL_RT` es tut.

Abmelden entfernt den Deskriptor wieder - **nur**, wenn er noch der von dieser API angelegte ist;
ein Daemon, der dieselbe Routine angemeldet hat, behält seinen Eintrag.

**Warum das Besitzerfeld `0` ist**, und warum das kein Zufallswert sein durfte - zwei Bedingungen
gleichzeitig:

* `cpu_comm_release()` gibt die pid des schließenden Prozesses an `RemovePidRoutines()`. Der Wert muss
  also einer sein, den **keine Aufgabe tragen kann**. pid 0 gehört dem Leerlauf-Task, der nie eine
  Datei öffnet.
* `Comm_Add2NewCallFifo()` prüft nach dem Kanalfund drei Felder gegen den Eintrag, und die erste
  Prüfung liest die **oberen 16 Bit** des Kanalschlüssels (`Comm_AddNewChannel()` legt den ganzen
  Schlüssel in ein Wort, `channel + 2` ist damit `key >> 16`) gegen das Kanalfeld der Nachricht.
  Das hält nur, solange der Schlüssel unter `0x10000` bleibt - bei einem pid-abgeleiteten Schlüssel
  also nur für pids unter 4096. Der Char-Device-Pfad lebt von diesem Zufall. Mit `owner = 0` ist der
  Schlüssel `1`, die oberen 16 Bit sind 0, und `1` ist ein Schlüssel, den `IOCTL_INSTALL_RT` gar
  nicht erzeugen kann (dessen ist `1 | pid << 4`, nie unter 17).

Ein Wert oberhalb `PID_MAX_LIMIT` - der erste Entwurf - erfüllt die erste Bedingung und **verletzt
die zweite**; er hätte je Callback eine `channel comp mismatch`-Fehlerzeile erzeugt. Gefunden beim
Nachlesen von `cpu_comm_channel.c:188`, nicht am Gerät.

### `0094` - meldet mit Namen an und schiebt die Probe auf

Die beiden Namen stehen als `H713_HDMIRX_CB_SIGNAL` / `H713_HDMIRX_CB_HOTPLUG` an einer Stelle statt
viermal ausgeschrieben. Neu ist außerdem: `-ENODEV` aus der Registrierung wird zu `-EPROBE_DEFER`.
Das ist eine **Folge** der Änderung - die Registrierung fasst jetzt das Shared Memory an und kann
deshalb aus demselben Grund scheitern wie die Init-Sequenz zwei Zeilen weiter unten: nichts ordnet
diese Probe gegen die des `cpu_comm`-Treibers.

### Kein Workaround

Kein Polling, keine Wiederholung, kein Timeout. Die Änderung setzt genau die zwei Schritte, die der
funktionierende Userspace-Weg auch macht, an die Stelle, an der sie fehlten.

---

## 5. Instrumentierung: `/sys/kernel/debug/cpu_comm/watch`

Lesen liefert jetzt:

```
rx_calls  12
unmatched 0 last 0x00000000
channel   0x00000001 registered
handlers  2
0x3e7fbc46      4 rt cpu=0 owner=0            MipsHalCallback_SignalChange
0x38d780e2      8 rt cpu=0 owner=0            MipsHalCallback_HdmiHotPlugByPortHandler
```

* **`rx_calls`** - jeder eingehende CALL, der `cpu_comm_kernel_deliver()` erreicht hat, **unabhängig
  davon, ob etwas registriert war**. Der frühere Code stieg vorher aus, wenn die Handlertabelle leer
  war; ein Messgerät, das erst funktioniert, wenn die Sache schon läuft, ist keins.
* **`unmatched … last`** - davon die, die kein Handler beansprucht hat, samt der id der letzten. Das
  ist der Unterschied zwischen „nichts kommt an" und „es kommt an und wir werfen es weg". Ein
  Ereigniszähler je Treiber kann die beiden nicht unterscheiden - genau daran hat diese Lücke eine
  Nacht gekostet.
* **`channel … registered|missing`** - der Schlüssel, unter dem `Comm_Add2NewCallFifo()` nachschlägt.
* **je Handler:** id, zugestellte Ereignisse, **und was die Shmem-Routinentabelle wirklich über die
  id sagt**. `rt none` ist genau der Zustand, in dem die Firmware den Empfänger nicht findet;
  `(foreign)` heißt: der Eintrag gehört jemand anderem (etwa einem `hdmi_seq.py`-Lauf).

Schreiben nimmt jetzt nur noch einen Namen (`echo MipsHalCallback_SignalChange > …/watch`,
`-Name` entfernt) - eine rohe id ließe sich nicht in einen Deskriptor zurückverwandeln.

---

## 6. Belegt / vermutet

**Belegt (aus Quelltext im erzeugten Baum und aus Mitschnitten am Gerät):**

* Der Kernel-Zustellpunkt liegt über der `<=4`/`>4`-Verzweigung und ist für beide Klassen genau
  einmal zuständig (`cpu_comm_proto.c:942/950/952`).
* Die angemeldeten comp_ids sind dieselben, die ankommen (`0x3e7fbc46`, `0x38d780e2`); der
  Namensaufbau von Kernel und Userspace ist für pid 0 identisch.
* `SendComm2CPUEx` bricht bei fehlgeschlagenem `FindRoutine` mit `-3` ab, bevor irgendetwas gesendet
  wird (`cpu_comm_proto.c:230`).
* Das Feld `+0x10` jeder eingehenden Nachricht stammt aus dem Routineneintrag `+4`
  (`cpu_comm_proto.c:447`), und in **allen** Mitschnitten steht dort eine ARM-Linux-pid.
* Vor dieser Änderung meldete auf dem Kernel-Weg **niemand** eine Routine an; nur `IOCTL_INSTALL_RT`
  ruft `AddInRoutine()`.
* Die 09:11-Messung lief ohne `hdmi_seq.py`, also ohne jeden `INSTALL_RT`.

**Vermutet (nicht in dieser Sitzung gemessen):**

* Dass die MIPS-Firmware zum Senden **dieselbe** Vendor-Routine benutzt, die wir als
  `SendComm2CPUEx` portiert haben. Das folgt aus der gemeinsamen `cpucomm`-Herkunft und aus Beleg B,
  ist aber in dieser Sitzung nicht disassembliert worden.
* Dass der Callback mit dem Eintrag ankommt. **Das entscheidet die Abnahme in §8** - und zwar in
  beide Richtungen, siehe dort.

**Ausgeschlossen ist ab jetzt durch Konstruktion:** dass ein ankommender CALL still im
Kernel-Zustellpunkt verlorengeht. `rx_calls` zählt vor jeder Zuordnung.

---

## 7. Prüfbau - **ausdrücklich ein Prüfbau, kein Serienartefakt**

Wegwerf-Kopie im Container `h713-build` unter `/tmp/pruefbau-callback` (nicht im Repo, nicht in
`mainline/build/`), am Ende gelöscht. Frischer Tarball aus `build/cache/linux-6.18.38.tar.xz`, alle
71 `series`-Zeilen mit `patch -s -p1` wie `build/build.sh` Z. 143-155, Board-defconfig,
`ARCH=arm64 LLVM=1`, clang 20.1.8.

| Prüfung | Ergebnis |
|---|---|
| `series` vollständig anwendbar, mit den neuen `0092`/`0094` | **71/71**, dieselben 17 `.orig`-Dateien wie mit dem Altstand (kein neuer Fuzz) |
| `make -j24 Image modules` | **rc=0**, keine Warnung, keine `undefined` |
| `make W=1` für `drivers/soc/sunxi/cpu_comm/` und `.../sun50i-h713-hdmirx/` | **eine** Warnung, unverändert Altbestand: `cpu_comm_rpc.c:256: variable 'prev_idx' set but not used` in `RemoveRoutine` - von mir nicht angefasst |
| `make dtbs` | rc=0, keine h713-Warnung |
| Symbole | `cpu_comm_call`, `cpu_comm_register_callback`, `cpu_comm_unregister_callback`, `cpu_comm_name2id` - alle `EXPORT_SYMBOL_GPL` in `Module.symvers` |
| Modulabhängigkeit | `sun50i-h713-hdmirx.ko`: `depends=hy310-cpu-comm,sun50i-h713-afbd,sun50i-h713-arisc` |

Artefakte des letzten Laufs (nur zum Vergleich, nicht aufbewahrt):

```
Image                    c29c86b6f4e246c2aead9b4bdc9b65ed57446ff7746538044a011f34a2d81137
hy310-cpu-comm.ko        53d9cdca9c162b4fa6b4735fd155d85d3075776c9eaa20572da2e5af618517ad
sun50i-h713-hdmirx.ko    2cf567ea7365f93c56cd853de85ba654612b4f7ad85862a829f3b8f55a66d89b
```

**Nicht gelaufen:** nichts davon war am Gerät. Der Bau beweist, dass es übersetzt und linkt, sonst
nichts.

---

## 8. Abnahmevorschrift (kopierbar, Hauptsitzung)

Sie macht **beide** Ausgänge sichtbar und stützt sich **nicht** auf `SignalChange: N mal` allein:
`N` steigt auch, wenn irgendein anderer Weg den Zähler bewegt, deshalb wird jede Aussage doppelt
belegt - einmal aus `cpu_comm/watch` (Zustellung), einmal aus dem elog (Firmware) - und vorher
wird geprüft, dass die Zähler **nicht** von beliebigem IPC-Verkehr wandern.

**Voraussetzungen:** Kernel mit der integrierten Serie inkl. der neuen `0092`/`0094`, Zuspieler
`192.168.8.162` wach auf 1080p60, Board-Sperre halten.

```bash
# --- 0. Kaltstart, danach KEIN prep-Skript und KEIN hdmi_seq.py ---------------
#     (hdmi_seq.py wuerde die Deskriptoren aus dem Userspace anlegen und damit
#      genau das verdecken, was hier geprueft wird)
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP, Nachtlog, nicht reparieren"; exit 1; }
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'cut -d" " -f1 /proc/uptime'          # < 60 = echter Kaltstart

# --- 1. Instrument zuerst: kann es einen Positivbefund ueberhaupt zeigen? -----
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch'
#  erwartet:
#    rx_calls  <N0>
#    unmatched <M0> last 0x........
#    channel   0x00000001 registered
#    handlers  2
#    0x3e7fbc46 <h0> rt cpu=0 owner=0   MipsHalCallback_SignalChange
#    0x38d780e2 <h1> rt cpu=0 owner=0   MipsHalCallback_HdmiHotPlugByPortHandler
#
#  DURCHFALL, und alles Weitere ist sinnlos, wenn:
#    * eine der beiden Zeilen "rt none" sagt  -> die Firmware findet den Empfaenger
#      nicht; die Anmeldung ist nicht angekommen (Fehler NICHT behoben),
#    * "channel 0x00000001 missing"           -> derselbe Fall eine Stufe spaeter,
#    * "handlers 0" oder die Datei fehlt      -> Treiber/Kernel ist nicht der neue.
#  "(foreign)" hinter owner ist KEIN Durchfall, heisst aber: es liegt ein fremder
#  Eintrag in der Tabelle (Rest eines hdmi_seq.py-Laufs) -- dann ist der Kaltstart
#  nicht sauber, Schritt 0 wiederholen.

# --- 2. MIPS-elog auf Stufe 5 und pruefen, dass ES etwas zeigen kann ----------
ssh root@192.168.8.141 'python3 - <<EOF
import mmap,os,struct
fd=os.open("/dev/mem",os.O_RDWR|os.O_SYNC)
m=mmap.mmap(fd,0x1000,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x4B48B000)
def r32(a): return struct.unpack_from("<I",m,a-0x4B48B000)[0]
def w32(a,v): struct.pack_into("<I",m,a-0x4B48B000,v)
w32(0x4B48BD9C,(r32(0x4B48BD9C)&0xffffff00)|5)
w32(0x4B48BE98,(r32(0x4B48BE98)&0xffffff00)|0)
print("level=%08x tabelle=%08x" % (r32(0x4B48BD9C), r32(0x4B48BE98)))
EOF'
ssh root@192.168.8.141 '[ -f /root/elog_tail.pid ] && kill $(cat /root/elog_tail.pid) 2>/dev/null; \
  nohup taskset -c 2 python3 /root/elog_tail.py --hb 200 > /root/elog_tail.out 2>&1 & echo $! > /root/elog_tail.pid'
sleep 2

# --- 3. FALSIFIZIERBARKEIT: ein RPC, der KEINEN Callback ausloesen darf -------
#     harmloser, unveraenderter Aufruf (dieselbe Positivkontrolle wie in K4)
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch > /tmp/watch.vor; \
  echo "Thal_Vp_SetBacklightLevel 100" > /sys/kernel/debug/cpu_comm/call; \
  cat /sys/kernel/debug/cpu_comm/call; sleep 2; \
  cat /sys/kernel/debug/cpu_comm/watch > /tmp/watch.nach; diff /tmp/watch.vor /tmp/watch.nach'
ssh root@192.168.8.141 'tail -20 /root/elog_tail.out'
#  ZWEI Bedingungen, beide noetig:
#   a) der elog zeigt Zeilen zu diesem RPC  -> das Instrument "elog" lebt (K4-Regel);
#      zeigt er nichts, hat die Firmware den Level ueberschrieben -> Schritt 2 wiederholen,
#      sonst sagt sein Schweigen spaeter NICHTS.
#   b) `diff` gibt GAR NICHTS aus -> rx_calls, unmatched und beide Trefferzaehler
#      haben sich NICHT bewegt. Damit ist belegt, dass rx_calls nicht einfach IPC-
#      Verkehr zaehlt (der RPC laeuft mit CALL/ACK/RETURN ueber dieselbe Msgbox,
#      nur eben in der Gegenrichtung). Bewegt sich hier etwas, ist der Zaehler als
#      Kriterium wertlos -> Nachtlog, STOPP.

# --- 4. Der eigentliche Reiz: Signalverlust und Rueckkehr ---------------------
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch > /tmp/watch.vor; \
  cat /sys/kernel/debug/sun50i-h713-hdmirx/status > /tmp/status.vor'
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off';  sleep 6
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 6
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch; echo ---; \
  cat /sys/kernel/debug/cpu_comm/watch > /tmp/watch.nach; diff /tmp/watch.vor /tmp/watch.nach; echo ---; \
  grep -E "SignalChange|HotPlug" /sys/kernel/debug/sun50i-h713-hdmirx/status; echo ---; \
  dmesg | grep -c "RX-CALL.*comp_id=0x3e7fbc46"; echo ---; \
  grep -E "CallbackOfSignalChange|NotifySignalChange" /root/elog_tail.out | tail -6'

# --- 5. Auswertung -----------------------------------------------------------
#  BESTANDEN, wenn ALLE vier zugleich gelten:
#   1. der elog zeigt CallbackOfSignalChange/NotifySignalChange (Firmware hat gefeuert),
#   2. `rx_calls` ist um >= 1 gestiegen,
#   3. die Zeile 0x3e7fbc46 hat um GENAU DENSELBEN Betrag zugelegt wie rx_calls,
#      und `unmatched` ist UNVERAENDERT,
#   4. `dmesg | grep -c "RX-CALL.*comp_id=0x3e7fbc46"` ist > 0 -- der unabhaengige
#      zweite Zeuge aus command_action, der nichts mit unseren Zaehlern zu tun hat.
#  Der Zaehler `SignalChange: N mal` aus dem hdmirx-status ist BESTAETIGUNG, kein
#  Kriterium: er darf nicht allein entscheiden.
#
#  DURCHGEFALLEN, und zwar unterscheidbar:
#   * elog feuert, `rx_calls` unveraendert, `dmesg`-Zaehler 0
#         -> der CALL ist nicht auf der Leitung. Die Anmeldung ist die Ursache
#            geblieben; `rt`-Spalte aus Schritt 1 sagt, ob der Eintrag ueberhaupt steht.
#   * `rx_calls` steigt, 0x3e7fbc46 bleibt stehen, `unmatched` steigt
#         -> es kommt etwas an, aber unter einer anderen id: `last 0x........`
#            nennt sie. Dann stimmt der Namenshash nicht, nicht die Anmeldung.
#   * elog schweigt
#         -> keine Aussage ueber den Zustellweg. Erst Schritt 2/3 wiederholen.

# --- 6. Zweiter Reiz: HotPlug ueber die ARISC (der andere Callback) -----------
ssh root@192.168.8.141 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; \
  sleep 1; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
sleep 3
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch'
#  erwartet: die Zeile 0x38d780e2 hat zugelegt. Damit ist belegt, dass es kein
#  Sonderweg fuer SignalChange ist, sondern der Zustellweg als Ganzes lebt.
```

**Aufräumen danach:** `kill $(cat /root/elog_tail.pid)`.

---

## 9. Nebenbefunde - gefunden, **nicht** behoben, mit Begründung

### 9.1 `RemovePidRoutines()` liest die pid am falschen Offset

`cpu_comm_rpc.c:438` prüft `*(u32 *)(entry + 28)`. Im Deskriptor steht die pid aber bei **`+4`**
(so schreibt `INSTALL_RT` sie, so liest `FindRoutineEx` sie, so nimmt `SendComm2CPUEx` sie);
`+28` liegt **mitten im Namensfeld** (`+12`…`+75`). Für
`MipsHalCallback_SignalChange_0_000` stehen dort die Bytes `"Sign"`. Die Aufräumung beim `close()`
räumt also **nichts** ab.

**Beleg am Gerät:** in `kmsg-udp-run81.txt` meldet `cpu_comm: MIPS-incoming channel reg pid=495`
um 10:45:57 an - und 1,5 s später trägt der eingehende CALL `chan_pid=0x1ad` (429), die pid eines
**früheren** Prozesses desselben Boots. Genau das Bild eines Eintrags, den `AddInRoutine()` als
„schon vorhanden" durchwinkt, weil ihn niemand entfernt hat. Dasselbe Muster in run59, 80, 83, 84, 85
(chan_pid stets kleiner als die zuletzt angemeldete pid).

**Warum nicht behoben:** die Reparatur ändert das Verhalten des heute funktionierenden
Char-Device-Pfades (Einträge würden ab dann beim `close()` tatsächlich verschwinden), und wie sich
`prep_after_boot.sh`/`hdmi_seq.py` mit dieser Änderung verhalten, hat niemand gemessen. Das gehört in
eine eigene, messbare Sitzung. Die Änderung hier ist davon **unabhängig**: das Besitzerfeld `0` kann
keine Aufgabe tragen, also nimmt `RemovePidRoutines()` unsere Einträge in keiner der beiden Fassungen
weg.

### 9.2 Die erste Kanalprüfung in `Comm_Add2NewCallFifo()` ist offsetabhängig richtig

`cpu_comm_channel.c:188` vergleicht `*(u16 *)(channel_ptr + 2)` mit dem Kanalfeld der Nachricht.
Weil `Comm_AddNewChannel()` den ganzen Schlüssel in ein Wort legt, liest das die **oberen 16 Bit des
Schlüssels**. Für pid-abgeleitete Schlüssel geht das nur bis pid 4095 gut. Nicht angefasst - es
funktioniert für den Bestand, und der richtige Ort dafür ist die Sitzung, die auch 9.1 macht. Für
diese Änderung war es der Grund, `owner = 0` zu wählen (§4).

### 9.3 `SignalChange` nimmt den FIFO-Pfad, nicht den Workqueue-Pfad

doku/72 sagt, `SignalChange` sei der `entry_cmd > 4`-Rückruf. In **allen** Mitschnitten
(run80/81/83/84/85) steht `chan=0x0` - auch für `comp_id=0x3e7fbc46`. Beide Callbacks nehmen also den
`<=4`-FIFO-Pfad. Für die Zustellung ist das gleichgültig (der Einhängepunkt liegt darüber), aber die
falsche Behauptung stand im Kommentarkopf von `0092` und ist dort korrigiert.

---

## 10. Was offen bleibt

* **Die Messung.** Der Beleg für „mit Eintrag kommt der Callback an" ist §8 und sonst nichts. Ich
  habe das Gerät nicht angefasst.
* **Ob der MIPS beim Senden wirklich unsere `SendComm2CPUEx`-Entsprechung fährt** - §6, „vermutet".
  Wenn §8 durchfällt mit „elog feuert, `rx_calls` 0, `rt cpu=0 owner=0"`, dann ist genau diese
  Annahme falsch, und der nächste Schritt ist die Disassembly des MIPS-Sendepfads, nicht ein weiterer
  Treiberumbau.
* **9.1 und 9.2** - echte Fehler im Bestand, absichtlich liegen gelassen.
* `RemoveRoutine()` verlässt in zwei Zweigen (`cpu_comm_rpc.c:289/298`) die Funktion mit gehaltenem
  `comm_SpinLock(2)`. Beide Zweige sind für ARM-Einträge (`cpu >= 0`, `next_idx` gültig) nicht
  erreichbar; angefasst habe ich es nicht.
