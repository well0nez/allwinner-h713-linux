/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Allwinner H713 TV Subsystem Top Module Driver
 *
 * Ported from stock sunxi_tvtop.ko (H713 SDK V1.3, Linux 5.4)
 * Original path: drivers/misc/sunxi-tvutils/sunxi_tvtop.c
 *
 * This driver manages clock gating, reset control and power domains
 * for the three TV subsystem blocks: tvdisp, tvcap, tvfe.
 */

#ifndef _SUNXI_TVTOP_H
#define _SUNXI_TVTOP_H

#include <linux/clk.h>
#include <linux/device.h>
#include <linux/list.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/types.h>

/* Submodule indices — order matches hw_data[] array */
#define TVTOP_SUB_TVDISP	0
#define TVTOP_SUB_TVCAP		1
#define TVTOP_SUB_TVFE		2
#define TVTOP_SUB_COUNT		3

/* Resolution types — used to select clock rates and register tables */
#define TVTOP_RES_1080P		0	/* 1920×1080 */
#define TVTOP_RES_UNKNOWN	(-1)	/* Undetected */
#define TVTOP_RES_360P		2	/* 640×360 */
#define TVTOP_RES_720P		3	/* 1280×720, 1366×768, or generic */

/* Maximum resolution types in clock rate tables */
#define TVTOP_RES_TYPE_COUNT	4

/* Number of register write entries per resolution type (tvdisp) */
#define TVTOP_DISP_REG_COUNT	7

/* INCAP power register physical address (tvcap enable) */
#define TVTOP_INCAP_REG_PHYS	0x06940000
#define TVTOP_INCAP_REG_SIZE	0x100

/**
 * struct tvtop_clk_desc - Clock descriptor in hardware data tables
 * @name:        DT clock name (NULL terminates the array)
 * @rates:       Target clock rates per resolution type (Hz)
 * @parent_rate: Parent clock rate (Hz), 0 = don't set
 */
struct tvtop_clk_desc {
	const char *name;
	unsigned long rates[TVTOP_RES_TYPE_COUNT];
	unsigned long parent_rate;
};

/**
 * struct tvtop_reg_entry - Register offset + value pair
 * @offset: Register offset from iobase
 * @value:  Value to write
 */
struct tvtop_reg_entry {
	u32 offset;
	u32 value;
};

/**
 * struct tvtop_hw_data - Per-submodule hardware description
 * @name:       Submodule name ("tvdisp", "tvcap", "tvfe")
 * @iomap_idx:  Index for of_iomap()
 * @rst_name:   Reset control name in DT
 * @clk_name:   Bus clock name in DT
 * @pm_domain:  Power domain name (NULL = none)
 * @clk_descs:  Array of clock descriptors (NULL-terminated)
 */
struct tvtop_hw_data {
	const char *name;
	int iomap_idx;
	const char *rst_name;
	const char *clk_name;
	const char *pm_domain;
	const struct tvtop_clk_desc *clk_descs;
};

/**
 * struct tvtop_clk_entry - Runtime clock list entry
 * @list:               Linked into submodule clk_list
 * @clk:                Clock handle
 * @parent_clk:         Cached parent clock handle
 * @target_rate:        Target rate for this clock (Hz)
 * @parent_rate:        Target rate for parent clock (Hz)
 * @clk_enabled:        Whether clk has been prepared+enabled
 * @parent_clk_enabled: Whether parent_clk has been prepared+enabled
 */
struct tvtop_clk_entry {
	struct list_head list;
	struct clk *clk;
	struct clk *parent_clk;
	unsigned long target_rate;
	unsigned long parent_rate;
	bool clk_enabled;
	bool parent_clk_enabled;
};

/**
 * struct tvtop_submodule - Per-submodule runtime state
 * @hw_data:           Pointer to static hardware description
 * @iobase:            Memory-mapped register base
 * @rst:               Reset control handle
 * @bus_clk:           Bus clock handle
 * @bus_clk_enabled:   Whether bus_clk has been prepared+enabled
 * @clk_list:          List of tvtop_clk_entry (runtime clocks)
 * @pm_link:           Device link for power domain (NULL = none)
 * @config_val:        Resolution type for submodule 0, 0 for others
 * @lock:              Mutex protecting enable/disable
 * @enabled:           Whether this submodule is currently enabled
 */
struct tvtop_submodule {
	const struct tvtop_hw_data *hw_data;
	void __iomem *iobase;
	struct reset_control *rst;
	struct clk *bus_clk;
	bool bus_clk_enabled;
	struct list_head clk_list;
	struct device *pm_dev;		/* virtual device for power domain */
	int config_val;
	struct mutex lock;
	int enabled;
};

/**
 * struct tvtop_clk_ctrl - Per-submodule clock reference counting
 * @lock:       Mutex protecting refcount and enable/disable
 * @refcount:   Number of active clock users
 * @enable_fn:  Function to call on first enable
 */
struct tvtop_clk_ctrl {
	struct mutex lock;
	int refcount;
	int (*enable_fn)(struct device *dev);
};

/**
 * struct tvtop_device - Main driver private data (allocated in probe)
 * @name:        Device name (NULL in normal probe)
 * @dev:         Child device created by device_create
 * @cls:         Device class
 * @sub:         Per-submodule data [tvdisp, tvcap, tvfe]
 * @first_init:  Flag: skip register writes on first tvdisp enable
 * @clk_ctrl:    Per-submodule clock reference control
 * @pdev_dev:    Platform device's struct device pointer
 */
struct tvtop_device {
	const char *name;
	struct device *dev;
	struct class *cls;
	struct tvtop_submodule sub[TVTOP_SUB_COUNT];
	int first_init;
	struct tvtop_clk_ctrl clk_ctrl[TVTOP_SUB_COUNT];
	struct device *pdev_dev;
};

/* Global device pointer (needed by clk_get/clk_put exports) */
extern struct tvtop_device *tvtopdev;

/* ---- Data tables (sunxi_tvtop_data.c) ---- */
extern const struct tvtop_hw_data tvtop_hw_data[TVTOP_SUB_COUNT];
extern const struct tvtop_reg_entry
	tvtop_disp_regs[TVTOP_RES_TYPE_COUNT][TVTOP_DISP_REG_COUNT];

/* ---- Clock management (sunxi_tvtop_clk.c) ---- */
int sunxi_tvtop_clk_get(unsigned int type);
int sunxi_tvtop_clk_put(unsigned int type);
int sunxi_tvtop_client_register(struct device *client_dev);
int sunxi_tvtop_clock_enable(struct tvtop_submodule *sub);

/* ---- Power / subsystem enable/disable (sunxi_tvtop_power.c) ---- */
int tvtop_tvdisp_enable(struct device *dev);
int tvtop_tvfe_enable(struct device *dev);
int tvtop_tvcap_enable(struct device *dev);
int tvtop_pm_domain_enable(struct tvtop_submodule *sub);
void tvtop_pm_domain_disable(struct tvtop_submodule *sub);
void tvtop_submodule_disable(struct device *dev, unsigned int index);

/* ---- Sysfs (sunxi_tvtop_sysfs.c) ---- */
extern const struct attribute_group tvtop_attribute_group;

#endif /* _SUNXI_TVTOP_H */
