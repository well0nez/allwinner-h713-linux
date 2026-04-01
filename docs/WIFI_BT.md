# HY310 WiFi / Bluetooth Subsystem

## Status: WORKING (WiFi stable, BT manual attach works; BT autostart has cold-boot baud issue)

## WiFi Hardware

- **Chip**: AIC8800D80 (SDIO)
  - VID: `0xC8A1`, DID: `0x0082`
- **MMC controller**: `0x04021000` (MMC1)
- **Pin mux**: PG0–PG5
- **Power**: PM1 (`wlan_regon`) via R_PIO

## Key Driver Patches

### R_PIO Fix
- **NEW_REG_LAYOUT**: register spacing is `0x30`, not `0x24` — this was a critical bug that prevented WiFi power-on

### sunxi-mmc.c Patches
- v5p3x DMA reset sequence
- NTSR stock delays preserved
- Clock doubling enabled
- `no_wait_pre_over` flag
- IDMA chunking
- DMA / FIFO / IDMA 3-step reset
- CMD53 retry with phase rotation

## WiFi Driver

- **Out-of-tree**: `aic8800-v5-ported`
- **Modules**: `bsp`, `fdrv`, `btlpm`
- **Firmware**: stock firmware (Dec 2024) in `/lib/firmware/aic8800D80/`
- **Performance**: stable, 10 MB+ transfers, ~1 MB/s, no errors

## Bluetooth

- **Interface**: UART1 (`ttyS1`), 1500000 baud, H4 protocol
- **Manual attach**: `hciattach /dev/ttyS1 any 1500000 flow` works correctly
- **Autostart issue**: cold boot baud rate mismatch — `hciattach` fails on first boot, requires manual intervention or a retry loop in the init script

## Next Steps

1. Fix BT autostart: add baud-rate negotiation retry or a cold-boot delay in the init script
2. Verify `btlpm` low-power management behavior on suspend/resume
