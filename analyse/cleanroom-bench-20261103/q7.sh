#!/bin/sh
# Q-DRM-7: the clean composer's full enable (vp-bench apply) with one pause only, three times in one fresh bench boot.
# q7.sh PACE LOG    (PACE = PER_WRITE_US,BETWEEN_TABLES_US)
B=/root/vp-bench; P=$1; L=$2; DB=/boot/mips/database.TSE
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
echo "=== q7 pace $P"; uname -r; cat /proc/uptime
r $B frame white 0x4c000000 1920 1080 nv12 --log $L
for n in 1 2; do
  echo "=== enable $n (pace $P)"
  r $B apply --db $DB --luma 0x4c000000 --pace $P --log $L
  r $B verify scan --log $L
  r $B verify hist --expect white --log $L
  r $B frame black 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect black --log $L
  r $B frame white 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect white --log $L
done
echo "=== disable, then enable 3 (pace $P)"
r $B apply --mode disable --luma 0x4c000000 --log $L
sleep 1
r $B apply --db $DB --luma 0x4c000000 --pace $P --log $L
r $B verify scan --log $L
r $B verify hist --expect white --log $L
r $B frame black 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect black --log $L
r $B frame white 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect white --log $L
echo "=== end"
