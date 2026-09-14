# Releases and versions

Three different numbers exist in this project, and mixing them up is easy. This page says which is which.

## What a release is

A release is a git tag plus the files a user needs to install without building anything. Tags are named
`vX.Y` or `vX.Y-beta`, and every file carries the same string. The names are unchanged since v0.5-beta:

| File | What it is |
|---|---|
| `h713-hy310-vX.Y-a-bootkette.img`, `-b-system.img`, `-c-gptkopie.img` | the three image parts, uploaded `.zst`-packed |
| `h713-hy310-vX.Y.tabelle.json` | the offset table: where each part goes, and where the placeholders lie |
| `h713-hy310-vX.Y.sha256` | checksums of the parts and of the table |
| `h713-hy310-vX.Y-README.txt` | what to do with all of it, next to the files themselves |
| `u-boot-installer.bin`, `sunxi-fel` | what [`h713-install`](FLASHING.md) needs to expose the eMMC over USB |
| `h713-hy310-vX.Y.BUILD.txt` | the build stamp — see below |

`<name>-README.txt` is the readme the image builder writes; the German `<name>-LIESMICH.txt` is gone. The dump
directory `h713-install` leaves on your PC carries a `README.txt` of its own, for the same reason and with
the same rename behind it.

**The first public release is `v0.5-beta`.** Before it, the only way to an image is
[BUILDING.md](BUILDING.md) — there is nothing to download, and any page that says "from a release" means
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
h713-hy310-v0.5-beta  gebaut 2026-09-12T19:11:13Z in 10 min 01 s
Serie:    0c8b184696b422b1  133 Patches
Kernelbaum: 0565521f  Release 6.18.38
u-boot: 4091ea68c06   arm-trusted-firmware: dfa9fab44   sunxi-tools: 269dfa2
```

Two builds of the same sources are not byte-identical (build timestamps and paths get embedded), so
comparing image checksums between machines proves nothing. The series hash, the kernel tree digest and
the three submodule commits do. Quote the stamp in a bug report. A build from the current tree writes two
lines more than the one above: the board it was built for, and the checksum of the kernel defconfig.

## What the development numbers are

While working towards a release, images are built and thrown away with plain numbers — `v0.8`, `v0.9`,
`v0.10`, `v0.11`, `v0.12`. They are internal, they appear in the German journal and occasionally in
[STATUS.md](STATUS.md) when it says which build a device is actually running, and they have **no**
relationship to release numbers: `v0.9` on a test device is older and less correct than `v0.5-beta`.

If you did not build it yourself, you will never see one of these.

## Where to look

Releases and their notes live on this repository's releases page. The tag matches the version string in
the image name, and the release notes name the same three commits the build stamp does.
