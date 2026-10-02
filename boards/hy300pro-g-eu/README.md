# HY300PRO-G-EU

A HY300 Pro bought by the maintainer (`well0nez`) in October 2026, box label **`HY300PRO-G-EU`**,
stock Android 11 of 2025-05-06. It is **not** the HY300 Pro of
[issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1) (`boards/hy300-pro`): that
one runs an Android 10 firmware of 2024, DDR3 at 636 MHz, 25 partitions and a display.bin of its
own. This one is HY310-like in everything that has been measured, and it is here so that the
maintainer can run the same software as issue #1's owner on a board of his own.

| | |
|---|---|
| Status | **profile-only** - a complete description from its own eMMC dump; nobody has run our firmware on it |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300pro_g_eu.py` |
| Image | **TEST images** only (`release/build-all.sh --board hy300pro-g-eu --test-image --version vX.Y`), table `test_for: "hy300pro_g_eu"` |
| Kernel DTB | `sun50i-h713-hy300pro-g-eu` (kernel patch 0167: the HY310's tree; the lamp's PWM words, fan tacho PH13, no pwm-backlight, no focus motor; the accelerometer node left on) |
| U-Boot base | `hy300pro_g_eu_defconfig` (hy310_defconfig with this board's device tree, name and tpr0..tpr2) |
| SoC | H713 (`sun50iw12p1`), stock DTB compatible `allwinner,tv303 arm,sun50iw12p1` |
| DRAM | DDR3 (type 3), **792 MHz** - the 24 boot0 words of its own eMMC (`uboot.config`) |
| Panel | declared project id `0x34`, 1280x720 single port, 1360x760 total, 62 MHz; lamp PWM channel 5, low active, 40 kHz |
| eMMC | **15 273 600 sectors** - 3712 more than the HY310's; 26 partitions, the HY310's table, only `UDISK` longer |
| Stock | Android 11, `h713_tuna_p3`, U-Boot 2018.05-00025-g4176897 of May 06 2025 |

## Where the numbers come from

All of it from one source: the full eMMC dump of 2026-10-02 (kept private) and what the
installer and `h713-extract` read out of it - the identification row (`h713-install identify`)
and the extraction report. Package GEU1 (`umbau/work/GEU1/`) compares each value with the
profile and the board files (`tools/check_profile.py`, LOG.txt).

- **DRAM** - the 24 words at LBA 16 (vendor boot0). Equal to what `hy310_defconfig` boots with,
  word for word, except tpr0..tpr2 (the HY310's defconfig carries the bench board's there); the
  DDR3 path of `dram_sun50iw12.c` never reads those three. tpr13 `0xb4016103` and para2
  `0x04000000` are the flashed-in values, as on any dump of a running device.
- **Partition table** - the GPT of the dump: 26 entries, first usable 73728, last usable
  15273566, backup header at 15273599. Entry for entry the HY310's, `UDISK` runs to the end.
- **Display firmware** - `display.bin` 1 256 216 bytes `16c74a28...` and `LogoRegData.bin`
  15 652 bytes `0d00bcdd...`: byte-identical to the HY310's, so the HDCP wait site `0x4b13d0a4`
  and the 15 LogoRegData descriptors are the HY310's. The event log addresses belong to the image,
  so cpu_comm's HY310 defaults are expected to apply (not checked on the board).
  `ProjectID_0x0034.TSE` (17 328 B) and `display_cfg.xml` are this firmware's own;
  `database.TSE` is the L018's.
- **Panel and lamp** - `vendor:/etc/tvconfig/panel_config/panel_config.ini`: ProjectID 52
  (`0x34`), 1280x720, `[PWMSetting]` channel 5, polarity 1, 40 kHz, vs_lock 1, duty 1..100.
- **ARISC** - its own build (`TV-303 ARISC 00.00.00.09`, May 6 2025); the kernel resolves its
  SRAM addresses from the image (0091a), so nothing about it is in this directory.

## Hardware this board does not have (`FEATURES=` in board.env)

| | this board | source |
|---|---|---|
| camera | none | no lens by eye - maintainer statement; verify on mainline: no capture device should appear |
| focus motor | none | maintainer statement, consistent with the stock DT's `motor_ctr` `status = "disabled"`; confirm on the device. The kernel tree switches the node off, so PH4..PH7 are not driven |
| accelerometer | unknown | the stock DT lists lsm6dsr (0x6a), stk83xx (0x18) and kxtj3 (0x0e) on twi1, all enabled, and does not say which one is fitted. The kernel tree leaves the HY310's SC7A20 node at 0x18 on, so the first boot answers it: `dmesg` says "failed to read Who-Am-I register" (nothing at 0x18), "WhoAmI mismatch" (another chip at 0x18 - the driver only warns and registers it as `sc7a20` anyway, so its readings mean nothing), or nothing and `/sys/bus/iio/devices/iio:device*/name` reads `sc7a20` |

What else the stock DT says differently from the HY310's, and what the kernel tree does with it,
is listed in package GEU1's report (round 2): the fan tachometer is PH13 here (PH17 on the HY310),
the panel power line is PF6 (U-Boot drives it), USB1's VBUS is PL3 (U-Boot drives it), there are no
ADC keys; the power key is PL4 as on the HY310.

## The project id

`h713-extract` prints "used 0x30" for this board, from the display.bin digest, next to the
declared `0x34`. That line is a report only: U-Boot takes the project from the environment's
`h713_project`, else from `panel_config.ini` (`h713_disp_declared_project()`, never from the
digest), and `h713-install` writes `h713_project` from the device's own `panel_config.ini` -
`0x34` here - plus `/etc/h713/board` with `project_id = 0x34` for `h713-tv`.

## What we do not know

- whether anything of ours boots on it - nobody has tried;
- what PB4 and PH17 are on this board: its stock DT does not say (PH17 carries the fan PWM's pin
  group, which the HY310's stock DT has too, where PH17 is the tacho); the tree leaves both alone;
- whether the fan runs at a usable speed without a PWM, and whether PH13 counts it (the board
  manager powers off after 8 s without pulses once the system runs: "fan0 stalled -- powering
  off to protect the optics" on the serial console; without one, fan and picture go off some
  10-20 s after the logo on every start, and the volatile journal keeps nothing);
- which pad hardware PWM channel 5 leaves the SoC on, and whether the firmware drives it once it
  has the six words (the open question of issue #1 as well);
- the content of `Reserve0`'s `panel_config.ini`: the ProjectID read off the device is `0x34`,
  the file itself was not extracted;
- the DRAM size (not in the boot0 words; the HY310 and the issue #1 board have 1 GiB).

## Moving it forward

The maintainer builds the TEST image, keeps his full dump as the way back, installs it with
`--test-image`, and reports. A green run makes this board `verified` with his name, the board
and the date in `VERIFIED_BY`; until then it stays `profile-only` here and everywhere else.
