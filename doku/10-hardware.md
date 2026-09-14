# Hardware

Alles hier ist gemessen oder aus dem Vendor-Material belegt, nichts geraten.
Wo es nur eine Vermutung ist, steht das dabei.

## Board

| | |
|---|---|
| Silkscreen | `HY260_QZ713_V3.1` |
| Aufkleber | `CGDD00700507/HY260A 1G+8G/UH2025011/9` |
| SoC | Allwinner H713 (sun50iw12), Los `Q81570A 2943` |
| SoC-ID | `0x1860`, im Kernel als `jep106:091e:1860` |
| CPU | 4× Cortex-A53, MIDR `0x410fd034` |

Das ist eine **dritte** Variante. cstenger kennt `HY200_QZ713DF_A1` (Bench,
DDR3) und `HY200_QZ713_V2` (Projektor, den er für LPDDR3 hält und nie
gebootet hat).

## DRAM

**DDR3, 792 MHz, 1 GiB.** Auf vier Ebenen belegt:

1. UART-Log des Vendor-boot0: `DRAM CLK = 792 MHz`, `DRAM Type = 3
   (2:DDR2,3:DDR3)`, `DRAM SIZE = 1024 M`
2. Der Baustein: SK hynix `H5TQ...EFR` — das Präfix `H5TQ` ist ihre
   DDR3-Linie (LPDDR3 wäre `H9C`, DDR3L `H5TC`)
3. `sys_config.fex`: `dram_clk = 792`, `dram_type = 3`
4. `boot0_sdcard.fex`/`boot0_nand.fex` bei Offset `0x38`

Die Parameter, die wir ausliefern — **nicht** durchgehend die aus dem boot0.
Nachgemessen am eigenen Vollabzug (13.09., `doku/120` §4.1): bei LBA 16 und
LBA 256 steht je ein `eGON.BT0`, ab Offset `0x38` der 24-Wort-Block. Davon
kommen `zq`, `para1`, die Moduleregister und `tpr3`–`tpr12` wörtlich von dort;
`tpr0`–`tpr2` rechnet cstengers generalisierter DDR3-Block aus dem Takt
(boot0: `0x004A2195`/`0x02423190`/`0x0008B061`, defconfig:
`0x00482151`/`0x01B1A94C`/`0x0006E04D`); bei `PARA2`/`TPR13` steht unten nicht
der boot0-, sondern der **defconfig**-Wert (siehe Korrektur unter dem Block).
`tpr11`/`tpr12` sind boardspezifische PHY-Abstimmung und lassen sich aus
nichts herleiten — deshalb liest `h713_probe` den Block vom Gerät:

```
dram_clk    792          dram_tpr0   0x004A2195
dram_type   3 (DDR3)     dram_tpr1   0x02423190
dram_zq     0x007B7BFB   dram_tpr2   0x0008B061
dram_odt_en 0x00000001   dram_tpr3   0xB4787896
dram_para1  0x000010F4   dram_tpr5   0x48484848
dram_para2  0x04000000   dram_tpr6   0x00000048
dram_mr0    0x00001C70   dram_tpr7   0x1620121E
dram_mr1    0x00000040   dram_tpr10  0x00000000
dram_mr2    0x00000018   dram_tpr11  0x44340000
dram_mr3    0x00000000   dram_tpr12  0x00006666
                         dram_tpr13  0xB4016103
```

**Korrektur (14.09., Stufe 4; der Hinweis stand seit dem 13.09. in `doku/120`
§4.1):** Dieser Block ist gemischt. `para2 0x04000000` und `tpr13 0xB4016103`
sind die **defconfig**-Werte, nicht die des boot0 — im boot0 des Geräts wie im
`update.img` stehen dort `0` und `0x34010100`
(`installer/h713/profiles/hy310.py`, Feld `dram`, gelesen aus
`boot0_sdcard.fex+0x38`). Alles andere im Block kommt aus dem boot0.

Unser ausgeliefertes DRAM-Fragment (`boards/hy310/uboot.config`) ist bis auf
den Takt identisch mit dem von `hy200-qz713df-a1`. Sein generalisierter
DDR3-Timing-Block rechnet 792 korrekt, ohne Änderung —
`hs = eclk > 800` ist bei 792 falsch, also derselbe Speed-Bin wie sein 624.

## Panel

**1920×1080 LVDS, dual-port.** Aus der `display_cfg.xml` des Geräts selbst
(`re/ida/IDA_hy310/TSE/`, liegt neben `ProjectID_0x0030.TSE` — also unsere ID):

```xml
<hde_size val='1920'/>    <vde_size val='1080'/>
<htotal typical='2128'/>  <vtotal typical='1120'/>
<pclk typical='143001600'/>
```

2128 × 1120 × 60 = 143.001.600 — exakt der angegebene pclk. Also 1080p60.

Vierfach unabhängig bestätigt:

| Quelle | Aussage |
|---|---|
| eigenes Kernel-Log (`re/notes/loop-sequential-safe-…`) | `panel=1920x1080 … dual_port=1 project_id=48` (= 0x30) |
| `re/notes/lvds-de2-tvtop.md` | device-verified: DE2-Panel-Region +0xBC/0xC0 = 1920×1080 |
| `re/notes/CURRENT-TRUTH.md` | ida-verified: AFBD `Y_GEOM = 0x04380780` |
| `legacy/drivers/tvtop/sunxi_tvtop_drv.c:85` | `dual_port == 1 → TVTOP_RES_1080P` |

Das Vendor-Bootlogo ist 1920×1080 (6.220.854 Bytes), weil das die native
Auflösung ist. Daran wird nichts skaliert.

### Falle: HY300-Boilerplate

`drivers/misc/sunxi-mipsloader.c` und Patch 0010 tragen einen fremden Header —
*„Copyright (C) 2025 HY300 Linux Porting Project"*, *„specifically for the HY300
projector hardware"*. Die Sätze *„Display framebuffer for 1280x720 native
panel"* und *„HDMI input processing and downscaling (1080p to 720p)"* stammen
von dort und beschreiben den **HY300**, ein anderes Gerät. Sie sind beim
Übernehmen mitgewandert und haben hier bereits einmal zu einer Fehldiagnose
geführt. Nichts in diesem Header ist an unserer Hardware gemessen.

### Die sechs Panel-Leitungen

Der Vendor-U-Boot-Devicetree (`legacy/reference/uboot_dtb.dts`, Knoten
`tvtop@1`) nennt sechs GPIOs, jede mit `<phandle bank pin mux pull drive data>`,
mux 1 = Ausgang, data 1:

| Eintrag | Pin | |
|---|---|---|
| `panel_power_en` | PH19 | |
| `panel_bl_en` | PB5 | **nie auf low** — Lüfter hängt daran |
| `panel_gpio_0` | PH16 | |
| `panel_gpio_1` | PH15 | |
| `panel_gpio_2` | PH8 | |
| `panel_gpio_3` | PH9 | |

Der Stock-Kernel-Devicetree nennt nur vier davon und heißt PH15 dort
`lcd_standby`. PF6, das cstengers U-Boot als „panel power" fährt, kommt in
**keinem** der drei Devicetrees vor.

Vier waren unkonfiguriert (`gpio status PH19` las `func` ohne Richtung).
Seit dem Build vom 31.08. setzt die Power-Sequenz sie board-gebunden.

### Nicht die Helligkeit

PH17 ist der **Lüfter-Tachometer**, also ein Eingang — eigene Notiz vom
01.04.2026. PH18 trägt pwm1 und ist mit hoher Wahrscheinlichkeit der
Lüfterantrieb. PB4 trägt pwm2, den Panel-Dimmer, der nachweislich nichts
bewirkt. Details in [70-sackgassen.md](70-sackgassen.md).

### Das 720p im U-Boot-Log ist sein Panel, nicht unseres

```
02d00500   aktiv          1280 × 720
02f80550   gesamt         1360 × 760
00140028   Sync-Breiten     20 / 40
```

Kein Messwert, sondern `h713_panel_cfg_board_b` aus `h713_mips.c:4740` — die
einzige Panel-Config in der Datei, transkribiert aus der `panel_config.ini`
**seines** Boards (ProjectID 0x34). Zeile 4816 wählt sie fest aus. Wir schreiben
sie damit auf ein 1080p-Panel. Die MIPS-Firmware überschreibt das Timing
anschließend selbst mit 1080p — siehe [40-display.md](40-display.md).

## USB

| Port | Adresse | was dranhängt |
|---|---|---|
| 0 | `ehci@4101000` / `ohci@4101400` | **externe USB-A-Buchse**, OTG. FEL und Gadget laufen darüber |
| 1 | `ehci@4200000` / `ohci@4200400` | **interne Kamera**, Realtek `0bda:5803` „Generic HD camera", 480 Mb/s — **läuft seit 11.09.** (`uvcvideo`, YUYV 640×480, [`analyse/beamer-cam/`](../analyse/beamer-cam/README.md)) |
| 2 | `ehci@4300000` / `ohci@4300400` | registriert, nichts dran |

Die PHY-Register liegen **8 Byte** auseinander, nicht 4 wie beim D1:

| Port | Register | OHCI-Takt | PHY-Takt | PHY-Reset |
|---|---|---|---|---|
| 0 | `0xa70` | BIT 31 | BIT 29 | BIT 30 |
| 1 | `0xa78` | BIT 31 | BIT 29 | BIT 30 |
| 2 | `0xa80` | BIT 31 | BIT 29 | BIT 30 |

Belegt im Vendor-U-Boot bei `0x4a045e12` (`cmp r0, #1`, dann
`ldr r2, =0x02001a78`) und im eigenen Kernel-CCU (Patch 0001).

Die HCI-PHYs starten mit **SIDDQ gesetzt** (`PHY_CTL_SIDDQ = BIT(3)` bei
PMU + `0x10`). Der Vendor löscht es mit `bic r3, r3, #8` bei `0x4a045ee8`.
Ohne das wird ein Gerät am Port erkannt, aber der Reset läuft nie durch.

## GPIOs

| Pin | Funktion | Regel |
|---|---|---|
| `PB5` | Lüfter **und** Panel-Backlight gemeinsam | **niemals LOW** — der Lüfter stoppt, das Board überhitzt |
| `PL3` | USB-/Kamera-Versorgung, im Stock-Map `cam-usb-power-gpio` | niemals LOW |
| `PF6`, `PH16` | Panel-Power-Sequenz | vom Display-Pfad gesetzt |
| `PL0`, `PL1` | Status-LED laut Vendor-DT | wird nicht per GPIO getrieben, hängt an den Rails |

`PL` liegt im R_PIO bei `0x07022000`, einem eigenen Controller. In U-Boot
braucht es dafür einen `r_pio`-Knoten im Devicetree, sonst schlägt jeder
Zugriff auf PL mit `-ENOENT` fehl.

## eMMC

7,3 GiB, HS400, 26 Partitionen (Android-GPT). Der Vendor-Bootloader fährt sie
mit `Best spd md: 4-HS400, freq: 5-200000000, Bus width: 8`.

Wichtige Partitionen:

| # | Name | Start-LBA | Größe |
|---|---|---|---|
| 1 | `bootloader_a` | 73728 | 32M |
| 2 | `bootloader_b` | 139264 | 32M |
| 3 | `env_a` | 204800 | 256K |
| 5 | `boot_a` | 205824 | 64M |
| 18 | `empty` | 4828160 | 15M |
| 26 | `UDISK` | 5555200 | 4,6G |

`empty` ist unbenutzt und nimmt U-Boot proper, Env und den SPL-Parkplatz auf.

## Firmware auf dem eMMC

| | |
|---|---|
| `display.bin` | 1.256.216 Bytes (`0x132b18`), sha256 `16c74a28187f342d…` |
| Bootlogo | 1920×1080, 24 bpp, 6.220.854 Bytes, sha256 `9684ef71483eb199…` |
| ProjectID | **`0x30`** — aus dem eigenen MIPS-Log: `load group: ProjectID_0x0030` |

Dreizehn TSE-Gruppen liegen auf dem Gerät (`0x0001` bis `0x0035`). cstengers
Board benutzt `0x34`.
