#!/bin/sh
# wrun.sh TAG "SWITCHES OFF": one standby after vp-bench apply with those switches off; prints GOOD or LOST
r=$(PRE="$3" VPBOFF="$2" sh /tmp/specbench/stbrun.sh $1 vpb - 2>&1)
echo "$r" | grep -E "done:" | head -1 | cut -c1-80
if echo "$r" | grep -q "back rc=0"; then echo "$1 GOOD (off: $2)"; else echo "$1 LOST (off: $2) $(echo "$r" | grep -o 'cause [0-9] ([a-z ]*)' | head -1)"; fi
