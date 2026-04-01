# HY310 eMMC Subsystem

## Status: WORKING

## Hardware

- **Controller**: `sunxi-mmc`, compatible `"allwinner,sun50i-h713-mmc"`
- **Controller version**: v5.4.0 (`sunxi-mmc-v5p3x`)
- **Device**: 7.3 GB Samsung eMMC
- **Mode**: DDR High-Speed @ 100 MHz

## Partition Table

- 26 partitions total

| Partition   | Label  | Use                    |
|-------------|--------|------------------------|
| mmcblk0p3   | env_a  | U-Boot environment     |
| mmcblk0p5   | boot_a | Active boot image      |
| mmcblk0p6   | boot_b | Fallback boot image    |

## Key Patches Applied to sunxi-mmc.c

| Patch                        | Notes                                              |
|------------------------------|----------------------------------------------------|
| `no_wait_pre_over` flag      | Required for v5p3x stability                       |
| IDMA chunking                | Prevents transfer errors on large blocks           |
| DMA / FIFO / IDMA 3-step reset | Correct reset sequence for v5p3x                |
| CMD53 retry with phase rotation | Fixes intermittent CMD53 failures              |
| Clock doubling               | Required to reach 100 MHz DDR                      |
| NTSR stock delays            | Preserves stock timing margins                     |

## Development Note

A debug `printk` in `mmc/core/core.c` was used during bringup to trace MMC initialization. This printk is **not** included in the upstream patch set — it was debug-only and must not be added to production builds.
