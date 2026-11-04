# SPDX-License-Identifier: GPL-2.0-only
# shellcheck shell=bash
#
# mainline/build/kconfig-check.sh - sourced by build.sh's kernel stage: did the kernel get what its defconfig asks for?
# kconfig drops a symbol without a word when a dependency is missing - CONFIG_RUST without the container's Rust
# toolchain, and CONFIG_DRM_H713 with it - and the kernel still builds. Host test: release/tests/test_kconfig_check.py.

# The modules an image must carry when its .config builds them (symbol=module): the clean display stack's driver
# (docs/subsystems/display-stacks.md).
KCONFIG_MODULES=(CONFIG_DRM_H713=h713_drm)

# kconfig_symbol LINE: CONFIG_X of "CONFIG_X=..." or "# CONFIG_X is not set" into $kconfig_sym; 1 for any other line
kconfig_symbol() {
	case $1 in
	CONFIG_*=*) kconfig_sym=${1%%=*} ;;
	'# CONFIG_'*' is not set') kconfig_sym=${1#\# }; kconfig_sym=${kconfig_sym%% *} ;;
	*) return 1 ;;
	esac
}

# kconfig_lost CONFIG DEFCONFIG [FRAGMENT...]: every line of DEFCONFIG that CONFIG does not carry word for word, one per
# line on stdout; lines whose symbol a FRAGMENT sets are the fragment's to check. Status 1 when there is one.
kconfig_lost() {
	local config=$1 defconfig=$2 f line lost=0
	shift 2
	local -A over=()
	for f in "$@"; do
		while IFS= read -r line || [[ -n $line ]]; do
			kconfig_symbol "$line" && over[$kconfig_sym]=1
		done < "$f"
	done
	while IFS= read -r line || [[ -n $line ]]; do
		kconfig_symbol "$line" || continue
		[[ -n ${over[$kconfig_sym]:-} ]] && continue
		grep -qxF -- "$line" "$config" || { printf '%s\n' "$line"; lost=1; }
	done < "$defconfig"
	return "$lost"
}

# kconfig_modules_missing CONFIG MODDIR: each module of KCONFIG_MODULES that CONFIG builds (=m) and MODDIR (a module
# tree, e.g. build/modroot.<hash>) lacks, one per line on stdout. Status 1 when there is one.
kconfig_modules_missing() {
	local config=$1 moddir=$2 e sym mod missing=0
	for e in "${KCONFIG_MODULES[@]}"; do
		sym=${e%%=*} mod=${e#*=}
		grep -qx -- "$sym=m" "$config" || continue
		if [[ -z $(find "$moddir" -name "$mod.ko*" -print -quit) ]]; then
			printf '%s\n' "$mod.ko ($sym=m)"
			missing=1
		fi
	done
	return "$missing"
}
