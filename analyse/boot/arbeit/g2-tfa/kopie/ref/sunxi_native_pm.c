/*
 * Copyright (c) 2017-2021, ARM Limited and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <arch_helpers.h>
#include <common/debug.h>
#include <drivers/arm/gicv2.h>
#include <drivers/delay_timer.h>
#include <lib/mmio.h>
#include <lib/psci/psci.h>

#include <sunxi_mmap.h>
#include <sunxi_private.h>

#define SUNXI_WDOG0_CTRL_REG		(SUNXI_R_WDOG_BASE + 0x0010)
#define SUNXI_WDOG0_CFG_REG		(SUNXI_R_WDOG_BASE + 0x0014)
#define SUNXI_WDOG0_MODE_REG		(SUNXI_R_WDOG_BASE + 0x0018)

static int sunxi_pwr_domain_on(u_register_t mpidr)
{
	sunxi_cpu_on(mpidr);

	return PSCI_E_SUCCESS;
}

static void sunxi_pwr_domain_off(const psci_power_state_t *target_state)
{
	gicv2_cpuif_disable();

	sunxi_cpu_power_off_self();
}

static void sunxi_pwr_domain_on_finish(const psci_power_state_t *target_state)
{
	gicv2_pcpu_distif_init();
	gicv2_cpuif_enable();
}

static int sunxi_validate_power_state(unsigned int power_state,
				      psci_power_state_t *req_state)
{
	unsigned int power_level = psci_get_pstate_pwrlvl(power_state);
	unsigned int type = psci_get_pstate_type(power_state);
	unsigned int i;

	if (power_level > PLAT_MAX_PWR_LVL) {
		return PSCI_E_INVALID_PARAMS;
	}

	if (type == PSTATE_TYPE_STANDBY) {
		/* Only a CPU-level WFI retention state is supported. */
		if (power_level != MPIDR_AFFLVL0) {
			return PSCI_E_INVALID_PARAMS;
		}
		req_state->pwr_domain_state[MPIDR_AFFLVL0] =
			PLAT_MAX_RET_STATE;
	} else {
		/* Power down this level and everything below it. */
		for (i = MPIDR_AFFLVL0; i <= power_level; i++) {
			req_state->pwr_domain_state[i] = PLAT_MAX_OFF_STATE;
		}
	}

	return PSCI_E_SUCCESS;
}

static void sunxi_cpu_standby(plat_local_state_t cpu_state)
{
	/*
	 * WFI wakes on a pending physical interrupt regardless of the PSTATE
	 * mask, so no SCR_EL3 changes are needed here.
	 */
	dsb();
	wfi();
}

static void sunxi_pwr_domain_suspend(const psci_power_state_t *target_state)
{
	/* A CPU-level powerdown suspend is the same as turning the CPU off. */
	if (is_local_state_off(target_state->pwr_domain_state[MPIDR_AFFLVL0])) {
		gicv2_cpuif_disable();
		sunxi_cpu_power_off_self();
	}
}

static void sunxi_pwr_domain_suspend_finish(const psci_power_state_t *target_state)
{
	if (is_local_state_off(target_state->pwr_domain_state[MPIDR_AFFLVL0])) {
		gicv2_pcpu_distif_init();
		gicv2_cpuif_enable();
	}
}

static void sunxi_system_off(void)
{
	gicv2_cpuif_disable();

	/* Attempt to power down the board (may not return) */
	sunxi_power_down();

	/* Turn off all CPUs */
	sunxi_cpu_power_off_others();
	sunxi_cpu_power_off_self();
}

static void __dead2 sunxi_system_reset(void)
{
	gicv2_cpuif_disable();

#ifdef SUNXI_WDOG_KEY
	/*
	 * Key-protected watchdog layout (H713/sun50iw12): CFG at +0x10,
	 * MODE at +0x14, writes ignored without the 0x16aa key.
	 */
	/* Reset the whole system when the watchdog times out */
	mmio_write_32(SUNXI_R_WDOG_BASE + 0x0010, SUNXI_WDOG_KEY | 1);
	/* Enable the watchdog with the shortest timeout (0.5 seconds) */
	mmio_write_32(SUNXI_R_WDOG_BASE + 0x0014, SUNXI_WDOG_KEY | 1);
#else
	/* Reset the whole system when the watchdog times out */
	mmio_write_32(SUNXI_WDOG0_CFG_REG, 1);
	/* Enable the watchdog with the shortest timeout (0.5 seconds) */
	mmio_write_32(SUNXI_WDOG0_MODE_REG, (0 << 4) | 1);
#endif
	/* Wait for twice the watchdog timeout before panicking */
	mdelay(1000);

	ERROR("PSCI: System reset failed\n");
	panic();
}

static const plat_psci_ops_t sunxi_native_psci_ops = {
	.cpu_standby			= sunxi_cpu_standby,
	.pwr_domain_on			= sunxi_pwr_domain_on,
	.pwr_domain_off			= sunxi_pwr_domain_off,
	.pwr_domain_on_finish		= sunxi_pwr_domain_on_finish,
	.pwr_domain_suspend		= sunxi_pwr_domain_suspend,
	.pwr_domain_suspend_finish	= sunxi_pwr_domain_suspend_finish,
	.validate_power_state		= sunxi_validate_power_state,
	.system_off			= sunxi_system_off,
	.system_reset			= sunxi_system_reset,
	.validate_ns_entrypoint		= sunxi_validate_ns_entrypoint,
};

void sunxi_set_native_psci_ops(const plat_psci_ops_t **psci_ops)
{
	*psci_ops = &sunxi_native_psci_ops;
}
