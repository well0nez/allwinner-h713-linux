#!/bin/sh
# st15.sh TAG a|b|c : notes/impl-drm.md step 9 (clean 3d383b1, spec 60 v4) - one sleep with the clean module, spec side
# 2026-11-04 (round 15). Guards as 60 §4: self-revert timer, h713-wifi restart after the wake; every line to $L, synced.
T=$1; M=$2; L=/data/bench/st15-$T.log; B=/root/vp-bench; K=/root/kms-test; D=/data/bench
say() { echo "$(cut -d' ' -f1 /proc/uptime) $*" >> $L; sync; }
run() { say "+ $*"; "$@" > $D/st15-$T-cmd.txt 2>&1; rc=$?; cut -c1-220 $D/st15-$T-cmd.txt >> $L; say "rc=$rc"; }
: > $L
rm -f /run/stb-ok; systemctl stop stb-guard.timer stb-guard.service 2>/dev/null
systemd-run --quiet --unit=stb-guard --on-active=600 /bin/sh -c '[ -e /run/stb-ok ] || { echo "stb-guard: no host contact, rebooting" > /dev/kmsg; sync; systemctl reboot || echo b > /proc/sysrq-trigger; }'
say "== st15 $T mode $M, $(uname -r), module $(sha256sum /root/h713_drm.ko | cut -c1-16), kms-test $(sha256sum $K | cut -c1-16)"
modprobe sun50i-h713-arisc
if [ -n "$PREINIT" ]; then
	insmod /root/old13/h713_drm.ko bench=1 restore_logo=1; say "pre-init: round-13 module insmod rc=$?"
	say "pre-init: $(/root/old13/kms-test hdmi --secs 3 --wait 25 2>&1 | grep -E 'hdmi_state' | tail -1)"
	rmmod h713_drm; say "pre-init: rmmod rc=$?, RX_CTL 0x8fc $(python3 /root/peek.py 0x068008fc 1)"
fi
insmod /root/h713_drm.ko bench=1 restore_logo=1; say "insmod rc=$?"
dmesg | grep -E "resume: |hdmi: TV top" | tail -3 >> $L
case $M in
a) ( $K video p1 1920 1080 nv12 --rgb white --alpha 128 --hold 300 > $D/st15-$T-kms.txt 2>&1 & ); sleep 8
   $B verify hist --expect p1 --log $D/st15-$T-vpb.log | grep -E "INFO histogram sum" | head -1 | cut -c1-200 >> $L ;;
b|c) ( $K hdmi --secs 5 --hold 300 > $D/st15-$T-kms.txt 2>&1 & ); sleep 15
   say "kms-test: $(grep -E 'hdmi_state' $D/st15-$T-kms.txt | tail -1)" ;;
esac
n=$(dmesg | wc -l)
echo 1 > /sys/power/pm_print_times
echo 0 > /sys/class/rtc/rtc0/wakealarm; echo +20 > /sys/class/rtc/rtc0/wakealarm
say "suspend (RTC +20 s)"
echo mem > /sys/power/state; rc=$?
say "back rc=$rc"
( for k in 1 2 3; do systemctl restart h713-wifi; r=$?; sleep 8; st=$(cat /sys/class/net/wlan0/operstate 2>/dev/null)
	echo "$(cut -d' ' -f1 /proc/uptime) h713-wifi restart $k rc=$r wlan0 $st" >> $L; sync; [ "$st" = up ] && break; done ) &
( dmesg -w | tail -n +$((n + 1)) | grep --line-buffered -E "h713-drm|hdmi|hdmirx" | grep --line-buffered -v "PM: " >> $L ) &
d=$!
sleep 20
case $M in
a) $B verify scan --log $D/st15-$T-vpb.log | grep -E "FAIL|verify scan:" >> $L
   $B verify hist --expect p1 --log $D/st15-$T-vpb.log | grep -E "INFO histogram sum" | head -1 | cut -c1-200 >> $L
   pkill -x kms-test ;;
b) say "kms-test hold after the wake: $(grep -E 'hdmi_state|FAIL' $D/st15-$T-kms.txt | tail -2 | tr '\n' '|')"
   say "hdmi_state $(cat /sys/class/drm/card*/device/hdmi_state 2>/dev/null | tr '\n' ' ')"
   pkill -x kms-test; sleep 2
   run $K hdmi --secs 5 --wait 5
   run $K v4l2 --wait 5 --events 0 ;;
c) pkill -x kms-test; sleep 2
   rmmod h713_drm; say "rmmod rc=$?"
   say "TV top before the reload: $(python3 /root/peek.py 0x06e00000 3 | tr '\n' ' ')"
   insmod /root/h713_drm.ko bench=1 restore_logo=1; say "insmod after the wake rc=$?"
   sleep 2
   run $K video p1 1920 1080 nv12 --hold 6
   run $K hdmi --secs 5 --wait 5
   run $K v4l2 --wait 5 --events 0 ;;
esac
sleep 3
kill $d
say "kernel trouble lines: $(dmesg | grep -ciE 'oops|bug:|warning:|call trace|soft lockup|hung task')"
say "== st15 $T: done"
