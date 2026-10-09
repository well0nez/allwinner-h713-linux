#!/bin/sh
# build-or1k-toolchain.sh -- the bare-metal OpenRISC compiler crust is built with (binutils + gcc,
# C only, libgcc, no libc: crust is freestanding), from GNU source tarballs pinned by SHA-256.
#
# Runs inside the container h713-build (docs/build-container.md), once; release/build-all.sh
# step 1b calls it when the compiler is missing. About 6 minutes on 8 cores.
#
#   OR1K_PREFIX  where it is installed      (default: mainline/build/toolchain/or1k)
#   OR1K_CACHE   where the tarballs are kept (default: mainline/build/cache/or1k)
#   OR1K_BUILD   the build directory, deleted at the end (default: mainline/build/or1k-toolchain-build)
#
#   --stamp      only print the stamp a finished build writes last into the prefix (build-all.sh
#                compares it before it reuses a compiler)
#
# A tarball already in OR1K_CACHE is not fetched again but checked all the same. gcc's own
# contrib/download_prerequisites fetches GMP, MPFR, MPC and ISL into the cache and checks them
# against contrib/prerequisites.sha512, which comes with the pinned gcc tarball; they are built
# in-tree. MAKEINFO=true: texinfo is not in the container and no manual is needed.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
MAINLINE=$(cd "$HERE/../.." && pwd)
PREFIX=${OR1K_PREFIX:-$MAINLINE/build/toolchain/or1k}
CACHE=${OR1K_CACHE:-$MAINLINE/build/cache/or1k}
BLD=${OR1K_BUILD:-$MAINLINE/build/or1k-toolchain-build}
TARGET=or1k-elf
BINUTILS=binutils-2.42
BINUTILS_SHA256=f6e4d41fd5fc778b06b7891457b3620da5ecea1006c6a4a41ae998109f85a800
GCC=gcc-13.3.0
GCC_SHA256=0845e9621c9543a13f484e94584a49ffc0129970e9914624235fc1d061a0c083
JOBS=${JOBS:-$(nproc)}
stamp() { printf '%s %s %s %s\n' $BINUTILS $BINUTILS_SHA256 $GCC $GCC_SHA256; }
[ "${1:-}" = --stamp ] && { stamp; exit 0; }

fetch() {	# fetch NAME URL SHA256 -- into the cache unless it is there, then check it either way
	if [ ! -f "$CACHE/$1" ]; then
		curl -fsSL -o "$CACHE/$1.part" "$2" || { echo "error: cannot fetch $2" >&2; exit 1; }
		mv "$CACHE/$1.part" "$CACHE/$1"
	fi
	echo "$3  $CACHE/$1" | sha256sum -c --quiet - || { echo "error: $1 does not match its pinned SHA-256 -- not used" >&2; exit 1; }
}
mkdir -p "$CACHE"
fetch $BINUTILS.tar.xz https://ftp.gnu.org/gnu/binutils/$BINUTILS.tar.xz $BINUTILS_SHA256
fetch $GCC.tar.xz https://ftp.gnu.org/gnu/gcc/$GCC/$GCC.tar.xz $GCC_SHA256
rm -rf "$BLD"; mkdir -p "$BLD/src"
tar -C "$BLD/src" -xf "$CACHE/$BINUTILS.tar.xz"
tar -C "$BLD/src" -xf "$CACHE/$GCC.tar.xz"
# unpacks them in the cache and links gmp, mpfr, mpc and isl in the gcc tree to there
(cd "$BLD/src/$GCC" && ./contrib/download_prerequisites --directory="$CACHE" >/dev/null)
rm -rf "$PREFIX"
echo "== binutils"
mkdir -p "$BLD/binutils" && cd "$BLD/binutils"
"$BLD/src/$BINUTILS/configure" --target=$TARGET --prefix="$PREFIX" --disable-nls --disable-werror \
	--disable-gdb --disable-sim --disable-libdecnumber --disable-readline --without-zstd MAKEINFO=true >/dev/null
make -s -j"$JOBS" MAKEINFO=true >/dev/null
make -s install MAKEINFO=true >/dev/null
echo "== gcc"
export PATH="$PREFIX/bin:$PATH"
mkdir -p "$BLD/gcc" && cd "$BLD/gcc"
"$BLD/src/$GCC/configure" --target=$TARGET --prefix="$PREFIX" --enable-languages=c --disable-nls \
	--disable-shared --disable-threads --disable-libssp --disable-libquadmath --disable-libgomp \
	--disable-libatomic --disable-libstdcxx --without-headers --with-newlib --disable-multilib \
	--disable-decimal-float --disable-werror MAKEINFO=true >/dev/null
make -s -j"$JOBS" all-gcc all-target-libgcc MAKEINFO=true >/dev/null
make -s install-gcc install-target-libgcc MAKEINFO=true >/dev/null
cd / && rm -rf "$BLD"
# written last: build-all.sh reuses a compiler only with it, and stamps it into the image's BUILD.txt
stamp > "$PREFIX/.h713-or1k-toolchain"
"$PREFIX/bin/$TARGET-gcc" --version | head -1
