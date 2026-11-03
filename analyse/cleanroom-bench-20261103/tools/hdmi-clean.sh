#!/bin/sh
# Visual state 5 / 59 X5-X7 in one command (bench boot, firmware never started): EDID + hot-plug through the ARISC,
# receiver bring-up (x5.py), capture into an own ring (cap7.py), channel 0 on ring slot 0 (vp-bench, NV16 1920x1080).
cd /data/bench; L=/data/bench/hdmi-clean.log; B=/root/vp-bench; DB=/boot/mips/database.TSE
case "$(uname -r)" in 7.3*) K=/data/bench/spx4-73.ko ;; *) K=/data/bench/spx4.ko ;; esac
rmmod spx4 2>/dev/null; insmod $K port=1 hpd=3
dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed: no AUX access, stop"; exit 1; }
sync; sleep 3
python3 x5.py $L | grep -E "SIGNS after H5 \+4" | cut -c12-200
python3 cap7.py $L keep | grep -E "top word|outputs on \+3" | cut -c12-330
$B apply --fmt nv16 --size 1920x1080 --pitch 1920 --luma 0x4b100000 --chroma 0x4b6fd000 --db $DB --log $L | tail -1
$B verify hist --expect p1 --log $L | grep -E "INFO histogram sum" | head -1 | cut -c1-300
python3 -c "
import sys; sys.path.insert(0,'/data/bench'); from blog import rd
print('CAP 104 %08x a0c %08x 548 %08x' % (rd(0x06940104), rd(0x06940a0c), rd(0x06940548)))"
