// SPDX-License-Identifier: GPL-2.0-only

#include <linux/bitops.h>
#include <linux/clk.h>
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/interrupt.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "audio_bridge.h"

static int index = -1;
module_param(index, int, 0444);
MODULE_PARM_DESC(index, "Index value for trident soundcard.");

static char *id = "snd_trid";
module_param(id, charp, 0444);
MODULE_PARM_DESC(id, "ID string for trident soundcard.");

static bool enable = true;
module_param(enable, bool, 0444);
MODULE_PARM_DESC(enable, "Enable this trident soundcard.");

static unsigned int pcm_substreams = 4;
module_param(pcm_substreams, uint, 0444);
MODULE_PARM_DESC(pcm_substreams,
		 "PCM substreams count exposed by the trident driver.");

static void trid_suspend_streams(struct trid_audio_bridge *bridge);
static int trid_resume_streams(struct trid_audio_bridge *bridge);

static void __iomem *trid_translate_reg(struct trid_audio_bridge *bridge,
					phys_addr_t reg)
{
	if (bridge->audif_base && reg >= TRID_AUDIF_PHYS_BASE &&
	    reg < TRID_AUDIF_PHYS_BASE + TRID_AUDIF_MMIO_SIZE)
		return bridge->audif_base + (reg - TRID_AUDIF_PHYS_BASE);

	if (bridge->audbrg_base && reg >= TRID_AUDBRG_PHYS_BASE &&
	    reg < TRID_AUDBRG_PHYS_BASE + TRID_AUDBRG_MMIO_SIZE)
		return bridge->audbrg_base + (reg - TRID_AUDBRG_PHYS_BASE);

	if (bridge->audio_top_clk_base && reg >= TRID_AUDIO_TOP_CLK_PHYS_BASE &&
	    reg < TRID_AUDIO_TOP_CLK_PHYS_BASE + TRID_AUDIO_TOP_CLK_MMIO_SIZE)
		return bridge->audio_top_clk_base +
		       (reg - TRID_AUDIO_TOP_CLK_PHYS_BASE);

	if (bridge->high_addr_ctl_base && reg == TRID_HIGH_ADDR_CTL_PHYS)
		return bridge->high_addr_ctl_base;

	if (bridge->sw_reg1_base && reg == TRID_SW_REG1_PHYS)
		return bridge->sw_reg1_base;

	if (bridge->sw_reg2_base && reg == TRID_SW_REG2_PHYS)
		return bridge->sw_reg2_base;

	if (bridge->arc_src_base && reg == TRID_ARC_SRC_PHYS)
		return bridge->arc_src_base;

	if (bridge->msp_owa_out_base && reg == TRID_MSP_OWA_OUT_SRC_PHYS)
		return bridge->msp_owa_out_base;

	return NULL;
}

u32 trid_reg_read(struct trid_audio_bridge *bridge, phys_addr_t reg)
{
	void __iomem *addr = trid_translate_reg(bridge, reg);

	if (!addr)
		return 0;

	return readl(addr);
}
EXPORT_SYMBOL_GPL(trid_reg_read);

void trid_reg_write(struct trid_audio_bridge *bridge, phys_addr_t reg, u32 val)
{
	void __iomem *addr = trid_translate_reg(bridge, reg);

	if (!addr)
		return;

	writel(val, addr);
}
EXPORT_SYMBOL_GPL(trid_reg_write);

void trid_reg_update_bits(struct trid_audio_bridge *bridge, phys_addr_t reg,
			  u32 mask, u32 val)
{
	void __iomem *addr = trid_translate_reg(bridge, reg);
	unsigned long flags;
	u32 tmp;

	if (!addr)
		return;

	spin_lock_irqsave(&bridge->reg_lock, flags);
	tmp = readl(addr);
	tmp = (tmp & ~mask) | (val & mask);
	writel(tmp, addr);
	spin_unlock_irqrestore(&bridge->reg_lock, flags);
}
EXPORT_SYMBOL_GPL(trid_reg_update_bits);

static int trid_misc_open(struct inode *inode, struct file *file)
{
	struct miscdevice *misc = file->private_data;
	struct trid_audio_bridge *bridge;

	bridge = container_of(misc, struct trid_audio_bridge, miscdev);
	file->private_data = bridge;
	return nonseekable_open(inode, file);
}

static long trid_misc_ioctl(struct file *file, unsigned int cmd,
			    unsigned long arg)
{
	struct trid_audio_bridge *bridge = file->private_data;
	unsigned int state;
	int ret = 0;

	if (cmd != TRID_IOCTL_PM)
		return -ENOTTY;

	if (copy_from_user(&state, (void __user *)arg, sizeof(state)))
		return -EFAULT;

	mutex_lock(&bridge->lock);
	switch (state) {
	case TRID_PM_SUSPEND:
		trid_suspend_streams(bridge);
		trid_audioio_exit(bridge);
		bridge->pm_error = false;
		break;
	case TRID_PM_RESUME:
		ret = trid_audioio_init(bridge);
		if (!ret)
			ret = trid_resume_streams(bridge);
		bridge->pm_error = ret < 0;
		break;
	default:
		ret = -EINVAL;
		break;
	}
	mutex_unlock(&bridge->lock);

	return ret;
}

static int trid_misc_release(struct inode *inode, struct file *file)
{
	return 0;
}

static const struct file_operations trid_misc_fops = {
	.owner		 = THIS_MODULE,
	.open		 = trid_misc_open,
	.release	 = trid_misc_release,
	.unlocked_ioctl = trid_misc_ioctl,
	.llseek		 = noop_llseek,
};

static int trid_map_optional_resource(struct trid_audio_bridge *bridge,
				      unsigned int index)
{
	struct resource *res;

	res = platform_get_resource(bridge->pdev, IORESOURCE_MEM, index);
	if (!res)
		return 0;

	bridge->logical_node_size = resource_size(res);
	bridge->logical_node_base = devm_ioremap_resource(bridge->dev, res);
	if (IS_ERR(bridge->logical_node_base))
		return PTR_ERR(bridge->logical_node_base);

	return 0;
}

static int trid_map_aux_windows(struct trid_audio_bridge *bridge)
{
	bridge->audif_base = devm_ioremap(bridge->dev, TRID_AUDIF_PHYS_BASE,
					 TRID_AUDIF_MMIO_SIZE);
	bridge->audbrg_base = devm_ioremap(bridge->dev, TRID_AUDBRG_PHYS_BASE,
					  TRID_AUDBRG_MMIO_SIZE);
	bridge->audio_top_clk_base = devm_ioremap(bridge->dev,
					  TRID_AUDIO_TOP_CLK_PHYS_BASE,
					  TRID_AUDIO_TOP_CLK_MMIO_SIZE);
	bridge->high_addr_ctl_base = devm_ioremap(bridge->dev,
					 TRID_HIGH_ADDR_CTL_PHYS, 4);
	bridge->sw_reg1_base = devm_ioremap(bridge->dev, TRID_SW_REG1_PHYS, 4);
	bridge->sw_reg2_base = devm_ioremap(bridge->dev, TRID_SW_REG2_PHYS, 4);
	bridge->arc_src_base = devm_ioremap(bridge->dev, TRID_ARC_SRC_PHYS, 4);
	bridge->msp_owa_out_base = devm_ioremap(bridge->dev,
					 TRID_MSP_OWA_OUT_SRC_PHYS, 4);

	if (!bridge->audif_base || !bridge->audbrg_base ||
	    !bridge->audio_top_clk_base || !bridge->high_addr_ctl_base ||
	    !bridge->sw_reg1_base || !bridge->sw_reg2_base ||
	    !bridge->arc_src_base || !bridge->msp_owa_out_base)
		return -ENOMEM;

	return 0;
}

static void trid_suspend_stream_array(struct trid_audio_bridge *bridge,
				     struct trid_stream_state *streams,
				     unsigned int count)
{
	unsigned int i;

	for (i = 0; i < count; i++) {
		if (!streams[i].substream)
			continue;

		streams[i].resume_running = streams[i].running;
		if (!streams[i].running)
			continue;

		timer_delete_sync(&streams[i].timer);
		if (streams[i].capture)
			trid_ostream_stop(bridge, streams[i].hw_stream);
		else
			trid_istream_stop(bridge, streams[i].hw_stream);
		streams[i].running = false;
	}
}

static int trid_resume_stream_array(struct trid_audio_bridge *bridge,
				    struct trid_stream_state *streams,
				    unsigned int count)
{
	unsigned int i;
	int ret;

	for (i = 0; i < count; i++) {
		if (!streams[i].substream)
			continue;

		ret = trid_iface_prepare(bridge, streams[i].iface, streams[i].rate,
					 streams[i].channels,
					 streams[i].sample_bits,
					 streams[i].period_bytes, true);
		if (ret)
			return ret;

		if (!streams[i].resume_running)
			continue;

		if (streams[i].capture)
			ret = trid_ostream_start(bridge, streams[i].hw_stream);
		else
			ret = trid_istream_start(bridge, streams[i].hw_stream);
		if (ret)
			return ret;

		streams[i].running = true;
		mod_timer(&streams[i].timer, jiffies + 1);
	}

	return 0;
}

static void trid_suspend_streams(struct trid_audio_bridge *bridge)
{
	trid_suspend_stream_array(bridge, bridge->playback, TRID_MAX_PCMS);
	trid_suspend_stream_array(bridge, bridge->capture, TRID_MAX_OSTREAMS);
}

static int trid_resume_streams(struct trid_audio_bridge *bridge)
{
	int ret;

	ret = trid_resume_stream_array(bridge, bridge->playback, TRID_MAX_PCMS);
	if (ret)
		return ret;

	return trid_resume_stream_array(bridge, bridge->capture,
					TRID_MAX_OSTREAMS);
}

static int trid_probe(struct platform_device *pdev)
{
	struct trid_audio_bridge *bridge;
	int ret;

	if (!enable)
		return -ENODEV;

	bridge = devm_kzalloc(&pdev->dev, sizeof(*bridge), GFP_KERNEL);
	if (!bridge)
		return -ENOMEM;

	bridge->dev = &pdev->dev;
	bridge->pdev = pdev;
	bridge->pcm_substreams = pcm_substreams;
	spin_lock_init(&bridge->reg_lock);
	mutex_init(&bridge->lock);
	platform_set_drvdata(pdev, bridge);

	ret = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
	if (ret)
		return ret;

	ret = trid_map_optional_resource(bridge, 0);
	if (ret)
		return ret;

	/*
	 * Step 9: Enable audio clocks before any MMIO access to 0x0614xxxx.
	 * Without these clocks the MIPS-bus domain is dead and register reads
	 * return 0. Clocks are optional — if not in DTS the driver still loads
	 * (user must enable clocks manually via tvfe sysfs).
	 */
	bridge->clk_audio_cpu = devm_clk_get_optional(&pdev->dev, "audio_cpu");
	bridge->clk_audio_umac = devm_clk_get_optional(&pdev->dev, "audio_umac");
	bridge->clk_audio_ihb = devm_clk_get_optional(&pdev->dev, "audio_ihb");

	if (!IS_ERR_OR_NULL(bridge->clk_audio_cpu))
		clk_prepare_enable(bridge->clk_audio_cpu);
	if (!IS_ERR_OR_NULL(bridge->clk_audio_umac))
		clk_prepare_enable(bridge->clk_audio_umac);
	if (!IS_ERR_OR_NULL(bridge->clk_audio_ihb))
		clk_prepare_enable(bridge->clk_audio_ihb);

	ret = trid_map_aux_windows(bridge);
	if (ret)
		return ret;

	bridge->audbrg_irq = platform_get_irq(pdev, 0);
	if (bridge->audbrg_irq < 0)
		return bridge->audbrg_irq;

	bridge->audif_irq = platform_get_irq(pdev, 1);
	if (bridge->audif_irq < 0)
		return bridge->audif_irq;

	ret = devm_request_threaded_irq(&pdev->dev, bridge->audbrg_irq, NULL,
					trid_audbrg_irq_thread,
					IRQF_ONESHOT,
					"audio bridge irq", bridge);
	if (ret)
		return ret;

	ret = devm_request_threaded_irq(&pdev->dev, bridge->audif_irq, NULL,
					trid_audif_irq_thread,
					IRQF_ONESHOT,
					"abp dtv irq", bridge);
	if (ret)
		return ret;

	ret = trid_mem_init(bridge);
	if (ret)
		return ret;

	ret = trid_audioio_init(bridge);
	if (ret)
		goto err_mem;

	ret = trid_register_pcm(bridge, index, id);
	if (ret)
		goto err_audioio;

	bridge->miscdev.minor = MISC_DYNAMIC_MINOR;
	bridge->miscdev.name = TRID_MISCDEV_NAME;
	bridge->miscdev.fops = &trid_misc_fops;
	bridge->miscdev.parent = &pdev->dev;

	ret = misc_register(&bridge->miscdev);
	if (ret)
		goto err_pcm;

	dev_info(&pdev->dev,
		 "Trident audio bridge probed: audbrg=%d audif=%d shared=%zu bytes\n",
		 bridge->audbrg_irq, bridge->audif_irq, (size_t)TRID_SHARED_DMA_BYTES);
	return 0;

err_pcm:
	trid_unregister_pcm(bridge);
err_audioio:
	trid_audioio_exit(bridge);
err_mem:
	trid_mem_exit(bridge);
	return ret;
}

static void trid_remove(struct platform_device *pdev)
{
	struct trid_audio_bridge *bridge = platform_get_drvdata(pdev);

	misc_deregister(&bridge->miscdev);
	trid_unregister_pcm(bridge);
	trid_audioio_exit(bridge);
	trid_mem_exit(bridge);

	if (!IS_ERR_OR_NULL(bridge->clk_audio_ihb))
		clk_disable_unprepare(bridge->clk_audio_ihb);
	if (!IS_ERR_OR_NULL(bridge->clk_audio_umac))
		clk_disable_unprepare(bridge->clk_audio_umac);
	if (!IS_ERR_OR_NULL(bridge->clk_audio_cpu))
		clk_disable_unprepare(bridge->clk_audio_cpu);
}

static int trid_suspend(struct device *dev)
{
	struct trid_audio_bridge *bridge = dev_get_drvdata(dev);

	mutex_lock(&bridge->lock);
	trid_suspend_streams(bridge);
	trid_audioio_exit(bridge);
	bridge->pm_error = false;
	mutex_unlock(&bridge->lock);
	return 0;
}

static int trid_resume(struct device *dev)
{
	struct trid_audio_bridge *bridge = dev_get_drvdata(dev);
	int ret;

	mutex_lock(&bridge->lock);
	ret = trid_audioio_init(bridge);
	if (!ret)
		ret = trid_resume_streams(bridge);
	bridge->pm_error = ret < 0;
	mutex_unlock(&bridge->lock);
	return ret;
}

static const struct dev_pm_ops trid_pm_ops = {
	.suspend = trid_suspend,
	.resume = trid_resume,
};

static const struct of_device_id trid_of_match[] = {
	{ .compatible = "vs,trid-audio-bridge" },
	{ }
};
MODULE_DEVICE_TABLE(of, trid_of_match);

static struct platform_driver trid_platform_driver = {
	.probe = trid_probe,
	.remove = trid_remove,
	.driver = {
		.name = "snd_trid",
		.of_match_table = trid_of_match,
		.pm = &trid_pm_ops,
	},
};
module_platform_driver(trid_platform_driver);

MODULE_DESCRIPTION("HY310 Trident audio bridge driver");
MODULE_AUTHOR("well0nez");
MODULE_LICENSE("GPL");
