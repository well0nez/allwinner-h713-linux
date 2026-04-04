# Building the HY310 Mainline Kernel

## Prerequisites

- ARM cross-compiler: `arm-linux-gnueabi-gcc` (Debian: `apt install gcc-arm-linux-gnueabi`)
- Standard kernel build tools: `make`, `bc`, `flex`, `bison`, `libssl-dev`
- Device tree compiler: built automatically with the kernel
- Python 3: for `repack_boot.py`

## Step 1: Get the Vanilla Kernel

```bash
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.16.7.tar.xz
tar xf linux-6.16.7.tar.xz
cd linux-6.16.7
```

## Step 2: Apply Patches

```bash
for p in $(cat /path/to/hy310-linux/patches/series); do
    patch -p1 < /path/to/hy310-linux/patches/$p
done
```

Or use the build script: `../hy310-linux/scripts/build_kernel.sh .`

## Step 3: Configure

```bash
cp /path/to/hy310-linux/config/hy310_defconfig arch/arm/configs/
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- hy310_defconfig
```

## Step 4: Build Kernel + In-Tree Modules

```bash
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- -j$(nproc) zImage modules
```

This produces:
- `arch/arm/boot/zImage` — compressed kernel image
- ~20 kernel modules (.ko files)

## Step 5: Build Out-of-Tree Modules

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

Or use: `../hy310-linux/scripts/build_modules.sh .`

## Step 6: Build Device Tree

```bash
../hy310-linux/scripts/build_dtb.sh . ../hy310-linux/output
```

## Step 7: Create Boot Image

The HY310 stock U-Boot only accepts Android Boot v3 format. The kernel cmdline
is hardcoded in the DTS (`chosen/bootargs`) because U-Boot ignores the boot
image header cmdline.

```bash
python3 ../hy310-linux/scripts/repack_boot.py \
    --zimage arch/arm/boot/zImage \
    --dtb ../hy310-linux/output/sun50i-h713-hy310.dtb
```

This produces `mboot32.00` + `mboot32.01` (4MB chunks for U-Boot fatload).

## Step 8: Install Modules to Staging

```bash
../hy310-linux/scripts/install_modules.sh . ./staging
```

This creates a `staging/lib/modules/6.16.7/` directory ready to copy into a rootfs.

## Next

See [FLASHING.md](FLASHING.md) for how to flash the boot image to the HY310.
See [ROOTFS.md](ROOTFS.md) for how to create a Debian rootfs.
