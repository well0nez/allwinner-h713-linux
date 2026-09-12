# S40 — Vorarbeit Standby Stufe 2: ARISC-Reste und die MIPS-Frage

Stand 09.09.2026. Rein statisch, kein Board, kein Bau, kein Netz. Grundlage:
[`104-plan-standby-stufe2.md`](../104-plan-standby-stufe2.md), [`S39`](S39-re-stock-standby-ablauf.md) §1/§4/§5/§6,
[`S35`](S35-re-arisc-standby-led-key.md).

**Herkunft:** Der erste Durchlauf wurde nach ~40 min abgebrochen, bevor er schreiben konnte.
Alles unter §1–§3 und §4.2/§4.3 ist **aus dem Transkript rekonstruiert** und, wo als „nachgeprüft"
markiert, in dieser Sitzung noch einmal am Original belegt. §4.1 und §5–§7 sind neu.

**Adressregel wie S35/S39:** Blob-Offset = AR100-Adresse = Adresse im Disassemblat.
`:N` = Zeile in `analyse/arisc-frame/full-disasm.txt`, es gilt `N = Adresse/4 + 1` (nachgeprüft).

---

## 1. Die vier offenen Adressen aus S39 §6 (Aufgabe A)

| Adresse | Zeile | Was es ist | Beleg |
|---|---|---|---|
| `0x12b04` | :19138 | **Schlafbefehl.** `l.addi r4,r0,0x10` / `l.addi r3,r0,0x4000` / `l.mtspr r3,r4,0` → SPR `0x4000` = Gruppe 8 Reg 0 = **PMR**, Wert `0x10` = **DME (Doze)**. Der OR1K hält an, bis ein IRQ kommt. | :19138-19140 |
| `0x6058` | :6167 | **IRQ-Handler eintragen.** `r3 = irq*8 + 0x16f44`; `[r3+0] = r4` (Funktion), `[r3+4] = r5` (Argument). Die Handler-Tabelle liegt also bei AR100 **`0x16f44`, 8 Byte je Eintrag**. | :6167-6173 |
| `0xc830` | :12813 | **Weckquelle eintragen.** Lädt `arr[0]`, ruft `0xc7c8` (Zuordnung), und bei Ergebnis ≠ −1 `0x6040(id, 1)`. Zwilling `0xc7fc` (:12800) ruft dasselbe mit `0`, ist also das Austragen. | :12813-12824 |
| `0x1330c` | :19652 | **Einheitenrechnung.** `r4 = 1000`; `r3 = arg*1000`; `jal 0x12f10` = 32-bit-Division (Zähler `r3`, Nenner `r4`, Quotient `r11`, Rest `r7`, Division durch 0 → 0; :19397-19458). Netto `arg` für `arg < 0x418937`, darüber mit 32-bit-Überlauf. Der Wert ist also schon in der Tick-Einheit des Timers. | :19652-19659 |

**IRQ-Hilfsfunktionen** (alle über den Zeiger `*(0x16f30)` = INTC-Basis):

| Funktion | Ziel | Wirkung |
|---|---|---|
| `0x5fd0` :6101 | `0x5b84` :5858 | Freigeben: `base+0x40`/`+0x44` Bit setzen; IRQ 0 zusätzlich `base+0x10 = 1` |
| `0x6028` :6155 | `0x5d68` :5979 | Feld in `base+0x50`/`+0x54` löschen und aus `r4` neu setzen |
| `0x6040` :6161 | `0x5e2c` :6028 | Dasselbe in `base+0xc0`/`+0xc4` — der Pfad, den `0xc830` benutzt |
| `0x6000` :6145 | — | `[base+0x0c] = r3`; Bit 0 in `base+0x50` setzen |

**`0xc830` ist im Standby-Pfad wirkungslos** (nachgeprüft): `0xc7c8` (:12787-12791) ist
`return (x == 0xffffffe0) ? 0 : −1`; übergeben wird ihm aber Feld A = `p[0] & 0x3ff`, also
`0…1023` — der Vergleich trifft nie, `0xc830` kommt nie zu `0x6040`. Freigeschaltet wird die
Weckquelle von den drei Aufrufen **danach** (`0x6058`, `0x5fd0`, `0x6028`, §2). Ob `−32` eine
Sentinel-Kennung eines anderen Aufrufers ist oder der Zweig tot: am Gerät prüfen (R13).

---

## 2. `set_wakeup_src` — die Felder von `p[0]` (Aufgabe A)

Handler ab `0xc994` (:12902). `r16 = p[0]` (:12903-12905).

```
0xc9bc  r14 = p[0] & 0x3ff             Feld A = Bits 9..0                 :12912
0xc9d0  if ((p[0] >> 30) != 3) -> 0xca04   Typwahl aus Bits 31..30        :12916-12917
0xc9f0  jal 0x1330c(p[0] & 0x3fffffff); *(0x16aa0) = Ergebnis  [Typ 3]    :12924-12929
0xca04  jal 0xc768(r14)                Feld A -> IRQ-Nummer   [Typ != 3]  :12930
0xca68  FeldB = (p[0]>>10)&0x3ff, FeldC = (p[0]>>20)&0x3ff                :12955-12959
0xca70  stack[12]=A, [16]=B, [20]=C ; jal 0xc830(&stack[12])              :12960-12962
0xca98  jal 0x6058(irq, 0xc864, 0)     ISR eintragen                      :12967
0xcaa0  jal 0x5fd0(irq) ; jal 0x6028(irq, 0)   IRQ freigeben              :12969-12972
0xcab4  *(0x17118) = 1                 „Weckquellen scharf"               :12974-12978
```

**Antwort auf die S39-Frage:** `p[0]` ist ein gepacktes Wort
`{ Typ = Bits 31..30, C = Bits 29..20, B = Bits 19..10, A = Bits 9..0 }`.

* **A** ist die Quellenkennung. Sie geht durch `0xc768` (:12763), das die Tabelle bei **`0x15a40`**
  durchsucht — Paare à 8 Byte `{IRQ-Nummer, Quelle + 0x20}`, bis zu 14 Einträge — und die
  **IRQ-Nummer** liefert (:12763-12783, Schlüsselbildung `r3 + 0x20` :12768). Dieselbe Tabelle
  liest der ISR `0xc864` (:12826) rückwärts: er vergleicht die IRQ-Nummer gegen Wort 0, nimmt
  Wort 1, zieht `0x20` ab (:12834-12852) und schreibt das Ergebnis nach **`0x17114`**
  (:12855-12856) — das Weckgrund-Wort, das die ARISC nach S39 §0 an den ARM zurückmeldet.
  Findet er nichts, schreibt er `0xffff` (:12852).
* **B** und **C** sind zwei 10-bit-Parameter der Quelle. Sie werden zusammen mit A als
  3-Wort-Block an `0xc830` gereicht, das aber **nur `arr[0]` liest** (:12814) und damit nichts
  tut (§1). B und C werden im Stock also entgegengenommen und im Standby-Pfad nicht ausgewertet —
  vermutlich Pegel/Flanke und Entprellung für Quellen, die dieser Zweig nicht bedient.
  **Für unseren Nachbau: 0 setzen.**
* **Typ 3** ist kein IRQ, sondern ein **Weck-Zeitgeber**: `p[0] & 0x3fffffff` wird zur Periode des
  Software-Timers bei `0x16aa0`. Dessen Rückruf `0xc7e0` (:12793) schreibt `0xc0000000` nach
  `0x17114`, das ist also der Weckgrund „Zeitablauf". Timer-Bedienung: `0x13294` anlegen
  (:19622), `0x13260` starten (:19609), `0x13274` stoppen (:19614).

**Die Warteschleife `0xd87c`** (:13856) schließt den Kreis:
Marke `0xf3f35001` → `0xc93c` (Timer starten) → Schleife ab `0xd8b0`: `0x107cc` (CEC-/Nachrichten-Pumpe),
dann `*(0x17114)` prüfen; ist es 0, wird `0x0701033c` Bit 27..24 gesetzt, **`0x12b04` (Doze)** gerufen,
das Feld wieder gelöscht und zurückgesprungen (:13869-13890). Sonst `printf("...", *(0x17114))` und
Sprung nach `0xc978` (Timer stoppen) (:13872-13880).

---

## 3. Baut der Stock-BL31 wirklich Typ `0x22`? — **Ja, bewiesen** (Aufgabe A)

`analyse/arisc/monitor.asm`, Funktion **`0x66b4`** (Zeile 6541 ff.):

```
66b8  mov w5,#0x22 ; strb w5,[x29,#0x2a]   Typ 0x22        (Zeile 6542/6544)
66c4  mov w5,#0x2  ; strb w5,[x29,#0x28]   state = 2 ; attr = 0 (66f0)
66c8  stp w0,w1,[x29,#0x10] / 66e4 stp w2,w3,[x29,#0x18] / 66e8 str w4,[x29,#0x20]
                                          mpidr, entrypoint, cpu_, cluster_, system_state
66d4  add x5,x29,#0x10 ; str x5,[x29,#0x48]  Datenzeiger (Kopf + 0x20)
66e0  mov w5,#0x5  ; strb w5,[x29,#0x2c]   count = 5
66f4  bl  0x60a0                           Msgbox-Senderoutine
```

Das ist **genau der 5-Wort-Block** `{mpidr, entrypoint, cpu_state, cluster_state, system_state}`
aus S39 §1.3. Die Senderoutine `0x60a0` (Zeile 6259 ff.) belegt auch den Rahmen:
sie schreibt das Kopfwort `*x19` nach **`0x0300347c`** (Zeile 6296-6300), danach das Byte
`x19+0x4` (`count`) und dann `count` Wörter aus `*(x19+0x20)` — jeweils mit Warteschleife auf
`0x0300346c` ≠ 8 (FIFO voll). Antwort wird aus `0x0300307c` gelesen, nachdem `0x0300306c` ≠ 0 ist
(Zeile 6339-6350). Damit ist auch S39 §1.2 bestätigt: **auf der Leitung liegen Kopfwort, `count`,
Datenwörter — Port 3.**

**Zwei Aufrufer** von `0x66b4`:

| Stelle | Argumente | Bedeutung |
|---|---|---|
| `0x1034` (Zeile 1005) | `(mpidr, **0**, 3, 3, 3)` | `entrypoint = 0` → die ARISC nimmt nach S39 §1.3 den Zweig `0x00e9b0` „kein Standby, nur CPU-Op" |
| `0x10e8` (Zeile 1050) | `(mpidr, **entrypoint**, 3, 3, 3)` | der **Standby-Pfad**; davor sichert `0x1084`-`0x10b8` `0x08110000`, `0x08110004`, `0x08120020` in Globale |

Zum Vergleich: `0x694c` (Zeile 6709) baut Typ **`0x11`**, `count = 2` (die Quittung aus Plan 104 H1),
`0x6704` Typ `0x24`, `count = 1`. Die Rahmen sind alle gleich gebaut, nur Typ und `count` ändern sich.

---

## 4. Marcos Frage: was wird aus der MIPS im Selfrefresh? (Aufgabe B)

### 4.1 Die ARISC weiß nichts von der MIPS (nachgeprüft)

Im gesamten Disassemblat (44032 Zeilen) kommt **keine** MIPS-Adresse vor:

| Gesucht | Treffer |
|---|---|
| `0x02001600` (MIPS-Takt), `0x0200160c` (MIPS-Reset) | `l.ori …,0x1600` = 0, `…,0x160c` = **0** |
| `0x0306101c/1024/1028/1030` (Status, Share-Adresse, Share-Größe, Bootadresse) | `l.movhi …,0x0306` = **0** im ganzen Blob |
| DRAM-Fenster `0x4b10…`, `0x4be0…`, `0x4bf4…`, `0x4d94…`, `0x4e30…` | je **0** |
| **Positivkontrolle:** `l.movhi …,0x0200` (CCU) | **20** Treffer, z. B. `0x02001010`, `0x02001020`, `0x02001028`, `0x0200171c`, `0x02001540`, `0x0200180c` |

Die Messung könnte einen Treffer zeigen — sie zeigt nur keinen für die MIPS.
**Die ARISC hält die MIPS weder an noch startet sie sie.** Sie kann es auch nicht sinnvoll:
`vdd-cpu`, `vdd-sys`, `vcc-pll` und `vcc-dram` liegen im Stock-`standby_param` alle auf demselben
Pin `PL6` (`re/vendor/HY310/extracted/dtb_extracted/hy310-board.dts`:2548-2558), der Kern bleibt
also unter Spannung, weil das DRAM es muss.

### 4.2 Der Stock erledigt es im Kernel — und zwar vollständig

`re/vendor/HY310/extracted/kallsyms.txt` (UTF-16LE) hat den kompletten Satz:

| Symbol | Adresse | Größe | Zeile |
|---|---|---|---|
| `mips_reset` | `c05d4cfc` | 416 B | 26778 |
| `mipsloader_resume` | `c05d4e9c` | **44 B** | 26779 |
| `mipsloader_probe` | `c05d4ec8` | 488 B | 26780 |
| `mips_powerdown` | `c05d50c0` | 244 B | 26782 |
| `mipsloader_suspend` | `c05d51b4` | **44 B** | 26783 |
| `mipsloader_pm_ops` | `c0ea9300` | — | 55746 |

(Größen = Abstand zum nächsten Symbol, die Tabelle ist nach Adresse sortiert.) 44 Byte sind
Prolog + ein Aufruf + Rücksprung: **`mipsloader_suspend` ist ein Mantel um `mips_powerdown`,
`mipsloader_resume` einer um `mips_reset`.** Die einzigen `request_firmware`-Symbole im Stock sind
der Kern-Lader (`c05c0458`-`c05c0fb8`, :26319-26331) und eine Kopie in `[ge2d_dev]` (:126119) —
in `c05d49xx…c05d51xx` keines. Das Abbild kommt über `mipsloader_ioctl` (`c05d51e0`, :26784) aus
dem Userspace, wie in `legacy/drivers/Archived/sunxi-mipsloader.c`:249-307 (`request_firmware` +
`memcpy_toio`) und :318-327 (Reset `MIPS_REG_CONTROL` 0x01 → 0x00).

Die Nachbarn haben ebenfalls PM-Rückrufe — `cpu_comm_pm_ops` (:123948), `tvtop_runtime_pm_ops`
(:129955), `dec_suspend`/`dec_resume` (:125481/:125497) —, aber **die eigentliche Arbeit steckt
im `mipsloader`** (Inhalte siehe §4.3).

### 4.3 Unser Baum hat davon nichts

* **Kein `mipsloader` in mainline.** In `mainline/patches/kernel/` (117 Patches) gibt es keinen
  MIPS-Ladetreiber; `mipsloader` kommt nur als Wort in `0014` und `0024` vor. Geladen wird
  ausschließlich aus U-Boot: `mainline/external/u-boot/arch/arm/mach-sunxi/h713_mips.c`.
* **`cpu_comm` hat keine PM-Ops.** `platform_driver` mit nur `.probe`/`.remove`
  (`mainline/patches/kernel/0014-soc-sunxi-add-cpu-comm-ipc.patch`:2903-2911). Die Funktionen
  `cpu_comm_suspend`/`cpu_comm_resume` (:1997-2008) sind ein **Zähler**, den der ioctl setzt
  (:1300, :1136) — kein Aufruf vom PM-Kern. Im Stock sind dieselben Namen echte Rückrufe an
  `cpu_comm_pm_ops` und deutlich größer (`bf0e35e4`, ~248 B; `bf0e388c`, 172 B; kallsyms
  :123893/:123901/:123948).
* **`tvtop` und `decd` haben PM-Ops, die nichts leisten.**
  `0012-misc-add-sunxi-tvtop.patch`:888-891 (`.suspend`/`.resume`/`.complete`), `.pm` :934 —
  die Rückrufe protokollieren nur, `sunxi_tvtop_complete` ruft `sunxi_smc_refresh_hdcp()`
  (`legacy/drivers/tvtop/sunxi_tvtop_drv.c`:363-403, `.pm` :448).
  `0013-misc-add-sunxi-decd.patch`:36-37 hat nur `RUNTIME_PM_OPS` (`legacy/drivers/decd/decd_core.c`:31-32,
  `.pm` :244), also gar keinen System-Sleep-Pfad. `0094-media-sun50i-h713-hdmirx.patch` hat
  überhaupt keine PM-Ops (Suche nach `dev_pm_ops`/`.suspend`/`.resume`/`.pm =`: kein Treffer).
* **`cpu_comm` adoptiert eine laufende MIPS.** `mips_was_running = mc && (readl(mc+0x1c) & BIT(0))`
  (:2100), und dann „Takt/Reset/Share-Regs bleiben unberührt" (:2104); Share-Register werden nur
  geschrieben, wenn die MIPS **nicht** lief (:2269-2284); `cpu_comm_shmem_adopted = valid &&
  mips_up && !force_init` (:2256). Der Treiber ist also auf „läuft schon" gebaut, nicht auf
  „wurde unter mir neu gestartet".
* **Der Speicher überlebt.** `mips-firmware@4b100000` (0xe41000), `framebuf@4bf41000`,
  `decoder@4d941000`, `cpu-comm@4e300000` sind alle `no-map` (`0024-…-board.patch`:63-98).
  Selfrefresh hält den Inhalt; der Kernel fasst ihn nicht an.
* **Die Startsequenz** (U-Boot, `h713_mips.c`): `h713_mips_release_reset()` :3541-3567 —
  `0x02001600 = 0x80000002`, dann `0x0200160c` in den Stufen `0`, `0x00010000`, `0x00030000`,
  `0x00030001`, je 12 ms, Share-Register `0x03061024`/`0x03061028`, Bootadresse
  `0x03061030 = 0x4b100000`, zuletzt `0x0200160c = 0x00070001`. Anhalten:
  `h713_mips_stop()` :2669-2676 (Reset auf 0, 12 ms, Takt aus).

### 4.4 Antwort

**Die MIPS kann den Selfrefresh nicht überleben, und die ARISC hält sie nicht an.** Code, BSS,
Heap und der CPU_COMM-Bereich liegen im DRAM (§4.3), im Selfrefresh antwortet der Controller
nicht, und ihr Takt bleibt an (§4.1) — sie liefe gegen ein stehendes DRAM. Der Stock löst das
**vor** dem `WFI` auf der ARM-Seite (`mipsloader_suspend` → `mips_powerdown`) und danach mit
`mipsloader_resume` → `mips_reset` (§4.2). Das Bild kommt im Stock also nicht von selbst zurück,
sondern weil der Kernel den Coprozessor neu startet — und der Resume läuft nie durch U-Boot.

---

## 5. Empfehlung für Plan 104

**Variante „Reset + Neustart aus dem Kernel/Userspace"**, wie im Stock. Nicht „MIPS weiterlaufen
lassen" (physikalisch unmöglich), nicht „ARISC lädt neu" (die Firmware kennt die MIPS nicht,
das wäre Firmware-Arbeit und widerspricht H4 „Stock-`scp.bin` unverändert").

Konkret als neues Paket **H7** neben H1–H6:

1. **Vor dem Suspend** (Reihenfolge des Stock): `hy310-tv` stoppt Capture und Audio (H5), dann
   MIPS parken — `0x0200160c = 0` und `0x02001600 = 0`, das ist `h713_mips_stop()`.
2. **Nach dem Resume:** Abbild wieder herstellen. `display.bin`, die vier `.TSE` und das
   `cfg`-Fenster neu in die Carveouts schreiben (die U-Boot-Reihenfolge aus `h713_disp_load_tse()`
   :5933-5972 ist bindend), Workspace löschen wie `h713_mips_clear_workspace()`, dann die
   Reset-Treppe aus §4.3. **Nur `mips_reset` ohne Neuladen ist nicht belegt** — unser eigener
   U-Boot-Kommentar (`h713_mips.c`:52-58 und :3670 ff.) sagt, dass ein nicht gelöschter
   BSS/Heap Läufe unreproduzierbar macht.
3. **`cpu_comm` neu aufsetzen:** die ARM-Seite muss ihre Sitzung wegwerfen und wie beim Kaltstart
   initialisieren (heute nur über `force_init`, :2108/:2262). Ohne das zeigen Kanaltabelle,
   Sequenznummern und Rückruf-Slots auf einen Zustand, den es nicht mehr gibt.
4. **Ort:** ein kleiner `h713-mipsloader`-Treiber mit `dev_pm_ops` — genau die Lücke, die der
   Stock mit `mipsloader_pm_ops` füllt. Ein `/dev/mem`-Werkzeug in `hy310-tv` ginge auch, muss
   aber die `no-map`-Carveouts erst abbilden und läuft nach `cpu_comm`.
5. **Erste Messung ohne Bild:** Stufe 2 zuerst mit geparkter MIPS und dunklem Panel messen
   (Verbrauch, Weckzeit, 20 Zyklen); den Neustart des Coprozessors erst danach dranhängen, sonst
   vermischen sich zwei Fehlerquellen.

## 6. Risikoliste, fortgeschrieben

| Nr | Risiko | Stand |
|---|---|---|
| **R7** | MIPS im gehaltenen DRAM | **Geklärt** (§4.4): sie läuft nicht weiter, muss neu gestartet werden. Aus der offenen Frage wird Paket H7. |
| **R9** *(neu)* | `cpu_comm`-Zustand nach dem MIPS-Neustart: Kanaltabelle, Sequenzzähler, Rückruf-Slots (bekannter Slot-Leck-Pfad, Patch 0124) zeigen ins Leere | Neu-Init-Weg fehlt; heute nur `force_init` |
| **R10** *(neu)* | Kein `mipsloader` in mainline — es gibt gar keine Stelle, die nach dem Resume laden könnte | Treiber oder Werkzeug muss erst entstehen |
| **R11** *(neu)* | U-Boots „ein Start je Netzzyklus": ein zweiter Lauf ohne Teardown initialisiert in einen halb abgebauten Zustand (`h713_mips.c`:10369 ff., :5717) | Teardown vor dem Suspend muss die Regel erfüllen |
| **R12** *(neu)* | Panel-Sequenz beim Resume (PF6/PH16, LVDS, INCAP) — U-Boot macht das heute, der Resume kommt dort nie vorbei | Ablauf aus `h713_disp_run()` nachbauen |
| **R13** *(neu)* | `0xc7c8` akzeptiert nur eine einzige Quellenkennung (§1) | Am Gerät gegen die echte Weckquelle prüfen, sonst wird nichts eingetragen |
| R1 | `arisc_para` ab `+0x4c` | unverändert offen |
| R2 | Rahmen `count`+Zeiger | **erledigt** durch §3: Kopfwort, `count`, `count` Datenwörter |
| R6 | kein Watchdog, DRAM-CRC-Endlosschleife | unverändert: jeder Versuch mit UART und Steckdose |
| R8 | FEL als Rückweg | unverändert offen |

## 7. Was noch offen ist

* `0xc7c8`: warum nur `0xffffffe0`? (R13)
* Felder **B**/**C** von `set_wakeup_src`: im Standby-Zweig ungenutzt — welcher andere Zweig liest sie?
* Ob `mips_reset` im Stock das Abbild mitkopiert: dazu müsste `c05d4cfc` aus dem Stock-`vmlinux`
  disassembliert werden (`boot.fex.gz`). Nicht in dieser Sitzung.
* `0x0701033c` Bit 27..24, das die Warteschleife um den Doze herum setzt und löscht (§2).
