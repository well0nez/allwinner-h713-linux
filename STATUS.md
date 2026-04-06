# HY310 Mainline Linux Port — Status

> Last updated: 2026-04-04

## Subsystem Status Overview

| Subsystem | Status | Driver | Notes |
|-----------|--------|--------|-------|
| **Boot** | Working | Stock U-Boot + patched env | Android Boot v3, cmdline in DTS |
| **Serial Console** | Working | 8250_dw | ttyS0 @ 115200 |
| **eMMC** | Working | sunxi-mmc (patched) | DDR HS @ 100MHz, 7.3GB |
| **USB** | Working | ehci/ohci + phy-sun4i-usb (patched) | 3x EHCI + 3x OHCI |
| **WiFi** | Working | aic8800_bsp + aic8800_fdrv (out-of-tree) | AIC8800D80 SDIO, stable |
| **Bluetooth** | Working | hci_uart H4 + aic8800_btlpm | Auto-start via systemd, 1.5Mbaud flow control |
| **IR Remote** | Working | sunxi-cir + rc-core decoders | NEC/RC5/RC6, /dev/lirc0, PL9 mux 3 (IDA-verified) |
| **RTC** | Working | sun6i-rtc | @ 0x07090000 |
| **Thermal** | Working | sun8i-thermal | 2 zones (CPU ~65C, GPU ~66C) |
| **I2C** | Working | mv64xxx | TWI1, STK8BA58 accelerometer |
| **PWM** | Working | pwm-sun8i (new driver) | 8 channels |
| **Fan Control** | Working | hy310-board-mgr | PWM fan + tachometer + NTC |
| **Watchdog** | Working | sunxi-wdt | @ 0x02051000 |
| **Reboot** | Working | sunxi-wdt | via watchdog reset |
| **Poweroff** | Working | — | Confirmed functional |
| **Keystone Motor** | Untested | hy310-keystone-motor | Sysfs works, limit switch defective on test unit |
| **Audio** | Working | codec + cpudai + machine (out-of-tree) | Speaker output, digital volume control, auto-start at boot |
| **Display (DRM/KMS)** | Working | h713_drm (out-of-tree) | DRM/GEM scanout, PRIME, Labwc desktop runs |
| **Video Decode (Cedrus)** | Working | sunxi-cedrus (patched, module) | H.264/H.265/MPEG2/VP8 HW decode, V4L2 stateless API |
| **Display (legacy)** | Working | ge2d + tvtop + mipsloader (in-tree) | Stock display pipeline, MIPS-initialized |
| **ARM-MIPS IPC** | Partial | cpu_comm (in-tree, out-of-tree) | Protocol works, MIPS Msgbox IRQ not routed |
| **GPU** | Working | panfrost + sun50i-h713-ppu | Mali-G31 864MHz, card0/renderD128, PRIME to h713_drm |
| **IOMMU** | Working (provider only) | sun50i-iommu (built-in) | Provider at 0x030f0000, no consumers attached yet |
| **GPADC** | Working | sun20i-gpadc (IIO) | 2 ADC channels via /sys/bus/iio/ |
| **LRADC** | Working | sun50i-h713-lradc (IIO, built-in) | NTC temp sensing for board-mgr via IIO consumer |
| **LRADC Keyboard** | Unclear | — | @ 0x02009800, 6 keys + power |
| **SPI** | N/A | — | No devices connected on HY310 |
| **Crypto Engine** | Working | sun8i-ce (built-in) | HW AES/SHA, 33 algorithms registered |
| **HW Spinlock** | Working | sun6i-hwspinlock (built-in) | Used by cpu_comm for ARM↔MIPS sync |

## Display Pipeline (DRM/KMS) — New

The H713 uses a custom display pipeline (NOT standard Allwinner DE2/DE3/TCON):

```
TVTOP (bus fabric) -> VBlender (timing) -> OSD (plane) -> AFBD -> LVDS -> DLPC3435 -> DLP
```

**Root cause of initial VBlender-reads-zero problem**: TVTOP bus fabric routing
registers at 0x05700000 must be programmed before any display sub-blocks respond.
See [docs/DISPLAY_BRINGUP.md](docs/DISPLAY_BRINGUP.md).

**Current DRM driver** (`drivers/display/drm/h713_drm.c`):
- Out-of-tree module, binds to `trix,ge2d` compatible
- `drm_simple_display_pipe` with fixed 1920x1080@60 LVDS mode
- GEM DMA scanout via AFBD controller (scanout addr at AFBD_CTRL+0x78)
- Warm-disable strategy (clocks kept alive, MIPS owns timing/PHY init)
- PRIME buffer sharing with Panfrost verified (bidirectional roundtrip)
- Weston launches with GL renderer (Panfrost), LVDS output enabled
- **Blocker**: CMA pool too small for Weston buffer allocation (ENOMEM on CREATE_DUMB)

## Known Issues

- **IR Remote: NEC kernel decoder unreliable** — LIRC raw data is correct but
  the kernel NEC decoder does not reliably match timings. Root cause: the stock
  H713 IR driver uses 3 R_CCU clocks (bus/pclk/mclk) with clk_set_parent 
  which configures a different prescaler than our D1-based R_CCU (2 clocks only).
  This makes rx_resolution ~25% off. Fix requires adding H713-specific clock
  indices to the R_CCU driver or implementing the 3-clock setup in sunxi-cir.
  Workaround: use lircd with raw timing config for remote control decoding.

- **MIPS IPC: Msgbox IRQ blocked** — ARM can send to MIPS (Msgbox TX works,
  MIPS reads FIFO), but MIPS cannot interrupt ARM because HW IRQ 25 at the MIPS
  INTC never asserts despite Msgbox IRQ status being pending. This is the
  fundamental blocker for bidirectional ARM-MIPS communication.
  See [docs/CPU_COMM.md](docs/CPU_COMM.md).



- **Motor** — Position tracking works via sysfs, but physical movement after
  boot homing is inconsistent. Limit switch (PH14) always reads LOW.

## Build Verification

This repository has been tested with the following workflow:
1. Fresh vanilla linux-6.16.7 extracted from tarball
2. All 16 patches applied cleanly (0 failures)
3. Kernel zImage built successfully (4m52s)
4. 20 in-tree kernel modules built
5. All out-of-tree modules built (audio 3x, bridge, ge2d, wifi 3x, h713_drm)
6. DTB from standalone DTS is SHA256-identical to production DTB
7. H713 DRM regression gates pass (reopen, reload, modetest, PRIME)
