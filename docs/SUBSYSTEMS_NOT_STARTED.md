# HY310 Subsystems: Not Started / Minimal Status

This file documents subsystems that have not been brought up yet (or are working with upstream drivers requiring no custom work). Each entry lists the known MMIO address, compatible string, IRQ, clock/reset IDs, and required work.

---

## GPU

- **Status**: not started
- **MMIO**: `0x01800000` (Mali-G57 / Bifrost)
- **Compatible**: `arm,mali-bifrost` (stock DTS)
- **Power domain**: `pd_gpu` (tv303-pmu)
- **Required**: Enable pd_gpu power domain, add Mali Bifrost DTS node, build Mali kernel module (out-of-tree or Panfrost)

---

## LRADC

- **Status**: not started
- **MMIO**: `0x07090000`
- **Compatible**: `allwinner,sun50i-r329-lradc` (stock DTS)
- **IRQ**: SPI 216
- **Required**: DTS node, input-keys or IIO driver for NTC thermistor and button matrix
- **Note**: Used by board manager for NTC temperature sensing

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

## IOMMU

- **Status**: not started
- **MMIO**: `0x030f0000`
- **Compatible**: `allwinner,sun50i-h616-iommu` (stock DTS)
- **IRQ**: SPI 61
- **Required**: DTS node present with correct address (0x02010000).
- **BLOCKED**: CONFIG_SUN50I_IOMMU selects ARM_DMA_USE_IOMMU on ARM32, which corrupts
  platform device of_node pointers causing kernel crashes in all module probes.
  Needs investigation: may require ARM64 or a workaround for the DMA-IOMMU layer.

---

## HW_SPINLOCK

- **Status**: not started
- **MMIO**: `0x03004000`
- **Compatible**: `allwinner,sun6i-hwspinlock` (stock DTS)
- **Required**: DTS node; upstream hwspinlock driver; used by ARISC/ARM shared resource locking

---

## CIR (IR Receiver)

- **Status**: WORKING
- **MMIO**: `0x07040000`
- **Compatible**: `allwinner,sun50i-h616-ir` (upstream driver `sunxi-ir`)
- **IRQ**: SPI 206
- **Clocks**: `ir`, `ir-mod` (R_CCU)
- **Notes**: Standard upstream driver, no custom patches required

---

## RTC

- **Status**: WORKING
- **MMIO**: `0x07000000`
- **Compatible**: `allwinner,sun50i-h616-rtc` (upstream `sun6i-rtc` driver)
- **IRQ**: SPI 207 (alarm)
- **Notes**: Standard upstream driver; LOSC external crystal not populated on this board

---

## I2C

- **Status**: WORKING
- **Buses**: I2C0 `0x02502000`, I2C1 `0x02502400`, I2C2 `0x02502800`, I2C3 `0x02502C00`
- **Compatible**: `allwinner,sun50i-h616-i2c` (upstream `i2c-mv64xxx` / `i2c-sunxi` driver)
- **Notes**: Standard upstream driver; I2C1 used for DLPC3435 projector (address TBD); I2C0 used for mir3da accelerometer at `0x27`

---

## PWM

- **Status**: WORKING
- **MMIO**: `0x0300A000`
- **Compatible**: `allwinner,sun50i-h616-pwm` → driver `sun4i-pwm`
- **Notes**: Working but `npwm=2` in current DTS; H713 needs `npwm=8` to expose channel 2 for backlight dimming (see `DISPLAY.md`)

---

## DEMODULATOR

- **Status**: not started
- **MMIO**: TVCAP `0x05400000`, TVFE `0x05080000`
- **Compatible**: stock uses proprietary `vs,h713-demod` / `vs,h713-tvcap`
- **Power domains**: `pd_tvfe`, `pd_tvcap` (tv303-pmu)
- **Required**: Full reverse engineering of demodulator firmware and register interface; no upstream driver exists; MIPS co-processor involvement likely
