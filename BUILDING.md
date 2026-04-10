# Building the HY310 Mainline Kernel

## Prerequisites

- ARM cross-compiler: `arm-linux-gnueabi-gcc` (Debian: `apt install gcc-arm-linux-gnueabi`)
- Standard kernel build tools: `make`, `bc`, `flex`, `bison`, `libssl-dev`
- Device tree compiler: built automatically with the kernel
- Python 3: for `repack_boot.py`

## Overview

This repo uses a **commit-based workflow** — the kernel source tree already
contains all HY310 changes. You do **not** need to apply patches unless you're
working with a fresh vanilla kernel tree.

### Option A: Build from this repo (recommended)

```bash
cd hy310-linux
# Kernel source already includes all changes — no patch application needed
```

### Option B: Apply patches to a fresh vanilla tree (optional)

If you have a vanilla `linux-6.16.7` tree and want to apply the HY310 patches:

```bash
cd linux-6.16.7
for p in $(cat /path/to/hy310-linux/patches/series); do
    patch -p1 < /path/to/hy310-linux/patches/$p
done
```

Or use the build script: `../hy310-linux/scripts/build_kernel.sh .`

## Step 1: Configure

```bash
cp /path/to/hy310-linux/config/hy310_defconfig arch/arm/configs/
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- hy310_defconfig
```

## Step 2: Build Kernel + In-Tree Modules

```bash
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- -j$(nproc) zImage modules
```

This produces:
- `arch/arm/boot/zImage` — compressed kernel image
- ~20 kernel modules (.ko files)

## Step 3: Build Out-of-Tree Modules

```bash
KDIR=/path/to/linux-6.16.7  # or $HY310_ROOT/kernel/source/linux-6.16.7

# DRM display driver (h713_drm.ko)
make -C $KDIR M=/path/to/hy310-linux/drivers/display/drm ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

# Audio (codec + cpudai + machine)
make -C $KDIR M=/path/to/hy310-linux/drivers/audio ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

# Audio bridge (TridentALSA)
make -C $KDIR M=/path/to/hy310-linux/drivers/audio/bridge ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

# WiFi AIC8800 (bsp + fdrv + btlpm)
make -C $KDIR M=/path/to/hy310-linux/drivers/wifi ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules
```

Or use: `../hy310-linux/scripts/build_modules.sh .`

## Step 4: Build Device Tree

```bash
# Canonical DTB build script (v8):
build_h713_dtb_v8.sh
# Output: output_arm32/sun50i-h713-hy310-v7.dtb
```

> **Note:** `build_h713_dtb_v8.sh` is the only correct DTB build script.
> Legacy scripts (`build_dtb.sh`, `build_h713_dtb_v7.sh`) are deprecated.

## Step 5: Create Boot Image

The HY310 stock U-Boot only accepts Android Boot v3 format. The kernel cmdline
is hardcoded in the DTS (`chosen/bootargs`) because U-Boot ignores the boot
image header cmdline.

```bash
python3 ../hy310-linux/scripts/repack_boot.py \
    --zimage arch/arm/boot/zImage \
    --dtb ../hy310-linux/output_arm32/sun50i-h713-hy310-v7.dtb
```

This produces `mboot32.00` + `mboot32.01` (4MB chunks for U-Boot fatload).

## Step 6: Install Modules to Staging

```bash
../hy310-linux/scripts/install_modules.sh . ./staging
```

This creates a `staging/lib/modules/6.16.7/` directory ready to copy into a rootfs.

## Next

See [FLASHING.md](FLASHING.md) for how to flash the boot image to the HY310.
See [ROOTFS.md](ROOTFS.md) for how to create a Debian rootfs.
