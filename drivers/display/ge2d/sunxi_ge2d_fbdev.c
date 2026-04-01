// SPDX-License-Identifier: GPL-2.0

#include <linux/backlight.h>
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/fb.h>
#include <linux/io.h>
#include <linux/kconfig.h>
#include <linux/mm.h>
#include <linux/moduleparam.h>
#include <linux/of_address.h>

#include "sunxi_ge2d.h"

#if IS_ENABLED(CONFIG_FB)

static inline struct ge2d_device *ge2d_from_info(struct fb_info *info)
{
	return *((struct ge2d_device **)info->par);
}

static void ge2d_fb_release_action(void *data)
{
	framebuffer_release(data);
}

static int ge2d_fb_open(struct fb_info *info, int user)
{
	return 0;
}

static int ge2d_fb_release(struct fb_info *info, int user)
{
	return 0;
}

static int ge2d_fb_check_var(struct fb_var_screeninfo *var, struct fb_info *info)
{
	struct ge2d_device *gdev = ge2d_from_info(info);

	if (var->bits_per_pixel != 32)
		return -EINVAL;

	if (var->xres != gdev->panel.width || var->yres != gdev->panel.height)
		return -EINVAL;

	return 0;
}

static int ge2d_fb_set_par(struct fb_info *info)
{
	return 0;
}

static int ge2d_fb_blank(int blank, struct fb_info *info)
{
	struct ge2d_device *gdev = ge2d_from_info(info);

	if (!gdev->backlight)
		return 0;

	gdev->backlight->props.power =
		(blank == FB_BLANK_UNBLANK) ? FB_BLANK_UNBLANK :
		FB_BLANK_POWERDOWN;
	return backlight_update_status(gdev->backlight);
}

static int ge2d_fb_pan_display(struct fb_var_screeninfo *var,
				      struct fb_info *info)
{
	if (var->xoffset || var->yoffset)
		return -EINVAL;

	return 0;
}

static int ge2d_fb_mmap(struct fb_info *info, struct vm_area_struct *vma)
{
	struct ge2d_device *gdev = ge2d_from_info(info);

	return vm_iomap_memory(vma, gdev->fb_phys, gdev->fb_size);
}

static int ge2d_fb_setcolreg(unsigned int regno, unsigned int red,
				    unsigned int green, unsigned int blue,
				    unsigned int transp,
				    struct fb_info *info)
{
	struct ge2d_device *gdev = ge2d_from_info(info);
	u32 value;

	if (regno >= ARRAY_SIZE(gdev->pseudo_palette))
		return -EINVAL;

	red >>= 8;
	green >>= 8;
	blue >>= 8;
	transp >>= 8;
	value = (transp << 24) | (red << 16) | (green << 8) | blue;
	gdev->pseudo_palette[regno] = value;

	return 0;
}

static const struct fb_ops ge2d_fb_ops = {
	.owner = THIS_MODULE,
	.fb_open = ge2d_fb_open,
	.fb_release = ge2d_fb_release,
	.fb_read = fb_sys_read,
	.fb_write = fb_sys_write,
	.fb_check_var = ge2d_fb_check_var,
	.fb_set_par = ge2d_fb_set_par,
	.fb_blank = ge2d_fb_blank,
	.fb_pan_display = ge2d_fb_pan_display,
	.fb_fillrect = sys_fillrect,
	.fb_copyarea = sys_copyarea,
	.fb_imageblit = sys_imageblit,
	.fb_mmap = ge2d_fb_mmap,
	.fb_setcolreg = ge2d_fb_setcolreg,
	.fb_setcmap = fb_set_cmap,
};

/*
 * Optional scanout override for A/B tests.
 * Default behavior is DTS memory-region to avoid forcing an unsafe address.
 */
static ulong ge2d_fb_phys_override;
static ulong ge2d_fb_size_override;
module_param_named(fb_phys_override, ge2d_fb_phys_override, ulong, 0644);
MODULE_PARM_DESC(fb_phys_override, "Optional scanout framebuffer physical base address (0=disabled)");
module_param_named(fb_size_override, ge2d_fb_size_override, ulong, 0644);
MODULE_PARM_DESC(fb_size_override, "Optional scanout framebuffer size in bytes (0=disabled)");

static int ge2d_lookup_framebuffer_region(struct ge2d_device *gdev,
					 struct resource *res)
{
	struct device_node *np;
	int ret;

	/* Try DTS memory-region first */
	np = of_parse_phandle(gdev->dev->of_node, "memory-region", 0);
	if (!np)
		np = of_find_node_by_name(NULL, "framebuf@4bf41000");
	if (np) {
		ret = of_address_to_resource(np, 0, res);
		of_node_put(np);
		if (!ret) {
			dev_info(gdev->dev,
				 "fbdev: DTS framebuffer at %pa (%pa bytes)\n",
				 &res->start, (phys_addr_t[]){resource_size(res)});
		}
	} else {
		ret = -ENOENT;
	}

	if (ge2d_fb_phys_override && ge2d_fb_size_override) {
		res->start = (resource_size_t)ge2d_fb_phys_override;
		res->end   = (resource_size_t)ge2d_fb_phys_override +
				 (resource_size_t)ge2d_fb_size_override - 1;
		res->flags = IORESOURCE_MEM;
		dev_info(gdev->dev,
			 "fbdev: using override scanout address %pa (size 0x%lx bytes)\n",
			 &res->start, ge2d_fb_size_override);
		return 0;
	}

	if (ge2d_fb_phys_override || ge2d_fb_size_override)
		dev_warn(gdev->dev,
			 "fbdev override ignored: set both fb_phys_override and fb_size_override\n");

	if (!ret)
		return 0;

	return ret;
}

int ge2d_fbdev_init(struct ge2d_device *gdev)
{
	struct fb_info *info;
	struct resource res;
	int ret;

	if (!ge2d_enable_fbdev)
		return 0;

	ret = ge2d_lookup_framebuffer_region(gdev, &res);
	if (ret) {
		dev_warn(gdev->dev,
			 "fbdev requested but no framebuffer memory-region was found\n");
		return 0;
	}

	info = framebuffer_alloc(sizeof(struct ge2d_device *), gdev->dev);
	if (!info)
		return -ENOMEM;

	ret = devm_add_action_or_reset(gdev->dev, ge2d_fb_release_action, info);
	if (ret)
		return ret;

	*((struct ge2d_device **)info->par) = gdev;
	gdev->fb_phys = res.start;
	gdev->fb_size = resource_size(&res);
	/*
	 * The U-Boot scanout address lives in System RAM (linear map).
	 * devm_memremap(MEMREMAP_WC) fails for RAM pages; use memremap
	 * with MEMREMAP_WB which falls through to the linear mapping.
	 * TODO: once reserved-memory is in DTS, switch back to
	 * devm_memremap(MEMREMAP_WC) for proper write-combining.
	 */
	gdev->fb_vaddr = memremap(gdev->fb_phys, gdev->fb_size, MEMREMAP_WB);
	if (!gdev->fb_vaddr) {
		dev_err(gdev->dev, "fbdev: memremap(%pa, %zu) failed\n",
			&gdev->fb_phys, gdev->fb_size);
		return -ENOMEM;
	}

	strscpy(info->fix.id, "sunxi-ge2d", sizeof(info->fix.id));
	info->fix.type = FB_TYPE_PACKED_PIXELS;
	info->fix.visual = FB_VISUAL_TRUECOLOR;
	info->fix.smem_start = gdev->fb_phys;
	info->fix.smem_len = gdev->fb_size;
	info->fix.ywrapstep = 0;
	info->fix.xpanstep = 0;
	info->fix.ypanstep = 0;
	info->fix.line_length = gdev->panel.width * 4;
	info->screen_base = gdev->fb_vaddr;
	info->screen_size = gdev->fb_size;
	info->fbops = &ge2d_fb_ops;
	info->pseudo_palette = gdev->pseudo_palette;
	info->flags = FBINFO_VIRTFB;

	info->var.xres = gdev->panel.width;
	info->var.yres = gdev->panel.height;
	info->var.xres_virtual = gdev->panel.width;
	info->var.yres_virtual = ALIGN(gdev->panel.height, 16); /* stock: 1088 for 1080 */
	info->var.bits_per_pixel = 32;
	info->var.activate = FB_ACTIVATE_NOW;
	info->var.red.offset = 16;
	info->var.red.length = 8;
	info->var.green.offset = 8;
	info->var.green.length = 8;
	info->var.blue.offset = 0;
	info->var.blue.length = 8;
	info->var.transp.offset = 24;
	info->var.transp.length = 8;

	ret = register_framebuffer(info);
	if (ret)
		return ret;

	gdev->fb_info = info;
	gdev->fb_registered = true;
	dev_info(gdev->dev,
		 "registered fbdev at %pa (%zu bytes)\n",
		 &gdev->fb_phys, gdev->fb_size);
	return 0;
}

void ge2d_fbdev_exit(struct ge2d_device *gdev)
{
	/*
	 * Do NOT power down backlight on remove.
	 * Stock ge2d_drv_remove (0x79f4) does not touch backlight.
	 * PB5 controls both backlight AND fan -- powering down kills fan.
	 * Backlight-off belongs in suspend path only.
	 */

	if (gdev->fb_vaddr) {
		memunmap(gdev->fb_vaddr);
		gdev->fb_vaddr = NULL;
	}

	gdev->fb_info = NULL;
}

#else

int ge2d_fbdev_init(struct ge2d_device *gdev)
{
	if (!ge2d_enable_fbdev)
		return 0;

	dev_warn(gdev->dev,
		 "enable_fbdev=1 requested, but this kernel was built without CONFIG_FB; deferring /dev/fb0 registration\n");
	return 0;
}

void ge2d_fbdev_exit(struct ge2d_device *gdev)
{
}

#endif
