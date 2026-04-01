// SPDX-License-Identifier: GPL-2.0
/*
 * GE2D panel GPIO helpers
 *
 * Mirrors stock get_panel_pin_info / __panel_pin_enable behaviour.
 */

#include <linux/delay.h>
#include <linux/gpio.h>
#include <linux/gpio/consumer.h>

#include "sunxi_ge2d.h"

/*
 * ge2d_request_one_pin - request and initialise a single panel GPIO
 *
 * init_on=true  → GPIOF_OUT_INIT_HIGH (keep power/backlight on at probe)
 * init_on=false → GPIOF_OUT_INIT_LOW
 *
 * If the GPIO is already claimed (e.g. by a gpio-hog or board-mgr),
 * we tolerate EBUSY and skip ownership — the hog keeps it driven.
 */
static int ge2d_request_one_pin(struct ge2d_device *gdev,
				struct ge2d_pin_info *pin,
				const char *label, bool init_on)
{
	unsigned long flags;
	bool level;
	int ret;

	if (pin->gpio < 0)
		return 0;	/* not present, nothing to do */

	/* Translate logical on/off to electrical level using polarity */
	level = init_on ? pin->active_high : !pin->active_high;
	flags = level ? GPIOF_OUT_INIT_HIGH : GPIOF_OUT_INIT_LOW;

		/*
	 * Use gpio_request_one (NOT devm_) so GPIOs survive rmmod.
	 * Stock ge2d_drv_remove (0x79f4) does NOT release GPIOs --
	 * panel power and backlight must stay driven. PB5 LOW kills fan.
	 */
	ret = gpio_request_one(pin->gpio, flags, label);
	if (ret == -EBUSY) {
		/*
		 * GPIO already claimed (e.g. by gpio-hog or board-mgr).
		 * Stock doesn't fail here — it just uses the pin as-is.
		 * Mark as not-requested so ge2d_drive_pin() skips control.
		 */
		dev_info(gdev->dev, "%s gpio %d busy (hog/other driver), sharing\n",
			 label, pin->gpio);
		pin->requested = false;
		return 0;
	}
	if (ret)
		return dev_err_probe(gdev->dev, ret,
				     "failed to request %s gpio %d\n",
				     label, pin->gpio);

	pin->requested = true;
	return 0;
}

/**
 * ge2d_drive_pin - assert or deassert a GPIO output
 * @pin: pin descriptor
 * @on:  logical on/off (polarity applied internally)
 *
 * Mirrors __panel_pin_enable() at 0x7960.
 */
static int ge2d_drive_pin(struct ge2d_pin_info *pin, bool on)
{
	struct gpio_desc *desc;
	int value;

	if (pin->gpio < 0 || !pin->requested)
		return 0;

	desc = gpio_to_desc(pin->gpio);
	if (!desc)
		return -ENODEV;

	value = on ? pin->active_high : !pin->active_high;
	return gpiod_direction_output_raw(desc, value);
}

/* ------------------------------------------------------------------ */

int ge2d_panel_request_gpios(struct ge2d_device *gdev)
{
	int i;
	int ret;

	/* Power and backlight init HIGH — U-Boot left them on, keep it */
	ret = ge2d_request_one_pin(gdev, &gdev->panel.power_gpio,
				   "panel_power_en", true);
	if (ret)
		return ret;

	ret = ge2d_request_one_pin(gdev, &gdev->panel.bl_gpio,
				   "panel_bl_en", true);
	if (ret)
		return ret;

	for (i = 0; i < GE2D_PANEL_GPIO_COUNT; i++) {
		char label[24];

		snprintf(label, sizeof(label), "panel_gpio_%d", i);
		ret = ge2d_request_one_pin(gdev, &gdev->panel.gpios[i],
					   label, true);
		if (ret)
			return ret;
	}

	return 0;
}

int ge2d_panel_set_power(struct ge2d_device *gdev, bool on)
{
	int ret;

	ret = ge2d_drive_pin(&gdev->panel.power_gpio, on);
	if (ret)
		return ret;

	if (on)
		msleep(gdev->panel.poweron_delay[0]);
	else
		msleep(gdev->panel.powerdown_delay[0]);

	return 0;
}

int ge2d_panel_set_backlight_enable(struct ge2d_device *gdev, bool on)
{
	return ge2d_drive_pin(&gdev->panel.bl_gpio, on);
}

void ge2d_panel_maybe_start_lvds_watchdog(struct ge2d_device *gdev)
{
	if (!ge2d_enable_lvds_watchdog)
		return;
	dev_info(gdev->dev, "LVDS FIFO watchdog deferred\n");
}
