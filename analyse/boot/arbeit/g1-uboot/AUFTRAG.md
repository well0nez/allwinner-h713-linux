# G1 — U-Boot: Einschalt-Gate (Plan 103 §2.1/§2.2), Bericht S36

Lies zuerst `../REGELN.md` und `doku/103-plan-einschaltgate.md`. Original nur lesen: `mainline/external/u-boot` (HEAD cbcbf10af04, mit unseren
Patches `uboot-h713/0001…0012`). Kopien der zu ändernden Dateien liegen in `kopie/` (board/sunxi/board.c, arch/arm/mach-sunxi/Kconfig,
configs/hy310_*_defconfig, dts/sun50i-h713-hy200-qz713df-a1.dts, include/configs/sunxi-common.h). Weitere Dateien bei Bedarf selbst
aus dem Original nach `kopie/` kopieren (gleiche relative Pfade).

## Zu liefern
1. `CONFIG_H713_POWER_GATE` (bool, mach-sunxi/Kconfig, abhängig von `H713_POWERON_LIGHT_FAN`), **aus** in `hy310_netboot_defconfig` und
   `hy310_host_defconfig`, **an** in `hy310_qz713_v3_1_defconfig` (und der vierten Defconfig sinngemäß — begründen).
2. In `board_late_init`, **vor** `h713_poweron_lines()`: `h713_power_gate()`:
   - Env `h713_gate` lesen: `0` → Gate übersprungen (Log-Zeile), `1`/fehlend → Gate nach Kconfig.
   - GP5 lesen (`readl(0x07090114)`): `RUN1` → kein Gate (Log „gate: warm start, booting"), sonst (0 oder `GATE`) → Gate.
   - Service-Hintertür: ist PL4 beim Eintritt bereits gedrückt und bleibt es ≥ 3 s → Gate aufheben (Log „gate: key held at power-on, bypass").
   - Gate-Schleife: PL4 als Eingang (DM-GPIO, Name "PL4"), alle 10 ms lesen, 50 ms entprellt; **Tastendruck = fallende Flanke mit ≥ 50 ms low, Freigabe
     erst beim Loslassen** (sonst startet ein Halten sofort den Boot). Kein Timeout. Konsole meldet einmal `gate: waiting for power key` und alle 60 s
     einen Punkt (kein Spam). Während der Schleife `WATCHDOG_RESET()`/`schedule()` wie in U-Boot üblich.
   - Danach: `writel(RUN1, GP5)`, Log „gate: power key, booting", dann `h713_poweron_lines()` wie bisher.
   - Wenn kein Gate: trotzdem `writel(RUN1, GP5)` **unmittelbar vor `h713_poweron_lines()`** — damit `reboot`/Absturz danach nie im Gate landen.
     Achtung: Beim Kaltstart mit `h713_gate=0` oder Netboot-Defconfig soll das Gerät wie heute direkt booten.
3. Prüfe, ob GP5 vor dem Kernelstart noch von etwas anderem überschrieben wird (PREBOOT nutzt GP7). Falls der Kernel-Treiber `0029` (Fastboot-GP7) ein
   Muster hat, wie GP-Register gelöscht werden, dokumentiere es — GP5 darf **nicht** gelöscht werden.
4. Wenn `CONFIG_BUTTON`/`button-gpio` einfacher ist als rohes DM-GPIO: erlaubt, aber dann DT-Knoten im Board-DTS ergänzen und begründen. Rohes
   `dm_gpio_lookup_name("PL4")` + `dm_gpio_request/set_dir_flags(GPIOD_IS_IN)/dm_gpio_get_value` ist die Vorgabe (kein Pull nötig).
5. Kein LED-Code (LED folgt PB5).
6. Patch `patches/0013-sunxi-h713-power-gate.patch` (gegen Originalpfade), Bericht `doku/nachtlog/S36-uboot-power-gate.md`: Ablauf, Register,
   Testrezept für die Hauptsitzung (U-Boot zuerst per TFTP/`loady` laden, **nicht** flashen), Risiken, offene Annahmen.
