#!/bin/sh
# stbrun.sh TAG MODE: arm the bench, boot it, run one standby, report where it ended.
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=10 -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
timeout 200 sh /tmp/specbench/boot.sh bench | grep BOOT
timeout 300 $S "while [ \$(cut -d. -f1 /proc/uptime) -lt 30 ]; do sleep 1; done; sh /data/bench/stb.sh $1 20 $2 $3" >/dev/null 2>&1
i=0; while [ $i -lt 60 ]; do $S true 2>/dev/null && break; sleep 5; i=$((i+1)); done
$S 'touch /run/stb-ok; systemctl stop stb-guard.timer 2>/dev/null; echo guard disarmed' 2>/dev/null
$S "uptime; grep -q module_blacklist /proc/cmdline && echo NOW=bench || echo NOW=normal; dmesg | grep 'previous run' | cut -c1-230; grep -vE '^\[' /data/bench/stb-$1.log | grep -vE 'SNAP .* (begin|rc=)' | cut -c1-200"
