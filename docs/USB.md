# HY310 USB Subsystem

## Status: WORKING

## Controllers

- 3x EHCI controllers
- 3x OHCI controllers

## USB PHY

- Driver: `phy-sun4i-usb`
- **H713 quirk**: `pmu_enable_bit0` — BIT(0) at the PMU base address must be set, or the PHY will not initialize correctly

## Boot Requirement

U-Boot must execute `usb start` **before** handing off to the kernel. The USB PHY initialization performed by U-Boot is required; the kernel does not re-initialize the PHY from scratch.

This is encoded in the U-Boot environment:
```
bootcmd=usb start;run setargs_nand boot_normal
```

## Network Access

- **USB-Ethernet adapter**: RTL8153
- **IP**: `192.168.8.141`
- Primary SSH access method during development
