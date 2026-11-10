# HY300 T08

An H713 projector known from its stock firmware image and, since 31.10.2026, from the eMMC dump of its first owner
(issue #7). Nobody working on this repository has one in hand; nothing of ours has ever run on it.

| | |
|---|---|
| Status | **profile-only** - a complete description, no device run; a TEST image can be built since 03.11.2026 |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_t08.py`, three variants: `ota20240419` (the stock OTA image), `unit202311` (the issue #7 unit), `fw20250221` (the issue #10 unit, eMMC 14 942 208 sectors) |
| Image | TEST only, per variant: `release/build-all.sh --board hy300-t08 --variant unit202311` (or `fw20250221`) `--test-image --version vX.Y`; published as pre-releases for their owners (`hy300-t08-test1`, 04.11.2026) |
| Kernel DTB | `sun50i-h713-hy300-t08` (kernel 0349, 03.11.2026): the HY300 Pro's tree with the "ADT-3 2024" firmware's elog and AFBD handoff words from the HY320; built with dtc, never booted |
| U-Boot base | `hy300_t08_defconfig` (fork `h713-hy310`, mirror `uboot-h713/0111`, 03.11.2026): `hy300_pro_defconfig` with this board's DRAM block at 640 MHz, its tree and its identification string; builds (release, installer), never run |
| DRAM | DDR3 (type 3), 640 MHz, 1 GiB; the HY350 family's block (`tpr0..tpr2` 0x4a2195 / 0x2423190 / 0x8b061) |
| Panel | 1280×720, single port, 62 MHz, declared project id `0x34`; display firmware "ADT-3 2024" (`22a7df11...`), the HY350's and HY320's |
| Wi-Fi | **AIC8801** (SDIO `5449:0145`), not the AIC8800D80 of the other boards; its firmware set lies at the root of `vendor:/etc/firmware/` and `h713-extract` takes it since 03.11.2026 |
| Stock | ADT-3 build 6245789: the OTA of 2024-04-19 (Android 10, U-Boot 2024-04-15, ARISC 2024-04-19), the issue #7 unit's 2023-11 boot package under a 2024-07 Android 11 userland, or the issue #10 unit's 2023-08 package under a 2025-02 Android 11 userland |

## Where the facts come from

- **ota20240419** - the stock OTA image `HY300_T08_OTA_2024-04-19-2028.img`, unpacked into
  `installer/tests/fixtures/images/hy300-t08.json` (package A1): boot0, boot package, `panel_config.ini`, the display
  firmware, the layout.
- **unit202311** - the owner's full eMMC dump (7 818 182 656 B), read by him with `h713-install identify` and
  `h713-extract 0.4` under Windows (issue #7, 31.10./01.11.2026), and the device tree item of his boot package
  (`7db0a4d3...`, 71 168 B) he attached. His boot package is older than the OTA's (U-Boot `2018.05-00014-gbbed928` of
  2023-11-18, ARISC of 2023-11-23, its own `dtb`; `monitor` and `optee` are the OTA's), the vendor partition, its
  fingerprint and all 19 display files are the OTA's byte for byte, his boot0 at LBA 16 is the OTA's block (unpatched
  pair), his LBA 256 copy the HY350's 792 MHz block (the BROM takes LBA 16 while it is valid). A second boot package at
  LBA 32800 holds a U-Boot of 2024-07-15, probably left by an update; which package his unit starts is not measured.
- **fw20250221** - the second owner's `h713-install identify` over FEL with our T08 installer U-Boot (issue #10,
  05.11.2026; the drive came up with `--device` only, since its size was unknown to `find_drive` until 10.11.2026), his
  boot0 block read from Android, his GPT and `panel_config.ini`. A boot package of 2023-08 (U-Boot `2018.05-00008-gc26a358`
  of 2023-08-08, ARISC of 2023-08-12, its own `dtb` `e0ee997e...`; `monitor` and `optee` not read) under a 2025-02-21
  Android 11 userland (32-bit, kernel 5.4.99), a vendor partition of its own (115 920 896 B), the display firmware and
  `database.TSE` the OTA's, the OTA's DRAM block, the panel block value for value, and an eMMC of 14 942 208 sectors
  (T22708; `UDISK` 7095296+7846879): the first H713 board below 15 269 888. Package item sizes are assumed from the
  family until his `h713-extract` package line is in. He has the stock IR remote, ADB and a `dd` of the whole eMMC.
- **DRAM** - the 24 words at `boot0_sdcard.fex+0x38`, the same on his LBA 16. `uboot.config` and `hy300_t08_defconfig`
  carry them with the `para2`/`tpr13` pair every defconfig of the fork uses (what the HY310 runs; his LBA 16 has the
  unpatched image form, his LBA 256 the patched pair). Whether our SPL trains this board's DRAM: not measured.
- **Panel** - `Reserve0.fex:panel_config.ini`: project id `0x34`, 1280×720 single port, htotal 1360, vtotal 760,
  62 000 000 Hz, hsync 20, vsync 2, hbp 40, vbp 20, both syncs active low, PWM channel 5 at 40 kHz (the HY300 Pro's
  lamp words). The display firmware is the HY320's: its row in `h713_mips.c` and its elog/handoff values (0335) apply.
- **The board, from his stock device tree** (decompiled and compared, `arbeit/issue7-hy300-t08-20261031/`): the HY300
  Pro's on every pin and table - LEDs, fan with tacho PH17, focus motor PH4..PH7 with the HY300 Pro's timing and
  limiter PH14, PB5, Wi-Fi/BT lines, accelerometer node on twi1, codec. It differs from the HY300 Pro's only in the
  decoder reservation (64 KiB), the SDIO clock (150 MHz) and an enabled eight-key LRADC keyboard; the owner checked the
  case: **the power button is the only key** (`getevent`: `KEY_POWER` and nothing else), so the tree has no keyboard
  node. He has **no remote**: on a test image the power button is his only input, everything else is Wi-Fi and ssh.
- **Layout** - 25 partitions, `super` 6 291 456 sectors, a *single* `Reserve0` at LBA 7 062 528 (the HY310 has an
  `a`/`b` pair). An installer must not carry the HY310's constants over to this board.
- **Identification** - the OTA, the HY350 and his unit share the ADT-3 build fingerprint and the same `database.TSE`,
  so neither tells them apart; the variants rely on the `scp`/`u-boot`/`dtb` digests and the two version strings
  (his unit has no `sunxi_version`).

## What we do not know

- whether our SPL trains this board's DRAM, and whether the display firmware drives the panel from our chain (project
  `0x34` with the "ADT-3 2024" firmware has never been run by us; the HY320 runs that firmware with `0x30`)
- whether this board's panel block needs the HY320's three DE words (`0x058c0000` bit 28, `0x051c0014`, `0x051c0028`)
  for the video plane; the tree names no mix window
- whether the AIC8801 comes up with our driver and his firmware set (the driver knows the chip; not measured)
- the HDMI socket's receiver port (`allwinner,hdmi-port` is not set: port 0)
- which of his two boot packages his unit starts; his boot0 training clock in practice

## What it would take to move this board forward

A TEST image of `unit202311` over FEL, from RAM, nothing written to the eMMC: `h713-fel` is not available on stock,
so FEL is reached with `adb reboot efex` (as on the HY320). The owner sees the wall and, if Wi-Fi comes up, ssh;
without a UART and without a remote there is no other channel. A green run makes the variant `partial` (TEST image
boots), as the HY320 is; `verified` needs a reported run of a release build.
