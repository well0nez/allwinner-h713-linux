# Befund: Endschalter und Fokusmotor

Bearbeitet 07.09.2026. Reines Reverse Engineering und Code — das Board wurde nicht angefasst.

Quellen, die hier zitiert werden:

* `re/ida/HY310/extracted/vmlinux.elf.i64` — Stock-Kernel, ARM32. Adressen sind Adressen darin.
* `re/vendor/HY310/extracted/dtb_extracted/hy310-board.dts` — der DTB, mit dem Stock bootet.
* `re/captures/HY310-DEV/boot.log`, `stock_gpio_debug.txt`, `stock_pinconf_pio.txt`,
  `stock_pinmux_pio.txt` — Mitschnitte vom laufenden Stock-System.
* `re/notes/WORKLOG.md`, Session 2026-03-21 — der einzige Motorlauf, den unser Port je hatte.

Alle Rohausgaben meiner idalib-Läufe liegen in `agenten/motor-fokus/out/`.

---

## 0. Der Fehler in einem Satz

Unser Treiber liest den Endschalter mit umgekehrter Bedeutung: Stock fährt zurück, **wenn der
Schalter inaktiv wird**, unser Treiber fährt zurück, **wenn er aktiv wird** — und weil er auf
diesem Gerät nie aktiv liest, fährt er überhaupt nie zurück, sondern läuft in den Anschlag.

Dazu kommen zwei Fehler im Lesepfad selbst, die erklären, warum PH14 bei uns nie aktiv liest:
die Leitung wird beim Anfordern als **Ausgang auf LOW** getrieben (`devm_gpio_request_one(dev,
gpio, 0, …)` ist `GPIOF_OUT_INIT_LOW`), und der **Pad-Bias** wird gar nicht gesetzt, während Stock
den Pin mit Pull-down betreibt. Der Rückgabewert von `gpiod_direction_input()` wurde außerdem
verworfen.

---

## 1. Aufgabe A — der Endschalter

### 1.1 Was Stock tut

**`motor_limiter_status` @ `0xc05d6930`** — die eigentliche Leseroutine:

```c
int motor_limiter_status(u32 *value, int dir)
{
  result = limiter_num;
  if (limiter_num == 1) { if (!MOTOR_LIMITER_PIN) return result; v4 = MOTOR_LIMITER_PIN; }
  else if (dir == 2)   { v4 = limter_up_pin; if (!limter_up_pin) return 1; }
  else if (dir == 1)   { v4 = limter_dn_pin; if (!limter_dn_pin) return 1; }
  else                 goto LABEL_5;                 /* *value = 1 */
  v5 = gpio_to_desc(v4);
  if (active_level == gpiod_get_raw_value(v5)) { LABEL_5: *value = 1; return 0; }
  *value = 0; return 0;
}
```

Der Lesevorgang selbst — `gpio_to_desc()` + `gpiod_get_raw_value()`, Vergleich gegen
`active_level` — ist bei uns identisch. Der Unterschied liegt nicht hier.

**`motor_control_fdt_parse` @ `0xc05d62c8`**, Aufrufstellen `0xc05d65b4`–`0xc05d6620`:

```c
named_gpio_flags = of_get_named_gpio_flags(np, "limiter-up-gpio", 0, 0);
limter_up_pin = named_gpio_flags;
if (named_gpio_flags < 0 || gpio_request(named_gpio_flags, "limiter-up-gpio") < 0)
        dev_err(motor->dev, "failed to get property limiter-gpio\n");
else {
        v15 = gpio_to_desc(limter_up_pin);
        gpiod_direction_input(v15);
        MOTOR_LIMITER_PIN = limter_up_pin;
        ++limiter_num;
}
```

`gpio_request()` — nicht `gpio_request_one()`. Stock gibt der Leitung **nie** eine
Ausgangsrichtung. Die Eigenschaftsnamen, die diese Funktion tatsächlich nachschlägt, stehen
in `agenten/motor-fokus/out/motor_globals.txt`; zwei davon sind mit Unterstrich geschrieben
(`active_level` @ `0xc11618ec`, `motor_type` @ `0xc1161a03`).

**Was der Wert bedeutet — `motor_run_up_control` @ `0xc05d6ea0`:**

```c
motor_run_up_mstep(longFlag);
motor_limiter_status(value, 2);
if (value[0]) { v4 = 0; }            /* aktiv: alles in Ordnung, weiterfahren */
else {                               /* INAKTIV: wir sind aus dem Bereich gelaufen */
    while (1) { motor_run_dn_mstep(longFlag); motor_limiter_status(value, 2);
                if (value[0] == 1) break;
                if (++v4 == 40) goto LABEL_23; }
    for (i = 0; i < back_step; ++i) { motor_run_dn_mstep(longFlag); … }
LABEL_23:
    g_motor_edge_Up = 1;
}
```

Das ist der Kern. **Der Endschalter ist ein Bereichsschalter, kein Anschlagkontakt.** Er liest
über den ganzen erlaubten Fahrweg *aktiv*; ihn zu verlieren ist das Signal zum sofortigen
Zurückfahren (höchstens 40 msteps, dann `back_step` weitere). `motor_run_dn_control`
@ `0xc05d70d4` ist dazu spiegelbildlich.

### 1.2 Beleg, dass Stock den Schalter am selben Gerät findet

Zwei unabhängige Messungen aus unseren eigenen Mitschnitten:

**(a) Der Stock-Bootlog.** `re/captures/HY310-DEV/boot.log:284`:

```
[    0.475418] motor-control motor_ctr: failed to get property limiter-gpio
[    0.483916] Failed to read array length
```

`motor_control_probe` @ `0xc05d753c` führt das Homing **synchron** aus:

```c
if (limiter_num == 1) {
    motor_limiter_status(value, 0);
    if (value[0] == 1) printk("limited normal\n");
    else { for (i = 0; i != 100; ++i) { …; motor_run_up_mstep(1); … }
           while (!value[0]) { ++i; motor_run_dn_mstep(1); …; if (i == 250) break; } }
}
```

Ein einziger mstep dauert `motor_cycle` × `step_num` × `motor-phase-udelay` = 2 × 8 × 1 ms
= 16 ms. 100 msteps wären ≥ 1,6 s. Zwischen der Motorzeile und der nächsten Kernelzeile liegen
**8,5 ms**. Die Schleife ist also nachweislich nicht gelaufen — der erste Lesevorgang lieferte
bereits `value[0] == 1`. **PH14 las unter Stock bei 0,475 s aktiv (HIGH).**

Dass `limiter_num` dabei 1 war und nicht 0, zeigt `re/captures/HY310-DEV/stock_gpio_debug.txt`:

```
 gpio-238 (                    |limiter-up-gpio     ) in  lo
```

Die Leitung wurde erfolgreich angefordert; die eine `failed to get property limiter-gpio`-Zeile
im Log ist die für das im DTB nicht vorhandene `limiter-dn-gpio` (dieselbe Fehlermeldung wird
für beide benutzt, `0xc05d65d0` und `0xc05d6650`).

**(b) Die Pad-Konfiguration.** `re/captures/HY310-DEV/stock_pinconf_pio.txt`:

```
pin 228 (PH4):  input bias disabled,  output drive strength (20 mA)
…
pin 238 (PH14): input bias pull down, output drive strength (20 mA)
```

und `stock_pinmux_pio.txt`: `pin 238 (PH14): GPIO 2000000.pinctrl:238`.

Also: GPIO-Eingang mit **Pull-down**, bei `active_level = 1`. Der Ruhepegel ist definiert LOW,
der Schalter zieht aktiv nach HIGH. Der Pin und der Schalter funktionieren unter Stock.

Damit ist die Aussage in `re/notes/motor.md` („Hardwaredefekt am Endschalter") und in
`re/notes/known-issues.md:134` ff. **durch unsere eigenen Mitschnitte widerlegt**.

### 1.3 Was unser Treiber stattdessen tut

Gegenüberstellung an genau der Stelle, an der der Schalter gelesen und ausgewertet wird
(`drivers/misc/hy310-keystone-motor.c` vor diesen Patches):

| | Stock | unser Treiber |
|---|---|---|
| Leitung anfordern | `gpio_request(pin, name)` — keine Richtung | `devm_gpio_request_one(dev, gpio, **0**, name)` |
| `flags == 0` heißt | — | `GPIOF_OUT_INIT_LOW` → `gpiod_direction_output_raw(desc, 0)` |
| danach | `gpiod_direction_input(desc)` | `gpiod_direction_input(desc)`, **Rückgabewert verworfen** |
| Pad-Bias | Pull-down (gemessen) | nicht gesetzt |
| Rückfahrt bei | Schalter **inaktiv** | Schalter **aktiv** |
| Verzögerung | `usleep_range(800·n, 1000·n)` bzw. Busy-Wait nur bei Autofokus | immer `mdelay(n)` |
| Arbeitsschleife | pollt nach Leerlauf noch 120 × 5 ms | leert die Queue einmal und endet |

Belege für die Zeilen mit Kernel-Bezug, alle aus dem Baum, gegen den wir bauen
(`linux-6.18.38`, `drivers/gpio/gpiolib-legacy.c`):

```c
int gpio_request_one(unsigned gpio, unsigned long flags, const char *label)
{
	…
	if (flags & GPIOF_IN)  err = gpiod_direction_input(desc);
	else                   err = gpiod_direction_output_raw(desc, !!(flags & GPIOF_OUT_INIT_HIGH));
```

mit `include/linux/gpio.h`: `#define GPIOF_IN ((1 << 0))`, `#define GPIOF_OUT_INIT_LOW ((0 << 0) | (0 << 1))`.
`flags = 0` ist also der Ausgangs-Zweig.

### 1.4 Warum das beide Beobachtungen erklärt

* **Warum Stock den Schalter findet.** Stock macht PH14 zu einem GPIO-Eingang mit Pull-down und
  liest ihn. Der Schalter zieht im erlaubten Bereich nach HIGH, `active_level = 1` trifft zu,
  `motor_limiter_status()` liefert 1 — im Bootlog nachweisbar innerhalb von 8,5 ms.
* **Warum wir ihn nie finden.** Unser Treiber treibt dieselbe Leitung beim Anfordern zuerst als
  Ausgang auf LOW, korrigiert die Richtung anschließend ungeprüft und überlässt den Bias dem
  Zufall dessen, was die Bootkette hinterlässt. Und selbst wenn der Pin dann korrekt liest,
  wertet die Bewegungslogik das Ergebnis genau falsch herum aus: der Rückzug wird an
  „Schalter aktiv" gehängt statt an „Schalter inaktiv". Ein Motor, dessen Schalter nie aktiv
  liest, fährt in unserem Treiber deshalb **ohne jede Rückfahrt** weiter — das ist der Weg in
  den mechanischen Anschlag, und er entsteht auch dann, wenn der Pin elektrisch völlig in
  Ordnung ist.

Die Erklärung ist damit für die Logik vollständig. Für den **elektrischen** Teil ist sie es
nicht — siehe 1.6.

### 1.5 Was der Fix macht

`0001-misc-hy310-motor-fix-the-limit-switch-read-path.patch`:

1. Endschalter-Leitung wird als `GPIOF_IN` angefordert, nie als Ausgang.
2. `gpiod_direction_input()` wird geprüft; scheitert es, schlägt das Probe fehl, statt ein
   Homing zu starten, dessen Messinstrument nachweislich kaputt ist.
3. Der Pad-Bias wird explizit gesetzt, als Komplement von `active_level` — für dieses Board
   also Pull-down, genau das, was der Stock-Mitschnitt zeigt. Kein geerbter Zufallszustand mehr.
4. `motor_run_up_control`/`motor_run_dn_control` bekommen Stocks Bedingung: Rückzug, wenn der
   Schalter **inaktiv** wird, bis zu 40 msteps zurück, danach `back_step`, dann Edge setzen.
5. `motor_limiter_status()` wird auf Stocks Verhalten gezogen, einschließlich der
   „kein Pin"-Zweige, die 1 liefern (ohne brauchbaren Schalter darf nichts einen Rückzug auslösen).
6. Verzögerung wie Stock: schlafend (`usleep_range(800·n, 1000·n)`), Busy-Wait nur im
   Autofokus-Pfad.
7. Arbeitsschleife wie Stock, mit Nachlauf (120 × 5 ms) — sonst gehen Kommandos verloren, die
   zwischen dem letzten Dequeue und dem Löschen von `work_running` eintreffen. **Über Stock
   hinaus** prüft der Handler die Queue nach dem Löschen des Flags noch einmal und startet sich
   neu, wenn etwas wartet; das letzte schmale Fenster lässt Stock offen. `motor_remove()` leert
   die Queue jetzt vor dem Abbrechen, damit dieser Neustart dem Abbau nicht in die Quere kommt.
8. Findet das Homing den Bereich in keiner Richtung, werden die Phasen abgeschaltet, **beide**
   Edge-Flags bleiben leer und der Treiber sagt es per `dev_err`. Kein erfundener Edge.

**Zur Schrittzahl-Obergrenze:** Sie bleibt — aber nicht als Workaround. Die 100 UP-msteps und der
Weiterlauf bis `i == 250` sind **Stocks eigene Werte** (`motor_control_probe`,
`0xc05d7758`–`0xc05d77c8`). Die Behauptung in `re/notes/motor.md`, das sei ein bei uns
eingebauter Workaround, ist falsch. Sie ist eine Schranke, nicht der Mechanismus; der
Mechanismus ist ab jetzt wieder der Schalter.

### 1.6 Was ich elektrisch **nicht** verifizieren konnte

Der Logikfehler (1.4, zweiter Punkt) ist bewiesen. Ob nach dessen Behebung PH14 auch wirklich
HIGH liest, ist es **nicht**. Ich kann nur benennen, was zwischen Stock und unserem Port an der
Pin-Grenze nachweislich verschieden war:

* **PB5 war zum Zeitpunkt der Messung aus.** Der einzige Motorlauf unseres Ports ist
  `re/notes/WORKLOG.md`, Session **2026-03-21**. `mainline/patches/kernel/0030-…-fan-power-gpio-hog.patch`
  beschreibt, dass der `fan_power_hog` bis dahin fehlerhaft war (`gpios = <37 …>` — zwei Zellen
  an einem `#gpio-cells = <3>`-Controller), gpiolib den Hog stillschweigend übersprang und **PB5
  nie getrieben wurde**; `doku/30-uboot-aenderungen.md` beschreibt für dieselbe Zeit, dass auch
  U-Boot PB5 nicht setzte („Der Lüfter lief nie an"). Stock hält PB5 dagegen high
  (`stock_gpio_debug.txt`: `gpio-37 (fan-power-gpio0) out hi`), und `doku/10-hardware.md:158`
  nennt PB5 die gemeinsame Freigabe für Lüfter **und** Panel-Backlight.
  **Ob der Endschalter an derselben Schiene hängt, weiß ich nicht.** Es ist die einzige
  dokumentierte elektrische Differenz an dieser Stelle, und sie ist billig zu prüfen —
  deshalb steht sie in `TESTPLAN.md` an erster Stelle, vor jeder Bewegung.

  **Nachtrag, im aktuellen Baum nachgeprüft:** Der Hog ist inzwischen in Ordnung.
  `sun50i-h713.dtsi:515` trägt `gpios = <1 5 GPIO_ACTIVE_HIGH>` (drei Zellen) als Kindknoten
  von `pio: pinctrl@2000000` (`gpio-controller`, `#gpio-cells = <3>`, Zeile 438/447/448); im
  gebauten DTB steht `gpios = <0x01 0x05 0x00>` mit `output-high`. Das ist genau die Form, die
  `of_parse_own_gpio()` erwartet — die alte Zweizellenform ließ
  `of_property_read_u32_index(np, "gpios", 2)` scheitern, `of_gpiochip_add_hog()` brach die
  Schleife ab und gab **0** zurück, also stilles Überspringen. Genau das beschreibt Patch 0030.
  Kein zweiter Hog und kein konkurrierender PB5-Verbraucher im Baum: die Backlight-Node
  verzichtet ausdrücklich auf `enable-gpios` (`sun50i-h713.dtsi:1746`), `panel_bl_en` und
  `dc_in` sind U-Boot-Properties, die Linux nicht anfordert, und `HY310_BOARD_MGR` ist im
  Defconfig aus.
  Zusätzlich fährt **U-Boot** PB5 selbst hoch: `h713_poweron_lines()` in
  `mainline/external/u-boot/board/sunxi/board.c:994` per `dm_gpio_lookup_name("PB5")`, aktiv in
  allen vier `hy310_*_defconfig` (`CONFIG_H713_POWERON_LIGHT_FAN=y`). Die Schiene liegt damit
  auf zwei unabhängigen Wegen an, lange bevor der Motortreiber probt.
  **Weiterhin nicht verifiziert:** ein Laufzeitbeleg von unserem Kernel (kein `gpio`- oder
  `pinconf`-Mitschnitt nach Patch 0030). Das ist eine statische Prüfung, keine Messung.
  Für den Test heißt das: Schritt 1 sollte jetzt bestehen — und wenn PH14 danach *trotzdem*
  LOW bleibt, ist die PB5-Hypothese erledigt und der nächste Schritt ist das Multimeter.
* **Pad-Schaden ist nicht ausgeschlossen.** Wenn der Schalter beim Probe geschlossen ist (Stock
  belegt genau das für 0,475 s), dann hat unser Treiber bei jedem Bootversuch die vom Schalter
  getriebenen 3,3 V für die Dauer eines `gpio_request_one()` gegen den Ausgangstreiber des Pads
  kurzgeschlossen. Ob das dem Pad oder dem Sensor geschadet hat, kann ich ohne Messung nicht
  sagen. Der Fix beseitigt die Ursache dieses Konflikts; ob er zu spät kommt, entscheidet der
  Test.
* **Keine Messung von unserer Seite.** Es existiert kein `/sys/kernel/debug/gpio`- oder
  `pinconf-pins`-Mitschnitt aus unserem Kernel. Der ganze „unsere Seite"-Teil dieses Befunds
  ist Codeanalyse, keine Messung.

---

## 2. Aufgabe B — der Fokusmotor

### 2.1 Der Befund ist ein negativer, und er ist belegt

**Es gibt auf der HY310 keinen zweiten Motor.** Der Auftrag (und `doku/60-offen.md:593`) geht
von „gleiche Treiberfamilie wie der Keystone-Motor" aus, also von zwei Motoren. Das trifft nicht
zu:

* **DTB:** genau ein Motorknoten. `hy310-board.dts:2635` — `motor_ctr`, PH4–PH7 + PH14. Ich habe
  den kompletten Kernel-DTB, den U-Boot-DTB (`bootpkg-full.dts:2909`) und die drei Overlays
  (`hy310-overlay-{0,1,2}.dts`, allesamt leere Teststummel) durchgesehen. Kein weiterer.
* **Stock-Kernel:** genau ein Motortreiber. `kallsyms` `0xc05d5c1c`–`0xc05d7d14`, mit genau
  **einem** Satz Globals (`motor_ctl`, `pMotordev`, `MOTOR_LIMITER_PIN`, `MOTOR_IN1_PIN`,
  `MOTOR_IN2_PIN`, `limiter_num`). Der Treiber ist ein Singleton; eine zweite Instanz ist
  strukturell nicht vorgesehen. Ein Namensscan über die gesamte Datenbank nach
  `motor|focus|lens|limiter|keystone` (`agenten/motor-fokus/out/name_scan.txt`) findet nichts
  weiter.
* **Laufendes Stock-System:** `stock_gpio_debug.txt` listet **alle** angeforderten GPIOs. Für den
  Motor sind es 228–231 (Phasen) und 238 (Limiter). Keine weiteren.
* **Stock-Module:** `init.input.rc` versucht `motor-control.ko` und `motor-limiter.ko` zu laden,
  beide existieren nicht (`stock_dmesg.txt:740`); die Treiber sind eingebaut. In
  `stock_vendor_modules.txt` gibt es kein Motormodul.
* **Und unser eigenes Projekt weiß es schon:** `legacy/tools/focus` fährt seit jeher
  `/sys/devices/platform/motor_ctr/motor_ctrl` — den Knoten, den wir „Keystone-Motor" nennen.

Der einzige Schrittmotor des Geräts ist der **Fokusantrieb**. Der Name „keystone" in unserem
Port stammt aus dem HY300-Baum und ist durch nichts in dieser Firmware gedeckt. Keystone macht
dieses Gerät nicht mechanisch.

### 2.2 Was zum Fokusfahren fehlte, und was jetzt da ist

Nicht ein zweiter Treiber, sondern die zweite Hälfte des sysfs-Protokolls.
`motor_ctrl_store` @ `0xc05d7d14` dekodiert `(cmd << 8) | (steps & 0x7f) | (full_limit ? 0x80 : 0)`
und hat **zwei** Fahrpfade:

| cmd | Stock | bei uns vorher |
|---|---|---|
| 1 / 2 | `autofocus = 1;` dann `motor_run_up_dn(cmd-1, …)` | vorhanden |
| 3 | `CleanQueue()` | vorhanden |
| 4 | `g_motor_step_cur = (v & 0xff) \| ((v & 0xff0000) >> 8)` | vorhanden |
| 6 | `g_motor_step_low = max(steps, 10)` | fehlte |
| 7 | `motor_goto_step(steps & 0x7f)` | `/* TODO */` |
| 8 / 9 | `autofocus = 0;` dann `motor_run_up_dn(cmd-8, …)` | **fehlte** |

Das `autofocus`-Flag ist nicht kosmetisch: `delay_ms_func` @ `0xc05d6b00` ist

```c
void delay_ms_func(int ms_time)
{
  if (autofocus) { for (i = ms_time; i; --i) const_udelay(0x1FFFFC70); }
  else             usleep_range(800 * ms_time, 1000 * ms_time);
}
```

Nur der Autofokus-Pfad blockiert die CPU; manuelles Fahren schläft. Weil bei uns nur cmd 1/2
portiert war, lief **jede** Bewegung mit der Autofokus-Zeitgebung — und mit `mdelay()` statt
`usleep_range()` blockierte sie die CPU auch dort, wo Stock schläft.

`0002-misc-hy310-motor-add-the-stock-manual-move-commands.patch` ergänzt cmd 6 und cmd 8/9.
Manuelles Fokusfahren, ohne Kamera, ohne Autofokus:

```sh
echo $(( (8 << 8) | 5 )) > /sys/devices/platform/motor_ctr/motor_ctrl   # 5 msteps hoch
echo $(( (9 << 8) | 5 )) > /sys/devices/platform/motor_ctr/motor_ctrl   # 5 msteps runter
cat /sys/devices/platform/motor_ctr/motor_ctrl                          # pos inc in_range
```

`legacy/tools/focus` benutzt noch cmd 1/2; das funktioniert weiter, setzt aber das
Autofokus-Flag. Das Skript gehört bei Gelegenheit auf 8/9 umgestellt — nicht Teil dieser Patches.

### 2.3 cmd 7 („goto step") — bewusst nicht implementiert

`motor_goto_step` @ `0xc05d7cbc` setzt nur `g_goto_step` und startet die Arbeit.
`g_goto_step` (@ `0xc146b0e4`) wird an genau **einer** Stelle gelesen, `func_motor_run`
@ `0xc05d7a88` und `0xc05d7ab4`, und dort ausschließlich als Schleifen-Fortsetzungsbedingung.
Nichts wertet den Wert aus, nichts dekrementiert ihn, nichts löscht ihn. In Stock würde ein
`goto step` die Arbeitsschleife also dauerhaft laufen lassen und den Motor nirgendwohin fahren.

Das Feature existiert in Stock nicht vollständig und ist aus Stock nicht rekonstruierbar. Ich
erfinde es nicht. Der Patch ersetzt den stillen `/* TODO */`-Stub durch ein ehrliches
`-EOPNOTSUPP`, damit ein Schreibvorgang nicht mehr scheinbar gelingt.

### 2.4 Notiz zur Autofokus-Schnittstelle (nur für später)

Nicht bearbeitet, aber beim Reversen aufgefallen und für die spätere Autofokus-Arbeit relevant:

* Der Autofokus erreicht den Motor **über genau dieselbe sysfs-Datei**,
  `/sys/devices/platform/motor_ctr/motor_ctrl`, mit **cmd 1 und cmd 2**. Das ist die einzige
  Unterscheidung, die Stock kennt: cmd 1/2 setzen `autofocus = 1`, cmd 8/9 setzen es auf 0.
* Es gibt **keinen kernelinternen Weg** dorthin. `init_motor_step` (`0xc05d7310`) und
  `android_motor_step_init` (`0xc05d73a4`) sind global exportiert, haben aber im gesamten
  Stock-vmlinux **null Aufrufer** (`agenten/motor-fokus/out/motor_xrefs.txt`). Die einzigen
  Aufrufer von `motor_run_up_dn` und `motor_goto_step` sind `motor_ctrl_store`.
* `shake_for_vafocus` (`0xc06bea8c`) und `shake_kxt_for_vafocus` (`0xc06c169c`) gehören zum
  **Beschleunigungssensor** (`stk83xx` / `kxtj3`, Adressbereich `0xc06bc…`–`0xc06c2…`), nicht zum
  Motor. Sie fassen keine Motorfunktion an. Das ist die „Schütteln → neu fokussieren"-Erkennung,
  nicht der Regelkreis.
* Daraus folgt für später: der Autofokus setzt auf dem hier portierten sysfs-Interface auf. Der
  Motor ist ohne Kamera vollständig benutzbar, und die Kamera-Baustelle braucht am Motor nichts
  mehr zu ändern.

---

## 3. Weitere Behauptungen, die ich gegen das Disassemblat geprüft habe

| Behauptung (Patchkopf 0009 / `re/notes/motor.md`) | Ergebnis |
|---|---|
| „GPIO polling — no EINT, H713 PH11+ EINT is broken" | Polling **richtig**, Begründung **erfunden**. Der Stock-Treiber hat überhaupt keinen Interruptpfad für den Limiter; EINT war nie im Spiel. Korrigiert in 0001/0004. |
| „motor-phase-udelay ist in Wahrheit ms" | **Richtig.** `delay_ms_func` @ `0xc05d6b00`, Zweig ohne Autofokus: `usleep_range(800·n, 1000·n)`. |
| Pin PH14 | **Richtig**, aus dem Stock-DTB: `limiter-up-gpio = <0x2C 0x7 0xE 0x0>` (`hy310-board.dts:2642`), Bank 7 = PH, `#gpio-cells = <3>` am `pinctrl@2000000`. |
| „active HIGH" (`active_level = 1`) | **Richtig**, und passt zum gemessenen Pull-down. |
| Phasentabellen CW/CCW | **Richtig**, wortgleich aus dem Stock-DTB. `01 09 08 0A 02 06 04 05` ist die saubere Halbschrittfolge A, A+D, D, D+B, B, B+C, C, C+A (Wicklungsreihenfolge PH4, PH7, PH5, PH6); CCW ist exakt die Umkehrung. |
| Schrittzahl-Obergrenze sei „unser Workaround" | **Falsch.** 100/250 sind Stocks eigene Werte aus `motor_control_probe`. |
| „Hardwaredefekt am Endschalter" | **Widerlegt**, siehe 1.2. |
| „Physical movement inconsistent / Motor bewegt sich nach dem Boot nicht mehr per sysfs" | Wahrscheinlich der verlorene Weckruf in `motor_work_handler` (Queue einmal leeren, `work_running = 0`, während ein Schreiber gerade eingereiht hat und wegen `work_running == 1` nicht neu startet). Stock deckt genau dieses Fenster mit 120 × 5 ms Nachlauf ab (`func_motor_run` @ `0xc05d7a3c`). In 0001 behoben. **Nicht am Gerät verifiziert.** |
| Eigenschaftsnamen `active-level` / `motor-type` | **Erfunden.** Stock liest `active_level` und `motor_type`. Korrigiert in 0003; der Treiber akzeptiert beide Schreibweisen. |

Nebenbefund, nicht behoben und nicht unser Problem: Stock reiht seine Arbeit mit
`queue_work_on(4, system_wq, …)` ein — CPU 4 auf einem Vierkerner.

---

## 4. Zustand des Ports

`CONFIG_HY310_KEYSTONE_MOTOR` steht in `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig`
auf „not set". Der Treiber wird also derzeit **gar nicht gebaut**, und nichts von seinem
Verhalten ist auf dem aktuellen Baum je gelaufen. Patch 0005 baut ihn als **Modul** — das Probe
stößt ein Homing an, das die Mechanik bewegt, also soll er absichtlich geladen und wieder
entladen werden können.

---

## 5. Die Patches

Reihenfolge einhalten; 0002 setzt auf 0001 auf.

| Datei | Ziel | Inhalt |
|---|---|---|
| `0001-misc-hy310-motor-fix-the-limit-switch-read-path.patch` | Kernelbaum, `-p1` | Ursache A: Lesepfad, Polarität, Zeitgebung, Arbeits-Handshake, ehrliches Homing-Ergebnis |
| `0002-misc-hy310-motor-add-the-stock-manual-move-commands.patch` | Kernelbaum, `-p1` | Aufgabe B: cmd 6, cmd 8/9, cmd 7 → `-EOPNOTSUPP` |
| `0003-arm64-dts-h713-use-the-stock-property-names-on-the-motor-node.patch` | Kernelbaum, `-p1` | `active_level` / `motor_type`, Kommentar |
| `0004-misc-hy310-motor-say-what-the-driver-is-in-kconfig.patch` | Kernelbaum, `-p1` | Kconfig-Text |
| `0005-build-enable-the-focus-motor-in-the-board-defconfig.patch` | **Repo-Datei**, `-p1` aus `mainline/` | Treiber als Modul bauen |

### Bauprobe

Isoliert in `agenten/motor-fokus/`, der gemeinsame Bau wurde nicht benutzt und der Kernelbaum
nur gelesen:

* `agenten/motor-fokus/build/cc.sh` übersetzt eine einzelne Übersetzungseinheit mit exakt den
  Flags aus `drivers/misc/.sunxi-scanout-dmabuf.o.cmd` des konfigurierten 6.18.38-Baums
  (clang 18.1.3, `--target=aarch64-linux-gnu`), ohne `-MMD`, Objekt in unseren Ordner.
* 0001–0004 angewandt auf frische Kopien von `drivers/misc/hy310-keystone-motor.c`,
  `drivers/misc/Kconfig` und `arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi`: alle vier
  greifen sauber mit `-p1`. Die gepatchte Quelle übersetzt **warnungsfrei**
  (`agenten/motor-fokus/build/verify.o`).
* Der DTB wurde mit `scripts/dtc/dtc` aus demselben Baum in
  `agenten/motor-fokus/dtswork/build/v2.dtb` gebaut. Einzige Warnung
  (`/soc/dec@5600000: duplicate unit-address`) besteht schon vorher, gegengeprüft mit der
  ungepatchten `.dtsi`. Der erzeugte Knoten trägt jetzt dieselben Eigenschaftsnamen wie der
  Stock-DTB.
* 0005 als Trockenlauf gegen `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig` geprüft.

**Nicht gebaut:** ein vollständiger Kernel und ein vollständiges Image. Übersetzt ist die
Übersetzungseinheit, nicht die Verlinkung ins Modul.

---

## 6. Ehrliche Liste dessen, was ich nicht verifizieren konnte

1. **Ob PH14 nach dem Fix HIGH liest.** Ohne Board keine Messung. Der Logikfehler ist bewiesen,
   die elektrische Ursache für „liest immer LOW" ist es nicht.
2. **Ob der Endschalter an PB5 hängt.** Naheliegendste dokumentierte Differenz zwischen Stock
   und unserem Port zum Zeitpunkt der Messung, aber ein Schaltplan liegt nicht vor. Erste
   Prüfung im Testplan.
3. **Ob das Pad oder der Sensor beschädigt ist.** Unser Treiber hat die Leitung bei jedem Probe
   kurzzeitig gegen den Schalter getrieben. Folgen unbekannt.
4. **Der exakte Wert der Autofokus-Verzögerung.** `const_udelay(0x1FFFFC70)` hängt von
   `CONFIG_HZ` des Stock-Kernels ab, den ich nicht ermittelt habe. Größenordnung 1–2 ms pro
   Einheit. Der schlafende Zweig ist eindeutig 1 ms pro Einheit; nur daraus leite ich die
   Millisekunden-Aussage ab.
5. **`motor_mstep_work_handler` @ `0xc05d60a8`** ließ sich nicht sauber dekompilieren (die
   Struktur-Offsets sind im Hex-Rays-Ergebnis verschoben). Er gehört zu einem zweiten,
   listenbasierten Phasenpfad, den unser Treiber nicht hat und der von `motor_ctrl_store` nicht
   erreicht wird. Nicht weiter verfolgt.
6. **Ob der verlorene Weckruf wirklich die Ursache** für „bewegt sich nach dem Boot nicht per
   sysfs" ist. Die Codeanalyse passt, ein Gegentest am Gerät fehlt.
7. **Der `long_flag`-Parameter.** Stock berechnet ihn in `func_motor_run` (1 nach Leerlauf oder
   Richtungswechsel, sonst 0) und reicht ihn bis in `motor_run_up_mstep` durch, wo er
   **nicht benutzt** wird. Ich habe die Berechnung nachgebildet, um die ABI zu erhalten; wofür
   er gedacht war, weiß ich nicht.
8. **Die Umbenennung der Datei** `hy310-keystone-motor.c` → `hy310-focus-motor.c` habe ich
   bewusst **nicht** gemacht, um Konflikte mit der laufenden Serie zu vermeiden. Sachlich wäre
   sie richtig; Beschreibung, Kconfig-Text und Kommentare sind korrigiert, Dateiname und
   Config-Symbol nicht. Das ist eine Aufräumaufgabe für die Hauptsitzung.
