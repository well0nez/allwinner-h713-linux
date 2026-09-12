# H713 bring-up notes — hard-won findings & dead-ends

Distilled technical lessons from the H713 (sun50iw12) U-Boot/TF-A/Linux
bring-up: the non-obvious gotchas, the silicon quirks, and the *wrong turns*
that the final curated commit series no longer shows (curation keeps the fix,
not the dead-end). Preserved here so the knowledge survives independent of git
archaeology.

- Where the real code lives: curated forks `external/u-boot@h713`,
  `external/arm-trusted-firmware@sun50i-h713`, `external/sunxi-tools@h713`.
  Commit SHAs below are the *pre-curation* hashes from the original working
  tree; find the equivalent by subject line on the curated branches.
- Deeper FEL / DRAM-ABI / SPL-sizing detail: [reference/h713-fel-notes.md](reference/h713-fel-notes.md).
- Planning / storage-layout / boot-path decisions: [bringup-readiness.md](bringup-readiness.md).

---

## SoC identity: H713 ≈ D1 (sun20i), **not** H616

Nearly every block reuses the Allwinner **D1 (sun20i)** register layout, so the
early H616-derived scaffolding was a dead end and got retired. Bind to D1
tables, not H616:

- **CCU** — D1 register layout. MMC clk/BGR at `0x830`/`0x84c`, USB at
  `0xa70`/`0xa74`/`0xa8c` (OTG gate bit 8 / reset bit 24, live-verified over
  FEL and from the prompt), UART BGR at `0x90c`. → match
  `allwinner,sun50i-h713-ccu` to the D1 gate/reset tables, default
  `CLK_SUN20I_D1` on for the H713 machine so DM consumers (MMC, MUSB, PHY) get
  real clock/reset handles. *(pre-curation `3a86da3`)*
- **DRAM controller** — MCTL COM at `0x04810000` + a combined controller/PHY
  block at `0x04820000`, using the D1 DRAMTMG/PITMG/PTR/RFSHTMG layout — **not**
  the H616 layout. The driver is a vendor-sequence replay of the stock BT0
  (libdram V1.18). *(pre-curation `0fd8b99`)*
- **R-CCU** — reuses the D1 R-CCU (`SUN20I_D1_R_CCU`). For the arm64 *kernel*,
  `ARM64` had to be added to that driver's Kconfig `depends` (upstream gated it
  to `MACH_SUN8I || RISCV`) before R-PIO / PPU power domains would probe.
- **Watchdog** at `0x02051000` — sun55i-a523 **keyed** layout (see below).

## The reset-before-gate silicon rule (SMHC *and* MUSB)

The single most important H713 quirk. On sun50iw12, a module whose **bus clock
gate opens while it is still held in reset** locks up its bus interface
*permanently*: the first register access (e.g. `0x0402x000` for SMHC) hangs the
CPU, and deasserting the reset afterwards does **not** recover the block —
only a power cycle does. The BROM brings controllers up in the opposite order.

**Rule: deassert reset first, then open the clock gate.** Applied H713-conditionally
so other SoCs keep the historical gate-then-reset order.

- SMHC / MMC — `mmc: sunxi` init, both legacy/SPL path and DM probe *(`382bc5b`)*.
- MUSB / USB-OTG — release OTG reset before the bus gate (`0xa8c`) *(`2a27ec5`)*.

Diagnosed by FEL register probing from a cold power-on before writing any code.

## Watchdog — keyed layout, and why it hung the boot

- Layout is **key-protected sun55i** (CTRL `+0x0c`, CFG `+0x10`, MODE `+0x14`,
  key `0x16aa` in bits `[31:16]`). Unkeyed writes are **silently ignored**.
- **Dead-end:** the DTS first claimed the H6/sun6i layout. `CONFIG_WATCHDOG`
  then hung pre-relocation — `init_func_watchdog_init()` fires right after
  `show_board_info()`, and the sun6i driver poked the wrong registers. The
  last console line was `Model:` and nothing more. Had to disable WATCHDOG/WDT
  entirely to get a prompt *(`0e5dc8b`)* until the binding was fixed.
- **Fix:** `compatible = "allwinner,sun55i-a523-wdt"` *(`850840e`)*, then
  re-enable `CONFIG_WDT` + `CONFIG_CMD_WDT` *(`bf00013`)*. `wdt expire` resets
  the board; same keyed layout the BL31 PSCI `SYSTEM_RESET` uses.
- **Timeout encodings:** short encodings fire (3 s = `0x3`); some longer ones
  are invalid on H713 (16 s = `0xB`, 10 s = `0x8`) and silently don't arm — an
  "armed watchdog never fires" symptom that was a bad encoding, not dead hardware.
  Use `wdt expire` (timeout 0 + kick) or a 3 s arm as self-recovery insurance.

## MMC / eMMC

- U-Boot's `sunxi_mmc` DM probe **derives the CCU base from the node's
  `clocks` entry [1]** (there is no separate sunxi clock driver at that point).
  Pointing the mmc nodes at the bare `osc24M` fixed clock made *every* probe
  fail `-ENOENT` and left U-Boot proper with **no MMC devices at all**.
  Reference the `ccu` node instead. *(`96bc4c9`)*
- **`mmc0` is disabled deliberately.** neither HY200 board (QZ713DF_A1 / QZ713_V2) has an SD slot, and a cold
  `mmc0` probe bus-hangs in `sunxi_mmc_reset()` because nothing in the DM path
  opens the SMHC0 gate — the eMMC only works because the SPL already warmed its
  controller. eMMC is **`mmc1`** (`mmc@4022000`), HS400, 26-partition Android GPT.

## Environment storage

- `ENV_IS_IN_FAT` pointed at the (non-FAT) `bootloader_a` partition and failed
  every boot. Moved to **raw eMMC at 4 MiB** — the gap between our boot image
  (<1 MiB at 8 KiB) and the vendor boot package (12 MiB); the lowest GPT
  partition starts at 36 MiB. With `boot_targets=mmc1` saved, boot-to-prompt
  drops from ~90 s of BOOTP/PXE retries to ~10 s. *(`bf00013`)*
- `mmc write` block count must **round up** (e.g. 844977 B = `0x673` blocks,
  not `0x672`); `cmp.b` caught a truncated tail otherwise.

## AArch32 kernel handoff (`el2_to_aarch32`)

U-Boot runs in **AArch64 EL2** (TF-A owns EL3), so `armv8_switch_to_el2()`
never takes its EL3 path and the generic weak `armv8_el2_to_aarch32` falls
through as a bare `RET` — a 32-bit kernel is then entered while still in
AArch64 and faults immediately.

- **Do not** reuse `armv8_switch_to_el1_m`: it programs SCTLR_EL1 with the
  AArch64-view RES1 bits 28/29, which read as **TRE/AFE** in the AArch32 view
  and scramble memory attributes (TEX remap with uninitialized PRRR/NMRR) the
  instant the OS enables its MMU. This caused the "silent kernel" for days.
- **Fix:** hand over the AArch32 reset state TF-A gives 32-bit lower ELs —
  `SCTLR = 0x00c50838` (RES1 | CP15BEN | nTWI | nTWE), `HCR_EL2.RW = 0`,
  `SPSR = 0x1d3` (SVC, A/I/F masked, ARM state). HW-validated: mainline 6.16.7
  AArch32 boots to userspace via `bootm` of a FIT `arch=arm` image. *(`f45e8f1`)*
- The native `arch=arm64` path needs none of this (ES_TO_AARCH64) and gets
  full 4-core SMP; the AArch32 path is single-core (32-bit PSCI secondary
  bring-up unsolved — see SMP below).

## arm64 linker: `.bss` placement (ld.lld)

`ld.lld` miscomputes the historical `.bss ADDR(.rela.dyn) (OVERLAY)` placement
and assigns `.bss` VMA 0. That makes `gd->mon_len = __bss_end - _start` wrap to
~2.9 GiB, sends `gd->relocaddr` to garbage, and hangs the first reserve-area
step. Place `.bss` at the current location counter (right after `.rela.dyn`)
instead. Costs bss-size bytes of relocated RAM, binary does not grow (NOBITS).
GNU ld resolves the OVERLAY form correctly, so upstream likely wants an
lld-conditional form. *(`309aee7`)*

## SMP / PSCI (TF-A) — status & the register map

- **CPU_ON works for all 4 cores** (HW-proven). The fix was forcing the
  **non-per-cluster** ("else") path in the shared `sunxi_cpu_on()` with the
  `ncat` register file — that path's registers line up exactly with the stock
  BL31 per-core sequence:
  - RVBAR `CPUSUBSYS+0x40+n*8` (`0x08100040`)
  - reset `CPUCFG+0x60+n*4` (`0x09010060`, bit 0 rst / bit 8 dbg)
  - enable/aa64 `CPUSUBSYS+0x20+n*4` (`0x08100020`, bit 0 → core comes up in AArch64)
  - power-rst `R_CPUCFG+0x70+n*4` (`0x07000470`, bits 0/1)
  - clamp `R_CPUCFG+0x50+n*4` (`0x07000450`, skipped — already 0 on our stack)
- `CPU_SUSPEND` implemented (standby + powerdown); full wake exercised by Linux,
  not the bare U-Boot harness (which leaves `GICD_CTLR=0`).
- **Open:** 32-bit kernels boot single-core — a 32-bit PSCI caller needs
  secondaries started in AArch32, but BL31 brings them up AArch64. The vendor
  32-bit stack sidesteps this by dropping to AArch32 at EL3 (SCR_EL3.RW=0).

## FEL (sunxi-tools)

- The **BROM stalls part-way through large contiguous bulk-OUT transfers**: a
  32 KiB SPL uploads reliably, 64 KiB wedges the session with `ETIMEDOUT`. Cap
  individual bulk requests at **16 KiB** and retry the remainder on a partial
  timeout. This is what makes FEL-loading any >~48 KiB SPL work (e.g. a recovery
  SPL with an embedded boot0). *(`003b61c`)*
- H713 FEL memory: scratch `0x121500`, SPL `0x104000`, with a stack swap
  *(`3212210`)*. Hardware **FEL button** exists → there is always a recovery
  vector. Full detail in [reference/h713-fel-notes.md](reference/h713-fel-notes.md).

## eMMC recovery tool — **local only, never upstream**

A one-shot recovery SPL (`hy200_h713_recovery_defconfig`,
`CONFIG_H713_EMMC_RECOVERY`) that, after DRAM init, writes an embedded copy of
the vendor boot0 back to the eMMC boot offset (sector 16) and halts. FEL-load it
once to un-brick a board whose first stage was overwritten, then power-cycle to
the stock firmware. Repeatedly recovered the HY200 bench board (`wrote 64/64
RESTORED-OK`), including from a fully cold FEL entry once the SMHC gate ordering
was fixed.

It embeds the board's **proprietary vendor boot0** (`h713_vendor_boot0.h`), so
it is kept out of the public forks entirely and lives as
`local/0001-h713-emmc-recovery-tool-LOCAL-ONLY.patch` (gitignored). `git am` it
to rebuild the tool. *(`d293f44`)*

## Diagnostic techniques (scaffolding stripped before commit)

These were removed from the final series *(`53d1921`, `0fd8b99`)* but the
**methods** are reusable for any further silicon debugging on this SoC:

- **Reboot-timing progress reporting (pre-console).** `H713_WDOG_STAGE` armed
  the watchdog to reset after N stages so boot progress could be read by the
  *reset timing* before the UART was up.
- **Reset-timing oracle over USB re-enumeration.** When the UART is flaky, a
  clean `bootm` handoff keeps the USB gadget enumerated, but an SoC reset drops
  it — so "watch the ACM/CDC gadget disappear" is a reliable reset detector.
- **AArch32 DRAM read-back oracle** (`h713_a32_dram_oracle` in `fel_utils.S`)
  and `CONFIG_H713_FEL_DIAG_*` FEL-return checkpoints / DMA oracles / PHY
  register captures.
- **Unicorn BT0 replay sweep.** Ran the stock BT0 DDR3 path over 30 DRAM clocks
  (312–1200 MHz) under Unicorn emulation and fitted each timing field, which
  generalized the DDR3 timing computation to a vendor-accurate model
  (510/510 register checks) instead of a single-clock replay. *(`fec73c7`)* Key
  DDR3 findings: most cycle counts are **frozen table values**, not JEDEC-ns
  conversions; one speed bin switches above 800 MHz; `trd2wr` bumps 5→6 above
  912 MHz; timings derive from the PLL_DDR-rounded effective clock
  `((clk*2/24)*12)`; the vendor ignores `para->mr0/mr2` for DDR3.

## Transfer speeds (bench workflow)

- Real UART @115200 ≈ 11 KB/s (a 7 MB image is ~10 min).
- USB-CDC ACM gadget ≈ 171 KB/s (USB bulk, baud-independent). UART is the
  compiled and saved safe default; run `run acm_mode` to opt into CDC for bulk
  loads. Resolve the device by USB VID `1f3a`, not a fixed `/dev/ttyACM*` path
  (it moves across re-enumeration).
- ACM, UMS, and fastboot share one device controller and must run successively.
  `run fastboot_mode` first selects serial-only consoles, starts fastboot, and
  restores serial-only consoles if fastboot returns. This transition was
  hardware-verified when issued directly from ACM. Close the old host handle
  before switching modes; if Linux retains a stale USB identity after reset,
  power-cycle the board before continuing.
- fastboot download buffer is 32 MiB → large images must be Android-sparse
  (`img2simg`); the host tool chunks them.
