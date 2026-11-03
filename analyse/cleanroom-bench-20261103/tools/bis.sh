#!/bin/sh
# 50 §6a bisect: bis.sh STEPS - one bench boot per call. Lock = timing 2200/1920/1125/1080 held 2 s; then the capture.
cd /data/bench; L=/data/bench/bis.log
case "$(uname -r)" in 7.3*) K=/data/bench/spx4-73.ko ;; *) K=/data/bench/spx4.ko ;; esac
insmod $K port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
sync; sleep 3
NGROUPS="${2:-abcde}" python3 x5min.py $L "$1" > /dev/null
sleep 2
python3 -c "
import sys; sys.path.insert(0,'/data/bench'); from blog import _page, rd
def rb(a):
    m,o=_page(a); return m[o]
L=0x06840000; t=bytes(rb(L+0x28+i) for i in range(0x18)); h=lambda o: t[o]<<8|t[o+1]
print('BISECT $1 ${2:-abcde}: timing h %d/%d v %d/%d 37a=%02x' % (h(0),h(2),h(0xc),h(0xe),rb(L+0x37a)))"
python3 cap7.py $L keep > /dev/null
python3 -c "
import sys,time; sys.path.insert(0,'/data/bench'); from blog import rd
a=rd(0x06940104); time.sleep(0.5); b=rd(0x06940104)
print('BISECT $1 ${2:-abcde}: capture frames in 0.5 s: %d (0x104 %08x -> %08x), 0x548 %08x' % (((b>>16)-(a>>16))&0xffff, a, b, rd(0x06940548)))"
