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
    return f"{d[len(d)//2]:.1f}" if d else "none"
def unc():
    time.sleep(0.06); h=[rd(PNL+0x380+4*i) for i in range(32)]; lo=sum(h[:9]); return f"{lo} dx~{1920-(2073600-lo)/1035:.0f}"
a=int(sys.argv[2],0); bit=int(sys.argv[3]); hold=float(sys.argv[4])
old=rd(a)
log(f"RESTART base phase {phase()} unc {unc()}")
for k in range(int(sys.argv[5])):
    wr(a,old|(1<<bit)); time.sleep(hold); wr(a,old); time.sleep(0.05)
    log(f"RESTART {a:#x} bit{bit} hold {hold}: phase {phase()} lines unc {unc()}")
