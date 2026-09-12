# H713 mainline bring-up

Mainline firmware and Linux for the **Allwinner H713 (sun50iw12)** SoC — a
fully open boot chain (U-Boot SPL → TF-A BL31 → U-Boot → Linux) with a
64-bit Debian userland, replacing the vendor Android stack.

> **Status (2026-07-19):** arm64 Debian 13 on Linux **6.18.38 LTS** boots from
> eMMC to a root login, 4-core SMP, HS400 eMMC — and boots **standalone**
> (power-on → Debian, no host). The signed key-only rootfs, growfs, serial
> recovery, modules, and sshd are hardware-verified on the HY200 bench board.
> 32-bit Linux also boots (single-core). See [docs/status.md](docs/status.md)
> for what works and [docs/roadmap.md](docs/roadmap.md) for what's next.

## Hardware

Two physically different H713 boards exist — **know which one you have**:

| Board | Silkscreen | DRAM | Notes |
|-------|-----------|------|-------|
| **Bench** | HY200_QZ713DF_A1 | **DDR3** (Samsung K4B2G, 1 GiB) | All FEL/bring-up runs on this one |
| **Projector** | HY200_QZ713_V2 | **LPDDR3** (1 GiB) | Inside a projector; do not risk it |

Feeding the wrong DRAM parameters trains "OK" but reads hang. Always name the
board a test ran on. Neither board has an SD slot — boot media is **eMMC or
FEL only**. There is a hardware **FEL button** (recovery vector).

## Boot chain

```
BROM → U-Boot SPL (DRAM init) → TF-A BL31 (EL3, @0x40000000 in DRAM)
     → U-Boot proper (AArch64 EL2) → FIT (bootm):
         arch=arm64  → EL1 AArch64  (native; SMP works, 4 cores)
         arch=arm    → EL1 AArch32  (via el2_to_aarch32; single-core)
```

## Layout

- `external/` — the three firmware components as git submodules pinned to our
  GitHub forks (curated H713 commit series on top of upstream):
  `external/u-boot/`, `external/arm-trusted-firmware/`, `external/sunxi-tools/`.
  Fetch them with `git submodule update --init`.
- `patches/kernel/` — kernel patch series (well0nez H713 drivers + our arm64
  additions), applied to a pinned mainline tag. See
  [patches/kernel/README.md](patches/kernel/README.md).
- `tools/` — hardware test/flash tooling (`serial/` console + FIT loaders,
  `rootfs/` Debian build helpers).
- `docs/` — project documentation (build, flash, status, gotchas). Docs live
  here, **not** in the submodules.
- `build/` — reproducible build orchestrator (`build.sh`).
- `config/` — pinned version + toolchain manifest (`versions.env`, `toolchain.md`).
- `local/` — ignored local-only captures, historical research/build trees, and
  proprietary recovery material. It is part of the workspace, never Git.

## Quick start

```
git clone --recurse-submodules <this repo>       # or: git submodule update --init
# host tools (Arch/CachyOS): see config/toolchain.md
build/build.sh all              # BL31 -> U-Boot -> kernel -> images, into build/out/
build/build.sh uboot            # or a single stage; BOARD=ddr3 (default) | lpddr3
tools/rootfs/build.sh --ssh-key ~/.ssh/id_ed25519.pub  # signed Debian + modules
```

See [docs/build.md](docs/build.md) for the underlying recipes and
[docs/flash.md](docs/flash.md) for writing images to the board.

## Gotchas (read before touching hardware)

- **Consoles/transfers:** hardwired UART (`ttyUSB0`) is the safe U-Boot default
  and the only console that survives kernel handoff. Run `run acm_mode` to opt
  into the faster USB-CDC console (`ttyACM*`, resolve by USB VID `1f3a`); it is
  ~15× faster for bulk loads. Stashing large images on eMMC is faster still.
- **One USB controller:** ACM, UMS, and fastboot are successive gadget modes,
  not simultaneous interfaces. `run fastboot_mode` first returns all consoles
  to UART, starts fastboot, and returns to UART when fastboot exits. It is safe
  to issue as one line from either UART or ACM. Close stale host device handles
  and resolve the new USB device after every transition; power-cycle the board
  if the host retains a stale gadget identity across a reset.
- **fastboot buffer is 32 MiB** → large images must be Android-sparse
  (`img2simg`); the host tool chunks them.

For the full set of driver-level findings, silicon quirks, and the dead-ends
behind the current design, see [docs/bringup-notes.md](docs/bringup-notes.md).

See [docs/status.md](docs/status.md) for what works and what's next.
