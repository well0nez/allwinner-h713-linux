// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner H713 TV Subsystem Top — Sysfs Interface
 *
 * Ported from: sunxi_tvtop_store_tvdisp (0x0f64),
 *              sunxi_tvtop_store_tvfe (0x0f24),
 *              sunxi_tvtop_store_tvcap (0x0ee4)
 *
 * Write "1" to enable (clk_get), "0" to disable (clk_put).
 */

#include <linux/device.h>
#include <linux/sysfs.h>

#include "sunxi_tvtop.h"

/*
 * Common sysfs store handler pattern.
 * Matches the three identical 64-byte functions in stock.
 *
 * Disasm logic (all three):
 *   val = simple_strtoul(buf, NULL, 0)
 *   if val != 0: sunxi_tvtop_clk_get(index)
 *   else:        sunxi_tvtop_clk_put(index)
 *   return count
 */
static ssize_t tvtop_sysfs_store(unsigned int index,
				 const char *buf, size_t count)
{
	unsigned long val;

	/* Stock uses simple_strtoul — invalid input becomes 0 (→ clk_put) */
	val = simple_strtoul(buf, NULL, 0);

	if (val)
		sunxi_tvtop_clk_get(index);
	else
		sunxi_tvtop_clk_put(index);

	return count;
}

static ssize_t tvdisp_store(struct device *dev, struct device_attribute *attr,
			    const char *buf, size_t count)
{
	return tvtop_sysfs_store(TVTOP_SUB_TVDISP, buf, count);
}

static ssize_t tvcap_store(struct device *dev, struct device_attribute *attr,
			   const char *buf, size_t count)
{
	return tvtop_sysfs_store(TVTOP_SUB_TVCAP, buf, count);
}

static ssize_t tvfe_store(struct device *dev, struct device_attribute *attr,
			  const char *buf, size_t count)
{
	return tvtop_sysfs_store(TVTOP_SUB_TVFE, buf, count);
}

static DEVICE_ATTR(tvdisp, 0200, NULL, tvdisp_store);
static DEVICE_ATTR(tvcap, 0200, NULL, tvcap_store);
static DEVICE_ATTR(tvfe, 0200, NULL, tvfe_store);

static struct attribute *tvtop_sysfs_entries[] = {
	&dev_attr_tvdisp.attr,
	&dev_attr_tvfe.attr,
	&dev_attr_tvcap.attr,
	NULL,
};

const struct attribute_group tvtop_attribute_group = {
	.attrs = tvtop_sysfs_entries,
};
