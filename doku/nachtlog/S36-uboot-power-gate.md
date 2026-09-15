# S36 - U-Boot: Einschalt-Gate (Paket G1 aus Plan 103)

**Stand 09.09.2026, Agent in der Kopie `analyse/boot/arbeit/g1-uboot/`.** Geliefert:
`analyse/boot/arbeit/g1-uboot/patches/0013-sunxi-h713-power-gate.patch` (unified diff, `-p1`, Pfade `a/…` `b/…` wie im Originalbaum).
Der Patch wurde gegen `mainline/external/u-boot` (HEAD `cbcbf10af04`) erzeugt und in einer Wegwerfkopie mit `patch -p1` probeweise
angewandt: sechs Dateien, keine Zurückweisung, kein Fuzz; das Ergebnis ist byteidentisch mit den geänderten Kopien.
**Nicht gebaut** (Regel: kein Bau, kein Board). Der Gate-Code wurde ersatzweise mit Stubs `gcc -fsyntax-only -Wall -Wextra`
durchgelassen - das prüft Syntax und Typen, **nicht** die U-Boot-API.

## 1. Was der Patch tut

Sechs Dateien:

| Datei | Änderung |
|---|---|
| `arch/arm/mach-sunxi/Kconfig` | neues `config H713_POWER_GATE`, `depends on H713_POWERON_LIGHT_FAN`, Vorgabe aus |
| `board/sunxi/board.c` | `h713_power_gate()` + drei Helfer, Aufruf in `board_late_init` **vor** `h713_poweron_lines()`; zwei neue Includes (`<time.h>` für `get_timer`, `<watchdog.h>` für `schedule()`) |
| `configs/hy310_qz713_v3_1_defconfig` | `CONFIG_H713_POWER_GATE=y` |
| `configs/hy310_netboot_defconfig`, `…_host_…`, `…_felmmc_…` | `# CONFIG_H713_POWER_GATE is not set` |

Kein LED-Code, kein Devicetree-Knoten, kein `CONFIG_BUTTON`, kein `CONFIG_LED`. Rohes DM-GPIO wie in der Vorgabe.

### Ablauf in `board_late_init`

```
h713_power_gate()          <-- neu
h713_poweron_lines()       <-- unverändert, PB5 + PL3 auf 1
usb_ether_init()           <-- unverändert
```

`h713_power_gate()` in Reihenfolge:

1. **Env**: `env_get("h713_gate")`. Genau der Wert `"0"` schaltet das Gate ab (`gate: off (h713_gate=0)`); alles andere und ein
   fehlender Eintrag lassen es an. Bewusst ein String-Vergleich und nicht `env_get_ulong`: ein Tippfehler in der Variablen soll
   nicht als „0" durchgehen und das Gate stillschweigend ausschalten.
2. **GP5 lesen** (`readl(0x07090114)`):
   - `0x52554E31` „RUN1" → `gate: warm start, booting`, kein Gate.
   - `0x47415445` „GATE" → `gate: power-off requested`, Gate.
   - alles andere (im Normalfall 0) → `gate: cold start (GP5 %08x)`, Gate.
3. **Taste holen**: `dm_gpio_lookup_name("PL4")` → `dm_gpio_request(…, "power-key")` (`-EBUSY` wird wie in
   `h713_poweron_lines()` toleriert) → `dm_gpio_set_dir_flags(GPIOD_IS_IN)` → **eine Probelesung**. Schlägt irgendetwas davon
   fehl: `gate: power key PL4 unavailable (%d), booting` und **kein** Gate. Begründung im Code: ohne lesbare Taste gäbe es keinen
   Weg aus der Schleife.
4. **Service-Hintertür**: ist PL4 beim Eintritt schon gedrückt und bleibt es 3 s lang durchgehend gedrückt (Abtastung 10 ms),
   dann `gate: key held at power-on, bypass`, kein Gate. Ist die Taste beim Eintritt nicht gedrückt, kostet dieser Schritt
   keine Zeit.
5. **Gate-Schleife** (`h713_gate_wait()`): einmal `gate: waiting for power key`, dann alle 10 ms PL4 lesen. Kein Timeout.
   Freigabe erst nach einem **vollständigen Tastenhub**: erst muss die Leitung 50 ms ruhig hoch gewesen sein (`idle_seen`),
   dann 50 ms entprellt tief (`pressed`), dann wieder 50 ms hoch - erst das Loslassen bricht die Schleife. Damit startet weder
   eine beim Einschalten gehaltene Taste noch ein zu langer Druck den Boot in dem Moment, in dem das Gate aufgeht.
   Alle 60 s ein `.` auf der Konsole (kein Spam), am Ende ein `\n`, falls Punkte gedruckt wurden. In jedem Schleifendurchlauf
   `schedule()` (das ist in diesem U-Boot der Nachfolger von `WATCHDOG_RESET()`; `<watchdog.h>` zieht `<u-boot/schedule.h>`).
   Danach `gate: power key, booting`.
6. **Immer, auf jedem Pfad**: `writel(0x52554E31, 0x07090114)` - unmittelbar vor der Rückkehr, also vor `h713_poweron_lines()`.
   Reboot, Absturz und Watchdog-Reset danach finden RUN1 und booten durch.

Die Taste wird **roh** gelesen (`dm_gpio_get_value(...) == 0` heißt gedrückt), nicht über `GPIOD_ACTIVE_LOW`. Grund: die eine
Invertierung steht damit als Kommentar an genau der Stelle, an der sie passiert, und der Code hängt nicht daran, ob
`dm_gpio_set_dir_flags()` das `ACTIVE_LOW`-Bit mitnimmt (es maskiert mit `GPIOD_MASK_DIR`).

### Register und Konstanten

| Name | Wert | Bedeutung |
|---|---|---|
| `H713_RTC_GP5_REG` | `0x07090114` | RTC-GP5, frei |
| `H713_GATE_RUN1` | `0x52554e31` | „RUN1", System läuft |
| `H713_GATE_REQUESTED` | `0x47415445` | „GATE", von TF-A bei `poweroff` (Paket G2) |
| `H713_GATE_POLL_MS` | 10 | Abtastung |
| `H713_GATE_DEBOUNCE_MS` | 50 | Entprellung wie Stock |
| `H713_GATE_BYPASS_MS` | 3000 | Service-Hintertür |
| `H713_GATE_NOTE_MS` | 60000 | Punkt auf der Konsole |

## 2. Auftragspunkt 3 - schreibt sonst jemand GP5?

Durchsucht wurde der ganze U-Boot-Baum nach `0x07090`, dazu `mainline/patches/`:

- **PREBOOT** (alle sechs Defconfigs) fasst nur `0x0709011c` = **GP7** an: liest die Fastboot-/Bootloader-Magic, schreibt bei
  Treffer 0 zurück, sonst nichts. Genauso `board/sunxi/board.c:59` (`fastboot_set_reboot_flag_board`) und
  `board/sunxi/h713_vendor_chain.c:39`, und `include/configs/sunxi-common.h:351` (`boot_vendor` = `mw.l 0x0709011c 0x001db007`).
- **SPL**: `arch/arm/mach-sunxi/dram_sun50iw12.c` fasst in dieser Region nur `0x07090160` und `0x070901f4` an (ZQ-/Analog-Vorgaben
  aus BT0). Der GP-Block `0x07090100…0x0709011c` wird nicht berührt.
- **Kernel**: Patch `0029` legt eine nvmem-Zelle **nur** auf Byte-Offset `0x1c` (= GP7) und hängt `nvmem-reboot-mode` daran.
  Das Löschmuster liegt nicht im Kernel, sondern im PREBOOT: *schreiben beim Anfordern, löschen beim Verbrauchen*
  (`mw.l 0x0709011c 0` im `if`-Zweig). Ein einfaches `reboot` schreibt gar nichts (der reboot-mode-Kern überspringt Magic 0).
  Der `sun6i-rtc`-Treiber legt die acht GP-Wörter als nvmem-Gerät offen, löscht sie aber nicht.

**Ergebnis: GP5 wird zwischen SPL und Kernelstart von nichts überschrieben.** Wenn das Muster von GP7 einmal auf GP5 übertragen
werden sollte (etwa ein zweiter reboot-mode), gilt: **GP5 darf nicht gelöscht werden** - es ist kein Ereignis-, sondern ein
Zustandswort, und ein gelöschtes GP5 sieht für den nächsten Start wie ein Kaltstart aus (= Gate).

## 3. Defconfigs, auch die fünfte und sechste

Der Auftrag nennt vier; im Baum tragen **sechs** Defconfigs `CONFIG_H713_POWERON_LIGHT_FAN=y`:

| Defconfig | Gate | Warum |
|---|---|---|
| `hy310_qz713_v3_1_defconfig` | **an** | der auslieferbare Stand, um den es geht |
| `hy310_netboot_defconfig` | aus | Entwicklungsbild, NFS-Root; muss am Netz allein hochkommen |
| `hy310_host_defconfig` | aus | Entwicklungsbild |
| `hy310_felmmc_defconfig` | aus | Restore-SPL für FEL. Die vierte Defconfig, ausdrücklich begründet: das ist der Rettungsweg für ein Board, dessen Zustand man gerade **nicht** kennt. Ein Rettungsbild, das auf einen Tastendruck wartet, ist kein Rettungsbild. |
| `hy200_qz713df_a1_defconfig`, `hy200_h713_felmmc_defconfig` | aus | Bench-Board HY200, nicht Marcos HY310; bleibt durch die Kconfig-Vorgabe `n` ohne jede Änderung |

Für die drei „aus"-Fälle steht `# CONFIG_H713_POWER_GATE is not set` ausdrücklich in der Datei, obwohl die Kconfig-Vorgabe
ohnehin `n` ist - wer die Defconfig liest, soll die Entscheidung sehen. **Nebenwirkung:** ein späteres `make savedefconfig`
wirft diese drei Zeilen wieder heraus (Kconfig schreibt nur Abweichungen von der Vorgabe). Das ist kein Fehler, nur Rauschen
im nächsten Diff.

**Ort des Kconfig-Symbols:** neben `H713_SPL_FORCE_MMC` (Zeile 63 ff.) und **nicht** neben `H713_POWERON_LIGHT_FAN`.
Grund: `H713_POWERON_LIGHT_FAN` und `H713_MIPS_BOOT` stehen heute *innerhalb* der `choice "Sunxi SoC Variant"`
(Zeilen 454-699). Das funktioniert offenbar (beide sind in den Defconfigs gleichzeitig `=y`, die Bilder laufen), ist aber
nicht das, was `choice` bedeutet. Ein drittes Symbol dort hineinzulegen wäre eine Wette; `H713_SPL_FORCE_MMC` zeigt, dass
H713-Optionen außerhalb der `choice` genauso gut aufgehoben sind. Die Abhängigkeit `depends on H713_POWERON_LIGHT_FAN`
funktioniert unabhängig von der Reihenfolge im File. (Beobachtung nebenbei, nicht in diesem Patch zu reparieren.)

## 4. Testrezept für die Hauptsitzung

### Vorbedingung: der Patch bringt **nur U-Boot proper** durcheinander

SPL (LBA 0x10) und die Bau-Kette darunter sind unverändert. Der geflashte Teil ist ausschließlich das Abbild ab
LBA `0x49ac00` (`doku/20`). Rückweg deshalb billig.

### Stufe 0 - Trockenlauf am **heutigen** Prompt, ohne Neubau (empfohlen, Risiko null)

Beweist die Physik und das Flag, bevor irgendetwas gebaut wird:

```
gpio input PL4        # Ruhe -> 1 ; mit gedrückter Taste -> 0 (mehrfach)
gpio clear PL3
gpio clear PB5        # Lüfter aus, Licht aus, LED rot == das, was das Gate erzeugt
md.l 0x07090114 1     # GP5 lesen
mw.l 0x07090114 0x52554e31 ; reset ; md.l 0x07090114 1   # RUN1 überlebt Reset
gpio set PB5          # blau + Lüfter == das, was h713_poweron_lines() macht
```

### Stufe 1 - bauen, mit **abgeschaltetem** Gate flashen

Bauen nach `doku/50` im Container. Vor dem Flashen am laufenden Prompt:

```
setenv h713_gate 0
saveenv
```

Dann U-Boot proper flashen (`doku/20` Weg 1, USB-Stick: `fatload usb 0:1 0x50000000 uboot-proper.bin` →
`mmc write 0x50000000 0x49ac00 <Sektoren>`; Sektorzahl neu ausrechnen). **SPL nicht anfassen.**
Erwartung: das Gerät bootet wie heute, auf der Konsole steht `gate: off (h713_gate=0)`. Damit ist bewiesen, dass das neue
U-Boot läuft, **ohne** dass das Gate je scharf war.

### Stufe 2 - Gate scharf schalten, jederzeit umkehrbar

```
setenv h713_gate 1 ; saveenv ; reset
```

Erwartung der Reihe nach:

1. Nach `reset` steht RUN1 in GP5 → `gate: warm start, booting`, direkt hoch. (Der erste Beweis für den RUN1-Pfad.)
2. Steckdose aus, 10 s warten, an → dunkel, leise, LED rot, Konsole `gate: cold start (GP5 00000000)` und
   `gate: waiting for power key`; nach 60 s ein Punkt. Tastendruck (kurz) → `gate: power key, booting`, Lüfter/Licht/blau,
   normaler Boot.
3. Taste beim Einschalten festhalten (≥ 3 s) → `gate: key held at power-on, bypass`, direkt hoch.
4. Aus Linux `reboot` → kommt ohne Taste wieder. Absturz (`echo c > /proc/sysrq-trigger`) → kommt ohne Taste wieder.
5. `poweroff` tut **noch nichts** - das ist Paket G2 (TF-A schreibt „GATE"). Ersatzprüfung des GATE-Zweigs von Hand:
   am Prompt `mw.l 0x07090114 0x47415445 ; reset` → erwartet `gate: power-off requested` und Gate.

**Rückweg, wenn das Gate klemmt** (in dieser Reihenfolge probieren): Taste beim Einschalten halten (Hintertür) →
am Prompt `setenv h713_gate 0 ; saveenv` → altes `uboot-proper.bin` vom USB-Stick zurückschreiben →
FEL-Restore-SPL nach `doku/20`. Das alte `uboot-proper.bin` **vor** Stufe 1 auf den Stick legen.

## 5. Risiken

- **Ein hängendes Gate ist ein unbedienbares Gerät.** Deshalb die drei Ausstiege (Env, gehaltene Taste, GPIO-Fehler ⇒ kein
  Gate) und deshalb der Weg über `h713_gate=0` beim ersten Flashen. Ein UART-Ausstieg (`tstc()`/beliebige Taste bricht das
  Gate ab) ist bewusst **nicht** eingebaut, weil der Auftrag ihn nicht vorsieht - er wäre drei Zeilen und wäre die naheliegende
  vierte Sicherung, falls Marco sie will.
- **`schedule()` in der Schleife**: in den Defconfigs steht `# CONFIG_WATCHDOG is not set` bei `CONFIG_WDT=y`, es gibt also
  keinen U-Boot-Watchdog-Cycle, der gefüttert werden müsste. `schedule()` ist trotzdem drin, weil es das ist, was U-Boot in
  Warteschleifen erwartet, und weil es ohne CYCLIC auf `uthread_schedule()` zusammenfällt.
- **Verbrauch im Gate ist ungemessen** (M5 aus Plan 103 offen). Der SoC läuft im Gate voll getaktet. Wenn das zu viel ist,
  bleibt nur Takt senken oder Stufe 2.
- **Reihenfolge PREBOOT/Gate**: `board_late_init` läuft in `board_r` (INITCALL Zeile 758) vor der `main_loop`, PREBOOT läuft
  in der `main_loop`. Das Gate liegt also **vor** `usb start` - richtig so, denn PL3 (USB-VBUS) ist im Gate noch aus.
- **Ein Gerät mit RUN1 in GP5 und leerer Batterie** gibt es nicht: die RTC-Domäne hat keine Batterie, GP5 ist nach Netz-aus 0.
  Umgekehrt gilt: wer GP5 von Hand auf RUN1 setzt und die Steckdose *nicht* trennt, sieht das Gate nie wieder.

## 6. Offene Annahmen (nicht gemessen, nicht gebaut)

1. **Nicht gebaut.** Der Patch ist syntaktisch geprüft, aber nicht durch einen Compiler mit U-Boot-Headern gelaufen.
   Erwartete Stolpersteine, falls es klemmt: `<time.h>` für `get_timer()` (neu hinzugefügt - falls `board.c` es schon
   indirekt hatte, ist der Include nur redundant), `<watchdog.h>` für `schedule()`, und `bool` aus `<linux/types.h>`
   (`get_unique_sid()` in derselben Datei benutzt `bool` bereits, also vorhanden).
2. **Entprellung über Zählschritte statt Uhr.** Die Schleife zählt `H713_GATE_POLL_MS` pro Durchlauf; `mdelay(10)` plus
   GPIO-Lesen und `schedule()` dauern real etwas länger als 10 ms, die effektive Entprellzeit ist also ≥ 50 ms. Für eine
   Taste ist das die richtige Richtung. Wenn es exakt sein muss: `get_timer()` statt Zählern.
3. **`dm_gpio_request(…, "power-key")` kollidiert mit nichts.** Im DT unseres Boards gibt es keinen `gpio-keys`-Knoten
   (Plan 103 §1) und keinen Hog auf PL4, `-EBUSY` wird trotzdem toleriert. Ungeprüft am Gerät.
4. **PL4 ist nach dem Kaltstart „func" (unkonfiguriert)** - so steht es in M1. `dm_gpio_set_dir_flags(GPIOD_IS_IN)` muss den
   Pin also erst auf Eingang schalten; dass der sunxi-Pinctrl das über die Uclass tut, ist Standardverhalten, aber hier
   nicht gemessen. Die Probelesung in `h713_gate_key_get()` würde einen harten Fehler fangen, einen falschen Pegel nicht.
5. **`gate: cold start (GP5 …)`** unterstellt, dass GP5 beim Kaltstart 0 liest (M3). Ein anderer Wert landet im selben Zweig
   (Gate) - das ist die sichere Richtung.
6. **Der GATE-Zweig ist tot, bis G2 steht.** Bis TF-A `0x47415445` schreibt, kommt man in diesen Zweig nur von Hand.
7. **Patchnummer 0013 kollidiert.** In `uboot-h713/` ist `0013-sunxi-h713-add-the-HY310-QZ713-V3.1-panel.patch` vergeben,
   der Baum steht bei `0017`. Der Auftrag nennt den Dateinamen ausdrücklich, deshalb liegt er so in
   `analyse/boot/arbeit/g1-uboot/patches/`; beim Einspielen gehört er nach `uboot-h713/0018-…`.
8. **Kein `git format-patch`-Kopf mit `From <sha1>`** - der Patch hat einen Mail-Kopf (From/Date/Subject) und reine
   `diff -u`-Rümpfe ohne `index`-Zeilen. `patch -p1` und `git apply -p1` gehen, `git am` sollte gehen, ist aber nicht geprüft.

## 7. Restliste

- Bauen und Stufe 0-2 des Testrezepts am Gerät (Hauptsitzung, Marco am UART).
- Paket G2 (TF-A `sunxi_power_down()` → GP5 := „GATE" + Reset) und G3 (Kernel-DTS `gpio-keys` auf PL4, `HandlePowerKey`).
- M5 (Verbrauch im Gate) nachholen.
- Entscheiden, ob der UART-Ausstieg aus der Gate-Schleife dazukommt.
- `doku/30-uboot-aenderungen.md` um einen Abschnitt „18 - Einschalt-Gate" ergänzen (Paket G6).
