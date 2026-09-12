#!/bin/sh
# Customize an extracted Debian rootfs without executing target binaries.
# Usage: customize.sh ROOTFS SSH_PUBLIC_KEY_FILE DEBIAN_MIRROR DEBIAN_SUITE
set -eu

R=$1
SSH_KEY=$2
DEBIAN_MIRROR=$3
DEBIAN_SUITE=$4

[ -d "$R/etc" ] || { echo "error: invalid rootfs: $R" >&2; exit 1; }
[ -s "$SSH_KEY" ] || { echo "error: missing SSH public key: $SSH_KEY" >&2; exit 1; }

printf '%s\n' h713-arm64 > "$R/etc/hostname"
cat > "$R/etc/hosts" <<EOF
127.0.0.1	localhost
127.0.1.1	h713-arm64
EOF

# UDISK is factory GPT partition 26. systemd-growfs expands this deliberately
# small image to the full partition on first boot.
printf '%s\n' \
  '/dev/mmcblk0p26  /  ext4  defaults,noatime,x-systemd.growfs  0  1' \
  > "$R/etc/fstab"

mkdir -p "$R/etc/network"
cat > "$R/etc/network/interfaces" <<EOF
auto lo
iface lo inet loopback
allow-hotplug eth0
iface eth0 inet dhcp
EOF

# Replace mmdebstrap's host-visible bootstrap keyring path with a target-local
# deb822 source. The installed debian-archive-keyring package owns this keyring.
rm -f "$R/etc/apt/sources.list"
install -d -m 0755 "$R/etc/apt/sources.list.d"
cat > "$R/etc/apt/sources.list.d/debian.sources" <<EOF
Types: deb
URIs: $DEBIAN_MIRROR
Suites: $DEBIAN_SUITE
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF

# Root has no usable password. SSH permits only the explicitly supplied key;
# the physical serial console remains available through autologin.
shadow_tmp="$R/etc/.shadow.h713"
awk -F: 'BEGIN { OFS=FS } $1 == "root" { $2="!" } { print }' \
  "$R/etc/shadow" > "$shadow_tmp"
cat "$shadow_tmp" > "$R/etc/shadow"
rm -f "$shadow_tmp"

install -d -m 0700 "$R/root/.ssh"
install -m 0600 "$SSH_KEY" "$R/root/.ssh/authorized_keys"

install -d -m 0755 "$R/etc/ssh/sshd_config.d"
cat > "$R/etc/ssh/sshd_config.d/10-h713.conf" <<EOF
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
X11Forwarding no
EOF

# Never clone host keys or machine identity across images. Generate missing
# host keys before ssh.service on every boot; ssh-keygen -A is idempotent and
# avoids relying on ConditionFirstBoot ordering while /etc/machine-id is being
# initialized.
rm -f "$R"/etc/ssh/ssh_host_*
rm -f "$R/etc/machine-id" "$R/var/lib/dbus/machine-id"
: > "$R/etc/machine-id"
rm -f "$R/var/lib/systemd/random-seed"

systemd_dir="$R/etc/systemd/system"
install -d -m 0755 \
  "$systemd_dir/getty.target.wants" \
  "$systemd_dir/multi-user.target.wants" \
  "$systemd_dir/ssh.service.wants" \
  "$systemd_dir/serial-getty@ttyS0.service.d"
ln -sfn /usr/lib/systemd/system/serial-getty@.service \
  "$systemd_dir/getty.target.wants/serial-getty@ttyS0.service"
ln -sfn /usr/lib/systemd/system/ssh.service \
  "$systemd_dir/multi-user.target.wants/ssh.service"
cat > "$systemd_dir/h713-ssh-host-keys.service" <<EOF
[Unit]
Description=Generate missing SSH host keys
Before=ssh.service

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes
EOF
ln -sfn ../h713-ssh-host-keys.service \
  "$systemd_dir/ssh.service.wants/h713-ssh-host-keys.service"
ln -sfn /dev/null "$systemd_dir/systemd-networkd-wait-online.service"

cat > "$systemd_dir/serial-getty@ttyS0.service.d/autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I \$TERM
EOF

# Load the AIC8800 WiFi/BT modules at boot. bsp registers the SDIO glue and
# powers the chip; fdrv (WiFi) and btlpm (BT) depend on it, so ordering matters.
install -d -m 0755 "$R/etc/modules-load.d"
cat > "$R/etc/modules-load.d/aic8800.conf" <<EOF
aic8800_bsp
aic8800_fdrv
aic8800_btlpm
EOF

# Quiet the WiFi driver for production. aic8800_fdrv's aicwf_dbg_level defaults
# to LOGERROR|LOGINFO|LOGDEBUG|LOGTRACE|LOGFW (0x40F); the DEBUG/TRACE bits flood
# the serial console under load (per-command rwnx_send_msg / rwnx_fill_station_info
# spam). Keep errors only. Flags (aicwf_debug.h): ERROR=0x1 INFO=0x2 TRACE=0x4
# DEBUG=0x8 FW=0x400. It stays a live knob: raise it for debugging via
# echo N > /sys/module/aic8800_fdrv/parameters/aicwf_dbg_level  and read it back
# from `journalctl -k` (kernel log), not the console (e.g. 0x403 adds firmware logs).
install -d -m 0755 "$R/etc/modprobe.d"
cat > "$R/etc/modprobe.d/aic8800.conf" <<EOF
options aic8800_fdrv aicwf_dbg_level=0x1
EOF

# Regulatory domain. The aic8800 wiphy is SELF-MANAGED (custregd=Y), so
# cfg80211's regulatory.db never applies to it -- the driver installs a domain
# from its own table in regdb.c, selected by default_ccode. That table is real
# (185 countries, 98 distinct rule sets, correct DFS regions and power limits),
# but default_ccode was a compiled-in "00", which resolves to a permissive world
# entry:
#
#   country 00: DFS-UNSET  (2380-2520 @ 40) 20dBm  (5140-5980 @ 80) 20dBm
#
# -- wider than the ISM band, covering DFS and weather-radar spectrum with no DFS
# or passive-scan constraint. patches/aic8800/aic8800-0006 exposes the selector;
# this sets it. With WIFI_REGDOMAIN=US the radio reports instead:
#
#   country US: DFS-FCC  (2400-2472) 30dBm, DFS on 5250-5350 and 5470-5730, ...
#
# Set WIFI_REGDOMAIN to the ISO 3166-1 alpha-2 code where the unit operates.
# Note the driver still prints "CAUTION: USING PERMISSIVE CUSTOM REGULATORY
# RULES" afterwards -- that message is on the SUCCESS branch in rwnx_custregd(),
# so it fires whatever domain is applied. Check `iw reg get`, not the log.
cat > "$R/etc/modprobe.d/aic8800-regdomain.conf" <<EOF
options aic8800_fdrv default_ccode=${WIFI_REGDOMAIN:-US}
EOF

# wireless-regdb ships Debian- and upstream-signed copies and defaults to the
# Debian one (alternatives priority 100 vs 50). Our kernel is mainline, so it
# only carries the upstream certs (net/wireless/certs: sforshee, wens) and
# cannot verify Debian's benh@debian.org signature. Select the upstream pair.
# This governs cfg80211's global domain rather than the self-managed wiphy
# above, so it matters if custregd is ever turned off -- and a correct link
# costs nothing either way.
if [ -e "$R/lib/firmware/regulatory.db-upstream" ]; then
  chroot "$R" update-alternatives --set regulatory.db \
    /lib/firmware/regulatory.db-upstream >/dev/null 2>&1 || true
fi

# AIC8800 Bluetooth: attach the HCI UART on ttyS1 (H4, 1.5 Mbaud). Use NO host
# flow control — mainline dw-apb-uart RTS/CTS blocks the controller (HCI cmd
# timeout), whereas 'noflow' works. hciattach returns 0 even when the controller
# is mute, so the loop verifies 'hciconfig hci0 up' and retries.
#
# Cold boot used to log two "opcode 0x1003 tx timeout" errors (Read Local
# Supported Features) and take until ~14s to reach MGMT, because the first
# N_HCI attach after power-on leaves the controller unable to answer the first
# HCI command. Measured 2026-08-21:
#
#   baseline                      2 timeouts, up on attempt 2, MGMT at 13.9s
#   +5s settle before attaching   2 timeouts (just later) -- NOT a timing race
#   115200 instead of 1.5 Mbaud   FAILS: 10 attempts, 30 timeouts, never up
#   +drain ttyS1 before attach    0 then 1 timeout -- helps, not deterministic
#   +drain +prime attach/detach   0 timeouts, attempt 1, 3 cold boots out of 3
#
# So the chip is at 1.5 Mbaud from power-on (the RE port notes in
# local/allwinner-h713-linux/docs/subsystems/wifi-bt.md claim 115200 and a baud
# race; that is wrong for this firmware), and the retry never worked because of
# elapsed time -- it worked because it was the SECOND attach. The script now
# drains stale bytes and primes with an attach/detach cycle, so the real attach
# is the second one and no HCI command is ever sent to a desynced controller.
install -d -m 0755 "$R/usr/local/sbin"
cat > "$R/etc/default/h713-bt-attach" <<'EOF'
# BT UART attach tuning. 115200 was tested on a cold boot 2026-08-21 and fails
# completely (10 attempts, 30 x opcode 0x1003 timeout, hci0 never up): the chip
# is at 1.5 Mbaud from power-on. BT_DRAIN flushes stale boot bytes off ttyS1;
# BT_PRIME does a throwaway attach/detach so the real attach is the second one.
BT_BAUD=1500000
BT_DRAIN=1
BT_PRIME=1
EOF
cat > "$R/usr/local/sbin/h713-bt-attach" <<'EOS'
#!/bin/sh
# Bring up the AIC8800 Bluetooth controller (hci0) on UART1.
CONF=/etc/default/h713-bt-attach
BT_BAUD=1500000
BT_DRAIN=1
BT_PRIME=1
[ -r "$CONF" ] && . "$CONF"

rfkill unblock bluetooth 2>/dev/null || true
modprobe hci_uart 2>/dev/null || true

# The BT core emits bytes on ttyS1 as it boots. If N_HCI attaches while those are
# still buffered the H4 parser locks onto the wrong offset and the first HCI
# command response is lost.
if [ "$BT_DRAIN" = 1 ]; then
	stty -F /dev/ttyS1 "$BT_BAUD" raw -echo -crtscts 2>/dev/null || true
	timeout 1 cat /dev/ttyS1 >/dev/null 2>&1 || true
fi

# Draining alone is not deterministic. The retry has always succeeded on the
# SECOND attach, so make that explicit: prime with an attach/detach cycle and let
# the real attach below be the second one. Priming sends no HCI commands, so a
# desynced controller costs nothing instead of two 2s timeouts.
if [ "$BT_PRIME" = 1 ]; then
	hciattach /dev/ttyS1 any "$BT_BAUD" noflow >/dev/null 2>&1 || true
	sleep 1
	pkill -x hciattach 2>/dev/null || true
	sleep 1
fi

i=0
while [ "$i" -lt 10 ]; do
	i=$((i + 1))
	pkill -x hciattach 2>/dev/null || true
	hciattach /dev/ttyS1 any "$BT_BAUD" noflow || true
	if hciconfig hci0 up 2>/dev/null && hciconfig hci0 2>/dev/null | grep -q "UP RUNNING"; then
		logger -t h713-bt-attach "hci0 up on attempt $i baud=$BT_BAUD drain=$BT_DRAIN prime=$BT_PRIME"
		exit 0
	fi
	sleep 2
done
logger -t h713-bt-attach "hci0 did NOT come up after $i attempts baud=$BT_BAUD"
exit 1
EOS
chmod 0755 "$R/usr/local/sbin/h713-bt-attach"
cat > "$systemd_dir/h713-bt-attach.service" <<EOF
[Unit]
Description=AIC8800 Bluetooth HCI attach (ttyS1, H4, noflow)
After=systemd-modules-load.service
Wants=systemd-modules-load.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/h713-bt-attach
# After an AIC8800 firmware crash the combo chip is dead, and hciattach blocks
# in the HCI/UART path where SIGTERM does not reach it. systemd then waits out
# the full default stop timeout on every reboot, which is what made the
# 2026-07-23 recovery attempt look like a hang and cost a power cycle. Nothing
# useful happens in that window -- BT cannot tear down on a dead chip -- so cut
# it short and let the shutdown proceed.
TimeoutStopSec=10s

[Install]
WantedBy=multi-user.target
EOF
ln -sfn ../h713-bt-attach.service \
  "$systemd_dir/multi-user.target.wants/h713-bt-attach.service"

# AIC8800 WiFi firmware-crash recovery. Under heavy load the vendor fdrv can
# time out on its firmware command handshake ("cmd timed-out / wlan error reset
# flow"), mark its cmd queue CRASHED, and fire a KOBJ_CHANGE uevent with
# DHDISDOWN=1. There is NO safe in-place recovery: unbinding+reloading the SDIO
# stack races the mmc/driver core into a NULL-deref Oops (bench-observed), and
# the chip -- WiFi and BT both, one combo part -- only comes back on a full
# boot.
#
# So the recovery IS the reboot, and the job is to make that reboot reliable:
# the handler logs the fault and then reboots (policy in
# /etc/default/h713-wifi-recovery), h713-bt-attach gets a short stop timeout so
# a dead chip cannot stall the shutdown, and RebootWatchdogSec arms the sunxi
# watchdog across the transition so a stuck unit still cannot wedge the board.
# That combination is what the 2026-07-23 attempt lacked.
install -d -m 0755 "$R/usr/local/sbin"
cat > "$R/usr/local/sbin/h713-wifi-recover" <<'WIFIRECOVER'
#!/bin/sh
# h713-wifi-recover: handle an AIC8800 WiFi firmware crash (DHDISDOWN).
#
# aic8800_fdrv times out on its firmware command->confirm handshake under load,
# prints "cmd timed-out / wlan error reset flow", marks its command queue
# CRASHED, and fires KOBJ_CHANGE with DHDISDOWN=1. The chip -- WiFi and BT both,
# it is one combo part -- stays dead until a full boot.
#
# There is NO safe in-place recovery. Unbinding and reloading the SDIO stack
# races the mmc/driver core into a NULL-deref Oops (bench-observed 2026-07-23,
# __device_attach_driver via mmc_rescan -> mmc_attach_sdio). Do not try again.
# A reboot is the only thing that revives the chip, so make the reboot reliable
# instead of trying to avoid it.
TAG=h713-wifi-recover
CONF=/etc/default/h713-wifi-recovery
AUTO_REBOOT=yes
GRACE_SECONDS=30
[ -r "$CONF" ] && . "$CONF"

say() {
    logger -t "$TAG" -- "$1" 2>/dev/null || true
    printf '%s: %s\n' "$TAG" "$1" > /dev/kmsg 2>/dev/null || true
}

say "AIC8800 WiFi firmware crashed (DHDISDOWN) -- WiFi/BT are down until reboot"

case "$AUTO_REBOOT" in
    [Yy]*|1|true) ;;
    *) say "auto-reboot disabled (AUTO_REBOOT=$AUTO_REBOOT in $CONF); staying down"; exit 0 ;;
esac

say "rebooting in ${GRACE_SECONDS}s to recover the chip; set AUTO_REBOOT=no in $CONF to disable"
sleep "$GRACE_SECONDS"
sync
say "requesting reboot now"
# A hung shutdown is bounded by RebootWatchdogSec (system.conf.d/h713-watchdog.conf):
# systemd arms the sunxi hardware watchdog across the shutdown, so a stuck unit
# cannot leave the board wedged the way it did on 2026-07-23.
exec systemctl reboot
WIFIRECOVER
chmod 0755 "$R/usr/local/sbin/h713-wifi-recover"

# Recovery policy, editable on a deployed unit without rebuilding an image.
cat > "$R/etc/default/h713-wifi-recovery" <<'EOF'
# Recovery policy for an AIC8800 WiFi firmware crash (DHDISDOWN).
#
# The chip cannot be revived in place -- only a reboot brings WiFi and BT back.
# AUTO_REBOOT=yes trades an interrupted session for unattended recovery, which
# is usually right for a headless or unattended unit; AUTO_REBOOT=no keeps the
# older behaviour (log only, wait for a human) and suits a projector that must
# never interrupt playback for a network fault.
AUTO_REBOOT=yes
GRACE_SECONDS=30
EOF

# Bound a hung shutdown in hardware. sunxi-wdt caps at 16s; systemd opens
# /dev/watchdog only for the shutdown transition, so this does NOT arm a runtime
# watchdog and cannot reset a healthy but busy system. Verified on hardware:
#   systemd-shutdown[1]: Using hardware watchdog 'sunxi-wdt' ... timeout of 16s.
# Set RuntimeWatchdogSec here too if you also want protection against a wedged
# running system -- but note 16s is the hardware maximum, which is tight.
install -d -m 0755 "$R/etc/systemd/system.conf.d"
cat > "$R/etc/systemd/system.conf.d/h713-watchdog.conf" <<'EOF'
[Manager]
RebootWatchdogSec=16s
EOF

# udev fires the handler on the driver's DHDISDOWN=1 uevent. The unit is
# triggered on demand (no [Install]/enable); systemd coalesces repeats.
install -d -m 0755 "$R/etc/udev/rules.d"
cat > "$R/etc/udev/rules.d/70-h713-wifi-crashlog.rules" <<'EOF'
# AIC8800 firmware crash -> aic8800_fdrv sends KOBJ_CHANGE with DHDISDOWN=1.
ACTION=="change", ENV{DHDISDOWN}=="1", TAG+="systemd", ENV{SYSTEMD_WANTS}+="h713-wifi-recover.service"
EOF
cat > "$systemd_dir/h713-wifi-recover.service" <<EOF
[Unit]
Description=Recover from an AIC8800 WiFi firmware crash (DHDISDOWN)
# Launched by udev (70-h713-wifi-crashlog.rules); not started at boot.

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/h713-wifi-recover
EOF

# Load the scanout carveout exporter at boot. Unlike cedrus and panfrost, which
# udev autoloads off their DT compatibles, this module is a plain misc device
# with no device table -- modinfo shows no alias at all -- so nothing will ever
# load it on its own, and everything that presents a frame through
# /dev/scanout-dmabuf fails without it. Its defaults are the working carveout
# (0x6c100000, 8 MiB = both buffers), so no options are needed.
install -d -m 0755 "$R/etc/modules-load.d"
cat > "$R/etc/modules-load.d/h713-video.conf" <<EOF
sunxi_scanout_dmabuf
EOF

# WiFi baseline capture tool. Shipped in the image because it has to run ON the
# board and STA WiFi cannot currently carry a file to it -- without this it
# would have to be pasted over an 11 KB/s serial console every time.
if [ -n "${WIFI_BASELINE_SRC:-}" ] && [ -f "${WIFI_BASELINE_SRC}" ]; then
  install -d -m 0755 "$R/usr/local/sbin"
  install -m 0755 "$WIFI_BASELINE_SRC" "$R/usr/local/sbin/wifi-baseline"
  echo "[customize] installed /usr/local/sbin/wifi-baseline"
fi

# Optional boot WiFi hotspot (AP). Enabled only when the build passed
# HOTSPOT_ENABLED=1 (i.e. local/hotspot.conf existed). A dedicated AP owns wlan0
# and DHCP, so mask the STA supplicant and the default dnsmasq.
if [ "${HOTSPOT_ENABLED:-0}" = 1 ]; then
  install -d -m 0755 "$R/etc/hostapd"
  # Band/width. The AIC8800D80 is a 1x1 dual-band VHT80 part, but the AP used to
  # be emitted as plain 802.11g -- 20 MHz, no HT, 54 Mbit/s -- which capped file
  # transfer at about 1.3 MB/s in and 2.4 MB/s out against an SDIO bus measured
  # at 24.4 MB/s. Measured on hardware, 128 MiB each way, SHA-256 exact and zero
  # SDIO faults in every case:
  #
  #   2.4 GHz 11g (old)   1.33 MB/s in   2.37 MB/s out
  #   2.4 GHz HT40        4.85 MB/s in   7.65 MB/s out
  #   5 GHz   VHT80      13.25 MB/s in  14.41 MB/s out
  #
  # HOTSPOT_BAND picks between them. 5 GHz is much faster and removes the
  # long-standing in/out asymmetry, but has shorter range, excludes 2.4-only
  # clients, and carries stricter regulatory obligations -- which matters here
  # because regulatory.db is not installed and the stack falls back to
  # permissive rules. 2.4 GHz HT40 is the conservative default.
  #
  # MAX-MPDU-11454 is NOT supported by this driver (it reports max 1, i.e.
  # 7991); asking for it makes hostapd fail with "Unable to setup interface".
  case "${HOTSPOT_BAND:-2.4}" in
    5)
      _hw=a
      _chan=${HOTSPOT_CHANNEL_5G:-36}
      # 80 MHz centre index: 42 covers channels 36-48 (UNII-1, non-DFS).
      _modes="ieee80211n=1
ieee80211ac=1
ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40]
vht_capab=[SHORT-GI-80][MAX-MPDU-7991]
vht_oper_chwidth=1
vht_oper_centr_freq_seg0_idx=${HOTSPOT_VHT_SEG0:-42}"
      ;;
    *)
      _hw=g
      _chan=$HOTSPOT_CHANNEL
      _modes="ieee80211n=1
ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40][MAX-AMSDU-7935]"
      ;;
  esac
  cat > "$R/etc/hostapd/hotspot.conf" <<EOF
interface=wlan0
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=$_hw
channel=$_chan
$_modes
wmm_enabled=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=$HOTSPOT_PASSPHRASE
EOF
  chmod 0600 "$R/etc/hostapd/hotspot.conf"
  cat > "$R/etc/default/h713-hotspot" <<EOF
HOTSPOT_IP=$HOTSPOT_IP
HOTSPOT_DHCP_START=$HOTSPOT_DHCP_START
HOTSPOT_DHCP_END=$HOTSPOT_DHCP_END
EOF
  install -d -m 0755 "$R/usr/local/sbin"
  cat > "$R/usr/local/sbin/h713-hotspot-up" <<'EOS'
#!/bin/sh
# Bring up the H713 WiFi hotspot (AP) on wlan0: hostapd + a DHCP-only dnsmasq.
CONF=/etc/hostapd/hotspot.conf
[ -f "$CONF" ] || exit 0
HOTSPOT_IP=192.168.4.1; HOTSPOT_DHCP_START=192.168.4.10; HOTSPOT_DHCP_END=192.168.4.100
[ -f /etc/default/h713-hotspot ] && . /etc/default/h713-hotspot
rfkill unblock wifi 2>/dev/null || true
i=0; while [ ! -e /sys/class/net/wlan0 ] && [ "$i" -lt 30 ]; do i=$((i + 1)); sleep 1; done
pkill -x hostapd 2>/dev/null || true
ip link set wlan0 down 2>/dev/null || true
ip addr flush dev wlan0 2>/dev/null || true
hostapd -B "$CONF" || exit 1
ip addr add "${HOTSPOT_IP}/24" dev wlan0
exec dnsmasq --keep-in-foreground --interface=wlan0 --bind-interfaces \
  --except-interface=lo \
  --dhcp-range="${HOTSPOT_DHCP_START},${HOTSPOT_DHCP_END},255.255.255.0,12h" \
  --dhcp-authoritative --port=0
EOS
  chmod 0755 "$R/usr/local/sbin/h713-hotspot-up"
  cat > "$systemd_dir/h713-hotspot.service" <<EOF
[Unit]
Description=H713 WiFi hotspot (hostapd + dnsmasq on wlan0)
After=systemd-modules-load.service
Wants=systemd-modules-load.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/h713-hotspot-up
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  ln -sfn ../h713-hotspot.service \
    "$systemd_dir/multi-user.target.wants/h713-hotspot.service"
  ln -sfn /dev/null "$systemd_dir/wpa_supplicant.service"
  ln -sfn /dev/null "$systemd_dir/dnsmasq.service"
  echo "[customize] boot hotspot enabled: SSID=$HOTSPOT_SSID ch=$HOTSPOT_CHANNEL ip=$HOTSPOT_IP"
fi

echo "[customize] configured key-only SSH, ttyS0 autologin, AIC8800 autoload + BT attach, scanout-dmabuf autoload"
