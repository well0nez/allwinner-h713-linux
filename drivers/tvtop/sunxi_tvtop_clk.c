// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner H713 TV Subsystem Top — Clock Management
 *
 * Implements reference-counted clock enable/disable for the three
 * TV subsystem blocks. Exported symbols used by decd.ko and others.
 *
 * Ported from: sunxi_tvtop_clk_get (0x00c0), sunxi_tvtop_clk_put (0x0e08),
 *              clk_prepare_enable (0x0164), sunxi_tvtop_clock_enable (0x0198)
 *
 * PATCH: TVTOP Freeze Fix — clk_set_rate Guards + Fail-Fast (2026-04-13)
 * - Skip ALL clk_set_rate calls (parent + target) for ALL submodules
 *   Root cause: clk_set_rate() triggers SoC bus fault / freeze
 *   (KNOW-20260413-031149-493, conf 0.92)
 * - Change sunxi_tvtop_clock_enable() from void to int with fail-fast + rollback
 *   (KNOW-20260413-020844-809)
 */
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/export.h>
#include <linux/mutex.h>
#include <linux/printk.h>
#include "sunxi_tvtop.h"

/*
 * Select the best parent for a clock given a desired parent rate.
 *
 * Problem: tvtop clk_set_rate(parent, rate) blindly changes whatever parent
 * the mux currently points to. If two clocks share a PLL parent but need
 * different rates (e.g. cip27 needs pll-video0@324MHz, adc needs pll-adc@1296MHz),
 * the second clk_set_rate destroys the first clock's rate.
 *
 * Fix: Before setting the parent rate, iterate all possible parents and pick
 * the one whose current rate already matches (or can match) the desired rate.
 * Then call clk_set_parent() to switch the mux before touching the PLL rate.
 */
static void tvtop_select_best_parent(struct clk *clk, unsigned long parent_rate)
{
	struct clk_hw *hw = __clk_get_hw(clk);
	unsigned int i, num_parents;
	struct clk *current_parent;
	unsigned long current_parent_rate;

	if (!hw)
		return;

	current_parent = clk_get_parent(clk);
	if (current_parent) {
		current_parent_rate = clk_get_rate(current_parent);
		if (current_parent_rate == parent_rate)
			return;
	}

	num_parents = clk_hw_get_num_parents(hw);
	for (i = 0; i < num_parents; i++) {
		struct clk_hw *candidate_hw = clk_hw_get_parent_by_index(hw, i);
		struct clk *candidate;
		unsigned long rate;

		if (!candidate_hw)
			continue;

		candidate = candidate_hw->clk;
		if (!candidate || candidate == current_parent)
			continue;

		rate = clk_get_rate(candidate);
		if (rate == parent_rate) {
			pr_info("tvtop: parent-select: %s: switch %s (%lu) -> %s (%lu)\n",
				__clk_get_name(clk),
				current_parent ? __clk_get_name(current_parent) : "none",
				current_parent ? current_parent_rate : 0,
				__clk_get_name(candidate), rate);
			clk_set_parent(clk, candidate);
			return;
		}
	}

	for (i = 0; i < num_parents; i++) {
		struct clk_hw *candidate_hw = clk_hw_get_parent_by_index(hw, i);
		struct clk *candidate;
		long rounded;

		if (!candidate_hw)
			continue;

		candidate = candidate_hw->clk;
		if (!candidate || candidate == current_parent)
			continue;

		rounded = clk_round_rate(candidate, parent_rate);
		if (rounded > 0 && (unsigned long)rounded == parent_rate) {
			pr_info("tvtop: parent-select: %s: switch to %s (can round to %lu)\n",
				__clk_get_name(clk),
				__clk_get_name(candidate), parent_rate);
			clk_set_parent(clk, candidate);
			return;
		}
	}

	pr_info("tvtop: parent-select: %s: no better parent for rate %lu, keeping %s\n",
		__clk_get_name(clk), parent_rate,
		current_parent ? __clk_get_name(current_parent) : "none");
}
/*
 * Internal helper: prepare + enable a clock, undo prepare on enable failure.
 * Matches stock clk_prepare_enable at 0x0164 (52 bytes).
 *
 * Disasm logic:
 *   clk_prepare(clk) → if fail, return error
 *   clk_enable(clk)  → if fail, clk_unprepare(clk), return error
 *   return 0
 */
static int tvtop_clk_prepare_enable(struct clk *clk)
{
	int ret;
	ret = clk_prepare(clk);
	if (ret)
		return ret;
	ret = clk_enable(clk);
	if (ret) {
		clk_unprepare(clk);
		return ret;
	}
	return 0;
}
/*
 * Enable all clocks in a submodule's clock list.
 * Matches stock sunxi_tvtop_clock_enable at 0x0198 (260 bytes).
 *
 * PATCH: Changed from void to int with fail-fast + rollback.
 * PATCH: Skip ALL clk_set_rate calls (parent + target) for ALL submodules.
 *   Root cause: clk_set_rate() triggers SoC bus fault / freeze
 *   (KNOW-20260413-031149-493, conf 0.92)
 *
 * Disasm logic:
 *   For each clk_entry in sub->clk_list:
 *     1. If entry->clk exists and not yet enabled:
 *        clk_prepare_enable(entry->clk), mark enabled, FAIL FAST on error
 *     2. If entry->parent_rate != 0:
 *        Select best parent, get parent clk, prepare+enable parent
 *        clk_set_rate(parent, parent_rate) — SKIPPED (causes freeze)
 *     3. If entry->target_rate != 0:
 *        clk_set_rate(entry->clk, target_rate) — SKIPPED (causes freeze)
 *
 * Returns: 0 on success, negative error code on failure.
 * On failure, already-enabled clocks are rolled back.
 */
int sunxi_tvtop_clock_enable(struct tvtop_submodule *sub)
{
	struct tvtop_clk_entry *entry;
	int ret;

	pr_info("tvtop: %s: clock_enable enter\n", sub->hw_data->name);

	list_for_each_entry(entry, &sub->clk_list, list) {
		pr_info("tvtop: %s: entry clk=%p enabled=%d target=%lu parent_rate=%lu\n",
			sub->hw_data->name, entry->clk, entry->clk_enabled,
			entry->target_rate, entry->parent_rate);

		/* Step 1: Enable the clock */
		if (entry->clk && !entry->clk_enabled) {
			pr_info("tvtop: %s: enable clock start\n", sub->hw_data->name);
			ret = tvtop_clk_prepare_enable(entry->clk);
			pr_info("tvtop: %s: enable clock done ret=%d\n",
				sub->hw_data->name, ret);
			if (ret == 0) {
				entry->clk_enabled = true;
			} else {
				pr_err("tvtop: %s: failed to enable clock! Rolling back.\n",
				       sub->hw_data->name);
				goto rollback;
			}
		}

		/* Step 2: Parent clock handling */
		if (entry->parent_rate == 0) {
			pr_info("tvtop: %s: no parent rate, go set_rate\n",
				sub->hw_data->name);
			goto set_rate;
		}

		/* Select correct parent mux BEFORE getting/enabling it */
		tvtop_select_best_parent(entry->clk, entry->parent_rate);

		entry->parent_clk = clk_get_parent(entry->clk);
		pr_info("tvtop: %s: parent clk=%p (%s) enabled=%d\n",
			sub->hw_data->name, entry->parent_clk,
			entry->parent_clk ? __clk_get_name(entry->parent_clk) : "null",
			entry->parent_clk_enabled);
		if (!entry->parent_clk)
			goto set_rate;
		if (entry->parent_clk_enabled) {
			pr_info("tvtop: %s: parent already enabled\n",
				sub->hw_data->name);
			goto set_rate;
		}
		pr_info("tvtop: %s: enable parent start rate=%lu\n",
			sub->hw_data->name, entry->parent_rate);
		ret = tvtop_clk_prepare_enable(entry->parent_clk);
		pr_info("tvtop: %s: enable parent done ret=%d\n",
			sub->hw_data->name, ret);
		if (ret == 0) {
			entry->parent_clk_enabled = true;
		} else {
			pr_err("tvtop: %s: failed to enable parent clock! Rolling back.\n",
			       sub->hw_data->name);
			goto rollback;
		}

		/*
		 * PATCH: Skip clk_set_rate for ALL parent clocks.
		 * clk_set_rate() on parent clocks (tvcap: 1296MHz, 600MHz, 1152MHz;
		 * tvdisp/tvfe: various PLL rates) causes a SoC bus fault / freeze.
		 * The mainline CCU driver doesn't support those PLL configurations.
		 * Clocks are still enabled normally, only the rate change is skipped.
		 * (KNOW-20260413-031149-493, conf 0.92)
		 */
		pr_info("tvtop: %s: SKIP parent clk_set_rate %lu (freeze workaround)\n",
			sub->hw_data->name, entry->parent_rate);

set_rate:
		/*
		 * PATCH: Skip clk_set_rate for ALL target clocks.
		 * Same root cause as parent rates — clk_set_rate triggers freeze.
		 * Boot default rates are used instead.
		 * (KNOW-20260413-031149-493, conf 0.92)
		 */
		if (entry->target_rate) {
			pr_info("tvtop: %s: SKIP target clk_set_rate %lu (freeze workaround)\n",
				sub->hw_data->name, entry->target_rate);
		}
	}

	pr_info("tvtop: %s: clock_enable exit (success)\n", sub->hw_data->name);
	return 0;

rollback:
	/* Rollback: disable all clocks we enabled in this call */
	pr_info("tvtop: %s: rolling back enabled clocks\n", sub->hw_data->name);
	list_for_each_entry_continue_reverse(entry, &sub->clk_list, list) {
		if (entry->clk && entry->clk_enabled) {
			clk_disable_unprepare(entry->clk);
			entry->clk_enabled = false;
			pr_info("tvtop: %s: rolled back clock %p\n",
				sub->hw_data->name, entry->clk);
		}
		if (entry->parent_clk && entry->parent_clk_enabled) {
			clk_disable_unprepare(entry->parent_clk);
			entry->parent_clk_enabled = false;
			pr_info("tvtop: %s: rolled back parent clock %p\n",
				sub->hw_data->name, entry->parent_clk);
		}
	}
	pr_err("tvtop: %s: clock_enable failed, returning %d\n",
	       sub->hw_data->name, ret);
	return ret;
}
/*
 * Acquire a clock reference for a submodule.
 * Matches stock sunxi_tvtop_clk_get at 0x00c0 (164 bytes).
 *
 * Disasm logic:
 *   if type > 2: error
 *   lock clk_ctrl[type].lock
 *   refcount++
 *   if refcount == 1 (first user):
 *     call enable_fn(tvtopdev->dev)
 *     if type == 0: also call sunxi_tvtop_clk_get(1) recursively
 *   unlock
 *   return result
 *
 * EXPORTED: Used by decd.ko and other display modules.
 */
int sunxi_tvtop_clk_get(unsigned int type)
{
	struct tvtop_clk_ctrl *ctrl;
	int ret = 0;
	if (type > 2) {
		pr_err("tvtop: %s: unknown module type %d\n",
		       __func__, type);
		return -EINVAL;
	}
	ctrl = &tvtopdev->clk_ctrl[type];
	mutex_lock(&ctrl->lock);
	ctrl->refcount++;
	pr_emerg("tvtopdbg:01 clk_get type=%u refcount=%u\n", type, ctrl->refcount);
	if (ctrl->refcount == 1) {
		pr_emerg("tvtopdbg:01b enable_fn_start type=%u\n", type);
		ret = ctrl->enable_fn(tvtopdev->dev);
		pr_emerg("tvtopdbg:01c enable_fn_done type=%u ret=%d\n", type, ret);
		/* tvdisp (type 0) also enables tvcap (type 1) */
		if (type == TVTOP_SUB_TVDISP) {
			int ret_tvcap;
			pr_emerg("tvtopdbg:01d recurse_get_tvcap start\n");
			ret_tvcap = sunxi_tvtop_clk_get(TVTOP_SUB_TVCAP);
			pr_emerg("tvtopdbg:01e recurse_get_tvcap done ret=%d\n", ret_tvcap);
			if (!ret)
				ret = ret_tvcap;
		}
	}
	mutex_unlock(&ctrl->lock);
	return ret;
}
EXPORT_SYMBOL(sunxi_tvtop_clk_get);
/*
 * Release a clock reference for a submodule.
 * Matches stock sunxi_tvtop_clk_put at 0x0e08 (220 bytes).
 *
 * Disasm logic:
 *   if type > 2: error
 *   lock clk_ctrl[type].lock
 *   if refcount == 0: WARN, return -1
 *   refcount--
 *   if refcount == 0 (last user):
 *     tvtop_submodule_disable(dev, type)
 *     if type == 0: also call sunxi_tvtop_clk_put(1) recursively
 *   unlock
 *   return result
 */
int sunxi_tvtop_clk_put(unsigned int type)
{
	struct tvtop_clk_ctrl *ctrl;
	int ret = 0;
	if (type > 2) {
		pr_err("tvtop: %s: unknown module type %d\n",
		       __func__, type);
		return -EINVAL;
	}
	ctrl = &tvtopdev->clk_ctrl[type];
	mutex_lock(&ctrl->lock);
	if (ctrl->refcount == 0) {
		pr_err("tvtop: %s: unbalance clk operation\n", __func__);
		WARN_ON(1);
		ret = -1;
		goto out;
	}
	ctrl->refcount--;
	if (ctrl->refcount == 0) {
		/* Last user — disable the submodule */
		tvtop_submodule_disable(tvtopdev->dev, type);
		/* tvdisp (type 0) also disables tvcap (type 1) */
		if (type == TVTOP_SUB_TVDISP)
			sunxi_tvtop_clk_put(TVTOP_SUB_TVCAP);
	}
out:
	mutex_unlock(&ctrl->lock);
	return ret;
}
EXPORT_SYMBOL(sunxi_tvtop_clk_put);
