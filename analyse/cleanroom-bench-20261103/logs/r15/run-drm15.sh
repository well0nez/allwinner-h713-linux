#!/bin/sh
# notes/impl-drm.md step 8 (quick regression) and step 8b as written (clean repo 3d383b1, round 15, 7.3.1-rustbench).
B=/root/vp-bench; K=/root/kms-test; L=/root/drm-bench.log
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
echo "=== 0"; uname -r; sha256sum /root/h713_drm.ko /root/kms-test /root/vp-bench; modinfo /root/h713_drm.ko | grep vermagic
r modprobe sun50i-h713-arisc
r insmod /root/h713_drm.ko bench=1 restore_logo=1
dmesg | grep -E 'hdmi:|hdmirx:'
echo "=== 8 quick"
r $K hdmi --secs 10 --wait 20
echo "=== 8b v4l2 alone"
sleep 3
r $K v4l2 --secs 10
dmesg | grep -E 'hdmi:|hdmirx:' | tail -20
echo "=== 8b v4l2 with the CRTC on the input"
$K hdmi --secs 5 --hold 40 > /root/r15-hdmi-hold.txt 2>&1 &
sleep 15; r $K v4l2 --secs 10 --events 0; wait; echo "hdmi hold:"; cat /root/r15-hdmi-hold.txt
dmesg | grep -E 'hdmi:|hdmirx:' | tail -20
r $B dump cap --log $L
echo "=== kernel (soak notes)"
dmesg | grep -ciE 'oops|bug:|warning:|call trace|rcu.*stall|soft lockup|hung task' | sed 's/^/kernel-trouble-lines=/'
dmesg | grep -iE 'oops|bug:|warning:|call trace' | head -10
echo "=== end"
