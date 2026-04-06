/* SPDX-License-Identifier: GPL-2.0+ */
/*
 * Allwinner H713 AV1 Hardware Decoder Driver
 *
 * Copyright (C) 2025 HY300 Linux Porting Project
 *
 * This driver implements V4L2 stateless decoder support for the
 * Allwinner H713 SoC AV1 hardware decoder.
 */

#ifndef _SUN50I_H713_AV1_H_
#define _SUN50I_H713_AV1_H_

#include <linux/platform_device.h>
#include <linux/clk.h>
#include <linux/reset.h>
#include <linux/interrupt.h>
#include <linux/iommu.h>
#include <linux/dma-mapping.h>
#include <media/v4l2-device.h>
#include <media/v4l2-mem2mem.h>
#include <media/v4l2-ctrls.h>
#include <media/videobuf2-v4l2.h>
#include <media/videobuf2-dma-contig.h>

/* Hardware register definitions */
#define AV1_REG_BASE_OFFSET		0x0000
#define AV1_REG_CTRL			0x0000
#define AV1_REG_STATUS			0x0004
#define AV1_REG_INT_ENABLE		0x0008
#define AV1_REG_INT_STATUS		0x000c
#define AV1_REG_FRAME_CONFIG		0x0010
#define AV1_REG_METADATA_ADDR		0x0014
#define AV1_REG_METADATA_SIZE		0x0018
#define AV1_REG_OUTPUT_ADDR_Y		0x001c
#define AV1_REG_OUTPUT_ADDR_U		0x0020
#define AV1_REG_OUTPUT_ADDR_V		0x0024
#define AV1_REG_OUTPUT_STRIDE		0x0028
#define AV1_REG_DECODE_START		0x002c

/* Control register bits */
#define AV1_CTRL_ENABLE			BIT(0)
#define AV1_CTRL_RESET			BIT(1)
#define AV1_CTRL_FBD_ENABLE		BIT(2)
#define AV1_CTRL_BLUE_ENABLE		BIT(3)
#define AV1_CTRL_INTERLACE_ENABLE	BIT(4)

/* Status register bits */
#define AV1_STATUS_IDLE			BIT(0)
#define AV1_STATUS_BUSY			BIT(1)
#define AV1_STATUS_ERROR		BIT(2)
#define AV1_STATUS_DONE			BIT(3)

/* Interrupt enable/status bits */
#define AV1_INT_DECODE_DONE		BIT(0)
#define AV1_INT_DECODE_ERROR		BIT(1)
#define AV1_INT_FRAME_READY		BIT(2)

/* Pixel format definitions from factory firmware */
enum av1_pixel_format {
	AV1_FORMAT_YUV420P = 0,
	AV1_FORMAT_YUV420P_10BIT = 1,
	AV1_FORMAT_YUV422P = 2,
	AV1_FORMAT_YUV422P_10BIT = 3,
	AV1_FORMAT_YUV444P = 4,
	AV1_FORMAT_YUV444P_10BIT = 5,
	AV1_FORMAT_RGB888 = 6,
	AV1_FORMAT_YUV420P_10BIT_AV1 = 20,
};

/* Frame configuration structure (from factory firmware) */
struct av1_frame_config {
	bool fbd_enable;
	bool blue_enable;
	bool interlace_enable;
	bool use_phy_addr;
	
	int image_fd;
	enum av1_pixel_format format;
	dma_addr_t image_addr[3];	/* Y, U, V plane addresses */
	u32 image_width[3];		/* Plane widths */
	u32 image_height[3];		/* Plane heights */
	u32 image_align[3];		/* Memory alignment */
	
	int metadata_fd;
	u32 metadata_size;
	u32 metadata_flag;
	dma_addr_t metadata_addr;
	
	int field_mode;
};

/* VSYNC timestamp structure */
struct av1_vsync_timestamp {
	u64 timestamp_ns;
	u32 frame_count;
};

/* Video buffer data structure */
struct av1_video_buffer_data {
	int fd;
	dma_addr_t phy_addr;
	void *vir_addr;
	u32 size;
};

/* Device context structure */
struct sun50i_av1_ctx {
	/* Format information */
	struct v4l2_pix_format_mplane	src_fmt;
	struct v4l2_pix_format_mplane	dst_fmt;
	
	/* Decode timing */
	ktime_t				decode_start_time;
	struct v4l2_fh			fh;
	struct sun50i_av1_dev		*dev;
	
	/* V4L2 controls */
	struct v4l2_ctrl_handler	ctrl_handler;
	
	/* Current decoding parameters */
	struct av1_frame_config		frame_config;
	
	/* Buffer queues */
	struct v4l2_m2m_ctx		*m2m_ctx;
	
	/* Decoding state */
	bool				streamon_cap;
	bool				streamon_out;
};

/* Main device structure */
struct sun50i_av1_dev {
	struct platform_device		*pdev;
	struct device			*dev;
	
	/* Hardware resources */
	void __iomem			*regs;
	void __iomem			*sram_ctrl;
	struct clk			*core_clk;
	struct clk			*bus_ve_clk;
	struct clk			*bus_ve3_clk;
	struct clk			*mbus_ve3_clk;
	struct reset_control		*reset_ve;
	struct reset_control		*reset_ve3;
	
	/* Interrupt handling */
	int				irq;
	struct completion		decode_complete;
	
	/* V4L2 framework */
	struct v4l2_device		v4l2_dev;
	struct video_device		vdev;
	struct v4l2_m2m_dev		*m2m_dev;
	struct mutex			dev_mutex;
	
	/* DMA coherent memory */
	struct device			*dma_dev;
	
	/* Runtime state */
	atomic_t			num_inst;
	bool				suspended;
};

/* Hardware interface functions */
static inline u32 av1_read(struct sun50i_av1_dev *dev, u32 offset)
{
	return readl(dev->regs + offset);
}

static inline void av1_write(struct sun50i_av1_dev *dev, u32 offset, u32 value)
{
	writel(value, dev->regs + offset);
}

static inline void av1_set_bits(struct sun50i_av1_dev *dev, u32 offset, u32 bits)
{
	u32 val = av1_read(dev, offset);
	av1_write(dev, offset, val | bits);
}

static inline void av1_clear_bits(struct sun50i_av1_dev *dev, u32 offset, u32 bits)
{
	u32 val = av1_read(dev, offset);
	av1_write(dev, offset, val & ~bits);
}

/* Function prototypes */
int sun50i_av1_hw_init(struct sun50i_av1_dev *dev);
void sun50i_av1_hw_deinit(struct sun50i_av1_dev *dev);
int sun50i_av1_hw_enable(struct sun50i_av1_dev *dev);
void sun50i_av1_hw_disable(struct sun50i_av1_dev *dev);
int sun50i_av1_hw_reset(struct sun50i_av1_dev *dev);
int sun50i_av1_hw_start_decode(struct sun50i_av1_dev *dev,
			       struct av1_frame_config *config);
bool sun50i_av1_hw_is_busy(struct sun50i_av1_dev *dev);
bool sun50i_av1_hw_wait_idle(struct sun50i_av1_dev *dev, unsigned int timeout_ms);
void sun50i_av1_hw_stop_decode(struct sun50i_av1_dev *dev);

int sun50i_av1_v4l2_init(struct sun50i_av1_dev *dev);
void sun50i_av1_v4l2_cleanup(struct sun50i_av1_dev *dev);

irqreturn_t sun50i_av1_irq_handler(int irq, void *priv);

/* IOCTL command definitions (from factory firmware) */
#define AV1_IOC_MAGIC			'd'
#define AV1_FRAME_SUBMIT		_IOW(AV1_IOC_MAGIC, 0x0, struct av1_frame_config)
#define AV1_ENABLE			_IOW(AV1_IOC_MAGIC, 0x1, unsigned int)
#define AV1_INTERLACE_SETUP		_IOW(AV1_IOC_MAGIC, 0x7, struct av1_frame_config)
#define AV1_STREAM_STOP			_IOW(AV1_IOC_MAGIC, 0x8, unsigned int)
#define AV1_BYPASS_EN			_IOW(AV1_IOC_MAGIC, 0x9, unsigned int)
#define AV1_GET_VSYNC_TIMESTAMP		_IOR(AV1_IOC_MAGIC, 0xA, struct av1_vsync_timestamp)
#define AV1_MAP_VIDEO_BUFFER		_IOWR(AV1_IOC_MAGIC, 0xB, struct av1_video_buffer_data)

/* Debug and metrics */
#ifdef CONFIG_DEBUG_FS
void sun50i_av1_debugfs_init(struct sun50i_av1_dev *dev);
void sun50i_av1_debugfs_cleanup(struct sun50i_av1_dev *dev);
#else
static inline void sun50i_av1_debugfs_init(struct sun50i_av1_dev *dev) {}
static inline void sun50i_av1_debugfs_cleanup(struct sun50i_av1_dev *dev) {}
#endif

/* Prometheus metrics support */
struct av1_metrics {
	atomic64_t frames_decoded;
	atomic64_t decode_errors;
	atomic64_t hw_resets;
	atomic_t current_sessions;
	u64 total_decode_time_us;
};

extern struct av1_metrics av1_metrics;

#endif /* _SUN50I_H713_AV1_H_ */