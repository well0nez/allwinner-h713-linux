#!/bin/sh
# g.sh N: fresh bench boot, TMDS bit before the module, then step 8 quick with the module; outputs to drm15f/
S="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=10 -o ConnectTimeout=8 -J root@192.168.0.180 root@192.168.4.1"
k=$1
timeout 200 sh /tmp/specbench/boot.sh bench | grep -q BOOT=bench || echo "not bench"
$S "while [ \$(cut -d. -f1 /proc/uptime) -lt 30 ]; do sleep 1; done; echo before the module: \$(python3 /root/peek.py 0x068008fc 1); modprobe sun50i-h713-arisc; insmod /root/h713_drm.ko bench=1 restore_logo=1; /root/kms-test hdmi --secs 10 --wait 40 > /root/$k.txt 2>&1; dmesg > /root/$k-dmesg.txt; echo after: \$(python3 /root/peek.py 0x068008fc 1)"
$S "cat /root/$k.txt" > drm15f/$k.txt; $S "cat /root/$k-dmesg.txt" > drm15f/$k-dmesg.txt
echo "### $k"; grep -E "hdmi_state|^PASS|^FAIL" drm15f/$k.txt | head -8
grep -E "TV top|hdmi: (provider|no TMDS|TMDS|receiver sequence|tmds|no-signal|unsupported|locked)" drm15f/$k-dmesg.txt | cut -c1-200 | head -10
