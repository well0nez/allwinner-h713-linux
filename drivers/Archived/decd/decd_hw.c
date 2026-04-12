// SPDX-License-Identifier: GPL-2.0

#include <linux/bitops.h>
#include <linux/clk.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/pm_runtime.h>

#include "decd_types.h"

/* Module-level globals matching IDA observations */
static int invert_field;
static int iommu_debug;
static u32 dec_vsync_counter;

/*
 * dec_reg_set_address — IDA 0x3834
 *
 * CRITICAL: IDA shows base = *(result+8) = regs->workaround (= afbd+0x60),
 * NOT regs->afbd. Offsets verified directly from IDA switch/case:
 *   idx 0: Y@+16 C@+36 Yaux@+32 Caux@+52 info@+56 field@+72
 *   idx 1: Y@+20 C@+40 Yaux@+33 Caux@+53 info@+60 field@+73
 *   idx 2: Y@+24 C@+44 Yaux@+34 Caux@+54 info@+64 field@+74
 *   idx 3: Y@+28 C@+48 Yaux@+35 Caux@+55 info@+68 field@+75
 */
void dec_reg_set_address(struct dec_reg_block *regs, u32 *planes, u32 aux,
			 char field, int idx)
{
	void __iomem *base;
	/* IDA-verified offset tables — base is regs->workaround */
	static const u32 y_off[]     = { 16, 20, 24, 28 };
	static const u32 c_off[]     = { 36, 40, 44, 48 };
	static const u32 y_aux_off[] = { 32, 33, 34, 35 };
	static const u32 c_aux_off[] = { 52, 53, 54, 55 };
	static const u32 info_off[]  = { 56, 60, 64, 68 };
	static const u32 field_off[] = { 72, 73, 74, 75 };

	if (!regs || !regs->workaround || idx < 0 || idx > 3)
		return;

	base = regs->workaround;
	writel(planes[0], base + y_off[idx]);
	writel(planes[2], base + c_off[idx]);
	writeb(planes[1], base + y_aux_off[idx]);
	writeb(planes[3], base + c_aux_off[idx]);
	writel(aux, base + info_off[idx]);
	writeb(field, base + field_off[idx]);
}

/*
 * dec_sync_frame_to_hardware — IDA 0x29b4
 *
 * Called as sync_cb from queue with (dec, payload, blank, idx, alt_field).
 * IDA shows: uses blue_en byte at payload+1, iommu_debug global, invert_field global.
 * idx==2 → set_filed_mode, idx==3 → set_filed_repeat + set_dirty.
 */
static void dec_sync_frame_to_hardware(struct dec_device *dec,
				       void *frame_payload,
				       bool blank,
				       int idx,
				       bool alt_field)
{
	struct dec_frame_item *item = frame_payload;
	u32 planes[4] = { 0 };
	u32 aux = 0;
	u32 fmt = 0;
	bool field_mode = alt_field;
	bool repeat_mode = false;

	if (!blank && item) {
		planes[0] = alt_field ? lower_32_bits(item->y_addr_alt)
				      : lower_32_bits(item->y_addr);
		planes[2] = alt_field ? lower_32_bits(item->c_addr_alt)
				      : lower_32_bits(item->c_addr);
		planes[1] = item->y_aux;
		planes[3] = item->c_aux;
		aux = item->video_info_addr;
		fmt = item->format_shadow;
		repeat_mode = item->alt_c_valid;
		if (iommu_debug) {
			planes[0] |= 0x80000000u;
			planes[2] |= 0x80000000u;
		}
	}

	dec_reg_set_address(dec->regs, planes, aux, blank ? 0 : planes[1], idx);
	dec_debug_trace_frame(planes[0], fmt);

	if (idx == 2) {
		/* IDA: if invert_field && split_fields && !invert_field_flag → flip */
		if (invert_field && item && item->alt_y_valid && !item->alt_c_valid)
			field_mode = !alt_field;
		dec_reg_set_filed_mode(dec->regs, field_mode);
	} else if (idx == 3) {
		dec_reg_set_filed_repeat(dec->regs, repeat_mode);
		dec_reg_set_dirty(dec->regs, true);
	}
}

int dec_reg_video_channel_attr_config(struct dec_reg_block *regs, u32 *cfg)
{
	void __iomem *base;
	u32 mode;
	u32 val;
	u8 b16;
	u8 b19;

	if (!regs || !regs->afbd || !cfg)
		return 0;

	base = regs->afbd;
	mode = cfg[1];
	b16 = readb(base + 16);
	b19 = readb(base + 19);
	val = cfg[0];

	if (mode == 1) {
		if (val) {
			writeb(b16 & 0xef, base + 16);
			writeb(1, base + 17);
			writeb((b19 & 0x78) | 0x83, base + 19);
			writew(cfg[2] - 1, base + 32);
			writew(cfg[3] - 1, base + 34);
			writew((cfg[2] - 1) >> 4, base + 36);
			writew((cfg[3] - 1) >> 4, base + 38);
			writel(0, base + 64);
			writel(0, base + 68);
			writel(0, base + 72);
			writel(0, base + 76);
		} else {
			writeb(b16 | 0x10, base + 16);
			writeb(6, base + 17);
			writew(val, base + 32);
			writew(val, base + 34);
			writeb((b19 & 0x78) | 3 | ((val & 1) << 7), base + 19);
			writew(val, base + 36);
			writew(val, base + 38);
			writel(2 * cfg[2], base + 64);
			writel(2 * cfg[2], base + 68);
			writew(2 * ((u16 *)cfg)[4], base + 72);
			writew(cfg[3], base + 74);
			writew(2 * ((u16 *)cfg)[4], base + 76);
			writew(cfg[3] >> 1, base + 78);
		}
	} else if (mode == 20) {
		if (val) {
			writeb(b16 & 0xef, base + 16);
			writeb(1, base + 17);
			writeb((b19 & 0x78) | 0x83, base + 19);
			writew(cfg[2] - 1, base + 32);
			writew(cfg[3] - 1, base + 34);
			writew((cfg[2] - 1) >> 4, base + 36);
			writew((cfg[3] - 1) >> 4, base + 38);
			writel(0, base + 64);
			writel(0, base + 68);
			writel(0, base + 72);
			writel(0, base + 76);
		} else {
			writeb(b16 | 0x10, base + 16);
			writeb(7, base + 17);
			writew(val, base + 32);
			writew(val, base + 34);
			writeb((b19 & 0x78) | 3 | ((val & 1) << 7), base + 19);
			writew(val, base + 36);
			writew(val, base + 38);
			writel(2 * cfg[2], base + 64);
			writel(2 * cfg[2], base + 68);
			writew(2 * ((u16 *)cfg)[4], base + 72);
			writew(cfg[3], base + 74);
			writew(2 * ((u16 *)cfg)[4], base + 76);
			writew(cfg[3] >> 1, base + 78);
		}
	}

	return 0;
}

void dec_reg_top_enable(struct dec_reg_block *regs, bool on)
{
	if (!regs || !regs->top || !regs->afbd)
		return;

	writeb((readb(regs->top + 0x00) & ~BIT(0)) | (on ? BIT(0) : 0), regs->top + 0x00);
	writeb((readb(regs->top + 0x00) & ~BIT(4)) | (on ? BIT(4) : 0), regs->top + 0x00);
	writeb((readb(regs->top + 0x01) & ~BIT(0)) | (on ? BIT(0) : 0), regs->top + 0x01);
	writeb((readb(regs->top + 0x02) & ~BIT(0)) | (on ? BIT(0) : 0), regs->top + 0x02);
	writeb((readb(regs->top + 0x04) & ~BIT(0)) | (on ? BIT(0) : 0), regs->top + 0x04);
	writel(0xffffffff, regs->top + 0x08);
	writel(0xffffffff, regs->top + 0x0c);
	writel(0xffffffff, regs->top + 0x10);
	writel(0xffffffff, regs->top + 0x14);
	writel(0xffffffff, regs->top + 0x18);
	writel(0xffffffff, regs->top + 0x1c);
	writeb((readb(regs->afbd + 0x03) & ~BIT(7)) | (on ? BIT(7) : 0), regs->afbd + 0x03);
}

/*
 * dec_reg_enable — IDA 0x3770
 * IDA: base = *(result+8) = regs->workaround
 * Offsets: +9, +0, +100
 */
void dec_reg_enable(struct dec_reg_block *regs, bool on)
{
	u8 v;

	if (!regs || !regs->workaround)
		return;

	writeb(readb(regs->workaround + 9) | BIT(0), regs->workaround + 9);
	v = readb(regs->workaround + 0);
	writeb((v & ~BIT(0)) | (on ? BIT(0) : 0), regs->workaround + 0);
	v = readb(regs->workaround + 100);
	writeb((v & ~BIT(0)) | (on ? BIT(0) : 0), regs->workaround + 100);
}

/*
 * dec_reg_mux_select — IDA 0x37b0
 * IDA: base = *(result+8) = regs->workaround, offset +8
 */
void dec_reg_mux_select(struct dec_reg_block *regs, u8 mux)
{
	u8 v;

	if (!regs || !regs->workaround)
		return;

	mux &= 0x3;
	v = readb(regs->workaround + 8);
	v = (v & ~0x03) | mux;
	v = (v & ~0x30) | (mux << 4);
	writeb(v, regs->workaround + 8);
}

void dec_decoder_display_init(struct dec_reg_block *regs)
{
	dec_reg_mux_select(regs, 2);
}

/* IDA 0x37e0: *(*(result+8)) |= 0x10 → workaround base */
void dec_reg_int_to_display(struct dec_reg_block *regs)
{
	if (regs && regs->workaround)
		writeb(readb(regs->workaround + 0) | BIT(4), regs->workaround + 0);
}

void dec_reg_int_to_display_atomic(struct dec_reg_block *regs)
{
	dec_reg_int_to_display(regs);
}

/* IDA: blue_en uses workaround base (result+8), offset +16 bit 4 */
void dec_reg_blue_en(struct dec_reg_block *regs, bool on)
{
	u8 v;

	if (!regs || !regs->workaround)
		return;

	v = readb(regs->workaround + 16);
	writeb((v & ~BIT(4)) | (on ? BIT(4) : 0), regs->workaround + 16);
}

/*
 * dec_reg_set_filed_mode — IDA 0x3970
 * IDA: *(*(result+8) + 4) = base is regs->workaround, NOT regs->afbd!
 */
void dec_reg_set_filed_mode(struct dec_reg_block *regs, bool on)
{
	u8 v;

	if (!regs || !regs->workaround)
		return;

	v = readb(regs->workaround + 0x04);
	writeb((v & ~BIT(0)) | (on ? BIT(0) : 0), regs->workaround + 0x04);
}

/*
 * dec_reg_set_filed_repeat — IDA 0x398c
 * IDA: *(*(result+8) + 4) bit 4 = also regs->workaround base
 */
void dec_reg_set_filed_repeat(struct dec_reg_block *regs, bool on)
{
	u8 v;

	if (!regs || !regs->workaround)
		return;

	v = readb(regs->workaround + 0x04);
	writeb((v & ~BIT(4)) | (on ? BIT(4) : 0), regs->workaround + 0x04);
}

/* IDA 0x39f8: *(result+8) = workaround, offset +12 */
void dec_reg_set_dirty(struct dec_reg_block *regs, bool dirty)
{
	if (!regs || !regs->workaround)
		return;

	regs->dirty = dirty;
	writel(dirty, regs->workaround + 12);
}

/* IDA 0x3a10: just reads result+12 = regs->dirty byte */
bool dec_reg_is_dirty(struct dec_reg_block *regs)
{
	return regs && regs->dirty;
}

/* IDA 0x3a20: *(*(result+8) + 92) = workaround+92 */
u32 dec_reg_frame_cnt(struct dec_reg_block *regs)
{
	return regs && regs->workaround ? readl(regs->workaround + 92) : 0;
}

/* IDA 0x3a34: *(*(result+8) + 16/20) = workaround+16/20 */
u32 dec_reg_get_y_address(struct dec_reg_block *regs, int idx)
{
	if (!regs || !regs->workaround)
		return 0;
	if (idx == 0)
		return readl(regs->workaround + 16);
	if (idx == 1)
		return readl(regs->workaround + 20);
	return 0;
}

/* IDA 0x3a6c: *(*(result+8) + 36/40) = workaround+36/40 */
u32 dec_reg_get_c_address(struct dec_reg_block *regs, int idx)
{
	if (!regs || !regs->workaround)
		return 0;
	if (idx == 0)
		return readl(regs->workaround + 36);
	if (idx == 1)
		return readl(regs->workaround + 40);
	return 0;
}

/* IDA: bypass_config uses workaround base, offset +9 and +12 */
void dec_reg_bypass_config(struct dec_reg_block *regs, u32 value)
{
	u8 v;

	if (!regs || !regs->workaround)
		return;

	v = readb(regs->workaround + 9);
	writeb((v & ~BIT(0)) | (!value ? BIT(0) : 0), regs->workaround + 9);
	writel(1, regs->workaround + 12);
}

/* IDA 0x39c8: *(result+8) = workaround, offsets +96 and +100 */
int dec_irq_query(struct dec_reg_block *regs)
{
	u8 s0, s1;

	if (!regs || !regs->workaround)
		return 0;

	s0 = readb(regs->workaround + 96);
	if (!(s0 & BIT(0)))
		return 0;
	s1 = readb(regs->workaround + 100);
	if (!(s1 & BIT(0)))
		return 0;
	writeb(s0 | BIT(0), regs->workaround + 96);
	return 1;
}

void dec_sync_interlace_cfg_to_hardware(struct dec_reg_block *regs,
					struct dec_video_frame *vf)
{
	if (!vf)
		return;

	dec_reg_set_filed_mode(regs, true);
	dec_reg_set_dirty(regs, true);
}

/*
 * dec_enable — IDA 0x2ed4
 * Sequence: deassert reset → clk_bus → clk_afbd → set_rate → request_irq →
 *           frame_manager_init → register callbacks → top_enable → display_init
 */
int dec_enable(struct dec_device *dec)
{
	int ret;

	mutex_lock(&dec->lock);
	if (dec->enabled) {
		ret = 0;
		goto out;
	}

	ret = reset_control_deassert(dec->rst_bus_disp);
	if (ret)
		goto out;
	ret = clk_prepare_enable(dec->clk_bus_disp);
	if (ret)
		goto err_reset;
	ret = clk_prepare_enable(dec->clk_afbd);
	if (ret)
		goto err_bus;
	clk_set_rate(dec->clk_afbd, dec->clk_rate);
	enable_irq(dec->irq);
	dec->fmgr = dec_frame_manager_init();
	if (!dec->fmgr) {
		ret = -EINVAL;
		goto err_irq;
	}
	dec_frame_manager_register_sync_cb(dec->fmgr, dec,
					 dec_sync_frame_to_hardware);
	dec_frame_manager_register_repeat_ctrl_pfn(dec->fmgr, dec->regs,
						   dec_reg_set_filed_repeat);
	dec_reg_top_enable(dec->regs, true);
	dec_decoder_display_init(dec->regs);
	dec->enabled = true;
	ret = 0;
	goto out;
err_irq:
	disable_irq(dec->irq);
err_afbd:
	clk_disable_unprepare(dec->clk_afbd);
err_bus:
	clk_disable_unprepare(dec->clk_bus_disp);
err_reset:
	reset_control_assert(dec->rst_bus_disp);
out:
	mutex_unlock(&dec->lock);
	return ret;
}

int dec_disable(struct dec_device *dec)
{
	mutex_lock(&dec->lock);
	if (dec->enabled) {
		dec_frame_manager_stop(dec->fmgr);
		disable_irq(dec->irq);
		dec_frame_manager_exit(dec->fmgr);
		dec->fmgr = NULL;
		dec_reg_int_to_display(dec->regs);
		dec_reg_enable(dec->regs, false);
		reset_control_assert(dec->rst_bus_disp);
		clk_disable_unprepare(dec->clk_bus_disp);
		clk_disable_unprepare(dec->clk_afbd);
		dec->enabled = false;
	}
	mutex_unlock(&dec->lock);
	return 0;
}

int dec_vsync_timestamp_get(struct dec_device *dec, u64 *ts)
{
	unsigned long flags;
	u32 next;

	spin_lock_irqsave(&dec->vsync->lock, flags);
	if (dec->vsync->rd == dec->vsync->wr) {
		spin_unlock_irqrestore(&dec->vsync->lock, flags);
		return -EAGAIN;
	}
	next = (dec->vsync->rd + 1) & (DECD_VSYNC_RING_LEN - 1);
	*ts = dec->vsync->ts[next];
	dec->vsync->rd = next;
	spin_unlock_irqrestore(&dec->vsync->lock, flags);
	return 0;
}

__poll_t dec_event_poll(struct dec_device *dec, struct file *file,
			poll_table *wait)
{
	unsigned long flags;
	__poll_t mask = 0;

	poll_wait(file, &dec->event_wait, wait);
	spin_lock_irqsave(&dec->vsync->lock, flags);
	if (dec->vsync->rd != dec->vsync->wr)
		mask |= EPOLLIN | EPOLLRDNORM;
	spin_unlock_irqrestore(&dec->vsync->lock, flags);
	return mask;
}

/*
 * dec_vsync_handler — IDA 0x273c
 *
 * IDA shows after timestamp ring update:
 *   1. wake_up
 *   2. jiffies_hist tracking: debug->jiffies_hist[pos+2] = jiffies, pos++, wrap at 100
 *   3. debug->irq_count++
 *   4. if fmgr → dec_vsync_process
 *   5. dec_vsync_counter++ (global)
 */
irqreturn_t dec_vsync_handler(int irq, void *data)
{
	struct dec_device *dec = data;
	unsigned long flags;
	u32 next;
	u32 jpos;

	if (!dec_irq_query(dec->regs))
		return IRQ_NONE;

	spin_lock_irqsave(&dec->vsync->lock, flags);
	next = (dec->vsync->wr + 1) & (DECD_VSYNC_RING_LEN - 1);
	dec->vsync->ts[next] = ktime_get_ns();
	dec->vsync->wr = next;
	if (dec->vsync->wr == dec->vsync->rd)
		dec->vsync->rd = (dec->vsync->rd + 1) & (DECD_VSYNC_RING_LEN - 1);
	spin_unlock_irqrestore(&dec->vsync->lock, flags);

	wake_up_interruptible(&dec->event_wait);

	/* IDA: jiffies tracking in debug block */
	if (dec->debug) {
		jpos = dec->debug->jiffies_pos;
		dec->debug->jiffies_hist[jpos + 2] = jiffies;
		jpos++;
		if (jpos >= 100)
			jpos = 0;
		dec->debug->jiffies_pos = jpos;
		dec->debug->irq_count++;
	}

	/* IDA: if fmgr exists → process vsync */
	dec_frame_manager_handle_vsync(dec->fmgr);

	/* IDA: global counter */
	dec_vsync_counter++;

	return IRQ_HANDLED;
}
