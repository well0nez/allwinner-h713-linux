#!/bin/sh
# q1all.sh LOG : the whole Q1 path so far in one go (bench boot), then a full snapshot
L=$1; cd /data/bench
python3 q1.py $L obs pre >/dev/null
python3 q1.py $L fill white >/dev/null
python3 q1.py $L prog | grep LATCH
for t in INIT_VPANEL INIT_VPROC INIT_VNR INIT_VDEINT DBUS_MP_RST_PROJECTOR; do python3 q1init.py $L $t | grep applied; done
python3 q1.py $L wr 0x0514fe08 0x04640897 PROC_LOCK totals >/dev/null
python3 q1.py $L wr 0x051cfe08 0x04640897 PNL_LOCK totals >/dev/null
python3 q1.py $L sel >/dev/null
python3 q1.py $L relatch | grep LATCH
python3 q1.py $L vsync 1 | grep VSYNC
python3 snap.py $L bench-after-inits >/dev/null
echo snap done
