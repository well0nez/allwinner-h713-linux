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

## CONFIG_RUST in the release kernel

Since 05.11.2026 (7.3.1) the image's defconfig, `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig`, has
`CONFIG_RUST=y` itself, for the clean display driver `h713_drm` (`CONFIG_DRM_H713=m`, kernel `0356`-`0359`,
[display stacks](subsystems/display-stacks.md)). The defconfig meets the other conditions of `config RUST` (no
MODVERSIONS, RANDSTRUCT, DEBUG_INFO_BTF, CFI, KASAN; LTO none). Against the 7.3.1 release tree before it, the `.config`
differs only in the Rust lines and the two `DRM_H713` ones:

```
CONFIG_RUSTC_VERSION=108900
CONFIG_RUST_IS_AVAILABLE=y
CONFIG_RUSTC_LLVM_VERSION=200107
CONFIG_RUST=y
CONFIG_RUSTC_VERSION_TEXT="rustc 1.89.0 (29483883e 2025-08-04)"
CONFIG_BINDGEN_VERSION_TEXT="bindgen 0.72.1"
CONFIG_RUST_OVERFLOW_CHECKS=y
CONFIG_DRM_H713=m
CONFIG_DRM_H713_BENCH=y
```

(plus the derived `CONFIG_RUSTC_HAS_*`, `CONFIG_RUSTC_SUPPORTS_ARM64`, `CONFIG_HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC`).
The compressed Image grows from 7 848 526 to 8 055 416 bytes (the `kernel` crate and `core`), the module set by
`h713_drm.ko` alone. Every release build therefore needs the container's Rust toolchain.

*Superseded 05.11.2026:* CONFIG_RUST came from a developer fragment, `board/rust.config` (`KERNEL_CONFIG=rust`, one line
`CONFIG_RUST=y`, "not part of an image"); on 6.18.38 it grew the Image from 7.60 to 7.79 MB. The release has the line
now, so the fragment changed nothing any more and was removed.

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

On the HY320 (test kernel 6.18.38 with the former `rust.config`, module built out of tree with `mainline/tools/rshim-demo/Makefile`):

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
podman exec h713-build sh -c 'cd /work && BOARD=hy320 mainline/build/build.sh kernel'
podman exec h713-build make -C /work/mainline/tools/rshim-demo KDIR=/work/mainline/build/linux-7.3.1-<hash of the tree>
```

The release tree has `CONFIG_RUST`, so a module with a Rust part builds against it and loads into the release kernel
(`vermagic: 7.3.1 SMP preempt mod_unload aarch64`); `h713_drm` is built in that tree itself. Until 05.11.2026 this took
`KERNEL_CONFIG=rust`, a tree of the release's name whose kernel and modules could only *replace* the release ones (that
is how the demo above was loaded on 6.18.38: `/boot/h713-kernel.fit` and `/lib/modules/6.18.38` swapped, then swapped
back).

## A Rust kernel next to the release

`board/rustbench.config` is `CONFIG_RUST=y` plus `CONFIG_LOCALVERSION="-rust"`: the kernel calls itself `<version>-rust`
(`6.18.38-rust`, on 7.3.1 `7.3.1-rust`), its modules live in `/lib/modules/<version>-rust`, and a module built against
its tree says `vermagic: <version>-rust` and is refused by the release kernel (and the other way round). Apart from that
line its `.config` equals the release tree's. On the HY320 it sits next to the release kernel; the normal boot (`bootcmd`, `/boot/h713-kernel.fit`,
`/lib/modules/6.18.38`) is untouched.

Build (the aic8800 Wi-Fi modules in a copy of their tree, so that `build/out/modules/` keeps the release builds):

```bash
podman exec h713-build sh -c 'cd /work && BOARD=hy320 KERNEL_CONFIG=rustbench mainline/build/build.sh kernel'
# -> build/out/h713-kernel-rustbench.fit, build/modroot.<hash>/lib/modules/6.18.38-rust
cp -a mainline/build/aic8800-<commit>-<hash>/. mainline/build/aic8800-rustbench/
podman exec h713-build bash -c 'K=/work/mainline/build/linux-6.18.38-<rustbench hash>; W=/work/mainline/build/aic8800-rustbench
  km="make -C $K ARCH=arm64 LLVM=1 CONFIG_PLATFORM_MAINLINE_SUNXI=y"
  $km M=$W/aic8800_bsp clean modules
  $km M=$W/aic8800_fdrv KBUILD_EXTRA_SYMBOLS=$W/aic8800_bsp/Module.symvers clean modules'
```

On the device: the FIT as `/boot/h713-kernel-rust.fit`; `modroot.<hash>/lib/modules/6.18.38-rust` as
`/lib/modules/6.18.38-rust`, with `aic8800_bsp.ko` and `aic8800_fdrv.ko` in its `extra/` (as in the release tree),
then `depmod -a 6.18.38-rust`.

**One-shot boot.** The environment has a `boot_rust` next to `boot_emmc`:

```
boot_rust=setenv h713_boot emmc; saveenv; wdt dev watchdog@2051000; wdt start 16000; if ext4load mmc 1:5 0x60000000 h713-kernel-rust.fit; then setenv bootargs "${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw ${h713_display_args}"; bootm 0x60000000; fi
```

`bootcmd` runs `boot_${h713_boot}`, so `fw_setenv h713_boot rust` + `reboot` boots the `-rust` FIT once. `boot_rust`
puts `h713_boot` back to `emmc` and saves it *before* it loads anything, so every later boot - a `reboot`, a watchdog
reset, a hang - is the normal one again. The watchdog (16 s, as in the bench boot of `doku/231`) covers a hang between
U-Boot and the kernel's watchdog driver; systemd keeps it fed after that. Afterwards remove what `saveenv` wrote
besides `h713_boot` (runtime variables): `fw_setenv fdtcontroladdr`, `fw_setenv mmc_bootdev`, `fw_setenv serial#`, and
`fdtfile` back to its old value (`allwinner/allwinner/sun50i-h713-hy320.dtb` on the HY320). A bench boot that needs
the Rust kernel loads `h713-kernel-rust.fit` instead of `h713-kernel.fit` in its own load line.

With the display-stack switch (U-Boot `h713_display`, [display stacks](subsystems/display-stacks.md)) a boot path ends
its `bootargs` with `${h713_display_args}`, as above, or a clean boot gets the clean stack's U-Boot half and the
vendor's kernel half. A `boot_rust` set before the switch existed lacks it, and `h713-display set clean` refuses it.
The clean stack's one-shot into 7.3.1-rustbench, `boot_rust73`, is in that page's device test.

Tested on the HY320 (03.11.2026): one-shot boot -> `uname -r` `6.18.38-rust`, `h713_boot=emmc` again, aic8800 loaded,
`wlan0` up as the access point (192.168.4.1), no failed units; the next reboot came up on the release kernel
(`6.18.38`, FIT `c5b9719a`), `h713-tv ctl status` ok, environment equal to before plus `boot_rust`.

## 7.3.1: the bench kernel `7.3.1-rustbench`

On 7.3.1 the device carries three kernels: the default 7.3.1 (`boot_emmc`), the kernel lane's own `7.3.1-rust`
(`rustbench.config`), and the display lane's bench kernel. So that the bench never shares a module directory with the
kernel lane, `board/rustbench73.config` is `CONFIG_RUST=y` plus `CONFIG_LOCALVERSION="-rustbench"`: kernel release
`7.3.1-rustbench`, FIT `/boot/h713-kernel-rustbench73.fit`, modules `/lib/modules/7.3.1-rustbench` (in-tree modules and
`extra/aic8800_{bsp,fdrv,btlpm}.ko` with aic8800 0011, the 7.3 `probe_peer` fix - without it the access point answers no
authentication). Apart from that line its `.config` equals the `7.3.1-rust` tree's.

Built from the committed `kernel-7.3` series in a worktree of its own, so that uncommitted work of the kernel lane does
not end up in it; the aic8800 modules in a copy of the aic8800 tree, as for 6.18:

```bash
git worktree add --detach mainline/build/rb73-wt kernel-7.3
mkdir -p mainline/build/rb73-wt/mainline/build/cache && cp <linux-7.3.1.tar.xz> mainline/build/rb73-wt/mainline/build/cache/
podman exec h713-build sh -c 'cd /work/mainline/build/rb73-wt && BOARD=hy320 KERNEL_CONFIG=rustbench73 \
  MKIMAGE=/work/mainline/build/uboot-hy320-check/tools/mkimage mainline/build/build.sh kernel'
# -> out/h713-kernel-rustbench73.fit, modroot.<hash>/lib/modules/7.3.1-rustbench; aic8800 against the same tree
```

One-shot selector, like `boot_rust`:

```
boot_rustbench73=setenv h713_boot emmc; saveenv; wdt dev watchdog@2051000; wdt start 16000; if ext4load mmc 1:5 0x60000000 h713-kernel-rustbench73.fit; then setenv bootargs "${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw"; bootm 0x60000000; fi
```

`fw_setenv h713_boot rustbench73` + `reboot` boots it once; every later boot is the default again. Afterwards put back
what `saveenv` wrote (`fdtcontroladdr`, `mmc_bootdev`, `serial#`, `fdtfile`). A bench boot loads
`h713-kernel-rustbench73.fit` in its own load line; modules for it are built against the `rustbench73` tree and say
`vermagic: 7.3.1-rustbench SMP preempt mod_unload aarch64`.

Tested on the HY320 (03.11.2026, default boot 7.3.1): one-shot boot -> `uname -r` `7.3.1-rustbench`, `h713_boot=emmc`
again, aic8800 loaded, `wlan0` up as the access point (192.168.4.1); the next reboot came up on the default 7.3.1,
`h713-tv ctl status` ok, environment equal to before plus `boot_rustbench73`. `h713_drm.ko` built against the tree says
`vermagic: 7.3.1-rustbench SMP preempt mod_unload aarch64`.

## 7.3.1: the release kernel with Rust (05.11.2026)

The release kernel itself has `CONFIG_RUST` and `h713_drm` (above, "CONFIG_RUST in the release kernel"). On the HY320
it is the normal boot: `/boot/h713-kernel-7.3.fit` (`boot_emmc`), modules `/lib/modules/7.3.1` with `h713_drm.ko` and
`extra/aic8800_{bsp,fdrv,btlpm}.ko`; the 7.3.1 without Rust before it stays as `/boot/h713-kernel-7.3-prev.fit` with the
one-shot

```
boot_73prev=setenv h713_boot emmc; saveenv; wdt dev watchdog@2051000; wdt start 16000; if ext4load mmc 1:5 0x60000000 h713-kernel-7.3-prev.fit; then setenv bootargs "${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw ${h713_display_args}"; bootm 0x60000000; fi
```

and its modules as `/lib/modules/7.3.1.prev`. Both kernels call themselves `7.3.1`, so the previous one reads the new
module tree; for more than a look, swap the two directories as well. Installed with a one-shot boot of the new FIT
first (as `h713-kernel-7.3-next.fit`), then renamed into place. Tested on the HY320 (`doku/229`): boot, Wi-Fi access
point, the module set of before plus nothing loaded (the vendor stack refuses `h713_drm` on its command line), 426
`rust_helper` symbols, and both display stacks on the normal boot. `rustbench73` stays for bench builds of modules the
release does not carry.
