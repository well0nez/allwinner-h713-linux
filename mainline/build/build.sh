#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 well0nez
#
# mainline/build/build.sh - the H713 pieces, one stage at a time: TF-A BL31, a board's base
# U-Boot, the patched kernel with its FIT, the aic8800 Wi-Fi/BT modules and a checksum list.
# Written anew in October 2026 from a functional specification alone (SPEC.md of the licence
# rework, 13.10.2026), without the text of the script that stood here before.
#
#   build/build.sh [all|bl31|uboot|kernel|aic8800|images]          (no argument: all)
#
# Runs inside the build container h713-build (docs/build-container.md); the working directory
# does not matter, every path follows from where this file lies. release/build-all.sh is the
# usual caller. What the environment may set:
#
#   BOARD           a directory under boards/, or one of the two old names (default: ddr3)
#   VARIANT         one of the board's VARIANTS; its variant.env is read after board.env
#   JOBS            make parallelism (default: the number of CPUs)
#   KERNEL_CONFIG   kernel fragments patches/kernel/board/<name>.config, comma-separated;
#                   the outputs then carry the names: Image-<a>-<b>.gz, h713-kernel-<a>-<b>.fit
#   H713_STANDBY=1  BL31 with PSCI SYSTEM_SUSPEND: needs a CRUST_DEFCONFIG on a verified board,
#                   or H713_TEST_IMAGE=1 for a board nobody has verified yet
#   SOURCE_DATE_EPOCH  one clock for every build time stamp (reproducible output)
#   MKIMAGE         the mkimage that makes the FIT (default: one built from the U-Boot submodule)
#   BOARDS_DIR      another place for the board directories (BOARDS is read as a fallback)
#   KCFLAGS         extra kernel compiler flags; kept, behind the path mapping
#
# Outputs go to build/out/, downloads to build/cache/. The kernel and aic8800 trees are
# named after the hash of their inputs and are reused while those do not change.

set -euo pipefail
shopt -s inherit_errexit

bdir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)    # mainline/build
mdir=$(dirname -- "$bdir")                                      # mainline
rdir=$(dirname -- "$mdir")                                      # the repository
out_dir=$bdir/out
cache_dir=$bdir/cache

# --- small helpers -----------------------------------------------------------
tell() { printf '[build] %s\n' "$*"; }
note() { printf '[build] note: %s\n' "$*" >&2; }
# die [status] line...: every line to stderr, then exit (status 1 unless given)
die() {
	local rc=1
	if [[ $1 =~ ^[0-9]+$ ]]; then rc=$1; shift; fi
	printf 'build.sh: %s\n' "$@" >&2
	exit "$rc"
}
sha_of() { local s; s=$(sha256sum < "$1"); printf '%s' "${s%% *}"; }
size_of() { stat -c %s -- "$1"; }

# Directories that only exist while a step runs. Whatever is still listed when the script
# ends (a failure) is removed; a finished step takes its directory off the list.
pending=()
forget() {
	local keep=() p
	for p in "${pending[@]}"; do [[ $p == "$1" ]] || keep+=("$p"); done
	pending=("${keep[@]}")
}
tidy_up() { local p; for p in "${pending[@]}"; do rm -rf -- "$p"; done; }
trap tidy_up EXIT

# the non-comment, non-empty lines of a patch series, in order, into the array $entries
entries=()
read_series() {
	local line
	entries=()
	while IFS= read -r line || [[ -n $line ]]; do
		[[ -z $line || $line == '#'* ]] && continue
		entries+=("$line")
	done < "$1"
}

usage() { printf 'usage: build.sh [all|bl31|uboot|kernel|aic8800|images]\n' >&2; }

# --- arguments, pinned versions, board ----------------------------------------
if (($# > 1)); then usage; exit 2; fi
stage=${1:-all}
case $stage in
	all | bl31 | uboot | kernel | aic8800 | images) ;;
	*) usage; exit 2 ;;
esac

# shellcheck source=../config/versions.env
source "$mdir/config/versions.env"

BOARD=${BOARD:-ddr3}
VARIANT=${VARIANT:-}
JOBS=${JOBS:-$(nproc)}
KERNEL_CONFIG=${KERNEL_CONFIG:-}
H713_STANDBY=${H713_STANDBY:-0}
H713_TEST_IMAGE=${H713_TEST_IMAGE:-0}
boards_dir=${BOARDS_DIR:-${BOARDS:-$rdir/boards}}

# The two board names from before boards/ existed. boards/check.sh reads these two lines.
case $BOARD in
	ddr3) BOARD=hy200-qz713df-a1 ;;
	lpddr3) BOARD=hy200-qz713-v2 ;;
esac

board_dirs() {
	local d names=()
	for d in "$boards_dir"/*/; do
		[[ -d $d ]] || continue
		d=${d%/}
		names+=("${d##*/}")
	done
	printf '%s' "${names[*]:-(none)}"
}

board_env=$boards_dir/$BOARD/board.env
if [[ ! -f $board_env ]]; then
	if [[ -d $boards_dir/$BOARD ]]; then why="$boards_dir/$BOARD has no board.env"
	else why="there is no board directory $boards_dir/$BOARD"; fi
	die 2 "unknown board '$BOARD': $why" \
		"boards here: $(board_dirs)" \
		"old names: ddr3 = hy200-qz713df-a1, lpddr3 = hy200-qz713-v2" \
		"a board that is not here yet starts from an h713_probe log, see boards/README.md"
fi
grep -q '^KERNEL_DTB=' "$board_env" ||
	die 2 "$board_env has no KERNEL_DTB= line (an empty value is allowed, a missing line is not)"
# Board keys come from the board files only, never from the caller's environment.
unset BOARD_ID STATUS UBOOT_BOARD UBOOT_DEFCONFIG VARIANTS CRUST_DEFCONFIG KERNEL_DTB
# shellcheck source=/dev/null
source "$board_env"
[[ ${BOARD_ID:-} == "$BOARD" ]] ||
	die 2 "$board_env says BOARD_ID='${BOARD_ID:-}', but the board asked for is '$BOARD'"

DRAM_CLK=
if [[ -n $VARIANT ]]; then
	wanted=$VARIANT
	read -ra known_variants <<< "${VARIANTS:-}"
	hit=0
	for v in "${known_variants[@]}"; do [[ $v == "$wanted" ]] && hit=1; done
	((hit)) || die 2 "boards/$BOARD has no variant '$wanted' (its variants: ${VARIANTS:-none})"
	variant_env=$boards_dir/$BOARD/variants/$wanted/variant.env
	[[ -f $variant_env ]] || die 2 "variant '$wanted' is named, but $variant_env is missing"
	unset VARIANT
	# shellcheck source=/dev/null
	source "$variant_env"
	[[ ${VARIANT:-} == "$wanted" ]] ||
		die 2 "$variant_env says VARIANT='${VARIANT:-}', but the variant asked for is '$wanted'"
fi
unit=$BOARD${VARIANT:+/$VARIANT}

mkdir -p "$out_dir" "$cache_dir"

# --- one clock for every build time stamp --------------------------------------
# Only when SOURCE_DATE_EPOCH is given; without it everything builds on the wall clock.
if [[ -n ${SOURCE_DATE_EPOCH:-} ]]; then
	export SOURCE_DATE_EPOCH
	# TF-A's own default is __TIME__", "__DATE__; this is the same text for the given second,
	# quotes included, as TF-A pastes it into a C string.
	BUILD_MESSAGE_TIMESTAMP="\"$(LC_ALL=C date -u -d "@$SOURCE_DATE_EPOCH" '+%T, %b %e %Y')\""
	KBUILD_BUILD_TIMESTAMP=$(LC_ALL=C date -u -d "@$SOURCE_DATE_EPOCH" '+%a %b %e %H:%M:%S %Z %Y')
	export BUILD_MESSAGE_TIMESTAMP KBUILD_BUILD_TIMESTAMP
	# the uname line: no user, no host name, and a build number that does not count up
	export KBUILD_BUILD_USER=h713 KBUILD_BUILD_HOST=h713-build KBUILD_BUILD_VERSION=1
	# Header paths in out-of-tree modules relative to mainline/, not to wherever it is checked out.
	# U-Boot sets its own KCFLAGS on the make command line and does not see this one.
	export KCFLAGS="-ffile-prefix-map=$mdir/=${KCFLAGS:+ $KCFLAGS}"
fi

# --- bl31 ----------------------------------------------------------------------
build_bl31() {
	local tfa=$mdir/external/arm-trusted-firmware suspend=0 flag plat_dir
	[[ -f $tfa/Makefile ]] ||
		die "TF-A is not checked out at $tfa - run: git submodule update --init"
	if [[ $H713_STANDBY == 1 ]]; then
		[[ -n ${CRUST_DEFCONFIG:-} ]] ||
			die "H713_STANDBY=1, but boards/$BOARD names no CRUST_DEFCONFIG: without crust there is nothing to suspend through"
		[[ ${STATUS:-} == verified || $H713_TEST_IMAGE == 1 ]] ||
			die "H713_STANDBY=1 on $unit (STATUS=${STATUS:-unset}): only a verified board, or a test image (H713_TEST_IMAGE=1)"
		suspend=1
	fi
	# TF-A does not notice a changed make switch; its objects of the other setting would stay.
	flag=$tfa/build/.h713-system-suspend
	plat_dir=$tfa/build/$ATF_PLAT
	if [[ ! -f $flag || "$(< "$flag")" != "$suspend" ]]; then
		rm -rf -- "$plat_dir"
	fi
	tell "bl31: TF-A $ATF_PLAT, SYSTEM_SUSPEND=$suspend"
	make -C "$tfa" -j"$JOBS" PLAT="$ATF_PLAT" DEBUG=0 BL31_IN_DRAM=1 SUNXI_SYSTEM_SUSPEND="$suspend" \
		CC=clang LD=ld.lld AR=llvm-ar OC=llvm-objcopy OD=llvm-objdump NM=llvm-nm READELF=llvm-readelf \
		CFLAGS="-Wno-error=deprecated-non-prototype -fno-stack-protector" bl31
	mkdir -p -- "$tfa/build"
	printf '%s\n' "$suspend" > "$flag"
	install -m 0644 -- "$plat_dir/release/bl31.bin" "$out_dir/bl31.bin"
	tell "bl31: build/out/bl31.bin, $(size_of "$out_dir/bl31.bin") bytes"
}

# --- uboot: the board's base defconfig, no role --------------------------------
build_uboot() {
	local ub=$mdir/external/u-boot base name odir
	[[ -f $ub/Makefile ]] ||
		die "U-Boot is not checked out at $ub - run: git submodule update --init"
	if [[ ! -f $out_dir/bl31.bin ]]; then
		tell "uboot: no build/out/bl31.bin yet, building it first"
		build_bl31
	fi
	if [[ -n ${UBOOT_DEFCONFIG:-} ]]; then base=$UBOOT_DEFCONFIG
	elif [[ -n ${UBOOT_BOARD:-} ]]; then base=${UBOOT_BOARD}_defconfig
	else die "boards/$BOARD names neither UBOOT_DEFCONFIG nor UBOOT_BOARD: no U-Boot base for it"
	fi
	name=$BOARD${VARIANT:+-$VARIANT}
	odir=$bdir/uboot-$name
	tell "uboot: $base${DRAM_CLK:+ at DRAM $DRAM_CLK MHz} into build/uboot-$name"
	# the same parameter set as every other U-Boot of the project, without a role and without SCP
	env -u SCP -u UBOOT_SRC -u DRAM_CLK ${DRAM_CLK:+"DRAM_CLK=$DRAM_CLK"} JOBS="$JOBS" \
		"$bdir/uboot-build.sh" "$odir" "$base"
	install -m 0644 -- "$odir/u-boot-sunxi-with-spl.bin" "$out_dir/u-boot-sunxi-with-spl-$name.bin"
	tell "uboot: build/out/u-boot-sunxi-with-spl-$name.bin, $(size_of "$out_dir/u-boot-sunxi-with-spl-$name.bin") bytes"
}

# --- kernel ----------------------------------------------------------------------
# KERNEL_CONFIG -> $frags (names) and $frag_files (paths); each one must exist.
frags=()
frag_files=()
pick_fragments() {
	local list pieces=() p f
	frags=(); frag_files=()
	list=${KERNEL_CONFIG//[,$'\t\n']/ }
	read -ra pieces <<< "$list"
	for p in "${pieces[@]}"; do
		[[ -n $p ]] || continue
		f=$mdir/patches/kernel/board/$p.config
		[[ -f $f ]] || die "KERNEL_CONFIG names '$p', but there is no patches/kernel/board/$p.config"
		frags+=("$p"); frag_files+=("$f")
	done
}

# The name of the kernel tree: a hash over everything that goes into it. The board is not part
# of it - all boards share one tree, only their FITs differ.
kernel_inputs_hash() {
	local text='' h e
	h=$(grep '^KERNEL_' "$mdir/config/versions.env" | sha256sum)
	text+="versions.env ${h%% *}"$'\n'
	h=$(sha_of "$mdir/patches/kernel/series")
	text+="series $h"$'\n'
	h=$(sha_of "$mdir/patches/kernel/board/$KERNEL_DEFCONFIG")
	text+="defconfig $h"$'\n'
	for e in "${frags[@]}"; do
		h=$(sha_of "$mdir/patches/kernel/board/$e.config")
		text+="fragment $e $h"$'\n'
	done
	read_series "$mdir/patches/kernel/series"
	for e in "${entries[@]}"; do
		h=$(sha_of "$mdir/patches/kernel/$e")
		text+="$e $h"$'\n'
	done
	h=$(printf '%s' "$text" | sha256sum)
	printf '%s\n' "${h%% *}"
}

# a tarball in build/cache, checked against its pinned sha256; fetched once if missing
fetch_pinned() {
	local url=$1 want=$2 dest=$3 got part
	if [[ -f $dest ]]; then
		got=$(sha_of "$dest")
		[[ $got == "$want" ]] ||
			die "$dest has sha256 $got, pinned is $want." \
				"The file stays where it is; remove it by hand to fetch it again."
		return 0
	fi
	part=$(mktemp "$dest.download.XXXXXX")
	pending+=("$part")
	tell "fetching $url"
	# every kind of failure is tried again, a reset or refused connection too: --retry alone gives up on those, and a
	# server that dropped one connection usually answers a minute later (15.10.2026)
	curl -fL --retry 4 --retry-all-errors --retry-delay 5 -o "$part" "$url" || die "could not fetch $url"
	got=$(sha_of "$part")
	[[ $got == "$want" ]] || die "$url arrived with sha256 $got, pinned is $want - not used"
	chmod 0644 -- "$part"
	mv -f -- "$part" "$dest"
	forget "$part"
}

# Make sure the kernel tree $1 (inputs hash $2) exists and is complete.
prepare_kernel_tree() {
	local tree=$1 hash=$2 mark=.h713-inputs-$2 tarball tmp e n=0
	if [[ -e $tree ]]; then
		[[ -f $tree/$mark ]] ||
			die "$tree is there without its mark $mark: an earlier preparation did not finish." \
				"Remove that directory and start again."
		tell "kernel: reusing ${tree##*/}"
		return 0
	fi
	tarball=$cache_dir/linux-$KERNEL_VERSION.tar.xz
	fetch_pinned "$KERNEL_TARBALL_URL" "$KERNEL_TARBALL_SHA256" "$tarball"
	tmp=$(mktemp -d "$bdir/.linux-$KERNEL_VERSION-unpack.XXXXXX")
	pending+=("$tmp")
	tell "kernel: unpacking linux-$KERNEL_VERSION"
	tar -xJf "$tarball" -C "$tmp" --strip-components=1
	read_series "$mdir/patches/kernel/series"
	for e in "${entries[@]}"; do
		patch -d "$tmp" -p1 -s -N -i "$mdir/patches/kernel/$e" < /dev/null ||
			die "kernel patch $e does not apply to linux-$KERNEL_VERSION; nothing of this tree was kept"
		n=$((n + 1))
	done
	cp -- "$mdir/patches/kernel/board/$KERNEL_DEFCONFIG" "$tmp/arch/$KERNEL_ARCH/configs/$KERNEL_DEFCONFIG"
	: > "$tmp/$mark"
	mv -T -- "$tmp" "$tree"
	forget "$tmp"
	tell "kernel: applied $n series patches, tree ${tree##*/}"
}

# After olddefconfig: is every line the fragments ask for really in .config?
check_fragments_took() {
	local config=$1 f line lost=()
	for f in "${frag_files[@]}"; do
		while IFS= read -r line || [[ -n $line ]]; do
			[[ -z $line ]] && continue
			if [[ $line == '#'* && $line != *' is not set' ]]; then continue; fi
			grep -qxF -- "$line" "$config" || lost+=("${f##*/}: $line")
		done < "$f"
	done
	if ((${#lost[@]})); then
		die "olddefconfig dropped what the fragments ask for (a missing dependency?):" "${lost[@]}"
	fi
}

# Which mkimage makes the FIT -> $mkimage_bin
mkimage_bin=
choose_mkimage() {
	local LC_ALL=C c ub=$mdir/external/u-boot
	if [[ -n ${MKIMAGE:-} ]]; then
		[[ -f $MKIMAGE && -x $MKIMAGE ]] || die "MKIMAGE=$MKIMAGE is not an executable file"
		mkimage_bin=$MKIMAGE
		return 0
	fi
	for c in "$bdir"/uboot-*/tools/mkimage; do
		if [[ -f $c && -x $c ]]; then mkimage_bin=$c; return 0; fi
	done
	if [[ -f $ub/Makefile ]]; then
		tell "kernel: no mkimage built yet, building U-Boot's tools into build/uboot-tools"
		make -C "$ub" -s O="$bdir/uboot-tools" HOSTCC=clang tools-only_defconfig > /dev/null
		make -C "$ub" -s -j"$JOBS" O="$bdir/uboot-tools" HOSTCC=clang tools-only > /dev/null
		c=$bdir/uboot-tools/tools/mkimage
		[[ -f $c && -x $c ]] || die "U-Boot is checked out, yet building its tools left no $c"
		mkimage_bin=$c
		return 0
	fi
	c=$(command -v mkimage) ||
		die "no mkimage: there is no U-Boot submodule here and none on PATH (set MKIMAGE=<file>)"
	note "no U-Boot submodule here, the FIT is made with $c from PATH"
	mkimage_bin=$c
}

# the FIT source: one kernel, one device tree, one configuration named after the device tree
write_fit_source() {
	local its=$1 image=$2 dtb=$3 suffix=$4
	cat > "$its" << EOF
/dts-v1/;

/ {
	description = "H713 arm64 kernel ($KERNEL_VERSION$suffix) + DTB ($BOARD)";
	#address-cells = <1>;

	images {
		kernel {
			description = "Linux $KERNEL_VERSION";
			data = /incbin/("$image");
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
			data = /incbin/("$dtb");
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
EOF
}

build_kernel() {
	local suffix='' hash tree its fit image d done_dtbs=' '
	[[ -n ${KERNEL_DTB:-} ]] ||
		die "boards/$BOARD has an empty KERNEL_DTB: no device tree of ours, so no FIT for it" \
			"(the stages bl31 and uboot still work for this board)"
	pick_fragments
	if ((${#frags[@]})); then suffix=-$(IFS=-; printf '%s' "${frags[*]}"); fi
	choose_mkimage
	hash=$(kernel_inputs_hash)
	tree=$bdir/linux-$KERNEL_VERSION-$hash
	prepare_kernel_tree "$tree" "$hash"

	local kmake=(make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1)
	"${kmake[@]}" "$KERNEL_DEFCONFIG"
	if ((${#frags[@]})); then
		tell "kernel: fragments ${frags[*]}"
		(cd -- "$tree" && ARCH=$KERNEL_ARCH ./scripts/kconfig/merge_config.sh -m -O "$tree" "$tree/.config" "${frag_files[@]}")
		"${kmake[@]}" olddefconfig
		check_fragments_took "$tree/.config"
	fi
	"${kmake[@]}" -j"$JOBS" Image dtbs modules

	image=$tree/arch/$KERNEL_ARCH/boot/Image
	gzip -9 -n -k -f -- "$image"
	install -m 0644 -- "$image.gz" "$out_dir/Image$suffix.gz"
	for d in "$KERNEL_DTB" "${KERNEL_DTB_BENCH:-}" "${KERNEL_DTB_PROJECTOR:-}"; do
		[[ -n $d && $done_dtbs != *" $d "* ]] || continue
		install -m 0644 -- "$tree/arch/$KERNEL_ARCH/boot/dts/allwinner/$d.dtb" "$out_dir/$d.dtb"
		done_dtbs+="$d "
	done

	its=$out_dir/h713-kernel$suffix.its
	fit=$out_dir/h713-kernel$suffix.fit
	write_fit_source "$its" "$out_dir/Image$suffix.gz" "$out_dir/$KERNEL_DTB.dtb" "$suffix"
	rm -f -- "$fit"
	"$mkimage_bin" -f "$its" "$fit" > /dev/null
	tell "kernel: build/out/h713-kernel$suffix.fit, $(size_of "$fit") bytes, configuration conf-$KERNEL_DTB"
	# build-all.sh takes the most recently changed tree as the one just built
	touch -- "$tree"
}

# --- aic8800 ---------------------------------------------------------------------
aic8800_inputs_hash() {
	local text='' h e
	text+="commit $AIC8800_COMMIT"$'\n'
	h=$(sha_of "$mdir/patches/aic8800/series")
	text+="series $h"$'\n'
	read_series "$mdir/patches/aic8800/series"
	for e in "${entries[@]}"; do
		h=$(sha_of "$mdir/patches/aic8800/$e")
		text+="$e $h"$'\n'
	done
	h=$(printf '%s' "$text" | sha256sum)
	printf '%s\n' "${h%% *}"
}

# git for the throw-away repository of the aic8800 tree: no user or system configuration,
# a fixed neutral identity
scratch_git() {
	env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
		git -c user.name="h713 build" -c user.email="build@h713.invalid" -c init.defaultBranch=base \
		-c commit.gpgsign=false "$@"
}

prepare_aic8800_tree() {
	local tree=$1 hash=$2 mark=.h713-inputs-$2 short=${AIC8800_COMMIT:0:12}
	local tarball unpack work line vendor=() p s out listed used=0 passed=0 skip_list=()
	if [[ -e $tree ]]; then
		[[ -f $tree/$mark ]] ||
			die "$tree is there without its mark $mark: an earlier preparation did not finish." \
				"Remove that directory and start again."
		tell "aic8800: reusing ${tree##*/}"
		return 0
	fi
	tarball=$cache_dir/aic8800-$short.tar.gz
	fetch_pinned "$AIC8800_TARBALL_URL" "$AIC8800_TARBALL_SHA256" "$tarball"
	unpack=$(mktemp -d "$bdir/.aic8800-$short-unpack.XXXXXX")
	pending+=("$unpack")
	tar -xzf "$tarball" -C "$unpack" --strip-components=1 \
		"aic8800-$AIC8800_COMMIT/src" "aic8800-$AIC8800_COMMIT/debian"

	# radxa's kernel-compat series first, over the whole tree (its patches touch PCIe, SDIO and
	# USB in the same hunks); only the names in AIC8800_VENDOR_PATCH_SKIP may fail
	read -ra skip_list <<< "${AIC8800_VENDOR_PATCH_SKIP:-}"
	while IFS= read -r line || [[ -n $line ]]; do
		[[ -n $line ]] && vendor+=("$line")
	done < "$unpack/debian/patches/series"
	for p in "${vendor[@]}"; do
		if out=$(patch -d "$unpack" -p1 -s -N --no-backup-if-mismatch -i "$unpack/debian/patches/$p" < /dev/null 2>&1); then
			used=$((used + 1))
			continue
		fi
		listed=0
		for s in "${skip_list[@]}"; do [[ $s == "$p" ]] && listed=1; done
		if ((listed)); then
			passed=$((passed + 1))
		else
			printf '%s\n' "$out" >&2
			die "vendor patch $p (debian/patches) does not apply at $short." \
				"If that is expected after a version jump, add it to AIC8800_VENDOR_PATCH_SKIP in config/versions.env."
		fi
	done
	tell "aic8800: vendor series: $used applied, $passed skipped as listed"

	[[ -d $unpack/$AIC8800_SUBTREE ]] ||
		die "the tarball has no $AIC8800_SUBTREE (AIC8800_SUBTREE)"
	work=$(mktemp -d "$bdir/.aic8800-$short-work.XXXXXX")
	pending+=("$work")
	cp -a -- "$unpack/$AIC8800_SUBTREE/." "$work/"
	rm -rf -- "$unpack"
	forget "$unpack"

	# a base commit, so that our series is applied with a real three-way merge
	scratch_git -C "$work" init -q
	scratch_git -C "$work" add -A -f .
	scratch_git -C "$work" commit -q -m "aic8800 $short: $AIC8800_SUBTREE after the vendor series"
	read_series "$mdir/patches/aic8800/series"
	for p in "${entries[@]}"; do
		if ! scratch_git -C "$work" am -q -3 "$mdir/patches/aic8800/$p"; then
			scratch_git -C "$work" am --abort || true
			forget "$work"
			die "aic8800 patch $p does not apply." "The work directory stays for a look: $work"
		fi
	done
	tell "aic8800: applied ${#entries[@]} patches of patches/aic8800"
	: > "$work/$mark"
	mv -T -- "$work" "$tree"
	forget "$work"
}

build_aic8800() {
	local khash ktree whash wtree m
	pick_fragments
	khash=$(kernel_inputs_hash)
	ktree=$bdir/linux-$KERNEL_VERSION-$khash
	[[ -f $ktree/.h713-inputs-$khash && -f $ktree/Module.symvers ]] ||
		die "no built kernel tree for these inputs (${ktree##*/}):" \
			"build the kernel first, with the same KERNEL_CONFIG: build.sh kernel"
	whash=$(aic8800_inputs_hash)
	wtree=$bdir/aic8800-${AIC8800_COMMIT:0:12}-$whash
	prepare_aic8800_tree "$wtree" "$whash"

	local kmake=(make -C "$ktree" -j"$JOBS" ARCH="$KERNEL_ARCH" LLVM=1 CONFIG_PLATFORM_MAINLINE_SUNXI=y)
	tell "aic8800: modules against ${ktree##*/}"
	"${kmake[@]}" M="$wtree/aic8800_bsp" modules
	# fdrv and btlpm import symbols of bsp
	for m in aic8800_fdrv aic8800_btlpm; do
		"${kmake[@]}" M="$wtree/$m" KBUILD_EXTRA_SYMBOLS="$wtree/aic8800_bsp/Module.symvers" modules
	done
	mkdir -p -- "$out_dir/modules"
	for m in aic8800_bsp aic8800_fdrv aic8800_btlpm; do
		install -m 0644 -- "$wtree/$m/$m.ko" "$out_dir/modules/$m.ko"
	done
	tell "aic8800: build/out/modules/aic8800_{bsp,fdrv,btlpm}.ko"
}

# --- images: the checksum list ----------------------------------------------------
build_images() {
	local LC_ALL=C names=(bl31.bin Image.gz "${KERNEL_DTB:-}.dtb" h713-kernel.fit) d n f seen lacking=()
	[[ -n ${KERNEL_DTB:-} ]] || die "boards/$BOARD has no KERNEL_DTB: no kernel outputs to list"
	for d in "${KERNEL_DTB_BENCH:-}" "${KERNEL_DTB_PROJECTOR:-}"; do
		[[ -n $d ]] || continue
		seen=0
		for n in "${names[@]}"; do [[ $n == "$d.dtb" ]] && seen=1; done
		((seen)) || names+=("$d.dtb")
	done
	for n in "${names[@]}"; do [[ -f $out_dir/$n ]] || lacking+=("$n"); done
	((${#lacking[@]} == 0)) ||
		die "build/out lacks: ${lacking[*]} - build everything first: build.sh all"
	for f in "$out_dir"/u-boot-sunxi-with-spl-*.bin; do
		[[ -f $f ]] && names+=("${f##*/}")
	done
	(cd -- "$out_dir" && sha256sum -- "${names[@]}") > "$out_dir/SHA256SUMS.tmp"
	mv -f -- "$out_dir/SHA256SUMS.tmp" "$out_dir/SHA256SUMS"
	tell "images: build/out/SHA256SUMS, ${#names[@]} files"
	ls -l -- "$out_dir"
}

case $stage in
	bl31) build_bl31 ;;
	uboot) build_uboot ;;
	kernel) build_kernel ;;
	aic8800) build_aic8800 ;;
	images) build_images ;;
	all)
		build_bl31
		build_uboot
		build_kernel
		build_aic8800
		build_images
		;;
esac
