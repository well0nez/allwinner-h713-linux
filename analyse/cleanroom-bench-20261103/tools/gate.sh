#!/bin/sh
cd /data/bench; L=/data/bench/gate-bench.log
W="0x06e00000:0x100 0x068b0000:0x100 0x05700000:0x200 0x06700000:0x100 0x07001000:0x200 0x07010000:0x200 0x050c0000:0x100"
insmod /data/bench/spx4.ko port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
sleep 3
python3 x5.py $L > /dev/null
python3 wdump.py $L bench $W > /dev/null
echo "gate dumps done"; grep -c DUMP $L
