#!/bin/sh
# boot E: aligned RGB-over-video state, then Q-ALN-1 (m-line horizontal totals), Q-ALN-2 (re-enable, 720p), Q-DRM-6 (pitch)
cd /data/bench; L=/data/bench/e-bench.log; B=/root/vp-bench; DB=/boot/mips/database.TSE
sh q1all.sh $L 2>&1 | grep VSYNC
python3 minimize.py $L all 2>&1 | grep TEST | cut -c12-100
python3 r10.py $L setup | grep STATE
python3 align3.py $L > /dev/null; grep -E "ALIGN3 (start|done)" $L | tail -2
python3 r10.py $L state | grep STATE
python3 aln1.py $L > /dev/null; grep ALN1 $L
python3 align3.py $L > /dev/null; grep -E "ALIGN3 done" $L | tail -1
python3 r10.py $L state | grep STATE
echo "=== Q-ALN-2 a: full re-enable at 1920x1080 (clean composer, measured pacing)"
$B frame black 0x4c000000 1920 1080 nv12 --log $L.vp >/dev/null
$B apply --db $DB --luma 0x4c000000 --log $L.vp | grep -E "^done"
python3 r10.py $L setup | grep STATE
python3 meas.py $L | grep MEAS
echo "=== Q-ALN-2 b: full enable at 1280x720 scaled"
$B frame black 0x4c000000 1280 720 nv12 --log $L.vp >/dev/null
$B apply --db $DB --size 1280x720 --luma 0x4c000000 --log $L.vp | grep -E "^done"
python3 r10.py $L setup | grep STATE
python3 meas.py $L | grep MEAS
python3 align3.py $L > /dev/null; grep -E "ALIGN3 (start|done)" $L | tail -2
python3 r10.py $L state | grep STATE
echo "=== Q-ALN-2 c: back to 1920x1080"
$B frame black 0x4c000000 1920 1080 nv12 --log $L.vp >/dev/null
$B apply --db $DB --luma 0x4c000000 --log $L.vp | grep -E "^done"
python3 r10.py $L setup | grep STATE
python3 meas.py $L | grep MEAS
python3 align3.py $L > /dev/null; grep -E "ALIGN3 (start|done)" $L | tail -2
echo "=== Q-DRM-6"
python3 pitch.py $L > /dev/null; grep PITCH $L
echo "=== end"
