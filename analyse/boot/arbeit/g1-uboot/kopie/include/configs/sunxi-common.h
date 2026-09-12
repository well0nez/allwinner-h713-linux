/* SPDX-License-Identifier: GPL-2.0+ */
/*
 * (C) Copyright 2012-2012 Henrik Nordstrom <henrik@henriknordstrom.net>
 *
 * (C) Copyright 2007-2011
 * Allwinner Technology Co., Ltd. <www.allwinnertech.com>
 * Tom Cubie <tangliang@allwinnertech.com>
 *
 * Configuration settings for the Allwinner sunxi series of boards.
 */

#ifndef _SUNXI_COMMON_CONFIG_H
#define _SUNXI_COMMON_CONFIG_H

#include <linux/stringify.h>

/****************************************************************************
 *                  base addresses for the SPL UART driver                  *
 ****************************************************************************/
#ifdef CONFIG_MACH_SUNIV
/* suniv doesn't have apb2 and uart is connected to apb1 */
#define CFG_SYS_NS16550_CLK		100000000
#else
#define CFG_SYS_NS16550_CLK		24000000
#endif
#if !CONFIG_IS_ENABLED(DM_SERIAL)
#include <asm/arch/serial.h>
# define CFG_SYS_NS16550_COM1		SUNXI_UART0_BASE
# define CFG_SYS_NS16550_COM2		SUNXI_UART1_BASE
# define CFG_SYS_NS16550_COM3		SUNXI_UART2_BASE
# define CFG_SYS_NS16550_COM4		SUNXI_UART3_BASE
# define CFG_SYS_NS16550_COM5		SUNXI_R_UART_BASE
#endif

/****************************************************************************
 *                             DRAM base address                            *
 ****************************************************************************/
/*
 * The DRAM Base differs between some models. We cannot use macros for the
 * CONFIG_FOO defines which contain the DRAM base address since they end
 * up unexpanded in include/autoconf.mk .
 *
 * So we have to have this #ifdef #else #endif block for these.
 */
#ifdef CONFIG_MACH_SUN9I
#define SDRAM_OFFSET(x) 0x2##x
#define CFG_SYS_SDRAM_BASE		0x20000000
#elif defined(CONFIG_MACH_SUNIV)
#define SDRAM_OFFSET(x) 0x8##x
#define CFG_SYS_SDRAM_BASE		0x80000000
#else
#define SDRAM_OFFSET(x) 0x4##x
#define CFG_SYS_SDRAM_BASE		0x40000000
/* V3s do not have enough memory to place code at 0x4a000000 */
#endif

#define CFG_SYS_INIT_RAM_ADDR	CONFIG_SUNXI_SRAM_ADDRESS
/* FIXME: this may be larger on some SoCs */
#define CFG_SYS_INIT_RAM_SIZE	0x8000 /* 32 KiB */

#define PHYS_SDRAM_0			CFG_SYS_SDRAM_BASE
#define PHYS_SDRAM_0_SIZE		0x80000000 /* 2 GiB */

/****************************************************************************
 *           environment variables holding default load addresses           *
 ****************************************************************************/
/*
 * We cannot use expressions here, because expressions won't be evaluated in
 * autoconf.mk.
 */
#ifdef CONFIG_ARM64
/*
 * Boards seem to come with at least 512MB of DRAM.
 * The kernel should go at 512K, which is the default text offset (that will
 * be adjusted at runtime if needed).
 * There is no compression for arm64 kernels (yet), so leave some space
 * for really big kernels, say 256MB for now.
 * Scripts, PXE and DTBs should go afterwards, leaving the rest for the initrd.
 */
#define BOOTM_SIZE        __stringify(0xa000000)
#define KERNEL_ADDR_R     __stringify(SDRAM_OFFSET(0080000))
#define KERNEL_COMP_ADDR_R __stringify(SDRAM_OFFSET(4000000))
#define KERNEL_COMP_SIZE  __stringify(0xb000000)
#define FDT_ADDR_R        __stringify(SDRAM_OFFSET(FA00000))
#define SCRIPT_ADDR_R     __stringify(SDRAM_OFFSET(FC00000))
#define PXEFILE_ADDR_R    __stringify(SDRAM_OFFSET(FD00000))
#define FDTOVERLAY_ADDR_R __stringify(SDRAM_OFFSET(FE00000))
#define RAMDISK_ADDR_R    __stringify(SDRAM_OFFSET(FF00000))

#elif (CONFIG_SUNXI_MINIMUM_DRAM_MB >= 256)
/*
 * 160M RAM (256M minimum minus 64MB heap + 32MB for u-boot, stack, fb, etc.
 * 32M uncompressed kernel, 16M compressed kernel, 1M fdt,
 * 1M script, 1M pxe, 1M dt overlay and the ramdisk at the end.
 */
#define BOOTM_SIZE        __stringify(0xa000000)
#define KERNEL_ADDR_R     __stringify(SDRAM_OFFSET(2000000))
#define FDT_ADDR_R        __stringify(SDRAM_OFFSET(3000000))
#define SCRIPT_ADDR_R     __stringify(SDRAM_OFFSET(3100000))
#define PXEFILE_ADDR_R    __stringify(SDRAM_OFFSET(3200000))
#define FDTOVERLAY_ADDR_R __stringify(SDRAM_OFFSET(3300000))
#define RAMDISK_ADDR_R    __stringify(SDRAM_OFFSET(3400000))

#elif (CONFIG_SUNXI_MINIMUM_DRAM_MB >= 64)
/*
 * 64M RAM minus 2MB heap + 16MB for u-boot, stack, fb, etc.
 * 16M uncompressed kernel, 8M compressed kernel, 1M fdt,
 * 1M script, 1M pxe, 1M dt overlay and the ramdisk at the end.
 */
#define BOOTM_SIZE        __stringify(0x2e00000)
#define KERNEL_ADDR_R     __stringify(SDRAM_OFFSET(1000000))
#define FDT_ADDR_R        __stringify(SDRAM_OFFSET(1800000))
#define SCRIPT_ADDR_R     __stringify(SDRAM_OFFSET(1900000))
#define PXEFILE_ADDR_R    __stringify(SDRAM_OFFSET(1A00000))
#define FDTOVERLAY_ADDR_R __stringify(SDRAM_OFFSET(1B00000))
#define RAMDISK_ADDR_R    __stringify(SDRAM_OFFSET(1C00000))

#elif (CONFIG_SUNXI_MINIMUM_DRAM_MB >= 32)
/*
 * 32M RAM minus 2.5MB for u-boot, heap, stack, etc.
 * 16M uncompressed kernel, 7M compressed kernel, 128K fdt, 64K script,
 * 128K DT overlay, 128K PXE and the ramdisk in the rest (max. 5MB)
 */
#define BOOTM_SIZE        __stringify(0x1700000)
#define KERNEL_ADDR_R     __stringify(SDRAM_OFFSET(1000000))
#define FDT_ADDR_R        __stringify(SDRAM_OFFSET(1d50000))
#define SCRIPT_ADDR_R     __stringify(SDRAM_OFFSET(1d40000))
#define PXEFILE_ADDR_R    __stringify(SDRAM_OFFSET(1d00000))
#define FDTOVERLAY_ADDR_R __stringify(SDRAM_OFFSET(1d20000))
#define RAMDISK_ADDR_R    __stringify(SDRAM_OFFSET(1800000))

#else
#error Need at least 32MB of DRAM. Please adjust load addresses.
#endif

#define MEM_LAYOUT_ENV_SETTINGS \
	"bootm_size=" BOOTM_SIZE "\0" \
	"kernel_addr_r=" KERNEL_ADDR_R "\0" \
	"fdt_addr_r=" FDT_ADDR_R "\0" \
	"scriptaddr=" SCRIPT_ADDR_R "\0" \
	"pxefile_addr_r=" PXEFILE_ADDR_R "\0" \
	"fdtoverlay_addr_r=" FDTOVERLAY_ADDR_R "\0" \
	"ramdisk_addr_r=" RAMDISK_ADDR_R "\0"

#ifdef CONFIG_ARM64
#define MEM_LAYOUT_ENV_EXTRA_SETTINGS \
	"kernel_comp_addr_r=" KERNEL_COMP_ADDR_R "\0" \
	"kernel_comp_size=" KERNEL_COMP_SIZE "\0"
#else
#define MEM_LAYOUT_ENV_EXTRA_SETTINGS ""
#endif

#define DFU_ALT_INFO_RAM \
	"dfu_alt_info_ram=" \
	"kernel ram " KERNEL_ADDR_R " 0x1000000;" \
	"fdt ram " FDT_ADDR_R " 0x100000;" \
	"ramdisk ram " RAMDISK_ADDR_R " 0x4000000\0"

/****************************************************************************
 *                  definitions for the distro boot system                  *
 ****************************************************************************/
#ifdef CONFIG_MMC
#if CONFIG_MMC_SUNXI_SLOT_EXTRA != -1
#define BOOTENV_DEV_MMC_AUTO(devtypeu, devtypel, instance)		\
	BOOTENV_DEV_MMC(MMC, mmc, 0)					\
	BOOTENV_DEV_MMC(MMC, mmc, 1)					\
	"bootcmd_mmc_auto="						\
		"if test ${mmc_bootdev} -eq 1; then "			\
			"run bootcmd_mmc1; "				\
			"run bootcmd_mmc0; "				\
		"elif test ${mmc_bootdev} -eq 0; then "			\
			"run bootcmd_mmc0; "				\
			"run bootcmd_mmc1; "				\
		"fi\0"

#define BOOTENV_DEV_NAME_MMC_AUTO(devtypeu, devtypel, instance) \
	"mmc_auto "

#define BOOT_TARGET_DEVICES_MMC(func) func(MMC_AUTO, mmc_auto, na)
#else
#define BOOT_TARGET_DEVICES_MMC(func) func(MMC, mmc, 0)
#endif
#else
#define BOOT_TARGET_DEVICES_MMC(func)
#endif

#ifdef CONFIG_AHCI
#define BOOT_TARGET_DEVICES_SCSI(func) func(SCSI, scsi, 0)
#else
#define BOOT_TARGET_DEVICES_SCSI(func)
#endif

#ifdef CONFIG_USB_STORAGE
#define BOOT_TARGET_DEVICES_USB(func) func(USB, usb, 0)
#else
#define BOOT_TARGET_DEVICES_USB(func)
#endif

#ifdef CONFIG_CMD_PXE
#define BOOT_TARGET_DEVICES_PXE(func) func(PXE, pxe, na)
#else
#define BOOT_TARGET_DEVICES_PXE(func)
#endif

#ifdef CONFIG_CMD_DHCP
#define BOOT_TARGET_DEVICES_DHCP(func) func(DHCP, dhcp, na)
#else
#define BOOT_TARGET_DEVICES_DHCP(func)
#endif

/* FEL boot support, auto-execute boot.scr if a script address was provided */
#define BOOTENV_DEV_FEL(devtypeu, devtypel, instance) \
	"bootcmd_fel=" \
		"if test -n ${fel_booted} && test -n ${fel_scriptaddr}; then " \
			"echo '(FEL boot)'; " \
			"source ${fel_scriptaddr}; " \
		"fi\0"
#define BOOTENV_DEV_NAME_FEL(devtypeu, devtypel, instance) \
	"fel "

#define BOOT_TARGET_DEVICES(func) \
	func(FEL, fel, na) \
	BOOT_TARGET_DEVICES_MMC(func) \
	BOOT_TARGET_DEVICES_SCSI(func) \
	BOOT_TARGET_DEVICES_USB(func) \
	BOOT_TARGET_DEVICES_PXE(func) \
	BOOT_TARGET_DEVICES_DHCP(func)

#ifdef CONFIG_OLD_SUNXI_KERNEL_COMPAT
#define BOOTCMD_SUNXI_COMPAT \
	"bootcmd_sunxi_compat=" \
		"setenv root /dev/mmcblk0p3 rootwait; " \
		"if ext2load mmc 0 0x44000000 uEnv.txt; then " \
			"echo Loaded environment from uEnv.txt; " \
			"env import -t 0x44000000 ${filesize}; " \
		"fi; " \
		"setenv bootargs console=${console} root=${root} ${extraargs}; " \
		"ext2load mmc 0 0x43000000 script.bin && " \
		"ext2load mmc 0 0x48000000 uImage && " \
		"bootm 0x48000000\0"
#else
#define BOOTCMD_SUNXI_COMPAT
#endif

#include <config_distro_bootcmd.h>

/*
 * H713 has one USB device controller.  Keep the recovery-safe serial console
 * as the default and switch the controller explicitly between ACM and
 * download gadgets; multiplexing ACM into the default stdin can prevent UART
 * from interrupting autoboot when the USB side is stale after a gadget reset.
 */
#if defined(CONFIG_MACH_SUN50I_H713)
#define CONSOLE_STDIN_SETTINGS \
	"stdin=serial\0"
#elif defined(CONFIG_USB_KEYBOARD)
#define CONSOLE_STDIN_SETTINGS \
	"stdin=serial,usbkbd\0"
#else
#define CONSOLE_STDIN_SETTINGS \
	"stdin=serial\0"
#endif

#ifdef CONFIG_VIDEO
#define CONSOLE_STDOUT_SETTINGS \
	"stdout=serial,vidconsole\0" \
	"stderr=serial,vidconsole\0"
#else
#define CONSOLE_STDOUT_SETTINGS \
	"stdout=serial\0" \
	"stderr=serial\0"
#endif

#define PARTS_DEFAULT \
	"name=loader1,start=8k,size=32k,uuid=${uuid_gpt_loader1};" \
	"name=loader2,size=984k,uuid=${uuid_gpt_loader2};" \
	"name=esp,size=128M,bootable,uuid=${uuid_gpt_esp};" \
	"name=system,size=-,uuid=${uuid_gpt_system};"

#define UUID_GPT_ESP "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"

#ifdef CONFIG_ARM64
#define UUID_GPT_SYSTEM "b921b045-1df0-41c3-af44-4c6f280d3fae"
#else
#define UUID_GPT_SYSTEM "69dad710-2ce4-4e3c-b16c-21a1d49abed3"
#endif

#define CONSOLE_ENV_SETTINGS \
	CONSOLE_STDIN_SETTINGS \
	CONSOLE_STDOUT_SETTINGS

/*
 * H713 boots the eMMC user area from LBA 16.  Give fastboot a bounded raw
 * target for the active SPL/U-Boot image.  The range ends immediately before
 * the persistent environment at LBA 0x2000 (4 MiB).
 *
 * Use the unambiguous name "bootloader": the factory GPT already contains a
 * different partition named "bootloader_a" starting at 36 MiB.
 */
#if defined(CONFIG_MACH_SUN50I_H713) && \
	defined(CONFIG_USB_FUNCTION_ACM) && \
	defined(CONFIG_USB_FUNCTION_FASTBOOT)
#define H713_SERIAL_COMMAND \
	"setenv stdin serial; setenv stdout serial; setenv stderr serial"
#define H713_ACM_COMMAND \
	"setenv stdin serial,usbacm; setenv stdout serial,usbacm; " \
	"setenv stderr serial,usbacm"
#define H713_FASTBOOT_COMMAND \
	"run serial_mode; fastboot usb 0; run serial_mode"
#define H713_FASTBOOT_MODE_ENV_SETTINGS \
	"serial_mode=" H713_SERIAL_COMMAND "\0" \
	"acm_mode=" H713_ACM_COMMAND "\0" \
	"fastboot_mode=" H713_FASTBOOT_COMMAND "\0"
#else
#define H713_SERIAL_COMMAND ""
#define H713_ACM_COMMAND ""
#define H713_FASTBOOT_COMMAND ""
#define H713_FASTBOOT_MODE_ENV_SETTINGS
#endif

#ifdef CONFIG_MACH_SUN50I_H713
/*
 * Switch to the vendor stack with one command, no host attached: copy the
 * vendor's boot0 from LBA 0x100 -- the second copy the vendor itself keeps at
 * 128 KiB, restored there by tools/boot-switch.sh stage -- over the first stage
 * at LBA 0x10, then power cycle.  Both boot chains are then complete and
 * resident: ours is SPL(0x10) + U-Boot proper(0x12000) + FIT(boot_a) + UDISK,
 * the vendor's is boot0(0x100) + its TOC1 boot package(24576/32800, which is
 * where its U-Boot, BL31 and OP-TEE live) + its slot-B Android images.
 *
 * Every step is chained with && and the copy is checked for the eGON magic
 * before it is written, so a failed read cannot go on to install whatever DRAM
 * happened to hold -- the failure that has already produced one worthless
 * "backup" on this board.  There is no switch_ours counterpart here: once the
 * vendor owns LBA 0x10 this environment is not running.  See docs/flash.md for
 * the two ways back (the FEL button, or the stashed SPL at LBA 0x14000).
 */
#define H713_SWITCH_VENDOR_COMMAND \
	"mmc dev 1 && mmc read 0x48000000 0x100 0x40 && " \
	"itest.l *0x48000004 == 0x4e4f4765 && " \
	"mmc write 0x48000000 0x10 0x40 && " \
	"echo VENDOR FIRST STAGE INSTALLED - POWER CYCLE TO BOOT IT"
/*
 * The one-shot form: arm the RTC marker the SPL consumes and reset.  Ours
 * stays installed at LBA 0x10, so the next boot after the vendor excursion is
 * ours again with nothing to undo, and a vendor chain that hangs costs a power
 * cycle rather than the FEL button.  Prefer this over switch_vendor, which
 * makes the vendor the persistent default until something rewrites LBA 0x10.
 */
#define H713_BOOT_VENDOR_COMMAND \
	"mw.l 0x0709011c 0x001db007 && reset"
#define H713_SWITCH_ENV_SETTINGS \
	"boot_vendor=" H713_BOOT_VENDOR_COMMAND "\0" \
	"switch_vendor=" H713_SWITCH_VENDOR_COMMAND "\0"

/*
 * The BROM-loaded first stage is a single raw image at LBA 0x10 (not slotted).
 * Provide it under a non-slotted alias "uboot" as well as "bootloader":
 * slot-aware fastboot hosts auto-append the A/B suffix to "bootloader" and end
 * up writing the unused 36 MiB GPT partition "bootloader_a" instead of LBA 0x10.
 * "uboot" is not a GPT partition name, so the host passes it through verbatim.
 *
 * LBA 0x10 holds *only* the 32 KiB first stage, because those 64 sectors are
 * the one range this board's two boot chains contend for: either our SPL or
 * the vendor's boot0 lives there, and swapping them is how you switch stacks.
 * U-Boot proper therefore lives in the "empty" partition (LBA 0x49ac00): not
 * at LBA 0x50, which is inside the region the vendor's boot0 reads, and no
 * longer in "bootloader_a" either -- that one looked like OTA staging but is
 * really a live FAT16 holding the vendor's mips/ display artifacts, and our
 * image over its boot sector left the vendor unable to mount it
 * ("** Unrecognized filesystem type **", bench 2026-08-06).  "empty" is 15 MiB
 * of zeros in the factory image and is named in nothing the vendor boots.  The size
 * guards below are deliberately tight so that flashing the concatenated
 * u-boot-sunxi-with-spl-*.bin to "uboot" fails loudly instead of quietly
 * recreating the old overlapping layout.  Flash the two halves with:
 *   fastboot flash uboot  <first 32 KiB of u-boot-sunxi-with-spl-*.bin>
 *   fastboot flash ubootp <the remainder>
 * or let tools/boot-switch.sh split them for you.
 */
#define H713_FASTBOOT_ENV_SETTINGS \
	"fastboot_raw_partition_bootloader=0x10 0x40\0" \
	"fastboot_raw_partition_uboot=0x10 0x40\0" \
	"fastboot_raw_partition_ubootp=0x49ac00 0x2000\0" \
	"fastboot_raw_partition_vboot0=0x100 0x40\0" \
	"fastboot_raw_partition_splstash=0x49cc00 0x40\0" \
	H713_SWITCH_ENV_SETTINGS \
	H713_FASTBOOT_MODE_ENV_SETTINGS
#else
#define H713_SWITCH_VENDOR_COMMAND ""
#define H713_FASTBOOT_ENV_SETTINGS
#endif

#if defined(CONFIG_ARM64) || defined(CONFIG_RISCV)
#define FDTFILE "allwinner/" CONFIG_DEFAULT_DEVICE_TREE ".dtb"
#else
#define FDTFILE CONFIG_DEFAULT_DEVICE_TREE ".dtb"
#endif

#define CFG_EXTRA_ENV_SETTINGS \
	CONSOLE_ENV_SETTINGS \
	MEM_LAYOUT_ENV_SETTINGS \
	MEM_LAYOUT_ENV_EXTRA_SETTINGS \
	DFU_ALT_INFO_RAM \
	"fdtfile=" FDTFILE "\0" \
	"console=ttyS0,115200\0" \
	"uuid_gpt_esp=" UUID_GPT_ESP "\0" \
	"uuid_gpt_system=" UUID_GPT_SYSTEM "\0" \
	"partitions=" PARTS_DEFAULT "\0" \
	H713_FASTBOOT_ENV_SETTINGS \
	BOOTCMD_SUNXI_COMPAT \
	BOOTENV

#endif /* _SUNXI_COMMON_CONFIG_H */
