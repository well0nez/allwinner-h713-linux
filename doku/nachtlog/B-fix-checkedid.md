# B - `CheckEDIDUpdateStatus`: Ursache gefunden, Treiber korrigiert (05:58-06:21)

Agent: Paket B, Teilauftrag „Fix `0x0215`". **Board nicht angefasst** - kein `ssh`, kein
`sonoff_ctl`, kein `wandcheck.py`, kein `tio`, kein `scp`, nichts nach `tftp/`. Kein `sudo`,
kein `git`. Nur `0091` bearbeitet; `series` und `build/build.sh` unberührt.

---

## 0. Die Kurzfassung

**Der Treiber hat die Antwort bekommen und weggeworfen.** `a5 00 01 08 00 00 00 00` ist der
**Rahmenkopf**, nicht die Nutzlast:

| Byte | Wert im Fehlerlauf | Bedeutung |
|---|---|---|
| 0 | `a5` | Marker |
| 1 | `00` | `seq` - erste gerahmte Antwort seit dem Firmwarestart |
| 2 | `01` | Typ, für diesen Sender konstant |
| 3 | `08` | **Länge der Nutzlast in Byte** |
| 4..7 | `00 00 00 00` | Füllwort des Kopfes - **keine leere Nutzlast** |

`8 Byte Nutzlast = 2 Wörter`, plus 2 Kopfwörter = **4 Wörter** - exakt die Zahl, die der
Treiber selbst geloggt hat („4 Woerter, 2 uebernommen"). Die gesuchten acht Bytes lagen in
**Wort 2 und 3** und wurden verworfen, weil `edid_status[]` acht Byte groß ist und der alte
Leser die Kopfwörter mitgezählt hat.

**Verdacht 2 („leere Nutzlast, Firmware hat das EDID nicht übernommen") ist damit
widerlegt** - jedenfalls als Schluss aus *dieser* Messung. Die Nullen stammen aus dem Kopf.
Ob die Firmware das EDID übernommen hat, sagt genau das Byte, das der Treiber nie gelesen
hat (Nutzlast[4]); ab jetzt liest und prüft er es.

**Auch die Vergleichszeile im Abnahmelog gehört zu einem anderen Befehl.** Der Dump
`ARM-RX ch1 (8 W): a5 01 01 48 …` hat `seq = 1` und `Länge = 0x48 = 72` - das ist die
Antwort auf **`0x0315 RequestEDID`** (`arisc_edid_init.sh` macht `drain` nach *beiden*
Befehlen). Die Antwort auf `0x0215` in demselben Lauf hätte
`a5 00 01 08 | 00 00 00 00 | ff f8 01 01 01 00 07 fe` gelautet. Dass dort `ff f8 02 41`
statt `ff f8 01 01` steht, ist kein Rahmenversatz-Unterschied, sondern ein anderer
Unterbefehl.

---

## 1. Der Firmware-Beleg (Quelle: `analyse/arisc-frame/full-disasm.txt`)

### 1.1 Wer den Kopf schreibt - `0x81c8`

`0x118e4` (der gerahmte Sender) übergibt Puffer und Länge an `0x8254` mit `r3 = 1`, das
reicht an `0x81c8` weiter. Dort:

```
0081e8  l.sw  4(r1), r6      ; r6 = 0        -> Kopfbyte 4..7 = 0   (Füllwort)
0081f4  l.sb  0(r1), r6      ; r6 = 0xffa5   -> Kopfbyte 0 = 0xa5   (Marker)
0081f8  l.sb  2(r1), r4      ;               -> Kopfbyte 2 = Typ (1)
0081fc  l.lbz r7, 0(r3)      ; r3 = 0x15bc4  -> seq aus dem Kanalkontext
008200  l.sb  1(r1), r7      ;               -> Kopfbyte 1 = seq
00820c  l.sb  0(r3), r7      ;               -> seq++
008210  l.addi r5, r0, 8
00821c  l.jal 0x7d7c         ; send(kanal, stackpuffer, 8, 1000)
008220  l.sb  3(r1), r2      ; Delay-Slot: Kopfbyte 3 = LÄNGE
008230  l.jal 0x7d7c         ; send(kanal, nutzlast, laenge, 1000)
```

`0x7d7c` packt die Bytes **LSB zuerst** in die Msgbox-Wörter (`0x7dd8 l.slli r3, r7, 3`,
`r7 = i & 3`), der ARM liest sie mit `put_unaligned_le32()` also unverändert zurück.

**Auf dem Draht:** `Wort0 = a5 | seq<<8 | typ<<16 | laenge<<24`, `Wort1 = 0`,
**ab Wort 2 die Nutzlast**, `DIV_ROUND_UP(laenge,4)` Wörter. Das ist derselbe BOP-Kopf, den
der ARM auf user1 Port 0 schickt - nur in die Gegenrichtung. Genau deshalb sieht `a5 .. 01 ..`
in beiden Läufen gleich aus: es ist beide Male ein Kopf.

### 1.2 Wer die Nutzlast rahmt - `0x118e4`

`0x1198c` `Nutzlast[0] = 0xff`; `0x11990..0x119c4` summiert `Nutzlast[1..laenge-6]`;
`0x119d4` legt die negierte Summe nach `Nutzlast[laenge-2]`; `0x119e0`
`Nutzlast[laenge-1] = 0xfe`.

Die Prüfsumme deckt bei Länge 8 nur `Nutzlast[1..2]` ab - **nicht** das Zustandsbyte. Der
Treiber rechnet sie nach, meldet Abweichungen aber nur per `dev_dbg` und verwirft den Rahmen
deswegen nicht. Hart geprüft werden Marker, Typ, Länge, `0xff` vorn, `0xfe` hinten.

### 1.3 Was `0x0215` wirklich schickt - `0x1257c`

Sprungtabellen: `classify 0x114e8` → `[0x15b30 + (lo-0x10)*4]`, für `lo = 0x15` ist das
`0x11780`. Dort `hi = 2 → Fall 1`, `hi = 3 → Fall 4`, `hi = 1 → Fall 6`. Zweite Tabelle
`[0x15b48 + fall*4]`: Fall 1 = `0x1257c`, Fall 4 = `0x12618`, Fall 6 = `0x1275c`,
Fall 8 = `0x127f0` (ResetEDIDModule).

`0x1257c` (druckt `"Request EDID Status"`, Formatstring `0x154e0`):

```
0125a0  l.sw  0(r3), r4      ; r3 = 0x17260, r4 = 0 -> Byte 0..3 = 0
0125a4  l.sb  3(r3), r2      ; r2 = 1  -> Nutzlast[3] = 0x01
0125a8  l.sb  2(r3), r2      ;         -> Nutzlast[2] = 0x01
0125b0  l.sw  4(r3), r4      ;         -> Byte 4..7 = 0
0125b8  l.sb  1(r3), r6      ; r6 = 0xfff8 -> Nutzlast[1] = 0xf8
0125bc  l.j   0x127a4
0125c0  l.lbz r2, 2(r2)      ; Delay-Slot: r2 = 0x1723c -> r2 = [0x1723e]
0127a4  l.sb  4(r3), r2      ;         -> Nutzlast[4] = [0x1723e]
0127a8  l.jal 0x118e4
0127ac  l.addi r4, r0, 8     ; Delay-Slot: LÄNGE = 8
```

**Nutzlast = `ff f8 01 01 <ready> 00 <cks> fe`**, `<cks> = -(0xf8+0x01) = 0x07`. Die
Erwartung `ff f8 01 01 …` im Treiber war also richtig - nur an der falschen Stelle
verglichen.

**Nebenbefund, der die zweite Frage stuetzt:** im Vergleichsdump vom 22:04 steht ab
Nutzlast-Offset 5 (Gesamt-Offset 13) `00 ff ff ff ff ff ff 00 5e 78 43 48 21 03` - das sind
Byte fuer Byte die ersten 14 Bytes von `analyse/arisc/hy310-edid.bin`. Damit ist zweierlei
gemessen und nicht hergeleitet: der ARM sieht die Rahmenbytes in **natuerlicher Reihenfolge**
(kein Wort-Swap noetig), und im **Userspace-Lauf hatte die Firmware das EDID uebernommen**.

Zur Abgrenzung: Fall 6 (`0x1275c`, `"Host Read HDMI port Number"`) benutzt denselben
Schwanz `0x127a4`, schreibt aber `Nutzlast[2] = 0x03` und `[0x17246]` als Zustandsbyte. Die
Angabe `[0x117246]` in `doku/82` gehörte zu diesem Befehl, nicht zu `0x0215`; sie ist
korrigiert.

### 1.4 Was `[0x1723e]` und `[0x1723f]` bedeuten

Die Firmware nennt das erste Byte selbst beim Namen: Formatstring `0x15393` =
`"g_Data.bEdidDataReady = %d\n"`, gedruckt in `0x11d88` (`0x11dcc`).

| Byte | Bedeutung | Wer schreibt |
|---|---|---|
| `[0x1723e]` | `g_Data.bEdidDataReady` | `UpdateEDID` Fragment 0..6 **nullen** es (`0x1256c`), **nur Fragment 7** setzt es auf 1 (`0x12570`) und ruft danach `0x11d88` (`0x12608`) |
| `[0x1723f]` | Ausgabe-Gate („edid updated", Formatstring `0x153af`) | `0x11d88` setzt es **ganz am Ende** (`0x11e6c`), nachdem das EDID je Port ins DDC-RAM geschrieben ist; `0x11d88` kehrt sofort zurück, solange `[0x1723e] == 0` (`0x11dac`) |

`ResetEDIDModule` nullt beide (`0x12188`), setzt dann `[0x1723e] = 1` und ruft `0x11d88`
(`0x121b4`) - es veröffentlicht das ROM-Vorgabe-EDID und setzt das Gate dabei gleich wieder.
**Das erklärt, warum das Zustandsbyte „auf frischem Boot schon 1" war**: es war nicht
„unklar", es war der Vorgabe-Datensatz. Für den Gate-Wert *vor* dem ersten
`ResetEDIDModule` gibt es keine Messung.

**Und das Gate ist der Grund, warum ein „erfolgreiches" HPD-UP trotzdem nichts bewirken
kann.** Die Routine, die den Pin treibt (`0x121e4`):

```
012210  l.lbz r2, 3(r2)      ; r2 = 0x1723c -> r2 = [0x1723f]
012218  l.sfnei r2, 0
01221c  l.bf 0x1223c         ; Gate gesetzt -> normal weiter
012230  l.jal 0xbf70         ; sonst: "EDID-HPD %d LOW"   (String 0x153ea)
012238  l.ori r4, r2, 0      ; ... und WERT := 0  -> Pin bleibt low
```

Die Hauptschleife zählt den HPD-Zähler trotzdem auf 0 herunter. Die bisherige Zählerprüfung
im Treiber hätte also eine steigende Flanke gemeldet, die es nicht gab.

---

## 2. Was geändert wurde (`0091`, nur `sun50i-h713-arisc.c`)

| # | Änderung | Beleg |
|---|---|---|
| 1 | **`arisc_unframe()`** neu: zerlegt den Wortstrom von ch1 in Rahmen, prüft Marker/Typ/Länge/`ff`/`fe`, überspringt die **zwei** Kopfwörter und liefert **nur die Nutzlast** - mehrere Rahmen hintereinander. `-EPROTO` bei kaputtem Rahmen oder Rest, `-EMSGSIZE` statt stiller Kürzung. | 1.1, 1.2 |
| 2 | `arisc_send_and_reply()` gibt Nutzlastbytes zurück statt roher Wörter; ein Wortstrom, der nicht in den Puffer passte, ist jetzt `-EMSGSIZE` statt einer `dev_dbg`-Zeile. | 1.1 |
| 3 | `arisc_hdmi_set_edid()` vergleicht `ff f8 01 01` gegen die **Nutzlast**, verlangt Länge 8 **und** `Nutzlast[4] == 1`; die Fehlermeldung nennt zusätzlich `[0x1723e]`/`[0x1723f]` aus dem SRAM. | 1.3, 1.4 |
| 4 | `arisc_hdmi_get_edid()` setzt die **vier** `RequestEDID`-Rahmen nach Fragmentindex wieder zu einem EDID-Block zusammen (Präfix `ff f8 02 41 <index>`, 64 B je Rahmen) statt Kopfbytes als EDID auszugeben. | `0x12618`, `0x126b8`, `0x126c4..0x126f8`, `0x12714` |
| 5 | `arisc_hpd_locked()` prüft **vor** UP/RESET das Gate `[0x1723f]` und liefert `-EIO`, wenn es 0 ist. Keine Warteschleife, keine Pause - ein Zustand, den nur die Ausgaberoutine herstellt. | 1.4 |
| 6 | **Instrumentierung:** `dev_dbg` gibt die rohe Antwort **vollständig mit Wortindex** aus (`Antwort 0x0215 Wort 0: 080100a5  a5 00 01 08`), dazu eine Zeile je Rahmen und die Prüfsummenabweichung. `debugfs status` zeigt neu `edid_ready` und `edid_gate`. | Auftrag |
| 7 | Kommentarblock im Quelltext: das ch1-Rahmenformat mit Adressen; Korrektur `[0x117246]` → `[0x1723e]` und Sender `0x11984` → `0x118e4`. | 1.1-1.4 |

`SRAM_EDID_READY` (`0x1723e`) und `SRAM_EDID_GATE` (`0x1723f`) liegen in **SRAM A2**, das der
Treiber ohnehin abbildet. **Kein `0x0709xxxx` wird gelesen** - die absolute Sperre bleibt
unangetastet, die Reihenfolge-Garantie über `edid_module_ready` bleibt wie sie war.

### Belegt vs. vermutet

**Belegt (Disassembly + Firmware-Strings):** Kopfaufbau und Kopflänge, Lage der Nutzlast ab
Wort 2, Byte-Reihenfolge, Rahmenmarker `ff`/`fe`, Prüfsummenformel und ihre Lücke,
Nutzlast von `0x0215` (inkl. `<ready> = [0x1723e]`), Nutzlast und Rahmenzahl von `0x0315`,
Bedeutung und Schreiber von `[0x1723e]`/`[0x1723f]`, das Erzwingen von `LOW` bei
geschlossenem Gate.

**Vermutet / noch nicht am Gerät gesehen:**

* dass `<ready>` im Treiberlauf tatsächlich `1` sein wird. Das entscheidet erst der
  Abnahmelauf; die Statusantwort war bisher nie gelesen worden. Wenn dort `0` steht, ist
  Verdacht 2 doch zutreffend - dann meldet der Treiber das jetzt **wörtlich** („EDID nicht
  uebernommen: bEdidDataReady = 0 …") statt es hinter `-EPROTO` zu verstecken.
* dass alle vier `RequestEDID`-Rahmen ankommen (80 Wörter durch ein 8 Wörter tiefes FIFO).
  Der Treiber pumpt in einer engen Schleife, das Skript hat nur einmal gedraint - deshalb
  standen dort 8 Wörter. Kommen weniger, meldet der Treiber
  `dev_warn "nur n von 4 Fragmenten angekommen"` und liefert die Bytes, die da waren; er
  scheitert nicht daran.
* der Typ `1` im Kopf: konstant für diesen Sender (`0x8254 r3 = 1`), die Kanalwahl selbst
  steckt im Kontext `0x15bc4+8`. Dass das ch1 ist, ist **gemessen** (beide Läufe), nicht
  aus der Disassembly hergeleitet.

---

## 3. Prüfbau

**Als Prüfbau gekennzeichnet, Originalbaum unberührt.** Kopie des grünen Baums
`mainline/build/linux-6.18.38-49c6dc50…` (der einzige mit dem aktuellen `0091`; der im
Auftrag genannte `…a9eb6d69…` enthält `0091` noch nicht) nach
`…/scratchpad/pruefbau-tree`, Markerdatei `PRUEFBAU-KOPIE-NICHT-DER-ORIGINALBAUM`.

```
make ARCH=arm64 LLVM=1 W=1 drivers/soc/sunxi/sun50i-h713-arisc.o   ->  CC [M]  ... , 0 Warnungen
make ARCH=arm64 LLVM=1 W=1 M=drivers/soc/sunxi modules             ->  LD [M]  sun50i-h713-arisc.ko
```

Die einzige Warnung im Verzeichnis kommt aus `cpu_comm/cpu_comm_rpc.c`
(`prev_idx set but not used`) und ist **vorbestehend**, nicht aus `0091`.

`checkpatch.pl --no-tree --no-signoff`: **0 errors, 6 warnings** - Zeichen für Zeichen
dieselben sechs wie beim alten `0091` (Zeilenlänge in der Commit-Message, 5×
„acknowledgement"). Keine neue.

`patch -p1 -R --dry-run` gegen den Prüfbau-Baum läuft glatt durch: der Patch deckt exakt den
Baum, der gebaut wurde. Genau **eine** `Signed-off-by:`-Zeile, Kopf wie `0049`.

`build/build.sh` wurde **nicht** aufgerufen, `patches/kernel/series` nicht angefasst.
`0093`/`0094` nicht berührt.

---

## 4. Abnahmevorschrift für die Hauptsitzung (kopierbar)

Voraussetzung: FIT mit dem neuen `0091` bauen (`build/build.sh`) und nach `tftp/` legen -
das macht die Hauptsitzung, dieser Agent hat das Board nicht angefasst.

```bash
# ---- 0. Vorbedingungen -------------------------------------------------------
ss -ulnp | grep -w :69                       # TFTP muss lauschen; sonst STOPP
echo "$(date +%F_%T) hauptsitzung B-fix-checkedid" > /tmp/claude-1000/h713-board.lock
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'   # ERWARTET: disconnected

# ---- 1. Kaltstart ------------------------------------------------------------
sonoff_ctl restart --host 192.168.8.179
for i in $(seq 30); do ssh -o BatchMode=yes -o ConnectTimeout=3 root@192.168.8.141 uptime && break; sleep 4; done

# ---- 2. Treiber da, Handshake gruen -----------------------------------------
ssh root@192.168.8.141 'modprobe sun50i-h713-arisc 2>/dev/null; cat /sys/kernel/debug/h713-arisc/status'
#   ERWARTET: startup_notify: acked / arisc: running / edid_firmware: hy310-edid.bin loaded
#   NEU in dieser Datei: edid_ready: / edid_gate:  -- Werte VOR ResetEDIDModule sind nicht
#   vorhergesagt (belegt ist nur, dass edid_ready auf frischem Boot schon 1 war, doku/82);
#   sie sind hier Ausgangswert fuer den Vergleich nach Schritt 6, kein Kriterium.

# ---- 3. dev_dbg scharfstellen (die neue Instrumentierung) -------------------
ssh root@192.168.8.141 "echo 'module sun50i_h713_arisc +p' > /sys/kernel/debug/dynamic_debug/control"

# ---- 4. Prep OHNE Schritt 1 und ohne das alte Modul -------------------------
ssh root@192.168.8.141 "sed -e '/arisc_load.py/d' \
    -e 's#; insmod /root/hy310-arisc-hdmi.ko 2>/dev/null##' \
    /root/prep_after_boot.sh > /root/prep_ohne_arisc.sh && sh /root/prep_ohne_arisc.sh"

# ---- 5. SetSource wie im Nachtplan Abschnitt 1 ------------------------------
ssh root@192.168.8.141 'taskset -c 1 python3 /root/hdmi_seq.py run --phase 4 --i-mean-it \
     --only setsource --source 3 --portmap stock --gap 500 --pre-source-wait 1 --listen-after 3'

# ---- 6. Die EDID-/HPD-Folge AUS DEM KERNEL ----------------------------------
ssh root@192.168.8.141 'time sh -c "echo edid > /sys/kernel/debug/h713-arisc/cmd"'
#   ~11-13 s (10 s davon der HPD-low-Teil). Rueckgabe 0 = alle Schritte quittiert.

# ---- 7. Abnahme -------------------------------------------------------------
ssh root@192.168.8.141 'dmesg | grep -i "h713-arisc" | tail -40'
ssh root@192.168.8.141 'cat /sys/kernel/debug/h713-arisc/status'
ssh user@192.168.8.162 'cat /sys/class/drm/card0-HDMI-A-2/status'
ssh user@192.168.8.162 'strings /sys/class/drm/card0-HDMI-A-2/edid | head'
```

**Erwartete `dmesg`-Zeilen (Schritt 7):**

```
sun50i-h713-arisc 100000.arisc: Antwort 0x0215 Wort  0: 080100a5  a5 00 01 08
sun50i-h713-arisc 100000.arisc: Antwort 0x0215 Wort  1: 00000000  00 00 00 00
sun50i-h713-arisc 100000.arisc: Antwort 0x0215 Wort  2: 0101f8ff  ff f8 01 01
sun50i-h713-arisc 100000.arisc: Antwort 0x0215 Wort  3: fe070001  01 00 07 fe
sun50i-h713-arisc 100000.arisc: Antwort auf 0x0215: 1 Rahmen, 8 Byte Nutzlast
sun50i-h713-arisc 100000.arisc: EDID uebernommen, Status ff f8 01 01 01 00 07 fe, Ausgabe-Gate [0x1723f]=1
sun50i-h713-arisc 100000.arisc: EDID zurueckgelesen (64 B): 00 ff ff ff ff ff ff 00 5e 78 43 48 21 03 00 00
sun50i-h713-arisc 100000.arisc: EDID/HPD-Sequenz auf Port 0 abgeschlossen
```

Die `seq`-Zahl in Wort 0 darf abweichen (sie zählt gerahmte Antworten seit dem
Firmwarestart); Marker `a5`, Typ `01` und Länge `08` nicht.

**`debugfs status`** soll dann zeigen:

```
edid_module: ready
edid_status: ff f8 01 01 01 00 07 fe
edid_ready: 1
edid_gate: 1
```

**Am Zuspieler:** `card0-HDMI-A-2/status` = `connected` (≤ 60 s nach Schritt 6),
`strings …/edid | head` enthält **`SGD SX8`**.

### Falls es doch an der Übernahme liegt (offener Punkt aus Abschnitt 2)

Dann steht im `dmesg` statt „EDID uebernommen" **wörtlich**:

```
EDID nicht uebernommen: bEdidDataReady = 0 statt 1, SRAM [0x1723e]=0 [0x1723f]=<n>
   -- Fragment 7 hat die Ausgabe nicht ausgeloest
```

**Messvorschrift für diesen Fall** (ausführbar ohne Rückfrage, kein Aux-Register, nur SRAM
A2 - auch vor `ResetEDIDModule` gefahrlos):

```bash
# Beide Bytes zwischen den Fragmenten mitlesen: erst die Folge bis Fragment 6, dann 7.
ssh root@192.168.8.141 'busybox devmem 0x0011723c'      # Wort = [1723c][1723d][1723e][1723f]
# -> Byte 2 (Bits 23:16) = bEdidDataReady, Byte 3 (Bits 31:24) = Ausgabe-Gate

# Erwartung laut Firmware (0x1256c / 0x12570 / 0x11e6c):
#   nach ResetEDIDModule           ready = 1, gate = 1   (ROM-Vorgabe veroeffentlicht)
#   nach UpdateEDID Fragment 0..6  ready = 0, gate = 1   (Gate bleibt vom vorigen Lauf stehen)
#   nach UpdateEDID Fragment 7     ready = 1, gate = 1   (0x11d88 lief erneut)
#
# ready bleibt nach Fragment 7 auf 0  -> Fragment 7 kam nicht bis 0x12570:
#     entweder hat classify es nicht angenommen (dann faellt schon der Scratch-Vergleich)
#     oder arg1 war nicht 7 (0x124d4 l.sfeqi r3, 7 -> nur dieser Wert setzt das Flag).
#     Naechster Schritt dann: die acht Fragmente einzeln senden und nach JEDEM
#     0x0011723c lesen; das Fragment, nach dem ready nicht auf 0 geht, ist das,
#     das der Handler nicht als UpdateEDID gesehen hat.
# ready = 1, gate = 0 ist laut 0x11d88 unmoeglich (das Gate wird auf demselben Pfad
#     gesetzt) -- tritt es auf, ist die Disassembly-Lesart falsch und NICHT der Treiber.
```

Ein Vergleichslauf mit dem Userspace-Weg (`analyse/hdmi-seq/arisc_edid_init.sh`) auf
demselben Boot beantwortet die Frage endgültig: läuft der durch und der Treiber nicht, liegt
es an der Nutzlast, die der Treiber schickt, nicht an der Firmware.

---

## 5. Stand von Paket B danach

| Teil | Stand |
|---|---|
| Firmware laden, Reset lösen, Notify quittieren | **grün am Gerät** |
| `ResetEDIDModule`, `HostHDMIMAP`, `SetEDIDVersion`, 8 × `UpdateEDID` | **grün am Gerät** |
| `CheckEDIDUpdateStatus` | Ursache belegt, Fix gebaut, **Abnahme offen** |
| `RequestEDID`, `SetEDIDAudioMode`, `SET5VFlag`, HPD | vom Fix mitbetroffen, **noch nie erreicht** |

`doku/82-arisc-treiber.md` ist nachgezogen: neue Abschnitte **5a** (ch1-Rahmenformat, das
bisher fehlte und die Fehlerursache ist) und **5b** (`[0x1723e]`/`[0x1723f]`), dazu die
Zeilen in den Tabellen zu `lo = 0x15`, `set_edid`, `get_edid`, `hpd` und den Folgeschritten
5, 6 und 11.
