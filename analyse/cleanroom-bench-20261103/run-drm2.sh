#!/bin/sh
# notes/impl-drm.md "Bench procedure (spec side), re-run" (clean repo fb4e236), run as written. Additions only: each
# command's exit code is echoed, 0xL/0xC are filled from the kernel log line the procedure names, section markers,
# and the step-5 commands of the first run (the procedure says "as the first run").
B=/root/vp-bench; K=/root/kms-test; L=/root/drm-bench.log
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
lc() { dmesg | grep 'video:' | tail -1 | sed -n 's/.*luma \(0x[0-9a-f]*\) chroma \(0x[0-9a-f]*\).*/\1 \2/p'; }

echo "=== 0 boot and files"; uname -r; cat /proc/cmdline; grep -i cma /proc/meminfo
sha256sum /root/h713_drm.ko /root/kms-test /root/vp-bench /lib/firmware/h713/database.TSE /boot/mips/database.TSE
r $B dump scanout --log $L; r $B dump mix --log $L; r $B dump tcon --log $L

echo "=== 1 load"
r insmod /root/h713_drm.ko bench=1 restore_logo=1
dmesg | grep -E 'h713|drm'
r $K info
r $B dump scanout --log $L; r $B dump mix --log $L; r $B dump tcon --log $L

echo "=== 2 RGB plane, vblank, flips, pitch"
$K rgb grey --hold 10 & sleep 2
r $B dump scanout --log $L
wait; echo "rgb grey rc=$?"
r $K vblank 656
r $K rgb white --flip 3930 --alt black --hold 0
$K video black 1920 1080 nv12 --rgb white --alpha 255 --hold 8 & sleep 4
r $B verify hist --expect white --log $L
wait; echo "pitch 7680 rc=$?"
$K video black 1920 1080 nv12 --rgb white --alpha 255 --rgb-pitch 8192 --hold 8 & sleep 4
r $B dump scanout --log $L
r $B verify hist --expect white --log $L
wait; echo "pitch 8192 rc=$?"

echo "=== 3 video T1"
$K video p1 1920 1080 nv12 --hold 30 & sleep 4
dmesg | grep -E 'video:|commit:|raster stall|0x0' | tail -8
set -- $(lc); echo "luma=$1 chroma=$2"
r $B verify t1 --luma $1 --chroma $2 --log $L
r $B verify scan --log $L
wait; echo "video p1 rc=$?"
for p in white black p3 p1; do
  $K video $p 1920 1080 nv12 --hold 8 & sleep 4
  case $p in p3) e=grey;; *) e=$p;; esac
  r $B verify hist --expect $e --log $L
  wait; echo "video $p rc=$?"
done
r $K video white 1920 1080 nv12 --flip 655 --alt black --hold 0

echo "=== 4 video T2"
$K video p2 1280 720 nv12 --hold 20 & sleep 4
dmesg | grep 'video:' | tail -1
set -- $(lc); echo "luma=$1 chroma=$2"
r $B verify t2 --luma $1 --chroma $2 --size 1280x720 --log $L
r $B verify scan --size 1280x720 --log $L
wait; echo "video p2 rc=$?"
for p in quad left top white; do
  $K video $p 1280 720 nv12 --hold 8 & sleep 4
  r $B verify hist --expect $p --log $L
  wait; echo "video $p rc=$?"
done

echo "=== 5 planes together"
$K video black 1920 1080 nv12 --rgb white --alpha 255 --hold 8 & sleep 4
r $B verify hist --expect white --log $L
wait
$K video black 1920 1080 nv12 --rgb white --alpha 128 --hold 8 & sleep 4
r $B verify hist --expect white --log $L
wait
$K video black 1920 1080 nv12 --rgb white --alpha 0 --hold 8 & sleep 4
r $B verify hist --expect black --log $L
r $B dump pnl --log $L
wait

echo "=== 6 unload"
r rmmod h713_drm
dmesg | tail -3
r $B dump scanout --log $L; r $B dump mix --log $L; r $B dump pnl --log $L
dmesg | grep -E 'h713|drm' | tail -40
echo "=== end"
