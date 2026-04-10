#!/bin/bash
# HY310 Module Install Script
# Installs all kernel modules into a staging directory ready for rootfs
#
# Usage: ./install_modules.sh [KERNEL_SRC_DIR] [STAGING_DIR]
#   STAGING_DIR defaults to ./staging/
#
# Author: well0nez
# SPDX-License-Identifier: GPL-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
KERNEL_SRC="${1:-$(dirname "$REPO_DIR")/linux-6.16.7-build}"
STAGING="${2:-$REPO_DIR/staging}"
CROSS_COMPILE="${CROSS_COMPILE:-arm-linux-gnueabi-}"

echo "=== Installing modules to $STAGING ==="

# In-tree modules
make -C "$KERNEL_SRC" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE"     INSTALL_MOD_PATH="$STAGING" modules_install

# Out-of-tree modules: find all .ko and install
KVER=$(make -C "$KERNEL_SRC" -s kernelversion)
EXTRA_DIR="$STAGING/lib/modules/$KVER/extra"
mkdir -p "$EXTRA_DIR"

for ko in $(find "$REPO_DIR/drivers" -name '*.ko' 2>/dev/null); do
    cp "$ko" "$EXTRA_DIR/"
    echo "  Installed: $(basename $ko)"
done

# Regenerate module dependencies
depmod -a -b "$STAGING" "$KVER" 2>/dev/null || true

echo ""
echo "=== Modules installed ==="
echo "Staging root: $STAGING"
echo "Module dir:   $STAGING/lib/modules/$KVER/"
echo ""
echo "Copy to rootfs: cp -a $STAGING/lib/modules/$KVER /path/to/rootfs/lib/modules/"
