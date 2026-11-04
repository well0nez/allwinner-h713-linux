#!/bin/sh
# w3run.sh TAG POST: full stage 2; channel 0, NRC writes and the TV side off before the sleep; POST after
r=$(PRE=vpbdisable,nrcoff,tvoff VPBOFF="" sh /tmp/specbench/stbrun.sh $1 vpb $2 2>&1)
if echo "$r" | grep -q "back rc=0"; then echo "$1 woke"; else echo "$1 LOST $(echo "$r" | grep -o 'cause [0-9] ([a-z ]*)' | head -1)"; fi
echo "$r" | grep -E "NOW="
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
$S "grep -h 'after the wake' /data/bench/stb-$1-rsm.log | cut -c12-200; grep -ah 'FAIL' /data/bench/stb-$1-rsm.log.vpb | cut -c19-120; tail -1 /data/bench/stb-$1-rsm.log.vpb | cut -c1-120" 2>/dev/null
