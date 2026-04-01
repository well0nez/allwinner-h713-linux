#!/bin/bash
# HY310 Module Build Script
# Builds all kernel modules (in-tree + out-of-tree)
#
# Prerequisites: build_kernel.sh must have been run first (kernel configured + zImage built)
#
# Build order matters:
#   1. In-tree modules (includes tvtop, decd, cpu_comm, board-mgr, motor, etc.)
#   2. Out-of-tree audio modules (codec, cpudai, machine — flat Makefile)
#   3. Out-of-tree audio bridge
#   4. Out-of-tree GE2D display (needs in-tree Module.symvers for tvtop symbols)
#   5. Out-of-tree WiFi AIC8800 (bsp + fdrv + btlpm)
#
# Author: well0nez
# SPDX-License-Identifier: GPL-2.0

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
KERNEL_SRC=${1:-$(dirname "$REPO_DIR")/linux-6.16.7}
CROSS_COMPILE=${CROSS_COMPILE:-arm-linux-gnueabi-}
JOBS=${JOBS:-$(nproc)}
MAKE="make -C $KERNEL_SRC ARCH=arm CROSS_COMPILE=$CROSS_COMPILE -j$JOBS"

if [ ! -f "$KERNEL_SRC/.config" ]; then
    echo "ERROR: Kernel not configured. Run build_kernel.sh first."
    exit 1
fi

echo "=== HY310 Module Build ==="
echo "Kernel: $KERNEL_SRC"
echo ""

# Step 1: In-tree modules
echo "--- [1/5] In-tree modules ---"
$MAKE modules
echo ""

# Step 2: Out-of-tree audio (codec + cpudai + machine in one flat directory)
echo "--- [2/5] Audio modules (codec, cpudai, machine) ---"
$MAKE M="$REPO_DIR/drivers/audio" modules
echo ""

# Step 3: Out-of-tree audio bridge
echo "--- [3/5] Audio bridge module ---"
$MAKE M="$REPO_DIR/drivers/audio/bridge" modules
echo ""

# Step 4: Out-of-tree GE2D display
echo "--- [4/5] GE2D display module ---"
$MAKE M="$REPO_DIR/drivers/display/ge2d" modules
echo ""

# Step 5: Out-of-tree WiFi AIC8800
echo "--- [5/5] WiFi AIC8800 modules (bsp + fdrv + btlpm) ---"
$MAKE M="$REPO_DIR/drivers/wifi" modules
echo ""

# Summary
echo "=== Build Summary ==="
echo "In-tree modules:"
find "$KERNEL_SRC" -path '*/drivers/*.ko' -newer "$KERNEL_SRC/.config" | wc -l
echo "Out-of-tree modules:"
find "$REPO_DIR/drivers" -name '*.ko' | while read ko; do echo "  $(basename $ko)"; done
echo ""
echo "Next: ./scripts/install_modules.sh [STAGING_DIR]"
