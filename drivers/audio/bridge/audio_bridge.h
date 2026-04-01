/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef HY310_AUDIO_BRIDGE_H
#define HY310_AUDIO_BRIDGE_H

#include <linux/cdev.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/spinlock.h>
#include <linux/timer.h>
#include <sound/control.h>
#include <sound/core.h>
#include <sound/pcm.h>

#define TRID_DRIVER_NAME		"snd-hy310-trid-audio-bridge"
#define TRID_CARD_NAME			"TridentALSA"
#define TRID_PCM_NAME			"TridentPCM"
#define TRID_MIXER_NAME			"trid Mixer"
#define TRID_MISCDEV_NAME		"trid_audio"

/* Recovered MMIO windows from REG_Init() */
#define TRID_AUDIF_PHYS_BASE		0x06146000u
#define TRID_AUDIF_MMIO_SIZE		0x88u
#define TRID_AUDBRG_PHYS_BASE		0x06148000u
#define TRID_AUDBRG_MMIO_SIZE		0x394u
#define TRID_AUDIO_TOP_CLK_PHYS_BASE	0x0614A000u
#define TRID_AUDIO_TOP_CLK_MMIO_SIZE	0x10u
#define TRID_HIGH_ADDR_CTL_PHYS		0x06142044u
#define TRID_SW_REG1_PHYS		0x02031078u
#define TRID_SW_REG2_PHYS		0x02032078u

/* Non-windowed control registers used by stock kcontrols */
#define TRID_ARC_SRC_PHYS		0x06E00020u
#define TRID_MSP_OWA_OUT_SRC_PHYS	0x02000158u

/* Audio-top clock block */
#define TRID_AUDIO_TOP_CLK_CTL		(TRID_AUDIO_TOP_CLK_PHYS_BASE + 0x0)
#define TRID_AUDIO_TOP_CLK_CFG		(TRID_AUDIO_TOP_CLK_PHYS_BASE + 0xc)

/* AudIf block */
#define TRID_AUDIF_IRQ_STATUS		(TRID_AUDIF_PHYS_BASE + 0x0)
#define TRID_AUDIF_IRQ_MASK		(TRID_AUDIF_PHYS_BASE + 0x4)
#define TRID_AUDIF_IRQ_ROUTE		(TRID_AUDIF_PHYS_BASE + 0x8)
#define TRID_AUDIF_SPDS_STATUS		(TRID_AUDIF_PHYS_BASE + 0x10)
#define TRID_AUDIF_ABPO1_CLK		(TRID_AUDIF_PHYS_BASE + 0x18)
#define TRID_AUDIF_ABPO1_DATA		(TRID_AUDIF_PHYS_BASE + 0x1c)
#define TRID_AUDIF_ABPO2_CLK		(TRID_AUDIF_PHYS_BASE + 0x20)
#define TRID_AUDIF_ABPO2_DATA		(TRID_AUDIF_PHYS_BASE + 0x24)
#define TRID_AUDIF_ABPO3_CLK		(TRID_AUDIF_PHYS_BASE + 0x28)
#define TRID_AUDIF_ABPO3_DATA		(TRID_AUDIF_PHYS_BASE + 0x2c)
#define TRID_AUDIF_SPDO_DATA		(TRID_AUDIF_PHYS_BASE + 0x30)
/*
 * S/PDIF input register layout (confirmed from IDA AudIf_spdi_Interrupt):
 *   +0x00: cfg    (config written by activate)
 *   +0x04: status (read-only status)
 *   +0x08: data   (preamble counter / data)
 * Previous port had CTRL at 0x34/0x44 (4 bytes too low).
 * SPDI2_RATE at 0x4c was wrong: that offset is SPDI2 status.
 */
#define TRID_AUDIF_SPDI1_CFG		(TRID_AUDIF_PHYS_BASE + 0x38)
#define TRID_AUDIF_SPDI1_STATUS		(TRID_AUDIF_PHYS_BASE + 0x3c)
#define TRID_AUDIF_SPDI1_DATA		(TRID_AUDIF_PHYS_BASE + 0x40)
#define TRID_AUDIF_SPDI2_CFG		(TRID_AUDIF_PHYS_BASE + 0x48)
#define TRID_AUDIF_SPDI2_STATUS		(TRID_AUDIF_PHYS_BASE + 0x4c)
#define TRID_AUDIF_SPDI2_DATA		(TRID_AUDIF_PHYS_BASE + 0x50)
#define TRID_AUDIF_DLY_CFG		(TRID_AUDIF_PHYS_BASE + 0x54)
#define TRID_AUDIF_DLY1_REG		(TRID_AUDIF_PHYS_BASE + 0x58)
#define TRID_AUDIF_DLY2_REG		(TRID_AUDIF_PHYS_BASE + 0x5c)
#define TRID_AUDIF_DLY3_REG		(TRID_AUDIF_PHYS_BASE + 0x60)
#define TRID_AUDIF_DLY4_REG		(TRID_AUDIF_PHYS_BASE + 0x64)
#define TRID_AUDIF_SPDO_DIV		(TRID_AUDIF_PHYS_BASE + 0x68)
#define TRID_AUDIF_SPDO_CFG0		(TRID_AUDIF_PHYS_BASE + 0x6c)
#define TRID_AUDIF_SPDO_CFG1		(TRID_AUDIF_PHYS_BASE + 0x74)
#define TRID_AUDIF_SPDO_CFG2		(TRID_AUDIF_PHYS_BASE + 0x78)
#define TRID_AUDIF_SPDO_CFG3		(TRID_AUDIF_PHYS_BASE + 0x7c)

/* Audio-bridge core block */
#define TRID_AUDBRG_GLOBAL_IRQ_EN	(TRID_AUDBRG_PHYS_BASE + 0x384)
#define TRID_AUDBRG_IRQ_MASK		(TRID_AUDBRG_PHYS_BASE + 0x388)
#define TRID_AUDBRG_IRQ_STATUS		(TRID_AUDBRG_PHYS_BASE + 0x38c)
#define TRID_AUDBRG_STREAM_SYNC		(TRID_AUDBRG_PHYS_BASE + 0x390)

#define TRID_AUDBRG_OSTREAM_BASE(_n)	(TRID_AUDBRG_PHYS_BASE + 0x100 + ((_n) << 6))
/* IDA audbrg_istream_config@0x32e8: (idx+0x18520A)<<6 → stream 0 = 0x06148280 */
#define TRID_AUDBRG_ISTREAM_BASE(_n)	(TRID_AUDBRG_PHYS_BASE + 0x280 + ((_n) << 6))
/* Runtime HW pointer register (read-only), used by audbrg_alsa_putdata2HW@0x37c8 */
#define TRID_AUDBRG_ISTREAM_PTR(_n)	(TRID_AUDBRG_PHYS_BASE + 0x29c + ((_n) << 6))
/* Ostream HW pointer register (read-only), used by audbrg_ostream_putdata2SW@0x3f5c */
#define TRID_AUDBRG_OSTREAM_PTR(_n)	(TRID_AUDBRG_PHYS_BASE + 0x108 + ((_n) << 6))
#define TRID_AUDBRG_OSTREAM_FLUSH(_n)	(TRID_AUDBRG_PHYS_BASE + 0x114 + ((_n) << 6))
#define TRID_AUDBRG_ISTREAM_FLUSH(_n)	(TRID_AUDBRG_PHYS_BASE + 0x294 + ((_n) << 6))
#define TRID_AUDBRG_ISTREAM_UMACREQ(_n)	(TRID_AUDBRG_PHYS_BASE + 0x298 + ((_n) << 6))
/* IDA audbrg_delayline_config@0xa930: WLB=(idx+0x185206)<<6 → line 0 = 0x06148180 */
#define TRID_AUDBRG_DLY_WLB_BASE(_n)	(TRID_AUDBRG_PHYS_BASE + 0x180 + ((_n) << 6))
/* IDA: RLB at bridge base + 0x000 (v10-384 = 0x06148000) */
#define TRID_AUDBRG_DLY_RLB_BASE(_n)	(TRID_AUDBRG_PHYS_BASE + 0x000 + ((_n) << 6))

#define TRID_STREAM_REG_CTRL(_base)	((_base) + 0x00)
#define TRID_STREAM_REG_START		0x00
#define TRID_STREAM_REG_END		0x04
#define TRID_STREAM_REG_PTR		0x08
#define TRID_STREAM_REG_STEP		0x0c
#define TRID_STREAM_REG_CFG		0x10

#define TRID_SHARED_DMA_BYTES		0x160000u
#define TRID_ISTREAM_BYTES		0x40000u
#define TRID_OSTREAM_BYTES		0x20000u
#define TRID_DELAYLINE_BYTES		0x100000u
#define TRID_SEGMENT_BYTES		0x10000u

#define TRID_MAX_ISTREAMS		4
#define TRID_MAX_OSTREAMS		2
#define TRID_MAX_I2SO			3
#define TRID_MAX_I2SO_FRAMES		32
#define TRID_MAX_DELAYLINES		4
#define TRID_MAX_PCMS			4

#define TRID_IOCTL_PM			0x6666
#define TRID_PM_SUSPEND			1
#define TRID_PM_RESUME			2

enum trid_kcontrol_id {
	TRID_CTL_DELAYLINE1 = 0,
	TRID_CTL_DELAYLINE2,
	TRID_CTL_DELAYLINE3,
	TRID_CTL_DELAYLINE4,
	TRID_CTL_ARC_SOURCE,
	TRID_CTL_MSP_OWA_OUT_SOURCE,
	TRID_CTL_COUNT,
};

enum trid_interface_type {
	TRID_IFACE_I2SO0 = 0,
	TRID_IFACE_I2SO1,
	TRID_IFACE_I2SO2,
	TRID_IFACE_SPDO0,
	TRID_IFACE_SPDI0,
	TRID_IFACE_SPDI1,
};

/* H3: SPDI input state machine — matches stock AudIf_spdi_Interrupt@0x4ff8 */
enum trid_spdi_state {
	TRID_SPDI_IDLE          = 0,
	TRID_SPDI_WAITING_SYNC  = 2,
	TRID_SPDI_RUNNING       = 3,
};

struct trid_dma_segment {
	void *cpu;
	dma_addr_t dma;
	size_t size;
};

struct trid_stream_state {
	struct snd_pcm_substream *substream;
	struct timer_list timer;
	spinlock_t lock;
	bool running;
	bool resume_running;
	bool capture;
	enum trid_interface_type iface;
	unsigned int pcm_dev;
	unsigned int hw_stream;
	unsigned int channels;
	unsigned int rate;
	unsigned int sample_bits;
	size_t period_bytes;
	size_t buffer_bytes;
	size_t hw_ptr_bytes;
	size_t bridge_offset;
};

/*
 * I2SO output interface state — per-channel (ABPO1/2/3).
 * IDA ref: abpDtv_i2so_state (560 bytes per channel in stock).
 * We keep only the fields needed for the activate/run/interrupt path.
 */
struct trid_i2so_frame {
	u32 rate;
	u32 format;		/* DATA register value for this frame */
};

struct trid_i2so_state {
	u8 state;		/* 0=closed, 1=opened, 3=activated, 4=paused */
	phys_addr_t data_reg;	/* ABPO DATA register (0x1C/0x24/0x2C offsets) */
	phys_addr_t clk_reg;	/* ABPO CLK register (DATA - 4) */
	u32 w1c_mask;		/* IRQ mask bit (0x40000/0x20000/0x10000) */
	u32 irq_route;		/* IRQ_ROUTE value (0x3/0xC/0x30) */
	u32 spds_w1c;		/* SPDS_STATUS W1C value */
	u32 rate;		/* current sample rate */
	u32 channels;		/* current channel count */
	u32 sample_bits;	/* current sample width */
	u16 data_word;		/* current DATA register value */
	u32 frame_write;	/* ring write pointer (5-bit, mod 32) */
	u32 frame_read;		/* ring read pointer (5-bit, mod 32) */
	struct trid_i2so_frame frames[TRID_MAX_I2SO_FRAMES];
};

struct trid_audio_bridge {
	struct device *dev;
	struct platform_device *pdev;
	spinlock_t reg_lock;
	struct mutex lock;
	struct miscdevice miscdev;

	void __iomem *logical_node_base;
	resource_size_t logical_node_size;
	void __iomem *audif_base;
	void __iomem *audbrg_base;
	void __iomem *audio_top_clk_base;
	void __iomem *high_addr_ctl_base;
	void __iomem *sw_reg1_base;
	void __iomem *sw_reg2_base;
	void __iomem *arc_src_base;
	void __iomem *msp_owa_out_base;

	int audbrg_irq;
	int audif_irq;
	bool pm_error;

	/* Audio clocks (enabled before MMIO access to 0x0614xxxx) */
	struct clk *clk_audio_cpu;
	struct clk *clk_audio_umac;
	struct clk *clk_audio_ihb;

	void *shared_cpu;
	dma_addr_t shared_dma;
	struct trid_dma_segment istream[TRID_MAX_ISTREAMS];
	struct trid_dma_segment ostream[TRID_MAX_OSTREAMS];
	struct trid_dma_segment delayline[TRID_MAX_DELAYLINES];

	struct snd_card *card;
	struct snd_pcm *pcm[TRID_MAX_PCMS];
	struct trid_stream_state playback[TRID_MAX_PCMS];
	struct trid_stream_state capture[TRID_MAX_PCMS];

	unsigned int delayline_ms[TRID_MAX_DELAYLINES];
	u32 delayline_ticks[TRID_MAX_DELAYLINES];
	bool delayline_open[TRID_MAX_DELAYLINES];
	bool delayline_running[TRID_MAX_DELAYLINES];
	unsigned int arc_source;
	unsigned int msp_owa_out_source;
	unsigned int pcm_substreams;
	u32 audif_irq_mask;
	/* H3: Per-SPDI-channel state machine (index 0=SPDI1, 1=SPDI2) */
	enum trid_spdi_state spdi_state[2];
	/* I2SO output interface state (3 channels: ABPO1/2/3) */
	struct trid_i2so_state i2so[TRID_MAX_I2SO];
};

u32 trid_reg_read(struct trid_audio_bridge *bridge, phys_addr_t reg);
void trid_reg_write(struct trid_audio_bridge *bridge, phys_addr_t reg, u32 val);
void trid_reg_update_bits(struct trid_audio_bridge *bridge, phys_addr_t reg,
			  u32 mask, u32 val);

int trid_mem_init(struct trid_audio_bridge *bridge);
void trid_mem_exit(struct trid_audio_bridge *bridge);

int trid_audioio_init(struct trid_audio_bridge *bridge);
void trid_audioio_exit(struct trid_audio_bridge *bridge);
irqreturn_t trid_audbrg_irq_thread(int irq, void *data);
irqreturn_t trid_audif_irq_thread(int irq, void *data);
int trid_istream_config(struct trid_audio_bridge *bridge, unsigned int stream,
		       unsigned int rate, unsigned int channels,
		       unsigned int sample_bits, size_t period_bytes,
		       bool irq_enable);
int trid_ostream_config(struct trid_audio_bridge *bridge, unsigned int stream,
		       unsigned int rate, unsigned int channels,
		       unsigned int sample_bits, size_t period_bytes,
		       bool irq_enable);
int trid_istream_start(struct trid_audio_bridge *bridge, unsigned int stream);
int trid_istream_stop(struct trid_audio_bridge *bridge, unsigned int stream);
int trid_ostream_start(struct trid_audio_bridge *bridge, unsigned int stream);
int trid_ostream_stop(struct trid_audio_bridge *bridge, unsigned int stream);
int trid_delayline_set(struct trid_audio_bridge *bridge, unsigned int line,
		      unsigned int delay_ticks);
int trid_iface_prepare(struct trid_audio_bridge *bridge,
		      enum trid_interface_type iface,
		      unsigned int rate, unsigned int channels,
		      unsigned int sample_bits, size_t period_bytes,
		      bool irq_enable);

int trid_register_pcm(struct trid_audio_bridge *bridge, int card_index,
		      const char *card_id);
void trid_unregister_pcm(struct trid_audio_bridge *bridge);
void trid_pcm_notify_irq(struct trid_audio_bridge *bridge, bool audif_irq,
			 u32 status);

#endif /* HY310_AUDIO_BRIDGE_H */
