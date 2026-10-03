#!/bin/sh
# Run the check of /etc/h713/wifi.env against good and bad files.
# The same script checks at build time (build-rootfs.sh, step 0) and on the
# device (h713-wifi up) - that is why it has to run here on the host.
#
#   sh tests/h713-wifi-check.sh          -> 20 cases, exit 0 if all pass
#
# Written 12.09.2026 while building the Wi-Fi block (doku/60, section
# "WLAN vor dem Release"). A case can also name a text that has to be in the
# output: set need=TEXT in the line before the call.
set -u
HIER=$(cd "$(dirname "$0")" && pwd)
W="$HIER/../overlay/usr/local/sbin/h713-wifi"
T=$(mktemp -d)
fehler=0
n=0
need=
fall() { # name expected-rc lines...
	name=$1; soll=$2; shift 2
	n=$((n + 1))
	printf '%s\n' "$@" > "$T/$name.env"
	out=$(dash "$W" check "$T/$name.env" 2>&1); rc=$?
	gut=1
	[ "$rc" -eq "$soll" ] || gut=0
	[ -z "$need" ] || printf '%s\n' "$out" | grep -qF -- "$need" || gut=0
	if [ "$gut" -eq 1 ]; then
		printf '  ok    %-22s rc=%s\n' "$name" "$rc"
	else
		printf '  FAIL  %-22s rc=%s (want %s%s): %s\n' "$name" "$rc" "$soll" "${need:+, text '$need'}" "$(echo "$out" | tail -1 | cut -c1-90)"
		fehler=$((fehler + 1))
	fi
	need=
}
CR=$(printf '\r')
echo "good files (rc 0):"
fall ok-ap-default    0 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
# the umlaut is on purpose: an ssid may carry non-ASCII bytes
fall ok-sta           0 "mode=sta" "ssid=Müllers WLAN" "password=secret123" "country=DE"
fall ok-sta-open      0 "mode=sta" "ssid=Cafe" "password=" "country=AT"
fall ok-off           0 "mode=off"
fall ok-5ghz          0 "mode=ap" "ssid=h713" "password=top-secret" "band=5" "channel=44" "country=DE" "ap_ip=10.0.0.1" "ap_dhcp_start=10.0.0.10" "ap_dhcp_end=10.0.0.50"
fall ok-crlf          0 "mode=ap$CR" "ssid=h713$CR" "password=magcubic$CR" "band=2.4$CR" "channel=6$CR" "country=DE$CR" "ap_ip=192.168.4.1$CR" "ap_dhcp_start=192.168.4.10$CR" "ap_dhcp_end=192.168.4.100$CR"
need="WARNING: country is empty"
fall ok-country-empty 0 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
echo "bad files (rc 1):"
fall typo             1 "mode=ap" "ssid=h713" "password=magcubic" "chanel=6" "band=2.4" "country=DE"
fall no-password      1 "mode=ap" "ssid=h713" "password=" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
fall password-short   1 "mode=ap" "ssid=h713" "password=short" "band=2.4" "channel=6" "country=DE"
fall channel-14       1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=14" "country=DE"
fall channel-dfs      1 "mode=ap" "ssid=h713" "password=magcubic" "band=5" "channel=52" "country=DE"
fall country-lower    1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=de"
need="country must be"
fall country-lower-sta 1 "mode=sta" "ssid=Cafe" "password=secret123" "country=de"
fall quote-in-ssid    1 "mode=sta" "ssid=Pete's \"Net\"" "password=secret123" "country=DE"
fall injected-command 1 "mode=ap" "ssid=h713" "password=magcubic" 'band=2.4; rm -rf /' "channel=6" "country=DE"
fall ssid-too-long    1 "mode=sta" "ssid=123456789012345678901234567890123" "password=secret123" "country=DE"
fall ip-broken        1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.999" "ap_dhcp_start=192.168.4.10" "ap_dhcp_end=192.168.4.100"
fall ip-other-subnet  1 "mode=ap" "ssid=h713" "password=magcubic" "band=2.4" "channel=6" "country=DE" "ap_ip=192.168.4.1" "ap_dhcp_start=192.168.5.10" "ap_dhcp_end=192.168.5.100"
fall no-assignment    1 "mode=ap" "ssid h713"
rm -rf "$T"
[ "$fehler" -eq 0 ] && echo "all $n cases as expected" || echo "$fehler of $n cases differ"
exit $fehler
