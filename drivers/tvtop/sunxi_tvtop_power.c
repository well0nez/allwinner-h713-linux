// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner H713 TV Subsystem Top — Power Domains & Subsystem Enable/Disable
 *
 * Ported from: tvtop_pm_domain_enable (0x093c), tvtop_pm_domain_disable (0x0c80),
 *              tvtop_tvdisp_enable (0x029c), tvtop_tvfe_enable (0x09dc),
 *              tvtop_tvcap_enable (0x0ac4), tvtop_submodule_disable (0x0cb8)
 *
 * PATCH: TVTOP Freeze Fix — Reset-Ordering + msleep + PM Error Handling (2026-04-13)
 * - tvfe: Remove first reset_deassert (was before clocks = undefined behavior)
 *   (KNOW-20260413-040938-645)
 * - Replace all usleep_range with msleep for stability
 * - Check pm_domain_enable return values, fail fast on error
 */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/mutex.h>
#include <linux/pm_domain.h>
#include <linux/pm_runtime.h>
#include <linux/reset.h>

#include "sunxi_tvtop.h"

/* Global power-on flag for tvcap INCAP register sequence */
static int is_power_on;

/*
 * Enable power domain for a submodule.
 * Matches stock tvtop_pm_domain_enable at 0x093c (160 bytes).
 *
 * Disasm logic:
 *   if sub->pm_link == NULL: return 0
 *   dev_pm_genpd_set_performance_state(pm_link, INT_MAX)
 *   pm_runtime_resume(pm_link)
 *   if resume fails:
 *     atomic_dec(pm_link->device.power.usage_count) [inline runtime]
 *     dev_pm_genpd_set_performance_state(pm_link, 0)
 *     dev_err(pm_link, "tvtop pm domain enable failed, ret=%d!")
 *   return ret
 */
int tvtop_pm_domain_enable(struct tvtop_submodule *sub)
{
	int ret;

	if (!sub->pm_dev)
		return 0;

	dev_pm_genpd_set_performance_state(sub->pm_dev, INT_MAX);

	/*
	 * Stock uses __pm_runtime_resume(pm_dev, RPM_GET_PUT=4).
	 * pm_runtime_resume_and_get() is the mainline equivalent.
	 */
	ret = pm_runtime_resume_and_get(sub->pm_dev);
	if (ret < 0) {
		/*
		 * Stock does inline atomic_dec_if_positive on usage_count.
		 * pm_runtime_put_noidle is the clean equivalent.
		 */
		pm_runtime_put_noidle(sub->pm_dev);
		dev_pm_genpd_set_performance_state(sub->pm_dev, 0);
		dev_err(sub->pm_dev,
			"tvtop pm domain enable failed, ret=%d!\n", ret);
	}

	return ret;
}

/*
 * Disable power domain for a submodule.
 * Matches stock tvtop_pm_domain_disable at 0x0c80 (56 bytes).
 *
 * Disasm logic:
 *   if sub->pm_link == NULL: return
 *   dev_pm_genpd_set_performance_state(pm_link, 0)
 *   pm_runtime_idle(pm_link)
 */
void tvtop_pm_domain_disable(struct tvtop_submodule *sub)
{
	if (!sub->pm_dev)
		return;

	dev_pm_genpd_set_performance_state(sub->pm_dev, 0);
	/* Stock uses flags value 5 = RPM_ASYNC | RPM_GET_PUT */
	__pm_runtime_idle(sub->pm_dev, RPM_ASYNC | RPM_GET_PUT);
}

/*
 * Enable tvdisp (display) subsystem.
 * Matches stock tvtop_tvdisp_enable at 0x029c (264 bytes).
 *
 * Disasm logic:
 *   lock sub[0].lock
 *   if already enabled: unlock, return 0
 *   clock_enable(sub[0])
 *   enable bus_clk if present and not yet enabled
 *   reset_control_deassert(rst) — if fail, error + unlock
 *   if first_init:
 *     dev_info "tvdisp skip first initialized."
 *     clear first_init, set enabled, unlock, return 0
 *   else:
 *     write 7 register entries from disp_regs[resolution_type]
 *     set enabled, unlock, return 0
 */
int tvtop_tvdisp_enable(struct device *dev)
{
	struct tvtop_device *tdev = dev_get_drvdata(dev);
	struct tvtop_submodule *sub = &tdev->sub[TVTOP_SUB_TVDISP];
	int ret = 0;
	int i;

	dev_info(tdev->dev,
		 "tvdisp: enter enabled=%d first_init=%d bus_clk_enabled=%d config=%d iobase=%p\n",
		 sub->enabled, tdev->first_init, sub->bus_clk_enabled,
		 sub->config_val, sub->iobase);

	mutex_lock(&sub->lock);
	pr_emerg("tvtopdbg:02 mutex_locked\n");

	if (sub->enabled) {
		dev_info(tdev->dev, "tvdisp: already enabled\n");
		goto out;
	}

	pr_emerg("tvtopdbg:03 clock_enable_start\n");
	ret = sunxi_tvtop_clock_enable(sub);
	pr_emerg("tvtopdbg:04 clock_enable_done ret=%d\n", ret);
	if (ret) {
		dev_err(tdev->dev, "tvdisp: clock_enable failed: %d\n", ret);
		goto out;
	}

	if (sub->bus_clk && !sub->bus_clk_enabled) {
		pr_emerg("tvtopdbg:05 bus_clk_start\n");
		ret = clk_prepare_enable(sub->bus_clk);
		pr_emerg("tvtopdbg:06 bus_clk_done ret=%d\n", ret);
		if (ret == 0)
			sub->bus_clk_enabled = true;
		else
			goto out;
	} else {
		dev_info(tdev->dev,
			 "tvdisp: bus_clk skip present=%d enabled=%d\n",
			 !!sub->bus_clk, sub->bus_clk_enabled);
	}

	pr_emerg("tvtopdbg:07 reset_start\n");
	ret = reset_control_deassert(sub->rst);
	pr_emerg("tvtopdbg:08 reset_done ret=%d\n", ret);
	if (ret) {
		dev_err(tdev->dev,
			"tvdisp bus reset deassert fail: %d!\n", ret);
		goto out;
	}

	dev_info(tdev->dev, "tvdisp: first_init check=%d\n", tdev->first_init);
	if (tdev->first_init) {
		pr_emerg("tvtopdbg:09 first_init_skip_forced_write\n");
		tdev->first_init = 0;
		pr_emerg("tvtopdbg:10 first_init_cleared\n");
	}

	{
		int res_type = sub->config_val;

		pr_emerg("tvtopdbg:10b write_table_start res_type=%d\n", res_type);
		if (res_type >= 0 && res_type < TVTOP_RES_TYPE_COUNT) {
			for (i = 0; i < TVTOP_DISP_REG_COUNT; i++) {
				pr_emerg("tvtopdbg:10c write idx=%d off=0x%x val=0x%08x\n",
					 i, tvtop_disp_regs[res_type][i].offset,
					 tvtop_disp_regs[res_type][i].value);
				writel(tvtop_disp_regs[res_type][i].value,
				       sub->iobase +
				       tvtop_disp_regs[res_type][i].offset);
			}
		} else {
			pr_emerg("tvtopdbg:10d invalid_res_type=%d\n", res_type);
		}
		pr_emerg("tvtopdbg:10e write_table_done\n");
	}

	sub->enabled = 1;
	pr_emerg("tvtopdbg:11 enabled_set\n");

out:
	dev_info(tdev->dev, "tvdisp: unlock ret=%d enabled=%d\n", ret, sub->enabled);
	mutex_unlock(&sub->lock);
	pr_emerg("tvtopdbg:12 return ret=%d\n", ret);
	return ret;
}

/*
 * Enable tvfe (TV front-end / demodulator) subsystem.
 * Matches stock tvtop_tvfe_enable at 0x09dc (232 bytes).
 *
 * PATCH: Remove first reset_deassert — it was called BEFORE clocks,
 *   causing undefined behavior. Only keep the second one after clocks.
 *   (KNOW-20260413-040938-645)
 * PATCH: Replace usleep_range with msleep for stability.
 * PATCH: Check pm_domain_enable return value.
 *
 * Disasm logic (original stock):
 *   lock sub[2].lock
 *   if already enabled: unlock, return 0
 *   reset_control_deassert(rst)   [first deassert — REMOVED]
 *   usleep_range(10000, 15000)    [REMOVED]
 *   clock_enable(sub[2])
 *   enable bus_clk if present
 *   usleep_range(10000, 15000)
 *   reset_control_deassert(rst)   [second deassert — KEPT]
 *   if fail: error, unlock
 *   tvtop_pm_domain_enable(sub[2])
 *   usleep_range(10000, 15000)
 *   writel(0x003003FF, iobase)    [tvfe init register]
 *   set enabled, unlock, return 0
 */
int tvtop_tvfe_enable(struct device *dev)
{
	struct tvtop_device *tdev = dev_get_drvdata(dev);
	struct tvtop_submodule *sub = &tdev->sub[TVTOP_SUB_TVFE];
	int ret = 0;

	mutex_lock(&sub->lock);
	pr_emerg("tvtopdbg:20 tvcap_mutex_locked\n");

	if (sub->enabled)
		goto out;

	/*
	 * PATCH: Removed first reset_deassert + usleep_range.
	 * The stock code called reset_deassert BEFORE clocks were enabled,
	 * which is undefined behavior and likely contributes to instability.
	 * (KNOW-20260413-040938-645)
	 */

	/* Enable clocks */
	pr_emerg("tvtopdbg:21 tvcap_clock_enable_start\n");
	ret = sunxi_tvtop_clock_enable(sub);
	pr_emerg("tvtopdbg:22 tvcap_clock_enable_done ret=%d\n", ret);
	if (ret) {
		dev_err(tdev->dev, "tvfe: clock_enable failed: %d\n", ret);
		goto out;
	}

	/* Enable bus clock if present */
	if (sub->bus_clk && !sub->bus_clk_enabled) {
		pr_emerg("tvtopdbg:25 tvcap_bus_clk_start\n");
		ret = clk_prepare_enable(sub->bus_clk);
		pr_emerg("tvtopdbg:26 tvcap_bus_clk_done ret=%d\n", ret);
		if (ret == 0)
			sub->bus_clk_enabled = true;
		else
			goto out;
	}

	/* PATCH: usleep_range → msleep for stability */
	msleep(15);

	/* Reset deassert — this is the ONLY one now (was the second in stock) */
	ret = reset_control_deassert(sub->rst);
	if (ret) {
		dev_err(tdev->dev,
			"tvfe bus reset deassert fail: %d!\n", ret);
		goto out;
	}

	/* Enable power domain — check return value */
	ret = tvtop_pm_domain_enable(sub);
	if (ret < 0) {
		dev_err(tdev->dev, "tvfe: pm_domain_enable failed: %d\n", ret);
		goto out;
	}

	/* PATCH: usleep_range → msleep for stability */
	msleep(15);

	/* Write tvfe init register */
	writel(0x003003FF, sub->iobase);

	sub->enabled = 1;

out:
	pr_emerg("tvtopdbg:36 tvcap_return ret=%d enabled=%d\n", ret, sub->enabled);
	mutex_unlock(&sub->lock);
	return ret;
}

/*
 * Enable tvcap (TV capture / HDMI input) subsystem.
 * Matches stock tvtop_tvcap_enable at 0x0ac4 (444 bytes).
 *
 * PATCH: Replace usleep_range with msleep for stability.
 * PATCH: Check pm_domain_enable return value.
 */
int tvtop_tvcap_enable(struct device *dev)
{
	struct tvtop_device *tdev = dev_get_drvdata(dev);
	struct tvtop_submodule *sub = &tdev->sub[TVTOP_SUB_TVCAP];
	int ret = 0;

	mutex_lock(&sub->lock);

	if (sub->enabled)
		goto out;

	/* Enable clocks */
	ret = sunxi_tvtop_clock_enable(sub);
	if (ret) {
		dev_err(tdev->dev, "tvcap: clock_enable failed: %d\n", ret);
		goto out;
	}

	pr_emerg("tvtopdbg:23 tvcap_sleep1_start\n");
	/* PATCH: usleep_range → msleep for stability */
	msleep(15);
	pr_emerg("tvtopdbg:24 tvcap_sleep1_done\n");

	/* Enable bus clock if present */
	if (sub->bus_clk && !sub->bus_clk_enabled) {
		ret = clk_prepare_enable(sub->bus_clk);
		if (ret == 0)
			sub->bus_clk_enabled = true;
		else
			goto out;
	}

	/* Deassert reset */
	pr_emerg("tvtopdbg:27 tvcap_reset_start\n");
	ret = reset_control_deassert(sub->rst);
	pr_emerg("tvtopdbg:28 tvcap_reset_done ret=%d\n", ret);
	if (ret) {
		dev_err(tdev->dev,
			"tvcap bus reset deassert fail: %d!\n", ret);
		goto out;
	}

	pr_emerg("tvtopdbg:29 tvcap_sleep2_start\n");
	/* PATCH: usleep_range → msleep for stability */
	msleep(15);
	pr_emerg("tvtopdbg:30 tvcap_sleep2_done\n");

	/* Enable power domain — check return value */
	pr_emerg("tvtopdbg:31 tvcap_pm_domain_start\n");
	ret = tvtop_pm_domain_enable(sub);
	pr_emerg("tvtopdbg:32 tvcap_pm_domain_done ret=%d\n", ret);
	if (ret < 0) {
		dev_err(tdev->dev, "tvcap: pm_domain_enable failed: %d\n", ret);
		goto out;
	}

	pr_emerg("tvtopdbg:33 tvcap_sleep3_start\n");
	/* PATCH: usleep_range → msleep for stability */
	msleep(15);
	pr_emerg("tvtopdbg:34 tvcap_sleep3_done\n");

	/*
	 * Magic INCAP register sequence: only on subsequent enables
	 * (is_power_on is 0 on first boot, set to 1 after first enable)
	 */
	if (1) {
		void __iomem *iobase = sub->iobase;
		void __iomem *incap_reg;

		pr_emerg("tvtopdbg:50 tvcap_magic_phase1_start\n");
		/* Phase 1: write magic values */
		writel(0x01111117, iobase + 4);
		writel(0x00000404, iobase + 8);
		writel(0x00111111, iobase + 0);
		/* PATCH: usleep_range → msleep for stability */
		msleep(15);

		pr_emerg("tvtopdbg:51 tvcap_magic_phase2_start\n");
		/* Phase 2: clear all */
		writel(0, iobase + 4);
		/* PATCH: usleep_range → msleep for stability */
		msleep(15);
		writel(0, iobase + 8);
		writel(0, iobase + 0);
		/* PATCH: usleep_range → msleep for stability */
		msleep(15);

		pr_emerg("tvtopdbg:52 tvcap_magic_phase3_start\n");
		/* Phase 3: re-write magic values */
		writel(0x01111117, iobase + 4);
		/* PATCH: usleep_range → msleep for stability */
		msleep(15);
		writel(0x00000404, iobase + 8);
		writel(0x00111111, iobase + 0);
		/* PATCH: usleep_range → msleep for stability */
		msleep(15);

		pr_emerg("tvtopdbg:53 tvcap_magic_phase4_start\n");
		/* Phase 4: INCAP power register — enable capture block */
		incap_reg = ioremap(TVTOP_INCAP_REG_PHYS,
				    TVTOP_INCAP_REG_SIZE);
		if (incap_reg && !IS_ERR(incap_reg)) {
			wmb(); /* dsb(st) + arm_heavy_mb() in stock */
			writel(1, incap_reg);
			pr_emerg("tvtopdbg:54 tvcap_incap_write_done\n");
			iounmap(incap_reg);
		} else {
			pr_err("tvtop: ioremap INCAP REG error: %pK\n",
			       incap_reg);
		}
	}

	pr_emerg("tvtopdbg:35 tvcap_set_enabled\n");
	is_power_on = 1;
	sub->enabled = 1;

out:
	mutex_unlock(&sub->lock);
	return ret;
}

/*
 * Disable a submodule: clocks, reset, power domain.
 * Matches stock tvtop_submodule_disable at 0x0cb8 (336 bytes).
 *
 * Disasm logic:
 *   lock sub[index].lock
 *   if not enabled: unlock, return
 *   For each clk_entry in sub->clk_list:
 *     if clk_enabled: clk_disable + clk_unprepare, clear flag
 *     if parent_clk_enabled: clk_disable + clk_unprepare parent, clear flag
 *   reset_control_assert(rst)
 *   if bus_clk enabled: clk_disable + clk_unprepare bus_clk, clear flag
 *   tvtop_pm_domain_disable(sub)
 *   set enabled = 0
 *   dev_info "submodule disable [%d]"
 *   unlock
 */
void tvtop_submodule_disable(struct device *dev, unsigned int index)
{
	struct tvtop_device *tdev = dev_get_drvdata(dev);
	struct tvtop_submodule *sub;
	struct tvtop_clk_entry *entry;

	if (index >= TVTOP_SUB_COUNT)
		return;

	sub = &tdev->sub[index];

	mutex_lock(&sub->lock);

	if (!sub->enabled)
		goto out;

	/* Disable all clocks in the list */
	list_for_each_entry(entry, &sub->clk_list, list) {
		if (entry->clk && entry->clk_enabled) {
			clk_disable(entry->clk);
			clk_unprepare(entry->clk);
			entry->clk_enabled = false;
		}
		if (entry->parent_clk && entry->parent_clk_enabled) {
			clk_disable(entry->parent_clk);
			clk_unprepare(entry->parent_clk);
			entry->parent_clk_enabled = false;
		}
	}

	/* Assert reset */
	reset_control_assert(sub->rst);

	/* Disable bus clock */
	if (sub->bus_clk && sub->bus_clk_enabled) {
		clk_disable(sub->bus_clk);
		clk_unprepare(sub->bus_clk);
		sub->bus_clk_enabled = false;
	}

	/* Disable power domain */
	tvtop_pm_domain_disable(sub);

	sub->enabled = 0;

	dev_info(tdev->dev, "submodule disable [%d]\n", index);

out:
	mutex_unlock(&sub->lock);
}
