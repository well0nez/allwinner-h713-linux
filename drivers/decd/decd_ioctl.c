// SPDX-License-Identifier: GPL-2.0

#include <linux/pm_runtime.h>
#include <linux/uaccess.h>

#include "decd_types.h"

/*
 * dec_stop_video_stream — IDA 0x1eec
 *
 * IDA: null check → mutex_lock → dec_is_enabled check →
 *      if enabled: frame_manager_stop
 *      if not: dev_err
 *      mutex_unlock
 */
int dec_stop_video_stream(struct dec_device *dec)
{
	int ret = 0;

	if (!dec)
		return 0;

	mutex_lock(&dec->lock);
	if (dec->enabled)
		ret = dec_frame_manager_stop(dec->fmgr);
	else
		dev_err(dec->dev, "dec is not enabled!\n");
	mutex_unlock(&dec->lock);
	return ret;
}

/*
 * dec_frame_submit — IDA 0x25d4
 *
 * IDA shows:
 *   - mutex_lock(a1) at entry
 *   - check dec_is_enabled via callback at a1+724
 *   - blue_en byte at a2+1 (= desc->reserved0[0])
 *   - loop: refcount_inc + enqueue while a4-- > 1
 *   - fence_fd = dec_fence_fd_create(item+52)
 *   - frame_item_release(item)
 *   - dec_reg_blue_en(regs, byte at a2+1)
 *   - dec_reg_enable(regs, 1)
 *   - mutex_unlock(a1)
 *   - always returns 0
 */
int dec_frame_submit(struct dec_device *dec,
		     struct dec_frame_submit_desc *desc,
		     int *release_fence_fd, int repeat)
{
	struct dec_frame_item *item;

	if (!dec || !desc)
		return 0;

	if (release_fence_fd)
		*release_fence_fd = -1;

	mutex_lock(&dec->lock);
	if (!dec->enabled) {
		dev_err(dec->dev, "dec is not enabled!\n");
		goto out;
	}

	if (!desc->reserved0[0]) {
		item = frame_item_create(dec, desc);
		if (item) {
			do {
				refcount_inc(&item->refcount);
				dec_frame_manager_enqueue_frame(dec->fmgr,
					item, frame_item_release);
			} while (repeat-- > 1);

			if (release_fence_fd)
				*release_fence_fd = dec_fence_fd_create(item->fence);
			frame_item_release(item);
		}
	}
	dec_reg_blue_en(dec->regs, desc->reserved0[0]);
	dec_reg_enable(dec->regs, true);
out:
	mutex_unlock(&dec->lock);
	return 0;
}

/*
 * dec_interlace_setup — IDA 0x22b4
 *
 * Same pattern: mutex_lock, check enabled, create top+bottom,
 * enqueue_interlace, blue_en, reg_enable, mutex_unlock.
 */
int dec_interlace_setup(struct dec_device *dec,
			struct dec_interlace_setup_desc *desc)
{
	struct dec_frame_item *top;
	struct dec_frame_item *bottom;

	if (!dec || !desc)
		return 0;

	mutex_lock(&dec->lock);
	if (!dec->enabled) {
		dev_err(dec->dev, "dec is not enabled!\n");
		goto out;
	}

	if (!desc->top.reserved0[0]) {
		/* IDA 0x22b4: set stream type to interlace BEFORE creating items */
		dec_frame_manager_set_stream_type(dec->fmgr, 1);
		top = frame_item_create(dec, &desc->top);
		bottom = frame_item_create(dec, &desc->bottom);
		if (!top || !bottom) {
			frame_item_release(top);
			frame_item_release(bottom);
			goto skip;
		}
		dec_frame_manager_enqueue_interlace_frame(dec->fmgr, top,
						  bottom, frame_item_release);
	}
skip:
	dec_reg_blue_en(dec->regs, desc->top.reserved0[0]);
	dec_reg_enable(dec->regs, true);
out:
	mutex_unlock(&dec->lock);
	return 0;
}

long dec_ioctl_file(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct dec_device *dec = file->private_data;
	struct dec_ioctl_header hdr;
	struct dec_frame_submit_desc submit;
	struct dec_interlace_setup_desc interlace;
	struct dec_linear_map_req mapreq;
	u64 ts;
	int fence_fd = -1;
	int ret;

	if (copy_from_user(&hdr, (void __user *)arg, sizeof(hdr)))
		return -EFAULT;

	switch (cmd) {
	case DECD_IOC_STOP_VIDEO_STREAM:
		return dec_stop_video_stream(dec);
	case DECD_IOC_BYPASS_CONFIG:
		dec_reg_bypass_config(dec->regs, (__u32)hdr.user_ptr);
		return 0;
	case DECD_IOC_PM_HINT:
		if (hdr.user_ptr)
			pm_runtime_get_sync(dec->dev);
		else
			pm_runtime_put_sync(dec->dev);
		return 0;
	case DECD_IOC_GET_VSYNC_TS:
		ret = dec_vsync_timestamp_get(dec, &ts);
		if (ret)
			return ret;
		if (copy_to_user((void __user *)(uintptr_t)hdr.user_ptr, &ts,
				 sizeof(ts)))
			return -EFAULT;
		return 0;
	case DECD_IOC_MAP_LINEAR_BUFFER:
		if (copy_from_user(&mapreq, (void __user *)(uintptr_t)hdr.user_ptr,
				   sizeof(mapreq)))
			return -EFAULT;
		ret = video_buffer_map(mapreq.phys, mapreq.size, &mapreq.dma_addr);
		if (ret)
			return ret;
		mapreq.reserved = 0;
		if (copy_to_user((void __user *)(uintptr_t)hdr.user_ptr, &mapreq,
				 sizeof(mapreq)))
			return -EFAULT;
		return 0;
	case DECD_IOC_FRAME_SUBMIT:
		if (copy_from_user(&submit, (void __user *)(uintptr_t)hdr.user_ptr,
				   sizeof(submit)))
			return -EFAULT;
		ret = dec_frame_submit(dec, &submit, &fence_fd, hdr.arg1);
		if (ret)
			return ret;
		if (copy_to_user((void __user *)(uintptr_t)hdr.user_ptr2, &fence_fd,
				 sizeof(fence_fd)))
			return -EFAULT;
		return 0;
	case DECD_IOC_INTERLACE_SETUP:
		if (copy_from_user(&interlace, (void __user *)(uintptr_t)hdr.user_ptr,
				   sizeof(interlace)))
			return -EFAULT;
		return dec_interlace_setup(dec, &interlace);
	default:
		dev_err(dec->dev, "Unknown cmd: 0x%x\n", cmd);
		return 0;
	}
}
