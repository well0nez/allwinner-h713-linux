# HY200 QZ713DF A1

One printed circuit board, silkscreen **`HY200 QZ713DF A1`**, sold in at least two projectors and
used bare as cstenger's bench board, the board the mainline port was brought up on. The same PCB
left the factory with different firmware, and that - not the hardware - is what differs between
units. So this is one board directory with one device tree and one U-Boot base, and each stock
firmware is a **variant** under `variants/<stock build>/`.

| | `projector05061226` | `projector09220931` |
|---|---|---|
| Sold as | HY300 Pro, box label **HY300PRO-G-EU** (the maintainer's own unit, October 2026) | "HY300 Pro+" (2025, DDR3) |
| Stock | Android 11 of 2025-05-06 | Android 11 of 2025-09-22 |
| State | **in test, the maintainer's own**: profile-only; a TEST image of ours booted on it (doku/136), no green report yet | **profile, testable**: profile-only; nobody has run our firmware on a unit with this firmware |
| Image | TEST only: `release/build-all.sh --board hy200-qz713df-a1 --variant projector05061226 --test-image --version vX.Y` | TEST only, the same with `--variant projector09220931` |
| DRAM clock | 792 MHz (its own boot0) | 624 MHz (its boot0; cstenger's bench clock) |
| eMMC | 15 273 600 sectors (its own GPT) | 15 269 888 sectors (the image's GPT; no unit read) |
| display.bin | 1 256 216 B `16c74a28...` = the HY310's revision | 1 255 696 B `4380f1b3...` = the `HY200 QZ713DF_A1` row of `h713_mips_fw_revs[]` |
| Measured | SC7A20 accelerometer at 0x18; no camera; fan tacho PH13 at 5520-5610 rpm (doku/136) | nothing |
| Installer profile | `hy200_qz713df_a1/projector05061226` | `hy200_qz713df_a1/projector09220931` |

Board level, the same for both: kernel DTB `sun50i-h713-hy200-qz713df-a1` (patch 0181), U-Boot base
`hy200_qz713df_a1_defconfig` (layout v4, the board's DRAM words, 624 MHz unless a variant says
otherwise), DDR3 type 3, panel project id `0x34` (1280x720 single port, 1360x760, 62 MHz), LVDS
8 bit (U-Boot `2de0cc8` for project 0x34), the lamp's PWM words `5 1 40000 1 1 100`, fan tacho PH13,
the 26-entry partition table (only UDISK follows the eMMC) and the places of the device-unique
regions. Old names: `BOARD=ddr3` (still an alias of `build/build.sh`) and `boards/hy300pro-g-eu`.

## Where the numbers come from

- **projector05061226** - the full eMMC dump of the maintainer's unit of 2026-10-02 (kept private),
  what `h713-install identify` and `h713-extract` read out of it, and its running stock system over
  ADB (package GEU1, working journal `GEU1`). Its stock device tree came out of `vendor_boot_a`.
- **projector09220931** - the 2025-09-22 `update.img` in the local firmware archive
  (`firmware/hy200-qz713df-a1/2025-09-22_projector09220931/`, sha256 `ced372b4...`) and its facts
  (`installer/tests/fixtures/images/hy300-pro-plus-ddr3-0922.json`): boot0, boot package, both
  `panel_config.ini` copies, the display firmware and the stock device tree of `vendor_boot.fex`.
- **The bench** - cstenger's `configs/hy200_qz713df_a1_defconfig` (624 MHz, his flash layout) and his
  runs: `mainline/README.md` "All FEL/bring-up runs on this one", `versions.env` Linux 6.18.38
  "boot-good". His run, not ours: it makes no variant `verified`.

What is the same: the 23 boot0 words besides the clock (tpr0..tpr2 included; para2/tpr13 only differ
as the image's unpatched pair against a running device's patched one), the partition table, the
panel and the `[PWMSetting]` of both `panel_config.ini` copies (channel 5, low active, 40 kHz, vsync
lock 1, duty 1..100, `ColorDepth 8`), and the two stock device trees, which differ in one node only:
`motor_ctr`. What differs is firmware: build, boot package, ARISC, display.bin, MIPS database,
vendor partition size, the DRAM clock - and, as an assembly option, the focus motor (below).

## The DRAM clock

The vendor ran this board at 792 MHz (2025-05) and at 624 MHz (2025-09) with the same words. In
`dram_sun50iw12.c` both clocks fall into the same DDR3 speed bin of `iw12_set_timing()` (one cycle
table, split at 800 MHz; only trasmax and the init timers scale), but `iw12_phy_train()` sets the
byte lanes' pads differently above 672 MHz. Each clock has run only on its own firmware's units: 792
on the HY300PRO-G-EU (its boot0, and our TEST image), 624 on the 2025-09 units and on cstenger's
bench. So every variant keeps the clock its own boot0 trains with (`DRAM_CLK` in its `variant.env`),
and the base runs 624, so that a build that names no variant gets the lower clock, never the higher.

## Optional hardware (`FEATURES`)

| | projector05061226 | projector09220931 | source |
|---|---|---|---|
| accelerometer | SC7A20 at 0x18, an IIO device | unknown | doku/136 section 1; the stock trees list lsm6dsr, stk83xx and kxtj3 and say nothing |
| camera | none | unknown | doku/136: no capture device |
| focus motor | none | its stock tree drives one | stock trees: `motor_ctr` disabled with a 4-step table / okay with the HY310's 8-step tables on PH4..PH7, limiter PH14 |

The board's tree leaves `motor_ctr` off: on a unit without a motor the driver would home at probe
and drive PH4..PH7 into nothing. A 2025-09 unit therefore loses its focus motor under our firmware
until its owner shows one and the tree learns per-variant nodes. The accelerometer node stays on.

## The project id

`h713-extract` may print "used 0x30" for the 2025-05 firmware, from its display.bin digest (the
HY310's revision), next to the declared `0x34`. That line is a report only: U-Boot takes the project
from the environment's `h713_project`, else from `panel_config.ini`, never from the digest, and
`h713-install` writes `h713_project` and `/etc/h713/board` (`project_id = 0x34`) from the device's own
`panel_config.ini`.

## What we do not know

- whether anything of ours runs on a 2025-09 unit, and that unit's real eMMC size and DRAM size
  (the image's GPT is a vendor template; the bench has 1 GiB, K4B2G0846D);
- the display firmware's event-log addresses of the 2025-09 display.bin (`cpu_comm` uses the HY310's,
  right for the 2025-05 firmware; a wrong pair only empties the elog dump);
- which pad hardware PWM channel 5 leaves the SoC on, and what PB4 and PH17 are on this board;
- whether a 2025-09 unit has the accelerometer, a camera, and the focus motor its stock tree drives.

## Moving it forward

An owner builds the TEST image of their variant, keeps their full dump as the way back, installs it
with `--test-image`, and reports. A green run makes **that variant** `verified` (its `variant.env`:
`STATUS=verified`, `VERIFIED_BY` with name, unit and date); the other variant stays where it is,
because its DRAM clock, eMMC and display firmware are not the ones that were tested.
