# `sun50i-h713-arisc` — der ARISC-Treiber

**Stand 07.09.2026, 08:30 (Paket B, nach der Board-Abnahme und dem HPD-Befund).** Patch:
`mainline/patches/kernel/0091-soc-sunxi-h713-arisc.patch`. Er **ersetzt**
`0090-soc-sunxi-add-arisc-hdmi-hpd.patch` (unser altes Diagnosemodul
`hy310-arisc-hdmi.ko`). Quellen für alles hier: [68](68-stock-extraktion-arisc-hdcp.md)
(Ladeweg, Rahmenformat, Fall 7), [75](75-handoff-20260907.md) Nachträge 13:35 / 14:55 / 15:25
(EDID-Sequenz, Handshake, Fallen), [77](77-plan-hdmi-integration.md) §2.1 (die API-Vorgabe),
`analyse/hdmi-seq/arisc_edid_init.sh` (die belegte Reihenfolge),
`analyse/arisc-frame/full-disasm.txt` (Disassembly),
`doku/nachtlog/B-abnahme-board.md` und `doku/nachtlog/B-fix-checkedid.md` (die Board-Abnahme
und der `CheckEDIDUpdateStatus`-Fix, aus dem Abschnitt 5a stammt),
`doku/nachtlog/B-hpd-luecke.md` (die Portmap-Quittung, Abschnitt 5c).

---

## 1. Wofür er da ist

Die ARISC (OpenRISC-1000, „AR100", „cpus") besitzt die R\_-Peripherie und damit den
HDMI-Hotplug-Pin, den EDID-Speicher und das DDC-RAM. Der ARM kommt an nichts davon heran —
ein Lesezugriff auf `0x07091014` hängt den SoC hart, solange der Block keinen Takt hat.
Auf Stock lädt der Vendor-BL31 die Firmware; unser Mainline-TF-A tut das nicht. Bis heute
haben wir die Lücke aus dem Userspace gestopft: `arisc_load.py` schrieb das Abbild über
`/dev/mem`, `arisc_edid_init.sh` spielte die EDID-Folge nach.

Der Treiber übernimmt beides:

* er lädt `h713-arisc.bin` per `request_firmware()`, löst den Reset und macht den
  Startup-Handshake, auf den die Firmware wartet,
* er bietet die HDMI-Unterbefehle als **Kernel-API** an
  (`include/linux/soc/sunxi/h713-arisc.h`) — darauf setzt später der V4L2-Treiber
  `sun50i-h713-hdmirx` (Paket E) mit `VIDIOC_S_EDID`/`G_EDID` und der Hotplug-Behandlung auf,
* er lässt die komplette EDID-/HPD-Folge aus debugfs auslösen, damit eine Inbetriebnahme
  ohne Userspace-Helfer auskommt.

**Was weg ist** (und warum es weg darf): der Doorbell-Puls auf `TX_IRQ_EN`, die
Lebensprüfung `main_loop_alive` und die Rettung `unstick`. Alle drei waren Symptome
derselben Ursache — des Startup-Handshakes. `unstick` funktionierte, weil seine Nullwörter
auf Port 3 zufällig genau die Quittung waren, auf die die Firmware wartete
(doku/75, Nachtrag 15:25). Ebenfalls weg: `hpd_delay` (Zähler von Hand setzen) — Diagnose,
kein Dienst.

---

## 2. Der Device-Tree-Knoten

Der Knoten gehört ins SoC-`sun50i-h713.dtsi`, nicht ins Board-DTS: unser Board fährt
cstengers `sun50i-h713-hy200-qz713df-a1.dts` unverändert (doku/60, „Eigene Board-DTS fehlt").
Der Knoten ist im dtsi als **unserer** gekennzeichnet.

```
arisc: arisc@100000 {
	compatible = "allwinner,sun50i-h713-arisc";
	reg = <0x00100000 0x23000>,   /* sram       */
	      <0x03003000 0x100>,     /* msgbox-rx  */
	      <0x03003400 0x100>,     /* msgbox-tx  */
	      <0x07000400 0x4>,       /* reset      */
	      <0x07010110 0xc>;       /* cpus-clk   */
	reg-names = "sram", "msgbox-rx", "msgbox-tx", "reset", "cpus-clk";
	firmware-name = "h713-arisc.bin", "hy310-edid.bin";
	status = "okay";
};
```

**Binding** (der Baum führt keine YAML-Schemata — geprüft: kein Patch der Serie legt etwas
unter `Documentation/devicetree/bindings/` an —, deshalb steht die Beschreibung im Patchkopf
und im Knotenkommentar):

| Eigenschaft | Bedeutung |
|---|---|
| `compatible` | `"allwinner,sun50i-h713-arisc"` |
| `reg`/`reg-names` `"sram"` | SRAM A2 aus ARM-Sicht, `0x00100000` + `0x23000`. Dorthin kommt das Abbild; dieselbe Fensterlage enthält im Betrieb den Nachrichtenpuffer (`0x115f59`), die HPD-Zähler (`0x11722c`) und den Scratch (`0x117320`). ARM-Adresse = ARISC-Adresse + `0x100000`. |
| `"msgbox-rx"` | Msgbox-Bank user0, erster Unterblock: die Kanäle, auf denen die ARISC antwortet (Startup-Notify ch3, Status/EDID ch1). |
| `"msgbox-tx"` | Msgbox-Bank user1, erster Unterblock: Port 0 = HDMI-Empfangspumpe, Port 3 = Standby-Dispatcher (nur die Startquittung). |
| `"reset"` | R_CPUCFG. Bit 0: 0 = Kern angehalten, 1 = Kern läuft. |
| `"cpus-clk"` | die drei R_PRCM-Gatter, die boot0 vor dem Laden setzt („prcm cpus timer clock enable"). |
| `firmware-name` | Index 0 = ARISC-Abbild, Index 1 = Vorgabe-EDID (beide Blöcke, 512 B). |

**Zwei Fenster überlappen bewusst fremde Knoten**, deshalb bildet der Treiber sie mit
`devm_ioremap()` ab und fordert die Region *nicht* exklusiv an:

* die Msgbox-Bänke liegen in der Seite von `cpu_comm@3003000`. `cpu_comm` benutzt
  `+0x164`/`+0x174` (RX vom MIPS) und `+0x864`/`+0x874` (TX zum MIPS) — **kein einziges
  Register ist geteilt**, wir benutzen `+0x60..0x7c` der Bank 0 und der Bank
  `0x03003400`. Eine exklusive Anforderung würde nur dafür sorgen, dass einer der beiden
  Treiber nicht probt.
* die CPUS-Taktgatter liegen im Registerfile von `r_ccu`. Das D1-R-CCU-Modell, das wir
  benutzen, beschreibt sie nicht (sein niedrigstes Gatter sitzt bei `+0x11c`), also gibt
  es keine `clocks`-Referenz, die man stattdessen nehmen könnte.

**Kein `reserved-memory`.** Der Vendor kopiert 32 KiB Abbild-Schwanz nach DRAM
`0x48100000`; das ist bei uns Kernel-Text (`analyse/baseline-20260904-2146/board-baseline.txt`:
`48000000-48e9ffff : Kernel code`). Deshalb `--skip-tail` im alten Prep-Schritt 1 — und
deshalb kopiert der Treiber den Schwanz nicht. Die Firmware ist über alle bisherigen
Kaltstarts ohne ihn hochgekommen (Boots 104–109). Falls je ein Dienst den Schwanz braucht,
muss er zuerst einen Carveout bekommen; der Knotenkommentar sagt das.

---

## 3. Der Ladeweg

Rekonstruiert aus dem Vendor-BL31 (`analyse/arisc/monitor.asm`, Lader `0x5cb8`,
Reset `0x5c38`), unabhängig bestätigt durch den Vendor-3.4-Treiber und durch crust;
im Werkzeug `analyse/arisc-loader/arisc_load.py` seit dem 04.09. in Betrieb.

1. **Takt**: Bit 0 in `0x07010110`, `0x07010114`, `0x07010118` setzen (boot0).
2. **Reset anlegen**: `0x07000400` Bit 0 löschen.
3. **RX-FIFOs leeren** — was ein früheres Leben der Firmware hinterlassen hat, würde sonst
   als Startup-Notify gelesen. (Neu gegenüber dem Skript; unschädlich, weil `cpu_comm`
   andere Register benutzt.)
4. **Abbild**: die ersten `0x23000` Byte nach `0x00100000`, **wortweise**. Ein breiter oder
   schief ausgerichteter Zugriff auf dieses Mapping löst einen Alignment-Fault aus
   (FSC 0x21, mehrfach passiert) — `memcpy_toio()` mit seinen 8-Byte-Stores ist deshalb
   keine Option. **Nicht swappen**: der Datenbus der AR100 dreht jedes Wort, und das
   Vendor-Abbild liegt bereits gedreht vor; Wort little-endian lesen, little-endian
   schreiben, fertig.
5. **Zurückvergleichen**: ab SRAM A2 (`0x00104000`) jedes Wort, im Vektorbereich nur die
   Wörter **auf** den `0x100`-Grenzen (dort ist nur eins je Grenze schreibbar, Hardware
   verwirft den Rest). Abweichung → `-EIO`, der Reset bleibt angelegt.
6. **`struct arisc_para`** (128 B) nach `0x00104008`: alles 0 außer
   `message_pool_phys = 0x00123000` und `message_pool_size = 0x1000` — genau die Werte, mit
   denen das Board läuft.
7. **Reset lösen**: `0x07000400` Bit 0 setzen.

Der BL31 schreibt vorher noch ein Wort nach `0x0709010c`. Bedeutung unbekannt; weder das
Werkzeug noch der Treiber schreibt es.

---

## 4. Der Startup-Handshake — warum der Treiber ohne ihn nichts kann

Disassembly `0xc4b0..0xc548`, Sender `0x75e0`, Warteroutine `0x756c`; gemessen Boots 104–109.

Nach dem Lösen des Resets schiebt die Firmware ihre Notify auf **ARM-RX ch3**
(`FIFO_STAT 0x0300306c`, `MSG_DATA 0x0300307c`): Kopfwort
`state | attr<<8 | type=0x90<<16 | result<<24`, dann `count` (13), dann 13 Datenwörter mit
dem Versionsstring. Danach wartet sie auf **user1 Port 3** (`0x0300347c`) auf die Antwort
des ARM: Kopfwort, dann `count`. Erst danach läuft ihre Hauptschleife, erst dann bedient
sie HDMI-Befehle.

| Fall | Folge (gemessen) |
|---|---|
| kein Leser | Wort 9 blockiert ~100 s (FIFO 8 tief), Boot 106 |
| Leser, keine Quittung | die Quittung blockiert ~100 s, Boot 105 (84 s + 100 s) |
| Quittung | erste Sonde 0,2 s nach Prep beantwortet, Boot 108 |

**Falle:** nur die Notify quittieren — Result-Byte 0 **und** `count > 0`. Eine Quittung auf
die Antwort der ARISC (`fd900200`, result −3 vom Standby-Dispatcher) erzeugt ein Ping-Pong
alle 100 ms (Boot 108). Der Treiber prüft `type == 0x90`, `result == 0`, `count > 0` und
antwortet nur dann.

Scheitert der Handshake, bindet der Treiber zwar (damit `debugfs status` da ist, um
nachzusehen), meldet aber `dev_err` und lässt **jeden** Dienst mit `-ENODEV` scheitern.
Stilles Weitermachen gibt es nicht.

---

## 5. Wie ein Unterbefehl abgeliefert wird

**Weg:** Msgbox user1 **Port 0** → RPM-Pumpe `0x7fd8` → `classify 0x114e8`. Port 3 ist der
Standby-Dispatcher und kennt HDMI nicht (er antwortet auf alles Fremde mit −3); das war
jahrelang die falsche Fährte.

**Form:** Die Pumpe hält `type` und `length` in Registern, nicht im Kontext, und ihr Poller
`0x7bbc` weckt sie schon beim ersten Wort. Kommen die Wörter nicht in einem Rutsch,
ist `length` wieder 0. `classify` liest den Unterbefehl aber aus dem **Puffer** (`0x11508`),
nicht aus der Länge. Also: Nutzlast direkt nach `0x115f59`, dann ein Zwei-Wort-Rahmen mit
Länge 0 (`0xA5 | seq<<8`, dann ein Füllwort). Das ist gegen das Rennen immun, statt zu
hoffen, es zu gewinnen.

**Kein Doorbell.** Die Hauptschleife pollt: `0xc5b4 receive(buf, 0)` liest Port 3,
`0xc5d0 rpm_poll()` liest Port 0, und die Startwarteroutine `0x756c` pollt Port 3 ebenfalls.
Der `TX_IRQ_EN`-Puls des alten Moduls hatte nichts zu wecken (doku/77 §2.1: 3/3 belegt).

**Nutzlast immer ganz schreiben.** Nur `UpdateEDID` (hi = 1) kopiert alle 65 Byte ab
Nutzlast[2]; ein kurzer Befehl würde sonst den Schwanz des vorigen erben. Der Treiber
schreibt deshalb stets alle 67 Puffer-Bytes, nullaufgefüllt. (Die frühere Fassung dieses
Absatzes schrieb „*immer* 65 Byte" — falsch, siehe die Fallunterscheidung in der
Quittungstabelle und in `arisc_expected_scratch()`.)

### 5c. Der Puffer gehört der Firmware, bis sie ihn gelesen hat

Der Scratch-Vergleich belegt, dass der **Gruppenhandler** `0x11550` gelaufen ist — sein
`memset(0x17320, 0, 0x41)` steht ganz vorn, *vor* der Verzweigung auf `hi`. Für drei der
fünf Zweige ist das zugleich der Beleg, dass die Firmware mit dem Pumpen-Puffer fertig
ist, denn sie nehmen ihre Argumente mit in den Scratch und rufen den Dispatcher mit einem
Zeiger **auf den Scratch**:

| `hi` | Befehl | was der Zweig aus dem Puffer holt | Puffer danach frei? |
|---|---|---|---|
| 1 | UpdateEDID | 65 B ab Nutzlast[2] → Scratch (`0x1160c`) | ja |
| 2 | PullHotPlug | Nutzlast[2], [3] → Scratch (`0x1164c`) | ja |
| 3 | SetEDIDVersion | Nutzlast[2] → Scratch (`0x11678`) | ja |
| 0x20 | ResetEDIDModule | nichts | ja |
| 4 / 5 | SET5VFlag / SetEDIDAudioMode | nichts — der Unter-Dispatch `0x11568` kennt nur 0, 1, 2, 3 und 0x20 und kehrt bei allem anderen bei `0x117f8` zurück; die beiden Befehle sind in **dieser** Firmware wirkungslos | ja |
| **0** | **HostHDMIMAP** | Nutzlast[2..4] bei `0x115bc..0x115d4` für die Logzeile, danach **Log-Aufruf** `0x115d8`, und **erst dann** liest `0x11f94` dieselben drei Bytes noch einmal (`0x11fac`, `0x11fb4`, `0x11fc0`) und legt sie in die Portmap | **nein** |

`HostHDMIMAP` ist damit der einzige Unterbefehl, bei dem der Scratch-Vergleich **zu früh**
fertig ist. Wer den nächsten Befehl schnell genug nachschiebt, überschreibt die Karte,
bevor die Firmware sie gelesen hat. Der Treiber wartet dort deshalb auf die **Portmap
selbst** (`0x17248`, Schrittweite 8, Byte +2 = Pin, Byte +3 = 1 << Pin) — die einzige
Stelle, die nur `0x11f94` schreibt. Belegt und gemessen: `doku/nachtlog/B-hpd-luecke.md`.

#### 5c-1. Die Portmap-Sätze: wer schreibt, wer liest, und was das ROM vorgibt

Ein Satz ist 8 Byte lang, drei Sätze liegen ab `0x17248`. Genau **zwei** Stellen im Image
schreiben sie (`grep 0x7248 0x724a 0x724b` über die Disassembly findet keine dritte):

| Adresse | wann | schreibt |
|---|---|---|
| `0x11e88` | **einmal**, aus der Firmware-Init `0x10f0c` | Byte +0 … +4 aller drei Sätze aus der ROM-Tabelle `0x15edc` |
| `0x11f94` | der Schwanz des `HostHDMIMAP`-Handlers | Byte +2, +3, +4 aller drei Sätze aus der Nutzlast |

**`ResetEDIDModule` setzt die Karte *nicht* zurück** — `0x127f0 → 0x120f0` fasst
`0x17248…` nicht an. Nach einem Kaltstart steht dort also, was das ROM vorgibt, und danach
nur noch, was `HostHDMIMAP` hineingeschrieben hat.

Und die ROM-Vorgabe ist **die Identität**:

```
0x15edc  01 10 00 01   Port 0: Maske 0x01, Tag 0x10, Pin 0, 1<<Pin = 0x01
0x15ee4  02 20 01 02   Port 1: Maske 0x02, Tag 0x20, Pin 1, 1<<Pin = 0x02
0x15eec  04 30 02 04   Port 2: Maske 0x04, Tag 0x30, Pin 2, 1<<Pin = 0x04
```

kopiert von `0x11ef8..0x11f3c` (Byte 0…4, Schrittweite 8, Abbruch bei Quelle `0x15ef4`).

**Das ist der Grund, warum die erste Fassung der Portmap-Prüfung nichts bewiesen hat.**
Die Stock-Folge fordert `HostHDMIMAP 0,1,2` an — und `0,1,2` steht bei frisch gestarteter
Firmware bereits da. Ein Warten auf „die Sätze tragen 0,1,2" ist damit in der **ersten**
Runde erfüllt, ob der Handler gelaufen ist oder nicht; `portmap: 0,1,2` in debugfs ist
aus demselben Grund **kein** Nachweis. Deshalb belegt der Treiber Byte +2 und +3 aller
drei Sätze **vor** dem Senden mit `0xff` — ein Wert, den weder ein Pin (0/1/2) noch ein
`1 << Pin` (1/2/4) annehmen kann und den auch die Nutzlast des Folgebefehls
(`SetEDIDVersion 2` → `11 03 02 00 …`) nicht hinterlässt — und liest die Vorbelegung
zurück, bevor überhaupt gesendet wird. Landet sie nicht, wird der Befehl **nicht**
gesendet: eine Prüfung, die nicht scheitern kann, ist schlechter als keine. Scheitert die
Prüfung, werden die Sätze wieder auf den vorgefundenen Stand gesetzt.

Dass `0xff` dort für die ~1 ms gefahrlos stehen darf, ist kein Vertrauen, sondern eine
vollständige Leserliste:

| Byte | wer liest | mit `0xff` |
|---|---|---|
| +0 Maske | Publish-Schleife `0x11dec` | nicht belegt |
| +1 Tag | `0x11bb0` (Ausgabe je Port) | nicht belegt |
| **+2 Pin** | Pin-Treiber `0x121e4` (`0x12220`) | Dispatch kennt 0/1/2 (`0x12240`–`0x1225c`), alles andere fällt auf `0x12304`: Logzeile, dann `0x07091014` mit **demselben** bei `0x12248` gelesenen Wert zurückschreiben. Ein Puls im Fenster geht **verloren**, er wandert nicht auf den falschen Pin. |
| **+3 1<<Pin** | `0x11cac` (`0x11cc8`), `0x11a04` (`0x11a4c`) | beide nur aus der Publish-Routine `0x11d88` bzw. dem Modul-Reset `0x120f0` erreichbar — also nur aus einem Unterbefehl, und die serialisiert der Treiber-Mutex. `0x11cac` merkt den Unterschied nicht einmal: es ODERt das Byte in einen Akku und prüft Bit 0 (`0x11d28`), was eine gesunde Karte genauso setzt. |
| +4 Rückwärts | Lookup `0x11c64` (`0x11c70`): Pin → Port | **bleibt unangetastet**, sonst antwortete der Lookup „kein solcher Port". Dieselben drei Stores schreiben es (`0x11fc4`), die zwei belegten Bytes decken es mit ab. |

Der einzige Leser, der **ohne** einen unserer Befehle laufen kann, ist `0x121e4` über die
Hauptschleife `0x10f50..0x10f7c`, und zwar genau dann, wenn ein Hotplug-Zähler auf 1
heruntergelaufen ist. `arisc_hdmi_set_portmap()` lehnt deshalb mit `-EBUSY` ab, solange
einer der drei Zähler `0x1722c+port` ungleich 0 ist, statt sich auf die harmlose
Fehlerkante zu verlassen.

### Quittungen — jede Wartezeit endet in einem Fehler

| Gruppe | Beleg, dass der Befehl angekommen ist | Fehler |
|---|---|---|
| `lo = 0x11` (Reset, Version, UpdateEDID, AudioMode, 5V, HotPlug) | Handler `0x11550` nullt den Scratch `0x117320` und kopiert je nach `hi` unterschiedlich viel hinein. Der Treiber füllt den Scratch vorher mit dem **Komplement** des **erwarteten** Inhalts und wartet, bis alle 65 Byte stimmen. Ein Zufallstreffer ist damit ausgeschlossen. | `-ETIMEDOUT` nach 500 ms |
| `lo = 0x11, hi = 0` (HostHDMIMAP) | **zusätzlich** die Portmap `0x17248 + Port*8`: Byte +2 = angeforderter Pin, Byte +3 = `1 << Pin`, für alle drei Ports — **vorher mit `0xff` belegt**, sonst prüft der Vergleich gegen die ROM-Vorgabe, die schon `0,1,2` ist. Siehe 5c-1. | `-EBUSY`, solange ein Hotplug-Zähler läuft; `-EIO`, wenn sich die Sätze nicht vorbelegen lassen (dann wird **nicht** gesendet); `-ETIMEDOUT` nach 500 ms — die Logzeile nennt Satz, gelesenen und erwarteten Pin/Bit und unterscheidet „Vorbelegung steht noch" (Handler nie gelaufen) von „falscher Pin" (Handler lief, Puffer war überschrieben) |
| `lo = 0x15` (CheckEDIDUpdateStatus, RequestEDID) | Antwortrahmen auf ARM-RX **ch1**, Aufbau siehe 5a. Vorher wird ch1 geleert, damit keine alte Antwort als die neue gelesen wird. | `-ETIMEDOUT` nach 2000 ms, `-EPROTO` bei kaputtem Rahmen |
| `PullHotPlug` zusätzlich | Zweistufiger Zähler `0x11722c+port`: Timer-ISR `0x10db4` zählt bis 1 herunter, **nur die Hauptschleife** `0x10f30` setzt ihn auf 0 und hebt den Pin. Also ist „Zähler 0" der Beleg, dass der Pin wirklich bewegt wurde; RESET muss unterwegs über ~84 gehen. | `-ETIMEDOUT` / `-EIO` nach 2000 ms |
| vor jedem Senden | `FIFO_STAT` user1 Port 0 muss 0 sein — ist er es nach 100 ms nicht, holt die Pumpe nicht ab | `-EBUSY` |

Der alte „Sonde 15/17 genullt"-Test war ein Sonderfall dieses Vergleichs und galt nur,
solange die Nutzlast zufällig Nullen enthielt — bei den EDID-Fragmenten war er sinnlos
(doku/75, Nachtrag 14:55, Befund 4). Der Byte-für-Byte-Vergleich ersetzt ihn.

### 5a. Das Rahmenformat auf ARM-RX ch1 — der Kopf gehört nicht zur Nutzlast

Das fehlte hier bisher, und genau daran ist die erste Board-Abnahme gescheitert
(`doku/nachtlog/B-fix-checkedid.md`). Die `0x15`-Gruppe antwortet **nicht** über den
Scratch, sondern mit einem Rahmen — und dieser Rahmen hat einen **Kopf, den der Leser
überspringen muss**.

Zwei Stufen, beide aus `analyse/arisc-frame/full-disasm.txt`:

1. **Nutzlast einrahmen** — `0x118e4`. Bekommt Puffer und Länge, schreibt
   `Nutzlast[0] = 0xff` (`0x1198c`), die Prüfsumme nach `Nutzlast[len-2]`
   (`0x119d4`, negierte Summe über `Nutzlast[1..len-6]`, `0x11990..0x119c4`) und
   `Nutzlast[len-1] = 0xfe` (`0x119e0`). Danach `0x8254` mit `r3 = 1` (Typ) →
   `0x81c8`.
2. **Rahmenkopf senden** — `0x81c8`. Baut **acht Byte** auf dem eigenen Stack und
   schickt sie als eigene Nachricht **vor** der Nutzlast:

   | Adresse | Wirkung |
   |---|---|
   | `0x081f4` | Byte 0 = `0xa5` (Marker) |
   | `0x08200` | Byte 1 = `seq` aus `[0x15bc4]`, danach `0x0820c` `seq++` |
   | `0x081f8` | Byte 2 = Typ, für diesen Sender konstant `1` |
   | `0x08220` | Byte 3 = **Länge** der folgenden Nutzlast in Byte |
   | `0x081e8` | Byte 4..7 = `0` — das Füllwort |
   | `0x0821c` | `send(kanal, kopf, 8)` |
   | `0x08230` | `send(kanal, nutzlast, len)` |

   `0x7d7c` packt Bytes **LSB zuerst** in die Wörter, der ARM liest also mit
   `put_unaligned_le32()` genau die Bytefolge zurück, die die Firmware geschrieben hat.

Auf dem Draht steht damit:

```
Wort 0   a5 | seq<<8 | typ<<16 | laenge<<24
Wort 1   00 00 00 00                     <- Füllwort, KEINE Nutzlast
Wort 2   Nutzlast, <laenge> Byte, DIV_ROUND_UP(laenge,4) Wörter
```

Das ist derselbe BOP-Kopf, den der ARM auf user1 Port 0 schickt — nur in die andere
Richtung. **Die Nutzlast beginnt bei Wort 2.**

| Unterbefehl | Firmware | Länge | Nutzlast |
|---|---|---|---|
| `0x0215` CheckEDIDUpdateStatus | `0x1257c` („Request EDID Status") | 8 | `ff f8 01 01 <ready> 00 <cks> fe`; Konstanten `0x125a0..0x125b8`, `<ready>` = `[0x1723e]`, gesetzt im Delay-Slot `0x125c0`, abgelegt vom gemeinsamen Schwanz `0x127a4` |
| `0x0315` RequestEDID | `0x12618` („Read EDID. MSG=") | 4 × `0x48` | je Fragment `ff f8 02 41 <index 0..3> <64 B DDC-RAM> 00 <cks> fe`; Quelle `0x07091c00 + port*0x100 + frag*0x40` (`0x126c4..0x126f8`), Schleifenende `0x12714` |
| `0x0115` (Host Read HDMI port Number) | `0x1275c` | 8 | `ff f8 03 01 <[0x17246]> 00 <cks> fe` — **nicht** dieselbe Konstante wie `0x0215`; der Treiber setzt den Befehl nicht ab |

**Die Prüfsumme deckt nicht alles ab** (bei Länge 8 nur `Nutzlast[1..2]`, also gerade
nicht das Zustandsbyte). Der Treiber rechnet sie nach, meldet eine Abweichung aber nur
per `dev_dbg` und verwirft den Rahmen deswegen nicht — eine Prüfung, die die
interessanten Bytes nicht abdeckt, darf keinen sonst wohlgeformten Rahmen ablehnen.
Hart geprüft werden Marker, Typ, Länge, `0xff` vorn und `0xfe` hinten.

### 5b. Die zwei EDID-Bytes: `[0x1723e]` Bereitschaft, `[0x1723f]` Ausgabe-Gate

| Byte | Vendor-Name | Wer setzt es |
|---|---|---|
| `[0x1723e]` (ARM `0x11723e`) | `g_Data.bEdidDataReady` (Firmware druckt den Namen selbst, Formatstring `0x15393` bei `0x11dcc`) | `UpdateEDID` Fragment 0..6 **nullt** es (`0x1256c`), **nur Fragment 7** setzt es auf 1 (`0x12570`) und ruft danach die Ausgaberoutine `0x11d88` (`0x12608`) |
| `[0x1723f]` (ARM `0x11723f`) | „edid updated"-Gate | `0x11d88` setzt es ganz am Ende (`0x11e6c`), **nachdem** das EDID je Port ins DDC-RAM geschrieben wurde; `0x11d88` kehrt sofort zurück, solange `[0x1723e] == 0` (`0x11dac`) |

`ResetEDIDModule` nullt beide (`0x12188`), setzt dann `[0x1723e] = 1` und ruft `0x11d88`
(`0x121b4`) — es veröffentlicht also das ROM-Vorgabe-EDID und setzt dabei das Gate gleich
wieder. **Damit ist erklärt, warum das Zustandsbyte „auf frischem Boot schon 1" war** (doku/75
und die frühere Fassung dieses Abschnitts): es war nicht unklar, es war der Vorgabe-Datensatz.
Für den Gate-Wert *vor* dem ersten `ResetEDIDModule` gibt es keine Messung.

**Warum das Gate zählt:** die Routine, die den Pin treibt (`0x121e4`), liest `[0x1723f]`
zuerst (`0x12210`) und überschreibt bei Null ihr eigenes Wert-Argument mit 0 (`0x12238`),
nachdem sie `EDID-HPD %d LOW` gedruckt hat (Formatstring `0x153ea`). Der Pin bleibt dann
low — **während die Hauptschleife den Zähler trotzdem auf 0 herunterzählt**. Die
Zählerprüfung allein belegt also keine steigende Flanke. Der Treiber liest deshalb vor
`PullHotPlug` UP/RESET das Gate aus dem SRAM und liefert `-EIO`, wenn es 0 ist. Beide
Bytes stehen außerdem in `debugfs status` (`edid_ready`, `edid_gate`) — beides SRAM A2,
kein Aux-Register, also jederzeit gefahrlos lesbar.

---

## 6. Die Kernel-API

`include/linux/soc/sunxi/h713-arisc.h`. Alle Funktionen dürfen schlafen, nehmen einen
treiberinternen Mutex und liefern echte Fehler. Ohne `CONFIG_SUN50I_H713_ARISC` gibt es
Inline-Attrappen, die `-ENODEV` liefern.

| Funktion | Unterbefehl | Semantik / Fehlerfälle |
|---|---|---|
| `arisc_hdmi_reset_edid()` | `0x2011` | Initialisiert das EDID-Modul und den HDMI-Aux-Block. **Muss als erstes laufen** (Abschnitt 8). `-ENODEV` (Firmware läuft nicht), `-ETIMEDOUT`, `-EBUSY`. |
| `arisc_hdmi_set_portmap(map, 3)` | `0x0011` | Port-Tabelle; Stock schickt `0,1,2` (`arg1=map[0]`, `arg2=map[1]`, `data[0]=map[2]`). `-EINVAL` bei anderer Länge, sonst wie oben, zusätzlich `-EAGAIN`. |
| `arisc_hdmi_set_edid(edid, 512)` | `0x0311` + 8 × `0x0111` + `0x0215` | Version 2 setzen, acht Fragmente à 64 B hochladen, Status prüfen. `-EINVAL` bei Länge ≠ 512. `-EPROTO`, wenn die **Nutzlast** der Statusantwort nicht `ff f8 01 01 <ready>` ist **oder** `<ready> ≠ 1` — dann hat Fragment 7 die Ausgabe nicht ausgelöst (Abschnitt 5b). |
| `arisc_hdmi_get_edid(port, buf, len)` | `0x0315` | Rücklese aus dem DDC-RAM. Die Antwort sind **vier** Rahmen à 64 B; der Treiber setzt sie nach dem Fragmentindex wieder zusammen und liefert die Zahl der abgelegten Bytes (256 bei vollem Block, weniger wenn `len` kleiner ist). `-EPROTO` bei falschem Rahmenpräfix oder falscher Reihenfolge. **Nicht** in doku/77 §2.1 — begründet in Abschnitt 7. |
| `arisc_hdmi_audio_mode(port, mode)` | `0x0511` | Belegt ist nur `(0, 0)`; die Argumente gehen durch, wie die Firmware sie definiert. |
| `arisc_hdmi_5v(port, on)` | `0x0411` | 5-V-Flag. |
| `arisc_hdmi_hpd(port, action)` | `0x0211` | `UP` (1) / `DOWN` (2) / `RESET` (3), mit Zählerprüfung wie oben. `UP`/`RESET` liefern vorab `-EIO`, wenn das Ausgabe-Gate `[0x1723f]` 0 ist — dann zwingt die Firmware den Pin ohnehin low (Abschnitt 5b). |
| `arisc_hdmi_edid_init(port, edid, len)` | die ganze Folge | Abschnitt 8. `edid = NULL` nimmt `hy310-edid.bin`; fehlt die Datei: `-ENOENT`. |

**Gemeinsame Rückgabewerte:** `0` = die Firmware hat den Befehl nachweislich verarbeitet.
`-ENODEV` = kein Treiber gebunden oder Handshake gescheitert. `-EAGAIN` = `reset_edid()`
fehlt noch. `-EBUSY` = Msgbox-FIFO nicht leer. `-ETIMEDOUT` = keine Quittung/keine Antwort
in der Frist. `-EPROTO` = Antwort kam, sah aber nicht aus wie erwartet. `-EIO` = Befehl
angekommen, Wirkung ausgeblieben (nur HPD-RESET). `-EINVAL` = Argumentfehler.

### 7. Abweichungen von doku/77 §2.1 — und warum

* **`arisc_hdmi_set_edid()` hat kein `port`-Argument.** Der `UpdateEDID`-Handler ist nicht
  portbezogen: der Speicher ist global, und Fragment 7 löst die Ausgabe **für alle Ports**
  aus (`0x12608`). Ein Port-Argument wäre eine Behauptung, die die Firmware nicht deckt.
* **`arisc_hdmi_set_edid()` nimmt beide Blöcke auf einmal** statt „block". Die Firmware gibt
  überhaupt erst dann ein EDID aus, wenn Fragment 7 da ist: jedes Fragment 0..6 nullt das
  Bereitschaftsbyte (Delay-Slot `0x1256c`), nur Fragment 7 setzt es. Ein Aufruf je Block
  könnte die Bedingung gar nicht erfüllen.
* **`arisc_hdmi_get_edid()` kommt hinzu.** doku/77 §2.2 verlangt `VIDIOC_G_EDID` „liest per
  `RequestEDID` zurück", und die Stock-Folge setzt den Befehl ohnehin ab.
* **`arisc_hdmi_edid_init()` kommt hinzu.** Die Reihenfolge ist keine Konvention, sondern
  das, was die Firmware annimmt. Sie über die Aufrufer zu verteilen lädt zum Umsortieren
  ein; Paket E braucht genau diese eine Folge beim Probe.

---

## 8. Die EDID-/HPD-Folge

1:1 aus `analyse/hdmi-seq/arisc_edid_init.sh`, belegt am 06.09. um 14:55 und 15:25
(Läufe 104 / Boot 109): ThinkPad meldet danach `connected`, 256-B-EDID, `ELD monitor SGD SX8`,
beide Prüfsummen 0.

| # | Schritt | Unterbefehl | Argumente | Warten — worauf, und warum |
|---|---|---|---|---|
| 1 | ResetEDIDModule | `0x2011` | 0, 0 | Scratch-Vergleich. **Muss durch sein**, bevor irgendwer `0x0709xxxx` liest. |
| 2 | HostHDMIMAP | `0x0011` | 0, 1, data 2 | Scratch-Vergleich **und** Rücklese der Portmap `0x17248`, die vorher mit `0xff` belegt wird (Abschnitte 5c, 5c-1) — ohne die zweite Prüfung überschreibt Schritt 3 die Karte, bevor die Firmware sie liest, und ohne die Vorbelegung prüft die zweite Prüfung nur die ROM-Vorgabe, die schon `0,1,2` ist. Der MAP-Wert landet als Physical Address im EDID (Byte 168), und Byte +2 jedes Satzes ist der HPD-Pin, den `0x121e4` später bewegt. |
| 3 | SetEDIDVersion | `0x0311` | 2, 0 | Scratch-Vergleich. |
| 4 | UpdateEDID ×8 | `0x0111` | `arg1` = Fragment 0..7, `arg2` = Datenbyte 0, `data` = Bytes 1..63 | Scratch-Vergleich je Fragment. Fragmente 0..3 = Block 0 (`0x15cdc`), 4..7 = Block 1 (`0x15ddc`). Ablage **plain**, kein Swap. |
| 5 | CheckEDIDUpdateStatus | `0x0215` | 0, 0 | Antwort auf ch1, **Nutzlast ab Wort 2** (Abschnitt 5a): `ff f8 01 01 <ready> 00 <cks> fe`. `ff`/`fe`/Prüfsumme sind der Rahmen des Senders `0x118e4`, `f8 01 01` sind Konstanten aus `0x125a0..0x125b8`, `<ready>` ist `[0x1723e]` = `g_Data.bEdidDataReady` (Abschnitt 5b). Der Treiber verlangt `<ready> = 1`. |
| 6 | RequestEDID | `0x0315` | Port, 0 | Antwort auf ch1: **vier** Rahmen à `0x48` Byte Nutzlast, je `ff f8 02 41 <index> <64 B> 00 <cks> fe`, Rücklese aus dem DDC-RAM `0x07091c00`. Im Skript stand hier `--settle 1.5` gegen 0.6 sonst; im Treiber ist es dieselbe Frist wie sonst (2000 ms), also großzügiger als das Skript. |
| 7 | SetEDIDAudioMode | `0x0511` | 0, 0 | Scratch-Vergleich. |
| 8 | SET5VFlag | `0x0411` | Port, 1 | Scratch-Vergleich. |
| 9 | PullHotPlug DOWN | `0x0211` | Port, 2 | Scratch-Vergleich. Der Handler zieht den Pin sofort low, der Zähler bleibt unberührt — mehr gibt es hier nicht zu beobachten. |
| 10 | **`HPD_DOWN_MS` warten (200 ms)** | — | — | Siehe unten. |
| 11 | PullHotPlug UP | `0x0211` | Port, 1 | Ausgabe-Gate `[0x1723f]` vorab, Scratch-Vergleich **und** Zähler zurück auf 0. Der Zähler allein genügt nicht: bei geschlossenem Gate zählt die Hauptschleife ihn herunter, `0x121e4` hält den Pin aber trotzdem low (Abschnitt 5b). |

**Die 10 Sekunden.** Fundstelle: `analyse/hdmi-seq/arisc_edid_init.sh`, vorletzte Zeile
(`snd 0x0211 0 2 PullHotPlug-DOWN; st; sleep 10`), und doku/75 Nachtrag 14:55
(„`0x0211 PullHotPlug 2 (DOWN)` → 10 s → `PullHotPlug 1 (UP)`"). Das ist **kein Workaround
und keine Drosselung**: eine HDMI-Senke liest ihr EDID neu, wenn sie den HPD-Pin lange genug
low sieht — die HDMI-Spezifikation verlangt mindestens 100 ms. 10 s war der Wert, mit dem
die Kette an diesem Board dreimal reproduziert wurde; ihn zu kürzen ist eine **Messung**
(Kandidat für einen Board-Slot), keine Aufräumarbeit. Er steht als
`HPD_DOWN_MS` an einer Stelle im Treiber.

> **Korrektur 07.09.: gemessen, 200 ms genügen** — für den Wiederanlauf
> ([`nachtlog/M4-hpd-dauer.md`](nachtlog/M4-hpd-dauer.md)) und für den EDID-Fall
> ([`nachtlog/A2-hpd-dauer-edid.md`](nachtlog/A2-hpd-dauer-edid.md)); 200 ist zugleich der
> **Stock-Wert** (`SetHPDTimeInterval 0xC8`). **`HPD_DOWN_MS` steht auf 200**
> (`0091` Z. 566, `msleep(HPD_DOWN_MS)` Z. 1923), die ganze Sequenz braucht damit
> **17,65 s statt 28,8 s**. Der Absatz oben bleibt als Herkunft stehen — die 10 s waren nie
> gemessen, sondern übernommen. Die Rückfallebene `analyse/hdmi-seq/arisc_edid_init.sh`
> hält weiterhin `sleep 10`, aus Vorsicht und ohne Lauf dagegen.

Die übrigen Wartezeiten im Skript (`--settle 0.6` bzw. `1.5`) waren **Beobachtungsfenster
des Werkzeugs**, keine Protokollpausen: das Werkzeug hatte kein Fertig-Signal und schaute
deshalb eine feste Zeit lang zu. Der Treiber hat ein Fertig-Signal (Abschnitt 5) und wartet
darauf statt auf die Uhr — er ist damit schneller *und* strenger als das Skript.

**Eine Einschränkung dazu, die das Board am 07.09. erzwungen hat:** bei **Schritt 2**
war das Beobachtungsfenster des Skripts unbeabsichtigt tragend. Der Scratch-Vergleich ist
dort schon fertig, während die Firmware die Karte noch nicht aus dem Pumpen-Puffer gelesen
hat (Abschnitt 5c); die 600 ms des Skripts überdecken das, die ~1 ms des Treibers nicht.
Das ist keine Protokollpause, sondern eine zu früh gesetzte Quittung — und wird auch nicht
mit einer Pause behoben, sondern mit der Rücklese der Portmap.

---

## 9. Die Reihenfolge-Garantie für `0x0709xxxx`

`0x07091014` (und die Nachbarschaft) vom ARM zu lesen, **bevor** die ARISC
`ResetEDIDModule` verarbeitet hat, hängt den SoC hart — kein Oops, keine Konsole. Das hat
am 06.09. drei Boards gekostet (doku/75, „Warum heute vier Boards starben").

Im Treiber ist das keine Kommentarzeile, sondern Bauweise:

1. Der Treiber bildet **kein einziges Register in `0x0709xxxx` ab**. Der Knoten nennt die
   Adresse nicht, also gibt es nichts, worüber ein Fehlgriff laufen könnte.
2. `arisc_get(need_edid_module = true)` liefert `-EAGAIN`, solange
   `edid_module_ready` nicht gesetzt ist. Gesetzt wird es **nur** von einem erfolgreichen
   `arisc_hdmi_reset_edid()`. Damit scheitert jeder andere Einstiegspunkt — `set_edid`,
   `get_edid`, `portmap`, `5v`, `audio_mode`, `hpd` —, bis der Reset durch ist.
3. Ein Verbraucher (Paket E), der den Aux-Block anfassen will, muss also `reset_edid()`
   aufrufen und dessen Rückgabewert auswerten; ohne das bekommt er von diesem Treiber
   nichts, worauf er aufbauen könnte.

---

## 10. debugfs

`/sys/kernel/debug/h713-arisc/`

* **`status`** (lesen) — fasst die Hardware nur lesend an:

  ```
  startup_notify: acked
  firmware_version: projector-tv303-android11-v1.3-3-g293ff69
  arisc: running
  edid_module: ready
  edid_firmware: hy310-edid.bin loaded
  edid_status: ff f8 01 01 01 ...
  edid_ready: 1
  edid_gate: 1
  portmap: 0,1,2
  hpd_counter: 0 0 0
  rpm_state: 0
  fifo_tx: port0=0 port3=0
  fifo_rx: ch0=0 ch1=0 ch2=0 ch3=0
  last_command: ...
  ```

  `portmap:` ist die Karte, **wie die Firmware sie hält** (Byte +2 der drei Sätze ab
  `0x17248`), nicht die, die der Treiber geschickt hat. Steht dort etwas anderes als
  `0,1,2` — vor allem `2,0,0` —, bewegt jeder `PullHotPlug` den falschen Pin, und die
  Zeile nennt die Nutzlast, die die Firmware stattdessen gelesen hat.

  **`portmap: 0,1,2` ist umgekehrt *kein* Beleg.** Genau das steht nach jedem Kaltstart
  schon aus der ROM-Vorgabe da (Abschnitt 5c-1), auch wenn `HostHDMIMAP` nie verarbeitet
  wurde. Ob der Handler gelaufen ist, sagt allein der **Rückgabewert** des Befehls
  (`echo portmap …` bzw. `echo edid`) — die Datei zeigt Zustand, kein Urteil.

  Alles in `status` liegt in SRAM A2 — kein `0x0709xxxx`, also jederzeit gefahrlos lesbar.

* **`cmd`** (schreiben; lesen gibt das Ergebnis des letzten Befehls):

  | Zeile | Wirkung |
  |---|---|
  | `edid` bzw. `edid <port>` | ganze Folge aus Abschnitt 8 (~2,5 s, davon 200 ms HPD low) |
  | `reset-edid` | nur `ResetEDIDModule` |
  | `portmap` bzw. `portmap a b c` | HostHDMIMAP (ohne Argumente: `0 1 2`) |
  | `hpd <port> up\|down\|reset` | PullHotPlug |
  | `5v <port> on\|off` | SET5VFlag |
  | `get-edid <port>` | RequestEDID, erste 16 Byte ins Kernel-Log |

  Ein Fehler kommt als Fehlercode des `write()` zurück (`echo` meldet ihn), nicht nur im Log.

---

## 11. Firmware-Dateien

| Datei am Board | Quelle im Baum | Größe | SHA-256 |
|---|---|---|---|
| `/lib/firmware/h713-arisc.bin` | `analyse/arisc/scp.bin` | 176 132 B | `d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e` |
| `/lib/firmware/hy310-edid.bin` | `analyse/arisc/hy310-edid.bin` | **512 B** | `70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef` |

`hy310-edid.bin` ist `re/work/weltneuheit/HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`,
in dieser Reihenfolge, unverändert aneinandergehängt. Beide Blöcke haben Prüfsumme 0,
Block 0 trägt den Namen `SGD SX8`. Byte 168 ist `0x10`; die Firmware patcht es aus der
Port-Tabelle auf `0x00` und rechnet Byte 255 neu — deshalb sieht das EDID am Zuspieler
an genau zwei Bytes anders aus als die Datei (doku/75, Nachtrag 14:55).

**Achtung:** unter `/srv/h713-rootfs/lib/firmware/hy310-edid.bin` liegt bereits eine Datei
dieses Namens mit **256 Byte** (nur der 1.4-Block). Der Treiber verwirft sie mit einer
Warnung („ist 256 Byte statt 512"). Sie muss ersetzt werden.

Beide Binärdateien bleiben außerhalb des öffentlichen Repos; der Patch nennt nur die Namen
(`MODULE_FIRMWARE`).

---

## 12. Was offen ist

1. **Abnahme am Board: alles grün außer der Wirkung am Zuspieler.** Stand 07.09. 06:45:
   Handshake, `ResetEDIDModule`, `HostHDMIMAP`, `SetEDIDVersion`, acht `UpdateEDID`,
   `CheckEDIDUpdateStatus` (`ff f8 01 01 01 00 07 fe`), `RequestEDID` (vier Rahmen,
   vollständiges EDID), `SetEDIDAudioMode`, `SET5VFlag`, HPD DOWN/UP — Rückgabe 0,
   10,85 s. Der Zuspieler blieb trotzdem `disconnected`. Ursache belegt und behoben:
   `doku/nachtlog/B-hpd-luecke.md` (Abschnitt 5c). Die erste Fassung der Gegenprüfung war
   allerdings nicht falsifizierbar — sie verglich gegen die ROM-Vorgabe, die schon `0,1,2`
   ist; korrigiert und begründet in `doku/nachtlog/B-waechter-falsifizierbar.md`
   (Abschnitt 5c-1). ~~**Der Fix ist noch nicht am Gerät nachgemessen** — die
   Abnahmevorschrift steht im zweiten Teillog.~~ **Abgenommen am 07.09., 09:02–09:10:**
   Zuspieler meldet `connected 1920x1080` aus dem Kernel, Sequenz nach **17,65 s**, und der
   Wächter ist falsifizierbar (Vorbelegung `0xff` → `0,1,2`; vergiftet meldet debugfs
   `255,255,255`) — [`nachtlog/B-abnahme-board.md`](nachtlog/B-abnahme-board.md).
   Offen bleibt allein, **wodurch** die Sequenz gewinnt; `portmap: 0,1,2` ist dafür
   ausdrücklich **kein** Beleg.
2. **Kein Doorbell — der einzige echte Belegsprung.** Dass die ARISC pollt, steht
   strukturell fest (Hauptschleife `0xc5b4`/`0xc5d0`, Poller `0x7bbc`, Warteroutine
   `0x756c`); die Formulierung „3/3 belegt" stammt aus doku/77 §2.1 und doku/78 §3 B.
   ~~Eine Messreihe *ohne* Puls ist in doku/ aber nirgends mit Lauf-Nummern hinterlegt.~~
   **Gemessen, mit Lauf-Nummern:** [`nachtlog/B-puls-messung.md`](nachtlog/B-puls-messung.md)
   — drei Läufe, zwei Unterbefehle (`0x0311 SetEDIDVersion`, `0x2011 ResetEDIDModule`), drei
   Kaltstarts, einmal als **allererster** Befehl seit dem Kaltstart, jedes Mal „Handler
   gelaufen: ja". Dazu die B-Abnahme, die **ohne das alte, pulsende Modul** lief
   (`/root/prep_ohne_arisc.sh`) und trotzdem durchkam —
   [`nachtlog/B-abnahme-board.md`](nachtlog/B-abnahme-board.md) Z. 3–4 und Z. 62–64. `0091`
   pulst nicht. Falls die Abnahme dennoch am Handshake scheitert (`status` zeigt
   `startup_notify: not seen`, `fifo_rx ch3` ungleich 0), ist das der erste Verdacht — und
   dann eine Messung, kein wieder eingebauter Puls.
3. **`SetEDIDVersion` bekommt nur `2`.** Der Treiber setzt die Version fest auf 2, weil das
   Stock so tut. Was 0/1 bedeuten, ist ungeklärt.
4. **Byte 4 der Statusantwort** (`ff f8 01 01 <x>`) — Bedeutung unbekannt, wird berichtet,
   nicht bewertet.
5. **Reaktion der ARISC auf 5-V-Detect** (doku/77 §2.1, K4): muss der Kernel nach dem
   Stecken `PullHotPlug` nachziehen oder macht die Firmware das selbst? Messung am Board.
   Teilantwort aus der Disassembly: **`SET5VFlag` (`0x0411`) selbst tut in dieser Firmware
   nichts** — der Unter-Dispatch `0x11568` kennt `hi` = 4 nicht und kehrt bei `0x117f8`
   zurück (dasselbe gilt für `SetEDIDAudioMode`, `hi` = 5). Wenn die ARISC auf 5 V
   reagiert, dann nicht über diesen Befehl. Der Treiber schickt beide weiterhin, weil
   Stock sie schickt; er darf ihnen aber keine Wirkung zuschreiben.
6. **`remove()` hält den Kern nicht an.** Den Reset anzulegen würde den HPD-Pin eines
   laufenden HDMI-Eingangs fallen lassen, und er ist nur zusammen mit einem frischen Abbild
   sinnvoll — das macht `probe()`. Ein `rmmod`/`insmod` lädt die Firmware also neu und
   erzeugt eine neue Notify; das ist der beabsichtigte Weg.
7. **Was die drei Bits von `0x07091014` am Stecker bedeuten, ist nicht durchgemessen.**
   Belegt ist: `0x121e4` schreibt das Register **aktiv-low** und bitweise nach dem *Pin*
   aus der Portmap (Bit gesetzt = low), Stock steht im verbundenen Zustand auf `0x06`, und
   `PullHotPlug` DOWN/UP auf Port 0 schaltet den Zuspieler nachweislich um (K4). **Nicht**
   erklärt ist der eine Lauf, in dem `0x03` ein verbundener Zustand war. Solange das offen
   ist, ist der Registerwert allein **kein** Abnahmekriterium — das Kriterium bleibt
   `card0-HDMI-A-2/status` am Zuspieler plus der **Rückgabewert** des Portmap-Schritts.
   `portmap: 0,1,2` in `status` ist es ausdrücklich **nicht**: dieselbe Zeile steht nach
   jedem Kaltstart schon aus der ROM-Vorgabe da (Abschnitt 5c-1).
