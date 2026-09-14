#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
#
# build-rootfs.sh -- build the slim rootfs for the HY310 v0.1.
#
# Specified in doku/107-plan-rootfs.md. Target layout: doku/109-plan-layout-v3.md §2.2
# (one partition hy310-rootfs, 7.15 GiB, /data is a directory inside it).
#
# Result (in --out):
#   hy310-rootfs.tar          the tree the installer unpacks into hy310-rootfs
#                             and which doubles as the NFS root
#                             (109 §4.2: one build, two targets)
#   hy310-rootfs.ext4         the same as an ext4 image (optional, --image-size)
#   hy310-rootfs.manifest     what is in it, and what it was built from
#   ROOTFS-SHA256SUMS         checksums
#
# ============================================================================
# WHERE THIS RUNS
# ============================================================================
# In the container h713-build (project rule: no build on the host):
#
#     podman exec -u root h713-build \
#         /work/analyse/release/arbeit/rootfs/build-rootfs.sh --out /work/...
#
# The project is mounted there as /work. The script finds its own project tree
# from its own path, it needs no --project-root.
#
# ============================================================================
# WHAT THIS SCRIPT DELIBERATELY DOES *NOT* DO -- how it differs from
# mainline/tools/rootfs/build.sh (cstenger)
# ============================================================================
#  * No VIDEO_RUNTIME_PACKAGES. There the GStreamer/Mesa/GTK chain is part of
#    the base system ("this is a projector"). For us it is the single biggest
#    item of today's netboot root (107 §1: libllvm19 118 MiB, mesa-libgallium
#    33 MiB, libgtk-3-common 30 MiB ...) and does nothing: h713-tv puts the
#    HDMI input on a DRM plane and decodes nothing.
#  * No --profile dev, no build-essential, no -dev packages. We cross-build
#    (107 §3).
#  * NO --ssh-key as a required argument. There the key is demanded and copied
#    into the image; for a release it has to come from the user, that is, from
#    the installer (107 §3). --authorized-key exists here only as a choice for
#    private builds, never as a duty.
#  * WLAN is in (since 12.09.: drivers as modules, packages, h713-wifi with
#    /etc/h713/wifi.env), but NO firmware blobs in the image (107 §5) -- the
#    aic8800 firmware comes, like everything proprietary, from the installer
#    out of h713-extract, out of the user's own dump. Bluetooth stays out: its
#    firmware is not in the dump.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Place and defaults
# ---------------------------------------------------------------------------
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Project root: the next parent directory with mainline/build/build.sh -- that way
# the script works in the working directory (analyse/release/arbeit/...) as well as
# in the release repository (rootfs/ and installer/ directly under the root), doku/116 P3.
project_root() { local d=$1; while [ "$d" != / ]; do [ -f "$d/mainline/build/build.sh" ] && { echo "$d"; return; }; d=$(dirname "$d"); done; return 1; }
# analyse/release/arbeit/rootfs -> four levels up is the project tree
PROJECT_ROOT=$(project_root "$HERE") || { echo "no project root (mainline/build/build.sh) found above $HERE" >&2; exit 1; }

SUITE=trixie
ARCH=arm64
MIRROR=http://deb.debian.org/debian
OUT_DIR="$HERE/out"
IMAGE_SIZE=1G
MAKE_EXT4=1
DRY_RUN=0
SKIP_PROJECT=0
AUTHORIZED_KEY=
KEEP_WORK=0
KEYRING=
# WLAN: /etc/h713/wifi.env in the image. Order: --wifi-env FILE, else
# rootfs/wifi.env next to this script (local, not for git), else the default
# out of the overlay (AP h713/magcubic -- publicly known).
WIFI_ENV=

# Project parts (section 4 of the assignment) -- defaults, changeable by switch
MODROOT="$PROJECT_ROOT/mainline/build/modroot.GUT-bad2f16b"
H713_TV_SRC="$PROJECT_ROOT/userspace/h713-tv"
H713_TV_BIN="$H713_TV_SRC/h713-tv.aarch64-linux-gnu"
H713_PQ_SRC="$PROJECT_ROOT/userspace/h713-pq"

usage() {
	cat <<EOF
Usage: ${0##*/} [options]

Builds Debian $SUITE/$ARCH with mmdebstrap --variant=minbase, lays overlay/
on top and installs the project parts (h713-tv, kernel modules, h713-pq).

  --out DIR             output directory (default: $OUT_DIR)
  --suite NAME          Debian suite (default: $SUITE)
  --arch ARCH           architecture (default: $ARCH)
  --mirror URL          mirror (default: $MIRROR)
  --keyring FILE        keyring for the signature check. NEEDED in the
                        container h713-build: its debian-archive-keyring
                        (2023.4) stops at bookworm and does not know trixie.
  --image-size SIZE     size of the ext4 image (default: $IMAGE_SIZE).
                        Building it small is deliberate: the fstab carries
                        x-systemd.growfs, the image grows to the full
                        partition (7.15 GiB) on the first start.
  --no-ext4             write the tar only
  --modroot DIR         kernel module tree (default: ${MODROOT#"$PROJECT_ROOT"/})
  --h713-tv FILE       cross-built h713-tv (default:
                        ${H713_TV_BIN#"$PROJECT_ROOT"/})
  --authorized-key FILE optionally build in an SSH key. NOT the default and
                        not the release way (107 §3).
  --wifi-env FILE       your own /etc/h713/wifi.env (mode=ap|sta|off, ssid,
                        password, channel, ...). Without the switch:
                        rootfs/wifi.env if it is there, else the default out
                        of the overlay -- access point h713 / magcubic, and
                        everybody knows that one. Checked with
                        'h713-wifi check' before the build.
  --skip-project        the Debian base system + overlay/ only
  --keep-work           do not delete the work directory
  --dry-run             build nothing, write nothing, fetch nothing from the
                        network -- only show what would happen. Runs through
                        even without mmdebstrap.
  -h, --help            this help
EOF
}

while (($#)); do
	case "$1" in
	--out)             OUT_DIR=${2:?missing value for --out}; shift 2 ;;
	--keyring)         KEYRING=${2:?missing value for --keyring}; shift 2 ;;
	--suite)           SUITE=${2:?missing value for --suite}; shift 2 ;;
	--arch)            ARCH=${2:?missing value for --arch}; shift 2 ;;
	--mirror)          MIRROR=${2:?missing value for --mirror}; shift 2 ;;
	--image-size)      IMAGE_SIZE=${2:?missing value for --image-size}; shift 2 ;;
	--no-ext4)         MAKE_EXT4=0; shift ;;
	--modroot)         MODROOT=${2:?missing value for --modroot}; shift 2 ;;
	--h713-tv)        H713_TV_BIN=${2:?missing value for --h713-tv}; shift 2 ;;
	--authorized-key)  AUTHORIZED_KEY=${2:?missing value for --authorized-key}; shift 2 ;;
	--wifi-env)        WIFI_ENV=${2:?missing value for --wifi-env}; shift 2 ;;
	--skip-project|--skip-projekt) SKIP_PROJECT=1; shift ;;
	--keep-work)       KEEP_WORK=1; shift ;;
	--dry-run)         DRY_RUN=1; shift ;;
	-h|--help)         usage; exit 0 ;;
	*) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
	esac
done

OVERLAY="$HERE/overlay"
PACKAGES_FILE="$HERE/packages.txt"
PROJECT_SCRIPT="$HERE/install-projekt.sh"

# Resolve wifi.env. The check is done by the same script that runs on the
# device -- what passes here passes there, and the other way round.
WIFI_CHECK="$OVERLAY/usr/local/sbin/h713-wifi"
WIFI_ENV_ORIGIN=
if [[ -n "$WIFI_ENV" ]]; then
	WIFI_ENV_ORIGIN="--wifi-env"
elif [[ -f "$HERE/wifi.env" ]]; then
	WIFI_ENV="$HERE/wifi.env"; WIFI_ENV_ORIGIN="rootfs/wifi.env"
else
	WIFI_ENV="$OVERLAY/etc/h713/wifi.env"; WIFI_ENV_ORIGIN="the default out of the overlay"
fi
WIFI_IS_DEFAULT=0
[[ "$WIFI_ENV" -ef "$OVERLAY/etc/h713/wifi.env" ]] && WIFI_IS_DEFAULT=1

say()  { printf '==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Tool check -- it should SAY what is missing, not just fail
# ---------------------------------------------------------------------------
# The mapping tool -> Debian/Ubuntu package lives here so that the message can
# name the command that gets you further. As of 10.09.2026 exactly mmdebstrap
# is missing in the container h713-build (ubuntu:24.04).
declare -A TOOL_PKG=(
	[mmdebstrap]=mmdebstrap
	[tar]=tar
	[mke2fs]=e2fsprogs
	[e2fsck]=e2fsprogs
	[depmod]=kmod
	[install]=coreutils
	[sha256sum]=coreutils
	[du]=coreutils
	[find]=findutils
)
# Needed for the ext4 step only
EXT4_TOOLS=(mke2fs e2fsck)
# Needed for the foreign-architecture bootstrap only
FOREIGN_TOOLS=(/usr/bin/qemu-aarch64-static)

check_tools() {
	local missing=() pkgs=() t
	for t in "${!TOOL_PKG[@]}"; do
		if [[ " ${EXT4_TOOLS[*]} " == *" $t "* ]] && ((MAKE_EXT4 == 0)); then
			continue
		fi
		command -v "$t" >/dev/null 2>&1 && continue
		missing+=("$t")
		pkgs+=("${TOOL_PKG[$t]}")
	done

	# Foreign architecture: the maintainer scripts of the arm64 packages run
	# under qemu-user. There are two ways that works, and the second is the
	# one we actually use here:
	#   a) qemu-user-static installed IN the container;
	#   b) the HOST's binfmt_misc is registered with flag F -- then the
	#      interpreter is already in the kernel and the path in the container
	#      does not matter. Inside the container /proc/sys/fs/binfmt_misc is
	#      then not even visible, so looking there would be a false negative.
	# That is why we do not look for files but MEASURE: arch-test (comes with
	# mmdebstrap) really runs a tiny test program of the target architecture.
	local fw_ok=1 fw_how=
	local host_arch; host_arch=$(dpkg --print-architecture 2>/dev/null || echo unknown)
	if [[ "$ARCH" != "$host_arch" ]]; then
		if command -v arch-test >/dev/null 2>&1 && arch-test "$ARCH" >/dev/null 2>&1; then
			fw_how="arch-test $ARCH: ok"
		elif [[ -x /usr/bin/qemu-${ARCH/arm64/aarch64}-static ]]; then
			fw_how="qemu-user-static in the container"
		elif [[ -r /proc/sys/fs/binfmt_misc/qemu-${ARCH/arm64/aarch64} ]]; then
			fw_how="binfmt_misc visible"
		else
			fw_ok=0
		fi
	else
		fw_how="native"
	fi

	if ((${#missing[@]} == 0)) && ((fw_ok == 1)); then
		info "tools complete ($host_arch -> $ARCH: $fw_how)"
		return 0
	fi

	warn "tools are missing:"
	((${#missing[@]})) && printf '    missing: %s\n' "${missing[*]}" >&2
	((fw_ok == 0)) && printf '    missing: running %s programs (qemu-user-static or the host binfmt)\n' "$ARCH" >&2

	# The recipe belongs in doku/50-befehle.md.
	((${#pkgs[@]})) || pkgs=()
	local pkglist
	pkglist=$( ((${#pkgs[@]})) && printf '%s\n' "${pkgs[@]}" | sort -u | tr '\n' ' ' )
	cat >&2 <<EOF

    Install them in the container (this belongs in the recipe in doku/50-befehle.md):

        podman exec -u root h713-build apt-get update
        podman exec -u root h713-build env DEBIAN_FRONTEND=noninteractive \\
            apt-get install -y mmdebstrap debian-archive-keyring

    mmdebstrap pulls in fakeroot, fakechroot, arch-test and gpg.
    debian-archive-keyring delivers /usr/share/keyrings/debian-archive-keyring.gpg
    -- without it mmdebstrap cannot check the Debian signatures.

    ONLY if "running $ARCH programs" is missing above, additionally:

        podman exec -u root h713-build env DEBIAN_FRONTEND=noninteractive \\
            apt-get install -y qemu-user-static

    (Not needed on this host: its binfmt_misc registers qemu-aarch64 with flag
     F, so the interpreter is already loaded in the kernel and counts inside
     the container too. Checked message: "arch-test arm64: ok".)
${pkglist:+
    Packages missing according to the tool check: $pkglist}
EOF
	return 1
}

# The keyring mmdebstrap checks the Debian source with. Without a keyring there
# is NO unsigned emergency path here -- better to stop than to build an image
# out of unchecked packages.
#
# WATCH OUT, the trap that can cost 40 minutes: the container h713-build is
# ubuntu:24.04, and its `debian-archive-keyring` is version 2023.4 -- which
# stops at **bookworm (12)**. The key for **trixie (13)** is not in it, and
# mmdebstrap then only fails while fetching the Release file, with a message
# about an invalid signature. That is why we check not only WHETHER a keyring
# is there, but whether it KNOWS the suite.
#
# Three ways, in this order:
#   1. --keyring FILE (given explicitly)
#   2. a keyring in the container that carries the suite key
#   3. the keyring of an existing trixie tree, e.g. today's NFS root:
#      /srv/h713-rootfs/usr/share/keyrings/debian-archive-keyring.gpg
#      (carries "Debian Archive Automatic Signing Key (13/trixie)"; the
#      container does not see /srv, so the file has to be copied to /work
#      -- see --keyring)
KEYRING_CANDIDATES=(
	/usr/share/keyrings/debian-archive-keyring.gpg
	/usr/share/keyrings/debian-archive-keyring.pgp
	/etc/apt/trusted.gpg.d/debian-archive-keyring.gpg
)

# Does this keyring know the suite? Looks for a uid that names the suite
# ("... (13/trixie) ..."). Without gpg we do not guess but let it pass -- it
# shows up later then, but we do not claim anything false.
keyring_knows_suite() {
	local k=$1
	command -v gpg >/dev/null 2>&1 || return 0
	gpg --no-default-keyring --keyring "$k" --list-keys 2>/dev/null \
		| grep -qi "/$SUITE)"
}

find_keyring() {
	local k
	if [[ -n "$KEYRING" ]]; then
		[[ -r "$KEYRING" ]] || return 1
		printf '%s\n' "$KEYRING"; return 0
	fi
	# first one that knows the suite
	for k in "${KEYRING_CANDIDATES[@]}"; do
		[[ -r "$k" ]] && keyring_knows_suite "$k" && { printf '%s\n' "$k"; return 0; }
	done
	# else any of them (the caller then reports the gap)
	for k in "${KEYRING_CANDIDATES[@]}"; do
		[[ -r "$k" ]] && { printf '%s\n' "$k"; return 0; }
	done
	return 1
}

check_keyring() {
	local k=$1
	if keyring_knows_suite "$k"; then
		info "keyring: $k (knows $SUITE)"
		return 0
	fi
	warn "keyring $k does NOT know the suite '$SUITE'."
	cat >&2 <<EOF
    The container ubuntu:24.04 ships debian-archive-keyring 2023.4, which
    stops at bookworm (12). Without the trixie key mmdebstrap fails at the
    Release file -- only after half the bootstrap.

    Way out (one of these):
      a) bring a current keyring into the container and
             $0 --keyring /path/to/debian-archive-keyring.gpg
      b) take the keyring out of an existing trixie tree. On this host there
         is one in today's NFS root:
             /srv/h713-rootfs/usr/share/keyrings/debian-archive-keyring.gpg
         The container does not see /srv -- so copy it to /work once:
             install -D -m 0644 \\
               /srv/h713-rootfs/usr/share/keyrings/debian-archive-keyring.gpg \\
               $OUT_DIR/keyring/debian-archive-keyring.gpg
         and then --keyring $OUT_DIR/keyring/debian-archive-keyring.gpg
      c) build with --suite bookworm (NOT wanted: today's root is
         trixie 13.6, 107 §5)
EOF
	return 1
}

# ---------------------------------------------------------------------------
# 2. Read the package list
# ---------------------------------------------------------------------------
read_packages() {
	[[ -r "$PACKAGES_FILE" ]] || die "packages.txt is not readable: $PACKAGES_FILE"
	# comments and blank lines out, the first word of a line is the package name
	sed -e 's/#.*//' -e 's/[[:space:]]\+/ /g' -e 's/^ //' -e 's/ $//' \
		"$PACKAGES_FILE" | awk 'NF { print $1 }'
}

# ---------------------------------------------------------------------------
# 3. Dry run
# ---------------------------------------------------------------------------
mmdebstrap_argv() {
	# Print as an array (one line per argument) so that the dry run shows
	# exactly what the real run executes.
	local mode=unshare
	((EUID == 0)) && mode=root
	local keyring; keyring=$(find_keyring || echo "<KEYRING-MISSING>")
	printf '%s\n' \
		mmdebstrap \
		"--mode=$mode" \
		--variant=minbase \
		"--architectures=$ARCH" \
		--skip=check/qemu \
		"--keyring=$keyring" \
		'--aptopt=Acquire::Languages "none"' \
		'--dpkgopt=path-exclude=/usr/share/man/*' \
		'--dpkgopt=path-exclude=/usr/share/doc/*' \
		'--dpkgopt=path-include=/usr/share/doc/*/copyright' \
		'--dpkgopt=path-exclude=/usr/share/locale/*' \
		'--dpkgopt=path-include=/usr/share/locale/locale.alias' \
		"--include=$(read_packages | paste -sd,)" \
		"$SUITE" \
		'<output>.tar' \
		"deb $MIRROR $SUITE main"
}

dry_run() {
	say "dry run -- nothing is written and nothing is fetched from the network"
	echo
	info "project tree:  $PROJECT_ROOT"
	info "output would be: $OUT_DIR"
	info "suite/arch:    $SUITE/$ARCH over $MIRROR"
	info "ext4 image:    $( ((MAKE_EXT4)) && echo "yes, $IMAGE_SIZE (grows via x-systemd.growfs)" || echo no )"
	echo

	say "1. tool check"
	check_tools || true
	echo

	say "2. package list ($PACKAGES_FILE)"
	local n; n=$(read_packages | wc -l)
	read_packages | sed 's/^/    /'
	info "-- $n packages beyond minbase"
	echo

	say "3. bootstrap call (this is how it would read)"
	mmdebstrap_argv | sed -e '1s/^/    /' -e '2,$s/^/        /'
	echo

	say "4. overlay ($OVERLAY) -- these files are laid on top"
	if [[ -d "$OVERLAY" ]]; then
		(cd "$OVERLAY" && find . -mindepth 1 \( -type f -o -type l \) -printf '    /%P\n' | sort)
		(cd "$OVERLAY" && find . -mindepth 1 -type d -empty -printf '    /%P/  (empty directory)\n' | sort)
	else
		warn "overlay/ is missing: $OVERLAY"
	fi
	echo

	say "5. WLAN ($WIFI_ENV_ORIGIN: $WIFI_ENV)"
	if sh "$WIFI_CHECK" check "$WIFI_ENV" 2>&1 | sed 's/^/    /'; then
		info "-> /etc/h713/wifi.env (0600), h713-wifi.service in multi-user.target.wants"
	fi
	echo

	say "6. rework on the tree"
	cat <<'EOF'
    - empty /etc/machine-id  (else every device would have the same ID)
    - delete /etc/ssh/ssh_host_* -> hy310-ssh-host-keys.service makes them
      again on the first start (else: the same host keys on every device)
    - leave/set the root password locked ("*"); you get in over the autologin
      on ttyS0, over ssh only with the key from the installer
    - link the units: serial-getty@ttyS0, hy310-zram-swap, hy310-ssh-host-keys,
      h713-hdcp-key, h713-wifi
    - make /data and /etc/h713/tvconfig (tvconfig stays EMPTY)
    - empty /var/lib/apt/lists and /var/cache/apt (107 §8: no apt update at
      build time -- 40 MiB of lists, stale on the first day)
EOF
	echo

	say "7. project parts"
	if ((SKIP_PROJECT)); then
		info "skipped (--skip-project)"
	elif [[ -x "$PROJECT_SCRIPT" ]]; then
		MODROOT="$MODROOT" H713_TV_SRC="$H713_TV_SRC" \
		H713_TV_BIN="$H713_TV_BIN" H713_PQ_SRC="$H713_PQ_SRC" \
			"$PROJECT_SCRIPT" --dry-run "<tree>" || true
	else
		warn "install-projekt.sh is missing or not executable: $PROJECT_SCRIPT"
	fi
	echo

	say "8. output"
	info "$OUT_DIR/hy310-rootfs.tar"
	((MAKE_EXT4)) && info "$OUT_DIR/hy310-rootfs.ext4  ($IMAGE_SIZE)"
	info "$OUT_DIR/hy310-rootfs.manifest"
	info "$OUT_DIR/ROOTFS-SHA256SUMS"
	echo
	say "dry run finished. Nothing written."
}

if ((DRY_RUN)); then
	dry_run
	exit 0
fi

# ===========================================================================
# Real run
# ===========================================================================
say "building the HY310 rootfs -- $SUITE/$ARCH"
check_tools || die "tools are missing (see above). With --dry-run it runs through anyway."
KEYRING=$(find_keyring) || die "no Debian keyring found. apt-get install debian-archive-keyring"
check_keyring "$KEYRING" || die "the keyring does not fit the suite (see above)"

[[ -d "$OVERLAY" ]] || die "overlay/ is missing: $OVERLAY"

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/hy310-rootfs.XXXXXX")
cleanup() { ((KEEP_WORK)) || rm -rf -- "$WORK"; }
trap cleanup EXIT

TREE="$WORK/tree"
BOOTSTRAP_TAR="$WORK/bootstrap.tar"

# --- 1. bootstrap ----------------------------------------------------------
say "0/6 check wifi.env ($WIFI_ENV_ORIGIN)"
sh "$WIFI_CHECK" check "$WIFI_ENV" | sed 's/^/    /' || die "wifi.env is not usable: $WIFI_ENV"
if ((WIFI_IS_DEFAULT)); then
	warn "This image opens the access point 'h713' with the password 'magcubic'."
	warn "That is what the docs and the repository say. Your own version: --wifi-env FILE"
	warn "or rootfs/wifi.env -- or change /etc/h713/wifi.env on the device."
fi

say "1/6 mmdebstrap --variant=minbase"
mapfile -t MMARGV < <(mmdebstrap_argv)
# replace the placeholder argument '<output>.tar' with the real path
for i in "${!MMARGV[@]}"; do
	[[ "${MMARGV[$i]}" == '<output>.tar' ]] && MMARGV[$i]=$BOOTSTRAP_TAR
done
"${MMARGV[@]}"
[[ -s "$BOOTSTRAP_TAR" ]] || die "mmdebstrap delivered no tar"
info "bootstrap tar: $(du -h "$BOOTSTRAP_TAR" | cut -f1)"

# --- 2. unpack -------------------------------------------------------------
say "2/6 unpack"
mkdir -p "$TREE"
# ./dev/* is left out: in the rootless container tar may not mknod, and it is
# not needed -- the kernel mounts devtmpfs on /dev before init runs
# (CONFIG_DEVTMPFS_MOUNT=y in our defconfig). The final tar excludes ./dev/*
# anyway (step 6).
tar --numeric-owner --xattrs --acls --exclude='./dev/*' -C "$TREE" -xf "$BOOTSTRAP_TAR"
rm -f "$BOOTSTRAP_TAR"
[[ -d "$TREE/etc" && -d "$TREE/usr" ]] || die "the tree does not look like a rootfs"

# --- 3. overlay ------------------------------------------------------------
say "3/6 lay the overlay"
# -a keeps permissions and symlinks; the overlay is deliberately root:root, so
# a chown to 0:0 follows (in case it was built as a user, see --mode=unshare).
# --exclude: a __pycache__ appears as soon as somebody starts a script out of
# the overlay by hand, and would otherwise end up in the image (11.09.2026).
tar -C "$OVERLAY" --exclude=__pycache__ --exclude="*.pyc" -cf - . |
	tar -C "$TREE" --no-same-owner -xf -
(cd "$OVERLAY" && find . -mindepth 1 \( -type f -o -type l \) -printf '%P\n') | \
	while read -r rel; do
		chown 0:0 "$TREE/$rel" 2>/dev/null || true
	done
info "$(cd "$OVERLAY" && find . -mindepth 1 \( -type f -o -type l \) | wc -l) files from overlay/"
# wifi.env: the chosen version, 0600 root -- it carries a password.
install -m 0600 -o 0 -g 0 "$WIFI_ENV" "$TREE/etc/h713/wifi.env" 2>/dev/null || \
	{ install -m 0600 "$WIFI_ENV" "$TREE/etc/h713/wifi.env"; chown 0:0 "$TREE/etc/h713/wifi.env" 2>/dev/null || true; }
info "/etc/h713/wifi.env from $WIFI_ENV_ORIGIN"

# --- 4. rework -------------------------------------------------------------
say "4/6 rework"

# 4a. Directories that MUST exist. /etc/h713/tvconfig is in the overlay too,
# but an empty directory does not survive git -- so once more explicitly here.
# It stays EMPTY: the PQ data is put in by the installer out of h713-extract
# (107 §8, 108 §6).
install -d -m 0755 "$TREE/etc/h713" "$TREE/etc/h713/tvconfig"
# /data: everything that grows (recordings, captures, optional logs) -- since
# layout v3 a directory in the rootfs, not a partition of its own (109 §2.2).
install -d -m 0755 "$TREE/data"
install -d -m 0755 "$TREE/boot"

# 4b. Machine identity: empty means "make it on the first start".
: > "$TREE/etc/machine-id"
rm -f "$TREE/var/lib/dbus/machine-id"

# 4c. SSH host keys: the postinst made them IN THE CHROOT, that is, at build
# time. Away with them, else every device has the same ones.
rm -f "$TREE"/etc/ssh/ssh_host_*
info "host keys removed (hy310-ssh-host-keys.service makes them again)"

# 4d. Root password locked. The way in is the autologin on ttyS0; over ssh
# only with a key, and that one comes from the installer (107 §3).
if [[ -f "$TREE/etc/shadow" ]]; then
	sed -i 's/^root:[^:]*:/root:*:/' "$TREE/etc/shadow"
	root_hash=$(awk -F: '$1=="root"{print $2}' "$TREE/etc/shadow")
	[[ "$root_hash" == '*' ]] || die "root password not locked (field: '$root_hash')"
	info "root password locked ('*')"
fi

# 4e. Optional key -- explicitly NOT the release way.
if [[ -n "$AUTHORIZED_KEY" ]]; then
	[[ -s "$AUTHORIZED_KEY" ]] || die "key file empty/missing: $AUTHORIZED_KEY"
	install -d -m 0700 "$TREE/root/.ssh"
	install -m 0600 "$AUTHORIZED_KEY" "$TREE/root/.ssh/authorized_keys"
	warn "--authorized-key: this image carries a key built in for good."
	warn "For a release that is the wrong way (107 §3)."
fi

# 4f. Link the units. Without a running systemd in the chroot: by hand, the way
# `systemctl enable` would do it too.
link_unit() { # $1 = target unit file (absolute in the tree), $2 = wants directory, $3 = name
	install -d "$TREE/$2"
	ln -sfn "$1" "$TREE/$2/$3"
}
link_unit /usr/lib/systemd/system/serial-getty@.service \
	etc/systemd/system/getty.target.wants serial-getty@ttyS0.service
link_unit /etc/systemd/system/hy310-zram-swap.service \
	etc/systemd/system/swap.target.wants hy310-zram-swap.service
link_unit /etc/systemd/system/hy310-ssh-host-keys.service \
	etc/systemd/system/ssh.service.wants hy310-ssh-host-keys.service
# h713-hdcp-key MUST be linked: modprobe.d blocks the autoload of the hdmirx
# driver so that the init sequence does not run without an HDCP key. Without
# this line nobody loads it -- the device would stay without a picture.
link_unit /etc/systemd/system/h713-hdcp-key.service \
	etc/systemd/system/sysinit.target.wants h713-hdcp-key.service
# h713-wifi: reads /etc/h713/wifi.env and brings up an AP, a station or nothing.
# The packages' own hostapd/wpa_supplicant units are masked in the overlay (-> /dev/null).
link_unit /etc/systemd/system/h713-wifi.service \
	etc/systemd/system/multi-user.target.wants h713-wifi.service
info "units linked: serial-getty@ttyS0, hy310-zram-swap, hy310-ssh-host-keys, h713-hdcp-key, h713-wifi"

# 4g. resolv.conf has to be a real file, not a symlink to systemd-resolved --
# that service does not exist here, isc-dhcp-client writes into it itself
# (S41 §1: that is how it runs today).
rm -f "$TREE/etc/resolv.conf"
: > "$TREE/etc/resolv.conf"
chmod 0644 "$TREE/etc/resolv.conf"

# 4h. apt: sources yes, lists no (107 §8).
rm -f "$TREE/etc/apt/sources.list"
rm -rf "$TREE"/var/lib/apt/lists/* "$TREE"/var/cache/apt/archives/*.deb
install -d "$TREE/var/lib/apt/lists/partial"
info "apt sources written, package lists NOT baked in"

# 4i. Do not create the journal directory: if /var/log/journal exists, journald
# switches to persistent despite Storage=volatile. That is exactly the trap
# 107 §4.1 wants to avoid.
rm -rf "$TREE/var/log/journal"

# 4j. regulatory.db: wireless-regdb ships two signed copies and points, through
# an alternative (priority 100 against 50), at the Debian-signed one. Our kernel
# is mainline and carries only the upstream certificates (net/wireless/certs:
# sforshee, wens) at CFG80211_REQUIRE_SIGNED_REGDB=y -- it cannot check the
# Debian signature and would reject the database. So point at -upstream. For the
# aic8800 (self-managed wiphy, default_ccode) that has no consequences; for
# cfg80211's global realm it is the difference between "loaded" and "discarded".
# (cstenger's finding, mainline/tools/rootfs/customize.sh.)
# Without a chroot: the alternative is only a symlink under /etc/alternatives.
for alt in regulatory.db regulatory.db.p7s; do
	if [[ -e "$TREE/lib/firmware/$alt-upstream" && -L "$TREE/etc/alternatives/$alt" ]]; then
		ln -sfn "/lib/firmware/$alt-upstream" "$TREE/etc/alternatives/$alt"
	fi
done
info "regulatory.db -> upstream-signed (the kernel knows only sforshee/wens)"

# --- 5. project parts ------------------------------------------------------
if ((SKIP_PROJECT)); then
	say "5/6 project parts skipped (--skip-project)"
else
	say "5/6 project parts"
	[[ -x "$PROJECT_SCRIPT" ]] || die "install-projekt.sh is missing: $PROJECT_SCRIPT"
	MODROOT="$MODROOT" H713_TV_SRC="$H713_TV_SRC" \
	H713_TV_BIN="$H713_TV_BIN" H713_PQ_SRC="$H713_PQ_SRC" \
		"$PROJECT_SCRIPT" "$TREE"
fi

# --- 6. acceptance, tar, ext4 ----------------------------------------------
say "6/6 acceptance and output"

# The checks that are ALLOWED to fail -- better no image than a wrong one.
t() { # t "what" test-expression...
	local what=$1; shift
	if "$@"; then info "✓ $what"; else die "acceptance failed: $what"; fi
}
t "systemd as init"           test -x "$TREE/usr/lib/systemd/systemd"
t "agetty present"            test -x "$TREE/sbin/agetty"
t "autologin drop-in"         test -f "$TREE/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf"
t "serial-getty linked"       test -L "$TREE/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service"
t "journald volatile"         grep -qx 'Storage=volatile' "$TREE/etc/systemd/journald.conf.d/10-hy310.conf"
t "no /var/log/journal"       test ! -d "$TREE/var/log/journal"
t "fstab: PARTLABEL root"     grep -q '^PARTLABEL=hy310-rootfs' "$TREE/etc/fstab"
t "fstab: PARTLABEL boot"     grep -q '^PARTLABEL=hy310-boot' "$TREE/etc/fstab"
t "fstab: no third line"      test "$(grep -c '^PARTLABEL=' "$TREE/etc/fstab")" = 2
t "fw_env at 0x700000"        grep -q '^/dev/mmcblk0[[:space:]]*0x700000[[:space:]]*0x10000' "$TREE/etc/fw_env.config"
t "fw_printenv present"       test -x "$TREE/usr/bin/fw_printenv"
t "network via ifupdown/DHCP" grep -q 'iface eth0 inet dhcp' "$TREE/etc/network/interfaces"
t "hy310-logs executable"     test -x "$TREE/usr/local/sbin/hy310-logs"
t "zram unit linked"          test -L "$TREE/etc/systemd/system/swap.target.wants/hy310-zram-swap.service"
t "HDCP unit linked"         test -L "$TREE/etc/systemd/system/sysinit.target.wants/h713-hdcp-key.service"
t "hdmirx autoload blocked"  test -f "$TREE/etc/modprobe.d/h713-hdcp-key.conf"
t "swappiness=180"            grep -q 'vm.swappiness *= *180' "$TREE/etc/sysctl.d/99-hy310-zram.conf"
t "tvconfig empty"            test -z "$(ls -A "$TREE/etc/h713/tvconfig")"
t "/data present"             test -d "$TREE/data"
t "no host keys"              test -z "$(find "$TREE/etc/ssh" -maxdepth 1 -name 'ssh_host_*' -print -quit)"
t "no apt lists"              test -z "$(find "$TREE/var/lib/apt/lists" -maxdepth 1 -type f -print -quit)"
t "apt source signed"         grep -q '^Signed-By:' "$TREE/etc/apt/sources.list.d/debian.sources"
# Leave comment lines out: our own sources file mentions trusted=yes in its
# reasoning, and an acceptance check that trips over its own comment checks
# nothing.
t "no trusted=yes"            bash -c "! grep -rhv '^[[:space:]]*#' '$TREE/etc/apt' 2>/dev/null | grep -q 'trusted=yes'"
t "no compiler"               test ! -e "$TREE/usr/bin/gcc"
t "no GStreamer"              test ! -e "$TREE/usr/bin/gst-launch-1.0"
# WLAN has been in since 12.09. (Marco). Until then this said "no
# wpa_supplicant" -- the sentence was turned round, not deleted.
t "wpa_supplicant present"    test -x "$TREE/usr/sbin/wpa_supplicant"
t "hostapd present"           test -x "$TREE/usr/sbin/hostapd"
t "dnsmasq present"           test -x "$TREE/usr/sbin/dnsmasq"
t "no dnsmasq.service"        test ! -e "$TREE/lib/systemd/system/dnsmasq.service"
t "hostapd.service masked"    test "$(readlink "$TREE/etc/systemd/system/hostapd.service")" = /dev/null
t "wpa_supplicant masked"     test "$(readlink "$TREE/etc/systemd/system/wpa_supplicant.service")" = /dev/null
t "wifi.env 0600"             test "$(stat -c %a "$TREE/etc/h713/wifi.env")" = 600
t "wifi.env usable"           sh "$TREE/usr/local/sbin/h713-wifi" check "$TREE/etc/h713/wifi.env"
t "h713-wifi linked"          test -L "$TREE/etc/systemd/system/multi-user.target.wants/h713-wifi.service"
t "aic8800 quiet"             grep -q 'aicwf_dbg_level=0x1' "$TREE/etc/modprobe.d/aic8800.conf"
t "regulatory.db upstream"    test "$(readlink "$TREE/etc/alternatives/regulatory.db")" = /lib/firmware/regulatory.db-upstream

TREE_KIB=$(du -sxk "$TREE" | cut -f1)
info "tree size: $((TREE_KIB / 1024)) MiB ($TREE_KIB KiB, du -sx)"
if ((TREE_KIB > 500 * 1024)); then
	warn "over the acceptance limit of 107 §7.1 (500 MiB)"
fi

say "write the tar"
TAR_OUT="$OUT_DIR/hy310-rootfs.tar"
tar --numeric-owner --xattrs --acls --sort=name \
	--exclude=./dev/* -C "$TREE" -cf "$TAR_OUT" .
info "$TAR_OUT ($(du -h "$TAR_OUT" | cut -f1))"

if ((MAKE_EXT4)); then
	say "write the ext4 image ($IMAGE_SIZE)"
	EXT4_OUT="$OUT_DIR/hy310-rootfs.ext4"
	rm -f "$EXT4_OUT"
	truncate -s "$IMAGE_SIZE" "$EXT4_OUT"
	# -L hy310-rootfs: the same label as the partition, so that blkid and
	# e2label say the same. -m 1: 1 % reserve is enough, this is no system
	# disk with a /var fill-level problem.
	mke2fs -q -F -t ext4 -L hy310-rootfs -m 1 \
		-E lazy_itable_init=0,lazy_journal_init=0 \
		-d "$TREE" "$EXT4_OUT"
	e2fsck -fn "$EXT4_OUT" >/dev/null
	info "$EXT4_OUT ($(du -h "$EXT4_OUT" | cut -f1)) -- grows on the first start (x-systemd.growfs)"
fi

say "manifest"
MANIFEST="$OUT_DIR/hy310-rootfs.manifest"
{
	echo "suite=$SUITE"
	echo "arch=$ARCH"
	echo "mirror=$MIRROR"
	echo "keyring=$KEYRING"
	echo "built=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
	echo "tree_size_kib=$TREE_KIB"
	echo "packages_beyond_minbase=$(read_packages | paste -sd,)"
	echo "installed=$(chroot_count=$(grep -c '^Package: ' "$TREE/var/lib/dpkg/status" 2>/dev/null || echo 0); echo "$chroot_count")"
	echo "modroot=${MODROOT#"$PROJECT_ROOT"/}"
	echo "h713_tv=${H713_TV_BIN#"$PROJECT_ROOT"/}"
	echo "ssh_key_built_in=$( [[ -n "$AUTHORIZED_KEY" ]] && echo yes || echo no )"
	echo "image_size=$( ((MAKE_EXT4)) && echo "$IMAGE_SIZE" || echo none )"
} > "$MANIFEST"
cat "$MANIFEST" | sed 's/^/    /'

(
	cd "$OUT_DIR"
	# shellcheck disable=SC2012
	sha256sum hy310-rootfs.tar hy310-rootfs.manifest \
		$( ((MAKE_EXT4)) && echo hy310-rootfs.ext4 ) > ROOTFS-SHA256SUMS
)
say "done"
ls -lh "$OUT_DIR"
