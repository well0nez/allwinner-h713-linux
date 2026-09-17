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
h713-hy310-v0.8-beta  built 2026-09-16T18:00:26Z in 19 min 24 s
board:    hy310 (verified; profile hy310, DTB sun50i-h713-hy310, U-Boot hy310 + release/installer, probe h713_probe_defconfig)
series:   43ce4ea197dd73c7  141 patches
kernel defconfig: hy200_qz713df_a1_defconfig bcf80cf8d63707f6
kernel tree: a04df07f  release 6.18.38
u-boot: d88a7c6ba3d
arm-trusted-firmware: dfa9fab44
sunxi-tools: 269dfa2
repo: 00f896a8e84 (3 local changes)
U-Boot:   U-Boot 2026.07-rc5-gd88a7c6ba3dc
building blocks (sha256, 16 characters):
  spl-release.bin              418e367596c194bb
  uboot-proper-release.bin     bc667f8d9da917b2
  hy310-env-release.bin        c13a84eefa0df626
  u-boot-installer.bin         eed278d7acb967b0
  h713-kernel.fit              11bf9e79f282a170
  modules/aic8800_bsp.ko       cac577a9e9656fd1
  modules/aic8800_fdrv.ko      1e660b556ac29df0
  h713-tv.aarch64-linux-gnu    a91e3cd10262bc07
  hy310-rootfs.tar             68ce688419b6b262
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

## Superseded releases

| Release | Why |
|---|---|
| `v0.7-beta` | its image is layout v3; the installer on `main` refuses it, and the v0.7-beta installer refuses a v4 image. Take `v0.8-beta` |

## Where to look

Releases and their notes live on this repository's releases page. The tag matches the version string in
the image name, and the release notes name the same three commits the build stamp does.
