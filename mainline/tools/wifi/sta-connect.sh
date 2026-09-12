#!/bin/bash
# Put the board on a real network as a STATION, instead of being an AP.
# RUNS ON THE TARGET.
#
# The image bakes in a boot hotspot (hostapd + dnsmasq own wlan0, and the STA
# wpa_supplicant unit is masked so they cannot fight over it), which is right
# for a projector and wrong for bring-up: a serial console moves files at
# 10.8 KB/s, and an ssh session moves them at wire speed. This script trades
# one for the other until the next reboot, which restores the hotspot.
#
# It runs the supplicant as a bare process rather than via systemd on purpose —
# the unit is masked in this image, and unmasking it would outlive the session.
#
#   usage: ./sta-connect.sh SSID PASSPHRASE [interface]
#
# ⚠ THE BULK-DATA WARNING THAT USED TO BE HERE IS OBSOLETE -- retested and
# refuted on 2026-08-21. It said, correctly for its time, that a sustained
# transfer over this link wedged the board twice out of two attempts (a 10.8 MB
# scp sat at zero bytes for six minutes, then `cmd timed-out` and the box went
# down). That was the SDIO bulk-RX defect, and it was not STA-specific: it failed
# in AP mode too. Patch 0046 (the v5p3x IDMA descriptor encoding) fixed it.
#
# Retested in STA mode against an 802.11ax AP, board at 10.42.0.50:
#
#   8 MiB   board-RX               4.46 MB/s   hash exact
#   64 MiB  RX 8.11 / TX 9.20 MB/s             hash exact
#   128 MiB RX 8.90 / TX 9.62 MB/s             hash exact
#
# Zero cmd53, cmd timed-out, DHDISDOWN or SDIO faults throughout, board up
# continuously. STA mode carries files, and on an HE-capable AP it is faster
# than the 2.4 GHz HT40 hotspot the image ships.
#
# Still worth keeping the serial console attached: it is the only control path
# once wlan0 leaves AP mode, and dhclient runs in the foreground here, so an
# unresponsive-looking shell is usually just DHCP waiting -- Ctrl-C returns it.

set -eu

SSID=${1:?usage: sta-connect.sh SSID PASSPHRASE [interface]}
PSK=${2:?usage: sta-connect.sh SSID PASSPHRASE [interface]}
IFACE=${3:-wlan0}
CONF=/etc/wpa_supplicant/wpa-sta-$IFACE.conf

echo "==> stopping the boot hotspot"
systemctl stop h713-hotspot.service 2>/dev/null || true
pkill -x hostapd 2>/dev/null || true
pkill -x dnsmasq 2>/dev/null || true
pkill -f "wpa_supplicant.*$IFACE" 2>/dev/null || true
sleep 1

echo "==> $IFACE: AP -> managed"
ip link set "$IFACE" down
iw dev "$IFACE" set type managed
ip link set "$IFACE" up

# The hotspot's address is still on the interface at this point and will
# happily coexist with the DHCP lease, quietly adding a second subnet to every
# routing decision. Drop it.
ip -4 addr flush dev "$IFACE"

echo "==> associating with $SSID"
umask 077
# wpa_passphrase emits the plaintext as a #psk= comment; strip it so the
# credential exists on disk only in its hashed form.
wpa_passphrase "$SSID" "$PSK" | grep -v '#psk' > "$CONF"
wpa_supplicant -B -i "$IFACE" -c "$CONF" -f /var/log/wpa-sta.log

# The `|| true` is load-bearing under `set -e`: on every iteration before the
# link comes up the grep fails, and an unguarded AND-list would abort the script
# on the first pass rather than wait.
for i in $(seq 20); do
  sleep 1
  if iw dev "$IFACE" link 2>/dev/null | grep -q "^Connected"; then break; fi
done
iw dev "$IFACE" link | head -3

echo "==> DHCP"
dhclient -1 "$IFACE"
ip -br addr show "$IFACE"
ip route | head -3
