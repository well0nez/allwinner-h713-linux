/*
 * Copyright (c) 2026, Arm Limited and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef SUNXI_MMAP_H
#define SUNXI_MMAP_H

/* Memory regions */
#define SUNXI_ROM_BASE			0x00000000
#define SUNXI_ROM_SIZE			0x00010000
#define SUNXI_SRAM_BASE			0x00100000
#define SUNXI_SRAM_SIZE			0x00024000
#define SUNXI_SRAM_A1_BASE		0x00100000
#define SUNXI_SRAM_A1_SIZE		0x00004000
#define SUNXI_SRAM_A2_BASE		0x00104000
#define SUNXI_SRAM_A2_SIZE		0x00020000
#define SUNXI_DEV_BASE			0x01000000
#define SUNXI_DEV_SIZE			0x09000000
#define SUNXI_DRAM_BASE			0x40000000
#define SUNXI_DRAM_VIRT_BASE		SUNXI_DRAM_BASE

/* Memory-mapped devices */
#define SUNXI_SYSCON_BASE		0x03000000
#define SUNXI_CCU_BASE			0x02001000
#define SUNXI_DMA_BASE			0x03002000
#define SUNXI_SID_BASE			0x03006000
#define SUNXI_SPC_BASE			0x03008000
#define SUNXI_WDOG_BASE			0x02051000
#define SUNXI_PIO_BASE			0x02000000
#define SUNXI_GICD_BASE			0x03021000
#define SUNXI_GICC_BASE			0x03022000
#define SUNXI_UART0_BASE		0x02500000
#define SUNXI_SPI0_BASE			0x04025000
#define SUNXI_R_CPUCFG_BASE		0x07000400
#define SUNXI_R_PRCM_BASE		0x07010000
#define SUNXI_R_WDOG_BASE		SUNXI_WDOG_BASE
/* sun50iw12 watchdog writes require the key in bits [31:16] */
#define SUNXI_WDOG_KEY			0x16aa0000
#define SUNXI_R_PIO_BASE		0x07022000
#define SUNXI_R_UART_BASE		0x07080000
#define SUNXI_R_I2C_BASE		0x07081400
#define SUNXI_R_RSB_BASE		0x07083000
/*
 * H713 uses the "ncat" register file with the non-per-cluster (else)
 * cpu_on path: per-core control regs at CPUCFG 0x09010060 + n*4, per-core
 * AArch64/enable at CPUSUBSYS 0x08100020 + n*4, RVBAR at 0x08100040 + n*8.
 * This matches the stock BL31 cpu_on sequence exactly.
 */
#define SUNXI_CPUSUBSYS_BASE		0x08100000
#define SUNXI_CPUCFG_BASE		0x09010000

#endif /* SUNXI_MMAP_H */
