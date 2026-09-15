# HY200 QZ713DF_A1 (bench)

cstenger's bring-up board, silkscreen `HY200_QZ713DF_A1`: an H713 on a bench, not in a projector.
The mainline port started here, and this repository's kernel, U-Boot and rootfs work was developed
against it before the HY310 existed as a target. It is not a board we own, and nothing of ours has
ever been flashed to it.

| | |
|---|---|
| Status | **profile-only** — nobody has run *our* firmware on this board |
| Verified by | nobody. cstenger booted his own kernel tree on it (see below); that is his run, not ours |
| Profile | `hy200_qz713df_a1` — from the 2025-09-22 "HY300 Pro+" DDR3 stock image |
| Image | never built (`STATUS` is not `verified`) |
| Kernel DTB | `sun50i-h713-hy200-qz713df-a1` |
| U-Boot base | `hy200_qz713df_a1_defconfig` |
| Kernel defconfig | `hy200_qz713df_a1_defconfig` — today the shared one for every board |
| DRAM | DDR3, 1 GiB (Samsung K4B2G0846D, auto-sized), 624 MHz |
| Panel | 1280x720 single-port, ProjectID `0x34`, 62 MHz, PWM channel 5 / 40 kHz |
| Old name | `BOARD=ddr3`, still accepted as an alias |

## Where the numbers come from

- **DRAM and device tree** — `configs/hy200_qz713df_a1_defconfig` of the U-Boot fork, verbatim. The
  values are this board's own stock BT0; nothing is borrowed, nothing comes from an image.
- **Installer profile** — `installer/h713/profiles/hy200_qz713df_a1.py`, built in package F1 from the
  facts of the 2025-09-22 "HY300 Pro+" DDR3 vendor image
  (`installer/tests/fixtures/images/hy300-pro-plus-ddr3-0922.json`). That image is this board's
  firmware: its boot0 DRAM block is the defconfig above word for word (624 MHz, type 3,
  `zq=0x7b7bfb`, `para1=0x10f4`, `tpr11/12=0x44340000/0x6666`), and its `display.bin` (1 255 696 B,
  sha256 `4380f1b3…`) is the revision `h713_mips_fw_revs[]` already lists under
  *HY200 QZ713DF_A1*. Only `para2`/`tpr13` differ, because the flashing tool patches that pair
  (`boards/README.md`), and `tpr0`–`tpr2`, which the DDR3 path computes from the clock anyway.
- **Defconfig names** — `mainline/config/versions.env`: `UBOOT_DEFCONFIG_DDR3` and
  `KERNEL_DEFCONFIG`. `boards/check.sh` fails if `board.env` and `versions.env` drift apart.
- **What was verified** — `mainline/README.md`: "All FEL/bring-up runs on this one"; the signed
  key-only rootfs, growfs, serial recovery, modules and sshd are hardware-verified on this board;
  `versions.env` records Linux 6.18.38 as "boot-good on HY200 QZ713DF_A1". Video decode, IOMMU and
  the Mali GPU come from his tree and are verified there, not here (`STATUS.md`).

## Why it is `profile-only` although cstenger booted it

`STATUS` says whether an owner has run **a build of ours** on the board and reported it green. Nobody
has. What exists is cstenger's own verification, in his own tree, and it is worth writing down:

- `mainline/README.md`: "All FEL/bring-up runs on this one".
- `mainline/config/versions.env`: Linux 6.18.38 recorded as *boot-good on HY200 QZ713DF_A1*.
- `STATUS.md`: hardware video decode, IOMMU and the Mali GPU are verified in his tree, not here.

That is somebody else's green run on somebody else's build, so under the honesty rule
(`boards/README.md`) it does not make the board `verified` and `VERIFIED_BY` stays empty. Having a
profile now does not change it either: a profile describes the stock firmware, it does not test
anything. When cstenger (or any owner of this board) runs an image of ours and reports it green, this
row becomes `verified`, `VERIFIED_BY` gets their name, their board and the date — and only then can
`release/build-all.sh --board hy200-qz713df-a1` produce an image.

## Note on the name

`HY200_QZ713DF_A1` is the bench board. The HY310 this repository runs on carries `HY260_QZ713_V3.1`
on its silkscreen and is a different board with a different DRAM clock (792 MHz) — the two shared one
defconfig and one DTB name for a long time, which is exactly the confusion stage 4 removes
(`doku/121`). See `docs/hardware.md` for the three names in circulation.
