# Unsere U-Boot-Änderungen

Alle im Submodul-Checkout `mainline/external/u-boot`. Weil dort nichts
committet ist und `git submodule update` alles wegwerfen würde, liegt eine
Kopie in `uboot-h713/` - Patch plus die neuen Dateien.

Sechs davon sind als [PR #1](https://github.com/cstenger/u-boot/pull/1)
eingereicht, die Display-Änderungen noch nicht.

## Der rote Faden

Jede einzelne dieser Änderungen hat dieselbe Ursache: eine Eigenschaft, die
zum **Board** oder zur **Firmware-Revision** gehört, steht als feste Konstante
im Code. Ein anderes Board fällt dann nacheinander über jede einzeln, jedes
Mal mit eigener Meldung und eigenem nötigen Eingriff.

## 1 - CCU: eigene Tabellen statt D1

`drivers/clk/sunxi/clk_h713.c` (neu), Makefile, `clk_sunxi.c`

Der H713 benutzte `d1_ccu_desc`. Für die Blöcke, die sein Kommentar als
verifiziert nennt, stimmt das - MMC `0x84c`/`0x830`, UART `0x90c`, USB-Bus-Gates
`0xa8c`. Für die **portabhängigen** USB-Register nicht: die liegen auf dem
H713 8 Byte auseinander, auf dem D1 4. Port 1 ist `0xa78`, nicht `0xa74`.

Mit dem D1-Wert bekommt OHCI1 nie seinen Takt, und der erste Registerzugriff
im Probe hängt das Board hart - drei Controller melden sich, dann Stillstand.

Belegt bei `0x4a045e12` im Vendor-U-Boot: `cmp r0, #1`, dann
`ldr r2, =0x02001a78`. Deckt sich mit dem eigenen Kernel-CCU (Patch 0001).

## 2 - PHY: H713-Unterstützung

`drivers/phy/allwinner/phy-sun4i-usb.c`

Der Treiber kannte H713 überhaupt nicht. Zwei Eigenheiten:

**`pmu_enable_bit0`** - BIT(0) an der PMU-Basis muss gesetzt werden, sonst
bleibt die PHY aus. Aus dem eigenen Kernel-Patch 0005 übernommen.

**`hci_phy_ctl_clear = PHY_CTL_SIDDQ`** - die HCI-PHYs starten im Power-Down.
Der Kernel darf das weglassen, weil dort das Vendor-U-Boot vorlief und es
schon gelöscht hatte; die eigene `usb.md` sagt es ausdrücklich: *„the kernel
doesn't re-init from scratch"*. Sobald U-Boot selbst die erste Stufe ist,
gibt es diesen Vorgänger nicht mehr. Der Vendor macht `bic r3, r3, #8` bei
`0x4a045ee8`.

`num_phys = 2` statt 3, weil der H713-CCU in U-Boot nur bis Port 1 reicht.

## 3 - R_PIO in den Devicetree

`dts/upstream/src/arm64/allwinner/sun50i-h713-hy200-qz713df-a1.dts`

Es gab nur `pinctrl@2000000`, also die Bänke PA bis PI. Die PL-Bank im
Always-on-Block hatte keinen Treiber, jedes `gpio_request()` darauf scheiterte
mit `-ENOENT`. Betrifft PL3, die Versorgung der USB-Buchse.

`allwinner,sun50i-h713-r-pinctrl` war im Treiber schon vorhanden und
`CONFIG_PINCTRL_SUN50I_H713_R` ist per Default an - nur der Knoten fehlte.

## 4 - USB-Host-Controller in den Devicetree

Dieselbe DTS. `CONFIG_USB_EHCI_HCD`, `USB_OHCI_HCD` und `USB_HOST` waren
gesetzt, aber es gab keine EHCI- oder OHCI-Knoten - nur die musb. `usb start`
meldete `No USB controllers found`.

Ports 0 und 1 ergänzt, jeweils EHCI und OHCI, Knotendefinitionen aus der
eigenen Board-DTS. Port 2 fehlt noch, dafür braucht der CCU erst seine
Takt-IDs.

## 5 - GPIO in `board_late_init`, über Namen

`board/sunxi/board.c`

Zwei Fehler auf einmal. In `board_init` steht die GPIO-Uclass noch nicht,
`gpio_request()` scheitert - und die Rückgabewerte wurden verworfen, also sagte
nichts etwas. Der Lüfter lief nie an.

Und die lineare Legacy-Nummerierung passt nicht zu den aus dem DT
registrierten Bänken: `SUNXI_GPB(5)` traf einen anderen Pin - der Aufruf gelang
und der Lüfter blieb trotzdem aus - `SUNXI_GPL(3)` löste gar nicht auf.
`dm_gpio_lookup_name()` ist der Weg, den `gpio set PB5` an der Konsole nimmt,
und der funktionierte immer.

PL3 zusätzlich zu PB5, und Fehler werden jetzt mit Pin-Namen gemeldet.

## 6 - Defconfigs

```
hy310_qz713_v3_1_defconfig   wie sein Bench-Config, nur CONFIG_DRAM_CLK=792.
                             MUSB drin, also ums und Fastboot nutzbar
hy310_host_defconfig         ohne MUSB. Nur so ist die USB-A-Buchse ein Host
hy310_felmmc_defconfig       Restore-SPL für FEL, mit eingebettetem Payload.
                             Bleibt lokal, enthält unser boot0
```

Zwei Varianten, weil die PHY-Weiche **compile-time** ist:

```c
#ifdef CONFIG_USB_MUSB_SUNXI
	sun4i_usb_phy0_reroute(data, true);   /* PHY0 ans Gadget */
#else
	sun4i_usb_phy0_reroute(data, false);  /* PHY0 an den Host */
#endif
```

Host und Gadget schließen sich auf diesem Board also aus.

## 7 - Display: Firmware-Revision als Tabelle

`arch/arm/mach-sunxi/h713_mips.c`, noch nicht eingereicht

Drei Konstanten hingen an der Firmware-Revision und lagen einzeln herum:
erwartete Größe, gepinnte SHA-256, HDCP-Patch-Adresse. Jetzt eine Zeile pro
Revision:

```c
struct h713_mips_fw_rev {
	const char *board;
	ulong size;
	ulong hdcp_wait_va;
	u8 digest[SHA256_SUM_LEN];
};
```

Die Größe wird zusätzlich zur Laufzeit aus der Datei genommen, nicht nur
geprüft - `h713_mips_clear_workspace()` löscht ab dem Ende der Firmware, und
mit einem zu kleinen Wert putzt es die letzten Bytes des Images weg.

## 8 - Display: zweite Schreibstelle absichern

Dieselbe Datei. Bei `0x4b101168` schrieb er ungeprüft eine Instruktion in die
Firmware. Auf unserem Image stehen dort Nullen. An der anderen Stelle prüft er
ausdrücklich vorher, „so a wrong offset reports rather than corrupting the
firmware" - hier fehlte genau das.

## 9 - Display: Wiederlauf-Sperre in `init`

`h713_panel_test_ran` wird von `panel-test` und `auto` gesetzt, von
`init_only` nicht. `init` lässt die Firmware aber laufen. Ein anschließendes
`auto` sieht die Sperre offen, überspringt den Teardown und lädt `display.bin`
über eine **laufende** MIPS - die schreibt weiter hinein, und die Prüfsumme
läuft über ein Image, das sich unter ihr verändert. Das Ergebnis passt dann zu
keinem Build.

## 10 - Display: eine Board-Tabelle, unser 1080p-Panel

`arch/arm/mach-sunxi/h713_mips.c`, gesichert als
`uboot-h713/0002-h713-display-board-separation.patch`. Nicht eingereicht.

Sein Baum kennt genau ein Panel und wählt es fest:

```c
const struct h713_panel_cfg *c = &h713_panel_cfg_board_b;   /* 1280×720 */
```

**`h713_panel_cfg_board_a`** ergänzt - unser Panel, direkt aus der
`display_cfg.xml` des Geräts: htotal 2128, vtotal 1120, hsync 44, vsync 5,
hbp 88, vbp 20, width 1920, `dual_port = 1` (bei ihm 0). `pll_n_plus_1 = 83`
als erster Kandidat; exakt geht nicht, 83 liegt 0,50 % tief, 84 liegt 0,70 %
hoch, beide innerhalb der Grenzen, die die `display_cfg.xml` selbst angibt.

**Eine Zeile pro Gerät.** `h713_mips_fw_rev` trägt jetzt zusätzlich
`project_id`, `panel` und `tick_wait_va`. Vorher lagen Firmware-Größe, Digest,
HDCP-Adresse, ProjectID, Panel und die zweite Schreibstelle an fünf
verschiedenen Orten - genau das Muster, an dem sich dieses Projekt
wiederholt aufgehalten hat. Zwei Zugriffe auf dieselbe Tabelle, weil die
Kennungen zu verschiedenen Zeiten eintreffen: der `display.bin`-Digest erst
nach dem Laden, die ProjectID sofort.

**`h713_disp_lookup()`** setzt das aktive Panel, sobald die ProjectID bekannt
ist, und meldet welches. `H713_DISP_OSD_WIDTH/HEIGHT` lesen es statt aus
`#define`.

**Puffer panelabhängig.** `FB_ADDR_B` = Front + gerundete Flächengröße - bei
720p exakt das alte `0x6c500000`, bei 1080p `0x6c900000`. BMP-Staging von
`0x6d000000` auf `0x6e000000`, weil ein 1080p-Paar bis `0x6d100000` reicht.

**Skalier-Blit verworfen.** Er rechnete das native 1080p-Logo auf 720p herunter
und verdeckte damit, dass die Panel-Zeile falsch war. Jetzt 1:1, mit klarer
Meldung bei Größen-Mismatch statt stiller Resampling.

**`tick_wait_va` aus der Tabelle.** Auf unserem Image stehen an seiner Adresse
Nullen. `0` heißt jetzt „diese Revision hat die Stelle nicht", statt dort blind
eine Instruktion hineinzuschreiben.

## 11 - Display: die sechs Vendor-Panel-Leitungen

`board/sunxi/board.c` fasst PB5 an, `h713_disp_stock_panel_power()` fuhr PF6
und PH16. Der **Vendor-U-Boot-Devicetree** (`legacy/reference/uboot_dtb.dts`,
Knoten `tvtop@1`) nennt sechs, jede mit mux 1 und data 1:

```
panel_power_en  PH19      panel_gpio_0  PH16
panel_bl_en     PB5       panel_gpio_1  PH15
                          panel_gpio_2  PH8
                          panel_gpio_3  PH9
```

Vier davon waren unkonfiguriert - `gpio status PH19` las `func` ohne Richtung.
PF6 wiederum kommt in **keinem** der drei Devicetrees vor und gehört seinem
Board.

Von Hand am Prompt gesetzt kam das Bild danach sofort statt nach Minuten. Das
leichte Flackern bleibt, die Leitungen sind also nicht dessen Ursache. Jetzt
board-gebunden in der Power-Sequenz.

## 12 - Display: der Latch-Puls gehört keinem Board

`h713_disp_latch_panel_timing()` schreibt literale 720p-Werte in den TCON,
*nachdem* die MIPS gelaufen ist. Sein Kommentar sagt warum:

> Restore the panel timing that project 0x33's timing block 6 programmed
> before the MIPS replaced it with 1080p

Auf seinem 720p-Panel ist das die Reparatur. Auf unserem zerstört es die
richtige Einstellung der Firmware - 720p-Raster in ein 1080p-Panel, Inhalt in
1920×1080, sichtbar als schmaler flackernder Streifen.

Der erste Versuch stieg per `return` aus der Funktion aus und nahm damit auch
den Latch-Puls mit:

```c
writel(ctl | BIT(0), 0x0588000c);
udelay(1);
writel(ctl & ~BIT(0), 0x0588000c);
```

Danach kam gar kein Bild mehr. Der Puls committet den TCON, nachdem der
Coprozessor geparkt wurde, und gehört zu keinem Board im Besonderen. **Die
Werte überspringen, den Commit nie.**

## 13 - Display: Timing und PLL aus dem Stock-Vergleich

Alle Werte gegen ein laufendes Stock-System gemessen, siehe
[90-stock-referenz.md](90-stock-referenz.md).

**Die Totale halten total−1.** Stock liest `0525c000 = 045f084f`, also
2127/1119 für ein 2128 × 1120-Panel - die `typical`-Spalte der
`display_cfg.xml`. Der TCON steht dabei auf `04650898`, also 2200 × 1125:
**Mixer und TCON tragen bewusst verschiedene Zahlen.** Eine Zwischenversion
hat sie zur Übereinstimmung gezwungen, das war falsch.

**PLL:** `058c0014 = b9002800` → N = 40, also N+1 = **41**, und Bit 24
(`ssc_en`) **gesetzt**. Dazu `058c0018 = c8d0362f`, die Spread-Spectrum-
Wellenform. Der Stock-Boot-Log sagt dasselbe im Klartext: *„n:41,
ssc_freq:31500 reg_value:0xc8d0362f"*. Der Vendor-Default 43 ist 4,7 % zu
schnell.

**Porches:** hsync 44, vsync 5, hbp 88, vbp 20 - die XML-Werte. Die
Zwischenversion hatte 62/214 und 7/34 aus TCON-Registern hergeleitet, die
etwas anderes bedeuten.

Drei Felder waren falsch oder gar nicht gesetzt:

| Register | war | ist | |
|---|---|---|---|
| `05800000[4:3]` | `color_depth` → 8 & 3 = 0 | **1** | ein Enum, kein Bitcount |
| `0528008c` | fest 0 | **55** | Layer-X-Ursprung |
| `05280084[31:16]` | ungesetzt | **`height`** | die aktive Höhe |

Zwei Kommentare in seinem Baum sind damit widerlegt: *„stock writes a literal
zero here"* für `0528008c` und *„stock appears to zero it"* für
`05280084[31:16]`. Beides stammt aus Schlüssen ohne laufendes Stock-System.

## 14 - Display: der X-Ursprung darf nicht erzwungen werden

`h713_disp_clear_layer_xoff()` las `0x0528008c` und schrieb eine **literale
Null** hinein, sobald dort etwas anderes stand - an drei Stellen, unter
anderem nach dem DE-Replay. Als Sicherheitsnetz gedacht:

> If the patch lands, the register already reads 0 and these calls are silent.

Die Annahme gilt nur für Board B. Auf einem HY260 ist 55 richtig, und das Netz
hat den Tabellen-Patch nach jedem Replay wieder zunichte gemacht - sichtbar als
schmaler heller Balken am rechten Bildrand.

Heißt jetzt `h713_disp_enforce_layer_xoff()` und erzwingt
`h713_disp_panel->layer_x` statt einer Null. Board B bewegt sich nicht, dessen
Wert ist 0.

## 15 - Einschalt-Gate (`0018`, Plan [`103`](103-plan-einschaltgate.md), Bericht [`S36`](nachtlog/S36-uboot-power-gate.md))

`CONFIG_H713_POWER_GATE`: Vor `h713_poweron_lines()` prüft `board_late_init` das RTC-Register GP5 (`0x07090114`). `0` (Netz kam) und
`GATE` (Ausschaltwunsch, von TF-A geschrieben) halten das Gerät dunkel und leise, bis die Einschalttaste PL4 (aktiv-low, externer Pull-up,
50 ms entprellt, Start beim Loslassen) gedrückt wird; `RUN1` (warmer Neustart) bootet direkt. U-Boot stempelt RUN1 auf jedem Pfad, bevor
Lüfter/Backlight/USB eingeschaltet werden - `reboot`, Absturz und Watchdog landen nie im Gate. Taste ≥ 3 s beim Netz-Einschalten überspringt das
Gate einmalig; `setenv h713_gate 0; saveenv` schaltet es dauerhaft ab, `1` an. Die Status-LED folgt PB5 (1 = blau, 0 = rot), es gibt keinen
LED-Code. Gate an in `hy310_qz713_v3_1_defconfig` und der Test-Defconfig `hy310_netboot_gate_defconfig` (geflasht 09.09.), aus in
`hy310_netboot`, `hy310_host`, `hy310_felmmc`. Gegenstück in TF-A: `sunxi_power_down()` stempelt GATE und resettet über den Haupt-Watchdog
(Commit `dfa9fab44` im Submodul, Bericht S37). Konsolenzeilen: `gate: cold start (GP5 …)`, `gate: warm start, booting`,
`gate: power-off requested`, `gate: waiting for power key`, `gate: power key, booting`, `gate: off (h713_gate=0)`.

## 16 - Env-Offset: der 2-GiB-Fehler in `env/mmc.c` (`0022`, 10.09.2026)

**Befund:** alle HY310-Defconfigs sagen `CONFIG_ENV_OFFSET=0x93d80000` (LBA 4844544, in `empty`/p7), und trotzdem lag die gespeicherte Env
am Gerät bei Byte `0x65d80000` (LBA 3.337.216, mitten in `super`, im Ziel-Layout in `hy310-data`). `saveenv`/`printenv` funktionierten und
verdeckten es. Ursache in `env/mmc.c`, `mmc_offset()`:

```c
return ofnode_conf_read_int(propname, defvalue);   /* int default_val, int Rückgabe */
```

`0x93d80000` passt nicht in ein `int` → `-0x6c280000`; `mmc_get_env_addr()` deutet negative Werte als „vom Ende des Geräts" und addiert
die Kapazität (`0x1d1f00000`) → `0x165d80000`, dann Zuweisung an `u32 *env_addr` → **`0x65d80000`**. Rechnung und Messung decken sich exakt.
Betroffen ist jeder MMC-Env-Offset ≥ 2 GiB in jedem U-Boot mit `OF_CONTROL`, nicht nur unserer.

**Fix `0022` (`env: mmc: keep a default offset of 2 GiB or more intact`):** die DT-Eigenschaft `u-boot,mmc-env-offset` wird direkt gelesen
(`ofnode_read_u32`, alte int-Semantik für DT-Werte bleibt), der Kconfig-Wert geht unverändert als `s64` zurück. Generisch, Kandidat für
einen PR an cstenger und upstream (R6).

**Folgen:** (1) `tftp/uboot-proper-gate-v4.bin` = v3 + `0022`. (2) Nach dem Flash findet U-Boot die alte Env nicht mehr - Vorgabe greift,
`h713_gate=1`: am Dev-Gerät sofort `setenv h713_gate 0; saveenv`. (3) Der Installer (`hy310-install.sh` 0.2) nimmt den Ort nicht an, sondern
sucht Env-Blöcke per CRC (Release-Ort, Zwilling `0x65d80000`, ganze p7; `--env-scan full`), prüft mit `--uboot-bin` den geflashten proper
und übernimmt mit `--env-migrate` die Variablen des Zwillings. (4) Ein U-Boot ohne den Fix darf nicht mit dem Ziel-Layout betrieben werden:
seine Env läge in einer ext4-Partition.

**Bau:** nur im Container `h713-build` (`doku/50` Bauen: LLVM 20 von apt.llvm.org, `python3-setuptools`), `build/uboot-build.sh` mit
absolutem `O=` unter `/work`; proper = `u-boot-sunxi-with-spl.bin` ab Byte 32768. v4 ist mit clang 20.1.8 gebaut wie v3, gleich groß
(886.137 B), BL31 aus `build/out/bl31.bin` (08.09.) enthalten, geprüft. Ein Versuch auf dem Host (clang 18: kein srec, keine gnutls-Header)
wurde verworfen - keine Host-Umgehung.
