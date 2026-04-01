# AIC8800D80 WiFi/BT Driver for HY310

## Overview

Out-of-tree driver for the AIC8800D80 SDIO WiFi + Bluetooth chip found on
the HY310 projector board. Based on the aic8800-v5 port from the AIC vendor SDK,
adapted for mainline kernel 6.16.7.

## Modules

| Module | Description |
|--------|-------------|
| aic8800_bsp | Board support package (SDIO init, firmware upload, power control) |
| aic8800_fdrv | Full MAC driver (creates wlan interface) |
| aic8800_btlpm | Bluetooth low-power management + rfkill |

## Prerequisites

1. Kernel patched with sunxi-mmc H713 v5p3x support (patch 0006)
2. AIC8800D80 firmware in `/lib/firmware/aic8800D80/` (from stock Android)
3. R_PIO pinctrl with NEW_REG_LAYOUT (patch 0003)

## Loading WiFi

```bash
modprobe aic8800_bsp
modprobe aic8800_fdrv
# wlan0 (or wlan1) interface appears

# Connect to WiFi
wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
dhclient wlan0
```

## Loading Bluetooth

```bash
modprobe aic8800_btlpm
rfkill unblock bluetooth
hciattach /dev/ttyS1 any 1500000 flow
# hci0 interface appears

bluetoothctl
> scan on
```

## Systemd Service

```ini
# /etc/systemd/system/aic8800-wifi.service
[Unit]
Description=AIC8800 WiFi
After=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/modprobe aic8800_bsp
ExecStart=/sbin/modprobe aic8800_fdrv

[Install]
WantedBy=multi-user.target
```

## Known Issues

- BT autostart at 1500000 baud fails on cold boot (needs initial 115200)
- WiFi runs at High Speed 25MHz (SDR104@50MHz needs 1.8V signal voltage switching)
- Firmware must be from stock Android Dec 2024 or newer (older FW causes init timeout)
