# Callback-Fix: die Regression an E — erklärt und behoben (Unteragent, 07.09. mittags)

**Kein Board angefasst:** kein `ssh`, kein `sonoff_ctl`, kein `scp`, nichts nach `tftp/`, kein `sudo`,
kein `git commit`/`push`. **`patches/kernel/series` nicht angefasst**, `build/build.sh` nicht
aufgerufen. `0091`, `0093`, `0095`, `0096`, `0097` nicht angefasst. Der Prüfbau lief in einer
gekennzeichneten Wegwerf-Kopie (`/tmp/PRUEFBAU-callback-regression` **im Container** `h713-build`,
also außerhalb des Repos), am Ende gelöscht; `mainline/build/` wurde nur **gelesen**.

## Ergebnisdateien

| Datei | sha256 |
|---|---|
| `mainline/patches/kernel/0092-soc-sunxi-h713-cpu-comm-kernel-api.patch` | `24a879c96ffda3272f24efa58c0327f8116d900e1f513baddf4787eb80949226` |
| `mainline/patches/kernel/0094-media-sun50i-h713-hdmirx.patch` | `330ba208d58dbedbfc9f3ba1779b9d4f0bbcbf3ab6ec8246167bb03a3818f521` |

---

## 1. Kurzfassung

Der Callback-Fix aus `CALLBACK-luecke.md` **funktioniert**. Genau das ist die Ursache der Regression:
seit dem Fix stellt die Firmware während der Probe tatsächlich einen Rückruf zu, und der Treiber ist
in diesem Moment mitten in einer Kette von Fremdgesprächen mit **beiden** Coprozessoren. Wo dieser
eine Rückruf landet, entscheidet, was kaputtgeht — deshalb zwei Kaltstarts, zwei Fehlerbilder.

Die Korrektur ist eine Reihenfolge, keine Abschaltung: `0094` meldet die beiden Callbacks jetzt als
**letzten** Schritt der Probe an, nach `video_register_device()`, statt als ersten. Der Fix bleibt
vollständig scharf; nur das Zeitfenster, in dem er schaden konnte, verschwindet.

---

## 2. Was die Messung wirklich sagt

`cpu_comm/watch` war in **beiden** Läufen identisch:

```
rx_calls  1
unmatched 0 last 0x00000000
channel   0x00000001 registered
handlers  0
```

Das liest sich Zeile für Zeile so:

* **`rx_calls 1`** — genau **ein** MIPS→ARM-CALL hat `cpu_comm_kernel_deliver()` erreicht. Vor dem Fix
  war das nie mehr als 0 (das war die Lücke). Das ist die einzige neue Zutat im ganzen System.
* **`unmatched 0 last 0x00000000`** — dieser eine CALL wurde einem **registrierten Handler**
  zugestellt; er ist nicht ins Leere gelaufen. Zusammen mit `rx_calls 1` ist damit belegt: die
  Anmeldung wirkt, die Firmware findet den Empfänger, der Kernel-Handler läuft. **Ziel 2 des Fixes
  ist erreicht.**
* **`channel 0x00000001 registered`** — der Kanalschlüssel steht. Er wird bewusst nie wieder
  abgemeldet, deshalb überlebt er den gescheiterten Probe.
* **`handlers 0`** — konsistent mit dem Fehlschlag, wie im Auftrag vermutet, und **nachgeprüft**: der
  Probe scheitert → `err_callbacks` → `h713_hdmirx_unregister_callbacks()` → beide Slots
  `memset`-gelöscht, Zähler 0, keine Handler-Zeilen mehr. `rx_calls`/`unmatched` sind modulglobal und
  bleiben stehen. Kein Widerspruch, keine Spur.

Welcher der beiden Rückrufe es war, sagt `watch` nicht; die Zeile
`cpu_comm: RX-CALL ... comp_id=0x3e7fbc46|0x38d780e2` aus `command_action()` sagt es. Sie steht in
der Abnahme (§7) mit drin.

---

## 3. Warum ein einzelner Rückruf die Probe zerlegt

### 3.1 Das Fenster, und warum es so groß ist

Die Probe machte bis eben:

1. `h713_hdmirx_register_callbacks()` — **Deskriptor in die Routinentabelle**, ab hier darf der MIPS senden.
2. 22 synchrone RPCs. Schritt **1** ist `THal_Vp_RegisterSignalChangeCallback(11)`, Schritt **2**
   `THal_Vp_SetHDMIHotPlugByPortCallback(1)` — damit ist der **Sender** in der Firmware scharf.
3. `arisc_hdmi_edid_init()` — ResetEDID, HostHDMIMAP, EDID hoch, Rücklesen, Audio, +5 V,
   HPD low → 200 ms → HPD up. Zehn Sekunden Größenordnung, mit `mutex_lock(&a->lock)` und
   SRAM-Vorbelegungen mittendrin.

Zwischen Schritt 2 und dem Ende von 3 liegen 20 weitere RPCs **und** die komplette ARISC-Sequenz.
In genau diesem Fenster kann der eine Rückruf ankommen, auf dem `cpu_comm`-Empfangs-Workitem, parallel
zu allem. Der Treiber hält dort keine Ordnung — und kann sie auch nicht halten, weil die Zustellung
absichtlich nicht auf `cpu_comm_call_mutex` wartet (`cpu_comm.h`: „The receive path deliberately does
NOT take it").

Vor dem Fix war dieses Fenster **leer**: `SendComm2CPUEx` auf dem MIPS scheiterte an `FindRoutine`
mit `-3` und verwarf den Rückruf, bevor er auf der Leitung war. Genau in diesem Zustand sind A–E, G, H
abgenommen worden.

### 3.2 Lauf 1 (09:51) — `Schritt 15 THal_Vp_HDMI_SetPortMap (Stock-Session 27): -110`

`-110` ist `-ETIMEDOUT` aus `cpu_comm_call_ex()` im `strict`-Zweig: das Warteobjekt der Sitzung ist
in seinem Zeitbudget nicht geweckt worden, die RETURN kam nicht (oder nicht zuordenbar) an.

Der ausschlaggebende Umstand ist, **welcher** Schritt es war. `THal_Vp_HDMI_SetPortMap` steht dreimal
hintereinander in der Tabelle — Schritt 13 (Session 25, Para 3/0), Schritt 14 (Session 26, Para 4/1),
Schritt 15 (Session 27, Para 5/2). Dieselbe Routine, dieselbe Argumentform, gleiches Zeitbudget.
**Zwei gingen durch, der dritte nicht.** Ein Fehler im Aufruf selbst, im Namen, im Hash, in der
Argumentzahl oder im Zeitbudget ist damit ausgeschlossen: der hätte alle drei getroffen. Übrig bleibt
etwas, das zwischen 14 und 15 dazwischenkam — und das einzige Neue, was dazwischenkommen kann, ist der
eine eingehende CALL.

### 3.3 Lauf 2 (09:53) — `-EBUSY` aus der EDID/HPD-Sequenz

Hier lief die Kette durch (`Init-Sequenz vollstaendig (22 Aufrufe)`), der Rückruf landete also später —
in der ARISC-Sequenz. `last_command: portmap 0,1,2 rc=-16` sagt, wo genau: `arisc_hdmi_set_portmap()`.

In `0091` gibt es dort **zwei** `-EBUSY`-Quellen, und die Unterscheidung steht im dmesg, nicht im
debugfs:

* **Hotplug-Wächter** (`sun50i-h713-arisc.c`, vor `arisc_arm_portmap_probe()`):
  `„HostHDMIMAP: Hotplug-Zaehler Port %u steht auf %u -- ein Puls ist noch unterwegs …"`
* **TX-FIFO-Wächter** in `arisc_send()`:
  `„Msgbox user1 Port 0 wird nicht geleert -- Unterbefehl 0x0011 nicht gesendet"`

Beide passen zu „etwas hat den ARISC-Pfad zeitlich verschoben"; welche der beiden es war, ist aus dem
Auftragstext nicht entscheidbar und muss aus dem vollen dmesg des Laufs kommen. **Für den Fix ist es
egal** (§4), für die Nachbetrachtung nicht — deshalb steht die Zeile in der Abnahme.

### 3.4 Belegt / vermutet — ehrlich getrennt

**Belegt:**

* Der Fix wirkt: ein CALL zugestellt, einem Handler zugeordnet, Kanal steht (§2).
* Der zugestellte CALL ist die **einzige** neue Laufzeit-Zutat gegenüber dem Stand, in dem E durchprobte.
  Der `diff -ru` der `cpu_comm`- und `hdmirx`-Verzeichnisse zwischen `…e39777bf…` (gut) und
  `…c78adf61…` (kaputt) enthält sonst nur: Namens- statt id-API, die Instrumentierung in `watch`, und
  `-ENODEV → -EPROBE_DEFER`. `sun50i-h713-arisc.c` ist zwischen beiden Bäumen **byte-gleich** — die
  `0xff`-Vorbelegung aus `0091` war im guten Baum schon drin und scheidet als Ursache aus.
* Das Fenster ist groß und beginnt vor Schritt 1 der Init-Sequenz (§3.1).
* Zwei von drei identischen Aufrufen gingen durch, der dritte nicht (§3.2). Das ist ein Rennen, kein
  Konstruktionsfehler im Aufruf.

**Vermutet (nicht bewiesen):** der genaue Mechanismus **innerhalb** des Protokolls, mit dem der
eingehende CALL den ausgehenden RPC bzw. den ARISC-Pfad stört. Ein Kandidat, der ins Auge fällt und
den ich **nicht** verifizieren konnte, ohne fremden Code anzufassen: `command_action(1, 0)` (eingehender
CALL) und `ack_action(1, 0)` (das CALL_ACK unseres eigenen ausgehenden Rufs) arbeiten auf **derselben**
Share-Sequenz `getShareSeq(ARM, MIPS, 0)`; die CALL-Bearbeitung schreibt dort den Sequenzindex
(`share_seq_r + 16 = 20`) und schickt über `SendAckLow()` einen ACK auf der ARM→MIPS-Sequenz. Dieser
Weg hatte in dieser Portierung noch nie zwei gleichzeitige Nutzer, weil nie ein CALL hereinkam. Das ist
`0014`-Gebiet und bleibt offen; die Korrektur unten braucht die Antwort nicht.

---

## 4. Die Änderung

### `0094` — die Anmeldung wandert ans **Ende** der Probe

```
  … ioremap shm …
  Stage 3  h713_hdmirx_run_init_seq()        22 RPCs
  Stage 4  arisc_hdmi_edid_init()            EDID + HPD
           vb2_queue_init / v4l2_device_register / video_register_device()
+ Stage 5  h713_hdmirx_register_callbacks()  <-- hier, nicht mehr oben
           debugfs, platform_set_drvdata
```

Fehlerpfade entsprechend: `err_vdev` (neu, `vb2_video_unregister_device`) vor `err_v4l2`;
`err_callbacks` entfällt, weil vor Stage 5 nichts angemeldet ist.

**Warum das den Fix nicht entwertet:** die Firmware wird von Schritt 1/2 der Init-Sequenz scharf
gemacht und bleibt es. Fehlt nur der Deskriptor, verwirft ihr `SendComm2CPUEx` den Rückruf mit `-3` —
exakt der Zustand des guten Kernels. Sobald der Deskriptor da ist, fließen die Rückrufe. Der Fix ist
also nicht geparkt, sondern nur ein paar Mikrosekunden später scharf.

**Warum dabei nichts verlorengeht — und das ist kein Ermessen:** beide Handler enden in
`h713_hdmirx_src_change()`, das ein V4L2-Source-Change-Ereignis einreiht. V4L2-Ereignisse gehen an
**abonnierte Dateihandles**. Vor `video_register_device()` gibt es keinen Videoknoten, also kein
Handle, also kein Abonnement — jedes bis dahin eingereihte Ereignis wäre ohnehin verworfen worden
(deshalb steht die `video_is_registered()`-Sperre überhaupt drin). Aufgegeben wird real das Fenster
zwischen `video_register_device()` und der Anmeldung: wenige Mikrosekunden.

Weiter fällt `-ENODEV → -EPROBE_DEFER` an der Anmeldestelle weg: an diesem Punkt sind gerade 22
Aufrufe durch `cpu_comm` gelaufen, „`cpu_comm` ist noch nicht gebunden" kann es dort nicht mehr
bedeuten. Die Verschiebung ist also für `-EPROBE_DEFER` an `run_init_seq()`/`edid_init()` gebunden,
wo sie hingehört.

### `0092` — die Regel steht jetzt da, wo der nächste Aufrufer sie liest

1. Header `<linux/soc/sunxi/h713-cpu-comm.h>` und Dateikopf `cpu_comm_api.c`: **Anmelden ist ein Akt
   mit sofortiger Wirkung auf dem anderen Prozessor.** Der Deskriptor ist es, der den Sender scharf
   macht; der erste Aufruf kann kommen, sobald `cpu_comm_register_callback()` zurückkehrt — auf dem
   Empfangs-Workitem, parallel zum Aufrufer. Also anmelden, **wenn man gerufen werden kann**, nicht am
   Anfang einer Probe, die danach eine Kette von Fremdgesprächen führt. Mit der Fundstelle: genau das
   hat die Probe am 07.09. an zwei verschiedenen Stellen zerlegt.
2. `cpu_comm_remove_routine()` prüft jetzt **zusätzlich** das `cpu`-Feld des gefundenen Eintrags.
   Grund: `RemoveRoutine()` (`cpu_comm_rpc.c`) hat **zwei** Rückgabepfade, die die
   **Hardware-Spinlock 2 nicht freigeben** — `next_idx > RT_MAX_INDEX` und `entry+2 > 1`. `0092` ist
   der erste Aufrufer dieser Funktion aus dem Kernel; bliebe das erreichbar, könnte ein
   fehlgeschlagener Abbau die Routinentabelle für den Coprozessor **und** für `IOCTL_INSTALL_RT`
   dauerhaft verklemmen. Beide Pfade sind jetzt hier ausgeschlossen statt dort repariert
   (`cpu_comm_rpc.c` gehört zum Grundport `0014`, nicht zu `0092`):
   * die Kette hat `FindRoutineEx()` unmittelbar davor bis zum selben Eintrag durchlaufen, und die
     Funktion bricht bei einem Glied über `RT_MAX_INDEX` ab, **bevor** sie ihm folgt — alle Glieder
     sind also im Bereich;
   * das `cpu`-Feld kommt aus derselben Suche zurück und wird geprüft.

Kein Retry, kein längeres Zeitbudget, kein Polling, kein toter Schalter.

---

## 5. Was **nicht** die Ursache war — die drei Auffälligkeiten aus dem Auftrag

### (2) `portmap: 16,32,48` — kein Byteversatz, sondern der unberührte Einschaltwert

`arisc_hdmi_set_portmap()` gab `-EBUSY` zurück, **bevor** die Karte geschrieben werden konnte:

* Beim Hotplug-Wächter (`goto out`) wird gar nichts angefasst.
* Beim TX-FIFO-Wächter hat `arisc_arm_portmap_probe()` `+2`/`+3` mit `0xff` vorbelegt, und
  `arisc_restore_portmap()` schreibt exakt die vorher gelesenen Bytes zurück — byteweise symmetrisch,
  kein Versatz möglich.

`16,32,48` ist also **das, was vor dem ersten `HostHDMIMAP` in den Sätzen steht**. Dass dort nach einem
erfolgreichen Lauf `0,1,2` steht, ist kein Widerspruch, sondern derselbe Befund von der anderen Seite:
`0,1,2` ist die **vom Handler geschriebene** Karte, `16,32,48` die **vom Firmware-Init hinterlassene**.

**Ausgeschlossen ist eine Kollision mit meinem Kanal-/Besitzerfeld-Schema, und zwar durch die Adressen:**
die Portmap-Sätze liegen in **SRAM A2** (ARM-Fenster `0x00100000 + 0x17248`), Deskriptor, Besitzerfeld
und Kanalpool von `0092` liegen in der `cpu_comm`-DRAM-Region (`0x4E300000`, Routinentabelle bei
`+0x75C0`) bzw. in kerneleigenem Speicher (`pcpu_comm_dev + 0x30`, **nicht** im Shared Memory). Es gibt
kein gemeinsames Byte. Die `0xff`-Vorbelegung aus `0091` und mein Schema können einander nicht sehen.

**Befund für den Besitzer von `0091`, nicht von mir zu ändern:** der Kommentar über `SRAM_PORTMAP`
sagt, die ROM-Tabelle `01 10 00 01 00 | 02 20 01 02 01 | 04 30 02 04 02` lasse die Firmware mit
Pin `0,1,2` in Byte `+2` starten, und leitet daraus ab, eine Prüfung auf `0,1,2` könne „nicht
scheitern". Die Messung sagt etwas anderes: frisch steht in `+2` `0x10, 0x20, 0x30` — das **Tag-Byte
bei `+1`** jedes ROM-Satzes. Entweder kopiert `0x11e88` `ROM[k] → SRAM[k+1]`, oder die Satzgrenze im
ROM liegt ein Byte früher als angenommen. **Die Logik von `0091` ändert das nicht** — im Gegenteil, die
`0xff`-Vorbelegung macht die Prüfung unabhängig davon richtig, und die Sorge „`0,1,2` steht schon da"
trifft beim Kaltstart gar nicht zu. Zu korrigieren ist der **Kommentar** (`SRAM_PORTMAP` und die
`portmap:`-Zeile in `h713_arisc_status_show`, die „0,1,2 ist auch der ROM-Zustand" behauptet).
Nebenbei: damit wird `portmap:` sogar ein *besseres* Anzeigegerät — `16,32,48` heißt eindeutig
„HostHDMIMAP hat nie geschrieben".

### (3) `-EBUSY` — der Wächter feuert nicht grundlos, er feuert zu spät im Ablauf

Der Wächter selbst ist in Ordnung: er lehnt ab, solange ein Puls unterwegs ist. Was ihn getroffen hat,
ist die Verschiebung der ARISC-Sequenz durch den dazwischengekommenen Rückruf (§3.3). **Kein Eingriff
in `0091` nötig oder empfohlen** — außer der Kommentarkorrektur aus (2). Sollte die Abnahme zeigen,
dass es der **TX-FIFO**-Wächter war und nicht der Hotplug-Zähler, ändert das an der Korrektur nichts,
wohl aber an der Nachbetrachtung; deshalb steht die dmesg-Zeile in §7 Schritt 4.

### (1) Zwei Kaltstarts, zwei Fehler — genau das erwartet man hier

Ein Rennen mit einem einzigen Ereignis und einem Fenster von mehreren Sekunden. Fällt das Ereignis in
die RPC-Kette, stirbt ein RPC (`-110`); fällt es in die ARISC-Sequenz, stirbt die (`-16`). Eine
Erklärung, die nur eines der beiden Bilder trägt, wäre schon deshalb falsch. Die Korrektur nimmt dem
Rennen den einzigen Teilnehmer, den es neu bekommen hat.

---

## 6. Prüfbau — **ausdrücklich ein Prüfbau, kein Serienartefakt**

Wegwerf-Kopie im Container `h713-build` unter `/tmp/PRUEFBAU-callback-regression` (nicht im Repo, nicht
in `mainline/build/`), am Ende gelöscht. Frischer Tarball aus `build/cache/linux-6.18.38.tar.xz`, alle
71 `series`-Zeilen mit `patch -s -p1`, Board-defconfig, `ARCH=arm64 LLVM=1`, clang 20.1.8.

| Prüfung | Ergebnis |
|---|---|
| `series` vollständig anwendbar mit den neuen `0092`/`0094` | **71/71**, 0 `.rej`, dieselben 17 `.orig` wie zuvor (kein neuer Fuzz) |
| `make -j24 Image modules` | **rc=0** |
| `make W=1` für `drivers/soc/sunxi/cpu_comm/` und `.../sun50i-h713-hdmirx/` | **eine** Warnung, unverändert Altbestand: `cpu_comm_rpc.c:256: variable 'prev_idx' set but not used` in `RemoveRoutine` — nicht angefasst |
| `make dtbs` | rc=0, keine h713-Warnung |
| Symbole | `cpu_comm_call`, `cpu_comm_register_callback`, `cpu_comm_unregister_callback`, `cpu_comm_name2id` alle `EXPORT_SYMBOL_GPL` in `Module.symvers` |
| Modulabhängigkeit | `sun50i-h713-hdmirx.ko`: `depends=hy310-cpu-comm,sun50i-h713-afbd,sun50i-h713-arisc` |

Artefakte des Prüfbaus (nur zum Vergleich, nicht aufbewahrt):

```
Image                    20d217aedebaf128a124c2a3b0bba2e5c531c2dda5577de28dd1f62a57b25a81
hy310-cpu-comm.ko        605cc36ed75626207c4cc980a57da1ed0692942419e5f7d0e3fb635227fa9a5f
sun50i-h713-hdmirx.ko    ac34201099c68e729c65021437d60ae6c31d6075031825a2ba5382106301d163
```

**Nicht gelaufen:** nichts davon war am Gerät.

---

## 7. Abnahmevorschrift (kopierbar, Hauptsitzung)

Sie prüft **beide** Ziele in einem Durchgang und in dieser Reihenfolge: erst dass E wieder probt, dann
dass der Callback ankommt. Schritt 2 ist der Ersatz für die alte Positivkontrolle: er belegt, dass die
Probe jetzt **ohne** eingehenden CALL abläuft — das ist die eigentliche Aussage der Korrektur und
zugleich ihre Falsifizierbarkeit.

**Voraussetzungen:** Kernel mit der integrierten Serie inkl. der neuen `0092`/`0094`, Zuspieler
`192.168.8.162` wach auf 1080p60, Board-Sperre halten.

```bash
# --- 0. Kaltstart, danach KEIN prep-Skript und KEIN hdmi_seq.py ---------------
#     (hdmi_seq.py legt die Deskriptoren aus dem Userspace an und verdeckt genau das,
#      was hier geprueft wird)
ss -ulnp | grep -w :69 || { echo "TFTP laeuft nicht -- STOPP, Nachtlog, nicht reparieren"; exit 1; }
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done
ssh root@192.168.8.141 'cut -d" " -f1 /proc/uptime'          # < 60 = echter Kaltstart

# --- 1. ZIEL 1: E probt durch -------------------------------------------------
ssh root@192.168.8.141 'ls -l /dev/video1; \
  dmesg | grep -E "sun50i-h713-hdmirx|hdmi-rx" | tail -20'
#  BESTANDEN, wenn ALLE drei zugleich:
#    * /dev/video1 existiert,
#    * "Init-Sequenz vollstaendig (22 Aufrufe)",
#    * "EDID/HPD-Sequenz auf Port 0 abgeschlossen" und danach
#      "/dev/video1, Slot-Quelle: ..." -- KEIN "probe with driver ... failed".
#  DURCHGEFALLEN mit -110 an irgendeinem Schritt oder -16 aus der EDID/HPD-Sequenz
#    -> weiter bei Schritt 2, der sagt, ob es noch am Callback liegt.

# --- 2. Die Kernaussage der Korrektur: waehrend der Probe kam KEIN CALL --------
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch'
#  erwartet, direkt nach dem Boot und vor jedem Signalreiz:
#    rx_calls  0                 <-- DAS ist der Punkt
#    unmatched 0 last 0x00000000
#    channel   0x00000001 registered
#    handlers  2
#    0x3e7fbc46      0 rt cpu=0 owner=0   MipsHalCallback_SignalChange
#    0x38d780e2      0 rt cpu=0 owner=0   MipsHalCallback_HdmiHotPlugByPortHandler
#
#  Lesehilfe:
#   * rx_calls 0 + handlers 2 + zweimal "rt cpu=0 owner=0"
#         -> Probe lief ungestoert durch, Deskriptoren stehen, Fix ist scharf. Weiter.
#   * "rt none" bei einer der beiden Zeilen
#         -> die Anmeldung ist nicht angekommen; Fix waere nicht mehr scharf. STOPP.
#   * "handlers 0" bei bestandenem Schritt 1
#         -> Widerspruch (die Anmeldung ist der letzte Probe-Schritt). Nachtlog, STOPP.
#   * rx_calls > 0 UND Schritt 1 durchgefallen
#         -> es kommt weiterhin waehrend der Probe etwas an: die Verschiebung hat nicht
#            gegriffen, Nachtlog. rx_calls > 0 bei bestandenem Schritt 1 ist dagegen
#            unkritisch (der Reiz kann vom Zuspieler selbst gekommen sein).
#   * "(foreign)" hinter owner -> Kaltstart war nicht sauber, Schritt 0 wiederholen.

# --- 3. ZIEL 2: der Callback kommt an ----------------------------------------
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
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch > /tmp/watch.vor'
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --off';  sleep 6
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output HDMI-2 --auto'; sleep 6
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch; echo ---; \
  cat /sys/kernel/debug/cpu_comm/watch > /tmp/watch.nach; diff /tmp/watch.vor /tmp/watch.nach; echo ---; \
  dmesg | grep -E "RX-CALL.*comp_id=0x(3e7fbc46|38d780e2)" | tail -5; echo ---; \
  grep -E "CallbackOfSignalChange|NotifySignalChange" /root/elog_tail.out | tail -6'
#  BESTANDEN, wenn ALLE vier zugleich:
#   1. der elog zeigt CallbackOfSignalChange/NotifySignalChange (Firmware hat gefeuert),
#   2. rx_calls ist um >= 1 gestiegen,
#   3. die Zeile 0x3e7fbc46 hat um GENAU DENSELBEN Betrag zugelegt, unmatched unveraendert,
#   4. die dmesg-Zeile "RX-CALL ... comp_id=0x3e7fbc46" ist da -- der unabhaengige
#      zweite Zeuge aus command_action.
#  Der Zaehler "SignalChange: N mal" aus dem hdmirx-status ist Bestaetigung, kein Kriterium.

# --- 4. Nachbetrachtung: welcher der beiden -EBUSY-Waechter war es am 07.09.? --
#     (nur fuer die Akten; nicht Teil der Abnahme)
ssh root@192.168.8.141 'dmesg | grep -E "HostHDMIMAP: Hotplug-Zaehler|Msgbox user1 Port 0 wird nicht geleert"'
ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status | grep -E "portmap|hpd_counter|last_command"'
#  Nach einer erfolgreichen Sequenz muss "portmap: 0,1,2" dastehen. "16,32,48" heisst
#  eindeutig: HostHDMIMAP hat in diesem Boot nie geschrieben (siehe Nachtlog §5).

# --- 5. Zweiter Reiz: HotPlug ueber die ARISC (der andere Callback) -----------
ssh root@192.168.8.141 'cd /root; python3 arisc_hdmi.py --no-probe raw --sub-cmd 0x0211 --arg1 0 --arg2 2 --settle 0.6; \
  sleep 1; python3 arisc_hdmi.py --no-probe hotplug --port 0 --value 1 --settle 1.0'
sleep 3
ssh root@192.168.8.141 'cat /sys/kernel/debug/cpu_comm/watch'
#  erwartet: die Zeile 0x38d780e2 hat zugelegt -- der Zustellweg lebt als Ganzes,
#  nicht nur fuer SignalChange.
```

**Aufräumen danach:** `kill $(cat /root/elog_tail.pid)`.

---

## 8. Offen

* Der Mechanismus **innerhalb** des Protokolls, mit dem ein eingehender CALL einen laufenden
  ausgehenden RPC bzw. den ARISC-Pfad stört (§3.4). Kandidat: gemeinsame Share-Sequenz von
  `command_action(1,0)` und `ack_action(1,0)` plus `SendAckLow()` auf der ARM→MIPS-Sequenz. Gebiet von
  `0014`; für die Korrektur nicht nötig, für einen Empfangsweg, der im Betrieb belastbar sein soll,
  schon.
* `RemoveRoutine()` (`cpu_comm_rpc.c`, `0014`) gibt auf zwei Pfaden die HW-Spinlock 2 nicht frei und
  relinkt die Hash-Kette nicht (`prev_idx set but not used` — genau die `W=1`-Warnung). `0092` umgeht
  beides jetzt, repariert es aber nicht. Gehört jemandem, der `0014` anfassen darf.
* Kommentarkorrektur in `0091` (§5, Auffälligkeit 2) — gehört dem Besitzer von `0091`.
* Ob am 07.09. der Hotplug- oder der TX-FIFO-Wächter das `-EBUSY` geliefert hat (§7 Schritt 4).
