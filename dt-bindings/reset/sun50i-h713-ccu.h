/* SPDX-License-Identifier: (GPL-2.0-only OR MIT) */
/*
 * Copyright (c) 2024 Project HY310
 *
 * Allwinner H713 CCU reset IDs
 * Extracted from stock kernel (sun50iw12p1) via binary analysis
 */

#ifndef _DT_BINDINGS_RST_SUN50I_H713_CCU_H_
#define _DT_BINDINGS_RST_SUN50I_H713_CCU_H_

#define RST_MBUS		0
#define RST_BUS_MIPS		1
#define RST_BUS_MIPS_DBG	2
#define RST_BUS_MIPS_CFG	3
#define RST_BUS_GPU		4
#define RST_BUS_CE		5
#define RST_BUS_CE_SYS		6
#define RST_BUS_VE		7
#define RST_BUS_AV1		8
#define RST_BUS_VE3		9
#define RST_BUS_DMA		10
#define RST_BUS_MSGBOX		11
#define RST_BUS_SPINLOCK	12
#define RST_BUS_TIMER0		13
#define RST_BUS_DBG		14
#define RST_BUS_PWM		15
#define RST_BUS_DRAM		16
#define RST_BUS_NAND		17
#define RST_BUS_NAND_SYS	18
#define RST_BUS_MMC0		19
#define RST_BUS_MMC1		20
#define RST_BUS_MMC2		21
#define RST_BUS_UART0		22
#define RST_BUS_UART1		23
#define RST_BUS_UART2		24
#define RST_BUS_UART3		25
#define RST_BUS_UART4		26
#define RST_BUS_TWI0		27
#define RST_BUS_TWI1		28
#define RST_BUS_TWI2		29
#define RST_BUS_TWI3		30
#define RST_BUS_SPI0		31
#define RST_BUS_SPI1		32
#define RST_BUS_EMAC		33
#define RST_BUS_GPADC		34
#define RST_BUS_THS		35
#define RST_BUS_I2S0		36
#define RST_BUS_I2S1		37
#define RST_BUS_I2S2		38
#define RST_BUS_OWA0		39
#define RST_BUS_OWA1		40
#define RST_BUS_AUDIO_HUB	41
#define RST_BUS_AUDIO_CODEC	42
#define RST_USB_PHY0		43
#define RST_USB_PHY1		44
#define RST_USB_PHY2		45
#define RST_BUS_OHCI0		46
#define RST_BUS_OHCI1		47
#define RST_BUS_OHCI2		48
#define RST_BUS_EHCI0		49
#define RST_BUS_EHCI1		50
#define RST_BUS_EHCI2		51
#define RST_BUS_OTG0		52
#define RST_BUS_LRADC		53
#define RST_BUS_TVE_TOP		54
#define RST_BUS_DEMOD		55
#define RST_BUS_TVCAP		56
#define RST_BUS_DISP		57

/* HDMI / TCON resets */
#define RST_BUS_TCON_TOP	58
#define RST_BUS_TCON_TV0	59
#define RST_BUS_HDMI		60
#define RST_BUS_HDMI_SUB	61
#define RST_BUS_HDCP		62

#define RST_NUMBER		63

#endif /* _DT_BINDINGS_RST_SUN50I_H713_CCU_H_ */
