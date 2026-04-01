// SPDX-License-Identifier: GPL-2.0
/*
 * sunxi_ge2d_osd.c — OSD interrupt, vsync timestamp, and frame init
 *
 * Functions covered:
 *   osd_interrupt_init()          0xc440
 *   ge2d_vsync_timestamp_init()   0xc3ec
 *   ge2d_osd_frame_init()         0xe248
 *   ge2d_plane_init()             0x5d20 + 0x17ec
 *   osd_resume_init()             probe step 21
 *   osd_suspend_request()         suspend step
 *   ge2d_vblender_hardirq()       0x61d8  (tgd_vblender_irq hardirq part)
 *   ge2d_afbd_hardirq()           0xcaa4  (osd_afbd_irq hardirq part)
 */

#include <linux/bitops.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/fb.h>
#include <linux/list.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include <linux/timekeeping.h>
#include <linux/wait.h>
#include <linux/workqueue.h>

#include "sunxi_ge2d.h"

/* ------------------------------------------------------------------ */
/* Forward declaration for delayed work callback                         */
/* ------------------------------------------------------------------ */

static void osd_resume_workfn(struct work_struct *work);

/* ------------------------------------------------------------------ */
/* osd_interrupt_init() — 0xc440                                         */
/*                                                                       */
/* Initialises the two OSD interrupt data blocks (waitqueues, counters)  */
/* then programs the vblender interrupt mask registers.                  */
/*                                                                       */
/* IDA-verified register addresses (decimal → hex):                      */
/*   WriteRegWord(90177896, -1)  → 0x05600168 = afbd2_base + 0x168      */
/*   WriteRegWord(90177900, 16)  → 0x0560016C = afbd2_base + 0x16C      */
/* ------------------------------------------------------------------ */

int osd_interrupt_init(struct ge2d_device *gdev)
{
	int i;

	if (!gdev->afbd2_base) {
		dev_warn(gdev->dev,
			 "osd_interrupt_init: afbd2_base not mapped; skipping HW init\n");
		return 0;
	}

	/* Initialise each per-channel interrupt data block */
	for (i = 0; i < GE2D_OSD_IRQ_QUEUES; i++) {
		struct ge2d_osd_irq_data *d = &gdev->osd_irq[i];

		init_waitqueue_head(&d->wq);
		spin_lock_init(&d->lock);
		d->count   = 0;
		d->last_ts = 0;
	}

	/* Clear all pending vblender interrupts (afbd2_base + 0x168) */
	ge2d_reg_write(gdev->afbd2_base, GE2D_OSD_IRQ_CLEAR, 0xFFFFFFFF);

	/* Enable vsync interrupt bit 4 (afbd2_base + 0x16C) */
	ge2d_reg_write(gdev->afbd2_base, GE2D_OSD_IRQ_ENABLE, 0x10);

	gdev->osd_irq_enabled = true;
	dev_dbg(gdev->dev, "osd_interrupt_init done\n");
	return 0;
}

/**
 * osd_interrupt_disable - mask all vblender interrupts (used in suspend)
 */
void osd_interrupt_disable(struct ge2d_device *gdev)
{
	if (!gdev->afbd2_base || !gdev->osd_irq_enabled)
		return;

	ge2d_reg_write(gdev->afbd2_base, GE2D_OSD_IRQ_ENABLE, 0x00);
	ge2d_reg_write(gdev->afbd2_base, GE2D_OSD_IRQ_CLEAR,  0xFFFFFFFF);
	gdev->osd_irq_enabled = false;
}

/* ------------------------------------------------------------------ */
/* ge2d_vsync_timestamp_init() — 0xc3ec                                  */
/*                                                                       */
/* Stock implementation is: memset(&vsync_data, 0, 0x50)                 */
/* ------------------------------------------------------------------ */

int ge2d_vsync_timestamp_init(struct ge2d_device *gdev)
{
	memset(&gdev->vsync_data, 0, sizeof(gdev->vsync_data));
	return 0;
}

/* ------------------------------------------------------------------ */
/* ge2d_osd_frame_init() — 0xe248                                        */
/*                                                                       */
/* Allocates a fence context for OSD frame sync.  Phase 1: just init    */
/* the list heads and mark ready.                                        */
/* ------------------------------------------------------------------ */

int ge2d_osd_frame_init(struct ge2d_device *gdev)
{
	/*
	 * Phase 2 will call dma_fence_context_alloc(1) here and set up the
	 * OSD writeback fence chain.  For now just signal readiness.
	 */
	dev_dbg(gdev->dev, "ge2d_osd_frame_init: stub ready\n");
	return 0;
}


struct ge2d_phys_reg_write {
	phys_addr_t addr;
	u32 value;
};

static const struct ge2d_phys_reg_write ge2d_plane_vblender_writes[] = {
	{ 0x05200040, 0x1A000005 },  /* VBlender_base(0x0520002C) + 20 */
	{ 0x05200050, 0x00350000 },  /* VBlender_base + 36 */
	{ 0x05200054, 0x08100035 },  /* VBlender_base + 40 */
};

static const struct ge2d_phys_reg_write ge2d_plane_osd_writes[] = {
	{ 0x05248000, 0x80FF0008 },
	{ 0x05248010, 0x04650098 },
	{ 0x05248014, 0x00000000 },
	{ 0x05248050, 0x0000FF00 },
	{ 0x0524807C, 0x03000140 },
	{ 0x05248080, 0x02000000 },
	{ 0x05248004, 0x00100010 },
	{ 0x05248018, 0x03000000 },
	{ 0x05248058, 0x01000100 },
	{ 0x0524805C, 0x00000100 },
};

static const struct ge2d_phys_reg_write ge2d_plane_afbd_writes[] = {
	{ 0x05600100, 0x83000201 },
	{ 0x05600108, 0x008000FF },
	{ 0x0560010C, 0x00FF0080 },
	{ 0x05600124, 0x00000808 },
	{ 0x05600128, 0x00000082 },
	{ 0x0560012C, 0x00000021 },
};

static int ge2d_write_phys_reg(struct ge2d_device *gdev, phys_addr_t addr,
			      u32 value)
{
	void __iomem *reg;

	reg = ioremap(addr, sizeof(u32));
	if (!reg) {
		dev_err(gdev->dev,
			"ge2d_plane_init: failed to map reg 0x%08llX\n",
			(unsigned long long)addr);
		return -ENOMEM;
	}

	writel(value, reg);
	iounmap(reg);
	return 0;
}

static int ge2d_read_phys_reg(struct ge2d_device *gdev, phys_addr_t addr,
			     u32 *value)
{
	void __iomem *reg;

	reg = ioremap(addr, sizeof(u32));
	if (!reg) {
		dev_err(gdev->dev,
			"ge2d_plane_init: failed to map reg 0x%08llX\n",
			(unsigned long long)addr);
		return -ENOMEM;
	}

	*value = readl(reg);
	iounmap(reg);
	return 0;
}

static int ge2d_update_phys_reg_bits(struct ge2d_device *gdev, phys_addr_t addr,
				    u32 clear_mask, u32 set_mask)
{
	void __iomem *reg;
	u32 value;

	reg = ioremap(addr, sizeof(u32));
	if (!reg) {
		dev_err(gdev->dev,
			"ge2d_plane_init: failed to map reg 0x%08llX\n",
			(unsigned long long)addr);
		return -ENOMEM;
	}

	value = readl(reg);
	value &= ~clear_mask;
	value |= set_mask;
	writel(value, reg);
	iounmap(reg);
	return 0;
}

static int ge2d_write_phys_table(struct ge2d_device *gdev,
				 const struct ge2d_phys_reg_write *writes,
				 size_t count)
{
	size_t i;
	int ret;

	for (i = 0; i < count; i++) {
		ret = ge2d_write_phys_reg(gdev, writes[i].addr, writes[i].value);
		if (ret)
			return ret;
	}

	return 0;
}

static int ge2d_config_vblender_irq(struct ge2d_device *gdev)
{
	/* plane 6 -> bit (6 + 8) = 14 on the decoded GE2D + 0x1C mask reg */
	return ge2d_update_phys_reg_bits(gdev, 0x05240018, 0, BIT(14));
}

static void ge2d_free_fastlogo_workfn(struct work_struct *work)
{
	struct ge2d_device *gdev =
		container_of(to_delayed_work(work), struct ge2d_device,
			     plane_fastlogo_work);

	dev_dbg(gdev->dev, "ge2d_free_fastlogo_workfn: stub\n");
}

static void ge2d_afbd_wb_init(struct ge2d_device *gdev)
{
	dev_dbg(gdev->dev, "ge2d_afbd_wb_init: stub\n");
}

int ge2d_plane_init(struct ge2d_device *gdev)
{
	int ret;

	dev_info(gdev->dev, "ge2d: starting plane init...\n");
	if (!gdev)
		return -EINVAL;

	if (!gdev->plane_fastlogo_work_inited) {
		INIT_DELAYED_WORK(&gdev->plane_fastlogo_work,
				  ge2d_free_fastlogo_workfn);
		gdev->plane_fastlogo_work_inited = true;
	}

	gdev->plane_mode = 2;
	gdev->plane_count = 1;
	gdev->plane_config = 2;
	gdev->plane_state_valid = true;
	gdev->plane_initialized = false;
	init_waitqueue_head(&gdev->plane_wait);

	ret = ge2d_config_vblender_irq(gdev);
	if (ret)
		return ret;

	ret = ge2d_write_phys_table(gdev, ge2d_plane_vblender_writes,
				    ARRAY_SIZE(ge2d_plane_vblender_writes));
	if (ret)
		return ret;

	ret = ge2d_write_phys_table(gdev, ge2d_plane_osd_writes,
				    ARRAY_SIZE(ge2d_plane_osd_writes));
	if (ret)
		return ret;

	ret = ge2d_write_phys_table(gdev, ge2d_plane_afbd_writes,
				    ARRAY_SIZE(ge2d_plane_afbd_writes));
	if (ret)
		return ret;

	/*
	 * VBlender bit24 RMW sequence from IDA init_osd_plane @ 0x1f50..0x2060:
	 *   read  ge2d_dev[56]+28 = 0x05200048
	 *   write ge2d_dev[56]+16 = 0x0520003C with bit24 clear
	 *   read  again
	 *   write with bit24 set
	 *   read  again
	 *   write with bit24 clear
	 */
	{
		u32 regv;

		ret = ge2d_read_phys_reg(gdev, 0x05200048, &regv);
		if (ret)
			return ret;
		ret = ge2d_write_phys_reg(gdev, 0x0520003C, regv & ~BIT(24));
		if (ret)
			return ret;

		ret = ge2d_read_phys_reg(gdev, 0x05200048, &regv);
		if (ret)
			return ret;
		ret = ge2d_write_phys_reg(gdev, 0x0520003C, regv | BIT(24));
		if (ret)
			return ret;

		ret = ge2d_read_phys_reg(gdev, 0x05200048, &regv);
		if (ret)
			return ret;
		ret = ge2d_write_phys_reg(gdev, 0x0520003C, regv & ~BIT(24));
		if (ret)
			return ret;
	}

	ge2d_afbd_wb_init(gdev);
	gdev->plane_initialized = true;
	dev_info(gdev->dev, "ge2d_plane_init done\n");
	return 0;
}

/* ------------------------------------------------------------------ */
/* osd_resume_init() — kicks the OSD firmware worker                     */
/* ------------------------------------------------------------------ */

int osd_resume_init(struct ge2d_device *gdev)
{
	/*
	 * Stock osd_resume_init() schedules a delayed work that re-programs
	 * the OSD plane registers after a suspend/resume cycle.
	 * Phase 1: schedule the stub delayed work after 100 ms.
	 */
	INIT_DELAYED_WORK(&gdev->osd_delayed_work, osd_resume_workfn);
	schedule_delayed_work(&gdev->osd_delayed_work, msecs_to_jiffies(100));
	return 0;
}

static void osd_resume_workfn(struct work_struct *work)
{
	struct ge2d_device *gdev =
		container_of(to_delayed_work(work), struct ge2d_device,
			     osd_delayed_work);
	int ret;

	ret = ge2d_firmware_load(gdev);
	if (ret) {
		dev_err(gdev->dev,
			"osd_resume_workfn: firmware load failed: %d\n", ret);
		return;
	}

	/* ret = ge2d_plane_init(gdev); */
	/* SKIPPED: VBlender block 0x05200000 is unpowered, writes go to void */
	dev_info(gdev->dev, "ge2d: plane_init SKIPPED (VBlender unpowered)\n");
	if (ret)
		dev_err(gdev->dev,
			"osd_resume_workfn: plane init failed: %d\n", ret);
}

void osd_suspend_request(struct ge2d_device *gdev)
{
	cancel_delayed_work_sync(&gdev->osd_delayed_work);
	if (gdev->plane_fastlogo_work_inited)
		cancel_delayed_work_sync(&gdev->plane_fastlogo_work);
	osd_interrupt_disable(gdev);
}

/* ------------------------------------------------------------------ */
/* ge2d_vblender_hardirq() — tgd_vblender_irq hardirq part (0x61d8)     */
/*                                                                       */
/* Stock reads status from ge2d_dev->field[7]+offset (osd_base region)  */
/* with io_accessor_read_reg, then updates waitqueues and vsync time.   */
/*                                                                       */
/* The vblender status register is read at osd_base + 0x9C (reg 156     */
/* decimal in IDA: v3 = ge2d_dev[28] which is field[7]=osd_base,        */
/* then reads at v3+156 = osd_base + 0x9C).                             */
/*                                                                       */
/* For Phase 1, we read the IRQ clear register to detect pending IRQs,  */
/* ack them, and wake waitqueues.                                        */
/* ------------------------------------------------------------------ */

irqreturn_t ge2d_vblender_hardirq(int irq, void *data)
{
	struct ge2d_device *gdev = data;
	u32 status;
	int i;

	if (!gdev->afbd2_base)
		return IRQ_NONE;

	/* Read and ack the vblender interrupt via afbd2_base + 0x168 */
	status = ge2d_reg_read(gdev->afbd2_base, GE2D_OSD_IRQ_CLEAR);
	if (!status)
		return IRQ_NONE;

	ge2d_reg_write(gdev->afbd2_base, GE2D_OSD_IRQ_CLEAR, status);

	/* Update vsync timestamps and wake waitqueues */
	for (i = 0; i < GE2D_OSD_IRQ_QUEUES; i++) {
		struct ge2d_osd_irq_data *d = &gdev->osd_irq[i];
		unsigned long flags;

		spin_lock_irqsave(&d->lock, flags);
		d->count++;
		d->last_ts = ktime_get();
		spin_unlock_irqrestore(&d->lock, flags);

		wake_up(&d->wq);
	}

	return IRQ_HANDLED;
}

/* ------------------------------------------------------------------ */
/* ge2d_afbd_hardirq() — osd_afbd_irq hardirq part (0xcaa4)             */
/*                                                                       */
/* Stock loops over 2 channels:                                          */
/*   ch 0: base = 0x05600100 (afbd_base),  status at base + 0x28       */
/*   ch 1: base = 0x05600140 (+ stride),   status at base + 0x28       */
/* Reads status 5 times (poll loop), checks bit 1, acks by writing back */
/* ------------------------------------------------------------------ */

irqreturn_t ge2d_afbd_hardirq(int irq, void *data)
{
	struct ge2d_device *gdev = data;
	irqreturn_t ret = IRQ_NONE;
	int ch;

	if (!gdev->afbd_base)
		return IRQ_NONE;

	/*
	 * Stock iterates over 2 channels with stride 0x40.
	 * Channel 0: afbd_base + 0x28  (0x05600128)
	 * Channel 1: afbd_base + 0x40 + 0x28  (0x05600168)
	 */
	for (ch = 0; ch < GE2D_OSD_IRQ_QUEUES; ch++) {
		u32 offset = ch * GE2D_AFBD_IRQ_CHANNEL_STRIDE +
			     GE2D_AFBD_IRQ_STATUS;
		u32 status;

		status = ge2d_reg_read(gdev->afbd_base, offset);
		if (!status)
			continue;

		/* Ack by writing the status back */
		ge2d_reg_write(gdev->afbd_base, offset, status);

		/*
		 * Phase 2: check bit 1 for writeback complete,
		 * signal fence, call AFBD state machine.
		 */

		/* Wake the corresponding OSD IRQ waitqueue */
		if (ch < GE2D_OSD_IRQ_QUEUES) {
			struct ge2d_osd_irq_data *d = &gdev->osd_irq[ch];
			unsigned long flags;

			spin_lock_irqsave(&d->lock, flags);
			d->count++;
			spin_unlock_irqrestore(&d->lock, flags);

			wake_up(&d->wq);
		}

		ret = IRQ_HANDLED;
	}

	return ret;
}
