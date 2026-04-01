# HY310 Rootfs Bootstrap Guide

## Overview

The HY310 boots its rootfs from a USB stick (partition 2, ext4). The kernel
uses `root=/dev/sda2 rootwait` hardcoded in the DTS.

## Creating a Debian Rootfs

### Prerequisites

```bash
sudo apt install debootstrap qemu-user-static
```

### Bootstrap

```bash
ROOTFS=/path/to/rootfs
sudo debootstrap --arch=armhf --foreign trixie $ROOTFS http://deb.debian.org/debian
sudo cp /usr/bin/qemu-arm-static $ROOTFS/usr/bin/
sudo chroot $ROOTFS /debootstrap/debootstrap --second-stage
```

### Configure

```bash
sudo chroot $ROOTFS bash -c '
echo hy310 > /etc/hostname
echo "root:root" | chpasswd
echo "/dev/sda2 / ext4 defaults,noatime 0 1" > /etc/fstab

# Enable serial console
systemctl enable serial-getty@ttyS0.service

# Network
apt install -y wpasupplicant openssh-server systemd-timesyncd
'
```

### Install Kernel Modules

After building (see [BUILDING.md](BUILDING.md)):

```bash
sudo cp -a staging/lib/modules/6.16.7 $ROOTFS/lib/modules/
sudo chroot $ROOTFS depmod -a 6.16.7
```

### Install WiFi Firmware

The AIC8800D80 WiFi chip requires firmware files in `/lib/firmware/aic8800D80/`.
These must be obtained from the stock Android firmware (extracted from super.fex
vendor partition) or from the AIC vendor SDK.

```bash
sudo mkdir -p $ROOTFS/lib/firmware/aic8800D80
sudo cp /path/to/aic8800d80/firmware/* $ROOTFS/lib/firmware/aic8800D80/
```

### Flash to USB Stick

```bash
# Partition USB stick: 128MB FAT32 (boot) + rest ext4 (rootfs)
sudo fdisk /dev/sdX  # create 2 partitions
sudo mkfs.vfat -F32 -n HY310BOOT /dev/sdX1
sudo mkfs.ext4 -L HY310ROOT /dev/sdX2

# Copy rootfs
sudo mount /dev/sdX2 /mnt
sudo cp -a $ROOTFS/* /mnt/
sudo umount /mnt

# Copy boot image chunks to FAT partition
sudo mount /dev/sdX1 /mnt
sudo cp mboot32.00 mboot32.01 /mnt/
sudo umount /mnt
```
