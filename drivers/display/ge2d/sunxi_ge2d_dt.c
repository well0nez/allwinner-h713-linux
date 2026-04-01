// SPDX-License-Identifier: GPL-2.0

#include <linux/gpio.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_gpio.h>

#include "sunxi_ge2d.h"

/*
 * Maximum sane GPIO number on H713 (from stock limit check at 0x7a5c:
 * "if (named_gpio_flags >= 0x1A0)" → 0x1A0 = 416).
 */
#define GE2D_GPIO_MAX	416

struct ge2d_dt_u32_field {
	const char *name;
	u32        *dst;
};

static int ge2d_panel_type_from_resolution(u32 width, u32 height)
{
	if (width == 1366 && height == 768)
		return GE2D_PANEL_TYPE_1366X768;

	if (width == 360 && height == 640)
		return GE2D_PANEL_TYPE_360X640;

	if (width == 640 && height == 360)
		return GE2D_PANEL_TYPE_640X360;

	if (width == 1280 && height == 720)
		return GE2D_PANEL_TYPE_1280X720;

	return GE2D_PANEL_TYPE_DEFAULT;
}

/**
 * ge2d_find_panel_node - find the DTS node containing panel properties
 *
 * Stock ge2d_drv_probe (IDA 0x9ac4) reads panel_* properties directly
 * from the "allwinner,sunxi-tvtop" compatible node (v3 in the decompile).
 * On our system the tvtop@5700000 has both the driver-specific properties
 * AND the panel_* properties.  So we simply return tvtop_np itself.
 *
 * Fallback: if someone puts properties in a separate tvtop@1 node,
 * search for that by path.
 */
static struct device_node *ge2d_find_panel_node(struct device_node *tvtop_np)
{
	struct device_node *np;

	if (!tvtop_np)
		return NULL;

	/* Stock behaviour: panel props live directly on the tvtop node */
	if (of_find_property(tvtop_np, "panel_width", NULL))
		return of_node_get(tvtop_np);

	/* Fallback: separate tvtop@1 node (legacy layout) */
	np = of_find_node_by_path("/soc/tvtop@1");
	if (np)
		return np;

	/* Last resort: return tvtop node itself */
	return of_node_get(tvtop_np);
}

static void ge2d_read_u32_fields(struct device_node *np,
				 struct ge2d_dt_u32_field *fields,
				 size_t count)
{
	size_t i;

	for (i = 0; i < count; i++)
		of_property_read_u32(np, fields[i].name, fields[i].dst);
}

/**
 * get_panel_pin_info - parse a named GPIO from DTS
 * @np:   device_node to read from (tvtop panel node)
 * @name: DTS property name (e.g. "panel_bl_en")
 * @pin:  output descriptor to fill
 *
 * Mirrors stock get_panel_pin_info() at 0x7a5c.
 *
 * Stock (kernel 5.4) used of_get_named_gpio_flags() and checked
 * !(flags & 1) for active_high.  In kernel 6.16.7 the _flags variant
 * is removed.  We use of_get_named_gpio() which returns just the GPIO
 * number.  Polarity defaults to active-high, matching stock behaviour
 * for panel GPIOs (the vendor DTS properties carry a separate data
 * field for initial level, not the GPIO_ACTIVE_LOW flag).
 *
 * Pins >= 0x1A0 (416) are treated as absent (stock limit check).
 */
static int get_panel_pin_info(struct device_node *np,
			      const char *name,
			      struct ge2d_pin_info *pin)
{
	int gpio;

	pin->gpio        = -1;
	pin->active_high = true;
	pin->requested   = false;

	if (!np)
		return -ENODEV;

	gpio = of_get_named_gpio(np, name, 0);
	if (gpio < 0)
		return gpio;

	/* Stock driver rejects anything >= 0x1A0 (416) as invalid */
	if (gpio >= GE2D_GPIO_MAX) {
		pr_warn("ge2d: %s gpio %d >= %d, treating as absent\n",
			name, gpio, GE2D_GPIO_MAX);
		return -EINVAL;
	}

	pin->gpio = gpio;
	/* active_high stays true — stock default for panel GPIOs */
	return 0;
}

int ge2d_parse_dt(struct ge2d_device *gdev)
{
	struct ge2d_panel_config *panel = &gdev->panel;
	char gpio_name[24];
	int i;
	struct ge2d_dt_u32_field fields[] = {
		{ "panel_protocol",          &panel->protocol          },
		{ "panel_bitwidth",          &panel->bitwidth          },
		{ "panel_data_swap",         &panel->data_swap         },
		{ "panel_ssc_span",          &panel->ssc_span          },
		{ "panel_ssc_step",          &panel->ssc_step          },
		{ "panel_ssc_en",            &panel->ssc_en            },
		{ "panel_dclk_freq",         &panel->dclk_freq         },
		{ "panel_de_current",        &panel->de_current        },
		{ "panel_even_data_current", &panel->even_data_current },
		{ "panel_odd_data_current",  &panel->odd_data_current  },
		{ "panel_vs_invert",         &panel->vs_invert         },
		{ "panel_hs_invert",         &panel->hs_invert         },
		{ "panel_de_invert",         &panel->de_invert         },
		{ "panel_dclk_invert",       &panel->dclk_invert       },
		{ "panel_mirror_mode",       &panel->mirror_mode       },
		{ "panel_dual_port",         &panel->dual_port         },
		{ "panel_debug_en",          &panel->debug_en          },
		{ "panel_pwm_ch",            &panel->pwm_ch            },
		{ "panel_pwm_freq",          &panel->pwm_freq          },
		{ "panel_pwm_pol",           &panel->pwm_pol           },
		{ "panel_pwm_min",           &panel->pwm_min           },
		{ "panel_pwm_max",           &panel->pwm_max           },
		{ "panel_backlight",         &panel->backlight         },
		{ "panel_poweron_delay0",    &panel->poweron_delay[0]  },
		{ "panel_poweron_delay1",    &panel->poweron_delay[1]  },
		{ "panel_poweron_delay2",    &panel->poweron_delay[2]  },
		{ "panel_powerdown_delay0",  &panel->powerdown_delay[0]},
		{ "panel_powerdown_delay1",  &panel->powerdown_delay[1]},
		{ "panel_powerdown_delay2",  &panel->powerdown_delay[2]},
		{ "panel_htotal",            &panel->htotal            },
		{ "panel_vtotal",            &panel->vtotal            },
		{ "panel_hsync",             &panel->hsync             },
		{ "panel_vsync",             &panel->vsync             },
		{ "panel_hsync_pol",         &panel->hsync_pol         },
		{ "panel_vsync_pol",         &panel->vsync_pol         },
		{ "panel_width",             &panel->width             },
		{ "panel_height",            &panel->height            },
		{ "panel_hbp",               &panel->hbp               },
		{ "panel_vbp",               &panel->vbp               },
		{ "project_id",              &panel->project_id        },
		{ "panel_lvds0_pol",         &panel->lvds0_pol         },
		{ "panel_lvds1_pol",         &panel->lvds1_pol         },
	};

	memset(panel, 0, sizeof(*panel));
	panel->panel_type = GE2D_PANEL_TYPE_DEFAULT;

	gdev->tvtop_np = of_find_compatible_node(NULL, NULL,
						 "allwinner,sunxi-tvtop");
	if (!gdev->tvtop_np)
		return -ENODEV;

	gdev->panel_np = ge2d_find_panel_node(gdev->tvtop_np);
	if (!gdev->panel_np)
		gdev->panel_np = of_node_get(gdev->tvtop_np);

	ge2d_read_u32_fields(gdev->panel_np, fields, ARRAY_SIZE(fields));

	/* Parse GPIOs — stock used of_get_named_gpio_flags, we use of_get_named_gpio (6.16.7) */
	get_panel_pin_info(gdev->panel_np, "panel_bl_en",    &panel->bl_gpio);
	get_panel_pin_info(gdev->panel_np, "panel_power_en", &panel->power_gpio);

	for (i = 0; i < GE2D_PANEL_GPIO_COUNT; i++) {
		snprintf(gpio_name, sizeof(gpio_name), "panel_gpio_%d", i);
		get_panel_pin_info(gdev->panel_np, gpio_name, &panel->gpios[i]);
	}

	if (panel->width && panel->height)
		panel->panel_type =
			ge2d_panel_type_from_resolution(panel->width,
							panel->height);

	if (!panel->pwm_max)
		panel->pwm_max = 100;

	return 0;
}

void ge2d_dt_cleanup(struct ge2d_device *gdev)
{
	of_node_put(gdev->panel_np);
	of_node_put(gdev->tvtop_np);
	gdev->panel_np = NULL;
	gdev->tvtop_np = NULL;
}
