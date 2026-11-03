// SPDX-License-Identifier: GPL-2.0-only
//! h713_rshim_demo: the Rust half. Not a Rust module (no `module!`): an object of the C module
//! h713_rshim_demo with two functions of C ABI, declared for C in `rshim_demo.h`. It maps nothing; the C side
//! owns the mapping and hands the pointer in.

use kernel::{bindings, ffi::c_void};

// A module file of a reused no_std crate, compiled as a submodule of this crate (docs/kernel-rust.md). Its
// items are `pub` for its own crate; here they are private, which the kernel's -Wunreachable_pub flags.
#[allow(unreachable_pub)]
#[path = "common/demo_calc.rs"]
mod demo_calc;

/// `u32 demo_add(u32 a, u32 b)`: `a + b`, wrapping at 2^32.
#[no_mangle]
pub extern "C" fn demo_add(a: u32, b: u32) -> u32 {
    demo_calc::add(a, b)
}

/// `u32 demo_readl(const void __iomem *base, u32 offset)`: `readl(base + offset)`.
///
/// # Safety
///
/// `base` must be a live MMIO mapping made by the caller, and `offset` 4-aligned with `offset + 4` inside it.
#[no_mangle]
pub unsafe extern "C" fn demo_readl(base: *const c_void, offset: u32) -> u32 {
    // SAFETY: by this function's contract `base + offset` is a mapped, aligned 32-bit register.
    unsafe { bindings::readl(base.cast::<u8>().add(offset as usize).cast::<c_void>()) }
}
