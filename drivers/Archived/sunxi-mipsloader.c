// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner MIPS Co-processor Loader Driver
 * 
 * Copyright (C) 2025 HY300 Linux Porting Project
 * 
 * This driver provides support for the MIPS co-processor found in
 * Allwinner H713 SoC, specifically for the HY300 projector hardware.
 * The MIPS co-processor handles display engine control, panel timing,
 * and projector-specific hardware management.
 * 
 *
 * Memory Layout (validated from Android libmips.so analysis - Task 032):
 * ========================================================================
 * Physical Base Address: 0x4b100000
 * Total Reserved Memory: 40MB (0x2800000)
 *
 * Region Breakdown:
 *   Boot Region:       4KB @ offset 0x00000 (0x4b100000)
 *     - MIPS bootloader and reset vector
 *     - Minimal initialization code
 *
 *   Firmware Region:  12MB @ offset 0x01000 (0x4b101000)
 *     - Main MIPS firmware (display.bin from factory)
 *     - Display engine control logic
 *     - HDMI input processing and downscaling (1080p to 720p)
 *
 *   TSE Region:        1MB @ offset 0xC01000 (0x4bd01000)
 *     - Transport Stream Engine buffer
 *     - Video stream processing workspace
 *
 *   Framebuffer:      26MB @ offset 0xD01000 (0x4be01000)
 *     - Display framebuffer for 1280x720 native panel
 *     - Multiple buffering support (26MB = ~14 full 720p RGBA buffers)
 *
 * Based on reverse engineering of factory Android implementation.
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/io.h>
#include <linux/ioctl.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/firmware.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/of_reserved_mem.h>
#include <linux/crc32.h>
#include <linux/crypto.h>
#include <linux/delay.h>
#include <linux/sysfs.h>

/*
 * MIPS Memory Layout - Validated from Android libmips.so (Task 032)
 *
 * Note: Android analysis shows different region offsets than initial reverse engineering.
 * Below defines updated to match Android-validated memory map.
 */
#define MIPS_BOOT_CODE_ADDR     0x4b100000  /* 4KB - MIPS reset vector */
#define MIPS_FIRMWARE_ADDR      0x4b101000  /* 12MB - Main MIPS firmware */
#define MIPS_TSE_ADDR           0x4bd01000  /* 1MB - Transport Stream Engine */
/* CONFIG and DATABASE regions merged into TSE in Android implementation */
/* Legacy MIPS_DEBUG_ADDR aliased to MIPS_TSE_ADDR for compatibility */
#define MIPS_FRAMEBUFFER_ADDR   0x4be01000  /* 26MB - Framebuffer (1280x720) */
#define MIPS_DEBUG_ADDR         MIPS_TSE_ADDR  /* Legacy alias */
#define MIPS_TOTAL_SIZE         0x2800000   /* 40MB total */

/* Register Interface (from factory analysis) */
#define MIPS_REG_CMD            0x00    /* Command register */
#define MIPS_REG_STATUS         0x04    /* Status register */
#define MIPS_REG_DATA           0x08    /* Data register */
#define MIPS_REG_CONTROL        0x0c    /* Control register */

/* Panel Timing Configuration (from factory) */
#define PANEL_HTOTAL_TYP        2200
#define PANEL_HTOTAL_MIN        2095
#define PANEL_HTOTAL_MAX        2809
#define PANEL_VTOTAL_TYP        1125
#define PANEL_VTOTAL_MIN        1107
#define PANEL_VTOTAL_MAX        1440
#define PANEL_PCLK_TYP          148500000  /* 148.5MHz */
#define PANEL_PCLK_MIN          130000000
#define PANEL_PCLK_MAX          164000000
/* Keystone Correction Limits (from factory analysis) */
#define MAX_KEYSTONE_X          100
#define MAX_KEYSTONE_Y          100

/* MIPS Commands */
#define MIPS_CMD_UPDATE_KEYSTONE 0x10
#define MIPS_CMD_TIMEOUT_MS      1000


/* Device node and class information */
#define MIPSLOADER_DEVICE_NAME  "mipsloader"
#define MIPSLOADER_CLASS_NAME   "mips"

/* IOCTL commands */
#define MIPSLOADER_IOC_MAGIC    'M'
#define MIPSLOADER_IOC_LOAD_FW  _IOW(MIPSLOADER_IOC_MAGIC, 1, char*)
#define MIPSLOADER_IOC_RESTART  _IO(MIPSLOADER_IOC_MAGIC, 2)
#define MIPSLOADER_IOC_POWERDOWN _IO(MIPSLOADER_IOC_MAGIC, 3)
#define MIPSLOADER_IOC_GET_STATUS _IOR(MIPSLOADER_IOC_MAGIC, 4, int)


/**
 * struct keystone_params - Keystone correction parameters
 * @tl_x, @tl_y: Top left corner offset
 * @tr_x, @tr_y: Top right corner offset
 * @bl_x, @bl_y: Bottom left corner offset
 * @br_x, @br_y: Bottom right corner offset
 */
struct keystone_params {
	int tl_x, tl_y;
	int tr_x, tr_y;
	int bl_x, bl_y;
	int br_x, br_y;
};

/**
 * struct mipsloader_metrics - Prometheus metrics tracking
 * @reg_access_count: Count of register accesses by type
 * @firmware_load_attempts: Total firmware load attempts
 * @firmware_load_success: Successful firmware loads
 * @firmware_load_failures: Failed firmware loads
 * @memory_regions_used: Active memory regions
 * @communication_errors: Communication error counts
 * @last_firmware_size: Size of last loaded firmware
 * @last_firmware_crc: CRC32 of last loaded firmware
 */
struct mipsloader_metrics {
	/* Register access tracking */
	atomic64_t reg_access_count[4];  /* cmd, status, data, control */
	
	/* Firmware loading metrics */
	atomic64_t firmware_load_attempts;
	atomic64_t firmware_load_success;
	atomic64_t firmware_load_failures;
	
	/* Memory usage tracking */
	atomic64_t memory_regions_used;
	
	/* Error tracking */
	atomic64_t communication_errors;
	
	/* Status information */
	size_t last_firmware_size;
	u32 last_firmware_crc;
};

/**
 * struct mipsloader_device - MIPS loader device structure
 * @pdev: Platform device
 * @reg_base: Register base address (ioremapped)
 * @mem_base: MIPS memory base address (ioremapped) 
 * @mem_size: Size of MIPS memory region
 * @cdev: Character device
 * @device: Device structure
 * @class: Device class
 * @major: Major device number
 * @firmware_loaded: Flag indicating if firmware is loaded
 * @lock: Mutex for device access synchronization
 * @keystone: Current keystone correction parameters
 * @metrics: Prometheus metrics tracking
 */
struct mipsloader_device {
	struct platform_device *pdev;
	void __iomem *reg_base;
	void __iomem *mem_base;
	size_t mem_size;
	struct cdev cdev;
	struct device *device;
	struct class *class;
	int major;
	bool firmware_loaded;
	struct mutex lock;
	struct keystone_params keystone;
	struct mipsloader_metrics metrics;
};

static struct mipsloader_device *mipsloader_dev;
static struct class *hy300_class;

/**
 * mipsloader_reg_offset_to_index - Convert register offset to metrics index
 */
static inline int mipsloader_reg_offset_to_index(u32 offset)
{
	switch (offset) {
	case MIPS_REG_CMD:     return 0;
	case MIPS_REG_STATUS:  return 1;
	case MIPS_REG_DATA:    return 2;
	case MIPS_REG_CONTROL: return 3;
	default:               return -1;
	}
}

/**
 * mipsloader_reg_read - Read from MIPS control register
 * @offset: Register offset
 * 
 * Returns register value
 */
static u32 mipsloader_reg_read(u32 offset)
{
	int idx;
	u32 value;
	
	if (!mipsloader_dev || !mipsloader_dev->reg_base)
		return 0;
	
	idx = mipsloader_reg_offset_to_index(offset);
	if (idx >= 0)
		atomic64_inc(&mipsloader_dev->metrics.reg_access_count[idx]);
	
	value = readl(mipsloader_dev->reg_base + offset);
	return value;
}

/**
 * mipsloader_reg_write - Write to MIPS control register
 * @offset: Register offset
 * @value: Value to write
 */
static void mipsloader_reg_write(u32 offset, u32 value)
{
	int idx;
	
	if (!mipsloader_dev || !mipsloader_dev->reg_base)
		return;
	
	idx = mipsloader_reg_offset_to_index(offset);
	if (idx >= 0)
		atomic64_inc(&mipsloader_dev->metrics.reg_access_count[idx]);
	
	writel(value, mipsloader_dev->reg_base + offset);
}

/**
 * mipsloader_load_firmware - Load MIPS firmware from file
 * @firmware_path: Path to firmware file
 * 
 * Returns 0 on success, negative error code on failure
 */
static int mipsloader_load_firmware(const char *firmware_path)
{
	const struct firmware *fw;
	int ret;
	u32 calculated_crc;
	
	/* Track firmware load attempt */
	atomic64_inc(&mipsloader_dev->metrics.firmware_load_attempts);
	
	if (!mipsloader_dev || !mipsloader_dev->mem_base) {
		pr_err("mipsloader: Device not initialized\n");
		atomic64_inc(&mipsloader_dev->metrics.firmware_load_failures);
		return -ENODEV;
	}
	
	/* Request firmware from userspace */
	ret = request_firmware(&fw, firmware_path, &mipsloader_dev->pdev->dev);
	if (ret) {
		dev_err(&mipsloader_dev->pdev->dev, 
			"Failed to load firmware %s: %d\n", firmware_path, ret);
		atomic64_inc(&mipsloader_dev->metrics.firmware_load_failures);
		return ret;
	}
	
	/* Validate firmware size */
	if (fw->size > (MIPS_FIRMWARE_ADDR - MIPS_BOOT_CODE_ADDR + 0xc00000)) {
		dev_err(&mipsloader_dev->pdev->dev,
			"Firmware too large: %zu bytes\n", fw->size);
		atomic64_inc(&mipsloader_dev->metrics.firmware_load_failures);
		ret = -E2BIG;
		goto release_fw;
	}
	
	/* Calculate CRC32 for validation */
	calculated_crc = crc32(0, fw->data, fw->size);
	dev_info(&mipsloader_dev->pdev->dev,
		"Loading firmware: %zu bytes, CRC32: 0x%08x\n", 
		fw->size, calculated_crc);
	
	/* Copy firmware to MIPS memory region */
	memcpy_toio(mipsloader_dev->mem_base + (MIPS_FIRMWARE_ADDR - MIPS_BOOT_CODE_ADDR),
		    fw->data, fw->size);
	
	/* Ensure write completion */
	wmb();
	
	/* Update metrics on successful load */
	atomic64_inc(&mipsloader_dev->metrics.firmware_load_success);
	atomic64_inc(&mipsloader_dev->metrics.memory_regions_used);
	mipsloader_dev->metrics.last_firmware_size = fw->size;
	mipsloader_dev->metrics.last_firmware_crc = calculated_crc;
	
	mipsloader_dev->firmware_loaded = true;
	dev_info(&mipsloader_dev->pdev->dev, "Firmware loaded successfully\n");
	
	ret = 0;

release_fw:
	release_firmware(fw);
	return ret;
}

/**
 * mipsloader_restart - Restart MIPS co-processor
 * 
 * Returns 0 on success, negative error code on failure
 */
static int mipsloader_restart(void)
{
	if (!mipsloader_dev->firmware_loaded) {
		dev_err(&mipsloader_dev->pdev->dev, 
			"Cannot restart: firmware not loaded\n");
		return -ENOENT;
	}
	
	/* Reset MIPS processor */
	mipsloader_reg_write(MIPS_REG_CONTROL, 0x01);  /* Reset */
	msleep(10);  /* Wait for reset */
	mipsloader_reg_write(MIPS_REG_CONTROL, 0x00);  /* Release reset */
	
	dev_info(&mipsloader_dev->pdev->dev, "MIPS co-processor restarted\n");
	return 0;
}

/**
 * mipsloader_powerdown - Power down MIPS co-processor
 * 
 * Returns 0 on success, negative error code on failure
 */
static int mipsloader_powerdown(void)
{
	/* Send powerdown command */
	mipsloader_reg_write(MIPS_REG_CMD, 0x02);  /* Powerdown command */
	
	/* Wait for acknowledgment */
	msleep(100);
	
	dev_info(&mipsloader_dev->pdev->dev, "MIPS co-processor powered down\n");
	return 0;
}

/**
 * mipsloader_open - Open device node
 */
static int mipsloader_open(struct inode *inode, struct file *file)
{
	if (!mipsloader_dev)
		return -ENODEV;
	
	file->private_data = mipsloader_dev;
	return 0;
}

/**
 * mipsloader_release - Close device node
 */
static int mipsloader_release(struct inode *inode, struct file *file)
{
	return 0;
}

/**
 * mipsloader_ioctl - Handle IOCTL commands
 */
static long mipsloader_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct mipsloader_device *dev = file->private_data;
	int ret = 0;
	char firmware_path[256];
	u32 status;
	
	if (!dev)
		return -ENODEV;
	
	mutex_lock(&dev->lock);
	
	switch (cmd) {
	case MIPSLOADER_IOC_LOAD_FW:
		if (copy_from_user(firmware_path, (char __user *)arg, sizeof(firmware_path))) {
			ret = -EFAULT;
			break;
		}
		firmware_path[sizeof(firmware_path) - 1] = '\0';
		ret = mipsloader_load_firmware(firmware_path);
		break;
		
	case MIPSLOADER_IOC_RESTART:
		ret = mipsloader_restart();
		break;
		
	case MIPSLOADER_IOC_POWERDOWN:
		ret = mipsloader_powerdown();
		break;
		
	case MIPSLOADER_IOC_GET_STATUS:
		status = mipsloader_reg_read(MIPS_REG_STATUS);
		if (copy_to_user((int __user *)arg, &status, sizeof(status)))
			ret = -EFAULT;
		break;
		
	default:
		ret = -ENOTTY;
		break;
	}
	
	mutex_unlock(&dev->lock);
	return ret;
}

static const struct file_operations mipsloader_fops = {
	.owner = THIS_MODULE,
	.open = mipsloader_open,
	.release = mipsloader_release,
	.unlocked_ioctl = mipsloader_ioctl,
	.compat_ioctl = mipsloader_ioctl,
};

/* Sysfs attribute functions for Prometheus metrics */

static ssize_t memory_stats_show(struct device *dev,
				 struct device_attribute *attr, char *buf)
{
	struct mipsloader_device *mips_dev = dev_get_drvdata(dev);
	ssize_t len = 0;
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_memory_usage_bytes Memory usage in MIPS regions\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_memory_usage_bytes gauge\n");
	
	if (mips_dev->firmware_loaded) {
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_memory_usage_bytes{region=\"boot_code\"} 4096\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_memory_usage_bytes{region=\"firmware\"} %zu\n",
			mips_dev->metrics.last_firmware_size);
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_memory_usage_bytes{region=\"debug\"} 1048576\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_memory_usage_bytes{region=\"config\"} 262144\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_memory_usage_bytes{region=\"database\"} 1048576\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_memory_usage_bytes{region=\"framebuffer\"} 27262976\n");
	}
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_memory_regions_active Number of active memory regions\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_memory_regions_active gauge\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_memory_regions_active %lld\n",
		atomic64_read(&mips_dev->metrics.memory_regions_used));
	
	return len;
}
static DEVICE_ATTR_RO(memory_stats);

static ssize_t register_access_count_show(struct device *dev,
					  struct device_attribute *attr, char *buf)
{
	struct mipsloader_device *mips_dev = dev_get_drvdata(dev);
	ssize_t len = 0;
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_register_access_total Total register access count\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_register_access_total counter\n");
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_register_access_total{register=\"cmd\"} %lld\n",
		atomic64_read(&mips_dev->metrics.reg_access_count[0]));
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_register_access_total{register=\"status\"} %lld\n",
		atomic64_read(&mips_dev->metrics.reg_access_count[1]));
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_register_access_total{register=\"data\"} %lld\n",
		atomic64_read(&mips_dev->metrics.reg_access_count[2]));
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_register_access_total{register=\"control\"} %lld\n",
		atomic64_read(&mips_dev->metrics.reg_access_count[3]));
	
	return len;
}
static DEVICE_ATTR_RO(register_access_count);

static ssize_t firmware_status_show(struct device *dev,
				    struct device_attribute *attr, char *buf)
{
	struct mipsloader_device *mips_dev = dev_get_drvdata(dev);
	ssize_t len = 0;
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_firmware_load_attempts_total Total firmware load attempts\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_firmware_load_attempts_total counter\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_firmware_load_attempts_total %lld\n",
		atomic64_read(&mips_dev->metrics.firmware_load_attempts));
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_firmware_load_success_total Successful firmware loads\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_firmware_load_success_total counter\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_firmware_load_success_total %lld\n",
		atomic64_read(&mips_dev->metrics.firmware_load_success));
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_firmware_load_failures_total Failed firmware loads\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_firmware_load_failures_total counter\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_firmware_load_failures_total %lld\n",
		atomic64_read(&mips_dev->metrics.firmware_load_failures));
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_firmware_loaded Current firmware load status\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_firmware_loaded gauge\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_firmware_loaded %d\n",
		mips_dev->firmware_loaded ? 1 : 0);
	
	if (mips_dev->firmware_loaded) {
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"# HELP hy300_mips_firmware_size_bytes Size of loaded firmware\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"# TYPE hy300_mips_firmware_size_bytes gauge\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_firmware_size_bytes %zu\n",
			mips_dev->metrics.last_firmware_size);
		
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"# HELP hy300_mips_firmware_crc32 CRC32 of loaded firmware\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"# TYPE hy300_mips_firmware_crc32 gauge\n");
		len += scnprintf(buf + len, PAGE_SIZE - len,
			"hy300_mips_firmware_crc32 %u\n",
			mips_dev->metrics.last_firmware_crc);
	}
	
	return len;
}
static DEVICE_ATTR_RO(firmware_status);

static ssize_t communication_errors_show(struct device *dev,
					 struct device_attribute *attr, char *buf)
{
	struct mipsloader_device *mips_dev = dev_get_drvdata(dev);
	ssize_t len = 0;
	
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# HELP hy300_mips_communication_errors_total Communication error count\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"# TYPE hy300_mips_communication_errors_total counter\n");
	len += scnprintf(buf + len, PAGE_SIZE - len,
		"hy300_mips_communication_errors_total %lld\n",
		atomic64_read(&mips_dev->metrics.communication_errors));
	
	return len;
}
static DEVICE_ATTR_RO(communication_errors);

/**
 * validate_keystone_params - Validate keystone parameter ranges
 * @params: Keystone parameters to validate
 * 
 * Returns 0 on success, negative error code on failure
 */
static int validate_keystone_params(struct keystone_params *params)
{
	if (abs(params->tl_x) > MAX_KEYSTONE_X ||
	    abs(params->tl_y) > MAX_KEYSTONE_Y ||
	    abs(params->tr_x) > MAX_KEYSTONE_X ||
	    abs(params->tr_y) > MAX_KEYSTONE_Y ||
	    abs(params->bl_x) > MAX_KEYSTONE_X ||
	    abs(params->bl_y) > MAX_KEYSTONE_Y ||
	    abs(params->br_x) > MAX_KEYSTONE_X ||
	    abs(params->br_y) > MAX_KEYSTONE_Y) {
		return -ERANGE;
	}
	
	return 0;
}

/**
 * mips_wait_cmd_complete - Wait for MIPS command completion
 * @timeout_ms: Timeout in milliseconds
 * 
 * Returns 0 on success, -ETIMEDOUT on timeout
 */
static int mips_wait_cmd_complete(unsigned long timeout_ms)
{
	unsigned long timeout = jiffies + msecs_to_jiffies(timeout_ms);
	u32 status;
	
	while (time_before(jiffies, timeout)) {
		status = mipsloader_reg_read(MIPS_REG_STATUS);
		if (!(status & 0x1))
			return 0;
		msleep(10);
	}
	
	return -ETIMEDOUT;
}

/**
 * mips_set_keystone_params - Send keystone parameters to MIPS processor
 * @params: Keystone parameters to set
 * 
 * Returns 0 on success, negative error code on failure
 */
static int mips_set_keystone_params(struct keystone_params *params)
{
	int ret;
	void __iomem *config_addr;
	
	if (!mipsloader_dev || !mipsloader_dev->mem_base) {
		pr_err("mipsloader: Device not initialized\n");
		return -ENODEV;
	}
	
	if (!mipsloader_dev->firmware_loaded) {
		dev_warn(&mipsloader_dev->pdev->dev, 
			 "Firmware not loaded, keystone parameters may not take effect\n");
	}
	
	ret = validate_keystone_params(params);
	if (ret) {
		dev_err(&mipsloader_dev->pdev->dev, 
			"Invalid keystone parameters: values out of range\n");
		return ret;
	}
	
	config_addr = mipsloader_dev->mem_base + (MIPS_TSE_ADDR - MIPS_BOOT_CODE_ADDR);
	memcpy_toio(config_addr, params, sizeof(*params));
	
	mipsloader_reg_write(MIPS_REG_CMD, MIPS_CMD_UPDATE_KEYSTONE);
	
	ret = mips_wait_cmd_complete(MIPS_CMD_TIMEOUT_MS);
	if (ret) {
		dev_err(&mipsloader_dev->pdev->dev, 
			"MIPS keystone update timeout\n");
		atomic64_inc(&mipsloader_dev->metrics.communication_errors);
		return ret;
	}
	
	mipsloader_dev->keystone = *params;
	
	dev_info(&mipsloader_dev->pdev->dev, 
		 "Keystone parameters updated: tl(%d,%d) tr(%d,%d) bl(%d,%d) br(%d,%d)\n",
		 params->tl_x, params->tl_y, params->tr_x, params->tr_y,
		 params->bl_x, params->bl_y, params->br_x, params->br_y);
	
	return 0;
}

/**
 * panelparam_show - Read current keystone correction parameters
 */
static ssize_t panelparam_show(struct device *dev,
			       struct device_attribute *attr, char *buf)
{
	if (!mipsloader_dev)
		return -ENODEV;
	
	return sprintf(buf, "tl_x=%d,tl_y=%d,tr_x=%d,tr_y=%d,bl_x=%d,bl_y=%d,br_x=%d,br_y=%d\n",
		       mipsloader_dev->keystone.tl_x, mipsloader_dev->keystone.tl_y,
		       mipsloader_dev->keystone.tr_x, mipsloader_dev->keystone.tr_y,
		       mipsloader_dev->keystone.bl_x, mipsloader_dev->keystone.bl_y,
		       mipsloader_dev->keystone.br_x, mipsloader_dev->keystone.br_y);
}

/**
 * panelparam_store - Write keystone correction parameters
 */
static ssize_t panelparam_store(struct device *dev,
				struct device_attribute *attr,
				const char *buf, size_t count)
{
	struct keystone_params params;
	int ret;
	
	if (!mipsloader_dev)
		return -ENODEV;
	
	ret = sscanf(buf, "tl_x=%d,tl_y=%d,tr_x=%d,tr_y=%d,bl_x=%d,bl_y=%d,br_x=%d,br_y=%d",
		     &params.tl_x, &params.tl_y,
		     &params.tr_x, &params.tr_y,
		     &params.bl_x, &params.bl_y,
		     &params.br_x, &params.br_y);
	
	if (ret != 8) {
		dev_err(dev, "Invalid keystone parameter format. Expected: tl_x=N,tl_y=N,...\n");
		return -EINVAL;
	}
	
	ret = mips_set_keystone_params(&params);
	if (ret)
		return ret;
	
	return count;
}

static DEVICE_ATTR_RW(panelparam);

static struct attribute *mipsloader_attrs[] = {
	&dev_attr_memory_stats.attr,
	&dev_attr_register_access_count.attr,
	&dev_attr_firmware_status.attr,
	&dev_attr_communication_errors.attr,
	&dev_attr_panelparam.attr,
	NULL,
};
ATTRIBUTE_GROUPS(mipsloader);

/**
 * mipsloader_probe - Platform device probe
 */
static int mipsloader_probe(struct platform_device *pdev)
{
	struct resource *res;
	int ret;
	int i;
	dev_t devt;
	
	dev_info(&pdev->dev, "Probing MIPS loader device\n");
	
	/* Allocate device structure */
	mipsloader_dev = devm_kzalloc(&pdev->dev, sizeof(*mipsloader_dev), GFP_KERNEL);
	if (!mipsloader_dev)
		return -ENOMEM;
	
	mipsloader_dev->pdev = pdev;
	mutex_init(&mipsloader_dev->lock);
	platform_set_drvdata(pdev, mipsloader_dev);
	
	/* Initialize metrics */
	memset(&mipsloader_dev->metrics, 0, sizeof(mipsloader_dev->metrics));
	for (i = 0; i < 4; i++)
		atomic64_set(&mipsloader_dev->metrics.reg_access_count[i], 0);
	
	memset(&mipsloader_dev->keystone, 0, sizeof(mipsloader_dev->keystone));
	
	/* Map register region */
	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!res) {
		dev_err(&pdev->dev, "No register resource found\n");
		return -ENOENT;
	}
	
	mipsloader_dev->reg_base = devm_ioremap_resource(&pdev->dev, res);
	if (IS_ERR(mipsloader_dev->reg_base)) {
		dev_err(&pdev->dev, "Failed to map registers\n");
		return PTR_ERR(mipsloader_dev->reg_base);
	}
	
	dev_info(&pdev->dev, "Register base mapped to %p\n", mipsloader_dev->reg_base);
	
	/* Map MIPS memory region */
	mipsloader_dev->mem_size = MIPS_TOTAL_SIZE;
	mipsloader_dev->mem_base = devm_ioremap(&pdev->dev, MIPS_BOOT_CODE_ADDR, 
						mipsloader_dev->mem_size);
	if (!mipsloader_dev->mem_base) {
		dev_err(&pdev->dev, "Failed to map MIPS memory region\n");
		return -ENOMEM;
	}
	
	dev_info(&pdev->dev, "MIPS memory region mapped: %zu bytes at %p\n",
		 mipsloader_dev->mem_size, mipsloader_dev->mem_base);
	
	/* Allocate character device number */
	ret = alloc_chrdev_region(&devt, 0, 1, MIPSLOADER_DEVICE_NAME);
	if (ret) {
		dev_err(&pdev->dev, "Failed to allocate device number: %d\n", ret);
		return ret;
	}
	
	mipsloader_dev->major = MAJOR(devt);
	
	/* Initialize character device */
	cdev_init(&mipsloader_dev->cdev, &mipsloader_fops);
	mipsloader_dev->cdev.owner = THIS_MODULE;
	
	ret = cdev_add(&mipsloader_dev->cdev, devt, 1);
	if (ret) {
		dev_err(&pdev->dev, "Failed to add character device: %d\n", ret);
		goto unregister_chrdev;
	}
	
	/* Create hy300 class if it doesn't exist */
	if (!hy300_class) {
		hy300_class = class_create("hy300");
		if (IS_ERR(hy300_class)) {
			ret = PTR_ERR(hy300_class);
			dev_err(&pdev->dev, "Failed to create hy300 class: %d\n", ret);
			hy300_class = NULL;
			goto del_cdev;
		}
	}
	
	/* Create device class */
	mipsloader_dev->class = class_create(MIPSLOADER_CLASS_NAME);
	if (IS_ERR(mipsloader_dev->class)) {
		ret = PTR_ERR(mipsloader_dev->class);
		dev_err(&pdev->dev, "Failed to create device class: %d\n", ret);
		goto del_cdev;
	}
	
	/* Create device node */
	mipsloader_dev->device = device_create_with_groups(mipsloader_dev->class, &pdev->dev,
					       devt, mipsloader_dev, mipsloader_groups, MIPSLOADER_DEVICE_NAME);
	if (IS_ERR(mipsloader_dev->device)) {
		ret = PTR_ERR(mipsloader_dev->device);
		dev_err(&pdev->dev, "Failed to create device: %d\n", ret);
		goto destroy_class;
	}
	
	/* Create additional device node in hy300 class for metrics */
	if (hy300_class) {
		struct device *metrics_dev = device_create_with_groups(hy300_class, &pdev->dev,
							MKDEV(0, 0), mipsloader_dev, mipsloader_groups, "mips");
		if (IS_ERR(metrics_dev)) {
			dev_warn(&pdev->dev, "Failed to create metrics device: %ld\n", PTR_ERR(metrics_dev));
		} else {
			dev_info(&pdev->dev, "Metrics available at /sys/class/hy300/mips/\n");
		}
	}
	
	dev_info(&pdev->dev, "MIPS loader driver initialized successfully\n");
	dev_info(&pdev->dev, "Device node: /dev/%s\n", MIPSLOADER_DEVICE_NAME);
	
	return 0;

destroy_class:
	class_destroy(mipsloader_dev->class);
del_cdev:
	cdev_del(&mipsloader_dev->cdev);
unregister_chrdev:
	unregister_chrdev_region(devt, 1);
	
	return ret;
}

/**
 * mipsloader_remove - Platform device remove
 */
static void mipsloader_remove(struct platform_device *pdev)
{
	struct mipsloader_device *dev = platform_get_drvdata(pdev);
	dev_t devt = MKDEV(dev->major, 0);
	
	dev_info(&pdev->dev, "Removing MIPS loader device\n");
	
	/* Remove metrics device from hy300 class */
	if (hy300_class) {
		device_destroy(hy300_class, MKDEV(0, 0));
		/* Note: Not destroying hy300_class as other drivers may use it */
	}
	
	/* Cleanup device */
	device_destroy(dev->class, devt);
	class_destroy(dev->class);
	cdev_del(&dev->cdev);
	unregister_chrdev_region(devt, 1);
	
	/* Power down MIPS if running */
	if (dev->firmware_loaded) {
		mipsloader_powerdown();
	}
	
	mipsloader_dev = NULL;
	
	dev_info(&pdev->dev, "MIPS loader driver removed\n");
}

static const struct of_device_id mipsloader_of_match[] = {
	{ .compatible = "allwinner,sunxi-mipsloader" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, mipsloader_of_match);

static struct platform_driver mipsloader_driver = {
	.probe = mipsloader_probe,
	.remove = mipsloader_remove,
	.driver = {
		.name = "sunxi-mipsloader",
		.of_match_table = mipsloader_of_match,
	},
};

module_platform_driver(mipsloader_driver);

MODULE_AUTHOR("HY300 Linux Porting Project");
MODULE_DESCRIPTION("Allwinner MIPS Co-processor Loader Driver");
MODULE_LICENSE("GPL v2");
MODULE_ALIAS("platform:sunxi-mipsloader");