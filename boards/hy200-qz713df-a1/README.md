# HY200 QZ713DF_A1 (bench)

cstenger's bring-up board, silkscreen `HY200_QZ713DF_A1`: an H713 on a bench, not in a projector.
The mainline port started here, and this repository's kernel, U-Boot and rootfs work was verified on
it before the HY310 existed as a target. It is not a board we own.

| | |
|---|---|
| Status | **verified** — by its owner, not by us |
| Verified by | cstenger, HY200 QZ713DF_A1 bench board |
| Profile | none (no stock image of this board was ever analysed here) |
| Image | not buildable: a release image needs an installer profile |
| Kernel DTB | `sun50i-h713-hy200-qz713df-a1` |
| U-Boot base | `hy200_qz713df_a1_defconfig` |
| Kernel defconfig | `hy200_qz713df_a1_defconfig` — today the shared one for every board |
| DRAM | DDR3, 1 GiB (Samsung K4B2G0846D, auto-sized), 624 MHz |
| Old name | `BOARD=ddr3`, still accepted as an alias |

## Where the numbers come from

- **DRAM and device tree** — `configs/hy200_qz713df_a1_defconfig` of the U-Boot fork, verbatim. The
  values are this board's own stock BT0; nothing is borrowed, nothing comes from an image.
- **Defconfig names** — `mainline/config/versions.env`: `UBOOT_DEFCONFIG_DDR3` and
  `KERNEL_DEFCONFIG`. `boards/check.sh` fails if `board.env` and `versions.env` drift apart.
- **What was verified** — `mainline/README.md`: "All FEL/bring-up runs on this one"; the signed
  key-only rootfs, growfs, serial recovery, modules and sshd are hardware-verified on this board;
  `versions.env` records Linux 6.18.38 as "boot-good on HY200 QZ713DF_A1". Video decode, IOMMU and
  the Mali GPU come from his tree and are verified there, not here (`STATUS.md`).

## Why it is `verified` and still gets no image

`STATUS=verified` says a person ran this firmware on this board and reported it green — that person
is cstenger. It does not say we can produce a release image for it: an image also needs an installer
profile (`PROFILE=`, empty here), because everything proprietary in an image comes out of the
owner's own device dump. So this board builds a kernel and a U-Boot, and stops there.

## Note on the name

`HY200_QZ713DF_A1` is the bench board. The HY310 this repository runs on carries `HY260_QZ713_V3.1`
on its silkscreen and is a different board with a different DRAM clock (792 MHz) — the two shared one
defconfig and one DTB name for a long time, which is exactly the confusion stage 4 removes
(`doku/121`). See `docs/hardware.md` for the three names in circulation.
