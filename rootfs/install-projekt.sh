#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
#
# install-projekt.sh -- die projektspezifischen Teile in einen ausgepackten
# Rootfs-Baum einspielen. Aufgerufen von build-rootfs.sh, aber ausdruecklich
# auch ALLEIN benutzbar:
#
#     ./install-projekt.sh /srv/h713-rootfs-neu      # z. B. die NFS-Wurzel
#     ./install-projekt.sh --dry-run /pfad/zum/baum
#
# Der zweite Fall ist der Grund fuer das eigene Skript: nach 109 §4.2 wird
# derselbe Bau an ZWEI Orte gelegt (hy310-rootfs auf der eMMC und die
# NFS-Wurzel auf dem Host), und wenn h713-tv oder die Module neu gebaut
# werden, will man sie nachziehen, ohne das ganze Rootfs neu zu bootstrappen.
#
# Eingespielt wird:
#   1. h713-tv (quer gebaut)  + Unit + udev-Regel + gamma-standard.bin
#   2. die Kernelmodule des GUT-Standes + die aic8800-Module (WLAN) + depmod
#   3. h713-pq
#   4. h713-focus
#   5. h713-cam
#
# NICHT eingespielt wird irgendein proprietaerer Blob (107 §5). Am Ende steht
# eine Sperre, die den Baum danach absucht und den Lauf abbricht, wenn doch
# einer drin liegt -- namentlich hy310-hdcp22.bin, das im heutigen
# Netboot-Root unter /lib/firmware liegt und auf keinen Fall mitkommen darf.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Projektwurzel: das naechste Elternverzeichnis mit mainline/build/build.sh -- so
# funktioniert das Skript im Arbeitsverzeichnis (analyse/release/arbeit/...) wie im
# Release-Repo (rootfs/ bzw. installer/ direkt unter der Wurzel), doku/116 P3.
projekt_wurzel() { local d=$1; while [ "$d" != / ]; do [ -f "$d/mainline/build/build.sh" ] && { echo "$d"; return; }; d=$(dirname "$d"); done; return 1; }
PROJECT_ROOT=$(projekt_wurzel "$HERE") || { echo "Projektwurzel (mainline/build/build.sh) oberhalb von $HERE nicht gefunden" >&2; exit 1; }

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; shift; fi
TREE=${1:-}
[[ -n "$TREE" ]] || { echo "Aufruf: ${0##*/} [--dry-run] BAUM" >&2; exit 2; }

# Von build-rootfs.sh per Umgebung gesetzt, sonst Vorgaben.
MODROOT=${MODROOT:-$PROJECT_ROOT/mainline/build/modroot.GUT-bad2f16b}
H713_TV_SRC=${H713_TV_SRC:-$PROJECT_ROOT/userspace/h713-tv}
H713_TV_BIN=${H713_TV_BIN:-$H713_TV_SRC/h713-tv.aarch64-linux-gnu}
H713_PQ_SRC=${H713_PQ_SRC:-$PROJECT_ROOT/userspace/h713-pq}
H713_FOCUS_SRC=${H713_FOCUS_SRC:-$PROJECT_ROOT/userspace/h713-focus}
H713_CAM_SRC=${H713_CAM_SRC:-$PROJECT_ROOT/userspace/h713-cam}
# Die WLAN-Module baut build.sh AUSSERHALB des Kernelbaums (out-of-tree, radxa-
# Quelle + patches/aic8800/) und legt sie nach build/out/modules/ -- in keinem
# modroot liegen sie. Ohne diesen Schritt haette das Abbild Pakete, Dienst und
# wifi.env, aber keinen Treiber (aufgefallen 12.09.).
AIC8800_MODULES=${AIC8800_MODULES:-$PROJECT_ROOT/mainline/build/out/modules}

say()  { printf '    -- %s\n' "$*"; }
info() { printf '       %s\n' "$*"; }
warn() { printf '!!     %s\n' "$*" >&2; }
die()  { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Blob-Sperre: was NIE ins Abbild darf
# ---------------------------------------------------------------------------
# Firmware und PQ-Daten kommen spaeter vom Installer aus h713-extract
# (107 §5, 108 §2/§6). Sie liegen im Arbeitsbaum und im heutigen
# Netboot-Root herum, also ist ein versehentliches Mitkopieren der
# wahrscheinlichste Fehler -- deshalb eine Sperre und nicht nur ein Satz im
# Plan.
#
# hy310-hdcp22.bin steht ausdruecklich vorn: HDCP-Schluesselmaterial. Es liegt
# heute in /srv/h713-rootfs/lib/firmware/ und darf das Abbild nie erreichen.
VERBOTEN_NAMEN=(
	'hy310-hdcp22.bin'      # HDCP 2.2 -- Schluesselmaterial, nie ins Abbild
	'hdcp_v22.bin'          # dasselbe unter dem Vendor-Namen
	'h713-arisc.bin'        # ARISC-Firmware, Vendor (108 §2) -> Installer
	'hy310-edid.bin'        # aus dem Stock ausgelesen -> Installer
	'hy310-edid-nodc.bin'
	'msp-patch.bin'         # MSP-DSP-Patch, Vendor -> Installer
	'fmacfw*'               # aic8800-WLAN-Firmware: NICHT im Abbild, kommt vom
	'fmacfwbt*'             #   Installer aus dem Abzug (h713-extract, 12.09.). Die
	                        #   Module selbst (GPL) liegen in extra/, siehe Schritt 2.
)
VERBOTEN_PFADE=(
	'lib/firmware/h713'
	'lib/firmware/aic8800_fw'
	'usr/lib/firmware/h713'
)

blob_sperre() {
	local tree=$1 found=0 n p hit
	for n in "${VERBOTEN_NAMEN[@]}"; do
		while IFS= read -r hit; do
			warn "VERBOTEN im Baum: ${hit#"$tree"}"
			found=1
		done < <(find "$tree" -name "$n" -print 2>/dev/null)
	done
	for p in "${VERBOTEN_PFADE[@]}"; do
		if [[ -e "$tree/$p" ]]; then
			warn "VERBOTEN im Baum: /$p"
			found=1
		fi
	done
	# tvconfig muss leer sein: der Pfad bezeichnet seit 107 §8 NUR das
	# Verzeichnis mit den extrahierten PQ-Dateien. Die Dienstkonfiguration
	# heisst /etc/hy310/tv.conf und ist etwas anderes.
	if [[ -d "$tree/etc/hy310/tvconfig" ]] && [[ -n "$(ls -A "$tree/etc/hy310/tvconfig")" ]]; then
		warn "VERBOTEN: /etc/hy310/tvconfig ist nicht leer"
		found=1
	fi
	((found == 0)) || die "Blob-Sperre: das Abbild traegt Dateien, die es nicht tragen darf (107 §5)"
	say "Blob-Sperre: sauber (${#VERBOTEN_NAMEN[@]} Namen, ${#VERBOTEN_PFADE[@]} Pfade geprueft, tvconfig leer)"
}

# ---------------------------------------------------------------------------
# Quellen pruefen
# ---------------------------------------------------------------------------
quellen_pruefen() {
	local fehler=0

	if [[ -x "$H713_TV_BIN" ]]; then
		local typ; typ=$(file -b "$H713_TV_BIN" 2>/dev/null || echo '?')
		case "$typ" in
		*aarch64*|*ARM\ aarch64*) : ;;
		'?') warn "file(1) fehlt -- Architektur von h713-tv ungeprueft" ;;
		*) warn "h713-tv ist NICHT aarch64: $typ"; fehler=1 ;;
		esac
	else
		warn "h713-tv fehlt: $H713_TV_BIN"
		info "quer bauen:  make -C ${H713_TV_SRC#"$PROJECT_ROOT"/} cross"
		info "  (Host-Clang gegen /srv/h713-rootfs als Sysroot -- siehe Makefile)"
		fehler=1
	fi

	local f
	for f in h713-tv@.service 99-h713-tv.rules gamma-standard.bin; do
		[[ -r "$H713_TV_SRC/$f" ]] || { warn "fehlt: $H713_TV_SRC/$f"; fehler=1; }
	done

	if [[ -d "$MODROOT/lib/modules" ]]; then
		local rel
		rel=$(ls -1 "$MODROOT/lib/modules" | head -1)
		[[ -n "$rel" ]] || { warn "kein Kernelrelease in $MODROOT/lib/modules"; fehler=1; }
	else
		warn "Modulbaum fehlt: $MODROOT/lib/modules"
		fehler=1
	fi

	[[ -x "$H713_PQ_SRC/h713-pq" ]] || { warn "fehlt: $H713_PQ_SRC/h713-pq"; fehler=1; }
	[[ -d "$H713_PQ_SRC/h713_pq" ]] || { warn "fehlt: $H713_PQ_SRC/h713_pq/"; fehler=1; }

	[[ -x "$H713_FOCUS_SRC/h713-focus" ]] || \
		{ warn "fehlt: $H713_FOCUS_SRC/h713-focus"; fehler=1; }
	[[ -x "$H713_CAM_SRC/h713-cam" ]] || \
		{ warn "fehlt: $H713_CAM_SRC/h713-cam"; fehler=1; }
	for ko in aic8800_bsp aic8800_fdrv; do
		[[ -f "$AIC8800_MODULES/$ko.ko" ]] || \
			{ warn "fehlt: $AIC8800_MODULES/$ko.ko (build/build.sh aic8800)"; fehler=1; }
	done

	return $fehler
}

# ---------------------------------------------------------------------------
# Trockenlauf
# ---------------------------------------------------------------------------
if ((DRY_RUN)); then
	printf '    Projektteile (install-projekt.sh --dry-run)\n'
	quellen_pruefen || warn "Quellen unvollstaendig -- der scharfe Lauf wuerde hier abbrechen"
	local_rel=$(ls -1 "$MODROOT/lib/modules" 2>/dev/null | head -1 || true)
	cat <<EOF
    1. h713-tv
       ${H713_TV_BIN#"$PROJECT_ROOT"/}
           -> /usr/local/sbin/h713-tv                     0755
       h713-tv@.service   -> /etc/systemd/system/          0644
       99-h713-tv.rules   -> /etc/udev/rules.d/            0644
       gamma-standard.bin  -> /usr/local/share/h713-tv/    0644
       README.md           -> /usr/local/share/doc/h713-tv/
       (kein systemctl enable: die Unit hat keinen [Install]-Abschnitt,
        gestartet wird sie von der udev-Regel ueber SYSTEMD_WANTS)
    2. Kernelmodule
       ${MODROOT#"$PROJECT_ROOT"/}/lib/modules/${local_rel:-<release>}
           -> /lib/modules/${local_rel:-<release>}   ($(find "$MODROOT" -name '*.ko*' 2>/dev/null | wc -l) Module,
              $(du -sh "$MODROOT" 2>/dev/null | cut -f1))
       ${AIC8800_MODULES#"$PROJECT_ROOT"/}/{aic8800_bsp,aic8800_fdrv}.ko
           -> /lib/modules/${local_rel:-<release>}/extra/   (WLAN, out-of-tree;
              btlpm bleibt draussen: keine BT-Firmware im Abzug)
       danach depmod -b
       (der Symlink build -> /work/mainline/build/... bleibt DRAUSSEN)
    3. h713-pq
       ${H713_PQ_SRC#"$PROJECT_ROOT"/}/{h713-pq,h713_pq/}
           -> /usr/local/lib/h713-pq/, Symlink /usr/local/bin/h713-pq
       (reines Python, Standardbibliothek; liest /etc/hy310/tvconfig)
    4. h713-focus
       ${H713_FOCUS_SRC#"$PROJECT_ROOT"/}/h713-focus
           -> /usr/local/bin/h713-focus                   0755
       README.md           -> /usr/local/share/doc/h713-focus/
       (eine Datei, reines Python; faehrt den Fokusmotor von Hand.
        KEINE Blacklist fuer hy310_focus_motor -- seit Patch 0156 ist
        homing standardmaessig aus, das Laden bewegt nichts.)
    5. h713-cam
       ${H713_CAM_SRC#"$PROJECT_ROOT"/}/h713-cam
           -> /usr/local/bin/h713-cam                     0755
       README.md           -> /usr/local/share/doc/h713-cam/
       (eine Datei, reines Python; probe/controls/get/set/grab an der
        internen UVC-Kamera. uvcvideo kommt aus dem Modulbaum, Schritt 2.)
    6. Blob-Sperre
       Abbruch, wenn eine dieser Dateien im Baum liegt:
       ${VERBOTEN_NAMEN[*]}
       oder eines dieser Verzeichnisse: ${VERBOTEN_PFADE[*]}
       oder /etc/hy310/tvconfig nicht leer ist.
EOF
	exit 0
fi

# ===========================================================================
# Scharfer Lauf
# ===========================================================================
[[ -d "$TREE/etc" && -d "$TREE/usr" ]] || die "das sieht nicht wie ein Rootfs aus: $TREE"
quellen_pruefen || die "Quellen unvollstaendig (siehe oben)"

# --- 1. h713-tv -----------------------------------------------------------
say "h713-tv"
install -D -m 0755 "$H713_TV_BIN"                     "$TREE/usr/local/sbin/h713-tv"
install -D -m 0644 "$H713_TV_SRC/h713-tv@.service"   "$TREE/etc/systemd/system/h713-tv@.service"
install -D -m 0644 "$H713_TV_SRC/99-h713-tv.rules"   "$TREE/etc/udev/rules.d/99-h713-tv.rules"
install -D -m 0644 "$H713_TV_SRC/gamma-standard.bin"  "$TREE/usr/local/share/h713-tv/gamma-standard.bin"
[[ -r "$H713_TV_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_TV_SRC/README.md" "$TREE/usr/local/share/doc/h713-tv/README.md"
# Eine alte h713-tv.service (nicht-Template) waere ein Doppelgaenger --
# derselbe Handgriff wie im Makefile-Ziel install-data.
rm -f "$TREE/etc/systemd/system/h713-tv.service"
info "/usr/local/sbin/h713-tv ($(stat -c %s "$TREE/usr/local/sbin/h713-tv") B), Unit, udev-Regel, gamma-standard.bin"
# Kein enable: h713-tv@.service hat absichtlich keinen [Install]-Abschnitt.
# Der hdmirx-Probe laeuft asynchron (EDID/HPD ueber zehn Sekunden), ein Start
# "beim Booten" waere ein Wettlauf. Die udev-Regel startet die Instanz, sobald
# /dev/videoN erscheint.

# --- 2. Kernelmodule -------------------------------------------------------
say "Kernelmodule"
KREL=$(ls -1 "$MODROOT/lib/modules" | head -1)
SRC_MOD="$MODROOT/lib/modules/$KREL"
DST_MOD="$TREE/lib/modules/$KREL"
rm -rf "$DST_MOD"
install -d "$DST_MOD"
# --exclude build/source: das sind Symlinks in den Bauverzeichnisbaum des
# Containers (/work/mainline/build/linux-...). Im Abbild waeren sie tote
# Verweise, und sie sind der Weg, ueber den versehentlich ein halber
# Kernelbaum mitwandert.
tar -C "$SRC_MOD" --exclude=./build --exclude=./source -cf - . | \
	tar -C "$DST_MOD" --no-same-owner -xf -
# Guertel und Hosenträger: falls eine tar-Fassung die Ausschluesse anders
# auslegt, liegen sie hier trotzdem nicht mehr.
rm -f "$DST_MOD/build" "$DST_MOD/source"
KO_N=$(find "$DST_MOD" -name '*.ko*' | wc -l)
((KO_N > 0)) || die "keine Module nach $DST_MOD kopiert"

# aic8800 (WLAN), out-of-tree gebaut. Nach extra/, wo depmod Fremdmodule
# erwartet. Nur bsp + fdrv: btlpm ist Bluetooth, und dessen Firmware liegt
# nicht im Vendor-Abzug (60-offen §WLAN und Bluetooth).
# Vermagic pruefen: ein gegen einen anderen Baum gebautes Modul laedt entweder
# nicht oder -- schlimmer -- laedt und stimmt nicht. Vergleich gegen ein
# In-Tree-Modul desselben modroot.
vermagic() { modinfo -F vermagic "$1" 2>/dev/null || strings -n 8 "$1" | sed -n 's/^vermagic=//p' | head -1; }
ref_ko=$(find "$DST_MOD" -name '*.ko' -print -quit)
ref_vm=$(vermagic "$ref_ko")
install -d "$DST_MOD/extra"
for ko in aic8800_bsp aic8800_fdrv; do
	src="$AIC8800_MODULES/$ko.ko"
	[[ -f "$src" ]] || die "$src fehlt -- build/build.sh aic8800 (gegen denselben Kernelbaum wie $MODROOT)"
	vm=$(vermagic "$src")
	[[ "$vm" == "$ref_vm" ]] || die "$ko.ko: vermagic '$vm' passt nicht zum Modulbaum ('$ref_vm') -- gegen denselben Kernel bauen"
	install -m 0644 "$src" "$DST_MOD/extra/$ko.ko"
done
info "aic8800_bsp + aic8800_fdrv nach extra/ (vermagic: $ref_vm)"
# depmod neu rechnen: die modules.dep aus dem Bau nennt Pfade des Bauorts.
if command -v depmod >/dev/null 2>&1; then
	depmod -b "$TREE" "$KREL"
	info "depmod -b: $(wc -l < "$DST_MOD/modules.dep") Zeilen in modules.dep"
else
	warn "depmod fehlt -- modules.dep bleibt die aus dem Bau (Paket kmod)"
fi
info "$KO_N Module, Release $KREL, $(du -sh "$DST_MOD" | cut -f1)"

# --- 3. h713-pq -----------------------------------------------------------
say "h713-pq"
PQ_DST="$TREE/usr/local/lib/h713-pq"
rm -rf "$PQ_DST"
install -d -m 0755 "$PQ_DST"
install -m 0755 "$H713_PQ_SRC/h713-pq" "$PQ_DST/h713-pq"
# __pycache__ des Hosts hat hier nichts verloren (x86-Bytecode-Pfade, und es
# wuerde beim ersten Lauf ohnehin neu erzeugt).
tar -C "$H713_PQ_SRC" --exclude=__pycache__ -cf - h713_pq | tar -C "$PQ_DST" -xf -
[[ -r "$H713_PQ_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_PQ_SRC/README.md" "$TREE/usr/local/share/doc/h713-pq/README.md"
# Der Einstiegspunkt macht sys.path.insert(0, Path(__file__).resolve().parent);
# resolve() folgt dem Symlink, also findet er das Paket in /usr/local/lib.
install -d "$TREE/usr/local/bin"
ln -sfn ../lib/h713-pq/h713-pq "$TREE/usr/local/bin/h713-pq"
# Kompatibilitaet: die alten Namen bleiben als Symlink erreichbar (113 B.4).
# Nur die Programme, nicht die Unit -- ein Unit-Symlink waere ein Alias und
# gaebe zwei Namen fuer denselben Dienst.
ln -sfn h713-tv                "$TREE/usr/local/sbin/hy310-tv"
ln -sfn h713-pq                "$TREE/usr/local/bin/hy310-pq"
info "/usr/local/lib/h713-pq + Symlink /usr/local/bin/h713-pq ($(du -sh "$PQ_DST" | cut -f1))"

# --- 4. h713-focus ---------------------------------------------------------
say "h713-focus"
install -d -m 0755 "$TREE/usr/local/bin"
install -m 0755 "$H713_FOCUS_SRC/h713-focus" "$TREE/usr/local/bin/h713-focus"
[[ -r "$H713_FOCUS_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_FOCUS_SRC/README.md" \
		"$TREE/usr/local/share/doc/h713-focus/README.md"
# Der fruehere Name im Altbestand war schlicht "focus" (legacy/tools/focus).
# Dafuer gibt es bewusst KEINEN Symlink: das alte Skript fuhr mit cmd 1/2 und
# ohne jede Pruefung; wer es aus einem Skript aufruft, soll den Unterschied
# merken statt ihn geerbt zu bekommen.
info "/usr/local/bin/h713-focus ($(wc -l < "$H713_FOCUS_SRC/h713-focus") Zeilen)"

# --- 5. h713-cam -----------------------------------------------------------
say "h713-cam"
install -m 0755 "$H713_CAM_SRC/h713-cam" "$TREE/usr/local/bin/h713-cam"
[[ -r "$H713_CAM_SRC/README.md" ]] && \
	install -D -m 0644 "$H713_CAM_SRC/README.md" \
		"$TREE/usr/local/share/doc/h713-cam/README.md"
# Ohne uvcvideo im Modulbaum sagt h713-cam das selbst -- aber der Bau soll es
# frueher sagen als das Geraet.
if ! find "$DST_MOD" -name 'uvcvideo.ko*' -print -quit | grep -q .; then
	warn "uvcvideo.ko fehlt im Modulbaum $MODROOT -- h713-cam findet dann keine Kamera"
fi
info "/usr/local/bin/h713-cam ($(wc -l < "$H713_CAM_SRC/h713-cam") Zeilen)"

# --- 6. Blob-Sperre --------------------------------------------------------
blob_sperre "$TREE"

# Zusaetzlich: /lib/firmware soll leer sein oder gar nicht existieren. Was
# gebraucht wird, spielt der Installer ein (108 §2).
if [[ -d "$TREE/lib/firmware" ]]; then
	# regulatory.db* ist wireless-regdb (ISC-Lizenz, frei) -- kein Blob, kein Verdacht.
	FW_N=$(find "$TREE/lib/firmware" -type f -not -name 'regulatory.db*' | wc -l)
	if ((FW_N > 0)); then
		warn "/lib/firmware traegt $FW_N Dateien -- pruefen, ob das Absicht ist:"
		find "$TREE/lib/firmware" -type f -not -name 'regulatory.db*' -printf '       /lib/firmware/%P\n' >&2
	else
		say "/lib/firmware ist leer (Firmware kommt vom Installer)"
	fi
else
	say "/lib/firmware existiert nicht (Firmware kommt vom Installer)"
fi
