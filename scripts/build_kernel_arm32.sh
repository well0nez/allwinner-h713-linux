#!/bin/bash
set -euo pipefail

HY310_ROOT="${HY310_ROOT:-/opt/hy310}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

KDIR="${KDIR:-$HY310_ROOT/kernels/working}"
OUTDIR="${OUTDIR:-$HY310_ROOT/build-output}"
DEFCONFIG_SRC="${DEFCONFIG_SRC:-$REPO_DIR/config/hy310_defconfig}"

export ARCH=arm
export CROSS_COMPILE="${CROSS_COMPILE:-arm-linux-gnueabi-}"

mkdir -p "$OUTDIR"

echo "=== HY310 Mainline Kernel Build (ARM32) ==="
echo "Kernel source: $KDIR"
echo "Defconfig: $DEFCONFIG_SRC"
echo "Toolchain: $(${CROSS_COMPILE}gcc --version | head -1)"
echo "Cores: $(nproc)"
echo ""

if [ ! -f "$KDIR/Makefile" ]; then
  echo "ERROR: kernel source not found: $KDIR"
  exit 1
fi

if [ ! -f "$DEFCONFIG_SRC" ]; then
  echo "ERROR: defconfig not found: $DEFCONFIG_SRC"
  exit 1
fi

cd "$KDIR"

# Clean tree for reproducible build
make mrproper

# Use repository defconfig as single source of truth
cp "$DEFCONFIG_SRC" arch/arm/configs/hy310_defconfig

echo "=== Step 1: Apply hy310_defconfig ==="
make hy310_defconfig
make olddefconfig

echo ""
echo "Config stats:"
grep -c '=y' .config | xargs -I{} echo "  Built-in: {}"
grep -c '=m' .config | xargs -I{} echo "  Modules: {}"

echo ""
echo "=== Step 2: Build zImage ==="
make -j"$(nproc)" zImage 2>&1 | tail -20

echo ""
echo "=== Step 3: Build DTBs ==="
make -j"$(nproc)" dtbs 2>&1 | tail -10

echo ""
echo "=== Step 4: Build modules ==="
make -j"$(nproc)" modules 2>&1 | tail -10

echo ""
echo "=== Step 5: Collect output ==="
cp arch/arm/boot/zImage "$OUTDIR/"

# Copy our HY310 DTB if it was built
if [ -f arch/arm/boot/dts/allwinner/sun50i-h713-hy310.dtb ]; then
  cp arch/arm/boot/dts/allwinner/sun50i-h713-hy310.dtb "$OUTDIR/"
  echo "HY310 DTB: OK"
elif [ -f arch/arm/boot/dts/sun50i-h713-hy310.dtb ]; then
  cp arch/arm/boot/dts/sun50i-h713-hy310.dtb "$OUTDIR/"
  echo "HY310 DTB: OK (alt path)"
fi

# Install modules to rootfs if it exists
ROOTFS="${ROOTFS:-$HY310_ROOT/rootfs/debian-armhf}"
if [ -d "$ROOTFS" ]; then
  echo ""
  echo "=== Step 5b: Install modules to rootfs ==="
  sudo make modules_install INSTALL_MOD_PATH="$ROOTFS" 2>&1 | tail -5
  echo "Modules installed to $ROOTFS"
fi

# Gzip compress for Android boot image
echo ""
echo "=== Step 6: Create gzip compressed Android boot image ==="
gzip -9 -k -f "$OUTDIR/zImage"

python3 - "$OUTDIR/zImage.gz" "$OUTDIR" << 'PYEOF'
import struct, sys, os

gz_path = sys.argv[1]
outdir = sys.argv[2]

with open(gz_path, 'rb') as f:
    kernel_data = f.read()

print(f"Compressed kernel: {len(kernel_data)} bytes ({len(kernel_data)/1024/1024:.1f} MB)")

PAGE_SIZE = 4096
HEADER_SIZE = 1580

header = bytearray(HEADER_SIZE)
header[0:8] = b'ANDROID!'
struct.pack_into('<I', header, 8, len(kernel_data))
struct.pack_into('<I', header, 12, 0)  # no ramdisk
struct.pack_into('<I', header, 16, 0x16000162)
struct.pack_into('<I', header, 20, HEADER_SIZE)
struct.pack_into('<I', header, 40, 3)  # v3
cmdline = b'console=ttyS0,115200 earlycon earlyprintk loglevel=8 root=/dev/sda2 rootwait rootfstype=ext4 clk_ignore_unused'
header[44:44+len(cmdline)] = cmdline

def page_align(size):
    return ((size + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE

header_padded = bytes(header) + b'\x00' * (page_align(HEADER_SIZE) - HEADER_SIZE)
kernel_padded = kernel_data + b'\x00' * (page_align(len(kernel_data)) - len(kernel_data))
image = header_padded + kernel_padded

out_path = os.path.join(outdir, 'hy310-mainline-arm32-boot.img')
with open(out_path, 'wb') as f:
    f.write(image)

print(f"Boot image: {len(image)} bytes ({len(image)/1024/1024:.1f} MB)")

# 4MB chunks
CHUNK_SIZE = 4 * 1024 * 1024
offset = 0
idx = 0
while offset < len(image):
    end = min(offset + CHUNK_SIZE, len(image))
    chunk = image[offset:end]
    name = f"mboot32.{idx:02d}"
    path = os.path.join(outdir, name)
    with open(path, 'wb') as f:
        f.write(chunk)
    offset = end
    idx += 1

print(f"{idx} chunks created")
print()
print("=== U-Boot commands ===")
print("usb start")
base = 0x45000000
for i in range(idx):
    addr = base + i * CHUNK_SIZE
    print(f"fatload usb 0:1 0x{addr:08x} mboot32.{i:02d}")
print(f"bootm 0x{base:08x}")
PYEOF

echo ""
echo "=== Output ==="
ls -lh "$OUTDIR/"
echo ""
echo "=== DONE ==="
date
