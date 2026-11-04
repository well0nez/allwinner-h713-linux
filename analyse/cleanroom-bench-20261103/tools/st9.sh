#!/bin/sh
# st9.sh TAG a|b|c : notes/impl-drm.md step 9 (clean e65a229) - one sleep with the clean module, spec side 2026-11-04.
# Guards as 60 §4: self-revert timer, h713-wifi restart after the wake; every line to $L with a sync.
T=$1; M=$2; L=/data/bench/st9-$T.log; B=/root/vp-bench; K=/root/kms-test; D=/data/bench
say() { echo "$(cut -d' ' -f1 /proc/uptime) $*" >> $L; sync; }
: > $L
rm -f /run/stb-ok; systemctl stop stb-guard.timer stb-guard.service 2>/dev/null
systemd-run --quiet --unit=stb-guard --on-active=600 /bin/sh -c '[ -e /run/stb-ok ] || { echo "stb-guard: no host contact, rebooting" > /dev/kmsg; sync; systemctl reboot || echo b > /proc/sysrq-trigger; }'
say "== st9 $T mode $M, $(uname -r)"
modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1; say "insmod rc=$?"
dmesg | grep -E "resume: TV-side" | tail -1 >> $L
case $M in
a) ( $K video p1 1920 1080 nv12 --rgb white --alpha 128 --hold 300 > $D/st9-$T-kms.txt 2>&1 & ); sleep 8
   $B verify hist --expect p1 --log $D/st9-$T-vpb.log | grep -E "INFO histogram sum" | head -1 | cut -c1-200 >> $L ;;
b) ( $K hdmi --secs 5 --hold 300 > $D/st9-$T-kms.txt 2>&1 & ); sleep 15
   say "kms-test: $(grep -E 'hdmi_state' $D/st9-$T-kms.txt | tail -1)" ;;
c) ( $K v4l2 --secs 60 --events 0 > $D/st9-$T-kms.txt 2>&1 & ); sleep 12 ;;
esac
n=$(dmesg | wc -l)
echo 1 > /sys/power/pm_print_times
echo 0 > /sys/class/rtc/rtc0/wakealarm; echo +20 > /sys/class/rtc/rtc0/wakealarm
say "suspend (RTC +20 s)"
echo mem > /sys/power/state; rc=$?
say "back rc=$rc"
( for k in 1 2 3; do systemctl restart h713-wifi; r=$?; sleep 8; st=$(cat /sys/class/net/wlan0/operstate 2>/dev/null)
	echo "$(cut -d' ' -f1 /proc/uptime) h713-wifi restart $k rc=$r wlan0 $st" >> $L; sync; [ "$st" = up ] && break; done ) &
( dmesg -w | tail -n +$((n + 1)) | grep --line-buffered -E "h713-drm|hdmi|hdmirx" >> $L ) &
d=$!
sleep 20
case $M in
a) $B verify scan --log $D/st9-$T-vpb.log | grep -E "FAIL|verify scan:" >> $L
   $B verify hist --expect p1 --log $D/st9-$T-vpb.log | grep -E "INFO histogram sum" | head -1 | cut -c1-200 >> $L ;;
b) say "kms-test after: $(grep -E 'hdmi_state|FAIL' $D/st9-$T-kms.txt | tail -2 | tr '\n' '|')"
   $B verify hist --log $D/st9-$T-vpb.log 2>/dev/null | grep -E "INFO histogram sum" | head -1 | cut -c1-200 >> $L ;;
c) sleep 30; say "v4l2: $(grep -E 'PASS|FAIL' $D/st9-$T-kms.txt | tr -s ' ' | cut -c1-160 | tr '\n' '|')" ;;
esac
kill $d
say "== st9 $T: done"
