/*
 * Copyright (c) 2026, Arm Limited and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <plat/common/platform.h>

#include <sunxi_cpucfg_ncat.h>

/*
 * The H713 uses the per-core (non-per-cluster) cpu_on path. With the ncat
 * register file this drives exactly the stock BL31 sequence: per-core
 * reset at C0_CPU_CTRL (0x09010060 + n*4), AArch64/enable at CPU_CTRL
 * (0x08100020 + n*4), power-on reset at CPU_UNK (0x07000470 + n*4), power
 * clamp at 0x07000450 + n*4, and RVBAR at ALT_RVBAR (0x08100040 + n*8).
 */
static inline bool sunxi_cpucfg_has_per_cluster_regs(void)
{
	return false;
}
