#!/bin/sh
# st9run.sh TAG MODE : bench boot, one step-9 sleep (detached on the device, so a Wi-Fi restart cannot kill it), report
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=10 -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
timeout 200 sh /tmp/specbench/boot.sh bench >/dev/null 2>&1
timeout 120 $S "while [ \$(cut -d. -f1 /proc/uptime) -lt 30 ]; do sleep 1; done; PREINIT=$PREINIT setsid nohup sh /data/bench/st15.sh $1 $2 </dev/null >/dev/null 2>&1 &" >/dev/null 2>&1
sleep 100
i=0; while [ $i -lt 60 ]; do $S "grep -q 'st15 $1: done' /data/bench/st15-$1.log" 2>/dev/null && break; $S "grep -q module_blacklist /proc/cmdline" 2>/dev/null || break; sleep 10; i=$((i+1)); done
i=0; while [ $i -lt 60 ]; do $S true 2>/dev/null && break; sleep 5; i=$((i+1)); done
$S 'touch /run/stb-ok; systemctl stop stb-guard.timer 2>/dev/null' 2>/dev/null
r=$($S "grep -q module_blacklist /proc/cmdline && echo NOW=bench || echo NOW=normal; dmesg | grep 'previous run' | grep -o 'phase [a-z]*.*cause [0-9] ([a-z ]*)'; cat /data/bench/st15-$1.log")
if echo "$r" | grep -q "back rc=0"; then w=WOKE; else w=LOST; fi
if echo "$r" | grep -q "st15 $1: done"; then f=finished; else f="not finished (reset after the wake)"; fi
echo "### $1 $2 $w, $f"
echo "$r" | grep -vE "^[0-9.]+ h713-wifi" | cut -c1-230
