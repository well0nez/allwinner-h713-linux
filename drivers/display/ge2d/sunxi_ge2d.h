/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SUNXI_GE2D_H_
#define _SUNXI_GE2D_H_

#include <linux/backlight.h>
#include <linux/clk.h>
#include <linux/cdev.h>
#include <linux/fb.h>
#include <linux/i2c.h>
#include <linux/interrupt.h>
#include <linux/kthread.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/pwm.h>
#include <linux/reset.h>
#include <linux/spinlock.h>
#include <linux/types.h>
#include <linux/wait.h>
#include <linux/workqueue.h>

#define GE2D_NAME		"ge2d_dev"
#define GE2D_CLASS_NAME		"ge2d"
#define GE2D_BACKLIGHT_NAME	"tv"		/* IDA: create_backlight_inst strcpy(s, "tv") */
#define GE2D_PANEL_GPIO_COUNT	4

/*
 * MMIO base addresses from init_svp() IDA analysis at 0x976c.
 * Verified by converting ge2d_dev struct field decimal values to hex:
 *   v2[7]  = 86245376  = 0x05240000   v2[8]  = 86360064  = 0x0525C000
 *   v2[9]  = 86507520  = 0x05280000   v2[10] = 86278144  = 0x05248000
 *   v2[11] = 86540288  = 0x05288000   v2[12] = 90177792  = 0x05600100
 *   v2[13] = 90177536  = 0x05600000   v2[14] = 85721088  = 0x051C0000
 *   v2[15] = 85983276  = 0x0520002C   v2[16] = 85721184  = 0x051C0060
 *
 * NOTE: several of these are NOT page-aligned (0x05600100, 0x0520002C,
 * 0x051C0060).  Stock uses raw ioremap() per address.  We store the
 * page-aligned base in mmio[] and keep the sub-page offset separate
 * where needed.  For addresses that fall inside a region already
 * mapped by an earlier entry we just compute the alias pointer.
 */
#define GE2D_MMIO_OSD		0x05240000	/* v2[7]  — GE2D core / OSD */
#define GE2D_MMIO_MIXER		0x0525C000	/* v2[8]  — GE2D mixer */
#define GE2D_MMIO_BLOCK2	0x05280000	/* v2[9]  */
#define GE2D_MMIO_BLOCK3	0x05248000	/* v2[10] */
#define GE2D_MMIO_BLOCK4	0x05288000	/* v2[11] */
#define GE2D_MMIO_AFBD		0x05600100	/* v2[12] — primary AFBD ctrl */
#define GE2D_MMIO_AFBD2		0x05600000	/* v2[13] — AFBD base / IRQ regs */
#define GE2D_MMIO_LVDS		0x051C0000	/* v2[14] — LVDS controller */
#define GE2D_MMIO_OSD_B		0x0520002C	/* v2[15] */
#define GE2D_MMIO_LVDS_B	0x051C0060	/* v2[16] */
#define GE2D_MMIO_COUNT		10		/* total ioremapped bases */
#define GE2D_IOMAP_MAX		4		/* max DTS reg resources */

/*
 * OSD / vblender IRQ registers — absolute addresses verified from
 * osd_interrupt_init() at 0xc440:
 *   WriteRegWord(90177896, -1)  → 0x05600168
 *   WriteRegWord(90177900, 16)  → 0x0560016C
 * These are at AFBD2 base (0x05600000) + 0x168 / 0x16C.
 */
#define GE2D_OSD_IRQ_CLEAR	0x168		/* offset from afbd2_base */
#define GE2D_OSD_IRQ_ENABLE	0x16C		/* offset from afbd2_base */

/*
 * AFBD IRQ status register — from osd_afbd_irq at 0xcaa4:
 *   First channel:  v1 = 0x05600100,  status at v1+40 = 0x05600128
 *   Second channel: v1 = 0x05600140,  status at v1+40 = 0x05600168
 * Offset 0x28 from the AFBD ctrl base (v2[12] = 0x05600100).
 * Second channel at stride 0x40.
 */
#define GE2D_AFBD_IRQ_STATUS		0x28	/* offset from afbd ctrl base */
#define GE2D_AFBD_IRQ_CHANNEL_STRIDE	0x40	/* between channel 0 and 1 */

/* LVDS FIFO registers (absolute addresses from lvds_reset_fifo analysis):
 *   92798988 = 0x0588000C   91226248 = 0x05700088   92803040 = 0x05880FE0
 */
#define GE2D_LVDS_CFG_REG	0x0588000C
#define GE2D_LVDS_FIFO_CTRL	0x05700088	/* bit 8 = reset */
#define GE2D_LVDS_FIFO_STATUS	0x05880FE0

/* Number of OSD interrupt wait queues (from osd_interrupt_init IDA) */
#define GE2D_OSD_IRQ_QUEUES	2

/*
 * Module parameter externs — defined in sunxi_ge2d_core.c.
 */
extern bool ge2d_enable_fbdev;
extern bool ge2d_enable_irqs;
extern bool ge2d_enable_dlpc3435;
extern bool ge2d_backlight_boot_on;
extern bool ge2d_enable_lvds_watchdog;

/*
 * External symbols from sunxi-tvtop.ko.
 */
extern int sunxi_tvtop_client_register(struct device *dev);
extern int sunxi_tvtop_clk_get(int id);
extern int sunxi_tvtop_clk_put(int id);

/* ------------------------------------------------------------------ */
/* Panel type enum                                                       */
/* ------------------------------------------------------------------ */

enum ge2d_panel_type {
	GE2D_PANEL_TYPE_UNKNOWN  = -1,
	GE2D_PANEL_TYPE_DEFAULT  = 4,
	GE2D_PANEL_TYPE_1366X768 = 6,
	GE2D_PANEL_TYPE_360X640  = 7,
	GE2D_PANEL_TYPE_640X360  = 8,
	GE2D_PANEL_TYPE_1280X720 = 9,
};

/* ------------------------------------------------------------------ */
/* GPIO descriptor (replaces ge2d_vendor_gpio)                          */
/* ------------------------------------------------------------------ */

/**
 * struct ge2d_pin_info - simple GPIO pin descriptor
 * @gpio:        Linux GPIO number; -1 if not present in DTS
 * @active_high: true when the signal is active-high (from OF_GPIO_ACTIVE_LOW)
 * @requested:   true after devm_gpio_request_one() succeeded
 */
struct ge2d_pin_info {
	int  gpio;
	bool active_high;
	bool requested;
};

/* ------------------------------------------------------------------ */
/* Panel configuration parsed from DTS                                  */
/* ------------------------------------------------------------------ */

struct ge2d_panel_config {
	u32 protocol;
	u32 bitwidth;
	u32 data_swap;
	u32 ssc_span;
	u32 ssc_step;
	u32 ssc_en;
	u32 dclk_freq;
	u32 de_current;
	u32 even_data_current;
	u32 odd_data_current;
	u32 vs_invert;
	u32 hs_invert;
	u32 de_invert;
	u32 dclk_invert;
	u32 mirror_mode;
	u32 dual_port;
	u32 debug_en;
	u32 pwm_ch;
	u32 pwm_freq;
	u32 pwm_pol;
	u32 pwm_min;
	u32 pwm_max;
	u32 backlight;
	u32 poweron_delay[3];
	u32 powerdown_delay[3];
	u32 htotal;
	u32 vtotal;
	u32 hsync;
	u32 vsync;
	u32 hsync_pol;
	u32 vsync_pol;
	u32 width;
	u32 height;
	u32 hbp;
	u32 vbp;
	u32 project_id;
	u32 lvds0_pol;
	u32 lvds1_pol;
	int panel_type;
	struct ge2d_pin_info power_gpio;
	struct ge2d_pin_info bl_gpio;
	struct ge2d_pin_info gpios[GE2D_PANEL_GPIO_COUNT];
};

/* ------------------------------------------------------------------ */
/* OSD interrupt data block (one per vblender channel)                  */
/* ------------------------------------------------------------------ */

/**
 * struct ge2d_osd_irq_data - per-channel OSD interrupt tracking
 * @wq:       wait queue woken on each vsync
 * @count:    vsync counter incremented in hardirq
 * @lock:     protects count and timestamp
 * @last_ts:  ktime of the most recent vsync
 */
struct ge2d_osd_irq_data {
	wait_queue_head_t wq;
	u32               count;
	spinlock_t        lock;
	ktime_t           last_ts;
};

/* ------------------------------------------------------------------ */
/* VSync timestamp block (ge2d_vsync_timestamp_init zeroes this)        */
/* ------------------------------------------------------------------ */

struct ge2d_vsync_data {
	u8 _raw[0x50];		/* layout not yet fully reversed */
};

/* ------------------------------------------------------------------ */
/* Main device struct                                                    */
/* ------------------------------------------------------------------ */

struct ge2d_device {
	struct device          *dev;
	struct platform_device *pdev;
	struct device_node     *tvtop_np;
	struct device_node     *panel_np;
	struct ge2d_panel_config panel;

	/* MMIO bases — indexed by GE2D_MMIO_* order in init_svp */
	void __iomem *mmio[GE2D_MMIO_COUNT];

	/* DTS reg resources (from platform_get_resource) */
	void __iomem *regs[4];
	unsigned int num_regs;

	/* Convenience aliases into mmio[] */
	void __iomem *osd_base;		/* mmio[0] = 0x05240000 */
	void __iomem *mixer_base;	/* mmio[1] = 0x0525C000 */
	void __iomem *afbd_base;	/* mmio[5] = 0x05600100  AFBD ctrl */
	void __iomem *afbd2_base;	/* mmio[6] = 0x05600000  AFBD IRQ regs */

	/* IRQ lines */
	int irq_vblender;
	int irq_afbd;

	/* Clocks and reset */
	struct clk           *clk_afbd;
	struct clk           *clk_bus_disp;
	struct reset_control *rst_bus_disp;
	bool reset_deasserted;
	bool clocks_enabled;

	/* OSD interrupt state (osd_interrupt_init fills these) */
	struct ge2d_osd_irq_data osd_irq[GE2D_OSD_IRQ_QUEUES];

	/* VSync timestamp data (ge2d_vsync_timestamp_init zeroes it) */
	struct ge2d_vsync_data vsync_data;

	/* SVP character device (/dev/ge2d) */
	struct class  *ge2d_class;
	dev_t          ge2d_devnum;
	struct device *ge2d_cdev;
	int            chrdev_major;

	/* PWM backlight */
	struct pwm_device      *pwm;
	struct backlight_device *backlight;

	/* DLPC3435 DLP companion */
	bool dlpc3435_registered;

	/* LVDS watchdog/reset kthread */
	struct task_struct *lvds_thread;

	/* OSD delayed work (osd_resume_init uses this) */
	struct delayed_work osd_delayed_work;

	/* Plane init state (tgd_init_planesetting / init_osd_plane) */
	wait_queue_head_t plane_wait;
	struct delayed_work plane_fastlogo_work;
	u32 plane_mode;
	u32 plane_count;
	u32 plane_config;
	bool plane_state_valid;
	bool plane_fastlogo_work_inited;
	bool plane_initialized;

	/* Framebuffer */
	struct fb_info *fb_info;
	bool			fb_registered;
	void           *fb_vaddr;
	phys_addr_t     fb_phys;
	size_t          fb_size;
	u32             pseudo_palette[16];

	/* Framebuffer physical address / size (from init_svp field[18/20]) */
	phys_addr_t fb_phyaddr;

	/* Misc state flags */
	bool tvtop_registered;
	bool osd_irq_enabled;

	struct mutex lock;
};

/* ------------------------------------------------------------------ */
/* Inline MMIO accessors (replaces vendor vs_io_helper)                 */
/* ------------------------------------------------------------------ */

static inline u32 ge2d_reg_read(void __iomem *base, u32 offset)
{
	return readl(base + offset);
}

static inline void ge2d_reg_write(void __iomem *base, u32 offset, u32 val)
{
	writel(val, base + offset);
}

/* ------------------------------------------------------------------ */
/* Function prototypes                                                   */
/* ------------------------------------------------------------------ */

/* sunxi_ge2d_dt.c */
int  ge2d_parse_dt(struct ge2d_device *gdev);
void ge2d_dt_cleanup(struct ge2d_device *gdev);

/* sunxi_ge2d_panel.c */
int  ge2d_panel_request_gpios(struct ge2d_device *gdev);
int  ge2d_panel_set_power(struct ge2d_device *gdev, bool on);
int  ge2d_panel_set_backlight_enable(struct ge2d_device *gdev, bool on);
void ge2d_panel_maybe_start_lvds_watchdog(struct ge2d_device *gdev);

/* sunxi_ge2d_backlight.c */
int  ge2d_backlight_init(struct ge2d_device *gdev);
void ge2d_backlight_exit(struct ge2d_device *gdev);

/* sunxi_ge2d_dlpc3435.c */
int  ge2d_dlpc3435_schedule_init(struct ge2d_device *gdev);
int  ge2d_dlpc3435_resume_init(struct ge2d_device *gdev);
void ge2d_dlpc3435_cancel_init(struct ge2d_device *gdev);

/* sunxi_ge2d_fbdev.c */
int  ge2d_fbdev_init(struct ge2d_device *gdev);
void ge2d_fbdev_exit(struct ge2d_device *gdev);

/* sunxi_ge2d_svp.c */
int  ge2d_svp_init(struct ge2d_device *gdev);
void ge2d_svp_exit(struct ge2d_device *gdev);

/* sunxi_ge2d_osd.c */
int  osd_interrupt_init(struct ge2d_device *gdev);
void osd_interrupt_disable(struct ge2d_device *gdev);
int  ge2d_vsync_timestamp_init(struct ge2d_device *gdev);
int  ge2d_osd_frame_init(struct ge2d_device *gdev);
int  ge2d_plane_init(struct ge2d_device *gdev);
int  osd_resume_init(struct ge2d_device *gdev);
void osd_suspend_request(struct ge2d_device *gdev);

/* Firmware loader (sunxi_ge2d_firmware.c) */
int  ge2d_firmware_load(struct ge2d_device *gdev);
void ge2d_firmware_unload(struct ge2d_device *gdev);
irqreturn_t ge2d_vblender_hardirq(int irq, void *data);
irqreturn_t ge2d_afbd_hardirq(int irq, void *data);

#endif /* _SUNXI_GE2D_H_ */
