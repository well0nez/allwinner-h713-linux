# U-Boot: boot chain, the fork, and which defconfig to use

Everything this project added to U-Boot - H713 support, the display bring-up, and the power-on gate
that decides whether the projector starts by itself - lives in a private fork, not upstream mainline.
This page is the boot chain end to end, how that fork relates to what ships in this repository, and
which of the tree's defconfigs is the one you actually want; get the last part wrong and you flash a
bench-only or diagnostic-only build.

## The chain

**BROM → SPL → TF-A BL31 → U-Boot proper → FIT → Linux.**

The BootROM reads a fixed 32 KiB SPL from LBA 16 on the eMMC - the one address it cannot be told to use
anything else for; everything after it is freely placed (`doku/109-plan-layout-v3.md` §2.1, measured and
flashed 10.09.2026). The SPL brings up DRAM with the timing its defconfig hard-codes - there is no
runtime detection - and hands off to TF-A's BL31 (submodule `arm-trusted-firmware`, branch
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
The submodule is a pinned commit in a fork, and `uboot-h713/` mirrors the same commits as
`git format-patch` files (`SERIES.txt` lists them) - for reading, or for `git am` into another tree. The build uses the submodule.
The first five - the H713 CCU tables, USB PHY support, the R_PIO and USB-host device-tree nodes, and the
fan and USB power lines in `board_late_init` - are filed upstream as
[cstenger/u-boot#1](https://github.com/cstenger/u-boot/pull/1). The rest is not submitted yet: most of
it - the whole display bring-up in `h713_mips.c`, the power gate, the boot-path and environment layout -
is specific to this panel and this board, but one, a generic U-Boot bug this board's environment offset
exposed (`env/mmc.c` truncating an offset ≥ 2 GiB through a plain `int`), is upstream material still
waiting to go out. The full list, with the hardware evidence behind each change, is
`doku/30-uboot-aenderungen.md`.

## Which defconfig

There is one defconfig per **board** and one fragment per **role**, and a build is the two of them
merged. The board says what the hardware is - SoC, DRAM timings and clock, console, eMMC, power lines.
The role says what the build is for - whether it boots, from where, whether it keeps an environment,
whether the USB-A socket is a gadget or a host, whether the [power gate](power-gate.md) is compiled in.

```
build/uboot-build.sh <output-dir> <board> [role] [make-target...]
build/uboot-build.sh build/uboot-release hy310 release
```

It runs `make <board>_defconfig`, merges `configs/fragments/h713_<role>.config` over the result with
`scripts/kconfig/merge_config.sh -m`, and settles it with `make olddefconfig`. Without a role you get
the board base, which boots nothing on purpose.

### Boards

| Board base | What it is | DRAM | Device tree |
|---|---|---|---|
| `hy310` | this projector (silkscreen `HY260_QZ713_V3.1`), DDR3 overclocked to the vendor's own 792 MHz | 792 MHz | `sun50i-h713-hy310` |
| `hy200_qz713df_a1` | cstenger's DDR3 bench board - verified by him, not by us | 624 MHz | `sun50i-h713-hy200-qz713df-a1` |
| `hy200_qz713_v2` | an LPDDR3 board revision neither of us has ever booted - unverified | 720 MHz | `sun50i-h713-hy200-qz713-v2` |
| `h713_probe` | **not a board** - the read-only probe for boards nobody has measured, at the conservative 624 MHz so an unknown board is more likely to train. It keeps its own base rather than being a role, because the clock is the whole point of it | 624 MHz | `sun50i-h713-hy200-qz713df-a1` |

The HY310 got a device tree of its own in stage 4. It is an include of the bench board's plus `model`
and `compatible`, so the two cannot drift; what changed is that a boot log now names the board it is
running on. Everything board-specific we patched into the HY200 tree still lives there.

### Roles

| Role | Purpose | power gate | USB-A | environment |
|---|---|---|---|---|
| `release` | the shipping build (`release/build-all.sh`) - boots the eMMC, `ums` and fastboot work | **on** | gadget | eMMC, 7 MiB |
| `host` | bench development: USB-A becomes a host, which the internal camera needs | off | host | eMMC, 7 MiB |
| `netboot` | `host` plus networking; boots over TFTP/NFS instead of eMMC | off | host | eMMC, 7 MiB |
| `netboot_gate` | `netboot` with the gate compiled in - how the gate was proven before it entered the release build | **on** | host | eMMC, 7 MiB |
| `installer` | exposes the eMMC as a USB drive from FEL (`ums 0 mmc 1`) for `h713-install`; no kernel boot at all | off | gadget | **none** (`ENV_IS_NOWHERE`) |
| `felmmc` | not a bootable image - an SPL carrying the original vendor `boot0`, to restore the first boot stage over FEL | off | gadget | eMMC, 4 MiB |

Roles are board-independent by construction. `hy200_h713_felmmc_defconfig` - the restore SPL at the
bench board's 624 MHz - is what `hy200_qz713df_a1` + `felmmc` produces, down to every symbol but
`CONFIG_PREBOOT`, which the bench base ends with `h713_disp auto 0x34 logo` and the felmmc build does
not. It is still a file of its own until someone decides which of the two is right.

### Why a base plus a fragment, and not ten defconfigs

Because there were ten, six of them for this one board, and they agreed on 53 lines and disagreed on
28. Every DRAM correction had to be made six times, and the one that was not, was not: for a year the
comment above `CONFIG_DRAM_CLK` announced the bench board's 624 MHz above a 792.

One detail worth knowing before writing a fragment: **fragments subtract reliably and add unreliably.**
Kconfig lowers a symbol when its dependencies stop being met, but not when whatever merely raised it
goes away, so a base without the USB gadget leaves `ANDROID_BOOT_IMAGE` and `CMD_FASTBOOT` at `n` and a
fragment that switches the gadget on afterwards does not bring them back. That is why the base carries
the superset - gadget and eMMC environment included - and the roles that do not want them switch them
off. Four symbols do not follow even then (`CMD_BIND` is implied, `ANDROID_BOOT_IMAGE` and
`USB_MUSB_PIO_ONLY` are defaulted, `CIRCBUF` is selected) and the fragments name those four explicitly.

Each of the six roles was proven to reproduce the defconfig it replaced, symbol for symbol, apart from
the device tree: `build/uboot-prove-fragments.sh` (from `mainline/`), config targets only, no toolchain needed.

Details: `doku/30-uboot-aenderungen.md`, `doku/109-plan-layout-v3.md`, `doku/10-hardware.md`.
