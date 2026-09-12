/*
 * Copyright (c) 2026, Arm Limited and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * This board has no PMIC and no power hold, so the H616 sunxi_power_down()
 * finds "pmic == UNKNOWN" and returns without doing anything: PSCI SYSTEM_OFF
 * only parks the cores and leaves fan, backlight and USB VBUS running. Hand
 * the power-off wish to the boot loader instead: put "GATE" into the RTC
 * general-purpose register GP5 and reset the SoC. U-Boot's power gate reads
 * GP5 and waits for the power key rather than booting.
 *
 * The rest of the H616 PMIC code is still needed (sunxi_pmic_setup() and the
 * axp_read()/axp_write() the AXP driver links against), so the file is still
 * included; only its sunxi_power_down() is renamed out of the way. Our
 * version therefore runs ahead of the "pmic == UNKNOWN" early return, which
 * on this board is always taken.
 */

#include <drivers/delay_timer.h>

#define sunxi_power_down	sunxi_pmic_power_down
#include "../sun50i_h616/sunxi_power.c"
#undef sunxi_power_down

/*
 * RTC GP registers live at RTC base + 0x100 (8 words). GP5 is free on this
 * board: GP7 is U-Boot's fastboot marker, GP2/GP3/GP6 are used by the vendor
 * firmware. A GP word survives a warm reset and is cleared when the board
 * loses mains power, which is what makes it a usable power-state flag.
 */
#define H713_RTC_BASE			0x07090000
#define H713_RTC_GP_REG(n)		(H713_RTC_BASE + 0x0100 + 4 * (n))
#define H713_GATE_FLAG_REG		H713_RTC_GP_REG(5)
#define H713_GATE_FLAG_VALUE		0x47415445	/* "GATE" */

/*
 * Same watchdog sequence as sunxi_system_reset() in
 * plat/allwinner/common/sunxi_native_pm.c, which is static there and cannot
 * be called. sun50iw12 layout: CFG at +0x10, MODE at +0x14, both ignored
 * without the key in bits [31:16]; MODE bits [7:4] are the interval, 0 being
 * the shortest one (0.5 s).
 */
#define H713_WDOG_CFG_REG		(SUNXI_R_WDOG_BASE + 0x0010)
#define H713_WDOG_MODE_REG		(SUNXI_R_WDOG_BASE + 0x0014)

/* The prototype in sunxi_private.h was renamed along with the include above. */
void sunxi_power_down(void);

void sunxi_power_down(void)
{
	/*
	 * If a PMIC is ever fitted, a real power off beats the gate; without
	 * one this returns immediately and we fall through to the gate.
	 */
	sunxi_pmic_power_down();

	mmio_write_32(H713_GATE_FLAG_REG, H713_GATE_FLAG_VALUE);
	dsbsy();

	/*
	 * Read back before resetting. Without the flag the board would come
	 * back up and boot straight into the OS, turning a power off into a
	 * reboot; parking the cores (what the caller does when we return) is
	 * the lesser evil.
	 */
	if (mmio_read_32(H713_GATE_FLAG_REG) != H713_GATE_FLAG_VALUE) {
		ERROR("PSCI: cannot arm the boot gate, not resetting\n");
		return;
	}

	/*
	 * NOTICE, not INFO: the release build (DEBUG=0) stops at NOTICE, and
	 * this is the one line the acceptance test looks for.
	 */
	NOTICE("PSCI: power off, resetting into the boot gate\n");

	/* Reset the whole system when the watchdog times out. */
	mmio_write_32(H713_WDOG_CFG_REG, SUNXI_WDOG_KEY | 1);
	/* Enable the watchdog with the shortest timeout (0.5 seconds). */
	mmio_write_32(H713_WDOG_MODE_REG, SUNXI_WDOG_KEY | 1);

	/* Wait for twice the watchdog timeout before giving up. */
	mdelay(1000);

	/*
	 * Leave the flag in place: the power-off wish is still pending, and
	 * the only way out of the parked state is a power cycle, which clears
	 * GP5 anyway (a cleared GP5 also means "gate").
	 */
	ERROR("PSCI: system reset failed, board stays powered\n");
}
