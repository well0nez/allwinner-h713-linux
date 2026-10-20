# The toolchain

The whole boot chain and the kernel build with **LLVM**: clang, ld.lld and the llvm binutils. There is no aarch64
GCC for BL31, U-Boot or the kernel. Everything is built inside the container `h713-build`; how to set it up, its
package list and the LLVM 20 step are in [docs/build-container.md](../../docs/build-container.md). crust, the
ARISC firmware, needs an `or1k-elf` GCC, which `mainline/tools/or1k-toolchain/build-or1k-toolchain.sh` builds once
and keeps (described there as well).

## A known good set

Measured in the container on 20.10.2026 (`podman exec h713-build ...`):

| Tool | Version |
|---|---|
| system | Ubuntu 24.04.4 LTS |
| clang, ld.lld, llvm-* | 20.1.8 (apt.llvm.org; `/usr/local/bin` points to `/usr/lib/llvm-20/bin`) |
| dtc | 1.7.0 |
| swig | 4.2.0 - required: U-Boot builds its own dtc and pylibfdt with it, and binman needs pylibfdt |
| Python | 3.12.3 (no system libfdt module, and none is needed: U-Boot builds its own) |
| GNU make, patch, tar, gzip, xz | 4.3, 2.7.6, 1.35, 1.12, 5.4.5 |
| git, curl, bash, gcc (host helpers) | 2.43.0, 8.5.0, 5.2.21, 13.3.0 |
| mmdebstrap | 1.4.3 (the rootfs) |
| mkimage of the system | 2025.10 - a fallback only; the FIT is made with the mkimage of the U-Boot build |

LLVM older than 19 is not enough: its `llvm-objcopy` cannot write SREC ([docs/build-container.md](../../docs/build-container.md)).
Newer versions should work. The table is a set that is known to work, not a lower bound.

## Switches that are not obvious

- U-Boot needs `-fintegrated-as` in `KAFLAGS` **and** in `KCFLAGS` (else clang hands `.S` files to the x86 `as`,
  which fails on `-EL`), and `CC` with the target triple `aarch64-linux-gnu`.
- U-Boot gets **no** `DTC=` and **no** `NO_PYTHON=1`: with swig it builds its own dtc, which knows the
  `graph_child_address` check, and the pylibfdt binman needs.
- TF-A takes plain `CC=clang`, the kernel `LLVM=1`.

The Debian keyring for the rootfs is no part of the toolchain: `release/build-all.sh` fetches it itself in step 5,
pinned by sha256.
