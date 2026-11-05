import sys, re, collections
L=open(sys.argv[1]).read().splitlines()
st={}; ev=[]
for l in L[1:-1]:
    t,rest=l.split(' ',1); t=float(t)
    for it in rest.split():
        k,v=it.split(':'); a,b=v.split('>'); ev.append((t,int(k,16),int(a,16),int(b,16)))
# reconstruct timing pairs
cur={}
def val(k): return cur.get(k)
hv=[]
for t,k,a,b in ev:
    cur.setdefault(k,a); cur[k]=b
    if 0x06840028<=k<=0x06840037:
        g=lambda o: (cur.get(0x06840000+o,0)<<8)|cur.get(0x06840001+o,0)
        hv.append((t,g(0x28),g(0x34)))
# first time htotal==2200 stable and vtotal==1125
def first(cond):
    for t,h,v in hv:
        if cond(h,v): return t
print("first h=2200:", first(lambda h,v:h==2200), " first v=1125:", first(lambda h,v:v==1125))
cnt=collections.Counter(k for _,k,_,_ in ev)
print("changes per address (top, excluding the >50 movers):")
print(" ".join(f"{k:#x}:{c}" for k,c in sorted(cnt.items()) if c<=50))
print("movers >50:", " ".join(f"{k:#x}:{c}" for k,c in sorted(cnt.items()) if c>50))
