#!/bin/sh
# Q-HDMI-1/2: provider, then the minimal receiver set and the capture with no pauses (rxtime.py). Run on a bench boot
# with or without clk_ignore_unused/pd_ignore_unused. Display blocks are not read.
cd /data/bench; L=/data/bench/clk-$(grep -q clk_ignore_unused /proc/cmdline && echo keep || echo cleanup).log
echo "log $L"; grep -o "clk_ignore_unused\|pd_ignore_unused" /proc/cmdline | tr '\n' ' '; echo
dmesg | grep -iE "Disabling unused|clk: Not disabling|pd_ignore|genpd.*off|power.*domain" | head -5 | cut -c1-140
python3 wdump.py $L ccu 0x02001000:0x1000 > /dev/null; python3 wdump.py $L ppu 0x07001000:0x240 > /dev/null
grep "DUMP ccu w 0x02001d[0-9a-f]0\|DUMP ccu w 0x02001040\|DUMP ccu w 0x02001050" $L | cut -c12-200
grep "DUMP ppu" $L | cut -c12-200 | sed -n '1,40p' | grep -v ": 00000000 00000000 00000000 00000000"
case "$(uname -r)" in 7.3*) K=/data/bench/spx4-73.ko ;; *) K=/data/bench/spx4.ko ;; esac
insmod $K port=1 hpd=3; dmesg | grep -q "edid_init(port 1, 512 bytes) = 0" || { echo "EDID init failed"; exit 1; }
echo "provider done at $(cut -d' ' -f1 /proc/uptime)"
t=0; while [ $t -lt 100 ]; do python3 -c "
import sys; sys.path.insert(0,'/data/bench'); from blog import _page
m,o=_page(0x068008fc); sys.exit(0 if m[o]&0x80 else 1)" && break; sleep 0.05; t=$((t+1)); done
echo "TMDS seen at $(cut -d' ' -f1 /proc/uptime)"
python3 rxtime.py $L | grep RXTIME | cut -c12-260
