# Plan 103 — Einschalt-Gate: Netz an = Bereitschaft, Taste = Start

**Status: Plan 08.09.2026 23:05; Messungen M1–M4, M6 am Gerät bestanden (23:20–00:20), M5 offen; Pakete G1–G3 können starten.** Auftrag Marco: für die Entwicklung bootet das Gerät weiter direkt am Netz; ein
auslieferbarer Stand braucht wieder das Stock-Verhalten (Netz an → Bereitschaft mit roter LED, Einschalttaste → Start, Ausschalten →
zurück in die Bereitschaft). Faktenbasis: Repo-Durchsuchung 08.09. 22:30–23:00 (Stock-U-Boot-Disassemblat, Stock-DTBs, ARISC-Strings,
unser U-Boot/TF-A/Kernel); alle Pfade unten sind belegt.

## 1. Wie der Stock es macht — und was das für uns heißt

| Frage | Befund | Beleg |
|---|---|---|
| Gibt es ein echtes Aus? | **Nein.** Kein PMIC, kein Power-Hold (`battery { enable = <0> }`), Regler sind PWM-/Fest-Regler. „Aus" ist immer ein Standby. | `re/vendor/HY310/extracted/dtb_extracted/hy310-board.dts:2676-2687` |
| Wer hält an? | **Nicht der U-Boot.** Stock-U-Boot bootet durch („Hit any key… 0", `Starting kernel` bei 4 s). Er setzt nur `BOOTMODE=standby` (aus `box_start_os0.start_type = 0`) und RTC-**GP2 := 2**; Android/Kernel legen sich danach schlafen. | `re/captures/HY310-DEV/boot.log:256-264`; `analyse/arisc/u_boot.bin` Funktionen `0x4a0070e8`/`0x4a0071c4`; `re/vendor/HY310/env_now.bin` |
| Was ist der Standby physisch? | **ARISC-Super-Standby mit DRAM-Selfrefresh** (`power_down = 0`, Strings `wait wakeup`, `power-up dram`, `Auto SR`). ARISC bleibt wach, LED rot PL0 = 1, blau PL1 = 0, hört Taste PL4 (Flanke, 50 ms Entprellung), CIR PL9 (19 IR-Power-Codes) und CEC. | `hy310-board.dts:2548-2612`; `analyse/arisc/scp-wordswapped.bin` Strings `0x14e98…0x14fea`; Dispatcher Port 3 `0x19 fake poweroff`, `0x25/0x26 wakeup src` (`doku/68` 1439–1450) |
| Die Taste | PL4 (R_PIO), `KEY_POWER` über `keyboard@2009800 power-gpio`, im Stock-Linux `sunxi_powerkey` Flanken-IRQ. | `hy310-board.dts:1904-1924`; `re/captures/HY310-DEV/stock_interrupts.txt:39` |

**Bei uns heute:** SPL → U-Boot (PREBOOT prüft nur GP7-Fastboot-Magic) → `board_late_init` schaltet **PB5 (Lüfter+Backlight) und PL3 (USB-VBUS)
bedingungslos ein** (`uboot-h713/0005-…`, `board/sunxi/board.c:994-1034`, `CONFIG_H713_POWERON_LIGHT_FAN` in allen sechs Defconfigs) → `bootcmd`
sofort. Kein `CONFIG_BUTTON`, kein `CONFIG_LED`. Im Kernel-DTS stehen `standby_param`/`cir_param`/`box_start_os0`/`prj{led0,led1}` wörtlich
(`sun50i-h713.dtsi:2229-2519`), aber **ohne Verbraucher**: kein `gpio-keys` für PL4, kein LED-Knoten, `adc_keys` und `board_mgr` auf unserem Board
abgeschaltet (`…-hy200-qz713df-a1.dts:39-40`). Die ARISC läuft erst unter Linux (Kernel-Treiber `0091`) und bekommt keinen DTB-Zeiger
(`arisc_para` genullt, `doku/82` 120–123). **`poweroff` ist wirkungslos:** TF-A `sunxi_power_down()` kehrt ohne PMIC sofort zurück, die Kerne
parken, die Platine bleibt bestromt (`plat/allwinner/sun50i_h616/sunxi_power.c:243-249`).

## 2. Zielbild und Entscheidung

Zwei Stufen, weil der Stock-Weg (Stufe 2) Unbekannte hat, die Stufe 1 nicht braucht:

**Stufe 1 — Gate im U-Boot (dieser Plan).** Am Netz startet der SoC, aber U-Boot schaltet **nichts** ein (kein Lüfter, kein Backlight, kein
USB-VBUS), setzt die rote LED und wartet auf die Taste. Erst danach `h713_poweron_lines()` und normaler Boot. „Ausschalten" aus Linux
(`poweroff`, Taste kurz) = zurück ins Gate. Verbrauch im Gate = SoC im Leerlauf (zu messen; Ziel < 1,5 W, Steckdose 192.168.8.179 kann Leistung
zeigen, sonst Messgerät). Kein IR-/CEC-Wecken in dieser Stufe (Option 1b unten).

**Stufe 2 — Stock-Standby über die ARISC (Folgeplan).** Linux bootet ins Standby (`box_start_os0`-Semantik), PSCI-Suspend in TF-A, ARISC
hält DRAM im Selfrefresh, weckt auf Taste/IR/CEC. Braucht: `arisc_para`-Layout (DTB-Zeiger, `analyse/arisc/BEFUND.md:137-160`), TF-A-Suspend
für H713, ARISC-Standby-Protokoll (Port 3). Ergebnis: Verbrauch im Bereich des Stock, IR-Wecken. Erst angehen, wenn Stufe 1 steht.

### 2.1 Flag-Protokoll (RTC-GP5, `0x07090114`; GP7 bleibt Fastboot, GP2/GP3/GP6 Stock-belegt)

| Wert | Bedeutung | Wer schreibt | Was U-Boot tut |
|---|---|---|---|
| `0` | Kaltstart (Netz kam) | RTC-Domäne ohne Batterie verliert den Inhalt — **zu verifizieren (M3)** | **Gate** |
| `0x52554E31` „RUN1" | läuft / warmer Neustart | U-Boot unmittelbar vor `bootm`; bleibt über `reboot`, Watchdog, Absturz erhalten | direkt booten |
| `0x47415445` „GATE" | Ausschaltwunsch | TF-A in `sunxi_power_down()` (PSCI `SYSTEM_OFF` ← Linux `poweroff`), danach `SYSTEM_RESET` | **Gate** |

Damit: Netz an → Gate; Taste → Boot; `reboot` → sofort wieder da (Entwicklung, Updates); `poweroff`/Taste in Linux → Gate; Absturz → direkt (kein
totes Gerät im Feld, weil RUN1 steht). **Schalter:** `CONFIG_H713_POWER_GATE` (aus in `hy310_netboot_defconfig` und `hy310_host_defconfig`,
an in `hy310_qz713_v3_1_defconfig`) **plus** Env `h713_gate=0|1` als Übersteuerung ohne Neubau; im Gate hebt eine gehaltene Taste beim
Netz-Einschalten (≥ 3 s) das Gate für diesen Boot auf (Service-Hintertür, Log-Zeile).

### 2.2 Gate-Schleife im U-Boot

- Ort: **vor** `h713_poweron_lines()`, also in `board_late_init` an dessen Stelle — dort ist die GPIO-Uclass da (`board.c:979-982` erklärt,
  warum nicht früher). Bis dahin sind PB5/PL3 auf Reset-Pegel (LOW, `doku/10` 153–161: nie von selbst HIGH) — das Gerät ist bis zum Gate dunkel
  und leise. Falls sich zeigt, dass PB5 vor `board_late_init` doch hochkommt: direkter R_PIO-/PIO-Registerzugriff in `board_init`.
- Schleife: LED rot an (PL0 = 1, blau PL1 = 0 — Polarität **M2**), `PL4` entprellt pollen (50 ms wie Stock), CPU in `udelay`/WFI; bei Tastendruck:
  LED blau, GP5 := RUN1, `h713_poweron_lines()`, weiter. Kein Timeout. UART bleibt nutzbar (Konsole meldet `gate: waiting for power key`).
- Umsetzung mit der Button-Uclass (`drivers/button/button-gpio.c`, `CONFIG_BUTTON_GPIO`, DT-Knoten `gpio-keys` mit PL4 im U-Boot-DTS) und
  `CONFIG_LED_GPIO` (PL0/PL1) — oder, falls die Uclass-Reihenfolge stört, `dm_gpio_lookup_name("PL4")` wie in `board.c:1010-1024`.
- **Option 1b (später, optional):** IR-Wecken im Gate durch Pollen des CIR-RX-FIFO (`r_ir@7040000`, PL9, NEC-Adresse/Code aus `cir_param`);
  kein U-Boot-Treiber vorhanden, ~150 Zeilen. CEC: nicht in Stufe 1.

### 2.3 TF-A: `poweroff` → Gate

`plat/allwinner/sun50i_h713/sunxi_power.c` (heute `#include` des H616-Codes): eigene `sunxi_power_down()` — GP5 := GATE, dann
`sunxi_system_reset()`. Reset ohne Flag (PSCI `SYSTEM_RESET` = `reboot`) bleibt unverändert. ~20 Zeilen, Bau über den Container (doku/50).

### 2.4 Kernel und Userspace

- DTS: `gpio-keys` mit PL4 → `KEY_POWER`, `debounce-interval = <50>`, `wakeup-source`; `leds { red: PL0, blue: PL1 }` (Polarität nach M2),
  Trigger: blau = `default-on` (läuft), rot aus. Beide als Patch `0139…` in `mainline/patches/kernel/`.
- systemd: `HandlePowerKey=poweroff` (Vorgabe) → kurzer Druck = `poweroff` = Gate. `hy310-tv` braucht nichts Neues (Dienst endet mit dem System).
- Lampe/Lüfter: heute durch U-Boot gesetzt und nie wieder angefasst; beim Übergang ins Gate genügt der Reset (PB5/PL3 fallen auf LOW).

## 3. Messungen zuerst (M1–M6, je 10 Minuten, am Gerät, U-Boot-Prompt über UART — **UART braucht Marco**)

| Nr. | Frage | Wie | Entscheidet |
|---|---|---|---|
| M1 | Pegel/Typ von PL4 | `gpio status PL4` in Ruhe und gedrückt; Pull-up nötig? (Stock: kein Bias) | Polling-Bedingung, Pinconf |
| M2 | Sind PL0/PL1 die LEDs, welche Polarität? | `gpio set/clear PL0`, `PL1`, hinsehen (`doku/10:161` behauptet „Rails", Vendor-DT sagt LED) | LED-Knoten |
| M3 | Verliert GP5 bei Netz-aus den Inhalt, überlebt es SPL/Reset? | `mw.l 0x07090114 0x52554E31`, `reset` → `md.l`; dann Steckdose aus/an → `md.l` | Flag-Protokoll |
| M4 | Wann kommen PB5/PL3 heute hoch? | UART-Zeitstempel von `board_late_init` gegen Lüftergeräusch/Backlight; ggf. `gpio status PB5` in `board_init` | Ort des Gates |
| M5 | Verbrauch im Leerlauf des U-Boot-Prompts | Steckdose/Messgerät, 2 min am Prompt ohne Lüfter (PB5 vorher `gpio clear`) | Ob Stufe 1 als Bereitschaft taugt |
| M6 | Verhält sich `reboot` aus Linux wie erwartet (PSCI-Reset, GP-Erhalt)? | GP5 setzen, `reboot`, im U-Boot lesen | RUN1-Pfad |

**Ergebnisse (08.09. 23:20–23:55, U-Boot-Prompt über den ESP32-S2-UART, Werkzeuge `tools/uart-uboot.py run`, neu `tools/uart-reset-catch.py`):**

| Nr. | Ergebnis |
|---|---|
| M1 | **PL4 aktiv-low mit externem Pull-up:** als Eingang 1 in Ruhe, 0 bei gedrückter Taste (24 Proben, `R_PIO DAT` 0x5a ↔ 0x4a), interner Pull nicht nötig. Nach Reset steht PL4 auf „func" (unkonfiguriert). Registerlayout R_PIO ist das neue (DRV0/1 bei 0x14/0x18 mit 4-Bit-Feldern, `0x11111111`); PULL liegt damit bei 0x24, nicht 0x1C. |
| M2 | **Die LED folgt PB5, nicht PL0/PL1:** PB5 = 1 → blau, PB5 = 0 → rot (zweimal hin und zurück, Marco). Alle vier PL0/PL1-Kombinationen ohne jede Wirkung; PL0/PL1 bleiben nach Kaltstart „func". Die rote Bereitschaftsanzeige entsteht also von selbst, solange das Gate PB5 unten lässt. (Ob die ARISC im Stock PL0/PL1 treibt, klärt S35 — für Stufe 1 unerheblich.) |
| M3 | **Flag-Protokoll trägt:** GP0–GP7 nach Kaltstart alle 0; `mw.l 0x07090114 0x52554E31` → überlebt `reset` (warm, U-Boot liest RUN1 zurück); nach Netz-aus/an per Steckdose wieder 0. GP5 ist frei. |
| M4 | Am U-Boot-Prompt sind PB5 (`fan-bl-power`) und PL3 (`usb-vbus-power`) bereits 1 — `board_late_init` läuft vor dem Prompt; nach dem Kaltstart ist das Gerät bis dahin dunkel/leise (Lüfter setzt erst mit U-Boot ein). PL6 steht nach Kaltstart schon als Ausgang auf 1 (Kernspannungen, gesetzt vor U-Boot — SPL/TF-A oder Hardware-Default). `gpio clear PB5` schaltet Lüfter und Licht sofort ab. |
| M5 | **Bereitschaft (Gate, Kaltstart, rote LED): 4 W**; **Betrieb mit MIPS, HDMI-Bild 1080p und Lüfter: 47 W**; **Bereitschaft nach `poweroff`: wieder 4 W** (Marco, Steckdosen-Messgerät, 09.09. 22:25–22:45). M5 abgeschlossen; Stufe 2 muss die 4 W deutlich unterbieten (Stock-Standby vermutlich < 1 W). Stufe 2 (ARISC-Super-Standby) müsste deutlich darunter liegen — der Wert ist die Messlatte. |
| M6 | **bestanden:** RUN1 aus Linux nach GP5 geschrieben (`/dev/mem`, nur Messung), `reboot` → U-Boot liest RUN1 zurück; GP3 trägt nach dem Linux-Lauf 0xb00f — laut S39 eine Fortschrittsmarke der ARISC („Hauptschleife läuft“), kein Vorparameter; GP7 0. Der RUN1-Pfad (warmer Neustart ohne Taste) funktioniert also über PSCI-Reset. Prompt-Fang nach `reboot`: 11 s. |

Offen und **nicht** für Stufe 1 nötig: wer im Stock `BOOTMODE=standby`/GP2 auswertet (Stock-vmlinux `sunxi_standby_*`), `arisc_para`-Layout,
ob der Stock am Netz bis Android durchbootet (UART-Mitschnitt ohne Tastendruck, 120 s).

## 4. Pakete

| Paket | Inhalt | Wer | Liefert |
|---|---|---|---|
| G0 | Messungen M1–M6 | Hauptsitzung + Marco (UART) | Tabelle in diesem Plan |
| G1 | U-Boot: `CONFIG_H713_POWER_GATE`, Env `h713_gate`, GP5-Protokoll, LED/Taste, Gate-Schleife, Service-Hintertür, Defconfigs | Agent in Kopie `analyse/boot/arbeit/g1-uboot/` | Patch `uboot-h713/0013…`, Bericht S35 |
| G2 | TF-A: `sunxi_power_down()` → GATE + Reset | Agent, Kopie `g2-tfa/` | Patch, Bericht S36 |
| G3 | Kernel-DTS `gpio-keys`/`leds`, logind-Vorgabe prüfen | Agent, Kopie `g3-kernel/` | Patch `0139`, Bericht S37 |
| G4 | Bau (Container, doku/50), **Flashen von SPL/U-Boot/TF-A** — Rückweg nach doku/20 (USB-Stick, Zweitkopie LBA 256, 300-MB-Dump) | Hauptsitzung, Marco am UART | — |
| G5 | Abnahme §5 | Hauptsitzung | Protokoll |
| G6 | Doku: 30-uboot-aenderungen, 20-flashen, 00-STATUS, Handoff | Hauptsitzung | — |

Regeln wie in Plan 101 §4: Agenten schreiben nur in ihre Kopien, fassen weder Board noch `mainline/`/`uboot-h713/` an, liefern Patches.

## 5. Abnahme

1. Netz an (Steckdose): dunkel, leise, rote LED; UART meldet das Gate; 5 min so — Verbrauch protokolliert.
2. Taste: blau, Lüfter/Backlight an, Boot bis `hy310-tv` mit Bild, Zeit ab Tastendruck.
3. `reboot` aus Linux: kommt ohne Taste wieder (RUN1). Erzwungener Absturz (`echo c > /proc/sysrq-trigger`, Watchdog aus): kommt ohne Taste wieder.
4. `poweroff` aus Linux und kurzer Tastendruck unter Linux: Gate, rote LED, Lüfter aus; Taste → wieder da.
5. 20 Zyklen Netz aus/an mit Taste, 20 Zyklen `poweroff`/Taste: 40/40 ohne Handgriff am UART.
6. Entwicklungsbild (`hy310_netboot_defconfig`) und `h713_gate=0`: Verhalten wie heute, direkt am Netz.
7. Service-Hintertür: Taste ≥ 3 s beim Netz-Einschalten → direkt.

### 5.1 Stand der Abnahme (09.09. 21:05, U-Boot proper v2 = Gate + BL31-GATE; Zielkernel bad2f16b = Serie 112 ohne Debug, installiert)

| Punkt | Ergebnis |
|---|---|
| 1 Netz an → Bereitschaft | ✅ 21:00: aus dem Gate Steckdose aus/an → „gate: cold start (GP5 00000000)“ → „waiting for power key“ (dunkel, rot); Druck → „power key, booting“ → Linux, Dienste an |
| 2 Taste → Start | ✅ 20:50: „gate: waiting for power key" → Druck → „gate: power key, booting" → Linux, Dienste an (Marco: LED rot im Gate) |
| 3 `reboot` ohne Taste | ✅ `reset`/`reboot` mit RUN1 → „gate: warm start, booting" (20:42), M6 |
| 4 `poweroff` → Bereitschaft | ✅ 20:48 per Befehl; ✅ 21:17 **per Taste unter Linux:** KEY_POWER 1/0 → logind → systemd-Shutdown → „Power down" nach 2,5 s → BL31 GATE → „gate: power-off requested" → „waiting for power key" (dunkel, rot, kein ssh) |
| 5 Zyklen 20×/20× | vertagt (Marco); heute 6 Gate-Durchläufe fehlerfrei (poweroff ×4, Kaltstart ×1, Taste unter Linux ×1) |
| 6 Entwicklungsbild / `h713_gate=0` | ✅ Env 0: „gate: off (h713_gate=0)", direkter Boot am Netz (Kaltstart-Konsole 18:06) |
| 7 Service-Hintertür (Taste ≥ 3 s beim Netz-Einschalten) | gestrichen (Marco 09.09. 21:45): bringt dem Nutzer nichts, da ein Druck im Gate ohnehin startet; Code bleibt harmlos drin, später ggf. als Recovery-/Fastboot-Einstieg umdeuten |
| 8 HDMI nach der Bereitschaft (MIPS-Neuladung) | ✅ 21:55: vor `poweroff` Bild + Ton 48 kHz; nach Gate → Taste → Boot: Signal 1080p, Plane an, Foto zeigt den Laptop-Sperrbildschirm, Prüfton über PipeWire → DSP-Pegel 1222, 0 Timeouts. In Stufe 1 ist Schlafen ein voller Reset, U-Boot lädt die MIPS neu wie beim Kaltstart |

## 6. Risiken

- **Flash-Risiko:** SPL/U-Boot/TF-A neu flashen; ein fehlerhaftes Gate kann ein Gerät ohne UART unbedienbar machen → erst als **U-Boot-Test per
  TFTP/USB-Stick laden** (kein Flash), dann flashen; Zweitkopie und Dump bleiben (doku/20).
- **Netz-aus bei laufendem Gate ist immer erlaubt** (nichts schreibt), aber ein Netz-aus während Linux ist wie heute ein harter Schnitt (NFS-Root).
- Wenn M3 zeigt, dass GP-Register den Netz-aus überleben, braucht der Kaltstart ein anderes Kennzeichen (z. B. Watchdog-/Reset-Ursache-Register
  oder ein SPL-Zähler) — der Plan ändert dann nur die Spalte „Kaltstart".
- Verbrauch im Gate (M5) ist der Preis von Stufe 1; wenn zu hoch, CPU-Takt im Gate senken (PLL auf 24 MHz) oder Stufe 2 vorziehen.

## 7. Verlauf

- **08.09. 23:20–00:20:** Messungen M1–M4, M6 bestanden (Tabelle §3); M5 offen. Neues Werkzeug `tools/uart-reset-catch.py` (Reset/Reboot
  auslösen, Autoboot fangen, Befehle absetzen). Befund LED = PB5 macht einen LED-Baustein überflüssig.
- **00:30:** Pakete G1 (U-Boot-Gate), G2 (TF-A `poweroff` → GATE), G3 (Kernel `gpio-keys` PL4) an Opus-Agenten übergeben; Regeln und Aufträge in
  `analyse/boot/arbeit/{REGELN.md,g1-uboot,g2-tfa,g3-kernel}/`, Berichte S36–S38. Parallel RE-Auftrag S35 (ARISC: LED/Taste/Standby-Ablauf) für Stufe 2.
- **00:40–01:20:** G1 (S36), G2 (S37), G3 (S38) und S35 (ARISC-RE) geliefert. G1 als `uboot-h713/0018-sunxi-h713-power-gate.patch` in
  `mainline/external/u-boot` eingespielt; neue Test-Defconfig `hy310_netboot_gate_defconfig` (Netboot + Gate). G2 in
  `mainline/external/arm-trusted-firmware` eingespielt (dort werden Änderungen als Commits geführt). G3 als Kernel-Patch `0139` + Defconfig
  `CONFIG_KEYBOARD_GPIO=y` (Serie 111, Snapshot `20260909-0100-serie111-powerkey`), Baum `4571c431`, installiert (FIT + Module).
- **01:25 Flash 1:** U-Boot proper (`flash-netboot-gate/uboot-proper.bin`, sha256 `f890f4a1…`, 1731 Sektoren) per `tftpboot 192.168.8.104:…`
  + `mmc write 0x49ac00 0x6c3` am Prompt, Rücklesen identisch; Sicherung des alten Stands `flash-netboot-gate/emmc-proper-vorher.bin`
  (= `smmheap/uboot-proper.bin`). Falle 1: `dhcp` setzt `serverip` auf den Router — Server immer explizit angeben. Erststart: neues U-Boot,
  `gate: off (h713_gate=0)`, Autoboot wie gehabt. **Falle 2:** die FIT enthielt noch das alte BL31 (Banner „Aug 31") — ein zweiter
  `uboot-build.sh` im selben Ausgabeverzeichnis packt die FIT nicht neu, wenn sich nur `bl31.bin` geändert hat → immer frisches
  Verzeichnis (oder FIT löschen) nach einem BL31-Bau. Zweiter Flash mit neuem BL31 folgt.
- **01:35 Flash 2** (`flash-netboot-gate/uboot-proper-v2.bin`, CRC e9e25b3e, mit neuem BL31 — FIT enthält jetzt die PSCI-Gate-Meldungen; der
  BL31-„Built"-Stempel bleibt „Aug 31", weil TF-A nur die geänderte Datei neu übersetzt): geschrieben, zurückgelesen, Neustart sauber,
  `gate: off (h713_gate=0)`, Linux bootet. **Gerätezustand beim Abschalten (Marco, 01:50): Env `h713_gate=0` gespeichert → das Gerät bootet am
  Netz weiterhin direkt, wie bisher.** `poweroff` aus Linux führt mit dem neuen BL31 zu GATE-Flag + Reset, wegen Env 0 also zu einem Neustart
  (noch nicht beobachtet).
- **Kernel 4571c431 (Serie 111) läuft:** `gpio-keys` als event1 mit KEY_POWER, IRQ 265 `sunxi_pio_edge 4 Edge power` registriert, EINT-CFG0
  0x00040000 (PL4, beide Flanken), CTL Bit 4. **Offen/Verdacht:** zwei Tastentests (mit `systemd-inhibit` blockiert) ergaben 0 Ereignisse und
  IRQ-Zähler 0, EINT-STATUS 0 — unklar, ob gedrückt wurde (erster Mitschnitt hatte die falsche GPIO-Zeile erwischt, zweiter wurde vom
  Schlafengehen unterbrochen). Registerbild: PL4 steht unter Linux auf **Mux 0**, der Treiber deklariert den Interrupt als Fn 6, die ARISC
  nutzt Fn 14 (S35). Nächster Schritt: Mitschnitt `gpio-4`-Zeile + IRQ-Zähler bei sicherem Tastendruck; falls Pegel wechselt, aber kein IRQ:
  Mux-Diagnose 6/14 per Register, dann Pinctrl-Patch (`pinctrl-sun50i-h713-r.c`, IRQ-Funktion) — siehe S38 §7 Annahme 2.
- **Noch nicht getan:** Stufe 2 (`setenv h713_gate 1; saveenv; reset` → Gate scharf, Taste startet), `poweroff`-Test mit Fänger, Abnahme §5,
  Commit der TF-A-Änderung im Submodul, Doku 30/20/00-STATUS, Kernel-GUT-Markierung für 4571c431 nach Abnahme.
- **09.09. 09:xx Aufräumen:** TF-A-Änderung als Commit `3b3fb35fa` im Submodul; U-Boot-Gate als Commit `1cd5e6d6beb` im Submodul und
  `uboot-h713/0018-sunxi-h713-add-the-power-gate-…patch` (git-am-Format, ersetzt den Roh-Diff). **Todo U-Boot-Baum:** `h713_mips.c` trägt 162
  unkommittierte Zeilen, Patch 0017 deckt 54 (das ist der seit 07.09. geflashte Stand) — sichten und als Commit(s) nachziehen; Branch heißt
  `h713-display`, README nennt `h713-display-hy310`.
- **09.09. 18:05–20:05 Tastentest unter Linux (Kernel 4571c431, Gate aus):** Kaltstart-Konsole zeigt `gate: off (h713_gate=0)`. Mit
  `analyse/boot/tastentest.sh` (Ausschalten per `systemd-inhibit` blockiert): Pegel `gpio-4` geht beim Drücken auf lo, **aber kein Interrupt,
  kein Ereignis** — PL4 steht auf Mux 0. Ursache in der Serie: Patch `0004` lässt den IRQ-Mux-Wechsel weg („H713 erkennt Flanken im GPIO-Modus"),
  und die Tabellen (`0002`/`0003`, vom H616) führen EINT als 0x6; der H713 hat wie der D1 das neue Registerlayout und **EINT = 0xe** (ARISC: 14).
  Diagnose per `/dev/mem` (nur Messung): PL4-Mux auf 0xe → jeder Druck zählt 2 Flanken am IRQ 265. → Patch `0140` (0x6 → 0xe in beiden Tabellen,
  Mux-Wechsel beim IRQ-Anfordern wieder wie upstream), gebaut (Serie 112, Snapshot `20260909-1810-serie112-eint`). Einziger GPIO-IRQ-Nutzer am
  Gerät ist die Taste (`/proc/interrupts`).
  **Zweites Problem:** auch mit zündendem IRQ liefert `gpio-keys` **kein Tastenereignis** (zwei Rohleser auf event1 leer, `EVIOCGKEY` nie gedrückt,
  `keys=116`, nicht disabled, kein Grabber, `inhibited=0`, keine dmesg-Fehler). Kein tracefs im Netboot-Kernel → temporärer Debug-Patch `0141`
  (dev_info in ISR und Meldepfad), Bau 113 läuft; danach Neustart und Tastentest mit `dmesg`.
- **20:35 G3 bestanden (Kernel `8a75131e`, Serie 113 = 112 + Debug-Patch 0141):** Kernel setzt PL4 selbst auf Mux e; Tastentest: 3 Drücke →
  6 Ereignisse (KEY_POWER 1/0), dmesg-Debug zeigt ISR → Report 50 ms später mit korrektem Zustand. Der Pinctrl-Fix `0140` ist damit belegt.
  Randnotiz: Beim Mux-Hack per `/dev/mem` (19:42–20:00) kamen trotz zündendem IRQ keine Ereignisse — nicht weiter untersucht, da der
  reguläre Weg funktioniert. `0141` ist temporär und wird vor dem GUT-Stand aus der Serie genommen (Serie 112 = Zielstand).
- **20:40 `poweroff`-Test (Env noch 0):** Linux „reboot: Power down" → BL31-Banner → U-Boot `gate: off (h713_gate=0)` → Neustart. Der Reset
  kann nur aus unserer `sunxi_power_down()` kommen (die alte parkt die Kerne, kein Banner). Die BL31-`NOTICE` erscheint nicht auf der Konsole —
  Laufzeit-Konsole von BL31 nach dem Boot aus; unkritisch. Verbesserung für G1 (Todo): den GP5-Wert in den `gate:`-Meldungen mit ausgeben.
- **21:00–21:20 Stufe 2 scharf (`h713_gate=1` gespeichert):** `reset` → „warm start, booting" (RUN1, korrekt); `poweroff` → „power-off requested" →
  Gate → Taste → Boot; Steckdose aus/an aus dem Gate → „cold start (GP5 00000000)" → Gate → Taste → Boot; **Taste unter Linux** → Shutdown →
  Gate. Zielkernel `bad2f16b` (Serie 112 = 0139 + 0140, ohne Debug 0141) installiert, Erstboot steht mit dem nächsten Tastendruck an.
  Werkzeuge: `tools/uart-passiv.py` (fortlaufender Mitschnitt), `analyse/boot/tastentest.sh`. Falle: `pkill -f` mit Muster in der eigenen
  Befehlszeile tötet die eigene Shell (zweimal passiert) — nur PIDs oder `c[a]tch`-Muster.
  **Offen für heute:** Service-Hintertür (Taste ≥ 3 s beim Netz-Einschalten), 20/20 Zyklen (bisher 4 Gate-Durchläufe fehlerfrei), M5 Verbrauch
  (kein Messgerät), GP5-Wert in allen `gate:`-Meldungen, GUT-Markierung nach Erstboot von `bad2f16b`, Doku 30/20/00-STATUS,
  Entscheidung mit Marco: bleibt `h713_gate=1` am Entwicklungsgerät oder zurück auf 0.
- **21:45–21:55 Entscheidungen Marco:** Gate bleibt am Entwicklungsgerät **an** (`h713_gate=1`); Hintertür-Test gestrichen; Zyklen später.
  HDMI nach Bereitschaft geprüft (Tabelle Punkt 8): Bild und Ton kommen zurück. Zu Stufe 2 (ARISC-Standby mit gehaltenem DRAM) gilt Marcos
  Hinweis: dort muss das Zusammenspiel mit der MIPS eigens betrachtet werden — in Stufe 1 entfällt das durch den Reset.
  Fallen des Tages: `/tmp` am Zuspieler ist nach dessen Neustart leer (Prüfton neu erzeugen); direktes `aplay -D hw:0,3` scheitert still,
  solange PipeWire die HDMI-Senke hält → `paplay` nehmen.
- **09.09. 22:25–22:35:** M5 Bereitschaft = **4 W** (Marco, Steckdosen-Messgerät). U-Boot-Submodul aufgeräumt: `h713_mips.c` in zwei Commits
  (`9dc3e437a26` = Patch 0017 SMM-Heap, `f24feb87c82` = 0019 `elog=N`-Option für `h713_disp init`), Gate = `1cd5e6d6beb` (0018); `uboot-h713/`
  0017–0019 per `git format-patch`, Arbeitsbaum sauber, Branch `h713-display`.
- **22:50:** GP5-Wert in allen `gate:`-Meldungen (`10d8811aa55`, `uboot-h713/0020`), noch nicht geflasht — kommt mit dem nächsten U-Boot-Flash.
  Stufe 2 vorbereitet: RE-Auftrag S39 (Stock-Standby-Ablauf Kernel → BL31 → ARISC, `arisc_para`, Weckquellen, DRAM-Selfrefresh, Lücken in
  unserem Stapel) läuft; daraus entsteht Plan 104.
