# Releases and versions

Three different numbers exist in this project, and mixing them up is easy. This page says which is which.

## What a release is

A release is a git tag plus the files a user needs to install without building anything. Tags are named `vX.Y` or
`vX.Y-beta`, and every file carries the same string. Since `v0.97-beta` a release has one archive per board, `<image>.tar`, holding that
board's release folder, plus the files every board shares:

| File | What it is |
|---|---|
| `<image>-a-bootkette.img`, `<image>-b-system.img`, `<image>-c-gptkopie.img` | the three image parts, uploaded `.zst`-packed; `<image>` is `h713-hy310-vX.Y-media-desktop` for the HY310 and `h713-hy200-qz713df-a1-projector05061226-vX.Y-media-desktop` for the HY300PRO-G-EU |
| `<image>.tabelle.json` | the table: where each part goes, and which of your device's own files the installer copies into which partition |
| `<image>.sha256` | checksums of the parts and of the table |
| `<image>-README.txt` | what to do with all of it, next to the files themselves |
| `<image>.BUILD.txt` | the build stamp - see below |
| `u-boot-installer.bin`, `sunxi-fel` | in each board's archive: what [`h713-install`](FLASHING.md) needs to expose the eMMC over USB; the installer U-Boot is built for that board (the two boards' differ) |
| `u-boot-h713-probe.bin` | the read-only probe for an H713 board nobody has measured ([docs/tools/h713-probe.md](docs/tools/h713-probe.md)) |
| `allwinner-h713-linux-vX.Y-with-submodules.tar` | the repository at the tag with its submodules checked out - GitHub's own "Source code" archive has no submodules, and the image's licence file points at this one for the corresponding source |

**The first public release was `v0.5-beta`.** Every release since is on this repository's releases page;
[BUILDING.md](BUILDING.md) is the other way to an image.

Why 0.5 and not 0.1: the device boots on its own, shows the HDMI input with sound and picture controls, runs Wi-Fi, the
focus motor and the camera, and can be installed and rolled back with one tool. Calling that 0.1 would undersell it.
Calling it 1.0 would be a lie while the standby question is open and one board's owner has yet to report a green run
([ROADMAP.md](ROADMAP.md)).

`-beta` comes off when the open device tests in [STATUS.md](STATUS.md) are done and a second device has been installed by
someone who did not write the installer.

## What the build stamp is

Every image carries `<image>.BUILD.txt`. That, not the version string, identifies a build. The stamp of the HY310's
`v0.97-beta` (23.10.2026):

```
h713-hy310-v0.97-beta-media-desktop  built 2026-10-23T11:06:20Z in 33 min 48 s
board:    hy310 (verified; profile hy310, DTB sun50i-h713-hy310, U-Boot hy310 + release/installer, probe h713_probe_defconfig)
series:   e8469bb799ee1c1f  351 patches
kernel defconfig: hy200_qz713df_a1_defconfig 7082d74940ac998f
kernel tree: 00cf47a9  release 6.18.38
u-boot: daa35622b0b
arm-trusted-firmware: 287dca2fe
sunxi-tools: 269dfa2
crust: 54e4a08ab9f3 (CRUST_SRC) h713_hy310_sr_defconfig v0.6.89, 0x05005128 (dram_self_refresh ir_wake_necx), or1k binutils-2.42 gcc-13.3.0
arisc: the vendor firmware from the owner's dump by default (h713-arisc.conf); crust in the rootfs only, experimental (h713-arisc set crust)
standby: sr, not offered: BL31 without SYSTEM_SUSPEND, AllowSuspend=no
repo: 43417440 (0 local changes)
source date: 1792750705 (2026-10-23T10:18:25Z, committer date of 43417440)
reproducible: yes (SOURCE_DATE_EPOCH=1792750705, commit 43417440)
profile:  media,desktop -- not a release image: over the 500 MiB of doku/107 section 7.1, the base rootfs tar is replaced by the profile tar
libva:    libva-v4l2_request cac6ece0e23a + 17 patches (rootfs/libva/patches/series), tar sha256 b1b24d820fbed386
sources:  Debian trixie,trixie-updates,trixie-security (http://deb.debian.org/debian, security: security.debian.org/debian-security) -- a profile image bootstraps from the suite, its -updates and its -security, the base image from the suite alone
rootfs packages: dpkg status 568ab820f4afcdc7 -- the tar repeats only while those Debian suites are at this state
U-Boot:   U-Boot 2026.07-rc5-gdaa35622b0bf
building blocks (sha256, 16 characters):
  spl-release.bin              d59b5af64b7e22d6
  uboot-proper-release.bin     1ad8f54db0dc8802
  hy310-env-release.bin        c357143066e56b6c
  u-boot-installer.bin         2a275c2e02b9aa38
  h713-kernel.fit              226e4c452db8bf60
  modules/aic8800_bsp.ko       cac577a9e9656fd1
  modules/aic8800_fdrv.ko      f594d9524475a0ce
  scp.bin (crust, rootfs only) 8934680a6405f1ce
  h713-tv.aarch64-linux-gnu    8fa6348f51a99948
  mesa-panfrost-25.0.7.tar     39bba6901aaf5cee
  libva-v4l2-request-1.2.tar   b1b24d820fbed386
  hy310-rootfs.tar             916c9d4c75fc90a9
```

Two builds of the same commit give the same building-block hashes: the build clock is the commit's date (`source date:`),
no part embeds the wall clock, and the cross builds map their paths out of their debug info. The `reproducible:` line says
whether a build was made that way, and if not, why (local changes, `--skip-*`, a private `--wifi-env`). The `profile:` line
still calls a `media,desktop` image "not a release image" because it is far above the 500 MiB a base image is held to; since
`v0.97-beta` that is what a release ships, and the sentence in the stamp is a left-over (`TODO.md` 1.8). Image checksums
differ between builds (the ext4 inputs carry their own UUIDs and times), so compare the stamp, not the image, and quote the
stamp in a bug report. A TEST image for a board below *verified* says so in its first line and names the board.

## What the development numbers are

While working towards a release, images are built and thrown away as `vX.Y-devN`; they appear in the German journal and
occasionally in [STATUS.md](STATUS.md). Test images for boards in test carry the board's name and a number or a `-TEST`
suffix (`hy300-pro-test11`, 22.10.2026, is the last for the HY300 Pro of issue #1); they are built for one owner and are
not releases.

## v0.97-beta (23.10.2026)

Mainline Linux 6.18.38 on the HY310 and, for the first time, a release image for a second board: the HY200 QZ713DF A1
with the HY300PRO-G-EU's firmware (`projector05061226`, verified 11.10.2026). Both are `media,desktop` images: the base
system plus Kodi, a labwc desktop and Firefox as modes, the launcher and the settings page driven by the remote. Layout v4
and the installer's way of working are unchanged since `v0.95-beta`, so the upgrade is an ordinary reinstall over our own
layout, and so is the way back. The release images were built on 23.10.2026 from `main` `43417440`, the commit the tag `v0.97-beta`
points at, after the documentation round.

**Before you install,** take the full dump of your device ([FLASHING.md](FLASHING.md)). The display firmware, the ARISC
firmware, the picture tables and the boot logo are not in this repository, and the keys and MAC addresses in your secure
storage exist exactly once. A failed install does not brick the device (FEL is always there to reinstall), but without the
dump those device-bound parts may be lost for good. **After the install** check
`fw_printenv h713_gate` and set it to 1 if the installer carried a 0 over from your dump (`TODO.md` 2.137).

**New since v0.96-beta** - 351 kernel patches, 145 more ([docs/kernel-patches.md](docs/kernel-patches.md)):

- **The remote acts.** Over Bluetooth and over infrared: volume, mute and focus with overlays over the picture; Home opens
  the **launcher**, an opaque page with HDMI input, Kodi, Browser, Desktop and Settings; the projector starts into it
  ([h713-keys](docs/tools/h713-keys.md), [h713-osd](docs/tools/h713-osd.md), `doku/193`, `doku/212`). Both stock remotes are
  known (`0254`, `0329`), and the infrared pin survives the vendor ARISC firmware's start (`0328`, `doku/219`).
- **Kodi, a desktop, a browser** as modes of the box, drawn through the keystone as Wayland clients of `h713-warp`, as
  system users; **hardware video decode** behind the IOMMU with cstenger's cedrus series and the VA-API driver, bit-exact
  over 33 clips, one hour of 4K HEVC in Kodi (`doku/211`, `doku/212`).
- **The settings page on the wall** ([h713-settings](docs/tools/h713-settings.md)): picture, white balance, gamma level
  and colour temperature (new in `h713-tv`), keystone, sound, focus, input, power, Wi-Fi.
- **Power.** A short press of the power key shows a 15 s countdown; the release switches off into U-Boot's gate at 2.9 W,
  and **the power key of either stock remote starts the board from the gate** (U-Boot `0102`, `doku/219` §3). The release
  runs the **vendor's ARISC firmware** and offers **no standby**; crust, our own ARISC firmware with a standby and a 0.3 W
  power-off, stays in the image as an experiment because the power supply hums with it (`doku/218`, the owner's decision
  of 22.10.2026; [arisc](docs/subsystems/arisc.md)).
- **Picture path.** 1080p60 from the three-slot capture ring with 59.7 of 60 frames shown (`0255`, `0314`); the warp adds
  no frame of latency; the wall stays black instead of showing the console while the picture path restarts; the EDID
  without deep colour; white balance and gamma computed the way the display firmware does.
- **Platform.** The RTC on the 24 MHz crystal (`0320`); the GPU's operating points at their true clocks (`0268` - `0270`);
  the CPU clock calm under the warp (`h713-cpufreq`); the eMMC host's read path hardened (`0312`, `0313`); the video engine's
  recovery after a damaged stream (`0305` - `0309`); the software spinlocks of `cpu_comm` as the vendor runs them (`0259`,
  `0261`); the display MIPS restartable from Linux (`0225` - `0245`); the SoC watchdog armed under systemd.
- **Boards.** A release image for the HY300PRO-G-EU's firmware variant; one host name per board (`hy310`, `hy300pro`);
  the HY300 Pro of issue #1 gets `test11` with the infrared retrofit.
- **Licences.** The image carries its licence notices and the revisions it was built from under
  `/usr/local/share/doc/h713-linux/`; cstenger's unlicensed files left the tree, the build scripts were written anew
  (`doku/210`, `doku/216`, [PROVENANCE.md](PROVENANCE.md)).

**Left out, and why:** the standby and crust's power-off (the hum, above); AV1 decode (switched off since `0310`: it
cannot live next to the video engine's recovery); the infrared remote of the HY300 (Pro) of issue #1 (his report is
outstanding). **Known and visible:** the faint flicker of the picture under load on the HY310, the stripe in the first two
panel columns under a page on the HY300PRO-G-EU - [docs/known-issues.md](docs/known-issues.md).

**Measured** with the parts of this release: on the HY300PRO-G-EU on 22.10.2026, installed over FEL, the acceptance script
with 25 of 25 cells passed and the Wi-Fi check, three rounds of switches between Kodi, desktop, browser and HDMI with the
owner's eyes, the power-off into the gate silent, the key and both remotes starting it; on the HY310 on 22./23.10.2026 the
same install, the acceptance with the owner's eyes on the cells the camera could not judge, the infrared keys of both
remotes and the start from the gate by both remotes on the UART (`doku/219`). Not measured: a 2.2 source after a restart of
the display firmware, the power draw in the gate with the infrared decoder, the Windows path.

**Files:** the table at the top of this page, with `v0.97-beta` for `vX.Y`. Unpack nothing by hand:
`h713-install install <the folder>` finds them all ([FLASHING.md](FLASHING.md)).

## Superseded releases

| Release | Why |
|---|---|
| `v0.96-beta` (04.10.2026) | Bluetooth and the stock remote, EDID block 1, the device sounds mixed into HDMI, the projection modes, optional hardware per board; no standby, no infrared, no desktop. Everything in it is in `v0.97-beta`; layout and installer unchanged, so the upgrade is an ordinary reinstall |
| `v0.95-beta` (23.09.2026) | the keystone, the settings web page, the autofocus; superseded by `v0.96-beta` |
| `v0.9-beta` (22.09.2026) | the display firmware's mode table as the mode list, the colour space from the firmware's record; superseded by `v0.95-beta` |
| `v0.7-beta` and earlier | layout v3; the installer on `main` refuses them. Take the current release |

## Where to look

Releases and their notes live on this repository's releases page. The tag matches the version string in the image name,
points at the commit the stamp's `repo:` line names, and the release notes name the same commits the build stamp does.
