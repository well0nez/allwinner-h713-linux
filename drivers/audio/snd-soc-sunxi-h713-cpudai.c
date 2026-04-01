// SPDX-License-Identifier: GPL-2.0-only
/*
 * Allwinner H713 Audio CPU-DAI / DMA Platform Driver
 *
 * Provides the PCM data path (DMA) between ALSA and the internal codec FIFOs.
 * Stock driver uses custom sunxi_pcm_* functions; this mainline port uses the
 * kernel's generic dmaengine PCM framework (snd_dmaengine_pcm_register).
 *
 * IDA Source: sunxi_asoc_cpudai_dev_probe @ 0xc083f35c
 *             sunxi_cpudai_probe @ 0xc083f318
 *             sunxi_pcm_* @ 0xc083e5bc..0xc083f0d8
 *
 * Stock DTS (hy310-board.dts):
 *   dummy_cpudai@203032c {
 *       compatible = "allwinner,sunxi-dummy-cpudai";
 *       reg = <0x0 0x203032C 0x0 0x4>;
 *       dac_txdata = <0x2030020>;   // DAC TX FIFO physical addr
 *       adc_txdata = <0x2030040>;   // ADC RX FIFO physical addr (name misleading!)
 *       tx_fifo_size = <0x80>;      // 128 bytes
 *       rx_fifo_size = <0x100>;     // 256 bytes
 *       playback_cma = <0x80>;      // 128 KB
 *       capture_cma = <0x100>;      // 256 KB
 *       dmas = <&dma 7>, <&dma 7>;
 *       dma-names = "tx", "rx";
 *       status = "okay";
 *   };
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/io.h>
#include <sound/soc.h>
#include <sound/pcm.h>
#include <sound/pcm_params.h>
#include <sound/dmaengine_pcm.h>

/*
 * IDA: driver_data structure (0x28 = 40 bytes, devm_kmalloc in probe)
 *
 * Stock layout: two 20-byte DMA param blocks (playback @ +0, capture @ +20).
 * Each block:   [0]=unused, [4]=fifo_phys_addr, [8]=src_maxburst(byte),
 *               [9]=dst_maxburst(byte), [12]=cma_kbytes, [16]=fifo_size
 *
 * Mainline: we use snd_dmaengine_dai_dma_data directly, which the
 * generic dmaengine PCM framework understands natively.
 */
struct sunxi_cpudai_data {
	struct snd_dmaengine_dai_dma_data playback_dma;
	struct snd_dmaengine_dai_dma_data capture_dma;
	u32 playback_cma;	/* buffer size in KB (for PCM hardware) */
	u32 capture_cma;
};

/* PCM hardware constraints — matches stock sunxi_pcm_hardware @ 0xc149c680 */
static const struct snd_pcm_hardware sunxi_pcm_hardware = {
	.info		= SNDRV_PCM_INFO_MMAP |
			  SNDRV_PCM_INFO_MMAP_VALID |
			  SNDRV_PCM_INFO_INTERLEAVED |
			  SNDRV_PCM_INFO_BLOCK_TRANSFER |
			  SNDRV_PCM_INFO_RESUME |
			  SNDRV_PCM_INFO_PAUSE,
	.formats	= SNDRV_PCM_FMTBIT_S16_LE |
			  SNDRV_PCM_FMTBIT_S24_LE |
			  SNDRV_PCM_FMTBIT_S32_LE,
	.rates		= SNDRV_PCM_RATE_8000_192000 |
			  SNDRV_PCM_RATE_KNOT,
	.rate_min	= 8000,
	.rate_max	= 192000,
	.channels_min	= 1,
	.channels_max	= 2,
	.buffer_bytes_max = 128 * 1024,	/* default, overridden by CMA */
	.period_bytes_min = 256,
	.period_bytes_max = 64 * 1024,
	.periods_min	= 1,
	.periods_max	= 8,
	.fifo_size	= 128,		/* default, overridden per-stream */
};

/*
 * Generic dmaengine PCM configuration.
 * Stock used custom sunxi_pcm_* functions, but the generic framework
 * provides equivalent functionality via snd_dmaengine_pcm_prepare_slave_config.
 *
 * IDA reference: sunxi_pcm_hw_params @ 0xc083ed7c sets:
 *   - slave_config.dst_maxburst = 4 (from byte offset 9 of DMA params)
 *   - slave_config.src_maxburst = 4 (from byte offset 8 of DMA params)
 *   - slave_config.dst_addr / src_addr from DMA params offset 4
 * All of this is handled automatically by snd_dmaengine_pcm_prepare_slave_config
 * reading from snd_dmaengine_dai_dma_data.
 */
static const struct snd_dmaengine_pcm_config sunxi_dmaengine_pcm_config = {
	.prepare_slave_config	= snd_dmaengine_pcm_prepare_slave_config,
	.pcm_hardware		= &sunxi_pcm_hardware,
	.prealloc_buffer_size	= 128 * 1024,
};

/* IDA: sunxi_cpudai_startup @ 0xc083f2c0 — re-sets dma_data per stream */
static int sunxi_cpudai_startup(struct snd_pcm_substream *substream,
				struct snd_soc_dai *dai)
{
	struct sunxi_cpudai_data *sdata = dev_get_drvdata(dai->dev);

	if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK)
		snd_soc_dai_set_dma_data(dai, substream, &sdata->playback_dma);
	else
		snd_soc_dai_set_dma_data(dai, substream, &sdata->capture_dma);

	return 0;
}

/* IDA: sunxi_cpudai_hw_params @ 0xc083f2ec — returns 0 */
static int sunxi_cpudai_hw_params(struct snd_pcm_substream *substream,
				  struct snd_pcm_hw_params *params,
				  struct snd_soc_dai *dai)
{
	return 0;
}

/* IDA: sunxi_cpudai_shutdown @ 0xc083f30c — empty */
static void sunxi_cpudai_shutdown(struct snd_pcm_substream *substream,
				  struct snd_soc_dai *dai)
{
}

static const struct snd_soc_dai_ops sunxi_cpudai_dai_ops = {
	.startup	= sunxi_cpudai_startup,
	.shutdown	= sunxi_cpudai_shutdown,
	.hw_params	= sunxi_cpudai_hw_params,
};

/* IDA: sunxi_cpudai_dai @ 0xc149c858
 * Stock: playback channels_max=4, capture channels_max=2
 * We match the codec's capabilities: 1-2 channels for both.
 */
static struct snd_soc_dai_driver sunxi_cpudai_dai = {
	.name		= "sunxi-dummy-cpudai",
	.playback	= {
		.stream_name	= "Playback",
		.channels_min	= 1,
		.channels_max	= 2,
		.rates		= SNDRV_PCM_RATE_8000_48000 |
				  SNDRV_PCM_RATE_96000 |
				  SNDRV_PCM_RATE_192000,
		.formats	= SNDRV_PCM_FMTBIT_S16_LE |
				  SNDRV_PCM_FMTBIT_S24_LE |
				  SNDRV_PCM_FMTBIT_S32_LE,
	},
	.capture	= {
		.stream_name	= "Capture",
		.channels_min	= 1,
		.channels_max	= 2,
		.rates		= SNDRV_PCM_RATE_8000_48000 |
				  SNDRV_PCM_RATE_96000 |
				  SNDRV_PCM_RATE_192000,
		.formats	= SNDRV_PCM_FMTBIT_S16_LE |
				  SNDRV_PCM_FMTBIT_S24_LE |
				  SNDRV_PCM_FMTBIT_S32_LE,
	},
	.ops		= &sunxi_cpudai_dai_ops,
};

/* IDA: sunxi_cpudai_suspend/resume @ 0xc083f5e0/0xc083f2fc — both return 0 */
static const struct snd_soc_component_driver sunxi_cpudai_component = {
	.name	= "sunxi-dummy-cpudai",
};

/* ===== Platform Probe ===== */
/* IDA: sunxi_asoc_cpudai_dev_probe @ 0xc083f35c */
static int sunxi_cpudai_dev_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct sunxi_cpudai_data *sdata;
	u32 dac_txdata = 0, adc_txdata = 0;
	u32 tx_fifo_size = 128, rx_fifo_size = 256;
	u32 playback_cma = 128, capture_cma = 256;
	int ret;

	sdata = devm_kzalloc(dev, sizeof(*sdata), GFP_KERNEL);
	if (!sdata)
		return -ENOMEM;

	platform_set_drvdata(pdev, sdata);

	/* IDA: parse playback_cma, clamped to [64, 256] */
	if (of_property_read_u32(np, "playback_cma", &playback_cma) < 0)
		dev_warn(dev, "playback_cma not set, default 256KB\n");
	playback_cma = clamp_val(playback_cma, 64, 256);
	sdata->playback_cma = playback_cma;

	/* IDA: parse capture_cma, clamped to [64, 256] */
	if (of_property_read_u32(np, "capture_cma", &capture_cma) < 0)
		dev_warn(dev, "capture_cma not set, default 256KB\n");
	capture_cma = clamp_val(capture_cma, 64, 256);
	sdata->capture_cma = capture_cma;

	/* IDA: parse FIFO sizes */
	if (of_property_read_u32(np, "tx_fifo_size", &tx_fifo_size) < 0)
		dev_warn(dev, "tx_fifo_size not set, default 128\n");

	if (of_property_read_u32(np, "rx_fifo_size", &rx_fifo_size) < 0)
		dev_warn(dev, "rx_fifo_size not set, default 256\n");

	/*
	 * IDA: parse DMA FIFO physical addresses
	 * dac_txdata = 0x2030020 (DAC TX FIFO, for playback DMA destination)
	 * adc_txdata = 0x2030040 (ADC RX FIFO, for capture DMA source)
	 *
	 * Stock probe then sets:
	 *   byte[8] = 4 (src_maxburst)
	 *   byte[9] = 4 (dst_maxburst)
	 *   dword[1] = physical_addr
	 *
	 * Mainline equivalent: snd_dmaengine_dai_dma_data fields.
	 */
	ret = of_property_read_u32(np, "dac_txdata", &dac_txdata);
	if (ret) {
		dev_err(dev, "dac_txdata property missing\n");
		return ret;
	}

	ret = of_property_read_u32(np, "adc_txdata", &adc_txdata);
	if (ret) {
		dev_err(dev, "adc_txdata property missing\n");
		return ret;
	}

	/* Playback DMA: CPU writes samples → DAC TX FIFO */
	sdata->playback_dma.addr = dac_txdata;
	sdata->playback_dma.addr_width = DMA_SLAVE_BUSWIDTH_4_BYTES;
	sdata->playback_dma.maxburst = 4;	/* IDA: byte[8]=4, byte[9]=4 */
	sdata->playback_dma.fifo_size = tx_fifo_size;

	/* Capture DMA: ADC RX FIFO → CPU reads samples */
	sdata->capture_dma.addr = adc_txdata;
	sdata->capture_dma.addr_width = DMA_SLAVE_BUSWIDTH_4_BYTES;
	sdata->capture_dma.maxburst = 4;	/* IDA: byte[28]=4, byte[29]=4 */
	sdata->capture_dma.fifo_size = rx_fifo_size;

	dev_info(dev, "dac_txdata=0x%08x adc_rxdata=0x%08x tx_fifo=%u rx_fifo=%u\n",
		 dac_txdata, adc_txdata, tx_fifo_size, rx_fifo_size);

	/*
	 * IDA: snd_soc_register_component(&sunxi_asoc_cpudai_component,
	 *                                  &sunxi_cpudai_dai, 1)
	 */
	ret = devm_snd_soc_register_component(dev, &sunxi_cpudai_component,
					      &sunxi_cpudai_dai, 1);
	if (ret) {
		dev_err(dev, "register component failed: %d\n", ret);
		return ret;
	}

	/*
	 * IDA: asoc_dma_platform_register(dev, 0) registered a custom PCM
	 * platform with sunxi_pcm_* ops.
	 *
	 * Mainline: use generic dmaengine PCM framework instead.
	 * This reads DMA config from snd_dmaengine_dai_dma_data set in
	 * dai_probe/startup, and uses the DTS "dmas" property for channels.
	 */
	ret = devm_snd_dmaengine_pcm_register(dev,
					       &sunxi_dmaengine_pcm_config, 0);
	if (ret) {
		/*
		 * -EPROBE_DEFER (-517) is normal when DMA controller hasn't
		 * probed yet. The kernel will retry automatically.
		 */
		if (ret != -EPROBE_DEFER)
			dev_err(dev, "register DMA PCM failed: %d\n", ret);
		return ret;
	}

	dev_info(dev, "H713 CPU-DAI probed (generic dmaengine PCM)\n");
	return 0;
}

static const struct of_device_id sunxi_cpudai_of_match[] = {
	{ .compatible = "allwinner,sunxi-dummy-cpudai" },
	{ /* sentinel */ },
};
MODULE_DEVICE_TABLE(of, sunxi_cpudai_of_match);

static struct platform_driver sunxi_cpudai_driver = {
	.probe	= sunxi_cpudai_dev_probe,
	.driver	= {
		.name		= "sunxi-dummy-cpudai",
		.of_match_table	= sunxi_cpudai_of_match,
	},
};
module_platform_driver(sunxi_cpudai_driver);

MODULE_DESCRIPTION("Allwinner H713 CPU-DAI / DMA Platform Driver");
MODULE_LICENSE("GPL");
MODULE_ALIAS("platform:sunxi-dummy-cpudai");
