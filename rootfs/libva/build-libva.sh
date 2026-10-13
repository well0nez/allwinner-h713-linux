#!/bin/bash
# rootfs/libva/build-libva.sh - the VA-API driver for the stateless V4L2 decoders (cedrus, the AV1 core): megi's
# libva-v4l2_request v1.2 plus the nine patches of rootfs/libva/patches/, cross-built with clang against the arm64
# sysroot.
#
#   rootfs/libva/build-libva.sh          fetch + patch + build + stage + tarball (run inside the build container)
#   SYSROOT=... JOBS=... OUT=... rootfs/libva/build-libva.sh
#
# Why this driver: it is the one stock ffmpeg, mpv, GStreamer `va*dec` and Kodi can use to decode on the H713's
# hardware, with no change to those players (media side project, package D). Upstream is Ondrej Jirman's (megi)
# GPL-3.0 rewrite; the nine patches are Christopher Stenger's (rootfs/libva/patches/, From: and Origin: in each),
# made on the same base. 1.2 as released is not enough here: AV1 crashes, a resolution change crashes, and
# GStreamer's dma-buf allocator shows green (patches/ headers say why).
#
# Not part of release/build-all.sh and not in the base image: the profiles media and desktop carry it
# (rootfs/build-rootfs.sh --libva). libva2 itself, which loads it, is Debian's (a dependency of ffmpeg, mpv, Kodi).
#
# Output: $OUT/libva-v4l2-request-<ver>.tar (paths usr/local/lib/dri/v4l2_request_drv_video.so, usr/local/share/doc/...),
# $OUT/libva-build.log, NEEDED and the sizes on stdout.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
LIBVA_VER=1.2
LIBVA_COMMIT=cac6ece0e23ac1f944dd3af266680aff0c3184df   # v1.2 + one README commit; the SHA-1 of a git commit covers the whole tree
LIBVA_URL=https://xff.cz/git/libva-v4l2_request/
DRIVERDIR=/usr/local/lib/dri                            # LIBVA_DRIVERS_PATH in rootfs/overlay-media/etc/environment.d/h713-media.conf

CACHE="$ROOT/mainline/build/cache/libva"
SYSROOT="${SYSROOT:-$ROOT/mainline/build/sysroot-arm64}"
BUILD="$ROOT/mainline/build/libva-build"
STAGE="$ROOT/mainline/build/libva-stage"
OUT="${OUT:-$ROOT/mainline/build/out}"
JOBS="${JOBS:-$(nproc)}"
PATCHES="$ROOT/rootfs/libva/patches"
mkdir -p "$CACHE" "$OUT"

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
LOG="$OUT/libva-build.log"; : > "$LOG"

# 1. source, pinned by commit
[[ -f "$SYSROOT/usr/include/va/va.h" ]] || die "no libva headers in the sysroot $SYSROOT (libva-dev in release/build-all.sh SYSROOT_PACKAGES; its step 6 makes the sysroot)"
[[ -f "$SYSROOT/usr/include/libdrm/drm.h" ]] || die "no sysroot at $SYSROOT (release/build-all.sh step 6 makes it)"
TARBALL="$CACHE/libva-v4l2_request-$LIBVA_COMMIT.tar"
if [[ ! -f "$TARBALL" ]]; then
	say "fetch $LIBVA_URL"
	[[ -d "$CACHE/repo.git" ]] || git init -q --bare "$CACHE/repo.git"
	git -C "$CACHE/repo.git" cat-file -e "$LIBVA_COMMIT^{commit}" 2>/dev/null ||
		git -C "$CACHE/repo.git" fetch -q "$LIBVA_URL" "+refs/heads/*:refs/heads/*" "+refs/tags/*:refs/tags/*" >> "$LOG" 2>&1 ||
		die "cannot fetch $LIBVA_URL (log: $LOG)"
	[[ $(git -C "$CACHE/repo.git" rev-parse "$LIBVA_COMMIT^{commit}") == "$LIBVA_COMMIT" ]] || die "commit $LIBVA_COMMIT is not what upstream has"
	git -C "$CACHE/repo.git" archive --format=tar -o "$TARBALL.part" "$LIBVA_COMMIT" && mv "$TARBALL.part" "$TARBALL"
fi

# 2. fresh tree (no old objects: release builds start from nothing), then the series in the order of its list, no fuzz
rm -rf "$BUILD" "$STAGE"; mkdir -p "$BUILD"
SRC="$BUILD/libva-v4l2_request-$LIBVA_VER"; mkdir -p "$SRC"
tar -C "$SRC" -xf "$TARBALL"
[[ -f "$PATCHES/series" ]] || die "no $PATCHES/series"
say "patches (rootfs/libva/patches/series)"
n=0
while read -r p; do
	[[ -n "$p" ]] || continue
	( cd "$SRC" && patch -p1 --fuzz=0 --no-backup-if-mismatch -s < "$PATCHES/$p" ) >> "$LOG" 2>&1 || die "patch does not apply: $p (log: $LOG)"
	n=$((n + 1))
done < "$PATCHES/series"
[[ "$n" -eq "$(ls "$PATCHES"/0*.patch | wc -l)" ]] || die "series names $n patches, the directory has $(ls "$PATCHES"/0*.patch | wc -l)"
printf '    %d patches applied to %s\n' "$n" "$LIBVA_COMMIT"
sed "s|@SYSROOT@|$SYSROOT|g" "$ROOT/rootfs/mesa/cross-aarch64.ini.in" > "$BUILD/cross-aarch64.ini"

# 3. configure. megi's own default build type (debugoptimized, -O2) is kept, the debug info goes at install (--strip):
#    cstenger measured the driver in his build, not in an -O3 one. The module goes where LIBVA_DRIVERS_PATH points,
#    not into Debian's multiarch driver directory.
say "meson setup (libva-v4l2_request $LIBVA_VER, sysroot $SYSROOT)"
meson setup "$BUILD/build" "$SRC" --cross-file "$BUILD/cross-aarch64.ini" \
	--prefix=/usr/local --libdir=lib --strip -Ddriverdir="$DRIVERDIR" >> "$LOG" 2>&1 ||
	{ tail -30 "$LOG"; die "meson setup failed (log: $LOG)"; }
grep -E "kernel supports stateless|Dependency (libva|libdrm)" "$LOG" | sed 's/^/    /' || true

# 4. build + stage
say "ninja -j$JOBS"
ninja -C "$BUILD/build" -j"$JOBS" >> "$LOG" 2>&1 || { tail -40 "$LOG"; die "ninja failed (log: $LOG)"; }
DESTDIR="$STAGE" ninja -C "$BUILD/build" install >> "$LOG" 2>&1 || die "install failed (log: $LOG)"

# 5. checks: the module is where libva looks, aarch64, no LLVM and nothing beyond libva, libdrm and libc, the entry
#    point libva calls is exported (the module is built -fvisibility=hidden), and the patches are in the binary
#    (their environment switches are strings in it). Every codec macro the uapi headers of the sysroot lack would
#    have turned a codec off silently (HAVE_V4L2_CTRL_*), so the configure result is checked as well.
DRV="$STAGE$DRIVERDIR/v4l2_request_drv_video.so"
[[ -f "$DRV" ]] || die "missing in the stage: $DRV"
readelf -h "$DRV" | grep -q "AArch64" || die "not aarch64?"
# (no grep -q behind a pipe: with pipefail readelf dies of SIGPIPE and the test with it - see build-mesa.sh)
need=$(readelf -d "$DRV" | grep NEEDED | sed 's/.*\[\(.*\)\]/\1/' | sort -u | tr '\n' ' ')
[[ $(printf '%s' "$need" | grep -c libLLVM) -eq 0 ]] || die "the driver links libLLVM"
for lib in $need; do
	case "$lib" in libva.so.2|libdrm.so.2|libc.so.6|libm.so.6|ld-linux-aarch64.so.1) ;; *) die "unexpected NEEDED: $lib" ;; esac
done
syms=$(readelf --dyn-syms --wide "$DRV" | grep -c " __vaDriverInit_1_") || true
[[ "$syms" -ge 1 ]] || die "no __vaDriverInit_1_* exported: libva could not load the module"
for s in V4L2_REQUEST_SCALE V4L2_REQUEST_CROP V4L2_REQUEST_LSB10_LINEAR; do
	[[ $(grep -c -a "$s" "$DRV") -ge 1 ]] || die "$s is not in the driver: the patches did not get in"
done
for c in H264 HEVC MPEG2 VP8 VP9 AV1; do
	grep -q "HAVE_V4L2_CTRL_$c 1" "$BUILD/build/config.h" || die "the uapi headers of the sysroot lack the $c stateless controls (config.h)"
done
printf '    NEEDED: %s\n' "$need"

# the licence text and where the source is: GPL-3.0 binaries go into an image
install -d "$STAGE/usr/local/share/doc/libva-v4l2-request"
install -m 0644 "$SRC/COPYING" "$STAGE/usr/local/share/doc/libva-v4l2-request/COPYING"
{
	echo "libva-v4l2_request $LIBVA_VER (GPL-3.0-or-later), built for the H713 by rootfs/libva/build-libva.sh"
	echo "upstream: $LIBVA_URL"
	echo "commit:   $LIBVA_COMMIT"
	echo "patches:  rootfs/libva/patches/ of https://github.com/well0nez/allwinner-h713-linux (Christopher Stenger's, in this order):"
	sed 's/^/          /' "$PATCHES/series"
} > "$STAGE/usr/local/share/doc/libva-v4l2-request/SOURCE"

# 6. tarball + sizes. Sorted, owner 0:0 and, with SOURCE_DATE_EPOCH (release/build-all.sh), one mtime for all.
TAR="$OUT/libva-v4l2-request-$LIBVA_VER.tar"
tar -C "$STAGE" --sort=name --owner=0 --group=0 --numeric-owner ${SOURCE_DATE_EPOCH:+--mtime=@$SOURCE_DATE_EPOCH} -cf "$TAR" usr
say "done: $TAR"
printf '    installed %s, tar %s\n' "$(du -sh "$STAGE" | cut -f1)" "$(du -h "$TAR" | cut -f1)"
find "$STAGE" -name '*.so*' -type f -printf '    %10s %P\n' | sort -k2
