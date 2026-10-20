# mainline/

The sources, patch series and build scripts for the open boot chain and the Linux kernel of the H713 boards.
Assembling the image, the installer and everything that runs on the device live elsewhere (`release/`,
`installer/`, `rootfs/`, `userspace/`); they call into this directory.

| Path | What is there |
|---|---|
| `external/` | Three git submodules, each a fork under the same account: `u-boot`, `arm-trusted-firmware`, `sunxi-tools`. Their commits are also mirrored as patch files in `../uboot-h713/` and `../tfa-h713/` |
| `patches/kernel/` | The kernel series: the numbered patches (a letter suffix is a follow-up placed behind the patch it corrects), the list `series` that fixes their order, and `board/` with the defconfig and the config fragments |
| `patches/aic8800/` | The series applied to Radxa's AIC8800 tree, the Wi-Fi and Bluetooth driver |
| `patches/zurueckgenommen/` | Patches that were withdrawn from the series, with the reason |
| `patches/vorschlaege/` | Work that is not in the series (yet): one folder per topic with drafts, findings and test plans; finished ones sit in `_erledigt/` |
| `modules/aic8800/` | The Wi-Fi and Bluetooth driver directories (`aic8800_bsp`, `aic8800_btlpm`, `aic8800_fdrv`) and the firmware checksum list; its own README says where the build takes the driver from |
| `build/` | `build.sh` (TF-A, U-Boot, kernel and the Wi-Fi modules), `uboot-build.sh`, and `uboot-prove-fragments.sh`, which the board check runs. Everything else that appears here is build output and not tracked |
| `config/` | `versions.env`, the pinned versions of every source, and a note on the toolchain |
| `tools/` | The build of the OpenRISC compiler and a few small programs for the device; see [tools/README.md](tools/README.md) |

How to build: [BUILDING.md](../BUILDING.md) and [docs/build-container.md](../docs/build-container.md); builds run in the
`h713-build` container, not on the host. What each kernel patch does and in which order they apply:
[docs/kernel-patches.md](../docs/kernel-patches.md). Who wrote what, which parts come from other people's
trees and which parts are left out on purpose: [PROVENANCE.md](../PROVENANCE.md). Which boards exist and how
they differ: [docs/hardware.md](../docs/hardware.md) and `../boards/`.
