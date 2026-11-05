/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * The C ABI of the Rust half of h713_rshim_demo (rshim_demo_hw.rs). Each prototype here has a
 * #[no_mangle] pub extern "C" fn of the same name and types on the Rust side; nothing checks the
 * two against each other, so a change goes into both files.
 */
#ifndef RSHIM_DEMO_H
#define RSHIM_DEMO_H

#include <linux/compiler_types.h>
#include <linux/types.h>

/* a + b, wrapping at 2^32 */
u32 demo_add(u32 a, u32 b);

/* readl(base + offset); base is a live MMIO mapping the caller made, offset 4-aligned and inside it */
u32 demo_readl(const void __iomem *base, u32 offset);

#endif /* RSHIM_DEMO_H */
