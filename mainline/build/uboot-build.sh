#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 well0nez
#
# mainline/build/uboot-build.sh - one U-Boot of the project: a base defconfig, optionally a role
# fragment and a DRAM clock over it, built with the LLVM toolchain against build/out/bl31.bin.
# Written anew in October 2026 from a functional specification alone (SPEC.md of the licence
# rework, 13.10.2026), without the text of the script that stood here before.
#
#   build/uboot-build.sh O BASE [ROLE] [MAKE-TARGET ...]
#
#   O       the U-Boot output directory (made absolute against the caller's directory; not
#           emptied - callers that want a clean build remove it first)
#   BASE    the base defconfig, with or without _defconfig (hy310, h713_probe_defconfig, ...)
#   ROLE    the third argument is a role exactly when configs/fragments/h713_<ROLE>.config
#           exists in the U-Boot tree (release, installer, netboot, ...); otherwise it is the
#           first make target
#   MAKE-TARGET  for the final make; none = U-Boot's default target
#
# Environment: DRAM_CLK (MHz, laid over base and role), SCP (a file, U-Boot's SCP=, crust in the
# FIT), UBOOT_SRC (another U-Boot checkout; default external/u-boot), JOBS, SOURCE_DATE_EPOCH
# (passed through; U-Boot and its mkimage read it themselves).
#
# Base and role are joined the way build/uboot-prove-fragments.sh proves them: the base
# defconfig, then merge_config.sh -m with the fragments, then olddefconfig.

set -euo pipefail
shopt -s inherit_errexit

bdir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
mdir=$(dirname -- "$bdir")

fail() { printf 'uboot-build.sh: %s\n' "$@" >&2; exit 1; }
absolute() { if [[ $1 == /* ]]; then printf '%s' "$1"; else printf '%s/%s' "$PWD" "$1"; fi; }

if (($# < 2)) || [[ -z $1 || -z $2 ]]; then
	printf 'usage: uboot-build.sh O BASE [ROLE] [MAKE-TARGET ...]\n' >&2
	exit 2
fi
odir=$(absolute "$1")
base=${2%_defconfig}
shift 2

src=$(absolute "${UBOOT_SRC:-$mdir/external/u-boot}")
[[ -f $src/Makefile ]] ||
	fail "no U-Boot tree at $src - git submodule update --init, or UBOOT_SRC=<checkout>"
role=
if (($#)) && [[ -n $1 && -f $src/configs/fragments/h713_$1.config ]]; then
	role=$1
	shift
fi
targets=("$@")

bl31=$mdir/build/out/bl31.bin
[[ -f $bl31 ]] || fail "no $bl31 - build it first: build/build.sh bl31"
scp=
if [[ -n ${SCP:-} ]]; then
	scp=$(absolute "$SCP")
	[[ -f $scp ]] || fail "SCP=$SCP is not a file"
fi

# A U-Boot that asks BL31 for the HDCP 1.4 key by stage (no address) needs a BL31 that offers
# that service; with an older bl31.bin it would boot without protected playback.
hdcp_src=$src/arch/arm/mach-sunxi/h713_hdcp14.c
if [[ -f $hdcp_src ]] && grep -q H713_SIP_HDCP14_STAGE "$hdcp_src"; then
	grep -qaF 'key set from the stage' "$bl31" ||
		fail "this U-Boot needs the address-free HDCP 1.4 service in BL31, and $bl31 does not have it" \
			"build bl31 again from the current TF-A: build/build.sh bl31"
fi

params=(
	O="$odir" ARCH=arm HOSTCC=clang CC="clang -target aarch64-linux-gnu"
	LD=ld.lld AR=llvm-ar NM=llvm-nm
	OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump READELF=llvm-readelf STRIP=llvm-strip
	KAFLAGS=-fintegrated-as KCFLAGS="-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector"
	BL31="$bl31"
)
[[ -n $scp ]] && params+=(SCP="$scp")

make -C "$src" -s "${params[@]}" "${base}_defconfig" ||
	fail "make ${base}_defconfig failed in $src"

# what goes over the base, in this order: the role, then the DRAM clock
fragments=()
[[ -n $role ]] && fragments+=("$src/configs/fragments/h713_$role.config")
if [[ -n ${DRAM_CLK:-} ]]; then
	printf 'CONFIG_DRAM_CLK=%s\n' "$DRAM_CLK" > "$odir/h713-dram-clk.config"
	fragments+=("$odir/h713-dram-clk.config")
fi
if ((${#fragments[@]})); then
	# merge_config.sh keeps its scratch files in the current directory: that is O
	(cd -- "$odir" && "$src/scripts/kconfig/merge_config.sh" -m -O "$odir" "$odir/.config" "${fragments[@]}") ||
		fail "merge_config.sh failed over $odir/.config"
	make -C "$src" -s "${params[@]}" olddefconfig || fail "make olddefconfig failed"
fi
if [[ -n ${DRAM_CLK:-} ]]; then
	grep -qxF "CONFIG_DRAM_CLK=$DRAM_CLK" "$odir/.config" ||
		fail "DRAM_CLK=$DRAM_CLK did not reach $odir/.config"
fi

printf 'uboot-build.sh: %s%s%s -> %s\n' "$base" "${role:+ + $role}" "${DRAM_CLK:+ + DRAM $DRAM_CLK MHz}" "$odir"
exec make -C "$src" -j"${JOBS:-$(nproc)}" "${params[@]}" "${targets[@]}"
