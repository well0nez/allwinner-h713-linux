# WLAN AIC8800D80 — Einschaltleitung und das Stummbleiben am SDIO-Bus

Stand: 12.09.2026. Vorschlag, **nichts davon ist am Geraet getestet**.
Ausgangspunkt: `analyse/boot/wlan-aic8800-messung-20260912.txt`.

| Datei | Was |
|---|---|
| `0001-arm64-dts-h713-die-wlan-einschaltleitung-in-den-geraetebaum.patch` | `wlan-enable-gpios` in `mmc@4021000/wifi@1` |
| `0002-aic8800-die-einschaltleitung-aus-dem-geraetebaum-holen.patch` | Treiber holt die Leitung per gpiod aus dem DT; ersetzt die feste 385 in `aic8800-0002` |
| `0003-aic8800-den-sdio-scan-wiederholen-solange-auf-den-chip-gewartet-wird.patch` | optional, unabhaengig; fasst dieselbe Zeile an wie `aic8800-0003` |
| `bauprotokoll.txt` | Nachweis, dass es uebersetzt |

---

## A. Wie die Einschaltleitung jetzt gefunden wird

Im Geraetebaum, im Knoten, der den Chip ohnehin schon beschreibt:

```dts
sdio_wifi: wifi@1 {
        reg = <1>;
        interrupt-parent = <&r_pio>;
        interrupts = <1 0 IRQ_TYPE_LEVEL_LOW>;   /* PM0 = host-wake */
        interrupt-names = "host-wake";
        wlan-enable-gpios = <&r_pio 1 1 GPIO_ACTIVE_HIGH>;   /* PM1 */
};
```

Der Treiber sucht den Knoten ueber die Eigenschaft selbst
(`of_find_node_with_property(NULL, "wlan-enable-gpios")`) und holt die Leitung
mit `fwnode_gpiod_get_index()`. Bank, Pin und Polaritaet stehen damit im
Geraetebaum, nicht im Code.

Derselbe Knoten dient gleich als Anker fuer den MMC-Host: sein Elternknoten
**ist** der Controller. Damit faellt die zweite fest verdrahtete Angabe im
Treiber weg — der Plattformname `"4021000.mmc"` bleibt nur noch als Rueckfall
stehen, falls die Eigenschaft im DT fehlt.

`wlan_regon=<n>` bleibt als Uebersteuerung erhalten, hat aber keinen
Standardwert mehr. Ohne Parameter gilt der Geraetebaum; mit Parameter schreibt
der Treiber eine Warnung ins Log, dass der Geraetebaum uebergangen wird.

### Warum kein `mmc-pwrseq`

`mmc-pwrseq-simple` mit `reset-gpios` waere der andere mainline-uebliche Weg
und haette den Reiz, dass der MMC-Kern den Chip schon beim ersten Scan
einschaltet. Dagegen spricht der **Besitz** der Leitung: der AIC-Treiber
schaltet selbst — aus, 50 ms warten, an, 50 ms warten, Scan anstossen — und
nimmt dem Chip den Strom wieder weg, wenn er nicht hochkommt
(`aicbsp_platform_power_on`/`-off`). Gehoert die Leitung dem pwrseq, scheitert
die Anforderung des Treibers mit `-EBUSY`, und genau diese Sequenz faellt aus.
Zwei Besitzer fuer eine Leitung ist die Art Fehler, die spaeter niemand mehr
findet.

Der pwrseq bleibt Plan B, falls wir die Stromsteuerung eines Tages ganz aus dem
Treiber nehmen. Dann braucht er `post-power-on-delay-ms`, weil der MMC-Kern
sonst unmittelbar nach dem Einschalten das erste CMD52 schickt.

`mmc1` selbst bleibt unveraendert: weiterhin **kein** `non-removable`, **kein**
`vqmmc-supply`. Beides stimmt mit Stock ueberein und ist nicht zu reparieren.

---

## B. Warum der Chip stumm blieb

**Die Sequenz hat PM1 nie angefasst. `wlan_regon=225` ist nicht PM1, sondern
PH1 — eine der beiden UART0-Leitungen der Debug-Konsole.**

### Die Beweiskette (alles aus dem Quelltext des laufenden Kernels)

1. **Die sunxi-pinctrl vergibt statische GPIO-Basen, keine dynamischen.**
   `drivers/pinctrl/sunxi/pinctrl-sunxi.c`:

   ```c
   pctl->chip->ngpio = round_up(last_pin, PINS_PER_BANK) - pctl->desc->pin_base;
   pctl->chip->base  = pctl->desc->pin_base;
   ```

   `pinctrl-sun50i-h713-r.c` setzt `.pin_base = PL_BASE` (= 352) und beschreibt
   PL0..PL15 und PM0..PM4; letzter Pin PM4 = 388, also
   `ngpio = round_up(388,32) - 352 = 64`. Der R-PIO-Chip deckt **352..415** ab.
   `pinctrl-sun50i-h713.c` setzt kein `pin_base` (= 0) und endet bei PH19 = 243,
   also `ngpio = 256`; die Haupt-PIO deckt **0..255** ab.

   Beide Groessen stimmen mit der Messung ueberein: *"gpiochip0: 256 GPIOs",
   "gpiochip1: 64 GPIOs"*.

2. **Die Messung belegt das Modell mit ihrem eigenen Datenpunkt.** GPIO 289
   lieferte `-517` = `-EPROBE_DEFER`. Genau das gibt `gpio_request()` zurueck,
   wenn **kein** gpiochip die Nummer abdeckt
   (`drivers/gpio/gpiolib-legacy.c`: `desc = gpio_to_desc(gpio); if (!desc)
   return -EPROBE_DEFER;`) — und 289 faellt in die Luecke zwischen 256 und 352.
   Unter der in der Messung angenommenen Basisvergabe (PIO bei 256, R_PIO bei
   192) waere 289 eine gueltige Leitung gewesen und haette `-EPROBE_DEFER` nicht
   ergeben koennen.

3. **Damit ist 385 = PM1**: 352 + 1·32 + 1. Die hartkodierte Zahl beschrieb auf
   diesem Kernel die richtige Leitung.

4. **Und 225 = PH1**: 7·32 + 1 auf der Haupt-PIO.
   `pinctrl-sun50i-h713.c` fuehrt fuer PH1 die Funktion `0x2 = "uart0"`, der
   Stock-Geraetebaum hat `uart0@0 { pins = "PH0", "PH1"; }`, und `serial0` ist
   die Konsole. Nach Allwinner-Konvention ist PH0 = TX und PH1 = RX; die genaue
   Richtungszuordnung ist nicht gemessen, fuer den Befund aber egal.

5. **Warum sich PH1 trotzdem anfordern liess:** im uebersetzten DTB hat die
   Gruppe `uart0-ph-pins` **kein phandle**, und `serial@2500000` hat **gar kein
   `pinctrl-0`**. Niemand beansprucht die Leitung im Linux-Pinmux — der Mux
   stammt noch vom Bootloader. `gpio_request(225)` kam also durch, und
   `gpio_direction_output(225, 0)` hat PH1 anschliessend als GPIO-Ausgang
   umgehaengt.

Damit erklaert sich das Messbild vollstaendig: die Sequenz lief durch, die
Logzeilen kamen, `mmc_detect_change` wurde abgesetzt — und der Chip hatte in
der ganzen Zeit keinen Strom, weil PM1 unberuehrt blieb.

> **Nicht noch einmal `wlan_regon=225` setzen.** Der USB-Serial-Adapter treibt
> dieselbe Leitung; zwei Ausgaenge auf einem Draht. Und die Konsoleneingabe ist
> danach bis zum Neustart tot (die Ausgabe laeuft weiter, deshalb faellt es
> nicht auf).

### Was ich damit **nicht** erklaeren kann

**Warum `gpio_request(385)` scheiterte, weiss ich nicht.** Die Fehlernummer zu
dieser Zeile ist nicht protokolliert. Nach der Analyse oben ist 385 gueltig und
im DTB beansprucht sie niemand (kein `r_pio`-Verweis auf Bank 1 ausser dem
host-wake auf PM0). Zwei Kandidaten, beide pruefbar:

* **`-EBUSY` (-16) bei einem Wiederholungsversuch.** `aicbsp_mainline_gpio_init()`
  fordert die Leitung bei **jedem** `aicbsp_platform_power_on()` neu an, gibt sie
  aber erst beim Entladen des Moduls frei. Nach einem erfolglosen ersten Anlauf
  muss der zweite `insmod aic8800_fdrv` zwangslaeufig an `-EBUSY` scheitern.
  Patch 0002 macht die Funktion idempotent.
* **etwas anderes beansprucht PM1.** Dann nennt der neue Treiber es im Klartext
  samt Fehlernummer, statt nur eine Zahl zu melden.

Das spricht dafuer, dass 385 richtig war: **am 21.08. lief WLAN auf diesem
Geraet vollstaendig** — `mmc1: new UHS-I speed SDR104 SDIO card at address 6721`,
8 und 128 MiB in beide Richtungen fehlerfrei, siehe
`mainline/docs/handoff-wifi-sdio-2026-08-17.md`. Derselbe Treiber mit derselben
385 im Code. Ob der Treiber den Chip damals einschaltete oder ob er schon an
war, laesst sich aus den Protokollen nicht entscheiden.

### Was ich ausgeschlossen habe

* **„Keine einzige mmc-Meldung im Log" ist kein Befund.** Der gesamte
  Fehlschlagpfad von `mmc_rescan()` / `mmc_rescan_try_freq()` /
  `mmc_attach_sdio()` ist `pr_debug`. Auf Loglevel 8 schweigt ein erfolgloser
  Scan vollstaendig; nur der Erfolg druckt (`mmc1: new ... SDIO card`). Die
  Stille ist genau das, was ein Scan ohne Karte erzeugt. Wie man ihn sichtbar
  macht, steht unten.
* **`mmc_rescan()` wird nicht blockiert.** Die beiden Ausstiege am Anfang
  greifen hier nicht: der „nur einmal scannen"-Ausstieg haengt an
  `MMC_CAP_NONREMOVABLE`, und `non-removable` steht nicht im Knoten; der
  `get_cd()==0`-Ausstieg kann nicht greifen, weil `sunxi_mmc_ops.get_cd` auf
  `mmc_gpio_get_cd()` zeigt und das ohne `cd-gpios` `-ENOSYS` liefert, nicht 0
  (`drivers/mmc/core/slot-gpio.c`). Die Sorge aus dem DTS-Kommentar ist also
  berechtigt formuliert und trifft in der jetzigen Fassung nicht zu.
* **Die fehlende `vqmmc-supply` blockiert nichts.** `sunxi_mmc_volt_switch()`
  gibt ohne vqmmc-Regler bei 3,3 V schlicht 0 zurueck, und der v5p3x-Zweig
  akzeptiert zusaetzlich den 1,8-V-Zustand.
* **Pinmux von mmc1 ist stock-identisch.** Aus dem uebersetzten DTB:
  `PG0..PG5`, `function = "mmc1c"`, `drive-strength = <0x28>`, `bias-pull-up` —
  Zeichen fuer Zeichen die Stock-Gruppe `sdc1@0` aus `hy310_factory.dts`.
  Die Schlafgruppe ist ebenfalls dieselbe (`gpio_in`).
* **Der Takt von mmc1 ist geklaert und nicht neu zu messen.** Kernel-Patch 0048,
  am 21.08. am Geraet bestaetigt: CCU `0x02001834` = `0x8100000B` → 600/12 =
  50 MHz am Pin, gegengeprueft gegen eine CMD53-Zeitmessung. `max-frequency`
  im DTB ist 50 MHz, und `sd-uhs-sdr25/50/104` und `ddr50` sind da.
* **Firmware ist noch nicht im Spiel.** Sie wird erst nach der Enumeration
  geladen.
* **Die Zeiten der Einschaltsequenz weichen nicht vom Hersteller ab.** Der
  BSP-Pfad im selben Quelltext macht `set_power(0); mdelay(50); set_power(1);
  mdelay(50); rescan`. Unser Pfad macht dasselbe. Die in der Messung notierten
  54 ms sind die 50 ms plus Messauflösung.

### Was unsicher bleibt

* Ob der Chip innerhalb von ~250 ms nach dem Einschalten am SDIO-Bus antwortet,
  ist **nicht gemessen**. Dass der Hersteller-BSP dieselben Zeiten benutzt,
  spricht dafuer, beweist es aber nicht. Patch 0003 macht die vorhandene
  Wartezeit deshalb nutzbar (siehe dort).
* Ob der 24-MHz-DCXO-Ausgang wirklich vom Bootloader eingeschaltet bleibt. Der
  Treiber nimmt es an und prueft es nicht. Dieselbe Annahme galt im August, als
  es lief — das ist ein Indiz, kein Beleg. Pruefbar mit
  `busybox devmem 0x07090160` (Bit 31).
* Der genaue Grund fuer den Fehlschlag mit 385, siehe oben.

---

## Testanleitung

Drei Stufen. **Stufe 0 kostet keinen Stromzyklus** und beantwortet die
wichtigste offene Frage schon allein.

Merkzettel fuer alle Stufen — so sieht PM1 von aussen aus:

```sh
busybox devmem 0x07022030      # Mux Bank M, PM1 in Bits [7:4]: 0=Eingang 1=Ausgang
busybox devmem 0x07022040      # Datenregister Bank M, PM1 = Bit 1
cat /sys/kernel/debug/gpio     # PM1 steht dort als "gpio-33" unter 7022000.pinctrl
```

Zwei Dinge zur debugfs-Ausgabe: sie zaehlt **je Chip ab 0**, nicht global
(`gpiolib_dbg_show()` in 6.18 fuehrt einen eigenen Zaehler) — PL4 als `gpio-4`
ist also richtig und sagt nichts ueber die Basis. Und sie zeigt eine Leitung nur
dann, wenn sie angefordert oder als IRQ belegt ist; taucht `gpio-33` nicht auf,
gehoert PM1 niemandem.

### Stufe 0 — laufender Kernel, altes Modul, kein Neustart

Ziel: die Fehlernummer zu 385 sehen, und pruefen, ob es mit 385 einfach laeuft.

```sh
rmmod aic8800_fdrv 2>/dev/null; rmmod aic8800_btlpm 2>/dev/null; rmmod aic8800_bsp
dmesg -C
modprobe aic8800_bsp            # Standardwert des alten Moduls ist 385
modprobe aic8800_fdrv
dmesg | grep -iE 'aicbsp|wlan_regon|mmc1|wlan0'
```

(Falls die Module nicht ueber `modprobe` erreichbar sind: `insmod` mit dem
vollen Pfad, bsp zuerst.)

* **Erfolg:** `mmc1: new UHS-I speed SDR104 SDIO card at address ...`, danach
  `rwnx_load_firmware` und `wlan0`. Dann war der Blocker allein der falsche
  Parameter am 12.09. 0001/0002 bleiben trotzdem richtig: sie nehmen die Zahl
  ganz aus dem Code heraus, damit die naechste pinctrl-Aenderung sie nicht
  wieder umwirft.
* **Misserfolg:** `aicbsp: failed to request wlan_regon GPIO 385: <n>`.
  **Diese Zahl `<n>` bitte notieren.** `-16` = `-EBUSY`, dann reicht Patch 0002.
  `-517` = `-EPROBE_DEFER`, dann ist die R-PIO nicht registriert und die Analyse
  oben ist an einer Stelle falsch — dann `cat /sys/kernel/debug/gpio` mitschicken.

### Stufe 1 — neue Module, alter Kernel und altes DTB

Bauen (Patches 0002 + 0003 auf `patches/aic8800/` zusammengefuehrt):

```sh
podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh aic8800'
# -> mainline/build/out/modules/aic8800_{bsp,fdrv,btlpm}.ko
```

Das alte DTB kennt `wlan-enable-gpios` noch nicht, der neue Treiber muss also
uebersteuert werden:

```sh
scp mainline/build/out/modules/*.ko root@<eth0-IP>:/tmp/    # eth0 laeuft
# auf dem Geraet:
rmmod aic8800_fdrv aic8800_btlpm aic8800_bsp 2>/dev/null
dmesg -C
insmod /tmp/aic8800_bsp.ko wlan_regon=385
insmod /tmp/aic8800_fdrv.ko
```

Erwartet:

```text
aicbsp: wlan_regon FORCED to GPIO 385 by module parameter - the device tree is ignored
aicbsp: found mmc_host mmc1 (fallback by name)
aicbsp: disabled MMC_CAP_UHS_DDR50 for mmc1
aicbsp: wlan_regon set to 0
aicbsp: wlan_regon set to 1
aicbsp: mmc_detect_change on mmc1 ...
v5p3x delay: rate=400000  timing=0 width=1 ...
v5p3x delay: rate=50000000 timing=6 width=4 DRV=00030000 NTSR=81710110
mmc1: new UHS-I speed SDR104 SDIO card at address ....
```

Woran man das **neue** Modul erkennt: die Zeile heisst `wlan_regon set to N`,
nicht mehr `wlan_regon PM1 set to N`. Steht das alte Format im Log, laeuft noch
das alte Modul.

Wenn der Chip stumm bleibt, sieht man mit Patch 0003 jetzt jede Sekunde:

```text
aicbsp: no SDIO card after 1000 ms, rescanning mmc
aicbsp: no SDIO card after 2000 ms, rescanning mmc
...
aicbsp: wlan_regon set to 0
aicbsp: aicbsp_set_subsys, fail to set AIC_WIFI power state to 1
```

### Stufe 2 — neuer Kernel mit DTB (der eigentliche Zielzustand)

Patch 0001 aendert das DTB, also braucht es einen Kernelbau und ein neues FIT.
Danach **ohne** `wlan_regon`-Parameter laden. Erwartet statt der FORCED-Zeile:

```text
aicbsp: wlan_regon from /soc/mmc@4021000/wifi@1 -> gpio 385, output low
aicbsp: found mmc_host mmc1 via /soc/mmc@4021000
```

Die `gpio 385` in dieser Zeile ist reine Diagnose — sie kommt aus dem
Geraetebaum und darf sich aendern, ohne dass etwas kaputtgeht. Genau das ist der
Punkt der Uebung.

### Wenn der Chip weiterhin stumm bleibt

In dieser Reihenfolge, jeweils mit Begruendung, warum es der naechste Schritt ist:

1. **Erst pruefen, ob die Leitung wirklich gewackelt hat** — vor und nach dem
   `insmod`:

   ```sh
   busybox devmem 0x07022030   # Bits [7:4] muessen nach dem Laden 1 sein (Ausgang)
   busybox devmem 0x07022040   # Bit 1 muss waehrend der Sequenz 0 -> 1 gehen
   ```

   Steht der Mux nicht auf 1, hat der Treiber die falsche Leitung erwischt, und
   alles weitere ist sinnlos. (Wer ein Messgeraet ansetzen kann: PM1 gegen Masse,
   3,3 V nach dem Einschalten.)

2. **Dann sichtbar machen, ob mmc1 ueberhaupt sucht.** Das ist der Messpunkt aus
   dem Protokoll vom 12.09., der bisher nicht beantwortet werden konnte, weil
   der Pfad schweigt:

   ```sh
   echo 'file drivers/mmc/core/core.c +p' > /sys/kernel/debug/dynamic_debug/control
   echo 'file drivers/mmc/core/sdio.c +p' > /sys/kernel/debug/dynamic_debug/control
   echo 'file drivers/mmc/core/sdio_ops.c +p' > /sys/kernel/debug/dynamic_debug/control
   ```

   (oder `dyndbg="file drivers/mmc/core/* +p"` in den bootargs). Erwartet je
   Versuch:

   ```text
   mmc1: mmc_rescan_try_freq: trying to init card at 400000 Hz
   ```

   * **Zeilen da, Karte nicht** → der Bus fragt, der Chip antwortet nicht. Dann
     ist es Strom, Takt oder Zeit — weiter bei 3 und 4.
   * **Keine Zeile** → `mmc_rescan()` laeuft gar nicht. Dann `host->rescan_disable`
     und die Arbeitswarteschlange ansehen; das waere ein neuer, eigener Befund.

3. **Den 24-MHz-DCXO pruefen**, den der Treiber ungeprueft voraussetzt:

   ```sh
   busybox devmem 0x07090160    # Bit 31 muss gesetzt sein
   ```

   Ist Bit 31 null, hat der Chip keinen Referenztakt und kann gar nicht
   antworten — dann muss der Gate-Bit vor dem Einschalten gesetzt werden (im
   Stock macht das `clocks = <&rtc_ccu 9>` am rfkill-Knoten).

4. **Erst dann an der Zeit drehen.** Mit Patch 0003 laeuft der Scan schon 20 s
   lang jede Sekunde; hilft das nicht, ist es keine Zeitfrage, und die Wartezeit
   zu verlaengern ist verschwendeter Stromzyklus.

Was **nicht** als naechstes zu tun ist: an `FEATURE_SDIO_CLOCK_V3`,
`max-frequency` oder den UHS-Modi drehen. Diese Werte sind am 21.08. am Geraet
validiert worden (128 MiB in beide Richtungen, null SDIO-Fehler), und ein Chip,
der sich gar nicht meldet, hat noch keinen Takt gesehen, der ihm nicht passt.
