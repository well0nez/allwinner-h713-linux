#!/bin/sh
# 59 X6/X7 on a bench boot whose receiver is already locked (x5w.sh).
cd /data/bench; L=/data/bench/x67-bench.log; B=/root/vp-bench; DB=/boot/mips/database.TSE
echo "=== X6"
python3 cap7.py $L keep | grep -E "before|programmed,|outputs on \+(0.5|3.0)" | cut -c12-420
python3 -c "
import sys,time; sys.path.insert(0,'/data/bench'); from blog import rd
for i in range(5):
    print('CAP 104 %08x a0c %08x 548 %08x 874 %08x | fe64 %08x' % (rd(0x06940104), rd(0x06940a0c), rd(0x06940548), rd(0x06940874), rd(0x0514fe64))); time.sleep(0.2)"
echo "=== X7"
$B apply --fmt nv16 --size 1920x1080 --pitch 1920 --luma 0x4b100000 --chroma 0x4b6fd000 --db $DB --log $L > /data/bench/x7-apply.txt 2>&1; echo "apply rc=$?"; tail -2 /data/bench/x7-apply.txt | cut -c1-200
$B verify scan --log $L | tail -1
for k in 1 2 3; do $B verify hist --expect p1 --log $L | grep -E "INFO histogram sum" | head -1 | cut -c1-300; sleep 1; done
python3 - <<'PY'
import mmap, os
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
for a in (0x4b100000, 0x4b2ff000, 0x4b4fe000):
    m = mmap.mmap(fd, 1920 * 1080, mmap.MAP_SHARED, mmap.PROT_READ, offset=a)
    h = [0] * 32
    for y in range(0, 1080, 4):
        for v in m[y * 1920:(y + 1) * 1920:4]:
            h[v >> 3] += 1
    print(f"slot {a:#x} luma hist (32 bins of 8):", " ".join(f"{i}:{n}" for i, n in enumerate(h) if n))
PY
