# HY200 QZ713_V2 (projector, untested)

The second board of cstenger's tree: silkscreen `HY200_QZ713_V2`, said to sit inside a projector and
to carry LPDDR3. We have his defconfig and his DTB name for it, and nothing else — no device, no
boot, no log.

| | |
|---|---|
| Status | **profile-only** — a complete description, no device run |
| Verified by | nobody |
| Profile | none |
| Image | never built (`STATUS` is not `verified`) |
| Kernel DTB | `sun50i-h713-hy200-qz713-v2` — built today, marked untested in `versions.env` |
| U-Boot base | `hy200_qz713_v2_defconfig` |
| Kernel defconfig | `hy200_qz713df_a1_defconfig` (shared; there is no separate one) |
| DRAM | LPDDR3, 1 GiB, 720 MHz — **assumed, never booted** |
| Old name | `BOARD=lpddr3`, still accepted as an alias |

## Where the numbers come from

- **DRAM and device tree** — `configs/hy200_qz713_v2_defconfig` of the U-Boot fork, verbatim,
  including his own note that these are the board's stock BT0 values (type 7 = LPDDR3,
  `zq=0x003f3ffb`, `odt/flags=0x31`, `para1=0x10f410f4`).
- **Defconfig names** — `mainline/config/versions.env`, `UBOOT_DEFCONFIG_LPDDR3` and
  `KERNEL_DEFCONFIG`; `boards/check.sh` fails if they drift apart from this `board.env`.
- **DTB** — `versions.env`, `KERNEL_DTB_PROJECTOR`: *"arm64 projector DTB (untested on hardware)"*.

## Why this board is not `verified`

Three places in this repository say nobody has run it:

- `mainline/README.md`: "Inside a projector; do not risk it" — all bring-up runs are on the bench
  board.
- `mainline/config/versions.env`: the projector DTB is "untested on hardware".
- `docs/hardware.md`: the LPDDR3 attribution is *assumed, never booted*, and it is unresolved whether
  `HY200_QZ713_V2` is a genuinely different board or the same one under a name taken from a listing.
  "Assume nothing from it."

So the DRAM values are complete and are cstenger's own, but no green run backs them. Under the
honesty rule that is `profile-only`: describe it, build a U-Boot and a kernel for it, never ship an
image for it. If cstenger has booted this board and says so, the status becomes `verified` and
`VERIFIED_BY` gets his name and the date — that is a one-line change, and it is the only thing
missing.

## What is special about it technically

It is the only H713 board we know on the **LPDDR3** path of the DRAM driver. There the packed timing
words are used as they are (`tpr0`–`tpr2`, gated by bit 1 of `tpr13`); on the DDR3 path — every other
board in `boards/` — the driver computes the timing registers from `CONFIG_DRAM_CLK` and ignores
them. A change to the LPDDR3 arm of `dram_sun50iw12.c` therefore affects exactly this board, and it
is the one board nobody can test.
