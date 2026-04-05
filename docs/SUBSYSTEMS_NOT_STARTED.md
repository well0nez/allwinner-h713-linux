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

- **Status**: not started
- **MMIO**: `0x01C0E000`
- **Compatible (stock)**: `allwinner,sunxi-cedar-ve`
- **Compatible (mainline)**: `allwinner,sun50i-h6-video-engine` (closest match)
- **IRQ**: SPI 75
- **Clocks**: bus_ve (CLK_BUS_VE=27), bus_ve3 (CLK_BUS_VE3=29), ve (CLK_VE_CORE=26), mbus_ve3 (CLK_MBUS_VE3=45)
- **Resets**: reset_ve (RST_BUS_VE=7), reset_ve3 (RST_BUS_VE3=9)
- **Power domain**: PPU domain 3 (pd_ve)
- **Driver**: `sunxi-cedrus` (staging, built as module in current config)
- **Blocker**: Stock VE uses IOMMU which cannot be enabled on ARM32. Needs testing without IOMMU.
- **Required**: DTS node, compatible string matching, IOMMU workaround, VE SRAM allocation

---

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
