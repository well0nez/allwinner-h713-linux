#!/usr/bin/env bash
# H713 firmware build orchestrator.
#
#   TF-A BL31  ->  U-Boot (SPL + BL31 + proper)  ->  Linux kernel  ->  images
#
# Sources are the git submodules under external/ and two curated patch series on
# pinned upstream tarballs — patches/kernel/ and patches/aic8800/ (see
# patches/README.md); versions are pinned in config/versions.env. LLVM-only
# (clang / ld.lld) — see config/toolchain.md.
#
# Usage:
#   build/build.sh [all|bl31|uboot|kernel|aic8800|images]   # default: all
#
# Env:
#   BOARD=ddr3|lpddr3   board profile (default ddr3): ddr3=HY200 QZ713DF_A1 bench, lpddr3=HY200 QZ713_V2 projector
#   JOBS=N              parallelism (default: nproc)
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=../config/versions.env
source "$ROOT/config/versions.env"

BOARD=${BOARD:-ddr3}
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

case "$BOARD" in
  ddr3)   UBOOT_DEFCONFIG=$UBOOT_DEFCONFIG_DDR3 ;;
  lpddr3) UBOOT_DEFCONFIG=$UBOOT_DEFCONFIG_LPDDR3 ;;
  *) echo "error: BOARD='$BOARD' must be ddr3 or lpddr3" >&2; exit 2 ;;
esac

log()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
note() { printf '    \033[33m%s\033[0m\n' "$*"; }
have() { [ -e "$ROOT/external/u-boot/Makefile" ] || { echo "error: submodules not checked out — run: git submodule update --init" >&2; exit 1; }; }

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
      [ -n "$p" ] || continue
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
build_bl31() {
  have
  log "TF-A BL31  (PLAT=$ATF_PLAT, BL31_IN_DRAM=1)"
  make -C "$ATF" -j"$JOBS" \
    PLAT="$ATF_PLAT" DEBUG=0 BL31_IN_DRAM=1 \
    CC=clang LD=ld.lld AR=llvm-ar OC=llvm-objcopy OD=llvm-objdump \
    NM=llvm-nm READELF=llvm-readelf \
    CFLAGS='-Wno-error=deprecated-non-prototype -fno-stack-protector' bl31
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
  local O="$ROOT/build/uboot-$BOARD"
  log "U-Boot  ($UBOOT_DEFCONFIG, board=$BOARD)"
  uboot_make "$O" "$UBOOT_DEFCONFIG"
  uboot_make "$O" -j"$JOBS"
  install -m 0644 "$O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-sunxi-with-spl-$BOARD.bin"
  log "image -> $OUT/u-boot-sunxi-with-spl-$BOARD.bin ($(stat -c%s "$OUT/u-boot-sunxi-with-spl-$BOARD.bin") bytes)"
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
    [ -n "$p" ] || continue
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
# locate a mkimage: prefer one the U-Boot stage already built, else build tools-only
find_mkimage() {
  local m
  for m in "$ROOT"/build/uboot-*/tools/mkimage; do [ -x "$m" ] && { echo "$m"; return; }; done
  m="$ROOT/build/uboot-tools/tools/mkimage"
  if [ ! -x "$m" ]; then
    log "building mkimage (u-boot tools-only)" >&2
    make -C "$UBOOT" O="$ROOT/build/uboot-tools" HOSTCC=clang tools-only_defconfig >/dev/null 2>&1
    make -C "$UBOOT" O="$ROOT/build/uboot-tools" HOSTCC=clang -j"$JOBS" tools-only >/dev/null 2>&1
  fi
  [ -x "$m" ] && echo "$m"
}

build_kernel() {
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
  gzip -9 -kf "$tree/arch/arm64/boot/Image"
  install -m 0644 "$tree/arch/arm64/boot/Image.gz" "$OUT/Image$suffix.gz"
  install -m 0644 "$tree/arch/arm64/boot/dts/allwinner/$KERNEL_DTB.dtb" "$OUT/$KERNEL_DTB.dtb"
  install -m 0644 "$tree/arch/arm64/boot/dts/allwinner/$KERNEL_DTB_PROJECTOR.dtb" \
    "$OUT/$KERNEL_DTB_PROJECTOR.dtb"
  log "Image$suffix.gz -> $OUT/Image$suffix.gz ($(stat -c%s "$OUT/Image$suffix.gz") bytes); bench + projector DTBs built"
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
      [ -n "$p" ] || continue
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
    [ -n "$p" ] || continue
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
    echo "error: kernel not built (no Module.symvers in $tree) — run build/build.sh kernel first" >&2
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
  [ -n "$mkimage" ] || { note "no mkimage — skipping FIT (install u-boot-tools or run the uboot stage)"; return; }
  cat > "$OUT/h713-kernel$suffix.its" <<ITS
/dts-v1/;
/ {
	description = "H713 arm64 kernel ($KERNEL_VERSION$suffix) + DTB";
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
		default = "conf-1";
		conf-1 {
			description = "H713 HY200";
			kernel = "kernel";
			fdt = "fdt-1";
		};
	};
};
ITS
  "$mkimage" -f "$OUT/h713-kernel$suffix.its" "$OUT/h713-kernel$suffix.fit" >/dev/null
  log "FIT -> $OUT/h713-kernel$suffix.fit ($(stat -c%s "$OUT/h713-kernel$suffix.fit") bytes)"
  note "Boot: load to DRAM + 'bootm' (arch=arm64, load $KERNEL_LOAD). See docs/flash.md."
}

# --- Images / summary -------------------------------------------------------
build_images() {
  local files=(bl31.bin Image.gz "$KERNEL_DTB.dtb" "$KERNEL_DTB_PROJECTOR.dtb" h713-kernel.fit)
  local image
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
  note "Flash U-Boot to eMMC sector 16 using a verified raw write — see docs/flash.md."
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
