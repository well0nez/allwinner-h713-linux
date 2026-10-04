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
| `u-boot-h713-probe.bin` | the read-only probe for an H713 board nobody has measured ([docs/tools/h713-probe.md](docs/tools/h713-probe.md)) |
| `h713-hy310-vX.Y.BUILD.txt` | the build stamp - see below |

`<name>-README.txt` is the readme the image builder writes; the German `<name>-LIESMICH.txt` is gone. The dump
directory `h713-install` leaves on your PC carries a `README.txt` of its own, for the same reason and with
the same rename behind it.

**The first public release was `v0.5-beta`.** Every release since is on this repository's releases page;
[BUILDING.md](BUILDING.md) is the other way to an image.

Why 0.5 and not 0.1: the device boots on its own, shows the HDMI input with sound and picture controls,
runs Wi-Fi, the focus motor and the camera, and can be installed and rolled back with one tool. Calling
that 0.1 would undersell it. Calling it 1.0 would be a lie while verified video decode, HDCP 1.4 and deep
sleep are open ([ROADMAP.md](ROADMAP.md)).

`-beta` comes off when the [open device tests](STATUS.md) are done and a second device has been installed
by someone who did not write the installer.

## What the build stamp is

Every image carries `<name>.BUILD.txt`. That, not the version string, identifies a build (the stamp of
`v0.9-beta`; since `v0.96-beta` it also has the lines `source date:`, `reproducible:` and `rootfs packages:`
and the mesa tar among the building blocks):

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

Two builds of the same commit are meant to give the same building-block hashes: the build clock is the
commit's date (`source date:` in the stamp), so no part embeds the wall clock, and the three userspace
cross builds map their checkout and sysroot paths out of their debug info, so the path does not matter
either. For `v0.96-beta` two builds of one commit - the working tree and a fresh clone elsewhere - gave the
same hash for every building block in the stamp, the boot chain and the backup GPT byte for byte.
The stamp's `reproducible:` line says whether a build was made that way, and if not, why (local changes,
`--skip-*`, a private `--wifi-env`). The rootfs tar repeats only while the Debian mirror is at the same
state; `rootfs packages:` names the package set for that comparison. Image checksums still differ between
builds (the ext4 inputs carry their own UUIDs and times), so compare the stamp, not the image. Quote the
stamp in a bug report. A TEST image for a board below *verified* says so in its first line and names the
board it was built for.

## What the development numbers are

While working towards a release, images are built and thrown away as `vX.Y-devN`: `v0.8-dev15` is the
fifteenth development build on the way past `v0.8-beta`. They are internal, they appear in the German
journal and occasionally in [STATUS.md](STATUS.md) when it says which build a device is actually
running, and a `-dev` build is never a release.

If you did not build it yourself, you will never see one of these.

**Current: `v0.96-beta`** for the HY310 - see the section below. Test images for boards in test carry the
board's name and a number or a `-TEST` suffix: `hy300-pro-test9` (25.09.2026) is the last for the HY300 Pro of
issue #1, and the HY200 QZ713DF A1 gets one per firmware variant; they are built for one owner and are not
releases.

## v0.96-beta

Mainline Linux 6.18.38 on the HY310, the seventh developer preview - still beta: one verified board, one
owner. Layout v4 and the installer's way of working are v0.95-beta's, so the upgrade is an ordinary
reinstall over our own layout, and so is the way back.

**Before you install,** take the full dump of your device ([FLASHING.md](FLASHING.md)). The display
firmware, the ARISC firmware, the picture tables and the boot logo are not in this repository, and the keys
and MAC addresses in your secure storage exist exactly once. Without the dump a failed install is not
repairable.

**New since v0.95-beta** - 206 kernel patches, 18 more ([docs/kernel-patches.md](docs/kernel-patches.md)):

- **The stock remote over Bluetooth.** Hold Left+Right to pair; its 16 keys and the mouse arrive as Linux
  input events (`0169`), and `h713-bt-reset` brings `hci0` up after a warm reboot too. Nothing in the image
  acts on the keys yet except Power, which shuts the system down. A reinstall loses the pairing and the
  settings in `/etc/h713` - pair again, set the corners again.
- **HDMI input.** The display firmware's own mode table is the list of modes (`0170` - `0173`), a raster
  outside it is named at once, and `h713-tv ctl edid block1` offers 1080p100/120.
- **Sound.** The box's own sounds play through `hw:hy310hdmi,0`, which the DSP mixes into HDMI and which is
  ALSA's default (`0176` - `0178`); the volume follows the stock curve. `h713-tv ctl hdcp` shows the HDCP state.
- **Geometry.** The automatic keystone corrects against the ideal level pose without a reference; four
  projection modes, the vendor's soft edge, and a calibration picture with corner cards (`h713-warp`).
- **Autofocus** waits for its pattern, turns round at the ends of the travel and walks back by counted motion.
- **Optional hardware per board.** `h713-features`; a tool whose camera, accelerometer or focus motor is
  missing says "not present on this board" (exit 7), and the settings page hides those controls.
- **Boards.** The HY200 QZ713DF A1 is one board with two firmware variants (`--variant`) and one device tree
  (`0181`); `0168` ends the lamp-word crash; U-Boot drives project 0x34 at 8-bit LVDS.
- **Installer, build, boot.** `restore-stock` takes both known eMMC sizes and refuses a container that does
  not fit; a reinstall over our layout keeps the board record and `h713_project`; a test image installs a
  second time; builds are reproducible (`SOURCE_DATE_EPOCH`); `panic=10` in the
  HY310's U-Boot environment reboots the box ten seconds after a kernel panic.

**Left out, and why:** standby (a suspend is reached, the wake-up is not), HDCP 1.4 (refused by the crypto
engine under this system, while the maker's firmware authenticates on the same unit - the reason is open and
is being looked for, [docs/known-issues.md](docs/known-issues.md)), the IR receiver (two keys send
one code), crust (after standby), reloading the display firmware at run time (black picture after a
reload), the fan backstop (untested on the device). An HDCP 2.2 session is unproven: no 2.2 source here.

**Boards.** A release image for `hy310` only. TEST images for one owner each, not releases:
`--board hy200-qz713df-a1 --variant projector05061226 --test-image` for the maintainer's HY300PRO-G-EU, and
`hy300-pro-test10` follows for the owner of issue #1 ([boards/hy300-pro](boards/hy300-pro/README.md)).

**Measured** on the HY310 from 02. to 04.10.2026 with the parts of this release (`doku/134`): the keystone
reference, the four projection modes and the soft edge on the wall; EDID block 1 with 1080p120 locked; the
remote's 16 keys, 97 of 97 pings beside it, cold start and reconnect; the device sounds within 0.1 dB of
HDMI over 20 rounds, the volume within 0.8 dB of the stock curve; the autofocus sharp at a wall twice at the
same motor position. The image itself, installed from these files over FEL on 2026-10-04 (`doku/142`):
ten cold starts in a row with the boot logo each time, Bluetooth up after two warm reboots, the remote's
keys and mouse, the device sound mixed into HDMI and the volume curve, 1080p120 under the warp at about 50
frames a second. The same commit as a TEST image on the maintainer's HY300PRO-G-EU: DRAM at 792 MHz, 8-bit
LVDS, project 0x34, the remote, Bluetooth after a cold start, three cold starts.

**Files:** the table at the top of this page, with `v0.96-beta` for `vX.Y`. Unpack nothing by hand:
`h713-install install <the folder>` finds them all ([FLASHING.md](FLASHING.md)).

## Superseded releases

| Release | Why |
|---|---|
| `v0.95-beta` | everything in it is in `v0.96-beta`; layout and installer are unchanged, so the upgrade is an ordinary reinstall |
| `v0.9-beta` | the keystone, the settings page, the autofocus and the tearing fix are in `v0.95-beta`; layout and installer are unchanged, so the upgrade is an ordinary reinstall |
| `v0.7-beta` | its image is layout v3; the installer on `main` refuses it, and the v0.7-beta installer refuses a v4 image. Take `v0.8-beta` |

## Where to look

Releases and their notes live on this repository's releases page. The tag matches the version string in
the image name, and the release notes name the same three commits the build stamp does.
