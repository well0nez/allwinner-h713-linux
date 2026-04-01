// SPDX-License-Identifier: GPL-2.0

#include <linux/backlight.h>
#include <linux/gpio.h>
#include <linux/math64.h>

#include "sunxi_ge2d.h"

static u64 ge2d_pwm_period_ns(const struct ge2d_panel_config *panel)
{
	if (!panel->pwm_freq)
		return 0;

	return DIV_ROUND_CLOSEST_ULL((u64)NSEC_PER_SEC, panel->pwm_freq);
}

static int ge2d_backlight_apply_pwm(struct ge2d_device *gdev, u32 brightness,
				    bool on)
{
	struct pwm_state state;
	u64 period;
	u32 max;
	u32 level_pct;

	if (!gdev->pwm)
		return 0;

	pwm_init_state(gdev->pwm, &state);
	period = ge2d_pwm_period_ns(&gdev->panel);
	if (period)
		state.period = period;

	state.polarity = gdev->panel.pwm_pol ? PWM_POLARITY_INVERSED :
						 PWM_POLARITY_NORMAL;
	if (!on) {
		state.enabled = false;
		state.duty_cycle = 0;
		return pwm_apply_might_sleep(gdev->pwm, &state);
	}

	max = max_t(u32, 1, gdev->backlight->props.max_brightness);
	level_pct = gdev->panel.pwm_min;
	if (gdev->panel.pwm_max > gdev->panel.pwm_min)
		level_pct += DIV_ROUND_CLOSEST((brightness *
					(gdev->panel.pwm_max - gdev->panel.pwm_min)),
					max);

	state.enabled = true;
	state.duty_cycle = div_u64(state.period * level_pct, 100);
	return pwm_apply_might_sleep(gdev->pwm, &state);
}

static int ge2d_backlight_update_status(struct backlight_device *bd)
{
	struct ge2d_device *gdev = bl_get_data(bd);
	u32 brightness = backlight_get_brightness(bd);
	bool on = brightness > 0 && !backlight_is_blank(bd);
	int ret;

	ret = ge2d_panel_set_backlight_enable(gdev, on);
	if (ret)
		return ret;

	return ge2d_backlight_apply_pwm(gdev, brightness, on);
}

static const struct backlight_ops ge2d_backlight_ops = {
	.options = BL_CORE_SUSPENDRESUME,
	.update_status = ge2d_backlight_update_status,
};

int ge2d_backlight_init(struct ge2d_device *gdev)
{
	struct backlight_properties props;
	int ret;

	if (gdev->panel.bl_gpio.gpio < 0 && !gdev->panel.pwm_freq) {
		dev_info(gdev->dev,
			 "no backlight-capable panel properties present; skipping backlight class device\n");
		return 0;
	}

	gdev->pwm = devm_pwm_get(gdev->dev, NULL);
	if (IS_ERR(gdev->pwm)) {
		int ret2 = PTR_ERR(gdev->pwm);

		if (ret2 == -EPROBE_DEFER)
			return ret2;

		dev_info(gdev->dev,
			 "PWM not available (%d); GPIO-only backlight\n", ret2);
		gdev->pwm = NULL;
	}

	/*
	 * Detect whether U-Boot / fastlogo left the backlight on by
	 * reading the current hardware state of the bl_gpio pin.
	 * This avoids blindly toggling PB5 which also controls fan power.
	 */
	{
		bool hw_bl_on = false;

		if (gdev->panel.bl_gpio.gpio >= 0) {
			struct gpio_desc *desc = gpio_to_desc(gdev->panel.bl_gpio.gpio);

			if (desc)
				hw_bl_on = !!gpiod_get_raw_value(desc);
		}

		dev_dbg(gdev->dev, "backlight hw state at probe: %s\n",
			hw_bl_on ? "on" : "off");

		memset(&props, 0, sizeof(props));
		props.type = BACKLIGHT_RAW;
		props.max_brightness = max_t(u32, 1, gdev->panel.pwm_max);
		props.brightness = hw_bl_on ?
			min_t(u32, gdev->panel.backlight, props.max_brightness) : 0;
		props.power = hw_bl_on ? FB_BLANK_UNBLANK : FB_BLANK_POWERDOWN;
	}

	gdev->backlight = devm_backlight_device_register(gdev->dev,
						 GE2D_BACKLIGHT_NAME,
						 gdev->dev, gdev,
						 &ge2d_backlight_ops,
						 &props);
	if (IS_ERR(gdev->backlight))
		return dev_err_probe(gdev->dev, PTR_ERR(gdev->backlight),
				     "failed to register backlight\n");

	ret = backlight_update_status(gdev->backlight);
	if (ret)
		return ret;

	return 0;
}

void ge2d_backlight_exit(struct ge2d_device *gdev)
{
	if (!gdev->backlight)
		return;

	gdev->backlight->props.power = FB_BLANK_POWERDOWN;
	gdev->backlight->props.brightness = 0;
	backlight_update_status(gdev->backlight);

}
