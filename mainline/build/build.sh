#!/usr/bin/env bash
# H713 firmware build orchestrator.
#
#   TF-A BL31  ->  U-Boot (SPL + BL31 + proper)  ->  Linux kernel  ->  images
#
# Sources are the git submodules under external/ and two curated patch series on
# pinned upstream tarballs - patches/kernel/ and patches/aic8800/ (see
# patches/README.md); versions are pinned in config/versions.env. LLVM-only
# (clang / ld.lld) - see config/toolchain.md.
#
# Usage:
#   build/build.sh [all|bl31|uboot|kernel|aic8800|images]   # default: all
#
# Env:
#   BOARD=<id>          board id, i.e. a directory under boards/ (default ddr3).
#                       'ddr3' and 'lpddr3' stay as aliases for cstenger's two
#                       HY200 boards -- ddr3=HY200 QZ713DF_A1 bench,
#                       lpddr3=HY200 QZ713_V2 projector. boards/<id>/board.env
#                       names the kernel DTB the FIT carries.
#   VARIANT=<name>      one stock firmware of a board with VARIANTS (boards/<id>/
#                       variants/<name>/variant.env): its DRAM clock goes into U-Boot.
#                       Unset on such a board, U-Boot is the base at its lower clock.
#   JOBS=N              parallelism (default: nproc)
#   H713_STANDBY=1      BL31 with PSCI SYSTEM_SUSPEND, the standby through crust
#                       (release/build-all.sh --standby); only for a verified board
#                       whose board.env names CRUST_DEFCONFIG
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=../config/versions.env
source "$ROOT/config/versions.env"

BOARD=${BOARD:-ddr3}
VARIANT=${VARIANT:-}
JOBS=${JOBS:-$(nproc)}
# KERNEL_CONFIG=name[,name...] merges patches/kernel/board/<name>.config over the
# board defconfig. Debug kernels only -- the shipping kernel is the defconfig
# alone. Fragments are part of the input digest, so a debug build gets its own
# source tree instead of quietly reusing the production one's objects, and its
# outputs are suffixed so it cannot overwrite the FIT the board boots from.
KERNEL_CONFIG=${KERNEL_CONFIG:-}
OUT="$ROOT/build/out"
CACHE="$ROOT/build/cache"
UBOOT="$ROOT/external/u-boot"
ATF="$ROOT/external/arm-trusted-firmware"
mkdir -p "$OUT" "$CACHE"

# --- reproducible builds ----------------------------------------------------
# With SOURCE_DATE_EPOCH set (release/build-all.sh: the commit date) nothing
# below embeds the wall clock or the checkout's path. U-Boot reads the variable
# itself (its Makefile writes timestamp.h from it), and so does its mkimage for
# the FIT's timestamp (tools/imagetool.c, imagetool_get_source_date); the rest
# is set here. Unset, everything behaves as before.
if [ -n "${SOURCE_DATE_EPOCH:-}" ]; then
  # TF-A: its Makefile has BUILD_MESSAGE_TIMESTAMP ?= __TIME__", "__DATE__ and
  # wants a C string, quotes included - the same shape as the default.
  BUILD_MESSAGE_TIMESTAMP="\"$(LC_ALL=C date -u -d "@$SOURCE_DATE_EPOCH" '+%T, %b %e %Y')\""
  # kernel: the uname line "#1 SMP <date>" and its user@host. The "#1" would
  # otherwise count up on every build in a cached tree (scripts/build-version).
  KBUILD_BUILD_TIMESTAMP=$(LC_ALL=C date -u -d "@$SOURCE_DATE_EPOCH")
  KBUILD_BUILD_USER=h713 KBUILD_BUILD_HOST=h713-build KBUILD_BUILD_VERSION=1
  # modules: WARN_ON/BUG_ON in kernel headers put __FILE__ into .rodata, and for
  # an external module (M=) that is the header's absolute path - three of them
  # in aic8800_fdrv.ko. Map the tree away; in-tree code is relative already.
  KCFLAGS="-ffile-prefix-map=$ROOT/=${KCFLAGS:+ $KCFLAGS}"
  export BUILD_MESSAGE_TIMESTAMP KBUILD_BUILD_TIMESTAMP KBUILD_BUILD_USER KBUILD_BUILD_HOST KBUILD_BUILD_VERSION KCFLAGS
fi

# --- board profile ----------------------------------------------------------
# One directory per board, boards/<id>/board.env (doku/121 §3). It sets BOARD_ID STATUS PROFILE IMAGE_NAME KERNEL_DTB
# UBOOT_BOARD (and, for cstenger's boards, the defconfig names they use today).
# KERNEL_DTB is the reason this is read here: which device tree a board boots
# is a property of the board, not of the release. The boards live next to
# mainline/, i.e. in the repository root, which is the parent of ROOT.
BOARDS_DIR=${BOARDS_DIR:-${BOARDS:-$ROOT/../boards}}
# The two names this script knew before stage 4 are cstenger's boards.
case "$BOARD" in
  ddr3)   BOARD=hy200-qz713df-a1 ;;   # cstenger's bench board (alias kept)
  lpddr3) BOARD=hy200-qz713-v2 ;;     # cstenger's projector (alias kept)
esac
BOARD_ENV="$BOARDS_DIR/$BOARD/board.env"
if [ ! -f "$BOARD_ENV" ]; then
  { echo "error: unknown board '$BOARD': there is no $BOARD_ENV"
    if [ -d "$BOARDS_DIR" ]; then
      echo "       known boards: $(cd "$BOARDS_DIR" && ls -d -- */ 2>/dev/null | tr -d / | tr '\n' ' ')"
    else
      echo "       there is no boards/ directory at $BOARDS_DIR"
    fi
    echo "       aliases:      ddr3 = hy200-qz713df-a1, lpddr3 = hy200-qz713-v2"
    echo "       a new board starts from an h713_probe log -- see boards/README.md"; } >&2
  exit 2
fi
grep -q '^KERNEL_DTB=' "$BOARD_ENV" ||
  { echo "error: $BOARD_ENV sets no KERNEL_DTB (empty is allowed, missing is not)" >&2; exit 2; }
unset CRUST_DEFCONFIG    # a board key only: never from the caller's environment
# shellcheck source=/dev/null
source "$BOARD_ENV"
[ "${BOARD_ID:-}" = "$BOARD" ] ||
  { echo "error: $BOARD_ENV says BOARD_ID='${BOARD_ID:-}', not '$BOARD'" >&2; exit 2; }
# A variant (boards/README.md, "Variants") overrides what its variant.env sets, DRAM_CLK above all.
DRAM_CLK=
if [ -n "$VARIANT" ]; then
  VARIANT_ENV="$BOARDS_DIR/$BOARD/variants/$VARIANT/variant.env"
  case " ${VARIANTS:-} " in
    *" $VARIANT "*) [ -f "$VARIANT_ENV" ] ||
                      { echo "error: no $VARIANT_ENV" >&2; exit 2; } ;;
    *) echo "error: board '$BOARD' has no variant '$VARIANT' (VARIANTS='${VARIANTS:-}')" >&2; exit 2 ;;
  esac
  want=$VARIANT
  # shellcheck source=/dev/null
  source "$VARIANT_ENV"
  [ "${VARIANT:-}" = "$want" ] ||
    { echo "error: $VARIANT_ENV says VARIANT='${VARIANT:-}', not '$want'" >&2; exit 2; }
fi
# board.env may name its own defconfigs (cstenger's boards do); otherwise the
# kernel defconfig comes from config/versions.env and the U-Boot one is the
# board's base defconfig <UBOOT_BOARD>_defconfig (base + role fragment, E3b).
UBOOT_DEFCONFIG=${UBOOT_DEFCONFIG:-${UBOOT_BOARD:?board.env: UBOOT_BOARD is empty}_defconfig}

log()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
note() { printf '    \033[33m%s\033[0m\n' "$*"; }
have() { [ -e "$ROOT/external/u-boot/Makefile" ] || { echo "error: submodules not checked out - run: git submodule update --init" >&2; exit 1; }; }

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

kernel_inputs_digest() {
  local p
  {
    # Only the KERNEL_* pins, not the whole file: versions.env is shared with
    # TF-A, U-Boot and the AIC8800 driver, and hashing it wholesale meant an
    # unrelated pin bump (e.g. AIC8800_COMMIT) silently invalidated every cached
    # kernel tree and forced a full rebuild. Matching on the prefix rather than
    # naming variables means a new KERNEL_* pin is covered automatically.
    printf 'versions.env %s\n' \
      "$(grep '^KERNEL_' "$ROOT/config/versions.env" | sha256sum | awk '{print $1}')"
    printf 'series %s\n' "$(hash_file "$ROOT/patches/kernel/series")"
    printf 'defconfig %s\n' "$(hash_file "$ROOT/patches/kernel/board/$KERNEL_DEFCONFIG")"
    for p in ${KERNEL_CONFIG//,/ }; do
      printf 'fragment %s %s\n' "$p" "$(hash_file "$ROOT/patches/kernel/board/$p.config")"
    done
    while IFS= read -r p || [ -n "$p" ]; do
      case "$p" in ''|'#'*) continue ;; esac   # blank or section comment
      printf '%s %s\n' "$p" "$(hash_file "$ROOT/patches/kernel/$p")"
    done < "$ROOT/patches/kernel/series"
  } | sha256sum | awk '{print $1}'
}

verify_kernel_tarball() {
  local tarball="$1"
  printf '%s  %s\n' "$KERNEL_TARBALL_SHA256" "$tarball" |
    sha256sum --check --status
}

# --- TF-A BL31 --------------------------------------------------------------
# PSCI SYSTEM_SUSPEND (the standby through crust) only when asked for with H713_STANDBY=1
# (release/build-all.sh --standby), and only for a board that names a crust build and is
# verified (board.env CRUST_DEFCONFIG, STATUS=verified) - or for a test image of such a board
# (H713_TEST_IMAGE=1 from build-all.sh --test-image). TF-A does not track a changed flag,
# so the build directory goes when the flag differs from the last build's.
build_bl31() {
  have
  local suspend=0 flag="$ATF/build/.h713-system-suspend"
  if [ "${H713_STANDBY:-0}" = 1 ]; then
    [ -n "${CRUST_DEFCONFIG:-}" ] && { [ "${STATUS:-}" = verified ] || [ "${H713_TEST_IMAGE:-0}" = 1 ]; } ||
      { echo "error: H713_STANDBY=1, but board '$BOARD' names no CRUST_DEFCONFIG or is neither verified nor a test image" >&2; return 1; }
    suspend=1
  fi
  [ "$(cat "$flag" 2>/dev/null)" = "$suspend" ] || rm -rf "$ATF/build/$ATF_PLAT"
  log "TF-A BL31  (PLAT=$ATF_PLAT, BL31_IN_DRAM=1, SUNXI_SYSTEM_SUSPEND=$suspend)"
  make -C "$ATF" -j"$JOBS" \
    PLAT="$ATF_PLAT" DEBUG=0 BL31_IN_DRAM=1 SUNXI_SYSTEM_SUSPEND="$suspend" \
    CC=clang LD=ld.lld AR=llvm-ar OC=llvm-objcopy OD=llvm-objdump \
    NM=llvm-nm READELF=llvm-readelf \
    CFLAGS='-Wno-error=deprecated-non-prototype -fno-stack-protector' bl31
  echo "$suspend" > "$flag"
  install -m 0644 "$ATF/build/$ATF_PLAT/release/bl31.bin" "$OUT/bl31.bin"
  log "bl31.bin -> $OUT/bl31.bin ($(stat -c%s "$OUT/bl31.bin") bytes)"
}

# --- U-Boot (embeds BL31) ---------------------------------------------------
uboot_make() {
  local O="$1"; shift
  make -C "$UBOOT" O="$O" \
    ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu' \
    LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump \
    READELF=llvm-readelf STRIP=llvm-strip \
    KAFLAGS=-fintegrated-as \
    KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector' \
    BL31="$OUT/bl31.bin" "$@"
}
build_uboot() {
  have
  [ -f "$OUT/bl31.bin" ] || build_bl31
  # Same guard as build/uboot-build.sh: this U-Boot needs the address-free HDCP 1.4 service.
  if grep -qs H713_SIP_HDCP14_STAGE "$UBOOT/arch/arm/mach-sunxi/h713_hdcp14.c" &&
     ! grep -qaF "key set from the stage" "$OUT/bl31.bin"; then
    echo "$OUT/bl31.bin has no address-free HDCP 1.4 service, which this U-Boot needs - run: build/build.sh bl31" >&2
    return 1
  fi
  local name="$BOARD${VARIANT:+-$VARIANT}"
  local O="$ROOT/build/uboot-$name"
  log "U-Boot  ($UBOOT_DEFCONFIG${DRAM_CLK:+ + DRAM $DRAM_CLK MHz}, board=$BOARD${VARIANT:+ variant $VARIANT})"
  uboot_make "$O" "$UBOOT_DEFCONFIG"
  if [ -n "$DRAM_CLK" ]; then      # the variant's clock, merged as build/uboot-build.sh does
    printf 'CONFIG_DRAM_CLK=%s\n' "$DRAM_CLK" > "$O/h713_dram_clk.config"
    "$UBOOT/scripts/kconfig/merge_config.sh" -m -O "$O" "$O/.config" "$O/h713_dram_clk.config" >/dev/null
    uboot_make "$O" olddefconfig
    grep -qx "CONFIG_DRAM_CLK=$DRAM_CLK" "$O/.config" ||
      { echo "error: CONFIG_DRAM_CLK=$DRAM_CLK did not survive olddefconfig" >&2; return 1; }
  fi
  uboot_make "$O" -j"$JOBS"
  install -m 0644 "$O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-sunxi-with-spl-$name.bin"
  log "image -> $OUT/u-boot-sunxi-with-spl-$name.bin ($(stat -c%s "$OUT/u-boot-sunxi-with-spl-$name.bin") bytes)"
}

# --- Kernel (mainline tarball + patches/kernel) -----------------------------
prepare_kernel() {
  local digest tree
  digest=$(kernel_inputs_digest)
  tree="$ROOT/build/linux-$KERNEL_VERSION-$digest"
  local tarball="$CACHE/linux-$KERNEL_VERSION.tar.xz"
  if [ -f "$tree/.h713-inputs-$digest" ]; then echo "$tree"; return; fi
  if [ -e "$tree" ]; then
    echo "error: incomplete kernel tree exists at $tree; remove it and retry" >&2
    return 1
  fi

  if [ -f "$tarball" ]; then
    verify_kernel_tarball "$tarball" || {
      echo "error: checksum mismatch for $tarball; remove it and retry" >&2
      return 1
    }
  else
    local partial="$tarball.part"
    log "fetch linux-$KERNEL_VERSION" >&2
    curl --fail --location --retry 3 --output "$partial" "$KERNEL_TARBALL_URL"
    verify_kernel_tarball "$partial" || {
      rm -f "$partial"
      echo "error: downloaded linux-$KERNEL_VERSION tarball failed SHA-256 verification" >&2
      return 1
    }
    mv "$partial" "$tarball"
  fi

  local tmp
  tmp=$(mktemp -d "$ROOT/build/.linux-$KERNEL_VERSION.XXXXXX")
  log "extract + patch linux-$KERNEL_VERSION" >&2
  tar -C "$tmp" --strip-components=1 -xf "$tarball"
  local n=0 p
  while read -r p; do
    case "$p" in ''|'#'*) continue ;; esac   # blank or section comment
    if ! patch -s -d "$tmp" -p1 < "$ROOT/patches/kernel/$p"; then
      rm -rf "$tmp"
      return 1
    fi
    n=$((n+1))
  done < "$ROOT/patches/kernel/series"
  # our arm64 defconfig (the R-CCU arm64 enable is patch 0023; see patches/kernel/README.md)
  cp "$ROOT/patches/kernel/board/$KERNEL_DEFCONFIG" "$tmp/arch/arm64/configs/"
  : > "$tmp/.h713-inputs-$digest"
  mv "$tmp" "$tree"
  note "applied $n series patches + arm64 defconfig" >&2
  echo "$tree"
}
# locate a mkimage: MKIMAGE= if given, else one the U-Boot stage already built, else build tools-only from
# the U-Boot submodule; a checkout without the submodule (a package worktree) takes the system's mkimage
# (the container has /usr/bin/mkimage) - never the release path, which builds U-Boot first (TODO 5.21)
find_mkimage() {
  local m
  [ -n "${MKIMAGE:-}" ] && { [ -x "$MKIMAGE" ] && echo "$MKIMAGE"; return; }
  for m in "$ROOT"/build/uboot-*/tools/mkimage; do [ -x "$m" ] && { echo "$m"; return; }; done
  m="$ROOT/build/uboot-tools/tools/mkimage"
  if [ ! -x "$m" ] && [ -e "$UBOOT/Makefile" ]; then
    log "building mkimage (u-boot tools-only)" >&2
    make -C "$UBOOT" O="$ROOT/build/uboot-tools" HOSTCC=clang tools-only_defconfig >/dev/null 2>&1
    make -C "$UBOOT" O="$ROOT/build/uboot-tools" HOSTCC=clang -j"$JOBS" tools-only >/dev/null 2>&1
  fi
  [ -x "$m" ] && { echo "$m"; return; }
  [ -e "$UBOOT/Makefile" ] && return    # the submodule is there and did not build: that is an error, not a fallback
  m=$(command -v mkimage) || return
  note "no U-Boot submodule in this checkout: the system's $m packs the FIT" >&2
  echo "$m"
}

build_kernel() {
  [ -n "$KERNEL_DTB" ] || {
    echo "error: board '$BOARD' (STATUS=${STATUS:-?}) has no device tree of ours -- boards/$BOARD/board.env" >&2
    echo "       leaves KERNEL_DTB empty, so no FIT may be built for it. bl31 and uboot do work." >&2
    return 1
  }
  local tree; tree=$(prepare_kernel)
  local suffix=""
  [ -n "$KERNEL_CONFIG" ] && suffix="-${KERNEL_CONFIG//,/-}"
  log "Linux kernel  ($KERNEL_DEFCONFIG${KERNEL_CONFIG:+ + $KERNEL_CONFIG}, arch=$KERNEL_ARCH)"
  make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 "$KERNEL_DEFCONFIG"
  for frag in ${KERNEL_CONFIG//,/ }; do
    local path="$ROOT/patches/kernel/board/$frag.config"
    [ -f "$path" ] || { echo "error: no config fragment: $path" >&2; return 1; }
    ARCH="$KERNEL_ARCH" "$tree/scripts/kconfig/merge_config.sh" -m -O "$tree" \
      "$tree/.config" "$path" >/dev/null
  done
  if [ -n "$KERNEL_CONFIG" ]; then
    make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 olddefconfig
    # merge_config warns about a request it could not honour, but olddefconfig
    # can drop a symbol afterwards for an unmet dependency and say nothing.
    # Check the config that was BUILT, not the one that was asked for: a KASAN
    # kernel that silently did not enable KASAN is worse than no kernel at all,
    # because every clean run after it reads as evidence.
    local want missing=""
    for frag in ${KERNEL_CONFIG//,/ }; do
      while IFS= read -r want || [ -n "$want" ]; do
        case "$want" in
          ''|'#'*' is not set') ;;      # a real request to disable; check it
          '#'*|'') continue ;;          # ordinary comment or blank
        esac
        grep -F -x -q -- "$want" "$tree/.config" || missing="$missing$(printf '\n      %s' "$want")"
      done < "$ROOT/patches/kernel/board/$frag.config"
    done
    [ -z "$missing" ] || {
      printf 'error: config fragment did not survive olddefconfig:%s\n' "$missing" >&2
      return 1
    }
  fi
  make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 -j"$JOBS" Image dtbs modules
  # -n: no mtime and no name in the gzip header (the kernel's own Image.gz
  # target does the same); with them two builds' FITs never matched.
  gzip -9 -n -kf "$tree/arch/arm64/boot/Image"
  install -m 0644 "$tree/arch/arm64/boot/Image.gz" "$OUT/Image$suffix.gz"
  # The board's own DTB (board.env) plus cstenger's two HY200 DTBs, which stay
  # in the output so his bench runs keep working and a regression there is
  # still visible. 'make dtbs' builds every DTB in the Makefile anyway; this
  # only decides what lands in build/out.
  local dtb dtbs=("$KERNEL_DTB")
  for dtb in "$KERNEL_DTB_BENCH" "$KERNEL_DTB_PROJECTOR"; do
    # BOARD=ddr3/lpddr3: the board DTB *is* one of the two; install it once.
    case " ${dtbs[*]} " in *" $dtb "*) continue ;; esac
    dtbs+=("$dtb")
  done
  for dtb in "${dtbs[@]}"; do
    install -m 0644 "$tree/arch/arm64/boot/dts/allwinner/$dtb.dtb" "$OUT/$dtb.dtb"
  done
  log "Image$suffix.gz -> $OUT/Image$suffix.gz ($(stat -c%s "$OUT/Image$suffix.gz") bytes); DTBs: $KERNEL_DTB (board $BOARD) + bench + projector"
  build_kernel_fit "$suffix"
}

# --- AIC8800 WiFi/BT out-of-tree modules (SDIO WiFi + UART BT) ---------------
# Source is a pinned radxa-pkg/aic8800 tarball, not vendored: their debian/
# patches are applied to the whole repo first (they patch PCIE/SDIO/USB in the
# same hunks), then the SDIO subtree is extracted and patches/aic8800/ applied
# on top. See patches/aic8800/README.md.
aic8800_inputs_digest() {
  local p
  {
    printf 'commit %s\n' "$AIC8800_COMMIT"
    printf 'series %s\n' "$(hash_file "$ROOT/patches/aic8800/series")"
    while IFS= read -r p || [ -n "$p" ]; do
      case "$p" in ''|'#'*) continue ;; esac   # blank or section comment
      printf '%s %s\n' "$p" "$(hash_file "$ROOT/patches/aic8800/$p")"
    done < "$ROOT/patches/aic8800/series"
  } | sha256sum | awk '{print $1}'
}

verify_aic8800_tarball() {
  printf '%s  %s\n' "$AIC8800_TARBALL_SHA256" "$1" | sha256sum --check --status
}

prepare_aic8800() {
  local digest tree tarball
  digest=$(aic8800_inputs_digest)
  tree="$ROOT/build/aic8800-${AIC8800_COMMIT:0:12}-$digest"
  tarball="$CACHE/aic8800-${AIC8800_COMMIT:0:12}.tar.gz"
  if [ -f "$tree/.h713-inputs-$digest" ]; then echo "$tree"; return; fi
  if [ -e "$tree" ]; then
    echo "error: incomplete aic8800 tree exists at $tree; remove it and retry" >&2
    return 1
  fi

  if [ -f "$tarball" ]; then
    verify_aic8800_tarball "$tarball" || {
      echo "error: checksum mismatch for $tarball; remove it and retry" >&2
      return 1
    }
  else
    local partial="$tarball.part"
    log "fetch aic8800 ${AIC8800_COMMIT:0:12}" >&2
    curl --fail --location --retry 3 --output "$partial" "$AIC8800_TARBALL_URL"
    verify_aic8800_tarball "$partial" || {
      rm -f "$partial"
      echo "error: downloaded aic8800 tarball failed SHA-256 verification" >&2
      return 1
    }
    mv "$partial" "$tarball"
  fi

  local tmp; tmp=$(mktemp -d "$ROOT/build/.aic8800.XXXXXX")
  log "extract + patch aic8800 (vendor series, then ours)" >&2
  tar -C "$tmp" --strip-components=1 -xf "$tarball" \
    "aic8800-$AIC8800_COMMIT/src" "aic8800-$AIC8800_COMMIT/debian"

  # Vendor's own kernel-compat series. Failures are only tolerated for the
  # names pinned in AIC8800_VENDOR_PATCH_SKIP; anything else stops the build.
  local n=0 skipped=0 p
  while IFS= read -r p || [ -n "$p" ]; do
    [ -n "$p" ] || continue
    if patch -s -d "$tmp" -p1 --no-backup-if-mismatch < "$tmp/debian/patches/$p" >/dev/null 2>&1; then
      n=$((n+1))
    elif [[ " $AIC8800_VENDOR_PATCH_SKIP " == *" $p "* ]]; then
      skipped=$((skipped+1))
    else
      rm -rf "$tmp"
      echo "error: vendor patch failed unexpectedly: $p" >&2
      echo "       if this is expected after a bump, add it to AIC8800_VENDOR_PATCH_SKIP" >&2
      return 1
    fi
  done < "$tmp/debian/patches/series"
  note "vendor series: $n applied, $skipped skipped (expected)" >&2

  # Keep only the SDIO driver. A throwaway git repo makes the base blobs
  # available so our series applies with real three-way merge instead of
  # context matching -- which is what makes the next upstream bump survivable.
  local sub="$tmp/$AIC8800_SUBTREE"
  [ -d "$sub" ] || { rm -rf "$tmp"; echo "error: subtree missing: $AIC8800_SUBTREE" >&2; return 1; }
  local stage; stage=$(mktemp -d "$ROOT/build/.aic8800-sdio.XXXXXX")
  cp -a "$sub/." "$stage/"
  rm -rf "$tmp"
  git -C "$stage" init -q
  git -C "$stage" add -A
  git -C "$stage" -c user.email=build@h713 -c user.name=h713 commit -qm \
    "aic8800 vendor $AIC8800_COMMIT + vendor compat series"
  local m=0
  while IFS= read -r p || [ -n "$p" ]; do
    case "$p" in ''|'#'*) continue ;; esac   # blank or section comment
    if ! git -C "$stage" -c user.email=build@h713 -c user.name=h713 \
           am -3 --keep-non-patch "$ROOT/patches/aic8800/$p" >/dev/null 2>&1; then
      git -C "$stage" am --abort >/dev/null 2>&1 || true
      echo "error: patches/aic8800/$p did not apply (three-way merge failed)" >&2
      echo "       tree left at $stage for inspection" >&2
      return 1
    fi
    m=$((m+1))
  done < "$ROOT/patches/aic8800/series"
  note "aic8800 series: $m patches applied" >&2

  : > "$stage/.h713-inputs-$digest"
  mv "$stage" "$tree"
  echo "$tree"
}

# Built against the same pinned kernel tree with the same arm64/LLVM toolchain.
# bsp first, then fdrv/btlpm with bsp's Module.symvers (they export/import
# symbols). CONFIG_PLATFORM_MAINLINE_SUNXI=y selects the H713 platform glue.
build_aic8800() {
  local tree; tree=$(prepare_kernel)
  [ -f "$tree/Module.symvers" ] || {
    echo "error: kernel not built (no Module.symvers in $tree) - run build/build.sh kernel first" >&2
    return 1
  }
  local moddir; moddir=$(prepare_aic8800)
  local common=(ARCH=arm64 LLVM=1 CONFIG_PLATFORM_MAINLINE_SUNXI=y)
  log "AIC8800 modules (SDIO WiFi + UART BT, arch=arm64)"
  make -C "$tree" M="$moddir/aic8800_bsp" "${common[@]}" modules
  local bsp_syms="$moddir/aic8800_bsp/Module.symvers"
  make -C "$tree" M="$moddir/aic8800_fdrv"  "${common[@]}" KBUILD_EXTRA_SYMBOLS="$bsp_syms" modules
  make -C "$tree" M="$moddir/aic8800_btlpm" "${common[@]}" KBUILD_EXTRA_SYMBOLS="$bsp_syms" modules
  install -d "$OUT/modules"
  install -m 0644 \
    "$moddir/aic8800_bsp/aic8800_bsp.ko" \
    "$moddir/aic8800_fdrv/aic8800_fdrv.ko" \
    "$moddir/aic8800_btlpm/aic8800_btlpm.ko" \
    "$OUT/modules/"
  log "modules -> $OUT/modules/ (aic8800_bsp, aic8800_fdrv, aic8800_btlpm)"
  note "Firmware (blob) is pinned + installed into the rootfs by tools/rootfs/, not here."
}

# package Image.gz + DTB into a bootable FIT (bootm at KERNEL_LOAD)
build_kernel_fit() {
  local suffix=${1:-}
  local mkimage; mkimage=$(find_mkimage)
  [ -n "$mkimage" ] || { note "no mkimage - skipping FIT (install u-boot-tools or run the uboot stage)"; return; }
  cat > "$OUT/h713-kernel$suffix.its" <<ITS
/dts-v1/;
/ {
	description = "H713 arm64 kernel ($KERNEL_VERSION$suffix) + DTB ($BOARD)";
	#address-cells = <1>;
	images {
		kernel {
			description = "Linux $KERNEL_VERSION";
			data = /incbin/("$OUT/Image$suffix.gz");
			type = "kernel";
			arch = "arm64";
			os = "linux";
			compression = "gzip";
			load = <$KERNEL_LOAD>;
			entry = <$KERNEL_LOAD>;
			hash-1 {
				algo = "sha256";
			};
		};
		fdt-1 {
			description = "$KERNEL_DTB";
			data = /incbin/("$OUT/$KERNEL_DTB.dtb");
			type = "flat_dt";
			arch = "arm64";
			compression = "none";
			hash-1 {
				algo = "sha256";
			};
		};
	};
	configurations {
		default = "conf-$KERNEL_DTB";
		conf-$KERNEL_DTB {
			description = "$BOARD ($KERNEL_DTB)";
			kernel = "kernel";
			fdt = "fdt-1";
		};
	};
};
ITS
  # The FIT's timestamp is SOURCE_DATE_EPOCH when set, else the time of the run
  # (tools/imagetool.c). mkimage -t is not that knob: it re-stamps an existing FIT.
  "$mkimage" -f "$OUT/h713-kernel$suffix.its" "$OUT/h713-kernel$suffix.fit" >/dev/null
  log "FIT -> $OUT/h713-kernel$suffix.fit ($(stat -c%s "$OUT/h713-kernel$suffix.fit") bytes)"
  note "Boot: load to DRAM + 'bootm' (arch=arm64, load $KERNEL_LOAD). See docs/flash.md."
}

# --- Images / summary -------------------------------------------------------
build_images() {
  local files=(bl31.bin Image.gz "$KERNEL_DTB.dtb" h713-kernel.fit)
  local image dtb
  for dtb in "$KERNEL_DTB_BENCH" "$KERNEL_DTB_PROJECTOR"; do
    case " ${files[*]} " in *" $dtb.dtb "*) continue ;; esac
    files+=("$dtb.dtb")
  done
  for image in "$OUT"/u-boot-sunxi-with-spl-*.bin; do
    [ -f "$image" ] && files+=("${image##*/}")
  done
  for image in "${files[@]}"; do
    [ -f "$OUT/$image" ] || {
      echo "error: missing $OUT/$image; run build/build.sh all first" >&2
      return 1
    }
  done
  log "Artifacts in $OUT"
  ls -la "$OUT" 2>/dev/null || true
  (
    cd "$OUT"
    sha256sum "${files[@]}" > SHA256SUMS
  )
  note "SHA-256 manifest -> $OUT/SHA256SUMS"
  note "Flash U-Boot to eMMC sector 16 using a verified raw write - see docs/flash.md."
}

case "${1:-all}" in
  bl31)    build_bl31 ;;
  uboot)   build_uboot ;;
  kernel)  build_kernel ;;
  aic8800) build_aic8800 ;;
  images)  build_images ;;
  all)     build_bl31; build_uboot; build_kernel; build_aic8800; build_images ;;
  *) echo "usage: $0 [all|bl31|uboot|kernel|aic8800|images]" >&2; exit 2 ;;
esac
