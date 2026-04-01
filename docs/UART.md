# UART / Serial Console Access

## Overview

The HY310 has a serial console (UART0) exposed on the main board. Access to
this console is essential for:
- Interrupting U-Boot during boot (5-second window)
- Debugging kernel panics or boot failures
- Recovery when SSH is not available (broken kernel, no network)

## Serial Parameters

- **Baud rate:** 115200
- **Data bits:** 8
- **Parity:** None
- **Stop bits:** 1
- **Flow control:** None

## Hardware Connection

The UART pins are on the HY310 main board. You need a 3.3V USB-UART adapter
or another device (e.g., an OrangePi with exposed UART pins) to connect.

**WARNING:** Use 3.3V logic levels only. 5V will damage the SoC.

Connect:
- HY310 TX -> Adapter RX
- HY310 RX -> Adapter TX
- HY310 GND -> Adapter GND

## Using a USB-UART Adapter (Direct)

```bash
# Linux
screen /dev/ttyUSB0 115200

# or with minicom
minicom -D /dev/ttyUSB0 -b 115200

# macOS
screen /dev/tty.usbserial-* 115200

# Windows
# Use PuTTY or Tera Term, select COM port, 115200 8N1
```

## Using an OrangePi as UART Bridge (Our Setup)

In our development setup, an OrangePi acts as a network-to-UART bridge,
allowing UART access from any machine on the LAN via TCP:

```
Windows/Linux PC --TCP:9999--> OrangePi (/dev/ttyS3) --wire--> HY310 UART
```

Connect via TCP:
```python
import socket
s = socket.socket()
s.connect(("192.168.8.179", 9999))
s.sendall(b"uname -a\r")
import time; time.sleep(1)
print(s.recv(4096).decode())
s.close()
```

## Interrupting U-Boot

U-Boot waits 5 seconds before auto-booting. During this window, send any
keypress to drop to the U-Boot command prompt.

### Automated (via our tool)

```bash
python3 tools/uboot_interrupt.py
# Connects to UART bridge, sends rapid keypresses, drops to U-Boot prompt

python3 tools/uboot_interrupt.py --boot-usb
# Interrupts U-Boot AND issues USB boot commands automatically
```

### Manual

1. Open serial terminal (screen, minicom, PuTTY)
2. Power on or reboot the HY310
3. When you see "Hit any key to stop autoboot:", press any key rapidly
4. You get the `=>` U-Boot prompt

### U-Boot Commands for Recovery

```
# Boot from USB stick (rescue):
usb start
fatload usb 0:1 0x45000000 mboot32.00
fatload usb 0:1 0x45400000 mboot32.01
bootm 0x45000000

# Boot stock Android from boot_b:
sunxi_flash read 45000000 boot_b
bootm 45000000

# Check environment:
printenv bootcmd

# Read eMMC partition:
mmc dev 0
mmc read 0x45000000 0x32400 0x1
md.b 0x45000000 0x100
```

## Boot Log

A normal successful boot shows approximately:
```
U-Boot SPL ...
U-Boot 2018.05 (Allwinner H713) ...
Hit any key to stop autoboot: 5 4 3 2 1 0
...
Starting kernel ...
[    0.000000] Booting Linux on physical CPU 0x0
[    0.000000] Linux version 6.16.7 ...
[    1.234567] sun50i-h713-pinctrl 2000000.pinctrl: initialized sunXi PIO driver
...
```

If boot fails, the UART output is the primary diagnostic tool. Common failure
patterns:
- **"data abort"** after "Starting kernel" = boot image format problem
- **Kernel panic** with stack trace = driver bug or config issue (auto-reboots in 5s)
- **Hangs after "Starting kernel"** with no output = wrong DTB or early init crash
