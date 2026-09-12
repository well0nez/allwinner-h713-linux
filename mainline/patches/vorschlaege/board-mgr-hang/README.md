# Warum `hy310-board-mgr` das Gerät aufhängt — Befund und Fix

Unteragent, 11.09.2026. **Kein Board angefasst** (kein `ssh`, kein `scp`, kein UART, kein
Stromzyklus). Geschrieben wurde nur in dieses Verzeichnis; `mainline/patches/kernel/`,
`series` und die Referenzbäume unter `mainline/build/` sind unberührt. Gebaut wurde
ausschließlich im Container `h713-build`, in der Wegwerfkopie
`mainline/build/pruefbau-hang` (Kopie von `linux-6.18.38-9e4e34bc…`, dem Baum aus dem
Mitschnitt).

Sprachregelung: **belegt** = Adresse im Disassemblat des Hersteller-`vmlinux` oder
Datei:Zeile im Quelltext. **Erschlossen** = aus Belegtem zusammengesetzt, ohne eigene
Messung. **Vermutung** = weder noch.

| Datei | | sha256 |
|---|---|---|
| `0143-pinctrl-sunxi-index-the-bank-interrupts-by-irq-bank-not-by-hardware-bank.patch` | **der Fix**, 145 Zeilen | `4b5ce1e3071d084ecc9443629b823cbe96a77b00bead6747dc95e96444158994` |
| `0144-arm64-dts-h713-the-pio-has-seven-bank-interrupts-not-nine.patch` | DTS, Beschreibung richtigstellen, 61 Zeilen | `fe0ef1d848b645478a7352bbe3a290e0054d1c7206eed9348a8047480bbd575c` |
| `DIAGNOSE-sunxi-pio-mask-a-parent-with-empty-status.patch` | **nicht für die Serie**, nur falls es wieder hängt, 55 Zeilen | `61f036964ffd23423cc13425199a8f996c5ed00a97f5b1f9c99bcaf44361b9ca` |

Alle drei mit `patch -p1` gegen `linux-6.18.38-9e4e34bc…` geprüft: angewandt, kein Fuzz,
keine Zurückweisung — einzeln und in der Reihenfolge 0143 → 0144 → DIAGNOSE.

---

## 1. Die Ursache in fünf Sätzen

Der Elternschaftsinterrupt der PIO-Bank **PH** wird in unserem Baum an der falschen
GIC-Leitung abgeholt. Patch `0004` hat die Zeile

```c
pctl->irq[i] = platform_get_irq(pdev, i);
```

zu `platform_get_irq(pdev, hw_bank)` gemacht, liest die `interrupts`-Liste des
Gerätebaums also als **eine Zeile pro Hardware-Bank**; sie ist aber **eine Zeile pro
IRQ-Bank**, in der Reihenfolge von `irq_bank_map`. Der H713 hat sieben IRQ-Bänke —
`irq_bank_map = {0,1,2,3,5,6,7}`, also PA PB PC PD **PF** PG PH, mit einer Lücke bei 4
(PE, hat auf diesem SoC gar keine Pins) —, und die sieben Leitungen GIC-SPI 54…60 gehören
lückenlos diesen sieben Bänken. Durch die Lücke rutscht mit `hw_bank` jede Bank hinter PE
eine Leitung zu hoch: der verkettete Handler, der sich für PH hält, sitzt auf SPI 61
(dort passiert nie etwas), und auf der echten PH-Leitung SPI 60 sitzt der Handler, der
sich für **PG** hält. Hebt `hy310-board-mgr` beim `request_irq` die EINT-Maske von PH17
auf, zieht die PIO SPI 60 hoch, der „PG"-Handler liest PG-Status (`0x2D4`) = 0, löscht
nichts, kehrt zurück — und weil die GIC ein *fasteoi*-Chip ist, maskiert
`chained_irq_enter()` nichts und `chained_irq_exit()` macht nur EOI: die Leitung bleibt
oben, die CPU nimmt denselben Interrupt sofort wieder. **Endlos.**

```
Bank        gewollt   mit 0004
PA  (hw 0)  SPI 54    SPI 54    ok
PB  (hw 1)  SPI 55    SPI 55    ok
PC  (hw 2)  SPI 56    SPI 56    ok
PD  (hw 3)  SPI 57    SPI 57    ok
PF  (hw 5)  SPI 58    SPI 59    ← das ist PG
PG  (hw 6)  SPI 59    SPI 60    ← das ist PH
PH  (hw 7)  SPI 60    SPI 61    ← das ist nichts
```

Der Tachometer-Interrupt war also die richtige Spur, aber nicht aus dem vermuteten Grund:
**nicht** der Mux `0xe`, **nicht** die Flankenart, **nicht** PH gegen PL — sondern die
Zuordnung Bank → GIC-Leitung eine Ebene darunter. Deshalb war auch nichts zu sehen: der
Kind-Interrupt 230 wird nie erreicht (Zähler bleibt 0), und ein verketteter
Elterninterrupt wird in `/proc/interrupts` weder gezählt noch überhaupt aufgeführt —
`show_interrupts()` in `kernel/irq/proc.c` schließt ihn ausdrücklich aus:
`if (!desc->action || irq_desc_is_chained(desc) || !desc->kstat_irqs) return 0;`.
Die stürmende Leitung ist vom Userspace aus vollständig unsichtbar.

## 2. Woran das hängt — Belegkette

**a) Der Hersteller-Treiber macht es indexbasiert.** Im Hersteller-`vmlinux`
(`re/vendor/HY310/extracted/vmlinux.elf`, ARM32, mit DWARF) steht in
`sunxi_pinctrl_init_with_variant`:

```
c0548548  ldr r8, [r4, #0x90]       ; pctl->irq
c054854c  mov r1, sb                ; r1 = i   (der Schleifenzähler!)
c0548550  mov r0, r7                ; pdev
c0548554  bl  #0xc05abd38           ; platform_get_irq
c0548558  str r0, [r8, sb, lsl #2]  ; pctl->irq[i] = ret
c054855c  ldr r3, [r4, #0x90]
c0548560  ldr r8, [r3, sb, lsl #2]
c0548564  cmp r8, #0
c0548568  blt #0xc0548528           ; Fehlerpfad
c054856c  add sb, sb, #1
c0548570  ldr r3, [r4, #8]          ; pctl->desc
c0548574  ldr r2, [r3, #0xc]        ; desc->irq_banks
c0548578  cmp r2, sb
c054857c  bhi #0xc0548548
```

Zwanzig Befehle weiter, in derselben Funktion, ruft die Masken-/Löschschleife für die
**Registeroffsets** sehr wohl den hw-Bank-Helfer auf (`bl #0xc05475a0`, dann `lsl #5` und
`+0x210` bzw. `+0x214`, `c0548640`–`c0548688`). Der Hersteller unterscheidet die beiden
Zahlen sauber; `0004` hat sie zusammengeworfen. *Belegt.*

**b) Die Tabellen sind identisch mit unseren.** `sun50iw12_irq_bank_map` (`c0e9d894`,
28 Byte) = `{0,1,2,3,5,6,7}`, `sun50iw12_pinctrl_data` (`c0e9d814`) hat `npins = 132`,
`irq_banks = 7`, `irq_read_needs_mux = 0`. Unser `h713_irq_bank_map` ist dieselbe Folge.
*Belegt.*

**c) Es gibt PE und PI auf diesem SoC nicht.** `sun50iw12_pins` (`c0e9d8b0`, 2640 Byte,
132 Einträge à 20 Byte) endet bei PH19; es gibt PA0–PA12, PB0–PB6, PC0–PC16, PD0–PD30,
PF0–PF28, PG0–PG14, PH0–PH19 — **kein einziger PE- und kein PI-Pin**. Der Kommentar
„Stock: GIC_SPI 54-62 for PA-PI banks" in unserer `sun50i-h713.dtsi` beschreibt also
Bänke, die es nicht gibt. *Belegt.*

**d) Der Hersteller benutzt genau diesen Weg für genau diesen Pin.** `pwm_fan_probe`
(`c05d9738`) ruft `gpiod_to_irq` (`c05d9ff4` → `c0549868`) und übergibt das Ergebnis an
`request_threaded_irq` mit `flags = 3` (beide Flanken, `mov r3, #3` bei `c05da034`).
Und: **kein** Knoten im Hersteller-Gerätebaum hat `interrupt-parent` auf den `pio`
(Phandle `0x2c`) oder den `r_pio` (`0x18`) — nur `0x01` und `0x08` kommen vor,
`interrupts-extended` gar nicht. PH17 über `pwm_fan` ist damit der **einzige**
Haupt-PIO-EINT-Nutzer des Serienkernels. Der Serienkernel holt dafür
`platform_get_irq(pdev, 6)` = SPI 54+6 = **SPI 60**. *Belegt (Code) + erschlossen (dass
er funktioniert).*

**e) Mainline macht es genauso, und die Gerätebäume passen dazu.** Der H616 hat dieselbe
Lückenform — `irq_bank_map = {1,2,3,5,6,7,8}`, Lücke bei 4 — und sein `pio`-Knoten listet
**sieben** aufeinanderfolgende Leitungen (GIC-SPI 51…57) für diese sieben Bänke, nicht
neun. *Belegt (Quelltext im Baum).*

**f) Der entscheidende, von der Silizium-Frage unabhängige Punkt.** Die
`interrupts`-Liste in unserer `sun50i-h713.dtsi` **ist Herstellerdatum** — sie wurde aus
`bootpkg-full.dts` übernommen (dort `<0x00 0x36 0x04 … 0x00 0x3e 0x04>` = SPI 54…62).
Herstellerdaten müssen so gelesen werden, wie der Hersteller sie liest. Sein Leser ist
indexbasiert und schaut nur die ersten sieben Einträge an. Eine übernommene Liste mit
einer anderen Indexkonvention zu lesen ist per Konstruktion falsch, ganz gleich, welche
SPI physisch welche Bank ist. *Erschlossen, aber zwingend.*

**g) Der Zeitpunkt passt auf die Millisekunde.** `CONFIG_HZ=250` und
`CONFIG_RCU_CPU_STALL_TIMEOUT=21` im `.config` des Baums. Die erste Meldung kommt bei
147,408 s mit `t=5254 jiffies` → 21,016 s → Beginn **126,392 s**. Im dmesg steht die
Tacho-Zeile („tachometer IRQ 230") bei **126,356 s** und die letzte Probe-Zeile bei
126,393 s. Der Stillstand beginnt also in genau dem Moment, in dem `devm_request_irq()`
die EINT-Maske von PH17 aufhebt. Die zweite Meldung (210,444 s, `t=21013`) rechnet auf
126,392 s zurück — derselbe Punkt. *Belegt.*

**h) Das Registerbild aus dem Mitschnitt passt zum Sturm, nicht zum Aufhänger.**
`pc : arch_local_irq_enable+0x8/0xc`, `lr : default_idle_call+0x24/0x30`. Im gebauten
`vmlinux` desselben Baums ist `default_idle_call+0x20` das `bl arch_local_irq_enable` und
`+0x24` die Rücksprungadresse; `arch_local_irq_enable` ist 12 Byte lang, `+0x8` ist der
Befehl **unmittelbar nach** dem `msr daifclr`. Genau dort landet eine CPU, die aus dem
`wfi` kommt und beim Entmaskieren sofort wieder einen Interrupt bekommt. Dazu passt
`idle=…/1/0x4000000000000002`: `ct_idle_exit()` ist schon gelaufen (nesting 1), und
`nmi_nesting` trägt `DYNTICK_IRQ_NONIDLE|2`, also „Interrupt aus Nicht-EQS-Kernelcode".
Zweimal, 63 s auseinander, an derselben Stelle. *Belegt (Disassemblat), erschlossen (die
Deutung als Sturm).*

**i) Warum es nie vorher aufgefallen ist.** Die einzigen GPIO-Interrupts, die dieser Baum
je angefordert hat, liegen am `r_pio`: die Einschalttaste auf PL4 (`0139`) und
`host-wake` auf PM0 (`sdio_wifi`). `sun50i_h713_r_pinctrl_data` hat **gar keine**
`irq_bank_map`, `sunxi_irq_hw_bank_num()` gibt dort den Index unverändert zurück — beide
Varianten liefern dasselbe. Der Fehler beißt nur am Haupt-PIO und nur hinter der PE-Lücke,
und PH17 ist der erste Pin, den wir dort je angefordert haben. *Belegt (Quelltext).*

## 3. Was der Fix tut

`0143` nimmt in `sunxi_pinctrl_init_with_flags()` die Indizierung zurück auf
`platform_get_irq(pdev, i)` — Mainline-Semantik, Hersteller-Semantik. Der aus `0004`
stammende `-ENXIO`-Pfad („weiter ohne IRQ-Unterstützung") bleibt unverändert erhalten,
nur die Meldung nennt weiterhin die Hardware-Banknummer, weil die für den Leser die
nützlichere Zahl ist. `sunxi_irq_hw_bank_num()` bleibt, wo es hingehört: bei den
Registeroffsets (`sunxi_irq_cfg_reg`, `…_ctrl_reg`, `…_status_reg`, `…_debounce_reg`).

Der zweite Hunk in `0143` ersetzt nur einen Kommentar, der seit `0140` falsch ist
(`irq_read_needs_mux` beschreibt nicht mehr den IRQ-Anforderungspfad).

`0144` kürzt die `interrupts`-Liste des `pio`-Knotens von neun auf die sieben Leitungen,
die es gibt, mit Bankzuordnung als Kommentar. **Das ist Beschreibung, nicht der Fix.**
Mit `0143` allein bootet das Gerät; `0144` allein hilft nicht — die `hw_bank`-Suche
fragte dann nach Index 7, bekäme `-ENXIO` und schaltete die GPIO-Interrupts des gesamten
Haupt-PIO still ab. **Reihenfolge: erst 0143, dann 0144.**

An `hy310-board-mgr` selbst ändert sich **nichts**. `0141` und `0142` bleiben, wie sie
sind; die `.ko` wird von diesem Fix nicht einmal neu übersetzt.

## 4. Was ausgeschlossen wurde, und wie

| Verdacht | Ergebnis | wie |
|---|---|---|
| Mux-Wert `0xe` falsch für den Haupt-PIO (die Arbeitshypothese) | **ausgeschlossen, `0xe` ist richtig** | Hersteller-Pintabelle ausgelesen: PH17 (`num 241`) hat `('irq', 0xe, irqbank 6, irqnum 17)`, PH15/16/18/19 analog, PA0 `('irq',0xe,0,0)`, PL4 `('irq',0xe,0,4)`. Unsere `SUNXI_FUNCTION_IRQ_BANK(0xe, 6, 17)` ist bitgleich. `0140` war richtig. |
| Mux-Umschaltung beim IRQ-Request überhaupt falsch | **ausgeschlossen** | Der Hersteller schaltet sie bedingungslos: `sunxi_pinctrl_irq_request_resources` `c0547b28`, `ldrb r2,[r7,#8]` (= `func->muxval`) → `bl c0547a4c` (`sunxi_pmx_set`). Kein `if`. |
| PH-Bank hat gar keine EINT-Bank / `irq_bank_map` falsch | **ausgeschlossen** | `sun50iw12_irq_bank_map` = `{0,1,2,3,5,6,7}`, identisch mit unserer. |
| Registerkarte (CFG/CTRL/STATUS) für Bank PH verrechnet | **ausgeschlossen** | `0x200 + 7·0x20 + (17/8)·4 = 0x2E8`, Feld `(209 % 8)·4 = 4`; CTRL `0x2F0` Bit 17, STATUS `0x2F4` Bit 17 — alles innerhalb von `reg = <0x02000000 0x800>`. Der Hersteller rechnet identisch (`c0548640`–`c0548688`). |
| Fehlende Takte/Reset der PIO-IRQ-Bank, Power-Domain | **ausgeschlossen** | Der `pio`-Knoten hat `clocks = <&ccu CLK_APB0>, <&osc24M>, <&rtc CLK_OSC32K>`, `devm_clk_get_enabled(…"apb")` im Probe; ohne Takt wären auch die vier funktionierenden Bänke tot und die Registerschreibzugriffe im Probe hätten gehängt. Der Hersteller-Knoten hat dieselben drei Takte. |
| Pegel statt Flanke / falscher `IRQF_TRIGGER_*` | **ausgeschlossen als Hängeursache** | `sunxi_pinctrl_irq_set_type()` wählt bei `IRQ_TYPE_EDGE_*` den `edge`-Chip mit `handle_edge_irq`; der quittiert und maskiert auch einen Kind-IRQ ohne `action`. Ein Pegelfehler beim *Kind* kann den Elterninterrupt nicht ungelöscht lassen — nur ein Handler auf der falschen *Eltern*leitung kann das. |
| Zusammenspiel mit `CONFIG_KEYBOARD_SUN4I_LRADC=y` / IIO-Kanal | **ausgeschlossen** | Der NTC-Pfad ist von `0141` unverändert; er lief im Mitschnitt sauber durch (`NTC via IIO channel acquired`, 63-Einträge-Tabelle) und der Stillstand beginnt 36 ms *danach*, exakt an der IRQ-Anforderung. Zusätzlich schon vom Auftraggeber geprüft. |
| `hy310_ntc_adc_to_temp`, `sun50i_lradc_read` | vom Auftraggeber ausgeschlossen, **bestätigt** | einfache Tabellenschleife bzw. ein einzelnes `readl`. |
| „`fan_work` verstummt nach 8 s" als Hinweis | **Fehlschluss, kein Hinweis** | Die Meldung steht in `if (fan->rpm_warn_cycles == fan->rpm_warn_cnt)` — sie kommt **genau einmal**, bei Zyklus 8. Danach schweigt `fan_work` auch in einem kerngesunden System. Die Zeile belegt nur, dass das System 8 s nach dem Probe noch lief (auf einer anderen CPU als 0). |
| Kind-IRQ 230 feuert doch und stürmt | **ausgeschlossen** | Zähler `0 0 0 0` im Mitschnitt, und `handle_edge_irq` würde quittieren. Der Sturm liegt eine Ebene höher, wo nicht gezählt wird. |

## 5. Was unsicher bleibt

1. **Nicht gemessen: dass PH physisch an GIC-SPI 60 hängt.** Belegt ist, dass der
   Hersteller-Treiber genau diese Zuordnung herstellt und dass der Serienkernel damit den
   Tachometer auf PH17 betreibt. Ein Registerlesen dieses SoCs, das SPI 60 ↔ PH bestätigt,
   gibt es nicht — `CONFIG_STRICT_DEVMEM=y` und `CONFIG_GENERIC_IRQ_DEBUGFS` ist aus, das
   ist vom Userspace aus auch nicht nachzuholen. Falls die Zuordnung anders ist, hängt es
   wieder; dafür ist der `DIAGNOSE`-Patch da (§8).
2. **Nicht gemessen: dass der Tacho danach zählt.** Der Lüfter drehte im Mitschnitt nicht
   („0 RPM"), und genau diese 0 kann auch vom kaputten Interruptweg kommen. Ob nach dem
   Fix eine plausible Drehzahl erscheint, entscheidet sich erst am Gerät (§7, Schritt 5).
   Bleibt es bei 0, ist die nächste Frage der PB5-Lüfterstrang, nicht der Interrupt.
3. **Absolute Drehzahl weiterhin unbestätigt.** `pulses-per-revolution = <2>` mit
   steigenden Flanken ist aus `0141` übernommen und nie gegen einen Referenztacho
   gemessen.
4. **Unsere Pintabelle weicht vom Hersteller ab** (nebenbei aufgefallen, nicht Teil dieses
   Fehlers): wir haben PB7–PB21, die der Hersteller nicht kennt, und es fehlen PF6–PF28.
   Für die Bankzahl und die IRQ-Zuordnung ist das ohne Folgen (die hängen an
   `irq_bank_map`), aber es gehört irgendwann geradegezogen.
5. **`0004` ist nicht nur hier falsch.** Die Änderung betrifft `pinctrl-sunxi.c`, also
   alle sunxi-SoCs im Baum. Für uns ist nur der H713 relevant; dass der Rückbau die
   Mainline-Semantik wiederherstellt, ist geprüft (H616-Gerätebaum im Baum, sieben
   Zeilen für sieben Bänke), aber kein anderes Board ist gebaut worden.

## 6. Bauprobe

Wegwerfbaum `mainline/build/pruefbau-hang` (`cp -a` von
`linux-6.18.38-9e4e34bc09211defe2ef9142905bfc45fb7fad8c3e2a19390e5b5f0a9a112f2a`), alle
drei Dateien von Hand auf den Stand der Patches gebracht, dann:

```
$ podman exec h713-build bash -lc 'cd /work/mainline/build/pruefbau-hang && \
    touch drivers/pinctrl/sunxi/pinctrl-sunxi.c && \
    make ARCH=arm64 LLVM=1 -j"$(nproc)" Image dtbs modules 2>&1 | tail -12; \
    echo "EXIT=${PIPESTATUS[0]}"'
  AS      .tmp_vmlinux1.kallsyms.o
  LD      .tmp_vmlinux2
  NM      .tmp_vmlinux2.syms
  KSYMS   .tmp_vmlinux2.kallsyms.S
  AS      .tmp_vmlinux2.kallsyms.o
  LD      vmlinux.unstripped
  NM      System.map
  SORTTAB vmlinux.unstripped
  OBJCOPY vmlinux
  GEN     modules.builtin.modinfo
  GEN     modules.builtin
  OBJCOPY arch/arm64/boot/Image
EXIT=0
```

Keine Warnung in den beiden geänderten Übersetzungseinheiten:

```
  CC      drivers/pinctrl/sunxi/pinctrl-sunxi.o
  CC      drivers/pinctrl/sunxi/pinctrl-sun50i-h713.o
```

Der DTB trägt danach sieben statt neun Bank-Interrupts:

```
$ ./scripts/dtc/dtc -I dtb -O dts arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713df-a1.dtb \
    | awk '/pinctrl@2000000 \{/,/mmc2-pins/' | grep interrupts
  interrupts = <0x00 0x36 0x04 0x00 0x37 0x04 0x00 0x38 0x04 0x00 0x39 0x04
                0x00 0x3a 0x04 0x00 0x3b 0x04 0x00 0x3c 0x04>;
```

`0x36`…`0x3c` = 54…60. Der `DIAGNOSE`-Patch übersetzt ebenfalls sauber (separat geprüft,
`CC drivers/pinctrl/sunxi/pinctrl-sunxi.o`, `EXIT=0`); er ist im Baum nicht enthalten.

Anwendungsprobe gegen den unveränderten Referenzbaum:

```
$ patch -p1 --dry-run < 0143-….patch
checking file drivers/pinctrl/sunxi/pinctrl-sunxi.c
checking file drivers/pinctrl/sunxi/pinctrl-sun50i-h713.c
$ patch -p1 --dry-run < 0144-….patch
checking file arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi
```

Der Wegwerfbaum kann weg: `podman exec h713-build bash -lc 'rm -rf /work/mainline/build/pruefbau-hang'`.

---

## 7. Testanleitung

Voraussetzung: `0143` und `0144` in die Serie aufgenommen (hinter `0142`), Kernel neu
gebaut (`mainline/build/build.sh kernel`), Image + DTB + Module aufgespielt wie üblich.
`&board_mgr` bleibt auf `okay`, **kein** `modprobe.blacklist` in den Bootargs.

Das kostet **einen** Stromzyklus für den Haupttest. Die Schritte 3–6 laufen alle in
derselben Sitzung.

### Schritt 1 — vor dem Einschalten: was erwartet wird

* Der Boot läuft durch. Die Marke ist `random: crng init done` — beim gesunden Lauf vom
  11.09. bei **t = 6,03 s**; erwartet wird wieder eine einstellige Sekundenzahl.
* `systemd-random-seed` läuft **nicht** in den 10-Minuten-Timeout.
* Es kommt **kein** `rcu_sched self-detected stall`.
* Die Probe-Zeilen von `hy310-board-mgr` kommen wie gehabt, insbesondere
  `fan0: tachometer IRQ 230, 2 pulses/rev`. **Ab hier lief es bisher auseinander** —
  wenn nach dieser Zeile noch mehr kommt und die Konsole ansprechbar bleibt, ist es
  vorbei.

### Schritt 2 — Misserfolg früh erkennen

Wenn die Konsole nach `HY310 board manager probed: …` verstummt und ~21 s später ein
`rcu: INFO: rcu_sched self-detected stall on CPU` mit `Comm: swapper/0` kommt: **es hängt
wieder**, weiter bei §8. Nicht auf die 10 Minuten warten, der Mitschnitt sagt dann schon
alles.

### Schritt 3 — Läuft es?

```sh
uptime
dmesg | grep -iE "crng init|board-mgr|rcu:|stall"
```

Erwartet: `crng init done` mit kleiner Zeitmarke, die board-mgr-Zeilen, **keine**
`rcu:`-Zeile.

### Schritt 4 — hat sich an den Interrupts etwas verschoben?

```sh
grep -E "^ *230:|CPU0" /proc/interrupts
```

Erwartet: die Zeile ist da wie vorher —
`230: … sunxi_pio_edge 209 Edge hy310-fan-tach`. Der Zähler sagt hier noch nichts; die
verketteten Elternleitungen (SPI 54…60) tauchen in `/proc/interrupts` **grundsätzlich
nicht** auf (`show_interrupts()` überspringt `irq_desc_is_chained()`), das ist kein
Fehler.

### Schritt 5 — zählt der Tachometer?

```sh
for h in /sys/class/hwmon/hwmon*; do echo "$(basename $h)=$(cat $h/name)"; done
H=$(grep -l '^hy310' /sys/class/hwmon/hwmon*/name | xargs -r dirname)
cat $H/temp1_input $H/fan1_input
sleep 10
grep -E "^ *230:" /proc/interrupts
cat $H/fan1_input
```

Drei mögliche Ausgänge:

* **Zähler steigt, `fan1_input` > 0** — der Interruptweg trägt, der Lüfter dreht. Damit
  ist der Fix vollständig bestätigt: Ursache weg *und* Funktion da.
* **Zähler bleibt 0, `fan1_input` = 0, System lebt** — der Fix hat das Aufhängen behoben,
  aber es kommen keine Flanken. Dann dreht der Lüfter nicht (PB5-Strang, siehe `0030`)
  oder PH17 ist nicht die Tacho-Leitung dieses Geräts. **Kein Rückschritt** und kein Grund,
  `0143` anzuzweifeln: vorher hing es an derselben Stelle. Nächster Schritt wäre dann,
  den Lüfter selbst zu prüfen, nicht den Treiber.
* **System stirbt hier** — §8.

`temp1_input` sollte in beiden lebenden Fällen einen plausiblen Wert liefern (Milligrad,
also z. B. `42000`); der ist vom Interrupt unabhängig und war auch vorher schon da.

### Schritt 6 — hält es?

```sh
sleep 120; uptime; dmesg | grep -c "rcu_sched self-detected"
```

Erwartet: `0`. Der Stall trat im Mitschnitt 21 s nach der IRQ-Anforderung auf; zwei
Minuten sind reichlich Sicherheitsabstand.

---

## 8. Wenn es wieder hängt

Dann ist §5.1 eingetreten: die PH-Bank hängt nicht an SPI 60. Der Fix ist dann nicht
falsch (die Indexkonvention bleibt die des Herstellers), aber die Liste im Gerätebaum
stimmt nicht.

**Zuerst wieder hereinkommen:** Bootargs um `modprobe.blacklist=hy310_board_mgr`
ergänzen, wie am 11.09.

**Dann messen statt raten.** `DIAGNOSE-sunxi-pio-mask-a-parent-with-empty-status.patch`
anwenden (zusätzlich zu `0143`/`0144`, er fasst eine andere Stelle derselben Datei an),
neu bauen, **ohne** Blacklist booten. Der Patch verwandelt die Endlosschleife in eine
Logzeile: ein Elterninterrupt, dessen Bank-Statusregister leer ist, wird an der GIC
maskiert und gemeldet:

```
sunxi-pio: parent irq N (bank index B, hw bank H, status reg 0xR) asserted with an
empty status register -- masking it
```

Das Gerät bleibt dabei am Leben. Die Zahl `N` ist eine Linux-virq; die dazugehörige
GIC-Leitung ist `54 + B` mit der jetzigen Liste, also verrät `B` unmittelbar, **welche**
Leitung die PIO wirklich hochgezogen hat, als PH17 gezuckt hat. Die gesuchte Zuordnung
ist dann: PH gehört an die Leitung, die in der `interrupts`-Liste an Position `B` steht.

Danach `0144` entsprechend anpassen (die Leitung an Position 6 setzen, bei der `B`
gemeldet wurde, und die übrigen sechs entsprechend nachziehen) und den `DIAGNOSE`-Patch
wieder entfernen — er würde sonst bei einer einzelnen Störflanke eine ganze Bank
stilllegen.

**Falls stattdessen gar nichts passiert** (System lebt, keine `sunxi-pio:`-Zeile, Zähler
230 bleibt 0): dann zieht PH17 überhaupt keine Flanke, und der Verdacht wandert vom
Interruptweg zum Pin — Lüfter aus, falscher Pin, oder der EINT-Entpreller
(`IRQ_DEBOUNCE_REG 0x218 + hw_bank·0x20`) samt seiner Taktwahl. Das ist dann ein neuer
Auftrag und kein Rückschritt: das Aufhängen wäre damit trotzdem erledigt.
