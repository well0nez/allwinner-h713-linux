# Kernel Rust: CONFIG_RUST, and a C module with a Rust hardware layer

Linux 6.18 has Rust bindings for platform devices, MMIO, clocks, IRQs, DMA and OF, but none for DRM/KMS. A driver that
wants its hardware layer in Rust and its DRM side in C therefore needs one module of both languages. This page says
how the project builds such a module, and what the Rust part may and may not do. The proof is `h713_rshim_demo`
(`mainline/tools/rshim-demo/`), loaded on the HY320.

## Versions

| | version | why |
|---|---|---|
| rustc | 1.89.0 (29483883e 2025-08-04), via rustup-init 1.28.2 | 6.18 wants >= 1.78; 1.89 is built on LLVM 20 like the container's clang 20.1.8 |
| rust-src | of 1.89.0 | the kernel builds `core` from it (`$(rustc --print sysroot)/lib/rustlib/src/rust/library`) |
| bindgen | bindgen-cli 0.72.1 (`cargo install --locked`) | 6.18 wants >= 0.65.1 (>= 0.69.5 with libclang >= 19.1) |
| libclang | 20.1.8 (`/usr/lib/llvm-20`, loaded by bindgen at run time) | the same as the C compiler |

The recipe is in [build-container.md](build-container.md) ("Rust for the kernel"); `make ARCH=arm64 LLVM=1
rustavailable` in a kernel tree says `Rust is available!`.

## The fragment

`mainline/patches/kernel/board/rust.config` is one line, `CONFIG_RUST=y`. The HY320/HY200 defconfig already meets the
other conditions of `config RUST` (no MODVERSIONS, RANDSTRUCT, DEBUG_INFO_BTF, CFI, KASAN; LTO none). Built with
`BOARD=hy320 KERNEL_CONFIG=rust build.sh kernel` (one fresh tree, about four minutes on 24 threads), the `.config`
differs from the release tree's only in the Rust lines:

```
CONFIG_RUSTC_VERSION=108900
CONFIG_RUST_IS_AVAILABLE=y
CONFIG_RUSTC_LLVM_VERSION=200107
CONFIG_RUST=y
CONFIG_RUSTC_VERSION_TEXT="rustc 1.89.0 (29483883e 2025-08-04)"
CONFIG_BINDGEN_VERSION_TEXT="bindgen 0.72.1"
CONFIG_RUST_OVERFLOW_CHECKS=y
```

(plus the derived `CONFIG_RUSTC_HAS_*`, `CONFIG_RUSTC_SUPPORTS_ARM64`, `CONFIG_HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC`).
The compressed Image grows from 7.60 to 7.79 MB (the `kernel` crate and `core`). It is a developer fragment, not part of
an image.

## How a C module calls Rust: one module, both objects

The pattern: **a composite module whose objects are C and Rust** (option b below). kbuild has a `%.o: %.rs` rule next to
`%.o: %.c`, so a `.rs` file named in `<module>-y` is compiled into an object and linked into the module like any other:

```make
obj-m := h713_rshim_demo.o
h713_rshim_demo-y := rshim_demo_main.o rshim_demo_hw.o     # .c and .rs
```

- The C object owns the module: `module_init`/`module_exit` (or the platform driver and the DRM device),
  `MODULE_LICENSE("GPL")` - the `kernel` crate's symbols are GPL-only exports.
- The Rust object is not a Rust module: no `module!`. It is a crate root (`rshim_demo_hw.rs`, crate name = object name)
  compiled `no_std` against `core` and the `kernel` crate, and its interface is `#[no_mangle] pub extern "C" fn`, declared
  for C in a header (`rshim_demo.h`). Nothing checks the two declarations against each other; a change goes into both.
- Pointers cross as raw pointers: the C side's `void __iomem *` is `*const c_void` in Rust, and the Rust side uses the
  kernel's accessors on it (`kernel::bindings::readl`, which is the exported `rust_helper_readl`; for a region with a size,
  `kernel::io::IoRaw` + `Io::from_raw` give bounds-checked `try_read32`/`try_write32`). The C side maps, the Rust side
  only touches what it is handed.
- One Rust crate root per module is the rule. Two `.rs` objects in one module do link (tried), but they are two crates
  that can only reach each other through `extern "C"`. Everything else in Rust becomes `mod` submodules of the one root.

On the HY320 (test kernel 6.18.38 with `rust.config`, module built out of tree with `mainline/tools/rshim-demo/Makefile`):

```
# uname -v; grep -c rust_helper_readl /proc/kallsyms
#1 SMP Tue Nov  3 06:13:30 UTC 2026
2
# insmod /data/rshim/h713_rshim_demo.ko; rmmod h713_rshim_demo; dmesg | grep h713_rshim_demo
[   19.278933] h713_rshim_demo: demo_add(40, 2) = 42, demo_add(0xffffffff, 2) = 1 (Rust)
[   19.286828] h713_rshim_demo: 0x03000024: demo_readl = 0x00000101 (Rust), readl = 0x00000101 (C)
[   19.295563] h713_rshim_demo: C -> Rust calls ok
[   19.325058] h713_rshim_demo: unloaded
```

The register is the system-control word `0x03000024`, mapped by C, read once through Rust and once by C itself.

### What was rejected, and why

- **(a) A Rust module exporting `extern "C"` functions to a separate C module.** Fails at build time: Rust in 6.18 has no
  way to export a symbol from a loadable module. `module!` makes no `__ksymtab`/`.export_symbol` entries, and
  `EXPORT_SYMBOL` is a C macro (the `kernel` crate's own exports come from `rust/exports.c`, which a module cannot use).
  A Rust module `rshim_a_rs` with `#[no_mangle] pub extern "C" fn demo_add` and a C module calling it end in
  `ERROR: modpost: "demo_add" [rshim_a_c.ko] undefined!`. Making it work would mean a C file with `EXPORT_SYMBOL_GPL`
  inside the Rust module - which is option (b) plus a module boundary the driver does not need.
- **(c) Rust built into the kernel (`obj-y`) with a C ABI.** Would work for built-in C callers; a C module would again
  need an `EXPORT_SYMBOL` from a C file next to it. Rejected: the hardware layer would sit in the Image, so every change
  to it is a new kernel and a reboot instead of `rmmod`/`insmod`, and it would be in every kernel whether the display
  driver is loaded or not.

## Limits of the Rust side

- **Panics are `BUG()`.** The kernel's panic handler (`rust/kernel/lib.rs`) prints the message and calls `BUG()`: in
  module code that is an oops that kills the calling thread and leaves the module stuck, not an error return. There is
  no unwinding (`-Cpanic=abort`), so nothing to catch at the `extern "C"` boundary. `CONFIG_RUST_OVERFLOW_CHECKS=y`
  turns integer overflow into such a panic (`a + b` became a call to `core::panicking::panic_const_add_overflow` in a
  test build). The hardware layer therefore says what it means - `wrapping_add`, `checked_*`, `get()` instead of `[i]`
  - and returns errors as `Result` inside Rust and as `-errno` (`Error::to_errno()`) across the C ABI. No `unwrap`.
- **`build_assert!`** (e.g. `Io::read32` with a constant offset) must be provable at compile time; otherwise the module
  fails to link with `rust_build_error`. Runtime offsets use the `try_*` accessors.
- **Same compiler as the kernel.** Rust symbols carry a hash of the crate (`_RNvNtNtCs1h9PaebWwla_4core...`), so a
  module only links against a kernel built by the same rustc, from the same tree. Build modules against the tree that
  built the running kernel, as for C modules.
- **No floats.** The arm64 kernel target is `aarch64-unknown-none-softfloat`; an `f32` multiplication ends in
  `ERROR: modpost: "__mulsf3" [tx.ko] undefined!` (and `__floatunsisf`, `__fixunssfsi`, ... - tried). Fixed point only.

## Reusing a no_std crate in the hardware layer

An existing `no_std`, alloc-free crate (register maps, sequence tables, pure computations) is compiled as part of the
module's one Rust crate, file by file, with `#[path]`:

```rust
#[allow(unreachable_pub)]          // its `pub` items are crate-private here; the kernel builds with -Wunreachable_pub
#[path = "common/demo_calc.rs"]
mod demo_calc;
```

`rshim_demo_hw.rs` does exactly this with `common/demo_calc.rs`, which the host tests on its own
(`rustc --edition 2021 --test common/demo_calc.rs`). Include the crate's module files, not its `lib.rs`: crate-level
attributes (`#![no_std]`, `#![deny(...)]`) are only allowed in a crate root. Paths inside the reused files change
accordingly (`crate::` now means the module's crate - prefer `super::`-relative paths in shared code). Unused items
need `#[allow(dead_code)]` at the `mod` line, or the build warns.

What such a crate must not use:

- `std` (it does not exist: the kernel builds with `--sysroot=/dev/null` and adds `no_std` to every crate) and `alloc`
  (`extern crate alloc` -> `error[E0463]: can't find crate for alloc`, tried). Allocation in the hardware layer is the
  `kernel` crate's (`KBox`, `KVec` with GFP flags), never in shared code.
- other crates from crates.io: kbuild passes only `--extern kernel` and `--extern pin_init`. A dependency has to be
  pulled in as source the same way, file by file.
- floats, panicking operations (above), `core::fmt` in hot paths (it is large), recursion with unbounded depth (the
  kernel stack is 16 KB), unstable features outside kbuild's allow-list (`rust_allowed_features` in
  `scripts/Makefile.build`), edition 2024 syntax (modules build with `--edition=2021`).
- static mutable state shared with C without a lock: the C side owns locking; Rust gets a `&mut` or a lock from C.

## Build and load

```bash
podman exec h713-build sh -c 'cd /work && BOARD=hy320 KERNEL_CONFIG=rust mainline/build/build.sh kernel'
podman exec h713-build make -C /work/mainline/tools/rshim-demo KDIR=/work/mainline/build/linux-6.18.38-<hash of the rust tree>
```

The kernel and module tree of the rust build (`build/out/h713-kernel-rust.fit`, `build/modroot.<hash>`) replace the
release ones on the device for the test - all in-tree modules, because they come from another build, and the aic8800
modules built against the same tree - then `insmod h713_rshim_demo.ko`. Back to the release kernel and its modules
afterwards.
