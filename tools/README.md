# Debug and Analysis Tools

## uboot_interrupt.py

U-Boot recovery tool. Connects to HY310 UART via OrangePi TCP bridge
(192.168.8.179:9999) and sends rapid keypresses to interrupt the 5-second
bootdelay.

```bash
python3 tools/uboot_interrupt.py --boot-usb   # Boot from USB stick (rescue)
python3 tools/uboot_interrupt.py --restore     # Restore boot_a from boot_b
python3 tools/uboot_interrupt.py --cmd "..."   # Custom U-Boot command
python3 tools/uboot_interrupt.py --monitor     # Watch UART output only
python3 tools/uboot_interrupt.py               # Drop to U-Boot prompt
```

## dump_mips_elog.py

Reads the MIPS co-processor error log from shared memory. The elog is a
ring buffer at physical address 0x4B272D9C (100KB), Mode 1 (ring buffer).

```bash
# Run on HY310 target:
python3 dump_mips_elog.py
```

## verify_bootimg.py

Validates an Android Boot v3 image: checks ANDROID! magic, header fields,
kernel/ramdisk offsets, and page alignment.

```bash
python3 tools/verify_bootimg.py output/hy310-mainline-arm32-boot.img
```

## compare_dtb.py

Compares two DTB files by decompiling both and diffing the DTS output.
Useful for verifying that a rebuilt DTB matches the production DTB.

```bash
python3 tools/compare_dtb.py old.dtb new.dtb
```

## analyze_env.py

Analyzes and dumps U-Boot env_a partition content. Parses the CRC32 header,
shows all environment variables, and validates checksum integrity.

```bash
python3 tools/analyze_env.py /path/to/env_a.bin
```

## patch_env_usb.py

Patches the U-Boot env_a partition to add `usb start` to bootcmd.
See also: https://github.com/well0nez/sunxi-env-patcher
Handles the CRC32 checksum correctly. See [FLASHING.md](../FLASHING.md).

```bash
python3 tools/patch_env_usb.py
```

## probe_wdt.py

Probes watchdog registers via /dev/mem. Used to discover that the H713
watchdog is at 0x02051000 (NOT the H6 address 0x030090a0).

```bash
# Run on HY310 target:
python3 probe_wdt.py
```

## read_rpio.py

Reads R_PIO (PL/PM bank) register values via /dev/mem. Useful for debugging
GPIO pin function and pull-up configuration on the H713 R_PIO controller
(0x30 byte bank spacing, NOT 0x24).

```bash
# Run on HY310 target:
python3 read_rpio.py
```
