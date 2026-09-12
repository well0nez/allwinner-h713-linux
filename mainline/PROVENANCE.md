# Provenance & licensing

This project integrates several upstream components and third-party work.
Respect the boundaries below — especially the redistribution ones.

## Components (submodules, our GitHub forks)

| Component | Upstream | License | Our changes |
|-----------|----------|---------|-------------|
| u-boot | Denx U-Boot | GPL-2.0+ | H713/HY200 SoC + board support (curated series) |
| arm-trusted-firmware | TF-A | BSD-3-Clause | `sun50i_h713` platform + keyed-wdog reset + PSCI cpu_on/suspend |
| sunxi-tools | linux-sunxi | GPL-2.0+ | H713 FEL support + fel_lib 16 KiB chunk fix |

Each fork carries a clean H713 commit series on top of a pinned upstream base,
intended to be upstreamable (H713/HY200 support) once validated.

## Kernel patches (`patches/kernel/`)

The bulk of the H713 driver support (CCU, pinctrl, MMC, USB PHY, PPU, LRADC,
board-mgr, cpu-comm, tvtop, decd, cedrus, …) originates from **well0nez**
(`local/allwinner-h713-linux`), GPL-2.0. These patches are carried here
**with attribution to well0nez**. Our own additions (arm64 DTS, arm64
defconfig, the `SUN20I_D1_R_CCU` arm64 Kconfig enablement) are marked as such
in the series.

## VA-API shim patches (`patches/libva-v4l2-request/`)

[bootlin/libva-v4l2-request](https://github.com/bootlin/libva-v4l2-request),
**MIT**, carried as a two-patch series on the pinned head of its unmerged
**PR #38** rather than vendored — see that directory's README for the base
commit and why `master` is the wrong starting point.

## DO NOT REDISTRIBUTE

- **Vendor boot0 / eGON blob** and the U-Boot `H713_EMMC_RECOVERY` tool that
  embeds it (`board/sunxi/h713_recovery.c`, `h713_vendor_boot0.h`). This is
  proprietary Allwinner code — it stays under the ignored `local/` directory,
  is excluded from repository history and the upstreamable series, and must
  not be pushed to public forks.
- **eMMC backups, BROM dumps, captures** (`local/h713-lab`, ~84 GB) —
  contain proprietary firmware; never commit or share.

## Toolchain

Built with LLVM (clang / ld.lld) — no aarch64 GCC required. Verified host-tool
versions are recorded in `config/toolchain.md`.
