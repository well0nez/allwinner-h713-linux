import sys,time; sys.path.insert(0,"/data/bench")
from blog import openlog,rd,wr,log,map_ram
import importlib.util
openlog(sys.argv[1])
SC=0x05600000; PNL=0x051c0000; A=0x4B200000
m,off=map_ram(A,7680*1080); m[off:off+7680*1080]=b"\xff"*(7680*1080)
def phase(sec=0.08):
    wr(SC+0xc0,1); wr(SC+0x168,2); tv=[];tr=[]; t0=time.perf_counter()
    while time.perf_counter()-t0<sec:
        if rd(SC+0xc0)&1: tv.append(time.perf_counter()); wr(SC+0xc0,1)
        if rd(SC+0x168)&2: tr.append(time.perf_counter()); wr(SC+0x168,2)
    d=sorted(((min([r for r in tr if r>v],default=v)-v)*1000) for v in tv)
    d=[x for x in d if x>0]
    return d[len(d)//2] if d else -1
def unc():
    time.sleep(0.05); h=[rd(PNL+0x380+4*i) for i in range(32)]; return sum(h[:9])/1920, sum(h[9:24])/1920
step=int(sys.argv[2]); n=int(sys.argv[3])
a=0x0525c000; old=rd(a)
for k in range(n):
    p=phase(); u,mid=unc()
    log(f"SCAN {k*step:4d} phase {p:.3f} ms = {p/0.013563:.1f} lines, uncovered {u:.2f} mid {mid:.2f}")
    wr(a,old-0x10000); time.sleep(step/65.54); wr(a,old)
log(f"SCAN end phase {phase():.3f}")
