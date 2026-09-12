# H713 U-Boot to Linux/Debian Bring-up Review

> **Board naming (2026-07-18):** "HY200" = the bench board `HY200_QZ713DF_A1`; "HY310" refers to the projector, now correctly identified as `HY200_QZ713_V2`. This historical doc predates that correction. Its legacy `~/Projects/...` evidence paths were consolidated under the ignored `local/` directory; use the matching basename there.

> **Historical planning record:** the execution plan in this document has been
> superseded by [status.md](status.md) and [roadmap.md](roadmap.md). In
> particular, the project retained the factory GPT, completed the arm64 path,
> and now boots Debian standalone. Keep this file for the evidence and decision
> history, not as current instructions.


Date: 2026-07-14 (v2 — revised after independent review)
U-Boot branch: `h713-sun50iw12-dram`
Reviewed U-Boot commit: `7df83b95a364cf5a29ef5381db8c56211e83091b`

## Purpose

This note records the current state of the local Allwinner H713 port and the
remaining work necessary before concentrating on Linux and Debian.

Revision 2 incorporates an independent review and two decisions:

1. **Preserving the factory Android system and eMMC layout is no longer a
   goal.** The earlier "change nothing on the board" posture existed only to
   avoid bricking the board before recovery tooling existed. That tooling now
   exists and is hardware-proven (see *Recovery posture* below), so the plan
   moves to a clean, conventional storage layout.
2. **The Linux side is not greenfield.** A substantial mainline-based 32-bit
   H713 Linux port already exists at `~/Projects/allwinner-h713-linux`
   (22 patches on linux-6.16.7, a complete interrupt-annotated device tree,
   and subsystem bring-up docs), previously booted under the stock vendor
   firmware chain. The bring-up plan below reuses it rather than rebuilding
   SoC knowledge from scratch.

## Executive summary

The port is ready to begin Linux bring-up. Additional U-Boot features such as
CDC ECM/NCM, display, USB host, and secure boot are not prerequisites for the
first Linux shell.

The two gates before kernel work:

1. **Archive, then repartition.** Take a full 7.3 GiB eMMC image (only the
   first 4 MiB is currently saved), then migrate to a clean layout:
   U-Boot at the 128 KiB BROM fallback offset (sector 256), a conventional
   128-entry GPT, and a first-partition floor of 16 MiB to protect the raw
   environment at 4 MiB. The factory 26-entry GPT no longer needs preserving.
2. **Choose the first kernel path.** The fastest route is booting the
   existing, hardware-proven 32-bit zImage + DTS from the new arm64 U-Boot
   (the AArch32 boot path is already compiled in). An arm64 port of the same
   patches is the strategic follow-up, not a prerequisite.

## Recovery posture (why aggressive changes are now acceptable)

Every element of the recovery chain has been proven on this board:

- **Cold FEL entry works.** The entire DRAM bring-up ran over FEL, and the
  one-shot eMMC recovery SPL (commit `d293f44f77d`,
  `hy200_h713_recovery_defconfig` + `CONFIG_H713_EMMC_RECOVERY`) has
  repeatedly restored the board — including from a fully cold FEL entry —
  by rewriting the embedded vendor boot0 to eMMC ("wrote 64/64 RESTORED-OK").
- **A full U-Boot can be FEL-loaded**, giving the ACM/UART console, `ums`,
  `fastboot`, and raw `mmc write` — enough to rewrite any part of the eMMC
  regardless of its contents. This requires the locally patched sunxi-tools
  (`~/Projects/sunxi-tools`, H713 soc_info + FEL transfer fixes).
- **The BROM is mask ROM.** No eMMC write can remove FEL itself.

Additionally, the board has a **hardware FEL entry (button)** — the cold
FEL probes in the MMC gate-order investigation were button-entered. This
closes even the narrow residual vector of flashing an image with a *valid*
eGON/TOC0 checksum that hangs before any console: FEL remains reachable
regardless of eMMC contents. Standing mitigations, already practiced:

- Never flash a first stage to eMMC that has not first run via FEL (the
  established one-SPL-per-FEL-session test protocol).
- Keep the recovery SPL binary and the archived vendor boot0 available
  off-board.

EXT_CSD experiments (eMMC boot partitions) and repartitioning carry no brick
risk beyond this vector, since FEL does not depend on eMMC state.

## Hardware and software context

- SoC: Allwinner H713 (sun50iw12), four Cortex-A53 cores.
- Board identifies itself as `HY200 QZ713DF_A1 (Allwinner H713)`.
- DRAM: 1 GiB DDR3 using the locally derived H713 initialization path.
- Storage: 7.3 GiB eMMC, currently U-Boot device `mmc 1`.
- Firmware chain: sunxi SPL → TF-A BL31 → U-Boot proper (all local builds).
- **BL31 provenance:** local TF-A tree at `~/Projects/arm-trusted-firmware`,
  four H713 commits on upstream `347d1c164`:
  `e138fd968` (sun50i_h713 platform port), `c909a1122` (key-protected
  watchdog SYSTEM_RESET), `a8f85bee8` (PSCI `CPU_ON`), `47ee829f7`
  (PSCI `CPU_SUSPEND`). Build: `make PLAT=sun50i_h713 DEBUG=0
  BL31_IN_DRAM=1` with the clang/LLVM toolchain settings recorded in the
  project notes. Any reproduction of this chain must pin that tree.
- Debug transport: UART is the persistent/default U-Boot console; `run
  acm_mode` explicitly enables the CDC ACM console over the peripheral USB
  port. ACM, UMS, and fastboot use that one controller successively.
- Current U-Boot image is stored in the eMMC user area beginning at LBA 16;
  clean build `g8a601c1` is 844417 bytes (1650 sectors, ending at LBA 1665).
- Persistent U-Boot environment offset: `0x400000` (4 MiB, LBA 8192).

The current board configuration is `configs/hy200_h713_ddr3_defconfig`; the
selected device tree and runtime model use the matching HY200 QZ713DF_A1 name.

## Functionality already demonstrated

The following has been exercised on hardware:

- SPL initializes 1 GiB of DRAM and loads BL31/U-Boot from eMMC.
- TF-A PSCI `CPU_ON` starts all three secondary CPU cores (AArch64 callers);
  `CPU_SUSPEND` is implemented and advertised (entry proven, wake via GIC).
- PSCI system reset works (requires the keyed watchdog sequence, see below).
- The eMMC user area can be read and written from U-Boot.
- U-Boot environment load/save works at the configured raw offset.
- USB CDC ACM works as an opt-in console multiplexed with UART. A transition
  issued from ACM to `run fastboot_mode` was hardware-verified; the helper
  returns the console to serial-only mode when fastboot exits.
- USB Mass Storage has exposed the eMMC to the host and has been used to
  write and verify a U-Boot image.
- UART S-record/YMODEM loading works as an alternate update mechanism.
- Cold FEL recovery via the one-shot recovery SPL (see *Recovery posture*).

This is sufficient boot-loader functionality to begin kernel work.

## Storage layout

### Factory state (recorded for the archive; no longer a constraint)

The saved first-4-MiB image of the original eMMC reports a 26-entry GPT
(disk GUID `AB6F3888-569A-4926-9668-80941DCB40BC`): entry array LBA 2–8,
first usable LBA 73728 (36 MiB), last usable LBA 15269854, with Android
partitions (`bootloader_a/b`, `boot_a/b`, `env_a/b`, `super`, `UDISK`).
The reduced entry array exists so the factory boot0 at LBA 16 does not
collide with it. Note that 26 × 128 B = 3328 B is below the UEFI
specification's 16 KiB minimum entry-array size — which is exactly why
generic tools tend to "normalize" such tables to 128 entries, whose array
(LBA 2–33) would overwrite an image at LBA 16.

Since the Android system is being retired, this analysis is archival. It
matters only until the migration below is performed, and it documents why
the current LBA 16 image and a conventional GPT cannot coexist.

### Target layout (recommended)

Move U-Boot to the BROM's alternate boot offset and use a completely
conventional GPT:

- **U-Boot image at sector 256 (128 KiB).** Per `doc/board/allwinner/sunxi.rst`,
  every Allwinner SoC since the H3 (2014) checks sector 256 after sector 16,
  specifically because it lies beyond a full 128-entry GPT.
  **Confirmed for the H713 by static analysis (2026-07-14):** in the BROM
  dump (`~/Projects/h713-lab/captures/brom/h713-brom-dump-20260712.bin`,
  base 0x0, ARM32), the candidate-offset function at `0x3e58` selects start
  sector `0x10` for attempt 0 (`0x3e9c`), sector `0x100` for attempt 1
  (`0x3ec0`), and returns failure for attempt ≥ 2; each candidate header is
  read into SRAM `0x104000` and validated, with one retry.
- **Standard 128-entry GPT** (entry array LBA 2–33, clear of sector 256).
- **First partition at ≥ 16 MiB.** The raw environment at 4 MiB (LBA 8192)
  is protected today only by the factory table's 36 MiB first-usable-LBA.
  Any conventional layout must impose this floor explicitly, or the default
  1 MiB first-partition alignment will overwrite both the environment and,
  at 128 KiB, U-Boot itself. This applies equally to MBR layouts.

Migration order (each step FEL-recoverable):

1. Write the (FEL-proven) image at sector 256 alongside the existing copy.
2. Invalidate the eGON/TOC0 header at LBA 16 and cold-boot to prove the
   BROM actually falls back to sector 256.
3. Only then write the new GPT.

### Alternatives (recorded, not recommended)

- **Keep LBA 16 and use a non-colliding GPT.** `sfdisk` (util-linux ≥ 2.36)
  supports `table-length: 26` and `first-lba:` headers; `sgdisk` can relocate
  the main entry array above the firmware region (`--move-main-table`,
  formerly `-j`). Workable, but retains a nonstandard table that generic
  tools may still normalize.
- **eMMC hardware boot partitions — likely unsupported by the BROM.** The
  eMMC has two 4 MiB boot partitions, currently disabled
  (`EXT_CSD[179] = 0`), and `mmc partconf`/`mmc bootbus` are available
  (`CONFIG_SUPPORT_EMMC_BOOT=y`). However, a scan of the BROM dump found no
  CMD6 `PARTITION_CONFIG` switch argument (`0x03B3xxxx`) anywhere, i.e. no
  evidence the BROM can even select a boot partition to read from. Treat
  this option as unavailable unless deeper BROM analysis proves otherwise.
- **MBR.** Avoids the entry-array collision but not the first-partition
  floor issue, and gives up GPT/UEFI compatibility for no benefit over the
  sector-256 migration.

### Partitioning tool cautions

- Avoid `parted` and the Debian installer's partman (libparted) on this disk;
  the plan below installs Debian with `mmdebstrap`, sidestepping the
  installer entirely.
- After the migration, the only invariants any tool must respect are:
  do not touch LBA 0–33 metadata regions incorrectly (normal GPT rules),
  and keep partitions at or above the 16 MiB floor.

### Required precautions (before repartitioning)

1. **Full 7.3 GiB eMMC image** — the current backup covers only the first
   4 MiB. Once the disk is repartitioned this image is the sole source of
   the vendor partitions and anything not yet harvested from them
   (Wi-Fi/BT MAC provisioning, DRM keys, any factory optical/keystone
   calibration). Record SHA-256 hashes for the full image, the first
   36 MiB, and the known-good U-Boot image.
2. Cold FEL recovery drill — **already satisfied** (see *Recovery posture*).
3. Keep the recovery SPL, vendor boot0, and patched sunxi-tools archived
   off-board.

## The existing Linux port

`~/Projects/allwinner-h713-linux` contains a mainline-based port previously
run on this board under the *stock* vendor firmware chain:

- 22 patches against linux-6.16.7: H713 CCU driver, pinctrl (PIO and R-PIO),
  MMC (`v5p3x`), USB PHY quirk, LRADC, PPU power domains, 8-channel PWM,
  CIR, Cedrus/VE clocks, IOMMU decoupling, and board-specific misc drivers
  (keystone motor, MIPS display co-processor loader, TVTOP, DECD, NSI,
  CPU-comm IPC).
- A complete board DTS (`dts/sun50i-h713-hy310.dts`) with GIC-400 at
  `0x03020000`, PSCI 0.2 SMC method, `enable-method = "psci"` on all four
  A53s, architectural-timer PPIs, and 41 `interrupts` properties covering
  the peripherals. This answers the GIC/interrupt questions the U-Boot-side
  DTS leaves open.
- Subsystem bring-up documentation (`docs/`): boot, eMMC, UART, USB, display
  (including MIPS `display.bin` firmware loaded to `0x4b100000` *before* the
  kernel), audio, Wi-Fi/BT, thermal, power.

Constraints inherited from the stock chain (per `docs/BOOT.md`), which the
new U-Boot removes or must replicate:

- The stock BL31 entered the kernel in **AArch32** (spsr `0x1d3`); the port
  is built `ARCH=arm` as a zImage with appended DTB (the stock U-Boot could
  not load a separate DTB and only accepted Android boot v3 images). None of
  these packaging constraints apply under the new U-Boot.
- The stock chain ran `usb start` before the kernel because the kernel
  depends on prior USB PHY initialization. The current
  `CONFIG_PREBOOT="usb start"` (a sunxi Kconfig default) may therefore be
  **load-bearing** for this kernel, not cosmetic — do not remove it until a
  kernel boot without it has been tested.
- The MIPS display firmware load at `0x4b100000` must move into the new boot
  flow (a FIT `loadables` entry is the clean mechanism).

One known discrepancy to fix: `docs/BOOT.md` describes the watchdog at
`0x02051000` as `sun6i-a31-wdt` layout, but the U-Boot bring-up proved on
hardware that it is the key-protected layout (key `0x16aa0000`, CFG +0x10,
MODE +0x14 — commit `850840ede26` and the TF-A reset fix). The Linux DTS
node should use the keyed compatible (Linux supports this layout as
`allwinner,sun20i-d1-wdt`); verify the driver services it correctly.

## Kernel path decision

### Path A (recommended first): boot the existing 32-bit kernel from the new U-Boot

Everything on the Linux side is already proven on this hardware; only the
handoff is new. Mechanics:

- U-Boot's AArch32 boot path is already compiled in:
  `CONFIG_ARM64_SUPPORT_AARCH32` is default-y (`arch/arm/Kconfig:609`), and
  `bootm` performs the EL2→AArch32 SVC transition (`ES_TO_AARCH32` in
  `arch/arm/lib/bootm.c`) — the same entry state the stock BL31 produced.
- Package zImage + DTS (now loadable separately — drop
  `CONFIG_ARM_APPENDED_DTB`) + initramfs + `display.bin` (as a `loadables`
  entry at `0x4b100000`) in a FIT with `arch = "arm"`.
- **SMP is the one open verification item:** secondary bring-up becomes a
  PSCI `CPU_ON` call from an *AArch32* caller into our BL31. TF-A's generic
  PSCI layer supports 32-bit callers, but the local H713 `CPU_ON`
  implementation has only been exercised from AArch64. Test early; if it
  misbehaves, boot `maxcpus=1` while fixing BL31.
- Debian **armhf** runs directly on this kernel.

### Path B (strategic follow-up): arm64 port

The driver patches are architecture-neutral (clk, pinctrl, mmc, phy compile
unchanged on arm64); the DTS port is mechanical (arm64 skeleton, same
peripherals, PSCI unchanged — our BL31 already serves AArch64 callers,
proven by U-Boot). The costs are re-validating every subsystem, foremost
display/audio/Wi-Fi, and redoing the out-of-tree module builds. Rewards:
Debian arm64 and alignment with any future upstreaming (upstream would
expect an arm64 DT under `arch/arm64/boot/dts/allwinner/`, structurally
modeled on `sun50i-h616.dtsi`).

Decide armhf-vs-arm64 for the durable system after Path A proves the
handoff; both share the same storage layout, extlinux/FIT infrastructure,
and U-Boot.

### The U-Boot-side DTS

`dts/upstream/src/arm64/allwinner/sun50i-h713-hy310.dts` remains a
U-Boot-only hardware description (no GIC, no interrupts, provisional fixed
regulators, and `mmc-ddr-1_8v`/`mmc-hs200-1_8v` capabilities that U-Boot
itself doesn't use — runtime is High Speed 52 MHz). It should not be handed
to Linux. Once a Linux-side arm64 DT exists (Path B), sync it back into
U-Boot rather than maintaining divergent descriptions. The Linux DTS should
start without DDR/HS200 capabilities until voltage switching and tuning are
validated; the fixed 3.3 V/1.8 V regulators should be checked against the
vendor DTB/schematics before higher-speed modes are enabled.

## Existing U-Boot boot capabilities

Generating `.config` from `hy200_h713_ddr3_defconfig` confirms the build
already enables:

- standard boot (`CONFIG_BOOTSTD`), extlinux boot method, `bootflow`,
- `booti` (arm64 Image) and `bootm` with the AArch32 path (see above),
- ext4 and FAT commands,
- EFI loader and EFI boot manager,
- USB Mass Storage and fastboot targeting eMMC device 1 (both via sunxi
  Kconfig defaults rather than explicit defconfig lines),
- driver-model watchdog support and the `wdt` command (auto-servicing
  `CONFIG_WATCHDOG` deliberately off — nothing arms the watchdog unless
  requested, so no accidental armed handoff to Linux), and
- persistent MMC environment storage.

The runtime EFI errors about a missing system partition are not a
kernel-bring-up blocker; an ESP and persistent EFI variables are unnecessary
for the first boot. The `No USB controllers found` message from
`CONFIG_PREBOOT="usb start"` is harmless — but see the note above before
removing the preboot command, since the 32-bit kernel may rely on the PHY
initialization it performs.

Remaining pre-`booti`/`bootm` check: confirm `kernel_addr_r`, `fdt_addr_r`,
and `ramdisk_addr_r` defaults are sane for 1 GiB at `0x40000000` and don't
collide with the `0x4b100000` display-firmware region (one `printenv` at the
prompt).

## Recommended first Linux boot path

### Phase 1: direct FIT `bootm` smoke test (Path A kernel)

Load a FIT containing the 32-bit zImage, the existing H713 DTS, a small
BusyBox initramfs (armhf), and `display.bin` as a loadable, then `bootm`.

Success criteria:

- Kernel reaches the UART console (`earlycon`; keep UART attached — it is
  the only reliable transport for the earliest messages).
- GIC and architectural timer initialize without errors.
- All four CPUs come online through PSCI **from the AArch32 kernel** (the
  key new-chain test; fall back to `maxcpus=1` if BL31 needs work).
- The kernel sees the expected usable RAM without corruption.
- eMMC works reliably at a conservative speed.
- The initramfs reaches an interactive shell.
- Reboot lands back in U-Boot (exercises the keyed-watchdog reset path from
  a 32-bit caller).

### Phase 2: extlinux from eMMC

After the storage migration, place the boot artifacts on a filesystem in the
new layout and boot via `bootflow scan`. Note extlinux.conf's `KERNEL` line
can point at the FIT (`path#conf-name` syntax), which keeps the
display-firmware loadable in play — plain KERNEL/FDT/INITRD lines cannot
load the extra blob.

### Phase 3: Debian root filesystem

Create a minimal Debian root filesystem (armhf for Path A) with `mmdebstrap`
or `debootstrap` on the host, and boot it with the same kernel/FIT/extlinux
path. This avoids the Debian installer's partitioning entirely. Keep it
small: ext4 root, serial login, SSH once networking works, no desktop.

## Console implications

The CDC ACM console does not continue through the kernel handoff; Linux
resets and re-enumerates the USB controller when its own MUSB/gadget drivers
bind. Keep UART attached for kernel work. Later, Linux can provide `ttyGS0`,
CDC ECM/NCM + SSH, or a composite gadget — none of which replace UART
`earlycon` during the failure-prone phase.

## Additional validation worth doing

- ~~Verify the sector-256 BROM fallback in the captured BROM disassembly~~
  — done 2026-07-14, confirmed (see *Target layout*); boot-partition
  support not found.
- Test PSCI `CPU_ON`/system-reset from an AArch32 caller against the local
  BL31 (Phase 1 covers this).
- Confirm Linux's keyed-watchdog driver (`sun20i-d1-wdt` compatible)
  services the H713 watchdog; fix the stale `sun6i-a31-wdt` claim in the
  Linux port's DTS/docs.
- Exercise a bounded DRAM test and repeated eMMC read/CRC cycles.
- Leave cpuidle states out of the Linux DT initially even though BL31
  advertises `CPU_SUSPEND`; add and validate them as a separate item.

## Features that can wait

- CDC ECM/NCM or composite gadgets in U-Boot.
- USB host support; display/GPU/video/audio/Wi-Fi/BT (the Linux port's
  existing subsystem work re-enters here after the first shell).
- eMMC HS200/HS400.
- Persistent EFI variables and a UEFI-first boot flow.
- Secure/verified boot; A/B updates, boot counting, rollback.
- The arm64 kernel port (Path B), if armhf proves sufficient.

## Work sequence

1. Take and hash the full 7.3 GiB eMMC image (the point of no return for
   the factory system is step 5, but the archive must exist first).
   *In progress 2026-07-14 (UMS + udisks OpenForBackup →
   `~/Projects/h713-lab/captures/emmc/emmc-full-20260714.img`).*
2. ~~Statically verify the sector-256 fallback in the BROM dump~~ — done,
   confirmed (function `0x3e58`: sector 16 then sector 256).
3. Build the Path A FIT (zImage + DTS + initramfs + display.bin) and prove
   the kernel handoff from the current layout — no repartitioning needed
   for this test; artifacts can be loaded over UMS/UART/FEL.
4. Validate SMP (AArch32 PSCI), reset, RAM, and conservative eMMC in the
   initramfs.
5. Migrate storage: U-Boot to sector 256, invalidate LBA 16, prove the
   cold boot, write the conventional GPT (first partition ≥ 16 MiB).
6. Create the boot filesystem, add extlinux.conf (FIT syntax), verify
   `bootflow scan` boots unattended.
7. Install Debian armhf via `mmdebstrap`; serial login, then SSH.
8. Re-enable the Linux port's subsystem work (display, audio, Wi-Fi) on the
   new chain.
9. Add Linux gadget serial/network to reduce UART dependence.
10. Optional strategic items: arm64 kernel port; HY200/HY310 naming cleanup
    before any upstream submission. (Firmware in eMMC boot0 is off the
    list — the BROM shows no boot-partition support.)

## Resolved review questions

Answers to the open questions from v1 of this document:

1. *LBA 16 vs 128-entry GPT collision* — confirmed correct (array LBA 2–33
   covers LBA 16); root cause is the UEFI 16 KiB minimum entry-array size.
2. *Keep 26-entry GPT vs eMMC boot0* — neither: migrate to sector 256 with
   a conventional GPT. Factory-table preservation is moot now that the
   Android system is being retired.
3. *Tool behavior with 26-entry GPTs* — `sfdisk` can preserve/recreate them
   (`table-length:` header); `sgdisk` can relocate the entry array
   (`--move-main-table`); `parted`/partman normalize and should be avoided.
   Irrelevant after the migration.
4. *MBR preferable?* — No; it doesn't protect the 4 MiB environment (the
   real remaining hazard is the first-partition floor) and loses GPT
   compatibility for nothing.
5. *Best upstream starting point* — structurally `sun50i-h616.dtsi` for an
   arm64 DT; the H713's CCU is D1-like (proven in U-Boot). In practice the
   existing 32-bit port supersedes the question for bring-up.
6. *GIC registers and interrupts* — already established: GIC-400 at
   `0x03020000` with full per-peripheral SPI assignments in
   `~/Projects/allwinner-h713-linux/dts/sun50i-h713-hy310.dts`.
7. *Compatible strings needing real drivers* — the port's 22 patches answer
   this; the one known correction is the watchdog (keyed layout, not
   `sun6i-a31-wdt`).
8. *Provisional fixed regulators* — keep 3.3 V; treat the 1.8 V vqmmc rail
   as unverified and gate DDR/HS200 modes on confirming it.
9. *Missing `booti`/`bootm` prerequisites* — only the `printenv` check of
   the `*_addr_r` defaults against the `0x4b100000` display-firmware region.
10. *Long-term layout retaining FEL* — sector 256 + conventional GPT; FEL
    is BROM-resident and unaffected by any eMMC layout.

## References

- Existing Linux port: `~/Projects/allwinner-h713-linux` (patches, DTS,
  `docs/BOOT.md` et al., `output/` prebuilt artifacts)
- Local TF-A tree: `~/Projects/arm-trusted-firmware` (H713 platform,
  commits `e138fd968`, `c909a1122`, `a8f85bee8`, `47ee829f7`)
- Patched sunxi-tools (H713 FEL): `~/Projects/sunxi-tools`
- BROM dump and MMC gate-order evidence: `~/Projects/h713-lab/captures/brom/`
- U-Boot board DT (U-Boot-only):
  `dts/upstream/src/arm64/allwinner/sun50i-h713-hy310.dts`
- Board configuration: `configs/hy200_h713_ddr3_defconfig`
- Allwinner boot offsets and eMMC boot partitions:
  `doc/board/allwinner/sunxi.rst`
- Linux arm64 boot protocol:
  <https://www.kernel.org/doc/html/latest/arch/arm64/booting.html>
- U-Boot extlinux boot method:
  <https://docs.u-boot.org/en/stable/develop/bootstd/extlinux.html>
- Debian mmdebstrap: <https://manpages.debian.org/mmdebstrap>
