# HY310 Boot Subsystem

## SoC / Boot Mode

- SoC: Allwinner H713 (sun50iw12p1)
- ARM32 boot: stock BL31 hands off to kernel in ARM32 mode (spsr=0x1d3)
- No ATF hand-off to AArch64 in this board configuration

## U-Boot Constraints

- Stock U-Boot only accepts **Android Boot v3** format (magic header `ANDROID!`)
- Separate DTB loading is NOT supported — stock U-Boot crashes if DTB is passed separately
- `CONFIG_ARM_APPENDED_DTB=y` is required; DTB must be appended to zImage via `repack_boot.py`
- U-Boot **ignores** the boot image header cmdline; DTS `bootargs` are authoritative

## eMMC Layout (relevant partitions)

| Partition | Label   | Notes                        |
|-----------|---------|------------------------------|
| mmcblk0p3 | env_a   | U-Boot environment           |
| mmcblk0p5 | boot_a  | Active boot image            |
| mmcblk0p6 | boot_b  | Fallback boot image          |

### env_a format
- CRC32 covers `data[4:0x20000]`
- Key variable: `bootcmd=usb start;run setargs_nand boot_normal`

## Boot Sequence

1. U-Boot runs `usb start` (required for USB PHY init before kernel)
2. U-Boot loads MIPS display firmware (`display.bin`) to `0x4b100000` **before** kernel
3. Kernel boots in ARM32 mode with appended DTB

## Kernel Boot Arguments

Key `bootargs` entries (set in DTS, not boot image header):

```
panic=5         # auto-reboot on kernel panic after 5 seconds
rootwait        # wait for USB stick rootfs to appear
```

## Watchdog

- Address: `0x02051000` (`sun6i-a31-wdt` register layout)
- **Not** at H6 address `0x030090a0` — do not copy H6 DTS verbatim
- R_WDOG (backup): `0x07020400`

## Repack Requirement

**NEVER inline-repack boot images.** Always use `repack_boot.py` which appends the DTB to zImage before packing the Android Boot v3 image.
