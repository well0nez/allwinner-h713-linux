# CPU_COMM auf arm64: erster Round-Trip, und wo es jetzt steht

Nacht vom 01. auf den 02.09.2026. Alles hier ist am Gerät gemessen; wo eine
Aussage nur hergeleitet ist, steht es dabei.

> **Nachtrag 04.09.2026:** Der Abschnitt „Der offene Punkt" ist erledigt. Der
> MIPS holte nicht ab, weil er geparkt war - `bootcmd` fährt
> `h713_disp auto 0x30 logo`, und dessen letzte Handlung legt ihn still. Dazu
> kamen zwei echte Treiberfehler. Der Aufruf läuft jetzt aus Linux durch:
> [67-cpu-comm-linux.md](67-cpu-comm-linux.md). Die dort beschriebene
> Auflösung geht dem hier Stehenden vor.

## Das Wichtigste zuerst

**Der erste CPU_COMM-Round-Trip auf diesem Board ist gelaufen** - aus U-Boot,
mit `h713_disp commcall`. Das ist der Meilenstein, den cstengers Handoff vom
30.08. als offen führt: *„Still unexercised: no message has been exchanged."*

```
CALL → CALL_ACK → RETURN → RETURN_ACK          in 1 ms
FreeReturn slot 0 recycled (rd=1 wr=20 -> 0)
```

Und **Session Z ist reproduziert**: `THal_Vp_Init` mit `Para[2] = 0x4E700000`
liefert `nret=1, ret[0]=00000001` - Zeichen für Zeichen das Ergebnis vom
05.05.2026. Der Para[2]-Fix von damals trägt auf arm64 unverändert.

**16 von 17 Aufrufen der Stock-Init-Sequenz** liefen sauber mit RETURN durch
(`tools/uboot-hdmi-sequence.txt`). Der siebzehnte, `SetSource(3)`, wird
angenommen, antwortet aber nicht im 2-Sekunden-Fenster.

**Aus Linux geht es noch nicht.** Der gemergte Treiber bindet, adoptiert die
laufende Region und schickt eine Nachricht, die byteweise dieselbe ist wie die
funktionierende aus U-Boot - der MIPS liest sie nicht. Siehe „Der offene
Punkt".

## Der Treiber: `analyse/cpu-comm-arm64/`

Drei-Wege-Merge, gemeinsamer Vorfahre `legacy/drivers/Archived/cpu_comm/`
(= cstengers Patch 0014), unsere Seite `legacy/drivers/cpu_comm/`. Details und
Konfliktauflösung stehen in [65-cpu-comm-abgleich.md](65-cpu-comm-abgleich.md).

Eingebaut in die Serie als `patches/kernel/0014-…patch`, dazu:

```
patches/kernel/board/hy200_qz713df_a1_defconfig   CONFIG_HY310_CPU_COMM=m
patches/kernel/0024-…dts…patch                    cpu-comm: reg 0x400 -> 0x1000
                                                  cpu-comm: status okay
                                                  cpu-comm: GIC_SPI 21 -> 46
```

Bauen und ausrollen:

```bash
podman exec h713-build bash -lc 'cd /work/mainline && \
  KERNEL_CONFIG=netboot BOARD=lpddr3 build/build.sh kernel'
# Modul einzeln, ohne Neustart (Gerät hängt am Netz):
scp <kernelbaum>/drivers/soc/sunxi/cpu_comm/hy310-cpu-comm.ko \
    root@<ip>:/lib/modules/6.18.38/kernel/drivers/soc/sunxi/cpu_comm/
```

Die Adresse wandert bei jedem Start (`CONFIG_NET_RANDOM_ETHADDR`); zu finden
über `ss -tn | grep :2049`.

## Fünf behobene Fehler

### 1. Zeiger-Abschneidung, verdeckt durch einen Cast

```c
u32 addr = ShMemAddrBase + 9760*1 + 4880*r + 2440*d + 152;
u32 *seq = (u32 *)(uintptr_t)addr;
```

`ShMemAddrBase` ist die Kernel-VA der Abbildung (`0xffff800082000000`). Durch
das `u32` bleibt `0x82000000`; für `r=0,d=0` ergibt das `0x820026b8` - exakt
die Adresse im Oops beim Probe. **Der `(uintptr_t)`-Cast beruhigt genau die
Warnung, die das gezeigt hätte.** Ein warnungsfreier Bau beweist nichts,
solange solche Casts im Quelltext stehen.

Sieben weitere Zeiger-Stellen wurden einzeln entschieden, darunter
`cpu_comm_is_mips_va()`, das ein `u32` nahm und auf arm64 Kernelzeiger stutzte,
bevor es fragte, ob sie wie `0x8xxxxxxx` aussehen - ein gültiger Rückgabewert
wäre zufällig als Korruption verworfen worden.

### 2. `request_irq` ohne `request_irq`

Beim Merge war der IRQ-Handler ganz verschwunden (Polling-Fassung übernommen),
während `cpu_comm_msgbox_request_irq` weiter „registered" meldete und 0
zurückgab. `dev.c` glaubte die Meldung und übersprang den Polling-Rückfall.
Ergebnis: **kein Empfangspfad überhaupt**, `/proc/interrupts` leer.

Handler ist zurück, Dekodierung für IRQ- und Polling-Pfad geteilt
(`cpu_comm_msgbox_drain`).

### 3. `IRQ_HANDLED` ohne Empfang

Die erste Fassung gab bedingungslos `IRQ_HANDLED` zurück, mit der Begründung,
die Leitung teile sich niemand. Das war eine **Annahme, keine Messung** - und
falsch: SPI 46 teilt sich die Leitung mit dem Watchdog. Auf der damals noch
falschen Nummer (s.u.) nagelte das die Kiste fest: 100000 Auslösungen, kein
`nobody cared`, kein Eingreifen des Kerns.

Jetzt `drained ? IRQ_HANDLED : IRQ_NONE`. Ein Fehlschlag ist damit eine
dmesg-Zeile statt eines toten Geräts.

### 4. `GIC_SPI 21` ist die S/PDIF-Leitung

Im Devicetree trug `cpu-comm@3003000` dieselbe Nummer wie `spdif@2036000`
direkt darüber - mit hoher Wahrscheinlichkeit kopiert. Sie liegt dauernd an,
niemand quittiert sie.

| Nummer | gemessen |
|---|---|
| `GIC_SPI 21` (GICv2 53) | 100000 Auslösungen, `Disabling IRQ #332` |
| `GIC_SPI 46` (GICv2 78) | Zähler 0, kein Sturm |

Belegt wird 46 zusätzlich durch unsere eigene Board-DTS
(`legacy/dts/sun50i-h713-hy310.dts`), deren Kommentar Stock-Zählerstände nennt:
*„SPI 46: 3134, SPI 108: 546, SPI 109: 63"*. `CONTRADICTIONS.md` hatte den
Streit 2026-06-23 gegen 46 entschieden, kannte aber diese Messung vom 03.05.
nicht - die Datei ist revidiert.

**Drei Fehler haben sich hier gegenseitig verdeckt:** die falsche Nummer fiel
nicht auf, solange kein Handler anmeldete; das fehlende `request_irq` fiel
nicht auf, weil `dev.c` der Erfolgsmeldung glaubte; und das bedingungslose
`IRQ_HANDLED` machte aus der falschen Nummer einen Hänger statt einer Meldung.

### 5. Der Treiber überschrieb die Routine-Tabelle

`InitCommSeqMem` enthält einen Block mit diesem Kommentar:

> *WORKAROUND: MIPS never initializes its share_seq structures … on our
> mainline we have to init the cpu=1 (MIPS-side) entries ourselves.*

Er schreibt **MIPS-seitige `share_seq`-Strukturen im Shared Memory** und läuft
im Adoptionszweig mit, der `InitCommSeqMem` in der Annahme ruft, es fasse nur
ARM-Privates an. Nach dem Laden stand an `0x4e3075c0` `version=0 count=0`, wo
U-Boot `version=162 count=81` gemeldet hatte.

Bittere Reihenfolge: **vor** Fix 1 faultete dieser Block und richtete nichts
an. Erst der reparierte Zeiger ließ ihn sauber schreiben - ein behobener
Fehler legte einen schlimmeren frei.

Jetzt an `!cpu_comm_shmem_adopted` gehängt, ebenso wie MIPS-Takt, MIPS-Reset,
Share-Regs und der „lies neu"-Doorbell. Alles davon stammt aus der arm32-Welt,
in der Linux den MIPS hochbrachte; hier tut es U-Boot.

## Die Diagnose im Sendepfad

`SendComm2CPUEx` druckt jetzt dieselben Zeilen wie U-Boots `commcall`:

```
cpu_comm: TX FreeCall rd=6 wr=20 cap=21 isz=4 base=0x4e302778
cpu_comm: TX slot idx=6 @… (erwartet …)
cpu_comm: TX chan=0x0000 dst_cpu=1 pid=0x8b8f3160 comp_id=0x2f02f7dd (key 0xb8f31600)
cpu_comm: TX nach Doorbell: SENT-Bit …
```

**Sie muss hinter Schritt 16 stehen** - die Routing-Felder (`+0x10 dst_pid`,
`+0x18 dst_cpu`) füllt erst der `direction == 0`-Block. Davor gelesen zeigt die
pid immer 0; genau das ist einmal passiert und wurde prompt fehlgedeutet.

Die Offsets stammen aus U-Boot, nicht aus dem Kopf: `share_seq + 0x78` ist der
FIFO-Kopf (`rd/wr`, `+0x10 cap`, `+0x14 isz`, `+0x18 base`), Slots ab `+0x168`,
das SENT-Bit bei `+0x08`.

## Der offene Punkt

> **Aufgelöst am 04.09.2026**, siehe [67-cpu-comm-linux.md](67-cpu-comm-linux.md).
> Die Nachricht war zu Recht byteweise identisch - es fehlte kein Feld, es fehlte
> der Empfänger. Der Rest dieses Abschnitts ist die Beweislage, die dahin führte.

Die Nachricht aus dem Treiber ist **byteweise identisch** mit der
funktionierenden aus U-Boot - gleicher Slot, gleicher Schlüssel
`0xb8f31600`, gleiche comp_id. Trotzdem:

```
TX nach Doorbell: SENT-Bit STEHT NOCH (nach 200 x 100us)
msgbox tx raw=0x00000000 (CALL), fifo now 13
msgbox tx raw=0x00000000 (CALL), fifo now 14
SendComm2CPUEx: ACK timeout
```

**Der FIFO-Zähler ist der aussagekräftigste Wert.** Er wächst seit dem ersten
Treiber-Aufruf und fällt nie. Aus U-Boot ging er sofort auf 0 („MIPS drained
the FIFO after 0 ms"). Der MIPS liest die Msgbox in diesem Zustand also
überhaupt nicht - unabhängig vom Inhalt.

Er pollt die FIFO (der HW-IRQ erreicht seine INTC nie, `CURRENT-TRUTH`), also
läuft sein Poll-Thread nicht. **Und das passiert auch aus U-Boot:** nach
`SetSource(3)` kletterte der Zähler dort 1→2→3→4 und blieb oben.

### Die heißeste Spur: die Msgbox muss VOR dem MIPS-Start laufen

cstengers eigener Kommentar in `h713_mips.c`, bei der Vorbereitung des Shared
Memory, beschreibt unser Symptom mitsamt Ursache:

> *Bring the msgbox up **before the coprocessor starts**, not when a message is
> finally sent. Its bus gate and reset at 0x0200171c read zero from cold …
> Enabling it at send time is too late: **the firmware configures its own
> receive side during startup**, and with the block gated those writes went
> nowhere. That is consistent with what the bench showed - **the doorbell
> reached the FIFO, the count went to one, and the MIPS never drained it**.*

Das beantwortet auch, warum U-Boot das überhaupt aufbaut: es ist Teil der
**Startkette**, nicht der HDMI-Kette. Der MIPS richtet seine Empfangsseite beim
Start ein; wer die Msgbox später einschaltet, kommt zu spät.

**Und es ist längst dokumentiert.** Unser arm32-Baum benutzt dasselbe
`devm_clk_get_enabled`, und dort lief das IPC - der Unterschied ist nicht der
Code, sondern die Prozedur:

> **SW-Reboot reicht NICHT** - physischer Power-Cycle nötig (MIPS muss kalt
> hochkommen, `feedback_mips_death_needs_power_cycle`)

Session DD hat es erlebt: *„Plus später hot-swap probiert (rmmod + insmod) →
**MIPS-tot**. Hot-swap broke MIPS state. Power-cycle brachte zurück."* Die
Deploy-Anleitung aus CC-NIGHT führt Hot-Swap als *„Variante B - riskant"*.

**In dieser Nacht wurde bei jedem Modultausch `rmmod`/`insmod` gefahren.** Alle
Linux-Aufrufe fanden also nach mindestens einem Hot-Swap statt. Das erklärt die
Beobachtung vollständig und ohne neue Hypothese - der Treiber muss dafür nichts
falsch machen.

**Aber das ist nur die halbe Antwort, und die kleinere.** Im arm32-Baum lief
das Draining *generell* - nicht bloss, weil dort nicht hot-geswappt wurde.
Session Z fuhr 33 Aufrufe am Stueck, Session DD empfing MIPS→ARM-Callbacks.
Der MIPS holte dort also zuverlaessig ab, unter Linux, mit einem von U-Boot
gestarteten Coprozessor.

Damit ist die eigentliche Frage fuer morgen nicht „warum drainiert er nicht",
sondern: **was macht `legacy/drivers/cpu_comm` an dieser Stelle, das der
gemergte Baum nicht tut?** Der Merge hat an genau dieser Nahtstelle Konflikte
gehabt (hw.c #2/#3/#4 - RX-Modell, Dekodierung, Registrierung), und dort ist
durchgaengig *seine* Seite genommen worden. Die drei Hunks gehoeren gegen
unseren Baum gehalten, bevor irgendetwas anderes probiert wird.

Der Rohdiff liegt reproduzierbar vor:

```bash
cd /opt/Projekte/h713/legacy/drivers
diff -u Archived/cpu_comm/cpu_comm_hw.c cpu_comm/cpu_comm_hw.c
```

Gemessen nach all dem: Gate an, Reset gelöst, Version `0x00020000` - der Block
lebt. TX-FIFO steht bei 14 und fällt nicht.

### Der nächste Test

> **Beide Tests sind gelaufen.** Der erste (Stromzyklus, ein `insmod`, ein CALL)
> schloss den Hot-Swap als Ursache aus: die FIFO stieg auch dort auf 2 und blieb.
> Der zweite (`h713_disp init 0x30` statt `auto … logo`) war die Antwort.
> [67-cpu-comm-linux.md](67-cpu-comm-linux.md).

**Zuerst dieser, er ist billiger:** Stromzyklus, booten, **`insmod` genau
einmal**, ein einziger CALL. Kein `rmmod` davor. Den TX-Zähler `0x03003864`
**vor** dem `insmod` lesen - er stand beim ersten Aufruf eines frischen Boots
schon auf 7, und das ist nie erklärt worden.

Fällt er danach auf 0, war es die Modul-Entladerei, und der Treiber darf Takt
und Reset der Msgbox bei laufendem MIPS nicht freigeben (dieselbe Klasse wie
die vier anderen Eingriffe, die jetzt an `cpu_comm_shmem_adopted` hängen).

**Danach erst dieser:**

Die funktionierenden Aufrufe kamen **direkt nach `h713_disp init 0x30`**. Der
Linux-Boot fährt `h713_disp auto 0x30 logo` - anderer Pfad, spielt zusätzlich
das Logo auf und lässt den Projektor-Task weiterlaufen; der elog endet bei
`EnterIdle again`.

```
setenv bootcmd 'h713_disp init 0x30; dhcp; tftpboot 0x60000000 192.168.8.104:${bootfile}; bootm 0x60000000'
```

Fällt der FIFO-Zähler danach auf 0, liegt es am Startpfad und nicht am
Treiber. Das Panel bleibt bei `init` schwarz - das ist dort erwartet und kein
Befund.

## Betriebliches

- **`elog=3` verhindert die MIPS-Bereitschaft.** Dreimal belegt, in beide
  Richtungen: mit `elog=3` bleibt `MIPS=00000000`, der Init fährt den Teardown
  und nimmt die Panel-Rail mit (schwarzer Schirm); ohne kommt `MIPS=00000005`.
  Vermutung: `ELOG_ASYNC=0` plus INFO-Stufe macht die Firmware langsam genug,
  dass sie U-Boots Bereitschaftsfenster verpasst. Nicht in `bootcmd` speichern.
- **`modprobe.blacklist=hy310_cpu_comm`** steht in den `bootargs`. Ein
  fehlerhaftes Modul kostet damit ein `insmod`, keinen Startvorgang.
- **Ein Leser pro UART.** Läuft noch ein altes Mitschnitt-Skript, frisst es die
  Bytes und jede Messung ist wertlos. Einmal passiert, mit falscher
  Schlussfolgerung. `fuser -v /dev/ttyACM0` vor jeder Konsolenmessung.
- **`h713_disp init` gilt einmal pro Stromzyklus.** `tools/uart-uboot.py catch`
  prüft das Kaltstart-Banner und wartet weiter, wenn nur der alte Prompt steht.
- **Warmstart hilft nicht.** Er liefert den Prompt, gated aber die
  Display-Blöcke wieder; der MIPS ist danach tot. Statische Speicherinhalte
  (Call-Tabelle, elog) beweisen dann nur, dass er *lief*.

## Board-Konstanten aus cstengers Baum, geprüft

| Konstante | Urteil |
|---|---|
| `SET/GET_PICTURE_MODE_HANDLER` `0x8b10a8c0/8ec` | ✓ identisch |
| Transport `0x03003874/864/810`, Gate `0x0200171c` | ✓ am Gerät bewiesen |
| `getCurCPUID` `0x8b1227b4` | ✗ bei uns **`0x8b122688`** |
| `H713_COMM_DEV_PTR` `0x8b22efe4` | ✗ liest 0 auch bei laufendem MIPS |
| Msgbox-IRQ `GIC_SPI 21` | ✗ **46** |

Die beiden Firmware-Adressen betreffen nur `h713_disp commdev`, einen
Diagnosebefehl. Er verweigert deshalb bei uns den Dienst („KSEG reads are not
landing where expected") - zu Unrecht: `fwmd` liest korrekt, geprüft gegen
`mipslog` und gegen das unberührte Abbild.

## Für cstenger

Vier Befunde, unabhängig von unserem Board:

1. `cpu-comm@3003000` trägt `GIC_SPI 21` - das ist S/PDIF.
2. `cpu_comm_msgbox_request_irq` meldet Erfolg, ohne einen Handler anzumelden.
3. Patch 0014 stammt aus `Archived/`; es fehlen Callback-Loop, Linux-Semaphoren,
   `Comm_AddNewChannel` im INSTALL_RT, DMB-Cache-Sync (siehe
   [65-cpu-comm-abgleich.md](65-cpu-comm-abgleich.md)).
4. Sein `commdev`-Selbsttest und `H713_COMM_DEV_PTR` sind auf seine
   Firmware-Revision kalibriert und gehören in `h713_mips_fw_rev`, wo die
   HDCP-Adresse schon steht.
