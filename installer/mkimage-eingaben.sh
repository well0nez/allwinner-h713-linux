#!/bin/bash
# mkimage-eingaben.sh -- die beiden ext4-Dateisysteme fuer hy310-mkimage bauen.
#
# WARUM ES DIESES SKRIPT GIBT
# hy310-mkimage.py laeuft unter Linux und Windows mit reiner Standardbibliothek
# und ohne externe Programme. Ein ext4 SELBST ZU ERZEUGEN waere der einzige
# Schritt, der das brechen wuerde -- also passiert er hier, bei uns, einmal, im
# Container h713-build mit e2fsprogs. Herauskommen zwei gewoehnliche Dateien,
# und die sind ab da nur noch Bausteine wie die SPL oder das U-Boot-Abbild.
# Beim Nutzer laeuft das hier nie.
#
#   tmp/hy310-boot.ext4          128 MiB: h713-kernel.fit (echt) + mips/ (19 Platzhalter)
#   tmp/hy310-rootfs-platz.ext4    1 GiB: das Rootfs aus rootfs/out/hy310-rootfs.tar,
#                                         erweitert um 11 Platzhalter (Firmware + PQ)
#                                         und /root/.ssh/authorized_keys (4096 B
#                                         Zeilenumbrueche, fuellt hy310-install)
#
# Aufruf IM CONTAINER -- ALS ROOT:
#   podman exec -u root h713-build bash /work/analyse/release/arbeit/r0-fel/mkimage-eingaben.sh
#
# Warum root: tar kann nur als root den Besitzer setzen, und mke2fs -d nimmt
# uid/gid/Modus aus dem Baum. Als Nutzer 1000 ausgepackt gehoerte im ext4
# ALLES uid 1000 -- /etc/shadow, /root, authorized_keys --, sshd nimmt dann
# keinen Schluessel (StrictModes) und setgid-Bits (unix_chkpwd) fehlen. So
# war es im Abbild v0.5 (11.09.2026). build-rootfs.sh laeuft aus demselben
# Grund mit -u root; hy310-mkimage prueft den Besitz im fertigen ext4 nach.
#
# WURZEL/TMP/ROOTFS_OUT/FIT lassen sich per Umgebung ueberschreiben (Tests aus
# einer Kopie heraus).
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
# Projektwurzel: das naechste Elternverzeichnis mit mainline/build/build.sh -- so
# funktioniert das Skript im Arbeitsverzeichnis (analyse/release/arbeit/...) wie im
# Release-Repo (rootfs/ bzw. installer/ direkt unter der Wurzel), doku/116 P3.
projekt_wurzel() { local d=$1; while [ "$d" != / ]; do [ -f "$d/mainline/build/build.sh" ] && { echo "$d"; return; }; d=$(dirname "$d"); done; return 1; }
WURZEL=${WURZEL:-$(projekt_wurzel "$HIER")} || { echo "Projektwurzel oberhalb von $HIER nicht gefunden" >&2; exit 1; }
TMP=${TMP:-$HIER/tmp}
# Beide Layouts (Release-Repo: rootfs/ unter der Wurzel; Arbeitsverzeichnis: analyse/...).
if [ -d "$WURZEL/rootfs/out" ] || [ -f "$WURZEL/rootfs/build-rootfs.sh" ]; then
	ROOTFS_OUT=${ROOTFS_OUT:-$WURZEL/rootfs/out}
else
	ROOTFS_OUT=${ROOTFS_OUT:-$WURZEL/analyse/release/arbeit/rootfs/out}
fi
# Der FIT kommt aus dem Bau (release/build-all.sh), nicht mehr aus tftp/ (12.09.).
FIT=${FIT:-$WURZEL/mainline/build/out/h713-kernel.fit}

if [ "$(id -u)" != 0 ]; then
	echo "als root ausfuehren: podman exec -u root h713-build bash $0" >&2
	echo "(sonst gehoert im ext4 jede Datei uid $(id -u) statt root)" >&2
	exit 1
fi

say() { printf '\n=== %s\n' "$*"; }
ok()  { printf '  OK   %s\n' "$*"; }

for w in mke2fs e2fsck python3 tar; do
	command -v "$w" >/dev/null || { echo "fehlt: $w (im Container h713-build ausfuehren)" >&2; exit 1; }
done
[ -f "$FIT" ] || { echo "Kernel-FIT nicht gefunden: $FIT" >&2; exit 1; }
[ -f "$ROOTFS_OUT/hy310-rootfs.tar" ] || { echo "hy310-rootfs.tar fehlt" >&2; exit 1; }

mkdir -p "$TMP"
rm -rf "$TMP/boot-baum" "$TMP/rootfs-baum"

# --- 1. hy310-boot -------------------------------------------------------
say "hy310-boot.ext4 (128 MiB)"
mkdir -p "$TMP/boot-baum"
python3 "$HIER/hy310-mkimage.py" --baum-boot "$TMP/boot-baum" --fit "$FIT"
rm -f "$TMP/hy310-boot.ext4"
truncate -s $((262144 * 512)) "$TMP/hy310-boot.ext4"
# Dieselben Optionen, mit denen p5 am Geraet angelegt wurde (r1-installer
# do_mkfs: -m 1), plus lazy_*_init=0, damit die Datei vollstaendig ist und
# nicht erst beim ersten Einhaengen fertig geschrieben wird.
mke2fs -q -F -t ext4 -L hy310-boot -m 1 \
	-E lazy_itable_init=0,lazy_journal_init=0 \
	-d "$TMP/boot-baum" "$TMP/hy310-boot.ext4"
e2fsck -fn "$TMP/hy310-boot.ext4" >/dev/null
ok "$TMP/hy310-boot.ext4"

# --- 2. hy310-rootfs mit Platzhaltern ------------------------------------
say "hy310-rootfs-platz.ext4 (1 GiB)"
mkdir -p "$TMP/rootfs-baum"
# Das abgenommene Rootfs (doku/107 §9) kommt aus dem tar, nicht aus dem
# fertigen ext4: die elf Platzhalter muessen als richtige Dateien mit
# richtiger Groesse angelegt werden, und das kann mke2fs -d in einem Zug.
# --numeric-owner: die uid/gid aus dem tar, nicht ueber Namen der Container-
# Nutzerdatenbank aufgeloest (0/0, 0/42 ...). Danach eine Stichprobe, bevor
# mke2fs den Baum einbackt.
tar --numeric-owner --xattrs --acls -xf "$ROOTFS_OUT/hy310-rootfs.tar" -C "$TMP/rootfs-baum"
python3 "$HIER/hy310-mkimage.py" --baum-rootfs "$TMP/rootfs-baum"
for pf in etc/passwd root root/.ssh root/.ssh/authorized_keys; do
	besitz=$(stat -c '%u:%g %a' "$TMP/rootfs-baum/$pf")
	case "$pf $besitz" in
		"etc/passwd 0:0 644"|"root 0:0 700"|"root/.ssh 0:0 700"|"root/.ssh/authorized_keys 0:0 600") ;;
		*) echo "Baum falsch: /$pf ist $besitz" >&2; exit 1 ;;
	esac
done
ok "Baum: /etc/passwd, /root, /root/.ssh, authorized_keys gehoeren root, Modi stimmen"
rm -f "$TMP/hy310-rootfs-platz.ext4"
truncate -s 1G "$TMP/hy310-rootfs-platz.ext4"
# Wortgleich mit build-rootfs.sh, damit dieses Dateisystem dasselbe ist wie
# das abgenommene -- nur mit den elf Platzhaltern mehr.
mke2fs -q -F -t ext4 -L hy310-rootfs -m 1 \
	-E lazy_itable_init=0,lazy_journal_init=0 \
	-d "$TMP/rootfs-baum" "$TMP/hy310-rootfs-platz.ext4"
e2fsck -fn "$TMP/hy310-rootfs-platz.ext4" >/dev/null
ok "$TMP/hy310-rootfs-platz.ext4"

say "Gegenprobe"
echo "  Baumgroesse rootfs: $(du -sxk "$TMP/rootfs-baum" | cut -f1) KiB"
echo "  Dateien boot-baum:  $(find "$TMP/boot-baum" -type f | wc -l)"
ls -l "$TMP/hy310-boot.ext4" "$TMP/hy310-rootfs-platz.ext4"

say "fertig -- jetzt (auf dem Host reicht auch) hy310-mkimage.py --out ..."
