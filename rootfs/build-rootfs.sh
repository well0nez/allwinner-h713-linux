#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
#
# build-rootfs.sh -- das schlanke Rootfs fuer HY310 v0.1 bauen.
#
# Vorgabe: doku/107-plan-rootfs.md. Ziel-Layout: doku/109-plan-layout-v3.md §2.2
# (eine Partition hy310-rootfs, 7,15 GiB, /data ist ein Verzeichnis darin).
#
# Ergebnis (in --out):
#   hy310-rootfs.tar          der Baum, den der Installer nach hy310-rootfs
#                             entpackt und der zugleich als NFS-Wurzel dient
#                             (109 §4.2: ein Bau, zwei Ziele)
#   hy310-rootfs.ext4         dasselbe als ext4-Abbild (optional, --image-size)
#   hy310-rootfs.manifest     was drin ist, mit welchen Quellen gebaut
#   ROOTFS-SHA256SUMS         Pruefsummen
#
# ============================================================================
# WO DAS LAEUFT
# ============================================================================
# Im Container h713-build (Projektregel: kein Bau auf dem Host):
#
#     podman exec -u root h713-build \
#         /work/analyse/release/arbeit/rootfs/build-rootfs.sh --out /work/...
#
# Das Projekt ist dort als /work gemountet. Das Skript findet seinen
# Projektbaum selbst ueber den eigenen Pfad, es braucht kein --project-root.
#
# ============================================================================
# WAS DIESES SKRIPT BEWUSST *NICHT* TUT -- Abgrenzung zu
# mainline/tools/rootfs/build.sh (cstenger)
# ============================================================================
#  * Kein VIDEO_RUNTIME_PACKAGES. Dort ist die GStreamer/Mesa/GTK-Kette Teil
#    des Grundsystems ("this is a projector"). Fuer uns ist sie der groesste
#    Einzelposten des heutigen Netboot-Roots (107 §1: libllvm19 118 MiB,
#    mesa-libgallium 33 MiB, libgtk-3-common 30 MiB ...) und ohne Funktion:
#    h713-tv schiebt den HDMI-Eingang auf eine DRM-Plane und decodiert nichts.
#  * Kein --profile dev, kein build-essential, keine -dev-Pakete. Gebaut wird
#    quer (107 §3).
#  * KEIN --ssh-key als Pflichtargument. Dort ist der Schluessel verlangt und
#    wird ins Abbild kopiert; fuer ein Release muss er vom Nutzer kommen, also
#    vom Installer (107 §3). --authorized-key gibt es hier nur als Wahl fuer
#    eigene Bauten, nicht als Pflicht.
#  * WLAN ist drin (seit 12.09.: Treiber als Module, Pakete, h713-wifi mit
#    /etc/h713/wifi.env), aber KEINE Firmware-Blobs im Abbild (107 §5) -- die
#    aic8800-Firmware kommt wie alles Proprietaere vom Installer aus
#    h713-extract, aus dem Abzug des Nutzers. Bluetooth bleibt draussen: seine
#    Firmware liegt nicht im Abzug.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Ort und Vorgaben
# ---------------------------------------------------------------------------
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Projektwurzel: das naechste Elternverzeichnis mit mainline/build/build.sh -- so
# funktioniert das Skript im Arbeitsverzeichnis (analyse/release/arbeit/...) wie im
# Release-Repo (rootfs/ bzw. installer/ direkt unter der Wurzel), doku/116 P3.
projekt_wurzel() { local d=$1; while [ "$d" != / ]; do [ -f "$d/mainline/build/build.sh" ] && { echo "$d"; return; }; d=$(dirname "$d"); done; return 1; }
# analyse/release/arbeit/rootfs -> vier Ebenen hoch ist der Projektbaum
PROJECT_ROOT=$(projekt_wurzel "$HERE") || { echo "Projektwurzel (mainline/build/build.sh) oberhalb von $HERE nicht gefunden" >&2; exit 1; }

SUITE=trixie
ARCH=arm64
MIRROR=http://deb.debian.org/debian
OUT_DIR="$HERE/out"
IMAGE_SIZE=1G
MAKE_EXT4=1
DRY_RUN=0
SKIP_PROJEKT=0
AUTHORIZED_KEY=
KEEP_WORK=0
KEYRING=
# WLAN: /etc/h713/wifi.env im Abbild. Reihenfolge: --wifi-env DATEI, sonst
# rootfs/wifi.env neben diesem Skript (lokal, nicht fuer git), sonst die
# Vorgabe aus dem Overlay (AP h713/magcubic -- oeffentlich bekannt).
WIFI_ENV=

# Projektteile (Abschnitt 4 des Auftrags) -- Vorgaben, per Schalter aenderbar
MODROOT="$PROJECT_ROOT/mainline/build/modroot.GUT-bad2f16b"
H713_TV_SRC="$PROJECT_ROOT/userspace/h713-tv"
H713_TV_BIN="$H713_TV_SRC/h713-tv.aarch64-linux-gnu"
H713_PQ_SRC="$PROJECT_ROOT/userspace/h713-pq"

usage() {
	cat <<EOF
Aufruf: ${0##*/} [Optionen]

Baut Debian $SUITE/$ARCH mit mmdebstrap --variant=minbase, legt overlay/
darueber und spielt die Projektteile ein (h713-tv, Kernelmodule, h713-pq).

  --out DIR             Ausgabeverzeichnis (Vorgabe: $OUT_DIR)
  --suite NAME          Debian-Suite (Vorgabe: $SUITE)
  --arch ARCH           Architektur (Vorgabe: $ARCH)
  --mirror URL          Spiegel (Vorgabe: $MIRROR)
  --keyring DATEI       Keyring fuer die Signaturpruefung. NOETIG im Container
                        h713-build: dessen debian-archive-keyring (2023.4)
                        hoert bei bookworm auf und kennt trixie nicht.
  --image-size GROESSE  Groesse des ext4-Abbilds (Vorgabe: $IMAGE_SIZE).
                        Klein bauen ist Absicht: die fstab traegt
                        x-systemd.growfs, das Abbild waechst beim ersten
                        Start auf die volle Partition (7,15 GiB).
  --no-ext4             nur das tar erzeugen
  --modroot DIR         Kernelmodul-Baum (Vorgabe: ${MODROOT#"$PROJECT_ROOT"/})
  --h713-tv DATEI      quer gebautes h713-tv (Vorgabe:
                        ${H713_TV_BIN#"$PROJECT_ROOT"/})
  --authorized-key FILE optional einen SSH-Schluessel einbauen. NICHT die
                        Vorgabe und nicht der Release-Weg (107 §3).
  --wifi-env DATEI      eigene /etc/h713/wifi.env (mode=ap|sta|off, ssid,
                        password, channel, ...). Ohne Schalter: rootfs/wifi.env,
                        falls vorhanden, sonst die Vorgabe aus dem Overlay --
                        Zugangspunkt h713 / magcubic, und die kennt jeder.
                        Wird vor dem Bau mit 'h713-wifi check' geprueft.
  --skip-projekt        nur das Debian-Grundsystem + overlay/
  --keep-work           Arbeitsverzeichnis nicht loeschen
  --dry-run             nichts bauen, nichts schreiben, nichts aus dem Netz
                        holen -- nur zeigen, was geschehen wuerde. Laeuft
                        auch ohne mmdebstrap durch.
  -h, --help            diese Hilfe
EOF
}

while (($#)); do
	case "$1" in
	--out)             OUT_DIR=${2:?fehlender Wert fuer --out}; shift 2 ;;
	--keyring)         KEYRING=${2:?fehlender Wert fuer --keyring}; shift 2 ;;
	--suite)           SUITE=${2:?fehlender Wert fuer --suite}; shift 2 ;;
	--arch)            ARCH=${2:?fehlender Wert fuer --arch}; shift 2 ;;
	--mirror)          MIRROR=${2:?fehlender Wert fuer --mirror}; shift 2 ;;
	--image-size)      IMAGE_SIZE=${2:?fehlender Wert fuer --image-size}; shift 2 ;;
	--no-ext4)         MAKE_EXT4=0; shift ;;
	--modroot)         MODROOT=${2:?fehlender Wert fuer --modroot}; shift 2 ;;
	--h713-tv)        H713_TV_BIN=${2:?fehlender Wert fuer --h713-tv}; shift 2 ;;
	--authorized-key)  AUTHORIZED_KEY=${2:?fehlender Wert fuer --authorized-key}; shift 2 ;;
	--wifi-env)        WIFI_ENV=${2:?fehlender Wert fuer --wifi-env}; shift 2 ;;
	--skip-projekt)    SKIP_PROJEKT=1; shift ;;
	--keep-work)       KEEP_WORK=1; shift ;;
	--dry-run)         DRY_RUN=1; shift ;;
	-h|--help)         usage; exit 0 ;;
	*) echo "Fehler: unbekanntes Argument: $1" >&2; usage >&2; exit 2 ;;
	esac
done

OVERLAY="$HERE/overlay"
PACKAGES_FILE="$HERE/packages.txt"
PROJEKT_SCRIPT="$HERE/install-projekt.sh"

# wifi.env aufloesen. Die Pruefung macht dasselbe Skript, das auf dem Geraet
# laeuft -- was hier durchgeht, geht dort durch, und umgekehrt.
WIFI_CHECK="$OVERLAY/usr/local/sbin/h713-wifi"
WIFI_ENV_HERKUNFT=
if [[ -n "$WIFI_ENV" ]]; then
	WIFI_ENV_HERKUNFT="--wifi-env"
elif [[ -f "$HERE/wifi.env" ]]; then
	WIFI_ENV="$HERE/wifi.env"; WIFI_ENV_HERKUNFT="rootfs/wifi.env"
else
	WIFI_ENV="$OVERLAY/etc/h713/wifi.env"; WIFI_ENV_HERKUNFT="Vorgabe aus dem Overlay"
fi
WIFI_IST_VORGABE=0
[[ "$WIFI_ENV" -ef "$OVERLAY/etc/h713/wifi.env" ]] && WIFI_IST_VORGABE=1

say()  { printf '==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Werkzeugpruefung -- soll SAGEN, was fehlt, nicht nur scheitern
# ---------------------------------------------------------------------------
# Die Zuordnung Werkzeug -> Debian/Ubuntu-Paket steht hier, damit die Meldung
# den Befehl nennt, mit dem man weiterkommt. Stand 10.09.2026 fehlt im
# Container h713-build (ubuntu:24.04) genau mmdebstrap.
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
# Nur fuer den ext4-Schritt gebraucht
EXT4_TOOLS=(mke2fs e2fsck)
# Nur fuer den Fremdarchitektur-Bootstrap
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

	# Fremdarchitektur: die Wartungsskripte der arm64-Pakete laufen unter
	# qemu-user. Es gibt zwei Wege, auf denen das klappt, und der zweite ist
	# der, den wir hier tatsaechlich benutzen:
	#   a) qemu-user-static IM Container installiert;
	#   b) das binfmt_misc des HOSTS ist mit Flag F registriert -- dann liegt
	#      der Interpreter bereits im Kernel und der Pfad im Container ist
	#      egal. Im Container ist /proc/sys/fs/binfmt_misc dann gar nicht
	#      sichtbar, ein Blick dorthin waere also ein falsches Negativ.
	# Deshalb wird nicht nach Dateien gesucht, sondern GEMESSEN: arch-test
	# (kommt mit mmdebstrap) fuehrt ein winziges Testprogramm der Zielarch
	# wirklich aus.
	local fw_ok=1 fw_wie=
	local host_arch; host_arch=$(dpkg --print-architecture 2>/dev/null || echo unbekannt)
	if [[ "$ARCH" != "$host_arch" ]]; then
		if command -v arch-test >/dev/null 2>&1 && arch-test "$ARCH" >/dev/null 2>&1; then
			fw_wie="arch-test $ARCH: ok"
		elif [[ -x /usr/bin/qemu-${ARCH/arm64/aarch64}-static ]]; then
			fw_wie="qemu-user-static im Container"
		elif [[ -r /proc/sys/fs/binfmt_misc/qemu-${ARCH/arm64/aarch64} ]]; then
			fw_wie="binfmt_misc sichtbar"
		else
			fw_ok=0
		fi
	else
		fw_wie="native"
	fi

	if ((${#missing[@]} == 0)) && ((fw_ok == 1)); then
		info "Werkzeuge vollstaendig ($host_arch -> $ARCH: $fw_wie)"
		return 0
	fi

	warn "es fehlen Werkzeuge:"
	((${#missing[@]})) && printf '    fehlend: %s\n' "${missing[*]}" >&2
	((fw_ok == 0)) && printf '    fehlend: Ausfuehrung von %s-Programmen (qemu-user-static oder binfmt des Hosts)\n' "$ARCH" >&2

	# Das Rezept gehoert nach doku/50-befehle.md.
	((${#pkgs[@]})) || pkgs=()
	local pkglist
	pkglist=$( ((${#pkgs[@]})) && printf '%s\n' "${pkgs[@]}" | sort -u | tr '\n' ' ' )
	cat >&2 <<EOF

    Im Container nachinstallieren (das gehoert ins Rezept in doku/50-befehle.md):

        podman exec -u root h713-build apt-get update
        podman exec -u root h713-build env DEBIAN_FRONTEND=noninteractive \\
            apt-get install -y mmdebstrap debian-archive-keyring

    mmdebstrap zieht fakeroot, fakechroot, arch-test und gpg mit.
    debian-archive-keyring liefert /usr/share/keyrings/debian-archive-keyring.gpg
    -- ohne das kann mmdebstrap die Debian-Signaturen nicht pruefen.

    NUR falls oben "Ausfuehrung von $ARCH-Programmen" fehlt, zusaetzlich:

        podman exec -u root h713-build env DEBIAN_FRONTEND=noninteractive \\
            apt-get install -y qemu-user-static

    (Auf diesem Host nicht noetig: sein binfmt_misc registriert qemu-aarch64
     mit Flag F, der Interpreter ist also schon im Kernel geladen und gilt
     auch im Container. Gepruefte Meldung: "arch-test arm64: ok".)
${pkglist:+
    Fehlende Pakete laut Werkzeugpruefung: $pkglist}
EOF
	return 1
}

# Das Keyring, mit dem mmdebstrap die Debian-Quelle prueft. Ohne Keyring gibt
# es hier KEINEN unsignierten Notweg -- lieber abbrechen als ein Abbild aus
# ungeprueften Paketen bauen.
#
# ACHTUNG, die Falle, die 40 Minuten kosten kann: der Container h713-build ist
# ubuntu:24.04, und dessen `debian-archive-keyring` ist Fassung 2023.4 -- die
# hoert bei **bookworm (12)** auf. Der Schluessel fuer **trixie (13)** ist
# nicht drin, und mmdebstrap scheitert dann erst beim Holen des Release-Files
# mit einer Meldung ueber eine ungueltige Signatur. Deshalb wird hier nicht
# nur geprueft, OB ein Keyring da ist, sondern ob er die Suite auch KENNT.
#
# Drei Wege, in dieser Reihenfolge:
#   1. --keyring DATEI (ausdrueckliche Angabe)
#   2. ein Keyring im Container, der den Suite-Schluessel traegt
#   3. der Keyring eines vorhandenen trixie-Baums, z. B. der heutigen
#      NFS-Wurzel: /srv/h713-rootfs/usr/share/keyrings/debian-archive-keyring.gpg
#      (traegt "Debian Archive Automatic Signing Key (13/trixie)"; der
#      Container sieht /srv nicht, die Datei muss also nach /work kopiert
#      werden -- siehe --keyring)
KEYRING_CANDIDATES=(
	/usr/share/keyrings/debian-archive-keyring.gpg
	/usr/share/keyrings/debian-archive-keyring.pgp
	/etc/apt/trusted.gpg.d/debian-archive-keyring.gpg
)

# Kennt dieser Keyring die Suite? Sucht eine uid, die den Suite-Namen nennt
# ("... (13/trixie) ..."). Ohne gpg wird nicht geraten, sondern durchgelassen
# -- dann faellt es spaeter auf, aber wir behaupten nichts Falsches.
keyring_kennt_suite() {
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
	# erst einen, der die Suite kennt
	for k in "${KEYRING_CANDIDATES[@]}"; do
		[[ -r "$k" ]] && keyring_kennt_suite "$k" && { printf '%s\n' "$k"; return 0; }
	done
	# sonst irgendeinen (der Aufrufer meldet dann die Luecke)
	for k in "${KEYRING_CANDIDATES[@]}"; do
		[[ -r "$k" ]] && { printf '%s\n' "$k"; return 0; }
	done
	return 1
}

keyring_pruefen() {
	local k=$1
	if keyring_kennt_suite "$k"; then
		info "Keyring: $k (kennt $SUITE)"
		return 0
	fi
	warn "Keyring $k kennt die Suite '$SUITE' NICHT."
	cat >&2 <<EOF
    Der Container ubuntu:24.04 liefert debian-archive-keyring 2023.4; die
    hoert bei bookworm (12) auf. Ohne den trixie-Schluessel scheitert
    mmdebstrap beim Release-File -- erst nach dem halben Bootstrap.

    Weg heraus (einer davon):
      a) einen aktuellen Keyring in den Container bringen und
             $0 --keyring /pfad/zum/debian-archive-keyring.gpg
      b) den Keyring aus einem vorhandenen trixie-Baum nehmen. Auf diesem
         Host liegt einer in der heutigen NFS-Wurzel:
             /srv/h713-rootfs/usr/share/keyrings/debian-archive-keyring.gpg
         Der Container sieht /srv nicht -- also einmal nach /work kopieren:
             install -D -m 0644 \\
               /srv/h713-rootfs/usr/share/keyrings/debian-archive-keyring.gpg \\
               $OUT_DIR/keyring/debian-archive-keyring.gpg
         und dann --keyring $OUT_DIR/keyring/debian-archive-keyring.gpg
      c) --suite bookworm bauen (NICHT gewollt: das heutige Root ist
         trixie 13.6, 107 §5)
EOF
	return 1
}

# ---------------------------------------------------------------------------
# 2. Paketliste einlesen
# ---------------------------------------------------------------------------
read_packages() {
	[[ -r "$PACKAGES_FILE" ]] || die "packages.txt nicht lesbar: $PACKAGES_FILE"
	# Kommentare und Leerzeilen weg, erstes Wort der Zeile ist der Paketname
	sed -e 's/#.*//' -e 's/[[:space:]]\+/ /g' -e 's/^ //' -e 's/ $//' \
		"$PACKAGES_FILE" | awk 'NF { print $1 }'
}

# ---------------------------------------------------------------------------
# 3. Trockenlauf
# ---------------------------------------------------------------------------
mmdebstrap_argv() {
	# Als Array ausgeben (eine Zeile je Argument), damit der Trockenlauf
	# genau das zeigt, was der scharfe Lauf ausfuehrt.
	local mode=unshare
	((EUID == 0)) && mode=root
	local keyring; keyring=$(find_keyring || echo "<KEYRING-FEHLT>")
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
		'<ausgabe>.tar' \
		"deb $MIRROR $SUITE main"
}

dry_run() {
	say "Trockenlauf -- es wird nichts geschrieben und nichts aus dem Netz geholt"
	echo
	info "Projektbaum:   $PROJECT_ROOT"
	info "Ausgabe waere: $OUT_DIR"
	info "Suite/Arch:    $SUITE/$ARCH ueber $MIRROR"
	info "ext4-Abbild:   $( ((MAKE_EXT4)) && echo "ja, $IMAGE_SIZE (waechst per x-systemd.growfs)" || echo nein )"
	echo

	say "1. Werkzeugpruefung"
	check_tools || true
	echo

	say "2. Paketliste ($PACKAGES_FILE)"
	local n; n=$(read_packages | wc -l)
	read_packages | sed 's/^/    /'
	info "-- $n Pakete ueber minbase hinaus"
	echo

	say "3. Bootstrap-Aufruf (so wuerde er lauten)"
	mmdebstrap_argv | sed -e '1s/^/    /' -e '2,$s/^/        /'
	echo

	say "4. Overlay ($OVERLAY) -- diese Dateien werden darueber gelegt"
	if [[ -d "$OVERLAY" ]]; then
		(cd "$OVERLAY" && find . -mindepth 1 \( -type f -o -type l \) -printf '    /%P\n' | sort)
		(cd "$OVERLAY" && find . -mindepth 1 -type d -empty -printf '    /%P/  (leeres Verzeichnis)\n' | sort)
	else
		warn "overlay/ fehlt: $OVERLAY"
	fi
	echo

	say "5. WLAN ($WIFI_ENV_HERKUNFT: $WIFI_ENV)"
	if sh "$WIFI_CHECK" check "$WIFI_ENV" 2>&1 | sed 's/^/    /'; then
		info "-> /etc/h713/wifi.env (0600), h713-wifi.service in multi-user.target.wants"
	fi
	echo

	say "6. Nacharbeit am Baum"
	cat <<'EOF'
    - /etc/machine-id leeren  (sonst haetten alle Geraete dieselbe ID)
    - /etc/ssh/ssh_host_* loeschen -> hy310-ssh-host-keys.service erzeugt sie
      beim ersten Start neu (sonst: gleiche Host-Schluessel auf jedem Geraet)
    - Root-Passwort gesperrt lassen/setzen ("*"); herein kommt man ueber den
      Autologin auf ttyS0, per ssh nur mit Schluessel vom Installer
    - Units verlinken: serial-getty@ttyS0, hy310-zram-swap, hy310-ssh-host-keys,
      h713-hdcp-key, h713-wifi
    - /data und /etc/h713/tvconfig anlegen (tvconfig bleibt LEER)
    - /var/lib/apt/lists und /var/cache/apt leeren (107 §8: kein apt update
      beim Bau -- 40 MiB Listen, am ersten Tag veraltet)
EOF
	echo

	say "7. Projektteile"
	if ((SKIP_PROJEKT)); then
		info "uebersprungen (--skip-projekt)"
	elif [[ -x "$PROJEKT_SCRIPT" ]]; then
		MODROOT="$MODROOT" H713_TV_SRC="$H713_TV_SRC" \
		H713_TV_BIN="$H713_TV_BIN" H713_PQ_SRC="$H713_PQ_SRC" \
			"$PROJEKT_SCRIPT" --dry-run "<baum>" || true
	else
		warn "install-projekt.sh fehlt oder ist nicht ausfuehrbar: $PROJEKT_SCRIPT"
	fi
	echo

	say "8. Ausgabe"
	info "$OUT_DIR/hy310-rootfs.tar"
	((MAKE_EXT4)) && info "$OUT_DIR/hy310-rootfs.ext4  ($IMAGE_SIZE)"
	info "$OUT_DIR/hy310-rootfs.manifest"
	info "$OUT_DIR/ROOTFS-SHA256SUMS"
	echo
	say "Trockenlauf beendet. Nichts geschrieben."
}

if ((DRY_RUN)); then
	dry_run
	exit 0
fi

# ===========================================================================
# Scharfer Lauf
# ===========================================================================
say "HY310-Rootfs bauen -- $SUITE/$ARCH"
check_tools || die "Werkzeuge fehlen (siehe oben). Mit --dry-run laeuft es trotzdem durch."
KEYRING=$(find_keyring) || die "kein Debian-Keyring gefunden. apt-get install debian-archive-keyring"
keyring_pruefen "$KEYRING" || die "Keyring passt nicht zur Suite (siehe oben)"

[[ -d "$OVERLAY" ]] || die "overlay/ fehlt: $OVERLAY"

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/hy310-rootfs.XXXXXX")
cleanup() { ((KEEP_WORK)) || rm -rf -- "$WORK"; }
trap cleanup EXIT

TREE="$WORK/tree"
BOOTSTRAP_TAR="$WORK/bootstrap.tar"

# --- 1. Bootstrap ----------------------------------------------------------
say "0/6 wifi.env pruefen ($WIFI_ENV_HERKUNFT)"
sh "$WIFI_CHECK" check "$WIFI_ENV" | sed 's/^/    /' || die "wifi.env nicht brauchbar: $WIFI_ENV"
if ((WIFI_IST_VORGABE)); then
	warn "Dieses Abbild spannt den Zugangspunkt 'h713' mit dem Passwort 'magcubic' auf."
	warn "Das steht so in der Doku und im Repo. Eigene Fassung: --wifi-env DATEI"
	warn "oder rootfs/wifi.env -- oder auf dem Geraet /etc/h713/wifi.env aendern."
fi

say "1/6 mmdebstrap --variant=minbase"
mapfile -t MMARGV < <(mmdebstrap_argv)
# das Platzhalter-Argument '<ausgabe>.tar' durch den echten Pfad ersetzen
for i in "${!MMARGV[@]}"; do
	[[ "${MMARGV[$i]}" == '<ausgabe>.tar' ]] && MMARGV[$i]=$BOOTSTRAP_TAR
done
"${MMARGV[@]}"
[[ -s "$BOOTSTRAP_TAR" ]] || die "mmdebstrap hat kein tar geliefert"
info "Bootstrap-tar: $(du -h "$BOOTSTRAP_TAR" | cut -f1)"

# --- 2. Auspacken ----------------------------------------------------------
say "2/6 auspacken"
mkdir -p "$TREE"
# ./dev/* wird ausgelassen: im rootless Container darf tar kein mknod, und
# gebraucht wird es nicht -- der Kernel mountet devtmpfs auf /dev, bevor init
# laeuft (CONFIG_DEVTMPFS_MOUNT=y in unserem Defconfig). Das finale tar
# schliesst ./dev/* ohnehin aus (Schritt 6).
tar --numeric-owner --xattrs --acls --exclude='./dev/*' -C "$TREE" -xf "$BOOTSTRAP_TAR"
rm -f "$BOOTSTRAP_TAR"
[[ -d "$TREE/etc" && -d "$TREE/usr" ]] || die "Baum sieht nicht wie ein Rootfs aus"

# --- 3. Overlay ------------------------------------------------------------
say "3/6 Overlay legen"
# -a erhaelt Rechte und Symlinks; das Overlay ist bewusst root:root, deshalb
# danach ein chown auf 0:0 (falls als Nutzer gebaut wurde, s. --mode=unshare).
# --exclude: ein __pycache__ entsteht, sobald jemand ein Skript aus dem
# Overlay von Hand startet, und waere sonst im Abbild gelandet (11.09.2026).
tar -C "$OVERLAY" --exclude=__pycache__ --exclude="*.pyc" -cf - . |
	tar -C "$TREE" --no-same-owner -xf -
(cd "$OVERLAY" && find . -mindepth 1 \( -type f -o -type l \) -printf '%P\n') | \
	while read -r rel; do
		chown 0:0 "$TREE/$rel" 2>/dev/null || true
	done
info "$(cd "$OVERLAY" && find . -mindepth 1 \( -type f -o -type l \) | wc -l) Dateien aus overlay/"
# wifi.env: die gewaehlte Fassung, 0600 root -- sie traegt ein Passwort.
install -m 0600 -o 0 -g 0 "$WIFI_ENV" "$TREE/etc/h713/wifi.env" 2>/dev/null || \
	{ install -m 0600 "$WIFI_ENV" "$TREE/etc/h713/wifi.env"; chown 0:0 "$TREE/etc/h713/wifi.env" 2>/dev/null || true; }
info "/etc/h713/wifi.env aus $WIFI_ENV_HERKUNFT"

# --- 4. Nacharbeit ---------------------------------------------------------
say "4/6 Nacharbeit"

# 4a. Verzeichnisse, die es geben MUSS. /etc/h713/tvconfig liegt zwar auch
# im Overlay, aber ein leeres Verzeichnis ueberlebt kein git -- deshalb hier
# noch einmal ausdruecklich. Es bleibt LEER: die PQ-Daten spielt der
# Installer aus h713-extract ein (107 §8, 108 §6).
install -d -m 0755 "$TREE/etc/h713" "$TREE/etc/h713/tvconfig"
# /data: alles Wachsende (Mitschnitte, Aufnahmen, optionale Logs) -- seit
# Layout v3 ein Verzeichnis im Rootfs, keine eigene Partition (109 §2.2).
install -d -m 0755 "$TREE/data"
install -d -m 0755 "$TREE/boot"

# 4b. Maschinen-Identitaet: leer heisst "beim ersten Start erzeugen".
: > "$TREE/etc/machine-id"
rm -f "$TREE/var/lib/dbus/machine-id"

# 4c. SSH-Host-Schluessel: das Postinst hat sie IM CHROOT erzeugt, also
# beim Bau. Weg damit, sonst haben alle Geraete dieselben.
rm -f "$TREE"/etc/ssh/ssh_host_*
info "Host-Schluessel entfernt (hy310-ssh-host-keys.service erzeugt sie neu)"

# 4d. Root-Passwort gesperrt. Der Weg herein ist der Autologin auf ttyS0;
# per ssh nur mit Schluessel, und der kommt vom Installer (107 §3).
if [[ -f "$TREE/etc/shadow" ]]; then
	sed -i 's/^root:[^:]*:/root:*:/' "$TREE/etc/shadow"
	root_hash=$(awk -F: '$1=="root"{print $2}' "$TREE/etc/shadow")
	[[ "$root_hash" == '*' ]] || die "Root-Passwort nicht gesperrt (Feld: '$root_hash')"
	info "Root-Passwort gesperrt ('*')"
fi

# 4e. Optionaler Schluessel -- ausdruecklich NICHT der Release-Weg.
if [[ -n "$AUTHORIZED_KEY" ]]; then
	[[ -s "$AUTHORIZED_KEY" ]] || die "Schluesseldatei leer/fehlt: $AUTHORIZED_KEY"
	install -d -m 0700 "$TREE/root/.ssh"
	install -m 0600 "$AUTHORIZED_KEY" "$TREE/root/.ssh/authorized_keys"
	warn "--authorized-key: dieses Abbild traegt einen fest eingebauten"
	warn "Schluessel. Fuer ein Release ist das der falsche Weg (107 §3)."
fi

# 4f. Units verlinken. Ohne laufendes systemd im Chroot: von Hand, so wie es
# `systemctl enable` auch tun wuerde.
link_unit() { # $1 = Ziel-Unit-Datei (im Baum absolut), $2 = wants-Verzeichnis, $3 = Name
	install -d "$TREE/$2"
	ln -sfn "$1" "$TREE/$2/$3"
}
link_unit /usr/lib/systemd/system/serial-getty@.service \
	etc/systemd/system/getty.target.wants serial-getty@ttyS0.service
link_unit /etc/systemd/system/hy310-zram-swap.service \
	etc/systemd/system/swap.target.wants hy310-zram-swap.service
link_unit /etc/systemd/system/hy310-ssh-host-keys.service \
	etc/systemd/system/ssh.service.wants hy310-ssh-host-keys.service
# h713-hdcp-key MUSS verlinkt sein: modprobe.d sperrt den Autoload des
# hdmirx-Treibers, damit die Init-Sequenz nicht ohne HDCP-Schluessel laeuft.
# Ohne diese Zeile laedt ihn niemand -- das Geraet bliebe ohne Bild.
link_unit /etc/systemd/system/h713-hdcp-key.service \
	etc/systemd/system/sysinit.target.wants h713-hdcp-key.service
# h713-wifi: liest /etc/h713/wifi.env und faehrt AP, Station oder nichts hoch.
# Die Paket-Units hostapd/wpa_supplicant sind im Overlay maskiert (-> /dev/null).
link_unit /etc/systemd/system/h713-wifi.service \
	etc/systemd/system/multi-user.target.wants h713-wifi.service
info "Units verlinkt: serial-getty@ttyS0, hy310-zram-swap, hy310-ssh-host-keys, h713-hdcp-key, h713-wifi"

# 4g. resolv.conf muss eine echte Datei sein, kein Symlink auf
# systemd-resolved -- den Dienst gibt es hier nicht, isc-dhcp-client schreibt
# selbst hinein (S41 §1: so laeuft es heute).
rm -f "$TREE/etc/resolv.conf"
: > "$TREE/etc/resolv.conf"
chmod 0644 "$TREE/etc/resolv.conf"

# 4h. apt: Quellen ja, Listen nein (107 §8).
rm -f "$TREE/etc/apt/sources.list"
rm -rf "$TREE"/var/lib/apt/lists/* "$TREE"/var/cache/apt/archives/*.deb
install -d "$TREE/var/lib/apt/lists/partial"
info "apt-Quellen eingetragen, Paketlisten NICHT eingebacken"

# 4i. Journal-Verzeichnis nicht anlegen: existiert /var/log/journal, schaltet
# journald trotz Storage=volatile auf persistent um. Das ist genau der
# Fallstrick, den 107 §4.1 vermeiden will.
rm -rf "$TREE/var/log/journal"

# 4j. regulatory.db: wireless-regdb liefert zwei signierte Kopien und zeigt per
# Alternative (Prioritaet 100 gegen 50) auf die Debian-signierte. Unser Kernel
# ist Mainline und traegt nur die Upstream-Zertifikate (net/wireless/certs:
# sforshee, wens) bei CFG80211_REQUIRE_SIGNED_REGDB=y -- die Debian-Signatur
# kann er nicht pruefen und wuerde die Datenbank ablehnen. Also auf -upstream
# zeigen. Fuer den aic8800 (self-managed wiphy, default_ccode) ist das ohne
# Folgen; fuer das globale Reich von cfg80211 ist es der Unterschied zwischen
# "geladen" und "verworfen". (cstengers Befund, mainline/tools/rootfs/customize.sh.)
# Ohne chroot: die Alternative ist nur ein Symlink unter /etc/alternatives.
for alt in regulatory.db regulatory.db.p7s; do
	if [[ -e "$TREE/lib/firmware/$alt-upstream" && -L "$TREE/etc/alternatives/$alt" ]]; then
		ln -sfn "/lib/firmware/$alt-upstream" "$TREE/etc/alternatives/$alt"
	fi
done
info "regulatory.db -> upstream-signiert (Kernel kennt nur sforshee/wens)"

# --- 5. Projektteile -------------------------------------------------------
if ((SKIP_PROJEKT)); then
	say "5/6 Projektteile uebersprungen (--skip-projekt)"
else
	say "5/6 Projektteile"
	[[ -x "$PROJEKT_SCRIPT" ]] || die "install-projekt.sh fehlt: $PROJEKT_SCRIPT"
	MODROOT="$MODROOT" H713_TV_SRC="$H713_TV_SRC" \
	H713_TV_BIN="$H713_TV_BIN" H713_PQ_SRC="$H713_PQ_SRC" \
		"$PROJEKT_SCRIPT" "$TREE"
fi

# --- 6. Abnahme, tar, ext4 -------------------------------------------------
say "6/6 Abnahme und Ausgabe"

# Die Pruefungen, die scheitern DUERFEN -- lieber kein Abbild als ein falsches.
t() { # t "Was" test-ausdruck...
	local what=$1; shift
	if "$@"; then info "✓ $what"; else die "Abnahme gescheitert: $what"; fi
}
t "systemd als Init"          test -x "$TREE/usr/lib/systemd/systemd"
t "agetty vorhanden"          test -x "$TREE/sbin/agetty"
t "Autologin-Drop-in"         test -f "$TREE/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf"
t "serial-getty verlinkt"     test -L "$TREE/etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service"
t "journald volatile"         grep -qx 'Storage=volatile' "$TREE/etc/systemd/journald.conf.d/10-hy310.conf"
t "kein /var/log/journal"     test ! -d "$TREE/var/log/journal"
t "fstab: PARTLABEL-Wurzel"   grep -q '^PARTLABEL=hy310-rootfs' "$TREE/etc/fstab"
t "fstab: PARTLABEL-Boot"     grep -q '^PARTLABEL=hy310-boot' "$TREE/etc/fstab"
t "fstab: keine dritte Zeile" test "$(grep -c '^PARTLABEL=' "$TREE/etc/fstab")" = 2
t "fw_env auf 0x700000"       grep -q '^/dev/mmcblk0[[:space:]]*0x700000[[:space:]]*0x10000' "$TREE/etc/fw_env.config"
t "fw_printenv vorhanden"     test -x "$TREE/usr/bin/fw_printenv"
t "Netz per ifupdown/DHCP"    grep -q 'iface eth0 inet dhcp' "$TREE/etc/network/interfaces"
t "hy310-logs ausfuehrbar"    test -x "$TREE/usr/local/sbin/hy310-logs"
t "zram-Unit verlinkt"        test -L "$TREE/etc/systemd/system/swap.target.wants/hy310-zram-swap.service"
t "HDCP-Unit verlinkt"       test -L "$TREE/etc/systemd/system/sysinit.target.wants/h713-hdcp-key.service"
t "hdmirx-Autoload gesperrt" test -f "$TREE/etc/modprobe.d/h713-hdcp-key.conf"
t "swappiness=180"            grep -q 'vm.swappiness *= *180' "$TREE/etc/sysctl.d/99-hy310-zram.conf"
t "tvconfig leer"             test -z "$(ls -A "$TREE/etc/h713/tvconfig")"
t "/data vorhanden"           test -d "$TREE/data"
t "keine Host-Schluessel"     test -z "$(find "$TREE/etc/ssh" -maxdepth 1 -name 'ssh_host_*' -print -quit)"
t "keine apt-Listen"          test -z "$(find "$TREE/var/lib/apt/lists" -maxdepth 1 -type f -print -quit)"
t "apt-Quelle signiert"       grep -q '^Signed-By:' "$TREE/etc/apt/sources.list.d/debian.sources"
# Kommentarzeilen ausnehmen: die eigene sources-Datei erwaehnt trusted=yes
# in ihrer Begruendung, und eine Abnahme, die ueber den eigenen Kommentar
# stolpert, prueft nichts.
t "kein trusted=yes"          bash -c "! grep -rhv '^[[:space:]]*#' '$TREE/etc/apt' 2>/dev/null | grep -q 'trusted=yes'"
t "kein Compiler"             test ! -e "$TREE/usr/bin/gcc"
t "kein GStreamer"            test ! -e "$TREE/usr/bin/gst-launch-1.0"
# WLAN ist seit dem 12.09. drin (Marco). Bis dahin stand hier "kein
# wpa_supplicant" -- der Satz ist umgedreht, nicht geloescht.
t "wpa_supplicant vorhanden"  test -x "$TREE/usr/sbin/wpa_supplicant"
t "hostapd vorhanden"         test -x "$TREE/usr/sbin/hostapd"
t "dnsmasq vorhanden"         test -x "$TREE/usr/sbin/dnsmasq"
t "kein dnsmasq.service"      test ! -e "$TREE/lib/systemd/system/dnsmasq.service"
t "hostapd.service maskiert"  test "$(readlink "$TREE/etc/systemd/system/hostapd.service")" = /dev/null
t "wpa_supplicant maskiert"   test "$(readlink "$TREE/etc/systemd/system/wpa_supplicant.service")" = /dev/null
t "wifi.env 0600"             test "$(stat -c %a "$TREE/etc/h713/wifi.env")" = 600
t "wifi.env brauchbar"        sh "$TREE/usr/local/sbin/h713-wifi" check "$TREE/etc/h713/wifi.env"
t "h713-wifi verlinkt"        test -L "$TREE/etc/systemd/system/multi-user.target.wants/h713-wifi.service"
t "aic8800 leise"             grep -q 'aicwf_dbg_level=0x1' "$TREE/etc/modprobe.d/aic8800.conf"
t "regulatory.db upstream"    test "$(readlink "$TREE/etc/alternatives/regulatory.db")" = /lib/firmware/regulatory.db-upstream

TREE_KIB=$(du -sxk "$TREE" | cut -f1)
info "Baumgroesse: $((TREE_KIB / 1024)) MiB ($TREE_KIB KiB, du -sx)"
if ((TREE_KIB > 500 * 1024)); then
	warn "ueber der Abnahmegrenze aus 107 §7.1 (500 MiB)"
fi

say "tar schreiben"
TAR_OUT="$OUT_DIR/hy310-rootfs.tar"
tar --numeric-owner --xattrs --acls --sort=name \
	--exclude=./dev/* -C "$TREE" -cf "$TAR_OUT" .
info "$TAR_OUT ($(du -h "$TAR_OUT" | cut -f1))"

if ((MAKE_EXT4)); then
	say "ext4-Abbild schreiben ($IMAGE_SIZE)"
	EXT4_OUT="$OUT_DIR/hy310-rootfs.ext4"
	rm -f "$EXT4_OUT"
	truncate -s "$IMAGE_SIZE" "$EXT4_OUT"
	# -L hy310-rootfs: dasselbe Etikett wie die Partition, damit blkid und
	# e2label dasselbe sagen. -m 1: 1 % Reserve reicht, das ist keine
	# Systemplatte mit /var-Fuellstand-Problem.
	mke2fs -q -F -t ext4 -L hy310-rootfs -m 1 \
		-E lazy_itable_init=0,lazy_journal_init=0 \
		-d "$TREE" "$EXT4_OUT"
	e2fsck -fn "$EXT4_OUT" >/dev/null
	info "$EXT4_OUT ($(du -h "$EXT4_OUT" | cut -f1)) -- waechst beim ersten Start (x-systemd.growfs)"
fi

say "Manifest"
MANIFEST="$OUT_DIR/hy310-rootfs.manifest"
{
	echo "suite=$SUITE"
	echo "arch=$ARCH"
	echo "mirror=$MIRROR"
	echo "keyring=$KEYRING"
	echo "gebaut=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
	echo "baumgroesse_kib=$TREE_KIB"
	echo "pakete_ueber_minbase=$(read_packages | paste -sd,)"
	echo "installiert=$(chroot_count=$(grep -c '^Package: ' "$TREE/var/lib/dpkg/status" 2>/dev/null || echo 0); echo "$chroot_count")"
	echo "modroot=${MODROOT#"$PROJECT_ROOT"/}"
	echo "h713_tv=${H713_TV_BIN#"$PROJECT_ROOT"/}"
	echo "ssh_key_eingebaut=$( [[ -n "$AUTHORIZED_KEY" ]] && echo ja || echo nein )"
	echo "image_size=$( ((MAKE_EXT4)) && echo "$IMAGE_SIZE" || echo keins )"
} > "$MANIFEST"
cat "$MANIFEST" | sed 's/^/    /'

(
	cd "$OUT_DIR"
	# shellcheck disable=SC2012
	sha256sum hy310-rootfs.tar hy310-rootfs.manifest \
		$( ((MAKE_EXT4)) && echo hy310-rootfs.ext4 ) > ROOTFS-SHA256SUMS
)
say "fertig"
ls -lh "$OUT_DIR"
