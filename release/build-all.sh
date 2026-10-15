#!/usr/bin/env bash
# release/build-all.sh -- from a fresh clone to an installable image, one entry point.
#
#   release/build-all.sh --version v0.10 [--board hy310] [--variant NAME] [--vendor DIR]
#                        [--wifi-env FILE] [--jobs N] [--skip-bl31] [--skip-uboot]
#                        [--skip-kernel] [--skip-rootfs] [--test-image] [--standby] [--dry-run]
#
# --board <id> (default hy310) picks boards/<id>/board.env: the installer
# profile, the kernel DTB the FIT carries, the U-Boot base defconfig and the
# image name ($IMAGE_NAME-$VERSION). The rule of doku/121 §5 is enforced here:
# no image for a board nobody has tested -- a board that is not STATUS=verified
# (an owner reported a green run) or has no installer profile is refused.
# --variant <name> is required for a board with VARIANTS (one board, several stock
# firmwares, boards/README.md): boards/<id>/variants/<name>/variant.env is read after
# board.env, and its STATUS, IMAGE_NAME and DRAM_CLK are what counts.
#
# --test-image is the one named way past that (plan/stufe-5.md): a partial/profile-only
# board with PROFILE, KERNEL_DTB and a U-Boot base gets $IMAGE_NAME-$VERSION-TEST, marked
# test_for=$PROFILE[/<variant>] in its table, for its own owner to try -- h713-install writes it on
# that board alone and only with --test-image. Not a release, no claim of support.
#
# crust, the ARISC firmware: a board that names CRUST_DEFCONFIG in board.env gets one crust build
# (step 1b, from mainline/external/crust or CRUST_SRC=<checkout>, the series crust-h713/ mirrors).
# It goes into the release U-Boot's FIT as "scp", which BL31 starts, and into the rootfs as
# /lib/firmware/<board>-crust.bin, the name the board's device tree gives the arisc driver; step
# 10 checks that both are this build (release/check-crust.py). The installer and the probe U-Boot
# never carry it.
# --standby offers the standby, experimental (TODO 2.29): BL31 with PSCI SYSTEM_SUSPEND and the rootfs
# with suspend allowed, so that h713-power (on every image) offers it in its countdown; power.conf's
# default stays poweroff. Only for STANDBY=sr, which follows from CRUST_DEFCONFIG on a verified board.
#
# Order (doku/116 P4):
#   1 bl31  1b crust  2 U-Boot (+ split SPL/proper + environment with CRC)  2b installer U-Boot (ums)
#   2b2 probe U-Boot (h713_probe)  2c sunxi-fel (trap door)  3 kernel (+ modules)
#   4 aic8800  5 Debian keyring (pinned)  6 sysroot + h713-tv, h713-osd cross-built  7 rootfs
#   8 ext4 inputs  9 image  10 check (with --vendor: the full self-test)  11 stamp
#
# Runs on the work machine and drives the container h713-build (doku/50 §Bauen);
# nothing is built on the host (memory: "build only in the container"). Everything
# that used to be copied to tftp/ by hand is made here under mainline/build/out/
# and is handed to the image builder explicitly -- tftp/ is a development shelf
# from now on, not an input.
#
# What this script does NOT do: make the extract out of the user's own dump
# (h713-install does that while installing) and send anything to the device.
#
# The paths of the building blocks are in one block below, so that the move to
# installer/ and rootfs/ (doku/116 P3) changes those lines and nothing else.
#
# Reproducible (ROADMAP "Reproducible builds"): SOURCE_DATE_EPOCH is the committer
# date of the checkout and reaches every step in the container. build.sh turns it
# into TF-A's build message, the kernel's uname line and relative module paths;
# U-Boot, its mkimage (the FIT's timestamp), build-rootfs.sh and build-mesa.sh
# read it themselves. The stamp says "reproducible: yes" or "no, because ...".
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# --- paths (P3 changes only these) -----------------------------------------
MAINLINE="$ROOT/mainline"
# Both layouts: release repository (installer/, rootfs/ under the root) and
# working directory (analyse/release/arbeit/...). The repository layout wins.
if [[ -d "$ROOT/installer" && -d "$ROOT/rootfs" ]]; then
	INSTALLER="$ROOT/installer"; EXTRACTOR="$ROOT/installer/h713-extract"; ROOTFS="$ROOT/rootfs"
else
	INSTALLER="$ROOT/analyse/release/arbeit/r0-fel"; EXTRACTOR="$ROOT/analyse/release/arbeit/r2-extract/h713-extract"; ROOTFS="$ROOT/analyse/release/arbeit/rootfs"
fi
USERSPACE="$ROOT/userspace"
CONTAINER=h713-build
# What is $ROOT called inside the container? Derive it from the container's
# mounts, do not assume -- the release repository can sit below the mounted work
# directory (e.g. /opt/Projekte/h713/repo-neu -> /work/repo-neu), doku/116 P3.
container_path() {
	local p=${1:-$ROOT} src dst
	while IFS=' ' read -r src dst; do
		[[ -n "$src" ]] || continue
		if [[ "$p" == "$src" || "$p" == "$src"/* ]]; then
			printf '%s%s' "$dst" "${p#"$src"}"; return 0
		fi
	done < <(podman inspect -f '{{range .Mounts}}{{.Source}} {{.Destination}}{{"\n"}}{{end}}' "$CONTAINER" 2>/dev/null)
	return 1
}
WORK=$(container_path) || { echo "error: $ROOT is in no mount of the container $CONTAINER" >&2; exit 1; }
# ---------------------------------------------------------------------------
# U-Boot is <board base> + <role fragment> (docs/uboot/README.md "Which defconfig"):
# the base comes from board.env (UBOOT_DEFCONFIG, else UBOOT_BOARD), the roles are
# fixed here (resolved into UBOOT_BASE below). The probe
# keeps its own base at 624 MHz and takes no role -- it must never run at the
# clock of a board someone happens to be building for.
UBOOT_RELEASE_ROLE=release                            # boots the eMMC, ums + fastboot
UBOOT_INSTALLER_ROLE=installer                        # FEL -> ums, for h713-install
UBOOT_PROBE_DEFCONFIG=h713_probe_defconfig            # FEL -> h713_probe, for unknown H713 devices
KEYRING_DEB_URL="https://deb.debian.org/debian/pool/main/d/debian-archive-keyring/debian-archive-keyring_2025.1_all.deb"
KEYRING_DEB_SHA256=9ea7778e443144ca490668737a8ab22dd3e748bb99e805e22ec055abeb3c7fac
KEYRING_IN_DEB=./usr/share/keyrings/debian-archive-keyring.pgp   # byte-identical to the .gpg used so far (12.09.)
# libwayland-dev, libwayland-egl-backend-dev, wayland-protocols, libglvnd-dev: mesa's Wayland platform and glvnd (rootfs/mesa/build-mesa.sh);
# libglvnd-dev is also where h713-warp finds libEGL.so and libGLESv2.so now (the dispatchers, no longer in the mesa stage)
# libva-dev: the VA-API headers megi's libva-v4l2_request driver is built against (rootfs/libva/build-libva.sh);
# the driver is built by that script on demand, not by this one: the base image does not carry it (profile media does)
SYSROOT_PACKAGES=libc6-dev,libgcc-14-dev,libstdc++-14-dev,libdrm-dev,libasound2-dev,zlib1g-dev,libwayland-dev,libwayland-egl-backend-dev,wayland-protocols,libglvnd-dev,libva-dev
DEBIAN_SUITE=trixie
DEBIAN_MIRROR=http://deb.debian.org/debian

VERSION= BOARD=hy310 VARIANT= VENDOR= WIFI_ENV= JOBS=$(nproc) DRY=0 TEST_IMAGE=0 WANT_STANDBY=0
SKIP_BL31=0 SKIP_UBOOT=0 SKIP_KERNEL=0 SKIP_ROOTFS=0
while (($#)); do
	case "$1" in
	--version)   VERSION=${2:?}; shift 2 ;;
	--board)     BOARD=${2:?}; shift 2 ;;
	--variant)   VARIANT=${2:?}; shift 2 ;;
	--vendor)    VENDOR=$(cd "${2:?}" && pwd); shift 2 ;;
	--wifi-env)  WIFI_ENV=$(readlink -f "${2:?}"); shift 2 ;;
	--jobs)      JOBS=${2:?}; shift 2 ;;
	--skip-bl31)   SKIP_BL31=1; shift ;;
	--skip-uboot)  SKIP_UBOOT=1; shift ;;
	--skip-kernel) SKIP_KERNEL=1; shift ;;
	--skip-rootfs) SKIP_ROOTFS=1; shift ;;
	--test-image)  TEST_IMAGE=1; shift ;;
	--standby)     WANT_STANDBY=1; shift ;;
	--dry-run)   DRY=1; shift ;;
	-h|--help)   sed -n '2,46p' "$0"; exit 0 ;;
	*) echo "unknown: $1" >&2; exit 2 ;;
	esac
done
# --- board (doku/121 §3 and §5) ---------------------------------------------
BOARD_ENV="$ROOT/boards/$BOARD/board.env"
if [[ ! -f "$BOARD_ENV" ]]; then
	echo "unknown board '$BOARD': there is no $BOARD_ENV" >&2
	echo "known boards: $(cd "$ROOT/boards" 2>/dev/null && ls -d -- */ | tr -d / | tr '\n' ' ')" >&2
	exit 2
fi
unset CRUST_DEFCONFIG    # a board key only: never from the caller's environment
# shellcheck source=/dev/null
source "$BOARD_ENV"
[[ "${BOARD_ID:-}" == "$BOARD" ]] || { echo "$BOARD_ENV says BOARD_ID='${BOARD_ID:-}', not '$BOARD'" >&2; exit 2; }
DRAM_CLK=
if [[ -n "${VARIANTS:-}" ]]; then
	if [[ " $VARIANTS " != *" ${VARIANT:-?} "* ]]; then
		echo "boards/$BOARD has one board and several stock firmwares: name one with --variant ($VARIANTS)" >&2
		exit 2
	fi
	VARIANT_ENV="$ROOT/boards/$BOARD/variants/$VARIANT/variant.env"
	[[ -f "$VARIANT_ENV" ]] || { echo "no $VARIANT_ENV" >&2; exit 2; }
	want=$VARIANT
	# shellcheck source=/dev/null
	source "$VARIANT_ENV"
	[[ "${VARIANT:-}" == "$want" ]] || { echo "$VARIANT_ENV says VARIANT='${VARIANT:-}', not '$want'" >&2; exit 2; }
	[[ -n "$DRAM_CLK" ]] || { echo "$VARIANT_ENV names no DRAM_CLK" >&2; exit 2; }
elif [[ -n "$VARIANT" ]]; then
	echo "boards/$BOARD has no variants -- drop --variant $VARIANT" >&2
	exit 2
fi
UNIT=$BOARD${VARIANT:+/$VARIANT}                # what the rule, the messages and the stamp name
TEST_PROFILE=$PROFILE${VARIANT:+/$VARIANT}      # the installer's name for it, test_for in the table
UB_ENV=${DRAM_CLK:+DRAM_CLK=$DRAM_CLK }         # the variant's clock for build/uboot-build.sh
if [[ "${STATUS:-}" != verified ]]; then
	# --test-image is the named exception; everything else about the rule stays as it is.
	if ! ((TEST_IMAGE)) || [[ "${STATUS:-}" != partial && "${STATUS:-}" != profile-only ]]; then
		echo "no image for a board nobody has tested (doku/121 section 5): boards/$UNIT is STATUS=${STATUS:-unset}." >&2
		echo "A board becomes 'verified' when its owner reports a green run of our build; until then it gets" >&2
		echo "an installer profile and the probe (h713_probe), not an image." >&2
		exit 2
	fi
elif ((TEST_IMAGE)); then
	echo "boards/$UNIT is STATUS=verified: --test-image is for a board nobody has run (partial, profile-only). This one gets a release image." >&2
	exit 2
fi
if [[ -z "${PROFILE:-}" ]]; then
	if ((TEST_IMAGE)); then
		echo "boards/$BOARD names no installer PROFILE -- a test image needs one, or h713-install cannot tell whether it is standing on the board the image was built for" >&2
	else
		echo "boards/$BOARD is verified but names no installer PROFILE -- a release image needs one, or h713-install cannot recognise the board it is for" >&2
	fi
	exit 2
fi
[[ -n "${KERNEL_DTB:-}" ]] || { echo "boards/$BOARD names no KERNEL_DTB -- no device tree of ours has booted there" >&2; exit 2; }
[[ -n "${UBOOT_BOARD:-}" ]] || { echo "boards/$BOARD names no UBOOT_BOARD -- no U-Boot base defconfig of ours for it" >&2; exit 2; }
[[ -n "${IMAGE_NAME:-}" ]] || { echo "boards/$BOARD names no IMAGE_NAME" >&2; exit 2; }
# crust and the standby (header). The source must be the head crust-h713/SERIES.txt names, unless
# CRUST_SRC points somewhere else on purpose - then the stamp says so.
# A test image for one unverified board may carry it too: that is how the board gets verified (TODO 1.4).
STANDBY=none; [[ -n "${CRUST_DEFCONFIG:-}" && ( "${STATUS:-}" == verified || $TEST_IMAGE == 1 ) ]] && STANDBY=sr
if ((WANT_STANDBY)) && [[ "$STANDBY" != sr ]]; then
	echo "--standby: boards/$UNIT has STANDBY=$STANDBY -- only a verified board with a CRUST_DEFCONFIG, or a --test-image of a board with one, can offer it" >&2; exit 2
fi
CRUST_SRC_GIVEN=${CRUST_SRC:+1}; CRUST_SRC=${CRUST_SRC:-$MAINLINE/external/crust}
if [[ -n "${CRUST_DEFCONFIG:-}" ]]; then
	if [[ ! -f "$CRUST_SRC/Makefile" ]]; then
		if git config -f "$ROOT/.gitmodules" --get-regexp '\.path$' 2>/dev/null | grep -q ' mainline/external/crust$'; then
			echo "no crust source at $CRUST_SRC -- git submodule update --init mainline/external/crust, or CRUST_SRC=<checkout>" >&2
		else
			echo "boards/$BOARD names CRUST_DEFCONFIG, and there is no crust submodule yet: CRUST_SRC=<checkout of the head crust-h713/SERIES.txt names> (crust-h713/README.md says how to make one)" >&2
		fi
		exit 2
	fi
	CRUST_HEAD=$(git -C "$CRUST_SRC" rev-parse HEAD 2>/dev/null) || { echo "$CRUST_SRC is no git checkout: crust's version text needs one" >&2; exit 2; }
	CRUST_MIRROR=$(awk '$1 == "head" { print $2 }' "$ROOT/crust-h713/SERIES.txt" 2>/dev/null)
	if [[ "$CRUST_HEAD" != "$CRUST_MIRROR" && -z "$CRUST_SRC_GIVEN" ]]; then
		echo "crust at $CRUST_HEAD, but crust-h713/SERIES.txt names ${CRUST_MIRROR:-nothing} -- update the submodule or the mirror" >&2; exit 2
	fi
fi
# The kernel defconfig: board.env may name one; otherwise config/versions.env pins it (build.sh does the same).
KDEF=${KERNEL_DEFCONFIG:-$(sed -n 's/^KERNEL_DEFCONFIG=\([^ #]*\).*/\1/p' "$MAINLINE/config/versions.env")}
[[ -n "$KDEF" ]] || { echo "no KERNEL_DEFCONFIG in boards/$BOARD/board.env or config/versions.env" >&2; exit 2; }
# The U-Boot base: board.env may name its defconfig outright (cstenger's boards do,
# their UBOOT_BOARD is the hyphenated id and no defconfig name), else it is
# <UBOOT_BOARD>_defconfig. Same resolution as mainline/build/build.sh; uboot-build.sh
# takes the base without the suffix. For hy310 this is hy310, as before.
UBOOT_BASE=${UBOOT_DEFCONFIG:-${UBOOT_BOARD}_defconfig}; UBOOT_BASE=${UBOOT_BASE%_defconfig}
[[ -n "$VERSION" ]] || { echo "--version vX.Y is missing (name of the image: $IMAGE_NAME-vX.Y)" >&2; exit 2; }
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+(-[a-z0-9]+)?$ ]] || { echo "--version: expected vX.Y or vX.Y-beta, not '$VERSION'" >&2; exit 2; }
NAME="$IMAGE_NAME-$VERSION"
((TEST_IMAGE)) && NAME="$NAME-TEST"        # the name is the first place it has to say so
OUT="$MAINLINE/build/out"
DELIVERY="$INSTALLER/out"
# --- reproducible build ---------------------------------------------------
# One clock for everything that embeds a build time: the committer date of HEAD
# (the release repository, else mainline/). The stamp's "reproducible:" line
# names what would still make a second build differ: local changes (a dirty or
# moved submodule counts as one), reused building blocks (--skip-*), a private
# --wifi-env. The rootfs is reproducible only against the same mirror state.
REPRO_GIT=$ROOT; git -C "$REPRO_GIT" rev-parse -q --verify HEAD >/dev/null 2>&1 || REPRO_GIT=$MAINLINE
REPRO_WHY=()
if SOURCE_DATE_EPOCH=$(git -C "$REPRO_GIT" log -1 --format=%ct 2>/dev/null) && [[ -n "$SOURCE_DATE_EPOCH" ]]; then
	REPRO_COMMIT=$(git -C "$REPRO_GIT" rev-parse --short HEAD)
	n=$(git -C "$REPRO_GIT" status --short 2>/dev/null | wc -l); ((n)) && REPRO_WHY+=("$n local changes")
else
	SOURCE_DATE_EPOCH=$(date +%s); REPRO_COMMIT=none; REPRO_WHY+=("not a git checkout")
fi
export SOURCE_DATE_EPOCH
((SKIP_BL31 || SKIP_UBOOT || SKIP_KERNEL || SKIP_ROOTFS)) && REPRO_WHY+=("--skip-* reused earlier building blocks")
[[ -n "${CRUST_DEFCONFIG:-}" && "$CRUST_HEAD" != "$CRUST_MIRROR" ]] && REPRO_WHY+=("crust ${CRUST_HEAD:0:12} from CRUST_SRC is not the head crust-h713/SERIES.txt names")
[[ -n "$WIFI_ENV" ]] && REPRO_WHY+=("--wifi-env is a private input")
REPRO_LINE="reproducible: yes (SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH, commit $REPRO_COMMIT)"
((${#REPRO_WHY[@]})) && { w=$(printf '%s; ' "${REPRO_WHY[@]}"); REPRO_LINE="reproducible: no, because ${w%; }"; }

say()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nerror: %s\n' "$*" >&2; exit 1; }
# The eGON SPL image must be exactly 32 KiB: this script splits the sunxi image at 32768 and the
# hy310-spl partition is 64 sectors. mkimage rounds to 8 KiB blocks, so anything else means the SPL
# outgrew its 32672 bytes and would be cut in half - refuse before it reaches a device (M3/M4, 16.09.).
spl_size_ok() {
	local n; n=$(stat -c %s "$1" 2>/dev/null || echo 0)
	[[ "$n" -eq 32768 ]] || die "$1 is $n bytes, not 32768 -- the SPL no longer fits its 32 KiB slot"
}
in_container()      { podman exec -e JOBS="$JOBS" -e SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" "$CONTAINER" bash -lc "$*"; }
in_container_root() { podman exec -u root -e JOBS="$JOBS" -e SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" "$CONTAINER" bash -lc "$*"; }
# host path -> container path
c() { printf '%s' "${1/#$ROOT/$WORK}"; }
T0=$(date +%s)
elapsed() { local s=$(( $(date +%s) - T0 )); printf '%d min %02d s' $((s/60)) $((s%60)); }

say "build-all $NAME  ($(date '+%Y-%m-%d %H:%M'))"
info "root $ROOT"
info "board $UNIT ($STATUS, profile $TEST_PROFILE, DTB $KERNEL_DTB, U-Boot $UBOOT_BASE + roles${DRAM_CLK:+, DRAM $DRAM_CLK MHz})"
info "crust ${CRUST_DEFCONFIG:-none}, standby $STANDBY$( ((WANT_STANDBY)) && echo ', offered (--standby)' )"
info "$REPRO_LINE"
((TEST_IMAGE)) && { say "TEST IMAGE for $UNIT (STATUS=$STATUS) -- not a release"
	info "Nobody has reported a green run here. The table is marked test_for=$TEST_PROFILE, so h713-install"
	info "writes it on this board alone and only with --test-image; the owner's full dump is the way back."; }
((WANT_STANDBY)) && { say "STANDBY offered (--standby) -- experimental"
	info "Suspend through crust is allowed; h713-power offers it in its countdown. The default stays power-off (power.conf default = poweroff); 'h713-power set default standby' makes it the default on the device."; }
((DRY)) && info "DRY RUN -- nothing is built"

# --- 0. prerequisites -------------------------------------------------------
say "0/11 prerequisites"
for w in podman python3 curl ar tar sha256sum; do command -v "$w" >/dev/null || die "missing on the host: $w"; done
st=$(podman inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo missing)
case "$st" in
	running) info "container $CONTAINER is running" ;;
	created|exited|stopped) ((DRY)) || podman start "$CONTAINER" >/dev/null; info "container $CONTAINER started (was: $st)" ;;
	*) die "container $CONTAINER is missing -- recipe in doku/50-befehle.md §Bauen" ;;
esac
((DRY)) || in_container 'clang --version | head -1; command -v mmdebstrap mke2fs depmod dtc >/dev/null || { echo "tools are missing in the container (mmdebstrap/mke2fs/depmod/dtc)"; exit 1; }' | sed 's/^/    /'
for f in "$INSTALLER/h713-mkimage" "$INSTALLER/mkimage-inputs.sh" "$ROOTFS/build-rootfs.sh" "$EXTRACTOR" "$MAINLINE/build/build.sh" "$MAINLINE/build/uboot-build.sh"; do
	[[ -e "$f" ]] || die "missing: $f"
done
[[ -z "$VENDOR" || -d "$VENDOR/boot/mips" ]] || die "--vendor $VENDOR does not look like an h713-extract output (no boot/mips/)"
mkdir -p "$OUT" "$DELIVERY"
((DRY)) && { info "would build: bl31$( ((WANT_STANDBY)) && echo ' with SYSTEM_SUSPEND')${CRUST_DEFCONFIG:+, crust $CRUST_DEFCONFIG}, U-Boot ($UBOOT_BASE + $UBOOT_RELEASE_ROLE${DRAM_CLK:+ + DRAM $DRAM_CLK MHz}${CRUST_DEFCONFIG:+ + scp}) + env, installer U-Boot ($UBOOT_BASE + $UBOOT_INSTALLER_ROLE${DRAM_CLK:+ + DRAM $DRAM_CLK MHz}), probe U-Boot ($UBOOT_PROBE_DEFCONFIG), sunxi-fel, kernel + modules (BOARD=$BOARD, $KERNEL_DTB), aic8800, keyring, sysroot + h713-tv, rootfs, inputs, image $NAME"; exit 0; }

# --- 1. bl31 ---------------------------------------------------------------
if ((SKIP_BL31)) && [[ -f "$OUT/bl31.bin" ]]; then say "1/11 bl31 -- skipped (--skip-bl31, $OUT/bl31.bin is there)"
else
	say "1/11 bl31 (TF-A)"
	# Build from scratch. Reason (12.09., P3.9): the work tree held a bl31 from
	# 10.09. built with assertions enabled (49260 instead of 45164 bytes). make
	# saw everything as up to date and never replaced it -- it sits in v0.8 to v0.10.
	rm -rf "$MAINLINE/external/arm-trusted-firmware/build"
	in_container "cd $WORK/mainline && BOARD=$BOARD H713_STANDBY=$WANT_STANDBY H713_TEST_IMAGE=$TEST_IMAGE build/build.sh bl31" | tail -3 | sed 's/^/    /'
fi
[[ -f "$OUT/bl31.bin" ]] || die "no bl31.bin"

# --- 1b. crust --------------------------------------------------------------
# One build feeds the FIT and the rootfs. A few seconds, so always from scratch; the or1k
# compiler is built once (mainline/tools/or1k-toolchain/, ~6 min) and then kept.
CR_O="$MAINLINE/build/crust"; OR1K="$MAINLINE/build/toolchain/or1k"
rm -rf "$CR_O" "$OUT/scp.bin" "$OUT/crust.config"   # no crust of an earlier board in this one's image
if [[ -n "${CRUST_DEFCONFIG:-}" ]]; then
	say "1b/11 crust $CRUST_DEFCONFIG (${CRUST_HEAD:0:12})"
	# Reused only with the stamp the toolchain script writes last, for its pinned sources: an unfinished
	# build or a compiler copied in from elsewhere is built again.
	OR1K_STAMP=$(sh "$MAINLINE/tools/or1k-toolchain/build-or1k-toolchain.sh" --stamp)
	if [[ ! -x "$OR1K/bin/or1k-elf-gcc" || "$(cat "$OR1K/.h713-or1k-toolchain" 2>/dev/null)" != "$OR1K_STAMP" ]]; then
		info "building the or1k toolchain first, no finished one of the pinned sources is there (log: $OUT/or1k-toolchain.log)"
		in_container "OR1K_PREFIX=$(c "$OR1K") $WORK/mainline/tools/or1k-toolchain/build-or1k-toolchain.sh" > "$OUT/or1k-toolchain.log" 2>&1 \
			|| { tail -20 "$OUT/or1k-toolchain.log"; die "the or1k toolchain failed (log: $OUT/or1k-toolchain.log)"; }
	fi
	CS=$(container_path "$CRUST_SRC") || die "$CRUST_SRC is in no mount of the container $CONTAINER"
	# crust's version text (scripts/version.sh) asks git inside the container. A worktree's .git file and a
	# shared clone's alternates name host paths the container does not have: the text would be v0.6.10000
	# with the hash "unknown", and step 10 refuses that. So git gets its directories by their container paths.
	CG=$(container_path "$(git -C "$CRUST_SRC" rev-parse --absolute-git-dir)") || die "the git directory of $CRUST_SRC is in no mount of the container"
	CR_GIT="GIT_DIR=$CG GIT_WORK_TREE=$CS"; alt="$(git -C "$CRUST_SRC" rev-parse --path-format=absolute --git-common-dir)/objects/info/alternates"
	if [[ -s "$alt" ]]; then
		ca=; while IFS= read -r a; do [[ -n "$a" && "$a" != \#* ]] || continue
			a=$(container_path "$a") || die "an alternate object store of $CRUST_SRC is in no mount of the container"; ca+=${ca:+:}$a; done < "$alt"
		CR_GIT+=" GIT_ALTERNATE_OBJECT_DIRECTORIES=$ca"
	fi
	in_container "export PATH=$(c "$OR1K")/bin:\$PATH $CR_GIT; cd $CS && make -s CROSS_COMPILE=or1k-elf- OBJ=$(c "$CR_O") $CRUST_DEFCONFIG && make -s CROSS_COMPILE=or1k-elf- OBJ=$(c "$CR_O") scp" > "$OUT/crust-build.log" 2>&1 \
		|| { tail -20 "$OUT/crust-build.log"; die "crust failed (log: $OUT/crust-build.log)"; }
	install -m 0644 "$CR_O/scp/scp.bin" "$OUT/scp.bin"
	install -m 0644 "$CRUST_SRC/.config" "$OUT/crust.config"
	CRUST_VERSION=$(sed -n 's/^#define VERSION_STRING "\(.*\)"$/\1/p' "$CR_O/include/version.h")
	CRUST_HASH=$(sed -n 's/^#define VERSION_HASH "\(.*\)"$/\1/p' "$CR_O/include/version.h")   # contract v5 on
	[[ -z "$CRUST_HASH" || "$CRUST_HASH" == "g${CRUST_HEAD:0:12}"* ]] \
		|| die "crust's notify text names the commit '$CRUST_HASH', the checkout is at ${CRUST_HEAD:0:12}: git did not see it in the container"
	info "crust $CRUST_VERSION${CRUST_HASH:+-$CRUST_HASH}, $(stat -c %s "$OUT/scp.bin") bytes, sha256 $(sha256sum "$OUT/scp.bin" | cut -c1-16)"
fi

# --- 2. U-Boot: build, split, environment -----------------------------------
UB_O="$MAINLINE/build/uboot-release"
if ((SKIP_UBOOT)) && [[ -f "$OUT/spl-release.bin" && -f "$OUT/uboot-proper-release.bin" && -f "$OUT/hy310-env-release.bin" ]]; then
	say "2/11 U-Boot -- skipped (--skip-uboot, the building blocks are there)"
else
	say "2/11 U-Boot $UBOOT_BASE + $UBOOT_RELEASE_ROLE"
	rm -rf "$UB_O"   # as with bl31: no old objects, no old .config
	# SCP= for this role alone: crust in the release FIT, never in the installer's or the probe's
	SCP_ENV=; [[ -f "$OUT/scp.bin" ]] && SCP_ENV="SCP=$(c "$OUT")/scp.bin "
	in_container "cd $WORK/mainline && ${UB_ENV}${SCP_ENV}build/uboot-build.sh $(c "$UB_O") $UBOOT_BASE $UBOOT_RELEASE_ROLE" > "$OUT/uboot-build.log" 2>&1 || { tail -20 "$OUT/uboot-build.log"; die "U-Boot build failed (log: $OUT/uboot-build.log)"; }
	B="$UB_O/u-boot-sunxi-with-spl.bin"; [[ -f "$B" ]] || die "no $B"
	spl_size_ok "$UB_O/spl/sunxi-spl.bin"
	# SPL = the first 32 KiB (eGON.BT0), the rest is U-Boot proper (doku/50 §Bauen)
	head -c 32768 "$B" > "$OUT/spl-release.bin"
	tail -c +32769 "$B" > "$OUT/uboot-proper-release.bin"
	[[ "$(head -c 12 "$OUT/spl-release.bin" | tail -c 8)" == "eGON.BT0" ]] || die "the SPL carries no eGON.BT0 marker"
	# The built-in default environment as a 64 KiB image with a CRC (doku/60 §Die U-Boot-Umgebung im Abbild).
	# u-boot-initial-env lists bootcmd twice (defconfig + hy310.env, identical); drop the duplicates.
	in_container "cd $WORK/mainline/external/u-boot && make -s O=$(c "$UB_O") ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu' LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump READELF=llvm-readelf STRIP=llvm-strip u-boot-initial-env" >/dev/null
	awk '!seen[$0]++' "$UB_O/u-boot-initial-env" > "$UB_O/u-boot-initial-env.dedup"
	in_container "$(c "$UB_O")/tools/mkenvimage -s 0x10000 -o $(c "$OUT")/hy310-env-release.bin $(c "$UB_O")/u-boot-initial-env.dedup"
	chmod 0644 "$OUT/hy310-env-release.bin"
	python3 - "$OUT/hy310-env-release.bin" <<'PY'
import sys, zlib, struct
d = open(sys.argv[1], "rb").read(); assert len(d) == 65536, len(d)
assert struct.unpack("<I", d[:4])[0] == zlib.crc32(d[4:]) & 0xffffffff, "CRC"
e = [x.decode() for x in d[4:].split(b"\0") if x and x != b"\xff" * len(x)]
g = [x for x in e if x.startswith("h713_gate=")]; assert g, "h713_gate is missing"
print("    environment: %d entries, %s" % (len(e), g[0]))
PY
	v=$(strings -n 8 "$OUT/uboot-proper-release.bin" | grep -m1 '^U-Boot 20' || true)
	info "U-Boot $v"
fi
# 2b. The installer U-Boot (FEL -> ums): same fork, own role fragment. Without it
#     h713-install cannot share the drive out of a fresh clone (P3, 12.09.).
UBI_O="$MAINLINE/build/uboot-installer"
if ((SKIP_UBOOT)) && [[ -f "$OUT/u-boot-installer.bin" ]]; then
	say "2b/11 installer U-Boot -- skipped"
else
	say "2b/11 installer U-Boot $UBOOT_BASE + $UBOOT_INSTALLER_ROLE (ums)"
	rm -rf "$UBI_O"
	in_container "cd $WORK/mainline && ${UB_ENV}build/uboot-build.sh $(c "$UBI_O") $UBOOT_BASE $UBOOT_INSTALLER_ROLE" > "$OUT/uboot-installer-build.log" 2>&1 || { tail -20 "$OUT/uboot-installer-build.log"; die "installer U-Boot failed (log: $OUT/uboot-installer-build.log)"; }
	[[ -f "$UBI_O/u-boot-sunxi-with-spl.bin" ]] || die "no $UBI_O/u-boot-sunxi-with-spl.bin"
	spl_size_ok "$UBI_O/spl/sunxi-spl.bin"
	cp "$UBI_O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-installer.bin"
	grep -q 'ums 0 mmc 1' "$OUT/u-boot-installer.bin" || die "the installer U-Boot carries no 'ums 0 mmc 1' in its bootcmd"
fi
# 2b2. The probe (FEL -> h713_probe): for H713 devices we do not know. Same fork,
#      own defconfig, DRAM at 624 instead of 792 -- the conservative end of the
#      range our two known boards span (doku/120 §4). Writes nothing; belongs next
#      to u-boot-installer.bin in the delivery directory.
UBP_O="$MAINLINE/build/uboot-probe"
if ((SKIP_UBOOT)) && [[ -f "$OUT/u-boot-h713-probe.bin" ]]; then
	say "2b2/11 probe U-Boot -- skipped"
else
	say "2b2/11 probe U-Boot $UBOOT_PROBE_DEFCONFIG (h713_probe)"
	rm -rf "$UBP_O"
	in_container "cd $WORK/mainline && build/uboot-build.sh $(c "$UBP_O") $UBOOT_PROBE_DEFCONFIG" > "$OUT/uboot-probe-build.log" 2>&1 || { tail -20 "$OUT/uboot-probe-build.log"; die "probe U-Boot failed (log: $OUT/uboot-probe-build.log)"; }
	[[ -f "$UBP_O/u-boot-sunxi-with-spl.bin" ]] || die "no $UBP_O/u-boot-sunxi-with-spl.bin"
	spl_size_ok "$UBP_O/spl/sunxi-spl.bin"
	cp "$UBP_O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-h713-probe.bin"
	grep -q 'h713_probe' "$OUT/u-boot-h713-probe.bin" || die "the probe U-Boot knows no h713_probe"
	# The probe must never be shipped with this board's clock: 792 on somebody
	# else's RAM is exactly the guessing it is meant to avoid.
	grep -q 'CONFIG_DRAM_CLK=624' "$MAINLINE/external/u-boot/configs/$UBOOT_PROBE_DEFCONFIG" || die "the probe defconfig is not at 624 MHz"
fi
# 2c. sunxi-fel with the S44 trap door (fork commit 269dfa2): the tool h713-install
#     reaches the device with at all. A host program, built in the container
#     (x86_64, libusb-1.0) -- belongs next to h713-install in the delivery directory.
if ((SKIP_UBOOT)) && [[ -x "$OUT/sunxi-fel" ]]; then
	say "2c/11 sunxi-fel -- skipped"
else
	say "2c/11 sunxi-fel (trap door, host program)"
	in_container "make -s -C $WORK/mainline/external/sunxi-tools clean >/dev/null 2>&1; make -s -C $WORK/mainline/external/sunxi-tools sunxi-fel" > "$OUT/sunxi-fel-build.log" 2>&1 || { tail -20 "$OUT/sunxi-fel-build.log"; die "building sunxi-fel failed (log: $OUT/sunxi-fel-build.log)"; }
	cp "$MAINLINE/external/sunxi-tools/sunxi-fel" "$OUT/sunxi-fel"
	# (no grep -q behind a pipe: with pipefail strings dies of SIGPIPE and the test fails)
	[[ $(strings -n 6 "$OUT/sunxi-fel" | grep -c 'FEL trap door') -gt 0 ]] || die "sunxi-fel without the trap-door marker -- wrong revision?"
fi

# --- 3. kernel + modules ----------------------------------------------------
if ((SKIP_KERNEL)) && [[ -f "$OUT/h713-kernel.fit" ]]; then say "3/11 kernel -- skipped (--skip-kernel)"
else
	say "3/11 kernel (board defconfig alone = delivery; BOARD=$BOARD, DTB $KERNEL_DTB)"
	in_container "cd $WORK/mainline && BOARD=$BOARD build/build.sh kernel" > "$OUT/kernel-build.log" 2>&1 || { tail -20 "$OUT/kernel-build.log"; die "kernel build failed (log: $OUT/kernel-build.log)"; }
	grep -o 'applied [0-9]* series patches' "$OUT/kernel-build.log" | sed 's/^/    /' || true
fi
# The FIT names its configuration after the DTB (build.sh); an image for board X
# must not quietly carry board Y's tree.
[[ -f "$OUT/$KERNEL_DTB.dtb" ]] || die "no $OUT/$KERNEL_DTB.dtb -- build.sh did not build the DTB of boards/$BOARD"
grep -q "conf-$KERNEL_DTB" "$OUT/h713-kernel.fit" || die "h713-kernel.fit carries no configuration conf-$KERNEL_DTB"
TREE=$(ls -dt "$MAINLINE"/build/linux-6.18.38-*/ | head -1); TREE=${TREE%/}
[[ -f "$TREE/Module.symvers" ]] || die "no built kernel tree under $MAINLINE/build/"
H=$(basename "$TREE" | sed 's/linux-6.18.38-//' | cut -c1-8)
MODROOT="$MAINLINE/build/modroot.$H"
if ((SKIP_KERNEL)) && [[ -d "$MODROOT/lib/modules" ]]; then info "module tree $MODROOT is there"
else
	in_container "cd $(c "$TREE") && make -s ARCH=arm64 LLVM=1 INSTALL_MOD_PATH=$(c "$MODROOT") modules_install" >/dev/null
fi
KREL=$(ls "$MODROOT/lib/modules" | head -1)
info "tree $H, release $KREL, $(find "$MODROOT" -name '*.ko' | wc -l) modules"

# --- 4. aic8800 (always after the kernel, against the same tree) ------------
say "4/11 aic8800 modules against tree $H"
in_container "cd $WORK/mainline && BOARD=$BOARD build/build.sh aic8800" > "$OUT/aic8800-build.log" 2>&1 || { tail -20 "$OUT/aic8800-build.log"; die "aic8800 build failed"; }
for k in aic8800_bsp aic8800_fdrv; do [[ -f "$OUT/modules/$k.ko" ]] || die "missing: $OUT/modules/$k.ko"; done
info "bsp + fdrv are there ($(stat -c %s "$OUT/modules/aic8800_fdrv.ko") bytes fdrv)"

# --- 5. Debian keyring, pinned ----------------------------------------------
say "5/11 Debian keyring for $DEBIAN_SUITE"
KEYRING_DIR="$MAINLINE/build/cache/keyring"; mkdir -p "$KEYRING_DIR"
KEYRING="$KEYRING_DIR/debian-archive-keyring.pgp"
if [[ ! -f "$KEYRING" ]]; then
	DEB="$MAINLINE/build/cache/$(basename "$KEYRING_DEB_URL")"
	[[ -f "$DEB" ]] || curl -fsSL -o "$DEB" "$KEYRING_DEB_URL"
	echo "$KEYRING_DEB_SHA256  $DEB" | sha256sum -c --quiet - || die "keyring package: the sha256 does not match -- do not use it"
	T=$(mktemp -d); ( cd "$T" && ar x "$DEB" && tar -xf data.tar.* "$KEYRING_IN_DEB" ) && cp "$T/$KEYRING_IN_DEB" "$KEYRING"; rm -rf "$T"
fi
info "$(basename "$KEYRING") ($(stat -c %s "$KEYRING") bytes) out of $(basename "$KEYRING_DEB_URL"), sha256 pinned"

# --- 6. sysroot + h713-tv cross-built ---------------------------------------
say "6/11 sysroot (arm64, development packages only), h713-tv and h713-osd cross-built"
SYSROOT="$MAINLINE/build/sysroot-arm64"
# A sysroot is reused only if it was made from this very package list and suite: the stamp
# carries their hash. Checking for one header let a sysroot from before the mesa stage
# (no libstdc++-14-dev) pass and fail at 6b, 05.10.2026.
SYSROOT_STAMP="$SYSROOT/.h713-sysroot-$(printf '%s %s' "$SYSROOT_PACKAGES" "$DEBIAN_SUITE" | sha256sum | cut -c1-12)"
if [[ ! -f "$SYSROOT_STAMP" ]]; then
	rm -rf "$SYSROOT"
	in_container_root "mmdebstrap --mode=unshare --variant=extract --arch=arm64 --skip=check/qemu --keyring=$(c "$KEYRING") --include=$SYSROOT_PACKAGES $DEBIAN_SUITE $(c "$SYSROOT") '$DEBIAN_MIRROR'" > "$OUT/sysroot.log" 2>&1 \
		|| in_container_root "mmdebstrap --variant=extract --arch=arm64 --skip=check/qemu --keyring=$(c "$KEYRING") --include=$SYSROOT_PACKAGES $DEBIAN_SUITE $(c "$SYSROOT") '$DEBIAN_MIRROR'" >> "$OUT/sysroot.log" 2>&1 \
		|| { tail -20 "$OUT/sysroot.log"; die "sysroot fails (log: $OUT/sysroot.log)"; }
	# mmdebstrap --variant=extract makes absolute symlinks (/usr/lib/... -> /lib/...);
	# clang --sysroot resolves those on the host. Make them relative (release/sysroot-fix.py: merged-usr links + relative symlinks).
	in_container_root "python3 $WORK/release/sysroot-fix.py $(c "$SYSROOT")" | sed 's/^/    /'
	in_container_root "touch $(c "$SYSROOT_STAMP")"
fi
info "sysroot $SYSROOT ($(du -sh "$SYSROOT" 2>/dev/null | cut -f1))"
in_container "cd $WORK/userspace/h713-tv && make -s -B cross SYSROOT=$(c "$SYSROOT") CROSS_CC=clang" > "$OUT/h713-tv-cross.log" 2>&1 || { tail -20 "$OUT/h713-tv-cross.log"; die "cross-building h713-tv failed (log: $OUT/h713-tv-cross.log)"; }
TV="$USERSPACE/h713-tv/h713-tv.aarch64-linux-gnu"; [[ -f "$TV" ]] || die "no $TV"
info "h713-tv $(stat -c %s "$TV") bytes, $(file -b "$TV" 2>/dev/null | cut -d, -f1-2)"
# The overlays over the picture (TODO 2.43-2.46): libc and libm only, with libh713osd and libh713geom
# compiled in; install-projekt.sh (5i) wants the binary and refuses without it.
in_container "cd $WORK/userspace/h713-osd && make -s -B cross SYSROOT=$(c "$SYSROOT") CROSS_CC=clang" > "$OUT/h713-osd-cross.log" 2>&1 || { tail -20 "$OUT/h713-osd-cross.log"; die "cross-building h713-osd failed (log: $OUT/h713-osd-cross.log)"; }
OSD="$USERSPACE/h713-osd/h713-osd.aarch64-linux-gnu"; [[ -f "$OSD" ]] || die "no $OSD"
info "h713-osd $(stat -c %s "$OSD") bytes, $(file -b "$OSD" 2>/dev/null | cut -d, -f1-2)"
# The autofocus metric in C (Q11): optional for the tool, which falls back to Python,
# but the image should carry it - the fallback is ten times slower on the A53.
in_container "cd $WORK/userspace/h713-autofocus && make -s -B cross SYSROOT=$(c "$SYSROOT") CROSS_CC=clang" > "$OUT/h713-afmetric-cross.log" 2>&1 || { tail -20 "$OUT/h713-afmetric-cross.log"; die "cross-building h713-afmetric failed (log: $OUT/h713-afmetric-cross.log)"; }
AF="$USERSPACE/h713-autofocus/h713-afmetric.aarch64-linux-gnu"; [[ -f "$AF" ]] || die "no $AF"
info "h713-afmetric $(stat -c %s "$AF") bytes, $(file -b "$AF" 2>/dev/null | cut -d, -f1-2)"

# --- 6b. mesa (panfrost only, no LLVM) for the GPU path -----------------------
say "6b/11 mesa cross-built (panfrost, EGL vendor for glvnd, GBM, Wayland platform; rootfs/mesa/build-mesa.sh)"
in_container "cd $WORK && rootfs/mesa/build-mesa.sh" > "$OUT/mesa-cross.log" 2>&1 || { tail -20 "$OUT/mesa-cross.log"; die "mesa build failed (log: $OUT/mesa-cross.log, $OUT/mesa-build.log)"; }
MESA="$OUT/mesa-panfrost-25.0.7.tar"; [[ -f "$MESA" ]] || die "no $MESA"
grep -E "NEEDED|installed" "$OUT/mesa-cross.log" | sed 's/^ *//; s/^/    /'

# --- 6c. h713-warp cross-built against the mesa stage -------------------------
# The keystone warp links libEGL and libGLESv2, the glvnd dispatchers: the linker finds libEGL.so and
# libGLESv2.so in the sysroot (libglvnd-dev), the headers and the vendor library behind them
# (libEGL_mesa.so.0) come from the stage build-mesa.sh leaves under mainline/build/mesa-stage;
# install-projekt.sh (5c) wants the binary and refuses without it.
say "6c/11 h713-warp cross-built (EGL, GLES2: glvnd dispatchers of the sysroot, vendor from the mesa stage)"
MESA_PREFIX="$MAINLINE/build/mesa-stage/usr/local"
[[ -f "$MESA_PREFIX/lib/libEGL_mesa.so.0" ]] || die "no $MESA_PREFIX/lib/libEGL_mesa.so.0 after the mesa step"
[[ -e "$SYSROOT/usr/lib/aarch64-linux-gnu/libEGL.so" && -e "$SYSROOT/usr/lib/aarch64-linux-gnu/libGLESv2.so" ]] || \
	die "no libEGL.so / libGLESv2.so in the sysroot -- libglvnd-dev missing from SYSROOT_PACKAGES?"
in_container "cd $WORK/userspace/h713-warp && make -s -B cross SYSROOT=$(c "$SYSROOT") CROSS_CC=clang MESA_PREFIX=$(c "$MESA_PREFIX")" > "$OUT/h713-warp-cross.log" 2>&1 || { tail -20 "$OUT/h713-warp-cross.log"; die "cross-building h713-warp failed (log: $OUT/h713-warp-cross.log)"; }
WARP="$USERSPACE/h713-warp/h713-warp.aarch64-linux-gnu"; [[ -f "$WARP" ]] || die "no $WARP"
info "h713-warp $(stat -c %s "$WARP") bytes, $(file -b "$WARP" 2>/dev/null | cut -d, -f1-2)"

# --- 7. rootfs --------------------------------------------------------------
if ((SKIP_ROOTFS)) && [[ -f "$ROOTFS/out/hy310-rootfs.tar" ]]; then say "7/11 rootfs -- skipped (--skip-rootfs)"
	# the tar carries its board's /etc/h713/features: one for another board would
	# expect hardware this one has not (or hide what it has)
	rec=$(tar -xOf "$ROOTFS/out/hy310-rootfs.tar" ./etc/h713/features 2>/dev/null | sed -n 's/^board = //p') || rec=
	[[ -z "$rec" || "$rec" == "$BOARD" ]] || die "the rootfs to reuse was built for board $rec, not $BOARD -- build it again (no --skip-rootfs)"
else
	say "7/11 rootfs ($DEBIAN_SUITE/arm64, mmdebstrap in the container as root)"
	CRUST_ARGS=; [[ -f "$OUT/scp.bin" ]] && CRUST_ARGS="--crust $(c "$OUT")/scp.bin"
	((WANT_STANDBY)) && CRUST_ARGS="$CRUST_ARGS --standby"
	in_container_root "cd $(c "$ROOTFS") && ./build-rootfs.sh --board $BOARD ${VARIANT:+--variant $VARIANT} --keyring $(c "$KEYRING") --modroot $(c "$MODROOT") --h713-tv $(c "$TV") --mesa $(c "$MESA") ${WIFI_ENV:+--wifi-env $(c "$WIFI_ENV")} $CRUST_ARGS" > "$OUT/rootfs-build.log" 2>&1 || { grep -E "^error:|acceptance failed|^!!" "$OUT/rootfs-build.log" | tail -8; die "rootfs build failed (log: $OUT/rootfs-build.log)"; }
	grep -E "tree size|wifi.env from|acceptance" "$OUT/rootfs-build.log" | sed 's/^/    /' | head -4
fi

# --- 8. ext4 inputs ---------------------------------------------------------
say "8/11 ext4 inputs (hy310-boot 128 MiB, hy310-rootfs 1 GiB, the vendor files come in at install time)"
# Make tmp/ as the user beforehand: the container writes into it as root, but the
# self-test (step 10) later puts probe-b-gefuellt.img next to it -- which does not
# work in a root-owned directory (P3, 12.09.).
mkdir -p "$INSTALLER/tmp"
in_container_root "FIT=$(c "$OUT")/h713-kernel.fit ROOTFS_OUT=$(c "$ROOTFS")/out bash $(c "$INSTALLER")/mkimage-inputs.sh" > "$OUT/inputs.log" 2>&1 || { tail -12 "$OUT/inputs.log"; die "ext4 inputs failed"; }
grep -c "  OK" "$OUT/inputs.log" | sed 's/^/    OK lines: /'

# --- 9. image ---------------------------------------------------------------
say "9/11 image $NAME"
TEST_FOR=(); ((TEST_IMAGE)) && TEST_FOR=(--test-for "$TEST_PROFILE")
ARISC_FW=vendor; [[ -n "${CRUST_DEFCONFIG:-}" ]] && ARISC_FW=crust      # the table's "arisc" (TODO 5.20)
( cd "$INSTALLER" && python3 h713-mkimage build -o "out/$NAME.img" "${TEST_FOR[@]+"${TEST_FOR[@]}"}" \
	--arisc "$ARISC_FW" \
	--spl "$OUT/spl-release.bin" --uboot "$OUT/uboot-proper-release.bin" --env "$OUT/hy310-env-release.bin" \
	--boot-ext4 tmp/hy310-boot.ext4 --rootfs-ext4 tmp/hy310-rootfs-platz.ext4 ) > "$OUT/mkimage.log" 2>&1 \
	|| { tail -20 "$OUT/mkimage.log"; die "image build failed (log: $OUT/mkimage.log)"; }
grep -E "environment:|OK   $NAME|placeholders for|in all" "$OUT/mkimage.log" | sed 's/^/    /'

# --- 10. check --------------------------------------------------------------
say "10/11 check"
# Der Journal-Index ist generiert; ein veralteter Index ist schlimmer als keiner,
# weil er aussieht wie eine Zusage. Also hier pruefen, nicht hoffen.
python3 "$ROOT/release/doku-index.py" --pruefen >/dev/null \
	&& info "journal index up to date" \
	|| die "doku/INDEX.md is stale -- run release/doku-index.py"
( cd "$INSTALLER" && python3 h713-mkimage check "out/$NAME.tabelle.json" ) | tail -2 | sed 's/^/    /'
# Judge the ARTEFACTS, not the sources: a piece that is not in the effective defconfig
# compiles away without a word, and the release would simply boot without protected
# playback. This also refuses an image built with the workbench probes, and any image
# with key material in it (release/check-hdcp-artifacts.sh, doku/148).
bash "$ROOT/release/check-hdcp-artifacts.sh" \
	"$OUT/uboot-proper-release.bin" "$OUT/bl31.bin" > "$OUT/hdcp-gate.log" 2>&1 \
	&& info "HDCP artefacts: green" \
	|| { grep -E "FAIL|problem" "$OUT/hdcp-gate.log" | sed 's/^/    /'
	     die "HDCP artefact check failed (log: $OUT/hdcp-gate.log)"; }
# crust and the standby (release/check-crust.py): this build's crust in the release FIT, the rootfs and
# the device tree and nowhere else, no variant the release refuses, U-Boot's DRAM values, and BL31 and
# rootfs agreeing on --standby and on the watchdog. A board without crust: no crust anywhere.
python3 "$ROOT/release/check-crust.py" --board "$BOARD" \
	${CRUST_DEFCONFIG:+--crust "$OUT/scp.bin" --crust-config "$OUT/crust.config" --crust-version "$CRUST_VERSION"} \
	--release-fit "$OUT/uboot-proper-release.bin" --empty-fit "$OUT/u-boot-installer.bin" \
	--empty-fit "$OUT/u-boot-h713-probe.bin" --uboot-config "$UB_O/.config" --dtb "$OUT/$KERNEL_DTB.dtb" \
	--rootfs "$ROOTFS/out/hy310-rootfs.tar" --bl31 "$OUT/bl31.bin" $( ((WANT_STANDBY)) && echo --standby ) \
	> "$OUT/crust-gate.log" 2>&1 \
	&& info "crust gate: green ($(sed -n 's/^crust: //p' "$OUT/crust-gate.log"))" \
	|| { grep -E "FAIL|Error" "$OUT/crust-gate.log" | sed 's/^/    /'
	     die "crust gate failed (log: $OUT/crust-gate.log)"; }
if [[ -n "$VENDOR" ]]; then
	( cd "$INSTALLER" && python3 mkimage-selftest.py "out/$NAME.tabelle.json" --vendor "$VENDOR" ) > "$OUT/selftest.log" 2>&1 || true
	if grep -q "ALL GREEN" "$OUT/selftest.log"; then info "self-test with the vendor files: ALL GREEN"
	else grep -E "FAIL" "$OUT/selftest.log" | sed 's/^/    /'; die "self-test not green (log: $OUT/selftest.log)"; fi
else
	info "no --vendor: structure check only. The full self-test needs an h713-extract output."
fi

# --- 11. stamp --------------------------------------------------------------
say "11/11 stamp"
STAMP="$DELIVERY/$NAME.BUILD.txt"
{
	echo "$NAME  built $(date -u '+%Y-%m-%dT%H:%M:%SZ') in $(elapsed)"
	((TEST_IMAGE)) && echo "TEST IMAGE: built for boards/$UNIT (STATUS=$STATUS), table test_for=$TEST_PROFILE -- not a release, and no claim that this board is supported"
	echo "board:    $UNIT ($STATUS; profile $TEST_PROFILE, DTB $KERNEL_DTB, U-Boot $UBOOT_BASE + $UBOOT_RELEASE_ROLE/$UBOOT_INSTALLER_ROLE${DRAM_CLK:+, DRAM $DRAM_CLK MHz}, probe $UBOOT_PROBE_DEFCONFIG)"
	echo "series:   $(sha256sum "$MAINLINE/patches/kernel/series" | cut -c1-16)  $(grep -cv '^#\|^$' "$MAINLINE/patches/kernel/series") patches"
	echo "kernel defconfig: $KDEF $(sha256sum "$MAINLINE/patches/kernel/board/$KDEF" | cut -c1-16)"
	echo "kernel tree: $H  release $KREL"
	for r in u-boot arm-trusted-firmware sunxi-tools; do
		echo "$r: $(git -C "$MAINLINE/external/$r" rev-parse --short HEAD 2>/dev/null)$(git -C "$MAINLINE/external/$r" diff --quiet HEAD 2>/dev/null || echo ' +uncommitted')"
	done
	if [[ -n "${CRUST_DEFCONFIG:-}" ]]; then
		echo "crust: ${CRUST_HEAD:0:12}${CRUST_SRC_GIVEN:+ (CRUST_SRC)} $CRUST_DEFCONFIG $CRUST_VERSION, $(sed -n 's/^build word //p' "$OUT/crust-gate.log"), or1k $(cut -d' ' -f1,3 "$OR1K/.h713-or1k-toolchain" 2>/dev/null)"
	else
		echo "crust: none - the ARISC runs the vendor firmware from the owner's dump"
	fi
	echo "standby: $STANDBY, $( ((WANT_STANDBY)) && echo "offered (--standby, experimental): BL31 with SYSTEM_SUSPEND, suspend allowed, power.conf default poweroff" || echo "not offered: BL31 without SYSTEM_SUSPEND, AllowSuspend=no")"
	GIT_ROOT=$(git -C "$MAINLINE" rev-parse --show-toplevel 2>/dev/null || true)
	# No directory name in the stamp: that is local and tells a reader nothing.
	if [[ "$GIT_ROOT" == "$MAINLINE" ]]; then W=mainline; else W=repo; fi
	echo "$W: $(git -C "$MAINLINE" rev-parse --short HEAD 2>/dev/null) ($(git -C "$MAINLINE" status --short 2>/dev/null | wc -l) local changes)"
	echo "source date: $SOURCE_DATE_EPOCH ($(date -u -d "@$SOURCE_DATE_EPOCH" '+%Y-%m-%dT%H:%M:%SZ'), committer date of $REPRO_COMMIT)"
	echo "$REPRO_LINE"
	echo "rootfs packages: dpkg status $(tar -xOf "$ROOTFS/out/hy310-rootfs.tar" ./var/lib/dpkg/status | sha256sum | cut -c1-16) -- the tar repeats only while $DEBIAN_MIRROR $DEBIAN_SUITE is at this state"
	echo "U-Boot:   $(strings -n 8 "$OUT/uboot-proper-release.bin" | grep -m1 '^U-Boot 20')"
	echo "building blocks (sha256, 16 characters):"
	for f in spl-release.bin uboot-proper-release.bin hy310-env-release.bin u-boot-installer.bin h713-kernel.fit modules/aic8800_bsp.ko modules/aic8800_fdrv.ko; do
		printf '  %-28s %s\n' "$f" "$(sha256sum "$OUT/$f" | cut -c1-16)"
	done
	[[ -f "$OUT/scp.bin" ]] && printf '  %-28s %s\n' "scp.bin (crust)" "$(sha256sum "$OUT/scp.bin" | cut -c1-16)"
	printf '  %-28s %s\n' "h713-tv.aarch64-linux-gnu" "$(sha256sum "$TV" | cut -c1-16)"
	printf '  %-28s %s\n' "mesa-panfrost-25.0.7.tar" "$(sha256sum "$MESA" | cut -c1-16)"
	printf '  %-28s %s\n' "hy310-rootfs.tar" "$(sha256sum "$ROOTFS/out/hy310-rootfs.tar" | cut -c1-16)"
} > "$STAMP"
sed 's/^/    /' "$STAMP"
say "done: $DELIVERY/$NAME-{a-bootkette,b-system,c-gptkopie}.img + $NAME.tabelle.json  ($(elapsed))"
