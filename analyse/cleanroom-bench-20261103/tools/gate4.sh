#!/bin/sh
cd /data/bench; L=/data/bench/gate4-bench.log
insmod /data/bench/spx4.ko port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
sleep 3
python3 x5.py $L > /dev/null
python3 x5g.py $L | cut -c12-220
