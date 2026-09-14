# HY300 T08

An H713 projector we know only from its stock firmware image. Nobody working on this repository has
one in hand; nothing of ours has ever run on it.

| | |
|---|---|
| Status | **profile-only** — a complete description, no device run |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_t08.py` |
| Image | never built (`STATUS` is not `verified`) |
| Kernel DTB | none |
| U-Boot base | `hy300-t08_defconfig` (does not exist yet — see below) |
| DRAM | DDR3 (type 3), 640 MHz, 1 GiB |
| Panel | 1280×720, single port, 62 MHz, declared project id `0x34` |
| Stock | Android 10, ADT-3 build 6245789, `sunxi_version` 2024-04-19 20:28:23 |

## Where the facts come from

One source: the stock OTA image `HY300_T08_OTA_2024-04-19-2028.img`, unpacked into
`installer/tests/fixtures/images/hy300-t08.json` (package A1) and written down as
`installer/h713/profiles/hy300_t08.py`.

- **DRAM** — the 24 words at `boot0_sdcard.fex+0x38`. `uboot.config` carries them; the two words the
  vendor flashing tool patches on its way onto the eMMC (`para2`, `tpr13`) are marked there, because
  an image carries the unpatched pair.
- **Panel** — `Reserve0.fex:panel_config.ini`: project id `0x34`, 1280×720 single port, htotal 1360,
  vtotal 760, 62 000 000 Hz, hsync 20, vsync 2, hbp 40, vbp 20, both syncs active low, PWM channel 5
  at 40 kHz. This is the second panel the U-Boot firmware table knows (`0x34`: 1280×720 single port),
  against the HY310's `0x30`.
- **Layout** — 25 partitions, `super` 6 291 456 sectors, a *single* `Reserve0` at LBA 7 062 528 (the
  HY310 has an `a`/`b` pair at 5 489 664 / 5 522 432). An installer must not carry the HY310's
  constants over to this board.
- **Identification** — this image and the HY350 share the ADT-3 build fingerprint and the same
  `database.TSE`, so neither of those tells the two boards apart; the profile's `strong_features`
  drop both and rely on the `scp`/`u-boot`/`dtb` digests and the two version strings.

## What we do not know

- whether our SPL trains this board's DRAM at all: `para2` and `tpr13` in the fragment are the
  HY310's patched values, not this board's
- everything below the surface of the image: no UART log, no device dump, no `h713_probe` output
- the panel's electrical side (LVDS lane order, backlight ramp), because nothing was ever driven

## What it would take to move this board forward

An owner runs the release `h713_probe` over FEL — read-only, no write to the eMMC — and pastes the
log into an issue (`docs/tools/h713-probe.md`). That log carries the device's own boot0 block,
including the patched `para2`/`tpr13`, the `display.bin` digest and the project descriptors. With it,
`uboot.config` stops containing borrowed values. An image still needs a green run reported by the
owner; until then the honesty rule stands (`boards/README.md`, `doku/121` §5).

`UBOOT_BOARD=hy300-t08` names a base defconfig that does not exist in the U-Boot fork yet — no
release or installer build is possible for this board, which is the intended state. A probe build
uses the generic `h713_probe` base and can take this fragment's DRAM block on top.
