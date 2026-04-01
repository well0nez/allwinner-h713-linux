// SPDX-License-Identifier: GPL-2.0-only
/*
 * Allwinner H713 LRADC IIO driver
 *
 * Provides IIO voltage channels for the Low-Resolution ADC found in the
 * Allwinner H713 SoC. This enables the mainline adc-keys driver for keyboard
 * input and allows the board management driver to read NTC temperature sensors
 * via the IIO consumer API instead of direct MMIO access.
 *
 * Register layout (verified on HY310 hardware):
 *   +0x00  CTRL   - Control (sample rate, enable)
 *   +0x04  INTC   - Interrupt control
 *   +0x08  INTS   - Interrupt status
 *   +0x0c  DATA0  - Channel 0 conversion result (6-bit: 0-63)
 *   +0x10  DATA1  - Channel 1 conversion result
 *
 * Copyright (C) 2026 well0nez
 * Based on sun20i-gpadc-iio.c by Maksim Kiselev
 */

#include <linux/clk.h>
#include <linux/completion.h>
#include <linux/iio/iio.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/reset.h>

#define LRADC_CTRL		0x00
#define LRADC_INTC		0x04
#define LRADC_INTS		0x08
#define LRADC_DATA(ch)		(0x0c + (ch) * 4)

/* CTRL bits */
#define LRADC_CTRL_EN		BIT(0)
#define LRADC_CTRL_RATE(x)	((x) << 2)	/* sample rate: 0=250Hz 1=125Hz 2=62Hz 3=32Hz */
#define LRADC_CTRL_CHAN_SEL(x)	((x) << 22)	/* channel select mask */
#define LRADC_CTRL_CONTINUE	BIT(4)		/* continuous mode */

/* INTC/INTS bits */
#define LRADC_INTS_CH0_DATA	BIT(0)
#define LRADC_INTS_CH1_DATA	BIT(8)

#define LRADC_MAX_CHANNELS	2
#define LRADC_DATA_MASK		0x3f		/* 6-bit resolution */

/* Stock H713 init value: 0x45 = enable + rate=1 (125Hz) + continue */
#define LRADC_CTRL_INIT		(LRADC_CTRL_EN | LRADC_CTRL_RATE(1) | LRADC_CTRL_CONTINUE)

struct sun50i_lradc {
	void __iomem *regs;
	struct mutex lock;
	struct completion completion;
	int last_channel;
};

static int sun50i_lradc_read(struct sun50i_lradc *lradc, int channel)
{
	/* In continuous mode, just read the data register directly */
	return readl(lradc->regs + LRADC_DATA(channel)) & LRADC_DATA_MASK;
}

static int sun50i_lradc_read_raw(struct iio_dev *indio_dev,
				 struct iio_chan_spec const *chan,
				 int *val, int *val2, long mask)
{
	struct sun50i_lradc *lradc = iio_priv(indio_dev);

	switch (mask) {
	case IIO_CHAN_INFO_RAW:
		mutex_lock(&lradc->lock);
		*val = sun50i_lradc_read(lradc, chan->channel);
		mutex_unlock(&lradc->lock);
		return IIO_VAL_INT;

	case IIO_CHAN_INFO_SCALE:
		/*
		 * LRADC reference voltage is ~1.8V (AVCC), 6-bit resolution.
		 * Scale = 1800000 / 63 = 28571 uV per LSB.
		 * Report as INT_PLUS_MICRO: val=0, val2=28571.
		 */
		*val = 0;
		*val2 = 28571;
		return IIO_VAL_INT_PLUS_MICRO;

	default:
		return -EINVAL;
	}
}

static const struct iio_info sun50i_lradc_info = {
	.read_raw = sun50i_lradc_read_raw,
};

static const struct iio_chan_spec sun50i_lradc_channels[] = {
	{
		.type = IIO_VOLTAGE,
		.indexed = 1,
		.channel = 0,
		.info_mask_separate = BIT(IIO_CHAN_INFO_RAW),
		.info_mask_shared_by_type = BIT(IIO_CHAN_INFO_SCALE),
	},
	{
		.type = IIO_VOLTAGE,
		.indexed = 1,
		.channel = 1,
		.info_mask_separate = BIT(IIO_CHAN_INFO_RAW),
		.info_mask_shared_by_type = BIT(IIO_CHAN_INFO_SCALE),
	},
};

static void sun50i_lradc_reset_assert(void *data)
{
	reset_control_assert(data);
}

static int sun50i_lradc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct iio_dev *indio_dev;
	struct sun50i_lradc *lradc;
	struct reset_control *rst;
	struct clk *clk;
	int ret;

	indio_dev = devm_iio_device_alloc(dev, sizeof(*lradc));
	if (!indio_dev)
		return -ENOMEM;

	lradc = iio_priv(indio_dev);
	mutex_init(&lradc->lock);

	lradc->regs = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(lradc->regs))
		return PTR_ERR(lradc->regs);

	clk = devm_clk_get_enabled(dev, NULL);
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "failed to enable bus clock\n");

	rst = devm_reset_control_get_exclusive(dev, NULL);
	if (IS_ERR(rst))
		return dev_err_probe(dev, PTR_ERR(rst), "failed to get reset\n");

	ret = reset_control_deassert(rst);
	if (ret)
		return dev_err_probe(dev, ret, "failed to deassert reset\n");

	ret = devm_add_action_or_reset(dev, sun50i_lradc_reset_assert, rst);
	if (ret)
		return ret;

	/* Initialize hardware: enable continuous sampling */
	writel(LRADC_CTRL_INIT | LRADC_CTRL_CHAN_SEL(0x3), lradc->regs + LRADC_CTRL);
	writel(LRADC_INTS_CH0_DATA | LRADC_INTS_CH1_DATA, lradc->regs + LRADC_INTC);

	indio_dev->name = "sun50i-h713-lradc";
	indio_dev->info = &sun50i_lradc_info;
	indio_dev->modes = INDIO_DIRECT_MODE;
	indio_dev->channels = sun50i_lradc_channels;
	indio_dev->num_channels = ARRAY_SIZE(sun50i_lradc_channels);

	ret = devm_iio_device_register(dev, indio_dev);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register IIO device\n");

	dev_info(dev, "H713 LRADC IIO registered (%d channels)\n",
		 indio_dev->num_channels);
	return 0;
}

static const struct of_device_id sun50i_lradc_of_match[] = {
	{ .compatible = "allwinner,sun50i-h713-lradc" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, sun50i_lradc_of_match);

static struct platform_driver sun50i_lradc_driver = {
	.probe = sun50i_lradc_probe,
	.driver = {
		.name = "sun50i-h713-lradc",
		.of_match_table = sun50i_lradc_of_match,
	},
};
module_platform_driver(sun50i_lradc_driver);

MODULE_AUTHOR("well0nez");
MODULE_DESCRIPTION("Allwinner H713 LRADC IIO driver");
MODULE_LICENSE("GPL");
