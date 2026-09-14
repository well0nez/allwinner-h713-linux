#!/usr/bin/env bash
# release/build-all.sh -- vom frischen Klon bis zum einspielbaren Abbild, ein Einstieg.
#
#   release/build-all.sh --version v0.10 [--vendor DIR] [--wifi-env DATEI]
#                        [--jobs N] [--skip-bl31] [--skip-uboot] [--skip-kernel]
#                        [--skip-rootfs] [--dry-run]
#
# Reihenfolge (doku/116 P4):
#   1 bl31  2 U-Boot (+ SPL/proper trennen + Umgebung mit CRC)  2b Installer-U-Boot (ums)
#   2b2 Sonden-U-Boot (h713_probe)  2c sunxi-fel (Falltuer)  3 Kernel (+ Module)
#   4 aic8800  5 Debian-Keyring (gepinnt)  6 Sysroot + h713-tv quer  7 Rootfs
#   8 ext4-Eingaben  9 Abbild  10 Pruefen (mit --vendor: voller Selbsttest)  11 Stempel
#
# Laeuft auf dem Arbeitsrechner und treibt den Container h713-build (doku/50 §Bauen);
# nichts wird auf dem Host gebaut (Gedaechtnis: "Bauen nur im Container"). Alles,
# was frueher von Hand nach tftp/ kopiert wurde, entsteht hier unter
# mainline/build/out/ und wird dem Abbild-Bauer ausdruecklich uebergeben --
# tftp/ ist ab jetzt Entwicklungsablage, keine Eingabe.
#
# Was dieses Skript NICHT tut: den Extrakt aus dem Abzug des Nutzers erzeugen
# (das macht hy310-install beim Einspielen) und irgendetwas ans Geraet schicken.
#
# Pfade der Bausteine stehen unten in einem Block, damit der Umzug nach
# installer/ und rootfs/ (doku/116 P3) genau diese Zeilen aendert und sonst nichts.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# --- Pfade (P3 aendert nur diese) ------------------------------------------
MAINLINE="$ROOT/mainline"
# Beide Layouts: Release-Repo (installer/, rootfs/ unter der Wurzel) und
# Arbeitsverzeichnis (analyse/release/arbeit/...). Das Repo-Layout gewinnt.
if [[ -d "$ROOT/installer" && -d "$ROOT/rootfs" ]]; then
	INSTALLER="$ROOT/installer"; EXTRAKTOR="$ROOT/installer/h713-extract"; ROOTFS="$ROOT/rootfs"
else
	INSTALLER="$ROOT/analyse/release/arbeit/r0-fel"; EXTRAKTOR="$ROOT/analyse/release/arbeit/r2-extract/h713-extract"; ROOTFS="$ROOT/analyse/release/arbeit/rootfs"
fi
USERSPACE="$ROOT/userspace"
CONTAINER=h713-build
# Wie heisst $ROOT im Container? Aus den Mounts des Containers ableiten, nicht
# annehmen -- das Release-Repo kann unterhalb des gemounteten Arbeitsverzeichnisses
# liegen (z. B. /opt/Projekte/h713/repo-neu -> /work/repo-neu), doku/116 P3.
container_pfad() {
	local quelle ziel
	while IFS=' ' read -r quelle ziel; do
		[[ -n "$quelle" ]] || continue
		if [[ "$ROOT" == "$quelle" || "$ROOT" == "$quelle"/* ]]; then
			printf '%s%s' "$ziel" "${ROOT#"$quelle"}"; return 0
		fi
	done < <(podman inspect -f '{{range .Mounts}}{{.Source}} {{.Destination}}{{"\n"}}{{end}}' "$CONTAINER" 2>/dev/null)
	return 1
}
WORK=$(container_pfad) || { echo "Fehler: $ROOT liegt in keinem Mount des Containers $CONTAINER" >&2; exit 1; }
# ---------------------------------------------------------------------------
UBOOT_DEFCONFIG=hy310_qz713_v3_1_defconfig
UBOOT_INSTALLER_DEFCONFIG=hy310_installer_defconfig   # FEL -> ums, fuer hy310-install --uboot
UBOOT_PROBE_DEFCONFIG=h713_probe_defconfig            # FEL -> h713_probe, fuer unbekannte H713-Geraete
KEYRING_DEB_URL="https://deb.debian.org/debian/pool/main/d/debian-archive-keyring/debian-archive-keyring_2025.1_all.deb"
KEYRING_DEB_SHA256=9ea7778e443144ca490668737a8ab22dd3e748bb99e805e22ec055abeb3c7fac
KEYRING_IN_DEB=./usr/share/keyrings/debian-archive-keyring.pgp   # byteidentisch zum bisher benutzten .gpg (12.09.)
SYSROOT_PAKETE=libc6-dev,libgcc-14-dev,libdrm-dev,libasound2-dev
DEBIAN_SUITE=trixie
DEBIAN_MIRROR=http://deb.debian.org/debian

VERSION= VENDOR= WIFI_ENV= JOBS=$(nproc) DRY=0
SKIP_BL31=0 SKIP_UBOOT=0 SKIP_KERNEL=0 SKIP_ROOTFS=0
while (($#)); do
	case "$1" in
	--version)   VERSION=${2:?}; shift 2 ;;
	--vendor)    VENDOR=$(cd "${2:?}" && pwd); shift 2 ;;
	--wifi-env)  WIFI_ENV=$(readlink -f "${2:?}"); shift 2 ;;
	--jobs)      JOBS=${2:?}; shift 2 ;;
	--skip-bl31)   SKIP_BL31=1; shift ;;
	--skip-uboot)  SKIP_UBOOT=1; shift ;;
	--skip-kernel) SKIP_KERNEL=1; shift ;;
	--skip-rootfs) SKIP_ROOTFS=1; shift ;;
	--dry-run)   DRY=1; shift ;;
	-h|--help)   sed -n '2,22p' "$0"; exit 0 ;;
	*) echo "unbekannt: $1" >&2; exit 2 ;;
	esac
done
[[ -n "$VERSION" ]] || { echo "--version vX.Y fehlt (Name des Abbilds: h713-hy310-vX.Y)" >&2; exit 2; }
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+(-[a-z0-9]+)?$ ]] || { echo "--version: erwartet vX.Y oder vX.Y-beta, nicht '$VERSION'" >&2; exit 2; }
NAME="h713-hy310-$VERSION"
OUT="$MAINLINE/build/out"
AUSGABE="$INSTALLER/out"

say()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nFehler: %s\n' "$*" >&2; exit 1; }
im_container()      { podman exec -e JOBS="$JOBS" "$CONTAINER" bash -lc "$*"; }
im_container_root() { podman exec -u root -e JOBS="$JOBS" "$CONTAINER" bash -lc "$*"; }
# Host-Pfad -> Container-Pfad
c() { printf '%s' "${1/#$ROOT/$WORK}"; }
T0=$(date +%s)
dauer() { local s=$(( $(date +%s) - T0 )); printf '%d min %02d s' $((s/60)) $((s%60)); }

say "build-all $NAME  ($(date '+%Y-%m-%d %H:%M'))"
info "Wurzel $ROOT"
((DRY)) && info "TROCKENLAUF -- es wird nichts gebaut"

# --- 0. Voraussetzungen -----------------------------------------------------
say "0/11 Voraussetzungen"
for w in podman python3 curl ar tar sha256sum; do command -v "$w" >/dev/null || die "fehlt auf dem Host: $w"; done
st=$(podman inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo fehlt)
case "$st" in
	running) info "Container $CONTAINER laeuft" ;;
	created|exited|stopped) ((DRY)) || podman start "$CONTAINER" >/dev/null; info "Container $CONTAINER gestartet (war: $st)" ;;
	*) die "Container $CONTAINER fehlt -- Rezept in doku/50-befehle.md §Bauen" ;;
esac
((DRY)) || im_container 'clang --version | head -1; command -v mmdebstrap mke2fs depmod dtc >/dev/null || { echo "im Container fehlen Werkzeuge (mmdebstrap/mke2fs/depmod/dtc)"; exit 1; }' | sed 's/^/    /'
for f in "$INSTALLER/hy310-mkimage.py" "$INSTALLER/mkimage-eingaben.sh" "$ROOTFS/build-rootfs.sh" "$EXTRAKTOR" "$MAINLINE/build/build.sh" "$MAINLINE/build/uboot-build.sh"; do
	[[ -e "$f" ]] || die "fehlt: $f"
done
[[ -z "$VENDOR" || -d "$VENDOR/boot/mips" ]] || die "--vendor $VENDOR sieht nicht wie eine h713-extract-Ausgabe aus (kein boot/mips/)"
mkdir -p "$OUT" "$AUSGABE"
((DRY)) && { info "wuerde bauen: bl31, U-Boot ($UBOOT_DEFCONFIG) + Env, Installer-U-Boot ($UBOOT_INSTALLER_DEFCONFIG), Sonden-U-Boot ($UBOOT_PROBE_DEFCONFIG), sunxi-fel, Kernel + Module, aic8800, Keyring, Sysroot + h713-tv, Rootfs, Eingaben, Abbild $NAME"; exit 0; }

# --- 1. bl31 ---------------------------------------------------------------
if ((SKIP_BL31)) && [[ -f "$OUT/bl31.bin" ]]; then say "1/11 bl31 -- uebersprungen (--skip-bl31, $OUT/bl31.bin vorhanden)"
else
	say "1/11 bl31 (TF-A)"
	# Von vorn bauen. Grund (12.09., P3.9): im Arbeitsbaum lag ein bl31 vom 10.09.,
	# das mit eingeschalteten Zusicherungen gebaut worden war (49260 statt 45164 Byte).
	# make sah alles aktuell und hat es nie ersetzt -- es steckt in v0.8 bis v0.10.
	rm -rf "$MAINLINE/external/arm-trusted-firmware/build"
	im_container "cd $WORK/mainline && build/build.sh bl31" | tail -3 | sed 's/^/    /'
fi
[[ -f "$OUT/bl31.bin" ]] || die "kein bl31.bin"

# --- 2. U-Boot: bauen, trennen, Umgebung ------------------------------------
UB_O="$MAINLINE/build/uboot-release"
if ((SKIP_UBOOT)) && [[ -f "$OUT/spl-release.bin" && -f "$OUT/uboot-proper-release.bin" && -f "$OUT/hy310-env-release.bin" ]]; then
	say "2/11 U-Boot -- uebersprungen (--skip-uboot, Bausteine vorhanden)"
else
	say "2/11 U-Boot $UBOOT_DEFCONFIG"
	rm -rf "$UB_O"   # wie bei bl31: keine alten Objekte, kein altes .config
	im_container "cd $WORK/mainline && build/uboot-build.sh $(c "$UB_O") $UBOOT_DEFCONFIG" > "$OUT/uboot-build.log" 2>&1 || { tail -20 "$OUT/uboot-build.log"; die "U-Boot-Bau gescheitert (Log: $OUT/uboot-build.log)"; }
	B="$UB_O/u-boot-sunxi-with-spl.bin"; [[ -f "$B" ]] || die "kein $B"
	# SPL = die ersten 32 KiB (eGON.BT0), der Rest ist U-Boot proper (doku/50 §Bauen)
	head -c 32768 "$B" > "$OUT/spl-release.bin"
	tail -c +32769 "$B" > "$OUT/uboot-proper-release.bin"
	[[ "$(head -c 12 "$OUT/spl-release.bin" | tail -c 8)" == "eGON.BT0" ]] || die "SPL traegt keine eGON.BT0-Kennung"
	# Die eingebaute Vorgabe-Umgebung als 64-KiB-Abbild mit CRC (doku/60 §Die U-Boot-Umgebung im Abbild).
	# u-boot-initial-env listet bootcmd zweimal (Defconfig + hy310.env, identisch); Dubletten raus.
	im_container "cd $WORK/mainline/external/u-boot && make -s O=$(c "$UB_O") ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu' LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump READELF=llvm-readelf STRIP=llvm-strip u-boot-initial-env" >/dev/null
	awk '!seen[$0]++' "$UB_O/u-boot-initial-env" > "$UB_O/u-boot-initial-env.dedup"
	im_container "$(c "$UB_O")/tools/mkenvimage -s 0x10000 -o $(c "$OUT")/hy310-env-release.bin $(c "$UB_O")/u-boot-initial-env.dedup"
	chmod 0644 "$OUT/hy310-env-release.bin"
	python3 - "$OUT/hy310-env-release.bin" <<'PY'
import sys, zlib, struct
d = open(sys.argv[1], "rb").read(); assert len(d) == 65536, len(d)
assert struct.unpack("<I", d[:4])[0] == zlib.crc32(d[4:]) & 0xffffffff, "CRC"
e = [x.decode() for x in d[4:].split(b"\0") if x and x != b"\xff" * len(x)]
g = [x for x in e if x.startswith("h713_gate=")]; assert g, "h713_gate fehlt"
print("    Umgebung: %d Eintraege, %s" % (len(e), g[0]))
PY
	v=$(strings -n 8 "$OUT/uboot-proper-release.bin" | grep -m1 '^U-Boot 20' || true)
	info "U-Boot $v"
fi
# 2b. Der Installer-U-Boot (FEL -> ums): derselbe Fork, eigene Defconfig. Ohne ihn
#     kann hy310-install aus einem frischen Klon nichts freigeben (P3, 12.09.).
UBI_O="$MAINLINE/build/uboot-installer"
if ((SKIP_UBOOT)) && [[ -f "$OUT/u-boot-installer.bin" ]]; then
	say "2b/11 Installer-U-Boot -- uebersprungen"
else
	say "2b/11 Installer-U-Boot $UBOOT_INSTALLER_DEFCONFIG (ums)"
	rm -rf "$UBI_O"
	im_container "cd $WORK/mainline && build/uboot-build.sh $(c "$UBI_O") $UBOOT_INSTALLER_DEFCONFIG" > "$OUT/uboot-installer-build.log" 2>&1 || { tail -20 "$OUT/uboot-installer-build.log"; die "Installer-U-Boot gescheitert (Log: $OUT/uboot-installer-build.log)"; }
	[[ -f "$UBI_O/u-boot-sunxi-with-spl.bin" ]] || die "kein $UBI_O/u-boot-sunxi-with-spl.bin"
	cp "$UBI_O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-installer.bin"
	grep -q 'ums 0 mmc 1' "$OUT/u-boot-installer.bin" || die "Installer-U-Boot traegt kein 'ums 0 mmc 1' im bootcmd"
fi
# 2b2. Die Sonde (FEL -> h713_probe): fuer H713-Geraete, die wir nicht kennen.
#      Derselbe Fork, eigene Defconfig, DRAM auf 624 statt 792 -- das konservative
#      Ende der Spanne, die unsere beiden bekannten Boards aufspannen (doku/120 §4).
#      Schreibt nichts; gehoert neben u-boot-installer.bin in den Auslieferungsordner.
UBP_O="$MAINLINE/build/uboot-probe"
if ((SKIP_UBOOT)) && [[ -f "$OUT/u-boot-h713-probe.bin" ]]; then
	say "2b2/11 Sonden-U-Boot -- uebersprungen"
else
	say "2b2/11 Sonden-U-Boot $UBOOT_PROBE_DEFCONFIG (h713_probe)"
	rm -rf "$UBP_O"
	im_container "cd $WORK/mainline && build/uboot-build.sh $(c "$UBP_O") $UBOOT_PROBE_DEFCONFIG" > "$OUT/uboot-probe-build.log" 2>&1 || { tail -20 "$OUT/uboot-probe-build.log"; die "Sonden-U-Boot gescheitert (Log: $OUT/uboot-probe-build.log)"; }
	[[ -f "$UBP_O/u-boot-sunxi-with-spl.bin" ]] || die "kein $UBP_O/u-boot-sunxi-with-spl.bin"
	cp "$UBP_O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-h713-probe.bin"
	grep -q 'h713_probe' "$OUT/u-boot-h713-probe.bin" || die "Sonden-U-Boot kennt kein h713_probe"
	# Die Sonde darf nie mit dem Takt dieses Boards ausgeliefert werden: 792 auf
	# fremdem RAM ist genau das Raten, das sie vermeiden soll.
	grep -q 'CONFIG_DRAM_CLK=624' "$MAINLINE/external/u-boot/configs/$UBOOT_PROBE_DEFCONFIG" || die "Sonden-defconfig steht nicht auf 624 MHz"
fi
# 2c. sunxi-fel mit der S44-Falltuer (Fork-Commit 269dfa2): das Werkzeug, mit dem
#     hy310-install das Geraet ueberhaupt erreicht. Wirtsprogramm, im Container gebaut
#     (x86_64, libusb-1.0) -- gehoert spaeter neben hy310-install in den Auslieferungsordner.
if ((SKIP_UBOOT)) && [[ -x "$OUT/sunxi-fel" ]]; then
	say "2c/11 sunxi-fel -- uebersprungen"
else
	say "2c/11 sunxi-fel (Falltuer, Wirtsprogramm)"
	im_container "make -s -C $WORK/mainline/external/sunxi-tools clean >/dev/null 2>&1; make -s -C $WORK/mainline/external/sunxi-tools sunxi-fel" > "$OUT/sunxi-fel-build.log" 2>&1 || { tail -20 "$OUT/sunxi-fel-build.log"; die "sunxi-fel bauen gescheitert (Log: $OUT/sunxi-fel-build.log)"; }
	cp "$MAINLINE/external/sunxi-tools/sunxi-fel" "$OUT/sunxi-fel"
	# (kein grep -q hinter einer Pipe: mit pipefail stirbt strings an SIGPIPE und der Test schlaegt fehl)
	[[ $(strings -n 6 "$OUT/sunxi-fel" | grep -c 'FEL trap door') -gt 0 ]] || die "sunxi-fel ohne Falltuer-Kennung -- falscher Stand?"
fi

# --- 3. Kernel + Module -----------------------------------------------------
if ((SKIP_KERNEL)) && [[ -f "$OUT/h713-kernel.fit" ]]; then say "3/11 Kernel -- uebersprungen (--skip-kernel)"
else
	say "3/11 Kernel (Board-defconfig allein = Auslieferung)"
	im_container "cd $WORK/mainline && build/build.sh kernel" > "$OUT/kernel-build.log" 2>&1 || { tail -20 "$OUT/kernel-build.log"; die "Kernelbau gescheitert (Log: $OUT/kernel-build.log)"; }
	grep -o 'applied [0-9]* series patches' "$OUT/kernel-build.log" | sed 's/^/    /' || true
fi
TREE=$(ls -dt "$MAINLINE"/build/linux-6.18.38-*/ | head -1); TREE=${TREE%/}
[[ -f "$TREE/Module.symvers" ]] || die "kein gebauter Kernelbaum unter $MAINLINE/build/"
H=$(basename "$TREE" | sed 's/linux-6.18.38-//' | cut -c1-8)
MODROOT="$MAINLINE/build/modroot.$H"
if ((SKIP_KERNEL)) && [[ -d "$MODROOT/lib/modules" ]]; then info "Modulbaum $MODROOT vorhanden"
else
	im_container "cd $(c "$TREE") && make -s ARCH=arm64 LLVM=1 INSTALL_MOD_PATH=$(c "$MODROOT") modules_install" >/dev/null
fi
KREL=$(ls "$MODROOT/lib/modules" | head -1)
info "Baum $H, Release $KREL, $(find "$MODROOT" -name '*.ko' | wc -l) Module"

# --- 4. aic8800 (immer nach dem Kernel, gegen denselben Baum) ---------------
say "4/11 aic8800-Module gegen Baum $H"
im_container "cd $WORK/mainline && build/build.sh aic8800" > "$OUT/aic8800-build.log" 2>&1 || { tail -20 "$OUT/aic8800-build.log"; die "aic8800-Bau gescheitert"; }
for k in aic8800_bsp aic8800_fdrv; do [[ -f "$OUT/modules/$k.ko" ]] || die "fehlt: $OUT/modules/$k.ko"; done
info "bsp + fdrv da ($(stat -c %s "$OUT/modules/aic8800_fdrv.ko") Byte fdrv)"

# --- 5. Debian-Keyring, gepinnt --------------------------------------------
say "5/11 Debian-Keyring fuer $DEBIAN_SUITE"
KEYRING_DIR="$MAINLINE/build/cache/keyring"; mkdir -p "$KEYRING_DIR"
KEYRING="$KEYRING_DIR/debian-archive-keyring.pgp"
if [[ ! -f "$KEYRING" ]]; then
	DEB="$MAINLINE/build/cache/$(basename "$KEYRING_DEB_URL")"
	[[ -f "$DEB" ]] || curl -fsSL -o "$DEB" "$KEYRING_DEB_URL"
	echo "$KEYRING_DEB_SHA256  $DEB" | sha256sum -c --quiet - || die "Keyring-Paket: sha256 passt nicht -- nicht benutzen"
	T=$(mktemp -d); ( cd "$T" && ar x "$DEB" && tar -xf data.tar.* "$KEYRING_IN_DEB" ) && cp "$T/$KEYRING_IN_DEB" "$KEYRING"; rm -rf "$T"
fi
info "$(basename "$KEYRING") ($(stat -c %s "$KEYRING") Byte) aus $(basename "$KEYRING_DEB_URL"), sha256 gepinnt"

# --- 6. Sysroot + h713-tv quer ----------------------------------------------
say "6/11 Sysroot (arm64, nur Entwicklungspakete) und h713-tv quer bauen"
SYSROOT="$MAINLINE/build/sysroot-arm64"
if [[ ! -f "$SYSROOT/usr/include/libdrm/drm.h" ]]; then
	rm -rf "$SYSROOT"
	im_container_root "mmdebstrap --mode=unshare --variant=extract --arch=arm64 --skip=check/qemu --keyring=$(c "$KEYRING") --include=$SYSROOT_PAKETE $DEBIAN_SUITE $(c "$SYSROOT") '$DEBIAN_MIRROR'" > "$OUT/sysroot.log" 2>&1 \
		|| im_container_root "mmdebstrap --variant=extract --arch=arm64 --skip=check/qemu --keyring=$(c "$KEYRING") --include=$SYSROOT_PAKETE $DEBIAN_SUITE $(c "$SYSROOT") '$DEBIAN_MIRROR'" >> "$OUT/sysroot.log" 2>&1 \
		|| { tail -20 "$OUT/sysroot.log"; die "Sysroot scheitert (Log: $OUT/sysroot.log)"; }
	# mmdebstrap --variant=extract legt absolute Symlinks an (/usr/lib/... -> /lib/...);
	# clang --sysroot loest die auf dem Host auf. Relativ machen (release/sysroot-fix.py: merged-usr-Links + relative Symlinks).
	im_container_root "python3 $WORK/release/sysroot-fix.py $(c "$SYSROOT")" | sed 's/^/    /'
fi
info "Sysroot $SYSROOT ($(du -sh "$SYSROOT" 2>/dev/null | cut -f1))"
im_container "cd $WORK/userspace/h713-tv && make -s -B cross SYSROOT=$(c "$SYSROOT") CROSS_CC=clang" > "$OUT/h713-tv-cross.log" 2>&1 || { tail -20 "$OUT/h713-tv-cross.log"; die "h713-tv quer bauen gescheitert (Log: $OUT/h713-tv-cross.log)"; }
TV="$USERSPACE/h713-tv/h713-tv.aarch64-linux-gnu"; [[ -f "$TV" ]] || die "kein $TV"
info "h713-tv $(stat -c %s "$TV") Byte, $(file -b "$TV" 2>/dev/null | cut -d, -f1-2)"

# --- 7. Rootfs --------------------------------------------------------------
if ((SKIP_ROOTFS)) && [[ -f "$ROOTFS/out/hy310-rootfs.tar" ]]; then say "7/11 Rootfs -- uebersprungen (--skip-rootfs)"
else
	say "7/11 Rootfs ($DEBIAN_SUITE/arm64, mmdebstrap im Container als root)"
	im_container_root "cd $(c "$ROOTFS") && ./build-rootfs.sh --keyring $(c "$KEYRING") --modroot $(c "$MODROOT") --h713-tv $(c "$TV") ${WIFI_ENV:+--wifi-env $(c "$WIFI_ENV")}" > "$OUT/rootfs-build.log" 2>&1 || { grep -E "Fehler|Abnahme gescheitert|^!!" "$OUT/rootfs-build.log" | tail -8; die "Rootfs-Bau gescheitert (Log: $OUT/rootfs-build.log)"; }
	grep -E "Baumgroesse|wifi.env aus|Abnahme" "$OUT/rootfs-build.log" | sed 's/^/    /' | head -4
fi

# --- 8. ext4-Eingaben -------------------------------------------------------
say "8/11 ext4-Eingaben (hy310-boot 128 MiB, hy310-rootfs 1 GiB mit Platzhaltern)"
# tmp/ vorher als Nutzer anlegen: der Container schreibt darin als root, aber der
# Selbsttest (Schritt 10) legt spaeter probe-b-gefuellt.img daneben -- in einem
# root-eigenen Verzeichnis geht das nicht (P3, 12.09.).
mkdir -p "$INSTALLER/tmp"
im_container_root "FIT=$(c "$OUT")/h713-kernel.fit ROOTFS_OUT=$(c "$ROOTFS")/out bash $(c "$INSTALLER")/mkimage-eingaben.sh" > "$OUT/eingaben.log" 2>&1 || { tail -12 "$OUT/eingaben.log"; die "ext4-Eingaben gescheitert"; }
grep -c "  OK" "$OUT/eingaben.log" | sed 's/^/    OK-Zeilen: /'

# --- 9. Abbild --------------------------------------------------------------
say "9/11 Abbild $NAME"
( cd "$INSTALLER" && python3 hy310-mkimage.py --out "out/$NAME.img" \
	--spl "$OUT/spl-release.bin" --uboot "$OUT/uboot-proper-release.bin" --env "$OUT/hy310-env-release.bin" \
	--boot-ext4 tmp/hy310-boot.ext4 --rootfs-ext4 tmp/hy310-rootfs-platz.ext4 --extraktor "$EXTRAKTOR" ) > "$OUT/mkimage.log" 2>&1 \
	|| { tail -20 "$OUT/mkimage.log"; die "Abbild-Bau gescheitert (Log: $OUT/mkimage.log)"; }
grep -E "Umgebung:|OK   $NAME|Platzhalter fuer|zusammen" "$OUT/mkimage.log" | sed 's/^/    /'

# --- 10. Pruefen ------------------------------------------------------------
say "10/11 Pruefen"
( cd "$INSTALLER" && python3 hy310-mkimage.py --pruefen "out/$NAME.tabelle.json" ) | tail -2 | sed 's/^/    /'
if [[ -n "$VENDOR" ]]; then
	( cd "$INSTALLER" && python3 mkimage-selbsttest.py "out/$NAME.tabelle.json" --vendor "$VENDOR" ) > "$OUT/selbsttest.log" 2>&1 || true
	if grep -q "ALLES GRUEN" "$OUT/selbsttest.log"; then info "Selbsttest mit Vendor-Dateien: ALLES GRUEN"
	else grep -E "FEHL" "$OUT/selbsttest.log" | sed 's/^/    /'; die "Selbsttest nicht gruen (Log: $OUT/selbsttest.log)"; fi
else
	info "kein --vendor: nur Strukturpruefung. Der volle Selbsttest braucht eine h713-extract-Ausgabe."
fi

# --- 11. Stempel ------------------------------------------------------------
say "11/11 Stempel"
STEMPEL="$AUSGABE/$NAME.BUILD.txt"
{
	echo "$NAME  gebaut $(date -u '+%Y-%m-%dT%H:%M:%SZ') in $(dauer)"
	echo "Serie:    $(sha256sum "$MAINLINE/patches/kernel/series" | cut -c1-16)  $(grep -cv '^#\|^$' "$MAINLINE/patches/kernel/series") Patches"
	echo "defconfig: $(sha256sum "$MAINLINE/patches/kernel/board/hy200_qz713df_a1_defconfig" | cut -c1-16)"
	echo "Kernelbaum: $H  Release $KREL"
	for r in u-boot arm-trusted-firmware sunxi-tools; do
		echo "$r: $(git -C "$MAINLINE/external/$r" rev-parse --short HEAD 2>/dev/null)$(git -C "$MAINLINE/external/$r" diff --quiet HEAD 2>/dev/null || echo ' +uncommitted')"
	done
	G_WURZEL=$(git -C "$MAINLINE" rev-parse --show-toplevel 2>/dev/null || true)
	# Kein Verzeichnisname im Stempel: der ist lokal und sagt einem Leser nichts.
	if [[ "$G_WURZEL" == "$MAINLINE" ]]; then W=mainline; else W=repo; fi
	echo "$W: $(git -C "$MAINLINE" rev-parse --short HEAD 2>/dev/null) ($(git -C "$MAINLINE" status --short 2>/dev/null | wc -l) lokale Aenderungen)"
	echo "U-Boot:   $(strings -n 8 "$OUT/uboot-proper-release.bin" | grep -m1 '^U-Boot 20')"
	echo "Bausteine (sha256, 16 Zeichen):"
	for f in spl-release.bin uboot-proper-release.bin hy310-env-release.bin u-boot-installer.bin h713-kernel.fit modules/aic8800_bsp.ko modules/aic8800_fdrv.ko; do
		printf '  %-28s %s\n' "$f" "$(sha256sum "$OUT/$f" | cut -c1-16)"
	done
	printf '  %-28s %s\n' "h713-tv.aarch64-linux-gnu" "$(sha256sum "$TV" | cut -c1-16)"
	printf '  %-28s %s\n' "hy310-rootfs.tar" "$(sha256sum "$ROOTFS/out/hy310-rootfs.tar" | cut -c1-16)"
} > "$STEMPEL"
sed 's/^/    /' "$STEMPEL"
say "fertig: $AUSGABE/$NAME-{a-bootkette,b-system,c-gptkopie}.img + $NAME.tabelle.json  ($(dauer))"
