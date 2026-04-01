#!/bin/bash
# HY310 Hash-Chain Verified Flash Script
# Copies boot image to HY310 and flashes to eMMC boot_a with hash verification
#
# Usage: ./flash.sh <boot_image> [HY310_IP]
#
# The HY310 boots from eMMC partition p5 (boot_a) which uses Android Boot v3
# format. The kernel cmdline is hardcoded in the DTS — U-Boot cannot override it.
#
# Author: well0nez
# SPDX-License-Identifier: GPL-2.0

set -e

IMG="${1:?Usage: flash.sh <boot_image> [HY310_IP]}"
HY310="${2:-192.168.8.141}"
SSH="ssh -i $HOME/.ssh/id_ed25519 root@$HY310"

if [ ! -f "$IMG" ]; then
    echo "ERROR: Image not found: $IMG"
    exit 1
fi

echo "=== HY310 Flash Workflow ==="
echo "Image: $IMG"
echo "Target: root@$HY310 -> /dev/mmcblk0p5 (boot_a)"
echo ""

# Step 1: Hash on build server
BUILD_HASH=$(sha256sum "$IMG" | cut -d' ' -f1)
echo "Build hash:     $BUILD_HASH"

# Step 2: Copy to HY310
echo "Copying to HY310..."
scp -i $HOME/.ssh/id_ed25519 "$IMG" root@$HY310:/root/boot.img

# Step 3: Hash on HY310
DEVICE_HASH=$($SSH 'sha256sum /root/boot.img' | cut -d' ' -f1)
echo "Device hash:    $DEVICE_HASH"

if [ "$BUILD_HASH" != "$DEVICE_HASH" ]; then
    echo "ERROR: Hash mismatch after transfer! Aborting."
    exit 1
fi
echo "Transfer verified OK"

# Step 4: Flash to boot_a
echo "Flashing to /dev/mmcblk0p5..."
$SSH 'dd if=/root/boot.img of=/dev/mmcblk0p5 bs=512 conv=notrunc && sync'

# Step 5: Verify partition hash
BLOCKS=$(stat -c%s "$IMG")
BLOCKS=$(( (BLOCKS + 511) / 512 ))
PART_HASH=$($SSH "dd if=/dev/mmcblk0p5 bs=512 count=$BLOCKS 2>/dev/null | sha256sum" | cut -d' ' -f1)
echo "Partition hash:  $PART_HASH"

if [ "$BUILD_HASH" != "$PART_HASH" ]; then
    echo "ERROR: Partition hash mismatch! DO NOT REBOOT."
    exit 1
fi

echo ""
echo "=== Flash complete and verified ==="
echo "All 3 hashes match. Safe to reboot."
echo "  $SSH reboot"
