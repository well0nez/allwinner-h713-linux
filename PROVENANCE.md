# Provenance

Who made what, where it comes from, and what is deliberately absent.

## The kernel series

`mainline/` is a **git subtree** of [cstenger/allwinner-h713-mainline](https://github.com/cstenger/allwinner-h713-mainline)
at commit `8860991`, with full history - you can `git log` any of his commits here. On top of it,
`mainline/patches/kernel/series` carries 140 patches in fifteen sections:

| Origin | Patches | Note |
|---|---|---|
| well0nez, via cstenger's `main` | 21 (`0001` - `0022`) | **the H713 driver series** - CCU, pinctrl, MMC, USB PHY, PWM, LRADC, board manager, cpu_comm, tvtop, decd. Written here, carried in his tree with attribution, six of them adapted from 6.16 to the pinned kernel. Byte-identical to his tree |
| cstenger, `main` | 24 (`0023` - `0048`; `0040` retired 15.09., see `zurueckgenommen/`) | the arm64 side built around that series: DTS, defconfig, boot chain, cpufreq. Byte-identical, verified by comparison |
| cstenger, branch `h713-display-video-path` | 17 (`0051` - `0086`) | byte-identical; scanout, DECD, IOMMU, MMC, video plane |
| well0nez | `0049`, `0091` - `0159` | ARISC, cpu_comm, HDMI input, audio, motor, board manager, Wi-Fi |
| well0nez, follow-ups | `0005a`, `0013a`, `0014a`, `0014b`, `0024a` - `0024d`, `0078a`, `0136a`, `0136c` | small fixes placed directly after the original they touch, so the original stays byte-identical. `0013a` carries three decd corrections from cstenger's branch; `0005a` (USB PHY SIDDQ), `0136a` and `0136c` (HDMI hot plug) are ours, 15./16.09.; `0014b` and `0024d` are the msgbox's three interrupt lines, 16.09. |

cstenger says the same in his own `PROVENANCE.md`: "the bulk of the H713 driver support … originates
from well0nez". The direction of the debt runs both ways - his arm64 work is what made the 6.18 line
possible here - which is why this repository vendors his tree with its full history instead of copying
files out of it. The follow-ups marked as pull-request candidates in `doku/116` are meant to go back to
him.

The Wi-Fi driver is a second series, `mainline/patches/aic8800/`: nine patches on Radxa's `aic8800` tree
(commit `df4c783b`, vendor release `2026_0123`). `0008` - `0010` are cstenger's `0007` - `0009` from the same
branch, renumbered and byte-identical but for the phantom `CONFIG_DEBUG_FS_AIC` that `0010` compiles in; the
rest is ours. That directory's README names each patch and its origin.

## Firmware components

Three git submodules under `mainline/external/`, pinned to forks under the same account:

| Component | Branch | Why a fork |
|---|---|---|
| `u-boot` | `h713-hy310` | 77 commits on top of cstenger's `h713` (base `8fe568c`): CCU tables, USB PHY, the MIPS display bring-up with the boot logo, the power gate, the boot paths, the eMMC at HS200 with DMA in U-Boot and in the SPL |
| `arm-trusted-firmware` | `sun50i-h713` | BL31 for this SoC, plus entering the boot gate on `SYSTEM_OFF` |
| `sunxi-tools` | `h713` | `sunxi-fel` with the EL3 trap door the H713 needs to return to FEL |

`uboot-h713/` mirrors the U-Boot commits as patch files (`git format-patch` from the fork, `SERIES.txt`
names base, head and count; last regenerated 16.09.2026 at `4c7e49b`), for reading without cloning. The
build uses the submodule, not the mirror.

## What is *not* in this repository, on purpose

**No vendor firmware, no keys, no dumps.** The display firmware (`display.bin`), the ARISC firmware, the
Wi-Fi firmware and the picture tables are the vendor's, not ours to redistribute - they are the same files
on every device of this model, and every owner already has them. The image ships placeholders;
`h713-extract` fills them from the user's own dump during installation. The material in secure storage -
HDCP keys, MAC addresses, serial number - is a different matter again: it exists once, per device, and
copying someone else's would be both illegal and useless.

The same applies to the reverse-engineering material - stock firmware images, disassembly databases,
captures. It exists, it is what this port was built from, and it stays on private disks. Every push is
preceded by `release/sperr-scan.py`, which fails the release if a vendor blob, a key, a dump or an image
has found its way into the tree.

## Licences

**Code: GPL-2.0** ([LICENSE](LICENSE)) - the kernel patches, the U-Boot changes and the drivers inherit it
from their upstreams and could not be anything else; the tools in `installer/`, `rootfs/`, `userspace/` and
`release/` are under it by choice, so the whole tree answers to one licence.

**Documentation: CC BY-SA 4.0** ([LICENSE.docs](LICENSE.docs)) - `docs/`, `doku/` and the Markdown at the
top level: share it, adapt it, credit **well0nez**, keep the same licence.

No file here is derived from vendor source code. The drivers were written from measurements, disassembly
of the shipping firmware, and the behaviour of the hardware.

## Reading the history

- `legacy` branch and tag `legacy-arm32-2026-08`: the 32-bit BSP era of this project, frozen. Different
  kernel, different approach; kept because the reverse-engineering notes in it are still valid.
- `doku/`: the German working journal, dated. Nothing in the English documentation claims anything that
  is not written down there with a date and a measurement.
