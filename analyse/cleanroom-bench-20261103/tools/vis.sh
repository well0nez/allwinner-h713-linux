#!/bin/sh
# visual window, bench states 2-5 (7.3.1-rustbench, h713_drm round-8 module). vis.sh 2|3|4|5
K=/root/kms-test; B=/root/vp-bench; L=/root/vis.log
case "$1" in
2) insmod /root/h713_drm.ko bench=1 restore_logo=1 align_cal=1; echo "insmod rc=$?"
   (nohup $K video p1 1920 1080 nv12 --hold 900 > /root/vis-2.txt 2>&1 &); sleep 5
   $B verify hist --expect p1 --log $L | grep -E "PASS|FAIL" | tail -2; dmesg | grep -E "commit:|video:" | tail -2 ;;
3) pkill -f "kms-test video"; sleep 1
   (nohup $K video p1 1920 1080 nv12 --rgb white --alpha 128 --hold 900 > /root/vis-3.txt 2>&1 &); sleep 8
   dmesg | grep -E "align" | tail -2; $B verify hist --expect p1 --log $L | grep -E "INFO histogram sum" | head -1 ;;
4) pkill -f "kms-test video"; sleep 1; rmmod h713_drm; echo "rmmod rc=$?"; dmesg | grep -E "unload|flip events" | tail -3
   $B dump scanout --log $L | grep -E "0x05600140|0x05600178"; $B dump mix --log $L | grep 0x058c0000 ;;
5) sh /data/bench/hdmi-clean.sh ;;
esac
