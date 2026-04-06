#include <linux/math64.h>
// SPDX-License-Identifier: GPL-2.0+
/*
 * Allwinner H713 AV1 Hardware Decoder Driver - Debug Interface
 *
 * Copyright (C) 2025 HY300 Linux Porting Project
 *
 * This file implements the debugfs interface for the H713 AV1 decoder.
 */

#include <linux/debugfs.h>
#include <linux/seq_file.h>
#include <linux/uaccess.h>
#include "sun50i-h713-av1.h"

static struct dentry *av1_debugfs_root;

/**
 * av1_debugfs_status_show - Show decoder status
 */
static int av1_debugfs_status_show(struct seq_file *s, void *data)
{
	struct sun50i_av1_dev *dev = s->private;
	u32 status, ctrl;

	status = av1_read(dev, AV1_REG_STATUS);
	ctrl = av1_read(dev, AV1_REG_CTRL);

	seq_printf(s, "AV1 Decoder Status:\n");
	seq_printf(s, "  Control Register: 0x%08x\n", ctrl);
	seq_printf(s, "  Status Register:  0x%08x\n", status);
	seq_printf(s, "  Hardware State:   %s\n",
		   (status & AV1_STATUS_IDLE) ? "IDLE" :
		   (status & AV1_STATUS_BUSY) ? "BUSY" : "UNKNOWN");
	seq_printf(s, "  Error Status:     %s\n",
		   (status & AV1_STATUS_ERROR) ? "ERROR" : "OK");
	seq_printf(s, "  Active Instances: %d\n", atomic_read(&dev->num_inst));
	seq_printf(s, "  Suspended:        %s\n", dev->suspended ? "YES" : "NO");

	return 0;
}

DEFINE_SHOW_ATTRIBUTE(av1_debugfs_status);

/**
 * av1_debugfs_metrics_show - Show metrics
 */
static int av1_debugfs_metrics_show(struct seq_file *s, void *data)
{
	seq_printf(s, "AV1 Decoder Metrics:\n");
	seq_printf(s, "  Frames Decoded:     %llu\n",
		   atomic64_read(&av1_metrics.frames_decoded));
	seq_printf(s, "  Decode Errors:      %llu\n",
		   atomic64_read(&av1_metrics.decode_errors));
	seq_printf(s, "  Hardware Resets:    %llu\n",
		   atomic64_read(&av1_metrics.hw_resets));
	seq_printf(s, "  Current Sessions:   %d\n",
		   atomic_read(&av1_metrics.current_sessions));
	seq_printf(s, "  Total Decode Time:  %llu us\n",
		   av1_metrics.total_decode_time_us);

	if (atomic64_read(&av1_metrics.frames_decoded) > 0) {
		u64 avg_time = div_u64(av1_metrics.total_decode_time_us, atomic64_read(&av1_metrics.frames_decoded));
		seq_printf(s, "  Average Decode Time: %llu us\n", avg_time);
	}

	return 0;
}

DEFINE_SHOW_ATTRIBUTE(av1_debugfs_metrics);

/**
 * av1_debugfs_regs_show - Show hardware registers
 */
static int av1_debugfs_regs_show(struct seq_file *s, void *data)
{
	struct sun50i_av1_dev *dev = s->private;

	seq_printf(s, "AV1 Hardware Registers:\n");
	seq_printf(s, "  CTRL:              0x%08x\n", av1_read(dev, AV1_REG_CTRL));
	seq_printf(s, "  STATUS:            0x%08x\n", av1_read(dev, AV1_REG_STATUS));
	seq_printf(s, "  INT_ENABLE:        0x%08x\n", av1_read(dev, AV1_REG_INT_ENABLE));
	seq_printf(s, "  INT_STATUS:        0x%08x\n", av1_read(dev, AV1_REG_INT_STATUS));
	seq_printf(s, "  FRAME_CONFIG:      0x%08x\n", av1_read(dev, AV1_REG_FRAME_CONFIG));
	seq_printf(s, "  METADATA_ADDR:     0x%08x\n", av1_read(dev, AV1_REG_METADATA_ADDR));
	seq_printf(s, "  METADATA_SIZE:     0x%08x\n", av1_read(dev, AV1_REG_METADATA_SIZE));
	seq_printf(s, "  OUTPUT_ADDR_Y:     0x%08x\n", av1_read(dev, AV1_REG_OUTPUT_ADDR_Y));
	seq_printf(s, "  OUTPUT_ADDR_U:     0x%08x\n", av1_read(dev, AV1_REG_OUTPUT_ADDR_U));
	seq_printf(s, "  OUTPUT_ADDR_V:     0x%08x\n", av1_read(dev, AV1_REG_OUTPUT_ADDR_V));
	seq_printf(s, "  OUTPUT_STRIDE:     0x%08x\n", av1_read(dev, AV1_REG_OUTPUT_STRIDE));
	seq_printf(s, "  DECODE_START:      0x%08x\n", av1_read(dev, AV1_REG_DECODE_START));

	return 0;
}

DEFINE_SHOW_ATTRIBUTE(av1_debugfs_regs);

/**
 * av1_debugfs_reset_write - Reset hardware via debugfs
 */
static ssize_t av1_debugfs_reset_write(struct file *file,
					const char __user *user_buf,
					size_t count, loff_t *ppos)
{
	struct sun50i_av1_dev *dev = file->private_data;
	char buf[16];
	int ret;

	if (count >= sizeof(buf))
		return -EINVAL;

	if (copy_from_user(buf, user_buf, count))
		return -EFAULT;

	buf[count] = '\0';

	if (strncmp(buf, "reset", 5) == 0) {
		mutex_lock(&dev->dev_mutex);
		ret = sun50i_av1_hw_reset(dev);
		mutex_unlock(&dev->dev_mutex);

		if (ret) {
			dev_err(dev->dev, "Hardware reset failed: %d\n", ret);
			return ret;
		}

		dev_info(dev->dev, "Hardware reset via debugfs\n");
	} else {
		return -EINVAL;
	}

	return count;
}

static const struct file_operations av1_debugfs_reset_fops = {
	.open = simple_open,
	.write = av1_debugfs_reset_write,
	.llseek = default_llseek,
};

/**
 * sun50i_av1_debugfs_init - Initialize debugfs interface
 * @dev: Device context
 */
void sun50i_av1_debugfs_init(struct sun50i_av1_dev *dev)
{
	if (!av1_debugfs_root) {
		av1_debugfs_root = debugfs_create_dir("sun50i-h713-av1", NULL);
		if (IS_ERR(av1_debugfs_root)) {
			dev_warn(dev->dev, "Failed to create debugfs root\n");
			av1_debugfs_root = NULL;
			return;
		}
	}

	if (!av1_debugfs_root)
		return;

	debugfs_create_file("status", 0444, av1_debugfs_root, dev,
			    &av1_debugfs_status_fops);

	debugfs_create_file("metrics", 0444, av1_debugfs_root, NULL,
			    &av1_debugfs_metrics_fops);

	debugfs_create_file("registers", 0444, av1_debugfs_root, dev,
			    &av1_debugfs_regs_fops);

	debugfs_create_file("reset", 0200, av1_debugfs_root, dev,
			    &av1_debugfs_reset_fops);

	dev_dbg(dev->dev, "Debugfs interface initialized\n");
}

/**
 * sun50i_av1_debugfs_cleanup - Cleanup debugfs interface
 * @dev: Device context
 */
void sun50i_av1_debugfs_cleanup(struct sun50i_av1_dev *dev)
{
	debugfs_remove_recursive(av1_debugfs_root);
	av1_debugfs_root = NULL;

	dev_dbg(dev->dev, "Debugfs interface cleaned up\n");
}
