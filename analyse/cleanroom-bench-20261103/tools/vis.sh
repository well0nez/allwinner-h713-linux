#!/bin/sh
# visual window, bench states 2-5 (7.3.1-rustbench, h713_drm stage-3 module f907a5a7..). vis.sh 2|3|4|5
# 2 P1 colour bars; 3 P1 under a white RGB plane at alpha 128 after align_cal=1; 4 rmmod: the boot logo back;
# 5 the HDMI source through the clean driver (kms-test hdmi). Each state stays until the next command.
K=/root/kms-test; B=/root/vp-bench; L=/root/vis.log
stop() { pkill -x kms-test 2>/dev/null; rm -f /root/vis.pid; sleep 1; }
load() { lsmod | grep -q "^h713_drm" || { modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1 "$@"; echo "insmod rc=$?"; }; }
case "$1" in
2) stop; rmmod h713_drm 2>/dev/null; load align_cal=1
   (nohup $K video p1 1920 1080 nv12 --hold 900 > /root/vis-2.txt 2>&1 & echo $! > /root/vis.pid); sleep 5
   $B verify hist --expect p1 --log $L | grep -E "PASS|FAIL" | tail -2; dmesg | grep -E "commit:" | tail -1 ;;
3) stop; load align_cal=1
   (nohup $K video p1 1920 1080 nv12 --rgb white --alpha 128 --hold 900 > /root/vis-3.txt 2>&1 & echo $! > /root/vis.pid); sleep 8
   dmesg | grep -E "align \(|align calibration" | tail -2; $B verify hist --expect p1 --log $L | grep -E "INFO histogram sum" | head -1 ;;
4) stop; rmmod h713_drm; echo "rmmod rc=$?"; dmesg | grep -E "unload" | tail -2
   $B dump scanout --log $L | grep -E "0x05600140|0x05600178"; $B dump mix --log $L | grep 0x058c0000 ;;
5) stop; load
   (nohup $K hdmi --secs 5 --hold 900 > /root/vis-5.txt 2>&1 & echo $! > /root/vis.pid); sleep 25
   grep -E "hdmi_state|PASS|FAIL" /root/vis-5.txt | cut -c1-140; dmesg | grep "hdmi:" | tail -3 | cut -c1-200 ;;
esac
