#!/bin/sh
# histchk.sh LOG : fill white/black/grey/P1/white and print the panel histogram and the PROC probe each time
L=$1; cd /data/bench
for p in white black grey P1 white; do
python3 q1.py $L fill $p >/dev/null; sleep 0.3
python3 q1.py $L rd 0x051c0380 32 hist | python3 -c "
import sys,re
v=[]
for l in sys.stdin:
  m=re.search(r': ((?:[0-9a-f]{8} ?)+)$',l.rstrip())
  if m and '0x051c03' in l: v+=[int(x,16) for x in m.group(1).split()]
print('$p hist sum',sum(v),[(i,x) for i,x in enumerate(v) if x][:12])"
python3 q1.py $L rd 0x05140600 2 | grep 0x05140600:
done
