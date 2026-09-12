#!/usr/bin/env bash
# Build a signed Debian arm64 rootfs, install the matching H713 modules, and
# emit raw + Android-sparse ext4 images without host root privileges.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# shellcheck source=../../config/versions.env
source "$PROJECT_ROOT/config/versions.env"

OUTPUT_DIR="$PROJECT_ROOT/build/out"
IMAGE_SIZE=$ROOTFS_IMAGE_SIZE
SSH_KEY=
KERNEL_TREE=
EXTRA_PACKAGES=
PROFILES=
DEV_PROFILE=0
ORIGINAL_ARGS=("$@")

# The image is otherwise minimal, but this is a projector: the video RUNTIME is
# not optional equipment on it, so it is part of the base set rather than
# something a bring-up image opts into. Each entry was resolved against the real
# trixie/main/arm64 Contents index (2026-08-15) rather than guessed, and the
# non-obvious ones are why the first, hand-installed set was hard to reproduce:
#
#   gstreamer1.0-plugins-bad   libgstv4l2codecs.so, i.e. v4l2slh264dec -- the
#                              decoder element gles-play drives. It is in "bad",
#                              not "good", and it is the reason this set is
#                              large: it pulls GTK3, x265, aom and friends.
#   gstreamer1.0-libav         avdec_h264, the software control that
#                              m1-decode-test.sh scores hardware decode against.
#   libgl1-mesa-dri            panfrost_dri.so. Without it EGL comes up with no
#                              renderer for the Mali-G31 and every GLES tool
#                              fails at init.
#   libgles2 / libegl1         the runtime dispatch libraries; libegl1 pulls
#                              libegl-mesa0.
#   mpv                        play a file from the device without a host in the
#                              loop. Only ~8 MB on top of the above. Note its
#                              video outputs want DRM/KMS, X or Wayland, and
#                              this panel is driven through AFBD registers with
#                              panfrost as a render-only device -- so mpv tests
#                              decode and file handling, not scanout.
VIDEO_RUNTIME_PACKAGES=libgles2,libegl1,libgl1-mesa-dri,gstreamer1.0-tools,gstreamer1.0-plugins-base,gstreamer1.0-plugins-good,gstreamer1.0-plugins-bad,gstreamer1.0-libav,v4l-utils,mpv
BASE_PACKAGES=systemd-sysv,udev,dbus,ifupdown,isc-dhcp-client,iproute2,openssh-server,ca-certificates,e2fsprogs,kmod,debian-archive-keyring,wpasupplicant,iw,wireless-regdb,rfkill,bluez,hostapd,dnsmasq,util-linux-extra,busybox,$VIDEO_RUNTIME_PACKAGES

# --profile dev: rebuild tools/video ON the board. This half is genuinely
# optional -- the product never compiles its own tools -- but without it a
# rootfs rebuild silently produces an image where gles-play no longer builds,
# which is exactly what happened when the first video image got its headers from
# .debs extracted over the serial console. The two traps in this list:
#
#   libgles-dev   GLES2 headers + libGLESv2.so. It depends on libgl-dev, which
#                 is where KHR/khrplatform.h actually lives -- the file the
#                 video notes claimed no Debian package ships at all.
#   libgstreamer-plugins-base1.0-dev
#                 gst/app, gst/allocators and gst/video headers; pulls
#                 libgstreamer1.0-dev, pkgconf and libglib2.0-dev, which is
#                 transitional in trixie -- glib.h comes from libgio-2.0-dev.
#
# build-essential is deliberate: M2/M3 are register experiments against a live
# framebuffer, and cross-compiling each iteration over an 11 KB/s UART is how
# this project has previously spent whole sessions.
#
# libva-dev, meson, ninja-build and ffmpeg are for the VA-API work in
# docs/vaapi-scope.md: building libva-v4l2-request on the board (it needs only
# libva and libdrm), and validating a hardware decode with the ffmpeg CLI
# against the M1 ladder's references before any display path is involved. The
# libva *runtime* is already present via mpv; only the headers were missing.
#
#   vainfo   the go/no-go for that work -- it is what says whether the driver
#            loads at all and which profiles it advertises, before a single
#            frame is decoded. Separate package from libva-dev.
#   gdb      the shim is unmerged POC-quality C being pointed at a VE it was
#            not developed against, so a backtrace is the expected first
#            question, not an unlikely one.
DEV_PACKAGES=build-essential,libgles-dev,libgstreamer1.0-dev,libgstreamer-plugins-base1.0-dev,libv4l-dev,libdrm-dev,libva-dev,vainfo,meson,ninja-build,ffmpeg,gdb,python3,strace
# Measured 2026-08-15: base + runtime + dev is 1.45 GiB on disk, so it fits the
# 2G default with little headroom. Raise the floor rather than have the next
# added package fail in mke2fs at the end of a ~10 minute bootstrap.
DEV_MIN_IMAGE_SIZE=3G

usage() {
  cat <<EOF
usage: $0 --ssh-key FILE [--kernel-tree DIR] [--output-dir DIR] [--image-size SIZE]
          [--profile NAME] [--extra-packages LIST]

Build Debian $DEBIAN_SUITE/$DEBIAN_ARCH into rootfs.ext4 and rootfs.simg.
The SSH public key is required and is copied into root's authorized_keys; it is
never copied into the repository outside the generated, ignored artifacts.

Every image carries the video runtime (mesa/GLES, the GStreamer stack incl.
v4l2slh264dec, v4l-utils, mpv): this is a projector.

--profile NAME installs a named bring-up package set (repeatable). Known:
  dev     rebuild tools/video on the board: an on-target compiler plus the
          GLES/EGL, GStreamer, v4l and DRM development headers.
          Raises --image-size to at least $DEV_MIN_IMAGE_SIZE.

--extra-packages takes a comma-separated list appended to the bootstrap set.
Bring-up only; the image carries nothing else beyond the base set by default.
Larger sets need --image-size.
EOF
}

while (($#)); do
  case "$1" in
    --ssh-key)      SSH_KEY=${2:?missing value for --ssh-key}; shift 2 ;;
    --kernel-tree) KERNEL_TREE=${2:?missing value for --kernel-tree}; shift 2 ;;
    --output-dir)  OUTPUT_DIR=${2:?missing value for --output-dir}; shift 2 ;;
    --image-size)  IMAGE_SIZE=${2:?missing value for --image-size}; shift 2 ;;
    --profile)     PROFILES=${PROFILES:+$PROFILES,}${2:?missing value for --profile}; shift 2 ;;
    --extra-packages) EXTRA_PACKAGES=${2:?missing value for --extra-packages}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

size_to_bytes() {
  case "$1" in
    *[Kk]) echo $(( ${1%[Kk]} * 1024 )) ;;
    *[Mm]) echo $(( ${1%[Mm]} * 1024 * 1024 )) ;;
    *[Gg]) echo $(( ${1%[Gg]} * 1024 * 1024 * 1024 )) ;;
    *[!0-9]*) echo "error: cannot parse size: $1" >&2; return 1 ;;
    *) echo "$1" ;;
  esac
}

for profile in ${PROFILES//,/ }; do
  case "$profile" in
    dev)
      DEV_PROFILE=1
      EXTRA_PACKAGES=${EXTRA_PACKAGES:+$EXTRA_PACKAGES,}$DEV_PACKAGES
      if (( $(size_to_bytes "$IMAGE_SIZE") < $(size_to_bytes "$DEV_MIN_IMAGE_SIZE") )); then
        # Print only in the namespace pass: the script re-execs itself with the
        # same arguments and would otherwise report this twice.
        if [ "${H713_ROOTFS_NAMESPACE:-0}" = 1 ]; then
          printf '==> profile dev: raising image size %s -> %s\n' \
            "$IMAGE_SIZE" "$DEV_MIN_IMAGE_SIZE"
        fi
        IMAGE_SIZE=$DEV_MIN_IMAGE_SIZE
      fi
      ;;
    *) echo "error: unknown profile: $profile (known: dev)" >&2; exit 2 ;;
  esac
done

[ -n "$SSH_KEY" ] || { echo "error: --ssh-key FILE is required" >&2; exit 2; }
SSH_KEY=$(realpath "$SSH_KEY")
[ -s "$SSH_KEY" ] || { echo "error: SSH public key not found: $SSH_KEY" >&2; exit 1; }
ssh-keygen -lf "$SSH_KEY" -E sha256 >/dev/null || {
  echo "error: invalid SSH public key file: $SSH_KEY" >&2
  exit 1
}

required_tools=(mmdebstrap unshare mke2fs e2fsck img2simg depmod modinfo ssh-keygen curl bsdtar pacman pacman-key)
for tool in "${required_tools[@]}"; do
  command -v "$tool" >/dev/null || { echo "error: required tool not found: $tool" >&2; exit 1; }
done
[ -x /usr/bin/qemu-aarch64-static ] || {
  echo "error: /usr/bin/qemu-aarch64-static is required" >&2
  exit 1
}
[ -r /usr/lib/binfmt.d/qemu-aarch64-static.conf ] || {
  echo "error: qemu-aarch64 binfmt registration file is missing" >&2
  exit 1
}

# Re-enter once with a complete subordinate-ID map and a private mount
# namespace. This keeps target ownership and qemu binfmt registration entirely
# rootless without modifying the host's global binfmt state.
if [ "${H713_ROOTFS_NAMESPACE:-0}" != 1 ]; then
  exec unshare --map-auto --map-root-user --mount -- \
    env H713_ROOTFS_NAMESPACE=1 bash "$0" "${ORIGINAL_ARGS[@]}"
fi

BINFMT_DIR=$(mktemp -d /tmp/h713-rootfs-binfmt.XXXXXX)
BOOTSTRAP_KEYRING=
WORK_DIR=
cleanup() {
  [ -z "$WORK_DIR" ] || rm -rf -- "$WORK_DIR"
  [ -z "$BOOTSTRAP_KEYRING" ] || rm -f -- "$BOOTSTRAP_KEYRING"
  umount "$BINFMT_DIR" 2>/dev/null || true
  rmdir "$BINFMT_DIR" 2>/dev/null || true
}
trap cleanup EXIT
mount -t binfmt_misc binfmt_misc "$BINFMT_DIR"
cat /usr/lib/binfmt.d/qemu-aarch64-static.conf > "$BINFMT_DIR/register"
[ -r "$BINFMT_DIR/qemu-aarch64" ] || {
  echo "error: failed to register private qemu-aarch64 binfmt" >&2
  exit 1
}

prepare_archive_keyring() {
  if [ -r "$DEBIAN_ARCHIVE_KEYRING" ]; then
    printf '%s\n' "$DEBIAN_ARCHIVE_KEYRING"
    return
  fi

  local cache="$PROJECT_ROOT/build/cache/debian-archive-keyring"
  local url package signature extracted partial
  mkdir -p "$cache"
  url=$(pacman -Sp --print-format '%l' debian-archive-keyring)
  [ -n "$url" ] || { echo "error: cannot resolve the Arch debian-archive-keyring package" >&2; return 1; }
  package="$cache/${url##*/}"
  signature="$package.sig"
  extracted="$cache/debian-archive-keyring.gpg"

  if [ ! -s "$package" ]; then
    partial="$package.part"
    curl --fail --location --retry 3 --output "$partial" "$url"
    mv "$partial" "$package"
  fi
  if [ ! -s "$signature" ]; then
    partial="$signature.part"
    curl --fail --location --retry 3 --output "$partial" "$url.sig"
    mv "$partial" "$signature"
  fi
  pacman-key --verify "$signature" "$package" >/dev/null
  partial="$extracted.part"
  # Arch packages the traditional .gpg name as a symlink to the keybox data.
  # Extract the symlink target itself so the bootstrap keyring is self-contained.
  bsdtar -xOf "$package" usr/share/keyrings/debian-archive-keyring.pgp > "$partial"
  [ -s "$partial" ] || { rm -f "$partial"; echo "error: archive keyring package is empty" >&2; return 1; }
  mv "$partial" "$extracted"
  printf '%s\n' "$extracted"
}

bootstrap_keyring_source=$(prepare_archive_keyring)
# APT drops privileges to _apt, which cannot traverse a private home directory.
# Give it a short-lived, world-readable copy in /tmp instead of weakening any
# host directory permissions.
BOOTSTRAP_KEYRING=$(mktemp /tmp/h713-debian-archive-keyring.XXXXXX.gpg)
install -m 0644 "$bootstrap_keyring_source" "$BOOTSTRAP_KEYRING"

if [ -z "$KERNEL_TREE" ]; then
  mapfile -t kernel_candidates < <(
    find "$PROJECT_ROOT/build" -maxdepth 1 -type d \
      -name "linux-$KERNEL_VERSION-*" -exec test -f '{}/modules.order' \; -print | sort
  )
  if ((${#kernel_candidates[@]} != 1)); then
    echo "error: expected one built linux-$KERNEL_VERSION content-addressed tree; found ${#kernel_candidates[@]}" >&2
    echo "run build/build.sh kernel or pass --kernel-tree DIR" >&2
    exit 1
  fi
  KERNEL_TREE=${kernel_candidates[0]}
else
  KERNEL_TREE=$(realpath "$KERNEL_TREE")
fi
[ -f "$KERNEL_TREE/modules.order" ] || { echo "error: modules are not built in $KERNEL_TREE" >&2; exit 1; }
[ -f "$KERNEL_TREE/System.map" ] || { echo "error: missing System.map in $KERNEL_TREE" >&2; exit 1; }

KERNEL_RELEASE=$(make -s -C "$KERNEL_TREE" ARCH=arm64 LLVM=1 kernelrelease)
[ "$KERNEL_RELEASE" = "$KERNEL_VERSION" ] || {
  echo "error: kernel release '$KERNEL_RELEASE' does not match pinned '$KERNEL_VERSION'" >&2
  exit 1
}
module_build_count=$(find "$KERNEL_TREE" -type f -name '*.ko' | wc -l)
((module_build_count > 0)) || { echo "error: no built kernel modules found" >&2; exit 1; }

# AIC8800 WiFi/BT: out-of-tree modules (staged by build/build.sh aic8800) plus
# the pinned firmware blob. Verify both on the host before entering the mount
# namespace, so failures are reported early and clearly.
AIC_KO_DIR="$PROJECT_ROOT/build/out/modules"
AIC_MODULES=(aic8800_bsp aic8800_fdrv aic8800_btlpm)
for m in "${AIC_MODULES[@]}"; do
  ko="$AIC_KO_DIR/$m.ko"
  [ -f "$ko" ] || { echo "error: missing $ko — run build/build.sh aic8800 first" >&2; exit 1; }
  vm=$(modinfo -F vermagic "$ko" 2>/dev/null | awk '{print $1}')
  [ "$vm" = "$KERNEL_RELEASE" ] || {
    echo "error: $m.ko vermagic '$vm' != kernel '$KERNEL_RELEASE' — rerun build/build.sh aic8800" >&2
    exit 1
  }
done
AIC_FW_SRC_ABS="$PROJECT_ROOT/$AIC8800_FW_SRC"
[ -d "$AIC_FW_SRC_ABS" ] || { echo "error: AIC8800 firmware source not found: $AIC_FW_SRC_ABS" >&2; exit 1; }
( cd "$AIC_FW_SRC_ABS" && sha256sum -c "$PROJECT_ROOT/$AIC8800_FW_SUMS" ) >/dev/null || {
  echo "error: AIC8800 firmware failed SHA-256 verification against $AIC8800_FW_SUMS" >&2
  exit 1
}

# Optional boot hotspot: baked in only if the local-only config exists. The
# SSID/passphrase live in that gitignored file, never in the repo.
HOTSPOT_ENABLED=0
HOTSPOT_SSID= HOTSPOT_PASSPHRASE= HOTSPOT_CHANNEL= HOTSPOT_IP=
HOTSPOT_DHCP_START= HOTSPOT_DHCP_END=
if [ -n "${HOTSPOT_CONF:-}" ] && [ -f "$PROJECT_ROOT/$HOTSPOT_CONF" ]; then
  # shellcheck disable=SC1090
  . "$PROJECT_ROOT/$HOTSPOT_CONF"
  : "${HOTSPOT_CHANNEL:=6}" "${HOTSPOT_IP:=192.168.4.1}"
  : "${HOTSPOT_DHCP_START:=192.168.4.10}" "${HOTSPOT_DHCP_END:=192.168.4.100}"
  [ -n "${HOTSPOT_SSID:-}" ] && [ "${#HOTSPOT_SSID}" -le 32 ] || {
    echo "error: HOTSPOT_SSID missing or >32 chars in $HOTSPOT_CONF" >&2; exit 1; }
  { [ "${#HOTSPOT_PASSPHRASE}" -ge 8 ] && [ "${#HOTSPOT_PASSPHRASE}" -le 63 ]; } || {
    echo "error: HOTSPOT_PASSPHRASE must be 8-63 chars (WPA2) in $HOTSPOT_CONF" >&2; exit 1; }
  HOTSPOT_ENABLED=1
  printf '\n==> Boot hotspot: SSID %q on ch %s, %s (from %s)\n' \
    "$HOTSPOT_SSID" "$HOTSPOT_CHANNEL" "$HOTSPOT_IP" "$HOTSPOT_CONF"
fi

mkdir -p "$PROJECT_ROOT/build" "$OUTPUT_DIR"
WORK_DIR=$(mktemp -d "$PROJECT_ROOT/build/.rootfs.XXXXXX")

ROOTFS_TAR="$WORK_DIR/rootfs.tar"
FINAL_ROOTFS_TAR="$WORK_DIR/rootfs-final.tar"
ROOTFS_TREE="$WORK_DIR/tree"
ROOTFS_EXT4="$WORK_DIR/rootfs.ext4"
ROOTFS_SIMG="$WORK_DIR/rootfs.simg"

INCLUDE_PACKAGES=$BASE_PACKAGES
if [ -n "$EXTRA_PACKAGES" ]; then
  INCLUDE_PACKAGES="$BASE_PACKAGES,$EXTRA_PACKAGES"
  printf '\n==> Extra packages requested: %s\n' "$EXTRA_PACKAGES"
fi

printf '\n==> Bootstrap signed Debian %s/%s\n' "$DEBIAN_SUITE" "$DEBIAN_ARCH"
mmdebstrap \
  --mode=unshare \
  --variant=minbase \
  --arch="$DEBIAN_ARCH" \
  --skip=check/qemu \
  --keyring="$BOOTSTRAP_KEYRING" \
  --aptopt='Acquire::Languages "none"' \
  --include="$INCLUDE_PACKAGES" \
  "$DEBIAN_SUITE" "$ROOTFS_TAR" \
  "deb [signed-by=$BOOTSTRAP_KEYRING] $DEBIAN_MIRROR $DEBIAN_SUITE main"

printf '\n==> Customize, install Linux %s modules, and create ext4\n' "$KERNEL_RELEASE"
env \
  ROOTFS_TAR="$ROOTFS_TAR" \
  FINAL_ROOTFS_TAR="$FINAL_ROOTFS_TAR" \
  ROOTFS_TREE="$ROOTFS_TREE" \
  ROOTFS_EXT4="$ROOTFS_EXT4" \
  IMAGE_SIZE="$IMAGE_SIZE" \
  SSH_KEY="$SSH_KEY" \
  CUSTOMIZE="$PROJECT_ROOT/tools/rootfs/customize.sh" \
  KERNEL_TREE="$KERNEL_TREE" \
  KERNEL_RELEASE="$KERNEL_RELEASE" \
  AIC_KO_DIR="$AIC_KO_DIR" \
  AIC_FW_SRC="$AIC_FW_SRC_ABS" \
  WIFI_BASELINE_SRC="$PROJECT_ROOT/tools/wifi/wifi-baseline.sh" \
  AIC_FW_DEST="$AIC8800_FW_DEST" \
  HOTSPOT_ENABLED="$HOTSPOT_ENABLED" \
  HOTSPOT_SSID="$HOTSPOT_SSID" \
  HOTSPOT_PASSPHRASE="$HOTSPOT_PASSPHRASE" \
  HOTSPOT_CHANNEL="$HOTSPOT_CHANNEL" \
  HOTSPOT_IP="$HOTSPOT_IP" \
  HOTSPOT_DHCP_START="$HOTSPOT_DHCP_START" \
  HOTSPOT_DHCP_END="$HOTSPOT_DHCP_END" \
  DEBIAN_MIRROR="$DEBIAN_MIRROR" \
  DEBIAN_SUITE="$DEBIAN_SUITE" \
  DEV_PROFILE="$DEV_PROFILE" \
  bash -ceu '
    mkdir -p "$ROOTFS_TREE"
    tar --numeric-owner --xattrs --acls --exclude="./dev/*" -C "$ROOTFS_TREE" -xf "$ROOTFS_TAR"
    "$CUSTOMIZE" "$ROOTFS_TREE" "$SSH_KEY" "$DEBIAN_MIRROR" "$DEBIAN_SUITE"

    make -s -C "$KERNEL_TREE" ARCH=arm64 LLVM=1 \
      INSTALL_MOD_PATH="$ROOTFS_TREE" modules_install
    find "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE" -maxdepth 1 -type l \
      \( -name build -o -name source \) -delete

    # AIC8800 out-of-tree modules go in updates/ (takes precedence, survives an
    # in-tree modules_install); firmware blob to the driver CONFIG_AIC_FW_PATH.
    install -d "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE/updates/aic8800"
    install -m 0644 "$AIC_KO_DIR/aic8800_bsp.ko" "$AIC_KO_DIR/aic8800_fdrv.ko" \
      "$AIC_KO_DIR/aic8800_btlpm.ko" \
      "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE/updates/aic8800/"
    install -d "$ROOTFS_TREE/$AIC_FW_DEST"
    install -m 0644 "$AIC_FW_SRC"/* "$ROOTFS_TREE/$AIC_FW_DEST/"

    depmod -b "$ROOTFS_TREE" -F "$KERNEL_TREE/System.map" "$KERNEL_RELEASE"

    test "$(stat -c %a "$ROOTFS_TREE/root/.ssh")" = 700
    test "$(stat -c %a "$ROOTFS_TREE/root/.ssh/authorized_keys")" = 600
    cmp -s "$SSH_KEY" "$ROOTFS_TREE/root/.ssh/authorized_keys"
    grep -qx "PasswordAuthentication no" "$ROOTFS_TREE/etc/ssh/sshd_config.d/10-h713.conf"
    grep -qx "AuthenticationMethods publickey" "$ROOTFS_TREE/etc/ssh/sshd_config.d/10-h713.conf"
    grep -q "x-systemd.growfs" "$ROOTFS_TREE/etc/fstab"
    ! grep -R "trusted=yes" "$ROOTFS_TREE/etc/apt" >/dev/null 2>&1
    grep -qx "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" \
      "$ROOTFS_TREE/etc/apt/sources.list.d/debian.sources"
    test -L "$ROOTFS_TREE/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service"
    test -L "$ROOTFS_TREE/etc/systemd/system/multi-user.target.wants/ssh.service"
    test -L "$ROOTFS_TREE/etc/systemd/system/ssh.service.wants/h713-ssh-host-keys.service"
    test -f "$ROOTFS_TREE/usr/lib/systemd/system/systemd-udevd.service"
    test -f "$ROOTFS_TREE/usr/lib/systemd/system/dbus.service"
    test -z "$(find "$ROOTFS_TREE/etc/ssh" -maxdepth 1 -type f -name "ssh_host_*" -print -quit)"
    root_hash=$(awk -F: '\''$1 == "root" { print $2 }'\'' "$ROOTFS_TREE/etc/shadow")
    case "$root_hash" in "!"*) ;; *) echo "error: root password is not locked" >&2; exit 1 ;; esac
    test -s "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE/modules.dep"
    test "$(find "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE" -type f -name "*.ko*" | wc -l)" -gt 0
    # AIC8800 WiFi/BT: modules installed, indexed by depmod, firmware + autoload present
    test -f "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE/updates/aic8800/aic8800_fdrv.ko"
    test -f "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE/updates/aic8800/aic8800_btlpm.ko"
    grep -q "updates/aic8800/aic8800_fdrv.ko" "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE/modules.dep"
    test -f "$ROOTFS_TREE/$AIC_FW_DEST/fmacfw_8800d80_u02.bin"
    test -f "$ROOTFS_TREE/$AIC_FW_DEST/fmacfwbt_8800d80_u02.bin"
    # The HY200 chip reports as an "h" variant (is_chip_id_h, read from register
    # 0x40500000), so the 2026 driver loads the _h_ firmware and nothing else
    # will do -- without this the driver enumerates the chip, fails to upload
    # fmacfw, and wlan0 never appears.
    test -f "$ROOTFS_TREE/$AIC_FW_DEST/fmacfw_8800d80_h_u02.bin"
    # the baseline tool must be on the board: it cannot be copied there later
    test -x "$ROOTFS_TREE/usr/local/sbin/wifi-baseline"
    grep -qx "aic8800_fdrv" "$ROOTFS_TREE/etc/modules-load.d/aic8800.conf"
    test -x "$ROOTFS_TREE/usr/local/sbin/h713-bt-attach"
    grep -q "noflow" "$ROOTFS_TREE/usr/local/sbin/h713-bt-attach"
    test -L "$ROOTFS_TREE/etc/systemd/system/multi-user.target.wants/h713-bt-attach.service"
    # Video runtime: assert the files that are actually dlopened and linked, not
    # just that the packages installed. A package rename or split would
    # otherwise ship an image that fails on the target hours later.
    L=$ROOTFS_TREE/usr/lib/aarch64-linux-gnu
    test -e "$L/libGLESv2.so.2"                                 # libgles2
    test -e "$L/libEGL.so.1"                                    # libegl1
    test -e "$L/dri/panfrost_dri.so"                            # the renderer
    test -e "$L/gstreamer-1.0/libgstv4l2codecs.so"              # v4l2slh264dec
    test -x "$ROOTFS_TREE/usr/bin/gst-launch-1.0"
    test -x "$ROOTFS_TREE/usr/bin/gst-inspect-1.0"
    test -x "$ROOTFS_TREE/usr/bin/v4l2-ctl"
    test -x "$ROOTFS_TREE/usr/bin/mpv"
    grep -qx "sunxi_scanout_dmabuf" "$ROOTFS_TREE/etc/modules-load.d/h713-video.conf"
    test -n "$(find "$ROOTFS_TREE/lib/modules/$KERNEL_RELEASE" -name "sunxi-scanout-dmabuf.ko*" -print -quit)"
    if [ "$DEV_PROFILE" = 1 ]; then
      # The exact headers, link targets and .pc files tools/video resolves.
      test -f "$ROOTFS_TREE/usr/include/KHR/khrplatform.h"      # via libgl-dev
      test -f "$ROOTFS_TREE/usr/include/GLES2/gl2.h"
      test -f "$ROOTFS_TREE/usr/include/GLES2/gl2ext.h"
      test -f "$ROOTFS_TREE/usr/include/EGL/egl.h"
      test -f "$ROOTFS_TREE/usr/include/EGL/eglext.h"
      test -f "$ROOTFS_TREE/usr/include/glib-2.0/glib.h"        # via libgio-2.0-dev
      test -f "$L/glib-2.0/include/glibconfig.h"
      test -f "$ROOTFS_TREE/usr/include/gstreamer-1.0/gst/gst.h"
      test -f "$ROOTFS_TREE/usr/include/gstreamer-1.0/gst/app/gstappsink.h"
      test -f "$ROOTFS_TREE/usr/include/gstreamer-1.0/gst/allocators/gstdmabuf.h"
      test -f "$ROOTFS_TREE/usr/include/gstreamer-1.0/gst/video/video-info-dma.h"
      for pc in gstreamer-1.0 gstreamer-app-1.0 gstreamer-allocators-1.0 gstreamer-video-1.0; do
        test -f "$L/pkgconfig/$pc.pc"
      done
      test -e "$L/libGLESv2.so"                                 # -lGLESv2 target
      test -e "$L/libEGL.so"                                    # -lEGL target
      test -f "$ROOTFS_TREE/usr/include/va/va.h"                # libva-dev
      test -f "$L/pkgconfig/libva.pc"
      test -x "$ROOTFS_TREE/usr/bin/gcc"
      test -x "$ROOTFS_TREE/usr/bin/meson"
      test -x "$ROOTFS_TREE/usr/bin/ffmpeg"
      test -x "$ROOTFS_TREE/usr/bin/pkg-config"
    fi
    if [ "$HOTSPOT_ENABLED" = 1 ]; then
      grep -qx "ssid=$HOTSPOT_SSID" "$ROOTFS_TREE/etc/hostapd/hotspot.conf"
      test "$(stat -c %a "$ROOTFS_TREE/etc/hostapd/hotspot.conf")" = 600
      test -x "$ROOTFS_TREE/usr/local/sbin/h713-hotspot-up"
      test -L "$ROOTFS_TREE/etc/systemd/system/multi-user.target.wants/h713-hotspot.service"
      test -L "$ROOTFS_TREE/etc/systemd/system/wpa_supplicant.service"   # masked
    fi

    tar --numeric-owner --xattrs --acls -C "$ROOTFS_TREE" -cf "$FINAL_ROOTFS_TAR" .
    truncate -s "$IMAGE_SIZE" "$ROOTFS_EXT4"
    mke2fs -q -F -t ext4 -L UDISK -m 1 \
      -E lazy_itable_init=0,lazy_journal_init=0 \
      -d "$ROOTFS_TREE" "$ROOTFS_EXT4"
  '

e2fsck -fn "$ROOTFS_EXT4"
img2simg "$ROOTFS_EXT4" "$ROOTFS_SIMG"

SSH_FINGERPRINT=$(ssh-keygen -lf "$SSH_KEY" -E sha256 | awk '{print $2}')
cat > "$WORK_DIR/rootfs.manifest" <<EOF
suite=$DEBIAN_SUITE
architecture=$DEBIAN_ARCH
mirror=$DEBIAN_MIRROR
archive_keyring=/usr/share/keyrings/debian-archive-keyring.gpg
kernel_release=$KERNEL_RELEASE
kernel_tree=${KERNEL_TREE#$PROJECT_ROOT/}
kernel_modules=$module_build_count
image_size=$IMAGE_SIZE
profiles=${PROFILES:-none}
extra_packages=${EXTRA_PACKAGES:-none}
ssh_key_fingerprint=$SSH_FINGERPRINT
EOF

mv -f "$FINAL_ROOTFS_TAR" "$OUTPUT_DIR/rootfs.tar"
mv -f "$ROOTFS_EXT4" "$OUTPUT_DIR/rootfs.ext4"
mv -f "$ROOTFS_SIMG" "$OUTPUT_DIR/rootfs.simg"
mv -f "$WORK_DIR/rootfs.manifest" "$OUTPUT_DIR/rootfs.manifest"
(
  cd "$OUTPUT_DIR"
  sha256sum rootfs.tar rootfs.ext4 rootfs.simg rootfs.manifest > ROOTFS-SHA256SUMS
)

printf '\n==> Rootfs artifacts\n'
ls -lh "$OUTPUT_DIR/rootfs.tar" "$OUTPUT_DIR/rootfs.ext4" \
  "$OUTPUT_DIR/rootfs.simg" "$OUTPUT_DIR/rootfs.manifest" \
  "$OUTPUT_DIR/ROOTFS-SHA256SUMS"
printf '    kernel modules: %s (%s)\n' "$module_build_count" "$KERNEL_RELEASE"
printf '    SSH key: %s\n' "$SSH_FINGERPRINT"
printf '    checksums: (cd %s && sha256sum -c ROOTFS-SHA256SUMS)\n' "$OUTPUT_DIR"
