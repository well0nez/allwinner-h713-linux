#!/bin/bash
# HY310 Mainline Kernel Build Script
# Applies patches to vanilla linux-6.16.7 and builds zImage + modules
#
# Usage: ./build_kernel.sh [KERNEL_SRC_DIR]
#   KERNEL_SRC_DIR: path to vanilla linux-6.16.7 source (default: ../linux-6.16.7)
#
# Author: well0nez
# SPDX-License-Identifier: GPL-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
KERNEL_SRC="${1:-$(dirname "$REPO_DIR")/linux-6.16.7}"
CROSS_COMPILE="${CROSS_COMPILE:-arm-linux-gnueabi-}"
JOBS="${JOBS:-$(nproc)}"

if [ ! -f "$KERNEL_SRC/Makefile" ]; then
    echo "ERROR: Kernel source not found at $KERNEL_SRC"
    echo "Usage: $0 [/path/to/linux-6.16.7]"
    exit 1
fi

echo "=== HY310 Kernel Build ==="
echo "Kernel source: $KERNEL_SRC"
echo "Cross compiler: $CROSS_COMPILE"
echo "Jobs: $JOBS"
echo ""

# Step 1: Apply patches (skip already applied)
echo "--- Applying patches ---"
while IFS= read -r patch; do
    [ -z "$patch" ] && continue
    [[ "$patch" == \#* ]] && continue
    patchfile="$REPO_DIR/patches/$patch"
    if [ ! -f "$patchfile" ]; then
        echo "WARNING: Patch not found: $patchfile"
        continue
    fi
    if patch -p1 --dry-run -N -d "$KERNEL_SRC" < "$patchfile" > /dev/null 2>&1; then
        patch -p1 -N -d "$KERNEL_SRC" < "$patchfile"
        echo "  Applied: $patch"
    else
        echo "  Skipped (already applied): $patch"
    fi
done < "$REPO_DIR/patches/series"

# Step 2: Copy defconfig and configure
echo ""
echo "--- Configuring kernel ---"
cp "$REPO_DIR/config/hy310_defconfig" "$KERNEL_SRC/arch/arm/configs/hy310_defconfig"
make -C "$KERNEL_SRC" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" hy310_defconfig
make -C "$KERNEL_SRC" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" olddefconfig

# Step 3: Build
echo ""
echo "--- Building zImage + modules ---"
make -C "$KERNEL_SRC" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" -j"$JOBS" zImage modules

echo ""
echo "=== Build complete ==="
echo "zImage: $KERNEL_SRC/arch/arm/boot/zImage"
echo ""
echo "Next steps:"
echo "  build_h713_dtb_v8.sh           # Compile HY310 DTB (canonical)"
echo "  ./scripts/build_modules.sh  # Build out-of-tree modules"
echo "  ./scripts/repack_boot.py    # Create Android boot v3 image"
