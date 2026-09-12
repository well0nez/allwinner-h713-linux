# U-Boot: boot chain, the fork, and which defconfig to use

Everything this project added to U-Boot — H713 support, the display bring-up, and the power-on gate
that decides whether the projector starts by itself — lives in a private fork, not upstream mainline.
This page is the boot chain end to end, how that fork relates to what ships in this repository, and
which of the tree's defconfigs is the one you actually want; get the last part wrong and you flash a
bench-only or diagnostic-only build.

## The chain

**BROM → SPL → TF-A BL31 → U-Boot proper → FIT → Linux.**

The BootROM reads a fixed 32 KiB SPL from LBA 16 on the eMMC — the one address it cannot be told to use
anything else for; everything after it is freely placed (`doku/109-plan-layout-v3.md` §2.1, measured and
flashed 10.09.2026). The SPL brings up DRAM with the timing its defconfig hard-codes — there is no
runtime detection — and hands off to TF-A's BL31 (submodule `arm-trusted-firmware`, branch
`sun50i-h713`), which owns EL3 and the PSCI power-down path the [power gate](power-gate.md) hooks into.
BL31 hands off to U-Boot proper, loaded from a 5 MiB window starting at LBA 2048: its `board_late_init`
runs the gate if it was compiled in, then brings up the fan/backlight/USB-VBUS lines, and `bootcmd`
starts the [display coprocessor](commands.md) before loading a kernel FIT image and handing off with
`bootm`.

## Relation to the fork

U-Boot is a git submodule, `mainline/external/u-boot`, pinned to branch `h713` of a private fork of
[cstenger/u-boot](https://github.com/cstenger/u-boot) (`mainline/.gitmodules`).
The branch is **`h713-hy310`**, and that is what this repository's own `.gitmodules` pins. The file
inside `mainline/` is cstenger's and names his branch `h713`; git only reads the one at the root, so
his copy is inert here.
The submodule is a pinned commit in a fork, and `uboot-h713/` mirrors the same 33 commits as
`git format-patch` files — for reading, or for `git am` into another tree. The build uses the submodule.
The first five — the H713 CCU tables, USB PHY support, the R_PIO and USB-host device-tree nodes, and the
fan and USB power lines in `board_late_init` — are filed upstream as
[cstenger/u-boot#1](https://github.com/cstenger/u-boot/pull/1). The rest is not submitted yet: most of
it — the whole display bring-up in `h713_mips.c`, the power gate, the boot-path and environment layout —
is specific to this panel and this board, but one, a generic U-Boot bug this board's environment offset
exposed (`env/mmc.c` truncating an offset ≥ 2 GiB through a plain `int`), is upstream material still
waiting to go out. The full list, with the hardware evidence behind each change, is
`doku/30-uboot-aenderungen.md`.

## Which defconfig

All seven configs below build against the same device tree, `sun50i-h713-hy200-qz713df-a1` — cstenger's
DDR3 bench board's DT, reused because this projector's own board turned out to be a third variant
(silkscreen `HY260_QZ713_V3.1`, DDR3 at 792 MHz, proven independently four ways, not identical to either
of his two known boards — `doku/10-hardware.md`).

| Defconfig | Purpose | DRAM clock | power gate |
|---|---|---|---|
| `hy310_qz713_v3_1_defconfig` | the shipping build (`release/build-all.sh`); USB gadget mode, so `ums` and fastboot work | 792 MHz | on |
| `hy310_host_defconfig` | development: makes the USB-A socket a host instead of a gadget — the internal camera needs this at the bench | 792 MHz | off |
| `hy310_netboot_defconfig` | development: `hy310_host_defconfig` plus networking, boots over TFTP/NFS instead of eMMC | 792 MHz | off |
| `hy310_netboot_gate_defconfig` | `hy310_netboot_defconfig` with the gate compiled in, built to test the gate itself before it moved into the release build | 792 MHz | on |
| `hy310_installer_defconfig` | exposes the eMMC as a USB drive from FEL (`ums 0 mmc 1`) for `hy310-install`; no saved environment and no kernel boot at all | 792 MHz | off |
| `hy310_felmmc_defconfig` | not a bootable image — an SPL with the original vendor `boot0` compiled in, to restore the first boot stage over FEL if that is ever needed | 792 MHz | off |
| `hy200_h713_felmmc_defconfig` | the same restore SPL, at the bench board's un-overclocked 624 MHz instead of 792 | 624 MHz | off |

Two more defconfigs in the same directory are out of scope here: `hy200_qz713df_a1_defconfig` targets
cstenger's bench board directly, and `hy200_qz713_v2_defconfig` an LPDDR3 board revision neither of us
has ever booted — unverified.

Details: `doku/30-uboot-aenderungen.md`, `doku/109-plan-layout-v3.md`, `doku/10-hardware.md`.
