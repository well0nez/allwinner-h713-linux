# Toolchain

The whole stack builds with **LLVM (clang / ld.lld)** — no aarch64 GCC is
required for BL31, U-Boot, or the arm64 kernel. Host is Arch/CachyOS.

## Pinned host tools

| Tool | Version verified | Provides | Notes |
|------|------------------|----------|-------|
| clang | 22.1.8 | C compiler + integrated assembler | `-target aarch64-linux-gnu` for U-Boot |
| ld.lld | 22.1.8 | linker | needs the `.bss` lds fix (see bringup-notes) |
| llvm (llvm-* binutils) | 22.1.8 | ar/nm/objcopy/objdump/readelf/strip | passed as `LLVM=1` to the kernel |
| dtc | 1.8.1 | device-tree compiler | system dtc is only a fallback |
| swig | 4.4.1 | **required** | U-Boot builds its own dtc + pylibfdt; pylibfdt needs swig |
| python libfdt | importable | binman | comes with `python-libfdt` |
| mmdebstrap | 1.5.7 | arm64 Debian rootfs | used with a private rootless QEMU binfmt namespace |

These are the versions this project has been built and hardware-verified with.
Newer LLVM should work; the pins record a known-good set, not a hard floor.

## Non-obvious flags (each cost real debugging time — see docs/build.md)

- **`-fintegrated-as`** (U-Boot `KAFLAGS` *and* `KCFLAGS`) — without it clang
  shells out to the x86 `/usr/bin/as` for `.S` files and fails on `-EL`.
- **No `DTC=` override, no `NO_PYTHON=1`** for U-Boot — with swig present it
  builds its own dtc (knows the `graph_child_address` check) and pylibfdt
  (binman needs it).
- TF-A / kernel take plain `CC=clang` / `LLVM=1`; only U-Boot needs the target
  triple and the integrated-as flags.

## Install (Arch/CachyOS)

```
sudo pacman -S clang lld llvm dtc python-libfdt swig
# mmdebstrap from the AUR (rootfs only)
sudo pacman -S apt qemu-user-static-binfmt e2fsprogs kmod android-tools curl libarchive openssh
```

`debian-archive-keyring` is optional on the host. If absent, the rootfs builder
downloads its Arch package, verifies the package signature, and extracts the
bootstrap trust anchor into the ignored build cache.
