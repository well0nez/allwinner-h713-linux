#!/bin/sh
# Die Pruefung von /etc/h713/wifi.env gegen gute und schlechte Dateien fahren.
# Dasselbe Skript prueft beim Bau (build-rootfs.sh, Schritt 0) und auf dem
# Geraet (h713-wifi up) -- deshalb muss es hier auf dem Host laufen.
#
#   sh tests/h713-wifi-check.sh          -> 17 Faelle, Exit 0 wenn alle stimmen
#
# Entstanden 12.09.2026 beim Bau des WLAN-Blocks (doku/60 §WLAN vor dem Release).
set -u
HIER=$(cd "$(dirname "$0")" && pwd)
W="$HIER/../overlay/usr/local/sbin/h713-wifi"
T=$(mktemp -d)
fehler=0
fall() { # name erwartet zeilen...
	name=$1; soll=$2; shift 2
	printf '%s\n' "$@" > "$T/$name.env"
	out=$(dash "$W" check "$T/$name.env" 2>&1); rc=$?
	if [ "$rc" -eq "$soll" ]; then
		printf '  ok    %-16s rc=%s\n' "$name" "$rc"
	else
		printf '  FEHL  %-16s rc=%s (soll %s): %s\n' "$name" "$rc" "$soll" "$(echo "$out" | tail -1 | cut -c1-90)"
		fehler=$((fehler + 1))
	fi
}
CR=$(printf '\r')
echo "gute Dateien (rc 0):"
fall ok-ap-vorgabe    0 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
fall ok-sta           0 "mode=sta" "ssid=Müllers WLAN" "password=geheim123" "country=DE"
fall ok-sta-offen     0 "mode=sta" "ssid=Cafe" "password=" "country=AT"
fall ok-off           0 "mode=off"
fall ok-5ghz          0 "mode=ap" "ssid=h713" "password=streng-geheim" "band=5" "channel=44" "country=DE" "ap_ip=10.0.0.1" "ap_dhcp_start=10.0.0.10" "ap_dhcp_end=10.0.0.50"
fall ok-crlf          0 "mode=ap$CR" "ssid=h713$CR" "password=magcubic$CR" "band=2.4$CR" "channel=6$CR" "country=DE$CR" "ap_ip=192.168.4.1$CR" "ap_dhcp_start=192.168.4.10$CR" "ap_dhcp_end=192.168.4.100$CR"
echo "schlechte Dateien (rc 1):"
fall tippfehler       1 "mode=ap" "ssid=h713" "password=magcubic" "chanel=6" "band=2.4" "country=DE"
fall kein-passwort    1 "mode=ap" "ssid=h713" "password=" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
fall pw-zu-kurz       1 "mode=ap" "ssid=h713" "password=kurz" "band=2.4" "channel=6" "country=DE"
fall kanal-14         1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=14" "country=DE"
fall kanal-dfs        1 "mode=ap" "ssid=h713" "password=magcubic" "band=5" "channel=52" "country=DE"
fall land-klein       1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=de"
fall anfuehrung       1 "mode=sta" "ssid=Peters \"Netz\"" "password=geheim123" "country=DE"
fall kommando         1 "mode=ap" "ssid=h713" "password=magcubic" 'band=2.4; rm -rf /' "channel=6" "country=DE"
fall ssid-lang        1 "mode=sta" "ssid=123456789012345678901234567890123" "password=geheim123" "country=DE"
fall ip-kaputt        1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.999" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
fall ip-fremdes-netz  1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.5.10" "ap_dhcp_end=192.168.5.100"
fall keine-zuweisung  1 "mode=ap" "ssid h713"
rm -rf "$T"
[ "$fehler" -eq 0 ] && echo "alle 18 Faelle wie erwartet" || echo "$fehler Fall/Faelle abweichend"
exit $fehler
