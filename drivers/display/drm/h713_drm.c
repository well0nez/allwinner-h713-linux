// SPDX-License-Identifier: GPL-2.0-only
/*
 * Allwinner H713 DRM/KMS Display Driver
 *
 * Minimal modesetting driver for the H713 custom display pipeline:
 *   TVTOP bus fabric -> VBlender timing -> OSD plane -> LVDS output
 *
 * The MIPS coprocessor initializes VBlender timing and LVDS PHY at boot.
 * This driver enables clocks, programs TVTOP routing, and handles
 * framebuffer scanout via the OSD plane registers.
 *
 * Copyright (C) 2026
 */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/i2c.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/platform_device.h>
#include <linux/reset.h>

#include <drm/clients/drm_client_setup.h>
#include <drm/drm_atomic_helper.h>
#include <drm/drm_device.h>
#include <drm/drm_drv.h>
#include <drm/drm_fb_dma_helper.h>
#include <drm/drm_fbdev_dma.h>
#include <drm/drm_fourcc.h>
#include <drm/drm_framebuffer.h>
#include <drm/drm_gem_dma_helper.h>
#include <drm/drm_gem_framebuffer_helper.h>
#include <drm/drm_module.h>
#include <drm/drm_probe_helper.h>
#include <drm/drm_simple_kms_helper.h>

/* ------------------------------------------------------------------ */
/* MMIO physical addresses                                             */
/* ------------------------------------------------------------------ */
#define H713_TVTOP_BASE		0x05700000
#define H713_TVTOP_SIZE		0xA0

#define H713_VBLEND_BASE	0x05200000
#define H713_VBLEND_SIZE	0x100

#define H713_OSD_BASE		0x05248000
#define H713_OSD_SIZE		0x200

#define H713_AFBD_CTRL_BASE	0x05600100
#define H713_AFBD_CTRL_SIZE	0x80
#define H713_AFBD_BASE		0x05600000
#define H713_AFBD_BASE_SIZE	0x20

#define H713_GE2D_CORE_BASE	0x05240000
#define H713_GE2D_CORE_SIZE	0x20

#define H713_LVDS_BASE		0x051C0000
#define H713_LVDS_SIZE		0x100

/* Known-good U-Boot scanout framebuffer from DTS reserved memory */
#define H713_UBOOT_SCANOUT_ADDR	0x78541000
#define H713_SAFE_FB_WIDTH	1920
#define H713_SAFE_FB_HEIGHT	1088
#define H713_SAFE_FB_STRIDE	(H713_SAFE_FB_WIDTH * 4)
#define H713_SAFE_FB_SIZE	(H713_SAFE_FB_STRIDE * H713_SAFE_FB_HEIGHT)

static bool h713_use_safe_scanout;
module_param_named(use_safe_scanout, h713_use_safe_scanout, bool, 0644);
MODULE_PARM_DESC(use_safe_scanout,
	"Use known-good U-Boot scanout buffer instead of GEM DMA buffer");

static bool h713_fill_test_pattern;
module_param_named(fill_test_pattern, h713_fill_test_pattern, bool, 0644);
MODULE_PARM_DESC(fill_test_pattern,
	"Fill scanout buffer with kernel test pattern for bring-up/debug");

static bool h713_enable_dlpc3435;
module_param_named(enable_dlpc3435, h713_enable_dlpc3435, bool, 0644);
MODULE_PARM_DESC(enable_dlpc3435,
	"Enable experimental DLPC3435 I2C init sequence during display enable");

/* ------------------------------------------------------------------ */
/* TVTOP bus fabric routing registers (1080p config)                    */
/* ------------------------------------------------------------------ */
static const struct { u32 off; u32 val; } tvtop_routing[] = {
	{ 0x04, 0x00000001 },
	{ 0x44, 0x11111111 },
	{ 0x88, 0xFFFFFFFF },
	{ 0x00, 0x00011111 },
	{ 0x40, 0x00011111 },
	{ 0x80, 0x00001111 },
	{ 0x84, 0xFFF000EF },
};

/* ------------------------------------------------------------------ */
/* OSD plane registers (relative to OSD_BASE 0x05248000)               */
/* ------------------------------------------------------------------ */
#define OSD_CTRL		0x00	/* Control/format, bit0=commit */
#define OSD_SIZE_A		0x10	/* Macro-block geometry */
#define OSD_SIZE_B		0x14	/* (height-1) | ((width-1) << 16) */
#define OSD_STRIDE		0x30	/* Bytes per line */
#define OSD_FB_ADDR		0x38	/* Framebuffer physical address */

/* OSD_CTRL format codes (bits [15:8]) */
#define OSD_FMT_ARGB8888	0x1900

/* ------------------------------------------------------------------ */
/* VBlender registers (read-only, for verification)                    */
/* ------------------------------------------------------------------ */
#define VB_CTRL			0x04
#define VB_H_ACTIVE		0x0C
#define VB_V_ACTIVE		0x10

/* ------------------------------------------------------------------ */
/* Driver private structure                                            */
/* ------------------------------------------------------------------ */
struct h713_drm {
	struct drm_device	drm;
	struct drm_simple_display_pipe pipe;
	struct drm_connector	connector;

	/* MMIO regions */
	void __iomem		*tvtop;
	void __iomem		*vblend;
	void __iomem		*osd;
	void __iomem		*afbd_ctrl;
	void __iomem		*afbd_base;
	void __iomem		*ge2d_core;
	void __iomem		*lvds;
	void __iomem		*safe_fb;

	/* Clocks */
	struct clk		*clk_bus_disp;
	struct clk		*clk_afbd;
	struct clk		*clk_svp_dtl;
	struct clk		*clk_deint;
	struct clk		*clk_panel;

	/* Reset */
	struct reset_control	*rst_bus_disp;

	bool			enabled;
	bool			dlpc_attempted;
};

#define to_h713(x) container_of(x, struct h713_drm, drm)
#define pipe_to_h713(x) container_of(x, struct h713_drm, pipe)

/* ------------------------------------------------------------------ */
/* Register accessors                                                  */
/* ------------------------------------------------------------------ */
static inline void h713_write(void __iomem *base, u32 reg, u32 val)
{
	writel(val, base + reg);
}

static inline u32 h713_read(void __iomem *base, u32 reg)
{
	return readl(base + reg);
}

static void __maybe_unused h713_trace_reg_write(struct h713_drm *h713,
				      const char *block,
				      u32 addr,
				      const char *name,
				      u32 val)
{
	dev_info(h713->drm.dev,
		 "h713_dbg: wr %s.%s [0x%08x] = 0x%08x\n",
		 block, name, addr, val);
}

#define H713_TRACE_WRITE(_h713, _base, _base_phys, _reg, _name, _val) \
	do { \
		u32 __val = (_val); \
		/* Debug trace kept for bring-up; enable when needed. */ \
		/* h713_trace_reg_write((_h713), #_base, (_base_phys) + (_reg), (_name), __val); */ \
		h713_write((_h713)->_base, (_reg), __val); \
	} while (0)

/* ------------------------------------------------------------------ */
/* Clock / reset / TVTOP management                                    */
/* ------------------------------------------------------------------ */
static int h713_clocks_enable(struct h713_drm *h713)
{
	int ret;

	if (h713->clk_svp_dtl) {
		ret = clk_prepare_enable(h713->clk_svp_dtl);
		if (ret)
			return ret;
	}
	if (h713->clk_deint) {
		ret = clk_prepare_enable(h713->clk_deint);
		if (ret)
			goto err_svp;
	}
	if (h713->clk_panel) {
		ret = clk_prepare_enable(h713->clk_panel);
		if (ret)
			goto err_deint;
	}

	ret = clk_prepare_enable(h713->clk_bus_disp);
	if (ret)
		goto err_panel;

	if (h713->clk_afbd) {
		ret = clk_prepare_enable(h713->clk_afbd);
		if (ret)
			goto err_bus;
	}

	return 0;

err_bus:
	clk_disable_unprepare(h713->clk_bus_disp);
err_panel:
	if (h713->clk_panel)
		clk_disable_unprepare(h713->clk_panel);
err_deint:
	if (h713->clk_deint)
		clk_disable_unprepare(h713->clk_deint);
err_svp:
	if (h713->clk_svp_dtl)
		clk_disable_unprepare(h713->clk_svp_dtl);
	return ret;
}

static void h713_clocks_disable(struct h713_drm *h713)
{
	if (h713->clk_afbd)
		clk_disable_unprepare(h713->clk_afbd);
	clk_disable_unprepare(h713->clk_bus_disp);
	if (h713->clk_panel)
		clk_disable_unprepare(h713->clk_panel);
	if (h713->clk_deint)
		clk_disable_unprepare(h713->clk_deint);
	if (h713->clk_svp_dtl)
		clk_disable_unprepare(h713->clk_svp_dtl);
}

static void h713_tvtop_enable(struct h713_drm *h713)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(tvtop_routing); i++)
		h713_write(h713->tvtop, tvtop_routing[i].off,
			   tvtop_routing[i].val);
	usleep_range(1000, 2000);
}

static void h713_fill_safe_pattern(struct h713_drm *h713)
{
	u32 x, y;

	if (!h713->safe_fb)
		return;

	for (y = 0; y < H713_SAFE_FB_HEIGHT; y++) {
		for (x = 0; x < H713_SAFE_FB_WIDTH; x++) {
			u8 r = (x * 255) / H713_SAFE_FB_WIDTH;
			u8 g = (y * 255) / H713_SAFE_FB_HEIGHT;
			u8 b = ((x / 64) ^ (y / 64)) ? 0xff : 0x20;
			u32 pixel = 0xff000000 | (r << 16) | (g << 8) | b;
			writel(pixel, h713->safe_fb + y * H713_SAFE_FB_STRIDE + x * 4);
		}
	}
}

static void h713_fill_pattern_to_ram(void *base, u32 width, u32 height,
				     u32 stride)
{
	u32 x, y;
	u8 *ptr = base;

	if (!base)
		return;

	for (y = 0; y < height; y++) {
		for (x = 0; x < width; x++) {
			u8 r = (x * 255) / (width ? width : 1);
			u8 g = (y * 255) / (height ? height : 1);
			u8 b = ((x / 64) ^ (y / 64)) ? 0xff : 0x20;
			u32 pixel = 0xff000000 | (r << 16) | (g << 8) | b;

			*(u32 *)(ptr + y * stride + x * 4) = pixel;
		}
	}

	wmb();
}

static dma_addr_t h713_get_scanout_addr(struct h713_drm *h713,
					struct drm_framebuffer *fb,
					struct drm_plane_state *state)
{
	if (h713_use_safe_scanout)
		return H713_UBOOT_SCANOUT_ADDR;

	return drm_fb_dma_get_gem_addr(fb, state, 0);
}

static void h713_try_init_dlpc3435(struct h713_drm *h713, u16 width, u16 height)
{
	struct device_node *np;
	struct i2c_client *client;
	u8 block4[4];
	u8 block8[8] = { 0 };
	int ret;

	if (h713->dlpc_attempted)
		return;
	if (!h713_enable_dlpc3435)
		return;
	h713->dlpc_attempted = true;

	np = of_find_compatible_node(NULL, NULL, "dlpc,dlpc3435");
	if (!np) {
		dev_info(h713->drm.dev, "DLPC3435 DT node not found\n");
		return;
	}

	client = of_find_i2c_device_by_node(np);
	of_node_put(np);
	if (!client) {
		dev_info(h713->drm.dev,
			 "DLPC3435 I2C client not present (addr may be unbound/off)\n");
		return;
	}

	block4[0] = width & 0xff;
	block4[1] = (width >> 8) & 0xff;
	block4[2] = height & 0xff;
	block4[3] = (height >> 8) & 0xff;
	block8[4] = block4[0];
	block8[5] = block4[1];
	block8[6] = block4[2];
	block8[7] = block4[3];

	ret = i2c_smbus_write_i2c_block_data(client, 46, sizeof(block4), block4);
	if (ret < 0)
		goto out_warn;
	ret = i2c_smbus_write_i2c_block_data(client, 18, sizeof(block4), block4);
	if (ret < 0)
		goto out_warn;
	ret = i2c_smbus_write_i2c_block_data(client, 16, sizeof(block8), block8);
	if (ret < 0)
		goto out_warn;
	ret = i2c_smbus_write_byte_data(client, 26, 1);
	if (ret < 0)
		goto out_warn;
	ret = i2c_smbus_write_byte_data(client, 5, 0);
	if (ret < 0)
		goto out_warn;
	msleep(20);
	ret = i2c_smbus_write_byte_data(client, 26, 0);
	if (ret < 0)
		goto out_warn;

	dev_info(h713->drm.dev,
		 "DLPC3435 init sequence applied for %ux%u\n", width, height);
	put_device(&client->dev);
	return;

out_warn:
	dev_warn(h713->drm.dev, "DLPC3435 init step failed: %d\n", ret);
	put_device(&client->dev);
}

struct h713_frame_geometry {
	dma_addr_t fb_addr;
	u32 stride;
	u32 buf_h;
	u16 src_x;
	u16 src_y;
	u16 src_w;
	u16 src_h;
	u16 dst_x;
	u16 dst_y;
	u16 dst_w;
	u16 dst_h;
	u32 afbd_src_start;
	u32 afbd_src_end;
	u32 afbd_dst_start;
	u32 osd_size_a;
	u32 osd_size_b;
};

static bool h713_build_frame_geometry(struct h713_drm *h713,
				      struct drm_plane_state *state,
				      struct drm_crtc_state *crtc_state,
				      struct h713_frame_geometry *geo)
{
	struct drm_framebuffer *fb = state ? state->fb : NULL;
	u32 src_x, src_y, src_w, src_h;
	u32 dst_w, dst_h;
	u32 buf_h;
	int dst_x, dst_y;

	if (!fb)
		return false;

	geo->fb_addr = h713_get_scanout_addr(h713, fb, state);
	geo->stride = fb->pitches[0];
	buf_h = geo->stride ? (u32)(fb->obj[0]->size / geo->stride) : fb->height;
	geo->buf_h = buf_h;
	if (!buf_h)
		buf_h = fb->height;

	src_x = state->src_x >> 16;
	src_y = state->src_y >> 16;
	src_w = state->src_w >> 16;
	src_h = state->src_h >> 16;

	if (!src_w)
		src_w = fb->width;
	if (!src_h)
		src_h = fb->height;
	if (src_x >= fb->width)
		src_x = fb->width - 1;
	if (src_y >= buf_h)
		src_y = buf_h - 1;
	src_w = min(src_w, fb->width - src_x);
	src_h = min(src_h, buf_h - src_y);

	dst_x = state->crtc_x;
	dst_y = state->crtc_y;
	dst_w = state->crtc_w;
	dst_h = state->crtc_h;

	if (!dst_w)
		dst_w = src_w;
	if (!dst_h)
		dst_h = src_h;
	if (crtc_state) {
		dst_w = min_t(u32, dst_w, crtc_state->adjusted_mode.hdisplay);
		dst_h = min_t(u32, dst_h, crtc_state->adjusted_mode.vdisplay);
	}
	if (dst_x < 0)
		dst_x = 0;
	if (dst_y < 0)
		dst_y = 0;

	geo->src_x = src_x;
	geo->src_y = src_y;
	geo->src_w = max_t(u32, src_w, 1);
	geo->src_h = max_t(u32, src_h, 1);
	geo->dst_x = min_t(u32, dst_x, 0xffff);
	geo->dst_y = min_t(u32, dst_y, 0xffff);
	geo->dst_w = max_t(u32, dst_w, 1);
	geo->dst_h = max_t(u32, dst_h, 1);

	/*
	 * AFBD coordinates kept in stock-observed x/y high/low layout.
	 * In stable addr-only mode these fields are computed for diagnostics
	 * but not programmed to hardware.
	 */
	geo->afbd_src_start = (geo->src_x << 16) | geo->src_y;
	geo->afbd_src_end = ((geo->src_x + geo->src_w - 1) << 16) |
			    (geo->src_y + geo->src_h - 1);
	geo->afbd_dst_start = (geo->dst_x << 16) | geo->dst_y;
	geo->osd_size_a = ((geo->src_h - 1) << 16) | (geo->src_w - 1);
	geo->osd_size_b = (geo->dst_h - 1) | ((geo->dst_w - 1) << 16);

	return true;
}

static void h713_program_stream_setup(struct h713_drm *h713)
{
	/*
	 * Stock-derived static stream setup. Keep this one-time init path
	 * separate from frame-dependent geometry and address programming.
	 */
	h713_write(h713->afbd_base, 0x00, 0x80000020);
	h713_write(h713->afbd_ctrl, 0x40, 0x03001901);
	h713_write(h713->afbd_ctrl, 0x48, 0x008000ff);
	h713_write(h713->afbd_ctrl, 0x4c, 0x00000080);
	h713_write(h713->afbd_ctrl, 0x64, 0x00000808);
	h713_write(h713->afbd_ctrl, 0x68, 0x000003b2);
	h713_write(h713->afbd_ctrl, 0x6c, 0x00000021);
	h713_write(h713->afbd_ctrl, 0x70, 0x00001000);
	h713_write(h713->afbd_ctrl, 0x74, 0x02601000);

	/* GE2D / main block */
	h713_write(h713->ge2d_core, 0x00, 0xffff0040);
	h713_write(h713->ge2d_core, 0x1c, 0x00000300);
}

static void h713_program_frame_geometry(struct h713_drm *h713,
					const struct h713_frame_geometry *geo)
{
	/*
	 * Stable mode: preserve boot-programmed geometry/timing registers and
	 * only redirect framebuffer addresses to DRM GEM scanout.
	 * This avoids partial-frame corruption seen when reprogramming
	 * SIZE/STRIDE/AFBD geometry in current bring-up state.
	 */
	H713_TRACE_WRITE(h713, osd, H713_OSD_BASE, OSD_FB_ADDR,
			 "OSD_FB_ADDR", (u32)geo->fb_addr);
	H713_TRACE_WRITE(h713, afbd_ctrl, H713_AFBD_CTRL_BASE, 0x78,
			 "AFBD_FB_ADDR", (u32)geo->fb_addr);
}

static void h713_commit_frame(struct h713_drm *h713)
{
	u32 ctrl = h713_read(h713->osd, OSD_CTRL);

	/* Stock latch sequence: AFBD latch, then OSD commit bit */
	H713_TRACE_WRITE(h713, afbd_ctrl, H713_AFBD_CTRL_BASE, 0x44,
			 "AFBD_LATCH", 0x00000001);
	H713_TRACE_WRITE(h713, osd, H713_OSD_BASE, OSD_CTRL,
			 "OSD_CTRL_COMMIT", ctrl | BIT(0));
}

static void h713_log_frame_geometry(struct h713_drm *h713,
				    const struct h713_frame_geometry *geo,
				    const char *stage)
{
	dev_info(h713->drm.dev,
		 "%s geom: src=%ux%u+%u+%u dst=%ux%u+%u+%u stride=%u buf_h=%u fb=0x%08x crop=[0x%08x..0x%08x] dst_start=0x%08x\n",
		 stage,
		 geo->src_w, geo->src_h, geo->src_x, geo->src_y,
		 geo->dst_w, geo->dst_h, geo->dst_x, geo->dst_y,
		 geo->stride,
		 geo->stride ? (u32)(geo->osd_size_a >> 16) + 1 : 0,
		 (u32)geo->fb_addr,
		 geo->afbd_src_start, geo->afbd_src_end,
		 geo->afbd_dst_start);
}

static bool h713_program_plane_frame(struct h713_drm *h713,
				     struct drm_plane_state *state,
				     struct drm_crtc_state *crtc_state,
				     const char *stage)
{
	struct h713_frame_geometry geo;

	if (!h713_build_frame_geometry(h713, state, crtc_state, &geo))
		return false;

	h713_program_frame_geometry(h713, &geo);
	h713_commit_frame(h713);
	h713_log_frame_geometry(h713, &geo, stage);

	return true;
}


/* ------------------------------------------------------------------ */
/* Connector — fixed 1920x1080@60 LVDS panel                          */
/* ------------------------------------------------------------------ */

/*
 * Standard 1080p60 CEA timing:
 *   Pixel clock: 148.5 MHz
 *   H: 1920 active, 88 front porch, 44 sync, 148 back porch = 2200 total
 *   V: 1080 active, 4 front porch, 5 sync, 36 back porch = 1125 total
 */
static const struct drm_display_mode h713_fixed_mode = {
	.clock = 148500,
	.hdisplay = 1920,
	.hsync_start = 2008,
	.hsync_end = 2052,
	.htotal = 2200,
	.vdisplay = 1080,
	.vsync_start = 1084,
	.vsync_end = 1089,
	.vtotal = 1125,
	.flags = DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_PVSYNC,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int h713_connector_get_modes(struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &h713_fixed_mode);
	if (!mode)
		return -ENOMEM;

	drm_mode_set_name(mode);
	mode->type |= DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED;
	drm_mode_probed_add(connector, mode);

	connector->display_info.width_mm = 120;
	connector->display_info.height_mm = 68;

	return 1;
}

static const struct drm_connector_helper_funcs h713_connector_helper_funcs = {
	.get_modes = h713_connector_get_modes,
};

static const struct drm_connector_funcs h713_connector_funcs = {
	.reset			= drm_atomic_helper_connector_reset,
	.fill_modes		= drm_helper_probe_single_connector_modes,
	.destroy		= drm_connector_cleanup,
	.atomic_duplicate_state	= drm_atomic_helper_connector_duplicate_state,
	.atomic_destroy_state	= drm_atomic_helper_connector_destroy_state,
};

/* ------------------------------------------------------------------ */
/* Simple display pipe callbacks                                       */
/* ------------------------------------------------------------------ */
static enum drm_mode_status
h713_pipe_mode_valid(struct drm_simple_display_pipe *pipe,
		     const struct drm_display_mode *mode)
{
	/* Only accept our fixed mode */
	if (mode->hdisplay == 1920 && mode->vdisplay == 1080)
		return MODE_OK;
	return MODE_BAD;
}

static void h713_pipe_enable(struct drm_simple_display_pipe *pipe,
			     struct drm_crtc_state *crtc_state,
			     struct drm_plane_state *plane_state)
{
	struct h713_drm *h713 = pipe_to_h713(pipe);
	struct drm_framebuffer *fb = plane_state ? plane_state->fb : NULL;
	int ret;
	u32 ctrl, hact, vact;

	/* Step 1: Enable clocks */
	ret = h713_clocks_enable(h713);
	if (ret) {
		dev_err(h713->drm.dev, "failed to enable clocks: %d\n", ret);
		return;
	}

	/* Step 2: Deassert reset */
	ret = reset_control_deassert(h713->rst_bus_disp);
	if (ret) {
		dev_err(h713->drm.dev, "reset deassert failed: %d\n", ret);
		h713_clocks_disable(h713);
		return;
	}

	/* Step 3: Program TVTOP bus fabric routing */
	h713_tvtop_enable(h713);

	/* Step 4: Verify VBlender is alive */
	ctrl = h713_read(h713->vblend, VB_CTRL);
	hact = h713_read(h713->vblend, VB_H_ACTIVE);
	vact = h713_read(h713->vblend, VB_V_ACTIVE);

	dev_info(h713->drm.dev,
		 "VBlender: ctrl=0x%08x h=0x%08x v=0x%08x\n",
		 ctrl, hact, vact);

	if (ctrl == 0 && hact == 0) {
		dev_err(h713->drm.dev,
			"VBlender reads zero! Display bus not active.\n");
		reset_control_assert(h713->rst_bus_disp);
		h713_clocks_disable(h713);
		return;
	}

	{
		dma_addr_t addr = H713_UBOOT_SCANOUT_ADDR;
		const char *scanout_src = "u-boot-fallback";
		bool frame_programmed = false;

		/*
		 * Stable mode: keep boot-programmed stream state untouched for now.
		 * Full stream_setup reintroduction will be done incrementally after
		 * each register group is validated against visual output.
		 */
		/* h713_program_stream_setup(h713); */

		if (fb) {
			struct drm_gem_dma_object *gem = drm_fb_dma_get_gem_obj(fb, 0);

			if (gem) {
				addr = h713_get_scanout_addr(h713, fb, plane_state);
				scanout_src = h713_use_safe_scanout ? "safe-scanout" : "gem";

				dev_info(h713->drm.dev,
					 "enable fb: fb_id=%u gem_dma=%pad pitch=%u size=%ux%u safe=%d\n",
					 fb->base.id, &gem->dma_addr, fb->pitches[0],
					 fb->width, fb->height, h713_use_safe_scanout);

				if (h713_fill_test_pattern && !h713_use_safe_scanout) {
					u32 fill_height = max_t(u32, fb->height, 1088);

					if (gem->vaddr) {
						h713_fill_pattern_to_ram((u8 *)gem->vaddr + fb->offsets[0],
								      fb->width,
								      fill_height,
								      fb->pitches[0]);
						dev_info(h713->drm.dev,
							 "filled initial GEM pattern at 0x%08x (%ux%u stride=%u)\n",
							 (u32)addr, fb->width, fill_height,
							 fb->pitches[0]);
					} else {
						dev_warn(h713->drm.dev,
							 "GEM object has no vaddr for initial fill\n");
					}
				}

				frame_programmed = h713_program_plane_frame(h713, plane_state,
								   crtc_state,
								   "enable");
			} else {
				dev_warn(h713->drm.dev,
					 "enable fb has no GEM object, falling back to U-Boot scanout\n");
			}
		}

		if (!frame_programmed) {
			h713_write(h713->afbd_ctrl, 0x78, (u32)addr);
			h713_commit_frame(h713);
		}

		dev_info(h713->drm.dev,
			 "enable handoff scanout addr set to 0x%08x (%s)\n",
			 (u32)addr, scanout_src);
	}

	if (h713_use_safe_scanout && h713_fill_test_pattern) {
		h713_fill_safe_pattern(h713);
		dev_info(h713->drm.dev,
			 "filled safe test pattern at 0x%08x (%ux%u stride=%u)\n",
			 H713_UBOOT_SCANOUT_ADDR, H713_SAFE_FB_WIDTH,
			 H713_SAFE_FB_HEIGHT, H713_SAFE_FB_STRIDE);
	}

	h713->enabled = true;
	h713_try_init_dlpc3435(h713, 1920, 1080);
	dev_info(h713->drm.dev, "display pipeline enabled\n");
}

static void h713_pipe_disable(struct drm_simple_display_pipe *pipe)
{
	struct h713_drm *h713 = pipe_to_h713(pipe);

	if (!h713->enabled)
		return;

	/*
	 * Warm-pipeline strategy: do NOT assert reset or disable clocks here.
	 * The MIPS coprocessor and U-Boot initialise timing/PHY state at boot;
	 * a hard clock/reset teardown destroys that state and the second
	 * enable() cannot fully recover it.  Instead we just stop updating
	 * the scanout address and let the pipeline keep running silently.
	 * Hard teardown happens in h713_drm_shutdown() / remove().
	 */
	h713->enabled = false;

	dev_info(h713->drm.dev, "display pipeline disabled (warm — clocks kept)\n");
}

static void h713_pipe_update(struct drm_simple_display_pipe *pipe,
			     struct drm_plane_state *old_state)
{
	struct h713_drm *h713 = pipe_to_h713(pipe);
	struct drm_plane_state *state = pipe->plane.state;
	struct drm_framebuffer *fb = state->fb;
	struct drm_gem_dma_object *gem;

	if (!fb || !h713->enabled)
		return;

	gem = drm_fb_dma_get_gem_obj(fb, 0);
	if (!gem)
		return;

	if (h713_fill_test_pattern && !h713_use_safe_scanout) {
		u32 fill_height = max_t(u32, fb->height, 1080);

		if (gem->vaddr)
			h713_fill_pattern_to_ram((u8 *)gem->vaddr + fb->offsets[0],
					      fb->width, fill_height,
					      fb->pitches[0]);
	}

	h713_program_plane_frame(h713, state, state->crtc ? state->crtc->state : NULL,
				 "update");
}

static const struct drm_simple_display_pipe_funcs h713_pipe_funcs = {
	.mode_valid	= h713_pipe_mode_valid,
	.enable		= h713_pipe_enable,
	.disable	= h713_pipe_disable,
	.update		= h713_pipe_update,
};

static const u32 h713_formats[] = {
	DRM_FORMAT_XRGB8888,
	DRM_FORMAT_ARGB8888,
};

/* ------------------------------------------------------------------ */
/* DRM driver                                                          */
/* ------------------------------------------------------------------ */
static const struct drm_mode_config_funcs h713_mode_config_funcs = {
	.fb_create	= drm_gem_fb_create,
	.atomic_check	= drm_atomic_helper_check,
	.atomic_commit	= drm_atomic_helper_commit,
};

DEFINE_DRM_GEM_DMA_FOPS(h713_drm_fops);

static const struct drm_driver h713_drm_driver = {
	.driver_features	= DRIVER_MODESET | DRIVER_GEM | DRIVER_ATOMIC,
	.name			= "h713",
	.desc			= "Allwinner H713 Display",
	.major			= 1,
	.minor			= 0,
	.patchlevel		= 0,
	.fops			= &h713_drm_fops,
	DRM_GEM_DMA_DRIVER_OPS_VMAP,
	DRM_FBDEV_DMA_DRIVER_OPS,
};

/* ------------------------------------------------------------------ */
/* Clock/reset acquisition                                             */
/* ------------------------------------------------------------------ */
static int h713_get_clocks(struct h713_drm *h713)
{
	struct device_node *tvtop_np, *ge2d_np;

	tvtop_np = of_find_compatible_node(NULL, NULL,
					   "allwinner,sunxi-tvtop");
	if (!tvtop_np) {
		dev_err(h713->drm.dev, "tvtop DT node not found\n");
		return -ENODEV;
	}

	ge2d_np = of_find_compatible_node(NULL, NULL, "trix,ge2d");

	/* Display clocks from tvtop */
	h713->clk_svp_dtl = of_clk_get_by_name(tvtop_np, "svp_dtl_clk");
	if (IS_ERR(h713->clk_svp_dtl)) {
		dev_warn(h713->drm.dev, "svp_dtl_clk not found\n");
		h713->clk_svp_dtl = NULL;
	}

	h713->clk_deint = of_clk_get_by_name(tvtop_np, "deint_clk");
	if (IS_ERR(h713->clk_deint)) {
		dev_warn(h713->drm.dev, "deint_clk not found\n");
		h713->clk_deint = NULL;
	}

	h713->clk_panel = of_clk_get_by_name(tvtop_np, "panel_clk");
	if (IS_ERR(h713->clk_panel)) {
		dev_warn(h713->drm.dev, "panel_clk not found\n");
		h713->clk_panel = NULL;
	}

	h713->clk_bus_disp = of_clk_get_by_name(tvtop_np, "clk_bus_disp");
	if (IS_ERR(h713->clk_bus_disp)) {
		dev_err(h713->drm.dev, "clk_bus_disp not found\n");
		of_node_put(tvtop_np);
		if (ge2d_np) of_node_put(ge2d_np);
		return PTR_ERR(h713->clk_bus_disp);
	}

	/* AFBD clock from ge2d */
	if (ge2d_np) {
		h713->clk_afbd = of_clk_get_by_name(ge2d_np, "clk_afbd");
		if (IS_ERR(h713->clk_afbd)) {
			dev_warn(h713->drm.dev, "clk_afbd not found\n");
			h713->clk_afbd = NULL;
		}
	}

	/* Reset from tvtop */
	h713->rst_bus_disp = of_reset_control_get_shared(tvtop_np,
							  "reset_bus_disp");
	if (IS_ERR(h713->rst_bus_disp)) {
		dev_err(h713->drm.dev, "reset_bus_disp not found\n");
		of_node_put(tvtop_np);
		if (ge2d_np) of_node_put(ge2d_np);
		return PTR_ERR(h713->rst_bus_disp);
	}

	of_node_put(tvtop_np);
	if (ge2d_np)
		of_node_put(ge2d_np);

	return 0;
}

/* ------------------------------------------------------------------ */
/* MMIO mapping                                                        */
/* ------------------------------------------------------------------ */
static int h713_map_mmio(struct h713_drm *h713)
{
	h713->tvtop = ioremap(H713_TVTOP_BASE, H713_TVTOP_SIZE);
	if (!h713->tvtop)
		return -ENOMEM;

	h713->vblend = ioremap(H713_VBLEND_BASE, H713_VBLEND_SIZE);
	if (!h713->vblend)
		goto err_tvtop;

	h713->osd = ioremap(H713_OSD_BASE, H713_OSD_SIZE);
	if (!h713->osd)
		goto err_vblend;

	h713->afbd_ctrl = ioremap(H713_AFBD_CTRL_BASE, H713_AFBD_CTRL_SIZE);
	if (!h713->afbd_ctrl)
		goto err_osd;

	h713->afbd_base = ioremap(H713_AFBD_BASE, H713_AFBD_BASE_SIZE);
	if (!h713->afbd_base)
		goto err_afbd_ctrl;

	h713->ge2d_core = ioremap(H713_GE2D_CORE_BASE, H713_GE2D_CORE_SIZE);
	if (!h713->ge2d_core)
		goto err_afbd;

	h713->lvds = ioremap(H713_LVDS_BASE, H713_LVDS_SIZE);
	if (!h713->lvds)
		goto err_ge2d;

	h713->safe_fb = ioremap_wc(H713_UBOOT_SCANOUT_ADDR, H713_SAFE_FB_SIZE);
	if (!h713->safe_fb)
		goto err_lvds;

	return 0;

err_lvds:
	iounmap(h713->lvds);
err_ge2d:
	iounmap(h713->ge2d_core);
err_afbd:
	iounmap(h713->afbd_base);
err_afbd_ctrl:
	iounmap(h713->afbd_ctrl);
err_osd:
	iounmap(h713->osd);
err_vblend:
	iounmap(h713->vblend);
err_tvtop:
	iounmap(h713->tvtop);
	return -ENOMEM;
}

static void h713_unmap_mmio(struct h713_drm *h713)
{
	if (h713->safe_fb) iounmap(h713->safe_fb);
	if (h713->lvds)  iounmap(h713->lvds);
	if (h713->ge2d_core) iounmap(h713->ge2d_core);
	if (h713->afbd_base) iounmap(h713->afbd_base);
	if (h713->afbd_ctrl) iounmap(h713->afbd_ctrl);
	if (h713->osd)   iounmap(h713->osd);
	if (h713->vblend) iounmap(h713->vblend);
	if (h713->tvtop) iounmap(h713->tvtop);
}

/* ------------------------------------------------------------------ */
/* Probe / remove                                                      */
/* ------------------------------------------------------------------ */
static int h713_drm_probe(struct platform_device *pdev)
{
	struct h713_drm *h713;
	struct drm_device *drm;
	int ret;

	h713 = devm_drm_dev_alloc(&pdev->dev, &h713_drm_driver,
				  struct h713_drm, drm);
	if (IS_ERR(h713))
		return PTR_ERR(h713);

	drm = &h713->drm;

	/* Get clocks and reset */
	ret = h713_get_clocks(h713);
	if (ret)
		return ret;

	/* Map MMIO regions */
	ret = h713_map_mmio(h713);
	if (ret)
		return ret;

	/* DMA mask */
	ret = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
	if (ret) {
		dev_err(&pdev->dev, "failed to set DMA mask\n");
		goto err_mmio;
	}

	/* Mode config */
	ret = drmm_mode_config_init(drm);
	if (ret)
		goto err_mmio;

	drm->mode_config.min_width = 1920;
	drm->mode_config.min_height = 1080;
	drm->mode_config.max_width = 1920;
	drm->mode_config.max_height = 1088;
	drm->mode_config.funcs = &h713_mode_config_funcs;

	/* Connector */
	drm_connector_helper_add(&h713->connector,
				 &h713_connector_helper_funcs);
	ret = drm_connector_init(drm, &h713->connector,
				 &h713_connector_funcs,
				 DRM_MODE_CONNECTOR_LVDS);
	if (ret)
		goto err_mmio;

	h713->connector.status = connector_status_connected;

	/* Simple display pipe: CRTC + plane + encoder */
	ret = drm_simple_display_pipe_init(drm, &h713->pipe,
					   &h713_pipe_funcs,
					   h713_formats,
					   ARRAY_SIZE(h713_formats),
					   NULL, &h713->connector);
	if (ret)
		goto err_mmio;

	drm_mode_config_reset(drm);

	/* Register DRM device */
	ret = drm_dev_register(drm, 0);
	if (ret)
		goto err_mmio;

	drm_kms_helper_poll_init(drm);

	platform_set_drvdata(pdev, drm);

	/*
	 * Diagnostic: keep the in-kernel DRM client/fb helper disabled for now.
	 * We need to verify whether a client-owned DMA framebuffer is consuming
	 * enough CMA/DMA memory to break the second CREATE_DUMB userspace run.
	 */
	/* drm_client_setup_with_fourcc(drm, DRM_FORMAT_ARGB8888); */

	dev_info(&pdev->dev, "H713 DRM driver loaded\n");
	return 0;

err_mmio:
	h713_unmap_mmio(h713);
	return ret;
}

static void h713_drm_remove(struct platform_device *pdev)
{
	struct drm_device *drm = platform_get_drvdata(pdev);
	struct h713_drm *h713 = to_h713(drm);

	drm_dev_unregister(drm);
	drm_kms_helper_poll_fini(drm);
	drm_atomic_helper_shutdown(drm);

	/* Hard teardown on remove — safe here since hardware is going away */
	if (h713->enabled) {
		h713->enabled = false;
		reset_control_assert(h713->rst_bus_disp);
		h713_clocks_disable(h713);
	}

	h713_unmap_mmio(h713);
}

static const struct of_device_id h713_drm_of_match[] = {
	{ .compatible = "trix,ge2d" },
	{ /* sentinel */ },
};
MODULE_DEVICE_TABLE(of, h713_drm_of_match);

static struct platform_driver h713_drm_platform_driver = {
	.probe	= h713_drm_probe,
	.remove	= h713_drm_remove,
	.driver	= {
		.name		= "h713-drm",
		.of_match_table	= h713_drm_of_match,
	},
};

drm_module_platform_driver(h713_drm_platform_driver);

MODULE_AUTHOR("HY310 Project");
MODULE_DESCRIPTION("Allwinner H713 DRM/KMS display driver");
MODULE_LICENSE("GPL");
