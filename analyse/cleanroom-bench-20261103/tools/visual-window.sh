#!/bin/sh
# visual-window.sh STATE - one command per wall state of the owner's visual window (spec side, 2026-11-03).
#   ref     take the env reference (/data/bench/env-before-vis.txt) - run first, on the normal boot
#   1       normal 7.3.1 boot, firmware HDMI path; afterwards the owner presses OK on the launcher ("HDMI input")
#   bench   arm the one-shot bench boot B0 with the 7.3.1-rustbench FIT and boot it
#   2       (bench) h713_drm.ko bench=1 restore_logo=1 align_cal=1, P1 colour bars 1920x1080 on the video plane
#   3       (bench) P1 under a white RGB plane at alpha 128 (the overlay after align_cal=1)
#   4       (bench) rmmod h713_drm: the boot logo back
#   5       (bench) the HDMI source through the clean driver (h713_drm stage 3, `kms-test hdmi`; the source must be on)
#   restore env back to the reference, normal boot
# Needs /data/bench/{envrestore.py,blog.py} and /root/{h713_drm.ko,kms-test,
# vp-bench,vis.sh} on the device.
set -eu
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=10 -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
D=$(dirname "$0")
waitup() {
	sleep 22
	i=0
	while [ $i -lt 50 ]; do $S true 2>/dev/null && break; sleep 3; i=$((i + 1)); done
	$S 'uptime; grep -q module_blacklist /proc/cmdline && echo BOOT=bench || echo BOOT=normal'
}
case "$1" in
ref) $S 'fw_printenv > /data/bench/env-before-vis.txt; wc -l /data/bench/env-before-vis.txt' ;;
1)
	$S 'sync; (sleep 1; systemctl reboot) >/dev/null 2>&1 &'
	waitup
	sleep 10
	$S 'h713-tv ctl status | grep -E "^signal|^picture|^cover"; h713-osd ctl status | grep launcher'
	;;
bench)
	$S 'fw_setenv bench_boot "wdt dev watchdog@2051000; wdt start 16000; h713_disp init \${h713_project} noboot logo; h713_conlog 0x45000000; mmc dev 1; mmc write 0x45000000 0x2800 0x400; run bench_hang; run bench_kernel; reset" &&
	fw_setenv bench_hang "echo bench: no hang" &&
	fw_setenv bench_kernel "if ext4load mmc 1:5 0x60000000 h713-kernel-rustbench73.fit; then setenv bootargs \"\${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd systemd.mask=h713-tv@video1.service systemd.mask=h713-warp.service systemd.mask=h713-osd.service systemd.mask=h713-desktop.service systemd.mask=h713-keystone-auto.service consoleblank=0\"; bootm 0x60000000; fi" &&
	fw_setenv bootcmd "if test -n \"\${h713_bench}\"; then setenv h713_bench; saveenv; run bench_boot; fi; h713_disp init \${h713_project} logo; run boot_\${h713_boot}; run boot_net" &&
	fw_setenv h713_bench 1 && sync; (sleep 1; systemctl reboot) >/dev/null 2>&1 &'
	waitup
	;;
2 | 3 | 4 | 5) $S "sh /root/vis.sh $1" ;;
restore)
	$S 'python3 /data/bench/envrestore.py /data/bench/env-before-vis.txt; diff <(fw_printenv) /data/bench/env-before-vis.txt && echo ENV-OK'
	"$0" 1
	;;
*) echo "usage: $0 ref|1|bench|2|3|4|5|restore" >&2; exit 2 ;;
esac
