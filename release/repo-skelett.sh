#!/usr/bin/env bash
# release/repo-skelett.sh -- das neue Repo lokal und wiederholbar aus dem Arbeitsbaum bauen.
#
#   release/repo-skelett.sh [--ziel DIR] [--neu]
#
# Ergebnis: ein Git unter DIR (Vorgabe: <Projekt>/repo-neu) mit
#   Branch legacy  = das alte well0nez/allwinner-h713-linux (master, 110 Commits)
#   Tag legacy-arm32-2026-08 auf dessen Spitze
#   Branch main    = legacy + eine Reihe von Commits, die das Ziel-Layout aus doku/116 §3 aufbauen:
#     1 den arm32-Baum ausraeumen
#     2 mainline/ als git subtree von cstenger/allwinner-h713-mainline@8860991
#     3 unsere Auflage auf mainline/ (Serie, build.sh, defconfig, gles-play, Fork-Pins)
#     4 uboot-h713/ aus dem Fork erzeugt (format-patch)
#     5 installer/ (aus analyse/release/arbeit/r0-fel + r2-extract)
#     6 rootfs/   (aus analyse/release/arbeit/rootfs)
#     7 userspace/ tools/ release/ analyse/{boot,beamer-cam} README.md
#     8 doku/
#     9 .gitignore
#   danach: Sperr-Scan (muss leer sein), build-all --dry-run aus dem Klon, Bericht.
#
# Kein Push. Nichts im Arbeitsbaum wird veraendert; --neu loescht nur DIR (unser Erzeugnis).
# Was draussen bleibt (116 §3): re/, mainline/build/, hy310-sicherung*, tftp/, patches-snapshots/,
# agenten/, legacy/ (-> Branch), analyse/ ausser boot/ und beamer-cam/ und den zwei Umzuegen.
set -euo pipefail

WURZEL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ZIEL="$WURZEL/repo-neu"; NEU=0
while (($#)); do
	case "$1" in
	--ziel) ZIEL=$(readlink -m "${2:?}"); shift 2 ;;
	--neu) NEU=1; shift ;;
	-h|--help) sed -n '2,24p' "$0"; exit 0 ;;
	*) echo "unbekannt: $1" >&2; exit 2 ;;
	esac
done

# Feste Staende (doku/116 §4a P1/P2, 115 §2). Wer sie aendert, aendert sie hier.
CSTENGER_MAINLINE=8860991
UBOOT_BASIS=8fe568cdfc4              # cstenger/u-boot h713 -- darauf sitzen unsere 33
UBOOT_KOPF=4091ea68c06               # unser Fork-Stand (Zweig h713-hy310 = h713-display)
TFA_KOPF=3b3fb35fa40b097eafc75528170de62f8130cff9
SUNXI_TOOLS_KOPF=269dfa22fcbbe5ced352c337495ba8dd0bbf82e6
UBOOT_KOPF_LANG=4091ea68c0620c590ad9af583c074a6bab463dad
LEGACY_TAG=legacy-arm32-2026-08

MAINLINE="$WURZEL/mainline"; ARBEIT="$WURZEL/analyse/release/arbeit"
LOG="$ARBEIT/logs/repo-skelett-$(date +%Y%m%d-%H%M).txt"; mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1
T0=$(date +%s)
say() { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }
die() { printf 'FEHLER: %s\n' "$*" >&2; exit 1; }
G() { git -C "$ZIEL" "$@"; }
commit() { # commit "Betreff" "Text..."
	G add -A . >/dev/null
	G -c commit.gpgsign=false commit -q --allow-empty -m "$1" -m "$2" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
	info "commit $(G rev-parse --short HEAD)  $1  ($(G diff --shortstat HEAD~1 HEAD | sed 's/^ //'))"
}

say "0 Voraussetzungen"
[[ -d "$WURZEL/legacy/.git" ]] || die "legacy/ ist kein Klon"
[[ "$(git -C "$MAINLINE" rev-parse --short HEAD)" == "$CSTENGER_MAINLINE" ]] || die "mainline/ steht nicht auf $CSTENGER_MAINLINE"
for paar in "u-boot:$UBOOT_KOPF" "arm-trusted-firmware:$TFA_KOPF" "sunxi-tools:$SUNXI_TOOLS_KOPF"; do
	r=${paar%%:*}; c=${paar#*:}
	git -C "$MAINLINE/external/$r" cat-file -e "$c^{commit}" 2>/dev/null || die "$r: Commit $c fehlt im Checkout"
	[[ "$(git -C "$MAINLINE/external/$r" rev-parse HEAD)" == "$(git -C "$MAINLINE/external/$r" rev-parse "$c")" ]] || info "Hinweis: $r-Checkout steht nicht auf $c (Pin bleibt $c)"
done
git -C "$MAINLINE/external/u-boot" merge-base --is-ancestor "$UBOOT_BASIS" "$UBOOT_KOPF" || die "U-Boot: $UBOOT_BASIS ist kein Vorfahr von $UBOOT_KOPF"
git subtree -h >/dev/null 2>&1 || [[ "$(git subtree 2>&1 | head -1)" == *prefix* ]] || die "git subtree fehlt"
command -v rsync >/dev/null || die "rsync fehlt"
[[ -n "$(git config user.name)" && -n "$(git config user.email)" ]] || die "git user.name/user.email nicht gesetzt"
if [[ -e "$ZIEL" ]]; then
	((NEU)) || die "$ZIEL existiert -- mit --neu wegwerfen und neu bauen"
	[[ -d "$ZIEL/.git" && "$ZIEL" == "$WURZEL"/* ]] || die "$ZIEL loesche ich nicht (kein Git unter $WURZEL)"
	# Nach einem Bau im Klon gehoeren Teile dem Container-root (uid 100000); die raeumt nur
	# podman unshare weg. Erst normal versuchen, damit ohne Podman nichts fehlt.
	rm -rf "$ZIEL" 2>/dev/null || { command -v podman >/dev/null && podman unshare rm -rf "$ZIEL"; }
	[[ -e "$ZIEL" ]] && die "$ZIEL liess sich nicht loeschen"
fi
info "Ziel $ZIEL, Log $LOG"

say "1 legacy: das alte Repo als Branch und Tag"
git init -q -b main "$ZIEL"
G fetch -q "$WURZEL/legacy" "master:legacy" "refs/tags/*:refs/tags/*"
G tag -a "$LEGACY_TAG" legacy -m "The arm32 (5.4 BSP) era of this repo, frozen before the arm64 overhaul.

Everything after this point is the mainline kernel 6.18 line built on
cstenger/allwinner-h713-mainline; see doku/116-plan-release-repo.md."
info "legacy = $(G rev-parse --short legacy) ($(G rev-list --count legacy) Commits), Tag $LEGACY_TAG, alte Tags: $(G tag | grep -v "$LEGACY_TAG" | tr '\n' ' ')"

say "2 main: den arm32-Baum ausraeumen"
G checkout -q -B main legacy
G rm -rq .
commit "tree: retire the arm32 layout" "The old tree lives on as branch 'legacy' and tag '$LEGACY_TAG'.
From here on the repo is the arm64 / mainline-6.18 project: kernel patches on
top of cstenger's tree, our U-Boot fork, the installer, the rootfs recipe and
the userspace tools. Layout and phases: doku/116-plan-release-repo.md."

say "3 mainline/: subtree von cstenger @$CSTENGER_MAINLINE"
G subtree add -q --prefix=mainline "$MAINLINE" main -m "mainline: import cstenger/allwinner-h713-mainline@$CSTENGER_MAINLINE as a subtree

Full history, no squash: the provenance of every patch we build on stays
readable with git log. Submodule pins are cstenger's for now; the next commit
moves them to our forks."
info "subtree $(G rev-parse --short HEAD); $(G ls-files mainline | wc -l) Dateien"
# Vor der Auflage: was cstengers Stand in .gitmodules pinnt
G ls-tree HEAD mainline/external/ | sed 's/^/   pin vorher: /'

say "4 mainline/: unsere Auflage"
rsync -a --delete \
	--exclude=.git --exclude=/build/ --exclude=/external/ --exclude=/patches-snapshots/ --exclude=/local/ \
	--exclude='*.orig' --exclude='*.rej' --exclude='*.body' --exclude=__pycache__/ \
	"$MAINLINE/" "$ZIEL/mainline/"
# build/: nur die zwei Skripte, keine Bauausgaben
mkdir -p "$ZIEL/mainline/build"
cp -a "$MAINLINE/build/build.sh" "$MAINLINE/build/uboot-build.sh" "$ZIEL/mainline/build/"
# Fork-Pins als Gitlinks (die Checkouts selbst sind nicht Teil des Repos)
for paar in "u-boot:$UBOOT_KOPF_LANG" "arm-trusted-firmware:$TFA_KOPF" "sunxi-tools:$SUNXI_TOOLS_KOPF"; do
	G update-index --add --cacheinfo "160000,${paar#*:},mainline/external/${paar%%:*}"
	mkdir -p "$ZIEL/mainline/external/${paar%%:*}"
done
# .gitmodules an der Wurzel: git liest nur die oberste; mainline/.gitmodules (cstengers) bleibt
# als Subtree-Inhalt liegen, wirkt aber nicht. Relative URLs wie bei cstenger -- unter
# well0nez/allwinner-h713-linux zeigen sie auf well0nez/{u-boot,arm-trusted-firmware,sunxi-tools}.
cat > "$ZIEL/.gitmodules" <<'EOF'
[submodule "mainline/external/arm-trusted-firmware"]
	path = mainline/external/arm-trusted-firmware
	url = ../arm-trusted-firmware.git
	branch = sun50i-h713
[submodule "mainline/external/sunxi-tools"]
	path = mainline/external/sunxi-tools
	url = ../sunxi-tools.git
	branch = h713
[submodule "mainline/external/u-boot"]
	path = mainline/external/u-boot
	url = ../u-boot.git
	branch = h713-hy310
EOF
# Beweis: die Serie im Ziel ist byteidentisch zur Arbeitskopie
diff -rq --exclude='*.orig' --exclude='*.rej' --exclude='*.body' --exclude=__pycache__ "$MAINLINE/patches" "$ZIEL/mainline/patches" >/dev/null || die "mainline/patches weicht ab"
cmp -s "$MAINLINE/build/build.sh" "$ZIEL/mainline/build/build.sh" || die "build.sh weicht ab"
commit "mainline: our kernel series, build.sh section support, fork pins" "patches/kernel: cstenger's 46 + the display branch's 16 + ours (0049, 0091-0158) plus
the P1 follow-ups 0014a/0024a/0024b/0024c/0078a placed right after their originals;
series carries section comments, build.sh skips '#' and blank lines.
patches/aic8800: series + 0007 (power line from the device tree).
board/: hy200_qz713df_a1_defconfig (no DEBUG_FS/DYNAMIC_DEBUG in the release),
debug.config and netboot.config fragments.
tools/video/gles-play.c, patches/kernel/README.md, zurueckgenommen/, vorschlaege/.
external/: u-boot -> well0nez $UBOOT_KOPF (branch h713-hy310, unpublished until P7),
arm-trusted-firmware -> well0nez ${TFA_KOPF:0:11} (sun50i-h713),
sunxi-tools -> well0nez ${SUNXI_TOOLS_KOPF:0:11} (h713, FEL trap door).
.gitmodules at the root repeats cstenger's three entries with the mainline/ prefix and
relative URLs (git only reads the top-level file); mainline/.gitmodules stays as subtree
content. u-boot's branch is h713-hy310 until P7 merges it into the fork's default branch."
G ls-tree HEAD mainline/external/ | sed 's/^/   pin nachher: /'
info "Serie: $(grep -cv '^#\|^$' "$ZIEL/mainline/patches/kernel/series") Patches, $(G ls-files mainline/patches | wc -l) Dateien unter mainline/patches"

say "5 uboot-h713/: aus dem Fork erzeugt ($UBOOT_BASIS..$UBOOT_KOPF)"
mkdir -p "$ZIEL/uboot-h713"
git -C "$MAINLINE/external/u-boot" format-patch -q -o "$ZIEL/uboot-h713" --no-signature "$UBOOT_BASIS..$UBOOT_KOPF"
n=$(ls "$ZIEL/uboot-h713"/*.patch | wc -l)
cp -a "$WURZEL/uboot-h713/README.md" "$ZIEL/uboot-h713/README.md"
{
	echo "# Generated -- do not edit."
	echo "# release/repo-skelett.sh: git format-patch $UBOOT_BASIS..$UBOOT_KOPF in mainline/external/u-boot"
	echo "base   $(git -C "$MAINLINE/external/u-boot" rev-parse "$UBOOT_BASIS")  (cstenger/u-boot, branch h713)"
	echo "head   $(git -C "$MAINLINE/external/u-boot" rev-parse "$UBOOT_KOPF")  (well0nez/u-boot, branch h713-hy310)"
	echo "count  $n"
} > "$ZIEL/uboot-h713/SERIES.txt"
# Vergleich mit den bisher von Hand gepflegten 33 (nur Hinweis)
# (Zuordnung ueber den Betreff -- die Handnummerierung weicht bei 0017/0018 ab; Signatur und index-Zeilen zaehlen nicht)
alt_n=$(ls "$WURZEL/uboot-h713"/*.patch 2>/dev/null | wc -l); gleich=0
rumpf() { sed -e '1,/^$/d' -e '/^-- $/,$d' "$1" | grep -v '^index '; }
for p in "$ZIEL/uboot-h713"/*.patch; do
	betreff=$(grep -m1 '^Subject:' "$p" | sed 's/^Subject: \[PATCH[^]]*\] //')
	alt=$(grep -l -F -m1 "] $betreff" "$WURZEL/uboot-h713"/*.patch 2>/dev/null | head -1); [[ -n "$alt" ]] || continue
	diff -q <(rumpf "$p") <(rumpf "$alt") >/dev/null && gleich=$((gleich+1))
done
info "$n Patches erzeugt; bisher von Hand: $alt_n, davon $gleich mit gleichem Inhalt"
commit "uboot-h713: $n patches generated from the fork" "git format-patch $UBOOT_BASIS..$UBOOT_KOPF in mainline/external/u-boot, written by
release/repo-skelett.sh. Read-only mirror of the fork for people who do not want to
clone it; the build uses the submodule pin. The old hand-copied configs/ and drivers/
snapshots from 2026-08-31 are gone -- the patches carry the same files."

say "6 installer/"
mkdir -p "$ZIEL/installer"
for f in hy310-install.py hy310-mkimage.py mkimage-selbsttest.py mkimage-eingaben.sh installer-fahren.py metadata-leer-16m.ext4.gz; do
	cp -a "$ARBEIT/r0-fel/$f" "$ZIEL/installer/"
done
cp -a "$ARBEIT/r2-extract/h713-extract" "$ZIEL/installer/"
# Die deutsche Langfassung r2-extract/README.md bleibt draussen (Marco, 12.09.): zwei
# Beschreibungen desselben Werkzeugs nebeneinander verwirren mehr, als sie helfen.
# Englisch steht sie in docs/tools/h713-extract.md.
commit "installer: hy310-install, hy310-mkimage, h713-extract and their helpers" "Moved from analyse/release/arbeit/{r0-fel,r2-extract}. hy310-install (FEL -> ums ->
dump -> placeholders -> env carry-over -> write -> verify), hy310-mkimage (image
layout v3: bootchain / hole 12288-14335 / system / GPT copy), mkimage-selbsttest,
mkimage-eingaben.sh, installer-fahren.py (pty driver for the JA prompt),
h713-extract (vendor blobs from the user's own firmware, with hashes and report; documented in
docs/tools/h713-extract.md, its German long form stays in the working tree),
metadata-leer-16m.ext4.gz (the empty metadata filesystem Android needs).
The FEL research (s44-*, probes, readbacks) stays behind in analyse/."

say "7 rootfs/"
rsync -a --exclude='/out/' --exclude='/out.*/' --exclude='/wifi.env' --exclude=__pycache__/ "$ARBEIT/rootfs/" "$ZIEL/rootfs/"
[[ -f "$ZIEL/rootfs/overlay/etc/h713/wifi.env" ]] || die "rootfs: die oeffentliche Vorgabe overlay/etc/h713/wifi.env fehlt"
grep -q '^ssid=h713$' "$ZIEL/rootfs/overlay/etc/h713/wifi.env" || die "rootfs: overlay/etc/h713/wifi.env ist nicht die oeffentliche Vorgabe (ssid=h713)"
commit "rootfs: Debian trixie/arm64 recipe, overlay, project install, tests" "Moved from analyse/release/arbeit/rootfs. build-rootfs.sh (mmdebstrap minbase, pinned
keyring, regulatory.db -> upstream, acceptance tests), install-projekt.sh (kernel modules,
aic8800 into extra/, h713-tv/-focus/-cam/-pq), packages.txt, overlay/ (h713-wifi,
wifi.env public default, fw_env.config 0x700000, systemd units), tests/h713-wifi-check.sh.
A personal rootfs/wifi.env next to the script overrides the public default and is ignored."

say "8 userspace/ tools/ release/ analyse/{boot,beamer-cam} docs/ + Wurzeldateien"
rsync -a --exclude='*.aarch64-linux-gnu' --exclude='*.aarch64-linux-gnu.*' --exclude='/hy310-tv.vor-audio-*' \
	--exclude='/hy310-tv' --exclude='/hy310-pq' --exclude=__pycache__/ --exclude='*.o' "$WURZEL/userspace/" "$ZIEL/userspace/"
rsync -a --exclude=__pycache__/ --exclude='*.bak-*' "$WURZEL/tools/" "$ZIEL/tools/"
rsync -a --exclude=__pycache__/ --exclude='/logs/' "$WURZEL/release/" "$ZIEL/release/"
mkdir -p "$ZIEL/analyse"
rsync -a --exclude=__pycache__/ "$WURZEL/analyse/boot/" "$ZIEL/analyse/boot/"
rsync -a --exclude=__pycache__/ "$WURZEL/analyse/beamer-cam/" "$ZIEL/analyse/beamer-cam/"
for f in README.md STATUS.md FLASHING.md BUILDING.md PROVENANCE.md ROADMAP.md RELEASES.md LICENSE LICENSE.docs; do cp -a "$WURZEL/$f" "$ZIEL/$f"; done
rsync -a --exclude=__pycache__/ "$WURZEL/docs/" "$ZIEL/docs/"
commit "userspace, tools, release, analyse/{boot,beamer-cam}, docs" "userspace/: h713-tv (C, the HDMI input as a service), h713-pq, h713-focus, h713-cam --
sources only, the cross-built binaries come out of release/build-all.sh.
tools/: UART helpers, regdiff, MIPS/OR1K disassembly aids (from the old tree, unchanged).
release/: build-all.sh (fresh clone -> image), sysroot-fix.py, sperr-scan.py, repo-skelett.sh.
analyse/boot: boot logs and acceptance records; analyse/beamer-cam: camera findings.
docs/ plus README, STATUS, FLASHING, BUILDING, PROVENANCE: the English documentation (P5).
The rest of analyse/ is not exported (116 §3): it gets rewritten into the English docs."

say "9 doku/"
rsync -a --exclude=__pycache__/ "$WURZEL/doku/" "$ZIEL/doku/"
commit "doku: the German working journal" "Unchanged. English documentation for users comes in P5 (docs/, README, FLASHING,
BUILDING); doku/ stays the record of how we got here."

say "10 .gitignore"
cat > "$ZIEL/.gitignore" <<'EOF'
# Build output -- everything under mainline/build except the two scripts
mainline/build/*
!mainline/build/build.sh
!mainline/build/uboot-build.sh
mainline/patches-snapshots/
# Installer / rootfs output and run logs
installer/out/
installer/logs/
installer/tmp/
installer/sunxi-fel
installer/u-boot-sunxi-with-spl.bin
rootfs/out/
rootfs/out.*/
# A personal WLAN file next to build-rootfs.sh (the public default lives in overlay/)
rootfs/wifi.env
# Cross-built binaries (release/build-all.sh)
userspace/h713-tv/h713-tv
userspace/h713-tv/*.aarch64-linux-gnu
userspace/h713-tv/*.aarch64-linux-gnu.*
# Never: images, dumps, keys, vendor blobs (release/sperr-scan.py enforces this before a push)
*.img
*.ext4
*.simg
*.fex
*.bundle
hy310-sicherung*/
re/
__pycache__/
*.pyc
*.orig
*.rej
EOF
# .gitignore auf den bestehenden Baum anwenden -- gezielt, damit die drei Gitlinks bleiben
G ls-files -z -i -c --exclude-standard > "$ZIEL/.ignoriert.z"
if [[ -s "$ZIEL/.ignoriert.z" ]]; then
	tr '\0' '\n' < "$ZIEL/.ignoriert.z" | sed 's/^/   austragen: /'
	G rm -q --cached --pathspec-from-file="$ZIEL/.ignoriert.z" --pathspec-file-nul
fi
rm -f "$ZIEL/.ignoriert.z"
commit "gitignore: build output, dumps, images, personal files" "What must never land in the repo is listed twice: here for git, and in
release/sperr-scan.py for the human check before every push."

say "11 Sperr-Scan"
python3 "$WURZEL/release/sperr-scan.py" "$ZIEL" --extraktor "$ARBEIT/r2-extract/h713-extract" || die "Sperr-Scan hat Funde -- nicht weiter"

say "12a Submodule aus den lokalen Checkouts (Platzhalter, bis P7 die Forks erreichbar macht)"
# Relative URLs zeigen von einem lokalen Klon aus ins Leere; darum hier die Checkouts des
# Arbeitsbaums als Quelle. Die Pins muessen dort als Commits vorliegen (Schritt 0 prueft das).
for r in u-boot arm-trusted-firmware sunxi-tools; do
	G config "submodule.mainline/external/$r.url" "$MAINLINE/external/$r"
done
G -c protocol.file.allow=always submodule update --init -q -- mainline/external/u-boot mainline/external/arm-trusted-firmware mainline/external/sunxi-tools
G submodule status | sed 's/^/   /'
[[ -f "$ZIEL/mainline/external/u-boot/Makefile" && -f "$ZIEL/mainline/external/sunxi-tools/fel.c" ]] || die "Submodule nicht befuellt"

say "12b Kernel-Tarball aus dem Arbeitsbaum vorlegen (spart 147 MB Download)"
# build/cache/ ist gitignored und keine Repo-Inhalt; build.sh prueft den sha256 selbst.
T="$MAINLINE/build/cache"
vor=0
for f in "$T"/linux-*.tar.xz "$T"/aic8800-*.tar.gz "$T"/debian-archive-keyring_*.deb; do
	[[ -f "$f" ]] || continue
	mkdir -p "$ZIEL/mainline/build/cache"; cp --update=none "$f" "$ZIEL/mainline/build/cache/"; vor=$((vor+1))
done
((vor)) && info "$vor Datei(en): $(ls "$ZIEL/mainline/build/cache" | tr '\n' ' ')" || info "nichts im Arbeitsbaum -- der erste Bau im Klon laedt alles"

say "12 build-all --dry-run aus dem Klon"
( cd "$ZIEL" && release/build-all.sh --version v0.0-beta --dry-run ) 2>&1 | sed 's/^/   /' || die "build-all --dry-run aus $ZIEL gescheitert"

say "13 Bericht"
info "Branches/Tags:"; G branch --format='   %(refname:short) %(objectname:short) %(subject)' ; G tag | sed 's/^/   tag /'
info "main (first-parent; der Subtree bringt cstengers Historie als zweiten Elternstrang mit):"; G log --oneline --first-parent legacy..main | sed 's/^/   /'
info "Dateien: $(G ls-files | wc -l) (mainline $(G ls-files mainline | wc -l), doku $(G ls-files doku | wc -l), installer $(G ls-files installer | wc -l), rootfs $(G ls-files rootfs | wc -l), userspace $(G ls-files userspace | wc -l), tools $(G ls-files tools | wc -l))"
info "Groesse: .git $(du -sh --exclude=modules "$ZIEL/.git" | cut -f1) (ohne Submodule), Arbeitsbaum $(du -sh --exclude=.git --exclude=external "$ZIEL" | cut -f1) (ohne external/)"
info "Grosse Dateien (>1 MB) im Baum:"; find "$ZIEL" \( -path "$ZIEL/.git" -o -path "$ZIEL/mainline/external" \) -prune -o -type f -size +1M -printf '   %s %P\n' | sort -rn | head -10
info "Diff gegen legacy: $(G diff --shortstat legacy main | sed 's/^ //')"
info "Aus legacy uebernommen (gleicher Pfad, gleicher Inhalt): $(comm -12 <(G ls-tree -r legacy --name-only | sort) <(G ls-tree -r main --name-only | sort) | while read -r f; do [[ "$(G rev-parse "legacy:$f")" == "$(G rev-parse "main:$f")" ]] && echo "$f"; done | wc -l) Dateien"
info "Fertig in $(( $(date +%s) - T0 )) s. Kein Push."
info "Voller Beweis aus dem Klon: cd $ZIEL && release/build-all.sh --version v0.0-beta --vendor <h713-extract-Ausgabe>"
