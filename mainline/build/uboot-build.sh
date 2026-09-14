#!/usr/bin/env bash
# Quick single-target U-Boot build helper (clang/lld).
# For the full BL31 -> U-Boot -> kernel -> images flow use build/build.sh.
#
# Usage: build/uboot-build.sh <O-dir> <board-base> [role] [make-target...]
#   board-base  hy310 | hy200_qz713df_a1 | h713_probe | ... ("_defconfig" optional)
#   role        release | installer | netboot | netboot_gate | felmmc | host
#               -- configs/fragments/h713_<role>.config, merged on top of the
#               base and resolved with olddefconfig. Omit it for a base-only
#               build; a third argument that is not a role is a make target,
#               so the old two-argument calls still work.
# Needs: swig (in-tree dtc + pylibfdt). -fintegrated-as = clang's assembler.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
O="$1"; BASE="${2%_defconfig}"; shift 2
UBOOT="${UBOOT_SRC:-$ROOT/external/u-boot}"   # UBOOT_SRC: build another checkout (proofs, bisects)
BL31="$ROOT/build/out/bl31.bin"
ROLE=""
[ $# -gt 0 ] && [ -f "$UBOOT/configs/fragments/h713_$1.config" ] && { ROLE="$1"; shift; }
[ -f "$BL31" ] || { echo "missing $BL31 — run: build/build.sh bl31" >&2; exit 1; }
F=(ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu'
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump
  READELF=llvm-readelf STRIP=llvm-strip
  KAFLAGS=-fintegrated-as
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector'
  BL31="$BL31")
make -C "$UBOOT" O="$O" "${F[@]}" "${BASE}_defconfig" >/dev/null 2>&1 || { echo DEFCONFIG_FAIL; exit 1; }
if [ -n "$ROLE" ]; then
	"$UBOOT/scripts/kconfig/merge_config.sh" -m -O "$O" \
		"$O/.config" "$UBOOT/configs/fragments/h713_$ROLE.config" >/dev/null ||
		{ echo FRAGMENT_FAIL; exit 1; }
	make -C "$UBOOT" O="$O" "${F[@]}" olddefconfig >/dev/null 2>&1 ||
		{ echo OLDDEFCONFIG_FAIL; exit 1; }
fi
make -C "$UBOOT" O="$O" "${F[@]}" -j"$(nproc)" "$@"
