#!/bin/bash
# tastentest.sh [SEK] -- Einschalttaste unter Linux pruefen, ohne dass sie ausschaltet (Plan 103 G3):
# blockiert handle-power-key per systemd-inhibit, schreibt SEK Sekunden lang Pegel der Leitung gpio-4 ("power"),
# IRQ-Zaehler (PL4 = "4 Edge power") und EINT-Status mit, liest Ereignisse von /dev/input/event1.
SEK=${1:-40}; B=root@192.168.8.141
ssh -o ConnectTimeout=5 $B "nohup systemd-inhibit --what=handle-power-key --who=tastentest --why=Messung --mode=block sleep $((SEK+10)) >/dev/null 2>&1 &
sleep 0.3
nohup bash -c 'for i in \$(seq 1 $((SEK*4))); do echo \"\$(date +%T.%N | cut -c1-11) \$(grep -h \"gpio-4 \" /sys/kernel/debug/gpio | tr -s \" \" | cut -c1-60) irq=\$(grep \" 4 Edge\" /proc/interrupts | awk \"{print \\\$2+\\\$3+\\\$4+\\\$5}\")\"; sleep 0.25; done; echo fertig' > /tmp/tastentest-pegel.log 2>&1 &
nohup python3 -c '
import struct,time,fcntl,os
f=open(\"/dev/input/event1\",\"rb\"); fl=fcntl.fcntl(f,fcntl.F_GETFL); fcntl.fcntl(f,fcntl.F_SETFL,fl|os.O_NONBLOCK); t0=time.time(); n=0
while time.time()-t0<$SEK:
    try: d=f.read(24)
    except BlockingIOError: d=None
    if d:
        s,us,typ,code,val=struct.unpack(\"qqHHi\",d)
        if typ==1: print(\"%.1fs KEY code=%d val=%d\"%(time.time()-t0,code,val)); n+=1
    else: time.sleep(0.02)
print(\"fertig, %d Tastenereignisse\"%n)' > /tmp/tastentest-ev.log 2>&1 &
echo \"laeuft \$(date +%T), $SEK s\""
echo "JETZT die Taste druecken (kurz und einmal 3 s halten). Warte auf Ende ..."
ssh -o ConnectTimeout=5 $B "until grep -q fertig /tmp/tastentest-pegel.log && grep -q fertig /tmp/tastentest-ev.log; do sleep 2; done
echo \"Pegel-Proben: \$(grep -c gpio-4 /tmp/tastentest-pegel.log), davon lo: \$(grep -c 'in lo' /tmp/tastentest-pegel.log)\"
grep 'in lo' /tmp/tastentest-pegel.log | head -1 | cut -c1-80; grep 'in lo' /tmp/tastentest-pegel.log | tail -1 | cut -c1-80
tail -2 /tmp/tastentest-pegel.log | head -1 | cut -c1-80
cat /tmp/tastentest-ev.log
python3 - <<PY
import mmap, os, struct
fd=os.open('/dev/mem', os.O_RDONLY|os.O_SYNC); m=mmap.mmap(fd, 0x1000, offset=0x07022000, prot=mmap.PROT_READ)
r=lambda o: struct.unpack('<I', m[o:o+4])[0]
print('R_PIO: PL4 mux %x  DAT %08x  EINT CFG0 %08x CTL %08x STATUS %08x' % ((r(0)>>16)&0xf, r(0x10), r(0x200), r(0x210), r(0x214)))
PY"
