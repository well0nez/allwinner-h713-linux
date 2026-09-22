#!/bin/bash
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
# Output: $OUT/mesa-panfrost-<ver>.tar (paths usr/local/...), $OUT/mesa-build.log, the sizes on stdout.
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

# 3. configure: panfrost only, GLES2 + EGL + GBM, surfaceless and GBM platforms, nothing that pulls LLVM,
#    expat (xmlconfig), zlib or the on-disk shader cache (it needs a compressor; one warp shader
#    compiles in milliseconds). libdir=lib because /usr/local/lib is in the device's ld.so.conf, the
#    multiarch dir under /usr/local is not.
say "meson setup (mesa $MESA_VER, sysroot $SYSROOT)"
meson setup "$BUILD/build" "$SRC" --cross-file "$BUILD/cross-aarch64.ini" \
	--prefix=/usr/local --libdir=lib --buildtype=release --strip \
	-Db_ndebug=true \
	-Dgallium-drivers=panfrost -Dvulkan-drivers= -Dplatforms= \
	-Degl=enabled -Dgbm=enabled -Dgles1=disabled -Dgles2=enabled -Dopengl=false -Dglx=disabled \
	-Dllvm=disabled -Dglvnd=disabled -Dshared-glapi=enabled \
	-Dzlib=disabled -Dxmlconfig=disabled -Dshader-cache=disabled -Dlibunwind=disabled -Dvalgrind=disabled \
	-Dvideo-codecs= -Dtools= -Dbuild-tests=false \
	> "$OUT/mesa-build.log" 2>&1 || { tail -40 "$OUT/mesa-build.log"; die "meson setup failed (log: $OUT/mesa-build.log)"; }
grep -E "EGL platforms|Gallium drivers|GLES|OpenGL ES|GBM" "$OUT/mesa-build.log" | sed 's/^/    /' || true

# 4. build + stage
say "ninja -j$JOBS"
ninja -C "$BUILD/build" -j"$JOBS" >> "$OUT/mesa-build.log" 2>&1 || { tail -40 "$OUT/mesa-build.log"; die "ninja failed"; }
DESTDIR="$STAGE" ninja -C "$BUILD/build" install >> "$OUT/mesa-build.log" 2>&1 || die "install failed"

# 5. checks and cleanup: no LLVM anywhere, the three libraries plus the GBM backend exist, every .so is aarch64,
#    the panfrost driver is compiled into libgallium (mesa 25 has no lib/dri/*_dri.so any more). The expat that
#    meson builds as a subproject (xmlconfig is off; nothing links it) does not go onto the device.
rm -f "$STAGE"/usr/local/lib/libexpat* "$STAGE"/usr/local/include/expat*
for f in lib/libEGL.so.1 lib/libGLESv2.so.2 lib/libgbm.so.1 lib/gbm/dri_gbm.so; do
	[[ -e "$STAGE/usr/local/$f" ]] || die "missing in the stage: $f"
done
grep -q "panfrost" "$STAGE"/usr/local/lib/libgallium-*.so || die "libgallium without panfrost?"
if find "$STAGE" -name '*.so*' -type f -exec readelf -d {} + | grep -q "libLLVM"; then die "a library links libLLVM"; fi
find "$STAGE" -name '*.so*' -type f -exec readelf -h {} + | grep -q "AArch64" || die "not aarch64?"
find "$STAGE" -name '*.so*' -type f -exec readelf -d {} + | grep "NEEDED" | sed 's/.*\[\(.*\)\]/\1/' | sort -u | tr '\n' ' ' | sed 's/^/    NEEDED: /'; echo

# 6. tarball + sizes
TAR="$OUT/mesa-panfrost-$MESA_VER.tar"
tar -C "$STAGE" -cf "$TAR" usr
say "done: $TAR"
printf '    installed %s, tar %s\n' "$(du -sh "$STAGE" | cut -f1)" "$(du -h "$TAR" | cut -f1)"
find "$STAGE" -name '*.so*' -type f -printf '    %10s %P\n' | sort -k2
