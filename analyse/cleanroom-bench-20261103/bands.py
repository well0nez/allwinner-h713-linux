import sys,time
sys.path.insert(0,"/data/bench")
from blog import rd,wr,wr_logged,log,map_ram,openlog
PNL=0x051c0000; A=0x4B200000
G=[0x00,0x20,0x40,0x60,0x80,0xa0,0xc0,0xe0]
def fill_bands():
    m,off=map_ram(A,7680*1080)
    for k in range(8):
        r0=k*135; g=G[k]
        m[off+r0*7680:off+(r0+135)*7680]=bytes([g,g,g,0xff])*(1920*135)
def bands(tag):
    time.sleep(0.12); h=[rd(PNL+0x380+4*i) for i in range(32)]
    out=[f"rows{k*135}-{k*135+134}:{h[G[k]>>3]/1920:.2f}" for k in range(8)]
    other={i:v for i,v in enumerate(h) if v and i not in [g>>3 for g in G]+[5,6]}
    log(f"BANDS {tag}: video {(h[5]+h[6])/1920:.2f} lines; visible lines per 135-row band: "+" ".join(out)+f"; other bins {other}")
