#!/bin/sh
# Q-DRM-7 control: the clean composer's full enable with no pause in a fresh bench boot, then once more with the
# measured pacing in the same boot.
B=/root/vp-bench; L=$1; DB=/boot/mips/database.TSE
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
uname -r; cat /proc/uptime
r $B frame white 0x4c000000 1920 1080 nv12 --log $L
echo "=== enable 1 (pace 0,0)"
r $B apply --db $DB --luma 0x4c000000 --pace 0,0 --log $L
r $B verify scan --log $L
r $B frame black 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect black --log $L
r $B frame white 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect white --log $L
echo "=== enable 2 (pace 1000,200000)"
r $B apply --db $DB --luma 0x4c000000 --pace 1000,200000 --log $L
r $B verify scan --log $L
r $B frame black 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect black --log $L
r $B frame white 0x4c000000 1920 1080 nv12 --log $L; r $B verify hist --expect white --log $L
echo "=== end"
