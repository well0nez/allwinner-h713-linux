obj-$(CONFIG_HY310_CPU_COMM) += hy310-cpu-comm.o
hy310-cpu-comm-objs := cpu_comm_dev.o cpu_comm_mem.o cpu_comm_hw.o cpu_comm_proto.o cpu_comm_fifo.o cpu_comm_channel.o cpu_comm_rpc.o
ccflags-y := -DCONFIG_ARM_CPU_COMM
++ b/drivers/soc/sunxi/Kconfig	2026-03-22 04:38:01.635768882 +0100
 	  Say y here to enable the SRAM controller support. This
 	  device is responsible on mapping the SRAM in the sunXi SoCs
 	  whether to the CPU/DMA, or to the devices.

source "drivers/soc/sunxi/cpu_comm/Kconfig"
++ b/drivers/soc/sunxi/Makefile	2026-03-22 04:37:46.631971202 +0100
 # SPDX-License-Identifier: GPL-2.0-only
 obj-$(CONFIG_SUNXI_MBUS) +=	sunxi_mbus.o
 obj-$(CONFIG_SUNXI_SRAM) +=	sunxi_sram.o
obj-$(CONFIG_HY310_CPU_COMM) += cpu_comm/
