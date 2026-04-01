# HY310 Projector — Mainline Linux Port

> **Work in Progress** — This project is under active development. Many subsystems
> work, but nothing is finalized. Contributions and testing welcome.

## What is this?

Mainline Linux 6.16.7 port for the **HY310 portable projector** based on the
**Allwinner H713** (sun50iw12p1) SoC. The H713 is a quad-core Cortex-A53 with
1GB DDR3, a built-in MIPS display co-processor, Mali-G31 GPU, and custom display
pipeline used in several affordable portable projectors (HY310, HY300, Magcubic,
etc.).

## Board Specifications

| Component | Details |
|-----------|---------|
| SoC | Allwinner H713 (sun50iw12p1), 4x Cortex-A53 |
| RAM | 1GB DDR3 |
| Storage | 7.3GB eMMC (Samsung KLM8G1GETF-B041) |
| WiFi | AIC8800D80 SDIO (802.11ac, onboard) |
| Bluetooth | AIC8800 BT 5.4 via UART |
| Display | MIPS co-processor driven, 1920x1080 DLP via DLPC3435 |
| Audio | Internal codec + TridentALSA bridge (MIPS dependency) |
| USB | 3x EHCI + 3x OHCI, USB-C (power + data) |
| IR | NEC protocol IR receiver on PL9 |
| Motor | 4-phase stepper for keystone correction |
| Fan | PWM-controlled cooling fan with tachometer |
| Sensors | Accelerometer (STK8BA58), NTC thermistor |

## Quick Start

See [BUILDING.md](BUILDING.md) for full build instructions.

```bash
# 1. Get vanilla kernel
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.16.7.tar.xz
tar xf linux-6.16.7.tar.xz

# 2. Apply patches
cd linux-6.16.7
for p in $(cat ../hy310-linux/patches/series); do
    patch -p1 < ../hy310-linux/patches/$p
done

# 3. Build
cp ../hy310-linux/config/hy310_defconfig arch/arm/configs/
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- hy310_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- -j$(nproc) zImage modules
```

See [FLASHING.md](FLASHING.md) for how to create an Android Boot v3 image
and flash it to the HY310.

## Repository Structure

```
dts/            — Standalone device tree source
dt-bindings/    — Clock and reset ID headers
config/         — Kernel defconfig
patches/        — 16 patches against vanilla linux-6.16.7
drivers/        — Out-of-tree kernel modules (audio, display, wifi)
scripts/        — Build, flash, and utility scripts
tools/          — Debug and analysis tools
docs/           — Per-subsystem documentation
reference/      — Stock firmware analysis material
```

## Current Status

See [STATUS.md](STATUS.md) for a detailed breakdown. Summary:

**Working:** Boot, serial console, eMMC, USB (3 ports), WiFi (AIC8800 SDIO),
Bluetooth, IR remote, RTC, thermal sensors, fan control, keystone motor,
I2C sensors, 8-channel PWM, watchdog, reboot, poweroff.

**Partial:** Audio (codec probes, no sound — MIPS DSP dependency), Display
(framebuffer writes work, no OSD scanout), ARM-MIPS IPC (protocol works,
MIPS IRQ routing blocked).

**Not started:** GPU (Mali-G31/Panfrost), GPADC, LRADC keyboard, SPI,
Ethernet, crypto engine, IOMMU, hardware spinlock, TV demodulator.

## Boot Architecture

The HY310 uses a stock U-Boot that only accepts **Android Boot v3** format
images. The kernel command line is **hardcoded in the device tree** because
U-Boot ignores the boot image header cmdline. See [BOOT.md](docs/BOOT.md)
for the full boot flow.

## Authors

- **well0nez** — Primary developer, reverse engineering, driver porting

## License

Kernel patches and drivers: GPL-2.0 (matching Linux kernel license).
Documentation and tools: MIT.
