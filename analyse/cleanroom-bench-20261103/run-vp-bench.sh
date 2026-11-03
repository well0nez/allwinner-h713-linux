#!/bin/sh
# The clean side's procedure (notes/impl-stage2.md, "Bench procedure for 95 T1 and T2"), run as written.
# Only addition: each command's exit code is echoed, stdout/stderr go to /root/vp-bench-stdout.txt.
B=/root/vp-bench; DB=/boot/mips/database.TSE; L=/root/vp-bench-stage2.log
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
r $B dump all --log $L
r $B frame P1 0x4c000000 1920 1080 nv12 --log $L
$B plan  --db $DB --luma 0x4c000000 > /root/t1.plan; echo "plan rc=$?"
r $B apply --db $DB --luma 0x4c000000 --log $L
r $B verify t1   --luma 0x4c000000 --log $L
r $B verify scan --log $L
for p in white black P3 P1; do
  r $B frame $p 0x4c000000 1920 1080 nv12 --log $L; sleep 0.2
  case $p in P3) e=grey;; P1) e=p1;; *) e=$p;; esac
  r $B verify hist --expect $e --log $L
done
r $B frame P1 0x4c000000 1920 1080 nv12 --log $L
r $B frame P2 0x4c000000 1280 720 nv12 --log $L
r $B apply --db $DB --luma 0x4c000000 --size 1280x720 --log $L
r $B verify t2   --luma 0x4c000000 --size 1280x720 --log $L
r $B verify scan --log $L
r $B frame white 0x4c000000 1280 720 nv12 --log $L; sleep 0.2
r $B verify hist --expect white --log $L
r $B frame P1 0x4c000000 1280 720 nv12 --log $L
r $B verify t2   --luma 0x4c000000 --size 1280x720 --log $L
r $B apply --mode disable --log $L
