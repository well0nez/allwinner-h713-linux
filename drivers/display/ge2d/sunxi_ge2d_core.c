// SPDX-License-Identifier: GPL-2.0

#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/pm_runtime.h>

#include "sunxi_ge2d.h"

bool ge2d_enable_fbdev = true;
module_param_named(enable_fbdev, ge2d_enable_fbdev, bool, 0644);
MODULE_PARM_DESC(enable_fbdev,
	"Register the guarded fbdev scaffold (default: true)");

bool ge2d_enable_irqs = true;
module_param_named(enable_irqs, ge2d_enable_irqs, bool, 0644);
MODULE_PARM_DESC(enable_irqs,
	"Request GE2D IRQs during probe (default: true)");

bool ge2d_enable_dlpc3435 = true;
module_param_named(enable_dlpc3435, ge2d_enable_dlpc3435, bool, 0644);
MODULE_PARM_DESC(enable_dlpc3435,
	"Register and initialize the optional DLPC3435 helper (default: true)");

bool ge2d_backlight_boot_on;
module_param_named(backlight_boot_on, ge2d_backlight_boot_on, bool, 0644);
MODULE_PARM_DESC(backlight_boot_on,
	"Enable backlight output during probe (default: false)");

bool ge2d_enable_lvds_watchdog;
module_param_named(enable_lvds_watchdog, ge2d_enable_lvds_watchdog, bool, 0644);
MODULE_PARM_DESC(enable_lvds_watchdog,
	"Enable LVDS watchdog scaffolding (default: false)");


static int ge2d_map_resources(struct ge2d_device *gdev)
{
	struct resource *res;
	unsigned int i;

	for (i = 0; i < GE2D_IOMAP_MAX; i++) {
		res = platform_get_resource(gdev->pdev, IORESOURCE_MEM, i);
		if (!res)
			break;

		gdev->regs[i] = devm_ioremap_resource(gdev->dev, res);
		if (IS_ERR(gdev->regs[i]))
			return dev_err_probe(gdev->dev, PTR_ERR(gdev->regs[i]),
					     "failed to map MMIO resource %u\n", i);
	}

	gdev->num_regs = i;
	if (!gdev->num_regs)
		return dev_err_probe(gdev->dev, -ENODEV,
				     "GE2D node has no MMIO resources\n");


	/*
	 * Set convenience aliases from DTS reg resources.
	 * DTS reg order:  [0] = 0x05240000 (OSD core, 384KB)
	 *                 [1] = 0x051C0000 (LVDS, 64KB)
	 *                 [2] = 0x05200000 (OSD_B, 4KB)
	 *                 [3] = 0x05600000 (AFBD2, 4KB)
	 *
	 * afbd_base = afbd2_base + 0x100 (stock v2[12] = 0x05600100)
	 */
	if (gdev->num_regs >= 1)
		gdev->osd_base = gdev->regs[0];
	if (gdev->num_regs >= 4) {
		gdev->afbd2_base = gdev->regs[3];
		gdev->afbd_base  = gdev->regs[3] + 0x100;
	}
	if (gdev->num_regs >= 2)
		gdev->mixer_base = gdev->regs[0];  /* mixer within OSD core region */

	return 0;
}

static int ge2d_enable_resources(struct ge2d_device *gdev)
{
	int ret;

	gdev->clk_afbd = devm_clk_get_optional(gdev->dev, "clk_afbd");
	if (IS_ERR(gdev->clk_afbd))
		return dev_err_probe(gdev->dev, PTR_ERR(gdev->clk_afbd),
				     "failed to get clk_afbd\n");

	gdev->clk_bus_disp = devm_clk_get_optional(gdev->dev, "clk_bus_disp");
	if (IS_ERR(gdev->clk_bus_disp))
		return dev_err_probe(gdev->dev, PTR_ERR(gdev->clk_bus_disp),
				     "failed to get clk_bus_disp\n");

	gdev->rst_bus_disp =
		devm_reset_control_get_optional_shared(gdev->dev, "rst_bus_disp");
	if (IS_ERR(gdev->rst_bus_disp))
		return dev_err_probe(gdev->dev, PTR_ERR(gdev->rst_bus_disp),
				     "failed to get shared rst_bus_disp\n");

	if (gdev->rst_bus_disp) {
		ret = reset_control_deassert(gdev->rst_bus_disp);
		if (ret)
			return dev_err_probe(gdev->dev, ret,
					     "failed to deassert rst_bus_disp\n");
		gdev->reset_deasserted = true;
	}

	if (gdev->clk_bus_disp) {
		ret = clk_prepare_enable(gdev->clk_bus_disp);
		if (ret)
			return dev_err_probe(gdev->dev, ret,
					     "failed to enable clk_bus_disp\n");
	}

	if (gdev->clk_afbd) {
		ret = clk_prepare_enable(gdev->clk_afbd);
		if (ret) {
			if (gdev->clk_bus_disp)
				clk_disable_unprepare(gdev->clk_bus_disp);
			return dev_err_probe(gdev->dev, ret,
					     "failed to enable clk_afbd\n");
		}
	}

	gdev->clocks_enabled = true;
	return 0;
}

static void ge2d_disable_resources(struct ge2d_device *gdev)
{
	if (gdev->clk_afbd)
		clk_disable_unprepare(gdev->clk_afbd);
	if (gdev->clk_bus_disp)
		clk_disable_unprepare(gdev->clk_bus_disp);
	if (gdev->rst_bus_disp && gdev->reset_deasserted)
		reset_control_assert(gdev->rst_bus_disp);
	gdev->reset_deasserted = false;
	gdev->clocks_enabled = false;
}

static int ge2d_request_irqs(struct ge2d_device *gdev)
{
	int ret;

	gdev->irq_vblender = platform_get_irq_optional(gdev->pdev, 0);
	gdev->irq_afbd = platform_get_irq_optional(gdev->pdev, 3);

	if (!ge2d_enable_irqs) {
		dev_info(gdev->dev,
			 "IRQ request skipped (enable_irqs=0); discovered IRQ0=%d IRQ3=%d\n",
			 gdev->irq_vblender, gdev->irq_afbd);
		return 0;
	}

	if (gdev->irq_vblender >= 0) {
		ret = devm_request_threaded_irq(gdev->dev, gdev->irq_vblender,
						 ge2d_vblender_hardirq,
						 NULL,
						 IRQF_SHARED,
						 "ge2d-vblender",
						 gdev);
		if (ret)
			return dev_err_probe(gdev->dev, ret,
					     "failed to request vblender IRQ\n");
	}

	if (gdev->irq_afbd >= 0) {
		ret = devm_request_threaded_irq(gdev->dev, gdev->irq_afbd,
						 ge2d_afbd_hardirq,
						 NULL,
						 IRQF_SHARED,
						 "ge2d-afbd",
						 gdev);
		if (ret)
			return dev_err_probe(gdev->dev, ret,
					     "failed to request AFBD IRQ\n");
	}

	return 0;
}

static void ge2d_log_probe_summary(struct ge2d_device *gdev)
{
	dev_info(gdev->dev,
		 "panel=%ux%u type=%d protocol=%u dual_port=%u project_id=%u panel_node=%pOFn\n",
		 gdev->panel.width, gdev->panel.height, gdev->panel.panel_type,
		 gdev->panel.protocol, gdev->panel.dual_port,
		 gdev->panel.project_id, gdev->panel_np);
}

static int sunxi_ge2d_probe(struct platform_device *pdev)
{
	struct ge2d_device *gdev;
	int ret;

	gdev = devm_kzalloc(&pdev->dev, sizeof(*gdev), GFP_KERNEL);
	if (!gdev)
		return -ENOMEM;

	gdev->dev = &pdev->dev;
	gdev->pdev = pdev;
	mutex_init(&gdev->lock);
	platform_set_drvdata(pdev, gdev);

	/* Step 1: Parse DTS panel properties (stock: ge2d_drv_probe top) */
	ret = ge2d_parse_dt(gdev);
	if (ret)
		return dev_err_probe(&pdev->dev, ret,
				     "failed to parse tvtop panel data\n");

	/* Step 2: Map DTS MMIO resources */
	ret = ge2d_map_resources(gdev);
	if (ret)
		goto err_dt;

	/* Step 3: Enable clocks and deassert reset (stock: after IRQ setup) */
	ret = ge2d_enable_resources(gdev);
	if (ret)
		goto err_dt;

	/*
	 * Step 4: SVP character device — /dev/ge2d
	 * Stock init_svp() at 0x976c: __register_chrdev + class_create +
	 * device_create.  Called early in probe before IRQ setup.
	 */
	ret = ge2d_svp_init(gdev);
	if (ret)
		goto err_resources;

	/*
	 * Step 5: OSD interrupt init — programs vblender IRQ mask registers.
	 * Stock osd_interrupt_init() at 0xc440: writes 0xFFFFFFFF to
	 * afbd2_base+0x168, 0x10 to afbd2_base+0x16C.
	 */
	ret = osd_interrupt_init(gdev);
	if (ret)
		goto err_svp;

	/* Step 6: Vsync timestamp init — trivial memset (stock 0xc3ec) */
	ge2d_vsync_timestamp_init(gdev);

	/* Step 7: OSD frame init — fence context alloc (stock 0xe248) */
	ret = ge2d_osd_frame_init(gdev);
	if (ret)
		dev_warn(&pdev->dev, "ge2d_osd_frame_init failed: %d\n", ret);

	/* Step 8: Request IRQs (stock: platform_get_irq + devm_request_threaded_irq) */
	ret = ge2d_request_irqs(gdev);
	if (ret)
		goto err_svp;

	/* Step 9: Panel GPIO request (stock: get_panel_pin_info already done in DT) */
	ret = ge2d_panel_request_gpios(gdev);
	if (ret)
		goto err_svp;

	/* Step 10: Backlight init (stock: create_backlight_inst at 0x1073c) */
	ret = ge2d_backlight_init(gdev);
	if (ret)
		goto err_svp;

	/* Step 11: Framebuffer init (stock: ge2d_fb_init at 0xd838) */
	ret = ge2d_fbdev_init(gdev);
	if (ret)
		goto err_backlight;

	/* Step 12: PM runtime */
	pm_runtime_set_active(&pdev->dev);
	pm_runtime_enable(&pdev->dev);

	/* Step 13: Register with tvtop (stock: sunxi_tvtop_client_register) */
	ret = sunxi_tvtop_client_register(&pdev->dev);
	if (!ret)
		gdev->tvtop_registered = true;
	else
		dev_warn(&pdev->dev, "sunxi_tvtop_client_register failed: %d\n", ret);

	/*
	 * Step 14: OSD resume init — schedules delayed work for OSD plane
	 * register programming (stock osd_resume_init at 0xff00).
	 */
	ret = osd_resume_init(gdev);
	if (ret)
		dev_warn(&pdev->dev, "osd_resume_init failed: %d\n", ret);

	/* Step 15: LVDS watchdog thread (stock: kthread_create lvds_reset_thread) */
	ge2d_panel_maybe_start_lvds_watchdog(gdev);

	/* Step 16: DLPC3435 companion init (stock: via work queue) */
	ret = ge2d_dlpc3435_schedule_init(gdev);
	if (ret)
		goto err_pm;

	ge2d_log_probe_summary(gdev);
	dev_info(&pdev->dev, "GE2D probe complete\n");
	return 0;

err_pm:
	pm_runtime_disable(&pdev->dev);
err_backlight:
	ge2d_backlight_exit(gdev);
err_svp:
	ge2d_svp_exit(gdev);
err_resources:
	ge2d_disable_resources(gdev);
err_dt:
	ge2d_dt_cleanup(gdev);
	return ret;
}

static void sunxi_ge2d_remove(struct platform_device *pdev)
{
	struct ge2d_device *gdev = platform_get_drvdata(pdev);

	/*
	 * Stock ge2d_drv_remove at 0x79f4 does:
	 *   1. pm_runtime_disable
	 *   2. cancel_delayed_work_sync
	 *   3. ge2d_dmabuf_cache_exit
	 *   4. devm_free_irq (x2)
	 *   5. ge2d_fb_exit (framebuffer_release only)
	 *
	 * Stock does NOT:
	 *   - disable clocks or assert resets (display pipeline stays alive)
	 *   - power down backlight (PB5 must stay HIGH for fan)
	 *   - release GPIOs (panel power must stay on)
	 *   - call destroy_backlight_inst (only done in suspend)
	 */
	ge2d_dlpc3435_cancel_init(gdev);
	ge2d_fbdev_exit(gdev);
	ge2d_svp_exit(gdev);
	pm_runtime_disable(&pdev->dev);
	/* Do NOT call ge2d_disable_resources -- display pipeline must stay alive */
	/* Do NOT call ge2d_backlight_exit -- PB5 LOW kills fan */
	ge2d_dt_cleanup(gdev);
}

static int sunxi_ge2d_runtime_suspend(struct device *dev)
{
	return 0;
}

static int sunxi_ge2d_runtime_resume(struct device *dev)
{
	return 0;
}

static const struct dev_pm_ops sunxi_ge2d_pm_ops = {
	SET_RUNTIME_PM_OPS(sunxi_ge2d_runtime_suspend,
			   sunxi_ge2d_runtime_resume, NULL)
};

static const struct of_device_id sunxi_ge2d_of_match[] = {
	{ .compatible = "trix,ge2d" },
	{ }
};
MODULE_DEVICE_TABLE(of, sunxi_ge2d_of_match);

static struct platform_driver sunxi_ge2d_driver = {
	.probe = sunxi_ge2d_probe,
	.remove = sunxi_ge2d_remove,
	.driver = {
		.name = GE2D_NAME,
		.of_match_table = sunxi_ge2d_of_match,
		.pm = pm_ptr(&sunxi_ge2d_pm_ops),
	},
};
module_platform_driver(sunxi_ge2d_driver);

MODULE_DESCRIPTION("Allwinner H713 GE2D display controller (safe Phase-1 port)");
MODULE_AUTHOR("OpenCode");
MODULE_LICENSE("GPL");
