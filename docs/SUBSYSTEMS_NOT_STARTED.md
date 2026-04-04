# HY310 Subsystems: Status Notes

This file documents subsystems that have not been brought up yet, are blocked,
or have been confirmed working. Each entry lists the known MMIO address,
compatible string, IRQ, clock/reset IDs, and required work.

---

## SPI

- **Status**: not started
- **MMIO**: SPI0 `0x04025000`, SPI1 `0x04026000`
- **Compatible**: `allwinner,sun50i-h313-spi` (stock DTS)
- **IRQs**: SPI0 = SPI 12, SPI1 = SPI 13
- **Clocks**: `spi0`, `spi1` (CCU); resets: `rst-spi0`, `rst-spi1`
- **Required**: DTS nodes, verify upstream spi-sun6i driver compatibility

---

## CRYPTO (CE)

- **Status**: not started
- **MMIO**: `0x03040000`
- **Compatible**: `allwinner,sun50i-h616-ce` (stock DTS)
- **IRQ**: SPI 52
- **Clocks**: `ce`, `ce-mod` (CCU); reset: `rst-ce`
- **Required**: DTS node; upstream `sun8i-ce` driver should work with minor compatible addition

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

- **Status**: BLOCKED (cannot enable on ARM32)
- **MMIO**: `0x030f0000` / `0x02010000`
- **Compatible**: `allwinner,sun50i-h616-iommu` (stock DTS)
- **IRQ**: SPI 61
- **Blocker**: CONFIG_SUN50I_IOMMU selects ARM_DMA_USE_IOMMU on ARM32, which corrupts
  platform device of_node pointers (set to 0x1) causing kernel crashes in all module probes.
  Would require ARM64 port or kernel framework fix. Panfrost uses GPU internal MMU instead.

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
- **Driver**: sunxi-cir (upstream)
- **Notes**: NEC protocol, PL9, no custom patches required

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
