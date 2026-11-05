#!/bin/sh
# docs/tools/h713-tv.md "Device test on a clean-stack boot" (hy320 7dcf8b48 / 924f0fdd), spec side 2026-11-04.
# Physical steps the owner would do are replaced as noted: loss/return by holding hot-plug low through the provider;
# "other mode" (720p at the source) and the remote's HOME key are not done.
B=/root/vp-bench
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
echo "=== boot"; cat /proc/cmdline; lsmod | grep -E 'afbd|hdmirx|cpu_comm|mips|msp'; echo "(vendor modules above, if any)"
r modprobe sun50i-h713-arisc
r insmod /root/h713_drm.ko bench=1
sleep 2
dmesg | grep -E 'hdmirx:|hdmi:' | head
grep -H . /sys/class/video4linux/video*/name
N=$(grep -l h713-hdmirx-clean /sys/class/video4linux/video*/name | head -1 | xargs dirname | xargs basename)
echo "node $N"
sleep 20
r systemctl --no-pager status "h713-tv@*" | head -8
journalctl -b -u "h713-tv@*" --no-pager | head -40 | cut -c1-220
echo "=== report only"
r h713-tv -n -d /dev/$N
echo "=== state"
h713-tv ctl status; sleep 2; h713-tv ctl status | grep -E "^stack|^hdmi|^frames|kernel|cpu_comm|hdcp"
echo "=== controls"
r h713-tv ctl list; r h713-tv ctl set saturation 0; r h713-tv ctl get saturation; r h713-tv ctl set saturation 50
echo "=== preset"
r h713-tv ctl preset cinema; h713-tv ctl status brief
echo "=== white balance"
r h713-tv ctl set wb_r_gain 400; $B dump pnl | grep -E "0x051c00dc"; r h713-tv ctl wb reset; $B dump pnl | grep -E "0x051c00dc"
echo "=== refusals"
for c in "cm" "aspect" "zoom in 2" "hdcp" "rpc THal_Vp_SetSource 3"; do echo "+ ctl $c"; h713-tv ctl $c; done
echo "=== gamma"
r h713-tv ctl set gamma 1; r h713-tv ctl set gamma 3; dmesg | grep "gamma:" | tail -2
echo "=== loss and return (hot-plug low 10 s through the provider, spec side)"
t0=$(cut -d' ' -f1 /proc/uptime); insmod /data/bench/spx4-73.ko port=1 hpd=2; dmesg | grep 'spx4: hpd' | tail -1; sleep 10
h713-tv ctl status | grep -E "^signal|^hdmi|^nosignal|^picture"
rmmod spx4; echo "hot-plug up at $(cut -d' ' -f1 /proc/uptime) (down at $t0)"; insmod /data/bench/spx4-73.ko port=1 hpd=1; rmmod spx4; sleep 15
h713-tv ctl status | grep -E "^signal|^hdmi|^picture"
dmesg | grep -E "hdmi: (capturing|no-signal|tmds|locked)" | tail -6 | cut -c1-160
journalctl -b -u "h713-tv@*" --no-pager | grep -E "signal|picture" | tail -6 | cut -c1-200
echo "=== replug"
r h713-tv ctl replug; sleep 8; dmesg | grep -E "S_EDID|-> locked|-> capturing" | tail -4 | cut -c1-160; h713-tv ctl status | grep -E "^signal|^hdmi"
echo "=== pages"
h713-osd ctl status | grep -E "launcher|page|overlay"; r h713-tv ctl volume 40; sleep 1; journalctl -b -u h713-osd --no-pager | grep -iE "alpha|waiting" | tail -3 | cut -c1-200
echo "=== client"
systemctl list-unit-files --no-pager | grep -iE "kodi|desktop" | head -3
r systemctl start h713-kodi; sleep 25; r h713-tv ctl warp; h713-warp ctl status | head -6
echo "=== warp ring (risk)"
r systemctl stop h713-kodi; sleep 3
r h713-warp ctl keystone set tl x 80; sleep 5; h713-warp ctl status | head -4; journalctl -b -u h713-warp --no-pager | tail -8 | cut -c1-200
r h713-warp ctl keystone set tl x 0
echo "=== way out"
r systemctl stop "h713-tv@*"; sleep 2; journalctl -b -u "h713-tv@*" --no-pager | tail -3 | cut -c1-200; dmesg | grep "hdmi:" | tail -2 | cut -c1-200
$B dump cap | grep -E "0x06940928|0x06940968"
echo "=== kernel"
dmesg | grep -ciE 'oops|bug:|warning:|call trace' | sed 's/^/kernel-trouble-lines=/'
echo "=== end"
