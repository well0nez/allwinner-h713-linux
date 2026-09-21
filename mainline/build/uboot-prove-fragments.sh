#!/usr/bin/env bash
# build/uboot-prove-fragments.sh -- what each U-Boot role fragment does to its
# board's base defconfig, proven against the fork as it is today.
#
# Until stage 3 it held every role against the single defconfig it replaced.
# Those defconfigs are gone from the fork, so it had nothing left to compare
# and was red (O2, 16.09.2026). What is worth proving now is what fragments
# get wrong: Kconfig lowers a symbol when its dependencies stop being met but
# does not raise one back, so a fragment line can be swallowed without a word
# (docs/uboot/README.md, "fragments subtract reliably and add unreliably").
# Every role is merged the way build/uboot-build.sh merges it, every line of
# it has to survive, and the diff against the bare base says what it did.
#
# Config targets only: no cross toolchain, no compile, nothing outside the work
# directory (build/uboot-proof/, ignored by git). Host or container.
# Usage: build/uboot-prove-fragments.sh [u-boot-dir] [work-dir]
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UBOOT=${1:-$ROOT/external/u-boot}
WORK=${2:-$ROOT/build/uboot-proof}
MAKE=(make -C "$UBOOT" ARCH=arm HOSTCC=cc)
# Base and role as release/build-all.sh pairs them, from boards/<id>/board.env.
MATRIX="hy310:release hy310:installer hy310:netboot hy310:netboot_gate
	hy310:felmmc hy310:host hy300_pro:release hy300_pro:installer"
mkdir -p "$WORK"
rc=0
printf '%-34s %-22s %s\n' "base + fragment" "fragment lines" "against the bare base"
for pair in $MATRIX; do
	base=${pair%%:*}; role=${pair#*:}
	frag=$UBOOT/configs/fragments/h713_$role.config
	[ -f "$frag" ] || { echo "no fragment $frag" >&2; exit 1; }
	# the bare base, once per base, normalised the same way as the merge
	b=$WORK/base-$base
	if [ ! -f "$b/.config" ]; then
		mkdir -p "$b"
		"${MAKE[@]}" O="$b" "${base}_defconfig" >/dev/null
		"${MAKE[@]}" O="$b" olddefconfig >/dev/null
	fi
	m=$WORK/$base-$role
	mkdir -p "$m"
	cp "$b/.config" "$m/.config"
	"$UBOOT"/scripts/kconfig/merge_config.sh -m -O "$m" "$m/.config" "$frag" \
		>"$WORK/merge-$base-$role.log" 2>&1
	"${MAKE[@]}" O="$m" olddefconfig >/dev/null

	# A "=value" line has to stand in the merged .config literally; an "is
	# not set" line counts as kept when the symbol is off AND when Kconfig
	# dropped it with the dependency that carried it - both mean it is out.
	lines=0 missing=0
	while IFS= read -r l; do
		sym=${l#\# }; sym=${sym%%[ =]*}
		case "$l" in
		CONFIG_*=*)                grep -qxF "$l" "$m/.config" ;;
		'# CONFIG_'*' is not set') ! grep -q "^$sym=" "$m/.config" ;;
		*) continue ;;
		esac || { missing=$((missing + 1)); echo "      swallowed: $l"; }
		lines=$((lines + 1))
	done < "$frag"

	d=$WORK/diff-$base-$role.txt
	diff -u "$b/.config" "$m/.config" >"$d" || true
	changed=$(grep -c '^[-+]\(CONFIG\|# CONFIG\)' "$d" || true)
	printf '%-34s %-22s %s\n' "${base}_defconfig + h713_$role" \
		"$lines asked, $missing lost" "$changed lines -> $d"
	[ "$missing" -eq 0 ] || rc=1
done
[ $rc -eq 0 ] && echo "every fragment line stands in its merged .config"
exit $rc
