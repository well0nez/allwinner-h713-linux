// SPDX-License-Identifier: GPL-2.0
/*
 * DLPC3435 DLP projector controller - I2C companion for ge2d
 *
 * Stock behavior (from IDA RE of ge2d_dev.ko):
 *   - dlpc3435_init is registered as a panel callback via lcd_set_panel_funs()
 *   - It is NEVER called during initial probe -- U-Boot initializes the DLPC3435
 *   - It is ONLY called from ge2d_resume(), after:
 *       1. Panel power GPIOs are set
 *       2. OSD/display pipeline is resumed (osd_resume_request)
 *       3. panel_poweron_delay1 (550ms) has elapsed
 *   - The I2C driver is registered at module load, but the init sequence
 *     only runs when the display pipeline is fully active
 *
 * I2C address: 0x1B (7-bit) = 0x36 (8-bit write), verified from stock
 * normal_i2c array at ge2d_dev.ko offset 0x18d7c.
 */

#include <linux/delay.h>

#include "sunxi_ge2d.h"

static struct i2c_client *ge2d_dlpc3435_client;

static int ge2d_dlpc3435_probe(struct i2c_client *client)
{
	ge2d_dlpc3435_client = client;
	dev_info(&client->dev, "DLPC3435 companion attached at 0x%02x\n",
		 client->addr);
	return 0;
}

static void ge2d_dlpc3435_remove(struct i2c_client *client)
{
	if (ge2d_dlpc3435_client == client)
		ge2d_dlpc3435_client = NULL;
}

static const struct i2c_device_id ge2d_dlpc3435_ids[] = {
	{ "DLPC3435", 0 },
	{ }
};
MODULE_DEVICE_TABLE(i2c, ge2d_dlpc3435_ids);

static const struct of_device_id ge2d_dlpc3435_of_match[] = {
	{ .compatible = "dlpc,dlpc3435" },
	{ }
};
MODULE_DEVICE_TABLE(of, ge2d_dlpc3435_of_match);

static struct i2c_driver ge2d_dlpc3435_driver = {
	.driver = {
		.name = "DLPC3435",
		.of_match_table = ge2d_dlpc3435_of_match,
	},
	.probe = ge2d_dlpc3435_probe,
	.remove = ge2d_dlpc3435_remove,
	.id_table = ge2d_dlpc3435_ids,
};

/*
 * ge2d_dlpc3435_run_init_sequence - send the DLPC3435 configuration
 *
 * This writes panel resolution and triggers the DLP light engine.
 * Must only be called when the display pipeline is active and the
 * chip is powered (panel_power_en HIGH, OSD running, delay elapsed).
 *
 * Stock register sequence (IDA @ 0x11af0..0x11b64):
 *   reg 46 (0x2E): 4-byte block [width_lo, width_hi, height_lo, height_hi]
 *   reg 18 (0x12): same 4-byte block
 *   reg 16 (0x10): 8-byte block [0,0,0,0, width_lo, width_hi, height_lo, height_hi]
 *   reg 26 (0x1A): byte 1  (start)
 *   reg  5 (0x05): byte 0
 *   msleep(20)
 *   reg 26 (0x1A): byte 0  (commit)
 */
static int ge2d_dlpc3435_run_init_sequence(struct ge2d_device *gdev)
{
	u16 width = min_t(u32, gdev->panel.width, U16_MAX);
	u16 height = min_t(u32, gdev->panel.height, U16_MAX);
	u8 block4[4];
	u8 block8[8] = { 0 };
	int ret;

	if (!ge2d_dlpc3435_client) {
		dev_dbg(gdev->dev, "DLPC3435 client not present, skipping init\n");
		return -ENODEV;
	}

	block4[0] = width & 0xff;
	block4[1] = (width >> 8) & 0xff;
	block4[2] = height & 0xff;
	block4[3] = (height >> 8) & 0xff;
	block8[4] = block4[0];
	block8[5] = block4[1];
	block8[6] = block4[2];
	block8[7] = block4[3];

	ret = i2c_smbus_write_i2c_block_data(ge2d_dlpc3435_client, 46,
					     sizeof(block4), block4);
	if (ret < 0)
		goto err_out;

	ret = i2c_smbus_write_i2c_block_data(ge2d_dlpc3435_client, 18,
					     sizeof(block4), block4);
	if (ret < 0)
		goto err_out;

	ret = i2c_smbus_write_i2c_block_data(ge2d_dlpc3435_client, 16,
					     sizeof(block8), block8);
	if (ret < 0)
		goto err_out;

	ret = i2c_smbus_write_byte_data(ge2d_dlpc3435_client, 26, 1);
	if (ret < 0)
		goto err_out;

	ret = i2c_smbus_write_byte_data(ge2d_dlpc3435_client, 5, 0);
	if (ret < 0)
		goto err_out;

	msleep_interruptible(20);

	ret = i2c_smbus_write_byte_data(ge2d_dlpc3435_client, 26, 0);
	if (ret < 0)
		goto err_out;

	dev_info(gdev->dev, "DLPC3435 init sequence applied for %ux%u panel\n",
		 width, height);
	return 0;

err_out:
	dev_warn(gdev->dev, "DLPC3435 init step failed: %d\n", ret);
	return ret;
}

/*
 * ge2d_dlpc3435_schedule_init - register the I2C driver (probe-time)
 *
 * Only registers the I2C driver so the DTS node is matched and the
 * client handle is captured.  Does NOT send any I2C commands --
 * at initial boot, U-Boot has already configured the DLPC3435.
 *
 * Stock behavior: dlpc3435_init() is only called from ge2d_resume(),
 * never from ge2d_drv_probe().
 */
int ge2d_dlpc3435_schedule_init(struct ge2d_device *gdev)
{
	int ret;

	if (!ge2d_enable_dlpc3435)
		return 0;

	ret = i2c_add_driver(&ge2d_dlpc3435_driver);
	if (ret) {
		dev_warn(gdev->dev,
			 "failed to register DLPC3435 I2C driver: %d\n", ret);
		return 0;	/* non-fatal */
	}

	gdev->dlpc3435_registered = true;

	/*
	 * Do NOT schedule any init work here.  At initial boot the DLPC3435
	 * was already configured by U-Boot.  The init sequence will be run
	 * from ge2d_dlpc3435_resume_init() after a suspend/resume cycle,
	 * matching the stock ge2d_resume() flow.
	 */
	if (ge2d_dlpc3435_client)
		dev_info(gdev->dev,
			 "DLPC3435 registered (U-Boot pre-initialized, skipping init sequence)\n");
	else
		dev_info(gdev->dev,
			 "DLPC3435 driver registered, client not yet matched\n");

	return 0;
}

/*
 * ge2d_dlpc3435_resume_init - re-initialize DLPC3435 after suspend/resume
 *
 * Stock calls this from ge2d_resume() after:
 *   1. panel_power_en GPIO HIGH
 *   2. panel GPIOs 0-3 enabled
 *   3. msleep(panel_poweron_delay0)
 *   4. osd_resume_request() -- display pipeline started
 *   5. IRQs re-enabled
 *   6. ge2d_resume_operation()
 *   7. msleep(panel_poweron_delay1 = 550ms)
 *   8. --> dlpc3435_init() called HERE <--
 */
int ge2d_dlpc3435_resume_init(struct ge2d_device *gdev)
{
	if (!ge2d_enable_dlpc3435 || !gdev->dlpc3435_registered)
		return 0;

	return ge2d_dlpc3435_run_init_sequence(gdev);
}

void ge2d_dlpc3435_cancel_init(struct ge2d_device *gdev)
{
	if (!gdev->dlpc3435_registered)
		return;

	i2c_del_driver(&ge2d_dlpc3435_driver);
	gdev->dlpc3435_registered = false;
	ge2d_dlpc3435_client = NULL;
}
