# `mainline/patches/kernel/` - the kernel as a patch series

The kernel is not a fork. `mainline/build/build.sh kernel` fetches Linux 6.18.38 as a tarball (version and
sha256 pinned in `mainline/config/versions.env`), applies the patches of this directory in the order of
`series` with `patch -p1`, and builds with `board/hy200_qz713df_a1_defconfig`. It leaves in `mainline/build/out/`
the device tree of the board (`KERNEL_DTB` in `boards/<id>/board.env`), the two HY200 trees, and
`h713-kernel.fit`: the gzipped `Image` and the board's DTB, loaded and entered at `0x48000000`, in a
configuration named `conf-<dtb>`.

## Where things are explained

- [`docs/kernel-patches.md`](../../../docs/kernel-patches.md): the series, its sections, why the numbers are
  history and not order, how to add a patch, and the digest that names the kernel tree.
- [`PROVENANCE.md`](../../../PROVENANCE.md): who wrote what. Every patch carries its author in its `From:`
  line. `0001` - `0022` are well0nez' H713 driver series (GPL-2.0, `drivers/` and `include/dt-bindings/` only,
  so they apply to arm64 as well); cstenger's patches are taken byte for byte and keep his `From:`.
- `../zurueckgenommen/`: patches taken out of the series, each with the reason. `../vorschlaege/`: work in progress.

## Reading the arm64 base

A few facts that the first patches of the series take for granted:

- `0023` lets the D1 R_CCU build for `ARM64` too; without it R_PIO and the PPU power domains never come.
- `0024` brings the arm64 device trees: the shared `sun50i-h713.dtsi` and the two HY200 boards, with
  `secure-bl31@40000000` reserved for TF-A.
- `0025` - `0028`: the CPU clock, cpufreq and the core voltage, which is regulated through R_PWM on PL7.
- `0030`: the fan's supply is switched by PB5 as a GPIO hog (the three-cell form), not by a PWM.
- `0032`: the backlight is a pwm-backlight on PWM2/PB4; the brightness takes effect only once the panel is
  initialised.
- The Crypto Engine is described in the tree but not driven (the defconfig says why).
- `0160`, `0161`, `0181`, `0182`: one device tree per board.

Everything from `0168` on is described in `docs/kernel-patches.md`.

## Developer kernels

`board/*.config` are fragments laid over the defconfig for a diagnosis, never for an image:

```bash
KERNEL_CONFIG=debug mainline/build/build.sh kernel             # -> build/out/h713-kernel-debug.fit
KERNEL_CONFIG=netboot,debug mainline/build/build.sh kernel     # several, comma-separated
```

| Fragment | What for |
|---|---|
| `debug` | debugfs and dynamic debug back on (`/sys/kernel/debug/cpu_comm/call` and the like); the release has them off |
| `netboot` | the USB network drivers built in, so that an NFS root can come up before any module is loaded |

Two properties not to break: a fragment counts into the digest, so a developer kernel gets a tree of its own;
and the outputs carry the fragment names (`Image-<name>.gz`, `h713-kernel-<name>.fit`), so a developer FIT never
replaces the one the board boots. After `olddefconfig` the build checks the `.config` it is about to build
against every line of the fragments, because `olddefconfig` may drop a symbol without a word when a dependency
is missing.
