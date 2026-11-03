#!/bin/sh
# 59 X5 vertical lock attempt in one bench boot: X5 replay (link opened), second hot-plug, the firmware's lock-step writes.
cd /data/bench; L=/data/bench/x5v-bench.log
insmod /data/bench/spx4.ko port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
sleep 3
python3 x5.py $L > /dev/null; echo "x5 done"
rmmod spx4; insmod /data/bench/spx4.ko port=1 hpd=3; echo "second hot-plug"; sleep 2
python3 x5j.py $L watch-only | grep SIGNS | cut -c12-260 | tail -3
python3 x5j.py $L | grep -E "SIGNS|W8" | cut -c12-260
rmmod spx4; insmod /data/bench/spx4.ko port=1 hpd=3; echo "third hot-plug after the lock-step writes"; sleep 2
python3 x5j.py $L watch-only | grep SIGNS | cut -c12-260
