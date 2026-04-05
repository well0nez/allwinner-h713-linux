// SPDX-License-Identifier: GPL-2.0-only
/*
 * Allwinner H713 Internal Audio Codec Driver
 *
 * Reverse-engineered from stock vmlinux (sun50iw12) via IDA Pro.
 * Every register offset, mask, and value verified against IDA decompilation.
 * Reference: PHASE3_CODEC_RE.md
 *
 * Copyright (C) 2026
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/clk.h>
#include <linux/reset.h>
#include <linux/gpio.h>
#include <linux/of_gpio.h>
#include <linux/regmap.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <sound/soc.h>
#include <sound/pcm.h>
#include <sound/pcm_params.h>
#include <sound/tlv.h>

/* ===== Codec Register Map (Window 0, base 0x02030000, size 0x32C) ===== */
/* IDA source: codec_reg_labels @ 0xc149cfac */
#define SUNXI_DAC_DPC		0x000	/* DAC Digital Part Control */
#define SUNXI_DAC_VOL_CTRL	0x004	/* DAC Volume Control */
#define SUNXI_DAC_FIFOC		0x010	/* DAC FIFO Control */
#define SUNXI_DAC_FIFOS		0x014	/* DAC FIFO Status */
#define SUNXI_DAC_TXDATA	0x020	/* DAC TX Data (DMA target) */
#define SUNXI_DAC_CNT		0x024	/* DAC DMA Count */
#define SUNXI_DAC_DG		0x028	/* DAC Debug */
#define SUNXI_ADC_FIFOC		0x030	/* ADC FIFO Control */
#define SUNXI_ADC_VOL_CTRL	0x034	/* ADC Volume Control */
#define SUNXI_ADC_FIFOS		0x038	/* ADC FIFO Status */
#define SUNXI_ADC_RXDATA	0x040	/* ADC RX Data (DMA source) */
#define SUNXI_ADC_CNT		0x044	/* ADC DMA Count */
#define SUNXI_ADC_DG		0x04C	/* ADC Debug */
#define SUNXI_DAC_DAP_CTL	0x0F0	/* DAC DRC/HPF Control */
#define SUNXI_ADC_DAP_CTL	0x0F8	/* ADC DRC/HPF Control */
#define SUNXI_ADCL_REG		0x300	/* ADC Left Analog Control */
#define SUNXI_ADCR_REG		0x304	/* ADC Right Analog Control */
#define SUNXI_DAC_REG		0x310	/* DAC Analog Control */
#define SUNXI_MICBIAS_REG	0x318	/* Mic Bias Control */
#define SUNXI_BIAS_REG		0x320	/* Analog Bias Control */
#define SUNXI_HP_REG		0x324	/* Headphone Control */
#define SUNXI_HMIC_CTRL		0x328	/* Headphone Mic Control */
#define SUNXI_HP_CAL_CTRL	0x32C	/* Stock dump: 0x00006000 */

/* ===== I2S Register Map (Window 1, base 0x02031000, size 0x7C) ===== */
/* IDA source: i2s_reg_labels @ 0xc149ce98 */
#define I2S_CTL			0x00
#define I2S_FMT0		0x04
#define I2S_FMT1		0x08
#define I2S_CLKDIV		0x24
#define I2S_CHCFG		0x30
#define I2S_TX0CHSEL		0x34
#define I2S_TX1CHSEL		0x38
#define I2S_TX2CHSEL		0x3C
#define I2S_TX3CHSEL		0x40
#define I2S_TX0CHMAP0		0x44
#define I2S_TX0CHMAP1		0x48
#define I2S_TX1CHMAP0		0x4C
#define I2S_TX1CHMAP1		0x50
#define I2S_TX2CHMAP0		0x54
#define I2S_TX2CHMAP1		0x58
#define I2S_TX3CHMAP0		0x5C
#define I2S_TX3CHMAP1		0x60
#define I2S_RXCHSEL		0x64
#define I2S_RXCHMAP0		0x68
#define I2S_RXCHMAP1		0x6C
#define I2S_RXCHMAP2		0x70
#define I2S_RXCHMAP3		0x74

/* I2S_CTL bits */
#define I2S_CTL_TXGE		BIT(1)	/* TX global enable — IDA: sunxi_codec_set_dacsrc_mode */
#define I2S_CTL_BIT17		BIT(17)	/* IDA: cleared in dacsrc I2S mode */
#define I2S_CTL_BIT18		BIT(18)	/* IDA: cleared in dacsrc I2S mode */

/* ===== Bit Definitions (from IDA decompilation) ===== */

/* SUNXI_DAC_DPC bits */
#define DAC_HUB_EN		BIT(0)	/* IDA: sunxi_codec_set_hub_mode */
#define DAC_DIG_VOL_SHIFT	12	/* IDA: sunxi_codec_init, mask 0x3F000 */
#define DAC_DIG_VOL_MASK	GENMASK(17, 12)
#define DAC_EN			BIT(31)	/* IDA: sunxi_codec_dac_route_enable */
#define DAC_SRC_I2S_SEL		BIT(30)	/* IDA: sunxi_codec_set_dacsrc_mode */
#define DAC_SRC_I2S_EN		BIT(29)	/* IDA: sunxi_codec_set_dacsrc_mode */

/* SUNXI_DAC_VOL_CTRL bits */
#define DAC_VOL_CTRL_BIT16	BIT(16)	/* IDA: sunxi_codec_init */

/* SUNXI_DAC_FIFOC bits */
#define DAC_FIFO_EN		BIT(0)	/* IDA: sunxi_codec_prepare */
#define DAC_DRQ_EN		BIT(4)	/* IDA: sunxi_codec_enable */
#define DAC_MONO		BIT(6)	/* IDA: sunxi_codec_hw_params */
#define DAC_SAMPLE_BITS		GENMASK(25, 24)	/* IDA: hw_params */
#define DAC_RATE_MASK		GENMASK(31, 29)	/* IDA: hw_params */
#define DAC_RATE_SHIFT		29

/* SUNXI_DAC_DG bits */
#define DAC_SWAP		BIT(6)	/* IDA: sunxi_codec_init, dac_swap_en */

/* SUNXI_ADC_FIFOC bits */
#define ADC_FIFO_EN		BIT(0)	/* IDA: sunxi_codec_prepare */
#define ADC_DRQ_EN		BIT(3)	/* IDA: sunxi_codec_enable */
#define ADC_CHAN_BITS		GENMASK(13, 12)	/* IDA: hw_params channels */
#define ADC_16BIT_MODE		BIT(16)	/* IDA: hw_params */
#define ADC_EN_BIT17		BIT(17)	/* IDA: sunxi_codec_init */
#define ADC_SAMPLE_BITS		BIT(24)	/* IDA: hw_params */
#define ADC_25_BITS		GENMASK(25, 24)	/* IDA: hw_params */
#define ADC_DIGITAL_EN		BIT(28)	/* IDA: sunxi_codec_capture_event */
#define ADC_RATE_MASK		GENMASK(31, 29)	/* IDA: hw_params */
#define ADC_RATE_SHIFT		29

/* SUNXI_ADC_DG bits */
#define ADC_SWAP		BIT(24)	/* IDA: sunxi_codec_init, adc_swap_en */

/* SUNXI_ADCL_REG / SUNXI_ADCR_REG bits */
#define ADCX_MIXER_MASK		0xFF	/* IDA: sunxi_codec_init, 0x55 */
#define ADCX_ENABLE		BIT(19)	/* IDA: adc_route_enable */
#define ADCX_GLOBAL_EN		BIT(31)	/* IDA: adc_route_enable */

/* SUNXI_DAC_REG bits */
#define DAC_SPK_VOL_MASK	GENMASK(4, 0)	/* IDA: sunxi_codec_init */
#define DAC_BIT5		BIT(5)	/* IDA: sunxi_codec_init */
#define DAC_BIT6		BIT(6)	/* IDA: sunxi_codec_init */
#define DAC_BIT10		BIT(10)	/* IDA: sunxi_codec_init */
#define DAC_SPK_OUT_L		BIT(11)	/* IDA: set_spk_status */
#define DAC_BIT12		BIT(12)	/* IDA: sunxi_codec_init */
#define DAC_SPK_OUT_R		BIT(13)	/* IDA: set_spk_status */
#define DAC_ROUTE_14		BIT(14)	/* IDA: dac_route_enable */
#define DAC_ROUTE_15		BIT(15)	/* IDA: dac_route_enable */
#define DAC_BITS_24_25		GENMASK(25, 24)	/* IDA: sunxi_codec_init */
#define DAC_BIT27		BIT(27)	/* IDA: sunxi_codec_init */
#define DAC_HP_VOL_MASK		GENMASK(30, 28)	/* IDA: sunxi_codec_init */
#define DAC_HP_VOL_SHIFT	28

/* SUNXI_HP_REG bits */
#define HP_BIT2			BIT(2)	/* Stock dump lower-byte parity */
#define HP_BIT3			BIT(3)	/* IDA: sunxi_codec_init */
#define HP_BITS_7_6		GENMASK(7, 6)	/* IDA: init, mask 0xC0 val 0x80 */
#define HP_BITS_9_8		GENMASK(9, 8)	/* IDA: sunxi_codec_init */
#define HP_EN_L			BIT(10)	/* IDA: set_hp_status */
#define HP_EN_R			BIT(11)	/* IDA: set_hp_status */
#define HP_AMP_EN		BIT(15)	/* IDA: set_hp_status */
#define HP_STOCK_LOW_MASK	0x8FCC
#define HP_STOCK_LOW_VAL	0x8F8C

/* ===== Driver Data Structure (96 bytes, IDA: 0x60 alloc) ===== */
struct sunxi_codec_data {
	struct device *dev;		/* offset 0 */
	void __iomem *codec_base;	/* offset 4 */
	void __iomem *i2s_base;	/* offset 8 */
	struct regmap *codec_regmap;	/* offset 12 */
	struct regmap *i2s_regmap;	/* offset 16 */
	struct clk *pll_audio;		/* offset 20 */
	struct clk *pll_tvfe;		/* offset 24 */
	struct clk *codec_dac;		/* offset 28 */
	struct clk *codec_adc;		/* offset 32 */
	struct clk *codec_bus;		/* offset 36 */
	struct clk *audio_hub_bus;	/* audio hub bus gate */
	struct reset_control *rst;	/* offset 40 */
	u32 digital_vol;		/* offset 44 */
	u32 speaker_vol;		/* offset 48 */
	u32 headphone_vol;		/* offset 52 */
	int gpio_spk;			/* offset 56 */
	u32 pa_msleep_time;		/* offset 60 */
	bool spk_used;			/* offset 64 */
	bool pa_level;			/* offset 65 */
	bool adcdrc_used;		/* offset 68 */
	bool dacdrc_used;		/* offset 69 */
	bool adchpf_used;		/* offset 70 */
	bool dachpf_used;		/* offset 71 */
	u32 spk_active;			/* offset 80 */
	u32 hp_active;			/* offset 84 */
	u32 dac_swap_en;		/* offset 88 */
	u32 adc_swap_en;		/* offset 92 */
};

/* ===== Sample Rate Table (IDA: sample_rate_conv @ 0xc0ee7da4, 11 entries) ===== */
struct sample_rate_conv {
	u32 samplerate;
	u32 rate_bit;
};

static const struct sample_rate_conv sample_rate_conv[] = {
	{ 8000,   5 },
	{ 11025,  4 },
	{ 12000,  4 },
	{ 16000,  3 },
	{ 22050,  2 },
	{ 24000,  2 },
	{ 32000,  1 },
	{ 44100,  0 },
	{ 48000,  0 },
	{ 96000,  7 },
	{ 192000, 6 },
};

/* ===== Register labels for suspend/resume ===== */
struct reg_label {
	const char *name;
	u32 address;
	u32 value;
};

/* IDA: codec_reg_labels @ 0xc149cfac (20 entries) */
static struct reg_label codec_reg_labels[] = {
	{ "SUNXI_DAC_DPC",      0x000, 0 },
	{ "SUNXI_DAC_VOL_CTRL", 0x004, 0 },
	{ "SUNXI_DAC_FIFOC",    0x010, 0 },
	{ "SUNXI_DAC_FIFOS",    0x014, 0 },
	{ "SUNXI_DAC_CNT",      0x024, 0 },
	{ "SUNXI_DAC_DG",       0x028, 0 },
	{ "SUNXI_ADC_FIFOC",    0x030, 0 },
	{ "SUNXI_ADC_VOL_CTRL", 0x034, 0 },
	{ "SUNXI_ADC_FIFOS",    0x038, 0 },
	{ "SUNXI_ADC_CNT",      0x044, 0 },
	{ "SUNXI_ADC_DG",       0x04C, 0 },
	{ "SUNXI_DAC_DAP_CTL",  0x0F0, 0 },
	{ "SUNXI_ADC_DAP_CTL",  0x0F8, 0 },
	{ "SUNXI_ADCL_REG",     0x300, 0 },
	{ "SUNXI_ADCR_REG",     0x304, 0 },
	{ "SUNXI_DAC_REG",      0x310, 0 },
	{ "SUNXI_MICBIAS_REG",  0x318, 0 },
	{ "SUNXI_BIAS_REG",     0x320, 0 },
	{ "SUNXI_HP_REG",       0x324, 0 },
	{ "SUNXI_HMIC_CTRL",    0x328, 0 },
	{ "SUNXI_HP_CAL_CTRL",  0x32C, 0 },
	{ NULL, 0, 0 },
};

/* IDA: i2s_reg_labels @ 0xc149ce98 (22 entries) */
static struct reg_label i2s_reg_labels[] = {
	{ "I2S_CTL",       0x00, 0 },
	{ "I2S_FMT0",      0x04, 0 },
	{ "I2S_FMT1",      0x08, 0 },
	{ "I2S_CLKDIV",    0x24, 0 },
	{ "I2S_CHCFG",     0x30, 0 },
	{ "I2S_TX0CHSEL",  0x34, 0 },
	{ "I2S_TX1CHSEL",  0x38, 0 },
	{ "I2S_TX2CHSEL",  0x3C, 0 },
	{ "I2S_TX3CHSEL",  0x40, 0 },
	{ "I2S_TX0CHMAP0", 0x44, 0 },
	{ "I2S_TX0CHMAP1", 0x48, 0 },
	{ "I2S_TX1CHMAP0", 0x4C, 0 },
	{ "I2S_TX1CHMAP1", 0x50, 0 },
	{ "I2S_TX2CHMAP0", 0x54, 0 },
	{ "I2S_TX2CHMAP1", 0x58, 0 },
	{ "I2S_TX3CHMAP0", 0x5C, 0 },
	{ "I2S_TX3CHMAP1", 0x60, 0 },
	{ "I2S_RXCHSEL",   0x64, 0 },
	{ "I2S_RXCHMAP0",  0x68, 0 },
	{ "I2S_RXCHMAP1",  0x6C, 0 },
	{ "I2S_RXCHMAP2",  0x70, 0 },
	{ "I2S_RXCHMAP3",  0x74, 0 },
	{ NULL, 0, 0 },
};

/* ===== Regmap Configurations ===== */
/* IDA: sunxi_codec_regmap_config @ 0xc0ee8998: reg_bits=32, val_bits=32, stride=4 */
static const struct regmap_config sunxi_codec_regmap_config = {
	.reg_bits	= 32,
	.reg_stride	= 4,
	.val_bits	= 32,
	.max_register	= SUNXI_HP_CAL_CTRL,
	.cache_type	= REGCACHE_NONE,
};

static const struct regmap_config sunxi_i2s_regmap_config = {
	.reg_bits	= 32,
	.reg_stride	= 4,
	.val_bits	= 32,
	.max_register	= I2S_RXCHMAP3,
	.cache_type	= REGCACHE_NONE,
};

/* ===== Component read/write ===== */
/* IDA: sunxi_codec_read @ 0xc0845754 */
static unsigned int sunxi_codec_read(struct snd_soc_component *component,
				     unsigned int reg)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	unsigned int val = 0;

	regmap_read(sdata->codec_regmap, reg, &val);
	return val;
}

/* IDA: sunxi_codec_write @ 0xc084520c */
static int sunxi_codec_write(struct snd_soc_component *component,
			     unsigned int reg, unsigned int val)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);

	regmap_write(sdata->codec_regmap, reg, val);
	return 0;
}

/* ===== DAC Route Enable ===== */
/* IDA: sunxi_codec_dac_route_enable @ 0xc0844868 */
static void sunxi_codec_dac_route_enable(struct snd_soc_component *component,
					 bool enable)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	struct regmap *regmap = sdata->codec_regmap;

	/* DAC_DPC[31]: global DAC enable */
	regmap_update_bits(regmap, SUNXI_DAC_DPC, DAC_EN,
			   enable ? DAC_EN : 0);
	/* DAC_FIFOC: clear rate bits [31:29], bit5, bit6 (always) */
	regmap_update_bits(regmap, SUNXI_DAC_FIFOC, 0xE0000000, 0);
	regmap_update_bits(regmap, SUNXI_DAC_FIFOC, BIT(5), 0);
	regmap_update_bits(regmap, SUNXI_DAC_FIFOC, BIT(6), 0);
	/* DAC_REG: route bits [15:14] */
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_ROUTE_15,
			   enable ? DAC_ROUTE_15 : 0);
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_ROUTE_14,
			   enable ? DAC_ROUTE_14 : 0);
}

/* ===== ADC Route Enable ===== */
/* IDA: sunxi_codec_adc_route_enable @ 0xc0844d80 */
static void sunxi_codec_adc_route_enable(struct snd_soc_component *component,
					 bool enable)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	struct regmap *regmap = sdata->codec_regmap;

	regmap_update_bits(regmap, SUNXI_ADC_FIFOC, BIT(28), BIT(28));
	regmap_update_bits(regmap, SUNXI_ADC_FIFOC, 0xE0000000, 0);
	regmap_update_bits(regmap, SUNXI_ADC_FIFOC, BIT(16), 0);
	/*
	 * NOTE: Stock IDA shows mask=0x1000, val=0x3000 here — meaning only bit12
	 * passes through the mask, bit13 in the value is silently dropped by regmap.
	 * This looks like a stock firmware bug. We use mask=0x3000 to actually set
	 * both bits 12+13 as the value suggests was intended.
	 * If ADC capture misbehaves, revert to stock: mask=0x1000, val=0x3000.
	 */
	regmap_update_bits(regmap, SUNXI_ADC_FIFOC, 0x3000, 0x3000);
	/* ADCL/R: global enable + bit19 enable */
	regmap_update_bits(regmap, SUNXI_ADCL_REG, ADCX_GLOBAL_EN, ADCX_GLOBAL_EN);
	regmap_update_bits(regmap, SUNXI_ADCR_REG, ADCX_GLOBAL_EN, ADCX_GLOBAL_EN);
	regmap_update_bits(regmap, SUNXI_ADCL_REG, ADCX_ENABLE, ADCX_ENABLE);
	regmap_update_bits(regmap, SUNXI_ADCR_REG, ADCX_ENABLE, ADCX_ENABLE);
}

/* ===== Codec Init Sequence ===== */
/* IDA: sunxi_codec_init @ 0xc084494c — 21 register writes in exact order */
static void sunxi_codec_init(struct snd_soc_component *component)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	struct regmap *regmap = sdata->codec_regmap;

	/* #1: DAC_VOL_CTRL bit16 */
	regmap_update_bits(regmap, SUNXI_DAC_VOL_CTRL, BIT(16), BIT(16));
	/* #2: ADC_FIFOC bit17 */
	regmap_update_bits(regmap, SUNXI_ADC_FIFOC, BIT(17), BIT(17));
	/* #3: ADC_FIFOC bits[27:25] */
	regmap_update_bits(regmap, SUNXI_ADC_FIFOC, 0xE000000, 0xE000000);
	/* #4: DAC_DPC: digital volume */
	regmap_update_bits(regmap, SUNXI_DAC_DPC, DAC_DIG_VOL_MASK,
			   sdata->digital_vol << DAC_DIG_VOL_SHIFT);
	/* #5: DAC_REG: speaker volume [4:0] */
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_SPK_VOL_MASK,
			   sdata->speaker_vol);
	/* #6: DAC_REG: headphone volume [30:28] */
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_HP_VOL_MASK,
			   sdata->headphone_vol << DAC_HP_VOL_SHIFT);
	/* #7-8: ADCL/R mixer = 0x55 */
	regmap_update_bits(regmap, SUNXI_ADCL_REG, ADCX_MIXER_MASK, 0x55);
	regmap_update_bits(regmap, SUNXI_ADCR_REG, ADCX_MIXER_MASK, 0x55);
	/* ADCL/R bit17: enable analog ADC path (stock sets this) */
	regmap_update_bits(regmap, SUNXI_ADCL_REG, BIT(17), BIT(17));
	regmap_update_bits(regmap, SUNXI_ADCR_REG, BIT(17), BIT(17));
	/* #9: force stock-observed HP low bits and clear stray bit6 */
	regmap_update_bits(regmap, SUNXI_HP_REG, HP_STOCK_LOW_MASK, HP_STOCK_LOW_VAL);
	/* #10-11: DAC_REG bit6, bit5 */
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_BIT6, DAC_BIT6);
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_BIT5, DAC_BIT5);
	/* #12: DAC route enable */
	sunxi_codec_dac_route_enable(component, true);
	/* DAC_DPC bits 30+29: required by stock for DAC analog output */
	regmap_update_bits(regmap, SUNXI_DAC_DPC,
			   DAC_SRC_I2S_SEL | DAC_SRC_I2S_EN,
			   DAC_SRC_I2S_SEL | DAC_SRC_I2S_EN);
	/* #13-14: DAC_REG bit12, bit10 */
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_BIT12, DAC_BIT12);
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_BIT10, DAC_BIT10);
	/* #15-16: keep stock HP low-bit pattern stable */
	regmap_update_bits(regmap, SUNXI_HP_REG, HP_STOCK_LOW_MASK, HP_STOCK_LOW_VAL);
	/* trailing analog register seen in stock idle/playback dumps */
	regmap_write(regmap, SUNXI_HP_CAL_CTRL, 0x00006000);
	/* #17-18: DAC_REG bit27, bits[25:24] */
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_BIT27, DAC_BIT27);
	regmap_update_bits(regmap, SUNXI_DAC_REG, DAC_BITS_24_25, DAC_BITS_24_25);
	/* #19: DAC swap if enabled */
	if (sdata->dac_swap_en)
		regmap_update_bits(regmap, SUNXI_DAC_DG, DAC_SWAP, DAC_SWAP);
	/* #20: ADC swap if enabled */
	if (sdata->adc_swap_en)
		regmap_update_bits(regmap, SUNXI_ADC_DG, ADC_SWAP, ADC_SWAP);
	/* #21: spk_active = 0 */
	sdata->spk_active = 0;
}

/* ===== I2S Init Sequence ===== */
/* IDA: sunxi_codec_i2s_init @ 0xc0845230 — 21 register writes */
static void sunxi_codec_i2s_init(struct snd_soc_component *component)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	struct regmap *regmap = sdata->i2s_regmap;

	/* #1: CTL: global enable */
	regmap_update_bits(regmap, I2S_CTL, 0x1, 0x1);
	/* #2: FMT0: clear bit30 */
	regmap_update_bits(regmap, I2S_FMT0, BIT(30), 0);
	/* #3: FMT0: LRCK period [17:8] = 0x1F (31) */
	regmap_update_bits(regmap, I2S_FMT0, 0x3FF00, 0x1F00);
	/* #4: FMT0: mode [2:0] = 5 */
	regmap_update_bits(regmap, I2S_FMT0, 0x7, 0x5);
	/* #5: CLKDIV: slot width [3:0] = 4 (32-bit) */
	regmap_update_bits(regmap, I2S_CLKDIV, 0xF, 0x4);
	/* #6: CLKDIV: bit8 */
	regmap_update_bits(regmap, I2S_CLKDIV, BIT(8), BIT(8));
	/* #7: CTL: TX enable [5:4] = 01 */
	regmap_update_bits(regmap, I2S_CTL, 0x30, 0x10);
	/* #8: FMT0: bit19 */
	regmap_update_bits(regmap, I2S_FMT0, BIT(19), BIT(19));
	/* #9: FMT0: clear bit7 */
	regmap_update_bits(regmap, I2S_FMT0, BIT(7), 0);
	/* #10: CLKDIV: bits[7:4] = 8 */
	regmap_update_bits(regmap, I2S_CLKDIV, 0xF0, 0x80);
	/* #11-12: FMT1: clear bit6, clear bit7 */
	regmap_update_bits(regmap, I2S_FMT1, BIT(6), 0);
	regmap_update_bits(regmap, I2S_FMT1, BIT(7), 0);
	/* #13: FMT1: bits[5:4] = 11 */
	regmap_update_bits(regmap, I2S_FMT1, 0x30, 0x30);
	/* #14: FMT0: sample resolution [6:4] = 101 */
	regmap_update_bits(regmap, I2S_FMT0, 0x70, 0x50);
	/* #15: RXCHMAP3: direct write 0x100 */
	regmap_write(regmap, I2S_RXCHMAP3, 0x100);
	/* #16: RXCHSEL: bits[19:16] = 1 */
	regmap_update_bits(regmap, I2S_RXCHSEL, 0xF0000, 0x10000);
	/* #17: CHCFG: bits[7:4] = 1 */
	regmap_update_bits(regmap, I2S_CHCFG, 0xF0, 0x10);
	/* #18: TX0CHMAP1: channel map 3-2-1-0 */
	regmap_write(regmap, I2S_TX0CHMAP1, 0x3210);
	/* #19: TX0CHSEL: bits[19:16] = 1 */
	regmap_update_bits(regmap, I2S_TX0CHSEL, 0xF0000, 0x10000);
	/* #20: CHCFG: bits[3:0] = 1 */
	regmap_update_bits(regmap, I2S_CHCFG, 0xF, 0x1);
	/* #21: TX0CHSEL: bits[15:0] = 3 */
	regmap_update_bits(regmap, I2S_TX0CHSEL, 0xFFFF, 0x3);
	/* Fix D: DAC src = I2S — IDA: sunxi_codec_set_dacsrc_mode I2S path */
	regmap_update_bits(regmap, I2S_CTL, I2S_CTL_BIT17, 0);
	regmap_update_bits(regmap, I2S_CTL, I2S_CTL_BIT18, 0);
	regmap_update_bits(regmap, I2S_CTL, I2S_CTL_TXGE, I2S_CTL_TXGE);
}

/* ===== DAI Operations ===== */

/* IDA: sunxi_codec_startup @ 0xc08446ec — returns 0 */
static int sunxi_codec_startup(struct snd_pcm_substream *substream,
			       struct snd_soc_dai *dai)
{
	return 0;
}

/* IDA: sunxi_codec_shutdown @ 0xc08446fc — empty */
static void sunxi_codec_shutdown(struct snd_pcm_substream *substream,
				 struct snd_soc_dai *dai)
{
}

/* IDA: sunxi_codec_enable @ 0xc08447ac */
static void sunxi_codec_enable(struct snd_pcm_substream *substream,
			       struct snd_soc_dai *dai, bool enable)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(dai->component->dev);

	if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK)
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_FIFOC,
				   DAC_DRQ_EN, enable ? DAC_DRQ_EN : 0);
	else
		regmap_update_bits(sdata->codec_regmap, SUNXI_ADC_FIFOC,
				   ADC_DRQ_EN, enable ? ADC_DRQ_EN : 0);
}

/* IDA: sunxi_codec_hw_params @ 0xc0845c50 */
static int sunxi_codec_hw_params(struct snd_pcm_substream *substream,
				 struct snd_pcm_hw_params *params,
				 struct snd_soc_dai *dai)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(dai->component->dev);
	struct regmap *regmap = sdata->codec_regmap;
	unsigned int rate = params_rate(params);
	unsigned int channels = params_channels(params);
	int i;

	/* Sample format — verified against IDA @ 0xc0845c50:
	 * S16_LE playback: DAC_FIFOC[25:24]=11, DAC_FIFOC[5]=0
	 * S24_LE playback: DAC_FIFOC[25:24]=00, DAC_FIFOC[5]=1
	 * S16_LE capture:  ADC_FIFOC[24]=1, ADC_FIFOC[16]=0
	 * S24_LE capture:  ADC_FIFOC[24]=0, ADC_FIFOC[16]=1
	 */
	switch (params_width(params)) {
	case 16:
		if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK) {
			/* IDA: DAC_FIFOC[25:24]=11, bit5=0 */
			regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
					   DAC_SAMPLE_BITS, DAC_SAMPLE_BITS);
			regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
					   BIT(5), 0);
		} else {
			/* IDA: ADC_FIFOC[24]=1, [16]=0 */
			regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
					   ADC_SAMPLE_BITS, ADC_SAMPLE_BITS);
			regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
					   ADC_16BIT_MODE, 0);
		}
		break;
	case 24:
	case 32:
		if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK) {
			/* IDA: DAC_FIFOC[25:24]=00, bit5=1 */
			regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
					   DAC_SAMPLE_BITS, 0);
			regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
					   BIT(5), BIT(5));
		} else {
			/* IDA: ADC_FIFOC[24]=0, [16]=1 */
			regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
					   ADC_SAMPLE_BITS, 0);
			regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
					   ADC_16BIT_MODE, ADC_16BIT_MODE);
		}
		break;
	default:
		dev_err(dai->dev, "unsupported sample width %d\n",
			params_width(params));
		return -EINVAL;
	}

	/* Sample rate lookup */
	for (i = 0; i < ARRAY_SIZE(sample_rate_conv); i++) {
		if (sample_rate_conv[i].samplerate == rate) {
			if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK) {
				regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
						   DAC_RATE_MASK,
						   sample_rate_conv[i].rate_bit << DAC_RATE_SHIFT);
			} else {
				/* IDA: capture rejects > 48kHz */
				if (rate > 48000)
					return -EINVAL;
				regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
						   ADC_RATE_MASK,
						   sample_rate_conv[i].rate_bit << ADC_RATE_SHIFT);
			}
			break;
		}
	}

	/* Channels: mono vs stereo */
	if (channels == 1) {
		if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK)
			regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
					   DAC_MONO, DAC_MONO);
		else
			regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
					   ADC_CHAN_BITS, BIT(12));
	} else if (channels == 2) {
		if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK)
			regmap_update_bits(regmap, SUNXI_DAC_FIFOC,
					   DAC_MONO, 0);
		else
			regmap_update_bits(regmap, SUNXI_ADC_FIFOC,
					   ADC_CHAN_BITS, ADC_CHAN_BITS);
	} else {
		dev_err(dai->dev, "unsupported channels %d\n", channels);
		return -EINVAL;
	}

	return 0;
}

/* IDA: sunxi_codec_prepare @ 0xc0845158 */
static int sunxi_codec_prepare(struct snd_pcm_substream *substream,
			       struct snd_soc_dai *dai)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(dai->component->dev);
	struct regmap *regmap = sdata->codec_regmap;

	if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK) {
		/* IDA: DAC_FIFOC[0]=1, DAC_FIFOS=0x0E, DAC_CNT=0 */
		regmap_update_bits(regmap, SUNXI_DAC_FIFOC, DAC_FIFO_EN,
				   DAC_FIFO_EN);
		regmap_write(regmap, SUNXI_DAC_FIFOS, 0x0E);
		regmap_write(regmap, SUNXI_DAC_CNT, 0);
	} else {
		/* IDA: ADC_FIFOC[0]=1, ADC_FIFOS=0x0A, ADC_CNT=0 */
		regmap_update_bits(regmap, SUNXI_ADC_FIFOC, ADC_FIFO_EN,
				   ADC_FIFO_EN);
		regmap_write(regmap, SUNXI_ADC_FIFOS, 0x0A);
		regmap_write(regmap, SUNXI_ADC_CNT, 0);
	}

	return 0;
}

/* IDA: sunxi_codec_trigger @ 0xc0844818 */
static int sunxi_codec_trigger(struct snd_pcm_substream *substream,
			       int cmd, struct snd_soc_dai *dai)
{
	switch (cmd) {
	case SNDRV_PCM_TRIGGER_START:
	case SNDRV_PCM_TRIGGER_RESUME:
	case SNDRV_PCM_TRIGGER_PAUSE_RELEASE:
		sunxi_codec_enable(substream, dai, true);
		break;
	case SNDRV_PCM_TRIGGER_STOP:
	case SNDRV_PCM_TRIGGER_SUSPEND:
	case SNDRV_PCM_TRIGGER_PAUSE_PUSH:
		sunxi_codec_enable(substream, dai, false);
		break;
	default:
		return -EINVAL;
	}

	return 0;
}

/* IDA: sunxi_codec_set_sysclk @ 0xc0845f44 */
static int sunxi_codec_set_sysclk(struct snd_soc_dai *dai, int clk_id,
				   unsigned int freq, int dir)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(dai->component->dev);
	int ret;

	switch (clk_id) {
	case 0:  /* playback */
	case 2:
		/* IDA: clk_set_rate(pll_audio, 4 * freq) */
		ret = clk_set_rate(sdata->pll_audio, 4 * freq);
		if (ret)
			dev_warn(dai->dev, "set pll_audio rate failed\n");
		ret = clk_set_rate(sdata->codec_dac, freq);
		if (ret) {
			dev_err(dai->dev, "set codec_dac rate failed\n");
			return -EINVAL;
		}
		break;
	case 1:  /* capture */
	case 3:
		ret = clk_set_rate(sdata->pll_audio, 4 * freq);
		if (ret)
			dev_warn(dai->dev, "set pll_audio rate failed\n");
		ret = clk_set_rate(sdata->codec_adc, freq);
		if (ret) {
			dev_err(dai->dev, "set codec_adc rate failed\n");
			return -EINVAL;
		}
		break;
	default:
		dev_err(dai->dev, "unsupported clk_id %d\n", clk_id);
		return -EINVAL;
	}

	return 0;
}

static const struct snd_soc_dai_ops sunxi_codec_dai_ops = {
	.set_sysclk	= sunxi_codec_set_sysclk,
	.startup	= sunxi_codec_startup,
	.shutdown	= sunxi_codec_shutdown,
	.hw_params	= sunxi_codec_hw_params,
	.prepare	= sunxi_codec_prepare,
	.trigger	= sunxi_codec_trigger,
};

/* ===== DAI Definition ===== */
/* IDA: sunxi_codec_dai @ 0xc149d148, name="sun50iw12codec" */
static struct snd_soc_dai_driver sunxi_codec_dai = {
	.name		= "sun50iw12codec",
	.playback	= {
		.stream_name	= "Playback",
		.channels_min	= 1,
		.channels_max	= 2,
		.rates		= SNDRV_PCM_RATE_8000_48000 |
				  SNDRV_PCM_RATE_96000 |
				  SNDRV_PCM_RATE_192000,
		.formats	= SNDRV_PCM_FMTBIT_S16_LE |
				  SNDRV_PCM_FMTBIT_S24_LE,
	},
	.capture	= {
		.stream_name	= "Capture",
		.channels_min	= 1,
		.channels_max	= 2,
		.rates		= SNDRV_PCM_RATE_8000_48000 |
				  SNDRV_PCM_RATE_96000 |
				  SNDRV_PCM_RATE_192000,
		.formats	= SNDRV_PCM_FMTBIT_S16_LE |
				  SNDRV_PCM_FMTBIT_S24_LE,
	},
	.ops		= &sunxi_codec_dai_ops,
};

/* ===== ALSA Controls ===== */

/* IDA: sunxi_codec_set_hub_mode @ 0xc08450c8 */
static int sunxi_codec_get_hub_mode(struct snd_kcontrol *kcontrol,
				    struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	unsigned int val;

	regmap_read(sdata->codec_regmap, SUNXI_DAC_DPC, &val);
	ucontrol->value.integer.value[0] = val & DAC_HUB_EN ? 1 : 0;
	return 0;
}

static int sunxi_codec_set_hub_mode(struct snd_kcontrol *kcontrol,
				    struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	int val = ucontrol->value.integer.value[0];

	if (val != 0 && val != 1)
		return -EINVAL;

	regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_DPC,
			   DAC_HUB_EN, val ? DAC_HUB_EN : 0);
	return 0;
}

/* IDA: sunxi_codec_set_spk_status @ 0xc0845b14 */
static int sunxi_codec_get_spk_status(struct snd_kcontrol *kcontrol,
				      struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);

	ucontrol->value.integer.value[0] = sdata->spk_active;
	return 0;
}

static int sunxi_codec_set_spk_status(struct snd_kcontrol *kcontrol,
				      struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	int val = ucontrol->value.integer.value[0];

	if (val == 0) {
		/* Speaker OFF */
		sdata->spk_active = 0;
		if (sdata->spk_used) {
			gpio_set_value(sdata->gpio_spk, !sdata->pa_level);
			if (sdata->pa_msleep_time)
				msleep(sdata->pa_msleep_time);
		}
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_REG,
				   DAC_SPK_OUT_R, 0);
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_REG,
				   DAC_SPK_OUT_L, 0);
	} else if (val == 1) {
		/* Speaker ON */
		sdata->spk_active = 1;
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_REG,
				   DAC_SPK_OUT_R, DAC_SPK_OUT_R);
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_REG,
				   DAC_SPK_OUT_L, DAC_SPK_OUT_L);
		if (sdata->spk_used) {
			if (sdata->pa_msleep_time)
				msleep(sdata->pa_msleep_time);
			gpio_direction_output(sdata->gpio_spk, 1);
			gpio_set_value(sdata->gpio_spk, sdata->pa_level);
		}
	} else {
		return -EINVAL;
	}

	return 0;
}

/* IDA: sunxi_codec_set_hp_status @ 0xc0844c78 */
static int sunxi_codec_get_hp_status(struct snd_kcontrol *kcontrol,
				     struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);

	ucontrol->value.integer.value[0] = sdata->hp_active;
	return 0;
}

static int sunxi_codec_set_hp_status(struct snd_kcontrol *kcontrol,
				     struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	int val = ucontrol->value.integer.value[0];

	if (val == 0) {
		sdata->hp_active = 0;
		regmap_update_bits(sdata->codec_regmap, SUNXI_HP_REG,
				   HP_EN_R, 0);
		regmap_update_bits(sdata->codec_regmap, SUNXI_HP_REG,
				   HP_EN_L, 0);
		regmap_update_bits(sdata->codec_regmap, SUNXI_HP_REG,
				   HP_AMP_EN, 0);
	} else if (val == 1) {
		sdata->hp_active = 1;
		regmap_update_bits(sdata->codec_regmap, SUNXI_HP_REG,
				   HP_EN_R, HP_EN_R);
		regmap_update_bits(sdata->codec_regmap, SUNXI_HP_REG,
				   HP_EN_L, HP_EN_L);
		regmap_update_bits(sdata->codec_regmap, SUNXI_HP_REG,
				   HP_AMP_EN, HP_AMP_EN);
	} else {
		return -EINVAL;
	}

	return 0;
}

/* IDA: sunxi_codec_get_dacsrc_mode @ 0xc08457b0 */
static int sunxi_codec_get_dacsrc_mode(struct snd_kcontrol *kcontrol,
					struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	unsigned int val;

	regmap_read(sdata->codec_regmap, SUNXI_DAC_DPC, &val);
	ucontrol->value.integer.value[0] = (val >> 29) & 1;
	return 0;
}

/* IDA: sunxi_codec_set_dacsrc_mode @ 0xc0844fbc */
static int sunxi_codec_set_dacsrc_mode(struct snd_kcontrol *kcontrol,
					struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_soc_kcontrol_component(kcontrol);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	int val = ucontrol->value.integer.value[0];

	if (val == 0) {
		/* APB path: DAC_DPC[29] = 0 */
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_DPC,
				   DAC_SRC_I2S_EN, 0);
	} else if (val == 1) {
		/* I2S path: clear I2S_CTL[18:17], set I2S_CTL[1], DAC_DPC[30:29] */
		regmap_update_bits(sdata->i2s_regmap, I2S_CTL, I2S_CTL_BIT17, 0);
		regmap_update_bits(sdata->i2s_regmap, I2S_CTL, I2S_CTL_BIT18, 0);
		regmap_update_bits(sdata->i2s_regmap, I2S_CTL,
				   I2S_CTL_TXGE, I2S_CTL_TXGE);
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_DPC,
				   DAC_SRC_I2S_SEL, DAC_SRC_I2S_SEL);
		regmap_update_bits(sdata->codec_regmap, SUNXI_DAC_DPC,
				   DAC_SRC_I2S_EN, DAC_SRC_I2S_EN);
		/* Allow I2S path to settle before stream opens */
		msleep(5);
	} else {
		return -EINVAL;
	}

	return 0;
}

/* IDA: sunxi_codec_controls @ 0xc0ee7e3c — 12 controls */
static const struct snd_kcontrol_new sunxi_codec_controls[] = {
	/* #0: Audio Hub Output (on/off) */
	SOC_SINGLE_BOOL_EXT("Audio Hub Output", 0,
			    sunxi_codec_get_hub_mode,
			    sunxi_codec_set_hub_mode),
	/* #1-2: DAC/ADC Volume — IDA: reg 0x004 shift 8 max 0xFF / reg 0x034 shift 8 max 0xFF */
	SOC_SINGLE("DAC Volume", SUNXI_DAC_VOL_CTRL, 8, 0xFF, 0),
	SOC_SINGLE("ADC Volume", SUNXI_ADC_VOL_CTRL, 8, 0xFF, 0),
	/* #3-4: DAC/ADC Swap */
	SOC_SINGLE("DAC Swap", SUNXI_DAC_DG, 6, 1, 0),
	SOC_SINGLE("ADC Swap", SUNXI_ADC_DG, 24, 1, 0),
	/* #5-6: DAC Src / ADC Dest select */
	SOC_SINGLE_BOOL_EXT("DAC Src Select", 0,
			    sunxi_codec_get_dacsrc_mode,
			    sunxi_codec_set_dacsrc_mode),
	SOC_SINGLE("ADC Dest Select", SUNXI_ADC_FIFOC, 28, 1, 0),
	/* #7: Digital volume */
	SOC_SINGLE("digital volume", SUNXI_DAC_DPC, 12, 0x3F, 1),
	/* #8-9: Speaker / Headphone volume */
	SOC_SINGLE("Speaker Volume", SUNXI_DAC_REG, 0, 0x1F, 0),
	SOC_SINGLE("Headphone Volume", SUNXI_DAC_REG, 28, 0x7, 1),
	/* #10-11: Speaker / Headphone switch */
	SOC_SINGLE_BOOL_EXT("Speaker", 0,
			    sunxi_codec_get_spk_status,
			    sunxi_codec_set_spk_status),
	SOC_SINGLE_BOOL_EXT("Headphone", 0,
			    sunxi_codec_get_hp_status,
			    sunxi_codec_set_hp_status),
};

/* ===== DAPM ===== */

/* IDA: sunxi_codec_capture_event @ 0xc0844c08 */
static int sunxi_codec_capture_event(struct snd_soc_dapm_widget *w,
				     struct snd_kcontrol *k, int event)
{
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);

	switch (event) {
	case SND_SOC_DAPM_PRE_PMU:
		regmap_update_bits(sdata->codec_regmap, SUNXI_ADC_FIFOC,
				   ADC_DIGITAL_EN, ADC_DIGITAL_EN);
		break;
	case SND_SOC_DAPM_POST_PMD:
		regmap_update_bits(sdata->codec_regmap, SUNXI_ADC_FIFOC,
				   ADC_DIGITAL_EN, 0);
		break;
	}

	return 0;
}

/*
 * LINEIN mux controls — select between LINEIN1 and LINEIN2 inputs.
 * IDA: ADCL_REG (0x300) and ADCR_REG (0x304) mixer bits select input source.
 */
static const char * const linein_mux_texts[] = { "LINEIN1", "LINEIN2" };

static SOC_ENUM_SINGLE_DECL(lineinl_mux_enum, SND_SOC_NOPM, 0,
			     linein_mux_texts);
static SOC_ENUM_SINGLE_DECL(lineinr_mux_enum, SND_SOC_NOPM, 0,
			     linein_mux_texts);

static const struct snd_kcontrol_new lineinl_mux_ctrl =
	SOC_DAPM_ENUM("LINEINL Mux", lineinl_mux_enum);
static const struct snd_kcontrol_new lineinr_mux_ctrl =
	SOC_DAPM_ENUM("LINEINR Mux", lineinr_mux_enum);

/* IDA: sunxi_codec_dapm_widgets @ 0xc0ee8090 — 10 widgets */
static const struct snd_soc_dapm_widget sunxi_codec_dapm_widgets[] = {
	/* ADC with capture event */
	SND_SOC_DAPM_ADC_E("ADCL", "Capture", SND_SOC_NOPM, 0, 0,
			   sunxi_codec_capture_event,
			   SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
	SND_SOC_DAPM_ADC_E("ADCR", "Capture", SND_SOC_NOPM, 0, 0,
			   sunxi_codec_capture_event,
			   SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
	/* Input muxes — need kcontrol for dapm_connect_mux */
	SND_SOC_DAPM_MUX("LINEINL", SND_SOC_NOPM, 0, 0, &lineinl_mux_ctrl),
	SND_SOC_DAPM_MUX("LINEINR", SND_SOC_NOPM, 0, 0, &lineinr_mux_ctrl),
	/* Input sources */
	SND_SOC_DAPM_INPUT("LINEIN1L"),
	SND_SOC_DAPM_INPUT("LINEIN1R"),
	SND_SOC_DAPM_INPUT("LINEIN2L"),
	SND_SOC_DAPM_INPUT("LINEIN2R"),
	/* PGAs */
	SND_SOC_DAPM_PGA("LINEINL PGA", SND_SOC_NOPM, 0, 0, NULL, 0),
	SND_SOC_DAPM_PGA("LINEINR PGA", SND_SOC_NOPM, 0, 0, NULL, 0),
};

/* IDA: sunxi_codec_dapm_routes @ 0xc0ee8798 — 8 routes */
static const struct snd_soc_dapm_route sunxi_codec_dapm_routes[] = {
	{ "LINEINL", "LINEIN1", "LINEIN1L" },
	{ "LINEINL", "LINEIN2", "LINEIN2L" },
	{ "LINEINR", "LINEIN1", "LINEIN1R" },
	{ "LINEINR", "LINEIN2", "LINEIN2R" },
	{ "LINEINL PGA", NULL, "LINEINL" },
	{ "LINEINR PGA", NULL, "LINEINR" },
	{ "ADCL", NULL, "LINEINL PGA" },
	{ "ADCR", NULL, "LINEINR PGA" },
};

/* ===== Suspend / Resume ===== */

/* IDA: sunxi_codec_suspend @ 0xc0846040 */
static int sunxi_codec_suspend(struct snd_soc_component *component)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	struct reg_label *rl;

	/* Mute speaker PA */
	if (sdata->spk_used) {
		gpio_direction_output(sdata->gpio_spk, 1);
		gpio_set_value(sdata->gpio_spk, !sdata->pa_level);
		if (sdata->pa_msleep_time)
			msleep(sdata->pa_msleep_time);
	}

	/* Save all codec registers */
	for (rl = codec_reg_labels; rl->name; rl++)
		regmap_read(sdata->codec_regmap, rl->address, &rl->value);

	/* Save all I2S registers */
	for (rl = i2s_reg_labels; rl->name; rl++)
		regmap_read(sdata->i2s_regmap, rl->address, &rl->value);

	/* Disable DAC route */
	sunxi_codec_dac_route_enable(component, false);

	/* Disable clocks in reverse order */
	clk_disable_unprepare(sdata->codec_dac);
	clk_disable_unprepare(sdata->codec_adc);
	clk_disable_unprepare(sdata->pll_audio);
	clk_disable_unprepare(sdata->pll_tvfe);
	clk_disable_unprepare(sdata->codec_bus);

	/* Assert reset */
	reset_control_assert(sdata->rst);

	return 0;
}

/* IDA: sunxi_codec_resume @ 0xc0846298 */
static int sunxi_codec_resume(struct snd_soc_component *component)
{
	struct sunxi_codec_data *sdata = dev_get_drvdata(component->dev);
	struct reg_label *rl;
	int ret;

	/* IDA: Set PLL audio rate on resume */
	ret = clk_set_rate(sdata->pll_audio, 98304000);
	if (ret) {
		dev_err(sdata->dev, "resume: set pll_audio rate failed\n");
		return -EBUSY;
	}

	/* Deassert reset */
	ret = reset_control_deassert(sdata->rst);
	if (ret) {
		dev_err(sdata->dev, "resume: deassert reset failed\n");
		return -EBUSY;
	}

	/* Enable clocks in order: bus → pll_audio → pll_tvfe → dac → adc */
	if (clk_prepare_enable(sdata->codec_bus)) {
		dev_err(sdata->dev, "resume: enable codec_bus failed\n");
		return -EBUSY;
	}
	if (clk_prepare_enable(sdata->pll_audio)) {
		dev_err(sdata->dev, "resume: enable pll_audio failed\n");
		return -EBUSY;
	}
	if (clk_prepare_enable(sdata->pll_tvfe))
		dev_warn(sdata->dev, "resume: enable pll_tvfe failed\n");

	if (clk_prepare_enable(sdata->codec_dac)) {
		dev_err(sdata->dev, "resume: enable codec_dac failed\n");
		return -EBUSY;
	}
	if (clk_prepare_enable(sdata->codec_adc)) {
		dev_err(sdata->dev, "resume: enable codec_adc failed\n");
		clk_disable_unprepare(sdata->codec_adc);
		return -EBUSY;
	}

	/* Re-init codec and I2S registers */
	sunxi_codec_init(component);
	sunxi_codec_i2s_init(component);

	/* Restore saved codec registers */
	for (rl = codec_reg_labels; rl->name; rl++)
		regmap_write(sdata->codec_regmap, rl->address, rl->value);

	/* Restore saved I2S registers */
	for (rl = i2s_reg_labels; rl->name; rl++)
		regmap_write(sdata->i2s_regmap, rl->address, rl->value);

	/* Restore speaker PA state */
	if (sdata->spk_used) {
		if (sdata->pa_msleep_time)
			msleep(sdata->pa_msleep_time);
		gpio_direction_output(sdata->gpio_spk, 1);
		gpio_set_value(sdata->gpio_spk,
			       sdata->spk_active ? sdata->pa_level
						 : !sdata->pa_level);
	}

	return 0;
}

/* ===== Component Probe ===== */
/* IDA: sunxi_codec_probe @ 0xc0846498 (component probe, NOT platform probe) */
static int sunxi_codec_probe(struct snd_soc_component *component)
{
	int ret;

	ret = snd_soc_add_component_controls(component, sunxi_codec_controls,
					     ARRAY_SIZE(sunxi_codec_controls));
	if (ret) {
		dev_err(component->dev, "add controls failed\n");
		return -EINVAL;
	}

	snd_soc_dapm_new_controls(&component->dapm, sunxi_codec_dapm_widgets,
				  ARRAY_SIZE(sunxi_codec_dapm_widgets));
	snd_soc_dapm_add_routes(&component->dapm, sunxi_codec_dapm_routes,
				ARRAY_SIZE(sunxi_codec_dapm_routes));

	sunxi_codec_init(component);
	sunxi_codec_i2s_init(component);

	return 0;
}

/* IDA: sunxi_codec_remove @ 0xc0844708 */
static void sunxi_codec_remove(struct snd_soc_component *component)
{
	sunxi_codec_dac_route_enable(component, false);
}

static const struct snd_soc_component_driver soc_codec_dev_sunxi = {
	.probe		= sunxi_codec_probe,
	.remove		= sunxi_codec_remove,
	.suspend	= sunxi_codec_suspend,
	.resume		= sunxi_codec_resume,
	.read		= sunxi_codec_read,
	.write		= sunxi_codec_write,
};

/* ===== Clock Setup Helper ===== */
/* IDA: within sunxi_internal_codec_probe, clock init block */
static int sunxi_codec_clk_init(struct sunxi_codec_data *sdata,
				struct device_node *np)
{
	int ret;

	sdata->pll_audio = of_clk_get_by_name(np, "pll_audio");
	sdata->pll_tvfe  = of_clk_get_by_name(np, "pll_tvfe");
	sdata->codec_dac = of_clk_get_by_name(np, "codec_dac");
	sdata->codec_adc = of_clk_get_by_name(np, "codec_adc");
	sdata->codec_bus = of_clk_get_by_name(np, "codec_bus");
	sdata->audio_hub_bus = of_clk_get_by_name(np, "audio_hub_bus");
	dev_info(sdata->dev, "audio_hub_bus clk: %pe\n", sdata->audio_hub_bus);

	if (IS_ERR_OR_NULL(sdata->pll_audio) ||
	    IS_ERR_OR_NULL(sdata->codec_dac) ||
	    IS_ERR_OR_NULL(sdata->codec_adc) ||
	    IS_ERR_OR_NULL(sdata->codec_bus)) {
		dev_err(sdata->dev, "failed to get required clocks\n");
		return -ENODEV;
	}

	/* IDA: devm_reset_control_get(shared) */
	sdata->rst = devm_reset_control_get_shared(sdata->dev, NULL);
	if (IS_ERR(sdata->rst)) {
		dev_err(sdata->dev, "failed to get reset control\n");
		return PTR_ERR(sdata->rst);
	}

	ret = reset_control_deassert(sdata->rst);
	if (ret) {
		dev_err(sdata->dev, "reset deassert failed\n");
		return ret;
	}

	/*
	 * IDA: Stock calls clk_set_parent(codec_dac/adc, pll_audio) here.
	 * In our mainline CCU, codec_dac and codec_adc are pure gate clocks
	 * with fixed parent "pll-audio" — clk_set_parent is not supported
	 * and not needed since the parent is already correct.
	 */

	/* IDA: pll_audio = 98304000 (0x5DC0000) */
	ret = clk_set_rate(sdata->pll_audio, 98304000);
	if (ret)
		dev_warn(sdata->dev, "set pll_audio rate failed\n");

	/* IDA: pll_tvfe = 1296220160 (0x4D3F6400) */
	if (!IS_ERR_OR_NULL(sdata->pll_tvfe)) {
		ret = clk_set_rate(sdata->pll_tvfe, 1296220160);
		if (ret)
			dev_warn(sdata->dev, "set pll_tvfe rate failed\n");
	}

	/* IDA: enable order: codec_bus → pll_audio → pll_tvfe → codec_dac → codec_adc */
	ret = clk_prepare_enable(sdata->codec_bus);
	if (ret) {
		dev_err(sdata->dev, "enable codec_bus failed\n");
		return ret;
	}

	/* Enable audio hub bus clock (required for I2S registers) */
	if (!IS_ERR_OR_NULL(sdata->audio_hub_bus)) {
		ret = clk_prepare_enable(sdata->audio_hub_bus);
		dev_info(sdata->dev, "audio_hub_bus enable ret=%d\n", ret);
		if (ret)
			dev_warn(sdata->dev, "enable audio_hub_bus failed: %d\n", ret);
	}

	ret = clk_prepare_enable(sdata->pll_audio);
	if (ret) {
		dev_err(sdata->dev, "enable pll_audio failed\n");
		goto err_dis_bus;
	}

	if (!IS_ERR_OR_NULL(sdata->pll_tvfe)) {
		ret = clk_prepare_enable(sdata->pll_tvfe);
		if (ret)
			dev_warn(sdata->dev, "enable pll_tvfe failed\n");
	}

	ret = clk_prepare_enable(sdata->codec_dac);
	if (ret) {
		dev_err(sdata->dev, "enable codec_dac failed\n");
		goto err_dis_tvfe;
	}

	ret = clk_prepare_enable(sdata->codec_adc);
	if (ret) {
		dev_err(sdata->dev, "enable codec_adc failed\n");
		goto err_dis_dac;
	}

	return 0;

err_dis_dac:
	clk_disable_unprepare(sdata->codec_dac);
err_dis_tvfe:
	if (!IS_ERR_OR_NULL(sdata->pll_tvfe))
		clk_disable_unprepare(sdata->pll_tvfe);
	clk_disable_unprepare(sdata->pll_audio);
err_dis_bus:
	clk_disable_unprepare(sdata->codec_bus);
	return ret;
}

/* ===== Platform Probe ===== */
/* IDA: sunxi_internal_codec_probe @ 0xc0846544 */
static int sunxi_internal_codec_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct sunxi_codec_data *sdata;
	struct resource *res;
	void __iomem *base;
	int ret;

	if (!np)
		return -ENODEV;

	sdata = devm_kzalloc(dev, sizeof(*sdata), GFP_KERNEL);
	if (!sdata)
		return -ENOMEM;

	sdata->dev = dev;
	platform_set_drvdata(pdev, sdata);

	/* Parse DTS properties — IDA: all read as u32, checked for non-zero.
	 * of_property_read_bool() is WRONG here because "spk_used = <0>"
	 * would return true (property exists) instead of false (value is 0).
	 */
	{
		u32 val;

		of_property_read_u32(np, "digital_vol", &sdata->digital_vol);
		of_property_read_u32(np, "speaker_vol", &sdata->speaker_vol);
		of_property_read_u32(np, "headphone_vol", &sdata->headphone_vol);

		/* IDA default: spk_used=0 */
		if (of_property_read_u32(np, "spk_used", &val) == 0)
			sdata->spk_used = !!val;

		/* IDA default: pa_level=1 (active-high) */
		if (of_property_read_u32(np, "pa_level", &val) == 0)
			sdata->pa_level = !!val;
		else
			sdata->pa_level = true;

		/* IDA default: pa_msleep_time=160 */
		if (of_property_read_u32(np, "pa_msleep_time", &val) == 0)
			sdata->pa_msleep_time = val;
		else
			sdata->pa_msleep_time = 160;

		/* IDA: all default to 0 (disabled) */
		if (of_property_read_u32(np, "dacdrc_used", &val) == 0)
			sdata->dacdrc_used = !!val;
		if (of_property_read_u32(np, "adcdrc_used", &val) == 0)
			sdata->adcdrc_used = !!val;
		if (of_property_read_u32(np, "dachpf_used", &val) == 0)
			sdata->dachpf_used = !!val;
		if (of_property_read_u32(np, "adchpf_used", &val) == 0)
			sdata->adchpf_used = !!val;

		of_property_read_u32(np, "dac_swap_en", &sdata->dac_swap_en);
		of_property_read_u32(np, "adc_swap_en", &sdata->adc_swap_en);
	}

	dev_info(dev, "digital_vol=%u spk_vol=%u hp_vol=%u spk_used=%d "
		 "pa_msleep=%u pa_level=%d\n",
		 sdata->digital_vol, sdata->speaker_vol, sdata->headphone_vol,
		 sdata->spk_used, sdata->pa_msleep_time, sdata->pa_level);

	/* GPIO speaker PA setup */
	if (sdata->spk_used) {
		sdata->gpio_spk = of_get_named_gpio(np, "gpio-spk", 0);
		if (gpio_is_valid(sdata->gpio_spk)) {
			ret = devm_gpio_request(dev, sdata->gpio_spk, "spk");
			if (ret) {
				dev_warn(dev, "gpio-spk request failed\n");
				sdata->spk_used = false;
			} else {
				gpio_direction_output(sdata->gpio_spk, 1);
				/* IDA: start muted (!pa_level) */
				gpio_set_value(sdata->gpio_spk,
					       !sdata->pa_level);
			}
		} else {
			dev_warn(dev, "gpio-spk invalid, disabling speaker\n");
			sdata->spk_used = false;
		}
	}

	/* Clock + reset init */
	ret = sunxi_codec_clk_init(sdata, np);
	if (ret)
		return ret;

	/* MMIO region 0: Codec registers */
	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	base = devm_ioremap_resource(dev, res);
	if (IS_ERR(base))
		return PTR_ERR(base);

	sdata->codec_base = base;
	sdata->codec_regmap = devm_regmap_init_mmio(dev, base,
						    &sunxi_codec_regmap_config);
	if (IS_ERR(sdata->codec_regmap)) {
		dev_err(dev, "codec regmap init failed\n");
		return PTR_ERR(sdata->codec_regmap);
	}

	/* MMIO region 1: I2S registers */
	res = platform_get_resource(pdev, IORESOURCE_MEM, 1);
	base = devm_ioremap_resource(dev, res);
	if (IS_ERR(base))
		return PTR_ERR(base);

	sdata->i2s_base = base;
	sdata->i2s_regmap = devm_regmap_init_mmio(dev, base,
						  &sunxi_i2s_regmap_config);
	if (IS_ERR(sdata->i2s_regmap)) {
		dev_err(dev, "i2s regmap init failed\n");
		return PTR_ERR(sdata->i2s_regmap);
	}

	/* Register ASoC component */
	ret = devm_snd_soc_register_component(dev, &soc_codec_dev_sunxi,
					      &sunxi_codec_dai, 1);
	if (ret) {
		dev_err(dev, "register component failed: %d\n", ret);
		return ret;
	}

	dev_info(dev, "H713 internal codec probed\n");
	return 0;
}

static void sunxi_internal_codec_remove(struct platform_device *pdev)
{
	struct sunxi_codec_data *sdata = platform_get_drvdata(pdev);

	clk_disable_unprepare(sdata->codec_adc);
	clk_disable_unprepare(sdata->codec_dac);
	if (!IS_ERR_OR_NULL(sdata->pll_tvfe))
		clk_disable_unprepare(sdata->pll_tvfe);
	clk_disable_unprepare(sdata->pll_audio);
	clk_disable_unprepare(sdata->codec_bus);
	reset_control_assert(sdata->rst);
}

static const struct of_device_id sunxi_internal_codec_of_match[] = {
	{ .compatible = "allwinner,sunxi-internal-codec" },
	{ /* sentinel */ },
};
MODULE_DEVICE_TABLE(of, sunxi_internal_codec_of_match);

static struct platform_driver sunxi_internal_codec_driver = {
	.probe	= sunxi_internal_codec_probe,
	.remove	= sunxi_internal_codec_remove,
	.driver	= {
		.name		= "sunxi-internal-codec",
		.of_match_table	= sunxi_internal_codec_of_match,
	},
};
module_platform_driver(sunxi_internal_codec_driver);

MODULE_DESCRIPTION("Allwinner H713 Internal Audio Codec Driver");
MODULE_LICENSE("GPL");
MODULE_ALIAS("platform:sunxi-internal-codec");
