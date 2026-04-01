# AIC8800D80 SDIO Driver Port Report
## V1.0 → Radxa V5.0 (radxa-pkg/aic8800) for Linux 6.16.7 ARM32 / Allwinner H713

**Date**: 2026-03-23  
**Upstream Commit**: `445a655fc5fb8deb3f0a558e39c8f9da295c0831` (radxa-pkg/aic8800 main)  
**Verification Scope**: Build-only (Port+Build, no runtime smoke/stress)  
**Build Host**: `lan` (192.168.8.218), `/opt/captcha/kernel/linux-6.16.7`, `arm-linux-gnueabi-gcc`  
**Build Command**: `make -C /opt/captcha/kernel/linux-6.16.7 M=<ported-tree> ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- CONFIG_PLATFORM_MAINLINE_SUNXI=y modules`

---

## Ported Changes (V5 → aic8800-v5-ported)

### aic8800_bsp

| File | Type | Notes |
|---|---|---|
| `aic8800d80n_compat.c/h` | Feature | New D80N chip variant compat tables and patch loader. Added `#include <linux/vmalloc.h>` for `vfree()` (Linux 6.16.7 fix). |
| `aic8800d80x2_compat.c/h` | Feature | New D80X2 chip variant compat tables. V5 upstream bug `sdiodev->fw_version_uint` not present in ported copy. |
| `Makefile` | API-Update | Added D80N/D80X2 to obj list. Added 7 new V5 config flags with safe defaults. Fixed `ARCH ?= arm` in MAINLINE_SUNXI block (was `x86_64`). Preserved `CONFIG_SDIO_PWRCTRL := y` and `CONFIG_AIC_FW_PATH ?= "/usr/lib/firmware/aic8800_sdio/aic8800"`. |
| `aicsdio.c` | **PRESERVED V1** | H713-specific GPIO/MMC control (`4021000.mmc`, PM1 `wlan_regon`, `mmc_detect_change`) kept intact. V5 SDIO deltas not imported to protect H713 platform glue. |

### aic8800_fdrv

| File | Type | Notes |
|---|---|---|
| `aic_priv_cmd.c/h` | Feature | New mandatory V5 file (unconditional in obj-m). Required `rwnx_main.h` include restructuring to avoid struct redefinition. |
| `aicwf_sdio.h` | API-Update | Extended `AICWF_IC` enum with D80N/D80WN/D80X2 variants. Added D40N/D40LN/D40WN device IDs. Added `func2` member to `aic_sdio_dev` struct. |
| `aicwf_sdio.c` | Feature | V5 SDIO data path. Fixed `from_timer` → `timer_container_of`, `del_timer_sync` → `timer_delete_sync`. |
| `rwnx_main.c` | Feature | V5 core driver. Fixed `from_timer` → `timer_container_of`, `del_timer_sync` → `timer_delete_sync`, `MODULE_IMPORT_NS` string syntax, `set_monitor_channel` 3-arg signature, `get_tx_power` 4-arg signature with `link_id`. |
| `rwnx_platform.c` | Feature | V5 platform layer. Fixed `MODULE_IMPORT_NS` string syntax. |
| `rwnx_rx.c` | Feature | V5 RX path. Fixed `from_timer` → `timer_container_of`, `del_timer_sync` → `timer_delete_sync`, `del_timer` → `timer_delete`. Added `#include <linux/timer.h>`. |
| `rwnx_msg_tx.c/h` | Feature | V5 TX message path with new API functions required by `aic_priv_cmd.c`. |
| `rwnx_mod_params.c/h` | API-Update | V5 module parameters. Added `get_fdrv_no_reg_sdio()` stub (V5 upstream bug: function referenced but never defined). |
| `rwnx_cmds.c/h` | Feature | V5 command processing. |
| `rwnx_tx.c/h`, `rwnx_txq.c/h` | Feature | V5 TX data path. |
| `rwnx_msg_rx.c` | Feature | V5 RX message handling. |
| `aicwf_txrxif.c/h` | Bugfix | V5 TX/RX interface reliability fixes. |
| `aicwf_compat_8800d80.c/h` | Feature | V5 D80 compat extension. |
| `aicwf_compat_8800dc.c` | Feature | V5 DC compat expansion. |
| `aic_vendor.c/h` | Feature | V5 vendor command extension. |
| `aicwf_tcp_ack.c/h` | Bugfix | V5 timer API fix (`timer_delete`), TCP ACK filtering safety. |
| `rwnx_defs.h`, `rwnx_platform.h`, `rwnx_rx.h`, `rwnx_tx.h`, `rwnx_txq.h`, `rwnx_radar.h`, `hal_desc.h`, `lmac_msg.h`, `rwnx_debugfs.h`, `rwnx_compat.h`, `aicwf_debug.h` | API-Update | V5 header updates for new API surface. |
| `regdb.c` | Feature | V5 regulatory database refresh. |
| `rwnx_main.h` | API-Update | Removed duplicate `android_wifi_priv_cmd` struct (moved to `aic_priv_cmd.h`). |
| `Makefile` | API-Update | Added `aic_priv_cmd.o` to obj list. Added 22 new V5 config flags. Accepted `CONFIG_FILTER_TCP_ACK=y`. Fixed `CONFIG_PLATFORM_UBUNTU ?= n`. Added MAINLINE_SUNXI block. |

### aic8800_btlpm

| File | Type | Notes |
|---|---|---|
| `aic8800_btlpm.c` | Bugfix | V5 timer API fix (`timer_delete`). |
| `aic_bluetooth_main.c` | Bugfix | V5 `platform_device_put` on error path. |
| `lpm.c` | Bugfix | V5 timer API fix (`del_timer` → `timer_delete`), DT GPIO flag handling. |
| `Makefile` | API-Update | `CONFIG_SUPPORT_LPM ?= n` (optional), Ubuntu guard removed from `lpm.o`. Added MAINLINE_SUNXI block. |

---

## Skipped V5 Changes (with rationale)

| File/Feature | Reason |
|---|---|
| `aic_btsdio.c/h`, `btsdio.c` | Guarded by `CONFIG_SDIO_BT=n`. Not needed for D80 SDIO WiFi target. |
| `aicwf_manager.c/h`, `aicwf_steering.c/h` | Guarded by `CONFIG_BAND_STEERING=n`. Not needed for current target profile. |
| `aic8800_bsp/aicsdio.c` V5 deltas | H713-specific GPIO/MMC control must be preserved. V5 `aicsdio.c` has no MAINLINE_SUNXI block. V1 version retained. |
| `aic8800_bsp/aic_bsp_driver.c` V5 deltas | V5 adds D80N/D80X2 routing but also Android-specific paths. Selective import deferred; D80N/D80X2 compat handled via new compat files. |
| `CONFIG_SDIO_PWRCTRL := n` (V5 default) | Rejected. V1 uses `y` for H713 SDIO power control. |
| `CONFIG_AIC_FW_PATH = "/vendor/etc/firmware"` (V5 default) | Rejected. V1 uses `/usr/lib/firmware/aic8800_sdio/aic8800`. |
| `MAKEFLAGS += -j$(shell nproc)` (V5 root) | Rejected. Parallel build can break BSP→fdrv dependency order. |
| D40N/D40LN/D40WN chip variants | Device IDs added to header for completeness, but no compat files ported. Not relevant for D80 target. |
| Debian packaging (`radxa-aic8800/Makefile`, `debian/`) | Out of scope. |

---

## Linux 6.16.7 API Audit Results

| API Change | Status | Files Affected |
|---|---|---|
| `from_timer()` → `timer_container_of()` | ✅ Fixed | `rwnx_rx.c`, `rwnx_main.c`, `aicwf_sdio.c` |
| `del_timer()` → `timer_delete()` | ✅ Fixed | `rwnx_rx.c`, `aicwf_sdio.c`, `lpm.c`, `aicwf_tcp_ack.c` (V5 already correct) |
| `del_timer_sync()` → `timer_delete_sync()` | ✅ Fixed | `rwnx_rx.c`, `rwnx_main.c`, `aicwf_sdio.c` |
| `MODULE_IMPORT_NS(ns)` → `MODULE_IMPORT_NS("ns")` | ✅ Fixed | `rwnx_main.c`, `rwnx_platform.c` |
| `set_monitor_channel(wiphy, chandef)` → `(wiphy, dev, chandef)` | ✅ Fixed | `rwnx_main.c` |
| `get_tx_power(wiphy, wdev, mbm)` → `(wiphy, wdev, link_id, mbm)` | ✅ Fixed | `rwnx_main.c` |
| `vfree()` requires `#include <linux/vmalloc.h>` | ✅ Fixed | `aic8800d80n_compat.c` |
| `class_create(owner, name)` → `class_create(name)` | ✅ Not present in ported files |
| `no_llseek` → `noop_llseek` | ✅ Not present in ported files |
| `#include <linux/tasklet.h>` → `<linux/interrupt.h>` | ✅ Not present in ported files |
| `dma_buf_vmap(dbuf)` → `dma_buf_vmap(dbuf, &map)` | ✅ Not present in ported files |
| `sched_setaffinity` | ✅ Dead code only (`#if 0` blocks), no fix needed |
| `sched_setscheduler` | ✅ Only in `#else` branch for kernel < 5.9, not reached on 6.16.7 |

---

## Build Log Summary

**Final Build**: 2026-03-23 on `lan` (192.168.8.218)  
**Exit Code**: 0  
**Errors**: 0  
**Warnings**: ~100 (inherited baseline: `-Wmissing-prototypes`, `-Wimplicit-fallthrough`, `-Wunused-variable`)

**Module Sizes**:
| Module | Size | Architecture |
|---|---|---|
| `aic8800_bsp.ko` | 122,980 bytes | ARM ELF |
| `aic8800_fdrv.ko` | 618,556 bytes | ARM ELF |
| `aic8800_btlpm.ko` | 7,972 bytes | ARM ELF |

**V5 Upstream Bugs Encountered and Fixed**:
1. `aic8800d80n_compat.c`: Missing `#include <linux/vmalloc.h>` for `vfree()` — added
2. `aic8800d80x2_compat.c`: References `sdiodev->fw_version_uint` which doesn't exist in struct — not present in ported copy (different V5 revision)
3. `rwnx_mod_params.c`: `get_fdrv_no_reg_sdio()` referenced as `extern` in `aicwf_sdio.c` but never defined anywhere in V5 — added stub implementation

---

## Known Remaining Issues

1. **`aicsdio.c` V5 deltas not imported**: The V5 BSP SDIO core (`aicsdio.c`) has 35 changed hunks including potential SDIO stability improvements. These were not imported to protect the H713-specific GPIO/MMC control path. If SDIO DMA issues persist after deploying this port, selective import of V5 `aicsdio.c` stability hunks should be evaluated.

2. **`aic_bsp_driver.c` V5 deltas not imported**: V5 adds D80N/D80X2 chip routing in `aic_bsp_driver.c` (24 hunks). The new compat files are present but the dispatch logic in `aic_bsp_driver.c` still uses V1 routing. This means D80N/D80X2 variants will not be initialized correctly at runtime (not relevant for D80 target).

3. **`func2` struct member added**: `struct aic_sdio_dev` now has a `func2` pointer for BT-over-SDIO. With `CONFIG_SDIO_BT=n`, this is never populated. No runtime impact expected.

4. **`get_fdrv_no_reg_sdio()` stub**: Returns `false` (CONFIG_FDRV_NO_REG_SDIO=n). This matches the V1 behavior and the Makefile default.

5. **Firmware path duality**: The BSP compile-time path is `/usr/lib/firmware/aic8800_sdio/aic8800`. The device runtime path is `/lib/firmware/aic8800D80/` (case-sensitive). These are deployment concerns, not build concerns. Ensure the deployment script creates the correct symlinks or copies.

6. **SDIO DMA at 50MHz**: The known issue with `cmd53 data error` at large transfers (>~500KB) at 50MHz SDIO clock is not addressed by this port. The DTS still requires `max-frequency = <25000000>` as a workaround. V5 SDIO stability fixes in `aicsdio.c` may help — see item 1 above.

---

## Kernel Tree Integrity

The kernel source tree at `/opt/captcha/kernel/linux-6.16.7` (remote build host `lan`) was used **read-only** throughout the port.

- The build command uses `-C /opt/captcha/kernel/linux-6.16.7` (read-only reference) and `M=<out-of-tree>` (write path)
- No driver source files were added under `include/`, `arch/`, `drivers/`, or `net/` in the kernel tree
- No `aic8800` files exist under `drivers/net/wireless/` in the kernel tree (verified: grep returns empty)
- The kernel `Module.symvers` timestamp (`23 Mär 00:13`) predates the driver build (`03:18`), confirming no kernel-tree writes occurred during the build
- The local workspace contains pre-existing kernel header mirrors (`include/`, `arch/`, `drivers/`, `net/`) that were placed at workspace initialization time (`00:08:50`) — these were not touched by the driver port

---

## Preserved V1-Specific Configuration

| Setting | Value | Reason |
|---|---|---|
| `CONFIG_PLATFORM_MAINLINE_SUNXI` | `y` (exported) | H713 Allwinner mainline kernel platform |
| `CONFIG_SDIO_PWRCTRL` | `y` | H713 SDIO power control required |
| `CONFIG_AIC_FW_PATH` | `/usr/lib/firmware/aic8800_sdio/aic8800` | BSP firmware path |
| `KDIR` | `/opt/captcha/kernel/linux-6.16.7` | Target kernel tree |
| `ARCH` | `arm` | Allwinner H713 ARM32 mode |
| `CROSS_COMPILE` | `arm-linux-gnueabi-` | ARM32 cross-compiler |
| Module load order | `bsp → fdrv → btlpm` | Dependency chain preserved |
| Module names | `aic8800_bsp`, `aic8800_fdrv`, `aic8800_btlpm` | Unchanged |
