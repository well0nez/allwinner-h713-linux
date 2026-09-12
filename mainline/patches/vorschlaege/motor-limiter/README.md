# Fokusmotor: wie Stock den Anschlag erkennt — und warum wir nichts sehen

Stand 12.09.2026. Quelle für alles Folgende ist der **echte** Vendor-Stand:
`re/vendor/HY310/hy310_factory.dts`, `re/vendor/HY310/extracted/bootpkg-full.dts`
(beide vom Gerät dekompiliert) und `re/vendor/HY310/extracted/vmlinux.elf`
(ARM32, mit DWARF). Nicht benutzt: `extracted/sun50i-h713-hy310.dts`, das ist
unsere eigene Portierungsfassung.

Die DWARF-Angaben machen den Herstellercode ungewöhnlich gut lesbar:

```
$ addr2line -e vmlinux.elf -f -i 0xc05d7724
check_motor_position
drivers/misc/gpio-motor/motor-control.c:718
motor_control_probe
drivers/misc/gpio-motor/motor-control.c:1280
```

Alle Zeilennummern unten sind aus dieser Datei, alle Adressen aus diesem ELF.

---

## 1. Kurzfassung

**Es gibt keinen Endschalter im klassischen Sinn.** PH14 ist ein
**Bereichswächter**: er liest `active_level` (= 1 = HIGH), *solange die Mechanik
im erlaubten Fahrbereich steht*. Stock erkennt den Anschlag nicht daran, dass
etwas anspricht, sondern daran, dass dieser Pegel **wegfällt** — in beide
Richtungen, aus demselben einen Pin.

Wir sehen ihn nicht, weil unser Treiber den Pad-Bias auf **Pull-down** zwingt.
Das ist genau die Einstellung, unter der ein hochohmiger Geber an *jeder*
Position „außerhalb" meldet. Stock setzt **gar keinen Bias**.

Dazu kommen zwei Fehler in unserer eigenen Beweiskette, die beide in
`doku/94-fokusmotor-endschalter.md` stehen und beide korrigiert gehören.

---

## 2. Wie Stock den Anschlag erkennt — und womit das belegt ist

### 2.1 Ein Pin, beide Richtungen — also kein Anschlagkontakt

`motor_limiter_status(int *out, int dir)` @ `0xc05d6930`
(`motor-control.c:160`), vollständig:

```
c05d6944  ldr r0, [r3, #0x18]      ; limiter_num
c05d6948  cmp r0, #1
c05d694c  bne ...                  ; sonst: getrennte up/dn-Pins
c05d6950  ldr r3, [r3, #0x14]      ; MOTOR_LIMITER_PIN
c05d6960  bl  gpio_to_desc
c05d6964  bl  gpiod_get_raw_value
c05d696c  ldr r3, [motor_control_driver + 0x120]   ; active_level
c05d6970  cmp r3, r0
   gleich  -> *out = 1, return 0
   sonst   -> *out = 0, return 0
```

Bei `limiter_num == 1` — dem Fall der HY310 — wird das Argument `dir`
**überhaupt nicht ausgewertet**. Derselbe Pin beantwortet „darf ich hoch?" und
„darf ich runter?".

Und beide Fahrfunktionen kehren um, wenn `*out == 0` wird:

| | Funktion | Adresse | Quelle |
|---|---|---|---|
| hoch | `motor_run_up_control` | `0xc05d6ea0` | `motor-control.c:299–352` |
| runter | `motor_run_dn_control` | `0xc05d70d4` | symmetrisch |

Rekonstruiert aus Disassembly plus DWARF-Zeilen (`motor_run_up_control`):

```c
299  int motor_run_up_control(int step) {
302      if (g_motor_edge_Up) return 0;
304      motor_limiter_status(&irq, MOTOR_UP);
...
316      motor_run_up_mstep(step);
317      motor_limiter_status(&irq, MOTOR_UP);
318      if (irq == 0) {                       /* Bereich verlassen */
319          for (k = 0; k < 40; k++) {
320              motor_run_dn_mstep(step);     /* zurück */
321              motor_limiter_status(&irq, MOTOR_UP);
323              if (irq == 1) {               /* wieder drin */
324                  for (t = 0; t < back_step; t++) { ... }
335                  g_motor_edge_Up = 1;      /* Kante gemerkt */
                     break;
                 }
             }
         }
351      return 1;
```

Ein einzelner Anschlagkontakt kann nicht beide Enden melden. Ein Fenstergeber
kann es: **drin = 1, draußen = 0**, und welches Ende man verlassen hat, weiß
der Treiber aus der Richtung, in die er gerade gefahren ist.

### 2.2 Stock nennt den Zustand selbst beim Namen

`check_motor_position()`, inline in `motor_control_probe`
(`motor-control.c:716–751`, Aufruf bei `:1280`):

```c
716  status = 0;
718  if (limiter_num == 1) {
719      motor_limiter_status(&status, 0);
720      if (status == 1)
721          printk("limited normal,no need to check postion\n");
722      else {
724          do { motor_run_up_mstep(1); motor_limiter_status(&status,0); }
727          while (status == 0 && ++i != 100);
733          printk("motor_run_up_mstep %d times, and back to normal\n", i);
             ...
738          while (status == 0) { motor_run_dn_mstep(1); ... if (++i==250) break; }
747          printk("motor_run_dn_mstep %d times, and back to normal\n", i);
748          g_motor_edge_Up = 1;
751          printk("zztest--can't back to normal position\n");
         }
     }
```

`status == 1` heißt für den Hersteller wörtlich **„limited normal"** — der
Wächter liest seinen *normalen* Wert. `status == 0` ist der Ausnahmefall, und
Stock **sucht** dann: bis zu 100 msteps hoch, danach bis zu 250 msteps runter,
bis der Wächter wieder normal liest. Genau davon hat unser Treiber
`HOMING_UP_MAX = 100` und `HOMING_DN_MAX = 150` (100 + 150 = 250).

Damit ist die Richtung eindeutig: **in-Bereich = `active_level` = HIGH.**

### 2.3 `active_level` ist bindend, nicht dekorativ

Im echten Vendor-Gerätebaum:

```
hy310_factory.dts:2642   limiter-up-gpio = <0x2c 0x07 0x0e 0x00>;   /* &pio PH14 */
hy310_factory.dts:2643   active_level    = <0x01>;
bootpkg-full.dts:2916/2917   dasselbe
```

`motor_control_fdt_parse` @ `0xc05d62c8` liest es als **erstes** und macht das
Fehlen tödlich:

```
c05d6314  ldr r1, ="active_level"
c05d6320  bl  of_property_read_u32
c05d6324  cmp r0, #0
c05d6328  ldrne r1, ="failed to active_level_flag\n"
c05d635c  bl  _dev_err
c05d6360  mvn r0, #0x15            ; -EINVAL, Probe bricht ab
```

Kein `active_level` → kein Motor. Das ist eine Eigenschaft derselben Klasse wie
`ntc_num`.

### 2.4 `limiter_num` ist das Tor — und es ist keine DTS-Eigenschaft

`limiter_num` (`0xc153fc40`) steht **nirgends im Gerätebaum**. Es wird gezählt:
`motor_control_fdt_parse` erhöht es einmal je Limiter-GPIO, das sich sowohl
auflösen **als auch** anfordern ließ:

```
c05d65c0  of_get_named_gpio_flags(np, "limiter-up-gpio", 0, NULL)
   < 0 -> dev_err("failed to get property limiter-gpio")   und weiter zum dn
c05d65e4  gpio_request(pin, "limiter-up-gpio")
   < 0 -> dev_err("failed to request gpio_%d as %s")
c05d6618  gpiod_direction_input(...)
c05d6620  MOTOR_LIMITER_PIN = limter_up_pin
c05d662c  limiter_num++
   danach dasselbe für "limiter-dn-gpio"
```

Die HY310 hat nur `limiter-up-gpio`, kein `limiter-dn-gpio` → `limiter_num == 1`.
Das ist auch der Grund, warum `dir` in 2.1 ignoriert wird.

---

## 3. Zwei Fehler in unserer bisherigen Beweiskette

### 3.1 `boot.log:284` sagt das Gegenteil von dem, was wir gelesen haben

`doku/94` führt diese Zeile als Beleg, „dass der Schalter unter Stock einmal
aktiv gelesen wurde":

```
[    0.475418] motor-control motor_ctr: failed to get property limiter-gpio
```

Das ist kein Lesevorgang. Das ist `dev_err` aus `motor_control_fdt_parse`, und
zwar für das **nicht vorhandene** `limiter-dn-gpio` (Zeichenkette `0xc1161ada`,
benutzt an `0xc05d65d0` *und* `0xc05d6650` — beide Stellen drucken denselben
Text). Es steht genau **eine** solche Zeile im Log, also ist genau **eine** der
beiden Abfragen gescheitert. Dass es die `dn`-Abfrage war, zeigt der
GPIO-Abzug des laufenden Stock-Systems:

```
re/captures/HY310-DEV/stock_gpio_debug.txt:9
gpio-238 (                    |limiter-up-gpio     ) in  lo
```

`limiter-up-gpio` ist also angefordert worden → `limiter_num == 1`.

### 3.2 Die 8,5 ms sind trotzdem ein Beleg — nur für etwas anderes

Das Zeitargument aus `doku/94` trägt, wenn man es an `check_motor_position`
hängt statt an einen Lesevorgang. Ein mstep kostet

```
delay_ms_func @ 0xc05d6b00:
   autofocus == 0 -> usleep_range(800*n, 1000*n)   /* µs */
motor_run_up_mstep @ 0xc05d6b6c:
   motor-cycle (2) × motor-step-num (8) = 16 Phasenschritte × ~0,9 ms ≈ 14,4 ms
```

Zwischen der Motor-Zeile (0,475418) und der nächsten Kernelzeile (0,483916)
liegen 8,5 ms. Das ist **weniger als ein einziger mstep**. Die Suchschleife aus
2.2 (100 msteps ≈ 1,4 s) kann nicht gelaufen sein. Also hat der erste
`motor_limiter_status()` im Probe `status == 1` geliefert:
**PH14 stand beim Booten auf HIGH.**

> **Ehrlich dazu:** die vier `printk()` aus 2.2 stehen *nicht* im Log — aber das
> beweist nichts. Sie sind nacktes `printk()` ohne `KERN_`-Präfix, also Stufe 4,
> und die Konsole dieser Aufnahme unterdrückt Stufe ≥ 4: im ganzen `boot.log`
> fehlen „Kernel command line", „Memory:", „Freeing unused kernel memory" und
> auch das `dev_info` „probe success", während jedes `dev_err` da ist. Die
> Abwesenheit der Meldungen ist kein Gegenargument, das Zeitargument steht
> allein.

### 3.3 Die 440-mstep-Messung wurde am Messaufbau vorbei gemacht

`doku/94` fuhr 440 msteps **ohne Bias** und schloss aus „der Pin blieb überall
HIGH", die Leitung trage keine Positionsinformation.

Unter dem Fenstermodell ist „überall HIGH" aber genau das **erwartete**
Ergebnis: 440 msteps sind gut die Hälfte des in der DTS hinterlegten Fahrwegs
(`MOTOR_STEP_TOTAL = 0x320 = 800`, gesetzt in `motor_control_probe` bei
`0xc05d7718`), quer durch die Mitte. Der Bereichsrand liegt an den Enden. Es
wurde nie ein Rand angefahren, also konnte nie ein Wechsel auftreten.

Die Messung, die etwas gezeigt hätte — mit Stock-Bias über den ganzen Weg — ist
nie gemacht worden. Mit Pull-down stand der Pin bei jeder Prüfung auf `lo`, und
das ist unter Pull-down zwangsläufig so, siehe unten.

---

## 4. Warum wir nichts sehen

`hy310-focus-motor.c` setzt beim Probe den Bias fest:

```c
default:
        bias = PIN_CONF_PACKED(m->active_level ? PIN_CONFIG_BIAS_PULL_DOWN
                                               : PIN_CONFIG_BIAS_PULL_UP, 1);
```

`active_level == 1` → **Pull-down**. Begründet war das mit „the defined idle
level for active_level = 1". Diese Regel gibt es im Herstellercode nicht.
Zwischen `gpio_request()` und dem ersten Lesen steht bei Stock kein einziges
`gpiod_set_config()`, und der Knoten `motor_ctr` hat keine pinctrl-Gruppe.

Der Pull-down im Stock-Pinabzug ist das, was die **Bootkette** hinterlässt,
nicht das, was der Treiber herstellt. Wir haben eine Beobachtung am laufenden
System für eine Absicht des Treibers gehalten.

Und die Folge ist nicht harmlos. In-Bereich ist HIGH. Ein interner Pull-down
zieht die Leitung auf LOW, sobald der Geber nicht selbst aktiv Strom liefert —
also bei jedem hochohmigen Ausgang, jedem Open-Drain-Ausgang, jedem Geber, der
einen externen Pull-up erwartet. Das Ergebnis ist „außerhalb" an **jeder**
Position, für immer. Genau das steht in `doku/94` in der Tabelle:

| Bias | Abzug | unter dem Fenstermodell |
|---|---|---|
| Pull-down | `in lo` | „außerhalb" — erzwungen, unabhängig vom Geber |
| Pull-up | `in hi` | „innerhalb" — ebenfalls erzwungen, wenn nichts angeschlossen ist |
| ohne Bias | `in hi` | offen; sagt nur, dass nichts kräftig nach Masse zieht |

Keine der drei Zeilen kann für sich sagen, ob der Geber lebt. Das kann nur eine
Fahrt bis an einen Bereichsrand.

---

## 5. Was der Fix tut

**`0001-…-pad-bias-des-endschalters-nicht-mehr-erzwingen.patch`**

* Vorgabe `limiter_bias = -1` heißt ab jetzt **„Pad nicht anfassen"** — wie Stock.
* `3` ist neu und macht das alte Verhalten (Gegenstück zu `active_level`)
  weiterhin erreichbar; `0`/`1`/`2` bleiben wie in Patch `0115`.
* Die Probe-Meldung nennt den **Rohpegel** und dessen Auslegung, nicht nur die
  Auslegung.
* Die Kommentare, die die erfundene Schaltungsannahme („der Schalter liefert im
  aktiven Fall 3,3 V und ist sonst offen") als Tatsache führten, sind
  ersetzt — mitsamt Belegstellen.

**`0002-…-rohpegel-des-endschalters-in-motor-limit-zeigen.patch`**

* `motor_limit` gibt zusätzlich `raw=`, `act=`, `edge_up=`, `edge_dn=`, `step=`
  aus. Erstes Feld unverändert (Stock-kompatibel).
* Damit reicht eine Shell-Schleife, um den Wächter über den Fahrweg abzutasten.

Beide Patches sind **nur** am Treiber. Der DTS-Knoten steht weiter auf
`disabled` (`0024`); daran ändert hier nichts etwas — das Modul wird von Hand
geladen.

### Was unsicher bleibt

* **Ob der Geber auf diesem Gerät etwas liefert, ist nicht belegt.** Belegt ist
  nur, dass unsere bisherige Messung es nicht zeigen *konnte*.
* Dass der Geber hochohmig / Open-Drain ist, ist eine **Hypothese**. Sie erklärt
  alle Messwerte, aber sie ist nicht aus dem Herstellercode belegt — der sagt
  über die Schaltung nichts.
* Der Verdacht aus `doku/94`, unser alter Treiber habe die Leitung durch
  `GPIOF_OUT_INIT_LOW` beschädigt, ist weiterhin weder belegt noch widerlegt.
* Der Stock-GPIO-Abzug zeigt `in lo`. Wenn der Stock-Pad wirklich Pull-down hat
  **und** die Mechanik damals im Bereich stand, müsste der Geber aktiv HIGH
  treiben können — dann wäre die Open-Drain-Hypothese falsch und der Geber
  wirklich tot. Der Test unten unterscheidet beides.

---

## 6. Testanleitung für Marco

### ⚠ Was hier gefährlich ist

> Der Motor fährt echte Mechanik gegen einen Anschlag.
>
> 1. **`limiter_bias=1` (Pull-up) schaltet den Schutz faktisch ab.** Ist kein
>    Geber da, liest der Wächter *dauerhaft* „innerhalb", und der Treiber hat
>    dann **keinen** Grund mehr umzukehren. Er würde bis zum Anschlag
>    weiterstepppen. Deshalb in diesem Modus **nur 2 msteps pro Befehl** und
>    **nur mit Abbruchzählung** fahren, so wie unten.
> 2. **Nie `motor_ctrl_no_limit=1` setzen.** Das schaltet die Prüfung explizit
>    ab und ist für diesen Test nie nötig.
> 3. **Immer `homing=0` laden.** Ohne das fährt schon das Laden des Moduls bis
>    zu 100 msteps **aufwärts** — und steht die Mechanik oben, drückt das in den
>    Anschlag.
> 4. **Zuerst abwärts fahren, nie zuerst aufwärts.** Wo die Mechanik steht,
>    weiß niemand; `doku/94` hat sie bewusst stehen lassen. Abwärts ist die
>    Richtung weg vom oberen Anschlag.
> 5. **Hinhören.** Ein Schrittmotor am Anschlag rattert/brummt hörbar, statt
>    gleichmäßig zu ticken. Beim ersten anderen Geräusch: abbrechen
>    (Schritt 0 unten) und nicht weiterfahren.

### Vorbereitung

Der DTS-Knoten steht auf `disabled`, das Modul steht auf der Blacklist. Für den
Test den Knoten aktivieren (`&motor_ctr { status = "okay"; };`) **oder** das
Modul von Hand laden, wenn der Knoten schon okay ist. Die Blacklist
`/etc/modprobe.d/hy310-focus-motor.conf` verhindert nur das automatische Laden,
nicht `insmod`.

```sh
S=/sys/devices/platform/motor-ctr      # Pfad ggf. mit find /sys -name motor_limit prüfen
```

### Schritt 0 — Notbremse, vorher merken

```sh
rmmod hy310_focus_motor        # stoppt die Phasen und gibt die Pins frei
```

### Schritt 1 — ohne jede Bewegung: was liefert der Pin unter welchem Bias?

Drei Ladevorgänge, **kein** Fahrbefehl dazwischen. `homing=0` sorgt dafür, dass
sich nichts bewegt.

```sh
for B in -1 0 1 2; do
    insmod hy310_focus_motor.ko homing=0 limiter_bias=$B
    dmesg | tail -3
    cat $S/motor_limit
    rmmod hy310_focus_motor
done
```

Erwartet wird die Tabelle aus Abschnitt 4. Neu ist `limiter_bias=-1`: **welchen
Pegel liefert der Pad, wenn ihn niemand anfasst?** Das ist der Zustand, in dem
Stock ihn liest, und den kannten wir bisher nicht.

*Ergebnis notieren.* Ist `raw=1` bei `limiter_bias=-1`, ist der Pin im
Stock-Zustand HIGH = „im Bereich" — passend zu 3.2, und Schritt 2 kann
vollständig ohne Bias-Zwang laufen.

### Schritt 2 — der eigentliche Test: einen Bereichsrand suchen, abwärts

Nur machen, wenn Schritt 1 für den gewählten Bias `raw=1` (= „im Bereich")
zeigt. Sonst gibt es nichts zu verlieren und der Test ist sinnlos.

```sh
insmod hy310_focus_motor.ko homing=0 limiter_bias=-1     # oder =0, siehe Schritt 1

n=0
while [ $n -lt 150 ]; do                  # harte Obergrenze: 150 × 2 = 300 msteps
    cat $S/motor_limit
    echo $(( (9 << 8) | 2 )) > $S/motor_ctrl     # 9 = ABWÄRTS, 2 msteps
    sleep 0.3
    n=$((n+1))
done
```

**Abbrechen (Strg-C, dann `rmmod`), sobald**

* das Motorgeräusch sich ändert (Rattern statt Ticken), **oder**
* `raw=` von 1 auf 0 springt — *das ist der gesuchte Bereichsrand*, **oder**
* im `dmesg` „limiter did not return in range" auftaucht.

Was der Test zeigt:

| Beobachtung | Bedeutung |
|---|---|
| `raw=` kippt irgendwann von 1 auf 0, Treiber kehrt um | **Der Geber lebt.** Der Fix ist die Lösung, `doku/94` ist widerlegt, Homing kann wieder scharf gestellt werden. |
| `raw=` bleibt 300 msteps lang 1, Motor läuft ruhig weiter | Der Bereichsrand liegt weiter weg, oder der Geber liefert nichts. Weiter mit Schritt 3. |
| `raw=` ist von Anfang an 0 | Unter diesem Bias ist nichts zu sehen — anderen Bias aus Schritt 1 nehmen. |

### Schritt 3 — nur falls Schritt 2 ergebnislos blieb

Denselben Lauf **aufwärts** (`(8 << 8) | 2`), aber mit **50** Durchläufen statt
150 und besonders aufmerksam hinhören: aufwärts liegt der Anschlag, gegen den in
der Vergangenheit gedrückt wurde. Bei der geringsten Geräuschänderung sofort
abbrechen.

Bleibt auch das ergebnislos, ist der Geber auf diesem Gerät tot oder nicht
angeschlossen, und dann gilt `doku/94` Abschnitt „Wie es weitergehen könnte"
unverändert weiter — mit der Ergänzung, dass Stock in diesem Fall **auch**
nichts erkennt, sondern nach 40 vergeblichen Umkehrschritten die Kante einfach
**behauptet** (`motor_run_up_control`, `g_motor_edge_Up = 1` bei `k == 40`,
`0xc05d7014`). Was Marco als „Stock erkennt den Anschlag" gesehen hat, wäre
dann dieses Verhalten: der Motor ruckt kurz, fährt netto zurück, und weitere
Aufwärtsbefehle werden stillschweigend verworfen.

### Aufräumen

```sh
rmmod hy310_focus_motor
```

Der Fokus bleibt stehen, wo er steht — nicht „zur Sicherheit" zurückfahren, das
wäre wieder eine Fahrt ohne Bezugspunkt.

---

## 7. Nachweis, dass es übersetzt

Wegwerfbaum `mainline/build/wegwerf-motor-limiter` (Kopie von
`linux-6.18.38-41db1941f6c82e1b7a50f852707ef6a0a2f22bb16e23521a86246208862d8312`),
beide Patches der Reihe nach angewandt, danach gelöscht.

```
$ patch -p1 -d mainline/build/wegwerf-motor-limiter < 0001-...patch
patching file drivers/misc/hy310-focus-motor.c
$ patch -p1 -d mainline/build/wegwerf-motor-limiter < 0002-...patch
patching file drivers/misc/hy310-focus-motor.c

$ podman exec h713-build bash -lc 'cd /work/mainline/build/wegwerf-motor-limiter && \
    make ARCH=arm64 LLVM=1 -j16 M=drivers/misc modules'
  CC [M]  hy310-focus-motor.o
  LD [M]  hy310-focus-motor.ko
exit=0
-rw-r--r-- 1 ubuntu ubuntu 32744 drivers/misc/hy310-focus-motor.ko
```

Keine Warnungen, kein Fehler.

---

## 8. Was in `doku/94-fokusmotor-endschalter.md` korrigiert gehört

Nicht selbst geändert — Zusammenführen macht Marco.

1. **Kurzfassung / „Was das heißt":** „der Endschalter liefert kein Signal" ist
   nicht belegt. Belegt ist: unter Pull-down kann er keins liefern.
2. **„Ein Verdacht, der benannt gehört":** `boot.log:284` belegt keinen
   erfolgreichen Lesevorgang, sondern das Fehlen von `limiter-dn-gpio`. Das
   Zeitargument bleibt gültig, hängt aber an `check_motor_position` (§3.2).
3. **„Die Leitung trägt keine Positionsinformation":** die 440 msteps wurden
   ohne Bias und in der Mitte des Fahrwegs gefahren; „überall HIGH" ist dort das
   erwartete Ergebnis, kein Befund (§3.3).
4. **Der Name:** „Endschalter" führt in die Irre. Es ist ein Bereichswächter.
5. **„Warum Software-Grenzen das nicht auffangen"** bleibt vollständig gültig.
