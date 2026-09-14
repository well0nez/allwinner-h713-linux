# HY350

An H713 projector we know only from its stock firmware image. Nobody working on this repository has
one in hand; nothing of ours has ever run on it.

| | |
|---|---|
| Status | **profile-only** — a complete description, no device run |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy350.py` |
| Image | never built (`STATUS` is not `verified`) |
| Kernel DTB | none |
| U-Boot base | `hy350_defconfig` (does not exist yet — see below) |
| DRAM | DDR3 (type 3), 792 MHz, 1 GiB — the HY310's clock, a different PHY tuning |
| Panel | 1920×1080, dual port, 148.5 MHz, declared project id `0x30` |
| Stock | Android 10, ADT-3 build 6245789, `sunxi_version` 2024-10-25 17:15:54 |

## Where the facts come from

One source: the stock OTA image `HY350_user_public_en_F_chuangyihui_OTA_2024-10-25-1715_.img`,
unpacked into `umbau/fixtures/images/hy350.json` (package A1) and written down as
`installer/h713/profiles/hy350.py`.

- **DRAM** — the 24 words at `boot0_sdcard.fex+0x38`. Same clock as the HY310 (792 MHz) and the same
  DDR3 value set, but its own PHY tuning: `tpr11` `0x44440000` and `tpr12` `0x00005555` against the
  HY310's `0x44340000` / `0x00006666`. That is the part of a DRAM block that cannot be derived from
  anything else, and it is why one board's fragment is not another's.
- **Panel** — `Reserve0.fex:panel_config.ini`: project id `0x30`, 1920×1080 dual port, htotal 2200,
  vtotal 1125, 148 500 000 Hz, hsync 44, vsync 5, hbp 148, vbp 12, PWM channel 5 at 40 kHz. The same
  declared project id as the HY310, with different timings — the project id selects the panel entry,
  it is not itself the timing.
- **Layout** — 25 partitions, `super` 5 242 880 sectors, a *single* `Reserve0` at LBA 6 013 952. The
  HY310's constants do not fit this board.
- **Display firmware** — `display.bin` 1 252 128 bytes,
  `22a7df113fce3fa182926268de8c7551a107f0c3bc2932f0940bd58b8f424835` ("ADT-3 2024"), and its U-Boot
  has no MIPS loader at all: the firmware lives only in the vendor partition, not in
  `bootloader_a/_b` as on the HY310.
- **Identification** — the HY350 and the HY300 T08 share the ADT-3 build fingerprint and the same
  `database.TSE`; only the `scp`/`u-boot`/`dtb` digests and the two version strings tell them apart.

## What we do not know

- whether our SPL trains this board's DRAM: `para2` and `tpr13` in the fragment are the HY310's
  patched values, not this board's
- anything from hardware: no UART log, no dump, no `h713_probe` output, no panel measurement

## What it would take to move this board forward

The same path as every untested board: an owner runs the release `h713_probe` over FEL (read-only)
and posts the log (`docs/tools/h713-probe.md`). That replaces the two borrowed DRAM words with
measured ones and adds the project descriptors the firmware carries. An image needs a green run
reported by the owner — `boards/README.md`, honesty rule.

`UBOOT_BOARD=hy350` names a base defconfig that does not exist in the U-Boot fork yet, so no release
or installer build is possible for this board. That is the intended state.
