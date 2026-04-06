#!/bin/bash
set -e

KDIR=/opt/captcha/kernel/linux-6.16.7
OUTDIR=/opt/captcha/kernel/output_arm32

export ARCH=arm
export CROSS_COMPILE=arm-linux-gnueabi-

mkdir -p "$OUTDIR"

echo "=== HY310 Mainline Kernel Build (ARM32) ==="
echo "Kernel: Linux 6.16.7"
echo "Toolchain: $(arm-linux-gnueabi-gcc --version | head -1)"
echo "Cores: $(nproc)"
echo ""

cd "$KDIR"
make mrproper

# ARM32 sunxi defconfig as base
echo "=== Step 1: sunxi_defconfig ==="
make sunxi_defconfig

# Apply H713-specific options
echo "=== Step 2: H713 options ==="
./scripts/config --enable CONFIG_ARCH_SUNXI
./scripts/config --enable CONFIG_MACH_SUN50I

# Serial (critical)
./scripts/config --enable CONFIG_SERIAL_8250
./scripts/config --enable CONFIG_SERIAL_8250_CONSOLE
./scripts/config --enable CONFIG_SERIAL_8250_DW
./scripts/config --enable CONFIG_SERIAL_OF_PLATFORM
./scripts/config --enable CONFIG_SERIAL_EARLYCON

# Storage
./scripts/config --enable CONFIG_MMC
./scripts/config --enable CONFIG_MMC_SUNXI
./scripts/config --enable CONFIG_MMC_BLOCK
./scripts/config --enable CONFIG_EXT4_FS
./scripts/config --enable CONFIG_VFAT_FS
./scripts/config --enable CONFIG_FAT_FS

# USB
./scripts/config --enable CONFIG_USB
./scripts/config --enable CONFIG_USB_OHCI_HCD
./scripts/config --enable CONFIG_USB_EHCI_HCD
./scripts/config --enable CONFIG_USB_STORAGE

# USB Networking (CDC ECM/NCM, RNDIS, common USB-Ethernet chips)
./scripts/config --module CONFIG_USB_USBNET
./scripts/config --module CONFIG_USB_NET_CDC_ETHER
./scripts/config --module CONFIG_USB_NET_CDCNCM
./scripts/config --module CONFIG_USB_NET_RNDIS_HOST
./scripts/config --module CONFIG_USB_RTL8152
./scripts/config --module CONFIG_USB_NET_AX8817X
./scripts/config --module CONFIG_USB_NET_AX88179_178A
./scripts/config --module CONFIG_USB_NET_SMSC95XX

# WiFi stack (mainline)
./scripts/config --enable CONFIG_WIRELESS
./scripts/config --enable CONFIG_CFG80211
./scripts/config --disable CONFIG_CFG80211_REQUIRE_SIGNED_REGDB
./scripts/config --disable CONFIG_CFG80211_USE_KERNEL_REGDB_KEYS
./scripts/config --enable CONFIG_CFG80211_INTERNAL_REGDB
./scripts/config --enable CONFIG_MAC80211
./scripts/config --enable CONFIG_WLAN
./scripts/config --enable CONFIG_RFKILL
./scripts/config --enable CONFIG_WLAN_VENDOR_REALTEK
./scripts/config --module CONFIG_RTL8XXXU
./scripts/config --enable CONFIG_RTL8XXXU_UNTESTED

# Use built-in regulatory DB instead of early signed external firmware fetch
./scripts/config --enable CONFIG_FW_LOADER
./scripts/config --set-str CONFIG_EXTRA_FIRMWARE ""
./scripts/config --set-str CONFIG_EXTRA_FIRMWARE_DIR ""

# Networking for WiFi
./scripts/config --enable CONFIG_INET
./scripts/config --enable CONFIG_IPV6
./scripts/config --enable CONFIG_PACKET
./scripts/config --enable CONFIG_UNIX

# No embedded initramfs (external rootfs on USB)
./scripts/config --set-str CONFIG_INITRAMFS_SOURCE ""

# Boot
./scripts/config --enable CONFIG_DEVTMPFS
./scripts/config --enable CONFIG_DEVTMPFS_MOUNT
./scripts/config --enable CONFIG_TMPFS
./scripts/config --enable CONFIG_PROC_FS
./scripts/config --enable CONFIG_SYSFS

# Pinctrl / GPIO
./scripts/config --enable CONFIG_PINCTRL
./scripts/config --enable CONFIG_PINCTRL_SUNXI
./scripts/config --enable CONFIG_PINCTRL_SUN50I_H6
./scripts/config --enable CONFIG_GPIOLIB
./scripts/config --enable CONFIG_GPIO_SYSFS

# Clock / Thermal / Power
./scripts/config --enable CONFIG_COMMON_CLK
./scripts/config --enable CONFIG_CPUFREQ
./scripts/config --enable CONFIG_CPUFREQ_DT
./scripts/config --enable CONFIG_THERMAL
./scripts/config --enable CONFIG_SUN8I_THERMAL
./scripts/config --enable CONFIG_REGULATOR

# DMA
./scripts/config --enable CONFIG_DMADEVICES
./scripts/config --enable CONFIG_DMA_SUN6I

# I2C / SPI
./scripts/config --enable CONFIG_I2C
./scripts/config --enable CONFIG_I2C_SUN6I
./scripts/config --enable CONFIG_SPI
./scripts/config --enable CONFIG_SPI_SUN6I

# Crypto Engine (CE)
./scripts/config --enable CONFIG_CRYPTO
./scripts/config --enable CONFIG_CRYPTO_ENGINE
./scripts/config --enable CONFIG_CRYPTO_DEV_ALLWINNER
./scripts/config --enable CONFIG_CRYPTO_DEV_SUN8I_CE

# Framebuffer (kept for stock ge2d compatibility)
./scripts/config --enable CONFIG_FB
./scripts/config --enable CONFIG_FB_VIRTUAL

# Phase 0: Panfrost GPU (Mali-G31 Bifrost, render-only /dev/dri/renderD128)
# Decoupled IOMMU strategy: enable the SUN50I provider plus API/support
# while keeping ARM_DMA_USE_IOMMU off so the global ARM32 DMA path stays disabled.
./scripts/config --enable CONFIG_DRM
./scripts/config --module CONFIG_DRM_PANFROST
./scripts/config --enable CONFIG_SUN50I_H713_PPU
./scripts/config --enable CONFIG_PM_GENERIC_DOMAINS
./scripts/config --disable CONFIG_SUN50I_H6_PRCM_PPU
./scripts/config --enable CONFIG_SUN50I_IOMMU
./scripts/config --enable CONFIG_IOMMU_SUPPORT
./scripts/config --enable CONFIG_IOMMU_API

# Cedrus VPU decode must stay modular for bring-up/debugging
./scripts/config --module CONFIG_VIDEO_SUNXI_CEDRUS

# Watchdog / RTC / PWM / IR / Input
./scripts/config --enable CONFIG_WATCHDOG
./scripts/config --enable CONFIG_RTC_CLASS
./scripts/config --enable CONFIG_PWM
./scripts/config --enable CONFIG_PWM_SUN8I
./scripts/config --disable CONFIG_PWM_SUN4I
./scripts/config --enable CONFIG_RC_CORE
./scripts/config --enable CONFIG_RC_DECODERS
./scripts/config --enable CONFIG_IR_NEC_DECODER
./scripts/config --enable CONFIG_IR_RC5_DECODER
./scripts/config --enable CONFIG_IR_RC6_DECODER
./scripts/config --enable CONFIG_LIRC
./scripts/config --enable CONFIG_INPUT
./scripts/config --enable CONFIG_INPUT_EVDEV

# DT
./scripts/config --enable CONFIG_OF
./scripts/config --enable CONFIG_OF_FLATTREE

# SMP
./scripts/config --enable CONFIG_SMP
./scripts/config --set-val CONFIG_NR_CPUS 4

# Early printk
./scripts/config --enable CONFIG_DEBUG_LL
./scripts/config --enable CONFIG_EARLY_PRINTK

# HY310 Board Management (fan, USB power, NTC thermal)
# Built-in (not module!) — fan stall detection must start as early as possible
./scripts/config --enable CONFIG_HY310_BOARD_MGR
./scripts/config --enable CONFIG_HWMON

# HY310 Keystone Motor (stepper motor for keystone correction)
# Built-in — motor homing runs at probe time
./scripts/config --enable CONFIG_HY310_KEYSTONE_MOTOR

# Disable old sunxi-cpu-comm (replaced by hy310-cpu-comm module)
./scripts/config --disable CONFIG_SUNXI_CPU_COMM
./scripts/config --enable CONFIG_HWSPINLOCK
./scripts/config --enable CONFIG_HWSPINLOCK_SUN6I
./scripts/config --module CONFIG_HY310_CPU_COMM
./scripts/config --module CONFIG_SUNXI_DECD

# Audio: ALSA + ASoC framework + H713 internal codec + CPU-DAI
# Phase 3: Audio support — drivers at sound/soc/sunxi/
./scripts/config --enable CONFIG_SOUND
./scripts/config --enable CONFIG_SND
./scripts/config --enable CONFIG_SND_SOC
./scripts/config --enable CONFIG_SND_SOC_GENERIC_DMAENGINE_PCM
./scripts/config --enable CONFIG_REGMAP_MMIO
./scripts/config --module CONFIG_SND_SOC_SUNXI_H713_CODEC
./scripts/config --module CONFIG_SND_SOC_SUNXI_H713_CPUDAI
./scripts/config --module CONFIG_SND_SOC_SUNXI_H713_MACHINE
# I2S: mainline sun4i-i2s is register-compatible with H713 DAUDIO (sun50i-h6 variant)
# IDA-verified: register offsets 0x00-0x74 match sun50i-h6-i2s exactly
./scripts/config --module CONFIG_SND_SUN4I_I2S
# OWA/SPDIF: mainline sun4i-spdif covers all variants including sun50i-h6
# IDA-verified: register offsets 0x00-0x34 match sun50i-h6-spdif exactly
./scripts/config --module CONFIG_SND_SUN4I_SPDIF

# LRADC IIO + GPADC (NTC temperature sensing + ADC keyboard)
./scripts/config --enable CONFIG_SUN50I_H713_LRADC
./scripts/config --enable CONFIG_SUN20I_GPADC
./scripts/config --module CONFIG_KEYBOARD_ADC

# Bluetooth
./scripts/config --enable CONFIG_BT
./scripts/config --module CONFIG_BT_HCIUART
./scripts/config --enable CONFIG_BT_HCIUART_H4
./scripts/config --enable CONFIG_BT_HCIUART_3WIRE
./scripts/config --enable CONFIG_BT_HCIUART_SERDEV

# Dynamic debug (required by AIC8800 WiFi/BT modules)
./scripts/config --enable CONFIG_DYNAMIC_DEBUG
./scripts/config --enable CONFIG_DYNAMIC_DEBUG_CORE

make olddefconfig

echo ""
echo "Config stats:"
grep -c '=y' .config | xargs -I{} echo "  Built-in: {}"
grep -c '=m' .config | xargs -I{} echo "  Modules: {}"

echo ""
echo "=== Step 3: Building zImage ==="
make -j$(nproc) zImage 2>&1 | tail -20

echo ""
echo "=== Step 4: Building DTBs ==="
make -j$(nproc) dtbs 2>&1 | tail -10

echo ""
echo "=== Step 4b: Building modules ==="
make -j$(nproc) modules 2>&1 | tail -10

echo ""
echo "=== Step 5: Collect output ==="
cp arch/arm/boot/zImage "$OUTDIR/"

# Copy our HY310 DTB if it was built
if [ -f arch/arm/boot/dts/allwinner/sun50i-h713-hy310.dtb ]; then
    cp arch/arm/boot/dts/allwinner/sun50i-h713-hy310.dtb "$OUTDIR/"
    echo "HY310 DTB: OK"
elif [ -f arch/arm/boot/dts/sun50i-h713-hy310.dtb ]; then
    cp arch/arm/boot/dts/sun50i-h713-hy310.dtb "$OUTDIR/"
    echo "HY310 DTB: OK (alt path)"
fi

# Install modules to rootfs if it exists
ROOTFS=/opt/captcha/debian-armhf
if [ -d "$ROOTFS" ]; then
    echo ""
    echo "=== Step 5b: Install modules to rootfs ==="
    sudo make modules_install INSTALL_MOD_PATH="$ROOTFS" 2>&1 | tail -5
    echo "Modules installed to $ROOTFS"
fi

# Gzip compress for Android boot image
echo ""
echo "=== Step 6: Create gzip compressed Android boot image ==="
gzip -9 -k -f "$OUTDIR/zImage"

python3 - "$OUTDIR/zImage.gz" "$OUTDIR" << 'PYEOF'
import struct, sys, os, math

gz_path = sys.argv[1]
outdir = sys.argv[2]

with open(gz_path, 'rb') as f:
    kernel_data = f.read()

print(f"Compressed kernel: {len(kernel_data)} bytes ({len(kernel_data)/1024/1024:.1f} MB)")

PAGE_SIZE = 4096
HEADER_SIZE = 1580

header = bytearray(HEADER_SIZE)
header[0:8] = b'ANDROID!'
struct.pack_into('<I', header, 8, len(kernel_data))
struct.pack_into('<I', header, 12, 0)  # no ramdisk
struct.pack_into('<I', header, 16, 0x16000162)
struct.pack_into('<I', header, 20, HEADER_SIZE)
struct.pack_into('<I', header, 40, 3)  # v3
cmdline = b'console=ttyS0,115200 earlycon earlyprintk loglevel=8 root=/dev/sda2 rootwait rootfstype=ext4 clk_ignore_unused'
header[44:44+len(cmdline)] = cmdline

def page_align(size):
    return ((size + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE

header_padded = bytes(header) + b'\x00' * (page_align(HEADER_SIZE) - HEADER_SIZE)
kernel_padded = kernel_data + b'\x00' * (page_align(len(kernel_data)) - len(kernel_data))
image = header_padded + kernel_padded

out_path = os.path.join(outdir, 'hy310-mainline-arm32-boot.img')
with open(out_path, 'wb') as f:
    f.write(image)

print(f"Boot image: {len(image)} bytes ({len(image)/1024/1024:.1f} MB)")

# 4MB chunks
CHUNK_SIZE = 4 * 1024 * 1024
offset = 0
idx = 0
while offset < len(image):
    end = min(offset + CHUNK_SIZE, len(image))
    chunk = image[offset:end]
    name = f"mboot32.{idx:02d}"
    path = os.path.join(outdir, name)
    with open(path, 'wb') as f:
        f.write(chunk)
    offset = end
    idx += 1

print(f"{idx} chunks created")
print()
print("=== U-Boot commands ===")
print("usb start")
base = 0x45000000
offset = 0
for i in range(idx):
    addr = base + i * CHUNK_SIZE
    print(f"fatload usb 0:1 0x{addr:08x} mboot32.{i:02d}")
print(f"bootm 0x{base:08x}")
PYEOF

echo ""
echo "=== Output ==="
ls -lh "$OUTDIR/"
echo ""
echo "=== DONE ==="
date
