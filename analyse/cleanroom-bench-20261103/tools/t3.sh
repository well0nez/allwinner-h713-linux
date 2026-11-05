#!/bin/sh
# Round 10 follow-up on the same bench boot: T3-08 done right (kill the holder first), then T3-05 with the loss made by
# the spec side: hot-plug held low through the provider for 10 s (the owner cannot unplug), then up again.
K=/root/kms-test; B=/root/vp-bench; L=/root/drm-bench.log
echo "=== T3-08"
$K hdmi --secs 5 --hold 30 > /root/t308b.txt 2>&1 & P=$!; sleep 20
kill $P; wait $P 2>/dev/null; echo "holder killed"
rmmod h713_drm; echo "rmmod rc=$?"
dmesg | grep -E 'hdmi:|unload' | tail -4
$B dump cap --log $L | grep -E "0x06940928|0x06940968|0x06940104"
modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1; echo "insmod rc=$?"
T0=$(cut -d' ' -f1 /proc/uptime)
$K hdmi --secs 10 --wait 40 | grep -E "hdmi_state|PASS|FAIL" | cut -c1-160
dmesg | grep 'hdmi:' | tail -9 | cut -c1-220
echo "=== T3-05 (loss by hot-plug low for 10 s, spec side)"
$K hdmi --secs 5 --hold 90 > /root/t305.txt 2>&1 & P=$!; sleep 15
echo "hot-plug down at $(cut -d' ' -f1 /proc/uptime)"
insmod /data/bench/spx4-73.ko port=1 hpd=2; dmesg | grep spx4 | tail -2 | cut -c1-120
sleep 10
echo "dump during loss:"; $B dump cap --log $L | grep -E "0x06940928|0x06940968"
rmmod spx4
echo "hot-plug up at $(cut -d' ' -f1 /proc/uptime)"
insmod /data/bench/spx4-73.ko port=1 hpd=1; dmesg | grep spx4 | tail -1 | cut -c1-120; rmmod spx4
sleep 30
dmesg | grep 'hdmi:' | tail -14 | cut -c1-220
kill $P; wait $P 2>/dev/null
