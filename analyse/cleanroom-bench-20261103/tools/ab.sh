#!/bin/sh
# ab.sh TAG: 70 §9 B1, B3, B4 on the bench boot (spec side, 2026-11-04). Every line to $L with a sync.
T=$1; D=/data/bench; A=$D/au; L=$A/ab-$T.log; K=/root/kms-test
mkdir -p $A; : > $L
say() { echo "$(cut -d' ' -f1 /proc/uptime) $*" >> $L; sync; }
say "== ab $T start $(uname -r) $(grep -o module_blacklist /proc/cmdline)"
modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1; say "insmod rc=$?"
( $K hdmi --secs 5 --hold 900 > $A/ab-$T-kms.txt 2>&1 & ); sleep 20
say "kms-test: $(grep -E 'hdmi_state' $A/ab-$T-kms.txt | tail -1)"
python3 $D/au.py $A/ab-$T-au.log dump B1a; say "B1 dump rc=$?"
python3 $D/au.py $A/ab-$T-au.log sel 2; say "B1 sel rc=$?"
python3 $D/au.py $A/ab-$T-trace.log trace 4; say "B1 trace rc=$?"
python3 $D/au.py $A/ab-$T-au.log state B1; say "B1 state rc=$?"
python3 $D/isl.py $A/ab-$T-isl.log up; say "B3 rc=$?"
python3 $D/isl.py $A/ab-$T-isl.log route; say "B4 route rc=$?"
python3 $D/isl.py $A/ab-$T-isl.log meter 20; say "B4 meter rc=$?"
python3 $D/au.py $A/ab-$T-au.log state B4; say "B4 state rc=$?"
python3 $D/au.py $A/ab-$T-au.log dump B4; say "after dump rc=$?"
say "kms-test after: $(grep -E 'hdmi_state|running' $A/ab-$T-kms.txt | tail -1); $(dmesg | grep 'hdmi: running' | tail -1 | cut -c1-150)"
say "== ab $T done"
