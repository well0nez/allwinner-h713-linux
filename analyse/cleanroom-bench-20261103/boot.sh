#!/bin/sh
# boot.sh bench|normal : reboot the HY320 (bench = arm the one-shot first), wait for ssh, report the boot kind
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -J root@192.168.0.180 root@192.168.4.1"
if [ "$1" = bench ]; then pre='fw_setenv h713_bench 1 && fw_printenv h713_bench && '; else pre=''; fi
$S "${pre}sync && (sleep 1; systemctl reboot) >/dev/null 2>&1 &"
t0=$(date +%s)
sleep 22
i=0
while [ $i -lt 50 ]; do
	$S true 2>/dev/null && break
	sleep 3
	i=$((i + 1))
done
echo "back after $(( $(date +%s) - t0 )) s"
$S 'uptime; if grep -q module_blacklist /proc/cmdline; then echo BOOT=bench; else echo BOOT=normal; fi; fw_printenv h713_bench'
