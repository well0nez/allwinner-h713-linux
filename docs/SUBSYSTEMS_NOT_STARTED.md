# HY310 Subsystems: Status Notes

This file documents subsystems that have not been brought up yet, are blocked,
or have been confirmed working. Each entry lists the known MMIO address,
compatible string, IRQ, clock/reset IDs, and required work.

---

## SPI

- **Status**: N/A
- **MMIO**: SPI0 `0x04025000`, SPI1 `0x04026000`
- **Notes**: Both ports disabled in stock DTS, no SPI devices connected on HY310

---

## CRYPTO (CE)

- **Status**: WORKING (built-in)
- **MMIO**: `0x03040000`
- **Driver**: sun8i-ce (CONFIG_CRYPTO_DEV_SUN8I_CE=y)
- **Notes**: 33 crypto algorithms registered, DTS node present, probes cleanly

---

## CEDAR / VPU (Video Engine)

- **Status**: WORKING (patched module)
- **MMIO**: 0x01C0E000
- **Driver**: sunxi-cedrus (staging, patched for H713 VE3 clock/reset)
- **Capabilities**: H.264, H.265 (10-bit), MPEG-2, VP8 hardware decode
- **DTS**: video-codec@1c0e000 with syscon/SRAM, IOMMU, 4 clocks, 2 resets
- **Patch**: 0022-staging-cedrus-add-h713-ve3-clock-reset.patch
- **Known issue**: power-domains = <&ppu 3> causes EPROBE_DEFER, currently
  disabled. VE power domain activation needs further investigation.
- **FFmpeg**: Custom v4l2-request build at /root/ffmpeg-v4l2request/ on target
- **Benchmark**: 1080p60 H.264 decode: 141 fps, 48% CPU (vs 117 fps, 215% CPU software)


## IOMMU

- **Status**: WORKING (provider only, no consumers attached)
- **MMIO**: 0x030f0000 (confirmed from stock HY300 DTS + live probe)
- **Compatible**: allwinner,sun50i-h6-iommu
- **IRQ**: SPI 24 (extracted from stock eMMC DTB; SPI 57 was H6, collides with pinctrl)
- **Clocks**: CLK_BUS_IOMMU
- **Resets**: index 11 (RST_BUS_IOMMU symbol not resolved by DTS compiler, used numeric)
- **Fix**: Removed select ARM_DMA_USE_IOMMU from SUN50I_IOMMU Kconfig entry.
  The global ARM32 DMA-IOMMU layer corrupted of_node pointers. Without it, the IOMMU
  provider probes cleanly as a standalone IOMMU API provider.
- **Next**: Attach consumers via iommus phandle in DTS (Cedar VE, Display blocks)
---

## Confirmed Working (moved from "not started")

### GPU (Mali-G31 Panfrost)
- **Status**: WORKING (since 2026-04-03)
- **MMIO**: `0x01800000`
- **Driver**: Panfrost + sun50i-h713-ppu power domain
- **Notes**: 864MHz core, 150MHz bus, card0/renderD128, PRIME to h713_drm verified

### HW Spinlock
- **Status**: WORKING (built-in)
- **MMIO**: `0x03004000`
- **Driver**: sun6i-hwspinlock
- **Notes**: Probes at boot, actively used by cpu_comm for ARM-MIPS shared memory sync

### CIR (IR Receiver)
- **Status**: WORKING
- **MMIO**: `0x07040000`
- **Driver**: sunxi-cir (patched for H713)
- **Notes**: NEC/RC5/RC6 decoders, /dev/lirc0, PL9 with mux 3 (s_cir).
  Key fix: stock H713 uses mux 3 for IR on PL9, not mux 2 as assumed from H616.
  Confirmed via IDA RE of stock sun50iw12 R_PIO pinctrl driver.

### RTC
- **Status**: WORKING
- **MMIO**: `0x07000000`
- **Driver**: sun6i-rtc (upstream)

### I2C
- **Status**: WORKING
- **Buses**: I2C0-3 at `0x02502000`..`0x02502C00`
- **Driver**: i2c-mv64xxx (upstream)
- **Notes**: I2C1 used for DLPC3435 (0x1B) and STK8BA58 accelerometer

### PWM
- **Status**: WORKING
- **MMIO**: `0x0300A000`
- **Driver**: pwm-sun8i (custom 8-channel driver)
- **Notes**: Fan speed and backlight control

---

## Not Applicable

### TV Demodulator (DTMB)
- **MMIO**: TVCAP `0x05400000`, TVFE `0x05080000`
- **Status**: N/A — not needed for projector use case
- **Notes**: DTMB is Chinese digital terrestrial TV reception. The H713 SoC includes this
  IP block because the SoC is also used in set-top boxes, but the HY310 projector has no
  antenna input and no tuner hardware. This subsystem will not be brought up.
