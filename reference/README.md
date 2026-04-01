# Reference Material

This directory contains extracted stock firmware analysis data. These files
are not part of the build — they serve as hardware reference for development.

## Files

- `stock_dts/hy310-board.dts` — Decompiled stock Android device tree (primary HW reference)
- `kallsyms.txt` — Stock kernel symbol table (130k symbols, invaluable for RE)
- `emmc_partition_map.txt` — eMMC partition layout with offsets and sizes
- `stock_gpio_map.txt` — GPIO pin assignments, I2C devices, reserved memory layout

## How these were obtained

- Stock DTS: extracted from `boot.fex` via `dtc -I dtb -O dts`
- kallsyms: extracted from `vmlinux.fex` via `/proc/kallsyms` format parser
- GPIO/partition data: extracted from running stock Android via ADB + /proc + /sys

## Stock firmware version

The HY310 runs a modified Android TV based on Allwinner H713 SDK V1.3.
Stock kernel: Linux 5.4.99 ARM32.
