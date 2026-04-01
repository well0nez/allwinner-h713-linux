// SPDX-License-Identifier: GPL-2.0
/*
 * sunxi_ge2d_svp.c — SVP character device (/dev/ge2d)
 *
 * From init_svp() at 0x976c:
 *   __register_chrdev(0, 0, 256, "ge2d", &svp_fops)
 *   class_create("ge2d")
 *   device_create(class, NULL, MKDEV(major, 0), NULL, "ge2d")
 *
 * Phase-1: minimal chrdev + class/device creation.
 * The full svp_ioctl dispatch (4480 bytes, 0x85ec) is Phase 2.
 */

#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/module.h>
#include <linux/poll.h>
#include <linux/uaccess.h>

#include "sunxi_ge2d.h"

/* ------------------------------------------------------------------ */
/* File operations                                                       */
/* ------------------------------------------------------------------ */

static int svp_open(struct inode *inode, struct file *filp)
{
	/*
	 * Stock open stores a pointer to the ge2d_device in filp->private_data
	 * via the container_of pattern on the cdev.  We use the global gdev
	 * stored during init_svp() equivalent.
	 */
	return 0;
}

static int svp_release(struct inode *inode, struct file *filp)
{
	return 0;
}

static ssize_t svp_read(struct file *filp, char __user *buf,
			size_t count, loff_t *ppos)
{
	return 0;
}

static ssize_t svp_write(struct file *filp, const char __user *buf,
			 size_t count, loff_t *ppos)
{
	return count;
}

static int svp_mmap(struct file *filp, struct vm_area_struct *vma)
{
	/*
	 * Phase 2: map OSD framebuffer / fence state.
	 * Return ENOSYS for now so callers know it's unimplemented.
	 */
	return -ENOSYS;
}

static __poll_t svp_poll(struct file *filp, poll_table *wait)
{
	return 0;
}

static long svp_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
	/*
	 * Phase 2: full dispatch of the 4480-byte stock ioctl handler at 0x85ec.
	 * For now log the command and return ENOTTY so well-behaved callers
	 * know the ioctl is not yet handled.
	 */
	pr_debug("ge2d: svp_ioctl cmd=0x%08x (not yet implemented)\n", cmd);
	return -ENOTTY;
}

static const struct file_operations svp_fops = {
	.owner          = THIS_MODULE,
	.open           = svp_open,
	.release        = svp_release,
	.read           = svp_read,
	.write          = svp_write,
	.mmap           = svp_mmap,
	.poll           = svp_poll,
	.unlocked_ioctl = svp_ioctl,
	.llseek         = noop_llseek,
};

/* ------------------------------------------------------------------ */
/* Init / exit                                                           */
/* ------------------------------------------------------------------ */

/**
 * ge2d_svp_init - register the /dev/ge2d character device
 * @gdev: driver device context
 *
 * Mirrors init_svp() at 0x976c:
 *   major = __register_chrdev(0, 0, 256, "ge2d", &svp_fops)
 *   class = class_create("ge2d")
 *   device_create(class, NULL, MKDEV(major, 0), NULL, "ge2d")
 */
int ge2d_svp_init(struct ge2d_device *gdev)
{
	int major;

	/*
	 * __register_chrdev with baseminor=0, count=256 allocates a dynamic
	 * major and registers 256 minors; identical to stock call.
	 */
	major = __register_chrdev(0, 0, 256, GE2D_CLASS_NAME, &svp_fops);
	if (major < 0) {
		dev_err(gdev->dev, "failed to register ge2d chrdev: %d\n", major);
		return major;
	}

	gdev->chrdev_major = major;
	gdev->ge2d_devnum  = MKDEV(major, 0);

	gdev->ge2d_class = class_create(GE2D_CLASS_NAME);
	if (IS_ERR(gdev->ge2d_class)) {
		int ret = PTR_ERR(gdev->ge2d_class);

		dev_err(gdev->dev, "failed to create ge2d class: %d\n", ret);
		gdev->ge2d_class = NULL;
		__unregister_chrdev(major, 0, 256, GE2D_CLASS_NAME);
		return ret;
	}

	gdev->ge2d_cdev = device_create(gdev->ge2d_class, NULL,
					gdev->ge2d_devnum, NULL,
					GE2D_CLASS_NAME);
	if (IS_ERR(gdev->ge2d_cdev)) {
		int ret = PTR_ERR(gdev->ge2d_cdev);

		dev_err(gdev->dev, "failed to create ge2d device node: %d\n", ret);
		gdev->ge2d_cdev = NULL;
		class_destroy(gdev->ge2d_class);
		gdev->ge2d_class = NULL;
		__unregister_chrdev(major, 0, 256, GE2D_CLASS_NAME);
		return ret;
	}

	dev_info(gdev->dev, "created /dev/ge2d (major=%d)\n", major);
	return 0;
}

/**
 * ge2d_svp_exit - undo ge2d_svp_init
 * @gdev: driver device context
 *
 * Mirrors the cleanup path in ge2d_drv_remove at 0x79f4.
 */
void ge2d_svp_exit(struct ge2d_device *gdev)
{
	if (gdev->ge2d_cdev) {
		device_destroy(gdev->ge2d_class, gdev->ge2d_devnum);
		gdev->ge2d_cdev = NULL;
	}

	if (gdev->ge2d_class) {
		class_destroy(gdev->ge2d_class);
		gdev->ge2d_class = NULL;
	}

	if (gdev->chrdev_major > 0) {
		__unregister_chrdev(gdev->chrdev_major, 0, 256,
				    GE2D_CLASS_NAME);
		gdev->chrdev_major = 0;
	}
}
