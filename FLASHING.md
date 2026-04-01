# Flashing the HY310

## Boot Architecture

The HY310 uses a **stock Allwinner U-Boot** that cannot be easily replaced.
This U-Boot only accepts **Android Boot v3** format images (`ANDROID!` magic header).

Key constraints:
- U-Boot ignores the boot image header cmdline — the kernel cmdline is
  **hardcoded in the device tree** (`chosen/bootargs`). This is intentional:
  we do not want U-Boot or any other component overriding our boot parameters.
- The boot image must be split into 4MB chunks (`mboot32.00`, `mboot32.01`)
  because U-Boot uses `fatload` which has size limitations on this platform.
- zImage + appended DTB (`CONFIG_ARM_APPENDED_DTB=y`) is required.

## eMMC Partition Map

| Partition | Offset | Size | Content |
|-----------|--------|------|---------|
| p3 | 204800 | 256K | **env_a** (U-Boot environment, CRC32 signed) |
| p4 | 205312 | 256K | env_b |
| p5 | 205824 | 64M | **boot_a** — OUR MAINLINE KERNEL |
| p6 | 336896 | 64M | boot_b (stock Android kernel backup) |

## Method 1: Permanent eMMC Boot (Recommended)

### First-time setup: Patch U-Boot Environment

The stock U-Boot env needs to be patched once to add `usb start` to the
boot command (needed for USB PHY initialization before the kernel):

```bash
# See: https://github.com/well0nez/sunxi-env-patcher
python3 sunxi-env-patcher/patch_env.py
```

This patches `env_a` (mmcblk0p3) with correct CRC32 checksum.
**Bootcmd becomes:** `usb start; run setargs_nand boot_normal`

### Flash the Boot Image

Use the hash-chain verified flash workflow:

```bash
# On build machine:
scripts/flash.sh output/hy310-mainline-arm32-boot.img 192.168.8.141
```

This script:
1. Computes SHA256 of the image on the build machine
2. Copies image to HY310 via SCP
3. Verifies SHA256 on device matches
4. Writes to /dev/mmcblk0p5 (boot_a) via dd
5. Reads back partition and verifies SHA256 again
6. Only reports success if all 3 hashes match

**NEVER flash if hashes don't match. NEVER touch boot_b (p6) — that's the
stock Android fallback.**

### Auto-boot Flow

After flashing + patching env_a:

```
Power on → U-Boot (5s delay) → usb start → load kernel from boot_a (p5)
→ kernel boots with DTS cmdline → rootwait finds USB stick → Debian boots
→ WiFi connects → SSH available (~15-20s total)
```

## Method 2: USB Stick Boot (Rescue / Testing)

The USB stick contains a known-good kernel as failsafe. Boot from it via
U-Boot when eMMC boot_a is broken:

```
# At U-Boot prompt (interrupt via UART during 5s bootdelay):
usb start
fatload usb 0:1 0x45000000 mboot32.00
fatload usb 0:1 0x45400000 mboot32.01
bootm 0x45000000
```

The USB stick has:
- **Partition 1 (FAT32):** `mboot32.00` + `mboot32.01` (boot image chunks)
- **Partition 2 (ext4):** Debian rootfs

**NEVER modify the USB stick boot files during normal operation.** It is the
failsafe recovery path.

## Recovery via UART

If the HY310 is in a boot loop (kernel panic, bad image), use the UART bridge:

```bash
# From Windows (via OrangePi UART-TCP bridge):
python3 tools/uboot_interrupt.py --boot-usb
```

This connects to the UART bridge at 192.168.8.179:9999, sends rapid keypresses
to interrupt U-Boot's 5-second bootdelay, then issues the USB boot commands.

## Rootfs Location

The kernel uses `root=/dev/sda2 rootwait` (from DTS chosen/bootargs).
This means the rootfs must be on a USB storage device partition 2 (ext4).
The USB stick serves this purpose.
