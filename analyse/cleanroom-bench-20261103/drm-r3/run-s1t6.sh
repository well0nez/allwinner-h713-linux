#!/bin/sh
# notes/impl-drm.md (clean repo 0af7d18) step 5 with the round-3 module: align=1, then align_cal=1, also 720p.
# Additions: ftrace of the two interrupt lines (Q-ALN-3), a polled-status delay while the module holds the planes.
B=/root/vp-bench; K=/root/kms-test; L=/root/drm-bench3.log; T=/sys/kernel/tracing
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
trace_on() { echo 0 > $T/tracing_on; echo > $T/trace; echo 'irq == 334 || irq == 335' > $T/events/irq/irq_handler_entry/filter;
  echo 1 > $T/events/irq/irq_handler_entry/enable; echo 1 > $T/tracing_on; }
trace_off() { echo 0 > $T/tracing_on; grep -E 'irq=(334|335)' $T/trace > /root/trace-$1.txt; echo "trace $1: $(wc -l < /root/trace-$1.txt) entries"; }
poll() { python3 /data/bench/phase.py; }
echo "=== 0"; uname -r; cat /proc/cmdline; ls $T >/dev/null && echo ftrace ok
for cal in 0 1; do
  echo "=== module align=1 align_cal=$cal"
  r insmod /root/h713_drm.ko bench=1 restore_logo=1 align=1 align_cal=$cal
  dmesg | grep -E 'h713-drm|h713_drm' | tail -4
  trace_on
  r $K s1t6
  trace_off s1t6-cal$cal
  dmesg | grep 'align' | tail -4
  echo "--- hold 1080p, both planes, alpha 255"
  trace_on
  $K video black 1920 1080 nv12 --rgb white --alpha 255 --hold 16 & sleep 6
  trace_off hold1080-cal$cal
  dmesg | grep 'align' | tail -2
  r $B verify hist --expect white --log $L
  poll
  wait
  echo "--- 720p (Q-ALN-2)"
  trace_on
  $K video black 1280 720 nv12 --rgb white --alpha 255 --hold 16 & sleep 6
  trace_off hold720-cal$cal
  dmesg | grep 'align' | tail -2
  r $B verify hist --expect white --log $L
  poll
  wait
  r rmmod h713_drm
  dmesg | tail -2
done
echo "=== end"
