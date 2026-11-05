// SPDX-License-Identifier: GPL-2.0
/* Spec-side bench tool (59 X4): EDID + hot-plug through the ARISC with the display firmware never started. */
#include <linux/module.h>
#include <linux/firmware.h>
#include <linux/platform_device.h>
#include <linux/soc/sunxi/h713-arisc.h>

static unsigned int port = 1;
module_param(port, uint, 0444);
static char *file = "hy310-edid.bin";
module_param(file, charp, 0444);
static int hpd;			/* 0 none, 1 up, 2 down, 3 reset (low, then up after ~840 ms) */
module_param(hpd, int, 0444);

static struct platform_device *pdev;

static int __init spx4_init(void)
{
	const struct firmware *fw;
	u8 *buf;
	int ret, i;
	u8 sum = 0;

	pdev = platform_device_register_simple("spx4", -1, NULL, 0);
	if (IS_ERR(pdev))
		return PTR_ERR(pdev);
	ret = request_firmware(&fw, file, &pdev->dev);
	if (ret) {
		pr_info("spx4: firmware %s: %d\n", file, ret);
		goto out_dev;
	}
	pr_info("spx4: %s %zu bytes, port %u\n", file, fw->size, port);
	ret = arisc_hdmi_edid_init(port, fw->data, fw->size);
	pr_info("spx4: edid_init(port %u, %zu bytes) = %d\n", port, fw->size, ret);
	release_firmware(fw);
	buf = kzalloc(256, GFP_KERNEL);
	if (buf) {
		ret = arisc_hdmi_get_edid(port, buf, 256);
		for (i = 0; i < 256; i++)
			sum += buf[i];
		pr_info("spx4: get_edid(port %u) = %d: %*ph | 128.. %*ph | byte168 %02x byte255 %02x sum %02x\n",
			port, ret, 16, buf, 8, buf + 128, buf[168], buf[255], sum);
		kfree(buf);
	}
	if (hpd) {
		ret = arisc_hdmi_hpd(port, hpd);
		pr_info("spx4: hpd(port %u, %d) = %d\n", port, hpd, ret);
	}
	return 0;
out_dev:
	platform_device_unregister(pdev);
	return ret;
}

static void __exit spx4_exit(void)
{
	platform_device_unregister(pdev);
}

module_init(spx4_init);
module_exit(spx4_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("spec-side bench tool: EDID/hot-plug via the ARISC");
