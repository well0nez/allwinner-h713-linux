# Debug and Analysis Tools

## uboot_interrupt.py

U-Boot recovery tool. Connects to HY310 UART via OrangePi TCP bridge
(192.168.8.179:9999) and sends rapid keypresses to interrupt the 5-second
bootdelay.

```bash
python3 tools/uboot_interrupt.py --boot-usb   # Boot from USB stick
python3 tools/uboot_interrupt.py --cmd "..."   # Custom U-Boot command
python3 tools/uboot_interrupt.py --monitor     # Watch UART output only
```

## uart_bridge.py

UART-TCP bridge daemon for the OrangePi. Exposes /dev/ttyS3 (HY310 serial
console) as a TCP socket on port 9999. Supports multiple concurrent clients,
64KB ring buffer, bidirectional communication.

Deploy to OrangePi:
```bash
scp tools/uart_bridge.py user@192.168.8.179:/home/user/
ssh user@192.168.8.179 "setsid python3 /home/user/uart_bridge.py &"
```

## dump_mips_elog.py

Reads the MIPS co-processor error log from shared memory. The elog is a
ring buffer at physical address 0x4B272D9C (100KB), Mode 1.

```bash
ssh root@192.168.8.141 "python3 /tmp/dump_elog.py"
```

## probe_msgbox.py

Probes the H713 Msgbox hardware registers (3 User Pages at 0x03003000).
Dumps IRQ enable/status, FIFO count/data for all ports.

## patch_env.py (in scripts/)

Patches the U-Boot env_a partition (mmcblk0p3) with correct CRC32 checksum.
Used for first-time setup to add `usb start` to bootcmd.
