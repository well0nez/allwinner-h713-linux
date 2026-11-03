#!/bin/sh
cd /data/bench; L=/data/bench/gate3-bench.log
python3 wdump.py $L bench 0x02000000:0x400 0x07022000:0x100 > /dev/null
insmod /data/bench/spx4.ko port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
sleep 3
python3 x5.py $L > /dev/null
python3 x5e.py $L | cut -c12-200
