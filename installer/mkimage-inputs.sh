#!/bin/bash
# mkimage-inputs.sh -- build the two ext4 file systems for h713-mkimage.
#
# WHY THIS SCRIPT EXISTS
# h713-mkimage runs under Linux and Windows with the standard library alone and
# without external programs. CREATING an ext4 ITSELF would be the only step that
# would break that -- so it happens here, at our end, once, in the container
# h713-build with e2fsprogs. What comes out are two ordinary files, and from
# there on they are building blocks like the SPL or the U-Boot image. At the
# user this never runs.
#
#   tmp/hy310-boot.ext4          128 MiB: h713-kernel.fit (real) + an empty mips/
#   tmp/hy310-rootfs-platz.ext4    1 GiB: the rootfs from rootfs/out/hy310-rootfs.tar,
#                                         extended by the empty target directories
#                                         (/lib/firmware/h713, the aic8800 path,
#                                         /etc/h713/tvconfig, /root/.ssh 0700)
#
# Layout v4 (plan/briefs/P-layout-v4.md): NO placeholder file goes into either file
# system. h713-install mounts the two and copies the device's own files in, each with
# its real length -- so nothing here depends on how big anybody's vendor files are.
#
# Call IN THE CONTAINER -- AS ROOT:
#   podman exec -u root h713-build bash /work/analyse/release/arbeit/r0-fel/mkimage-inputs.sh
#
# Why root: only root can make tar set the owner, and mke2fs -d takes uid/gid/mode
# from the tree. Unpacked as user 1000, EVERYTHING in the ext4 belonged to uid 1000
# -- /etc/shadow, /root, /root/.ssh -- sshd then takes no key (StrictModes) and
# setgid bits (unix_chkpwd) are missing. That is how it was in image v0.5
# (11.09.2026). build-rootfs.sh runs with -u root for the same reason; h713-mkimage
# checks the ownership in the finished ext4 afterwards.
#
# ROOT/TMP/ROOTFS_OUT/FIT can be overridden through the environment (tests out of a
# copy). WURZEL is still accepted as the old name of ROOT.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# Project root: the next parent directory with mainline/build/build.sh -- that way the
# script works in the working directory (analyse/release/arbeit/...) as well as in the
# release repository (rootfs/ and installer/ directly under the root), doku/116 P3.
project_root() { local d=$1; while [ "$d" != / ]; do [ -f "$d/mainline/build/build.sh" ] && { echo "$d"; return; }; d=$(dirname "$d"); done; return 1; }
ROOT=${ROOT:-${WURZEL:-$(project_root "$HERE")}} || { echo "no project root found above $HERE" >&2; exit 1; }
TMP=${TMP:-$HERE/tmp}
# Both layouts (release repository: rootfs/ under the root; working directory: analyse/...).
if [ -d "$ROOT/rootfs/out" ] || [ -f "$ROOT/rootfs/build-rootfs.sh" ]; then
	ROOTFS_OUT=${ROOTFS_OUT:-$ROOT/rootfs/out}
else
	ROOTFS_OUT=${ROOTFS_OUT:-$ROOT/analyse/release/arbeit/rootfs/out}
fi
# The FIT comes out of the build (release/build-all.sh), no longer out of tftp/ (12.09.).
FIT=${FIT:-$ROOT/mainline/build/out/h713-kernel.fit}

if [ "$(id -u)" != 0 ]; then
	echo "run as root: podman exec -u root h713-build bash $0" >&2
	echo "(otherwise every file in the ext4 belongs to uid $(id -u) instead of root)" >&2
	exit 1
fi

say() { printf '\n=== %s\n' "$*"; }
ok()  { printf '  OK   %s\n' "$*"; }

for w in mke2fs e2fsck python3 tar; do
	command -v "$w" >/dev/null || { echo "missing: $w (run this in the container h713-build)" >&2; exit 1; }
done
[ -f "$FIT" ] || { echo "kernel FIT not found: $FIT" >&2; exit 1; }
[ -f "$ROOTFS_OUT/hy310-rootfs.tar" ] || { echo "hy310-rootfs.tar is missing" >&2; exit 1; }

mkdir -p "$TMP"
rm -rf "$TMP/boot-baum" "$TMP/rootfs-baum"

# --- 1. hy310-boot -------------------------------------------------------
say "hy310-boot.ext4 (128 MiB)"
mkdir -p "$TMP/boot-baum"
python3 "$HERE/h713-mkimage" tree-boot "$TMP/boot-baum" --fit "$FIT"
rm -f "$TMP/hy310-boot.ext4"
truncate -s $((262144 * 512)) "$TMP/hy310-boot.ext4"
# The same options p5 was created with on the device (r1-installer do_mkfs: -m 1),
# plus lazy_*_init=0 so that the file is complete and is not finished off only at
# the first mount.
mke2fs -q -F -t ext4 -L hy310-boot -m 1 \
	-E lazy_itable_init=0,lazy_journal_init=0 \
	-d "$TMP/boot-baum" "$TMP/hy310-boot.ext4"
e2fsck -fn "$TMP/hy310-boot.ext4" >/dev/null
ok "$TMP/hy310-boot.ext4"

# --- 2. hy310-rootfs with the target directories -------------------------
say "hy310-rootfs-platz.ext4 (1 GiB)"
mkdir -p "$TMP/rootfs-baum"
# The accepted rootfs (doku/107 §9) comes out of the tar, not out of the finished
# ext4: the target directories have to be created with their own modes, and
# mke2fs -d can do that in one go. --numeric-owner: the uid/gid out of the tar,
# not resolved through the names in the container's user database (0/0, 0/42 ...).
# Then a spot check, before mke2fs bakes the tree in.
tar --numeric-owner --xattrs --acls -xf "$ROOTFS_OUT/hy310-rootfs.tar" -C "$TMP/rootfs-baum"
python3 "$HERE/h713-mkimage" tree-rootfs "$TMP/rootfs-baum"
for pf in etc/passwd root root/.ssh lib/firmware/h713 etc/h713/tvconfig; do
	owner=$(stat -c '%u:%g %a' "$TMP/rootfs-baum/$pf")
	case "$pf $owner" in
		"etc/passwd 0:0 644"|"root 0:0 700"|"root/.ssh 0:0 700") ;;
		"lib/firmware/h713 0:0 755"|"etc/h713/tvconfig 0:0 755") ;;
		*) echo "tree wrong: /$pf is $owner" >&2; exit 1 ;;
	esac
done
ok "tree: /etc/passwd, /root, /root/.ssh and the target directories belong to root, the modes match"
if [ -e "$TMP/rootfs-baum/root/.ssh/authorized_keys" ]; then
	echo "tree wrong: authorized_keys is in it -- layout v4 leaves that file to h713-install" >&2
	exit 1
fi
rm -f "$TMP/hy310-rootfs-platz.ext4"
truncate -s 1G "$TMP/hy310-rootfs-platz.ext4"
# Word for word the same as build-rootfs.sh, so that this file system is the same as
# the accepted one -- only with the empty target directories more.
mke2fs -q -F -t ext4 -L hy310-rootfs -m 1 \
	-E lazy_itable_init=0,lazy_journal_init=0 \
	-d "$TMP/rootfs-baum" "$TMP/hy310-rootfs-platz.ext4"
e2fsck -fn "$TMP/hy310-rootfs-platz.ext4" >/dev/null
ok "$TMP/hy310-rootfs-platz.ext4"

say "counter-check"
echo "  rootfs tree size:   $(du -sxk "$TMP/rootfs-baum" | cut -f1) KiB"
echo "  files in boot-baum: $(find "$TMP/boot-baum" -type f | wc -l)"
ls -l "$TMP/hy310-boot.ext4" "$TMP/hy310-rootfs-platz.ext4"

say "done -- now (the host is enough for this) h713-mkimage build -o ..."
