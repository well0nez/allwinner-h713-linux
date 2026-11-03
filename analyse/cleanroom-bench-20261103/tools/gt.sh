#!/bin/sh
# gt.sh GROUP... : one bench boot, gatetest the groups in order; prints OK lines or HANG at <group>
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=10 -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
timeout 200 sh /tmp/specbench/boot.sh bench | grep BOOT
timeout 90 $S "while [ \$(cut -d. -f1 /proc/uptime) -lt 30 ]; do sleep 1; done; python3 /data/bench/gatetest.py /data/bench/gate-q2.log $* | grep -E 'GATES .* (read ok|restored)' | cut -c12-200; sync" 2>/dev/null
sleep 3; i=0; while [ $i -lt 30 ]; do $S true 2>/dev/null && break; sleep 5; i=$((i+1)); done
$S 'grep -q module_blacklist /proc/cmdline && echo AFTER=bench || echo AFTER=normal; tail -1 /data/bench/gate-q2.log | cut -c12-160'
