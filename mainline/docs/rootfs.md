# arm64 Debian rootfs

`tools/rootfs/build.sh` creates a signed Debian 13 (trixie) arm64 root
filesystem for the eMMC `UDISK` partition (`/dev/mmcblk0p26`). The build is
rootless, installs the modules from the exact pinned Linux 6.18.38 build tree,
and emits both raw ext4 and Android-sparse images.

## Security and trust model

- A public key is a mandatory argument; no personal key is stored in Git.
- Root has no usable password. SSH allows public-key authentication only.
- The physical `ttyS0` console autologins as root for board recovery and
  bring-up. Physical serial access is therefore privileged access.
- SSH host keys, the machine ID, and the systemd random seed are removed from
  the image and generated independently on first boot. An idempotent service
  runs `ssh-keygen -A` before SSH so a missing key can never race sshd startup.
- Debian `InRelease` and packages are verified with the Debian archive
  keyring. The final deb822 source uses
  `Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg`; there is no
  `[trusted=yes]` escape hatch.

If the host does not have `debian-archive-keyring` installed, the builder
downloads its Arch package, verifies the detached package signature using the
host pacman keyring, and extracts a temporary bootstrap keyring into the ignored
build cache.

## Prerequisites

On Arch/CachyOS:

- `mmdebstrap`, `apt`, `qemu-user-static-binfmt`
- `e2fsprogs`, `kmod`, `util-linux`
- `android-tools` (`img2simg` and `simg2img`)
- `curl`, `libarchive`, `openssh`

The global `systemd-binfmt` service does **not** need to be enabled. The builder
creates a private user/mount namespace and registers `qemu-aarch64-static` only
inside it. Host sudo/root access is not used.

The kernel must have been built first:

```
build/build.sh kernel
```

## Build

Pass the public key that should be authorized for root:

```
tools/rootfs/build.sh --ssh-key ~/.ssh/id_ed25519.pub
```

Optional arguments:

```
--kernel-tree DIR   use an explicit built kernel tree
--output-dir DIR    output directory (default: build/out)
--image-size SIZE   initial ext4 size (default: 2G)
```

## Video runtime, and the `dev` profile

**Every image carries the video runtime.** This is a projector; a build that
cannot play video is not a useful build of it, so these are in the base set
rather than something a bring-up image opts into:

| package | why |
|---------|-----|
| `gstreamer1.0-plugins-bad` | `libgstv4l2codecs.so`, i.e. `v4l2slh264dec`. It is in "bad", not "good", and it is why this set is large — it pulls GTK3, x265, aom |
| `gstreamer1.0-libav` | `avdec_h264`, the software control `m1-decode-test.sh` scores hardware decode against |
| `libgl1-mesa-dri` | `panfrost_dri.so`; without it EGL comes up with no renderer for the Mali-G31 |
| `libgles2`, `libegl1` | the runtime dispatch libraries (`libegl1` pulls `libegl-mesa0`) |
| `v4l-utils` | `v4l2-ctl`, the M1 decode gate |
| `mpv` | play a file from the device with no host in the loop; ~8 MB on top of the above |

That costs about 680 MB installed, nearly all of it `plugins-bad`'s dependency
tree. One caveat on `mpv`: its video outputs want DRM/KMS, X or Wayland, and
this panel is driven through AFBD registers with panfrost as a render-only
device — so mpv exercises decode and file handling, not scanout.

Every image also gets `/etc/modules-load.d/h713-video.conf` so
`sunxi_scanout_dmabuf` loads at boot. That module is a plain misc device with no
DT compatible and no module alias — `modinfo` shows none — so udev can never
autoload it the way it does cedrus and panfrost, and anything that presents a
frame through the carveout fails without it.

**`--profile dev` adds the on-target build environment** (repeatable;
`--extra-packages LIST` still takes an ad-hoc comma-separated list):

```
tools/rootfs/build.sh --ssh-key ~/.ssh/id_ed25519.pub --profile dev
```

This half is genuinely optional — the product never compiles its own tools — but
without it a rootfs rebuild silently produces an image where `gles-play` no
longer builds, which is exactly what happened when the first video image got its
headers from `.deb`s extracted over the serial console. The two traps in the
list:

| package | why |
|---------|-----|
| `libgles-dev` | GLES2 headers + `libGLESv2.so`; depends on `libgl-dev`, which is where `KHR/khrplatform.h` actually lives — nothing needs fetching from the Khronos registry |
| `libgstreamer-plugins-base1.0-dev` | `gst/app`, `gst/allocators`, `gst/video` headers; pulls `libgstreamer1.0-dev`, `pkgconf` and `libglib2.0-dev` — which is transitional in trixie, `glib.h` comes from `libgio-2.0-dev` |

plus `build-essential`, `libv4l-dev`, `libdrm-dev`, `python3` and `strace`
(+376 MB), and it raises the image to 3 GiB. The compiler on the board is
deliberate: the register experiments are edited in place, not cross-compiled
over an 11 KB/s UART.

The build asserts the individual headers, `.so` link targets, `.pc` files,
plugin paths and binaries these resolve — not merely that the packages installed
— so a package rename or split fails the build here instead of on the target
hours later. `build/out/rootfs.manifest` records `profiles=` and
`extra_packages=`, so an image states what is in it.

### Verifying that an image can rebuild the tooling

Package presence still is not proof that a compile works. `verify-video-tooling.sh`
unpacks the image, chroots into it under `qemu-aarch64` (privately registered
binfmt, no host state touched, no root), and builds every `tools/video/*.c` with
the **image's own** `gcc`, using the exact command documented in each tool's
source header:

```
tools/rootfs/verify-video-tooling.sh build/out/rootfs.tar
```

It also checks the output really is aarch64, since a silent fall-through to the
host compiler would make every pass meaningless.

Results, 2026-08-15:

| image | result |
|-------|--------|
| the previous `build/out/rootfs.tar` | **2/8** — `EGL/egl.h: No such file or directory`, no `gstreamer-1.0.pc`; only the two plain-gcc tools built |
| `build.sh --profile dev` | **8/8** |

The first row is the debt this closes, measured rather than assumed. The run
also caught that `gles-play.c`'s own documented build command omitted
`gstreamer-video-1.0` and had therefore never linked as written.

The default kernel-tree discovery intentionally requires exactly one complete
content-addressed `build/linux-6.18.38-*` tree. This prevents modules from a
stale kernel build being installed accidentally. If a series/defconfig/`versions.env`
edit has left several trees behind, the build aborts with `expected one ...
found N`; prune the stale `build/linux-6.18.38-*` trees (git-ignored, safe to
`rm -rf` — see [build.md](build.md#build-cache-cleanup)) or pass `--kernel-tree DIR`
to select one explicitly. `build/out/rootfs.manifest` records the `kernel_tree`
that was actually used.

## Outputs and validation

The builder publishes these ignored artifacts only after all staging-tree and
filesystem checks pass:

| Artifact | Purpose |
|----------|---------|
| `build/out/rootfs.tar` | Final customized filesystem tree, including modules |
| `build/out/rootfs.ext4` | 2 GiB raw ext4 image labelled `UDISK` |
| `build/out/rootfs.simg` | Android-sparse image for fastboot |
| `build/out/rootfs.manifest` | Suite, kernel, module count, size, and SSH-key fingerprint |
| `build/out/ROOTFS-SHA256SUMS` | SHA-256 checksums for all four files |

Verify the published set with:

```
(cd build/out && sha256sum -c ROOTFS-SHA256SUMS)
```

The build checks key permissions and identity, locked password state, SSH
policy, signed APT sources, first-boot identity handling, service enablement,
growfs configuration, and the installed module dependency database. It then
runs read-only `e2fsck`. The first completed build contained all 24 modules for
kernel `6.18.38`; sparse-to-raw conversion was byte-exact in offline testing.

**Hardware-verified on the HY200 bench board (2026-07-19):** the sparse image
flashed through U-Boot Fastboot, booted twice, and expanded from 2 GiB to the
full 4.5 GiB filesystem. `ttyS0` root autologin, udev, dbus, growfs, SSH host-key
generation, and sshd all completed successfully with zero failed systemd units.
The machine ID and all three generated SSH host keys persisted unchanged across
the second boot. All 24 modules were present; Cedrus and Panfrost loaded and
bound to their devices.

## Flash

Enter fastboot from the default U-Boot UART console, or issue this as one line
from the opt-in ACM console:

```
run fastboot_mode
```

Then flash the sparse image from the host:

```
fastboot flash UDISK build/out/rootfs.simg
fastboot reboot
```

`rootfs.simg` is required instead of the 2 GiB raw image because U-Boot's
fastboot download buffer is 32 MiB; the host fastboot tool chunks sparse input.

## First-boot checks

The `x-systemd.growfs` root mount option expands the deliberately small ext4
filesystem to fill `UDISK` during first boot. On the serial console, verify:

```
uname -r
findmnt /
test -d /lib/modules/$(uname -r)
modprobe sunxi-cedrus
systemctl --no-pager status systemd-growfs-root.service ssh.service
```

Expected kernel release is `6.18.38`. The rootfs build now also installs the
AIC8800 WiFi/BT out-of-tree modules (`aic8800_bsp`/`aic8800_fdrv`/`aic8800_btlpm`
into `/lib/modules/$KREL/updates/aic8800/`, autoloaded via
`/etc/modules-load.d/aic8800.conf`) and the pinned firmware blob (verified
against `modules/aic8800/firmware.sha256sums`, installed to
`/usr/lib/firmware/aic8800_sdio/aic8800`). See
[../modules/aic8800/README.md](../modules/aic8800/README.md). Association itself
still needs on-hardware bring-up, but the driver + firmware now ship in the image.

## Optional boot hotspot

If the file named by `HOTSPOT_CONF` in `config/versions.env` exists (default
`local/hotspot.conf`, which is gitignored so the SSID/passphrase stay out of the
repo), the build bakes in an on-boot WiFi AP: `hostapd` + a DHCP-only `dnsmasq`
on `wlan0` via `h713-hotspot.service`. Because a dedicated AP owns `wlan0` and
DHCP, the STA `wpa_supplicant` and the default `dnsmasq` are masked. Remove the
file to build an image with no hotspot. Format: see
[hotspot.conf.example](../tools/rootfs/hotspot.conf.example).

The artifacts under `local/h713-arm64/rootfs-build/` are historical. They
predate signed bootstrapping, module installation, growfs, and key-only SSH.
