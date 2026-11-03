import sys,time; sys.path.insert(0,"/data/bench")
from blog import openlog,rd,wr,log
openlog(sys.argv[1])
SC=0x05600000; PNL=0x051c0000
def phase(sec=0.1):
    wr(SC+0xc0,1); wr(SC+0x168,2); tv=[];tr=[]; t0=time.perf_counter()
    while time.perf_counter()-t0<sec:
        if rd(SC+0xc0)&1: tv.append(time.perf_counter()); wr(SC+0xc0,1)
        if rd(SC+0x168)&2: tr.append(time.perf_counter()); wr(SC+0x168,2)
    d=sorted((min([r for r in tr if r>v],default=v)-v)*1000/0.013563 for v in tv)
    d=[x for x in d if x>0]
    return (f"{d[0]:.0f}..{d[-1]:.0f}" if d else "none")+f" v{len(tv)} r{len(tr)}"
def unc():
    time.sleep(0.06); h=[rd(PNL+0x380+4*i) for i in range(32)]; return f"{sum(h[:9])/1920:.2f}"
words=[int(x,0) for x in sys.argv[2].split(",")]
log(f"BITS base: phase {phase()} unc {unc()}")
for a in words:
    old=rd(a)
    for b in range(32):
        v=old^(1<<b)
        wr(a,v); time.sleep(0.05); p=phase(); u=unc(); rb=rd(a); wr(a,old); time.sleep(0.05); p2=phase(0.05); u2=unc()
        log(f"BITS {a:#010x} {old:#010x} bit{b:2d} -> rb {rb:#010x}: phase {p} unc {u} | restored phase {p2} unc {u2}")
