# B - Die HPD-Lücke: warum der Treiber den falschen Pin bewegt (07:00-08:30)

Agent: Paket B, Teilauftrag „ein Punkt fehlt noch". **Board nicht angefasst** - kein `ssh`,
kein `sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts nach `tftp/`. Kein
`sudo`, kein `git`. Geändert: `mainline/patches/kernel/0091-...patch` und
`doku/82-arisc-treiber.md`. `series` und `build/build.sh` unberührt; Prüfbau in einer
gekennzeichneten Kopie, danach gelöscht.

---

## 0. Die Kurzfassung

**Die Befehlsfolge des Treibers ist Zeichen für Zeichen die des Skripts. Der Unterschied
ist die Geschwindigkeit - und ein Unterbefehl, dessen Quittung zu früh kommt.**

`HostHDMIMAP` ist der **einzige** Unterbefehl der `0x11`-Gruppe, dessen Handler seine
Argumente **nach** dem `memset`, auf das der Treiber wartet, noch einmal aus dem Puffer der
Empfangspumpe liest - und zwar hinter einem Log-Aufruf. Das Skript wartet danach 600 ms und
merkt nichts. Der Treiber schiebt den nächsten Befehl nach ~1 ms nach und überschreibt die
Karte, bevor die Firmware sie gelesen hat.

Der nächste Befehl ist `SetEDIDVersion 2`; seine Nutzlast ist `11 03 02 00 00 …`. Die
Firmware liest daraus die Karte **2,0,0**. Damit trägt **Port 0 den Pin 2**, und
`PullHotPlug` bewegt Bit 2 statt Bit 0 des Pin-Registers.

Genau das steht in der Messung: `0x07091014` ging von `0x07` auf `0x03` - Bit 2 gelöscht.
Stock steht im verbundenen Zustand auf `0x06` - Bit 0 gelöscht. Der Zuspieler hängt an
Bit 0 und hat deshalb nie eine steigende Flanke gesehen, obwohl jeder einzelne Schritt der
Folge `0` zurückgegeben hat.

---

## 1. Schritt für Schritt: Skript gegen Treiber

`analyse/hdmi-seq/arisc_edid_init.sh` gegen `arisc_hdmi_edid_init()` im erzeugten Baum
`mainline/build/linux-6.18.38-8fb6758e…4402/drivers/soc/sunxi/sun50i-h713-arisc.c`.

| # | Skript | Treiber | gleich? |
|---|---|---|---|
| 1 | `0x2011` 0,0 | `arisc_hdmi_reset_edid()` → `0x2011` 0,0 | ja |
| 2 | `0x0011` 0,1, data `2` | `arisc_hdmi_set_portmap({0,1,2})` → `0x0011` 0,1, data `2` | ja |
| 3 | `0x0311` 2,0 | `0x0311` 2,0 | ja |
| 4-11 | `0x0111` frag, EDID[frag*64], 63 B | dasselbe | ja |
| 12 | `0x0215` 0,0 | dasselbe | ja |
| 13 | `0x0315` 0,0 | `arisc_hdmi_get_edid(0,…)` → `0x0315` 0,0 | ja |
| 14 | `0x0511` 0,0 | `arisc_hdmi_audio_mode(0,0)` → `0x0511` 0,0 | ja |
| 15 | `0x0411` 0,1 | `arisc_hdmi_5v(0,true)` → `0x0411` 0,1 | ja |
| 16 | `0x0211` 0,2 | `ARISC_HDMI_HPD_DOWN` = 2 → `0x0211` 0,2 | ja |
| 17 | 10 s, dann `0x0211` 0,1 | `msleep(10000)`, `ARISC_HDMI_HPD_UP` = 1 → `0x0211` 0,1 | ja |

**Kein Unterschied in Unterbefehl, Argument oder Reihenfolge.** Auch der Ablieferweg ist
derselbe: beide schreiben die Nutzlast direkt nach `0x115f59` und schicken einen
Zwei-Wort-Rahmen mit Länge 0. Es bleiben vier Unterschiede, und nur der erste ist tragend:

1. **Abstand.** Das Skript startet je Befehl einen eigenen Python-Prozess und schaut danach
   `--settle 0.6` s zu (`0x0315`: 1,5 s). Der Treiber wartet auf den Scratch-Vergleich -
   `usleep_range(500, 1000)` - und sendet den nächsten Befehl unmittelbar danach. Der
   ganze Vorlauf bis `PullHotPlug DOWN` dauert beim Treiber **0,85 s** (10,85 s gemessen
   minus die 10 s HPD-low), beim Skript rund 15 s.
2. Doorbell-Puls: Skript ja, Treiber nein. Am Gerät belegt, dass die Handler auch ohne Puls
   laufen (`B-abnahme-board.md`), und der Fehler tritt bei `HostHDMIMAP` auf, dessen Handler
   nachweislich **gelaufen ist**.
3. Das Skript leert ARM-RX ch1 nur einmal nach `0x0315`; der Treiber holt alle vier Rahmen
   ab. Das erklärt die Messung `0x07091b04 = 0` vor dem UP im Skriptlauf (siehe §3),
   nicht den Fehler.
4. Das Skript liest `0x07091014`/`0x07091b04` vom ARM aus, der Treiber nie. Lesezugriffe.

---

## 2. Der Beleg aus der Disassembly (`analyse/arisc-frame/full-disasm.txt`)

### 2.1 Der Gruppenhandler nullt zuerst und verzweigt danach

```
011550  l.movhi  r14, 0x0001
011558  l.ori    r14, r14, 0x7320      ; r14 = 0x17320  (Scratch)
01155c  l.addi   r5,  r0,  0x0041      ; 65 Byte
011560  l.jal    0x9aa0                ; memset(0x17320, 0, 0x41)   <-- die Quittung
011568  l.lbz    r3,  1(r2)            ; erst JETZT sub_cmd_hi
```

Der Unter-Dispatch dahinter kennt genau fünf Werte:

```
01156c  sfeqi  r3, 2   -> 0x1164c   PullHotPlug
011574  sfgtui r3, 2   -> 0x115a0
011580  sfeqi  r3, 0   -> 0x115b8   HostHDMIMAP
01158c  sfeqi  r3, 1   -> 0x115f8   UpdateEDID    (sonst 0x117f8 = return)
0115a0  (hi==3)        -> 0x11678   SetEDIDVersion
0115a4  sfeqi  r3, 0x20-> 0x11664   ResetEDIDModule (sonst 0x117f8 = return)
```

`hi = 4` (**SET5VFlag**) und `hi = 5` (**SetEDIDAudioMode**) fallen auf `0x117f8` und tun
**nichts**. Beide Läufe schicken sie, beide Läufe bekommen dasselbe Nichts - als Ursache
scheiden sie aus. (Für doku/82 §12.5 ist das die Teilantwort: wenn die ARISC auf 5 V
reagiert, dann nicht über `0x0411`.)

### 2.2 Drei Zweige nehmen ihre Argumente mit, einer nicht

| `hi` | liest aus dem Pumpen-Puffer | wohin | Dispatcher bekommt |
|---|---|---|---|
| 1 | 65 B ab Nutzlast[2] (`0x1160c` - `0x1162c`) | Scratch | Zeiger auf Scratch (`0x11634`) |
| 2 | Nutzlast[2], [3] (`0x1164c`, `0x11658`) | Scratch | Zeiger auf Scratch (`0x11660`) |
| 3 | Nutzlast[2] (`0x11678`) | Scratch | Zeiger auf Scratch (`0x11660`) |
| 0x20 | nichts | - | - |
| **0** | Nutzlast[2],[3],[4] (`0x115bc`, `0x115c8`, `0x115d4`) **nur für die Logzeile**, dann `l.jal 0xbf70` (`0x115d8`), dann `l.j 0x11f94` (`0x115f0`) mit `r3 = &Nutzlast[2]` | - | **Zeiger in den Pumpen-Puffer** |

Und `0x11f94` liest ihn danach noch einmal:

```
011fa0  l.ori  r4, r4, 0x724a      ; Ziel = 0x1724a  (Satz 0, Byte +2)
011fac  l.lbz  r2, 0(r3)           ; Quelle = Nutzlast[2+i]
011fb0  l.sb   0(r4), r2           ;   +2 = Pin
011fb4  l.lbz  r6, 0(r3)
011fb8  l.sll  r6, r5, r6
011fbc  l.sb   1(r4), r6           ;   +3 = 1 << Pin
011fc0  l.lbz  r2, 0(r3)
011fc4  l.sb   2(r4), r2           ;   +4 = Pin
011fcc  l.addi r4, r4, 0x0008      ; nächster Satz
011fd4  l.sfne r4, 0x17262         ; drei Sätze
011fdc  l.addi r3, r3, 0x0001      ; Quelle += 1  (Delay-Slot)
011fec  l.j    0x11d88             ; danach: veröffentlichen (Maske 7)
```

**Zwischen `memset` und diesen Stores liegt ein Log-Aufruf.** Das ist das Fenster.

### 2.3 Was mit der Karte passiert, und warum das den Pin verschiebt

`0x121e4` ist die Routine, die den Pin treibt:

```
0121f0  l.slli r3, r3, 3            ; Port * 8
0121f4  l.ori  r2, r2, 0x7248
0121fc  l.add  r3, r3, r2           ; &Portmap[Port]
012210  l.lbz  r2, 3(r2)            ; [0x1723f]  Ausgabe-Gate
012218  l.sfnei r2, 0
01221c  l.bf   0x1223c              ; Gate zu -> "EDID-HPD %d LOW", Wert := 0
012220  l.lbz  r14, 2(r3)           ; r14 = PIN dieses Ports   <-- aus der Karte
012240  l.sfeqi r14, 1  -> 0x1229c  ; Bit 1
012250  l.sfltui r14, 1 -> 0x12270  ; Bit 0
01225c  l.sfeqi r14, 2  -> 0x122d8  ; Bit 2   (sonst Fehlerpfad 0x12304)
012318  l.sw   0(r3), r2            ; 0x07091014 zurückschreiben
```

Je Zweig gilt dasselbe Muster, hier Pin 0 (`0x12270`):

```
012258  l.sfnei r4, 0               ; Wert != 0 ?
012270  l.bf    0x12280             ;   ja  -> löschen
01227c  l.ori   r2, r2, 0x0001      ;   nein-> Bit SETZEN     (Delay-Slot)
012284  l.and   r2, r2, ~1          ;         Bit LÖSCHEN
```

**`0x07091014` ist aktiv-low: Bit gesetzt = HPD LOW.** Das deckt sich mit allem
Gemessenen: `0x07` (alle drei gesetzt) = `disconnected`, Stock verbunden = `0x06`
(Bit 0 gelöscht), `PullHotPlug` DOWN/UP auf Port 0 schaltet den Zuspieler um (K4).

Die Vorgabetabelle im ROM (`0x15edc`, je 8 Byte) liefert Pin 0/1/2 für Port 0/1/2:

```
015edc  01 10 00 01 | 015ee0  00 00 00 00     Port0: Maske 0x01, Pin 0, 1<<Pin = 0x01
015ee4  02 20 01 02 | 015ee8  01 00 00 00     Port1: Maske 0x02, Pin 1, 0x02
015eec  04 30 02 04 | 015ef0  02 00 00 00     Port2: Maske 0x04, Pin 2, 0x04
```

`HostHDMIMAP 0,1,2` schreibt genau dasselbe wieder hinein. **Solange die Karte stimmt,
kann `PullHotPlug` auf Port 0 nur Bit 0 bewegen.** `0x03` ist also beweisbar **nicht** das
Ergebnis eines Port-0-Pulses mit korrekter Karte.

Mit der überschriebenen Karte `2,0,0` dagegen:

* Port 0 → Pin 2 → **Bit 2**,
* DOWN setzt Bit 2 (war schon gesetzt: `0x07` bleibt `0x07`),
* UP löscht Bit 2: **`0x07` → `0x03`**. Genau der gemessene Wert.

---

## 3. Die drei Messwerte, erklärt

| Messung | Erklärung |
|---|---|
| Skript vor UP: `1014 = 0x07`, `b04 = 0x00` | Alle drei Pins low (DOWN auf Port 0 hatte Bit 0 gesetzt, die anderen standen schon). `b04 = 0` ist die Klammer von `RequestEDID`: `0x1269c` ruft `0x11cac(7,0)` (Bits 0-2 löschen), erst `0x12724` ruft `0x11cac(7,1)` und setzt sie wieder - und dazwischen schiebt die Firmware vier Rahmen à 0x48 B durch ein 8-Wort-FIFO. Das Skript hatte nur einmal gedraint, die Firmware hing also noch im Senden. |
| Skript nach UP: `1014 = 0x06`, `b04 = 0x07` → `connected` | Karte intakt → Pin 0 → Bit 0 gelöscht. `0x06` ist derselbe Wert wie im Stock-Abzug (`re/captures/weltneuheit/stock-post-hdmi.txt`, Z. 931). `b04` steht wieder auf 7, weil `0x12724` inzwischen gelaufen ist (der Sendeversuch lief in seine Frist). |
| Treiber: `0x07` → `0x03`, `disconnected` | Karte auf `2,0,0` überschrieben → Pin 2 → Bit 2 gelöscht. Bit 0 (der Stecker) wurde in der ganzen Folge **nie angefasst** und blieb low. |
| Treiber im bereits verbundenen Zustand: `0x03`/`0x07` vorher wie nachher, Verbindung bleibt | Dieselbe kaputte Karte: DOWN setzt Bit 2, UP löscht es wieder - vor und nach der Folge steht dasselbe da, und Bit 0 wird nicht berührt, also reißt die Folge auch nichts ab. |

### Was die Werte **nicht** hergeben - offen und benannt

In dem einen Lauf, in dem `0x03` ein **verbundener** Zustand war, ist Bit 0 gesetzt, also
Pin 0 low - und der Zuspieler meldete trotzdem `connected`. Das passt nicht zu „Bit 0 =
der Stecker" und ist mit den vorliegenden Daten **nicht** entscheidbar. Solange das offen
ist, gilt: **der Registerwert allein bestimmt den Zustand nicht.** Was ihn bestimmt, ist
das Paar aus (a) der Karte `0x17248+Port*8+2`, die sagt, *welches* Bit ein Puls bewegt,
und (b) dem Ausgabe-Gate `[0x1723f]`, das `0x121e4` bei 0 den Wert auf 0 zwingen lässt.
Beides liegt in SRAM A2 und ist gefahrlos lesbar; das Register `0x07091014` ist nur die
Wirkung. Die Messvorschrift dafür steht in §6.

---

## 4. Was geändert wurde (`0091`, nur `sun50i-h713-arisc.c`)

| # | Änderung | Beleg |
|---|---|---|
| 1 | Neu `SRAM_PORTMAP 0x17248`, `PORTMAP_STRIDE 8`, `PORTMAP_PIN 2`, `PORTMAP_PIN_BIT 3` mit Kommentar, was die Sätze enthalten und wer sie schreibt. | `0x11f94`, `0x121e4` (`0x12220`), ROM-Tabelle `0x15edc` |
| 2 | Neu `arisc_wait_portmap()`: wartet, bis alle drei Sätze den angeforderten Pin (`+2`) **und** `1 << Pin` (`+3`) tragen. Dieselbe Frist wie der Scratch-Vergleich (`HANDLER_TIMEOUT_MS`, 500 ms), **keine neue Wartezeit**, kein Retry. Bei Ablauf `-ETIMEDOUT` und eine Zeile, die Port, gelesenen und erwarteten Pin nennt. | §2.2, §2.3 |
| 3 | `arisc_hdmi_set_portmap()` ruft das nach `arisc_send()` auf und lehnt Pins ≥ 3 vorab ab (`0x121e4` hat für alles andere nur den Fehlerpfad `0x12304`). | §2.3 |
| 4 | Kommentarblock an `arisc_hdmi_set_portmap()`: die vollständige Fallunterscheidung, welcher Zweig den Puffer wann losläßt, warum das Skript den Fehler nicht sieht, und was aus der Karte `2,0,0` folgt. | §2 |
| 5 | Der Kommentar an `arisc_expected_scratch()` sagt jetzt ausdrücklich, dass die Quittung für `hi = 0` **nicht** reicht, und warum sie für `hi = 4`/`5` trotzdem genügt (die beiden bewirken nichts). | §2.1 |
| 6 | `debugfs status` zeigt neu `portmap: a,b,c` - die Karte, **wie die Firmware sie hält**. Nur SRAM A2, kein `0x0709xxxx`. | Abnahme |

**Was ausdrücklich *nicht* geändert wurde:** keine Pause zwischen den Unterbefehlen, keine
Wiederholung, kein Puls, kein Timeout als Heilmittel. Die Quittung war zu schwach; sie ist
jetzt die richtige. Der Treiber bleibt schneller als das Skript - er wartet nur auf das,
was der Befehl bewirkt, statt auf das, was der Gruppenhandler in seiner Vorrede tut.

### Belegt vs. vermutet

**Belegt (Disassembly, Wort für Wort in §2 zitiert):** die Lage des `memset` vor der
Verzweigung; dass nur `hi = 0` den Puffer nach der Quittung noch liest; der Log-Aufruf
dazwischen; dass `0x11f94` Pin und `1 << Pin` in die Sätze ab `0x1724a` schreibt; dass
`0x121e4` den Pin aus `+2` holt und aktiv-low arbeitet; die ROM-Vorgabe 0/1/2; dass
`hi = 4` und `hi = 5` in dieser Firmware nichts tun.

**Belegt (Messung):** `0x07 → 0x03` beim Treiber, `0x07 → 0x06` beim Skript, Stock `0x06`,
und dass DOWN/UP auf Port 0 den Zuspieler umschaltet (K4).

**Vermutet, bis der Abnahmelauf es sagt:** dass das Fenster wirklich bei *jedem* Lauf
zuschlägt und nicht nur meistens - das Rennen ist ein Rennen, nicht ein Determinismus. Die
neue Prüfung deckt beide Ausgänge ab: gewinnt der Treiber das Rennen, geht `portmap` sofort
durch; verliert er es, steht die Karte falsch, die Prüfung schlägt an und nennt den Wert.
Deshalb ist im Abnahmelauf **`dmesg` auch dann interessant, wenn alles grün ist**.

**Nicht erklärt:** der Lauf mit `0x03` = verbunden (§3).

---

## 5. Prüfbau

**Als Prüfbau gekennzeichnet, Originalbaum unberührt.** Kopie von
`mainline/build/linux-6.18.38-8fb6758e3cc841727859df4b4dea61ea3eae9724e999c8e019f478f21fdd4402`
nach `/tmp/claude-1000/wf-rest/paket-b/pruefbau-tree`, Markerdatei
`PRUEFBAU-KOPIE-NICHT-DER-ORIGINALBAUM`, am Ende gelöscht.

```
make ARCH=arm64 LLVM=1 W=1 drivers/soc/sunxi/sun50i-h713-arisc.o   ->  CC [M] ..., 0 Warnungen
make ARCH=arm64 LLVM=1 W=1 M=drivers/soc/sunxi modules             ->  LD [M] sun50i-h713-arisc.ko
```

Die einzige Warnung im Verzeichnis kommt aus `cpu_comm/cpu_comm_rpc.c` (`prev_idx set but
not used`) und ist **vorbestehend**. `llvm-18` lag nicht im `PATH` und wurde für den Bau
davorgehängt (`PATH=/usr/lib/llvm-18/bin:$PATH`) - nichts am Rechner geändert.

`checkpatch.pl --no-tree --no-signoff`: **0 errors, 6 warnings** - dieselben sechs wie beim
alten `0091` (Zeilenlänge in der Commit-Message, 5× „acknowledgement"). Keine neue.

`patch -p1 -R --dry-run` gegen den Prüfbau läuft glatt durch: der Patch deckt exakt den
Baum, der gebaut wurde. Genau **eine** `Signed-off-by:`-Zeile, Kopf wie `0049`.
`build/build.sh` nicht aufgerufen, `patches/kernel/series` nicht angefasst.

---

## 6. Abnahmevorschrift für die Hauptsitzung (kopierbar)

Voraussetzung: FIT mit dem neuen `0091` bauen (`build/build.sh`) und nach `tftp/` legen.

```bash
# ---- 0. Vorbedingungen -------------------------------------------------------
ss -ulnp | grep -w :69                       # TFTP muss lauschen; sonst STOPP
echo "$(date +%F_%T) hauptsitzung B-hpd-luecke" > /tmp/claude-1000/h713-board.lock
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

# ---- 3. Karte VOR der Folge lesen (nur SRAM A2, gefahrlos) ------------------
ssh root@192.168.8.141 'for a in 0x00117248 0x00117250 0x00117258; do busybox devmem $a; done'
#   Wort = Byte[+0..+3] little-endian: Byte 2 = Pin, Byte 3 = 1<<Pin.
#   ERWARTET nach Reset/ROM-Vorgabe: 0x01001001 / 0x02012002 / 0x04022004
#   (Port0 Pin0, Port1 Pin1, Port2 Pin2)

# ---- 4. Die EDID-/HPD-Folge aus dem Kernel ----------------------------------
ssh root@192.168.8.141 'time sh -c "echo edid > /sys/kernel/debug/h713-arisc/cmd"'

# ---- 5. Abnahme -------------------------------------------------------------
ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status'
ssh root@192.168.8.141 'dmesg | grep -i "h713-arisc" | tail -40'
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'
ssh user@192.168.8.162 'strings /sys/class/drm/card0-HDMI-A-2/edid | head'
```

**Gutkriterien, alle drei nötig:**

1. `status` zeigt **`portmap: 0,1,2`** - die Karte, wie die Firmware sie hält. Das ist der
   Punkt, den diese Änderung herstellt.
2. `echo edid` gibt **0** zurück und `dmesg` endet mit
   `EDID/HPD-Sequenz auf Port 0 abgeschlossen`.
3. Der Zuspieler meldet **`connected`** und `strings …/edid` enthält **`SGD SX8`**.

**Wenn 1 und 2 grün sind und 3 rot bleibt**, ist die Karte nicht die (einzige) Ursache. Dann
ist der nächste und einzige nötige Messschritt der Registerwert **mit** der geprüften Karte:

```bash
ssh root@192.168.8.141 'busybox devmem 0x07091014; busybox devmem 0x07091b04'
#   ERWARTET dann 0x00000006 / 0x00000007  (= der Stock-Zustand)
#   ACHTUNG: erst NACH ResetEDIDModule lesen -- vorher haengt der SoC (doku/82 §9).
```

Steht dort `0x06` und der Zuspieler bleibt trotzdem `disconnected`, liegt es **nicht** an
der ARISC-Seite, und die Suche gehört auf die Zuspieler-/Kabelseite bzw. an das
Ausgabe-Gate; steht dort etwas anderes als `0x06`, hat ein Dritter den Pin nachgezogen -
dann `busybox devmem 0x0011722c` (die drei Anforderungsfächer) unmittelbar danach lesen.

**Wenn 1 rot ist** (`portmap` ≠ `0,1,2` oder `echo edid` liefert `-110` beim Portmap-
Schritt), hat der Treiber das Rennen erneut verloren und die Prüfung hat es *gefangen* statt
es durchzulassen - das ist das gewünschte Verhalten, nicht das alte Fehlerbild. `dmesg`
nennt dann Port, gelesenen und erwarteten Pin; die Zeile gehört ins Log, denn sie beweist
das Rennen am Gerät.

---

## 7. Stand von Paket B danach

| Teil | Stand |
|---|---|
| Firmware laden, Reset lösen, Notify quittieren | **grün am Gerät** |
| `ResetEDIDModule`, `SetEDIDVersion`, 8 × `UpdateEDID`, `CheckEDIDUpdateStatus`, `RequestEDID` | **grün am Gerät** |
| `HostHDMIMAP` | Handler lief, Karte wurde überschrieben - **Ursache belegt, Fix gebaut, Abnahme offen** |
| `SetEDIDAudioMode`, `SET5VFlag` | laufen durch; in dieser Firmware **wirkungslos** (belegt), Stock schickt sie trotzdem |
| HPD DOWN/UP | mechanisch grün, bewegt bis zum Fix den falschen Pin |
| Zuspieler `connected` aus dem Kernel | **offen bis zur Abnahme** |
