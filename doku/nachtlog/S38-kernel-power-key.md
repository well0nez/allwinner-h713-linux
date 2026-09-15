# S38 - Kernel: die Einschalttaste als `gpio-keys` auf PL4 (Paket G3 aus Plan 103)

**Stand 08.09.2026, Agent in der Kopie `analyse/boot/arbeit/g3-kernel/`.** Auftrag
[`g3-kernel/AUFTRAG.md`](../../analyse/boot/arbeit/g3-kernel/AUFTRAG.md), Regeln
[`REGELN.md`](../../analyse/boot/arbeit/REGELN.md), Plan [`103`](../103-plan-einschaltgate.md) §2.4.
Belege: die Messungen vom 08.09. 23:20-00:20 am Gerät (REGELN §„Gemessene Fakten"),
[`S35`](S35-re-arisc-standby-led-key.md) §3c (ARISC-Weg auf denselben Pin), [`S36`](S36-uboot-power-gate.md) (U-Boot-Gate, GP5).
**Kein Board, kein Kernelbau.** Geprüft wurde gegen den gebauten Baum
`mainline/build/linux-6.18.38-d5fd82a7…/` (Serie bis `0138`) - nur lesend.

## 1. Was geliefert wird

| Datei | Inhalt |
|---|---|
| `analyse/boot/arbeit/g3-kernel/patches/0139-arm64-dts-h713-power-key-on-pl4.patch` | DTS: Knoten `gpio_keys` in `sun50i-h713.dtsi` + `#include <dt-bindings/input/input.h>`; `patch -p1` im Kernelbaum |
| `analyse/boot/arbeit/g3-kernel/patches/0139b-board-defconfig-enable-keyboard-gpio.patch` | `CONFIG_KEYBOARD_GPIO=y` in `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig`; `patch -p1` **im Projektwurzelverzeichnis** `/opt/Projekte/h713` |
| `analyse/boot/arbeit/g3-kernel/systemd/10-h713-power-key.conf` | Vorschlag für ein logind-Drop-in, **nicht installiert** |
| `analyse/boot/arbeit/g3-kernel/kopie/` | die geänderten Kopien (`sun50i-h713.dtsi`, `hy200_qz713df_a1_defconfig`), aus denen die Diffs erzeugt wurden |

Beide Patches wurden in einer Wegwerfkopie mit `patch -p1 --dry-run` probeweise angewandt: keine Zurückweisung, kein Fuzz.
Zusätzlich wurde der Gerätebaum **übersetzt** - `cpp` mit den Kernel-Includes, dann `scripts/dtc/dtc` aus dem gebauten Baum
auf `sun50i-h713-hy200-qz713df-a1.dts`: DTB entsteht fehlerfrei, `KEY_POWER` löst zu `116` auf, `GPIO_ACTIVE_LOW` zu `1`.
Das ist eine Syntax- und Auflösungsprüfung, **kein** Bau des aktiven Baums.

Der Knoten selbst:

```dts
	gpio_keys: gpio-keys {
		compatible = "gpio-keys";

		key-power {
			label = "power";
			gpios = <&r_pio 0 4 GPIO_ACTIVE_LOW>;	/* PL4 */
			linux,code = <KEY_POWER>;
			debounce-interval = <50>;	/* ms, stock value */
			wakeup-source;
		};
	};
```

Er sitzt in `sun50i-h713.dtsi` unmittelbar **vor** `adc_keys`, auf derselben Ebene (Wurzelknoten), ohne `status` - also an.
**Kein LED-Knoten**, wie beauftragt: die Frontleuchte folgt PB5 (`fan-bl-power`), PL0/PL1 sind wirkungslos, es gibt keinen
eigenen LED-Baustein (REGELN, bestätigt durch S35 §4).

## 2. Ist PL4 frei? (Auftragspunkt 1)

Ja. Vollständige Fundstellen von PL4 im Baum:

| Fundstelle | Art | Konflikt? |
|---|---|---|
| `standby_param { power_key = "PL4"; key_debounce = <50>; }` (dtsi 2452 ff.) | **Zeichenkette**, kein Phandle, kein `gpios`-Eintrag | nein - kein Linux-Treiber liest den Knoten; er ist für U-Boot und die ARISC da |
| `pinctrl-sun50i-h713-r.c`, `SUNXI_PINCTRL_PIN(L, 4)` | Pin-Beschreibung: `gpio_in` (mux 0), `gpio_out` (1), `s_jtag` MS (2), `PL_EINT4` (mux 6, Bank 0, Nr. 4) | nein |
| ARISC-Firmware `0x00daac` (S35 §3c) | setzt PL4 auf Funktion 14 = EINT, fallende Flanke - **nur beim Eintritt in Standby** | nein, solange Linux läuft; siehe §7 Annahme 2 |

Kein `gpio-hog` auf PL4 (der einzige Hog im Baum ist `fan_power_hog` auf PB5), kein `pinctrl`-Knoten, der PL4 belegt
(im `r_pio` stehen nur `r-ir-rx-pin` = PL9 und `s-pwm1-pin` = PL7), keine `gpios`-Eigenschaft irgendeines Knotens auf
`<&r_pio 0 4 …>`. Der `prj`-Knoten belegt PL0/PL1/PL3, der `board_mgr` PL3 - und beide sind auf diesem Board ohnehin
abgeschaltet (`&board_mgr { status = "disabled"; }` in der Board-DTS). `adc_keys` ist dort ebenfalls abgeschaltet, es gibt
also keine zweite Tastatur, die `KEY_POWER` melden könnte.

## 3. Ist `r_pio` als GPIO-Controller nutzbar? (Auftragspunkt 1)

Ja, und der Interrupt-Weg trägt auch:

* Der Knoten `r_pio: pinctrl@7022000` hat `gpio-controller`, `#gpio-cells = <3>`, `interrupt-controller`,
  `#interrupt-cells = <3>` und zwei Interrupts (GIC-SPI 149 für Bank PL, 151 für PM).
* Es gibt bereits einen Nutzer der R_PIO-Interrupts im Baum: `sdio_wifi` hängt sein `host-wake` an `<&r_pio 1 0 …>` (PM0).
  Der Weg ist also nicht theoretisch.
* `gpio_keys` braucht einen echten Interrupt (sonst `-ENXIO` beim Sondieren). `sunxi_pinctrl_gpio_to_irq()` sucht zu dem Pin
  eine Funktion namens `irq` - PL4 hat sie (`SUNXI_FUNCTION_IRQ_BANK(0x6, 0, 4)`), also liefert `gpiod_to_irq()` eine Nummer.
* **Der Mux wird dabei nicht umgestellt.** Unser Patch `0004` macht das Umschalten von `irq_read_needs_mux` abhängig, und die
  H713-Beschreibungen setzen es auf `false` (im Haupt-PIO ausdrücklich mit dem Kommentar „IRQ works in GPIO mode, mux to func6
  kills input"; die R-Variante lässt das Feld weg, also ebenfalls `false`). Der Pin bleibt damit `gpio_in`, die Flankenerkennung
  läuft über die EINT-Register. Nebenbei löst sich so der scheinbare Widerspruch zu S35: die ARISC schreibt Mux **14**,
  der Treiber deklariert **6** - der Wert wird nie geschrieben, die Abweichung ist folgenlos (aber siehe §7 Annahme 2).
* Die EINT-Registerkarte des Treibers deckt sich mit der aus S35 gemessenen: `IRQ_CFG_REG 0x200` → `0x07022200`,
  Freigabe `0x210`, Status `0x214`.
* `wakeup-source` ist unbedenklich: `sunxi_pinctrl_edge_irq_chip` hat ein `.irq_set_wake`, `enable_irq_wake()` liefert also
  0. Ohne das würde `gpio_keys_suspend()` beim ersten Suspend mit einem Fehler abbrechen.

**Kein Pinconf-Knoten.** Zwei Gründe: der externe Pull-up ist gemessen (Ruhe 1, gedrückt 0), und gpiolib mux't den Pin beim
Anfordern selbst auf `gpio_in`; ein `pinctrl-0` am selben Pin würde ihn nur ein zweites Mal beanspruchen. Der Zurückfallweg,
falls sich doch ein interner Pull einmischt, steht in §7 Annahme 1.

## 4. Defconfig (Auftragspunkt 3)

`CONFIG_KEYBOARD_GPIO` war **nicht** gesetzt - belegt an zwei Stellen:

* `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig` kennt nur `CONFIG_KEYBOARD_ADC=m` und
  `CONFIG_KEYBOARD_SUN4I_LRADC=y`;
* der `.config` des gebauten Baums sagt Zeile 1822 `# CONFIG_KEYBOARD_GPIO is not set` (und 1823
  `# CONFIG_KEYBOARD_GPIO_POLLED is not set`).

`CONFIG_INPUT_KEYBOARD=y` und `CONFIG_INPUT_EVDEV=y` sind vorhanden, es fehlt also wirklich nur der eine Schalter. Der Patch
setzt ihn **fest eingebaut** (`=y`, nicht `=m`), weil die Taste vor jedem Userspace wirken soll, und trägt ihn zwischen
`KEYBOARD_ADC` und `KEYBOARD_SUN4I_LRADC` ein.

Achtung beim Anwenden: die Defconfig ist **nicht Teil der `series`** - `build/build.sh kernel` kopiert die Datei nach
`arch/arm64/configs/`. Deshalb ist der zweite Patch gegen den Projektpfad geschnitten und wird in
`/opt/Projekte/h713` angewandt, nicht im Kernelbaum. Er heißt bewusst `0139b`, damit die Zusammengehörigkeit sichtbar bleibt,
ohne eine Nummer der Kernel-Serie zu verbrauchen.

## 5. systemd / logind (Auftragspunkt 4)

Gelesen in `/srv/h713-rootfs` (nur lesend):

* `etc/systemd/logind.conf` ist die **unveränderte Vorlage** - jede Zeile im `[Login]`-Abschnitt ist auskommentiert,
  auch `#HandlePowerKey=poweroff`. Es gilt also die Vorgabe **`poweroff`**.
* Ein Verzeichnis `etc/systemd/logind.conf.d/` gibt es **nicht**; nichts überschreibt die Vorgabe.
* `usr/lib/udev/rules.d/70-power-switch.rules` ist ebenfalls die Vorlage: `ENV{ID_INPUT_KEY}=="1"` → `TAG+="power-switch"`.
  Ein `gpio-keys`-Gerät mit `KEY_POWER` bekommt `ID_INPUT_KEY=1` vom `input_id`-Builtin und damit die Marke, die logind
  auswertet. `systemd-logind.service` liegt in `usr/lib/systemd/system/`, ein `serial-getty@ttyS0` ist eingerichtet.

**Es ist also nichts zu tun, damit die Taste herunterfährt.** Das gelieferte Drop-in
`analyse/boot/arbeit/g3-kernel/systemd/10-h713-power-key.conf` schreibt die Vorgabe nur ausdrücklich hin, ergänzt
`HandlePowerKeyLongPress=poweroff` (Vorgabe wäre `ignore`) und trägt `PowerKeyIgnoreInhibited=yes` auskommentiert als
Reserve, falls ein Dienst Inhibitor-Sperren nimmt. **Nicht installiert**, wie beauftragt.

Der wichtige Vorbehalt: `poweroff` ist auf diesem Gerät kein Aus. Es gibt keinen PMIC, `sunxi_power_down()` in der TF-A
kehrt zurück, `sunxi_system_off()` parkt nur die Kerne - Linux hält an, Panel und Lüfter bleiben an (PB5 setzt
`h713_poweron_lines()` in U-Boot). Erst das Gate aus G1/G2 macht daraus ein sichtbares Aus. Wie die beiden zusammenfinden,
steht in der Restliste §7.

## 6. Testrezept (ohne `evtest`, ohne `libinput`)

Im Netboot-Rootfs liegen weder `evtest` noch `hexdump`/`xxd`; `od`, `dd`, `udevadm`, `busctl` und `systemd-analyze` sind da.
`CONFIG_GPIO_SYSFS` ist aus, `CONFIG_DEBUG_FS=y` und `CONFIG_GPIO_CDEV=y` sind an.

**Erst entschärfen, dann drücken** - sonst schaltet logind beim ersten Test ab:

```sh
mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress=ignore\n' \
    > /etc/systemd/logind.conf.d/00-test-taste.conf
systemctl restart systemd-logind
systemd-analyze cat-config systemd/logind.conf | grep -i powerkey    # zur Kontrolle
```

**Schritt 1 - bindet der Treiber?**

```sh
dmesg | grep -i "gpio-keys\|gpio_keys"
ls -d /sys/bus/platform/devices/gpio-keys
grep -A4 'Name="gpio-keys"' /proc/bus/input/devices     # liefert die eventN-Nummer
```

**Schritt 2 - sieht udev die Taste als Netzschalter?**

```sh
udevadm info /dev/input/eventN | grep -E "TAGS|ID_INPUT_KEY"    # power-switch, 1
```

**Schritt 3 - kommen Ereignisse an?** `struct input_event` ist auf arm64 24 Byte groß (16 Byte Zeitstempel, dann
`type`, `code`, `value`). Ein Druck erzeugt vier Ereignisse (`EV_KEY`+`EV_SYN` beim Drücken und beim Loslassen):

```sh
dd if=/dev/input/eventN bs=24 count=4 2>/dev/null | od -An -tx1 -w24
```

Erwartet in Byte 17-24 der ersten Zeile: `01 00` (`EV_KEY`), `74 00` (`0x74` = 116 = `KEY_POWER`), `01 00 00 00` (gedrückt).
Die dritte Zeile trägt denselben Code mit `00 00 00 00` (losgelassen). Bleibt `dd` stehen, ist die Flanke nicht angekommen -
weiter mit Schritt 4.

**Schritt 4 - zählt der Interrupt?** `gpio_keys` fordert den Interrupt unter dem `label` an:

```sh
grep -i power /proc/interrupts        # vor und nach dem Drücken vergleichen
mount -t debugfs none /sys/kernel/debug 2>/dev/null
grep -i "gpio-4\|power" /sys/kernel/debug/gpio
```

Steigt der Zähler nicht, liegt es an der Flankenerkennung im `gpio_in`-Mux (§7, Annahme 2), nicht am Gerätebaum.

**Schritt 5 - Zurücknehmen und scharf schalten:**

```sh
rm /etc/systemd/logind.conf.d/00-test-taste.conf
systemctl restart systemd-logind
busctl get-property org.freedesktop.login1 /org/freedesktop/login1 \
    org.freedesktop.login1.Manager HandlePowerKey     # erwartet: s "poweroff"
```

Ein Druck fährt das Gerät jetzt herunter. Vorsicht: bis das Gate aus G1/G2 steht, bleibt danach **das Bild an und der
Lüfter läuft**, und es hilft nur Netz aus/an.

## 7. Offene Annahmen (nicht gemessen)

1. **Kein interner Pull.** Der externe Pull-up ist am Gerät gemessen; ob U-Boot oder die ARISC vorher einen internen Pull
   an PL4 stehen lassen, ist nicht geprüft. Falls die Taste dauerhaft gedrückt erscheint (Ruhe = 0), gehört ein
   Pinconf-Knoten im `r_pio` dazu - `pins = "PL4"; function = "gpio_in"; bias-disable;` - und ein `pinctrl-0` am
   `gpio-keys`-Knoten. Das ist bewusst **nicht** im Patch: es wäre eine ungeprüfte Zweitbelegung desselben Pins.
2. **Flankenerkennung im GPIO-Mux.** `irq_read_needs_mux = false` stammt vom Haupt-PIO (Kommentar in
   `pinctrl-sun50i-h713.c`, dort offenbar gemessen). Für das **R_PIO** ist es nur geerbt (das Feld fehlt in der
   Beschreibung und ist deshalb 0). Die ARISC schreibt für dieselbe Aufgabe Mux 14. Sollte Schritt 4 des Testrezepts
   keine Interrupts zeigen, sind das die zwei Versuche in dieser Reihenfolge: (a) `.irq_read_needs_mux = true` in
   `sun50i_h713_r_pinctrl_data` **und** `SUNXI_FUNCTION_IRQ_BANK(0xe, 0, 4)` statt `0x6` in der PL-Beschreibung -
   das entspricht S35; (b) ersatzweise `compatible = "gpio-keys-polled"` mit `poll-interval = <50>` und
   `CONFIG_KEYBOARD_GPIO_POLLED=y`. Beides ist ein eigener Patch, kein Nachtrag zu 0139.
3. **PM0-Beleg ist schwach.** Dass `sdio_wifi` einen R_PIO-Interrupt benutzt, zeigt, dass die Verdrahtung im Gerätebaum
   stimmt - nicht, dass jemals eine Flanke ankam (WLAN läuft auf diesem Board über SDIO-Polling genauso).
4. **Zweiter Baum.** Der Knoten liegt in der `dtsi`, also erbt ihn auch `sun50i-h713-hy200-qz713-v2.dts` (die
   Projektor-DTS, laut README „strukturell, ungetestet"). Ob dort ebenfalls PL4 die Taste trägt, ist nicht belegt -
   `standby_param` sagt es für die Familie, gemessen ist es nur auf Marcos HY310. Wer das trennen will, verschiebt den
   Knoten in die Board-DTS `sun50i-h713-hy200-qz713df-a1.dts`; der Patch bliebe sonst gleich.
5. **`.orig` im Baum.** Neben `sun50i-h713.dtsi` liegt eine `sun50i-h713.dtsi.orig` aus einem früheren Patchlauf. Der
   Diff wurde gegen die **aktive** Datei erzeugt; die `.orig` ist unberührt und sollte bei Gelegenheit weg (bekannte
   Falle aus der Audio-Serie).
6. **Nicht gebaut.** Kein Kernelbau, kein Board - die Regel des Pakets. Der DTB-Übersetzungslauf oben ist alles, was an
   Prüfung möglich war.

## 8. Restliste

* **Reihenfolge beim Einspielen:** erst `0139b` (Defconfig) in `/opt/Projekte/h713`, dann `0139` im Kernelbaum, dann bauen.
  Ohne den Defconfig-Schalter bindet der Knoten nichts und der Test in §6 Schritt 1 schlägt still fehl.
* **Zusammenschluss mit dem Gate (G1/G2):** logind kann heute nur `poweroff`, und das ist auf diesem Gerät kein Aus. Sauber
  wäre, den Ausschaltwunsch als Neustart mit Flagge zu fahren: GP5 (`0x07090114`) auf `0x47415445` „GATE" und `reboot`.
  Im Baum liegt dafür schon ein Muster - `reboot-mode { compatible = "nvmem-reboot-mode"; }` mit der nvmem-Zelle
  `reboot_mode_magic@1c` (= GP7) aus Patch `0029`. Eine zweite Zelle `@14` (GP5) plus `mode-gate = <0x47415445>` und
  `HandlePowerKey=reboot` … das ist ein eigener Auftrag: ob zwei `nvmem-reboot-mode`-Instanzen nebeneinander arbeiten,
  ist nicht geprüft, und `systemctl reboot gate` müsste den Modus mitgeben.
* **Ein Blick auf die Entprellung:** 50 ms sind der Stock-Wert aus `key_debounce`. `gpio_keys` setzt daraus
  `gpiod_set_debounce()` und fällt auf einen Software-Timer zurück, wenn die Hardware es nicht kann. Der sunxi-Treiber
  bietet kein `.pin_config_set` für `PIN_CONFIG_INPUT_DEBOUNCE`, es wird also der Timer sein - reicht, aber es erklärt,
  warum `PL_EINT_DEB (0x07022218)` ungenutzt bleibt (S35).
* **Wenn die Taste steht:** `hy310-tv` interessiert sich nicht für `KEY_POWER`; eine Prüfung, ob der Dienst
  Inhibitor-Sperren nimmt (dann bräuchte es `PowerKeyIgnoreInhibited=yes`), steht aus.
