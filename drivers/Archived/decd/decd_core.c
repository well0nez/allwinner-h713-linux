// SPDX-License-Identifier: GPL-2.0

#include <linux/cdev.h>
#include <linux/clk.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/reset.h>
#include <linux/slab.h>

#include "decd_types.h"

struct dec_device *g_dec;
struct dec_video_frame *last_frame;

static int dec_runtime_suspend(struct device *dev)
{
	return dec_disable(dev_get_drvdata(dev));
}

static int dec_runtime_resume(struct device *dev)
{
	return dec_enable(dev_get_drvdata(dev));
}

static const struct dev_pm_ops dec_pm_ops = {
	RUNTIME_PM_OPS(dec_runtime_suspend, dec_runtime_resume, NULL)
};

static int dec_open(struct inode *inode, struct file *file)
{
	file->private_data = g_dec;
	return 0;
}

static int dec_release_file(struct inode *inode, struct file *file)
{
	return 0;
}

static ssize_t dec_read_file(struct file *file, char __user *buf, size_t len,
			     loff_t *ppos)
{
	struct dec_device *dec = file->private_data;
	u64 ts;

	if (len < sizeof(ts))
		return -EINVAL;
	if (dec_vsync_timestamp_get(dec, &ts))
		return -EAGAIN;
	if (copy_to_user(buf, &ts, sizeof(ts)))
		return -EFAULT;
	return sizeof(ts);
}

static __poll_t dec_poll_file(struct file *file, poll_table *wait)
{
	return dec_event_poll(file->private_data, file, wait);
}

long dec_ioctl_file(struct file *file, unsigned int cmd, unsigned long arg);

static const struct file_operations dec_fops = {
	.owner = THIS_MODULE,
	.open = dec_open,
	.release = dec_release_file,
	.read = dec_read_file,
	.poll = dec_poll_file,
	.unlocked_ioctl = dec_ioctl_file,
	.llseek = noop_llseek,
};

static DEVICE_ATTR(info, 0444, dec_show_info, NULL);
static DEVICE_ATTR(frame_manager, 0444, dec_show_frame_manager, NULL);

static struct attribute *dec_attrs[] = {
	&dev_attr_info.attr,
	&dev_attr_frame_manager.attr,
	NULL,
};

static const struct attribute_group dec_attr_group = {
	.attrs = dec_attrs,
};

int dec_init(struct dec_device *dec)
{
	struct device *dev = dec->dev;

	dec->regs = devm_kzalloc(dev, sizeof(*dec->regs), GFP_KERNEL);
	dec->debug = devm_kzalloc(dev, sizeof(*dec->debug), GFP_KERNEL);
	dec->vsync = devm_kzalloc(dev, sizeof(*dec->vsync), GFP_KERNEL);
	if (!dec->regs || !dec->debug || !dec->vsync)
		return -ENOMEM;

	dec->regs->top = of_iomap(dev->of_node, 0);
	dec->regs->afbd = of_iomap(dev->of_node, 1);
	if (!dec->regs->top || !dec->regs->afbd)
		return -ENOMEM;
	dec->regs->workaround = dec->regs->afbd + 0x60;
	dec->debug->reg_base = dec->regs->afbd;

	dec->irq = irq_of_parse_and_map(dev->of_node, 0);
	if (!dec->irq)
		return -EINVAL;

	if (of_property_read_u32(dev->of_node, "clock-frequency", &dec->clk_rate))
		dec->clk_rate = DECD_DEFAULT_CLK_RATE;

	dec->clk_afbd = devm_clk_get(dev, "clk_afbd");
	if (IS_ERR(dec->clk_afbd))
		return PTR_ERR(dec->clk_afbd);
	dec->clk_bus_disp = devm_clk_get(dev, "clk_bus_disp");
	if (IS_ERR(dec->clk_bus_disp))
		return PTR_ERR(dec->clk_bus_disp);
	dec->rst_bus_disp = devm_reset_control_get_shared(dev, "rst_bus_disp");
	if (IS_ERR(dec->rst_bus_disp))
		return PTR_ERR(dec->rst_bus_disp);

	dec->fence_ctx = dec_fence_context_alloc("dec");
	if (IS_ERR(dec->fence_ctx))
		return PTR_ERR(dec->fence_ctx);
	dec_debug_init(dec);
	dec_debug_set_register_base((int)(uintptr_t)dec->regs->afbd);
	video_info_memory_block_init(dev);

	spin_lock_init(&dec->vsync->lock);
	mutex_init(&dec->lock);
	init_waitqueue_head(&dec->event_wait);
	return 0;
}

void dec_exit(struct dec_device *dec)
{
	dec_disable(dec);
	if (dec->regs) {
		if (dec->regs->top)
			iounmap(dec->regs->top);
		if (dec->regs->afbd)
			iounmap(dec->regs->afbd);
	}
	video_info_memory_block_exit();
	kfree(dec->fence_ctx);
}

static int dec_probe(struct platform_device *pdev)
{
	struct dec_device *dec;
	int ret;

	dec = devm_kzalloc(&pdev->dev, sizeof(*dec), GFP_KERNEL);
	if (!dec)
		return -ENOMEM;
	dec->dev = &pdev->dev;
	dec->pdev = pdev;
	platform_set_drvdata(pdev, dec);

	ret = dec_init(dec);
	if (ret)
		return ret;

	ret = alloc_chrdev_region(&dec->devt, 0, 1, DECD_NAME);
	if (ret)
		goto err_exit;
	cdev_init(&dec->cdev, &dec_fops);
	dec->cdev.owner = THIS_MODULE;
	ret = cdev_add(&dec->cdev, dec->devt, 1);
	if (ret)
		goto err_chr;
	dec->class = class_create(DECD_CLASS_NAME);
	if (IS_ERR(dec->class)) {
		ret = PTR_ERR(dec->class);
		goto err_cdev;
	}
	dec->chrdev = device_create(dec->class, NULL, dec->devt, NULL, DECD_NAME);
	if (IS_ERR(dec->chrdev)) {
		ret = PTR_ERR(dec->chrdev);
		goto err_class;
	}
	ret = devm_request_irq(&pdev->dev, dec->irq, dec_vsync_handler, 0,
			      DECD_NAME, dec);
	if (ret)
		goto err_dev;
	disable_irq(dec->irq);
	ret = sysfs_create_group(&pdev->dev.kobj, &dec_attr_group);
	if (ret)
		goto err_dev;
	dec->attr_group = (struct attribute_group *)&dec_attr_group;
	pm_runtime_enable(&pdev->dev);
	ret = sunxi_tvtop_client_register(&pdev->dev);
	if (ret)
		goto err_pm;
	g_dec = dec;
	dev_info(&pdev->dev, "reconstructed decd probed\n");
	return 0;
err_pm:
	pm_runtime_disable(&pdev->dev);
err_dev:
	if (dec->attr_group)
		sysfs_remove_group(&pdev->dev.kobj, dec->attr_group);
	device_destroy(dec->class, dec->devt);
err_class:
	class_destroy(dec->class);
err_cdev:
	cdev_del(&dec->cdev);
err_chr:
	unregister_chrdev_region(dec->devt, 1);
err_exit:
	dec_exit(dec);
	return ret;
}

static void dec_remove(struct platform_device *pdev)
{
	struct dec_device *dec = platform_get_drvdata(pdev);

	pm_runtime_disable(&pdev->dev);
	if (dec->attr_group)
		sysfs_remove_group(&pdev->dev.kobj, dec->attr_group);
	device_destroy(dec->class, dec->devt);
	class_destroy(dec->class);
	cdev_del(&dec->cdev);
	unregister_chrdev_region(dec->devt, 1);
	dec_exit(dec);
}

static const struct of_device_id dec_of_match[] = {
	{ .compatible = "allwinner,sunxi-dec" },
	{ }
};
MODULE_DEVICE_TABLE(of, dec_of_match);

static struct platform_driver dec_driver = {
	.probe = dec_probe,
	.remove = dec_remove,
	.driver = {
		.name = DECD_NAME,
		.of_match_table = dec_of_match,
		.pm = &dec_pm_ops,
	},
};

module_platform_driver(dec_driver);

MODULE_IMPORT_NS("DMA_BUF");
MODULE_DESCRIPTION("HY310 decd reconstruction scaffold (modular)");
MODULE_LICENSE("GPL");
