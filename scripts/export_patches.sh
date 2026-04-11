#!/bin/bash
# HY310 Patch Export Script
# Generates patches from the modified kernel tree by diffing against vanilla.
# Run this after making changes to the kernel tree to update the repo patches.
#
# Usage: ./export_patches.sh [KERNEL_SRC] [VANILLA_SRC]
#   KERNEL_SRC:  Modified kernel tree (default: $HY310_ROOT/kernels/working)
#   VANILLA_SRC: Vanilla kernel tree (default: $HY310_ROOT/kernels/vanilla)
#
# Workflow:
#   1. Edit code in the kernel tree as usual
#   2. Build, flash, test on HY310
#   3. When it works: run this script to update patches
#   4. git add/commit/push in hy310-linux repo
#
# Author: well0nez
# SPDX-License-Identifier: GPL-2.0

set -e

HY310_ROOT="${HY310_ROOT:-/opt/hy310}"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
M=${1:-"$HY310_ROOT/kernels/working"}
V=${2:-"$HY310_ROOT/kernels/vanilla"}
P=$REPO_DIR/patches

if [ ! -d "$V" ]; then
    echo "ERROR: Vanilla kernel not found at $V"
    echo "Extract it: tar xf linux-6.16.7.tar.xz -C linux-6.16.7-vanilla --strip-components=1"
    exit 1
fi

EXCLUDE="--exclude=*.o --exclude=*.ko --exclude=*.cmd --exclude=*.mod* --exclude=*.order --exclude=*.symvers --exclude=.config* --exclude=*.dtb --exclude=built-in* --exclude=*.a --exclude=.tmp* --exclude=*.bak* --exclude=source"

echo "=== HY310 Patch Export ==="
echo "Modified: $M"
echo "Vanilla:  $V"
echo "Output:   $P"
echo ""

gen_patch() {
    local name=$1; shift
    local patchfile="$P/$name"
    > "$patchfile"
    for path in "$@"; do
        diff -ruN $EXCLUDE "$V/$path" "$M/$path" 2>/dev/null \
            | sed "s@${V}/@a/@g" | sed "s@${M}/@b/@g" \
            >> "$patchfile" || true
    done
    local lines=$(wc -l < "$patchfile")
    if [ "$lines" -eq 0 ]; then
        echo "  SKIP (no changes): $name"
        rm -f "$patchfile"
        return 1
    fi
    echo "  OK ($lines lines): $name"
    return 0
}

echo "Generating patches..."

gen_patch "0001-clk-sunxi-ng-add-h713-ccu-driver.patch" \
    "drivers/clk/sunxi-ng/ccu-sun50i-h713.c" \
    "drivers/clk/sunxi-ng/ccu-sun50i-h713.h" \
    "drivers/clk/sunxi-ng/Kconfig" \
    "drivers/clk/sunxi-ng/Makefile"

gen_patch "0002-pinctrl-sunxi-add-h713-pio-driver.patch" \
    "drivers/pinctrl/sunxi/pinctrl-sun50i-h713.c" \
    "drivers/pinctrl/sunxi/Kconfig" \
    "drivers/pinctrl/sunxi/Makefile"

gen_patch "0003-pinctrl-sunxi-add-h713-r-pio-driver.patch" \
    "drivers/pinctrl/sunxi/pinctrl-sun50i-h713-r.c"

gen_patch "0004-pinctrl-sunxi-fix-irq-mux-and-graceful-resource.patch" \
    "drivers/pinctrl/sunxi/pinctrl-sunxi.c"

gen_patch "0005-phy-sun4i-usb-add-h713-pmu-bit0-quirk.patch" \
    "drivers/phy/allwinner/phy-sun4i-usb.c"

gen_patch "0006-mmc-sunxi-add-h713-v5p3x-support.patch" \
    "drivers/mmc/host/sunxi-mmc.c"

gen_patch "0007-pwm-add-sun8i-8channel-driver.patch" \
    "drivers/pwm/pwm-sun8i.c" \
    "drivers/pwm/Kconfig" \
    "drivers/pwm/Makefile"

gen_patch "0008-misc-add-hy310-board-mgr.patch" \
    "drivers/misc/hy310-board-mgr.c"

gen_patch "0009-misc-add-hy310-keystone-motor.patch" \
    "drivers/misc/hy310-keystone-motor.c"

gen_patch "0010-misc-add-sunxi-mipsloader.patch" \
    "drivers/misc/sunxi-mipsloader.c"

gen_patch "0011-misc-add-sunxi-nsi.patch" \
    "drivers/misc/sunxi-nsi.c"

# NOTE: TVTOP, DECD, CPU_COMM are now out-of-tree modules (drivers/ in repo)
# They are no longer generated as patches.

gen_patch "0015-misc-add-h713-driver-kconfig.patch" \
    "drivers/misc/Kconfig" \
    "drivers/misc/Makefile"

gen_patch "0016-dt-bindings-add-h713-clock-reset-ids.patch"     "include/dt-bindings/clock/sun50i-h713-ccu.h"     "include/dt-bindings/reset/sun50i-h713-ccu.h"

gen_patch "0017-iommu-sun50i-decouple-arm-dma-use-iommu.patch"     "drivers/iommu/Kconfig"

gen_patch 0018-pinctrl-sunxi-add-h713-pb-bank-to-h616.patch     drivers/pinctrl/sunxi/pinctrl-sun50i-h616.c

gen_patch 0019-iio-adc-add-h713-lradc-driver.patch     drivers/iio/adc/sun50i-h713-lradc-iio.c     drivers/iio/adc/Kconfig     drivers/iio/adc/Makefile

gen_patch 0020-pmdomain-add-h713-ppu-driver.patch     drivers/pmdomain/sunxi/sun50i-h713-ppu.c     drivers/pmdomain/sunxi/Kconfig     drivers/pmdomain/sunxi/Makefile

gen_patch "0021-media-sunxi-cir-add-h713-vendor-init.patch"     "drivers/media/rc/sunxi-cir.c"

gen_patch "0022-staging-cedrus-add-h713-ve3-clock-reset.patch"     "drivers/staging/media/sunxi/cedrus/cedrus.h"     "drivers/staging/media/sunxi/cedrus/cedrus_hw.c"

# Also sync DTS if it exists in kernel tree
echo ""
if [ -f "$M/arch/arm64/boot/dts/allwinner/sun50i-h713-hy310.dts" ]; then
    cp "$M/arch/arm64/boot/dts/allwinner/sun50i-h713-hy310.dts" "$REPO_DIR/dts/"
    echo "DTS synced from kernel tree"
fi

# Sync dt-bindings
cp "$M/include/dt-bindings/clock/sun50i-h713-ccu.h" "$REPO_DIR/dt-bindings/clock/" 2>/dev/null && echo "dt-bindings/clock synced"
cp "$M/include/dt-bindings/reset/sun50i-h713-ccu.h" "$REPO_DIR/dt-bindings/reset/" 2>/dev/null && echo "dt-bindings/reset synced"

# Export defconfig
if [ -f "$M/.config" ]; then
    make -C "$M" ARCH=arm savedefconfig 2>/dev/null
    cp "$M/defconfig" "$REPO_DIR/config/hy310_defconfig"
    echo "Defconfig exported ($(wc -l < "$REPO_DIR/config/hy310_defconfig") lines)"
fi

echo ""
echo "=== Export complete ==="
echo ""
echo "Next:"
echo "  cd $REPO_DIR"
echo "  git diff --stat"
echo "  git add -A && git commit -m 'Update patches: <what changed>'"
echo "  git push"
