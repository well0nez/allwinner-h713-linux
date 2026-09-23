# Releases and versions

Three different numbers exist in this project, and mixing them up is easy. This page says which is which.

## What a release is

A release is a git tag plus the files a user needs to install without building anything. Tags are named
`vX.Y` or `vX.Y-beta`, and every file carries the same string. The names are unchanged since v0.5-beta:

| File | What it is |
|---|---|
| `h713-hy310-vX.Y-a-bootkette.img`, `-b-system.img`, `-c-gptkopie.img` | the three image parts, uploaded `.zst`-packed |
| `h713-hy310-vX.Y.tabelle.json` | the table: where each part goes, and which of your device's own files the installer copies into which partition (layout v4 - the image carries none of them, and no size of yours has to match) |
| `h713-hy310-vX.Y.sha256` | checksums of the parts and of the table |
| `h713-hy310-vX.Y-README.txt` | what to do with all of it, next to the files themselves |
| `u-boot-installer.bin`, `sunxi-fel` | what [`h713-install`](FLASHING.md) needs to expose the eMMC over USB |
| `h713-hy310-vX.Y.BUILD.txt` | the build stamp - see below |

`<name>-README.txt` is the readme the image builder writes; the German `<name>-LIESMICH.txt` is gone. The dump
directory `h713-install` leaves on your PC carries a `README.txt` of its own, for the same reason and with
the same rename behind it.

**The first public release is `v0.5-beta`.** Before it, the only way to an image is
[BUILDING.md](BUILDING.md) - there is nothing to download, and any page that says "from a release" means
"once one exists".

Why 0.5 and not 0.1: the device boots on its own, shows the HDMI input with sound and picture controls,
runs Wi-Fi, the focus motor and the camera, and can be installed and rolled back with one tool. Calling
that 0.1 would undersell it. Calling it 1.0 would be a lie while Bluetooth, verified video decode, HDCP
and deep sleep are open ([ROADMAP.md](ROADMAP.md)).

`-beta` comes off when the [open device tests](STATUS.md) are done and a second device has been installed
by someone who did not write the installer.

## What the build stamp is

Every image carries `<name>.BUILD.txt`. That, not the version string, identifies a build:

```
h713-hy310-v0.9-beta  built 2026-09-22T14:55:40Z in 18 min 12 s
board:    hy310 (verified; profile hy310, DTB sun50i-h713-hy310, U-Boot hy310 + release/installer, probe h713_probe_defconfig)
series:   325196d738badd94  182 patches
kernel defconfig: hy200_qz713df_a1_defconfig 00c052ced1a85a91
kernel tree: 41b71e61  release 6.18.38
u-boot: 4cecddd5561
arm-trusted-firmware: dfa9fab44
sunxi-tools: 269dfa2
repo: 074b5835404 (0 local changes)
U-Boot:   U-Boot 2026.07-rc5-g4cecddd55613
building blocks (sha256, 16 characters):
  spl-release.bin              e36bef37a7fffbd5
  uboot-proper-release.bin     cc4f47d0945bac19
  hy310-env-release.bin        c13a84eefa0df626
  u-boot-installer.bin         e3701352bf687bbe
  h713-kernel.fit              1f90d009aebe75ab
  modules/aic8800_bsp.ko       cac577a9e9656fd1
  modules/aic8800_fdrv.ko      a73bff13e8b3da52
  h713-tv.aarch64-linux-gnu    056073ce803648da
  hy310-rootfs.tar             3a80f4fbdd5a9e4b
```

Two builds of the same sources are not byte-identical (build timestamps and paths get embedded), so
comparing image checksums between machines proves nothing. The series hash, the kernel tree digest, the
three submodule commits and the nine building blocks do. Quote the stamp in a bug report. A TEST image
for a board below *verified* says so in its first line and names the board it was built for.

## What the development numbers are

While working towards a release, images are built and thrown away as `vX.Y-devN`: `v0.8-dev15` is the
fifteenth development build on the way past `v0.8-beta`. They are internal, they appear in the German
journal and occasionally in [STATUS.md](STATUS.md) when it says which build a device is actually
running, and a `-dev` build is never a release.

If you did not build it yourself, you will never see one of these.

**Current: `v0.95-beta`** for the HY310 - the keystone chain, the settings page and the autofocus in an image. Test images for boards in test carry the board's name and a number,
`hy300-pro-test7` being the last; they are built for one owner and are not releases.

## Superseded releases

| Release | Why |
|---|---|
| `v0.9-beta` | the keystone, the settings page, the autofocus and the tearing fix are in `v0.95-beta`; layout and installer are unchanged, so the upgrade is an ordinary reinstall |
| `v0.7-beta` | its image is layout v3; the installer on `main` refuses it, and the v0.7-beta installer refuses a v4 image. Take `v0.8-beta` |

## Where to look

Releases and their notes live on this repository's releases page. The tag matches the version string in
the image name, and the release notes name the same three commits the build stamp does.
