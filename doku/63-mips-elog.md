# Das Log des Coprozessors mitlesen

Die MIPS-Firmware führt ein eigenes Log. Es kommt **nicht** über UART heraus -
alle Ausgabemodi schreiben in DRAM. Der Kommentar in unserem U-Boot, Modus 0
sei „SYNC, schreibt direkt über route (0 = uart)", ist falsch; er war aus dem
Formatter hergeleitet, nicht gemessen.

## Was die Firmware wirklich tut

`elog_output` @ `0x8b150068` verzweigt über ein Byte:

| `0x8B48BE9B` | Ziel | Größe |
|---|---|---|
| 1 | `elog_mode1_ring100k_write` | **100 KiB Ring** bei `0x8B272D9C` |
| 2 | `elog_mode2_linear2m_write` | 2 MiB linear bei `0x8B28BD9C` |
| sonst | `elog_default_dispatch` | 120 KiB Ring |

Bei uns steht das Byte auf **1**. Deshalb lief `mips_elog2.py` aus
`weltneuheit` in einen Bus-Error: es liest die Modus-2-Adresse.

**Modus 2 nicht einschalten.** In der Wissensdatenbank steht dazu ausdrücklich
*„enabling mode 2 (`0x8B48BE9B=2`) may break MIPS init per HANDOFF-D"*.

## Adressen, aus Linux erreichbar

MIPS-VA minus `0x40000000`, alles innerhalb `mips-firmware@4b100000`:

| Zweck | MIPS-VA | ARM-phys |
|---|---|---|
| Ringpuffer, 102400 Bytes | `0x8B272D9C` | `0x4B272D9C` |
| Schreibzeiger (Offset) | `0x8B48C2A8` | `0x4B48C2A8` |
| Lesezeiger (Offset) | `0x8B48C2A4` | `0x4B48C2A4` |
| Overflow-Flag | `0x8B48C2A1` | `0x4B48C2A1` |
| Enable | `0x8B48C2AC` | `0x4B48C2AC` |
| Semaphor, bei jedem Schreiben | `0x8B48C2B4` | `0x4B48C2B4` |

## Der Ring hat einen Konsumenten-Vertrag

Aus `elog_mode1_ring100k_write`:

```c
result = 102400 - (write_ptr - read_ptr);      // freier Platz aus BEIDEN Zeigern
if ( !result ) return;                         // voll -> Zeile faellt weg
if ( str_len >= result ) { overflow = 1; }     // passt nicht -> Overflow setzen
if ( MEMORY[0x8B48C2A1] ) return;              // Overflow gesetzt -> nichts mehr
```

**Zieht niemand den Lesezeiger nach, läuft der Ring einmal voll und die
Firmware hört auf zu loggen.** Er überschreibt den Anfang nicht, er verwirft
das Neue. Ohne Konsument stehen dort also die ersten ~100 KiB ab Firmwarestart
und danach nichts mehr - was praktisch ist, wenn man die Boot-Phase sucht, und
nutzlos, wenn man live mitlesen will.

## Das Zeilenformat

```
E/TSEXX    [0] (./TFDManager.cpp 148) TSE read data_header incorrect
^  ^        ^   ^              ^
|  Modul    |   Datei          Zeile
Stufe       get_uptime_ticks()
```

Die Klammer trägt bis zu drei einzeln freischaltbare Felder, gesteuert über
eine Tabelle pro Loglevel im RAM (`sub_8B150E28`):

- Maske 4 → `sub_8B1521D8` = `get_uptime_ticks()`, als `%ld`
- Maske 8 → `sub_8B152218` = die feste Zeichenkette `"pid:1008"`
- Maske 16 → drittes Feld

Bei uns ist nur Maske 4 an, und **der Tickzähler steht bei jeder Zeile auf 0** -
obwohl die HDCP-Zeile beweist, dass Zeit vergangen ist. Die Tickquelle läuft zu
dem Zeitpunkt also noch nicht; als Ordnungskriterium taugt das Feld nicht.

Alle Threads teilen sich einen 1024-Byte-Formatpuffer bei `0x8B27299C`, und der
Mutex bei `0x8B48BE9C` ist ein No-Op (`nullsub_28/29`). Gleichzeitige Threads
verschränken ihre Bytes. Das ist der einzige Punkt, an dem ein Firmware-Patch
etwas brächte.

## Mitlesen

`tools/mipslog.c`, auf dem Gerät übersetzen:

```bash
gcc -O2 -o mipslog mipslog.c
./mipslog state     # Zeiger und Overflow-Flag
./mipslog dump      # Ringinhalt, Lesezeiger bleibt stehen (Boot-Historie)
./mipslog tail      # laufend, zieht den Lesezeiger nach
```

**Erst `dump`, dann `tail`.** Sobald `tail` den Lesezeiger nachzieht, ist die
Historie jenseits von 100 KiB weg.

## Den Level hochdrehen

Auf ERROR-Stufe schreibt die Firmware ganze 1879 Bytes und schweigt dann. Die
Meldungen, die bei der Scanout-Suche zählen - `vdd`, `EntrySTM*`,
`EnterWaiting*`, WCE - liegen darüber.

U-Boot kann den Level setzen; es tut es bisher nur in `h713_disp test`. Neu ist
das optionale Argument:

```
h713_disp init <project-id> [noboot|quiesce] [elog=<0-5>]
```

Es setzt `H713_CFG_OFF_ELOG_MODE` auf 1, `ELOG_ASYNC` auf 0 und
`ELOG_LEVEL` auf den gewünschten Wert - drei Bytes in `display_cfg.xml`, das
bei `0x4be01000` im RAM liegt, bevor der Coprozessor losgelassen wird. Kein
Firmware-Patch.

**Nicht ohne mitlaufenden `mipslog tail` benutzen.** Ein höherer Level ohne
Konsument füllt den Ring in Sekunden, das Overflow-Flag kippt, und danach ist
das Log toter als vorher.

## Was das Log auf INFO-Stufe zeigt (01.09.2026)

Erster Lauf mit `h713_disp init 0x30 elog=3`. Aus 1879 Bytes auf ERROR werden
**51805 Bytes** auf INFO, 552 Zeilen.

### Die Pipeline konfiguriert sich vollständig

`NRWinNode`, `ProcWinNode` und `PanelWinNode` laufen alle sauber durch, mit
unserer Panelgeometrie:

```
I/wce_nr    (NRWinNode.cpp 852)  y:1920, c:1920
I/wce_nr    (NRWinNode.cpp 863)  y_width:1920, c_width:1920, v_size:1080
I/wce_proc  (ProcWinNode.cpp)    in [1920,1080] -> out [1920,1080], ratio 65536 x 65536
I/wce_panel (PanelWinNode.cpp)   m_video_win [104, 25, 1920, 1080]
```

Am Display-Teil liegt es also nicht.

### Wo sie stehenbleibt

```
W/app [13] (app_top_projector.cpp 193)  cant get device : 2
W/app [13] (app_top_projector.cpp 193)  cant get device : 4
I/app [13] (app_top_projector.cpp 974)  AppTopSetSource
I/app [13] (app_top_projector.cpp 363)  EnterIdle
I/app [13] (app_top_projector.cpp 366)  EnterIdle again
I/dtv [28] (THiDTVPro.cpp 57)           Enable VideoDeocer [1]
I/mem_agn [28] (memory_agent.cpp 71)    update_onoff
```

Zwei Eingabegeräte fehlen, der Projektor-Task geht in den Leerlauf und bleibt
dort. `EnterWaitingWindowsReady`, `EnterWaitingPipeLineReady`,
`PushSignalToMemoryAgent` - die Kette, die den Scanout scharfschalten würde -
kommen im ganzen Log **nicht ein einziges Mal** vor. Ebensowenig `vdd`,
`EntrySTM*`, `SignalValid` oder `VideoDec`.

### Und dann schweigt sie

```
write=51805 read=51805 overflow=0      dreimal im Abstand von 3 s
Uptime 438 s
```

Der Schreibzeiger steht seit sieben Minuten. Die Firmware hängt nicht und ist
nicht abgestürzt - sie ist **untätig**. Die Ticks im Log reichen von 0 bis 28.
(Vorsicht beim Auszählen: `length[197616]` und ähnliche Werte aus den
TSE-Kopfzeilen sehen wie Ticks aus, sind aber keine.)

### Der Deskriptor wirkt genau einmal

`videodec_poke.py poke` löste beim ersten Mal eine **komplette
WCE-Neuberechnung** aus, 70 Zeilen:

```
m_in_win           : [   0,  0, 1920, 1080]
m_out_win          : [ 104, 25, 1920, 1080]
m_afbd_source_mode : 2
Compression mode 1, Y[0x60, 0x60, 0x438], C[0x60, 0x60, 0x21c]
mb_420_format      : 1
```

Danach nicht mehr. `WinMgr+56` war kurz auf `0x0002007C` (gültiges Signal) und
steht wieder auf `0x00020003` (kein Signal). Ein erneutes Setzen des
Deskriptors - auch nach Zurücksetzen auf 0 - erzeugt **keine einzige
Logzeile** mehr.

Einordnung: der erste Poke wirkte, weil die Firmware noch in ihrem
Init-Durchlauf war und ohnehin auswertete. Danach ist sie ereignisgesteuert,
und das Ereignis ist laut `CURRENT-TRUTH.md` **MIPS-HW-IRQ 19 →
`sw_int_type 8` → `THiDTVPro_OnSignalEvent_STM` → `CheckSignal`**. Ohne
Dekoder-Aktivität feuert nichts, also schaut niemand auf den Deskriptor.

**Der Deskriptor ist notwendig, aber nicht hinreichend.**

## Die zwei verbleibenden Blocker, benannt

1. **Auslöser.** Was hebt MIPS-IRQ 19 beziehungsweise `sw_int_type 8`? Solange
   das fehlt, evaluiert die Firmware den Deskriptor nicht, egal was darin
   steht. `register_hw_interrupt` (`0x8b147b48`) programmiert die MIPS-INTC bei
   `~0x0305FC00` - dort wäre nachzusehen, ob der Interrupt von ARM aus
   auslösbar ist.

2. **Format.** Selbst als sie evaluierte, stellte sie AFBD auf
   `m_afbd_source_mode = 2`, also **AFBC-komprimiertes** Lesen, bei
   Kompressionsverhältnis 15625. Unser Cedrus-Puffer enthält **rohes NV12**.
   Das ist die dokumentierte Ursache für das weiße beziehungsweise schwarze
   Bild. Laut `HANDOFF-NV12-WHITE-ROOTCAUSE` sitzt diese Entscheidung in
   `NRWinNode` (`m_afbd_source_mode 1->2`, NRWinNode.cpp:251) und **nicht** im
   Deskriptor - unser `b_compress_en = 0` ändert daran nichts, was der Lauf
   bestätigt hat.

Beides ist ab jetzt am Log überprüfbar: jede Änderung, die die Firmware
tatsächlich erreicht, hinterlässt Zeilen.

## Den Level zur Laufzeit hochdrehen - ohne Neustart (06.09.2026)

`elog=3` im U-Boot-`init` verhindert die MIPS-Bereitschaft (doku/67). Der
Level lässt sich aber **nach** dem Start aus Linux setzen, weil die Firmware
ihn zur Laufzeit aus dem RAM liest. Aus `elog_output` (`0x8b150068`) und dem
Modul-Lookup `0x8b150c98`, mit `tools/mips-dis.py` gelesen:

| ARM-phys | Bedeutung |
|---|---|
| `0x4b48bd9c` (Byte) | **globaler Level** (Boot: 1 = nur `E/`) |
| `0x4b48be98` (Byte) | 1 = **Modultabelle** benutzen, 0 = globalen Level |
| `0x4b48bdc0` | Modultabelle, 10 Einträge à 19 Byte: `name[16]`, `+0x11` Schalter, `+0x12` Level |
| `0x4b48be99` / `0x4b48be9b` | enable / Modus (1 = 100-KiB-Ring), unverändert lassen |

Eine Zeile wird geschrieben, wenn `level(Zeile) <= Schwelle` (`sltu` bei
`0x8b15014c`). Die Tabelle ist im Betrieb leer (alle Schalter 0), also zählt
der globale Level. Wortweise (RMW, 32 Bit ausgerichtet - Slices auf Device-
Memory geben Bus-Error):

```
0x4b48bd9c: Byte 0 := 5      globaler Level 5
0x4b48be98: Byte 0 := 0      Tabellenmodus aus
```

Gemessen: Phase 2+3 der Init-Sequenz schreiben danach ~40 KiB statt 187 Byte
(`D/cpucomm`, `D/TSEXX`, `D/hal`, mit laufenden Tick-Stempeln). Der MIPS
blieb bereit, alle 22 Aufrufe mit RETURN.

**Konsument zwingend:** `analyse/hdmi-seq/elog_tail.py` (auf dem Board
`/root/elog_tail.py`) pollt den Ring alle 10 ms, zieht den Lesezeiger nach,
schreibt alles nach stdout und **gefilterte** Zeilen (`--kmsg-grep`,
Vorgabe `hdmi|app|hal|wce|win|…`) nach `/dev/kmsg`, dazu einen Herzschlag
`elog_tail: hb N` alle `--hb` ms. Der Filter ist nötig: der UART schafft bei
115200 Baud ~11 KiB/s, die `cpucomm`-Debugzeilen allein würden die
Warteschlange füllen, und beim Tod des ARM wären genau die letzten Zeilen noch
nicht draußen. `echo 8 > /proc/sys/kernel/printk`, damit `kmsg` am UART
erscheint.
