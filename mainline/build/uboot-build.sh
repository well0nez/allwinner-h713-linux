#!/usr/bin/env bash
# Quick single-defconfig U-Boot build helper (clang/lld).
# For the full BL31 -> U-Boot -> kernel -> images flow use build/build.sh.
#
# Usage: build/uboot-build.sh <O-dir> <defconfig> [make-target...]
# Needs: swig (in-tree dtc + pylibfdt). -fintegrated-as = clang's assembler.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
O="$1"; DEF="$2"; shift 2
UBOOT="$ROOT/external/u-boot"
BL31="$ROOT/build/out/bl31.bin"
[ -f "$BL31" ] || { echo "missing $BL31 — run: build/build.sh bl31" >&2; exit 1; }
F=(ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu'
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump
  READELF=llvm-readelf STRIP=llvm-strip
  KAFLAGS=-fintegrated-as
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector'
  BL31="$BL31")
make -C "$UBOOT" O="$O" "${F[@]}" "$DEF" >/dev/null 2>&1 || { echo DEFCONFIG_FAIL; exit 1; }
make -C "$UBOOT" O="$O" "${F[@]}" -j"$(nproc)" "$@"
