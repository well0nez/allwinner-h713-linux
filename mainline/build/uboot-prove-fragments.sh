#!/usr/bin/env bash
# build/uboot-prove-fragments.sh -- equivalence proof for the HY310 U-Boot
# defconfig matrix (docs/uboot/README.md "Which defconfig").
#
# For each role: the old single defconfig, and hy310_defconfig + the role
# fragment merged the way build/uboot-build.sh merges it, must expand to the
# same .config.
#
# The old defconfigs are deleted in the same commit that adds the fragments,
# so they are fetched back out of git for the length of the run -- from the
# parent of whichever commit deleted them -- and removed again at the end.
#
# Two differences are intended and are normalised away here: the base names
# the board's own device tree and the old defconfigs named the bench board's,
# so CONFIG_DEFAULT_DEVICE_TREE differs, and CONFIG_OF_LIST with it because
# its default is the default device tree; and the installer role's boot
# message is English now. Every other difference is a failure.
#
# Config targets only: no cross toolchain, no compile, nothing written outside
# the work directory (build/uboot-proof/, ignored by git). Runs on the host or
# in the container. Usage: build/uboot-prove-fragments.sh [u-boot-dir] [work-dir]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UBOOT=${1:-$ROOT/external/u-boot}
WORK=${2:-$ROOT/build/uboot-proof}
MAKE=(make -C "$UBOOT" ARCH=arm HOSTCC=cc)
OLD_DT=allwinner/sun50i-h713-hy200-qz713df-a1
NEW_DT=allwinner/sun50i-h713-hy310
ROLES="release:hy310_qz713_v3_1 installer:hy310_installer
       netboot:hy310_netboot netboot_gate:hy310_netboot_gate
       felmmc:hy310_felmmc host:hy310_host"

restored=()
cleanup() { for f in ${restored+"${restored[@]}"}; do rm "$f"; done; }
trap cleanup EXIT

mkdir -p "$WORK"
rc=0
printf '%-30s %-34s %s\n' "old defconfig" "base + fragment" "result"
for pair in $ROLES; do
	role=${pair%%:*}; old=${pair#*:}_defconfig
	ref=$WORK/ref-$role; new=$WORK/new-$role
	mkdir -p "$ref" "$new"

	if [ ! -f "$UBOOT/configs/$old" ]; then
		gone=$(git -C "$UBOOT" log --diff-filter=D --format=%H -1 \
			-- "configs/$old")
		[ -n "$gone" ] || { echo "$old: not in the tree and never deleted" >&2; exit 1; }
		git -C "$UBOOT" show "$gone^:configs/$old" > "$UBOOT/configs/$old"
		restored+=("$UBOOT/configs/$old")
	fi

	"${MAKE[@]}" O="$ref" "$old"          >/dev/null
	"${MAKE[@]}" O="$new" hy310_defconfig >/dev/null
	"$UBOOT"/scripts/kconfig/merge_config.sh -m -O "$new" \
		"$new/.config" "$UBOOT/configs/fragments/h713_$role.config" \
		>"$WORK/merge-$role.log" 2>&1
	"${MAKE[@]}" O="$new" olddefconfig >/dev/null
	sed -i "s|$NEW_DT|$OLD_DT|" "$new/.config"
	# The second intended difference: stage 3 put the installer role's boot
	# message into English (fragment h713_installer.config); the defconfig it
	# replaced still carries the German one. Same command, other words.
	sed -i 's|echo H713 installer: exposing the eMMC as a USB drive; ums 0 mmc 1|echo HY310 installer: eMMC wird als USB-Laufwerk freigegeben; ums 0 mmc 1|' "$new/.config"

	if diff -u "$ref/.config" "$new/.config" >"$WORK/diff-$role.txt"; then
		verdict=identical
	else
		verdict="DIFFERENT -- $WORK/diff-$role.txt"
		rc=1
	fi
	printf '%-30s %-34s %s\n' "$old" "hy310_defconfig + h713_$role" "$verdict"
done
[ $rc -eq 0 ] && echo "all six identical (device tree normalised)"
exit $rc
