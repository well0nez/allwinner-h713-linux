#!/bin/sh
cd /data/bench; L=/data/bench/x5w-bench.log
insmod /data/bench/spx4.ko port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
sleep 3
python3 x5.py $L | grep -E "SIGNS (after step 1b|after H5 \+4)|step 1b" | cut -c12-330
python3 x5j.py $L watch-only | grep SIGNS | cut -c12-200 | tail -2
rmmod spx4; insmod /data/bench/spx4.ko port=1 hpd=3; echo "second hot-plug"; sleep 2
python3 x5j.py $L watch-only | grep SIGNS | cut -c12-200
