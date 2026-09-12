#!/usr/bin/env bash
# Switch the board between our stack and the vendor's, and flash ours in the
# split layout that makes the switch a 32 KiB write.
#
# Both chains are complete and resident; only the 32 KiB entry point at LBA 0x10
# is swapped, because the BROM reads the first stage from there and nowhere else
# (Android's A/B slots only cover kernel and OS, not the boot chain):
#
#   ours    SPL      LBA 0x10   <-- contended, this is the switch
#           U-Boot   LBA 0x49ac00 ('empty' partition)
#           env      LBA 0x49ec00 ('empty' + 8 MiB)
#           kernel   boot_a       rootfs  UDISK
#   vendor  boot0    LBA 0x100    (the vendor's own 128 KiB second copy)
#           U-Boot   LBA 24576 and 32800 -- its TOC1 boot package, which also
#                    carries BL31, SCP and OP-TEE; never overwritten, and there
#                    is only ever one copy of it
#           kernel   boot_b       Android  vendor_boot_b, dtbo_b, vbmeta*_b, super
#
# Usage:
#   tools/boot-switch.sh status  --dev /dev/sdX
#   tools/boot-switch.sh stage   [--via fastboot | --dev /dev/sdX]
#   tools/boot-switch.sh vendor  [--via fastboot | --dev /dev/sdX]
#   tools/boot-switch.sh ours    [--via fel      | --dev /dev/sdX]
#   tools/boot-switch.sh install [--via fastboot | --dev /dev/sdX]
#
# "stage" restores the vendor's boot0 to LBA 0x100 and stashes our SPL at LBA
# 0x49cc00, so that afterwards each direction is one on-board copy: "run
# switch_vendor" at our U-Boot prompt, or the mmc read/write pair in
# docs/flash.md at a vendor prompt.  Run it once, after "install".
#
# --dev is the whole eMMC as exposed by "ums 0 mmc 1" from U-Boot, or
# /dev/mmcblk0 from Debian/Android on the board itself.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OURS_IMG="$ROOT/build/out/u-boot-sunxi-with-spl-ddr3.bin"
VENDOR_BOOT0="$ROOT/local/stock-boot/boot0-board-b-emmc-sector16.bin"
RESTORE_SPL="$ROOT/build/out/h713-restore-spl.bin"
SUNXI_FEL="$ROOT/external/sunxi-tools/sunxi-fel"

FIRST_STAGE_LBA=16       # 0x10     BROM entry, 64 sectors
VENDOR_BOOT0_LBA=256     # 0x100    the vendor's own second copy, at 128 KiB
UBOOT_PROPER_LBA=4828160 # 0x49ac00 start of the 'empty' partition
OURS_STASH_LBA=4836352   # 0x49cc00 'empty' + 4 MiB, our SPL kept on-board
DRY=0

die() { echo "$*" >&2; exit 1; }

# A first stage that fails its own eGON checksum boots nothing and costs a FEL
# trip to undo, so every candidate is checked before it is written anywhere.
check_egon() {
	python3 - "$1" <<'EOF'
import struct, sys
p = sys.argv[1]
b = open(p, 'rb').read()
if len(b) != 32768:
    sys.exit(f"{p}: {len(b)} bytes, expected exactly 32768")
if b[4:12] != b'eGON.BT0':
    sys.exit(f"{p}: no eGON.BT0 magic at +4")
length = struct.unpack('<I', b[0x10:0x14])[0]
stored = struct.unpack('<I', b[0x0c:0x10])[0]
if length > len(b):
    sys.exit(f"{p}: header length {length} exceeds the file")
d = bytearray(b[:length])
d[0x0c:0x10] = struct.pack('<I', 0x5F0A6C39)
s = 0
for i in range(0, length, 4):
    s = (s + struct.unpack('<I', bytes(d[i:i+4]))[0]) & 0xffffffff
if s != stored:
    sys.exit(f"{p}: eGON checksum 0x{s:08x} != stored 0x{stored:08x}")
EOF
}

# Refuse to dd into anything that is not this board's eMMC.
check_dev() {
	local dev="$1"
	[ -b "$dev" ] || die "$dev is not a block device"
	sudo python3 - "$dev" <<'EOF'
import struct, sys
dev = sys.argv[1]
with open(dev, 'rb') as f:
    f.seek(512)
    hdr = f.read(92)
    if hdr[:8] != b'EFI PART':
        sys.exit(f"{dev}: no GPT — refusing to write")
    part_lba = struct.unpack('<Q', hdr[72:80])[0]
    n, sz = struct.unpack('<II', hdr[80:88])
    f.seek(part_lba * 512)
    data = f.read(n * sz)
names = [data[i*sz+56:i*sz+128].decode('utf-16-le').rstrip('\x00') for i in range(n)]
names = [x for x in names if x]
if not names or names[0] != 'bootloader_a' or names[-1] != 'UDISK':
    sys.exit(f"{dev}: partition table is not the H713 layout "
             f"(first={names[:1]}, last={names[-1:]}) — refusing to write")
EOF
}

dd_write() {  # file lba dev
	local f="$1" lba="$2" dev="$3" sz n rb
	sz=$(stat -c%s "$f")
	echo "==> dd $(basename "$f") -> $dev sector $lba ($sz B)"
	[ "$DRY" = 1 ] && return 0
	sudo dd if="$f" of="$dev" bs=512 seek="$lba" conv=fsync status=none
	# Read back into a file rather than a pipe: the device hands back whole
	# sectors, so a "head -c" pipe would SIGPIPE dd and trip pipefail on a
	# comparison that actually succeeded.
	n=$(( ( sz + 511 ) / 512 ))
	rb=$(mktemp)
	sudo dd if="$dev" bs=512 skip="$lba" count="$n" status=none of="$rb"
	cmp -s -n "$sz" "$rb" "$f" \
		|| { rm -f "$rb"; die "read-back differs from $f — do NOT power cycle, investigate first"; }
	rm -f "$rb"
	echo "    read-back OK"
}

fb_flash() {  # alias file
	echo "==> fastboot flash $1 $(basename "$2") ($(stat -c%s "$2") B)"
	[ "$DRY" = 1 ] && return 0
	fastboot flash "$1" "$2"
}

split_ours() {  # -> $TMP/spl.bin, $TMP/uboot-proper.bin
	[ -f "$OURS_IMG" ] || die "missing $OURS_IMG — run build/build.sh"
	# An image built for an older layout expects U-Boot proper elsewhere.  Writing
	# it to the new locations produces an SPL that loads nothing, so refuse.
	local def="$ROOT/external/u-boot/configs/hy200_qz713df_a1_defconfig"
	[ "$OURS_IMG" -nt "$def" ] || die \
		"$(basename "$OURS_IMG") is older than $(basename "$def") — it may
predate the current layout and would look for U-Boot proper where it used to be.
Rebuild before flashing."
	TMP=$(mktemp -d)
	trap 'rm -rf "$TMP"' EXIT
	head -c 32768 "$OURS_IMG" > "$TMP/spl.bin"
	tail -c +32769 "$OURS_IMG" > "$TMP/uboot-proper.bin"
	check_egon "$TMP/spl.bin"
}

cmd_status() {
	local dev="$1"
	check_dev "$dev"
	local cur ours vendor
	cur=$(sudo dd if="$dev" bs=512 skip=$FIRST_STAGE_LBA count=64 status=none | sha256sum | cut -d' ' -f1)
	ours=$(head -c 32768 "$OURS_IMG" 2>/dev/null | sha256sum | cut -d' ' -f1)
	vendor=$(sha256sum "$VENDOR_BOOT0" 2>/dev/null | cut -d' ' -f1)
	echo "first stage at LBA 0x10: $cur"
	case "$cur" in
		"$ours")   echo "  -> OURS (matches $(basename "$OURS_IMG") first 32 KiB)" ;;
		"$vendor") echo "  -> VENDOR (matches $(basename "$VENDOR_BOOT0"))" ;;
		*)         echo "  -> UNKNOWN — neither the current build nor the captured vendor boot0" ;;
	esac
}

cmd_stage() {
	local via="$1" dev="$2"
	[ -f "$VENDOR_BOOT0" ] || die "missing $VENDOR_BOOT0 (extract it from the board-b capture)"
	check_egon "$VENDOR_BOOT0"
	split_ours
	case "$via" in
	fastboot)
		fb_flash vboot0 "$VENDOR_BOOT0"
		fb_flash splstash "$TMP/spl.bin"
		;;
	dev)
		check_dev "$dev"
		dd_write "$VENDOR_BOOT0" $VENDOR_BOOT0_LBA "$dev"
		dd_write "$TMP/spl.bin" $OURS_STASH_LBA "$dev"
		;;
	esac
	echo
	echo "Both chains are now resident:"
	echo "  vendor boot0 at LBA 0x100    -> 'run switch_vendor' from our U-Boot"
	echo "  our SPL      at LBA 0x49cc00 -> 'mmc dev 1; mmc read 0x48000000 0x49cc00 0x40;"
	echo "                                   mmc write 0x48000000 0x10 0x40' from a vendor prompt"
	echo "Note: with a valid boot0 at LBA 0x100, a corrupt first stage may boot the"
	echo "vendor instead of dropping to FEL.  Check 'status' before concluding anything."
}

cmd_vendor() {
	local via="$1" dev="$2"
	[ -f "$VENDOR_BOOT0" ] || die "missing $VENDOR_BOOT0 (extract it from the board-b capture)"
	check_egon "$VENDOR_BOOT0"
	case "$via" in
	fastboot) fb_flash uboot "$VENDOR_BOOT0" ;;
	dev)      check_dev "$dev"; dd_write "$VENDOR_BOOT0" $FIRST_STAGE_LBA "$dev" ;;
	esac
	echo
	echo "Vendor first stage installed.  Power cycle to boot it."
	echo "Capture UART from the first byte; the fastlogo lines appear within ~2 s."
	echo "Come back with:  tools/boot-switch.sh ours --via fel   (hold the FEL button)"
}

cmd_ours() {
	local via="$1" dev="$2"
	case "$via" in
	fel)
		[ -x "$SUNXI_FEL" ] || die "missing $SUNXI_FEL"
		[ -f "$RESTORE_SPL" ] || die "missing $RESTORE_SPL"
		# The restore SPL carries our first stage as a payload; if it predates
		# the current build it will install a stale SPL that looks for U-Boot
		# proper somewhere it no longer is.
		local hdr="$ROOT/external/u-boot/arch/arm/mach-sunxi/h713_spl_payload.h"
		if [ -f "$hdr" ] && [ -f "$OURS_IMG" ] && [ "$OURS_IMG" -nt "$hdr" ]; then
			echo "WARNING: $(basename "$hdr") is older than the current build." >&2
			echo "         Regenerate it and rebuild the restore SPL first" >&2
			echo "         (docs/flash.md, 'Recovering a clobbered first stage')." >&2
		fi
		echo "==> hold the FEL button and power on, then:"
		echo "    $SUNXI_FEL version"
		[ "$DRY" = 1 ] || "$SUNXI_FEL" version
		[ "$DRY" = 1 ] || "$SUNXI_FEL" -p spl "$RESTORE_SPL"
		echo "UART should show '=== H713 SPL RESTORE ===' and 'wrote 64/64 RESTORED-OK'."
		;;
	fastboot)
		# Only useful while ours is still running -- once the vendor owns
		# LBA 0x10 there is no fastboot to talk to.  Handy for iterating on
		# the SPL, which is where the chainloader lives.
		split_ours
		fb_flash uboot "$TMP/spl.bin"
		;;
	dev)
		split_ours
		check_dev "$dev"
		dd_write "$TMP/spl.bin" $FIRST_STAGE_LBA "$dev"
		;;
	esac
	echo
	echo "Our first stage installed.  Power cycle."
}

cmd_install() {
	local via="$1" dev="$2"
	split_ours
	# U-Boot proper first: a half-finished install then leaves the *old* working
	# first stage in place rather than a new one pointing at nothing.
	case "$via" in
	fastboot)
		fb_flash ubootp "$TMP/uboot-proper.bin"
		fb_flash uboot "$TMP/spl.bin"
		;;
	dev)
		check_dev "$dev"
		dd_write "$TMP/uboot-proper.bin" $UBOOT_PROPER_LBA "$dev"
		dd_write "$TMP/spl.bin" $FIRST_STAGE_LBA "$dev"
		;;
	esac
	echo
	echo "Installed: first stage at LBA 0x10, U-Boot proper at LBA 0x49ac00."
	echo "The environment is at LBA 0x49ec00; re-run saveenv after booting."
}

[ $# -ge 1 ] || die "usage: $(basename "$0") status|stage|vendor|ours|install [--via X] [--dev /dev/sdX]"
CMD="$1"; shift
VIA=""; DEV=""
while [ $# -gt 0 ]; do
	case "$1" in
	--via) VIA="$2"; shift 2 ;;
	--dev) DEV="$2"; VIA="${VIA:-dev}"; shift 2 ;;
	--dry-run) DRY=1; shift ;;
	*) die "unknown argument: $1" ;;
	esac
done

case "$CMD" in
status)  [ -n "$DEV" ] || die "status needs --dev (a running U-Boot cannot be read from the host)"
         cmd_status "$DEV" ;;
stage)   cmd_stage  "${VIA:-fastboot}" "$DEV" ;;
vendor)  cmd_vendor "${VIA:-fastboot}" "$DEV" ;;
ours)    cmd_ours   "${VIA:-fel}" "$DEV" ;;
install) cmd_install "${VIA:-fastboot}" "$DEV" ;;
*)       die "unknown command: $CMD" ;;
esac
