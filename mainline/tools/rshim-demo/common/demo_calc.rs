// SPDX-License-Identifier: GPL-2.0-only
//! Stands for a module of an existing `no_std`, alloc-free crate: only `core`, no `std`, no `alloc`, no kernel
//! crate, no floats. The kernel module pulls it in with `#[path = "common/demo_calc.rs"] mod demo_calc;`; on the
//! host the same file is tested on its own: `rustc --edition 2021 --test common/demo_calc.rs -o /tmp/t && /tmp/t`.

/// `a + b`, wrapping at 2^32. Plain `a + b` would be a panic (`BUG()` in the kernel, which builds with
/// `CONFIG_RUST_OVERFLOW_CHECKS=y`) on overflow, so the hardware layer says which arithmetic it means.
pub fn add(a: u32, b: u32) -> u32 {
    a.wrapping_add(b)
}

#[cfg(test)]
mod tests {
    use super::add;

    #[test]
    fn adds_and_wraps() {
        assert_eq!(add(40, 2), 42);
        assert_eq!(add(u32::MAX, 2), 1);
    }
}
