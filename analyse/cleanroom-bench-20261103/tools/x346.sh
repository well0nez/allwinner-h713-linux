#!/bin/sh
# 59 X3, X4, X6 in one bench boot (no source signal). Each block's first read is logged and synced (rxdump.py).
cd /data/bench; L=/data/bench/x346-bench.log
echo "=== X3"; uname -r; cat /proc/uptime
lsmod | grep -iE "arisc|hdmirx|mips|cpu_comm" ; sync
python3 rxdump.py $L bench tvtop ppu ccu rprcm cap tvfe dtop
python3 rxdump.py $L bench ctl
python3 rxdump.py $L bench link link2
python3 rxdump.py $L bench dmx
echo "X3 reads done"; sync
echo "=== X4"
insmod /data/bench/spx4.ko port=1 hpd=3; echo "insmod rc=$?"; dmesg | grep spx4; sync
sleep 2
python3 rxdump.py $L bench-after-edid rprcm aux
python3 /root/peek.py 0x07091014; python3 /root/peek.py 0x07091b04
echo "=== X6"
python3 cap6.py $L
python3 cap6.py $L tvtop504
grep -E "CAP6" $L | cut -c12-400
echo "=== end"
