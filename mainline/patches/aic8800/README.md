# AIC8800 driver patches

The AIC8800 WiFi/BT driver is carried as a **patch series applied to a pinned
vendor tarball**, the same way the kernel is (see `../kernel/README.md`) rather
than as a fork. Filenames are prefixed `aic8800-` so a patch is identifiable on
sight even out of context — these are **not** kernel patches and are never
applied to the kernel tree.

## Base

| | |
|---|---|
| Upstream | `radxa-pkg/aic8800`, commit `df4c783b` |
| Vendor driver release | `2026_0123_5f7be68d` |
| Subtree used | `src/SDIO/driver_fw/driver/aic8800` |
| Applied first | the repo's own `debian/patches/series` |

**Order matters.** Radxa's `debian/patches` are applied to the *whole* repo
first (they patch `src/PCIE`, `src/SDIO` and `src/USB` together), and only then
is the SDIO subtree extracted and this series applied on top.

Two of Radxa's patches do not apply at this commit and that is expected:
`fix-usb-firmware-path` (USB only, zero SDIO hunks) and
`fix-Lower-the-debugging-log-level` (already merged upstream — `patch` reports
it as reversed/previously applied).

## The series

| # | What | Why |
|---|------|-----|
| 0001 | `CONFIG_PLATFORM_MAINLINE_SUNXI` build target | Vendor ships `CONFIG_PLATFORM_ALLWINNER`, but that targets their Android/longan BSP. Mainline sunxi is a new platform, added alongside the existing ones. |
| 0002 | H713 `wlan_regon` GPIO, power sequencing, SDIO rescan | The actual bring-up glue: PM1 (GPIO 385) power enable, `4021000.mmc` host lookup, `mmc_detect_change()` rescan, hostwake input, DDR50 disable. All inside `#ifdef CONFIG_PLATFORM_MAINLINE_SUNXI`. |
| 0003 | SDIO clock and chip-up timeout tuning | See below — the most consequential patch in the series. |
| 0004 | Guard the firmware-array include | Vendor `#include`s `aicwf_firmware_array.h` unconditionally even though its only caller is `#ifdef CONFIG_FIRMWARE_ARRAY`. `aicwf_firmware_array.c` is a **1.9 MB proprietary blob-as-C-array**; guarding the include is what lets the build exclude it. |

## Patch 0003 deserves attention

Two constants, both inherited from the well0nez tree and both **outside** the
`CONFIG_PLATFORM_MAINLINE_SUNXI` guards, so neither is obvious when reading the
diff:

- **`FEATURE_SDIO_CLOCK_V3`: 150 MHz → 25 MHz.** A 6× downclock, and
  `aic_bsp_driver.c` applies this value specifically to `PRODUCT_ID_AIC8800D80`
  — our exact chip. The original vendor lines are preserved commented-out
  directly above the override in the source we inherited, which is what marks it
  as deliberate rather than accidental.
- **chip-up semaphore: 2 s → 20 s.** A 10× increase on the wait for the chip to
  come up.

Provenance is not fully certain: pristine vendor `2024_0109` was not available
to diff against, so it cannot be proven these were well0nez's changes rather
than the 2024 vendor defaults. They are carried forward because dropping them
silently is the riskier direction — a longer timeout only costs time on a path
that has already failed, and the SDIO downclock is very likely a workaround for
the `FIFO_RUN_ERROR`/CMD53 underrun history (see `docs/roadmap.md`).

**The SDIO clock is a live experiment, not a settled value.** 25 MHz was chosen
before kernel patch 0006 added FIFO/DMA-reset recovery, and it is a plausible
suspect in "STA WiFi cannot carry a file". Raising it is worth trying — but only
against a captured baseline (`tools/wifi/wifi-baseline.sh`), one step at a time,
never blind.

## Deliberately *not* carried forward

- **Our kernel-compat changes.** Radxa's series already covers all of it and
  covers it better: the timer API rename (`from_timer`→`timer_container_of`,
  `del_timer*`→`timer_delete*`) in `fix-linux-6.15/6.16-build`, and
  `radio_idx`/`link_id` in `fix-linux-6.17-build`. Theirs are guarded with
  `#if LINUX_VERSION_CODE`; ours hardcoded the new signatures and so only built
  on new kernels.
- **`KDIR ?= /opt/captcha/kernel/linux-6.16.7`** and its `PWD`/`KVER` siblings —
  a hardcoded path from someone else's build machine. `build/build.sh` passes
  `KDIR` itself.
- **~1450 lines of vendor development** we were simply two years behind on
  (D80N/D80X2/DC chip support, refactoring, log-string fixes). Taking vendor's
  version is the point of the rebase.

## Two firmware consequences of this rebase (hardware-verified 2026-08-17)

Neither is a patch here, but both are required for the series to actually boot,
and both were found the hard way:

1. **The firmware path moved.** Radxa's `debian/patches/fix-sdio-firmware-path`
   sets `CONFIG_AIC_FW_PATH = /lib/firmware/aic8800_fw/SDIO/aic8800D80`, where
   the 2024 driver used `aic8800_sdio/aic8800`. `AIC8800_FW_DEST` in
   `config/versions.env` must match, or the driver enumerates the chip and then
   fails every firmware open.
2. **This board needs `_h_` firmware.** The chip reports `is_chip_id_h` from
   register `0x40500000` (`((memdata >> 16) & 0xC0) == 0xC0`). Both drivers
   compute it, but only the 2026 one has a D80 `_h_` firmware list, so it loads
   `fmacfw_8800d80_h_u02.bin`. The 2024 driver had no such list and silently
   used the non-`_h_` file.

The second point also **refutes an earlier assumption in this file's history**:
the identical `lmac_msg.h` ABI does *not* mean driver and firmware can be
swapped independently. The wire protocol is unchanged, but the firmware
*file-selection* logic is not, so the 2026 driver cannot run on the 2024
firmware set at all.

## Regenerating after an upstream bump

Apply with three-way merge so context drift is survivable:

```
git apply -3 patches/aic8800/<patch>     # falls back to patch -p1
```

Verified at generation time: all four apply cleanly to a fresh extract and
reproduce the intended tree byte-for-byte.
