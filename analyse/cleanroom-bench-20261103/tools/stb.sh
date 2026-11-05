#!/bin/sh
# stb.sh TAG SECS MODE STEPS: one real standby on the bench boot (spec side, 2026-11-04).
# MODE: none (no module) | idle (module loaded, no client) | hdmi (kms-test hdmi running through the sleep) |
#       reload (module and kms-test hdmi before; both stopped and the module unloaded before the sleep; after the
#       wake and the re-init STEPS: insmod and kms-test hdmi again)
# STEPS: rsm.py steps after the wake (e.g. ccu,tvtop,cap) or "-" for none.
# Snapshots: "safe" = CCU page, PPU, TVTOP, R_CCU (readable in every state measured); "full" = vp-bench dump all + the
# receiver windows (8-bit) + CAP. After the wake only "safe" is taken before the re-init. Every line -> $L with a sync;
# the kernel log after the wake is streamed there too.
T=${1:-s1}; SECS=${2:-20}; MODE=${3:-none}; STEPS=${4:--}
L=/data/bench/stb-$T.log; B=/root/vp-bench; K=/root/kms-test; D=/data/bench
say() { echo "$(cut -d' ' -f1 /proc/uptime) $*" >> $L; sync; }
safe() { python3 $D/wdump.py $D/stb-$T-safe-$1.log $1 0x02001000:0x1000 0x07001000:0x240 0x06e00000:0x40 0x07010000:0x400 0x02000000:0x400 0x07022000:0x100 0x07020c00:0x100 0x04002000:0x400 0x04003000:0x400 0x03000000:0x100 > /dev/null 2>&1; say "SAFE $1 rc=$?"; }
full() {
	$B dump all --log $D/stb-$T-dump-$1.log > $D/stb-$T-dump-$1.txt 2>&1; say "FULL $1 vp-bench rc=$?"
	python3 $D/rxdump.py $D/stb-$T-rx-$1.log $1 ctl link link2 > /dev/null 2>&1; say "FULL $1 rx rc=$?"
	grep -E "h713-drm" /proc/interrupts | tr -s ' ' >> $L
	python3 -c "
import sys,time; sys.path.insert(0,'$D'); from blog import rd
v=[rd(0x05600310) for i in range(2000)]; t=[rd(0x05880000) for i in range(3)]
a=rd(0x051c0174); time.sleep(0.05); b=rd(0x051c0174)
print('RASTER SCANOUT 0x310 bit 21 clear in %d of 2000 reads; TCON 0x05880000 %s; PNL 0x174 %08x -> %08x' % (sum(1 for x in v if not x & 0x200000), ' '.join('%08x' % x for x in t), a, b))" >> $L 2>&1
	sync
}
: > $L
# Self-revert: unless the host disarms it (touch /run/stb-ok, or stop stb-guard.timer), the device reboots into the
# normal boot 600 s of awake time (CLOCK_MONOTONIC, the sleep not counted) after this point - a lost Wi-Fi after the
# wake never needs the owner. Disarm: ssh ... 'touch /run/stb-ok; systemctl stop stb-guard.timer'.
rm -f /run/stb-ok
systemctl stop stb-guard.timer stb-guard.service 2>/dev/null
systemd-run --quiet --unit=stb-guard --on-active=600 /bin/sh -c '[ -e /run/stb-ok ] || { echo "stb-guard: no host contact, rebooting" > /dev/kmsg; sync; systemctl reboot || echo b > /proc/sysrq-trigger; }'
say "== stb $T: start, $(uname -r), mode $MODE, steps $STEPS, gate word $(python3 /root/peek.py 0x07090114)"
if [ "$MODE" = reload2 ]; then
	modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1 tvtop_init=none; say "insmod tvtop_init=none rc=$?"
elif [ "$MODE" != none ]; then
	lsmod | grep -q '^h713_drm' || { modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1; say "insmod rc=$?"; }
fi
if [ "$MODE" = vpb ] || [ "$MODE" = vpbdis ]; then
	$B frame P1 0x4c000000 1920 1080 nv12 --log $D/stb-$T-vpb.log > /dev/null 2>&1
	offs=""; for o in $VPBOFF; do offs="$offs --off $o"; done; say "vp-bench apply$offs"
	$B apply --db /boot/mips/database.TSE --luma 0x4c000000 $offs --log $D/stb-$T-vpb.log 2>&1 | tail -1 >> $L
	$B verify hist --expect p1 --log $D/stb-$T-hist.log | grep -E "PASS P1|FAIL" | head -1 >> $L
	if [ "$MODE" = vpbdis ]; then $B apply --mode disable --log $D/stb-$T-vpb.log 2>&1 | tail -1 >> $L; say "stage 2 disabled before the sleep"; fi
fi
if [ "$MODE" = video ]; then
	( $K video p1 1920 1080 nv12 --hold 900 > $D/stb-$T-kms.txt 2>&1 & ); sleep 6
	$B verify hist --expect p1 --log $D/stb-$T-hist.log | grep -E "PASS P1|FAIL" | head -2 >> $L
fi
if [ "$MODE" = hdmi ] || [ "$MODE" = reload ] || [ "$MODE" = reload2 ]; then
	( $K hdmi --secs 5 --hold 900 > $D/stb-$T-kms.txt 2>&1 & ); sleep 12
	say "kms-test: $(grep -E 'hdmi_state' $D/stb-$T-kms.txt | tail -1)"
fi
[ "$MODE" = reload2 ] && { pkill -x kms-test; sleep 2; say "kms-test stopped; the module stays loaded through the sleep"; }
safe before; full before
if [ "$MODE" = reload ]; then pkill -x kms-test; sleep 1; rmmod h713_drm; say "rmmod rc=$?"; safe before-rmmod; fi
[ -n "$PRE" ] && { python3 $D/rsm.py $D/stb-$T-pre.log $D/stb-$T-safe-before.log "$PRE" > /dev/null 2>&1; say "pre-sleep rsm $PRE rc=$?"; safe before-pre; }
[ -n "$PMTEST" ] && { echo $PMTEST > /sys/power/pm_test; say "pm_test $(cat /sys/power/pm_test)"; }
echo 1 > /sys/power/pm_print_times; echo 1 > /sys/power/pm_debug_messages
n=$(dmesg | wc -l)
echo 0 > /sys/class/rtc/rtc0/wakealarm; echo +$SECS > /sys/class/rtc/rtc0/wakealarm
say "suspend (RTC +$SECS s)"
echo mem > /sys/power/state; rc=$?
say "back rc=$rc"
( for k in 1 2 3; do systemctl restart h713-wifi; r=$?; sleep 8
	st=$(cat /sys/class/net/wlan0/operstate 2>/dev/null)
	echo "$(cut -d' ' -f1 /proc/uptime) h713-wifi restart $k rc=$r wlan0 $st" >> $L; sync
	[ "$st" = up ] && break; done ) &
( dmesg -w | tail -n +$((n + 1)) >> $L ) &
d=$!
sleep 2
safe after
ref=$D/stb-$T-safe-before.log; [ "$MODE" = reload ] && ref=$D/stb-$T-safe-before-rmmod.log
[ "$STEPS" != - ] && { python3 $D/rsm.py $D/stb-$T-rsm.log $ref "$STEPS" > /dev/null 2>&1; say "rsm $STEPS rc=$?"; safe after-rsm; }
case "$STEPS" in *cap*) full after ;; esac
if [ "$MODE" = reload ] || [ "$MODE" = reload2 ]; then
	if [ "$MODE" = reload2 ]; then
		dmesg | grep h713-drm | grep -E "suspend|resume|commit:|hdmi:" | tail -6 >> $L
		rmmod h713_drm; say "rmmod after the wake rc=$?"
		say "TV top before the reload: $(python3 /root/peek.py 0x06e00000 3 | tr '\n' ' ')"
	fi
	modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1; say "insmod after the wake rc=$?"
	( $K hdmi --secs 10 --hold 60 > $D/stb-$T-kms2.txt 2>&1 & ); sleep 25
	say "kms-test after: $(grep -E 'hdmi_state|PASS|FAIL' $D/stb-$T-kms2.txt | tr -s ' ' | tr '\n' '|' | cut -c1-900)"
	full after-reload
fi
if [ "$MODE" = video ] || [ "$MODE" = hdmi ]; then
	sleep 5
	dmesg | grep -E "h713-drm" | tail -n +1 | grep -E "suspend|resume|commit:|hdmi:|stall" | tail -12 >> $L
	$B verify hist --expect p1 --log $D/stb-$T-hist.log | grep -E "PASS P1|FAIL|INFO histogram sum" | head -3 >> $L
	full after-module
fi
sleep 5
kill $d
say "== stb $T: done"
