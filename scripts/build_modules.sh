#!/bin/bash
# HY310 Out-of-Tree Module Build Script
# Builds all out-of-tree modules against a configured kernel tree.
#
# Prerequisites: Kernel tree must be configured + zImage built
#   (run build_kernel_arm32.sh or manually: make hy310_defconfig && make zImage)
#
# Build order matters — dependencies are resolved sequentially:
#   1. TVTOP (display bus fabric — no deps)
#   2. DECD (video decoder — no deps)
#   3. CPU_COMM (ARM↔MIPS IPC — no deps)
#   4. Audio codec/cpudai/machine (flat directory)
#   5. Audio bridge (TridentALSA)
#   6. GE2D display (legacy, needs Module.symvers)
#   7. WiFi AIC8800 (bsp + fdrv + btlpm)
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
    echo "ERROR: Kernel not configured. Run build_kernel_arm32.sh first."
    exit 1
fi

echo "=== HY310 Out-of-Tree Module Build ==="
echo "Kernel: $KERNEL_SRC"
echo ""

# Step 1: TVTOP (display bus fabric)
echo "--- [1/7] TVTOP display module ---"
$MAKE M="$REPO_DIR/drivers/tvtop" modules
echo ""

# Step 2: DECD (video decoder)
echo "--- [2/7] DECD video decoder module ---"
$MAKE M="$REPO_DIR/drivers/decd" modules
echo ""

# Step 3: CPU_COMM (ARM↔MIPS IPC)
echo "--- [3/7] CPU_COMM IPC module ---"
$MAKE M="$REPO_DIR/drivers/cpu_comm" modules
echo ""

# Step 4: Audio (codec + cpudai + machine)
echo "--- [4/7] Audio modules (codec, cpudai, machine) ---"
$MAKE M="$REPO_DIR/drivers/audio" modules
echo ""

# Step 5: Audio bridge
echo "--- [5/7] Audio bridge module ---"
$MAKE M="$REPO_DIR/drivers/audio/bridge" modules
echo ""

# Step 6: GE2D display (legacy)
echo "--- [6/7] GE2D display module ---"
$MAKE M="$REPO_DIR/drivers/display/ge2d" modules
echo ""

# Step 7: WiFi AIC8800
echo "--- [7/7] WiFi AIC8800 modules (bsp + fdrv + btlpm) ---"
$MAKE M="$REPO_DIR/drivers/wifi" modules
echo ""

# Summary
echo "=== Build Summary ==="
echo "Out-of-tree modules:"
find "$REPO_DIR/drivers" -name '*.ko' -not -path '*/Archived/*' | while read ko; do
  echo "  $(basename $ko)"
done
echo ""
echo "Next: ./scripts/install_modules.sh [STAGING_DIR]"
