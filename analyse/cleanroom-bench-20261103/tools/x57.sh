#!/bin/sh
# 59 X5/X6/X7 in one bench boot with a source on the socket (port 1). Every first access is logged and synced.
cd /data/bench; L=/data/bench/x57-bench.log; B=/root/vp-bench; DB=/boot/mips/database.TSE
echo "=== X5"; uname -r; cat /proc/uptime
python3 rxdump.py $L bench-before ctl link link2
insmod /data/bench/spx4.ko port=1 hpd=3; echo "insmod rc=$?"; dmesg | grep spx4 | tail -4
dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed: no AUX access, stop"; exit 1; }
sync
sleep 3
python3 x5.py $L
python3 rxdump.py $L bench-after-x5 ctl link link2 aux
echo "=== X6"
python3 cap7.py $L keep
echo "=== X7"
$B apply --fmt nv16 --size 1920x1080 --pitch 1920 --luma 0x4b100000 --chroma 0x4b6fd000 --db $DB --log $L; echo "apply rc=$?"
$B verify scan --log $L; echo "scan rc=$?"
for k in 1 2 3; do $B verify hist --expect p1 --log $L | grep -E "INFO histogram sum|FAIL|PASS" | head -3; sleep 1; done
python3 - <<'PY'
import mmap, os
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
for a in (0x4b100000, 0x4b2ff000, 0x4b4fe000):
    m = mmap.mmap(fd, 1920 * 1080, mmap.MAP_SHARED, mmap.PROT_READ, offset=a)
    h = [0] * 32
    for y in range(0, 1080, 4):
        row = m[y * 1920:(y + 1) * 1920:4]
        for v in row:
            h[v >> 3] += 1
    print(f"slot {a:#x} luma histogram (32 bins of 8, every 4th pixel/line):", " ".join(f"{i}:{n}" for i, n in enumerate(h) if n))
PY
python3 -c "
import sys; sys.path.insert(0,'/data/bench'); from blog import rd
print('CAP 104 %08x a0c %08x 548 %08x | 0x05600070 %08x 0x084 %08x 0x320 %08x' % (rd(0x06940104), rd(0x06940a0c), rd(0x06940548), rd(0x05600070), rd(0x05600084), rd(0x05600320)))"
echo "=== end"
