# Was cstenger portiert hat, und was nicht

Vollständiger Abgleich `legacy/drivers/` gegen `mainline/patches/kernel/`,
Stand 31.08.2026. Nicht stichprobenartig - jeder Treiber, jeder Patch.

## Zugeordnet

| unser Baum | Zeilen | sein Patch | Zeilen |
|---|---|---|---|
| `cpu_comm/` (10 Dateien) | ~9.000 | `0014-soc-sunxi-add-cpu-comm-ipc` | 8.440 |
| `decd/` (6 Dateien) | ~2.700 | `0013-misc-add-sunxi-decd` | 3.106 |
| `tvtop/` (5 Dateien) | ~1.400 | `0012-misc-add-sunxi-tvtop` | 1.666 |

Dazu CCU, Pinctrl, MMC, PHY, NSI, LRADC, PPU, CIR, Cedrus - die Patches
0001-0022 sind unsere, mit Namensnennung übernommen (sein `PROVENANCE.md`).

## Weggelassen: `sunxi-mipsloader`

Unsere Patch-Nummer 0010. Seine Nummerierung springt **0009 → 0011**. Der
MIPS-Loader existiert in seinem Kernel-Baum nicht; er macht diese Arbeit in
U-Boot (`arch/arm/mach-sunxi/h713_mips.c`, gut 11.000 Zeilen). Die
Registerdefinitionen sind dieselben, nur eine Stufe früher.

## Kein Gegenstück: `display/ge2d/`

Zehn Dateien, rund 3.000 Zeilen, in seinem Baum vollständig abwesend:

| Datei | Zeilen | Inhalt |
|---|---|---|
| `sunxi_ge2d_firmware.c` | 1.010 | `g_panel_set[29]`-Aufbau, Firmware-Parser |
| `sunxi_ge2d_osd.c` | 476 | OSD-Ebenen |
| `sunxi_ge2d_core.c` | 372 | Kern |
| `sunxi_ge2d_fbdev.c` | 293 | fbdev |
| `sunxi_ge2d_dt.c` | 215 | Devicetree-Parsing der `panel_*`-Felder |
| **`sunxi_ge2d_dlpc3435.c`** | **208** | **DLP-Lichtmaschine über I²C** |
| `sunxi_ge2d_svp.c` | 172 | SVP |
| `sunxi_ge2d_backlight.c` | 146 | Backlight |
| `sunxi_ge2d_panel.c` | 144 | Panel-Callbacks |

An dessen Stelle steht `0037-drm-add-h713-afbd-scanout-kms-driver`, 535 Zeilen,
das ausdrücklich nur übernimmt, was U-Boot hinterlassen hat, und Timing, LVDS
und `rst_bus_disp` nicht anfasst.

**Das ist der größte strukturelle Unterschied zwischen den Bäumen.** `ge2d/`
ist der Stock-Display-Stack - Panel-Konfiguration aus dem Devicetree,
Backlight, OSD, Lichtmaschine. Davon ist nichts portiert, und nichts davon
findet in seinem U-Boot ein Äquivalent.

Für die Helligkeit hat sich daraus bisher nichts ergeben: die
DLPC3435-Spur ist an der Hardware gescheitert, siehe
[70-sackgassen.md](70-sackgassen.md).

## Ebenfalls ohne Gegenstück

`audio/` (4 Dateien plus Bridge, ~4.000 Zeilen), `media/av1/` (7 Dateien,
~2.000 Zeilen) und `display/drm/h713_drm.c` (1.460 Zeilen). Audio ist bei ihm
Roadmap-Punkt 6, nicht angefangen, mit ausdrücklichem Verweis auf unsere
Treiber als Ausgangsmaterial. HDMI-RX fehlt bei ihm ganz.

## Was er selbst gebaut hat

`0007` PWM-Achtkanaltreiber, `0008` Board-Manager, `0009` Keystone-Motor,
`0017`/`0041`/`0042` IOMMU, `0019` LRADC, `0020` PPU, `0025` - `0028` CPU-DVFS,
`0031` RTC, `0033` - `0035` decd-Korrekturen, `0036` - `0038` der Scanout-/KMS-Weg,
`0039`/`0040` Cedrus-Absicherung, `0043` - `0048` MMC-Feinschliff.

## Devicetrees

Drei liegen vor, und sie sagen nicht dasselbe:

| Datei | was er ist |
|---|---|
| `legacy/reference/uboot_dtb.dts` | **Vendor-U-Boot**, dekompiliert - der für unseren Fall maßgebliche |
| `legacy/reference/stock_dts/hy310-board.dts` | Stock-Kernel |
| `legacy/dts/sun50i-h713-hy310.dts` | unser Kernel-Port |

Abweichungen zwischen Bootloader- und Kernel-Devicetree, die zählen:

| Feld | U-Boot-DT | Kernel-DT |
|---|---|---|
| Panel-GPIOs | **sechs** (`panel_gpio_0..3`) | vier (`lcd_standby` statt `panel_gpio_1`) |
| `panel_pwm_pol` | 1 | 0 |
| `panel_backlight` | 0x64 = 100 | 0x4B = 75 |

Beide nennen `panel_dclk_freq = 148500000`, `panel_dual_port = 1` und
`panel_ssc_en = 1`.
