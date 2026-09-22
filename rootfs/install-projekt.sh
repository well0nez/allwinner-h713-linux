#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
#
# install-projekt.sh -- install the project-specific parts into an unpacked
# rootfs tree. Called by build-rootfs.sh, but explicitly usable ON ITS OWN too:
#
#     ./install-projekt.sh /srv/h713-rootfs-neu      # e.g. the NFS root
#     ./install-projekt.sh --dry-run /path/to/tree
#
# The second case is the reason for a script of its own: by 109 §4.2 the same
# build is put in TWO places (hy310-rootfs on the eMMC and the NFS root on the
# host), and when h713-tv or the modules are rebuilt you want to pull them over
# without bootstrapping the whole rootfs again.
#
# What is installed:
#   1. h713-tv (cross-built) + unit + udev rule + gamma-standard.bin
#   2. the kernel modules of the GOOD revision + the aic8800 modules (WLAN) + depmod
#   3. h713-pq
#   4. h713-focus
#   5. h713-cam
#   5b. h713-autofocus
#
# What is NOT installed is any proprietary blob (107 §5). At the end there is a
# guard that searches the tree afterwards and stops the run if one is in there
# after all -- namely hy310-hdcp22.bin, which today sits in the netboot root
# under /lib/firmware and must never come along.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Project root: the next parent directory with mainline/build/build.sh -- that way
# the script works in the working directory (analyse/release/arbeit/...) as well as
# in the release repository (rootfs/ and installer/ directly under the root), doku/116 P3.
project_root() { local d=$1; while [ "$d" != / ]; do [ -f "$d/mainline/build/build.sh" ] && { echo "$d"; return; }; d=$(dirname "$d"); done; return 1; }
PROJECT_ROOT=$(project_root "$HERE") || { echo "no project root (mainline/build/build.sh) found above $HERE" >&2; exit 1; }

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; shift; fi
TREE=${1:-}
[[ -n "$TREE" ]] || { echo "usage: ${0##*/} [--dry-run] TREE" >&2; exit 2; }

# Set by build-rootfs.sh through the environment, else defaults.
MODROOT=${MODROOT:-$PROJECT_ROOT/mainline/build/modroot.GUT-bad2f16b}
H713_TV_SRC=${H713_TV_SRC:-$PROJECT_ROOT/userspace/h713-tv}
H713_TV_BIN=${H713_TV_BIN:-$H713_TV_SRC/h713-tv.aarch64-linux-gnu}
H713_PQ_SRC=${H713_PQ_SRC:-$PROJECT_ROOT/userspace/h713-pq}
H713_FOCUS_SRC=${H713_FOCUS_SRC:-$PROJECT_ROOT/userspace/h713-focus}
H713_CAM_SRC=${H713_CAM_SRC:-$PROJECT_ROOT/userspace/h713-cam}
H713_AF_SRC=${H713_AF_SRC:-$PROJECT_ROOT/userspace/h713-autofocus}
# build.sh builds the WLAN modules OUTSIDE the kernel tree (out-of-tree, radxa
# source + patches/aic8800/) and puts them into build/out/modules/ -- they are
# in no modroot. Without this step the image would have packages, service and
# wifi.env, but no driver (noticed 12.09.).
AIC8800_MODULES=${AIC8800_MODULES:-$PROJECT_ROOT/mainline/build/out/modules}

say()  { printf '    -- %s\n' "$*"; }
info() { printf '       %s\n' "$*"; }
warn() { printf '!!     %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Blob guard: what must NEVER go into the image
# ---------------------------------------------------------------------------
# Firmware and PQ data come later from the installer out of h713-extract
# (107 §5, 108 §2/§6). They lie around in the working tree and in today's
# netboot root, so copying one along by accident is the most likely mistake
# -- hence a guard and not just a sentence in the plan.
#
# hy310-hdcp22.bin is explicitly first: HDCP key material. Today it sits in
# /srv/h713-rootfs/lib/firmware/ and must never reach the image.
FORBIDDEN_NAMES=(
	'hy310-hdcp22.bin'      # HDCP 2.2 -- key material, never into the image
	'hdcp_v22.bin'          # the same under the vendor name
	'h713-arisc.bin'        # ARISC firmware, vendor (108 §2) -> installer
	'hy310-edid.bin'        # read out of the stock -> installer
	'hy310-edid-nodc.bin'
	'msp-patch.bin'         # MSP DSP patch, vendor -> installer
	'fmacfw*'               # aic8800 WLAN firmware: NOT in the image, comes from
	'fmacfwbt*'             #   the installer out of the dump (h713-extract, 12.09.).
	                        #   The modules themselves (GPL) are in extra/, see step 2.
)
FORBIDDEN_PATHS=(
	'lib/firmware/h713'
	'lib/firmware/aic8800_fw'
	'usr/lib/firmware/h713'
)

blob_guard() {
	local tree=$1 found=0 n p hit
	for n in "${FORBIDDEN_NAMES[@]}"; do
		while IFS= read -r hit; do
			warn "FORBIDDEN in the tree: ${hit#"$tree"}"
			found=1
		done < <(find "$tree" -name "$n" -print 2>/dev/null)
	done
	for p in "${FORBIDDEN_PATHS[@]}"; do
		if [[ -e "$tree/$p" ]]; then
			warn "FORBIDDEN in the tree: /$p"
			found=1
		fi
	done
	# tvconfig has to be empty: since 107 §8 the path means ONLY the directory
	# with the extracted PQ files. The service configuration is called
	# /etc/h713/tv.conf and is something else.
	if [[ -d "$tree/etc/h713/tvconfig" ]] && [[ -n "$(ls -A "$tree/etc/h713/tvconfig")" ]]; then
		warn "FORBIDDEN: /etc/h713/tvconfig is not empty"
		found=1
	fi
	((found == 0)) || die "blob guard: the image carries files it must not carry (107 §5)"
	say "blob guard: clean (${#FORBIDDEN_NAMES[@]} names, ${#FORBIDDEN_PATHS[@]} paths checked, tvconfig empty)"
}

# ---------------------------------------------------------------------------
# Check the sources
# ---------------------------------------------------------------------------
check_sources() {
	local errors=0

	if [[ -x "$H713_TV_BIN" ]]; then
		local kind; kind=$(file -b "$H713_TV_BIN" 2>/dev/null || echo '?')
		case "$kind" in
		*aarch64*|*ARM\ aarch64*) : ;;
		'?') warn "file(1) is missing -- the architecture of h713-tv is unchecked" ;;
		*) warn "h713-tv is NOT aarch64: $kind"; errors=1 ;;
		esac
	else
		warn "h713-tv is missing: $H713_TV_BIN"
		info "cross-build it:  make -C ${H713_TV_SRC#"$PROJECT_ROOT"/} cross"
		info "  (host clang against /srv/h713-rootfs as the sysroot -- see the Makefile)"
		errors=1
	fi

	local f
	for f in h713-tv@.service 99-h713-tv.rules gamma-standard.bin; do
		[[ -r "$H713_TV_SRC/$f" ]] || { warn "missing: $H713_TV_SRC/$f"; errors=1; }
	done

	if [[ -d "$MODROOT/lib/modules" ]]; then
		local rel
		rel=$(ls -1 "$MODROOT/lib/modules" | head -1)
		[[ -n "$rel" ]] || { warn "no kernel release in $MODROOT/lib/modules"; errors=1; }
	else
		warn "module tree is missing: $MODROOT/lib/modules"
		errors=1
	fi

	[[ -x "$H713_PQ_SRC/h713-pq" ]] || { warn "missing: $H713_PQ_SRC/h713-pq"; errors=1; }
	[[ -d "$H713_PQ_SRC/h713_pq" ]] || { warn "missing: $H713_PQ_SRC/h713_pq/"; errors=1; }

	[[ -x "$H713_FOCUS_SRC/h713-focus" ]] || \
		{ warn "missing: $H713_FOCUS_SRC/h713-focus"; errors=1; }
	[[ -x "$H713_CAM_SRC/h713-cam" ]] || \
		{ warn "missing: $H713_CAM_SRC/h713-cam"; errors=1; }
	[[ -x "$H713_AF_SRC/h713-autofocus" ]] || \
		{ warn "missing: $H713_AF_SRC/h713-autofocus"; errors=1; }
	for ko in aic8800_bsp aic8800_fdrv; do
		[[ -f "$AIC8800_MODULES/$ko.ko" ]] || \
			{ warn "missing: $AIC8800_MODULES/$ko.ko (build/build.sh aic8800)"; errors=1; }
	done

	return $errors
}

# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------
if ((DRY_RUN)); then
	printf '    project parts (install-projekt.sh --dry-run)\n'
	check_sources || warn "sources incomplete -- the real run would stop here"
	local_rel=$(ls -1 "$MODROOT/lib/modules" 2>/dev/null | head -1 || true)
	cat <<EOF
    1. h713-tv
       ${H713_TV_BIN#"$PROJECT_ROOT"/}
           -> /usr/local/sbin/h713-tv                     0755
       h713-tv@.service   -> /etc/systemd/system/          0644
       99-h713-tv.rules   -> /etc/udev/rules.d/            0644
       gamma-standard.bin  -> /usr/local/share/h713-tv/    0644
       README.md           -> /usr/local/share/doc/h713-tv/
       (no systemctl enable: the unit has no [Install] section, it is started
        by the udev rule through SYSTEMD_WANTS)
    2. kernel modules
       ${MODROOT#"$PROJECT_ROOT"/}/lib/modules/${local_rel:-<release>}
           -> /lib/modules/${local_rel:-<release>}   ($(find "$MODROOT" -name '*.ko*' 2>/dev/null | wc -l) modules,
              $(du -sh "$MODROOT" 2>/dev/null | cut -f1))
       ${AIC8800_MODULES#"$PROJECT_ROOT"/}/{aic8800_bsp,aic8800_fdrv}.ko
           -> /lib/modules/${local_rel:-<release>}/extra/   (WLAN, out-of-tree;
              btlpm stays out: no BT firmware in the dump)
       then depmod -b
       (the symlink build -> /work/mainline/build/... stays OUT)
    3. h713-pq
       ${H713_PQ_SRC#"$PROJECT_ROOT"/}/{h713-pq,h713_pq/}
           -> /usr/local/lib/h713-pq/, symlink /usr/local/bin/h713-pq
       (pure Python, standard library; reads /etc/h713/tvconfig)
    4. h713-focus
       ${H713_FOCUS_SRC#"$PROJECT_ROOT"/}/h713-focus
           -> /usr/local/bin/h713-focus                   0755
       README.md           -> /usr/local/share/doc/h713-focus/
       (one file, pure Python; drives the focus motor by hand.
        NO blacklist for hy310_focus_motor -- since patch 0156 homing is off
        by default, loading it moves nothing.)
    5. h713-cam
       ${H713_CAM_SRC#"$PROJECT_ROOT"/}/h713-cam
           -> /usr/local/bin/h713-cam                     0755
       README.md           -> /usr/local/share/doc/h713-cam/
       (one file, pure Python; probe/controls/get/set/grab on the internal
        UVC camera. uvcvideo comes out of the module tree, step 2.)
    5b. h713-autofocus
       ${H713_AF_SRC#"$PROJECT_ROOT"/}/h713-autofocus
           -> /usr/local/bin/h713-autofocus               0755
       (one file, pure Python; the stock autofocus search rebuilt: chessboard
        on /dev/fb0, camera frames, focus motor cmd 1/2. Q6, 22.09.2026.)
    6. blob guard
       Stop if one of these files is in the tree:
       ${FORBIDDEN_NAMES[*]}
       or one of these directories: ${FORBIDDEN_PATHS[*]}
       or /etc/h713/tvconfig is not empty.
EOF
	exit 0
fi

# ===========================================================================
# Real run
# ===========================================================================
[[ -d "$TREE/etc" && -d "$TREE/usr" ]] || die "this does not look like a rootfs: $TREE"
check_sources || die "sources incomplete (see above)"

# --- 1. h713-tv -----------------------------------------------------------
say "h713-tv"
install -D -m 0755 "$H713_TV_BIN"                     "$TREE/usr/local/sbin/h713-tv"
install -D -m 0644 "$H713_TV_SRC/h713-tv@.service"   "$TREE/etc/systemd/system/h713-tv@.service"
install -D -m 0644 "$H713_TV_SRC/99-h713-tv.rules"   "$TREE/etc/udev/rules.d/99-h713-tv.rules"
install -D -m 0644 "$H713_TV_SRC/gamma-standard.bin"  "$TREE/usr/local/share/h713-tv/gamma-standard.bin"
[[ -r "$H713_TV_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_TV_SRC/README.md" "$TREE/usr/local/share/doc/h713-tv/README.md"
# An old h713-tv.service (non-template) would be a doppelganger -- the same
# move as in the Makefile target install-data.
rm -f "$TREE/etc/systemd/system/h713-tv.service"
info "/usr/local/sbin/h713-tv ($(stat -c %s "$TREE/usr/local/sbin/h713-tv") B), unit, udev rule, gamma-standard.bin"
# No enable: h713-tv@.service deliberately has no [Install] section. The hdmirx
# probe runs asynchronously (EDID/HPD over ten seconds), a start "at boot"
# would be a race. The udev rule starts the instance as soon as /dev/videoN
# appears.

# --- 2. kernel modules -----------------------------------------------------
say "kernel modules"
KREL=$(ls -1 "$MODROOT/lib/modules" | head -1)
SRC_MOD="$MODROOT/lib/modules/$KREL"
DST_MOD="$TREE/lib/modules/$KREL"
rm -rf "$DST_MOD"
install -d "$DST_MOD"
# --exclude build/source: those are symlinks into the container's build
# directory tree (/work/mainline/build/linux-...). In the image they would be
# dead links, and they are the path along which half a kernel tree wanders in
# by accident.
tar -C "$SRC_MOD" --exclude=./build --exclude=./source -cf - . | \
	tar -C "$DST_MOD" --no-same-owner -xf -
# Belt and braces: should some version of tar read the exclusions differently,
# they are gone here anyway.
rm -f "$DST_MOD/build" "$DST_MOD/source"
KO_N=$(find "$DST_MOD" -name '*.ko*' | wc -l)
((KO_N > 0)) || die "no modules copied to $DST_MOD"

# aic8800 (WLAN), built out of tree. Into extra/, where depmod expects foreign
# modules. Only bsp + fdrv: btlpm is Bluetooth, and its firmware is not in the
# vendor dump (60-offen §WLAN und Bluetooth).
# Check the vermagic: a module built against another tree either does not load
# or -- worse -- loads and does not match. Compared against an in-tree module
# of the same modroot.
vermagic() { modinfo -F vermagic "$1" 2>/dev/null || strings -n 8 "$1" | sed -n 's/^vermagic=//p' | head -1; }
ref_ko=$(find "$DST_MOD" -name '*.ko' -print -quit)
ref_vm=$(vermagic "$ref_ko")
install -d "$DST_MOD/extra"
for ko in aic8800_bsp aic8800_fdrv; do
	src="$AIC8800_MODULES/$ko.ko"
	[[ -f "$src" ]] || die "$src is missing -- build/build.sh aic8800 (against the same kernel tree as $MODROOT)"
	vm=$(vermagic "$src")
	[[ "$vm" == "$ref_vm" ]] || die "$ko.ko: vermagic '$vm' does not fit the module tree ('$ref_vm') -- build it against the same kernel"
	install -m 0644 "$src" "$DST_MOD/extra/$ko.ko"
done
info "aic8800_bsp + aic8800_fdrv into extra/ (vermagic: $ref_vm)"
# Recompute depmod: the modules.dep from the build names paths of the build place.
if command -v depmod >/dev/null 2>&1; then
	depmod -b "$TREE" "$KREL"
	info "depmod -b: $(wc -l < "$DST_MOD/modules.dep") lines in modules.dep"
else
	warn "depmod is missing -- modules.dep stays the one from the build (package kmod)"
fi
info "$KO_N modules, release $KREL, $(du -sh "$DST_MOD" | cut -f1)"

# --- 3. h713-pq -----------------------------------------------------------
say "h713-pq"
PQ_DST="$TREE/usr/local/lib/h713-pq"
rm -rf "$PQ_DST"
install -d -m 0755 "$PQ_DST"
install -m 0755 "$H713_PQ_SRC/h713-pq" "$PQ_DST/h713-pq"
# The host's __pycache__ has no business here (x86 bytecode paths, and it would
# be made again on the first run anyway).
tar -C "$H713_PQ_SRC" --exclude=__pycache__ -cf - h713_pq | tar -C "$PQ_DST" -xf -
# The TSE reader (h713_pq/tse.py) loads the project's one TFD walk, tools/tse_dump.py,
# and looks for it next to the package on a device (Q2). Without it "--source tse"
# fails with a clear message; with it the board's own gamma curve is one command away.
install -m 0644 "$PROJECT_ROOT/tools/tse_dump.py" "$PQ_DST/h713_pq/tse_dump.py"
[[ -r "$H713_PQ_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_PQ_SRC/README.md" "$TREE/usr/local/share/doc/h713-pq/README.md"
# The entry point does sys.path.insert(0, Path(__file__).resolve().parent);
# resolve() follows the symlink, so it finds the package in /usr/local/lib.
install -d "$TREE/usr/local/bin"
ln -sfn ../lib/h713-pq/h713-pq "$TREE/usr/local/bin/h713-pq"
# Compatibility: the old names stay reachable as symlinks (113 B.4). Only the
# programs, not the unit -- a unit symlink would be an alias and would give two
# names for the same service.
ln -sfn h713-tv                "$TREE/usr/local/sbin/hy310-tv"
ln -sfn h713-pq                "$TREE/usr/local/bin/hy310-pq"
info "/usr/local/lib/h713-pq + symlink /usr/local/bin/h713-pq ($(du -sh "$PQ_DST" | cut -f1))"

# --- 4. h713-focus ---------------------------------------------------------
say "h713-focus"
install -d -m 0755 "$TREE/usr/local/bin"
install -m 0755 "$H713_FOCUS_SRC/h713-focus" "$TREE/usr/local/bin/h713-focus"
[[ -r "$H713_FOCUS_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_FOCUS_SRC/README.md" \
		"$TREE/usr/local/share/doc/h713-focus/README.md"
# The earlier name in the old tree was simply "focus" (legacy/tools/focus).
# There is deliberately NO symlink for it: the old script drove with cmd 1/2
# and without any check; whoever calls it from a script should notice the
# difference instead of inheriting it.
info "/usr/local/bin/h713-focus ($(wc -l < "$H713_FOCUS_SRC/h713-focus") lines)"

# --- 5. h713-cam -----------------------------------------------------------
say "h713-cam"
install -m 0755 "$H713_CAM_SRC/h713-cam" "$TREE/usr/local/bin/h713-cam"
[[ -r "$H713_CAM_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_CAM_SRC/README.md" \
		"$TREE/usr/local/share/doc/h713-cam/README.md"
# Without uvcvideo in the module tree h713-cam says so itself -- but the build
# should say it earlier than the device does.
if ! find "$DST_MOD" -name 'uvcvideo.ko*' -print -quit | grep -q .; then
	warn "uvcvideo.ko is missing from the module tree $MODROOT -- h713-cam will then find no camera"
fi
info "/usr/local/bin/h713-cam ($(wc -l < "$H713_CAM_SRC/h713-cam") lines)"

# --- 5b. h713-autofocus ----------------------------------------------------
say "h713-autofocus"
install -m 0755 "$H713_AF_SRC/h713-autofocus" "$TREE/usr/local/bin/h713-autofocus"
info "/usr/local/bin/h713-autofocus ($(wc -l < "$H713_AF_SRC/h713-autofocus") lines)"

# --- 6. blob guard ---------------------------------------------------------
blob_guard "$TREE"

# In addition: /lib/firmware should be empty or not exist at all. What is
# needed is put in by the installer (108 §2).
if [[ -d "$TREE/lib/firmware" ]]; then
	# regulatory.db* is wireless-regdb (ISC licence, free) -- no blob, no suspicion.
	FW_N=$(find "$TREE/lib/firmware" -type f -not -name 'regulatory.db*' | wc -l)
	if ((FW_N > 0)); then
		warn "/lib/firmware carries $FW_N files -- check whether that is intended:"
		find "$TREE/lib/firmware" -type f -not -name 'regulatory.db*' -printf '       /lib/firmware/%P\n' >&2
	else
		say "/lib/firmware is empty (the firmware comes from the installer)"
	fi
else
	say "/lib/firmware does not exist (the firmware comes from the installer)"
fi
