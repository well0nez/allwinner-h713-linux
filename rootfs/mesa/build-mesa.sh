#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
#
# rootfs/mesa/build-mesa.sh - mesa for the board: the panfrost gallium driver, EGL, GLES2 and GBM,
# no LLVM, no X11, no Wayland, cross-built with clang against the arm64 sysroot.
#
#   rootfs/mesa/build-mesa.sh            build + stage + tarball (run inside the build container, or
#                                        let release/build-all.sh step 6b call it there)
#   SYSROOT=... JOBS=... rootfs/mesa/build-mesa.sh
#
# Why not Debian's packages: libgbm1 alone pulls mesa-libgallium and libllvm19 (187 MiB installed,
# plan/keystone S0). This build is 8-12 MiB. Pinned to the mesa version Debian trixie ships, so the
# only difference to the distribution's build is the option set below.
#
# glvnd: libEGL.so.1 and libGLESv2.so.2 are Debian's libglvnd
# dispatchers (libegl1, libgles2, in the base image); this mesa is their EGL vendor, libEGL_mesa.so.0,
# found through the ICD file in /etc/glvnd/egl_vendor.d. That is what lets Debian's compositors and
# Kodi (profiles, rootfs/build-rootfs.sh --profile) install and run on it: the mesa packages they
# depend on are dummies (rootfs/equivs/), the files come from here.
#
# Output: $OUT/mesa-panfrost-<ver>.tar (paths usr/local/..., plus etc/glvnd/egl_vendor.d/50_mesa.json),
# $OUT/mesa-build.log, the sizes on stdout.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
MESA_VER=25.0.7
MESA_SHA256=592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6   # = Debian's mesa_25.0.7.orig.tar.xz
MESA_URL="https://archive.mesa3d.org/mesa-$MESA_VER.tar.xz"

CACHE="$ROOT/mainline/build/cache/mesa"
SYSROOT="${SYSROOT:-$ROOT/mainline/build/sysroot-arm64}"
BUILD="$ROOT/mainline/build/mesa-build"
STAGE="$ROOT/mainline/build/mesa-stage"
OUT="${OUT:-$ROOT/mainline/build/out}"
JOBS="${JOBS:-$(nproc)}"
mkdir -p "$CACHE" "$OUT"

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# 1. source, pinned
TARBALL="$CACHE/mesa-$MESA_VER.tar.xz"
[[ -f "$TARBALL" ]] || curl -fsSL -o "$TARBALL" "$MESA_URL"
echo "$MESA_SHA256  $TARBALL" | sha256sum -c --quiet - || die "mesa tarball: sha256 does not match"
[[ -f "$SYSROOT/usr/include/libdrm/drm.h" ]] || die "no sysroot at $SYSROOT (release/build-all.sh step 6 makes it)"
[[ -d "$SYSROOT/usr/include/c++" ]] || die "sysroot without C++ headers (libstdc++-14-dev) - mesa has C++ parts"

# 2. fresh tree (no old objects: release builds start from nothing)
rm -rf "$BUILD" "$STAGE"; mkdir -p "$BUILD"
tar -C "$BUILD" -xf "$TARBALL"
SRC="$BUILD/mesa-$MESA_VER"
sed "s|@SYSROOT@|$SYSROOT|g" "$ROOT/rootfs/mesa/cross-aarch64.ini.in" > "$BUILD/cross-aarch64.ini"

# 3. configure: panfrost only, GLES2 + EGL + GBM, the Wayland platform (surfaceless and GBM need no option),
#    glvnd, nothing that pulls LLVM,
#    expat (xmlconfig), zlib or the on-disk shader cache (it needs a compressor; one warp shader
#    compiles in milliseconds). libdir=lib because /usr/local/lib is in the device's ld.so.conf, the
#    multiarch dir under /usr/local is not.
say "meson setup (mesa $MESA_VER, sysroot $SYSROOT)"
meson setup "$BUILD/build" "$SRC" --cross-file "$BUILD/cross-aarch64.ini" \
	--prefix=/usr/local --libdir=lib --buildtype=release --strip \
	-Db_ndebug=true \
	-Dgallium-drivers=panfrost -Dvulkan-drivers= -Dplatforms=wayland \
	-Degl=enabled -Dgbm=enabled -Dgles1=disabled -Dgles2=enabled -Dopengl=false -Dglx=disabled \
	-Dllvm=disabled -Dglvnd=enabled -Dshared-glapi=enabled \
	-Dzlib=disabled -Dxmlconfig=disabled -Dshader-cache=disabled -Dlibunwind=disabled -Dvalgrind=disabled \
	-Dvideo-codecs= -Dtools= -Dbuild-tests=false \
	> "$OUT/mesa-build.log" 2>&1 || { tail -40 "$OUT/mesa-build.log"; die "meson setup failed (log: $OUT/mesa-build.log)"; }
grep -E "EGL platforms|Gallium drivers|GLES|OpenGL ES|GBM" "$OUT/mesa-build.log" | sed 's/^/    /' || true

# 4. build + stage
say "ninja -j$JOBS"
ninja -C "$BUILD/build" -j"$JOBS" >> "$OUT/mesa-build.log" 2>&1 || { tail -40 "$OUT/mesa-build.log"; die "ninja failed"; }
DESTDIR="$STAGE" ninja -C "$BUILD/build" install >> "$OUT/mesa-build.log" 2>&1 || die "install failed"

# 5. checks and cleanup: no LLVM and no X11 anywhere, the EGL vendor library, GBM and the GBM backend exist, every
#    .so is aarch64, the panfrost driver is compiled into libgallium (mesa 25 has no lib/dri/*_dri.so any more).
#    The expat that meson builds as a subproject (xmlconfig is off; nothing links it) does not go onto the device.
#    With glvnd there is no libEGL.so.1 and no libGLESv2.so.2 here (Debian's libegl1/libgles2 are the dispatchers,
#    GLES2 comes through libEGL_mesa and libgallium). glvnd looks for the vendor's ICD file in /etc/glvnd/egl_vendor.d
#    and /usr/share/glvnd/egl_vendor.d, not under /usr/local: the file moves to /etc.
rm -f "$STAGE"/usr/local/lib/libexpat* "$STAGE"/usr/local/include/expat*
for f in lib/libEGL_mesa.so.0 lib/libgbm.so.1 lib/gbm/dri_gbm.so share/glvnd/egl_vendor.d/50_mesa.json; do
	[[ -e "$STAGE/usr/local/$f" ]] || die "missing in the stage: $f"
done
for f in lib/libEGL.so.1 lib/libGLESv2.so.2; do
	[[ ! -e "$STAGE/usr/local/$f" ]] || die "$f in the stage: that is the glvnd dispatcher's name, mesa would shadow it"
done
install -d "$STAGE/etc/glvnd/egl_vendor.d"
mv "$STAGE/usr/local/share/glvnd/egl_vendor.d/50_mesa.json" "$STAGE/etc/glvnd/egl_vendor.d/"
rmdir -p --ignore-fail-on-non-empty "$STAGE/usr/local/share/glvnd/egl_vendor.d"
grep -q '"libEGL_mesa.so.0"' "$STAGE/etc/glvnd/egl_vendor.d/50_mesa.json" || die "the ICD file does not name libEGL_mesa.so.0"
grep -q "panfrost" "$STAGE"/usr/local/lib/libgallium-*.so || die "libgallium without panfrost?"
# (no grep -q behind a pipe: with pipefail readelf dies of SIGPIPE, find fails and the test with it -
# 10.10.: "not aarch64?" on a good stage, and a libLLVM match would have passed unseen)
[[ $(find "$STAGE" -name '*.so*' -type f -exec readelf -d {} + | grep -c "libLLVM") -eq 0 ]] || die "a library links libLLVM"
[[ $(find "$STAGE" -name '*.so*' -type f -exec readelf -d {} + | grep -ciE "NEEDED.*(libX11|libxcb)") -eq 0 ]] || die "a library links X11/xcb"
find "$STAGE" -name 'libEGL_mesa.so.0.0.0' -exec readelf -d {} + | grep -q "libwayland-client" || die "libEGL_mesa without the Wayland platform?"
[[ $(find "$STAGE" -name '*.so*' -type f -exec readelf -h {} + | grep -c "AArch64") -gt 0 ]] || die "not aarch64?"
find "$STAGE" -name '*.so*' -type f -exec readelf -d {} + | grep "NEEDED" | sed 's/.*\[\(.*\)\]/\1/' | sort -u | tr '\n' ' ' | sed 's/^/    NEEDED: /'; echo

# Mesa is MIT-licensed for the most part and wants its copyright and permission notice in every copy: the licence
# texts of the source tree (licenses/: MIT, Apache-2.0, BSL-1.0, SGI-B-2.0, GPL-2.0-only, GPL-1.0-or-later) and its
# docs/license.rst go into the tarball, with a note on where the source is.
DOC="$STAGE/usr/local/share/doc/mesa"
install -d "$DOC"
cp -a "$SRC/licenses" "$DOC/licenses"
install -m 0644 "$SRC/docs/license.rst" "$DOC/license.rst"
{
	echo "Mesa $MESA_VER, built for the H713 by rootfs/mesa/build-mesa.sh: the panfrost gallium driver, EGL (glvnd vendor library), GLES2, GBM,"
	echo "the Wayland platform; no patches of ours, only the option set in the script."
	echo "licence:    mostly MIT; docs/license.rst (license.rst here) says who holds which copyright, licenses/ has the texts"
	echo "source:     $MESA_URL"
	echo "            sha256 $MESA_SHA256 (the same bytes as Debian's mesa_$MESA_VER.orig.tar.xz)"
	echo "build:      rootfs/mesa/build-mesa.sh and rootfs/mesa/cross-aarch64.ini.in of https://github.com/well0nez/allwinner-h713-linux, revision ${REPO_REV:-$(git -C "$ROOT" -c safe.directory='*' describe --tags --always 2>/dev/null || echo unknown)}"
} > "$DOC/README"
[[ -f "$DOC/licenses/MIT" && -s "$DOC/license.rst" ]] || die "the licence texts are not in the stage"

# 6. tarball + sizes. Sorted, owner 0:0 (build-rootfs.sh chowns to 0:0 on the way in anyway) and, with
#    SOURCE_DATE_EPOCH (release/build-all.sh), one mtime for all: the same stage gives the same tar.
TAR="$OUT/mesa-panfrost-$MESA_VER.tar"
tar -C "$STAGE" --sort=name --owner=0 --group=0 --numeric-owner ${SOURCE_DATE_EPOCH:+--mtime=@$SOURCE_DATE_EPOCH} -cf "$TAR" usr etc
say "done: $TAR"
printf '    installed %s, tar %s\n' "$(du -sh "$STAGE" | cut -f1)" "$(du -h "$TAR" | cut -f1)"
find "$STAGE" -name '*.so*' -type f -printf '    %10s %P\n' | sort -k2
