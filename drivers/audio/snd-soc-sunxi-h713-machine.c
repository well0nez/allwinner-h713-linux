// SPDX-License-Identifier: GPL-2.0-only
/*
 * Allwinner H713 Audio Machine Driver
 *
 * Connects the internal codec (snd-soc-sunxi-h713-codec) to the CPU-DAI
 * (snd-soc-sunxi-h713-cpudai) and configures clock rates per sample rate.
 *
 * IDA Source: sunxi_card_dev_probe @ 0xc0847c60
 *             sunxi_card_hw_params @ 0xc0847880
 *             sunxi_card_init @ 0xc0847a60
 *             sunxi_card_suspend @ 0xc0847b84
 *             sunxi_card_resume @ 0xc0847b28
 *
 * Stock DTS (hy310-board.dts):
 *   sound@2030330 {
 *       compatible = "allwinner,sunxi-codec-machine";
 *       sunxi,audio-codec = <&codec>;
 *       sunxi,cpudai-controller = <&dummy_cpudai>;
 *       hp_detect_case = <0>;
 *       jack_enable = <0>;   // Jack detection DISABLED on HY310
 *       status = "okay";
 *   };
 *
 * NOTE: Stock has extensive headset jack detection (IRQ, delayed_work,
 * HMIC registers). HY310 DTS disables this (jack_enable=0), so this
 * port omits the entire jack detection subsystem.
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <sound/soc.h>
#include <sound/pcm_params.h>

/*
 * IDA: sunxi_card_hw_params @ 0xc0847880
 *
 * Clock selection by sample rate:
 *   11025, 22050, 44100 Hz → sysclk = 22579200 (22.5792 MHz)
 *   All other rates         → sysclk = 24576000 (24.576 MHz)
 *
 * clk_id mapping (matches sunxi_codec_set_sysclk):
 *   Playback + 22.5MHz: clk_id = 0
 *   Capture  + 22.5MHz: clk_id = 1
 *   Playback + 24.5MHz: clk_id = 2
 *   Capture  + 24.5MHz: clk_id = 3
 */
#define SYSCLK_22M	22579200	/* IDA: 0x1588800 */
#define SYSCLK_24M	24576000	/* IDA: 0x1770000 */

static int sunxi_card_hw_params(struct snd_pcm_substream *substream,
				struct snd_pcm_hw_params *params)
{
	struct snd_soc_pcm_runtime *rtd = snd_soc_substream_to_rtd(substream);
	struct snd_soc_dai *codec_dai = snd_soc_rtd_to_codec(rtd, 0);
	unsigned int rate = params_rate(params);
	unsigned int sysclk;
	int clk_id;
	int ret;

	/* IDA: rates 11025/22050/44100 use 22.5MHz, all others use 24.5MHz */
	switch (rate) {
	case 11025:
	case 22050:
	case 44100:
		sysclk = SYSCLK_22M;
		/* IDA: playback=0, capture=1 */
		clk_id = (substream->stream == SNDRV_PCM_STREAM_PLAYBACK) ? 0 : 1;
		break;
	default:
		sysclk = SYSCLK_24M;
		/* IDA: playback=2, capture=3 */
		clk_id = (substream->stream == SNDRV_PCM_STREAM_PLAYBACK) ? 2 : 3;
		break;
	}

	ret = snd_soc_dai_set_sysclk(codec_dai, clk_id, sysclk, 0);
	if (ret < 0) {
		dev_err(rtd->dev, "set sysclk %u (clk_id=%d) failed: %d\n",
			sysclk, clk_id, ret);
		return ret;
	}

	return 0;
}

static const struct snd_soc_ops sunxi_card_ops = {
	.hw_params = sunxi_card_hw_params,
};

/* IDA: sunxi_card_init @ 0xc0847a60
 * Stock creates jack with SND_JACK_HEADSET | SND_JACK_BTN_0-3.
 * HY310 has jack_enable=0, so we just sync DAPM.
 */
static int sunxi_card_init(struct snd_soc_pcm_runtime *rtd)
{
	struct snd_soc_component *component = snd_soc_rtd_to_codec(rtd, 0)->component;

	snd_soc_dapm_sync(&component->dapm);
	return 0;
}

/*
 * IDA: sunxi_card_suspend @ 0xc0847b84
 * Stock clears HMIC_CTRL[0],[1],[2] and MICBIAS_REG[23].
 * These disable headset detection hardware during suspend.
 * We keep this for correctness even though jack_enable=0.
 */
static int sunxi_card_suspend(struct snd_soc_card *card)
{
	struct snd_soc_component *component;
	struct snd_soc_pcm_runtime *rtd;

	rtd = snd_soc_get_pcm_runtime(card, &card->dai_link[0]);
	if (!rtd)
		return 0;

	component = snd_soc_rtd_to_codec(rtd, 0)->component;

	/* IDA: HMIC_CTRL (0x328) bits [0],[1],[2] → 0 */
	snd_soc_component_update_bits(component, 0x328, BIT(0), 0);
	snd_soc_component_update_bits(component, 0x328, BIT(1), 0);
	snd_soc_component_update_bits(component, 0x328, BIT(2), 0);
	/* IDA: MICBIAS_REG (0x318) bit [23] → 0 */
	snd_soc_component_update_bits(component, 0x318, BIT(23), 0);

	return 0;
}

/* IDA: sunxi_card_resume @ 0xc0847b28
 * Stock re-enables jack IRQ and re-inits headset registers.
 * HY310: jack_enable=0, nothing to do.
 */
static int sunxi_card_resume(struct snd_soc_card *card)
{
	return 0;
}

/* ===== DAI Link ===== */
/* IDA: sunxi_card_dai_link @ 0xc149d4dc
 * name = "audiocodec"
 * stream_name = "SUNXI-CODEC"
 * codec DAI = "sun50iw12codec" (from codec driver)
 */
SND_SOC_DAILINK_DEFS(h713_codec,
	DAILINK_COMP_ARRAY(COMP_EMPTY()),	/* CPU: filled from DTS */
	DAILINK_COMP_ARRAY(COMP_EMPTY()),	/* Codec: filled from DTS */
	DAILINK_COMP_ARRAY(COMP_EMPTY()));	/* Platform: filled from DTS */

static struct snd_soc_dai_link sunxi_card_dai_link[] = {
	{
		.name		= "audiocodec",
		.stream_name	= "SUNXI-CODEC",
		.init		= sunxi_card_init,
		.ops		= &sunxi_card_ops,
		SND_SOC_DAILINK_REG(h713_codec),
	},
};

static struct snd_soc_card snd_soc_sunxi_card = {
	.name		= "audiocodec",
	.dai_link	= sunxi_card_dai_link,
	.num_links	= ARRAY_SIZE(sunxi_card_dai_link),
	.suspend_pre	= sunxi_card_suspend,
	.resume_post	= sunxi_card_resume,
};

/* ===== Platform Probe ===== */
/* IDA: sunxi_card_dev_probe @ 0xc0847c60 */
static int sunxi_card_dev_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct device_node *cpu_np, *codec_np;

	if (!np) {
		dev_err(dev, "no device tree node\n");
		return -EINVAL;
	}

	/* IDA: of_parse_phandle("sunxi,cpudai-controller", 0) */
	cpu_np = of_parse_phandle(np, "sunxi,cpudai-controller", 0);
	if (!cpu_np) {
		dev_err(dev, "sunxi,cpudai-controller phandle missing\n");
		return -EINVAL;
	}

	/* IDA: of_parse_phandle("sunxi,audio-codec", 0) */
	codec_np = of_parse_phandle(np, "sunxi,audio-codec", 0);
	if (!codec_np) {
		dev_err(dev, "sunxi,audio-codec phandle missing\n");
		of_node_put(cpu_np);
		return -EINVAL;
	}

	/*
	 * IDA: dai_link setup:
	 *   cpus->of_node = cpu_np
	 *   platforms->of_node = cpu_np (same — DMA is on CPU-DAI device)
	 *   codecs->of_node = codec_np
	 *   codecs->dai_name = "sun50iw12codec" (must match codec DAI driver name)
	 *   cpus->dai_name = "sunxi-dummy-cpudai" (must match cpudai DAI driver name)
	 *
	 * NOTE: Modern ASoC (6.12+) does NOT auto-detect dai_name from of_node
	 * alone. COMP_EMPTY() with NULL dai_name triggers "DAI name is not set"
	 * error. Both codec and CPU DAI names must be set explicitly.
	 */
	sunxi_card_dai_link[0].cpus->of_node = cpu_np;
	sunxi_card_dai_link[0].cpus->dai_name = "sunxi-dummy-cpudai";
	sunxi_card_dai_link[0].platforms->of_node = cpu_np;
	sunxi_card_dai_link[0].platforms->name = NULL;
	sunxi_card_dai_link[0].codecs->of_node = codec_np;
	sunxi_card_dai_link[0].codecs->dai_name = "sun50iw12codec";

	snd_soc_sunxi_card.dev = dev;

	return devm_snd_soc_register_card(dev, &snd_soc_sunxi_card);
}

static const struct of_device_id sunxi_card_of_match[] = {
	{ .compatible = "allwinner,sunxi-codec-machine" },
	{ /* sentinel */ },
};
MODULE_DEVICE_TABLE(of, sunxi_card_of_match);

static struct platform_driver sunxi_card_driver = {
	.probe	= sunxi_card_dev_probe,
	.driver	= {
		.name		= "sunxi-codec-machine",
		.of_match_table	= sunxi_card_of_match,
	},
};
module_platform_driver(sunxi_card_driver);

MODULE_DESCRIPTION("Allwinner H713 Audio Machine Driver");
MODULE_LICENSE("GPL");
MODULE_ALIAS("platform:sunxi-codec-machine");
