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
#   DRAM_CLK=<MHz> in the environment: a board variant's clock (boards/<id>/
#               variants/<v>/variant.env), merged after the role; the build
#               stops if the resolved .config does not carry it.
#   SCP=<file>  in the environment: crust, the FIT's "scp" loadable, which BL31
#               starts on the ARISC. release/build-all.sh sets it for the
#               release role only; the installer and the probe stay without.
# Needs: swig (in-tree dtc + pylibfdt). -fintegrated-as = clang's assembler.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
O="$1"; BASE="${2%_defconfig}"; shift 2
UBOOT="${UBOOT_SRC:-$ROOT/external/u-boot}"   # UBOOT_SRC: build another checkout (proofs, bisects)
BL31="$ROOT/build/out/bl31.bin"
ROLE=""
[ $# -gt 0 ] && [ -f "$UBOOT/configs/fragments/h713_$1.config" ] && { ROLE="$1"; shift; }
[ -f "$BL31" ] || { echo "missing $BL31 - run: build/build.sh bl31" >&2; exit 1; }
[ -z "${SCP:-}" ] || [ -f "$SCP" ] || { echo "missing SCP=$SCP" >&2; exit 1; }
# A U-Boot that talks to the address-free HDCP 1.4 service (TODO 6.1) needs a BL31 that
# has it. With an older bl31.bin the image boots, HDCP 1.4 gets SMC_UNK, and that looks
# like a fault on the device rather than a stale building block.
if grep -qs H713_SIP_HDCP14_STAGE "$UBOOT/arch/arm/mach-sunxi/h713_hdcp14.c" &&
   ! grep -qaF "key set from the stage" "$BL31"; then
	echo "$BL31 has no address-free HDCP 1.4 service, which this U-Boot needs - run: build/build.sh bl31" >&2
	exit 1
fi
F=(ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu'
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump
  READELF=llvm-readelf STRIP=llvm-strip
  KAFLAGS=-fintegrated-as
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector'
  BL31="$BL31")
[ -z "${SCP:-}" ] || F+=(SCP="$SCP")
make -C "$UBOOT" O="$O" "${F[@]}" "${BASE}_defconfig" >/dev/null 2>&1 || { echo DEFCONFIG_FAIL; exit 1; }
FRAGS=()
[ -n "$ROLE" ] && FRAGS+=("$UBOOT/configs/fragments/h713_$ROLE.config")
if [ -n "${DRAM_CLK:-}" ]; then
	printf 'CONFIG_DRAM_CLK=%s\n' "$DRAM_CLK" > "$O/h713_dram_clk.config"
	FRAGS+=("$O/h713_dram_clk.config")
fi
if [ ${#FRAGS[@]} -gt 0 ]; then
	"$UBOOT/scripts/kconfig/merge_config.sh" -m -O "$O" "$O/.config" "${FRAGS[@]}" >/dev/null ||
		{ echo FRAGMENT_FAIL; exit 1; }
	make -C "$UBOOT" O="$O" "${F[@]}" olddefconfig >/dev/null 2>&1 ||
		{ echo OLDDEFCONFIG_FAIL; exit 1; }
fi
[ -z "${DRAM_CLK:-}" ] || grep -qx "CONFIG_DRAM_CLK=$DRAM_CLK" "$O/.config" || { echo DRAM_CLK_FAIL; exit 1; }
make -C "$UBOOT" O="$O" "${F[@]}" -j"$(nproc)" "$@"
