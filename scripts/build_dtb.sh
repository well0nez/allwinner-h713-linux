#!/bin/bash
# HY310 Device Tree Build Script
# Compiles the standalone DTS using the kernel tree's dtc and include paths
#
# Usage: ./build_dtb.sh [KERNEL_SRC_DIR] [OUTPUT_DIR]
#
# Author: well0nez
# SPDX-License-Identifier: GPL-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
KERNEL_SRC="${1:-$(dirname "$REPO_DIR")/linux-6.16.7}"
OUTPUT_DIR="${2:-$REPO_DIR/output}"

DTS_FILE="$REPO_DIR/dts/sun50i-h713-hy310.dts"
DTB_FILE="$OUTPUT_DIR/sun50i-h713-hy310.dtb"

if [ ! -f "$KERNEL_SRC/scripts/dtc/dtc" ]; then
    echo "ERROR: dtc not found. Build kernel first or point to kernel source."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "=== Building HY310 DTB ==="
echo "DTS: $DTS_FILE"
echo "DTB: $DTB_FILE"

# Preprocess with cpp (resolve #include directives)
cpp -nostdinc     -I "$KERNEL_SRC/include"     -I "$KERNEL_SRC/scripts/dtc/include-prefixes"     -I "$REPO_DIR/dt-bindings"     -undef -x assembler-with-cpp     "$DTS_FILE" | "$KERNEL_SRC/scripts/dtc/dtc" -I dts -O dtb     -o "$DTB_FILE" -

echo "DTB written: $DTB_FILE ($(stat -c%s "$DTB_FILE") bytes)"
echo "SHA256: $(sha256sum "$DTB_FILE" | cut -d' ' -f1)"
