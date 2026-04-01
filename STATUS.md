# HY310 Mainline Linux Port — Status

> Last updated: 2026-04-01

## Subsystem Status Overview

| Subsystem | Status | Driver | Notes |
|-----------|--------|--------|-------|
| **Boot** | Working | Stock U-Boot + patched env | Android Boot v3, cmdline in DTS |
| **Serial Console** | Working | 8250_dw | ttyS0 @ 115200 |
| **eMMC** | Working | sunxi-mmc (patched) | DDR HS @ 100MHz, 7.3GB |
| **USB** | Working | ehci/ohci + phy-sun4i-usb (patched) | 3x EHCI + 3x OHCI |
| **WiFi** | Working | aic8800_bsp + aic8800_fdrv (out-of-tree) | AIC8800D80 SDIO, stable |
| **Bluetooth** | Working | hci_uart H4 + aic8800_btlpm | Manual hciattach, autostart WIP |
| **IR Remote** | Working | sunxi-cir | NEC protocol, PL9 |
| **RTC** | Working | sun6i-rtc | @ 0x07090000 |
| **Thermal** | Working | sun8i-thermal | 2 zones (CPU ~65C, GPU ~66C) |
| **I2C** | Working | mv64xxx | TWI1, STK8BA58 accelerometer |
| **PWM** | Working | pwm-sun8i (new driver) | 8 channels |
| **Fan Control** | Working | hy310-board-mgr | PWM fan + tachometer + NTC |
| **Watchdog** | Working | sunxi-wdt | @ 0x02051000 |
| **Reboot** | Working | sunxi-wdt | via watchdog reset |
| **Poweroff** | Working | — | Confirmed functional |
| **Keystone Motor** | Partial | hy310-keystone-motor | Sysfs works, physical movement inconsistent |
| **Audio** | Partial | codec + cpudai + machine + bridge (out-of-tree) | Card probes, no sound output (MIPS DSP dependency) |
| **Display** | Partial | ge2d + tvtop + mipsloader (in-tree) | FB writes work, no OSD scanout |
| **ARM-MIPS IPC** | Partial | cpu_comm (in-tree, out-of-tree) | Protocol works, MIPS Msgbox IRQ not routed |
| **GPU** | Not started | — | Mali-G31 @ 0x01800000, needs Panfrost + IOMMU |
| **IOMMU** | Not started | — | @ 0x02010000, needed for GPU |
| **GPADC** | Not started | — | @ 0x02009000, 2 channels |
| **LRADC Keyboard** | Not started | — | @ 0x02009800, 6 keys + power |
| **SPI** | Not started | — | SPI0 @ 0x04025000, SPI1 @ 0x04026000 |
| **Crypto Engine** | Not started | — | @ 0x03040000 |
| **HW Spinlock** | Not started | — | @ 0x03004000 |
| **TV Demodulator** | Not started | — | DTMB @ 0x06600000 |

## Known Issues

- **Audio: No sound output** — The internal codec probes and ALSA card registers,
  but speaker audio on this SoC goes through the MIPS co-processor's audio DSP.
  The DSP firmware must be loaded via `msp_download_sxl()` before audio works.
  See [docs/AUDIO.md](docs/AUDIO.md).

- **Display: No OSD scanout** — The framebuffer exists and FB writes are visible
  (noise via `dd if=/dev/urandom of=/dev/fb0`), but the OSD/VBlender hardware
  block at 0x05200000 is dead (reads zero). Display output currently relies on
  the U-Boot-initialized MIPS scanout. See [docs/DISPLAY.md](docs/DISPLAY.md).

- **MIPS IPC: Msgbox IRQ blocked** — ARM can send to MIPS (Msgbox TX works,
  MIPS reads FIFO), but MIPS cannot interrupt ARM because HW IRQ 25 at the MIPS
  INTC never asserts despite Msgbox IRQ status being pending. This is the
  fundamental blocker for bidirectional ARM-MIPS communication.
  See [docs/CPU_COMM.md](docs/CPU_COMM.md).

- **BT autostart** — hciattach at 1500000 baud fails on cold boot (HCI Reset
  timeout). Works when run manually after system is fully up. Likely needs
  initial 115200 baud before speed switch.

- **Motor** — Position tracking works via sysfs, but physical movement after
  boot homing is inconsistent. Limit switch (PH14) always reads LOW.

## Build Verification

This repository has been tested with the following workflow:
1. Fresh vanilla linux-6.16.7 extracted from tarball
2. All 16 patches applied cleanly (0 failures)
3. Kernel zImage built successfully (4m52s)
4. 20 in-tree kernel modules built
5. All out-of-tree modules built (audio 3x, bridge, ge2d, wifi 3x)
6. DTB from standalone DTS is SHA256-identical to production DTB
