# HY200 QZ713_V2 (projector, untested)

The second board of cstenger's tree: silkscreen `HY200_QZ713_V2`, said to sit inside a projector and
to carry LPDDR3. We have his defconfig, his DTB name, and - since package F1 - a stock vendor image
that matches his DRAM block exactly. What we still do not have is a device, a boot or a log.

| | |
|---|---|
| Status | **profile-only** - a complete description, no device run |
| Verified by | nobody |
| Profile | `hy200_qz713_v2` - from the 2025-07-10 "HY300 Pro+" LPDDR3 stock image |
| Image | never built (`STATUS` is not `verified`) |
| Kernel DTB | `sun50i-h713-hy200-qz713-v2` - built today, marked untested in `versions.env` |
| U-Boot base | `hy200_qz713_v2_defconfig` |
| Kernel defconfig | `hy200_qz713df_a1_defconfig` (shared; there is no separate one) |
| DRAM | LPDDR3, 1 GiB, 720 MHz - his defconfig, now backed by that image's boot0; **never booted here** |
| Panel | 1280x720 single-port, ProjectID `0x34`, 62 MHz, PWM channel 5 / 40 kHz |
| Old name | `BOARD=lpddr3`, still accepted as an alias |

## Where the numbers come from

- **DRAM and device tree** - `configs/hy200_qz713_v2_defconfig` of the U-Boot fork, verbatim,
  including his own note that these are the board's stock BT0 values (type 7 = LPDDR3,
  `zq=0x003f3ffb`, `odt/flags=0x31`, `para1=0x10f410f4`).
- **Defconfig names** - `mainline/config/versions.env`, `UBOOT_DEFCONFIG_LPDDR3` and
  `KERNEL_DEFCONFIG`; `boards/check.sh` fails if they drift apart from this `board.env`.
- **DTB** - `versions.env`, `KERNEL_DTB_PROJECTOR`: *"arm64 projector DTB (untested on hardware)"*.
- **Installer profile** - `installer/h713/profiles/hy200_qz713_v2.py`, built in package F1 from the
  facts of the 2025-07-10 "HY300 Pro+" LPDDR3 vendor image
  (`installer/tests/fixtures/images/hy300-pro-plus-lpddr3-0710.json`). Its boot0 DRAM block is his
  defconfig word for word - 720 MHz, type 7, `zq=0x003f3ffb`, `odt_en=0x31`, `para1=0x10f410f4`,
  `tpr7=0x1621121e`, `tpr10=0x7767`, `tpr11/12=0x44650000/0x5544` - with two differences:
  `para2`/`tpr13` are the unpatched pair every image boot0 carries, and `tpr0` - `tpr2` are the image's
  template, not the board's timing. U-Boot uses his; *The timing words* says why.
- **One stock firmware** - the 2025-07-10 image is the only one known for this board, so it has no
  variants.
- **Panel and display firmware** - the image's `Reserve0.fex:panel_config.ini` (ProjectID `0x34`,
  1280x720, 1360/760/20/2/40/20, 62 MHz, both polarities 0, PWM 5 / 40 kHz) and its `display.bin`
  (1 255 664 B, sha256 `4628cbaf...`, HDCP wait site `0x4b13d538`, searched with `h713.hdcpsite`).

## Why this board is not `verified`, and not testable yet

Three places in this repository say nobody has run it:

- `mainline/README.md`: "Inside a projector; do not risk it" - all bring-up runs are on the bench
  board.
- `mainline/config/versions.env`: the projector DTB is "untested on hardware".
- `docs/hardware.md`: the LPDDR3 attribution is *assumed, never booted*, and it is unresolved whether
  `HY200_QZ713_V2` is a genuinely different board or the same one under a name taken from a listing.
  "Assume nothing from it."

The stock image found in package F1 corroborates his numbers - it is this board's own firmware - but
corroboration is not a boot. So the DRAM values are complete and are cstenger's own, but no green run
backs them. Under the honesty rule that is `profile-only`: describe it, never ship an image for it.

A TEST image is not ready either, although `release/build-all.sh --test-image` passes its dry run: its
U-Boot base `hy200_qz713_v2_defconfig` is cstenger's bring-up config (environment at `0x400000`, no
U-Boot sector `0x800`, no display bring-up), not our installer's layout v4 as `hy200_qz713df_a1_defconfig`
became in ST3-BOARDMERGE, and its kernel tree is the H713 dtsi alone (no lamp PWM words, the HY310's
motor and accelerometer nodes). Both need a board of their own first.

## What is special about it technically

It is the only H713 board we know on the **LPDDR3** path of the DRAM driver. There the packed timing
words are used as they are (`tpr0` - `tpr2`, gated by bit 1 of `tpr13`); on the DDR3 path - every other
board in `boards/` - the driver programs a fixed cycle table and ignores them. A change to the LPDDR3
arm of `dram_sun50iw12.c` therefore affects exactly this board, and it is the one board nobody can test.

## The timing words

Decoded with the bit fields of `iw12_set_timing()` (one unit = two DRAM clocks, 2.78 ns at 720 MHz;
`tREFI` in units of 32):

| | tRCD | tRP | tRAS | tRC | tRRD | tFAW | tWR | tRFC | tREFI |
|---|---|---|---|---|---|---|---|---|---|
| cstenger `0x49225a/0x1b1b1d0/0x4c02c` | 25.0 | 19.4 | 44.4 | 72.2 | 11.1 | 50.0 | 16.7 | 211 | 3911 |
| image `0x4a2195/0x2423190/0x8b061` | 16.7 | 16.7 | 44.4 | 58.3 | 11.1 | 55.6 | 16.7 | 386 | 8622 |
| LPDDR3-1600 minimum (JEDEC) | 18 | 18 | 42 | 60 | 10 | 50 | 15 | 210 (8 Gb) | max 3900 |

(ns.) **cstenger's words are this board's, and U-Boot uses them.** They are LPDDR3 timing at 720 MHz
in every field - 210 ns refresh cycle and a 3.9 us refresh interval are LPDDR3's own numbers - and
they are what a boot0 header read off a device carries: one table of round nanosecond values
reproduces his set and the three DDR3 sets read off devices (bench 624 MHz, issue #1 636,
HY300PRO-G-EU 792) exactly, each at its own clock. His `tpr13` `0xb4036223` (bit 1 set: "use the
words") is likewise a device's, not an image's. The image's words are the DDR3 timing at 792 MHz -
the template every image boot0 here carries, the 624 and 640 MHz ones as well; read as LPDDR3 at
720 MHz they break tRCD, tRP and tRC and refresh half as often as LPDDR3 needs. Its `tpr13`
`0x34032220` has bit 1 clear, so its own boot0 does not use them. Two small marks on his set: tREFI
is 0.3 % above 3.9 us (the formula's rounding) and tRP 19.4 ns is below the all-bank 21 ns.

A first boot shows whether the words hold: the SPL's `DRAM: 1024 MiB` (a wrong size or a hang there
is the DRAM) and then a kernel that stays up under load (`memtester` over most of the RAM).
The vendor boot0's `DRAM simple test OK` line belongs to the stock boot and is the comparison.

## Optional hardware (`FEATURES`)

Unset: no unit ran anything of ours, and nothing in its image says whether a camera, an accelerometer
or a focus motor is fitted.
