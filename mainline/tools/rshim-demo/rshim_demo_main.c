// SPDX-License-Identifier: GPL-2.0-only
/*
 * h713_rshim_demo: the C half. Proves the C-shell / Rust-hardware-layer split of docs/kernel-rust.md:
 * C owns the module (init/exit, license, the mapping), Rust provides functions with a C ABI, and both
 * are linked into one .ko. The register read is the H6-style system-control "version" word at
 * 0x03000024 (syscon@3000000 in sun50i-h713.dtsi): mapped by C, read once by Rust and once by C.
 */
#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/printk.h>

#include "rshim_demo.h"

#define DEMO_SYSCON_BASE	0x03000000
#define DEMO_SYSCON_SIZE	0x1000
#define DEMO_VERSION_REG	0x24

static int __init h713_rshim_demo_init(void)
{
	void __iomem *base;
	u32 sum, wrap, from_rust, from_c;

	sum = demo_add(40, 2);
	wrap = demo_add(0xffffffff, 2);
	pr_info("demo_add(40, 2) = %u, demo_add(0xffffffff, 2) = %u (Rust)\n", sum, wrap);

	base = ioremap(DEMO_SYSCON_BASE, DEMO_SYSCON_SIZE);
	if (!base)
		return -ENOMEM;
	from_rust = demo_readl(base, DEMO_VERSION_REG);
	from_c = readl(base + DEMO_VERSION_REG);
	iounmap(base);
	pr_info("0x%08x: demo_readl = 0x%08x (Rust), readl = 0x%08x (C)\n",
		DEMO_SYSCON_BASE + DEMO_VERSION_REG, from_rust, from_c);

	if (sum != 42 || wrap != 1 || from_rust != from_c) {
		pr_err("C and Rust disagree\n");
		return -EIO;
	}
	pr_info("C -> Rust calls ok\n");
	return 0;
}

static void __exit h713_rshim_demo_exit(void)
{
	pr_info("unloaded\n");
}

module_init(h713_rshim_demo_init);
module_exit(h713_rshim_demo_exit);

MODULE_DESCRIPTION("H713 demo: a C module calling a Rust hardware layer linked into the same .ko");
MODULE_LICENSE("GPL");
