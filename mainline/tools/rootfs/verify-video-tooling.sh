#!/usr/bin/env bash
# Compile tools/video INSIDE a built rootfs, using that image's own gcc under
# qemu-aarch64. It answers exactly one question:
#
#   can this image rebuild the video tooling, or does it only run the binaries
#   that happen to be on the board already?
#
# That question is the debt this exists to close. The first video-decode image
# got its GLES and GStreamer headers from Debian .debs extracted and pushed over
# an 11 KB/s serial console; nothing in the build reproduced them, so a rootfs
# rebuild would have silently shipped an image where gles-play no longer
# compiles. Package-presence checks in build.sh cannot see that -- only a real
# compile can, because it also exercises the pkg-config graph and the link.
#
#   usage: verify-video-tooling.sh [ROOTFS_TAR|ROOTFS_DIR]     (default:
#          build/out/rootfs.tar)
#
# Build the image it checks with:
#   tools/rootfs/build.sh --ssh-key KEY --profile video
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ROOTFS=${1:-$PROJECT_ROOT/build/out/rootfs.tar}
ORIGINAL_ARGS=("$@")

[ -e "$ROOTFS" ] || { echo "error: no such rootfs: $ROOTFS" >&2; exit 1; }
ROOTFS=$(realpath "$ROOTFS")

for tool in unshare tar; do
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

# Same rootless shape as build.sh: a complete subordinate-ID map and a private
# mount namespace, so qemu binfmt is registered for this run only and the host's
# global binfmt state is never touched.
if [ "${H713_VERIFY_NAMESPACE:-0}" != 1 ]; then
  exec unshare --map-auto --map-root-user --mount -- \
    env H713_VERIFY_NAMESPACE=1 bash "$0" "${ORIGINAL_ARGS[@]}"
fi

BINFMT_DIR=$(mktemp -d /tmp/h713-verify-binfmt.XXXXXX)
WORK_DIR=
TREE=
cleanup() {
  # Lazily, and NOT with -R: the /proc rbind carries the host's
  # /proc/sys/fs/binfmt_misc, on which umount -R aborts ("not mounted") and then
  # leaves /proc itself mounted under a tree this script is about to delete. A
  # lazy umount of the rbind root detaches the whole subtree in one call.
  if [ -n "$TREE" ]; then
    umount -l "$TREE/dev/null" 2>/dev/null || true
    umount -l "$TREE/proc" 2>/dev/null || true
  fi
  # --one-file-system so a failed umount can never let rm walk out of the
  # unpacked tree and into the host's /dev or /proc through a live bind.
  [ -z "$WORK_DIR" ] || rm -rf --one-file-system -- "$WORK_DIR"
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

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/h713-verify-rootfs.XXXXXX")
if [ -d "$ROOTFS" ]; then
  TREE=$ROOTFS
  printf '==> rootfs tree: %s\n' "$TREE"
else
  TREE=$WORK_DIR/tree
  mkdir -p "$TREE"
  printf '==> unpacking %s\n' "$ROOTFS"
  tar --numeric-owner --xattrs --acls -C "$TREE" -xf "$ROOTFS"
fi
[ -x "$TREE/usr/bin/gcc" ] || {
  echo "error: no gcc in the image -- it was not built with --profile video" >&2
  exit 1
}

# The tar carries no /dev (build.sh excludes it), and gcc's driver needs
# /dev/null; qemu and ld want /proc. Bind exactly those two into the private
# namespace -- not all of /dev, which this script later deletes.
mkdir -p "$TREE/dev" "$TREE/proc" "$TREE/tmp/video-build"
: > "$TREE/dev/null"
mount --bind /dev/null "$TREE/dev/null"
# --rbind is not a choice: a plain --bind of /proc is refused in a user
# namespace, because it would hide /proc's locked submounts. The recursion is
# why cleanup unmounts lazily -- see there.
mount --rbind /proc "$TREE/proc"
cp "$PROJECT_ROOT"/tools/video/*.c "$TREE/tmp/video-build/"

# The command for each tool is the one documented in its own source header --
# that is the contract with whoever builds it on the board, so it is what gets
# tested. If one of these changes, change it in both places.
declare -a TOOLS=(
  "gles-play|gcc -O2 -o gles-play gles-play.c \$(pkg-config --cflags --libs gstreamer-1.0 gstreamer-app-1.0 gstreamer-allocators-1.0 gstreamer-video-1.0) -lEGL -lGLESv2"
  "gles-nv12|gcc -O2 -o gles-nv12 gles-nv12.c -lEGL -lGLESv2"
  "gles-scanout|gcc -O2 -o gles-scanout gles-scanout.c -lEGL -lGLESv2"
  "gles-tear|gcc -O2 -o gles-tear gles-tear.c -lEGL -lGLESv2"
  "gles-probe|gcc -O2 -o gles-probe gles-probe.c -lEGL -lGLESv2"
  "gputest|gcc -O2 -o gputest gputest.c -lEGL -lGLESv2"
  "h713-present|gcc -O2 -o h713-present h713-present.c"
  "decd-client|gcc -O2 -o decd-client decd-client.c"
)

printf '==> compiling %s tools with the image gcc (%s)\n' "${#TOOLS[@]}" \
  "$(chroot "$TREE" /usr/bin/gcc -dumpversion 2>/dev/null || echo unknown)"
pass=0 fail=0
for entry in "${TOOLS[@]}"; do
  name=${entry%%|*}
  cmd=${entry#*|}
  log=$WORK_DIR/$name.log
  if chroot "$TREE" /bin/sh -c "cd /tmp/video-build && $cmd" >"$log" 2>&1; then
    size=$(stat -c %s "$TREE/tmp/video-build/$name" 2>/dev/null || echo 0)
    printf '  PASS  %-14s %s bytes\n' "$name" "$size"
    pass=$((pass + 1))
  else
    printf '  FAIL  %-14s\n' "$name"
    sed 's/^/          /' "$log" | head -20
    fail=$((fail + 1))
  fi
done

# A binary that is not aarch64 would mean the chroot silently used the host
# compiler, which would make every PASS above meaningless.
if [ -f "$TREE/tmp/video-build/gputest" ]; then
  arch=$(od -An -tx1 -j18 -N2 "$TREE/tmp/video-build/gputest" | tr -d ' ')
  [ "$arch" = "b700" ] || {
    echo "error: output is not aarch64 (e_machine=$arch) -- wrong compiler" >&2
    exit 1
  }
fi

rm -rf "$TREE/tmp/video-build"
printf '\n==> %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
