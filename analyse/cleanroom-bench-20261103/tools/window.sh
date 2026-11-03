#!/bin/sh
# The owner's visual window on a fixed schedule (2026-11-04): 1 normal-boot HDMI 20 s -> bench reboot -> 2 P1 bars 20 s
# -> 3 bars under a white overlay 20 s -> 4 boot logo 10 s -> 5 HDMI via the clean module 30 s -> restore.
# Every state's start and end is logged with the host time (UTC) to /tmp/specbench/window.log.
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=10 -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
W=/tmp/specbench/window.log
ts() { echo "$(date -u +%H:%M:%S) $*" | tee -a $W; }
hold() { sleep "$1"; }
: > $W
ts "window start"
$S 'fw_printenv > /data/bench/env-before-vis.txt'
# state 1
$S 'h713-osd ctl launcher close >/dev/null; sleep 1; h713-tv ctl status | grep -E "^picture|^cover|^signal" | tr -s " " | tr "\n" ";"' | sed 's/^/  /' | tee -a $W; echo >> $W
ts "STATE 1 on: normal boot, the console's picture through the vendor firmware path"
hold 20
ts "STATE 1 end; rebooting into the bench (the boot logo shows during the reboot)"
$S 'fw_setenv bench_boot "wdt dev watchdog@2051000; wdt start 16000; h713_disp init \${h713_project} noboot logo; h713_conlog 0x45000000; mmc dev 1; mmc write 0x45000000 0x2800 0x400; run bench_hang; run bench_kernel; reset" &&
fw_setenv bench_hang "echo bench: no hang" &&
fw_setenv bench_kernel "if ext4load mmc 1:5 0x60000000 h713-kernel-rustbench73.fit; then setenv bootargs \"\${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd systemd.mask=h713-tv@video1.service systemd.mask=h713-warp.service systemd.mask=h713-osd.service systemd.mask=h713-desktop.service systemd.mask=h713-keystone-auto.service consoleblank=0\"; bootm 0x60000000; fi" &&
fw_setenv bootcmd "if test -n \"\${h713_bench}\"; then setenv h713_bench; saveenv; run bench_boot; fi; h713_disp init \${h713_project} logo; run boot_\${h713_boot}; run boot_net" &&
fw_setenv h713_bench 1'
timeout 200 sh /tmp/specbench/boot.sh bench | grep BOOT | sed 's/^/  /' | tee -a $W
$S 'while [ $(cut -d. -f1 /proc/uptime) -lt 28 ]; do sleep 1; done'
for st in 2 3 4 5; do
	case $st in 2) d=20; what="P1 colour bars (clean module)" ;; 3) d=20; what="the bars under a half-transparent white plane (after align_cal=1)" ;;
	4) d=10; what="the boot logo (module unloaded)" ;; 5) d=30; what="the console's picture through the clean driver" ;; esac
	$S "sh /root/vis.sh $st" 2>&1 | grep -E "PASS|FAIL|rmmod rc|capturing|0x05600178|shows the ring" | cut -c1-160 | sed 's/^/  /' | tee -a $W
	ts "STATE $st on: $what"
	hold $d
	ts "STATE $st end"
done
$S 'pkill -x kms-test; python3 /data/bench/envrestore.py /data/bench/env-before-vis.txt >/dev/null; diff <(fw_printenv) /data/bench/env-before-vis.txt >/dev/null && echo "env identical"' | sed 's/^/  /' | tee -a $W
ts "restore: rebooting into the normal boot"
timeout 200 sh /tmp/specbench/boot.sh normal | grep BOOT | sed 's/^/  /' | tee -a $W
ts "window end"
