# B - Der Wächter, der nichts bewachte: die Portmap-Prüfung falsifizierbar machen

Agent: Paket B, Teilauftrag „mach die Prüfung falsifizierbar". **Board nicht angefasst** -
kein `ssh`, kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts nach
`tftp/`. Kein `sudo`, kein `git`. Geändert: `mainline/patches/kernel/0091-...patch` und
`doku/82-arisc-treiber.md`. `patches/kernel/series` und `build/build.sh` unberührt;
Prüfbau in einer gekennzeichneten Kopie, danach gelöscht. `userspace/hy310-tv/` nicht
angefasst.

---

## 0. Die Kurzfassung

**`arisc_wait_portmap()` wartete darauf, dass die Portmap `0,1,2` trägt - und `0,1,2`
steht nach jedem Firmware-Start schon da. Die Funktion konnte nicht scheitern und hat
deshalb nichts bewiesen.**

Der Treiber belegt jetzt Byte +2 und +3 aller drei Sätze **vor** dem Senden mit `0xff`,
liest diese Vorbelegung zurück und sendet gar nicht erst, wenn sie nicht landet. Ein
Treffer ist damit nur noch durch einen Schreibzugriff der Firmware erreichbar; ein Ablauf
ist ein echter Fehler. Scheitert die Prüfung, werden die Sätze auf den vorgefundenen Stand
zurückgesetzt.

Die Analyse aus `B-hpd-luecke.md` (HostHDMIMAP liest den Pumpen-Puffer nach dem `memset`
noch einmal, der Treiber überschreibt ihn ~1 ms später) steht unverändert. Nur ihre
Gegenprüfung war blind.

---

## 1. Der Befund, nachgerechnet

`0x11e88` - die Init-Routine, die die Firmware **einmal** aus `0x10f0c` ruft - kopiert die
ROM-Tabelle `0x15edc` in die Portmap-Sätze ab `0x17248` (`0x11ef8..0x11f3c`: Byte 0…4,
Schrittweite 8, Abbruch bei Quelle `0x15ef4`). Die Tabelle selbst, wortweise aus
`analyse/arisc-frame/full-disasm.txt`:

```
015edc  01100001      -> 01 10 00 01     Port 0: Maske 0x01, Tag 0x10, Pin 0, 1<<Pin 0x01
015ee4  02200102      -> 02 20 01 02     Port 1: Maske 0x02, Tag 0x20, Pin 1, 1<<Pin 0x02
015eec  04300204      -> 04 30 02 04     Port 2: Maske 0x04, Tag 0x30, Pin 2, 1<<Pin 0x04
```

Das ist die **Identität** - und exakt das, was `HostHDMIMAP 0,1,2` hineinschreiben würde.

Dazu kommt: **`ResetEDIDModule` setzt die Karte nicht zurück.** Der Unterbefehl geht über
den Dispatcher `0x12490` (Sprungtabelle `0x15b48`, Index 8) nach `0x127f0` und von dort
nach `0x120f0`; `0x120f0` fasst `[0x1723e]`, `[0x1723f]`, `[0x17240]`, `0x07091b00/b04`
und die Publish-Routine an, aber **kein** Byte in `0x17248…`. Die Sätze tragen nach einem
Kaltstart also die ROM-Vorgabe und danach nur noch das, was `HostHDMIMAP` geschrieben hat.

Damit war die alte Prüfung in der **ersten** Runde erfüllt - ohne je gewartet zu haben,
ohne je scheitern zu können, unabhängig davon, ob der Handler gelaufen ist. Die Messung
vom 07.09. 08:27 (`portmap: 0,1,2` im debugfs) ist aus demselben Grund kein Nachweis: die
Zeile hätte auch bei einer Firmware, die den Befehl komplett ignoriert, so ausgesehen.

**Der Auftrag hat das richtig gesehen. Der Befund ist bestätigt, nicht relativiert.**

---

## 2. Die Entscheidung - und die Alternativen, die ich verworfen habe

### 2.1 Gibt es ein Feld, das die Firmware nur bei Erfolg setzt? Nein - Beweis durch Aufzählung

Der vollständige Fußabdruck von `HostHDMIMAP` (`hi = 0`), Instruktion für Instruktion:

| # | was | taugt als Nachweis? |
|---|---|---|
| 1 | `memset(0x17320, 0, 0x41)` im Gruppenvorspann `0x11550..0x11564` | **nein** - läuft **vor** der Verzweigung, für alle fünf Unterbefehle gleich. Das ist genau die zu frühe Quittung. |
| 2 | Logzeile `0x115bc..0x115d8` (`l.jal 0xbf70`) | **nein**, doppelt: `0xbf70` ist ein `printf` mit Pegelmaske `[0x15c0c]` und Ziel `[0x15c10]`, es hinterlässt keinen Zähler in SRAM A2 - und selbst wenn: der Aufruf steht **vor** den Stores, würde also zu früh feuern. Er ist ja gerade das Fenster. |
| 3 | die drei Stores in `0x11f94`: +2 = Pin (`0x11fb0`), +3 = `1 << Pin` (`0x11fbc`), +4 = Pin (`0x11fc4`), drei Sätze bis `r4 == 0x17262` | **ja** - der einzige Kandidat |
| 4 | Tail-Jump `0x11fec` nach `0x11d88` mit Maske 7 (Publish) | **nein** - die Routine setzt am Ende `[0x1723f] = 1` (`0x11e6c`), aber das Byte steht an dieser Stelle der Folge **schon** auf 1: `ResetEDIDModule` setzt `[0x1723e] = 1` im Delay-Slot `0x121b8` und ruft direkt danach dieselbe Publish-Routine. Kein neuer Zustand, keine Information. |

Es gibt also **kein** Feld, das die Firmware ohnehin nur bei erfolgreicher Verarbeitung
setzt. Punkt 3 ist der einzige Nachweis - und der ist ohne Vorbelegung nicht
falsifizierbar. Der vom Prüfer vorgeschlagene Weg ist damit nicht der bequemere, sondern
der einzige.

Nebenbefund aus derselben Aufzählung: `0x11fdc` ist die **letzte** Instruktion im Image,
die den Pumpen-Puffer liest. Der Publish-Schwanz danach fasst ihn nicht mehr an. „Sätze
stimmen" heißt also wirklich „Puffer ist frei" - die Bedingung, die der nächste Befehl
braucht, und nicht nur „Handler ist irgendwann fertig".

### 2.2 Darf man in `0x17248…` schreiben? Ja - und das ist keine neue Praxis

Zwei Argumente, beide belegt:

**a) Der Treiber tut es bereits eine Ebene höher.** `arisc_arm_handler_probe()` schreibt
das **Komplement** des erwarteten Scratch-Inhalts nach `0x17320`, damit „unverändert" nicht
als „verarbeitet" durchgehen kann. Genau derselbe Gedanke, genau dasselbe SRAM A2, nur ein
Feld weiter. Wer das eine für zulässig hält, kann das andere nicht ablehnen; und wer die
Portmap-Prüfung ohne Vorbelegung baut, wiederholt den Fehler, den `arisc_arm_handler_probe()`
für den Scratch schon einmal behoben hat.

**b) Die Schreiber- und Leserliste ist vollständig.** `grep 0x7248 0x724a 0x724b 0x7262`
über die Disassembly:

*Schreiber:* `0x11ef8` (ROM-Kopie, einmal aus der Init `0x10f0c`) und `0x11fa0..0x11fc4`
(der `HostHDMIMAP`-Schwanz). **Kein dritter.** Insbesondere schreibt nichts periodisch
dorthin - das ist am Gerät mit einer Zeile prüfbar, siehe §5, Kontrolle A.

*Leser:*

| Byte | Leser | Verhalten mit `0xff` |
|---|---|---|
| +0 Maske | `0x11dec` (Publish-Schleife) | **nicht belegt** |
| +1 Tag | `0x11bb0` | **nicht belegt** |
| **+2 Pin** | `0x121e4` (`0x12220`) | Der Dispatch `0x12240`/`0x12250`/`0x1225c` kennt Pin 0, 1, 2; alles andere geht auf `0x12304`, das eine Logzeile ausgibt und dann bei `0x12318` `0x07091014` mit **genau dem** bei `0x12248` gelesenen Wert zurückschreibt. **Der Pin wird nicht bewegt - in keine Richtung.** |
| **+3 1<<Pin** | `0x11cac` (`0x11cc8`), `0x11a04` (`0x11a4c`) | Beide nur aus der Publish-Routine `0x11d88` bzw. dem Modul-Reset `0x120f0` erreichbar, also nur aus einem Unterbefehl - und die serialisiert `a->lock`. `0x11cac` merkt den Unterschied ohnehin nicht: es ODERt das Byte in einen Akku und testet Bit 0 (`0x11d28`); eine gesunde Karte (`1|2|4 = 7`) setzt es genauso wie `0xff`. |
| +4 Rückwärts | `0x11c64` (`0x11c70`): Pin → Port | **bleibt unangetastet.** Ein Fremdwert ließe den Lookup „kein solcher Port" antworten. Dieselben drei Stores schreiben +4 (`0x11fc4`), die beiden belegten Bytes decken es also mit ab. |

### 2.3 Was, wenn zwischen Vorbelegung und Firmware-Store ein `PullHotPlug` einträfe?

Drei Ebenen, in dieser Reihenfolge:

1. **Von uns kann keiner kommen.** `arisc_hdmi_set_portmap()` hält `a->lock` über die
   ganze Aktion, und `arisc_hdmi_hpd()` gibt das Mutex erst nach seiner eigenen Wartezeit
   wieder her.
2. **Von der Firmware nur mit laufendem Zähler.** Der einzige Pfad zu `0x121e4` ohne
   unseren Befehl ist die Hauptschleife `0x10f30`: sie prüft die drei Zähler
   `0x1722c+port` und ruft den Pin-Treiber genau dann, wenn ein Zähler auf **1** steht
   (`l.sfnei r16, 1` bei `0x10f54`, danach `[Zähler] = 0` und `0x121e4(port, r16)`).
   Der Treiber lehnt deshalb mit **`-EBUSY`** ab, solange einer der drei Zähler ungleich 0
   ist, statt sich auf Punkt 3 zu verlassen.
3. **Und wenn doch einer durchrutscht** (Zähler erreicht 1 zwischen unserem Lesen und
   unserem Schreiben): `0x121e4` landet mit Pin `0xff` auf `0x12304` und schreibt
   `0x07091014` unverändert zurück. **Der Puls geht verloren, er geht nicht auf den
   falschen Pin.** Von den beiden möglichen Fehlern ist das der harmlose - und er ist
   der Grund, warum die Vorbelegung `0xff` sein muss und nicht etwa ein anderer gültiger
   Pin: ein Wert aus `{0,1,2}` würde einen durchrutschenden Puls auf ein falsches Bit
   legen, also genau den Fehler erzeugen, den diese Prüfung fangen soll.

Ein Nebenbefund noch, damit er nicht verloren geht: `0x128b8` schreibt die Hotplug-Zähler
**pin-indiziert** (`0x12928`: `[0x1722c + Pin] = Wert`), während `0x12330` sie
**port-indiziert** schreibt. Mit einer Vorbelegung `0xff` läge das Ziel bei `0x1732b` -
mitten im Scratch. Die Routine ist in diesem Abbild jedoch **unerreichbar**: weder
`0x128b8` noch ihr Helfer `0x1283c` wird von irgendwo aufgerufen, und es gibt kein
Datenwort `000128b8`/`0001283c` (Funktionszeiger) im Image. Sollte eine spätere
Firmware-Version sie beleben, ist `0xff` als Vorbelegung neu zu bewerten - deshalb steht
es hier.

### 2.4 Warum `0xff` und nicht irgendein Wert

* Ein Pin ist 0, 1 oder 2; `1 << Pin` ist 1, 2 oder 4. `0xff` ist für **beide** Bytes
  unerreichbar, ein Treffer also nie ein Zufall.
* Der Fehlerfall, den die Prüfung fangen soll, hinterlässt Nutzlastbytes des
  **Folgebefehls**; `SetEDIDVersion 2` hat die Nutzlast `11 03 02 00 …`. Auch daraus kann
  nie `0xff` werden - die beiden Fehlerbilder bleiben unterscheidbar.
* `0xff` ist für jeden erreichbaren Leser harmlos (§2.2) und für `0x121e4` sogar
  ausdrücklich als Fehlereingabe vorgesehen.

### 2.5 Verworfen

| Weg | warum nicht |
|---|---|
| `HostHDMIMAP` zweimal senden, erst eine Permutation, dann `0,1,2` | Verdoppelt genau das Rennen, um das es geht, und programmiert für ~1 ms eine **gültige** falsche Karte - ein durchrutschender Puls ginge dann auf den falschen Pin statt ins Leere. Wäre außerdem eine Wiederholung, und die ist ausgeschlossen. |
| Pause zwischen den Unterbefehlen | Der Auftrag schließt es aus, und es wäre auch sachlich falsch: eine Pause verdeckt das Rennen wieder, statt es zu entscheiden. Genau das tut das Skript mit seinen 600 ms. |
| Prüfung ganz weglassen und nur den Rückgabewert von `arisc_send()` melden | Damit wäre man beim Zustand vor `B-hpd-luecke.md`: der Scratch-Vergleich quittiert für `hi = 0` zu früh. |
| Nichts belegen und stattdessen dokumentieren, dass die Prüfung nur bei bereits kaputter Karte greift | Ein Wächter, der beim Kaltstart schläft und nur beim Warmstart wacht, ist genau am gefährlichen Fall blind. |

---

## 3. Was geändert wurde (`0091`, nur `sun50i-h713-arisc.c`)

| # | Änderung | Beleg |
|---|---|---|
| 1 | `PORTMAP_POISON 0xff` neu; der Kommentarblock an `SRAM_PORTMAP` nennt jetzt **beide** Schreiber (`0x11e88` aus der Init, `0x11f94`), die ROM-Tabelle `0x15edc` byteweise und die Folgerung, dass die Vorgabe die Identität ist. | `0x11ef8..0x11f3c`, `0x15edc` |
| 2 | Neu `arisc_arm_portmap_probe()`: sichert Byte +2/+3 aller drei Sätze, belegt sie mit `0xff` und **liest die Vorbelegung zurück**. Landet sie nicht, `-EIO` und **es wird nichts gesendet** - eine Prüfung, die nicht scheitern kann, ist schlechter als keine. | §2.2 |
| 3 | Neu `arisc_restore_portmap()`: setzt +2/+3 auf den vorgefundenen Stand zurück, sobald der Befehl scheitert. Sonst bliebe `0xff` stehen und jeder spätere `PullHotPlug` liefe in die Fehlerkante `0x12304`, während der Zähler trotzdem auf 0 geht - ein **zweiter** stiller Erfolg, also genau das Muster, das hier verschwinden soll. | `0x12304`, `0x10f30` |
| 4 | `arisc_wait_portmap()` unterscheidet die beiden Fehlerbilder in der Meldung: „Vorbelegung steht noch" (Handler nie bis zu den Stores gekommen) gegen „Pin x statt Pin y" (Handler lief, Puffer war überschrieben). Beide Zeilen nennen Satz, gelesenen Pin, gelesenes Bit, erwarteten Pin, erwartetes Bit. Frist unverändert `HANDLER_TIMEOUT_MS` (500 ms), kein Retry. | §1 |
| 5 | `arisc_hdmi_set_portmap()`: `-EBUSY`, solange einer der drei Hotplug-Zähler ungleich 0 ist; Vorbelegung → senden → warten → bei Fehler zurücksetzen. Die Pin-Prüfung `< ARISC_HDMI_PORTS` läuft jetzt in einer Schleife statt dreifach ausgeschrieben. | §2.3 |
| 6 | Der Kommentar an der Portmap-Zeile in `debugfs status` sagt jetzt, dass `0,1,2` dort **nichts** beweist (die ROM-Vorgabe sieht genauso aus) und dass der Rückgabewert das Urteil ist. Die Zeile bleibt, weil sie im **anderen** Fall die Nutzlast nennt, die die Firmware stattdessen gelesen hat. | §1 |
| 7 | Der Patchtext begründet in einem eigenen Absatz, **warum die alte Prüfung nichts bewies**, und trägt die Leserliste als Argument, nicht als Behauptung. | - |

**Was ausdrücklich *nicht* geändert wurde:** keine Pause zwischen den Unterbefehlen, keine
Wiederholung, kein Doorbell-Puls, kein Timeout als Heilmittel, keine neue Wartezeit. Die
Frist ist dieselbe wie vorher; nur die Bedingung, auf die gewartet wird, kann jetzt
scheitern.

### Belegt vs. vermutet

**Belegt (Disassembly, in §1 und §2 wortweise zitiert):** die ROM-Tabelle `0x15edc` und
ihre Kopie durch `0x11e88`; dass `ResetEDIDModule` die Sätze nicht anfasst; dass es genau
zwei Schreiber und fünf Leser gibt; dass `0x12304` das Register unverändert zurückschreibt;
dass `0x11fdc` die letzte Instruktion ist, die den Pumpen-Puffer liest; dass `0x128b8`
(pin-indizierte Zählerschreibung) in diesem Abbild keinen Aufrufer und keinen
Funktionszeiger hat.

**Vermutet, bis die Abnahme es sagt:** dass die Vorbelegung am Gerät wirklich landet.
Genau das prüft der Treiber vor dem Senden selbst und meldet `-EIO`, wenn nicht - und §5
Kontrolle A macht es zusätzlich von Hand sichtbar.

**Unverändert offen (aus `B-hpd-luecke.md`):** der eine Lauf, in dem `0x03` ein
verbundener Zustand war.

---

## 4. Prüfbau

**Als Prüfbau gekennzeichnet, Originalbaum unberührt.** Kopie von
`mainline/build/linux-6.18.38-8fb6758e3cc841727859df4b4dea61ea3eae9724e999c8e019f478f21fdd4402`
nach `<scratch>/paket-b2/pruefbau-tree`, Markerdatei
`PRUEFBAU-KOPIE-NICHT-DER-ORIGINALBAUM`, am Ende gelöscht.

```
make ARCH=arm64 LLVM=1 W=1 drivers/soc/sunxi/sun50i-h713-arisc.o   ->  CC [M] ..., 0 Warnungen
make ARCH=arm64 LLVM=1 W=1 M=drivers/soc/sunxi modules             ->  LD [M] sun50i-h713-arisc.ko
```

Die einzige Warnung im Verzeichnis kommt aus `cpu_comm/cpu_comm_rpc.c` (`prev_idx set but
not used`) und ist **vorbestehend**. `llvm-18` lag nicht im `PATH` und wurde für den Bau
davorgehängt (`PATH=/usr/lib/llvm-18/bin:$PATH`) - nichts am Rechner geändert.

`checkpatch.pl --no-tree --no-signoff`: **0 errors, 6 warnings** - dieselben sechs wie
vorher (Zeilenlänge in der Commit-Message, 5× „acknowledgement"). Keine neue.

`patch -p1 -R --dry-run` gegen den Prüfbau läuft glatt durch; der Patch in ein leeres
Verzeichnis angewandt liefert `sun50i-h713-arisc.c` und `h713-arisc.h` **byteidentisch** zu
dem, was gebaut wurde. Genau **eine** `Signed-off-by:`-Zeile, Kopf wie `0049`.
`build/build.sh` nicht aufgerufen, `patches/kernel/series` nicht angefasst.

**Nebenbei repariert:** der Hunk-Kopf des Treibers stand auf `@@ -0,0 +1,1721 @@`, während
der Rumpf 1730 Zeilen hatte, und vor dem Header-Diff fehlte die `diff -ruN`-Zeile. GNU
`patch` schluckt beides, `git apply` nicht. Beides ist jetzt korrekt; der Patch wurde
komplett neu erzeugt, nicht von Hand nachgezählt.

---

## 5. Abnahmevorschrift für die Hauptsitzung (kopierbar)

Voraussetzung: FIT mit dem neuen `0091` bauen (`build/build.sh`) und nach `tftp/` legen.

Der Zweck dieser Vorschrift ist **nicht** nur „läuft es durch", sondern: **beide Ausgänge
der Prüfung am Gerät sichtbar machen.** Schritte 3-5 sind Kontrollen, die vor der
eigentlichen Folge laufen und je einzeln scheitern können; sie brauchen zusammen keine
Minute.

```bash
# ---- 0. Vorbedingungen -------------------------------------------------------
ss -ulnp | grep -w :69                       # TFTP muss lauschen; sonst STOPP
echo "$(date +%F_%T) hauptsitzung B-waechter" > /tmp/claude-1000/h713-board.lock
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'   # Ausgangswert notieren

# ---- 1. Kaltstart ------------------------------------------------------------
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

# ---- 2. Prep OHNE Schritt 1 und ohne das alte Modul, dann SetSource ----------
ssh root@192.168.8.141 "echo 'module sun50i_h713_arisc +p' > /sys/kernel/debug/dynamic_debug/control"
ssh root@192.168.8.141 "sed -e '/arisc_load.py/d' \
    -e 's#; insmod /root/hy310-arisc-hdmi.ko 2>/dev/null##' \
    /root/prep_after_boot.sh > /root/prep_ohne_arisc.sh && sh /root/prep_ohne_arisc.sh"
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it \
     --only setsource --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3'
```

### Schritt 3 - der Ausgangszustand, der die alte Prüfung blind machte

```bash
ssh root@192.168.8.141 'for a in 0x0011724a 0x0011724b 0x00117252 0x00117253 0x0011725a 0x0011725b; do
    printf "%s = " $a; busybox devmem $a b; done'
```

**ERWARTET nach Kaltstart: `00 01 | 01 02 | 02 04`** - die ROM-Vorgabe, Pin 0/1/2 mit
`1<<Pin`. Genau darauf hat die alte Prüfung gewartet, und genau deshalb konnte sie nicht
scheitern. Steht hier etwas anderes, ist die Firmware nicht frisch gestartet - dann
zurück zu Schritt 1.

### Schritt 4 - Kontrolle A: schreibt irgendetwas sonst in die Sätze?

`reset-edid` muss zuerst laufen (der Treiber sperrt alles andere bis dahin), und die
Hotplug-Zähler müssen 0 sein, sonst könnte die Hauptschleife den Pin-Treiber rufen.

```bash
ssh root@192.168.8.141 'echo reset-edid > /sys/kernel/debug/h713-arisc/cmd; echo rc=$?'
ssh root@192.168.8.141 'grep hpd_counter /sys/kernel/debug/h713-arisc/status'   # muss "0 0 0" sein

# Satz 0 von Hand vorbelegen -- nur SRAM A2, kein 0x0709xxxx
ssh root@192.168.8.141 'busybox devmem 0x0011724a b 0xff; busybox devmem 0x0011724b b 0xff'
ssh root@192.168.8.141 'grep portmap /sys/kernel/debug/h713-arisc/status'
#   ERWARTET: portmap: 255,1,2     <- die Datei zeigt, was die Firmware haelt
sleep 5
ssh root@192.168.8.141 'grep portmap /sys/kernel/debug/h713-arisc/status'
#   ERWARTET: portmap: 255,1,2     <- unveraendert
```

**Was das beweist:** die ARM-Seite kann diese Bytes schreiben (sonst wäre die Vorbelegung
und damit die ganze Methode wertlos), und **kein Dritter schreibt sie periodisch nach** -
die Behauptung „nur `0x11f94` schreibt hier" ist damit nicht nur aus der Disassembly,
sondern am laufenden Gerät belegt. Bleibt die Zeile bei `0,1,2`, hat der `devmem`-Schreib
nicht gewirkt; dann ist die Vorbelegung des Treibers ebenfalls wirkungslos und der Treiber
würde `-EIO` melden - das ist dann der Befund, und §2 ist neu zu bewerten.

### Schritt 5 - Kontrolle B: ersetzt die Firmware die Vorbelegung?

Satz 0 trägt jetzt `0xff/0xff`. Der Treiber belegt beim nächsten `portmap` alle drei Sätze
neu vor und wartet auf `0,1,2`.

```bash
ssh root@192.168.8.141 'echo "portmap 0 1 2" > /sys/kernel/debug/h713-arisc/cmd; echo rc=$?'
ssh root@192.168.8.141 'grep portmap /sys/kernel/debug/h713-arisc/status'
ssh root@192.168.8.141 'dmesg | grep -i h713-arisc | tail -10'
```

`echo` liefert bei jedem Fehler `rc=1` und schreibt den `strerror`-Text der Shell dazu;
**welcher** Fehler es war, sagt `dmesg` - deshalb steht die `dmesg`-Zeile oben mit im Block.

* **`rc=0` und `portmap: 0,1,2`** → die Firmware hat die Sätze geschrieben. Das ist der
  Nachweis, den die alte Prüfung nie erbringen konnte: `0,1,2` steht dort jetzt, **weil**
  der Handler gelaufen ist, und nicht, weil es ohnehin dort stand.
* **`Input/output error`** (`-EIO`, 5) und `laesst sich nicht vorbelegen` → die
  Vorbelegung landet nicht; siehe Schritt 4.
* **`Connection timed out`** (`-ETIMEDOUT`, 110) und `traegt nach 500 ms noch die
  Vorbelegung 0xff` → **der Handler ist nicht gelaufen.** Das ist der Ausgang, den es
  vorher nicht geben konnte. Satz 0 steht danach wieder auf `255/255` (der Treiber setzt
  den vorgefundenen Stand zurück) - **von Hand aufräumen**:
  ```bash
  ssh root@192.168.8.141 'busybox devmem 0x0011724a b 0x00; busybox devmem 0x0011724b b 0x01'
  ```
* **`Connection timed out`** und `traegt Pin 2 (Bit 0x04) statt Pin 0` → der Handler lief,
  hat aber aus einem überschriebenen Puffer gelesen. Das ist das Rennen aus
  `B-hpd-luecke.md`, am Gerät gefangen statt durchgelassen. Die Zeile gehört ins Log.
* **`Device or resource busy`** (`-EBUSY`, 16) und `Hotplug-Zaehler Port n steht auf m` →
  ein Puls ist noch unterwegs; ein paar Sekunden warten und Schritt 5 wiederholen.

**In jedem Fehlerfall gilt:** die Handvorbelegung aus Schritt 4 steht noch (der Treiber
setzt den *vorgefundenen* Stand zurück, und der war `0xff`). Vor Schritt 6 also immer
`portmap:` prüfen und, wenn dort `255` steht, die Aufräumzeile oben laufen lassen.

### Schritt 6 - die eigentliche Folge

```bash
ssh root@192.168.8.141 'time sh -c "echo edid > /sys/kernel/debug/h713-arisc/cmd"; echo rc=$?'
ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status'
ssh root@192.168.8.141 'dmesg | grep -i "h713-arisc" | tail -40'
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'
ssh user@192.168.8.162 'strings /sys/class/drm/card0-HDMI-A-2/edid | head'
```

**Gutkriterien, alle drei nötig:**

1. Schritt 5 lieferte **`rc=0`** - der Portmap-Schritt hat einen echten
   Firmware-Schreibzugriff gesehen. (`portmap: 0,1,2` in `status` ist **kein**
   Kriterium und war nie eins; siehe §1.)
2. `echo edid` gibt **0** zurück und `dmesg` endet mit
   `EDID/HPD-Sequenz auf Port 0 abgeschlossen`.
3. Der Zuspieler meldet **`connected`** und `strings …/edid` enthält **`SGD SX8`**.

**Wenn 1 und 2 grün sind und 3 rot bleibt**, ist die Karte nicht die (einzige) Ursache.
Dann ist der nächste und einzige nötige Messschritt der Registerwert **mit** der
nachgewiesenen Karte:

```bash
ssh root@192.168.8.141 'busybox devmem 0x07091014; busybox devmem 0x07091b04'
#   ERWARTET dann 0x00000006 / 0x00000007  (= der Stock-Zustand)
#   ACHTUNG: erst NACH ResetEDIDModule lesen -- vorher haengt der SoC (doku/82 §9).
```

Steht dort `0x06` und der Zuspieler bleibt trotzdem `disconnected`, liegt es **nicht** an
der ARISC-Seite; die Suche gehört auf die Zuspieler-/Kabelseite bzw. an das Ausgabe-Gate
`[0x1723f]`. Steht dort etwas anderes als `0x06`, hat ein Dritter den Pin nachgezogen -
dann `busybox devmem 0x0011722c` (die drei Zählerfächer) unmittelbar danach lesen.

### Woran man sähe, dass der Handler *nicht* gelaufen ist - die Kurzform

| Beobachtung | Bedeutung |
|---|---|
| `echo … > cmd` scheitert (`Connection timed out`, `-ETIMEDOUT`) und `dmesg` sagt `traegt nach 500 ms noch die Vorbelegung 0xff` | Der Handler hat die Stores in `0x11f94` nie erreicht. **Vorher unsichtbar** - die alte Prüfung hätte hier 0 gemeldet. |
| dasselbe, aber `traegt Pin 2 (Bit 0x04) statt Pin 0 (Bit 0x01)` | Der Handler lief zu spät und las den überschriebenen Puffer - das Rennen aus `B-hpd-luecke.md`. |
| `Input/output error` (`-EIO`) und `laesst sich nicht vorbelegen` | Die Vorbelegung landet nicht; die Prüfung wäre blind, es wurde **nichts** gesendet. |
| `Device or resource busy` (`-EBUSY`) und `Hotplug-Zaehler …` | Ein Puls ist unterwegs; die Karte wurde absichtlich nicht angefasst. |
| `rc=0` | Die drei Sätze trugen `0xff`, und danach den angeforderten Pin. Nur die Firmware kann das geschrieben haben. |

---

## 6. Stand von Paket B danach

| Teil | Stand |
|---|---|
| Firmware laden, Reset lösen, Notify quittieren | **grün am Gerät** |
| `ResetEDIDModule`, `SetEDIDVersion`, 8 × `UpdateEDID`, `CheckEDIDUpdateStatus`, `RequestEDID` | **grün am Gerät** |
| `HostHDMIMAP` - Ursache | belegt (`B-hpd-luecke.md`) |
| `HostHDMIMAP` - Gegenprüfung | **falsifizierbar gebaut**, Prüfbau grün, Abnahme offen |
| `SetEDIDAudioMode`, `SET5VFlag` | laufen durch; in dieser Firmware **wirkungslos** (belegt) |
| HPD DOWN/UP | mechanisch grün; ob der richtige Pin bewegt wird, entscheidet Schritt 5 der Abnahme |
| Zuspieler `connected` aus dem Kernel | **offen bis zur Abnahme** |
