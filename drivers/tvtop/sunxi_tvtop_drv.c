// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner H713 TV Subsystem Top — Platform Driver
 *
 * Ported from: sunxi_tvtop_probe (0x03a4), sunxi_tvtop_remove (0x0fa4),
 *              sunxi_tvtop_resume (0x0000), sunxi_tvtop_suspend (0x0020),
 *              sunxi_tvtop_complete (0x0084),
 *              sunxi_tvtop_client_register (0x0040)
 */

#include <linux/clk.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/pm_domain.h>
#include <linux/reset.h>
#include <linux/slab.h>
#include <linux/sysfs.h>

#include "sunxi_tvtop.h"

/* Global device pointer — used by exported clk_get/clk_put */
struct tvtop_device *tvtopdev;

/*
 * External: HDCP key refresh (provided by sunxi secure monitor or stub).
 * Declared weak so the driver works without the secure monitor.
 */
int sunxi_smc_refresh_hdcp(void);
int __weak sunxi_smc_refresh_hdcp(void)
{
	return 0;
}

/* ================================================================
 * Resolution detection — reads panel DT node
 * Matches stock probe at 0x0530-0x0638
 * ================================================================ */

static int tvtop_detect_resolution(struct device_node *tvtop_node)
{
	struct device_node *panel_node;
	u32 width = 0, height = 0, dual_port = 0;

	/*
	 * Stock searches for a "tvtop@1" FEX-style panel config node.
	 * In our mainline DTS this node doesn't exist as a separate device.
	 * Try reading panel properties from the tvtop node itself first,
	 * then fall back to TVTOP_RES_1080P (HY310 has a 1080p panel).
	 */
	panel_node = of_get_child_by_name(tvtop_node, "tvtop@1");
	if (!panel_node)
		panel_node = of_node_get(tvtop_node);
	if (!panel_node) {
		pr_info("tvtop: no panel node found, defaulting to 1080p\n");
		return TVTOP_RES_1080P;
	}

	of_property_read_u32(panel_node, "panel_width", &width);
	of_property_read_u32(panel_node, "panel_height", &height);
	of_property_read_u32(panel_node, "panel_dual_port", &dual_port);
	of_node_put(panel_node);

	/* Resolution mapping — extracted from stock binary */
	if (width == 1920 && height == 1080)
		return TVTOP_RES_1080P;		/* 0 */

	if (width == 1366 && height == 768)
		return TVTOP_RES_720P;		/* 3 */

	if (width == 1280 && height == 720)
		return TVTOP_RES_720P;		/* 3 */

	if (width == 640 && height == 360)
		return TVTOP_RES_360P;		/* 2 */

	if (width == 0 || height == 0)
		return TVTOP_RES_1080P;	/* default for HY310 */

	/* Unknown resolution: interlace → type 0, otherwise type 3 */
	return (dual_port == 1) ? TVTOP_RES_1080P : TVTOP_RES_720P;
}

/* ================================================================
 * Probe — main initialization
 * Matches stock sunxi_tvtop_probe at 0x03a4 (1432 bytes)
 * ================================================================ */

static int sunxi_tvtop_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct tvtop_device *tdev;
	int i, ret;

	/*
	 * Stock driver checks strstr(pdev->name, "tvtop_pm"):
	 * If the device is probed via the "allwinner,sunxi-tvtop-pm"
	 * compatible, it only does power domain attachment for existing
	 * tvtopdev, then returns.
	 */
	if (tvtopdev && strstr(pdev->name, "tvtop_pm")) {
		for (i = 0; i < TVTOP_SUB_COUNT; i++) {
			struct tvtop_submodule *sub = &tvtopdev->sub[i];
			const struct tvtop_hw_data *hw = &tvtop_hw_data[i];

			sub->hw_data = hw;
			if (hw->pm_domain) {
				sub->pm_dev = dev_pm_domain_attach_by_name(
					dev, hw->pm_domain);
				if (IS_ERR_OR_NULL(sub->pm_dev)) {
					dev_err(dev,
						"failed to get power domain: %s!\n",
						hw->pm_domain);
					sub->pm_dev = NULL;
				}
			}
		}
		return 0;
	}

	/* --- Normal probe path --- */

	tdev = kzalloc(sizeof(*tdev), GFP_KERNEL);
	if (!tdev) {
		dev_err(dev, "kzalloc failed, out of memory!\n");
		return -ENOMEM;
	}

	/* Create device class and child device */
	tdev->cls = class_create("tvtop");
	if (IS_ERR_OR_NULL(tdev->cls)) {
		dev_err(dev, "class_create 'tvtop' failed!\n");
		kfree(tdev);
		return -ENOMEM;
	}

	tdev->dev = device_create(tdev->cls, dev, 0, tdev, "tvtop");
	tdev->first_init = 1;
	tdev->pdev_dev = dev;
	platform_set_drvdata(pdev, tdev);

	/* Validate DT node early - must check before any of_* calls.
	 * With CONFIG_OF_IOMMU enabled, of_node can be non-NULL but invalid
	 * (e.g. 0x1) during probe deferral. Guard against this.
	 */
	if (!np || (unsigned long)np < PAGE_SIZE) {
		dev_err(dev, "invalid of_node (%pe), cannot probe\n", np);
		ret = -ENODEV;
		goto err_cleanup;
	}

	/* Initialize each submodule */
	for (i = 0; i < TVTOP_SUB_COUNT; i++) {
		struct tvtop_submodule *sub = &tdev->sub[i];
		const struct tvtop_hw_data *hw = &tvtop_hw_data[i];
		const struct tvtop_clk_desc *desc;

		sub->hw_data = hw;

		/* Resolution detection only for tvdisp (index 0) */
		if (i == TVTOP_SUB_TVDISP)
			sub->config_val = tvtop_detect_resolution(np);
		else
			sub->config_val = 0;

		/* Init clock list */
		INIT_LIST_HEAD(&sub->clk_list);
		mutex_init(&sub->lock);


		/* Map I/O registers */
		sub->iobase = of_iomap(np, hw->iomap_idx);
		if (!sub->iobase) {
			dev_err(dev, "%s: invalid io memory!\n", hw->name);
			ret = -ENOMEM;
			goto err_cleanup;
		}

		/* Get reset control — stock uses shared=1, optional=0 */
		sub->rst = of_reset_control_get_shared(np, hw->rst_name);
		if (IS_ERR(sub->rst)) {
			dev_err(dev, "%s: Could not get reset control!\n",
				hw->name);
			ret = PTR_ERR(sub->rst);
			sub->rst = NULL;
			iounmap(sub->iobase);
			sub->iobase = NULL;
			if (ret == 0)
				goto init_clk_ctrl;
			goto err_cleanup;
		}

		/* Get bus clock */
		sub->bus_clk = of_clk_get_by_name(np, hw->clk_name);

		/* Parse and allocate sub-clock entries */
		for (desc = hw->clk_descs; desc->name; desc++) {
			struct tvtop_clk_entry *entry;
			struct clk *clk;

			clk = of_clk_get_by_name(np, desc->name);
			if (IS_ERR(clk)) {
				dev_err(dev,
					"%s: failed to get clk '%s'!\n",
					hw->name, desc->name);
				continue;
			}

			entry = kzalloc(sizeof(*entry), GFP_KERNEL);
			if (!entry) {
				dev_err(dev,
					"%s: kzalloc clk node error!\n",
					hw->name);
				clk_put(clk);
				continue;
			}

			entry->clk = clk;
			entry->target_rate = desc->rates[sub->config_val >= 0 ?
							  sub->config_val : 0];
			entry->parent_rate = desc->parent_rate;

			list_add_tail(&entry->list, &sub->clk_list);
		}

		/* Power domain attachment */
		sub->pm_dev = NULL;
		sub->enabled = 0;

init_clk_ctrl:
		/* Initialize clock control (ref counting) */
		mutex_init(&tdev->clk_ctrl[i].lock);
		tdev->clk_ctrl[i].refcount = 0;

		/* Assign enable function */
		switch (i) {
		case TVTOP_SUB_TVDISP:
			tdev->clk_ctrl[i].enable_fn = tvtop_tvdisp_enable;
			break;
		case TVTOP_SUB_TVCAP:
			tdev->clk_ctrl[i].enable_fn = tvtop_tvcap_enable;
			break;
		case TVTOP_SUB_TVFE:
			tdev->clk_ctrl[i].enable_fn = tvtop_tvfe_enable;
			break;
		}
	}

	/* Store global pointer */
	tvtopdev = tdev;

	/* Create sysfs attributes */
	if (tdev->dev) {
		ret = sysfs_create_group(&tdev->dev->kobj,
					 &tvtop_attribute_group);
		if (ret < 0) {
			dev_warn(tdev->dev,
				 "failed to create attr group \"reset_reason\": %d\n",
				 ret);
		}
	}

	return 0;

err_cleanup:
	/* On error during normal probe: cleanup and fail */
	dev_err(dev, "tvtop_driver_data_init error, type=%d!\n", i);
	device_destroy(tdev->cls, 0);
	class_destroy(tdev->cls);
	kfree(tdev);
	return ret;
}

/* ================================================================
 * Remove
 * Matches stock sunxi_tvtop_remove at 0x0fa4 (312 bytes)
 * ================================================================ */

static void sunxi_tvtop_remove(struct platform_device *pdev)
{
	struct tvtop_device *tdev = tvtopdev;
	int i;

	if (!tdev)
		return;

	/* Remove sysfs group */
	if (tdev->dev)
		sysfs_remove_group(&tdev->dev->kobj, &tvtop_attribute_group);

	/* Disable and cleanup each submodule */
	for (i = 0; i < TVTOP_SUB_COUNT; i++) {
		struct tvtop_submodule *sub = &tdev->sub[i];
		struct tvtop_clk_entry *entry, *tmp;

		/* Disable submodule */
		tvtop_submodule_disable(tdev->dev, i);

		/* Skip cleanup if no config */
		if (!sub->enabled && !sub->iobase)
			goto detach_pm;

		/* Unmap I/O */
		if (sub->iobase) {
			iounmap(sub->iobase);
			sub->iobase = NULL;
		}

		/* Release reset control */
		if (sub->rst) {
			reset_control_put(sub->rst);
			sub->rst = NULL;
		}

		/* Release bus clock */
		if (sub->bus_clk) {
			clk_put(sub->bus_clk);
			sub->bus_clk = NULL;
		}

		/* Free all clock entries */
		list_for_each_entry_safe(entry, tmp, &sub->clk_list, list) {
			list_del(&entry->list);
			if (entry->clk)
				clk_put(entry->clk);
			if (entry->parent_clk)
				clk_put(entry->parent_clk);
			kfree(entry);
		}

detach_pm:
		/* Detach power domain */
		if (sub->pm_dev) {
			dev_pm_domain_detach(sub->pm_dev, false);
			sub->pm_dev = NULL;
		}
		sub->enabled = 0;
	}

	/* Destroy device and class */
	if (tdev->dev)
		device_destroy(tdev->cls, 0);
	if (tdev->cls)
		class_destroy(tdev->cls);

	kfree(tdev);
	tvtopdev = NULL;
	platform_set_drvdata(pdev, NULL);
}

/* ================================================================
 * PM callbacks
 * Matches stock at 0x0000-0x00bc
 * ================================================================ */

/*
 * sunxi_tvtop_resume (0x0000, 32 bytes)
 * Just logs "sunxi tvtop resume"
 */
static int sunxi_tvtop_resume(struct device *dev)
{
	dev_info(dev, "sunxi tvtop resume\n");
	return 0;
}

/*
 * sunxi_tvtop_suspend (0x0020, 32 bytes)
 * Just logs "sunxi tvtop suspend"
 */
static int sunxi_tvtop_suspend(struct device *dev)
{
	dev_info(dev, "sunxi tvtop suspend\n");
	return 0;
}

/*
 * sunxi_tvtop_complete (0x0084, 60 bytes)
 *
 * Disasm logic:
 *   ret = sunxi_smc_refresh_hdcp()
 *   if ret != 0: printk("tvtop: refresh hdcp key failed!!!")
 *   dev_info(dev, "sunxi tvtop resume complete")
 */
static void sunxi_tvtop_complete(struct device *dev)
{
	int ret;

	ret = sunxi_smc_refresh_hdcp();
	if (ret)
		pr_err("tvtop: refresh hdcp key failed!!!\n");

	dev_info(dev, "sunxi tvtop resume complete\n");
}

static const struct dev_pm_ops tvtop_runtime_pm_ops = {
	.suspend  = sunxi_tvtop_suspend,
	.resume   = sunxi_tvtop_resume,
	.complete = sunxi_tvtop_complete,
};

/* ================================================================
 * Client registration (exported)
 * Matches stock sunxi_tvtop_client_register at 0x0040 (68 bytes)
 *
 * Disasm logic:
 *   if tvtopdev == NULL: return -ENODEV
 *   if tvtopdev->pdev_dev == NULL: return -ENODEV
 *   device_link_add(client_dev, tvtopdev->pdev_dev, DL_FLAG_STATELESS)
 *   return 0
 * ================================================================ */

int sunxi_tvtop_client_register(struct device *client_dev)
{
	if (!tvtopdev)
		return -EINVAL;
	if (!tvtopdev->pdev_dev)
		return -EINVAL;

	/* Stock passes flag value 2 = DL_FLAG_AUTOREMOVE_CONSUMER */
	device_link_add(client_dev, tvtopdev->pdev_dev,
			DL_FLAG_AUTOREMOVE_CONSUMER);

	return 0;
}
EXPORT_SYMBOL(sunxi_tvtop_client_register);

/* ================================================================
 * OF match table and platform driver
 * ================================================================ */

static const struct of_device_id sunxi_tvtop_of_match[] = {
	{ .compatible = "allwinner,sunxi-tvtop" },
	{ .compatible = "allwinner,sunxi-tvtop-pm" },
	{ /* sentinel */ },
};
MODULE_DEVICE_TABLE(of, sunxi_tvtop_of_match);

static struct platform_driver sunxi_tvtop_driver = {
	.probe  = sunxi_tvtop_probe,
	.remove = sunxi_tvtop_remove,
	.driver = {
		.name           = "sunxi-tvtop",
		.pm             = &tvtop_runtime_pm_ops,
		.of_match_table = sunxi_tvtop_of_match,
	},
};

module_platform_driver(sunxi_tvtop_driver);

MODULE_AUTHOR("Allwinner");
MODULE_DESCRIPTION("Sunxi tv subsystem top module driver");
MODULE_LICENSE("GPL v2");
