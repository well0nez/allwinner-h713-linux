# Firmware Files

This directory intentionally does not contain firmware binaries.
Firmware files are not redistributable and must be obtained separately.

## Required Firmware

### AIC8800D80 WiFi/BT
- Source: Stock Android firmware (super.fex vendor partition) or AIC vendor SDK
- Install to: `/lib/firmware/aic8800D80/`
- Files: fw_patch_table_u03.bin, fw_adid_u03.bin, fw_patch_u03.bin, fmacfw.bin, etc.
- The Dec 2024 / Nov 2024 firmware versions from stock are confirmed working.

### MIPS Display Co-processor
- Source: Loaded by stock U-Boot from eMMC boot package (display.bin)
- Location: Reserved memory at 0x4B100000 (42MB)
- The kernel does NOT need to load this — U-Boot does it before handing off to Linux.
- The sunxi-mipsloader driver provides a /dev/mipsloader interface but firmware
  is already present in memory at boot time.
