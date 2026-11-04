#!/bin/sh
# w2run.sh TAG: full stage 2 (vp-bench), channel 0 and NRC write channels off before the sleep, stage 2 again after
r=$(PRE=vpbdisable,nrcoff VPBOFF="" sh /tmp/specbench/stbrun.sh $1 vpb ${2:-vpbapply} 2>&1)
if echo "$r" | grep -q "back rc=0"; then echo "$1 GOOD"; else echo "$1 LOST $(echo "$r" | grep -o 'cause [0-9] ([a-z ]*)' | head -1)"; fi
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
$S "grep -h 'after the wake' /data/bench/stb-$1-rsm.log | cut -c12-200" 2>/dev/null
