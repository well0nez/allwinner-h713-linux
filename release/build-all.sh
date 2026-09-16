#!/usr/bin/env bash
# release/build-all.sh -- from a fresh clone to an installable image, one entry point.
#
#   release/build-all.sh --version v0.10 [--board hy310] [--vendor DIR] [--wifi-env FILE]
#                        [--jobs N] [--skip-bl31] [--skip-uboot] [--skip-kernel]
#                        [--skip-rootfs] [--test-image] [--dry-run]
#
# --board <id> (default hy310) picks boards/<id>/board.env: the installer
# profile, the kernel DTB the FIT carries, the U-Boot base defconfig and the
# image name ($IMAGE_NAME-$VERSION). The rule of doku/121 §5 is enforced here:
# no image for a board nobody has tested -- a board that is not STATUS=verified
# (an owner reported a green run) or has no installer profile is refused.
#
# --test-image is the one named way past that (plan/stufe-5.md): a partial/profile-only
# board with PROFILE, KERNEL_DTB and a U-Boot base gets $IMAGE_NAME-$VERSION-TEST, marked
# test_for=$PROFILE in its table, for its own owner to try -- h713-install writes it on
# that board alone and only with --test-image. Not a release, no claim of support.
#
# Order (doku/116 P4):
#   1 bl31  2 U-Boot (+ split SPL/proper + environment with CRC)  2b installer U-Boot (ums)
#   2b2 probe U-Boot (h713_probe)  2c sunxi-fel (trap door)  3 kernel (+ modules)
#   4 aic8800  5 Debian keyring (pinned)  6 sysroot + h713-tv cross-built  7 rootfs
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
	local src dst
	while IFS=' ' read -r src dst; do
		[[ -n "$src" ]] || continue
		if [[ "$ROOT" == "$src" || "$ROOT" == "$src"/* ]]; then
			printf '%s%s' "$dst" "${ROOT#"$src"}"; return 0
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
SYSROOT_PACKAGES=libc6-dev,libgcc-14-dev,libdrm-dev,libasound2-dev
DEBIAN_SUITE=trixie
DEBIAN_MIRROR=http://deb.debian.org/debian

VERSION= BOARD=hy310 VENDOR= WIFI_ENV= JOBS=$(nproc) DRY=0 TEST_IMAGE=0
SKIP_BL31=0 SKIP_UBOOT=0 SKIP_KERNEL=0 SKIP_ROOTFS=0
while (($#)); do
	case "$1" in
	--version)   VERSION=${2:?}; shift 2 ;;
	--board)     BOARD=${2:?}; shift 2 ;;
	--vendor)    VENDOR=$(cd "${2:?}" && pwd); shift 2 ;;
	--wifi-env)  WIFI_ENV=$(readlink -f "${2:?}"); shift 2 ;;
	--jobs)      JOBS=${2:?}; shift 2 ;;
	--skip-bl31)   SKIP_BL31=1; shift ;;
	--skip-uboot)  SKIP_UBOOT=1; shift ;;
	--skip-kernel) SKIP_KERNEL=1; shift ;;
	--skip-rootfs) SKIP_ROOTFS=1; shift ;;
	--test-image)  TEST_IMAGE=1; shift ;;
	--dry-run)   DRY=1; shift ;;
	-h|--help)   sed -n '2,33p' "$0"; exit 0 ;;
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
# shellcheck source=/dev/null
source "$BOARD_ENV"
[[ "${BOARD_ID:-}" == "$BOARD" ]] || { echo "$BOARD_ENV says BOARD_ID='${BOARD_ID:-}', not '$BOARD'" >&2; exit 2; }
if [[ "${STATUS:-}" != verified ]]; then
	# --test-image is the named exception; everything else about the rule stays as it is.
	if ! ((TEST_IMAGE)) || [[ "${STATUS:-}" != partial && "${STATUS:-}" != profile-only ]]; then
		echo "no image for a board nobody has tested (doku/121 §5): boards/$BOARD is STATUS=${STATUS:-unset}." >&2
		echo "A board becomes 'verified' when its owner reports a green run of our build; until then it gets" >&2
		echo "an installer profile and the probe (h713_probe), not an image." >&2
		exit 2
	fi
elif ((TEST_IMAGE)); then
	echo "boards/$BOARD is STATUS=verified: --test-image is for a board nobody has run (partial, profile-only). This one gets a release image." >&2
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
in_container()      { podman exec -e JOBS="$JOBS" "$CONTAINER" bash -lc "$*"; }
in_container_root() { podman exec -u root -e JOBS="$JOBS" "$CONTAINER" bash -lc "$*"; }
# host path -> container path
c() { printf '%s' "${1/#$ROOT/$WORK}"; }
T0=$(date +%s)
elapsed() { local s=$(( $(date +%s) - T0 )); printf '%d min %02d s' $((s/60)) $((s%60)); }

say "build-all $NAME  ($(date '+%Y-%m-%d %H:%M'))"
info "root $ROOT"
info "board $BOARD ($STATUS, profile $PROFILE, DTB $KERNEL_DTB, U-Boot $UBOOT_BASE + roles)"
((TEST_IMAGE)) && { say "TEST IMAGE for $BOARD (STATUS=$STATUS) -- not a release"
	info "Nobody has reported a green run here. The table is marked test_for=$PROFILE, so h713-install"
	info "writes it on this board alone and only with --test-image; the owner's full dump is the way back."; }
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
((DRY)) && { info "would build: bl31, U-Boot ($UBOOT_BASE + $UBOOT_RELEASE_ROLE) + env, installer U-Boot ($UBOOT_BASE + $UBOOT_INSTALLER_ROLE), probe U-Boot ($UBOOT_PROBE_DEFCONFIG), sunxi-fel, kernel + modules (BOARD=$BOARD, $KERNEL_DTB), aic8800, keyring, sysroot + h713-tv, rootfs, inputs, image $NAME"; exit 0; }

# --- 1. bl31 ---------------------------------------------------------------
if ((SKIP_BL31)) && [[ -f "$OUT/bl31.bin" ]]; then say "1/11 bl31 -- skipped (--skip-bl31, $OUT/bl31.bin is there)"
else
	say "1/11 bl31 (TF-A)"
	# Build from scratch. Reason (12.09., P3.9): the work tree held a bl31 from
	# 10.09. built with assertions enabled (49260 instead of 45164 bytes). make
	# saw everything as up to date and never replaced it -- it sits in v0.8 to v0.10.
	rm -rf "$MAINLINE/external/arm-trusted-firmware/build"
	in_container "cd $WORK/mainline && BOARD=$BOARD build/build.sh bl31" | tail -3 | sed 's/^/    /'
fi
[[ -f "$OUT/bl31.bin" ]] || die "no bl31.bin"

# --- 2. U-Boot: build, split, environment -----------------------------------
UB_O="$MAINLINE/build/uboot-release"
if ((SKIP_UBOOT)) && [[ -f "$OUT/spl-release.bin" && -f "$OUT/uboot-proper-release.bin" && -f "$OUT/hy310-env-release.bin" ]]; then
	say "2/11 U-Boot -- skipped (--skip-uboot, the building blocks are there)"
else
	say "2/11 U-Boot $UBOOT_BASE + $UBOOT_RELEASE_ROLE"
	rm -rf "$UB_O"   # as with bl31: no old objects, no old .config
	in_container "cd $WORK/mainline && build/uboot-build.sh $(c "$UB_O") $UBOOT_BASE $UBOOT_RELEASE_ROLE" > "$OUT/uboot-build.log" 2>&1 || { tail -20 "$OUT/uboot-build.log"; die "U-Boot build failed (log: $OUT/uboot-build.log)"; }
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
	in_container "cd $WORK/mainline && build/uboot-build.sh $(c "$UBI_O") $UBOOT_BASE $UBOOT_INSTALLER_ROLE" > "$OUT/uboot-installer-build.log" 2>&1 || { tail -20 "$OUT/uboot-installer-build.log"; die "installer U-Boot failed (log: $OUT/uboot-installer-build.log)"; }
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
say "6/11 sysroot (arm64, development packages only) and h713-tv cross-built"
SYSROOT="$MAINLINE/build/sysroot-arm64"
if [[ ! -f "$SYSROOT/usr/include/libdrm/drm.h" ]]; then
	rm -rf "$SYSROOT"
	in_container_root "mmdebstrap --mode=unshare --variant=extract --arch=arm64 --skip=check/qemu --keyring=$(c "$KEYRING") --include=$SYSROOT_PACKAGES $DEBIAN_SUITE $(c "$SYSROOT") '$DEBIAN_MIRROR'" > "$OUT/sysroot.log" 2>&1 \
		|| in_container_root "mmdebstrap --variant=extract --arch=arm64 --skip=check/qemu --keyring=$(c "$KEYRING") --include=$SYSROOT_PACKAGES $DEBIAN_SUITE $(c "$SYSROOT") '$DEBIAN_MIRROR'" >> "$OUT/sysroot.log" 2>&1 \
		|| { tail -20 "$OUT/sysroot.log"; die "sysroot fails (log: $OUT/sysroot.log)"; }
	# mmdebstrap --variant=extract makes absolute symlinks (/usr/lib/... -> /lib/...);
	# clang --sysroot resolves those on the host. Make them relative (release/sysroot-fix.py: merged-usr links + relative symlinks).
	in_container_root "python3 $WORK/release/sysroot-fix.py $(c "$SYSROOT")" | sed 's/^/    /'
fi
info "sysroot $SYSROOT ($(du -sh "$SYSROOT" 2>/dev/null | cut -f1))"
in_container "cd $WORK/userspace/h713-tv && make -s -B cross SYSROOT=$(c "$SYSROOT") CROSS_CC=clang" > "$OUT/h713-tv-cross.log" 2>&1 || { tail -20 "$OUT/h713-tv-cross.log"; die "cross-building h713-tv failed (log: $OUT/h713-tv-cross.log)"; }
TV="$USERSPACE/h713-tv/h713-tv.aarch64-linux-gnu"; [[ -f "$TV" ]] || die "no $TV"
info "h713-tv $(stat -c %s "$TV") bytes, $(file -b "$TV" 2>/dev/null | cut -d, -f1-2)"

# --- 7. rootfs --------------------------------------------------------------
if ((SKIP_ROOTFS)) && [[ -f "$ROOTFS/out/hy310-rootfs.tar" ]]; then say "7/11 rootfs -- skipped (--skip-rootfs)"
else
	say "7/11 rootfs ($DEBIAN_SUITE/arm64, mmdebstrap in the container as root)"
	in_container_root "cd $(c "$ROOTFS") && ./build-rootfs.sh --keyring $(c "$KEYRING") --modroot $(c "$MODROOT") --h713-tv $(c "$TV") ${WIFI_ENV:+--wifi-env $(c "$WIFI_ENV")}" > "$OUT/rootfs-build.log" 2>&1 || { grep -E "^error:|acceptance failed|^!!" "$OUT/rootfs-build.log" | tail -8; die "rootfs build failed (log: $OUT/rootfs-build.log)"; }
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
TEST_FOR=(); ((TEST_IMAGE)) && TEST_FOR=(--test-for "$PROFILE")
( cd "$INSTALLER" && python3 h713-mkimage build -o "out/$NAME.img" "${TEST_FOR[@]+"${TEST_FOR[@]}"}" \
	--spl "$OUT/spl-release.bin" --uboot "$OUT/uboot-proper-release.bin" --env "$OUT/hy310-env-release.bin" \
	--boot-ext4 tmp/hy310-boot.ext4 --rootfs-ext4 tmp/hy310-rootfs-platz.ext4 ) > "$OUT/mkimage.log" 2>&1 \
	|| { tail -20 "$OUT/mkimage.log"; die "image build failed (log: $OUT/mkimage.log)"; }
grep -E "environment:|OK   $NAME|placeholders for|in all" "$OUT/mkimage.log" | sed 's/^/    /'

# --- 10. check --------------------------------------------------------------
say "10/11 check"
( cd "$INSTALLER" && python3 h713-mkimage check "out/$NAME.tabelle.json" ) | tail -2 | sed 's/^/    /'
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
	((TEST_IMAGE)) && echo "TEST IMAGE: built for boards/$BOARD (STATUS=$STATUS), table test_for=$PROFILE -- not a release, and no claim that this board is supported"
	echo "board:    $BOARD ($STATUS; profile $PROFILE, DTB $KERNEL_DTB, U-Boot $UBOOT_BASE + $UBOOT_RELEASE_ROLE/$UBOOT_INSTALLER_ROLE, probe $UBOOT_PROBE_DEFCONFIG)"
	echo "series:   $(sha256sum "$MAINLINE/patches/kernel/series" | cut -c1-16)  $(grep -cv '^#\|^$' "$MAINLINE/patches/kernel/series") patches"
	echo "kernel defconfig: $KDEF $(sha256sum "$MAINLINE/patches/kernel/board/$KDEF" | cut -c1-16)"
	echo "kernel tree: $H  release $KREL"
	for r in u-boot arm-trusted-firmware sunxi-tools; do
		echo "$r: $(git -C "$MAINLINE/external/$r" rev-parse --short HEAD 2>/dev/null)$(git -C "$MAINLINE/external/$r" diff --quiet HEAD 2>/dev/null || echo ' +uncommitted')"
	done
	GIT_ROOT=$(git -C "$MAINLINE" rev-parse --show-toplevel 2>/dev/null || true)
	# No directory name in the stamp: that is local and tells a reader nothing.
	if [[ "$GIT_ROOT" == "$MAINLINE" ]]; then W=mainline; else W=repo; fi
	echo "$W: $(git -C "$MAINLINE" rev-parse --short HEAD 2>/dev/null) ($(git -C "$MAINLINE" status --short 2>/dev/null | wc -l) local changes)"
	echo "U-Boot:   $(strings -n 8 "$OUT/uboot-proper-release.bin" | grep -m1 '^U-Boot 20')"
	echo "building blocks (sha256, 16 characters):"
	for f in spl-release.bin uboot-proper-release.bin hy310-env-release.bin u-boot-installer.bin h713-kernel.fit modules/aic8800_bsp.ko modules/aic8800_fdrv.ko; do
		printf '  %-28s %s\n' "$f" "$(sha256sum "$OUT/$f" | cut -c1-16)"
	done
	printf '  %-28s %s\n' "h713-tv.aarch64-linux-gnu" "$(sha256sum "$TV" | cut -c1-16)"
	printf '  %-28s %s\n' "hy310-rootfs.tar" "$(sha256sum "$ROOTFS/out/hy310-rootfs.tar" | cut -c1-16)"
} > "$STAMP"
sed 's/^/    /' "$STAMP"
say "done: $DELIVERY/$NAME-{a-bootkette,b-system,c-gptkopie}.img + $NAME.tabelle.json  ($(elapsed))"
