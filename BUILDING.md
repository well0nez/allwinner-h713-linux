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

## Quick Build (End-to-End)

The `scripts/build_kernel_arm32.sh` script handles the entire pipeline:
defconfig → zImage → DTBs → modules → Android Boot v3 image (4MB chunks).

```bash
# Set paths (defaults shown)
export KDIR=/path/to/linux-6.16.7          # vanilla or patched kernel tree
export OUTDIR=./output_arm32                # build output directory
export ROOTFS=/path/to/debian-armhf         # optional: modules install target

./scripts/build_kernel_arm32.sh
```

This produces in `$OUTDIR/`:
- `zImage` — compressed kernel image
- `sun50i-h713-hy310.dtb` — device tree blob
- `hy310-mainline-arm32-boot.img` — Android Boot v3 image
- `mboot32.00`, `mboot32.01` — 4MB chunks for U-Boot fatload
- Kernel modules (installed to `$ROOTFS` if it exists)

## Manual Build Steps

### Step 1: Configure

```bash
cp /path/to/hy310-linux/config/hy310_defconfig arch/arm/configs/
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- hy310_defconfig
make olddefconfig
```

### Step 2: Build Kernel + In-Tree Modules

```bash
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- -j$(nproc) zImage modules dtbs
```

### Step 3: Build Out-of-Tree Modules

```bash
KDIR=/path/to/linux-6.16.7

# DRM display driver (h713_drm.ko)
make -C $KDIR M=/path/to/hy310-linux/drivers/display/drm ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

# Audio (codec + cpudai + machine)
make -C $KDIR M=/path/to/hy310-linux/drivers/audio ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

# Audio bridge (TridentALSA)
make -C $KDIR M=/path/to/hy310-linux/drivers/audio/bridge ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

# WiFi AIC8800 (bsp + fdrv + btlpm)
make -C $KDIR M=/path/to/hy310-linux/drivers/wifi ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules
```

Or use: `./scripts/build_modules.sh .`

### Step 4: Build Device Tree

```bash
# Canonical DTB build script (v8):
build_h713_dtb_v8.sh
```

> **Note:** `build_h713_dtb_v8.sh` is the only correct DTB build script.
> Legacy scripts (`build_dtb.sh`, `build_h713_dtb_v7.sh`) are deprecated.

### Step 5: Create Boot Image

```bash
python3 scripts/repack_boot.py \
    --zimage arch/arm/boot/zImage \
    --dtb output_arm32/sun50i-h713-hy310-v7.dtb
```

### Step 6: Install Modules to Staging

```bash
./scripts/install_modules.sh . ./staging
```

## Next

See [FLASHING.md](FLASHING.md) for how to flash the boot image to the HY310.
See [ROOTFS.md](ROOTFS.md) for how to create a Debian rootfs.
