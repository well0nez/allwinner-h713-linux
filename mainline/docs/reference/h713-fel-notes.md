# H713 FEL notes

> **Board naming (2026-07-18):** "HY200" = the bench board `HY200_QZ713DF_A1`; "HY310" refers to the projector, now correctly identified as `HY200_QZ713_V2`. This historical doc predates that correction.


This file tracks the H713-specific FEL facts we have imported from local
hardware testing and from `<local>/sun50iw12p1-research/`.

## USB TRANSPORT — CORRECTED 2026-07-29 (read before trusting any FEL result below)

The long-standing "H713 FEL BROM stalls on large bulk transfers" conclusion is
**wrong**, and several results in this file were shaped by it. Measured on
hardware 2026-07-29:

- The FEL link is **full-speed USB 1.1 with 64-byte bulk packets** (`bcdUSB
  1.10`, 12 Mbit/s, `wMaxPacketSize=64` on both endpoints), not high-speed with
  512-byte packets. Any reasoning that assumed 512 was wrong.
- Large contiguous transfers are **fine**: 49152 bytes in a single bulk request,
  92.4 ms, ~530 KB/s, read back byte-identical. 32 KiB unchunked likewise.
  The 4 KiB/16 KiB chunk caps have been removed.
- A healthy session replies with **exactly** 13/32/8 bytes. It does *not*
  over-send, contrary to the premise of the "oversized FEL status reads" commit.
  An oversized reply means the stream had already desynced upstream.

The real cause of the "stalls": a raw `sunxi-fel write` bypasses the swap-buffer
relocation the SPL loader performs, so a write based at `0x104000` runs straight
through the BROM's own IRQ stack (`0x105000`) and BSS (`0x10b300`), killing the
BROM's USB stack mid-transfer. Reproduced deliberately: 32 KiB at `0x104000`
wedges the session; 4 KiB at the same base (stopping just below `0x105000`)
completes in 7.8 ms. `sunxi-fel` now refuses such writes up front.

**Consequence for the record below:** any experiment that used a raw `write`/
`readl`/`writel` into `0x104000`–`0x124000` may have been measuring BROM
corruption rather than the effect under test. Results obtained via the SPL
loader (`sunxi-fel spl`) are *not* implicated — it relocates around these
regions by design, which covers most of the DRAM bring-up ladder. Re-verify
before relying on any raw-write result.

Useful knobs now available: `SUNXI_FEL_TRACE=1` (per-request wire trace),
`SUNXI_FEL_TIMEOUT=<ms>` (bound diagnostic runs), `SUNXI_FEL_MAX_CHUNK=<bytes>`,
`SUNXI_FEL_ALLOW_UNSAFE=1` (override the reserved-region guard).

## CURRENT STATE (read this first; updated 2026-07-04 UTC)

- HANDOFF FOR CLAUDE: start with
  `<local>/h713-lab/reports/h713-bt0-dram-init-sequence-20260703T004500Z/CLAUDE-HANDOFF-20260704.md`.
  It is the compact current-state summary with the queued SPL images and
  timing verdicts. The short version: A523 is not the right DRAM-controller
  base; D1/sun20i is the closer COM+DRAMC register model; the best current
  evidence is that even an independent DMA master cannot complete the first
  SDRAM read after nominal init.

- sunxi-tools H713 support is hardware-proven: soc 0x1860, scratch
  `0x121500`, `spl_addr 0x104000`, safe upload to `0x1c300`, swap protection
  for `0x120300..0x120500`, working ERET-based `return_to_fel()`.
- SPL checkpoint ladder is clean through console init and into
  `sunxi_dram_init()` entry (UART0 base is `0x02500000`).
- STOP bisecting the H616-derived PHY writes. Offline BT0 disassembly
  (2026-07-03) proved the stock H713 BT0 does not use the H616 DRAM
  layout. The first pass identified A133-generation COM/CTL addresses:
  COM `0x04810000`, CTL/DRAMC `0x04820000`, and no touches to the H616
  bases `0x047fa000/0x047fb000/0x04800000` that `dram_sun50i_h713.c`
  currently programs. All "PHY 0x144/0x14c" wedge results were writes
  into an unknown non-DRAM block at `0x04800000` and prove nothing about
  DRAM sequencing.
  See `<local>/h713-lab/reports/`
  `h713-bt0-dram-block-discovery-20260703T000809Z.txt`.
- Update after full sequence extraction (2026-07-03): no mainline driver
  matches sun50iw12. A133 shares the COM base (0x04810000) but BT0 never
  touches an 0x04830000 PHY; the block at 0x04820000 is a combined
  controller/PHY variant with PIR-style trigger/poll writes at DRAMC+0,
  a timing block at +0x2c..0x94, and per-lane delay blocks at
  +0x310/0x390/0x410/0x490. Stock HY310 DQS-gating mode 0 uses
  0x172->0x173 when R_CPUCFG+0x5d4 bit16 is clear, or 0x62->0x63 with
  extra PHY toggles when that bit is set; 0x52->0x53/0x401 is the mode-1
  arm, not the stock path. Full decode and ordered plan:
  `<local>/h713-lab/reports/`
  `h713-bt0-dram-init-sequence-20260703T004500Z/`.
- MILESTONE 2026-07-03: ALL implemented blocks through TYPE_PARAMS are
  hardware-proven first-in-session via `h713-lab/scripts/iw12-ladder.fish`
  (BUS, LDOB, ZQ_CAL, DRAM_CLK, COM, TYPE_PARAMS all PASS). Key process
  lesson: results only count FIRST-in-session — every apparent rung-3
  failure was a second-upload artifact (Chris spotted the confound).
  Two FEL-safety deviations from vendor order are baked into
  `iw12_bus_init()` and documented in-code.
- TIMING DECODE UPDATE (2026-07-03): the intermediate Claude note in
  `TIMING-DECODE.txt` was wrong about the target. A forced-Thumb check
  of stock BT0 function `0x105da6` shows direct DRAMC writes to
  `0x0482002c..0x04820094` from literal-loaded register addresses,
  not only computed fields in a RAM struct. The HY310 LPDDR3/720 MHz
  path has now been ported into U-Boot as `iw12_set_timing()`, behind
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_IW12_TIMING`. This is build-,
  disassembly-, and live hardware-verified first-in-session. A static
  eMMC/BT0 dump does not contain a runtime post-compute register
  snapshot; it contains the code and seed parameters, so the values come
  from the BT0 disassembly/build output rather than being read from a
  saved register dump.
- PIR/TRAIN DECODE UPDATE (2026-07-03): after installing Unicorn/Capstone,
  BT0 `0x1068d0` was executed offline with the HY310 LPDDR3 parameter
  struct and prior timing registers seeded. The trace returns success and
  confirms the stock mode-0 path above, including `DRAMC+0x0c0 =
  0x01003087`, `DRAMC+0x140 = 0x023f3ffb`, trigger `0x172->0x173`
  when R_CPUCFG+0x5d4 bit16 is clear, and final cleanup through
  `COM+0x014 bit31`. The `0x105b54` per-lane delay helper and `0x1068d0`
  PHY/train body are now ported into U-Boot as
  `iw12_eye_delay_compensation()` and `iw12_phy_train()`, with a
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_IW12_PIR` checkpoint. This is
  build/disassembly/emulator-verified and live hardware-proven
  first-in-session.
- POST-PIR TAIL UPDATE (2026-07-03): the BT0 `0x10723a` tail, SID capacity
  clamp, Auto-SR policy bits, and `0x106bdc` size calculator are now ported.
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_IW12_SIZE` is live hardware-proven
  first-in-session: SPL returned and `sunxi-fel version` still worked. The
  first full simple-test checkpoint (`CONFIG_H713_FEL_DIAG_RETURN_AFTER_IW12_SIMPLE_TEST`)
  did NOT return: upload reached `=> Executing the SPL... done.`, then
  `usb_bulk_send()`/`version` timed out while `lsusb` still showed FEL. Treat
  that as a real post-size simple-test hang/panic, not a size-tail failure.
  Next debug rungs split BT0 `0x106cec`: first low write, first high write,
  full write phase, then readback checkpoints if needed. The first low write
  diagnostic is live-proven: one store to `0x40000000` returned to FEL and
  `sunxi-fel version` still worked. The first high write diagnostic is also
  live-proven: the paired store to the size-derived half-memory address
  returned to FEL and `sunxi-fel version` still worked. The full interleaved
  write phase (`0x1000` words at each window) is live-proven too, so the
  remaining failure is in readback/compare or later. The first low-window
  readback checkpoint did not return; `sunxi-fel version` timed out afterward
  while `lsusb` still showed FEL. Next checkpoint should capture the actual
  first low read value before compare/panic. Follow-up capture checkpoint
  also did not return even though it returns before compare, proving the
  failing operation is the first CPU read from `0x40000000` itself, not a
  value mismatch. The broad PHY-status capture
  (`CONFIG_H713_FEL_DIAG_CAPTURE_IW12_PHY_STATUS`) reached SPL execution on a
  healthy FEL session, then timed out; `sunxi-fel version` timed out afterward
  while `lsusb` still listed `1f3a:efe8`. It captured after PIR/train cleanup
  and before size calculation or SDRAM access, so the failure is now either
  the broad capture's extra DRAMC/COM register reads, the SRAM scratch choice,
  or the just-finished train state itself. The minimal PHY-status capture
  (`CONFIG_H713_FEL_DIAG_CAPTURE_IW12_PHY_STATUS_MINIMAL`) PASSED first in a
  fresh session and `sunxi-fel version` still worked after readback. Record at
  `0x00110000`: magic `0x49313257`, tag `0x5048596d` (`PHYm`),
  `DRAMC+0x010 = 0x8000001d`, `DRAMC+0x018 = 0x00000001`, CPU-gate masked
  value `0`, DQS-gating mode `0`, BT0-style return `1`. This means the live
  path is the stock mode-0 `0x172->0x173` path and training is nominal by
  BT0's `0x0ff00000` failure mask; the first SDRAM CPU read wedge is
  downstream of a nominal train result. Avoid broad DRAMC/COM register scrapes unless
  split one register at a time. A stronger immediate hypothesis is that
  U-Boot's simple test was using MMIO `readl()`/`writel()` on SDRAM, adding
  barriers that BT0's plain `ldr/str` simple test does not use. That was
  tested and disproven: the plain-access low-read capture still reached SPL
  execution, then wedged before the SRAM record stores. The first CPU load
  from SDRAM itself remains the failing operation. Skipping the write phase
  entirely also still wedged on the first low SDRAM read, so the writes are
  not causing the read failure. The pre-tail split also failed/hung first in
  session: one low SDRAM read immediately after PHY/train cleanup and before
  SID/size/tail work reached SPL execution, then timed out; a following
  `sunxi-fel version` also timed out while `lsusb` still showed FEL. This
  means the read path is already broken immediately after nominal train
  cleanup, not caused solely by the post-tail writes. Follow-up offline trace
  diff found a concrete U-Boot mismatch: `iw12_eye_delay_compensation()` only
  programmed the first two BT0 byte-lane delay blocks, missing the BT0 writes
  for `DRAMC+0x410..0x430`, `+0x490..0x4b0`, and companions
  `+0x434/+0x438/+0x43c/+0x4b4/+0x4b8/+0x4bc`. That has been patched in the
  U-Boot tree and rebuilt as
  `/tmp/u-boot-iw12-pre-tail-low-read-lane-fix/spl/sunxi-spl.bin`. The
  rebuilt disassembly shows the lane-2/lane-3 writes and keeps the first
  SDRAM read before the tail (`0x1051b8` read, `0x1051e4` tail begins).
- LIVE UPDATE 2026-07-04: A523 is useful as a fabric/security clue source,
  but not a better H713 DRAM-controller base. The mainline A523/T527 DRAM
  driver is a different COM/CTL/PHY split; the H713 BT0 trace and D1/sun20i
  still match the actual COM+DRAMC offsets. The A523-style 0x02000800
  firewall/SPC sequence was live-tested with both write+DSB and read oracles:
  it did not unblock SDRAM CPU reads. A validated DMA probe narrowed the
  failure further. SRAM-to-SRAM DMA copied correctly (`DMAS/DONE`, expected
  0x13579bdf). A start-only SDRAM DMA read left the CPU/watchdog alive
  (fallback watchdog reset at ~16 s), but a DMA chain whose second LLI writes
  the watchdog reset registers did not advance when the first LLI read from
  SDRAM: the DRAM-chain image reset only at the fallback watchdog time
  (execute 1783197511.224, USB absent 1783197527.730, delta +16.506 s),
  while the SRAM-chain control reset immediately (execute 1783197424.860,
  USB absent 1783197425.467, delta +0.607 s). Conclusion: the failure is not
  CPU-load-specific and not just missing master/firewall enables; an
  independent DMA master cannot complete the first SDRAM read after the
  current init sequence. Follow-up bypass of the PIR trigger/poll still took
  the fallback watchdog path with the same DMA-chain oracle (execute
  1783197897.479, USB absent 1783197913.888, delta +16.409 s), so the poll
  path itself is less likely to be corrupting an otherwise usable read path.
  A 1000 ms settle delay before the first SDRAM access also failed: execute
  1783198161.710, USB absent 1783198179.172, delta +17.462 s (the expected
  one-second delay plus fallback watchdog). Waiting after final controller
  setup does not unblock SDRAM reads.
- NEW DRIVER EXISTS: `arch/arm/mach-sunxi/dram_sun50iw12.c` in the local
  U-Boot tree, enabled by `CONFIG_DRAM_SUN50IW12=y` (now default in
  `hy310_h713_defconfig`; the H616-derived `dram_sun50i_h713.c` is no
  longer built). Implemented so far, each behind a FEL checkpoint:
  RTC-region sys cfg, bus/NSI/MBUS enables (the DRAM-relevant tail of
  boot0 set_pll; PLL_CPU/PLL_PERI deliberately NOT replayed — U-Boot
  clock_init covers them and touching PLL_PERI under FEL risks BROM USB),
  ldob fix, ZQ-cal (internal-ZQ path per tpr13 bit16), DRAM clock/COM/
  type params, timing write-out, PIR/train, and the post-training
  SID/size/controller tail. Full simple write/read is implemented but not
  hardware-proven; the current live failure is inside or after BT0 `0x106cec`.
  Do not treat a no-checkpoint build as complete until that path passes.
- Do NOT readl the DRAM blocks over FEL before their clocks are enabled;
  gated-block reads can wedge FEL like the `0x124000` case.
- The queued `unk500-only` checkpoint is superseded by the above; running it
  adds no DRAM information.

## Proven on hardware

- FEL version reports `soc=00001860(H713)` and `scratchpad=00121500`.
- Two H713 boards reported the same ROM scratchpad address: `0x00121500`.
- A small write/restore and an executable marker helper at `0x121500` both
  worked, so `scratch_addr = 0x121500` is preferred over the older guessed
  `0x121000`.
- `spl_addr = 0x104000` is supported by the factory eGON header analysis and
  by the minimal dummy SPL upload/execute test.
- The BROM stack helper measured `sp_irq = 0x00105400` and `sp = 0x00120300`.
- Reusing the scratch address for different helper code can execute stale
  instructions unless H713 uses the I-cache workaround.
- The region at `0x124000` is not safe to probe as normal SRAM. Reads crossing
  into it wedge FEL until the board is reconnected.
- Corrected scratch plus I-cache handling makes helper-backed operations work,
  including `sid`, `readl`, and scratch `memmove`.

## Useful imported research

- `docs/H713_BROM_MEMORY_MAP.md` confirms that H713 uses SRAM A2 for SPL
  loading and that the old H616-style `0x20000` SPL address is wrong for this
  board.
- `FEL_USB_OVERFLOW_FIX_TESTING.md` claims H713 returns a larger response for
  tiny FEL status reads. **Disproven 2026-07-29** — a healthy session replies
  with exactly 13/32/8 bytes. The real requirement is that a bulk IN buffer be a
  multiple of `wMaxPacketSize` (64 here); the old 64-byte bounce for `<=8`-byte
  reads satisfied that by coincidence and missed the 13-byte `AWUS` read.
  `fel_lib.c` now sizes the bounce from the endpoint descriptor.
- `FEL_USB_WRITE_SUCCESS.md` and the chunk-size experiments are **superseded**:
  the transfer sizes were never the variable. See the corrected transport
  section at the top. `fel_lib.c` is back to upstream chunk sizes (512 KiB
  normal / 128 KiB progress) with a 20 second default USB timeout.
- `SCTLR_WARNING_ANALYSIS.md` matches local testing: H713 FEL starts with MMU
  disabled, so `SCTLR = 0` is expected and not a blocker by itself.
- `<local>/h713-lab/` contains an earlier conservative evidence
  gate. Most of it predates the live scratch/thunk/SID tests in this repo, but
  two findings are still useful:
  - Stock BT0 images have eGON length `0x8000` and load evidence at
    `0x104000`.
  - Offline scans found the quietest SRAM study band at
    `0x111000..0x11d000`, while `0x120000`, `0x122000`, and the high stack
    neighborhood are noisy.

## Stale or conflicting research

- `sunxi-tools-h713-support.patch` and early summary notes add H713 using the
  H616 memory map (`spl_addr = 0x20000`, `scratch_addr = 0x21000`,
  `thunk_addr = 0x53a00`). Do not use those addresses for this board.
- Older candidate notes guessed `scratch_addr = 0x121000`; the ROM-reported
  and hardware-proven scratchpad is `0x121500`.
- Factory boot0/BSS notes disagree about exact BSS placement
  (`0x10b348..0x10b944` versus `0x10bc44..0x10beec`). The current swap table
  protects the locally analyzed `0x10b300..0x10ba00` window; expand only after
  a hardware proof or a reconciled disassembly.

## Latest large-SPL result

- Restoring upstream-sized USB writes did not fix the `0x1d000` dummy SPL.
  `./sunxi-fel -v spl /tmp/h713_large_return_spl.bin` still timed out in
  `usb_bulk_send()` before thunk execution.
- After that timeout, `lsusb` still showed `1f3a:efe8`, but `./sunxi-fel version`
  also timed out. Treat this as a wedged FEL session that needs reconnect/reset.
- A later increasing-size probe run passed every return-SPL through length
  `0x1c300` (end address `0x120300`) and failed again at length `0x1d000`
  (end address `0x121000`). The remaining unsafe upload window is therefore
  inside `0x120300..0x121000`, immediately above the measured `sp=0x120300`.
- The first fine probe, length `0x1c400` (end address `0x120400`), also failed
  and wedged FEL. This proves the first unsafe write window starts exactly at
  `0x120300`.
- With a `0x120300..0x120400` swap entry, the `0x1c400` probe passed. The next
  probe, length `0x1c500` (end address `0x120500`), failed and wedged FEL.
- With a `0x120300..0x120500` swap entry, the `0x1c500` probe passed. The next
  probe, length `0x1c600` (end address `0x120600`), failed and wedged FEL.
- The current code protects the last hardware-proven upper stack-adjacent
  slice, `0x120300..0x120500`, backed up at `0x122000..0x122200`. The failed
  `0x1c600` probe proves that the next slice still needs a deliberate plan if
  a real SPL ever reaches it.
- After removing the unproven `0x120500..0x120600` slice, the current table
  was re-tested with `/tmp/h713_return_spl_10000.bin`. The `0x10000` dummy
  return SPL uploaded, executed, returned to FEL, and `version` still worked.

## Mainline U-Boot SPL sizing

- A clean local U-Boot clone exists at `<local>/u-boot/`, commit
  `f605dcee103` on `master`.
- Mainline has H616/H618/H700 configs but no explicit H713 config yet.
- An out-of-tree build of `x96_mate_defconfig` was done in
  `/tmp/u-boot-x96-mate.ucs301` with clang/LLVM. The useful SPL artifact is
  `/tmp/u-boot-x96-mate.ucs301/spl/sunxi-spl.bin`.
- The successful SPL-only build used:
  `make -C <local>/u-boot O=/tmp/u-boot-x96-mate.ucs301 ARCH=arm NO_PYTHON=1 HOSTCC=clang CC='clang -target aarch64-linux-gnu' LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump READELF=llvm-readelf STRIP=llvm-strip KCFLAGS=-fintegrated-as KAFLAGS=-fintegrated-as -j8 spl/sunxi-spl.bin`.
- That SPL's eGON header length is `0xa000` bytes. This is below both the
  hardware-proven `0x1c300` upload end and the current swap-derived software
  limit of `0x1d900`.
- The H713 `sram_size` field is set conservatively to `128 * 1024`, covering
  `0x104000..0x124000`. The old H616-derived `207 * 1024` value crosses the
  locally unsafe `0x124000` boundary and should not be used for H713.
- Do not execute that H616 SPL on H713 as-is. The config still has
  `CONFIG_SUNXI_SRAM_ADDRESS=0x20000` and `CONFIG_SPL_TEXT_BASE=0x20060`;
  H713 needs the U-Boot side changed to the `0x104000` SRAM A2 layout before a
  real SPL execution test.

## H713 U-Boot support work

- `<local>/allwinner-h713-linux/` is the strongest source for
  board-level H713 values. It identifies the H713/HY310 main PIO as
  `0x02000000` with D1-style `0x30` bank spacing, CCU at `0x02001000`, UART0
  at `0x02500000` on `PH0/PH1` mux 2, eMMC/MMC2 at `0x04022000` on
  `PC0/PC1/PC5/PC6/PC8-PC11/PC13-PC16`, and watchdog at `0x02051000`.
- Its FEX gives the current DRAM seed values used in the new U-Boot config:
  `dram_clk = 792`, `dram_type = 3`, `dram_odt_en = 0x1`,
  `dram_tpr0 = 0x004a2195`, `dram_tpr2 = 0x0008b061`,
  `dram_tpr6 = 0x48`, `dram_tpr10 = 0x0`, `dram_tpr11 = 0x44340000`,
  and `dram_tpr12 = 0x00006666`.
- The older `<local>/sun50iw12p1-research/` U-Boot configs are
  useful mainly as a warning: they mix real H713 DRAM/FEX values with stale
  H6/H616 assumptions such as `CONFIG_SPL_TEXT_BASE=0x10000` or H6 PIO/watchdog
  addresses. Prefer the live FEL proof and the newer H713 Linux DTS/FEX.
- `<local>/h713-lab/` agrees with the live-critical values:
  `spl_addr = 0x00104000`, SID base `0x03006000`, alternate RVBAR
  `0x08100040`, and watchdog `0x02051000`.
- Mainline U-Boot now has a local H713/HY310 target in
  `<local>/u-boot/configs/hy310_h713_defconfig` and
  `<local>/u-boot/dts/upstream/src/arm64/allwinner/sun50i-h713-hy310.dts`.
  The generated config uses `CONFIG_SUNXI_SRAM_ADDRESS=0x104000`,
  `CONFIG_SPL_TEXT_BASE=0x104060`, `CONFIG_SPL_STACK=0x120000`,
  `CONFIG_SPL_MAX_SIZE=0xbfa0`, `CONFIG_DRAM_CLK=792`,
  `CONFIG_MMC_SUNXI_SLOT_EXTRA=2`, `CONFIG_SUNXI_NEW_PINCTRL=y`, and
  `CONFIG_SUNXI_RVBAR_ALTERNATIVE=0x08100040`.
- The current H713 SPL build succeeded in `/tmp/u-boot-h713.EhMXob`:
  `/tmp/u-boot-h713.EhMXob/spl/sunxi-spl.bin` is `40960` bytes, has a valid
  eGON header, and reports DT name `allwinner/sun50i-h713-hy310`.
- A full U-Boot build now succeeds with the local H713 TF-A BL31. The current
  `/tmp/u-boot-h713.EhMXob/u-boot-sunxi-with-spl.bin` is `772065` bytes and
  embeds the H713 BL31 strings, so it no longer uses binman's fake BL31
  placeholder.
- The H713 DRAM controller base addresses still come from the H616 driver
  model (`0x047fa000`, `0x047fb000`, `0x04800000`) because the local research
  did not contain a better H713-specific DRAM controller base proof. The FEX
  timing values are H713-specific, but the current mainline H616 DRAM driver
  cannot represent every stock FEX field directly.

## H713 TF-A support work

- `<local>/arm-trusted-firmware/` now has a local
  `plat/allwinner/sun50i_h713` platform.
- The platform uses H713/HY310 evidence for SRAM and MMIO layout:
  `SUNXI_SRAM_BASE = 0x00100000`, `SUNXI_SRAM_A2_BASE = 0x00104000`,
  `SUNXI_CCU_BASE = 0x02001000`, `SUNXI_PIO_BASE = 0x02000000`,
  `SUNXI_UART0_BASE = 0x02500000`, `SUNXI_WDOG_BASE = 0x02051000`,
  `SUNXI_GICD_BASE = 0x03021000`, `SUNXI_GICC_BASE = 0x03022000`,
  `SUNXI_DMA_BASE = 0x03002000`, `SUNXI_R_PRCM_BASE = 0x07010000`,
  `SUNXI_R_PIO_BASE = 0x07022000`, `SUNXI_CPUSUBSYS_BASE = 0x08100000`,
  and `SUNXI_CPUCFG_BASE = 0x09010000`.
- `SUNXI_SPC_BASE = 0x03008000` is still carried from the H616-family secure
  peripheral controller layout; local research did not expose an H713-specific
  replacement.
- The successful BL31 build used clang with `PLAT=sun50i_h713` and
  `BUILD_BASE=/tmp/atf-h713`. The useful artifact is
  `/tmp/atf-h713/sun50i_h713/release/bl31.bin`, size `40964` bytes. Its ELF
  entry point is `0x40000000`, matching the U-Boot H713 BL31 base.

## H713-linked SPL smoke test

Do not keep walking the upper stack-adjacent window in 0x100-byte increments
unless we specifically need to support SPLs that reach it. The measured
mainline H616 SPL size is small enough for the current H713 FEL support, and a
larger `0x10000` dummy has been re-proven on hardware.

- The first H713-linked SPL smoke test used
  `/tmp/u-boot-h713.EhMXob/spl/sunxi-spl.bin`.
- Before execution, `./sunxi-fel -v ver` reported
  `soc=00001860(H713)` and `scratchpad=00121500`.
- `./sunxi-fel -v spl /tmp/u-boot-h713.EhMXob/spl/sunxi-spl.bin` printed the
  expected DT name, measured stack pointers, and reached
  `=> Executing the SPL... done.`, but the tool returned with
  `usb_bulk_send() ERROR -7: Operation timed out`.
- After execution, `lsusb` still showed `1f3a:efe8`, but
  `./sunxi-fel -v ver` timed out. Treat this as a wedged post-SPL session that
  needs reconnect/reset.
- After building a real BL31-enabled full image,
  `./sunxi-fel -v spl /tmp/u-boot-h713.EhMXob/u-boot-sunxi-with-spl.bin` failed
  in the same shape: it printed the H713 DT name, stack pointers, and
  `=> Executing the SPL... done.`, then returned
  `usb_bulk_send() ERROR -7: Operation timed out`.
- After that staged full-image `spl` test, `lsusb` still showed `1f3a:efe8`,
  but `./sunxi-fel -v ver` timed out. `uboot` was not attempted because the
  board is not surviving SPL well enough to accept the DRAM payload transfer.
- A pre-DRAM diagnostic SPL was then built with
  `CONFIG_H713_FEL_DIAG_RETURN_BEFORE_DRAM`. Disassembly confirmed
  `sunxi_board_init()` calls `sunxi_return_to_fel()` before
  `sunxi_dram_init()`.
- The first pre-DRAM diagnostic used the inherited H616/A133 return path:
  write CPU hotplug magic `0xfa50392f` to `SUNXI_R_CPUCFG_BASE + 0x1c0`
  (`0x070005c0` on H713), write `back_in_32` to the following word, then
  request AArch32 RMR mode `2`. It failed in the same shape:
  `=> Executing the SPL... done.`, followed by
  `usb_bulk_send() ERROR -7: Operation timed out`; afterwards `lsusb` still
  showed `1f3a:efe8`, but `./sunxi-fel -v ver` timed out.
- That result proves the current wedge happens before DRAM init or inside the
  return-to-FEL path. It specifically weakens the inherited H616 hotplug
  mailbox assumption for H713.
- Vendor boot0 evidence in `<local>/h713-lab/` shows H713 boot0
  programming direct RVBAR `0x08100040` and issuing RMR mode `3` to enter
  AArch64. A new H713-only experimental return stub now mirrors that path in
  reverse: it writes `back_in_32` to `CONFIG_SUNXI_RVBAR_ALTERNATIVE`
  (`0x08100040`), clears the high word, and requests AArch32 RMR mode `2`.
- The rebuilt pre-DRAM RVBAR-return SPL in
  `/tmp/u-boot-h713-diag-pre-dram.lWoyzk/spl/sunxi-spl.bin` still had the
  expected H713/HY310 eGON header and embedded literal `0x08100040` in
  `return_to_fel()`. It also failed in the same shape:
  `=> Executing the SPL... done.`, followed by
  `usb_bulk_send() ERROR -7: Operation timed out`; afterwards `lsusb` still
  showed `1f3a:efe8`, but `./sunxi-fel -v ver` timed out.
- This means the wedge is earlier than DRAM and was not fixed by replacing the
  inherited H616 hotplug mailbox with direct H713 RVBAR programming.
- A new board-init-entry diagnostic SPL has been built at
  `/tmp/u-boot-h713-diag-board-init-entry/spl/sunxi-spl.bin`. Disassembly
  confirms `board_init_f()` loads the saved FEL `sp/lr` and calls
  `return_to_fel()` before `sunxi_sram_init()`, `tzpc_init()`, `timer_init()`,
  `clock_init()`, `gpio_init()`, or `spl_init()`. The return stub still embedded
  literal `0x08100040`. It also failed in the same shape:
  `=> Executing the SPL... done.`, followed by
  `usb_bulk_send() ERROR -7: Operation timed out`; afterwards `lsusb` still
  showed `1f3a:efe8`, but `./sunxi-fel -v ver` timed out.
- That result means the failure is before normal SPL board init, or the
  AArch64 return-to-FEL path is not landing back in BROM/FEL.
- Two tighter boundary diagnostics are ready:
  `/tmp/u-boot-h713-diag-boot0-a32/spl/sunxi-spl.bin` returns directly from
  the AArch32 boot0 hook before programming RVBAR or requesting the AArch64 RMR
  transition. Byte inspection shows the intended `ldr sp`, `ldr lr`, `bx lr`
  sequence immediately after the FEL state is saved. This test succeeded:
  `./sunxi-fel -v spl ...boot0-a32.../sunxi-spl.bin` returned without timeout,
  and a follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report.
- `/tmp/u-boot-h713-diag-a64-reset/spl/sunxi-spl.bin` returns immediately after
  the AArch64 reset vector reaches `save_boot_params_ret`, before exception
  setup, stack setup, or C runtime. Disassembly confirms it loads `sp/lr` from
  `fel_stash` and branches to `return_to_fel()`. This test failed in the same
  wedged shape: the SPL command timed out after `=> Executing the SPL... done.`,
  `lsusb` still showed `1f3a:efe8`, and `./sunxi-fel -v ver` timed out.
- The A64 image's embedded AArch32 boot hook contains
  `CONFIG_SUNXI_RVBAR_ADDRESS = 0x09010040`, `SUNXI_SRAMC_BASE = 0x03000000`,
  `CONFIG_SUNXI_RVBAR_ALTERNATIVE = 0x08100040`, and
  `CONFIG_SPL_TEXT_BASE = 0x00104060`. Since live `readl 0x03000024` was
  `0x00000101`, that hook should choose the alternate `0x08100040` RVBAR.
- Both boundary diagnostic builds place `fel_stash` at `0x0010cb38`. After the
  next successful A32 direct-return run, read `0x0010cb38` for 0x20 bytes to
  capture the saved ROM/FEL `sp`, `lr`, `cpsr`, `sctlr`, `vbar`, and
  `sp_irq` values. That data is needed before attempting an A64 `eret`-style
  return path.
- The A32 direct-return SPL was rerun and `fel_stash` was captured while FEL
  was still alive:
  `sp = 0x00123a18`, `lr = 0x00123ad8`, `cpsr = 0x200001d3`,
  `sctlr = 0x00c50838`, `vbar = 0x00014000`, `sp_irq = 0x00105400`,
  `icc_pmr = 0x00000000`, and `icc_igrpen1 = 0x00000000`.
- This proves the working return target is the `sunxi-fel` thunk region around
  `0x00123a00`, not a direct ROM entry. It also shows the ROM/FEL return
  context is AArch32 SVC mode with abort/IRQ/FIQ masked.
- A single-process FEL register survey was used to avoid repeated USB
  interface claims. The candidate RVBAR and mailbox registers read back as
  zero at reset: `0x08100040`, `0x08100044`, `0x09010040`, `0x09010044`,
  `0x070005c0`, `0x070005c4`, `0x070901b8`, `0x070901bc`, `0x07090100`, and
  `0x07090104`. Vendor boot0 setup registers were live:
  `0x07090160 = 0x883f10f7` and `0x07010340 = 0x00002f0f`.
- A new A64 reset-entry diagnostic SPL was built at
  `/tmp/u-boot-h713-diag-a64-rtc-mailbox.hxolZH/spl/sunxi-spl.bin`. It used
  the H6-style RTC hotplug mailbox adjusted for H713
  (`0x070901b8/0x070901bc`). Disassembly confirmed `return_to_fel()` writes
  `0xfa50392f` to `0x070901b8` and `back_in_32` to `0x070901bc`.
- The H713 RTC-mailbox diagnostic failed in the same wedged shape:
  `=> Executing the SPL... done.`, followed by
  `usb_bulk_send() ERROR -7: Operation timed out`. Afterwards `lsusb` still
  showed `1f3a:efe8`, but `./sunxi-fel -v ver` timed out.
- This rules out the known H616/A133 hotplug mailbox, direct alternate-RVBAR
  programming, and the H6-style RTC hotplug mailbox as sufficient H713 A64
  return paths.
- One remaining ambiguity is which AArch64 exception level H713 reaches after
  the A32 boot hook requests the AArch64 RMR transition. The current
  `return_to_fel()` path always writes `RMR_EL3`; if H713 lands at EL1 or EL2,
  that instruction would trap before any return-vector experiment can work.
- A new current-EL RMR diagnostic SPL is ready at
  `/tmp/u-boot-h713-diag-a64-currentel-rmr.6zZXNA/spl/sunxi-spl.bin`. It
  still returns immediately at `save_boot_params_ret`, still writes
  `back_in_32` to the direct H713 RVBAR window `0x08100040`, but then selects
  `RMR_EL1`, `RMR_EL2`, or `RMR_EL3` based on `CurrentEL`. Disassembly confirms
  all three RMR writes are present. Run this after reconnecting the wedged
  board from the RTC-mailbox test.
- The current-EL RMR diagnostic also failed in the familiar wedged shape:
  `=> Executing the SPL... done.`, followed by
  `usb_bulk_send() ERROR -7: Operation timed out`. Afterwards `lsusb` still
  showed `1f3a:efe8`, but `./sunxi-fel -v ver` timed out. This means the
  A64-return failure is not explained solely by writing `RMR_EL3` from the
  wrong exception level.
- The H713 watchdog base is documented by the local H713 Linux DTS at
  `0x02051000`, but a direct FEL reset sequence did not reset the board.
  After writing marker values to the RTC-GP scratch area, the sequence
  `writel 0x02051014 1`, `writel 0x02051018 1`,
  `writel 0x02051010 0x14af` left the device alive in FEL for more than 20
  seconds. Follow-up reads showed `0x02051010 = 0x00000001`,
  `0x02051014 = 0x00000000`, and `0x02051018 = 0x0000001f`.
  Because this reset behavior is not proven, H713 currently has no watchdog
  reset callback in `soc_info.c`.
- A marker/reset diagnostic SPL is ready at
  `/tmp/u-boot-h713-diag-a64-marker-wdreset.NNleWn/spl/sunxi-spl.bin`. It
  writes `"H713"` to `0x070901b8`, `CurrentEL` to `0x070901bc`, and `_start`
  to `0x070901c0`, then triggers the H713 watchdog at `0x02051000`
  (`cfg = 1`, `mode = 1`, `ctl = 0x14af`). Disassembly confirms those writes.
  After reconnecting, run it and then read back `0x070901b8..0x070901c0` if
  FEL comes back after the watchdog reset.
- Before the marker/reset SPL, `0x070901b8`, `0x070901bc`, and `0x070901c0`
  all read back as zero. The marker/reset SPL then failed in the same visible
  shape as the return-path diagnostics: `=> Executing the SPL... done.`,
  followed by `usb_bulk_send() ERROR -7: Operation timed out`. A follow-up
  `./sunxi-fel -v ver` timed out, so the marker registers could not be read.
  This does not yet prove whether A64 failed to reach the marker code or
  whether the watchdog/marker path itself is invalid.
- Direct FEL writes showed that the H6-style RTC mailbox/marker addresses
  `0x070901b8`, `0x070901bc`, and `0x070901c0` read as zero and writes do not
  stick on H713. They are not useful as H713 diagnostic marker storage.
- Vendor boot0's RTC-GP area at `0x07090100` is writable from FEL and was
  proven safe for small markers: `0x07090100` accepted `"H713"`,
  `0x07090104` accepted `0x00000020`, and `0x07090108` accepted
  `0x00104060`. All three were restored to zero and FEL stayed alive.
- A new A64 reset-entry marker-hold diagnostic SPL was built at
  `/tmp/u-boot-h713-diag-a64-rtcgp-marker-hold.aEGpQ3/spl/sunxi-spl.bin`.
  Disassembly confirms that `save_boot_params_ret` writes `"H713"` to
  `0x07090100`, `CurrentEL` to `0x07090104`, and `_start` to `0x07090108`,
  then waits in a `wfi` loop. The first run timed out after
  `=> Executing the SPL... done.`, and a follow-up `./sunxi-fel -v ver` also
  timed out, which is expected for a marker-hold image. After reconnecting,
  FEL was alive again, but `0x07090100`, `0x07090104`, and `0x07090108` all
  read back as zero. This means the reconnect path clears the RTC-GP marker
  state, so this test cannot distinguish "A64 never reached the marker writes"
  from "A64 wrote them, but they were lost during recovery".
- A new A64 reset-entry ERET diagnostic SPL was built at
  `/tmp/u-boot-h713-diag-a64-eret-a32.rXDFIQ/spl/sunxi-spl.bin`. It bypasses
  the RMR reset path and instead sets the current exception level's
  `SPSR_ELx/ELR_ELx` to return directly into the existing AArch32
  `back_in_32` restore stub. This test succeeded: `./sunxi-fel -v spl ...`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves that the saved FEL context and AArch32
  restore stub are valid from A64 reset-entry, and that the H713 failure is in
  the RMR/hotplug return mechanism rather than in the basic A32 restore.
- The H713 `return_to_fel()` path in the local U-Boot tree has been promoted
  to use this ERET helper by default, leaving the older RMR/mailbox paths
  available only behind diagnostic defines. A board-init-entry diagnostic built
  at `/tmp/u-boot-h713-diag-board-init-eret.ZUWm5V/spl/sunxi-spl.bin` still
  timed out when the helper only cleared `SCR_EL3.RW`, so the helper was
  adjusted to also clear `SCR_EL3[3:0]` before returning to AArch32. The
  rebuilt image succeeded: `./sunxi-fel -v spl ...` returned without timeout,
  and a follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report.

The FEL upload, SRAM handoff, AArch32 boot hook entry, and raw A64-to-A32 ERET
return are now proven, including after `board_init_f()` entry once the helper
restores SCR state. A pre-DRAM diagnostic built at
`/tmp/u-boot-h713-diag-pre-dram-eret.LnE5dd/spl/sunxi-spl.bin` timed out and
left FEL unresponsive when run after an earlier successful checkpoint, but
later tests showed that second-SPL uploads can be misleading. Retest this
pre-DRAM image first in a fresh FEL session before treating it as a real
`sunxi_board_init()`/DRAM boundary. Narrower checkpoint images have been built:
`/tmp/u-boot-h713-diag-after-sram-eret.2XzJBa/spl/sunxi-spl.bin`,
`/tmp/u-boot-h713-diag-after-timer-eret.B1Q3zc/spl/sunxi-spl.bin`, and
`/tmp/u-boot-h713-diag-after-clock-eret.kIdFf8/spl/sunxi-spl.bin`, plus
`/tmp/u-boot-h713-diag-after-gpio-eret.Y8oRlf/spl/sunxi-spl.bin`. The next
hardware probe should start with the after-SRAM image and advance through the
ladder until FEL stops returning.
- The after-SRAM checkpoint succeeded: `./sunxi-fel -v spl ...after-sram...`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `sunxi_sram_init()` as the cause.
- The after-timer checkpoint then timed out and left FEL unresponsive. However,
  this image was run as the second SPL upload in the same FEL session, and its
  `timer_init()` disassembles to the weak no-op implementation
  (`mov w0, wzr; ret`). To remove that possible session-order confound, retest
  `/tmp/u-boot-h713-diag-after-timer-eret.B1Q3zc/spl/sunxi-spl.bin` first
  immediately after reconnecting.
- Retesting the after-timer checkpoint first in a fresh FEL session succeeded:
  `./sunxi-fel -v spl ...after-timer...` returned without timeout, and a
  follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report. This
  clears the no-op `timer_init()` boundary and confirms that at least some
  second-SPL runs can be misleading.
- The after-clock checkpoint was then run as the second SPL upload in that same
  session and timed out, with a follow-up `./sunxi-fel -v ver` also timing out.
  This is inconclusive until the after-clock image is retested first after a
  reconnect. If after-clock fails first, the boundary is `clock_init()`. If it
  passes first, the remaining issue is the post-return FEL/SRAM state affecting
  later SPL uploads.
- Retesting the after-clock checkpoint first in a fresh FEL session succeeded:
  `./sunxi-fel -v spl ...after-clock...` returned without timeout, and a
  follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report. This
  clears `clock_init()` as the cause. The next clean checkpoint is
  `/tmp/u-boot-h713-diag-after-gpio-eret.Y8oRlf/spl/sunxi-spl.bin`, run first
  immediately after reconnecting.
- Retesting the after-GPIO checkpoint first in a fresh FEL session succeeded:
  `./sunxi-fel -v spl ...after-gpio...` returned without timeout, and a
  follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report. This
  clears the UART pinmux setup plus the H713 PIO/R_PIO power-mode register
  writes. The next clean checkpoint is
  `/tmp/u-boot-h713-diag-after-spl-eret.zdZerQ/spl/sunxi-spl.bin`, run first
  immediately after reconnecting.
- Retesting the after-SPL checkpoint first in a fresh FEL session succeeded:
  `./sunxi-fel -v spl ...after-spl...` returned without timeout, and a
  follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report. This
  clears `spl_init()`. The next clean checkpoint is
  `/tmp/u-boot-h713-diag-after-console-eret.EuF1jG/spl/sunxi-spl.bin`, run
  first immediately after reconnecting.
- Additional checkpoints are ready for the next rungs:
  `/tmp/u-boot-h713-diag-after-spl-eret.zdZerQ/spl/sunxi-spl.bin` returns
  after `spl_init()`, and
  `/tmp/u-boot-h713-diag-after-console-eret.EuF1jG/spl/sunxi-spl.bin` returns
  after `preloader_console_init()`. Disassembly confirms both return points
  are placed as intended.
- Retesting the after-console checkpoint first in a fresh FEL session failed:
  `./sunxi-fel -v spl ...after-console...` timed out after
  `=> Executing the SPL... done.`, and a follow-up `./sunxi-fel -v ver` also
  timed out. This makes the current real boundary `preloader_console_init()`,
  after `spl_init()` has already been cleared.
- The after-console SPL disassembly shows that `preloader_console_init()` sets
  `gd->baudrate = 115200`, calls `serial_init()`, sets
  `GD_FLG_HAVE_CONSOLE`, and then tail-branches to `puts()` for the banner.
  Two narrower console checkpoints are now built:
  `/tmp/u-boot-h713-diag-after-serial-eret.QIW0uO/spl/sunxi-spl.bin` returns
  immediately after `serial_init()`, before `GD_FLG_HAVE_CONSOLE` or `puts()`;
  `/tmp/u-boot-h713-diag-console-ready-eret.boV4xi/spl/sunxi-spl.bin` returns
  after `GD_FLG_HAVE_CONSOLE` is set, but before `puts()`. Disassembly confirms
  both return points.
- On the next reconnect attempt, `lsusb` did not show the Allwinner FEL device
  and two direct `./sunxi-fel -v ver` probes reported
  `ERROR: Allwinner USB FEL device not found!`. No SPL was uploaded in that
  session. The next clean hardware probe is still the after-serial checkpoint,
  run first immediately after a successful FEL enumeration.
- Retesting the original after-serial checkpoint first in a fresh FEL session
  failed: `./sunxi-fel -v spl ...after-serial...` timed out after
  `=> Executing the SPL... done.`, and a follow-up `./sunxi-fel -v ver` also
  timed out. Disassembly of that image showed the legacy SPL serial path was
  initializing UART0 at `0x05000000`.
- Local H713 sources consistently identify UART0 as `0x02500000`:
  `<local>/allwinner-h713-linux/dts/sun50i-h713-hy310.dts`,
  `<local>/h713-lab/notes/board-a-stock-boot-map-20260622.txt`,
  and the local U-Boot H713 DTS all point to `uart@2500000` / earlyprintk
  `sunxi-uart,0x02500000`. The stale `0x05000000` value came from H6-family
  early SPL serial base selection.
- U-Boot `arch/arm/include/asm/arch-sunxi/serial.h` has been adjusted so
  `CONFIG_MACH_SUN50I_H713` selects the NCAT2-style UART0 base
  `0x02500000`, ahead of the broader `CONFIG_SUN50I_GEN_H6` branch. Corrected
  diagnostics were built and disassembled:
  `/tmp/u-boot-h713-diag-after-serial-fixed-eret.XL069M/spl/sunxi-spl.bin`
  returns immediately after `serial_init()`, and
  `/tmp/u-boot-h713-diag-console-ready-fixed-eret.FWjJ3Y/spl/sunxi-spl.bin`
  returns after `GD_FLG_HAVE_CONSOLE` is set but before `puts()`. Both images
  now use `0x02500000` for `eserial1_init()` and related UART operations.
- The next clean hardware probe is the corrected after-serial image
  `/tmp/u-boot-h713-diag-after-serial-fixed-eret.XL069M/spl/sunxi-spl.bin`,
  run first immediately after reconnecting.
- Retesting the corrected after-serial checkpoint first in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-serial-fixed-eret.XL069M/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `serial_init()` once H713 uses UART0
  base `0x02500000`, and confirms that the previous after-serial failure was
  caused by the stale H6-family `0x05000000` UART base.
- The next clean hardware probe is the corrected console-ready image
  `/tmp/u-boot-h713-diag-console-ready-fixed-eret.FWjJ3Y/spl/sunxi-spl.bin`,
  run first immediately after reconnecting. If it passes, the next boundary is
  the banner `puts()` / first UART transmit path.
- Retesting the corrected console-ready checkpoint first in a fresh FEL
  session succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-console-ready-fixed-eret.FWjJ3Y/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the `GD_FLG_HAVE_CONSOLE` flag update
  path after `serial_init()`.
- A corrected full after-console checkpoint is now built at
  `/tmp/u-boot-h713-diag-after-console-fixed-eret.luyEwB/spl/sunxi-spl.bin`.
  It uses `CONFIG_H713_FEL_DIAG_RETURN_AFTER_CONSOLE_INIT`, so it runs through
  `preloader_console_init()` including the banner `puts()` path, then returns
  to FEL from `board_init_f()`. Disassembly confirms the return point after
  `preloader_console_init()` and confirms `eserial1_init()` uses UART0 base
  `0x02500000`.
- The next clean hardware probe is the corrected full after-console image,
  run first immediately after reconnecting. If it passes, the corrected UART
  base fully resolves the previous console boundary and testing can move back
  to the pre-DRAM checkpoint.
- Retesting the corrected full after-console checkpoint first in a fresh FEL
  session succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-console-fixed-eret.luyEwB/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the full `preloader_console_init()` path,
  including the banner `puts()` / first UART transmit path, with UART0 base
  `0x02500000`.
- A corrected pre-DRAM checkpoint is now built at
  `/tmp/u-boot-h713-diag-pre-dram-fixed-eret.w4xtZ9/spl/sunxi-spl.bin`. It
  uses `CONFIG_H713_FEL_DIAG_RETURN_BEFORE_DRAM`, so it returns to FEL just
  before `printf("DRAM:")` and `sunxi_dram_init()`. Disassembly confirms the
  `sunxi_return_to_fel()` call precedes `sunxi_dram_init()`, and confirms
  `eserial1_init()` uses UART0 base `0x02500000`.
- The next clean hardware probe is the corrected pre-DRAM image, run first
  immediately after reconnecting. If it passes, the next real boundary is
  inside `sunxi_dram_init()` / H713 DRAM training rather than console setup.
- Retesting the corrected pre-DRAM checkpoint first in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-pre-dram-fixed-eret.w4xtZ9/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears all board setup through the point just
  before `printf("DRAM:")`.
- A new after-DRAM-banner checkpoint is now built at
  `/tmp/u-boot-h713-diag-after-dram-banner-eret.YZAism/spl/sunxi-spl.bin`.
  It uses `CONFIG_H713_FEL_DIAG_RETURN_AFTER_DRAM_BANNER`, so it executes
  `printf("DRAM:")`, returns to FEL, and still avoids `sunxi_dram_init()`.
  Disassembly confirms the sequence `printf`, `sunxi_return_to_fel()`,
  `sunxi_dram_init()`, and confirms `eserial1_init()` uses UART0 base
  `0x02500000`.
- The next clean hardware probe is the after-DRAM-banner image, run first
  immediately after reconnecting. If it passes, the next boundary is truly
  inside `sunxi_dram_init()`.
- Retesting the after-DRAM-banner checkpoint first in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-dram-banner-eret.YZAism/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `printf("DRAM:")`; the next boundary is
  inside `sunxi_dram_init()`.
- A new DRAM-init-entry checkpoint is now built at
  `/tmp/u-boot-h713-diag-dram-init-entry-eret.8zY7tq/spl/sunxi-spl.bin`. It
  uses `CONFIG_H713_FEL_DIAG_RETURN_DRAM_INIT_ENTRY`, so it returns to FEL at
  the start of `sunxi_dram_init()`, before the first PRCM writes
  (`CCU_PRCM_RES_CAL_CTRL` / `CCU_PRCM_OHMS240`). Disassembly confirms the
  `sunxi_return_to_fel()` call immediately after the function prologue and
  confirms `eserial1_init()` uses UART0 base `0x02500000`.
- Retesting the DRAM-init-entry checkpoint first in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-dram-init-entry-eret.8zY7tq/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears entry into `sunxi_dram_init()` and
  proves the next boundary is after the first PRCM/DRAM-resistance calibration
  writes.
- DRAM-value evidence now has three local source tiers. The older
  `<local>/sun50iw12p1-research/` HY300 notes/configs describe a
  640 MHz DDR3-style block (`dram_clk = 640`, `dram_type = 3`,
  `dram_zq = 0x7b7bfb`, `dram_odt_en = 0x1`, `dram_tpr0 = 0x004a2195`,
  `dram_tpr2 = 0x0008b061`, `dram_tpr6 = 0x48`,
  `dram_tpr10 = 0x0`, `dram_tpr11 = 0x44440000`,
  `dram_tpr12 = 0x00005555`). The HY310 Linux repo's
  `<local>/allwinner-h713-linux/reference/sys_config.fex` instead
  uses 792 MHz DDR3-style values with the same `tpr0/tpr2/tpr6/tpr10` and
  `dram_tpr11 = 0x44340000`, `dram_tpr12 = 0x00006666`.
- The strongest currently checked evidence for this board family is the stock
  BT0 dump in `<local>/h713-lab/analysis/board-a-stock-20260622/`.
  Both `bt0-8KiB-exact-32KiB.img` and `bt0-128KiB-exact-32KiB.img` have the
  same SHA-256
  `f8ac16e44a83869c8fa7193531bc3a8b228235428a99ac426daa0902026c9f0f` and the
  same DRAM parameter window. Interpreting the block from the word after the
  leading zero at offset `0x30` gives:
  `unknown = 0x00000008`, `dram_clk = 0x000002d0` (720),
  `dram_type = 0x00000007` (LPDDR3 in U-Boot's H616-family enum),
  `dram_zq = 0x003f3ffb`, `dram_odt_en_or_flags = 0x00000031`,
  `dram_para1 = 0x10f410f4`, `dram_para2 = 0x04000000`,
  `dram_mr0 = 0x0`, `dram_mr1 = 0xc3`, `dram_mr2 = 0x0a`,
  `dram_mr3 = 0x02`, `dram_tpr0 = 0x0049225a`,
  `dram_tpr1 = 0x01b1b1d0`, `dram_tpr2 = 0x0004c02c`,
  `dram_tpr3 = 0xb4787896`, `dram_tpr5 = 0x48484848`,
  `dram_tpr6 = 0x48`, `dram_tpr7 = 0x1621121e`,
  `dram_tpr10 = 0x00007767`, `dram_tpr11 = 0x44650000`,
  `dram_tpr12 = 0x00005544`, and `dram_tpr13 = 0xb4036223`.
- This means the current local `hy310_h713_defconfig` is still a seed, not a
  proven DRAM config: it uses `CONFIG_DRAM_CLK=792` and
  `CONFIG_SUNXI_DRAM_H616_DDR3_1333=y`, while the stock BT0 window points at
  720 MHz LPDDR3. Before full DRAM training, prefer either a
  firmware-derived H616-field mapping or another narrow checkpoint.
- A new after-PRCM-calibration checkpoint should return immediately after
  `setbits_le32(prcm + CCU_PRCM_RES_CAL_CTRL, BIT(8))` and
  `clrbits_le32(prcm + CCU_PRCM_OHMS240, 0x3f)`, before
  `mctl_auto_detect_rank_width()`.
- The after-PRCM-calibration checkpoint was built at
  `/tmp/u-boot-h713-diag-after-prcm-cal-eret.F6Se9U/spl/sunxi-spl.bin`.
  Because the symbol is intentionally local and not a Kconfig entry, the
  successful build used
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_PRCM_CAL'`.
  Disassembly confirms `sunxi_dram_init()` performs the two PRCM writes, then
  branches to `sunxi_return_to_fel()`, before `mctl_auto_detect_rank_width()`.
- Running that after-PRCM-calibration checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-prcm-cal-eret.F6Se9U/spl/sunxi-spl.bin`
  printed the normal SPL header details and `=> Executing the SPL... done.`,
  but returned `usb_bulk_send() ERROR -7: Operation timed out`. A follow-up
  `./sunxi-fel -v ver` also timed out, although `lsusb` still showed
  `1f3a:efe8`. Treat this as a real failure at or immediately after the PRCM
  calibration writes, requiring a physical reconnect before the next probe.
- The next narrower hardware probe should split those two PRCM writes: first
  return after only `CCU_PRCM_RES_CAL_CTRL |= BIT(8)`, before touching
  `CCU_PRCM_OHMS240`.
- A narrower after-RES-CAL-set checkpoint is now built at
  `/tmp/u-boot-h713-diag-after-rescal-set-eret.wYziIN/spl/sunxi-spl.bin`.
  It was built with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_RESCAL_SET'`.
  Disassembly confirms the sequence is `RES_CAL_CTRL |= BIT(8)`, then
  `sunxi_return_to_fel()`, then the later `OHMS240` access and rank/width
  detection only if the return did not happen.
- Running the after-RES-CAL-set checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-rescal-set-eret.wYziIN/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves that the first inherited H616 PRCM
  calibration write, `0x07010310 |= BIT(8)`, is not the operation that wedges
  the board.
- Direct FEL MMIO probes after that successful checkpoint also stayed healthy:
  `readl 0x07010310` returned `0x00000000`, `readl 0x07010318` returned
  `0x00000000`, `writel 0x07010310 0x00000100` returned normally but still read
  back as `0x00000000`, and `writel 0x07010318 0x00000000` returned normally.
  A follow-up `ver` still returned the normal H713 ROM report. This means the
  PRCM addresses are at least reachable from FEL's AArch32 helper path, though
  the `0x07010310` bit does not appear to stick.
- Retesting the after-PRCM-calibration SPL reproduced the original failure:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-prcm-cal-eret.F6Se9U/spl/sunxi-spl.bin` timed out
  during the post-execute USB status phase, and a follow-up `ver` also timed
  out. The board needs another physical reconnect before additional FEL
  commands. The failure is now narrower than simple MMIO reachability: it is
  tied to the SPL execution path after the second inherited PRCM operation, or
  to CPU/exception-state restoration immediately after that sequence.
- To split the second inherited PRCM operation further, the local U-Boot DRAM
  driver now has diagnostic hooks around the `OHMS240` read and write. A new
  after-`OHMS240`-read checkpoint is built at
  `/tmp/u-boot-h713-diag-after-ohms-read-eret.Y0bG2W/spl/sunxi-spl.bin` with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_OHMS_READ'`.
  Disassembly confirms it executes `RES_CAL_CTRL |= BIT(8)`, then loads
  `0x07010318`, then branches to `sunxi_return_to_fel()` before storing back to
  `0x07010318`. This is the next checkpoint to run after a reconnect.
- If the after-`OHMS240`-read checkpoint succeeds, the matching
  after-`OHMS240`-write checkpoint is ready at
  `/tmp/u-boot-h713-diag-after-ohms-write-eret.FMVRpY/spl/sunxi-spl.bin`.
  It was built with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_OHMS_WRITE'`.
  Disassembly confirms it performs the read/barrier/write sequence against
  `0x07010318`, then branches to `sunxi_return_to_fel()` before DRAM rank/width
  detection.
- Running the after-`OHMS240`-read checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-ohms-read-eret.Y0bG2W/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the `OHMS240` read in SPL context.
- Running the after-`OHMS240`-write checkpoint immediately afterward failed:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-after-ohms-write-eret.FMVRpY/spl/sunxi-spl.bin` timed
  out during the post-execute USB status phase, and a follow-up `ver` also
  timed out. This pins the current SPL wedge to the write-back to
  `0x07010318`, not the preceding read. The board needs another physical
  reconnect before more hardware probes.
- A diagnostic skip-`OHMS240`-write checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-write-after-prcm-eret.QxUORn/spl/sunxi-spl.bin`.
  It was built with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_PRCM_CAL'`.
  Disassembly confirms it still executes `RES_CAL_CTRL |= BIT(8)` and reads
  `0x07010318`, but skips the store to `0x07010318` on H713 and then branches
  to `sunxi_return_to_fel()` before DRAM rank/width detection. This is the next
  checkpoint to run after a reconnect.
- Running the skip-`OHMS240`-write checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-write-after-prcm-eret.QxUORn/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This confirms the `0x07010318` store is the current
  bad PRCM operation, and that the rest of the pre-rank/width path can survive
  if that store is skipped.
- A skip-`OHMS240`-write after-rank/width checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-rank-width-eret.GwgKRM/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_RANK_WIDTH'`.
  Disassembly confirmed it skips the `0x07010318` store, calls
  `mctl_auto_detect_rank_width()`, then branches to `sunxi_return_to_fel()`
  before DRAM size detection.
- Running that after-rank/width checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-rank-width-eret.GwgKRM/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up `ver`
  also timed out. This pins the next wedge inside
  `mctl_auto_detect_rank_width()`, most likely in its first
  `mctl_core_init()` trial (`bus_full_width = 1`, `ranks = 2`). The board needs
  another physical reconnect before more hardware probes.
- The next split is inside `mctl_core_init()`: return after `mctl_sys_init()`
  and before `mctl_ctrl_init()`, with the `OHMS240` write still skipped.
- That after-`mctl_sys_init()` checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-sys-init-eret.F0F6oz/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_SYS_INIT'`.
  Disassembly confirms the branch to `sunxi_return_to_fel()` occurs after the
  inlined `mctl_sys_init()` clock/reset sequence and before the controller init
  body. This is the next checkpoint to run after a reconnect.
- Running the after-`mctl_sys_init()` checkpoint in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-mctl-sys-init-eret.F0F6oz/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the H616-style DRAM clock/reset setup on
  H713 when the bad `OHMS240` write is skipped. The next boundary is inside
  `mctl_ctrl_init()`.
- A skip-`OHMS240`-write early-`mctl_ctrl_init()` checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-early-eret.xVhBEs/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_EARLY'`.
  Disassembly confirmed it returns after the early controller setup
  (`MSTR`, ODT config, and `mctl_com->cr`) and before address-map/timing work.
- Running that early-`mctl_ctrl_init()` checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-early-eret.xVhBEs/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up `ver`
  also timed out. This pins the next wedge to the first part of
  `mctl_ctrl_init()`, before address-map, timing, DFI, or PHY init. The board
  needs another physical reconnect before more hardware probes.
- The next narrower checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-clken-eret.z9TmkB/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_CLKEN'`.
  Disassembly confirms it returns immediately after the first
  `mctl_ctrl_init()` enable cluster, before the later `unk_0x008`, scheduler,
  MSTR, ODT, address-map, timing, DFI, or PHY setup. This is the next
  checkpoint to run after a reconnect.
- Running the after-`mctl_ctrl_init()` `clken` checkpoint in a fresh FEL
  session succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-clken-eret.z9TmkB/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the first controller-enable cluster.
- A skip-`OHMS240`-write pre-MSTR checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-pre-mstr-eret.aGR5b0/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_PRE_MSTR'`.
  Disassembly confirmed it returns after the scheduler/`hwlpctl`/second
  `unk_0x008` block and before MSTR/ODT setup.
- Running that pre-MSTR checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-pre-mstr-eret.aGR5b0/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up `ver`
  also timed out. This pins the current wedge between the passing `clken`
  checkpoint and the MSTR setup: the first `unk_0x008` set, scheduler write,
  `hwlpctl` clear, or second `unk_0x008` set. The board needs another physical
  reconnect before more hardware probes.
- The next narrower checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-unk008-eret.qtdfDl/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_UNK008'`.
  Disassembly confirms it returns immediately after the first
  `mctl_com->unk_0x008 |= 0xff00` write, before the scheduler and `hwlpctl`
  writes. This is the next checkpoint to run after a reconnect.
- The `/tmp` artifact above was rebuilt as
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-unk008-eret.3Ulp17/spl/sunxi-spl.bin`
  and run in a fresh FEL session. It returned without timeout, and a follow-up
  `./sunxi-fel -v ver` returned the normal H713 ROM report. This clears the
  first `mctl_com->unk_0x008 |= 0xff00` write. The remaining suspect block is
  now the scheduler write, `hwlpctl` clear, or second `unk_0x008` set.
- A scheduler checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-sched-eret.yJMvhR/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_SCHED'`.
  Disassembly confirmed it returns after the scheduler register update and
  before `hwlpctl`.
- Running that scheduler checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-sched-eret.yJMvhR/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up `ver`
  also timed out. This pins the current wedge to the scheduler
  read-modify-write in `mctl_ctrl_init()`, before `hwlpctl` or the second
  `unk_0x008` set. The board needs another physical reconnect before more
  hardware probes.
- To split the scheduler read-modify-write, the local U-Boot DRAM driver now
  has a diagnostic return between the scheduler read and write. A read-only
  scheduler checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-sched-read-eret.MnrzQJ/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_SCHED_READ'`.
  Disassembly confirms it reads `sched[0]`, then branches to
  `sunxi_return_to_fel()` before writing the modified value. This is the next
  checkpoint to run after a reconnect.
- Running the read-only scheduler checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-after-mctl-ctrl-sched-read-eret.MnrzQJ/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the scheduler read and pins the current
  scheduler failure to the write-back.
- A skip-scheduler-write pre-MSTR checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-after-pre-mstr-eret.hSHZX5/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_SKIP_MCTL_CTRL_SCHED_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_PRE_MSTR'`.
  Disassembly confirmed the scheduler register is read but not written, then
  `hwlpctl` is cleared and the second `unk_0x008` set runs before returning.
- Running the skip-scheduler-write pre-MSTR checkpoint failed: `./sunxi-fel -v
  spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-after-pre-mstr-eret.hSHZX5/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up `ver`
  also timed out. This means the scheduler write is bad, but not the only bad
  operation in this block: with that write skipped, either `hwlpctl = 0` or the
  second `unk_0x008 |= 0xff00` still wedges the board. The board needs another
  physical reconnect before more hardware probes.
- A skip-scheduler-write after-`hwlpctl` checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-after-hwlpctl-eret.CAp42M/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_SKIP_MCTL_CTRL_SCHED_WRITE -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_HWLPCTL'`.
  Disassembly confirms it skips the scheduler write, clears `hwlpctl`, then
  branches to `sunxi_return_to_fel()` before the second
  `mctl_com->unk_0x008 |= 0xff00`. This is the next checkpoint to run after a
  reconnect.
- Running that after-`hwlpctl` checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-after-hwlpctl-eret.CAp42M/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `hwlpctl = 0`. Because the earlier
  skip-scheduler-write pre-MSTR checkpoint still failed, the remaining bad
  operation in this block is the second `mctl_com->unk_0x008 |= 0xff00`.
- A skip-`OHMS240`, skip-scheduler-write, skip-second-`unk_0x008` pre-MSTR
  checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-pre-mstr-eret.lYwql8/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_SKIP_MCTL_CTRL_SCHED_WRITE -DCONFIG_H713_FEL_DIAG_SKIP_MCTL_CTRL_SECOND_UNK008 -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_PRE_MSTR'`.
  Disassembly confirms it reads but does not write the scheduler register,
  clears `hwlpctl`, omits the second `mctl_com->unk_0x008 |= 0xff00`, and
  branches to `sunxi_return_to_fel()` before the MSTR/ODT setup. The instruction
  stream from the scheduler read through the return call matches the earlier
  passing after-`hwlpctl` checkpoint.
- Running that skip-second-`unk_0x008` pre-MSTR checkpoint in a fresh FEL
  session failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-pre-mstr-eret.lYwql8/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. Because the executed path should be
  equivalent to the passing after-`hwlpctl` checkpoint, treat this as an
  anomalous result that needs a repeat before drawing a new register-map
  conclusion.
- After a reconnect, repeating that same skip-second-`unk_0x008` pre-MSTR
  checkpoint succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-pre-mstr-eret.lYwql8/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This confirms the previous failure was transient and
  clears the path up to the MSTR/ODT/CR cluster when the three known-bad writes
  are skipped.
- The next all-known-bad-writes-skipped early-controller checkpoint is built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-ctrl-early-eret.hUGUlS/spl/sunxi-spl.bin`
  with
  `KCFLAGS='-fintegrated-as -DCONFIG_H713_FEL_DIAG_SKIP_OHMS_WRITE -DCONFIG_H713_FEL_DIAG_SKIP_MCTL_CTRL_SCHED_WRITE -DCONFIG_H713_FEL_DIAG_SKIP_MCTL_CTRL_SECOND_UNK008 -DCONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_EARLY'`.
  Disassembly confirms it still skips the `OHMS240`, scheduler, and second
  `unk_0x008` writes, then returns after the early MSTR/ODT/CR writes at
  `0x104c9c`, before address mapping and timing setup.
- Running that early-controller checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-ctrl-early-eret.hUGUlS/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins the next failure inside the
  MSTR/ODT/CR cluster, after the pre-MSTR checkpoint and before address mapping.
- The U-Boot DRAM driver now has narrower H713-only diagnostic hooks after
  `mstr`, `odtmap`, the ODT config/shadow writes, and `mctl_com->cr`. Three
  queued SPL checkpoints are built with the known-bad `OHMS240`, scheduler, and
  second `unk_0x008` writes skipped:
  after-MSTR at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-mstr-eret.6ktoA2/spl/sunxi-spl.bin`,
  after-ODTMAP at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-odtmap-eret.0oDSsU/spl/sunxi-spl.bin`,
  and after-ODTCFG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-odtcfg-eret.0Yh0uv/spl/sunxi-spl.bin`.
  Disassembly confirms the after-MSTR image returns at `0x104c04`, the
  after-ODTMAP image returns at `0x104c20`, and the after-ODTCFG image returns
  at `0x104c8c` before the `mctl_com->cr` write. Run them in that order after
  the next reconnect.
- After a reconnect, running the after-MSTR checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-mstr-eret.6ktoA2/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the `mctl_ctl->mstr` write when the known
  bad writes are skipped.
- Running the after-ODTMAP checkpoint immediately afterward failed:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-after-odtmap-eret.0oDSsU/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins the current failure to the
  `mctl_ctl->odtmap` write, currently `0x0201` on the one-rank path.
- A temporary H713-only skip hook for the ODTMAP write was added to the U-Boot
  DRAM driver. Two queued SPL checkpoints are built with the known-bad
  `OHMS240`, scheduler, second `unk_0x008`, and ODTMAP writes skipped:
  after-ODTCFG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-after-odtcfg-eret.WaXlGX/spl/sunxi-spl.bin`
  and after-CR at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-after-cr-eret.3mLZVd/spl/sunxi-spl.bin`.
  Disassembly confirms the skip-ODTMAP after-ODTCFG image returns at `0x104c70`
  before the `mctl_com->cr` write, and the skip-ODTMAP after-CR image returns
  at `0x104c80` immediately after the CR write. Run the skip-ODTMAP
  after-ODTCFG image first after the next reconnect.
- After a reconnect, running the skip-ODTMAP after-ODTCFG checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-after-odtcfg-eret.WaXlGX/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the ODT config and shadow writes when
  ODTMAP is skipped.
- Running the skip-ODTMAP after-CR checkpoint immediately afterward failed:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-after-cr-eret.3mLZVd/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins another bad operation to the
  `mctl_com->cr = BIT(31)` write.
- A temporary H713-only skip hook for the `mctl_com->cr` write was added. Two
  queued SPL checkpoints are built with the known-bad `OHMS240`, scheduler,
  second `unk_0x008`, ODTMAP, and CR writes skipped: after-ADDRMAP at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-addrmap-eret.RptORo/spl/sunxi-spl.bin`
  and after-TIMING at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-eret.6fEGO3/spl/sunxi-spl.bin`.
  Disassembly confirms the after-ADDRMAP image returns at `0x104d9c`, and the
  after-TIMING image returns at `0x104da4`. Run the after-ADDRMAP image first
  after the next reconnect.
- After a reconnect, running the skip-ODTMAP/CR after-ADDRMAP checkpoint
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-addrmap-eret.RptORo/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `mctl_set_addrmap()` with the current
  skip set.
- Running the skip-ODTMAP/CR after-TIMING checkpoint immediately afterward
  failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-eret.6fEGO3/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins the next failure inside the
  H616 DDR3 timing object currently selected by `hy310_h713_defconfig`.
- The H616 DDR3 timing object now has H713-only diagnostic return hooks after
  the `dramtmg[]`, `init[]`, `dfimisc`/`rankctl`, DFI timing, and refresh
  timing groups. Four queued SPL checkpoints are built with the known-bad
  `OHMS240`, scheduler, second `unk_0x008`, ODTMAP, and CR writes skipped:
  after-DRAMTMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-dramtmg-eret.XaySnG/spl/sunxi-spl.bin`,
  after-INIT at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init-eret.NEYVc0/spl/sunxi-spl.bin`,
  after-RANKCTL at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-rankctl-eret.YtpS86/spl/sunxi-spl.bin`,
  and after-DFITMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-dfitmg-eret.wyepWB/spl/sunxi-spl.bin`.
  Disassembly confirms return calls at `0x106a40`, `0x106a78`, `0x106a90`,
  and `0x106aa8`, respectively. Run them in that order after the next
  reconnect.
- After a reconnect, running the after-DRAMTMG checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-dramtmg-eret.XaySnG/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the `dramtmg[]` writes in the selected
  H616 DDR3 timing object.
- Running the after-INIT checkpoint immediately afterward failed:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init-eret.NEYVc0/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins the next failure inside the
  timing `init[]` group.
- The H616 DDR3 timing object now has more granular H713-only diagnostic
  return hooks after the first four `init[]` writes. Four queued SPL
  checkpoints are built with the known-bad `OHMS240`, scheduler, second
  `unk_0x008`, ODTMAP, and CR writes skipped: after-INIT0 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init0-eret.vpNAPM/spl/sunxi-spl.bin`,
  after-INIT1 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init1-eret.clrB4F/spl/sunxi-spl.bin`,
  after-INIT2 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init2-eret.rRo2v8/spl/sunxi-spl.bin`,
  and after-INIT3 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init3-eret.MDf9y1/spl/sunxi-spl.bin`.
  Disassembly confirms return calls at `0x106a4c`, `0x106a58`, `0x106a5c`,
  and `0x106a6c`, respectively. Run them in that order after the next
  reconnect.
- After a reconnect, running the after-INIT0 checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init0-eret.vpNAPM/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the `init[0]` clear in the selected H616
  DDR3 timing object.
- Running the after-INIT1 checkpoint immediately afterward failed:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-after-timing-init1-eret.clrB4F/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins the current timing failure to
  `mctl_ctl->init[1] = 0x420000`.
- A temporary H713-only skip hook for the `init[1]` write was added. Three
  queued SPL checkpoints are built with the known-bad `OHMS240`, scheduler,
  second `unk_0x008`, ODTMAP, CR, and timing `init[1]` writes skipped:
  after-INIT2 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-init2-eret.jSLCmi/spl/sunxi-spl.bin`,
  after-INIT3 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-init3-eret.r6VZ13/spl/sunxi-spl.bin`,
  and after-INIT at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-init-eret.kYoWrd/spl/sunxi-spl.bin`.
  Disassembly confirms return calls at `0x106a50`, `0x106a60`, and `0x106a6c`,
  respectively. Run them in that order after the next reconnect.
- Three later timing checkpoints are also queued with the same skip set:
  after-RANKCTL at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-rankctl-eret.Soq1zc/spl/sunxi-spl.bin`,
  after-DFITMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-dfitmg-eret.2hxl4E/spl/sunxi-spl.bin`,
  and after-RFSHTMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-rfshtmg-eret.dTn9gv/spl/sunxi-spl.bin`.
  Disassembly confirms return calls at `0x106a84`, `0x106a9c`, and
  `0x106aa0`, respectively.
- After the next physical reconnect attempt, `lsusb -d 1f3a:efe8` showed the
  FEL device as `Bus 005 Device 018`, but two harmless `./sunxi-fel -v ver`
  attempts both timed out with `usb_bulk_send() ERROR -7: Operation timed out`.
  No SPL was launched during this attempt. The next hardware test is still the
  skip-`init[1]` after-INIT2 checkpoint above.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-`init[1]` after-INIT2 checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-init2-eret.jSLCmi/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `mctl_ctl->init[2] = 5` with the current
  skip set.
- Running the skip-`init[1]` after-INIT3 checkpoint immediately afterward
  failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-after-timing-init3-eret.r6VZ13/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This pins the next timing failure to
  `mctl_ctl->init[3] = 0x1f140004`.
- A temporary H713-only skip hook for the `init[3]` write was added. Four
  queued SPL checkpoints are built with the known-bad `OHMS240`, scheduler,
  second `unk_0x008`, ODTMAP, CR, timing `init[1]`, and timing `init[3]`
  writes skipped: after-INIT at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-init-eret.SasBhR/spl/sunxi-spl.bin`,
  after-RANKCTL at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-rankctl-eret.0LLEJ7/spl/sunxi-spl.bin`,
  after-DFITMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-dfitmg-eret.65mWGI/spl/sunxi-spl.bin`,
  and after-RFSHTMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-rfshtmg-eret.IQR4Nk/spl/sunxi-spl.bin`.
  Disassembly confirms return calls/branch at `0x106a5c`, `0x106a74`,
  `0x106a8c`, and `0x106a90`, respectively. Run the after-INIT image first
  after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-`init[1]`/skip-`init[3]` after-INIT checkpoint
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-init-eret.SasBhR/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `mctl_ctl->init[4] = 0x00200000` with
  the current skip set.
- Running the skip-`init[1]`/skip-`init[3]` after-RANKCTL checkpoint
  immediately afterward failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-rankctl-eret.0LLEJ7/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. This narrows the next failure to either
  `mctl_ctl->dfimisc = 0` or the `rankctl` update
  `clrsetbits_le32(&mctl_ctl->rankctl, 0xff0, 0x660)`.
- A temporary H713-only return hook after the `dfimisc` write and a temporary
  skip hook for the `rankctl` update were added. Three queued SPL checkpoints
  are built with the known-bad `OHMS240`, scheduler, second `unk_0x008`,
  ODTMAP, CR, timing `init[1]`, and timing `init[3]` writes skipped:
  after-DFIMISC at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-dfimisc-eret.1XqX6I/spl/sunxi-spl.bin`,
  skip-RANKCTL after-DFITMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-after-timing-dfitmg-eret.0qfnTz/spl/sunxi-spl.bin`,
  and skip-RANKCTL after-RFSHTMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-after-timing-rfshtmg-eret.SZSogQ/spl/sunxi-spl.bin`.
  Disassembly confirms return calls/branch at `0x106a64`, `0x106a7c`, and
  `0x106a80`, respectively. Run the after-DFIMISC image first after the next
  reconnect; if it passes, the already-failed after-RANKCTL result pins
  `rankctl`, so continue with the skip-RANKCTL after-DFITMG image instead of
  rerunning after-RANKCTL.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the after-DFIMISC checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-after-timing-dfimisc-eret.1XqX6I/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `mctl_ctl->dfimisc = 0` and pins the
  previous after-RANKCTL failure to
  `clrsetbits_le32(&mctl_ctl->rankctl, 0xff0, 0x660)`.
- Running the skip-RANKCTL after-DFITMG checkpoint immediately afterward
  failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-after-timing-dfitmg-eret.0qfnTz/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. With `rankctl` skipped, this narrows the
  next failure to one of the DFI timing writes:
  `mctl_ctl->dfitmg0 = t_wr_lat | 0x2000000 | (t_rdata_en << 16) | 0x808000`
  or `mctl_ctl->dfitmg1 = 0x100202`.
- Temporary H713-only hooks were added to split the DFI timing writes. Three
  queued SPL checkpoints are built with the known-bad `OHMS240`, scheduler,
  second `unk_0x008`, ODTMAP, CR, timing `init[1]`, timing `init[3]`, and
  `rankctl` writes skipped: after-DFITMG0 at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-after-timing-dfitmg0-eret.GWuWVg/spl/sunxi-spl.bin`,
  skip-DFITMG1 after-RFSHTMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-after-timing-rfshtmg-eret.O7g7dz/spl/sunxi-spl.bin`,
  and skip-DFITMG0 after-DFITMG at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg0-after-timing-dfitmg-eret.CL6Sr4/spl/sunxi-spl.bin`.
  Disassembly confirms return calls/branch at `0x106a6c`, `0x106a70`, and
  `0x106a60`, respectively. Run the after-DFITMG0 image first after the next
  reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the after-DFITMG0 checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-after-timing-dfitmg0-eret.GWuWVg/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears
  `mctl_ctl->dfitmg0 = t_wr_lat | 0x2000000 | (t_rdata_en << 16) | 0x808000`
  and pins the previous after-DFITMG failure to `mctl_ctl->dfitmg1 = 0x100202`.
- Running the skip-DFITMG1 after-RFSHTMG checkpoint immediately afterward
  failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-after-timing-rfshtmg-eret.O7g7dz/spl/sunxi-spl.bin`
  timed out during the post-execute USB status phase, and a follow-up
  `./sunxi-fel -v ver` also timed out. With `dfitmg1` skipped, this pins the
  next failure to `mctl_ctl->rfshtmg = (trefi << 16) | trfc`.
- A temporary H713-only skip hook for the `rfshtmg` write was added. One
  queued SPL checkpoint is built with the known-bad `OHMS240`, scheduler,
  second `unk_0x008`, ODTMAP, CR, timing `init[1]`, timing `init[3]`,
  `rankctl`, timing `dfitmg1`, and timing `rfshtmg` writes skipped: after
  the controller timing call at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-after-mctl-ctrl-timing-eret.jUif7X/spl/sunxi-spl.bin`.
  Disassembly confirms the return call at `0x104da4`, immediately after the
  `mctl_set_timing_params()` call. Run this image first after the next
  reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the after-controller-timing checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-after-mctl-ctrl-timing-eret.jUif7X/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves `mctl_set_timing_params()` itself can
  return to `mctl_ctrl_init()` when the known-bad timing writes are skipped.
- A temporary H713-only return hook after the first post-timing `pwrctl` write
  was added. The queued SPL checkpoint is built with the same known-bad writes
  skipped, plus `CONFIG_H713_FEL_DIAG_RETURN_AFTER_MCTL_CTRL_PWRCTL0`, at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-after-mctl-ctrl-pwrctl0-eret.rPWLRG/spl/sunxi-spl.bin`.
  Disassembly confirms the return call at `0x104dac`, immediately after
  storing zero to `mctl_ctl->pwrctl`.
- Running the after-`pwrctl = 0` checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-after-mctl-ctrl-pwrctl0-eret.rPWLRG/spl/sunxi-spl.bin`
  timed out during USB communication, and a follow-up `./sunxi-fel -v ver`
  also timed out. With the after-controller-timing checkpoint proven good, this
  pins the next failure to `writel(0, &mctl_ctl->pwrctl)` in
  `mctl_ctrl_init()`.
- A temporary H713-only skip hook for the post-timing `pwrctl = 0` write and a
  return hook after the following `dfiupd[0]` update were added. The queued SPL
  checkpoint is built with known-bad `OHMS240`, scheduler, second `unk_0x008`,
  ODTMAP, CR, timing `init[1]`, timing `init[3]`, `rankctl`, timing
  `dfitmg1`, timing `rfshtmg`, and post-timing `pwrctl = 0` writes skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-after-mctl-ctrl-dfiupd-eret.tStn75/spl/sunxi-spl.bin`.
  Disassembly confirms `dfiupd[0]` is updated at `0x104dac` and the return call
  follows at `0x104db0`. Run this image first after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-`pwrctl = 0` after-DFIUPD checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-after-mctl-ctrl-dfiupd-eret.tStn75/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears
  `setbits_le32(&mctl_ctl->dfiupd[0], BIT(31) | BIT(30))` when the bad
  post-timing `pwrctl = 0` write is skipped.
- A temporary H713-only return hook after the following `zqctl[0]` update was
  added. The queued SPL checkpoint was built with the same known-bad writes
  skipped at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-after-mctl-ctrl-zqctl-eret.4Wo11C/spl/sunxi-spl.bin`.
  Disassembly confirms `zqctl[0]` is updated at `0x104db8` and the return call
  follows at `0x104dbc`.
- Running the after-ZQCTL checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-after-mctl-ctrl-zqctl-eret.4Wo11C/spl/sunxi-spl.bin`
  timed out during USB communication, and a follow-up `./sunxi-fel -v ver`
  also timed out. With after-DFIUPD proven good, this pins the next failure to
  `setbits_le32(&mctl_ctl->zqctl[0], BIT(31) | BIT(30))`.
- A temporary H713-only skip hook for the `zqctl[0]` update and a return hook
  after the following `unk_0x2180` update were added. The queued SPL checkpoint
  is built with known-bad `OHMS240`, scheduler, second `unk_0x008`, ODTMAP, CR,
  timing `init[1]`, timing `init[3]`, `rankctl`, timing `dfitmg1`, timing
  `rfshtmg`, post-timing `pwrctl = 0`, and `zqctl[0]` writes skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-after-mctl-ctrl-unk2180-eret.crWOmA/spl/sunxi-spl.bin`.
  Disassembly confirms `unk_0x2180` is updated at `0x104db8` and the return
  call follows at `0x104dbc`. Run this image first after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-ZQCTL after-UNK2180 checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-after-mctl-ctrl-unk2180-eret.crWOmA/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears
  `setbits_le32(&mctl_ctl->unk_0x2180, BIT(31) | BIT(30))` when the bad
  post-timing `pwrctl = 0` and `zqctl[0]` writes are skipped.
- A temporary H713-only return hook after the following `unk_0x3180` update was
  added. The queued SPL checkpoint was built with the same known-bad writes
  skipped at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-after-mctl-ctrl-unk3180-eret.0MubVs/spl/sunxi-spl.bin`.
  Disassembly confirms `unk_0x3180` is updated at `0x104dc4` and the return
  call follows at `0x104dc8`.
- Running the after-UNK3180 checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-after-mctl-ctrl-unk3180-eret.0MubVs/spl/sunxi-spl.bin`
  timed out during USB communication, and a follow-up `./sunxi-fel -v ver`
  also timed out. With after-UNK2180 proven good, this pins the next failure to
  `setbits_le32(&mctl_ctl->unk_0x3180, BIT(31) | BIT(30))`.
- A temporary H713-only skip hook for the `unk_0x3180` update and a return hook
  after the following `unk_0x4180` update were added. The queued SPL checkpoint
  is built with known-bad `OHMS240`, scheduler, second `unk_0x008`, ODTMAP, CR,
  timing `init[1]`, timing `init[3]`, `rankctl`, timing `dfitmg1`, timing
  `rfshtmg`, post-timing `pwrctl = 0`, `zqctl[0]`, and `unk_0x3180` writes
  skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-after-mctl-ctrl-unk4180-eret.493RWt/spl/sunxi-spl.bin`.
  Disassembly confirms `unk_0x4180` is updated at `0x104dc4` and the return
  call follows at `0x104dc8`. Run this image first after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-UNK3180 after-UNK4180 checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-after-mctl-ctrl-unk4180-eret.493RWt/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears
  `setbits_le32(&mctl_ctl->unk_0x4180, BIT(31) | BIT(30))` when the bad
  post-timing `pwrctl = 0`, `zqctl[0]`, and `unk_0x3180` writes are skipped.
- A temporary H713-only return hook after the following `rfshctl3` set was
  added. The queued SPL checkpoint was built with the same known-bad writes
  skipped at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-after-mctl-ctrl-rfshctl3-set-eret.G81ueO/spl/sunxi-spl.bin`.
  Disassembly confirms `rfshctl3` is updated at `0x104dd0` and the return call
  follows at `0x104dd4`.
- Running the after-RFSHCTL3-set checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-after-mctl-ctrl-rfshctl3-set-eret.G81ueO/spl/sunxi-spl.bin`
  timed out during USB communication, and a follow-up `./sunxi-fel -v ver`
  also timed out. With after-UNK4180 proven good, this pins the next failure to
  `setbits_le32(&mctl_ctl->rfshctl3, BIT(0))`.
- A temporary H713-only skip hook for the `rfshctl3` set and a return hook
  after the following `dfimisc` clear were added. The queued SPL checkpoint is
  built with known-bad `OHMS240`, scheduler, second `unk_0x008`, ODTMAP, CR,
  timing `init[1]`, timing `init[3]`, `rankctl`, timing `dfitmg1`, timing
  `rfshtmg`, post-timing `pwrctl = 0`, `zqctl[0]`, `unk_0x3180`, and
  `rfshctl3` set writes skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-after-mctl-ctrl-dfimisc-clear-eret.OxAY0X/spl/sunxi-spl.bin`.
  Disassembly confirms `dfimisc` is cleared at `0x104dd0` and the return call
  follows at `0x104dd4`. Run this image first after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-RFSHCTL3-set after-DFIMISC-clear checkpoint
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-after-mctl-ctrl-dfimisc-clear-eret.OxAY0X/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears
  `clrbits_le32(&mctl_ctl->dfimisc, BIT(0))` when the bad post-timing
  `pwrctl = 0`, `zqctl[0]`, `unk_0x3180`, and `rfshctl3` set writes are
  skipped.
- A temporary H713-only return hook after the following `maer0` clear was
  added. The queued SPL checkpoint was built with the same known-bad writes
  skipped at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-after-mctl-ctrl-maer0-clear-eret.TyIkbz/spl/sunxi-spl.bin`.
  Disassembly confirms the zero write to the `maer0` slot at `0x104dd8` and
  the return call follows at `0x104ddc`.
- Running the after-MAER0-clear checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-after-mctl-ctrl-maer0-clear-eret.TyIkbz/spl/sunxi-spl.bin`
  timed out during USB communication, and a follow-up `./sunxi-fel -v ver`
  also timed out. With after-DFIMISC-clear proven good, this pins the next
  failure to `writel(0, &mctl_com->maer0)`.
- A temporary H713-only skip hook for the `maer0` clear and a return hook after
  the following `maer1` clear were added. The queued SPL checkpoint is built
  with known-bad `OHMS240`, scheduler, second `unk_0x008`, ODTMAP, CR, timing
  `init[1]`, timing `init[3]`, `rankctl`, timing `dfitmg1`, timing `rfshtmg`,
  post-timing `pwrctl = 0`, `zqctl[0]`, `unk_0x3180`, `rfshctl3` set, and
  `maer0` clear writes skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-after-mctl-ctrl-maer1-clear-eret.ohs4r4/spl/sunxi-spl.bin`.
  Disassembly confirms `maer1` is cleared at `0x104ddc` and the return call
  follows at `0x104de0`. Run this image first after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-MAER0 after-MAER1-clear checkpoint succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-after-mctl-ctrl-maer1-clear-eret.ohs4r4/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `writel(0, &mctl_com->maer1)` when the
  bad post-timing `pwrctl = 0`, `zqctl[0]`, `unk_0x3180`, `rfshctl3` set, and
  `maer0` clear writes are skipped.
- A temporary H713-only return hook after the following `maer2` clear was
  added. The queued SPL checkpoint was built with the same known-bad writes
  skipped at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-after-mctl-ctrl-maer2-clear-eret.z4pYbb/spl/sunxi-spl.bin`.
  Disassembly confirms `maer2` is cleared at `0x104de8` and the return call
  follows at `0x104dec`.
- Running the after-MAER2-clear checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-after-mctl-ctrl-maer2-clear-eret.z4pYbb/spl/sunxi-spl.bin`
  timed out during USB communication, and a follow-up `./sunxi-fel -v ver`
  also timed out. With after-MAER1-clear proven good, this pins the next
  failure to `writel(0, &mctl_com->maer2)`.
- A temporary H713-only skip hook for the `maer2` clear and a return hook after
  the following `pwrctl = 0x20` write were added. The queued SPL checkpoint is
  built with known-bad `OHMS240`, scheduler, second `unk_0x008`, ODTMAP, CR,
  timing `init[1]`, timing `init[3]`, `rankctl`, timing `dfitmg1`, timing
  `rfshtmg`, post-timing `pwrctl = 0`, `zqctl[0]`, `unk_0x3180`, `rfshctl3`
  set, `maer0` clear, and `maer2` clear writes skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-after-mctl-ctrl-pwrctl20-eret.9GUnuA/spl/sunxi-spl.bin`.
  Disassembly confirms `pwrctl = 0x20` is written at `0x104e10` and the return
  call follows at `0x104e14`. Run this image first after the next reconnect.
- After a fresh reconnect, `./sunxi-fel -v ver` returned the normal H713 ROM
  report again. Running the skip-MAER2 after-`pwrctl = 0x20` checkpoint
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-after-mctl-ctrl-pwrctl20-eret.9GUnuA/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears `writel(0x20, &mctl_ctl->pwrctl)` when
  the bad post-timing `pwrctl = 0`, `zqctl[0]`, `unk_0x3180`, `rfshctl3` set,
  `maer0` clear, and `maer2` clear writes are skipped.
- A temporary H713-only return hook after the post-timing
  `setbits_le32(&mctl_ctl->clken, BIT(8))` was added. The checkpoint was built
  with the same known-bad writes skipped:
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-after-mctl-ctrl-clken-post-timing-eret.I4ofZg/spl/sunxi-spl.bin`.
  Disassembly confirmed `pwrctl = 0x20` is written at `0x104e10`,
  `clken |= BIT(8)` runs at `0x104e14..0x104e1c`, and the return call is at
  `0x104e20`.
- Running that post-timing `clken` checkpoint succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-after-mctl-ctrl-clken-post-timing-eret.I4ofZg/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the post-timing
  `setbits_le32(&mctl_ctl->clken, BIT(8))` write when all previously bad
  writes are skipped.
- A return hook after the following
  `clrsetbits_le32(&mctl_com->unk_0x500, BIT(24), 0x300)` was then added. The
  checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-after-mctl-ctrl-unk500-clrset-eret.KyClpc/spl/sunxi-spl.bin`.
  Disassembly confirmed the `unk_0x500` write at `0x104e20..0x104e2c` and the
  return call at `0x104e30`.
- Running that after-`unk_0x500`-clrset checkpoint failed:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-after-mctl-ctrl-unk500-clrset-eret.KyClpc/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. This pins the next
  failure to `clrsetbits_le32(&mctl_com->unk_0x500, BIT(24), 0x300)` after the
  post-timing `clken` write. The board needs another physical reconnect before
  live testing continues.
- A skip hook for that first `unk_0x500` clrset write and a return hook after
  the following `setbits_le32(&mctl_com->unk_0x500, BIT(24))` were added. The
  next checkpoint is queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-after-mctl-ctrl-unk500-set-eret.f2Crcy/spl/sunxi-spl.bin`.
  Disassembly confirms the known-bad clrset path is omitted, the
  `unk_0x500 |= BIT(24)` store is at `0x104e24`, and the return call is at
  `0x104e28`. Run this after the next reconnect to test whether the second
  `unk_0x500` write is independently unsafe.
- Running that skip-`unk_0x500`-clrset after-`unk_0x500`-set checkpoint in a
  fresh FEL session succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-after-mctl-ctrl-unk500-set-eret.f2Crcy/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the later
  `setbits_le32(&mctl_com->unk_0x500, BIT(24))` when the failed
  `clrsetbits_le32(&mctl_com->unk_0x500, BIT(24), 0x300)` is skipped.
- A return hook at `mctl_phy_init()` entry was added. With clang this inlined
  into `mctl_core_init()` as a return after the second post-`unk_0x500`
  `udelay(1)` and before the first PHY register access. The checkpoint was
  built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-phy-init-entry-eret.7AmySv/spl/sunxi-spl.bin`.
  Disassembly confirmed `unk_0x500 |= BIT(24)` stores at `0x104e28`, the
  following `udelay(1)` call runs at `0x104e2c`, and the return call is at
  `0x104e30`, before the first PHY write.
- Running that pre-PHY checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-phy-init-entry-eret.7AmySv/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. Since the immediate
  return after `unk_0x500 |= BIT(24)` passed, this narrows the next failure to
  the post-set delay/state before the first PHY register access. The board
  needs another physical reconnect before live testing continues.
- A skip hook for the later `unk_0x500 |= BIT(24)` write was added. The next
  checkpoint is queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-init-entry-eret.F7HPz9/spl/sunxi-spl.bin`.
  Disassembly confirms both `unk_0x500` writes are omitted, the two
  surrounding `udelay(1)` calls remain at `0x104e18` and `0x104e20`, and the
  return call is at `0x104e24` before the first PHY register access. Run this
  after the next reconnect to prove whether the post-set delay/state depends
  on the later `unk_0x500` set.
- Running that skip-both-`unk_0x500` pre-PHY checkpoint in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-init-entry-eret.F7HPz9/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves the two `udelay(1)` calls are harmless
  when both `unk_0x500` writes are skipped, and pins the previous pre-PHY
  failure to the state created by the later `unk_0x500 |= BIT(24)` write.
- A return hook after the first PHY register access,
  `clrsetbits_le32(SUNXI_DRAM_PHY0_BASE + 0x3c, 0xf, val)`, was added. The
  checkpoint was built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-after-phy-width-eret.wBa1Fh/spl/sunxi-spl.bin`.
  Disassembly confirmed the `PHY0 + 0x3c` write at `0x104e5c` and the return
  call at `0x104e60`.
- Running that after-PHY-width checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-after-phy-width-eret.wBa1Fh/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. With both
  `unk_0x500` writes skipped and the pre-PHY checkpoint passing, this pins the
  next failure to the first PHY width/config write at `SUNXI_DRAM_PHY0_BASE +
  0x3c`. The board needs another physical reconnect before live testing
  continues.
- A skip hook for the first PHY width/config write was added, with a return
  hook after the following PHY timing writes. The next checkpoint is queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-after-phy-timing-writes-eret.l2OMZr/spl/sunxi-spl.bin`.
  Disassembly confirms `PHY0 + 0x3c` is omitted, the twelve PHY timing writes
  run through `0x104f00`, and the return call is at `0x104f04` before the
  `phy_init[]` table loop. Run this after the next reconnect to test whether
  those timing writes are safe when the first PHY width/config write is
  skipped.
- Running that skip-PHY-width after-PHY-timing-writes checkpoint in a fresh
  FEL session succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-after-phy-timing-writes-eret.l2OMZr/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This clears the twelve PHY timing writes when the
  first PHY width/config write is skipped.
- A return hook after the `phy_init[]` table loop was added. The checkpoint was
  built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-after-phy-init-table-eret.EjYN52/spl/sunxi-spl.bin`.
  Disassembly confirmed the `phy_init[]` loop completes at `0x104f24` and the
  return call is at `0x104f28`, before the optional CA bit-delay path.
- Running that after-`phy_init[]` checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-after-phy-init-table-eret.EjYN52/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. With the prior
  after-PHY-timing-writes checkpoint passing, this pins the next failure to the
  `phy_init[]` table loop. The board needs another physical reconnect before
  live testing continues.
- A skip hook for the `phy_init[]` table loop was added. The next checkpoint
  is queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-after-phy-init-table-eret.dgtrr8/spl/sunxi-spl.bin`.
  Disassembly confirms the table loop is omitted and the return call is at
  `0x104f04`, before the optional CA bit-delay branch. Run this after the next
  reconnect to prove the table loop is the trigger.
- Running that skip-`phy_init[]` after-table checkpoint in a fresh FEL session
  succeeded: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-after-phy-init-table-eret.dgtrr8/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves the `phy_init[]` table loop is the
  trigger when the first PHY width/config write is already skipped.
- A return hook after the two `tpr6` PHY writes was added. The checkpoint was
  built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-after-phy-tpr6-eret.q8eOWC/spl/sunxi-spl.bin`.
  Disassembly confirmed the source writes to `PHY0 + 0x3dc` and
  `PHY0 + 0x45c` are immediately followed by the FEL return call. In the
  current DDR3 seed this uses `tpr6 & 0xff`, so the written value is `0x48`.
- Running that after-`tpr6` checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-after-phy-tpr6-eret.q8eOWC/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. With the prior
  skip-`phy_init[]` after-table checkpoint passing, this pins the next failure
  to the `tpr6` PHY writes at `PHY0 + 0x3dc` / `PHY0 + 0x45c`.
- A skip hook for the `tpr6` PHY writes was added. The next checkpoint is
  queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-after-phy-tpr6-eret.gsl0if/spl/sunxi-spl.bin`.
  Disassembly confirms the two `tpr6` stores are omitted and the return call is
  at `0x104f24`, before `mctl_phy_configure_odt()`. Run this after the next
  reconnect to prove the `tpr6` writes were the trigger.
- Running that skip-`tpr6` checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-after-phy-tpr6-eret.gsl0if/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves the `tpr6` writes at `PHY0 + 0x3dc` /
  `PHY0 + 0x45c` are the trigger when the first PHY width/config write and
  `phy_init[]` table are already skipped.
- A return hook after `mctl_phy_configure_odt()` was added. The checkpoint was
  built at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-after-phy-odt-eret.7Tmrpz/spl/sunxi-spl.bin`.
  Disassembly confirmed the return call is at `0x105134`, after the ODT helper
  writes and before the next PHY mode write.
- Running that after-ODT checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-after-phy-odt-eret.7Tmrpz/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. With the prior
  skip-`tpr6` checkpoint passing, this moves the next confirmed failure into
  `mctl_phy_configure_odt()`. A skip-ODT control is needed before splitting the
  helper into individual register writes.
- A skip hook for `mctl_phy_configure_odt()` was added. The next checkpoint is
  queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-phy-odt-after-phy-odt-eret.spfjKS/spl/sunxi-spl.bin`.
  Disassembly confirms the ODT helper body is omitted for H713 and the return
  call is at `0x104f24`, before the next PHY mode write. Run this after the
  next reconnect to prove `mctl_phy_configure_odt()` is the trigger.
- Running that skip-ODT checkpoint in a fresh FEL session succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-phy-odt-after-phy-odt-eret.spfjKS/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. This proves `mctl_phy_configure_odt()` is the trigger
  when the first PHY width/config write, `phy_init[]` table, and `tpr6` PHY
  writes are already skipped.
- A return hook after the PHY mode write was added. The checkpoint was built
  at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-phy-odt-after-phy-mode-eret.PAMl7l/spl/sunxi-spl.bin`.
  Disassembly confirmed the `clrsetbits_le32(PHY0 + 4, 0x7, 0x0a)` mode
  update is immediately followed by the FEL return call at `0x10502c`.
- Running that after-mode checkpoint failed: `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-phy-odt-after-phy-mode-eret.PAMl7l/spl/sunxi-spl.bin`
  timed out with `usb_bulk_send() ERROR -7`; `lsusb` still showed
  `1f3a:efe8`, but `./sunxi-fel -v ver` also timed out. With the prior
  skip-ODT checkpoint passing, this pins the next failure to the PHY mode write
  at `PHY0 + 4`.
- A skip hook for the `PHY0 + 4` mode write was added. The next checkpoint is
  queued at
  `/tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-phy-odt-phy-mode-after-phy-mode-eret.lDITfr/spl/sunxi-spl.bin`.
  Disassembly confirms the mode write is omitted for H713 and the return call
  is at `0x104f24`, before the clock-dependent PHY tweaks. Run this after the
  next reconnect to prove the `PHY0 + 4` mode write was the trigger.
- Running that skip-`PHY0 + 4` mode checkpoint in a fresh FEL session
  succeeded:
  `./sunxi-fel -v spl
  /tmp/u-boot-h713-diag-skip-ohms-sched-unk008-odtmap-cr-init1-init3-rankctl-dfitmg1-rfshtmg-pwrctl0-zqctl-unk3180-rfshctl3-set-maer0-maer2-unk500-clrset-unk500-set-phy-width-phy-init-table-phy-tpr6-phy-odt-phy-mode-after-phy-mode-eret.lDITfr/spl/sunxi-spl.bin`
  returned without timeout, and a follow-up `./sunxi-fel -v ver` returned the
  normal H713 ROM report. With the after-mode checkpoint failing and this
  skip-mode control passing, the `PHY0 + 4` mode write is a confirmed trigger
  in the current DDR3-seeded path.
- The PRCM failure also exposed an H713/H616 register-map mismatch risk.
  U-Boot's inherited `prcm_sun50i.h` defines `CCU_PRCM_RES_CAL_CTRL = 0x310`
  and `CCU_PRCM_OHMS240 = 0x318`. The stock HY310 DTS and the H713 Linux port
  both describe H713 `r_ccu` at `0x07010000` with size `0x240`, and the H713
  PPU analysis only accounts for R_CCU-embedded registers up through the
  documented power-domain window below that size. Therefore the current PRCM
  writes target `0x07010310` and `0x07010318`, outside the currently documented
  H713 R_CCU range. This does not prove those registers are absent, but it
  strongly argues against proceeding with inherited H616 PRCM calibration
  writes until the H713 vendor boot0 path or register map proves them.

## H713 raw capture and stock boot-chain evidence refresh

- Deep scan source: `<local>/h713-lab/`. The existing raw capture
  has already been reconstructed into full eMMC images, so no duplicate 7.3 GiB
  rebuild is needed for this pass. The primary image is
  `captures/board-a/board-a-mmcblk0-20260622T044744Z.img`; the verification
  image is `captures/board-a/board-a-mmcblk0-20260622T050413Z.img`, size
  `7818182656` bytes / `0x1d2000000`.
- The chunk manifests report 30 chunks, with 29 full 256 MiB chunks plus a
  final 32 MiB chunk. The two full-image hashes differ because live Android
  data changed, but the lab's partition hash comparison showed all non-UDISK
  boot-chain partitions matching.
- GPT confirms the boot-chain offsets used by the extracted lab artifacts:
  `bootloader_a` at `0x02400000`, `bootloader_b` at `0x04400000`,
  `env_a` at `0x06400000`, `boot_a` at `0x06480000`,
  `vendor_boot_a` at `0x0e480000`, and `dtbo_a` at `0x96480000`.
- Stock BT0 is present at 8 KiB and 128 KiB. Both copies are byte-identical
  with SHA-256
  `f8ac16e44a83869c8fa7193531bc3a8b228235428a99ac426daa0902026c9f0f`.
  The header/load words at offsets `0x1c` and `0x20` are `0x00104000`,
  matching our current SPL load address choice.
- The older h713-lab SRAM notes were intentionally conservative and predate
  the current live scratch tests, but their exclusion map remains useful:
  BT0 clears/touches `0x0010b348..0x0010b944`, sets SP/top around
  `0x00124000`, and has an observed stack-frame range
  `0x00122fc0..0x00123fff`. Do not place a FEL helper/thunk in that upper
  stack range. The old offline-preferred scratch/swap study band was
  `0x00110000..0x0011e000`.
- The local `sunxi-bootinfo` parser recognizes the BT0 container
  (`eGON.BT0`, length `32768`, header size `48`) but reports `Unknown boot0
  header version`. Use the raw BT0 word map below rather than the older
  `bootinfo.c` private-header struct for H713 DRAM parameters.
- TOC1 copy 1 starts at absolute offset 12 MiB; copy 2 starts at 16 MiB plus
  16 KiB. Parsed item payloads match across copies. Items are `u-boot`
  offset `0x800` size `0x9c000`, `monitor` offset `0x9c800` size `0x1020c`,
  `scp` offset `0xacc00` size `0x2b004`, `optee` offset `0xd8000` size
  `0x43380`, and `dtb` offset `0x11b400` size `0x12000`.
- The useful BT0 DRAM parameter window starts one word after the leading zero
  at BT0 offset `0x30`. The raw words are:
  `0x00000008 0x000002d0 0x00000007 0x003f3ffb 0x00000031
  0x10f410f4 0x04000000 0x00000000 0x000000c3 0x0000000a
  0x00000002 0x0049225a 0x01b1b1d0 0x0004c02c 0xb4787896
  0x00000000 0x48484848 0x00000048 0x1621121e 0x00000000
  0x00000000 0x00007767 0x44650000 0x00005544 0xb4036223`.
- Best current field interpretation for the BT0 window:
  `unknown/header = 0x00000008`, `dram_clk = 0x000002d0` (720 MHz),
  `dram_type = 0x00000007`, `dram_zq = 0x003f3ffb`,
  `dram_odt_en_or_flags = 0x00000031`, `dram_para1 = 0x10f410f4`,
  `dram_para2 = 0x04000000`, `dram_mr0 = 0x00000000`,
  `dram_mr1 = 0x000000c3`, `dram_mr2 = 0x0000000a`,
  `dram_mr3 = 0x00000002`, `dram_tpr0 = 0x0049225a`,
  `dram_tpr1 = 0x01b1b1d0`, `dram_tpr2 = 0x0004c02c`,
  `dram_tpr3 = 0xb4787896`, `dram_tpr4 = 0x00000000`,
  `dram_tpr5 = 0x48484848`, `dram_tpr6 = 0x00000048`,
  `dram_tpr7 = 0x1621121e`, `dram_tpr8 = 0x00000000`,
  `dram_tpr9 = 0x00000000`, `dram_tpr10 = 0x00007767`,
  `dram_tpr11 = 0x44650000`, `dram_tpr12 = 0x00005544`,
  `dram_tpr13 = 0xb4036223`.
- U-Boot's current H616-family enum defines `SUNXI_DRAM_TYPE_LPDDR3 = 7` and
  `SUNXI_DRAM_TYPE_LPDDR4 = 8`. Therefore the stock BT0 window is strong
  evidence for a 720 MHz LPDDR3-style path, not the current local
  `hy310_h713_defconfig` DDR3 seed (`CONFIG_DRAM_CLK=792` and
  `CONFIG_SUNXI_DRAM_H616_DDR3_1333=y`).
- This reframes the live checkpoint failures: many confirmed bad writes were
  generated by the DDR3-seeded path. The next useful U-Boot experiment should
  be an explicit LPDDR3 candidate using the stock BT0-derived values where
  current U-Boot has fields for them, plus the existing H713 PRCM safeguards.
- Stock BT0 strings include `DRAM CLK = %d MHz`, `DRAM Type = %d`,
  `DRAMC ZQ value: 0x%x`, `DRAM ODT value: 0x%x`,
  `DRAM SIZE = %d M`, and failure paths for rank/width and size auto-scan.
  This confirms BT0 is the right artifact to mine for initial DRAM setup even
  though its debug string only names older DDR2/DDR3 type labels.
- Stock U-Boot strings show it knows how to inspect/copy/update boot0 DRAM
  parameters (`update_fdt_dram_para`, `soc/dram_para`,
  `dram para[%d] = %x`, `androidboot.dramfreq=%d`,
  `androidboot.dramsize=%d`,
  `sunxi_flash boot0 force_dram_update_flag <new_val>`). Treat BT0 as the
  authoritative local DRAM source unless UART output from stock boot proves a
  later override.
- Stock environment confirms the console/load-address facts useful for later
  firmware work: `console=ttyS0,115200`, `earlyprintk=sunxi-uart,0x02500000`,
  `boot_normal=sunxi_flash read 45000000 boot;bootm 45000000`, and active
  `slot_suffix=_a`.
- Android boot/vendor-boot headers place normal kernel/vendor ramdisk/DTB work
  in DRAM around `0x40008000`, `0x43200000`, and `0x43300000`. This is useful
  for eventual handoff validation after SPL DRAM is working, but it does not
  prove FEL scratch/thunk SRAM.

## H713 stock DTB/DTS capture scan

- The useful decompiled DT sources in `<local>/h713-lab/` are
  `analysis/board-a-stock-20260622/vendor_boot_a-unpack/dtb.dts`,
  `analysis/board-a-stock-20260622/boot-map/toc1-12MiB-items/toc1-dtb.dts`,
  `reports/h713-dtb-ir-powerkey-decompile-20260627T074324Z/vendor_boot.dts`,
  and `reports/h713-dtb-ir-powerkey-decompile-20260627T074324Z/toc1.dts`.
  All four decompiled sources have SHA256
  `ff2e8a88c7e0d839109cf2eee4777960eb5a7d46c442314857b2f56e898e2706`.
- The binary vendor-boot DTB and TOC1 DTB are not byte-identical, but the two
  TOC1 copies match each other. The readable DTS content converges, so use the
  decompiled tree as one stock board-description source.
- The stock tree names the board/SOC family as `model = "sun50iw12"` with
  `compatible = "allwinner,tv303", "arm,sun50iw12p1"`. It does not use an
  `h713` compatible string.
- DT confirms several live values already used by FEL/U-Boot work:
  main PIO `0x02000000` size `0x400`, main CCU `0x02001000` size `0x1000`,
  watchdog0 `0x02051000`, UART0 `0x02500000` size `0x400` on `PH0/PH1`,
  SID `0x03006000` size `0x1000`, RTC/RTC-CCU `0x07090000`, R_CCU
  `0x07010000` size `0x240`, and R_PIO `0x07022000` size `0x800`.
- The SID child fields match the local sunxi-tools support choice:
  secure-status offset `0x0a0`, chipid offset `0x200` size `0x10`, FT zone
  offset `0x22c` size `0x10`, and ROTPK offset `0x270` size `0x20`.
- The DT reinforces the PRCM warning: H616-style `CCU_PRCM_RES_CAL_CTRL` and
  `CCU_PRCM_OHMS240` offsets `0x310`/`0x318` are beyond the stock H713 R_CCU
  aperture described by DT (`0x07010000..0x0701023f`).
- Storage/boot-relevant nodes: aliases point `mmc0` to `sdmmc@4020000` and
  `mmc2` to `sdmmc@4022000`. `sdmmc@4022000` is an 8-bit non-removable
  MMC/eMMC-style controller at `0x04022000`, with HS200/HS400 properties,
  while `sdmmc@4020000` is the 4-bit card controller at `0x04020000`.
- Power/standby detail: the stock DT `standby_param` maps `vdd-cpu`,
  `vdd-sys`, `vcc-pll`, and `vcc-dram` to `PL6`; the R_PIO pinctrl also has
  `PL6` groups for `s_pwm0` and `gpio_in`. This is not a DRAM timing source,
  but it is a board-specific rail/control hint to keep in view for SPL power
  sequencing.
- USB nodes describe OTG/UDC at `0x04100000`, EHCI/OHCI0 at
  `0x04101000`/`0x04101400`, EHCI/OHCI1 at `0x04200000`/`0x04200400`, and
  EHCI/OHCI2 at `0x04300000`/`0x04300400`.
- DRAM timing is not described in the stock DTB. Searches found no
  `memory@...`, `device_type = "memory"`, `dram_para`, `dram_tpr*`, MCTL, DDR,
  or LPDDR timing node useful for SPL DRAM init. Continue treating BT0/boot0
  extraction and live FEL SPL checkpoints as the sources of DRAM truth.
- Reserved-memory only describes the post-DRAM firmware layout: BL31
  `0x48000000` size `0x180000`, OP-TEE `0x48600000` size `0x100000`, display
  MIPS loader `0x4b100000` size `0x2841000`, decode buffer `0x4d941000` size
  `0x20000`, CPU communication buffer `0x4e300000` size `0x500000`, and
  frame buffer `0x4bf41000` size `0x1a00000`.

## H713 capture-derived U-Boot profile

- Updated the local U-Boot H713 path to stop selecting `DRAM_SUN50I_H616`.
  `MACH_SUN50I_H713` now selects a separate `DRAM_SUN50I_H713` profile, and
  `hy310_h713_defconfig` selects `SUNXI_DRAM_H713_LPDDR3_STOCK`.
- The HY310 defconfig now uses the stock BT0-derived values that the current
  U-Boot scaffold can consume: `CONFIG_DRAM_CLK=720`,
  `CONFIG_DRAM_SUNXI_ODT_EN=0x31`, `CONFIG_DRAM_SUNXI_TPR0=0x0049225a`,
  `CONFIG_DRAM_SUNXI_TPR2=0x0004c02c`,
  `CONFIG_DRAM_SUNXI_TPR6=0x00000048`,
  `CONFIG_DRAM_SUNXI_TPR10=0x00007767`,
  `CONFIG_DRAM_SUNXI_TPR11=0x44650000`, and
  `CONFIG_DRAM_SUNXI_TPR12=0x00005544`.
- Added `arch/arm/mach-sunxi/dram_timings/h713_lpddr3_stock.c` as an explicit
  H713 timing scaffold. It records the wider BT0 parameter window in comments
  because the current `struct dram_para` does not model all captured fields
  yet (`tpr1`, `tpr3`, `tpr5`, `tpr7`, `tpr13`, `dram_zq`, `dram_para1`,
  `dram_para2`, and MR values).
- The controller scaffold still reuses `dram_sun50i_h616.c`, but the H713
  profile name is now visible in the selection points. The H713 stock profile
  treats `tpr6=0x00000048` as the raw captured low byte instead of applying
  the H616 LPDDR3 high-halfword convention.
- Plain build check passed:
  `make O=/tmp/u-boot-h713-capture-profile ARCH=arm NO_PYTHON=1 HOSTCC=clang CC='clang -target aarch64-linux-gnu' LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump READELF=llvm-readelf STRIP=llvm-strip KCFLAGS=-fintegrated-as KAFLAGS=-fintegrated-as -j8 spl/sunxi-spl.bin`.
  The build compiled `spl/arch/arm/mach-sunxi/dram_timings/h713_lpddr3_stock.o`
  and produced `/tmp/u-boot-h713-capture-profile/spl/sunxi-spl.bin`.
- Guarded live FEL check passed after reconnect:
  `/tmp/u-boot-h713-capture-skip-mode-eret/spl/sunxi-spl.bin` was built with
  the same known-trigger skip set as the last passing mode-write control plus
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_MODE`. Disassembly showed the return
  call at `0x104f24` with the `PHY0 + 4` mode write omitted.
- Running `./sunxi-fel -v spl
  /tmp/u-boot-h713-capture-skip-mode-eret/spl/sunxi-spl.bin` returned
  `=> Executing the SPL... done.`, and a follow-up `./sunxi-fel -v ver`
  returned the normal ROM report:
  `AWUSBFEX soc=00001860(H713) 00000001 ver=0001 44 08 scratchpad=00121500
  00000000 00000000`.
- This proves the new capture-derived H713 selection/profile builds and can
  traverse the last known-safe guarded path without wedging FEL. It does not
  prove DRAM init yet; the next work should continue replacing or splitting
  the confirmed bad PRCM/PHY writes with H713-specific behavior instead of
  re-enabling inherited H616 writes wholesale.

## H713-specific DRAM parameter ABI

- Split H713 another step away from H616: `MACH_SUN50I_H713` now includes an
  H713 DRAM header and builds `dram_sun50i_h713.o` instead of compiling
  `dram_sun50i_h616.o` for H713.
- Added `arch/arm/include/asm/arch-sunxi/dram_sun50i_h713.h` with an
  H713/vendor-shaped `struct dram_para`. The struct preserves raw captured
  fields: `zq`, `odt_en`, `para1`, `para2`, `mr0..3`, and `tpr0..13`.
  The provisional scaffold fields `dx_odt`, `dx_dri`, and `ca_dri` remain
  separate because they are still inherited register-write inputs, not proven
  names from the H713 BT0 parameter window.
- Added H713-visible Kconfig fields for the raw BT0 block:
  `DRAM_SUNXI_ZQ`, `DRAM_SUNXI_PARA1`, `DRAM_SUNXI_PARA2`,
  `DRAM_SUNXI_MR0..3`, `DRAM_SUNXI_TPR4`, `DRAM_SUNXI_TPR5`,
  `DRAM_SUNXI_TPR7`, `DRAM_SUNXI_TPR8`, `DRAM_SUNXI_TPR9`, and H713 use of
  `DRAM_SUNXI_TPR13`.
- `hy310_h713_defconfig` now carries the complete captured BT0 parameter block
  that we have decoded so far, instead of carrying only the subset accepted by
  the H616-shaped struct.
- Plain build check passed:
  `/tmp/u-boot-h713-specific-dram-para/spl/sunxi-spl.bin` built with
  `spl/arch/arm/mach-sunxi/dram_sun50i_h713.o` and
  `spl/arch/arm/mach-sunxi/dram_timings/h713_lpddr3_stock.o`.
- Guarded live FEL check passed after reconnect:
  `/tmp/u-boot-h713-specific-skip-mode-eret/spl/sunxi-spl.bin` was built with
  the known-trigger skip set plus `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_MODE`.
  Disassembly showed the return call at `0x104f24` with the `PHY0 + 4` mode
  write omitted. Running `./sunxi-fel -v spl` returned
  `=> Executing the SPL... done.`, and the follow-up `./sunxi-fel -v ver`
  returned the normal H713 ROM report with scratchpad `00121500`.
- Next live checkpoint with the H713-specific driver allowed the LPDDR3
  `PHY0 + 4` mode write (`0x0b`) and returned immediately after it:
  `/tmp/u-boot-h713-specific-mode-write-eret/spl/sunxi-spl.bin`.
  Disassembly confirmed the `0x0b` write is followed by the FEL return call
  at `0x10502c`. Running it succeeded, and a follow-up
  `./sunxi-fel -v ver` returned the normal H713 ROM report. This means the
  earlier DDR3-seeded `PHY0 + 4` failure was caused by the wrong DRAM-type
  path/value (`0x0a`), not by any write to `PHY0 + 4` in general.
- The next checkpoint returned after the 720 MHz clock-dependent PHY tweaks:
  `/tmp/u-boot-h713-specific-after-phy-clock-tweaks-eret/spl/sunxi-spl.bin`.
  It kept the known-trigger skip set and allowed the now-proven LPDDR3 mode
  write. Disassembly placed the return after the `PHY0 + 0x144` clear, before
  the later `unk_0x500`/DFI sequence. Running it timed out with
  `usb_bulk_send() ERROR -7`; a follow-up `./sunxi-fel -v ver` also timed out,
  while `lsusb` still showed `1f3a:efe8`. This pins the next failure to the
  small clock-tweak block after the LPDDR3 mode write, before `unk_0x500`.
- Added finer diagnostic hooks for the 720 MHz clock-tweak block:
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_CLK_GT500_144`,
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_CLK_GT500_14C`,
  `CONFIG_H713_FEL_DIAG_SKIP_PHY_CLK_GT500_144`, and
  `CONFIG_H713_FEL_DIAG_SKIP_PHY_CLK_GT500_14C`.
- Queued next checkpoint:
  `/tmp/u-boot-h713-specific-after-phy-clk144-eret/spl/sunxi-spl.bin`.
  It uses the known-trigger skip set, allows the proven LPDDR3 mode write,
  executes only the first `clk > 500` PHY clock-tweak write, and returns before
  the second write. Disassembly confirms the return call at `0x10505c`, before
  the subsequent `PHY0 + 0x14c` clear. Run this after the next reconnect.
- Live result at 2026-07-02 15:52 PDT:
  `/tmp/u-boot-h713-specific-after-phy-clk144-eret/spl/sunxi-spl.bin` ran
  successfully. `./sunxi-fel -v spl` returned `=> Executing the SPL... done.`,
  and a follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report with
  scratchpad `00121500`. This proves the first 720 MHz clock-tweak write,
  clearing `BIT(7)` at `PHY0 + 0x144`, is safe by itself in the current guarded
  path.
- Built and ran the companion checkpoint:
  `/tmp/u-boot-h713-specific-after-phy-clk14c-eret/spl/sunxi-spl.bin`.
  It uses the same known-trigger skip set, allows the proven LPDDR3 mode write,
  executes the `PHY0 + 0x144` clear, then executes the second clock-tweak clear
  at `PHY0 + 0x14c` with mask `0xe0`, and returns immediately after.
  Disassembly confirmed the branch to `sunxi_return_to_fel` at `0x105068`
  directly after the `PHY0 + 0x14c` write.
- Live result: running the `0x14c` checkpoint reproduced the timeout:
  `usb_bulk_send() ERROR -7: Operation timed out`. A follow-up
  `./sunxi-fel -v ver` also timed out, while `lsusb` still showed the board as
  `1f3a:efe8`. This narrows the next failure to the second 720 MHz clock tweak,
  `clrbits_le32(PHY0 + 0x14c, 0xe0)`, or to the combination of that write after
  the now-proven `PHY0 + 0x144` clear.
- Next recommended live checkpoint after reconnect: run the second write alone
  by skipping `PHY0 + 0x144` and returning after `PHY0 + 0x14c`. If that passes,
  the bad behavior is the combination/order of the two writes; if it fails, the
  `PHY0 + 0x14c` clear itself is unsafe for H713 as currently modeled.
- Queued that second-write-alone checkpoint:
  `/tmp/u-boot-h713-specific-skip-clk144-after-clk14c-eret/spl/sunxi-spl.bin`.
  It was built with `CONFIG_H713_FEL_DIAG_SKIP_PHY_CLK_GT500_144` plus
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_CLK_GT500_14C`. Disassembly confirmed
  there is no `PHY0 + 0x144` clear on the `clk > 500` path and the return call
  follows the `PHY0 + 0x14c` clear directly. Run this after the next reconnect.
- Live result at 2026-07-02 15:57 PDT:
  `/tmp/u-boot-h713-specific-skip-clk144-after-clk14c-eret/spl/sunxi-spl.bin`
  ran successfully. `./sunxi-fel -v spl` returned `=> Executing the SPL...
  done.`, and a follow-up `./sunxi-fel -v ver` returned the normal H713 ROM
  report with scratchpad `00121500`.
- This proves the `PHY0 + 0x14c` clear is safe by itself in the current guarded
  path. Combined with the previous passing `PHY0 + 0x144`-alone test and the
  failing normal-order pair, the next suspect is the order/interaction of the
  two 720 MHz clock-tweak writes rather than either individual write.
- Next recommended checkpoint: reverse the two-write order for H713 only:
  clear `PHY0 + 0x14c` with mask `0xe0`, then clear `BIT(7)` at
  `PHY0 + 0x144`, then return to FEL. If this passes, keep the H713-specific
  ordering; if it fails, skip or replace the pair and continue from the next
  known-safe point.
- Added `CONFIG_H713_FEL_DIAG_PHY_CLK_GT500_REVERSE_ORDER` to the H713 DRAM
  driver and built:
  `/tmp/u-boot-h713-specific-reverse-clk14c-then-144-eret/spl/sunxi-spl.bin`.
  It uses the same known-trigger skip set, reverses the `clk > 500` PHY
  clock-tweak order for H713 only, and returns after the second reversed write.
  Disassembly showed the expected order: clear `PHY0 + 0x14c` with mask
  `0xe0`, clear `BIT(7)` at `PHY0 + 0x144`, then branch to
  `sunxi_return_to_fel`.
- Live result at 2026-07-02 16:00 PDT: the reversed-pair checkpoint timed out
  with `usb_bulk_send() ERROR -7: Operation timed out`. A follow-up
  `./sunxi-fel -v ver` also timed out, while `lsusb` still showed the board as
  `1f3a:efe8`.
- This proves the problem is not simply normal-order sequencing. Each write
  alone is safe, but any tested pair containing both 720 MHz clock-tweak writes
  wedges FEL transfers. Treat this inherited pair as unsafe for H713 until we
  find a captured/vendor equivalent. Next checkpoint should skip both writes
  and return after the clock-tweak block to prove we can continue past it.
- Queued the skip-both control checkpoint:
  `/tmp/u-boot-h713-specific-skip-both-clk-tweaks-eret/spl/sunxi-spl.bin`.
  It was built with the known-trigger skip set plus both
  `CONFIG_H713_FEL_DIAG_SKIP_PHY_CLK_GT500_144` and
  `CONFIG_H713_FEL_DIAG_SKIP_PHY_CLK_GT500_14C`, then
  `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_CLOCK_TWEAKS`. Disassembly confirmed
  that the 720 MHz `clk > 500` path branches directly to
  `sunxi_return_to_fel` after the clock-tweak block, with neither inherited
  PHY clock-tweak clear executed. Run this after the next reconnect.
- Live result at 2026-07-02 16:04 PDT:
  `/tmp/u-boot-h713-specific-skip-both-clk-tweaks-eret/spl/sunxi-spl.bin` ran
  successfully. `./sunxi-fel -v spl` returned `=> Executing the SPL... done.`,
  and a follow-up `./sunxi-fel -v ver` returned the normal H713 ROM report with
  scratchpad `00121500`.
- This confirms we can safely pass the 720 MHz clock-tweak block only if both
  inherited PHY clears are skipped. The next checkpoint moves one small step
  later: after skipping both clock-tweak writes, execute the `unk_0x500` clear,
  `udelay(1)`, and `clrbits(PHY0 + 0x14c, 8)`, then return before the first
  PHY await/completion poll.
- Added `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_UNK500_AND_14C8` and built:
  `/tmp/u-boot-h713-specific-after-unk500-14c8-eret/spl/sunxi-spl.bin`.
  It skips both unsafe 720 MHz PHY clock-tweak writes, executes
  `clrbits(&mctl_com->unk_0x500, 0x200)`, waits 1 us, clears bit 3 at
  `PHY0 + 0x14c`, and returns before the first PHY await.
- Live result at 2026-07-02 16:06 PDT: the checkpoint timed out with
  `usb_bulk_send() ERROR -7: Operation timed out`. A follow-up
  `./sunxi-fel -v ver` also timed out, while `lsusb` still showed the board as
  `1f3a:efe8`.
- Next checkpoint should split this again: skip both unsafe clock-tweak writes,
  execute only the `unk_0x500` clear plus `udelay(1)`, and return before the
  extra `PHY0 + 0x14c` bit-3 clear. If that passes, the next bad write is the
  second use of `PHY0 + 0x14c`; if it fails, the H713 sequence cannot use this
  inherited `unk_0x500` clear here.
- Added `CONFIG_H713_FEL_DIAG_RETURN_AFTER_PHY_UNK500_CLEAR` and queued:
  `/tmp/u-boot-h713-specific-after-unk500-only-eret/spl/sunxi-spl.bin`.
  It skips both unsafe 720 MHz PHY clock-tweak clears, executes only
  `clrbits(&mctl_com->unk_0x500, 0x200)` plus `udelay(1)`, and returns before
  the later `PHY0 + 0x14c` bit-3 clear. Disassembly confirms the 720 MHz path
  branches through the `unk_0x500` clear and returns at `0x105084`. Run this
  after the next reconnect.
