// SPDX-License-Identifier: GPL-2.0+
/*
 * Allwinner H713 AV1 Hardware Decoder Driver
 *
 * Copyright (C) 2025 HY300 Linux Porting Project
 *
 * This driver implements V4L2 stateless decoder support for the
 * Allwinner H713 SoC AV1 hardware decoder.
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/pm_runtime.h>
#include <linux/slab.h>
#include <linux/clk.h>
#include <linux/reset.h>
#include <linux/interrupt.h>
#include <linux/iommu.h>
#include <linux/dma-mapping.h>
#include <media/v4l2-device.h>
#include <media/v4l2-ioctl.h>
#include <media/v4l2-mem2mem.h>
#include <media/videobuf2-dma-contig.h>

#include "sun50i-h713-av1.h"

/* Global metrics instance */
/**
 * sun50i_av1_irq_handler - AV1 hardware interrupt handler
 * @irq: IRQ number
 * @priv: Device context
 *
 * Returns: IRQ_HANDLED if interrupt was handled, IRQ_NONE otherwise
 */
irqreturn_t sun50i_av1_irq_handler(int irq, void *priv)
{
	struct sun50i_av1_dev *dev = priv;
	u32 status;
	bool handled = false;
	
	/* Read interrupt status */
	status = av1_read(dev, AV1_REG_INT_STATUS);
	if (!status)
		return IRQ_NONE;
	
	/* Clear interrupts */
	av1_write(dev, AV1_REG_INT_STATUS, status);
	
	dev_dbg(dev->dev, "AV1 IRQ: status=0x%08x\n", status);
	
	/* Handle decode completion */
	if (status & AV1_INT_DECODE_DONE) {
		struct sun50i_av1_ctx *ctx = NULL;
		struct vb2_v4l2_buffer *src_buf, *dst_buf;
		ktime_t decode_time;
		
		dev_dbg(dev->dev, "Decode completion interrupt\n");
		
		/* Find active context */
		if (dev->m2m_dev) {
			ctx = v4l2_m2m_get_curr_priv(dev->m2m_dev);
		}
		
		if (ctx && ctx->m2m_ctx) {
			/* Calculate decode time */
			decode_time = ktime_sub(ktime_get(), ctx->decode_start_time);
			av1_metrics.total_decode_time_us += ktime_to_us(decode_time);
			
			/* Get buffers */
			src_buf = v4l2_m2m_src_buf_remove(ctx->m2m_ctx);
			dst_buf = v4l2_m2m_dst_buf_remove(ctx->m2m_ctx);
			
			if (src_buf && dst_buf) {
				/* Copy timestamp */
				dst_buf->vb2_buf.timestamp = src_buf->vb2_buf.timestamp;
				
				/* Mark buffers as done */
				v4l2_m2m_buf_done(src_buf, VB2_BUF_STATE_DONE);
				v4l2_m2m_buf_done(dst_buf, VB2_BUF_STATE_DONE);
				
				/* Update metrics */
				atomic64_inc(&av1_metrics.frames_decoded);
			}
			
			/* Schedule next job */
			v4l2_m2m_job_finish(dev->m2m_dev, ctx->m2m_ctx);
		}
		
		handled = true;
	}
	
	/* Handle decode errors */
	if (status & AV1_INT_DECODE_ERROR) {
		struct sun50i_av1_ctx *ctx = NULL;
		struct vb2_v4l2_buffer *src_buf, *dst_buf;
		
		dev_err(dev->dev, "Decode error interrupt\n");
		
		/* Find active context */
		if (dev->m2m_dev) {
			ctx = v4l2_m2m_get_curr_priv(dev->m2m_dev);
		}
		
		if (ctx && ctx->m2m_ctx) {
			/* Get buffers */
			src_buf = v4l2_m2m_src_buf_remove(ctx->m2m_ctx);
			dst_buf = v4l2_m2m_dst_buf_remove(ctx->m2m_ctx);
			
			if (src_buf && dst_buf) {
				/* Mark buffers as error */
				v4l2_m2m_buf_done(src_buf, VB2_BUF_STATE_ERROR);
				v4l2_m2m_buf_done(dst_buf, VB2_BUF_STATE_ERROR);
				
				/* Update error metrics */
				atomic64_inc(&av1_metrics.decode_errors);
			}
			
			/* Schedule next job */
			v4l2_m2m_job_finish(dev->m2m_dev, ctx->m2m_ctx);
		}
		
		handled = true;
	}
	
	/* Handle frame ready */
	if (status & AV1_INT_FRAME_READY) {
		dev_dbg(dev->dev, "Frame ready interrupt\n");
		/* Signal completion for waiting threads */
		complete(&dev->decode_complete);
		handled = true;
	}
	
	return handled ? IRQ_HANDLED : IRQ_NONE;
}
struct av1_metrics av1_metrics = {
	.frames_decoded = ATOMIC64_INIT(0),
	.decode_errors = ATOMIC64_INIT(0),
	.hw_resets = ATOMIC64_INIT(0),
	.current_sessions = ATOMIC_INIT(0),
	.total_decode_time_us = 0,
};

static const struct of_device_id sun50i_av1_of_match[] = {
	{
		.compatible = "allwinner,sun50i-h713-av1-decoder",
	},
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, sun50i_av1_of_match);

static int sun50i_av1_probe(struct platform_device *pdev)
{
	struct sun50i_av1_dev *dev;
	struct resource *res;
	int ret;

	dev_info(&pdev->dev, "Probing H713 AV1 decoder driver\n");

	dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
	if (!dev)
		return -ENOMEM;

	dev->pdev = pdev;
	dev->dev = &pdev->dev;
	platform_set_drvdata(pdev, dev);

	mutex_init(&dev->dev_mutex);
	init_completion(&dev->decode_complete);
	atomic_set(&dev->num_inst, 0);

	/* Get memory resource */
	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	dev->regs = devm_ioremap_resource(&pdev->dev, res);
	if (IS_ERR(dev->regs)) {
		dev_err(&pdev->dev, "Failed to map registers\n");
		return PTR_ERR(dev->regs);
	}

	/* Get interrupt */
	dev->irq = platform_get_irq(pdev, 0);
	if (dev->irq < 0) {
		dev_err(&pdev->dev, "Failed to get IRQ\n");
		return dev->irq;
	}

	ret = devm_request_irq(&pdev->dev, dev->irq, sun50i_av1_irq_handler,
			       0, dev_name(&pdev->dev), dev);
	if (ret) {
		dev_err(&pdev->dev, "Failed to request IRQ %d\n", dev->irq);
		return ret;
	}

	/* Get clocks */
	dev->bus_clk = devm_clk_get(&pdev->dev, "bus");
	if (IS_ERR(dev->bus_clk)) {
		dev_err(&pdev->dev, "Failed to get bus clock\n");
		return PTR_ERR(dev->bus_clk);
	}

	dev->mbus_clk = devm_clk_get(&pdev->dev, "mbus");
	if (IS_ERR(dev->mbus_clk)) {
		dev_err(&pdev->dev, "Failed to get mbus clock\n");
		return PTR_ERR(dev->mbus_clk);
	}

	/* Get reset control */
	dev->reset = devm_reset_control_get_exclusive(&pdev->dev, NULL);
	if (IS_ERR(dev->reset)) {
		dev_err(&pdev->dev, "Failed to get reset control\n");
		return PTR_ERR(dev->reset);
	}

	/* Initialize V4L2 device */
	ret = v4l2_device_register(&pdev->dev, &dev->v4l2_dev);
	if (ret) {
		dev_err(&pdev->dev, "Failed to register V4L2 device\n");
		return ret;
	}

	/* Set up DMA configuration */
	dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
	dev->dma_dev = &pdev->dev;

	/* Initialize hardware */
	ret = sun50i_av1_hw_init(dev);
	if (ret) {
		dev_err(&pdev->dev, "Failed to initialize hardware\n");
		goto err_v4l2_cleanup;
	}

	/* Initialize V4L2 interface */
	ret = sun50i_av1_v4l2_init(dev);
	if (ret) {
		dev_err(&pdev->dev, "Failed to initialize V4L2 interface\n");
		goto err_hw_cleanup;
	}

	/* Enable power management */
	pm_runtime_enable(&pdev->dev);
	pm_runtime_get_sync(&pdev->dev);

	/* Initialize debug interface */
	sun50i_av1_debugfs_init(dev);

	dev_info(&pdev->dev, "H713 AV1 decoder registered successfully\n");
	return 0;

err_hw_cleanup:
	sun50i_av1_hw_deinit(dev);
err_v4l2_cleanup:
	v4l2_device_unregister(&dev->v4l2_dev);
	return ret;
}

static int sun50i_av1_remove(struct platform_device *pdev)
{
	struct sun50i_av1_dev *dev = platform_get_drvdata(pdev);

	dev_info(&pdev->dev, "Removing H713 AV1 decoder driver\n");

	/* Cleanup debug interface */
	sun50i_av1_debugfs_cleanup(dev);

	/* Disable power management */
	pm_runtime_put_sync(&pdev->dev);
	pm_runtime_disable(&pdev->dev);

	/* Cleanup V4L2 interface */
	sun50i_av1_v4l2_cleanup(dev);

	/* Cleanup hardware */
	sun50i_av1_hw_deinit(dev);

	/* Unregister V4L2 device */
	v4l2_device_unregister(&dev->v4l2_dev);

	dev_info(&pdev->dev, "H713 AV1 decoder removed successfully\n");
	return 0;
}

static int __maybe_unused sun50i_av1_suspend(struct device *dev)
{
	struct sun50i_av1_dev *av1_dev = dev_get_drvdata(dev);

	mutex_lock(&av1_dev->dev_mutex);
	av1_dev->suspended = true;
	sun50i_av1_hw_disable(av1_dev);
	mutex_unlock(&av1_dev->dev_mutex);

	return 0;
}

static int __maybe_unused sun50i_av1_resume(struct device *dev)
{
	struct sun50i_av1_dev *av1_dev = dev_get_drvdata(dev);
	int ret;

	mutex_lock(&av1_dev->dev_mutex);
	ret = sun50i_av1_hw_enable(av1_dev);
	if (ret)
		dev_err(dev, "Failed to re-enable hardware\n");
	else
		av1_dev->suspended = false;
	mutex_unlock(&av1_dev->dev_mutex);

	return ret;
}

static const struct dev_pm_ops sun50i_av1_pm_ops = {
	SET_RUNTIME_PM_OPS(sun50i_av1_suspend, sun50i_av1_resume, NULL)
	SET_SYSTEM_SLEEP_PM_OPS(sun50i_av1_suspend, sun50i_av1_resume)
};

static struct platform_driver sun50i_av1_driver = {
	.probe		= sun50i_av1_probe,
	.remove		= sun50i_av1_remove,
	.driver		= {
		.name		= "sun50i-h713-av1",
		.of_match_table	= sun50i_av1_of_match,
		.pm		= &sun50i_av1_pm_ops,
	},
};

module_platform_driver(sun50i_av1_driver);

MODULE_DESCRIPTION("Allwinner H713 AV1 Hardware Decoder Driver");
MODULE_AUTHOR("HY300 Linux Porting Project");
MODULE_LICENSE("GPL v2");
MODULE_ALIAS("platform:sun50i-h713-av1");